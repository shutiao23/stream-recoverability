"""Resume-safe unified runner for traditional, deep, and proposed imputers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

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
from stream_recoverability.models.proposed import MissingAwareMultisourceImputer, ProposedModelConfig
from stream_recoverability.models.proposed_training import (
    ProposedTrainingConfig,
    load_proposed_checkpoint,
    train_proposed_model,
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
DAILY_KEY = ["scenario_id", "model", "training_seed", "mask_seed", "date", "station_id", "target"]
EVENT_KEY = ["scenario_id", "model", "training_seed", "mask_seed", "station_id", "target"]


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


def apply_full_artificial_mask(values: np.ndarray, artificial_mask: np.ndarray) -> np.ndarray:
    """Hide every selected cell in a complete date × station × variable mask."""

    values = np.asarray(values)
    mask = np.asarray(artificial_mask)
    if mask.dtype != np.bool_ or mask.shape != values.shape or mask.ndim != 3:
        raise ValueError("artificial_mask must be a 3D boolean array matching values")
    masked = values.copy()
    masked[mask] = np.nan
    return masked


def make_training_mask(values: np.ndarray, seed: int, protocol: str) -> np.ndarray:
    """Create deterministic train/validation block masks for seen/unseen protocols."""

    array = np.asarray(values)
    if array.ndim != 2:
        raise ValueError("training values must have shape [time, feature]")
    if protocol not in {"seen_length", "unseen_length"}:
        raise ValueError("protocol must be seen_length or unseen_length")
    lengths = (10, 30, 90, 180) if protocol == "seen_length" else (10, 30, 90)
    rng = np.random.default_rng(seed)
    result = np.zeros_like(array, dtype=bool)
    finite = np.isfinite(array)
    for feature in range(array.shape[1]):
        requested = lengths[feature % len(lengths)]
        if requested <= len(array):
            candidates = np.flatnonzero(
                np.lib.stride_tricks.sliding_window_view(finite[:, feature], requested).all(axis=1)
            )
        else:
            candidates = np.empty(0, dtype=int)
        if candidates.size:
            start = int(rng.choice(candidates))
            result[start : start + requested, feature] = True
        else:
            candidates = np.flatnonzero(finite[:, feature])
            if candidates.size:
                result[int(rng.choice(candidates)), feature] = True
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
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
    np.savez_compressed(temporary, packed=np.packbits(array.reshape(-1), bitorder="little"))
    temporary.replace(mask_path)
    _atomic_json(dict(metadata), scenario_dir / f"{scenario_id}.json")


def _load_compact_mask(root: Path, scenario_id: str) -> tuple[np.ndarray, dict[str, Any]]:
    axes = json.loads((root / "axes.json").read_text(encoding="utf-8"))
    shape = tuple(int(value) for value in axes["shape"])
    with np.load(root / "scenarios" / f"{scenario_id}.npz", allow_pickle=False) as archive:
        packed = np.asarray(archive["packed"], dtype=np.uint8)
    size = int(np.prod(shape))
    mask = np.unpackbits(packed, bitorder="little", count=size).reshape(shape).astype(bool)
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
    wide = pd.read_parquet(wide_path) if Path(wide_path).suffix.lower() == ".parquet" else pd.read_csv(wide_path)
    required = {"date", "split"}
    if not required.issubset(wide):
        raise KeyError(f"wide data is missing {sorted(required.difference(wide.columns))}")
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
                [pd.to_numeric(wide[f"{station}_{variable}"], errors="coerce") for variable in variables],
                axis=-1,
            )
            for station in stations
        ],
        axis=1,
    ).astype(np.float32)

    natural = np.isfinite(values)
    quality = np.isfinite(values)
    if quality_path is not None and Path(quality_path).exists():
        long = pd.read_parquet(quality_path) if Path(quality_path).suffix.lower() == ".parquet" else pd.read_csv(quality_path)
        required_long = {"date", "station_id", "variable", "quality_approved"}
        if not required_long.issubset(long):
            raise KeyError(f"quality data is missing {sorted(required_long.difference(long.columns))}")
        long = long.copy()
        long["date"] = pd.to_datetime(long["date"]).dt.normalize()
        for station_index, station in enumerate(stations):
            for variable_index, variable in enumerate(variables):
                selected = long.loc[
                    (long["station_id"].astype(str) == station)
                    & (long["variable"].astype(str) == variable)
                ].drop_duplicates("date").set_index("date")
                aligned = selected.reindex(pd.DatetimeIndex(wide["date"]))
                quality[:, station_index, variable_index] = (
                    aligned["quality_approved"].fillna(False).astype(bool).to_numpy()
                )
                natural_column = "natural_observed" if "natural_observed" in aligned else "quality_approved"
                natural[:, station_index, variable_index] = (
                    aligned[natural_column].fillna(False).astype(bool).to_numpy()
                )
    natural &= np.isfinite(values)
    quality &= np.isfinite(values)

    if {"day_of_year_sin", "day_of_year_cos", "month_sin", "month_cos"}.issubset(wide):
        seasonal = wide[["day_of_year_sin", "day_of_year_cos", "month_sin", "month_cos"]].to_numpy(
            dtype=np.float32
        )
    else:
        dates = pd.DatetimeIndex(wide["date"])
        days = np.where(dates.is_leap_year, 366.0, 365.0)
        day_phase = 2 * np.pi * (dates.dayofyear.to_numpy() - 1) / days
        month_phase = 2 * np.pi * (dates.month.to_numpy() - 1) / 12.0
        seasonal = np.column_stack(
            (np.sin(day_phase), np.cos(day_phase), np.sin(month_phase), np.cos(month_phase))
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
        self.variable_names = tuple(self.config.get("all_variables", ("T", "F", "L", "Ta", "P", "W", "RH", "DH")))
        self.data = _load_data(wide_path, quality_path, self.variable_names)
        self.output_dir = Path(output_dir)
        self.mask_dir = Path(mask_dir)
        self.models = tuple(dict.fromkeys(str(value).lower() for value in models))
        unknown = sorted(set(self.models).difference(SUPPORTED_MODELS))
        if unknown:
            raise ValueError(f"unsupported models: {unknown}")
        requested_seeds = tuple(grid.training_seeds if training_seeds is None else map(int, training_seeds))
        invalid_seeds = sorted(set(requested_seeds).difference(grid.training_seeds))
        if invalid_seeds:
            raise ValueError(f"training seeds are not in the manifest: {invalid_seeds}")
        self.training_seeds = requested_seeds
        self.resume = bool(resume)
        self._deep_cache: dict[tuple[str, int, int, str], Any] = {}
        self._proposed_cache: dict[
            tuple[int, int, str], tuple[MissingAwareMultisourceImputer, np.ndarray, np.ndarray]
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

    def _indices(self, scenario: ExperimentScenario) -> tuple[list[int], list[int]]:
        stations = [self.data.station_ids.index(value) for value in scenario.condition.station_ids]
        variables = [self.data.variable_names.index(value) for value in scenario.condition.variables]
        return stations, variables

    def _event_condition(self, scenario: ExperimentScenario) -> np.ndarray:
        station = self.data.station_ids.index(scenario.condition.station_ids[0])
        event = scenario.condition.event_type
        if event in {"high_temperature", "rapid_warming"}:
            variable = self.data.variable_names.index("T")
        else:
            variable = self.data.variable_names.index("F")
        series = self.data.values[:, station, variable]
        train = series[self.train_rows & np.isfinite(series)]
        condition = np.zeros(len(series), dtype=bool)
        if event == "high_temperature":
            condition = series >= np.quantile(train, 0.9)
        elif event == "rapid_warming":
            differences = np.diff(series, prepend=np.nan)
            train_diff = differences[self.train_rows & np.isfinite(differences)]
            condition = differences >= np.quantile(train_diff, 0.9)
        elif event == "flood":
            condition = series >= np.quantile(train, 0.9)
        elif event == "low_flow":
            condition = series <= np.quantile(train, 0.1)
        else:
            raise ValueError(f"unsupported event_type: {event}")
        return condition & self.test_rows

    def _generate_mask(self, scenario: ExperimentScenario) -> tuple[np.ndarray, dict[str, Any]]:
        mask_path = self.mask_dir / "scenarios" / f"{scenario.scenario_id}.npz"
        metadata_path = self.mask_dir / "scenarios" / f"{scenario.scenario_id}.json"
        if mask_path.exists() and metadata_path.exists():
            return _load_compact_mask(self.mask_dir, scenario.scenario_id)
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
        if mask.shape != self.data.values.shape or mask.dtype != np.bool_:
            raise AssertionError("scenario did not produce a complete 3D mask")
        if np.any(mask[~self.test_rows]):
            raise AssertionError("test scenario mask leaked into train/validation dates")
        metadata.update(scenario.as_dict())
        is_loso = condition.mask_type == "loso"
        metadata.update(
            {
                "fit_split": "train_other_stations" if is_loso else "train",
                "tuning_split": "validation_other_stations" if is_loso else "validation",
                "evaluation_split": "test",
                "external_validation_status": self.grid.external_validation_status,
                "is_external_validation": False,
            }
        )
        _save_compact_mask(
            mask,
            metadata,
            self.mask_dir,
            dates=self.data.dates,
            station_ids=self.data.station_ids,
            variable_names=self.data.variable_names,
        )
        return mask, metadata

    def _climatology(self, station: int, variable: int) -> tuple[Any, np.ndarray]:
        key = (station, variable)
        if key not in self._climatology_cache:
            target = self.data.values[:, station, variable].astype(float)
            frame = pd.DataFrame({"date": self.data.dates, "target": target})
            fit_mask = self.train_rows & self.data.quality_approved[:, station, variable] & np.isfinite(target)
            model = ClimatologyBaseline("target", window=7).fit(frame, train_mask=fit_mask)
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
            return variable_name == "F" if model_name != "pooled_loso" else variable_name == "T"
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
        other_stations = [value for value in self.data.station_ids if value != station_id]
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
            model_class = RandomForestBaseline if model_name == "random_forest" else XGBoostBaseline
            model = model_class(feature_cols, target_col).fit(frame, train_mask=fit_mask)
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

    def _pooled_loso_prediction(self, held_out_station: int) -> tuple[Any, np.ndarray, float]:
        """Fit/tune a pooled seasonal Ta/F/L model without held-out T labels."""

        if held_out_station in self._loso_cache:
            return self._loso_cache[held_out_station]
        target_index = self.data.variable_names.index("T")
        feature_indices = {name: self.data.variable_names.index(name) for name in ("Ta", "F", "L")}
        donor_stations = [
            index for index in range(len(self.data.station_ids)) if index != held_out_station
        ]

        def pooled_frame(rows: np.ndarray) -> pd.DataFrame:
            positions = np.flatnonzero(rows)
            frames = []
            for station in donor_stations:
                target = self.data.values[positions, station, target_index].astype(float)
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
            score = float(np.sqrt(np.mean((truth[valid] - prediction[valid]) ** 2))) if valid.any() else float("inf")
            if score < best_score:
                best_alpha, best_score = alpha, score
        model = SeasonalRidgeBaseline(
            ("Ta", "F", "L"), "target", alpha=best_alpha
        ).fit(train)
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
        truth = self.data.values[:, station, variable].astype(float)
        hidden = artificial_mask[:, station, variable]
        masked_values = apply_full_artificial_mask(self.data.values, artificial_mask)
        masked_frame = self._wide_frame(masked_values)
        target_col = f"{self.data.station_ids[station]}_{self.data.variable_names[variable]}"
        masked = masked_frame[target_col]
        if model_name == "pooled_loso":
            return self._pooled_loso_prediction(station)[1].copy()
        if model_name == "climatology":
            return self._climatology(station, variable)[1].copy()
        if model_name == "linear":
            return OfflineLinearInterpolation().predict(masked, dates=self.data.dates).to_numpy(dtype=float)
        if model_name == "pchip":
            return PCHIPInterpolation().predict(masked, dates=self.data.dates).to_numpy(dtype=float)
        if model_name == "kalman":
            return self._traditional_model(model_name, station, variable).predict(
                masked_frame, target=target_col
            ).to_numpy(dtype=float)
        model = self._traditional_model(model_name, station, variable)
        if model_name == "rating_curve":
            return model.predict(masked_frame).to_numpy(dtype=float)
        return model.predict(masked_frame, dates=self.data.dates).to_numpy(dtype=float)

    def _deep_model(self, name: str, seed: int, window: int, protocol: str) -> Any:
        key = (name, seed, window, protocol)
        if key in self._deep_cache:
            return self._deep_cache[key]
        checkpoint = self.output_dir / "checkpoints" / f"{name}-S{seed}-W{window}-{protocol}.pt"
        model_class = BRITSImputer if name == "brits" else SAITSImputer
        if checkpoint.exists() and self.resume:
            model = model_class.load_checkpoint(checkpoint)
            self._deep_cache[key] = model
            return model
        flattened = self.data.values.reshape(len(self.data.values), -1)
        train_values = flattened[self.train_rows]
        validation_values = flattened[self.validation_rows]
        train_mask = make_training_mask(train_values, seed, protocol)
        validation_mask = make_training_mask(validation_values, seed + 10_000, protocol)
        train_windows, train_masks = make_windows(train_values, train_mask, window, stride=window // 2)
        validation_windows, validation_masks = make_windows(
            validation_values, validation_mask, min(window, len(validation_values)), stride=max(1, window // 2)
        )
        if name == "brits":
            model = BRITSImputer(flattened.shape[1], hidden_size=32, seed=seed)
        else:
            model = SAITSImputer(flattened.shape[1], d_model=32, n_heads=4, d_ff=64, seed=seed)
        runner_config = self.config.get("runner", {})
        model.fit(
            train_windows,
            train_masks,
            validation_values=validation_windows,
            validation_mask=validation_masks,
            epochs=int(runner_config.get("deep_epochs", 3)),
            batch_size=int(runner_config.get("batch_size", 8)),
            patience=int(runner_config.get("patience", 2)),
        )
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
                "natural_mask": torch.from_numpy(natural[start : start + window]).unsqueeze(0),
                "artificial_mask": torch.from_numpy(artificial[start : start + window]).unsqueeze(0),
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
                "seasonal_features": torch.from_numpy(seasonal[start : start + window]).unsqueeze(0),
            }
            for start in starts
            if artificial[start : start + window, :, 0].any()
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
                selected = values[train_quality[:, station, variable] & np.isfinite(values)]
                if selected.size == 0:
                    raise ValueError(
                        f"no approved training values for {self.data.station_ids[station]}_"
                        f"{self.data.variable_names[variable]}"
                    )
                mean[station, variable] = float(selected.mean())
                standard_deviation = float(selected.std())
                scale[station, variable] = standard_deviation if standard_deviation >= 1e-6 else 1.0
        self._proposed_scale_cache = (mean, scale)
        return self._proposed_scale_cache

    def _proposed_model(
        self, seed: int, window: int, protocol: str
    ) -> tuple[MissingAwareMultisourceImputer, np.ndarray, np.ndarray]:
        key = (seed, window, protocol)
        if key in self._proposed_cache:
            return self._proposed_cache[key]
        checkpoint = self.output_dir / "checkpoints" / f"proposed-S{seed}-W{window}-{protocol}.pt"
        if checkpoint.exists() and self.resume:
            model, checkpoint_metadata = load_proposed_checkpoint(checkpoint)
            stored_scaler = checkpoint_metadata.get("train_scaler")
            if stored_scaler is None:
                mean, scale = self._proposed_scaler()
                checkpoint_metadata["train_scaler"] = {
                    "mean": mean.tolist(),
                    "scale": scale.tolist(),
                    "station_ids": list(self.data.station_ids),
                    "variable_names": list(self.data.variable_names),
                }
                torch.save(checkpoint_metadata, checkpoint)
            else:
                mean = np.asarray(stored_scaler["mean"], dtype=np.float32)
                scale = np.asarray(stored_scaler["scale"], dtype=np.float32)
            if mean.shape != self.data.values.shape[1:] or scale.shape != mean.shape:
                raise ValueError("proposed checkpoint scaler does not match the current data axes")
            self._proposed_cache[key] = (model, mean, scale)
            return self._proposed_cache[key]
        mean, scale = self._proposed_scaler()
        normalized_values = (self.data.values - mean[None]) / scale[None]
        train_values = self.data.values[self.train_rows].reshape(int(self.train_rows.sum()), -1)
        validation_values = self.data.values[self.validation_rows].reshape(int(self.validation_rows.sum()), -1)
        train_mask = make_training_mask(train_values, seed, protocol)
        validation_mask = make_training_mask(validation_values, seed + 10_000, protocol)
        train_window = min(window, len(train_values))
        validation_window = min(window, len(validation_values))
        train_batches = self._proposed_batches(
            normalized_values, self.train_rows, train_mask, train_window
        )
        validation_batches = self._proposed_batches(
            normalized_values, self.validation_rows, validation_mask, validation_window
        )
        model = MissingAwareMultisourceImputer(
            ProposedModelConfig(
                station_ids=self.data.station_ids,
                variable_names=self.data.variable_names,
                hidden_size=24,
                dropout=0.0,
            )
        )
        runner_config = self.config.get("runner", {})
        train_proposed_model(
            model,
            train_batches,
            validation_batches,
            ProposedTrainingConfig(
                epochs=int(runner_config.get("proposed_epochs", 3)),
                patience=int(runner_config.get("patience", 2)),
                seed=seed,
                device=str(runner_config.get("device", "cpu")),
            ),
            checkpoint_path=checkpoint,
        )
        checkpoint_metadata = torch.load(checkpoint, map_location="cpu", weights_only=False)
        checkpoint_metadata["train_scaler"] = {
            "mean": mean.tolist(),
            "scale": scale.tolist(),
            "station_ids": list(self.data.station_ids),
            "variable_names": list(self.data.variable_names),
        }
        torch.save(checkpoint_metadata, checkpoint)
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
            model = self._deep_model(model_name, seed, condition.window_length, condition.training_protocol)
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
                prediction_sum[start:end] += np.where(window_mask, window_prediction, 0.0)
                prediction_count[start:end] += window_mask
            if np.any(flat_mask & (prediction_count == 0)):
                raise RuntimeError("windowed deep prediction did not cover every hidden cell")
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
        normalized_values = (self.data.values - mean[None]) / scale[None]
        values = torch.from_numpy(normalized_values[None])
        natural = torch.from_numpy(self.data.natural_observed[None])
        artificial = torch.from_numpy(artificial_mask[None])
        seasonal = torch.from_numpy(self.data.seasonal_features[None])
        with torch.no_grad():
            output = model(values, natural, artificial, seasonal_features=seasonal)
        quantiles = output["quantiles"][0].cpu().numpy()
        prediction = np.full_like(masked_values, np.nan, dtype=float)
        target_index = self.data.variable_names.index("T")
        quantiles = (
            quantiles * scale[:, target_index][None, :, None]
            + mean[:, target_index][None, :, None]
        )
        prediction[..., target_index] = quantiles[..., 1]
        return prediction, {
            "q05": quantiles[..., 0],
            "q50": quantiles[..., 1],
            "q95": quantiles[..., 2],
        }

    def _prediction_rows(
        self,
        scenario: ExperimentScenario,
        metadata: Mapping[str, Any],
        artificial_mask: np.ndarray,
        model_name: str,
        training_seed: int | None,
    ) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
        evaluation_variables = scenario.condition.evaluation_variables or scenario.condition.variables
        station_indices = [self.data.station_ids.index(value) for value in scenario.condition.station_ids]
        shared_prediction, quantiles = self._model_prediction(
            model_name, training_seed, scenario, artificial_mask
        )
        daily_parts: list[pd.DataFrame] = []
        event_rows: list[dict[str, Any]] = []
        skipped_rows: list[dict[str, Any]] = []
        is_loso = scenario.condition.mask_type == "loso"
        fit_split = "train_other_stations" if is_loso else "train"
        tuning_split = "validation_other_stations" if is_loso else "validation"
        failed_stations = (
            list(scenario.condition.station_ids)
            if scenario.condition.experiment in {"M4", "M6"}
            or scenario.condition.mask_type == "async"
            else []
        )
        failed_stations_json = json.dumps(failed_stations, separators=(",", ":"))
        for station in station_indices:
            for variable_name in evaluation_variables:
                variable = self.data.variable_names.index(variable_name)
                hidden = artificial_mask[:, station, variable]
                if (
                    not hidden.any()
                    or (model_name == "proposed" and variable_name != "T")
                    or not self._supports_target(model_name, variable_name)
                ):
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
                    unavailable = artificial_mask[positions, station, level] | ~np.isfinite(
                        self.data.values[positions, station, level]
                    )
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
                    prediction = self._traditional_prediction(model_name, station, variable, artificial_mask)
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
                )
                event_row.update(
                    {
                        "experiment": scenario.condition.experiment,
                        "fit_split": fit_split,
                        "tuning_split": tuning_split,
                        "evaluation_split": "test",
                        "window_length": scenario.condition.window_length,
                        "training_protocol": scenario.condition.training_protocol,
                        "external_validation_status": self.grid.external_validation_status,
                        "validation_scope": scenario.condition.validation_scope,
                        "is_external_validation": False,
                        "failed_stations": failed_stations_json,
                    }
                )
                if model_name == "pooled_loso":
                    event_row["selected_alpha"] = self._pooled_loso_prediction(station)[2]
                if not np.isfinite(event_row["MAE"]) or not np.isfinite(event_row["RMSE"]):
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
                        "q05": q["q05"][positions] if q else np.nan,
                        "q25": np.nan,
                        "q50": q["q50"][positions] if q else prediction[positions],
                        "q75": np.nan,
                        "q95": q["q95"][positions] if q else np.nan,
                        "season": seasons,
                        "event_type": scenario.condition.event_type,
                        "quality_approved": quality[positions],
                        "artificial_mask": hidden[positions],
                        "window_length": scenario.condition.window_length,
                        "training_protocol": scenario.condition.training_protocol,
                        "external_validation_status": self.grid.external_validation_status,
                        "validation_scope": scenario.condition.validation_scope,
                        "is_external_validation": False,
                    }
                )
                daily_parts.append(daily)
        daily_result = pd.concat(daily_parts, ignore_index=True) if daily_parts else pd.DataFrame()
        return daily_result, pd.DataFrame(event_rows), skipped_rows

    def _run_keys(self) -> list[tuple[str, int | None]]:
        return [
            (model, seed)
            for model in self.models
            for seed in (self.training_seeds if model in TRAINABLE_MODELS else (None,))
        ]

    def _run_scenario(self, scenario: ExperimentScenario) -> str:
        scenario_dir = self.output_dir / "scenarios" / scenario.scenario_id
        status_path = scenario_dir / "status.json"
        status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
        artificial, metadata = self._generate_mask(scenario)
        completed = set(status.get("completed_runs", [])) if self.resume else set()
        skipped_runs = list(status.get("skipped_runs", [])) if self.resume else []
        daily_path = scenario_dir / "daily_predictions.parquet"
        event_path = scenario_dir / "event_metrics.parquet"
        daily = pd.read_parquet(daily_path) if self.resume and daily_path.exists() else pd.DataFrame()
        events = pd.read_parquet(event_path) if self.resume and event_path.exists() else pd.DataFrame()
        invalid_run_keys: set[str] = set()
        if not daily.empty:
            finite_daily = np.isfinite(pd.to_numeric(daily["y_true"], errors="coerce")) & np.isfinite(
                pd.to_numeric(daily["y_pred"], errors="coerce")
            )
            invalid_run_keys.update(
                _stored_run_key(row.model, row.training_seed)
                for row in daily.loc[~finite_daily, ["model", "training_seed"]].itertuples(index=False)
            )
            if not finite_daily.all():
                daily = daily.loc[finite_daily].reset_index(drop=True)
                _atomic_parquet(daily, daily_path)
        if not events.empty:
            finite_events = np.isfinite(pd.to_numeric(events["MAE"], errors="coerce")) & np.isfinite(
                pd.to_numeric(events["RMSE"], errors="coerce")
            )
            invalid_run_keys.update(
                _stored_run_key(row.model, row.training_seed)
                for row in events.loc[~finite_events, ["model", "training_seed"]].itertuples(index=False)
            )
            if not finite_events.all():
                events = events.loc[finite_events].reset_index(drop=True)
                _atomic_parquet(events, event_path)
        if invalid_run_keys:
            completed.difference_update(invalid_run_keys)
            skipped_runs = [
                row for row in skipped_runs if row.get("run_key") not in invalid_run_keys
            ]
        run_keys = (
            [("pooled_loso", None)]
            if scenario.condition.mask_type == "loso"
            else self._run_keys()
        )
        for model_name, training_seed in run_keys:
            run_key = f"{model_name}:none" if training_seed is None else f"{model_name}:{training_seed}"
            if run_key in completed:
                continue
            new_daily, new_events, new_skips = self._prediction_rows(
                scenario, metadata, artificial, model_name, training_seed
            )
            daily = pd.concat((daily, new_daily), ignore_index=True) if not new_daily.empty else daily
            events = pd.concat((events, new_events), ignore_index=True) if not new_events.empty else events
            if not daily.empty:
                daily = daily.drop_duplicates(DAILY_KEY, keep="last")
                _atomic_parquet(daily, daily_path)
            if not events.empty:
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
            completed.add(run_key)
            is_loso = scenario.condition.mask_type == "loso"
            _atomic_json(
                {
                    "scenario_id": scenario.scenario_id,
                    "status": "complete",
                    "completed_runs": sorted(completed),
                    "skipped_runs": skipped_runs,
                    "skipped_run_count": len(skipped_runs),
                    "fit_split": "train_other_stations" if is_loso else "train",
                    "tuning_split": "validation_other_stations" if is_loso else "validation",
                    "evaluation_split": "test",
                    "validation_scope": scenario.condition.validation_scope,
                    "is_external_validation": False,
                },
                status_path,
            )
        return "complete"

    def _aggregate(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        daily_frames = []
        event_frames = []
        for directory in sorted((self.output_dir / "scenarios").glob("*")):
            daily_path = directory / "daily_predictions.parquet"
            event_path = directory / "event_metrics.parquet"
            if daily_path.exists():
                daily_frames.append(pd.read_parquet(daily_path))
            if event_path.exists():
                event_frames.append(pd.read_parquet(event_path))
        daily = pd.concat(daily_frames, ignore_index=True).drop_duplicates(DAILY_KEY) if daily_frames else pd.DataFrame()
        events = pd.concat(event_frames, ignore_index=True).drop_duplicates(EVENT_KEY) if event_frames else pd.DataFrame()
        if not daily.empty:
            _atomic_parquet(daily, self.output_dir / "daily_predictions.parquet")
        if not events.empty:
            _atomic_parquet(events, self.output_dir / "event_metrics.parquet")
        return daily, events

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
        _atomic_json(
            {
                "suite": self.grid.suite,
                "models": list(self.models),
                "training_seeds": list(self.training_seeds),
                "mask_seeds": list(self.grid.mask_seeds),
                "shard_index": shard_index,
                "shard_count": shard_count,
                "selected_scenarios": len(selected),
                "status_counts": statuses,
                "fit_split": "train",
                "tuning_split": "validation",
                "evaluation_split": "test_once",
                "external_validation_status": self.grid.external_validation_status,
                "loso_scope": "exploratory_internal_not_external_validation",
            },
            self.output_dir / "run_manifest.json",
        )
        return daily, events


def run_experiments(grid: ExperimentGrid, **kwargs: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    run_kwargs = {
        key: kwargs.pop(key)
        for key in ("shard_index", "shard_count", "max_scenarios")
        if key in kwargs
    }
    return ExperimentRunner(grid, **kwargs).run(**run_kwargs)


__all__ = [
    "ExperimentRunner",
    "SUPPORTED_MODELS",
    "apply_full_artificial_mask",
    "make_training_mask",
    "run_experiments",
]
