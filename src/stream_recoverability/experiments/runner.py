"""Resume-safe unified runner for traditional, deep, and proposed imputers."""

from __future__ import annotations

import json
import pickle
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import yaml

from stream_recoverability.evaluation.event_metrics import compute_event_metrics
from stream_recoverability.masks import (
    generate_async_mask,
    generate_block_mask,
    generate_event_mask,
    generate_multiblock_mask,
    generate_network_outage_mask,
    generate_point_mask,
    generate_station_outage_mask,
)
from stream_recoverability.models.baselines import (
    AirHydroBaseline,
    AirOnlyBaseline,
    ClimatologyBaseline,
    DonorRegressionBaseline,
    IndependentFlowBaseline,
    KalmanSmootherBaseline,
    OfflineLinearInterpolation,
    PCHIPInterpolation,
    RandomForestBaseline,
    RatingCurveBaseline,
    SeasonalRidgeBaseline,
    XGBoostBaseline,
)
from stream_recoverability.models.deep_baselines import BRITSImputer, SAITSImputer
from stream_recoverability.models.proposed import (
    MissingAwareMultisourceImputer,
    ProposedModelConfig,
)
from stream_recoverability.models.proposed_training import (
    ProposedTrainingConfig,
    load_proposed_checkpoint,
    set_deterministic_seed,
    train_proposed_model,
    validate_proposed_checkpoint_contract,
)
from stream_recoverability.models.training import make_windows

from .grid import ExperimentGrid, ExperimentScenario

SUPPORTED_MODELS = (
    "climatology",
    "linear",
    "pchip",
    "kalman",
    "air_only",
    "air_hydro",
    "donor_regression",
    "random_forest",
    "xgboost",
    "rating_curve",
    "independent_flow",
    "brits",
    "saits",
    "proposed",
)
TRAINABLE_MODELS = {"brits", "saits", "proposed"}
STRUCTURAL_SKIP_CODES = {"unsupported_model_target", "required_input_unavailable"}
DAILY_KEY = [
    "scenario_id",
    "model",
    "training_seed",
    "mask_seed",
    "date",
    "station_id",
    "target",
]
EVENT_KEY = [
    "scenario_id",
    "model",
    "training_seed",
    "mask_seed",
    "station_id",
    "target",
]


class _CheckpointRetrainingRequired(RuntimeError):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class _DataBundle:
    dates: pd.DatetimeIndex
    splits: np.ndarray
    station_ids: tuple[str, ...]
    variable_names: tuple[str, ...]
    values: np.ndarray
    natural_observed: np.ndarray
    quality_approved: np.ndarray
    seasonal_features: np.ndarray


@dataclass(frozen=True)
class _TrainingReference:
    q10: float
    q90: float
    iqr: float
    std: float


def apply_full_artificial_mask(
    values: np.ndarray, artificial_mask: np.ndarray
) -> np.ndarray:
    """Hide every selected cell in a complete date × station × variable mask."""

    values = np.asarray(values)
    mask = np.asarray(artificial_mask)
    if mask.dtype != np.bool_ or mask.shape != values.shape or mask.ndim != 3:
        raise ValueError("artificial_mask must be a 3D boolean array matching values")
    masked = values.copy()
    masked[mask] = np.nan
    return masked


def make_training_mask(
    values: np.ndarray,
    seed: int,
    protocol: str,
    *,
    repeats: int = 1,
) -> np.ndarray:
    """Create deterministic, separated mixed-length training episodes."""

    array = np.asarray(values)
    if array.ndim != 2:
        raise ValueError("training values must have shape [time, feature]")
    if protocol not in {"seen_length", "unseen_length"}:
        raise ValueError("protocol must be seen_length or unseen_length")
    if not isinstance(repeats, (int, np.integer)) or int(repeats) < 1:
        raise ValueError("repeats must be a positive integer")
    lengths = (10, 30, 90, 180) if protocol == "seen_length" else (10, 30, 90)
    rng = np.random.default_rng(seed)
    result = np.zeros_like(array, dtype=bool)
    finite = np.isfinite(array)
    episodes = tuple(length for _ in range(int(repeats)) for length in lengths)
    for feature in range(array.shape[1]):
        finite_feature = finite[:, feature]
        span = sum(episodes) + len(episodes) - 1
        span_starts = (
            np.flatnonzero(
                np.lib.stride_tricks.sliding_window_view(finite_feature, span).all(
                    axis=1
                )
            )
            if span <= len(array)
            else np.empty(0, dtype=int)
        )
        if span_starts.size:
            start = int(rng.choice(span_starts))
            ordered_lengths = list(rng.permutation(episodes))
            for length in ordered_lengths:
                result[start : start + int(length), feature] = True
                start += int(length) + 1
            continue

        # Sparse series may not contain one long span. Place the longest
        # episodes first and require an observed one-day separator so distinct
        # requested lengths cannot merge into a longer artificial gap.
        occupied = np.zeros(len(array), dtype=bool)
        for length in sorted(episodes, reverse=True):
            candidates = (
                np.flatnonzero(
                    np.lib.stride_tricks.sliding_window_view(
                        finite_feature, length
                    ).all(axis=1)
                )
                if length <= len(array)
                else np.empty(0, dtype=int)
            )
            separated = np.asarray(
                [
                    start
                    for start in candidates
                    if not occupied[
                        max(0, start - 1) : min(len(array), start + length + 1)
                    ].any()
                ],
                dtype=int,
            )
            if not separated.size:
                raise ValueError(
                    f"feature {feature} cannot support {repeats} separated "
                    f"{protocol} training-mask repeats"
                )
            start = int(rng.choice(separated))
            result[start : start + length, feature] = True
            occupied[start : start + length] = True
    if not result.any():
        raise ValueError("no finite values are available for a training mask")
    return result


