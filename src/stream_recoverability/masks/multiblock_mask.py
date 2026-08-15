"""Fixed-total-budget multi-block masks."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ._common import (
    MaskAndMetadata,
    apply_block,
    base_metadata,
    display_position,
    ensure_subset,
    normalize_dates,
    normalize_indices,
    normalize_labels,
    selected_labels,
    stable_scenario_id,
    target_day_eligibility,
    valid_block_starts,
    validate_eligible,
    validate_seed,
)


FIXED_BUDGET_SEGMENTS: dict[int, tuple[int, ...]] = {
    10: (3, 3, 4),
    30: (10, 10, 10),
    90: (30, 30, 30),
    180: (60, 60, 60),
}


def _find_spaced_starts(
    candidates: list[np.ndarray],
    lengths: tuple[int, ...],
    minimum_gap: int,
    rng: np.random.Generator,
) -> list[int] | None:
    randomized = [rng.permutation(values) for values in candidates]

    def search(segment: int, previous_end: int, chosen: list[int]) -> list[int] | None:
        if segment == len(lengths):
            return chosen.copy()
        valid = randomized[segment]
        if previous_end >= 0:
            valid = valid[valid >= previous_end + minimum_gap]
        for value in valid:
            start = int(value)
            chosen.append(start)
            result = search(segment + 1, start + lengths[segment], chosen)
            if result is not None:
                return result
            chosen.pop()
        return None

    return search(0, -1, [])


def generate_multiblock_mask(
    eligible: np.ndarray,
    total_budget: int,
    *,
    segment_lengths: Sequence[int] | None = None,
    minimum_gap: int = 30,
    station_indices: Sequence[int] | None = None,
    variable_indices: Sequence[int] | None = None,
    seed: int = 0,
    dates: Sequence[object] | np.ndarray | None = None,
    context: int = 0,
    station_ids: Sequence[str] | None = None,
    variable_names: Sequence[str] | None = None,
    split: str | None = None,
    scenario_id: str | None = None,
) -> MaskAndMetadata:
    """Mask separated blocks whose lengths sum exactly to ``total_budget``."""

    eligible = validate_eligible(eligible)
    seed = validate_seed(seed)
    if not isinstance(total_budget, (int, np.integer)) or int(total_budget) <= 0:
        raise ValueError("total_budget must be a positive integer")
    total_budget = int(total_budget)
    if not isinstance(minimum_gap, (int, np.integer)) or int(minimum_gap) < 0:
        raise ValueError("minimum_gap must be a non-negative integer")
    minimum_gap = int(minimum_gap)
    if not isinstance(context, (int, np.integer)) or int(context) < 0:
        raise ValueError("context must be a non-negative integer")
    context = int(context)

    if segment_lengths is None:
        try:
            lengths = FIXED_BUDGET_SEGMENTS[total_budget]
        except KeyError as error:
            raise ValueError(
                "segment_lengths is required unless total_budget is 10, 30, 90, or 180"
            ) from error
    else:
        lengths = tuple(int(value) for value in segment_lengths)
        if not lengths or any(value <= 0 for value in lengths):
            raise ValueError("segment_lengths must contain positive integers")
    if sum(lengths) != total_budget:
        raise ValueError("segment_lengths must sum exactly to total_budget")

    stations = normalize_indices(station_indices, eligible.shape[1], "station_indices")
    variables = normalize_indices(variable_indices, eligible.shape[2], "variable_indices")
    station_labels = normalize_labels(station_ids, eligible.shape[1], "S")
    variable_labels = normalize_labels(variable_names, eligible.shape[2], "V")
    normalized_dates = normalize_dates(dates, eligible.shape[0])
    day_eligible = target_day_eligibility(eligible, stations, variables)

    candidate_sets: list[np.ndarray] = []
    for length in lengths:
        starts = valid_block_starts(day_eligible, length)
        starts = starts[
            (starts >= context)
            & (starts + length + context <= eligible.shape[0])
        ]
        candidate_sets.append(starts)
    if any(values.size == 0 for values in candidate_sets):
        raise ValueError("at least one segment length has no eligible candidate")

    rng = np.random.default_rng(seed)
    starts = _find_spaced_starts(candidate_sets, lengths, minimum_gap, rng)
    if starts is None:
        raise ValueError(
            "no eligible multi-block layout satisfies the requested minimum gap"
        )

    mask = np.zeros_like(eligible, dtype=bool)
    for start, length in zip(starts, lengths, strict=True):
        apply_block(mask, start, length, stations, variables)
    ensure_subset(mask, eligible)

    station_tokens = selected_labels(station_labels, stations)
    variable_tokens = selected_labels(variable_labels, variables)
    if scenario_id is None:
        layout = "x".join(str(value) for value in lengths)
        scenario_id = stable_scenario_id(
            "BLKM",
            "".join(station_tokens),
            "".join(variable_tokens),
            f"D{total_budget:03d}",
            layout,
            f"G{minimum_gap}",
            split,
            seed=seed,
        )

    ends = [start + length - 1 for start, length in zip(starts, lengths, strict=True)]
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
        mask_type="multiblock",
    )
    metadata.update(
        {
            "missing_rate": None,
            "total_budget": total_budget,
            "gap_lengths": list(lengths),
            "minimum_gap": minimum_gap,
            "start_indices": starts,
            "end_indices": ends,
            "start_dates": [display_position(value, normalized_dates) for value in starts],
            "end_dates": [display_position(value, normalized_dates) for value in ends],
            "overlap_ratio": None,
            "season": None,
            "event_type": None,
            "context": context,
        }
    )
    return mask, metadata


multiblock_mask = generate_multiblock_mask

