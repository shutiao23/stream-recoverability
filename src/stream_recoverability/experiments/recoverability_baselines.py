"""Recoverability-predictor baselines and incremental-value comparisons.

The scientific target is not that a recovery model wins.  It is that the
conditional-observability predictor explains held-out residual recoverability
after simple monotone and ACF/donor baselines.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from stream_recoverability.analysis.conditional_observability import (
    expected_gaussian_mae,
    information_set_conditionals,
)
from stream_recoverability.analysis.heuristic_degeneration import memory_component
from stream_recoverability.analysis.recoverability_spectrum import recoverability
from stream_recoverability.experiments.synthetic_river import SyntheticRiver


Predictor = Callable[[int], float]


def gap_length_only(gap_length: int, *, scale: float = 30.0) -> float:
    return float(np.exp(-float(gap_length) / scale))


def acf_only(phi: float, gap_length: int) -> float:
    distances = np.minimum(
        np.arange(gap_length) + 1, gap_length - np.arange(gap_length)
    )
    residual = float(np.mean(np.abs(phi) ** (2.0 * distances)))
    return float(1.0 - np.sqrt(residual))


def donor_r2_only(donor_r2: float, gap_length: int) -> float:
    del gap_length
    return float(1.0 - np.sqrt(max(0.0, 1.0 - donor_r2)))


def additive_heuristic(donor_r2: float, rho_at_d_over_4: float) -> float:
    available = float(
        np.clip(donor_r2 + memory_component(donor_r2, rho_at_d_over_4), 0.0, 1.0)
    )
    return float(1.0 - np.sqrt(1.0 - available))


def memory_range_index(acf30: float, temperature_range: float) -> float:
    if not np.isfinite(temperature_range) or temperature_range <= 0:
        return float("nan")
    return float(acf30 / temperature_range)


def ar1_phi_from_sigma(sigma_00: float, transition_00: float) -> float:
    del sigma_00
    return float(np.clip(transition_00, -0.999, 0.999))


def predictor_frame(
    river: SyntheticRiver,
    *,
    gap_lengths: Sequence[int] = (14, 30, 90, 180),
) -> pd.DataFrame:
    """Compare simple predictors with the conditional operator on one river."""

    target_var = float(river.sigma[river.target, river.target])
    donors = list(river.donors)
    if donors:
        sigma_dd = river.sigma[np.ix_(donors, donors)]
        sigma_td = river.sigma[river.target, donors]
        try:
            donor_r2 = float(
                np.clip(sigma_td @ np.linalg.solve(sigma_dd, sigma_td) / target_var, 0, 1)
            )
        except np.linalg.LinAlgError:
            donor_r2 = float(
                np.clip(
                    sigma_td @ np.linalg.pinv(sigma_dd) @ sigma_td / target_var, 0, 1
                )
            )
    else:
        donor_r2 = 0.0
    phi = float(river.transition[river.target, river.target])
    rows = []
    for gap in gap_lengths:
        conditionals = information_set_conditionals(
            river.transition,
            river.sigma,
            target=river.target,
            donors=river.donors,
            gap_length=int(gap),
        )
        loss_0 = float(conditionals["none"]["expected_mae_conditional"])
        observed = recoverability(
            float(conditionals["B_union_D"]["expected_mae_conditional"]),
            loss_0,
        )
        rho = phi ** (float(gap) / 4.0)
        rows.append(
            {
                "river": river.name,
                "gap_length": int(gap),
                "observed_structural_skill": observed,
                "gap_length_only": gap_length_only(int(gap)),
                "acf_only": acf_only(phi, int(gap)),
                "donor_r2_only": donor_r2_only(donor_r2, int(gap)),
                "additive_heuristic": additive_heuristic(donor_r2, rho),
                "conditional_covariance": float(
                    conditionals["B_union_D"]["predicted_skill"]
                ),
                "true_donor_r2": donor_r2,
                "phi": phi,
            }
        )
    return pd.DataFrame(rows)


def incremental_fit(
    frame: pd.DataFrame,
    *,
    outcome: str = "observed_structural_skill",
    predictors: Sequence[str] = (
        "gap_length_only",
        "acf_only",
        "donor_r2_only",
        "additive_heuristic",
        "conditional_covariance",
    ),
) -> pd.DataFrame:
    """Nested least-squares \(R^2\) after successively richer predictors."""

    y = pd.to_numeric(frame[outcome], errors="coerce").to_numpy(dtype=float)
    rows = []
    columns: list[str] = []
    previous = float("nan")
    for name in predictors:
        columns.append(str(name))
        design = np.column_stack(
            [np.ones(len(frame)), frame[columns].to_numpy(dtype=float)]
        )
        valid = np.isfinite(y) & np.isfinite(design).all(axis=1)
        if int(valid.sum()) <= design.shape[1]:
            r2 = float("nan")
        else:
            coef = np.linalg.lstsq(design[valid], y[valid], rcond=None)[0]
            residual = float(np.square(y[valid] - design[valid] @ coef).sum())
            total = float(np.square(y[valid] - y[valid].mean()).sum())
            r2 = float("nan") if total == 0 else 1.0 - residual / total
        rows.append(
            {
                "model": "+".join(columns),
                "added": name,
                "r2": r2,
                "delta_r2": r2 - previous if np.isfinite(previous) else r2,
            }
        )
        previous = r2
    return pd.DataFrame(rows)


def residual_after_simple_baselines(frame: pd.DataFrame) -> dict[str, float]:
    """Does the operator explain residual skill after gap/ACF/donor predictors?"""

    y = frame["observed_structural_skill"].to_numpy(dtype=float)
    simple = frame[["gap_length_only", "acf_only", "donor_r2_only"]].to_numpy(
        dtype=float
    )
    design = np.column_stack([np.ones(len(frame)), simple])
    coef = np.linalg.lstsq(design, y, rcond=None)[0]
    residual = y - design @ coef
    operator = frame["conditional_covariance"].to_numpy(dtype=float)
    if float(np.var(residual)) == 0 or float(np.var(operator)) == 0:
        return {"residual_correlation": float("nan"), "residual_r2": float("nan")}
    correlation = float(np.corrcoef(residual, operator)[0, 1])
    full = np.column_stack([design, operator])
    coef_full = np.linalg.lstsq(full, y, rcond=None)[0]
    residual_full = y - full @ coef_full
    r2_simple = 1.0 - float(np.square(residual).sum()) / float(
        np.square(y - y.mean()).sum()
    )
    r2_full = 1.0 - float(np.square(residual_full).sum()) / float(
        np.square(y - y.mean()).sum()
    )
    return {
        "residual_correlation": correlation,
        "residual_r2": r2_full - r2_simple,
        "r2_simple": r2_simple,
        "r2_with_operator": r2_full,
    }


def run_baseline_suite(rivers: Mapping[str, SyntheticRiver]) -> dict[str, pd.DataFrame]:
    frames = [predictor_frame(river) for river in rivers.values()]
    combined = pd.concat(frames, ignore_index=True)
    return {
        "predictions": combined,
        "nested_r2": incremental_fit(combined),
        "residual_gain": pd.DataFrame([residual_after_simple_baselines(combined)]),
    }


__all__ = [
    "acf_only",
    "additive_heuristic",
    "donor_r2_only",
    "expected_gaussian_mae",
    "gap_length_only",
    "incremental_fit",
    "memory_range_index",
    "predictor_frame",
    "residual_after_simple_baselines",
    "run_baseline_suite",
]
