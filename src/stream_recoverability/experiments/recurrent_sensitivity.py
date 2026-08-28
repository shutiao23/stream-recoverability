"""Bounded recurrent-model sensitivity for the v11 first confirmation.

This module deliberately implements an exploratory sensitivity, not a fourth
member of the frozen recovery-model roster.  It trains the repository's small
BRITS-style recurrent imputer only on outer-training years and evaluates a
provider-stratified subset of already-scored ``B_union_D`` placements.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


def provider_stratified_subset(
    qualified: pd.DataFrame,
    scored_networks: Sequence[str],
    *,
    per_provider: int = 1,
) -> pd.DataFrame:
    """Choose a deterministic, compute-bounded subset within every provider."""

    if per_provider <= 0:
        raise ValueError("per_provider must be positive")
    required = {"network_id", "provider", "qc_status", "n_eligible_stations"}
    missing = required.difference(qualified.columns)
    if missing:
        raise ValueError(f"qualified panel is missing columns: {sorted(missing)}")
    scored = {str(value) for value in scored_networks}
    candidates = qualified.loc[
        qualified["qc_status"].eq("qualified")
        & qualified["network_id"].astype(str).isin(scored)
    ].copy()
    candidates["network_id"] = candidates["network_id"].astype(str)
    candidates = candidates.sort_values(
        ["provider", "n_eligible_stations", "network_id"], kind="mergesort"
    )
    return candidates.groupby("provider", sort=True, as_index=False).head(per_provider)


def nested_training_years(
    outer_training_years: Sequence[int], *, validation_fraction: float = 0.25
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Split outer-training years chronologically for fit and validation."""

    years = tuple(sorted({int(value) for value in outer_training_years}))
    if len(years) < 2:
        raise ValueError("at least two outer-training years are required")
    if not 0.0 < validation_fraction < 1.0:
        raise ValueError("validation_fraction must lie in (0, 1)")
    n_validation = max(1, round(len(years) * validation_fraction))
    n_validation = min(len(years) - 1, n_validation)
    return years[:-n_validation], years[-n_validation:]


def recurrently_usable_years(
    panel: pd.DataFrame,
    outer_training_years: Sequence[int],
    *,
    minimum_features: int = 2,
    minimum_concurrent_days: int = 30,
) -> tuple[int, ...]:
    """Keep outer-training years with a minimally multivariate daily record."""

    if minimum_features < 2 or minimum_concurrent_days <= 0:
        raise ValueError("recurrent availability floors are invalid")
    years: list[int] = []
    outer = {int(value) for value in outer_training_years}
    concurrency = panel.notna().sum(axis=1)
    for year, values in concurrency.groupby(panel.index.year):
        if int(year) in outer and int(values.ge(minimum_features).sum()) >= int(
            minimum_concurrent_days
        ):
            years.append(int(year))
    return tuple(years)


