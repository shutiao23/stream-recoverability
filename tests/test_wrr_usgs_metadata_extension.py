import importlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
E=importlib.import_module("424_wrr_usgs_metadata_extension")


def feature(comid=None, point=(-75.,40.), number="01234567"):
    return {"type":"FeatureCollection","features":[{"properties":{"identifier":"USGS-"+number,"source":"nwissite","comid":comid},"geometry":{"type":"Point","coordinates":list(point)}}]}


def test_null_reach_is_explicit_after_exact_identity_and_location_check():
    result=E.classify_feature(feature(),"01234567",[[-75.,40.]])
    assert result["status"]=="identity_location_verified_reach_unindexed"
    assert result["reported_comid"] is None and "comid" not in result
    assert result["source_coordinate_within_original_tolerance"]


def test_wrong_coordinates_do_not_pass_because_reach_is_null_or_positive():
    for comid in [None,123]:
        result=E.classify_feature(feature(comid),"01234567",[[-76.,40.]])
        assert result["status"]=="pending_coordinate_mismatch"
        assert not result["source_coordinate_within_original_tolerance"]


def test_unverified_reach_types_are_not_coerced_or_guessed():
    for value in ["123",True,0,-1]:
        assert E.classify_feature(feature(value),"01234567",[[-75.,40.]])["status"]=="pending_reach_schema"
    assert E.classify_feature(feature(123),"01234567",[[-75.,40.]])["comid"]==123


def test_identity_or_measurement_payload_cannot_be_source_metadata():
    with pytest.raises(ValueError,match="identity"):
        E.classify_feature(feature(number="87654321"),"01234567",[[-75.,40.]])
    payload=feature(123);payload["features"][0]["properties"]["value"]=10.
    with pytest.raises(ValueError,match="non-metadata"):
        E.classify_feature(payload,"01234567",[[-75.,40.]])
