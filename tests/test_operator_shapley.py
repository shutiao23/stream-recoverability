from __future__ import annotations

import numpy as np
import pytest

from stream_recoverability.analysis.conditional_observability import (
    StationTime,
    information_set_conditionals,
    stationary_covariance,
)
from stream_recoverability.analysis.operator_shapley import (
    shapley_from_conditionals,
    shapley_from_var1,
    shapley_information,
)
from stream_recoverability.experiments.synthetic_river import (
    donor_dominant_river,
    memory_dominant_river,
)


def test_shapley_information_matches_two_player_formula() -> None:
    values = {
        "none": 0.0,
        "B": 1.0,
        "D": 3.0,
        "B_union_D": 6.0,
    }
    result = shapley_information(values, ("B", "D"))
    assert result["B"] == pytest.approx(0.5 * (1.0 - 0.0) + 0.5 * (6.0 - 3.0))
    assert result["D"] == pytest.approx(0.5 * (3.0 - 0.0) + 0.5 * (6.0 - 1.0))
    assert result["B"] + result["D"] == pytest.approx(6.0)


def test_shapley_information_efficiency_on_four_players() -> None:
    players = ("B", "D", "M", "H")
    values = {
        frozenset(players[bit] for bit in range(4) if mask & (1 << bit)): float(
            bin(mask).count("1")
        )
        for mask in range(16)
    }
    result = shapley_information(values, players)
    assert sum(result.values()) == pytest.approx(4.0)
    for player in players:
        assert result[player] == pytest.approx(1.0)


def test_memory_dominant_boundary_shapley_exceeds_donor() -> None:
    river = memory_dominant_river()
    result = shapley_from_var1(
        river.transition,
        river.sigma,
        target=river.target,
        donors=river.donors,
        gap_length=30,
        value_key="expected_mae_conditional",
    )
    assert result["B"] > result["D"]


def test_donor_dominant_donor_shapley_exceeds_boundary() -> None:
    river = donor_dominant_river()
    result = shapley_from_var1(
        river.transition,
        river.sigma,
        target=river.target,
        donors=river.donors,
        gap_length=30,
        value_key="expected_mae_conditional",
    )
    assert result["D"] > result["B"]


def test_four_set_shapley_is_efficient() -> None:
    transition = np.diag([0.85, 0.25, 0.25, 0.25])
    noise = np.array(
        [
            [1.00, 0.10, 0.40, 0.20],
            [0.10, 1.00, 0.05, 0.05],
            [0.40, 0.05, 1.00, 0.10],
            [0.20, 0.05, 0.10, 1.00],
        ]
    )
    sigma = stationary_covariance(transition, noise)
    meteorology = tuple(StationTime(2, time) for time in range(8))
    hydraulics = tuple(StationTime(3, time) for time in range(8))
    conditionals = information_set_conditionals(
        transition,
        sigma,
        target=0,
        donors=(1,),
        gap_length=8,
        meteorology=meteorology,
        hydraulics=hydraulics,
    )
    assert len(conditionals) == 16
    result = shapley_from_conditionals(
        conditionals,
        ("B", "D", "M", "H"),
        value_key="expected_mae_conditional",
    )
    total = (
        conditionals["none"]["expected_mae_conditional"]
        - conditionals["B_union_D_union_M_union_H"]["expected_mae_conditional"]
    )
    assert sum(result.values()) == pytest.approx(total)
    assert set(result) == {"B", "D", "M", "H"}


def test_default_shapley_uses_recoverability_r() -> None:
    river = memory_dominant_river()
    default = shapley_from_var1(
        river.transition,
        river.sigma,
        target=river.target,
        donors=river.donors,
        gap_length=30,
    )
    explicit = shapley_from_var1(
        river.transition,
        river.sigma,
        target=river.target,
        donors=river.donors,
        gap_length=30,
        value_key="recoverability_r",
    )
    assert default == pytest.approx(explicit)
    assert default["B"] > default["D"]


def test_shapley_information_requires_all_coalitions() -> None:
    with pytest.raises(ValueError, match="missing coalitions"):
        shapley_information({"none": 0.0, "B": 1.0}, ("B", "D"))
