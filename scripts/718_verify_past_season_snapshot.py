#!/usr/bin/env python3
"""Replay past-only warm-season screening from the included 95-station snapshot.

This does not reconstruct historical data vintages or validate source sensors,
quality control, final station selection or independent-climate transfer.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/past_season_screening'
DEFAULT=ROOT/'results/wrr_review_response_20261027/audit/past_season_snapshot_reproduction.json'
TABLES=['station_year_decisions.csv','witness_decisions.csv','summary.csv','transitions.csv']

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=DEFAULT);a=p.parse_args()
    amendment=json.loads((OUT/'multirule_correction.json').read_text())
    with tempfile.TemporaryDirectory(prefix='wrr_past_season_') as folder:
        generated=Path(folder)
        run=subprocess.run([sys.executable,str(ROOT/amendment['replacement_script']),'--output',str(generated)],cwd=ROOT,capture_output=True,text=True)
        if run.returncode:raise RuntimeError('Past-only screening failed: '+(run.stdout+run.stderr)[-3000:])
        for name in TABLES:
            try:pd.testing.assert_frame_equal(pd.read_csv(generated/name),pd.read_csv(OUT/name),check_dtype=False,check_exact=False,rtol=0,atol=1e-9)
            except AssertionError as error:raise ValueError('Past-only reproduced table differs: '+name) from error
        shutil.copyfile(OUT/'plan.json',generated/'plan.json')
        shutil.copyfile(OUT/'multirule_correction.json',generated/'multirule_correction.json')
        spec=importlib.util.spec_from_file_location('past_independent_snapshot',ROOT/'scripts/716_past_season_independent_audit.py')
        independent=importlib.util.module_from_spec(spec);spec.loader.exec_module(independent);independent.OUT=generated
        independent.main()
        checked=json.loads((generated/'independent_audit.json').read_text())
        original=json.loads((OUT/'independent_audit.json').read_text())
        if checked!=original:raise ValueError('Independent past-only audit differs')
        report={'status':'passed','input':'included 95-station project-processed daily snapshot and supplied station groups',
                'tables_reproduced':len(TABLES),'station_years':checked['station_years_independently_reconstructed'],
                'decisions':checked['rule_decisions_checked'],'future_perturbation_probes':checked['target_and_future_perturbation_probes'],
                'limits':'Current-vintage data and retrospective station selection; not original provider QC, physical measurement validation or prospective evidence.'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
