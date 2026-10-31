from pathlib import Path
import importlib
import json
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
A = importlib.import_module("412_wrr_usgs_prior_cache_audit")


def test_ignored_native_cache_identity_needs_the_documented_temperature_schema(tmp_path):
    path = tmp_path / "data/public_rivers/nwis/01234567_2000-01-01_2024-12-31.csv"
    path.parent.mkdir(parents=True)
    path.write_text("site_id,date,temperature_c,qualifier\n")
    assert A.inspect_cache_identity(path, tmp_path) == [("01234567", "daily_temperature_cache_filename_and_schema", "T")]
    path.write_text("station_id,date,air_temperature\n")
    assert A.inspect_cache_identity(path, tmp_path) == []


def test_cached_daily_water_channel_path_includes_auxiliary_source_contact(tmp_path):
    path = tmp_path / "data_versions/old/raw/usgs/daily/01234567/F/page_0001.response.json"
    assert A.inspect_cache_identity(path, tmp_path) == [("01234567", "saved_daily_water_response_path", "F")]


def test_legacy_metadata_uses_only_saved_daily_requests_and_keeps_headers_private(tmp_path):
    path = tmp_path / "data_versions/old/raw/usgs_legacy/request/request.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"method": "GET", "url": "https://waterservices.usgs.gov/nwis/dv/?sites=01234567,08765432&parameterCd=00010", "headers": {"Authorization": "not emitted"}}))
    assert A.inspect_cache_identity(path, tmp_path) == []
    (path.parent / "response.rdb").write_text("not parsed")
    result = A.inspect_cache_identity(path, tmp_path)
    assert {row[0] for row in result} == {"01234567", "08765432"}
    assert all(row[2] == "T" for row in result) and "not emitted" not in str(result)
    path.write_text(json.dumps({"url": "https://waterservices.usgs.gov/nwis/site/?sites=01234567&parameterCd=00010"}))
    assert A.inspect_cache_identity(path, tmp_path) == []


def test_added_prior_contact_changes_only_effective_scope_preserving_all_original_rows():
    original = pd.DataFrame({"station_id": ["01234567", "08765432"], "initial_metadata_candidate": [True, True]})
    scope = A.effective_scope(original, {"01234567"})
    assert len(scope) == len(original) and original.initial_metadata_candidate.all()
    assert scope.effective_metadata_candidate.tolist() == [False, True]
    assert not scope.new_role_assigned.any() and not scope.new_temperature_value_access_allowed.any()


def test_new_metadata_and_unrelated_provider_catalogs_do_not_burn_temperature_candidates(tmp_path):
    path = tmp_path / "data/external/wrr_usgs_new_reference_20261021/nwis/01234567_2000-01-01_2024-12-31.csv"
    assert A.inspect_cache_identity(path, tmp_path) == []
    assert A.inspect_cache_identity(tmp_path / "data/usgs_state_temperature_catalog.rdb", tmp_path) == []


def test_location_metadata_append_cannot_overwrite_a_nonconsecutive_prior_index():
    old = pd.DataFrame({"site": ["01234567", "08765432"], "longitude": [-75., -76.], "latitude": [40., 41.]}, index=[0, 2])
    features = [{"properties": {"monitoring_location_id": "USGS-09999999", "agency_code": "USGS"},
                 "geometry": {"type": "Point", "coordinates": [-77., 42.]}}]
    locations = A.expanded_locations(old, features, {"01234567", "08765432", "09999999"})
    assert set(locations.site) == {"01234567", "08765432", "09999999"}
    assert len(locations) == 3
    assert locations.set_index("site").loc["08765432", "longitude"] == -76.


def test_complete_audit_preserves_the_prior_set(tmp_path, monkeypatch):
    out, preflight = tmp_path / "audit", tmp_path / "preflight"
    out.mkdir(); preflight.mkdir()
    settings = tmp_path / "settings.json"
    settings.write_text("{}")
    pd.DataFrame({"station_id": ["08765432", "09999999"]}).to_csv(preflight / "metadata_candidates.csv", index=False)
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    (metadata / "combined_daily_mean_temperature_metadata.json").write_text(json.dumps({"features": [
        {"properties": {"monitoring_location_id": "USGS-08765432", "agency_code": "USGS"},
         "geometry": {"type": "Point", "coordinates": [-76., 41.]}}]}))
    monkeypatch.setattr(A, "OUT", out)
    monkeypatch.setattr(A, "CONFIG", settings)
    monkeypatch.setattr(A.C, "ROOT", tmp_path)
    monkeypatch.setattr(A.P, "OUT", preflight)
    monkeypatch.setattr(A.P, "RAW", metadata)
    monkeypatch.setattr(A, "discover", lambda *a: (pd.DataFrame({"station_id": ["08765432"]}), {}))
    locations = pd.DataFrame({"site": ["01234567"], "longitude": [-75.], "latitude": [40.]}, index=[2])
    monkeypatch.setattr(A.P, "prior_records", lambda: ({"01234567"}, set(), locations))
    assert A.main() == 0
    summary = json.loads((out / "summary.json").read_text())
    assert summary["expanded_prior_station_numbers"] == 2
    assert summary["remaining_effective_metadata_candidates"] == 1
    assert summary["expanded_prior_identities_without_current_location"] == 0
