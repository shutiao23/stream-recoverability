"""State-segment detection and same-state versus changed-state splits (E6)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


def variance_ratio_segments(
    values: Sequence[float],
    dates: Sequence[object],
    *,
    min_days: int = 365,
) -> dict[str, object]:
    """One-break scan that maximizes a two-segment variance contrast.

    This is a fitting-period diagnostic, not a causal change-point claim.
    """

    series = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
    parsed = pd.DatetimeIndex(pd.to_datetime(dates))
    if len(parsed) != len(series):
        raise ValueError("dates must align with values")
    if len(series) < 2 * min_days:
        return {
            "break_index": None,
            "break_date": None,
            "pre_variance": float("nan"),
            "post_variance": float("nan"),
            "score": float("nan"),
            "reason": "record_shorter_than_two_minimum_windows",
        }
    best_score = -np.inf
    best = min_days
    for index in range(min_days, len(series) - min_days):
        left = series[:index]
        right = series[index:]
        left = left[np.isfinite(left)]
        right = right[np.isfinite(right)]
        if left.size < 2 or right.size < 2:
            continue
        score = abs(float(np.log(np.var(right) + 1e-12) - np.log(np.var(left) + 1e-12)))
        if score > best_score:
            best_score = score
            best = index
    left = series[:best]
    right = series[best:]
    return {
        "break_index": int(best),
        "break_date": parsed[best].date().isoformat(),
        "pre_variance": float(np.nanvar(left)),
        "post_variance": float(np.nanvar(right)),
        "score": float(best_score),
        "reason": None,
    }


def assign_state(
    dates: Sequence[object],
    break_date: str | None,
    *,
    labels: tuple[str, str] = ("pre", "post"),
) -> np.ndarray:
    parsed = pd.DatetimeIndex(pd.to_datetime(dates))
    if break_date is None:
        return np.array([labels[0]] * len(parsed), dtype=object)
    stamp = pd.Timestamp(break_date)
    return np.where(parsed < stamp, labels[0], labels[1])


def evaluation_regime(fit_state: str, eval_state: str) -> str:
    if fit_state == eval_state:
        return "same_state"
    return "changed_state"


__all__ = ["assign_state", "evaluation_regime", "variance_ratio_segments"]
