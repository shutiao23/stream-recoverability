from __future__ import annotations

from stream_recoverability.experiments.sensor_policy import (
    budget_curve,
    evaluate_placement,
    policy_success,
)
from stream_recoverability.experiments.synthetic_river import advection_chain


def test_more_sensors_do_not_worsen_oracle_risk() -> None:
    river = advection_chain(n_stations=5)
    two = evaluate_placement(river, (0, 4), gap_length=14)
    four = evaluate_placement(river, (0, 1, 3, 4), gap_length=14)
    assert four["worst_case_mae"] <= two["worst_case_mae"] + 1e-8


def test_budget_curve_contains_required_policies() -> None:
    curve = budget_curve(advection_chain(n_stations=5), budgets=(2, 3), random_repeats=2)
    required = {
        "current_network",
        "random",
        "spatially_even",
        "degree",
        "distance",
        "correlation_redundancy",
        "observability_gramian",
        "oh_bartos_2025_rank_revealing_qr",
        "proposed_recoverability",
        "oracle",
    }
    assert required.issubset(set(curve["policy"]))
    success = policy_success(curve, reduction_min=0.0)
    assert not success.empty
    assert "worst_case_reduction" in success
