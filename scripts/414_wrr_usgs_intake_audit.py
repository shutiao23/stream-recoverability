#!/usr/bin/env python3
"""Bind conservative USGS intake evidence to a dated metadata snapshot."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib
import json
import re

import numpy as np
import pandas as pd
from pyproj import Geod

import wrr_r3_common as C

P = importlib.import_module("410_wrr_usgs_reference_preflight")
N = importlib.import_module("411_wrr_usgs_network_intake")
A = importlib.import_module("412_wrr_usgs_prior_cache_audit")
OUT = P.OUT.parent / "usgs_intake_evidence"


def returned_RDB_identifiers(path):
    """Consult agency and station columns only, without parsing measurements."""
    result = set()
    with path.open(errors="replace") as handle:
        for line in handle:
            fields = line.split("\t", 2)
            if len(fields) >= 2 and fields[0] == "USGS" and re.fullmatch(r"\d{8,15}", fields[1]):
                result.add(fields[1])
    return result


def additional_locations(base, features, prior):
    additions = []
    for feature in features:
        p, geometry = feature["properties"], feature.get("geometry") or {}
        identity = feature["id"]
        if p.get("agency_code") != "USGS" or not identity.startswith("USGS-"):
            raise ValueError("Unexpected agency in a declared prior-location response")
        number = P.station_number(identity)
        if number not in prior or P.station_number(p["monitoring_location_number"]) != number:
            raise ValueError("Returned location identity differs from the old-record inventory")
        point = geometry.get("coordinates")
        if geometry.get("type") != "Point" or not isinstance(point, list) or len(point) != 2 or not np.isfinite(point).all():
            raise ValueError("Unverified additional old-station coordinates")
        additions.append({"site": number, "longitude": point[0], "latitude": point[1]})
    return pd.concat([base, pd.DataFrame(additions, columns=["site", "longitude", "latitude"])], ignore_index=True).drop_duplicates(["site", "longitude", "latitude"])


def collect_prior_indices(features, prior, source_path, observations):
    """Keep positive indexed old reaches without inventing a verified point."""
    for feature in features:
        properties = feature.get("properties", {})
        identity = properties.get("identifier", "")
        if not isinstance(identity, str) or not identity.startswith("USGS-") or properties.get("source") != "nwissite":
            continue
        station = identity.removeprefix("USGS-")
        reach = properties.get("comid")
        if station not in prior or isinstance(reach, bool) or not isinstance(reach, int) or reach <= 0:
            continue
        record = observations.setdefault(station, {"reaches": set(), "sources": set()})
        record["reaches"].add(reach)
        record["sources"].add(source_path)


def effective_connection_scope(candidates, cache_scope, results, prior, locations, prior_indices=None):
    # Preserve archived job kinds. Only this copied analytical view treats the
    # newly discovered old-cache candidates as prior records.
    normalized = {key: {**value, "kind": "prior" if key in prior else value["kind"]} for key, value in results.items()}
    network = N.connection_scope(candidates, normalized, prior)
    frame = cache_scope.merge(network, on="station_id", how="left", validate="one_to_one", suffixes=("", "_network"))
    labels = set(frame.loc[frame.expanded_prior_cache_contact & frame.provisional_network_index_component.ne(""), "provisional_network_index_component"])
    frame["component_contains_old_cache_identity"] = frame.expanded_prior_cache_contact | frame.provisional_network_index_component.isin(labels)
    near = []
    geod = Geod(ellps="WGS84")
    for row in frame.itertuples(index=False):
        distance = geod.inv(locations.longitude.tolist(), locations.latitude.tolist(),
                            [row.longitude] * len(locations), [row.latitude] * len(locations))[2]
        near.append(";".join(sorted(set(locations.loc[np.asarray(distance) <= 250, "site"]))))
    frame["expanded_prior_stations_within_250m"] = near
    indexed_reaches = {reach for record in (prior_indices or {}).values() for reach in record["reaches"]}
    frame["navigation_seen_prior_reach_match"] = frame.station_id.map(
        lambda number: results.get(number, {}).get("comid") in indexed_reaches)
    reach_labels = set(frame.loc[frame.navigation_seen_prior_reach_match & frame.provisional_network_index_component.ne(""),
                                 "provisional_network_index_component"])
    frame["component_has_navigation_seen_prior_reach"] = (frame.navigation_seen_prior_reach_match |
                                                          frame.provisional_network_index_component.isin(reach_labels))
    frame["known_prior_contact_screen"] = (frame.expanded_prior_cache_contact | frame.component_contains_old_cache_identity |
                                            frame.component_has_prior_connection_screen | frame.expanded_prior_stations_within_250m.ne("") |
                                            frame.component_has_navigation_seen_prior_reach)
    frame["not_yet_excluded_metadata_candidate"] = frame.effective_metadata_candidate & ~frame.known_prior_contact_screen
    frame["reference_release_allowed"] = False
    return frame


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["audit"])
    parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    prior = set(pd.read_csv(A.OUT / "expanded_prior_station_inventory.csv", dtype={"station_id": str}).station_id)
    occurrences = pd.read_csv(A.OUT / "cache_identity_occurrences.csv", dtype={"station_id": str})
    legacy = occurrences.loc[occurrences.evidence_kind.eq("saved_legacy_daily_request_and_response")].drop_duplicates("source_path")
    returned, response_rows = set(), []
    for row in legacy.itertuples(index=False):
        response = (C.ROOT / row.source_path).parent / "response.rdb"
        numbers = returned_RDB_identifiers(response)
        returned.update(numbers)
        response_rows.append({"path": str(response.relative_to(C.ROOT)), "returned_station_ids": sorted(numbers)})
    if returned - prior:
        raise RuntimeError("Old response identities are absent from the expanded exclusion inventory")
    C.write_json(OUT / "legacy_response_identity_coverage.json", {
        "saved_responses_checked": len(response_rows), "unique_returned_station_ids": len(returned),
        "all_returned_identities_already_excluded": True, "temperature_columns_parsed": False,
        "request_only_identity_is_not_an_observed_station_count": True, "sources": response_rows})
    locations = pd.read_csv(A.OUT / "expanded_prior_locations.csv", dtype={"site": str})
    extra = P.RAW / "additional_prior_location_metadata.json"
    extra_features = json.loads(extra.read_text())["features"]
    locations = additional_locations(locations, extra_features, prior)
    locations.to_csv(OUT / "expanded_prior_locations.csv", index=False)
    settings = json.loads(N.CONFIG.read_text())
    plan, _ = N.make_plan(settings)
    acquisition_path = N.OUT / "acquisition.json"
    acquisition_bytes = acquisition_path.read_bytes()
    acquisition = json.loads(acquisition_bytes)
    recorded = datetime.now(timezone.utc)
    snapshot = OUT / "snapshots" / f"acquisition_{recorded:%Y%m%dT%H%M%S%fZ}.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(acquisition_bytes)
    results = {row["station"]: row for row in acquisition["results"]}
    observations, visited_sources = {}, set()
    for row in results.values():
        for source in row["sources"]:
            if "request_path" in source and source["path"] not in visited_sources:
                visited_sources.add(source["path"])
                payload = json.loads((C.ROOT / source["path"]).read_text())
                collect_prior_indices(payload.get("features", []), prior, source["path"], observations)
    candidates = pd.read_csv(P.OUT / "metadata_candidates.csv", dtype={"station_id": str})
    cache_scope = pd.read_csv(A.OUT / "candidate_prior_cache_scope.csv", dtype={"station_id": str})
    scope = effective_connection_scope(candidates, cache_scope, results, prior, locations, observations)
    scope.to_csv(OUT / "effective_candidate_scope.csv", index=False)
    planned = {job["station"] for job in plan["jobs"]}
    indexed = pd.DataFrame([{
        "station_id": station, "positive_reach_ids": ";".join(map(str, sorted(record["reaches"]))),
        "source_paths": ";".join(sorted(record["sources"])), "source_count": len(record["sources"]),
        "in_original_network_plan": station in planned, "multiple_indexed_reaches": len(record["reaches"]) > 1,
        "direct_feature_coordinate_check_recorded": "coordinate_distance_m" in results.get(station, {}),
        "index_observation_alone_verifies_independence": False,
    } for station, record in sorted(observations.items())], columns=[
        "station_id", "positive_reach_ids", "source_paths", "source_count", "in_original_network_plan",
        "multiple_indexed_reaches", "direct_feature_coordinate_check_recorded", "index_observation_alone_verifies_independence"])
    indexed.to_csv(OUT / "prior_index_observations.csv", index=False)
    unexcluded = scope.loc[scope.not_yet_excluded_metadata_candidate]
    summary = {
        "status": "dated_incomplete_metadata_scope_not_new_references_or_confirmation",
        "recorded_at_utc": recorded.isoformat(), "base_acquisition_snapshot": str(snapshot.relative_to(C.ROOT)),
        "base_metadata_jobs_attempted": acquisition["attempted_jobs"], "base_metadata_jobs_planned": acquisition["planned_jobs"],
        "base_plan_all_jobs_attempted": acquisition["all_jobs_attempted"],
        "original_preflight_metadata_candidates": len(candidates),
        "prior_cached_identifiers": len(prior), "direct_prior_cache_exclusions": int(scope.expanded_prior_cache_contact.sum()),
        "after_direct_cache_exclusions": int(scope.effective_metadata_candidate.sum()),
        "not_yet_excluded_after_current_connection_and_coordinate_screens": len(unexcluded),
        "those_without_complete_candidate_index_checks": int(unexcluded.network_status.ne("complete").sum()),
        "prior_identities_without_current_location": len(prior - set(locations.site)),
        "prior_identities_outside_original_network_plan": len(prior - {job["station"] for job in plan["jobs"]}),
        "prior_ids_seen_with_positive_reach_index_in_saved_responses": len(observations),
        "extra_prior_ids_outside_plan_seen_in_saved_responses": sum(station not in planned for station in observations),
        "prior_ids_with_multiple_indexed_reaches": sum(len(record["reaches"]) > 1 for record in observations.values()),
        "saved_index_observations_do_not_complete_source_coordinate_checks": True,
        "returned_legacy_response_ids_covered": True,
        "new_temperature_observations_acquired": False, "new_roles_assigned": False,
        "new_H30_prediction_errors_opened": False, "new_independent_confirmation_completed": False,
        "new_reference_quality_qualified_station_years": None,
        "unrequested_unindexed_or_unlocated_is_not_zero_reference_eligibility": True,
        "known_network_index_connection_does_not_alone_prove_record_leakage": True,
        "regional_events_process_attributes_and_complete_prior_inventory_still_required": True,
    }
    checks = {
        "original_candidate_rows_retained": len(scope) == len(candidates) and not scope.station_id.duplicated().any(),
        "all_prior_cache_candidates_remain_excluded": not scope.loc[scope.expanded_prior_cache_contact, "not_yet_excluded_metadata_candidate"].any(),
        "all_returned_legacy_ids_in_prior_inventory": returned.issubset(prior),
        "old_location_rows_preserved": set(pd.read_csv(A.OUT / "expanded_prior_locations.csv", dtype={"site": str}).site).issubset(set(locations.site)),
        "no_reference_release_or_role_assignment": not scope.reference_release_allowed.any() and not scope.new_role_assigned.any(),
        "no_new_error_access_in_snapshot": not acquisition["new_prediction_errors_opened"],
        "no_unavailable_reference_quality_promoted": not scope.reference_quality_qualified.any(),
        "index_observations_do_not_verify_independence": not indexed.index_observation_alone_verifies_independence.any(),
    }
    if not all(checks.values()):
        raise RuntimeError(f"Intake conservation failed: {[key for key, value in checks.items() if not value]}")
    C.write_json(OUT / "summary.json", summary)
    pd.DataFrame([{"check": key, "passed": value} for key, value in checks.items()]).to_csv(OUT / "checks.csv", index=False)
    print(f"[414] {len(candidates)} original metadata candidates retained; {int(scope.effective_metadata_candidate.sum())} after direct cache exclusions; "
          f"{len(unexcluded)} not yet excluded by partial connection evidence; no reference release", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
