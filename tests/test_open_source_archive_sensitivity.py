"""Fixed-mask sensitivity must preserve targets and the unchanged comparator."""
import importlib.util
import json
import hashlib
from pathlib import Path
import sys
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('open_archive_sensitivity', SCRIPTS / '658_open_source_archive_sensitivity.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def rows():
    return pd.DataFrame([
        {'family': 'crossed', 'mode': 'forward', 'region': 'test', 'station_key': 'test|1', 'replicate': 0,
         'estimator': 'plug_in', 'retention': retention, 'dependence': 'point', 'available': True,
         'error': error, 'truth_slope': 0.2} for retention, error in [('all', 0.1), ('warm90', -0.2)]
    ])

def test_reanalysis_rejects_changed_plugin_or_reference(tmp_path):
    old = tmp_path / 'old'; new = tmp_path / 'new'
    old.mkdir(); new.mkdir()
    frame = rows()
    frame.to_csv(old / 'trends.csv', index=False)
    frame.iloc[::-1].to_csv(new / 'trends.csv', index=False)
    m.verify_plugin(old, new)
    changed = frame.copy(); changed.loc[0, 'truth_slope'] = 0.21
    changed.to_csv(new / 'trends.csv', index=False)
    with pytest.raises(ValueError, match='baseline or target reference'):
        m.verify_plugin(old, new)

def test_reanalysis_rejects_missing_trend_identity(tmp_path):
    old = tmp_path / 'old'; new = tmp_path / 'new'
    old.mkdir(); new.mkdir()
    frame = rows()
    frame.to_csv(old / 'trends.csv', index=False)
    frame.iloc[:1].to_csv(new / 'trends.csv', index=False)
    with pytest.raises(ValueError, match='identities changed'):
        m.verify_plugin(old, new)

def test_reanalysis_requires_matching_bridge_repair(tmp_path, monkeypatch):
    out = tmp_path / 'audit'; out.mkdir()
    source = tmp_path / 'source'; repair = source / 'repairs/before_2010/seed_00.parquet'
    repair.parent.mkdir(parents=True); repair.write_bytes(b'repair')
    for name in ['plan.json', 'single_year_calibration_plan.json', 'archive_bridge_repair_effect.csv']:
        (out / name).write_text(name)
    script = tmp_path / 'scripts/731_open_archive_bridge_dependency.py'
    script.parent.mkdir(); script.write_text('audit')
    report = {'status': 'passed', 'repaired_calibrations_match_saved': True,
              'input_sha256':{str(p.relative_to(tmp_path)):hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in [repair,script,*[out/name for name in ['plan.json','single_year_calibration_plan.json','archive_bridge_repair_effect.csv']]]}}
    (out / 'archive_bridge_repair_dependency.json').write_text(json.dumps(report))
    monkeypatch.setattr(m, 'ROOT', tmp_path); monkeypatch.setattr(m, 'OUT', out)
    monkeypatch.setattr(m, 'SOURCE', source)
    m.verify_bridge_dependencies(['forward'])
    repair.write_bytes(b'changed')
    with pytest.raises(ValueError, match='missing or changed'):
        m.verify_bridge_dependencies(['forward'])
    repair.unlink()
    with pytest.raises(ValueError, match='missing or changed'):
        m.verify_bridge_dependencies(['forward'])
    repair.write_bytes(b'repair');report.pop('input_sha256')
    (out/'archive_bridge_repair_dependency.json').write_text(json.dumps(report))
    with pytest.raises(ValueError,match='missing or changed'):
        m.verify_bridge_dependencies(['forward'])
