#!/usr/bin/env python3
"""Finalize second-confirmation point, fallback, triage, and hash audits."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.analysis.advanced_validation import (
    evaluate_risk_control,
    risk_control_threshold,
)
from stream_recoverability.experiments.route_a_confirmation import (
    point_prediction_metrics,
)
from stream_recoverability.experiments.second_confirmation_guard import (
    sha256_file,
    validate_canonical_authorization,
    validate_scored_result_gate,
)

SECOND = ROOT / "results/development_v11/second_confirmation"
SCORING = SECOND / "scoring"
SUPPORTED_HORIZONS = (7, 30, 90, 180)


def _safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        numeric = float(value)
        return numeric if np.isfinite(numeric) else None
    return value


def _station_gap_empirical(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"network_id": str, "station_id": str})
    if "placement" not in frame:
        return frame
    return frame.groupby(
        ["network_id", "station_id", "gap_length"], as_index=False
    ).agg(
        empirical_transfer_prediction=("empirical_transfer_prediction", "mean"),
        observed_recovery_loss=("mae_deg_c", "mean"),
    )


def _triage_endpoint(
    calibration: pd.DataFrame,
    evaluation: pd.DataFrame,
    *,
    calibration_risk: str,
    evaluation_risk: str,
) -> dict[str, object]:
    rule = risk_control_threshold(calibration, risk_column=calibration_risk)
    result = evaluate_risk_control(evaluation, rule, risk_column=evaluation_risk)
    passed = bool(
        result["status"] == "certified"
        and result["n_released"] > 0
        and np.isfinite(float(result["false_release_rate"]))
        and float(result["false_release_rate"]) <= 0.05
    )
    return {**result, "endpoint_passed": passed}


def _heterogeneity(frame: pd.DataFrame, *, model: str, prediction: str) -> pd.DataFrame:
    rows = []
    for moderator in ("provider", "domain", "network_size_group"):
        for level, values in frame.groupby(moderator, dropna=False, observed=True):
            scoring = (
                values.rename(columns={prediction: "predicted_loss"})
                if prediction != "predicted_loss"
                else values
            )
            rows.append(
                {
                    "model": model,
                    "moderator": moderator,
                    "level": str(level),
                    **point_prediction_metrics(scoring),
                    "descriptive_only": True,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    summary_path = SCORING / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    validate_scored_result_gate(summary)
    readiness_path = SECOND / "readiness.json"
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    validate_canonical_authorization(
        readiness,
        readiness_path=readiness_path,
        canonical_readiness_path=readiness_path,
        root=ROOT,
    )
    simple = pd.read_csv(
        SCORING / "simple_predictions.csv", dtype={"network_id": str, "station_id": str}
    )
    empirical = pd.read_csv(
        SCORING / "empirical_predictions.csv",
        dtype={"network_id": str, "station_id": str},
    ).rename(columns={"empirical_transfer_prediction": "predicted_loss"})
    supported = empirical.loc[empirical["gap_length"].isin(SUPPORTED_HORIZONS)]
    fallback = empirical.loc[~empirical["gap_length"].isin(SUPPORTED_HORIZONS)]
    summary["empirical_point_metrics"] = point_prediction_metrics(empirical)
    summary["empirical_supported_horizon_metrics"] = point_prediction_metrics(supported)
    summary["empirical_prediction_source_audit"] = {
        "definition": (
            "The frozen fitting-period curve directly targets horizons "
            "7/30/90/180 days. Other horizons use the training-period network mean."
        ),
        "supported_horizons": list(SUPPORTED_HORIZONS),
        "supported_station_gaps": len(supported),
        "network_mean_fallback_station_gaps": len(fallback),
        "all_station_gaps": len(empirical),
        "all_predictions_finite": bool(empirical["predicted_loss"].notna().all()),
    }
    summary.pop("empirical_metrics", None)

    development_simple = pd.read_csv(
        ROOT / "results/development_v11/nested_lono_predictions.csv",
        dtype={"network_id": str, "station_id": str},
    )
    development_empirical = _station_gap_empirical(
        ROOT
        / "results/development_v11/reviewer_completion/development_empirical_predictions.csv"
    )
    triage = {
        "endpoint": {
            "unsafe_loss_c": 0.5,
            "false_release_cap": 0.05,
            "confidence": 0.95,
            "calibration": "development networks only",
            "evaluation": "57 second-confirmation networks",
        },
        "simple_descriptors": _triage_endpoint(
            development_simple,
            simple,
            calibration_risk="simple_prediction",
            evaluation_risk="predicted_loss",
        ),
        "fitting_period_empirical_all_cells": _triage_endpoint(
            development_empirical,
            empirical,
            calibration_risk="empirical_transfer_prediction",
            evaluation_risk="predicted_loss",
        ),
    }
    triage["endpoint_passed"] = bool(
        triage["simple_descriptors"]["endpoint_passed"]
        or triage["fitting_period_empirical_all_cells"]["endpoint_passed"]
    )
    summary["triage"] = triage
    (SCORING / "triage_endpoint.json").write_text(
        json.dumps(_safe(triage), indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    roster = pd.read_csv(
        SECOND / "frozen_scoring_roster_v2.csv", dtype={"network_id": str}
    )
    metadata = roster[["network_id", "provider", "domain"]]
    station_counts = simple.groupby("network_id")["station_id"].nunique()
    size_group = pd.cut(
        station_counts,
        bins=[0, 4, 7, np.inf],
        labels=["3_to_4", "5_to_7", "8_plus"],
    ).rename("network_size_group")
    metadata = metadata.merge(size_group, on="network_id", how="inner")
    simple_meta = simple.merge(metadata, on="network_id", validate="many_to_one")
    empirical_meta = empirical.merge(metadata, on="network_id", validate="many_to_one")
    heterogeneity = pd.concat(
        [
            _heterogeneity(
                simple_meta, model="simple_descriptors", prediction="predicted_loss"
            ),
            _heterogeneity(
                empirical_meta,
                model="fitting_period_empirical_all_cells",
                prediction="predicted_loss",
            ),
        ],
        ignore_index=True,
    )
    heterogeneity.to_csv(SCORING / "heterogeneity_metrics.csv", index=False)
    summary["heterogeneity"] = {
        "moderators": ["provider", "domain", "network_size_group"],
        "descriptive_only": True,
        "climate_and_regulation_status": "not_available_in_frozen_second_roster",
        "rows": heterogeneity.to_dict(orient="records"),
    }

    placement_summary_path = SCORING / "placement_summary.json"
    if placement_summary_path.is_file():
        placement = json.loads(placement_summary_path.read_text(encoding="utf-8"))
        placement.pop("endpoint_passed", None)
        random_regret = float(placement["random_mean_regret"])
        minimax_regret = float(placement["simple_minimax_mean_regret"])
        placement.update(
            {
                "simple_minimax_relative_regret_reduction_vs_random": (
                    (random_regret - minimax_regret) / random_regret
                ),
                "directional_improvement_observed": minimax_regret < random_regret,
                "preregistered_margin_or_significance_threshold": False,
                "confirmatory_utility_claim_licensed": False,
                "endpoint_status": "directionally_lower_regret_no_preregistered_margin",
            }
        )
        placement_summary_path.write_text(
            json.dumps(placement, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        summary["placement"] = placement

    registration = SECOND / "amendment_registration_record.json"
    bound = {
        "canonical_readiness": SECOND / "readiness.json",
        "authorization_amendment": ROOT
        / "configs/route_a_second_confirmation_amendment_v2.yaml",
        "frozen_scoring_roster": SECOND / "frozen_scoring_roster_v2.csv",
        "readiness_roster": SECOND / "readiness_roster.csv",
        "development_outcomes": ROOT
        / "results/development_v11/station_gap_outcomes.csv",
        "development_empirical_predictions": ROOT
        / "results/development_v11/reviewer_completion/development_empirical_predictions.csv",
        "registration_record_non_authorizing": registration,
        "simple_predictions": SCORING / "simple_predictions.csv",
        "empirical_predictions": SCORING / "empirical_predictions.csv",
        "empirical_intervals": SCORING / "empirical_intervals.csv",
        "scoring_attrition": SCORING / "scoring_attrition.csv",
        "triage_endpoint": SCORING / "triage_endpoint.json",
        "placement_summary": placement_summary_path,
        "placement_attrition": SCORING / "placement_attrition.csv",
        "placement_pairwise_losses": SCORING / "placement_pairwise_losses.csv",
        "placement_policy_summary": SCORING / "placement_policy_summary.csv",
        "placement_replay_curve": SCORING / "placement_replay_curve.csv",
        "heterogeneity_metrics": SCORING / "heterogeneity_metrics.csv",
    }
    summary["artifact_bindings"] = {
        key: {
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256_file(path),
        }
        for key, path in bound.items()
    }
    summary["large_regenerable_artifacts"] = {
        "placement_losses": {
            "path": "results/development_v11/second_confirmation/scoring/placement_losses.csv",
            "sha256": sha256_file(SCORING / "placement_losses.csv"),
            "packaged": False,
            "regenerable": True,
        },
    }
    summary["registration_boundary"] = json.loads(
        registration.read_text(encoding="utf-8")
    )
    strict = _safe(summary)
    summary_path.write_text(
        json.dumps(strict, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(_safe(summary), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
