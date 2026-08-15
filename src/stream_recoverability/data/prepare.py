"""Prepare aligned daily tables, time splits, scaling parameters, and windows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from .loading import load_stations
from .schema import RAW_VARIABLES, SPLIT_RANGES, WINDOW_SIZES

TIME_FEATURE_COLUMNS = (
    "day_of_year_sin",
    "day_of_year_cos",
    "month_sin",
    "month_cos",
    "year_index",
    "is_leap_year",
    "season",
)


def align_daily_calendar(long_data: pd.DataFrame) -> pd.DataFrame:
    """Align all stations and variables to the union daily calendar."""

    key_columns = ["date", "station_id", "raw_name"]
    duplicated = long_data.duplicated(key_columns, keep=False)
    if duplicated.any():
        sample = long_data.loc[duplicated, key_columns].head().to_dict("records")
        raise ValueError(f"Duplicate station/date/variable rows cannot be aligned: {sample}")

    data = long_data.copy()
    data["date"] = pd.to_datetime(data["date"]).dt.normalize()
    calendar = pd.date_range(data["date"].min(), data["date"].max(), freq="D")
    station_ids = list(dict.fromkeys(data["station_id"].astype(str)))
    available_raw_names = set(data["raw_name"])
    raw_names = [name for name in RAW_VARIABLES if name in available_raw_names]
    raw_names.extend(sorted(available_raw_names.difference(raw_names)))
    full_index = pd.MultiIndex.from_product(
        [calendar, station_ids, raw_names], names=key_columns
    )

    static_columns = ["variable", "raw_unit", "unit", "source"]
    static = (
        data[["station_id", "raw_name", *static_columns]]
        .drop_duplicates(["station_id", "raw_name"])
        .set_index(["station_id", "raw_name"])
    )
    aligned = data.set_index(key_columns).reindex(full_index).reset_index()
    for column in static_columns:
        lookup = static[column]
        missing = aligned[column].isna()
        aligned.loc[missing, column] = [
            lookup.loc[(station_id, raw_name)]
            for station_id, raw_name in aligned.loc[missing, ["station_id", "raw_name"]].itertuples(
                index=False, name=None
            )
        ]

    aligned["natural_observed"] = aligned["natural_observed"].fillna(False).astype(bool)
    aligned["quality_approved"] = aligned["quality_approved"].fillna(False).astype(bool)
    aligned["qc_status"] = aligned["qc_status"].fillna("source_missing")
    aligned["raw_value"] = aligned["raw_value"].astype(float)
    aligned["value"] = aligned["value"].astype(float)
    return aligned


def assign_time_split(
    frame: pd.DataFrame,
    split_ranges: Mapping[str, tuple[str, str]] = SPLIT_RANGES,
) -> pd.DataFrame:
    """Assign fixed chronological train/validation/test labels."""

    result = frame.copy()
    dates = pd.to_datetime(result["date"]).dt.normalize()
    labels = np.full(len(result), "unassigned", dtype=object)
    for split, (start, end) in split_ranges.items():
        in_range = dates.between(pd.Timestamp(start), pd.Timestamp(end), inclusive="both")
        labels[in_range.to_numpy()] = split
    result["split"] = labels
    return result


def add_time_features(frame: pd.DataFrame, origin_year: int = 2006) -> pd.DataFrame:
    """Add leakage-free calendar features while preserving leap days."""

    result = frame.copy()
    dates = pd.to_datetime(result["date"]).dt.normalize()
    days_in_year = np.where(dates.dt.is_leap_year, 366.0, 365.0)
    day_angle = 2.0 * np.pi * (dates.dt.dayofyear.to_numpy() - 1.0) / days_in_year
    month_angle = 2.0 * np.pi * (dates.dt.month.to_numpy() - 1.0) / 12.0
    result["day_of_year_sin"] = np.sin(day_angle)
    result["day_of_year_cos"] = np.cos(day_angle)
    result["month_sin"] = np.sin(month_angle)
    result["month_cos"] = np.cos(month_angle)
    result["year_index"] = (dates.dt.year - origin_year).astype(int)
    result["is_leap_year"] = dates.dt.is_leap_year.astype(bool)
    month = dates.dt.month
    result["season"] = np.select(
        [month.isin([12, 1, 2]), month.isin([3, 4, 5]), month.isin([6, 7, 8])],
        ["DJF", "MAM", "JJA"],
        default="SON",
    )
    return result


def to_daily_wide(long_data: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Pivot converted values to ``{station_id}_{variable}`` columns."""

    duplicated = long_data.duplicated(["date", "station_id", "variable"], keep=False)
    if duplicated.any():
        sample = long_data.loc[duplicated, ["date", "station_id", "variable"]].head().to_dict("records")
        raise ValueError(f"Duplicate canonical variable rows cannot be pivoted: {sample}")
    value_wide = long_data.pivot(index="date", columns=["station_id", "variable"], values="value")
    value_wide = value_wide.sort_index()
    value_wide.columns = [f"{station}_{variable}" for station, variable in value_wide.columns]
    measurement_columns = list(value_wide.columns)
    wide = value_wide.reset_index()

    split_by_date = long_data[["date", "split"]].drop_duplicates()
    if split_by_date.duplicated("date").any():
        raise ValueError("A date was assigned to more than one split")
    wide = wide.merge(split_by_date, on="date", how="left", validate="one_to_one")
    wide = add_time_features(wide)
    leading = ["date", "split", *TIME_FEATURE_COLUMNS]
    return wide[[*leading, *measurement_columns]], measurement_columns


