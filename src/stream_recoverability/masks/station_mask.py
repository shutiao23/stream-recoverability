"""Single-station hydro-only and full-site outage masks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from ._common import (
    MaskAndMetadata,
    normalize_indices,
    normalize_labels,
    stable_scenario_id,
    validate_eligible,
    validate_seed,
)
from .block_mask import generate_block_mask

_HYDRO_NAMES = {
    "T",
    "F",
    "L",
    "WTEMP",
    "FLOW",
    "WLEVEL",
    "WATER_TEMPERATURE",
    "WATER_LEVEL",
}


def _hydro_indices(
    variable_names: Sequence[str] | None,
    variable_count: int,
    explicit: Sequence[int] | None,
) -> np.ndarray:
    if explicit is not None:
        return normalize_indices(explicit, variable_count, "hydro_variable_indices")
    if variable_names is not None:
        selected = [
            index
            for index, value in enumerate(variable_names)
            if str(value).strip().upper() in _HYDRO_NAMES
        ]
        if selected:
            return np.asarray(selected, dtype=int)
    if variable_count == 3:
        return np.arange(3, dtype=int)
    raise ValueError(
        "hydro-only mode needs variable_names containing T/F/L or hydro_variable_indices"
    )


def generate_station_outage_mask(
    eligible: np.ndarray,
    station_index: int,
    length: int,
    *,
    mode: str = "hydro-only",
    hydro_variable_indices: Sequence[int] | None = None,
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
    """Mask T/F/L (hydro-only) or every channel (full-site) at one station."""

    eligible = validate_eligible(eligible)
    seed = validate_seed(seed)
    station = normalize_indices([station_index], eligible.shape[1], "station_index")
    station_labels = normalize_labels(station_ids, eligible.shape[1], "S")
    variable_labels = normalize_labels(variable_names, eligible.shape[2], "V")
    normalized_mode = str(mode).strip().lower().replace("_", "-")
    if normalized_mode == "hydro-only":
        variables = _hydro_indices(
            variable_names, eligible.shape[2], hydro_variable_indices
        )
        mode_token = "HYDRO"
    elif normalized_mode == "full-site":
        variables = np.arange(eligible.shape[2], dtype=int)
        mode_token = "ALL"
    else:
        raise ValueError("mode must be 'hydro-only' or 'full-site'")

    if scenario_id is None:
        scenario_id = stable_scenario_id(
            "SITE",
            station_labels[int(station[0])],
            mode_token,
            f"D{int(length):03d}",
            f"M{int(month):02d}" if month is not None else season,
            split,
            seed=seed,
        )

    mask, metadata = generate_block_mask(
        eligible,
        length,
        station_indices=station,
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
        forced_start_index=forced_start_index,
        center_index=center_index,
        center_date=center_date,
        anchor_id=anchor_id,
        anchor_metadata=anchor_metadata,
    )
    metadata["mask_type"] = "station_outage"
    metadata["outage_mode"] = normalized_mode
    return mask, metadata


station_outage_mask = generate_station_outage_mask
