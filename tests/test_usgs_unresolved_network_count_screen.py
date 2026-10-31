import importlib.util
from pathlib import Path

import pandas as pd
import pytest


spec = importlib.util.spec_from_file_location(
    'usgs_unresolved_count', Path(__file__).resolve().parents[1] / 'scripts/583_usgs_unresolved_network_count_screen.py'
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_extract_counts_uses_only_matching_approved_daily_mean_and_discards_values():
    roster = pd.DataFrame({'station_id': ['001'], 'series_id': ['chosen']})
    approved = {'interval_type': 'calendar_year', 'approval_status': 'approved',
                'start_date': '2025-01-01', 'end_date': '2025-12-31', 'sample_count': 365,
                'value': 17.25}
    wrong = {'parent_time_series_id': 'other', 'parent_statistic_id': '00003', 'values': [approved]}
    right = {'parent_time_series_id': 'chosen', 'parent_statistic_id': '00003', 'values': [approved]}
    doc = {'features': [{'properties': {'monitoring_location_id': 'USGS-001', 'data': [wrong, right]}}]}
    result = audit.extract_year(doc, roster, 2025)
    assert len(result) == 1 and bool(result.loc[0, 'count_complete'])
    assert result.loc[0, 'approved_daily_count'] == 365
    assert 'value' not in result.columns
    right['values'].append(dict(approved))
    with pytest.raises(ValueError, match='duplicate'):
        audit.extract_year(doc, roster, 2025)


def test_partial_leap_year_is_not_a_complete_year():
    roster = pd.DataFrame({'station_id': ['001'], 'series_id': ['chosen']})
    val = {'interval_type': 'calendar_year', 'approval_status': 'approved',
           'start_date': '2024-01-02', 'end_date': '2024-12-31', 'sample_count': 366}
    series = {'parent_time_series_id': 'chosen', 'parent_statistic_id': '00003', 'values': [val]}
    doc = {'features': [{'properties': {'monitoring_location_id': 'USGS-001', 'data': [series]}}]}
    result = audit.extract_year(doc, roster, 2024)
    assert result.loc[0, 'expected_days'] == 366
    assert not bool(result.loc[0, 'count_complete'])


def test_missing_new_year_remains_unknown_only_when_it_could_change_eligibility():
    base = pd.DataFrame({'station_id': ['a', 'b', 'c', 'd', 'e'],
                         'n_count_complete_years': [0, 3, 3, 2, 4]})
    new = pd.DataFrame({'station_id': ['c'], 'approved_daily_count': [365], 'count_complete': [True]})
    result = audit.combine_2025(base, new).set_index('station_id')
    assert not bool(result.loc['a', 'extended_count_pass'])
    assert pd.isna(result.loc['b', 'extended_count_pass'])
    assert bool(result.loc['c', 'extended_count_pass'])
    assert not bool(result.loc['d', 'extended_count_pass'])
    assert bool(result.loc['e', 'extended_count_pass'])


def test_frozen_counts_reject_provider_revision_without_overwriting(tmp_path):
    path = tmp_path / 'counts.csv'
    receipt = pd.DataFrame({'station_id': ['001'], 'year': [2025], 'approved_daily_count': [365],
                            'expected_days': [365], 'interval_full_year': [True], 'count_complete': [True]})
    audit.write_frozen_counts(path, receipt)
    audit.write_frozen_counts(path, receipt.copy())
    changed = receipt.copy()
    changed.loc[0, 'approved_daily_count'] = 364
    with pytest.raises(RuntimeError, match='Frozen count receipt changed'):
        audit.write_frozen_counts(path, changed)
    assert pd.read_csv(path).loc[0, 'approved_daily_count'] == 365
