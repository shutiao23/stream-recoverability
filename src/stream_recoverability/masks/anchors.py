"""Deterministic, season-balanced anchors for nested centered gaps.

Catalog semantics are intentionally explicit: ``center_date``/``season`` refer
to the fixed center, while ``start_month`` is the month containing the first day
of the *maximum-supported* centered window.  Shorter gaps keep the same center,
so their own start month can differ without changing anchor identity.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

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
VALIDATION_MASK_SEEDS = tuple(range(101, 106))
VALIDATION_ANCHOR_COLUMNS = (
    *FRONTIER_ANCHOR_COLUMNS,
    "complete_variables",
    "season_slot",
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
        if "natural_observed" in aligned:
            eligible &= (
                aligned["natural_observed"].fillna(False).astype(bool).to_numpy()
            )
        evaluation_positions = np.flatnonzero(
            aligned["split"].astype(str).eq(evaluation_split).to_numpy()
        )
        eligible[evaluation_positions[-1]] = False
    starts = valid_block_starts(eligible, max_supported_length)
    return starts + (max_supported_length - 1) // 2


def _joint_eligible_centers(
    frame: pd.DataFrame,
    dates: pd.DatetimeIndex,
    *,
    station_id: str,
    variables: Sequence[str],
    evaluation_split: str,
    max_supported_length: int,
) -> np.ndarray:
    eligible = np.ones(len(dates), dtype=bool)
    for variable in variables:
        rows = frame.loc[
            frame["station_id"].astype(str).eq(station_id)
            & frame["variable"].astype(str).eq(str(variable))
        ].set_index("date")
        aligned = rows.reindex(dates)
        values = pd.to_numeric(aligned["value"], errors="coerce")
        channel_eligible = (
            aligned["quality_approved"].fillna(False).astype(bool)
            & aligned["split"].astype(str).eq(evaluation_split)
            & values.notna()
            & np.isfinite(values)
        ).to_numpy(dtype=bool)
        if "natural_observed" in aligned:
            channel_eligible &= (
                aligned["natural_observed"].fillna(False).astype(bool).to_numpy()
            )
        eligible &= channel_eligible
    evaluation_positions = np.flatnonzero(
        aligned["split"].astype(str).eq(evaluation_split).to_numpy()
    )
    eligible[evaluation_positions[-1]] = False
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


def _normalize_anchor_catalog(
    catalog: pd.DataFrame,
    *,
    expected_columns: Sequence[str],
    expected_data_version: str,
    expected_evaluation_split: str,
    expected_max_supported_length: int,
) -> pd.DataFrame:
    missing = sorted(set(expected_columns).difference(catalog.columns))
    if missing:
        raise ValueError(f"anchor catalog is missing required columns: {missing}")
    if catalog.empty:
        raise ValueError("anchor catalog is empty")
    frame = catalog.loc[:, list(expected_columns)].copy()
    for column in ("anchor_id", "station_id", "target", "season"):
        if frame[column].isna().any() or not frame[column].astype(str).str.strip().all():
            raise ValueError(f"anchor catalog has empty {column} values")
        frame[column] = frame[column].astype(str)
    for column in (
        "center_index",
        "start_month",
        "year",
        "mask_seed",
        "max_supported_length",
    ):
        numeric = pd.to_numeric(frame[column], errors="coerce")
        if numeric.isna().any() or not np.equal(numeric, np.floor(numeric)).all():
            raise ValueError(f"anchor catalog {column} must contain integers")
        frame[column] = numeric.astype(int)
    center_dates = pd.to_datetime(frame["center_date"], errors="coerce")
    if center_dates.isna().any():
        raise ValueError("anchor catalog contains invalid center_date values")
    frame["center_date"] = center_dates.dt.strftime("%Y-%m-%d")
    if frame["anchor_id"].duplicated().any():
        raise ValueError("anchor catalog anchor_id values must be unique")
    key = ["station_id", "target", "mask_seed"]
    if frame.duplicated(key).any():
        raise ValueError(f"anchor catalog contains duplicate {key} bindings")
    versions = tuple(sorted(frame["data_version"].astype(str).unique()))
    if versions != (str(expected_data_version),):
        raise ValueError(
            "anchor catalog data_version mismatch: "
            f"catalog={versions}, expected={expected_data_version!r}"
        )
    splits = tuple(sorted(frame["evaluation_split"].astype(str).unique()))
    if splits != (str(expected_evaluation_split),):
        raise ValueError(
            "anchor catalog evaluation_split mismatch: "
            f"catalog={splits}, expected={expected_evaluation_split!r}"
        )
    supported = tuple(sorted(frame["max_supported_length"].unique()))
    if supported != (int(expected_max_supported_length),):
        raise ValueError(
            "anchor catalog max_supported_length mismatch: "
            f"catalog={supported}, expected={int(expected_max_supported_length)}"
        )
    expected_seasons = frame["center_date"].map(
        lambda value: meteorological_season(pd.Timestamp(value).month)
    )
    if not frame["season"].eq(expected_seasons).all():
        raise ValueError("anchor catalog season disagrees with center_date")
    if not frame["start_month"].between(1, 12).all():
        raise ValueError("anchor catalog start_month must be in 1..12")
    return frame.sort_values(
        ["station_id", "target", "mask_seed"], kind="mergesort", ignore_index=True
    )


def load_frontier_anchor_catalog(
    path: str | Path,
    *,
    expected_data_version: str = "published_v1",
    expected_evaluation_split: str = "development_test",
    required_stations: Sequence[str] | None = None,
    required_targets: Sequence[str] | None = None,
    expected_max_supported_length: int = 365,
) -> pd.DataFrame:
    """Load one immutable frontier catalog without silently filtering identity.

    A sensitivity data version deliberately reuses this primary catalog.  Callers
    must therefore pass the catalog's primary identity here and carry the
    evaluated data version separately; unavailable anchors are reported by
    :func:`audit_anchor_availability`, never replaced by a new random draw.
    """

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    frame = _normalize_anchor_catalog(
        pd.read_csv(source),
        expected_columns=FRONTIER_ANCHOR_COLUMNS,
        expected_data_version=expected_data_version,
        expected_evaluation_split=expected_evaluation_split,
        expected_max_supported_length=expected_max_supported_length,
    )
    stations = (
        tuple(sorted(frame["station_id"].unique()))
        if required_stations is None
        else tuple(dict.fromkeys(map(str, required_stations)))
    )
    targets = (
        tuple(sorted(frame["target"].unique()))
        if required_targets is None
        else tuple(dict.fromkeys(map(str, required_targets)))
    )
    expected_seeds = set(FRONTIER_MASK_SEEDS)
    for station_id in stations:
        for target in targets:
            selected = frame.loc[
                frame["station_id"].eq(station_id) & frame["target"].eq(target)
            ]
            if set(selected["mask_seed"]) != expected_seeds:
                raise ValueError(
                    "frontier anchor catalog must contain mask seeds 101..120 for "
                    f"{station_id}/{target}"
                )
            if selected["season"].value_counts().to_dict() != {
                season: 5 for season in FRONTIER_SEASONS
            }:
                raise ValueError(
                    "frontier anchor catalog must contain five anchors per season for "
                    f"{station_id}/{target}"
                )
    unexpected_stations = sorted(set(frame["station_id"]).difference(stations))
    unexpected_targets = sorted(set(frame["target"]).difference(targets))
    if required_stations is not None and unexpected_stations:
        raise ValueError(
            f"frontier catalog contains undeclared stations: {unexpected_stations}"
        )
    if required_targets is not None and unexpected_targets:
        raise ValueError(
            f"frontier catalog contains undeclared targets: {unexpected_targets}"
        )
    return frame


def generate_validation_anchor_catalog(
    long_data: pd.DataFrame,
    *,
    data_version: str,
    station_ids: Sequence[str],
    evaluation_split: str = "validation",
    source_split: str = "validation",
    variables: Sequence[str] = ("T", "F", "L"),
    max_supported_length: int = 180,
    mask_seeds: Sequence[int] = VALIDATION_MASK_SEEDS,
) -> pd.DataFrame:
    """Generate five immutable, jointly T/F/L-complete centers per station.

    Every station receives all four seasons; the fifth season rotates by station
    so aggregate coverage remains balanced and is directly auditable through
    ``season_slot``.  The same station/seed center is reused by every validation
    condition, including T-only, T/F/L, point, and station-outage strata.
    """

    stations = tuple(dict.fromkeys(map(str, station_ids)))
    variable_names = tuple(dict.fromkeys(map(str, variables)))
    seeds = tuple(int(value) for value in mask_seeds)
    if not stations or not variable_names:
        raise ValueError("station_ids and variables must not be empty")
    if seeds != VALIDATION_MASK_SEEDS:
        raise ValueError("validation mask_seeds must be fixed at 101..105")
    if int(max_supported_length) != 180:
        raise ValueError("validation max_supported_length must be fixed at 180")
    if str(evaluation_split) != "validation" or str(source_split) != "validation":
        raise ValueError("validation anchors must use the validation split identity")
    frame, dates = _normalize_frame(long_data, data_version=str(data_version))
    present_stations = set(frame["station_id"].astype(str).unique())
    unknown = sorted(set(stations).difference(present_stations))
    if unknown:
        raise ValueError(f"validation anchor stations are absent from data: {unknown}")

    flow_lookup, seasonal_thresholds, global_thresholds = _flow_reference(frame)
    rows: list[dict[str, object]] = []
    availability_rows: list[dict[str, object]] = []
    for station_index, station_id in enumerate(stations):
        centers = _joint_eligible_centers(
            frame,
            dates,
            station_id=station_id,
            variables=variable_names,
            evaluation_split=source_split,
            max_supported_length=max_supported_length,
        )
        seasons = np.asarray(
            [meteorological_season(dates[int(index)].month) for index in centers],
            dtype=object,
        )
        season_plan = (*FRONTIER_SEASONS, FRONTIER_SEASONS[station_index % 4])
        required_by_season = {
            season: season_plan.count(season) for season in FRONTIER_SEASONS
        }
        for season in FRONTIER_SEASONS:
            available = int((seasons == season).sum())
            required = required_by_season[season]
            availability_rows.append(
                {
                    "station_id": station_id,
                    "target": "T_F_L",
                    "season": season,
                    "required_anchors": required,
                    "available_candidate_centers": available,
                    "shortfall": max(required - available, 0),
                    "max_supported_length": max_supported_length,
                    "data_version": data_version,
                    "evaluation_split": evaluation_split,
                    "source_split": source_split,
                }
            )
        selected_centers: set[int] = set()
        for slot, (mask_seed, season) in enumerate(
            zip(seeds, season_plan, strict=True), start=1
        ):
            candidates = np.asarray(
                [
                    int(index)
                    for index in centers[seasons == season]
                    if int(index) not in selected_centers
                ],
                dtype=int,
            )
            if candidates.size == 0:
                continue
            rng = _stable_rng(
                "validation_anchor_v1",
                data_version,
                station_id,
                season,
                mask_seed,
            )
            center_index = int(rng.choice(candidates))
            selected_centers.add(center_index)
            start_index, _ = centered_bounds(
                center_index, max_supported_length, len(dates)
            )
            center_date = pd.Timestamp(dates[center_index])
            rows.append(
                {
                    "anchor_id": stable_scenario_id(
                        "VALANCHOR",
                        data_version,
                        evaluation_split,
                        station_id,
                        seed=mask_seed,
                    ),
                    "station_id": station_id,
                    "target": "T_F_L",
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
                    "mask_seed": mask_seed,
                    "max_supported_length": max_supported_length,
                    "data_version": data_version,
                    "evaluation_split": evaluation_split,
                    "source_split": source_split,
                    "complete_variables": "_".join(variable_names),
                    "season_slot": slot,
                }
            )
    availability = pd.DataFrame(availability_rows)
    if (availability["shortfall"] > 0).any() or len(rows) != len(stations) * len(seeds):
        raise AnchorAvailabilityError(availability)
    result = pd.DataFrame(rows, columns=VALIDATION_ANCHOR_COLUMNS)
    return _normalize_anchor_catalog(
        result,
        expected_columns=VALIDATION_ANCHOR_COLUMNS,
        expected_data_version=str(data_version),
        expected_evaluation_split="validation",
        expected_max_supported_length=180,
    )


def load_validation_anchor_catalog(
    path: str | Path,
    *,
    expected_data_version: str,
    required_stations: Sequence[str],
) -> pd.DataFrame:
    """Load the exact three-station, five-center validation catalog."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    frame = _normalize_anchor_catalog(
        pd.read_csv(source),
        expected_columns=VALIDATION_ANCHOR_COLUMNS,
        expected_data_version=expected_data_version,
        expected_evaluation_split="validation",
        expected_max_supported_length=180,
    )
    stations = tuple(dict.fromkeys(map(str, required_stations)))
    if set(frame["station_id"]) != set(stations):
        raise ValueError("validation anchor stations do not match the frozen panel")
    if set(frame["target"]) != {"T_F_L"}:
        raise ValueError("validation anchors must declare jointly complete T_F_L")
    if set(frame["complete_variables"].astype(str)) != {"T_F_L"}:
        raise ValueError("validation anchors must be jointly T/F/L complete")
    for station_id, group in frame.groupby("station_id", observed=True):
        if set(group["mask_seed"]) != set(VALIDATION_MASK_SEEDS) or len(group) != 5:
            raise ValueError(f"validation station {station_id} must have seeds 101..105")
        if set(group["season"]) != set(FRONTIER_SEASONS):
            raise ValueError(
                f"validation station {station_id} must cover all four seasons"
            )
    return frame


