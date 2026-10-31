#!/usr/bin/env python3
"""Acquire a fixed NLDI station-connectivity inventory without temperatures."""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import importlib
import json
import re
import threading
import time

import numpy as np
import pandas as pd
from pyproj import Geod
import requests

import wrr_r3_common as C
from stream_recoverability.seeds import plain_seed

P = importlib.import_module("410_wrr_usgs_reference_preflight")
CONFIG = C.ROOT / "configs/wrr_usgs_network_intake_20261021.json"
RAW = P.RAW.parent / "network_metadata/intake"
OUT = P.OUT.parent / "usgs_network_intake"
STOP = threading.Event()
RATE_LOCK = threading.Lock()
NEXT_REQUEST = 0.0
# Fixed seed of the request-order permutation over station-sorted jobs.
JOB_ORDER_SEED = 411


class MetadataRequestFailure(RuntimeError):
    def __init__(self, status, source, detail):
        super().__init__(detail)
        self.status, self.source = status, source


def write_atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def request_metadata(station, mode, settings):
    """Read cached bytes or one bounded metadata request; access failures stop."""
    global NEXT_REQUEST
    identifier = "USGS-" + P.station_number(station)
    endpoint = settings["network_base"] + "/" + identifier
    parameters = {"f": "json"}
    if mode != "feature":
        if mode not in settings["candidate_navigation_modes"]:
            raise ValueError("Undeclared metadata navigation mode")
        endpoint += f"/navigation/{mode}/nwissite"
        parameters.update(distance=settings["navigation_distance_km"], excludeGeometry="true")
    path = RAW / mode / (station + ".json")
    ledger_path = path.with_suffix(".request.json")
    if path.exists():
        ledger = json.loads(ledger_path.read_text())
        if ledger["endpoint"] != endpoint or ledger["parameters"] != parameters:
            raise RuntimeError("NLDI metadata cache request changed")
    else:
        if STOP.is_set():
            raise MetadataRequestFailure("pending_service_stop", None, "No new request after service stop")
        with RATE_LOCK:
            now = time.monotonic()
            delay = max(0., NEXT_REQUEST - now)
            NEXT_REQUEST = max(now, NEXT_REQUEST) + 1 / settings["maximum_requests_per_second"]
        if delay:
            time.sleep(delay)
        if STOP.is_set():
            raise MetadataRequestFailure("pending_service_stop", None, "No new request after service stop")
        path.parent.mkdir(parents=True, exist_ok=True)
        ledger = {"endpoint": endpoint, "parameters": parameters,
                  "acquired_at_utc": datetime.now(timezone.utc).isoformat(), "temperature_values_requested": False}
        try:
            response = requests.get(endpoint, params=parameters, timeout=settings["request_timeout_seconds"])
        except requests.RequestException as error:
            failure = path.with_name(path.stem + f".failure_{time.time_ns()}.json")
            write_atomic(failure, {**ledger, "status": "transport_failure", "exception": str(error)[:1000]})
            raise MetadataRequestFailure("pending_transport", failure, str(error)) from error
        if not response.ok:
            if response.status_code in (401, 403, 429, 503):
                STOP.set()
            failure = path.with_name(path.stem + f".failure_{time.time_ns()}.json")
            write_atomic(failure, {**ledger, "http_status": response.status_code,
                                  "retry_after": response.headers.get("Retry-After"), "response_excerpt": response.text[:1200]})
            status = "not_indexed" if response.status_code == 404 and mode == "feature" else f"pending_http_{response.status_code}"
            raise MetadataRequestFailure(status, failure, f"NLDI HTTP {response.status_code}")
        if len(response.content) > settings["maximum_response_bytes"]:
            raise MetadataRequestFailure("pending_oversized_metadata", None, "Metadata response exceeds fixed bound")
        payload = response.json()
        if payload.get("type") != "FeatureCollection" or any("value" in feature.get("properties", {}) for feature in payload.get("features", [])):
            raise MetadataRequestFailure("pending_metadata_schema", None, "Invalid station metadata FeatureCollection")
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(response.content)
        temporary.replace(path)
        ledger.update(http_status=response.status_code, bytes=len(response.content))
        write_atomic(ledger_path, ledger)
    payload = json.loads(path.read_text())
    if payload.get("type") != "FeatureCollection":
        raise RuntimeError("Cached NLDI result is not station metadata")
    return payload, {"path": str(path.relative_to(C.ROOT)), "request_path": str(ledger_path.relative_to(C.ROOT))}


