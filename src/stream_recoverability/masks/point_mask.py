"""Exact-rate random point masks."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from itertools import pairwise

import numpy as np

from ._common import (
    MaskAndMetadata,
    base_metadata,
    date_months,
    ensure_subset,
    normalize_dates,
    normalize_indices,
    normalize_labels,
    rate_token,
    selected_labels,
    stable_scenario_id,
    validate_eligible,
    validate_rate,
    validate_seed,
)

_SEASON_CODES = ("DJF", "MAM", "JJA", "SON")


def _count_for_rate(count: int, rate: float) -> int:
    """Return the nearest attainable integer count, with halves rounded up."""

    return min(count, int(np.floor(count * rate + 0.5)))


def _season_code(month: int) -> str:
    if month in (12, 1, 2):
        return "DJF"
    if month in (3, 4, 5):
        return "MAM"
    if month in (6, 7, 8):
        return "JJA"
    return "SON"


def _validate_ranking(
    ranking: Sequence[int],
    candidates: np.ndarray,
    *,
    name: str,
) -> np.ndarray:
    raw = np.asarray(list(ranking))
    if raw.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if raw.size == 0:
        result = np.empty(0, dtype=int)
    elif not np.issubdtype(raw.dtype, np.integer):
        raise TypeError(f"{name} must contain integer date indices")
    else:
        result = raw.astype(int, copy=False)
    if np.unique(result).size != result.size:
        raise ValueError(f"{name} must not contain duplicate date indices")
    if result.size != candidates.size or not np.array_equal(
        np.sort(result), candidates
    ):
        raise ValueError(f"{name} must rank every eligible candidate exactly once")
    return result


def _seeded_candidate_ranking(
    candidates: np.ndarray,
    *,
    seed: int,
    dates: np.ndarray | None,
    season_balanced: bool,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if candidates.size == 0:
        return np.empty(0, dtype=int)
    if not season_balanced:
        return rng.permutation(candidates)
    if dates is None:
        raise ValueError("dates are required for a season-balanced point ranking")

    months = date_months(dates)
    queues: dict[str, list[int]] = {}
    for season in _SEASON_CODES:
        values = candidates[
            np.array(
                [_season_code(int(months[index])) == season for index in candidates]
            )
        ]
        queues[season] = [int(value) for value in rng.permutation(values)]
    positions = {season: 0 for season in _SEASON_CODES}
    ranking: list[int] = []
    while len(ranking) < len(candidates):
        added = False
        for season in _SEASON_CODES:
            position = positions[season]
            if position < len(queues[season]):
                ranking.append(queues[season][position])
                positions[season] += 1
                added = True
        if not added:
            raise AssertionError(
                "season-balanced ranking stalled before exhausting candidates"
            )
    return np.asarray(ranking, dtype=int)


def _ranking_digest(
    ranking: np.ndarray | Mapping[tuple[int, int], np.ndarray] | None,
) -> str | None:
    if ranking is None:
        return None
    digest = hashlib.sha256()
    if isinstance(ranking, Mapping):
        for key in sorted(ranking):
            digest.update(np.asarray(key, dtype=np.int64).tobytes())
            digest.update(np.asarray(ranking[key], dtype=np.int64).tobytes())
    else:
        digest.update(np.asarray(ranking, dtype=np.int64).tobytes())
    return digest.hexdigest()


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
    candidate_ranking: (
        Sequence[int] | Mapping[tuple[int, int], Sequence[int]] | None
    ) = None,
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
    variables = normalize_indices(
        variable_indices, eligible.shape[2], "variable_indices"
    )
    station_labels = normalize_labels(station_ids, eligible.shape[1], "S")
    variable_labels = normalize_labels(variable_names, eligible.shape[2], "V")
    rng = np.random.default_rng(seed)
    mask = np.zeros_like(eligible, dtype=bool)
    validated_ranking: np.ndarray | dict[tuple[int, int], np.ndarray] | None = None

    if synchronized:
        day_eligible = eligible[:, stations][:, :, variables].all(axis=(1, 2))
        candidates = np.flatnonzero(day_eligible)
        count = _count_for_rate(candidates.size, missing_rate)
        if missing_rate > 0 and candidates.size == 0:
            raise ValueError("no dates are jointly eligible for synchronized masking")
        if candidate_ranking is None:
            chosen = rng.choice(candidates, size=count, replace=False)
        else:
            if isinstance(candidate_ranking, Mapping):
                raise TypeError(
                    "synchronized candidate_ranking must be one sequence of date indices"
                )
            validated_ranking = _validate_ranking(
                candidate_ranking, candidates, name="candidate_ranking"
            )
            chosen = validated_ranking[:count]
        mask[np.ix_(chosen, stations, variables)] = True
        sampled_dates = int(count)
    else:
        sampled_dates = None
        if candidate_ranking is not None and not isinstance(candidate_ranking, Mapping):
            raise TypeError(
                "independent candidate_ranking must map (station, variable) to rankings"
            )
        ranking_map = dict(candidate_ranking or {})
        expected_keys = {
            (int(station), int(variable))
            for station in stations
            for variable in variables
        }
        if candidate_ranking is not None and set(ranking_map) != expected_keys:
            raise ValueError(
                "independent candidate_ranking keys must exactly match selected channels"
            )
        validated_map: dict[tuple[int, int], np.ndarray] = {}
        for station in stations:
            for variable in variables:
                candidates = np.flatnonzero(eligible[:, station, variable])
                count = _count_for_rate(candidates.size, missing_rate)
                if missing_rate > 0 and candidates.size == 0:
                    raise ValueError(
                        f"station {station}, variable {variable} has no eligible cells"
                    )
                key = (int(station), int(variable))
                if candidate_ranking is None:
                    chosen = rng.choice(candidates, size=count, replace=False)
                else:
                    validated_map[key] = _validate_ranking(
                        ranking_map[key], candidates, name=f"candidate_ranking[{key}]"
                    )
                    chosen = validated_map[key][:count]
                mask[chosen, station, variable] = True
        if candidate_ranking is not None:
            validated_ranking = validated_map

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
            "selection_mode": (
                "supplied_candidate_ranking"
                if candidate_ranking is not None
                else "seeded_random"
            ),
            "candidate_ranking_sha256": _ranking_digest(validated_ranking),
        }
    )
    return mask, metadata


def generate_nested_point_mask_family(
    eligible: np.ndarray,
    missing_rates: Sequence[float] = (0.10, 0.30, 0.50),
    *,
    station_indices: Sequence[int] | None = None,
    variable_indices: Sequence[int] | None = None,
    seed: int = 0,
    synchronized: bool = True,
    dates: Sequence[object] | np.ndarray | None = None,
    season_balanced: bool = True,
    station_ids: Sequence[str] | None = None,
    variable_names: Sequence[str] | None = None,
    split: str | None = None,
) -> dict[float, MaskAndMetadata]:
    """Generate a point-rate family from prefixes of one fixed ranking.

    The default 10%, 30%, and 50% masks therefore satisfy explicit set nesting;
    this property does not depend on repeated random calls producing compatible
    samples.  When requested, candidates are shuffled within each season and
    then interleaved DJF/MAM/JJA/SON so every prefix is season-balanced to the
    extent allowed by eligibility.
    """

    eligible = validate_eligible(eligible)
    seed = validate_seed(seed)
    rates = tuple(validate_rate(rate) for rate in missing_rates)
    if not rates:
        raise ValueError("missing_rates must not be empty")
    if len(set(rates)) != len(rates) or any(
        current <= previous for previous, current in pairwise(rates)
    ):
        raise ValueError("missing_rates must be unique and strictly increasing")
    stations = normalize_indices(station_indices, eligible.shape[1], "station_indices")
    variables = normalize_indices(
        variable_indices, eligible.shape[2], "variable_indices"
    )
    station_labels = normalize_labels(station_ids, eligible.shape[1], "S")
    variable_labels = normalize_labels(variable_names, eligible.shape[2], "V")
    normalized_dates = normalize_dates(dates, eligible.shape[0])

    if synchronized:
        candidates = np.flatnonzero(
            eligible[:, stations][:, :, variables].all(axis=(1, 2))
        )
        ranking: np.ndarray | dict[
            tuple[int, int], np.ndarray
        ] = _seeded_candidate_ranking(
            candidates,
            seed=seed,
            dates=normalized_dates,
            season_balanced=season_balanced,
        )
    else:
        ranking = {}
        for station in stations:
            for variable in variables:
                candidates = np.flatnonzero(eligible[:, station, variable])
                channel_seed = int(
                    np.random.SeedSequence(
                        [seed, int(station), int(variable)]
                    ).generate_state(1, dtype=np.uint32)[0]
                )
                ranking[(int(station), int(variable))] = _seeded_candidate_ranking(
                    candidates,
                    seed=channel_seed,
                    dates=normalized_dates,
                    season_balanced=season_balanced,
                )

    selected_station_labels = selected_labels(station_labels, stations)
    selected_variable_labels = selected_labels(variable_labels, variables)
    family_id = stable_scenario_id(
        "PNTFAMILY",
        "".join(selected_station_labels),
        "".join(selected_variable_labels),
        "SYNC" if synchronized else "IND",
        split,
        seed=seed,
    )
    result: dict[float, MaskAndMetadata] = {}
    previous_mask: np.ndarray | None = None
    for rate in rates:
        mask, metadata = generate_point_mask(
            eligible,
            rate,
            station_indices=stations,
            variable_indices=variables,
            seed=seed,
            synchronized=synchronized,
            station_ids=station_labels,
            variable_names=variable_labels,
            split=split,
            candidate_ranking=ranking,
        )
        if previous_mask is not None and np.any(previous_mask & ~mask):
            raise AssertionError("point-mask family violated prefix nesting")
        previous_mask = mask
        season_counts: dict[str, int] | None = None
        if normalized_dates is not None:
            selected = mask[:, stations][:, :, variables].sum(axis=(1, 2))
            months = date_months(normalized_dates)
            season_counts = {
                season: int(
                    selected[
                        np.array(
                            [_season_code(int(month)) == season for month in months]
                        )
                    ].sum()
                )
                for season in _SEASON_CODES
            }
        metadata.update(
            {
                "point_family_id": family_id,
                "nested_rates": list(rates),
                "ranking_season_balanced": bool(season_balanced),
                "season_counts": season_counts,
            }
        )
        result[rate] = (mask, metadata)
    return result


point_mask = generate_point_mask


__all__ = [
    "generate_nested_point_mask_family",
    "generate_point_mask",
    "point_mask",
]
