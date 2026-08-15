"""Frozen retrained-information upper-bound experiment.

Each declared coalition is a distinct training estimand.  A proposed-model
checkpoint is trained for exactly one coalition and one training seed, selected
only by validation loss, then evaluated once on the frozen development-test masks.
These results must never be pooled with the one-checkpoint operational-dropout
estimand.
"""

from __future__ import annotations

import copy
import hashlib
import json
import pickle
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from stream_recoverability.analysis.compensation import combination_label
from stream_recoverability.data.confirmatory import (
    FinalizedModelRoster,
    load_finalized_model_roster,
)
from stream_recoverability.evaluation.event_metrics import compute_event_metrics
from stream_recoverability.models.proposed import (
    MissingAwareMultisourceImputer,
    ProposedModelConfig,
    information_group_mask,
    masked_imputation_loss,
)
from stream_recoverability.models.proposed_curriculum import (
    FROZEN_VALIDATION_SCENARIOS,
)
from stream_recoverability.models.proposed_training import (
    ProposedTrainingConfig,
    load_proposed_checkpoint,
    sample_source_dropout,
    set_deterministic_seed,
    validate_proposed_checkpoint_contract,
)

from .contracts import file_sha256
from .grid import DEFAULT_FRONTIER_ANCHOR_PATH, ExperimentGrid, ExperimentScenario
from .runner import ExperimentRunner
from .science import (
    FIXED_MASK_SEEDS,
    FIXED_TRAINING_SEEDS,
    S0_DEFINITION,
    _atomic_json,
    _atomic_parquet,
    build_compensation_grid,
    predict_proposed_information_combinations,
    training_doy_climatology,
)

RETRAINED_INFORMATION_SCHEMA_VERSION = "retrained_information_run_v1"
RETRAINED_CHECKPOINT_SCHEMA_VERSION = "retrained_information_checkpoint_v1"
RETRAINED_SUITE = "retrained_information_upper_bounds"
RETRAINED_MODEL_NAME = "retrained_information_upper_bound"
RETRAINED_GAP_LENGTHS = (30, 90, 180)
RETRAINED_COALITIONS: tuple[tuple[str, ...], ...] = (
    (),
    ("A",),
    ("B",),
    ("C",),
    ("D",),
    ("A", "B"),
    ("A", "C"),
    ("A", "D"),
    ("A", "B", "C", "D"),
)
RETRAINED_COALITION_LABELS = tuple(
    combination_label(value) for value in RETRAINED_COALITIONS
)
REQUIRED_EVIDENCE_FIELDS = (
    "design_version",
    "design_hash",
    "data_version",
    "evaluation_split",
    "mask_schema_version",
    "model_schema_version",
    "statistics_schema_version",
)


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_identity(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).resolve()
    stat = resolved.stat()
    return {
        "path": str(resolved),
        "size": int(stat.st_size),
        "sha256": file_sha256(resolved),
    }


