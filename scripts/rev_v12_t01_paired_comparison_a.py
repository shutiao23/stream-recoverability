#!/usr/bin/env python3
"""Agent A (adversarial pair): same-unit paired baseline comparison, second panel.

Revision v12 task t01: compare the fitting-period empirical transfer predictor
against a fitting-period-only simple-descriptor predictor on the SAME second-panel
units (874 direct-horizon and all 1,446), with paired network bootstrap, provider
block sensitivity, per-horizon network Spearman, and a within-network
decomposition of the empirical predictor's network-level rank.

Read-only inputs (never modified):
  results/development_v11/...  (all evidence tables)

Writes only to:
  results/revision_v12/t01_paired_comparison/agent_a/
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import r2_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (
    GAP_LENGTHS,
    read_temperature_panel,
)
from stream_recoverability.experiments.route_a_confirmation import (
    SIMPLE_COLUMNS,
    simple_predictors,
)

OUT = ROOT / "results/revision_v12/t01_paired_comparison/agent_a"
DEV_OUTCOMES = ROOT / "results/development_v11/station_gap_outcomes.csv"
FIRST_PANEL = ROOT / "results/development_v11/route_a_confirmation/predictions.csv"
SECOND = ROOT / "results/development_v11/second_confirmation"
SECOND_SIMPLE = SECOND / "scoring/simple_predictions.csv"
SECOND_EMPIRICAL = SECOND / "scoring/empirical_predictions.csv"
SECOND_ROSTER = SECOND / "frozen_scoring_roster_v2.csv"
CONFIRMATION_DAILY_QC = ROOT / "results/development_v11/confirmation_daily_qc/networks"
SECOND_DAILY_QC = SECOND / "daily_qc/networks"
FINAL_SUMMARY = ROOT / "results/development_v11/final_summary.json"

MODEL_COLUMNS = (
    "gap_length",
    "acf_only",
    "donor_r2_only",
    "additive_d_over_4_heuristic",
    "nearest_donor_correlation",
)
DIRECT_HORIZONS = (7, 30, 90, 180)
BOOTSTRAP_REPEATS = 2000
BOOTSTRAP_SEED = 0


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"network_id": str, "station_id": str})


def _fit_linear(design: np.ndarray, outcome: np.ndarray, weight: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(
        design * weight[:, None], outcome * weight, rcond=None
    )[0]


def fit_route_a_coefficients(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    outcome: str = "observed_recovery_loss",
) -> tuple[float, list[float]]:
    """Equal-network-weighted OLS, matching fit_route_a_model in route_a_confirmation.

    weights = 1 / per-network row count; design includes intercept.
    """
    counts = frame.groupby("network_id")["network_id"].transform("size")
    root_weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    design = np.column_stack(
        [np.ones(len(frame)), frame[list(columns)].to_numpy(dtype=float)]
    )
    coefficients = _fit_linear(design, frame[outcome].to_numpy(dtype=float), root_weight)
    return float(coefficients[0]), [float(value) for value in coefficients[1:]]


def apply_coefficients(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    intercept: float,
    coefficients: list[float],
) -> np.ndarray:
    return intercept + frame[list(columns)].to_numpy(dtype=float) @ np.asarray(coefficients)


def metrics(frame: pd.DataFrame, prediction: str, outcome: str) -> dict[str, float]:
    """Rank, equal-network calibration, R2, RMSE (matches _prediction_metrics in 124)."""
    usable = frame[["network_id", prediction, outcome]].dropna()
    predicted = usable[prediction].to_numpy(dtype=float)
    observed = usable[outcome].to_numpy(dtype=float)
    network = usable.groupby("network_id")[[prediction, outcome]].mean()
    counts = usable.groupby("network_id")["network_id"].transform("size")
    weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    design = np.column_stack([np.ones(len(usable)), predicted])
    intercept, slope = _fit_linear(design, observed, weight)
    return {
        "n": int(len(usable)),
        "n_networks": int(len(network)),
        "station_gap_spearman": float(spearmanr(predicted, observed).statistic),
        "network_spearman": float(
            spearmanr(network[prediction], network[outcome]).statistic
        ),
        "calibration_intercept": float(intercept),
        "calibration_slope": float(slope),
        "r2": float(r2_score(observed, predicted)),
        "rmse": float(np.sqrt(np.mean(np.square(observed - predicted)))),
    }


def network_level_spearman_by_horizon(
    frame: pd.DataFrame, prediction: str, outcome: str
) -> dict[int, dict[str, float]]:
    result = {}
    for horizon, values in frame.groupby("gap_length"):
        network = values.groupby("network_id")[[prediction, outcome]].mean()
        result[int(horizon)] = {
            "n": int(len(values)),
            "n_networks": int(len(network)),
            "network_spearman": float(
                spearmanr(network[prediction], network[outcome]).statistic
            ),
        }
    return result


def within_network_spearman(
    frame: pd.DataFrame, prediction: str, outcome: str, min_units: int = 4
) -> pd.Series:
    rows = {}
    for network, values in frame.groupby("network_id"):
        if len(values) < min_units:
            continue
        predicted = values[prediction].to_numpy(dtype=float)
        observed = values[outcome].to_numpy(dtype=float)
        if np.allclose(predicted, predicted[0]) or np.allclose(observed, observed[0]):
            continue
        rows[network] = float(spearmanr(predicted, observed).statistic)
    return pd.Series(rows, name="spearman")


def residualized_spearman(frame: pd.DataFrame, prediction: str, outcome: str) -> float:
    usable = frame[["network_id", prediction, outcome]].dropna()
    predicted = usable[prediction] - usable.groupby("network_id")[prediction].transform(
        "mean"
    )
    observed = usable[outcome] - usable.groupby("network_id")[outcome].transform("mean")
    return float(spearmanr(predicted, observed).statistic)


def paired_bootstrap(
    frame: pd.DataFrame,
    prediction_a: str,
    prediction_b: str,
    outcome: str,
    *,
    repeats: int,
    seed: int,
) -> dict[str, object]:
    """Network-cluster paired bootstrap: both methods on the same resampled networks."""
    rng = np.random.default_rng(seed)
    networks = np.asarray(sorted(frame["network_id"].unique()))
    by_network = {network: group for network, group in frame.groupby("network_id")}
    deltas_station = []
    deltas_network = []
    deltas_slope = []
    rho_a_station = []
    rho_b_station = []
    rho_a_network = []
    rho_b_network = []
    skipped = 0
    for _ in range(repeats):
        sampled = rng.choice(networks, size=len(networks), replace=True)
        if len(np.unique(sampled)) < 2:
            skipped += 1
            continue
        parts = []
        for draw, network in enumerate(sampled):
            part = by_network[network].copy()
            part["network_id"] = f"draw_{draw}"
            parts.append(part)
        boot = pd.concat(parts, ignore_index=True)
        metric_a = metrics(boot, prediction_a, outcome)
        metric_b = metrics(boot, prediction_b, outcome)
        deltas_station.append(metric_a["station_gap_spearman"] - metric_b["station_gap_spearman"])
        deltas_network.append(metric_a["network_spearman"] - metric_b["network_spearman"])
        deltas_slope.append(metric_a["calibration_slope"] - metric_b["calibration_slope"])
        rho_a_station.append(metric_a["station_gap_spearman"])
        rho_b_station.append(metric_b["station_gap_spearman"])
        rho_a_network.append(metric_a["network_spearman"])
        rho_b_network.append(metric_b["network_spearman"])

    def ci(values: list[float]) -> tuple[float, float, float]:
        array = np.asarray(values)
        return (
            float(np.mean(array)),
            float(np.quantile(array, 0.025)),
            float(np.quantile(array, 0.975)),
        )

    mean, low, high = ci(deltas_station)
    mean_n, low_n, high_n = ci(deltas_network)
    mean_s, low_s, high_s = ci(deltas_slope)
    return {
        "repeats": repeats,
        "skipped_degenerate_draws": skipped,
        "delta_station_gap_spearman_mean": mean,
        "delta_station_gap_spearman_ci95": [low, high],
        "delta_network_spearman_mean": mean_n,
        "delta_network_spearman_ci95": [low_n, high_n],
        "delta_calibration_slope_mean": mean_s,
        "delta_calibration_slope_ci95": [low_s, high_s],
        "empirical_station_gap_spearman_boot_mean": ci(rho_a_station)[0],
        "empirical_station_gap_spearman_ci95": [ci(rho_a_station)[1], ci(rho_a_station)[2]],
        "simple_station_gap_spearman_boot_mean": ci(rho_b_station)[0],
        "simple_station_gap_spearman_ci95": [ci(rho_b_station)[1], ci(rho_b_station)[2]],
        "empirical_network_spearman_boot_mean": ci(rho_a_network)[0],
        "empirical_network_spearman_ci95": [ci(rho_a_network)[1], ci(rho_a_network)[2]],
        "simple_network_spearman_boot_mean": ci(rho_b_network)[0],
        "simple_network_spearman_ci95": [ci(rho_b_network)[1], ci(rho_b_network)[2]],
        "fraction_delta_station_positive": float(np.mean(np.asarray(deltas_station) > 0.0)),
        "fraction_delta_network_positive": float(np.mean(np.asarray(deltas_network) > 0.0)),
    }


def panel_path_for(network_id: str) -> Path:
    second = SECOND_DAILY_QC / network_id / "daily_wide_temperature.csv"
    if second.is_file():
        return second
    first = CONFIRMATION_DAILY_QC / network_id / "daily_wide_temperature.csv"
    if first.is_file():
        return first
    raise FileNotFoundError(f"panel absent for {network_id}")


def recompute_second_panel_features(
    targets: pd.DataFrame,
    *,
    limit_networks: int | None,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    """Recompute simple-descriptor features from daily QC panels (route_a path)."""
    cache = OUT / "features_recomputed.csv"
    cached = set()
    parts = []
    if cache.is_file():
        done = _read_csv(cache)
        cached = set(done["network_id"].unique())
        parts.append(done)
    checks = []
    networks = sorted(targets["network_id"].unique())
    if limit_networks is not None:
        networks = networks[:limit_networks]
    for ordinal, network in enumerate(networks, start=1):
        if network in cached:
            print(f"features {ordinal}/{len(networks)}: {network} (cached)", flush=True)
            continue
        started = time.time()
        panel = read_temperature_panel(str(panel_path_for(network)))
        station_ids = tuple(
            sorted(targets.loc[targets["network_id"].eq(network), "station_id"].astype(str).unique())
        )
        features = simple_predictors(
            str(network), panel, gaps=GAP_LENGTHS, target_stations=station_ids
        )
        checks.append(
            {
                "network_id": network,
                "n_stations_recomputed": int(features["station_id"].nunique()),
                "n_rows_recomputed": len(features),
                "elapsed_seconds": round(time.time() - started, 1),
            }
        )
        parts.append(features)
        pd.concat(parts, ignore_index=True).to_csv(cache, index=False)
        print(
            f"features {ordinal}/{len(networks)}: {network} "
            f"({features['station_id'].nunique()} stations, {round(time.time() - started, 1)}s)",
            flush=True,
        )
    return pd.concat(parts, ignore_index=True), checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit-networks", type=int, help="smoke test: first N networks")
    parser.add_argument("--bootstrap-repeats", type=int, default=BOOTSTRAP_REPEATS)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- evidence
    dev = _read_csv(DEV_OUTCOMES)
    first = _read_csv(FIRST_PANEL)
    second_simple = _read_csv(SECOND_SIMPLE)
    second_empirical = _read_csv(SECOND_EMPIRICAL)
    roster = pd.read_csv(SECOND_ROSTER, dtype={"network_id": str})[
        ["network_id", "provider", "domain"]
    ]

    archive_simple = second_simple.merge(
        second_empirical[
            ["network_id", "station_id", "gap_length", "empirical_transfer_prediction"]
        ],
        on=["network_id", "station_id", "gap_length"],
        validate="one_to_one",
    )
    archive_simple["simple_devonly_archived"] = archive_simple["predicted_loss"]

    # ------------------------------------------------------------ verification
    verification = []
    direct = second_empirical.loc[second_empirical["gap_length"].isin(DIRECT_HORIZONS)]
    verification.append(
        {
            "check": "second_panel_empirical_direct_874",
            "source": "archived scoring/empirical_predictions.csv",
            **metrics(direct, "empirical_transfer_prediction", "observed_recovery_loss"),
        }
    )
    verification.append(
        {
            "check": "second_panel_empirical_all_1446",
            "source": "archived scoring/empirical_predictions.csv",
            **metrics(
                second_empirical,
                "empirical_transfer_prediction",
                "observed_recovery_loss",
            ),
        }
    )
    verification.append(
        {
            "check": "second_panel_simple_archived_all_1446",
            "source": "archived scoring/simple_predictions.csv (dev-only fit)",
            **metrics(second_simple, "predicted_loss", "observed_recovery_loss"),
        }
    )
    # First-panel cross-check of the metric pipeline (direct 780 units).
    first_direct = first.loc[first["gap_length"].isin(DIRECT_HORIZONS)].copy()
    first_empirical = _read_csv(
        ROOT / "results/development_v11/reviewer_completion/confirmation_empirical_predictions.csv"
    )
    first_empirical_agg = first_empirical.groupby(
        ["network_id", "station_id", "gap_length"], as_index=False
    ).agg(
        empirical_transfer_prediction=("empirical_transfer_prediction", "mean"),
        observed_recovery_loss=("mae_deg_c", "mean"),
        empirical_transfer_supported=("empirical_transfer_supported", "all"),
    )
    first_empirical_direct = first_empirical_agg.loc[
        first_empirical_agg["gap_length"].isin(DIRECT_HORIZONS)
    ].copy()
    verification.append(
        {
            "check": "first_panel_empirical_direct_780_supported",
            "source": "reviewer_completion/confirmation_empirical_predictions.csv",
            **metrics(
                first_empirical_direct.loc[first_empirical_direct["empirical_transfer_supported"]],
                "empirical_transfer_prediction",
                "observed_recovery_loss",
            ),
        }
    )
    verification.append(
        {
            "check": "first_panel_simple_direct_780",
            "source": "route_a_confirmation/predictions.csv",
            **metrics(first_direct, "predicted_loss", "observed_recovery_loss"),
        }
    )
    verification.append(
        {
            "check": "first_panel_simple_all_1440",
            "source": "route_a_confirmation/predictions.csv",
            **metrics(first, "predicted_loss", "observed_recovery_loss"),
        }
    )
    fallback_counts = second_empirical.loc[
        ~second_empirical["gap_length"].isin(DIRECT_HORIZONS)
    ].shape[0]
    verification.append(
        {
            "check": "second_panel_fallback_units",
            "expected_572": 572,
            "observed": int(fallback_counts),
        }
    )
    verification.append(
        {
            "check": "second_panel_direct_units",
            "expected_874": 874,
            "observed": int(len(direct)),
        }
    )

    # -------------------------------------------------- feature recomputation
    targets = second_simple[["network_id", "station_id"]].drop_duplicates()
    recomputed, feature_checks = recompute_second_panel_features(
        targets, limit_networks=args.limit_networks
    )
    pd.DataFrame(feature_checks).to_csv(OUT / "feature_recompute_timing.csv", index=False)

    # Verify recomputed features against archived feature columns.
    compare_columns = [
        "acf_only",
        "donor_r2_only",
        "additive_d_over_4_heuristic",
        "nearest_donor_correlation",
        "donor_station_ids",
    ]
    feature_check_rows = []
    merged = recomputed.merge(
        second_simple[
            ["network_id", "station_id", "gap_length", *compare_columns, "predicted_loss"]
        ],
        on=["network_id", "station_id", "gap_length"],
        suffixes=("_recomputed", "_archived"),
    )
    for column in compare_columns[:-1]:
        recomputed_values = merged[f"{column}_recomputed"].to_numpy(dtype=float)
        archived_values = merged[f"{column}_archived"].to_numpy(dtype=float)
        valid = np.isfinite(recomputed_values) & np.isfinite(archived_values)
        feature_check_rows.append(
            {
                "feature": column,
                "n_rows": len(merged),
                "n_finite_both": int(valid.sum()),
                "max_abs_diff": float(np.max(np.abs(recomputed_values[valid] - archived_values[valid]))),
                "pearson": float(np.corrcoef(recomputed_values[valid], archived_values[valid])[0, 1]),
                "exact_match_rows": int(np.allclose(recomputed_values, archived_values, equal_nan=True)),
            }
        )
    feature_check_rows.append(
        {
            "feature": "donor_station_ids",
            "n_rows": len(merged),
            "n_finite_both": len(merged),
            "max_abs_diff": None,
            "pearson": None,
            "exact_match_rows": int((merged["donor_station_ids_recomputed"] == merged["donor_station_ids_archived"]).sum()),
        }
    )
    pd.DataFrame(feature_check_rows).to_csv(OUT / "feature_recomputation_check.csv", index=False)

    features = recomputed.merge(
        second_simple[
            ["network_id", "station_id", "gap_length", "placement_season_sin", "placement_season_cos"]
        ],
        on=["network_id", "station_id", "gap_length"],
        validate="one_to_one",
    ).dropna(subset=list(MODEL_COLUMNS))

    # ------------------------------------------------------------- model fits
    # 1) fitting-period only: development (55) + first panel (42) = 97 networks.
    fit_frame = pd.concat(
        [
            dev[["network_id", "station_id", *MODEL_COLUMNS, "observed_recovery_loss"]],
            first[["network_id", "station_id", *MODEL_COLUMNS, "observed_recovery_loss"]],
        ],
        ignore_index=True,
    )
    fit_frame = fit_frame.dropna(subset=list(MODEL_COLUMNS))
    fit_intercept, fit_coefficients = fit_route_a_coefficients(fit_frame, MODEL_COLUMNS)
    # 2) development-only fit (reproduces the archived route A model).
    dev_fit = dev[["network_id", "station_id", *MODEL_COLUMNS, "observed_recovery_loss"]].dropna(
        subset=list(MODEL_COLUMNS)
    )
    dev_intercept, dev_coefficients = fit_route_a_coefficients(dev_fit, MODEL_COLUMNS)
    coefficients_df = pd.DataFrame(
        [
            {
                "fit_scope": "development_plus_first_panel_97_networks",
                "n_networks": int(fit_frame["network_id"].nunique()),
                "n_units": len(fit_frame),
                "intercept": fit_intercept,
                **{f"coef_{name}": value for name, value in zip(MODEL_COLUMNS, fit_coefficients)},
            },
            {
                "fit_scope": "development_only_55_networks",
                "n_networks": int(dev_fit["network_id"].nunique()),
                "n_units": len(dev_fit),
                "intercept": dev_intercept,
                **{f"coef_{name}": value for name, value in zip(MODEL_COLUMNS, dev_coefficients)},
            },
        ]
    )
    coefficients_df.to_csv(OUT / "model_coefficients.csv", index=False)

    # ----------------------------------------------------------- predictions
    predictions = features.copy()
    predictions["simple_fitperiod"] = apply_coefficients(
        predictions, MODEL_COLUMNS, fit_intercept, fit_coefficients
    )
    predictions["simple_devonly"] = apply_coefficients(
        predictions, MODEL_COLUMNS, dev_intercept, dev_coefficients
    )
    predictions = predictions.merge(
        second_empirical[
            ["network_id", "station_id", "gap_length", "empirical_transfer_prediction", "observed_recovery_loss"]
        ],
        on=["network_id", "station_id", "gap_length"],
        validate="one_to_one",
    )
    predictions = predictions.merge(roster, on="network_id", validate="many_to_one")
    predictions["horizon_group"] = np.where(
        predictions["gap_length"].isin(DIRECT_HORIZONS), "direct", "fallback"
    )
    # Cross-check: dev-only fit applied to recomputed features vs archived predicted_loss.
    archive_check = metrics(
        predictions.rename(columns={"simple_devonly": "predicted_loss"}),
        "predicted_loss",
        "observed_recovery_loss",
    )
    predictions.to_csv(OUT / "predictions.csv", index=False)

    # ---------------------------------------------------------- same-subset metrics
    subsets = {
        "direct_874": predictions.loc[predictions["gap_length"].isin(DIRECT_HORIZONS)],
        "all_1446": predictions,
    }
    method_specs = [
        ("empirical", "empirical_transfer_prediction"),
        ("simple_fitperiod", "simple_fitperiod"),
        ("simple_devonly", "simple_devonly"),
    ]
    metric_rows = []
    for subset_name, subset in subsets.items():
        for method, column in method_specs:
            metric_rows.append(
                {"subset": subset_name, "method": method, **metrics(subset, column, "observed_recovery_loss")}
            )
    metrics_df = pd.DataFrame(metric_rows)
    metrics_df.to_csv(OUT / "same_subset_metrics.csv", index=False)

    # ------------------------------------------------------- paired bootstrap
    bootstrap_rows = []
    for subset_name, subset in subsets.items():
        bootstrap_rows.append(
            {
                "subset": subset_name,
                **paired_bootstrap(
                    subset,
                    "empirical_transfer_prediction",
                    "simple_fitperiod",
                    "observed_recovery_loss",
                    repeats=args.bootstrap_repeats,
                    seed=BOOTSTRAP_SEED,
                ),
            }
        )
    bootstrap_df = pd.DataFrame(bootstrap_rows)
    bootstrap_df.to_csv(OUT / "paired_bootstrap.csv", index=False)

    # ------------------------------------------------------------- beat fraction
    beat_rows = []
    for subset_name, subset in subsets.items():
        for method, column in [("empirical", "empirical_transfer_prediction"), ("simple_fitperiod", "simple_fitperiod")]:
            series = within_network_spearman(subset, column, "observed_recovery_loss")
            series.name = method
            if method == "empirical":
                emp_within = series
            else:
                common = emp_within.index.intersection(series.index)
                beat_rows.append(
                    {
                        "subset": subset_name,
                        "n_networks_with_both_defined": int(len(common)),
                        "n_networks_total": int(subset["network_id"].nunique()),
                        "fraction_empirical_beats_simple": float((emp_within.loc[common] > series.loc[common]).mean()),
                        "median_within_network_spearman_empirical": float(emp_within.loc[common].median()),
                        "median_within_network_spearman_simple": float(series.loc[common].median()),
                    }
                )
    beat_df = pd.DataFrame(beat_rows)
    beat_df.to_csv(OUT / "beat_fraction.csv", index=False)

    # ------------------------------------------------------- provider sensitivity
    provider_rows = []
    for subset_name, subset in subsets.items():
        for provider, block in subset.groupby("provider"):
            for method, column in method_specs:
                provider_rows.append(
                    {
                        "subset": subset_name,
                        "provider": provider,
                        "method": method,
                        **metrics(block, column, "observed_recovery_loss"),
                    }
                )
    provider_df = pd.DataFrame(provider_rows)
    provider_df.to_csv(OUT / "provider_sensitivity.csv", index=False)

    # -------------------------------------------------------------- per-horizon
    horizon_rows = []
    for horizon in DIRECT_HORIZONS:
        subset = predictions.loc[predictions["gap_length"].eq(horizon)]
        row = {"horizon": horizon, "n_units": len(subset), "n_networks": int(subset["network_id"].nunique())}
        for method, column in method_specs:
            row[f"{method}_network_spearman"] = network_level_spearman_by_horizon(
                subset, column, "observed_recovery_loss"
            )[horizon]["network_spearman"]
        horizon_rows.append(row)
    horizon_df = pd.DataFrame(horizon_rows)
    horizon_df.to_csv(OUT / "per_horizon_network_spearman.csv", index=False)

    # -------------------------------------------------- within-network decomposition
    decomposition_rows = []
    for subset_name, subset in subsets.items():
        row = {"subset": subset_name}
        for method, column in method_specs:
            per_network = within_network_spearman(subset, column, "observed_recovery_loss")
            row[f"{method}_n_networks_defined"] = int(len(per_network))
            row[f"{method}_within_median"] = float(per_network.median())
            row[f"{method}_within_q1"] = float(per_network.quantile(0.25))
            row[f"{method}_within_q3"] = float(per_network.quantile(0.75))
            row[f"{method}_within_iqr"] = float(per_network.quantile(0.75) - per_network.quantile(0.25))
            row[f"{method}_residualized_spearman"] = residualized_spearman(
                subset, column, "observed_recovery_loss"
            )
            row[f"{method}_pooled_spearman"] = float(
                spearmanr(subset[column], subset["observed_recovery_loss"]).statistic
            )
            row[f"{method}_network_spearman"] = float(
                spearmanr(
                    subset.groupby("network_id")[[column, "observed_recovery_loss"]].mean()[column],
                    subset.groupby("network_id")[[column, "observed_recovery_loss"]].mean()["observed_recovery_loss"],
                ).statistic
            )
        network_mean = subset.groupby("network_id")["observed_recovery_loss"].transform("mean")
        row["network_mean_only_pooled_spearman"] = float(
            spearmanr(network_mean, subset["observed_recovery_loss"]).statistic
        )
        decomposition_rows.append(row)
    decomposition_df = pd.DataFrame(decomposition_rows)
    decomposition_df.to_csv(OUT / "within_network_decomposition.csv", index=False)

    # ---------------------------------------------------------------- summary
    summary = {
        "task": "t01_paired_comparison",
        "agent": "a",
        "subsets": {
            "direct_874": {"n_units": int(len(direct)), "n_networks": int(direct["network_id"].nunique())},
            "all_1446": {"n_units": len(predictions), "n_networks": int(predictions["network_id"].nunique())},
        },
        "fit_scopes": {
            "fitting_period_only": "development (55 networks) + first panel (42 networks)",
            "development_only": "development (55 networks), reproduces archived route A model",
        },
        "archive_check_simple_fitperiod": archive_check,
        "verification": verification,
        "metrics": metric_rows,
        "paired_bootstrap": bootstrap_rows,
        "beat_fraction": beat_rows,
        "per_horizon": horizon_rows,
        "within_network_decomposition": decomposition_rows,
        "feature_recomputation": feature_check_rows,
        "artifacts": [
            "same_subset_metrics.csv",
            "paired_bootstrap.csv",
            "beat_fraction.csv",
            "provider_sensitivity.csv",
            "per_horizon_network_spearman.csv",
            "within_network_decomposition.csv",
            "model_coefficients.csv",
            "predictions.csv",
            "feature_recomputation_check.csv",
            "feature_recompute_timing.csv",
        ],
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, default=str))
    print(f"\nWrote artifacts to {OUT}")


if __name__ == "__main__":
    main()
