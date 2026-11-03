from __future__ import annotations

import inspect
import math

import numpy as np
import pytest

from gapbench import (
    decompose_slope_error,
    finite_record_slope,
    group_splits,
    mask_archive,
    observed_window_bound,
    select_years,
)


def test_finite_record_slope_known_answer() -> None:
    years = np.arange(1998, 2003)
    values = np.array([1.0, 2.0, 4.0, 8.0, 16.0])

    fit = finite_record_slope(years, values)

    assert fit.slope_per_decade == pytest.approx(36.0)
    assert fit.intercept == pytest.approx(6.2 - 3.6 * 2000.0)
    assert fit.standard_error == pytest.approx(8.0)
    assert fit.n == 5


def test_finite_record_slope_matches_ols_weights() -> None:
    years = np.arange(1998, 2003, dtype=float)
    values = np.array([1.0, 2.0, 4.0, 8.0, 16.0])
    centered = years - years.mean()
    weights = centered / (centered @ centered)

    fit = finite_record_slope(years, values)

    assert weights.sum() == pytest.approx(0.0, abs=1e-12)
    assert fit.slope_per_decade == pytest.approx(10.0 * float(weights @ values))
    assert fit.intercept == pytest.approx(
        values.mean() - 0.1 * fit.slope_per_decade * years.mean()
    )


def test_finite_record_slope_filters_pairs_and_flags_two_points() -> None:
    fit = finite_record_slope([2000.0, 2001.0, 2002.0, 2003.0], [1.0, np.nan, 3.0, 4.0])
    assert fit.n == 3

    two_points = finite_record_slope([2000.0, 2001.0], [1.0, 3.0])
    assert two_points.slope_per_decade == pytest.approx(20.0)
    assert math.isnan(two_points.standard_error)


def test_observed_window_bound_known_answers() -> None:
    series = np.arange(40, dtype=float)
    bound = observed_window_bound(series, 30)
    assert bound.value == pytest.approx(24.5)
    assert (bound.start, bound.end) == (10, 40)

    small = observed_window_bound([1.0, 2.0, 3.0, 4.0, 5.0], 3)
    assert small.value == pytest.approx(4.0)
    assert (small.start, small.end) == (2, 5)


def test_observed_window_bound_respects_gaps() -> None:
    gapped = np.array([1.0, 2.0, 3.0, np.nan, 5.0, 6.0, 7.0])
    bound = observed_window_bound(gapped, 3)
    assert bound.value == pytest.approx(6.0)
    assert (bound.start, bound.end) == (4, 7)

    no_window = observed_window_bound([1.0, 2.0, np.nan, 4.0], 3)
    assert math.isnan(no_window.value)
    assert no_window.start is None and no_window.end is None


def test_select_years_cdf_and_sxx_known_answer() -> None:
    years = np.arange(10)
    complete = np.array([0, 1, 2, 3, 8, 9])

    cdf_selected = select_years(years, complete, method="cdf", count=8)
    sxx_selected = select_years(years, complete, method="sxx", count=8)

    assert cdf_selected.tolist() == [0, 1, 2, 3, 5, 6, 8, 9]
    assert sxx_selected.tolist() == [0, 1, 2, 3, 6, 7, 8, 9]
    for selected in (cdf_selected, sxx_selected):
        assert len(selected) == 8
        assert set(complete).issubset(selected.tolist())


def test_select_years_is_deterministic_and_count_none_keeps_all() -> None:
    years = np.arange(10)
    complete = np.array([0, 1, 2, 3, 8, 9])
    first = select_years(years, complete, method="cdf", count=7)
    second = select_years(years, complete, method="cdf", count=7)
    assert np.array_equal(first, second)

    assert select_years(years, complete).tolist() == years.tolist()


def test_select_years_rejects_impossible_inputs() -> None:
    years = np.arange(10)
    complete = np.array([0, 1, 2, 3, 8, 9])
    with pytest.raises(ValueError):
        select_years(years, complete, method="cdf", count=5)
    with pytest.raises(ValueError):
        select_years(years, np.array([99]), method="cdf")
    with pytest.raises(ValueError):
        select_years(years, complete, method="other")
    with pytest.raises(ValueError):
        select_years([0, 0, 1], [0], method="cdf")


