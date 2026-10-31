import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


spec = importlib.util.spec_from_file_location(
    'nova_scotia_intake', Path(__file__).resolve().parents[1] / 'scripts/589_nova_scotia_verified_intake.py'
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_reported_hour_labels_can_form_complete_leap_year_without_proving_quality():
    times = pd.date_range('2012-01-01', '2013-01-01', freq='h', inclusive='left')
    records = pd.DataFrame({'timestamp': times, 'numeric_temperature': True})
    result = audit.label_completeness(records, 2012)
    assert result['days'] == 366 and result['complete_label_year']
    assert result['source_rows'] == 366 * 24


def test_missing_duplicate_off_hour_and_nonnumeric_records_disqualify_days():
    times = pd.date_range('2011-01-01', '2012-01-01', freq='h', inclusive='left')
    frame = pd.DataFrame({'timestamp': times, 'numeric_temperature': True})
    frame = frame.drop(index=0).copy()
    frame = pd.concat([frame, frame.loc[[24]]], ignore_index=True)
    frame.loc[frame.timestamp.eq(pd.Timestamp('2011-01-03')), 'numeric_temperature'] = False
    index = frame.timestamp.eq(pd.Timestamp('2011-01-04'))
    frame.loc[index, 'timestamp'] += pd.Timedelta(minutes=1)
    result = audit.label_completeness(frame, 2011)
    assert not result['complete_label_year'] and result['incomplete_label_days'] == 4
    assert result['duplicate_rows'] == 2 and result['off_hour_rows'] == 1
    assert result['nonnumeric_temperature_rows'] == 1


def test_aware_timestamps_do_not_silently_change_reported_time_basis():
    records = pd.DataFrame({'timestamp': pd.to_datetime(['2011-01-01T00:00:00Z'], utc=True),
                            'numeric_temperature': [True]})
    with pytest.raises(ValueError, match='unexpected timezone'):
        audit.label_completeness(records, 2011)
