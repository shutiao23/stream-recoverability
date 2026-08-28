#!/usr/bin/env python3
"""Evaluate fixed development safe-release thresholds on Route A confirmation."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.route_a_confirmation import (
    apply_safe_release_threshold,
    fit_safe_release_threshold,
)

DEVELOPMENT = ROOT / "results/development_v11/nested_lono_predictions.csv"
CONFIRMATION = ROOT / "results/development_v11/route_a_confirmation/predictions.csv"
OUTPUT = ROOT / "results/development_v11/route_a_confirmation/triage.json"


def main() -> None:
    development = pd.read_csv(DEVELOPMENT)
    confirmation = pd.read_csv(CONFIRMATION)
    simple_threshold = fit_safe_release_threshold(
        development, risk_column="simple_prediction"
    )
    length_threshold = fit_safe_release_threshold(
        development, risk_column="gap_length"
    )
    simple = apply_safe_release_threshold(
        confirmation,
        risk_column="predicted_loss",
        threshold=simple_threshold,
    )
    length = apply_safe_release_threshold(
        confirmation,
        risk_column="gap_length",
        threshold=length_threshold,
    )
    absolute_pp = 100.0 * (
        simple["safe_fill_fraction"] - length["safe_fill_fraction"]
    )
    relative = (
        (simple["safe_fill_fraction"] - length["safe_fill_fraction"])
        / length["safe_fill_fraction"]
        if length["safe_fill_fraction"] > 0
        else None
    )
    relative_pass = (
        relative >= 0.30
        if relative is not None
        else simple["safe_fill_fraction"] > 0
    )
    result = {
        "decision_endpoint": "gap_triage",
        "false_release_cap": 0.05,
        "unsafe_loss_c": 0.5,
        "threshold_source": "open_development_lono_only",
        "simple_model": simple,
        "gap_length": length,
        "absolute_improvement_pp": absolute_pp,
        "relative_improvement": relative,
        "relative_improvement_unbounded": bool(
            relative is None and simple["safe_fill_fraction"] > 0
        ),
        "passes_decision_floor": bool(relative_pass and absolute_pp >= 15.0),
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
