"""Frozen validation-only model funnel and deterministic model ranking.

The artifacts produced from this module are model-selection evidence only.  They
must never be mixed with development, confirmatory, or formal-result artifacts.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from stream_recoverability.masks import load_validation_anchor_catalog

from .contracts import file_sha256
from .grid import (
    ExperimentCondition,
    ExperimentGrid,
    ExperimentScenario,
)

VALIDATION_STATIONS = ("B1", "S2", "P3")
VALIDATION_MASK_SEEDS = (101, 102, 103, 104, 105)
VALIDATION_DEEP_SEEDS = (11, 22, 33)
DEFAULT_VALIDATION_ANCHOR_PATH = (
    Path(__file__).resolve().parents[3] / "metadata" / "validation_anchors.csv"
)
VALIDATION_STRATA = (
    "point_30pct",
    "t_block_10d",
    "t_block_30d",
    "t_block_90d",
    "t_block_180d",
    "tfl_block_90d",
    "hydro_station_outage_90d",
)
LONG_GAP_STRATA = frozenset(
    {"t_block_90d", "t_block_180d", "tfl_block_90d"}
)
STATION_OUTAGE_STRATUM = "hydro_station_outage_90d"

TRADITIONAL_CANDIDATES = (
    "climatology",
    "linear",
    "pchip",
    "kalman",
    "air_only",
    "air_hydro",
    "donor_regression",
    "random_forest",
    "xgboost",
)
DEEP_CANDIDATES = ("brits_ref", "saits_ref", "csdi", "proposed")


@dataclass(frozen=True)
class ValidationStage:
    """One frozen model-selection stage and its allowed training seeds."""

    name: str
    models: tuple[str, ...]
    training_seeds: tuple[int, ...]
    requires_explicit_finalists: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


VALIDATION_STAGES = (
    ValidationStage("traditional", TRADITIONAL_CANDIDATES, ()),
    ValidationStage("deep_single_seed", DEEP_CANDIDATES, (11,)),
    ValidationStage(
        "deep_stability",
        DEEP_CANDIDATES,
        VALIDATION_DEEP_SEEDS,
        requires_explicit_finalists=True,
    ),
)


@dataclass(frozen=True)
class ValidationMaskUnit:
    """Stable validation unit bound to one immutable centered anchor."""

    mask_unit_id: str
    condition_id: str
    scenario_id: str
    unit_index: int
    mask_seed_placeholder: int
    anchor_id: str
    center_date: str
    center_index: int
    season: str
    anchor_data_version: str
    anchor_evaluation_split: str
    max_supported_length: int = 180
    anchor_status: str = "bound_centered_anchor_v1"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationFunnel:
    """Frozen validation grid, mask-unit registry, and staged candidate sets."""

    grid: ExperimentGrid
    mask_units: tuple[ValidationMaskUnit, ...]
    stages: tuple[ValidationStage, ...] = VALIDATION_STAGES
    evidence_role: str = "model_selection_only"
    formal_evidence: bool = False

    def stage(self, name: str) -> ValidationStage:
        for stage in self.stages:
            if stage.name == name:
                return stage
        raise ValueError(
            f"unknown validation stage {name!r}; expected "
            f"{[stage.name for stage in self.stages]}"
        )

    def mask_unit_frame(self) -> pd.DataFrame:
        frame = pd.DataFrame(unit.as_dict() for unit in self.mask_units)
        frame["data_version"] = self.grid.conditions[0].data_version
        frame["evaluation_split"] = "validation"
        frame["evidence_role"] = self.evidence_role
        frame["formal_evidence"] = self.formal_evidence
        return frame


def _load_mapping(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"expected a YAML mapping in {path}")
    return value


def _condition(
    *,
    station: str,
    stratum: str,
    window_length: int,
    data_version: str,
) -> ExperimentCondition:
    common: dict[str, Any] = {
        "experiment": "VAL_FUNNEL",
        "station_ids": (station,),
        "evaluation_variables": ("T",),
        "window_length": window_length,
        "validation_scope": "internal_validation_model_selection_only",
        "data_version": data_version,
        "evaluation_split": "validation",
    }
    if stratum == "point_30pct":
        return ExperimentCondition(
            condition_id=f"VAL-PNT-{station}-T-P30",
            mask_type="point",
            variables=("T",),
            missing_rate=0.30,
            layout="synchronized",
            **common,
        )
    if stratum.startswith("t_block_"):
        length = int(stratum.removeprefix("t_block_").removesuffix("d"))
        return ExperimentCondition(
            condition_id=f"VAL-BLK1-{station}-T-D{length:03d}",
            mask_type="block",
            variables=("T",),
            gap_length=length,
            layout="single",
            **common,
        )
    if stratum == "tfl_block_90d":
        return ExperimentCondition(
            condition_id=f"VAL-BLK1-{station}-TFL-D090",
            mask_type="block",
            variables=("T", "F", "L"),
            gap_length=90,
            layout="single_synchronized",
            **common,
        )
    if stratum == STATION_OUTAGE_STRATUM:
        return ExperimentCondition(
            condition_id=f"VAL-SITE-{station}-HYDROONLY-D090",
            mask_type="station_outage",
            variables=("T", "F", "L"),
            gap_length=90,
            layout="single",
            outage_mode="hydro-only",
            failed_station_ids=(station,),
            **common,
        )
    raise ValueError(f"unsupported validation stratum: {stratum}")


def validation_condition_stratum(condition_id: str) -> str:
    """Map one frozen condition ID to its equal-weight ranking stratum."""

    parts = str(condition_id).split("-")
    if len(parts) < 5 or parts[0] != "VAL":
        raise ValueError(f"not a frozen validation-funnel condition: {condition_id}")
    if parts[1] == "PNT" and parts[-2:] == ["T", "P30"]:
        return "point_30pct"
    if parts[1] == "BLK1" and parts[-2] == "T":
        length_token = parts[-1]
        if length_token in {"D010", "D030", "D090", "D180"}:
            return f"t_block_{int(length_token[1:])}d"
    if parts[1] == "BLK1" and parts[-2:] == ["TFL", "D090"]:
        return "tfl_block_90d"
    if parts[1] == "SITE" and parts[-2:] == ["HYDROONLY", "D090"]:
        return STATION_OUTAGE_STRATUM
    raise ValueError(f"not a frozen validation-funnel condition: {condition_id}")


def build_validation_funnel(
    manifest_path: str | Path = "study_manifest.yaml",
    config_path: str | Path = "configs/experiments.yaml",
    *,
    data_version: str = "published_v1",
    anchor_catalog_path: str | Path = DEFAULT_VALIDATION_ANCHOR_PATH,
    anchor_data_version: str = "published_v1",
) -> ValidationFunnel:
    """Build the immutable 21-condition, 105-unit validation-only funnel."""

    data_version = str(data_version).strip()
    if not data_version:
        raise ValueError("data_version must not be empty")
    manifest = _load_mapping(manifest_path)
    config = _load_mapping(config_path)
    configured_stations = tuple(manifest["data_panels"]["core"]["stations"])
    if configured_stations != VALIDATION_STATIONS:
        raise AssertionError(
            "validation funnel requires the frozen station order "
            f"{VALIDATION_STATIONS}, found {configured_stations}"
        )
    configured_mask_seeds = tuple(int(seed) for seed in manifest["mask_seeds"])
    if not set(VALIDATION_MASK_SEEDS).issubset(configured_mask_seeds):
        raise AssertionError("manifest does not contain validation mask placeholders 101..105")
    configured_training_seeds = tuple(
        int(seed) for seed in manifest["training_seeds"]
    )
    if not set(VALIDATION_DEEP_SEEDS).issubset(configured_training_seeds):
        raise AssertionError("manifest does not contain deep validation seeds 11/22/33")
    anchor_catalog = load_validation_anchor_catalog(
        anchor_catalog_path,
        expected_data_version=anchor_data_version,
        required_stations=VALIDATION_STATIONS,
    )
    anchor_lookup = {
        (str(row.station_id), int(row.mask_seed)): row
        for row in anchor_catalog.itertuples(index=False)
    }

    window_length = int(manifest["window"]["main"])
    conditions = tuple(
        _condition(
            station=station,
            stratum=stratum,
            window_length=window_length,
            data_version=data_version,
        )
        for station in VALIDATION_STATIONS
        for stratum in VALIDATION_STRATA
    )
    scenarios = tuple(
        ExperimentScenario(
            replace(
                condition,
                anchor_id=str(anchor_lookup[(condition.station_ids[0], seed)].anchor_id),
                center_date=str(
                    anchor_lookup[(condition.station_ids[0], seed)].center_date
                ),
                center_index=int(
                    anchor_lookup[(condition.station_ids[0], seed)].center_index
                ),
                anchor_target="T_F_L",
                anchor_mask_seed=seed,
                anchor_data_version=str(
                    anchor_lookup[(condition.station_ids[0], seed)].data_version
                ),
                anchor_evaluation_split="validation",
                anchor_source_split="validation",
                anchor_max_supported_length=180,
                anchor_start_month=int(
                    anchor_lookup[(condition.station_ids[0], seed)].start_month
                ),
                anchor_season=str(
                    anchor_lookup[(condition.station_ids[0], seed)].season
                ),
                anchor_year=int(anchor_lookup[(condition.station_ids[0], seed)].year),
                anchor_hydrologic_state=str(
                    anchor_lookup[(condition.station_ids[0], seed)].hydrologic_state
                ),
            ),
            seed,
        )
        for condition in conditions
        for seed in VALIDATION_MASK_SEEDS
    )
    mask_units = tuple(
        ValidationMaskUnit(
            mask_unit_id=f"{scenario.condition.condition_id}-VU{unit_index:02d}",
            condition_id=scenario.condition.condition_id,
            scenario_id=scenario.scenario_id,
            unit_index=unit_index,
            mask_seed_placeholder=scenario.mask_seed,
            anchor_id=str(scenario.condition.anchor_id),
            center_date=str(scenario.condition.center_date),
            center_index=int(scenario.condition.center_index),
            season=str(scenario.condition.anchor_season),
            anchor_data_version=str(scenario.condition.anchor_data_version),
            anchor_evaluation_split=str(
                scenario.condition.anchor_evaluation_split
            ),
        )
        for condition in conditions
        for unit_index, scenario in enumerate(
            (
                scenario
                for scenario in scenarios
                if scenario.condition.condition_id == condition.condition_id
            ),
            start=1,
        )
    )
    if len(conditions) != 21 or len(scenarios) != 105 or len(mask_units) != 105:
        raise AssertionError("validation funnel must contain 21 conditions and 105 units")
    if len({unit.mask_unit_id for unit in mask_units}) != len(mask_units):
        raise AssertionError("validation mask_unit_id values must be unique")

    grid = ExperimentGrid(
        suite="validation_funnel",
        conditions=conditions,
        scenarios=scenarios,
        mask_seeds=VALIDATION_MASK_SEEDS,
        training_seeds=VALIDATION_DEEP_SEEDS,
        external_validation_status=str(config["external_validation_status"]),
        validation_anchor_catalog_path=str(Path(anchor_catalog_path)),
        validation_anchor_catalog_sha256=file_sha256(anchor_catalog_path),
        validation_anchor_count=len(anchor_catalog),
    )
    return ValidationFunnel(grid=grid, mask_units=mask_units)


def select_validation_stage(
    funnel: ValidationFunnel,
    stage_name: str,
    *,
    models: Sequence[str] | None = None,
) -> tuple[ValidationStage, tuple[str, ...]]:
    """Validate an optional model subset against one frozen funnel stage."""

    stage = funnel.stage(stage_name)
    selected = stage.models if models is None else tuple(
        dict.fromkeys(str(model).strip().lower() for model in models)
    )
    if not selected:
        raise ValueError("at least one validation model is required")
    unknown = sorted(set(selected).difference(stage.models))
    if unknown:
        raise ValueError(
            f"models are not candidates for {stage.name}: {unknown}; "
            f"allowed={list(stage.models)}"
        )
    if stage.requires_explicit_finalists and models is None:
        raise ValueError(
            "deep_stability requires explicit stage-2 finalist models"
        )
    return stage, selected


def _expected_condition_ids() -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for station in VALIDATION_STATIONS:
        for stratum in VALIDATION_STRATA:
            if stratum == "point_30pct":
                condition_id = f"VAL-PNT-{station}-T-P30"
            elif stratum.startswith("t_block_"):
                length = int(stratum.removeprefix("t_block_").removesuffix("d"))
                condition_id = f"VAL-BLK1-{station}-T-D{length:03d}"
            elif stratum == "tfl_block_90d":
                condition_id = f"VAL-BLK1-{station}-TFL-D090"
            else:
                condition_id = f"VAL-SITE-{station}-HYDROONLY-D090"
            result[condition_id] = (station, stratum)
    return result


def _validate_ranking_input(
    event_metrics: pd.DataFrame,
    *,
    expected_data_version: str | None,
    expected_design_hash: str | None,
) -> pd.DataFrame:
    required = {
        "condition_id",
        "scenario_id",
        "model",
        "training_seed",
        "mask_seed",
        "station_id",
        "target",
        "skill",
        "evaluation_split",
        "data_version",
        "design_hash",
    }
    missing = sorted(required.difference(event_metrics.columns))
    if missing:
        raise ValueError(f"validation ranking input is missing columns: {missing}")
    if event_metrics.empty:
        raise ValueError("validation ranking input is empty")

    data = event_metrics.copy()
    if not data["evaluation_split"].astype(str).eq("validation").all():
        raise ValueError("validation ranking rejects non-validation rows")
    if not data["target"].astype(str).eq("T").all():
        raise ValueError("validation ranking is frozen to target T")
    versions = tuple(sorted(data["data_version"].astype(str).unique()))
    if len(versions) != 1:
        raise ValueError(f"validation ranking cannot mix data versions: {versions}")
    if expected_data_version is not None and versions != (expected_data_version,):
        raise ValueError(
            f"validation ranking data_version mismatch: {versions[0]!r} != "
            f"{expected_data_version!r}"
        )
    design_hashes = tuple(sorted(data["design_hash"].astype(str).unique()))
    if len(design_hashes) != 1:
        raise ValueError("validation ranking cannot mix design hashes")
    if expected_design_hash is not None and design_hashes != (expected_design_hash,):
        raise ValueError("validation ranking design_hash does not match current contract")

    expected = _expected_condition_ids()
    actual_condition_ids = set(data["condition_id"].astype(str))
    extra = sorted(actual_condition_ids.difference(expected))
    if extra:
        raise ValueError(f"ranking input contains non-funnel conditions: {extra}")
    data["condition_id"] = data["condition_id"].astype(str)
    data["condition_stratum"] = data["condition_id"].map(
        lambda value: expected[value][1]
    )
    expected_station = data["condition_id"].map(lambda value: expected[value][0])
    if not data["station_id"].astype(str).eq(expected_station).all():
        raise ValueError("condition_id and station_id disagree in validation results")

    data["skill"] = pd.to_numeric(data["skill"], errors="coerce")
    if not np.isfinite(data["skill"]).all():
        raise ValueError("validation ranking requires finite skill for every unit")
    data["mask_seed"] = pd.to_numeric(data["mask_seed"], errors="coerce")
    if data["mask_seed"].isna().any():
        raise ValueError("validation ranking requires integer mask_seed placeholders")
    data["mask_seed"] = data["mask_seed"].astype(int)
    data["_training_seed_key"] = data["training_seed"].map(
        lambda value: "none" if pd.isna(value) else str(int(value))
    )

    raw_key = [
        "model",
        "_training_seed_key",
        "condition_id",
        "mask_seed",
        "station_id",
        "target",
    ]
    duplicates = data.duplicated(raw_key, keep=False)
    if duplicates.any():
        raise ValueError("validation ranking input contains duplicate model-seed units")

    expected_ids = set(expected)
    expected_seeds = set(VALIDATION_MASK_SEEDS)
    for (model, training_seed), group in data.groupby(
        ["model", "_training_seed_key"], sort=True, dropna=False
    ):
        condition_ids = set(group["condition_id"])
        if condition_ids != expected_ids:
            missing_ids = sorted(expected_ids.difference(condition_ids))
            raise ValueError(
                f"incomplete validation conditions for {model}/{training_seed}: "
                f"missing={missing_ids}"
            )
        per_condition = group.groupby("condition_id", sort=False)["mask_seed"].agg(
            lambda values: set(map(int, values))
        )
        bad = {
            condition_id: sorted(seeds)
            for condition_id, seeds in per_condition.items()
            if seeds != expected_seeds
        }
        if bad:
            raise ValueError(
                f"each condition requires mask placeholders 101..105 for "
                f"{model}/{training_seed}: {bad}"
            )
    return data


def rank_validation_models(
    event_metrics: pd.DataFrame,
    *,
    expected_data_version: str | None = None,
    expected_design_hash: str | None = None,
) -> pd.DataFrame:
    """Rank complete models using equal-weight validation condition strata.

    Training-seed replicates are averaged within each immutable mask unit first.
    The primary score is then the unweighted mean of the seven stratum means.
    Stable tie-breaks prioritize worst-stratum and minimum-unit performance,
    fewer negative units, long gaps, station outages, and finally model name.
    """

    data = _validate_ranking_input(
        event_metrics,
        expected_data_version=expected_data_version,
        expected_design_hash=expected_design_hash,
    )
    unit_keys = [
        "model",
        "condition_id",
        "condition_stratum",
        "station_id",
        "mask_seed",
    ]
    units = (
        data.groupby(unit_keys, as_index=False, sort=True, dropna=False)
        .agg(unit_skill=("skill", "mean"))
        .sort_values(unit_keys, kind="mergesort")
    )
    strata = (
        units.groupby(["model", "condition_stratum"], as_index=False, sort=True)
        .agg(stratum_skill=("unit_skill", "mean"))
    )

    rows: list[dict[str, Any]] = []
    version = str(data["data_version"].iloc[0])
    design_hash = str(data["design_hash"].iloc[0])
    for model, model_units in units.groupby("model", sort=True):
        model_strata = strata.loc[strata["model"].eq(model)].copy()
        observed_strata = set(model_strata["condition_stratum"])
        if observed_strata != set(VALIDATION_STRATA):
            raise ValueError(f"model {model} does not cover all validation strata")
        long_gap = model_units.loc[
            model_units["condition_stratum"].isin(LONG_GAP_STRATA), "unit_skill"
        ]
        outage = model_units.loc[
            model_units["condition_stratum"].eq(STATION_OUTAGE_STRATUM),
            "unit_skill",
        ]
        station_means = model_units.groupby("station_id", sort=True)[
            "unit_skill"
        ].mean()
        raw_model = data.loc[data["model"].eq(model)]
        seed_values = pd.to_numeric(raw_model["training_seed"], errors="coerce")
        non_null_seeds = tuple(
            int(seed) for seed in sorted(seed_values.dropna().astype(int).unique())
        )
        if not non_null_seeds:
            stage = "traditional"
        elif len(non_null_seeds) == 1:
            stage = "deep_single_seed"
        else:
            stage = "deep_stability"
        rows.append(
            {
                "model": str(model),
                "validation_stage": stage,
                "mean_skill_across_strata": float(model_strata["stratum_skill"].mean()),
                "worst_stratum_skill": float(model_strata["stratum_skill"].min()),
                "minimum_mask_unit_skill": float(model_units["unit_skill"].min()),
                "negative_skill_count": int((model_units["unit_skill"] < 0).sum()),
                "negative_stratum_count": int(
                    (model_strata["stratum_skill"] < 0).sum()
                ),
                "long_gap_mean_skill": float(long_gap.mean()),
                "long_gap_min_skill": float(long_gap.min()),
                "station_outage_mean_skill": float(outage.mean()),
                "station_outage_min_skill": float(outage.min()),
                "worst_station_mean_skill": float(station_means.min()),
                "condition_strata_count": len(model_strata),
                "mask_unit_count": len(model_units),
                "training_seed_count": len(non_null_seeds),
                "training_seeds": json.dumps(list(non_null_seeds)),
                "evaluation_split": "validation",
                "data_version": version,
                "design_hash": design_hash,
                "evidence_role": "model_selection_only",
                "formal_evidence": False,
            }
        )

    ranking = pd.DataFrame(rows).sort_values(
        [
            "mean_skill_across_strata",
            "worst_stratum_skill",
            "minimum_mask_unit_skill",
            "negative_skill_count",
            "long_gap_mean_skill",
            "station_outage_mean_skill",
            "model",
        ],
        ascending=[False, False, False, True, False, False, True],
        kind="mergesort",
        ignore_index=True,
    )
    ranking.insert(0, "rank", np.arange(1, len(ranking) + 1, dtype=int))
    return ranking


def write_validation_model_ranking(
    event_metrics: pd.DataFrame,
    output_path: str | Path,
    *,
    expected_data_version: str | None = None,
    expected_design_hash: str | None = None,
) -> pd.DataFrame:
    """Write the deterministic validation-only ranking CSV."""

    ranking = rank_validation_models(
        event_metrics,
        expected_data_version=expected_data_version,
        expected_design_hash=expected_design_hash,
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    ranking.to_csv(temporary, index=False)
    temporary.replace(destination)
    return ranking


__all__ = [
    "DEEP_CANDIDATES",
    "LONG_GAP_STRATA",
    "STATION_OUTAGE_STRATUM",
    "TRADITIONAL_CANDIDATES",
    "VALIDATION_DEEP_SEEDS",
    "VALIDATION_MASK_SEEDS",
    "VALIDATION_STAGES",
    "VALIDATION_STATIONS",
    "VALIDATION_STRATA",
    "ValidationFunnel",
    "ValidationMaskUnit",
    "ValidationStage",
    "build_validation_funnel",
    "rank_validation_models",
    "select_validation_stage",
    "validation_condition_stratum",
    "write_validation_model_ranking",
]
