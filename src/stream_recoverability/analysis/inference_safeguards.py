"""Safeguards for overlap-aware, anchor-level scientific inference.

The functions in this module are deliberately independent of the experiment
runner.  They operate on frozen masks or result tables after prediction and
make the statistical unit, monotonicity adjustment, denominator guard, and
multiplicity family explicit in their outputs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MaskOverlapAudit:
    """Machine-readable result of :func:`audit_mask_anchor_overlap`."""

    pairwise: pd.DataFrame
    unique_date_coverage: pd.DataFrame
    effective_replication_summary: pd.DataFrame
    anchors: pd.DataFrame
    clusters: pd.DataFrame
    summary: dict[str, Any]

    def artifact_frames(self) -> dict[str, pd.DataFrame]:
        """Return copies keyed by the frozen overlap-audit artifact names."""

        return {
            "pairwise_jaccard.csv": self.pairwise.copy(),
            "unique_date_coverage.csv": self.unique_date_coverage.copy(),
            "effective_replication_summary.csv": (
                self.effective_replication_summary.copy()
            ),
        }


@dataclass(frozen=True)
class AnchorBootstrapResult:
    """Seed-collapsed data and anchor-stratified bootstrap estimates."""

    collapsed: pd.DataFrame
    estimates: pd.DataFrame


@dataclass(frozen=True)
class FrontierSafeguardResult:
    """Raw/isotonic curve values and their first-loss frontier summaries."""

    curve: pd.DataFrame
    summary: pd.DataFrame


@dataclass(frozen=True)
class FrontierBootstrapResult:
    """Complete anchor curves, estimates, and auditable joint bootstrap draws."""

    collapsed: pd.DataFrame
    curve: pd.DataFrame
    samples: pd.DataFrame
    summary: pd.DataFrame

    def artifact_frames(self) -> dict[str, pd.DataFrame]:
        """Return the frozen bootstrap-sample artifact without writing files."""

        return {"frontier_bootstrap_samples.parquet": self.samples.copy()}


def _require_columns(
    frame: pd.DataFrame, columns: Sequence[str], *, context: str
) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"{context} requires columns: {missing}")


def _safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator > 0 else 0.0


def _season_from_month(month: int) -> str:
    if month in (12, 1, 2):
        return "DJF"
    if month in (3, 4, 5):
        return "MAM"
    if month in (6, 7, 8):
        return "JJA"
    if month in (9, 10, 11):
        return "SON"
    raise ValueError("month must be in 1..12")


def _connected_components(
    identifiers: Sequence[str], edges: Sequence[tuple[str, str]]
) -> list[tuple[str, ...]]:
    adjacency = {identifier: set() for identifier in identifiers}
    for left, right in edges:
        adjacency[left].add(right)
        adjacency[right].add(left)
    components: list[tuple[str, ...]] = []
    visited: set[str] = set()
    for root in sorted(adjacency):
        if root in visited:
            continue
        pending = [root]
        component: list[str] = []
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            pending.extend(sorted(adjacency[current] - visited, reverse=True))
        components.append(tuple(sorted(component)))
    return components


def audit_mask_anchor_overlap(
    masks: Mapping[str, np.ndarray],
    *,
    dates: Sequence[object] | np.ndarray | pd.Series | None = None,
    cluster_on: str = "either",
) -> MaskOverlapAudit:
    """Audit temporal and exact-cell overlap among frozen mask anchors.

    Parameters
    ----------
    masks:
        Mapping from immutable mask/anchor identifier to a boolean array.  All
        arrays must share shape ``(time, ...)``.  Callers should pass one union
        mask per inferential anchor when several gap lengths share an anchor.
    dates:
        Optional unique date axis used to report the first and last overlapping
        day.  Integer time positions are still audited when it is omitted.
    cluster_on:
        Build connected components from ``"temporal"``, ``"cell"``, or
        ``"either"`` overlap.  ``"either"`` is conservative because masks on
        different channels can still share environmental time variation.

    ``effective_unique_masked_cells`` uses fractional attribution: a cell
    covered by ``k`` anchors contributes ``1/k`` to each.  It is order
    independent, and the anchor-level values sum to the exact union size.
    """

    if cluster_on not in {"temporal", "cell", "either"}:
        raise ValueError("cluster_on must be 'temporal', 'cell', or 'either'")
    if not masks:
        raise ValueError("at least one mask is required")

    identifiers = sorted(str(identifier) for identifier in masks)
    if len(set(identifiers)) != len(masks):
        raise ValueError("mask identifiers must be unique after string conversion")
    normalized: dict[str, np.ndarray] = {}
    expected_shape: tuple[int, ...] | None = None
    for raw_identifier, raw_mask in masks.items():
        identifier = str(raw_identifier)
        mask = np.asarray(raw_mask)
        if mask.dtype != np.bool_:
            raise TypeError(f"mask {identifier!r} must have boolean dtype")
        if mask.ndim < 1:
            raise ValueError(f"mask {identifier!r} must include a time axis")
        if expected_shape is None:
            expected_shape = mask.shape
        elif mask.shape != expected_shape:
            raise ValueError(
                "all masks must share one time/cell shape; "
                f"expected {expected_shape}, received {mask.shape} for {identifier!r}"
            )
        normalized[identifier] = mask.copy()
    assert expected_shape is not None

    date_axis: pd.DatetimeIndex | None = None
    if dates is not None:
        date_axis = pd.DatetimeIndex(pd.to_datetime(dates, errors="coerce")).normalize()
        if len(date_axis) != expected_shape[0]:
            raise ValueError("dates must have the same length as the mask time axis")
        if date_axis.isna().any() or date_axis.duplicated().any():
            raise ValueError("dates must be finite and unique")

    time_activity = {
        identifier: mask.reshape(mask.shape[0], -1).any(axis=1)
        for identifier, mask in normalized.items()
    }
    cell_activity = {
        identifier: mask.reshape(-1) for identifier, mask in normalized.items()
    }
    stacked = np.stack([cell_activity[identifier] for identifier in identifiers])
    coverage = stacked.sum(axis=0, dtype=np.int64)
    temporal_stack = np.stack([time_activity[identifier] for identifier in identifiers])
    full_mask_stack = np.stack([normalized[identifier] for identifier in identifiers])
    masked_instances_by_date = full_mask_stack.reshape(
        len(identifiers), expected_shape[0], -1
    ).sum(axis=(0, 2))
    unique_cells_by_date = (
        full_mask_stack.any(axis=0).reshape(expected_shape[0], -1).sum(axis=1)
    )
    anchor_count_by_date = temporal_stack.sum(axis=0)
    unique_date_coverage = pd.DataFrame(
        {
            "date_index": np.arange(expected_shape[0], dtype=int),
            "date": (
                date_axis
                if date_axis is not None
                else pd.Series(pd.NaT, index=np.arange(expected_shape[0]))
            ),
            "year": (
                pd.Series(date_axis.year, dtype="Int64")
                if date_axis is not None
                else pd.Series(pd.NA, index=np.arange(expected_shape[0]), dtype="Int64")
            ),
            "season": (
                pd.Series(
                    [_season_from_month(month) for month in date_axis.month],
                    dtype="string",
                )
                if date_axis is not None
                else pd.Series(
                    pd.NA, index=np.arange(expected_shape[0]), dtype="string"
                )
            ),
            "anchor_ids": [
                tuple(
                    identifiers[position]
                    for position in np.flatnonzero(temporal_stack[:, time_index])
                )
                for time_index in range(expected_shape[0])
            ],
            "anchors_covering_date": anchor_count_by_date.astype(int),
            "masked_cell_instances": masked_instances_by_date.astype(int),
            "unique_masked_cells": unique_cells_by_date.astype(int),
        }
    )
    unique_date_coverage["effective_cell_replication"] = np.divide(
        unique_date_coverage["masked_cell_instances"],
        unique_date_coverage["unique_masked_cells"],
        out=np.zeros(expected_shape[0], dtype=float),
        where=unique_date_coverage["unique_masked_cells"].to_numpy() > 0,
    )
    unique_date_coverage["is_masked_date"] = (
        unique_date_coverage["anchors_covering_date"] > 0
    )
    unique_date_coverage["unique_to_one_anchor"] = (
        unique_date_coverage["anchors_covering_date"] == 1
    )
    unique_date_coverage["temporal_overlap_flag"] = (
        unique_date_coverage["anchors_covering_date"] > 1
    )

    pair_rows: list[dict[str, Any]] = []
    edges: list[tuple[str, str]] = []
    for left_position, left_id in enumerate(identifiers):
        for right_id in identifiers[left_position + 1 :]:
            left_time = time_activity[left_id]
            right_time = time_activity[right_id]
            temporal_intersection = left_time & right_time
            temporal_union = left_time | right_time
            left_cells = cell_activity[left_id]
            right_cells = cell_activity[right_id]
            cell_intersection = left_cells & right_cells
            cell_union = left_cells | right_cells
            temporal_count = int(temporal_intersection.sum())
            cell_count = int(cell_intersection.sum())
            temporal_flag = temporal_count > 0
            cell_flag = cell_count > 0
            edge_flag = (
                temporal_flag
                if cluster_on == "temporal"
                else cell_flag
                if cluster_on == "cell"
                else temporal_flag or cell_flag
            )
            if edge_flag:
                edges.append((left_id, right_id))
            overlap_positions = np.flatnonzero(temporal_intersection)
            pair_rows.append(
                {
                    "left_anchor_id": left_id,
                    "right_anchor_id": right_id,
                    "left_temporal_days": int(left_time.sum()),
                    "right_temporal_days": int(right_time.sum()),
                    "temporal_overlap_days": temporal_count,
                    "temporal_union_days": int(temporal_union.sum()),
                    "temporal_jaccard": _safe_ratio(
                        temporal_count, int(temporal_union.sum())
                    ),
                    "temporal_overlap_coefficient": _safe_ratio(
                        temporal_count,
                        min(int(left_time.sum()), int(right_time.sum())),
                    ),
                    "temporal_overlap_start_index": (
                        int(overlap_positions[0]) if overlap_positions.size else None
                    ),
                    "temporal_overlap_end_index": (
                        int(overlap_positions[-1]) if overlap_positions.size else None
                    ),
                    "left_masked_cells": int(left_cells.sum()),
                    "right_masked_cells": int(right_cells.sum()),
                    "cell_overlap_count": cell_count,
                    "cell_union_count": int(cell_union.sum()),
                    "cell_jaccard": _safe_ratio(cell_count, int(cell_union.sum())),
                    "cell_overlap_coefficient": _safe_ratio(
                        cell_count,
                        min(int(left_cells.sum()), int(right_cells.sum())),
                    ),
                    "temporal_overlap_start": (
                        date_axis[overlap_positions[0]]
                        if date_axis is not None and overlap_positions.size
                        else pd.NaT
                    ),
                    "temporal_overlap_end": (
                        date_axis[overlap_positions[-1]]
                        if date_axis is not None and overlap_positions.size
                        else pd.NaT
                    ),
                    "has_temporal_overlap": temporal_flag,
                    "has_cell_overlap": cell_flag,
                    "same_temporal_footprint": bool(
                        np.array_equal(left_time, right_time)
                    ),
                    "exact_duplicate_mask": bool(
                        np.array_equal(left_cells, right_cells)
                    ),
                    "connected_overlap_edge": edge_flag,
                }
            )
    pairwise_columns = (
        "left_anchor_id",
        "right_anchor_id",
        "left_temporal_days",
        "right_temporal_days",
        "temporal_overlap_days",
        "temporal_union_days",
        "temporal_jaccard",
        "temporal_overlap_coefficient",
        "temporal_overlap_start_index",
        "temporal_overlap_end_index",
        "left_masked_cells",
        "right_masked_cells",
        "cell_overlap_count",
        "cell_union_count",
        "cell_jaccard",
        "cell_overlap_coefficient",
        "temporal_overlap_start",
        "temporal_overlap_end",
        "has_temporal_overlap",
        "has_cell_overlap",
        "same_temporal_footprint",
        "exact_duplicate_mask",
        "connected_overlap_edge",
    )
    pairwise = pd.DataFrame(pair_rows, columns=pairwise_columns)

    components = _connected_components(identifiers, edges)
    component_by_anchor: dict[str, tuple[str, int]] = {}
    cluster_rows: list[dict[str, Any]] = []
    for position, members in enumerate(components, start=1):
        cluster_id = f"OC{position:04d}"
        member_stack = np.stack([normalized[member] for member in members])
        temporal_union = np.stack([time_activity[member] for member in members]).any(
            axis=0
        )
        cell_union = member_stack.any(axis=0)
        summed_cells = int(member_stack.sum())
        unique_cells = int(cell_union.sum())
        for member in members:
            component_by_anchor[member] = (cluster_id, len(members))
        cluster_rows.append(
            {
                "overlap_cluster_id": cluster_id,
                "anchor_ids": members,
                "anchor_count": len(members),
                "temporal_union_days": int(temporal_union.sum()),
                "summed_masked_cells": summed_cells,
                "effective_unique_masked_cells": unique_cells,
                "duplicate_cell_burden": summed_cells - unique_cells,
                "has_overlap": len(members) > 1,
            }
        )
    clusters = pd.DataFrame(cluster_rows)

    anchor_rows: list[dict[str, Any]] = []
    for row_position, identifier in enumerate(identifiers):
        mask = stacked[row_position]
        masked_cells = int(mask.sum())
        exclusive_cells = int((mask & (coverage == 1)).sum())
        effective_cells = float(np.sum(1.0 / coverage[mask]))
        cluster_id, cluster_size = component_by_anchor[identifier]
        temporal_degree = (
            int(
                pairwise.loc[
                    (
                        pairwise["left_anchor_id"].eq(identifier)
                        | pairwise["right_anchor_id"].eq(identifier)
                    )
                    & pairwise["has_temporal_overlap"],
                ].shape[0]
            )
            if not pairwise.empty
            else 0
        )
        cell_degree = (
            int(
                pairwise.loc[
                    (
                        pairwise["left_anchor_id"].eq(identifier)
                        | pairwise["right_anchor_id"].eq(identifier)
                    )
                    & pairwise["has_cell_overlap"],
                ].shape[0]
            )
            if not pairwise.empty
            else 0
        )
        anchor_rows.append(
            {
                "anchor_id": identifier,
                "temporal_days": int(time_activity[identifier].sum()),
                "masked_cells": masked_cells,
                "exclusive_masked_cells": exclusive_cells,
                "effective_unique_masked_cells": effective_cells,
                "cells_covered_by_other_anchors": masked_cells - exclusive_cells,
                "temporal_overlap_degree": temporal_degree,
                "cell_overlap_degree": cell_degree,
                "overlap_cluster_id": cluster_id,
                "overlap_cluster_size": cluster_size,
                "empty_mask_flag": masked_cells == 0,
                "overlap_flag": cluster_size > 1,
            }
        )
    anchors = pd.DataFrame(anchor_rows)

    total_cells = int(stacked.sum())
    union_cells = int(stacked.any(axis=0).sum())
    temporal_pairs = (
        int(pairwise["has_temporal_overlap"].sum()) if not pairwise.empty else 0
    )
    cell_pairs = int(pairwise["has_cell_overlap"].sum()) if not pairwise.empty else 0
    duplicate_pairs = (
        int(pairwise["exact_duplicate_mask"].sum()) if not pairwise.empty else 0
    )
    mean_cell_jaccard = float(pairwise["cell_jaccard"].mean()) if len(pairwise) else 0.0
    mean_temporal_jaccard = (
        float(pairwise["temporal_jaccard"].mean()) if len(pairwise) else 0.0
    )
    max_cell_overlap = int(pairwise["cell_overlap_count"].max()) if len(pairwise) else 0
    max_temporal_overlap = (
        int(pairwise["temporal_overlap_days"].max()) if len(pairwise) else 0
    )
    max_cell_overlap_coefficient = (
        float(pairwise["cell_overlap_coefficient"].max()) if len(pairwise) else 0.0
    )
    empty_masks = int((anchors["masked_cells"] == 0).sum())
    overlap_components = int((clusters["anchor_count"] > 1).sum())
    flags: list[str] = []
    if empty_masks:
        flags.append("empty_masks_present")
    if temporal_pairs:
        flags.append("temporal_overlap_present")
    if cell_pairs:
        flags.append("cell_overlap_present")
    if duplicate_pairs:
        flags.append("exact_duplicate_masks_present")
    if overlap_components:
        flags.append("anchors_not_independent")
    summary = {
        "audit_status": "flags_present" if flags else "no_overlap_detected",
        "cluster_on": cluster_on,
        "n_anchors": len(identifiers),
        "n_pairs": len(pairwise),
        "n_temporally_overlapping_pairs": temporal_pairs,
        "n_cell_overlapping_pairs": cell_pairs,
        "n_exact_duplicate_pairs": duplicate_pairs,
        "n_empty_masks": empty_masks,
        "mean_jaccard": mean_cell_jaccard,
        "max_overlap": max_cell_overlap_coefficient,
        "mean_cell_jaccard": mean_cell_jaccard,
        "mean_temporal_jaccard": mean_temporal_jaccard,
        "max_cell_overlap_count": max_cell_overlap,
        "max_temporal_overlap_days": max_temporal_overlap,
        "max_cell_overlap_coefficient": max_cell_overlap_coefficient,
        "summed_masked_cells": total_cells,
        "effective_unique_masked_cells": union_cells,
        "duplicate_cell_burden": total_cells - union_cells,
        "n_overlap_clusters": overlap_components,
        "largest_overlap_cluster": int(clusters["anchor_count"].max()),
        "flags": tuple(flags),
    }
    replication_rows: list[dict[str, Any]] = [
        {
            "scope": "overall",
            "scope_id": "all_anchors",
            "anchor_count": len(identifiers),
            "temporal_union_days": int(temporal_stack.any(axis=0).sum()),
            "summed_masked_cells": total_cells,
            "effective_unique_masked_cells": union_cells,
            "effective_replication_factor": _safe_ratio(total_cells, union_cells),
            "duplicate_cell_burden": total_cells - union_cells,
            "mean_jaccard": mean_cell_jaccard,
            "max_overlap": max_cell_overlap_coefficient,
            "mean_temporal_jaccard": mean_temporal_jaccard,
            "max_temporal_overlap_days": max_temporal_overlap,
            "overlap_flag": overlap_components > 0,
            "audit_status": summary["audit_status"],
            "flags": summary["flags"],
        }
    ]
    for cluster in clusters.itertuples(index=False):
        replication_rows.append(
            {
                "scope": "overlap_cluster",
                "scope_id": cluster.overlap_cluster_id,
                "anchor_count": int(cluster.anchor_count),
                "temporal_union_days": int(cluster.temporal_union_days),
                "summed_masked_cells": int(cluster.summed_masked_cells),
                "effective_unique_masked_cells": int(
                    cluster.effective_unique_masked_cells
                ),
                "effective_replication_factor": _safe_ratio(
                    int(cluster.summed_masked_cells),
                    int(cluster.effective_unique_masked_cells),
                ),
                "duplicate_cell_burden": int(cluster.duplicate_cell_burden),
                "overlap_flag": bool(cluster.has_overlap),
                "audit_status": (
                    "overlap_cluster" if cluster.has_overlap else "singleton"
                ),
                "flags": (("anchors_not_independent",) if cluster.has_overlap else ()),
            }
        )
    effective_replication_summary = pd.DataFrame(replication_rows)
    if not np.isclose(anchors["effective_unique_masked_cells"].sum(), union_cells):
        raise AssertionError(
            "fractional effective-cell attribution did not preserve union"
        )
    return MaskOverlapAudit(
        pairwise,
        unique_date_coverage,
        effective_replication_summary,
        anchors,
        clusters,
        summary,
    )


def average_training_seeds_by_anchor(
    events: pd.DataFrame,
    *,
    value_col: str,
    group_cols: Sequence[str] = (),
    model_col: str = "model",
    anchor_col: str = "anchor_id",
    station_col: str = "station_id",
    year_col: str = "year",
    training_seed_col: str = "training_seed",
    anchor_date_col: str = "center_date",
    overlap_cluster_col: str | None = None,
) -> pd.DataFrame:
    """Collapse optimisation repeats before treating an anchor as evidence.

    Duplicate source rows within one training seed are first averaged and
    counted.  Training-seed means are then averaged within
    ``model x mask-anchor x station x year`` (and requested analysis groups).
    This ensures training seeds never inflate the inferential sample size.
    """

    data = events.copy()
    if year_col not in data:
        if anchor_date_col not in data:
            raise ValueError(
                f"seed aggregation requires {year_col!r} or {anchor_date_col!r}"
            )
        dates = pd.to_datetime(data[anchor_date_col], errors="coerce")
        if dates.isna().any():
            raise ValueError(f"{anchor_date_col} contains invalid dates")
        data[year_col] = dates.dt.year
    keys = [*group_cols, model_col, anchor_col, station_col, year_col]
    if overlap_cluster_col is not None:
        keys.append(overlap_cluster_col)
    keys = list(dict.fromkeys(keys))
    _require_columns(
        data,
        [*keys, training_seed_col, value_col],
        context="training-seed aggregation",
    )
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data = data.dropna(subset=[*keys, value_col]).copy()
    anchor_context = list(dict.fromkeys([*group_cols, anchor_col]))
    assignments = data.groupby(anchor_context, dropna=False, observed=True, sort=True)[
        [station_col, year_col]
    ].nunique(dropna=False)
    if (assignments > 1).any().any():
        raise ValueError(
            "each mask anchor must belong to exactly one station/year stratum "
            "within an analysis group"
        )
    if data.empty:
        columns = [
            *keys,
            value_col,
            "n_training_seeds",
            "n_seed_units",
            "n_source_rows",
            "pseudoreplicate_rows_collapsed",
            "training_seeds_averaged",
        ]
        return pd.DataFrame(columns=columns)
    seed_keys = [*keys, training_seed_col]
    within_seed = (
        data.groupby(seed_keys, dropna=False, observed=True, sort=True)[value_col]
        .agg(seed_value="mean", source_rows="size")
        .reset_index()
    )
    collapsed = (
        within_seed.groupby(keys, dropna=False, observed=True, sort=True)
        .agg(
            **{
                value_col: ("seed_value", "mean"),
                "n_training_seeds": (training_seed_col, "nunique"),
                "n_seed_units": ("seed_value", "size"),
                "n_source_rows": ("source_rows", "sum"),
            }
        )
        .reset_index()
    )
    collapsed["pseudoreplicate_rows_collapsed"] = (
        collapsed["n_source_rows"] - 1
    ).astype(int)
    collapsed["training_seeds_averaged"] = True
    return collapsed


def _stratified_anchor_bootstrap(
    values: pd.DataFrame,
    *,
    value_col: str,
    station_col: str,
    year_col: str,
    bootstrap_cluster_col: str,
    n_boot: int,
    rng: np.random.Generator,
) -> np.ndarray:
    strata: list[list[np.ndarray]] = []
    for _, stratum in values.groupby(
        [station_col, year_col], dropna=False, observed=True, sort=True
    ):
        clusters = [
            cluster[value_col].to_numpy(dtype=float)
            for _, cluster in stratum.groupby(
                bootstrap_cluster_col,
                dropna=False,
                observed=True,
                sort=True,
            )
        ]
        strata.append(clusters)
    draws = np.empty(n_boot, dtype=float)
    for draw in range(n_boot):
        sampled_clusters: list[np.ndarray] = []
        for clusters in strata:
            chosen = rng.integers(0, len(clusters), size=len(clusters))
            sampled_clusters.extend(clusters[position] for position in chosen)
        draws[draw] = float(np.mean(np.concatenate(sampled_clusters)))
    return draws


def anchor_year_cluster_bootstrap(
    events: pd.DataFrame,
    *,
    value_col: str,
    group_cols: Sequence[str] = (),
    model_col: str = "model",
    anchor_col: str = "anchor_id",
    station_col: str = "station_id",
    year_col: str = "year",
    training_seed_col: str = "training_seed",
    anchor_date_col: str = "center_date",
    overlap_cluster_col: str | None = None,
    baseline_model: str | None = None,
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> AnchorBootstrapResult:
    """Bootstrap anchor-level means within fixed station/year strata.

    Training seeds are averaged first with
    :func:`average_training_seeds_by_anchor`.  With ``baseline_model``, models
    are paired to that baseline on the identical anchor/year and the bootstrapped
    estimand is ``model - baseline``.  Otherwise each model mean is estimated.
    Resampling anchors rather than rows prevents training-seed or daily-row
    pseudoreplication while preserving the observed station/year composition.
    When ``overlap_cluster_col`` is supplied, connected anchors from the mask
    audit are resampled together as a stricter dependence cluster.
    """

    if n_boot < 1:
        raise ValueError("n_boot must be positive")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between zero and one")
    collapsed = average_training_seeds_by_anchor(
        events,
        value_col=value_col,
        group_cols=group_cols,
        model_col=model_col,
        anchor_col=anchor_col,
        station_col=station_col,
        year_col=year_col,
        training_seed_col=training_seed_col,
        anchor_date_col=anchor_date_col,
        overlap_cluster_col=overlap_cluster_col,
    )
    if collapsed.empty:
        return AnchorBootstrapResult(collapsed, pd.DataFrame())

    active_groups = list(dict.fromkeys(group_cols))
    grouped: Any
    if active_groups:
        grouped = collapsed.groupby(
            active_groups, dropna=False, observed=True, sort=True
        )
    else:
        grouped = [((), collapsed)]
    rng = np.random.default_rng(seed)
    alpha = (1.0 - confidence) / 2.0
    rows: list[dict[str, Any]] = []
    for group_key, group in grouped:
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(
            zip(active_groups, group_key if active_groups else (), strict=True)
        )
        models = sorted(group[model_col].astype(str).unique())
        if baseline_model is not None and baseline_model not in models:
            rows.append(
                {
                    **metadata,
                    "model": None,
                    "baseline_model": baseline_model,
                    "estimate": np.nan,
                    "ci_lower": np.nan,
                    "ci_upper": np.nan,
                    "n_anchor_year_units": 0,
                    "n_station_year_strata": 0,
                    "n_source_rows": 0,
                    "reason": "baseline model is absent",
                }
            )
            continue
        for model in models:
            if baseline_model is not None and model == baseline_model:
                continue
            if baseline_model is None:
                unit_columns = [anchor_col, station_col, year_col]
                if overlap_cluster_col is not None:
                    unit_columns.append(overlap_cluster_col)
                sampled = group.loc[
                    group[model_col].astype(str).eq(model),
                    [*unit_columns, value_col, "n_source_rows"],
                ].copy()
                estimand = "model_mean"
            else:
                selected = group.loc[
                    group[model_col].astype(str).isin([model, baseline_model]),
                    [
                        anchor_col,
                        station_col,
                        year_col,
                        *(
                            [overlap_cluster_col]
                            if overlap_cluster_col is not None
                            else []
                        ),
                        model_col,
                        value_col,
                        "n_source_rows",
                    ],
                ].copy()
                index_cols = [anchor_col, station_col, year_col]
                if overlap_cluster_col is not None:
                    index_cols.append(overlap_cluster_col)
                values = selected.pivot(
                    index=index_cols, columns=model_col, values=value_col
                )
                source_counts = selected.groupby(
                    index_cols, dropna=False, observed=True
                )["n_source_rows"].sum()
                if model not in values or baseline_model not in values:
                    sampled = pd.DataFrame()
                else:
                    paired = values[[model, baseline_model]].dropna().copy()
                    sampled = paired.reset_index()
                    sampled[value_col] = paired[model].to_numpy(dtype=float) - paired[
                        baseline_model
                    ].to_numpy(dtype=float)
                    sampled["n_source_rows"] = source_counts.reindex(
                        paired.index
                    ).to_numpy(dtype=int)
                estimand = "model_minus_baseline"
            if sampled.empty:
                rows.append(
                    {
                        **metadata,
                        "model": model,
                        "baseline_model": baseline_model,
                        "estimand": estimand,
                        "estimate": np.nan,
                        "ci_lower": np.nan,
                        "ci_upper": np.nan,
                        "n_anchor_year_units": 0,
                        "n_station_year_strata": 0,
                        "n_source_rows": 0,
                        "reason": "no finite anchor-level units",
                    }
                )
                continue
            sampled = sampled.sort_values(
                [station_col, year_col, anchor_col], kind="stable"
            ).reset_index(drop=True)
            bootstrap_cluster_col = overlap_cluster_col or anchor_col
            stratum_sizes = sampled.groupby(
                [station_col, year_col],
                dropna=False,
                observed=True,
                sort=True,
            )[bootstrap_cluster_col].nunique(dropna=False)
            n_resampleable_strata = int((stratum_sizes >= 2).sum())
            bootstrap_reason = None
            if len(sampled) < 2:
                lower = upper = np.nan
                bootstrap_reason = (
                    "at least two anchor-year units are required for a bootstrap CI"
                )
            elif n_resampleable_strata == 0:
                lower = upper = np.nan
                bootstrap_reason = (
                    "no station/year stratum contains two anchors to resample"
                )
            else:
                draws = _stratified_anchor_bootstrap(
                    sampled,
                    value_col=value_col,
                    station_col=station_col,
                    year_col=year_col,
                    bootstrap_cluster_col=bootstrap_cluster_col,
                    n_boot=n_boot,
                    rng=rng,
                )
                lower = float(np.quantile(draws, alpha))
                upper = float(np.quantile(draws, 1.0 - alpha))
            rows.append(
                {
                    **metadata,
                    "model": model,
                    "baseline_model": baseline_model,
                    "estimand": estimand,
                    "estimate": float(sampled[value_col].mean()),
                    "ci_lower": lower,
                    "ci_upper": upper,
                    "n_anchor_year_units": len(sampled),
                    "n_unique_anchors": int(sampled[anchor_col].nunique()),
                    "n_station_year_strata": int(
                        sampled[[station_col, year_col]].drop_duplicates().shape[0]
                    ),
                    "n_resampleable_station_year_strata": n_resampleable_strata,
                    "n_bootstrap_clusters": int(
                        sampled[[station_col, year_col, bootstrap_cluster_col]]
                        .drop_duplicates()
                        .shape[0]
                    ),
                    "n_source_rows": int(sampled["n_source_rows"].sum()),
                    "training_seeds_averaged_first": True,
                    "bootstrap_unit": (
                        "connected_overlap_cluster_within_station_year_strata"
                        if overlap_cluster_col is not None
                        else "anchor_within_station_year_strata"
                    ),
                    "n_boot": int(n_boot),
                    "reason": bootstrap_reason,
                }
            )
    return AnchorBootstrapResult(collapsed, pd.DataFrame(rows))


def anchor_year_frontier_bootstrap(
    events: pd.DataFrame,
    *,
    value_col: str = "skill",
    gap_col: str = "gap_length",
    group_cols: Sequence[str] = ("station_id", "target", "model"),
    model_col: str = "model",
    anchor_col: str = "anchor_id",
    station_col: str = "station_id",
    year_col: str = "year",
    training_seed_col: str = "training_seed",
    anchor_date_col: str = "center_date",
    overlap_cluster_col: str | None = None,
    required_gap_lengths: Sequence[float] | None = None,
    threshold: float = 0.0,
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> FrontierBootstrapResult:
    """Jointly bootstrap complete cross-gap anchor curves.

    Training seeds are averaged within model, anchor, and gap before any
    resampling.  In each bootstrap replicate, anchors (or connected overlap
    clusters) are drawn once within every station/year stratum and that exact
    draw is reused at every gap length.  Incomplete anchor curves are excluded
    as whole units.  The long ``samples`` table records the sampled identifiers
    and every gap-specific value and is suitable for
    ``frontier_bootstrap_samples.parquet``.
    """

    if n_boot < 1:
        raise ValueError("n_boot must be positive")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between zero and one")
    active_groups = list(dict.fromkeys(group_cols))
    if gap_col in active_groups:
        raise ValueError("gap_col must not be an outer frontier group")
    if model_col not in active_groups:
        raise ValueError("frontier groups must keep models separate")
    source = events.copy()
    _require_columns(source, [gap_col, value_col], context="frontier bootstrap")
    source[gap_col] = pd.to_numeric(source[gap_col], errors="coerce")
    if source[gap_col].isna().any() or not np.isfinite(source[gap_col]).all():
        raise ValueError("frontier gap lengths must be finite")

    collapsed = average_training_seeds_by_anchor(
        source,
        value_col=value_col,
        group_cols=[*active_groups, gap_col],
        model_col=model_col,
        anchor_col=anchor_col,
        station_col=station_col,
        year_col=year_col,
        training_seed_col=training_seed_col,
        anchor_date_col=anchor_date_col,
        overlap_cluster_col=overlap_cluster_col,
    )
    collapsed["frontier_complete_curve"] = False
    if collapsed.empty:
        return FrontierBootstrapResult(
            collapsed, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        )

    anchor_context = list(dict.fromkeys([*active_groups, anchor_col]))
    identity_columns = [station_col, year_col]
    if overlap_cluster_col is not None:
        identity_columns.append(overlap_cluster_col)
    identities = collapsed.groupby(
        anchor_context, dropna=False, observed=True, sort=True
    )[identity_columns].nunique(dropna=False)
    if (identities > 1).any().any():
        raise ValueError(
            "each frontier anchor must retain one station/year/overlap-cluster "
            "identity across all gap lengths"
        )

    required_gaps: np.ndarray | None = None
    if required_gap_lengths is not None:
        required_gaps = np.asarray(required_gap_lengths, dtype=float)
        if (
            required_gaps.ndim != 1
            or len(required_gaps) < 2
            or not np.isfinite(required_gaps).all()
            or len(np.unique(required_gaps)) != len(required_gaps)
        ):
            raise ValueError(
                "required_gap_lengths must contain at least two unique finite values"
            )
        required_gaps = np.sort(required_gaps)

    grouped = collapsed.groupby(active_groups, dropna=False, observed=True, sort=True)
    rng = np.random.default_rng(seed)
    alpha = (1.0 - confidence) / 2.0
    curve_rows: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for group_key, group in grouped:
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(zip(active_groups, group_key, strict=True))
        gaps = (
            required_gaps
            if required_gaps is not None
            else np.sort(group[gap_col].unique().astype(float))
        )
        if len(gaps) < 2:
            summary_rows.append(
                {
                    **metadata,
                    "n_gap_lengths": len(gaps),
                    "n_complete_anchor_curves": 0,
                    "n_incomplete_anchor_curves_excluded": 0,
                    "n_bootstrap_samples": 0,
                    "joint_cross_gap_resampling": True,
                    "reason": "at least two gap lengths are required",
                }
            )
            continue
        selected = group.loc[group[gap_col].isin(gaps)].copy()
        index_cols = [anchor_col, station_col, year_col]
        if overlap_cluster_col is not None:
            index_cols.append(overlap_cluster_col)
        panel = selected.pivot(index=index_cols, columns=gap_col, values=value_col)
        panel = panel.reindex(columns=gaps)
        complete = panel.notna().all(axis=1)
        n_incomplete = int((~complete).sum())
        panel = panel.loc[complete]
        complete_identities = set(panel.index.tolist())
        if len(index_cols) == 1:
            complete_identities = {(value,) for value in complete_identities}
        selected_identity = pd.MultiIndex.from_frame(selected[index_cols])
        completed_rows = selected.index[
            [identity in complete_identities for identity in selected_identity]
        ]
        collapsed.loc[completed_rows, "frontier_complete_curve"] = True
        if panel.empty:
            summary_rows.append(
                {
                    **metadata,
                    "n_gap_lengths": len(gaps),
                    "n_complete_anchor_curves": 0,
                    "n_incomplete_anchor_curves_excluded": n_incomplete,
                    "n_bootstrap_samples": 0,
                    "joint_cross_gap_resampling": True,
                    "reason": "no anchor has a complete cross-gap curve",
                }
            )
            continue

        panel_values = panel.to_numpy(dtype=float)
        unit_metadata = panel.index.to_frame(index=False)
        unit_metadata["_panel_row"] = np.arange(len(panel), dtype=int)
        bootstrap_cluster_col = overlap_cluster_col or anchor_col
        strata: list[list[tuple[tuple[Any, ...], np.ndarray]]] = []
        for stratum_key, stratum in unit_metadata.groupby(
            [station_col, year_col],
            dropna=False,
            observed=True,
            sort=True,
        ):
            if not isinstance(stratum_key, tuple):
                stratum_key = (stratum_key,)
            clusters: list[tuple[tuple[Any, ...], np.ndarray]] = []
            for cluster_id, cluster in stratum.groupby(
                bootstrap_cluster_col,
                dropna=False,
                observed=True,
                sort=True,
            ):
                label = (*stratum_key, cluster_id)
                clusters.append((label, cluster["_panel_row"].to_numpy(dtype=int)))
            strata.append(clusters)
        n_clusters = int(sum(len(stratum) for stratum in strata))
        n_resampleable_strata = int(sum(len(stratum) >= 2 for stratum in strata))
        point_raw = panel_values.mean(axis=0)
        point_monotone, _ = weighted_pava(point_raw, non_increasing=True)
        point_raw_frontier = _first_loss_frontier(gaps, point_raw, threshold)
        point_monotone_frontier = _first_loss_frontier(gaps, point_monotone, threshold)

        sample_matrix: np.ndarray | None = None
        bootstrap_reason: str | None = None
        if len(panel) < 2:
            bootstrap_reason = (
                "at least two complete anchor curves are required for bootstrap"
            )
        elif n_resampleable_strata == 0:
            bootstrap_reason = (
                "no station/year stratum contains two anchor clusters to resample"
            )
        else:
            sample_matrix = np.empty((n_boot, len(gaps)), dtype=float)
            for bootstrap_id in range(n_boot):
                sampled_positions: list[int] = []
                sampled_cluster_ids: list[tuple[Any, ...]] = []
                for stratum in strata:
                    chosen = rng.integers(0, len(stratum), size=len(stratum))
                    for position in chosen:
                        cluster_label, panel_rows = stratum[int(position)]
                        sampled_cluster_ids.append(cluster_label)
                        sampled_positions.extend(panel_rows.tolist())
                sampled_position_array = np.asarray(sampled_positions, dtype=int)
                sampled_anchor_ids = tuple(
                    unit_metadata.iloc[sampled_position_array][anchor_col].astype(str)
                )
                sample_curve = panel_values[sampled_position_array].mean(axis=0)
                sample_matrix[bootstrap_id] = sample_curve
                monotone_curve, _ = weighted_pava(sample_curve, non_increasing=True)
                raw_frontier = _first_loss_frontier(gaps, sample_curve, threshold)
                monotone_frontier = _first_loss_frontier(
                    gaps, monotone_curve, threshold
                )
                for gap_position, gap in enumerate(gaps):
                    sample_rows.append(
                        {
                            **metadata,
                            "bootstrap_id": bootstrap_id,
                            gap_col: float(gap),
                            "bootstrap_raw_value": float(sample_curve[gap_position]),
                            "bootstrap_monotone_value": float(
                                monotone_curve[gap_position]
                            ),
                            "sampled_cluster_ids": tuple(sampled_cluster_ids),
                            "sampled_anchor_ids": sampled_anchor_ids,
                            "n_sampled_clusters": len(sampled_cluster_ids),
                            "n_sampled_anchor_rows": len(sampled_position_array),
                            "raw_frontier_days": raw_frontier["frontier_days"],
                            "raw_frontier_censoring": raw_frontier["censoring"],
                            "monotone_frontier_days": monotone_frontier[
                                "frontier_days"
                            ],
                            "monotone_frontier_censoring": monotone_frontier[
                                "censoring"
                            ],
                            "complete_cross_gap_curve": True,
                            "joint_cross_gap_resampling": True,
                        }
                    )

        for gap_position, gap in enumerate(gaps):
            if sample_matrix is None:
                lower = upper = np.nan
            else:
                lower = float(np.quantile(sample_matrix[:, gap_position], alpha))
                upper = float(np.quantile(sample_matrix[:, gap_position], 1.0 - alpha))
            adjustment = point_monotone[gap_position] - point_raw[gap_position]
            curve_rows.append(
                {
                    **metadata,
                    gap_col: float(gap),
                    "raw_frontier_value": float(point_raw[gap_position]),
                    "monotone_frontier_value": float(point_monotone[gap_position]),
                    "frontier_adjustment": float(adjustment),
                    "frontier_adjusted": not np.isclose(adjustment, 0.0),
                    "bootstrap_ci_lower": lower,
                    "bootstrap_ci_upper": upper,
                    "n_complete_anchor_curves": len(panel),
                    "n_incomplete_anchor_curves_excluded": n_incomplete,
                    "joint_cross_gap_resampling": True,
                    "reason": bootstrap_reason,
                }
            )
        summary_rows.append(
            {
                **metadata,
                "n_gap_lengths": len(gaps),
                "gap_lengths": tuple(float(gap) for gap in gaps),
                "n_complete_anchor_curves": len(panel),
                "n_incomplete_anchor_curves_excluded": n_incomplete,
                "n_bootstrap_clusters": n_clusters,
                "n_resampleable_station_year_strata": n_resampleable_strata,
                "n_bootstrap_samples": n_boot if sample_matrix is not None else 0,
                "raw_frontier_days": point_raw_frontier["frontier_days"],
                "raw_frontier_censoring": point_raw_frontier["censoring"],
                "monotone_frontier_days": point_monotone_frontier["frontier_days"],
                "monotone_frontier_censoring": point_monotone_frontier["censoring"],
                "bootstrap_unit": (
                    "connected_overlap_cluster_within_station_year_strata"
                    if overlap_cluster_col is not None
                    else "anchor_within_station_year_strata"
                ),
                "joint_cross_gap_resampling": True,
                "reason": bootstrap_reason,
            }
        )
    return FrontierBootstrapResult(
        collapsed,
        pd.DataFrame(curve_rows),
        pd.DataFrame(sample_rows),
        pd.DataFrame(summary_rows),
    )


def weighted_pava(
    values: Sequence[float] | np.ndarray | pd.Series,
    weights: Sequence[float] | np.ndarray | pd.Series | None = None,
    *,
    non_increasing: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Return weighted isotonic values and stable pooled-block identifiers."""

    observed = np.asarray(values, dtype=float)
    if observed.ndim != 1 or not len(observed):
        raise ValueError("values must be a non-empty one-dimensional sequence")
    if not np.isfinite(observed).all():
        raise ValueError("values must be finite")
    if weights is None:
        mass = np.ones(len(observed), dtype=float)
    else:
        mass = np.asarray(weights, dtype=float)
        if mass.shape != observed.shape:
            raise ValueError("weights must match values")
        if not np.isfinite(mass).all() or np.any(mass <= 0):
            raise ValueError("weights must be finite and strictly positive")
    working = -observed if non_increasing else observed
    blocks: list[dict[str, float | int]] = []
    for position, (value, weight) in enumerate(zip(working, mass, strict=True)):
        blocks.append(
            {
                "start": position,
                "stop": position + 1,
                "weight": float(weight),
                "weighted_sum": float(value * weight),
                "mean": float(value),
            }
        )
        while len(blocks) >= 2 and float(blocks[-2]["mean"]) > float(
            blocks[-1]["mean"]
        ):
            right = blocks.pop()
            left = blocks.pop()
            combined_weight = float(left["weight"]) + float(right["weight"])
            combined_sum = float(left["weighted_sum"]) + float(right["weighted_sum"])
            blocks.append(
                {
                    "start": int(left["start"]),
                    "stop": int(right["stop"]),
                    "weight": combined_weight,
                    "weighted_sum": combined_sum,
                    "mean": combined_sum / combined_weight,
                }
            )
    fitted = np.empty(len(observed), dtype=float)
    block_ids = np.empty(len(observed), dtype=int)
    for block_id, block in enumerate(blocks, start=1):
        start, stop = int(block["start"]), int(block["stop"])
        fitted[start:stop] = float(block["mean"])
        block_ids[start:stop] = block_id
    if non_increasing:
        fitted *= -1.0
    return fitted, block_ids


