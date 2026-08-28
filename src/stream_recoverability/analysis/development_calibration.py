"""Development-stage complete operator, cross-network calibration, and diagnostics.

This module turns the conditional-observability coalitions into one reusable
station-by-gap table.  Boundary memory (B), synchronous temperature donors
(D), meteorology (M), and hydraulics (H) are all explicit.  Calibration is fit
out of network: every reported calibrated prediction comes from a model that
did not see that prediction's river network.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.isotonic import IsotonicRegression

from stream_recoverability.analysis.conditional_observability import (
    ridge_psd,
    spectral_radius,
    stationary_covariance,
    var1_gap_conditional_risk,
)

CalibrationMethod = Literal["linear", "isotonic", "monotonic"]
MemoryWeighting = Literal["uniform", "regime"]

FULL_INFORMATION = "B_union_D_union_M_union_H"
WITHOUT_INFORMATION = {
    "boundary": "D_union_M_union_H",
    "donor": "B_union_M_union_H",
    "meteorology": "B_union_D_union_H",
    "hydraulics": "B_union_D_union_M",
}
SINGLE_INFORMATION = {
    "boundary": "B",
    "donor": "D",
    "meteorology": "M",
    "hydraulics": "H",
}


def regime_memory_weight(
    acf30: float,
    *,
    lower: float = 0.20,
    upper: float = 0.70,
) -> float:
    """Continuous memory weight: zero below ``lower`` and one above ``upper``."""

    return float(np.clip((abs(float(acf30)) - lower) / (upper - lower), 0.0, 1.0))


def _lag_correlation(values: np.ndarray, lag: int) -> float:
    left = np.asarray(values, dtype=float)[:-lag]
    right = np.asarray(values, dtype=float)[lag:]
    valid = np.isfinite(left) & np.isfinite(right)
    return float(np.corrcoef(left[valid], right[valid])[0, 1])


def _memory_regime(acf30: float, lower: float, upper: float) -> str:
    if abs(acf30) >= upper:
        return "high_memory"
    if abs(acf30) <= lower:
        return "low_memory"
    return "transition_memory"


def _fit_var1(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    adjacent = np.isfinite(values[:-1]).all(axis=1) & np.isfinite(values[1:]).all(axis=1)
    previous = values[:-1][adjacent]
    following = values[1:][adjacent]
    transition = np.linalg.lstsq(previous, following, rcond=None)[0].T
    radius = spectral_radius(transition)
    if radius >= 0.98:
        transition = transition * (0.98 / radius)
    residual = following - previous @ transition.T
    process_noise = ridge_psd(np.atleast_2d(np.cov(residual, rowvar=False)))
    return transition, stationary_covariance(transition, process_noise)


def _coalition_summary(
    transition: np.ndarray,
    sigma: np.ndarray,
    *,
    target: int,
    groups: Mapping[str, Sequence[int]],
    players: Sequence[str],
    gap_length: int,
) -> dict[str, float]:
    observed = [
        int(index)
        for player in ("D", "M", "H")
        if player in players
        for index in groups[player]
    ]
    return var1_gap_conditional_risk(
        transition,
        sigma,
        target=target,
        donors=observed,
        gap_length=gap_length,
        include_left_boundary="B" in players,
        include_right_boundary="B" in players,
    )


def station_gap_operator_predictions(
    series: pd.DataFrame,
    *,
    network_id: str,
    target_stations: Sequence[str],
    gaps: Sequence[int],
    donor_stations: Mapping[str, Sequence[str]],
    meteorology_columns: Sequence[str],
    hydraulics_columns: Sequence[str],
    memory_weighting: MemoryWeighting = "uniform",
    memory_lower: float = 0.20,
    memory_upper: float = 0.70,
) -> pd.DataFrame:
    """Predict conditional risk for every requested station and gap.

    ``series`` is a fitting-period table whose columns contain target water
    temperatures, donor water temperatures, meteorological covariates, and
    hydraulic covariates.  M and H are observed throughout the hidden gap;
    target temperature is observed at both gap boundaries and donor
    temperatures are observed throughout the gap.

    The four ``*_incremental_information`` columns are leave-one-information-
    class-out risk reductions.  They therefore measure what each class adds
    after conditioning on the other three, rather than an additive heuristic.
    """

    values = series.to_numpy(dtype=float)
    transition, sigma = _fit_var1(values)
    column_index = {str(name): position for position, name in enumerate(series.columns)}
    meteorology_index = [column_index[str(name)] for name in meteorology_columns]
    hydraulics_index = [column_index[str(name)] for name in hydraulics_columns]
    rows: list[dict[str, float | int | str]] = []

    for station in target_stations:
        target = column_index[str(station)]
        donors = [column_index[str(name)] for name in donor_stations[str(station)]]
        groups = {
            "D": donors,
            "M": meteorology_index,
            "H": hydraulics_index,
        }
        acf30 = _lag_correlation(values[:, target], 30)
        memory_weight = (
            1.0
            if memory_weighting == "uniform"
            else regime_memory_weight(
                acf30,
                lower=memory_lower,
                upper=memory_upper,
            )
        )
        memory_regime = _memory_regime(acf30, memory_lower, memory_upper)

        for gap in gaps:
            coalition_players = {
                "B": ("B",),
                "D": ("D",),
                "M": ("M",),
                "H": ("H",),
                "B_union_D_union_M_union_H": ("B", "D", "M", "H"),
                "D_union_M_union_H": ("D", "M", "H"),
                "B_union_M_union_H": ("B", "M", "H"),
                "B_union_D_union_H": ("B", "D", "H"),
                "B_union_D_union_M": ("B", "D", "M"),
            }
            summaries = {
                name: _coalition_summary(
                    transition,
                    sigma,
                    target=target,
                    groups=groups,
                    players=players,
                    gap_length=int(gap),
                )
                for name, players in coalition_players.items()
            }
            full = summaries[FULL_INFORMATION]
            no_boundary = summaries[WITHOUT_INFORMATION["boundary"]]
            full_risk = float(full["predicted_conditional_risk"])
            no_boundary_risk = float(no_boundary["predicted_conditional_risk"])
            weighted_risk = no_boundary_risk - memory_weight * (
                no_boundary_risk - full_risk
            )
            unconditional_risk = float(full["expected_mae_unconditional"])
            row: dict[str, float | int | str] = {
                "network_id": str(network_id),
                "station_id": str(station),
                "gap_length": int(gap),
                "acf30": acf30,
                "memory_regime": memory_regime,
                "memory_weighting": memory_weighting,
                "memory_weight": memory_weight,
                "unconditional_risk": unconditional_risk,
                "complete_operator_risk": full_risk,
                "predicted_conditional_risk": weighted_risk,
                "predicted_skill": 1.0 - weighted_risk / unconditional_risk,
                "recoverability_r": 1.0
                - np.sqrt(
                    float(no_boundary["normalized_conditional_variance"])
                    - memory_weight
                    * (
                        float(no_boundary["normalized_conditional_variance"])
                        - float(full["normalized_conditional_variance"])
                    )
                ),
            }
            for information, coalition in SINGLE_INFORMATION.items():
                summary = summaries[coalition]
                row[f"{information}_conditional_risk"] = float(
                    summary["predicted_conditional_risk"]
                )
                row[f"{information}_conditional_variance"] = float(
                    summary["normalized_conditional_variance"]
                )
            for information, coalition in WITHOUT_INFORMATION.items():
                row[f"{information}_incremental_information"] = float(
                    summaries[coalition]["predicted_conditional_risk"]
                ) - full_risk
            rows.append(row)
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class LinearCalibrator:
    """Affine map from operator risk to observed recovery loss."""

    intercept: float
    slope: float

    def predict(self, values: Sequence[float] | np.ndarray) -> np.ndarray:
        x = np.asarray(values, dtype=float)
        return self.intercept + self.slope * x


@dataclass(frozen=True)
class MonotonicCalibrator:
    """Piecewise-linear representation of an increasing isotonic fit."""

    x_thresholds: np.ndarray
    y_thresholds: np.ndarray

    def predict(self, values: Sequence[float] | np.ndarray) -> np.ndarray:
        x = np.asarray(values, dtype=float)
        return np.interp(
            x,
            self.x_thresholds,
            self.y_thresholds,
            left=float(self.y_thresholds[0]),
            right=float(self.y_thresholds[-1]),
        )


def fit_calibrator(
    predicted: Sequence[float] | np.ndarray,
    observed: Sequence[float] | np.ndarray,
    *,
    method: CalibrationMethod = "linear",
    sample_weight: Sequence[float] | np.ndarray | None = None,
) -> LinearCalibrator | MonotonicCalibrator:
    """Fit an affine or increasing-isotonic calibration map."""

    x = np.asarray(predicted, dtype=float)
    y = np.asarray(observed, dtype=float)
    weight = np.ones(x.size) if sample_weight is None else np.asarray(sample_weight)
    if method == "linear":
        design = np.column_stack([np.ones(x.size), x])
        root_weight = np.sqrt(weight)
        intercept, slope = np.linalg.lstsq(
            design * root_weight[:, None], y * root_weight, rcond=None
        )[0]
        return LinearCalibrator(float(intercept), float(slope))
    isotonic = IsotonicRegression(increasing=True, out_of_bounds="clip").fit(
        x, y, sample_weight=weight
    )
    return MonotonicCalibrator(
        np.asarray(isotonic.X_thresholds_, dtype=float),
        np.asarray(isotonic.y_thresholds_, dtype=float),
    )


def _rank(left: np.ndarray, right: np.ndarray) -> float:
    return float(spearmanr(left, right).statistic)


def calibration_metrics(
    predictions: pd.DataFrame,
    *,
    observed_col: str = "observed_recovery_loss",
    calibrated_col: str = "calibrated_prediction",
    lower_col: str = "prediction_lower",
    upper_col: str = "prediction_upper",
    network_col: str = "network_id",
) -> dict[str, float]:
    """Return slope/intercept, station-gap rank, network rank, and coverage."""

    x = predictions[calibrated_col].to_numpy(dtype=float)
    y = predictions[observed_col].to_numpy(dtype=float)
    design = np.column_stack([np.ones(x.size), x])
    row_intercept, row_slope = np.linalg.lstsq(design, y, rcond=None)[0]
    counts = predictions.groupby(network_col)[network_col].transform("size")
    root_weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    intercept, slope = np.linalg.lstsq(
        design * root_weight[:, None], y * root_weight, rcond=None
    )[0]
    network = predictions.groupby(network_col, sort=False)[
        [calibrated_col, observed_col]
    ].mean()
    covered = (
        (predictions[observed_col] >= predictions[lower_col])
        & (predictions[observed_col] <= predictions[upper_col])
    )
    coverage = covered.mean()
    network_coverage = covered.groupby(predictions[network_col]).mean()
    network_simultaneous_coverage = covered.groupby(predictions[network_col]).all()
    return {
        "calibration_intercept": float(intercept),
        "calibration_slope": float(slope),
        "row_weighted_calibration_intercept": float(row_intercept),
        "row_weighted_calibration_slope": float(row_slope),
        "rank_spearman": _rank(x, y),
        "network_rank_spearman": _rank(
            network[calibrated_col].to_numpy(dtype=float),
            network[observed_col].to_numpy(dtype=float),
        ),
        "interval_coverage": float(coverage),
        "network_equal_interval_coverage": float(network_coverage.mean()),
        "network_simultaneous_interval_coverage": float(
            network_simultaneous_coverage.mean()
        ),
        "mean_interval_width": float(
            np.mean(
                predictions[upper_col].to_numpy(dtype=float)
                - predictions[lower_col].to_numpy(dtype=float)
            )
        ),
        "n_rows": float(len(predictions)),
        "n_networks": float(predictions[network_col].nunique()),
    }


def residual_diagnostics(
    predictions: pd.DataFrame,
    *,
    residual_col: str = "calibration_residual",
    prediction_col: str = "calibrated_prediction",
    group_cols: Sequence[str] = ("gap_length", "memory_regime"),
) -> pd.DataFrame:
    """Summarize bias, spread, tails, and residual trend by gap/regime."""

    active = [column for column in group_cols if column in predictions]
    grouped = (
        predictions.groupby(active, dropna=False, sort=False)
        if active
        else [((), predictions)]
    )
    rows: list[dict[str, float | int | str]] = []
    for key, group in grouped:
        key = key if isinstance(key, tuple) else (key,)
        residual = group[residual_col].to_numpy(dtype=float)
        predicted = group[prediction_col].to_numpy(dtype=float)
        metadata = dict(zip(active, key, strict=True))
        rows.append(
            {
                **metadata,
                "n": int(residual.size),
                "residual_mean": float(np.mean(residual)),
                "residual_std": float(np.std(residual)),
                "mae": float(np.mean(np.abs(residual))),
                "rmse": float(np.sqrt(np.mean(np.square(residual)))),
                "residual_q05": float(np.quantile(residual, 0.05)),
                "residual_median": float(np.median(residual)),
                "residual_q95": float(np.quantile(residual, 0.95)),
                "residual_prediction_spearman": _rank(residual, predicted),
            }
        )
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class CalibrationResult:
    """Out-of-network predictions plus headline and residual diagnostics."""

    predictions: pd.DataFrame
    folds: pd.DataFrame
    summary: dict[str, float]
    residuals: pd.DataFrame


def leave_one_network_out_calibration(
    frame: pd.DataFrame,
    *,
    predicted_col: str = "predicted_conditional_risk",
    observed_col: str = "observed_recovery_loss",
    network_col: str = "network_id",
    method: CalibrationMethod = "linear",
    coverage: float = 0.90,
) -> CalibrationResult:
    """Cross-fit equal-network calibration and network-block residual intervals."""

    def network_weights(data: pd.DataFrame) -> np.ndarray:
        counts = data.groupby(network_col)[network_col].transform("size")
        return 1.0 / counts.to_numpy(dtype=float)

    def inner_lono_scores(data: pd.DataFrame) -> np.ndarray:
        residuals = []
        for calibration_network in pd.unique(data[network_col]):
            inner_train = data.loc[~data[network_col].eq(calibration_network)]
            inner_test = data.loc[data[network_col].eq(calibration_network)]
            inner_calibrator = fit_calibrator(
                inner_train[predicted_col].to_numpy(dtype=float),
                inner_train[observed_col].to_numpy(dtype=float),
                method=method,
                sample_weight=network_weights(inner_train),
            )
            inner_prediction = inner_calibrator.predict(
                inner_test[predicted_col].to_numpy(dtype=float)
            )
            residuals.append(
                float(
                    np.max(
                        np.abs(
                            inner_test[observed_col].to_numpy(dtype=float)
                            - inner_prediction
                        )
                    )
                )
            )
        return np.asarray(residuals, dtype=float)

    predictions: list[pd.DataFrame] = []
    fold_rows: list[dict[str, float | str]] = []
    for held_out in pd.unique(frame[network_col]):
        train = frame.loc[~frame[network_col].eq(held_out)]
        test = frame.loc[frame[network_col].eq(held_out)].copy()
        calibrator = fit_calibrator(
            train[predicted_col].to_numpy(dtype=float),
            train[observed_col].to_numpy(dtype=float),
            method=method,
            sample_weight=network_weights(train),
        )
        network_scores = inner_lono_scores(train)
        interval_radius = float(
            np.quantile(network_scores, float(coverage), method="higher")
        )
        calibrated = calibrator.predict(test[predicted_col].to_numpy(dtype=float))
        test["calibrated_prediction"] = calibrated
        test["prediction_lower"] = calibrated - interval_radius
        test["prediction_upper"] = calibrated + interval_radius
        test["calibration_residual"] = (
            test[observed_col].to_numpy(dtype=float) - calibrated
        )
        test["held_out_network"] = str(held_out)
        predictions.append(test)
        fold_rows.append(
            {
                "held_out_network": str(held_out),
                "method": "isotonic" if method == "monotonic" else method,
                "train_residual_lower": -interval_radius,
                "train_residual_upper": interval_radius,
                "interval_radius": interval_radius,
                "interval_calibration_unit": "network_max_absolute_inner_lono_residual",
                "n_interval_calibration_networks": float(len(network_scores)),
                "n_train": float(len(train)),
                "n_test": float(len(test)),
            }
        )
    cross_fitted = pd.concat(predictions).sort_index()
    summary = calibration_metrics(
        cross_fitted,
        observed_col=observed_col,
        network_col=network_col,
    )
    summary["nominal_coverage"] = float(coverage)
    return CalibrationResult(
        predictions=cross_fitted,
        folds=pd.DataFrame(fold_rows),
        summary=summary,
        residuals=residual_diagnostics(cross_fitted),
    )


__all__ = [
    "FULL_INFORMATION",
    "CalibrationResult",
    "LinearCalibrator",
    "MonotonicCalibrator",
    "calibration_metrics",
    "fit_calibrator",
    "leave_one_network_out_calibration",
    "regime_memory_weight",
    "residual_diagnostics",
    "station_gap_operator_predictions",
]
