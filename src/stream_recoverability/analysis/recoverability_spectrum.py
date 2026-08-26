"""Continuous recoverability spectrum and incremental information values.

Hard donor/memory labels are optional diagnostics.  They are not the primary
estimand and they are not forced when donor \(R^2\ge 0.5\).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from stream_recoverability.analysis.conditional_observability import (
    conditionals_table,
    information_set_conditionals,
)

DEFAULT_EPSILON = 1e-6


def recoverability(loss_s: float, loss_0: float) -> float:
    """Return \(1-E[L_S]/E[L_0]\)."""

    if not np.isfinite(loss_s) or not np.isfinite(loss_0) or loss_0 == 0:
        return float("nan")
    return float(1.0 - loss_s / loss_0)


@dataclass(frozen=True)
class IncrementalValue:
    v_donor: float
    v_boundary: float
    tau: float
    recoverability_none: float
    recoverability_boundary: float
    recoverability_donor: float
    recoverability_both: float
    sign: str
    epsilon: float

    def as_dict(self) -> dict[str, float | str]:
        return asdict(self)


def incremental_information(
    recoverability_boundary: float,
    recoverability_donor: float,
    recoverability_both: float,
    *,
    recoverability_none: float = 0.0,
    epsilon: float = DEFAULT_EPSILON,
) -> IncrementalValue:
    """Return \(V_D\), \(V_B\), and \(\tau=\log((V_B+\varepsilon)/(V_D+\varepsilon))\)."""

    if epsilon <= 0:
        raise ValueError("epsilon must be positive")
    v_donor = float(recoverability_both - recoverability_boundary)
    v_boundary = float(recoverability_both - recoverability_donor)
    tau = float(np.log((v_boundary + epsilon) / (v_donor + epsilon)))
    if not np.isfinite(tau):
        sign = "undefined"
    elif abs(tau) < 1e-12:
        sign = "tied"
    elif tau > 0:
        sign = "boundary_dominant"
    else:
        sign = "donor_dominant"
    return IncrementalValue(
        v_donor=v_donor,
        v_boundary=v_boundary,
        tau=tau,
        recoverability_none=float(recoverability_none),
        recoverability_boundary=float(recoverability_boundary),
        recoverability_donor=float(recoverability_donor),
        recoverability_both=float(recoverability_both),
        sign=sign,
        epsilon=float(epsilon),
    )


def spectrum_from_conditionals(
    conditionals: Mapping[str, Mapping[str, float]],
    *,
    risk_key: str = "expected_mae_conditional",
    epsilon: float = DEFAULT_EPSILON,
) -> IncrementalValue:
    """Build \(\tau\) from operator summaries keyed by information set."""

    required = ("none", "B", "D", "B_union_D")
    missing = [name for name in required if name not in conditionals]
    if missing:
        raise KeyError(f"conditionals missing {missing}")
    loss_0 = float(conditionals["none"][risk_key])
    r_none = recoverability(loss_0, loss_0)
    r_b = recoverability(float(conditionals["B"][risk_key]), loss_0)
    r_d = recoverability(float(conditionals["D"][risk_key]), loss_0)
    r_bd = recoverability(float(conditionals["B_union_D"][risk_key]), loss_0)
    return incremental_information(
        r_b,
        r_d,
        r_bd,
        recoverability_none=r_none,
        epsilon=epsilon,
    )


def spectrum_from_var1(
    transition: np.ndarray,
    sigma: np.ndarray,
    *,
    target: int,
    donors: Sequence[int],
    gap_length: int,
    include_right_boundary: bool = True,
    epsilon: float = DEFAULT_EPSILON,
) -> IncrementalValue:
    conditionals = information_set_conditionals(
        transition,
        sigma,
        target=target,
        donors=donors,
        gap_length=gap_length,
        include_right_boundary=include_right_boundary,
    )
    return spectrum_from_conditionals(conditionals, epsilon=epsilon)


def optional_soft_label(tau: float, *, margin: float = 0.1) -> str:
    """Descriptive label that remains undefined near \(\tau=0\)."""

    if not np.isfinite(tau):
        return "undefined"
    if tau > margin:
        return "boundary_dominant"
    if tau < -margin:
        return "donor_dominant"
    return "indeterminate"


def year_block_bootstrap_tau(
    series: np.ndarray,
    years: Sequence[int],
    *,
    target: int,
    donors: Sequence[int],
    gap_length: int,
    n_boot: int = 200,
    seed: int = 0,
    include_right_boundary: bool = True,
    epsilon: float = DEFAULT_EPSILON,
) -> dict[str, float]:
    """Year-block bootstrap for \(\tau\) estimated from fitting series."""

    from stream_recoverability.analysis.conditional_observability import (
        empirical_information_set_conditionals,
    )

    values = np.asarray(series, dtype=float)
    year_index = np.asarray(years)
    if len(year_index) != len(values):
        raise ValueError("years must align with series rows")
    unique_years = np.array(sorted(pd.unique(year_index)))
    if unique_years.size < 2:
        return {
            "tau_hat": float("nan"),
            "tau_ci_lower": float("nan"),
            "tau_ci_upper": float("nan"),
            "n_years": float(unique_years.size),
            "n_boot": float(n_boot),
            "inference_status": "withheld_insufficient_independent_clusters",
        }
    rng = np.random.default_rng(seed)
    point = spectrum_from_conditionals(
        empirical_information_set_conditionals(
            values,
            target=target,
            donors=donors,
            gap_length=gap_length,
            include_right_boundary=include_right_boundary,
        ),
        epsilon=epsilon,
    )
    if unique_years.size < 5:
        return {
            "tau_hat": point.tau,
            "tau_ci_lower": float("nan"),
            "tau_ci_upper": float("nan"),
            "n_years": float(unique_years.size),
            "n_boot": float(n_boot),
            "inference_status": "withheld_insufficient_independent_clusters",
        }
    draws: list[float] = []
    for _ in range(n_boot):
        sampled = rng.choice(unique_years, size=unique_years.size, replace=True)
        rows = np.concatenate([np.flatnonzero(year_index == year) for year in sampled])
        try:
            estimate = spectrum_from_conditionals(
                empirical_information_set_conditionals(
                    values[rows],
                    target=target,
                    donors=donors,
                    gap_length=gap_length,
                    include_right_boundary=include_right_boundary,
                ),
                epsilon=epsilon,
            )
        except (np.linalg.LinAlgError, ValueError):
            continue
        if np.isfinite(estimate.tau):
            draws.append(estimate.tau)
    if len(draws) < 20:
        lower = upper = float("nan")
        status = "withheld_unstable_bootstrap"
    else:
        lower, upper = np.quantile(draws, [0.025, 0.975])
        status = "tested"
    return {
        "tau_hat": point.tau,
        "tau_ci_lower": float(lower),
        "tau_ci_upper": float(upper),
        "n_years": float(unique_years.size),
        "n_boot": float(n_boot),
        "inference_status": status,
    }


def spectrum_frame(
    transition: np.ndarray,
    sigma: np.ndarray,
    *,
    target: int,
    donors: Sequence[int],
    gap_lengths: Sequence[int],
    include_right_boundary: bool = True,
    epsilon: float = DEFAULT_EPSILON,
) -> pd.DataFrame:
    rows = []
    for gap in gap_lengths:
        conditionals = information_set_conditionals(
            transition,
            sigma,
            target=target,
            donors=donors,
            gap_length=int(gap),
            include_right_boundary=include_right_boundary,
        )
        value = spectrum_from_conditionals(conditionals, epsilon=epsilon)
        row = value.as_dict()
        row["gap_length"] = int(gap)
        row["target"] = int(target)
        row["donors"] = ",".join(str(item) for item in donors)
        row["task"] = (
            "offline_archival" if include_right_boundary else "online_causal"
        )
        row["soft_label"] = optional_soft_label(value.tau)
        table = conditionals_table(conditionals)
        for name in ("none", "B", "D", "B_union_D"):
            match = table.loc[table["information_set"].eq(name)].iloc[0]
            row[f"predicted_skill_{name}"] = match["predicted_skill"]
            row[f"predicted_risk_{name}"] = match["expected_mae_conditional"]
        rows.append(row)
    return pd.DataFrame(rows)


__all__ = [
    "DEFAULT_EPSILON",
    "IncrementalValue",
    "incremental_information",
    "optional_soft_label",
    "recoverability",
    "spectrum_frame",
    "spectrum_from_conditionals",
    "spectrum_from_var1",
    "year_block_bootstrap_tau",
]
