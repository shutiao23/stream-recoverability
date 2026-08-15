"""Formal adapters for the official PyPOTS 1.5 reference imputers.

This module intentionally does not import the project-specific BRITS/SAITS-style
models in :mod:`deep_baselines`.  A reference adapter either uses the pinned
official PyPOTS implementation or fails closed.

The protocol builder mirrors the proposed model's comparison budget: fixed
artificial curriculum masks, half-window stride with a final right-aligned
window, target-only (``T``) scoring, and an equal-weight mean over the four
frozen validation scenarios.  The custom loop only controls data assembly and
model selection; all trainable cores and losses are the official PyPOTS 1.5
implementations.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pickle
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Literal, NamedTuple, cast

import numpy as np
import torch

from .proposed_curriculum import (
    CURRICULUM_SCENARIOS,
    FROZEN_VALIDATION_SCENARIOS,
    ProposedCurriculumConfig,
    generate_curriculum_mask,
    sample_curriculum_scenarios,
)

ReferenceModelName = Literal["brits", "saits", "csdi"]

PYPOTS_REQUIRED_VERSION = "1.5"
REFERENCE_CHECKPOINT_SCHEMA_VERSION = "pypots_reference_checkpoint_v1"
REFERENCE_PROTOCOL_SCHEMA_VERSION = "pypots_reference_protocol_v1"
REFERENCE_IMPLEMENTATION = "official_pypots_1.5"
VALIDATION_SCORE_AGGREGATION = "equal_mean_of_four_target_normalized_maes"
BRITS_TARGET_MIT_WEIGHT = 1.0

_REQUIRED_DIAGNOSTIC_FIELDS = (
    "parameter_count",
    "best_epoch",
    "epochs_run",
    "hit_epoch_limit",
    "validation_score_by_scenario",
    "training_time_seconds",
    "inference_time_seconds",
)


class _PyPOTSBindings(NamedTuple):
    version: str
    BRITS: type
    SAITS: type
    CSDI: type
    Adam: type
    parse_delta_torch: Callable[[torch.Tensor], torch.Tensor]


def require_pypots_15() -> _PyPOTSBindings:
    """Load the pinned official implementation or raise a clear hard failure."""

    try:
        installed_version = importlib_metadata.version("pypots")
    except importlib_metadata.PackageNotFoundError as error:
        raise ImportError(
            "formal reference baselines require optional dependency "
            "'pypots==1.5'; install the project's 'reference' extra"
        ) from error
    if installed_version != PYPOTS_REQUIRED_VERSION:
        raise RuntimeError(
            "formal reference baselines require exactly pypots==1.5; "
            f"found {installed_version!r}"
        )
    try:
        from pypots.data.utils import _parse_delta_torch
        from pypots.imputation import BRITS, CSDI, SAITS
        from pypots.optim import Adam
    except (
        Exception
    ) as error:  # an incomplete/broken optional install must not fall back
        raise ImportError(
            "pypots==1.5 is installed but its official imputation API could "
            "not be imported"
        ) from error

    expected_modules = {
        "BRITS": "pypots.imputation.brits.model",
        "SAITS": "pypots.imputation.saits.model",
        "CSDI": "pypots.imputation.csdi.model",
        "Adam": "pypots.optim.adam",
    }
    loaded = {"BRITS": BRITS, "SAITS": SAITS, "CSDI": CSDI, "Adam": Adam}
    for name, expected_module in expected_modules.items():
        if loaded[name].__module__ != expected_module:
            raise RuntimeError(
                f"unexpected PyPOTS {name} origin {loaded[name].__module__!r}; "
                f"expected {expected_module!r}"
            )
    return _PyPOTSBindings(
        version=installed_version,
        BRITS=BRITS,
        SAITS=SAITS,
        CSDI=CSDI,
        Adam=Adam,
        parse_delta_torch=_parse_delta_torch,
    )


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise TypeError(f"{name} must be an integer")
    if int(value) < 1:
        raise ValueError(f"{name} must be positive")
    return int(value)


def _non_negative_integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise TypeError(f"{name} must be an integer")
    if int(value) < 0:
        raise ValueError(f"{name} must be non-negative")
    return int(value)


def _immutable_array(value: object, *, dtype: np.dtype[Any] | type) -> np.ndarray:
    result = np.array(value, dtype=dtype, order="C", copy=True)
    result.setflags(write=False)
    return result


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    return value


def _canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        _json_ready(value),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _state_dict_sha256(state_dict: Mapping[str, torch.Tensor]) -> str:
    digest = hashlib.sha256()
    for name in sorted(state_dict):
        tensor = state_dict[name]
        if not isinstance(tensor, torch.Tensor):
            raise TypeError(f"state_dict entry {name!r} is not a tensor")
        contiguous = tensor.detach().cpu().contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(str(contiguous.dtype).encode("ascii"))
        digest.update(
            json.dumps(list(contiguous.shape), separators=(",", ":")).encode("ascii")
        )
        digest.update(contiguous.numpy().tobytes(order="C"))
    return digest.hexdigest()


def _validate_finite_state_dict(state_dict: object) -> Mapping[str, torch.Tensor]:
    if not isinstance(state_dict, Mapping) or not state_dict:
        raise ValueError("reference checkpoint requires a non-empty model_state_dict")
    typed: dict[str, torch.Tensor] = {}
    for name, value in state_dict.items():
        if not isinstance(name, str) or not isinstance(value, torch.Tensor):
            raise TypeError("reference checkpoint state_dict entries must be tensors")
        if torch.is_floating_point(value) and not torch.isfinite(value).all().item():
            raise ValueError(f"state_dict entry {name!r} must be finite")
        typed[name] = value
    return typed


def _window_starts(length: int, window: int) -> tuple[int, ...]:
    length = _positive_integer(length, "length")
    window = min(_positive_integer(window, "window"), length)
    stride = max(1, window // 2)
    starts = list(range(0, length - window + 1, stride))
    final = length - window
    if not starts or starts[-1] != final:
        starts.append(final)
    return tuple(starts)


@dataclass(frozen=True)
class ReferenceWindowDataset:
    """Fixed masked windows used by every official reference implementation."""

    X_ori: np.ndarray
    artificial_mask: np.ndarray
    score_mask: np.ndarray
    scenario_labels: tuple[str, ...]
    metadata: tuple[dict[str, Any], ...]

    def __post_init__(self) -> None:
        X_ori = _immutable_array(self.X_ori, dtype=np.float32)
        artificial = _immutable_array(self.artificial_mask, dtype=np.bool_)
        score = _immutable_array(self.score_mask, dtype=np.bool_)
        if X_ori.ndim != 3 or X_ori.shape[0] < 1:
            raise ValueError("X_ori must be a non-empty [sample, step, feature] array")
        if artificial.shape != X_ori.shape or score.shape != X_ori.shape:
            raise ValueError("artificial_mask and score_mask must match X_ori")
        finite = np.isfinite(X_ori)
        if np.any(artificial & ~finite):
            raise ValueError("artificial_mask may only hide finite eligible cells")
        if np.any(score & ~artificial):
            raise ValueError("score_mask must be a subset of artificial_mask")
        if np.any(score.reshape(len(score), -1).sum(axis=1) < 1):
            raise ValueError(
                "every reference window must score at least one target cell"
            )
        labels = tuple(str(value) for value in self.scenario_labels)
        rows = tuple(copy.deepcopy(dict(value)) for value in self.metadata)
        if len(labels) != len(X_ori) or len(rows) != len(X_ori):
            raise ValueError("scenario_labels and metadata must align with X_ori")
        object.__setattr__(self, "X_ori", X_ori)
        object.__setattr__(self, "artificial_mask", artificial)
        object.__setattr__(self, "score_mask", score)
        object.__setattr__(self, "scenario_labels", labels)
        object.__setattr__(self, "metadata", rows)

    @property
    def masked_X(self) -> np.ndarray:
        result = np.array(self.X_ori, copy=True)
        result[self.artificial_mask] = np.nan
        return result

    @property
    def values(self) -> np.ndarray:
        return self.X_ori

    @property
    def masked_values(self) -> np.ndarray:
        return self.masked_X

    @property
    def n_samples(self) -> int:
        return int(self.X_ori.shape[0])

    @property
    def n_steps(self) -> int:
        return int(self.X_ori.shape[1])

    @property
    def n_features(self) -> int:
        return int(self.X_ori.shape[2])

    @property
    def scenario_counts(self) -> dict[str, int]:
        return {
            scenario: self.scenario_labels.count(scenario)
            for scenario in dict.fromkeys(self.scenario_labels)
        }


@dataclass(frozen=True)
class ReferenceProtocolData:
    """Train-only scaling plus fixed train/validation reference windows."""

    train: ReferenceWindowDataset
    validation: ReferenceWindowDataset
    feature_mean: np.ndarray
    feature_scale: np.ndarray
    station_ids: tuple[str, ...]
    variable_names: tuple[str, ...]
    window_size: int
    stride: int
    protocol: str
    seed: int
    curriculum_config: dict[str, Any]
    fingerprint: str
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        stations = tuple(str(value) for value in self.station_ids)
        variables = tuple(str(value) for value in self.variable_names)
        if len(stations) < 2 or not variables:
            raise ValueError("reference protocol requires at least two stations")
        mean = _immutable_array(self.feature_mean, dtype=np.float32)
        scale = _immutable_array(self.feature_scale, dtype=np.float32)
        expected_shape = (len(stations), len(variables))
        if mean.shape != expected_shape or scale.shape != expected_shape:
            raise ValueError("feature scaler must match station/variable axes")
        if (
            not np.isfinite(mean).all()
            or not np.isfinite(scale).all()
            or np.any(scale <= 0)
        ):
            raise ValueError("feature scaler must be finite with positive scales")
        n_features = len(stations) * len(variables)
        if (
            self.train.n_steps != self.validation.n_steps
            or self.train.n_steps != int(self.window_size)
            or self.train.n_features != n_features
            or self.validation.n_features != n_features
        ):
            raise ValueError("reference windows do not match protocol dimensions")
        if self.protocol not in {"seen_length", "unseen_length"}:
            raise ValueError("protocol must be seen_length or unseen_length")
        if tuple(dict.fromkeys(self.validation.scenario_labels)) != tuple(
            FROZEN_VALIDATION_SCENARIOS
        ):
            raise ValueError("validation data must contain the frozen scenario order")
        counts = self.validation.scenario_counts
        if len(set(counts.values())) != 1:
            raise ValueError(
                "each frozen validation scenario needs the same window budget"
            )
        if len(self.fingerprint) != 64:
            raise ValueError("reference protocol fingerprint must be a SHA-256 digest")
        object.__setattr__(self, "feature_mean", mean)
        object.__setattr__(self, "feature_scale", scale)
        object.__setattr__(self, "station_ids", stations)
        object.__setattr__(self, "variable_names", variables)
        object.__setattr__(
            self, "curriculum_config", copy.deepcopy(self.curriculum_config)
        )
        object.__setattr__(self, "metadata", copy.deepcopy(self.metadata))

    @property
    def feature_mean_flat(self) -> np.ndarray:
        return self.feature_mean.reshape(-1)

    @property
    def feature_scale_flat(self) -> np.ndarray:
        return self.feature_scale.reshape(-1)


def _coerce_eligibility(
    values: np.ndarray, eligible: object | None, name: str
) -> np.ndarray:
    if eligible is None:
        return np.isfinite(values)
    raw = np.asarray(eligible)
    if raw.dtype != np.bool_ or raw.shape != values.shape:
        raise ValueError(f"{name} must be a boolean array matching its values")
    return np.array(raw & np.isfinite(values), dtype=np.bool_, copy=True)


def _build_fixed_windows(
    values: np.ndarray,
    eligible: np.ndarray,
    *,
    variable_names: tuple[str, ...],
    starts: tuple[int, ...],
    window: int,
    protocol: str,
    curriculum_seed: int,
    repeats: int,
    config: ProposedCurriculumConfig,
    validation: bool,
) -> ReferenceWindowDataset:
    target = {name.strip().upper(): index for index, name in enumerate(variable_names)}[
        "T"
    ]
    windows: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    scores: list[np.ndarray] = []
    labels: list[str] = []
    rows: list[dict[str, Any]] = []

    if validation:
        schedule_groups: Sequence[tuple[str, int]] = tuple(
            (scenario, curriculum_seed + 10_000 + scenario_index)
            for scenario_index, scenario in enumerate(FROZEN_VALIDATION_SCENARIOS)
        )
    else:
        schedule_groups = (("__training__", curriculum_seed),)

    for fixed_scenario, group_seed in schedule_groups:
        batch_count = len(starts) * repeats
        schedule = (
            tuple(fixed_scenario for _ in range(batch_count))
            if validation
            else sample_curriculum_scenarios(batch_count, group_seed, config)
        )
        schedule_index = 0
        for repeat in range(repeats):
            for start in starts:
                end = start + window
                mask_seed = int(
                    np.random.SeedSequence(
                        [int(group_seed), int(repeat), int(schedule_index)]
                    ).generate_state(1, dtype=np.uint32)[0]
                )
                generated = generate_curriculum_mask(
                    eligible[start:end],
                    variable_names,
                    scenario=cast(Any, schedule[schedule_index]),
                    protocol=protocol,
                    seed=mask_seed,
                    config=config,
                )
                artificial_3d = generated.artificial_mask
                score_3d = np.zeros_like(artificial_3d, dtype=bool)
                score_3d[..., target] = artificial_3d[..., target]
                if not score_3d.any():
                    raise AssertionError("curriculum generated no scorable T cells")
                label = (
                    str(fixed_scenario)
                    if validation
                    else str(generated.metadata["training_mask_type"])
                )
                row = {
                    **generated.metadata,
                    "reference_protocol_schema_version": REFERENCE_PROTOCOL_SCHEMA_VERSION,
                    "reference_split": "validation" if validation else "train",
                    "window_start": int(start),
                    "window_end": int(end - 1),
                    "window_length": int(window),
                    "repeat": int(repeat),
                    "schedule_index": int(schedule_index),
                    "input_mask_scope": "all_curriculum_channels",
                    "score_mask_scope": "T_only",
                }
                windows.append(values[start:end].reshape(window, -1))
                masks.append(artificial_3d.reshape(window, -1))
                scores.append(score_3d.reshape(window, -1))
                labels.append(label)
                rows.append(row)
                schedule_index += 1

    return ReferenceWindowDataset(
        X_ori=np.stack(windows),
        artificial_mask=np.stack(masks),
        score_mask=np.stack(scores),
        scenario_labels=tuple(labels),
        metadata=tuple(rows),
    )


def build_reference_protocol_data(
    train_values: np.ndarray,
    validation_values: np.ndarray,
    *,
    variable_names: Sequence[str],
    station_ids: Sequence[str],
    train_eligible: np.ndarray | None = None,
    validation_eligible: np.ndarray | None = None,
    window_size: int,
    protocol: str,
    seed: int,
    train_mask_repeats: int = 5,
    validation_mask_repeats: int = 1,
    curriculum_config: ProposedCurriculumConfig | None = None,
) -> ReferenceProtocolData:
    """Build a deterministic, equal-budget protocol for all reference models.

    Values have shape ``[time, station, variable]``.  Eligibility should combine
    natural-observation and quality approval; finite values outside it are
    converted to natural missingness before any model sees them.
    """

    train = np.asarray(train_values, dtype=np.float32)
    validation = np.asarray(validation_values, dtype=np.float32)
    if (
        train.ndim != 3
        or validation.ndim != 3
        or train.shape[1:] != validation.shape[1:]
    ):
        raise ValueError(
            "train_values and validation_values must be [time, station, variable] "
            "arrays with matching feature axes"
        )
    if train.shape[0] < 1 or validation.shape[0] < 1:
        raise ValueError("train and validation splits must be non-empty")
    stations = tuple(str(value) for value in station_ids)
    variables = tuple(str(value) for value in variable_names)
    if len(stations) != train.shape[1] or len(set(stations)) != len(stations):
        raise ValueError("station_ids must be unique and match the station axis")
    if len(variables) != train.shape[2] or len(set(variables)) != len(variables):
        raise ValueError("variable_names must be unique and match the variable axis")
    normalized_variables = {value.strip().upper() for value in variables}
    if not {"T", "F", "L"}.issubset(normalized_variables):
        raise ValueError("reference curriculum requires T/F/L variables")
    if not normalized_variables.intersection({"TA", "P", "W", "RH", "DH"}):
        raise ValueError("reference curriculum requires a meteorology variable")
    protocol = str(protocol)
    if protocol not in {"seen_length", "unseen_length"}:
        raise ValueError("protocol must be seen_length or unseen_length")
    seed = _non_negative_integer(seed, "seed")
    train_repeats = _positive_integer(train_mask_repeats, "train_mask_repeats")
    validation_repeats = _positive_integer(
        validation_mask_repeats, "validation_mask_repeats"
    )
    requested_window = _positive_integer(window_size, "window_size")
    window = min(requested_window, len(train), len(validation))
    stride = max(1, window // 2)
    config = curriculum_config or ProposedCurriculumConfig()

    train_allowed = _coerce_eligibility(train, train_eligible, "train_eligible")
    validation_allowed = _coerce_eligibility(
        validation, validation_eligible, "validation_eligible"
    )
    effective_train = np.where(train_allowed, train, np.nan).astype(np.float32)
    effective_validation = np.where(validation_allowed, validation, np.nan).astype(
        np.float32
    )

    mean = np.zeros(train.shape[1:], dtype=np.float32)
    scale = np.ones(train.shape[1:], dtype=np.float32)
    unavailable: list[dict[str, str]] = []
    for station in range(train.shape[1]):
        for variable in range(train.shape[2]):
            selected = train[:, station, variable][train_allowed[:, station, variable]]
            if not selected.size:
                unavailable.append(
                    {"station_id": stations[station], "variable": variables[variable]}
                )
                continue
            mean[station, variable] = float(selected.mean(dtype=np.float64))
            standard_deviation = float(selected.astype(np.float64).std(ddof=0))
            scale[station, variable] = (
                standard_deviation if standard_deviation >= 1e-6 else 1.0
            )

    train_starts = _window_starts(len(train), window)
    validation_starts = _window_starts(len(validation), window)
    train_windows = _build_fixed_windows(
        effective_train,
        train_allowed,
        variable_names=variables,
        starts=train_starts,
        window=window,
        protocol=protocol,
        curriculum_seed=seed,
        repeats=train_repeats,
        config=config,
        validation=False,
    )
    validation_windows = _build_fixed_windows(
        effective_validation,
        validation_allowed,
        variable_names=variables,
        starts=validation_starts,
        window=window,
        protocol=protocol,
        curriculum_seed=seed,
        repeats=validation_repeats,
        config=config,
        validation=True,
    )

    identity = {
        "schema_version": REFERENCE_PROTOCOL_SCHEMA_VERSION,
        "station_ids": stations,
        "variable_names": variables,
        "window_size": window,
        "stride": stride,
        "protocol": protocol,
        "seed": seed,
        "train_mask_repeats": train_repeats,
        "validation_mask_repeats": validation_repeats,
        "curriculum_config": config.metadata(),
        "train": {
            "X_ori": _array_sha256(train_windows.X_ori),
            "artificial_mask": _array_sha256(train_windows.artificial_mask),
            "score_mask": _array_sha256(train_windows.score_mask),
            "scenario_labels": train_windows.scenario_labels,
        },
        "validation": {
            "X_ori": _array_sha256(validation_windows.X_ori),
            "artificial_mask": _array_sha256(validation_windows.artificial_mask),
            "score_mask": _array_sha256(validation_windows.score_mask),
            "scenario_labels": validation_windows.scenario_labels,
        },
        "feature_mean": _array_sha256(mean),
        "feature_scale": _array_sha256(scale),
    }
    fingerprint = _canonical_json_sha256(identity)
    protocol_metadata = {
        "schema_version": REFERENCE_PROTOCOL_SCHEMA_VERSION,
        "requested_window_size": requested_window,
        "effective_window_size": window,
        "stride": stride,
        "train_window_starts": list(train_starts),
        "validation_window_starts": list(validation_starts),
        "train_mask_repeats": train_repeats,
        "validation_mask_repeats": validation_repeats,
        "training_scenarios": list(CURRICULUM_SCENARIOS),
        "validation_scenarios": list(FROZEN_VALIDATION_SCENARIOS),
        "validation_score_aggregation": VALIDATION_SCORE_AGGREGATION,
        "input_mask_scope": "all_curriculum_channels",
        "score_mask_scope": "T_only",
        "unavailable_train_features": unavailable,
        "fingerprint": fingerprint,
    }
    return ReferenceProtocolData(
        train=train_windows,
        validation=validation_windows,
        feature_mean=mean,
        feature_scale=scale,
        station_ids=stations,
        variable_names=variables,
        window_size=window,
        stride=stride,
        protocol=protocol,
        seed=seed,
        curriculum_config=config.metadata(),
        fingerprint=fingerprint,
        metadata=protocol_metadata,
    )


@dataclass(frozen=True)
class ReferenceTrainingConfig:
    """Training controls shared by the three official reference adapters."""

    epochs: int = 100
    patience: int = 10
    batch_size: int = 32
    learning_rate: float = 1e-3
    weight_decay: float = 0.0
    min_delta: float = 0.0
    gradient_clip: float = 1.0
    seed: int = 0
    device: str = "cpu"
    validation_sampling_times: int = 10
    prediction_sampling_times: int = 100

    def __post_init__(self) -> None:
        for field_name in (
            "epochs",
            "patience",
            "batch_size",
            "validation_sampling_times",
            "prediction_sampling_times",
        ):
            _positive_integer(getattr(self, field_name), field_name)
        _non_negative_integer(self.seed, "seed")
        for field_name in (
            "learning_rate",
            "weight_decay",
            "min_delta",
            "gradient_clip",
        ):
            value = float(getattr(self, field_name))
            if not np.isfinite(value) or value < 0:
                raise ValueError(f"{field_name} must be finite and non-negative")
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be positive")
        if not isinstance(self.device, str) or not self.device.strip():
            raise ValueError("device must be a non-empty torch device string")
        try:
            torch.device(self.device)
        except (RuntimeError, TypeError) as error:
            raise ValueError(f"invalid torch device {self.device!r}") from error


@dataclass(frozen=True)
class ReferencePrediction:
    """Unified deterministic point output and optional CSDI uncertainty."""

    point: np.ndarray
    samples: np.ndarray | None
    quantiles: dict[float, np.ndarray]
    interval: tuple[np.ndarray, np.ndarray] | None
    inference_time_seconds: float

    def __post_init__(self) -> None:
        point = _immutable_array(self.point, dtype=np.float32)
        samples = (
            None
            if self.samples is None
            else _immutable_array(self.samples, dtype=np.float32)
        )
        quantiles = {
            float(level): _immutable_array(value, dtype=np.float32)
            for level, value in sorted(self.quantiles.items())
        }
        interval = (
            None
            if self.interval is None
            else (
                _immutable_array(self.interval[0], dtype=np.float32),
                _immutable_array(self.interval[1], dtype=np.float32),
            )
        )
        if point.ndim != 3 or not np.isfinite(point).all():
            raise ValueError("point prediction must be finite [sample, step, feature]")
        if samples is not None:
            if (
                samples.ndim != 4
                or samples.shape[0] != point.shape[0]
                or samples.shape[2:] != point.shape[1:]
            ):
                raise ValueError("samples must be [sample, draw, step, feature]")
            if not np.isfinite(samples).all():
                raise ValueError("samples must be finite")
        if any(value.shape != point.shape for value in quantiles.values()):
            raise ValueError("quantile arrays must match point prediction")
        if interval is not None and (
            interval[0].shape != point.shape or interval[1].shape != point.shape
        ):
            raise ValueError("interval arrays must match point prediction")
        if (
            not np.isfinite(float(self.inference_time_seconds))
            or self.inference_time_seconds < 0
        ):
            raise ValueError("inference_time_seconds must be finite and non-negative")
        object.__setattr__(self, "point", point)
        object.__setattr__(self, "samples", samples)
        object.__setattr__(self, "quantiles", quantiles)
        object.__setattr__(self, "interval", interval)

    @property
    def interval_lower(self) -> np.ndarray | None:
        return None if self.interval is None else self.interval[0]

    @property
    def interval_upper(self) -> np.ndarray | None:
        return None if self.interval is None else self.interval[1]


_DEFAULT_MODEL_KWARGS: dict[str, dict[str, Any]] = {
    "brits": {"rnn_hidden_size": 64},
    "saits": {
        "n_layers": 2,
        "d_model": 64,
        "n_heads": 4,
        "d_k": 16,
        "d_v": 16,
        "d_ffn": 128,
        "dropout": 0.0,
        "attn_dropout": 0.0,
        "diagonal_attention_mask": True,
        "ORT_weight": 1,
        "MIT_weight": 1,
    },
    "csdi": {
        "n_layers": 4,
        "n_heads": 8,
        "n_channels": 64,
        "d_time_embedding": 128,
        "d_feature_embedding": 16,
        "d_diffusion_embedding": 128,
        "n_diffusion_steps": 50,
        "target_strategy": "random",
        "is_unconditional": False,
        "schedule": "quad",
        "beta_start": 0.0001,
        "beta_end": 0.5,
    },
}


def _effective_model_kwargs(
    model_name: ReferenceModelName, supplied: Mapping[str, Any] | None
) -> dict[str, Any]:
    result = copy.deepcopy(_DEFAULT_MODEL_KWARGS[model_name])
    provided = {} if supplied is None else dict(supplied)
    reserved = {
        "n_steps",
        "n_features",
        "batch_size",
        "epochs",
        "patience",
        "optimizer",
        "device",
        "saving_path",
        "model_saving_strategy",
        "verbose",
    }
    conflicts = sorted(reserved.intersection(provided))
    if conflicts:
        raise ValueError(
            "model_kwargs cannot override adapter/training fields: "
            + ", ".join(conflicts)
        )
    unknown = sorted(set(provided).difference(result))
    if unknown:
        raise ValueError(f"unknown {model_name} model_kwargs: {unknown}")
    result.update(provided)
    if model_name == "saits" and int(result["d_model"]) != int(result["n_heads"]) * int(
        result["d_k"]
    ):
        raise ValueError("SAITS requires d_model == n_heads * d_k")
    return result


def _seed_everything(seed: int) -> None:
    np.random.seed(int(seed))
    torch.manual_seed(int(seed))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(seed))


@contextmanager
def _isolated_torch_seed(seed: int, device: torch.device):
    devices: list[int] = []
    if device.type == "cuda":
        devices = [
            device.index if device.index is not None else torch.cuda.current_device()
        ]
    with torch.random.fork_rng(devices=devices, enabled=True):
        torch.manual_seed(int(seed))
        if device.type == "cuda":
            torch.cuda.manual_seed_all(int(seed))
        yield


def _as_numpy(value: object) -> np.ndarray:
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().numpy()
    return np.asarray(value)


class PyPOTSReferenceImputer:
    """Adapter around an official PyPOTS 1.5 BRITS, SAITS, or CSDI model."""

    def __init__(
        self,
        model_name: ReferenceModelName | str,
        n_steps: int,
        n_features: int,
        *,
        model_kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        normalized = str(model_name).lower()
        if normalized not in _DEFAULT_MODEL_KWARGS:
            raise ValueError("model_name must be one of: brits, saits, csdi")
        self.model_name = cast(ReferenceModelName, normalized)
        self.n_steps = _positive_integer(n_steps, "n_steps")
        self.n_features = _positive_integer(n_features, "n_features")
        self.model_kwargs = _effective_model_kwargs(self.model_name, model_kwargs)
        self.official_estimator_: Any | None = None
        self.diagnostics_: dict[str, Any] = {}
        self.metadata_: dict[str, Any] = {
            "implementation": REFERENCE_IMPLEMENTATION,
            "reference_status": "formal_reference_baseline",
            "fallback_policy": "fail_closed",
            "model_name": self.model_name,
            "pypots_required_version": PYPOTS_REQUIRED_VERSION,
        }
        self.training_config_: dict[str, Any] = {}
        self.protocol_fingerprint_: str | None = None
        self.protocol_metadata_: dict[str, Any] = {}
        self.station_ids_: tuple[str, ...] = ()
        self.variable_names_: tuple[str, ...] = ()
        self.feature_mean_: np.ndarray | None = None
        self.feature_scale_: np.ndarray | None = None
        self._is_fitted = False

    @property
    def model(self) -> torch.nn.Module:
        if self.official_estimator_ is None:
            raise RuntimeError("fit or load_checkpoint must be called first")
        return self.official_estimator_.model

    @property
    def pypots_model_(self) -> Any:
        if self.official_estimator_ is None:
            raise RuntimeError("fit or load_checkpoint must be called first")
        return self.official_estimator_

    def _instantiate(
        self, config: ReferenceTrainingConfig, bindings: _PyPOTSBindings
    ) -> Any:
        optimizer = bindings.Adam(
            lr=float(config.learning_rate), weight_decay=float(config.weight_decay)
        )
        common = {
            "n_steps": self.n_steps,
            "n_features": self.n_features,
            "batch_size": int(config.batch_size),
            "epochs": int(config.epochs),
            "patience": int(config.patience),
            "optimizer": optimizer,
            "num_workers": 0,
            "device": config.device,
            "saving_path": None,
            "model_saving_strategy": None,
            "verbose": False,
        }
        model_class = {
            "brits": bindings.BRITS,
            "saits": bindings.SAITS,
            "csdi": bindings.CSDI,
        }[self.model_name]
        try:
            estimator = model_class(**common, **self.model_kwargs)
        except Exception as error:
            raise RuntimeError(
                f"official PyPOTS 1.5 {self.model_name.upper()} initialization failed"
            ) from error
        core_module = estimator.model.__class__.__module__
        expected_core = f"pypots.imputation.{self.model_name}.core"
        if core_module != expected_core:
            raise RuntimeError(
                f"unexpected official core origin {core_module!r}; expected {expected_core!r}"
            )
        return estimator

    def _check_protocol(self, protocol: ReferenceProtocolData) -> None:
        if protocol.window_size != self.n_steps:
            raise ValueError(
                f"protocol window_size {protocol.window_size} != n_steps {self.n_steps}"
            )
        if protocol.train.n_features != self.n_features:
            raise ValueError(
                f"protocol n_features {protocol.train.n_features} != {self.n_features}"
            )

    def _scaled_dataset_arrays(
        self, dataset: ReferenceWindowDataset
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        if self.feature_mean_ is None or self.feature_scale_ is None:
            raise RuntimeError("training scaler is unavailable")
        mean = self.feature_mean_.reshape(-1)
        scale = self.feature_scale_.reshape(-1)
        finite = np.isfinite(dataset.X_ori)
        scaled_original = np.zeros(dataset.X_ori.shape, dtype=np.float32)
        broadcast_mean = mean.reshape(1, 1, -1)
        broadcast_scale = scale.reshape(1, 1, -1)
        normalized = (dataset.X_ori - broadcast_mean) / broadcast_scale
        scaled_original[finite] = normalized[finite]
        observed = finite & ~dataset.artificial_mask
        scaled_input = np.zeros_like(scaled_original)
        scaled_input[observed] = scaled_original[observed]
        return scaled_original, scaled_input, observed, np.array(dataset.score_mask)

    def _batch_inputs(
        self,
        arrays: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
        indices: np.ndarray,
        bindings: _PyPOTSBindings,
        device: torch.device,
    ) -> dict[str, Any]:
        original, masked, observed, score = arrays
        X_ori = torch.from_numpy(original[indices]).to(device)
        X = torch.from_numpy(masked[indices]).to(device)
        missing_mask = torch.from_numpy(observed[indices].astype(np.float32)).to(device)
        indicating_mask = torch.from_numpy(score[indices].astype(np.float32)).to(device)
        if self.model_name == "brits":
            backward_X = torch.flip(X, dims=(1,))
            backward_mask = torch.flip(missing_mask, dims=(1,))
            return {
                "indices": torch.from_numpy(indices.astype(np.int64)).to(device),
                "forward": {
                    "X": X,
                    "missing_mask": missing_mask,
                    "deltas": bindings.parse_delta_torch(missing_mask),
                },
                "backward": {
                    "X": backward_X,
                    "missing_mask": backward_mask,
                    "deltas": bindings.parse_delta_torch(backward_mask),
                },
                # The official BRITS core ignores these two extra fields while
                # training.  The adapter uses them below for the fixed-protocol
                # target-only masked-imputation term.
                "X_ori": X_ori,
                "indicating_mask": indicating_mask,
            }
        if self.model_name == "saits":
            return {
                "X": X,
                "missing_mask": missing_mask,
                "X_ori": X_ori,
                "indicating_mask": indicating_mask,
            }
        batch_size = len(indices)
        observed_tp = torch.arange(self.n_steps, dtype=torch.float32, device=device)
        return {
            "X_ori": X_ori.permute(0, 2, 1),
            "indicating_mask": indicating_mask.permute(0, 2, 1),
            "cond_mask": missing_mask.permute(0, 2, 1),
            "observed_tp": observed_tp.unsqueeze(0).repeat(batch_size, 1),
        }

    def _masked_scaled_input(self, dataset: ReferenceWindowDataset) -> np.ndarray:
        if self.feature_mean_ is None or self.feature_scale_ is None:
            raise RuntimeError("training scaler is unavailable")
        mean = self.feature_mean_.reshape(1, 1, -1)
        scale = self.feature_scale_.reshape(1, 1, -1)
        finite = np.isfinite(dataset.X_ori)
        observed = finite & ~dataset.artificial_mask
        result = np.full(dataset.X_ori.shape, np.nan, dtype=np.float32)
        normalized = (dataset.X_ori - mean) / scale
        result[observed] = normalized[observed]
        return result

    def _invoke_official_predict(
        self,
        masked_scaled: np.ndarray,
        *,
        n_sampling_times: int,
        seed: int,
    ) -> tuple[np.ndarray, np.ndarray | None, float]:
        if self.official_estimator_ is None:
            raise RuntimeError("official estimator is unavailable")
        device = torch.device(self.official_estimator_.device)
        started = time.perf_counter()
        with _isolated_torch_seed(seed, device), torch.inference_mode():
            if self.model_name == "csdi":
                result = self.official_estimator_.predict(
                    {"X": masked_scaled}, n_sampling_times=int(n_sampling_times)
                )
                samples = _as_numpy(result["imputation"]).astype(np.float32, copy=False)
                if samples.ndim != 4:
                    raise RuntimeError(
                        "official CSDI returned an unexpected sample shape"
                    )
                point = np.median(samples, axis=1).astype(np.float32)
            else:
                result = self.official_estimator_.predict({"X": masked_scaled})
                point = _as_numpy(result["imputation"]).astype(np.float32, copy=False)
                samples = None
        elapsed = time.perf_counter() - started
        if point.shape != masked_scaled.shape or not np.isfinite(point).all():
            raise RuntimeError(
                "official reference prediction is non-finite or mis-shaped"
            )
        if samples is not None and not np.isfinite(samples).all():
            raise RuntimeError("official CSDI returned non-finite samples")
        return point, samples, float(elapsed)

    def _validation_scores(
        self,
        dataset: ReferenceWindowDataset,
        config: ReferenceTrainingConfig,
    ) -> tuple[float, dict[str, float], float]:
        masked_scaled = self._masked_scaled_input(dataset)
        point, _, elapsed = self._invoke_official_predict(
            masked_scaled,
            n_sampling_times=(
                config.validation_sampling_times if self.model_name == "csdi" else 1
            ),
            seed=config.seed + 20_000,
        )
        original, _, _, _ = self._scaled_dataset_arrays(dataset)
        scenario_scores: dict[str, float] = {}
        for scenario in FROZEN_VALIDATION_SCENARIOS:
            rows = np.asarray(
                [label == scenario for label in dataset.scenario_labels], dtype=bool
            )
            selected = dataset.score_mask & rows[:, None, None]
            if not selected.any():
                raise ValueError(
                    f"validation scenario {scenario!r} has no scored T cells"
                )
            errors = np.abs(point[selected] - original[selected])
            if not np.isfinite(errors).all():
                raise RuntimeError(f"validation scenario {scenario!r} is non-finite")
            scenario_scores[scenario] = float(errors.mean(dtype=np.float64))
        if tuple(scenario_scores) != tuple(FROZEN_VALIDATION_SCENARIOS):
            raise AssertionError("validation scenarios escaped their frozen order")
        score = float(np.mean(tuple(scenario_scores.values()), dtype=np.float64))
        return score, scenario_scores, elapsed

    def fit(
        self,
        protocol: ReferenceProtocolData,
        config: ReferenceTrainingConfig | None = None,
    ) -> PyPOTSReferenceImputer:
        """Fit the official core on fixed masks and restore the best epoch."""

        config = config or ReferenceTrainingConfig(seed=protocol.seed)
        self._check_protocol(protocol)
        bindings = require_pypots_15()
        device = torch.device(config.device)
        if device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError(f"requested device {config.device!r} is unavailable")
        _seed_everything(config.seed)
        self.feature_mean_ = np.array(protocol.feature_mean, copy=True)
        self.feature_scale_ = np.array(protocol.feature_scale, copy=True)
        self.station_ids_ = protocol.station_ids
        self.variable_names_ = protocol.variable_names
        self.protocol_fingerprint_ = protocol.fingerprint
        self.protocol_metadata_ = copy.deepcopy(protocol.metadata)
        self.training_config_ = asdict(config)
        self.official_estimator_ = self._instantiate(config, bindings)
        estimator = self.official_estimator_
        arrays = self._scaled_dataset_arrays(protocol.train)
        shuffle = np.random.default_rng(config.seed + 17)
        history: list[dict[str, Any]] = []
        best_score = float("inf")
        best_epoch = 0
        best_by_scenario: dict[str, float] = {}
        best_state: dict[str, torch.Tensor] | None = None
        stale_epochs = 0
        training_started = time.perf_counter()

        for epoch in range(1, config.epochs + 1):
            estimator.model.train()
            order = shuffle.permutation(protocol.train.n_samples)
            batch_losses: list[tuple[float, int]] = []
            batch_components: list[tuple[dict[str, float], int]] = []
            for offset in range(0, len(order), config.batch_size):
                indices = order[offset : offset + config.batch_size]
                inputs = self._batch_inputs(arrays, indices, bindings, device)
                estimator.optimizer.zero_grad(set_to_none=True)
                results = estimator.model(inputs, calc_criterion=True)
                official_loss = results.get("loss")
                if (
                    not isinstance(official_loss, torch.Tensor)
                    or official_loss.ndim != 0
                ):
                    raise RuntimeError(
                        "official PyPOTS training core returned no scalar loss"
                    )
                component_values = {
                    "official_core_loss": float(official_loss.detach().cpu())
                }
                loss = official_loss
                if self.model_name == "brits":
                    imputation = results.get("imputation")
                    if not isinstance(imputation, torch.Tensor):
                        raise RuntimeError(
                            "official BRITS core returned no differentiable imputation"
                        )
                    target_mit = estimator.training_loss(
                        imputation,
                        inputs["X_ori"],
                        inputs["indicating_mask"],
                    )
                    if not isinstance(target_mit, torch.Tensor) or target_mit.ndim != 0:
                        raise RuntimeError(
                            "official BRITS MAE returned no scalar MIT loss"
                        )
                    loss = official_loss + BRITS_TARGET_MIT_WEIGHT * target_mit
                    component_values["target_only_MIT_loss"] = float(
                        target_mit.detach().cpu()
                    )
                if not torch.isfinite(loss).item():
                    raise RuntimeError(
                        f"official {self.model_name.upper()} produced non-finite training loss"
                    )
                loss.backward()
                if config.gradient_clip > 0:
                    torch.nn.utils.clip_grad_norm_(
                        estimator.model.parameters(), config.gradient_clip
                    )
                estimator.optimizer.step()
                batch_losses.append((float(loss.detach().cpu()), len(indices)))
                batch_components.append((component_values, len(indices)))
            train_loss = float(
                sum(loss * count for loss, count in batch_losses)
                / sum(count for _, count in batch_losses)
            )
            component_names = tuple(batch_components[0][0])
            train_loss_components = {
                name: float(
                    sum(values[name] * count for values, count in batch_components)
                    / sum(count for _, count in batch_components)
                )
                for name in component_names
            }
            validation_score, by_scenario, _ = self._validation_scores(
                protocol.validation, config
            )
            history.append(
                {
                    "epoch": epoch,
                    "train_loss": train_loss,
                    "train_loss_components": train_loss_components,
                    "validation_score": validation_score,
                    "validation_score_by_scenario": by_scenario,
                }
            )
            if validation_score < best_score - config.min_delta:
                best_score = validation_score
                best_epoch = epoch
                best_by_scenario = dict(by_scenario)
                best_state = {
                    name: value.detach().cpu().clone()
                    for name, value in estimator.model.state_dict().items()
                }
                stale_epochs = 0
            else:
                stale_epochs += 1
                if stale_epochs >= config.patience:
                    break

        training_time = time.perf_counter() - training_started
        if best_state is None or best_epoch < 1 or not np.isfinite(best_score):
            raise RuntimeError(
                "reference training produced no finite validation checkpoint"
            )
        estimator.model.load_state_dict(best_state, strict=True)
        estimator.model.eval()
        final_score, final_by_scenario, inference_time = self._validation_scores(
            protocol.validation, config
        )
        if not np.isclose(final_score, best_score, rtol=1e-6, atol=1e-7):
            raise RuntimeError(
                "restored best reference checkpoint changed validation score"
            )
        if any(
            not np.isclose(
                final_by_scenario[name], best_by_scenario[name], rtol=1e-6, atol=1e-7
            )
            for name in FROZEN_VALIDATION_SCENARIOS
        ):
            raise RuntimeError(
                "restored best checkpoint changed scenario validation scores"
            )

        epochs_run = len(history)
        self.diagnostics_ = {
            "parameter_count": int(
                sum(parameter.numel() for parameter in estimator.model.parameters())
            ),
            "best_epoch": int(best_epoch),
            "epochs_run": int(epochs_run),
            "hit_epoch_limit": bool(epochs_run == config.epochs),
            "validation_score_by_scenario": final_by_scenario,
            "training_time_seconds": float(training_time),
            "inference_time_seconds": float(inference_time),
            "best_validation_score": float(final_score),
            "validation_score_aggregation": VALIDATION_SCORE_AGGREGATION,
            "history": history,
        }
        self.metadata_ = {
            "implementation": REFERENCE_IMPLEMENTATION,
            "reference_status": "formal_reference_baseline",
            "fallback_policy": "fail_closed",
            "model_name": self.model_name,
            "pypots_version": bindings.version,
            "official_wrapper_class": {
                "module": estimator.__class__.__module__,
                "name": estimator.__class__.__name__,
            },
            "official_core_class": {
                "module": estimator.model.__class__.__module__,
                "name": estimator.model.__class__.__name__,
            },
            "optimizer_class": {
                "module": estimator.optimizer.__class__.__module__,
                "name": estimator.optimizer.__class__.__name__,
            },
            "protocol_fingerprint": protocol.fingerprint,
            "fixed_artificial_masks": True,
            "window_stride": "half_window_with_final_right_alignment",
            "score_mask_scope": "T_only",
            "validation_score_aggregation": VALIDATION_SCORE_AGGREGATION,
            "training_objective": (
                "official_consistency_and_observed_reconstruction_plus_target_only_MIT"
                if self.model_name == "brits"
                else "official_ORT_plus_target_only_MIT"
                if self.model_name == "saits"
                else "official_target_only_diffusion_noise_loss"
            ),
            "target_only_MIT_weight": BRITS_TARGET_MIT_WEIGHT
            if self.model_name == "brits"
            else None,
            "pinned_private_api": ["pypots.data.utils._parse_delta_torch"]
            if self.model_name == "brits"
            else [],
        }
        self._is_fitted = True
        return self

    def predict(
        self,
        values: np.ndarray,
        artificial_mask: np.ndarray | None = None,
        *,
        n_sampling_times: int | None = None,
        quantile_levels: Sequence[float] = (0.05, 0.25, 0.5, 0.75, 0.95),
        interval_levels: tuple[float, float] = (0.05, 0.95),
        seed: int | None = None,
    ) -> ReferencePrediction:
        """Predict from raw-scale windows without ever exposing hidden truth."""

        if (
            not self._is_fitted
            or self.feature_mean_ is None
            or self.feature_scale_ is None
        ):
            raise RuntimeError("fit or load_checkpoint must be called before predict")
        array = np.asarray(values, dtype=np.float32)
        if array.ndim != 3 or array.shape[1:] != (self.n_steps, self.n_features):
            raise ValueError(
                f"values must have shape [sample, {self.n_steps}, {self.n_features}]"
            )
        if len(array) < 1:
            raise ValueError("values must contain at least one sample")
        if artificial_mask is None:
            mask = np.zeros(array.shape, dtype=bool)
        else:
            raw_mask = np.asarray(artificial_mask)
            if raw_mask.dtype != np.bool_ or raw_mask.shape != array.shape:
                raise ValueError("artificial_mask must be boolean and match values")
            mask = np.array(raw_mask, copy=True)
        levels = tuple(float(level) for level in quantile_levels)
        if not levels or any(
            not np.isfinite(level) or not 0 < level < 1 for level in levels
        ):
            raise ValueError("quantile_levels must be finite values in (0, 1)")
        if len(set(levels)) != len(levels) or tuple(sorted(levels)) != levels:
            raise ValueError("quantile_levels must be unique and increasing")
        low, high = map(float, interval_levels)
        if not 0 < low < high < 1:
            raise ValueError("interval_levels must satisfy 0 < lower < upper < 1")
        prediction_seed = (
            _non_negative_integer(seed, "seed")
            if seed is not None
            else int(self.training_config_["seed"]) + 30_000
        )
        draws = (
            _positive_integer(n_sampling_times, "n_sampling_times")
            if n_sampling_times is not None
            else int(self.training_config_["prediction_sampling_times"])
        )
        mean = self.feature_mean_.reshape(1, 1, -1)
        scale = self.feature_scale_.reshape(1, 1, -1)
        observed = np.isfinite(array) & ~mask
        masked_scaled = np.full(array.shape, np.nan, dtype=np.float32)
        normalized = (array - mean) / scale
        masked_scaled[observed] = normalized[observed]
        point_scaled, samples_scaled, elapsed = self._invoke_official_predict(
            masked_scaled,
            n_sampling_times=draws if self.model_name == "csdi" else 1,
            seed=prediction_seed,
        )
        point = point_scaled * scale + mean
        point[observed] = array[observed]
        quantiles: dict[float, np.ndarray] = {}
        interval: tuple[np.ndarray, np.ndarray] | None = None
        samples: np.ndarray | None = None
        if samples_scaled is not None:
            samples = samples_scaled * scale[:, None, :, :] + mean[:, None, :, :]
            observed_draws = np.broadcast_to(observed[:, None], samples.shape)
            observed_values = np.broadcast_to(array[:, None], samples.shape)
            samples[observed_draws] = observed_values[observed_draws]
            for level in levels:
                value = np.quantile(samples, level, axis=1).astype(np.float32)
                value[observed] = array[observed]
                quantiles[level] = value
            interval_values = np.quantile(samples, (low, high), axis=1).astype(
                np.float32
            )
            interval_values[:, observed] = np.broadcast_to(
                array[observed], (2, int(observed.sum()))
            )
            interval = (interval_values[0], interval_values[1])
            point = np.median(samples, axis=1).astype(np.float32)
            point[observed] = array[observed]
        self.diagnostics_["inference_time_seconds"] = float(elapsed)
        return ReferencePrediction(
            point=point,
            samples=samples,
            quantiles=quantiles,
            interval=interval,
            inference_time_seconds=elapsed,
        )

    def _checkpoint_metadata(self) -> dict[str, Any]:
        if not self._is_fitted or self.official_estimator_ is None:
            raise RuntimeError("fit must be called before save_checkpoint")
        if self.feature_mean_ is None or self.feature_scale_ is None:
            raise RuntimeError("training scaler is unavailable")
        state = _validate_finite_state_dict(self.official_estimator_.model.state_dict())
        for field in _REQUIRED_DIAGNOSTIC_FIELDS:
            if field not in self.diagnostics_:
                raise ValueError(f"missing training diagnostic {field!r}")
        return {
            "schema_version": REFERENCE_CHECKPOINT_SCHEMA_VERSION,
            "implementation": REFERENCE_IMPLEMENTATION,
            "pypots_version": PYPOTS_REQUIRED_VERSION,
            "model_name": self.model_name,
            "adapter_config": {
                "n_steps": self.n_steps,
                "n_features": self.n_features,
                "model_kwargs": copy.deepcopy(self.model_kwargs),
            },
            "training_config": copy.deepcopy(self.training_config_),
            "protocol": {
                "fingerprint": self.protocol_fingerprint_,
                "metadata": copy.deepcopy(self.protocol_metadata_),
                "station_ids": list(self.station_ids_),
                "variable_names": list(self.variable_names_),
                "feature_mean": self.feature_mean_.tolist(),
                "feature_scale": self.feature_scale_.tolist(),
            },
            "official_classes": {
                "wrapper": copy.deepcopy(self.metadata_["official_wrapper_class"]),
                "core": copy.deepcopy(self.metadata_["official_core_class"]),
                "optimizer": copy.deepcopy(self.metadata_["optimizer_class"]),
            },
            "reference_metadata": copy.deepcopy(self.metadata_),
            "diagnostics": copy.deepcopy(self.diagnostics_),
            "state_dict_sha256": _state_dict_sha256(state),
        }

    def save_checkpoint(self, path: str | Path) -> Path:
        """Atomically save weights plus strict metadata and a file-hash sidecar."""

        if self.official_estimator_ is None:
            raise RuntimeError("fit must be called before save_checkpoint")
        metadata = self._checkpoint_metadata()
        metadata["metadata_sha256"] = _canonical_json_sha256(metadata)
        state = {
            name: value.detach().cpu().clone()
            for name, value in self.official_estimator_.model.state_dict().items()
        }
        payload = {**metadata, "model_state_dict": state}
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=output.parent,
                prefix=f".{output.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_name = handle.name
            torch.save(payload, temporary_name)
            os.replace(temporary_name, output)
            temporary_name = None
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
        file_hash = _sha256_file(output)
        sidecar = Path(str(output) + ".sha256")
        sidecar_temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="ascii",
                dir=sidecar.parent,
                prefix=f".{sidecar.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                sidecar_temporary = handle.name
                handle.write(file_hash + "\n")
            os.replace(sidecar_temporary, sidecar)
            sidecar_temporary = None
        finally:
            if sidecar_temporary is not None:
                Path(sidecar_temporary).unlink(missing_ok=True)
        return output

    @classmethod
    def load_checkpoint(
        cls,
        path: str | Path,
        *,
        expected_model_name: str | None = None,
        expected_protocol_fingerprint: str | None = None,
        expected_adapter_config: Mapping[str, Any] | None = None,
        expected_training_config: Mapping[str, Any] | None = None,
    ) -> PyPOTSReferenceImputer:
        """Load only a fully hashed, version-matched official checkpoint."""

        checkpoint = Path(path)
        sidecar = Path(str(checkpoint) + ".sha256")
        if not checkpoint.is_file() or not sidecar.is_file():
            raise ValueError(
                "reference checkpoint and .sha256 sidecar are both required"
            )
        expected_file_hash = sidecar.read_text(encoding="ascii").strip()
        if len(expected_file_hash) != 64 or any(
            value not in "0123456789abcdef" for value in expected_file_hash
        ):
            raise ValueError("reference checkpoint sidecar is not a SHA-256 digest")
        if _sha256_file(checkpoint) != expected_file_hash:
            raise ValueError("reference checkpoint file SHA-256 mismatch")
        try:
            try:
                payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
            except TypeError:  # PyTorch 2.0 compatibility
                payload = torch.load(checkpoint, map_location="cpu")
        except (EOFError, OSError, RuntimeError, pickle.UnpicklingError) as error:
            raise ValueError(
                "reference checkpoint payload cannot be decoded"
            ) from error
        if not isinstance(payload, Mapping):
            raise TypeError("reference checkpoint payload must be a mapping")
        if payload.get("schema_version") != REFERENCE_CHECKPOINT_SCHEMA_VERSION:
            raise ValueError("reference checkpoint schema version mismatch")
        if payload.get("implementation") != REFERENCE_IMPLEMENTATION:
            raise ValueError("reference checkpoint implementation mismatch")
        if payload.get("pypots_version") != PYPOTS_REQUIRED_VERSION:
            raise ValueError("reference checkpoint PyPOTS version mismatch")
        require_pypots_15()
        stored_metadata_hash = payload.get("metadata_sha256")
        metadata_for_hash = {
            key: value
            for key, value in payload.items()
            if key not in {"model_state_dict", "metadata_sha256"}
        }
        if (
            not isinstance(stored_metadata_hash, str)
            or _canonical_json_sha256(metadata_for_hash) != stored_metadata_hash
        ):
            raise ValueError("reference checkpoint metadata SHA-256 mismatch")
        state = _validate_finite_state_dict(payload.get("model_state_dict"))
        if _state_dict_sha256(state) != payload.get("state_dict_sha256"):
            raise ValueError("reference checkpoint state_dict SHA-256 mismatch")

        model_name = str(payload.get("model_name", ""))
        if (
            expected_model_name is not None
            and model_name != str(expected_model_name).lower()
        ):
            raise ValueError("reference checkpoint model name mismatch")
        adapter_config = payload.get("adapter_config")
        training_config = payload.get("training_config")
        protocol = payload.get("protocol")
        diagnostics = payload.get("diagnostics")
        reference_metadata = payload.get("reference_metadata")
        official_classes = payload.get("official_classes")
        if not all(
            isinstance(value, Mapping)
            for value in (
                adapter_config,
                training_config,
                protocol,
                diagnostics,
                reference_metadata,
                official_classes,
            )
        ):
            raise TypeError("reference checkpoint metadata fields must be mappings")
        adapter_config = dict(cast(Mapping[str, Any], adapter_config))
        training_config = dict(cast(Mapping[str, Any], training_config))
        protocol = dict(cast(Mapping[str, Any], protocol))
        diagnostics = dict(cast(Mapping[str, Any], diagnostics))
        if expected_adapter_config is not None and adapter_config != dict(
            expected_adapter_config
        ):
            raise ValueError("reference checkpoint adapter contract mismatch")
        if expected_training_config is not None and training_config != dict(
            expected_training_config
        ):
            raise ValueError("reference checkpoint training contract mismatch")
        if (
            expected_protocol_fingerprint is not None
            and protocol.get("fingerprint") != expected_protocol_fingerprint
        ):
            raise ValueError("reference checkpoint protocol fingerprint mismatch")
        for field in _REQUIRED_DIAGNOSTIC_FIELDS:
            if field not in diagnostics:
                raise ValueError(f"reference checkpoint misses diagnostic {field!r}")

        try:
            config = ReferenceTrainingConfig(**training_config)
            adapter = PyPOTSReferenceImputer(
                model_name,
                int(adapter_config["n_steps"]),
                int(adapter_config["n_features"]),
                model_kwargs=cast(Mapping[str, Any], adapter_config["model_kwargs"]),
            )
            bindings = require_pypots_15()
            adapter.official_estimator_ = adapter._instantiate(config, bindings)
            runtime_classes = {
                "wrapper": {
                    "module": adapter.official_estimator_.__class__.__module__,
                    "name": adapter.official_estimator_.__class__.__name__,
                },
                "core": {
                    "module": adapter.model.__class__.__module__,
                    "name": adapter.model.__class__.__name__,
                },
                "optimizer": {
                    "module": adapter.official_estimator_.optimizer.__class__.__module__,
                    "name": adapter.official_estimator_.optimizer.__class__.__name__,
                },
            }
            if runtime_classes != dict(cast(Mapping[str, Any], official_classes)):
                raise ValueError(
                    "reference checkpoint official class metadata mismatch"
                )
            adapter.model.load_state_dict(state, strict=True)
        except (KeyError, TypeError, RuntimeError) as error:
            if isinstance(error, ValueError):
                raise
            raise ValueError("reference checkpoint architecture is invalid") from error
        adapter.model.eval()
        station_ids = tuple(str(value) for value in protocol.get("station_ids", ()))
        variable_names = tuple(
            str(value) for value in protocol.get("variable_names", ())
        )
        feature_mean = np.asarray(protocol.get("feature_mean"), dtype=np.float32)
        feature_scale = np.asarray(protocol.get("feature_scale"), dtype=np.float32)
        if (
            feature_mean.shape != (len(station_ids), len(variable_names))
            or feature_scale.shape != feature_mean.shape
            or feature_mean.size != adapter.n_features
            or not np.isfinite(feature_mean).all()
            or not np.isfinite(feature_scale).all()
            or np.any(feature_scale <= 0)
        ):
            raise ValueError("reference checkpoint training scaler is invalid")
        adapter.feature_mean_ = feature_mean.copy()
        adapter.feature_scale_ = feature_scale.copy()
        adapter.station_ids_ = station_ids
        adapter.variable_names_ = variable_names
        adapter.protocol_fingerprint_ = cast(str, protocol.get("fingerprint"))
        adapter.protocol_metadata_ = copy.deepcopy(
            cast(dict[str, Any], protocol.get("metadata", {}))
        )
        adapter.training_config_ = training_config
        adapter.diagnostics_ = diagnostics
        adapter.metadata_ = copy.deepcopy(
            dict(cast(Mapping[str, Any], reference_metadata))
        )
        adapter._is_fitted = True
        _validate_finite_state_dict(adapter.model.state_dict())
        return adapter


ReferenceBaselineAdapter = PyPOTSReferenceImputer
OfficialPyPOTSReferenceImputer = PyPOTSReferenceImputer


__all__ = [
    "BRITS_TARGET_MIT_WEIGHT",
    "PYPOTS_REQUIRED_VERSION",
    "REFERENCE_CHECKPOINT_SCHEMA_VERSION",
    "REFERENCE_IMPLEMENTATION",
    "REFERENCE_PROTOCOL_SCHEMA_VERSION",
    "VALIDATION_SCORE_AGGREGATION",
    "OfficialPyPOTSReferenceImputer",
    "PyPOTSReferenceImputer",
    "ReferenceBaselineAdapter",
    "ReferencePrediction",
    "ReferenceProtocolData",
    "ReferenceTrainingConfig",
    "ReferenceWindowDataset",
    "build_reference_protocol_data",
    "require_pypots_15",
]