def _first_loss_frontier(
    gaps: np.ndarray, values: np.ndarray, threshold: float
) -> dict[str, Any]:
    feasible = values > threshold
    if not feasible[0]:
        return {
            "frontier_days": np.nan,
            "censoring": "left",
            "status": "below_threshold_at_smallest_gap",
            "reversal_after_loss": bool(feasible[1:].any()),
        }
    losses = np.flatnonzero(~feasible)
    if not losses.size:
        return {
            "frontier_days": float(gaps[-1]),
            "censoring": "right",
            "status": "above_threshold_through_largest_gap",
            "reversal_after_loss": False,
        }
    right = int(losses[0])
    left = right - 1
    if np.isclose(values[left], values[right]):
        frontier = float(gaps[left])
    else:
        fraction = (threshold - values[left]) / (values[right] - values[left])
        frontier = float(gaps[left] + fraction * (gaps[right] - gaps[left]))
    return {
        "frontier_days": frontier,
        "censoring": None,
        "status": "threshold_crossing_interpolated",
        "reversal_after_loss": bool(feasible[right + 1 :].any()),
    }


def raw_and_monotone_frontier(
    curve: pd.DataFrame,
    *,
    value_col: str = "mean_skill",
    gap_col: str = "gap_length",
    weight_col: str | None = None,
    group_cols: Sequence[str] = ("station_id", "target", "model"),
    threshold: float = 0.0,
) -> FrontierSafeguardResult:
    """Preserve raw curves and add weighted non-increasing PAVA estimates.

    One row per group/gap is required so weighting choices cannot silently
    change through implicit aggregation.  The returned curve retains every
    input column and adds raw, adjusted, block, and feasibility fields.
    """

    active_groups = list(dict.fromkeys(group_cols))
    required = [*active_groups, gap_col, value_col]
    if weight_col is not None:
        required.append(weight_col)
    _require_columns(curve, required, context="frontier safeguard")
    if curve.empty:
        return FrontierSafeguardResult(curve.copy(), pd.DataFrame())
    result = curve.copy()
    result[gap_col] = pd.to_numeric(result[gap_col], errors="coerce")
    result[value_col] = pd.to_numeric(result[value_col], errors="coerce")
    if (
        result[[gap_col, value_col]].isna().any().any()
        or not np.isfinite(result[[gap_col, value_col]].to_numpy(dtype=float)).all()
    ):
        raise ValueError("gap and frontier values must be finite")
    if result.duplicated([*active_groups, gap_col]).any():
        raise ValueError("frontier input must contain one row per group and gap")
    if weight_col is None:
        result["frontier_weight"] = 1.0
    else:
        result["frontier_weight"] = pd.to_numeric(result[weight_col], errors="coerce")
        if (
            result["frontier_weight"].isna().any()
            or not np.isfinite(result["frontier_weight"]).all()
            or (result["frontier_weight"] <= 0).any()
        ):
            raise ValueError("frontier weights must be finite and strictly positive")
    result["_safeguard_input_order"] = np.arange(len(result))
    result["raw_frontier_value"] = result[value_col].to_numpy(dtype=float)
    result["monotone_frontier_value"] = np.nan
    result["frontier_adjustment"] = np.nan
    result["frontier_adjusted"] = False
    result["pava_block_id"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    result["raw_threshold_feasible"] = False
    result["monotone_threshold_feasible"] = False

    grouped: Any
    if active_groups:
        grouped = result.groupby(active_groups, dropna=False, observed=True, sort=True)
    else:
        grouped = [((), result)]
    summaries: list[dict[str, Any]] = []
    for group_key, group in grouped:
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(
            zip(active_groups, group_key if active_groups else (), strict=True)
        )
        ordered = group.sort_values(gap_col, kind="stable")
        gaps = ordered[gap_col].to_numpy(dtype=float)
        raw = ordered[value_col].to_numpy(dtype=float)
        weights = ordered["frontier_weight"].to_numpy(dtype=float)
        fitted, block_ids = weighted_pava(raw, weights, non_increasing=True)
        adjustment = fitted - raw
        adjusted = ~np.isclose(adjustment, 0.0, rtol=1e-12, atol=1e-12)
        result.loc[ordered.index, "monotone_frontier_value"] = fitted
        result.loc[ordered.index, "frontier_adjustment"] = adjustment
        result.loc[ordered.index, "frontier_adjusted"] = adjusted
        result.loc[ordered.index, "pava_block_id"] = block_ids
        result.loc[ordered.index, "raw_threshold_feasible"] = raw > threshold
        result.loc[ordered.index, "monotone_threshold_feasible"] = fitted > threshold
        raw_frontier = _first_loss_frontier(gaps, raw, threshold)
        monotone_frontier = _first_loss_frontier(gaps, fitted, threshold)
        summaries.append(
            {
                **metadata,
                "frontier_threshold": float(threshold),
                "raw_frontier_days": raw_frontier["frontier_days"],
                "raw_frontier_censoring": raw_frontier["censoring"],
                "raw_frontier_status": raw_frontier["status"],
                "raw_reversal_after_loss": raw_frontier["reversal_after_loss"],
                "monotone_frontier_days": monotone_frontier["frontier_days"],
                "monotone_frontier_censoring": monotone_frontier["censoring"],
                "monotone_frontier_status": monotone_frontier["status"],
                "n_gap_lengths": len(ordered),
                "n_adjusted_gap_lengths": int(adjusted.sum()),
                "max_absolute_adjustment": float(np.max(np.abs(adjustment))),
                "isotonic_method": "weighted_pava_non_increasing",
            }
        )
    result = result.sort_values("_safeguard_input_order").drop(
        columns="_safeguard_input_order"
    )
    result["pava_block_id"] = result["pava_block_id"].astype("Int64")
    return FrontierSafeguardResult(result, pd.DataFrame(summaries))


def add_guarded_climatology_skill(
    frame: pd.DataFrame,
    *,
    model_error_col: str = "model_mae",
    climatology_error_col: str = "climatology_mae",
    near_zero_threshold: float | None,
    output_col: str = "skill",
) -> pd.DataFrame:
    """Compute ``1 - model/climatology`` only under a declared guard.

    A missing threshold never defaults to zero: all skill values are withheld
    with ``threshold_not_declared`` status.  This prevents arbitrarily large
    ratios from a near-zero climatology denominator entering frontier analysis.
    """

    _require_columns(
        frame,
        [model_error_col, climatology_error_col],
        context="climatology denominator guard",
    )
    result = frame.copy()
    numerator = pd.to_numeric(result[model_error_col], errors="coerce").to_numpy(
        dtype=float
    )
    denominator = pd.to_numeric(
        result[climatology_error_col], errors="coerce"
    ).to_numpy(dtype=float)
    result[output_col] = np.nan
    result["climatology_denominator_threshold"] = near_zero_threshold
    result["climatology_denominator_guarded"] = True
    if near_zero_threshold is None:
        result["climatology_threshold_status"] = "not_declared"
        result["climatology_denominator_status"] = "threshold_not_declared"
        return result
    if not np.isfinite(near_zero_threshold) or near_zero_threshold <= 0:
        raise ValueError("near_zero_threshold must be finite and strictly positive")
    status = np.full(len(result), "ok", dtype=object)
    status[~np.isfinite(numerator)] = "nonfinite_model_error"
    status[np.isfinite(numerator) & (numerator < 0)] = "negative_model_error"
    status[~np.isfinite(denominator)] = "nonfinite_climatology_error"
    status[np.isfinite(denominator) & (denominator < 0)] = "negative_climatology_error"
    status[
        np.isfinite(denominator)
        & (denominator >= 0)
        & (denominator <= near_zero_threshold)
    ] = "near_zero_climatology_error"
    usable = status == "ok"
    result.loc[usable, output_col] = 1.0 - numerator[usable] / denominator[usable]
    result["climatology_threshold_status"] = "declared"
    result["climatology_denominator_status"] = status
    return result


def assess_application_boundary(
    curve: pd.DataFrame,
    criteria: Mapping[str, tuple[str, float]] | None,
    *,
    gap_col: str = "gap_length",
) -> dict[str, Any]:
    """Return a conservative tested-gap boundary and explicit claim status.

    If no application criterion was declared, the function intentionally
    returns no operational boundary.  With criteria, the boundary is the last
    gap in the initial feasible prefix; no recovery after a failed gap is used
    to extend it.
    """

    if not criteria:
        return {
            "application_threshold_status": "not_declared",
            "operational_boundary_days": np.nan,
            "operational_boundary_status": "not_estimable",
            "operational_boundary_claim_allowed": False,
            "reason": (
                "no predeclared application threshold; operational boundary "
                "is not reported"
            ),
        }
    _require_columns(curve, [gap_col, *criteria.keys()], context="application boundary")
    operators = {
        "<=": np.less_equal,
        "<": np.less,
        ">=": np.greater_equal,
        ">": np.greater,
    }
    data = curve[[gap_col, *criteria.keys()]].copy()
    data = data.apply(pd.to_numeric, errors="coerce").sort_values(gap_col)
    if data[gap_col].duplicated().any():
        raise ValueError("application boundary requires one row per tested gap")
    if data.empty or not np.isfinite(data.to_numpy(dtype=float)).all():
        return {
            "application_threshold_status": "declared",
            "operational_boundary_days": np.nan,
            "operational_boundary_status": "invalid_inputs",
            "operational_boundary_claim_allowed": False,
            "reason": "application criteria require finite values at every tested gap",
        }
    feasible = np.ones(len(data), dtype=bool)
    failed_metrics: list[tuple[str, ...]] = []
    for row_index in range(len(data)):
        failed: list[str] = []
        for metric, (operator, threshold) in criteria.items():
            if operator not in operators:
                raise ValueError(f"unsupported application operator: {operator}")
            if not np.isfinite(threshold):
                raise ValueError("application thresholds must be finite")
            if not bool(
                operators[operator](float(data.iloc[row_index][metric]), threshold)
            ):
                failed.append(metric)
        failed_metrics.append(tuple(failed))
        feasible[row_index] = not failed
    gaps = data[gap_col].to_numpy(dtype=float)
    failures = np.flatnonzero(~feasible)
    if not failures.size:
        return {
            "application_threshold_status": "declared",
            "operational_boundary_days": float(gaps[-1]),
            "operational_boundary_lower_days": float(gaps[-1]),
            "operational_boundary_upper_days": np.nan,
            "operational_boundary_status": "right_censored",
            "operational_boundary_claim_allowed": True,
            "nonmonotonic_feasibility": False,
            "limiting_metrics": (),
            "reason": "all declared criteria pass through the largest tested gap",
        }
    first_failure = int(failures[0])
    regained = bool(feasible[first_failure + 1 :].any())
    if first_failure == 0:
        return {
            "application_threshold_status": "declared",
            "operational_boundary_days": np.nan,
            "operational_boundary_lower_days": np.nan,
            "operational_boundary_upper_days": float(gaps[0]),
            "operational_boundary_status": "left_censored",
            "operational_boundary_claim_allowed": True,
            "nonmonotonic_feasibility": regained,
            "limiting_metrics": failed_metrics[0],
            "reason": "a declared criterion fails at the smallest tested gap",
        }
    return {
        "application_threshold_status": "declared",
        "operational_boundary_days": float(gaps[first_failure - 1]),
        "operational_boundary_lower_days": float(gaps[first_failure - 1]),
        "operational_boundary_upper_days": float(gaps[first_failure]),
        "operational_boundary_status": "interval_censored_between_tested_gaps",
        "operational_boundary_claim_allowed": True,
        "nonmonotonic_feasibility": regained,
        "limiting_metrics": failed_metrics[first_failure],
        "reason": "reported conservatively at the last passing tested gap",
    }


def _benjamini_hochberg(values: np.ndarray) -> np.ndarray:
    adjusted = np.full(values.shape, np.nan, dtype=float)
    finite_positions = np.flatnonzero(np.isfinite(values))
    if not finite_positions.size:
        return adjusted
    order = finite_positions[np.argsort(values[finite_positions], kind="stable")]
    count = len(order)
    running = 1.0
    for reverse_rank in range(count - 1, -1, -1):
        position = int(order[reverse_rank])
        rank = reverse_rank + 1
        candidate = min(1.0, values[position] * count / rank)
        running = min(running, candidate)
        adjusted[position] = running
    return adjusted


def benjamini_hochberg_by_family(
    hypotheses: pd.DataFrame,
    *,
    p_col: str = "p_value",
    family_cols: str | Sequence[str] = "hypothesis_family",
    output_col: str = "p_bh",
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Apply BH independently within explicitly named hypothesis families."""

    families = [family_cols] if isinstance(family_cols, str) else list(family_cols)
    if not families:
        raise ValueError("at least one named hypothesis-family column is required")
    _require_columns(
        hypotheses, [p_col, *families], context="family-wise BH adjustment"
    )
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between zero and one")
    result = hypotheses.copy()
    for column in families:
        invalid_name = result[column].isna() | result[column].astype(
            str
        ).str.strip().eq("")
        if invalid_name.any():
            raise ValueError(
                f"every hypothesis must have a non-empty named family in {column!r}"
            )
    p_values = pd.to_numeric(result[p_col], errors="coerce")
    invalid_p = p_values.notna() & ((p_values < 0) | (p_values > 1))
    nonnumeric_present = result[p_col].notna() & p_values.isna()
    if invalid_p.any() or nonnumeric_present.any():
        raise ValueError("finite p-values must lie in [0, 1]")
    result[output_col] = np.nan
    result["bh_family_size"] = 0
    result["bh_finite_hypotheses"] = 0
    grouped = result.groupby(families, dropna=False, observed=True, sort=True).indices
    for positions in grouped.values():
        family_values = p_values.iloc[positions].to_numpy(dtype=float)
        result.iloc[positions, result.columns.get_loc(output_col)] = (
            _benjamini_hochberg(family_values)
        )
        result.iloc[positions, result.columns.get_loc("bh_family_size")] = len(
            positions
        )
        result.iloc[positions, result.columns.get_loc("bh_finite_hypotheses")] = int(
            np.isfinite(family_values).sum()
        )
    result["bh_reject"] = result[output_col].le(alpha) & result[output_col].notna()
    result["bh_alpha"] = float(alpha)
    result["bh_scope"] = "within_named_hypothesis_family"
    return result


__all__ = [
    "AnchorBootstrapResult",
    "FrontierBootstrapResult",
    "FrontierSafeguardResult",
    "MaskOverlapAudit",
    "add_guarded_climatology_skill",
    "anchor_year_cluster_bootstrap",
    "anchor_year_frontier_bootstrap",
    "assess_application_boundary",
    "audit_mask_anchor_overlap",
    "average_training_seeds_by_anchor",
    "benjamini_hochberg_by_family",
    "raw_and_monotone_frontier",
    "weighted_pava",
]
