"""Natural-outage catalogs and the offline versus online task split (E7)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

TASK_OFFLINE = "offline_archival"
TASK_ONLINE = "online_causal"


def gap_runs(missing: Sequence[bool]) -> list[dict[str, int]]:
    """Return contiguous missing blocks as start, end, and length."""

    flags = np.asarray(missing, dtype=bool)
    if flags.size == 0:
        return []
    starts = np.flatnonzero(flags & ~np.r_[False, flags[:-1]])
    ends = np.flatnonzero(flags & ~np.r_[flags[1:], False])
    return [
        {"start": int(start), "end": int(end), "length": int(end - start + 1)}
        for start, end in zip(starts, ends, strict=True)
    ]


def catalog_from_quality_flags(
    frame: pd.DataFrame,
    *,
    station_col: str = "station_id",
    date_col: str = "date",
    missing_col: str = "missing",
) -> pd.DataFrame:
    """Build an empirical outage catalog from quality or completeness flags."""

    rows = []
    parsed = frame.copy()
    parsed[date_col] = pd.to_datetime(parsed[date_col])
    for station, group in parsed.groupby(station_col, sort=False):
        ordered = group.sort_values(date_col)
        for gap in gap_runs(ordered[missing_col].fillna(False).to_numpy()):
            start_date = ordered.iloc[gap["start"]][date_col]
            rows.append(
                {
                    "station_id": str(station),
                    "start_date": pd.Timestamp(start_date).date().isoformat(),
                    "length_days": gap["length"],
                    "season": _season(pd.Timestamp(start_date)),
                    "suite": "natural_outage",
                }
            )
    return pd.DataFrame(rows)


def _season(stamp: pd.Timestamp) -> str:
    return ("DJF", "MAM", "JJA", "SON")[(int(stamp.month) % 12) // 3]


def weight_natural_suite(catalog: pd.DataFrame) -> pd.DataFrame:
    """Empirical weights are length-by-season frequencies."""

    if catalog.empty:
        return catalog.assign(weight=pd.Series(dtype=float))
    result = catalog.copy()
    counts = result.groupby(["length_days", "season"], dropna=False).size()
    mapped = result.set_index(["length_days", "season"]).index.map(counts)
    result["weight"] = np.asarray(mapped, dtype=float) / float(len(result))
    return result


def adversarial_suite(
    lengths: Sequence[int] = (14, 30, 90, 180, 365),
    seasons: Sequence[str] = ("DJF", "MAM", "JJA", "SON"),
) -> pd.DataFrame:
    rows = []
    for length in lengths:
        for season in seasons:
            rows.append(
                {
                    "station_id": "*",
                    "start_date": None,
                    "length_days": int(length),
                    "season": season,
                    "suite": "adversarial_stress",
                    "weight": 1.0 / (len(lengths) * len(seasons)),
                }
            )
    return pd.DataFrame(rows)


def task_contract(task: str) -> dict[str, bool | str]:
    if task == TASK_OFFLINE:
        return {
            "task": TASK_OFFLINE,
            "left_boundary_allowed": True,
            "right_boundary_allowed": True,
        }
    if task == TASK_ONLINE:
        return {
            "task": TASK_ONLINE,
            "left_boundary_allowed": True,
            "right_boundary_allowed": False,
        }
    raise ValueError("task must be offline_archival or online_causal")


__all__ = [
    "TASK_OFFLINE",
    "TASK_ONLINE",
    "adversarial_suite",
    "catalog_from_quality_flags",
    "gap_runs",
    "task_contract",
    "weight_natural_suite",
]
