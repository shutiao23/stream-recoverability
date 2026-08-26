"""Numeric isolation of additive-heuristic bias terms ε_⊥ and ε_{d/4}.

The legacy formula
``R2_avail = R2_donor + (1 - R2_donor) * rho(d/4)^2``
is a special case of the Schur operator under donor–boundary orthogonality
and an exponential ACF.  The signed split
``old - new = ε_⊥ + ε_{d/4}`` attributes the Jensen / ``d/4`` substitution
to ``ε_{d/4}`` (from ``jensen_acf_gap``) and the remainder — orthogonality
violation plus any leftover two-sided vs nearest-boundary mismatch — to
``ε_⊥``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from stream_recoverability.analysis.conditional_observability import (
    DEFAULT_RIDGE,
    StationTime,
    conditional_summaries,
    gap_nodes,
    information_set_conditionals,
    joint_covariance,
    recoverability_r,
    ridge_psd,
    schur_complement,
)
from stream_recoverability.analysis.heuristic_degeneration import (
    forced_donor_dominated,
    jensen_acf_gap,
    memory_component,
)

PHASE1_RELATIVE_ERROR_MAX = 0.05


def heuristic_explained_variance(donor_r2: float, rho_d_over_4: float) -> float:
    """Legacy additive explained variance \(R^2_{\mathrm{donor}}+(1-R^2_{\mathrm{donor}})\rho(d/4)^2\)."""

    donor = float(donor_r2)
    if not 0.0 <= donor <= 1.0:
        raise ValueError("donor_r2 must lie in [0, 1]")
    return float(donor + memory_component(donor, rho_d_over_4))


def operator_explained_variance(
    sigma_gg: np.ndarray,
    sigma_cond: np.ndarray,
) -> float:
    """Operator explained variance \(1-\overline{\mathrm{diag}}\,\Sigma_{G\mid O}/\overline{\mathrm{diag}}\,\Sigma_{G}\)."""

    return float(
        conditional_summaries(sigma_gg, sigma_cond)["operator_explained_variance"]
    )


def contemporaneous_donor_r2(
    sigma: np.ndarray,
    target: int,
    donors: Sequence[int],
) -> float:
    """Population \(R^2\) of the target on contemporaneous donors."""

    matrix = np.asarray(sigma, dtype=float)
    target_var = float(matrix[target, target])
    if target_var <= 0:
        return float("nan")
    donor_index = [int(item) for item in donors]
    if not donor_index:
        return 0.0
    sigma_dd = matrix[np.ix_(donor_index, donor_index)]
    sigma_td = matrix[target, donor_index]
    try:
        explained = float(sigma_td @ np.linalg.solve(sigma_dd, sigma_td))
    except np.linalg.LinAlgError:
        explained = float(sigma_td @ np.linalg.pinv(sigma_dd) @ sigma_td)
    return float(np.clip(explained / target_var, 0.0, 1.0))


def epsilon_d_over_4(phi: float, gap_length: int, donor_r2: float) -> float:
    """Jensen / \(d/4\) bias in explained-variance units.

    \(\varepsilon_{d/4}=(1-R^2_{\mathrm{donor}})(\rho(d/4)^2-E[\rho^2(L)])\).
    """

    gap = jensen_acf_gap(float(phi), int(gap_length))
    return float((1.0 - float(donor_r2)) * (-gap["heuristic_gap"]))


def _select(
    joint: np.ndarray,
    nodes: Sequence[StationTime],
    rows: Sequence[StationTime],
    cols: Sequence[StationTime],
) -> np.ndarray:
    index = {node: position for position, node in enumerate(nodes)}
    return joint[
        np.ix_(
            [index[node] for node in rows],
            [index[node] for node in cols],
        )
    ]


def true_conditional_from_precision(
    sigma_gg: np.ndarray,
    sigma_go: np.ndarray,
    sigma_oo: np.ndarray,
    *,
    ridge: float = DEFAULT_RIDGE,
) -> np.ndarray:
    """True Gaussian conditional covariance via the joint precision block.

    For a joint covariance \(\Sigma\), \(\mathrm{Var}(G\mid O)=(\Precision_{GG})^{-1}\).
    This is algebraically the Schur complement; the two formulas are compared
    as an independent implementation of the same Gaussian identity.
    """

    hidden = np.asarray(sigma_gg, dtype=float)
    observed = np.asarray(sigma_oo, dtype=float)
    cross = np.asarray(sigma_go, dtype=float)
    n_hidden = hidden.shape[0]
    if observed.size == 0:
        return ridge_psd(hidden, ridge)
    joint = np.block([[hidden, cross], [cross.T, observed]])
    precision = np.linalg.inv(ridge_psd(joint, ridge))
    return ridge_psd(np.linalg.inv(precision[:n_hidden, :n_hidden]), ridge)


def operator_vs_true_conditional_relative_error(
    transition: np.ndarray,
    sigma: np.ndarray,
    *,
    target: int,
    donors: Sequence[int],
    gap_length: int,
    include_right_boundary: bool = True,
    ridge: float = DEFAULT_RIDGE,
) -> dict[str, float]:
    """Relative error of the Schur operator versus the precision-block conditional."""

    parts = gap_nodes(
        target=target,
        donors=donors,
        gap_length=gap_length,
        include_right_boundary=include_right_boundary,
    )
    universe = parts["G"] + parts["B_union_D"]
    joint = joint_covariance(transition, sigma, universe)
    hidden = _select(joint, universe, parts["G"], parts["G"])
    if not parts["B_union_D"]:
        operator = hidden.copy()
        truth = hidden.copy()
    else:
        cross = _select(joint, universe, parts["G"], parts["B_union_D"])
        observed = _select(joint, universe, parts["B_union_D"], parts["B_union_D"])
        operator = schur_complement(hidden, cross, observed, ridge=ridge)
        truth = true_conditional_from_precision(hidden, cross, observed, ridge=ridge)
    theory_var = float(np.mean(np.clip(np.diag(truth), 0.0, None)))
    operator_var = float(np.mean(np.clip(np.diag(operator), 0.0, None)))
    frobenius = float(np.linalg.norm(operator - truth, ord="fro"))
    frobenius_den = float(np.linalg.norm(truth, ord="fro"))
    return {
        "operator_mean_diag": operator_var,
        "true_mean_diag": theory_var,
        "relative_error_mean_diag": (
            float("nan")
            if theory_var <= 0
            else abs(operator_var - theory_var) / theory_var
        ),
        "relative_error_frobenius": (
            float("nan") if frobenius_den <= 0 else frobenius / frobenius_den
        ),
        "phase1_gate_max": PHASE1_RELATIVE_ERROR_MAX,
        "phase1_gate_pass": bool(
            np.isfinite(theory_var)
            and theory_var > 0
            and abs(operator_var - theory_var) / theory_var
            < PHASE1_RELATIVE_ERROR_MAX
        ),
    }


def bias_terms(
    *,
    donor_r2: float,
    phi: float,
    gap_length: int,
    operator_explained: float,
    river: str = "",
    information_set: str = "B_union_D",
    relative_error: float | None = None,
) -> dict[str, float | bool | str]:
    """Assemble old heuristic, operator, \(\varepsilon_{d/4}\), and \(\varepsilon_\perp\)."""

    donor = float(donor_r2)
    gap = jensen_acf_gap(float(phi), int(gap_length))
    rho = float(np.sqrt(gap["rho_squared_at_d_over_4"]))
    old = heuristic_explained_variance(donor, rho)
    new = float(operator_explained)
    eps_d4 = float((1.0 - donor) * (-gap["heuristic_gap"]))
    old_minus_new = old - new
    return {
        "river": river,
        "information_set": information_set,
        "gap_length": float(gap_length),
        "R2_donor": donor,
        "phi": float(phi),
        "rho_d_over_4": rho,
        "old_heuristic_explained_variance": old,
        "operator_explained_variance": new,
        "recoverability_r_from_explained": float(1.0 - np.sqrt(max(1.0 - new, 0.0))),
        "epsilon_d_over_4": eps_d4,
        "epsilon_perp": old_minus_new - eps_d4,
        "old_minus_new": old_minus_new,
        "jensen_gap": float(gap["jensen_gap"]),
        "heuristic_gap": float(gap["heuristic_gap"]),
        "E_rho_squared": float(gap["E_rho_squared"]),
        "forced_donor_dominated": forced_donor_dominated(donor),
        "operator_vs_true_rel_error": (
            float("nan") if relative_error is None else float(relative_error)
        ),
    }


def bias_terms_from_var1(
    transition: np.ndarray,
    sigma: np.ndarray,
    *,
    target: int,
    donors: Sequence[int],
    gap_length: int,
    river: str = "",
    include_right_boundary: bool = True,
) -> dict[str, float | bool | str]:
    """Bias terms on a known VAR(1) using B∪D as the operator observation set."""

    donor_r2 = contemporaneous_donor_r2(sigma, target, donors)
    phi = float(np.clip(abs(np.asarray(transition, dtype=float)[target, target]), 1e-6, 1.0 - 1e-6))
    conditionals = information_set_conditionals(
        transition,
        sigma,
        target=target,
        donors=donors,
        gap_length=gap_length,
        include_right_boundary=include_right_boundary,
    )
    both = conditionals["B_union_D"]
    error = operator_vs_true_conditional_relative_error(
        transition,
        sigma,
        target=target,
        donors=donors,
        gap_length=gap_length,
        include_right_boundary=include_right_boundary,
    )
    row = bias_terms(
        donor_r2=donor_r2,
        phi=phi,
        gap_length=gap_length,
        operator_explained=float(both["operator_explained_variance"]),
        river=river,
        information_set="B_union_D",
        relative_error=float(error["relative_error_mean_diag"]),
    )
    row["recoverability_r"] = float(both["recoverability_r"])
    row["predicted_skill"] = float(both["predicted_skill"])
    row["phase1_gate_pass"] = bool(error["phase1_gate_pass"])
    return row


def orthogonal_ar1_donor(
    *,
    phi: float = 0.90,
    donor_ar: float = 0.20,
) -> tuple[np.ndarray, np.ndarray, int, tuple[int, ...]]:
    """AR(1) target with an independent donor (orthogonality holds)."""

    from stream_recoverability.analysis.conditional_observability import (
        stationary_covariance,
    )

    transition = np.diag([float(phi), float(donor_ar)])
    noise = np.eye(2)
    return transition, stationary_covariance(transition, noise), 0, (1,)


def nonorthogonal_ar1_donor(
    *,
    phi: float = 0.90,
    corr: float = 0.85,
) -> tuple[np.ndarray, np.ndarray, int, tuple[int, ...]]:
    """Shared-shock AR(1) pair (donor–boundary orthogonality is violated)."""

    from stream_recoverability.analysis.conditional_observability import (
        stationary_covariance,
    )

    transition = float(phi) * np.eye(2)
    noise = np.array([[1.0, float(corr)], [float(corr), 1.0]])
    return transition, stationary_covariance(transition, noise), 0, (1,)


def heuristic_bias_table(
    systems: Sequence[tuple[str, np.ndarray, np.ndarray, int, Sequence[int]]] | None = None,
    gap_lengths: Sequence[int] = (14, 30, 90),
) -> pd.DataFrame:
    """Bias-term rows for named VAR(1) systems."""

    if systems is None:
        from stream_recoverability.experiments.synthetic_river import catalog

        inventory = catalog()
        systems = [
            (river.name, river.transition, river.sigma, river.target, river.donors)
            for river in inventory.values()
        ]
        orthogonal = orthogonal_ar1_donor()
        correlated = nonorthogonal_ar1_donor()
        systems = [
            ("orthogonal_ar1_donor", *orthogonal),
            ("nonorthogonal_ar1_donor", *correlated),
            *systems,
        ]
    rows = []
    for name, transition, sigma, target, donors in systems:
        for gap in gap_lengths:
            rows.append(
                bias_terms_from_var1(
                    transition,
                    sigma,
                    target=target,
                    donors=donors,
                    gap_length=int(gap),
                    river=str(name),
                )
            )
    return pd.DataFrame(rows)


def forced_label_identity_rows(
    donor_r2_grid: Sequence[float] | None = None,
    rho: float = 1.0,
) -> pd.DataFrame:
    """Show the hard label is forced once \(R^2_{\mathrm{donor}}\ge 0.5\)."""

    donors = (
        (0.49, 0.50, 0.51, 0.75, 0.90)
        if donor_r2_grid is None
        else tuple(float(item) for item in donor_r2_grid)
    )
    rows = []
    for donor in donors:
        memory = memory_component(float(donor), float(rho))
        rows.append(
            {
                "R2_donor": float(donor),
                "rho": float(rho),
                "memory_component_at_rho": memory,
                "hard_label": (
                    "donor_dominated" if donor >= memory else "memory_dominated"
                ),
                "forced_donor_dominated": forced_donor_dominated(float(donor)),
            }
        )
    return pd.DataFrame(rows)


def recoverability_from_summaries(summary: Mapping[str, float]) -> float:
    return float(summary.get("recoverability_r", float("nan")))


__all__ = [
    "PHASE1_RELATIVE_ERROR_MAX",
    "bias_terms",
    "bias_terms_from_var1",
    "contemporaneous_donor_r2",
    "epsilon_d_over_4",
    "forced_label_identity_rows",
    "heuristic_bias_table",
    "heuristic_explained_variance",
    "nonorthogonal_ar1_donor",
    "operator_explained_variance",
    "operator_vs_true_conditional_relative_error",
    "orthogonal_ar1_donor",
    "recoverability_from_summaries",
    "recoverability_r",
    "true_conditional_from_precision",
]
