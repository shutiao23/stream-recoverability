"""Frozen, training-referenced event episodes and matched controls.

The catalog is the single source of truth for both aggregate M7a stress masks
and episode-level M7b analyses.  Event thresholds are fitted on the training
split only; the evaluation split is used only to locate episodes and controls.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .anchors import meteorological_season

EVENT_CATALOG_SCHEMA_VERSION = "event_catalog_v2"


@dataclass(frozen=True)
class EventDefinition:
    """Immutable numerical definition of one declared M7 event."""

    target: str
    quantile: float
    operator: str
    transform: str
    threshold_reference_scope: str
    minimum_duration_days: int
    merge_gap_days: int
    fixed_window_length: int
    climatology_half_window_days: int = 0
    threshold_doy_half_window_days: int = 0
    definition: str = ""


EVENT_DEFINITIONS: dict[str, EventDefinition] = {
    "high_temperature": EventDefinition(
        target="T",
        quantile=0.90,
        operator=">=",
        transform="doy_climatology_anomaly",
        threshold_reference_scope="station_doy_window",
        minimum_duration_days=3,
        merge_gap_days=2,
        fixed_window_length=0,
        climatology_half_window_days=7,
        threshold_doy_half_window_days=15,
        definition=(
            "T minus train-only 15-day DOY-window mean climatology >= the "
            "train-only 31-day DOY-window anomaly q90 for >=3 consecutive "
            "days; qualifying episodes separated by <=2 days are merged"
        ),
    ),
    "rapid_warming": EventDefinition(
        target="T",
        quantile=0.90,
        operator=">=",
        transform="daily_difference",
        threshold_reference_scope="station_season",
        minimum_duration_days=1,
        merge_gap_days=0,
        fixed_window_length=0,
        definition=(
            "quality-approved daily T increase >= train-only station-season q90"
        ),
    ),
    "flood": EventDefinition(
        target="F",
        quantile=0.90,
        operator=">=",
        transform="identity",
        threshold_reference_scope="station_season",
        minimum_duration_days=1,
        merge_gap_days=2,
        fixed_window_length=15,
        definition=(
            "F >= train-only station-season q90; exceedance runs separated by "
            "<=2 days form one flood process; audit window is 15 days centered "
            "on the process peak"
        ),
    ),
    "low_flow": EventDefinition(
        target="F",
        quantile=0.10,
        operator="<=",
        transform="identity",
        threshold_reference_scope="station_season",
        minimum_duration_days=7,
        merge_gap_days=0,
        fixed_window_length=0,
        definition=(
            "F <= train-only station-season q10 for >=7 consecutive days; "
            "the process minimum is retained"
        ),
    ),
}


EVENT_CATALOG_COLUMNS = (
    "catalog_schema_version",
    "pair_id",
    "anchor_id",
    "event_id",
    "control_id",
    "station_id",
    "target",
    "event_type",
    "season",
    "episode_length",
    "raw_episode_length",
    "window_length",
    "episode_component_count",
    "raw_episode_start_index",
    "raw_episode_end_index",
    "raw_episode_start_date",
    "raw_episode_end_date",
    "window_start_index",
    "window_end_index",
    "window_center_index",
    "window_start_date",
    "window_end_date",
    "window_center_date",
    # Backward-compatible aliases.  They always identify the final audit window.
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
    "event_definition",
    "minimum_duration_days",
    "merge_gap_days",
    "fixed_window_length",
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
)


@dataclass(frozen=True)
class EventDayDerivation:
    """Per-day values produced from a frozen, train-only event definition."""

    measure: np.ndarray
    measure_eligible: np.ndarray
    target_eligible: np.ndarray
    condition: np.ndarray
    threshold: np.ndarray
    threshold_training_samples: np.ndarray
    climatology: np.ndarray
    definition: EventDefinition


@dataclass(frozen=True)
class EventWindow:
    """One raw process and its final audit window."""

    raw_start_index: int
    raw_end_index: int
    window_start_index: int
    window_end_index: int
    window_center_index: int
    component_count: int
    peak_index: int | None = None
    min_index: int | None = None
    rising_start_index: int | None = None
    rising_end_index: int | None = None
    recession_start_index: int | None = None
    recession_end_index: int | None = None


class EventCatalogAvailabilityError(ValueError):
    """Raised when a declared threshold, episode, or control is unavailable."""

    def __init__(self, report: Mapping[str, Any]):
        self.report = dict(report)
        super().__init__(json.dumps(self.report, ensure_ascii=False, sort_keys=True))


class EventCatalogAuditError(ValueError):
    """Raised when a stored catalog differs from deterministic regeneration."""

    def __init__(self, report: Mapping[str, Any]):
        self.report = dict(report)
        super().__init__(json.dumps(self.report, ensure_ascii=False, sort_keys=True))


def _token(value: object) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "", str(value)).upper()
    return token or "NA"


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12].upper()
    human = "-".join(_token(part) for part in parts[-3:])
    return f"{_token(prefix)}-{human}-{digest}"


def event_stress_identity(
    *,
    station_id: str,
    event_type: str,
    data_version: str,
    evaluation_split: str,
) -> tuple[str, str]:
    """Return stable event and anchor IDs for one aggregate M7a stress case."""

    parts = (data_version, evaluation_split, station_id, event_type)
    return _stable_id("M7A-STRESS", *parts), _stable_id("M7A-ANCHOR", *parts)


def _source_split(evaluation_split: str, source_split: str | None) -> str:
    if source_split is not None:
        result = str(source_split).strip()
    elif evaluation_split == "development_test":
        result = "test"
    else:
        result = str(evaluation_split).strip()
    if not result:
        raise ValueError("source_split must not be empty")
    return result


def _normalize_long(
    long_data: pd.DataFrame,
    *,
    data_version: str,
) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    required = {
        "date",
        "station_id",
        "variable",
        "value",
        "quality_approved",
        "split",
    }
    missing = sorted(required.difference(long_data.columns))
    if missing:
        raise KeyError(f"daily_long is missing required columns: {missing}")
    if long_data.empty:
        raise ValueError("daily_long is empty")
    frame = long_data.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    if frame["date"].isna().any():
        raise ValueError("daily_long contains invalid dates")
    if "data_version" in frame:
        versions = set(frame["data_version"].dropna().astype(str).unique())
        if data_version not in versions:
            raise ValueError(
                f"requested data_version {data_version!r} is absent; "
                f"available={sorted(versions)}"
            )
        frame = frame.loc[frame["data_version"].astype(str).eq(data_version)].copy()
    elif data_version != "published_v1":
        raise ValueError("unversioned input is allowed only for published_v1")
    if frame.duplicated(["date", "station_id", "variable"]).any():
        raise ValueError("daily_long contains duplicate date/station/variable rows")
    split_counts = frame.groupby("date", observed=True)["split"].nunique(dropna=False)
    if (split_counts != 1).any():
        raise ValueError("each date must have exactly one split label")
    dates = pd.DatetimeIndex(sorted(frame["date"].unique()))
    if len(dates) > 1 and not np.all(
        np.diff(dates.to_numpy(dtype="datetime64[D]")) == np.timedelta64(1, "D")
    ):
        raise ValueError("daily_long date axis must be daily-continuous")
    return frame, dates


def _definitions(
    declared_events: Mapping[str, str] | None,
) -> dict[str, EventDefinition]:
    declared = (
        {name: definition.target for name, definition in EVENT_DEFINITIONS.items()}
        if declared_events is None
        else {str(name): str(target) for name, target in declared_events.items()}
    )
    if not declared:
        raise ValueError("declared_events must not be empty")
    unknown = sorted(set(declared).difference(EVENT_DEFINITIONS))
    if unknown:
        raise ValueError(f"unsupported declared event types: {unknown}")
    mismatches = {
        name: (target, EVENT_DEFINITIONS[name].target)
        for name, target in declared.items()
        if target != EVENT_DEFINITIONS[name].target
    }
    if mismatches:
        raise ValueError(
            f"declared event targets disagree with frozen design: {mismatches}"
        )
    return {name: EVENT_DEFINITIONS[name] for name in sorted(declared)}


def _series_arrays(
    frame: pd.DataFrame,
    dates: pd.DatetimeIndex,
    *,
    station_id: str,
    target: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows = frame.loc[
        frame["station_id"].astype(str).eq(station_id)
        & frame["variable"].astype(str).eq(target)
    ].set_index("date")
    if rows.empty:
        raise EventCatalogAvailabilityError(
            {
                "reason": "missing_station_target",
                "station_id": station_id,
                "target": target,
            }
        )
    aligned = rows.reindex(dates)
    values = pd.to_numeric(aligned["value"], errors="coerce").to_numpy(dtype=float)
    quality = aligned["quality_approved"].fillna(False).astype(bool).to_numpy()
    splits = aligned["split"].fillna("").astype(str).to_numpy()
    return values, quality, splits


def _climatological_doy(dates: pd.DatetimeIndex) -> np.ndarray:
    """Map month/day to a stable 366-day calendar (leap reference year 2000)."""

    return np.asarray(
        [pd.Timestamp(2000, value.month, value.day).dayofyear for value in dates],
        dtype=int,
    )


def _circular_doy_distance(values: np.ndarray, center: int) -> np.ndarray:
    difference = np.abs(values.astype(int) - int(center))
    return np.minimum(difference, 366 - difference)


def _daily_measure(
    values: np.ndarray,
    quality: np.ndarray,
    splits: np.ndarray,
    definition: EventDefinition,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    target_eligible = quality & np.isfinite(values)
    if definition.transform == "identity":
        return values.copy(), target_eligible.copy(), target_eligible
    if definition.transform != "daily_difference":
        raise ValueError(f"unsupported direct event transform: {definition.transform}")
    measure = np.full(len(values), np.nan, dtype=float)
    measure[1:] = np.diff(values)
    adjacent = np.zeros(len(values), dtype=bool)
    adjacent[1:] = target_eligible[1:] & target_eligible[:-1]
    same_split = np.zeros(len(values), dtype=bool)
    same_split[1:] = splits[1:] == splits[:-1]
    return measure, adjacent & same_split, target_eligible


def _seasonal_threshold_arrays(
    dates: pd.DatetimeIndex,
    measure: np.ndarray,
    measure_eligible: np.ndarray,
    splits: np.ndarray,
    definition: EventDefinition,
    *,
    event_type: str,
    minimum_training_samples: int,
) -> tuple[np.ndarray, np.ndarray]:
    seasons = np.asarray(
        [meteorological_season(int(date.month)) for date in dates], dtype=object
    )
    thresholds: dict[str, float] = {}
    counts: dict[str, int] = {}
    for season in ("DJF", "MAM", "JJA", "SON"):
        selected = (
            measure_eligible
            & (splits == "train")
            & (seasons == season)
            & np.isfinite(measure)
        )
        training_values = measure[selected]
        if len(training_values) < minimum_training_samples:
            raise EventCatalogAvailabilityError(
                {
                    "reason": "insufficient_training_threshold_samples",
                    "event_type": event_type,
                    "season": season,
                    "available": len(training_values),
                    "required": minimum_training_samples,
                    "threshold_reference_split": "train",
                }
            )
        thresholds[season] = float(np.quantile(training_values, definition.quantile))
        counts[season] = len(training_values)
    return (
        np.asarray([thresholds[str(season)] for season in seasons], dtype=float),
        np.asarray([counts[str(season)] for season in seasons], dtype=int),
    )


def _high_temperature_derivation(
    dates: pd.DatetimeIndex,
    values: np.ndarray,
    quality: np.ndarray,
    splits: np.ndarray,
    *,
    source_split: str,
    minimum_training_samples: int,
) -> EventDayDerivation:
    definition = EVENT_DEFINITIONS["high_temperature"]
    target_eligible = quality & np.isfinite(values)
    training = target_eligible & (splits == "train")
    doys = _climatological_doy(dates)
    climatology_curve = np.full(367, np.nan, dtype=float)
    for doy in range(1, 367):
        selected = training & (
            _circular_doy_distance(doys, doy) <= definition.climatology_half_window_days
        )
        if int(selected.sum()) < minimum_training_samples:
            raise EventCatalogAvailabilityError(
                {
                    "reason": "insufficient_training_climatology_samples",
                    "event_type": "high_temperature",
                    "day_of_year": doy,
                    "available": int(selected.sum()),
                    "required": minimum_training_samples,
                    "threshold_reference_split": "train",
                }
            )
        climatology_curve[doy] = float(np.mean(values[selected]))
    climatology = climatology_curve[doys]
    anomaly = values - climatology
    threshold_curve = np.full(367, np.nan, dtype=float)
    count_curve = np.zeros(367, dtype=int)
    for doy in range(1, 367):
        selected = (
            training
            & np.isfinite(anomaly)
            & (
                _circular_doy_distance(doys, doy)
                <= definition.threshold_doy_half_window_days
            )
        )
        count = int(selected.sum())
        if count < minimum_training_samples:
            raise EventCatalogAvailabilityError(
                {
                    "reason": "insufficient_training_threshold_samples",
                    "event_type": "high_temperature",
                    "day_of_year": doy,
                    "available": count,
                    "required": minimum_training_samples,
                    "threshold_reference_split": "train",
                }
            )
        threshold_curve[doy] = float(
            np.quantile(anomaly[selected], definition.quantile)
        )
        count_curve[doy] = count
    threshold = threshold_curve[doys]
    threshold_samples = count_curve[doys]
    measure_eligible = target_eligible.copy()
    condition = (
        measure_eligible
        & (splits == source_split)
        & np.isfinite(anomaly)
        & (anomaly >= threshold)
    )
    return EventDayDerivation(
        measure=anomaly,
        measure_eligible=measure_eligible,
        target_eligible=target_eligible,
        condition=condition,
        threshold=threshold,
        threshold_training_samples=threshold_samples,
        climatology=climatology,
        definition=definition,
    )


def _duration_qualified_condition(
    condition: np.ndarray, minimum_duration_days: int
) -> np.ndarray:
    if minimum_duration_days <= 1:
        return condition.copy()
    qualified = np.zeros_like(condition, dtype=bool)
    indices = np.flatnonzero(condition)
    if not len(indices):
        return qualified
    start = previous = int(indices[0])
    for raw_index in (*indices[1:], None):
        index = None if raw_index is None else int(raw_index)
        if index is None or index != previous + 1:
            if previous - start + 1 >= minimum_duration_days:
                qualified[start : previous + 1] = True
            if index is None:
                break
            start = index
        previous = index
    return qualified


def _qualified_derivation(derived: EventDayDerivation) -> EventDayDerivation:
    return EventDayDerivation(
        measure=derived.measure,
        measure_eligible=derived.measure_eligible,
        target_eligible=derived.target_eligible,
        condition=_duration_qualified_condition(
            derived.condition, derived.definition.minimum_duration_days
        ),
        threshold=derived.threshold,
        threshold_training_samples=derived.threshold_training_samples,
        climatology=derived.climatology,
        definition=derived.definition,
    )


def derive_event_day_condition(
    dates: Sequence[object] | pd.DatetimeIndex,
    values: Sequence[float] | np.ndarray,
    quality: Sequence[bool] | np.ndarray,
    splits: Sequence[object] | np.ndarray,
    event_type: str,
    *,
    source_split: str,
    minimum_training_samples: int = 30,
) -> EventDayDerivation:
    """Apply the shared frozen event definition without evaluation leakage."""

    event_name = str(event_type).strip()
    if event_name not in EVENT_DEFINITIONS:
        raise ValueError(f"unsupported event type: {event_name!r}")
    if minimum_training_samples < 1:
        raise ValueError("minimum_training_samples must be positive")
    normalized_dates = pd.DatetimeIndex(pd.to_datetime(dates)).normalize()
    value_array = np.asarray(values, dtype=float)
    quality_array = np.asarray(quality)
    split_array = np.asarray(splits).astype(str)
    expected_shape = (len(normalized_dates),)
    if value_array.shape != expected_shape or split_array.shape != expected_shape:
        raise ValueError(
            "dates, values, and splits must be one-dimensional and aligned"
        )
    if quality_array.shape != expected_shape or quality_array.dtype != np.bool_:
        raise TypeError("quality must be an aligned boolean array")
    if len(normalized_dates) > 1 and not np.all(
        np.diff(normalized_dates.to_numpy(dtype="datetime64[D]"))
        == np.timedelta64(1, "D")
    ):
        raise ValueError("event dates must be daily-continuous")
    if "train" not in set(split_array) or source_split not in set(split_array):
        raise ValueError("event derivation requires train and source split rows")
    if event_name == "high_temperature":
        return _qualified_derivation(
            _high_temperature_derivation(
                normalized_dates,
                value_array,
                quality_array,
                split_array,
                source_split=source_split,
                minimum_training_samples=int(minimum_training_samples),
            )
        )
    definition = EVENT_DEFINITIONS[event_name]
    measure, measure_eligible, target_eligible = _daily_measure(
        value_array, quality_array, split_array, definition
    )
    threshold, threshold_samples = _seasonal_threshold_arrays(
        normalized_dates,
        measure,
        measure_eligible,
        split_array,
        definition,
        event_type=event_name,
        minimum_training_samples=int(minimum_training_samples),
    )
    selected = (
        measure_eligible
        & (split_array == source_split)
        & np.isfinite(measure)
        & np.isfinite(threshold)
    )
    if definition.operator == ">=":
        condition = selected & (measure >= threshold)
    elif definition.operator == "<=":
        condition = selected & (measure <= threshold)
    else:
        raise ValueError(f"unsupported threshold operator: {definition.operator}")
    return _qualified_derivation(
        EventDayDerivation(
            measure=measure,
            measure_eligible=measure_eligible,
            target_eligible=target_eligible,
            condition=condition,
            threshold=threshold,
            threshold_training_samples=threshold_samples,
            climatology=np.full(len(value_array), np.nan, dtype=float),
            definition=definition,
        )
    )


def _true_runs(condition: np.ndarray) -> list[tuple[int, int]]:
    indices = np.flatnonzero(condition)
    if not len(indices):
        return []
    runs: list[tuple[int, int]] = []
    start = previous = int(indices[0])
    for raw_index in indices[1:]:
        index = int(raw_index)
        if index != previous + 1:
            runs.append((start, previous))
            start = index
        previous = index
    runs.append((start, previous))
    return runs


def _merge_runs(
    runs: Sequence[tuple[int, int]], merge_gap_days: int
) -> list[tuple[int, int, int]]:
    if not runs:
        return []
    merged: list[tuple[int, int, int]] = []
    start, end = runs[0]
    component_count = 1
    for next_start, next_end in runs[1:]:
        gap = int(next_start) - int(end) - 1
        if gap <= merge_gap_days:
            end = next_end
            component_count += 1
        else:
            merged.append((start, end, component_count))
            start, end, component_count = next_start, next_end, 1
    merged.append((start, end, component_count))
    return merged


def _extreme_index(
    start: int,
    end: int,
    measure: np.ndarray,
    condition: np.ndarray,
    *,
    largest: bool,
    threshold: np.ndarray | None = None,
) -> int:
    indices = np.arange(start, end + 1, dtype=int)
    event_indices = indices[condition[indices]]
    selected = event_indices if len(event_indices) else indices
    values = measure[selected]
    if threshold is not None:
        values = values - threshold[selected]
    finite = np.isfinite(values)
    if not finite.any():
        raise ValueError("event process has no finite extreme value")
    selected = selected[finite]
    values = values[finite]
    position = int(np.argmax(values) if largest else np.argmin(values))
    return int(selected[position])


def extract_event_windows(
    event_condition: Sequence[bool] | np.ndarray,
    measure: Sequence[float] | np.ndarray,
    event_type: str,
    *,
    threshold: Sequence[float] | np.ndarray | None = None,
) -> tuple[EventWindow, ...]:
    """Convert day flags into frozen raw processes and final audit windows."""

    event_name = str(event_type).strip()
    if event_name not in EVENT_DEFINITIONS:
        raise ValueError(f"unsupported event type: {event_name!r}")
    definition = EVENT_DEFINITIONS[event_name]
    condition = np.asarray(event_condition)
    values = np.asarray(measure, dtype=float)
    if condition.dtype != np.bool_ or condition.ndim != 1:
        raise TypeError("event_condition must be one-dimensional and boolean")
    if values.shape != condition.shape:
        raise ValueError("measure and event_condition must be aligned")
    thresholds = None if threshold is None else np.asarray(threshold, dtype=float)
    if thresholds is not None and thresholds.shape != condition.shape:
        raise ValueError("threshold and event_condition must be aligned")
    qualified = [
        (start, end)
        for start, end in _true_runs(condition)
        if end - start + 1 >= definition.minimum_duration_days
    ]
    processes = _merge_runs(qualified, definition.merge_gap_days)
    windows: list[EventWindow] = []
    for raw_start, raw_end, components in processes:
        peak_index: int | None = None
        min_index: int | None = None
        rising_start: int | None = None
        rising_end: int | None = None
        recession_start: int | None = None
        recession_end: int | None = None
        if event_name == "low_flow":
            min_index = _extreme_index(
                raw_start, raw_end, values, condition, largest=False
            )
        else:
            peak_index = _extreme_index(
                raw_start,
                raw_end,
                values,
                condition,
                largest=True,
                threshold=thresholds if event_name == "high_temperature" else None,
            )
        if event_name == "flood":
            assert peak_index is not None
            half_window = definition.fixed_window_length // 2
            window_start = peak_index - half_window
            window_end = window_start + definition.fixed_window_length - 1
            window_center = peak_index
            if raw_start <= peak_index - 1:
                rising_start, rising_end = raw_start, peak_index - 1
            if peak_index + 1 <= raw_end:
                recession_start, recession_end = peak_index + 1, raw_end
        else:
            window_start, window_end = raw_start, raw_end
            window_center = window_start + (window_end - window_start) // 2
        windows.append(
            EventWindow(
                raw_start_index=raw_start,
                raw_end_index=raw_end,
                window_start_index=window_start,
                window_end_index=window_end,
                window_center_index=window_center,
                component_count=components,
                peak_index=peak_index,
                min_index=min_index,
                rising_start_index=rising_start,
                rising_end_index=rising_end,
                recession_start_index=recession_start,
                recession_end_index=recession_end,
            )
        )
    return tuple(windows)


def _center(start: int, length: int) -> int:
    return int(start) + (int(length) - 1) // 2


def _day_of_year_distance(first: pd.Timestamp, second: pd.Timestamp) -> int:
    first_doy = pd.Timestamp(2000, first.month, first.day).dayofyear
    second_doy = pd.Timestamp(2000, second.month, second.day).dayofyear
    difference = abs(int(first_doy) - int(second_doy))
    return min(difference, 366 - difference)


def _overlaps_forbidden(start: int, stop: int, forbidden: np.ndarray) -> bool:
    clipped_start = max(0, start)
    clipped_stop = min(len(forbidden), stop)
    return clipped_start < clipped_stop and bool(
        forbidden[clipped_start:clipped_stop].any()
    )


def _control_candidates(
    *,
    event_center: int,
    window_length: int,
    season: str,
    dates: pd.DatetimeIndex,
    target_eligible: np.ndarray,
    source_rows: np.ndarray,
    event_condition: np.ndarray,
    forbidden_event_windows: np.ndarray,
    context_days: int,
    used_windows: set[tuple[int, int]],
) -> list[tuple[tuple[int, int, int, int], int]]:
    candidates: list[tuple[tuple[int, int, int, int], int]] = []
    for start in range(len(dates) - window_length + 1):
        stop = start + window_length
        if (start, stop) in used_windows:
            continue
        if _overlaps_forbidden(start, stop, forbidden_event_windows):
            continue
        if not source_rows[start:stop].all() or not target_eligible[start:stop].all():
            continue
        if event_condition[start:stop].any():
            continue
        context_start = start - context_days
        context_stop = stop + context_days
        if context_start < 0 or context_stop > len(dates):
            continue
        if not source_rows[context_start:context_stop].all():
            continue
        if not target_eligible[context_start:context_stop].all():
            continue
        center = _center(start, window_length)
        if meteorological_season(int(dates[center].month)) != season:
            continue
        event_date = pd.Timestamp(dates[event_center])
        control_date = pd.Timestamp(dates[center])
        score = (
            abs(int(event_date.year) - int(control_date.year)),
            _day_of_year_distance(event_date, control_date),
            abs(event_center - center),
            start,
        )
        candidates.append((score, start))
    return sorted(candidates)


def _date_text(dates: pd.DatetimeIndex, index: int | None) -> str:
    if index is None:
        return ""
    # The daily-continuous contract lets boundary-censored requested windows
    # retain their intended dates even when an index falls just outside source.
    date = pd.Timestamp(dates[0]) + pd.Timedelta(days=int(index))
    return date.strftime("%Y-%m-%d")


def _optional_value(values: np.ndarray, index: int | None) -> float:
    if index is None or index < 0 or index >= len(values):
        return float("nan")
    return float(values[index])


def _context_contract(
    window: EventWindow,
    *,
    n_dates: int,
    source_rows: np.ndarray,
    target_eligible: np.ndarray,
    context_days: int,
) -> tuple[bool, bool, bool, bool, str]:
    start = window.window_start_index
    stop = window.window_end_index + 1
    in_bounds = start >= 0 and stop <= n_dates
    window_eligible = bool(
        in_bounds
        and source_rows[start:stop].all()
        and target_eligible[start:stop].all()
    )
    left_start = start - context_days
    left_available = bool(
        left_start >= 0
        and start >= 0
        and source_rows[left_start:start].all()
        and target_eligible[left_start:start].all()
    )
    right_stop = stop + context_days
    right_available = bool(
        stop <= n_dates
        and right_stop <= n_dates
        and source_rows[stop:right_stop].all()
        and target_eligible[stop:right_stop].all()
    )
    analysis_eligible = window_eligible and left_available and right_available
    reasons: list[str] = []
    if not window_eligible:
        reasons.append("event_window_not_fully_eligible")
    if not left_available:
        reasons.append("missing_left_context")
    if not right_available:
        reasons.append("missing_right_context")
    return (
        window_eligible,
        left_available,
        right_available,
        analysis_eligible,
        ";".join(reasons),
    )


def generate_event_episode_catalog(
    long_data: pd.DataFrame,
    *,
    data_version: str,
    evaluation_split: str,
    declared_events: Mapping[str, str] | None = None,
    station_ids: Sequence[str] | None = None,
    source_split: str | None = None,
    minimum_training_samples: int = 30,
    control_context_days: int = 1,
) -> pd.DataFrame:
    """Build deterministic event-process and matched-control pairs.

    High-temperature thresholds are DOY-local anomaly thresholds.  Flow and
    rapid-warming thresholds are station-season thresholds.  Every row stores
    both the raw process and the final audit window; controls use the latter's
    station, center season, and exact length and contain no event-condition day.
    """

    data_version = str(data_version).strip()
    evaluation_split = str(evaluation_split).strip()
    if not data_version or not evaluation_split:
        raise ValueError("data_version and evaluation_split must not be empty")
    if minimum_training_samples < 1:
        raise ValueError("minimum_training_samples must be positive")
    if control_context_days < 0:
        raise ValueError("control_context_days must be non-negative")
    selected_source_split = _source_split(evaluation_split, source_split)
    definitions = _definitions(declared_events)
    frame, dates = _normalize_long(long_data, data_version=data_version)
    available_splits = set(frame["split"].astype(str).unique())
    if "train" not in available_splits or selected_source_split not in available_splits:
        raise ValueError(
            "event catalog requires train and source splits; "
            f"available={sorted(available_splits)}, source={selected_source_split!r}"
        )
    present_stations = tuple(sorted(frame["station_id"].astype(str).unique()))
    stations = (
        present_stations
        if station_ids is None
        else tuple(dict.fromkeys(str(station) for station in station_ids))
    )
    unknown_stations = sorted(set(stations).difference(present_stations))
    if not stations or unknown_stations:
        raise ValueError(f"unknown or empty station selection: {unknown_stations}")

    rows: list[dict[str, Any]] = []
    for station_id in stations:
        for event_type, definition in definitions.items():
            values, quality, splits = _series_arrays(
                frame, dates, station_id=station_id, target=definition.target
            )
            derived = derive_event_day_condition(
                dates,
                values,
                quality,
                splits,
                event_type,
                source_split=selected_source_split,
                minimum_training_samples=int(minimum_training_samples),
            )
            windows = extract_event_windows(
                derived.condition,
                derived.measure,
                event_type,
                threshold=derived.threshold,
            )
            if not windows:
                raise EventCatalogAvailabilityError(
                    {
                        "reason": "no_evaluation_episodes",
                        "station_id": station_id,
                        "event_type": event_type,
                        "evaluation_split": evaluation_split,
                        "source_split": selected_source_split,
                    }
                )
            source_rows = splits == selected_source_split
            forbidden = np.zeros(len(dates), dtype=bool)
            for window in windows:
                start = max(0, window.window_start_index)
                stop = min(len(dates), window.window_end_index + 1)
                if start < stop:
                    forbidden[start:stop] = True
            used_windows: set[tuple[int, int]] = set()
            for window in windows:
                raw_start = window.raw_start_index
                raw_end = window.raw_end_index
                window_start = window.window_start_index
                window_end = window.window_end_index
                window_length = window_end - window_start + 1
                window_center = window.window_center_index
                season = meteorological_season(
                    int(pd.Timestamp(dates[window_center]).month)
                )
                (
                    event_window_eligible,
                    left_context_available,
                    right_context_available,
                    analysis_eligible,
                    exclusion_reason,
                ) = _context_contract(
                    window,
                    n_dates=len(dates),
                    source_rows=source_rows,
                    target_eligible=derived.target_eligible,
                    context_days=int(control_context_days),
                )
                candidates = _control_candidates(
                    event_center=window_center,
                    window_length=window_length,
                    season=season,
                    dates=dates,
                    target_eligible=derived.target_eligible,
                    source_rows=source_rows,
                    event_condition=derived.condition,
                    forbidden_event_windows=forbidden,
                    context_days=int(control_context_days),
                    used_windows=used_windows,
                )
                if not candidates:
                    raise EventCatalogAvailabilityError(
                        {
                            "reason": "matched_control_unavailable",
                            "station_id": station_id,
                            "event_type": event_type,
                            "season": season,
                            "window_length": window_length,
                            "raw_episode_start_date": _date_text(dates, raw_start),
                            "control_reuse_policy": (
                                "no_exact_window_reuse_within_station_event"
                            ),
                        }
                    )
                _, control_start = candidates[0]
                control_end = control_start + window_length - 1
                control_center = _center(control_start, window_length)
                used_windows.add((control_start, control_end + 1))

                peak_index = window.peak_index
                min_index = window.min_index
                anchor_index = min_index if min_index is not None else peak_index
                if anchor_index is None:
                    anchor_index = window_center
                threshold = _optional_value(derived.threshold, anchor_index)
                threshold_samples = int(
                    _optional_value(derived.threshold_training_samples, anchor_index)
                )
                if peak_index is not None:
                    raw_peak_value = _optional_value(values, peak_index)
                    if event_type in {"high_temperature", "rapid_warming"}:
                        peak_measure = _optional_value(derived.measure, peak_index)
                    else:
                        peak_measure = raw_peak_value
                    intensity = peak_measure - threshold
                else:
                    raw_peak_value = float("nan")
                    minimum_value = _optional_value(values, min_index)
                    intensity = threshold - minimum_value
                minimum_value = _optional_value(values, min_index)
                raw_start_date = _date_text(dates, raw_start)
                raw_end_date = _date_text(dates, raw_end)
                window_start_date = _date_text(dates, window_start)
                window_end_date = _date_text(dates, window_end)
                control_start_date = _date_text(dates, control_start)
                control_end_date = _date_text(dates, control_end)
                identity = (
                    data_version,
                    evaluation_split,
                    station_id,
                    event_type,
                    raw_start_date,
                    raw_end_date,
                    window_start_date,
                    window_end_date,
                )
                event_id = _stable_id("M7B-EVENT", *identity)
                control_id = _stable_id(
                    "M7B-CONTROL", *identity, control_start_date, control_end_date
                )
                pair_id = _stable_id("M7B-PAIR", event_id, control_id)
                anchor_id = _stable_id("M7B-ANCHOR", event_id, control_id)

                rising_start = window.rising_start_index
                rising_end = window.rising_end_index
                recession_start = window.recession_start_index
                recession_end = window.recession_end_index
                rows.append(
                    {
                        "catalog_schema_version": EVENT_CATALOG_SCHEMA_VERSION,
                        "pair_id": pair_id,
                        "anchor_id": anchor_id,
                        "event_id": event_id,
                        "control_id": control_id,
                        "station_id": station_id,
                        "target": definition.target,
                        "event_type": event_type,
                        "season": season,
                        "episode_length": window_length,
                        "raw_episode_length": raw_end - raw_start + 1,
                        "window_length": window_length,
                        "episode_component_count": window.component_count,
                        "raw_episode_start_index": raw_start,
                        "raw_episode_end_index": raw_end,
                        "raw_episode_start_date": raw_start_date,
                        "raw_episode_end_date": raw_end_date,
                        "window_start_index": window_start,
                        "window_end_index": window_end,
                        "window_center_index": window_center,
                        "window_start_date": window_start_date,
                        "window_end_date": window_end_date,
                        "window_center_date": _date_text(dates, window_center),
                        "event_start_index": window_start,
                        "event_end_index": window_end,
                        "event_center_index": window_center,
                        "event_start_date": window_start_date,
                        "event_end_date": window_end_date,
                        "event_center_date": _date_text(dates, window_center),
                        "event_peak_index": peak_index,
                        "event_peak_date": _date_text(dates, peak_index),
                        "event_peak_value": raw_peak_value,
                        "event_min_index": min_index,
                        "event_min_date": _date_text(dates, min_index),
                        "event_min_value": minimum_value,
                        "event_intensity": float(intensity),
                        "rising_phase_start_index": rising_start,
                        "rising_phase_end_index": rising_end,
                        "rising_phase_start_date": _date_text(dates, rising_start),
                        "rising_phase_end_date": _date_text(dates, rising_end),
                        "peak_phase_start_index": peak_index
                        if event_type == "flood"
                        else None,
                        "peak_phase_end_index": peak_index
                        if event_type == "flood"
                        else None,
                        "peak_phase_start_date": (
                            _date_text(dates, peak_index)
                            if event_type == "flood"
                            else ""
                        ),
                        "peak_phase_end_date": (
                            _date_text(dates, peak_index)
                            if event_type == "flood"
                            else ""
                        ),
                        "recession_phase_start_index": recession_start,
                        "recession_phase_end_index": recession_end,
                        "recession_phase_start_date": _date_text(
                            dates, recession_start
                        ),
                        "recession_phase_end_date": _date_text(dates, recession_end),
                        "control_start_index": control_start,
                        "control_end_index": control_end,
                        "control_center_index": control_center,
                        "control_start_date": control_start_date,
                        "control_end_date": control_end_date,
                        "control_center_date": _date_text(dates, control_center),
                        "threshold": threshold,
                        "threshold_quantile": definition.quantile,
                        "threshold_operator": definition.operator,
                        "threshold_reference_split": "train",
                        "threshold_reference_scope": (
                            definition.threshold_reference_scope
                        ),
                        "threshold_training_samples": threshold_samples,
                        "minimum_training_samples": int(minimum_training_samples),
                        "event_definition": definition.definition,
                        "minimum_duration_days": definition.minimum_duration_days,
                        "merge_gap_days": definition.merge_gap_days,
                        "fixed_window_length": definition.fixed_window_length,
                        "climatology_half_window_days": (
                            definition.climatology_half_window_days
                        ),
                        "threshold_doy_half_window_days": (
                            definition.threshold_doy_half_window_days
                        ),
                        "event_climatology_value": _optional_value(
                            derived.climatology, anchor_index
                        ),
                        "control_context_days": int(control_context_days),
                        "event_window_eligible": event_window_eligible,
                        "event_left_context_available": left_context_available,
                        "event_right_context_available": right_context_available,
                        "analysis_eligible": analysis_eligible,
                        "analysis_exclusion_reason": exclusion_reason,
                        "episode_boundary_policy": (
                            "catalog_all_analyze_only_complete_window_and_context"
                        ),
                        "control_match_year_distance": abs(
                            int(dates[window_center].year)
                            - int(dates[control_center].year)
                        ),
                        "control_match_day_of_year_distance": _day_of_year_distance(
                            pd.Timestamp(dates[window_center]),
                            pd.Timestamp(dates[control_center]),
                        ),
                        "control_reuse_policy": (
                            "no_exact_window_reuse_within_station_event"
                        ),
                        "data_version": data_version,
                        "evaluation_split": evaluation_split,
                        "source_split": selected_source_split,
                    }
                )
    if not rows:
        raise EventCatalogAvailabilityError({"reason": "empty_event_catalog"})
    return validate_event_episode_catalog(pd.DataFrame(rows))


_REQUIRED_INTEGER_COLUMNS = (
    "episode_length",
    "raw_episode_length",
    "window_length",
    "episode_component_count",
    "raw_episode_start_index",
    "raw_episode_end_index",
    "window_start_index",
    "window_end_index",
    "window_center_index",
    "event_start_index",
    "event_end_index",
    "event_center_index",
    "control_start_index",
    "control_end_index",
    "control_center_index",
    "threshold_training_samples",
    "minimum_training_samples",
    "minimum_duration_days",
    "merge_gap_days",
    "fixed_window_length",
    "climatology_half_window_days",
    "threshold_doy_half_window_days",
    "control_context_days",
    "control_match_year_distance",
    "control_match_day_of_year_distance",
)
_OPTIONAL_INTEGER_COLUMNS = (
    "event_peak_index",
    "event_min_index",
    "rising_phase_start_index",
    "rising_phase_end_index",
    "peak_phase_start_index",
    "peak_phase_end_index",
    "recession_phase_start_index",
    "recession_phase_end_index",
)
_BOOLEAN_COLUMNS = (
    "event_window_eligible",
    "event_left_context_available",
    "event_right_context_available",
    "analysis_eligible",
)
_OPTIONAL_DATE_COLUMNS = (
    "event_peak_date",
    "event_min_date",
    "rising_phase_start_date",
    "rising_phase_end_date",
    "peak_phase_start_date",
    "peak_phase_end_date",
    "recession_phase_start_date",
    "recession_phase_end_date",
)


def _normalize_boolean(series: pd.Series, column: str) -> pd.Series:
    if series.dtype == bool:
        return series.astype(bool)
    mapped = (
        series.astype(str).str.strip().str.lower().map({"true": True, "false": False})
    )
    if mapped.isna().any():
        raise ValueError(f"event catalog requires boolean {column}")
    return mapped.astype(bool)


def validate_event_episode_catalog(catalog: pd.DataFrame) -> pd.DataFrame:
    """Normalize and strictly validate the paired event-catalog schema."""

    missing = sorted(set(EVENT_CATALOG_COLUMNS).difference(catalog.columns))
    extra = sorted(set(catalog.columns).difference(EVENT_CATALOG_COLUMNS))
    if missing or extra:
        raise ValueError(
            f"event catalog schema mismatch: missing={missing}, extra={extra}"
        )
    if catalog.empty:
        raise ValueError("event catalog is empty")
    result = catalog.loc[:, EVENT_CATALOG_COLUMNS].copy()
    if (
        not result["catalog_schema_version"]
        .astype(str)
        .eq(EVENT_CATALOG_SCHEMA_VERSION)
        .all()
    ):
        raise ValueError("event catalog schema version mismatch")
    for column in ("pair_id", "anchor_id", "event_id", "control_id"):
        if (
            result[column].isna().any()
            or result[column].astype(str).str.strip().eq("").any()
        ):
            raise ValueError(f"event catalog contains empty {column}")
        if result[column].astype(str).duplicated().any():
            raise ValueError(f"event catalog contains duplicate {column}")
    for column in _REQUIRED_INTEGER_COLUMNS:
        numeric = pd.to_numeric(result[column], errors="coerce")
        if numeric.isna().any() or not np.equal(numeric, np.floor(numeric)).all():
            raise ValueError(f"event catalog requires integer {column}")
        result[column] = numeric.astype(int)
    for column in _OPTIONAL_INTEGER_COLUMNS:
        numeric = pd.to_numeric(result[column], errors="coerce")
        present = numeric.notna()
        if not np.equal(numeric[present], np.floor(numeric[present])).all():
            raise ValueError(f"event catalog requires integer-or-empty {column}")
        result[column] = numeric.astype(float)
    for column in _BOOLEAN_COLUMNS:
        result[column] = _normalize_boolean(result[column], column)
    if (
        (result[["episode_length", "raw_episode_length", "window_length"]] <= 0)
        .any()
        .any()
    ):
        raise ValueError("event and window lengths must be positive")
    if not result["episode_length"].eq(result["window_length"]).all():
        raise ValueError("episode_length must alias window_length")
    for column in (
        "threshold",
        "threshold_quantile",
        "event_peak_value",
        "event_min_value",
        "event_intensity",
        "event_climatology_value",
    ):
        result[column] = pd.to_numeric(result[column], errors="coerce").astype(float)
    if (
        not np.isfinite(result["threshold"]).all()
        or not np.isfinite(result["threshold_quantile"]).all()
    ):
        raise ValueError("event catalog thresholds must be finite")
    if not np.isfinite(result["event_intensity"]).all():
        raise ValueError("event intensity must be finite")
    if (result["event_intensity"] < -1e-12).any():
        raise ValueError("event intensity must be non-negative")
    if not result["threshold_reference_split"].astype(str).eq("train").all():
        raise ValueError("event thresholds must reference train only")

    required_dates = (
        "raw_episode_start_date",
        "raw_episode_end_date",
        "window_start_date",
        "window_end_date",
        "window_center_date",
        "event_start_date",
        "event_end_date",
        "event_center_date",
        "control_start_date",
        "control_end_date",
        "control_center_date",
    )
    for column in required_dates:
        parsed = pd.to_datetime(result[column], errors="coerce")
        if parsed.isna().any():
            raise ValueError(f"event catalog contains invalid {column}")
        result[column] = parsed.dt.strftime("%Y-%m-%d")
    for column in _OPTIONAL_DATE_COLUMNS:
        values = result[column].fillna("").astype(str).str.strip()
        present = values.ne("")
        parsed = pd.to_datetime(values.where(present), errors="coerce")
        if parsed[present].isna().any():
            raise ValueError(f"event catalog contains invalid {column}")
        result[column] = ""
        result.loc[present, column] = parsed.loc[present].dt.strftime("%Y-%m-%d")

    expected_raw_length = (
        result["raw_episode_end_index"] - result["raw_episode_start_index"] + 1
    )
    expected_window_length = (
        result["window_end_index"] - result["window_start_index"] + 1
    )
    expected_control_length = (
        result["control_end_index"] - result["control_start_index"] + 1
    )
    if not expected_raw_length.eq(result["raw_episode_length"]).all():
        raise ValueError("raw episode indices disagree with raw_episode_length")
    if not expected_window_length.eq(result["window_length"]).all():
        raise ValueError("window indices disagree with window_length")
    if not expected_control_length.eq(result["window_length"]).all():
        raise ValueError("control indices disagree with window_length")
    expected_center = result["window_start_index"] + (result["window_length"] - 1) // 2
    expected_control_center = (
        result["control_start_index"] + (result["window_length"] - 1) // 2
    )
    if not expected_center.eq(result["window_center_index"]).all():
        raise ValueError("window center index is inconsistent")
    if not expected_control_center.eq(result["control_center_index"]).all():
        raise ValueError("control center index is inconsistent")
    for suffix in ("start_index", "end_index", "center_index"):
        if not result[f"event_{suffix}"].eq(result[f"window_{suffix}"]).all():
            raise ValueError(f"event_{suffix} must alias window_{suffix}")
    for suffix in ("start_date", "end_date", "center_date"):
        if not result[f"event_{suffix}"].eq(result[f"window_{suffix}"]).all():
            raise ValueError(f"event_{suffix} must alias window_{suffix}")

    event_season = pd.to_datetime(result["window_center_date"]).dt.month.map(
        meteorological_season
    )
    control_season = pd.to_datetime(result["control_center_date"]).dt.month.map(
        meteorological_season
    )
    if (
        not result["season"].astype(str).eq(event_season).all()
        or not result["season"].astype(str).eq(control_season).all()
    ):
        raise ValueError("event and control centers must have the declared same season")
    if not result["threshold_operator"].isin([">=", "<="]).all():
        raise ValueError("event catalog contains an invalid threshold operator")
    if (
        not result["control_reuse_policy"]
        .astype(str)
        .eq("no_exact_window_reuse_within_station_event")
        .all()
    ):
        raise ValueError("event catalog control reuse policy mismatch")
    if (
        not result["episode_boundary_policy"]
        .astype(str)
        .eq("catalog_all_analyze_only_complete_window_and_context")
        .all()
    ):
        raise ValueError("event catalog boundary policy mismatch")
    expected_eligible = (
        result["event_window_eligible"]
        & result["event_left_context_available"]
        & result["event_right_context_available"]
    )
    if not result["analysis_eligible"].eq(expected_eligible).all():
        raise ValueError("analysis_eligible disagrees with window/context availability")
    result["analysis_exclusion_reason"] = (
        result["analysis_exclusion_reason"].fillna("").astype(str)
    )
    if (
        not result.loc[result["analysis_eligible"], "analysis_exclusion_reason"]
        .eq("")
        .all()
    ):
        raise ValueError("eligible episodes cannot have exclusion reasons")
    if (
        result.loc[~result["analysis_eligible"], "analysis_exclusion_reason"]
        .eq("")
        .any()
    ):
        raise ValueError("excluded episodes require exclusion reasons")
    if (result["event_start_index"] == result["control_start_index"]).any():
        raise ValueError("an event window cannot be its own matched control")

    for event_type, definition in EVENT_DEFINITIONS.items():
        selected = result["event_type"].astype(str).eq(event_type)
        if not selected.any():
            continue
        expected_values = {
            "target": definition.target,
            "threshold_quantile": definition.quantile,
            "threshold_operator": definition.operator,
            "threshold_reference_scope": definition.threshold_reference_scope,
            "event_definition": definition.definition,
            "minimum_duration_days": definition.minimum_duration_days,
            "merge_gap_days": definition.merge_gap_days,
            "fixed_window_length": definition.fixed_window_length,
            "climatology_half_window_days": definition.climatology_half_window_days,
            "threshold_doy_half_window_days": definition.threshold_doy_half_window_days,
        }
        for column, expected in expected_values.items():
            if not result.loc[selected, column].eq(expected).all():
                raise ValueError(f"{event_type} catalog rows violate frozen {column}")
    unknown_events = sorted(
        set(result["event_type"].astype(str)).difference(EVENT_DEFINITIONS)
    )
    if unknown_events:
        raise ValueError(
            f"event catalog contains unsupported event types: {unknown_events}"
        )
    flood = result["event_type"].astype(str).eq("flood")
    if flood.any():
        if (
            not result.loc[flood, "window_length"]
            .eq(EVENT_DEFINITIONS["flood"].fixed_window_length)
            .all()
        ):
            raise ValueError("flood audit windows must have the frozen fixed length")
        peak = pd.to_numeric(result.loc[flood, "event_peak_index"], errors="coerce")
        if (
            peak.isna().any()
            or not peak.astype(int).eq(result.loc[flood, "window_center_index"]).all()
        ):
            raise ValueError("flood audit windows must be centered on event peak")
    low = result["event_type"].astype(str).eq("low_flow")
    if low.any() and result.loc[low, "event_min_index"].isna().any():
        raise ValueError("low-flow rows must record the process minimum")

    result = result.sort_values(
        ["station_id", "event_type", "raw_episode_start_index", "event_id"],
        kind="mergesort",
        ignore_index=True,
    )
    return result.loc[:, EVENT_CATALOG_COLUMNS]


def load_event_episode_catalog(
    path: str | Path,
    *,
    expected_data_version: str | None = None,
    expected_evaluation_split: str | None = None,
) -> pd.DataFrame:
    """Load a catalog and reject identity-contract mismatches."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    catalog = validate_event_episode_catalog(pd.read_csv(source))
    versions = tuple(sorted(catalog["data_version"].astype(str).unique()))
    splits = tuple(sorted(catalog["evaluation_split"].astype(str).unique()))
    if len(versions) != 1 or len(splits) != 1:
        raise ValueError(
            "one event catalog cannot mix data versions or evaluation splits"
        )
    if expected_data_version is not None and versions != (expected_data_version,):
        raise ValueError(
            f"event catalog data_version mismatch: {versions[0]!r} != "
            f"{expected_data_version!r}"
        )
    if expected_evaluation_split is not None and splits != (expected_evaluation_split,):
        raise ValueError(
            f"event catalog evaluation_split mismatch: {splits[0]!r} != "
            f"{expected_evaluation_split!r}"
        )
    return catalog


