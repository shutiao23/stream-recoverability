"""Real-data monitoring-placement replay for open development networks.

Policies see fitting-period correlation only.  They are evaluated by removing
unretained stations and replaying observed evaluation-period gaps with a
ridge-stabilized single-donor reconstruction.  The oracle sees realized replay
loss only to define regret.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations

import numpy as np
import pandas as pd
from scipy.linalg import qr

from stream_recoverability.experiments.recovery_roster import (
    score_model_roster_on_placements,
)
from stream_recoverability.experiments.development_recovery import year_split


def training_correlation(panel: pd.DataFrame) -> pd.DataFrame:
    """Calendar-day-anomaly correlation using fitting years only."""

    daily = panel.copy().sort_index().asfreq("D")
    daily.columns = daily.columns.astype(str)
    train, _, _ = year_split(daily.index)
    fitting = daily.loc[train]
    climatology = fitting.groupby(fitting.index.dayofyear).transform("mean")
    return (fitting - climatology).corr().fillna(0.0)


def pairwise_replay_losses(
    network_id: str,
    panel: pd.DataFrame,
    placements: pd.DataFrame,
    *,
    gap_length: int = 90,
) -> pd.DataFrame:
    """Score each target with each possible retained station as its sole donor."""

    daily = panel.copy()
    daily.columns = daily.columns.astype(str)
    selected = placements.loc[
        placements["network_id"].astype(str).eq(str(network_id))
        & placements["information_condition"].eq("B_union_D")
        & placements["gap_length"].eq(gap_length)
    ].copy()
    rows: list[pd.DataFrame] = []
    stations = tuple(daily.columns)
    for target in stations:
        target_rows = selected.loc[selected["station_id"].astype(str).str.lstrip("0").eq(target.lstrip("0"))]
        if target_rows.empty:
            continue
        for donor in stations:
            if donor == target:
                continue
            one = target_rows.copy()
            one["donor_station_ids"] = donor
            try:
                scored = score_model_roster_on_placements(str(network_id), daily, one)
            except ValueError:
                # This directed station pair lacks enough complete fitting
                # rows. The common-roster step below will remove it rather
                # than fabricate a replay loss.
                continue
            scored = scored.loc[scored["model_family"].eq("donor_blup_ridge")]
            if scored.empty:
                continue
            rows.append(
                pd.DataFrame(
                    {
                        "network_id": [str(network_id)],
                        "target_station": [target],
                        "donor_station": [donor],
                        "gap_length": [gap_length],
                        "realized_mae": [float(scored["mae_deg_c"].mean())],
                        "n_placements": [int(len(scored))],
                    }
                )
            )
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _score_selected(
    selected: Sequence[str],
    losses: pd.DataFrame,
    correlation: pd.DataFrame,
) -> float:
    retained = tuple(str(value) for value in selected)
    targets = [station for station in correlation.index if station not in retained]
    target_losses = []
    for target in targets:
        available = [donor for donor in retained if donor in correlation.columns]
        if not available:
            return float("inf")
        donor = max(available, key=lambda value: abs(float(correlation.loc[target, value])))
        match = losses.loc[
            losses["target_station"].eq(target)
            & losses["donor_station"].eq(donor),
            "realized_mae",
        ]
        if match.empty:
            return float("inf")
        target_losses.append(float(match.iloc[0]))
    return max(target_losses) if target_losses else 0.0


def _proxy_score(selected: Sequence[str], correlation: pd.DataFrame) -> float:
    retained = tuple(str(value) for value in selected)
    values = []
    for target in correlation.index:
        if target in retained:
            continue
        best = max(abs(float(correlation.loc[target, donor])) for donor in retained)
        values.append(float(np.sqrt(max(0.0, 1.0 - best**2))))
    return max(values) if values else 0.0


def _greedy_minimax(correlation: pd.DataFrame, k: int) -> tuple[str, ...]:
    selected: list[str] = []
    candidates = list(correlation.index)
    for _ in range(k):
        selected.append(
            min(
                (value for value in candidates if value not in selected),
                key=lambda value: _proxy_score((*selected, value), correlation),
            )
        )
    return tuple(selected)


def _greedy_mi(correlation: pd.DataFrame, k: int) -> tuple[str, ...]:
    selected: list[str] = []
    candidates = list(correlation.index)
    for _ in range(k):
        def objective(value: str) -> float:
            subset = [*selected, value]
            matrix = correlation.loc[subset, subset].to_numpy(dtype=float)
            sign, logdet = np.linalg.slogdet(matrix + np.eye(len(subset)) * 1e-6)
            return float(logdet) if sign > 0 else -np.inf

        selected.append(
            max((value for value in candidates if value not in selected), key=objective)
        )
    return tuple(selected)


def _qr_selected(correlation: pd.DataFrame, k: int) -> tuple[str, ...]:
    _, _, pivots = qr(correlation.to_numpy(dtype=float), pivoting=True, mode="economic")
    return tuple(str(correlation.columns[index]) for index in pivots[:k])


def _distance_selected(stations: Sequence[str], k: int) -> tuple[str, ...]:
    positions = np.linspace(0, len(stations) - 1, k)
    indices = []
    for position in positions:
        candidate = int(round(float(position)))
        if candidate not in indices:
            indices.append(candidate)
    for candidate in range(len(stations)):
        if len(indices) >= k:
            break
        if candidate not in indices:
            indices.append(candidate)
    return tuple(str(stations[index]) for index in indices)


def placement_replay_curve(
    losses: pd.DataFrame,
    correlation: pd.DataFrame,
    *,
    random_repeats: int = 100,
    seed: int = 0,
) -> pd.DataFrame:
    """Compare five train-only policies with the realized-outcome oracle."""

    stations = list(
        station
        for station in correlation.index.astype(str)
        if station in set(losses["target_station"])
        and station in set(losses["donor_station"])
    )
    available_pairs = set(
        zip(losses["target_station"].astype(str), losses["donor_station"].astype(str))
    )
    # A fair leave-k replay requires every retained station to be a scoreable
    # donor for every possible target. Find the largest complete directed
    # submatrix exactly; sequential deletion can discard a valid large clique.
    common: tuple[str, ...] = ()
    for size in range(len(stations), 4, -1):
        for subset in combinations(stations, size):
            if all(
                (target, donor) in available_pairs
                for target in subset
                for donor in subset
                if target != donor
            ):
                common = tuple(subset)
                break
        if common:
            break
    stations = common
    if len(stations) < 5:
        raise ValueError("fewer than five stations have a complete replay matrix")
    correlation = correlation.loc[list(stations), list(stations)]
    station_index = {station: index for index, station in enumerate(stations)}
    correlation_values = np.abs(correlation.to_numpy(dtype=float))
    loss_values = np.full((len(stations), len(stations)), np.nan, dtype=float)
    for item in losses.itertuples(index=False):
        target = station_index.get(str(item.target_station))
        donor = station_index.get(str(item.donor_station))
        if target is not None and donor is not None:
            loss_values[target, donor] = float(item.realized_mae)

    def score_selected(selected_values: Sequence[str]) -> float:
        selected_index = np.asarray(
            [station_index[str(value)] for value in selected_values], dtype=int
        )
        retained = np.zeros(len(stations), dtype=bool)
        retained[selected_index] = True
        targets = np.flatnonzero(~retained)
        if not len(targets):
            return 0.0
        target_losses = np.empty(len(targets), dtype=float)
        for position, target in enumerate(targets):
            best_position = int(
                np.argmax(correlation_values[target, selected_index])
            )
            donor = int(selected_index[best_position])
            target_losses[position] = loss_values[target, donor]
        return float(np.max(target_losses))

    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for k in range(1, len(stations)):
        oracle_selected = min(
            combinations(stations, k), key=score_selected
        )
        oracle_loss = score_selected(oracle_selected)
        policies = {
            "simple_risk_minimax": _greedy_minimax(correlation, k),
            "greedy_mutual_information": _greedy_mi(correlation, k),
            "qr_pivot": _qr_selected(correlation, k),
            "distance_even": _distance_selected(stations, k),
            "oracle": oracle_selected,
        }
        for policy, selected in policies.items():
            value = score_selected(selected)
            rows.append(
                {
                    "policy": policy,
                    "k": k,
                    "protected_fraction": k / len(stations),
                    "selected": "|".join(selected),
                    "worst_target_mae": value,
                    "oracle_mae": oracle_loss,
                    "regret": value - oracle_loss,
                    "independent_realized_outcomes": True,
                }
            )
        random_values = []
        for _ in range(random_repeats):
            selected = tuple(rng.choice(stations, size=k, replace=False))
            random_values.append(score_selected(selected))
        rows.append(
            {
                "policy": "random",
                "k": k,
                "protected_fraction": k / len(stations),
                "selected": "random_ensemble",
                "worst_target_mae": float(np.mean(random_values)),
                "oracle_mae": oracle_loss,
                "regret": float(np.mean(random_values) - oracle_loss),
                "independent_realized_outcomes": True,
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "pairwise_replay_losses",
    "placement_replay_curve",
    "training_correlation",
]
