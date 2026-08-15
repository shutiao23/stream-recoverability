#!/usr/bin/env python3
"""Run traditional offline baselines on a fixed validation/test mask library."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any
import warnings

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.evaluation.event_metrics import (  # noqa: E402
    EVENT_METRIC_COLUMNS,
    compute_event_metrics,
)
from stream_recoverability.masks import load_mask_library, load_mask_manifest  # noqa: E402
from stream_recoverability.models.baselines import (  # noqa: E402
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
    XGBoostBaseline,
)


DEFAULT_DATA = PROJECT_ROOT / "data/processed/daily_wide.parquet"
DEFAULT_QUALITY = PROJECT_ROOT / "data/processed/daily_long.parquet"
DEFAULT_MASKS = PROJECT_ROOT / "masks/test"
DEFAULT_OUTPUT = PROJECT_ROOT / "results/baselines"
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
)


def _read_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if path.suffix.lower() in {".csv", ".txt"}:
        return pd.read_csv(path)
    raise ValueError(f"unsupported table format: {path}")


def _write_table(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in {".parquet", ".pq"}:
        frame.to_parquet(path, index=False)
    elif path.suffix.lower() == ".csv":
        frame.to_csv(path, index=False)
    else:
        raise ValueError(f"output must be .parquet or .csv: {path}")


def _parse_models(values: list[str]) -> list[str]:
    models: list[str] = []
    for value in values:
        models.extend(part.strip().lower() for part in value.split(",") if part.strip())
    if "all" in models:
        if len(models) != 1:
            raise ValueError("'all' cannot be combined with individual model names")
        return list(SUPPORTED_MODELS)
    unknown = sorted(set(models) - set(SUPPORTED_MODELS))
    if unknown:
        raise ValueError(f"unsupported models: {unknown}; choices are {SUPPORTED_MODELS}")
    return list(dict.fromkeys(models))


def _ordered_wide(wide: pd.DataFrame, manifest: dict[str, Any]) -> pd.DataFrame:
    if "date" not in wide:
        raise KeyError("prepared wide table must contain a date column")
    result = wide.copy()
    result["date"] = pd.to_datetime(result["date"]).dt.normalize()
    if result["date"].duplicated().any():
        raise ValueError("prepared wide table contains duplicate dates")
    axis_dates = manifest.get("axes", {}).get("date")
    if axis_dates is None:
        return result.sort_values("date").reset_index(drop=True)
    ordered_dates = pd.DatetimeIndex(pd.to_datetime(axis_dates)).normalize()
    indexed = result.set_index("date")
    absent = ordered_dates.difference(indexed.index)
    if len(absent):
        raise ValueError(f"wide data is missing {len(absent)} mask-axis dates")
    return indexed.loc[ordered_dates].rename_axis("date").reset_index()


def _infer_axes(wide: pd.DataFrame, manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    axes = manifest.get("axes", {})
    stations = axes.get("station")
    variables = axes.get("variable")
    if stations is not None and variables is not None:
        return [str(value) for value in stations], [str(value) for value in variables]

    columns = [column for column in wide.columns if "_" in str(column)]
    inferred_stations: set[str] = set()
    inferred_variables: set[str] = set()
    for column in columns:
        station, variable = str(column).split("_", 1)
        if variable in {"T", "F", "L"}:
            inferred_stations.add(station)
            inferred_variables.add(variable)
    variable_order = [value for value in ("T", "F", "L") if value in inferred_variables]
    return sorted(inferred_stations), variable_order


def _quality_wide(
    wide: pd.DataFrame,
    quality_path: Path | None,
    stations: list[str],
    variables: list[str],
) -> pd.DataFrame:
    result = pd.DataFrame(index=wide.index)
    expected = [f"{station}_{variable}" for station in stations for variable in variables]
    if quality_path is None or not quality_path.exists():
        for column in expected:
            if column in wide:
                result[column] = pd.to_numeric(wide[column], errors="coerce").notna()
        return result

    quality = _read_table(quality_path)
    required = {"date", "station_id", "variable", "quality_approved"}
    missing = sorted(required - set(quality.columns))
    if missing:
        raise KeyError(f"quality table is missing required columns: {missing}")
    quality = quality.loc[quality["variable"].astype(str).isin(variables)].copy()
    quality["date"] = pd.to_datetime(quality["date"]).dt.normalize()
    if quality.duplicated(["date", "station_id", "variable"]).any():
        raise ValueError("quality table has duplicate date/station/variable rows")
    pivot = quality.pivot(
        index="date", columns=["station_id", "variable"], values="quality_approved"
    )
    pivot.columns = [f"{station}_{variable}" for station, variable in pivot.columns]
    pivot = pivot.reindex(pd.DatetimeIndex(wide["date"]))
    pivot.index = wide.index
    for column in expected:
        if column in pivot:
            result[column] = pivot[column].fillna(False).astype(bool)
        elif column in wide:
            result[column] = False
    return result


def _event_gap_length(metadata: dict[str, Any]) -> int | float | None:
    if metadata.get("total_budget") is not None:
        return int(metadata["total_budget"])
    values = metadata.get("gap_lengths")
    if isinstance(values, (list, tuple)):
        if len(values) == 1:
            return int(values[0])
        if values:
            return int(sum(values))
        return None
    if values is not None:
        return int(values)
    return None


def _pattern(metadata: dict[str, Any]) -> str | None:
    values = metadata.get("variables")
    if isinstance(values, (list, tuple)):
        return "+".join(str(value) for value in values)
    return str(values) if values is not None else None


def _present(wide: pd.DataFrame, columns: list[str]) -> list[str]:
    return list(dict.fromkeys(column for column in columns if column in wide))


def _build_trainable_model(
    model_name: str,
    wide: pd.DataFrame,
    stations: list[str],
    station: str,
    target: str,
) -> tuple[Any | None, str | None]:
    """Build one station/target model or return an explicit skip reason."""

    target_column = f"{station}_{target}"
    if target not in {"T", "F", "L"}:
        return None, None
    same_air = f"{station}_Ta"
    same_flow = f"{station}_F"
    same_level = f"{station}_L"
    other_stations = [value for value in stations if value != station]
    other_target = _present(
        wide, [f"{other}_{target}" for other in other_stations]
    )
    other_hydrology = _present(
        wide,
        [
            column
            for other in other_stations
            for column in (f"{other}_F", f"{other}_L")
        ],
    )

    if model_name == "kalman":
        return KalmanSmootherBaseline(target_column), None
    if model_name == "air_only":
        if target != "T":
            return None, None
        if same_air not in wide:
            return None, f"missing required air-temperature feature {same_air}"
        return AirOnlyBaseline(same_air, target_column), None
    if model_name == "air_hydro":
        if target != "T":
            return None, None
        hydrology = _present(wide, [same_flow, same_level])
        if same_air not in wide or not hydrology:
            return None, "air-hydro requires same-site Ta and at least one of F/L"
        return AirHydroBaseline(same_air, hydrology, target_column), None
    if model_name == "donor_regression":
        if not other_target:
            return None, "no other-station target donor is available"
        covariates = [same_air] if same_air in wide else []
        return DonorRegressionBaseline(
            other_target,
            target_column,
            covariate_cols=covariates,
        ), None
    if model_name in {"random_forest", "xgboost"}:
        same_site = _present(
            wide,
            [same_air, same_flow, same_level],
        )
        features = _present(
            wide,
            [
                *[column for column in same_site if column != target_column],
                *other_target,
                *other_hydrology,
            ],
        )
        features = [column for column in features if column != target_column]
        if not features:
            return None, "no non-target regression features are available"
        if model_name == "random_forest":
            return RandomForestBaseline(features, target_column), None
        if not XGBoostBaseline.is_available():
            return None, "xgboost is not installed"
        return XGBoostBaseline(features, target_column), None
    if model_name == "rating_curve":
        if target != "F":
            return None, None
        if same_level not in wide:
            return None, f"missing target-station level {same_level}"
        return RatingCurveBaseline(same_level, target_column), None
    if model_name == "independent_flow":
        if target != "F":
            return None, None
        features = _present(wide, [same_air, *other_target, *other_hydrology])
        features = [column for column in features if column != same_level]
        if not features:
            return None, "no independent flow features are available"
        return IndependentFlowBaseline(
            features,
            same_level,
            target_column,
        ), None
    raise AssertionError(model_name)


def _base_event_metadata(
    metadata: dict[str, Any],
    scenario_id: str,
    station: str,
    target: str,
    model_name: str,
) -> dict[str, Any]:
    return {
        **metadata,
        "scenario_id": scenario_id,
        "station_id": station,
        "model": model_name,
        "training_seed": None,
        "mask_seed": metadata.get("seed"),
        "target": target,
        "gap_length": _event_gap_length(metadata),
        "pattern": _pattern(metadata),
    }


def _skipped_event(metadata: dict[str, Any], reason: str) -> dict[str, Any]:
    row = {column: metadata.get(column) for column in EVENT_METRIC_COLUMNS}
    row.update(
        {
            "n_evaluated": 0,
            "MAE": np.nan,
            "RMSE": np.nan,
            "bias": np.nan,
            "Pearson": np.nan,
            "Spearman": np.nan,
            "NMAE": np.nan,
            "NRMSE": np.nan,
            "skill": np.nan,
            "boundary_jump_left": np.nan,
            "boundary_jump_right": np.nan,
            "coverage_90": np.nan,
            "interval_width_90": np.nan,
            "model_status": "skipped",
            "skip_reason": reason,
        }
    )
    return row


def run_baselines(
    wide_path: Path,
    mask_dir: Path,
    *,
    quality_path: Path | None,
    models: list[str],
    stations_filter: set[str] | None = None,
    targets_filter: set[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return daily predictions and one event-metric row per model/target/scenario."""

    manifest = load_mask_manifest(mask_dir)
    library = load_mask_library(mask_dir)
    wide = _ordered_wide(_read_table(wide_path), manifest)
    stations, variables = _infer_axes(wide, manifest)
    if not stations or not variables:
        raise ValueError("could not infer station and variable axes")
    quality = _quality_wide(wide, quality_path, stations, variables)

    expected_shape = (len(wide), len(stations), len(variables))
    training_rows = (
        wide["split"].astype(str).eq("train")
        if "split" in wide
        else pd.to_datetime(wide["date"]).le(pd.Timestamp("2015-12-31"))
    )
    climatologies: dict[str, tuple[ClimatologyBaseline, pd.Series]] = {}
    fitted_models: dict[tuple[str, str], tuple[Any | None, str | None]] = {}
    daily_parts: list[pd.DataFrame] = []
    event_rows: list[dict[str, Any]] = []

    for scenario_id, (artificial_3d, stored_metadata) in library.items():
        artificial_3d = np.asarray(artificial_3d, dtype=bool)
        if artificial_3d.shape != expected_shape:
            raise ValueError(
                f"mask {scenario_id} has shape {artificial_3d.shape}, expected {expected_shape}"
            )
        metadata = dict(stored_metadata)
        scenario_frame = wide.copy()
        for masked_station, masked_variable in np.argwhere(
            artificial_3d.any(axis=0)
        ):
            masked_column = f"{stations[masked_station]}_{variables[masked_variable]}"
            if masked_column in scenario_frame:
                scenario_frame.loc[
                    artificial_3d[:, masked_station, masked_variable], masked_column
                ] = np.nan
        for station_index, station in enumerate(stations):
            if stations_filter is not None and station not in stations_filter:
                continue
            for variable_index, target in enumerate(variables):
                if targets_filter is not None and target not in targets_filter:
                    continue
                artificial = artificial_3d[:, station_index, variable_index]
                if not artificial.any():
                    continue
                target_column = f"{station}_{target}"
                if target_column not in wide:
                    raise KeyError(f"prepared wide table is missing {target_column}")
                truth = pd.to_numeric(wide[target_column], errors="coerce")
                approved = quality[target_column].to_numpy(dtype=bool)
                train_mask = training_rows.to_numpy(dtype=bool) & approved & truth.notna().to_numpy()
                training_values = truth.to_numpy(dtype=float)[train_mask]
                if not training_values.size:
                    raise ValueError(f"{target_column} has no approved training values")
                normalization_iqr = float(
                    np.quantile(training_values, 0.75)
                    - np.quantile(training_values, 0.25)
                )
                normalization_std = float(np.std(training_values, ddof=0))
                high_threshold = float(np.quantile(training_values, 0.90))
                low_threshold = float(np.quantile(training_values, 0.10))

                if target_column not in climatologies:
                    climatology_model = ClimatologyBaseline(target_column, window=7)
                    climatology_model.fit(wide, train_mask=train_mask)
                    climatology_prediction = climatology_model.predict(wide)
                    climatologies[target_column] = (climatology_model, climatology_prediction)
                climatology_prediction = climatologies[target_column][1]

                masked = pd.to_numeric(
                    scenario_frame[target_column], errors="coerce"
                )
                for model_name in models:
                    event_metadata = _base_event_metadata(
                        metadata,
                        scenario_id,
                        station,
                        target,
                        model_name,
                    )
                    if model_name == "climatology":
                        prediction = climatology_prediction.copy()
                    elif model_name == "linear":
                        prediction = OfflineLinearInterpolation().predict(
                            masked, dates=wide["date"]
                        )
                    elif model_name == "pchip":
                        prediction = PCHIPInterpolation().predict(
                            masked, dates=wide["date"]
                        )
                    else:
                        cache_key = (model_name, target_column)
                        if cache_key not in fitted_models:
                            model, skip_reason = _build_trainable_model(
                                model_name,
                                wide,
                                stations,
                                station,
                                target,
                            )
                            if model is not None:
                                try:
                                    model.fit(wide, train_mask=train_mask)
                                except ImportError as exc:
                                    if model_name != "xgboost":
                                        raise
                                    model = None
                                    skip_reason = str(exc)
                            fitted_models[cache_key] = (model, skip_reason)
                        model, skip_reason = fitted_models[cache_key]
                        if model is None:
                            if skip_reason is not None:
                                event_rows.append(
                                    _skipped_event(event_metadata, skip_reason)
                                )
                            continue
                        if model_name == "kalman":
                            prediction = model.predict(masked)
                        else:
                            prediction = model.predict(scenario_frame)

                    event_row = compute_event_metrics(
                        truth,
                        prediction,
                        approved,
                        artificial,
                        target=target,
                        metadata=event_metadata,
                        climatology_pred=climatology_prediction,
                        dates=wide["date"],
                        high_threshold=high_threshold,
                        low_threshold=low_threshold,
                        normalization_iqr=normalization_iqr,
                        normalization_std=normalization_std,
                    )
                    event_row["model_status"] = "ok"
                    event_row["skip_reason"] = None
                    event_rows.append(event_row)

                    positions = np.flatnonzero(artificial)
                    daily_parts.append(
                        pd.DataFrame(
                            {
                                "date": wide.loc[positions, "date"].to_numpy(),
                                "station_id": station,
                                "target": target,
                                "scenario_id": scenario_id,
                                "mask_type": metadata.get("mask_type"),
                                "gap_length": _event_gap_length(metadata),
                                "missing_rate": metadata.get("missing_rate"),
                                "variable_pattern": _pattern(metadata),
                                "model": model_name,
                                "training_seed": None,
                                "mask_seed": metadata.get("seed"),
                                "y_true": truth.iloc[positions].to_numpy(dtype=float),
                                "y_pred": prediction.iloc[positions].to_numpy(dtype=float),
                                "q05": np.nan,
                                "q25": np.nan,
                                "q50": prediction.iloc[positions].to_numpy(dtype=float),
                                "q75": np.nan,
                                "q95": np.nan,
                                "climatology_pred": climatology_prediction.iloc[
                                    positions
                                ].to_numpy(dtype=float),
                                "quality_approved": approved[positions],
                                "artificial_mask": artificial[positions],
                                "season": metadata.get("season"),
                                "event_type": metadata.get("event_type"),
                                "window_length": None,
                                "model_status": "ok",
                                "skip_reason": None,
                            }
                        )
                    )

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="The behavior of DataFrame concatenation with empty or all-NA entries",
            category=FutureWarning,
        )
        daily = (
            pd.concat(daily_parts, ignore_index=True)
            if daily_parts
            else pd.DataFrame()
        )
    events = pd.DataFrame(event_rows)
    if events.empty:
        events = pd.DataFrame(columns=EVENT_METRIC_COLUMNS)
    else:
        leading = [column for column in EVENT_METRIC_COLUMNS if column in events]
        trailing = [column for column in events if column not in leading]
        events = events.loc[:, [*leading, *trailing]]
    return daily, events


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--quality-data", type=Path, default=DEFAULT_QUALITY)
    parser.add_argument("--masks", type=Path, default=DEFAULT_MASKS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--models",
        nargs="+",
        default=["all"],
        help="Space- or comma-separated subset, or 'all': "
        + ", ".join(SUPPORTED_MODELS),
    )
    parser.add_argument("--stations", nargs="*", default=None)
    parser.add_argument("--targets", nargs="*", default=None)
    parser.add_argument("--daily-output", type=Path, default=None)
    parser.add_argument("--event-output", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    models = _parse_models(args.models)
    daily, events = run_baselines(
        args.data,
        args.masks,
        quality_path=args.quality_data,
        models=models,
        stations_filter=set(args.stations) if args.stations else None,
        targets_filter=set(args.targets) if args.targets else None,
    )
    daily_output = args.daily_output or args.output_dir / "predictions.parquet"
    event_output = args.event_output or args.output_dir / "event_metrics.parquet"
    _write_table(daily, daily_output)
    _write_table(events, event_output)
    skipped = int(events.get("model_status", pd.Series(dtype=str)).eq("skipped").sum())
    print(f"wrote {len(daily)} daily predictions to {daily_output}")
    print(f"wrote {len(events)} event rows ({skipped} skipped) to {event_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