def feature_metadata(payload, station, locations, tolerance_m):
    if len(payload.get("features", [])) != 1:
        raise ValueError("A source feature must identify exactly one station")
    feature = payload["features"][0]
    p, geometry = feature.get("properties", {}), feature.get("geometry", {}) or {}
    if p.get("identifier") != "USGS-" + station or p.get("source") != "nwissite":
        raise ValueError("NLDI station identity is not verified")
    point = geometry.get("coordinates")
    if geometry.get("type") != "Point" or not isinstance(point, list) or len(point) != 2 or not np.isfinite(point).all():
        raise ValueError("NLDI station coordinates are not verified")
    if not isinstance(p.get("comid"), int) or p["comid"] <= 0:
        raise ValueError("NLDI physical reach identifier is not verified")
    distances = [Geod(ellps="WGS84").inv(location[0], location[1], point[0], point[1])[2] for location in locations]
    if not distances or min(distances) > tolerance_m:
        raise ValueError("NLDI coordinates exceed fixed station tolerance")
    return {"comid": p["comid"], "reachcode": str(p.get("reachcode") or ""),
            "mainstem": p.get("mainstem"), "coordinate_distance_m": float(min(distances))}


def navigation_identifiers(payload):
    if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise ValueError("Invalid NLDI station-navigation metadata")
    if any(link.get("rel") == "next" for link in payload.get("links", [])):
        raise ValueError("Incomplete station-navigation metadata")
    numbers = set()
    for feature in payload["features"]:
        p = feature.get("properties", {})
        identifier = p.get("identifier")
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Z0-9]{2,8}-\d{8,15}", identifier) or p.get("source") != "nwissite":
            raise ValueError("Unverified identity in station-navigation metadata")
        if identifier.startswith("USGS-"):
            numbers.add(P.station_number(identifier))
    return sorted(numbers)


def run_job(job, settings):
    station = job["station"]
    result = {"station": station, "kind": job["kind"],
              "status": "pending", "sources": [], "new_temperature_values_opened": False,
              "upstream_station_ids": [], "downstream_station_ids": [], "other_agency_indexed_identifiers": {}}
    try:
        payload, source = request_metadata(station, "feature", settings)
        result["sources"].append(source)
        result.update(feature_metadata(payload, station, job["locations"], settings["feature_coordinate_tolerance_m"]))
        if job["kind"] == "candidate":
            for mode, field in (("UT", "upstream_station_ids"), ("DD", "downstream_station_ids")):
                payload, source = request_metadata(station, mode, settings)
                result["sources"].append(source)
                result[field] = navigation_identifiers(payload)
                result["other_agency_indexed_identifiers"][mode] = sorted({
                    feature["properties"]["identifier"] for feature in payload["features"]
                    if not feature["properties"]["identifier"].startswith("USGS-")})
        result["status"] = "complete"
    except MetadataRequestFailure as error:
        result["status"], result["detail"] = error.status, str(error)
        if error.source is not None:
            result["sources"].append({"path": str(error.source.relative_to(C.ROOT))})
    except (ValueError, KeyError, TypeError) as error:
        result["status"], result["detail"] = "pending_identity_or_schema_review", str(error)
    result["recorded_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_atomic(RAW / "job_results" / (station + ".json"), result)
    return result


def make_plan(settings):
    """Fix the job list and its request order once; later runs reuse the same plan."""
    OUT.mkdir(parents=True, exist_ok=True)
    plan_path = OUT / "plan_lock.json"
    if plan_path.exists():
        return json.loads(plan_path.read_text()), plan_path
    _, _, prior = P.prior_records()
    candidates = pd.read_csv(P.OUT / "metadata_candidates.csv", dtype={"station_id": str})
    jobs = []
    for station, group in prior.groupby("site"):
        jobs.append({"station": station, "kind": "prior", "locations": group[["longitude", "latitude"]].to_numpy().tolist()})
    for row in candidates.itertuples(index=False):
        jobs.append({"station": row.station_id, "kind": "candidate", "locations": [[row.longitude, row.latitude]]})
    if len({job["station"] for job in jobs}) != len(jobs):
        raise RuntimeError("Prior and new candidate identities overlap")
    jobs.sort(key=lambda job: job["station"])
    order = np.random.default_rng(plain_seed(JOB_ORDER_SEED)).permutation(len(jobs))
    plan = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "jobs": [jobs[index] for index in order],
            "existing_pilot_is_metadata_only": True, "new_temperature_values_opened": False,
            "component_roles_assigned": False}
    C.write_json(plan_path, plan)
    return plan, plan_path


