#!/usr/bin/env python3
"""Run the open, iterative v11 development analysis."""

from __future__ import annotations

import argparse
import json
from itertools import combinations
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from stream_recoverability.analysis.development_calibration import (
    calibration_metrics,
    leave_one_network_out_calibration,
)
from stream_recoverability.experiments.development_data import (
    complete_operator_network_predictions,
    read_table,
)
from stream_recoverability.experiments.development_suite import (
    full_regret_curve,
    leave_one_network_out_nested_predictions,
    leave_one_network_out_predictions,
    lono_advancement_gate,
    lono_metrics,
    nested_lono_metrics,
    station_gap_metrics,
)
from stream_recoverability.experiments.synthetic_river import advection_chain


def _plot_calibration(predictions: pd.DataFrame, output: Path) -> None:
    figure, axis = plt.subplots(figsize=(6.4, 5.4))
    for network, group in predictions.groupby("network_id"):
        axis.scatter(
            group["calibrated_prediction"],
            group["observed_recovery_loss"],
            s=18,
            alpha=0.65,
            label=network,
        )
    low = min(
        predictions["calibrated_prediction"].min(),
        predictions["observed_recovery_loss"].min(),
    )
    high = max(
        predictions["calibrated_prediction"].max(),
        predictions["observed_recovery_loss"].max(),
    )
    axis.plot([low, high], [low, high], color="black", linewidth=1.2)
    axis.set(
        xlabel="LONO calibrated predicted loss (°C)",
        ylabel="Realized recovery loss (°C)",
        title="Open-development calibration",
    )
    axis.legend(fontsize=6, ncol=2, frameon=False)
    figure.tight_layout()
    figure.savefig(output, dpi=220)
    plt.close(figure)


def _plot_placements(raw: pd.DataFrame, output: Path) -> None:
    figure, axis = plt.subplots(figsize=(6.4, 5.4))
    axis.scatter(
        raw["primary_operator_risk"],
        raw["observed_recovery_loss"],
        s=8,
        alpha=0.18,
        color="#2962a3",
    )
    axis.set(
        xlabel="Train-only predicted conditional risk",
        ylabel="Placement-specific realized loss (°C)",
        title="All gap placements (no error-bar surrogate)",
    )
    figure.tight_layout()
    figure.savefig(output, dpi=220)
    plt.close(figure)


