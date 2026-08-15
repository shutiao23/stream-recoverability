"""Small shared helpers for deterministic artificial-missingness masks."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import numpy as np

MaskAndMetadata = tuple[np.ndarray, dict[str, Any]]


def validate_eligible(eligible: np.ndarray) -> np.ndarray:
    array = np.asarray(eligible)
    if array.ndim != 3:
        raise ValueError("eligible must have shape (date, station, variable)")
    if array.dtype != np.bool_:
        raise TypeError("eligible must be a boolean array")
    return array


def normalize_indices(
    indices: Sequence[int] | None, size: int, name: str
) -> np.ndarray:
    if indices is None:
        result = np.arange(size, dtype=int)
    else:
        result = np.asarray(list(indices), dtype=int)
    if result.ndim != 1 or result.size == 0:
        raise ValueError(f"{name} must contain at least one index")
    if np.any(result < 0) or np.any(result >= size):
        raise IndexError(f"{name} contains an out-of-range index")
    if np.unique(result).size != result.size:
        raise ValueError(f"{name} must not contain duplicate indices")
    return result


def normalize_labels(labels: Sequence[str] | None, size: int, prefix: str) -> list[str]:
    if labels is None:
        return [f"{prefix}{index + 1}" for index in range(size)]
    result = [str(label) for label in labels]
    if len(result) != size:
        raise ValueError(f"expected {size} {prefix} labels, got {len(result)}")
    return result


def normalize_dates(
    dates: Sequence[object] | np.ndarray | None, size: int
) -> np.ndarray | None:
    if dates is None:
        return None
    result = np.asarray(dates, dtype="datetime64[D]")
    if result.ndim != 1 or result.size != size:
        raise ValueError(f"dates must contain exactly {size} entries")
    if np.isnat(result).any():
        raise ValueError("dates must not contain missing values")
    return result


def validate_seed(seed: int) -> int:
    if not isinstance(seed, (int, np.integer)) or int(seed) < 0:
        raise ValueError("seed must be a non-negative integer")
    return int(seed)


def validate_rate(rate: float) -> float:
    result = float(rate)
    if not 0.0 <= result <= 1.0:
        raise ValueError("missing_rate must be between 0 and 1")
    return result


def target_day_eligibility(
    eligible: np.ndarray, station_indices: np.ndarray, variable_indices: np.ndarray
) -> np.ndarray:
    selected = eligible[:, station_indices][:, :, variable_indices]
    return selected.all(axis=(1, 2))


def valid_block_starts(day_eligible: np.ndarray, length: int) -> np.ndarray:
    if not isinstance(length, (int, np.integer)) or int(length) <= 0:
        raise ValueError("length must be a positive integer")
    length = int(length)
    if length > day_eligible.size:
        return np.empty(0, dtype=int)
    windows = np.lib.stride_tricks.sliding_window_view(day_eligible, length)
    return np.flatnonzero(windows.all(axis=1))


def centered_bounds(
    center_index: int,
    length: int,
    n_dates: int | None = None,
) -> tuple[int, int]:
    """Return half-open bounds for a block centered on one fixed date.

    For an even length, ``center_index`` is the earlier of the two middle
    positions.  This convention makes every shorter block a strict set subset
    of every longer block around the same center whenever their lengths differ.
    """

    if isinstance(center_index, (bool, np.bool_)) or not isinstance(
        center_index, (int, np.integer)
    ):
        raise TypeError("center_index must be an integer")
    if isinstance(length, (bool, np.bool_)) or not isinstance(
        length, (int, np.integer)
    ):
        raise TypeError("length must be an integer")
    center_index = int(center_index)
    length = int(length)
    if center_index < 0:
        raise ValueError("center_index must be non-negative")
    if length <= 0:
        raise ValueError("length must be a positive integer")
    start = center_index - (length - 1) // 2
    stop = start + length
    if n_dates is not None:
        if isinstance(n_dates, (bool, np.bool_)) or not isinstance(
            n_dates, (int, np.integer)
        ):
            raise TypeError("n_dates must be an integer")
        if int(n_dates) <= 0:
            raise ValueError("n_dates must be positive")
        if start < 0 or stop > int(n_dates):
            raise ValueError(
                f"centered block [{start}, {stop}) is outside a {int(n_dates)}-date axis"
            )
    return start, stop


def season_for_month(month: int) -> str:
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"


def date_months(dates: np.ndarray) -> np.ndarray:
    return (dates.astype("datetime64[M]").astype(int) % 12 + 1).astype(int)


def filter_stratified_starts(
    starts: np.ndarray,
    dates: np.ndarray | None,
    *,
    n_dates: int,
    season: str | None = None,
    month: int | None = None,
    context: int = 0,
    length: int,
) -> np.ndarray:
    if not isinstance(context, (int, np.integer)) or int(context) < 0:
        raise ValueError("context must be a non-negative integer")
    context = int(context)
    keep = (starts >= context) & (starts + length + context <= n_dates)
    result = starts[keep]

    if season is not None and month is not None:
        raise ValueError("choose either season or month stratification, not both")
    if season is None and month is None:
        return result
    if dates is None:
        raise ValueError("dates are required for season or month stratification")

    months = date_months(dates[result])
    if month is not None:
        if not isinstance(month, (int, np.integer)) or not 1 <= int(month) <= 12:
            raise ValueError("month must be in 1..12")
        return result[months == int(month)]

    normalized = str(season).strip().lower()
    aliases = {"fall": "autumn"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"spring", "summer", "autumn", "winter"}:
        raise ValueError("season must be spring, summer, autumn/fall, or winter")
    return result[np.array([season_for_month(value) == normalized for value in months])]


def apply_block(
    mask: np.ndarray,
    start: int,
    length: int,
    station_indices: np.ndarray,
    variable_indices: np.ndarray,
) -> None:
    dates = np.arange(start, start + length, dtype=int)
    mask[np.ix_(dates, station_indices, variable_indices)] = True


def display_position(index: int, dates: np.ndarray | None) -> str | int:
    if dates is None:
        return int(index)
    return str(dates[index])


def selected_labels(labels: Sequence[str], indices: np.ndarray) -> list[str]:
    return [labels[int(index)] for index in indices]


def _token(value: object) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", str(value))
    return cleaned or "NA"


def rate_token(rate: float) -> str:
    percent = rate * 100.0
    text = f"{percent:.6f}".rstrip("0").rstrip(".").replace(".", "p")
    return f"P{text}"


def stable_scenario_id(prefix: str, *parts: object, seed: int) -> str:
    tokens = [_token(prefix), *(_token(part) for part in parts if part is not None)]
    tokens.append(f"R{int(seed):04d}")
    return "-".join(tokens)


def base_metadata(
    *,
    eligible: np.ndarray,
    mask: np.ndarray,
    station_indices: np.ndarray,
    variable_indices: np.ndarray,
    station_labels: Sequence[str],
    variable_labels: Sequence[str],
    scenario_id: str,
    split: str | None,
    seed: int,
    mask_type: str,
) -> dict[str, Any]:
    selected = eligible[:, station_indices][:, :, variable_indices]
    eligible_cells = int(selected.sum())
    masked_cells = int(mask.sum())
    matrix_eligible_cells = int(eligible.sum())
    return {
        "scenario_id": scenario_id,
        "split": split,
        "seed": int(seed),
        "mask_type": mask_type,
        "station_ids": selected_labels(station_labels, station_indices),
        "variables": selected_labels(variable_labels, variable_indices),
        "eligible_cells": eligible_cells,
        "masked_cells": masked_cells,
        "target_missing_rate": masked_cells / eligible_cells if eligible_cells else 0.0,
        "matrix_missing_rate": (
            masked_cells / matrix_eligible_cells if matrix_eligible_cells else 0.0
        ),
    }


def ensure_subset(mask: np.ndarray, eligible: np.ndarray) -> None:
    if mask.dtype != np.bool_ or mask.shape != eligible.shape:
        raise AssertionError("generated mask has an invalid shape or dtype")
    if np.any(mask & ~eligible):
        raise AssertionError("generated mask covers ineligible ground truth")