def test_select_years_has_no_outcome_argument() -> None:
    parameters = inspect.signature(select_years).parameters
    forbidden = {
        "temperature",
        "temperatures",
        "values",
        "outcomes",
        "target",
        "predictions",
        "errors",
    }
    assert forbidden.isdisjoint(parameters)
    assert not any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )

    years = np.arange(10)
    complete = np.array([0, 1, 2, 3, 8, 9])
    temperatures = np.linspace(10.0, 20.0, years.size)
    with pytest.raises(TypeError):
        select_years(years, complete, temperature=temperatures)
    with pytest.raises(ValueError):
        select_years(years, complete, temperatures)


def test_decompose_slope_error_identity() -> None:
    years = np.arange(2000, 2010)
    truth = 10.0 + 0.4 * (years - 2000)
    estimate = truth + 0.1 * (years - 2000)
    selected = years[[0, 1, 2, 3, 8, 9]]
    keep = np.isin(years, selected)
    reference = finite_record_slope(years, truth)

    result = decompose_slope_error(
        reference.slope_per_decade,
        selected,
        truth[keep],
        estimate[keep],
    )

    assert result.S == pytest.approx(0.0, abs=1e-12)
    assert result.R == pytest.approx(1.0)
    assert result.E == pytest.approx(1.0)
    assert result.cross_term == pytest.approx(2.0 * result.S * result.R)
    assert result.identity_residual == pytest.approx(0.0, abs=1e-12)
    assert result.identity_ok is True
    assert result.identity_holds is True


def test_decompose_slope_error_nontrivial_identity() -> None:
    years = np.arange(2000, 2011)
    truth = 12.0 + 0.3 * (years - 2000) + 0.02 * (years - 2005) ** 2
    estimate = truth + 0.05 * (years - 2000) + 0.1
    selected = years[[0, 1, 2, 3, 8, 9]]
    keep = np.isin(years, selected)
    reference = finite_record_slope(years, truth)

    result = decompose_slope_error(
        reference.slope_per_decade,
        selected,
        truth[keep],
        estimate[keep],
    )

    assert abs(result.S) > 1e-6
    assert abs(result.R) > 1e-6
    assert result.E == pytest.approx(result.S + result.R, abs=1e-12)
    assert result.cross_term == pytest.approx(2.0 * result.S * result.R)
    assert result.identity_ok is True


def test_group_splits_are_disjoint_and_deterministic() -> None:
    groups = np.array(["a", "a", "b", "b", "c", "c", "d", "d", "e", "e"])

    folds = group_splits(groups, n_splits=3, seed=7)
    repeated = group_splits(groups, n_splits=3, seed=7)

    assert len(folds) == 3
    seen_groups: set[str] = set()
    all_test = np.concatenate([test for _, test in folds])
    assert sorted(all_test.tolist()) == list(range(groups.size))
    for (train, test), (train_repeated, test_repeated) in zip(folds, repeated):
        assert np.array_equal(train, train_repeated)
        assert np.array_equal(test, test_repeated)
        assert set(train).isdisjoint(test)
        assert sorted(np.concatenate([train, test]).tolist()) == list(
            range(groups.size)
        )
        test_groups = set(groups[test].tolist())
        assert seen_groups.isdisjoint(test_groups)
        seen_groups.update(test_groups)
    assert seen_groups == set(groups.tolist())

    with pytest.raises(ValueError):
        group_splits(groups, n_splits=6, seed=7)


def test_mask_archive_masks_only_the_requested_segment() -> None:
    values = np.arange(10, dtype=float)
    masked = mask_archive(values, 3, 4)

    assert np.all(np.isnan(masked[3:7]))
    assert np.array_equal(masked[:3], values[:3])
    assert np.array_equal(masked[7:], values[7:])
    assert not np.any(np.isnan(values))

    with pytest.raises(ValueError):
        mask_archive(values, 8, 4)
    with pytest.raises(ValueError):
        mask_archive(values, -1, 2)
