import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


spec = importlib.util.spec_from_file_location(
    'nova_clock_reference', Path(__file__).resolve().parents[1] / 'scripts/604_nova_clock_sensitivity_reference.py'
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def sources(year, shift):
    start = pd.Timestamp(year=year, month=1, day=1) + pd.Timedelta(hours=shift)
    end = pd.Timestamp(year=year+1, month=1, day=1) + pd.Timedelta(hours=shift)
    hours = pd.date_range(start, end, freq='h', inclusive='left')
    f = pd.DataFrame({'timestamp': hours, 'value': np.arange(len(hours), dtype=float)})
    return f, f.copy()


def test_shifted_daily_means_include_adjacent_year_boundary_hours():
    workbook, portal = sources(2020, -1)
    daily, status = audit.build_year(workbook, portal, 2020, -1)
    assert status['status'] == 'available' and status['expected_hours'] == 366 * 24
    assert len(daily) == 366 and daily.date.iloc[0] == pd.Timestamp('2020-01-01')
    assert daily.temperature_c.iloc[0] == np.mean(np.arange(24))


def test_missing_duplicate_and_mismatched_boundary_hours_are_not_filled():
    workbook, portal = sources(2021, 1)
    daily, status = audit.build_year(workbook, portal.iloc[:-1], 2021, 1)
    assert daily is None and status['status'] == 'missing_or_nonfinite_hour'
    duplicate = pd.concat([portal, portal.iloc[[0]]], ignore_index=True)
    daily, status = audit.build_year(workbook, duplicate, 2021, 1)
    assert daily is None and status['status'] == 'duplicate_hour'
    changed = portal.copy()
    changed.loc[0, 'value'] += .1
    daily, status = audit.build_year(workbook, changed, 2021, 1)
    assert daily is None and status['status'] == 'release_disagreement'
