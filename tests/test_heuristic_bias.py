from __future__ import annotations

import numpy as np
import pytest

from stream_recoverability.analysis.heuristic_bias import (
    PHASE1_RELATIVE_ERROR_MAX,
    bias_terms_from_var1,
    contemporaneous_donor_r2,
    forced_label_identity_rows,
    heuristic_explained_variance,
    nonorthogonal_ar1_donor,
    operator_vs_true_conditional_relative_error,
    orthogonal_ar1_donor,
)
from stream_recoverability.analysis.heuristic_degeneration import forced_donor_dominated
from stream_recoverability.experiments.synthetic_river import (
    high_donor_and_high_memory_river,
    memory_dominant_river,
)


def test_heuristic_explained_variance_is_additive_formula() -> None:
    assert heuristic_explained_variance(0.4, 0.5) == pytest.approx(0.4 + 0.6 * 0.25)


def test_forced_donor_dominated_when_r2_at_least_half() -> None:
    table = forced_label_identity_rows()
    forced = table.loc[table["R2_donor"].ge(0.5)]
    assert forced["forced_donor_dominated"].all()
    assert forced["hard_label"].eq("donor_dominated").all()
    below = table.loc[table["R2_donor"].lt(0.5)]
    assert not bool(below["forced_donor_dominated"].any())


def test_high_donor_high_memory_forces_the_hard_label() -> None:
    river = high_donor_and_high_memory_river()
    donor_r2 = contemporaneous_donor_r2(river.sigma, river.target, river.donors)
    assert donor_r2 >= 0.5
    assert forced_donor_dominated(donor_r2)
    row = bias_terms_from_var1(
        river.transition,
        river.sigma,
        target=river.target,
        donors=river.donors,
        gap_length=30,
        river=river.name,
    )
    assert row["forced_donor_dominated"] is True


def test_bias_terms_split_old_minus_new_into_epsilons() -> None:
    transition, sigma, target, donors = orthogonal_ar1_donor()
    row = bias_terms_from_var1(
        transition,
        sigma,
        target=target,
        donors=donors,
        gap_length=30,
        river="orthogonal_ar1_donor",
    )
    assert row["old_minus_new"] == pytest.approx(
        float(row["epsilon_perp"]) + float(row["epsilon_d_over_4"])
    )
    assert float(row["R2_donor"]) < 0.05
    assert row["forced_donor_dominated"] is False


def test_epsilon_perp_grows_when_orthogonality_is_violated() -> None:
    orthogonal = bias_terms_from_var1(
        *orthogonal_ar1_donor()[:2],
        target=0,
        donors=(1,),
        gap_length=30,
        river="orthogonal",
    )
    correlated = bias_terms_from_var1(
        *nonorthogonal_ar1_donor()[:2],
        target=0,
        donors=(1,),
        gap_length=30,
        river="nonorthogonal",
    )
    assert abs(float(correlated["epsilon_perp"])) > abs(float(orthogonal["epsilon_perp"]))
    assert float(correlated["R2_donor"]) > float(orthogonal["R2_donor"])


def test_operator_relative_error_beats_phase1_gate_on_var1() -> None:
    river = memory_dominant_river()
    error = operator_vs_true_conditional_relative_error(
        river.transition,
        river.sigma,
        target=river.target,
        donors=river.donors,
        gap_length=14,
    )
    assert error["relative_error_mean_diag"] < PHASE1_RELATIVE_ERROR_MAX
    assert error["relative_error_frobenius"] < PHASE1_RELATIVE_ERROR_MAX
    assert error["phase1_gate_pass"] is True
