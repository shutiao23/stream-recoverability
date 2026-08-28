"""Route A simple-risk model and wholly-new-network confirmation analysis."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from stream_recoverability.experiments.development_recovery import year_split
from stream_recoverability.experiments.recoverability_baselines import (
    acf_only,
    additive_heuristic,
    donor_r2_only,
)

SIMPLE_COLUMNS = (
    "gap_length",
    "acf_only",
    "donor_r2_only",
    "additive_d_over_4_heuristic",
    "nearest_donor_correlation",
    "placement_season_sin",
    "placement_season_cos",
)


def _lag_correlation(values: np.ndarray, lag: float) -> float:
    lower = int(np.floor(max(1.0, lag)))
    upper = int(np.ceil(max(1.0, lag)))

    def correlation(distance: int) -> float:
        valid = np.isfinite(values[:-distance]) & np.isfinite(values[distance:])
        return float(
            np.corrcoef(values[:-distance][valid], values[distance:][valid])[0, 1]
        )

    low = correlation(lower)
    if lower == upper:
        return low
    high = correlation(upper)
    return float(low + (high - low) * (lag - lower))


def _training_anomalies(
    panel: pd.DataFrame,
) -> tuple[pd.DataFrame, tuple[int, ...]]:
    train_mask, training_years, _ = year_split(panel.index)
    training = panel.loc[train_mask].copy()
    climatology = training.groupby(training.index.dayofyear).transform("mean")
    fallback = training.mean()
    climatology = climatology.fillna(fallback)
    return training - climatology, training_years


def _year_block_donor_r2(
    target: pd.Series,
    donors: pd.DataFrame,
) -> float:
    residual = 0.0
    total = 0.0
    folds = 0
    for held_year in sorted(target.index.year.unique()):
        train = target.index.year != held_year
        test = ~train
        train_frame = pd.concat([target[train], donors.loc[train]], axis=1).dropna()
        test_frame = pd.concat([target[test], donors.loc[test]], axis=1).dropna()
        design_train = np.column_stack(
            [np.ones(len(train_frame)), train_frame.iloc[:, 1:].to_numpy(dtype=float)]
        )
        design_test = np.column_stack(
            [np.ones(len(test_frame)), test_frame.iloc[:, 1:].to_numpy(dtype=float)]
        )
        if len(train_frame) <= design_train.shape[1] or len(test_frame) < 2:
            continue
        coefficients = np.linalg.lstsq(
            design_train, train_frame.iloc[:, 0].to_numpy(dtype=float), rcond=None
        )[0]
        observed = test_frame.iloc[:, 0].to_numpy(dtype=float)
        predicted = design_test @ coefficients
        fold_total = float(np.square(observed - observed.mean()).sum())
        if fold_total == 0.0:
            continue
        residual += float(np.square(observed - predicted).sum())
        total += fold_total
        folds += 1
    return (
        float("nan") if folds == 0 else float(np.clip(1.0 - residual / total, 0.0, 1.0))
    )


def simple_predictors(
    network_id: str,
    panel: pd.DataFrame,
    *,
    gaps: Sequence[int],
    min_train_days: int = 365,
    target_stations: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Compute train-only gap, ACF, donor-R2, and additive predictors."""

    daily = panel.copy().sort_index().asfreq("D")
    daily.columns = daily.columns.astype(str)
    anomalies, training_years = _training_anomalies(daily)
    rows = []
    targets = daily.columns if target_stations is None else target_stations
    for station in targets:
        target = anomalies[station]
        donors = tuple(
            donor
            for donor in daily.columns
            if donor != station
            and int((target.notna() & anomalies[donor].notna()).sum()) >= min_train_days
        )
        donor_r2 = _year_block_donor_r2(target, anomalies[list(donors)])
        nearest_correlation = max(
            abs(float(target.corr(anomalies[donor]))) for donor in donors
        )
        phi = _lag_correlation(target.to_numpy(dtype=float), 1.0)
        for gap in gaps:
            rho = _lag_correlation(target.to_numpy(dtype=float), float(gap) / 4.0)
            rows.append(
                {
                    "network_id": str(network_id),
                    "station_id": str(station),
                    "gap_length": int(gap),
                    "acf_only": acf_only(phi, int(gap)),
                    "donor_r2_only": donor_r2_only(donor_r2, int(gap)),
                    "additive_d_over_4_heuristic": additive_heuristic(donor_r2, rho),
                    "nearest_donor_correlation": nearest_correlation,
                    "donor_station_ids": "|".join(donors),
                    "training_years": "|".join(map(str, training_years)),
                }
            )
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class RouteAModel:
    intercept: float
    columns: tuple[str, ...]
    coefficients: tuple[float, ...]
    interval_radius: float

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return self.intercept + frame[list(self.columns)].to_numpy(
            dtype=float
        ) @ np.asarray(self.coefficients)


