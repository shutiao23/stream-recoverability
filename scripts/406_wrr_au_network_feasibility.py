#!/usr/bin/env python3
"""Metadata-only network recruitment audit; no temperature requests or new roles."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import time

import numpy as np
import pandas as pd
from pyproj import Geod
import requests

import wrr_r3_common as C

RAW = C.ROOT / "data/external/wrr_au_confirmation_20261021/geofabric_network_metadata"
OUT = C.READY / "followup_20261021/au_network_recruitment"
FIRST = OUT.parent / "au_confirmation"
SERVICE = "https://hosting.wsapi.cloud.bom.gov.au/arcgis/rest/services/ahgf/Geofabric_V3x_All_Products/FeatureServer"


def source(path, layer, parameters):
    path.parent.mkdir(exist_ok=True, parents=True)
    ledger = path.with_suffix(".request.json")
    if path.exists() and ledger.exists():
        old = json.loads(ledger.read_text())
        if old["parameters"] != parameters:
            raise RuntimeError("Network metadata cache request changed")
        return json.loads(path.read_text())
    for attempt in range(2):
        response = requests.get(f"{SERVICE}/{layer}/query", params=parameters, timeout=90)
        if response.status_code not in {500, 502, 503, 504} or attempt:
            break
        time.sleep(1)
    response.raise_for_status()
    if len(response.content) > 32 << 20:
        raise RuntimeError("Single metadata response exceeds bounded intake size")
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(f"Public network metadata error: {payload['error']}")
    path.write_bytes(response.content)
    C.write_json(ledger, {"endpoint": f"{SERVICE}/{layer}/query", "parameters": parameters,
                         "bytes": len(response.content),
                         "acquired_at_utc": datetime.now(timezone.utc).isoformat(), "temperature_measurements_requested": False})
    return payload


def fetch():
    OUT.mkdir(exist_ok=True, parents=True)
    lookup = source(RAW / "gauging_node_lookup_v2.json", 36, {
        "f": "json", "where": "1=1", "outFields": "*", "returnGeometry": "false"})
    if lookup.get("exceededTransferLimit"):
        raise RuntimeError("Gauging station lookup is truncated")
    candidates = pd.read_csv(FIRST / "metadata_candidates_and_roles.csv", dtype={"station_id": str, "station_no": str})
    lookup_frame = pd.DataFrame([f["attributes"] for f in lookup["features"]])
    selected = candidates.merge(lookup_frame, left_on=["station_no", "DATA_OWNER"], right_on=["stationno", "dataownrid"], how="inner")
    ids = sorted({int(value) for value in selected.netnodeid})
    for start in range(0, len(ids), 200):
        source(RAW / "gauge_nodes" / f"batch_{start:05d}.json", 3, {
            "f": "json", "where": "hydroid IN (" + ",".join(map(str, ids[start:start + 200])) + ")",
            "outFields": "*", "returnGeometry": "true", "outSR": "4326"})
    count = source(RAW / "downstream_count.json", 38, {"f": "json", "where": "1=1", "returnCountOnly": "true"})["count"]
    maximum = source(RAW / "downstream_maximum.json", 38, {
        "f": "json", "where": "1=1", "outFields": "objectid", "returnGeometry": "false",
        "orderByFields": "objectid DESC", "resultRecordCount": "1"})["features"][0]["attributes"]["objectid"]
    starts = list(range(1, maximum + 1, 10000))
    def page(start):
        result = source(RAW / "downstream" / f"objects_{start:07d}.json", 38, {
            "f": "json", "where": f"objectid >= {start} AND objectid < {start + 10000}",
            "outFields": "objectid,from_id,to_id", "returnGeometry": "false", "resultRecordCount": "10000"})
        if result.get("exceededTransferLimit"):
            raise RuntimeError("A bounded network page is truncated")
        identifiers = [f["attributes"]["objectid"] for f in result["features"]]
        if len(set(identifiers)) != len(identifiers) or any(not start <= i < start + 10000 for i in identifiers):
            raise RuntimeError("Network page does not respect its unique object-ID interval")
        return len(result["features"])
    # A successful bounded page precedes two-worker batches. An access denial
    # terminates acquisition, rather than scheduling the remaining requests.
    total = page(starts[0])
    with ThreadPoolExecutor(max_workers=2) as executor:
        for index in range(1, len(starts), 2):
            total += sum(executor.map(page, starts[index:index + 2]))
            print(f"[406] {min(index + 2, len(starts))}/{len(starts)} topology pages; metadata only", flush=True)
    if total != count:
        raise RuntimeError("Network edge count differs from the provider snapshot")
    paths = [RAW / "gauging_node_lookup_v2.json", RAW / "downstream_count.json", RAW / "downstream_maximum.json",
             *sorted((RAW / "gauge_nodes").glob("*.json")), *sorted((RAW / "downstream").glob("objects_*.json"))]
    paths = [p for p in paths if not p.name.endswith(".request.json")]
    C.write_json(OUT / "metadata_acquisition.json", {
        "network_edges": total, "lookup_station_rows": len(lookup_frame), "queried_gauge_nodes": len(ids),
        "temperature_measurements_requested": False,
        "sources": [{"path": str(p.relative_to(C.ROOT)), "bytes": p.stat().st_size} for p in paths]})
    return 0


def downstream_station_links(anchors, adjacency):
    """Follow every route; stop at the next gauge because its own walk continues."""
    by_node = {}
    for station, node in anchors.items():
        by_node.setdefault(node, set()).add(station)
    links, unresolved = set(), set()
    for station, anchor in anchors.items():
        for other in by_node[anchor] - {station}:
            links.add(tuple(sorted((station, other))))
        stack, seen = list(adjacency.get(anchor, [])), {anchor}
        if anchor not in adjacency:
            unresolved.add(station)
        while stack:
            node = stack.pop()
            if node <= 0 or node in seen:
                continue
            seen.add(node)
            if node in by_node:
                for other in by_node[node] - {station}:
                    links.add(tuple(sorted((station, other))))
                continue
            if node not in adjacency:
                unresolved.add(station)
                continue
            stack.extend(adjacency[node])
    return links, unresolved


def graph_attachment(info, adjacency):
    identifier = int(info["hydroid"])
    # A ghost's own outgoing edge does not prove that upstream streams pass
    # through the ghost. Use its physical downstream attachment in every case.
    if info.get("ahgfftype") == 8:
        return info.get("nextdownid")
    return identifier if identifier in adjacency else info.get("nextdownid")


def summarize():
    candidates = pd.read_csv(FIRST / "metadata_candidates_and_roles.csv", dtype={"station_id": str, "station_no": str})
    lookup = pd.DataFrame([f["attributes"] for f in json.loads((RAW / "gauging_node_lookup_v2.json").read_text())["features"]])
    node_of = {}
    for path in sorted((RAW / "gauge_nodes").glob("batch_*.json")):
        if path.name.endswith(".request.json"):
            continue
        for feature in json.loads(path.read_text())["features"]:
            node_of[int(feature["attributes"]["hydroid"])] = feature
    adjacency = {}
    for path in sorted((RAW / "downstream").glob("objects_*.json")):
        if path.name.endswith(".request.json"):
            continue
        for feature in json.loads(path.read_text())["features"]:
            r = feature["attributes"]
            adjacency.setdefault(int(r["from_id"]), []).append(int(r["to_id"]))
    geod = Geod(ellps="WGS84")
    anchors, rows = {}, []
    for row in candidates.to_dict("records"):
        match = lookup.loc[lookup.stationno.eq(row["station_no"]) & lookup.dataownrid.eq(row["DATA_OWNER"])]
        good = match.loc[match.confidence.isin([1, 2, 3, 4]) & match.flagissues.isna()]
        reasons, distance, anchor = [], np.nan, None
        if row["medium_status"] != "watercourse_parameter_supported":
            reasons.append("pending_medium")
        if not np.isfinite(row["local_standard_offset_hours"]):
            reasons.append("pending_local_calendar")
        if len(good) != 1:
            reasons.append("no_unique_good_exact_station_owner_lookup")
        else:
            node = node_of.get(int(good.iloc[0].netnodeid))
            if node is None:
                reasons.append("missing_official_gauge_node")
            else:
                info, point = node["attributes"], node.get("geometry")
                if not point or info.get("dataownrid") != row["DATA_OWNER"] or info.get("stationno") != row["station_no"]:
                    reasons.append("gauge_identity_or_coordinate_unverified")
                else:
                    distance = geod.inv(float(row["station_longitude"]), float(row["station_latitude"]), point["x"], point["y"])[2]
                    if distance > 250:
                        reasons.append("gauge_coordinate_difference_over_250m")
                    # Ghost gauges do not break the stream graph. Attaching
                    # to the documented next downstream node can merge extra
                    # tributaries; it never creates finer independent units.
                    anchor = graph_attachment(info, adjacency)
                    if anchor is None or int(anchor) not in adjacency:
                        reasons.append("no_verified_downstream_graph_attachment")
                    else:
                        anchor = int(anchor)
        if not reasons:
            anchors[row["station_id"]] = anchor
        rows.append({"station_id": row["station_id"], "station_no": row["station_no"], "station_name": row["station_name"],
                     "first_wave_role": row["role"], "first_wave_group": row["independence_group"],
                     "gauge_distance_m": distance, "downstream_attachment_node": anchor,
                     "network_metadata_status": "resolved" if not reasons else ";".join(reasons),
                     "new_role_assigned": False, "new_temperature_measurements_opened_by_this_audit": False})
    links, unresolved = downstream_station_links(anchors, adjacency)
    parent = {station: station for station in anchors}
    def find(station):
        while parent[station] != station:
            parent[station] = parent[parent[station]]
            station = parent[station]
        return station
    for left, right in links:
        parent[find(right)] = find(left)
    components = {}
    for station in parent:
        components.setdefault(find(station), []).append(station)
    frame = pd.DataFrame(rows)
    frame["network_component"] = ""
    conflicts = []
    for group, members in enumerate(sorted(components.values(), key=lambda v: sorted(v))):
        selected = frame.station_id.isin(members)
        frame.loc[selected, "network_component"] = f"network_{group:04d}"
        roles = set(frame.loc[selected, "first_wave_role"]) - {"pending_metadata"}
        if len(roles) > 1:
            conflicts.append({"network_component": f"network_{group:04d}", "first_wave_roles": ";".join(sorted(roles)), "members": ";".join(sorted(members))})
    frame.loc[frame.station_id.isin(unresolved), "network_metadata_status"] = "pending_incomplete_downstream_trace"
    frame.to_csv(OUT / "station_network_scope.csv", index=False)
    pd.DataFrame(sorted(links), columns=["station_a", "station_b"]).to_csv(OUT / "network_connections.csv", index=False)
    pd.DataFrame(conflicts, columns=["network_component", "first_wave_roles", "members"]).to_csv(OUT / "first_wave_role_conflicts.csv", index=False)
    C.write_json(OUT / "summary.json", {
        "status": "metadata_feasibility_not_new_reference_release_or_confirmation", "candidate_stations": len(candidates),
        "stations_with_good_identity_coordinate_and_graph_attachment": len(anchors),
        "network_components_before_event_dependence_audit": len(components),
        "resolved_stations_previously_pending_polygon_metadata": int(frame.network_metadata_status.eq("resolved").mul(frame.first_wave_role.eq("pending_metadata")).sum()),
        "incomplete_trace_stations": len(unresolved), "first_wave_cross_role_network_components": len(conflicts),
        "first_wave_roles_edited": False, "new_role_assignments_or_temperature_downloads": False,
        "downstream_attachment_can_merge_additional_tributaries": True,
        "topology_or_station_match_is_not_process_or_region_event_verification": True,
        "shared_upstream_bifurcation_connections_fully_audited": False,
        "potential_new_candidate_bridges_do_not_alone_prove_original_role_leakage": True,
        "need_prior_pool_connection_review_and_additional_metadata_protocol_before_new_measurements": True})
    print(f"[406] {len(anchors)} mapped stations / {len(components)} network components; first-wave cross-role components={len(conflicts)}; no roles changed", flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["fetch", "summarize"])
    args = parser.parse_args()
    return fetch() if args.action == "fetch" else summarize()


if __name__ == "__main__":
    raise SystemExit(main())
