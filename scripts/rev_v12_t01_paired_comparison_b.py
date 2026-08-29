#!/usr/bin/env python3
"""Agent B (adversarial pair): same-unit paired baseline comparison for the
second confirmation panel (57 networks, outcome-disjoint from fitting).

Deliverables:
  T1. Reproduce headline second-panel numbers (874 direct-horizon, 1446 all).
  T2. Fitting-period-only simple-descriptor predictor for second-panel units
      (features recomputed from daily QC panels via route_a_confirmation.
      simple_predictors, i.e. the exact code path behind scripts 115/124/131;
      coefficients refit with equal-network weighted OLS on development
      (55 networks) + first confirmation panel (42 networks) only).
  T3. Same-unit paired metrics: empirical vs simple, per method station-gap and
      network Spearman, equal-network calibration slope/intercept, R2, RMSE;
      paired DeltaRho with 2000-draw network bootstrap 95% CI; fraction of
      networks where empirical beats simple; provider-block sensitivity.
  T4. Per-horizon (7/30/90/180) network-level Spearman, both methods.
  T5. Within-network decomposition of the empirical predictor (per-network
      Spearman distribution, residualized Spearman after removing network
      means, network-mean-only predictor comparison).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import r2_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.route_a_confirmation import simple_predictors

OUTPUT = ROOT / "results/revision_v12/t01_paired_comparison/agent_b"
SECOND = ROOT / "results/development_v11/second_confirmation"
SCORING = SECOND / "scoring"
FIT_COLUMNS = [
    "gap_length",
    "acf_only",
    "donor_r2_only",
    "additive_d_over_4_heuristic",
    "nearest_donor_correlation",
]
SUPPORTED_HORIZONS = (7, 30, 90, 180)
BOOTSTRAP_REPEATS = 2000
BOOTSTRAP_SEED = 20260828

DEV_OUTCOMES = ROOT / "results/development_v11/station_gap_outcomes.csv"
FIRST_PANEL = ROOT / "results/development_v11/route_a_confirmation/predictions.csv"
LONO = ROOT / "results/development_v11/nested_lono_predictions.csv"
ROSTER = SECOND / "frozen_scoring_roster_v2.csv"


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"network_id": str, "station_id": str})


def panel_path(network_id: str) -> Path:
    """Replicates script 131 `panel_path`: second-panel QC first, then the
    first-panel confirmation QC fallback (used by the 15 chmi_* networks)."""
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


def metrics(frame: pd.DataFrame, prediction: str, outcome: str = "observed_recovery_loss") -> dict:
    """Equal-network-weighted OLS calibration + rank metrics, matching
    script 124 `_prediction_metrics` / `point_prediction_metrics`."""
    usable = frame[["network_id", prediction, outcome]].dropna()
    network = usable.groupby("network_id")[[prediction, outcome]].mean()
    counts = usable.groupby("network_id")["network_id"].transform("size")
    root_weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    design = np.column_stack([np.ones(len(usable)), usable[prediction].to_numpy(dtype=float)])
    intercept, slope = np.linalg.lstsq(
        design * root_weight[:, None],
        usable[outcome].to_numpy(dtype=float) * root_weight,
        rcond=None,
    )[0]
    return {
        "n": int(len(usable)),
        "n_networks": int(network.shape[0]),
        "station_gap_spearman": float(spearmanr(usable[prediction], usable[outcome]).statistic),
        "network_spearman": float(
            spearmanr(network[prediction], network[outcome]).statistic
        ),
        "calibration_intercept": float(intercept),
        "calibration_slope": float(slope),
        "r2": float(r2_score(usable[outcome], usable[prediction])),
        "rmse": float(
            np.sqrt(np.mean(np.square(usable[outcome].to_numpy(dtype=float) - usable[prediction].to_numpy(dtype=float))))
        ),
    }


def fit_coefficients(fitting: pd.DataFrame, columns: list[str], outcome: str = "observed_recovery_loss") -> dict:
    """Equal-network weighted OLS (weights 1/count per network), matching
    `fit_route_a_model` / script 124 `_weighted_fit`."""
    usable = fitting[["network_id", *columns, outcome]].dropna()
    counts = usable.groupby("network_id")["network_id"].transform("size")
    root_weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    design = np.column_stack([np.ones(len(usable)), usable[columns].to_numpy(dtype=float)])
    coefficients = np.linalg.lstsq(
        design * root_weight[:, None],
        usable[outcome].to_numpy(dtype=float) * root_weight,
        rcond=None,
    )[0]
    return {
        "intercept": float(coefficients[0]),
        "coefficients": [float(value) for value in coefficients[1:]],
        "columns": columns,
        "n": int(len(usable)),
        "n_networks": int(usable["network_id"].nunique()),
    }


def apply_model(frame: pd.DataFrame, fit: dict, prediction_name: str) -> pd.DataFrame:
    result = frame.copy()
    result[prediction_name] = fit["intercept"] + frame[fit["columns"]].to_numpy(
        dtype=float
    ) @ np.asarray(fit["coefficients"])
    return result


def paired_network_bootstrap(
    frame: pd.DataFrame,
    *,
    repeats: int,
    seed: int,
) -> pd.DataFrame:
    """2000-draw network bootstrap of both methods on identical draws.

    Each draw resamples networks with replacement; within a draw both methods
    are scored on the exact same unit set, so DeltaRho is paired.
    """
    rng = np.random.default_rng(seed)
    networks = np.asarray(sorted(frame["network_id"].unique()))
    rows = []
    for _ in range(repeats):
        sampled = rng.choice(networks, size=len(networks), replace=True)
        parts = []
        for draw, network in enumerate(sampled):
            part = frame.loc[frame["network_id"].eq(network)].copy()
            part["network_id"] = f"draw_{draw}"
            parts.append(part)
        draw_frame = pd.concat(parts, ignore_index=True)
        row = {"draw": len(rows)}
        for method, column in (("empirical", "empirical_transfer_prediction"), ("simple", "simple_prediction_fitperiod")):
            result = metrics(draw_frame, column)
            row[f"rho_station_{method}"] = result["station_gap_spearman"]
            row[f"rho_network_{method}"] = result["network_spearman"]
        row["delta_rho_station"] = row["rho_station_empirical"] - row["rho_station_simple"]
        row["delta_rho_network"] = row["rho_network_empirical"] - row["rho_network_simple"]
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_ci(deltas: np.ndarray) -> dict:
    return {
        "lower_95": float(np.quantile(deltas, 0.025)),
        "median": float(np.quantile(deltas, 0.5)),
        "upper_95": float(np.quantile(deltas, 0.975)),
        "fraction_positive": float(np.mean(deltas > 0.0)),
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    empirical = read_csv(SCORING / "empirical_predictions.csv")
    stored_simple = read_csv(SCORING / "simple_predictions.csv")
    roster = pd.read_csv(ROSTER, dtype={"network_id": str})
    dev = read_csv(DEV_OUTCOMES)
    first = read_csv(FIRST_PANEL)
    lono = read_csv(LONO)

    for frame in (empirical, stored_simple):
        frame["gap_length"] = frame["gap_length"].astype(int)
    empirical = empirical.sort_values(["network_id", "station_id", "gap_length"]).reset_index(drop=True)
    empirical["direct_horizon"] = empirical["gap_length"].isin(SUPPORTED_HORIZONS)

    # ------------------------------------------------------------------ T1
    # Reproduce second-panel headline numbers and add R2/RMSE.
    reproduction = []
    for subset_name, mask in (("direct_874", empirical["direct_horizon"]), ("all_1446", pd.Series(True, index=empirical.index))):
        reproduction.append(
            {"subset": subset_name, "method": "empirical_transfer",
             **metrics(empirical.loc[mask], "empirical_transfer_prediction")}
        )
    reproduction_df = pd.DataFrame(reproduction)
    stored_summary = json.loads((SCORING / "summary.json").read_text(encoding="utf-8"))
    expected = {
        "direct_874": stored_summary["empirical_supported_horizon_metrics"],
        "all_1446": stored_summary["empirical_point_metrics"],
    }
    reproduction_df["stored_station_gap_spearman"] = [
        expected[row["subset"]]["station_gap_spearman"] for _, row in reproduction_df.iterrows()
    ]
    reproduction_df["stored_network_spearman"] = [
        expected[row["subset"]]["network_spearman"] for _, row in reproduction_df.iterrows()
    ]
    reproduction_df["stored_calibration_slope"] = [
        expected[row["subset"]]["calibration_slope"] for _, row in reproduction_df.iterrows()
    ]
    reproduction_df.to_csv(OUTPUT / "t1_headline_reproduction.csv", index=False)

    # Cross-check: our metrics function on the stored route-A simple table.
    stored_metrics = {
        "direct_874": metrics(stored_simple.loc[stored_simple["gap_length"].isin(SUPPORTED_HORIZONS)], "predicted_loss"),
        "all_1446": metrics(stored_simple, "predicted_loss"),
    }
    crosscheck = pd.DataFrame(
        [{"subset": key, "method": "stored_route_a_simple", **value} for key, value in stored_metrics.items()]
    )
    crosscheck.to_csv(OUTPUT / "crosscheck_stored_route_a_simple.csv", index=False)

    # ------------------------------------------------------------------ T2
    # Fitting-period-only simple-descriptor predictor.
    # Column set = LONO-selected simple model (same as fit_route_a_model).
    selected_columns = tuple(lono["selected_simple_model"].mode().iloc[0].split("|"))
    assert list(selected_columns) == FIT_COLUMNS, selected_columns

    fit_dev_only = fit_coefficients(dev, FIT_COLUMNS)
    fitting = pd.concat([dev[["network_id", *FIT_COLUMNS, "observed_recovery_loss"]],
                         first[["network_id", *FIT_COLUMNS, "observed_recovery_loss"]]], ignore_index=True)
    fit_period = fit_coefficients(fitting, FIT_COLUMNS)

    # Validation: dev-only coefficients must reproduce the route-A model that
    # scripts 115/131 fit (results/development_v11/route_a_confirmation/summary.json).
    route_a = json.loads((ROOT / "results/development_v11/route_a_confirmation/summary.json").read_text(encoding="utf-8"))
    validation = {
        "our_dev_only_intercept": fit_dev_only["intercept"],
        "stored_route_a_intercept": route_a["model_intercept"],
        "our_dev_only_coefficients": fit_dev_only["coefficients"],
        "stored_route_a_coefficients": route_a["model_coefficients"],
        "intercept_abs_diff": abs(fit_dev_only["intercept"] - route_a["model_intercept"]),
        "coefficient_max_abs_diff": float(np.max(np.abs(
            np.asarray(fit_dev_only["coefficients"]) - np.asarray(route_a["model_coefficients"])
        ))),
    }
    (OUTPUT / "t2_fit_validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    (OUTPUT / "t2_coefficients.json").write_text(
        json.dumps({
            "columns": FIT_COLUMNS,
            "dev_only": fit_dev_only,
            "fitting_period_dev_plus_first": fit_period,
            "fitting_sources": {
                "development": {"n": int(len(dev)), "n_networks": int(dev["network_id"].nunique()), "path": str(DEV_OUTCOMES.relative_to(ROOT))},
                "first_confirmation": {"n": int(len(first)), "n_networks": int(first["network_id"].nunique()), "path": str(FIRST_PANEL.relative_to(ROOT))},
            },
        }, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )

    # Recompute descriptor features for second-panel stations from daily QC
    # panels (exact code path of scripts 115/124/131: simple_predictors on the
    # training-year split, donor R2 via year-block LOO, d/4 heuristic, etc.).
    feature_parts = []
    panel_origin = {}
    for ordinal, network in enumerate(sorted(empirical["network_id"].unique()), start=1):
        panel = read_temperature_panel(str(panel_path(network)))
        panel_origin[network] = "second_confirmation_daily_qc" if (
            SECOND / "daily_qc/networks" / network / "daily_wide_temperature.csv"
        ).is_file() else "confirmation_daily_qc_fallback"
        sub = empirical.loc[empirical["network_id"].eq(network)]
        feature_parts.append(
            simple_predictors(
                str(network),
                panel,
                gaps=tuple(sorted(int(value) for value in sub["gap_length"].unique())),
                target_stations=tuple(sub["station_id"].astype(str).unique()),
            )
        )
        print(f"features {ordinal}/57: {network} ({panel_origin[network]})", flush=True)
    features = pd.concat(feature_parts, ignore_index=True)
    features["gap_length"] = features["gap_length"].astype(int)

    observed = empirical[["network_id", "station_id", "gap_length", "empirical_transfer_prediction", "observed_recovery_loss"]]
    second = features.merge(observed, on=["network_id", "station_id", "gap_length"], validate="one_to_one")
    missing_features = second[FIT_COLUMNS].isna().any(axis=1).sum()
    if missing_features:
        print(f"WARNING: dropping {missing_features} second-panel units with NaN features", flush=True)
    second = second.dropna(subset=FIT_COLUMNS)
    second = apply_model(second, fit_period, "simple_prediction_fitperiod")
    second = second.sort_values(["network_id", "station_id", "gap_length"]).reset_index(drop=True)

    # Bit-level check of recomputed features against stored route-A features
    # and of the dev-only model against stored route-A predictions.
    feature_check = features.merge(
        stored_simple[["network_id", "station_id", "gap_length", "acf_only", "donor_r2_only",
                       "additive_d_over_4_heuristic", "nearest_donor_correlation", "predicted_loss"]],
        on=["network_id", "station_id", "gap_length"], suffixes=("_new", "_stored")
    ).merge(
        apply_model(second, fit_dev_only, "predicted_dev_only")[
            ["network_id", "station_id", "gap_length", "predicted_dev_only"]
        ],
        on=["network_id", "station_id", "gap_length"],
    )
    feature_check["feature_max_abs_diff"] = feature_check[
        ["acf_only_new", "acf_only_stored", "donor_r2_only_new", "donor_r2_only_stored",
         "additive_d_over_4_heuristic_new", "additive_d_over_4_heuristic_stored",
         "nearest_donor_correlation_new", "nearest_donor_correlation_stored"]
    ].apply(
        lambda row: max(
            abs(row["acf_only_new"] - row["acf_only_stored"]),
            abs(row["donor_r2_only_new"] - row["donor_r2_only_stored"]),
            abs(row["additive_d_over_4_heuristic_new"] - row["additive_d_over_4_heuristic_stored"]),
            abs(row["nearest_donor_correlation_new"] - row["nearest_donor_correlation_stored"]),
        ),
        axis=1,
    )
    feature_check["predicted_abs_diff_vs_stored"] = (
        feature_check["predicted_dev_only"] - feature_check["predicted_loss"]
    ).abs()
    feature_check.to_csv(OUTPUT / "t2_feature_and_model_check.csv", index=False)
    t2_check_summary = {
        "n_units_compared": int(len(feature_check)),
        "feature_max_abs_diff_max": float(feature_check["feature_max_abs_diff"].max()),
        "dev_only_model_prediction_max_abs_diff_vs_stored_route_a": float(
            feature_check["predicted_abs_diff_vs_stored"].max()
        ),
        "panel_origin_counts": {key: sum(1 for v in panel_origin.values() if v == key) for key in sorted(set(panel_origin.values()))},
    }
    (OUTPUT / "t2_check_summary.json").write_text(json.dumps(t2_check_summary, indent=2) + "\n", encoding="utf-8")

    second.to_csv(OUTPUT / "second_panel_simple_predictions.csv", index=False)

    # ------------------------------------------------------------------ T3
    paired_metrics_rows = []
    within_rows = []
    for subset_name, mask in (("direct_874", second["gap_length"].isin(SUPPORTED_HORIZONS)),
                              ("all_1446", pd.Series(True, index=second.index))):
        subset = second.loc[mask]
        paired_metrics_rows.append(
            {"subset": subset_name, "method": "empirical_transfer",
             **metrics(subset, "empirical_transfer_prediction")}
        )
        paired_metrics_rows.append(
            {"subset": subset_name, "method": "simple_fitting_period",
             **metrics(subset, "simple_prediction_fitperiod")}
        )
        # Fraction of networks where the within-network Spearman of the
        # empirical predictor exceeds the simple predictor's.
        within = subset.groupby("network_id").apply(
            lambda g: pd.Series({
                "rho_empirical_within": float(spearmanr(g["empirical_transfer_prediction"], g["observed_recovery_loss"]).statistic)
                if len(g) >= 2 else np.nan,
                "rho_simple_within": float(spearmanr(g["simple_prediction_fitperiod"], g["observed_recovery_loss"]).statistic)
                if len(g) >= 2 else np.nan,
                "n_units": len(g),
            })
        ).dropna()
        within_rows.append({
            "subset": subset_name,
            "method": "within_network_beat_fraction",
            "fraction_networks_empirical_beats_simple": float(
                np.mean(within["rho_empirical_within"] > within["rho_simple_within"])
            ),
            "n_networks_within_valid": int(len(within)),
            "median_within_delta_rho": float(np.median(within["rho_empirical_within"] - within["rho_simple_within"])),
        })
    paired_metrics_df = pd.DataFrame(paired_metrics_rows)
    within_df = pd.DataFrame(within_rows)
    paired_metrics_df.to_csv(OUTPUT / "t3_paired_metrics.csv", index=False)
    within_df.to_csv(OUTPUT / "t3_within_network_beat_fraction.csv", index=False)

    bootstrap_draw_rows = []
    bootstrap_ci_rows = []
    for subset_name, mask in (("direct_874", second["gap_length"].isin(SUPPORTED_HORIZONS)),
                              ("all_1446", pd.Series(True, index=second.index))):
        subset = second.loc[mask].copy()
        draws = paired_network_bootstrap(subset, repeats=BOOTSTRAP_REPEATS, seed=BOOTSTRAP_SEED)
        draws.insert(0, "subset", subset_name)
        bootstrap_draw_rows.append(draws)
        point = metrics(subset, "empirical_transfer_prediction")
        point_simple = metrics(subset, "simple_prediction_fitperiod")
        summary_row = {
            "subset": subset_name,
            "point_delta_rho_station": point["station_gap_spearman"] - point_simple["station_gap_spearman"],
            "point_delta_rho_network": point["network_spearman"] - point_simple["network_spearman"],
            "delta_rho_station_ci": summarize_ci(draws["delta_rho_station"].to_numpy()),
            "delta_rho_network_ci": summarize_ci(draws["delta_rho_network"].to_numpy()),
            "rho_station_empirical_ci": summarize_ci(draws["rho_station_empirical"].to_numpy()),
            "rho_network_empirical_ci": summarize_ci(draws["rho_network_empirical"].to_numpy()),
            "rho_station_simple_ci": summarize_ci(draws["rho_station_simple"].to_numpy()),
            "rho_network_simple_ci": summarize_ci(draws["rho_network_simple"].to_numpy()),
        }
        bootstrap_ci_rows.append(summary_row)
    bootstrap_draws_df = pd.concat(bootstrap_draw_rows, ignore_index=True)
    bootstrap_ci_df = pd.DataFrame(bootstrap_ci_rows)
    bootstrap_draws_df.to_csv(OUTPUT / "t3_bootstrap_draws.csv", index=False)
    bootstrap_ci_df.to_csv(OUTPUT / "t3_bootstrap_ci.csv", index=False)

    # Provider-block sensitivity: US (usgs), CZ (chmi), NO (nve_hydapi).
    provider_map = roster.set_index("network_id")["provider"].to_dict()
    provider_block = {"usgs": "US", "chmi": "CZ", "nve_hydapi": "NO"}
    second["provider_block"] = second["network_id"].map(provider_map).map(provider_block)
    block_rows = []
    for subset_name, mask in (("direct_874", second["gap_length"].isin(SUPPORTED_HORIZONS)),
                              ("all_1446", pd.Series(True, index=second.index))):
        for block in ("US", "CZ", "NO"):
            subset = second.loc[mask & second["provider_block"].eq(block)]
            for method, column in (("empirical_transfer", "empirical_transfer_prediction"),
                                   ("simple_fitting_period", "simple_prediction_fitperiod")):
                block_rows.append({"subset": subset_name, "provider_block": block,
                                   "method": method, **metrics(subset, column)})
    block_df = pd.DataFrame(block_rows)
    block_df.to_csv(OUTPUT / "t3_provider_block_metrics.csv", index=False)

    # ------------------------------------------------------------------ T4
    per_horizon_rows = []
    for horizon in SUPPORTED_HORIZONS:
        subset = second.loc[second["gap_length"].eq(horizon)]
        for method, column in (("empirical_transfer", "empirical_transfer_prediction"),
                               ("simple_fitting_period", "simple_prediction_fitperiod")):
            per_horizon_rows.append({"gap_length": horizon, "method": method,
                                     **metrics(subset, column)})
    per_horizon_df = pd.DataFrame(per_horizon_rows)
    per_horizon_df.to_csv(OUTPUT / "t4_per_horizon_metrics.csv", index=False)

    # ------------------------------------------------------------------ T5
    decomposition_rows = []
    for subset_name, mask in (("direct_874", second["gap_length"].isin(SUPPORTED_HORIZONS)),
                              ("all_1446", pd.Series(True, index=second.index))):
        subset = second.loc[mask].copy()
        subset = subset.merge(roster[["network_id", "provider"]], on="network_id", how="left")
        for method, column in (("empirical_transfer", "empirical_transfer_prediction"),
                               ("simple_fitting_period", "simple_prediction_fitperiod")):
            per_network = subset.groupby("network_id", as_index=False).apply(
                lambda g: pd.Series({
                    "rho_within_network": float(
                        spearmanr(g[column], g["observed_recovery_loss"]).statistic
                    ) if len(g) >= 2 else np.nan,
                    "n_units": len(g),
                }),
            ).dropna()
            pooled = subset.groupby("network_id", as_index=False).agg(
                pred_mean=(column, "mean"), obs_mean=("observed_recovery_loss", "mean"), n=("network_id", "size")
            )
            pooled = pooled.loc[pooled["n"].ge(2)]
            within = subset.loc[subset["network_id"].isin(pooled["network_id"])].merge(
                pooled[["network_id", "pred_mean", "obs_mean"]], on="network_id"
            )
            residual_rho = float(spearmanr(
                within[column] - within["pred_mean"],
                within["observed_recovery_loss"] - within["obs_mean"],
            ).statistic)
            decomposition_rows.append({
                "subset": subset_name,
                "method": method,
                "per_network_rho_median": float(per_network["rho_within_network"].median()),
                "per_network_rho_q1": float(per_network["rho_within_network"].quantile(0.25)),
                "per_network_rho_q3": float(per_network["rho_within_network"].quantile(0.75)),
                "per_network_rho_mean": float(per_network["rho_within_network"].mean()),
                "n_networks_per_network_rho": int(len(per_network)),
                "residualized_pooled_rho": residual_rho,
                "n_units_residualized": int(len(within)),
                "n_networks_residualized": int(within["network_id"].nunique()),
            })
        # Network-mean-only predictor: every unit predicted by its network mean.
        pooled = subset.groupby("network_id")["observed_recovery_loss"].transform("mean")
        network_mean_frame = subset.assign(network_mean_only_prediction=pooled)
        network_mean_metrics = metrics(network_mean_frame, "network_mean_only_prediction")
        decomposition_rows.append({
            "subset": subset_name,
            "method": "network_mean_only",
            "station_gap_spearman": network_mean_metrics["station_gap_spearman"],
            "network_spearman": network_mean_metrics["network_spearman"],
            "r2": network_mean_metrics["r2"],
            "rmse": network_mean_metrics["rmse"],
            "calibration_slope": network_mean_metrics["calibration_slope"],
            "n": network_mean_metrics["n"],
            "n_networks": network_mean_metrics["n_networks"],
        })
    decomposition_df = pd.DataFrame(decomposition_rows)
    decomposition_df.to_csv(OUTPUT / "t5_within_network_decomposition.csv", index=False)

    # ------------------------------------------------------------------ summary
    summary = {
        "task": "t01_paired_comparison",
        "agent": "b",
        "subsets": {"direct_horizon_units": int(second["gap_length"].isin(SUPPORTED_HORIZONS).sum()),
                    "all_units": int(len(second)),
                    "n_networks": int(second["network_id"].nunique())},
        "t1_reproduction": reproduction_df.to_dict(orient="records"),
        "t2_fit": {"columns": FIT_COLUMNS,
                   "dev_only": fit_dev_only,
                   "fitting_period_dev_plus_first": fit_period,
                   "validation_against_route_a": validation},
        "t3_paired_metrics": [row for row in paired_metrics_df.to_dict(orient="records")]
                             + [row for row in within_df.to_dict(orient="records")],
        "t3_bootstrap_draws": [row for row in bootstrap_draws_df.to_dict(orient="records")],
        "t3_bootstrap_ci": [row for row in bootstrap_ci_df.to_dict(orient="records")],
        "t4_per_horizon": per_horizon_df.to_dict(orient="records"),
        "t5_decomposition": decomposition_df.to_dict(orient="records"),
    }
    def _walk_nan(value: object, path: str = "") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                _walk_nan(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                _walk_nan(item, f"{path}[{index}]")
        elif isinstance(value, float) and value != value:
            print(f"NONFINITE AT {path}")

    def _json_safe(value: object) -> object:
        if isinstance(value, dict):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_json_safe(item) for item in value]
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating, float)):
            numeric = float(value)
            return numeric if np.isfinite(numeric) else None
        return value

    _walk_nan(summary)
    strict_summary = _json_safe(summary)
    (OUTPUT / "analysis_summary.json").write_text(
        json.dumps(strict_summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(strict_summary, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
