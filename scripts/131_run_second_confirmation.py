#!/usr/bin/env python3
"""Run confirmation two only after the executable readiness gate authorizes it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.analysis.advanced_validation import (
    interval_metrics,
    network_block_scaled_intervals,
)
from stream_recoverability.experiments.development_recovery import (
    GAP_LENGTHS,
    XGBOOST_PARAMETERS,
    read_temperature_panel,
    score_network,
)
from stream_recoverability.experiments.recovery_roster import (
    empirical_transfer_predictions,
    fitting_period_empirical_losses,
)
from stream_recoverability.experiments.route_a_confirmation import (
    apply_route_a_model,
    confirmation_metrics,
    fit_route_a_model,
    simple_predictors,
)

SECOND = ROOT / "results/development_v11/second_confirmation"
DEVELOPMENT = ROOT / "results/development_v11/station_gap_outcomes.csv"
DEVELOPMENT_LONO = ROOT / "results/development_v11/nested_lono_predictions.csv"
DEV_EMPIRICAL = ROOT / "results/development_v11/reviewer_completion/development_empirical_predictions.csv"


def panel_path(network_id: str) -> Path:
    second = SECOND / "daily_qc/networks" / network_id / "daily_wide_temperature.csv"
    if second.is_file():
        return second
    first = (
        ROOT
        / "results/development_v11/confirmation_daily_qc/networks"
        / network_id
        / "daily_wide_temperature.csv"
    )
    if first.is_file():
        return first
    raise FileNotFoundError(f"qualified network panel absent: {network_id}")


def _empirical_summary(losses: pd.DataFrame, placements: pd.DataFrame) -> pd.DataFrame:
    predicted = empirical_transfer_predictions(losses, placements)
    return (
        predicted.groupby(["network_id", "station_id", "gap_length"], as_index=False)
        .agg(
            empirical_transfer_prediction=("empirical_transfer_prediction", "mean"),
            observed_recovery_loss=("mae_deg_c", "mean"),
        )
        .dropna(subset=["empirical_transfer_prediction"])
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness", type=Path, default=SECOND / "readiness.json")
    parser.add_argument("--output", type=Path, default=SECOND / "scoring")
    parser.add_argument("--n-jobs", type=int, default=4)
    args = parser.parse_args()
    readiness = json.loads(args.readiness.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    if not readiness.get("scoring_authorized", False):
        result = {
            "status": "withheld_by_readiness_gate",
            "readiness": str(args.readiness),
            "blocking_domain_checks": {
                key: value
                for key, value in readiness["domain_checks"].items()
                if not value["passed"]
            },
            "temperature_panels_read": 0,
            "recovery_models_fit": 0,
            "outcomes_scored": 0,
        }
        (args.output / "withheld.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(result, indent=2))
        return

    roster = pd.read_csv(SECOND / "readiness_roster.csv", dtype={"network_id": str})
    qualified = roster.loc[roster["qc_status"].eq("qualified")].copy()
    route_a = fit_route_a_model(pd.read_csv(DEVELOPMENT), pd.read_csv(DEVELOPMENT_LONO))
    parameters = {**XGBOOST_PARAMETERS, "n_jobs": args.n_jobs}
    placement_parts = []
    outcome_parts = []
    predictor_parts = []
    empirical_parts = []
    for ordinal, network in enumerate(qualified["network_id"], start=1):
        panel = read_temperature_panel(str(panel_path(str(network))))
        scored = score_network(
            str(network),
            panel,
            None,
            gap_lengths=GAP_LENGTHS,
            placements_per_gap=20,
            xgboost_parameters=parameters,
        )
        placement = scored["placement_losses"].loc[
            lambda frame: frame["information_condition"].eq("B_union_D")
        ]
        outcome = scored["station_gap_summary"].loc[
            lambda frame: frame["information_condition"].eq("B_union_D")
        ]
        if placement.empty or outcome.empty:
            continue
        placement_parts.append(placement)
        outcome_parts.append(outcome)
        phase = 2.0 * np.pi * (
            pd.to_datetime(placement["gap_start"]).dt.dayofyear.to_numpy() - 1.0
        ) / np.where(pd.to_datetime(placement["gap_start"]).dt.is_leap_year, 366.0, 365.0)
        season = placement.assign(
            placement_season_sin=np.sin(phase),
            placement_season_cos=np.cos(phase),
        ).groupby(["network_id", "station_id", "gap_length"], as_index=False)[
            ["placement_season_sin", "placement_season_cos"]
        ].mean()
        predictor_parts.append(
            simple_predictors(
                str(network),
                panel,
                gaps=GAP_LENGTHS,
                target_stations=tuple(outcome["station_id"].astype(str).unique()),
            ).merge(season, on=["network_id", "station_id", "gap_length"])
        )
        empirical_parts.append(
            fitting_period_empirical_losses(
                str(network), panel, placement, xgboost_parameters=parameters
            )
        )
        print(f"second confirmation {ordinal}/{len(qualified)}: {network}", flush=True)

    placements = pd.concat(placement_parts, ignore_index=True)
    outcomes = pd.concat(outcome_parts, ignore_index=True)
    predictors = pd.concat(predictor_parts, ignore_index=True).dropna(
        subset=list(route_a.columns)
    )
    simple = apply_route_a_model(route_a, predictors).merge(
        outcomes[["network_id", "station_id", "gap_length", "observed_recovery_loss"]],
        on=["network_id", "station_id", "gap_length"],
    )
    empirical_losses = pd.concat(empirical_parts, ignore_index=True)
    empirical = _empirical_summary(empirical_losses, placements)
    development_empirical = _empirical_summary(
        pd.read_csv(
            ROOT / "results/development_v11/reviewer_completion/development_empirical_fit_losses.csv"
        ),
        pd.read_csv(
            ROOT / "results/development_v11/recovery_scoring/placement_losses.csv"
        ),
    )
    interval = network_block_scaled_intervals(
        development_empirical,
        empirical.rename(columns={"empirical_transfer_prediction": "predicted_loss"}),
        calibration_prediction="empirical_transfer_prediction",
        evaluation_prediction="predicted_loss",
    )
    result = {
        "status": "scored_after_readiness_authorization",
        "n_qc_networks": int(len(qualified)),
        "n_scored_networks": int(simple["network_id"].nunique()),
        "simple_metrics": confirmation_metrics(simple),
        "empirical_metrics": confirmation_metrics(
            empirical.rename(columns={"empirical_transfer_prediction": "predicted_loss"}).assign(
                prediction_lower=lambda frame: frame["predicted_loss"],
                prediction_upper=lambda frame: frame["predicted_loss"],
            )
        ),
        "empirical_interval_metrics": interval_metrics(interval),
    }
    placements.to_csv(args.output / "placement_losses.csv", index=False)
    simple.to_csv(args.output / "simple_predictions.csv", index=False)
    empirical.to_csv(args.output / "empirical_predictions.csv", index=False)
    interval.to_csv(args.output / "empirical_intervals.csv", index=False)
    (args.output / "summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
