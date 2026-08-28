#!/usr/bin/env python3
"""Fit v11 station-gap mixed models with network random intercepts."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.analysis.development_mixed_model import (
    compare_mixed_models,
)

INPUT = ROOT / "results/development_v11/station_gap_outcomes.csv"
OUTPUT = ROOT / "results/development_v11"


def main() -> None:
    frame = pd.read_csv(INPUT)
    selected = str(
        pd.read_csv(OUTPUT / "nested_lono_predictions.csv")[
            "selected_simple_model"
        ].mode().iloc[0]
    ).split("|")
    summaries, increment = compare_mixed_models(
        frame,
        simple_predictors=selected,
    )
    summaries.to_csv(OUTPUT / "mixed_model_summary.csv", index=False)
    (OUTPUT / "mixed_model_increment.json").write_text(
        json.dumps(increment, indent=2) + "\n", encoding="utf-8"
    )
    print(summaries.to_string(index=False))
    print(json.dumps(increment, indent=2))


if __name__ == "__main__":
    main()
