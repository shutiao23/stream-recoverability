"""Single contiguous-block masks with optional calendar stratification."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ._common import (
    MaskAndMetadata,
    apply_block,
    base_metadata,
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
) -> MaskAndMetadata:
    """Mask one exact-length block that has eligible truth in every channel."""

    eligible = validate_eligible(eligible)
    seed = validate_seed(seed)
    if not isinstance(length, (int, np.integer)) or int(length) <= 0:
        raise ValueError("length must be a positive integer")
    length = int(length)
    stations = normalize_indices(station_indices, eligible.shape[1], "station_indices")
    variables = normalize_indices(variable_indices, eligible.shape[2], "variable_indices")
    station_labels = normalize_labels(station_ids, eligible.shape[1], "S")
    variable_labels = normalize_labels(variable_names, eligible.shape[2], "V")
    normalized_dates = normalize_dates(dates, eligible.shape[0])

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
        stratum = f" in season {season}" if season else f" in month {month}" if month else ""
        raise ValueError(f"no eligible block of length {length}{stratum}")

    rng = np.random.default_rng(seed)
    start = int(rng.choice(candidates))
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
            f"M{int(month):02d}" if month is not None else season,
            split,
            seed=seed,
        )

    start_month = (
        int(date_months(normalized_dates[[start]])[0]) if normalized_dates is not None else None
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
            "season": season_for_month(start_month) if start_month is not None else season,
            "start_month": start_month,
            "event_type": None,
            "context": int(context),
        }
    )
    return mask, metadata


block_mask = generate_block_mask

