#!/usr/bin/env python3
"""Run v11 predictors on frozen truth-bearing natural-geometry counterparts."""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (
    read_temperature_panel,
)
from stream_recoverability.experiments.development_suite import (
    leave_one_network_out_nested_predictions,
)
from stream_recoverability.experiments.matched_outage_geometry import (
    linear_prediction,
    nearest_artificial_horizon,
    network_bootstrap_spearman,
    network_equal_coefficients,
    paired_bootstrap_delta,
    validate_natural_xgboost_rows,
)
from stream_recoverability.experiments.recovery_roster import (
    empirical_transfer_predictions,
)
from stream_recoverability.experiments.route_a_confirmation import (
    point_prediction_metrics,
    simple_predictors,
)
from stream_recoverability.experiments.second_confirmation_guard import sha256_file

CORPUS = ROOT / "data_versions/global_network_corpus_v1/open_role_qc/failure_closure6"
NATURAL_CATALOG = ROOT / "results/framework/t2_outage_geometry_v1/natural_outage_catalog.csv"
T2_RESULTS = ROOT / "results/framework/t2_recovery_benchmark_v4/aggregation_v3/item_results.parquet"
BD_OUTCOMES = ROOT / "results/development_v11/recovery_scoring/station_gap_summary.csv"
BD_PLACEMENTS = ROOT / "results/development_v11/recovery_scoring/placement_losses.csv"
EMPIRICAL_LOSSES = ROOT / "results/development_v11/reviewer_completion/development_empirical_fit_losses.csv"
EMPIRICAL_PREDICTIONS = ROOT / "results/development_v11/reviewer_completion/development_empirical_predictions.csv"
OUTPUT = ROOT / "results/development_v11/matched_outage_geometry"


def _station(value: object) -> str:
    return str(value).strip().removesuffix(".0")


