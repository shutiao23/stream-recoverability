import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


spec = importlib.util.spec_from_file_location(
    'nechako_qualification', Path(__file__).resolve().parents[1] / 'scripts/585_nechako_reference_qualification.py'
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def regular_year(year):
    time = pd.date_range(f'{year}-01-01', f'{year+1}-01-01', freq='15min', inclusive='left', tz='UTC')
    return pd.DataFrame({'timestamp': time, 'temperature': np.ones(len(time)), 'flag': 'P'})


def test_complete_leap_year_requires_all_utc_quarter_hours():
    frame = regular_year(2020)
    result, days = audit.qualify_year(frame, 2020)
    assert result['qualified'] and result['calendar_days'] == 366
    assert result['source_rows'] == 366 * 96 and len(days) == 366
    np.testing.assert_allclose(days.water_c, 1.)


def test_missing_duplicate_flagged_nonfinite_and_off_grid_days_fail():
    frame = regular_year(2021)
    frame = frame.drop(index=0).copy()
    frame = pd.concat([frame, frame.loc[[96]]], ignore_index=True)
    frame.loc[frame.timestamp.eq(pd.Timestamp('2021-01-03T00:00Z')), 'flag'] = 'B'
    frame.loc[frame.timestamp.eq(pd.Timestamp('2021-01-04T00:00Z')), 'temperature'] = np.nan
    off_grid = frame.timestamp.eq(pd.Timestamp('2021-01-05T00:00Z'))
    frame.loc[off_grid, 'timestamp'] += pd.Timedelta(minutes=1)
    result, days = audit.qualify_year(frame, 2021)
    assert not result['qualified'] and result['missing_days'] == 5
    assert result['duplicate_rows'] == 2 and result['off_grid_rows'] == 1
    assert result['nonfinite_rows'] == 1 and result['disallowed_flag_rows'] == 1
    assert len(days) == 360


def test_author_approved_average_flag_is_allowed_without_admitting_cautionary_average():
    frame = regular_year(2023)
    frame.loc[0, 'flag'] = 'A'
    result, _ = audit.qualify_year(frame, 2023)
    assert result['qualified']
    frame.loc[0, 'flag'] = 'C'
    result, _ = audit.qualify_year(frame, 2023)
    assert not result['qualified'] and result['disallowed_flag_rows'] == 1
