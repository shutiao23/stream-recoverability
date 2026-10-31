"""Scientific checks of information access and fixed-marginal trend inference."""

import numpy as np
import pandas as pd

from stream_recoverability.experiments.tr_revision.archive import (
    factorial_contrasts,
    group_error_quantile,
    history_ranks,
    marginal_draws,
    mask_archive,
    reorder_marginals,
    slope,
    trend_result,
    task_calibration_support,
)


def test_all_hidden_years_are_removed_before_fitting_and_cannot_change_draws():
    dates = pd.date_range("2000-01-01", "2011-12-31")
    air = pd.Series(
        10 + 5 * np.sin(dates.dayofyear.to_numpy() / 365.25 * 2 * np.pi), index=dates
    )
    rng = np.random.default_rng(10)
    panel = pd.DataFrame(
        {"target": 2 + 0.7 * air + rng.normal(size=len(dates)), "donor": air},
        index=dates,
    )
    masks = {2003: "150:30", 2008: "160:60"}
    first = mask_archive(panel, "target", masks)
    altered = panel.copy()
    for year, run in masks.items():
        start, length = map(int, run.split(":"))
        positions = np.flatnonzero(dates.year == year)[start : start + length]
        altered.iloc[positions, 0] += 1000
    second = mask_archive(altered, "target", masks)
    pd.testing.assert_frame_equal(first, second)
    np.testing.assert_array_equal(first.donor, panel.donor)
    a = history_ranks(first.target, air, masks, [2003, 2008], draws=16, block=3)
    b = history_ranks(second.target, air, masks, [2003, 2008], draws=16, block=3)
    np.testing.assert_array_equal(a, b)


def test_forward_joint_fit_ignores_future_visible_values():
    dates = pd.date_range("1995-01-01", "2015-12-31")
    air = pd.Series(
        10 + 5 * np.sin(dates.dayofyear.to_numpy() / 365.25 * 2 * np.pi), index=dates
    )
    target = 2 + 0.7 * air + np.random.default_rng(5).normal(size=len(dates))
    masks = {2011: "150:30", 2013: "160:30"}
    changed = target.copy()
    changed.loc[dates.year >= 2010] += 100
    a = history_ranks(target, air, masks, [2011, 2013], draws=16, fit_before=2010)
    b = history_ranks(changed, air, masks, [2011, 2013], draws=16, fit_before=2010)
    np.testing.assert_array_equal(a, b)


def test_dependence_changes_trend_uncertainty_without_changing_any_marginal():
    base = np.tile(np.linspace(-1, 1, 100)[:, None], (1, 3))
    constant_bias = reorder_marginals(base, base)
    drift = reorder_marginals(base, base * np.array([-1, 1, 1]))
    np.testing.assert_array_equal(
        np.sort(constant_bias, axis=0), np.sort(drift, axis=0)
    )
    np.testing.assert_allclose(slope([2000, 2010, 2020], constant_bias), 0, atol=1e-12)
    assert np.std(slope([2000, 2010, 2020], drift)) > 0.5
    result = trend_result([2000, 2010, 2020], np.zeros(3), np.zeros(3), constant_bias)
    assert result["missing_coverage95"] and result["width95"] < 1e-12


def test_factorial_decomposition_is_symmetric_and_adds_to_total_gain():
    rows = []
    for retention, estimator, mse in [
        ("warm90", "plug_in", 10),
        ("all", "plug_in", 6),
        ("warm90", "D2", 7),
        ("all", "D2", 5),
        ("warm90", "stochastic_calibrated", 8),
        ("all", "stochastic_calibrated", 4),
    ]:
        rows.append(
            dict(
                mode="offline",
                station_key="x",
                replicate=0,
                retention=retention,
                estimator=estimator,
                squared_error=mse,
            )
        )
    result = factorial_contrasts(pd.DataFrame(rows))
    np.testing.assert_allclose(
        result.symmetric_retention + result.symmetric_estimator, result.total_gain
    )
    assert result.set_index("estimator").loc["D2", "interaction"] == 2


def test_repeated_masks_cannot_increase_a_calibration_groups_total_weight():
    a = pd.DataFrame({"independence_group": ["a", "a"], "error": [1.0, -3.0]})
    b = pd.DataFrame({"independence_group": ["b"], "error": [10.0]})
    original = pd.concat([a, b], ignore_index=True)
    repeated = pd.concat([a] * 100 + [b], ignore_index=True)
    assert group_error_quantile(original) == group_error_quantile(repeated) == 10.0
    assert np.quantile(repeated.error.abs(), 0.95) < group_error_quantile(repeated)


def test_tail_sensitivity_preserves_the_stored_central_quantile_function():
    q = np.array([[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]])
    flat = marginal_draws(q, draws=200, tails="constant")
    extended = marginal_draws(q, draws=200, tails="normal")
    np.testing.assert_array_equal(flat[10:190], extended[10:190])
    assert extended[0, 0] < flat[0, 0] and extended[-1, 0] > flat[-1, 0]


def test_normal_tails_restore_normal_reference_and_respect_observed_bounds():
    from scipy.stats import norm
    levels = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]
    q = norm.ppf(levels)[None, :]
    draws = marginal_draws(q, draws=4000)[:, 0]
    lo, hi = np.quantile(draws, [0.025, 0.975])
    assert norm.cdf(hi) - norm.cdf(lo) > 0.949
    bounded = marginal_draws(q, draws=4000, lower_bounds=[-1.0])[:, 0]
    assert bounded.min() >= -1.0
    # Interpolating projected stored quantiles changes the segment crossing the
    # bound; quantile intervals entirely above it remain unchanged.
    np.testing.assert_array_equal(draws[1000:], bounded[1000:])


def test_task_calibration_withholds_degenerate_or_unsupported_source_groups():
    frame = pd.DataFrame({"independence_group": ["a", "b", "c"],
                          "reference_half_width": [1.0, 1.0, 1.0],
                          "error": [0.0, 0.0, 0.0]})
    plan, _ = task_calibration_support(frame)
    assert plan["status"] == "degenerate_source_errors"
    frame.loc[0, "error"] = 2.0
    assert task_calibration_support(frame.iloc[:2])[0]["status"] == "insufficient_source_groups"
    plan, _ = task_calibration_support(frame)
    assert plan["status"] == "supported" and plan["scale_factor"] == 2.0
    frame.loc[2, "reference_half_width"] = 0.0
    assert task_calibration_support(frame)[0]["status"] == "insufficient_source_groups"


def test_source_and_archive_use_the_same_bounded_tail_distribution():
    import importlib.util
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    spec = importlib.util.spec_from_file_location("annual_scoring_test", root / "scripts/528_review_response_annual.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    q = np.array([[1, 2, 3, 4, 5, 6, 7], [10, 11, 12, 13, 14, 15, 16]], dtype=float)
    bounds = np.array([2.5, np.nan])
    source = module.quantile_samples(q, bounds, draws=128)
    archive = marginal_draws(q, draws=128, lower_bounds=bounds).T
    np.testing.assert_allclose(source, archive, rtol=0, atol=1e-12)
