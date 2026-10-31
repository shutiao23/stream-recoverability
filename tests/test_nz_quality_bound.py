import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.experiments.tr_revision.native_temperature import NZST, strict_daily_mean


def load_screen():
    path = Path(__file__).resolve().parents[1] / 'scripts/681_nz_native_completeness_bound.py'
    spec = importlib.util.spec_from_file_location('nz_bound', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_finite_regular_day_is_only_a_quality_blind_possibility():
    dates = pd.date_range('2020-01-01', periods=96, freq='15min', tz=NZST)
    quality = pd.Series([600.], index=pd.DatetimeIndex([pd.Timestamp('1900-01-01', tz=NZST)]))
    raw = pd.Series(np.ones(len(dates)), index=dates)
    kwargs = dict(start='2020-01-01', end_exclusive='2020-01-02')
    assert strict_daily_mean(raw, quality, **kwargs).complete_native_day.tolist() == [True]
    raw.iloc[7] = np.inf
    raw = raw.where(np.isfinite(raw))
    assert strict_daily_mean(raw, quality, **kwargs).complete_native_day.tolist() == [False]
    raw.iloc[7] = 1
    assert strict_daily_mean(raw.drop(dates[7]), quality, **kwargs).complete_native_day.tolist() == [False]


def test_hot_year_includes_leap_day_and_missing_dates():
    dates = pd.date_range('2019-07-01', '2020-06-30')
    daily = pd.DataFrame({'date': dates, 'complete_native_day': True})
    screen = load_screen()
    assert screen.hot_year_counts(daily)[0]['expected_days'] == 366
    assert screen.hot_year_counts(daily)[0]['possibly_complete_year']
    without_leap = daily[daily.date.ne(pd.Timestamp('2020-02-29'))]
    assert not screen.hot_year_counts(without_leap)[0]['possibly_complete_year']


def test_duplicate_optimization_matches_original_nan_and_conflict_rules():
    index = pd.to_datetime(['2020-01-01', '2020-01-02', '2020-01-02', '2020-01-03', '2020-01-03', '2020-01-04', '2020-01-04'])
    series = pd.Series([3., 1., 1., 1., 2., np.nan, 2.], index=index)
    aggregate = lambda s: s.iloc[0] if len(s.unique()) == 1 else float('nan')
    original = series.groupby(level=0).agg(aggregate)
    duplicated = series.index.duplicated(keep=False)
    fast = pd.concat([series[~duplicated], series[duplicated].groupby(level=0).agg(aggregate)]).sort_index()
    pd.testing.assert_series_equal(original, fast)


def test_independent_annual_count_matches_strict_algorithm():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('independent_nz_audit', root / 'scripts/683_nz_completeness_independent_audit.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    index = pd.date_range('2019-07-01', '2020-06-30 23:00', freq='h', tz=NZST)
    raw = pd.Series(1., index=index)
    raw.loc[pd.Timestamp('2020-02-29 03:00', tz=NZST)] = np.nan
    quality = pd.Series([600.], index=pd.DatetimeIndex([pd.Timestamp('1900-01-01', tz=NZST)]))
    daily = strict_daily_mean(raw, quality, start='2019-07-01', end_exclusive='2020-07-01')
    expected = load_screen().hot_year_counts(daily)[0]
    independently_counted = audit.independently_count(raw, pd.Timestamp('2019-07-01'), pd.Timestamp('2020-07-01'))
    assert independently_counted == [(2019, 366, expected['possible_complete_days'])]
    assert expected['possible_complete_days'] == 365
