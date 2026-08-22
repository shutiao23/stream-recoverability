"""Focused entry points for dense frontiers, network resilience, and compensation.

The dense block and network-resilience studies delegate execution to
:class:`ExperimentRunner`. The information study reuses a trained proposed-model
checkpoint and never trains or tunes on the test split. Mutual information and
transfer entropy are descriptive information measures; neither is interpreted as a
causal effect.
"""

from __future__ import annotations

import json
import pickle
from collections.abc import Mapping, Sequence
from dataclasses import replace
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import yaml

from stream_recoverability.analysis.compensation import (
    benjamini_hochberg_fdr,
    combination_label,
    knn_mutual_information,
    transfer_entropy,
)
from stream_recoverability.evaluation.event_metrics import compute_event_metrics
from stream_recoverability.masks import load_frontier_anchor_catalog
from stream_recoverability.models.baselines import (
    ClimatologyBaseline,
    _climatological_doy,
)
from stream_recoverability.models.proposed import (
    all_information_group_combinations,
    information_group_mask,
)
from stream_recoverability.models.proposed_training import (
    load_proposed_checkpoint,
    validate_proposed_checkpoint_contract,
)

from .contracts import canonical_evaluation_split, file_sha256
from .formal_authorization import authorize_proposed_estimand
from .grid import (
    DEFAULT_FRONTIER_ANCHOR_PATH,
    ExperimentCondition,
    ExperimentGrid,
    ExperimentScenario,
    bind_frontier_anchor,
)
from .runner import ExperimentRunner, _window_starts

DENSE_T_BLOCK_LENGTHS = (1, 3, 7, 10, 14, 21, 30, 45, 60, 90, 120, 150, 180, 240, 365)
DENSE_FL_BLOCK_LENGTHS = (3, 10, 30, 60, 90, 120, 180, 365)
COMPENSATION_T_BLOCK_LENGTHS = (10, 30, 90, 180)
RESILIENCE_BLOCK_LENGTHS = (10, 30, 90, 180)
FIXED_MASK_SEEDS = tuple(range(101, 121))
FIXED_TRAINING_SEEDS = (11, 22, 33, 44, 55)
INFORMATION_COMBINATION_LABELS = tuple(
    combination_label(value) for value in all_information_group_combinations()
)
EVIDENCE_TABLE_FIELDS = (
    "design_version",
    "data_version",
    "evaluation_split",
    "mask_schema_version",
    "model_schema_version",
    "statistics_schema_version",
)
SKIP_COLUMNS = (
    "scenario_id",
    "training_seed",
    "information_combination",
    "reason_code",
    "reason",
)
S0_DEFINITION = (
    "permanent proposed-model branch containing leap-aware calendar features, "
    "training-only target climatology, and static station identity; the climatology "
    "uses a reference-year-2000 month-day key, circular +/-7-day median, training-"
    "global median fallback, and a distinct February 29 key"
)
INFORMATION_ANOMALY_DEFINITION = (
    "approved training exact reference-year-2000 month-day mean anomaly; February 29 "
    "is a distinct calendar key"
)


def _read_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"expected a mapping in {path}")
    return value


def _selected_fixed_seeds(
    configured: Sequence[int], selected: Sequence[int] | None
) -> tuple[int, ...]:
    configured_tuple = tuple(int(value) for value in configured)
    if configured_tuple != FIXED_MASK_SEEDS:
        raise AssertionError("mask_seeds must be fixed at 101..120")
    if selected is None:
        return configured_tuple
    result = tuple(dict.fromkeys(int(value) for value in selected))
    unknown = sorted(set(result).difference(configured_tuple))
    if unknown:
        raise ValueError(f"mask seeds are not in the fixed manifest set: {unknown}")
    if not result:
        raise ValueError("at least one mask seed is required")
    return result


def _science_grid(
    manifest: Mapping[str, Any],
    conditions: Sequence[ExperimentCondition],
    *,
    suite: str,
    mask_seeds: Sequence[int] | None,
    data_version: str,
    evaluation_split: str,
    frontier_anchor_path: str | Path | None,
) -> ExperimentGrid:
    selected_mask_seeds = _selected_fixed_seeds(manifest["mask_seeds"], mask_seeds)
    training_seeds = tuple(int(value) for value in manifest["training_seeds"])
    if training_seeds != FIXED_TRAINING_SEEDS:
        raise AssertionError("training_seeds must be fixed at 11/22/33/44/55")
    canonical_split = canonical_evaluation_split(evaluation_split)
    if canonical_split != "development_test":
        raise ValueError(
            "the committed frontier catalog is frozen to development_test; "
            "a different split requires a separately frozen catalog"
        )
    anchored_conditions = tuple(
        replace(
            condition,
            data_version=str(data_version),
            evaluation_split=canonical_split,
            validation_scope="development_evaluation",
        )
        for condition in conditions
    )
    if len({condition.condition_id for condition in anchored_conditions}) != len(
        anchored_conditions
    ):
        raise AssertionError("science condition IDs must be unique")
    stations = tuple(manifest["data_panels"]["core"]["stations"])
    anchor_data_version = (
        "published_v2"
        if str(data_version) == "published_v2" or str(data_version).endswith("_v2")
        else "published_v1"
    )
    anchor_catalog = (
        load_frontier_anchor_catalog(
            frontier_anchor_path,
            expected_data_version=anchor_data_version,
            expected_evaluation_split="development_test",
            required_stations=stations,
            required_targets=("T", "F", "L"),
        )
        if frontier_anchor_path is not None
        else None
    )
    scenarios = tuple(
        ExperimentScenario(
            bind_frontier_anchor(condition, seed, anchor_catalog)
            if anchor_catalog is not None
            else condition,
            seed,
        )
        for condition in anchored_conditions
        for seed in selected_mask_seeds
    )
    external_status = str(manifest.get("external_validation_status", "unavailable"))
    return ExperimentGrid(
        suite=suite,
        conditions=anchored_conditions,
        scenarios=scenarios,
        mask_seeds=selected_mask_seeds,
        training_seeds=training_seeds,
        external_validation_status=external_status,
        frontier_anchor_catalog_path=(
            str(Path(frontier_anchor_path))
            if frontier_anchor_path is not None
            else None
        ),
        frontier_anchor_catalog_sha256=(
            file_sha256(frontier_anchor_path)
            if frontier_anchor_path is not None
            else None
        ),
        frontier_anchor_count=len(anchor_catalog) if anchor_catalog is not None else 0,
    )


def build_dense_science_grid(
    manifest_path: str | Path = "study_manifest.yaml",
    *,
    mask_seeds: Sequence[int] | None = None,
    data_version: str = "published_v1",
    evaluation_split: str = "development_test",
    frontier_anchor_path: str | Path | None = DEFAULT_FRONTIER_ANCHOR_PATH,
    variables: Sequence[str] | None = None,
) -> ExperimentGrid:
    """Build the dense single-gap grid.

    The frozen inventory is 93 conditions (T+F+L). Passing ``variables=('T',)``
    selects the 45-condition temperature frontier first.
    """

    manifest = _read_yaml(manifest_path)
    stations = tuple(
        str(value) for value in manifest["data_panels"]["core"]["stations"]
    )
    t_lengths = tuple(int(value) for value in manifest["dense_T_block_lengths"])
    fl_lengths = tuple(int(value) for value in manifest["dense_FL_block_lengths"])
    if t_lengths != DENSE_T_BLOCK_LENGTHS or fl_lengths != DENSE_FL_BLOCK_LENGTHS:
        raise AssertionError("dense block lengths do not match the fixed study design")
    window = int(manifest["window"]["science_dense"])
    if window != 736:
        raise AssertionError("the dense science window must be fixed at 736 days")
    selected = (
        ("T", "F", "L")
        if variables is None
        else tuple(dict.fromkeys(str(value) for value in variables))
    )
    unknown = sorted(set(selected).difference({"T", "F", "L"}))
    if unknown:
        raise ValueError(f"dense variables must be T, F, or L: {unknown}")
    if not selected:
        raise ValueError("dense experiments require at least one variable")
    lengths_by_variable = {"T": t_lengths, "F": fl_lengths, "L": fl_lengths}
    conditions = [
        ExperimentCondition(
            experiment="SCI_DENSE",
            condition_id=f"SCI-DENSE-BLK-{station}-{variable}-D{length:03d}",
            mask_type="block",
            station_ids=(station,),
            variables=(variable,),
            evaluation_variables=(variable,),
            gap_length=length,
            layout="single",
            window_length=window,
            validation_scope="internal_test",
        )
        for station in stations
        for variable in selected
        for length in lengths_by_variable[variable]
    ]
    return _science_grid(
        manifest,
        conditions,
        suite="science_dense",
        mask_seeds=mask_seeds,
        data_version=data_version,
        evaluation_split=evaluation_split,
        frontier_anchor_path=frontier_anchor_path,
    )