def _atomic_torch_save(value: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(dict(value), temporary)
    temporary.replace(path)


def _coalition(value: Sequence[str] | str) -> tuple[str, ...]:
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized == "S0":
            result: tuple[str, ...] = ()
        else:
            result = tuple(
                part for part in normalized.replace("S0+", "").split("+") if part
            )
    else:
        result = tuple(str(group).strip().upper() for group in value)
    if result not in RETRAINED_COALITIONS:
        raise ValueError(
            f"coalition {value!r} is not in the frozen nine-coalition design"
        )
    return result


def coalition_slug(value: Sequence[str] | str) -> str:
    """Return a path-safe, one-to-one label for a frozen coalition."""

    coalition = _coalition(value)
    return (
        "s0"
        if not coalition
        else "s0-" + "-".join(group.lower() for group in coalition)
    )


def _selected_coalitions(
    values: Sequence[Sequence[str] | str] | None,
) -> tuple[tuple[str, ...], ...]:
    if values is None:
        return RETRAINED_COALITIONS
    selected = tuple(_coalition(value) for value in values)
    if not selected:
        raise ValueError("at least one retrained coalition is required")
    if len(set(selected)) != len(selected):
        raise ValueError("retrained coalitions must be unique")
    return selected


def build_retrained_information_grid(
    manifest_path: str | Path = "study_manifest.yaml",
    *,
    mask_seeds: Sequence[int] | None = None,
    data_version: str = "published_v1",
    evaluation_split: str = "development_test",
    frontier_anchor_path: str | Path | None = DEFAULT_FRONTIER_ANCHOR_PATH,
) -> ExperimentGrid:
    """Build the frozen 30/90/180-day anchored target-T grid."""

    base = build_compensation_grid(
        manifest_path,
        mask_seeds=mask_seeds,
        data_version=data_version,
        evaluation_split=evaluation_split,
        frontier_anchor_path=frontier_anchor_path,
    )
    conditions = tuple(
        replace(condition, experiment="SCI_RETRAINED_INFORMATION")
        for condition in base.conditions
        if condition.gap_length in RETRAINED_GAP_LENGTHS
    )
    condition_by_id = {condition.condition_id: condition for condition in conditions}
    scenarios = tuple(
        ExperimentScenario(
            condition_by_id[scenario.condition.condition_id], scenario.mask_seed
        )
        for scenario in base.scenarios
        if scenario.condition.condition_id in condition_by_id
    )
    if len(conditions) != 9:
        raise AssertionError(
            "retrained information grid must contain 3 stations x 3 gaps"
        )
    if (
        tuple(sorted({int(value.gap_length) for value in conditions}))
        != RETRAINED_GAP_LENGTHS
    ):
        raise AssertionError("retrained information gaps differ from 30/90/180 days")
    return replace(
        base,
        suite=RETRAINED_SUITE,
        conditions=conditions,
        scenarios=scenarios,
    )


def _assert_estimand_directory(output_root: Path) -> None:
    manifest_path = output_root / "run_manifest.json"
    if not manifest_path.is_file():
        return
    try:
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("existing retrained run manifest is unreadable") from error
    estimand = existing.get("attribution_estimand")
    if estimand not in {None, "retrained_upper_bound"}:
        raise ValueError(
            "output directory already contains a different information estimand"
        )


def _write_not_applicable_manifest(
    output_root: Path,
    roster: FinalizedModelRoster,
    *,
    data_version: str,
    evaluation_split: str,
) -> dict[str, Any]:
    manifest = {
        "schema_version": RETRAINED_INFORMATION_SCHEMA_VERSION,
        "suite": RETRAINED_SUITE,
        "status": "not_applicable",
        "complete": False,
        "formal_design_complete": False,
        "attribution_estimand": "retrained_upper_bound",
        "information_estimand": "retrained_upper_bound",
        "not_applicable_reason": "proposed validation decision is framework_only",
        "proposed_decision": roster.proposed_decision,
        "finalized_model_roster": {
            "path": roster.manifest_path,
            "sha256": roster.manifest_sha256,
        },
        "data_version": data_version,
        "evaluation_split": evaluation_split,
        "formal_evidence": False,
        "evidence_role": "not_applicable",
    }
    _atomic_json(manifest, output_root / "run_manifest.json")
    return manifest


def _checkpoint_path(
    output_root: Path, coalition: tuple[str, ...], training_seed: int
) -> Path:
    return (
        output_root
        / "checkpoints"
        / coalition_slug(coalition)
        / f"proposed-retrained-S{int(training_seed)}.pt"
    )


def _base_training_contract(
    runner: ExperimentRunner,
    coalition: tuple[str, ...],
    training_seed: int,
    *,
    window_length: int,
    training_protocol: str,
) -> tuple[ProposedModelConfig, ProposedTrainingConfig, dict[str, Any], dict[str, Any]]:
    model_config, training_config, training_context = runner._proposed_contract(
        training_seed, window_length, training_protocol
    )
    contract = {
        "schema_version": RETRAINED_CHECKPOINT_SCHEMA_VERSION,
        "attribution_estimand": "retrained_upper_bound",
        "information_combination": combination_label(coalition),
        "coalition": list(coalition),
        "allowed_information_groups": list(coalition),
        "permanent_information_groups": ["S0"],
        "training_seed": int(training_seed),
        "data_version": runner.data.data_version,
        "design_version": runner.evidence_contract["design_version"],
        "design_hash": runner.evidence_contract["design_hash"],
        "code_identity": runner.evidence_contract["code_identity"],
        "model_config": asdict(model_config),
        "training_config": asdict(training_config),
        "training_context": training_context,
        "input_hashes": {
            name: identity.get("sha256")
            for name, identity in training_context["input_files"].items()
        },
        "fit_split": "train",
        "early_stopping_split": "validation",
        "evaluation_split": runner.evaluation_split,
        "source_restriction": "fixed_group_mask_during_training_validation_and_inference",
    }
    return model_config, training_config, training_context, contract


def _training_batches(
    runner: ExperimentRunner,
    training_seed: int,
    training_config: ProposedTrainingConfig,
    *,
    window_length: int,
    training_protocol: str,
) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    mean, scale = runner._proposed_scaler()
    normalized = (runner.data.values - mean[None]) / scale[None]
    effective_window = min(
        int(window_length),
        int(runner.train_rows.sum()),
        int(runner.validation_rows.sum()),
    )
    train_batches = tuple(
        runner._proposed_batches(
            normalized,
            runner.train_rows,
            None,
            effective_window,
            curriculum_config=training_config.curriculum,
            curriculum_seed=training_seed,
            protocol=training_protocol,
            repeats=runner.training_settings["train_mask_repeats"],
        )
    )
    validation_batches: list[Mapping[str, Any]] = []
    if tuple(training_config.curriculum.validation_scenarios) != tuple(
        FROZEN_VALIDATION_SCENARIOS
    ):
        raise ValueError("validation scenarios differ from the frozen design")
    for index, scenario in enumerate(FROZEN_VALIDATION_SCENARIOS):
        validation_batches.extend(
            runner._proposed_batches(
                normalized,
                runner.validation_rows,
                None,
                effective_window,
                curriculum_config=training_config.curriculum,
                curriculum_seed=training_seed + 10_000 + index,
                protocol=training_protocol,
                repeats=runner.training_settings["validation_mask_repeats"],
                validation_scenario=scenario,
            )
        )
    return train_batches, tuple(validation_batches)


def _target_tensor(
    value: torch.Tensor, model: MissingAwareMultisourceImputer
) -> torch.Tensor:
    if value.ndim == 4:
        return value[..., model.target_index]
    if value.ndim == 3:
        return value
    raise ValueError("target tensors must have shape [B,T,N] or [B,T,N,V]")


def _batch_loss(
    model: MissingAwareMultisourceImputer,
    batch: Mapping[str, Any],
    config: ProposedTrainingConfig,
    group_mask: torch.Tensor,
) -> tuple[torch.Tensor, int]:
    output = model(
        batch["values"],
        batch["natural_mask"],
        batch["artificial_mask"],
        batch.get("time_gap"),
        batch.get("seasonal_features"),
        training_climatology=batch.get("training_climatology"),
        group_mask=group_mask,
    )
    target = _target_tensor(batch["target"], model)
    artificial = _target_tensor(batch["artificial_mask"], model)
    quality = batch.get("quality_mask")
    quality_target = _target_tensor(quality, model) if quality is not None else None
    natural_target = _target_tensor(batch["natural_mask"], model).bool()
    observed = natural_target & ~artificial.bool() & torch.isfinite(target)
    losses = masked_imputation_loss(
        output,
        target,
        artificial,
        quality_mask=quality_target,
        observed_target=target,
        observed_mask=observed,
        huber_weight=config.huber_weight,
        pinball_weight=config.pinball_weight,
        consistency_weight=config.consistency_weight,
    )
    count = int(losses["masked_count"].detach().cpu())
    return losses["loss"] * losses["masked_count"].to(losses["loss"].dtype), count


def _eligible_target_count(
    model: MissingAwareMultisourceImputer, batch: Mapping[str, Any]
) -> int:
    target = _target_tensor(batch["target"], model)
    artificial = _target_tensor(batch["artificial_mask"], model).bool()
    eligible = artificial & torch.isfinite(target)
    quality = batch.get("quality_mask")
    if quality is not None:
        eligible &= _target_tensor(quality, model).bool()
    return int(eligible.sum().detach().cpu())


def _move_batch(batch: Mapping[str, Any], device: torch.device) -> dict[str, Any]:
    return {
        key: value.to(device) if isinstance(value, torch.Tensor) else value
        for key, value in batch.items()
    }


def _scenario_name(batch: Mapping[str, Any]) -> str:
    value = batch.get("validation_scenario")
    if value is not None:
        return str(value)
    metadata = batch.get("curriculum_metadata")
    if (
        isinstance(metadata, Mapping)
        and metadata.get("validation_scenario") is not None
    ):
        return str(metadata["validation_scenario"])
    return str(batch.get("training_mask_type", "aggregate"))


def _epoch(
    model: MissingAwareMultisourceImputer,
    batches: Sequence[Mapping[str, Any]],
    config: ProposedTrainingConfig,
    allowed_mask: torch.Tensor,
    *,
    optimizer: torch.optim.Optimizer | None,
    source_generator: torch.Generator | None,
) -> tuple[float, dict[str, float], int]:
    if not batches:
        raise ValueError("training and validation batches must be non-empty")
    training = optimizer is not None
    device = torch.device(config.device)
    model.train(training)
    if training:
        optimizer.zero_grad(set_to_none=True)
    expected_counts = [_eligible_target_count(model, batch) for batch in batches]
    total_count = int(sum(expected_counts))
    if total_count < 1:
        raise ValueError("retrained coalition epoch has no eligible masked targets")
    total_sum = 0.0
    scenario_sums: dict[str, float] = defaultdict(float)
    scenario_counts: dict[str, int] = defaultdict(int)
    for original, expected_count in zip(batches, expected_counts, strict=True):
        batch = _move_batch(original, device)
        fixed = allowed_mask.to(device=device)
        if training:
            sampled = sample_source_dropout(
                int(batch["values"].shape[0]),
                config.source_dropout_probability,
                generator=source_generator,
                device=device,
                ensure_one_source=False,
            )
            fixed = sampled & fixed.view(1, 4)
        if training:
            loss_sum, count = _batch_loss(model, batch, config, fixed)
        else:
            with torch.no_grad():
                loss_sum, count = _batch_loss(model, batch, config, fixed)
        if count != expected_count or count < 1 or not torch.isfinite(loss_sum).item():
            raise RuntimeError("retrained coalition produced a non-finite batch loss")
        if training:
            (loss_sum / float(total_count)).backward()
        detached = float(loss_sum.detach().cpu())
        total_sum += detached
        scenario = _scenario_name(original)
        scenario_sums[scenario] += detached
        scenario_counts[scenario] += count
    if training:
        if config.gradient_clip > 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.gradient_clip)
        optimizer.step()
    return (
        total_sum / total_count,
        {
            scenario: scenario_sums[scenario] / count
            for scenario, count in sorted(scenario_counts.items())
        },
        total_count,
    )


