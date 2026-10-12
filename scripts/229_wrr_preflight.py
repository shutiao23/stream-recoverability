#!/usr/bin/env python3
"""P0-03 preflight for the current WRR submission-readiness tree."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.wrr_submission_ready.run_identity import (  # noqa: E402
    preflight_current_study,
)


def main() -> None:
    report = preflight_current_study()
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
