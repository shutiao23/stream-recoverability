"""Exact Shapley allocation over recoverability information parts.

Default players are {B, D} (the four coalitions already computed by
``information_set_conditionals``).  An optional four-set interface
{B, D, M, H} is used when meteorology or hydraulics coordinates are
supplied.  Values describe allocation of a chosen value function, not
causal effects.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.analysis.conditional_observability import (
    INFORMATION_PLAYER_ORDER,
    StationTime,
    coalition_label,
    information_set_conditionals,
)

PLAYERS_BD = ("B", "D")
PLAYERS_BDMH = ("B", "D", "M", "H")
LOWER_BETTER_KEYS = frozenset(
    {
        "expected_mae_conditional",
        "predicted_conditional_risk",
        "normalized_conditional_variance",
        "trace_conditional",
        "trace_ratio",
    }
)
_EMPTY_KEYS = frozenset(
    {"none", "empty", "clim", "climatology", "emptyset", ""}
)


def normalize_coalition_key(
    key: Any,
    players: Sequence[str],
) -> frozenset[str]:
    """Parse a coalition key into a frozenset of player names."""

    allowed = {str(name) for name in players}
    if key is None:
        return frozenset()
    if isinstance(key, frozenset):
        return frozenset(str(item) for item in key)
    if isinstance(key, (set, list, tuple)):
        return frozenset(str(item) for item in key)
    text = str(key).strip()
    if text.lower() in _EMPTY_KEYS:
        return frozenset()
    if "_union_" in text:
        return frozenset(part for part in text.split("_union_") if part)
    if text in allowed:
        return frozenset({text})
    raise ValueError(f"unrecognized coalition key: {key!r}")


def shapley_information(
    values_by_coalition: Mapping[Any, float],
    players: Sequence[str],
) -> dict[str, float]:
    r"""Exact Shapley values from the standard \(2^n\) formula.

    ``values_by_coalition`` must contain every subset of ``players``.  Keys
    may be frozensets, tuples, or labels such as ``none`` / ``B_union_D``.
    """

    names = tuple(str(player) for player in players)
    if not names:
        return {}
    if len(set(names)) != len(names):
        raise ValueError("players must be unique")
    parsed = {
        normalize_coalition_key(key, names): float(value)
        for key, value in values_by_coalition.items()
    }
    missing = [
        coalition_label(combo) if combo else "none"
        for size in range(len(names) + 1)
        for combo in combinations(names, size)
        if frozenset(combo) not in parsed
    ]
    if missing:
        raise ValueError(f"shapley_information missing coalitions: {missing}")
    n_players = len(names)
    denominator = math.factorial(n_players)
    result: dict[str, float] = {}
    for player in names:
        contribution = 0.0
        others = [name for name in names if name != player]
        for size in range(n_players):
            for subset in combinations(others, size):
                coalition = frozenset(subset)
                weight = (
                    math.factorial(size)
                    * math.factorial(n_players - size - 1)
                    / denominator
                )
                contribution += weight * (
                    parsed[coalition | {player}] - parsed[coalition]
                )
        result[player] = float(contribution)
    return result


def values_from_conditionals(
    conditionals: Mapping[str, Mapping[str, Any]],
    players: Sequence[str] = PLAYERS_BD,
    *,
    value_key: str = "recoverability_r",
    reduction: bool | None = None,
) -> dict[frozenset[str], float]:
    """Build a complete coalition value function from operator summaries.

    Lower-is-better keys (expected MAE, residual variance) are converted to
    reductions versus climatology so Shapley attributes *gain*.
    """

    names = tuple(str(player) for player in players)
    if "none" not in conditionals:
        raise KeyError("conditionals missing none")
    baseline = float(conditionals["none"][value_key])
    as_reduction = value_key in LOWER_BETTER_KEYS if reduction is None else reduction
    values: dict[frozenset[str], float] = {}
    for size in range(len(names) + 1):
        for combo in combinations(names, size):
            label = coalition_label(combo)
            if label not in conditionals:
                raise KeyError(f"conditionals missing {label}")
            raw = float(conditionals[label][value_key])
            values[frozenset(combo)] = (baseline - raw) if as_reduction else raw
    return values


def shapley_from_conditionals(
    conditionals: Mapping[str, Mapping[str, Any]],
    players: Sequence[str] = PLAYERS_BD,
    *,
    value_key: str = "recoverability_r",
    reduction: bool | None = None,
) -> dict[str, float]:
    return shapley_information(
        values_from_conditionals(
            conditionals,
            players,
            value_key=value_key,
            reduction=reduction,
        ),
        players,
    )


def extra_observed_nodes(
    items: Sequence[StationTime | int],
    gap_length: int,
) -> tuple[StationTime, ...]:
    """Interpret station indices as contemporaneous gap observations."""

    if gap_length < 1:
        raise ValueError("gap_length must be positive")
    nodes: list[StationTime] = []
    for item in items:
        if isinstance(item, StationTime):
            nodes.append(item)
            continue
        nodes.extend(StationTime(int(item), time) for time in range(gap_length))
    return tuple(nodes)


def shapley_from_var1(
    transition: np.ndarray,
    sigma: np.ndarray,
    *,
    target: int,
    donors: Sequence[int],
    gap_length: int,
    meteorology: Sequence[StationTime | int] = (),
    hydraulics: Sequence[StationTime | int] = (),
    value_key: str = "recoverability_r",
    reduction: bool | None = None,
    include_right_boundary: bool = True,
) -> dict[str, float]:
    """Exact Shapley of {B, D} or {B, D, M, H} on a known VAR(1)."""

    met_nodes = extra_observed_nodes(meteorology, gap_length) if meteorology else ()
    hyd_nodes = extra_observed_nodes(hydraulics, gap_length) if hydraulics else ()
    players = ["B", "D"]
    if met_nodes:
        players.append("M")
    if hyd_nodes:
        players.append("H")
    conditionals = information_set_conditionals(
        transition,
        sigma,
        target=target,
        donors=donors,
        gap_length=gap_length,
        include_right_boundary=include_right_boundary,
        meteorology=met_nodes,
        hydraulics=hyd_nodes,
    )
    return shapley_from_conditionals(
        conditionals,
        players,
        value_key=value_key,
        reduction=reduction,
    )


def shapley_frame(
    contributions: Mapping[str, float],
    *,
    river: str,
    gap_length: int,
    value_key: str,
) -> pd.DataFrame:
    total = float(sum(contributions.values()))
    rows = [
        {
            "river": river,
            "gap_length": int(gap_length),
            "player": player,
            "shapley": float(contributions[player]),
            "total_gain": total,
            "value_key": value_key,
            "player_order": ",".join(INFORMATION_PLAYER_ORDER),
        }
        for player in contributions
    ]
    return pd.DataFrame(rows)


__all__ = [
    "LOWER_BETTER_KEYS",
    "PLAYERS_BD",
    "PLAYERS_BDMH",
    "extra_observed_nodes",
    "normalize_coalition_key",
    "shapley_frame",
    "shapley_from_conditionals",
    "shapley_from_var1",
    "shapley_information",
    "values_from_conditionals",
]
