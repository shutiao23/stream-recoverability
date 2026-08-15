"""Frozen model registry and training protocols for formal experiment runs."""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

FORMAL_MODEL_CATEGORY_ORDER = (
    "traditional",
    "deep_deterministic",
    "probabilistic",
    "proposed",
)
DEVELOPMENT_MODEL_CATEGORY = "development_only"
REQUIRED_COMMON_TRAINING_FIELDS = (
    "optimizer",
    "learning_rate",
    "weight_decay",
    "gradient_clip",
    "batch_size",
    "max_epochs",
    "patience",
    "minimum_delta",
)


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"design freeze {name} must be a mapping")
    return {str(key): copy.deepcopy(item) for key, item in value.items()}


def _model_sequence(value: object, name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"design freeze {name} must be a sequence of model names")
    result = tuple(str(item).strip().lower() for item in value)
    if not result or any(not item for item in result):
        raise ValueError(f"design freeze {name} must contain model names")
    if len(set(result)) != len(result):
        raise ValueError(f"design freeze {name} contains duplicate model names")
    return result


@dataclass(frozen=True)
class FrozenModelDesign:
    """Canonical candidates and per-model protocols from one design freeze."""

    design_version: str
    categories: tuple[tuple[str, tuple[str, ...]], ...]
    common_training: dict[str, Any]
    model_protocols: dict[str, dict[str, Any]]
    curriculum_probabilities: tuple[tuple[str, float], ...]
    curriculum_gap_lengths: tuple[int, ...]
    seen_length_max_days: int
    unseen_length_train_max_days: int

    @property
    def formal_candidates(self) -> tuple[str, ...]:
        categories = dict(self.categories)
        return tuple(
            model
            for category in FORMAL_MODEL_CATEGORY_ORDER
            for model in categories[category]
        )

    @property
    def development_only(self) -> tuple[str, ...]:
        return dict(self.categories)[DEVELOPMENT_MODEL_CATEGORY]

    @property
    def all_candidates(self) -> tuple[str, ...]:
        return (*self.formal_candidates, *self.development_only)

    def category_for(self, model_name: str) -> str:
        normalized = str(model_name).strip().lower()
        for category, models in self.categories:
            if normalized in models:
                return category
        raise ValueError(
            f"model {normalized!r} is not declared by design freeze "
            f"{self.design_version!r}"
        )

    def protocol_for(self, model_name: str) -> dict[str, Any]:
        normalized = str(model_name).strip().lower()
        if normalized not in self.model_protocols:
            raise ValueError(
                f"design freeze has no fixed model protocol for {normalized!r}"
            )
        return copy.deepcopy(self.model_protocols[normalized])


