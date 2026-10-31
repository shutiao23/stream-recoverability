import importlib.util
from pathlib import Path

import pandas as pd
import pytest


spec = importlib.util.spec_from_file_location(
    'poudre_preflight', Path(__file__).resolve().parents[1] / 'scripts/587_poudre_metadata_preflight.py'
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_metadata_period_is_only_an_upper_bound_and_respects_utc_edges():
    assert audit.metadata_possible_years('2020-01-01T00:00:00Z', '2024-12-31T23:45:00Z') == [2020, 2021, 2022, 2023, 2024]
    assert audit.metadata_possible_years('2020-01-01T00:15:00Z', '2024-12-31T23:44:59Z') == [2021, 2022, 2023]
    assert audit.metadata_possible_years(None, '2025-01-01T00:00:00Z') == []


def test_logged_gaps_pair_removal_and_next_deployment_without_implying_sensor_truth():
    rows = pd.DataFrame({'site': ['a'] * 4,
                         'timestamp': pd.to_datetime(['2022-01-01', '2022-03-01', '2022-04-01', '2022-04-01T12:00'], utc=True, format='mixed'),
                         'action': [1., 0., 1., 0.]})
    gaps = audit.logged_gaps(rows)
    assert len(gaps) == 1 and gaps.loc[0, 'site'] == 'a'
    assert gaps.loc[0, 'days_between_visits'] == 59.


def test_conflicting_actions_at_same_timestamp_are_rejected():
    events = pd.DataFrame({'site': ['a', 'a'],
                           'timestamp': pd.to_datetime(['2022-01-01', '2022-01-01'], utc=True),
                           'action': [1., 0.]})
    with pytest.raises(ValueError, match='ambiguous'):
        audit.logged_gaps(events)