def build_compensation_grid(
    manifest_path: str | Path = "study_manifest.yaml",
    *,
    mask_seeds: Sequence[int] | None = None,
    data_version: str = "published_v1",
    evaluation_split: str = "development_test",
    frontier_anchor_path: str | Path | None = DEFAULT_FRONTIER_ANCHOR_PATH,
) -> ExperimentGrid:
    """Build fixed T-gap scenarios used by the 16 information combinations."""

    manifest = _read_yaml(manifest_path)
    stations = tuple(
        str(value) for value in manifest["data_panels"]["core"]["stations"]
    )
    window = int(manifest["window"]["main"])
    conditions = [
        ExperimentCondition(
            experiment="SCI_COMPENSATION",
            condition_id=f"SCI-COMP-BLK-{station}-T-D{length:03d}",
            mask_type="block",
            station_ids=(station,),
            variables=("T",),
            evaluation_variables=("T",),
            gap_length=length,
            layout="single",
            window_length=window,
            validation_scope="internal_test",
        )
        for station in stations
        for length in COMPENSATION_T_BLOCK_LENGTHS
    ]
    return _science_grid(
        manifest,
        conditions,
        suite="science_compensation",
        mask_seeds=mask_seeds,
        data_version=data_version,
        evaluation_split=evaluation_split,
        frontier_anchor_path=frontier_anchor_path,
    )


def build_resilience_science_grid(
    manifest_path: str | Path = "study_manifest.yaml",
    *,
    mask_seeds: Sequence[int] | None = None,
    data_version: str = "published_v1",
    evaluation_split: str = "development_test",
    frontier_anchor_path: str | Path | None = DEFAULT_FRONTIER_ANCHOR_PATH,
) -> ExperimentGrid:
    """Build the matched three-station failure powerset for target-T gaps."""

    manifest = _read_yaml(manifest_path)
    stations = tuple(
        str(value) for value in manifest["data_panels"]["core"]["stations"]
    )
    lengths = tuple(int(value) for value in manifest["block_lengths"])
    if len(stations) != 3:
        raise AssertionError(
            "the resilience powerset requires exactly three core stations"
        )
    if lengths != RESILIENCE_BLOCK_LENGTHS:
        raise AssertionError(
            "resilience block lengths do not match the fixed study design"
        )
    window = int(manifest["window"]["main"])
    failure_sets = tuple(
        failed
        for count in range(len(stations) + 1)
        for failed in combinations(stations, count)
    )
    conditions = [
        ExperimentCondition(
            experiment="SCI_NET",
            condition_id=(
                f"SCI-NET-{target}-T-D{length:03d}-F{len(failed)}-"
                f"{'NONE' if not failed else ''.join(failed)}"
            ),
            mask_type="matched_network",
            station_ids=(target,),
            variables=("T",),
            evaluation_variables=("T",),
            gap_length=length,
            layout="matched_target_gap",
            outage_mode="hydro-only",
            window_length=window,
            failed_station_ids=failed,
            validation_scope="internal_test",
        )
        for target in stations
        for length in lengths
        for failed in failure_sets
    ]
    if len(conditions) != 96:
        raise AssertionError("the resilience design must contain 96 conditions")
    return _science_grid(
        manifest,
        conditions,
        suite="science_resilience",
        mask_seeds=mask_seeds,
        data_version=data_version,
        evaluation_split=evaluation_split,
        frontier_anchor_path=frontier_anchor_path,
    )