def fit_train_scaler(
    wide_data: pd.DataFrame,
    measurement_columns: Sequence[str],
) -> dict[str, Any]:
    """Fit means and population standard deviations using training dates only."""

    train = wide_data.loc[wide_data["split"] == "train"]
    if train.empty:
        raise ValueError("Cannot fit scaler: no rows are labelled train")
    features: dict[str, dict[str, float | int]] = {}
    for column in measurement_columns:
        values = pd.to_numeric(train[column], errors="coerce").dropna()
        if values.empty:
            raise ValueError(f"Cannot fit scaler: {column} has no approved training values")
        standard_deviation = float(values.std(ddof=0))
        features[column] = {
            "mean": float(values.mean()),
            "scale": standard_deviation if standard_deviation > 0 else 1.0,
            "observed_count": int(len(values)),
        }
    return {
        "fitted_split": "train",
        "train_start": SPLIT_RANGES["train"][0],
        "train_end": SPLIT_RANGES["train"][1],
        "features": features,
    }


def apply_scaler(wide_data: pd.DataFrame, scaler: Mapping[str, Any]) -> pd.DataFrame:
    """Apply a previously fitted scaler without changing missing values."""

    result = wide_data.copy()
    for column, parameters in scaler["features"].items():
        result[column] = (result[column] - parameters["mean"]) / parameters["scale"]
    return result


def build_windows(
    split_data: pd.DataFrame,
    window_size: int,
    feature_columns: Sequence[str],
    stride: int = 1,
) -> tuple[np.ndarray, np.ndarray, tuple[str, ...]]:
    """Construct a zero-copy sliding view for one chronological split.

    The caller must pass only one split, which prevents windows from crossing
    train/validation/test boundaries.
    """

    if window_size not in WINDOW_SIZES:
        raise ValueError(f"window_size must be one of {WINDOW_SIZES}")
    if stride < 1:
        raise ValueError("stride must be at least 1")
    if "split" in split_data:
        labels = split_data["split"].dropna().unique()
        if len(labels) > 1:
            raise ValueError("Filter to a single split before constructing windows")

    ordered = split_data.sort_values("date").reset_index(drop=True)
    dates = pd.to_datetime(ordered["date"]).to_numpy(dtype="datetime64[ns]")
    if len(dates) > 1 and not np.all(np.diff(dates) == np.timedelta64(1, "D")):
        raise ValueError("Window input dates must be unique and daily-continuous")
    features = tuple(feature_columns)
    values = ordered.loc[:, features].to_numpy(dtype=float)
    if len(ordered) < window_size:
        return (
            np.empty((0, window_size, len(features)), dtype=float),
            np.empty((0, window_size), dtype="datetime64[ns]"),
            features,
        )

    value_windows = np.lib.stride_tricks.sliding_window_view(values, window_size, axis=0)
    value_windows = np.moveaxis(value_windows, -1, 1)[::stride]
    date_windows = np.lib.stride_tricks.sliding_window_view(dates, window_size)[::stride]
    return value_windows, date_windows, features


def window_counts(wide_data: pd.DataFrame, sizes: Iterable[int] = WINDOW_SIZES) -> pd.DataFrame:
    """Return constructible window counts without materialising window tensors."""

    rows = []
    for split in ("train", "validation", "test"):
        count = int((wide_data["split"] == split).sum())
        for size in sizes:
            if size not in WINDOW_SIZES:
                raise ValueError(f"window_size must be one of {WINDOW_SIZES}")
            rows.append({"split": split, "window_size": size, "window_count": max(count - size + 1, 0)})
    return pd.DataFrame(rows)


def write_prepared_outputs(
    long_data: pd.DataFrame,
    wide_data: pd.DataFrame,
    scaler: Mapping[str, Any],
    output_dir: str | Path,
) -> None:
    output_dir = Path(output_dir)
    split_dir = output_dir / "splits"
    split_dir.mkdir(parents=True, exist_ok=True)
    long_data.to_parquet(output_dir / "daily_long.parquet", index=False)
    wide_data.to_parquet(output_dir / "daily_wide.parquet", index=False)
    for split in ("train", "validation", "test"):
        wide_data.loc[wide_data["split"] == split].to_parquet(split_dir / f"{split}.parquet", index=False)
    with (output_dir / "scaler.json").open("w", encoding="utf-8") as handle:
        json.dump(scaler, handle, ensure_ascii=False, indent=2, allow_nan=False)


def prepare_daily_data(
    raw_dir: str | Path,
    data_dictionary: str | Path | None,
    output_dir: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Run the complete first-stage preparation pipeline."""

    loaded = load_stations(raw_dir, data_dictionary)
    aligned = assign_time_split(align_daily_calendar(loaded))
    wide, measurement_columns = to_daily_wide(aligned)
    scaler = fit_train_scaler(wide, measurement_columns)
    write_prepared_outputs(aligned, wide, scaler, output_dir)
    return aligned, wide, scaler