def _season_coordinates(dates: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    index = pd.DatetimeIndex(pd.to_datetime(dates))
    phase = 2.0 * np.pi * (index.dayofyear.to_numpy() - 1.0) / np.where(
        index.is_leap_year, 366.0, 365.0
    )
    return np.sin(phase), np.cos(phase)


def _candidate_models() -> list[tuple[str, ...]]:
    base = (
        "gap_length",
        "acf_only",
        "donor_r2_only",
        "additive_d_over_4_heuristic",
    )
    result = []
    for size in range(1, len(base) + 1):
        for subset in combinations(base, size):
            result.extend(
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
    return result


def _natural_results() -> pd.DataFrame:
    columns = [
        "network_id",
        "role",
        "target_station",
        "model",
        "gap_length",
        "placement",
        "information_condition",
        "geometry",
        "geometry_id",
        "truth_start_date",
        "observed_missing_start_date",
        "status",
        "implementation",
        "runner_contract_version",
        "mae_deg_c",
    ]
    results = pd.read_parquet(T2_RESULTS, columns=columns)
    catalog = pd.read_csv(
        NATURAL_CATALOG,
        dtype={"network_id": str, "station_id": str, "geometry_id": str},
    )[
        [
            "geometry_id",
            "actual_missing_truth_available",
            "benchmark_truth_source",
            "benchmark_eligible",
        ]
    ]
    merged = results.merge(catalog, on="geometry_id", validate="many_to_one")
    return validate_natural_xgboost_rows(merged)


def _panel(role: str, network: str) -> pd.DataFrame:
    return read_temperature_panel(
        str(CORPUS / role / "networks" / network / "daily_wide_qc.csv")
    )


def _predictor_tables(
    natural: pd.DataFrame, artificial: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    parts = []
    failures = []
    for (role, network), grid in artificial.groupby(["role", "network_id"]):
        panel = _panel(str(role), str(network))
        panel.columns = panel.columns.astype(str)
        grid_stations = {_station(value) for value in grid["station_id"]}
        natural_network = natural.loc[natural["network_id"].eq(network)]
        natural_stations = {_station(value) for value in natural_network["station_id"]}
        targets = tuple(
            station for station in panel.columns if station in grid_stations | natural_stations
        )
        gaps = tuple(
            sorted(
                set(grid["gap_length"].astype(int))
                | set(natural_network["gap_length"].astype(int))
            )
        )
        for target in targets:
            try:
                predictors = simple_predictors(
                    str(network), panel, gaps=gaps, target_stations=(target,)
                )
            except (KeyError, ValueError) as error:
                failures.append(
                    {
                        "network_id": str(network),
                        "station_id": str(target),
                        "reason": str(error),
                    }
                )
                continue
            predictors["station_id"] = predictors["station_id"].astype(str)
            parts.append(predictors)
    static = pd.concat(parts, ignore_index=True)
    keys = ["network_id", "station_id", "gap_length"]
    artificial_predictors = artificial.merge(
        static, on=keys, validate="one_to_one", how="inner"
    )
    natural_predictors = natural.merge(
        static, on=keys, validate="many_to_one", how="inner"
    )
    return natural_predictors, artificial_predictors, pd.DataFrame(failures)


def _apply_nested_simple(
    natural: pd.DataFrame, artificial: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    simple_columns = (
        "gap_length",
        "acf_only",
        "donor_r2_only",
        "additive_d_over_4_heuristic",
        "nearest_donor_correlation",
        "placement_season_sin",
        "placement_season_cos",
    )
    artificial = artificial.assign(complete_operator_risk=0.0)
    nested = leave_one_network_out_nested_predictions(
        artificial,
        operator_col="complete_operator_risk",
        simple_cols=simple_columns,
        outcome="observed_recovery_loss",
        candidate_models=_candidate_models(),
    )
    natural_parts = []
    for network, evaluation in natural.groupby("network_id", sort=True):
        selected = str(
            nested.loc[nested["network_id"].eq(network), "selected_simple_model"].iloc[
                0
            ]
        ).split("|")
        training = artificial.loc[~artificial["network_id"].eq(network)]
        coefficients = network_equal_coefficients(
            training, selected, "observed_recovery_loss"
        )
        result = evaluation.copy()
        result["simple_prediction"] = linear_prediction(
            result, selected, coefficients
        )
        result["selected_simple_model"] = "|".join(selected)
        natural_parts.append(result)
    return pd.concat(natural_parts, ignore_index=True), nested


def _artificial_empirical() -> pd.DataFrame:
    frame = pd.read_csv(
        EMPIRICAL_PREDICTIONS, dtype={"network_id": str, "station_id": str}
    )
    frame["station_id"] = frame["station_id"].map(_station)
    return frame.groupby(
        ["network_id", "station_id", "gap_length"], as_index=False
    ).agg(
        empirical_prediction=("empirical_transfer_prediction", "mean"),
        empirical_supported=("empirical_transfer_supported", "all"),
        observed_recovery_loss=("mae_deg_c", "mean"),
    )


def _paired_table(
    natural: pd.DataFrame,
    artificial_simple: pd.DataFrame,
    artificial_empirical: pd.DataFrame,
) -> pd.DataFrame:
    keys = ["network_id", "station_id"]
    pairs = natural.copy()
    pairs["matched_artificial_gap_length"] = pairs["gap_length"].map(
        nearest_artificial_horizon
    )
    artificial = artificial_simple[
        [*keys, "gap_length", "simple_prediction", "observed_recovery_loss"]
    ].merge(
        artificial_empirical[
            [*keys, "gap_length", "empirical_prediction", "empirical_supported"]
        ],
        on=[*keys, "gap_length"],
        validate="one_to_one",
    )
    artificial = artificial.rename(
        columns={
            "gap_length": "matched_artificial_gap_length",
            "simple_prediction": "artificial_simple_prediction",
            "empirical_prediction": "artificial_empirical_prediction",
            "empirical_supported": "artificial_empirical_supported",
            "observed_recovery_loss": "artificial_observed_loss",
        }
    )
    pairs = pairs.merge(
        artificial,
        on=[*keys, "matched_artificial_gap_length"],
        validate="many_to_one",
    )
    pairs = pairs.rename(
        columns={
            "gap_length": "natural_gap_length",
            "observed_recovery_loss": "natural_observed_loss",
            "simple_prediction": "natural_simple_prediction",
            "empirical_prediction": "natural_empirical_prediction",
            "empirical_supported": "natural_empirical_supported",
            "empirical_source": "natural_empirical_source",
        }
    )
    pairs["gap_length_ratio"] = (
        pairs["natural_gap_length"] / pairs["matched_artificial_gap_length"]
    )
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--bootstrap-repeats", type=int, default=2000)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    natural = _natural_results().rename(
        columns={"target_station": "station_id", "mae_deg_c": "observed_recovery_loss"}
    )
    natural["network_id"] = natural["network_id"].astype(str)
    natural["station_id"] = natural["station_id"].map(_station)
    empirical_losses = pd.read_csv(
        EMPIRICAL_LOSSES, dtype={"network_id": str, "station_id": str}
    )
    empirical_losses["station_id"] = empirical_losses["station_id"].map(_station)
    supported_pairs = empirical_losses[["network_id", "station_id"]].drop_duplicates()
    natural = natural.merge(
        supported_pairs, on=["network_id", "station_id"], validate="many_to_one"
    )
    natural["gap_start"] = pd.to_datetime(natural["truth_start_date"])
    natural["information_condition"] = "B_union_D"
    natural["placement"] = 0

    empirical_natural = empirical_transfer_predictions(empirical_losses, natural)
    empirical_natural = empirical_natural.rename(
        columns={
            "empirical_transfer_prediction": "empirical_prediction",
            "empirical_transfer_source": "empirical_source",
            "empirical_transfer_supported": "empirical_supported",
        }
    )
    natural_sin, natural_cos = _season_coordinates(empirical_natural["gap_start"])
    empirical_natural["placement_season_sin"] = natural_sin
    empirical_natural["placement_season_cos"] = natural_cos

    artificial = pd.read_csv(
        BD_OUTCOMES, dtype={"network_id": str, "station_id": str}
    ).loc[lambda frame: frame["information_condition"].eq("B_union_D")]
    artificial["station_id"] = artificial["station_id"].map(_station)
    placement = pd.read_csv(
        BD_PLACEMENTS, dtype={"network_id": str, "station_id": str}
    ).loc[lambda frame: frame["information_condition"].eq("B_union_D")]
    placement["station_id"] = placement["station_id"].map(_station)
    season_sin, season_cos = _season_coordinates(placement["gap_start"])
    placement["placement_season_sin"] = season_sin
    placement["placement_season_cos"] = season_cos
    season = placement.groupby(
        ["network_id", "station_id", "gap_length"], as_index=False
    )[["placement_season_sin", "placement_season_cos"]].mean()
    artificial = artificial.merge(
        season,
        on=["network_id", "station_id", "gap_length"],
        validate="one_to_one",
    )
    matched_networks = set(empirical_natural["network_id"])
    artificial = artificial.loc[artificial["network_id"].isin(matched_networks)]

    natural_predictors, artificial_predictors, predictor_failures = _predictor_tables(
        empirical_natural, artificial
    )
    predictor_failures.to_csv(args.output / "simple_predictor_attrition.csv", index=False)
    natural_predicted, artificial_nested = _apply_nested_simple(
        natural_predictors, artificial_predictors
    )
    artificial_empirical = _artificial_empirical().loc[
        lambda frame: frame["network_id"].isin(matched_networks)
    ]
    paired = _paired_table(
        natural_predicted, artificial_nested, artificial_empirical
    )

    paired_columns = [
        "geometry_id",
        "network_id",
        "station_id",
        "role",
        "observed_missing_start_date",
        "truth_start_date",
        "natural_gap_length",
        "matched_artificial_gap_length",
        "gap_length_ratio",
        "natural_observed_loss",
        "artificial_observed_loss",
        "natural_simple_prediction",
        "artificial_simple_prediction",
        "natural_empirical_prediction",
        "artificial_empirical_prediction",
        "natural_empirical_source",
        "natural_empirical_supported",
        "artificial_empirical_supported",
        "selected_simple_model",
    ]
    paired = paired[paired_columns]
    paired.to_csv(args.output / "matched_item_predictions.csv", index=False)

    network_parts = []
    for geometry in ("natural", "artificial"):
        network = paired.groupby("network_id", as_index=False).agg(
            n_matched_items=("geometry_id", "size"),
            observed_loss=(f"{geometry}_observed_loss", "mean"),
            simple_prediction=(f"{geometry}_simple_prediction", "mean"),
            empirical_prediction=(f"{geometry}_empirical_prediction", "mean"),
            empirical_supported_fraction=(
                f"{geometry}_empirical_supported",
                "mean",
            ),
        )
        network.insert(0, "geometry", geometry)
        network_parts.append(network)
    network_table = pd.concat(network_parts, ignore_index=True)
    network_table.to_csv(args.output / "matched_network_comparison.csv", index=False)

    source_audit = (
        paired.groupby("natural_empirical_source", as_index=False)
        .agg(
            n_items=("geometry_id", "size"),
            n_networks=("network_id", "nunique"),
        )
        .rename(columns={"natural_empirical_source": "prediction_source"})
    )
    source_audit["fraction"] = source_audit["n_items"] / len(paired)
    source_audit.to_csv(args.output / "empirical_source_audit.csv", index=False)

    metrics = {}
    for geometry in ("natural", "artificial"):
        evaluation = paired.rename(
            columns={
                f"{geometry}_observed_loss": "observed_recovery_loss",
                f"{geometry}_simple_prediction": "simple",
                f"{geometry}_empirical_prediction": "empirical",
            }
        )
        for model in ("simple", "empirical"):
            point = point_prediction_metrics(
                evaluation.rename(columns={model: "predicted_loss"})
            )
            point["network_bootstrap"] = network_bootstrap_spearman(
                evaluation,
                model,
                "observed_recovery_loss",
                repeats=args.bootstrap_repeats,
            )
            metrics[f"{geometry}_{model}"] = point

    consistency = {}
    for value in ("observed_loss", "simple_prediction", "empirical_prediction"):
        network = paired.groupby("network_id")[[f"natural_{value}", f"artificial_{value}"]].mean()
        consistency[f"natural_vs_artificial_{value}_network_spearman"] = float(
            network.corr(method="spearman").iloc[0, 1]
        )
    consistency["simple_rank_delta"] = paired_bootstrap_delta(
        paired, "simple_prediction", repeats=args.bootstrap_repeats
    )
    consistency["empirical_rank_delta"] = paired_bootstrap_delta(
        paired, "empirical_prediction", repeats=args.bootstrap_repeats
    )

    summary = {
        "analysis_id": "v11_matched_planted_outage_geometry_v1",
        "status": "complete_matched_planted_geometry",
        "actual_missing_days_scored": False,
        "truth_source": "held_out_observed_counterpart",
        "natural_geometry_catalog_rows": 2355,
        "complete_natural_xgboost_bd_rows": 2344,
        "empirical_curve_matched_before_simple_attrition": len(empirical_natural),
        "v11_empirical_curve_matched_rows": len(paired),
        "simple_predictor_attrition_stations": len(predictor_failures),
        "n_networks": int(paired["network_id"].nunique()),
        "n_stations": int(paired[["network_id", "station_id"]].drop_duplicates().shape[0]),
        "recovery_model": "xgboost_B_union_D_300_trees_depth4_lr0.05",
        "outer_fit_rule": "first_70_percent_calendar_years_fit_last_30_percent_truth",
        "artificial_match_rule": "same network and station; nearest log-gap grid horizon; ties shorter",
        "natural_empirical_source_audit": source_audit.to_dict(orient="records"),
        "metrics": metrics,
        "consistency": consistency,
        "input_bindings": {
            str(path.relative_to(ROOT)): sha256_file(path)
            for path in (
                NATURAL_CATALOG,
                T2_RESULTS,
                BD_OUTCOMES,
                BD_PLACEMENTS,
                EMPIRICAL_LOSSES,
                EMPIRICAL_PREDICTIONS,
            )
        },
        "output_bindings": {
            name: sha256_file(args.output / name)
            for name in (
                "matched_item_predictions.csv",
                "matched_network_comparison.csv",
                "empirical_source_audit.csv",
                "simple_predictor_attrition.csv",
            )
        },
        "boundaries": [
            "actual_missing_days_have_no_truth",
            "counterpart_results_do_not_estimate_failure_process_selection_bias",
            "artificial comparator reuses station-gap mean for repeated natural geometries",
            "result applies only to networks with fitting-period empirical curves",
        ],
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
