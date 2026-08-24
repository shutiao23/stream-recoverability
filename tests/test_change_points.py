import numpy as np
import pytest

from stream_recoverability.analysis.change_points import (
    least_squares_change_point,
    permutation_p_value,
    pettitt_change_point,
    residual_block_bootstrap_change_points,
)


def test_pettitt_and_least_squares_locate_a_clear_single_step() -> None:
    values = np.r_[np.zeros(120), np.full(120, 4.0)]
    pettitt = pettitt_change_point(values, min_segment=30)
    least_squares = least_squares_change_point(values, min_segment=30)
    assert pettitt["change_index"] == 120
    assert least_squares["change_index"] == 120
    assert pettitt["signed_statistic"] < 0
    assert pettitt["asymptotic_p_value_iid"] < 0.001


def test_block_permutation_is_reproducible_and_preserves_auditable_contract() -> None:
    values = np.r_[np.arange(20), np.arange(20) + 10.0]
    labels = np.repeat([2001, 2002, 2003, 2004], 10)
    first = permutation_p_value(
        values,
        pettitt_change_point,
        n_permutations=99,
        seed=17,
        min_segment=5,
        block_labels=labels,
    )
    second = permutation_p_value(
        values,
        pettitt_change_point,
        n_permutations=99,
        seed=17,
        min_segment=5,
        block_labels=labels,
    )
    assert first == second
    assert first["block_count"] == 4
    assert first["scheme"] == "contiguous_block_order_permutation"
    assert first["p_value"] == pytest.approx((first["exceedances"] + 1) / 100)


def test_residual_block_bootstrap_returns_valid_deterministic_change_indices() -> None:
    rng = np.random.default_rng(3)
    values = np.r_[rng.normal(0, 0.1, 100), rng.normal(3, 0.1, 100)]
    result = residual_block_bootstrap_change_points(
        values,
        pettitt_change_point,
        n_bootstrap=100,
        block_length=10,
        seed=29,
        min_segment=30,
        center="median",
    )
    repeat = residual_block_bootstrap_change_points(
        values,
        pettitt_change_point,
        n_bootstrap=100,
        block_length=10,
        seed=29,
        min_segment=30,
        center="median",
    )
    assert np.array_equal(result["change_indices"], repeat["change_indices"])
    assert result["ci_lower_index"] <= 100 <= result["ci_upper_index"]
    assert np.all((result["change_indices"] >= 30) & (result["change_indices"] <= 170))


@pytest.mark.parametrize(
    "values,min_segment",
    [([1.0, 2.0, np.nan, 4.0], 1), ([1.0, 2.0, 3.0, 4.0], 3)],
)
def test_change_point_input_contract_rejects_invalid_series(
    values: list[float], min_segment: int
) -> None:
    with pytest.raises(ValueError):
        pettitt_change_point(values, min_segment=min_segment)
