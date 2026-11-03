"""Tests for the dated benchmark layer: annual H30, gap generation, baselines, runner."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

import numpy as np
import pytest

from gapbench import (
    AnnualRecord,
    annual_h30,
    ar1_bridge_paths,
    climatology_fill,
    decompose_slope_error,
    finite_record_slope,
    generate_gaps,
    linear_interpolation_fill,
    run_benchmark,
)


def dated_series(first_year: int, n_years: int, seed: int = 0):
    start = date(first_year, 1, 1)
    days = (date(first_year + n_years, 1, 1) - start).days
    dates = [start + timedelta(days=i) for i in range(days)]
    rng = np.random.default_rng(seed)
    doy = np.array([d.timetuple().tm_yday for d in dates])
    years = np.array([d.year for d in dates])
    values = 15.0 + 12.0 * np.sin(2 * np.pi * (doy - 80) / 365.25) + 0.04 * (years - first_year)
    values = values + rng.normal(0.0, 0.8, days)
    return dates, values


def test_annual_h30_complete_years_match_direct_maximum():
    dates, values = dated_series(2001, 6, seed=3)
    record = annual_h30(dates, values)
    assert record.complete.all()
    assert np.isfinite(record.h30).all()
    # Direct check for one year: maximum complete 30-day mean.
    year_idx = [i for i, d in enumerate(dates) if d.year == 2003]
    windows = np.lib.stride_tricks.sliding_window_view(values[year_idx], 30)
    assert record.h30[record.years == 2003][0] == pytest.approx(windows.mean(axis=1).max())
    assert np.allclose(record.h30, record.observed_bound)


def test_annual_h30_incomplete_year_gives_bound_not_h30():
    dates, values = dated_series(2001, 6, seed=4)
    masked = values.copy()
    year_positions = [i for i, d in enumerate(dates) if d.year == 2003]
    masked[year_positions[150] : year_positions[150] + 60] = np.nan
    record = annual_h30(dates, masked)
    incomplete = record.years == 2003
    assert not record.complete[incomplete][0]
    assert np.isnan(record.h30[incomplete][0])
    bound = record.observed_bound[incomplete][0]
    truth = annual_h30(dates, values).observed_bound[incomplete][0]
    assert np.isfinite(bound) and bound <= truth + 1e-12
    # The bound is a valid lower bound on the true H30.
    assert bound <= annual_h30(dates, values).h30[incomplete][0]


def test_annual_h30_handles_leap_years_and_out_of_order_input():
    dates, values = dated_series(2000, 5, seed=5)  # 2000 is a leap year
    shuffled = np.random.default_rng(6).permutation(len(dates))
    record = annual_h30([dates[i] for i in shuffled], values[shuffled])
    assert list(record.years) == [2000, 2001, 2002, 2003, 2004]
    assert np.isfinite(record.h30).all()
    with pytest.raises(ValueError):
        annual_h30(dates + [dates[10]], np.append(values, 1.0))


def test_generate_gaps_is_reproducible_and_respects_burn_in():
    plan_a = generate_gaps(np.arange(2001, 2021), seed=7, length_days=45)
    plan_b = generate_gaps(np.arange(2001, 2021), seed=7, length_days=45)
    assert np.array_equal(plan_a.mask, plan_b.mask)
    assert plan_a.years.min() >= 2008  # seven-year burn-in
    expected_days = sum(366 if calendar.isleap(y) else 365 for y in range(2001, 2021))
    assert plan_a.mask.size == expected_days
    assert (plan_a.lengths == 45).all()
    excluded = generate_gaps(np.arange(2001, 2021), seed=7, length_days=45, exclude_years=plan_a.years.tolist())
    assert excluded.years.size == 0
    with pytest.raises(ValueError):
        generate_gaps(np.arange(2001, 2021), seed=7, length_days=45, year_probability=1.5)


def test_generate_gaps_probability_is_empirically_respected():
    plan = generate_gaps(np.arange(2001, 2051), seed=11, length_days=30)
    share = plan.years.size / (50 - 7)
    assert 0.15 < share < 0.60


def test_climatology_and_interpolation_fills_preserve_observed_values():
    dates, values = dated_series(2001, 8, seed=8)
    masked = values.copy()
    masked[900:960] = np.nan
    for filled in (climatology_fill(dates, masked), linear_interpolation_fill(dates, masked)):
        assert np.allclose(filled[~np.isnan(masked)], masked[~np.isnan(masked)])
        assert np.isfinite(filled).all()


def test_ar1_bridge_paths_prefix_invariance():
    dates, values = dated_series(2001, 8, seed=9)
    masked = values.copy()
    masked[1000:1060] = np.nan
    twenty = ar1_bridge_paths(dates, masked, n_paths=20, seed=42)
    hundred = ar1_bridge_paths(dates, masked, n_paths=100, seed=42)
    assert twenty.shape == (20, masked.size)
    assert np.allclose(twenty, hundred[:20])
    assert not np.allclose(twenty[0], twenty[1])
    observed = ~np.isnan(masked)
    assert np.allclose(twenty[:, observed], masked[observed])


def test_run_benchmark_scores_climatology_and_reports_decomposition():
    dates, values = dated_series(2001, 20, seed=12)
    plan = generate_gaps(np.arange(2001, 2021), seed=13, length_days=60, burn_in_years=5)

    def reconstructor(sorted_dates, daily_masked, record):
        assert np.isnan(daily_masked).any()
        return climatology_fill(sorted_dates, daily_masked)

    result = run_benchmark(dates, values, plan, reconstructor)
    assert result.annual_error.size == plan.years.size
    assert np.isfinite(result.annual_error).all()
    assert np.isfinite(result.slope_true)
    assert result.decomposition.identity_holds
    assert np.isclose(
        result.decomposition.total_error,
        result.slope_estimated - result.slope_true,
        atol=1e-9,
    )


def test_run_benchmark_rejects_misaligned_mask_and_bad_output():
    dates, values = dated_series(2001, 10, seed=14)
    plan = generate_gaps(np.arange(2001, 2011), seed=15, length_days=30)
    with pytest.raises(ValueError):
        run_benchmark(dates, values, plan, lambda dates_, d, r: d[:-1])
    with pytest.raises(ValueError):
        run_benchmark(dates, values, plan, lambda dates_, d, r: np.zeros(3))
