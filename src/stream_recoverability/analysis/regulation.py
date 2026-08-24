"""Hydrothermal regulation diagnostics used in the major-revision analysis.

These functions keep the reviewer-requested state-change, regulation-fingerprint,
and low-frequency sensitivity calculations explicit and independently testable.
They do not alter the originally frozen 2006--2015 covariance budget.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, skew

from stream_recoverability.analysis.recoverability_budget import budget_decomposition


def _stable_doy(dates: Sequence[object] | pd.Series) -> np.ndarray:
    axis = pd.DatetimeIndex(pd.to_datetime(dates))
    return np.asarray(
        [pd.Timestamp(2000, value.month, value.day).dayofyear for value in axis],
        dtype=int,
    )


def circular_doy_climatology(
    fit_dates: Sequence[object] | pd.Series,
    fit_values: Sequence[float] | pd.Series,
    *,
    half_window_days: int = 7,
) -> pd.Series:
    """Return a 366-day circular median climatology fitted to finite values."""

    if half_window_days < 0 or half_window_days > 182:
        raise ValueError("half_window_days must be between 0 and 182")
    dates = pd.DatetimeIndex(pd.to_datetime(fit_dates))
    values = pd.to_numeric(pd.Series(fit_values), errors="coerce").to_numpy(float)
    if len(dates) != len(values):
        raise ValueError("fit_dates and fit_values must have the same length")
    finite = np.isfinite(values)
    if not finite.any():
        raise ValueError("climatology requires at least one finite value")
    doys = _stable_doy(dates)[finite]
    observed = values[finite]
    fallback = float(np.median(observed))
    result = np.empty(366, dtype=float)
    for doy in range(1, 367):
        distance = np.abs(doys - doy)
        distance = np.minimum(distance, 366 - distance)
        local = observed[distance <= half_window_days]
        result[doy - 1] = float(np.median(local)) if len(local) else fallback
    return pd.Series(result, index=np.arange(1, 367), name="climatology")


def predict_climatology(
    climatology: pd.Series,
    dates: Sequence[object] | pd.Series,
) -> np.ndarray:
    """Map a stable 366-day climatology to an arbitrary daily date axis."""

    doys = _stable_doy(dates)
    values = pd.to_numeric(climatology.reindex(doys), errors="coerce").to_numpy(float)
    if not np.isfinite(values).all():
        raise ValueError("climatology does not cover the requested calendar days")
    return values


def temperature_anomalies(
    frame: pd.DataFrame,
    station: str,
    *,
    fit_frame: pd.DataFrame,
    half_window_days: int = 7,
) -> pd.Series:
    """Subtract a fitting-period circular day-of-year median from temperature."""

    column = f"{station}_T"
    for source, label in ((frame, "frame"), (fit_frame, "fit_frame")):
        missing = {"date", column}.difference(source.columns)
        if missing:
            raise ValueError(f"{label} lacks columns: {sorted(missing)}")
    climatology = circular_doy_climatology(
        fit_frame["date"],
        fit_frame[column],
        half_window_days=half_window_days,
    )
    observed = pd.to_numeric(frame[column], errors="coerce").to_numpy(float)
    anomaly = observed - predict_climatology(climatology, frame["date"])
    return pd.Series(anomaly, index=frame.index, name=f"{station}_T_anomaly")


def _acf(values: pd.Series, lag: int) -> float:
    numeric = pd.to_numeric(values, errors="coerce").to_numpy(float)
    if lag < 1 or len(numeric) <= lag:
        return np.nan
    left, right = numeric[:-lag], numeric[lag:]
    finite = np.isfinite(left) & np.isfinite(right)
    if finite.sum() < 3:
        return np.nan
    return float(np.corrcoef(left[finite], right[finite])[0, 1])


def annual_thermal_metrics(
    frame: pd.DataFrame,
    stations: Sequence[str],
) -> pd.DataFrame:
    """Return observed annual minimum, maximum, mean, and amplitude."""

    if "date" not in frame:
        raise ValueError("annual thermal metrics require date")
    dates = pd.to_datetime(frame["date"])
    rows: list[dict[str, Any]] = []
    for station in stations:
        column = f"{station}_T"
        if column not in frame:
            raise ValueError(f"annual thermal metrics lack {column}")
        values = pd.to_numeric(frame[column], errors="coerce")
        table = pd.DataFrame({"year": dates.dt.year, "temperature": values})
        for year, group in table.groupby("year", sort=True, observed=True):
            finite = group["temperature"].dropna()
            rows.append(
                {
                    "station_id": str(station),
                    "year": int(year),
                    "annual_minimum_degC": float(finite.min()),
                    "annual_maximum_degC": float(finite.max()),
                    "annual_mean_degC": float(finite.mean()),
                    "annual_amplitude_degC": float(finite.max() - finite.min()),
                    "n_days": len(finite),
                }
            )
    return pd.DataFrame(rows)


def period_thermal_metrics(
    frame: pd.DataFrame,
    stations: Sequence[str],
    periods: Mapping[str, tuple[str, str]],
    *,
    climatology_fit_frame: pd.DataFrame,
    half_window_days: int = 7,
) -> pd.DataFrame:
    """Summarize amplitude, anomaly variability, persistence, and shape."""

    dates = pd.to_datetime(frame["date"])
    annual = annual_thermal_metrics(frame, stations)
    rows: list[dict[str, Any]] = []
    for station in stations:
        anomaly = temperature_anomalies(
            frame,
            station,
            fit_frame=climatology_fit_frame,
            half_window_days=half_window_days,
        )
        raw = pd.to_numeric(frame[f"{station}_T"], errors="coerce")
        for label, (start, end) in periods.items():
            selected = dates.between(pd.Timestamp(start), pd.Timestamp(end))
            values = anomaly.loc[selected].dropna()
            raw_values = raw.loc[selected].dropna()
            years = sorted(set(dates.loc[selected].dt.year))
            annual_selected = annual.loc[
                annual["station_id"].eq(str(station)) & annual["year"].isin(years)
            ]
            anomaly_array = values.to_numpy(float)
            rows.append(
                {
                    "station_id": str(station),
                    "period": str(label),
                    "start_date": str(start),
                    "end_date": str(end),
                    "n_days": len(values),
                    "annual_minimum_range_degC": (
                        f"{annual_selected['annual_minimum_degC'].min():.1f}--"
                        f"{annual_selected['annual_minimum_degC'].max():.1f}"
                    ),
                    "annual_amplitude_range_degC": (
                        f"{annual_selected['annual_amplitude_degC'].min():.1f}--"
                        f"{annual_selected['annual_amplitude_degC'].max():.1f}"
                    ),
                    "median_annual_amplitude_degC": float(
                        annual_selected["annual_amplitude_degC"].median()
                    ),
                    "anomaly_mean_degC": float(values.mean()),
                    "anomaly_sd_degC": float(values.std(ddof=1)),
                    "acf30": _acf(values.reset_index(drop=True), 30),
                    "acf90": _acf(values.reset_index(drop=True), 90),
                    "anomaly_skewness": float(skew(anomaly_array, bias=False)),
                    "anomaly_excess_kurtosis": float(
                        kurtosis(anomaly_array, fisher=True, bias=False)
                    ),
                    "seasonal_variance_fraction": float(
                        1.0 - np.var(anomaly_array) / np.var(raw_values.to_numpy(float))
                    ),
                }
            )
    return pd.DataFrame(rows)


def network_regulation_fingerprint(
    train_frame: pd.DataFrame,
    stations: Sequence[str],
    *,
    half_window_days: int = 7,
    classification_gap_days: int = 30,
) -> pd.DataFrame:
    """Relate an observable memory/amplitude index to covariance-budget type."""

    annual = annual_thermal_metrics(train_frame, stations)
    rows: list[dict[str, Any]] = []
    for station in stations:
        climatology = circular_doy_climatology(
            train_frame["date"],
            train_frame[f"{station}_T"],
            half_window_days=half_window_days,
        )
        anomaly = temperature_anomalies(
            train_frame,
            station,
            fit_frame=train_frame,
            half_window_days=half_window_days,
        ).dropna()
        amplitudes = annual.loc[
            annual["station_id"].eq(str(station)), "annual_amplitude_degC"
        ]
        budget = budget_decomposition(
            train_frame,
            str(station),
            tuple(value for value in stations if str(value) != str(station)),
            [classification_gap_days],
        ).iloc[0]
        amplitude = float(amplitudes.median())
        observed = pd.to_numeric(train_frame[f"{station}_T"], errors="coerce").dropna()
        observed_range = float(observed.max() - observed.min())
        climatology_range = float(climatology.max() - climatology.min())
        acf30 = _acf(anomaly.reset_index(drop=True), 30)
        rows.append(
            {
                "station_id": str(station),
                "median_annual_amplitude_degC": amplitude,
                "training_observed_range_degC": observed_range,
                "climatology_range_degC": climatology_range,
                "anomaly_sd_degC": float(anomaly.std(ddof=1)),
                "acf30": acf30,
                "acf90": _acf(anomaly.reset_index(drop=True), 90),
                "seasonal_variance_fraction": float(
                    budget["seasonal_variance_fraction"]
                ),
                "R2_donor": float(budget["R2_donor"]),
                "memory_component_30d": float(budget["memory_component"]),
                "donor_component_30d": float(budget["donor_component"]),
                "recoverability_type": (
                    "donor_dominated"
                    if float(budget["donor_component"])
                    >= float(budget["memory_component"])
                    else "memory_dominated"
                ),
                "memory_range_index_per_degC": float(acf30 / observed_range),
                "memory_range_index_definition": (
                    "acf30_divided_by_training_period_observed_temperature_range"
                ),
            }
        )
    result = pd.DataFrame(rows)
    result["memory_range_rank_within_network"] = (
        result["memory_range_index_per_degC"]
        .rank(method="min", ascending=False)
        .astype(int)
    )
    return result


def _exact_calendar_anomaly(frame: pd.DataFrame, column: str) -> np.ndarray:
    dates = pd.to_datetime(frame["date"]).dt.strftime("%m-%d")
    values = pd.to_numeric(frame[column], errors="coerce")
    climatology = values.groupby(dates).transform("median")
    return (values - climatology).to_numpy(float)


def expanded_covariate_r2(
    fit_frame: pd.DataFrame,
    stations: Sequence[str],
) -> pd.DataFrame:
    """Compare donor-T-only and reviewer-requested expanded linear budgets."""

    rows: list[dict[str, Any]] = []
    for station in stations:
        target = _exact_calendar_anomaly(fit_frame, f"{station}_T")
        donors = [str(value) for value in stations if str(value) != str(station)]
        base_columns = [f"{donor}_T" for donor in donors]
        expanded_columns = [
            *base_columns,
            f"{station}_Ta",
            f"{station}_F",
            f"{station}_L",
            *(f"{donor}_Ta" for donor in donors),
            *(f"{donor}_F" for donor in donors),
        ]

        def r2(columns: Sequence[str], target_values: np.ndarray = target) -> float:
            missing = sorted(set(columns).difference(fit_frame.columns))
            if missing:
                raise ValueError(f"expanded covariance analysis lacks {missing}")
            design = np.column_stack(
                [_exact_calendar_anomaly(fit_frame, column) for column in columns]
            )
            valid = np.isfinite(target_values) & np.isfinite(design).all(axis=1)
            y = target_values[valid]
            x = np.column_stack([np.ones(valid.sum()), design[valid]])
            coefficients, *_ = np.linalg.lstsq(x, y, rcond=None)
            total = float(np.square(y - y.mean()).sum())
            residual = float(np.square(y - x @ coefficients).sum())
            return float(np.clip(1.0 - residual / total, 0.0, 1.0))

        base_r2 = r2(base_columns)
        expanded_r2 = r2(expanded_columns)
        rows.append(
            {
                "station_id": str(station),
                "donor_temperature_R2": base_r2,
                "expanded_covariate_R2": expanded_r2,
                "incremental_R2": expanded_r2 - base_r2,
                "donor_only_long_gap_skill": 1.0 - np.sqrt(1.0 - base_r2),
                "expanded_long_gap_skill": 1.0 - np.sqrt(1.0 - expanded_r2),
                "expanded_predictors": ";".join(expanded_columns),
            }
        )
    return pd.DataFrame(rows)


def annual_demeaned_skill_events(
    dense_predictions: pd.DataFrame,
    *,
    denominator_guard_degC: float = 0.05,
) -> pd.DataFrame:
    """Remove separate model/truth annual anomaly means before scoring skill.

    This sensitivity removes constant and slower-than-annual offsets from both
    the observed and reconstructed anomaly series.  One-day/year groups are
    consequently unidentifiable and are withheld by the denominator guard.
    """

    required = {
        "date",
        "scenario_id",
        "station_id",
        "model",
        "gap_length",
        "y_true",
        "y_pred",
        "climatology_pred",
        "anchor_id",
    }
    missing = sorted(required.difference(dense_predictions.columns))
    if missing:
        raise ValueError(f"annual-demeaned skill requires columns: {missing}")
    data = dense_predictions.copy()
    data["date"] = pd.to_datetime(data["date"])
    data["year"] = data["date"].dt.year
    if "training_seed" not in data:
        data["training_seed"] = -1
    else:
        data["training_seed"] = pd.to_numeric(
            data["training_seed"], errors="coerce"
        ).fillna(-1)
    valid = np.isfinite(
        data[["y_true", "y_pred", "climatology_pred"]].to_numpy(float)
    ).all(axis=1)
    if "quality_approved" in data:
        valid &= data["quality_approved"].fillna(False).astype(bool).to_numpy()
    if "artificial_mask" in data:
        valid &= data["artificial_mask"].fillna(False).astype(bool).to_numpy()
    data = data.loc[valid].copy()
    data["truth_anomaly"] = data["y_true"] - data["climatology_pred"]
    data["predicted_anomaly"] = data["y_pred"] - data["climatology_pred"]
    demean_groups = ["scenario_id", "model", "training_seed", "year"]
    data["truth_high_frequency"] = data["truth_anomaly"] - data.groupby(
        demean_groups, dropna=False, observed=True
    )["truth_anomaly"].transform("mean")
    data["prediction_high_frequency"] = data["predicted_anomaly"] - data.groupby(
        demean_groups, dropna=False, observed=True
    )["predicted_anomaly"].transform("mean")
    data["absolute_error"] = (
        data["truth_high_frequency"] - data["prediction_high_frequency"]
    ).abs()
    data["climatology_absolute_error"] = data["truth_high_frequency"].abs()
    unit_columns = [
        column
        for column in (
            "scenario_id",
            "station_id",
            "model",
            "training_seed",
            "mask_seed",
            "gap_length",
            "anchor_id",
            "anchor_year",
        )
        if column in data
    ]
    result = (
        data.groupby(unit_columns, dropna=False, observed=True)
        .agg(
            annual_demeaned_MAE=("absolute_error", "mean"),
            annual_demeaned_climatology_MAE=("climatology_absolute_error", "mean"),
            n_evaluated=("absolute_error", "size"),
        )
        .reset_index()
    )
    denominator = result["annual_demeaned_climatology_MAE"]
    result["annual_demeaned_skill"] = np.where(
        np.isfinite(denominator) & denominator.gt(denominator_guard_degC),
        1.0 - result["annual_demeaned_MAE"] / denominator,
        np.nan,
    )
    result["denominator_guard_degC"] = float(denominator_guard_degC)
    result["detrending_definition"] = (
        "separate_truth_and_prediction_calendar_year_anomaly_means_removed"
    )
    return result


def rescore_with_state_climatology(
    dense_predictions: pd.DataFrame,
    wide: pd.DataFrame,
    stations: Sequence[str],
    *,
    fit_start: str,
    fit_end: str,
    half_window_days: int = 7,
    denominator_guard_degC: float = 0.05,
) -> pd.DataFrame:
    """Re-score fixed predictions against a state-matched climatology."""

    fit_dates = pd.to_datetime(wide["date"])
    fit = wide.loc[
        fit_dates.between(pd.Timestamp(fit_start), pd.Timestamp(fit_end))
    ].copy()
    if fit.empty:
        raise ValueError("state-climatology fit period is empty")
    data = dense_predictions.copy()
    data["date"] = pd.to_datetime(data["date"])
    data["state_climatology_pred"] = np.nan
    for station in stations:
        climatology = circular_doy_climatology(
            fit["date"], fit[f"{station}_T"], half_window_days=half_window_days
        )
        selected = data["station_id"].astype(str).eq(str(station))
        data.loc[selected, "state_climatology_pred"] = predict_climatology(
            climatology, data.loc[selected, "date"]
        )
    data["model_absolute_error"] = (data["y_true"] - data["y_pred"]).abs()
    data["state_climatology_absolute_error"] = (
        data["y_true"] - data["state_climatology_pred"]
    ).abs()
    unit_columns = [
        column
        for column in (
            "scenario_id",
            "station_id",
            "model",
            "training_seed",
            "mask_seed",
            "gap_length",
            "anchor_id",
            "anchor_year",
        )
        if column in data
    ]
    result = (
        data.groupby(unit_columns, dropna=False, observed=True)
        .agg(
            MAE=("model_absolute_error", "mean"),
            state_climatology_MAE=("state_climatology_absolute_error", "mean"),
            n_evaluated=("model_absolute_error", "size"),
        )
        .reset_index()
    )
    denominator = result["state_climatology_MAE"]
    result["state_climatology_skill"] = np.where(
        np.isfinite(denominator) & denominator.gt(denominator_guard_degC),
        1.0 - result["MAE"] / denominator,
        np.nan,
    )
    result["climatology_fit_start"] = str(fit_start)
    result["climatology_fit_end"] = str(fit_end)
    result["climatology_half_window_days"] = int(half_window_days)
    result["post_hoc_state_control"] = True
    return result


__all__ = [
    "annual_demeaned_skill_events",
    "annual_thermal_metrics",
    "circular_doy_climatology",
    "expanded_covariate_r2",
    "network_regulation_fingerprint",
    "period_thermal_metrics",
    "predict_climatology",
    "rescore_with_state_climatology",
    "temperature_anomalies",
]
