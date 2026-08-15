#!/usr/bin/env python3
"""Run the secondary strictly causal online-recovery protocol."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.evaluation.online import score_online_predictions  # noqa: E402
from stream_recoverability.masks import load_mask_library, load_mask_manifest  # noqa: E402
from stream_recoverability.models.online import (  # noqa: E402
    CausalGRUImputer,
    LastObservationPersistence,
    TrainingDOYClimatology,
)


DEFAULT_WIDE = PROJECT_ROOT / "data/processed/daily_wide.parquet"
DEFAULT_LONG = PROJECT_ROOT / "data/processed/daily_long.parquet"
DEFAULT_VALIDATION_MASKS = PROJECT_ROOT / "masks/validation"
DEFAULT_TEST_MASKS = PROJECT_ROOT / "masks/test"
DEFAULT_OUTPUT = PROJECT_ROOT / "results/online"


def _ordered_data(
    wide_path: Path, long_path: Path, manifest: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray, pd.DatetimeIndex, np.ndarray, list[str], list[str]]:
    axes = manifest["axes"]
    dates = pd.DatetimeIndex(pd.to_datetime(axes["date"])).normalize()
    stations = [str(value) for value in axes["station"]]
    variables = [str(value) for value in axes["variable"]]
    wide = pd.read_parquet(wide_path)
    wide["date"] = pd.to_datetime(wide["date"]).dt.normalize()
    if wide["date"].duplicated().any():
        raise ValueError("daily_wide contains duplicate dates")
    wide = wide.set_index("date").reindex(dates)
    if wide["split"].isna().any():
        raise ValueError("daily_wide does not cover the mask date axis")
    columns = [f"{station}_{variable}" for station in stations for variable in variables]
    missing = [column for column in columns if column not in wide]
    if missing:
        raise KeyError(f"daily_wide is missing columns: {missing}")
    values = wide[columns].apply(pd.to_numeric, errors="coerce").to_numpy(np.float32)
    values = values.reshape(len(dates), len(stations), len(variables))

    long = pd.read_parquet(long_path)
    required = {"date", "station_id", "variable", "quality_approved"}
    absent = required - set(long.columns)
    if absent:
        raise KeyError(f"daily_long is missing columns: {sorted(absent)}")
    long = long.loc[:, list(required)].copy()
    long["date"] = pd.to_datetime(long["date"]).dt.normalize()
    if long.duplicated(["date", "station_id", "variable"]).any():
        raise ValueError("daily_long contains duplicate date/station/variable rows")
    quality = long.pivot(
        index="date", columns=["station_id", "variable"], values="quality_approved"
    )
    quality = quality.reindex(
        index=dates, columns=pd.MultiIndex.from_product([stations, variables])
    ).fillna(False)
    approved = quality.to_numpy(bool).reshape(values.shape) & np.isfinite(values)
    values[~approved] = np.nan
    return values, approved, dates, wide["split"].astype(str).to_numpy(), stations, variables


def _exact_training_mask(
    values: np.ndarray, approved: np.ndarray, rate: float, seed: int
) -> np.ndarray:
    if not 0.0 < rate < 1.0:
        raise ValueError("train_mask_rate must be between 0 and 1")
    result = np.zeros(values.shape, dtype=bool)
    rng = np.random.default_rng(seed)
    for station in range(values.shape[1]):
        for variable in range(values.shape[2]):
            candidates = np.flatnonzero(
                approved[:, station, variable] & np.isfinite(values[:, station, variable])
            )
            count = int(np.floor(len(candidates) * rate + 0.5))
            if count:
                chosen = rng.choice(candidates, size=count, replace=False)
                result[chosen, station, variable] = True
    if not result.any():
        raise ValueError("training mask contains no targets")
    return result


def _choose_masks(
    library: dict[str, tuple[np.ndarray, dict[str, Any]]],
    requested: list[str] | None,
    maximum: int | None,
) -> list[tuple[str, np.ndarray, dict[str, Any]]]:
    if maximum is not None and maximum <= 0:
        raise ValueError("max_test_masks must be positive")
    if requested:
        missing = [scenario_id for scenario_id in requested if scenario_id not in library]
        if missing:
            raise KeyError(f"unknown scenarios: {missing}")
        selected = [(scenario_id, *library[scenario_id]) for scenario_id in requested]
    else:
        selected = [(scenario_id, *scenario) for scenario_id, scenario in library.items()]
    return selected[:maximum] if maximum is not None else selected


def run(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame]:
    test_manifest = load_mask_manifest(args.test_masks)
    values, approved, dates, split, stations, variables = _ordered_data(
        args.wide_data, args.long_data, test_manifest
    )
    train_selector = split == "train"
    validation_selector = split == "validation"
    test_selector = split == "test"
    if not train_selector.any() or not validation_selector.any() or not test_selector.any():
        raise ValueError("train, validation, and test splits must all be non-empty")

    climatology = TrainingDOYClimatology(window=7).fit(
        values, dates, train_selector, approved=approved
    )
    persistence = LastObservationPersistence().fit(
        values, train_selector, approved=approved
    )
    pure_climatology = climatology.baseline(dates)

    models: dict[str, Any] = {}
    if "climatology" in args.models:
        models["climatology"] = climatology
    if "persistence" in args.models:
        models["persistence"] = persistence
    if "causal_gru" in args.models:
        input_channels = np.ones((len(stations), len(variables)), dtype=bool)
        if args.input_variables:
            unknown = sorted(set(args.input_variables) - set(variables))
            if unknown:
                raise ValueError(f"unknown input variables: {unknown}")
            input_channels[:] = False
            for variable in args.input_variables:
                input_channels[:, variables.index(variable)] = True

        validation_library = load_mask_library(args.validation_masks)
        if args.validation_scenario:
            if args.validation_scenario not in validation_library:
                raise KeyError(f"unknown validation scenario: {args.validation_scenario}")
            validation_artificial = validation_library[args.validation_scenario][0]
        else:
            validation_artificial = next(iter(validation_library.values()))[0]
        train_values = values[train_selector]
        train_approved = approved[train_selector]
        validation_values = values[validation_selector]
        validation_approved = approved[validation_selector]
        train_artificial = _exact_training_mask(
            train_values, train_approved, args.train_mask_rate, args.seed
        )
        validation_artificial = np.asarray(validation_artificial, dtype=bool)[
            validation_selector
        ]
        if args.smoke:
            train_limit = min(256, len(train_values))
            validation_limit = min(128, len(validation_values))
            train_values = train_values[:train_limit]
            train_approved = train_approved[:train_limit]
            train_artificial = train_artificial[:train_limit]
            validation_values = validation_values[:validation_limit]
            validation_approved = validation_approved[:validation_limit]
            validation_artificial = validation_artificial[:validation_limit]
        gru = CausalGRUImputer(
            len(stations),
            len(variables),
            hidden_size=min(args.hidden_size, 8) if args.smoke else args.hidden_size,
            input_channel_mask=input_channels,
            seed=args.seed,
        ).fit(
            train_values,
            train_artificial,
            train_approved=train_approved,
            validation_values=validation_values,
            validation_mask=validation_artificial,
            validation_approved=validation_approved,
            epochs=min(args.epochs, 1) if args.smoke else args.epochs,
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            chunk_size=min(args.chunk_size, 32) if args.smoke else args.chunk_size,
            patience=min(args.patience, 1) if args.smoke else args.patience,
            verbose=args.verbose,
        )
        models["causal_gru"] = gru

    maximum = 1 if args.smoke and args.max_test_masks is None else args.max_test_masks
    scenarios = _choose_masks(
        load_mask_library(args.test_masks), args.scenarios, maximum
    )
    overall_rows: list[dict[str, Any]] = []
    horizon_parts: list[pd.DataFrame] = []
    for scenario_id, artificial, scenario_metadata in scenarios:
        artificial = np.asarray(artificial, dtype=bool)
        if artificial.shape != values.shape:
            raise ValueError(
                f"mask {scenario_id} has shape {artificial.shape}, expected {values.shape}"
            )
        if np.any(artificial & ~test_selector[:, None, None]):
            raise ValueError(f"test mask {scenario_id} contains non-test targets")
        for model_name, model in models.items():
            if model_name == "climatology":
                prediction = model.predict(
                    values, dates, artificial, approved=approved
                )
            elif model_name == "persistence":
                prediction = model.predict(values, artificial, approved=approved)
            else:
                prediction = model.predict(
                    values, artificial, approved=approved, chunk_size=args.predict_chunk_size
                )
            metadata = {
                "scenario_id": scenario_id,
                "model": model_name,
                "mask_type": scenario_metadata.get("mask_type"),
                "mask_seed": scenario_metadata.get("seed"),
                "stations": "+".join(scenario_metadata.get("station_ids", [])),
                "variables": "+".join(scenario_metadata.get("variables", [])),
                "protocol": "online_causal",
            }
            overall, horizon = score_online_predictions(
                values,
                prediction,
                approved,
                artificial,
                pure_climatology,
                metadata=metadata,
            )
            overall_rows.append(overall)
            horizon_parts.append(horizon)

    overall_frame = pd.DataFrame(overall_rows)
    horizon_frame = pd.concat(horizon_parts, ignore_index=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    overall_frame.to_csv(args.output_dir / "metrics.csv", index=False)
    horizon_frame.to_csv(args.output_dir / "horizon_metrics.csv", index=False)
    if "causal_gru" in models:
        models["causal_gru"].save_checkpoint(args.output_dir / "causal_gru.pt")
        (args.output_dir / "causal_gru_history.json").write_text(
            json.dumps(models["causal_gru"].history_, indent=2) + "\n", encoding="utf-8"
        )
    (args.output_dir / "protocol.json").write_text(
        json.dumps(
            {
                "protocol": "online_causal",
                "future_values_allowed": False,
                "backward_interpolation_allowed": False,
                "smoother_allowed": False,
                "train_dates": [str(dates[train_selector][0].date()), str(dates[train_selector][-1].date())],
                "validation_dates": [
                    str(dates[validation_selector][0].date()),
                    str(dates[validation_selector][-1].date()),
                ],
                "test_dates": [str(dates[test_selector][0].date()), str(dates[test_selector][-1].date())],
                "models": list(models),
                "scenario_count": len(scenarios),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {len(overall_frame)} online metric rows and "
        f"{len(horizon_frame)} horizon rows to {args.output_dir}"
    )
    return overall_frame, horizon_frame


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wide-data", type=Path, default=DEFAULT_WIDE)
    parser.add_argument("--long-data", type=Path, default=DEFAULT_LONG)
    parser.add_argument("--validation-masks", type=Path, default=DEFAULT_VALIDATION_MASKS)
    parser.add_argument("--test-masks", type=Path, default=DEFAULT_TEST_MASKS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=["climatology", "persistence", "causal_gru"],
        default=["climatology", "persistence", "causal_gru"],
    )
    parser.add_argument("--input-variables", nargs="*")
    parser.add_argument("--validation-scenario")
    parser.add_argument("--scenarios", nargs="*")
    parser.add_argument("--max-test-masks", type=int)
    parser.add_argument("--train-mask-rate", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--hidden-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-5)
    parser.add_argument("--chunk-size", type=int, default=64)
    parser.add_argument("--predict-chunk-size", type=int, default=256)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
