import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


spec = importlib.util.spec_from_file_location(
    'nova_scotia_portal', Path(__file__).resolve().parents[1] / 'scripts/590_nova_scotia_portal_audit.py'
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_duplicate_timestamps_are_not_averaged_into_apparent_agreement():
    w = pd.DataFrame({'timestamp': pd.to_datetime(['2015-01-01 00:00', '2015-01-01 01:00',
            '2015-01-01 02:00', '2015-01-01 02:00', '2015-01-01 03:00']),
            'value': [1., 2., 3., 3., np.nan]})
    p = pd.DataFrame({'timestamp': pd.to_datetime(['2015-01-01 00:00', '2015-01-01 01:00',
            '2015-01-01 02:00', '2015-01-01 03:00', '2015-01-01 04:00']),
            'value': [1., 2.2, 3., np.nan, 5.]})
    result = audit.compare_series(w, p)
    assert result['workbook_duplicate_label_rows'] == 2
    assert result['shared_unique_labels'] == 3 and result['portal_only_unique_labels'] == 2
    assert result['numeric_equal'] == 1 and result['numeric_different'] == 1
    assert result['both_nonnumeric_or_missing'] == 1
    assert result['max_numeric_abs_difference_c'] == pytest.approx(.2)


def test_mismatched_missing_values_are_not_counted_as_numeric_agreement():
    t = pd.to_datetime(['2015-01-01 00:00', '2015-01-01 01:00'])
    w = pd.DataFrame({'timestamp': t, 'value': [1., np.nan]})
    p = pd.DataFrame({'timestamp': t, 'value': [np.nan, 2.]})
    result = audit.compare_series(w, p)
    assert result['shared_unique_labels'] == 2
    assert result['one_numeric_other_missing'] == 2
    assert result['both_numeric'] == 0 and result['max_numeric_abs_difference_c'] is None