def audit_anchor_availability(
    long_data: pd.DataFrame,
    anchors: pd.DataFrame,
    *,
    data_version: str,
    evaluation_split: str,
    source_split: str | None = None,
    variables_by_anchor: dict[str, Sequence[str]] | None = None,
) -> pd.DataFrame:
    """Audit fixed primary centers on one data version without replacement.

    This is the only supported sensitivity behavior: the primary ``anchor_id``
    and center remain fixed, while each requested version reports whether all
    truth cells needed by the maximum centered block remain available.
    """

    if anchors.empty:
        raise ValueError("anchors must not be empty")
    source_label = source_split or _SOURCE_SPLIT_BY_EVALUATION.get(
        evaluation_split, evaluation_split
    )
    frame, dates = _normalize_frame(long_data, data_version=data_version)
    rows: list[dict[str, object]] = []
    for anchor in anchors.itertuples(index=False):
        center_date = pd.Timestamp(anchor.center_date).normalize()
        matches = np.flatnonzero(dates == center_date)
        index_matches = matches.size == 1 and int(matches[0]) == int(anchor.center_index)
        variables = tuple(
            map(
                str,
                (variables_by_anchor or {}).get(
                    str(anchor.anchor_id),
                    str(getattr(anchor, "complete_variables", anchor.target)).split("_"),
                ),
            )
        )
        required_cells = int(anchor.max_supported_length) * len(variables)
        available_cells = 0
        reason = "available"
        if not index_matches:
            reason = "center_identity_mismatch"
        else:
            start, stop = centered_bounds(
                int(anchor.center_index), int(anchor.max_supported_length), len(dates)
            )
            for variable in variables:
                selected = frame.loc[
                    frame["station_id"].astype(str).eq(str(anchor.station_id))
                    & frame["variable"].astype(str).eq(variable)
                ].set_index("date").reindex(dates[start:stop])
                values = pd.to_numeric(selected["value"], errors="coerce")
                eligible = (
                    selected["quality_approved"].fillna(False).astype(bool)
                    & selected["split"].astype(str).eq(source_label)
                    & values.notna()
                    & np.isfinite(values)
                )
                if "natural_observed" in selected:
                    eligible &= selected["natural_observed"].fillna(False).astype(bool)
                available_cells += int(eligible.sum())
            if available_cells != required_cells:
                reason = "incomplete_fixed_anchor_truth"
        rows.append(
            {
                "anchor_id": str(anchor.anchor_id),
                "station_id": str(anchor.station_id),
                "target": str(anchor.target),
                "center_date": center_date.strftime("%Y-%m-%d"),
                "center_index": int(anchor.center_index),
                "anchor_data_version": str(anchor.data_version),
                "data_version": str(data_version),
                "anchor_evaluation_split": str(anchor.evaluation_split),
                "evaluation_split": str(evaluation_split),
                "source_split": str(source_label),
                "required_variables": "_".join(variables),
                "required_cells": required_cells,
                "available_cells": available_cells,
                "available": reason == "available",
                "reason": reason,
                "replacement_allowed": False,
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "FRONTIER_ANCHOR_COLUMNS",
    "FRONTIER_MASK_SEEDS",
    "FRONTIER_SEASONS",
    "VALIDATION_ANCHOR_COLUMNS",
    "VALIDATION_MASK_SEEDS",
    "AnchorAvailabilityError",
    "audit_anchor_availability",
    "generate_frontier_anchor_catalog",
    "generate_validation_anchor_catalog",
    "load_frontier_anchor_catalog",
    "load_validation_anchor_catalog",
    "meteorological_season",
]
