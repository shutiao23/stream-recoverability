"""Step 2 — the outage design.

Two arms. The empirical arm samples real outage geometry from the same
provider's records, so operational numbers are weighted to what agencies
actually experience. The stratified arm crosses outage length with the overlap
between the outage and the station's *climatological* peak window, so that the
response surface is estimable rather than accidental.

The peak-window overlap is computed from training years only and is therefore
visible at decision time. This is the covariate the v16 programme never had.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from stream_recoverability.experiments.v17_fitness.paths import (
    HOTTEST_WINDOW_DAYS,
    OUTAGE_LENGTHS,
    OVERLAP_CLASSES,
)


@dataclass(frozen=True)
class Realization:
    """One outage pattern placed on one calendar year."""

    realization_id: str
    arm: str
    runs: tuple[tuple[int, int], ...]  # (start index within the year, length)
    n_runs: int
    total_missing: int
    longest_run: int
    target_length: int = 0
    overlap_class: str = "observed"
    meta: dict = field(default_factory=dict)

    def mask(self, n_days: int) -> np.ndarray:
        flags = np.zeros(int(n_days), dtype=bool)
        for start, length in self.runs:
            flags[int(start) : int(start) + int(length)] = True
        return flags


def climatological_peak_window(
    target: pd.Series,
    *,
    exclude_year: int | None = None,
    window: int = HOTTEST_WINDOW_DAYS,
) -> np.ndarray:
    """Day-of-year indices of the climatological hottest window.

    Uses every year except the evaluation year, so the window is a training-time
    quantity. Returns day-of-year values in 1..366.
    """

    values = pd.to_numeric(target, errors="coerce")
    if exclude_year is not None:
        values = values.loc[values.index.year != int(exclude_year)]
    values = values.dropna()
    if values.empty:
        return np.arange(182, 182 + window)
    doy = values.index.dayofyear
    climatology = values.groupby(doy).mean().reindex(range(1, 367)).interpolate(limit_direction="both")
    padded = np.concatenate([climatology.to_numpy(), climatology.to_numpy()[: window - 1]])
    rolling = np.convolve(padded, np.ones(window) / window, mode="valid")[:366]
    start = int(np.nanargmax(rolling)) + 1
    return np.array([((start - 1 + offset) % 366) + 1 for offset in range(window)], dtype=int)


def peak_overlap_fraction(year_index: pd.DatetimeIndex, mask: np.ndarray, peak_doys: np.ndarray) -> float:
    """Share of the climatological peak window that the outage hides."""

    peak = np.isin(year_index.dayofyear.to_numpy(), peak_doys)
    if not peak.any():
        return float("nan")
    return float((mask & peak).sum() / peak.sum())


def _place_run(occupied: np.ndarray, start: int, length: int) -> bool:
    n = len(occupied)
    if start < 1 or start + length > n - 1:
        return False
    if occupied[start : start + length].any():
        return False
    occupied[start : start + length] = True
    return True


def stratified_realization(
    year_index: pd.DatetimeIndex,
    peak_doys: np.ndarray,
    *,
    length: int,
    overlap_class: str,
    rng: np.random.Generator,
    realization_id: str,
) -> Realization | None:
    """One outage of a requested length with a requested peak-window overlap."""

    n = len(year_index)
    length = int(min(length, n - 2))
    if length < 1:
        return None
    peak = np.isin(year_index.dayofyear.to_numpy(), peak_doys)
    peak_positions = np.flatnonzero(peak)
    if len(peak_positions) == 0:
        return None
    peak_start, peak_end = int(peak_positions.min()), int(peak_positions.max())

    candidates = np.arange(1, n - length)
    if len(candidates) == 0:
        return None
    covered = np.array(
        [peak[start : start + length].sum() / peak.sum() for start in candidates], dtype=float
    )
    if overlap_class == "none":
        keep = candidates[covered <= 0.0]
    elif overlap_class == "partial":
        keep = candidates[(covered > 0.15) & (covered < 0.85)]
    elif overlap_class == "full":
        keep = candidates[covered >= 0.999]
    else:
        keep = candidates
    if len(keep) == 0:
        return None
    start = int(rng.choice(keep))
    occupied = np.zeros(n, dtype=bool)
    if not _place_run(occupied, start, length):
        return None
    return Realization(
        realization_id=realization_id,
        arm="stratified",
        runs=((start, length),),
        n_runs=1,
        total_missing=int(length),
        longest_run=int(length),
        target_length=int(length),
        overlap_class=str(overlap_class),
        meta={"peak_start": peak_start, "peak_end": peak_end},
    )


def provider_geometry_pool(records: Sequence[pd.DataFrame]) -> pd.DataFrame:
    """Pool real outage runs observed anywhere in a provider's records."""

    frames = [frame for frame in records if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame(columns=["gap_length", "month", "runs_in_year"])
    pooled = pd.concat(frames, ignore_index=True)
    pooled = pooled.loc[pd.to_numeric(pooled["gap_length"], errors="coerce") >= 3].copy()
    pooled["month"] = pd.to_datetime(pooled["gap_start"]).dt.month.astype(int)
    pooled["gap_length"] = pd.to_numeric(pooled["gap_length"], errors="coerce").astype(int)
    return pooled[["gap_length", "month", "runs_in_year"]] if "runs_in_year" in pooled else pooled[["gap_length", "month"]]


def empirical_realization(
    year_index: pd.DatetimeIndex,
    pool: pd.DataFrame,
    *,
    rng: np.random.Generator,
    realization_id: str,
    max_runs: int = 4,
) -> Realization | None:
    """Sample real (length, month) outage runs and place them on a complete year."""

    if pool is None or pool.empty:
        return None
    n = len(year_index)
    n_runs = int(rng.integers(1, max_runs + 1))
    picks = pool.sample(n=min(n_runs, len(pool)), random_state=int(rng.integers(0, 2**31 - 1)))
    occupied = np.zeros(n, dtype=bool)
    runs: list[tuple[int, int]] = []
    months = year_index.month.to_numpy()
    for row in picks.itertuples(index=False):
        length = int(min(int(row.gap_length), n - 2))
        if length < 1:
            continue
        options = np.flatnonzero(months == int(row.month))
        options = options[(options >= 1) & (options + length <= n - 1)]
        if len(options) == 0:
            continue
        rng.shuffle(options)
        for start in options:
            if _place_run(occupied, int(start), length):
                runs.append((int(start), length))
                break
    if not runs:
        return None
    runs_sorted = tuple(sorted(runs))
    total = int(sum(length for _, length in runs_sorted))
    return Realization(
        realization_id=realization_id,
        arm="empirical",
        runs=runs_sorted,
        n_runs=len(runs_sorted),
        total_missing=total,
        longest_run=int(max(length for _, length in runs_sorted)),
        target_length=int(max(length for _, length in runs_sorted)),
        overlap_class="observed",
    )


def design_for_year(
    year_index: pd.DatetimeIndex,
    peak_doys: np.ndarray,
    pool: pd.DataFrame,
    *,
    rng: np.random.Generator,
    lengths: Sequence[int] = OUTAGE_LENGTHS,
    overlap_classes: Sequence[str] = OVERLAP_CLASSES,
    n_empirical: int = 5,
    cross_overlap: bool = False,
) -> list[Realization]:
    """The realizations scored for one station-year: stratified plus empirical.

    When ``cross_overlap`` is True (P0-05 / F04), every length is paired with
    every feasible overlap class on the same station-year so position and length
    effects can be separated. The historical default draws one overlap class per
    length.
    """

    out: list[Realization] = []
    for length in lengths:
        classes = (
            list(overlap_classes)
            if cross_overlap
            else [str(overlap_classes[int(rng.integers(0, len(overlap_classes)))])]
        )
        for overlap_class in classes:
            item = stratified_realization(
                year_index,
                peak_doys,
                length=int(length),
                overlap_class=str(overlap_class),
                rng=rng,
                realization_id=f"s{int(length)}_{overlap_class}",
            )
            if item is None and str(overlap_class) != "partial" and not cross_overlap:
                item = stratified_realization(
                    year_index,
                    peak_doys,
                    length=int(length),
                    overlap_class="partial",
                    rng=rng,
                    realization_id=f"s{int(length)}_partial",
                )
            if item is not None:
                out.append(item)
    for k in range(int(n_empirical)):
        item = empirical_realization(year_index, pool, rng=rng, realization_id=f"e{k}")
        if item is not None:
            out.append(item)
    return out
