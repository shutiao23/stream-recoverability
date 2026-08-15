"""Deterministic CPU-friendly training helpers for the proposed imputer."""

from __future__ import annotations

import copy
import pickle
import random
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import Tensor

from .proposed import (
    MissingAwareMultisourceImputer,
    ProposedModelConfig,
    masked_imputation_loss,
)
from .proposed_curriculum import ProposedCurriculumConfig

TRAINING_CONTRACT_VERSION = "proposed_training_v2"
LOSS_AGGREGATION = "masked_cell_weighted"
VALIDATION_SCORE_AGGREGATION = "equal_frozen_scenario_mean"


@dataclass(frozen=True)
class ProposedTrainingConfig:
    epochs: int = 200
    learning_rate: float = 1e-3
    weight_decay: float = 0.0
    patience: int = 20
    min_delta: float = 0.0
    gradient_clip: float = 1.0
    source_dropout_probability: float = 0.20
    huber_weight: float = 1.0
    pinball_weight: float = 1.0
    consistency_weight: float = 0.0
    seed: int = 11
    device: str = "cpu"
    training_contract_version: str = TRAINING_CONTRACT_VERSION
    loss_aggregation: str = LOSS_AGGREGATION
    validation_score_aggregation: str = VALIDATION_SCORE_AGGREGATION
    curriculum: ProposedCurriculumConfig = field(
        default_factory=ProposedCurriculumConfig
    )


@dataclass(frozen=True)
class ProposedTrainingResult:
    best_epoch: int
    best_validation_loss: float
    epochs_run: int
    hit_epoch_limit: bool
    history: tuple[dict[str, Any], ...]
    training_curriculum: dict[str, Any]
    validation_curriculum: dict[str, Any]


@dataclass(frozen=True)
class EpochMetrics:
    loss: float
    masked_cells: int
    scenario_losses: dict[str, float]
    scenario_masked_cells: dict[str, int]


def set_deterministic_seed(seed: int) -> None:
    """Seed Python, NumPy, and PyTorch for repeatable CPU experiments."""

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)


def sample_source_dropout(
    batch_size: int,
    probability: float | Mapping[str, float],
    *,
    generator: torch.Generator | None = None,
    device: torch.device | str = "cpu",
    ensure_one_source: bool = True,
) -> Tensor:
    """Sample per-example A/B/C/D branch availability for source dropout."""

    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if isinstance(probability, Mapping):
        probabilities = torch.tensor(
            [float(probability.get(group, 0.0)) for group in ("A", "B", "C", "D")],
            dtype=torch.float32,
        )
    else:
        probabilities = torch.full((4,), float(probability), dtype=torch.float32)
    if ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError("source dropout probabilities must be in [0, 1]")

    draws = torch.rand((batch_size, 4), generator=generator)
    keep = draws >= probabilities.view(1, 4)
    if ensure_one_source:
        empty = ~keep.any(dim=1)
        if empty.any():
            replacement = torch.randint(0, 4, (int(empty.sum()),), generator=generator)
            keep[empty] = False
            keep[empty, replacement] = True
    return keep.to(device=device)


def _move_batch(batch: Mapping[str, Any], device: torch.device) -> dict[str, Any]:
    return {
        key: value.to(device) if isinstance(value, Tensor) else value
        for key, value in batch.items()
    }


def _target_tensor(value: Tensor, model: MissingAwareMultisourceImputer) -> Tensor:
    if value.ndim == 4:
        return value[..., model.target_index]
    if value.ndim == 3:
        return value
    raise ValueError("target and target masks must have shape [B,T,N] or [B,T,N,V]")


