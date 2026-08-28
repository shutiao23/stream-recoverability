#!/usr/bin/env python3
"""Run the fixed Route A model on the wholly-new qualified network panel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (
    GAP_LENGTHS,
    XGBOOST_PARAMETERS,
    read_temperature_panel,
    score_network,
)
from stream_recoverability.experiments.route_a_confirmation import (
    apply_route_a_model,
    confirmation_metrics,
    fit_route_a_model,
    grouped_confirmation_metrics,
    simple_predictors,
    thermal_state_changes,
)

SUMMARY = ROOT / "results/development_v11/confirmation_qc_summary.csv"
NETWORK_ROOT = ROOT / "results/development_v11/confirmation_daily_qc/networks"
DEVELOPMENT = ROOT / "results/development_v11/station_gap_outcomes.csv"
DEVELOPMENT_LONO = ROOT / "results/development_v11/nested_lono_predictions.csv"
OUTPUT = ROOT / "results/development_v11/route_a_confirmation"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=SUMMARY)
    parser.add_argument("--network-root", type=Path, default=NETWORK_ROOT)
    parser.add_argument("--placements", type=int, default=20)
    parser.add_argument("--n-jobs", type=int, default=4)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    qualified = pd.read_csv(args.summary).loc[
        lambda frame: frame["qc_status"].eq("qualified")
    ]
    model = fit_route_a_model(
        pd.read_csv(DEVELOPMENT),
        pd.read_csv(DEVELOPMENT_LONO),
    )
    placement_parts = []
    outcome_parts = []
    predictor_parts = []
    attrition = []
    state_parts = []
    parameters = {**XGBOOST_PARAMETERS, "n_jobs": args.n_jobs}
    for network in qualified["network_id"].astype(str):
        panel = read_temperature_panel(
            str(args.network_root / network / "daily_wide_temperature.csv")
        )
        scored = score_network(
            network,
            panel,
            None,
            gap_lengths=GAP_LENGTHS,
            placements_per_gap=args.placements,
            xgboost_parameters=parameters,
        )
        if scored["placement_losses"].empty:
            attrition.append(
                {
                    "network_id": network,
                    "reason": "no_scored_b_union_d_evaluation_gap",
                }
            )
            continue
        placement_parts.append(
            scored["placement_losses"].loc[
                lambda frame: frame["information_condition"].eq("B_union_D")
            ]
        )
        outcome_parts.append(
            scored["station_gap_summary"].loc[
                lambda frame: frame["information_condition"].eq("B_union_D")
            ]
        )
        state_parts.append(
            thermal_state_changes(
                network,
                panel,
                target_stations=tuple(
                    outcome_parts[-1]["station_id"].astype(str).unique()
                ),
            )
        )
        placement = placement_parts[-1]
        phase = 2.0 * np.pi * (
            pd.to_datetime(placement["gap_start"]).dt.dayofyear.to_numpy(dtype=float)
            - 1.0
        ) / np.where(
            pd.to_datetime(placement["gap_start"]).dt.is_leap_year,
            366.0,
            365.0,
        )
        placement = placement.assign(
            placement_season_sin=np.sin(phase),
            placement_season_cos=np.cos(phase),
        )
        season = placement.groupby(
            ["network_id", "station_id", "gap_length"], as_index=False
        )[["placement_season_sin", "placement_season_cos"]].mean()
        predictor_parts.append(
            simple_predictors(
                network,
                panel,
                gaps=GAP_LENGTHS,
                target_stations=tuple(outcome_parts[-1]["station_id"].astype(str).unique()),
            ).merge(
                season,
                on=["network_id", "station_id", "gap_length"],
            )
        )

    placements = pd.concat(placement_parts, ignore_index=True)
    outcomes = pd.concat(outcome_parts, ignore_index=True)
    predictors = pd.concat(predictor_parts, ignore_index=True)
    predictors = predictors.dropna(subset=list(model.columns))
    predictions = apply_route_a_model(model, predictors).merge(
        outcomes[
            ["network_id", "station_id", "gap_length", "observed_recovery_loss"]
        ],
        on=["network_id", "station_id", "gap_length"],
    )
    metrics = confirmation_metrics(predictions)
    provider = qualified[["network_id", "provider", "domain"]]
    predictions = predictions.merge(provider, on="network_id")
    predictions["domain_group"] = np.where(
        predictions["domain"].eq("united_states"), "united_states", "cross_domain"
    )
    states = pd.concat(state_parts, ignore_index=True)
    predictions = predictions.merge(states, on=["network_id", "station_id"])
    provider_metrics = grouped_confirmation_metrics(
        predictions, group_column="provider"
    )
    domain_metrics = grouped_confirmation_metrics(
        predictions, group_column="domain_group"
    )
    state_metrics = grouped_confirmation_metrics(
        predictions, group_column="thermal_state_shift"
    )
    result = {
        "route": "route_a_simple_outage_geometry_and_redundancy",
        "model_intercept": model.intercept,
        "model_columns": list(model.columns),
        "model_coefficients": list(model.coefficients),
        "interval_radius": model.interval_radius,
        "n_qc_networks": int(len(qualified)),
        "n_scoring_attrition_networks": len(attrition),
        **metrics,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    qualified.to_csv(args.output / "qualified_panel.csv", index=False)
    pd.DataFrame(attrition, columns=["network_id", "reason"]).to_csv(
        args.output / "scoring_attrition.csv", index=False
    )
    placements.to_csv(args.output / "placement_losses.csv", index=False)
    outcomes.to_csv(args.output / "station_gap_outcomes.csv", index=False)
    predictions.to_csv(args.output / "predictions.csv", index=False)
    states.to_csv(args.output / "thermal_state_changes.csv", index=False)
    provider_metrics.to_csv(args.output / "provider_metrics.csv", index=False)
    domain_metrics.to_csv(args.output / "domain_metrics.csv", index=False)
    state_metrics.to_csv(args.output / "thermal_state_metrics.csv", index=False)
    (args.output / "summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
