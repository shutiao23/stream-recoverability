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
