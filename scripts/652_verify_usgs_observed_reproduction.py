#!/usr/bin/env python3
"""Rebuild the additional USGS observational witnesses without network access.

Uses frozen daily API responses, provider metadata and the original QC/selection
pipeline; also runs a separate arithmetic audit. Does not validate sensors,
24-hour sampling, transfer, reconstruction accuracy, or other manuscript results.
All generated files go to a disposable directory, never the study source inputs.
"""
from __future__ import annotations
import argparse
import gzip
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'results/additional_usgs_observed'
RAW = ROOT / 'data/external/additional_usgs_observed/raw'
MANIFEST = ROOT / 'results/wrr_review_response_20261027/audit/usgs_observed_snapshot_manifest.json'
TABLES = ['raw_reference_summary.csv', 'robust_record_witnesses.csv', 'qualification.csv', 'all_approved_window_bounds.csv']

def create_manifest(destination):
    """Freeze a new snapshot vintage; never retrofit a historical manifest."""
    cohort=pd.read_csv(SOURCE/'cohort_metadata.csv',dtype=str)
    files=[SOURCE/name for name in ['cohort_metadata.csv','acquisition.json','plan.json',*TABLES]]
    files += [RAW/(site+'.json.gz') for site in cohort.station_id]
    files.append(RAW.parent/'ATTRIBUTION.txt')
    if any(not path.is_file() or path.is_symlink() for path in files):
        raise ValueError('Missing or unsafe USGS snapshot input')
    doc={'scope':'New content-pinned USGS observation snapshot; this does not retroactively certify a historical manifest',
         'station_count':len(cohort),'files':[{'path':str(path.relative_to(ROOT)),
                                             'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for path in files]}
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('x') as stream:stream.write(json.dumps(doc,indent=2)+'\n')
    return doc

def verify_manifest(manifest_path=None):
    manifest_path=Path(manifest_path) if manifest_path is not None else MANIFEST
    doc = json.loads(manifest_path.read_text())
    names = [item['path'] for item in doc['files']]
    if len(names) != len(set(names)):
        raise ValueError('Duplicate snapshot manifest paths')
    for item in doc['files']:
        path = ROOT / item['path']
        if (not path.resolve().is_relative_to(ROOT.resolve()) or not path.is_file() or path.is_symlink()
                or not item.get('sha256') or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']):
            raise ValueError('Missing, unsafe or changed USGS snapshot input: ' + item['path'])
    cohort = pd.read_csv(SOURCE / 'cohort_metadata.csv', dtype=str)
    if cohort.station_id.duplicated().any() or len(cohort) != doc['station_count']:
        raise ValueError('Frozen cohort is invalid')
    expected = {f'data/external/additional_usgs_observed/raw/{site}.json.gz' for site in cohort.station_id}
    recorded = {i['path'] for i in doc['files'] if i['path'].startswith('data/external/additional_usgs_observed/raw/')}
    if expected != recorded:
        raise ValueError('Snapshot raw payloads do not match cohort')
    required = {f'results/additional_usgs_observed/{name}' for name in
                ['cohort_metadata.csv', 'acquisition.json', 'plan.json', *TABLES]}
    required.add('data/external/additional_usgs_observed/ATTRIBUTION.txt')
    if set(names) != expected | required:
        raise ValueError('Snapshot manifest does not match required evidence')
    acquisition = json.loads((SOURCE / 'acquisition.json').read_text())
    requests_by_site = {str(row['station_id']): row for row in acquisition}
    if len(acquisition) != len(requests_by_site) or set(requests_by_site) != set(cohort.station_id):
        raise ValueError('Acquisition log does not match cohort')
    allowed_parameters = {'f', 'time_series_id', 'properties', 'skipGeometry', 'limit', 'datetime'}
    for row in cohort.itertuples():
        if row.agency_code != 'USGS' or row.parameter_code != '00010' or row.statistic_id != '00003':
            raise ValueError('Unexpected agency, parameter or statistic')
        request = requests_by_site[row.station_id]
        url = urlsplit(request['url'])
        query = parse_qs(url.query)
        if (url.hostname != 'api.waterdata.usgs.gov' or
                set(query) != allowed_parameters or
                query['time_series_id'] != [row.series_id] or
                request['status'] != 200 or
                request.get('api_key_supplied') is not False):
            raise ValueError('Unexpected acquisition provenance or request parameters')
        with gzip.open(RAW / (row.station_id + '.json.gz'), 'rt') as stream:
            payload = json.load(stream)
        links = payload.get('links', [])
        self_links = [link for link in links if link.get('rel') == 'self']
        if len(self_links) != 1 or any(link.get('rel') == 'next' for link in links):
            raise ValueError('Snapshot missing self link or appears paginated')
        self_url = urlsplit(self_links[0]['href'])
        self_query = parse_qs(self_url.query)
        if (self_url.hostname != 'api.waterdata.usgs.gov' or
                set(self_query) != allowed_parameters or
                self_query['time_series_id'] != [row.series_id] or
                payload.get('numberReturned') != len(payload.get('features', []))):
            raise ValueError('Payload metadata does not match the selected series')
    return doc

def run_offline(root, script):
    # The analysis uses requests for acquisition; a cache miss is fatal rather
    # than silently downloading a different provider vintage.
    code = ("import sys,runpy,requests;sys.path[:0]=['scripts','src']; "
            "requests.sessions.Session.request=lambda *a,**k: "
            "(_ for _ in ()).throw(RuntimeError('network access disabled')); "
            f"sys.argv=['scripts/{script}'];runpy.run_path(sys.argv[0],run_name='__main__')")
    env = os.environ.copy()
    env.pop('USGS_WATERDATA_API_KEY', None)
    env.pop('USGS_API_KEY', None)
    env['PYTHONPATH'] = str(root / 'src')
    proc = subprocess.run([sys.executable, '-c', code], cwd=root, env=env, capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(f'{script} failed: ' + (proc.stdout + proc.stderr)[-3000:])

def compare_tables(root):
    for name in TABLES:
        kwargs = {'dtype': {'station_id': str, 'huc2': str}}
        original = pd.read_csv(SOURCE / name, **kwargs)
        rebuilt = pd.read_csv(root / 'results/additional_usgs_observed' / name, **kwargs)
        try:
            pd.testing.assert_frame_equal(original, rebuilt, check_dtype=False, rtol=1e-10, atol=1e-10)
        except AssertionError as exc:
            raise ValueError(f'Rebuilt {name} does not match saved results: {exc}') from exc

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest',type=Path,help='Use an explicit content manifest; historical default remains unchanged')
    parser.add_argument('--create-manifest',type=Path,help='Create a new content-pinned snapshot manifest; refuses to overwrite')
    parser.add_argument('--output', type=Path, default=ROOT / 'results/wrr_review_response_20261027/audit/usgs_observed_reproduction.json')
    args = parser.parse_args()
    if args.create_manifest:
        doc=create_manifest(args.create_manifest)
        print(json.dumps({'status':'new_manifest_created','station_count':doc['station_count']},indent=2))
        return
    report = {'scope': 'offline replay of additional USGS observation-only evidence from saved API payloads and included local code; independent arithmetic audit of reference years and reported witness windows',
              'limitations': 'Not an independent implementation of the original quality-based window selection; not sensor accuracy, continuous 24-hour sampling, reconstruction accuracy, climate transfer, or an end-to-end reproduction of the whole paper.'}
    try:
        manifest = verify_manifest(args.manifest)
        with tempfile.TemporaryDirectory(prefix='usgs_observed_replay_') as tmp:
            root = Path(tmp)
            for folder in ['scripts', 'configs', 'src', 'results/additional_usgs_observed', 'data/external/additional_usgs_observed/raw']:
                (root / folder).mkdir(parents=True, exist_ok=True)
            for name in ['525_external_observed_records.py', '572_reaudit_usgs_witnesses.py', 'wrr_tr_common.py', 'wrr_r3_common.py']:
                shutil.copy2(ROOT / 'scripts' / name, root / 'scripts' / name)
            shutil.copy2(ROOT / 'configs/wrr_target_recovery_20261022.json', root / 'configs')
            shutil.copytree(ROOT / 'src/stream_recoverability', root / 'src/stream_recoverability', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            for name in ['cohort_metadata.csv', 'raw_reference_summary.csv', 'robust_record_witnesses.csv']:
                shutil.copy2(SOURCE / name, root / 'results/additional_usgs_observed' / name)
            for site in pd.read_csv(SOURCE / 'cohort_metadata.csv', dtype={'station_id': str}).station_id:
                shutil.copy2(RAW / (site + '.json.gz'), root / 'data/external/additional_usgs_observed/raw' / (site + '.json.gz'))
            run_offline(root, '572_reaudit_usgs_witnesses.py')
            independent = json.loads((root / 'results/wrr_review_response_20261027/audit/usgs_observed_independent_reaudit.json').read_text())
            if not independent.get('passed'):
                raise ValueError('Independent witness arithmetic audit failed')
            run_offline(root, '525_external_observed_records.py')
            compare_tables(root)
            report.update({'status': 'passed', 'snapshot_files_verified': len(manifest['files']),
                           'station_count': independent['stations_acquired'], 'complete_reference_station_years': independent['complete_approved_station_years'],
                           'witness_station_years': independent['witness_station_years_checked'],
                           'tables_reproduced': TABLES, 'requests_http_disabled_for_analysis': True,
                           'selection_replayed_with_original_implementation': True,
                           'independent_arithmetic_audit_passed': True})
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        report.update({'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if report['status'] != 'passed':
        raise SystemExit(1)

if __name__ == '__main__':
    main()