def _train_coalition_model(
    model: MissingAwareMultisourceImputer,
    train_batches: Sequence[Mapping[str, Any]],
    validation_batches: Sequence[Mapping[str, Any]],
    config: ProposedTrainingConfig,
    coalition: tuple[str, ...],
) -> dict[str, Any]:
    """Train one coalition with validation-only early stopping."""

    set_deterministic_seed(config.seed)
    device = torch.device(config.device)
    model.to(device)
    allowed = information_group_mask(coalition, device=device)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    source_generator = torch.Generator(device="cpu").manual_seed(config.seed + 17)
    best_loss = float("inf")
    best_epoch = 0
    best_state = copy.deepcopy(model.state_dict())
    bad_epochs = 0
    history: list[dict[str, Any]] = []
    for epoch in range(1, config.epochs + 1):
        train_loss, _, train_count = _epoch(
            model,
            train_batches,
            config,
            allowed,
            optimizer=optimizer,
            source_generator=source_generator,
        )
        validation_loss, scenario_losses, validation_count = _epoch(
            model,
            validation_batches,
            config,
            allowed,
            optimizer=None,
            source_generator=None,
        )
        missing = sorted(set(FROZEN_VALIDATION_SCENARIOS).difference(scenario_losses))
        if missing:
            raise ValueError(f"frozen validation scenarios are incomplete: {missing}")
        validation_score = float(
            np.mean([scenario_losses[name] for name in FROZEN_VALIDATION_SCENARIOS])
        )
        if not all(
            np.isfinite(value)
            for value in (train_loss, validation_loss, validation_score)
        ):
            raise RuntimeError("retrained coalition produced non-finite epoch metrics")
        row: dict[str, Any] = {
            "epoch": epoch,
            "train_loss": train_loss,
            "validation_loss": validation_loss,
            "validation_score": validation_score,
            "train_masked_cells": train_count,
            "validation_masked_cells": validation_count,
        }
        for name, value in scenario_losses.items():
            row[f"validation_{name}_loss"] = value
        history.append(row)
        if validation_score < best_loss - config.min_delta:
            best_loss = validation_score
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
            bad_epochs = 0
        else:
            bad_epochs += 1
            if bad_epochs >= config.patience:
                break
    if best_epoch < 1 or not np.isfinite(best_loss):
        raise RuntimeError("retrained coalition has no finite validation checkpoint")
    model.load_state_dict(best_state)
    best_row = history[best_epoch - 1]
    return {
        "model_state_dict": best_state,
        "epoch": best_epoch,
        "best_epoch": best_epoch,
        "best_validation_loss": best_loss,
        "best_validation_score": best_loss,
        "epochs_run": len(history),
        "hit_epoch_limit": len(history) == config.epochs,
        "history": history,
        "validation_scores": {
            name: float(best_row[f"validation_{name}_loss"])
            for name in FROZEN_VALIDATION_SCENARIOS
        },
    }