def _masked_target_count(
    model: MissingAwareMultisourceImputer,
    batch: Mapping[str, Any],
) -> int:
    required = {"values", "natural_mask", "artificial_mask", "target"}
    absent = sorted(required.difference(batch))
    if absent:
        raise KeyError(f"training batch is missing keys: {absent}")
    target = _target_tensor(batch["target"], model)
    artificial = _target_tensor(batch["artificial_mask"], model).bool()
    eligible = artificial & torch.isfinite(target)
    quality = batch.get("quality_mask")
    if quality is not None:
        eligible &= _target_tensor(quality, model).bool()
    return int(eligible.sum().detach().cpu())


def _scenario_name(batch: Mapping[str, Any]) -> str:
    for key in ("validation_scenario", "training_mask_type"):
        value = batch.get(key)
        if value is not None and str(value):
            return str(value)
    metadata = batch.get("curriculum_metadata")
    if isinstance(metadata, Mapping):
        for key in ("validation_scenario", "training_mask_type"):
            value = metadata.get(key)
            if value is not None and str(value):
                return str(value)
    return "aggregate"


def _curriculum_summary(
    model: MissingAwareMultisourceImputer,
    batches: Sequence[Mapping[str, Any]],
    *,
    split: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    by_scenario: dict[str, dict[str, int]] = defaultdict(
        lambda: {"batch_count": 0, "masked_cells": 0, "target_masked_cells": 0}
    )
    for index, batch in enumerate(batches):
        artificial = batch.get("artificial_mask")
        if not isinstance(artificial, Tensor):
            raise TypeError("artificial_mask must be a tensor")
        target_count = _masked_target_count(model, batch)
        metadata = batch.get("curriculum_metadata")
        source = dict(metadata) if isinstance(metadata, Mapping) else {}
        scenario = _scenario_name(batch)
        masked_cells = int(artificial.bool().sum().detach().cpu())
        row = {
            "batch_index": int(index),
            "training_mask_type": str(source.get("training_mask_type", scenario)),
            "training_gap_length": source.get("training_gap_length"),
            "training_pattern": str(source.get("training_pattern", "unspecified")),
            "training_station_count": int(
                source.get(
                    "training_station_count",
                    int(
                        _target_tensor(artificial, model)
                        .bool()
                        .any(dim=(0, 1))
                        .sum()
                        .detach()
                        .cpu()
                    ),
                )
            ),
            "training_masked_cells": int(
                source.get("training_masked_cells", masked_cells)
            ),
            "training_target_masked_cells": int(
                source.get("training_target_masked_cells", target_count)
            ),
            "validation_scenario": source.get(
                "validation_scenario", batch.get("validation_scenario")
            ),
        }
        rows.append(row)
        totals = by_scenario[scenario]
        totals["batch_count"] += 1
        totals["masked_cells"] += masked_cells
        totals["target_masked_cells"] += target_count
    return {
        "split": split,
        "batch_count": len(rows),
        "masked_cells": int(sum(row["training_masked_cells"] for row in rows)),
        "target_masked_cells": int(
            sum(row["training_target_masked_cells"] for row in rows)
        ),
        "by_scenario": {key: value for key, value in sorted(by_scenario.items())},
        "batch_log": rows,
    }


def _batch_loss(
    model: MissingAwareMultisourceImputer,
    batch: Mapping[str, Any],
    config: ProposedTrainingConfig,
    *,
    group_mask: Tensor | None,
) -> dict[str, Tensor]:
    required = {"values", "natural_mask", "artificial_mask", "target"}
    absent = sorted(required.difference(batch))
    if absent:
        raise KeyError(f"training batch is missing keys: {absent}")
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
    artificial_target = _target_tensor(batch["artificial_mask"], model)
    quality = batch.get("quality_mask")
    quality_target = _target_tensor(quality, model) if quality is not None else None
    natural_target = _target_tensor(batch["natural_mask"], model).bool()
    observed_mask = natural_target & ~artificial_target.bool() & torch.isfinite(target)
    losses = masked_imputation_loss(
        output,
        target,
        artificial_target,
        quality_mask=quality_target,
        observed_target=target,
        observed_mask=observed_mask,
        huber_weight=config.huber_weight,
        pinball_weight=config.pinball_weight,
        consistency_weight=config.consistency_weight,
    )
    losses["loss_sum"] = losses["loss"] * losses["masked_count"].to(
        losses["loss"].dtype
    )
    return losses


def _run_epoch(
    model: MissingAwareMultisourceImputer,
    batches: Iterable[Mapping[str, Any]],
    config: ProposedTrainingConfig,
    device: torch.device,
    *,
    optimizer: torch.optim.Optimizer | None,
    source_generator: torch.Generator | None,
) -> EpochMetrics:
    training = optimizer is not None
    model.train(training)
    materialized = tuple(batches)
    if not materialized:
        raise ValueError(
            "training and validation iterables must each contain at least one batch"
        )
    counts = [_masked_target_count(model, batch) for batch in materialized]
    total_masked_cells = int(sum(counts))
    if total_masked_cells < 1:
        raise ValueError(
            "an epoch requires at least one eligible artificially masked target"
        )
    if training:
        optimizer.zero_grad(set_to_none=True)

    loss_sum = 0.0
    scenario_loss_sums: dict[str, float] = defaultdict(float)
    scenario_counts: dict[str, int] = defaultdict(int)
    for original_batch, expected_count in zip(materialized, counts, strict=True):
        batch = _move_batch(original_batch, device)
        if training:
            group_mask = sample_source_dropout(
                batch["values"].shape[0],
                config.source_dropout_probability,
                generator=source_generator,
                device=device,
                ensure_one_source=False,
            )
            losses = _batch_loss(model, batch, config, group_mask=group_mask)
        else:
            with torch.no_grad():
                losses = _batch_loss(model, batch, config, group_mask=None)
        actual_count = int(losses["masked_count"].detach().cpu())
        if actual_count != expected_count:
            raise AssertionError(
                "precomputed and model-reported masked target counts differ"
            )
        batch_loss_sum = losses["loss_sum"]
        if not torch.isfinite(batch_loss_sum).item():
            return EpochMetrics(
                loss=float("nan"),
                masked_cells=total_masked_cells,
                scenario_losses={},
                scenario_masked_cells={},
            )
        if training:
            (batch_loss_sum / float(total_masked_cells)).backward()
        detached_sum = float(batch_loss_sum.detach().cpu())
        loss_sum += detached_sum
        scenario = _scenario_name(original_batch)
        scenario_loss_sums[scenario] += detached_sum
        scenario_counts[scenario] += actual_count

    if training:
        if config.gradient_clip > 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.gradient_clip)
        optimizer.step()
    scenario_losses = {
        scenario: scenario_loss_sums[scenario] / count
        for scenario, count in scenario_counts.items()
        if count > 0
    }
    return EpochMetrics(
        loss=loss_sum / total_masked_cells,
        masked_cells=total_masked_cells,
        scenario_losses=dict(sorted(scenario_losses.items())),
        scenario_masked_cells=dict(sorted(scenario_counts.items())),
    )


