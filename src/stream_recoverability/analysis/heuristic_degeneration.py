"""Structural defects of the additive donor-plus-memory heuristic.

These results are identities of the formula, not empirical findings from a
river.  They exist so the current Design cannot be mistaken for a theorem.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from stream_recoverability.analysis.conditional_observability import (
    mean_nearest_boundary_distance,
    nearest_boundary_distances,
)
from stream_recoverability.analysis.recoverability_budget import (
    budget_decomposition,
)


def memory_component(donor_r2: float, rho: float) -> float:
    donor = float(donor_r2)
    if not 0.0 <= donor <= 1.0:
        raise ValueError("donor_r2 must lie in [0, 1]")
    return (1.0 - donor) * float(rho) ** 2


def forced_donor_dominated(donor_r2: float) -> bool:
    """Return True when the formula cannot emit a memory label."""

    return float(donor_r2) >= 0.5


def degeneration_bound(donor_r2: float) -> dict[str, float | bool]:
    """Prove M <= 1-D <= D whenever D >= 0.5 and rho^2 <= 1."""

    donor = float(donor_r2)
    max_memory = 1.0 - donor
    return {
        "R2_donor": donor,
        "max_memory_component": max_memory,
        "memory_always_le_donor": bool(max_memory <= donor + 1e-15),
        "forced_donor_dominated": forced_donor_dominated(donor),
        "any_rho_can_produce_memory_label": bool(max_memory > donor),
    }


def scan_degeneration(
    donor_r2_grid: Sequence[float] | None = None,
    rho_grid: Sequence[float] | None = None,
) -> pd.DataFrame:
    """Enumerate the hard-label map over donor R2 and ACF."""

    donors = (
        np.linspace(0.0, 1.0, 21)
        if donor_r2_grid is None
        else np.asarray(donor_r2_grid, dtype=float)
    )
    rhos = (
        np.linspace(0.0, 1.0, 21)
        if rho_grid is None
        else np.asarray(rho_grid, dtype=float)
    )
    rows = []
    for donor in donors:
        for rho in rhos:
            memory = memory_component(float(donor), float(rho))
            rows.append(
                {
                    "R2_donor": float(donor),
                    "rho": float(rho),
                    "memory_component": memory,
                    "hard_label": (
                        "donor_dominated" if donor >= memory else "memory_dominated"
                    ),
                    "forced_by_formula": forced_donor_dominated(float(donor)),
                }
            )
    return pd.DataFrame(rows)


def jensen_acf_gap(
    phi: float,
    gap_length: int,
) -> dict[str, float]:
    """Show E[rho^2(L)] != rho^2(E[L]) for an AR(1) anomaly process.

    \(L\) is the nearest-boundary distance inside a length-``gap_length``
    block.  The heuristic evaluates \(\rho^2\) at \(d/4\), which is only an
    approximation to \(E[L]\) and is applied outside the expectation.
    """

    if not 0.0 < abs(phi) < 1.0:
        raise ValueError("phi must lie in (0, 1)")
    distances = nearest_boundary_distances(gap_length)
    rho_sq = np.abs(phi) ** (2.0 * distances)
    mean_distance = float(np.mean(distances))
    expected_rho_sq = float(np.mean(rho_sq))
    rho_sq_at_mean = float(abs(phi) ** (2.0 * mean_distance))
    rho_sq_at_d_over_4 = float(abs(phi) ** (2.0 * (gap_length / 4.0)))
    return {
        "phi": float(phi),
        "gap_length": float(gap_length),
        "mean_nearest_boundary": mean_distance,
        "d_over_4": float(gap_length) / 4.0,
        "mean_nearest_minus_d_over_4": mean_distance - gap_length / 4.0,
        "E_rho_squared": expected_rho_sq,
        "rho_squared_at_E_L": rho_sq_at_mean,
        "rho_squared_at_d_over_4": rho_sq_at_d_over_4,
        "jensen_gap": expected_rho_sq - rho_sq_at_mean,
        "heuristic_gap": expected_rho_sq - rho_sq_at_d_over_4,
    }


def in_sample_r2(target: np.ndarray, donors: Sequence[np.ndarray]) -> float:
    design = np.column_stack([np.ones(len(target)), *donors])
    valid = np.isfinite(target) & np.isfinite(design).all(axis=1)
    y = target[valid]
    x = design[valid]
    if y.size < x.shape[1] + 1 or float(np.var(y)) == 0:
        return float("nan")
    coefficients = np.linalg.lstsq(x, y, rcond=None)[0]
    residual = float(np.square(y - x @ coefficients).sum())
    total = float(np.square(y - y.mean()).sum())
    return float(np.clip(1.0 - residual / total, 0.0, 1.0))


def year_block_cv_r2(
    target: np.ndarray,
    donors: Sequence[np.ndarray],
    years: Sequence[int],
) -> float:
    """Leave-one-year-out R2 on held-out years."""

    y = np.asarray(target, dtype=float)
    donor_matrix = np.column_stack([np.asarray(item, dtype=float) for item in donors])
    year_index = np.asarray(years)
    if len(year_index) != len(y):
        raise ValueError("years must align with the target")
    unique = np.array(sorted(pd.unique(year_index)))
    if unique.size < 2:
        return float("nan")
    residuals: list[float] = []
    totals: list[float] = []
    for held in unique:
        train = year_index != held
        test = year_index == held
        if int(train.sum()) < donor_matrix.shape[1] + 2 or int(test.sum()) < 2:
            continue
        design_train = np.column_stack([np.ones(int(train.sum())), donor_matrix[train]])
        design_test = np.column_stack([np.ones(int(test.sum())), donor_matrix[test]])
        valid_train = np.isfinite(y[train]) & np.isfinite(design_train).all(axis=1)
        valid_test = np.isfinite(y[test]) & np.isfinite(design_test).all(axis=1)
        if int(valid_train.sum()) < design_train.shape[1] + 1:
            continue
        coefficients = np.linalg.lstsq(
            design_train[valid_train], y[train][valid_train], rcond=None
        )[0]
        observed = y[test][valid_test]
        predicted = design_test[valid_test] @ coefficients
        residuals.append(float(np.square(observed - predicted).sum()))
        totals.append(float(np.square(observed - observed.mean()).sum()))
    if not totals or sum(totals) == 0:
        return float("nan")
    return float(np.clip(1.0 - sum(residuals) / sum(totals), 0.0, 1.0))


def donor_count_inflation(
    n_time: int = 800,
    n_years: int = 8,
    n_donors: int = 8,
    signal_scale: float = 1.0,
    noise_scale: float = 0.75,
    seed: int = 0,
) -> pd.DataFrame:
    """Show in-sample R2 rising with redundant donors while CV R2 does not."""

    rng = np.random.default_rng(seed)
    factor = rng.normal(0.0, signal_scale, n_time)
    target = factor + rng.normal(0.0, noise_scale, n_time)
    years = np.repeat(np.arange(n_years), n_time // n_years + 1)[:n_time]
    donors = [
        factor + rng.normal(0.0, noise_scale, n_time) for _ in range(n_donors)
    ]
    rows = []
    for count in range(1, n_donors + 1):
        selected = donors[:count]
        rows.append(
            {
                "n_donors": count,
                "in_sample_r2": in_sample_r2(target, selected),
                "year_block_cv_r2": year_block_cv_r2(target, selected, years),
            }
        )
    return pd.DataFrame(rows)


def heuristic_from_frame(
    train_frame: pd.DataFrame,
    station: str,
    donors: Sequence[str],
    gap_lengths: Sequence[int],
) -> pd.DataFrame:
    """Wrap the frozen additive heuristic without changing its formula."""

    result = budget_decomposition(train_frame, station, donors, gap_lengths)
    result["forced_donor_dominated"] = result["R2_donor"].ge(0.5)
    result["mean_nearest_boundary"] = [
        mean_nearest_boundary_distance(int(gap)) for gap in result["gap_length_days"]
    ]
    return result


__all__ = [
    "degeneration_bound",
    "donor_count_inflation",
    "forced_donor_dominated",
    "heuristic_from_frame",
    "in_sample_r2",
    "jensen_acf_gap",
    "memory_component",
    "scan_degeneration",
    "year_block_cv_r2",
]
