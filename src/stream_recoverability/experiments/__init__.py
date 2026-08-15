"""Unified experiment grids and execution helpers."""

from .grid import (
    ExperimentCondition,
    ExperimentGrid,
    ExperimentScenario,
    build_experiment_grid,
)
from .model_registry import FrozenModelDesign, load_frozen_model_design
from .runner import (
    LEGACY_MODEL_ALIASES,
    LOCAL_DEEP_MODELS,
    REFERENCE_MODELS,
    SUPPORTED_MODELS,
    TRAINABLE_MODELS,
    ExperimentRunner,
    canonical_model_name,
    run_experiments,
)
from .validation import (
    ValidationFunnel,
    ValidationMaskUnit,
    ValidationStage,
    build_validation_funnel,
    rank_validation_models,
    write_validation_model_ranking,
)

__all__ = [
    "LEGACY_MODEL_ALIASES",
    "LOCAL_DEEP_MODELS",
    "REFERENCE_MODELS",
    "SUPPORTED_MODELS",
    "TRAINABLE_MODELS",
    "ExperimentCondition",
    "ExperimentGrid",
    "ExperimentRunner",
    "ExperimentScenario",
    "FrozenModelDesign",
    "ValidationFunnel",
    "ValidationMaskUnit",
    "ValidationStage",
    "build_experiment_grid",
    "build_validation_funnel",
    "canonical_model_name",
    "load_frozen_model_design",
    "rank_validation_models",
    "run_experiments",
    "write_validation_model_ranking",
]
