"""Build the fixed M1--M10 experiment grid from project YAML files."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from stream_recoverability.masks.anchors import load_frontier_anchor_catalog
from stream_recoverability.masks.event_catalog import (
    EVENT_DEFINITIONS,
    event_catalog_sha256,
    event_stress_identity,
    load_event_episode_catalog,
)

from .contracts import canonical_evaluation_split, file_sha256

CORE_EXPECTED_COUNTS = {"M1": 36, "M2": 48, "M3": 48, "M4": 24}
DEFAULT_FRONTIER_ANCHOR_PATH = (
    Path(__file__).resolve().parents[3] / "metadata" / "frontier_anchors.csv"
)


@dataclass(frozen=True)
class ExperimentCondition:
    experiment: str
    condition_id: str
    mask_type: str
    station_ids: tuple[str, ...]
    variables: tuple[str, ...]
    evaluation_variables: tuple[str, ...] | None = None
    missing_rate: float | None = None
    gap_length: int | None = None
    layout: str | None = None
    outage_mode: str | None = None
    overlap_ratio: float | None = None
    event_type: str | None = None
    window_length: int = 368
    training_protocol: str = "seen_length"
    held_out_station: str | None = None
    failed_station_ids: tuple[str, ...] = ()
    validation_scope: str = "internal_test"
    data_version: str = "published_v1"
    evaluation_split: str = "test"
    anchor_id: str | None = None
    center_date: str | None = None
    forced_start_index: int | None = None
    event_id: str | None = None
    control_id: str | None = None
    pair_id: str | None = None
    catalog_role: str | None = None
    event_season: str | None = None
    event_threshold: float | None = None
    threshold: float | None = None
    threshold_quantile: float | None = None
    threshold_operator: str | None = None
    threshold_reference_split: str | None = None
    threshold_reference_scope: str | None = None
    threshold_training_samples: int | None = None
    minimum_training_samples: int | None = None
    source_split: str | None = None
    analysis_eligible: bool | None = None
    catalog_schema_version: str | None = None
    episode_length: int | None = None
    event_window_length: int | None = None
    episode_component_count: int | None = None
    raw_episode_length: int | None = None
    raw_episode_start_index: int | None = None
    raw_episode_end_index: int | None = None
    raw_episode_start_date: str | None = None
    raw_episode_end_date: str | None = None
    window_start_index: int | None = None
    window_end_index: int | None = None
    window_center_index: int | None = None
    window_start_date: str | None = None
    window_end_date: str | None = None
    window_center_date: str | None = None
    event_peak_index: int | None = None
    event_peak_date: str | None = None
    event_peak_value: float | None = None
    event_min_index: int | None = None
    event_min_date: str | None = None
    event_min_value: float | None = None
    event_intensity: float | None = None
    rising_phase_start_index: int | None = None
    rising_phase_end_index: int | None = None
    rising_phase_start_date: str | None = None
    rising_phase_end_date: str | None = None
    peak_phase_start_index: int | None = None
    peak_phase_end_index: int | None = None
    peak_phase_start_date: str | None = None
    peak_phase_end_date: str | None = None
    recession_phase_start_index: int | None = None
    recession_phase_end_index: int | None = None
    recession_phase_start_date: str | None = None
    recession_phase_end_date: str | None = None
    control_start_index: int | None = None
    control_end_index: int | None = None
    control_center_index: int | None = None
    control_start_date: str | None = None
    control_end_date: str | None = None
    control_center_date: str | None = None
    event_definition: str | None = None
    minimum_duration_days: int | None = None
    merge_gap_days: int | None = None
    fixed_window_length: int | None = None
    climatology_half_window_days: int | None = None
    threshold_doy_half_window_days: int | None = None
    event_climatology_value: float | None = None
    control_context_days: int | None = None
    center_index: int | None = None
    anchor_target: str | None = None
    anchor_mask_seed: int | None = None
    anchor_data_version: str | None = None
    anchor_evaluation_split: str | None = None
    anchor_source_split: str | None = None
    anchor_max_supported_length: int | None = None
    anchor_start_month: int | None = None
    anchor_season: str | None = None
    anchor_year: int | None = None
    anchor_hydrologic_state: str | None = None
    async_axis: str | None = None
    event_window_eligible: bool | None = None
    event_left_context_available: bool | None = None
    event_right_context_available: bool | None = None
    analysis_exclusion_reason: str | None = None
    episode_boundary_policy: str | None = None
    control_match_year_distance: int | None = None
    control_match_day_of_year_distance: int | None = None
    control_reuse_policy: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentScenario:
    condition: ExperimentCondition
    mask_seed: int

    @property
    def scenario_id(self) -> str:
        suffixes: list[str] = []
        if self.condition.data_version != "published_v1":
            suffixes.append(self.condition.data_version.upper())
        if self.condition.evaluation_split != "test":
            suffixes.append(self.condition.evaluation_split.upper())
        detail = "" if not suffixes else "-" + "-".join(suffixes)
        return f"{self.condition.condition_id}{detail}-R{self.mask_seed:04d}"

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.condition.as_dict(),
            "scenario_id": self.scenario_id,
            "mask_seed": self.mask_seed,
        }


@dataclass(frozen=True)
class ExperimentGrid:
    suite: str
    conditions: tuple[ExperimentCondition, ...]
    scenarios: tuple[ExperimentScenario, ...]
    mask_seeds: tuple[int, ...]
    training_seeds: tuple[int, ...]
    external_validation_status: str
    event_catalog_path: str | None = None
    event_catalog_sha256: str | None = None
    event_catalog_episode_count: int = 0
    event_catalog_analysis_count: int = 0
    frontier_anchor_catalog_path: str | None = None
    frontier_anchor_catalog_sha256: str | None = None
    frontier_anchor_count: int = 0
    validation_anchor_catalog_path: str | None = None
    validation_anchor_catalog_sha256: str | None = None
    validation_anchor_count: int = 0
    validation_anchor_catalog_logical_sha256: str | None = None
    validation_anchor_ids: tuple[str, ...] = ()

    @property
    def condition_counts(self) -> dict[str, int]:
        counts = Counter(condition.experiment for condition in self.conditions)
        return dict(sorted(counts.items()))

    def shard(self, index: int, count: int) -> ExperimentGrid:
        if count < 1 or not 0 <= index < count:
            raise ValueError("shard index/count must satisfy 0 <= index < count")
        scenarios = tuple(
            scenario for position, scenario in enumerate(self.scenarios) if position % count == index
        )
        condition_ids = {scenario.condition.condition_id for scenario in scenarios}
        conditions = tuple(
            condition for condition in self.conditions if condition.condition_id in condition_ids
        )
        return ExperimentGrid(
            suite=self.suite,
            conditions=conditions,
            scenarios=scenarios,
            mask_seeds=self.mask_seeds,
            training_seeds=self.training_seeds,
            external_validation_status=self.external_validation_status,
            event_catalog_path=self.event_catalog_path,
            event_catalog_sha256=self.event_catalog_sha256,
            event_catalog_episode_count=self.event_catalog_episode_count,
            event_catalog_analysis_count=self.event_catalog_analysis_count,
            frontier_anchor_catalog_path=self.frontier_anchor_catalog_path,
            frontier_anchor_catalog_sha256=self.frontier_anchor_catalog_sha256,
            frontier_anchor_count=self.frontier_anchor_count,
            validation_anchor_catalog_path=self.validation_anchor_catalog_path,
            validation_anchor_catalog_sha256=self.validation_anchor_catalog_sha256,
            validation_anchor_count=self.validation_anchor_count,
            validation_anchor_catalog_logical_sha256=(
                self.validation_anchor_catalog_logical_sha256
            ),
            validation_anchor_ids=self.validation_anchor_ids,
        )


def _load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"Expected a mapping in {path}")
    return value


def _variables(pattern: str | Iterable[str]) -> tuple[str, ...]:
    if isinstance(pattern, str):
        return tuple(part for part in pattern.replace("+", "_").split("_") if part)
    return tuple(str(value) for value in pattern)


def _rate_token(rate: float) -> str:
    return f"P{round(rate * 100):02d}"


def _pattern_token(variables: tuple[str, ...]) -> str:
    return "".join(variables)


def _catalog_int(value: object) -> int | None:
    missing = value is None or isinstance(value, float) and math.isnan(value)
    return None if missing else int(value)


def _catalog_float(value: object) -> float | None:
    missing = value is None or isinstance(value, float) and math.isnan(value)
    return None if missing else float(value)


def _catalog_text(value: object) -> str | None:
    missing = value is None or isinstance(value, float) and math.isnan(value)
    if missing or not str(value).strip():
        return None
    return str(value)


def _frontier_anchor_target(condition: ExperimentCondition) -> str | None:
    if condition.mask_type not in {
        "async",
        "block",
        "station_outage",
        "matched_network",
    }:
        return None
    if condition.anchor_target is not None:
        return str(condition.anchor_target)
    evaluation = condition.evaluation_variables or condition.variables
    return str(evaluation[0])


def bind_frontier_anchor(
    condition: ExperimentCondition,
    mask_seed: int,
    anchor_catalog: Any,
) -> ExperimentCondition:
    """Bind one condition to its immutable station/target/mask-seed center."""

    target = _frontier_anchor_target(condition)
    if target is None:
        return condition
    station_id = str(condition.station_ids[0])
    selected = anchor_catalog.loc[
        anchor_catalog["station_id"].astype(str).eq(station_id)
        & anchor_catalog["target"].astype(str).eq(target)
        & anchor_catalog["mask_seed"].astype(int).eq(int(mask_seed))
    ]
    if len(selected) != 1:
        raise ValueError(
            "frontier catalog must identify exactly one fixed anchor for "
            f"{station_id}/{target}/R{int(mask_seed):04d}"
        )
    row = selected.iloc[0]
    if str(row["evaluation_split"]) != condition.evaluation_split:
        raise ValueError(
            "condition and frontier anchor evaluation_split differ: "
            f"{condition.evaluation_split!r} != {str(row['evaluation_split'])!r}"
        )
    if int(condition.gap_length or 0) > int(row["max_supported_length"]):
        raise ValueError("condition gap exceeds its fixed anchor maximum")
    return replace(
        condition,
        anchor_id=str(row["anchor_id"]),
        center_date=str(row["center_date"]),
        center_index=int(row["center_index"]),
        anchor_target=target,
        anchor_mask_seed=int(row["mask_seed"]),
        anchor_data_version=str(row["data_version"]),
        anchor_evaluation_split=str(row["evaluation_split"]),
        anchor_source_split=str(row["source_split"]),
        anchor_max_supported_length=int(row["max_supported_length"]),
        anchor_start_month=int(row["start_month"]),
        anchor_season=str(row["season"]),
        anchor_year=int(row["year"]),
        anchor_hydrologic_state=str(row["hydrologic_state"]),
    )


def _core_conditions(manifest: dict[str, Any], config: dict[str, Any]) -> list[ExperimentCondition]:
    stations = tuple(manifest["data_panels"]["core"]["stations"])
    rates = tuple(float(value) for value in manifest["point_missing_rates"])
    lengths = tuple(int(value) for value in manifest["block_lengths"])
    point_patterns = tuple(_variables(value) for value in config["M1"]["patterns"])
    primary_patterns = tuple(_variables(value) for value in manifest["primary_variable_patterns"])
    main_window = int(manifest["window"]["main"])
    conditions: list[ExperimentCondition] = []

    for station in stations:
        for rate in rates:
            for variables in point_patterns:
                conditions.append(
                    ExperimentCondition(
                        "M1",
                        f"M1-PNT-{station}-{_pattern_token(variables)}-{_rate_token(rate)}",
                        "point",
                        (station,),
                        variables,
                        evaluation_variables=variables,
                        missing_rate=rate,
                        layout="synchronized",
                        window_length=main_window,
                    )
                )
    for station in stations:
        for length in lengths:
            for variables in primary_patterns:
                conditions.append(
                    ExperimentCondition(
                        "M2",
                        f"M2-BLK1-{station}-{_pattern_token(variables)}-D{length:03d}",
                        "block",
                        (station,),
                        variables,
                        evaluation_variables=variables,
                        gap_length=length,
                        layout="single",
                        window_length=main_window,
                    )
                )
                conditions.append(
                    ExperimentCondition(
                        "M3",
                        f"M3-BLKM-{station}-{_pattern_token(variables)}-D{length:03d}",
                        "multiblock",
                        (station,),
                        variables,
                        evaluation_variables=variables,
                        gap_length=length,
                        layout="fixed_total_budget",
                        window_length=main_window,
                    )
                )
    for station in stations:
        for length in lengths:
            for mode in config["M4"]["outage_modes"]:
                conditions.append(
                    ExperimentCondition(
                        "M4",
                        f"M4-SITE-{station}-{str(mode).upper().replace('-', '')}-D{length:03d}",
                        "station_outage",
                        (station,),
                        ("T", "F", "L") if mode == "hydro-only" else tuple(config["all_variables"]),
                        evaluation_variables=("T", "F", "L"),
                        gap_length=length,
                        layout="single",
                        outage_mode=str(mode),
                        window_length=main_window,
                        failed_station_ids=(station,),
                    )
                )
    counts = Counter(condition.experiment for condition in conditions)
    actual = {name: counts[name] for name in CORE_EXPECTED_COUNTS}
    if actual != CORE_EXPECTED_COUNTS:
        raise AssertionError(f"Core experiment count mismatch: {actual} != {CORE_EXPECTED_COUNTS}")
    return conditions


def _full_only_conditions(
    manifest: dict[str, Any],
    config: dict[str, Any],
    *,
    data_version: str,
    evaluation_split: str,
    event_catalog: Any | None,
) -> list[ExperimentCondition]:
    stations = tuple(manifest["data_panels"]["core"]["stations"])
    lengths = tuple(int(value) for value in manifest["block_lengths"])
    main_window = int(manifest["window"]["main"])
    conditions: list[ExperimentCondition] = []

    # M5: complete F/L supplementary single- and fixed-budget experiments.
    for station in stations:
        for length in lengths:
            for variables in map(_variables, manifest["secondary_variable_patterns"]):
                for layout, mask_type in (("single", "block"), ("fixed_total_budget", "multiblock")):
                    conditions.append(
                        ExperimentCondition(
                            "M5",
                            f"M5-{mask_type.upper()}-{station}-{_pattern_token(variables)}-D{length:03d}",
                            mask_type,
                            (station,),
                            variables,
                            evaluation_variables=variables,
                            gap_length=length,
                            layout=layout,
                            window_length=main_window,
                        )
                    )

    # M6a: same-station variable-axis asynchronous outages.
    for station in stations:
        for pattern in config["M6"]["variable_patterns"]:
            variables = _variables(pattern)
            for length in lengths:
                for overlap in config["M6"]["overlap_ratios"]:
                    overlap = float(overlap)
                    conditions.append(
                        ExperimentCondition(
                            "M6a",
                            f"M6A-VAR-{station}-{_pattern_token(variables)}-"
                            f"D{length:03d}-O{int(overlap * 100):03d}",
                            "async",
                            (station,),
                            variables,
                            evaluation_variables=variables,
                            gap_length=length,
                            layout="same_station_variable_async",
                            overlap_ratio=overlap,
                            window_length=main_window,
                            failed_station_ids=(station,),
                            anchor_target=variables[0],
                            async_axis="variable",
                        )
                    )

    # M6b: synchronous and staggered cross-station T/F/L outages.
    for pair in config["M6"]["station_pairs"]:
        pair_tuple = tuple(str(value) for value in pair)
        for length in lengths:
            for overlap in config["M6"]["overlap_ratios"]:
                overlap = float(overlap)
                conditions.append(
                    ExperimentCondition(
                        "M6b",
                        f"M6B-STATION-"
                        f"{''.join(pair_tuple)}-TFL-D{length:03d}-O{int(overlap * 100):03d}",
                        "async",
                        pair_tuple,
                        ("T", "F", "L"),
                        evaluation_variables=("T", "F", "L"),
                        gap_length=length,
                        overlap_ratio=overlap,
                        window_length=main_window,
                        failed_station_ids=pair_tuple,
                        anchor_target="T",
                        async_axis="station",
                    )
                )

    # M7a: one deterministic aggregate stress case per station and event.  A
    # stress case is deliberately not replicated across mask seeds because a
    # 100% event-conditioned mask would otherwise be bit-identical.
    if float(config["M7"]["missing_rate"]) != 1.0:
        raise AssertionError("M7a deterministic stress requires missing_rate=1.0")
    for station in stations:
        for event_type, variable in config["M7"]["events"].items():
            event_definition = EVENT_DEFINITIONS[str(event_type)]
            event_id, anchor_id = event_stress_identity(
                station_id=station,
                event_type=str(event_type),
                data_version=data_version,
                evaluation_split=evaluation_split,
            )
            conditions.append(
                ExperimentCondition(
                    "M7a",
                    f"M7A-STRESS-{station}-{event_type.upper()}",
                    "event",
                    (station,),
                    (str(variable),),
                    evaluation_variables=(str(variable),),
                    missing_rate=1.0,
                    layout="deterministic_stress_once",
                    event_type=str(event_type),
                    window_length=main_window,
                    anchor_id=anchor_id,
                    event_id=event_id,
                    catalog_role="stress",
                    threshold_reference_split="train",
                    threshold_reference_scope=(
                        event_definition.threshold_reference_scope
                    ),
                    threshold_quantile=event_definition.quantile,
                    threshold_operator=event_definition.operator,
                    minimum_training_samples=30,
                    source_split=(
                        "test"
                        if evaluation_split == "development_test"
                        else evaluation_split
                    ),
                    analysis_eligible=True,
                    event_definition=event_definition.definition,
                    minimum_duration_days=(
                        event_definition.minimum_duration_days
                    ),
                    merge_gap_days=event_definition.merge_gap_days,
                    fixed_window_length=event_definition.fixed_window_length,
                    climatology_half_window_days=(
                        event_definition.climatology_half_window_days
                    ),
                    threshold_doy_half_window_days=(
                        event_definition.threshold_doy_half_window_days
                    ),
                )
            )

    # M7b: every catalog row yields one fixed episode and its paired fixed
    # non-event control.  Boundary-censored episodes remain auditable in the
    # catalog but are not admitted to the analysis grid.
    if event_catalog is not None:
        configured_events = {
            str(name): str(target) for name, target in config["M7"]["events"].items()
        }
        catalog_pairs = set(
            zip(
                event_catalog["event_type"].astype(str),
                event_catalog["target"].astype(str),
            )
        )
        expected_pairs = set(configured_events.items())
        if not catalog_pairs.issubset(expected_pairs):
            raise ValueError(
                "event catalog contains undeclared event/target pairs: "
                f"{sorted(catalog_pairs.difference(expected_pairs))}"
            )
        unknown_stations = sorted(
            set(event_catalog["station_id"].astype(str)).difference(stations)
        )
        if unknown_stations:
            raise ValueError(
                f"event catalog contains stations outside the core panel: {unknown_stations}"
            )
        selected_catalog = event_catalog.loc[event_catalog["analysis_eligible"]]
        if selected_catalog.empty:
            raise ValueError("event catalog contains no analysis-eligible episodes")
        for row in selected_catalog.itertuples(index=False):
            common = {
                "experiment": "M7b",
                "station_ids": (str(row.station_id),),
                "variables": (str(row.target),),
                "evaluation_variables": (str(row.target),),
                "gap_length": int(row.window_length),
                "event_type": str(row.event_type),
                "window_length": main_window,
                "anchor_id": str(row.anchor_id),
                "event_id": str(row.event_id),
                "control_id": str(row.control_id),
                "pair_id": str(row.pair_id),
                "event_season": str(row.season),
                "event_threshold": float(row.threshold),
                "threshold": float(row.threshold),
                "threshold_quantile": float(row.threshold_quantile),
                "threshold_operator": str(row.threshold_operator),
                "threshold_reference_split": str(row.threshold_reference_split),
                "threshold_reference_scope": str(row.threshold_reference_scope),
                "threshold_training_samples": int(row.threshold_training_samples),
                "minimum_training_samples": int(row.minimum_training_samples),
                "source_split": str(row.source_split),
                "analysis_eligible": True,
                "catalog_schema_version": str(row.catalog_schema_version),
                "episode_length": int(row.episode_length),
                "event_window_length": int(row.window_length),
                "episode_component_count": int(row.episode_component_count),
                "raw_episode_length": int(row.raw_episode_length),
                "raw_episode_start_index": int(row.raw_episode_start_index),
                "raw_episode_end_index": int(row.raw_episode_end_index),
                "raw_episode_start_date": str(row.raw_episode_start_date),
                "raw_episode_end_date": str(row.raw_episode_end_date),
                "window_start_index": int(row.window_start_index),
                "window_end_index": int(row.window_end_index),
                "window_center_index": int(row.window_center_index),
                "window_start_date": str(row.window_start_date),
                "window_end_date": str(row.window_end_date),
                "window_center_date": str(row.window_center_date),
                "event_peak_index": _catalog_int(row.event_peak_index),
                "event_peak_date": _catalog_text(row.event_peak_date),
                "event_peak_value": _catalog_float(row.event_peak_value),
                "event_min_index": _catalog_int(row.event_min_index),
                "event_min_date": _catalog_text(row.event_min_date),
                "event_min_value": _catalog_float(row.event_min_value),
                "event_intensity": float(row.event_intensity),
                "rising_phase_start_index": _catalog_int(
                    row.rising_phase_start_index
                ),
                "rising_phase_end_index": _catalog_int(row.rising_phase_end_index),
                "rising_phase_start_date": _catalog_text(
                    row.rising_phase_start_date
                ),
                "rising_phase_end_date": _catalog_text(row.rising_phase_end_date),
                "peak_phase_start_index": _catalog_int(row.peak_phase_start_index),
                "peak_phase_end_index": _catalog_int(row.peak_phase_end_index),
                "peak_phase_start_date": _catalog_text(row.peak_phase_start_date),
                "peak_phase_end_date": _catalog_text(row.peak_phase_end_date),
                "recession_phase_start_index": _catalog_int(
                    row.recession_phase_start_index
                ),
                "recession_phase_end_index": _catalog_int(
                    row.recession_phase_end_index
                ),
                "recession_phase_start_date": _catalog_text(
                    row.recession_phase_start_date
                ),
                "recession_phase_end_date": _catalog_text(
                    row.recession_phase_end_date
                ),
                "control_start_index": int(row.control_start_index),
                "control_end_index": int(row.control_end_index),
                "control_center_index": int(row.control_center_index),
                "control_start_date": str(row.control_start_date),
                "control_end_date": str(row.control_end_date),
                "control_center_date": str(row.control_center_date),
                "event_definition": str(row.event_definition),
                "minimum_duration_days": int(row.minimum_duration_days),
                "merge_gap_days": int(row.merge_gap_days),
                "fixed_window_length": int(row.fixed_window_length),
                "climatology_half_window_days": int(
                    row.climatology_half_window_days
                ),
                "threshold_doy_half_window_days": int(
                    row.threshold_doy_half_window_days
                ),
                "event_climatology_value": _catalog_float(
                    row.event_climatology_value
                ),
                "control_context_days": int(row.control_context_days),
                "event_window_eligible": bool(row.event_window_eligible),
                "event_left_context_available": bool(
                    row.event_left_context_available
                ),
                "event_right_context_available": bool(
                    row.event_right_context_available
                ),
                "analysis_exclusion_reason": str(row.analysis_exclusion_reason),
                "episode_boundary_policy": str(row.episode_boundary_policy),
                "control_match_year_distance": int(
                    row.control_match_year_distance
                ),
                "control_match_day_of_year_distance": int(
                    row.control_match_day_of_year_distance
                ),
                "control_reuse_policy": str(row.control_reuse_policy),
                "data_version": data_version,
                "evaluation_split": evaluation_split,
            }
            conditions.append(
                ExperimentCondition(
                    condition_id=f"M7B-EVENT-{row.event_id}",
                    mask_type="event_episode",
                    layout="catalog_event_episode",
                    forced_start_index=int(row.window_start_index),
                    center_date=str(row.window_center_date),
                    catalog_role="event_episode",
                    **common,
                )
            )
            conditions.append(
                ExperimentCondition(
                    condition_id=f"M7B-CONTROL-{row.control_id}",
                    mask_type="event_control",
                    layout="matched_non_event_control",
                    forced_start_index=int(row.control_start_index),
                    center_date=str(row.control_center_date),
                    catalog_role="matched_control",
                    **common,
                )
            )

    # M8: compact window sensitivity anchors rather than duplicating all M1--M4.
    for anchor in config["M8"]["anchors"]:
        station = str(anchor.get("station", stations[0]))
        variables = _variables(anchor["variables"])
        for window in config["windows"]:
            length = int(anchor["length"])
            mask_type = str(anchor["mask_type"])
            conditions.append(
                ExperimentCondition(
                    "M8",
                    f"M8-W{int(window):03d}-{mask_type.upper()}-{station}-{_pattern_token(variables)}-D{length:03d}",
                    mask_type,
                    (station,),
                    variables,
                    evaluation_variables=("T", "F", "L") if mask_type == "station_outage" else variables,
                    gap_length=length,
                    layout="single",
                    outage_mode=anchor.get("outage_mode"),
                    window_length=int(window),
                )
            )

    # M9: seen/unseen 180-day length protocols on the primary target.
    for protocol in config["M9"]["protocols"]:
        for station in stations:
            conditions.append(
                ExperimentCondition(
                    "M9",
                    f"M9-{str(protocol).upper()}-{station}-T-D180",
                    "block",
                    (station,),
                    ("T",),
                    evaluation_variables=("T",),
                    gap_length=180,
                    layout="single",
                    window_length=main_window,
                    training_protocol=str(protocol),
                )
            )

    # M10 is explicitly internal exploratory LOSO, never external validation.
    for station in stations:
        conditions.append(
            ExperimentCondition(
                "M10",
                f"M10-LOSO-{station}-T",
                "loso",
                (station,),
                ("T",),
                evaluation_variables=("T",),
                held_out_station=station,
                window_length=main_window,
                validation_scope="exploratory_internal_loso_not_external_validation",
            )
        )
    return conditions


def _smoke_conditions(conditions: list[ExperimentCondition]) -> list[ExperimentCondition]:
    selectors = (
        ("M1", "B1", "T", None, 0.30),
        ("M2", "B1", "T", 30, None),
        ("M3", "B1", "T", 30, None),
        ("M4", "B1", "TFL", 30, None),
    )
    selected = []
    for experiment, station, variables, length, rate in selectors:
        match = next(
            condition
            for condition in conditions
            if condition.experiment == experiment
            and condition.station_ids == (station,)
            and _pattern_token(condition.variables) == variables
            and condition.gap_length == length
            and condition.missing_rate == rate
        )
        selected.append(match)
    return selected


def build_experiment_grid(
    manifest_path: str | Path = "study_manifest.yaml",
    config_path: str | Path = "configs/experiments.yaml",
    *,
    suite: str = "core",
    data_version: str = "published_v1",
    evaluation_split: str = "development_test",
    event_catalog_path: str | Path | None = None,
    frontier_anchor_path: str | Path | None = DEFAULT_FRONTIER_ANCHOR_PATH,
) -> ExperimentGrid:
    """Build ``smoke``, ``core`` (M1--M4), or ``full`` (M1--M10).

    ``full`` always contains the twelve singleton M7a stress cases.  Supplying
    ``event_catalog_path`` additionally expands every analysis-eligible M7b
    event/control pair into two singleton scenarios.
    """

    if suite not in {"smoke", "core", "full"}:
        raise ValueError("suite must be smoke, core, or full")
    evaluation_split = canonical_evaluation_split(evaluation_split)
    data_version = str(data_version).strip()
    if not data_version:
        raise ValueError("data_version must not be empty")
    if event_catalog_path is not None and suite != "full":
        raise ValueError("event_catalog_path is only valid for the full suite")
    manifest = _load_yaml(manifest_path)
    config = _load_yaml(config_path)
    event_catalog = (
        load_event_episode_catalog(
            event_catalog_path,
            expected_data_version=data_version,
            expected_evaluation_split=evaluation_split,
        )
        if event_catalog_path is not None
        else None
    )
    frontier_catalog = (
        load_frontier_anchor_catalog(
            frontier_anchor_path,
            expected_data_version="published_v1",
            expected_evaluation_split="development_test",
            required_stations=tuple(manifest["data_panels"]["core"]["stations"]),
            required_targets=("T", "F", "L"),
        )
        if frontier_anchor_path is not None
        and evaluation_split == "development_test"
        else None
    )
    configured_mask_seeds = tuple(int(value) for value in manifest["mask_seeds"])
    configured_training_seeds = tuple(int(value) for value in manifest["training_seeds"])
    if configured_mask_seeds != tuple(range(101, 121)):
        raise AssertionError("mask_seeds must be fixed at 101..120")
    if configured_training_seeds != (11, 22, 33, 44, 55):
        raise AssertionError("training_seeds must be fixed at 11/22/33/44/55")

    core = _core_conditions(manifest, config)
    if suite == "smoke":
        conditions = _smoke_conditions(core)
        mask_seeds = configured_mask_seeds[:1]
        training_seeds = configured_training_seeds[:1]
    elif suite == "core":
        conditions = core
        mask_seeds = configured_mask_seeds
        training_seeds = configured_training_seeds
    else:
        conditions = [
            *core,
            *_full_only_conditions(
                manifest,
                config,
                data_version=data_version,
                evaluation_split=evaluation_split,
                event_catalog=event_catalog,
            ),
        ]
        mask_seeds = configured_mask_seeds
        training_seeds = configured_training_seeds
    validation_scope = (
        "internal_validation_selection"
        if evaluation_split == "validation"
        else "development_evaluation"
        if evaluation_split in {"test", "development_test"}
        else "confirmatory_once"
    )
    conditions = [
        replace(
            condition,
            data_version=data_version,
            evaluation_split=evaluation_split,
            validation_scope=(
                condition.validation_scope
                if condition.experiment == "M10"
                else validation_scope
            ),
        )
        for condition in conditions
    ]
    if len({condition.condition_id for condition in conditions}) != len(conditions):
        raise AssertionError("condition_id values must be unique")
    scenarios = tuple(
        ExperimentScenario(
            bind_frontier_anchor(condition, seed, frontier_catalog)
            if frontier_catalog is not None
            else condition,
            seed,
        )
        for condition in conditions
        for seed in (
            (0,)
            if condition.experiment in {"M7a", "M7b"}
            else (mask_seeds[0],)
            if condition.experiment == "M10"
            else mask_seeds
        )
    )
    return ExperimentGrid(
        suite=suite,
        conditions=tuple(conditions),
        scenarios=scenarios,
        mask_seeds=mask_seeds,
        training_seeds=training_seeds,
        external_validation_status=str(config["external_validation_status"]),
        event_catalog_path=(
            str(Path(event_catalog_path)) if event_catalog_path is not None else None
        ),
        event_catalog_sha256=(
            event_catalog_sha256(event_catalog) if event_catalog is not None else None
        ),
        event_catalog_episode_count=(
            len(event_catalog) if event_catalog is not None else 0
        ),
        event_catalog_analysis_count=(
            int(event_catalog["analysis_eligible"].sum())
            if event_catalog is not None
            else 0
        ),
        frontier_anchor_catalog_path=(
            str(Path(frontier_anchor_path))
            if frontier_catalog is not None and frontier_anchor_path is not None
            else None
        ),
        frontier_anchor_catalog_sha256=(
            file_sha256(frontier_anchor_path)
            if frontier_catalog is not None and frontier_anchor_path is not None
            else None
        ),
        frontier_anchor_count=(len(frontier_catalog) if frontier_catalog is not None else 0),
    )


__all__ = [
    "CORE_EXPECTED_COUNTS",
    "DEFAULT_FRONTIER_ANCHOR_PATH",
    "ExperimentCondition",
    "ExperimentGrid",
    "ExperimentScenario",
    "bind_frontier_anchor",
    "build_experiment_grid",
]
