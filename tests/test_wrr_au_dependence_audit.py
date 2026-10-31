from pathlib import Path
import importlib
import json
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
A = importlib.import_module("408_wrr_au_dependence_audit")


def test_shared_ungauged_upstream_bifurcation_cannot_make_two_independent_units():
    edges = np.array([[1, 2], [1, 3], [2, -1], [3, -1], [8, -1]])
    blocks, pending, _ = A.hydrologic_blocks(edges, {"left": 2, "right": 3, "other": 8})
    assert blocks["left"] == blocks["right"]
    assert blocks["left"] != blocks["other"]
    assert not pending


def test_common_ungauged_downstream_node_is_conservatively_one_block():
    edges = np.array([[1, 3], [2, 3], [3, 0], [4, -1]])
    blocks, _, _ = A.hydrologic_blocks(edges, {"a": 1, "b": 2, "c": 4})
    assert blocks["a"] == blocks["b"] != blocks["c"]


def test_sentinel_outlets_and_absent_nodes_cannot_invent_connectivity_or_units():
    edges = np.array([[1, 0], [2, 0], [3, -1], [4, -1]])
    blocks, pending, stats = A.hydrologic_blocks(edges, {"a": 1, "b": 2, "c": 3, "d": 4, "unknown": 9})
    assert len(set(blocks.values())) == 4
    assert pending == {"unknown"} and "unknown" not in blocks
    assert stats["nonpositive_endpoint_rows_excluded_from_connections"] == 4


def test_cycles_aliases_and_row_order_preserve_the_same_component_identity():
    edges = np.array([[5, 6], [6, 5], [6, 9], [9, 0], [8, 0]])
    anchors = {"a": 5, "alias": 5, "b": 9, "outside": 8}
    first = A.hydrologic_blocks(edges, anchors)[0]
    assert first == A.hydrologic_blocks(edges[::-1], dict(reversed(list(anchors.items()))))[0]
    assert first["a"] == first["alias"] == first["b"] == "hydrologic_5"
    assert first["outside"] != first["a"]


def test_no_edges_keeps_every_anchor_pending_instead_of_certifying_singletons():
    blocks, pending, stats = A.hydrologic_blocks(np.empty((0, 2), dtype=int), {"unknown": 10})
    assert blocks == {} and pending == {"unknown"}
    assert stats["all_network_weak_components"] == 0


@pytest.mark.parametrize("edges,anchors", [
    (np.array([[1.0, 2.5]]), {"a": 1}),
    (np.array([[1, 2]]), {"a": 0}),
    (np.array([[1, 2]]), {"a": 1.5}),
    (np.array([1, 2]), {"a": 1}),
])
def test_unverified_node_identifiers_are_rejected(edges, anchors):
    with pytest.raises(ValueError):
        A.hydrologic_blocks(edges, anchors)


def test_conflict_reporting_preserves_roles_and_never_picks_a_favorable_subset():
    frame = pd.DataFrame({"station_id": ["a", "b", "c", "d"],
                          "first_wave_role": ["development", "test", "pending_metadata", "calibration"],
                          "hydrologic_block": ["river", "river", "river", ""]})
    original = frame.copy(deep=True)
    summary = A.role_block_summary(frame)
    pd.testing.assert_frame_equal(frame, original)
    assert len(summary) == 1 and summary.cross_role_screen.all()
    assert summary.original_roles.iloc[0] == "development;test"
    assert summary.members.iloc[0] == "a;b;c"


def test_cached_topology_requires_complete_unique_object_identifiers(tmp_path, monkeypatch):
    monkeypatch.setattr(A.C, "ROOT", tmp_path)
    folder = tmp_path / "downstream"
    folder.mkdir()
    path = folder / "objects_0000001.json"
    rows = [{"attributes": {"objectid": 1, "from_id": 1, "to_id": 2}},
            {"attributes": {"objectid": 1, "from_id": 2, "to_id": 0}}]
    path.write_text(json.dumps({"features": rows}))
    source = {"sources": [{"path": "downstream/objects_0000001.json"}], "network_edges": 2}
    with pytest.raises(RuntimeError, match="unique object-ID"):
        A.load_network(source)
    rows[1]["attributes"]["objectid"] = 2
    path.write_text(json.dumps({"features": rows}))
    assert A.load_network(source).tolist() == [[1, 2], [2, 0]]
    source["network_edges"] = 3
    with pytest.raises(RuntimeError, match="count"):
        A.load_network(source)


def test_truncated_topology_does_not_become_an_independence_result(tmp_path, monkeypatch):
    monkeypatch.setattr(A.C, "ROOT", tmp_path)
    folder = tmp_path / "downstream"
    folder.mkdir()
    path = folder / "objects_0000001.json"
    path.write_text(json.dumps({"features": [], "exceededTransferLimit": True}))
    source = {"sources": [{"path": "downstream/objects_0000001.json"}], "network_edges": 0}
    with pytest.raises(RuntimeError, match="truncated"):
        A.load_network(source)
