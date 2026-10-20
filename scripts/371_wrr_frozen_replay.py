#!/usr/bin/env python3
"""Replay the sealed test protocol without refitting or changing a threshold."""

from __future__ import annotations

import argparse
import subprocess
import sys

import wrr_r3_common as C


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--rebuild-test-cases", action="store_true")
    args = parser.parse_args()
    C.protocol()
    gate = C.load_script("r3_replay_access_check", C.ROOT / "scripts/358_wrr_external_recovery.py")
    gate.verify_role_access("test")
    if args.check_only:
        print("[371] frozen inputs/models/thresholds verified; no fitting or test scoring", flush=True)
        return 0
    def run(name: str, *arguments: str) -> None:
        subprocess.run([sys.executable, str(C.ROOT / "scripts" / name), *arguments], cwd=C.ROOT, check=True)
    for protocol_name in ("leave_one_year_out", "strictly_prior_years"):
        for family, flag in [("admission", "--admission"), ("crossed", None), ("events", "--events"), ("real_calendars", "--real-calendars")]:
            if args.rebuild_test_cases:
                arguments = ["--role", "test", "--protocol", protocol_name, "--workers", str(args.workers)]
                if flag:
                    arguments.append(flag)
                run("358_wrr_external_recovery.py", *arguments)
            run("360_wrr_external_decisions.py", "--role", "test", "--protocol", protocol_name, "--family", family)
            run("373_wrr_hydrological_strata.py", "--protocol", protocol_name, "--family", family)
        run("366_wrr_composition_transfer.py", "--evaluate", "test", "--protocol", protocol_name)
        run("362_wrr_process_reference.py", "--role", "test", "--protocol", protocol_name, "--workers", str(args.workers))
    run("361_wrr_probabilistic_reference.py", "--evaluate", "test")
    run("367_wrr_revision_evidence.py")
    run("369_wrr_revision_si.py")
    run("368_wrr_revision_figures.py")
    print("[371] sealed inference replay complete; no model or threshold refitted", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
