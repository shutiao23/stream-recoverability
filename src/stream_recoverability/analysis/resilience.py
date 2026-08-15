"""Monitoring-network failure curves, AUC, and station importance."""

from __future__ import annotations

from collections.abc import Sequence
import json
import re
from typing import Any

import numpy as np
import pandas as pd


def parse_failed_sites(value: object) -> tuple[str, ...]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ()
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"none", "full_network", "[]"}:
            return ()
        if text.startswith("["):
            parsed = json.loads(text)
            tokens = [str(item) for item in parsed]
        else:
            tokens = [item for item in re.split(r"[+,|;/\s]+", text) if item]
    elif isinstance(value, (list, tuple, set, frozenset, np.ndarray)):
        tokens = [str(item) for item in value]
    else:
        tokens = [str(value)]
    return tuple(sorted(set(token.strip() for token in tokens if token.strip())))


def _with_failures(
    events: pd.DataFrame,
    failed_sites_col: str,
    total_sites: int | None,
) -> tuple[pd.DataFrame, int, str | None]:
    if failed_sites_col not in events:
        raise ValueError(f"network resilience requires column: {failed_sites_col}")
    data = events.copy()
    data["failed_sites"] = data[failed_sites_col].map(parse_failed_sites)
    data["failed_count"] = data["failed_sites"].map(len).astype(int)
    if total_sites is None:
        if "network_size" in data and pd.to_numeric(data["network_size"], errors="coerce").notna().any():
            total_sites = int(pd.to_numeric(data["network_size"], errors="coerce").max())
            reason = None
        else:
            all_sites = set().union(*data["failed_sites"].tolist()) if len(data) else set()
            total_sites = max(len(all_sites), int(data["failed_count"].max()) if len(data) else 0)
            reason = "network size inferred from observed failed-site labels"
    else:
        reason = None
    if total_sites < 1:
        raise ValueError("total_sites must be positive or inferable")
    if (data["failed_count"] > total_sites).any():
        raise ValueError("a failure set is larger than total_sites")
    data["failure_fraction"] = data["failed_count"] / float(total_sites)
    data["failure_class"] = np.select(
        [
            data["failed_count"].eq(0),
            data["failed_count"].eq(1),
            data["failed_count"].eq(total_sites),
            data["failed_count"].eq(2),
        ],
        ["none", "single", "full_network", "double"],
        default="multiple",
    )
    return data, total_sites, reason


def resilience_curve(
    events: pd.DataFrame,
    *,
    skill_col: str = "skill",
    failed_sites_col: str = "failed_stations",
    total_sites: int | None = None,
    group_cols: Sequence[str] = ("model", "target", "gap_length"),
) -> pd.DataFrame:
    """Compute relative skill as a function of failed-node fraction."""

    if skill_col not in events:
        raise ValueError(f"network resilience requires column: {skill_col}")
    data, total_sites, inference_reason = _with_failures(
        events, failed_sites_col, total_sites
    )
    data[skill_col] = pd.to_numeric(data[skill_col], errors="coerce")
    active_groups = [column for column in group_cols if column in data]
    aggregation_cols = [*active_groups, "failed_count", "failure_fraction", "failure_class"]
    curve = (
        data.dropna(subset=[skill_col])
        .groupby(aggregation_cols, dropna=False, observed=True)[skill_col]
        .agg([("mean_skill", "mean"), ("n_events", "size")])
        .reset_index()
    )
    if curve.empty:
        return curve
    if active_groups:
        full_lookup = (
            curve.loc[curve["failed_count"].eq(0)]
            .set_index(active_groups)["mean_skill"]
            .to_dict()
        )
        keys = curve[active_groups].apply(tuple, axis=1)
        if len(active_groups) == 1:
            keys = curve[active_groups[0]]
        curve["full_network_skill"] = keys.map(full_lookup)
    else:
        full_rows = curve.loc[curve["failed_count"].eq(0), "mean_skill"]
        curve["full_network_skill"] = full_rows.iloc[0] if len(full_rows) else np.nan
    denominator = curve["full_network_skill"].replace(0.0, np.nan)
    curve["relative_skill"] = curve["mean_skill"] / denominator
    curve["network_size"] = total_sites
    curve["reason"] = inference_reason
    missing_full = curve["full_network_skill"].isna()
    curve.loc[missing_full, "reason"] = "no zero-failure full-network reference"
    zero_full = curve["full_network_skill"].eq(0)
    curve.loc[zero_full, "reason"] = "full-network skill is zero"
    return curve


