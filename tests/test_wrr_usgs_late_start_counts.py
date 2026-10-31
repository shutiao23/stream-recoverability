import importlib.util
from pathlib import Path
import pandas as pd
import pytest

SPEC = importlib.util.spec_from_file_location('late_counts', Path(__file__).resolve().parents[1] / 'scripts/650_usgs_late_start_counts.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def feature(values, site='USGS-12345678', series='series'):
    return {'properties': {'monitoring_location_id': site, 'data': [{'parent_time_series_id': series, 'parent_statistic_id': '00003', 'values': values}]}}


def annual(start, end, n, approved='approved'):
    return {'start_date': start, 'end_date': end, 'sample_count': n, 'interval_type': 'calendar_year', 'approval_status': approved, 'value': 999}


def test_count_requires_complete_interval_and_leap_days():
    roster = pd.DataFrame([{'station_id': '12345678', 'series_id': 'series'}])
    values = [annual('2020-01-01', '2020-12-31', 366), annual('2021-02-01', '2021-12-31', 334), annual('2022-01-01', '2022-12-31', 365, 'provisional')]
    out = MODULE.extract_counts({'features': [feature(values)]}, roster)
    assert out.year.tolist() == [2020, 2021]
    assert out.count_complete.tolist() == [True, False]
    assert 'value' not in out.columns


def test_duplicate_year_and_pagination_rejected():
    roster = pd.DataFrame([{'station_id': '12345678', 'series_id': 'series'}])
    val = annual('2020-01-01', '2020-12-31', 366)
    with pytest.raises(ValueError, match='Duplicate'):
        MODULE.extract_counts({'features': [feature([val, val])]}, roster)
    with pytest.raises(ValueError, match='Paginated'):
        MODULE.extract_counts({'features': [], 'links': [{'rel': 'next'}]}, roster)


def test_unreturned_or_other_series_not_misrepresented_as_zero():
    roster = pd.DataFrame([{'station_id': '12345678', 'series_id': 'series'}])
    out = MODULE.extract_counts({'features': [feature([annual('2020-01-01', '2020-12-31', 366)], series='other')]}, roster)
    assert out.empty
