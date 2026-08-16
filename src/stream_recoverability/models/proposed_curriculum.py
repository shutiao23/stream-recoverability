"""Deterministic mixed-missingness curriculum for the proposed imputer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, cast

import numpy as np

CurriculumScenario = Literal[
    "point",
    "single_block",
    "multiblock",
    "synchronous_variable_group",
    "hydrological_station_outage",
    "meteorology_dropout",
    "same_station_variable_async",
    "cross_station_async",
]
ValidationScenario = Literal[
    "point",
    "short_block",
    "long_block",
    "station_outage",
]

CURRICULUM_SCHEMA_VERSION = "mixed_missingness_v1"
CURRICULUM_SCENARIOS: tuple[CurriculumScenario, ...] = (
    "point",
    "single_block",
    "multiblock",
    "synchronous_variable_group",
    "hydrological_station_outage",
    "meteorology_dropout",
    "same_station_variable_async",
    "cross_station_async",
)
FROZEN_VALIDATION_SCENARIOS: tuple[ValidationScenario, ...] = (
    "point",
    "short_block",
    "long_block",
    "station_outage",
)


@dataclass(frozen=True)
class ProposedCurriculumConfig:
    """Frozen scenario probabilities and gap support for proposed training."""

    schema_version: str = CURRICULUM_SCHEMA_VERSION
    scenario_probabilities: tuple[tuple[CurriculumScenario, float], ...] = (
        ("point", 0.20),
        ("single_block", 0.25),
        ("multiblock", 0.15),
        ("synchronous_variable_group", 0.15),
        ("hydrological_station_outage", 0.10),
        ("meteorology_dropout", 0.05),
        ("same_station_variable_async", 0.05),
        ("cross_station_async", 0.05),
    )
    gap_lengths: tuple[int, ...] = (3, 7, 10, 14, 30, 60, 90, 120, 180)
    unseen_length_max_days: int = 90
    point_missing_rates: tuple[float, ...] = (0.10, 0.30, 0.50)
    validation_point_missing_rate: float = 0.30
    validation_short_block_days: int = 14
    validation_long_block_days: int = 90
    validation_station_outage_days: int = 90
    validation_scenarios: tuple[ValidationScenario, ...] = (
        "point",
        "short_block",
        "long_block",
        "station_outage",
    )

    def __post_init__(self) -> None:
        if self.schema_version != CURRICULUM_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {CURRICULUM_SCHEMA_VERSION!r}")
        names = tuple(name for name, _ in self.scenario_probabilities)
        if names != CURRICULUM_SCENARIOS:
            raise ValueError(
                "scenario_probabilities must contain the frozen curriculum order"
            )
        probabilities = np.asarray(
            [probability for _, probability in self.scenario_probabilities],
            dtype=float,
        )
        if not np.isfinite(probabilities).all() or np.any(probabilities < 0):
            raise ValueError("curriculum probabilities must be finite and non-negative")
        if not np.isclose(probabilities.sum(), 1.0, rtol=0.0, atol=1e-12):
            raise ValueError("curriculum probabilities must sum to one")
        if (
            not self.gap_lengths
            or any(int(value) <= 0 for value in self.gap_lengths)
            or tuple(sorted(set(self.gap_lengths))) != self.gap_lengths
        ):
            raise ValueError("gap_lengths must be unique increasing positive integers")
        if self.unseen_length_max_days not in self.gap_lengths:
            raise ValueError("unseen_length_max_days must be one of gap_lengths")
        if not self.point_missing_rates or any(
            not 0.0 < float(value) < 1.0 for value in self.point_missing_rates
        ):
            raise ValueError("point_missing_rates must be in (0, 1)")
        if not 0.0 < float(self.validation_point_missing_rate) < 1.0:
            raise ValueError("validation_point_missing_rate must be in (0, 1)")
        fixed_lengths = (
            self.validation_short_block_days,
            self.validation_long_block_days,
            self.validation_station_outage_days,
        )
        if any(int(value) <= 0 for value in fixed_lengths):
            raise ValueError("validation gap lengths must be positive")
        if self.validation_scenarios != FROZEN_VALIDATION_SCENARIOS:
            raise ValueError(
                "validation_scenarios must match the frozen four scenarios"
            )

    @property
    def probability_map(self) -> dict[str, float]:
        return {name: float(value) for name, value in self.scenario_probabilities}

    def metadata(self) -> dict[str, Any]:
        result = asdict(self)
        result["scenario_probabilities"] = self.probability_map
        return result


@dataclass(frozen=True)
class CurriculumMask:
    artificial_mask: np.ndarray
    metadata: dict[str, Any]


def _validate_seed(seed: int) -> int:
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)):
        raise TypeError("seed must be an integer")
    if int(seed) < 0:
        raise ValueError("seed must be non-negative")
    return int(seed)


def sample_curriculum_scenarios(
    batch_count: int,
    seed: int,
    config: ProposedCurriculumConfig | None = None,
) -> tuple[CurriculumScenario, ...]:
    """Draw a reproducible per-batch scenario schedule at the frozen weights."""

    config = config or ProposedCurriculumConfig()
    if isinstance(batch_count, (bool, np.bool_)) or not isinstance(
        batch_count, (int, np.integer)
    ):
        raise TypeError("batch_count must be an integer")
    if int(batch_count) < 1:
        raise ValueError("batch_count must be positive")
    rng = np.random.default_rng(_validate_seed(seed))
    probabilities = [config.probability_map[name] for name in CURRICULUM_SCENARIOS]
    selected = rng.choice(
        np.asarray(CURRICULUM_SCENARIOS, dtype=object),
        size=int(batch_count),
        replace=True,
        p=probabilities,
    )
    return tuple(cast(CurriculumScenario, str(value)) for value in selected)


def _variable_indices(
    variable_names: tuple[str, ...],
    *,
    jinsha_sunshine_sensitivity: bool = False,
) -> tuple[int, int, int, tuple[int, ...]]:
    normalized = {
        str(name).strip().upper(): index for index, name in enumerate(variable_names)
    }
    missing = [name for name in ("T", "F", "L") if name not in normalized]
    if missing:
        raise ValueError(f"curriculum requires T/F/L channels; missing {missing}")
    if jinsha_sunshine_sensitivity:
        if "RS" in normalized:
            raise ValueError(
                "Jinsha DH sunshine sensitivity cannot include main Rs; "
                "use a DH-only roster"
            )
        if "DH" not in normalized:
            raise ValueError("Jinsha sunshine sensitivity requires DH")
        meteorology_names = ("TA", "P", "W", "RH", "DH")
    else:
        if "RS" not in normalized:
            raise ValueError(
                "main s0_abcd_rs_v1 curriculum requires Rs; "
                "DH sunshine hours are not a silent Group D fallback"
            )
        meteorology_names = ("TA", "P", "W", "RH", "RS")
    meteorology = tuple(
        normalized[name] for name in meteorology_names if name in normalized
    )
    if not meteorology:
        raise ValueError("curriculum requires at least one meteorology channel")
    return normalized["T"], normalized["F"], normalized["L"], meteorology


def _effective_lengths(
    config: ProposedCurriculumConfig,
    protocol: str,
    steps: int,
) -> tuple[int, ...]:
    if protocol not in {"seen_length", "unseen_length"}:
        raise ValueError("protocol must be seen_length or unseen_length")
    maximum = (
        config.unseen_length_max_days
        if protocol == "unseen_length"
        else max(config.gap_lengths)
    )
    result = tuple(
        value for value in config.gap_lengths if value <= maximum and value <= steps
    )
    if not result:
        raise ValueError("window is shorter than every configured curriculum gap")
    return result


def _mark_block(
    geometry: np.ndarray,
    start: int,
    length: int,
    stations: tuple[int, ...],
    variables: tuple[int, ...],
) -> None:
    geometry[
        np.ix_(
            np.arange(start, start + length, dtype=int),
            np.asarray(stations, dtype=int),
            np.asarray(variables, dtype=int),
        )
    ] = True


def _segment_lengths(total: int) -> tuple[int, int, int]:
    quotient, remainder = divmod(int(total), 3)
    return tuple(quotient + (1 if index < remainder else 0) for index in range(3))  # type: ignore[return-value]


def _resolve_validation_scenario(
    requested: CurriculumScenario | ValidationScenario,
    config: ProposedCurriculumConfig,
) -> tuple[CurriculumScenario, int | None, float | None, str | None]:
    if requested == "short_block":
        return "single_block", config.validation_short_block_days, None, requested
    if requested == "long_block":
        return "single_block", config.validation_long_block_days, None, requested
    if requested == "station_outage":
        return (
            "hydrological_station_outage",
            config.validation_station_outage_days,
            None,
            requested,
        )
    if requested == "point":
        return "point", None, config.validation_point_missing_rate, requested
    if requested not in CURRICULUM_SCENARIOS:
        raise ValueError(f"unknown curriculum scenario {requested!r}")
    return cast(CurriculumScenario, requested), None, None, None


def generate_curriculum_mask(
    eligible: np.ndarray,
    variable_names: tuple[str, ...],
    *,
    scenario: CurriculumScenario | ValidationScenario,
    protocol: str,
    seed: int,
    config: ProposedCurriculumConfig | None = None,
    jinsha_sunshine_sensitivity: bool = False,
) -> CurriculumMask:
    """Generate one typed batch mask, intersected with finite eligible cells."""

    config = config or ProposedCurriculumConfig()
    array = np.asarray(eligible)
    if array.ndim != 3 or array.dtype != np.bool_:
        raise ValueError("eligible must be a boolean [time, station, variable] array")
    if array.shape[1] < 2:
        raise ValueError("curriculum requires at least two stations")
    if len(variable_names) != array.shape[2]:
        raise ValueError("variable_names must match the variable axis")
    if not array.any():
        raise ValueError("eligible contains no finite cells")
    seed = _validate_seed(seed)
    rng = np.random.default_rng(seed)
    target, flow, level, meteorology = _variable_indices(
        variable_names,
        jinsha_sunshine_sensitivity=jinsha_sunshine_sensitivity,
    )
    (
        mask_type,
        forced_length,
        forced_point_rate,
        validation_label,
    ) = _resolve_validation_scenario(scenario, config)
    lengths = _effective_lengths(config, protocol, array.shape[0])

    for _ in range(512):
        geometry = np.zeros_like(array, dtype=bool)
        station_count = 1
        overlap_ratio: float | None = None
        point_rate: float | None = None
        if mask_type == "point":
            station = int(rng.integers(0, array.shape[1]))
            candidates = np.flatnonzero(array[:, station, target])
            if not candidates.size:
                continue
            point_rate = float(
                forced_point_rate
                if forced_point_rate is not None
                else rng.choice(config.point_missing_rates)
            )
            count = max(
                1,
                min(candidates.size, int(np.floor(candidates.size * point_rate + 0.5))),
            )
            chosen = rng.choice(candidates, size=count, replace=False)
            geometry[chosen, station, target] = True
            gap_length = 1
            pattern = "T"
            station_indices = (station,)
            variable_indices = (target,)
        elif mask_type == "multiblock":
            feasible = [value for value in lengths if value + 2 <= array.shape[0]]
            if not feasible:
                continue
            gap_length = int(forced_length or rng.choice(feasible))
            segments = _segment_lengths(gap_length)
            minimum_gap = max(1, min(7, (array.shape[0] - gap_length) // 2))
            span = gap_length + 2 * minimum_gap
            if span > array.shape[0]:
                continue
            station = int(rng.integers(0, array.shape[1]))
            start = int(rng.integers(0, array.shape[0] - span + 1))
            cursor = start
            for segment in segments:
                _mark_block(geometry, cursor, segment, (station,), (target,))
                cursor += segment + minimum_gap
            pattern = "T_three_separated_blocks"
            station_indices = (station,)
            variable_indices = (target,)
        else:
            if mask_type == "same_station_variable_async":
                selected_variables = tuple(
                    int(value)
                    for value in rng.choice(
                        np.asarray(
                            [(target, flow), (target, level), (target, flow, level)],
                            dtype=object,
                        )
                    )
                )
                group_count = len(selected_variables)
                # Match the frozen M6 axis exactly.  Ratio 1.0 is retained even
                # though it is geometrically synchronous: it is the endpoint
                # needed to compare the same variable family across M6.
                overlap_ratio = float(rng.choice((0.0, 0.5, 1.0)))
                feasible = [
                    value
                    for value in lengths
                    if value + round(value * (1.0 - overlap_ratio)) * (group_count - 1)
                    <= array.shape[0]
                ]
            elif mask_type == "cross_station_async":
                selected_variables = (target, flow, level)
                group_count = 2
                overlap_ratio = float(rng.choice((0.0, 0.5, 1.0)))
                feasible = [
                    value
                    for value in lengths
                    if value + round(value * (1.0 - overlap_ratio)) <= array.shape[0]
                ]
            else:
                selected_variables = (target,)
                group_count = 1
                feasible = list(lengths)
            if forced_length is not None:
                feasible = [value for value in feasible if value == forced_length]
            if not feasible:
                continue
            gap_length = int(rng.choice(feasible))

            if mask_type == "single_block":
                station = int(rng.integers(0, array.shape[1]))
                start = int(rng.integers(0, array.shape[0] - gap_length + 1))
                _mark_block(geometry, start, gap_length, (station,), (target,))
                pattern = "T"
                station_indices = (station,)
                variable_indices = (target,)
            elif mask_type == "synchronous_variable_group":
                station = int(rng.integers(0, array.shape[1]))
                choices = ((target, flow), (target, level), (target, flow, level))
                selected_variables = choices[int(rng.integers(0, len(choices)))]
                start = int(rng.integers(0, array.shape[0] - gap_length + 1))
                _mark_block(
                    geometry,
                    start,
                    gap_length,
                    (station,),
                    selected_variables,
                )
                pattern = "+".join(
                    variable_names[index] for index in selected_variables
                )
                station_indices = (station,)
                variable_indices = selected_variables
            elif mask_type == "hydrological_station_outage":
                station = int(rng.integers(0, array.shape[1]))
                selected_variables = (target, flow, level)
                start = int(rng.integers(0, array.shape[0] - gap_length + 1))
                _mark_block(
                    geometry,
                    start,
                    gap_length,
                    (station,),
                    selected_variables,
                )
                pattern = "hydrological_T+F+L"
                station_indices = (station,)
                variable_indices = selected_variables
            elif mask_type == "meteorology_dropout":
                station = int(rng.integers(0, array.shape[1]))
                selected_variables = (target, *meteorology)
                start = int(rng.integers(0, array.shape[0] - gap_length + 1))
                _mark_block(
                    geometry,
                    start,
                    gap_length,
                    (station,),
                    selected_variables,
                )
                pattern = "T+same_station_meteorology"
                station_indices = (station,)
                variable_indices = selected_variables
            elif mask_type == "same_station_variable_async":
                station = int(rng.integers(0, array.shape[1]))
                shift = round(gap_length * (1.0 - float(overlap_ratio)))
                span = gap_length + shift * (len(selected_variables) - 1)
                start = int(rng.integers(0, array.shape[0] - span + 1))
                for offset, variable in enumerate(selected_variables):
                    _mark_block(
                        geometry,
                        start + offset * shift,
                        gap_length,
                        (station,),
                        (variable,),
                    )
                pattern = "async_" + "+".join(
                    variable_names[index] for index in selected_variables
                )
                station_indices = (station,)
                variable_indices = selected_variables
            elif mask_type == "cross_station_async":
                station_indices = tuple(
                    int(value)
                    for value in rng.choice(array.shape[1], size=2, replace=False)
                )
                station_count = 2
                shift = round(gap_length * (1.0 - float(overlap_ratio)))
                span = gap_length + shift
                start = int(rng.integers(0, array.shape[0] - span + 1))
                selected_variables = (target, flow, level)
                for offset, station in enumerate(station_indices):
                    _mark_block(
                        geometry,
                        start + offset * shift,
                        gap_length,
                        (station,),
                        selected_variables,
                    )
                pattern = "async_cross_station_hydrological_T+F+L"
                variable_indices = selected_variables
            else:  # pragma: no cover - guarded by the typed resolver
                raise AssertionError(mask_type)

        artificial = geometry & array
        intended_channels = np.argwhere(geometry.any(axis=0))
        if any(
            not artificial[:, int(station), int(variable)].any()
            for station, variable in intended_channels
        ):
            continue
        target_masked = artificial[..., target]
        if not target_masked.any():
            continue
        metadata: dict[str, Any] = {
            "curriculum_schema_version": config.schema_version,
            "training_mask_type": mask_type,
            "training_gap_length": int(gap_length),
            "training_pattern": pattern,
            "training_station_count": int(station_count),
            "training_masked_cells": int(artificial.sum()),
            "training_target_masked_cells": int(target_masked.sum()),
            "station_indices": [int(value) for value in station_indices],
            "variable_indices": [int(value) for value in variable_indices],
            "variable_names": [variable_names[index] for index in variable_indices],
            "protocol": protocol,
            "seed": seed,
            "point_missing_rate": point_rate,
            "overlap_ratio": overlap_ratio,
            "validation_scenario": validation_label,
        }
        if artificial.shape != array.shape or np.any(artificial & ~array):
            raise AssertionError("curriculum mask escaped finite eligible cells")
        return CurriculumMask(artificial_mask=artificial, metadata=metadata)
    raise ValueError(
        f"could not place a finite target mask for curriculum scenario {scenario!r}"
    )


__all__ = [
    "CURRICULUM_SCENARIOS",
    "CURRICULUM_SCHEMA_VERSION",
    "FROZEN_VALIDATION_SCENARIOS",
    "CurriculumMask",
    "CurriculumScenario",
    "ProposedCurriculumConfig",
    "ValidationScenario",
    "generate_curriculum_mask",
    "sample_curriculum_scenarios",
]
