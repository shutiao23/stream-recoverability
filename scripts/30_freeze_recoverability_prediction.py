#!/usr/bin/env python3
"""Freeze the train-only analytic recoverability prediction before aggregation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.analysis.recoverability_budget import budget_decomposition

DEFAULT_GAPS = (1, 3, 7, 10, 14, 21, 30, 45, 60, 90, 120, 150, 180, 240, 365)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--train-data",
        type=Path,
        default=PROJECT_ROOT / "data_versions/published_v2/splits/train.parquet",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "results/predictions/recoverability_prediction_v1.json",
    )
    parser.add_argument("--gap-lengths", nargs="+", type=int, default=DEFAULT_GAPS)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    train = pd.read_parquet(args.train_data)
    stations = tuple(
        column[:-2]
        for column in train.columns
        if column.endswith("_T") and "_" not in column[:-2]
    )
    tables = [
        budget_decomposition(
            train,
            station,
            tuple(value for value in stations if value != station),
            args.gap_lengths,
        )
        for station in stations
    ]
    predictions = pd.concat(tables, ignore_index=True)
    reference_gap = min(args.gap_lengths, key=lambda value: abs(value - 30))
    station_types = {
        str(row.station): (
            "donor_dominated"
            if float(row.donor_component) >= float(row.memory_component)
            else "memory_dominated"
        )
        for row in predictions.loc[
            predictions["gap_length_days"].eq(reference_gap)
        ].itertuples(index=False)
    }
    payload = {
        "schema_version": "recoverability_prediction_v1",
        "status": "frozen_before_dense_aggregate",
        "evidence_role": "train_only_prediction",
        "formal_evidence": False,
        "data_version": "published_v2",
        "fit_split": "train",
        "fit_period": {"start": "2006-01-01", "end": "2015-12-31"},
        "formula": {
            "R2_avail": "R2_donor + (1 - R2_donor) * rho(d/4)^2",
            "predicted_skill": "1 - sqrt(1 - R2_avail)",
            "minimum_identifiable_acf_lag_days": 1,
        },
        "classification_reference_gap_days": int(reference_gap),
        "station_types": station_types,
        "dense_evidence_state_at_freeze": {
            "completed_scenarios": 1,
            "planned_scenarios": 900,
            "aggregate_exists": False,
            "only_completed_scenario": "SCI-DENSE-BLK-B1-T-D001-PUBLISHED_V2-DEVELOPMENT_TEST-R0101",
        },
        "predictions": predictions.to_dict(orient="records"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(args.output)


if __name__ == "__main__":
    main()
