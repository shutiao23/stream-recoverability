"""Clustered uncertainty. Every interval in this study is clustered by network.

Station-years from one network are not independent observations, and reusing
one station-year under several outage realizations does not create several
independent observations either. Both are handled by resampling networks.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
import pandas as pd

DEFAULT_DRAWS = 2000


def cluster_bootstrap(
    frame: pd.DataFrame,
    statistic: Callable[[pd.DataFrame], float],
    *,
    cluster: str = "network_id",
    draws: int = DEFAULT_DRAWS,
    seed: int = 0,
    alpha: float = 0.05,
) -> dict[str, float]:
    """Bootstrap ``statistic`` by resampling whole clusters with replacement."""

    point = float(statistic(frame))
    groups = {key: block for key, block in frame.groupby(cluster, sort=True)}
    keys = list(groups)
    if len(keys) < 2:
        return {"point": point, "low": float("nan"), "high": float("nan"), "n_clusters": len(keys)}
    rng = np.random.default_rng(int(seed))
    values = np.empty(int(draws), dtype=float)
    for draw in range(int(draws)):
        picked = rng.integers(0, len(keys), size=len(keys))
        sample = pd.concat([groups[keys[int(i)]] for i in picked], ignore_index=True)
        try:
            values[draw] = float(statistic(sample))
        except (ValueError, ZeroDivisionError, KeyError):
            values[draw] = np.nan
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {"point": point, "low": float("nan"), "high": float("nan"), "n_clusters": len(keys)}
    return {
        "point": point,
        "low": float(np.quantile(finite, alpha / 2)),
        "high": float(np.quantile(finite, 1 - alpha / 2)),
        "se": float(np.std(finite, ddof=1)),
        "n_clusters": len(keys),
    }


def paired_cluster_bootstrap(
    frame: pd.DataFrame,
    left: str,
    right: str,
    *,
    cluster: str = "network_id",
    draws: int = DEFAULT_DRAWS,
    seed: int = 0,
    alpha: float = 0.05,
) -> dict[str, float]:
    """Paired difference ``left - right`` on the same cases, clustered by network."""

    def statistic(block: pd.DataFrame) -> float:
        return float(pd.to_numeric(block[left], errors="coerce").mean() - pd.to_numeric(block[right], errors="coerce").mean())

    return cluster_bootstrap(frame, statistic, cluster=cluster, draws=draws, seed=seed, alpha=alpha)


def network_equal_mean(frame: pd.DataFrame, column: str, *, cluster: str = "network_id") -> float:
    """Network-equal mean: each network contributes once, whatever its size."""

    per_network = frame.groupby(cluster)[column].mean()
    return float(per_network.mean())


def precision_for_margin(sd_between: float, margin: float, *, z: float = 1.96) -> float:
    """Clusters needed to resolve ``margin`` at the stated confidence."""

    if not np.isfinite(sd_between) or margin <= 0:
        return float("nan")
    return float((z * sd_between / margin) ** 2)


def resolvable_margin(sd_between: float, n_clusters: int, *, z: float = 1.96) -> float:
    """The smallest difference a study with this many clusters can resolve."""

    if not np.isfinite(sd_between) or n_clusters < 2:
        return float("nan")
    return float(z * sd_between / np.sqrt(n_clusters))


def rate(values: Sequence[float], threshold: float) -> float:
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return float("nan")
    return float((finite > float(threshold)).mean())
