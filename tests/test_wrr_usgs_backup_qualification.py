from pathlib import Path
import importlib
import json
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
U = importlib.import_module("395_wrr_usgs_backup_qualification")
N = importlib.import_module("396_wrr_usgs_named_instruments")


@pytest.mark.parametrize("daylight,standard,utc_hour", [("PDT", "PST", 8), ("EDT", "EST", 5), ("CDT", "CST", 6)])
def test_explicit_dst_offsets_preserve_two_distinct_fall_back_observations(daylight, standard, utc_hour):
    frame = pd.DataFrame({"datetime": ["2024-11-03 01:30", "2024-11-03 01:30"],
                          "tz_cd": [daylight, standard]})
    times = U.native_times(frame)
    assert times.iloc[0] == pd.Timestamp(f"2024-11-03 {utc_hour:02d}:30Z")
    assert times.iloc[1] == pd.Timestamp(f"2024-11-03 {utc_hour + 1:02d}:30Z")
    assert times.nunique() == 2


def test_unknown_offset_cannot_silently_assign_wrong_utc_day():
    frame = pd.DataFrame({"datetime": ["2024-01-01 23:30"], "tz_cd": ["XX"]})
    with pytest.raises(ValueError, match="Unrecognised"):
        U.native_times(frame)


def test_approved_estimated_or_ice_affected_temperature_is_not_reference_truth():
    frame = pd.DataFrame({"datetime": ["2024-01-01 12:00"] * 7,
                          "tz_cd": ["AKST"] * 7,
                          "a": [10, 11, 12, 13, 14, 15, 16],
                          "a_cd": ["A", "A,e", "A,Ice", "P", "P,e", "", None]})
    main = U.observation_frame(frame, "a")
    assert main.WaterTemperature_Celsius.notna().tolist() == [True, False, False, False, False, False, False]
    coverage = U.observation_frame(frame, "a", approved_only=False)
    assert coverage.WaterTemperature_Celsius.notna().tolist() == [True, False, False, True, False, False, False]


def test_missing_channel_status_cannot_be_interpreted_as_approved():
    frame = pd.DataFrame({"datetime": ["2024-01-01 12:00"], "tz_cd": ["PST"], "a": [10]})
    with pytest.raises(ValueError, match="Required native channel"):
        U.observation_frame(frame, "a")


def test_ogc_serialization_keeps_qualifiers_and_zero_values():
    properties = {"time_series_id": "sensor", "monitoring_location_id": "USGS-12345678",
                  "parameter_code": "00010", "unit_of_measure": "degC", "approval_status": "Approved",
                  "qualifier": ["e"], "time": "2020-01-01T00:00:00Z", "value": "0.0"}
    rows = N.ogc_native_rows([{"properties": properties}], "12345678", {"sensor"})
    assert rows[0]["sensor_00010"] == "0.0"
    assert rows[0]["sensor_00010_cd"] == "A,e"
    assert U.observation_frame(pd.DataFrame(rows), "sensor_00010").WaterTemperature_Celsius.isna().all()
    properties["qualifier"] = None
    observed = pd.DataFrame(N.ogc_native_rows([{"properties": properties}], "12345678", {"sensor"}))
    assert U.observation_frame(observed, "sensor_00010").WaterTemperature_Celsius.iloc[0] == 0


def test_ogc_wrong_sensor_or_units_cannot_enter_reference():
    properties = {"time_series_id": "unregistered", "monitoring_location_id": "USGS-12345678",
                  "parameter_code": "00010", "unit_of_measure": "degF", "approval_status": "Approved",
                  "time": "2020-01-01T00:00:00Z", "value": "10"}
    with pytest.raises(ValueError, match="selected temperature channels"):
        N.ogc_native_rows([{"properties": properties}], "12345678", {"sensor"})


def test_unacquired_candidate_remains_pending_in_original_denominator(tmp_path, monkeypatch):
    output = tmp_path / "results"
    output.mkdir()
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"candidates": [{"site": "12345678", "name": "Pending stream", "candidate_years": [2024]}],
                                 "time_zone": "project UTC"}))
    acquisition = output / "partial.json"
    acquisition.write_text(json.dumps({"records": []}))
    monkeypatch.setattr(U, "CONFIG", config)
    monkeypatch.setattr(U, "OUT", output)
    U.qualify(acquisition_path=acquisition, allow_pending=True)
    row = pd.read_csv(output / "usgs_pair_year_qualification.csv").iloc[0]
    assert pd.isna(row.record_reference_eligible) and row.acquisition_pending
    summary = json.loads((output / "usgs_qualification_summary.json").read_text())
    assert summary["candidate_pair_years"] == 1
    assert summary["available_pair_years_evaluated"] == 0
    assert summary["pending_pair_years_not_evaluated"] == 1