def run_dense_experiments(
    *,
    manifest_path: str | Path = "study_manifest.yaml",
    config_path: str | Path = "configs/experiments.yaml",
    design_path: str | Path = "configs/design_freeze_v4.yaml",
    data_version_manifest_path: str | Path | None = None,
    wide_path: str | Path = "data/processed/daily_wide.parquet",
    quality_path: str | Path | None = "data/processed/daily_long.parquet",
    output_dir: str | Path = "results/science_experiments/dense",
    mask_dir: str | Path = "masks/science_dense",
    models: Sequence[str] = ("climatology", "linear"),
    training_seeds: Sequence[int] | None = None,
    formal_authorization: Mapping[str, Any] | None = None,
    mask_seeds: Sequence[int] | None = None,
    data_version: str = "published_v1",
    evaluation_split: str = "development_test",
    frontier_anchor_path: str | Path | None = DEFAULT_FRONTIER_ANCHOR_PATH,
    variables: Sequence[str] | None = None,
    shard_index: int = 0,
    shard_count: int = 1,
    max_scenarios: int | None = None,
    resume: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the dense grid through the existing unified runner."""

    grid = build_dense_science_grid(
        manifest_path,
        mask_seeds=mask_seeds,
        data_version=data_version,
        evaluation_split=evaluation_split,
        frontier_anchor_path=frontier_anchor_path,
        variables=variables,
    )
    runner = ExperimentRunner(
        grid,
        wide_path=wide_path,
        quality_path=quality_path,
        output_dir=output_dir,
        mask_dir=mask_dir,
        config_path=config_path,
        design_path=design_path,
        manifest_path=manifest_path,
        data_version_manifest_path=data_version_manifest_path,
        models=models,
        training_seeds=training_seeds,
        formal_authorization=formal_authorization,
        resume=resume,
    )
    return runner.run(
        shard_index=shard_index,
        shard_count=shard_count,
        max_scenarios=max_scenarios,
    )


def run_resilience_experiments(
    *,
    manifest_path: str | Path = "study_manifest.yaml",
    config_path: str | Path = "configs/experiments.yaml",
    design_path: str | Path = "configs/design_freeze_v4.yaml",
    data_version_manifest_path: str | Path | None = None,
    wide_path: str | Path = "data/processed/daily_wide.parquet",
    quality_path: str | Path | None = "data/processed/daily_long.parquet",
    output_dir: str | Path = "results/science_experiments/resilience",
    mask_dir: str | Path = "masks/science_resilience",
    models: Sequence[str] = ("climatology", "linear"),
    training_seeds: Sequence[int] | None = None,
    formal_authorization: Mapping[str, Any] | None = None,
    mask_seeds: Sequence[int] | None = None,
    data_version: str = "published_v1",
    evaluation_split: str = "development_test",
    frontier_anchor_path: str | Path | None = DEFAULT_FRONTIER_ANCHOR_PATH,
    shard_index: int = 0,
    shard_count: int = 1,
    max_scenarios: int | None = None,
    resume: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the matched station-failure powerset through the unified runner."""

    grid = build_resilience_science_grid(
        manifest_path,
        mask_seeds=mask_seeds,
        data_version=data_version,
        evaluation_split=evaluation_split,
        frontier_anchor_path=frontier_anchor_path,
    )
    runner = ExperimentRunner(
        grid,
        wide_path=wide_path,
        quality_path=quality_path,
        output_dir=output_dir,
        mask_dir=mask_dir,
        config_path=config_path,
        design_path=design_path,
        manifest_path=manifest_path,
        data_version_manifest_path=data_version_manifest_path,
        models=models,
        training_seeds=training_seeds,
        formal_authorization=formal_authorization,
        resume=resume,
    )
    return runner.run(
        shard_index=shard_index,
        shard_count=shard_count,
        max_scenarios=max_scenarios,
    )


def training_doy_climatology(
    dates: Sequence[object] | pd.DatetimeIndex,
    values: Sequence[float] | np.ndarray,
    train_rows: Sequence[bool] | np.ndarray,
    quality_approved: Sequence[bool] | np.ndarray | None = None,
) -> np.ndarray:
    """Apply the same leakage-safe climatology used by the unified runner."""

    date_index = pd.DatetimeIndex(pd.to_datetime(dates)).normalize()
    target = np.asarray(values, dtype=float)
    train = np.asarray(train_rows, dtype=bool)
    approved = (
        np.ones(len(target), dtype=bool)
        if quality_approved is None
        else np.asarray(quality_approved, dtype=bool)
    )
    if not (len(date_index) == len(target) == len(train) == len(approved)):
        raise ValueError("dates, values, train_rows, and quality_approved must align")
    fit_mask = train & approved & np.isfinite(target)
    if not fit_mask.any():
        raise ValueError(
            "S0 requires at least one approved finite training observation"
        )
    frame = pd.DataFrame({"date": date_index, "target": target})
    model = ClimatologyBaseline("target", window=7).fit(frame, train_mask=fit_mask)
    return model.predict(frame).to_numpy(dtype=float)


def _checkpoint_scaler(
    checkpoint: Mapping[str, Any],
    station_ids: Sequence[str],
    variable_names: Sequence[str],
) -> tuple[np.ndarray, np.ndarray]:
    scaler = checkpoint.get("train_scaler")
    if not isinstance(scaler, Mapping):
        raise TypeError("checkpoint is missing its training-only scaler")
    stored_stations = tuple(str(value) for value in scaler.get("station_ids", ()))
    stored_variables = tuple(str(value) for value in scaler.get("variable_names", ()))
    if stored_stations != tuple(station_ids) or stored_variables != tuple(
        variable_names
    ):
        raise ValueError("checkpoint scaler axes do not match the current data")
    mean = np.asarray(scaler.get("mean"), dtype=np.float32)
    scale = np.asarray(scaler.get("scale"), dtype=np.float32)
    expected = (len(station_ids), len(variable_names))
    if mean.shape != expected or scale.shape != expected:
        raise ValueError("checkpoint scaler shape does not match the current data")
    if (
        not np.isfinite(mean).all()
        or not np.isfinite(scale).all()
        or np.any(scale <= 0)
    ):
        raise ValueError("checkpoint scaler contains invalid values")
    return mean, scale


def predict_proposed_information_combinations(
    model: torch.nn.Module,
    values: np.ndarray,
    natural_mask: np.ndarray,
    artificial_mask: np.ndarray,
    seasonal_features: np.ndarray,
    mean: np.ndarray,
    scale: np.ndarray,
    *,
    target_index: int,
    training_climatology: np.ndarray | None = None,
    information_combinations: Sequence[Sequence[str]] | None = None,
    window_length: int | None = None,
    device: str | torch.device = "cpu",
) -> dict[str, dict[str, np.ndarray]]:
    """Infer frozen A/B/C/D coalitions through the proposed checkpoint.

    By default all 16 coalitions are evaluated, including the empty optional-source
    set labelled S0. S0 still passes through the same model and keeps its permanent
    calendar, training-climatology, and station-identity branch. Returned arrays are
    finite only at artificially hidden T cells; all other cells remain NaN.
    """

    array = np.asarray(values, dtype=np.float32)
    natural = np.asarray(natural_mask, dtype=bool)
    artificial = np.asarray(artificial_mask, dtype=bool)
    seasonal = np.asarray(seasonal_features, dtype=np.float32)
    if (
        array.ndim != 3
        or natural.shape != array.shape
        or artificial.shape != array.shape
    ):
        raise ValueError("values and masks must align as [time, station, variable]")
    if (
        np.asarray(mean).shape != array.shape[1:]
        or np.asarray(scale).shape != array.shape[1:]
    ):
        raise ValueError("scaler must match station and variable axes")
    if seasonal.ndim != 2 or seasonal.shape[0] != array.shape[0]:
        raise ValueError("seasonal_features must align with the time axis")
    if training_climatology is None:
        climatology = None
    else:
        climatology = np.asarray(training_climatology, dtype=np.float32)
        if climatology.shape != array.shape[:2]:
            raise ValueError(
                "training_climatology must align with time and station axes"
            )
    if not 0 <= target_index < array.shape[2]:
        raise ValueError("target_index is outside the variable axis")
    if window_length is None:
        window_length = len(array)
    if int(window_length) < 1:
        raise ValueError("window_length must be positive")

    # Removing hidden values before constructing the tensor makes the no-hidden-
    # truth invariant explicit instead of relying only on the model's internal mask.
    normalized = (array - mean[None]) / scale[None]
    normalized = normalized.copy()
    normalized[artificial] = np.nan
    combinations = (
        tuple(all_information_group_combinations())
        if information_combinations is None
        else tuple(
            tuple(str(group).upper() for group in value)
            for value in information_combinations
        )
    )
    allowed_combinations = set(all_information_group_combinations())
    if not combinations:
        raise ValueError("at least one information combination is required")
    if len(set(combinations)) != len(combinations):
        raise ValueError("information combinations must be unique")
    unknown = [value for value in combinations if value not in allowed_combinations]
    if unknown:
        raise ValueError(f"unknown information combinations: {unknown}")
    group_masks = torch.stack([information_group_mask(value) for value in combinations])
    batch_size = len(combinations)
    torch_device = torch.device(device)
    model = model.to(torch_device)
    model.eval()
    target_mean = np.asarray(mean, dtype=float)[:, target_index]
    target_scale = np.asarray(scale, dtype=float)[:, target_index]
    hidden_target = artificial[..., target_index]
    quantile_sum = np.zeros((batch_size, len(array), array.shape[1], 5), dtype=float)
    prediction_count = np.zeros(hidden_target.shape, dtype=np.int16)
    window = min(int(window_length), len(array))
    for start in _window_starts(len(array), window):
        end = start + window
        window_hidden = hidden_target[start:end]
        if not window_hidden.any():
            continue
        tensor_values = (
            torch.from_numpy(normalized[start:end])
            .unsqueeze(0)
            .expand(batch_size, -1, -1, -1)
        )
        tensor_natural = (
            torch.from_numpy(natural[start:end])
            .unsqueeze(0)
            .expand(batch_size, -1, -1, -1)
        )
        tensor_artificial = (
            torch.from_numpy(artificial[start:end])
            .unsqueeze(0)
            .expand(batch_size, -1, -1, -1)
        )
        tensor_seasonal = (
            torch.from_numpy(seasonal[start:end])
            .unsqueeze(0)
            .expand(batch_size, -1, -1)
        )
        tensor_climatology = (
            torch.from_numpy(climatology[start:end])
            .unsqueeze(0)
            .expand(batch_size, -1, -1)
            if climatology is not None
            else None
        )
        with torch.no_grad():
            model_kwargs: dict[str, Any] = {
                "seasonal_features": tensor_seasonal.to(torch_device),
                "enabled_groups": group_masks.to(torch_device),
            }
            if tensor_climatology is not None:
                model_kwargs["training_climatology"] = tensor_climatology.to(
                    torch_device
                )
            output = model(
                tensor_values.to(torch_device),
                tensor_natural.to(torch_device),
                tensor_artificial.to(torch_device),
                **model_kwargs,
            )
        raw = output["quantiles"].detach().cpu().numpy()
        expected_shape = (batch_size, window, array.shape[1], 5)
        if raw.shape != expected_shape:
            raise ValueError(
                f"model quantiles have shape {raw.shape}; expected {expected_shape}"
            )
        raw = raw * target_scale[None, None, :, None] + target_mean[None, None, :, None]
        quantile_sum[:, start:end] += np.where(window_hidden[None, ..., None], raw, 0.0)
        prediction_count[start:end] += window_hidden
    if np.any(hidden_target & (prediction_count == 0)):
        raise RuntimeError(
            "windowed information-combination prediction did not cover every hidden T cell"
        )
    result: dict[str, dict[str, np.ndarray]] = {}
    for index, combination in enumerate(combinations):
        label = combination_label(combination)
        averaged = np.full((len(array), array.shape[1], 5), np.nan, dtype=float)
        averaged[hidden_target] = (
            quantile_sum[index][hidden_target] / prediction_count[hidden_target, None]
        )
        result[label] = {
            "q05": averaged[..., 0],
            "q25": averaged[..., 1],
            "q50": averaged[..., 2],
            "q75": averaged[..., 3],
            "q95": averaged[..., 4],
        }
    return result


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.stem + ".tmp.parquet")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.stem + ".tmp.csv")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _atomic_json(value: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _compensation_training_seeds(
    grid: ExperimentGrid,
    training_seeds: Sequence[int] | None,
    training_seed: int | None,
) -> tuple[int, ...]:
    if training_seeds is not None and training_seed is not None:
        raise ValueError("use training_seeds or training_seed, not both")
    selected = (
        tuple(int(value) for value in training_seeds)
        if training_seeds is not None
        else (int(training_seed),)
        if training_seed is not None
        else tuple(grid.training_seeds)
    )
    selected = tuple(dict.fromkeys(selected))
    unknown = sorted(set(selected).difference(grid.training_seeds))
    if unknown:
        raise ValueError(f"training seeds are not in the fixed manifest set: {unknown}")
    if not selected:
        raise ValueError("at least one training seed is required")
    return selected


def _compensation_checkpoint_files(
    grid: ExperimentGrid,
    training_seeds: Sequence[int],
    *,
    checkpoint_path: str | Path | None,
    checkpoint_dir: str | Path,
    checkpoint_template: str,
) -> dict[int, Path]:
    windows = {condition.window_length for condition in grid.conditions}
    protocols = {condition.training_protocol for condition in grid.conditions}
    if len(windows) != 1 or len(protocols) != 1:
        raise ValueError(
            "compensation checkpoints require one fixed window and protocol"
        )
    window = next(iter(windows))
    protocol = next(iter(protocols))
    if checkpoint_path is not None:
        if len(training_seeds) != 1:
            raise ValueError("checkpoint_path can only be used with one training seed")
        return {int(training_seeds[0]): Path(checkpoint_path)}
    root = Path(checkpoint_dir)
    try:
        return {
            int(seed): root
            / checkpoint_template.format(
                seed=int(seed), window=int(window), protocol=str(protocol)
            )
            for seed in training_seeds
        }
    except (KeyError, ValueError) as error:
        raise ValueError(
            "checkpoint_template may only use {seed}, {window}, and {protocol}"
        ) from error


def _load_compensation_checkpoint(
    checkpoint_file: Path,
    runner: ExperimentRunner,
    *,
    training_seed: int,
    window_length: int,
    training_protocol: str,
    device: str,
) -> tuple[torch.nn.Module, np.ndarray, np.ndarray]:
    if not checkpoint_file.is_file():
        raise FileNotFoundError(f"checkpoint does not exist: {checkpoint_file}")
    try:
        model, checkpoint = load_proposed_checkpoint(
            checkpoint_file, map_location=device
        )
    except RuntimeError as error:
        raise ValueError(
            "checkpoint is incompatible with the current five-quantile architecture; retrain it"
        ) from error
    try:
        stored_quantile_levels = tuple(
            float(value) for value in checkpoint.get("quantile_levels", ())
        )
    except (TypeError, ValueError):
        stored_quantile_levels = ()
    if stored_quantile_levels != model.quantile_levels:
        raise ValueError(
            "checkpoint does not declare the required quantile levels "
            f"{model.quantile_levels}; retrain it"
        )
    (
        expected_model_config,
        expected_training_config,
        expected_training_context,
    ) = runner._proposed_contract(training_seed, window_length, training_protocol)
    validate_proposed_checkpoint_contract(
        checkpoint,
        expected_model_config=expected_model_config,
        expected_training_config=expected_training_config,
        expected_training_context=expected_training_context,
    )
    mean, scale = _checkpoint_scaler(
        checkpoint, runner.data.station_ids, runner.data.variable_names
    )
    if tuple(model.config.station_ids) != runner.data.station_ids:
        raise ValueError("checkpoint model station axes do not match the current data")
    if tuple(model.config.variable_names) != runner.data.variable_names:
        raise ValueError("checkpoint model variable axes do not match the current data")
    return model, mean, scale


def _compensation_unit_dir(
    output_root: Path, scenario_id: str, training_seed: int
) -> Path:
    return output_root / "units" / scenario_id / f"S{training_seed}"


def _compensation_checkpoint_status_path(output_root: Path, training_seed: int) -> Path:
    return output_root / "checkpoint_status" / f"S{training_seed}.json"


def _checkpoint_artifact_identity(checkpoint_file: Path) -> dict[str, Any] | None:
    try:
        stat = checkpoint_file.stat()
    except OSError:
        return None
    return {
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "sha256": file_sha256(checkpoint_file),
    }


def _compensation_unit_status(
    scenario: ExperimentScenario,
    training_seed: int,
    checkpoint_file: Path,
    *,
    status: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "status": status,
        "scenario_id": scenario.scenario_id,
        "training_seed": int(training_seed),
        "mask_seed": int(scenario.mask_seed),
        "checkpoint": str(checkpoint_file.resolve()),
        "checkpoint_artifact": _checkpoint_artifact_identity(checkpoint_file),
        "window_length": int(scenario.condition.window_length),
        "training_protocol": scenario.condition.training_protocol,
        "information_combinations": list(INFORMATION_COMBINATION_LABELS),
        **extra,
    }


def _compensation_unit_contract(
    runner: ExperimentRunner,
    scenario: ExperimentScenario,
    training_seed: int,
    checkpoint_file: Path,
) -> dict[str, Any]:
    contract = runner._run_execution_contract(scenario, "proposed", training_seed)
    artifact = _checkpoint_artifact_identity(checkpoint_file)
    contract["checkpoint"] = (
        {
            "path": str(checkpoint_file.resolve()),
            **artifact,
        }
        if artifact is not None
        else None
    )
    return json.loads(json.dumps(contract))


def _validate_compensation_unit(
    daily: pd.DataFrame,
    events: pd.DataFrame,
    scenario: ExperimentScenario,
    training_seed: int,
) -> None:
    labels = set(INFORMATION_COMBINATION_LABELS)
    required = {
        "scenario_id",
        "training_seed",
        "information_combination",
        "component_estimator",
        "attribution_estimand",
        *EVIDENCE_TABLE_FIELDS,
    }
    if not required.issubset(daily.columns) or not required.issubset(events.columns):
        raise ValueError("compensation unit is missing identity columns")
    if (
        len(events) != len(labels)
        or events["information_combination"].duplicated().any()
    ):
        raise ValueError(
            "compensation unit must contain exactly one event for each combination"
        )
    if set(events["information_combination"].astype(str)) != labels:
        raise ValueError(
            "compensation event unit does not contain the fixed 16 combinations"
        )
    if set(daily["information_combination"].astype(str)) != labels:
        raise ValueError(
            "compensation daily unit does not contain the fixed 16 combinations"
        )
    counts = daily.groupby("information_combination", observed=True).size()
    if counts.empty or counts.nunique() != 1:
        raise ValueError(
            "each information combination must score the same hidden T cells"
        )
    if daily.duplicated(
        ["information_combination", "station_id", "target", "date"]
    ).any():
        raise ValueError("compensation unit contains duplicate hidden T scores")
    identity_columns = ["date", "station_id", "target", "y_true"]
    reference_cells = set(
        daily.loc[
            daily["information_combination"].eq("S0"), identity_columns
        ].itertuples(index=False, name=None)
    )
    for label in labels.difference({"S0"}):
        cells = set(
            daily.loc[
                daily["information_combination"].eq(label), identity_columns
            ].itertuples(index=False, name=None)
        )
        if cells != reference_cells:
            raise ValueError("information combinations scored different hidden T cells")
    for frame in (daily, events):
        if not frame["scenario_id"].eq(scenario.scenario_id).all():
            raise ValueError("compensation unit scenario identity does not match")
        if not frame["training_seed"].eq(training_seed).all():
            raise ValueError("compensation unit training seed does not match")
        if not frame["component_estimator"].eq("proposed_checkpoint").all():
            raise ValueError(
                "every operational coalition must use the proposed checkpoint"
            )
        if not frame["attribution_estimand"].eq("operational_dropout").all():
            raise ValueError("compensation unit mixes information estimands")
    if not daily["quality_approved"].all() or not daily["artificial_mask"].all():
        raise ValueError(
            "compensation unit contains a non-approved or non-hidden score"
        )
    quantile_columns = ["q05", "q25", "q50", "q75", "q95"]
    quantiles = daily.loc[:, quantile_columns].to_numpy(dtype=float)
    if not np.isfinite(quantiles).all():
        raise ValueError("a coalition has nonfinite five-quantile predictions")
    if not np.all(np.diff(quantiles, axis=1) > 0):
        raise ValueError("coalition five-quantile predictions are not strictly ordered")
    required_metrics = ["MAE", "RMSE"]
    if (
        not set(required_metrics).issubset(events.columns)
        or not np.isfinite(events[required_metrics].to_numpy(dtype=float)).all()
    ):
        raise ValueError("compensation event MAE/RMSE must be finite")


def _read_resumable_compensation_unit(
    unit_dir: Path,
    scenario: ExperimentScenario,
    training_seed: int,
    checkpoint_file: Path | None,
    runner: ExperimentRunner,
) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    status_path = unit_dir / "status.json"
    daily_path = unit_dir / "daily_predictions.parquet"
    event_path = unit_dir / "event_metrics.parquet"
    if (
        not status_path.is_file()
        or not daily_path.is_file()
        or not event_path.is_file()
    ):
        return None
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
        expected_checkpoint = (
            str(checkpoint_file.resolve()) if checkpoint_file is not None else None
        )
        stored_checkpoint = status.get("checkpoint")
        current_checkpoint = (
            checkpoint_file
            if checkpoint_file is not None
            else Path(stored_checkpoint)
            if isinstance(stored_checkpoint, str)
            else None
        )
        runner._generate_mask(scenario)
        if (
            status.get("status") != "complete"
            or status.get("scenario_id") != scenario.scenario_id
            or status.get("training_seed") != training_seed
            or status.get("window_length") != scenario.condition.window_length
            or status.get("training_protocol") != scenario.condition.training_protocol
            or status.get("information_combinations")
            != list(INFORMATION_COMBINATION_LABELS)
            or (
                expected_checkpoint is not None
                and stored_checkpoint != expected_checkpoint
            )
            or current_checkpoint is None
            or status.get("checkpoint_artifact")
            != _checkpoint_artifact_identity(current_checkpoint)
            or status.get("execution_contract")
            != _compensation_unit_contract(
                runner, scenario, training_seed, current_checkpoint
            )
        ):
            return None
        daily = pd.read_parquet(daily_path)
        events = pd.read_parquet(event_path)
        _validate_compensation_unit(daily, events, scenario, training_seed)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
    return daily, events


def _score_compensation_unit(
    runner: ExperimentRunner,
    grid: ExperimentGrid,
    scenario: ExperimentScenario,
    training_seed: int,
    model: torch.nn.Module,
    mean: np.ndarray,
    scale: np.ndarray,
    s0_by_station: Mapping[int, np.ndarray],
    *,
    device: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    target_index = runner.data.variable_names.index("T")
    station = runner.data.station_ids.index(scenario.condition.station_ids[0])
    if station not in s0_by_station:
        raise ValueError("S0 training input is unavailable for the target station")
    artificial, metadata = runner._generate_mask(scenario)
    truth = runner.data.values[:, station, target_index].astype(float)
    quality = runner.data.quality_approved[:, station, target_index]
    hidden = artificial[:, station, target_index]
    positions = np.flatnonzero(hidden & quality & np.isfinite(truth))
    if positions.size == 0:
        raise ValueError(
            "no approved finite T observations were selected by the artificial mask"
        )
    proposed = predict_proposed_information_combinations(
        model,
        runner.data.values,
        runner.data.natural_observed,
        artificial,
        runner.data.seasonal_features,
        mean,
        scale,
        target_index=target_index,
        training_climatology=(
            np.column_stack(
                [s0_by_station[index] for index in range(len(runner.data.station_ids))]
            ).astype(np.float32)
            - mean[:, target_index][None, :]
        )
        / scale[:, target_index][None, :],
        window_length=scenario.condition.window_length,
        device=device,
    )
    if set(proposed) != set(INFORMATION_COMBINATION_LABELS):
        raise ValueError("proposed inference did not return all fixed 16 coalitions")

    climatology = s0_by_station[station]
    reference = runner._training_reference(station, target_index)
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
    daily_parts: list[pd.DataFrame] = []
    event_rows: list[dict[str, Any]] = []
    for label in INFORMATION_COMBINATION_LABELS:
        quantiles = proposed[label]
        component = "proposed_checkpoint"
        prediction = quantiles["q50"][:, station]
        q = {name: values[:, station] for name, values in quantiles.items()}
        if not np.isfinite(prediction[positions]).all():
            raise ValueError(
                f"{label} did not identify every approved artificial target"
            )
        row_metadata = {
            **metadata,
            "scenario_id": scenario.scenario_id,
            "station_id": runner.data.station_ids[station],
            "model": "information_compensation",
            "training_seed": training_seed,
            "mask_seed": scenario.mask_seed,
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
            quantile_predictions=q,
            high_threshold=reference.q90,
            low_threshold=reference.q10,
            ecological_threshold=None,
            normalization_iqr=reference.iqr,
            normalization_std=reference.std,
        )
        event.update(
            {
                "experiment": scenario.condition.experiment,
                "information_combination": label,
                "component_estimator": component,
                "estimator": component,
                "attribution_estimand": "operational_dropout",
                "information_estimand": "operational_dropout",
                "fit_split": "train",
                "tuning_split": "validation_checkpoint",
                "evaluation_split": runner.evaluation_split,
                "window_length": scenario.condition.window_length,
                "training_protocol": scenario.condition.training_protocol,
                "external_validation_status": grid.external_validation_status,
                "validation_scope": scenario.condition.validation_scope,
                "is_external_validation": False,
                "high_threshold": reference.q90,
                "low_threshold": reference.q10,
                "normalization_iqr": reference.iqr,
                "normalization_std": reference.std,
                "threshold_reference_split": "train",
                "normalization_reference_split": "train",
            }
        )
        event_rows.append(event)
        daily_parts.append(
            pd.DataFrame(
                {
                    "date": runner.data.dates[positions],
                    "station_id": runner.data.station_ids[station],
                    "target": "T",
                    "scenario_id": scenario.scenario_id,
                    "experiment": scenario.condition.experiment,
                    "mask_type": scenario.condition.mask_type,
                    "gap_length": scenario.condition.gap_length,
                    "missing_rate": scenario.condition.missing_rate,
                    "variable_pattern": "T",
                    "model": "information_compensation",
                    "training_seed": training_seed,
                    "mask_seed": scenario.mask_seed,
                    "information_combination": label,
                    "component_estimator": component,
                    "estimator": component,
                    "attribution_estimand": "operational_dropout",
                    "information_estimand": "operational_dropout",
                    "fit_split": "train",
                    "tuning_split": "validation_checkpoint",
                    "evaluation_split": runner.evaluation_split,
                    "y_true": truth[positions],
                    "y_pred": prediction[positions],
                    "climatology_pred": climatology[positions],
                    "q05": q["q05"][positions],
                    "q25": q["q25"][positions],
                    "q50": q["q50"][positions],
                    "q75": q["q75"][positions],
                    "q95": q["q95"][positions],
                    "season": seasons,
                    "event_type": None,
                    "quality_approved": quality[positions],
                    "artificial_mask": hidden[positions],
                    "high_threshold": reference.q90,
                    "low_threshold": reference.q10,
                    "normalization_iqr": reference.iqr,
                    "normalization_std": reference.std,
                    "threshold_reference_split": "train",
                    "normalization_reference_split": "train",
                    "window_length": scenario.condition.window_length,
                    "training_protocol": scenario.condition.training_protocol,
                    "external_validation_status": grid.external_validation_status,
                    "validation_scope": scenario.condition.validation_scope,
                    "is_external_validation": False,
                }
            )
        )
    daily = pd.concat(daily_parts, ignore_index=True)
    events = pd.DataFrame(event_rows)
    for field in EVIDENCE_TABLE_FIELDS:
        daily[field] = runner.evidence_contract[field]
        events[field] = runner.evidence_contract[field]
    daily["evidence_role"] = "formal_development_evaluation"
    events["evidence_role"] = "formal_development_evaluation"
    daily["formal_evidence"] = True
    events["formal_evidence"] = True
    _validate_compensation_unit(daily, events, scenario, training_seed)
    return daily, events


def _collect_compensation_units(
    output_root: Path,
    grid: ExperimentGrid,
    runner: ExperimentRunner,
    *,
    excluded_seeds: set[int],
    required_checkpoint_files: Mapping[int, Path],
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]], int]:
    daily_parts: list[pd.DataFrame] = []
    event_parts: list[pd.DataFrame] = []
    skips: list[dict[str, Any]] = []
    completed_units = 0
    for scenario in grid.scenarios:
        for training_seed in grid.training_seeds:
            if training_seed in excluded_seeds:
                continue
            checkpoint_file = required_checkpoint_files.get(training_seed)
            unit_dir = _compensation_unit_dir(
                output_root, scenario.scenario_id, training_seed
            )
            completed = _read_resumable_compensation_unit(
                unit_dir, scenario, training_seed, checkpoint_file, runner
            )
            if completed is not None:
                daily, events = completed
                daily_parts.append(daily)
                event_parts.append(events)
                completed_units += 1
                continue
            status_path = unit_dir / "status.json"
            if not status_path.is_file():
                continue
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
            except (OSError, TypeError, json.JSONDecodeError):
                continue
            if status.get("status") == "skipped":
                skips.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "training_seed": training_seed,
                        "information_combination": status.get(
                            "information_combination"
                        ),
                        "reason_code": status.get("reason_code", "unit_skipped"),
                        "reason": status.get("reason", "compensation unit was skipped"),
                    }
                )
    daily = pd.concat(daily_parts, ignore_index=True) if daily_parts else pd.DataFrame()
    events = (
        pd.concat(event_parts, ignore_index=True) if event_parts else pd.DataFrame()
    )
    if not daily.empty:
        daily = daily.sort_values(
            ["scenario_id", "training_seed", "information_combination", "date"],
            kind="stable",
        ).reset_index(drop=True)
    if not events.empty:
        events = events.sort_values(
            ["scenario_id", "training_seed", "information_combination"], kind="stable"
        ).reset_index(drop=True)
    return daily, events, skips, completed_units


