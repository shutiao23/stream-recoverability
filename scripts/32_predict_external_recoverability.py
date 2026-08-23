#!/usr/bin/env python3
"""Predict Chattahoochee recoverability from the external training split only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.analysis.recoverability_budget import budget_decomposition

GAPS = (1, 3, 7, 10, 14, 21, 30, 45, 60, 90, 120, 150, 180, 240, 365)
DATA_VERSION = "external_upper_middle_chattahoochee_v1"


def main() -> None:
    train_path = PROJECT_ROOT / "data_versions" / DATA_VERSION / "splits/train.parquet"
    train = pd.read_parquet(train_path)
    if set(train["split"].astype(str)) != {"train"}:
        raise ValueError("external prediction input must contain the train split only")
    stations = tuple(column[:-2] for column in train if column.endswith("_T"))
    predictions = pd.concat(
        [
            budget_decomposition(
                train,
                station,
                tuple(value for value in stations if value != station),
                GAPS,
            )
            for station in stations
        ],
        ignore_index=True,
    )
    at_30 = predictions.loc[predictions["gap_length_days"].eq(30)]
    station_types = {
        str(row.station): (
            "donor_dominated"
            if float(row.donor_component) >= float(row.memory_component)
            else "memory_dominated"
        )
        for row in at_30.itertuples(index=False)
    }
    payload = {
        "schema_version": "external_recoverability_prediction_v1",
        "evidence_role": "external_train_only_prediction",
        "performance_metrics_computed": False,
        "confirmatory_period_read": False,
        "data_version": DATA_VERSION,
        "fit_split": "train",
        "fit_period": {"start": "2012-01-01", "end": "2020-12-31"},
        "station_types": station_types,
        "predictions": predictions.to_dict(orient="records"),
    }
    output = (
        PROJECT_ROOT
        / "results/predictions/chattahoochee_recoverability_prediction_v1.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(output)


if __name__ == "__main__":
    main()
