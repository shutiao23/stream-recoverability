"""Focused experiment entry points for dense frontiers and information compensation.

The dense block study deliberately delegates execution to :class:`ExperimentRunner`.
The information study reuses a trained proposed-model checkpoint and never trains or
tunes on the test split.  Mutual information and transfer entropy are descriptive
information measures; neither is interpreted as a causal effect.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import yaml

from stream_recoverability.analysis.compensation import (
    combination_label,
    knn_mutual_information,
    transfer_entropy,
)
from stream_recoverability.evaluation.event_metrics import compute_event_metrics
from stream_recoverability.models.proposed import (
    all_information_group_combinations,
    information_group_mask,
)
from stream_recoverability.models.proposed_training import load_proposed_checkpoint

from .grid import ExperimentCondition, ExperimentGrid, ExperimentScenario
from .runner import ExperimentRunner

DENSE_T_BLOCK_LENGTHS = (1, 3, 7, 10, 14, 21, 30, 45, 60, 90, 120, 150, 180, 240, 365)
DENSE_FL_BLOCK_LENGTHS = (3, 10, 30, 60, 90, 120, 180, 365)
COMPENSATION_T_BLOCK_LENGTHS = (10, 30, 90, 180)
FIXED_MASK_SEEDS = tuple(range(101, 121))
FIXED_TRAINING_SEEDS = (11, 22, 33, 44, 55)
SKIP_COLUMNS = (
    "scenario_id",
    "training_seed",
    "information_combination",
    "reason_code",
    "reason",
)
MIXED_BASELINE_LIMITATION = (
    "S0 is a training-only day-of-year climatology, whereas non-empty A/B/C/D "
    "combinations are ablations of one trained proposed model; their contrast is a "
    "mixed-estimator information analysis, not a pure architectural ablation. In "
    "the checkpoint architecture, supplied calendar features share branch D with "
    "meteorology, so non-empty branch ablations cannot hold S0 as a separate branch."
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
) -> ExperimentGrid:
    selected_mask_seeds = _selected_fixed_seeds(manifest["mask_seeds"], mask_seeds)
    training_seeds = tuple(int(value) for value in manifest["training_seeds"])
    if training_seeds != FIXED_TRAINING_SEEDS:
        raise AssertionError("training_seeds must be fixed at 11/22/33/44/55")
    if len({condition.condition_id for condition in conditions}) != len(conditions):
        raise AssertionError("science condition IDs must be unique")
    scenarios = tuple(
        ExperimentScenario(condition, seed)
        for condition in conditions
        for seed in selected_mask_seeds
    )
    external_status = str(
        manifest.get("external_validation_status", "unavailable")
    )
    return ExperimentGrid(
        suite=suite,
        conditions=tuple(conditions),
        scenarios=scenarios,
        mask_seeds=selected_mask_seeds,
        training_seeds=training_seeds,
        external_validation_status=external_status,
    )


def build_dense_science_grid(
    manifest_path: str | Path = "study_manifest.yaml",
    *,
    mask_seeds: Sequence[int] | None = None,
) -> ExperimentGrid:
    """Build the 93-condition, 1,860-scenario dense single-gap grid."""

    manifest = _read_yaml(manifest_path)
    stations = tuple(str(value) for value in manifest["data_panels"]["core"]["stations"])
    t_lengths = tuple(int(value) for value in manifest["dense_T_block_lengths"])
    fl_lengths = tuple(int(value) for value in manifest["dense_FL_block_lengths"])
    if t_lengths != DENSE_T_BLOCK_LENGTHS or fl_lengths != DENSE_FL_BLOCK_LENGTHS:
        raise AssertionError("dense block lengths do not match the fixed study design")
    window = int(manifest["window"]["main"])
    long_window = max(int(value) for value in manifest["window"]["sensitivity"])
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
            window_length=long_window if length == 365 else window,
            validation_scope="internal_test",
        )
        for station in stations
        for variable, lengths in (("T", t_lengths), ("F", fl_lengths), ("L", fl_lengths))
        for length in lengths
    ]
    return _science_grid(
        manifest,
        conditions,
        suite="science_dense",
        mask_seeds=mask_seeds,
    )


def build_compensation_grid(
    manifest_path: str | Path = "study_manifest.yaml",
    *,
    mask_seeds: Sequence[int] | None = None,
) -> ExperimentGrid:
    """Build fixed T-gap scenarios used by the 16 information combinations."""

    manifest = _read_yaml(manifest_path)
    stations = tuple(str(value) for value in manifest["data_panels"]["core"]["stations"])
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
    )


def run_dense_experiments(
    *,
    manifest_path: str | Path = "study_manifest.yaml",
    config_path: str | Path = "configs/experiments.yaml",
    wide_path: str | Path = "data/processed/daily_wide.parquet",
    quality_path: str | Path | None = "data/processed/daily_long.parquet",
    output_dir: str | Path = "results/science_experiments/dense",
    mask_dir: str | Path = "masks/science_dense",
    models: Sequence[str] = ("climatology", "linear"),
    training_seeds: Sequence[int] | None = None,
    mask_seeds: Sequence[int] | None = None,
    shard_index: int = 0,
    shard_count: int = 1,
    max_scenarios: int | None = None,
    resume: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the dense grid through the existing unified runner."""

    grid = build_dense_science_grid(manifest_path, mask_seeds=mask_seeds)
    runner = ExperimentRunner(
        grid,
        wide_path=wide_path,
        quality_path=quality_path,
        output_dir=output_dir,
        mask_dir=mask_dir,
        config_path=config_path,
        models=models,
        training_seeds=training_seeds,
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
    """Predict a day-of-year mean fitted only on approved training observations."""

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
    fit = train & approved & np.isfinite(target)
    if not fit.any():
        raise ValueError("S0 requires at least one approved finite training observation")
    day = date_index.dayofyear.to_numpy()
    means = pd.Series(target[fit]).groupby(day[fit]).mean()
    global_mean = float(np.mean(target[fit]))
    return np.asarray([float(means.get(value, global_mean)) for value in day], dtype=float)


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
    if stored_stations != tuple(station_ids) or stored_variables != tuple(variable_names):
        raise ValueError("checkpoint scaler axes do not match the current data")
    mean = np.asarray(scaler.get("mean"), dtype=np.float32)
    scale = np.asarray(scaler.get("scale"), dtype=np.float32)
    expected = (len(station_ids), len(variable_names))
    if mean.shape != expected or scale.shape != expected:
        raise ValueError("checkpoint scaler shape does not match the current data")
    if not np.isfinite(mean).all() or not np.isfinite(scale).all() or np.any(scale <= 0):
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
    device: str | torch.device = "cpu",
) -> dict[str, dict[str, np.ndarray]]:
    """Infer the 15 non-empty A/B/C/D subsets without exposing hidden truth.

    The empty subset is intentionally absent: callers must use the training-only
    day-of-year climatology for S0.
    """

    array = np.asarray(values, dtype=np.float32)
    natural = np.asarray(natural_mask, dtype=bool)
    artificial = np.asarray(artificial_mask, dtype=bool)
    seasonal = np.asarray(seasonal_features, dtype=np.float32)
    if array.ndim != 3 or natural.shape != array.shape or artificial.shape != array.shape:
        raise ValueError("values and masks must align as [time, station, variable]")
    if np.asarray(mean).shape != array.shape[1:] or np.asarray(scale).shape != array.shape[1:]:
        raise ValueError("scaler must match station and variable axes")
    if seasonal.ndim != 2 or seasonal.shape[0] != array.shape[0]:
        raise ValueError("seasonal_features must align with the time axis")

    # Removing hidden values before constructing the tensor makes the no-hidden-
    # truth invariant explicit instead of relying only on the model's internal mask.
    normalized = (array - mean[None]) / scale[None]
    normalized = normalized.copy()
    normalized[artificial] = np.nan
    combinations = [
        combination
        for combination in all_information_group_combinations()
        if combination
    ]
    group_masks = torch.stack([information_group_mask(value) for value in combinations])
    batch_size = len(combinations)
    torch_device = torch.device(device)
    model = model.to(torch_device)
    model.eval()
    tensor_values = torch.from_numpy(normalized).unsqueeze(0).expand(batch_size, -1, -1, -1)
    tensor_natural = torch.from_numpy(natural).unsqueeze(0).expand(batch_size, -1, -1, -1)
    tensor_artificial = torch.from_numpy(artificial).unsqueeze(0).expand(batch_size, -1, -1, -1)
    tensor_seasonal = torch.from_numpy(seasonal).unsqueeze(0).expand(batch_size, -1, -1)
    with torch.no_grad():
        output = model(
            tensor_values.to(torch_device),
            tensor_natural.to(torch_device),
            tensor_artificial.to(torch_device),
            seasonal_features=tensor_seasonal.to(torch_device),
            enabled_groups=group_masks.to(torch_device),
        )
    raw = output["quantiles"].detach().cpu().numpy()
    target_mean = np.asarray(mean, dtype=float)[:, target_index]
    target_scale = np.asarray(scale, dtype=float)[:, target_index]
    raw = raw * target_scale[None, None, :, None] + target_mean[None, None, :, None]
    result: dict[str, dict[str, np.ndarray]] = {}
    for index, combination in enumerate(combinations):
        label = combination_label(combination)
        result[label] = {
            "q05": raw[index, ..., 0],
            "q50": raw[index, ..., 1],
            "q95": raw[index, ..., 2],
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
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_information_compensation(
    *,
    checkpoint_path: str | Path,
    manifest_path: str | Path = "study_manifest.yaml",
    config_path: str | Path = "configs/experiments.yaml",
    wide_path: str | Path = "data/processed/daily_wide.parquet",
    quality_path: str | Path | None = "data/processed/daily_long.parquet",
    output_dir: str | Path = "results/science_experiments/compensation",
    mask_dir: str | Path = "masks/science_compensation",
    training_seed: int = 11,
    mask_seeds: Sequence[int] | None = None,
    max_scenarios: int | None = None,
    device: str = "cpu",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Score S0 plus all 15 proposed-model information subsets on fixed T gaps."""

    grid = build_compensation_grid(manifest_path, mask_seeds=mask_seeds)
    if training_seed not in grid.training_seeds:
        raise ValueError(f"training seed {training_seed} is not in the fixed manifest set")
    selected = grid.scenarios
    if max_scenarios is not None:
        if max_scenarios < 1:
            raise ValueError("max_scenarios must be positive")
        selected = selected[:max_scenarios]
    output_root = Path(output_dir)
    # The runner owns data alignment and mask generation.  Its run method is not
    # called here because one checkpoint is evaluated under 16 source subsets.
    runner = ExperimentRunner(
        grid,
        wide_path=wide_path,
        quality_path=quality_path,
        output_dir=output_root,
        mask_dir=mask_dir,
        config_path=config_path,
        models=("proposed",),
        training_seeds=(training_seed,),
        resume=True,
    )
    checkpoint_file = Path(checkpoint_path)
    skips: list[dict[str, Any]] = []
    try:
        if not checkpoint_file.exists():
            raise FileNotFoundError(f"checkpoint does not exist: {checkpoint_file}")
        model, checkpoint = load_proposed_checkpoint(checkpoint_file, map_location=device)
        mean, scale = _checkpoint_scaler(
            checkpoint, runner.data.station_ids, runner.data.variable_names
        )
        if tuple(model.config.station_ids) != runner.data.station_ids:
            raise ValueError("checkpoint model station axes do not match the current data")
        if tuple(model.config.variable_names) != runner.data.variable_names:
            raise ValueError("checkpoint model variable axes do not match the current data")
    except (EOFError, OSError, KeyError, RuntimeError, TypeError, ValueError) as error:
        skips.append(
            {
                "scenario_id": None,
                "training_seed": training_seed,
                "reason_code": "checkpoint_unavailable_or_incompatible",
                "reason": str(error),
            }
        )
        daily = pd.DataFrame()
        events = pd.DataFrame()
        skipped = pd.DataFrame(skips).reindex(columns=SKIP_COLUMNS)
        _atomic_csv(skipped, output_root / "skipped_runs.csv")
        _atomic_json(
            {
                "status": "skipped",
                "selected_scenarios": len(selected),
                "checkpoint": str(checkpoint_file),
                "reason": str(error),
                "s0_definition": "training-only approved day-of-year mean with training-global fallback",
                "mixed_baseline_limitation": MIXED_BASELINE_LIMITATION,
            },
            output_root / "run_manifest.json",
        )
        return daily, events, skipped

    target_index = runner.data.variable_names.index("T")
    s0_by_station: dict[int, np.ndarray] = {}
    s0_errors: dict[int, str] = {}
    for station in range(len(runner.data.station_ids)):
        try:
            s0_by_station[station] = training_doy_climatology(
                runner.data.dates,
                runner.data.values[:, station, target_index],
                runner.train_rows,
                runner.data.quality_approved[:, station, target_index],
            )
        except ValueError as error:
            s0_errors[station] = str(error)
    daily_parts: list[pd.DataFrame] = []
    event_rows: list[dict[str, Any]] = []
    for scenario in selected:
        station = runner.data.station_ids.index(scenario.condition.station_ids[0])
        if station in s0_errors:
            skips.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "training_seed": training_seed,
                    "reason_code": "s0_training_input_unavailable",
                    "reason": s0_errors[station],
                }
            )
            continue
        try:
            artificial, metadata = runner._generate_mask(scenario)
        except (OSError, KeyError, RuntimeError, TypeError, ValueError) as error:
            skips.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "training_seed": training_seed,
                    "reason_code": "mask_generation_failed",
                    "reason": str(error),
                }
            )
            continue
        truth = runner.data.values[:, station, target_index].astype(float)
        quality = runner.data.quality_approved[:, station, target_index]
        hidden = artificial[:, station, target_index]
        positions = np.flatnonzero(hidden & quality & np.isfinite(truth))
        if positions.size == 0:
            skips.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "training_seed": training_seed,
                    "reason_code": "no_approved_artificial_targets",
                    "reason": "no approved finite T observations were selected by the artificial mask",
                }
            )
            continue
        try:
            proposed = predict_proposed_information_combinations(
                model,
                runner.data.values,
                runner.data.natural_observed,
                artificial,
                runner.data.seasonal_features,
                mean,
                scale,
                target_index=target_index,
                device=device,
            )
        except (RuntimeError, TypeError, ValueError) as error:
            skips.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "training_seed": training_seed,
                    "reason_code": "inference_failed",
                    "reason": str(error),
                }
            )
            continue

        combinations: dict[str, dict[str, np.ndarray] | None] = {"S0": None, **proposed}
        climatology = s0_by_station[station]
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
        for label, quantiles in combinations.items():
            component = "training_doy_climatology" if label == "S0" else "proposed_checkpoint"
            prediction = climatology if quantiles is None else quantiles["q50"][:, station]
            q = (
                None
                if quantiles is None
                else {name: values[:, station] for name, values in quantiles.items()}
            )
            if not np.isfinite(prediction[positions]).all():
                skips.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "training_seed": training_seed,
                        "information_combination": label,
                        "reason_code": "nonfinite_prediction",
                        "reason": "the estimator did not identify every approved artificial target",
                    }
                )
                continue
            row_metadata = {
                **metadata,
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
            )
            event.update(
                {
                    "experiment": scenario.condition.experiment,
                    "information_combination": label,
                    "component_estimator": component,
                    "fit_split": "train",
                    "tuning_split": "validation_checkpoint",
                    "evaluation_split": "test",
                    "window_length": scenario.condition.window_length,
                    "training_protocol": scenario.condition.training_protocol,
                    "external_validation_status": grid.external_validation_status,
                    "validation_scope": scenario.condition.validation_scope,
                    "is_external_validation": False,
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
                        "y_true": truth[positions],
                        "y_pred": prediction[positions],
                        "q05": q["q05"][positions] if q else np.nan,
                        "q25": np.nan,
                        "q50": q["q50"][positions] if q else prediction[positions],
                        "q75": np.nan,
                        "q95": q["q95"][positions] if q else np.nan,
                        "season": seasons,
                        "event_type": None,
                        "quality_approved": quality[positions],
                        "artificial_mask": hidden[positions],
                        "window_length": scenario.condition.window_length,
                        "training_protocol": scenario.condition.training_protocol,
                        "external_validation_status": grid.external_validation_status,
                        "validation_scope": scenario.condition.validation_scope,
                        "is_external_validation": False,
                    }
                )
            )

    daily = pd.concat(daily_parts, ignore_index=True) if daily_parts else pd.DataFrame()
    events = pd.DataFrame(event_rows)
    skipped = pd.DataFrame(skips).reindex(columns=SKIP_COLUMNS)
    if not daily.empty:
        if not daily["quality_approved"].all() or not daily["artificial_mask"].all():
            raise AssertionError("compensation output contains an unapproved or non-artificial score")
        _atomic_parquet(daily, output_root / "daily_predictions.parquet")
    if not events.empty:
        _atomic_parquet(events, output_root / "event_metrics.parquet")
    _atomic_csv(skipped, output_root / "skipped_runs.csv")
    _atomic_json(
        {
            "status": "complete" if not events.empty else "skipped",
            "selected_scenarios": len(selected),
            "completed_event_rows": len(events),
            "daily_rows": len(daily),
            "checkpoint": str(checkpoint_file),
            "training_seed": training_seed,
            "mask_seeds": list(grid.mask_seeds),
            "information_combinations": [
                combination_label(value) for value in all_information_group_combinations()
            ],
            "fit_split": "train",
            "tuning_split": "validation_checkpoint",
            "evaluation_split": "test_once",
            "s0_definition": "training-only approved day-of-year mean with training-global fallback",
            "mixed_baseline_limitation": MIXED_BASELINE_LIMITATION,
            "hidden_truth_input_policy": "artificially hidden values are replaced by NaN before inference",
        },
        output_root / "run_manifest.json",
    )
    return daily, events, skipped


def _read_frame(value: pd.DataFrame | str | Path) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    path = Path(value)
    return pd.read_parquet(path) if path.suffix.lower() == ".parquet" else pd.read_csv(path)


def _quality_series(
    quality_long: pd.DataFrame | None,
    dates: pd.DatetimeIndex,
    station: str,
    variable: str,
) -> np.ndarray:
    if quality_long is None:
        return np.ones(len(dates), dtype=bool)
    selected = quality_long.loc[
        (quality_long["station_id"].astype(str) == station)
        & (quality_long["variable"].astype(str) == variable)
    ].drop_duplicates("date").set_index("date")
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
    """Remove the approved training day-of-year mean without outside data."""

    result = np.full(len(values), np.nan, dtype=float)
    valid = np.asarray(approved, dtype=bool) & np.isfinite(values)
    if not valid.any():
        return result
    day = dates.dayofyear.to_numpy()
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
        raise KeyError(f"daily_wide is missing {sorted(required.difference(wide.columns))}")
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
            *[(target_station, variable, "D") for variable in ("Ta", "P", "W", "RH", "DH")],
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
            source = pd.to_numeric(train[source_column], errors="coerce").to_numpy(float)
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
            if np.unique(x[np.isfinite(x)]).size < 2 or np.unique(y[np.isfinite(y)]).size < 2:
                mi = {
                    "mutual_information": np.nan,
                    "n": int((np.isfinite(x) & np.isfinite(y)).sum()),
                    "n_neighbors": n_neighbors,
                    "reason": "both paired series need at least two distinct values",
                }
            else:
                mi = knn_mutual_information(x, y, n_neighbors=n_neighbors, seed=seed + pair_index)
            rows.append(
                {
                    **common,
                    "metric": "knn_mutual_information",
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
                for lag_index, lag in enumerate(lags):
                    te = transfer_entropy(
                        driver,
                        response,
                        lag=int(lag),
                        n_bins=n_bins,
                        n_permutations=n_permutations,
                        seed=seed + pair_index * 100 + direction_index * 20 + lag_index,
                    )
                    rows.append(
                        {
                            **common,
                            "metric": "transfer_entropy",
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
    return pd.DataFrame(rows)


def write_training_information_metrics(
    daily_wide: pd.DataFrame | str | Path,
    output_path: str | Path = "results/analysis/information_metrics.csv",
    **kwargs: Any,
) -> pd.DataFrame:
    """Compute and atomically write the training-only information table."""

    result = compute_training_information_metrics(daily_wide, **kwargs)
    _atomic_csv(result, Path(output_path))
    return result


__all__ = [
    "COMPENSATION_T_BLOCK_LENGTHS",
    "DENSE_FL_BLOCK_LENGTHS",
    "DENSE_T_BLOCK_LENGTHS",
    "MIXED_BASELINE_LIMITATION",
    "build_compensation_grid",
    "build_dense_science_grid",
    "compute_training_information_metrics",
    "predict_proposed_information_combinations",
    "run_dense_experiments",
    "run_information_compensation",
    "training_doy_climatology",
    "write_training_information_metrics",
]
