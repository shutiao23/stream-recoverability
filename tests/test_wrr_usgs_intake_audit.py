from pathlib import Path
import importlib
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
E = importlib.import_module("414_wrr_usgs_intake_audit")


def test_legacy_response_ids_do_not_come_from_guessed_request_padding_or_temperature_values(tmp_path):
    path = tmp_path / "response.rdb"
    path.write_text("# source metadata\nagency_cd\tsite_no\tvalue\nUSGS\t01234567\t9999\nUSGS\t08765432\t0\nUSGS\t01234567\tNaN\n")
    assert E.returned_RDB_identifiers(path) == {"01234567", "08765432"}


def test_additional_old_locations_preserve_nonconsecutive_base_rows_and_match_exact_ids():
    base = pd.DataFrame({"site": ["01234567"], "longitude": [-75.], "latitude": [40.]}, index=[2])
    features = [{"id": "USGS-08765432", "properties": {"agency_code": "USGS", "monitoring_location_number": "08765432"},
                 "geometry": {"type": "Point", "coordinates": [-76., 41.]}}]
    locations = E.additional_locations(base, features, {"01234567", "08765432"})
    assert set(locations.site) == {"01234567", "08765432"}


def test_old_cache_group_members_are_excluded_without_merging_all_unrequested_blank_groups():
    candidates = pd.DataFrame({"station_id": ["00000001", "00000002", "00000003", "00000004"]})
    cache = candidates.assign(expanded_prior_cache_contact=[True, False, True, False], effective_metadata_candidate=[False, True, False, True],
                              longitude=[-75., -76., -77., -78.], latitude=[40., 41., 42., 43.], new_role_assigned=False)
    results = {"00000001": {"kind": "candidate", "status": "complete", "comid": 1, "upstream_station_ids": [], "downstream_station_ids": ["00000002"]},
               "00000002": {"kind": "candidate", "status": "complete", "comid": 2}}
    locations = pd.DataFrame({"site": ["00000001", "00000003"], "longitude": [-75., -77.], "latitude": [40., 42.]})
    scope = E.effective_connection_scope(candidates, cache, results, {"00000001", "00000003"}, locations).set_index("station_id")
    assert scope.loc["00000002", "component_contains_old_cache_identity"]
    assert not scope.loc["00000002", "not_yet_excluded_metadata_candidate"]
    assert scope.loc["00000004", "not_yet_excluded_metadata_candidate"]
    assert scope.loc["00000004", "network_status"] == "not_yet_requested"
    assert not scope.reference_release_allowed.any()


def test_saved_navigation_indices_preserve_source_provenance_and_missing_indices():
    observations = {}
    def feature(station, reach, source="nwissite"):
        return {"properties": {"identifier": "USGS-" + station, "comid": reach, "source": source}}
    E.collect_prior_indices([feature("09999999", 15), feature("09999999", 15), feature("08888888", None),
                             feature("07777777", 18), feature("09999999", True)],
                            {"09999999", "08888888"}, "first", observations)
    E.collect_prior_indices([feature("09999999", 16)], {"09999999"}, "second", observations)
    assert set(observations) == {"09999999"}
    assert observations["09999999"] == {"reaches": {15, 16}, "sources": {"first", "second"}}


def test_prior_reach_seen_without_a_direct_prior_job_excludes_only_known_connections():
    candidates = pd.DataFrame({"station_id": ["00000001", "00000002"]})
    cache = candidates.assign(expanded_prior_cache_contact=False, effective_metadata_candidate=True,
                              longitude=[-75., -76.], latitude=[40., 41.], new_role_assigned=False)
    results = {"00000001": {"kind": "candidate", "status": "complete", "comid": 15},
               "00000002": {"kind": "candidate", "status": "complete", "comid": 20}}
    locations = pd.DataFrame({"site": ["09999999"], "longitude": [-120.], "latitude": [30.]})
    indices = {"09999999": {"reaches": {15}, "sources": {"a saved navigation"}}}
    frame = E.effective_connection_scope(candidates, cache, results, {"09999999"}, locations, indices).set_index("station_id")
    assert frame.loc["00000001", "navigation_seen_prior_reach_match"]
    assert not frame.loc["00000001", "not_yet_excluded_metadata_candidate"]
    assert frame.loc["00000002", "not_yet_excluded_metadata_candidate"]
    assert not frame.reference_release_allowed.any()
