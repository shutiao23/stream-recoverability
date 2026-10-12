"""Shared scoring for the v18 endpoint studies."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap


def interannual_scale(cases: pd.DataFrame, truth_column: str) -> float:
    """Mean over stations of the within-station standard deviation of the truth.

    A tolerance in the units of an estimand means nothing without the scale of
    that estimand, and the scale has to be the year-to-year variation of the
    quantity itself rather than anything borrowed from another endpoint.
    """

    truth = (
        cases.groupby(["network_id", "station_id", "year"])[truth_column]
        .first()
        .reset_index()
    )
    per_station = truth.groupby(["network_id", "station_id"])[truth_column].agg(["std", "size"])
    usable = per_station.loc[(per_station["size"] >= 3) & per_station["std"].notna()]
    return float(usable["std"].mean())


def auc(labels: np.ndarray, score: np.ndarray) -> float:
    good = np.isfinite(score) & np.isfinite(labels)
    if good.sum() < 20:
        return float("nan")
    y = labels[good]
    if y.min() == y.max():
        return float("nan")
    return float(roc_auc_score(y, score[good]))


def axis_table(
    cases: pd.DataFrame,
    label: np.ndarray,
    axes: Sequence[str],
    *,
    higher_is_worse: dict[str, bool] | None = None,
) -> dict[str, float]:
    """AUC of every candidate axis against a consequential-error label.

    Each axis is oriented so that a larger value means a worse case, which is
    what a screening rule needs; the orientation is declared, not fitted.
    """

    signs = higher_is_worse or {}
    out: dict[str, float] = {}
    for name in axes:
        if name not in cases.columns:
            out[f"auc_{name}"] = float("nan")
            continue
        values = pd.to_numeric(cases[name], errors="coerce").to_numpy(dtype=float)
        if not signs.get(name, True):
            values = -values
        out[f"auc_{name}"] = auc(label.astype(float), values)
    return out


def clustered_auc_contrast(
    cases: pd.DataFrame,
    label_column: str,
    left: str,
    right: str,
    *,
    higher_is_worse: dict[str, bool] | None = None,
    seed: int = 20260924,
    draws: int = 600,
) -> dict[str, float]:
    """AUC(left) - AUC(right) with whole networks resampled."""

    signs = higher_is_worse or {}
    frame = cases[["network_id", label_column, left, right]].dropna()

    def statistic(block: pd.DataFrame) -> float:
        y = block[label_column].to_numpy(dtype=float)
        if y.min() == y.max():
            return float("nan")
        a = block[left].to_numpy(dtype=float) * (1 if signs.get(left, True) else -1)
        b = block[right].to_numpy(dtype=float) * (1 if signs.get(right, True) else -1)
        return float(roc_auc_score(y, a) - roc_auc_score(y, b))

    result = cluster_bootstrap(frame, statistic, draws=draws, seed=seed)
    result["left"] = left
    result["right"] = right
    result["excludes_zero"] = bool(
        np.isfinite(result.get("low", np.nan))
        and np.isfinite(result.get("high", np.nan))
        and (result["low"] > 0 or result["high"] < 0)
    )
    return result
