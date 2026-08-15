#!/usr/bin/env python3
"""Train local CPU BRITS-lite/SAITS-lite models with fixed validation masks."""

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

from stream_recoverability.masks import load_mask_library, load_mask_manifest  # noqa: E402
from stream_recoverability.models.deep_baselines import (  # noqa: E402
    BRITSImputer,
    SAITSImputer,
)
from stream_recoverability.models.training import make_windows  # noqa: E402


DEFAULT_DATA = PROJECT_ROOT / "data/processed/daily_wide.parquet"
DEFAULT_QUALITY = PROJECT_ROOT / "data/processed/daily_long.parquet"
DEFAULT_VALIDATION_MASKS = PROJECT_ROOT / "masks/validation"
DEFAULT_OUTPUT = PROJECT_ROOT / "checkpoints/deep_baselines"
LEGACY_MODEL_ALIASES = {"brits": "brits_lite", "saits": "saits_lite"}


def _ordered_inputs(
    wide_path: Path, quality_path: Path, mask_dir: Path
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    manifest = load_mask_manifest(mask_dir)
    axes = manifest.get("axes", {})
    dates = pd.DatetimeIndex(pd.to_datetime(axes.get("date"))).normalize()
    stations = [str(value) for value in axes.get("station", [])]
    variables = [str(value) for value in axes.get("variable", [])]
    if len(dates) == 0 or not stations or not variables:
        raise ValueError("mask manifest must define date, station, and variable axes")

    wide = pd.read_parquet(wide_path)
    if "date" not in wide or "split" not in wide:
        raise KeyError("daily_wide must contain date and split")
    wide["date"] = pd.to_datetime(wide["date"]).dt.normalize()
    if wide["date"].duplicated().any():
        raise ValueError("daily_wide contains duplicate dates")
    wide = wide.set_index("date").reindex(dates)
    if wide["split"].isna().any():
        raise ValueError("daily_wide does not cover every mask-axis date")

    columns = [f"{station}_{variable}" for station in stations for variable in variables]
    missing_columns = [column for column in columns if column not in wide]
    if missing_columns:
        raise KeyError(f"daily_wide is missing value columns: {missing_columns}")
    values = wide.loc[:, columns].apply(pd.to_numeric, errors="coerce").to_numpy(np.float32)

    quality = pd.read_parquet(quality_path)
    required = {"date", "station_id", "variable", "quality_approved"}
    missing = required - set(quality.columns)
    if missing:
        raise KeyError(f"daily_long is missing columns: {sorted(missing)}")
    quality = quality.loc[:, list(required)].copy()
    quality["date"] = pd.to_datetime(quality["date"]).dt.normalize()
    if quality.duplicated(["date", "station_id", "variable"]).any():
        raise ValueError("daily_long contains duplicate date/station/variable rows")
    pivot = quality.pivot(
        index="date", columns=["station_id", "variable"], values="quality_approved"
    )
    ordered_columns = pd.MultiIndex.from_product([stations, variables])
    pivot = pivot.reindex(index=dates, columns=ordered_columns).fillna(False)
    eligible = pivot.to_numpy(dtype=bool).reshape(values.shape)
    values[~eligible] = np.nan
    split = wide["split"].astype(str).to_numpy()
    return values, eligible, split, manifest


def _exact_training_mask(
    values: np.ndarray, eligible: np.ndarray, rate: float, seed: int
) -> np.ndarray:
    if not 0.0 < rate < 1.0:
        raise ValueError("training mask rate must be between 0 and 1")
    candidates = eligible & np.isfinite(values)
    result = np.zeros_like(candidates, dtype=bool)
    rng = np.random.default_rng(seed)
    for feature in range(values.shape[1]):
        positions = np.flatnonzero(candidates[:, feature])
        count = int(np.floor(len(positions) * rate + 0.5))
        if count:
            result[rng.choice(positions, size=count, replace=False), feature] = True
    if not result.any():
        raise ValueError("training mask selected no eligible values")
    return result


def _validation_windows(
    values: np.ndarray,
    validation_rows: np.ndarray,
    library: dict[str, tuple[np.ndarray, dict[str, Any]]],
    window_size: int,
    stride: int,
) -> tuple[np.ndarray, np.ndarray]:
    value_parts: list[np.ndarray] = []
    mask_parts: list[np.ndarray] = []
    validation_values = values[validation_rows]
    for artificial_3d, _ in library.values():
        artificial = np.asarray(artificial_3d, dtype=bool).reshape(len(values), -1)
        selected = artificial[validation_rows]
        if not selected.any():
            continue
        window_values, window_masks = make_windows(
            validation_values,
            selected,
            window_size,
            stride=stride,
            require_masked_target=True,
        )
        value_parts.append(window_values)
        mask_parts.append(window_masks)
    if not value_parts:
        raise ValueError("fixed validation library contains no validation targets")
    return np.concatenate(value_parts), np.concatenate(mask_parts)


def train(args: argparse.Namespace) -> dict[str, Path]:
    values, eligible, split, manifest = _ordered_inputs(
        args.data, args.quality_data, args.validation_masks
    )
    training_rows = split == "train"
    validation_rows = split == "validation"
    if not training_rows.any() or not validation_rows.any():
        raise ValueError("prepared data must contain train and validation splits")

    window_size = (
        min(args.window_size, 64, int(training_rows.sum()), int(validation_rows.sum()))
        if args.smoke
        else args.window_size
    )
    stride = args.stride or max(1, window_size // 2)
    training_values = values[training_rows]
    training_hidden = _exact_training_mask(
        training_values,
        eligible[training_rows],
        args.train_mask_rate,
        args.seed,
    )
    train_values, train_masks = make_windows(
        training_values,
        training_hidden,
        window_size,
        stride=stride,
        require_masked_target=True,
    )
    validation_values, validation_masks = _validation_windows(
        values,
        validation_rows,
        load_mask_library(args.validation_masks),
        window_size,
        stride,
    )
    if args.smoke:
        train_values, train_masks = train_values[:8], train_masks[:8]
        validation_values, validation_masks = (
            validation_values[:4],
            validation_masks[:4],
        )

    epochs = min(args.epochs, 2) if args.smoke else args.epochs
    patience = min(args.patience, 2) if args.smoke else args.patience
    hidden_size = min(args.hidden_size, 16) if args.smoke else args.hidden_size
    d_model = min(args.d_model, 16) if args.smoke else args.d_model
    n_heads = min(args.n_heads, 2) if args.smoke else args.n_heads
    while d_model % n_heads:
        n_heads -= 1
    d_ff = min(args.d_ff, 32) if args.smoke else args.d_ff

    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}
    canonical_models = tuple(
        dict.fromkeys(LEGACY_MODEL_ALIASES.get(name, name) for name in args.models)
    )
    for model_name in canonical_models:
        if model_name == "brits_lite":
            model = BRITSImputer(
                values.shape[1], hidden_size=hidden_size, seed=args.seed
            )
        elif model_name == "saits_lite":
            model = SAITSImputer(
                values.shape[1],
                d_model=d_model,
                n_heads=n_heads,
                n_layers=args.n_layers,
                d_ff=d_ff,
                seed=args.seed,
            )
        else:
            raise ValueError(f"unsupported model: {model_name}")
        model.fit(
            train_values,
            train_masks,
            validation_values=validation_values,
            validation_mask=validation_masks,
            epochs=epochs,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            patience=patience,
            verbose=args.verbose,
        )
        checkpoint = model.save_checkpoint(args.output_dir / f"{model_name}.pt")
        history_path = args.output_dir / f"{model_name}_history.json"
        history_path.write_text(
            json.dumps(
                {
                    **model.history_,
                    "model": model_name,
                    "seed": args.seed,
                    "window_size": window_size,
                    "feature_axes": {
                        "order": manifest["axes"]["order"],
                        "station": manifest["axes"]["station"],
                        "variable": manifest["axes"]["variable"],
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        outputs[model_name] = checkpoint
        print(
            f"saved {model_name} checkpoint to {checkpoint} "
            f"(best epoch {model.history_['best_epoch']})"
        )
    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--quality-data", type=Path, default=DEFAULT_QUALITY)
    parser.add_argument("--validation-masks", type=Path, default=DEFAULT_VALIDATION_MASKS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=["brits_lite", "saits_lite", "brits", "saits"],
        default=["brits_lite", "saits_lite"],
        help="local lightweight models; brits/saits are migration-only aliases",
    )
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--window-size", type=int, default=368)
    parser.add_argument("--stride", type=int)
    parser.add_argument("--train-mask-rate", type=float, default=0.15)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-5)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--hidden-size", type=int, default=64)
    parser.add_argument("--d-model", type=int, default=64)
    parser.add_argument("--n-heads", type=int, default=4)
    parser.add_argument("--n-layers", type=int, default=1)
    parser.add_argument("--d-ff", type=int, default=128)
    parser.add_argument("--smoke", action="store_true", help="two tiny CPU epochs on a few windows")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> None:
    train(build_parser().parse_args())


if __name__ == "__main__":
    main()