def event_catalog_sha256(catalog: pd.DataFrame) -> str:
    """Return a row-order-independent digest of the canonical catalog."""

    canonical = validate_event_episode_catalog(catalog)
    records = canonical.to_dict(orient="records")
    payload = json.dumps(
        records, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def audit_event_episode_catalog(
    catalog: pd.DataFrame,
    long_data: pd.DataFrame,
) -> dict[str, Any]:
    """Regenerate and compare a stored catalog to its exact source contract."""

    try:
        actual = validate_event_episode_catalog(catalog)
        data_versions = tuple(sorted(actual["data_version"].astype(str).unique()))
        evaluation_splits = tuple(
            sorted(actual["evaluation_split"].astype(str).unique())
        )
        source_splits = tuple(sorted(actual["source_split"].astype(str).unique()))
        minimum_samples = tuple(sorted(actual["minimum_training_samples"].unique()))
        contexts = tuple(sorted(actual["control_context_days"].unique()))
        if not (
            len(data_versions)
            == len(evaluation_splits)
            == len(source_splits)
            == len(minimum_samples)
            == len(contexts)
            == 1
        ):
            raise ValueError("catalog mixes generation-contract values")
        definitions = {
            str(row.event_type): str(row.target)
            for row in actual[["event_type", "target"]]
            .drop_duplicates()
            .itertuples(index=False)
        }
        expected = generate_event_episode_catalog(
            long_data,
            data_version=data_versions[0],
            evaluation_split=evaluation_splits[0],
            declared_events=definitions,
            station_ids=tuple(sorted(actual["station_id"].astype(str).unique())),
            source_split=source_splits[0],
            minimum_training_samples=int(minimum_samples[0]),
            control_context_days=int(contexts[0]),
        )
        pd.testing.assert_frame_equal(
            actual,
            expected,
            check_dtype=False,
            check_exact=False,
            rtol=1e-12,
            atol=1e-12,
        )
    except Exception as error:
        report = {
            "status": "failed",
            "catalog_schema_version": EVENT_CATALOG_SCHEMA_VERSION,
            "reason": str(error),
        }
        raise EventCatalogAuditError(report) from error

    group_counts = (
        actual.groupby(["station_id", "event_type", "season"], observed=True)
        .size()
        .rename("episode_count")
        .reset_index()
        .to_dict(orient="records")
    )
    return {
        "status": "passed",
        "catalog_schema_version": EVENT_CATALOG_SCHEMA_VERSION,
        "catalog_sha256": event_catalog_sha256(actual),
        "episode_pair_count": len(actual),
        "event_id_count": int(actual["event_id"].nunique()),
        "control_id_count": int(actual["control_id"].nunique()),
        "anchor_id_count": int(actual["anchor_id"].nunique()),
        "analysis_eligible_episode_count": int(actual["analysis_eligible"].sum()),
        "boundary_excluded_episode_count": int((~actual["analysis_eligible"]).sum()),
        "threshold_reference_split": "train",
        "threshold_reference_scopes": sorted(
            actual["threshold_reference_scope"].astype(str).unique()
        ),
        "control_rule": "same_station_same_season_same_window_length_non_event",
        "group_counts": group_counts,
        "data_version": str(actual["data_version"].iloc[0]),
        "evaluation_split": str(actual["evaluation_split"].iloc[0]),
        "source_split": str(actual["source_split"].iloc[0]),
    }


__all__ = [
    "EVENT_CATALOG_COLUMNS",
    "EVENT_CATALOG_SCHEMA_VERSION",
    "EVENT_DEFINITIONS",
    "EventCatalogAuditError",
    "EventCatalogAvailabilityError",
    "EventDayDerivation",
    "EventDefinition",
    "EventWindow",
    "audit_event_episode_catalog",
    "derive_event_day_condition",
    "event_catalog_sha256",
    "event_stress_identity",
    "extract_event_windows",
    "generate_event_episode_catalog",
    "load_event_episode_catalog",
    "validate_event_episode_catalog",
]
