"""Synchronous and asynchronous multi-channel outage masks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from ._common import (
    MaskAndMetadata,
    apply_block,
    base_metadata,
    centered_bounds,
    display_position,
    ensure_subset,
    normalize_dates,
    normalize_indices,
    normalize_labels,
    selected_labels,
    stable_scenario_id,
    validate_eligible,
    validate_seed,
)
from .block_mask import generate_block_mask


def generate_network_outage_mask(
    eligible: np.ndarray,
    station_indices: Sequence[int],
    length: int,
    *,
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
    center_index: int | None = None,
    center_date: object | None = None,
    anchor_id: str | None = None,
    anchor_metadata: Mapping[str, Any] | None = None,
) -> MaskAndMetadata:
    """Mask the same exact block at two or more stations."""

    eligible = validate_eligible(eligible)
    seed = validate_seed(seed)
    stations = normalize_indices(station_indices, eligible.shape[1], "station_indices")
    if stations.size < 2:
        raise ValueError("network outage requires at least two stations")
    variables = normalize_indices(variable_indices, eligible.shape[2], "variable_indices")
    station_labels = normalize_labels(station_ids, eligible.shape[1], "S")
    variable_labels = normalize_labels(variable_names, eligible.shape[2], "V")

    if scenario_id is None:
        scenario_id = stable_scenario_id(
            "PAIR" if stations.size == 2 else "NET",
            "".join(selected_labels(station_labels, stations)),
            "".join(selected_labels(variable_labels, variables)),
            f"D{int(length):03d}",
            "O100",
            split,
            seed=seed,
        )

    mask, metadata = generate_block_mask(
        eligible,
        length,
        station_indices=stations,
        variable_indices=variables,
        seed=seed,
        dates=dates,
        season=season,
        month=month,
        context=context,
        station_ids=station_labels,
        variable_names=variable_labels,
        split=split,
        scenario_id=scenario_id,
        center_index=center_index,
        center_date=center_date,
        anchor_id=anchor_id,
        anchor_metadata=anchor_metadata,
    )
    metadata["mask_type"] = "network_outage"
    metadata["overlap_ratio"] = 1.0
    return mask, metadata


def _build_groups(
    stations: np.ndarray,
    variables: np.ndarray,
    axis: str,
    groups: Sequence[tuple[Sequence[int], Sequence[int]]] | None,
    station_count: int,
    variable_count: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    if groups is not None:
        if axis != "groups":
            raise ValueError("set axis='groups' when explicit groups are supplied")
        result = [
            (
                normalize_indices(s, station_count, "group station indices"),
                normalize_indices(v, variable_count, "group variable indices"),
            )
            for s, v in groups
        ]
    elif axis == "station":
        result = [(np.asarray([station]), variables) for station in stations]
    elif axis == "variable":
        result = [(stations, np.asarray([variable])) for variable in variables]
    else:
        raise ValueError("axis must be 'station', 'variable', or 'groups'")
    if len(result) < 2:
        raise ValueError("asynchronous masking requires at least two groups")
    return result


def generate_async_mask(
    eligible: np.ndarray,
    length: int,
    overlap_ratio: float,
    *,
    station_indices: Sequence[int] | None = None,
    variable_indices: Sequence[int] | None = None,
    axis: str = "station",
    groups: Sequence[tuple[Sequence[int], Sequence[int]]] | None = None,
    seed: int = 0,
    dates: Sequence[object] | np.ndarray | None = None,
    context: int = 0,
    station_ids: Sequence[str] | None = None,
    variable_names: Sequence[str] | None = None,
    split: str | None = None,
    scenario_id: str | None = None,
    center_index: int | None = None,
    center_date: object | None = None,
    anchor_id: str | None = None,
    anchor_metadata: Mapping[str, Any] | None = None,
) -> MaskAndMetadata:
    """Mask staggered equal-length groups at 0, 0.5, or 1 overlap.

    For more than two groups, ``overlap_ratio`` applies to adjacent groups.
    """

    eligible = validate_eligible(eligible)
    seed = validate_seed(seed)
    if not isinstance(length, (int, np.integer)) or int(length) <= 0:
        raise ValueError("length must be a positive integer")
    length = int(length)
    overlap_ratio = float(overlap_ratio)
    if overlap_ratio not in {0.0, 0.5, 1.0}:
        raise ValueError("overlap_ratio must be 0, 0.5, or 1")
    if not isinstance(context, (int, np.integer)) or int(context) < 0:
        raise ValueError("context must be a non-negative integer")
    context = int(context)

    stations = normalize_indices(station_indices, eligible.shape[1], "station_indices")
    variables = normalize_indices(variable_indices, eligible.shape[2], "variable_indices")
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
        center_index = int(supplied_anchor["center_index"])
    elif (
        center_index is not None
        and supplied_anchor.get("center_index") is not None
        and int(center_index) != int(supplied_anchor["center_index"])
    ):
        raise ValueError("center_index conflicts with anchor_metadata")
    if center_date is None and supplied_anchor.get("center_date") is not None:
        center_date = supplied_anchor["center_date"]
    elif center_date is not None and supplied_anchor.get("center_date") is not None:
        requested = np.asarray([center_date], dtype="datetime64[D]")[0]
        anchored = np.asarray(
            [supplied_anchor["center_date"]], dtype="datetime64[D]"
        )[0]
        if requested != anchored:
            raise ValueError("center_date conflicts with anchor_metadata")
    if supplied_anchor.get("mask_seed") is not None and int(
        supplied_anchor["mask_seed"]
    ) != seed:
        raise ValueError("seed conflicts with anchor_metadata.mask_seed")
    if supplied_anchor.get("max_supported_length") is not None and int(
        supplied_anchor["max_supported_length"]
    ) < length:
        raise ValueError("length exceeds anchor_metadata.max_supported_length")
    if center_date is not None:
        if normalized_dates is None:
            raise ValueError("dates are required when center_date is supplied")
        requested_date = np.asarray([center_date], dtype="datetime64[D]")[0]
        matches = np.flatnonzero(normalized_dates == requested_date)
        if matches.size != 1:
            raise ValueError("center_date does not identify exactly one date")
        matched_center = int(matches[0])
        if center_index is not None and int(center_index) != matched_center:
            raise ValueError("center_index and center_date identify different positions")
        center_index = matched_center
    if center_index is not None:
        if isinstance(center_index, (bool, np.bool_)) or not isinstance(
            center_index, (int, np.integer)
        ):
            raise TypeError("center_index must be an integer")
        center_index = int(center_index)
    grouped_channels = _build_groups(
        stations,
        variables,
        axis,
        groups,
        eligible.shape[1],
        eligible.shape[2],
    )

    shift_float = length * (1.0 - overlap_ratio)
    shift = round(shift_float)
    if not np.isclose(shift, shift_float):
        raise ValueError("length cannot represent the requested overlap exactly")
    actual_overlap = (length - shift) / length
    last_offset = shift * (len(grouped_channels) - 1)
    latest_base = eligible.shape[0] - last_offset - length - context
    candidates: list[int] = []
    for base in range(context, latest_base + 1):
        valid = True
        for group_index, (group_stations, group_variables) in enumerate(grouped_channels):
            start = base + group_index * shift
            selected = eligible[
                start : start + length, group_stations
            ][:, :, group_variables]
            if not selected.all():
                valid = False
                break
        if valid:
            candidates.append(base)
    if not candidates:
        raise ValueError("no eligible asynchronous layout satisfies the requested overlap")

    if center_index is None:
        rng = np.random.default_rng(seed)
        base = int(rng.choice(np.asarray(candidates, dtype=int)))
        selection_mode = "seeded_random"
        center_index = base + (length - 1) // 2
    else:
        base, _ = centered_bounds(center_index, length, eligible.shape[0])
        if base not in candidates:
            raise ValueError(
                "fixed target anchor cannot support the requested asynchronous layout"
            )
        selection_mode = "fixed_target_center"
    starts = [base + index * shift for index in range(len(grouped_channels))]
    mask = np.zeros_like(eligible, dtype=bool)
    for start, (group_stations, group_variables) in zip(
        starts, grouped_channels, strict=True
    ):
        apply_block(mask, start, length, group_stations, group_variables)
    ensure_subset(mask, eligible)

    involved_stations = np.unique(
        np.concatenate([value[0] for value in grouped_channels])
    )
    involved_variables = np.unique(
        np.concatenate([value[1] for value in grouped_channels])
    )
    if scenario_id is None:
        scenario_id = stable_scenario_id(
            "ASYNC",
            "".join(selected_labels(station_labels, involved_stations)),
            "".join(selected_labels(variable_labels, involved_variables)),
            f"D{length:03d}",
            f"O{round(overlap_ratio * 100):02d}",
            axis,
            split,
            seed=seed,
        )

    ends = [start + length - 1 for start in starts]
    metadata = base_metadata(
        eligible=eligible,
        mask=mask,
        station_indices=involved_stations,
        variable_indices=involved_variables,
        station_labels=station_labels,
        variable_labels=variable_labels,
        scenario_id=scenario_id,
        split=split,
        seed=seed,
        mask_type="async",
    )
    metadata.update(
        {
            "missing_rate": None,
            "gap_lengths": [length] * len(grouped_channels),
            "start_indices": starts,
            "end_indices": ends,
            "start_dates": [display_position(value, normalized_dates) for value in starts],
            "end_dates": [display_position(value, normalized_dates) for value in ends],
            "overlap_ratio": actual_overlap,
            "requested_overlap_ratio": overlap_ratio,
            "overlap_axis": axis,
            "group_count": len(grouped_channels),
            "season": None,
            "event_type": None,
            "context": context,
            "selection_mode": selection_mode,
            "center_index": center_index,
            "center_date": display_position(center_index, normalized_dates),
            "anchor_id": str(anchor_id) if anchor_id is not None else None,
            "target_group_index": 0,
            "target_gap_start_index": starts[0],
            "target_gap_end_index": ends[0],
            "target_gap_start_date": display_position(starts[0], normalized_dates),
            "target_gap_end_date": display_position(ends[0], normalized_dates),
        }
    )
    if supplied_anchor:
        metadata["anchor_metadata"] = {
            str(key): value.item() if isinstance(value, np.generic) else value
            for key, value in supplied_anchor.items()
        }
    return mask, metadata


network_outage_mask = generate_network_outage_mask
async_mask = generate_async_mask
