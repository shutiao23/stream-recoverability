"""Resume-safe unified runner for traditional, deep, and proposed imputers."""

from __future__ import annotations

import json
import pickle
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import yaml

from stream_recoverability.evaluation.event_metrics import compute_event_metrics
from stream_recoverability.masks import (
    centered_bounds,
    derive_event_day_condition,
    generate_async_mask,
    generate_block_mask,
    generate_event_mask,
    generate_multiblock_mask,
    generate_nested_point_mask_family,
    generate_network_outage_mask,
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
from stream_recoverability.models.proposed_curriculum import (
    CURRICULUM_SCENARIOS,
    FROZEN_VALIDATION_SCENARIOS,
    ProposedCurriculumConfig,
    ValidationScenario,
    generate_curriculum_mask,
    sample_curriculum_scenarios,
)
from stream_recoverability.models.proposed_training import (
    ProposedTrainingConfig,
    load_proposed_checkpoint,
    set_deterministic_seed,
    train_proposed_model,
    validate_proposed_checkpoint_contract,
)
from stream_recoverability.models.reference_baselines import (
    REFERENCE_IMPLEMENTATION,
    PyPOTSReferenceImputer,
    ReferenceProtocolData,
    ReferenceTrainingConfig,
    build_reference_protocol_data,
)
from stream_recoverability.models.training import make_windows

from .contracts import (
    DEFAULT_DESIGN_PATH,
    DEFAULT_MANIFEST_PATH,
    build_design_contract,
    canonical_evaluation_split,
    file_sha256,
    validate_data_version_inputs,
)
from .formal_authorization import (
    validate_formal_authorization,
    validate_formal_grid_contract,
)
from .grid import ExperimentGrid, ExperimentScenario
from .model_registry import FrozenModelDesign, load_frozen_model_design

TRADITIONAL_MODELS = (
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
)
LOCAL_DEEP_MODELS = frozenset({"brits_lite", "saits_lite"})
REFERENCE_MODELS = frozenset({"brits_ref", "saits_ref", "csdi"})
LEGACY_MODEL_ALIASES = {"brits": "brits_lite", "saits": "saits_lite"}
SUPPORTED_MODELS = (
    *TRADITIONAL_MODELS,
    "brits_lite",
    "saits_lite",
    "brits_ref",
    "saits_ref",
    "csdi",
    "proposed",
)
TRAINABLE_MODELS = {*LOCAL_DEEP_MODELS, *REFERENCE_MODELS, "proposed"}
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
EVENT_DESIGN_FIELD_NAMES = (
    "anchor_id",
    "event_id",
    "control_id",
    "pair_id",
    "catalog_role",
    "event_season",
    "event_threshold",
    "threshold",
    "threshold_quantile",
    "threshold_operator",
    "threshold_reference_split",
    "threshold_reference_scope",
    "threshold_training_samples",
    "minimum_training_samples",
    "source_split",
    "analysis_eligible",
    "catalog_schema_version",
    "episode_length",
    "event_window_length",
    "episode_component_count",
    "raw_episode_length",
    "raw_episode_start_index",
    "raw_episode_end_index",
    "raw_episode_start_date",
    "raw_episode_end_date",
    "window_start_index",
    "window_end_index",
    "window_center_index",
    "window_start_date",
    "window_end_date",
    "window_center_date",
    "event_peak_index",
    "event_peak_date",
    "event_peak_value",
    "event_min_index",
    "event_min_date",
    "event_min_value",
    "event_intensity",
    "rising_phase_start_index",
    "rising_phase_end_index",
    "rising_phase_start_date",
    "rising_phase_end_date",
    "peak_phase_start_index",
    "peak_phase_end_index",
    "peak_phase_start_date",
    "peak_phase_end_date",
    "recession_phase_start_index",
    "recession_phase_end_index",
    "recession_phase_start_date",
    "recession_phase_end_date",
    "control_start_index",
    "control_end_index",
    "control_center_index",
    "control_start_date",
    "control_end_date",
    "control_center_date",
    "event_definition",
    "minimum_duration_days",
    "merge_gap_days",
    "fixed_window_length",
    "climatology_half_window_days",
    "threshold_doy_half_window_days",
    "event_climatology_value",
    "control_context_days",
    "event_window_eligible",
    "event_left_context_available",
    "event_right_context_available",
    "analysis_exclusion_reason",
    "episode_boundary_policy",
    "control_match_year_distance",
    "control_match_day_of_year_distance",
    "control_reuse_policy",
)


def canonical_model_name(value: str) -> str:
    """Return the emitted model name, accepting legacy lite aliases as input."""

    normalized = str(value).strip().lower()
    return LEGACY_MODEL_ALIASES.get(normalized, normalized)


def _reference_adapter_name(model_name: str) -> str:
    mapping = {"brits_ref": "brits", "saits_ref": "saits", "csdi": "csdi"}
    try:
        return mapping[model_name]
    except KeyError as error:
        raise ValueError(
            f"{model_name!r} is not an official reference model"
        ) from error


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
    data_version: str


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


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _stored_run_key(model: Any, training_seed: Any) -> str:
    if training_seed is None or pd.isna(training_seed):
        return f"{model}:none"
    seed = float(training_seed)
    return f"{model}:{int(seed)}" if seed.is_integer() else f"{model}:{training_seed}"


@lru_cache(maxsize=4096)
def _cached_file_sha256(path: str, size: int, mtime_ns: int) -> str:
    del size, mtime_ns
    return file_sha256(path)


def _file_identity(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "sha256": _cached_file_sha256(
            str(path.resolve()), int(stat.st_size), int(stat.st_mtime_ns)
        ),
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
    if "data_version" in wide:
        wide_versions = tuple(
            str(value) for value in wide["data_version"].dropna().unique()
        )
        if len(wide_versions) != 1:
            raise ValueError("wide data must contain exactly one data_version")
        data_version = wide_versions[0]
    else:
        data_version = "published_v1"

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
        v2_quality_contract = data_version == "published_v2" or data_version.endswith(
            "_v2"
        )
        quality_column = (
            "analysis_eligible" if v2_quality_contract else "quality_approved"
        )
        required_long = {"date", "station_id", "variable", quality_column}
        if v2_quality_contract:
            required_long.update({"provider_qc_status", "known_issue_flag"})
        if not required_long.issubset(long):
            raise KeyError(
                f"quality data is missing {sorted(required_long.difference(long.columns))}"
            )
        long = long.copy()
        long["date"] = pd.to_datetime(long["date"]).dt.normalize()
        if "quality_approved" in long and "analysis_eligible" in long:
            legacy = long["quality_approved"].fillna(False).astype(bool)
            current = long["analysis_eligible"].fillna(False).astype(bool)
            if not legacy.equals(current):
                raise ValueError(
                    "quality_approved legacy alias differs from analysis_eligible"
                )
        if "data_version" in long:
            long_versions = tuple(
                str(value) for value in long["data_version"].dropna().unique()
            )
            if long_versions != (data_version,):
                raise ValueError(
                    "wide and quality data must carry the same single data_version"
                )
        elif "data_version" in wide:
            raise ValueError(
                "versioned wide data requires quality data with explicit data_version"
            )
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
                    aligned[quality_column].fillna(False).astype(bool).to_numpy()
                )
                natural_column = (
                    "natural_observed"
                    if "natural_observed" in aligned
                    else quality_column
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
        data_version=data_version,
    )


CONFIRMATORY_ONCE_PATH_REQUIRED = (
    "evaluation_split=confirmatory is prohibited outside the once-locked "
    "scripts/20 confirmatory path; scripts/08 and ExperimentRunner cannot "
    "train or write skill on confirmatory splits"
)


class ExperimentRunner:
    """Execute scenario shards and atomically aggregate resume-safe outputs."""

    _allow_confirmatory_evaluation = False

    def __init__(
        self,
        grid: ExperimentGrid,
        *,
        wide_path: str | Path = "data/processed/daily_wide.parquet",
        quality_path: str | Path | None = "data/processed/daily_long.parquet",
        output_dir: str | Path = "results/experiments",
        mask_dir: str | Path = "masks/full",
        config_path: str | Path = "configs/experiments.yaml",
        design_path: str | Path = DEFAULT_DESIGN_PATH,
        manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
        data_version_manifest_path: str | Path | None = None,
        models: Sequence[str] | None = None,
        training_seeds: Sequence[int] | None = None,
        formal_authorization: Mapping[str, Any] | None = None,
        resume: bool = True,
    ) -> None:
        self.grid = grid
        self.config_path = Path(config_path)
        self.design_path = Path(design_path)
        self.manifest_path = Path(manifest_path)
        self.config = _read_yaml(config_path)
        self.frozen_model_design: FrozenModelDesign = load_frozen_model_design(
            self.design_path
        )
        undeclared_implementations = sorted(
            set(self.frozen_model_design.all_candidates).difference(SUPPORTED_MODELS)
        )
        if undeclared_implementations:
            raise ValueError(
                "design freeze declares models that the runner does not implement: "
                f"{undeclared_implementations}"
            )
        runner_config = dict(self.config.get("runner", {}))
        self.training_profile_name = "smoke" if grid.suite == "smoke" else "formal"
        profile = dict(runner_config.get(self.training_profile_name, {}))
        common_training = self.frozen_model_design.common_training
        if self.training_profile_name == "formal":
            configured_formal_budget = {
                "deep_epochs": profile.get("deep_epochs"),
                "deep_patience": profile.get("deep_patience"),
                "proposed_epochs": profile.get("proposed_epochs"),
                "proposed_patience": profile.get("proposed_patience"),
                "batch_size": runner_config.get("batch_size"),
            }
            frozen_formal_budget = {
                "deep_epochs": common_training["max_epochs"],
                "deep_patience": common_training["patience"],
                "proposed_epochs": common_training["max_epochs"],
                "proposed_patience": common_training["patience"],
                "batch_size": common_training["batch_size"],
            }
            formal_mismatches = {
                name: (configured_formal_budget[name], frozen_formal_budget[name])
                for name in frozen_formal_budget
                if configured_formal_budget[name] != frozen_formal_budget[name]
            }
            if formal_mismatches:
                raise ValueError(
                    "formal experiments.yaml training budget disagrees with the "
                    f"frozen design: {formal_mismatches}"
                )
            deep_epochs = int(common_training["max_epochs"])
            deep_patience = int(common_training["patience"])
            proposed_epochs = int(common_training["max_epochs"])
            proposed_patience = int(common_training["patience"])
            batch_size = int(common_training["batch_size"])
        else:
            deep_epochs = int(profile["deep_epochs"])
            deep_patience = int(profile["deep_patience"])
            proposed_epochs = int(profile["proposed_epochs"])
            proposed_patience = int(profile["proposed_patience"])
            batch_size = int(runner_config["batch_size"])
        self.training_settings = {
            "train_mask_repeats": int(profile["train_mask_repeats"]),
            "validation_mask_repeats": int(profile["validation_mask_repeats"]),
            "deep_epochs": deep_epochs,
            "deep_patience": deep_patience,
            "proposed_epochs": proposed_epochs,
            "proposed_patience": proposed_patience,
            "batch_size": batch_size,
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
                "all_variables", ("T", "F", "L", "Ta", "P", "W", "RH", "Rs")
            )
        )
        self.wide_path = Path(wide_path)
        self.quality_path = Path(quality_path) if quality_path is not None else None
        grid_versions = {condition.data_version for condition in grid.conditions}
        if len(grid_versions) != 1:
            raise ValueError("one runner grid cannot mix data_version values")
        grid_data_version = next(iter(grid_versions))
        evaluation_splits = {
            condition.evaluation_split for condition in grid.conditions
        }
        if len(evaluation_splits) != 1:
            raise ValueError("one runner grid cannot mix evaluation_split values")
        self.evaluation_split = next(iter(evaluation_splits))
        if canonical_evaluation_split(self.evaluation_split) == "confirmatory":
            if not self._allow_confirmatory_evaluation:
                raise ValueError(CONFIRMATORY_ONCE_PATH_REQUIRED)
        inferred_version_manifest = self.wide_path.parent / "version_manifest.json"
        self.data_version_manifest_path = (
            Path(data_version_manifest_path)
            if data_version_manifest_path is not None
            else inferred_version_manifest
            if inferred_version_manifest.exists()
            else None
        )
        strict_version_binding = bool(
            formal_authorization is not None or self.evaluation_split == "validation"
        )
        self.data_version_input_identity = validate_data_version_inputs(
            data_version_manifest_path=self.data_version_manifest_path,
            data_version=grid_data_version,
            wide_path=self.wide_path,
            quality_path=self.quality_path,
            require_manifest=strict_version_binding,
            require_quality=strict_version_binding,
        )
        self.data = _load_data(wide_path, quality_path, self.variable_names)
        if grid_versions != {self.data.data_version}:
            raise ValueError(
                "experiment grid and input data_version differ: "
                f"grid={sorted(grid_versions)}, data={self.data.data_version!r}"
            )
        design_contract = build_design_contract(
            design_path=self.design_path,
            manifest_path=self.manifest_path,
            experiment_config_path=self.config_path,
            data_version=self.data.data_version,
            evaluation_split=self.evaluation_split,
            data_version_manifest_path=self.data_version_manifest_path,
        )
        self.code_provenance = dict(design_contract.pop("code_provenance"))
        self.evidence_contract = design_contract
        self._assert_formal_code_provenance(
            self.training_profile_name, self.code_provenance
        )
        self.output_dir = Path(output_dir)
        self.mask_dir = Path(mask_dir)
        requested_models = tuple(
            runner_config.get("default_models", ())
            if models is None and self.training_profile_name == "smoke"
            else self.frozen_model_design.formal_candidates
            if models is None
            else models
        )
        if not requested_models:
            raise ValueError("at least one model must be selected")
        normalized_inputs = tuple(
            str(value).strip().lower() for value in requested_models
        )
        legacy_inputs = sorted(
            set(normalized_inputs).intersection(LEGACY_MODEL_ALIASES)
        )
        if legacy_inputs and self.training_profile_name == "formal":
            raise ValueError(
                "legacy BRITS/SAITS aliases are migration-only and cannot be used "
                f"in formal runs: {legacy_inputs}"
            )
        self.models = tuple(
            dict.fromkeys(canonical_model_name(value) for value in normalized_inputs)
        )
        unknown = sorted(set(self.models).difference(SUPPORTED_MODELS))
        if unknown:
            raise ValueError(f"unsupported models: {unknown}")
        if self.training_profile_name == "formal":
            nonformal = sorted(
                set(self.models).difference(self.frozen_model_design.formal_candidates)
            )
            if nonformal:
                raise ValueError(
                    "formal runner models must come from the design freeze formal "
                    f"candidate registry: {nonformal}"
                )
        if formal_authorization is not None and (
            self.training_profile_name != "formal"
            or self.evaluation_split != "development_test"
        ):
            raise ValueError(
                "formal roster authorization is valid only for formal "
                "development_test execution"
            )
        self.formal_authorization = (
            validate_formal_authorization(
                formal_authorization,
                expected_suite=self.grid.suite,
                expected_models=self.models,
                design_path=self.design_path,
                study_manifest_path=self.manifest_path,
                experiment_config_path=self.config_path,
            )
            if formal_authorization is not None
            else None
        )
        self.formal_evidence = self.formal_authorization is not None
        self.formal_grid_contract = (
            validate_formal_grid_contract(self.grid) if self.formal_evidence else None
        )
        self.model_request_aliases = {
            value: canonical_model_name(value)
            for value in normalized_inputs
            if value in LEGACY_MODEL_ALIASES
        }
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
        self._reference_protocol_cache: dict[
            tuple[int, int, str], ReferenceProtocolData
        ] = {}
        self._reference_cache: dict[
            tuple[str, int, int, str], PyPOTSReferenceImputer
        ] = {}
        self._reference_last_run_diagnostics: dict[
            tuple[str, int, int, str], dict[str, Any]
        ] = {}
        self._reference_inference_seconds: dict[tuple[str, int, int, str], float] = {}
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
        self._proposed_climatology_cache: np.ndarray | None = None
        self.anchor_availability = self._build_anchor_availability_report()
        if not self.anchor_availability.empty:
            identity_failures = self.anchor_availability.loc[
                self.anchor_availability["reason"].isin(
                    {
                        "anchor_mask_seed_mismatch",
                        "anchor_evaluation_split_mismatch",
                        "center_identity_mismatch",
                    }
                )
            ]
            if not identity_failures.empty:
                raise ValueError(
                    "fixed anchor identity does not match the current data axis:\n"
                    + identity_failures.to_string(index=False)
                )

    @staticmethod
    def _assert_formal_code_provenance(
        training_profile_name: str,
        code_provenance: Mapping[str, Any],
    ) -> None:
        if training_profile_name == "formal" and not code_provenance.get(
            "relevant_source_clean", False
        ):
            raise RuntimeError(
                "formal runs require clean, committed relevant source and frozen "
                "configuration inputs; code provenance status is "
                f"{code_provenance.get('status')!r}, dirty tracked paths are "
                f"{code_provenance.get('dirty_tracked_paths', [])}, and "
                "relevant untracked paths are "
                f"{code_provenance.get('relevant_untracked_paths', [])}"
            )

    @property
    def train_rows(self) -> np.ndarray:
        return self.data.splits == "train"

    @property
    def validation_rows(self) -> np.ndarray:
        return self.data.splits == "validation"

    @property
    def test_rows(self) -> np.ndarray:
        return self.data.splits == "test"

    @staticmethod
    def _stored_split_label(evaluation_split: str) -> str:
        return "test" if evaluation_split == "development_test" else evaluation_split

    def _evaluation_rows(self, scenario: ExperimentScenario) -> np.ndarray:
        label = self._stored_split_label(scenario.condition.evaluation_split)
        rows = self.data.splits == label
        if not rows.any():
            raise ValueError(
                f"input data contains no rows for evaluation_split {label!r}"
            )
        return rows

    def _build_anchor_availability_report(self) -> pd.DataFrame:
        """Report fixed-center truth availability without drawing replacements."""

        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str, tuple[str, ...], int]] = set()
        for scenario in self.grid.scenarios:
            condition = scenario.condition
            if condition.anchor_id is None or condition.center_index is None:
                continue
            variables = tuple(map(str, condition.variables))
            audit_length = int(
                condition.gap_length or condition.anchor_max_supported_length or 1
            )
            key = (
                str(condition.anchor_id),
                condition.condition_id,
                variables,
                audit_length,
            )
            if key in seen:
                continue
            seen.add(key)
            center_index = int(condition.center_index)
            center_date = pd.Timestamp(condition.center_date).normalize()
            center_matches = (
                0 <= center_index < len(self.data.dates)
                and self.data.dates[center_index] == center_date
            )
            available_cells = 0
            required_cells = audit_length * len(variables)
            if condition.mask_type == "async" and condition.async_axis == "station":
                required_cells *= len(condition.station_ids)
            layout_start_index: int | None = None
            layout_end_index: int | None = None
            reason = "available"
            if condition.anchor_mask_seed != scenario.mask_seed:
                reason = "anchor_mask_seed_mismatch"
            elif condition.anchor_evaluation_split != condition.evaluation_split:
                reason = "anchor_evaluation_split_mismatch"
            elif not center_matches:
                reason = "center_identity_mismatch"
            else:
                target_start, target_stop = centered_bounds(
                    center_index, audit_length, len(self.data.dates)
                )
                variable_indices = [
                    self.data.variable_names.index(variable) for variable in variables
                ]
                if condition.mask_type == "async":
                    shift = round(audit_length * (1.0 - float(condition.overlap_ratio)))
                    if condition.async_axis == "variable":
                        groups = [
                            (
                                [self.data.station_ids.index(condition.station_ids[0])],
                                [variable],
                            )
                            for variable in variable_indices
                        ]
                    elif condition.async_axis == "station":
                        groups = [
                            ([self.data.station_ids.index(station)], variable_indices)
                            for station in condition.station_ids
                        ]
                    else:
                        raise ValueError("anchored async condition has an invalid axis")
                else:
                    shift = 0
                    groups = [
                        (
                            [self.data.station_ids.index(condition.station_ids[0])],
                            variable_indices,
                        )
                    ]
                layout_start_index = target_start
                layout_end_index = target_stop - 1 + shift * (len(groups) - 1)
                if layout_end_index >= len(self.data.dates):
                    reason = "fixed_anchor_layout_out_of_bounds"
                else:
                    evaluation_rows = self._evaluation_rows(scenario)
                    for group_index, (station_indices, group_variables) in enumerate(
                        groups
                    ):
                        start = target_start + group_index * shift
                        stop = start + audit_length
                        selected = np.ix_(
                            np.arange(start, stop, dtype=int),
                            np.asarray(station_indices, dtype=int),
                            np.asarray(group_variables, dtype=int),
                        )
                        available = (
                            self.data.natural_observed[selected]
                            & self.data.quality_approved[selected]
                            & np.isfinite(self.data.values[selected])
                        )
                        available &= evaluation_rows[start:stop, None, None]
                        available_cells += int(available.sum())
                if available_cells != required_cells and reason == "available":
                    reason = "incomplete_fixed_anchor_truth"
            rows.append(
                {
                    "anchor_id": str(condition.anchor_id),
                    "condition_id": condition.condition_id,
                    "mask_seed": int(scenario.mask_seed),
                    "station_id": str(condition.station_ids[0]),
                    "anchor_target": condition.anchor_target,
                    "required_variables": "_".join(variables),
                    "gap_length": audit_length,
                    "center_date": str(condition.center_date),
                    "center_index": center_index,
                    "layout_start_index": layout_start_index,
                    "layout_end_index": layout_end_index,
                    "anchor_data_version": condition.anchor_data_version,
                    "data_version": self.data.data_version,
                    "anchor_evaluation_split": condition.anchor_evaluation_split,
                    "evaluation_split": condition.evaluation_split,
                    "source_split": condition.anchor_source_split,
                    "required_cells": required_cells,
                    "available_cells": available_cells,
                    "available": reason == "available",
                    "reason": reason,
                    "replacement_allowed": False,
                }
            )
        return pd.DataFrame(rows)

    def _evidence_role(self, evaluation_split: str) -> str:
        if evaluation_split == "validation":
            return "model_selection_only"
        if evaluation_split in {"test", "development_test"}:
            return (
                "formal_development_evaluation"
                if self.formal_evidence
                else "development_evaluation"
            )
        return "confirmatory_once"

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

    @staticmethod
    def _condition_anchor_metadata(condition: Any) -> dict[str, Any] | None:
        if condition.anchor_id is None:
            return None
        required = {
            "center_index": condition.center_index,
            "center_date": condition.center_date,
            "mask_seed": condition.anchor_mask_seed,
            "max_supported_length": condition.anchor_max_supported_length,
            "data_version": condition.anchor_data_version,
            "evaluation_split": condition.anchor_evaluation_split,
            "source_split": condition.anchor_source_split,
            "target": condition.anchor_target,
        }
        missing = sorted(key for key, value in required.items() if value is None)
        if missing:
            raise ValueError(
                f"fixed anchor {condition.anchor_id!r} is missing metadata: {missing}"
            )
        return {
            "anchor_id": condition.anchor_id,
            **required,
            "start_month": condition.anchor_start_month,
            "season": condition.anchor_season,
            "year": condition.anchor_year,
            "hydrologic_state": condition.anchor_hydrologic_state,
        }

    def _event_condition(self, scenario: ExperimentScenario) -> np.ndarray:
        station = self.data.station_ids.index(scenario.condition.station_ids[0])
        event = str(scenario.condition.event_type)
        if event in {"high_temperature", "rapid_warming"}:
            variable = self.data.variable_names.index("T")
        else:
            variable = self.data.variable_names.index("F")
        series = self.data.values[:, station, variable]
        source_split = scenario.condition.source_split or self._stored_split_label(
            scenario.condition.evaluation_split
        )
        derived = derive_event_day_condition(
            self.data.dates,
            series,
            self.data.quality_approved[:, station, variable],
            self.data.splits,
            event,
            source_split=source_split,
            minimum_training_samples=(
                scenario.condition.minimum_training_samples or 30
            ),
        )
        return derived.condition & self._evaluation_rows(scenario)

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
            if (
                not axes_path.exists()
                or json.loads(axes_path.read_text(encoding="utf-8")) != expected_axes
            ):
                raise ValueError("stored mask axes do not match the current data")
            try:
                mask, metadata = _load_compact_mask(self.mask_dir, scenario.scenario_id)
                self._validate_scenario_mask(scenario, mask, metadata)
            except (KeyError, ValueError):
                # Current quality or scenario metadata can legitimately invalidate
                # one cached mask; regenerate only that scenario below.
                pass
            else:
                return mask, metadata
        condition = scenario.condition
        stations, variables = self._indices(scenario)
        evaluation_rows = self._evaluation_rows(scenario)
        eligible = (
            self.data.natural_observed
            & self.data.quality_approved
            & np.isfinite(self.data.values)
            & evaluation_rows[:, None, None]
        )
        # Offline interpolators need a right boundary; never hide the final
        # available row of the selected evaluation split.
        if condition.mask_type != "loso":
            eligible[np.flatnonzero(evaluation_rows)[-1]] = False
        common = {
            "eligible": eligible,
            "seed": scenario.mask_seed,
            "station_ids": self.data.station_ids,
            "variable_names": self.data.variable_names,
            "split": condition.evaluation_split,
            "scenario_id": scenario.scenario_id,
        }
        if condition.mask_type == "loso":
            mask = np.zeros_like(eligible, dtype=bool)
            station = self.data.station_ids.index(str(condition.held_out_station))
            target = self.data.variable_names.index("T")
            mask[:, station, target] = eligible[:, station, target]
            metadata = {
                "scenario_id": scenario.scenario_id,
                "split": condition.evaluation_split,
                "seed": scenario.mask_seed,
                "mask_type": "loso",
                "station_ids": [self.data.station_ids[station]],
                "variables": ["T"],
                "masked_cells": int(mask.sum()),
                "held_out_station": self.data.station_ids[station],
                "validation_scope": condition.validation_scope,
                "is_external_validation": condition.evaluation_split == "confirmatory",
            }
        elif condition.mask_type == "point":
            point_family = generate_nested_point_mask_family(
                eligible,
                missing_rates=(0.10, 0.30, 0.50),
                station_indices=stations,
                variable_indices=variables,
                synchronized=True,
                seed=scenario.mask_seed,
                dates=self.data.dates.to_numpy(),
                station_ids=self.data.station_ids,
                variable_names=self.data.variable_names,
                split=condition.evaluation_split,
            )
            try:
                mask, metadata = point_family[float(condition.missing_rate)]
            except KeyError as error:
                raise ValueError(
                    "point conditions must use the frozen nested rates 0.10/0.30/0.50"
                ) from error
            metadata["scenario_id"] = scenario.scenario_id
        elif condition.mask_type == "block":
            anchor_metadata = self._condition_anchor_metadata(condition)
            mask, metadata = generate_block_mask(
                length=int(condition.gap_length),
                station_indices=stations,
                variable_indices=variables,
                dates=self.data.dates.to_numpy(),
                center_index=condition.center_index,
                center_date=condition.center_date,
                anchor_id=condition.anchor_id,
                anchor_metadata=anchor_metadata,
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
                center_index=condition.center_index,
                center_date=condition.center_date,
                anchor_id=condition.anchor_id,
                anchor_metadata=self._condition_anchor_metadata(condition),
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
                center_index=condition.center_index,
                center_date=condition.center_date,
                anchor_id=condition.anchor_id,
                anchor_metadata=self._condition_anchor_metadata(condition),
                **common,
            )
        elif condition.mask_type == "async":
            mask, metadata = generate_async_mask(
                length=int(condition.gap_length),
                overlap_ratio=float(condition.overlap_ratio),
                station_indices=stations,
                variable_indices=variables,
                axis=str(condition.async_axis),
                dates=self.data.dates.to_numpy(),
                center_index=condition.center_index,
                center_date=condition.center_date,
                anchor_id=condition.anchor_id,
                anchor_metadata=self._condition_anchor_metadata(condition),
                **common,
            )
            metadata["target_gap_id"] = (
                f"{condition.experiment}-{condition.station_ids[0]}-"
                f"{condition.anchor_target}-D{int(condition.gap_length):03d}-"
                f"{condition.anchor_id}"
            )
        elif condition.mask_type == "network_outage":
            mask, metadata = generate_network_outage_mask(
                length=int(condition.gap_length),
                station_indices=stations,
                variable_indices=variables,
                dates=self.data.dates.to_numpy(),
                **common,
            )
        elif condition.mask_type in {"event", "event_episode", "event_control"}:
            event_kwargs: dict[str, Any] = {
                "event_condition": self._event_condition(scenario),
                "event_type": str(condition.event_type),
                "station_indices": stations,
                "variable_indices": variables,
                "synchronized": True,
                "dates": self.data.dates.to_numpy(),
                "anchor_id": condition.anchor_id,
                "event_id": condition.event_id,
                "control_id": condition.control_id,
                "pair_id": condition.pair_id,
                "catalog_role": condition.catalog_role or "stress",
                "event_metadata": condition.as_dict(),
            }
            if condition.mask_type == "event":
                event_kwargs["missing_rate"] = float(condition.missing_rate)
            else:
                event_kwargs.update(
                    {
                        "length": int(condition.gap_length),
                        "forced_start_index": int(condition.forced_start_index),
                        "center_date": condition.center_date,
                        "context": int(condition.control_context_days or 0),
                    }
                )
            mask, metadata = generate_event_mask(**event_kwargs, **common)
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
                "evaluation_split": condition.evaluation_split,
                "evidence_role": self._evidence_role(condition.evaluation_split),
                "formal_evidence": self.formal_evidence,
                "external_validation_status": self.grid.external_validation_status,
                "is_external_validation": condition.evaluation_split == "confirmatory",
                **self.evidence_contract,
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
        evaluation_rows = self._evaluation_rows(scenario)
        if np.any(mask[~evaluation_rows]):
            raise ValueError("scenario mask leaked outside its evaluation split")
        if np.any(mask & ~self.data.quality_approved):
            raise ValueError(
                "scenario mask includes cells not currently quality-approved"
            )
        if np.any(mask & ~self.data.natural_observed):
            raise ValueError("scenario mask includes cells without natural truth")
        if (
            scenario.condition.mask_type != "loso"
            and mask[np.flatnonzero(evaluation_rows)[-1]].any()
        ):
            raise ValueError("offline scenario mask cannot hide the final split row")
        expected = json.loads(json.dumps(scenario.as_dict()))
        stored = json.loads(json.dumps(dict(metadata)))
        mismatches = {
            key: (stored.get(key), value)
            for key, value in expected.items()
            if stored.get(key) != value
        }
        if mismatches:
            raise ValueError(f"stored mask condition metadata mismatch: {mismatches}")
        contract_mismatches = {
            key: (stored.get(key), value)
            for key, value in self.evidence_contract.items()
            if stored.get(key) != value
        }
        if contract_mismatches:
            raise ValueError(
                f"stored mask evidence contract mismatch: {contract_mismatches}"
            )
        condition = scenario.condition
        if condition.anchor_id is not None and condition.mask_type in {
            "async",
            "block",
            "station_outage",
            "matched_network",
        }:
            if stored.get("selection_mode") not in {
                "fixed_center",
                "fixed_center_and_start",
                "fixed_target_center",
            }:
                raise ValueError("anchored scenario did not use fixed-center selection")
            if stored.get("anchor_id") != condition.anchor_id:
                raise ValueError("anchored scenario persisted the wrong anchor_id")
            if int(stored.get("center_index", -1)) != int(condition.center_index):
                raise ValueError("anchored scenario persisted the wrong center_index")

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
        if model_name in {*REFERENCE_MODELS, "proposed"}:
            return variable_name == "T"
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
                f"{station_id}_Rs",
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
        if name not in LOCAL_DEEP_MODELS:
            raise ValueError(f"{name!r} is not a local lightweight deep model")
        model_class = BRITSImputer if name == "brits_lite" else SAITSImputer
        expected_features = int(self.data.values.shape[1] * self.data.values.shape[2])
        expected_model_config = (
            {
                "n_features": expected_features,
                "seed": int(seed),
                "hidden_size": 32,
                "consistency_weight": 0.1,
            }
            if name == "brits_lite"
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
        if name == "brits_lite":
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

    def _frozen_curriculum_config(self) -> ProposedCurriculumConfig:
        probabilities = self.frozen_model_design.curriculum_probabilities
        if tuple(name for name, _ in probabilities) != CURRICULUM_SCENARIOS:
            raise ValueError(
                "design freeze curriculum order differs from the implemented protocol"
            )
        return ProposedCurriculumConfig(
            scenario_probabilities=tuple(
                (name, float(probability)) for name, probability in probabilities
            ),
            gap_lengths=self.frozen_model_design.curriculum_gap_lengths,
            unseen_length_max_days=(
                self.frozen_model_design.unseen_length_train_max_days
            ),
        )

    def _reference_model_kwargs(self, model_name: str) -> dict[str, Any]:
        frozen = self.frozen_model_design.protocol_for(model_name)
        implementation = str(frozen.pop("implementation", ""))
        if implementation != "pypots_1.5_official_core":
            raise ValueError(
                f"{model_name} must use the frozen official PyPOTS 1.5 core"
            )
        if model_name == "brits_ref":
            if float(frozen.pop("target_only_MIT_weight", float("nan"))) != 1.0:
                raise ValueError("brits_ref target-only MIT weight must be 1.0")
            expected = {"rnn_hidden_size"}
            kwargs = {"rnn_hidden_size": int(frozen["rnn_hidden_size"])}
        elif model_name == "saits_ref":
            expected = {
                "n_layers",
                "d_model",
                "n_heads",
                "d_k",
                "d_v",
                "d_ffn",
                "dropout",
                "attention_dropout",
                "ORT_weight",
                "MIT_weight",
            }
            kwargs = {
                "n_layers": int(frozen["n_layers"]),
                "d_model": int(frozen["d_model"]),
                "n_heads": int(frozen["n_heads"]),
                "d_k": int(frozen["d_k"]),
                "d_v": int(frozen["d_v"]),
                "d_ffn": int(frozen["d_ffn"]),
                "dropout": float(frozen["dropout"]),
                "attn_dropout": float(frozen["attention_dropout"]),
                "diagonal_attention_mask": True,
                "ORT_weight": float(frozen["ORT_weight"]),
                "MIT_weight": float(frozen["MIT_weight"]),
            }
        elif model_name == "csdi":
            frozen.pop("validation_samples", None)
            frozen.pop("formal_prediction_samples", None)
            expected = {
                "n_layers",
                "n_heads",
                "n_channels",
                "time_embedding_size",
                "feature_embedding_size",
                "diffusion_embedding_size",
                "diffusion_steps",
                "schedule",
                "beta_start",
                "beta_end",
                "target_strategy",
                "unconditional",
            }
            kwargs = {
                "n_layers": int(frozen["n_layers"]),
                "n_heads": int(frozen["n_heads"]),
                "n_channels": int(frozen["n_channels"]),
                "d_time_embedding": int(frozen["time_embedding_size"]),
                "d_feature_embedding": int(frozen["feature_embedding_size"]),
                "d_diffusion_embedding": int(frozen["diffusion_embedding_size"]),
                "n_diffusion_steps": int(frozen["diffusion_steps"]),
                "target_strategy": str(frozen["target_strategy"]),
                "is_unconditional": bool(frozen["unconditional"]),
                "schedule": str(frozen["schedule"]),
                "beta_start": float(frozen["beta_start"]),
                "beta_end": float(frozen["beta_end"]),
            }
        else:
            raise ValueError(f"{model_name!r} is not a reference model")
        unexpected = sorted(set(frozen).difference(expected))
        missing = sorted(expected.difference(frozen))
        if missing or unexpected:
            raise ValueError(
                f"frozen {model_name} protocol mismatch: "
                f"missing={missing}, unexpected={unexpected}"
            )
        return kwargs

    def _reference_training_config(self, seed: int) -> ReferenceTrainingConfig:
        common = self.frozen_model_design.common_training
        csdi = self.frozen_model_design.protocol_for("csdi")
        return ReferenceTrainingConfig(
            epochs=self.training_settings["deep_epochs"],
            patience=self.training_settings["deep_patience"],
            batch_size=self.training_settings["batch_size"],
            learning_rate=float(common["learning_rate"]),
            weight_decay=float(common["weight_decay"]),
            min_delta=float(common["minimum_delta"]),
            gradient_clip=float(common["gradient_clip"]),
            seed=int(seed),
            device=self.training_settings["device"],
            validation_sampling_times=int(csdi["validation_samples"]),
            prediction_sampling_times=(
                int(csdi["formal_prediction_samples"])
                if self.training_profile_name == "formal"
                else int(csdi["validation_samples"])
            ),
        )

    def _reference_protocol(
        self, seed: int, window: int, protocol: str
    ) -> ReferenceProtocolData:
        key = (int(seed), int(window), str(protocol))
        if key not in self._reference_protocol_cache:
            train_values = self.data.values[self.train_rows]
            validation_values = self.data.values[self.validation_rows]
            train_eligible = (
                self.data.natural_observed[self.train_rows]
                & self.data.quality_approved[self.train_rows]
                & np.isfinite(train_values)
            )
            validation_eligible = (
                self.data.natural_observed[self.validation_rows]
                & self.data.quality_approved[self.validation_rows]
                & np.isfinite(validation_values)
            )
            self._reference_protocol_cache[key] = build_reference_protocol_data(
                train_values,
                validation_values,
                variable_names=self.data.variable_names,
                station_ids=self.data.station_ids,
                train_eligible=train_eligible,
                validation_eligible=validation_eligible,
                window_size=int(window),
                protocol=str(protocol),
                seed=int(seed),
                train_mask_repeats=self.training_settings["train_mask_repeats"],
                validation_mask_repeats=self.training_settings[
                    "validation_mask_repeats"
                ],
                curriculum_config=self._frozen_curriculum_config(),
            )
        return self._reference_protocol_cache[key]

    def _reference_contract(
        self, model_name: str, seed: int, window: int, protocol: str
    ) -> tuple[
        ReferenceProtocolData,
        dict[str, Any],
        ReferenceTrainingConfig,
        dict[str, Any],
    ]:
        reference_protocol = self._reference_protocol(seed, window, protocol)
        model_kwargs = self._reference_model_kwargs(model_name)
        adapter_config = {
            "n_steps": reference_protocol.window_size,
            "n_features": reference_protocol.train.n_features,
            "model_kwargs": model_kwargs,
        }
        training_config = self._reference_training_config(seed)
        context = {
            "implementation": REFERENCE_IMPLEMENTATION,
            "formal_model_name": model_name,
            "adapter_model_name": _reference_adapter_name(model_name),
            "profile": self.training_profile_name,
            "training_budget_source": (
                "design_freeze"
                if self.training_profile_name == "formal"
                else "smoke_profile"
            ),
            "design_version": self.frozen_model_design.design_version,
            "protocol_fingerprint": reference_protocol.fingerprint,
            "protocol_metadata": reference_protocol.metadata,
            "curriculum_config": reference_protocol.curriculum_config,
            "input_files": self._training_input_identities(),
        }
        return reference_protocol, adapter_config, training_config, context

    def _reference_checkpoint_path(
        self, model_name: str, seed: int, window: int, protocol: str
    ) -> Path:
        return (
            self.output_dir
            / "checkpoints"
            / f"{model_name}-S{seed}-W{window}-{protocol}.pt"
        )

    @staticmethod
    def _quarantine_reference_checkpoint_files(checkpoint: Path) -> Path | None:
        quarantined = _quarantine_file(checkpoint)
        _quarantine_file(Path(str(checkpoint) + ".sha256"))
        return quarantined

    def _reference_model(
        self, model_name: str, seed: int, window: int, protocol: str
    ) -> PyPOTSReferenceImputer:
        key = (model_name, int(seed), int(window), str(protocol))
        if key in self._reference_cache:
            return self._reference_cache[key]
        reference_protocol, adapter_config, training_config, _ = (
            self._reference_contract(model_name, seed, window, protocol)
        )
        checkpoint = self._reference_checkpoint_path(model_name, seed, window, protocol)
        sidecar = Path(str(checkpoint) + ".sha256")
        if self.resume and (checkpoint.exists() or sidecar.exists()):
            try:
                model = PyPOTSReferenceImputer.load_checkpoint(
                    checkpoint,
                    expected_model_name=_reference_adapter_name(model_name),
                    expected_protocol_fingerprint=reference_protocol.fingerprint,
                    expected_adapter_config=adapter_config,
                    expected_training_config=asdict(training_config),
                )
            except (
                EOFError,
                OSError,
                KeyError,
                TypeError,
                ValueError,
                pickle.UnpicklingError,
            ):
                self._quarantine_reference_checkpoint_files(checkpoint)
            else:
                self._reference_cache[key] = model
                return model
        model = PyPOTSReferenceImputer(
            _reference_adapter_name(model_name),
            adapter_config["n_steps"],
            adapter_config["n_features"],
            model_kwargs=adapter_config["model_kwargs"],
        )
        model.fit(reference_protocol, training_config)
        model.save_checkpoint(checkpoint)
        self._reference_cache[key] = model
        return model

    def _proposed_batches(
        self,
        model_values: np.ndarray,
        rows: np.ndarray,
        artificial_flat: np.ndarray | None,
        window: int,
        *,
        curriculum_config: ProposedCurriculumConfig | None = None,
        curriculum_seed: int | None = None,
        protocol: str | None = None,
        repeats: int = 1,
        validation_scenario: ValidationScenario | None = None,
    ) -> list[dict[str, Any]]:
        values = model_values[rows]
        natural = self.data.natural_observed[rows]
        quality = self.data.quality_approved[rows]
        seasonal = self.data.seasonal_features[rows]
        climatology = self._proposed_training_climatology()[rows]
        if len(values) < 1:
            raise ValueError("proposed batches require at least one selected row")
        window = min(int(window), len(values))
        starts = _window_starts(len(values), window)
        target = self.data.variable_names.index("T")
        if (
            isinstance(repeats, (bool, np.bool_))
            or not isinstance(repeats, (int, np.integer))
            or int(repeats) < 1
        ):
            raise ValueError("repeats must be a positive integer")
        repeats = int(repeats)

        batches: list[dict[str, Any]] = []
        if artificial_flat is not None:
            if (
                curriculum_seed is not None
                or protocol is not None
                or validation_scenario is not None
                or curriculum_config is not None
                or repeats != 1
            ):
                raise ValueError(
                    "fixed artificial masks cannot be combined with curriculum options"
                )
            artificial = np.asarray(artificial_flat, dtype=bool).reshape(values.shape)
            schedule: tuple[str, ...] = tuple("fixed_mask" for _ in starts)
        else:
            if curriculum_seed is None or protocol is None:
                raise ValueError(
                    "curriculum_seed and protocol are required for curriculum batches"
                )
            curriculum_config = curriculum_config or ProposedCurriculumConfig()
            batch_count = len(starts) * repeats
            schedule = (
                tuple(validation_scenario for _ in range(batch_count))
                if validation_scenario is not None
                else sample_curriculum_scenarios(
                    batch_count, curriculum_seed, curriculum_config
                )
            )

        schedule_index = 0
        for repeat in range(repeats):
            for start in starts:
                end = start + window
                if artificial_flat is None:
                    mask_seed = int(
                        np.random.SeedSequence(
                            [int(curriculum_seed), repeat, schedule_index]
                        ).generate_state(1, dtype=np.uint32)[0]
                    )
                    eligible = (
                        natural[start:end]
                        & quality[start:end]
                        & np.isfinite(values[start:end])
                    )
                    generated = generate_curriculum_mask(
                        eligible,
                        self.data.variable_names,
                        scenario=schedule[schedule_index],
                        protocol=str(protocol),
                        seed=mask_seed,
                        config=curriculum_config,
                    )
                    artificial_window = generated.artificial_mask
                    metadata = {
                        **generated.metadata,
                        "window_start": int(start),
                        "window_end": int(end - 1),
                        "window_length": int(window),
                        "repeat": int(repeat),
                    }
                else:
                    artificial_window = artificial[start:end]
                    metadata = {
                        "training_mask_type": "fixed_mask",
                        "training_gap_length": None,
                        "training_pattern": "fixed_external_mask",
                        "training_station_count": int(
                            artificial_window[..., target].any(axis=0).sum()
                        ),
                        "training_masked_cells": int(artificial_window.sum()),
                        "training_target_masked_cells": int(
                            artificial_window[..., target].sum()
                        ),
                        "validation_scenario": None,
                        "window_start": int(start),
                        "window_end": int(end - 1),
                        "window_length": int(window),
                        "repeat": 0,
                    }
                schedule_index += 1
                if not artificial_window[..., target].any():
                    continue
                batch: dict[str, Any] = {
                    "values": torch.from_numpy(values[start:end]).unsqueeze(0),
                    "natural_mask": torch.from_numpy(natural[start:end]).unsqueeze(0),
                    "artificial_mask": torch.from_numpy(artificial_window).unsqueeze(0),
                    "target": torch.from_numpy(values[start:end, :, target]).unsqueeze(
                        0
                    ),
                    "quality_mask": torch.from_numpy(
                        quality[start:end, :, target]
                    ).unsqueeze(0),
                    "seasonal_features": torch.from_numpy(
                        seasonal[start:end]
                    ).unsqueeze(0),
                    "training_climatology": torch.from_numpy(
                        climatology[start:end]
                    ).unsqueeze(0),
                    "training_mask_type": metadata["training_mask_type"],
                    "curriculum_metadata": metadata,
                }
                if metadata.get("validation_scenario") is not None:
                    batch["validation_scenario"] = metadata["validation_scenario"]
                batches.append(batch)
        if not batches:
            raise ValueError(
                "proposed batch construction produced no masked target cells"
            )
        return batches

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
                    # Sensitivity versions may intentionally remove an input
                    # channel (for example B1 L). Its values remain missing and
                    # the neutral scaler prevents an artificial imputation.
                    mean[station, variable] = 0.0
                    scale[station, variable] = 1.0
                else:
                    mean[station, variable] = float(selected.mean())
                    standard_deviation = float(selected.std())
                    scale[station, variable] = (
                        standard_deviation if standard_deviation >= 1e-6 else 1.0
                    )
        self._proposed_scale_cache = (mean, scale)
        return self._proposed_scale_cache

    def _proposed_training_climatology(self) -> np.ndarray:
        """Return train-only T climatology on the proposed model's target scale."""

        if self._proposed_climatology_cache is not None:
            return self._proposed_climatology_cache
        target = self.data.variable_names.index("T")
        mean, scale = self._proposed_scaler()
        climatology = np.column_stack(
            [
                self._climatology(station, target)[1]
                for station in range(len(self.data.station_ids))
            ]
        ).astype(np.float32)
        climatology = (climatology - mean[:, target][None, :]) / scale[:, target][
            None, :
        ]
        self._proposed_climatology_cache = climatology.astype(np.float32)
        return self._proposed_climatology_cache

    def _proposed_contract(
        self, seed: int, window: int, protocol: str
    ) -> tuple[ProposedModelConfig, ProposedTrainingConfig, dict[str, Any]]:
        frozen = self.frozen_model_design.protocol_for("proposed")
        common = self.frozen_model_design.common_training
        required = {
            "architecture_version",
            "hidden_size",
            "station_embedding_size",
            "variable_embedding_size",
            "temporal_bidirectional_size_per_direction",
            "dropout",
            "quantiles",
        }
        missing = sorted(required.difference(frozen))
        if missing:
            raise ValueError(f"frozen proposed protocol is incomplete: {missing}")
        if int(frozen["temporal_bidirectional_size_per_direction"]) * 2 != int(
            frozen["hidden_size"]
        ):
            raise ValueError(
                "frozen proposed temporal bidirectional size must be half hidden_size"
            )
        frozen_quantiles = tuple(float(value) for value in frozen["quantiles"])
        if frozen_quantiles != MissingAwareMultisourceImputer.quantile_levels:
            raise ValueError(
                "frozen proposed quantiles differ from the implemented architecture"
            )
        return (
            ProposedModelConfig(
                station_ids=self.data.station_ids,
                variable_names=self.data.variable_names,
                hidden_size=int(frozen["hidden_size"]),
                station_embedding_size=int(frozen["station_embedding_size"]),
                variable_embedding_size=int(frozen["variable_embedding_size"]),
                dropout=float(frozen["dropout"]),
                architecture_version=str(frozen["architecture_version"]),
            ),
            ProposedTrainingConfig(
                epochs=self.training_settings["proposed_epochs"],
                learning_rate=float(common["learning_rate"]),
                weight_decay=float(common["weight_decay"]),
                patience=self.training_settings["proposed_patience"],
                min_delta=float(common["minimum_delta"]),
                gradient_clip=float(common["gradient_clip"]),
                seed=seed,
                device=self.training_settings["device"],
                curriculum=self._frozen_curriculum_config(),
            ),
            {
                "profile": self.training_profile_name,
                "training_budget_source": (
                    "design_freeze"
                    if self.training_profile_name == "formal"
                    else "smoke_profile"
                ),
                "design_version": self.frozen_model_design.design_version,
                "frozen_common_training": dict(common),
                "frozen_model_protocol": frozen,
                "train_mask_repeats": self.training_settings["train_mask_repeats"],
                "validation_mask_repeats": self.training_settings[
                    "validation_mask_repeats"
                ],
                "window": int(window),
                "effective_window": min(
                    int(window),
                    int(self.train_rows.sum()),
                    int(self.validation_rows.sum()),
                ),
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
        if (
            tuple(model.config.station_ids) != self.data.station_ids
            or tuple(model.config.variable_names) != self.data.variable_names
        ):
            raise _CheckpointRetrainingRequired(
                f"proposed checkpoint {checkpoint} axes do not match the current data; "
                "retrain it",
                reason_code="checkpoint_incompatible_axes",
            )
        try:
            stored_quantile_levels = tuple(
                float(value) for value in checkpoint_metadata.get("quantile_levels", ())
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
                self._load_proposed_model_checkpoint(checkpoint, seed, window, protocol)
            )
            self._proposed_checkpoint_metadata[key] = checkpoint_metadata
            self._proposed_cache[key] = (model, mean, scale)
            return self._proposed_cache[key]
        mean, scale = self._proposed_scaler()
        normalized_values = (self.data.values - mean[None]) / scale[None]
        effective_window = min(
            window,
            int(self.train_rows.sum()),
            int(self.validation_rows.sum()),
        )
        train_window = effective_window
        validation_window = effective_window
        training_config = expected_training_config
        train_batches = self._proposed_batches(
            normalized_values,
            self.train_rows,
            None,
            train_window,
            curriculum_config=training_config.curriculum,
            curriculum_seed=seed,
            protocol=protocol,
            repeats=self.training_settings["train_mask_repeats"],
        )
        if tuple(training_config.curriculum.validation_scenarios) != tuple(
            FROZEN_VALIDATION_SCENARIOS
        ):
            raise ValueError(
                "proposed validation scenarios do not match the frozen design"
            )
        validation_batches: list[dict[str, Any]] = []
        for scenario_index, validation_scenario in enumerate(
            FROZEN_VALIDATION_SCENARIOS
        ):
            validation_batches.extend(
                self._proposed_batches(
                    normalized_values,
                    self.validation_rows,
                    None,
                    validation_window,
                    curriculum_config=training_config.curriculum,
                    curriculum_seed=seed + 10_000 + scenario_index,
                    protocol=protocol,
                    repeats=self.training_settings["validation_mask_repeats"],
                    validation_scenario=validation_scenario,
                )
            )
        set_deterministic_seed(seed)
        model = MissingAwareMultisourceImputer(expected_model_config)
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
        if model_name in LOCAL_DEEP_MODELS:
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
        if model_name in REFERENCE_MODELS:
            model = self._reference_model(
                model_name, seed, condition.window_length, condition.training_protocol
            )
            reference_protocol = self._reference_protocol(
                seed, condition.window_length, condition.training_protocol
            )
            available = (
                self.data.natural_observed
                & self.data.quality_approved
                & np.isfinite(self.data.values)
            )
            reference_values = np.where(available, self.data.values, np.nan).astype(
                np.float32
            )
            flat = reference_values.reshape(len(reference_values), -1)
            flat_mask = artificial_mask.reshape(len(artificial_mask), -1)
            prediction_sum = np.zeros(flat.shape, dtype=np.float64)
            prediction_count = np.zeros(flat.shape, dtype=np.int16)
            sample_sum: np.ndarray | None = None
            total_inference_seconds = 0.0
            draws = self._reference_training_config(seed).prediction_sampling_times
            window = reference_protocol.window_size
            for start in _window_starts(len(flat), window):
                end = start + window
                window_mask = flat_mask[start:end]
                if not window_mask.any():
                    continue
                prediction_seed = int(
                    np.random.SeedSequence(
                        [seed, int(scenario.mask_seed), int(start)]
                    ).generate_state(1, dtype=np.uint32)[0]
                )
                output = model.predict(
                    flat[None, start:end],
                    window_mask[None],
                    n_sampling_times=draws,
                    seed=prediction_seed,
                )
                point = np.asarray(output.point[0], dtype=float)
                prediction_sum[start:end] += np.where(window_mask, point, 0.0)
                prediction_count[start:end] += window_mask
                total_inference_seconds += float(output.inference_time_seconds)
                if model_name == "csdi":
                    if output.samples is None or output.samples.shape[1] != draws:
                        raise RuntimeError(
                            "official CSDI did not return the frozen sampling budget"
                        )
                    if sample_sum is None:
                        sample_sum = np.zeros((draws, *flat.shape), dtype=np.float32)
                    samples = np.asarray(output.samples[0], dtype=np.float32)
                    sample_sum[:, start:end] += np.where(
                        window_mask[None], samples, 0.0
                    )
            if np.any(flat_mask & (prediction_count == 0)):
                raise RuntimeError(
                    "windowed reference prediction did not cover every hidden cell"
                )
            predicted_flat = np.full(flat.shape, np.nan, dtype=float)
            predicted_flat[flat_mask] = (
                prediction_sum[flat_mask] / prediction_count[flat_mask]
            )
            quantile_result: dict[str, np.ndarray] | None = None
            if model_name == "csdi":
                if sample_sum is None:
                    raise RuntimeError("official CSDI produced no sampled windows")
                averaged_samples = np.full(sample_sum.shape, np.nan, dtype=np.float32)
                for draw in range(draws):
                    averaged_samples[draw][flat_mask] = (
                        sample_sum[draw][flat_mask] / prediction_count[flat_mask]
                    )
                levels = (0.05, 0.25, 0.50, 0.75, 0.95)
                selected_quantiles = np.quantile(
                    averaged_samples[:, flat_mask], levels, axis=0
                )
                quantile_result = {}
                for index, name in enumerate(("q05", "q25", "q50", "q75", "q95")):
                    values = np.full(flat.shape, np.nan, dtype=float)
                    values[flat_mask] = selected_quantiles[index]
                    quantile_result[name] = values.reshape(self.data.values.shape)
                predicted_flat[flat_mask] = selected_quantiles[2]
            key = (
                model_name,
                seed,
                condition.window_length,
                condition.training_protocol,
            )
            self._reference_inference_seconds[key] = (
                self._reference_inference_seconds.get(key, 0.0)
                + total_inference_seconds
            )
            self._reference_last_run_diagnostics[key] = {
                **dict(model.diagnostics_),
                "inference_time_seconds": total_inference_seconds,
                "cumulative_inference_time_seconds": (
                    self._reference_inference_seconds[key]
                ),
                "protocol_fingerprint": reference_protocol.fingerprint,
            }
            return predicted_flat.reshape(self.data.values.shape), quantile_result
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
        diagnostic_names = (
            "source_available_A",
            "source_available_B",
            "source_available_C",
            "source_available_D",
            "gate_A",
            "gate_B",
            "gate_C",
            "gate_D",
        )
        diagnostic_sum = np.zeros(
            (*target_hidden.shape, len(diagnostic_names)), dtype=float
        )
        prediction_count = np.zeros_like(target_hidden, dtype=np.int16)
        training_climatology = self._proposed_training_climatology()
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
            climatology = torch.from_numpy(training_climatology[None, start:end])
            with torch.no_grad():
                output = model(
                    values,
                    natural,
                    artificial,
                    seasonal_features=seasonal,
                    training_climatology=climatology,
                )
            window_quantiles = output["quantiles"][0].detach().cpu().numpy()
            window_diagnostics = np.stack(
                [
                    output[name][0].detach().cpu().numpy().astype(float)
                    for name in diagnostic_names
                ],
                axis=-1,
            )
            window_quantiles = (
                window_quantiles * scale[:, target_index][None, :, None]
                + mean[:, target_index][None, :, None]
            )
            quantile_sum[start:end] += np.where(
                window_hidden[..., None], window_quantiles, 0.0
            )
            diagnostic_sum[start:end] += np.where(
                window_hidden[..., None], window_diagnostics, 0.0
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
        result = {
            "q05": quantiles[..., 0],
            "q25": quantiles[..., 1],
            "q50": quantiles[..., 2],
            "q75": quantiles[..., 3],
            "q95": quantiles[..., 4],
        }
        for index, name in enumerate(diagnostic_names):
            values = np.full(target_hidden.shape, np.nan, dtype=float)
            values[target_hidden] = (
                diagnostic_sum[..., index][target_hidden]
                / prediction_count[target_hidden]
            )
            result[name] = (
                values >= 0.5 if name.startswith("source_available_") else values
            )
        return prediction, result

    def _model_diagnostic_fields(
        self,
        model_name: str,
        training_seed: int | None,
        scenario: ExperimentScenario,
    ) -> dict[str, Any]:
        try:
            category = self.frozen_model_design.category_for(model_name)
        except ValueError:
            category = "exploratory"
        fields: dict[str, Any] = {"model_registry_category": category}
        if training_seed is None:
            return fields
        condition = scenario.condition
        key = (
            int(training_seed),
            condition.window_length,
            condition.training_protocol,
        )
        if model_name in REFERENCE_MODELS:
            model_key = (model_name, *key)
            model = self._reference_cache.get(model_key)
            if model is None:
                return fields
            diagnostics = self._reference_last_run_diagnostics.get(
                model_key, dict(model.diagnostics_)
            )
            validation_score = diagnostics.get("best_validation_score")
            checkpoint = self._reference_checkpoint_path(model_name, *key)
            fields.update(
                {
                    "reference_implementation": REFERENCE_IMPLEMENTATION,
                    "reference_model_name": _reference_adapter_name(model_name),
                    "reference_protocol_fingerprint": model.protocol_fingerprint_,
                    "reference_checkpoint_sha256": (
                        (_file_identity(checkpoint) or {}).get("sha256")
                    ),
                    "reference_checkpoint_sidecar_sha256": (
                        (_file_identity(Path(str(checkpoint) + ".sha256")) or {}).get(
                            "sha256"
                        )
                    ),
                    "parameter_count": diagnostics.get("parameter_count"),
                    "best_epoch": diagnostics.get("best_epoch"),
                    "epochs_run": diagnostics.get("epochs_run"),
                    "hit_epoch_limit": diagnostics.get("hit_epoch_limit"),
                    "validation_score_by_scenario": json.dumps(
                        diagnostics.get("validation_score_by_scenario", {}),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "finite_predictions": True,
                    "finite_validation_score": bool(
                        validation_score is not None
                        and np.isfinite(float(validation_score))
                    ),
                    "training_time_seconds": diagnostics.get("training_time_seconds"),
                    "inference_time_seconds": diagnostics.get("inference_time_seconds"),
                    "cumulative_inference_time_seconds": diagnostics.get(
                        "cumulative_inference_time_seconds"
                    ),
                }
            )
        elif model_name == "proposed":
            metadata = self._proposed_checkpoint_metadata.get(key, {})
            history = list(metadata.get("history", ()))
            best_epoch = metadata.get("best_epoch", metadata.get("epoch"))
            selected_history = next(
                (
                    row
                    for row in history
                    if int(float(row.get("epoch", -1))) == int(best_epoch or -1)
                ),
                {},
            )
            by_scenario = {
                scenario_name: selected_history.get(f"validation_{scenario_name}_loss")
                for scenario_name in FROZEN_VALIDATION_SCENARIOS
                if selected_history.get(f"validation_{scenario_name}_loss") is not None
            }
            validation_score = metadata.get(
                "best_validation_score", metadata.get("best_validation_loss")
            )
            cached = self._proposed_cache.get(key)
            fields.update(
                {
                    "parameter_count": (
                        sum(parameter.numel() for parameter in cached[0].parameters())
                        if cached is not None
                        else None
                    ),
                    "best_epoch": best_epoch,
                    "epochs_run": metadata.get("epochs_run"),
                    "hit_epoch_limit": metadata.get("hit_epoch_limit"),
                    "validation_score_by_scenario": json.dumps(
                        by_scenario, sort_keys=True, separators=(",", ":")
                    ),
                    "finite_predictions": True,
                    "finite_validation_score": bool(
                        validation_score is not None
                        and np.isfinite(float(validation_score))
                    ),
                }
            )
        return fields

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
        run_key = (
            f"{model_name}:none"
            if training_seed is None
            else f"{model_name}:{training_seed}"
        )
        unsupported_rows = [
            {
                "run_key": run_key,
                "model": model_name,
                "training_seed": training_seed,
                "station_id": self.data.station_ids[station],
                "target": variable_name,
                "reason_code": "unsupported_model_target",
                "reason": f"{model_name} does not estimate target {variable_name}",
            }
            for station in station_indices
            for variable_name in evaluation_variables
            if artificial_mask[
                :, station, self.data.variable_names.index(variable_name)
            ].any()
            and not self._supports_target(model_name, variable_name)
        ]
        has_supported_target = any(
            artificial_mask[
                :, station, self.data.variable_names.index(variable_name)
            ].any()
            and self._supports_target(model_name, variable_name)
            for station in station_indices
            for variable_name in evaluation_variables
        )
        if not has_supported_target:
            return pd.DataFrame(), pd.DataFrame(), unsupported_rows
        shared_prediction, quantiles = self._model_prediction(
            model_name, training_seed, scenario, artificial_mask
        )
        model_diagnostic_fields = self._model_diagnostic_fields(
            model_name, training_seed, scenario
        )
        daily_parts: list[pd.DataFrame] = []
        event_rows: list[dict[str, Any]] = []
        skipped_rows: list[dict[str, Any]] = []
        is_loso = scenario.condition.mask_type == "loso"
        fit_split = "train_other_stations" if is_loso else "train"
        tuning_split = "validation_other_stations" if is_loso else "validation"
        evaluation_split = scenario.condition.evaluation_split
        evidence_role = self._evidence_role(evaluation_split)
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
                if not self._supports_target(model_name, variable_name):
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
                    if quantiles is None:
                        q = None
                    else:
                        q = {}
                        for name, values in quantiles.items():
                            array = np.asarray(values)
                            if array.ndim == 3:
                                q[name] = array[:, station, variable]
                            elif array.ndim == 2:
                                q[name] = array[:, station]
                            else:
                                raise ValueError(
                                    f"prediction diagnostic {name!r} has an invalid shape"
                                )
                metric_quantiles = (
                    {name: q[name] for name in ("q05", "q25", "q50", "q75", "q95")}
                    if q is not None
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
                    else (str(metadata["target_gap_id"]))
                    if scenario.condition.mask_type == "async"
                    and scenario.condition.anchor_id is not None
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
                    "async_axis": scenario.condition.async_axis,
                    "anchor_id": scenario.condition.anchor_id,
                    "anchor_target": scenario.condition.anchor_target,
                    "anchor_mask_seed": scenario.condition.anchor_mask_seed,
                    "center_date": scenario.condition.center_date,
                    "center_index": scenario.condition.center_index,
                    "anchor_data_version": scenario.condition.anchor_data_version,
                    "anchor_evaluation_split": (
                        scenario.condition.anchor_evaluation_split
                    ),
                    "anchor_source_split": scenario.condition.anchor_source_split,
                    "anchor_max_supported_length": (
                        scenario.condition.anchor_max_supported_length
                    ),
                    "anchor_start_month": scenario.condition.anchor_start_month,
                    "anchor_season": scenario.condition.anchor_season,
                    "anchor_year": scenario.condition.anchor_year,
                    "anchor_hydrologic_state": (
                        scenario.condition.anchor_hydrologic_state
                    ),
                    "event_type": scenario.condition.event_type,
                    "window_length": scenario.condition.window_length,
                    "model_window_length": scenario.condition.window_length,
                    "training_protocol": scenario.condition.training_protocol,
                    "held_out_station": scenario.condition.held_out_station,
                    "validation_scope": scenario.condition.validation_scope,
                    "data_version": self.data.data_version,
                    "evaluation_split": evaluation_split,
                    "evidence_role": evidence_role,
                    "formal_evidence": self.formal_evidence,
                    "design_version": self.evidence_contract["design_version"],
                    "design_hash": self.evidence_contract["design_hash"],
                    "mask_schema_version": self.evidence_contract[
                        "mask_schema_version"
                    ],
                    "model_schema_version": self.evidence_contract[
                        "model_schema_version"
                    ],
                    "statistics_schema_version": self.evidence_contract[
                        "statistics_schema_version"
                    ],
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
                    **{
                        name: getattr(scenario.condition, name)
                        for name in EVENT_DESIGN_FIELD_NAMES
                    },
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
                    quantile_predictions=metric_quantiles,
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
                        "evaluation_split": evaluation_split,
                        "evidence_role": evidence_role,
                        "formal_evidence": self.formal_evidence,
                        "external_validation_status": self.grid.external_validation_status,
                        "is_external_validation": evaluation_split == "confirmatory",
                        **design_fields,
                        **reference_fields,
                        **model_diagnostic_fields,
                    }
                )
                if scenario.condition.event_window_length is not None:
                    event_row["window_length"] = scenario.condition.event_window_length
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
                        "source_available_A": (
                            q["source_available_A"][positions]
                            if q and "source_available_A" in q
                            else np.nan
                        ),
                        "source_available_B": (
                            q["source_available_B"][positions]
                            if q and "source_available_B" in q
                            else np.nan
                        ),
                        "source_available_C": (
                            q["source_available_C"][positions]
                            if q and "source_available_C" in q
                            else np.nan
                        ),
                        "source_available_D": (
                            q["source_available_D"][positions]
                            if q and "source_available_D" in q
                            else np.nan
                        ),
                        "gate_A": (
                            q["gate_A"][positions] if q and "gate_A" in q else np.nan
                        ),
                        "gate_B": (
                            q["gate_B"][positions] if q and "gate_B" in q else np.nan
                        ),
                        "gate_C": (
                            q["gate_C"][positions] if q and "gate_C" in q else np.nan
                        ),
                        "gate_D": (
                            q["gate_D"][positions] if q and "gate_D" in q else np.nan
                        ),
                        "season": seasons,
                        "event_type": scenario.condition.event_type,
                        "quality_approved": quality[positions],
                        "artificial_mask": hidden[positions],
                        "external_validation_status": self.grid.external_validation_status,
                        "is_external_validation": evaluation_split == "confirmatory",
                        **design_fields,
                        **reference_fields,
                        **model_diagnostic_fields,
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
        reference_fingerprint: str | None = None
        reference_implementation: str | None = None
        if model_name in LOCAL_DEEP_MODELS:
            _, model_config, training_config = self._deep_contract(
                model_name,
                int(training_seed),
                condition.window_length,
                condition.training_protocol,
            )
            training_context: dict[str, Any] | None = None
        elif model_name in REFERENCE_MODELS:
            (
                reference_protocol,
                model_config,
                reference_training,
                training_context,
            ) = self._reference_contract(
                model_name,
                int(training_seed),
                condition.window_length,
                condition.training_protocol,
            )
            training_config = asdict(reference_training)
            reference_fingerprint = reference_protocol.fingerprint
            reference_implementation = REFERENCE_IMPLEMENTATION
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
            **self.evidence_contract,
            "code_provenance": dict(self.code_provenance),
            "suite": self.grid.suite,
            "training_profile": self.training_profile_name,
            "model": model_name,
            "model_registry_category": (
                self.frozen_model_design.category_for(model_name)
                if model_name != "pooled_loso"
                else "exploratory"
            ),
            "model_config": model_config,
            "training_seed": training_seed,
            "training_config": training_config,
            "training_context": training_context,
            "reference_implementation": reference_implementation,
            "reference_protocol_fingerprint": reference_fingerprint,
            "runner_training_settings": dict(self.training_settings),
            "mask_seed": scenario.mask_seed,
            "window_length": condition.window_length,
            "training_protocol": condition.training_protocol,
            "scenario": json.loads(json.dumps(scenario.as_dict())),
            "input_files": {
                "wide": _file_identity(self.wide_path),
                "quality": _file_identity(self.quality_path),
                "config": _file_identity(self.config_path),
                "design": _file_identity(self.design_path),
                "study_manifest": _file_identity(self.manifest_path),
                "data_version_manifest": _file_identity(
                    self.data_version_manifest_path
                ),
            },
            "mask_files": {
                "axes": _file_identity(self.mask_dir / "axes.json"),
                "mask": _file_identity(scenario_dir / f"{scenario.scenario_id}.npz"),
                "metadata": _file_identity(
                    scenario_dir / f"{scenario.scenario_id}.json"
                ),
            },
            "checkpoint": _file_identity(
                self._checkpoint_path(model_name, training_seed, scenario)
            ),
            "checkpoint_sidecar": _file_identity(
                Path(
                    str(self._checkpoint_path(model_name, training_seed, scenario))
                    + ".sha256"
                )
                if model_name in REFERENCE_MODELS
                else None
            ),
        }
        return json.loads(json.dumps(contract))

    @staticmethod
    def _execution_contract_matches(
        stored: Mapping[str, Any] | None,
        current: Mapping[str, Any],
    ) -> bool:
        """Compare scientific identity while retaining non-invalidating git audit."""

        if not isinstance(stored, Mapping):
            return False
        stored_identity = dict(stored)
        current_identity = dict(current)
        stored_identity.pop("code_provenance", None)
        current_identity.pop("code_provenance", None)
        return stored_identity == current_identity

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
        if model_name in LOCAL_DEEP_MODELS:
            self._deep_cache.pop((model_name, *key), None)
        elif model_name in REFERENCE_MODELS:
            self._reference_cache.pop((model_name, *key), None)
            self._reference_last_run_diagnostics.pop((model_name, *key), None)
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
            if model_name in LOCAL_DEEP_MODELS:
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
            elif model_name in REFERENCE_MODELS:
                reference_protocol, adapter_config, training_config, _ = (
                    self._reference_contract(
                        model_name,
                        int(training_seed),
                        condition.window_length,
                        condition.training_protocol,
                    )
                )
                model = PyPOTSReferenceImputer.load_checkpoint(
                    checkpoint,
                    expected_model_name=_reference_adapter_name(model_name),
                    expected_protocol_fingerprint=reference_protocol.fingerprint,
                    expected_adapter_config=adapter_config,
                    expected_training_config=asdict(training_config),
                )
                self._reference_cache[
                    (
                        model_name,
                        int(training_seed),
                        condition.window_length,
                        condition.training_protocol,
                    )
                ] = model
            elif model_name == "proposed":
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
            else:
                raise ValueError(
                    f"no strict checkpoint validator for trainable model {model_name!r}"
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
        candidate = (
            self._quarantine_reference_checkpoint_files(checkpoint)
            if model_name in REFERENCE_MODELS
            else _quarantine_file(checkpoint)
        )
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
            if (rows := [row for row in skipped_runs if row.get("run_key") == run_key])
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
            contract_matches = self._execution_contract_matches(
                stored_contracts.get(run_key),
                self._run_execution_contract(scenario, model_name, training_seed),
            )
            checkpoint_valid = model_name not in TRAINABLE_MODELS or (
                contract_matches
                and self._strict_checkpoint_valid(scenario, model_name, training_seed)
            )
            if not has_evidence or not contract_matches or not checkpoint_valid:
                invalidated.add(run_key)

        runs_to_reset = invalidated | retryable_run_keys
        for model_name, training_seed in run_keys:
            run_key = (
                f"{model_name}:none"
                if training_seed is None
                else f"{model_name}:{training_seed}"
            )
            if run_key not in runs_to_reset:
                continue
            self._clear_model_cache(scenario, model_name, training_seed)
            completed.discard(run_key)
            terminal_run_keys.discard(run_key)
            stored_contracts.pop(run_key, None)
            daily = _without_run(daily, run_key)
            events = _without_run(events, run_key)
            skipped_runs = [
                row for row in skipped_runs if row.get("run_key") != run_key
            ]

        if daily_path.exists() and runs_to_reset:
            _atomic_parquet(daily, daily_path)
        if event_path.exists() and runs_to_reset:
            _atomic_parquet(events, event_path)

        for model_name, training_seed in run_keys:
            run_key = (
                f"{model_name}:none"
                if training_seed is None
                else f"{model_name}:{training_seed}"
            )
            if run_key in completed:
                continue
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
            if any(row.get("reason_code") in hard_failure_codes for row in new_skips):
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
                    row.get("reason_code") in STRUCTURAL_SKIP_CODES for row in new_skips
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
                self._clear_model_cache(scenario, model_name, training_seed)
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
                "evaluation_split": scenario.condition.evaluation_split,
                "data_version": self.data.data_version,
                "evidence_role": self._evidence_role(
                    scenario.condition.evaluation_split
                ),
                "formal_evidence": self.formal_evidence,
                "validation_scope": scenario.condition.validation_scope,
                "is_external_validation": scenario.condition.evaluation_split
                == "confirmatory",
                **self.evidence_contract,
                "code_provenance": dict(self.code_provenance),
            },
            status_path,
        )
        return "complete" if scenario_complete else "retryable_failure"

    def _aggregate(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        daily_frames = []
        event_frames = []
        scenarios = {scenario.scenario_id: scenario for scenario in self.grid.scenarios}
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
                if run_key in completed and self._execution_contract_matches(
                    contracts.get(run_key),
                    self._run_execution_contract(scenario, model_name, training_seed),
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
                contracted & _frame_run_keys(daily_frame) & _frame_run_keys(event_frame)
            )
            if daily_path.exists():
                selected = np.fromiter(
                    (
                        _stored_run_key(row.model, row.training_seed) in result_run_keys
                        for row in daily_frame[["model", "training_seed"]].itertuples(
                            index=False
                        )
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
                        _stored_run_key(row.model, row.training_seed) in result_run_keys
                        for row in event_frame[["model", "training_seed"]].itertuples(
                            index=False
                        )
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
            checkpoint = self._reference_checkpoint_path(
                model_name, seed, window, protocol
            )
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
                    "checkpoint": _file_identity(checkpoint),
                    "checkpoint_sidecar": None,
                    "checkpoint_contract_valid": checkpoint.is_file(),
                }
            )
        for (model_name, seed, window, protocol), model in sorted(
            self._reference_cache.items()
        ):
            checkpoint = self._reference_checkpoint_path(
                model_name, seed, window, protocol
            )
            sidecar = Path(str(checkpoint) + ".sha256")
            diagnostics = dict(model.diagnostics_)
            diagnostics["cumulative_inference_time_seconds"] = (
                self._reference_inference_seconds.get(
                    (model_name, seed, window, protocol), 0.0
                )
            )
            summaries.append(
                {
                    "model": model_name,
                    "reference_model_name": model.model_name,
                    "reference_implementation": REFERENCE_IMPLEMENTATION,
                    "training_seed": seed,
                    "window": window,
                    "protocol": protocol,
                    "protocol_fingerprint": model.protocol_fingerprint_,
                    "protocol_metadata": dict(model.protocol_metadata_),
                    "adapter_config": {
                        "n_steps": model.n_steps,
                        "n_features": model.n_features,
                        "model_kwargs": dict(model.model_kwargs),
                    },
                    "training_config": dict(model.training_config_),
                    "reference_metadata": dict(model.metadata_),
                    "diagnostics": diagnostics,
                    "parameter_count": diagnostics.get("parameter_count"),
                    "best_epoch": diagnostics.get("best_epoch"),
                    "epochs_run": diagnostics.get("epochs_run"),
                    "hit_epoch_limit": diagnostics.get("hit_epoch_limit"),
                    "validation_score_by_scenario": diagnostics.get(
                        "validation_score_by_scenario", {}
                    ),
                    "training_time_seconds": diagnostics.get("training_time_seconds"),
                    "inference_time_seconds": diagnostics.get(
                        "cumulative_inference_time_seconds"
                    ),
                    "checkpoint": _file_identity(checkpoint),
                    "checkpoint_sidecar": _file_identity(sidecar),
                    "checkpoint_contract_valid": (
                        checkpoint.is_file() and sidecar.is_file()
                    ),
                }
            )
        for (seed, window, protocol), metadata in sorted(
            self._proposed_checkpoint_metadata.items()
        ):
            checkpoint = self._reference_checkpoint_path(
                "proposed", seed, window, protocol
            )
            summaries.append(
                {
                    "model": "proposed",
                    "training_seed": seed,
                    "window": window,
                    "protocol": protocol,
                    "training_config": dict(metadata.get("training_config", {})),
                    "training_context": dict(metadata.get("training_context", {})),
                    "history": list(metadata.get("history", [])),
                    "training_curriculum": dict(
                        metadata.get("training_curriculum", {})
                    ),
                    "validation_curriculum": dict(
                        metadata.get("validation_curriculum", {})
                    ),
                    "best_epoch": metadata.get("best_epoch", metadata.get("epoch")),
                    "epochs_run": metadata.get("epochs_run"),
                    "hit_epoch_limit": metadata.get("hit_epoch_limit"),
                    "checkpoint": _file_identity(checkpoint),
                    "checkpoint_sidecar": None,
                    "checkpoint_contract_valid": checkpoint.is_file(),
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
        if not self.anchor_availability.empty:
            _atomic_csv(
                self.anchor_availability,
                self.output_dir / "anchor_availability.csv",
            )
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
        finite_daily_runs = (
            {
                (str(scenario_id), _stored_run_key(model, training_seed))
                for (scenario_id, model, training_seed), frame in daily.groupby(
                    ["scenario_id", "model", "training_seed"],
                    dropna=False,
                    sort=False,
                )
                if np.isfinite(pd.to_numeric(frame["y_true"], errors="coerce")).all()
                and np.isfinite(pd.to_numeric(frame["y_pred"], errors="coerce")).all()
            }
            if {"y_true", "y_pred"}.issubset(daily.columns)
            else set()
        )
        finite_metric_runs = (
            {
                (str(scenario_id), _stored_run_key(model, training_seed))
                for (scenario_id, model, training_seed), frame in events.groupby(
                    ["scenario_id", "model", "training_seed"],
                    dropna=False,
                    sort=False,
                )
                if np.isfinite(pd.to_numeric(frame["MAE"], errors="coerce")).all()
                and np.isfinite(pd.to_numeric(frame["RMSE"], errors="coerce")).all()
            }
            if {"MAE", "RMSE"}.issubset(events.columns)
            else set()
        )
        expected_run_count = 0
        completed_status_run_count = 0
        grid_complete = True
        expected_run_units: set[str] = set()
        completed_run_units: set[str] = set()
        retryable_run_units: set[str] = set()
        structural_skip_run_units: set[str] = set()
        checkpoint_required_run_units: set[str] = set()
        checkpoint_valid_run_units: set[str] = set()
        checkpoint_validity_cache: dict[tuple[str, int, int, str], bool] = {}
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
            expected_run_units.update(
                f"{scenario.scenario_id}|{run_key}" for run_key in expected_runs
            )
            status_path = (
                self.output_dir / "scenarios" / scenario.scenario_id / "status.json"
            )
            if not status_path.exists():
                grid_complete = False
                continue
            status = json.loads(status_path.read_text(encoding="utf-8"))
            completed_runs = set(status.get("completed_runs", ()))
            scenario_retryable = set(status.get("retryable_run_keys", ()))
            retryable_run_units.update(
                f"{scenario.scenario_id}|{run_key}"
                for run_key in scenario_retryable.intersection(expected_runs)
            )
            completed_runs.difference_update(scenario_retryable)
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
                run_unit = f"{scenario.scenario_id}|{run_key}"
                checkpoint_valid = True
                if (
                    model_name in TRAINABLE_MODELS
                    and training_seed is not None
                    and run_key not in valid_terminal_runs
                ):
                    checkpoint_required_run_units.add(run_unit)
                    checkpoint_key = (
                        model_name,
                        int(training_seed),
                        scenario.condition.window_length,
                        scenario.condition.training_protocol,
                    )
                    if checkpoint_key not in checkpoint_validity_cache:
                        checkpoint_validity_cache[checkpoint_key] = (
                            self._strict_checkpoint_valid(
                                scenario, model_name, training_seed
                            )
                        )
                    checkpoint_valid = checkpoint_validity_cache[checkpoint_key]
                    if checkpoint_valid and run_key in completed_runs:
                        checkpoint_valid_run_units.add(run_unit)
                has_evidence = (
                    scenario.scenario_id,
                    run_key,
                ) in aggregate_runs or run_key in valid_terminal_runs
                if (
                    run_key in completed_runs
                    and has_evidence
                    and checkpoint_valid
                    and self._execution_contract_matches(
                        contracts.get(run_key),
                        self._run_execution_contract(
                            scenario, model_name, training_seed
                        ),
                    )
                ):
                    valid_completed.add(run_key)
                    completed_run_units.add(run_unit)
            structural_skip_run_units.update(
                f"{scenario.scenario_id}|{run_key}"
                for run_key in valid_terminal_runs.intersection(valid_completed)
            )
            completed_status_run_count += len(
                expected_runs.intersection(valid_completed)
            )
            grid_complete &= status.get(
                "status"
            ) == "complete" and expected_runs.issubset(valid_completed)
        del checkpoint_validity_cache
        completed_evidence_run_units = {
            f"{scenario_id}|{run_key}" for scenario_id, run_key in aggregate_runs
        }
        expected_evidence_run_units = expected_run_units - structural_skip_run_units
        finite_prediction_run_units = {
            f"{scenario_id}|{run_key}" for scenario_id, run_key in finite_daily_runs
        }
        finite_event_metric_run_units = {
            f"{scenario_id}|{run_key}" for scenario_id, run_key in finite_metric_runs
        }
        run_unit_complete = expected_run_units == completed_run_units
        evidence_complete = expected_evidence_run_units == completed_evidence_run_units
        finite_predictions = expected_evidence_run_units == finite_prediction_run_units
        finite_event_metrics = (
            expected_evidence_run_units == finite_event_metric_run_units
        )
        checkpoint_contract_complete = (
            checkpoint_required_run_units == checkpoint_valid_run_units
        )
        aggregate_scenarios = {scenario_id for scenario_id, _ in aggregate_runs}
        requires_training_seeds = any(
            model in TRAINABLE_MODELS for model in self.models
        )
        formal_training_seed_complete = not requires_training_seeds or set(
            self.training_seeds
        ) == set(self.grid.training_seeds)
        formal_mask_seed_complete = self.training_profile_name == "smoke" or set(
            self.grid.mask_seeds
        ) == set(range(101, 121))
        run_complete = bool(
            grid_complete
            and run_unit_complete
            and evidence_complete
            and finite_predictions
            and finite_event_metrics
            and checkpoint_contract_complete
        )
        formal_grid_contract_complete = bool(
            self.formal_evidence and self.formal_grid_contract is not None
        )
        formal_design_complete = bool(
            self.formal_evidence
            and run_complete
            and formal_training_seed_complete
            and formal_mask_seed_complete
            and formal_grid_contract_complete
        )
        _atomic_json(
            {
                "suite": self.grid.suite,
                "models": list(self.models),
                "formal_model_candidates": list(
                    self.frozen_model_design.formal_candidates
                ),
                "development_only_models": list(
                    self.frozen_model_design.development_only
                ),
                "model_request_aliases": dict(self.model_request_aliases),
                "training_seeds": list(self.training_seeds),
                "mask_seeds": list(self.grid.mask_seeds),
                "frontier_anchor_catalog_path": (
                    self.grid.frontier_anchor_catalog_path
                ),
                "frontier_anchor_catalog_sha256": (
                    self.grid.frontier_anchor_catalog_sha256
                ),
                "frontier_anchor_count": self.grid.frontier_anchor_count,
                "validation_anchor_catalog_path": (
                    self.grid.validation_anchor_catalog_path
                ),
                "validation_anchor_catalog_sha256": (
                    self.grid.validation_anchor_catalog_sha256
                ),
                "validation_anchor_count": self.grid.validation_anchor_count,
                "validation_anchor_catalog_logical_sha256": (
                    self.grid.validation_anchor_catalog_logical_sha256
                ),
                "validation_anchor_ids": list(self.grid.validation_anchor_ids),
                "anchor_availability_rows": len(self.anchor_availability),
                "anchor_unavailable_rows": (
                    int((~self.anchor_availability["available"]).sum())
                    if not self.anchor_availability.empty
                    else 0
                ),
                "shard_index": shard_index,
                "shard_count": shard_count,
                "selected_scenarios": len(selected),
                "grid_scenario_count": len(self.grid.scenarios),
                "event_catalog_path": self.grid.event_catalog_path,
                "event_catalog_sha256": self.grid.event_catalog_sha256,
                "event_catalog_episode_count": (self.grid.event_catalog_episode_count),
                "event_catalog_analysis_count": (
                    self.grid.event_catalog_analysis_count
                ),
                "expected_run_count": expected_run_count,
                "completed_status_run_count": completed_status_run_count,
                "aggregate_scenario_count": len(aggregate_scenarios),
                "aggregate_run_count": len(aggregate_runs),
                "expected_run_unit_keys": sorted(expected_run_units),
                "expected_run_unit_count": len(expected_run_units),
                "completed_run_unit_keys": sorted(completed_run_units),
                "completed_run_unit_count": len(completed_run_units),
                "retryable_run_keys": sorted(retryable_run_units),
                "retryable_run_unit_keys": sorted(retryable_run_units),
                "retryable_run_unit_count": len(retryable_run_units),
                "structural_skip_run_keys": sorted(structural_skip_run_units),
                "structural_skip_run_unit_keys": sorted(structural_skip_run_units),
                "structural_skip_run_unit_count": len(structural_skip_run_units),
                "expected_evidence_run_unit_keys": sorted(expected_evidence_run_units),
                "expected_evidence_run_unit_count": len(expected_evidence_run_units),
                "completed_evidence_run_unit_keys": sorted(
                    completed_evidence_run_units
                ),
                "completed_evidence_run_unit_count": len(completed_evidence_run_units),
                "finite_prediction_run_unit_keys": sorted(finite_prediction_run_units),
                "finite_prediction_run_unit_count": len(finite_prediction_run_units),
                "finite_event_metric_run_unit_keys": sorted(
                    finite_event_metric_run_units
                ),
                "finite_event_metric_run_unit_count": len(
                    finite_event_metric_run_units
                ),
                "checkpoint_required_run_unit_keys": sorted(
                    checkpoint_required_run_units
                ),
                "checkpoint_required_run_count": len(checkpoint_required_run_units),
                "checkpoint_valid_run_unit_keys": sorted(checkpoint_valid_run_units),
                "checkpoint_valid_run_count": len(checkpoint_valid_run_units),
                "completed_daily_rows": len(daily),
                "completed_event_rows": len(events),
                "run_unit_complete": run_unit_complete,
                "evidence_complete": evidence_complete,
                "finite_predictions": finite_predictions,
                "finite_event_metrics": finite_event_metrics,
                "checkpoint_contract_complete": checkpoint_contract_complete,
                "grid_complete": grid_complete,
                "run_complete": run_complete,
                "complete": formal_design_complete,
                "formal_design_complete": formal_design_complete,
                "formal_training_seed_complete": formal_training_seed_complete,
                "formal_mask_seed_complete": formal_mask_seed_complete,
                "formal_grid_contract_complete": formal_grid_contract_complete,
                "formal_grid_contract": self.formal_grid_contract,
                "expected_mask_seeds": list(range(101, 121)),
                "expected_training_seeds": list(self.grid.training_seeds),
                "status_counts": statuses,
                "fit_split": "train",
                "tuning_split": "validation",
                "evaluation_split": self.evaluation_split,
                "data_version": self.data.data_version,
                "data_version_input_identity": self.data_version_input_identity,
                "evidence_role": self._evidence_role(self.evaluation_split),
                "formal_evidence": self.formal_evidence,
                "formal_execution_authorization": self.formal_authorization,
                "finalized_model_roster": (
                    self.formal_authorization["finalized_model_roster"]
                    if self.formal_authorization is not None
                    else None
                ),
                "expected_formal_models": (
                    list(self.models) if self.formal_evidence else []
                ),
                "is_external_validation": self.evaluation_split == "confirmatory",
                "external_validation_status": self.grid.external_validation_status,
                "loso_scope": "exploratory_internal_not_external_validation",
                "training_profile": self.training_profile_name,
                "training_settings": self.training_settings,
                "training_checkpoints": self._training_checkpoint_summaries(),
                **self.evidence_contract,
                "code_provenance": dict(self.code_provenance),
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
    "CONFIRMATORY_ONCE_PATH_REQUIRED",
    "LEGACY_MODEL_ALIASES",
    "LOCAL_DEEP_MODELS",
    "REFERENCE_MODELS",
    "SUPPORTED_MODELS",
    "TRAINABLE_MODELS",
    "ExperimentRunner",
    "apply_full_artificial_mask",
    "canonical_model_name",
    "make_training_mask",
    "run_experiments",
]
