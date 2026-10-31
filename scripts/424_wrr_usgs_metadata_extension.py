"""Extend prior-identity metadata coverage; preserve the completed base plan."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import importlib
import json
import math
import os
import time
import numpy as np
import pandas as pd
from pyproj import Geod
import wrr_r3_common as C
from stream_recoverability.seeds import plain_seed
N = importlib.import_module('411_wrr_usgs_network_intake')
A = importlib.import_module('414_wrr_usgs_intake_audit')
R = importlib.import_module('413_wrr_usgs_network_resume')
BASE = C.READY / 'followup_20261021'
OUT = BASE / 'usgs_metadata_extension'
RAW = C.ROOT / 'data/external/wrr_usgs_new_reference_20261021/network_metadata/expanded_prior'
CONFIG = C.ROOT / 'configs/wrr_usgs_metadata_extension_20261021.json'
JOB_ORDER_SEED = 424

def classify_feature(payload, station, locations, tolerance=250):
    """Keep real missing reach indices separate from unverifiable identities."""
    features = payload.get('features', [])
    if payload.get('type') != 'FeatureCollection' or len(features) != 1:
        raise ValueError('The response does not identify exactly one source feature')
    feature = features[0]
    props, geom = (feature.get('properties', {}), feature.get('geometry') or {})
    if props.get('identifier') != 'USGS-' + station or props.get('source') != 'nwissite' or 'value' in props:
        raise ValueError('Unverified source identity or non-metadata payload')
    point = geom.get('coordinates')
    if geom.get('type') != 'Point' or not isinstance(point, list) or len(point) != 2 or (not np.isfinite(point).all()):
        raise ValueError('Unverified source geometry')
    distances = [Geod(ellps='WGS84').inv(*location, *point)[2] for location in locations]
    if not distances or not np.isfinite(distances).all():
        raise ValueError('No verified comparison coordinate')
    distance = float(min(distances))
    result = {'coordinate_distance_m': distance, 'source_identity_verified': True, 'source_coordinate_within_original_tolerance': distance <= tolerance, 'reported_comid': props.get('comid'), 'source_name': props.get('name', '')}
    if distance > tolerance:
        return {**result, 'status': 'pending_coordinate_mismatch'}
    comid = props.get('comid')
    if comid is None:
        return {**result, 'status': 'identity_location_verified_reach_unindexed'}
    if type(comid) is not int or comid <= 0:
        return {**result, 'status': 'pending_reach_schema'}
    return {**result, 'status': 'complete', 'comid': comid}

def prepare():
    """Fix the extension's job list and request order once; later runs reuse it."""
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / 'plan_lock.json'
    if path.exists():
        return json.loads(path.read_text())
    acquisition = json.loads((N.OUT / 'acquisition.json').read_text())
    if not acquisition['all_jobs_attempted'] or acquisition['acquisition_running']:
        raise RuntimeError('The base plan must be terminal before creating its extension')
    planned = {j['station'] for j in json.loads((N.OUT / 'plan_lock.json').read_text())['jobs']}
    prior = set(pd.read_csv(BASE / 'usgs_prior_cache_audit/expanded_prior_station_inventory.csv', dtype=str).station_id)
    locations = pd.read_csv(A.OUT / 'expanded_prior_locations.csv', dtype={'site': str})
    jobs = [{'station': number, 'kind': 'prior', 'locations': locations.loc[locations.site.eq(number), ['longitude', 'latitude']].to_numpy().tolist()} for number in sorted(prior - planned)]
    order = np.random.default_rng(plain_seed(JOB_ORDER_SEED)).permutation(len(jobs))
    plan = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'jobs': [jobs[index] for index in order], 'metadata_only': True, 'no_base_plan_or_results_changed': True, 'no_new_temperature_or_prediction_errors': True}
    C.write_json(path, plan)
    return plan