def _coerce_epoch_metrics(value: EpochMetrics | float) -> EpochMetrics:
    if isinstance(value, EpochMetrics):
        return value
    return EpochMetrics(
        loss=float(value),
        masked_cells=0,
        scenario_losses={},
        scenario_masked_cells={},
    )


def _validation_score(
    metrics: EpochMetrics,
    config: ProposedTrainingConfig,
) -> float:
    required = tuple(config.curriculum.validation_scenarios)
    present = tuple(name for name in required if name in metrics.scenario_losses)
    if present and present != required:
        missing = sorted(set(required).difference(present))
        raise ValueError(
            f"frozen validation batches are incomplete; missing scenarios {missing}"
        )
    if present:
        return float(np.mean([metrics.scenario_losses[name] for name in required]))
    return metrics.loss


def train_proposed_model(
    model: MissingAwareMultisourceImputer,
    train_batches: Iterable[Mapping[str, Any]],
    validation_batches: Iterable[Mapping[str, Any]],
    config: ProposedTrainingConfig | None = None,
    *,
    checkpoint_path: str | Path | None = None,
) -> ProposedTrainingResult:
    """Train with source dropout, validation early stopping, and best checkpointing."""

    config = config or ProposedTrainingConfig()
    if config.epochs < 1 or config.patience < 1:
        raise ValueError("epochs and patience must be positive")
    if config.training_contract_version != TRAINING_CONTRACT_VERSION:
        raise ValueError(
            f"training_contract_version must be {TRAINING_CONTRACT_VERSION!r}"
        )
    if config.loss_aggregation != LOSS_AGGREGATION:
        raise ValueError(f"loss_aggregation must be {LOSS_AGGREGATION!r}")
    if config.validation_score_aggregation != VALIDATION_SCORE_AGGREGATION:
        raise ValueError(
            f"validation_score_aggregation must be {VALIDATION_SCORE_AGGREGATION!r}"
        )
    set_deterministic_seed(config.seed)
    device = torch.device(config.device)
    model.to(device)
    train_batches = tuple(train_batches)
    validation_batches = tuple(validation_batches)
    if not train_batches or not validation_batches:
        raise ValueError(
            "training and validation iterables must each contain at least one batch"
        )
    training_curriculum = _curriculum_summary(model, train_batches, split="train")
    validation_curriculum = _curriculum_summary(
        model, validation_batches, split="validation"
    )
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    source_generator = torch.Generator(device="cpu").manual_seed(config.seed + 17)
    path = Path(checkpoint_path) if checkpoint_path is not None else None
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)

    best_loss = float("inf")
    best_epoch = 0
    best_state = copy.deepcopy(model.state_dict())
    best_optimizer_state = copy.deepcopy(optimizer.state_dict())
    bad_epochs = 0
    history: list[dict[str, Any]] = []
    for epoch in range(1, config.epochs + 1):
        train_metrics = _coerce_epoch_metrics(
            _run_epoch(
                model,
                train_batches,
                config,
                device,
                optimizer=optimizer,
                source_generator=source_generator,
            )
        )
        validation_metrics = _coerce_epoch_metrics(
            _run_epoch(
                model,
                validation_batches,
                config,
                device,
                optimizer=None,
                source_generator=None,
            )
        )
        validation_score = _validation_score(validation_metrics, config)
        if (
            not np.isfinite(train_metrics.loss)
            or not np.isfinite(validation_metrics.loss)
            or not np.isfinite(validation_score)
        ):
            raise RuntimeError(
                "proposed training produced a non-finite train or validation loss"
            )
        row: dict[str, Any] = {
            "epoch": float(epoch),
            "train_loss": train_metrics.loss,
            "validation_loss": validation_metrics.loss,
            "validation_score": validation_score,
            "train_masked_cells": int(train_metrics.masked_cells),
            "validation_masked_cells": int(validation_metrics.masked_cells),
        }
        for scenario in config.curriculum.validation_scenarios:
            if scenario in validation_metrics.scenario_losses:
                row[f"validation_{scenario}_loss"] = validation_metrics.scenario_losses[
                    scenario
                ]
                row[f"validation_{scenario}_masked_cells"] = int(
                    validation_metrics.scenario_masked_cells[scenario]
                )
        history.append(row)
        if validation_score < best_loss - config.min_delta:
            best_loss = validation_score
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
            best_optimizer_state = copy.deepcopy(optimizer.state_dict())
            bad_epochs = 0
            if path is not None:
                torch.save(
                    {
                        "model_state_dict": best_state,
                        "optimizer_state_dict": optimizer.state_dict(),
                        "model_config": asdict(model.config),
                        "training_config": asdict(config),
                        "epoch": epoch,
                        "best_validation_loss": best_loss,
                        "best_validation_score": best_loss,
                        "training_curriculum": training_curriculum,
                        "validation_curriculum": validation_curriculum,
                    },
                    path,
                )
        else:
            bad_epochs += 1
            if bad_epochs >= config.patience:
                break

    if best_epoch < 1 or not np.isfinite(best_loss):
        raise RuntimeError(
            "proposed training did not produce a finite validation checkpoint"
        )
    model.load_state_dict(best_state)
    hit_epoch_limit = len(history) == config.epochs
    if path is not None:
        torch.save(
            {
                "model_state_dict": best_state,
                "optimizer_state_dict": best_optimizer_state,
                "model_config": asdict(model.config),
                "training_config": asdict(config),
                "epoch": best_epoch,
                "best_epoch": best_epoch,
                "best_validation_loss": best_loss,
                "best_validation_score": best_loss,
                "epochs_run": len(history),
                "hit_epoch_limit": hit_epoch_limit,
                "history": history,
                "training_curriculum": training_curriculum,
                "validation_curriculum": validation_curriculum,
            },
            path,
        )
    return ProposedTrainingResult(
        best_epoch=best_epoch,
        best_validation_loss=best_loss,
        epochs_run=len(history),
        hit_epoch_limit=hit_epoch_limit,
        history=tuple(history),
        training_curriculum=training_curriculum,
        validation_curriculum=validation_curriculum,
    )