def _validate_retrained_checkpoint(
    checkpoint_path: Path,
    expected_contract: Mapping[str, Any],
    expected_model_config: ProposedModelConfig,
    expected_training_config: ProposedTrainingConfig,
    expected_training_context: Mapping[str, Any],
) -> tuple[MissingAwareMultisourceImputer, dict[str, Any], np.ndarray, np.ndarray]:
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"retrained checkpoint is missing: {checkpoint_path}")
    model, metadata = load_proposed_checkpoint(checkpoint_path, map_location="cpu")
    if metadata.get("retrained_contract") != dict(expected_contract):
        raise ValueError(
            "retrained checkpoint contract does not exactly match the request"
        )
    validate_proposed_checkpoint_contract(
        metadata,
        expected_model_config=expected_model_config,
        expected_training_config=expected_training_config,
        expected_training_context=expected_training_context,
    )
    scores = metadata.get("validation_scores")
    if not isinstance(scores, Mapping) or set(scores) != set(
        FROZEN_VALIDATION_SCENARIOS
    ):
        raise ValueError("retrained checkpoint validation scores are incomplete")
    if not np.isfinite(np.asarray(list(scores.values()), dtype=float)).all():
        raise ValueError("retrained checkpoint validation scores must be finite")
    scaler = metadata.get("train_scaler")
    if not isinstance(scaler, Mapping):
        raise TypeError("retrained checkpoint has no training scaler")
    if tuple(scaler.get("station_ids", ())) != tuple(model.config.station_ids) or tuple(
        scaler.get("variable_names", ())
    ) != tuple(model.config.variable_names):
        raise ValueError("retrained checkpoint scaler axes do not match the model")
    mean = np.asarray(scaler.get("mean"), dtype=np.float32)
    scale = np.asarray(scaler.get("scale"), dtype=np.float32)
    expected_shape = (len(model.config.station_ids), len(model.config.variable_names))
    if (
        mean.shape != expected_shape
        or scale.shape != expected_shape
        or not np.isfinite(mean).all()
        or not np.isfinite(scale).all()
        or np.any(scale <= 0)
    ):
        raise ValueError("retrained checkpoint scaler is invalid")
    if tuple(float(value) for value in metadata.get("quantile_levels", ())) != tuple(
        model.quantile_levels
    ):
        raise ValueError("retrained checkpoint quantile contract is invalid")
    return model, metadata, mean, scale


def _train_or_load_checkpoint(
    runner: ExperimentRunner,
    output_root: Path,
    coalition: tuple[str, ...],
    training_seed: int,
    *,
    window_length: int,
    training_protocol: str,
    resume: bool,
) -> tuple[
    MissingAwareMultisourceImputer, dict[str, Any], np.ndarray, np.ndarray, Path
]:
    model_config, training_config, training_context, contract = _base_training_contract(
        runner,
        coalition,
        training_seed,
        window_length=window_length,
        training_protocol=training_protocol,
    )
    checkpoint_path = _checkpoint_path(output_root, coalition, training_seed)
    if checkpoint_path.exists() and resume:
        model, metadata, mean, scale = _validate_retrained_checkpoint(
            checkpoint_path,
            contract,
            model_config,
            training_config,
            training_context,
        )
        return model, metadata, mean, scale, checkpoint_path

    train_batches, validation_batches = _training_batches(
        runner,
        training_seed,
        training_config,
        window_length=window_length,
        training_protocol=training_protocol,
    )
    set_deterministic_seed(training_seed)
    model = MissingAwareMultisourceImputer(model_config)
    trained = _train_coalition_model(
        model, train_batches, validation_batches, training_config, coalition
    )
    mean, scale = runner._proposed_scaler()
    payload = {
        **trained,
        "model_config": asdict(model_config),
        "training_config": asdict(training_config),
        "training_context": training_context,
        "quantile_levels": list(model.quantile_levels),
        "train_scaler": {
            "mean": mean.tolist(),
            "scale": scale.tolist(),
            "station_ids": list(runner.data.station_ids),
            "variable_names": list(runner.data.variable_names),
        },
        "retrained_contract": contract,
        "checkpoint_metadata": {
            "coalition": list(coalition),
            "allowed_information_groups": list(coalition),
            "training_seed": int(training_seed),
            "data_version": runner.data.data_version,
            "design_hash": runner.evidence_contract["design_hash"],
            "code_identity": runner.evidence_contract["code_identity"],
            "input_hashes": contract["input_hashes"],
            "fit_split": "train",
            "early_stopping_split": "validation",
        },
    }
    _atomic_torch_save(payload, checkpoint_path)
    model, metadata, mean, scale = _validate_retrained_checkpoint(
        checkpoint_path,
        contract,
        model_config,
        training_config,
        training_context,
    )
    return model, metadata, mean, scale, checkpoint_path


def _retrained_scenario_id(
    scenario: ExperimentScenario, coalition: tuple[str, ...]
) -> str:
    del coalition
    return scenario.scenario_id


def _run_unit_key(scenario: ExperimentScenario, training_seed: int) -> str:
    return f"{scenario.scenario_id}|{RETRAINED_MODEL_NAME}:{int(training_seed)}"


def _unit_dir(
    output_root: Path,
    scenario: ExperimentScenario,
    coalition: tuple[str, ...],
    training_seed: int,
) -> Path:
    return (
        output_root
        / "units"
        / scenario.scenario_id
        / coalition_slug(coalition)
        / f"S{int(training_seed)}"
    )


def _unit_contract(
    runner: ExperimentRunner,
    scenario: ExperimentScenario,
    coalition: tuple[str, ...],
    training_seed: int,
    checkpoint_path: Path,
    checkpoint_contract: Mapping[str, Any],
) -> dict[str, Any]:
    contract = {
        **runner.evidence_contract,
        "code_provenance": runner.code_provenance,
        "suite": RETRAINED_SUITE,
        "attribution_estimand": "retrained_upper_bound",
        "scenario": scenario.as_dict(),
        "retrained_scenario_id": _retrained_scenario_id(scenario, coalition),
        "information_combination": combination_label(coalition),
        "coalition": list(coalition),
        "training_seed": int(training_seed),
        "mask_seed": int(scenario.mask_seed),
        "checkpoint": _file_identity(checkpoint_path),
        "checkpoint_contract_sha256": _canonical_sha256(checkpoint_contract),
    }
    return json.loads(json.dumps(contract))


def _add_evidence_columns(
    frame: pd.DataFrame, evidence_contract: Mapping[str, Any]
) -> pd.DataFrame:
    result = frame.copy()
    for field in REQUIRED_EVIDENCE_FIELDS:
        result[field] = evidence_contract[field]
    result["evidence_role"] = "formal_development_evaluation"
    result["formal_evidence"] = True
    return result


