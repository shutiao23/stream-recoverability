"""Save and load fixed validation/test mask libraries."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import numpy as np

from ._common import MaskAndMetadata


def _json_value(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return [_json_value(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _csv_value(value: Any) -> Any:
    value = _json_value(value)
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def save_mask_library(
    scenarios: Iterable[MaskAndMetadata],
    output_dir: str | Path,
    *,
    dates: Iterable[object] | None = None,
    station_ids: Iterable[str] | None = None,
    variable_names: Iterable[str] | None = None,
) -> Path:
    """Write ``masks.npz`` plus JSON/CSV manifests and return the directory."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    arrays: dict[str, np.ndarray] = {}
    records: list[dict[str, Any]] = []
    ids: set[str] = set()
    shape: tuple[int, ...] | None = None

    for index, (mask, metadata) in enumerate(scenarios):
        mask = np.asarray(mask)
        if mask.ndim != 3 or mask.dtype != np.bool_:
            raise ValueError("every artificial mask must be a 3D boolean array")
        if shape is None:
            shape = mask.shape
        elif mask.shape != shape:
            raise ValueError("all masks in one library must have the same shape")
        record = _json_value(dict(metadata))
        scenario_id = str(record.get("scenario_id", "")).strip()
        if not scenario_id:
            raise ValueError("every mask needs a non-empty scenario_id")
        if scenario_id in ids:
            raise ValueError(f"duplicate scenario_id: {scenario_id}")
        ids.add(scenario_id)
        array_key = f"mask_{index:06d}"
        record["array_key"] = array_key
        arrays[array_key] = mask
        records.append(record)

    if not records or shape is None:
        raise ValueError("cannot save an empty mask library")

    date_axis = [str(value) for value in dates] if dates is not None else None
    station_axis = [str(value) for value in station_ids] if station_ids is not None else None
    variable_axis = [str(value) for value in variable_names] if variable_names is not None else None
    if date_axis is not None and len(date_axis) != shape[0]:
        raise ValueError("dates length does not match the mask date axis")
    if station_axis is not None and len(station_axis) != shape[1]:
        raise ValueError("station_ids length does not match the mask station axis")
    if variable_axis is not None and len(variable_axis) != shape[2]:
        raise ValueError("variable_names length does not match the mask variable axis")

    manifest = {
        "axes": {
            "order": ["date", "station", "variable"],
            "shape": list(shape),
            "date": date_axis,
            "station": station_axis,
            "variable": variable_axis,
        },
        "scenarios": records,
    }
    np.savez_compressed(output / "masks.npz", **arrays)
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    preferred = [
        "array_key",
        "scenario_id",
        "split",
        "seed",
        "mask_type",
        "station_ids",
        "variables",
        "missing_rate",
        "gap_lengths",
        "start_dates",
        "end_dates",
        "overlap_ratio",
        "season",
        "event_type",
        "eligible_cells",
        "masked_cells",
        "target_missing_rate",
        "matrix_missing_rate",
    ]
    remaining = sorted(set().union(*(record.keys() for record in records)) - set(preferred))
    columns = [name for name in preferred if any(name in record for record in records)] + remaining
    with (output / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in records:
            writer.writerow({name: _csv_value(record.get(name)) for name in columns})
    return output


def load_mask_manifest(input_dir: str | Path) -> dict[str, Any]:
    path = Path(input_dir) / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_mask_library(input_dir: str | Path) -> dict[str, MaskAndMetadata]:
    """Load a library as ``scenario_id -> (artificial_mask, metadata)``."""

    directory = Path(input_dir)
    manifest = load_mask_manifest(directory)
    result: dict[str, MaskAndMetadata] = {}
    with np.load(directory / "masks.npz", allow_pickle=False) as archive:
        for stored in manifest["scenarios"]:
            metadata = dict(stored)
            array_key = metadata.pop("array_key")
            mask = np.asarray(archive[array_key], dtype=bool)
            result[str(metadata["scenario_id"])] = (mask, metadata)
    return result