def _plot_regret(curve: pd.DataFrame, output: Path) -> None:
    selected = curve.loc[
        curve["policy"].isin(
            (
                "greedy_mutual_information",
                "proposed_recoverability",
                "correlation_redundancy",
                "distance",
                "random",
                "oracle",
            )
        )
    ]
    figure, axis = plt.subplots(figsize=(7.0, 5.2))
    for policy, group in selected.groupby("policy"):
        axis.plot(
            group["protected_fraction"],
            group["relative_regret"],
            marker="o",
            label=policy.replace("_", " "),
        )
    axis.axhline(0.0, color="black", linewidth=1.0)
    axis.set(
        xlabel="Protected fraction of stations",
        ylabel="Worst-case MAE regret relative to oracle",
        title="Synthetic full-budget placement regret",
    )
    axis.legend(fontsize=7, frameon=False)
    figure.tight_layout()
    figure.savefig(output, dpi=220)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "configs/development_v11.yaml"
    )
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    input_path = ROOT / config["input_results"]
    output = ROOT / config["output_dir"]
    output.mkdir(parents=True, exist_ok=True)

    raw = read_table(input_path)
    raw["network_id"] = raw["network_id"].astype(str)
    raw["station_id"] = raw["station_id"].astype(str).str.zfill(8)
    outcome_config = config["outcome"]
    primary_operator_risk = config["operator"]["primary_risk"]
    raw = raw.loc[
        raw["information_condition"].eq(
            outcome_config["information_condition"]
        )
    ].copy()
    placement_source = read_table(ROOT / config["input_placements"])
    placement_source["network_id"] = placement_source["network_id"].astype(str)
    placement_source["station_id"] = (
        placement_source["station_id"].astype(str).str.zfill(8)
    )
    placement_source = placement_source.loc[
        placement_source["model"].eq(outcome_config["model"])
        & placement_source["information_condition"].eq(
            outcome_config["information_condition"]
        )
    ].copy()
    station_gap = raw[
        [
            "network_id",
            "station_id",
            "gap_length",
            "observed_recovery_loss",
            "placement_loss_sd",
            "n_placements",
            "role",
        ]
    ].copy()
    gap_roster = tuple(sorted(station_gap["gap_length"].unique().astype(int)))
    complete_parts = []
    for network in sorted(station_gap["network_id"].unique()):
        role = str(
            station_gap.loc[station_gap["network_id"].eq(network), "role"].iloc[0]
        )
        temperature_path = (
            ROOT
            / config["temperature_root"]
            / role
            / "networks"
            / network
            / "daily_wide_qc.csv"
        )
        auxiliary_path = (
            ROOT
            / config["auxiliary_root"]
            / role
            / "networks"
            / network
            / "daily_long_auxiliary.parquet"
        )
        complete_parts.append(
            complete_operator_network_predictions(
                temperature_path,
                auxiliary_path,
                network_id=network,
                gaps=gap_roster,
                target_stations=tuple(
                    station_gap.loc[
                        station_gap["network_id"].eq(network), "station_id"
                    ].drop_duplicates()
                ),
            )
        )
    complete_operator = pd.concat(complete_parts, ignore_index=True)
    complete_operator.to_csv(output / "complete_operator_predictions.csv", index=False)
    roster_columns = [
        "donor_station_ids",
        "meteorology_feature_ids",
        "hydraulics_feature_ids",
    ]
    operator_roster = complete_operator.groupby(
        ["network_id", "station_id"], as_index=False
    )[[*roster_columns, "operator_training_years"]].first()
    recovery_roster = placement_source.groupby(
        ["network_id", "station_id"], as_index=False
    )[[*roster_columns, "training_years"]].first()
    roster_audit = operator_roster.merge(
        recovery_roster,
        on=["network_id", "station_id"],
        suffixes=("_operator", "_recovery"),
    )
    for column in roster_columns:
        roster_audit[f"{column}_match"] = roster_audit[
            f"{column}_operator"
        ].fillna("").eq(roster_audit[f"{column}_recovery"].fillna(""))
    roster_audit["training_years_match"] = roster_audit[
        "operator_training_years"
    ].eq(roster_audit["training_years"])
    match_columns = [
        *[f"{column}_match" for column in roster_columns],
        "training_years_match",
    ]
    roster_audit["all_rosters_match"] = roster_audit[match_columns].all(axis=1)
    roster_audit.to_csv(output / "operator_recovery_roster_audit.csv", index=False)
    station_gap = station_gap.rename(
        columns={"predicted_conditional_risk": "partial_operator_risk"}
    ).merge(
        complete_operator,
        on=["network_id", "station_id", "gap_length"],
    )
    station_gap["regime_weighted_operator_risk"] = station_gap[
        "predicted_conditional_risk"
    ]
    station_gap["predicted_conditional_risk"] = station_gap[
        config["operator"]["primary_risk_column"]
    ]
    baseline = pd.read_parquet(ROOT / config["predictor_sidecar"])[
        [
            "network_id",
            "station_id",
            "gap_length",
            "acf_only",
            "donor_r2_only",
            "additive_d_over_4_heuristic",
        ]
    ]
    station_gap = station_gap.merge(
        baseline,
        on=["network_id", "station_id", "gap_length"],
    )
    placement_source["gap_start"] = pd.to_datetime(placement_source["gap_start"])
    phase = 2.0 * np.pi * (
        placement_source["gap_start"].dt.dayofyear.to_numpy(dtype=float) - 1.0
    ) / np.where(placement_source["gap_start"].dt.is_leap_year, 366.0, 365.0)
    placement_source["placement_season_sin"] = np.sin(phase)
    placement_source["placement_season_cos"] = np.cos(phase)
    season = placement_source.groupby(
        ["network_id", "station_id", "gap_length"], as_index=False
    )[["placement_season_sin", "placement_season_cos"]].mean()
    station_gap = station_gap.merge(
        season,
        on=["network_id", "station_id", "gap_length"],
    )
    simple_base = (
        "gap_length",
        "acf_only",
        "donor_r2_only",
        "additive_d_over_4_heuristic",
    )
    simple_cols = (
        *simple_base,
        "nearest_donor_correlation",
        "placement_season_sin",
        "placement_season_cos",
    )
    candidate_models = []
    for size in range(1, len(simple_base) + 1):
        for subset in combinations(simple_base, size):
            candidate_models.extend(
                (
                    subset,
                    (*subset, "nearest_donor_correlation"),
                    (*subset, "placement_season_sin", "placement_season_cos"),
                    (
                        *subset,
                        "nearest_donor_correlation",
                        "placement_season_sin",
                        "placement_season_cos",
                    ),
                )
            )
    predictors = {
        "operator": primary_operator_risk,
        "donor_r2": "donor_r2_only",
        "gap_length": "gap_length",
    }

    marginal = station_gap_metrics(station_gap, predictors=predictors)
    lono_prediction = leave_one_network_out_predictions(
        station_gap, predictors=predictors
    )
    lono_summary = lono_metrics(lono_prediction)
    nested_prediction = leave_one_network_out_nested_predictions(
        station_gap,
        operator_col=primary_operator_risk,
        simple_cols=simple_cols,
        candidate_models=candidate_models,
        coverage=config["operator"]["prediction_interval"],
    )
    nested_summary = nested_lono_metrics(nested_prediction)
    simple_calibration = calibration_metrics(
        nested_prediction,
        calibrated_col="simple_prediction",
        lower_col="simple_prediction_lower",
        upper_col="simple_prediction_upper",
    )
    gate = lono_advancement_gate(
        lono_summary,
        spearman_gain_min=config["advancement_gate"]["incremental_spearman_min"],
        r2_gain_min=config["advancement_gate"]["station_gap_incremental_r2_min"],
        incremental_r2=nested_summary["operator_incremental_r2"],
    )
    calibration = leave_one_network_out_calibration(
        station_gap,
        predicted_col=primary_operator_risk,
        method=config["operator"]["calibration"],
        coverage=config["operator"]["prediction_interval"],
    )
    regret = full_regret_curve(
        advection_chain(n_stations=8),
        budgets=range(1, 8),
        gap_length=90,
        random_repeats=20,
    )

    station_gap.to_csv(output / "station_gap_outcomes.csv", index=False)
    marginal.to_csv(output / "station_gap_metrics.csv", index=False)
    lono_prediction.to_csv(output / "lono_predictions.csv", index=False)
    lono_summary.to_csv(output / "lono_metrics.csv", index=False)
    nested_prediction.to_csv(output / "nested_lono_predictions.csv", index=False)
    calibration.predictions.to_csv(output / "calibration_predictions.csv", index=False)
    calibration.folds.to_csv(output / "calibration_folds.csv", index=False)
    calibration.residuals.to_csv(output / "calibration_residuals.csv", index=False)
    regret.to_csv(output / "placement_regret_curve.csv", index=False)
    _plot_calibration(calibration.predictions, output / "calibration.png")
    placement_rows = placement_source.merge(
        station_gap[
            ["network_id", "station_id", "gap_length", primary_operator_risk]
        ],
        on=["network_id", "station_id", "gap_length"],
    )
    placement_rows = placement_rows.rename(
        columns={primary_operator_risk: "primary_operator_risk"}
    )
    _plot_placements(placement_rows, output / "placement_scatter.png")
    _plot_regret(regret, output / "placement_regret.png")

    summary = {
        "analysis_id": config["analysis_id"],
        "evidence_role": "open_development_pilot",
        "recovery_information_condition": outcome_config["information_condition"],
        "operator_information": [
            "boundary_memory",
            "donor",
            "meteorology",
            "hydraulics",
        ],
        "primary_operator_risk": primary_operator_risk,
        "regime_weighted_risk_role": "diagnostic_only",
        "complete_bdmh_operator_evaluated": True,
        "complete_bdmh_operator_predictor_computed": True,
        "matched_bdmh_recovery_outcome_evaluated": True,
        "operator_recovery_roster_audit": {
            "n_stations": len(roster_audit),
            "n_exact_matches": int(roster_audit["all_rosters_match"].sum()),
            "all_match": bool(roster_audit["all_rosters_match"].all()),
        },
        "n_networks": int(station_gap["network_id"].nunique()),
        "n_stations": int(
            station_gap[["network_id", "station_id"]].drop_duplicates().shape[0]
        ),
        "n_station_gaps": len(station_gap),
        "advancement_gate": gate,
        "nested_lono": nested_summary,
        "route_a_simple_calibration": simple_calibration,
        "placement_regret_role": "synthetic_implementation_benchmark",
        "calibration": calibration.summary,
        "route_decision": (
            "route_b_complete_operator"
            if gate["passed"]
            else "route_a_simple_outage_geometry_and_redundancy"
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
