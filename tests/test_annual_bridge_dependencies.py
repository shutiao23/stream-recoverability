import importlib.util
import json
import hashlib
from pathlib import Path
import sys
import pytest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('annual_bridge_export',SCRIPTS/'575_export_private_annual_predictions.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_export_rejects_missing_or_changed_bridge_repair(tmp_path,monkeypatch):
    repair=tmp_path/'results/wrr_review_completion_20261024/repairs/leave_one_year_out/seed_00.parquet'
    repair.parent.mkdir(parents=True);repair.write_bytes(b'bridge')
    audit=tmp_path/'results/wrr_review_response_20261027/audit';audit.mkdir(parents=True)
    effect=audit/'annual_bridge_repair_effect.csv';effect.write_bytes(b'effect')
    script=tmp_path/'scripts/730_annual_bridge_dependency.py';script.parent.mkdir();script.write_bytes(b'script')
    report={'status':'passed','seeds_checked':20,'input_sha256':{
        str(p.relative_to(tmp_path)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [repair,effect,script]}}
    (audit/'annual_bridge_repair_dependency.json').write_text(json.dumps(report))
    monkeypatch.setattr(m.T,'ROOT',tmp_path)
    m.verify_bridge_repair(0)
    repair.write_bytes(b'changed')
    with pytest.raises(ValueError,match='missing or changed'):m.verify_bridge_repair(0)
    repair.unlink()
    with pytest.raises(ValueError,match='missing or changed'):m.verify_bridge_repair(0)
    repair.write_bytes(b'bridge');report.pop('input_sha256')
    (audit/'annual_bridge_repair_dependency.json').write_text(json.dumps(report))
    with pytest.raises(ValueError,match='missing or changed'):m.verify_bridge_repair(0)