def load_result(job):
    path = RAW / "job_results" / (job["station"] + ".json")
    if not path.exists():
        return None
    result = json.loads(path.read_text())
    if result["station"] != job["station"] or result["kind"] != job["kind"]:
        raise RuntimeError("NLDI cached job does not belong to this intake plan")
    return result


def checkpoint(plan, results, running=False):
    attempted = len(results)
    complete = sum(result["status"] == "complete" for result in results.values())
    C.write_json(OUT / "acquisition.json", {"planned_jobs": len(plan["jobs"]), "attempted_jobs": attempted,
                 "complete_index_jobs": complete, "pending_or_unindexed_jobs": attempted - complete,
                 "all_jobs_attempted": attempted == len(plan["jobs"]), "acquisition_running": running,
                 "service_stop_requested": STOP.is_set(), "new_temperature_values_opened": False,
                 "new_roles_assigned": False, "new_prediction_errors_opened": False,
                 "results": [results[key] for key in sorted(results)]})


def fetch(settings, plan, workers, retry_pending=False):
    results, pending = {}, []
    for job in plan["jobs"]:
        result = load_result(job)
        if result is not None:
            results[job["station"]] = result
        if result is None or (retry_pending and result["status"] != "complete"):
            pending.append(job)
    checkpoint(plan, results, running=True)
    iterator = iter(pending)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        active = {}
        def submit():
            job = next(iterator, None)
            if job is not None and not STOP.is_set():
                active[executor.submit(run_job, job, settings)] = job
        for _ in range(workers):
            submit()
        while active:
            finished, _ = wait(active, timeout=10, return_when=FIRST_COMPLETED)
            for future in finished:
                job = active.pop(future)
                results[job["station"]] = future.result()
                submit()
            checkpoint(plan, results, running=bool(active))
            if finished:
                complete = sum(result["status"] == "complete" for result in results.values())
                print(f"[411] {len(results)}/{len(plan['jobs'])} metadata jobs; complete index checks={complete}; service stop={STOP.is_set()}", flush=True)
    checkpoint(plan, results, running=False)
    return int(STOP.is_set())


