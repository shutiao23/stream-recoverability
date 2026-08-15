"""Build the fixed M1--M10 experiment grid from project YAML files."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml


CORE_EXPECTED_COUNTS = {"M1": 36, "M2": 48, "M3": 48, "M4": 24}


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

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentScenario:
    condition: ExperimentCondition
    mask_seed: int

    @property
    def scenario_id(self) -> str:
        return f"{self.condition.condition_id}-R{self.mask_seed:04d}"

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

    @property
    def condition_counts(self) -> dict[str, int]:
        counts = Counter(condition.experiment for condition in self.conditions)
        return dict(sorted(counts.items()))

    def shard(self, index: int, count: int) -> "ExperimentGrid":
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
        )


def _load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a mapping in {path}")
    return value


def _variables(pattern: str | Iterable[str]) -> tuple[str, ...]:
    if isinstance(pattern, str):
        return tuple(part for part in pattern.replace("+", "_").split("_") if part)
    return tuple(str(value) for value in pattern)


def _rate_token(rate: float) -> str:
    return f"P{int(round(rate * 100)):02d}"


def _pattern_token(variables: tuple[str, ...]) -> str:
    return "".join(variables)


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


def _full_only_conditions(manifest: dict[str, Any], config: dict[str, Any]) -> list[ExperimentCondition]:
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

    # M6: synchronous and staggered two-station T/F/L outages.
    for pair in config["M6"]["station_pairs"]:
        pair_tuple = tuple(str(value) for value in pair)
        for length in lengths:
            for overlap in config["M6"]["overlap_ratios"]:
                overlap = float(overlap)
                conditions.append(
                    ExperimentCondition(
                        "M6",
                        f"M6-{'SYNC' if overlap == 1.0 else 'ASYNC'}-"
                        f"{''.join(pair_tuple)}-TFL-D{length:03d}-O{int(overlap * 100):03d}",
                        "network_outage" if overlap == 1.0 else "async",
                        pair_tuple,
                        ("T", "F", "L"),
                        evaluation_variables=("T", "F", "L"),
                        gap_length=length,
                        overlap_ratio=overlap,
                        window_length=main_window,
                        failed_station_ids=pair_tuple,
                    )
                )

    # M7: event-conditioned cases; thresholds are derived from training only.
    for station in stations:
        for event_type, variable in config["M7"]["events"].items():
            conditions.append(
                ExperimentCondition(
                    "M7",
                    f"M7-EVENT-{station}-{event_type.upper()}",
                    "event",
                    (station,),
                    (str(variable),),
                    evaluation_variables=(str(variable),),
                    missing_rate=float(config["M7"]["missing_rate"]),
                    event_type=str(event_type),
                    window_length=main_window,
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
) -> ExperimentGrid:
    """Build ``smoke``, ``core`` (M1--M4), or ``full`` (M1--M10)."""

    if suite not in {"smoke", "core", "full"}:
        raise ValueError("suite must be smoke, core, or full")
    manifest = _load_yaml(manifest_path)
    config = _load_yaml(config_path)
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
        conditions = [*core, *_full_only_conditions(manifest, config)]
        mask_seeds = configured_mask_seeds
        training_seeds = configured_training_seeds
    if len({condition.condition_id for condition in conditions}) != len(conditions):
        raise AssertionError("condition_id values must be unique")
    scenarios = tuple(
        ExperimentScenario(condition, seed)
        for condition in conditions
        for seed in ((mask_seeds[0],) if condition.experiment == "M10" else mask_seeds)
    )
    return ExperimentGrid(
        suite=suite,
        conditions=tuple(conditions),
        scenarios=scenarios,
        mask_seeds=mask_seeds,
        training_seeds=training_seeds,
        external_validation_status=str(config["external_validation_status"]),
    )


__all__ = [
    "CORE_EXPECTED_COUNTS",
    "ExperimentCondition",
    "ExperimentGrid",
    "ExperimentScenario",
    "build_experiment_grid",
]