def _contract_mismatches(
    stored: object, expected: Mapping[str, Any]
) -> dict[str, tuple[Any, Any]]:
    if not isinstance(stored, Mapping):
        return {"<mapping>": (type(stored).__name__, "mapping")}
    keys = set(stored).union(expected)
    return {
        str(field): (stored.get(field), expected.get(field))
        for field in sorted(keys, key=str)
        if stored.get(field) != expected.get(field)
        or (field in stored) != (field in expected)
    }


def _validate_finite_state_dict(state_dict: object) -> None:
    if not isinstance(state_dict, Mapping) or not state_dict:
        raise ValueError("checkpoint model_state_dict must be a non-empty mapping")
    for name, value in state_dict.items():
        if (
            not isinstance(value, torch.Tensor)
            or not torch.isfinite(value).all().item()
        ):
            raise ValueError(
                f"checkpoint model_state_dict entry {name!r} must be finite"
            )


def validate_proposed_checkpoint_contract(
    checkpoint: Mapping[str, Any],
    *,
    expected_model_config: ProposedModelConfig,
    expected_training_config: ProposedTrainingConfig,
    expected_training_context: Mapping[str, Any],
) -> None:
    """Reject checkpoints that differ from the requested model/training estimand."""

    model_mismatches = _contract_mismatches(
        checkpoint.get("model_config"), asdict(expected_model_config)
    )
    training_mismatches = _contract_mismatches(
        checkpoint.get("training_config"), asdict(expected_training_config)
    )
    context_mismatches = _contract_mismatches(
        checkpoint.get("training_context"), dict(expected_training_context)
    )
    if model_mismatches or training_mismatches or context_mismatches:
        raise ValueError(
            "checkpoint contract mismatch: "
            f"model_config={model_mismatches}, "
            f"training_config={training_mismatches}, "
            f"training_context={context_mismatches}"
        )

    _validate_finite_state_dict(checkpoint.get("model_state_dict"))

    best_epoch = checkpoint.get("best_epoch")
    epochs_run = checkpoint.get("epochs_run")
    best_loss = checkpoint.get("best_validation_loss")
    history = checkpoint.get("history")
    if (
        isinstance(best_epoch, bool)
        or not isinstance(best_epoch, (int, np.integer))
        or int(best_epoch) < 1
    ):
        raise ValueError("checkpoint best_epoch must be a positive integer")
    if (
        isinstance(epochs_run, bool)
        or not isinstance(epochs_run, (int, np.integer))
        or int(epochs_run) < int(best_epoch)
        or int(epochs_run) > expected_training_config.epochs
    ):
        raise ValueError(
            "checkpoint epochs_run must satisfy best_epoch <= epochs_run <= configured epochs"
        )
    if not isinstance(
        best_loss, (int, float, np.integer, np.floating)
    ) or not np.isfinite(float(best_loss)):
        raise ValueError("checkpoint best_validation_loss must be finite")
    if not isinstance(history, Sequence) or isinstance(history, (str, bytes)):
        raise TypeError("checkpoint history must be a non-empty epoch sequence")
    if len(history) != int(epochs_run) or not history:
        raise ValueError("checkpoint history length must equal epochs_run")
    for index, row in enumerate(history, start=1):
        if not isinstance(row, Mapping):
            raise TypeError("checkpoint history rows must be mappings")
        try:
            epoch = float(row["epoch"])
            train_loss = float(row["train_loss"])
            validation_loss = float(row["validation_loss"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "checkpoint history rows require epoch/train_loss/validation_loss"
            ) from error
        if (
            epoch != index
            or not np.isfinite(train_loss)
            or not np.isfinite(validation_loss)
        ):
            raise ValueError(
                "checkpoint history epochs must be sequential with finite losses"
            )
    best_history_row = history[int(best_epoch) - 1]
    best_history_loss = float(
        best_history_row.get("validation_score", best_history_row["validation_loss"])
    )
    if not np.isclose(best_history_loss, float(best_loss), rtol=1e-12, atol=0.0):
        raise ValueError(
            "checkpoint best_validation_loss does not match its best_epoch history row"
        )
    best_score = checkpoint.get("best_validation_score", best_loss)
    if not isinstance(
        best_score, (int, float, np.integer, np.floating)
    ) or not np.isclose(float(best_score), float(best_loss), rtol=1e-12, atol=0.0):
        raise ValueError(
            "checkpoint best_validation_score must equal best_validation_loss"
        )
    if checkpoint.get("epoch") != int(best_epoch):
        raise ValueError("checkpoint epoch must equal best_epoch")
    hit_epoch_limit = checkpoint.get("hit_epoch_limit")
    expected_hit_limit = int(epochs_run) == expected_training_config.epochs
    if not isinstance(hit_epoch_limit, bool) or hit_epoch_limit != expected_hit_limit:
        raise ValueError("checkpoint hit_epoch_limit is inconsistent with epochs_run")


def load_proposed_checkpoint(
    checkpoint_path: str | Path,
    model: MissingAwareMultisourceImputer | None = None,
    *,
    map_location: str | torch.device = "cpu",
) -> tuple[MissingAwareMultisourceImputer, dict[str, Any]]:
    """Load a saved best checkpoint and return the model plus metadata."""

    try:
        checkpoint = torch.load(
            checkpoint_path, map_location=map_location, weights_only=False
        )
    except pickle.UnpicklingError as error:
        raise ValueError("proposed checkpoint payload cannot be decoded") from error
    if not isinstance(checkpoint, Mapping):
        raise TypeError("proposed checkpoint payload must be a mapping")
    state_dict = checkpoint.get("model_state_dict")
    _validate_finite_state_dict(state_dict)
    if model is None:
        try:
            model = MissingAwareMultisourceImputer(
                ProposedModelConfig(**checkpoint["model_config"])
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("proposed checkpoint model_config is invalid") from error
    model.load_state_dict(state_dict)
    _validate_finite_state_dict(model.state_dict())
    return model, dict(checkpoint)


__all__ = [
    "LOSS_AGGREGATION",
    "TRAINING_CONTRACT_VERSION",
    "VALIDATION_SCORE_AGGREGATION",
    "EpochMetrics",
    "ProposedTrainingConfig",
    "ProposedTrainingResult",
    "load_proposed_checkpoint",
    "sample_source_dropout",
    "set_deterministic_seed",
    "train_proposed_model",
    "validate_proposed_checkpoint_contract",
]