def fit_route_a_model(
    development: pd.DataFrame,
    lono_predictions: pd.DataFrame,
    *,
    coverage: float = 0.90,
) -> RouteAModel:
    """Fit the fixed equal-network simple model and its network-block radius."""

    selected_model = str(lono_predictions["selected_simple_model"].mode().iloc[0])
    selected_columns = tuple(selected_model.split("|"))
    counts = development.groupby("network_id")["network_id"].transform("size")
    weights = 1.0 / counts.to_numpy(dtype=float)
    design = np.column_stack(
        [
            np.ones(len(development)),
            development[list(selected_columns)].to_numpy(dtype=float),
        ]
    )
    root_weight = np.sqrt(weights)
    coefficients = np.linalg.lstsq(
        design * root_weight[:, None],
        development["observed_recovery_loss"].to_numpy(dtype=float) * root_weight,
        rcond=None,
    )[0]
    absolute = np.abs(
        lono_predictions["observed_recovery_loss"].to_numpy(dtype=float)
        - lono_predictions["simple_prediction"].to_numpy(dtype=float)
    )
    network_scores = (
        pd.Series(absolute).groupby(lono_predictions["network_id"].to_numpy()).max()
    )
    radius = float(np.quantile(network_scores, coverage, method="higher"))
    return RouteAModel(
        intercept=float(coefficients[0]),
        columns=selected_columns,
        coefficients=tuple(float(value) for value in coefficients[1:]),
        interval_radius=radius,
    )


def apply_route_a_model(model: RouteAModel, predictors: pd.DataFrame) -> pd.DataFrame:
    result = predictors.copy()
    result["predicted_loss"] = model.predict(result)
    result["prediction_lower"] = result["predicted_loss"] - model.interval_radius
    result["prediction_upper"] = result["predicted_loss"] + model.interval_radius
    return result


def confirmation_metrics(frame: pd.DataFrame) -> dict[str, float]:
    """Rank, equal-network calibration, and interval coverage on new networks."""

    observed = frame["observed_recovery_loss"].to_numpy(dtype=float)
    predicted = frame["predicted_loss"].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(frame)), predicted])
    counts = frame.groupby("network_id")["network_id"].transform("size")
    root_weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    intercept, slope = np.linalg.lstsq(
        design * root_weight[:, None], observed * root_weight, rcond=None
    )[0]
    network = frame.groupby("network_id")[
        ["predicted_loss", "observed_recovery_loss"]
    ].mean()
    covered = observed >= frame["prediction_lower"].to_numpy(dtype=float)
    covered &= observed <= frame["prediction_upper"].to_numpy(dtype=float)
    simultaneous = pd.Series(covered).groupby(frame["network_id"].to_numpy()).all()
    return {
        "station_gap_spearman": float(spearmanr(predicted, observed).statistic),
        "network_spearman": float(
            spearmanr(
                network["predicted_loss"], network["observed_recovery_loss"]
            ).statistic
        ),
        "calibration_intercept": float(intercept),
        "calibration_slope": float(slope),
        "interval_coverage": float(np.mean(covered)),
        "network_simultaneous_interval_coverage": float(simultaneous.mean()),
        "mean_interval_width": float(
            2.0 * (frame["prediction_upper"] - frame["predicted_loss"]).mean()
        ),
        "n_networks": float(frame["network_id"].nunique()),
        "n_station_gaps": float(len(frame)),
    }


def point_prediction_metrics(frame: pd.DataFrame) -> dict[str, float]:
    """Rank and calibration metrics without manufacturing interval columns."""

    observed = frame["observed_recovery_loss"].to_numpy(dtype=float)
    predicted = frame["predicted_loss"].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(frame)), predicted])
    counts = frame.groupby("network_id")["network_id"].transform("size")
    root_weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    intercept, slope = np.linalg.lstsq(
        design * root_weight[:, None], observed * root_weight, rcond=None
    )[0]
    network = frame.groupby("network_id")[
        ["predicted_loss", "observed_recovery_loss"]
    ].mean()
    return {
        "station_gap_spearman": float(spearmanr(predicted, observed).statistic),
        "network_spearman": float(
            spearmanr(
                network["predicted_loss"], network["observed_recovery_loss"]
            ).statistic
        ),
        "calibration_intercept": float(intercept),
        "calibration_slope": float(slope),
        "n_networks": float(frame["network_id"].nunique()),
        "n_station_gaps": float(len(frame)),
    }


