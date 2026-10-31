"""Public source subsets must not silently change or admit excluded sources."""
import importlib.util
import json
import hashlib
from pathlib import Path
import pandas as pd
import pytest

SPEC = importlib.util.spec_from_file_location('open_snapshot', Path(__file__).resolve().parents[1] / 'scripts/654_verify_open_observed_snapshot.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

def setup_snapshot(tmp_path, monkeypatch):
    for name in M.NEEDED:
        (tmp_path / name).write_bytes(b'snapshot')
    pd.DataFrame({'station_key': ['usgs|01', 'gkd_bayern|02', 'chmi|03', 'foen|04'],
                  'provider': ['usgs', 'gkd_bayern', 'chmi', 'foen']}).to_csv(tmp_path / 'source_roster.csv', index=False)
    pd.DataFrame({'station_key': ['usgs|01'], 'incomplete_year': [2000]}).to_csv(tmp_path / 'observed_record_certificates.csv', index=False)
    manifest = {'included_eligible_stations': 4, 'original_witnesses_included': 1,
                'included_by_provider': {'usgs': 1, 'gkd_bayern': 1, 'chmi': 1, 'foen': 1},
                'files': [{'path': name, 'sha256':hashlib.sha256((tmp_path/name).read_bytes()).hexdigest()} for name in sorted(M.NEEDED)]}
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(M, 'SNAPSHOT', tmp_path)
    return manifest

def test_valid_snapshot_and_changed_daily_are_distinguished(tmp_path, monkeypatch):
    setup_snapshot(tmp_path, monkeypatch)
    assert M.verify_snapshot()['included_eligible_stations'] == 4
    (tmp_path / 'daily_temperature.parquet').write_bytes(b'changed')
    with pytest.raises(ValueError, match='changed'):
        M.verify_snapshot()
    manifest=setup_snapshot(tmp_path,monkeypatch)
    manifest['files'][0].pop('sha256')
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='changed'):M.verify_snapshot()

def test_manifest_cannot_replace_an_attribution(tmp_path, monkeypatch):
    manifest = setup_snapshot(tmp_path, monkeypatch)
    manifest['files'] = [x for x in manifest['files'] if x['path'] != 'ATTRIBUTION.txt']
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='missing snapshot'):
        M.verify_snapshot()
