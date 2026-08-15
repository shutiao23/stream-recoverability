"""Single contiguous-block masks with optional calendar stratification."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from ._common import (
    MaskAndMetadata,
    apply_block,
    base_metadata,
    centered_bounds,
    date_months,
    display_position,
    ensure_subset,
    filter_stratified_starts,
    normalize_dates,
    normalize_indices,
    normalize_labels,
    season_for_month,
    selected_labels,
    stable_scenario_id,
    target_day_eligibility,
    valid_block_starts,
    validate_eligible,
    validate_seed,
)


def _optional_index(value: object, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise TypeError(f"{name} must be an integer")
    result = int(value)
    if result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _normalize_center_date(value: object) -> np.datetime64:
    try:
        result = np.asarray([value], dtype="datetime64[D]")[0]
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid center_date: {value!r}") from error
    if np.isnat(result):
        raise ValueError("center_date must not be missing")
    return result


def generate_block_mask(
    eligible: np.ndarray,
    length: int,
    *,
    station_indices: Sequence[int] | None = None,
    variable_indices: Sequence[int] | None = None,
    seed: int = 0,
    dates: Sequence[object] | np.ndarray | None = None,
    season: str | None = None,
    month: int | None = None,
    context: int = 0,
    station_ids: Sequence[str] | None = None,
    variable_names: Sequence[str] | None = None,
    split: str | None = None,
    scenario_id: str | None = None,
    forced_start_index: int | None = None,
    center_index: int | None = None,
    center_date: object | None = None,
    anchor_id: str | None = None,
    anchor_metadata: Mapping[str, Any] | None = None,
) -> MaskAndMetadata:
    """Mask one exact-length block that has eligible truth in every channel.

    The legacy seeded random selection remains the default.  A caller may
    instead force a start, or supply a center index/date for nested frontier
    blocks.  Even lengths use :func:`centered_bounds`' earlier-middle rule.
    """

    eligible = validate_eligible(eligible)
    seed = validate_seed(seed)
    if not isinstance(length, (int, np.integer)) or int(length) <= 0:
        raise ValueError("length must be a positive integer")
    length = int(length)
    stations = normalize_indices(station_indices, eligible.shape[1], "station_indices")
    variables = normalize_indices(
        variable_indices, eligible.shape[2], "variable_indices"
    )
    station_labels = normalize_labels(station_ids, eligible.shape[1], "S")
    variable_labels = normalize_labels(variable_names, eligible.shape[2], "V")
    normalized_dates = normalize_dates(dates, eligible.shape[0])

    supplied_anchor = dict(anchor_metadata or {})
    if anchor_id is None and supplied_anchor.get("anchor_id") is not None:
        anchor_id = str(supplied_anchor["anchor_id"])
    elif (
        anchor_id is not None
        and supplied_anchor.get("anchor_id") is not None
        and str(anchor_id) != str(supplied_anchor["anchor_id"])
    ):
        raise ValueError("anchor_id conflicts with anchor_metadata")
    if center_index is None and supplied_anchor.get("center_index") is not None:
        center_index = supplied_anchor["center_index"]
    elif (
        center_index is not None
        and supplied_anchor.get("center_index") is not None
        and int(center_index) != int(supplied_anchor["center_index"])
    ):
        raise ValueError("center_index conflicts with anchor_metadata")
    if center_date is None and supplied_anchor.get("center_date") is not None:
        center_date = supplied_anchor["center_date"]
    elif (
        center_date is not None
        and supplied_anchor.get("center_date") is not None
        and _normalize_center_date(center_date)
        != _normalize_center_date(supplied_anchor["center_date"])
    ):
        raise ValueError("center_date conflicts with anchor_metadata")
    if supplied_anchor.get("mask_seed") is not None and int(
        supplied_anchor["mask_seed"]
    ) != int(seed):
        raise ValueError("seed conflicts with anchor_metadata.mask_seed")
    if (
        supplied_anchor.get("max_supported_length") is not None
        and int(supplied_anchor["max_supported_length"]) < length
    ):
        raise ValueError("length exceeds anchor_metadata.max_supported_length")

    forced_start_index = _optional_index(forced_start_index, "forced_start_index")
    center_index = _optional_index(center_index, "center_index")
    requested_center_date = (
        _normalize_center_date(center_date) if center_date is not None else None
    )
    if requested_center_date is not None:
        if normalized_dates is None:
            raise ValueError("dates are required when center_date is supplied")
        matches = np.flatnonzero(normalized_dates == requested_center_date)
        if matches.size != 1:
            raise ValueError(
                f"center_date {str(requested_center_date)!r} does not identify exactly one date"
            )
        matched_center = int(matches[0])
        if center_index is not None and center_index != matched_center:
            raise ValueError(
                "center_index and center_date identify different positions"
            )
        center_index = matched_center

    day_eligible = target_day_eligibility(eligible, stations, variables)
    candidates = valid_block_starts(day_eligible, length)
    candidates = filter_stratified_starts(
        candidates,
        normalized_dates,
        n_dates=eligible.shape[0],
        season=season,
        month=month,
        context=context,
        length=length,
    )
    if candidates.size == 0:
        stratum = (
            f" in season {season}" if season else f" in month {month}" if month else ""
        )
        raise ValueError(f"no eligible block of length {length}{stratum}")

    if center_index is not None:
        centered_start, _ = centered_bounds(center_index, length, eligible.shape[0])
        if forced_start_index is not None and forced_start_index != centered_start:
            raise ValueError(
                "forced_start_index is inconsistent with center_index/center_date "
                "under the centered even-length convention"
            )
        start = centered_start
        selection_mode = (
            "fixed_center_and_start"
            if forced_start_index is not None
            else "fixed_center"
        )
    elif forced_start_index is not None:
        start = forced_start_index
        center_index = start + (length - 1) // 2
        selection_mode = "forced_start"
    else:
        rng = np.random.default_rng(seed)
        start = int(rng.choice(candidates))
        center_index = start + (length - 1) // 2
        selection_mode = "seeded_random"
    if not np.any(candidates == start):
        raise ValueError(
            f"requested block start {start} is not eligible for length {length}, "
            "stratification, and context constraints"
        )
    mask = np.zeros_like(eligible, dtype=bool)
    apply_block(mask, start, length, stations, variables)
    ensure_subset(mask, eligible)

    station_tokens = selected_labels(station_labels, stations)
    variable_tokens = selected_labels(variable_labels, variables)
    if scenario_id is None:
        scenario_id = stable_scenario_id(
            "BLK1",
            "".join(station_tokens),
            "".join(variable_tokens),
            f"D{length:03d}",
            anchor_id,
            f"M{int(month):02d}" if month is not None else season,
            split,
            seed=seed,
        )

    start_month = (
        int(date_months(normalized_dates[[start]])[0])
        if normalized_dates is not None
        else None
    )
    metadata = base_metadata(
        eligible=eligible,
        mask=mask,
        station_indices=stations,
        variable_indices=variables,
        station_labels=station_labels,
        variable_labels=variable_labels,
        scenario_id=scenario_id,
        split=split,
        seed=seed,
        mask_type="block",
    )
    metadata.update(
        {
            "missing_rate": None,
            "gap_lengths": [length],
            "start_indices": [start],
            "end_indices": [start + length - 1],
            "start_dates": [display_position(start, normalized_dates)],
            "end_dates": [display_position(start + length - 1, normalized_dates)],
            "overlap_ratio": None,
            "season": season_for_month(start_month)
            if start_month is not None
            else season,
            "start_month": start_month,
            "event_type": None,
            "context": int(context),
            "selection_mode": selection_mode,
            "center_index": int(center_index),
            "center_date": display_position(int(center_index), normalized_dates),
            "anchor_id": str(anchor_id) if anchor_id is not None else None,
        }
    )
    if supplied_anchor:
        normalized_anchor = {
            str(key): (
                str(value.astype("datetime64[D]"))
                if isinstance(value, np.datetime64)
                else value.item()
                if isinstance(value, np.generic)
                else value
            )
            for key, value in supplied_anchor.items()
        }
        metadata["anchor_metadata"] = normalized_anchor
        for key in (
            "data_version",
            "evaluation_split",
            "source_split",
            "hydrologic_state",
            "max_supported_length",
            "mask_seed",
            "target",
            "year",
        ):
            if key in normalized_anchor and key not in metadata:
                metadata[key] = normalized_anchor[key]
    return mask, metadata


block_mask = generate_block_mask