def run_job(job, settings):
    result = {'station': job['station'], 'kind': 'prior', 'sources': [], 'new_temperature_values_opened': False, 'upstream_station_ids': [], 'downstream_station_ids': []}
    if not job['locations']:
        result['status'] = 'pending_no_verified_source_location'
    else:
        try:
            payload, source = N.request_metadata(job['station'], 'feature', settings)
            result['sources'].append(source)
            result.update(classify_feature(payload, job['station'], job['locations']))
        except N.MetadataRequestFailure as error:
            result.update(status=error.status, detail=str(error))
            if error.source is not None:
                result['sources'].append({'path': str(error.source.relative_to(C.ROOT))})
        except (ValueError, KeyError, TypeError) as error:
            result.update(status='pending_identity_or_schema_review', detail=str(error))
    result['recorded_at_utc'] = datetime.now(timezone.utc).isoformat()
    N.write_atomic(RAW / 'job_results' / (job['station'] + '.json'), result)
    return result

def retained(job):
    path = RAW / 'job_results' / (job['station'] + '.json')
    if not path.exists():
        return None
    result = json.loads(path.read_text())
    if result['station'] != job['station']:
        raise RuntimeError('A result belongs to a different metadata extension')
    return result

def checkpoint(plan, results, **extra):
    C.write_json(OUT / 'acquisition.json', {'planned_jobs': len(plan['jobs']), 'attempted_jobs': len(results), 'all_jobs_attempted': len(results) == len(plan['jobs']), 'results': [results[k] for k in sorted(results)], 'controller_pid': os.getpid(), 'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'new_temperature_values_opened': False, 'new_prediction_errors_opened': False, **extra})

def fetch(plan):
    N.RAW = RAW
    settings = json.loads(N.CONFIG.read_text())
    N.STOP.clear()
    results = {job['station']: value for job in plan['jobs'] if (value := retained(job)) is not None}
    if any((row['status'] in {'pending_http_401', 'pending_http_403', 'pending_http_503'} for row in results.values())):
        raise RuntimeError('A retained access/service stop requires external-state review before new requests')
    deadline = R.observed_quota_deadline({'results': list(results.values())}, settings)
    while deadline is not None and (remaining := (deadline - datetime.now(timezone.utc)).total_seconds()) > 0:
        checkpoint(plan, results, status='waiting_observed_quota', next_allowed_utc=deadline.isoformat(), acquisition_running=True)
        print(f'[424] observed quota wait: {math.ceil(remaining)} seconds', flush=True)
        time.sleep(min(30.0, remaining))
    pending = [job for job in plan['jobs'] if job['station'] not in results or results[job['station']]['status'].startswith('pending_http_429') or results[job['station']]['status'] == 'pending_service_stop']
    checkpoint(plan, results, status='fetching_exact_prior_feature_metadata', acquisition_running=True)
    iterator = iter(pending)
    with ThreadPoolExecutor(max_workers=2) as pool:
        active = {}

        def submit():
            job = next(iterator, None)
            if job is not None and (not N.STOP.is_set()):
                active[pool.submit(run_job, job, settings)] = job
        for _ in range(2):
            submit()
        while active:
            finished, _ = wait(active, timeout=10, return_when=FIRST_COMPLETED)
            for future in finished:
                job = active.pop(future)
                results[job['station']] = future.result()
                submit()
            checkpoint(plan, results, status='fetching_exact_prior_feature_metadata', acquisition_running=bool(active))
            if finished:
                print(f"[424] {len(results)}/{len(plan['jobs'])} prior identity records; service stop={N.STOP.is_set()}", flush=True)
    checkpoint(plan, results, status='stopped_for_service_review' if N.STOP.is_set() else 'extension_metadata_attempts_finished', acquisition_running=False)
    return int(N.STOP.is_set())

def audit(plan):
    results = {j['station']: value for j in plan['jobs'] if (value := retained(j)) is not None}
    original = json.loads((N.OUT / 'acquisition.json').read_text())
    jobs = {j['station']: j for j in json.loads((N.OUT / 'plan_lock.json').read_text())['jobs']}
    comparisons = []
    for row in original['results']:
        if row['status'] == 'complete':
            continue
        source = next((item for item in row['sources'] if 'request_path' in item))
        source_path = C.ROOT / source['path']
        classification = classify_feature(json.loads(source_path.read_text()), row['station'], jobs[row['station']]['locations'])
        comparisons.append({'station_id': row['station'], 'kind': row['kind'], 'original_status': row['status'], **classification, 'original_result_edited': False, 'source_path': source['path']})
    reviewed = pd.DataFrame(comparisons)
    reviewed.to_csv(OUT / 'base_unresolved_response_review.csv', index=False)
    pd.DataFrame([{k: v for k, v in row.items() if k not in {'sources', 'upstream_station_ids', 'downstream_station_ids'}} for row in results.values()]).to_csv(OUT / 'expanded_prior_identity_scope.csv', index=False)
    candidates = pd.read_csv(N.P.OUT / 'metadata_candidates.csv', dtype={'station_id': str})
    cache = pd.read_csv(BASE / 'usgs_prior_cache_audit/candidate_prior_cache_scope.csv', dtype={'station_id': str})
    locations = pd.read_csv(A.OUT / 'expanded_prior_locations.csv', dtype={'site': str})
    prior = set(pd.read_csv(BASE / 'usgs_prior_cache_audit/expanded_prior_station_inventory.csv', dtype=str).station_id)
    observed = pd.read_csv(A.OUT / 'prior_index_observations.csv', dtype=str)
    prior_indices = {row.station_id: {'reaches': {int(i) for i in row.positive_reach_ids.split(';')}} for row in observed.itertuples()}
    combined = {row['station']: row for row in original['results']}
    combined.update(results)
    scope = A.effective_connection_scope(candidates, cache, combined, prior, locations, prior_indices)
    scope.to_csv(OUT / 'effective_candidate_scope.csv', index=False)
    original_scope = pd.read_csv(A.OUT / 'effective_candidate_scope.csv', dtype={'station_id': str}).set_index('station_id')
    current = scope.set_index('station_id')
    if set(current.index) != set(original_scope.index) or (current.not_yet_excluded_metadata_candidate & ~original_scope.not_yet_excluded_metadata_candidate).any():
        raise RuntimeError('A conservative prior extension cannot silently add new retained candidates')
    unexcluded = scope.loc[scope.not_yet_excluded_metadata_candidate]
    summary = {'status': 'prior_metadata_extension_not_new_independent_references', 'extended_prior_identifiers': len(plan['jobs']), 'extended_records_attempted': len(results), 'extension_all_records_attempted': len(results) == len(plan['jobs']), 'new_verified_prior_reach_indices': sum((r['status'] == 'complete' for r in results.values())), 'extended_status_counts': pd.Series([r['status'] for r in results.values()]).value_counts().to_dict(), 'base_unresolved_records_reviewed_without_new_requests': len(reviewed), 'base_review_status_counts': reviewed.status.value_counts().to_dict(), 'not_yet_excluded_metadata_candidates': len(unexcluded), 'those_without_complete_base_candidate_index_checks': int((~unexcluded.all_component_candidate_checks_complete).sum()), 'retained_candidates_are_not_qualified_references': True, 'base_plan_results_and_roles_unchanged': True, 'new_temperature_values_or_prediction_errors_opened': False, 'new_confirmation_completed': False, 'null_reach_index_is_not_a_zero_observation_or_independent_singleton': True, 'process_region_event_and_shared_upstream_dependence_still_unverified': True}
    C.write_json(OUT / 'summary.json', summary)
    print(f"[424] {len(reviewed)} base unresolved responses classified; {len(results)}/{len(plan['jobs'])} extended priors; {len(unexcluded)} metadata candidates remain unexcluded", flush=True)
    return 0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'fetch', 'audit'])
    args = parser.parse_args()
    plan = prepare()
    if args.action == 'prepare':
        print(f"[424] fixed {len(plan['jobs'])} expanded prior identities before new feature requests", flush=True)
        return 0
    return fetch(plan) if args.action == 'fetch' else audit(plan)
if __name__ == '__main__':
    raise SystemExit(main())
