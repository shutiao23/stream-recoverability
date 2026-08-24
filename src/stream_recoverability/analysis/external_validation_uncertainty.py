"""Mask-placement uncertainty on the external 2021--2022 validation split.

This diagnostic is deliberately separated from the evaluate-once external
confirmation.  It reads the immutable external data bundle and the finalized
validation-only model roster, evaluates repeated artificial masks on the
``validation`` split, and never opens confirmatory outcome artifacts or the
evaluate-once lock.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.data.confirmatory import (
    CONFIRMATORY_DATA_VERSION,
    FROZEN_SITE_IDS,
    load_confirmatory_protocol,
    load_finalized_model_roster,
)
from stream_recoverability.experiments.contracts import DEFAULT_DESIGN_PATH, file_sha256
from stream_recoverability.experiments.external_confirmation import (
    EXTERNAL_BLOCK_LENGTHS,
    EXTERNAL_TRAINING_PROTOCOL,
    EXTERNAL_WINDOW_LENGTH,
    ExternalConfirmationRunner,
    _frozen_training_seeds,
    _strict_json_mapping,
    _validate_access_gate,
    _validate_selected_models,
)
from stream_recoverability.experiments.grid import (
    ExperimentCondition,
    ExperimentGrid,
    ExperimentScenario,
)
from stream_recoverability.experiments.model_registry import load_frozen_model_design

EXTERNAL_VALIDATION_UNCERTAINTY_SCHEMA_VERSION = (
    "external_validation_mask_placement_uncertainty_v1"
)
EXTERNAL_VALIDATION_UNCERTAINTY_ROLE = (
    "post_frozen_external_validation_mask_placement_diagnostic"
)
EXTERNAL_VALIDATION_SPLIT = "validation"
EXTERNAL_VALIDATION_MASK_SEEDS = tuple(range(101, 121))
DOWNSTREAM_DAM_SITE = "02334430"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_json(value: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _prepare_nonconfirmatory_input(
    *,
    data_root: Path,
    staging_root: Path,
    roster: Any,
    protocol: Any,
) -> tuple[Path, Path, Path, dict[str, Any]]:
    """Materialize train+validation rows without exposing confirmatory rows.

    The immutable source manifest and its train/validation split identities are
    checked first.  The wide input is assembled from the two physical split
    files.  The long table is predicate-filtered before it enters a DataFrame.
    """

    manifest_path = data_root / "provenance_manifest.json"
    manifest, raw_manifest = _strict_json_mapping(manifest_path)
    _validate_access_gate(manifest, roster, protocol)
    source_manifest_sha256 = hashlib.sha256(raw_manifest).hexdigest()
    sidecar_path = data_root / "provenance_manifest.json.sha256"
    if (
        not sidecar_path.is_file()
        or sidecar_path.read_text(encoding="ascii") != source_manifest_sha256 + "\n"
    ):
        raise ValueError("external data manifest SHA-256 sidecar mismatch")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise TypeError("external data manifest artifacts must be a mapping")

    allowed_wide: list[pd.DataFrame] = []
    source_split_identities: dict[str, dict[str, Any]] = {}
    for split in ("train", EXTERNAL_VALIDATION_SPLIT):
        name = f"splits/{split}.parquet"
        identity = artifacts.get(name)
        if not isinstance(identity, Mapping):
            raise TypeError(f"external data manifest lacks {name}")
        path = data_root / name
        expected_bytes = identity.get("bytes")
        expected_sha256 = identity.get("sha256")
        if (
            not path.is_file()
            or path.stat().st_size != expected_bytes
            or file_sha256(path) != expected_sha256
        ):
            raise ValueError(f"external allowed split identity mismatch: {name}")
        frame = pd.read_parquet(path)
        if set(frame["split"].astype(str)) != {split}:
            raise ValueError(f"external {split} split contains another split")
        allowed_wide.append(frame)
        source_split_identities[name] = {
            "sha256": str(expected_sha256),
            "bytes": int(expected_bytes),
        }

    wide = pd.concat(allowed_wide, ignore_index=True)
    long_source = data_root / "daily_long.parquet"
    long = pd.read_parquet(
        long_source,
        filters=[("split", "in", ["train", EXTERNAL_VALIDATION_SPLIT])],
    )
    allowed_splits = {"train", EXTERNAL_VALIDATION_SPLIT}
    if (
        set(wide["split"].astype(str)) != allowed_splits
        or set(long["split"].astype(str)) != allowed_splits
    ):
        raise ValueError("restricted external input has an invalid split inventory")
    wide_dates = pd.to_datetime(wide["date"]).dt.normalize()
    long_dates = pd.to_datetime(long["date"]).dt.normalize()
    cutoff = pd.Timestamp("2022-12-31")
    if wide_dates.max() > cutoff or long_dates.max() > cutoff:
        raise RuntimeError("confirmatory-period row entered restricted input")
    if wide_dates.duplicated().any() or not wide_dates.is_monotonic_increasing:
        raise ValueError("restricted external wide dates are not unique and ordered")
    if tuple(wide["data_version"].astype(str).unique()) != (
        CONFIRMATORY_DATA_VERSION,
    ) or tuple(long["data_version"].astype(str).unique()) != (
        CONFIRMATORY_DATA_VERSION,
    ):
        raise ValueError("restricted external input data-version mismatch")

    input_root = staging_root / "restricted_input"
    input_root.mkdir(parents=True)
    wide_path = input_root / "daily_wide.parquet"
    long_path = input_root / "daily_long.parquet"
    wide.to_parquet(wide_path, index=False)
    long.to_parquet(long_path, index=False)
    restricted_manifest = {
        "schema_version": "restricted_external_validation_input_v1",
        "data_version": CONFIRMATORY_DATA_VERSION,
        "allowed_splits": ["train", EXTERNAL_VALIDATION_SPLIT],
        "maximum_date": cutoff.strftime("%Y-%m-%d"),
        "confirmatory_period_rows": 0,
        "source_manifest_sha256": source_manifest_sha256,
        "artifacts": {
            "daily_wide.parquet": {
                "sha256": file_sha256(wide_path),
                "bytes": wide_path.stat().st_size,
            },
            "daily_long.parquet": {
                "sha256": file_sha256(long_path),
                "bytes": long_path.stat().st_size,
            },
        },
    }
    restricted_manifest_path = input_root / "version_manifest.json"
    _atomic_json(restricted_manifest, restricted_manifest_path)
    return (
        wide_path,
        long_path,
        restricted_manifest_path,
        {
            "source_manifest_path": str(manifest_path),
            "source_manifest_sha256": source_manifest_sha256,
            "source_split_identities": source_split_identities,
            "restricted_wide_rows": len(wide),
            "restricted_long_rows": len(long),
            "maximum_date": cutoff.strftime("%Y-%m-%d"),
            "confirmatory_period_rows": 0,
        },
    )


def build_external_validation_uncertainty_grid(
    *,
    training_seeds: Sequence[int],
    mask_seeds: Sequence[int] = EXTERNAL_VALIDATION_MASK_SEEDS,
    data_version: str = CONFIRMATORY_DATA_VERSION,
) -> ExperimentGrid:
    """Build the full-information block grid used by the reported external curve.

    The 15 station-by-gap conditions match the geometry behind the reported
    full-information external curve.  Twenty scenario copies differ only in
    artificial-mask seed and are evaluated exclusively in 2021--2022.
    """

    normalized_training = tuple(int(value) for value in training_seeds)
    normalized_masks = tuple(int(value) for value in mask_seeds)
    if not normalized_training or len(set(normalized_training)) != len(
        normalized_training
    ):
        raise ValueError("training_seeds must be non-empty and unique")
    if len(normalized_masks) != 20 or len(set(normalized_masks)) != 20:
        raise ValueError("mask-placement diagnostic requires exactly 20 unique seeds")
    if any(value < 0 for value in (*normalized_training, *normalized_masks)):
        raise ValueError("all seeds must be non-negative")

    conditions = tuple(
        ExperimentCondition(
            experiment="EXT_VALIDATION_UNCERTAINTY",
            condition_id=f"EXT-VALUNC-BLK-FULL-{site_id}-T-D{length:03d}",
            mask_type="block",
            station_ids=(site_id,),
            variables=("T",),
            evaluation_variables=("T",),
            gap_length=length,
            layout="full_information_frontier",
            window_length=EXTERNAL_WINDOW_LENGTH,
            training_protocol=EXTERNAL_TRAINING_PROTOCOL,
            validation_scope=(
                "post_frozen_external_validation_mask_placement_uncertainty"
            ),
            data_version=data_version,
            evaluation_split=EXTERNAL_VALIDATION_SPLIT,
        )
        for site_id in FROZEN_SITE_IDS
        for length in EXTERNAL_BLOCK_LENGTHS
    )
    scenarios = tuple(
        ExperimentScenario(condition=condition, mask_seed=mask_seed)
        for condition in conditions
        for mask_seed in normalized_masks
    )
    if len(conditions) != 15 or len(scenarios) != 300:
        raise AssertionError("external validation uncertainty grid is incomplete")
    return ExperimentGrid(
        suite="external_validation_uncertainty",
        conditions=conditions,
        scenarios=scenarios,
        mask_seeds=normalized_masks,
        training_seeds=normalized_training,
        external_validation_status=(
            "validation_only_post_frozen_diagnostic_not_confirmatory"
        ),
    )


class ExternalValidationUncertaintyRunner(ExternalConfirmationRunner):
    """External information-mask runner restricted to validation-only evidence."""

    _allow_confirmatory_evaluation = False

    @staticmethod
    def _evidence_role(evaluation_split: str) -> str:
        if evaluation_split != EXTERNAL_VALIDATION_SPLIT:
            raise ValueError(
                "external validation uncertainty only permits "
                "evaluation_split=validation"
            )
        return EXTERNAL_VALIDATION_UNCERTAINTY_ROLE


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{label} lacks required columns: {missing}")


def summarize_external_validation_uncertainty(
    events: pd.DataFrame,
    *,
    models: Sequence[str],
    mask_seeds: Sequence[int] = EXTERNAL_VALIDATION_MASK_SEEDS,
) -> dict[str, pd.DataFrame]:
    """Return seed cells, cell SDs, envelope SDs, paired SDs, and summaries."""

    required = {
        "station_id",
        "model",
        "gap_length",
        "mask_seed",
        "mask_type",
        "pattern",
        "evaluation_split",
        "evidence_role",
        "skill",
        "MAE",
        "n_evaluated",
    }
    _require_columns(events, required, "external validation event metrics")
    selected = events.loc[
        events["mask_type"].astype(str).eq("block")
        & events["pattern"].astype(str).eq("T")
        & events["evaluation_split"].astype(str).eq(EXTERNAL_VALIDATION_SPLIT)
        & events["evidence_role"].astype(str).eq(EXTERNAL_VALIDATION_UNCERTAINTY_ROLE)
    ].copy()
    selected["station_id"] = selected["station_id"].astype(str)
    selected["model"] = selected["model"].astype(str)
    selected["gap_length"] = pd.to_numeric(
        selected["gap_length"], errors="raise"
    ).astype(int)
    selected["mask_seed"] = pd.to_numeric(selected["mask_seed"], errors="raise").astype(
        int
    )
    selected["skill"] = pd.to_numeric(selected["skill"], errors="coerce")
    selected["MAE"] = pd.to_numeric(selected["MAE"], errors="coerce")
    selected["n_evaluated"] = pd.to_numeric(
        selected["n_evaluated"], errors="raise"
    ).astype(int)

    expected_models = tuple(str(value) for value in models)
    expected_seeds = tuple(int(value) for value in mask_seeds)
    key = ["station_id", "gap_length", "model", "mask_seed"]
    if selected.duplicated(key).any():
        raise ValueError("validation uncertainty contains duplicate seed cells")
    expected_count = (
        len(FROZEN_SITE_IDS)
        * len(EXTERNAL_BLOCK_LENGTHS)
        * len(expected_models)
        * len(expected_seeds)
    )
    if len(selected) != expected_count:
        raise ValueError(
            "validation uncertainty seed-cell inventory is incomplete: "
            f"{len(selected)} != {expected_count}"
        )
    if set(selected["station_id"]) != set(FROZEN_SITE_IDS):
        raise ValueError("validation uncertainty station inventory differs from freeze")
    if set(selected["gap_length"]) != set(EXTERNAL_BLOCK_LENGTHS):
        raise ValueError("validation uncertainty gap inventory differs from freeze")
    if set(selected["model"]) != set(expected_models):
        raise ValueError("validation uncertainty model inventory differs from roster")
    if set(selected["mask_seed"]) != set(expected_seeds):
        raise ValueError("validation uncertainty seed inventory is incomplete")
    if (
        not np.isfinite(selected["skill"]).all()
        or not np.isfinite(selected["MAE"]).all()
    ):
        raise ValueError("validation uncertainty requires finite skill and MAE")
    group_sizes = selected.groupby(key[:-1], observed=True).size()
    if not group_sizes.eq(len(expected_seeds)).all():
        raise ValueError("each station-gap-model cell must contain all 20 seeds")

    seed_cells = selected[
        [
            "station_id",
            "gap_length",
            "model",
            "mask_seed",
            "skill",
            "MAE",
            "n_evaluated",
            "evaluation_split",
            "evidence_role",
        ]
    ].sort_values(key, kind="mergesort", ignore_index=True)
    cells = (
        seed_cells.groupby(key[:-1], as_index=False, observed=True)
        .agg(
            n_mask_seeds=("mask_seed", "nunique"),
            mean_skill=("skill", "mean"),
            skill_sd=("skill", "std"),
            min_skill=("skill", "min"),
            max_skill=("skill", "max"),
            mean_MAE_degC=("MAE", "mean"),
            MAE_sd_degC=("MAE", "std"),
            min_n_evaluated=("n_evaluated", "min"),
            max_n_evaluated=("n_evaluated", "max"),
        )
        .sort_values(key[:-1], kind="mergesort", ignore_index=True)
    )
    cells["skill_sd_definition"] = "sample_sd_across_20_mask_placements_ddof_1"
    if cells["skill_sd"].isna().any():
        raise ValueError("cell skill SD is non-finite")

    # This is a descriptive envelope matching the published best-of-roster
    # curve's geometry.  It is explicitly not a new model-selection decision.
    seed_best = (
        seed_cells.sort_values(
            ["station_id", "gap_length", "mask_seed", "skill", "model"],
            ascending=[True, True, True, False, True],
            kind="mergesort",
        )
        .groupby(
            ["station_id", "gap_length", "mask_seed"],
            as_index=False,
            observed=True,
        )
        .first()
        .rename(columns={"model": "envelope_model", "skill": "envelope_skill"})
    )
    envelope = (
        seed_best.groupby(["station_id", "gap_length"], as_index=False, observed=True)
        .agg(
            n_mask_seeds=("mask_seed", "nunique"),
            mean_envelope_skill=("envelope_skill", "mean"),
            envelope_skill_sd=("envelope_skill", "std"),
            min_envelope_skill=("envelope_skill", "min"),
            max_envelope_skill=("envelope_skill", "max"),
            distinct_envelope_models=("envelope_model", "nunique"),
        )
        .sort_values(["station_id", "gap_length"], ignore_index=True)
    )
    envelope["estimand"] = "best_roster_envelope_per_mask_seed_descriptive_only"

    dam = seed_best.loc[
        seed_best["station_id"].eq(DOWNSTREAM_DAM_SITE),
        [
            "gap_length",
            "mask_seed",
            "envelope_skill",
        ],
    ].rename(columns={"envelope_skill": "dam_envelope_skill"})
    donors = seed_best.loc[~seed_best["station_id"].eq(DOWNSTREAM_DAM_SITE)].rename(
        columns={
            "station_id": "donor_station_id",
            "envelope_skill": "donor_envelope_skill",
        }
    )
    paired_seed = donors.merge(
        dam,
        on=["gap_length", "mask_seed"],
        how="left",
        validate="many_to_one",
    )
    paired_seed["donor_minus_dam_skill"] = (
        paired_seed["donor_envelope_skill"] - paired_seed["dam_envelope_skill"]
    )
    paired = (
        paired_seed.groupby(
            ["donor_station_id", "gap_length"], as_index=False, observed=True
        )["donor_minus_dam_skill"]
        .agg(
            n_mask_seeds="count",
            mean_validation_difference="mean",
            paired_difference_sd="std",
            min_validation_difference="min",
            max_validation_difference="max",
        )
        .sort_values(["donor_station_id", "gap_length"], ignore_index=True)
    )
    paired["paired_difference_sd_definition"] = (
        "sample_sd_of_seed_paired_best_roster_envelope_difference_ddof_1"
    )

    finite_sd = cells["skill_sd"].to_numpy(float)
    summary_rows: list[dict[str, Any]] = [
        {
            "summary_level": "all_station_gap_model_cells",
            "gap_length": None,
            "model": "all_roster_models",
            "n_cells": len(cells),
            "mean_skill_sd": float(np.mean(finite_sd)),
            "median_skill_sd": float(np.median(finite_sd)),
            "rms_skill_sd": float(np.sqrt(np.mean(np.square(finite_sd)))),
            "p95_skill_sd": float(np.quantile(finite_sd, 0.95)),
            "max_skill_sd": float(np.max(finite_sd)),
        }
    ]
    for gap_length, group in cells.groupby("gap_length", observed=True, sort=True):
        values = group["skill_sd"].to_numpy(float)
        summary_rows.append(
            {
                "summary_level": "all_station_model_cells_within_gap",
                "gap_length": int(gap_length),
                "model": "all_roster_models",
                "n_cells": len(group),
                "mean_skill_sd": float(np.mean(values)),
                "median_skill_sd": float(np.median(values)),
                "rms_skill_sd": float(np.sqrt(np.mean(np.square(values)))),
                "p95_skill_sd": float(np.quantile(values, 0.95)),
                "max_skill_sd": float(np.max(values)),
            }
        )
    for model, group in cells.groupby("model", observed=True, sort=True):
        values = group["skill_sd"].to_numpy(float)
        summary_rows.append(
            {
                "summary_level": "all_station_gap_cells_within_model",
                "gap_length": None,
                "model": str(model),
                "n_cells": len(group),
                "mean_skill_sd": float(np.mean(values)),
                "median_skill_sd": float(np.median(values)),
                "rms_skill_sd": float(np.sqrt(np.mean(np.square(values)))),
                "p95_skill_sd": float(np.quantile(values, 0.95)),
                "max_skill_sd": float(np.max(values)),
            }
        )
    summary = pd.DataFrame(summary_rows)
    return {
        "seed_cells": seed_cells,
        "cells": cells,
        "seed_envelope": seed_best,
        "envelope": envelope,
        "paired_seed_differences": paired_seed,
        "paired_differences": paired,
        "summary": summary,
    }


def run_external_validation_uncertainty(
    *,
    data_root: str | Path,
    finalized_model_roster_path: str | Path,
    output_dir: str | Path,
    design_path: str | Path = DEFAULT_DESIGN_PATH,
    study_manifest_path: str | Path = "study_manifest.yaml",
    experiment_config_path: str | Path = "configs/experiments.yaml",
    selection_data_version_manifest_path: str | Path | None = None,
    mask_seeds: Sequence[int] = EXTERNAL_VALIDATION_MASK_SEEDS,
    runner_factory: type[ExternalValidationUncertaintyRunner] = (
        ExternalValidationUncertaintyRunner
    ),
) -> dict[str, Any]:
    """Run and atomically publish the validation-only placement diagnostic."""

    root = Path(data_root).resolve()
    output = Path(output_dir).resolve()
    if output.exists():
        raise FileExistsError(f"refusing existing uncertainty output: {output}")
    protocol = load_confirmatory_protocol(design_path)
    roster = load_finalized_model_roster(
        finalized_model_roster_path,
        design_path=design_path,
        study_manifest_path=study_manifest_path,
        experiment_config_path=experiment_config_path,
        selection_data_version_manifest_path=selection_data_version_manifest_path,
    )
    model_design = load_frozen_model_design(design_path)
    models = _validate_selected_models(roster, model_design)
    training_seeds = _frozen_training_seeds(design_path)
    grid = build_external_validation_uncertainty_grid(
        training_seeds=training_seeds,
        mask_seeds=mask_seeds,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.staging.", dir=output.parent)
    )
    try:
        wide_path, long_path, restricted_manifest_path, data_identity = (
            _prepare_nonconfirmatory_input(
                data_root=root,
                staging_root=staging,
                roster=roster,
                protocol=protocol,
            )
        )
        runner = runner_factory(
            grid,
            wide_path=wide_path,
            quality_path=long_path,
            output_dir=staging / "runner",
            mask_dir=staging / "masks",
            config_path=experiment_config_path,
            design_path=design_path,
            manifest_path=study_manifest_path,
            data_version_manifest_path=restricted_manifest_path,
            models=models,
            training_seeds=training_seeds,
            resume=False,
        )
        if runner.evaluation_split != EXTERNAL_VALIDATION_SPLIT:
            raise RuntimeError("uncertainty runner left the validation split")
        daily, events = runner.run()
        del daily
        products = summarize_external_validation_uncertainty(
            events, models=models, mask_seeds=mask_seeds
        )
        artifact_names = {
            "seed_cells": "external_validation_uncertainty_seed_cells.csv",
            "cells": "external_validation_uncertainty_cells.csv",
            "seed_envelope": "external_validation_uncertainty_seed_envelope.csv",
            "envelope": "external_validation_uncertainty_envelope.csv",
            "paired_seed_differences": (
                "external_validation_uncertainty_paired_seed_differences.csv"
            ),
            "paired_differences": (
                "external_validation_uncertainty_paired_differences.csv"
            ),
            "summary": "external_validation_uncertainty_summary.csv",
        }
        artifacts: dict[str, dict[str, Any]] = {}
        for key, name in artifact_names.items():
            path = staging / name
            _atomic_csv(products[key], path)
            artifacts[name] = {
                "sha256": file_sha256(path),
                "bytes": path.stat().st_size,
                "rows": len(products[key]),
            }

        # Raw runner/mask shards are temporary working products.  The published
        # seed-cell table is the complete sufficient record for recomputing all
        # SD summaries and keeps the revision artifact compact.
        shutil.rmtree(staging / "runner")
        shutil.rmtree(staging / "masks")
        shutil.rmtree(staging / "restricted_input")
        grid_contract = {
            "evaluation_split": EXTERNAL_VALIDATION_SPLIT,
            "site_ids": list(FROZEN_SITE_IDS),
            "gap_lengths": list(EXTERNAL_BLOCK_LENGTHS),
            "mask_seeds": [int(value) for value in mask_seeds],
            "training_seeds": list(training_seeds),
            "models": list(models),
            "condition_count": len(grid.conditions),
            "scenario_count": len(grid.scenarios),
            "conditions": [asdict(value) for value in grid.conditions],
        }
        manifest: dict[str, Any] = {
            "schema_version": EXTERNAL_VALIDATION_UNCERTAINTY_SCHEMA_VERSION,
            "status": "complete",
            "complete": True,
            "completed_at_utc": _utc_now(),
            "evidence_role": EXTERNAL_VALIDATION_UNCERTAINTY_ROLE,
            "formal_evidence": False,
            "post_frozen_diagnostic": True,
            "fit_split": "train",
            "tuning_split": "validation",
            "evaluation_split": EXTERNAL_VALIDATION_SPLIT,
            "evaluation_period": {"start": "2021-01-01", "end": "2022-12-31"},
            "confirmatory_period_read": False,
            "confirmatory_outcomes_read": False,
            "confirmatory_metric_uses": 0,
            "once_lock_read": False,
            "once_lock_modified": False,
            "model_selection_performed": False,
            "interpretation": (
                "mask-placement uncertainty scale only; not a second "
                "confirmatory evaluation and not model-selection evidence"
            ),
            "data_version": CONFIRMATORY_DATA_VERSION,
            "data_input": data_identity,
            "finalized_model_roster": {
                "path": roster.manifest_path,
                "sha256": roster.manifest_sha256,
            },
            "grid": grid_contract,
            "grid_sha256": _canonical_sha256(grid_contract),
            "sd_definition": "sample_standard_deviation_across_20_mask_seeds_ddof_1",
            "artifacts": artifacts,
        }
        manifest_path = staging / "external_validation_uncertainty_manifest.json"
        _atomic_json(manifest, manifest_path)
        if output.exists():
            raise FileExistsError(f"refusing existing uncertainty output: {output}")
        os.rename(staging, output)
        return manifest
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = [
    "DOWNSTREAM_DAM_SITE",
    "EXTERNAL_VALIDATION_MASK_SEEDS",
    "EXTERNAL_VALIDATION_SPLIT",
    "EXTERNAL_VALIDATION_UNCERTAINTY_ROLE",
    "EXTERNAL_VALIDATION_UNCERTAINTY_SCHEMA_VERSION",
    "ExternalValidationUncertaintyRunner",
    "build_external_validation_uncertainty_grid",
    "run_external_validation_uncertainty",
    "summarize_external_validation_uncertainty",
]