def _window_starts(length: int, window: int) -> list[int]:
    window = min(int(window), int(length))
    stride = max(1, window // 2)
    starts = list(range(0, length - window + 1, stride))
    final = length - window
    if not starts or starts[-1] != final:
        starts.append(final)
    return starts


def _read_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        result = yaml.safe_load(handle)
    return result if isinstance(result, dict) else {}


def _atomic_json(value: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.stem + ".tmp.parquet")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _stored_run_key(model: Any, training_seed: Any) -> str:
    if training_seed is None or pd.isna(training_seed):
        return f"{model}:none"
    seed = float(training_seed)
    return f"{model}:{int(seed)}" if seed.is_integer() else f"{model}:{training_seed}"


def _file_identity(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def _quarantine_file(path: Path) -> Path | None:
    if not path.exists():
        return None
    candidate = path.with_name(path.name + ".invalid")
    index = 1
    while candidate.exists():
        candidate = path.with_name(path.name + f".invalid.{index}")
        index += 1
    path.rename(candidate)
    return candidate


def _frame_run_keys(frame: pd.DataFrame) -> set[str]:
    if frame.empty or not {"model", "training_seed"}.issubset(frame.columns):
        return set()
    return {
        _stored_run_key(row.model, row.training_seed)
        for row in frame[["model", "training_seed"]].itertuples(index=False)
    }


def _without_run(frame: pd.DataFrame, run_key: str) -> pd.DataFrame:
    if frame.empty or not {"model", "training_seed"}.issubset(frame.columns):
        return frame
    keep = np.fromiter(
        (
            _stored_run_key(row.model, row.training_seed) != run_key
            for row in frame[["model", "training_seed"]].itertuples(index=False)
        ),
        dtype=bool,
        count=len(frame),
    )
    return frame.loc[keep].reset_index(drop=True)


def _mask_axes(
    dates: pd.DatetimeIndex,
    station_ids: Sequence[str],
    variable_names: Sequence[str],
) -> dict[str, Any]:
    return {
        "order": ["date", "station", "variable"],
        "shape": [len(dates), len(station_ids), len(variable_names)],
        "date": [value.strftime("%Y-%m-%d") for value in dates],
        "station": list(station_ids),
        "variable": list(variable_names),
    }


def _save_compact_mask(
    mask: np.ndarray,
    metadata: Mapping[str, Any],
    root: Path,
    *,
    dates: pd.DatetimeIndex,
    station_ids: Sequence[str],
    variable_names: Sequence[str],
) -> None:
    """Store shared axes once and one packed bit vector per scenario."""

    array = np.asarray(mask)
    axes = _mask_axes(dates, station_ids, variable_names)
    if array.dtype != np.bool_ or list(array.shape) != axes["shape"]:
        raise ValueError("mask must be a boolean array matching the shared axes")
    axes_path = root / "axes.json"
    if axes_path.exists():
        if json.loads(axes_path.read_text(encoding="utf-8")) != axes:
            raise ValueError("stored mask axes do not match the current data")
    else:
        _atomic_json(axes, axes_path)

    scenario_id = str(metadata["scenario_id"])
    scenario_dir = root / "scenarios"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    mask_path = scenario_dir / f"{scenario_id}.npz"
    temporary = scenario_dir / f"{scenario_id}.tmp.npz"
    np.savez_compressed(
        temporary, packed=np.packbits(array.reshape(-1), bitorder="little")
    )
    temporary.replace(mask_path)
    _atomic_json(dict(metadata), scenario_dir / f"{scenario_id}.json")


def _load_compact_mask(
    root: Path, scenario_id: str
) -> tuple[np.ndarray, dict[str, Any]]:
    axes = json.loads((root / "axes.json").read_text(encoding="utf-8"))
    shape = tuple(int(value) for value in axes["shape"])
    with np.load(
        root / "scenarios" / f"{scenario_id}.npz", allow_pickle=False
    ) as archive:
        packed = np.asarray(archive["packed"], dtype=np.uint8)
    size = int(np.prod(shape))
    mask = (
        np.unpackbits(packed, bitorder="little", count=size).reshape(shape).astype(bool)
    )
    metadata = json.loads(
        (root / "scenarios" / f"{scenario_id}.json").read_text(encoding="utf-8")
    )
    if metadata.get("scenario_id") != scenario_id:
        raise ValueError("stored mask metadata has the wrong scenario_id")
    return mask, metadata


def _load_data(
    wide_path: str | Path,
    quality_path: str | Path | None,
    variable_names: Sequence[str],
) -> _DataBundle:
    wide = (
        pd.read_parquet(wide_path)
        if Path(wide_path).suffix.lower() == ".parquet"
        else pd.read_csv(wide_path)
    )
    required = {"date", "split"}
    if not required.issubset(wide):
        raise KeyError(
            f"wide data is missing {sorted(required.difference(wide.columns))}"
        )
    wide = wide.copy()
    wide["date"] = pd.to_datetime(wide["date"]).dt.normalize()
    wide = wide.sort_values("date").reset_index(drop=True)
    if wide["date"].duplicated().any():
        raise ValueError("wide data contains duplicate dates")

    variables = tuple(str(value) for value in variable_names)
    stations = sorted(
        {
            str(column).split("_", 1)[0]
            for column in wide.columns
            if "_" in str(column) and str(column).split("_", 1)[1] in variables
        }
    )
    if not stations:
        raise ValueError("could not infer station columns from wide data")
    missing_columns = [
        f"{station}_{variable}"
        for station in stations
        for variable in variables
        if f"{station}_{variable}" not in wide
    ]
    if missing_columns:
        raise KeyError(f"wide data is missing measurement columns: {missing_columns}")
    values = np.stack(
        [
            np.stack(
                [
                    pd.to_numeric(wide[f"{station}_{variable}"], errors="coerce")
                    for variable in variables
                ],
                axis=-1,
            )
            for station in stations
        ],
        axis=1,
    ).astype(np.float32)

    natural = np.isfinite(values)
    quality = np.isfinite(values)
    if quality_path is not None and Path(quality_path).exists():
        long = (
            pd.read_parquet(quality_path)
            if Path(quality_path).suffix.lower() == ".parquet"
            else pd.read_csv(quality_path)
        )
        required_long = {"date", "station_id", "variable", "quality_approved"}
        if not required_long.issubset(long):
            raise KeyError(
                f"quality data is missing {sorted(required_long.difference(long.columns))}"
            )
        long = long.copy()
        long["date"] = pd.to_datetime(long["date"]).dt.normalize()
        for station_index, station in enumerate(stations):
            for variable_index, variable in enumerate(variables):
                selected = (
                    long.loc[
                        (long["station_id"].astype(str) == station)
                        & (long["variable"].astype(str) == variable)
                    ]
                    .drop_duplicates("date")
                    .set_index("date")
                )
                aligned = selected.reindex(pd.DatetimeIndex(wide["date"]))
                quality[:, station_index, variable_index] = (
                    aligned["quality_approved"].fillna(False).astype(bool).to_numpy()
                )
                natural_column = (
                    "natural_observed"
                    if "natural_observed" in aligned
                    else "quality_approved"
                )
                natural[:, station_index, variable_index] = (
                    aligned[natural_column].fillna(False).astype(bool).to_numpy()
                )
    natural &= np.isfinite(values)
    quality &= np.isfinite(values)

    if {"day_of_year_sin", "day_of_year_cos", "month_sin", "month_cos"}.issubset(wide):
        seasonal = wide[
            ["day_of_year_sin", "day_of_year_cos", "month_sin", "month_cos"]
        ].to_numpy(dtype=np.float32)
    else:
        dates = pd.DatetimeIndex(wide["date"])
        days = np.where(dates.is_leap_year, 366.0, 365.0)
        day_phase = 2 * np.pi * (dates.dayofyear.to_numpy() - 1) / days
        month_phase = 2 * np.pi * (dates.month.to_numpy() - 1) / 12.0
        seasonal = np.column_stack(
            (
                np.sin(day_phase),
                np.cos(day_phase),
                np.sin(month_phase),
                np.cos(month_phase),
            )
        ).astype(np.float32)
    return _DataBundle(
        dates=pd.DatetimeIndex(wide["date"]),
        splits=wide["split"].astype(str).to_numpy(),
        station_ids=tuple(stations),
        variable_names=variables,
        values=values,
        natural_observed=natural,
        quality_approved=quality,
        seasonal_features=seasonal,
    )


class ExperimentRunner:
    """Execute scenario shards and atomically aggregate resume-safe outputs."""

    def __init__(
        self,
        grid: ExperimentGrid,
        *,
        wide_path: str | Path = "data/processed/daily_wide.parquet",
        quality_path: str | Path | None = "data/processed/daily_long.parquet",
        output_dir: str | Path = "results/experiments",
        mask_dir: str | Path = "masks/full",
        config_path: str | Path = "configs/experiments.yaml",
        models: Sequence[str] = ("climatology", "linear"),
        training_seeds: Sequence[int] | None = None,
        resume: bool = True,
    ) -> None:
        self.grid = grid
        self.config = _read_yaml(config_path)
        runner_config = dict(self.config.get("runner", {}))
        self.training_profile_name = "smoke" if grid.suite == "smoke" else "formal"
        profile = dict(runner_config.get(self.training_profile_name, {}))
        self.training_settings = {
            "train_mask_repeats": int(profile["train_mask_repeats"]),
            "validation_mask_repeats": int(profile["validation_mask_repeats"]),
            "deep_epochs": int(profile["deep_epochs"]),
            "deep_patience": int(profile["deep_patience"]),
            "proposed_epochs": int(profile["proposed_epochs"]),
            "proposed_patience": int(profile["proposed_patience"]),
            "batch_size": int(runner_config["batch_size"]),
            "device": str(runner_config["device"]),
        }
        if any(
            int(value) < 1
            for key, value in self.training_settings.items()
            if key != "device"
        ):
            raise ValueError("runner training settings must be positive")
        self.variable_names = tuple(
            self.config.get(
                "all_variables", ("T", "F", "L", "Ta", "P", "W", "RH", "DH")
            )
        )
        self.wide_path = Path(wide_path)
        self.quality_path = Path(quality_path) if quality_path is not None else None
        self.config_path = Path(config_path)
        self.data = _load_data(wide_path, quality_path, self.variable_names)
        self.output_dir = Path(output_dir)
        self.mask_dir = Path(mask_dir)
        self.models = tuple(dict.fromkeys(str(value).lower() for value in models))
        unknown = sorted(set(self.models).difference(SUPPORTED_MODELS))
        if unknown:
            raise ValueError(f"unsupported models: {unknown}")
        requested_seeds = tuple(
            dict.fromkeys(
                grid.training_seeds
                if training_seeds is None
                else map(int, training_seeds)
            )
        )
        invalid_seeds = sorted(set(requested_seeds).difference(grid.training_seeds))
        if invalid_seeds:
            raise ValueError(f"training seeds are not in the manifest: {invalid_seeds}")
        self.training_seeds = requested_seeds
        self.resume = bool(resume)
        self._training_references = self._build_training_references()
        self._deep_cache: dict[tuple[str, int, int, str], Any] = {}
        self._proposed_cache: dict[
            tuple[int, int, str],
            tuple[MissingAwareMultisourceImputer, np.ndarray, np.ndarray],
        ] = {}
        self._proposed_checkpoint_metadata: dict[
            tuple[int, int, str], dict[str, Any]
        ] = {}
        self._climatology_cache: dict[tuple[int, int], tuple[Any, np.ndarray]] = {}
        self._traditional_cache: dict[tuple[str, int, int], Any] = {}
        self._loso_cache: dict[int, tuple[Any, np.ndarray, float]] = {}
        self._proposed_scale_cache: tuple[np.ndarray, np.ndarray] | None = None

    @property
    def train_rows(self) -> np.ndarray:
        return self.data.splits == "train"

    @property
    def validation_rows(self) -> np.ndarray:
        return self.data.splits == "validation"

    @property
    def test_rows(self) -> np.ndarray:
        return self.data.splits == "test"

    def _build_training_references(self) -> dict[tuple[int, int], _TrainingReference]:
        references: dict[tuple[int, int], _TrainingReference] = {}
        for station in range(len(self.data.station_ids)):
            for variable in range(len(self.data.variable_names)):
                eligible = (
                    self.train_rows
                    & self.data.quality_approved[:, station, variable]
                    & np.isfinite(self.data.values[:, station, variable])
                )
                values = self.data.values[eligible, station, variable].astype(float)
                if values.size:
                    q10, q25, q75, q90 = np.quantile(values, (0.10, 0.25, 0.75, 0.90))
                    references[(station, variable)] = _TrainingReference(
                        q10=float(q10),
                        q90=float(q90),
                        iqr=float(q75 - q25),
                        std=float(np.std(values, ddof=0)),
                    )
                else:
                    references[(station, variable)] = _TrainingReference(
                        q10=float("nan"),
                        q90=float("nan"),
                        iqr=float("nan"),
                        std=float("nan"),
                    )
        return references

    def _training_reference(self, station: int, variable: int) -> _TrainingReference:
        return self._training_references[(station, variable)]

    def _indices(self, scenario: ExperimentScenario) -> tuple[list[int], list[int]]:
        stations = [
            self.data.station_ids.index(value)
            for value in scenario.condition.station_ids
        ]
        variables = [
            self.data.variable_names.index(value)
            for value in scenario.condition.variables
        ]
        return stations, variables

    def _event_condition(self, scenario: ExperimentScenario) -> np.ndarray:
        station = self.data.station_ids.index(scenario.condition.station_ids[0])
        event = scenario.condition.event_type
        if event in {"high_temperature", "rapid_warming"}:
            variable = self.data.variable_names.index("T")
        else:
            variable = self.data.variable_names.index("F")
        series = self.data.values[:, station, variable]
        approved_finite = (
            self.data.quality_approved[:, station, variable] & np.isfinite(series)
        )
        train_eligible = self.train_rows & approved_finite
        condition = np.zeros(len(series), dtype=bool)
        if event == "high_temperature":
            train = series[train_eligible]
            if not train.size:
                raise ValueError("event threshold has no approved finite training samples")
            condition = (series >= np.quantile(train, 0.9)) & approved_finite
        elif event == "rapid_warming":
            differences = np.diff(series, prepend=np.nan)
            adjacent_eligible = approved_finite & np.roll(approved_finite, 1)
            adjacent_eligible[0] = False
            adjacent_train = self.train_rows & np.roll(self.train_rows, 1)
            adjacent_train[0] = False
            train_diff = differences[adjacent_train & adjacent_eligible]
            if not train_diff.size:
                raise ValueError(
                    "rapid-warming threshold has no adjacent approved finite "
                    "training samples"
                )
            condition = (
                differences >= np.quantile(train_diff, 0.9)
            ) & adjacent_eligible
        elif event == "flood":
            train = series[train_eligible]
            if not train.size:
                raise ValueError("event threshold has no approved finite training samples")
            condition = (series >= np.quantile(train, 0.9)) & approved_finite
        elif event == "low_flow":
            train = series[train_eligible]
            if not train.size:
                raise ValueError("event threshold has no approved finite training samples")
            condition = (series <= np.quantile(train, 0.1)) & approved_finite
        else:
            raise ValueError(f"unsupported event_type: {event}")
        return condition & self.test_rows

    def _generate_mask(
        self, scenario: ExperimentScenario
    ) -> tuple[np.ndarray, dict[str, Any]]:
        mask_path = self.mask_dir / "scenarios" / f"{scenario.scenario_id}.npz"
        metadata_path = self.mask_dir / "scenarios" / f"{scenario.scenario_id}.json"
        if mask_path.exists() and metadata_path.exists():
            axes_path = self.mask_dir / "axes.json"
            expected_axes = _mask_axes(
                self.data.dates, self.data.station_ids, self.data.variable_names
            )
            if not axes_path.exists() or json.loads(
                axes_path.read_text(encoding="utf-8")
            ) != expected_axes:
                raise ValueError("stored mask axes do not match the current data")
            try:
                mask, metadata = _load_compact_mask(
                    self.mask_dir, scenario.scenario_id
                )
                self._validate_scenario_mask(scenario, mask, metadata)
            except (KeyError, ValueError):
                # Current quality or scenario metadata can legitimately invalidate
                # one cached mask; regenerate only that scenario below.
                pass
            else:
                return mask, metadata
        condition = scenario.condition
        stations, variables = self._indices(scenario)
        eligible = self.data.quality_approved & self.test_rows[:, None, None]
        # Offline interpolators need a right boundary; never hide the final
        # available calendar row where no future endpoint can exist.
        if condition.mask_type != "loso":
            eligible[-1] = False
        common = {
            "eligible": eligible,
            "seed": scenario.mask_seed,
            "station_ids": self.data.station_ids,
            "variable_names": self.data.variable_names,
            "split": "test",
            "scenario_id": scenario.scenario_id,
        }
        if condition.mask_type == "loso":
            mask = np.zeros_like(eligible, dtype=bool)
            station = self.data.station_ids.index(str(condition.held_out_station))
            target = self.data.variable_names.index("T")
            mask[:, station, target] = eligible[:, station, target]
            metadata = {
                "scenario_id": scenario.scenario_id,
                "split": "test",
                "seed": scenario.mask_seed,
                "mask_type": "loso",
                "station_ids": [self.data.station_ids[station]],
                "variables": ["T"],
                "masked_cells": int(mask.sum()),
                "held_out_station": self.data.station_ids[station],
                "validation_scope": condition.validation_scope,
                "is_external_validation": False,
            }
        elif condition.mask_type == "point":
            mask, metadata = generate_point_mask(
                missing_rate=float(condition.missing_rate),
                station_indices=stations,
                variable_indices=variables,
                synchronized=True,
                **common,
            )
        elif condition.mask_type == "block":
            mask, metadata = generate_block_mask(
                length=int(condition.gap_length),
                station_indices=stations,
                variable_indices=variables,
                dates=self.data.dates.to_numpy(),
                **common,
            )
        elif condition.mask_type == "matched_network":
            if condition.experiment != "SCI_NET" or len(stations) != 1:
                raise ValueError(
                    "matched_network is reserved for one-target SCI_NET conditions"
                )
            target_variable = self.data.variable_names.index("T")
            if variables != [target_variable]:
                raise ValueError("matched_network must anchor one target-station T gap")
            failed_station_ids = tuple(
                str(value) for value in condition.failed_station_ids
            )
            unknown_failed = sorted(
                set(failed_station_ids).difference(self.data.station_ids)
            )
            if unknown_failed:
                raise ValueError(f"unknown failed stations: {unknown_failed}")
            if len(set(failed_station_ids)) != len(failed_station_ids):
                raise ValueError("failed_station_ids must not contain duplicates")
            mask, metadata = generate_block_mask(
                length=int(condition.gap_length),
                station_indices=stations,
                variable_indices=variables,
                dates=self.data.dates.to_numpy(),
                **common,
            )
            start = int(metadata["start_indices"][0])
            stop = start + int(condition.gap_length)
            failed_indices = [
                self.data.station_ids.index(value) for value in failed_station_ids
            ]
            hydro_indices = [
                self.data.variable_names.index(value) for value in ("T", "F", "L")
            ]
            if failed_indices:
                selection = np.ix_(
                    np.arange(start, stop, dtype=int),
                    np.asarray(failed_indices, dtype=int),
                    np.asarray(hydro_indices, dtype=int),
                )
                mask[selection] = eligible[selection]
            design_channels = np.zeros(eligible.shape[1:], dtype=bool)
            design_channels[stations[0], target_variable] = True
            for failed_index in failed_indices:
                design_channels[failed_index, hydro_indices] = True
            design_eligible_cells = int(eligible[:, design_channels].sum())
            matrix_eligible_cells = int(eligible.sum())
            metadata.update(
                {
                    "mask_type": "matched_network",
                    "target_station_id": self.data.station_ids[stations[0]],
                    "target_variable": "T",
                    "failed_station_ids": list(failed_station_ids),
                    "failure_count": len(failed_station_ids),
                    "network_size": len(self.data.station_ids),
                    "failure_fraction": len(failed_station_ids)
                    / len(self.data.station_ids),
                    "layout": "matched_target_gap",
                    "outage_mode": "hydro-only",
                    "eligible_cells": design_eligible_cells,
                    "masked_cells": int(mask.sum()),
                    "target_missing_rate": (
                        int(mask.sum()) / design_eligible_cells
                        if design_eligible_cells
                        else 0.0
                    ),
                    "matrix_missing_rate": (
                        int(mask.sum()) / matrix_eligible_cells
                        if matrix_eligible_cells
                        else 0.0
                    ),
                }
            )
        elif condition.mask_type == "multiblock":
            mask, metadata = generate_multiblock_mask(
                total_budget=int(condition.gap_length),
                minimum_gap=30,
                station_indices=stations,
                variable_indices=variables,
                dates=self.data.dates.to_numpy(),
                **common,
            )
        elif condition.mask_type == "station_outage":
            mask, metadata = generate_station_outage_mask(
                station_index=stations[0],
                length=int(condition.gap_length),
                mode=str(condition.outage_mode),
                dates=self.data.dates.to_numpy(),
                **common,
            )
        elif condition.mask_type == "async":
            mask, metadata = generate_async_mask(
                length=int(condition.gap_length),
                overlap_ratio=float(condition.overlap_ratio),
                station_indices=stations,
                variable_indices=variables,
                axis="station",
                dates=self.data.dates.to_numpy(),
                **common,
            )
        elif condition.mask_type == "network_outage":
            mask, metadata = generate_network_outage_mask(
                length=int(condition.gap_length),
                station_indices=stations,
                variable_indices=variables,
                dates=self.data.dates.to_numpy(),
                **common,
            )
        elif condition.mask_type == "event":
            mask, metadata = generate_event_mask(
                event_condition=self._event_condition(scenario),
                event_type=str(condition.event_type),
                missing_rate=float(condition.missing_rate),
                station_indices=stations,
                variable_indices=variables,
                synchronized=True,
                dates=self.data.dates.to_numpy(),
                **common,
            )
        else:
            raise ValueError(f"unsupported mask type: {condition.mask_type}")
        metadata.update(scenario.as_dict())
        is_loso = condition.mask_type == "loso"
        metadata.update(
            {
                "fit_split": "train_other_stations" if is_loso else "train",
                "tuning_split": "validation_other_stations"
                if is_loso
                else "validation",
                "evaluation_split": "test",
                "external_validation_status": self.grid.external_validation_status,
                "is_external_validation": False,
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

    def _validate_scenario_mask(
        self,
        scenario: ExperimentScenario,
        mask: np.ndarray,
        metadata: Mapping[str, Any],
    ) -> None:
        if mask.shape != self.data.values.shape or mask.dtype != np.bool_:
            raise ValueError("scenario mask must be boolean and match the current data")
        if np.any(mask[~self.test_rows]):
            raise ValueError("scenario mask leaked into train/validation dates")
        if np.any(mask & ~self.data.quality_approved):
            raise ValueError("scenario mask includes cells not currently quality-approved")
        if scenario.condition.mask_type != "loso" and mask[-1].any():
            raise ValueError("offline scenario mask cannot hide the final calendar row")
        expected = json.loads(json.dumps(scenario.as_dict()))
        stored = json.loads(json.dumps(dict(metadata)))
        mismatches = {
            key: (stored.get(key), value)
            for key, value in expected.items()
            if stored.get(key) != value
        }
        if mismatches:
            raise ValueError(f"stored mask condition metadata mismatch: {mismatches}")

    def _climatology(self, station: int, variable: int) -> tuple[Any, np.ndarray]:
        key = (station, variable)
        if key not in self._climatology_cache:
            target = self.data.values[:, station, variable].astype(float)
            frame = pd.DataFrame({"date": self.data.dates, "target": target})
            fit_mask = (
                self.train_rows
                & self.data.quality_approved[:, station, variable]
                & np.isfinite(target)
            )
            model = ClimatologyBaseline("target", window=7).fit(
                frame, train_mask=fit_mask
            )
            prediction = model.predict(frame).to_numpy(dtype=float)
            self._climatology_cache[key] = (model, prediction)
        return self._climatology_cache[key]

    def _wide_frame(self, values: np.ndarray) -> pd.DataFrame:
        frame = pd.DataFrame({"date": self.data.dates})
        for station, station_id in enumerate(self.data.station_ids):
            for variable, variable_name in enumerate(self.data.variable_names):
                frame[f"{station_id}_{variable_name}"] = values[:, station, variable]
        return frame

    @staticmethod
    def _supports_target(model_name: str, variable_name: str) -> bool:
        if model_name in {"air_only", "air_hydro"}:
            return variable_name == "T"
        if model_name in {"rating_curve", "independent_flow", "pooled_loso"}:
            return (
                variable_name == "F"
                if model_name != "pooled_loso"
                else variable_name == "T"
            )
        return True

    def _traditional_model(self, model_name: str, station: int, variable: int) -> Any:
        key = (model_name, station, variable)
        if key in self._traditional_cache:
            return self._traditional_cache[key]
        station_id = self.data.station_ids[station]
        variable_name = self.data.variable_names[variable]
        target_col = f"{station_id}_{variable_name}"
        frame = self._wide_frame(self.data.values)
        fit_mask = (
            self.train_rows
            & self.data.quality_approved[:, station, variable]
            & np.isfinite(self.data.values[:, station, variable])
        )
        other_stations = [
            value for value in self.data.station_ids if value != station_id
        ]
        if model_name == "kalman":
            model = KalmanSmootherBaseline(target_col).fit(frame, train_mask=fit_mask)
        elif model_name == "air_only":
            model = AirOnlyBaseline(f"{station_id}_Ta", target_col).fit(
                frame, train_mask=fit_mask
            )
        elif model_name == "air_hydro":
            model = AirHydroBaseline(
                f"{station_id}_Ta",
                (f"{station_id}_F", f"{station_id}_L"),
                target_col,
            ).fit(frame, train_mask=fit_mask)
        elif model_name == "donor_regression":
            model = DonorRegressionBaseline(
                [f"{value}_{variable_name}" for value in other_stations],
                target_col,
                covariate_cols=(f"{station_id}_Ta",),
            ).fit(frame, train_mask=fit_mask)
        elif model_name in {"random_forest", "xgboost"}:
            feature_cols = [
                f"{source_station}_{source_variable}"
                for source_station in self.data.station_ids
                for source_variable in self.data.variable_names
                if f"{source_station}_{source_variable}" != target_col
            ]
            model_class = (
                RandomForestBaseline
                if model_name == "random_forest"
                else XGBoostBaseline
            )
            model = model_class(feature_cols, target_col).fit(
                frame, train_mask=fit_mask
            )
        elif model_name == "rating_curve":
            model = RatingCurveBaseline(f"{station_id}_L", target_col).fit(
                frame, train_mask=fit_mask
            )
        elif model_name == "independent_flow":
            feature_cols = [
                *[f"{value}_F" for value in other_stations],
                f"{station_id}_Ta",
                f"{station_id}_P",
                f"{station_id}_W",
                f"{station_id}_RH",
                f"{station_id}_DH",
            ]
            model = IndependentFlowBaseline(
                feature_cols,
                f"{station_id}_L",
                target_col,
            ).fit(frame, train_mask=fit_mask)
        else:
            raise AssertionError(model_name)
        self._traditional_cache[key] = model
        return model

    def _pooled_loso_prediction(
        self, held_out_station: int
    ) -> tuple[Any, np.ndarray, float]:
        """Fit/tune a pooled seasonal Ta/F/L model without held-out T labels."""

        if held_out_station in self._loso_cache:
            return self._loso_cache[held_out_station]
        target_index = self.data.variable_names.index("T")
        feature_indices = {
            name: self.data.variable_names.index(name) for name in ("Ta", "F", "L")
        }
        donor_stations = [
            index
            for index in range(len(self.data.station_ids))
            if index != held_out_station
        ]

        def pooled_frame(rows: np.ndarray) -> pd.DataFrame:
            positions = np.flatnonzero(rows)
            frames = []
            for station in donor_stations:
                target = self.data.values[positions, station, target_index].astype(
                    float
                )
                approved = self.data.quality_approved[positions, station, target_index]
                frames.append(
                    pd.DataFrame(
                        {
                            "date": self.data.dates[positions],
                            "target": np.where(approved, target, np.nan),
                            **{
                                name: self.data.values[positions, station, index]
                                for name, index in feature_indices.items()
                            },
                        }
                    )
                )
            return pd.concat(frames, ignore_index=True)

        train = pooled_frame(self.train_rows)
        validation = pooled_frame(self.validation_rows)
        best_alpha = 1.0
        best_score = float("inf")
        for alpha in (0.1, 1.0, 10.0):
            candidate = SeasonalRidgeBaseline(
                ("Ta", "F", "L"), "target", alpha=alpha
            ).fit(train)
            prediction = candidate.predict(validation).to_numpy(dtype=float)
            truth = validation["target"].to_numpy(dtype=float)
            valid = np.isfinite(truth) & np.isfinite(prediction)
            score = (
                float(np.sqrt(np.mean((truth[valid] - prediction[valid]) ** 2)))
                if valid.any()
                else float("inf")
            )
            if score < best_score:
                best_alpha, best_score = alpha, score
        model = SeasonalRidgeBaseline(("Ta", "F", "L"), "target", alpha=best_alpha).fit(
            train
        )
        held_out = pd.DataFrame(
            {
                "date": self.data.dates,
                **{
                    name: self.data.values[:, held_out_station, index]
                    for name, index in feature_indices.items()
                },
            }
        )
        prediction = model.predict(held_out).to_numpy(dtype=float)
        self._loso_cache[held_out_station] = (model, prediction, best_alpha)
        return self._loso_cache[held_out_station]

    def _traditional_prediction(
        self, model_name: str, station: int, variable: int, artificial_mask: np.ndarray
    ) -> np.ndarray:
        masked_values = apply_full_artificial_mask(self.data.values, artificial_mask)
        masked_frame = self._wide_frame(masked_values)
        target_col = (
            f"{self.data.station_ids[station]}_{self.data.variable_names[variable]}"
        )
        masked = masked_frame[target_col]
        if model_name == "pooled_loso":
            return self._pooled_loso_prediction(station)[1].copy()
        if model_name == "climatology":
            return self._climatology(station, variable)[1].copy()
        if model_name == "linear":
            return (
                OfflineLinearInterpolation()
                .predict(masked, dates=self.data.dates)
                .to_numpy(dtype=float)
            )
        if model_name == "pchip":
            return (
                PCHIPInterpolation()
                .predict(masked, dates=self.data.dates)
                .to_numpy(dtype=float)
            )
        if model_name == "kalman":
            return (
                self._traditional_model(model_name, station, variable)
                .predict(masked_frame, target=target_col)
                .to_numpy(dtype=float)
            )
        model = self._traditional_model(model_name, station, variable)
        if model_name == "rating_curve":
            return model.predict(masked_frame).to_numpy(dtype=float)
        return model.predict(masked_frame, dates=self.data.dates).to_numpy(dtype=float)

    def _deep_contract(
        self, name: str, seed: int, window: int, protocol: str
    ) -> tuple[type[BRITSImputer | SAITSImputer], dict[str, Any], dict[str, Any]]:
        model_class = BRITSImputer if name == "brits" else SAITSImputer
        expected_features = int(self.data.values.shape[1] * self.data.values.shape[2])
        expected_model_config = (
            {
                "n_features": expected_features,
                "seed": int(seed),
                "hidden_size": 32,
                "consistency_weight": 0.1,
            }
            if name == "brits"
            else {
                "n_features": expected_features,
                "seed": int(seed),
                "d_model": 32,
                "n_heads": 4,
                "n_layers": 1,
                "d_ff": 64,
                "dropout": 0.0,
            }
        )
        expected_training_config = {
            "epochs": self.training_settings["deep_epochs"],
            "batch_size": self.training_settings["batch_size"],
            "learning_rate": 1e-3,
            "weight_decay": 0.0,
            "patience": self.training_settings["deep_patience"],
            "min_delta": 0.0,
            "seed": int(seed),
            "profile": self.training_profile_name,
            "train_mask_repeats": self.training_settings["train_mask_repeats"],
            "validation_mask_repeats": self.training_settings[
                "validation_mask_repeats"
            ],
            "window": int(window),
            "protocol": protocol,
            "input_files": self._training_input_identities(),
        }
        return model_class, expected_model_config, expected_training_config

    def _training_input_identities(self) -> dict[str, Any]:
        return {
            "wide": _file_identity(self.wide_path),
            "quality": _file_identity(self.quality_path),
        }

    def _deep_model(self, name: str, seed: int, window: int, protocol: str) -> Any:
        key = (name, seed, window, protocol)
        if key in self._deep_cache:
            return self._deep_cache[key]
        checkpoint = (
            self.output_dir / "checkpoints" / f"{name}-S{seed}-W{window}-{protocol}.pt"
        )
        model_class, expected_model_config, expected_training_config = (
            self._deep_contract(name, seed, window, protocol)
        )
        if checkpoint.exists() and self.resume:
            try:
                model = model_class.load_checkpoint(
                    checkpoint,
                    expected_config=expected_model_config,
                    expected_training_config=expected_training_config,
                )
            except (
                EOFError,
                OSError,
                KeyError,
                RuntimeError,
                TypeError,
                ValueError,
                pickle.UnpicklingError,
            ):
                _quarantine_file(checkpoint)
                model = None
            if model is not None:
                self._deep_cache[key] = model
                return model
        flattened = self.data.values.reshape(len(self.data.values), -1)
        train_values = flattened[self.train_rows]
        validation_values = flattened[self.validation_rows]
        train_mask = make_training_mask(
            train_values,
            seed,
            protocol,
            repeats=self.training_settings["train_mask_repeats"],
        )
        validation_mask = make_training_mask(
            validation_values,
            seed + 10_000,
            protocol,
            repeats=self.training_settings["validation_mask_repeats"],
        )
        train_windows, train_masks = make_windows(
            train_values, train_mask, window, stride=window // 2
        )
        validation_windows, validation_masks = make_windows(
            validation_values,
            validation_mask,
            min(window, len(validation_values)),
            stride=max(1, window // 2),
        )
        if name == "brits":
            model = BRITSImputer(flattened.shape[1], hidden_size=32, seed=seed)
        else:
            model = SAITSImputer(
                flattened.shape[1], d_model=32, n_heads=4, d_ff=64, seed=seed
            )
        model.fit(
            train_windows,
            train_masks,
            validation_values=validation_windows,
            validation_mask=validation_masks,
            epochs=self.training_settings["deep_epochs"],
            batch_size=self.training_settings["batch_size"],
            patience=self.training_settings["deep_patience"],
        )
        model.training_config_.update(expected_training_config)
        model.save_checkpoint(checkpoint)
        self._deep_cache[key] = model
        return model

    def _proposed_batches(
        self,
        model_values: np.ndarray,
        rows: np.ndarray,
        artificial_flat: np.ndarray,
        window: int,
    ) -> list[dict[str, torch.Tensor]]:
        values = model_values[rows]
        natural = self.data.natural_observed[rows]
        quality = self.data.quality_approved[rows]
        artificial = artificial_flat.reshape(values.shape)
        seasonal = self.data.seasonal_features[rows]
        starts = list(range(0, len(values) - window + 1, window))
        final = len(values) - window
        if final >= 0 and (not starts or starts[-1] != final):
            starts.append(final)
        return [
            {
                "values": torch.from_numpy(values[start : start + window]).unsqueeze(0),
                "natural_mask": torch.from_numpy(
                    natural[start : start + window]
                ).unsqueeze(0),
                "artificial_mask": torch.from_numpy(
                    artificial[start : start + window]
                ).unsqueeze(0),
                "target": torch.from_numpy(
                    values[
                        start : start + window,
                        :,
                        self.data.variable_names.index("T"),
                    ]
                ).unsqueeze(0),
                "quality_mask": torch.from_numpy(
                    quality[
                        start : start + window,
                        :,
                        self.data.variable_names.index("T"),
                    ]
                ).unsqueeze(0),
                "seasonal_features": torch.from_numpy(
                    seasonal[start : start + window]
                ).unsqueeze(0),
            }
            for start in starts
            if artificial[
                start : start + window,
                :,
                self.data.variable_names.index("T"),
            ].any()
        ]

    def _proposed_scaler(self) -> tuple[np.ndarray, np.ndarray]:
        if self._proposed_scale_cache is not None:
            return self._proposed_scale_cache
        train_values = self.data.values[self.train_rows]
        train_quality = self.data.quality_approved[self.train_rows]
        mean = np.empty(train_values.shape[1:], dtype=np.float32)
        scale = np.empty_like(mean)
        for station in range(train_values.shape[1]):
            for variable in range(train_values.shape[2]):
                values = train_values[:, station, variable]
                selected = values[
                    train_quality[:, station, variable] & np.isfinite(values)
                ]
                if selected.size == 0:
                    raise ValueError(
                        f"no approved training values for {self.data.station_ids[station]}_"
                        f"{self.data.variable_names[variable]}"
                    )
                mean[station, variable] = float(selected.mean())
                standard_deviation = float(selected.std())
                scale[station, variable] = (
                    standard_deviation if standard_deviation >= 1e-6 else 1.0
                )
        self._proposed_scale_cache = (mean, scale)
        return self._proposed_scale_cache

    def _proposed_contract(
        self, seed: int, window: int, protocol: str
    ) -> tuple[ProposedModelConfig, ProposedTrainingConfig, dict[str, Any]]:
        return (
            ProposedModelConfig(
                station_ids=self.data.station_ids,
                variable_names=self.data.variable_names,
                hidden_size=24,
                dropout=0.0,
            ),
            ProposedTrainingConfig(
                epochs=self.training_settings["proposed_epochs"],
                patience=self.training_settings["proposed_patience"],
                seed=seed,
                device=self.training_settings["device"],
            ),
            {
                "profile": self.training_profile_name,
                "train_mask_repeats": self.training_settings["train_mask_repeats"],
                "validation_mask_repeats": self.training_settings[
                    "validation_mask_repeats"
                ],
                "window": int(window),
                "protocol": protocol,
                "input_files": self._training_input_identities(),
            },
        )

    def _load_proposed_model_checkpoint(
        self, checkpoint: Path, seed: int, window: int, protocol: str
    ) -> tuple[
        MissingAwareMultisourceImputer,
        dict[str, Any],
        np.ndarray,
        np.ndarray,
    ]:
        expected_model_config, expected_training_config, expected_context = (
            self._proposed_contract(seed, window, protocol)
        )
        try:
            model, checkpoint_metadata = load_proposed_checkpoint(checkpoint)
        except (
            EOFError,
            OSError,
            KeyError,
            RuntimeError,
            TypeError,
            ValueError,
            pickle.UnpicklingError,
        ) as error:
            raise _CheckpointRetrainingRequired(
                f"proposed checkpoint {checkpoint} is incompatible with the current "
                "five-quantile architecture; retrain it",
                reason_code="checkpoint_incompatible_model",
            ) from error
        if tuple(model.config.station_ids) != self.data.station_ids or tuple(
            model.config.variable_names
        ) != self.data.variable_names:
            raise _CheckpointRetrainingRequired(
                f"proposed checkpoint {checkpoint} axes do not match the current data; "
                "retrain it",
                reason_code="checkpoint_incompatible_axes",
            )
        try:
            stored_quantile_levels = tuple(
                float(value)
                for value in checkpoint_metadata.get("quantile_levels", ())
            )
        except (TypeError, ValueError):
            stored_quantile_levels = ()
        if stored_quantile_levels != model.quantile_levels:
            raise _CheckpointRetrainingRequired(
                f"proposed checkpoint {checkpoint} does not declare the required "
                f"quantile levels {model.quantile_levels}; retrain it",
                reason_code="checkpoint_incompatible_quantiles",
            )
        stored_scaler = checkpoint_metadata.get("train_scaler")
        if not isinstance(stored_scaler, Mapping):
            raise _CheckpointRetrainingRequired(
                f"proposed checkpoint {checkpoint} has no training-only scaler; retrain it",
                reason_code="checkpoint_missing_training_scaler",
            )
        stored_stations = tuple(
            str(value) for value in stored_scaler.get("station_ids", ())
        )
        stored_variables = tuple(
            str(value) for value in stored_scaler.get("variable_names", ())
        )
        try:
            mean = np.asarray(stored_scaler["mean"], dtype=np.float32)
            scale = np.asarray(stored_scaler["scale"], dtype=np.float32)
        except (KeyError, TypeError, ValueError) as error:
            raise _CheckpointRetrainingRequired(
                f"proposed checkpoint {checkpoint} has an invalid training scaler; "
                "retrain it",
                reason_code="checkpoint_incompatible_training_scaler",
            ) from error
        if (
            stored_stations != self.data.station_ids
            or stored_variables != self.data.variable_names
            or mean.shape != self.data.values.shape[1:]
            or scale.shape != mean.shape
            or not np.isfinite(mean).all()
            or not np.isfinite(scale).all()
            or np.any(scale <= 0)
        ):
            raise _CheckpointRetrainingRequired(
                f"proposed checkpoint {checkpoint} scaler does not match the current "
                "data axes; retrain it",
                reason_code="checkpoint_incompatible_training_scaler",
            )
        try:
            validate_proposed_checkpoint_contract(
                checkpoint_metadata,
                expected_model_config=expected_model_config,
                expected_training_config=expected_training_config,
                expected_training_context=expected_context,
            )
        except (TypeError, ValueError) as error:
            raise _CheckpointRetrainingRequired(
                f"proposed checkpoint {checkpoint} has an incompatible model, "
                f"training, or completion contract: {error}; retrain it",
                reason_code="checkpoint_incompatible_training_config",
            ) from error
        return model, checkpoint_metadata, mean, scale

    def _proposed_model(
        self, seed: int, window: int, protocol: str
    ) -> tuple[MissingAwareMultisourceImputer, np.ndarray, np.ndarray]:
        key = (seed, window, protocol)
        if key in self._proposed_cache:
            return self._proposed_cache[key]
        checkpoint = (
            self.output_dir
            / "checkpoints"
            / f"proposed-S{seed}-W{window}-{protocol}.pt"
        )
        expected_model_config, expected_training_config, expected_context = (
            self._proposed_contract(seed, window, protocol)
        )
        if checkpoint.exists() and self.resume:
            model, checkpoint_metadata, mean, scale = (
                self._load_proposed_model_checkpoint(
                    checkpoint, seed, window, protocol
                )
            )
            self._proposed_checkpoint_metadata[key] = checkpoint_metadata
            self._proposed_cache[key] = (model, mean, scale)
            return self._proposed_cache[key]
        mean, scale = self._proposed_scaler()
        normalized_values = (self.data.values - mean[None]) / scale[None]
        train_values = self.data.values[self.train_rows].reshape(
            int(self.train_rows.sum()), -1
        )
        validation_values = self.data.values[self.validation_rows].reshape(
            int(self.validation_rows.sum()), -1
        )
        train_mask = make_training_mask(
            train_values,
            seed,
            protocol,
            repeats=self.training_settings["train_mask_repeats"],
        )
        validation_mask = make_training_mask(
            validation_values,
            seed + 10_000,
            protocol,
            repeats=self.training_settings["validation_mask_repeats"],
        )
        train_window = min(window, len(train_values))
        validation_window = min(window, len(validation_values))
        train_batches = self._proposed_batches(
            normalized_values, self.train_rows, train_mask, train_window
        )
        validation_batches = self._proposed_batches(
            normalized_values, self.validation_rows, validation_mask, validation_window
        )
        set_deterministic_seed(seed)
        model = MissingAwareMultisourceImputer(expected_model_config)
        training_config = expected_training_config
        train_proposed_model(
            model,
            train_batches,
            validation_batches,
            training_config,
            checkpoint_path=checkpoint,
        )
        checkpoint_metadata = torch.load(
            checkpoint, map_location="cpu", weights_only=False
        )
        checkpoint_metadata["quantile_levels"] = list(model.quantile_levels)
        checkpoint_metadata.setdefault("training_config", asdict(training_config))
        checkpoint_metadata["train_scaler"] = {
            "mean": mean.tolist(),
            "scale": scale.tolist(),
            "station_ids": list(self.data.station_ids),
            "variable_names": list(self.data.variable_names),
        }
        checkpoint_metadata["training_context"] = expected_context
        validate_proposed_checkpoint_contract(
            checkpoint_metadata,
            expected_model_config=expected_model_config,
            expected_training_config=expected_training_config,
            expected_training_context=expected_context,
        )
        torch.save(checkpoint_metadata, checkpoint)
        self._proposed_checkpoint_metadata[key] = checkpoint_metadata
        self._proposed_cache[key] = (model, mean, scale)
        return self._proposed_cache[key]

    def _model_prediction(
        self,
        model_name: str,
        training_seed: int | None,
        scenario: ExperimentScenario,
        artificial_mask: np.ndarray,
    ) -> tuple[np.ndarray | None, dict[str, np.ndarray] | None]:
        if model_name not in TRAINABLE_MODELS:
            return None, None
        seed = int(training_seed)
        condition = scenario.condition
        masked_values = apply_full_artificial_mask(self.data.values, artificial_mask)
        if model_name in {"brits", "saits"}:
            model = self._deep_model(
                model_name, seed, condition.window_length, condition.training_protocol
            )
            flat = self.data.values.reshape(len(self.data.values), -1)
            flat_mask = artificial_mask.reshape(len(artificial_mask), -1)
            prediction_sum = np.zeros_like(flat, dtype=float)
            prediction_count = np.zeros_like(flat, dtype=np.int16)
            window = min(condition.window_length, len(flat))
            for start in _window_starts(len(flat), window):
                end = start + window
                window_mask = flat_mask[start:end]
                if not window_mask.any():
                    continue
                window_prediction = model.predict(flat[start:end], window_mask)
                prediction_sum[start:end] += np.where(
                    window_mask, window_prediction, 0.0
                )
                prediction_count[start:end] += window_mask
            if np.any(flat_mask & (prediction_count == 0)):
                raise RuntimeError(
                    "windowed deep prediction did not cover every hidden cell"
                )
            predicted = np.full_like(flat, np.nan, dtype=float)
            predicted[flat_mask] = (
                prediction_sum[flat_mask] / prediction_count[flat_mask]
            )
            predicted = predicted.reshape(self.data.values.shape)
            return predicted, None
        model, mean, scale = self._proposed_model(
            seed, condition.window_length, condition.training_protocol
        )
        model.eval()
        normalized_values = ((self.data.values - mean[None]) / scale[None]).copy()
        normalized_values[artificial_mask] = np.nan
        prediction = np.full_like(masked_values, np.nan, dtype=float)
        target_index = self.data.variable_names.index("T")
        target_hidden = artificial_mask[..., target_index]
        quantile_sum = np.zeros((*target_hidden.shape, 5), dtype=float)
        prediction_count = np.zeros_like(target_hidden, dtype=np.int16)
        window = min(condition.window_length, len(self.data.values))
        for start in _window_starts(len(self.data.values), window):
            end = start + window
            window_hidden = target_hidden[start:end]
            if not window_hidden.any():
                continue
            values = torch.from_numpy(normalized_values[None, start:end])
            natural = torch.from_numpy(self.data.natural_observed[None, start:end])
            artificial = torch.from_numpy(artificial_mask[None, start:end])
            seasonal = torch.from_numpy(self.data.seasonal_features[None, start:end])
            with torch.no_grad():
                output = model(values, natural, artificial, seasonal_features=seasonal)
            window_quantiles = output["quantiles"][0].detach().cpu().numpy()
            window_quantiles = (
                window_quantiles * scale[:, target_index][None, :, None]
                + mean[:, target_index][None, :, None]
            )
            quantile_sum[start:end] += np.where(
                window_hidden[..., None], window_quantiles, 0.0
            )
            prediction_count[start:end] += window_hidden
        if np.any(target_hidden & (prediction_count == 0)):
            raise RuntimeError(
                "windowed proposed prediction did not cover every hidden T cell"
            )
        quantiles = np.full((*target_hidden.shape, 5), np.nan, dtype=float)
        quantiles[target_hidden] = (
            quantile_sum[target_hidden] / prediction_count[target_hidden, None]
        )
        prediction[..., target_index][target_hidden] = quantiles[target_hidden, 2]
        return prediction, {
            "q05": quantiles[..., 0],
            "q25": quantiles[..., 1],
            "q50": quantiles[..., 2],
            "q75": quantiles[..., 3],
            "q95": quantiles[..., 4],
        }

    def _prediction_rows(
        self,
        scenario: ExperimentScenario,
        metadata: Mapping[str, Any],
        artificial_mask: np.ndarray,
        model_name: str,
        training_seed: int | None,
    ) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
        evaluation_variables = (
            scenario.condition.evaluation_variables or scenario.condition.variables
        )
        station_indices = [
            self.data.station_ids.index(value)
            for value in scenario.condition.station_ids
        ]
        shared_prediction, quantiles = self._model_prediction(
            model_name, training_seed, scenario, artificial_mask
        )
        daily_parts: list[pd.DataFrame] = []
        event_rows: list[dict[str, Any]] = []
        skipped_rows: list[dict[str, Any]] = []
        is_loso = scenario.condition.mask_type == "loso"
        fit_split = "train_other_stations" if is_loso else "train"
        tuning_split = "validation_other_stations" if is_loso else "validation"
        if (
            scenario.condition.experiment == "SCI_NET"
            or scenario.condition.failed_station_ids
        ):
            failed_stations = list(scenario.condition.failed_station_ids)
        elif (
            scenario.condition.experiment in {"M4", "M6"}
            or scenario.condition.mask_type == "async"
        ):
            failed_stations = list(scenario.condition.station_ids)
        else:
            failed_stations = []
        failed_stations_json = json.dumps(failed_stations, separators=(",", ":"))
        network_size = len(self.data.station_ids)

        def first_metadata_value(name: str) -> Any:
            value = metadata.get(name)
            if isinstance(value, (list, tuple, np.ndarray)):
                return value[0] if len(value) else None
            return value

        gap_start_index = first_metadata_value("start_indices")
        gap_end_index = first_metadata_value("end_indices")
        gap_start_date = first_metadata_value("start_dates")
        gap_end_date = first_metadata_value("end_dates")
        condition_stations_json = json.dumps(
            list(scenario.condition.station_ids), separators=(",", ":")
        )
        condition_variables_json = json.dumps(
            list(scenario.condition.variables), separators=(",", ":")
        )
        evaluation_variables_json = json.dumps(
            list(evaluation_variables), separators=(",", ":")
        )
        for station in station_indices:
            for variable_name in evaluation_variables:
                variable = self.data.variable_names.index(variable_name)
                hidden = artificial_mask[:, station, variable]
                if not hidden.any():
                    continue
                if (
                    model_name == "proposed" and variable_name != "T"
                ) or not self._supports_target(model_name, variable_name):
                    skipped_rows.append(
                        {
                            "run_key": (
                                f"{model_name}:none"
                                if training_seed is None
                                else f"{model_name}:{training_seed}"
                            ),
                            "model": model_name,
                            "training_seed": training_seed,
                            "station_id": self.data.station_ids[station],
                            "target": variable_name,
                            "reason_code": "unsupported_model_target",
                            "reason": f"{model_name} does not estimate target {variable_name}",
                        }
                    )
                    continue
                truth = self.data.values[:, station, variable]
                quality = self.data.quality_approved[:, station, variable]
                positions = np.flatnonzero(hidden & quality & np.isfinite(truth))
                if not positions.size:
                    skipped_rows.append(
                        {
                            "run_key": (
                                f"{model_name}:none"
                                if training_seed is None
                                else f"{model_name}:{training_seed}"
                            ),
                            "model": model_name,
                            "training_seed": training_seed,
                            "station_id": self.data.station_ids[station],
                            "target": variable_name,
                            "reason_code": "no_approved_masked_targets",
                            "reason": "no finite quality-approved artificial targets are available",
                        }
                    )
                    continue
                if model_name == "rating_curve":
                    level = self.data.variable_names.index("L")
                    unavailable = artificial_mask[
                        positions, station, level
                    ] | ~np.isfinite(self.data.values[positions, station, level])
                    if unavailable.any():
                        skipped_rows.append(
                            {
                                "run_key": (
                                    f"{model_name}:none"
                                    if training_seed is None
                                    else f"{model_name}:{training_seed}"
                                ),
                                "model": model_name,
                                "training_seed": training_seed,
                                "station_id": self.data.station_ids[station],
                                "target": variable_name,
                                "reason_code": "required_input_unavailable",
                                "reason": (
                                    "rating_curve requires unmasked finite same-station L "
                                    "at every evaluated F cell"
                                ),
                                "required_inputs": [
                                    f"{self.data.station_ids[station]}_L"
                                ],
                                "unavailable_cells": int(unavailable.sum()),
                            }
                        )
                        continue
                if shared_prediction is None:
                    prediction = self._traditional_prediction(
                        model_name, station, variable, artificial_mask
                    )
                    q = None
                else:
                    prediction = shared_prediction[:, station, variable]
                    q = (
                        {name: values[:, station] for name, values in quantiles.items()}
                        if quantiles is not None
                        else None
                    )
                if not np.isfinite(prediction[positions]).all():
                    skipped_rows.append(
                        {
                            "run_key": (
                                f"{model_name}:none"
                                if training_seed is None
                                else f"{model_name}:{training_seed}"
                            ),
                            "model": model_name,
                            "training_seed": training_seed,
                            "station_id": self.data.station_ids[station],
                            "target": variable_name,
                            "reason_code": "nonfinite_prediction",
                            "reason": "model did not identify every evaluated artificial target",
                            "nonfinite_prediction_cells": int(
                                (~np.isfinite(prediction[positions])).sum()
                            ),
                        }
                    )
                    continue
                climatology = self._climatology(station, variable)[1]
                reference = self._training_reference(station, variable)
                target_station_id = self.data.station_ids[station]
                target_gap_id = (
                    f"SCI-NET-{target_station_id}-{variable_name}-"
                    f"D{int(scenario.condition.gap_length):03d}-R{scenario.mask_seed:04d}"
                    if scenario.condition.experiment == "SCI_NET"
                    else None
                )
                design_fields = {
                    "condition_id": scenario.condition.condition_id,
                    "mask_type": scenario.condition.mask_type,
                    "station_ids": condition_stations_json,
                    "variables": condition_variables_json,
                    "evaluation_variables": evaluation_variables_json,
                    "missing_rate": scenario.condition.missing_rate,
                    "gap_length": scenario.condition.gap_length,
                    "layout": scenario.condition.layout,
                    "outage_mode": scenario.condition.outage_mode,
                    "overlap_ratio": scenario.condition.overlap_ratio,
                    "event_type": scenario.condition.event_type,
                    "window_length": scenario.condition.window_length,
                    "training_protocol": scenario.condition.training_protocol,
                    "held_out_station": scenario.condition.held_out_station,
                    "validation_scope": scenario.condition.validation_scope,
                    "target_station_id": target_station_id,
                    "failed_station_ids": failed_stations_json,
                    "failed_stations": failed_stations_json,
                    "failure_count": len(failed_stations),
                    "network_size": network_size,
                    "failure_fraction": len(failed_stations) / network_size,
                    "target_gap_id": target_gap_id,
                    "target_gap_start_index": gap_start_index,
                    "target_gap_end_index": gap_end_index,
                    "target_gap_start_date": gap_start_date,
                    "target_gap_end_date": gap_end_date,
                }
                reference_fields = {
                    "high_threshold": reference.q90,
                    "low_threshold": reference.q10,
                    "normalization_iqr": reference.iqr,
                    "normalization_std": reference.std,
                    "threshold_reference_split": "train",
                    "normalization_reference_split": "train",
                }
                row_metadata = {
                    **metadata,
                    "station_id": self.data.station_ids[station],
                    "model": model_name,
                    "training_seed": training_seed,
                    "mask_seed": scenario.mask_seed,
                    "target": variable_name,
                    "gap_length": scenario.condition.gap_length,
                    "pattern": "+".join(scenario.condition.variables),
                }
                event_row = compute_event_metrics(
                    truth,
                    prediction,
                    quality,
                    hidden,
                    target=variable_name,
                    metadata=row_metadata,
                    climatology_pred=climatology,
                    dates=self.data.dates,
                    quantile_predictions=q,
                    high_threshold=reference.q90,
                    low_threshold=reference.q10,
                    ecological_threshold=None,
                    normalization_iqr=reference.iqr,
                    normalization_std=reference.std,
                )
                event_row.update(
                    {
                        "experiment": scenario.condition.experiment,
                        "fit_split": fit_split,
                        "tuning_split": tuning_split,
                        "evaluation_split": "test",
                        "external_validation_status": self.grid.external_validation_status,
                        "is_external_validation": False,
                        **design_fields,
                        **reference_fields,
                    }
                )
                if model_name == "pooled_loso":
                    event_row["selected_alpha"] = self._pooled_loso_prediction(station)[
                        2
                    ]
                if not np.isfinite(event_row["MAE"]) or not np.isfinite(
                    event_row["RMSE"]
                ):
                    skipped_rows.append(
                        {
                            "run_key": (
                                f"{model_name}:none"
                                if training_seed is None
                                else f"{model_name}:{training_seed}"
                            ),
                            "model": model_name,
                            "training_seed": training_seed,
                            "station_id": self.data.station_ids[station],
                            "target": variable_name,
                            "reason_code": "nonfinite_event_metrics",
                            "reason": "finite MAE and RMSE could not be computed",
                        }
                    )
                    continue
                event_rows.append(event_row)
                months = self.data.dates[positions].month.to_numpy()
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
                        "date": self.data.dates[positions],
                        "station_id": self.data.station_ids[station],
                        "target": variable_name,
                        "scenario_id": scenario.scenario_id,
                        "experiment": scenario.condition.experiment,
                        "mask_type": scenario.condition.mask_type,
                        "gap_length": scenario.condition.gap_length,
                        "missing_rate": scenario.condition.missing_rate,
                        "variable_pattern": "+".join(scenario.condition.variables),
                        "model": model_name,
                        "training_seed": training_seed,
                        "mask_seed": scenario.mask_seed,
                        "y_true": truth[positions],
                        "y_pred": prediction[positions],
                        "climatology_pred": climatology[positions],
                        "q05": q["q05"][positions] if q else np.nan,
                        "q25": q["q25"][positions] if q else np.nan,
                        "q50": q["q50"][positions] if q else prediction[positions],
                        "q75": q["q75"][positions] if q else np.nan,
                        "q95": q["q95"][positions] if q else np.nan,
                        "season": seasons,
                        "event_type": scenario.condition.event_type,
                        "quality_approved": quality[positions],
                        "artificial_mask": hidden[positions],
                        "external_validation_status": self.grid.external_validation_status,
                        "is_external_validation": False,
                        **design_fields,
                        **reference_fields,
                    }
                )
                daily_parts.append(daily)
        daily_result = (
            pd.concat(daily_parts, ignore_index=True) if daily_parts else pd.DataFrame()
        )
        return daily_result, pd.DataFrame(event_rows), skipped_rows

    def _run_keys(self) -> list[tuple[str, int | None]]:
        return [
            (model, seed)
            for model in self.models
            for seed in (self.training_seeds if model in TRAINABLE_MODELS else (None,))
        ]

    def _checkpoint_path(
        self,
        model_name: str,
        training_seed: int | None,
        scenario: ExperimentScenario,
    ) -> Path | None:
        if model_name not in TRAINABLE_MODELS or training_seed is None:
            return None
        condition = scenario.condition
        return (
            self.output_dir
            / "checkpoints"
            / (
                f"{model_name}-S{training_seed}-W{condition.window_length}-"
                f"{condition.training_protocol}.pt"
            )
        )

    def _run_execution_contract(
        self,
        scenario: ExperimentScenario,
        model_name: str,
        training_seed: int | None,
    ) -> dict[str, Any]:
        condition = scenario.condition
        if model_name in {"brits", "saits"}:
            _, model_config, training_config = self._deep_contract(
                model_name,
                int(training_seed),
                condition.window_length,
                condition.training_protocol,
            )
            training_context: dict[str, Any] | None = None
        elif model_name == "proposed":
            proposed_model, proposed_training, training_context = (
                self._proposed_contract(
                    int(training_seed),
                    condition.window_length,
                    condition.training_protocol,
                )
            )
            model_config = asdict(proposed_model)
            training_config = asdict(proposed_training)
        else:
            model_config = {"name": model_name}
            training_config = None
            training_context = None
        scenario_dir = self.mask_dir / "scenarios"
        contract = {
            "suite": self.grid.suite,
            "training_profile": self.training_profile_name,
            "model": model_name,
            "model_config": model_config,
            "training_seed": training_seed,
            "training_config": training_config,
            "training_context": training_context,
            "runner_training_settings": dict(self.training_settings),
            "mask_seed": scenario.mask_seed,
            "window_length": condition.window_length,
            "training_protocol": condition.training_protocol,
            "scenario": json.loads(json.dumps(scenario.as_dict())),
            "input_files": {
                "wide": _file_identity(self.wide_path),
                "quality": _file_identity(self.quality_path),
                "config": _file_identity(self.config_path),
            },
            "mask_files": {
                "axes": _file_identity(self.mask_dir / "axes.json"),
                "mask": _file_identity(
                    scenario_dir / f"{scenario.scenario_id}.npz"
                ),
                "metadata": _file_identity(
                    scenario_dir / f"{scenario.scenario_id}.json"
                ),
            },
            "checkpoint": _file_identity(
                self._checkpoint_path(model_name, training_seed, scenario)
            ),
        }
        return json.loads(json.dumps(contract))

    def _clear_model_cache(
        self,
        scenario: ExperimentScenario,
        model_name: str,
        training_seed: int | None,
    ) -> None:
        if training_seed is None:
            return
        key = (
            int(training_seed),
            scenario.condition.window_length,
            scenario.condition.training_protocol,
        )
        if model_name in {"brits", "saits"}:
            self._deep_cache.pop((model_name, *key), None)
        elif model_name == "proposed":
            self._proposed_cache.pop(key, None)
            self._proposed_checkpoint_metadata.pop(key, None)

    def _strict_checkpoint_valid(
        self,
        scenario: ExperimentScenario,
        model_name: str,
        training_seed: int | None,
    ) -> bool:
        checkpoint = self._checkpoint_path(model_name, training_seed, scenario)
        if checkpoint is None:
            return True
        if not checkpoint.exists() or training_seed is None:
            return False
        condition = scenario.condition
        self._clear_model_cache(scenario, model_name, training_seed)
        try:
            if model_name in {"brits", "saits"}:
                model_class, model_config, training_config = self._deep_contract(
                    model_name,
                    int(training_seed),
                    condition.window_length,
                    condition.training_protocol,
                )
                model = model_class.load_checkpoint(
                    checkpoint,
                    expected_config=model_config,
                    expected_training_config=training_config,
                )
                self._deep_cache[
                    (
                        model_name,
                        int(training_seed),
                        condition.window_length,
                        condition.training_protocol,
                    )
                ] = model
            else:
                model, metadata, mean, scale = self._load_proposed_model_checkpoint(
                    checkpoint,
                    int(training_seed),
                    condition.window_length,
                    condition.training_protocol,
                )
                key = (
                    int(training_seed),
                    condition.window_length,
                    condition.training_protocol,
                )
                self._proposed_cache[key] = (model, mean, scale)
                self._proposed_checkpoint_metadata[key] = metadata
        except (
            EOFError,
            OSError,
            KeyError,
            RuntimeError,
            TypeError,
            ValueError,
            pickle.UnpicklingError,
        ):
            self._clear_model_cache(scenario, model_name, training_seed)
            return False
        return True

    def _quarantine_checkpoint(
        self,
        scenario: ExperimentScenario,
        model_name: str,
        training_seed: int | None,
    ) -> Path | None:
        checkpoint = self._checkpoint_path(model_name, training_seed, scenario)
        if checkpoint is None or not checkpoint.exists():
            return None
        candidate = _quarantine_file(checkpoint)
        self._clear_model_cache(scenario, model_name, training_seed)
        return candidate

    def _run_scenario(self, scenario: ExperimentScenario) -> str:
        scenario_dir = self.output_dir / "scenarios" / scenario.scenario_id
        status_path = scenario_dir / "status.json"
        status = (
            json.loads(status_path.read_text(encoding="utf-8"))
            if self.resume and status_path.exists()
            else {}
        )
        artificial, metadata = self._generate_mask(scenario)
        run_keys = (
            [("pooled_loso", None)]
            if scenario.condition.mask_type == "loso"
            else self._run_keys()
        )
        expected_run_keys = {
            f"{model}:none" if seed is None else f"{model}:{seed}"
            for model, seed in run_keys
        }
        completed = set(status.get("completed_runs", ())).intersection(
            expected_run_keys
        )
        skipped_runs = list(status.get("skipped_runs", ()))
        retryable_run_keys = set(status.get("retryable_run_keys", ())) | {
            str(row.get("run_key"))
            for row in skipped_runs
            if row.get("retryable")
            or row.get("required_action") == "retrain_proposed_model"
        }
        retryable_run_keys.intersection_update(expected_run_keys)
        completed.difference_update(retryable_run_keys)
        terminal_run_keys = set(status.get("terminal_run_keys", ())).intersection(
            expected_run_keys
        )
        raw_contracts = status.get("run_contracts", {})
        stored_contracts = {
            str(key): value
            for key, value in (
                raw_contracts.items() if isinstance(raw_contracts, Mapping) else ()
            )
            if key in expected_run_keys and isinstance(value, Mapping)
        }
        daily_path = scenario_dir / "daily_predictions.parquet"
        event_path = scenario_dir / "event_metrics.parquet"
        daily = (
            pd.read_parquet(daily_path)
            if self.resume and daily_path.exists()
            else pd.DataFrame()
        )
        events = (
            pd.read_parquet(event_path)
            if self.resume and event_path.exists()
            else pd.DataFrame()
        )
        invalid_run_keys: set[str] = set()
        if not daily.empty:
            finite_daily = np.isfinite(
                pd.to_numeric(daily["y_true"], errors="coerce")
            ) & np.isfinite(pd.to_numeric(daily["y_pred"], errors="coerce"))
            invalid_run_keys.update(
                _stored_run_key(row.model, row.training_seed)
                for row in daily.loc[
                    ~finite_daily, ["model", "training_seed"]
                ].itertuples(index=False)
            )
        if not events.empty:
            finite_events = np.isfinite(
                pd.to_numeric(events["MAE"], errors="coerce")
            ) & np.isfinite(pd.to_numeric(events["RMSE"], errors="coerce"))
            invalid_run_keys.update(
                _stored_run_key(row.model, row.training_seed)
                for row in events.loc[
                    ~finite_events, ["model", "training_seed"]
                ].itertuples(index=False)
            )
        daily_run_keys = _frame_run_keys(daily)
        event_run_keys = _frame_run_keys(events)
        valid_terminal_run_keys = {
            run_key
            for run_key in terminal_run_keys
            if (
                rows := [
                    row
                    for row in skipped_runs
                    if row.get("run_key") == run_key
                ]
            )
            and all(
                not row.get("retryable")
                and row.get("reason_code") in STRUCTURAL_SKIP_CODES
                for row in rows
            )
        }
        invalidated = set(invalid_run_keys)
        for model_name, training_seed in run_keys:
            run_key = (
                f"{model_name}:none"
                if training_seed is None
                else f"{model_name}:{training_seed}"
            )
            if run_key not in completed:
                continue
            has_evidence = (
                run_key in daily_run_keys and run_key in event_run_keys
            ) or run_key in valid_terminal_run_keys
            contract_matches = stored_contracts.get(
                run_key
            ) == self._run_execution_contract(scenario, model_name, training_seed)
            checkpoint_valid = model_name not in TRAINABLE_MODELS or (
                contract_matches
                and self._strict_checkpoint_valid(
                    scenario, model_name, training_seed
                )
            )
            if not has_evidence or not contract_matches or not checkpoint_valid:
                invalidated.add(run_key)

        for run_key in invalidated | retryable_run_keys:
            completed.discard(run_key)
            terminal_run_keys.discard(run_key)
            stored_contracts.pop(run_key, None)
            daily = _without_run(daily, run_key)
            events = _without_run(events, run_key)
            skipped_runs = [
                row for row in skipped_runs if row.get("run_key") != run_key
            ]

        if daily_path.exists() and (invalidated or retryable_run_keys):
            _atomic_parquet(daily, daily_path)
        if event_path.exists() and (invalidated or retryable_run_keys):
            _atomic_parquet(events, event_path)

        for model_name, training_seed in run_keys:
            run_key = (
                f"{model_name}:none"
                if training_seed is None
                else f"{model_name}:{training_seed}"
            )
            if run_key in completed:
                continue
            self._clear_model_cache(scenario, model_name, training_seed)
            daily = _without_run(daily, run_key)
            events = _without_run(events, run_key)
            skipped_runs = [
                row for row in skipped_runs if row.get("run_key") != run_key
            ]
            terminal_run_keys.discard(run_key)
            stored_contracts.pop(run_key, None)
            retryable_run_keys.discard(run_key)
            retryable_failure = False
            try:
                new_daily, new_events, new_skips = self._prediction_rows(
                    scenario, metadata, artificial, model_name, training_seed
                )
            except _CheckpointRetrainingRequired as error:
                quarantined = self._quarantine_checkpoint(
                    scenario, model_name, training_seed
                )
                new_daily = pd.DataFrame()
                new_events = pd.DataFrame()
                new_skips = [
                    {
                        "run_key": run_key,
                        "model": model_name,
                        "training_seed": training_seed,
                        "station_id": None,
                        "target": None,
                        "reason_code": error.reason_code,
                        "reason": str(error),
                        "required_action": "retrain_proposed_model",
                        "retryable": True,
                        "quarantined_checkpoint": (
                            str(quarantined) if quarantined is not None else None
                        ),
                    }
                ]
                retryable_failure = True
            hard_failure_codes = {
                "no_approved_masked_targets",
                "nonfinite_prediction",
                "nonfinite_event_metrics",
            }
            if any(
                row.get("reason_code") in hard_failure_codes for row in new_skips
            ):
                retryable_failure = True
                for row in new_skips:
                    if row.get("reason_code") in hard_failure_codes:
                        row["retryable"] = True
                        row["required_action"] = "rerun_or_fix_model"

            result_evidence = not new_daily.empty and not new_events.empty
            terminal_evidence = (
                new_daily.empty
                and new_events.empty
                and bool(new_skips)
                and all(not row.get("retryable") for row in new_skips)
                and all(
                    row.get("reason_code") in STRUCTURAL_SKIP_CODES
                    for row in new_skips
                )
            )
            if (
                not retryable_failure
                and model_name in TRAINABLE_MODELS
                and result_evidence
                and not self._strict_checkpoint_valid(
                    scenario, model_name, training_seed
                )
            ):
                retryable_failure = True
                result_evidence = False
                new_daily = pd.DataFrame()
                new_events = pd.DataFrame()
                new_skips.append(
                    {
                        "run_key": run_key,
                        "model": model_name,
                        "training_seed": training_seed,
                        "station_id": None,
                        "target": None,
                        "reason_code": "checkpoint_invalid_after_run",
                        "reason": "trainable run did not produce a valid checkpoint",
                        "required_action": "rerun_or_fix_model",
                        "retryable": True,
                    }
                )
            if not retryable_failure and not result_evidence and not terminal_evidence:
                retryable_failure = True
                new_skips.append(
                    {
                        "run_key": run_key,
                        "model": model_name,
                        "training_seed": training_seed,
                        "station_id": None,
                        "target": None,
                        "reason_code": "missing_run_evidence",
                        "reason": "run produced neither both result tables nor a terminal skip",
                        "required_action": "rerun_or_fix_model",
                        "retryable": True,
                    }
                )
            daily = (
                pd.concat((daily, new_daily), ignore_index=True)
                if not new_daily.empty
                else daily
            )
            events = (
                pd.concat((events, new_events), ignore_index=True)
                if not new_events.empty
                else events
            )
            if not daily.empty or daily_path.exists():
                daily = daily.drop_duplicates(DAILY_KEY, keep="last")
                _atomic_parquet(daily, daily_path)
            if not events.empty or event_path.exists():
                events = events.drop_duplicates(EVENT_KEY, keep="last")
                _atomic_parquet(events, event_path)
            skipped_runs.extend(new_skips)
            skipped_runs = list(
                {
                    (
                        row["run_key"],
                        row.get("station_id"),
                        row.get("target"),
                        row.get("reason_code"),
                    ): row
                    for row in skipped_runs
                }.values()
            )
            if retryable_failure:
                completed.discard(run_key)
                retryable_run_keys.add(run_key)
                terminal_run_keys.discard(run_key)
                stored_contracts.pop(run_key, None)
            else:
                completed.add(run_key)
                retryable_run_keys.discard(run_key)
                if terminal_evidence:
                    terminal_run_keys.add(run_key)
                else:
                    terminal_run_keys.discard(run_key)
                stored_contracts[run_key] = self._run_execution_contract(
                    scenario, model_name, training_seed
                )
        completed.intersection_update(expected_run_keys)
        completed.difference_update(retryable_run_keys)
        terminal_run_keys.intersection_update(completed)
        stored_contracts = {
            key: value for key, value in stored_contracts.items() if key in completed
        }
        scenario_complete = not retryable_run_keys and expected_run_keys.issubset(
            completed
        )
        is_loso = scenario.condition.mask_type == "loso"
        _atomic_json(
            {
                "scenario_id": scenario.scenario_id,
                "status": "complete" if scenario_complete else "retryable_failure",
                "completed_runs": sorted(completed),
                "terminal_run_keys": sorted(terminal_run_keys),
                "run_contracts": stored_contracts,
                "skipped_runs": skipped_runs,
                "skipped_run_count": len(skipped_runs),
                "retryable_run_keys": sorted(retryable_run_keys),
                "fit_split": "train_other_stations" if is_loso else "train",
                "tuning_split": (
                    "validation_other_stations" if is_loso else "validation"
                ),
                "evaluation_split": "test",
                "validation_scope": scenario.condition.validation_scope,
                "is_external_validation": False,
            },
            status_path,
        )
        return "complete" if scenario_complete else "retryable_failure"

    def _aggregate(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        daily_frames = []
        event_frames = []
        scenarios = {
            scenario.scenario_id: scenario for scenario in self.grid.scenarios
        }
        allowed_models = set(self.models)
        if any(condition.mask_type == "loso" for condition in self.grid.conditions):
            allowed_models.add("pooled_loso")

        def current_runs(frame: pd.DataFrame) -> pd.DataFrame:
            if frame.empty:
                return frame
            selected = frame["model"].astype(str).isin(allowed_models)
            trainable = frame["model"].astype(str).isin(TRAINABLE_MODELS)
            selected &= (~trainable & frame["training_seed"].isna()) | (
                trainable
                & pd.to_numeric(frame["training_seed"], errors="coerce").isin(
                    self.training_seeds
                )
            )
            return frame.loc[selected]

        for scenario_id, scenario in sorted(scenarios.items()):
            directory = self.output_dir / "scenarios" / scenario_id
            status_path = directory / "status.json"
            daily_path = directory / "daily_predictions.parquet"
            event_path = directory / "event_metrics.parquet"
            status = (
                json.loads(status_path.read_text(encoding="utf-8"))
                if status_path.exists()
                else {}
            )
            raw_contracts = status.get("run_contracts", {})
            contracts = raw_contracts if isinstance(raw_contracts, Mapping) else {}
            completed = set(status.get("completed_runs", ()))
            completed.difference_update(status.get("retryable_run_keys", ()))
            run_keys = (
                [("pooled_loso", None)]
                if scenario.condition.mask_type == "loso"
                else self._run_keys()
            )
            contracted: set[str] = set()
            for model_name, training_seed in run_keys:
                run_key = (
                    f"{model_name}:none"
                    if training_seed is None
                    else f"{model_name}:{training_seed}"
                )
                if run_key in completed and contracts.get(
                    run_key
                ) == self._run_execution_contract(
                    scenario, model_name, training_seed
                ):
                    contracted.add(run_key)
            daily_frame = (
                current_runs(pd.read_parquet(daily_path))
                if daily_path.exists()
                else pd.DataFrame()
            )
            event_frame = (
                current_runs(pd.read_parquet(event_path))
                if event_path.exists()
                else pd.DataFrame()
            )
            result_run_keys = (
                contracted
                & _frame_run_keys(daily_frame)
                & _frame_run_keys(event_frame)
            )
            if daily_path.exists():
                selected = np.fromiter(
                    (
                        _stored_run_key(row.model, row.training_seed)
                        in result_run_keys
                        for row in daily_frame[
                            ["model", "training_seed"]
                        ].itertuples(index=False)
                    ),
                    dtype=bool,
                    count=len(daily_frame),
                )
                frame = daily_frame.loc[selected]
                if not frame.empty:
                    daily_frames.append(frame)
            if event_path.exists():
                selected = np.fromiter(
                    (
                        _stored_run_key(row.model, row.training_seed)
                        in result_run_keys
                        for row in event_frame[
                            ["model", "training_seed"]
                        ].itertuples(index=False)
                    ),
                    dtype=bool,
                    count=len(event_frame),
                )
                frame = event_frame.loc[selected]
                if not frame.empty:
                    event_frames.append(frame)
        daily = (
            pd.concat(daily_frames, ignore_index=True).drop_duplicates(DAILY_KEY)
            if daily_frames
            else pd.DataFrame(columns=DAILY_KEY)
        )
        events = (
            pd.concat(event_frames, ignore_index=True).drop_duplicates(EVENT_KEY)
            if event_frames
            else pd.DataFrame(columns=EVENT_KEY)
        )
        _atomic_parquet(daily, self.output_dir / "daily_predictions.parquet")
        _atomic_parquet(events, self.output_dir / "event_metrics.parquet")
        return daily, events

    def _training_checkpoint_summaries(self) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for (model_name, seed, window, protocol), model in sorted(
            self._deep_cache.items()
        ):
            history = dict(model.history_)
            summaries.append(
                {
                    "model": model_name,
                    "training_seed": seed,
                    "window": window,
                    "protocol": protocol,
                    "training_config": dict(model.training_config_),
                    "history": history,
                    "best_epoch": history.get("best_epoch"),
                    "epochs_run": history.get("epochs_ran"),
                    "hit_epoch_limit": history.get("hit_epoch_limit"),
                }
            )
        for (seed, window, protocol), metadata in sorted(
            self._proposed_checkpoint_metadata.items()
        ):
            summaries.append(
                {
                    "model": "proposed",
                    "training_seed": seed,
                    "window": window,
                    "protocol": protocol,
                    "training_config": dict(metadata.get("training_config", {})),
                    "training_context": dict(metadata.get("training_context", {})),
                    "history": list(metadata.get("history", [])),
                    "best_epoch": metadata.get("best_epoch", metadata.get("epoch")),
                    "epochs_run": metadata.get("epochs_run"),
                    "hit_epoch_limit": metadata.get("hit_epoch_limit"),
                }
            )
        return summaries

    def run(
        self,
        *,
        shard_index: int = 0,
        shard_count: int = 1,
        max_scenarios: int | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        selected = self.grid.shard(shard_index, shard_count).scenarios
        if max_scenarios is not None:
            if max_scenarios < 1:
                raise ValueError("max_scenarios must be positive")
            selected = selected[:max_scenarios]
        statuses = {"complete": 0, "skipped": 0}
        for scenario in selected:
            outcome = self._run_scenario(scenario)
            statuses[outcome] = statuses.get(outcome, 0) + 1
        daily, events = self._aggregate()
        aggregate_daily_runs = {
            (str(row.scenario_id), _stored_run_key(row.model, row.training_seed))
            for row in daily[["scenario_id", "model", "training_seed"]].itertuples(
                index=False
            )
        }
        aggregate_event_runs = {
            (str(row.scenario_id), _stored_run_key(row.model, row.training_seed))
            for row in events[["scenario_id", "model", "training_seed"]].itertuples(
                index=False
            )
        }
        aggregate_runs = aggregate_daily_runs & aggregate_event_runs
        expected_run_count = 0
        completed_status_run_count = 0
        grid_complete = True
        for scenario in self.grid.scenarios:
            expected_runs = {
                "pooled_loso:none"
                if scenario.condition.mask_type == "loso"
                else (f"{model}:none" if seed is None else f"{model}:{seed}")
                for model, seed in (
                    [("pooled_loso", None)]
                    if scenario.condition.mask_type == "loso"
                    else self._run_keys()
                )
            }
            expected_run_count += len(expected_runs)
            status_path = (
                self.output_dir / "scenarios" / scenario.scenario_id / "status.json"
            )
            if not status_path.exists():
                grid_complete = False
                continue
            status = json.loads(status_path.read_text(encoding="utf-8"))
            completed_runs = set(status.get("completed_runs", ()))
            completed_runs.difference_update(status.get("retryable_run_keys", ()))
            raw_contracts = status.get("run_contracts", {})
            contracts = raw_contracts if isinstance(raw_contracts, Mapping) else {}
            terminal_runs = set(status.get("terminal_run_keys", ()))
            valid_terminal_runs = {
                run_key
                for run_key in terminal_runs
                if (
                    rows := [
                        row
                        for row in status.get("skipped_runs", ())
                        if row.get("run_key") == run_key
                    ]
                )
                and all(
                    not row.get("retryable")
                    and row.get("reason_code") in STRUCTURAL_SKIP_CODES
                    for row in rows
                )
            }
            valid_completed: set[str] = set()
            scenario_run_keys = (
                [("pooled_loso", None)]
                if scenario.condition.mask_type == "loso"
                else self._run_keys()
            )
            for model_name, training_seed in scenario_run_keys:
                run_key = (
                    f"{model_name}:none"
                    if training_seed is None
                    else f"{model_name}:{training_seed}"
                )
                has_evidence = (
                    scenario.scenario_id,
                    run_key,
                ) in aggregate_runs or run_key in valid_terminal_runs
                if (
                    run_key in completed_runs
                    and has_evidence
                    and contracts.get(run_key)
                    == self._run_execution_contract(
                        scenario, model_name, training_seed
                    )
                ):
                    valid_completed.add(run_key)
            completed_status_run_count += len(
                expected_runs.intersection(valid_completed)
            )
            grid_complete &= status.get(
                "status"
            ) == "complete" and expected_runs.issubset(valid_completed)
        aggregate_scenarios = {scenario_id for scenario_id, _ in aggregate_runs}
        requires_training_seeds = any(
            model in TRAINABLE_MODELS for model in self.models
        )
        formal_training_seed_complete = (
            not requires_training_seeds
            or set(self.training_seeds) == set(self.grid.training_seeds)
        )
        formal_mask_seed_complete = (
            self.training_profile_name == "smoke"
            or set(self.grid.mask_seeds) == set(range(101, 121))
        )
        formal_design_complete = bool(
            grid_complete
            and formal_training_seed_complete
            and formal_mask_seed_complete
        )
        _atomic_json(
            {
                "suite": self.grid.suite,
                "models": list(self.models),
                "training_seeds": list(self.training_seeds),
                "mask_seeds": list(self.grid.mask_seeds),
                "shard_index": shard_index,
                "shard_count": shard_count,
                "selected_scenarios": len(selected),
                "grid_scenario_count": len(self.grid.scenarios),
                "expected_run_count": expected_run_count,
                "completed_status_run_count": completed_status_run_count,
                "aggregate_scenario_count": len(aggregate_scenarios),
                "aggregate_run_count": len(aggregate_runs),
                "complete": formal_design_complete,
                "formal_design_complete": formal_design_complete,
                "formal_training_seed_complete": formal_training_seed_complete,
                "formal_mask_seed_complete": formal_mask_seed_complete,
                "expected_mask_seeds": list(range(101, 121)),
                "expected_training_seeds": list(self.grid.training_seeds),
                "status_counts": statuses,
                "fit_split": "train",
                "tuning_split": "validation",
                "evaluation_split": "test_once",
                "external_validation_status": self.grid.external_validation_status,
                "loso_scope": "exploratory_internal_not_external_validation",
                "training_profile": self.training_profile_name,
                "training_settings": self.training_settings,
                "training_checkpoints": self._training_checkpoint_summaries(),
            },
            self.output_dir / "run_manifest.json",
        )
        return daily, events


def run_experiments(
    grid: ExperimentGrid, **kwargs: Any
) -> tuple[pd.DataFrame, pd.DataFrame]:
    run_kwargs = {
        key: kwargs.pop(key)
        for key in ("shard_index", "shard_count", "max_scenarios")
        if key in kwargs
    }
    return ExperimentRunner(grid, **kwargs).run(**run_kwargs)


__all__ = [
    "SUPPORTED_MODELS",
    "ExperimentRunner",
    "apply_full_artificial_mask",
    "make_training_mask",
    "run_experiments",
]
