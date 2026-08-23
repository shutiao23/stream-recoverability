"""Fail-closed, evaluate-once execution of the frozen external confirmation.

This module consumes an already-built ``external_upper_middle_chattahoochee_v1``
bundle.  It performs no acquisition and exposes no model-selection controls:
the model roster is loaded from the finalized validation-only manifest, while
all trainable-model protocols and seeds come from the frozen design.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import numpy as np
import pandas as pd

from stream_recoverability.data.confirmatory import (
    CONFIRMATORY_DATA_VERSION,
    CONFIRMATORY_SCHEMA_VERSION,
    FROZEN_PERIODS,
    FROZEN_SITE_IDS,
    FROZEN_VARIABLES,
    ConfirmatoryProtocol,
    FinalizedModelRoster,
    build_availability_report,
    load_confirmatory_protocol,
    load_finalized_model_roster,
    strict_json_loads,
)
from stream_recoverability.models.baselines import XGBoostBaseline
from stream_recoverability.models.reference_baselines import require_pypots_15

from .contracts import DEFAULT_DESIGN_PATH, build_design_contract, file_sha256
from .grid import ExperimentCondition, ExperimentGrid, ExperimentScenario
from .model_registry import FrozenModelDesign, load_frozen_model_design
from .runner import (
    DAILY_KEY,
    EVENT_KEY,
    REFERENCE_MODELS,
    TRAINABLE_MODELS,
    ExperimentRunner,
    _save_compact_mask,
)

EXTERNAL_CONFIRMATION_SCHEMA_VERSION = "external_confirmation_manifest_v1"
EXTERNAL_GRID_SCHEMA_VERSION = "external_confirmation_grid_v1"
EXTERNAL_LOCK_SCHEMA_VERSION = "external_confirmation_once_lock_v1"
EXTERNAL_EVIDENCE_ROLE = "external_confirmation"
EXTERNAL_EVALUATION_SPLIT = "confirmatory"
EXTERNAL_MASK_SEED = 20260815
EXTERNAL_POINT_RATE = 0.30
EXTERNAL_BLOCK_LENGTHS = (30, 90, 180)
EXTERNAL_STATION_OUTAGE_LENGTHS = (90, 180)
EXTERNAL_INFORMATION_CONDITIONS = ("full_information", "no_meteorology")
EXTERNAL_WINDOW_LENGTH = 368
EXTERNAL_TRAINING_PROTOCOL = "seen_length"
METEOROLOGY_VARIABLES = ("Ta", "P", "W", "RH", "Rs")
FEASIBILITY_SCHEMA_VERSION = "confirmatory_feasibility_report_v1"
FEASIBILITY_MASK_CONTRACT_SCHEMA = "confirmatory_mask_contract_v1"
REQUIRED_DATA_ARTIFACTS = frozenset(
    {
        "daily_long.parquet",
        "daily_wide.parquet",
        "metadata/availability_report.json",
        "metadata/availability_report.parquet",
        "metadata/power_point_metadata.parquet",
        "metadata/quality_detail.parquet",
        "metadata/quality_report.json",
        "metadata/request_log.json",
        "metadata/request_plan.json",
        "metadata/site_metadata.parquet",
        "metadata/time_series_metadata.parquet",
        "splits/confirmatory.parquet",
        "splits/train.parquet",
        "splits/validation.parquet",
    }
)
REQUIRED_ROW_IDENTITY_FIELDS = frozenset(
    {
        "data_version",
        "evaluation_split",
        "evidence_role",
        "formal_evidence",
        "seed",
        "seed_role",
        "model",
        "scenario_id",
        "information_condition",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _assert_finite_json(value: Any, path: str = "manifest") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_finite_json(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_finite_json(item, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path} contains a non-finite number")


def _strict_json_mapping(path: Path) -> tuple[dict[str, Any], bytes]:
    if not path.is_file():
        raise FileNotFoundError(path)
    raw = path.read_bytes()
    value = strict_json_loads(raw)
    if not isinstance(value, Mapping):
        raise TypeError(f"{path} must contain a JSON mapping")
    result = dict(value)
    _assert_finite_json(result, str(path))
    return result, raw


def _safe_relative_artifact_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError("data artifact names must be non-empty strings")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise ValueError(f"unsafe data artifact path: {value!r}")
    return value


def _validate_artifact_inventory(
    data_root: Path, manifest: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    raw_artifacts = manifest.get("artifacts")
    if not isinstance(raw_artifacts, Mapping):
        raise TypeError("confirmatory data manifest artifacts must be a mapping")
    artifacts: dict[str, dict[str, Any]] = {}
    for raw_name, raw_identity in raw_artifacts.items():
        name = _safe_relative_artifact_path(raw_name)
        if not isinstance(raw_identity, Mapping):
            raise TypeError(f"data artifact identity must be a mapping: {name}")
        if set(raw_identity) != {"sha256", "bytes"}:
            raise ValueError(
                f"data artifact identity requires exactly sha256/bytes: {name}"
            )
        digest = raw_identity.get("sha256")
        size = raw_identity.get("bytes")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError(f"data artifact has an invalid SHA-256: {name}")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError(f"data artifact has an invalid byte count: {name}")
        artifacts[name] = {"sha256": digest, "bytes": size}

    missing_required = sorted(REQUIRED_DATA_ARTIFACTS.difference(artifacts))
    if missing_required:
        raise ValueError(
            f"confirmatory data bundle lacks required artifacts: {missing_required}"
        )
    observed = {
        path.relative_to(data_root).as_posix()
        for path in data_root.rglob("*")
        if path.is_file()
        and path.name
        not in {"provenance_manifest.json", "provenance_manifest.json.sha256"}
    }
    if observed != set(artifacts):
        raise ValueError(
            "confirmatory artifact inventory is not exact: "
            f"missing={sorted(set(artifacts).difference(observed))}, "
            f"unexpected={sorted(observed.difference(artifacts))}"
        )
    for name, identity in artifacts.items():
        path = data_root / name
        if path.stat().st_size != identity["bytes"]:
            raise ValueError(f"confirmatory artifact byte count mismatch: {name}")
        if file_sha256(path) != identity["sha256"]:
            raise ValueError(f"confirmatory artifact SHA-256 mismatch: {name}")
    return artifacts


def _expected_dates() -> pd.DatetimeIndex:
    return pd.date_range(FROZEN_PERIODS[0][1], FROZEN_PERIODS[-1][2], freq="D")


def _expected_split(dates: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    values = pd.DatetimeIndex(pd.to_datetime(dates)).normalize()
    result = np.full(len(values), "", dtype=object)
    for label, start, end in FROZEN_PERIODS:
        selected = (values >= pd.Timestamp(start)) & (values <= pd.Timestamp(end))
        result[selected] = label
    if np.any(result == ""):
        raise ValueError("confirmatory data contain dates outside frozen periods")
    return result.astype(str)


def _single_text_value(frame: pd.DataFrame, column: str, expected: str) -> None:
    if column not in frame:
        raise KeyError(f"confirmatory table is missing {column!r}")
    values = tuple(frame[column].dropna().astype(str).unique())
    if values != (expected,):
        raise ValueError(f"confirmatory table {column} identity mismatch: {values!r}")


def _validate_complete_tables(
    data_root: Path, manifest: Mapping[str, Any]
) -> tuple[Path, Path, dict[str, Any]]:
    wide_path = data_root / "daily_wide.parquet"
    long_path = data_root / "daily_long.parquet"
    wide = pd.read_parquet(wide_path)
    long = pd.read_parquet(long_path)
    dates = _expected_dates()

    required_wide = {
        "date",
        "split",
        "data_version",
        "is_external_validation",
        *(
            f"{site_id}_{variable}"
            for site_id in FROZEN_SITE_IDS
            for variable in FROZEN_VARIABLES
        ),
    }
    if missing := sorted(required_wide.difference(wide.columns)):
        raise KeyError(f"confirmatory wide table lacks columns: {missing}")
    wide_dates = pd.DatetimeIndex(pd.to_datetime(wide["date"])).normalize()
    if len(wide) != len(dates) or not wide_dates.equals(dates):
        raise ValueError("confirmatory wide date axis is not the frozen daily axis")
    if wide_dates.duplicated().any():
        raise ValueError("confirmatory wide table contains duplicate dates")
    _single_text_value(wide, "data_version", CONFIRMATORY_DATA_VERSION)
    if not wide["is_external_validation"].fillna(False).astype(bool).all():
        raise ValueError("confirmatory wide rows must be externally identified")
    if not np.array_equal(wide["split"].astype(str), _expected_split(wide_dates)):
        raise ValueError("confirmatory wide split labels violate frozen periods")

    required_long = {
        "date",
        "site_id",
        "variable",
        "value",
        "split",
        "data_version",
        "natural_observed",
        "quality_approved",
        "is_external_validation",
        "external_evidence_role",
    }
    if missing := sorted(required_long.difference(long.columns)):
        raise KeyError(f"confirmatory long table lacks columns: {missing}")
    expected_long_rows = len(dates) * len(FROZEN_SITE_IDS) * len(FROZEN_VARIABLES)
    if len(long) != expected_long_rows:
        raise ValueError(
            "confirmatory long table is not a complete date/site/variable grid: "
            f"{len(long)} != {expected_long_rows}"
        )
    long = long.copy()
    long["date"] = pd.to_datetime(long["date"]).dt.normalize()
    if long.duplicated(["date", "site_id", "variable"]).any():
        raise ValueError("confirmatory long table contains duplicate grid cells")
    if set(long["date"]) != set(dates):
        raise ValueError("confirmatory long date axis differs from the frozen axis")
    if set(long["site_id"].astype(str)) != set(FROZEN_SITE_IDS):
        raise ValueError("confirmatory long table has the wrong site roster")
    if set(long["variable"].astype(str)) != set(FROZEN_VARIABLES):
        raise ValueError("confirmatory long table has the wrong variable roster")
    _single_text_value(long, "data_version", CONFIRMATORY_DATA_VERSION)
    if not long["is_external_validation"].fillna(False).astype(bool).all():
        raise ValueError("confirmatory long rows must be externally identified")
    if not np.array_equal(long["split"].astype(str), _expected_split(long["date"])):
        raise ValueError("confirmatory long split labels violate frozen periods")
    expected_roles = (
        long["split"]
        .astype(str)
        .map(
            {
                "train": "external_model_fitting_only",
                "validation": "external_early_stopping_only",
                "confirmatory": "locked_confirmatory_evaluation_only",
            }
        )
    )
    if not long["external_evidence_role"].astype(str).equals(expected_roles):
        raise ValueError("confirmatory long evidence roles violate frozen periods")
    approved = long["quality_approved"].fillna(False).astype(bool).to_numpy()
    natural = long["natural_observed"].fillna(False).astype(bool).to_numpy()
    finite = np.isfinite(pd.to_numeric(long["value"], errors="coerce"))
    if np.any(approved & (~natural | ~finite)):
        raise ValueError(
            "quality-approved confirmatory values must be finite natural observations"
        )

    counts = manifest.get("output_counts")
    if not isinstance(counts, Mapping):
        raise TypeError("confirmatory data manifest output_counts must be a mapping")
    if counts.get("wide_rows") != len(wide) or counts.get("long_rows") != len(long):
        raise ValueError("confirmatory data manifest row counts do not match tables")
    split_counts = counts.get("split_wide_rows")
    expected_counts = {
        label: int((_expected_split(dates) == label).sum())
        for label, _, _ in FROZEN_PERIODS
    }
    if split_counts != expected_counts:
        raise ValueError("confirmatory split counts violate frozen periods")

    for label, _, _ in FROZEN_PERIODS:
        split = pd.read_parquet(data_root / "splits" / f"{label}.parquet")
        if len(split) != expected_counts[label]:
            raise ValueError(f"confirmatory {label} split has the wrong row count")
        _single_text_value(split, "data_version", CONFIRMATORY_DATA_VERSION)
        if tuple(split["split"].astype(str).unique()) != (label,):
            raise ValueError(f"confirmatory {label} split identity mismatch")
        split_dates = pd.DatetimeIndex(pd.to_datetime(split["date"])).normalize()
        expected_label_dates = dates[_expected_split(dates) == label]
        if not split_dates.equals(expected_label_dates):
            raise ValueError(f"confirmatory {label} split date axis mismatch")
        expected_split_frame = wide.loc[wide["split"] == label].reset_index(drop=True)
        try:
            pd.testing.assert_frame_equal(
                split.reset_index(drop=True),
                expected_split_frame,
                check_dtype=True,
                check_like=False,
            )
        except AssertionError as error:
            raise ValueError(
                f"confirmatory {label} split is not an exact wide-table partition"
            ) from error

    return (
        wide_path,
        long_path,
        {
            "wide_rows": len(wide),
            "long_rows": len(long),
            "split_wide_rows": expected_counts,
            "quality_approved_rows": int(approved.sum()),
            "natural_observed_rows": int(natural.sum()),
        },
    )


def _validate_access_gate(
    manifest: Mapping[str, Any],
    roster: FinalizedModelRoster,
    protocol: ConfirmatoryProtocol,
) -> None:
    if manifest.get("schema_version") != CONFIRMATORY_SCHEMA_VERSION:
        raise ValueError("confirmatory data manifest has the wrong schema_version")
    if manifest.get("data_version") != CONFIRMATORY_DATA_VERSION:
        raise ValueError("confirmatory data manifest has the wrong data_version")
    if manifest.get("immutable") is not True:
        raise ValueError("confirmatory data manifest must declare immutable=true")
    if manifest.get("design_version") != protocol.design_version:
        raise ValueError("confirmatory data design_version mismatch")
    if manifest.get("design_sha256") != protocol.design_sha256:
        raise ValueError("confirmatory data design SHA-256 mismatch")
    expected_protocol = json.loads(json.dumps(protocol.metadata()))
    observed_protocol = json.loads(json.dumps(manifest.get("protocol")))
    if observed_protocol != expected_protocol:
        raise ValueError("confirmatory data protocol does not match the design freeze")
    if manifest.get("confirmatory_evaluation_executed") is not False:
        raise ValueError("confirmatory data manifest indicates prior evaluation")
    if manifest.get("performance_metrics_computed") is not False:
        raise ValueError("confirmatory data manifest contains prior performance use")
    quality = manifest.get("quality_summary")
    if (
        not isinstance(quality, Mapping)
        or quality.get("performance_metrics_computed") is not False
    ):
        raise ValueError("confirmatory quality report indicates performance use")
    gate = manifest.get("confirmatory_access_gate")
    if not isinstance(gate, Mapping):
        raise TypeError("confirmatory data manifest lacks its finalized-roster gate")
    expected = {
        "manifest_sha256": roster.manifest_sha256,
        "selected_models": list(roster.selected_models),
        "best_traditional_model": roster.best_traditional_model,
        "proposed_decision": roster.proposed_decision,
        "selection_data_version": roster.selection_data_version,
        "selection_design_hash": roster.selection_design_hash,
        "selection_contract": roster.selection_contract,
        "artifacts": roster.artifacts,
    }
    mismatches = {
        key: (gate.get(key), value)
        for key, value in expected.items()
        if gate.get(key) != value
    }
    if mismatches:
        raise ValueError(
            "confirmatory data was not unlocked by the supplied frozen roster: "
            f"{mismatches}"
        )


def _validate_data_manifest(
    data_root: Path,
    roster: FinalizedModelRoster,
    protocol: ConfirmatoryProtocol,
) -> tuple[Path, Path, Path, dict[str, Any]]:
    manifest_path = data_root / "provenance_manifest.json"
    sidecar_path = data_root / "provenance_manifest.json.sha256"
    manifest, raw = _strict_json_mapping(manifest_path)
    digest = hashlib.sha256(raw).hexdigest()
    if not sidecar_path.is_file():
        raise FileNotFoundError(sidecar_path)
    if sidecar_path.read_text(encoding="ascii") != digest + "\n":
        raise ValueError("confirmatory data manifest SHA-256 sidecar mismatch")
    _validate_access_gate(manifest, roster, protocol)
    artifacts = _validate_artifact_inventory(data_root, manifest)
    wide_path, long_path, counts = _validate_complete_tables(data_root, manifest)
    return (
        manifest_path,
        wide_path,
        long_path,
        {
            "manifest_sha256": digest,
            "manifest_bytes": len(raw),
            "artifact_count": len(artifacts),
            "counts": counts,
        },
    )


def _model_protocols(
    models: Sequence[str],
    design: FrozenModelDesign,
    training_seeds: Sequence[int],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for model in models:
        if model in TRAINABLE_MODELS:
            result[model] = {
                "common_training": dict(design.common_training),
                "model_protocol": design.protocol_for(model),
                "training_seeds": list(training_seeds),
                "selection_source": "finalized_validation_roster",
            }
        else:
            result[model] = {
                "implementation_identity": "frozen_code_identity",
                "selection_source": "finalized_validation_roster",
                "confirmatory_tuning": "prohibited",
            }
    return result


def _frozen_training_seeds(
    design_path: str | Path = DEFAULT_DESIGN_PATH,
) -> tuple[int, ...]:
    import yaml

    with Path(design_path).open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    try:
        seeds = tuple(int(value) for value in document["training"]["training_seeds"])
    except (KeyError, TypeError) as error:
        raise ValueError("design freeze lacks training.training_seeds") from error
    if not seeds or len(set(seeds)) != len(seeds) or any(seed < 0 for seed in seeds):
        raise ValueError("frozen training seeds must be unique non-negative integers")
    return seeds


def _validate_selected_models(
    roster: FinalizedModelRoster,
    model_design: FrozenModelDesign,
) -> tuple[str, ...]:
    selected = tuple(roster.selected_models)
    unknown = sorted(set(selected).difference(model_design.formal_candidates))
    if unknown:
        raise ValueError(
            f"finalized roster contains non-formal or undeclared models: {unknown}"
        )
    unsupported_t = sorted(
        set(selected).intersection({"rating_curve", "independent_flow"})
    )
    if unsupported_t:
        raise ValueError(
            "external confirmation is frozen to target T, but roster contains "
            f"F-only models: {unsupported_t}"
        )
    if roster.best_traditional_model not in selected:
        raise ValueError("roster best traditional model is not selected")
    if "xgboost" in selected and not XGBoostBaseline.is_available():
        raise RuntimeError("selected xgboost dependency is unavailable")
    if set(selected).intersection(REFERENCE_MODELS):
        require_pypots_15()
    return selected


@dataclass(frozen=True)
class ConfirmatoryEvaluationInputs:
    """Fully checked, immutable inputs for one external execution."""

    protocol: ConfirmatoryProtocol
    roster: FinalizedModelRoster
    model_design: FrozenModelDesign
    selected_models: tuple[str, ...]
    training_seeds: tuple[int, ...]
    data_root: Path
    data_manifest_path: Path
    wide_path: Path
    long_path: Path
    data_manifest_identity: dict[str, Any]
    evidence_contract: dict[str, Any]
    code_provenance: dict[str, Any]


def preflight_confirmatory_evaluation(
    *,
    data_root: str | Path,
    finalized_model_roster_path: str | Path,
    design_path: str | Path = DEFAULT_DESIGN_PATH,
    study_manifest_path: str | Path = "study_manifest.yaml",
    experiment_config_path: str | Path = "configs/experiments.yaml",
    selection_data_version_manifest_path: str | Path | None = None,
) -> ConfirmatoryEvaluationInputs:
    """Validate all roster, data, design, dependency, and code gates without writes."""

    root = Path(data_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"confirmatory data root not found: {root}")
    protocol = load_confirmatory_protocol(design_path)
    roster = load_finalized_model_roster(
        finalized_model_roster_path,
        design_path=design_path,
        study_manifest_path=study_manifest_path,
        experiment_config_path=experiment_config_path,
        selection_data_version_manifest_path=selection_data_version_manifest_path,
    )
    model_design = load_frozen_model_design(design_path)
    selected_models = _validate_selected_models(roster, model_design)
    data_manifest_path, wide_path, long_path, data_identity = _validate_data_manifest(
        root, roster, protocol
    )
    contract = build_design_contract(
        design_path=design_path,
        manifest_path=study_manifest_path,
        experiment_config_path=experiment_config_path,
        data_version=CONFIRMATORY_DATA_VERSION,
        evaluation_split=EXTERNAL_EVALUATION_SPLIT,
        data_version_manifest_path=data_manifest_path,
    )
    provenance = contract.get("code_provenance")
    if not isinstance(provenance, Mapping):
        raise TypeError("external design contract lacks code_provenance")
    if provenance.get("relevant_source_clean") is not True:
        raise RuntimeError(
            "external confirmation requires clean, committed relevant source; "
            f"status={provenance.get('status')!r}, "
            f"dirty={provenance.get('dirty_tracked_paths', [])}, "
            f"untracked={provenance.get('relevant_untracked_paths', [])}"
        )
    canonical_contract = {
        key: value for key, value in contract.items() if key != "code_provenance"
    }
    if canonical_contract.get("data_version") != CONFIRMATORY_DATA_VERSION:
        raise ValueError("external design contract has the wrong data_version")
    if canonical_contract.get("evaluation_split") != EXTERNAL_EVALUATION_SPLIT:
        raise ValueError("external design contract has the wrong evaluation_split")
    return ConfirmatoryEvaluationInputs(
        protocol=protocol,
        roster=roster,
        model_design=model_design,
        selected_models=selected_models,
        training_seeds=_frozen_training_seeds(design_path),
        data_root=root,
        data_manifest_path=data_manifest_path,
        wide_path=wide_path,
        long_path=long_path,
        data_manifest_identity=data_identity,
        evidence_contract=canonical_contract,
        code_provenance=dict(provenance),
    )


def build_external_confirmation_grid(
    *,
    training_seeds: Sequence[int],
    data_version: str = CONFIRMATORY_DATA_VERSION,
    mask_seed: int = EXTERNAL_MASK_SEED,
) -> ExperimentGrid:
    """Build the exact frozen 60-scenario external confirmation grid."""

    normalized_seeds = tuple(int(value) for value in training_seeds)
    if not normalized_seeds or len(set(normalized_seeds)) != len(normalized_seeds):
        raise ValueError("external training seeds must be non-empty and unique")
    conditions: list[ExperimentCondition] = []
    for information_condition in EXTERNAL_INFORMATION_CONDITIONS:
        token = "FULL" if information_condition == "full_information" else "NOMET"
        layout = f"{information_condition}_frontier"
        for site_id in FROZEN_SITE_IDS:
            conditions.append(
                ExperimentCondition(
                    experiment="EXT_POINT",
                    condition_id=f"EXT-PNT-{token}-{site_id}-T-P30",
                    mask_type="point",
                    station_ids=(site_id,),
                    variables=("T",),
                    evaluation_variables=("T",),
                    missing_rate=EXTERNAL_POINT_RATE,
                    layout=layout,
                    window_length=EXTERNAL_WINDOW_LENGTH,
                    training_protocol=EXTERNAL_TRAINING_PROTOCOL,
                    validation_scope="frozen_external_confirmation",
                    data_version=data_version,
                    evaluation_split=EXTERNAL_EVALUATION_SPLIT,
                )
            )
            for length in EXTERNAL_BLOCK_LENGTHS:
                conditions.append(
                    ExperimentCondition(
                        experiment="EXT_BLOCK",
                        condition_id=(f"EXT-BLK-{token}-{site_id}-T-D{length:03d}"),
                        mask_type="block",
                        station_ids=(site_id,),
                        variables=("T",),
                        evaluation_variables=("T",),
                        gap_length=length,
                        layout=layout,
                        window_length=EXTERNAL_WINDOW_LENGTH,
                        training_protocol=EXTERNAL_TRAINING_PROTOCOL,
                        validation_scope="frozen_external_confirmation",
                        data_version=data_version,
                        evaluation_split=EXTERNAL_EVALUATION_SPLIT,
                    )
                )
            for length in EXTERNAL_STATION_OUTAGE_LENGTHS:
                conditions.append(
                    ExperimentCondition(
                        experiment="EXT_STATION_OUTAGE",
                        condition_id=(
                            f"EXT-SITE-{token}-{site_id}-HYDRO-D{length:03d}"
                        ),
                        mask_type="station_outage",
                        station_ids=(site_id,),
                        variables=("T", "F", "L"),
                        evaluation_variables=("T",),
                        gap_length=length,
                        layout=layout,
                        outage_mode="hydro-only",
                        window_length=EXTERNAL_WINDOW_LENGTH,
                        training_protocol=EXTERNAL_TRAINING_PROTOCOL,
                        failed_station_ids=(site_id,),
                        validation_scope="frozen_external_confirmation",
                        data_version=data_version,
                        evaluation_split=EXTERNAL_EVALUATION_SPLIT,
                    )
                )
    if len(conditions) != 60 or len({value.condition_id for value in conditions}) != 60:
        raise AssertionError("frozen external grid must contain 60 unique conditions")
    scenarios = tuple(
        ExperimentScenario(condition=condition, mask_seed=int(mask_seed))
        for condition in conditions
    )
    return ExperimentGrid(
        suite="external_confirmation",
        conditions=tuple(conditions),
        scenarios=scenarios,
        mask_seeds=(int(mask_seed),),
        training_seeds=normalized_seeds,
        external_validation_status="frozen_evaluate_once",
    )


def _information_condition(condition: ExperimentCondition) -> str:
    layout = str(condition.layout)
    for value in EXTERNAL_INFORMATION_CONDITIONS:
        if layout == f"{value}_frontier":
            return value
    raise ValueError(
        f"external condition has an invalid information frontier: {layout}"
    )


class ExternalConfirmationRunner(ExperimentRunner):
    """Unified runner with the frozen external information-frontier masks."""

    _allow_confirmatory_evaluation = True

    @staticmethod
    def _evidence_role(evaluation_split: str) -> str:
        if evaluation_split != EXTERNAL_EVALUATION_SPLIT:
            raise ValueError(
                "external runner only permits evaluation_split=confirmatory"
            )
        return EXTERNAL_EVIDENCE_ROLE

    def _generate_mask(
        self, scenario: ExperimentScenario
    ) -> tuple[np.ndarray, dict[str, Any]]:
        mask, metadata = super()._generate_mask(scenario)
        information_condition = _information_condition(scenario.condition)
        target_index = self.data.variable_names.index("T")
        target_station_indices = [
            self.data.station_ids.index(value)
            for value in scenario.condition.station_ids
        ]
        target_dates = np.zeros(len(self.data.dates), dtype=bool)
        for station_index in target_station_indices:
            target_dates |= mask[:, station_index, target_index]
        if not target_dates.any():
            raise ValueError("external scenario has no masked target-T cells")

        meteorology_indices = [
            self.data.variable_names.index(value) for value in METEOROLOGY_VARIABLES
        ]
        eligible = (
            self.data.natural_observed
            & self.data.quality_approved
            & np.isfinite(self.data.values)
        )
        expected_auxiliary = np.zeros_like(mask, dtype=bool)
        for variable_index in meteorology_indices:
            expected_auxiliary[:, :, variable_index] = (
                target_dates[:, None] & eligible[:, :, variable_index]
            )
        before = mask.copy()
        if information_condition == "no_meteorology":
            mask |= expected_auxiliary
        elif np.any(mask[:, :, meteorology_indices]):
            raise ValueError("full-information external mask hides meteorology")
        auxiliary_cells = int((mask & ~before).sum())
        if information_condition == "no_meteorology":
            observed_auxiliary = mask[:, :, meteorology_indices]
            expected_selected = expected_auxiliary[:, :, meteorology_indices]
            if not np.array_equal(observed_auxiliary, expected_selected):
                raise ValueError("no-meteorology mask does not exactly remove group D")
        metadata = dict(metadata)
        metadata.update(
            {
                "information_condition": information_condition,
                "frontier_estimand": "external_information_availability",
                "primary_target_masked_cells": int(mask[:, :, target_index].sum()),
                "auxiliary_meteorology_masked_cells": auxiliary_cells,
                "meteorology_removal_scope": (
                    "all_sites_on_target_gap_dates"
                    if information_condition == "no_meteorology"
                    else "none"
                ),
                "masked_cells": int(mask.sum()),
            }
        )
        self._validate_scenario_mask(scenario, mask, metadata)
        _save_compact_mask(
            mask,
            metadata,
            self.mask_dir,
            dates=self.data.dates,
            station_ids=self.data.station_ids,
            variable_names=self.data.variable_names,
        )
        return mask, metadata


def _expected_run_units(
    grid: ExperimentGrid,
    models: Sequence[str],
    training_seeds: Sequence[int],
) -> tuple[str, ...]:
    units: list[str] = []
    for scenario in grid.scenarios:
        for model in models:
            seeds: Sequence[int | None] = (
                tuple(training_seeds) if model in TRAINABLE_MODELS else (None,)
            )
            units.extend(
                f"{scenario.scenario_id}|{model}:{seed if seed is not None else 'none'}"
                for seed in seeds
            )
    return tuple(sorted(units))


def _frame_run_unit_keys(frame: pd.DataFrame) -> set[str]:
    if frame.empty:
        return set()
    return {
        f"{row.scenario_id}|{row.model}:"
        f"{int(row.training_seed) if pd.notna(row.training_seed) else 'none'}"
        for row in frame[["scenario_id", "model", "training_seed"]].itertuples(
            index=False
        )
    }


def _mask_identities(
    mask_dir: Path, scenarios: Sequence[ExperimentScenario]
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for scenario in scenarios:
        mask = mask_dir / "scenarios" / f"{scenario.scenario_id}.npz"
        metadata = mask_dir / "scenarios" / f"{scenario.scenario_id}.json"
        if not mask.is_file() or not metadata.is_file():
            raise FileNotFoundError(
                f"external mask artifacts are incomplete: {scenario.scenario_id}"
            )
        result[scenario.scenario_id] = {
            "mask_sha256": file_sha256(mask),
            "mask_metadata_sha256": file_sha256(metadata),
        }
    return result


def _checkpoint_identities(
    runner_manifest: Mapping[str, Any],
) -> dict[tuple[str, int], str]:
    values = runner_manifest.get("training_checkpoints")
    if not isinstance(values, list):
        raise TypeError("runner manifest lacks training_checkpoints")
    result: dict[tuple[str, int], str] = {}
    for raw in values:
        if not isinstance(raw, Mapping):
            raise TypeError("runner checkpoint summary must be a mapping")
        model = raw.get("model")
        seed = raw.get("training_seed")
        identity = raw.get("checkpoint")
        if model is None or seed is None or not isinstance(identity, Mapping):
            continue
        digest = identity.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"checkpoint identity is incomplete for {model}:{seed}")
        result[(str(model), int(seed))] = digest
    return result


def _annotate_evidence_rows(
    frame: pd.DataFrame,
    *,
    inputs: ConfirmatoryEvaluationInputs,
    grid: ExperimentGrid,
    mask_identities: Mapping[str, Mapping[str, str]],
    checkpoint_identities: Mapping[tuple[str, int], str],
) -> pd.DataFrame:
    result = frame.copy()
    scenario_information = {
        scenario.scenario_id: _information_condition(scenario.condition)
        for scenario in grid.scenarios
    }
    result["formal_evidence"] = True
    result["evidence_role"] = EXTERNAL_EVIDENCE_ROLE
    result["information_condition"] = result["scenario_id"].map(scenario_information)
    result["seed"] = np.where(
        result["training_seed"].notna(),
        result["training_seed"],
        result["mask_seed"],
    ).astype("int64")
    result["seed_role"] = np.where(
        result["training_seed"].notna(), "training_seed", "mask_seed"
    )

    def run_unit_key(row: Any) -> str:
        seed = int(row.training_seed) if pd.notna(row.training_seed) else "none"
        return f"{row.scenario_id}|{row.model}:{seed}"

    run_units = [
        run_unit_key(row)
        for row in result[["scenario_id", "model", "training_seed"]].itertuples(
            index=False
        )
    ]
    result["run_unit_sha256"] = [
        _canonical_sha256(
            {
                "run_unit": run_unit,
                "design_version": inputs.evidence_contract["design_version"],
            }
        )
        for run_unit in run_units
    ]
    result["mask_sha256"] = result["scenario_id"].map(
        {key: value["mask_sha256"] for key, value in mask_identities.items()}
    )
    result["mask_metadata_sha256"] = result["scenario_id"].map(
        {key: value["mask_metadata_sha256"] for key, value in mask_identities.items()}
    )
    result["checkpoint_sha256"] = [
        checkpoint_identities.get((str(row.model), int(row.training_seed)))
        if pd.notna(row.training_seed)
        else None
        for row in result[["model", "training_seed"]].itertuples(index=False)
    ]
    return result


def _validate_output_rows(
    daily: pd.DataFrame,
    events: pd.DataFrame,
    *,
    inputs: ConfirmatoryEvaluationInputs,
    expected_run_units: Sequence[str],
) -> dict[str, Any]:
    expected = set(expected_run_units)
    for name, frame in (("daily", daily), ("events", events)):
        missing = sorted(REQUIRED_ROW_IDENTITY_FIELDS.difference(frame.columns))
        if missing:
            raise ValueError(f"external {name} rows lack identity fields: {missing}")
        if frame.empty:
            raise ValueError(f"external {name} evidence is empty")
        exact_values = {
            "data_version": CONFIRMATORY_DATA_VERSION,
            "evaluation_split": EXTERNAL_EVALUATION_SPLIT,
            "evidence_role": EXTERNAL_EVIDENCE_ROLE,
            "formal_evidence": True,
        }
        for field, value in exact_values.items():
            observed = tuple(frame[field].drop_duplicates().tolist())
            if observed != (value,):
                raise ValueError(
                    f"external {name} {field} identity mismatch: {observed!r}"
                )
        if frame[list(REQUIRED_ROW_IDENTITY_FIELDS)].isna().any().any():
            raise ValueError(f"external {name} rows contain null required identities")
        if _frame_run_unit_keys(frame) != expected:
            raise ValueError(f"external {name} run-unit set is incomplete")
    if daily.duplicated(DAILY_KEY).any():
        raise ValueError("external daily evidence contains duplicate primary keys")
    if events.duplicated(EVENT_KEY).any():
        raise ValueError("external event evidence contains duplicate primary keys")
    if not np.isfinite(pd.to_numeric(daily["y_true"], errors="coerce")).all():
        raise ValueError("external daily truth contains non-finite values")
    if not np.isfinite(pd.to_numeric(daily["y_pred"], errors="coerce")).all():
        raise ValueError("external daily predictions contain non-finite values")
    for field in ("MAE", "RMSE"):
        if (
            field not in events
            or not np.isfinite(pd.to_numeric(events[field], errors="coerce")).all()
        ):
            raise ValueError(f"external event metric {field} is not finite")
    return {
        "daily_rows": len(daily),
        "event_rows": len(events),
        "completed_run_unit_count": len(expected),
        "finite_prediction_rows": len(daily),
        "finite_event_metric_rows": len(events),
    }


def _validate_runner_manifest(
    path: Path,
    *,
    inputs: ConfirmatoryEvaluationInputs,
    expected_run_units: Sequence[str],
    scenario_count: int,
) -> dict[str, Any]:
    manifest, _ = _strict_json_mapping(path)
    required_true = (
        "run_unit_complete",
        "evidence_complete",
        "finite_predictions",
        "finite_event_metrics",
        "checkpoint_contract_complete",
        "formal_training_seed_complete",
    )
    failed = [name for name in required_true if manifest.get(name) is not True]
    if failed:
        raise RuntimeError(f"external runner completion gates failed: {failed}")
    if manifest.get("retryable_run_unit_count") != 0:
        raise RuntimeError("external runner contains retryable failures")
    if manifest.get("structural_skip_run_unit_count") != 0:
        raise RuntimeError("external runner contains structural model skips")
    if manifest.get("expected_run_unit_keys") != sorted(expected_run_units):
        raise RuntimeError("external runner run-unit contract mismatch")
    expected_fields = {
        "suite": "external_confirmation",
        "grid_scenario_count": scenario_count,
        "selected_scenarios": scenario_count,
        "data_version": CONFIRMATORY_DATA_VERSION,
        "evaluation_split": EXTERNAL_EVALUATION_SPLIT,
        "evidence_role": EXTERNAL_EVIDENCE_ROLE,
        "design_version": inputs.evidence_contract["design_version"],
    }
    mismatches = {
        field: (manifest.get(field), value)
        for field, value in expected_fields.items()
        if manifest.get(field) != value
    }
    if mismatches:
        raise RuntimeError(f"external runner manifest mismatch: {mismatches}")
    return manifest


def _atomic_json(value: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(_canonical_json_bytes(dict(value)) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def _exclusive_json(value: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise FileExistsError(
            f"confirmatory evaluation has already been started or completed: {path}"
        ) from error
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical_json_bytes(dict(value)) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _artifact_inventory(
    root: Path, *, exclude: Sequence[str] = ()
) -> dict[str, dict[str, Any]]:
    excluded = set(exclude)
    return {
        path.relative_to(root).as_posix(): {
            "sha256": file_sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.relative_to(root).as_posix() not in excluded
    }


def _lock_payload(
    inputs: ConfirmatoryEvaluationInputs,
    output_dir: Path,
    *,
    status: str,
) -> dict[str, Any]:
    return {
        "schema_version": EXTERNAL_LOCK_SCHEMA_VERSION,
        "status": status,
        "started_at_utc": _utc_now(),
        "evaluate_once": True,
        "output_dir": str(output_dir.resolve()),
        "data_version": CONFIRMATORY_DATA_VERSION,
        "data_version_manifest_sha256": inputs.data_manifest_identity[
            "manifest_sha256"
        ],
        "design_version": inputs.evidence_contract["design_version"],
        "evaluation_split": EXTERNAL_EVALUATION_SPLIT,
        "evidence_role": EXTERNAL_EVIDENCE_ROLE,
        "formal_evidence": True,
        "finalized_model_roster_sha256": inputs.roster.manifest_sha256,
        "selected_models": list(inputs.selected_models),
    }


def confirmatory_once_lock_path(data_root: str | Path) -> Path:
    """Return the sole lock location bound to one external data-version root."""

    root = Path(data_root).resolve()
    return root.parent / f".{root.name}.confirmatory-evaluation-once.lock.json"


@dataclass(frozen=True)
class ConfirmatoryFeasibilityResult:
    """Mask/coverage artifacts from a lock-free confirmatory dry-run."""

    report: dict[str, Any]
    mask_contract: pd.DataFrame
    coverage: pd.DataFrame
    output_dir: Path
    once_lock_created: Literal[False]
    performance_metrics_computed: Literal[False]
    models_trained: Literal[False]


def _performance_metric_columns(frame: pd.DataFrame) -> tuple[str, ...]:
    forbidden = ("mae", "rmse", "skill", "nse", "kge")
    return tuple(
        str(column)
        for column in frame.columns
        if str(column).strip().lower() in forbidden
    )


def materialize_external_masks(
    grid: ExperimentGrid,
    *,
    inputs: ConfirmatoryEvaluationInputs,
    mask_dir: str | Path,
    design_path: str | Path,
    experiment_config_path: str | Path,
    study_manifest_path: str | Path,
) -> pd.DataFrame:
    """Construct all 60 external masks without training or scoring."""

    if len(grid.scenarios) != 60:
        raise AssertionError("frozen external grid must contain 60 scenarios")
    output_masks = Path(mask_dir)
    output_masks.mkdir(parents=True, exist_ok=True)
    runner = ExternalConfirmationRunner(
        grid,
        wide_path=inputs.wide_path,
        quality_path=inputs.long_path,
        output_dir=output_masks / ".feasibility-runner-unused",
        mask_dir=output_masks,
        config_path=experiment_config_path,
        design_path=design_path,
        manifest_path=study_manifest_path,
        data_version_manifest_path=inputs.data_manifest_path,
        models=("climatology",),
        training_seeds=(),
        resume=False,
    )
    expected_dates = len(runner.data.dates)
    expected_stations = len(runner.data.station_ids)
    expected_variables = len(runner.data.variable_names)
    if tuple(runner.data.variable_names) != FROZEN_VARIABLES:
        raise ValueError(
            "external mask axes must use FROZEN_VARIABLES ending in Rs, not DH"
        )
    target_index = runner.data.variable_names.index("T")
    meteorology_indices = [
        runner.data.variable_names.index(value) for value in METEOROLOGY_VARIABLES
    ]
    truth_ok = (
        runner.data.natural_observed
        & runner.data.quality_approved
        & np.isfinite(runner.data.values)
    )
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for scenario in grid.scenarios:
        mask, metadata = runner._generate_mask(scenario)
        del metadata
        if mask.shape != (expected_dates, expected_stations, expected_variables):
            failures.append(
                f"{scenario.scenario_id}: mask shape {mask.shape} != "
                f"({expected_dates}, {expected_stations}, {expected_variables})"
            )
        information_condition = _information_condition(scenario.condition)
        masked_t = mask[:, :, target_index]
        approved_finite_masked_t = int((masked_t & truth_ok[:, :, target_index]).sum())
        masked_t_cells = int(masked_t.sum())
        if masked_t_cells == 0:
            failures.append(f"{scenario.scenario_id}: no masked evaluation T cells")
        if np.any(masked_t & ~truth_ok[:, :, target_index]):
            failures.append(
                f"{scenario.scenario_id}: masked T cells lack approved finite truth"
            )
        auxiliary_cells = int(mask[:, :, meteorology_indices].sum())
        if information_condition == "full_information" and auxiliary_cells:
            failures.append(
                f"{scenario.scenario_id}: full_information hid meteorology"
            )
        mask_file = output_masks / "scenarios" / f"{scenario.scenario_id}.npz"
        metadata_file = output_masks / "scenarios" / f"{scenario.scenario_id}.json"
        rows.append(
            {
                "schema_version": FEASIBILITY_MASK_CONTRACT_SCHEMA,
                "scenario_id": scenario.scenario_id,
                "condition_id": scenario.condition.condition_id,
                "mask_type": scenario.condition.mask_type,
                "site_id": scenario.condition.station_ids[0],
                "information_condition": information_condition,
                "gap_length": scenario.condition.gap_length,
                "missing_rate": scenario.condition.missing_rate,
                "masked_T_cells": masked_t_cells,
                "approved_finite_masked_T_cells": approved_finite_masked_t,
                "auxiliary_meteorology_masked_cells": auxiliary_cells,
                "mask_sha256": file_sha256(mask_file) if mask_file.is_file() else "",
                "mask_metadata_sha256": (
                    file_sha256(metadata_file) if metadata_file.is_file() else ""
                ),
                "window_length": scenario.condition.window_length,
                "data_version": CONFIRMATORY_DATA_VERSION,
                "evaluation_split": EXTERNAL_EVALUATION_SPLIT,
            }
        )
    if failures:
        raise ValueError(
            "confirmatory mask constructability failed: " + "; ".join(failures)
        )
    return pd.DataFrame(rows)


def assert_confirmatory_masks_constructable(
    *,
    inputs: ConfirmatoryEvaluationInputs,
    grid: ExperimentGrid,
    design_path: str | Path,
    experiment_config_path: str | Path,
    study_manifest_path: str | Path,
) -> pd.DataFrame:
    """Dry-run all 60 masks in a throwaway directory before any once-lock."""

    staging = Path(
        tempfile.mkdtemp(
            prefix=".confirmatory-mask-dry-run.",
            dir=inputs.data_root.parent,
        )
    )
    try:
        return materialize_external_masks(
            grid,
            inputs=inputs,
            mask_dir=staging / "masks",
            design_path=design_path,
            experiment_config_path=experiment_config_path,
            study_manifest_path=study_manifest_path,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def run_confirmatory_feasibility(
    *,
    data_root: str | Path,
    finalized_model_roster_path: str | Path,
    output_dir: str | Path,
    design_path: str | Path = DEFAULT_DESIGN_PATH,
    study_manifest_path: str | Path = "study_manifest.yaml",
    experiment_config_path: str | Path = "configs/experiments.yaml",
    selection_data_version_manifest_path: str | Path | None = None,
) -> ConfirmatoryFeasibilityResult:
    """Generate all 60 masks; audit truth/coverage; never lock or train."""

    inputs = preflight_confirmatory_evaluation(
        data_root=data_root,
        finalized_model_roster_path=finalized_model_roster_path,
        design_path=design_path,
        study_manifest_path=study_manifest_path,
        experiment_config_path=experiment_config_path,
        selection_data_version_manifest_path=selection_data_version_manifest_path,
    )
    lock = confirmatory_once_lock_path(inputs.data_root)
    if lock.exists():
        raise FileExistsError(
            "confirmatory once-lock already exists; feasibility is only "
            f"permitted before evaluate-once: {lock}"
        )
    output = Path(output_dir).resolve()
    if output.exists():
        raise FileExistsError(
            f"refusing existing confirmatory feasibility output: {output}"
        )
    grid = build_external_confirmation_grid(training_seeds=inputs.training_seeds)
    if len(grid.scenarios) != 60:
        raise AssertionError("frozen external grid must contain 60 scenarios")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.staging.", dir=output.parent)
    )
    try:
        mask_contract = materialize_external_masks(
            grid,
            inputs=inputs,
            mask_dir=staging / "masks",
            design_path=design_path,
            experiment_config_path=experiment_config_path,
            study_manifest_path=study_manifest_path,
        )
        long_data = pd.read_parquet(inputs.long_path)
        availability = build_availability_report(long_data, inputs.protocol)
        coverage = availability.rename(
            columns={"usable_days": "usable_finite_approved_days"}
        )[
            [
                "split",
                "site_id",
                "variable",
                "expected_days",
                "quality_approved_days",
                "usable_finite_approved_days",
                "usable_fraction",
                "data_version",
            ]
        ].copy()
        if _performance_metric_columns(mask_contract) or _performance_metric_columns(
            coverage
        ):
            raise RuntimeError("feasibility artifacts must not contain skill metrics")
        mask_path = staging / "confirmatory_mask_contract.parquet"
        coverage_path = staging / "confirmatory_coverage_by_site_split_variable.csv"
        mask_contract.to_parquet(mask_path, index=False)
        coverage.to_csv(coverage_path, index=False)
        checks = {
            "complete_grid": len(mask_contract) == 60,
            "approved_finite_target_truth": bool(
                mask_contract["approved_finite_masked_T_cells"].gt(0).all()
                and mask_contract["approved_finite_masked_T_cells"]
                .eq(mask_contract["masked_T_cells"])
                .all()
            ),
            "exact_mask_lengths": True,
            "information_condition_masks": set(
                mask_contract["information_condition"]
            )
            == set(EXTERNAL_INFORMATION_CONDITIONS),
            "structural_skip_policy": True,
            "once_lock_absent": not lock.exists(),
        }
        failures = [name for name, passed in checks.items() if not passed]
        report = {
            "schema_version": FEASIBILITY_SCHEMA_VERSION,
            "status": "failed" if failures else "passed",
            "performance_metrics_computed": False,
            "models_trained": False,
            "once_lock_created": False,
            "design_version": inputs.evidence_contract["design_version"],
            "design_version": inputs.evidence_contract["design_version"],
            "data_version": CONFIRMATORY_DATA_VERSION,
            "data_version_manifest_sha256": inputs.data_manifest_identity[
                "manifest_sha256"
            ],
            "roster_sha256": inputs.roster.manifest_sha256,
            "scenario_count": 60,
            "mask_seed": EXTERNAL_MASK_SEED,
            "information_conditions": list(EXTERNAL_INFORMATION_CONDITIONS),
            "structural_skip_policy": {
                "evaluation_requires_zero_structural_skips": True,
                "codes_considered": [
                    "unsupported_model_target",
                    "required_input_unavailable",
                ],
                "feasibility_checks": [
                    "every_scenario_has_nonzero_approved_finite_masked_T",
                    "no_scenario_has_empty_evaluation_cells_for_target_T",
                ],
                "models_not_fitted": True,
            },
            "checks": checks,
            "failures": failures,
            "artifact_inventory": {
                "confirmatory_mask_contract.parquet": {
                    "sha256": file_sha256(mask_path),
                    "bytes": mask_path.stat().st_size,
                },
                "confirmatory_coverage_by_site_split_variable.csv": {
                    "sha256": file_sha256(coverage_path),
                    "bytes": coverage_path.stat().st_size,
                },
            },
        }
        _assert_finite_json(report)
        report_path = staging / "confirmatory_feasibility_report.json"
        _atomic_json(report, report_path)
        if lock.exists():
            raise RuntimeError("feasibility must not create a confirmatory once-lock")
        if failures:
            raise ValueError("confirmatory feasibility failed: " + ", ".join(failures))
        os.rename(staging, output)
        return ConfirmatoryFeasibilityResult(
            report=report,
            mask_contract=mask_contract,
            coverage=coverage,
            output_dir=output,
            once_lock_created=False,
            performance_metrics_computed=False,
            models_trained=False,
        )
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


def _portable_scenario_contract(grid: ExperimentGrid) -> dict[str, Any]:
    return {
        "schema_version": EXTERNAL_GRID_SCHEMA_VERSION,
        "mask_seed": EXTERNAL_MASK_SEED,
        "point_T_rates": [EXTERNAL_POINT_RATE],
        "block_T_days": list(EXTERNAL_BLOCK_LENGTHS),
        "hydrological_station_outage_days": list(EXTERNAL_STATION_OUTAGE_LENGTHS),
        "frontier_information_conditions": list(EXTERNAL_INFORMATION_CONDITIONS),
        "site_ids": list(FROZEN_SITE_IDS),
        "target": "T",
        "scenario_count": len(grid.scenarios),
        "conditions": [asdict(condition) for condition in grid.conditions],
    }


def run_confirmatory_evaluation(
    *,
    data_root: str | Path,
    finalized_model_roster_path: str | Path,
    output_dir: str | Path,
    once_lock_path: str | Path | None = None,
    design_path: str | Path = DEFAULT_DESIGN_PATH,
    study_manifest_path: str | Path = "study_manifest.yaml",
    experiment_config_path: str | Path = "configs/experiments.yaml",
    selection_data_version_manifest_path: str | Path | None = None,
    runner_factory: Callable[..., ExperimentRunner] = ExternalConfirmationRunner,
) -> dict[str, Any]:
    """Execute the external grid once and publish one immutable atomic bundle.

    Mask constructability for all 60 scenarios is verified before the once-lock
    is created. After the lock exists, a crash during model execution may expose
    performance, so a failed attempt cannot be silently retried as though
    confirmation were unseen.
    """

    inputs = preflight_confirmatory_evaluation(
        data_root=data_root,
        finalized_model_roster_path=finalized_model_roster_path,
        design_path=design_path,
        study_manifest_path=study_manifest_path,
        experiment_config_path=experiment_config_path,
        selection_data_version_manifest_path=selection_data_version_manifest_path,
    )
    output = Path(output_dir).resolve()
    lock = confirmatory_once_lock_path(inputs.data_root)
    if once_lock_path is not None and Path(once_lock_path).resolve() != lock:
        raise ValueError(
            "once_lock_path is fixed by the external data-version root and "
            "cannot be redirected"
        )
    if output.exists():
        raise FileExistsError(f"refusing existing confirmatory output: {output}")
    if lock.exists():
        raise FileExistsError(
            f"confirmatory evaluation has already been started or completed: {lock}"
        )
    if output == lock or output in lock.parents or lock in output.parents:
        raise ValueError("confirmatory output and once-lock paths must be independent")
    grid = build_external_confirmation_grid(training_seeds=inputs.training_seeds)
    expected_run_units = _expected_run_units(
        grid, inputs.selected_models, inputs.training_seeds
    )
    grid_contract = _portable_scenario_contract(grid)
    grid_sha256 = _canonical_sha256(grid_contract)
    assert_confirmatory_masks_constructable(
        inputs=inputs,
        grid=grid,
        design_path=design_path,
        experiment_config_path=experiment_config_path,
        study_manifest_path=study_manifest_path,
    )
    if lock.exists():
        raise FileExistsError(
            f"confirmatory evaluation has already been started or completed: {lock}"
        )
    initial_lock = {
        **_lock_payload(inputs, output, status="started"),
        "grid_sha256": grid_sha256,
        "expected_run_unit_count": len(expected_run_units),
        "expected_run_unit_sha256": _canonical_sha256(list(expected_run_units)),
        "mask_constructability_verified_before_lock": True,
    }
    _exclusive_json(initial_lock, lock)

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.staging.", dir=output.parent)
    )
    runner_output = staging / "runner"
    mask_dir = staging / "masks"
    try:
        runner = runner_factory(
            grid,
            wide_path=inputs.wide_path,
            quality_path=inputs.long_path,
            output_dir=runner_output,
            mask_dir=mask_dir,
            config_path=experiment_config_path,
            design_path=design_path,
            manifest_path=study_manifest_path,
            data_version_manifest_path=inputs.data_manifest_path,
            models=inputs.selected_models,
            training_seeds=inputs.training_seeds,
            resume=False,
        )
        if runner.evidence_contract != inputs.evidence_contract:
            raise RuntimeError(
                "external preflight and runner evidence contracts differ"
            )
        daily, events = runner.run()
        runner_manifest_path = runner_output / "run_manifest.json"
        runner_manifest = _validate_runner_manifest(
            runner_manifest_path,
            inputs=inputs,
            expected_run_units=expected_run_units,
            scenario_count=len(grid.scenarios),
        )
        masks = _mask_identities(mask_dir, grid.scenarios)
        checkpoints = _checkpoint_identities(runner_manifest)
        daily = _annotate_evidence_rows(
            daily,
            inputs=inputs,
            grid=grid,
            mask_identities=masks,
            checkpoint_identities=checkpoints,
        )
        events = _annotate_evidence_rows(
            events,
            inputs=inputs,
            grid=grid,
            mask_identities=masks,
            checkpoint_identities=checkpoints,
        )
        checks = _validate_output_rows(
            daily,
            events,
            inputs=inputs,
            expected_run_units=expected_run_units,
        )
        daily_path = staging / "daily_predictions.parquet"
        events_path = staging / "event_metrics.parquet"
        daily.to_parquet(daily_path, index=False)
        events.to_parquet(events_path, index=False)
        if file_sha256(daily_path) == file_sha256(events_path):
            raise RuntimeError("external output table identities unexpectedly collide")

        run_units = []
        for run_unit in expected_run_units:
            scenario_id, model_seed = run_unit.split("|", maxsplit=1)
            model, raw_seed = model_seed.rsplit(":", maxsplit=1)
            daily_rows = int(
                (
                    daily["scenario_id"].eq(scenario_id)
                    & daily["model"].eq(model)
                    & (
                        daily["training_seed"].isna()
                        if raw_seed == "none"
                        else daily["training_seed"].eq(int(raw_seed))
                    )
                ).sum()
            )
            event_rows = int(
                (
                    events["scenario_id"].eq(scenario_id)
                    & events["model"].eq(model)
                    & (
                        events["training_seed"].isna()
                        if raw_seed == "none"
                        else events["training_seed"].eq(int(raw_seed))
                    )
                ).sum()
            )
            run_units.append(
                {
                    "run_unit_key": run_unit,
                    "scenario_id": scenario_id,
                    "model": model,
                    "training_seed": None if raw_seed == "none" else int(raw_seed),
                    "mask_seed": EXTERNAL_MASK_SEED,
                    "daily_rows": daily_rows,
                    "event_rows": event_rows,
                    "finite_predictions": daily_rows > 0,
                    "finite_event_metrics": event_rows > 0,
                    "mask_sha256": masks[scenario_id]["mask_sha256"],
                    "mask_metadata_sha256": masks[scenario_id]["mask_metadata_sha256"],
                    "checkpoint_sha256": (
                        checkpoints.get((model, int(raw_seed)))
                        if raw_seed != "none"
                        else None
                    ),
                }
            )
        if not all(
            value["finite_predictions"] and value["finite_event_metrics"]
            for value in run_units
        ):
            raise RuntimeError("external run-unit finite-evidence audit failed")

        inputs_manifest = {
            "design_freeze": {
                "path": str(Path(design_path).resolve()),
                "sha256": file_sha256(design_path),
            },
            "study_manifest": {
                "path": str(Path(study_manifest_path).resolve()),
                "sha256": file_sha256(study_manifest_path),
            },
            "experiment_config": {
                "path": str(Path(experiment_config_path).resolve()),
                "sha256": file_sha256(experiment_config_path),
            },
            "data_version_manifest": {
                "path": str(inputs.data_manifest_path),
                "sha256": inputs.data_manifest_identity["manifest_sha256"],
            },
            "daily_wide": {
                "path": str(inputs.wide_path),
                "sha256": file_sha256(inputs.wide_path),
            },
            "daily_long": {
                "path": str(inputs.long_path),
                "sha256": file_sha256(inputs.long_path),
            },
            "finalized_model_roster": {
                "path": inputs.roster.manifest_path,
                "sha256": inputs.roster.manifest_sha256,
            },
        }
        inventory = _artifact_inventory(
            staging,
            exclude=(
                "completion_manifest.json",
                "completion_manifest.json.sha256",
            ),
        )
        manifest: dict[str, Any] = {
            "schema_version": EXTERNAL_CONFIRMATION_SCHEMA_VERSION,
            "status": "complete",
            "complete": True,
            "immutable": True,
            "completed_at_utc": _utc_now(),
            "evaluate_once": True,
            "data_version": CONFIRMATORY_DATA_VERSION,
            "design_version": inputs.evidence_contract["design_version"],
            "evaluation_split": EXTERNAL_EVALUATION_SPLIT,
            "evidence_role": EXTERNAL_EVIDENCE_ROLE,
            "formal_evidence": True,
            "fit_split": "train",
            "tuning_split": "validation",
            "periods": {
                label: {"start": start, "end": end}
                for label, start, end in FROZEN_PERIODS
            },
            "confirmatory_metric_uses": 1,
            "model_selection_on_confirmatory": False,
            "selected_models": list(inputs.selected_models),
            "best_traditional_model": inputs.roster.best_traditional_model,
            "proposed_decision": inputs.roster.proposed_decision,
            "training_seeds": list(inputs.training_seeds),
            "mask_seed": EXTERNAL_MASK_SEED,
            "model_protocols": _model_protocols(
                inputs.selected_models,
                inputs.model_design,
                inputs.training_seeds,
            ),
            "finalized_model_roster": inputs.roster.metadata(),
            "evidence_contract": inputs.evidence_contract,
            "code_provenance": inputs.code_provenance,
            "grid": grid_contract,
            "grid_sha256": grid_sha256,
            "expected_run_unit_keys": list(expected_run_units),
            "expected_run_unit_count": len(expected_run_units),
            "completed_run_unit_keys": list(expected_run_units),
            "completed_run_unit_count": len(expected_run_units),
            "run_unit_complete": True,
            "finite_predictions": True,
            "finite_event_metrics": True,
            "checkpoint_contract_complete": True,
            "retryable_run_unit_count": 0,
            "structural_skip_run_unit_count": 0,
            "run_units": run_units,
            "checks": checks,
            "input_identities": inputs_manifest,
            "output_identities": {
                "daily_predictions.parquet": inventory["daily_predictions.parquet"],
                "event_metrics.parquet": inventory["event_metrics.parquet"],
                "runner/run_manifest.json": inventory["runner/run_manifest.json"],
            },
            "artifact_inventory": inventory,
            "artifact_count": len(inventory),
            "generic_runner_formal_mask_seed_gate_applicable": False,
            "external_mask_seed_contract": {
                "schema_version": EXTERNAL_GRID_SCHEMA_VERSION,
                "seed": EXTERNAL_MASK_SEED,
                "exact_seed_count": 1,
                "reason": "frozen_compact_evaluate_once_external_grid",
            },
        }
        completion_path = staging / "completion_manifest.json"
        _atomic_json(manifest, completion_path)
        completion_sha256 = file_sha256(completion_path)
        (staging / "completion_manifest.json.sha256").write_text(
            completion_sha256 + "\n", encoding="ascii"
        )
        if output.exists():
            raise FileExistsError(f"refusing existing confirmatory output: {output}")
        os.rename(staging, output)
        completed_lock = {
            **initial_lock,
            "status": "complete",
            "completed_at_utc": _utc_now(),
            "completion_manifest": str((output / "completion_manifest.json").resolve()),
            "completion_manifest_sha256": completion_sha256,
        }
        _atomic_json(completed_lock, lock)
        return manifest
    except BaseException as error:
        failed_lock = {
            **initial_lock,
            "status": "failed_closed",
            "failed_at_utc": _utc_now(),
            "failure_type": type(error).__name__,
            "retry_permitted": False,
            "staging_path": str(staging.resolve()),
        }
        try:
            _atomic_json(failed_lock, lock)
        except OSError:
            # The original failure is more informative; the exclusive lock
            # remains present even if its status update cannot be replaced.
            ...
        raise


__all__ = [
    "ConfirmatoryEvaluationInputs",
    "ConfirmatoryFeasibilityResult",
    "EXTERNAL_BLOCK_LENGTHS",
    "EXTERNAL_CONFIRMATION_SCHEMA_VERSION",
    "EXTERNAL_EVALUATION_SPLIT",
    "EXTERNAL_EVIDENCE_ROLE",
    "EXTERNAL_GRID_SCHEMA_VERSION",
    "EXTERNAL_INFORMATION_CONDITIONS",
    "EXTERNAL_MASK_SEED",
    "EXTERNAL_POINT_RATE",
    "EXTERNAL_STATION_OUTAGE_LENGTHS",
    "ExternalConfirmationRunner",
    "FEASIBILITY_MASK_CONTRACT_SCHEMA",
    "FEASIBILITY_SCHEMA_VERSION",
    "assert_confirmatory_masks_constructable",
    "build_external_confirmation_grid",
    "confirmatory_once_lock_path",
    "materialize_external_masks",
    "preflight_confirmatory_evaluation",
    "run_confirmatory_evaluation",
    "run_confirmatory_feasibility",
]
