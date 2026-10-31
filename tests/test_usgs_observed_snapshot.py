"""The packaged USGS snapshot must match its cohort and recorded source."""
import gzip
import importlib.util
import json
import hashlib
from pathlib import Path
import pytest

SPEC = importlib.util.spec_from_file_location('usgs_snapshot', Path(__file__).resolve().parents[1] / 'scripts/652_verify_usgs_observed_reproduction.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

def snapshot(tmp_path, monkeypatch):
    source = tmp_path / 'results/additional_usgs_observed'
    raw = tmp_path / 'data/external/additional_usgs_observed/raw'
    audit = tmp_path / 'results/wrr_review_response_20261027/audit'
    for p in (source, raw, audit):
        p.mkdir(parents=True)
    site, series = '01234567', 'chosen-series'
    url = 'https://api.waterdata.usgs.gov/ogcapi/v1/collections/daily/items?f=json&time_series_id=chosen-series&properties=time,value,approval_status,qualifier&skipGeometry=true&limit=50000&datetime=1980%2F2026'
    (source / 'cohort_metadata.csv').write_text('station_id,series_id,agency_code,parameter_code,statistic_id\n01234567,chosen-series,USGS,00010,00003\n')
    (source / 'acquisition.json').write_text(json.dumps([{'station_id': site, 'url': url, 'status': 200, 'api_key_supplied': False}]))
    (source / 'plan.json').write_text('{}')
    for name in M.TABLES:
        (source / name).write_text('station_id\n01234567\n')
    (raw.parent / 'ATTRIBUTION.txt').write_text('Credit USGS')
    (raw / (site + '.json.gz')).write_bytes(gzip.compress(json.dumps({'features': [], 'numberReturned': 0, 'links': [{'rel': 'self', 'href': url}]}).encode()))
    files = [p for p in tmp_path.rglob('*') if p.is_file()]
    manifest = {'station_count': 1, 'files': [{'path': str(p.relative_to(tmp_path)),
                                           'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]}
    manifest_path = audit / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest))
    for key, value in {'ROOT': tmp_path, 'SOURCE': source, 'RAW': raw, 'MANIFEST': manifest_path}.items():
        monkeypatch.setattr(M, key, value)
    return source, manifest, manifest_path

def test_valid_snapshot_and_changed_input_rejected(tmp_path, monkeypatch):
    source, _, _ = snapshot(tmp_path, monkeypatch)
    assert M.verify_manifest()['station_count'] == 1
    (source / 'qualification.csv').write_text('changed')
    with pytest.raises(ValueError, match='changed'):
        M.verify_manifest()

def test_manifest_cannot_silently_omit_an_output(tmp_path, monkeypatch):
    _, manifest, path = snapshot(tmp_path, monkeypatch)
    manifest['files'] = [x for x in manifest['files'] if not x['path'].endswith('qualification.csv')]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='required evidence'):
        M.verify_manifest()
