"""Masks constrained to externally defined hydrological/event conditions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from ._common import (
    MaskAndMetadata,
    ensure_subset,
    normalize_indices,
    normalize_labels,
    selected_labels,
    stable_scenario_id,
    validate_eligible,
    validate_seed,
)
from .block_mask import generate_block_mask
from .point_mask import generate_point_mask


def _event_eligible(
    eligible: np.ndarray,
    event_condition: np.ndarray,
    *,
    invert: bool = False,
) -> np.ndarray:
    condition = np.asarray(event_condition)
    if condition.dtype != np.bool_:
        raise TypeError("event_condition must be boolean")
    if condition.shape == (eligible.shape[0],):
        condition = np.broadcast_to(condition[:, None, None], eligible.shape)
    elif condition.shape != eligible.shape:
        raise ValueError("event_condition must have shape (date,) or match eligible")
    return eligible & (~condition if invert else condition)


def generate_event_mask(
    eligible: np.ndarray,
    event_condition: np.ndarray,
    event_type: str,
    *,
    length: int | None = None,
    missing_rate: float = 1.0,
    station_indices: Sequence[int] | None = None,
    variable_indices: Sequence[int] | None = None,
    seed: int = 0,
    synchronized: bool = True,
    dates: Sequence[object] | np.ndarray | None = None,
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
    event_id: str | None = None,
    control_id: str | None = None,
    pair_id: str | None = None,
    catalog_role: str = "stress",
    event_metadata: Mapping[str, Any] | None = None,
) -> MaskAndMetadata:
    """Generate an aggregate stress, event episode, or matched-control mask.

    ``stress`` preserves the aggregate event-conditioned design.  Catalog
    episodes and controls require immutable identities and a fixed block
    location.  An episode masks its complete audit window (which may include a
    heat-event merge gap or flood rising/recession days), whereas a matched
    control requires every hidden day to be non-event.
    """

    eligible = validate_eligible(eligible)
    seed = validate_seed(seed)
    stations = normalize_indices(station_indices, eligible.shape[1], "station_indices")
    variables = normalize_indices(
        variable_indices, eligible.shape[2], "variable_indices"
    )
    station_labels = normalize_labels(station_ids, eligible.shape[1], "S")
    variable_labels = normalize_labels(variable_names, eligible.shape[2], "V")
    event_name = str(event_type).strip()
    if not event_name:
        raise ValueError("event_type must not be empty")
    role = str(catalog_role).strip().lower()
    if role not in {"stress", "event_episode", "matched_control"}:
        raise ValueError(
            "catalog_role must be stress, event_episode, or matched_control"
        )
    if role != "stress":
        if length is None:
            raise ValueError("catalog event/control masks require length")
        if forced_start_index is None and center_index is None and center_date is None:
            raise ValueError(
                "catalog event/control masks require a fixed anchor location"
            )
        if not str(event_id or "").strip() or not str(anchor_id or "").strip():
            raise ValueError(
                "catalog event/control masks require event_id and anchor_id"
            )
        if not str(pair_id or "").strip():
            raise ValueError("catalog event/control masks require pair_id")
        if role == "matched_control" and not str(control_id or "").strip():
            raise ValueError("matched-control masks require control_id")
    elif control_id is not None:
        raise ValueError("aggregate stress masks must not declare control_id")

    event_eligible = _event_eligible(eligible, event_condition)
    constrained = (
        event_eligible
        if role == "stress"
        else _event_eligible(eligible, event_condition, invert=True)
        if role == "matched_control"
        else eligible
    )

    if scenario_id is None:
        detail = (
            f"D{int(length):03d}" if length is not None else f"P{missing_rate * 100:g}"
        )
        scenario_id = stable_scenario_id(
            "EVT",
            "".join(selected_labels(station_labels, stations)),
            "".join(selected_labels(variable_labels, variables)),
            event_name,
            detail,
            split,
            seed=seed,
        )

    if length is None:
        mask, metadata = generate_point_mask(
            constrained,
            missing_rate,
            station_indices=stations,
            variable_indices=variables,
            seed=seed,
            synchronized=synchronized,
            station_ids=station_labels,
            variable_names=variable_labels,
            split=split,
            scenario_id=scenario_id,
        )
    else:
        mask, metadata = generate_block_mask(
            constrained,
            length,
            station_indices=stations,
            variable_indices=variables,
            seed=seed,
            dates=dates,
            context=context,
            station_ids=station_labels,
            variable_names=variable_labels,
            split=split,
            scenario_id=scenario_id,
            forced_start_index=forced_start_index,
            center_index=center_index,
            center_date=center_date,
            anchor_id=anchor_id,
            anchor_metadata=anchor_metadata,
        )
    ensure_subset(mask, eligible)
    event_overlap = int((mask & event_eligible).sum())
    if role == "event_episode" and event_overlap == 0:
        raise ValueError("catalog event window contains no event-condition cell")
    if role == "matched_control" and event_overlap:
        raise ValueError("matched-control window contains an event-condition cell")
    supplied_event_metadata = dict(event_metadata or {})
    expected_identity = {
        "event_id": event_id,
        "control_id": control_id,
        "anchor_id": anchor_id,
        "pair_id": pair_id,
        "catalog_role": role,
    }
    for key, expected in expected_identity.items():
        if (
            key in supplied_event_metadata
            and supplied_event_metadata[key] is not None
            and str(supplied_event_metadata[key]) != str(expected)
        ):
            raise ValueError(f"{key} conflicts with event_metadata")
    metadata.update(supplied_event_metadata)
    metadata.update(
        {
            "mask_type": (
                "event"
                if role == "stress"
                else "event_episode"
                if role == "event_episode"
                else "event_control"
            ),
            "event_type": event_name,
            "catalog_role": role,
            "event_id": str(event_id) if event_id is not None else None,
            "control_id": str(control_id) if control_id is not None else None,
            "anchor_id": str(anchor_id) if anchor_id is not None else None,
            "pair_id": str(pair_id) if pair_id is not None else None,
            "event_condition_cells_in_mask": event_overlap,
            "event_eligible_cells": int(
                event_eligible[:, stations][:, :, variables].sum()
            ),
            "control_eligible_cells": (
                int(constrained[:, stations][:, :, variables].sum())
                if role == "matched_control"
                else None
            ),
        }
    )
    if role == "stress" and length is None:
        metadata["selection_mode"] = (
            "deterministic_all_event_cells"
            if float(missing_rate) == 1.0
            else "seeded_event_subset"
        )
    return mask, metadata


event_mask = generate_event_mask
