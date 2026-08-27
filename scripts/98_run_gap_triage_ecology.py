#!/usr/bin/env python3
"""T3(b) ecological bridge on W2 gap-specific fills."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.gap_triage_ecology import run_ecological_bridge

SCORES = (
    ROOT
    / "results/framework/public_rivers/w2_phase4_gap_specific/operator_station_scores.csv"
)
PANELS = ROOT / "results/framework/public_rivers"
OUTPUT = ROOT / "results/framework/public_rivers/w2_phase4_gap_specific"


def main() -> None:
    payload = run_ecological_bridge(
        scores_path=SCORES,
        panels_root=PANELS,
        output_dir=OUTPUT,
    )
    print(json.dumps({k: v for k, v in payload.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