def load_frozen_model_design(path: str | Path) -> FrozenModelDesign:
    """Load and strictly validate the formal model section of a design freeze."""

    design_path = Path(path)
    with design_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    design = _mapping(raw, "root")
    design_version = str(design.get("design_version", "")).strip()
    if not design_version:
        raise ValueError("design freeze requires a non-empty design_version")

    registry = _mapping(
        design.get("formal_model_candidates"), "formal_model_candidates"
    )
    expected_categories = {
        *FORMAL_MODEL_CATEGORY_ORDER,
        DEVELOPMENT_MODEL_CATEGORY,
    }
    missing_categories = sorted(expected_categories.difference(registry))
    extra_categories = sorted(set(registry).difference(expected_categories))
    if missing_categories or extra_categories:
        raise ValueError(
            "design freeze formal_model_candidates categories differ from the "
            f"runner contract: missing={missing_categories}, extra={extra_categories}"
        )
    categories = tuple(
        (
            category,
            _model_sequence(
                registry[category], f"formal_model_candidates.{category}"
            ),
        )
        for category in (*FORMAL_MODEL_CATEGORY_ORDER, DEVELOPMENT_MODEL_CATEGORY)
    )
    all_models = [model for _, models in categories for model in models]
    duplicates = sorted(
        model for model in set(all_models) if all_models.count(model) > 1
    )
    if duplicates:
        raise ValueError(
            "design freeze assigns models to multiple candidate categories: "
            f"{duplicates}"
        )

    training = _mapping(design.get("training"), "training")
    curriculum = _mapping(training.get("curriculum"), "training.curriculum")
    curriculum_probabilities = tuple(
        (str(name), float(probability)) for name, probability in curriculum.items()
    )
    if (
        not curriculum_probabilities
        or any(
            not math.isfinite(value) or value < 0
            for _, value in curriculum_probabilities
        )
        or abs(sum(value for _, value in curriculum_probabilities) - 1.0) > 1e-12
    ):
        raise ValueError("frozen training curriculum probabilities must sum to one")
    raw_gap_lengths = training.get("curriculum_gap_lengths")
    if isinstance(raw_gap_lengths, (str, bytes)) or not isinstance(
        raw_gap_lengths, Sequence
    ):
        raise TypeError("training.curriculum_gap_lengths must be a sequence")
    curriculum_gap_lengths = tuple(int(value) for value in raw_gap_lengths)
    if (
        not curriculum_gap_lengths
        or tuple(sorted(set(curriculum_gap_lengths))) != curriculum_gap_lengths
        or curriculum_gap_lengths[0] < 1
    ):
        raise ValueError(
            "training.curriculum_gap_lengths must be unique increasing positive days"
        )
    seen_length_max_days = int(training["seen_length_max_days"])
    unseen_length_train_max_days = int(training["unseen_length_train_max_days"])
    if seen_length_max_days != max(curriculum_gap_lengths):
        raise ValueError(
            "seen_length_max_days must equal the maximum curriculum gap length"
        )
    if unseen_length_train_max_days not in curriculum_gap_lengths:
        raise ValueError(
            "unseen_length_train_max_days must occur in curriculum_gap_lengths"
        )
    fixed = _mapping(training.get("fixed_model_protocols"), "fixed_model_protocols")
    common = _mapping(fixed.get("common"), "fixed_model_protocols.common")
    missing_common = sorted(set(REQUIRED_COMMON_TRAINING_FIELDS).difference(common))
    if missing_common:
        raise ValueError(
            "design freeze common training protocol is incomplete: "
            f"{missing_common}"
        )
    if str(common["optimizer"]) != "Adam":
        raise ValueError("formal runner currently requires frozen optimizer 'Adam'")
    for name in ("batch_size", "max_epochs", "patience"):
        value = common[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"frozen common training field {name} must be positive")
    for name in (
        "learning_rate",
        "weight_decay",
        "gradient_clip",
        "minimum_delta",
    ):
        value = common[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"frozen common training field {name} must be numeric")
        if (
            not math.isfinite(float(value))
            or float(value) < 0
            or (name == "learning_rate" and float(value) == 0)
        ):
            raise ValueError(
                f"frozen common training field {name} has an invalid value"
            )

    required_protocols = {"brits_ref", "saits_ref", "csdi", "proposed"}
    missing_protocols = sorted(required_protocols.difference(fixed))
    if missing_protocols:
        raise ValueError(
            "design freeze fixed_model_protocols is incomplete: "
            f"{missing_protocols}"
        )
    protocols = {
        name: _mapping(fixed[name], f"fixed_model_protocols.{name}")
        for name in required_protocols
    }
    return FrozenModelDesign(
        design_version=design_version,
        categories=categories,
        common_training=common,
        model_protocols=protocols,
        curriculum_probabilities=curriculum_probabilities,
        curriculum_gap_lengths=curriculum_gap_lengths,
        seen_length_max_days=seen_length_max_days,
        unseen_length_train_max_days=unseen_length_train_max_days,
    )


__all__ = [
    "DEVELOPMENT_MODEL_CATEGORY",
    "FORMAL_MODEL_CATEGORY_ORDER",
    "FrozenModelDesign",
    "load_frozen_model_design",
]
