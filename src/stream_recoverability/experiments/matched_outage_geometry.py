"""Matched planted-outage geometry analysis for the v11 predictors.

Actual missing days have no truth.  The frozen catalog maps each such geometry
to a non-overlapping, truth-bearing observed counterpart.  This module applies
the v11 fitting-period empirical predictor and the nested simple comparator to
the existing XGBoost B+D counterpart losses, then pairs every natural geometry
with the same station's nearest artificial-grid horizon.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ARTIFICIAL_GAP_GRID = (7, 14, 30, 60, 90, 180, 365)
EXPECTED_NATURAL_IMPLEMENTATION = "xgboost_donor_plus_train_loo_boundary_BD"
EXPECTED_NATURAL_CONTRACT = "t2_v91_runner_v4_legacy_mh_lag_grid_v1"


def normalize_station_id(value: object, widths: Sequence[int] = (15, 8)) -> str:
    text = str(value).strip().removesuffix(".0")
    if not text.isdigit():
        return text
    for width in sorted({int(item) for item in widths}):
        if len(text) <= width:
            return text.zfill(width)
    return text


def nearest_artificial_horizon(
    gap_length: int, grid: Sequence[int] = ARTIFICIAL_GAP_GRID
) -> int:
    """Choose the nearest log-horizon, breaking ties toward the shorter gap."""

    gap = int(gap_length)
    candidates = tuple(sorted({int(value) for value in grid}))
    if gap <= 0 or not candidates or candidates[0] <= 0:
        raise ValueError("gap lengths must be positive")
    return min(candidates, key=lambda value: (abs(np.log(gap / value)), value))


def validate_natural_xgboost_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Fail closed unless rows are frozen truth-bearing XGBoost B+D counterparts."""

    required = {
        "network_id",
        "target_station",
        "model",
        "information_condition",
        "geometry",
        "geometry_id",
        "truth_start_date",
        "observed_missing_start_date",
        "actual_missing_truth_available",
        "benchmark_truth_source",
        "status",
        "implementation",
        "runner_contract_version",
        "mae_deg_c",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"natural result lacks columns: {sorted(missing)}")
    selected = frame.loc[
        frame["geometry"].eq("natural_outage")
        & frame["model"].eq("xgboost")
        & frame["information_condition"].eq("B_union_D")
        & frame["status"].eq("complete")
        & frame["mae_deg_c"].notna()
    ].copy()
    if selected.empty:
        raise ValueError("no complete natural XGBoost B+D counterparts")
    if selected["actual_missing_truth_available"].astype(bool).any():
        raise ValueError("actual missing days must not be treated as truth-bearing")
    if not selected["benchmark_truth_source"].eq(
        "held_out_observed_counterpart"
    ).all():
        raise ValueError("natural rows must use held-out observed counterparts")
    if not selected["implementation"].eq(EXPECTED_NATURAL_IMPLEMENTATION).all():
        raise ValueError("natural rows do not use the expected XGBoost B+D model")
    if not selected["runner_contract_version"].eq(EXPECTED_NATURAL_CONTRACT).all():
        raise ValueError("natural rows do not use the expected outer-fit contract")
    if selected["geometry_id"].duplicated().any():
        raise ValueError("natural geometry IDs must be unique")
    truth = pd.to_datetime(selected["truth_start_date"])
    missing_start = pd.to_datetime(selected["observed_missing_start_date"])
    if truth.isna().any() or missing_start.isna().any():
        raise ValueError("natural and counterpart dates must be present")
    return selected


def network_equal_coefficients(
    frame: pd.DataFrame, columns: Sequence[str], outcome: str
) -> np.ndarray:
    counts = frame.groupby("network_id")["network_id"].transform("size")
    root_weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    design = np.column_stack(
        [np.ones(len(frame)), frame[list(columns)].to_numpy(dtype=float)]
    )
    return np.linalg.lstsq(
        design * root_weight[:, None],
        frame[outcome].to_numpy(dtype=float) * root_weight,
        rcond=None,
    )[0]


def linear_prediction(
    frame: pd.DataFrame, columns: Sequence[str], coefficients: np.ndarray
) -> np.ndarray:
    design = np.column_stack(
        [np.ones(len(frame)), frame[list(columns)].to_numpy(dtype=float)]
    )
    return design @ coefficients


def network_spearman(frame: pd.DataFrame, prediction: str, outcome: str) -> float:
    network = frame.groupby("network_id")[[prediction, outcome]].mean()
    return float(spearmanr(network[prediction], network[outcome]).statistic)


def network_bootstrap_spearman(
    frame: pd.DataFrame,
    prediction: str,
    outcome: str,
    *,
    repeats: int = 2000,
    seed: int = 20260828,
) -> dict[str, float | int]:
    """Bootstrap network-summary Spearman by resampling whole networks."""

    network = frame.groupby("network_id")[[prediction, outcome]].mean().dropna()
    if len(network) < 3:
        raise ValueError("network bootstrap requires at least three networks")
    rng = np.random.default_rng(seed)
    values = network.to_numpy(dtype=float)
    estimates = []
    for _ in range(int(repeats)):
        chosen = rng.integers(0, len(values), size=len(values))
        sampled = values[chosen]
        rho = float(spearmanr(sampled[:, 0], sampled[:, 1]).statistic)
        if np.isfinite(rho):
            estimates.append(rho)
    return {
        "estimate": network_spearman(frame, prediction, outcome),
        "ci95_lower": float(np.quantile(estimates, 0.025)),
        "ci95_upper": float(np.quantile(estimates, 0.975)),
        "bootstrap_repeats": int(repeats),
        "finite_repeats": len(estimates),
        "n_networks": len(network),
    }


def paired_bootstrap_delta(
    paired: pd.DataFrame,
    prediction: str,
    *,
    repeats: int = 2000,
    seed: int = 20260828,
) -> dict[str, float | int]:
    """Bootstrap natural-minus-artificial network rank on matched geometries."""

    columns = [
        f"natural_{prediction}",
        "natural_observed_loss",
        f"artificial_{prediction}",
        "artificial_observed_loss",
    ]
    network = paired.groupby("network_id")[columns].mean().dropna()
    rng = np.random.default_rng(seed)

    def delta(values: np.ndarray) -> float:
        natural = float(spearmanr(values[:, 0], values[:, 1]).statistic)
        artificial = float(spearmanr(values[:, 2], values[:, 3]).statistic)
        return natural - artificial

    values = network.to_numpy(dtype=float)
    estimate = delta(values)
    estimates = []
    for _ in range(int(repeats)):
        sampled = values[rng.integers(0, len(values), size=len(values))]
        value = delta(sampled)
        if np.isfinite(value):
            estimates.append(value)
    return {
        "natural_minus_artificial_estimate": estimate,
        "ci95_lower": float(np.quantile(estimates, 0.025)),
        "ci95_upper": float(np.quantile(estimates, 0.975)),
        "bootstrap_repeats": int(repeats),
        "finite_repeats": len(estimates),
        "n_networks": len(network),
    }


__all__ = [
    "ARTIFICIAL_GAP_GRID",
    "EXPECTED_NATURAL_CONTRACT",
    "EXPECTED_NATURAL_IMPLEMENTATION",
    "linear_prediction",
    "nearest_artificial_horizon",
    "network_bootstrap_spearman",
    "network_equal_coefficients",
    "network_spearman",
    "normalize_station_id",
    "paired_bootstrap_delta",
    "validate_natural_xgboost_rows",
]
