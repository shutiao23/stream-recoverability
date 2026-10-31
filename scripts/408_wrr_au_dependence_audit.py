#!/usr/bin/env python3
"""Conservatively screen all cached river connections before new evaluation.

This metadata-only extension includes shared upstream bifurcations and common
downstream nodes even where no candidate station was recruited. Original roles,
reference qualifications, models and primary-error access remain unchanged.
"""
from __future__ import annotations

import importlib
import json

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import yaml

import wrr_r3_common as C

G = importlib.import_module("406_wrr_au_network_feasibility")
N = importlib.import_module("399_wrr_neon_recruitment_feasibility")
OUT = G.OUT.parent / "au_dependence_audit"
CONFIG = C.ROOT / "configs/wrr_au_dependence_audit_20261021.json"


def hydrologic_blocks(edges, anchors):
    """Return deterministic weak-component IDs for verified station anchors.

    Nonpositive sentinel IDs must not merge separate river outlets. A positive
    node absent from the cached topology stays pending rather than becoming an
    independent singleton. Weak connectivity intentionally also merges separate
    tributaries; it is a conservative block definition, not a leakage test.
    """
    edges = np.asarray(edges)
    if edges.ndim != 2 or edges.shape[1] != 2 or edges.dtype.kind not in "iu":
        raise ValueError("Expected integer from/to physical-node connections")
    if any(not isinstance(node, (int, np.integer)) or node <= 0 for node in anchors.values()):
        raise ValueError("Station anchors must be verified positive physical-node IDs")
    nodes = np.unique(edges[edges > 0])
    physical = edges[(edges > 0).all(axis=1)]
    indices = np.searchsorted(nodes, physical)
    graph = coo_matrix((np.ones(len(physical), dtype=bool), (indices[:, 0], indices[:, 1])),
                       shape=(len(nodes), len(nodes))).tocsr()
    count, labels = connected_components(graph, directed=False)
    smallest = np.full(count, np.iinfo(np.int64).max, dtype=np.int64)
    np.minimum.at(smallest, labels, nodes)
    blocks, missing = {}, set()
    for station, anchor in anchors.items():
        index = np.searchsorted(nodes, anchor)
        if index == len(nodes) or nodes[index] != anchor:
            missing.add(station)
        else:
            blocks[station] = f"hydrologic_{smallest[labels[index]]}"
    return blocks, missing, {
        "positive_physical_nodes": len(nodes),
        "positive_physical_connection_rows": len(physical),
        "nonpositive_endpoint_rows_excluded_from_connections": len(edges) - len(physical),
        "all_network_weak_components": int(count),
    }


def role_block_summary(frame, *, role_column="first_wave_role", block_column="hydrologic_block"):
    """Keep every original role; never choose which role wins a conflict."""
    resolved = frame.loc[frame[block_column].ne("")]
    rows = []
    for block, members in resolved.groupby(block_column, sort=True):
        roles = sorted(set(members[role_column]) - {"pending_metadata"})
        rows.append({
            "hydrologic_block": block, "stations": len(members),
            "original_roles": ";".join(roles), "original_role_count": len(roles),
            "cross_role_screen": len(roles) > 1,
            "members": ";".join(sorted(members.station_id.astype(str))),
        })
    return pd.DataFrame(rows, columns=["hydrologic_block", "stations", "original_roles",
                                       "original_role_count", "cross_role_screen", "members"])


