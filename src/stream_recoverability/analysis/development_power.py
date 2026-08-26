"""Simulation-based network-count power for the provisional Spearman rule."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.analysis.hierarchical_confirmation import (
    network_blocked_spearman,
    simulate_confirmation_panel,
)


def power_curve(
    network_counts: tuple[int, ...] = (6, 8, 12, 16, 20),
    *,
    stations_per_network: int = 4,
    slope: float = 1.0,
    noise: float = 0.25,
    n_replicates: int = 80,
    spearman_min: float = 0.60,
    seed: int = 0,
) -> pd.DataFrame:
    """Estimate the chance of beating a Spearman threshold under a known slope."""

    rng = np.random.default_rng(seed)
    rows = []
    for n_networks in network_counts:
        hits = 0
        estimates = []
        for _ in range(n_replicates):
            panel = simulate_confirmation_panel(
                n_networks=n_networks,
                stations_per_network=stations_per_network,
                slope=slope,
                noise=noise,
                seed=int(rng.integers(1e9)),
            )
            rho = network_blocked_spearman(panel)["spearman"]
            estimates.append(rho)
            if np.isfinite(rho) and rho >= spearman_min:
                hits += 1
        finite = [value for value in estimates if np.isfinite(value)]
        rows.append(
            {
                "n_networks": n_networks,
                "stations_per_network": stations_per_network,
                "slope": slope,
                "noise": noise,
                "spearman_min": spearman_min,
                "n_replicates": n_replicates,
                "power": hits / n_replicates,
                "mean_spearman": float(np.mean(finite)) if finite else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def recommended_network_count(curve: pd.DataFrame, *, power_min: float = 0.8) -> int | None:
    eligible = curve.loc[curve["power"].ge(power_min)]
    if eligible.empty:
        return None
    return int(eligible["n_networks"].min())


__all__ = ["power_curve", "recommended_network_count"]
