#!/usr/bin/env python3
"""Step 7: realistic failure replay on the same complete-year thermal endpoint."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.wrr_revision.paths import STEP7_FAILURE_REPLAY  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-networks", type=int, default=None)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--networks", default=None)
    args = parser.parse_args()
    STEP7_FAILURE_REPLAY.mkdir(parents=True, exist_ok=True)
    note = {
        "heat_event_labels": "training-period seasonal 90th percentile, min 3 days; overlap is a post-hoc diagnostic, not a deployment input",
        "hidden_observations": "replay_case hides every gap interior before prediction so adjacent outages cannot supply boundaries",
        "co_missing": "donors are masked on the same windows as the target",
        "geometry": "month/length/count transplanted from training-year natural gaps onto later complete years",
    }
    (STEP7_FAILURE_REPLAY / "FAILURE_DESIGN.json").write_text(json.dumps(note, indent=2))
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "173_wrr_thermal_decision.py"),
        "--failure-mode",
        "natural_transplant",
        "--co-missing",
        "--output",
        str(STEP7_FAILURE_REPLAY),
        "--workers",
        str(args.workers),
    ]
    if args.max_networks is not None:
        cmd.extend(["--max-networks", str(args.max_networks)])
    if args.networks:
        cmd.extend(["--networks", args.networks])
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
