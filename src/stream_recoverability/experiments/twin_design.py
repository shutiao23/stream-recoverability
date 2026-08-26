"""Phase 2 twin design: interior dam-like node vs ordinary endpoint.

This is a known-dynamics design exercise for the next paper's Fig. 2.
It is not formal evidence and it is not confirmation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from stream_recoverability.analysis.conditional_observability import (
    empirical_information_set_conditionals,
    information_set_conditionals,
    var1_cross_covariance,
)
from stream_recoverability.analysis.heuristic_degeneration import (
    in_sample_r2,
    memory_component,
)
from stream_recoverability.experiments.synthetic_identifiability import (
    contemporaneous_donor_r2,
)
from stream_recoverability.experiments.synthetic_river import (
    SyntheticRiver,
    simulate_var1,
    twin_a_interior_dam_chain,
    twin_a_interior_dam_confluence,
    twin_b_ordinary_endpoint_chain,
    twin_b_ordinary_endpoint_confluence,
    twin_c_endpoint_dam_chain,
    twin_d_ordinary_interior_chain,
)

DEFAULT_GAP = 90
OPERATOR_AUC_MIN = 0.85
UNIVARIATE_AUC_MAX = 0.65
ACF_LAG = 30

UNIVARIATE_PREDICTORS = (
    "donor_r2_risk",
    "acf30",
    "memory_component",
    "hard_memory_label",
    "mean_donor_hops",
)


def directed_partition(
    n_stations: int,
    edges: Sequence[tuple[int, int]],
    node: int,
) -> tuple[set[int], set[int]]:
    """Return ancestor and descendant sets on a directed river graph."""

    downstream: dict[int, list[int]] = {index: [] for index in range(n_stations)}
    upstream: dict[int, list[int]] = {index: [] for index in range(n_stations)}
    for left, right in edges:
        downstream[int(left)].append(int(right))
        upstream[int(right)].append(int(left))

    def _walk(start: int, adjacency: Mapping[int, Sequence[int]]) -> set[int]:
        seen: set[int] = set()
        queue = [int(start)]
        for current in queue:
            for nxt in adjacency[current]:
                if nxt not in seen:
                    seen.add(int(nxt))
                    queue.append(int(nxt))
        return seen

    return _walk(node, upstream), _walk(node, downstream)


def hop_distances(
    n_stations: int,
    edges: Sequence[tuple[int, int]],
    source: int,
) -> dict[int, int]:
    adjacency: dict[int, list[int]] = {index: [] for index in range(n_stations)}
    for left, right in edges:
        adjacency[int(left)].append(int(right))
        adjacency[int(right)].append(int(left))
    dist = {int(source): 0}
    queue = [int(source)]
    for current in queue:
        for nxt in adjacency[current]:
            if nxt not in dist:
                dist[int(nxt)] = dist[current] + 1
                queue.append(int(nxt))
    return dist


def graph_neighbors(river: SyntheticRiver, node: int) -> tuple[int, ...]:
    adjacent: list[int] = []
    for left, right in river.edges:
        if left == node:
            adjacent.append(int(right))
        elif right == node:
            adjacent.append(int(left))
    return tuple(sorted(set(adjacent)))


def topology_label(river: SyntheticRiver) -> str:
    if "confluence" in river.name:
        return "confluence"
    if "chain" in river.name:
        return "chain"
    return "other"


def twin_family(river: SyntheticRiver) -> str:
    if river.name.startswith("twin_c_"):
        return "C"
    if river.name.startswith("twin_d_"):
        return "D"
    if river.dam_like_index is not None:
        return "A"
    return "B"


def twin_cell(river: SyntheticRiver) -> str:
    family = twin_family(river)
    return {
        "A": "dam_times_interior",
        "B": "ordinary_times_endpoint",
        "C": "dam_times_endpoint",
        "D": "ordinary_times_interior",
    }[family]


def binary_auc(labels: Sequence[object], scores: Sequence[object]) -> float:
    """ROC AUC; undefined when a class is missing or all scores are non-finite."""

    y = np.asarray(labels, dtype=int)
    s = np.asarray(scores, dtype=float)
    valid = np.isfinite(s)
    y = y[valid]
    s = s[valid]
    if y.size < 2 or int(y.min()) == int(y.max()):
        return float("nan")
    from sklearn.metrics import roc_auc_score

    return float(roc_auc_score(y, s))


def _lag_acf(transition: np.ndarray, sigma: np.ndarray, station: int, lag: int) -> float:
    variance = float(sigma[station, station])
    if variance <= 0:
        return float("nan")
    gamma = var1_cross_covariance(transition, sigma, int(lag))
    return float(gamma[station, station] / variance)


def _sample_acf(series: np.ndarray, station: int, lag: int) -> float:
    left = series[:-lag, station]
    right = series[lag:, station]
    valid = np.isfinite(left) & np.isfinite(right)
    if int(valid.sum()) < 3:
        return float("nan")
    return float(np.corrcoef(left[valid], right[valid])[0, 1])


def uniqueness_margin(values: Sequence[float], index: int, *, higher: bool) -> float:
    scores = np.asarray(values, dtype=float)
    others = np.delete(scores, int(index))
    others = others[np.isfinite(others)]
    focus = float(scores[int(index)])
    if not np.isfinite(focus) or others.size == 0:
        return float("nan")
    if higher:
        return float(focus - np.max(others))
    return float(np.min(others) - focus)


def score_twin_nodes(
    river: SyntheticRiver,
    *,
    gap_length: int = DEFAULT_GAP,
    series: np.ndarray | None = None,
    source: str = "exact_sigma",
) -> pd.DataFrame:
    """Score every node as if it were the recovery target."""

    n_stations = river.n_stations
    rows = []
    for target in range(n_stations):
        donors = tuple(index for index in range(n_stations) if index != target)
        if series is None:
            conditionals = information_set_conditionals(
                river.transition,
                river.sigma,
                target=target,
                donors=donors,
                gap_length=int(gap_length),
            )
            recoverability = float(conditionals["B_union_D"]["recoverability_r"])
            donor_r2 = contemporaneous_donor_r2(river, target=target, donors=donors)
            acf30 = _lag_acf(river.transition, river.sigma, target, ACF_LAG)
        else:
            conditionals = empirical_information_set_conditionals(
                series,
                target=target,
                donors=donors,
                gap_length=int(gap_length),
            )
            recoverability = float(conditionals["B_union_D"]["recoverability_r"])
            donor_r2 = in_sample_r2(series[:, target], [series[:, item] for item in donors])
            acf30 = _sample_acf(series, target, ACF_LAG)
        phi = float(river.transition[target, target])
        rho_d4 = float(abs(phi) ** (float(gap_length) / 4.0))
        memory = memory_component(float(np.clip(donor_r2, 0.0, 1.0)), rho_d4)
        hops = hop_distances(n_stations, river.edges, target)
        hop_values = [hops[index] for index in donors if index in hops]
        ancestors, descendants = directed_partition(n_stations, river.edges, target)
        rows.append(
            {
                "river": river.name,
                "twin": twin_family(river),
                "cell": twin_cell(river),
                "topology": topology_label(river),
                "source": source,
                "gap_length": int(gap_length),
                "node": int(target),
                "station": river.station_names[target],
                "is_dam_like": bool(
                    river.dam_like_index is not None and target == river.dam_like_index
                ),
                "is_ordinary_endpoint": bool(
                    river.ordinary_endpoint is not None
                    and target == river.ordinary_endpoint
                ),
                "is_ordinary_interior": bool(
                    getattr(river, "ordinary_interior", None) is not None
                    and target == river.ordinary_interior
                ),
                "n_donors": len(donors),
                "n_upstream_donors": len(ancestors),
                "n_downstream_donors": len(descendants),
                "one_sided_donors": bool(not ancestors or not descendants),
                "nearest_donor_hops": (
                    float(min(hop_values)) if hop_values else float("nan")
                ),
                "mean_donor_hops": (
                    float(np.mean(hop_values)) if hop_values else float("nan")
                ),
                "recoverability_r": recoverability,
                "operator_risk": 1.0 - recoverability,
                "donor_r2": float(donor_r2),
                "donor_r2_risk": 1.0 - float(donor_r2),
                "acf30": float(acf30),
                "memory_component": float(memory),
                "hard_memory_label": int(memory > donor_r2),
                "local_ar": phi,
            }
        )
    return pd.DataFrame(rows)


def multi_graph_suite() -> list[SyntheticRiver]:
    """Chain and confluence twins at a few sizes. Includes at least one tree."""

    rivers: list[SyntheticRiver] = []
    for n_stations in (5, 6, 7):
        rivers.append(twin_a_interior_dam_chain(n_stations))
        rivers.append(twin_b_ordinary_endpoint_chain(n_stations))
    for n_stations in (5, 6):
        rivers.append(twin_a_interior_dam_confluence(n_stations))
        rivers.append(twin_b_ordinary_endpoint_confluence(n_stations))
    for n_stations in (5, 6):
        rivers.append(twin_c_endpoint_dam_chain(n_stations))
        rivers.append(twin_d_ordinary_interior_chain(n_stations))
    return rivers


def _auc_row(
    frame: pd.DataFrame,
    predictor: str,
    *,
    higher_means: str,
) -> dict[str, float | str | bool]:
    auc = binary_auc(frame["is_dam_like"], frame[predictor])
    role = "operator" if predictor == "operator_risk" else "univariate"
    return {
        "predictor": predictor,
        "auc": auc,
        "n_positive": int(frame["is_dam_like"].sum()),
        "n_negative": int((~frame["is_dam_like"]).sum()),
        "higher_means": higher_means,
        "gate_role": role,
        "univariate_exceeds_max": bool(
            role == "univariate" and np.isfinite(auc) and auc > UNIVARIATE_AUC_MAX
        ),
    }


def hard_negative_frame(node_scores: pd.DataFrame) -> pd.DataFrame:
    """Interior dam-like positives versus ordinary-endpoint negatives only."""

    positives = node_scores.loc[
        node_scores["is_dam_like"] & node_scores["twin"].eq("A")
    ]
    negatives = node_scores.loc[
        node_scores["is_ordinary_endpoint"] & node_scores["twin"].eq("B")
    ]
    return pd.concat([positives, negatives], ignore_index=True)


def summarize_aucs(node_scores: pd.DataFrame) -> pd.DataFrame:
    rows = [
        _auc_row(
            node_scores,
            "operator_risk",
            higher_means="higher residual risk (1-R) is more dam-like",
        ),
        _auc_row(
            node_scores,
            "donor_r2_risk",
            higher_means="lower contemporaneous donor R2 looks more memory-like",
        ),
        _auc_row(
            node_scores,
            "acf30",
            higher_means="higher lag-30 ACF looks more memory-like",
        ),
        _auc_row(
            node_scores,
            "memory_component",
            higher_means="higher legacy (1-D)*rho(d/4)^2 looks more memory-like",
        ),
        _auc_row(
            node_scores,
            "hard_memory_label",
            higher_means="legacy hard memory label (memory_component > donor R2)",
        ),
        _auc_row(
            node_scores,
            "mean_donor_hops",
            higher_means="larger mean hop distance is more endpoint-like",
        ),
    ]
    return pd.DataFrame(rows)


def gate_from_aucs(auc_table: pd.DataFrame) -> dict[str, float | str | bool]:
    operator = auc_table.loc[auc_table["predictor"].eq("operator_risk")].iloc[0]
    operator_auc = float(operator["auc"])
    univariate = auc_table.loc[auc_table["gate_role"].eq("univariate")]
    defined = univariate.loc[pd.to_numeric(univariate["auc"], errors="coerce").notna()]
    univariate_max = (
        float(defined["auc"].max()) if not defined.empty else float("nan")
    )
    univariate_ok = bool(
        not defined.empty
        and (defined["auc"].to_numpy(dtype=float) <= UNIVARIATE_AUC_MAX).all()
    )
    operator_ok = bool(np.isfinite(operator_auc) and operator_auc >= OPERATOR_AUC_MIN)
    if not operator_ok:
        status = "inseparable"
    elif univariate_ok:
        status = "operator_unique"
    else:
        status = "operator_separable_univariates_also_separable"
    return {
        "operator_auc": operator_auc,
        "univariate_max_auc": univariate_max,
        "operator_auc_min": OPERATOR_AUC_MIN,
        "univariate_auc_max": UNIVARIATE_AUC_MAX,
        "operator_meets_floor": operator_ok,
        "univariate_all_at_or_below_max": univariate_ok,
        "gate_pass": bool(operator_ok and univariate_ok),
        "identifiability_status": status,
    }


def run_twin_design(
    *,
    gap_length: int = DEFAULT_GAP,
    include_finite_sample: bool = False,
    n_time: int = 365 * 8,
    seeds: Sequence[int] = (0, 1, 2),
) -> dict[str, pd.DataFrame | dict]:
    """Score the multi-graph suite. Default predictors use known Sigma."""

    rivers = multi_graph_suite()
    frames = [
        score_twin_nodes(river, gap_length=gap_length, source="exact_sigma")
        for river in rivers
    ]
    if include_finite_sample:
        primaries = [
            twin_a_interior_dam_chain(),
            twin_b_ordinary_endpoint_chain(),
            twin_a_interior_dam_confluence(),
        ]
        for seed in seeds:
            for river in primaries:
                series = simulate_var1(river, n_time, seed=int(seed))
                frames.append(
                    score_twin_nodes(
                        river,
                        gap_length=gap_length,
                        series=series,
                        source=f"simulated_seed_{int(seed)}",
                    )
                )
    nodes = pd.concat(frames, ignore_index=True)
    exact = nodes.loc[nodes["source"].eq("exact_sigma")].copy()
    aucs = summarize_aucs(exact)
    hard = summarize_aucs(hard_negative_frame(exact))
    hard["contrast"] = "interior_dam_vs_ordinary_endpoint"
    aucs["contrast"] = "all_nodes_dam_like_vs_not"
    gate = gate_from_aucs(aucs)
    hard_gate = gate_from_aucs(hard)
    gate["hard_negative_operator_auc"] = hard_gate["operator_auc"]
    gate["hard_negative_univariate_max_auc"] = hard_gate["univariate_max_auc"]
    gate["hard_negative_gate_pass"] = hard_gate["gate_pass"]
    return {
        "node_scores": nodes,
        "aucs": pd.concat([aucs, hard], ignore_index=True),
        "gate": gate,
        "n_graphs": int(exact["river"].nunique()),
        "topologies": sorted(exact["topology"].unique()),
        "cells": sorted(exact["cell"].unique()),
    }


__all__ = [
    "ACF_LAG",
    "DEFAULT_GAP",
    "OPERATOR_AUC_MIN",
    "UNIVARIATE_AUC_MAX",
    "binary_auc",
    "directed_partition",
    "gate_from_aucs",
    "graph_neighbors",
    "hard_negative_frame",
    "hop_distances",
    "multi_graph_suite",
    "run_twin_design",
    "score_twin_nodes",
    "summarize_aucs",
    "uniqueness_margin",
]
