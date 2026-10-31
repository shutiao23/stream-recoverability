import importlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
E=importlib.import_module("425_wrr_au_catchment_scope_extension")


def feature(left,right,node=123):
    return {"type":"Feature","properties":{"hydroid":left+10,"netnodeid":node},"geometry":{"type":"Polygon","coordinates":[[[left,0],[right,0],[right,1],[left,1],[left,0]]]}}


def test_shared_boundary_keeps_every_covering_catchment_and_unindexed_node():
    records=E.validate_payload({"type":"FeatureCollection","features":[feature(0,1),feature(1,2,None)]},2000)
    selected=E.covering_records(records,1,.5)
    assert len(selected)==2 and selected[1]["netnodeid"] is None
    assert E.covering_records(records,3,.5)==[]


def test_disagreeing_original_and_proxy_blocks_merge_all_potential_dependence():
    result=E.combined_components({"old":{"A","B"},"new":{"B"},"other":{"C"},"unknown":set()})
    assert result["old"]==result["new"] and result["old"]!=result["other"]
    assert result["unknown"]==""


def test_truncation_bad_identity_or_measurement_fields_are_not_empty_geography():
    for payload in [{"type":"FeatureCollection","features":[],"exceededTransferLimit":True},
                    {"type":"FeatureCollection","features":[feature(0,1)],"links":[{"rel":"next"}]}]:
        with pytest.raises(ValueError,match="truncated"):E.validate_payload(payload,2000)
    payload={"type":"FeatureCollection","features":[feature(0,1)]};payload["features"][0]["properties"]["value"]=10
    with pytest.raises(ValueError,match="non-metadata"):E.validate_payload(payload,2000)


def test_native_point_metadata_keeps_unindexed_nodes_and_rejects_truncation():
    payload={"features":[{"attributes":{"hydroid":12,"netnodeid":None,"hassegment":2}}]}
    assert E.point_records(payload)[0]["netnodeid"] is None
    assert E.point_records({"features":[]})==[]
    with pytest.raises(ValueError,match="truncated"):E.point_records({**payload,"exceededTransferLimit":True})
    with pytest.raises(ValueError,match="Unverified"):E.point_records({"features":[{"attributes":{"hydroid":True}}]})