def artificial_block_windows(
    panel: pd.DataFrame,
    years: Sequence[int],
    *,
    gap_lengths: Sequence[int] = (7, 30, 90),
    window_length: int = 128,
    max_windows: int = 48,
    seed: int = 20260828,
) -> tuple[np.ndarray, np.ndarray]:
    """Build deterministic artificial-block samples wholly within named years."""

    if window_length <= 1 or max_windows <= 0:
        raise ValueError("window_length and max_windows must be positive")
    if panel.empty or not isinstance(panel.index, pd.DatetimeIndex):
        raise ValueError("panel must be a non-empty DatetimeIndex frame")
    gaps = tuple(sorted({int(value) for value in gap_lengths}))
    if not gaps or min(gaps) <= 0 or max(gaps) >= window_length:
        raise ValueError("gap lengths must be positive and shorter than the window")
    allowed_years = {int(value) for value in years}
    values = panel.to_numpy(dtype=np.float32)
    candidates: list[tuple[int, int, int, int]] = []
    for gap in gaps:
        left_context = (window_length - gap) // 2
        for feature in range(values.shape[1]):
            finite = np.isfinite(values[:, feature])
            for block_start in range(0, len(panel) - gap + 1, max(1, gap // 2)):
                window_start = block_start - left_context
                window_end = window_start + window_length
                if window_start < 0 or window_end > len(panel):
                    continue
                window_years = panel.index[window_start:window_end].year
                if not set(map(int, window_years)).issubset(allowed_years):
                    continue
                if finite[block_start : block_start + gap].all():
                    candidates.append((gap, feature, block_start, window_start))
    if not candidates:
        raise ValueError("no finite artificial block windows are available")
    rng = np.random.default_rng(seed)
    chosen: list[tuple[int, int, int, int]] = []
    for gap in gaps:
        by_gap = [item for item in candidates if item[0] == gap]
        if by_gap:
            chosen.append(by_gap[int(rng.integers(len(by_gap)))])
    remainder = [item for item in candidates if item not in chosen]
    if remainder and len(chosen) < max_windows:
        order = rng.permutation(len(remainder))[: max_windows - len(chosen)]
        chosen.extend(remainder[int(index)] for index in order)
    chosen = chosen[:max_windows]
    samples = np.stack(
        [values[start : start + window_length] for _, _, _, start in chosen]
    )
    masks = np.zeros_like(samples, dtype=bool)
    for row, (gap, feature, block_start, window_start) in enumerate(chosen):
        relative = block_start - window_start
        masks[row, relative : relative + gap, feature] = True
    return samples, masks


def score_existing_placements(
    model: object,
    panel: pd.DataFrame,
    placements: pd.DataFrame,
    *,
    gap_lengths: Sequence[int] = (7, 30, 90),
    window_length: int = 128,
    max_placements_per_cell: int = 3,
    model_label: str = "brits",
) -> pd.DataFrame:
    """Score selected existing placements without exposing their target truth."""

    if max_placements_per_cell <= 0:
        raise ValueError("max_placements_per_cell must be positive")
    if not model_label.isidentifier():
        raise ValueError("model_label must be a valid identifier")
    gaps = {int(value) for value in gap_lengths}
    selected = placements.loc[
        placements["information_condition"].eq("B_union_D")
        & placements["gap_length"].astype(int).isin(gaps)
    ].copy()
    selected["station_id"] = selected["station_id"].astype(str)
    selected["gap_start"] = pd.to_datetime(selected["gap_start"])
    selected = (
        selected.sort_values(
            ["station_id", "gap_length", "placement"], kind="mergesort"
        )
        .groupby(["station_id", "gap_length"], sort=False, as_index=False)
        .head(max_placements_per_cell)
    )
    columns = panel.columns.astype(str)
    panel = panel.copy()
    panel.columns = columns
    values = panel.to_numpy(dtype=np.float32)
    rows: list[dict[str, object]] = []
    for item in selected.itertuples(index=False):
        station = str(item.station_id)
        if station not in columns:
            continue
        gap = int(item.gap_length)
        block_start = panel.index.get_indexer([pd.Timestamp(item.gap_start)])[0]
        if block_start < 0:
            continue
        block_end = block_start + gap
        window_start = block_start - (window_length - gap) // 2
        window_start = max(0, min(window_start, len(panel) - window_length))
        window_end = window_start + window_length
        if block_end > window_end or window_end > len(panel):
            continue
        feature = int(columns.get_loc(station))
        truth = values[block_start:block_end, feature]
        if len(truth) != gap or not np.isfinite(truth).all():
            continue
        sample = values[window_start:window_end].copy()
        hidden = np.zeros_like(sample, dtype=bool)
        relative = block_start - window_start
        hidden[relative : relative + gap, feature] = True
        prediction = model.predict(sample, hidden)
        predicted = prediction[relative : relative + gap, feature]
        rows.append(
            {
                "network_id": str(item.network_id),
                "station_id": station,
                "gap_length": gap,
                "placement": int(item.placement),
                "gap_start": pd.Timestamp(item.gap_start),
                f"{model_label}_mae_deg_c": float(np.mean(np.abs(predicted - truth))),
                "xgboost_mae_deg_c": float(item.mae_deg_c),
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "artificial_block_windows",
    "nested_training_years",
    "provider_stratified_subset",
    "recurrently_usable_years",
    "score_existing_placements",
]
