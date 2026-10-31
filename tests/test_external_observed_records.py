"""The external fact check must use real gaps and approved raw references."""

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "external_observed_records_test", ROOT / "scripts/525_external_observed_records.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def row(last=1991):
    return {
        "station_id": "00000001",
        "monitoring_location_name": "Test River",
        "hydrologic_unit_code": "13010001",
        "first_full_year": 1990,
        "last_full_year": last,
    }


def test_an_approved_observed_window_can_disprove_the_complete_only_record():
    dates = pd.date_range("1990-01-01", "1991-12-31")
    raw = pd.Series(np.nan, index=dates)
    raw.loc["1990"] = 10.0
    window = pd.date_range("1991-07-01", periods=30)
    raw.loc[window] = 20 + np.sin(np.arange(30))
    references, bounds, found = MODULE.observed_witnesses(row(), raw, raw)
    assert len(references) == 1 and len(bounds) == len(found) == 1
    assert found[0]["n_absent_or_unapproved"] > 0
    assert found[0]["window_mean"] > found[0]["maximum_raw_complete_H30"]
    assert len(found[0]["approved_window_values"].split(";")) == 30


def test_heuristic_censoring_cannot_create_a_false_reference_or_a_false_gap():
    dates = pd.date_range("1990-01-01", "1992-12-31")
    raw = pd.Series(np.nan, index=dates)
    raw.loc["1990"] = 10.0
    raw.loc["1991"] = 25.0
    window = pd.date_range("1992-07-01", periods=30)
    raw.loc[window] = 20 + np.sin(np.arange(30))
    cleaned = raw.copy()
    cleaned.loc["1991"] = np.nan
    cleaned.loc[window] = (
        40.0  # even transformed candidate values cannot establish a raw observation fact
    )
    references, _, found = MODULE.observed_witnesses(row(last=1992), raw, cleaned)
    assert len(references) == 2 and max(value for _, value in references) == 25.0
    assert found == []


def test_conflicting_or_unapproved_reported_values_are_not_reference_values():
    records = [
        {"time": "2000-01-01", "value": 12.0, "approval_status": "Approved"},
        {"time": "2000-01-01", "value": 13.0, "approval_status": "Approved"},
        {"time": "2000-01-02", "value": 15.0, "approval_status": "Provisional"},
        {"time": "2000-01-03", "value": 16.0, "approval_status": "Approved"},
    ]
    values = MODULE.approved_series(records, "America/Denver")
    assert values.loc["2000-01-01":"2000-01-02"].isna().all()
    assert values.loc["2000-01-03"] == 16.0
