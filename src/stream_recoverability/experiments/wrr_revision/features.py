"""Feature construction that makes the train/eval boundary protocol explicit."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from stream_recoverability.experiments.development_recovery import (
    _boundary_values,
    _candidate_starts,
    _seasonal_features,
    select_placements,
)
from stream_recoverability.experiments.wrr_revision.paths import GAP_GRID

TRAIN_BLOCKS_PER_LENGTH = 24
MIN_BLOCK_TRAIN_ROWS = 200


def neighbor_boundary_series(target: pd.Series) -> pd.Series:
    """Adjacent-day mean used by the current development trainer."""

    numeric = pd.to_numeric(target, errors="coerce")
    return (numeric.shift(1) + numeric.shift(-1)) / 2.0


def gap_interpolated_boundary(target: pd.Series, start: int, gap_length: int) -> np.ndarray:
    return _boundary_values(target, int(start), int(gap_length))


def base_feature_frame(
    panel: pd.DataFrame,
    *,
    donors: Sequence[str],
    air: pd.Series | None = None,
    discharge: pd.Series | None = None,
) -> pd.DataFrame:
    features = _seasonal_features(panel.index)
    for donor in donors:
        features[f"D__{donor}"] = pd.to_numeric(panel[donor], errors="coerce")
    if air is not None:
        features["M__Ta"] = pd.to_numeric(air, errors="coerce").reindex(panel.index)
    if discharge is not None:
        features["H__F"] = pd.to_numeric(discharge, errors="coerce").reindex(panel.index)
    return features


def attach_neighbor_boundary(features: pd.DataFrame, target: pd.Series) -> pd.DataFrame:
    out = features.copy()
    out["B__boundary_temperature"] = neighbor_boundary_series(target)
    return out


def attach_gap_boundary(
    features: pd.DataFrame,
    target: pd.Series,
    start: int,
    gap_length: int,
) -> pd.DataFrame:
    out = features.iloc[int(start) : int(start) + int(gap_length)].copy()
    out["B__boundary_temperature"] = gap_interpolated_boundary(target, start, gap_length)
    return out


def sample_training_blocks(
    panel: pd.DataFrame,
    *,
    target_station: str,
    donors: Sequence[str],
    train_mask: pd.Series,
    gap_lengths: Sequence[int] = GAP_GRID,
    blocks_per_length: int = TRAIN_BLOCKS_PER_LENGTH,
    auxiliary: pd.DataFrame | None = None,
    meteorology: Sequence[str] = (),
    hydraulics: Sequence[str] = (),
) -> list[tuple[int, int]]:
    """Return (start, length) training gaps inside the fitting years."""

    empty = auxiliary if auxiliary is not None else pd.DataFrame(index=panel.index)
    blocks: list[tuple[int, int]] = []
    for gap_length in (int(value) for value in gap_lengths):
        candidates = _candidate_starts(
            panel,
            empty,
            target_station=str(target_station),
            donors=tuple(donors),
            meteorology=tuple(meteorology),
            hydraulics=tuple(hydraulics),
            evaluation_mask=train_mask,
            gap_length=gap_length,
        )
        selected = select_placements(candidates, count=int(blocks_per_length))
        blocks.extend((int(start), gap_length) for start in selected)
    return blocks


def long_block_training_table(
    panel: pd.DataFrame,
    features: pd.DataFrame,
    *,
    target_station: str,
    blocks: Sequence[tuple[int, int]],
    include_boundary: bool,
) -> tuple[pd.DataFrame, pd.Series]:
    """Stack sampled training-gap rows with evaluation-matched boundary features."""

    frames: list[pd.DataFrame] = []
    targets: list[pd.Series] = []
    target = pd.to_numeric(panel[target_station], errors="coerce")
    for start, gap_length in blocks:
        if include_boundary:
            block = attach_gap_boundary(features, target, start, gap_length)
        else:
            block = features.iloc[int(start) : int(start) + int(gap_length)].copy()
        y = target.iloc[int(start) : int(start) + int(gap_length)]
        ok = y.notna() & ~block.isna().any(axis=1)
        if not ok.any():
            continue
        frames.append(block.loc[ok])
        targets.append(y.loc[ok])
    if not frames:
        empty = features.iloc[0:0]
        return empty, pd.Series(dtype=float)
    x = pd.concat(frames, axis=0)
    y_all = pd.concat(targets, axis=0)
    return x, y_all


def neighbor_training_table(
    features: pd.DataFrame,
    target: pd.Series,
    train_mask: pd.Series,
    *,
    include_boundary: bool,
) -> tuple[pd.DataFrame, pd.Series]:
    frame = attach_neighbor_boundary(features, target) if include_boundary else features
    y = pd.to_numeric(target, errors="coerce")
    ok = train_mask & y.notna() & ~frame.isna().any(axis=1)
    return frame.loc[ok], y.loc[ok]
