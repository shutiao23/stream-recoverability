#!/usr/bin/env python3
"""Keep the validation funnel alive across Cursor shell aborts.

This is an operations helper, not scientific evidence.  Formal claims remain
gated on completed manifests and a hash-verified roster.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/home/lzq/workspace/parttime/stream-recoverability")
SRC = str(ROOT / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def _validation_run_root() -> Path:
    from stream_recoverability.experiments.contracts import build_design_contract

    contract = build_design_contract(
        design_path=ROOT / "configs/design_freeze_v3.yaml",
        manifest_path=ROOT / "study_manifest.yaml",
        experiment_config_path=ROOT / "configs/experiments.yaml",
        data_version="published_v1",
        evaluation_split="validation",
        data_version_manifest_path=(
            ROOT / "data_versions/published_v1/version_manifest.json"
        ),
    )
    return (
        ROOT
        / "results/validation_funnel/published_v1"
        / str(contract["design_hash"])
    )


RUN = _validation_run_root()
SCRIPT = ROOT / "scripts/15_run_validation_funnel.py"
PYTHON = sys.executable
LOG = RUN / "funnel_watchdog.log"
PIDFILE = RUN / "funnel_watchdog.pid"
DEEP_DIR = RUN / "deep_single_seed"
DEEP_MANIFEST = DEEP_DIR / "validation_stage_manifest.json"
DEEP_LOG = DEEP_DIR / "watchdog_run.log"
STAGE3_MANIFEST = RUN / "deep_stability" / "validation_stage_manifest.json"
ROSTER = RUN / "finalized_model_roster.json"
AFTER_ROSTER = ROOT / "scripts/ops/after_roster_pipeline.py"
AFTER_LOG = RUN / "after_roster.log"
AFTER_STATUS = RUN / "after_roster_status.json"
POLL_SECONDS = 30
ALLOW_WATCHDOG = RUN / "ALLOW_WATCHDOG"
ALLOW_FREEZE_ROSTER = RUN / "ALLOW_FREEZE_ROSTER"
ALLOW_AFTER_ROSTER = RUN / "ALLOW_AFTER_ROSTER"

signal.signal(signal.SIGHUP, signal.SIG_IGN)


def log(message: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + message
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line, flush=True)


def _comm(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", "replace").strip()


def _alive(pid: int) -> bool:
    return Path(f"/proc/{pid}").is_dir()


def iter_python_cmds() -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if _comm(pid) not in {"python", "python3"}:
            continue
        cmd = _cmdline(pid)
        if cmd:
            found.append((pid, cmd))
    return found


def _is_funnel_cli(cmd: str) -> bool:
    return "15_run_validation_funnel.py" in cmd or "funnel_cli.py" in cmd


def deep_pids() -> list[int]:
    pids = []
    for pid, cmd in iter_python_cmds():
        if _is_funnel_cli(cmd) and "deep_single_seed" in cmd:
            pids.append(pid)
    return pids


def stability_pids() -> list[int]:
    pids = []
    for pid, cmd in iter_python_cmds():
        if _is_funnel_cli(cmd) and "deep_stability" in cmd:
            pids.append(pid)
    return pids


def watchdog_pids() -> list[int]:
    self = os.getpid()
    pids = []
    for pid, cmd in iter_python_cmds():
        if "funnel_watchdog.py" in cmd and pid != self:
            pids.append(pid)
    return pids


def after_roster_pids() -> list[int]:
    pids = []
    for pid, cmd in iter_python_cmds():
        if "after_roster_pipeline.py" in cmd:
            pids.append(pid)
    return pids


def validation_stage_complete(stage_dir: Path) -> bool:
    run_doc = None
    stage = stage_dir / "validation_stage_manifest.json"
    run_path = stage_dir / "run_manifest.json"
    if not stage.is_file() or not run_path.is_file():
        return False
    try:
        run_doc = json.loads(run_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(run_doc, dict):
        return False
    selected = run_doc.get("selected_scenarios")
    grid_count = run_doc.get("grid_scenario_count")
    full_invocation = (
        isinstance(selected, int)
        and isinstance(grid_count, int)
        and selected == grid_count
        and grid_count > 0
    )
    return (
        run_doc.get("run_unit_complete") is True
        and run_doc.get("evidence_complete") is True
        and full_invocation
    )


def ensure_after_roster() -> None:
    if not ALLOW_AFTER_ROSTER.is_file():
        log("after_roster blocked; missing ALLOW_AFTER_ROSTER")
        return
    if not ROSTER.is_file():
        return
    living = after_roster_pids()
    if living:
        log(f"after_roster_alive pid={living}")
        return
    if AFTER_STATUS.is_file():
        try:
            status = json.loads(AFTER_STATUS.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            status = {}
        if status.get("steps", {}).get("pipeline") in {
            "complete",
            "stopped_after_p12",
        }:
            log("after_roster_idle pipeline=" + str(status.get("steps", {}).get("pipeline")))
            return
    log("starting after_roster_pipeline")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONUNBUFFERED"] = "1"
    env["AFTER_ROSTER_STOP_AFTER"] = "p12"
    AFTER_LOG.parent.mkdir(parents=True, exist_ok=True)
    handle = AFTER_LOG.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        [PYTHON, str(AFTER_ROSTER)],
        cwd=ROOT,
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log(f"started_after_roster pid={proc.pid}")


def start_detached(args: list[str], logfile: Path) -> int:
    logfile.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONUNBUFFERED"] = "1"
    handle = logfile.open("a", encoding="utf-8")
    handle.write(
        "\n--- start "
        + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        + " "
        + " ".join(args)
        + " ---\n"
    )
    handle.flush()
    proc = subprocess.Popen(
        [PYTHON, str(SCRIPT), *args],
        cwd=ROOT,
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return proc.pid


def run_logged(args: list[str], logfile: Path) -> int:
    logfile.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONUNBUFFERED"] = "1"
    log("RUN " + " ".join(args))
    with logfile.open("a", encoding="utf-8") as handle:
        completed = subprocess.run(
            [PYTHON, str(SCRIPT), *args],
            cwd=ROOT,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
            start_new_session=True,
        )
    return completed.returncode


def checkpoint_names() -> list[str]:
    directory = DEEP_DIR / "checkpoints"
    if not directory.is_dir():
        return []
    return sorted(path.name for path in directory.glob("*.pt"))


def ensure_deep() -> None:
    if validation_stage_complete(DEEP_DIR):
        return
    pids = deep_pids()
    if pids:
        rss_kb = 0
        try:
            text = Path(f"/proc/{pids[0]}/status").read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("VmRSS:"):
                    rss_kb = int(line.split()[1])
        except OSError:
            pass
        log(
            f"deep_alive pid={pids} rss_mb={rss_kb / 1024:.0f} "
            f"checkpoints={checkpoint_names()}"
        )
        return
    log("deep_missing; restarting with resume")
    pid = start_detached(
        ["run", "--stage", "deep_single_seed"],
        DEEP_LOG,
    )
    log(f"restarted_deep pid={pid} log={DEEP_LOG}")


def continue_after_deep() -> None:
    if ROSTER.is_file():
        log(f"roster_present {ROSTER}")
        return
    if not validation_stage_complete(DEEP_DIR):
        return
    if stability_pids():
        log(f"deep_stability_alive pid={stability_pids()}")
        return
    diagnostics = RUN / "stage2_diagnostics.csv"
    ranking = RUN / "validation_model_ranking.csv"
    selection_path = RUN / "stage2_finalist_selection.manifest.json"
    decision = RUN / "proposed_go_no_go" / "proposed_go_no_go_decision.json"
    branch_metrics = RUN / "branch_ablation" / "branch_ablation_metrics.parquet"
    log("deep_single_seed complete; continuing funnel")
    if not diagnostics.is_file():
        if run_logged(["extract-diagnostics"], RUN / "continuation.log") != 0:
            log("extract-diagnostics failed")
            return
    if not ranking.is_file():
        if run_logged(["rank"], RUN / "continuation.log") != 0:
            log("rank failed")
            return
    if not selection_path.is_file():
        if (
            run_logged(
                ["select-finalists", "--diagnostics", str(diagnostics)],
                RUN / "continuation.log",
            )
            != 0
        ):
            log("select-finalists failed")
            return
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    finalists = [str(model) for model in selection.get("selected_models", ())]
    log("finalists=" + ",".join(finalists))
    if not finalists:
        log("no finalists; stopping")
        return
    if not validation_stage_complete(RUN / "deep_stability"):
        if (
            run_logged(
                ["run", "--stage", "deep_stability", "--models", *finalists],
                RUN / "deep_stability" / "watchdog_run.log",
            )
            != 0
        ):
            log("deep_stability failed")
            return
    if "proposed" in finalists:
        if not branch_metrics.is_file():
            if run_logged(["run-branch-ablation"], RUN / "continuation.log") != 0:
                log("run-branch-ablation failed")
                return
        if not decision.is_file():
            code = run_logged(
                [
                    "go-no-go",
                    "--event-metrics",
                    str(RUN / "traditional" / "event_metrics.parquet"),
                    str(RUN / "deep_stability" / "event_metrics.parquet"),
                    "--branch-ablations",
                    str(branch_metrics),
                ],
                RUN / "continuation.log",
            )
            if code != 0:
                log("go-no-go failed")
                return
    elif not decision.is_file():
        if run_logged(["go-no-go"], RUN / "continuation.log") != 0:
            log("go-no-go failed")
            return
    if not ALLOW_FREEZE_ROSTER.is_file():
        log(
            "freeze-roster blocked; missing ALLOW_FREEZE_ROSTER. "
            "Roster freeze is irreversible and must be started by hand after "
            "reading proposed_go_no_go_decision.json."
        )
        return
    if run_logged(["freeze-roster"], RUN / "continuation.log") != 0:
        log("freeze-roster failed")
        return
    log("funnel_complete roster=" + str(ROSTER.is_file()))


def already_running() -> bool:
    others = watchdog_pids()
    if not others:
        return False
    log(f"another_watchdog_running pid={others}; exiting")
    return True


def main() -> int:
    if not ALLOW_WATCHDOG.is_file():
        log(
            "watchdog_disarmed missing ALLOW_WATCHDOG; refusing to auto-continue "
            "freeze-roster or after_roster"
        )
        return 0
    if already_running():
        return 0
    PIDFILE.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    os.chdir(ROOT)
    log(f"watchdog_start pid={os.getpid()} sid={os.getsid(0)}")
    while True:
        try:
            if not ROSTER.is_file():
                ensure_deep()
                continue_after_deep()
            ensure_after_roster()
        except Exception as exc:  # noqa: BLE001
            log(f"watchdog_error {type(exc).__name__}: {exc}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