def thermal_state_changes(
    network_id: str,
    panel: pd.DataFrame,
    *,
    target_stations: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Compare target memory and thermal range across the fixed year split."""

    daily = panel.copy().sort_index().asfreq("D")
    train_mask, _, _ = year_split(daily.index)
    rows = []
    targets = daily.columns.astype(str) if target_stations is None else target_stations
    for station in targets:
        training = daily.loc[train_mask, station].dropna().to_numpy(dtype=float)
        evaluation = daily.loc[~train_mask, station].dropna().to_numpy(dtype=float)
        training_range = float(
            np.quantile(training, 0.95) - np.quantile(training, 0.05)
        )
        evaluation_range = float(
            np.quantile(evaluation, 0.95) - np.quantile(evaluation, 0.05)
        )
        train_acf30 = _lag_correlation(training, 30.0)
        evaluation_acf30 = _lag_correlation(evaluation, 30.0)
        range_change = float(evaluation_range / training_range - 1.0)
        acf_change = float(evaluation_acf30 - train_acf30)
        rows.append(
            {
                "network_id": str(network_id),
                "station_id": station,
                "training_thermal_range": training_range,
                "evaluation_thermal_range": evaluation_range,
                "thermal_range_relative_change": range_change,
                "training_acf30": train_acf30,
                "evaluation_acf30": evaluation_acf30,
                "acf30_change": acf_change,
                "thermal_state_shift": bool(
                    abs(range_change) >= 0.25 or abs(acf_change) >= 0.20
                ),
            }
        )
    return pd.DataFrame(rows)


def grouped_confirmation_metrics(
    frame: pd.DataFrame,
    *,
    group_column: str,
) -> pd.DataFrame:
    rows = []
    for group, values in frame.groupby(group_column):
        rows.append({group_column: group, **confirmation_metrics(values)})
    return pd.DataFrame(rows)


def fit_safe_release_threshold(
    development: pd.DataFrame,
    *,
    risk_column: str,
    loss_column: str = "observed_recovery_loss",
    false_release_cap: float = 0.05,
    unsafe_loss_c: float = 0.5,
) -> float:
    """Select the largest development safe set under the false-release cap."""

    ordered = development.sort_values(risk_column)
    unsafe = ordered[loss_column].to_numpy(dtype=float) > unsafe_loss_c
    rates = np.cumsum(unsafe) / np.arange(1, len(ordered) + 1)
    eligible = np.flatnonzero(rates <= false_release_cap)
    return (
        float("nan")
        if len(eligible) == 0
        else float(ordered.iloc[int(eligible[-1])][risk_column])
    )


def apply_safe_release_threshold(
    confirmation: pd.DataFrame,
    *,
    risk_column: str,
    threshold: float,
    loss_column: str = "observed_recovery_loss",
    unsafe_loss_c: float = 0.5,
) -> dict[str, float]:
    released = confirmation[risk_column].to_numpy(dtype=float) <= threshold
    losses = confirmation[loss_column].to_numpy(dtype=float)
    return {
        "threshold": float(threshold),
        "n": float(len(confirmation)),
        "n_released": float(released.sum()),
        "safe_fill_fraction": float(released.mean()),
        "false_release_rate": float(np.mean(losses[released] > unsafe_loss_c))
        if released.any()
        else float("nan"),
    }


def network_bootstrap_intervals(
    frame: pd.DataFrame,
    *,
    repeats: int = 1000,
    seed: int = 0,
) -> pd.DataFrame:
    """Network-cluster bootstrap intervals for confirmation metrics."""

    rng = np.random.default_rng(seed)
    networks = frame["network_id"].unique()
    rows = []
    for _ in range(repeats):
        sampled = rng.choice(networks, size=len(networks), replace=True)
        parts = []
        for draw, network in enumerate(sampled):
            part = frame.loc[frame["network_id"].eq(network)].copy()
            part["network_id"] = f"draw_{draw}"
            parts.append(part)
        rows.append(confirmation_metrics(pd.concat(parts, ignore_index=True)))
    samples = pd.DataFrame(rows)
    estimate = confirmation_metrics(frame)
    return pd.DataFrame(
        [
            {
                "metric": metric,
                "estimate": float(estimate[metric]),
                "lower_95": float(samples[metric].quantile(0.025)),
                "upper_95": float(samples[metric].quantile(0.975)),
            }
            for metric in (
                "station_gap_spearman",
                "network_spearman",
                "calibration_intercept",
                "calibration_slope",
                "interval_coverage",
                "network_simultaneous_interval_coverage",
            )
        ]
    )


__all__ = [
    "SIMPLE_COLUMNS",
    "RouteAModel",
    "apply_route_a_model",
    "apply_safe_release_threshold",
    "confirmation_metrics",
    "fit_route_a_model",
    "fit_safe_release_threshold",
    "grouped_confirmation_metrics",
    "network_bootstrap_intervals",
    "point_prediction_metrics",
    "simple_predictors",
    "thermal_state_changes",
]
