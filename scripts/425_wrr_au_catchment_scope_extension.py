"""Acquire official catchment metadata without replacing verified attachments."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import importlib
import json
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point, shape
import wrr_r3_common as C
from stream_recoverability.seeds import plain_seed
D = importlib.import_module('408_wrr_au_dependence_audit')
G = D.G
BASE = C.READY / 'followup_20261021'
OUT = BASE / 'au_catchment_scope_extension'
RAW = C.ROOT / 'data/external/wrr_au_confirmation_20261021/catchment_extension_metadata'
CONFIG = C.ROOT / 'configs/wrr_au_catchment_scope_extension_20261021_v2.json'
POINT_ORDER_SEED = 425

def point_records(payload, maximum=2000):
    if not isinstance(payload.get('features'), list) or payload.get('error'):
        raise ValueError('Response is not native catchment feature metadata')
    if payload.get('exceededTransferLimit') or len(payload['features']) >= maximum:
        raise ValueError('Point query may be truncated')
    records = []
    for feature in payload['features']:
        props = feature.get('attributes', {})
        if 'value' in props or type(props.get('hydroid')) is not int or props['hydroid'] <= 0:
            raise ValueError('Unverified catchment identity or non-metadata payload')
        node = props.get('netnodeid')
        records.append({'hydroid': props['hydroid'], 'netnodeid': node if type(node) is int and node > 0 else None, 'hassegment': props.get('hassegment')})
    if len({row['hydroid'] for row in records}) != len(records):
        raise ValueError('Duplicate catchment identities')
    return records

def validate_payload(payload, maximum):
    if payload.get('type') != 'FeatureCollection' or not isinstance(payload.get('features'), list):
        raise ValueError('Response is not catchment feature metadata')
    if payload.get('exceededTransferLimit') or len(payload['features']) >= maximum or any((x.get('rel') == 'next' for x in payload.get('links', []))):
        raise ValueError('Catchment query may be truncated')
    records = []
    for feature in payload['features']:
        props = feature.get('properties', {})
        if 'value' in props or type(props.get('hydroid')) is not int or props['hydroid'] <= 0:
            raise ValueError('Unverified catchment identifier or non-metadata payload')
        geom = shape(feature['geometry'])
        if geom.geom_type not in {'Polygon', 'MultiPolygon'} or not geom.is_valid:
            raise ValueError('Unverified catchment polygon; do not silently repair it')
        node = props.get('netnodeid')
        records.append({'hydroid': props['hydroid'], 'netnodeid': node if type(node) is int and node > 0 else None, 'geometry': geom, 'hassegment': props.get('hassegment')})
    if len({r['hydroid'] for r in records}) != len(records):
        raise ValueError('Duplicate catchment identity in one metadata response')
    return records

def covering_records(records, longitude, latitude):
    point = Point(longitude, latitude)
    return [row for row in records if row['geometry'].covers(point)]

def combined_components(block_sets):
    """Retain all possible blocks, including disagreements with older anchors."""
    parent = {block: block for blocks in block_sets.values() for block in blocks}

    def find(block):
        while parent[block] != block:
            parent[block] = parent[parent[block]]
            block = parent[block]
        return block
    for blocks in block_sets.values():
        blocks = sorted(blocks)
        for other in blocks[1:]:
            parent[find(other)] = find(blocks[0])
    groups = {}
    for block in parent:
        groups.setdefault(find(block), set()).add(block)
    label = {block: 'catchment_scope_' + min(values) for values in groups.values() for block in values}
    return {station: label[next(iter(blocks))] if blocks else '' for station, blocks in block_sets.items()}

def prepare():
    """Fix the point batches and their request order once; later runs reuse them."""
    OUT.mkdir(exist_ok=True, parents=True)
    path = OUT / 'point_plan_lock.json'
    if path.exists():
        return json.loads(path.read_text())
    settings = json.loads(CONFIG.read_text())
    stations = pd.read_csv(G.FIRST / 'metadata_candidates_and_roles.csv', dtype={'station_id': str})
    points = [{'station_id': r.station_id, 'longitude': float(r.station_longitude), 'latitude': float(r.station_latitude)} for r in stations.itertuples()]
    pending = [p['station_id'] for p in points if not (110 < p['longitude'] < 160 and -45 < p['latitude'] < -9)]
    points = sorted((p for p in points if p['station_id'] not in set(pending)), key=lambda p: p['station_id'])
    points = [points[i] for i in np.random.default_rng(plain_seed(POINT_ORDER_SEED)).permutation(len(points))]
    jobs = [{'batch': i // settings['batch_size'], 'points': points[i:i + settings['batch_size']]} for i in range(0, len(points), settings['batch_size'])]
    plan = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'jobs': jobs, 'pending_provider_coordinate_review': pending, 'all_original_candidates_retained': True, 'metadata_only': True, 'no_new_roles_or_error_access': True}
    C.write_json(path, plan)
    return plan

def parameters(job):
    if len(job['points']) != 1:
        raise ValueError('Only one coordinate per corrected spatial query')
    point = job['points'][0]
    return {'f': 'json', 'where': '1=1', 'geometryType': 'esriGeometryPoint', 'geometry': json.dumps({'x': point['longitude'], 'y': point['latitude'], 'spatialReference': {'wkid': 4326}}, separators=(',', ':')), 'inSR': '4326', 'spatialRel': 'esriSpatialRelIntersects', 'outFields': 'hydroid,netnodeid,hassegment,ncb_id,planacc,textnote', 'returnGeometry': 'false', 'outSR': '4326', 'resultRecordCount': '2000'}

def retained(job):
    path = RAW / 'point_batches' / f"batch_{job['batch']:04d}.json"
    ledger = path.with_suffix('.request.json')
    if not path.exists():
        return None
    record = json.loads(ledger.read_text())
    if record['parameters'] != parameters(job):
        raise RuntimeError('Catchment metadata cached request changed')
    return (path, ledger)

def fetch(plan):
    settings = json.loads(CONFIG.read_text())
    RAW.mkdir(exist_ok=True, parents=True)
    if list((RAW / 'point_batches').glob('*.failure.json')):
        raise RuntimeError('Retained service/schema failure requires review before any new request')
    done = 0
    next_request = 0.0
    rate_lock = threading.Lock()
    stop = threading.Event()

    def acquire(job):
        nonlocal next_request
        old = retained(job)
        if old is None:
            if stop.is_set():
                return False
            with rate_lock:
                now = time.monotonic()
                delay = max(0.0, next_request - now)
                next_request = max(now, next_request) + 1 / settings['maximum_requests_per_second']
            if delay:
                time.sleep(delay)
            if stop.is_set():
                return False
            endpoint = f'{G.SERVICE}/7/query'
            params = parameters(job)
            try:
                response = requests.get(endpoint, params=params, timeout=90)
            except requests.RequestException as error:
                stop.set()
                failure = RAW / 'point_batches' / f"batch_{job['batch']:04d}.failure.json"
                failure.parent.mkdir(exist_ok=True, parents=True)
                C.write_json(failure, {'endpoint': endpoint, 'parameters': params, 'error': str(error), 'response_observed_at_utc': datetime.now(timezone.utc).isoformat(), 'http_status': None, 'temperature_measurements_requested': False})
                raise
            stamp = datetime.now(timezone.utc).isoformat()
            path = RAW / 'point_batches' / f"batch_{job['batch']:04d}.json"
            path.parent.mkdir(exist_ok=True, parents=True)
            info = {'endpoint': endpoint, 'parameters': params, 'response_observed_at_utc': stamp, 'http_status': response.status_code, 'retry_after': response.headers.get('Retry-After'), 'temperature_measurements_requested': False}
            try:
                response.raise_for_status()
                if len(response.content) > settings['maximum_response_bytes']:
                    raise ValueError('Catchment metadata exceeds fixed byte bound')
                point_records(response.json(), settings['maximum_returned_features'])
            except (ValueError, requests.RequestException) as error:
                stop.set()
                C.write_json(path.with_suffix('.failure.json'), {**info, 'error': str(error), 'response_excerpt': response.text[:1000]})
                raise
            path.write_bytes(response.content)
            C.write_json(path.with_suffix('.request.json'), {**info, 'bytes': len(response.content)})
        return True

    def checkpoint(status, running):
        C.write_json(OUT / 'acquisition.json', {'status': status, 'completed_batches': done, 'planned_batches': len(plan['jobs']), 'acquisition_running': running, 'controller_pid': os.getpid(), 'new_temperature_values_or_prediction_errors_opened': False, 'recorded_at_utc': datetime.now(timezone.utc).isoformat()})
    checkpoint('fetching', True)
    try:
        with ThreadPoolExecutor(max_workers=settings['maximum_workers']) as pool:
            futures = [pool.submit(acquire, job) for job in plan['jobs']]
            for future in as_completed(futures):
                done += bool(future.result())
                checkpoint('fetching', True)
                if done % 25 == 0:
                    print(f"[425] {done}/{len(plan['jobs'])} per-point catchment queries; no measurements", flush=True)
    except Exception:
        stop.set()
        checkpoint('stopped_requires_source_review', False)
        raise
    checkpoint('all_metadata_batches_acquired', False)
    return 0

def audit(plan):
    station_records = {}
    catchments = {}
    for job in plan['jobs']:
        old = retained(job)
        if old is None:
            raise RuntimeError('Metadata acquisition is incomplete; do not promote a partial survey')
        source, _ = old
        records = point_records(json.loads(source.read_text()), 2000)
        for row in records:
            if row['hydroid'] in catchments and row != catchments[row['hydroid']]:
                raise RuntimeError('Catchment metadata changed between batches')
            catchments[row['hydroid']] = row
        for point in job['points']:
            station_records[point['station_id']] = records
    topology = json.loads((G.OUT / 'metadata_acquisition.json').read_text())
    anchors = {str(key): value['netnodeid'] for key, value in catchments.items() if value['netnodeid'] is not None}
    blocks, missing, network = D.hydrologic_blocks(D.load_network(topology), anchors)
    original = pd.read_csv(D.OUT / 'station_hydrologic_scope.csv', dtype=str).fillna('')
    rows = []
    sets = {}
    for item in original.itertuples():
        records = station_records.get(item.station_id, [])
        proxy = {blocks[str(r['hydroid'])] for r in records if str(r['hydroid']) in blocks}
        possible = proxy | ({item.hydrologic_block} if item.hydrologic_block else set())
        sets[item.station_id] = possible
        rows.append({'station_id': item.station_id, 'first_wave_role': item.first_wave_role, 'original_verified_block': item.hydrologic_block, 'catchment_query_attempted': item.station_id in station_records, 'provider_coordinate_pending_review': item.station_id in set(plan['pending_provider_coordinate_review']), 'catchment_ids': ';'.join((str(r['hydroid']) for r in records)), 'catchment_blocks': ';'.join(sorted(proxy)), 'catchments_without_verified_node_block': sum((str(r['hydroid']) not in blocks for r in records)), 'original_block_in_proxy': item.hydrologic_block in proxy if item.hydrologic_block and proxy else None, 'combined_possible_blocks': ';'.join(sorted(possible)), 'new_physical_gauge_attachment_verified': False, 'new_role_assigned': False, 'reference_release_allowed': False, 'new_prediction_errors_opened': False})
    frame = pd.DataFrame(rows)
    frame['conservative_combined_component'] = frame.station_id.map(combined_components(sets))
    frame.to_csv(OUT / 'station_catchment_scope.csv', index=False)
    groups = D.role_block_summary(frame, role_column='first_wave_role', block_column='conservative_combined_component')
    groups.to_csv(OUT / 'conservative_component_scope.csv', index=False)
    paired = frame.loc[frame.original_block_in_proxy.notna()]
    summary = {'status': 'official_catchment_proxy_scope_not_verified_new_independent_units', 'original_candidates': len(frame), 'provider_coordinates_pending_review_without_guessing': len(plan['pending_provider_coordinate_review']), 'station_coordinates_queried': len(station_records), 'metadata_batches': len(plan['jobs']), 'unique_provider_reported_catchments': len(catchments), 'catchment_nodes_not_in_retained_graph': len(missing), 'stations_with_catchment_proxy_blocks': int(frame.catchment_blocks.ne('').sum()), 'originally_unmapped_stations_with_proxy_blocks': int((frame.original_verified_block.eq('') & frame.catchment_blocks.ne('')).sum()), 'paired_original_and_proxy_stations': len(paired), 'paired_block_disagreements': int(paired.original_block_in_proxy.eq(False).sum()), 'conservative_combined_components': len(groups), 'combined_components_spanning_original_roles': int(groups.cross_role_screen.sum()), 'unresolved_stations_without_either_block': int(frame.conservative_combined_component.eq('').sum()), 'new_physical_station_attachments_verified': False, 'proxy_does_not_verify_region_event_or_process_independence': True, 'original_roles_qualifications_models_or_errors_changed': False, 'new_independent_confirmation_completed': False, 'new_temperature_values_or_prediction_errors_opened': False, 'network': network, 'scope': 'Official per-point spatial-query metadata at exact recorded coordinates; retain all reported catchment-node proxies plus original verified blocks. Polygon geometry was not independently rechecked locally; no nearest-river assignment, physical attachment verification or reference release.'}
    C.write_json(OUT / 'summary.json', summary)
    print(f"[425] {summary['originally_unmapped_stations_with_proxy_blocks']} formerly unmapped stations have catchment proxies; {len(groups)} conservative combined components; no new reference released", flush=True)
    return 0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'fetch', 'audit', 'run'])
    args = parser.parse_args()
    plan = prepare()
    if args.action == 'prepare':
        print(f"[425] fixed {sum((len(j['points']) for j in plan['jobs']))} station coordinates in {len(plan['jobs'])} metadata batches", flush=True)
        return 0
    if args.action == 'run':
        code = fetch(plan)
        return code if code else audit(plan)
    return fetch(plan) if args.action == 'fetch' else audit(plan)
if __name__ == '__main__':
    raise SystemExit(main())
