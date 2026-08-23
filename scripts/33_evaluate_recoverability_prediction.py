#!/usr/bin/env python3
"""Compare the frozen train-only budget with the completed dense curves."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    prediction_path = ROOT / "results/predictions/recoverability_prediction_v1.json"
    curve_path = ROOT / "results/analysis/frontier_climatology_curves.csv"
    output = ROOT / "results/predictions/recoverability_prediction_evaluation_v1.csv"
    summary_path = output.with_suffix(".json")

    frozen = json.loads(prediction_path.read_text(encoding="utf-8"))
    prediction = pd.DataFrame(frozen["predictions"]).rename(
        columns={"station": "station_id", "gap_length_days": "gap_length"}
    )
    curves = pd.read_csv(curve_path)
    curves = curves.loc[curves["target"].astype(str).eq("T")].copy()
    donor = curves.loc[curves["model"].astype(str).eq("donor_regression")].rename(
        columns={
            "mean_skill": "donor_mean_skill",
            "ci_lower": "donor_ci_lower",
            "ci_upper": "donor_ci_upper",
        }
    )
    best = (
        curves.sort_values("mean_skill", ascending=False, kind="mergesort")
        .groupby(["station_id", "gap_length"], as_index=False, sort=True)
        .first()
        .rename(
            columns={
                "model": "best_model",
                "mean_skill": "best_mean_skill",
                "ci_lower": "best_ci_lower",
                "ci_upper": "best_ci_upper",
            }
        )
    )
    result = prediction.merge(
        donor[
            [
                "station_id",
                "gap_length",
                "donor_mean_skill",
                "donor_ci_lower",
                "donor_ci_upper",
            ]
        ],
        on=["station_id", "gap_length"],
        validate="one_to_one",
    ).merge(
        best[
            [
                "station_id",
                "gap_length",
                "best_model",
                "best_mean_skill",
                "best_ci_lower",
                "best_ci_upper",
            ]
        ],
        on=["station_id", "gap_length"],
        validate="one_to_one",
    )
    result["donor_prediction_error"] = (
        result["donor_mean_skill"] - result["predicted_skill"]
    )
    result["best_exceeds_prediction"] = (
        result["best_mean_skill"] > result["predicted_skill"]
    )
    result["best_ci_lower_exceeds_prediction"] = (
        result["best_ci_lower"] > result["predicted_skill"]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)

    stations = {}
    for station, group in result.groupby("station_id", sort=True):
        stations[str(station)] = {
            "best_envelope_prediction_mae": float(
                (group["best_mean_skill"] - group["predicted_skill"]).abs().mean()
            ),
            "best_envelope_prediction_rmse": float(
                np.sqrt(
                    np.square(
                        group["best_mean_skill"] - group["predicted_skill"]
                    ).mean()
                )
            ),
            "best_envelope_prediction_correlation": float(
                group["predicted_skill"].corr(group["best_mean_skill"])
            ),
            "donor_prediction_mae": float(
                group["donor_prediction_error"].abs().mean()
            ),
            "donor_prediction_rmse": float(
                np.sqrt(np.square(group["donor_prediction_error"]).mean())
            ),
            "donor_prediction_correlation": float(
                group["predicted_skill"].corr(group["donor_mean_skill"])
            ),
            "best_exceeds_prediction_count": int(
                group["best_exceeds_prediction"].sum()
            ),
            "best_ci_lower_exceeds_prediction_count": int(
                group["best_ci_lower_exceeds_prediction"].sum()
            ),
        }
    summary = {
        "schema_version": "recoverability_prediction_evaluation_v1",
        "prediction_status": frozen["status"],
        "dense_analysis_status": "complete",
        "comparison_cells": int(len(result)),
        "best_exceeds_prediction_count": int(result["best_exceeds_prediction"].sum()),
        "best_ci_lower_exceeds_prediction_count": int(
            result["best_ci_lower_exceeds_prediction"].sum()
        ),
        "analytic_information_ceiling_supported": False,
        "station_metrics": stations,
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