def resilience_auc(
    curve: pd.DataFrame,
    *,
    group_cols: Sequence[str] = ("model", "target", "gap_length"),
) -> pd.DataFrame:
    """Integrate relative skill over failed fraction, requiring coverage 0..1."""

    required = {"failure_fraction", "relative_skill"}
    missing = sorted(required - set(curve.columns))
    if missing:
        raise ValueError(f"resilience AUC requires columns: {missing}")
    active_groups = [column for column in group_cols if column in curve]
    grouped = curve.groupby(active_groups, dropna=False, observed=True) if active_groups else [((), curve)]
    rows: list[dict[str, Any]] = []
    for group_key, group in grouped:
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(zip(active_groups, group_key if active_groups else (), strict=True))
        points = (
            group[["failure_fraction", "relative_skill"]]
            .dropna()
            .groupby("failure_fraction", as_index=False)["relative_skill"]
            .mean()
            .sort_values("failure_fraction")
        )
        spans_full_range = (
            len(points) >= 2
            and np.isclose(points["failure_fraction"].iloc[0], 0.0)
            and np.isclose(points["failure_fraction"].iloc[-1], 1.0)
        )
        if spans_full_range:
            auc = float(np.trapz(points["relative_skill"], points["failure_fraction"]))
            reason = None
        else:
            auc = np.nan
            reason = "resilience curve must span failed fractions 0 and 1"
        rows.append(
            {
                **metadata,
                "resilience_auc": auc,
                "n_failure_levels": int(len(points)),
                "reason": reason,
            }
        )
    return pd.DataFrame(rows)


def node_importance(
    events: pd.DataFrame,
    *,
    value_col: str = "skill",
    failed_sites_col: str = "failed_stations",
    higher_is_better: bool = True,
    group_cols: Sequence[str] = ("model", "target", "gap_length"),
) -> pd.DataFrame:
    """Compare each singleton station failure with the no-failure reference."""

    if value_col not in events:
        raise ValueError(f"node importance requires column: {value_col}")
    data, _, _ = _with_failures(events, failed_sites_col, total_sites=None)
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    active_groups = [column for column in group_cols if column in data]
    grouped = data.groupby(active_groups, dropna=False, observed=True) if active_groups else [((), data)]
    rows: list[dict[str, Any]] = []
    for group_key, group in grouped:
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(zip(active_groups, group_key if active_groups else (), strict=True))
        full = group.loc[group["failed_count"].eq(0), value_col].dropna()
        full_value = float(full.mean()) if len(full) else np.nan
        singleton = group.loc[group["failed_count"].eq(1)].copy()
        for sites, values in singleton.groupby("failed_sites", observed=True):
            failed_value = float(values[value_col].mean())
            impact = (
                full_value - failed_value
                if higher_is_better
                else failed_value - full_value
            )
            rows.append(
                {
                    **metadata,
                    "station_id": sites[0],
                    "full_network_value": full_value,
                    "failed_value": failed_value,
                    "impact": impact if np.isfinite(full_value) else np.nan,
                    "n_events": int(len(values)),
                    "reason": None if np.isfinite(full_value) else "no zero-failure reference",
                }
            )
    return pd.DataFrame(rows)


def analyze_resilience(
    events: pd.DataFrame,
    **kwargs: Any,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    curve = resilience_curve(events, **kwargs)
    auc = resilience_auc(curve)
    importance = node_importance(
        events,
        value_col=kwargs.get("skill_col", "skill"),
        failed_sites_col=kwargs.get("failed_sites_col", "failed_stations"),
    )
    return curve, auc, importance


__all__ = [
    "analyze_resilience",
    "node_importance",
    "parse_failed_sites",
    "resilience_auc",
    "resilience_curve",
]
