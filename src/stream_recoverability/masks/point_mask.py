"""Exact-rate random point masks."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ._common import (
    MaskAndMetadata,
    base_metadata,
    ensure_subset,
    normalize_indices,
    normalize_labels,
    rate_token,
    selected_labels,
    stable_scenario_id,
    validate_eligible,
    validate_rate,
    validate_seed,
)


def _count_for_rate(count: int, rate: float) -> int:
    """Return the nearest attainable integer count, with halves rounded up."""

    return min(count, int(np.floor(count * rate + 0.5)))


def generate_point_mask(
    eligible: np.ndarray,
    missing_rate: float,
    *,
    station_indices: Sequence[int] | None = None,
    variable_indices: Sequence[int] | None = None,
    seed: int = 0,
    synchronized: bool = True,
    station_ids: Sequence[str] | None = None,
    variable_names: Sequence[str] | None = None,
    split: str | None = None,
    scenario_id: str | None = None,
) -> MaskAndMetadata:
    """Generate an exact-count point mask on eligible cells.

    With ``synchronized=True``, one set of dates is sampled where every selected
    station-variable channel is eligible. With ``False``, each selected channel
    receives its own exact-count sample.
    """

    eligible = validate_eligible(eligible)
    missing_rate = validate_rate(missing_rate)
    seed = validate_seed(seed)
    stations = normalize_indices(station_indices, eligible.shape[1], "station_indices")
    variables = normalize_indices(variable_indices, eligible.shape[2], "variable_indices")
    station_labels = normalize_labels(station_ids, eligible.shape[1], "S")
    variable_labels = normalize_labels(variable_names, eligible.shape[2], "V")
    rng = np.random.default_rng(seed)
    mask = np.zeros_like(eligible, dtype=bool)

    if synchronized:
        day_eligible = eligible[:, stations][:, :, variables].all(axis=(1, 2))
        candidates = np.flatnonzero(day_eligible)
        count = _count_for_rate(candidates.size, missing_rate)
        if missing_rate > 0 and candidates.size == 0:
            raise ValueError("no dates are jointly eligible for synchronized masking")
        chosen = rng.choice(candidates, size=count, replace=False)
        mask[np.ix_(chosen, stations, variables)] = True
        sampled_dates = int(count)
    else:
        sampled_dates = None
        for station in stations:
            for variable in variables:
                candidates = np.flatnonzero(eligible[:, station, variable])
                count = _count_for_rate(candidates.size, missing_rate)
                if missing_rate > 0 and candidates.size == 0:
                    raise ValueError(
                        f"station {station}, variable {variable} has no eligible cells"
                    )
                chosen = rng.choice(candidates, size=count, replace=False)
                mask[chosen, station, variable] = True

    selected_station_labels = selected_labels(station_labels, stations)
    selected_variable_labels = selected_labels(variable_labels, variables)
    if scenario_id is None:
        scenario_id = stable_scenario_id(
            "PNT",
            "".join(selected_station_labels),
            "".join(selected_variable_labels),
            "SYNC" if synchronized else "IND",
            rate_token(missing_rate),
            split,
            seed=seed,
        )

    ensure_subset(mask, eligible)
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
        mask_type="point",
    )
    metadata.update(
        {
            "missing_rate": missing_rate,
            "synchronized": bool(synchronized),
            "sampled_dates": sampled_dates,
            "gap_lengths": [],
            "start_dates": [],
            "end_dates": [],
            "overlap_ratio": None,
            "season": None,
            "event_type": None,
        }
    )
    return mask, metadata


point_mask = generate_point_mask