def _assert_operational_compensation_directory(output_root: Path) -> None:
    manifest_path = output_root / "run_manifest.json"
    if not manifest_path.is_file():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("existing compensation run manifest is unreadable") from error
    estimand = manifest.get("attribution_estimand")
    if estimand not in {None, "operational_dropout"}:
        raise ValueError(
            "output directory already contains a different information estimand"
        )


def run_information_compensation(
    *,
    finalized_model_roster_path: str
    | Path = "results/validation_funnel/finalized_model_roster.json",
    selection_data_version_manifest_path: str
    | Path = "data_versions/published_v2/version_manifest.json",
    checkpoint_path: str | Path | None = None,
    checkpoint_dir: str | Path = "results/experiments/checkpoints",
    checkpoint_template: str = "proposed-S{seed}-W{window}-{protocol}.pt",
    manifest_path: str | Path = "study_manifest.yaml",
    config_path: str | Path = "configs/experiments.yaml",
    design_path: str | Path = "configs/design_freeze_v3.yaml",
    data_version_manifest_path: str | Path | None = None,
    wide_path: str | Path = "data/processed/daily_wide.parquet",
    quality_path: str | Path | None = "data/processed/daily_long.parquet",
    output_dir: str | Path = "results/science_experiments/compensation",
    mask_dir: str | Path = "masks/science_compensation",
    training_seeds: Sequence[int] | None = None,
    training_seed: int | None = None,
    mask_seeds: Sequence[int] | None = None,
    data_version: str = "published_v1",
    evaluation_split: str = "development_test",
    frontier_anchor_path: str | Path | None = DEFAULT_FRONTIER_ANCHOR_PATH,
    max_scenarios: int | None = None,
    device: str = "cpu",
    resume: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Score the fixed 16-combination contract for one or all five training seeds."""

    output_root = Path(output_dir)
    _assert_operational_compensation_directory(output_root)
    roster, formal_authorization = authorize_proposed_estimand(
        finalized_model_roster_path,
        suite="science_compensation",
        design_path=design_path,
        study_manifest_path=manifest_path,
        experiment_config_path=config_path,
        selection_data_version_manifest_path=selection_data_version_manifest_path,
    )
    if formal_authorization is None:
        manifest = {
            "schema_version": "operational_information_dropout_run_v1",
            "suite": "science_compensation",
            "status": "not_applicable",
            "complete": False,
            "formal_design_complete": False,
            "attribution_estimand": "operational_dropout",
            "information_estimand": "operational_dropout",
            "not_applicable_reason": ("proposed validation decision is framework_only"),
            "proposed_decision": roster.proposed_decision,
            "models": ["information_compensation"],
            "expected_formal_models": [],
            "finalized_model_roster": {
                "path": roster.manifest_path,
                "sha256": roster.manifest_sha256,
                "selected_models": list(roster.selected_models),
                "proposed_decision": roster.proposed_decision,
            },
            "data_version": data_version,
            "evaluation_split": canonical_evaluation_split(evaluation_split),
            "formal_evidence": False,
            "evidence_role": "not_applicable",
            "performance_row_count": 0,
        }
        _atomic_json(manifest, output_root / "run_manifest.json")
        return (
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(columns=SKIP_COLUMNS),
        )
    grid = build_compensation_grid(
        manifest_path,
        mask_seeds=mask_seeds,
        data_version=data_version,
        evaluation_split=evaluation_split,
        frontier_anchor_path=frontier_anchor_path,
    )
    if checkpoint_path is not None and training_seeds is None and training_seed is None:
        training_seed = grid.training_seeds[0]
    selected_training_seeds = _compensation_training_seeds(
        grid, training_seeds, training_seed
    )
    checkpoint_files = _compensation_checkpoint_files(
        grid,
        selected_training_seeds,
        checkpoint_path=checkpoint_path,
        checkpoint_dir=checkpoint_dir,
        checkpoint_template=checkpoint_template,
    )
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
        training_seeds=selected_training_seeds,
        formal_authorization=formal_authorization,
        resume=resume,
    )
    if not runner.anchor_availability.empty:
        _atomic_csv(
            runner.anchor_availability,
            output_root / "anchor_availability.csv",
        )
    windows = {condition.window_length for condition in grid.conditions}
    protocols = {condition.training_protocol for condition in grid.conditions}
    window_length = next(iter(windows))
    training_protocol = next(iter(protocols))
    loaded: dict[int, tuple[torch.nn.Module, np.ndarray, np.ndarray]] = {}
    invalid_seeds: set[int] = set()
    invocation_skips: list[dict[str, Any]] = []
    for seed in selected_training_seeds:
        checkpoint_file = checkpoint_files[seed]
        try:
            loaded[seed] = _load_compensation_checkpoint(
                checkpoint_file,
                runner,
                training_seed=seed,
                window_length=window_length,
                training_protocol=training_protocol,
                device=device,
            )
            _atomic_json(
                {
                    "status": "valid",
                    "training_seed": seed,
                    "checkpoint": str(checkpoint_file.resolve()),
                    "checkpoint_artifact": _checkpoint_artifact_identity(
                        checkpoint_file
                    ),
                    "window_length": int(window_length),
                    "training_protocol": training_protocol,
                    "training_profile": runner.training_profile_name,
                    "training_settings": runner.training_settings,
                    "information_combinations": list(INFORMATION_COMBINATION_LABELS),
                },
                _compensation_checkpoint_status_path(output_root, seed),
            )
        except (
            EOFError,
            OSError,
            KeyError,
            RuntimeError,
            TypeError,
            ValueError,
            pickle.UnpicklingError,
        ) as error:
            invalid_seeds.add(seed)
            _atomic_json(
                {
                    "status": "invalid",
                    "training_seed": seed,
                    "checkpoint": str(checkpoint_file.resolve()),
                    "reason_code": "checkpoint_unavailable_or_incompatible",
                    "reason": str(error),
                },
                _compensation_checkpoint_status_path(output_root, seed),
            )
            invocation_skips.append(
                {
                    "scenario_id": None,
                    "training_seed": seed,
                    "reason_code": "checkpoint_unavailable_or_incompatible",
                    "reason": str(error),
                }
            )
            for scenario in grid.scenarios:
                unit_dir = _compensation_unit_dir(
                    output_root, scenario.scenario_id, seed
                )
                _atomic_json(
                    _compensation_unit_status(
                        scenario,
                        seed,
                        checkpoint_file,
                        status="skipped",
                        reason_code="checkpoint_unavailable_or_incompatible",
                        reason=str(error),
                    ),
                    unit_dir / "status.json",
                )

    target_index = runner.data.variable_names.index("T")
    s0_by_station: dict[int, np.ndarray] = {}
    for station in range(len(runner.data.station_ids)):
        try:
            s0_by_station[station] = training_doy_climatology(
                runner.data.dates,
                runner.data.values[:, station, target_index],
                runner.train_rows,
                runner.data.quality_approved[:, station, target_index],
            )
        except ValueError:
            pass

    for seed, (model, mean, scale) in loaded.items():
        checkpoint_file = checkpoint_files[seed]
        for scenario in selected_scenarios:
            unit_dir = _compensation_unit_dir(output_root, scenario.scenario_id, seed)
            if (
                resume
                and _read_resumable_compensation_unit(
                    unit_dir, scenario, seed, checkpoint_file, runner
                )
                is not None
            ):
                continue
            _atomic_json(
                _compensation_unit_status(
                    scenario, seed, checkpoint_file, status="running"
                ),
                unit_dir / "status.json",
            )
            try:
                unit_daily, unit_events = _score_compensation_unit(
                    runner,
                    grid,
                    scenario,
                    seed,
                    model,
                    mean,
                    scale,
                    s0_by_station,
                    device=device,
                )
                _atomic_parquet(unit_daily, unit_dir / "daily_predictions.parquet")
                _atomic_parquet(unit_events, unit_dir / "event_metrics.parquet")
                _atomic_json(
                    _compensation_unit_status(
                        scenario,
                        seed,
                        checkpoint_file,
                        status="complete",
                        daily_rows=len(unit_daily),
                        event_rows=len(unit_events),
                        execution_contract=_compensation_unit_contract(
                            runner, scenario, seed, checkpoint_file
                        ),
                    ),
                    unit_dir / "status.json",
                )
            except (OSError, KeyError, RuntimeError, TypeError, ValueError) as error:
                _atomic_json(
                    _compensation_unit_status(
                        scenario,
                        seed,
                        checkpoint_file,
                        status="skipped",
                        reason_code="compensation_unit_failed",
                        reason=str(error),
                    ),
                    unit_dir / "status.json",
                )

    persisted_invalid_seeds = set(invalid_seeds)
    for seed in grid.training_seeds:
        status_path = _compensation_checkpoint_status_path(output_root, seed)
        if not status_path.is_file():
            continue
        try:
            checkpoint_status = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError):
            continue
        if checkpoint_status.get("status") == "invalid":
            persisted_invalid_seeds.add(seed)
    daily, events, unit_skips, completed_units = _collect_compensation_units(
        output_root,
        grid,
        runner,
        excluded_seeds=persisted_invalid_seeds,
        required_checkpoint_files={
            seed: checkpoint_files[seed]
            for seed in selected_training_seeds
            if seed not in invalid_seeds
        },
    )
    skipped = pd.DataFrame([*invocation_skips, *unit_skips]).reindex(
        columns=SKIP_COLUMNS
    )
    if not skipped.empty:
        skipped = skipped.drop_duplicates().sort_values(
            ["training_seed", "scenario_id"], na_position="first", kind="stable"
        )
    # Aggregates are always replaced, including the empty case, so a missing or
    # incompatible checkpoint cannot leave stale top-level scientific results.
    _atomic_parquet(daily, output_root / "daily_predictions.parquet")
    _atomic_parquet(events, output_root / "event_metrics.parquet")
    _atomic_csv(skipped, output_root / "skipped_runs.csv")
    expected_run_unit_keys = sorted(
        f"{scenario.scenario_id}|information_compensation:{seed}"
        for scenario in grid.scenarios
        for seed in grid.training_seeds
    )
    completed_run_unit_keys: list[str] = []
    if not events.empty:
        for (scenario_id, seed), unit in events.groupby(
            ["scenario_id", "training_seed"], observed=True, sort=True
        ):
            if len(unit) == len(INFORMATION_COMBINATION_LABELS) and set(
                unit["information_combination"].astype(str)
            ) == set(INFORMATION_COMBINATION_LABELS):
                completed_run_unit_keys.append(
                    f"{scenario_id}|information_compensation:{int(seed)}"
                )
    completed_run_unit_keys = sorted(completed_run_unit_keys)
    completed_set = set(completed_run_unit_keys)
    expected_set = set(expected_run_unit_keys)
    retryable_run_unit_keys = sorted(expected_set.difference(completed_set))
    selected_completed = sum(
        key.endswith(tuple(f":{seed}" for seed in selected_training_seeds))
        for key in completed_run_unit_keys
    )
    expected_selected_units = len(grid.scenarios) * len(selected_training_seeds)
    aggregate_training_seeds = (
        set(events["training_seed"].astype(int)) if not events.empty else set()
    )
    formal_training_seed_complete = aggregate_training_seeds == set(grid.training_seeds)
    formal_mask_seed_complete = set(grid.mask_seeds) == set(FIXED_MASK_SEEDS)
    expected_formal_units = len(expected_run_unit_keys)
    formal_unit_grid_complete = completed_set == expected_set

    valid_checkpoint_seeds: set[int] = set()
    training_checkpoints: list[dict[str, Any]] = []
    for seed in grid.training_seeds:
        status_path = _compensation_checkpoint_status_path(output_root, seed)
        try:
            checkpoint_status = json.loads(status_path.read_text(encoding="utf-8"))
            checkpoint_file = Path(checkpoint_status["checkpoint"])
            if checkpoint_status.get("status") != "valid" or checkpoint_status.get(
                "checkpoint_artifact"
            ) != _checkpoint_artifact_identity(checkpoint_file):
                continue
            _load_compensation_checkpoint(
                checkpoint_file,
                runner,
                training_seed=seed,
                window_length=window_length,
                training_protocol=training_protocol,
                device=device,
            )
            metadata = torch.load(
                checkpoint_file, map_location="cpu", weights_only=False
            )
        except (
            EOFError,
            FileNotFoundError,
            KeyError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            pickle.UnpicklingError,
        ):
            persisted_invalid_seeds.add(seed)
            continue
        valid_checkpoint_seeds.add(seed)
        artifact = _checkpoint_artifact_identity(checkpoint_file)
        training_checkpoints.append(
            {
                "model": "information_compensation",
                "training_seed": seed,
                "information_combinations": list(INFORMATION_COMBINATION_LABELS),
                "best_epoch": metadata.get("best_epoch", metadata.get("epoch")),
                "epochs_run": metadata.get("epochs_run"),
                "best_validation_score": metadata.get(
                    "best_validation_score", metadata.get("best_validation_loss")
                ),
                "checkpoint": {
                    "path": str(checkpoint_file.resolve()),
                    "size": artifact["size"],
                    "sha256": artifact["sha256"],
                },
                "checkpoint_sidecar": None,
                "checkpoint_contract_valid": True,
            }
        )
    checkpoint_required_run_unit_keys = expected_run_unit_keys
    checkpoint_valid_run_unit_keys = sorted(
        f"{scenario.scenario_id}|information_compensation:{seed}"
        for scenario in grid.scenarios
        for seed in valid_checkpoint_seeds
    )
    checkpoint_contract_complete = set(checkpoint_valid_run_unit_keys) == expected_set
    formal_design_complete = bool(
        runner.formal_evidence
        and formal_unit_grid_complete
        and formal_training_seed_complete
        and formal_mask_seed_complete
        and checkpoint_contract_complete
        and not persisted_invalid_seeds
    )
    exact_run_unit_fields = {
        "expected_run_unit_keys": expected_run_unit_keys,
        "completed_run_unit_keys": completed_run_unit_keys,
        "retryable_run_unit_keys": retryable_run_unit_keys,
        "structural_skip_run_unit_keys": [],
        "expected_evidence_run_unit_keys": expected_run_unit_keys,
        "completed_evidence_run_unit_keys": completed_run_unit_keys,
        "finite_prediction_run_unit_keys": completed_run_unit_keys,
        "finite_event_metric_run_unit_keys": completed_run_unit_keys,
        "checkpoint_required_run_unit_keys": checkpoint_required_run_unit_keys,
        "checkpoint_valid_run_unit_keys": checkpoint_valid_run_unit_keys,
    }
    exact_run_unit_counts = {
        f"{field.removesuffix('_keys')}_count": len(values)
        for field, values in exact_run_unit_fields.items()
    }
    exact_run_unit_counts["checkpoint_required_run_count"] = exact_run_unit_counts.pop(
        "checkpoint_required_run_unit_count"
    )
    exact_run_unit_counts["checkpoint_valid_run_count"] = exact_run_unit_counts.pop(
        "checkpoint_valid_run_unit_count"
    )
    _atomic_json(
        {
            "schema_version": "operational_information_dropout_run_v1",
            "suite": grid.suite,
            "models": ["information_compensation"],
            "expected_formal_models": ["information_compensation"],
            "status": (
                "complete"
                if formal_design_complete
                else "partial"
                if completed_units
                else "skipped"
            ),
            "complete": formal_design_complete,
            "formal_design_complete": formal_design_complete,
            "formal_unit_grid_complete": formal_unit_grid_complete,
            "formal_training_seed_complete": formal_training_seed_complete,
            "formal_mask_seed_complete": formal_mask_seed_complete,
            "run_unit_complete": formal_unit_grid_complete,
            "evidence_complete": formal_unit_grid_complete,
            "finite_predictions": formal_unit_grid_complete,
            "finite_event_metrics": formal_unit_grid_complete,
            "checkpoint_contract_complete": checkpoint_contract_complete,
            "retryable_run_keys": retryable_run_unit_keys,
            **exact_run_unit_fields,
            **exact_run_unit_counts,
            "expected_run_count": len(expected_run_unit_keys),
            "completed_status_run_count": len(completed_run_unit_keys),
            "aggregate_run_count": len(completed_run_unit_keys),
            "expected_training_seeds": list(grid.training_seeds),
            "expected_mask_seeds": list(FIXED_MASK_SEEDS),
            "expected_formal_units": expected_formal_units,
            "selected_scenarios_this_invocation": len(selected_scenarios),
            "grid_scenarios": len(grid.scenarios),
            "selected_training_seeds": list(selected_training_seeds),
            "fixed_training_seeds": list(grid.training_seeds),
            "expected_selected_units": expected_selected_units,
            "completed_selected_units": selected_completed,
            "completed_aggregate_units": completed_units,
            "completed_event_rows": len(events),
            "event_rows": len(events),
            "daily_rows": len(daily),
            "completed_daily_rows": len(daily),
            "training_checkpoints": training_checkpoints,
            "checkpoints": {
                str(seed): str(path.resolve())
                for seed, path in checkpoint_files.items()
            },
            "invalid_checkpoint_seeds": sorted(persisted_invalid_seeds),
            "mask_seeds": list(grid.mask_seeds),
            "information_combinations": list(INFORMATION_COMBINATION_LABELS),
            "fit_split": "train",
            "tuning_split": "validation_checkpoint",
            "evaluation_split": runner.evaluation_split,
            "data_version": runner.data.data_version,
            "data_version_input_identity": runner.data_version_input_identity,
            "frontier_anchor_catalog_path": grid.frontier_anchor_catalog_path,
            "frontier_anchor_catalog_sha256": grid.frontier_anchor_catalog_sha256,
            "frontier_anchor_count": grid.frontier_anchor_count,
            "formal_grid_contract_complete": runner.formal_grid_contract is not None,
            "formal_grid_contract": runner.formal_grid_contract,
            "anchor_availability_rows": len(runner.anchor_availability),
            "unavailable_anchor_rows": (
                int((~runner.anchor_availability["available"]).sum())
                if not runner.anchor_availability.empty
                else 0
            ),
            "anchor_replacement_allowed": False,
            "inference_window_length": int(window_length),
            "inference_stride": max(1, int(window_length) // 2),
            "training_profile": runner.training_profile_name,
            "training_settings": runner.training_settings,
            "s0_definition": S0_DEFINITION,
            "attribution_estimand": "operational_dropout",
            "information_estimand": "operational_dropout",
            "component_estimator": "proposed_checkpoint",
            "coalition_checkpoint_policy": "one_shared_checkpoint_per_training_seed",
            "hidden_truth_input_policy": "artificially hidden values are replaced by NaN before inference",
            "formal_evidence": formal_design_complete,
            "evidence_role": "formal_development_evaluation",
            "formal_execution_authorization": runner.formal_authorization,
            "finalized_model_roster": {
                "path": roster.manifest_path,
                "sha256": roster.manifest_sha256,
                "selected_models": list(roster.selected_models),
                "proposed_decision": roster.proposed_decision,
            },
            **runner.evidence_contract,
            "code_provenance": runner.code_provenance,
        },
        output_root / "run_manifest.json",
    )
    return daily, events, skipped


def _read_frame(value: pd.DataFrame | str | Path) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    path = Path(value)
    return (
        pd.read_parquet(path)
        if path.suffix.lower() == ".parquet"
        else pd.read_csv(path)
    )


def _quality_series(
    quality_long: pd.DataFrame | None,
    dates: pd.DatetimeIndex,
    station: str,
    variable: str,
) -> np.ndarray:
    if quality_long is None:
        return np.ones(len(dates), dtype=bool)
    selected = (
        quality_long.loc[
            (quality_long["station_id"].astype(str) == station)
            & (quality_long["variable"].astype(str) == variable)
        ]
        .drop_duplicates("date")
        .set_index("date")
    )
    return (
        selected["quality_approved"]
        .reindex(dates)
        .fillna(False)
        .astype(bool)
        .to_numpy()
    )


def _training_doy_anomaly(
    dates: pd.DatetimeIndex,
    values: np.ndarray,
    approved: np.ndarray,
) -> np.ndarray:
    """Remove the exact month-day training mean on a stable leap-year calendar."""

    result = np.full(len(values), np.nan, dtype=float)
    valid = np.asarray(approved, dtype=bool) & np.isfinite(values)
    if not valid.any():
        return result
    day = _climatological_doy(dates)
    means = pd.Series(values[valid]).groupby(day[valid]).mean()
    result[valid] = values[valid] - np.asarray(
        [float(means.loc[value]) for value in day[valid]], dtype=float
    )
    return result


def compute_training_information_metrics(
    daily_wide: pd.DataFrame | str | Path,
    *,
    quality_long: pd.DataFrame | str | Path | None = None,
    station_ids: Sequence[str] | None = None,
    n_neighbors: int = 5,
    lags: Sequence[int] = (1, 2, 3, 7),
    n_permutations: int = 199,
    n_bins: int = 4,
    seed: int = 11,
    deseasonalize: bool = True,
) -> pd.DataFrame:
    """Compute training-only kNN MI and bidirectional TE for candidate T sources.

    By default each series is converted to a training day-of-year anomaly so the
    shared annual cycle is not mistaken for cross-source information.
    """

    wide = _read_frame(daily_wide)
    required = {"date", "split"}
    if not required.issubset(wide):
        raise KeyError(
            f"daily_wide is missing {sorted(required.difference(wide.columns))}"
        )
    wide["date"] = pd.to_datetime(wide["date"]).dt.normalize()
    wide = wide.sort_values("date").reset_index(drop=True)
    if wide["date"].duplicated().any():
        raise ValueError("daily_wide contains duplicate dates")
    train = wide.loc[wide["split"].astype(str) == "train"].copy()
    if train.empty:
        raise ValueError("daily_wide contains no training rows")
    dates = pd.DatetimeIndex(train["date"])
    quality: pd.DataFrame | None = None
    if quality_long is not None:
        quality = _read_frame(quality_long)
        quality_required = {"date", "station_id", "variable", "quality_approved"}
        if not quality_required.issubset(quality):
            raise KeyError(
                f"quality_long is missing {sorted(quality_required.difference(quality.columns))}"
            )
        quality["date"] = pd.to_datetime(quality["date"]).dt.normalize()
    if station_ids is None:
        station_ids = sorted(
            str(column).rsplit("_", 1)[0]
            for column in train.columns
            if str(column).endswith("_T")
        )
    stations = tuple(str(value) for value in station_ids)
    rows: list[dict[str, Any]] = []
    te_hypotheses: dict[str, tuple[dict[str, Any], int]] = {}
    pair_index = 0
    for target_station in stations:
        target_column = f"{target_station}_T"
        if target_column not in train:
            rows.append(
                {
                    "target_station": target_station,
                    "target_variable": "T",
                    "source_station": None,
                    "source_variable": None,
                    "information_group": None,
                    "metric": "input_status",
                    "hypothesis_id": None,
                    "hypothesis_duplicate": False,
                    "seed": np.nan,
                    "direction": "not_evaluated",
                    "lag": np.nan,
                    "estimate": np.nan,
                    "n": 0,
                    "reason": f"missing target column {target_column}",
                    "interpretation": "input unavailable",
                    "fit_split": "train",
                }
            )
            continue
        source_specs = [
            *[(target_station, variable, "B") for variable in ("F", "L")],
            *[
                (target_station, variable, "D")
                for variable in ("Ta", "P", "W", "RH", "Rs")
            ],
            *[
                (source_station, variable, "C")
                for source_station in stations
                if source_station != target_station
                for variable in ("T", "F", "L")
            ],
        ]
        target = pd.to_numeric(train[target_column], errors="coerce").to_numpy(float)
        target_quality = _quality_series(quality, dates, target_station, "T")
        target_values = (
            _training_doy_anomaly(dates, target, target_quality)
            if deseasonalize
            else np.where(target_quality, target, np.nan)
        )
        for source_station, source_variable, group in source_specs:
            source_column = f"{source_station}_{source_variable}"
            if source_column not in train:
                rows.append(
                    {
                        "target_station": target_station,
                        "target_variable": "T",
                        "source_station": source_station,
                        "source_variable": source_variable,
                        "information_group": group,
                        "metric": "input_status",
                        "hypothesis_id": None,
                        "hypothesis_duplicate": False,
                        "seed": np.nan,
                        "direction": "not_evaluated",
                        "lag": np.nan,
                        "estimate": np.nan,
                        "n": 0,
                        "reason": f"missing source column {source_column}",
                        "interpretation": "input unavailable",
                        "fit_split": "train",
                    }
                )
                continue
            source = pd.to_numeric(train[source_column], errors="coerce").to_numpy(
                float
            )
            source_quality = _quality_series(
                quality, dates, source_station, source_variable
            )
            source_values = (
                _training_doy_anomaly(dates, source, source_quality)
                if deseasonalize
                else np.where(source_quality, source, np.nan)
            )
            approved = target_quality & source_quality
            x = np.where(approved, source_values, np.nan)
            y = np.where(approved, target_values, np.nan)
            common = {
                "target_station": target_station,
                "target_variable": "T",
                "source_station": source_station,
                "source_variable": source_variable,
                "information_group": group,
                "fit_split": "train",
                "series_preprocessing": (
                    "training_day_of_year_anomaly" if deseasonalize else "raw"
                ),
            }
            target_series = f"{target_station}_T"
            source_series = f"{source_station}_{source_variable}"
            mi_seed = seed + pair_index
            if (
                np.unique(x[np.isfinite(x)]).size < 2
                or np.unique(y[np.isfinite(y)]).size < 2
            ):
                mi = {
                    "mutual_information": np.nan,
                    "n": int((np.isfinite(x) & np.isfinite(y)).sum()),
                    "n_neighbors": n_neighbors,
                    "reason": "both paired series need at least two distinct values",
                }
            else:
                mi = knn_mutual_information(x, y, n_neighbors=n_neighbors, seed=mi_seed)
            rows.append(
                {
                    **common,
                    "metric": "knn_mutual_information",
                    "hypothesis_id": (
                        f"MI:{source_series}~{target_series}:target={target_series}"
                    ),
                    "hypothesis_duplicate": False,
                    "seed": mi_seed,
                    "direction": "contemporaneous_association",
                    "lag": 0,
                    "estimate": mi["mutual_information"],
                    "p_value": np.nan,
                    "n": mi["n"],
                    "n_neighbors": mi.get("n_neighbors", n_neighbors),
                    "reason": mi.get("reason"),
                    "interpretation": "statistical association, not causation",
                }
            )
            for direction_index, (driver, response, direction) in enumerate(
                (
                    (x, y, "source_to_target"),
                    (y, x, "target_to_source"),
                )
            ):
                driver_series, response_series = (
                    (source_series, target_series)
                    if direction == "source_to_target"
                    else (target_series, source_series)
                )
                for lag_index, lag in enumerate(lags):
                    hypothesis_id = (
                        f"TE:{driver_series}->{response_series}:lag={int(lag)}"
                    )
                    duplicate = hypothesis_id in te_hypotheses
                    if duplicate:
                        te, te_seed = te_hypotheses[hypothesis_id]
                    else:
                        te_seed = (
                            seed + pair_index * 100 + direction_index * 20 + lag_index
                        )
                        te = transfer_entropy(
                            driver,
                            response,
                            lag=int(lag),
                            n_bins=n_bins,
                            n_permutations=n_permutations,
                            seed=te_seed,
                        )
                        te_hypotheses[hypothesis_id] = (te, te_seed)
                    rows.append(
                        {
                            **common,
                            "metric": "transfer_entropy",
                            "hypothesis_id": hypothesis_id,
                            "hypothesis_duplicate": duplicate,
                            "seed": te_seed,
                            "direction": direction,
                            "lag": int(lag),
                            "estimate": te["transfer_entropy"],
                            "p_value": te["p_value"],
                            "n": te["n"],
                            "n_bins": te.get("n_bins", n_bins),
                            "n_permutations": te.get("n_permutations", n_permutations),
                            "null_mean": te.get("null_mean", np.nan),
                            "null_std": te.get("null_std", np.nan),
                            "z_score": te.get("z_score", np.nan),
                            "reason": te.get("reason"),
                            "interpretation": "directional predictive information, not causation",
                        }
                    )
            pair_index += 1
    result = pd.DataFrame(rows)
    if not result.empty:
        result["series_preprocessing_definition"] = (
            INFORMATION_ANOMALY_DEFINITION
            if deseasonalize
            else "approved raw training values without seasonal adjustment"
        )
        if "p_value" not in result:
            result["p_value"] = np.nan
        result["p_fdr_bh"] = np.nan
        te_rows = (
            result["metric"].eq("transfer_entropy") & result["hypothesis_id"].notna()
        )
        unique_te = result.loc[te_rows].drop_duplicates("hypothesis_id", keep="first")
        adjusted = benjamini_hochberg_fdr(unique_te["p_value"])
        adjusted_by_hypothesis = dict(
            zip(unique_te["hypothesis_id"], adjusted, strict=True)
        )
        result.loc[te_rows, "p_fdr_bh"] = result.loc[te_rows, "hypothesis_id"].map(
            adjusted_by_hypothesis
        )
        result["significant_fdr_05"] = result["p_fdr_bh"].le(0.05)
    return result


def write_training_information_metrics(
    daily_wide: pd.DataFrame | str | Path,
    output_path: str | Path = "results/analysis/information_metrics.csv",
    *,
    evidence_contract: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> pd.DataFrame:
    """Compute and atomically write the training-only information table."""

    result = compute_training_information_metrics(daily_wide, **kwargs)
    if evidence_contract is not None:
        for key, value in evidence_contract.items():
            result[key] = (
                json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (Mapping, list, tuple))
                else value
            )
    result["evidence_role"] = "training_only_association"
    result["formal_evidence"] = False
    result["test_or_confirmatory_values_used"] = False
    _atomic_csv(result, Path(output_path))
    return result


__all__ = [
    "COMPENSATION_T_BLOCK_LENGTHS",
    "DENSE_FL_BLOCK_LENGTHS",
    "DENSE_T_BLOCK_LENGTHS",
    "RESILIENCE_BLOCK_LENGTHS",
    "build_compensation_grid",
    "build_dense_science_grid",
    "build_resilience_science_grid",
    "compute_training_information_metrics",
    "predict_proposed_information_combinations",
    "run_dense_experiments",
    "run_information_compensation",
    "run_resilience_experiments",
    "training_doy_climatology",
    "write_training_information_metrics",
]
