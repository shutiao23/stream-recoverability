"""Deterministic, season-balanced anchors for nested frontier gaps."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

import numpy as np
import pandas as pd

from ._common import centered_bounds, stable_scenario_id, valid_block_starts

FRONTIER_SEASONS = ("DJF", "MAM", "JJA", "SON")
FRONTIER_MASK_SEEDS = tuple(range(101, 121))
FRONTIER_ANCHOR_COLUMNS = (
    "anchor_id",
    "station_id",
    "target",
    "center_date",
    "center_index",
    "start_month",
    "season",
    "year",
    "hydrologic_state",
    "mask_seed",
    "max_supported_length",
    "data_version",
    "evaluation_split",
    "source_split",
)

_SOURCE_SPLIT_BY_EVALUATION = {
    "development_test": "test",
    "validation": "validation",
    "confirmatory": "confirmatory",
    "test": "test",
}


class AnchorAvailabilityError(ValueError):
    """Raised when any station-target-season cannot meet its anchor quota."""

    def __init__(self, report: pd.DataFrame):
        self.report = report.reset_index(drop=True)
        failures = self.report.loc[self.report["shortfall"] > 0]
        detail = failures.to_string(index=False)
        super().__init__(f"frontier anchor quota is unavailable:\n{detail}")


def meteorological_season(month: int) -> str:
    """Return the conventional three-letter meteorological season."""

    if month in (12, 1, 2):
        return "DJF"
    if month in (3, 4, 5):
        return "MAM"
    if month in (6, 7, 8):
        return "JJA"
    if month in (9, 10, 11):
        return "SON"
    raise ValueError("month must be in 1..12")


def _stable_rng(*parts: object) -> np.random.Generator:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(payload).digest()[:8], "little")
    return np.random.default_rng(seed)


def _normalize_frame(
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
        available_versions = set(frame["data_version"].dropna().astype(str).unique())
        if data_version not in available_versions:
            raise ValueError(
                f"requested data_version {data_version!r} is absent; "
                f"available: {sorted(available_versions)}"
            )
        frame = frame.loc[frame["data_version"].astype(str) == data_version].copy()
    elif data_version != "published_v1":
        raise ValueError(
            "unversioned daily_long can only be used as the published_v1 source"
        )

    if frame.duplicated(["date", "station_id", "variable"]).any():
        raise ValueError(
            "daily_long contains duplicate date/station/variable rows for the requested version"
        )
    split_counts = frame.groupby("date", observed=True)["split"].nunique(dropna=False)
    if (split_counts != 1).any():
        raise ValueError("each date must have exactly one evaluation split")
    if frame["quality_approved"].isna().any():
        raise ValueError("quality_approved must not contain missing values")

    dates = pd.DatetimeIndex(sorted(frame["date"].unique()))
    if len(dates) > 1 and not np.all(
        np.diff(dates.to_numpy(dtype="datetime64[D]")) == np.timedelta64(1, "D")
    ):
        raise ValueError("daily_long date axis must be daily-continuous")
    return frame, dates


def _eligible_centers(
    frame: pd.DataFrame,
    dates: pd.DatetimeIndex,
    *,
    station_id: str,
    target: str,
    evaluation_split: str,
    max_supported_length: int,
) -> np.ndarray:
    rows = frame.loc[
        frame["station_id"].astype(str).eq(station_id)
        & frame["variable"].astype(str).eq(target)
    ].set_index("date")
    eligible = np.zeros(len(dates), dtype=bool)
    if not rows.empty:
        aligned = rows.reindex(dates)
        values = pd.to_numeric(aligned["value"], errors="coerce")
        eligible = (
            aligned["quality_approved"].fillna(False).astype(bool)
            & aligned["split"].astype(str).eq(evaluation_split)
            & values.notna()
            & np.isfinite(values)
        ).to_numpy(dtype=bool)
    starts = valid_block_starts(eligible, max_supported_length)
    return starts + (max_supported_length - 1) // 2


def _flow_reference(
    frame: pd.DataFrame,
) -> tuple[
    dict[tuple[str, pd.Timestamp], float],
    dict[tuple[str, str], tuple[float, float]],
    dict[str, tuple[float, float]],
]:
    flow = frame.loc[frame["variable"].astype(str).eq("F")].copy()
    flow["numeric_value"] = pd.to_numeric(flow["value"], errors="coerce")
    eligible = (
        flow["quality_approved"].fillna(False).astype(bool)
        & flow["numeric_value"].notna()
        & np.isfinite(flow["numeric_value"])
    )
    flow = flow.loc[eligible]
    lookup = {
        (str(row.station_id), pd.Timestamp(row.date)): float(row.numeric_value)
        for row in flow.itertuples(index=False)
    }
    training = flow.loc[flow["split"].astype(str).eq("train")].copy()
    training["season"] = training["date"].dt.month.map(meteorological_season)

    seasonal: dict[tuple[str, str], tuple[float, float]] = {}
    for (station_id, season), group in training.groupby(
        ["station_id", "season"], observed=True
    ):
        if len(group) >= 3:
            quantiles = group["numeric_value"].quantile([1 / 3, 2 / 3])
            seasonal[(str(station_id), str(season))] = (
                float(quantiles.iloc[0]),
                float(quantiles.iloc[1]),
            )
    global_thresholds: dict[str, tuple[float, float]] = {}
    for station_id, group in training.groupby("station_id", observed=True):
        if len(group) >= 3:
            quantiles = group["numeric_value"].quantile([1 / 3, 2 / 3])
            global_thresholds[str(station_id)] = (
                float(quantiles.iloc[0]),
                float(quantiles.iloc[1]),
            )
    return lookup, seasonal, global_thresholds


def _hydrologic_state(
    station_id: str,
    center_date: pd.Timestamp,
    season: str,
    flow_lookup: dict[tuple[str, pd.Timestamp], float],
    seasonal_thresholds: dict[tuple[str, str], tuple[float, float]],
    global_thresholds: dict[str, tuple[float, float]],
) -> str:
    value = flow_lookup.get((station_id, center_date))
    thresholds = seasonal_thresholds.get(
        (station_id, season), global_thresholds.get(station_id)
    )
    if value is None or thresholds is None:
        return "unknown"
    lower, upper = thresholds
    if value <= lower:
        return "low_flow"
    if value >= upper:
        return "high_flow"
    return "normal_flow"


def _validate_parameters(
    *,
    max_supported_length: int,
    anchors_per_season: int,
    mask_seeds: Sequence[int],
) -> tuple[int, int, tuple[int, ...]]:
    if isinstance(max_supported_length, (bool, np.bool_)) or not isinstance(
        max_supported_length, (int, np.integer)
    ):
        raise TypeError("max_supported_length must be an integer")
    if isinstance(anchors_per_season, (bool, np.bool_)) or not isinstance(
        anchors_per_season, (int, np.integer)
    ):
        raise TypeError("anchors_per_season must be an integer")
    max_supported_length = int(max_supported_length)
    anchors_per_season = int(anchors_per_season)
    if max_supported_length <= 0:
        raise ValueError("max_supported_length must be positive")
    if anchors_per_season <= 0:
        raise ValueError("anchors_per_season must be positive")
    seeds = tuple(int(seed) for seed in mask_seeds)
    expected = len(FRONTIER_SEASONS) * anchors_per_season
    if len(seeds) != expected or len(set(seeds)) != len(seeds):
        raise ValueError(
            f"mask_seeds must contain exactly {expected} unique values "
            f"({anchors_per_season} per season)"
        )
    if any(seed < 0 for seed in seeds):
        raise ValueError("mask_seeds must be non-negative")
    return max_supported_length, anchors_per_season, seeds


def generate_frontier_anchor_catalog(
    long_data: pd.DataFrame,
    *,
    evaluation_split: str,
    data_version: str,
    source_split: str | None = None,
    targets: Sequence[str] = ("T", "F", "L"),
    station_ids: Sequence[str] | None = None,
    max_supported_length: int = 365,
    anchors_per_season: int = 5,
    mask_seeds: Sequence[int] = FRONTIER_MASK_SEEDS,
) -> pd.DataFrame:
    """Build fixed station-target anchors with exact seasonal quotas.

    Candidate centers are admitted only when every target value in the centered
    maximum-length block is quality-approved, finite, and inside ``source_split``.
    ``evaluation_split`` is the evidence-facing label, so the historical stored
    label ``test`` can be recorded honestly as ``development_test``. Selection
    never depends on the target values themselves.
    Hydrologic-state labels are descriptive and use station/season discharge
    tertiles fitted on training rows, with a station-wide fallback.
    """

    max_supported_length, anchors_per_season, seeds = _validate_parameters(
        max_supported_length=max_supported_length,
        anchors_per_season=anchors_per_season,
        mask_seeds=mask_seeds,
    )
    evaluation_split = str(evaluation_split).strip()
    if not evaluation_split:
        raise ValueError("evaluation_split must be non-empty")
    if source_split is None:
        try:
            source_split = _SOURCE_SPLIT_BY_EVALUATION[evaluation_split]
        except KeyError as error:
            raise ValueError(
                "source_split is required for an unknown evaluation_split label"
            ) from error
    source_split = str(source_split).strip()
    if not source_split:
        raise ValueError("source_split must be non-empty")
    data_version = str(data_version).strip()
    if not data_version:
        raise ValueError("data_version must be non-empty")
    target_names = tuple(dict.fromkeys(str(target) for target in targets))
    if not target_names:
        raise ValueError("targets must not be empty")

    frame, dates = _normalize_frame(long_data, data_version=data_version)
    present_splits = set(frame["split"].astype(str).unique())
    if source_split not in present_splits:
        raise ValueError(
            f"source_split {source_split!r} is absent; available: {sorted(present_splits)}"
        )
    stations = (
        tuple(sorted(str(value) for value in frame["station_id"].unique()))
        if station_ids is None
        else tuple(dict.fromkeys(str(value) for value in station_ids))
    )
    if not stations:
        raise ValueError("station_ids must not be empty")

    centers_by_group: dict[tuple[str, str, str], np.ndarray] = {}
    availability_rows: list[dict[str, object]] = []
    for station_id in stations:
        for target in target_names:
            centers = _eligible_centers(
                frame,
                dates,
                station_id=station_id,
                target=target,
                evaluation_split=source_split,
                max_supported_length=max_supported_length,
            )
            center_seasons = np.array(
                [meteorological_season(dates[int(index)].month) for index in centers],
                dtype=object,
            )
            for season in FRONTIER_SEASONS:
                seasonal_centers = centers[center_seasons == season]
                centers_by_group[(station_id, target, season)] = seasonal_centers
                available = len(seasonal_centers)
                availability_rows.append(
                    {
                        "station_id": station_id,
                        "target": target,
                        "season": season,
                        "required_anchors": anchors_per_season,
                        "available_candidate_centers": available,
                        "shortfall": max(anchors_per_season - available, 0),
                        "max_supported_length": max_supported_length,
                        "data_version": data_version,
                        "evaluation_split": evaluation_split,
                        "source_split": source_split,
                    }
                )
    availability = pd.DataFrame(availability_rows)
    if (availability["shortfall"] > 0).any():
        raise AnchorAvailabilityError(availability)

    flow_lookup, seasonal_thresholds, global_thresholds = _flow_reference(frame)
    anchor_rows: list[dict[str, object]] = []
    for station_id in stations:
        for target in target_names:
            for season_index, season in enumerate(FRONTIER_SEASONS):
                remaining = list(centers_by_group[(station_id, target, season)])
                season_seeds = seeds[
                    season_index
                    * anchors_per_season : (season_index + 1)
                    * anchors_per_season
                ]
                for mask_seed in season_seeds:
                    rng = _stable_rng(
                        "frontier_anchor_v1",
                        data_version,
                        evaluation_split,
                        station_id,
                        target,
                        season,
                        mask_seed,
                    )
                    selected_position = int(rng.integers(0, len(remaining)))
                    center_index = int(remaining.pop(selected_position))
                    start_index, _ = centered_bounds(
                        center_index, max_supported_length, len(dates)
                    )
                    center_date = pd.Timestamp(dates[center_index])
                    anchor_rows.append(
                        {
                            "anchor_id": stable_scenario_id(
                                "ANCHOR",
                                data_version,
                                evaluation_split,
                                station_id,
                                target,
                                season,
                                seed=mask_seed,
                            ),
                            "station_id": station_id,
                            "target": target,
                            "center_date": center_date.strftime("%Y-%m-%d"),
                            "center_index": center_index,
                            "start_month": int(dates[start_index].month),
                            "season": season,
                            "year": int(center_date.year),
                            "hydrologic_state": _hydrologic_state(
                                station_id,
                                center_date,
                                season,
                                flow_lookup,
                                seasonal_thresholds,
                                global_thresholds,
                            ),
                            "mask_seed": int(mask_seed),
                            "max_supported_length": max_supported_length,
                            "data_version": data_version,
                            "evaluation_split": evaluation_split,
                            "source_split": source_split,
                        }
                    )
    catalog = pd.DataFrame(anchor_rows, columns=FRONTIER_ANCHOR_COLUMNS)
    if catalog["anchor_id"].duplicated().any():
        raise AssertionError("generated duplicate frontier anchor IDs")
    return catalog


__all__ = [
    "FRONTIER_ANCHOR_COLUMNS",
    "FRONTIER_MASK_SEEDS",
    "FRONTIER_SEASONS",
    "AnchorAvailabilityError",
    "generate_frontier_anchor_catalog",
    "meteorological_season",
]
