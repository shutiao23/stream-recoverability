import csv
import gzip
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

def test_reference_replay_checks_distinct_slots_finite_values_and_fixed_mst(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / 'scripts/829_usace_open_reference_replay.py'
    spec = importlib.util.spec_from_file_location('usace_open_replay', script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    data = tmp_path / 'data'
    rev = tmp_path / 'results'
    data.mkdir()
    target = data / 'input.csv.gz'
    start = datetime(2024, 1, 1, 7, tzinfo=timezone.utc)
    with gzip.open(target, 'wt', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp', 'temp_degC'])
        for i in range(96):
            writer.writerow([(start + timedelta(minutes=15 * i)).isoformat(), '12.0'])
        for i in range(96):
            # Duplicate one quarter-hour in the second day.
            writer.writerow([(start + timedelta(days=1, minutes=15 * min(i, 94))).isoformat(), '12.0'])
        for i in range(96):
            writer.writerow([(start + timedelta(days=2, minutes=15 * i)).isoformat(), '' if i == 17 else '12.0'])
    manifest = {'records': [{'resource_id': 'site', 'file': target.name, }]}
    (data / 'manifest.json').write_text(json.dumps(manifest))
    annual = rev / 'external_usace_reservoir'
    annual.mkdir(parents=True)
    (annual / 'finite_reference_years.csv').write_text('resource_id,year,reported_days,complete_finite_days,expected_days,finite_reference_year\nsite,2024,3,1,366,False\n')
    monkeypatch.setattr(mod, 'DATA', data)
    monkeypatch.setattr(mod, 'REV', rev)
    mod.main()
    result = json.loads((rev / 'audit/usace_open_reference_replay.json').read_text())
    assert result['status'] == 'passed'
    assert result['complete_finite_days'] == 1
    assert result['complete_finite_years'] == 0