def _score_unit(
    runner: ExperimentRunner,
    grid: ExperimentGrid,
    scenario: ExperimentScenario,
    coalition: tuple[str, ...],
    training_seed: int,
    model: MissingAwareMultisourceImputer,
    mean: np.ndarray,
    scale: np.ndarray,
    checkpoint_path: Path,
    checkpoint_contract: Mapping[str, Any],
    climatology_by_station: Mapping[int, np.ndarray],
    *,
    device: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    target_index = runner.data.variable_names.index("T")
    station = runner.data.station_ids.index(scenario.condition.station_ids[0])
    if station not in climatology_by_station:
        raise ValueError("training climatology reference is unavailable")
    artificial, metadata = runner._generate_mask(scenario)
    truth = runner.data.values[:, station, target_index].astype(float)
    quality = runner.data.quality_approved[:, station, target_index]
    hidden = artificial[:, station, target_index]
    positions = np.flatnonzero(hidden & quality & np.isfinite(truth))
    if positions.size == 0:
        raise ValueError("retrained unit has no approved artificial target")
    model_climatology = runner._proposed_training_climatology()
    predicted = predict_proposed_information_combinations(
        model,
        runner.data.values,
        runner.data.natural_observed,
        artificial,
        runner.data.seasonal_features,
        mean,
        scale,
        target_index=target_index,
        training_climatology=model_climatology,
        information_combinations=(coalition,),
        window_length=scenario.condition.window_length,
        device=device,
    )
    label = combination_label(coalition)
    if set(predicted) != {label}:
        raise ValueError("retrained inference returned a different coalition")
    quantiles = {name: value[:, station] for name, value in predicted[label].items()}
    prediction = quantiles["q50"]
    scored_quantiles = np.column_stack(
        [quantiles[name][positions] for name in ("q05", "q25", "q50", "q75", "q95")]
    )
    if not np.isfinite(scored_quantiles).all() or not np.all(
        np.diff(scored_quantiles, axis=1) > 0
    ):
        raise ValueError("retrained unit has invalid five-quantile predictions")
    climatology = climatology_by_station[station]
    reference = runner._training_reference(station, target_index)
    scenario_id = _retrained_scenario_id(scenario, coalition)
    checkpoint_identity = _file_identity(checkpoint_path)
    checkpoint_contract_sha = _canonical_sha256(checkpoint_contract)
    row_metadata = {
        **metadata,
        "scenario_id": scenario_id,
        "base_scenario_id": scenario.scenario_id,
        "station_id": runner.data.station_ids[station],
        "model": RETRAINED_MODEL_NAME,
        "training_seed": int(training_seed),
        "mask_seed": int(scenario.mask_seed),
        "target": "T",
        "gap_length": scenario.condition.gap_length,
        "pattern": "T",
    }
    event = compute_event_metrics(
        truth,
        prediction,
        quality,
        hidden,
        target="T",
        metadata=row_metadata,
        climatology_pred=climatology,
        dates=runner.data.dates,
        quantile_predictions=quantiles,
        high_threshold=reference.q90,
        low_threshold=reference.q10,
        ecological_threshold=None,
        normalization_iqr=reference.iqr,
        normalization_std=reference.std,
    )
    common = {
        "experiment": "SCI_RETRAINED_INFORMATION",
        "information_combination": label,
        "coalition": json.dumps(list(coalition), separators=(",", ":")),
        "allowed_information_groups": json.dumps(
            list(coalition), separators=(",", ":")
        ),
        "component_estimator": "proposed_checkpoint",
        "estimator": "proposed_checkpoint",
        "attribution_estimand": "retrained_upper_bound",
        "information_estimand": "retrained_upper_bound",
        "fit_split": "train",
        "tuning_split": "validation_checkpoint",
        "evaluation_split": runner.evaluation_split,
        "window_length": scenario.condition.window_length,
        "window": scenario.condition.window_length,
        "training_protocol": scenario.condition.training_protocol,
        "external_validation_status": grid.external_validation_status,
        "validation_scope": scenario.condition.validation_scope,
        "is_external_validation": False,
        "checkpoint_sha256": checkpoint_identity["sha256"],
        "checkpoint_contract_sha256": checkpoint_contract_sha,
        "high_threshold": reference.q90,
        "low_threshold": reference.q10,
        "normalization_iqr": reference.iqr,
        "normalization_std": reference.std,
        "threshold_reference_split": "train",
        "normalization_reference_split": "train",
    }
    event.update(common)
    months = runner.data.dates[positions].month.to_numpy()
    seasons = np.select(
        [
            np.isin(months, (12, 1, 2)),
            np.isin(months, (3, 4, 5)),
            np.isin(months, (6, 7, 8)),
        ],
        ["DJF", "MAM", "JJA"],
        default="SON",
    )
    daily = pd.DataFrame(
        {
            "date": runner.data.dates[positions],
            "station_id": runner.data.station_ids[station],
            "target": "T",
            "scenario_id": scenario_id,
            "base_scenario_id": scenario.scenario_id,
            "mask_type": scenario.condition.mask_type,
            "gap_length": scenario.condition.gap_length,
            "missing_rate": scenario.condition.missing_rate,
            "variable_pattern": "T",
            "pattern": "T",
            "model": RETRAINED_MODEL_NAME,
            "training_seed": int(training_seed),
            "mask_seed": int(scenario.mask_seed),
            "y_true": truth[positions],
            "y_pred": prediction[positions],
            "climatology_pred": climatology[positions],
            "q05": quantiles["q05"][positions],
            "q25": quantiles["q25"][positions],
            "q50": quantiles["q50"][positions],
            "q75": quantiles["q75"][positions],
            "q95": quantiles["q95"][positions],
            "season": seasons,
            "event_type": None,
            "quality_approved": quality[positions],
            "artificial_mask": hidden[positions],
            **common,
        }
    )
    daily = _add_evidence_columns(daily, runner.evidence_contract)
    events = _add_evidence_columns(pd.DataFrame([event]), runner.evidence_contract)
    return daily, events


def _validate_unit_tables(
    daily: pd.DataFrame,
    events: pd.DataFrame,
    scenario: ExperimentScenario,
    coalition: tuple[str, ...],
    training_seed: int,
) -> None:
    scenario_id = _retrained_scenario_id(scenario, coalition)
    label = combination_label(coalition)
    for frame in (daily, events):
        required = {
            "scenario_id",
            "model",
            "training_seed",
            "mask_seed",
            "information_combination",
            "attribution_estimand",
            "checkpoint_sha256",
        }
        missing = sorted(required.difference(frame.columns))
        if missing:
            raise ValueError(f"retrained unit is missing columns: {missing}")
        if (
            not frame["scenario_id"].eq(scenario_id).all()
            or not frame["model"].eq(RETRAINED_MODEL_NAME).all()
            or not frame["training_seed"].eq(training_seed).all()
            or not frame["mask_seed"].eq(scenario.mask_seed).all()
            or not frame["information_combination"].eq(label).all()
            or not frame["attribution_estimand"].eq("retrained_upper_bound").all()
        ):
            raise ValueError("retrained unit identity does not match its contract")
    if len(events) != 1:
        raise ValueError("retrained unit requires exactly one event row")
    if daily.empty or daily.duplicated(["date", "station_id", "target"]).any():
        raise ValueError("retrained unit daily scores are empty or duplicated")
    quantiles = daily[["q05", "q25", "q50", "q75", "q95"]].to_numpy(float)
    if (
        not np.isfinite(quantiles).all()
        or not np.all(np.diff(quantiles, axis=1) > 0)
        or not np.isfinite(daily[["y_true", "y_pred"]].to_numpy(float)).all()
        or not np.isfinite(events[["MAE", "RMSE"]].to_numpy(float)).all()
    ):
        raise ValueError("retrained unit contains non-finite or crossed predictions")


def _write_unit(
    unit_dir: Path,
    daily: pd.DataFrame,
    events: pd.DataFrame,
    contract: Mapping[str, Any],
) -> None:
    daily_path = unit_dir / "daily_predictions.parquet"
    events_path = unit_dir / "event_metrics.parquet"
    _atomic_parquet(daily, daily_path)
    _atomic_parquet(events, events_path)
    _atomic_json(
        {
            "status": "complete",
            "run_unit_key": (
                f"{daily['scenario_id'].iloc[0]}|{RETRAINED_MODEL_NAME}:"
                f"{int(daily['training_seed'].iloc[0])}"
            ),
            "information_combination": daily["information_combination"].iloc[0],
            "execution_contract": contract,
            "execution_contract_sha256": _canonical_sha256(contract),
            "daily_predictions": _file_identity(daily_path),
            "event_metrics": _file_identity(events_path),
            "daily_rows": len(daily),
            "event_rows": len(events),
        },
        unit_dir / "status.json",
    )


def _read_unit(
    unit_dir: Path,
    expected_contract: Mapping[str, Any],
    scenario: ExperimentScenario,
    coalition: tuple[str, ...],
    training_seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    status_path = unit_dir / "status.json"
    if not status_path.is_file():
        return None
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if (
            status.get("status") != "complete"
            or status.get("execution_contract") != dict(expected_contract)
            or status.get("execution_contract_sha256")
            != _canonical_sha256(expected_contract)
        ):
            return None
        daily_identity = status["daily_predictions"]
        event_identity = status["event_metrics"]
        daily_path = Path(daily_identity["path"])
        event_path = Path(event_identity["path"])
        if (
            _file_identity(daily_path) != daily_identity
            or _file_identity(event_path) != event_identity
        ):
            return None
        daily = pd.read_parquet(daily_path)
        events = pd.read_parquet(event_path)
        _validate_unit_tables(daily, events, scenario, coalition, training_seed)
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return None
    return daily, events


def _checkpoint_summary(
    path: Path, metadata: Mapping[str, Any], contract: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "model": RETRAINED_MODEL_NAME,
        "information_combination": contract["information_combination"],
        "coalition": contract["coalition"],
        "allowed_information_groups": contract["allowed_information_groups"],
        "training_seed": contract["training_seed"],
        "best_epoch": metadata["best_epoch"],
        "epochs_run": metadata["epochs_run"],
        "best_validation_score": metadata["best_validation_score"],
        "validation_scores": metadata["validation_scores"],
        "checkpoint": _file_identity(path),
        "checkpoint_sidecar": None,
        "checkpoint_contract_sha256": _canonical_sha256(contract),
        "checkpoint_contract_valid": True,
    }


def _manifest_count_fields(keys: Mapping[str, list[str]]) -> dict[str, int]:
    result = {
        f"{name.removesuffix('_keys')}_count": len(value)
        for name, value in keys.items()
    }
    result["checkpoint_required_run_count"] = len(
        keys["checkpoint_required_run_unit_keys"]
    )
    result["checkpoint_valid_run_count"] = len(keys["checkpoint_valid_run_unit_keys"])
    return result


def run_retrained_information_upper_bounds(
    *,
    finalized_model_roster_path: str | Path,
    manifest_path: str | Path = "study_manifest.yaml",
    config_path: str | Path = "configs/experiments.yaml",
    design_path: str | Path = "configs/design_freeze_v1.yaml",
    data_version_manifest_path: str | Path | None = None,
    selection_data_version_manifest_path: str | Path | None = None,
    wide_path: str | Path = "data/processed/daily_wide.parquet",
    quality_path: str | Path | None = "data/processed/daily_long.parquet",
    output_dir: str
    | Path = "results/science_experiments/retrained_information_upper_bounds",
    mask_dir: str | Path = "masks/science_retrained_information",
    training_seeds: Sequence[int] | None = None,
    mask_seeds: Sequence[int] | None = None,
    coalitions: Sequence[Sequence[str] | str] | None = None,
    data_version: str = "published_v1",
    evaluation_split: str = "development_test",
    frontier_anchor_path: str | Path | None = DEFAULT_FRONTIER_ANCHOR_PATH,
    max_scenarios: int | None = None,
    device: str = "cpu",
    resume: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Train and evaluate the frozen nine-coalition upper-bound design."""

    output_root = Path(output_dir)
    _assert_estimand_directory(output_root)
    roster = load_finalized_model_roster(
        finalized_model_roster_path,
        design_path=design_path,
        study_manifest_path=manifest_path,
        experiment_config_path=config_path,
        selection_data_version_manifest_path=selection_data_version_manifest_path,
    )
    if roster.proposed_decision == "framework_only":
        manifest = _write_not_applicable_manifest(
            output_root,
            roster,
            data_version=data_version,
            evaluation_split=evaluation_split,
        )
        return pd.DataFrame(), pd.DataFrame(), manifest
    if (
        roster.proposed_decision != "include_proposed_formally"
        or "proposed" not in roster.selected_models
    ):
        raise ValueError("finalized roster does not authorize proposed-model evidence")

    grid = build_retrained_information_grid(
        manifest_path,
        mask_seeds=mask_seeds,
        data_version=data_version,
        evaluation_split=evaluation_split,
        frontier_anchor_path=frontier_anchor_path,
    )
    selected_seeds = (
        tuple(int(value) for value in training_seeds)
        if training_seeds is not None
        else tuple(grid.training_seeds)
    )
    if not selected_seeds or len(set(selected_seeds)) != len(selected_seeds):
        raise ValueError("training seeds must be non-empty and unique")
    unknown_seeds = sorted(set(selected_seeds).difference(FIXED_TRAINING_SEEDS))
    if unknown_seeds:
        raise ValueError(f"training seeds are outside 11/22/33/44/55: {unknown_seeds}")
    selected_coalitions = _selected_coalitions(coalitions)
    selected_scenarios = grid.scenarios
    if max_scenarios is not None:
        if max_scenarios < 1:
            raise ValueError("max_scenarios must be positive")
        selected_scenarios = selected_scenarios[:max_scenarios]
    runner = ExperimentRunner(
        grid,
        wide_path=wide_path,
        quality_path=quality_path,
        output_dir=output_root,
        mask_dir=mask_dir,
        config_path=config_path,
        design_path=design_path,
        manifest_path=manifest_path,
        data_version_manifest_path=data_version_manifest_path,
        models=("proposed",),
        training_seeds=selected_seeds,
        resume=resume,
    )
    if runner.evaluation_split != "development_test":
        raise ValueError("retrained information evidence is development_test only")
    windows = {int(condition.window_length) for condition in grid.conditions}
    protocols = {str(condition.training_protocol) for condition in grid.conditions}
    if len(windows) != 1 or len(protocols) != 1:
        raise ValueError("retrained information requires one training window/protocol")
    window_length = next(iter(windows))
    training_protocol = next(iter(protocols))

    target_index = runner.data.variable_names.index("T")
    climatology_by_station: dict[int, np.ndarray] = {}
    for station in range(len(runner.data.station_ids)):
        climatology_by_station[station] = training_doy_climatology(
            runner.data.dates,
            runner.data.values[:, station, target_index],
            runner.train_rows,
            runner.data.quality_approved[:, station, target_index],
        )

    loaded: dict[
        tuple[tuple[str, ...], int],
        tuple[
            MissingAwareMultisourceImputer,
            dict[str, Any],
            np.ndarray,
            np.ndarray,
            Path,
            dict[str, Any],
        ],
    ] = {}
    for coalition in selected_coalitions:
        for seed in selected_seeds:
            model, metadata, mean, scale, checkpoint = _train_or_load_checkpoint(
                runner,
                output_root,
                coalition,
                seed,
                window_length=window_length,
                training_protocol=training_protocol,
                resume=resume,
            )
            _, _, _, contract = _base_training_contract(
                runner,
                coalition,
                seed,
                window_length=window_length,
                training_protocol=training_protocol,
            )
            loaded[(coalition, seed)] = (
                model,
                metadata,
                mean,
                scale,
                checkpoint,
                contract,
            )

    for scenario in selected_scenarios:
        for coalition in selected_coalitions:
            for seed in selected_seeds:
                model, _metadata, mean, scale, checkpoint, checkpoint_contract = loaded[
                    (coalition, seed)
                ]
                unit_dir = _unit_dir(output_root, scenario, coalition, seed)
                execution_contract = _unit_contract(
                    runner,
                    scenario,
                    coalition,
                    seed,
                    checkpoint,
                    checkpoint_contract,
                )
                if (
                    resume
                    and _read_unit(
                        unit_dir,
                        execution_contract,
                        scenario,
                        coalition,
                        seed,
                    )
                    is not None
                ):
                    continue
                daily, events = _score_unit(
                    runner,
                    grid,
                    scenario,
                    coalition,
                    seed,
                    model,
                    mean,
                    scale,
                    checkpoint,
                    checkpoint_contract,
                    climatology_by_station,
                    device=device,
                )
                _validate_unit_tables(daily, events, scenario, coalition, seed)
                _write_unit(unit_dir, daily, events, execution_contract)

    expected_keys = sorted(
        _run_unit_key(scenario, seed)
        for scenario in grid.scenarios
        for seed in grid.training_seeds
    )
    daily_parts: list[pd.DataFrame] = []
    event_parts: list[pd.DataFrame] = []
    completed_subunits: set[tuple[str, tuple[str, ...], int]] = set()
    checkpoint_valid_pairs: set[tuple[tuple[str, ...], int]] = set()
    checkpoint_summaries: dict[tuple[tuple[str, ...], int], dict[str, Any]] = {}
    validated_checkpoints: dict[
        tuple[tuple[str, ...], int],
        tuple[Path, dict[str, Any], dict[str, Any]] | None,
    ] = {}
    for coalition in RETRAINED_COALITIONS:
        for seed in grid.training_seeds:
            model_config, training_config, training_context, checkpoint_contract = (
                _base_training_contract(
                    runner,
                    coalition,
                    seed,
                    window_length=window_length,
                    training_protocol=training_protocol,
                )
            )
            path = _checkpoint_path(output_root, coalition, seed)
            try:
                _, metadata, _, _ = _validate_retrained_checkpoint(
                    path,
                    checkpoint_contract,
                    model_config,
                    training_config,
                    training_context,
                )
                validated_checkpoints[(coalition, seed)] = (
                    path,
                    metadata,
                    checkpoint_contract,
                )
                checkpoint_summaries[(coalition, seed)] = _checkpoint_summary(
                    path, metadata, checkpoint_contract
                )
                checkpoint_valid_pairs.add((coalition, seed))
            except (
                EOFError,
                FileNotFoundError,
                KeyError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
                pickle.UnpicklingError,
            ):
                validated_checkpoints[(coalition, seed)] = None

    for scenario in grid.scenarios:
        for coalition in RETRAINED_COALITIONS:
            for seed in grid.training_seeds:
                checkpoint_value = validated_checkpoints[(coalition, seed)]
                if checkpoint_value is None:
                    continue
                path, _, checkpoint_contract = checkpoint_value
                execution_contract = _unit_contract(
                    runner,
                    scenario,
                    coalition,
                    seed,
                    path,
                    checkpoint_contract,
                )
                unit = _read_unit(
                    _unit_dir(output_root, scenario, coalition, seed),
                    execution_contract,
                    scenario,
                    coalition,
                    seed,
                )
                if unit is None:
                    continue
                daily, events = unit
                daily_parts.append(daily)
                event_parts.append(events)
                completed_subunits.add((scenario.scenario_id, coalition, seed))
    daily = pd.concat(daily_parts, ignore_index=True) if daily_parts else pd.DataFrame()
    events = (
        pd.concat(event_parts, ignore_index=True) if event_parts else pd.DataFrame()
    )
    if not daily.empty:
        daily = daily.sort_values(
            ["scenario_id", "model", "training_seed", "date"], kind="stable"
        ).reset_index(drop=True)
    if not events.empty:
        events = events.sort_values(
            ["scenario_id", "model", "training_seed"], kind="stable"
        ).reset_index(drop=True)
    _atomic_parquet(daily, output_root / "daily_predictions.parquet")
    _atomic_parquet(events, output_root / "event_metrics.parquet")

    completed_keys = sorted(
        _run_unit_key(scenario, seed)
        for scenario in grid.scenarios
        for seed in grid.training_seeds
        if all(
            (scenario.scenario_id, coalition, seed) in completed_subunits
            for coalition in RETRAINED_COALITIONS
        )
    )
    checkpoint_valid_keys = sorted(
        _run_unit_key(scenario, seed)
        for scenario in grid.scenarios
        for seed in grid.training_seeds
        if all(
            (coalition, seed) in checkpoint_valid_pairs
            for coalition in RETRAINED_COALITIONS
        )
    )
    expected_set = set(expected_keys)
    completed_set = set(completed_keys)
    retryable_keys = sorted(expected_set.difference(completed_set))
    observed_training_seeds = (
        set(events["training_seed"].astype(int)) if not events.empty else set()
    )
    observed_coalitions = (
        set(events["information_combination"].astype(str))
        if not events.empty
        else set()
    )
    formal_seed_complete = observed_training_seeds == set(FIXED_TRAINING_SEEDS)
    formal_mask_complete = set(grid.mask_seeds) == set(FIXED_MASK_SEEDS)
    formal_coalition_complete = observed_coalitions == set(RETRAINED_COALITION_LABELS)
    checkpoint_complete = set(checkpoint_valid_keys) == expected_set
    formal_complete = bool(
        runner.training_profile_name == "formal"
        and formal_seed_complete
        and formal_mask_complete
        and formal_coalition_complete
        and completed_set == expected_set
        and checkpoint_complete
    )
    key_lists = {
        "expected_run_unit_keys": expected_keys,
        "completed_run_unit_keys": completed_keys,
        "retryable_run_unit_keys": retryable_keys,
        "structural_skip_run_unit_keys": [],
        "expected_evidence_run_unit_keys": expected_keys,
        "completed_evidence_run_unit_keys": completed_keys,
        "finite_prediction_run_unit_keys": completed_keys,
        "finite_event_metric_run_unit_keys": completed_keys,
        "checkpoint_required_run_unit_keys": expected_keys,
        "checkpoint_valid_run_unit_keys": checkpoint_valid_keys,
    }
    manifest: dict[str, Any] = {
        "schema_version": RETRAINED_INFORMATION_SCHEMA_VERSION,
        "suite": RETRAINED_SUITE,
        "status": "complete" if formal_complete else "partial",
        "complete": formal_complete,
        "formal_design_complete": formal_complete,
        "formal_unit_grid_complete": completed_set == expected_set,
        "formal_training_seed_complete": formal_seed_complete,
        "formal_mask_seed_complete": formal_mask_complete,
        "formal_coalition_complete": formal_coalition_complete,
        "run_unit_complete": completed_set == expected_set,
        "evidence_complete": completed_set == expected_set,
        "finite_predictions": completed_set == expected_set,
        "finite_event_metrics": completed_set == expected_set,
        "checkpoint_contract_complete": checkpoint_complete,
        "retryable_run_keys": retryable_keys,
        "models": [RETRAINED_MODEL_NAME],
        "attribution_estimand": "retrained_upper_bound",
        "information_estimand": "retrained_upper_bound",
        "pooling_rule": "never_mix_with_operational_dropout",
        "component_estimator": "proposed_checkpoint",
        "checkpoint_policy": "one_checkpoint_per_coalition_and_training_seed",
        "coalitions": [combination_label(value) for value in RETRAINED_COALITIONS],
        "gap_lengths": list(RETRAINED_GAP_LENGTHS),
        "expected_training_seeds": list(FIXED_TRAINING_SEEDS),
        "expected_mask_seeds": list(FIXED_MASK_SEEDS),
        "selected_training_seeds": list(selected_seeds),
        "selected_mask_seeds": list(grid.mask_seeds),
        "selected_coalitions": [
            combination_label(value) for value in selected_coalitions
        ],
        "fit_split": "train",
        "tuning_split": "validation_checkpoint",
        "evaluation_split": runner.evaluation_split,
        "training_profile": runner.training_profile_name,
        "training_settings": runner.training_settings,
        "daily_rows": len(daily),
        "completed_daily_rows": len(daily),
        "event_rows": len(events),
        "completed_event_rows": len(events),
        "training_checkpoints": [
            checkpoint_summaries[key] for key in sorted(checkpoint_summaries)
        ],
        "finalized_model_roster": {
            "path": roster.manifest_path,
            "sha256": roster.manifest_sha256,
            "proposed_decision": roster.proposed_decision,
        },
        "frontier_anchor_catalog_path": grid.frontier_anchor_catalog_path,
        "frontier_anchor_catalog_sha256": grid.frontier_anchor_catalog_sha256,
        "frontier_anchor_count": grid.frontier_anchor_count,
        "anchor_replacement_allowed": False,
        "s0_definition": S0_DEFINITION,
        "hidden_truth_input_policy": "artificially hidden values are NaN before inference",
        "formal_evidence": formal_complete,
        "evidence_role": "formal_development_evaluation",
        **key_lists,
        **_manifest_count_fields(key_lists),
        **runner.evidence_contract,
        "code_provenance": runner.code_provenance,
    }
    _atomic_json(manifest, output_root / "run_manifest.json")
    return daily, events, manifest


__all__ = [
    "RETRAINED_COALITIONS",
    "RETRAINED_COALITION_LABELS",
    "RETRAINED_GAP_LENGTHS",
    "RETRAINED_MODEL_NAME",
    "RETRAINED_SUITE",
    "build_retrained_information_grid",
    "coalition_slug",
    "run_retrained_information_upper_bounds",
]