def load_network(acquired):
    """Read only complete topology pages and validate their IDs."""
    pages, identifiers = [], []
    for item in acquired["sources"]:
        path = C.ROOT / item["path"]
        if path.parent.name != "downstream" or not path.name.startswith("objects_"):
            continue
        payload = json.loads(path.read_text())
        if payload.get("exceededTransferLimit"):
            raise RuntimeError("Cached network page is truncated")
        rows = [feature["attributes"] for feature in payload["features"]]
        if not all(isinstance(row[key], int) for row in rows for key in ("objectid", "from_id", "to_id")):
            raise ValueError("Network node identifiers are not explicit integers")
        pages.append(np.array([[row["from_id"], row["to_id"]] for row in rows], dtype=np.int64).reshape(-1, 2))
        identifiers.append(np.array([row["objectid"] for row in rows], dtype=np.int64))
    if not pages:
        raise RuntimeError("No cached physical topology pages")
    edges, ids = np.concatenate(pages), np.concatenate(identifiers)
    if len(edges) != acquired["network_edges"] or len(np.unique(ids)) != len(ids):
        raise RuntimeError("Topology count or unique object-ID coverage is incomplete")
    return edges


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    settings = json.loads(CONFIG.read_text())
    if settings["new_temperature_or_prediction_requests"] or settings["new_role_assignments"]:
        raise RuntimeError("This command is restricted to metadata auditing")
    inputs = {
        "parent_specification": C.ROOT / "configs/wrr_next_confirmation_20261021.yaml",
        "network_acquisition": G.OUT / "metadata_acquisition.json",
        "network_station_scope": G.OUT / "station_network_scope.csv",
        "original_roles": G.FIRST / "metadata_candidates_and_roles.csv",
        "original_reference_qualification": G.FIRST / "observed_reference_release.csv",
    }
    acquired = json.loads(inputs["network_acquisition"].read_text())
    edges = load_network(acquired)
    original = pd.read_csv(inputs["original_roles"], dtype={"station_id": str, "station_no": str})
    scope = pd.read_csv(inputs["network_station_scope"], dtype={"station_id": str, "station_no": str}).fillna("")
    if scope.station_id.duplicated().any() or set(scope.station_id) != set(original.station_id):
        raise RuntimeError("Network scope does not preserve every original metadata candidate")
    resolved = scope.loc[scope.network_metadata_status.eq("resolved")]
    nodes = pd.to_numeric(resolved.downstream_attachment_node, errors="raise")
    if not np.isfinite(nodes).all() or not np.equal(nodes, np.floor(nodes)).all():
        raise ValueError("Unverified or fractional physical-node attachment")
    anchors = dict(zip(resolved.station_id, nodes.astype(np.int64)))
    blocks, pending, network_stats = hydrologic_blocks(edges, anchors)
    scope["hydrologic_block"] = scope.station_id.map(blocks).fillna("")
    scope["hydrologic_screen_status"] = np.where(scope.hydrologic_block.ne(""), "resolved", scope.network_metadata_status)
    scope.loc[scope.station_id.isin(pending), "hydrologic_screen_status"] = "pending_node_absent_from_topology"
    scope["original_role_edited"] = False
    scope["primary_test_error_access_allowed"] = False
    scope.to_csv(OUT / "station_hydrologic_scope.csv", index=False)
    block_table = role_block_summary(scope)
    block_table.to_csv(OUT / "all_candidate_blocks.csv", index=False)

    references = pd.read_csv(inputs["original_reference_qualification"], dtype={"station_id": str})
    qualified = references.loc[references.observed_sampling_reference_eligible.eq(True)].copy()
    qualified = qualified.merge(scope[["station_id", "hydrologic_block", "hydrologic_screen_status"]],
                                on="station_id", how="left", validate="many_to_one")
    if qualified.hydrologic_screen_status.isna().any():
        raise RuntimeError("A qualified reference disappeared from the metadata scope")
    qualified.to_csv(OUT / "original_qualified_references_scope.csv", index=False)
    reference_members = qualified.drop_duplicates("station_id").rename(columns={"role": "first_wave_role"})
    reference_blocks = role_block_summary(reference_members)
    reference_blocks.to_csv(OUT / "qualified_reference_blocks.csv", index=False)
    specification = yaml.safe_load(inputs["parent_specification"].read_text())
    floor = N.ideal_group_floor(specification["selected_risk_cap"],
                               specification["joint_error_allocation"]["formal_calibration_per_method"])
    role_support = qualified.groupby("role").independence_group.nunique().to_dict()
    screened_support = qualified.loc[qualified.hydrologic_block.ne("")].groupby("role").hydrologic_block.nunique().to_dict()
    role_rows = []
    for role in ("development", "calibration", "test"):
        candidates = scope.loc[scope.first_wave_role.eq(role)]
        refs = qualified.loc[qualified.role.eq(role)]
        role_rows.append({
            "role": role,
            "original_qualified_station_years": len(refs),
            "original_qualified_polygon_components": int(role_support.get(role, 0)),
            "conservative_qualified_hydrologic_blocks": int(screened_support.get(role, 0)),
            "original_metadata_stations": len(candidates),
            "metadata_stations_with_hydrologic_scope": int(candidates.hydrologic_block.ne("").sum()),
            "qualified_stations_pending_topology": int(refs.loc[refs.hydrologic_block.eq(""), "station_id"].nunique()),
            "role_counts_may_share_the_same_block": True,
            "formal_primary_evaluation_ready": False,
        })
    pd.DataFrame(role_rows).to_csv(OUT / "role_support.csv", index=False)
    summary = {
        "status": "conservative_metadata_dependence_screen_not_new_confirmatory_units",
        "candidate_stations": len(scope), "stations_with_verified_physical_graph_attachment": len(blocks),
        "stations_pending_attachment_or_metadata": int(scope.hydrologic_block.eq("").sum()),
        "conservative_hydrologic_blocks_all_mapped_candidates": len(block_table),
        "all_candidate_blocks_spanning_original_roles": int(block_table.cross_role_screen.sum()),
        "original_qualified_reference_station_years": len(qualified),
        "original_qualified_reference_stations": qualified.station_id.nunique(),
        "original_qualified_components_by_role": role_support,
        "conservative_qualified_hydrologic_blocks_by_role": screened_support,
        "qualified_references_in_role_counts_can_share_blocks": True,
        "conservative_qualified_hydrologic_blocks_total": len(reference_blocks),
        "qualified_reference_blocks_spanning_original_roles": int(reference_blocks.cross_role_screen.sum()),
        "qualified_reference_stations_pending_topology": qualified.loc[qualified.hydrologic_block.eq(""), "station_id"].nunique(),
        "shared_upstream_bifurcations_and_ungauged_connections_accounted_for_in_cached_graph": True,
        "basin_connectivity_does_not_alone_prove_record_leakage": True,
        "basin_connectivity_does_not_prove_region_event_independence": True,
        "earlier_opened_record_exclusion_fully_verified": False,
        "region_event_dependence_verified": False,
        "necessary_ideal_one_threshold_calibration_group_floor": floor,
        "necessary_ideal_disjoint_calibration_plus_test_floor": 2 * floor,
        "ideal_floor_is_not_joint_power_or_recruitment_recommendation": True,
        "mapped_pool_alone_can_reach_ideal_disjoint_floor": len(block_table) >= 2 * floor,
        "unmapped_pool_feasibility": "pending_not_inferred_from_mapped_subset",
        "new_roles_assigned": False, "original_role_and_qualification_files_modified": False,
        "new_temperature_values_or_H30_prediction_errors_opened": False,
        "primary_test_error_access_allowed": False, "new_confirmation_completed": False,
        "network": network_stats,
    }
    C.write_json(OUT / "summary.json", summary)
    print(f"[408] {len(blocks)} mapped stations / {len(block_table)} conservative hydrologic blocks; "
          f"qualified role support={screened_support}; new outcomes remain sealed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
