"""Event-level evaluation built on the strict approved/artificial mask."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from .metrics import (
    boundary_jump_metrics,
    compute_metrics,
    evaluation_mask,
    flow_metrics,
    level_metrics,
    quantile_metrics,
    temperature_metrics,
)

EVENT_ID_COLUMNS = [
    "scenario_id",
    "station_id",
    "station",
    "model",
    "training_seed",
    "mask_seed",
    "target",
    "gap_length",
    "missing_rate",
    "pattern",
    "pair_id",
    "anchor_id",
    "event_id",
    "control_id",
    "catalog_role",
    "event_season",
    "season",
    "event_type",
    "event_start",
    "event_end",
    "event_length",
    "matched_control_id",
    "raw_episode_start_index",
    "raw_episode_end_index",
    "raw_episode_start_date",
    "raw_episode_end_date",
    "raw_episode_length",
    "episode_length",
    "window_start_index",
    "window_end_index",
    "window_center_index",
    "window_start_date",
    "window_end_date",
    "window_center_date",
    "window_length",
    "event_start_index",
    "event_end_index",
    "event_center_index",
    "event_start_date",
    "event_end_date",
    "event_center_date",
    "event_peak_index",
    "event_peak_date",
    "event_peak_value",
    "event_min_index",
    "event_min_date",
    "event_min_value",
    "event_intensity",
    "event_definition",
    "minimum_duration_days",
    "merge_gap_days",
    "fixed_window_length",
    "episode_component_count",
    "rising_phase_start_index",
    "rising_phase_end_index",
    "rising_phase_start_date",
    "rising_phase_end_date",
    "peak_phase_start_index",
    "peak_phase_end_index",
    "peak_phase_start_date",
    "peak_phase_end_date",
    "recession_phase_start_index",
    "recession_phase_end_index",
    "recession_phase_start_date",
    "recession_phase_end_date",
    "control_start_index",
    "control_end_index",
    "control_center_index",
    "control_start_date",
    "control_end_date",
    "control_center_date",
    "threshold",
    "threshold_quantile",
    "threshold_operator",
    "threshold_reference_split",
    "threshold_reference_scope",
    "threshold_training_samples",
    "minimum_training_samples",
    "climatology_half_window_days",
    "threshold_doy_half_window_days",
    "event_climatology_value",
    "control_context_days",
    "event_window_eligible",
    "event_left_context_available",
    "event_right_context_available",
    "analysis_eligible",
    "analysis_exclusion_reason",
    "episode_boundary_policy",
    "control_match_year_distance",
    "control_match_day_of_year_distance",
    "control_reuse_policy",
    "data_version",
    "evaluation_split",
    "source_split",
    "catalog_schema_version",
]

EVENT_METRIC_COLUMNS = [
    *EVENT_ID_COLUMNS,
    "n_evaluated",
    "MAE",
    "RMSE",
    "bias",
    "Pearson",
    "Spearman",
    "NMAE",
    "NRMSE",
    "skill",
    "boundary_jump_left",
    "boundary_jump_right",
    "coverage_90",
    "interval_width_90",
    "peak_error",
    "timing_error",
    "minimum_error",
    "minimum_timing_error",
    "event_peak_magnitude_error",
    "event_peak_timing_error_days",
    "event_minimum_magnitude_error",
    "event_minimum_timing_error_days",
]


def _metadata_value(metadata: Mapping[str, Any], name: str) -> Any:
    aliases = {
        "pattern": ("pattern", "variable_pattern", "variables"),
        "mask_seed": ("mask_seed", "seed"),
        "gap_length": ("gap_length", "gap_lengths"),
        "station_id": ("station_id", "station"),
        "station": ("station", "station_id"),
        "event_season": ("event_season", "season"),
        "season": ("season", "event_season"),
        "control_id": ("control_id", "matched_control_id"),
        "matched_control_id": ("matched_control_id", "control_id"),
        "event_start": (
            "event_start",
            "raw_episode_start_date",
            "event_start_date",
        ),
        "event_end": ("event_end", "raw_episode_end_date", "event_end_date"),
        "event_length": (
            "event_length",
            "raw_episode_length",
            "episode_length",
            "window_length",
        ),
    }
    candidates = aliases.get(name, (name,))
    for candidate in candidates:
        if candidate in metadata:
            value = metadata[candidate]
            if isinstance(value, np.ndarray):
                value = value.tolist()
            if isinstance(value, (list, tuple)) and len(value) == 1:
                return value[0]
            if name == "pattern" and isinstance(value, (list, tuple)):
                return "+".join(str(item) for item in value)
            return value
    return None


def _numeric_array(values: Sequence[float] | np.ndarray | pd.Series) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1:
        raise ValueError("event extrema inputs must be one-dimensional")
    return pd.to_numeric(pd.Series(array), errors="coerce").to_numpy(dtype=float)


def _metadata_timestamp(metadata: Mapping[str, Any], name: str) -> pd.Timestamp | None:
    value = _metadata_value(metadata, name)
    if value is None:
        return None
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(parsed) else parsed


def _metadata_index(metadata: Mapping[str, Any], name: str, *, size: int) -> int | None:
    value = _metadata_value(metadata, name)
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(numeric) or not numeric.is_integer():
        return None
    index = int(numeric)
    return index if 0 <= index < size else None


def _same_calendar_date(values: pd.DatetimeIndex, target: pd.Timestamp) -> np.ndarray:
    """Compare calendar dates without imposing a timezone convention."""

    target_date = target.date()
    return np.asarray(
        [False if pd.isna(value) else value.date() == target_date for value in values],
        dtype=bool,
    )


def _anchor_position(
    metadata: Mapping[str, Any],
    *,
    prefix: str,
    dates: pd.DatetimeIndex,
    selected: np.ndarray,
) -> int | None:
    anchor_date = _metadata_timestamp(metadata, f"{prefix}_date")
    if anchor_date is not None:
        matches = _same_calendar_date(dates, anchor_date) & selected
        if matches.any():
            return int(np.flatnonzero(matches)[0])
        return None
    index = _metadata_index(metadata, f"{prefix}_index", size=len(selected))
    return index if index is not None and selected[index] else None


def _event_scope(
    metadata: Mapping[str, Any],
    *,
    dates: pd.DatetimeIndex,
    selected: np.ndarray,
) -> np.ndarray:
    """Restrict extrema to the raw episode when catalog bounds are present."""

    scoped = selected.copy()
    start = _metadata_timestamp(metadata, "raw_episode_start_date")
    end = _metadata_timestamp(metadata, "raw_episode_end_date")
    if start is not None:
        scoped &= np.asarray(
            [
                False if pd.isna(value) else value.date() >= start.date()
                for value in dates
            ],
            dtype=bool,
        )
    if end is not None:
        scoped &= np.asarray(
            [
                False if pd.isna(value) else value.date() <= end.date()
                for value in dates
            ],
            dtype=bool,
        )
    if start is not None or end is not None:
        return scoped

    start_index = _metadata_index(
        metadata, "raw_episode_start_index", size=len(selected)
    )
    end_index = _metadata_index(metadata, "raw_episode_end_index", size=len(selected))
    if start_index is not None:
        scoped[:start_index] = False
    if end_index is not None:
        scoped[end_index + 1 :] = False
    return scoped


def _event_extrema_metrics(
    y_true: Sequence[float] | np.ndarray | pd.Series,
    y_pred: Sequence[float] | np.ndarray | pd.Series,
    quality_approved: Sequence[bool] | np.ndarray | pd.Series,
    artificial_mask: Sequence[bool] | np.ndarray | pd.Series,
    *,
    metadata: Mapping[str, Any],
    dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None,
) -> dict[str, float]:
    """Score catalog-declared maxima/minima within the evaluated raw episode.

    Magnitude errors are signed (predicted extremum minus the observed value at
    the catalog anchor); timing errors are absolute calendar-day differences.
    A matched control normally carries the paired event's anchor, which lies
    outside its mask, and therefore correctly receives ``NaN`` extrema scores.
    """

    names = {
        "peak_error": float("nan"),
        "timing_error": float("nan"),
        "minimum_error": float("nan"),
        "minimum_timing_error": float("nan"),
        "event_peak_magnitude_error": float("nan"),
        "event_peak_timing_error_days": float("nan"),
        "event_minimum_magnitude_error": float("nan"),
        "event_minimum_timing_error_days": float("nan"),
    }
    if dates is None:
        return names

    truth = _numeric_array(y_true)
    prediction = _numeric_array(y_pred)
    parsed_dates = pd.DatetimeIndex(pd.to_datetime(dates))
    if len(parsed_dates) != len(truth):
        raise ValueError("dates must align with y_true")
    selected = evaluation_mask(truth, prediction, quality_approved, artificial_mask)
    scope = _event_scope(metadata, dates=parsed_dates, selected=selected)
    positions = np.flatnonzero(scope)
    if not len(positions):
        return names

    peak_anchor = _anchor_position(
        metadata,
        prefix="event_peak",
        dates=parsed_dates,
        selected=scope,
    )
    if peak_anchor is not None and np.isfinite(truth[peak_anchor]):
        predicted_peak = positions[int(np.argmax(prediction[positions]))]
        magnitude = float(prediction[predicted_peak] - truth[peak_anchor])
        timing = abs(
            float(
                (
                    parsed_dates[predicted_peak].normalize()
                    - parsed_dates[peak_anchor].normalize()
                ).days
            )
        )
        names.update(
            {
                "peak_error": magnitude,
                "timing_error": timing,
                "event_peak_magnitude_error": magnitude,
                "event_peak_timing_error_days": timing,
            }
        )

    minimum_anchor = _anchor_position(
        metadata,
        prefix="event_min",
        dates=parsed_dates,
        selected=scope,
    )
    if minimum_anchor is not None and np.isfinite(truth[minimum_anchor]):
        predicted_minimum = positions[int(np.argmin(prediction[positions]))]
        magnitude = float(prediction[predicted_minimum] - truth[minimum_anchor])
        timing = abs(
            float(
                (
                    parsed_dates[predicted_minimum].normalize()
                    - parsed_dates[minimum_anchor].normalize()
                ).days
            )
        )
        names.update(
            {
                "minimum_error": magnitude,
                "minimum_timing_error": timing,
                "event_minimum_magnitude_error": magnitude,
                "event_minimum_timing_error_days": timing,
            }
        )
        # D4 keeps a common ``peak_error``/``timing_error`` schema across
        # event types.  For low-flow episodes the scientifically relevant
        # extremum is the catalog minimum, so use it when no peak is declared.
        if not np.isfinite(names["peak_error"]):
            names["peak_error"] = magnitude
            names["timing_error"] = timing
    return names


def compute_event_metrics(
    y_true: Sequence[float] | np.ndarray | pd.Series,
    y_pred: Sequence[float] | np.ndarray | pd.Series,
    quality_approved: Sequence[bool] | np.ndarray | pd.Series,
    artificial_mask: Sequence[bool] | np.ndarray | pd.Series,
    *,
    target: str,
    metadata: Mapping[str, Any] | None = None,
    climatology_pred: Sequence[float] | np.ndarray | pd.Series | None = None,
    dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None = None,
    quantile_predictions: Mapping[float | str, Sequence[float] | np.ndarray | pd.Series]
    | None = None,
    high_threshold: float | None = None,
    low_threshold: float | None = None,
    ecological_threshold: float | None = None,
    normalization_iqr: float | None = None,
    normalization_std: float | None = None,
) -> dict[str, Any]:
    """Evaluate one complete mask episode and return a flat result row."""

    metadata = {} if metadata is None else dict(metadata)
    target_kind = str(target).split("_")[-1].upper()
    common_kwargs = {
        "climatology_pred": climatology_pred,
        "normalization_iqr": normalization_iqr,
        "normalization_std": normalization_std,
    }
    if target_kind == "T":
        values = temperature_metrics(
            y_true,
            y_pred,
            quality_approved,
            artificial_mask,
            dates=dates,
            high_threshold=high_threshold,
            ecological_threshold=ecological_threshold,
            **common_kwargs,
        )
    elif target_kind == "F":
        values = flow_metrics(
            y_true,
            y_pred,
            quality_approved,
            artificial_mask,
            dates=dates,
            high_threshold=high_threshold,
            low_threshold=low_threshold,
            **common_kwargs,
        )
    elif target_kind == "L":
        values = level_metrics(
            y_true,
            y_pred,
            quality_approved,
            artificial_mask,
            dates=dates,
            high_threshold=high_threshold,
            **common_kwargs,
        )
    else:
        values = compute_metrics(
            y_true,
            y_pred,
            quality_approved,
            artificial_mask,
            **common_kwargs,
        )
    values.update(
        boundary_jump_metrics(y_true, y_pred, quality_approved, artificial_mask)
    )
    if quantile_predictions:
        values.update(
            quantile_metrics(
                y_true,
                quantile_predictions,
                quality_approved,
                artificial_mask,
            )
        )
    values.update(
        _event_extrema_metrics(
            y_true,
            y_pred,
            quality_approved,
            artificial_mask,
            metadata=metadata,
            dates=dates,
        )
    )

    row = {column: _metadata_value(metadata, column) for column in EVENT_ID_COLUMNS}
    row["target"] = target
    row.update(
        {
            "n_evaluated": values.pop("n", 0),
            "MAE": values.pop("mae", float("nan")),
            "RMSE": values.pop("rmse", float("nan")),
            "bias": values.pop("bias", float("nan")),
            "Pearson": values.pop("pearson", float("nan")),
            "Spearman": values.pop("spearman", float("nan")),
            "NMAE": values.pop("nmae", float("nan")),
            "NRMSE": values.pop("nrmse", float("nan")),
            "skill": values.pop("skill", float("nan")),
            "boundary_jump_left": values.pop("boundary_jump_left", float("nan")),
            "boundary_jump_right": values.pop("boundary_jump_right", float("nan")),
            "coverage_90": values.pop("coverage_90", float("nan")),
            "interval_width_90": values.pop("interval_width_90", float("nan")),
        }
    )
    row.update(values)
    return row


def event_metrics_from_frame(
    predictions: pd.DataFrame,
    *,
    truth_col: str = "y_true",
    prediction_col: str = "y_pred",
    quality_col: str = "quality_approved",
    artificial_col: str = "artificial_mask",
    date_col: str = "date",
    target_col: str = "target",
    climatology_col: str = "climatology_pred",
    group_cols: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Reduce a daily prediction table to one row per mask episode/model/target."""

    required = {truth_col, prediction_col, quality_col, artificial_col, target_col}
    missing = sorted(required - set(predictions.columns))
    if missing:
        raise KeyError(f"prediction table is missing required columns: {missing}")
    if group_cols is None:
        group_cols = [column for column in EVENT_ID_COLUMNS if column in predictions]
    else:
        group_cols = list(group_cols)

    quantile_cols = [
        column
        for column in predictions.columns
        if column.lower().startswith("q") and column[1:].isdigit()
    ]
    rows: list[dict[str, Any]] = []
    if group_cols:
        grouped = predictions.groupby(list(group_cols), dropna=False, sort=False)
        iterator = grouped
    else:
        iterator = [(None, predictions)]
    for _, group in iterator:
        if date_col in group:
            group = group.sort_values(date_col)
        metadata = {
            column: group.iloc[0][column]
            for column in predictions.columns
            if column
            in {
                *EVENT_ID_COLUMNS,
                "mask_type",
                "event_type",
                "season",
                "window_length",
                "variable_pattern",
                "seed",
                "gap_lengths",
            }
        }
        target = str(group.iloc[0][target_col])
        quantiles = {column: group[column] for column in quantile_cols}
        row = compute_event_metrics(
            group[truth_col],
            group[prediction_col],
            group[quality_col],
            group[artificial_col],
            target=target,
            metadata=metadata,
            climatology_pred=group.get(climatology_col, None),
            dates=group.get(date_col, None),
            quantile_predictions=quantiles or None,
        )
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=EVENT_METRIC_COLUMNS)
    result = pd.DataFrame(rows)
    leading = [column for column in EVENT_METRIC_COLUMNS if column in result]
    trailing = [column for column in result if column not in leading]
    return result.loc[:, [*leading, *trailing]]


evaluate_event = compute_event_metrics
evaluate_events = event_metrics_from_frame
build_event_metrics = event_metrics_from_frame


__all__ = [
    "EVENT_ID_COLUMNS",
    "EVENT_METRIC_COLUMNS",
    "build_event_metrics",
    "compute_event_metrics",
    "evaluate_event",
    "evaluate_events",
    "event_metrics_from_frame",
]
