"""Masks constrained to externally defined hydrological/event conditions."""

from __future__ import annotations

from collections.abc import Sequence

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


def _event_eligible(eligible: np.ndarray, event_condition: np.ndarray) -> np.ndarray:
    condition = np.asarray(event_condition)
    if condition.dtype != np.bool_:
        raise TypeError("event_condition must be boolean")
    if condition.shape == (eligible.shape[0],):
        condition = np.broadcast_to(condition[:, None, None], eligible.shape)
    elif condition.shape != eligible.shape:
        raise ValueError("event_condition must have shape (date,) or match eligible")
    return eligible & condition


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
) -> MaskAndMetadata:
    """Generate a point or contiguous mask only inside an event condition."""

    eligible = validate_eligible(eligible)
    seed = validate_seed(seed)
    stations = normalize_indices(station_indices, eligible.shape[1], "station_indices")
    variables = normalize_indices(variable_indices, eligible.shape[2], "variable_indices")
    station_labels = normalize_labels(station_ids, eligible.shape[1], "S")
    variable_labels = normalize_labels(variable_names, eligible.shape[2], "V")
    event_name = str(event_type).strip()
    if not event_name:
        raise ValueError("event_type must not be empty")
    constrained = _event_eligible(eligible, event_condition)

    if scenario_id is None:
        detail = f"D{int(length):03d}" if length is not None else f"P{missing_rate * 100:g}"
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
        )
    ensure_subset(mask, eligible)
    metadata["mask_type"] = "event"
    metadata["event_type"] = event_name
    metadata["event_eligible_cells"] = int(
        constrained[:, stations][:, :, variables].sum()
    )
    return mask, metadata


event_mask = generate_event_mask

