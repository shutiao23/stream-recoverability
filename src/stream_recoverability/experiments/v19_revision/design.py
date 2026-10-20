"""Paired feasible gap geometries, including repeated and equal-budget controls."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class GapDesign:
    key: str
    family: str
    length: int
    overlap_class: str
    replicate: int
    mask: np.ndarray


def overlap_class(share: float) -> str:
    if share == 0:
        return "none"
    if share >= 1 - 1e-12:
        return "full"
    return "partial"


def contiguous_starts(n_days: int, length: int, support: np.ndarray) -> dict[str, np.ndarray]:
    support = np.asarray(support, dtype=bool)
    if support.shape != (n_days,) or not support.any() or not 0 < length < n_days:
        raise ValueError("Require a nonempty support vector and a feasible positive gap length")
    starts = np.arange(1, n_days - length)
    cumulative = np.concatenate([[0], np.cumsum(support.astype(int))])
    share = (cumulative[starts + length] - cumulative[starts]) / support.sum()
    return {
        "none": starts[share == 0],
        "partial": starts[(share >= 0.15) & (share <= 0.85)],
        "full": starts[share >= 1 - 1e-12],
    }


def paired_gap_designs(
    support: np.ndarray,
    warm_season: np.ndarray,
    *,
    seed: int,
    lengths: tuple[int, ...] = (30, 60, 90),
    replicates: int = 4,
) -> tuple[list[GapDesign], list[dict]]:
    support = np.asarray(support, dtype=bool)
    warm_season = np.asarray(warm_season, dtype=bool)
    if warm_season.shape != support.shape or support.ndim != 1:
        raise ValueError("Warm season and support must be matching vectors")
    rng = np.random.default_rng(seed)
    designs, empty = [], []
    n_days = len(support)
    for length in lengths:
        by_class = contiguous_starts(n_days, length, support)
        for name, starts in by_class.items():
            if not len(starts):
                empty.append({"family": "crossed_contiguous", "length": length, "overlap_class": name, "reason": "no_feasible_start"})
                continue
            selected = rng.choice(starts, size=replicates, replace=len(starts) < replicates)
            for replicate, start in enumerate(selected):
                mask = np.zeros(n_days, dtype=bool)
                mask[start : start + length] = True
                designs.append(GapDesign(f"cross_{length}_{name}_{replicate}", "crossed_contiguous", length, name, replicate, mask))
        warm_starts = {
            name: np.array([start for start in starts if warm_season[start : start + length].all()], dtype=int)
            for name, starts in by_class.items()
        }
        if len(warm_starts["none"]) and len(warm_starts["full"]):
            for name in ("none", "full"):
                starts = warm_starts[name]
                selected = rng.choice(starts, size=replicates, replace=len(starts) < replicates)
                for replicate, start in enumerate(selected):
                    mask = np.zeros(n_days, dtype=bool)
                    mask[start : start + length] = True
                    designs.append(GapDesign(f"warm_{length}_{name}_{replicate}", "within_warm_season", length, name, replicate, mask))
        else:
            empty.append({"family": "within_warm_season", "length": length, "overlap_class": "paired_none_full", "reason": "both_classes_not_feasible"})
        warm_positions = np.flatnonzero(warm_season & (np.arange(n_days) > 0) & (np.arange(n_days) < n_days - 1))
        if len(warm_positions) >= length:
            for replicate in range(replicates):
                candidates = []
                for start in warm_positions:
                    if start + 9 <= n_days and warm_season[start : start + 9].all():
                        candidates.append(int(start))
                rng.shuffle(candidates)
                mask = np.zeros(n_days, dtype=bool)
                for start in candidates:
                    if mask[max(0, start - 1) : min(n_days, start + 10)].any():
                        continue
                    remaining = length - int(mask.sum())
                    if not remaining:
                        break
                    mask[start : start + min(9, remaining)] = True
                if mask.sum() == length:
                    share = float(mask[support].mean())
                    designs.append(GapDesign(f"fragment_{length}_{replicate}", "fragmented_equal_budget", length, overlap_class(share), replicate, mask))
                else:
                    empty.append({"family": "fragmented_equal_budget", "length": length, "overlap_class": "any", "reason": "insufficient_separated_warm_blocks"})
    return designs, empty


def event_relative_designs(events: np.ndarray, support: np.ndarray, *, lengths: tuple[int, ...] = (30, 60, 90)) -> tuple[list[GapDesign], list[dict]]:
    events = np.asarray(events, dtype=bool)
    support = np.asarray(support, dtype=bool)
    starts = np.flatnonzero(events & ~np.r_[False, events[:-1]])
    ends = np.flatnonzero(events & ~np.r_[events[1:], False]) + 1
    if not len(starts):
        return [], [{"family": "event_relative", "reason": "no_training_threshold_event_in_target_year"}]
    episode = int(np.argmax(ends - starts))
    event_start, event_end = int(starts[episode]), int(ends[episode])
    designs, empty = [], []
    for length in lengths:
        positions = {"before": event_start - length, "during": (event_start + event_end - length) // 2, "after": event_end}
        for phase, start in positions.items():
            if start < 1 or start + length >= len(events):
                empty.append({"family": "event_relative", "length": length, "phase": phase, "reason": "event_relative_gap_exits_calendar"})
                continue
            mask = np.zeros(len(events), dtype=bool)
            mask[start : start + length] = True
            share = float(mask[support].mean())
            designs.append(GapDesign(f"event_{phase}_{length}", "event_relative", length, overlap_class(share), 0, mask))
    return designs, empty
