"""Fault conditions: donor co-missing, missing right boundary, transplanted geometry."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

def hide_donors(
    panel: pd.DataFrame,
    *,
    donors: Sequence[str],
    start: int,
    gap_length: int,
) -> pd.DataFrame:
    """Synchronous donor outage on the same window as the target."""

    out = panel.copy()
    for donor in donors:
        out.iloc[int(start) : int(start) + int(gap_length), out.columns.get_loc(donor)] = np.nan
    return out


def left_only_persistence(target: pd.Series, start: int, gap_length: int) -> np.ndarray:
    left = float(target.iloc[int(start) - 1])
    return np.full(int(gap_length), left)


def right_boundary_missing_fill(target: pd.Series, start: int, gap_length: int) -> np.ndarray:
    """What a boundary model can use if the outage is still open on the right."""

    return left_only_persistence(target, start, gap_length)


def natural_gap_geometry(series: pd.Series) -> pd.DataFrame:
    """Extract contiguous missing blocks from an observed record."""

    missing = ~pd.to_numeric(series, errors="coerce").notna().to_numpy()
    rows: list[dict[str, object]] = []
    start = None
    for i, flag in enumerate(missing):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            rows.append(
                {
                    "start_index": int(start),
                    "gap_length": int(i - start),
                    "gap_start": series.index[start],
                    "season": int(series.index[start].month),
                }
            )
            start = None
    if start is not None:
        rows.append(
            {
                "start_index": int(start),
                "gap_length": int(len(missing) - start),
                "gap_start": series.index[start],
                "season": int(series.index[start].month),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["start_index", "gap_length", "gap_start", "season"])
    return pd.DataFrame(rows)


def transplant_geometry(
    evaluation_index: pd.DatetimeIndex,
    geometry: pd.DataFrame,
    *,
    min_length: int = 7,
    max_length: int = 180,
    position_index: pd.DatetimeIndex | None = None,
) -> list[tuple[int, int]]:
    """Place historical gap lengths into later complete years, keeping season.

    Starts are positions in ``position_index`` when it is supplied, otherwise
    positions in ``evaluation_index``. Pass the full daily index as
    ``position_index`` when ``evaluation_index`` is a later-year view.
    """

    placed: list[tuple[int, int]] = []
    if geometry is None or geometry.empty or "gap_length" not in geometry.columns:
        return placed
    usable = geometry.loc[geometry["gap_length"].between(int(min_length), int(max_length))]
    locator = evaluation_index if position_index is None else position_index
    years = sorted(set(pd.DatetimeIndex(evaluation_index).year))
    eval_index = pd.DatetimeIndex(evaluation_index)
    for row in usable.itertuples(index=False):
        month = int(pd.Timestamp(row.gap_start).month)
        length = int(row.gap_length)
        for year in years:
            candidates = np.flatnonzero((eval_index.year == year) & (eval_index.month == month))
            if len(candidates) == 0:
                continue
            rel = int(candidates[min(len(candidates) // 2, len(candidates) - 1)])
            stamp = eval_index[rel]
            start = int(pd.DatetimeIndex(locator).get_indexer([stamp])[0])
            if start < 1 or start + length >= len(locator):
                continue
            placed.append((start, length))
            break
    return placed


def heatwave_mask(series: pd.Series, train_mask: pd.Series) -> pd.Series:
    """Days warmer than the training 90th percentile; evaluation-only diagnostic."""

    threshold = float(series.loc[train_mask].quantile(0.9))
    return series > threshold


def seasonal_threshold_from_training(
    series: pd.Series,
    train_mask: pd.Series,
    *,
    quantile: float = 0.9,
) -> pd.Series:
    """Per-DOY threshold fit on training years only. Never uses evaluation truth."""

    train = pd.to_numeric(series, errors="coerce").loc[train_mask.reindex(series.index).fillna(False)]
    doy = pd.Series(train.index.dayofyear, index=train.index)
    grouped = train.groupby(doy).quantile(float(quantile))
    fallback = float(train.quantile(float(quantile))) if train.notna().any() else float("nan")
    mapped = pd.Series(series.index.dayofyear, index=series.index).map(grouped).astype(float)
    return mapped.fillna(fallback)


def heat_event_mask(
    series: pd.Series,
    threshold: pd.Series,
    *,
    min_duration: int = 3,
) -> pd.Series:
    """Runs at least ``min_duration`` days above a training-period seasonal threshold."""

    above = pd.to_numeric(series, errors="coerce") > pd.to_numeric(threshold, errors="coerce").reindex(series.index)
    above = above.fillna(False).to_numpy(dtype=bool)
    out = np.zeros(len(series), dtype=bool)
    start = None
    for i, flag in enumerate(above):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            if i - start >= int(min_duration):
                out[start:i] = True
            start = None
    if start is not None and len(above) - start >= int(min_duration):
        out[start:] = True
    return pd.Series(out, index=series.index)


def heat_event_overlap(gaps: pd.DataFrame, event_mask: pd.Series) -> pd.Series:
    """Post-hoc diagnostic: whether a gap overlaps a heat event. Not a deployment input."""

    flags = []
    for row in gaps.itertuples(index=False):
        start = int(event_mask.index.get_indexer([pd.Timestamp(row.gap_start)])[0])
        length = int(row.gap_length)
        if start < 0 or start + length > len(event_mask):
            flags.append(False)
            continue
        flags.append(bool(event_mask.iloc[start : start + length].any()))
    return pd.Series(flags, index=gaps.index)


def transplant_month_length_pattern(
    evaluation_index: pd.DatetimeIndex,
    geometry: pd.DataFrame,
    *,
    max_gaps: int = 4,
    min_length: int = 7,
    max_length: int = 180,
) -> pd.DataFrame:
    """Copy historical month/length/count onto a later complete year without overlap."""

    if geometry is None or geometry.empty:
        return pd.DataFrame(columns=["gap_start", "gap_length", "gap_end"])
    usable = geometry.loc[pd.to_numeric(geometry["gap_length"], errors="coerce").between(min_length, max_length)]
    if usable.empty:
        return pd.DataFrame(columns=["gap_start", "gap_length", "gap_end"])
    years = sorted(set(pd.DatetimeIndex(evaluation_index).year))
    occupied = np.zeros(len(evaluation_index), dtype=bool)
    rows: list[dict[str, object]] = []
    eval_index = pd.DatetimeIndex(evaluation_index)
    for row in usable.itertuples(index=False):
        if len(rows) >= int(max_gaps):
            break
        month = int(pd.Timestamp(row.gap_start).month)
        length = int(row.gap_length)
        placed = False
        for year in years:
            candidates = np.flatnonzero((eval_index.year == year) & (eval_index.month == month))
            if len(candidates) == 0:
                continue
            for rel in candidates:
                start = int(rel)
                if start < 1 or start + length >= len(eval_index):
                    continue
                if occupied[start : start + length].any():
                    continue
                occupied[start : start + length] = True
                rows.append(
                    {
                        "gap_start": eval_index[start],
                        "gap_length": length,
                        "gap_end": eval_index[start + length - 1],
                        "source": "transplanted_geometry",
                    }
                )
                placed = True
                break
            if placed:
                break
    return pd.DataFrame(rows)


def hide_donors_on_gaps(
    panel: pd.DataFrame,
    donors: Sequence[str],
    gaps: pd.DataFrame,
) -> pd.DataFrame:
    """Synchronous co-missingness: donors are unobserved on the same windows as the target."""

    out = panel.copy()
    for row in gaps.itertuples(index=False):
        start = int(out.index.get_indexer([pd.Timestamp(row.gap_start)])[0])
        length = int(row.gap_length)
        if start < 0:
            continue
        for donor in donors:
            if donor in out.columns:
                out.iloc[start : start + length, out.columns.get_loc(donor)] = np.nan
    return out

