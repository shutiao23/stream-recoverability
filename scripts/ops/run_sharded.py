#!/usr/bin/env python3
"""Run a resume-safe sharded experiment, then aggregate with shard_count=1.

Shared checkpoints must already exist, or --bootstrap-checkpoints starts shard 0
until --min-checkpoints files appear and only then launches the remaining shards.
This is an operations helper, not scientific evidence.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/home/lzq/workspace/parttime/stream-recoverability")


def log(message: str) -> None:
    line = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + message
    print(line, flush=True)


def checkpoint_files(output_dir: Path) -> list[Path]:
    directory = output_dir / "checkpoints"
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.glob("*.pt")
        if path.is_file() and not path.name.endswith(".sha256")
    )


def command_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONUNBUFFERED"] = "1"
    return env


def launch(command: list[str], logfile: Path) -> subprocess.Popen[str]:
    logfile.parent.mkdir(parents=True, exist_ok=True)
    handle = logfile.open("a", encoding="utf-8")
    handle.write(
        "\n--- start "
        + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        + " "
        + " ".join(command)
        + " ---\n"
    )
    handle.flush()
    return subprocess.Popen(
        command,
        cwd=ROOT,
        env=command_env(),
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
    )


def wait_process(proc: subprocess.Popen[str], name: str) -> int:
    code = proc.wait()
    log(f"{name} exit={code} pid={proc.pid}")
    return code


def shard_command(base: list[str], index: int, count: int) -> list[str]:
    return [*base, "--shard-index", str(index), "--shard-count", str(count)]


def wait_for_checkpoints(
    output_dir: Path,
    minimum: int,
    proc: subprocess.Popen[str],
    *,
    poll_seconds: int,
) -> bool:
    while True:
        found = checkpoint_files(output_dir)
        log(f"bootstrap checkpoints={len(found)}/{minimum}")
        if len(found) >= minimum:
            return True
        if proc.poll() is not None:
            log(f"bootstrap process exited before checkpoints pid={proc.pid}")
            return len(found) >= minimum
        time.sleep(poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--log-dir", type=Path, required=True)
    parser.add_argument("--shard-count", type=int, default=4)
    parser.add_argument("--min-checkpoints", type=int, default=0)
    parser.add_argument(
        "--bootstrap-checkpoints",
        action="store_true",
        help="start shard 0 first if checkpoints are missing, then launch the rest",
    )
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--skip-finalize", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a command is required after --")
    if args.shard_count < 1:
        parser.error("shard-count must be >= 1")
    if args.min_checkpoints < 0:
        parser.error("min-checkpoints must be >= 0")

    output_dir = args.output_dir
    log_dir = args.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    existing = checkpoint_files(output_dir)
    log(
        f"sharded_run output={output_dir} shards={args.shard_count} "
        f"checkpoints={len(existing)} min={args.min_checkpoints}"
    )

    if (
        args.min_checkpoints
        and len(existing) < args.min_checkpoints
        and not args.bootstrap_checkpoints
    ):
        log(
            "refusing to shard before shared checkpoints exist; "
            "pass --bootstrap-checkpoints or wait"
        )
        return 2

    processes: dict[int, subprocess.Popen[str]] = {}
    if args.bootstrap_checkpoints and len(existing) < args.min_checkpoints:
        log("bootstrap shard 0 until checkpoints exist")
        processes[0] = launch(
            shard_command(command, 0, args.shard_count),
            log_dir / "shard_0.log",
        )
        if args.min_checkpoints and not wait_for_checkpoints(
            output_dir,
            args.min_checkpoints,
            processes[0],
            poll_seconds=args.poll_seconds,
        ):
            return wait_process(processes[0], "shard_0") or 3
        existing = checkpoint_files(output_dir)
        log(f"bootstrap ready checkpoints={len(existing)}")

    for index in range(args.shard_count):
        if index in processes:
            continue
        processes[index] = launch(
            shard_command(command, index, args.shard_count),
            log_dir / f"shard_{index}.log",
        )
        log(f"started shard {index}/{args.shard_count} pid={processes[index].pid}")

    codes = {
        index: wait_process(proc, f"shard_{index}")
        for index, proc in processes.items()
    }
    failed = {index: code for index, code in codes.items() if code != 0}
    if failed:
        log(f"shard failures {failed}")
        return 1

    if args.skip_finalize:
        log("skip-finalize")
        return 0
    log("finalize shard_count=1 resume aggregate")
    finalize = launch(
        [*command, "--shard-index", "0", "--shard-count", "1"],
        log_dir / "finalize_aggregate.log",
    )
    return wait_process(finalize, "finalize")


if __name__ == "__main__":
    raise SystemExit(main())
