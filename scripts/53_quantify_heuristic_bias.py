#!/usr/bin/env python3
"""Write synthetic heuristic-bias and Shapley-toy tables. No real-river Shapley."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.analysis.heuristic_bias import (
    PHASE1_RELATIVE_ERROR_MAX,
    forced_label_identity_rows,
    heuristic_bias_table,
    operator_vs_true_conditional_relative_error,
)
from stream_recoverability.analysis.operator_shapley import (
    shapley_frame,
    shapley_from_var1,
)
from stream_recoverability.experiments.synthetic_river import (
    donor_dominant_river,
    memory_dominant_river,
)

OUTPUT = ROOT / "results/framework/synthetic_identifiability"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    bias = heuristic_bias_table(gap_lengths=(14, 30, 90))
    forced = forced_label_identity_rows()
    bias_path = OUTPUT / "heuristic_bias_terms.csv"
    bias.to_csv(bias_path, index=False)
    forced.to_csv(OUTPUT / "heuristic_forced_label_identity.csv", index=False)

    shapley_rows = []
    for river in (memory_dominant_river(), donor_dominant_river()):
        for gap in (14, 30, 90):
            contributions = shapley_from_var1(
                river.transition,
                river.sigma,
                target=river.target,
                donors=river.donors,
                gap_length=gap,
                value_key="expected_mae_conditional",
            )
            frame = shapley_frame(
                contributions,
                river=river.name,
                gap_length=gap,
                value_key="expected_mae_conditional",
            )
            shapley_rows.append(frame)
    shapley = pd.concat(shapley_rows, ignore_index=True)
    shapley.to_csv(OUTPUT / "shapley_toy.csv", index=False)

    river = memory_dominant_river()
    error = operator_vs_true_conditional_relative_error(
        river.transition,
        river.sigma,
        target=river.target,
        donors=river.donors,
        gap_length=14,
    )
    gate = {
        "river": river.name,
        "gap_length": 14,
        "relative_error_mean_diag": error["relative_error_mean_diag"],
        "relative_error_frobenius": error["relative_error_frobenius"],
        "phase1_gate_max": PHASE1_RELATIVE_ERROR_MAX,
        "phase1_gate_pass": bool(error["phase1_gate_pass"]),
        "note": "Schur operator vs precision-block conditional on exact VAR(1).",
    }
    print(json.dumps(gate, indent=2, sort_keys=True))
    print(f"wrote {bias_path}")
    print(f"wrote {OUTPUT / 'shapley_toy.csv'}")


if __name__ == "__main__":
    main()
