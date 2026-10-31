from pathlib import Path
import importlib
import json
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
N = importlib.import_module("411_wrr_usgs_network_intake")
SETTINGS = json.loads(N.CONFIG.read_text())


def feature(number="01234567", comid=100, coordinate=(-75., 40.)):
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "id": "USGS-" + number,
             "properties": {"identifier": "USGS-" + number, "source": "nwissite", "comid": comid, "reachcode": "01020304000123"},
             "geometry": {"type": "Point", "coordinates": list(coordinate)}}]}


def test_network_feature_requires_exact_identity_reach_and_coordinate():
    record = N.feature_metadata(feature(), "01234567", [[-75., 40.]], 250)
    assert record["comid"] == 100 and record["coordinate_distance_m"] < .1
    with pytest.raises(ValueError, match="identity"):
        N.feature_metadata(feature(), "87654321", [[-75., 40.]], 250)
    with pytest.raises(ValueError, match="tolerance"):
        N.feature_metadata(feature(), "01234567", [[-80., 40.]], 250)
    with pytest.raises(ValueError, match="reach"):
        N.feature_metadata(feature(comid=0), "01234567", [[-75., 40.]], 250)


def test_navigation_metadata_never_treats_truncation_or_other_identity_as_disjoint():
    assert N.navigation_identifiers(feature()) == ["01234567"]
    payload = feature()
    payload["links"] = [{"rel": "next"}]
    with pytest.raises(ValueError, match="Incomplete"):
        N.navigation_identifiers(payload)
    payload = feature()
    payload["features"][0]["properties"]["identifier"] = "malformed-identity"
    with pytest.raises(ValueError, match="identity"):
        N.navigation_identifiers(payload)


def test_other_agency_NWIS_identifiers_are_retained_without_becoming_USGS_aliases(tmp_path, monkeypatch):
    monkeypatch.setattr(N, "RAW", tmp_path)
    payload = feature()
    other = feature()["features"][0]
    other["properties"]["identifier"] = "USCE-01234567"
    payload["features"].append(other)
    def request(station, mode, settings):
        return (feature() if mode == "feature" else payload), {"path": "test"}
    monkeypatch.setattr(N, "request_metadata", request)
    result = N.run_job({"station": "01234567", "kind": "candidate", "locations": [[-75., 40.]]}, SETTINGS)
    assert result["status"] == "complete"
    assert result["upstream_station_ids"] == ["01234567"]
    assert result["other_agency_indexed_identifiers"]["UT"] == ["USCE-01234567"]
    assert not result["new_temperature_values_opened"]


def test_prior_connections_propagate_through_all_candidates_without_removing_rows():
    candidates = pd.DataFrame({"station_id": ["00000001", "00000002", "00000003"]})
    results = {
        "00000001": {"kind": "candidate", "status": "complete", "comid": 1, "upstream_station_ids": [], "downstream_station_ids": ["00000002"]},
        "00000002": {"kind": "candidate", "status": "complete", "comid": 2, "upstream_station_ids": ["99999999"], "downstream_station_ids": []},
    }
    scope = N.connection_scope(candidates, results, {"99999999"}).set_index("station_id")
    assert len(scope) == 3
    assert scope.loc["00000001", "provisional_network_index_component"] == scope.loc["00000002", "provisional_network_index_component"]
    assert scope.loc[["00000001", "00000002"], "component_has_prior_connection_screen"].all()
    assert scope.loc["00000003", "provisional_network_index_component"] == ""
    assert not scope.independent_component_verified.any() and not scope.new_reference_eligible.any()


def test_shared_reach_and_partial_checks_cannot_create_independent_singletons():
    candidates = pd.DataFrame({"station_id": ["00000001", "00000002"]})
    results = {
        "00000001": {"kind": "candidate", "status": "complete", "comid": 5},
        "00000002": {"kind": "candidate", "status": "pending_http_500", "comid": 5},
        "99999999": {"kind": "prior", "status": "complete", "comid": 5},
    }
    scope = N.connection_scope(candidates, results, {"99999999"})
    assert scope.provisional_network_index_component.nunique() == 1
    assert scope.same_index_comid_as_prior.all() and not scope.all_component_candidate_checks_complete.any()


def test_unindexed_candidates_stay_pending_without_a_component_count():
    candidates = pd.DataFrame({"station_id": ["00000001"]})
    result = {"00000001": {"kind": "candidate", "status": "not_indexed"}}
    scope = N.connection_scope(candidates, result, set())
    assert scope.network_status.iloc[0] == "not_indexed"
    assert scope.provisional_network_index_component.iloc[0] == ""


def test_access_denial_stops_new_requests_and_is_not_an_empty_navigation(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(N, "RAW", tmp_path)
    monkeypatch.setattr(N.C, "ROOT", tmp_path)
    monkeypatch.setattr(N.requests, "get", lambda *a, **k: SimpleNamespace(ok=False, status_code=403, text="Access denied", headers={}))
    N.STOP.clear()
    try:
        with pytest.raises(N.MetadataRequestFailure) as failure:
            N.request_metadata("01234567", "feature", SETTINGS)
        assert failure.value.status == "pending_http_403" and N.STOP.is_set()
        with pytest.raises(N.MetadataRequestFailure) as stopped:
            N.request_metadata("87654321", "feature", SETTINGS)
        assert stopped.value.status == "pending_service_stop"
        assert not (tmp_path / "feature/87654321.json").exists()
    finally:
        N.STOP.clear()


def test_transport_failure_remains_pending_and_keeps_the_exact_request(tmp_path, monkeypatch):
    monkeypatch.setattr(N, "RAW", tmp_path)
    monkeypatch.setattr(N.C, "ROOT", tmp_path)
    def fail(*args, **kwargs):
        raise N.requests.Timeout("observed timeout")
    monkeypatch.setattr(N.requests, "get", fail)
    N.STOP.clear()
    with pytest.raises(N.MetadataRequestFailure) as failure:
        N.request_metadata("01234567", "feature", SETTINGS)
    assert failure.value.status == "pending_transport" and not N.STOP.is_set()
    record = json.loads(failure.value.source.read_text())
    assert record["parameters"] == {"f": "json"} and not record["temperature_values_requested"]
