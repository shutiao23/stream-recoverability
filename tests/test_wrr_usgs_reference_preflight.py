from pathlib import Path
import importlib
import json
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
P = importlib.import_module("410_wrr_usgs_reference_preflight")
SETTINGS = json.loads(P.CONFIG.read_text())


def feature(station="01234567", identifier="series", **overrides):
    properties = {
        "id": identifier, "monitoring_location_id": "USGS-" + station, "monitoring_location_number": station,
        "monitoring_location_name": "Test River", "parameter_code": "00010", "statistic_id": "00003",
        "computation_period_identifier": "Daily", "computation_identifier": "Mean", "data_type": "Daily values",
        "primary": "Primary", "unit_of_measure": "degC", "agency_code": "USGS", "country_code": "US",
        "site_type_code": "ST", "hydrologic_unit_code": "010203040506", "state_name": "Test State",
        "begin": "2010-01-01T05:00:00Z", "end": "2024-12-31T05:00:00Z", "parent_time_series_id": "native",
    }
    properties.update(overrides)
    return {"type": "Feature", "id": identifier, "properties": properties,
            "geometry": {"type": "Point", "coordinates": [-75., 40.]}}


def collections(*features):
    return {"type": "FeatureCollection", "features": list(features), "links": []}


def scope(*features, old_numbers=frozenset(), old_contexts=frozenset(), old_locations=None):
    old_locations = pd.DataFrame([{"site": "99999999", "longitude": -120., "latitude": 20.}]) if old_locations is None else old_locations
    return P.series_scope(collections(*features), collections(*features), SETTINGS, old_numbers, old_contexts, old_locations)


def test_provider_prefix_preserves_leading_zeros_and_rejects_guessed_aliases():
    assert P.station_number("USGS-01234567") == "01234567"
    assert P.station_number("012345678901234") == "012345678901234"
    for value in ("1234567", "01234567A", "12345678.0", "FOEN-01234567"):
        with pytest.raises(ValueError):
            P.station_number(value)


def test_huc_prefix_is_reported_without_inventing_lost_zeroes():
    assert P.huc8("010203040506") == P.huc8("01020304") == "01020304"
    for value in (None, "nan", "1234567", "00000000", "01020304A"):
        assert P.huc8(value) == ""


def test_necessary_date_bounds_keep_quality_and_observed_sampling_unverified():
    assert P.interval_can_support("2021-01-01T08:00Z", "2024-12-31T08:00Z", 2024)
    assert not P.interval_can_support("2021-02-01", "2024-12-31", 2024)
    assert not P.interval_can_support("2021-01-01", "2024-11-30", 2024)
    assert not P.interval_can_support("invalid", "2024-12-31", 2024)
    frame = scope(feature())
    assert frame.initial_metadata_candidate.all()
    assert not frame.reference_quality_qualified.any() and not frame.native_daily_support_verified.any()
    assert not frame.new_role_assigned.any() and not frame.new_temperature_value_access_allowed.any()


def test_exact_prior_records_and_nearby_station_aliases_remain_excluded():
    assert not scope(feature(), old_numbers={"01234567"}).initial_metadata_candidate.any()
    nearby = pd.DataFrame([{"site": "08765432", "longitude": -75., "latitude": 40.0001}])
    frame = scope(feature(), old_locations=nearby)
    assert not frame.initial_metadata_candidate.any()
    assert frame.previous_stations_within_250m.iloc[0] == "08765432"


def test_huc_overlap_stays_a_review_flag_and_never_claims_disjointness():
    frame = scope(feature(), old_contexts={"01020304"})
    assert frame.same_HUC8_as_prior_record.all()
    assert frame.initial_metadata_candidate.all()
    assert frame.scope_status.str.contains("pending_network").all()
    assert not frame.new_prediction_errors_opened.any()


def test_lake_groundwater_and_multiple_channels_do_not_become_river_references():
    for code in ("GW", "LK", "ST-CA", "ST-DCH", "ES"):
        assert not scope(feature(site_type_code=code)).initial_metadata_candidate.any()
    frame = scope(feature(identifier="one"), feature(identifier="two"))
    assert len(frame) == 2 and not frame.initial_metadata_candidate.any()
    assert frame.scope_status.str.contains("multiple_primary").all()


def test_other_agency_catalog_records_remain_visible_but_never_become_USGS_candidates():
    point = feature("331949112371701", agency_code="AZ014", monitoring_location_id="AZ014-331949112371701")
    frame = scope(point)
    assert len(frame) == 1 and frame.station_id.iloc[0] == "AZ014-331949112371701"
    assert not frame.initial_metadata_candidate.any()
    assert frame.scope_status.str.contains("outside_declared_agency").all()


def test_unverified_geometry_and_engineered_names_remain_pending():
    point = feature()
    point["geometry"] = None
    assert not scope(point).initial_metadata_candidate.any()
    assert not scope(feature(monitoring_location_name="Canal outfall")).initial_metadata_candidate.any()


def test_filter_mismatch_and_missing_location_metadata_fail_loudly():
    for override in ({"unit_of_measure": "degF"}, {"statistic_id": "00001"}, {"data_type": "Continuous values"}):
        with pytest.raises(ValueError):
            scope(feature(**override))
    with pytest.raises(RuntimeError, match="lack combined"):
        P.series_scope(collections(feature()), collections(), SETTINGS, set(), set(), pd.DataFrame())


def test_cached_national_catalog_must_be_complete_and_keep_its_retrieval_recipe(tmp_path):
    path = tmp_path / "catalog.json"
    endpoint = P.BASE + "/time-series-metadata/items"
    path.write_text(json.dumps(collections(feature())))
    ledger = {"endpoint": endpoint, "parameters": {"f": "json"}}
    path.with_suffix(".request.json").write_text(json.dumps(ledger))
    assert len(P.cached_collection(path, endpoint, {"f": "json"})["features"]) == 1
    with pytest.raises(RuntimeError, match="recipe"):
        P.cached_collection(path, endpoint, {"f": "geojson"})
    obj = collections(feature())
    obj["links"] = [{"rel": "next", "href": "next-page"}]
    path.write_text(json.dumps(obj))
    with pytest.raises(RuntimeError, match="incomplete"):
        P.cached_collection(path, endpoint, {"f": "json"})


def test_observation_endpoints_cannot_be_used_by_the_metadata_preflight(tmp_path):
    with pytest.raises(ValueError, match="metadata endpoints"):
        P.cached_collection(tmp_path / "forbidden.json", P.BASE + "/daily/items", {})
