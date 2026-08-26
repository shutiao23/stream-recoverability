from __future__ import annotations

import numpy as np
import pytest

from stream_recoverability.analysis.conditional_observability import (
    GAUSSIAN_MAE_FACTOR,
    StationTime,
    conditional_summaries,
    expected_gaussian_mae,
    information_set_conditional_covariances,
    information_set_conditionals,
    loewner_leq,
    mean_nearest_boundary_distance,
    nearest_boundary_distances,
    recoverability_r,
    residual_quantile_width,
    schur_complement,
    stationary_covariance,
)
from stream_recoverability.analysis.recoverability_spectrum import (
    incremental_information,
    spectrum_from_var1,
)
from stream_recoverability.experiments.synthetic_river import (
    catalog,
    donor_dominant_river,
    memory_dominant_river,
)


def test_schur_complement_recovers_scalar_residual_variance() -> None:
    sigma_gg = np.array([[2.0]])
    sigma_go = np.array([[1.0]])
    sigma_oo = np.array([[2.0]])
    residual = schur_complement(sigma_gg, sigma_go, sigma_oo)
    assert residual[0, 0] == pytest.approx(1.5)


def test_gaussian_mae_matches_closed_form() -> None:
    sigma = np.diag([4.0, 9.0])
    assert expected_gaussian_mae(sigma) == pytest.approx(
        np.mean([2.0, 3.0]) * GAUSSIAN_MAE_FACTOR
    )


def test_more_information_never_increases_expected_mae() -> None:
    river = memory_dominant_river()
    summary = information_set_conditionals(
        river.transition,
        river.sigma,
        target=river.target,
        donors=river.donors,
        gap_length=30,
    )
    none = summary["none"]["expected_mae_conditional"]
    both = summary["B_union_D"]["expected_mae_conditional"]
    assert both <= none + 1e-10
    assert summary["B"]["expected_mae_conditional"] <= none + 1e-10
    assert summary["D"]["expected_mae_conditional"] <= none + 1e-10


def test_spectrum_recovers_known_information_order() -> None:
    memory = spectrum_from_var1(
        memory_dominant_river().transition,
        memory_dominant_river().sigma,
        target=0,
        donors=(1, 2),
        gap_length=30,
    )
    donor = spectrum_from_var1(
        donor_dominant_river().transition,
        donor_dominant_river().sigma,
        target=0,
        donors=(1, 2),
        gap_length=30,
    )
    assert memory.sign == "boundary_dominant"
    assert donor.sign == "donor_dominant"
    assert memory.tau > 0
    assert donor.tau < 0


def test_incremental_information_is_continuous_not_hard_threshold() -> None:
    value = incremental_information(0.20, 0.80, 0.85)
    assert value.sign == "donor_dominant"
    assert value.v_donor == pytest.approx(0.65)
    assert value.v_boundary == pytest.approx(0.05)


def test_nearest_boundary_mean_is_near_d_over_4_but_not_identical() -> None:
    distances = nearest_boundary_distances(180)
    assert mean_nearest_boundary_distance(180) == pytest.approx(float(distances.mean()))
    assert mean_nearest_boundary_distance(180) != pytest.approx(180 / 4.0)


def test_lyapunov_solver_is_symmetric_psd() -> None:
    transition = 0.4 * np.eye(2)
    noise = np.array([[1.0, 0.2], [0.2, 1.0]])
    sigma = stationary_covariance(transition, noise)
    assert sigma == pytest.approx(sigma.T)
    assert np.min(np.linalg.eigvalsh(sigma)) > 0


def test_recoverability_r_matches_v9_and_predicted_skill_stays_mae_ratio() -> None:
    hidden = np.diag([4.0, 9.0])
    residual = np.diag([1.0, 1.0])
    expected_r = 1.0 - np.sqrt(2.0 / 13.0)
    assert recoverability_r(hidden, residual) == pytest.approx(expected_r)
    summary = conditional_summaries(hidden, residual)
    assert summary["recoverability_r"] == pytest.approx(expected_r)
    mae_0 = expected_gaussian_mae(hidden)
    mae_s = expected_gaussian_mae(residual)
    assert summary["predicted_skill"] == pytest.approx(1.0 - mae_s / mae_0)
    assert summary["predicted_skill"] != pytest.approx(expected_r)


def test_loewner_leq_detects_psd_difference() -> None:
    smaller = np.eye(2)
    larger = 2.0 * np.eye(2)
    assert loewner_leq(smaller, larger)
    assert not loewner_leq(larger, smaller)


def test_adding_observations_never_increases_mae_or_decreases_r() -> None:
    nested = (("none", "B"), ("none", "D"), ("B", "B_union_D"), ("D", "B_union_D"))
    for river in catalog().values():
        matrices = information_set_conditional_covariances(
            river.transition,
            river.sigma,
            target=river.target,
            donors=river.donors,
            gap_length=14,
        )
        summary = information_set_conditionals(
            river.transition,
            river.sigma,
            target=river.target,
            donors=river.donors,
            gap_length=14,
        )
        for fewer, more in nested:
            assert loewner_leq(matrices[more], matrices[fewer])
            assert (
                summary[more]["expected_mae_conditional"]
                <= summary[fewer]["expected_mae_conditional"] + 1e-10
            )
            assert (
                summary[more]["recoverability_r"]
                >= summary[fewer]["recoverability_r"] - 1e-10
            )


def test_four_set_interface_adds_meteorology_and_hydraulics_coalitions() -> None:
    river = memory_dominant_river()
    meteorology = (StationTime(1, 0),)
    hydraulics = (StationTime(2, 0),)
    summary = information_set_conditionals(
        river.transition,
        river.sigma,
        target=river.target,
        donors=(),
        gap_length=8,
        meteorology=meteorology,
        hydraulics=hydraulics,
    )
    assert "B_union_D_union_M_union_H" in summary
    assert "M" in summary
    assert "H" in summary
    assert summary["B_union_D_union_M_union_H"]["n_observed"] == 4.0


def test_residual_quantile_width_is_documented_fallback_not_primary() -> None:
    samples = np.linspace(-2.0, 2.0, 21)
    width = residual_quantile_width(samples)
    assert width == pytest.approx(float(np.quantile(samples, 0.9) - np.quantile(samples, 0.1)))
    assert residual_quantile_width.__doc__ is not None
    assert "not the primary estimand" in residual_quantile_width.__doc__.lower()