def connection_scope(candidates, results, prior_numbers):
    """Keep unresolved stations explicit and never assign deployment roles."""
    numbers = set(candidates.station_id)
    parent = {number: number for number in numbers}
    def find(number):
        while parent[number] != number:
            parent[number] = parent[parent[number]]
            number = parent[number]
        return number
    old_comids = {result["comid"] for result in results.values() if result["kind"] == "prior" and result["status"] == "complete"}
    by_comid, old_connections = {}, {}
    for number in sorted(numbers):
        result = results.get(number, {})
        reached = set(result.get("upstream_station_ids", [])) | set(result.get("downstream_station_ids", []))
        old_connections[number] = reached & prior_numbers
        for other in reached & numbers:
            parent[find(number)] = find(other)
        if "comid" in result:
            previous = by_comid.setdefault(result["comid"], number)
            parent[find(number)] = find(previous)
    members = {}
    for number in sorted(numbers):
        members.setdefault(find(number), []).append(number)
    records = []
    for group in members.values():
        known = any(results.get(number, {}).get("status") == "complete" for number in group)
        # Members are sorted, so the label is the component's smallest station number.
        label = "index_" + group[0] if known else ""
        group_prior = set().union(*(old_connections[number] for number in group))
        group_comid_prior = any(results.get(number, {}).get("comid") in old_comids for number in group)
        group_complete = all(results.get(number, {}).get("status") == "complete" for number in group)
        for number in group:
            result = results.get(number, {})
            records.append({"station_id": number, "network_status": result.get("status", "not_yet_requested"),
                            "provisional_network_index_component": label,
                            "all_component_candidate_checks_complete": group_complete,
                            "reached_prior_station_ids": ";".join(sorted(group_prior)),
                            "same_index_comid_as_prior": group_comid_prior,
                            "component_has_prior_connection_screen": bool(group_prior) or group_comid_prior,
                            "new_role_assigned": False, "independent_component_verified": False,
                            "new_reference_eligible": False, "new_prediction_errors_opened": False})
    return pd.DataFrame(records)


def summarize(plan):
    results = {job["station"]: result for job in plan["jobs"] if (result := load_result(job)) is not None}
    candidates = pd.read_csv(P.OUT / "metadata_candidates.csv", dtype={"station_id": str})
    prior_numbers, _, _ = P.prior_records()
    frame = connection_scope(candidates, results, prior_numbers)
    frame.to_csv(OUT / "candidate_network_scope.csv", index=False)
    blocks = frame.loc[frame.provisional_network_index_component.ne("")].drop_duplicates("provisional_network_index_component")
    prior_results = [result for result in results.values() if result["kind"] == "prior"]
    summary = {"status": "indexed_metadata_connectivity_screen_not_confirmatory_independence",
               "planned_candidate_jobs": len(candidates), "planned_prior_jobs": len(plan["jobs"]) - len(candidates),
               "all_planned_jobs_attempted": len(results) == len(plan["jobs"]),
               "candidate_complete_index_checks": int(frame.network_status.eq("complete").sum()),
               "candidate_pending_or_unindexed": int(frame.network_status.ne("complete").sum()),
               "prior_complete_index_checks": sum(result["status"] == "complete" for result in prior_results),
               "provisional_candidate_index_components": len(blocks),
               "provisional_components_with_prior_connection_screen": int(blocks.component_has_prior_connection_screen.sum()),
               "all_candidate_directions_complete_in_every_component": bool(frame.all_component_candidate_checks_complete.all()),
               "new_independent_components_verified": False,
               "shared_upstream_diversions_without_indexed_station_connection_fully_checked": False,
               "region_event_dependence_verified": False, "repository_prior_access_audit_complete": False,
               "new_temperature_observations_acquired": False, "new_roles_assigned": False,
               "new_H30_prediction_errors_opened": False, "new_confirmation_completed": False}
    C.write_json(OUT / "summary.json", summary)
    print(f"[411] candidate checks {summary['candidate_complete_index_checks']}/{len(candidates)}; "
          f"{len(blocks)} provisional index groups; primary reference and outcome gates remain closed", flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["fetch", "summarize"])
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--retry-pending", action="store_true")
    args = parser.parse_args()
    settings = json.loads(CONFIG.read_text())
    if not 1 <= args.workers <= settings["maximum_workers"]:
        raise ValueError("Worker count exceeds fixed metadata intake bound")
    plan, _ = make_plan(settings)
    return fetch(settings, plan, args.workers, args.retry_pending) if args.action == "fetch" else summarize(plan)


if __name__ == "__main__":
    raise SystemExit(main())
