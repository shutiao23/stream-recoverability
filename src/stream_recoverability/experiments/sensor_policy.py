"""Sensor-placement policies and recoverability-aware decision tests (E9)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
import pandas as pd

from stream_recoverability.analysis.conditional_observability import (
    ridge_psd,
    var1_gap_conditional_risk,
)
from stream_recoverability.experiments.synthetic_river import (
    SyntheticRiver,
    advection_chain,
)

Policy = Callable[[SyntheticRiver, int, np.random.Generator], tuple[int, ...]]


def _risk_for_target(
    river: SyntheticRiver,
    target: int,
    donors: Sequence[int],
    *,
    gap_length: int,
) -> float:
    if not donors:
        hidden = float(
            np.sqrt(max(river.sigma[target, target], 0.0))
            * np.sqrt(2.0 / np.pi)
        )
        return hidden
    summary = var1_gap_conditional_risk(
        river.transition,
        river.sigma,
        target=target,
        donors=donors,
        gap_length=gap_length,
    )
    return float(summary["expected_mae_conditional"])


def evaluate_placement(
    river: SyntheticRiver,
    selected: Sequence[int],
    *,
    gap_length: int = 30,
) -> dict[str, float | str]:
    """Score retained donor stations on every unretained target station."""

    chosen = tuple(int(item) for item in selected)
    if len(set(chosen)) != len(chosen):
        raise ValueError("selected stations must be unique")
    targets = tuple(
        station for station in range(river.n_stations) if station not in chosen
    )
    risks = []
    for target in targets:
        risks.append(
            _risk_for_target(river, target, chosen, gap_length=gap_length)
        )
    risks_array = np.asarray(risks, dtype=float)
    return {
        "selected": ",".join(str(item) for item in chosen),
        "evaluated_targets": ",".join(str(item) for item in targets),
        "k": float(len(chosen)),
        "mean_mae": float(np.mean(risks_array)) if targets else 0.0,
        "worst_case_mae": float(np.max(risks_array)) if targets else 0.0,
        "n_evaluated": float(len(risks_array)),
    }


def policy_current(river: SyntheticRiver, k: int, rng: np.random.Generator) -> tuple[int, ...]:
    del k, rng
    return tuple(range(river.n_stations))


def policy_random(river: SyntheticRiver, k: int, rng: np.random.Generator) -> tuple[int, ...]:
    chosen = rng.choice(river.n_stations, size=k, replace=False)
    return tuple(sorted(int(item) for item in chosen))


def policy_spatially_even(river: SyntheticRiver, k: int, rng: np.random.Generator) -> tuple[int, ...]:
    del rng
    if k == 1:
        return (river.n_stations // 2,)
    grid = np.linspace(0, river.n_stations - 1, k)
    selected: list[int] = []
    for value in grid:
        candidate = round(value)
        if candidate not in selected:
            selected.append(candidate)
    remaining = [index for index in range(river.n_stations) if index not in selected]
    while len(selected) < k and remaining:
        selected.append(remaining.pop(0))
    return tuple(sorted(selected[:k]))


def policy_distance(river: SyntheticRiver, k: int, rng: np.random.Generator) -> tuple[int, ...]:
    """Greedy farthest-point placement along the chain index."""

    del rng
    selected = [0]
    remaining = set(range(1, river.n_stations))
    while len(selected) < k and remaining:
        def score(candidate: int) -> float:
            return min(abs(candidate - item) for item in selected)

        best = max(remaining, key=score)
        selected.append(best)
        remaining.remove(best)
    return tuple(sorted(selected))


def policy_degree(river: SyntheticRiver, k: int, rng: np.random.Generator) -> tuple[int, ...]:
    """Highest-degree nodes of a |corr| ≥ 0.5 graph built from Σ."""

    del rng
    variance = np.clip(np.diag(river.sigma), 1e-12, None)
    corr = river.sigma / np.sqrt(np.outer(variance, variance))
    graph = np.abs(corr) >= 0.5
    np.fill_diagonal(graph, False)
    degree = graph.sum(axis=1)
    order = np.argsort(-degree, kind="mergesort")
    return tuple(sorted(int(item) for item in order[:k]))


def rank_revealing_qr_indices(matrix: np.ndarray, k: int) -> tuple[int, ...]:
    """Column-pivoted QR (Businger–Golub) used by Oh & Bartos-style placement."""

    cols = np.asarray(matrix, dtype=float).copy()
    if cols.ndim != 2:
        raise ValueError("matrix must be 2-d")
    remaining = list(range(cols.shape[1]))
    selected: list[int] = []
    for _ in range(min(int(k), cols.shape[1])):
        norms = [float(np.linalg.norm(cols[:, index])) for index in remaining]
        best = remaining[int(np.argmax(norms))]
        selected.append(best)
        remaining.remove(best)
        vector = cols[:, best]
        norm = float(np.linalg.norm(vector))
        if norm < 1e-12:
            continue
        axis = vector / norm
        for index in remaining:
            cols[:, index] = cols[:, index] - axis * float(axis @ cols[:, index])
    return tuple(sorted(selected))


def policy_oh_bartos(
    river: SyntheticRiver, k: int, rng: np.random.Generator
) -> tuple[int, ...]:
    """Rank-revealing QR pivots on the stationary covariance (Oh & Bartos 2025)."""

    del rng
    return rank_revealing_qr_indices(river.sigma, k)


def policy_correlation(river: SyntheticRiver, k: int, rng: np.random.Generator) -> tuple[int, ...]:
    """Greedy: add the station least explained by those already chosen."""

    del rng
    variance = np.diag(river.sigma)
    selected = [int(np.argmax(variance))]
    remaining = [index for index in range(river.n_stations) if index != selected[0]]
    while len(selected) < k and remaining:
        scores = []
        for candidate in remaining:
            donors = selected
            sigma_dd = river.sigma[np.ix_(donors, donors)]
            sigma_td = river.sigma[candidate, donors]
            try:
                explained = float(sigma_td @ np.linalg.solve(sigma_dd, sigma_td))
            except np.linalg.LinAlgError:
                explained = float(sigma_td @ np.linalg.pinv(sigma_dd) @ sigma_td)
            residual = max(float(river.sigma[candidate, candidate] - explained), 0.0)
            scores.append((residual, candidate))
        winner = max(scores)[1]
        selected.append(winner)
        remaining.remove(winner)
    return tuple(sorted(selected))


def observability_gramian(
    transition: np.ndarray,
    selected: Sequence[int],
    horizon: int = 40,
) -> np.ndarray:
    """Finite-horizon observability Gramian for selected observation rows."""

    matrix = np.asarray(transition, dtype=float)
    n = matrix.shape[0]
    observation = np.zeros((len(selected), n))
    for row, station in enumerate(selected):
        observation[row, int(station)] = 1.0
    gramian = np.zeros((n, n))
    power = np.eye(n)
    for _ in range(horizon):
        observed = observation @ power
        gramian = gramian + observed.T @ observed
        power = matrix @ power
    return ridge_psd(gramian)


def policy_gramian(river: SyntheticRiver, k: int, rng: np.random.Generator) -> tuple[int, ...]:
    del rng
    selected: list[int] = []
    remaining = list(range(river.n_stations))
    while len(selected) < k and remaining:
        best_score = -np.inf
        best = remaining[0]
        for candidate in remaining:
            trial = selected + [candidate]
            score = float(np.linalg.slogdet(observability_gramian(river.transition, trial))[1])
            if score > best_score:
                best_score = score
                best = candidate
        selected.append(best)
        remaining.remove(best)
    return tuple(sorted(selected))


def policy_proposed(
    river: SyntheticRiver,
    k: int,
    rng: np.random.Generator,
    *,
    gap_length: int = 30,
) -> tuple[int, ...]:
    """Greedy: minimize worst-case predicted reconstruction risk."""

    del rng
    selected: list[int] = []
    remaining = list(range(river.n_stations))
    while len(selected) < k and remaining:
        best_score = np.inf
        best = remaining[0]
        for candidate in remaining:
            trial = selected + [candidate]
            score = evaluate_placement(river, trial, gap_length=gap_length)["worst_case_mae"]
            if score < best_score:
                best_score = score
                best = candidate
        selected.append(best)
        remaining.remove(best)
    return tuple(sorted(selected))


def policy_oracle(
    river: SyntheticRiver,
    k: int,
    rng: np.random.Generator,
    *,
    gap_length: int = 30,
) -> tuple[int, ...]:
    r"""Exact combinatorial search for small \(k\) on a short chain."""

    del rng
    n = river.n_stations
    if k >= n:
        return tuple(range(n))
    best_set = tuple(range(k))
    best_score = np.inf
    stack = [(0, [])]
    while stack:
        start, chosen = stack.pop()
        if len(chosen) == k:
            score = evaluate_placement(river, chosen, gap_length=gap_length)["worst_case_mae"]
            if score < best_score:
                best_score = score
                best_set = tuple(sorted(chosen))
            continue
        need = k - len(chosen)
        for index in range(start, n - need + 1):
            stack.append((index + 1, chosen + [index]))
    return best_set


POLICIES: dict[str, Policy] = {
    "current_network": policy_current,
    "random": policy_random,
    "spatially_even": policy_spatially_even,
    "degree": policy_degree,
    "distance": policy_distance,
    "correlation_redundancy": policy_correlation,
    "observability_gramian": policy_gramian,
    "oh_bartos_2025_rank_revealing_qr": policy_oh_bartos,
    "proposed_recoverability": policy_proposed,
    "oracle": policy_oracle,
}


def budget_curve(
    river: SyntheticRiver | None = None,
    *,
    budgets: Sequence[int] = (2, 3, 4),
    gap_length: int = 30,
    random_repeats: int = 8,
    seed: int = 0,
) -> pd.DataFrame:
    graph = advection_chain() if river is None else river
    rng = np.random.default_rng(seed)
    rows = []
    for k in budgets:
        if k < 1 or k > graph.n_stations:
            continue
        for name, policy in POLICIES.items():
            if name == "random":
                metrics = [
                    evaluate_placement(
                        graph,
                        policy(graph, k, np.random.default_rng(int(rng.integers(1e9)))),
                        gap_length=gap_length,
                    )
                    for _ in range(random_repeats)
                ]
                row = {
                    "policy": name,
                    "k": k,
                    "mean_mae": float(np.mean([item["mean_mae"] for item in metrics])),
                    "worst_case_mae": float(
                        np.mean([item["worst_case_mae"] for item in metrics])
                    ),
                    "selected": "random_ensemble",
                }
            else:
                if name == "proposed_recoverability":
                    selected = policy_proposed(
                        graph, k, rng, gap_length=gap_length
                    )
                elif name == "oracle":
                    selected = policy_oracle(graph, k, rng, gap_length=gap_length)
                else:
                    selected = policy(graph, k, rng)
                row = evaluate_placement(graph, selected, gap_length=gap_length)
                row["policy"] = name
                row["k"] = k
            rows.append(row)
    return pd.DataFrame(rows)


def policy_success(
    curve: pd.DataFrame,
    *,
    reduction_min: float = 0.15,
) -> pd.DataFrame:
    """Compare proposed placement with the strongest non-oracle baseline."""

    rows = []
    for k, group in curve.groupby("k"):
        proposed = group.loc[group["policy"].eq("proposed_recoverability")]
        oracle = group.loc[group["policy"].eq("oracle")]
        baselines = group.loc[
            ~group["policy"].isin(["proposed_recoverability", "oracle", "current_network"])
        ]
        if proposed.empty or baselines.empty:
            continue
        proposed_worst = float(proposed["worst_case_mae"].iloc[0])
        best_baseline = baselines.loc[baselines["worst_case_mae"].idxmin()]
        reduction = 1.0 - proposed_worst / float(best_baseline["worst_case_mae"])
        rows.append(
            {
                "k": int(k),
                "proposed_worst_case_mae": proposed_worst,
                "best_non_oracle_policy": str(best_baseline["policy"]),
                "best_non_oracle_worst_case_mae": float(best_baseline["worst_case_mae"]),
                "worst_case_reduction": reduction,
                "meets_provisional_15pct": reduction >= reduction_min,
                "oracle_worst_case_mae": (
                    float(oracle["worst_case_mae"].iloc[0]) if not oracle.empty else np.nan
                ),
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "POLICIES",
    "budget_curve",
    "evaluate_placement",
    "observability_gramian",
    "policy_degree",
    "policy_oh_bartos",
    "policy_success",
    "rank_revealing_qr_indices",
]
