"""Counterexamples for missingness, silent denominator changes and cancellation."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    result = module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


W = load("process_review_water_air")
R = load("960_process_region_identification")


def panel():
    return pd.DataFrame([
        dict(station_key=s, region="region", independence_group=s, year=y,
             period="before_2010" if y < 2010 else "from_2010",
             air_h30_target_year=float(a), eval_truth_h30=float(2*a+i))
        for i, s in enumerate(["a", "b"])
        for y, a in [(2007, 2), (2008, 4), (2009, 5), (2010, 3), (2011, 6), (2012, 7)]
    ])


def test_duplicate_missing_finite_conflict_fails_in_both_row_orders():
    frame = panel().iloc[:1].copy()
    missing = frame.copy()
    missing["eval_truth_h30"] = np.nan
    for work in [pd.concat([frame, missing]), pd.concat([missing, frame])]:
        with pytest.raises(ValueError, match="including missingness"):
            W.deduplicate_complete_years(work)


def test_unique_nonfinite_years_have_explicit_exclusion_and_duplicate_counts():
    frame = panel()
    frame.loc[0, "air_h30_target_year"] = np.nan
    duplicated = pd.concat([frame, frame], ignore_index=True)
    work, audit = W.deduplicate_complete_years(duplicated)
    assert len(work) == len(frame)-1
    assert len(audit) == len(frame)
    assert audit.mask_rows.eq(2).all()
    assert audit.loc[~audit.included, "exclusion_reason"].tolist() == ["nonfinite_air"]
    expected = W.deduplicate_complete_years(duplicated.sample(frac=1, random_state=1))[0]
    pd.testing.assert_frame_equal(work.sort_values(["station_key","year"]).reset_index(drop=True),
                                  expected.sort_values(["station_key","year"]).reset_index(drop=True))


def test_station_metadata_conflict_and_missing_groups_cannot_disappear_in_groupby():
    work = panel()
    work.loc[0, "independence_group"] = "other"
    with pytest.raises(ValueError, match="membership"):
        W.deduplicate_complete_years(work)
    work.loc[0, "independence_group"] = None
    with pytest.raises(ValueError, match="metadata"):
        W.deduplicate_complete_years(work)
    with pytest.raises(ValueError, match="metadata"):
        W.station_moments(work)


def test_pooled_fit_is_invariant_to_large_temperature_origins():
    frame = panel()
    before = W.station_moments(frame)
    shifted = frame.copy()
    shifted["air_h30_target_year"] += 1e12
    shifted["eval_truth_h30"] += 1e12
    after = W.station_moments(shifted)
    for period in W.PERIODS:
        a = W.fit_moments(before.loc[before.period.eq(period), W.MOMENTS].sum().to_numpy(), "pooled")
        b = W.fit_moments(after.loc[after.period.eq(period), W.MOMENTS].sum().to_numpy(), "pooled")
        for metric in a:
            assert np.isclose(a[metric], b[metric], atol=1e-7)


def test_zero_variance_point_and_duplicate_station_year_fit_fail_clearly():
    frame = panel()
    frame["air_h30_target_year"] = 4.
    with pytest.raises(ValueError, match="zero variance"):
        W.paired_analysis(frame, bootstraps=10)
    with pytest.raises(ValueError, match="unique station-years"):
        W.paired_analysis(pd.concat([panel(), panel()]), bootstraps=10)


def test_bootstrap_handles_undefined_resampled_units_without_infinite_ci():
    frame = panel()
    frame.loc[frame.station_key.eq("a"), "air_h30_target_year"] = 4.
    summary, changes, _ = W.paired_analysis(frame, bootstraps=100, seed=14)
    within = summary.loc[summary.centering.eq("within_station_period")]
    assert (within.slope_valid_draws < 100).all()
    assert (within.slope_valid_draws > 0).all()
    assert np.isfinite(within.slope_low).all()


def test_missing_cells_and_separator_collisions_are_rejected():
    frame = pd.DataFrame({"region":["foen","gkd_bayern"],"a":[np.nan,np.nan]})
    with pytest.raises(ValueError, match="Missing"):
        R.common_cell_weights(frame,["a"])
    frame["a"] = ["one|two", "one"]
    with pytest.raises(ValueError, match="delimiter"):
        R.common_cell_weights(frame,["a"])


def test_2026_is_not_labeled_as_the_2020_2025_evaluation_period():
    bins = R.year_bin(pd.Series([2010,2014,2015,2019,2020,2025,2026]))
    assert bins.iloc[-1] is np.nan or pd.isna(bins.iloc[-1])
    assert str(bins.iloc[-2]) == "2020-2025"


def test_missing_intervals_are_not_silently_counted_as_coverage_misses():
    frame = pd.DataFrame({"reference_h30":[20.],"D2":[20.],"D2_q05":[np.nan],"D2_q95":[21.]})
    with pytest.raises(ValueError, match="finite"):
        R.outcome_values(frame,"D2")


def test_continuous_balance_is_conditional_on_finite_values_and_reports_missing_mass():
    frame = pd.DataFrame({"region":["foen","foen","gkd_bayern","gkd_bayern","gkd_bayern"],
                          "value":[0.,2.,0.,2.,np.nan],"weight":[.5,.5,.25,.25,.5]})
    mean, variance, missing = R.weighted_continuous(frame.loc[frame.region.eq("gkd_bayern")], "value", "weight")
    assert mean == 1 and variance == 1 and missing == .5
    # A zero conditional KS does not establish balance of missingness itself.
    assert R.weighted_ks(frame, "value", "weight") == 0
