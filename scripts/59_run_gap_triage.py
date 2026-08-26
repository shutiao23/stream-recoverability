#!/usr/bin/env python3
"""T3(b) gap triage on scored fills. Development only; floors stay locked.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.gap_triage import compare_operator_to_length_only

OUTPUT = ROOT / "results/framework/public_rivers"


def _load_scores() -> pd.DataFrame:
    natural = OUTPUT / "natural_outage_scores.csv"
    if natural.is_file():
        frame = pd.read_csv(natural)
        if not frame.empty and "fill_mae" in frame.columns:
            return frame
    nested = OUTPUT / "operator_vs_univariate_network.csv"
    if nested.is_file():
        frame = pd.read_csv(nested)
        if "fill_mae" not in frame.columns and "donor_mae" in frame.columns:
            frame = frame.rename(columns={"donor_mae": "fill_mae"})
        return frame
    raise SystemExit("need natural_outage_scores.csv or operator_vs_univariate_network.csv")


def main() -> None:
    scores = _load_scores()
    result = compare_operator_to_length_only(scores)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "gap_triage.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
