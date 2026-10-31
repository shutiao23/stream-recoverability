#!/usr/bin/env python3
"""Reproduce seasonal-window evidence from the included 95-station snapshot.

Does not rebuild provider quality control, validate regulation labels against
provider records, or establish physical measurement accuracy or data rights.
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
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/summer_window_comparison'
DEFAULT=ROOT/'results/wrr_review_response_20261027/audit/summer_snapshot_reproduction.json'
TABLES=['complete_year_windows.csv','station_mean_gaps.csv','witness_comparison.csv','screening_counts.csv',
        'provider_summary.csv','influence_summary.csv','selected_station_peak_windows.csv']


def compare_json(a,b):
    if set(a)!=set(b):raise ValueError('Summary JSON fields differ')
    for key in a:
        x,y=a[key],b[key]
        if isinstance(x,(int,float)) and not isinstance(x,bool):
            if not isinstance(y,(int,float)) or not np.isclose(x,y,atol=1e-10,rtol=0,equal_nan=True):raise ValueError('Summary numeric field differs: '+key)
        elif x!=y:raise ValueError('Summary field differs: '+key)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=DEFAULT);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='wrr_summer_reproduction_') as folder:
        generated=Path(folder)
        for script in ['706_summer_window_compare.py','709_summer_influence.py']:
            process=subprocess.run([sys.executable,str(ROOT/'scripts'/script),'--output',str(generated)],cwd=ROOT,capture_output=True,text=True)
            if process.returncode:raise RuntimeError(script+' failed: '+(process.stdout+process.stderr)[-3000:])
        for name in TABLES:
            actual=pd.read_csv(generated/name);expected=pd.read_csv(OUT/name)
            try:pd.testing.assert_frame_equal(actual,expected,check_dtype=False,check_exact=False,rtol=0,atol=1e-9)
            except AssertionError as error:raise ValueError('Reproduced table differs: '+name) from error
        compare_json(json.loads((generated/'summary.json').read_text()),json.loads((OUT/'summary.json').read_text()))
        shutil.copyfile(OUT/'station_groups.csv',generated/'station_groups.csv')
        spec=importlib.util.spec_from_file_location('summer_snapshot_independent',ROOT/'scripts/707_summer_window_independent_audit.py')
        audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit);audit.OUT=generated
        audit.main()
        result=json.loads((generated/'independent_audit.json').read_text())
        expected=json.loads((OUT/'independent_audit.json').read_text())
        compare_json(result,expected)
        report={'status':'passed','input':'included 95-station processed daily snapshot and supplied station groups',
                'tables_reproduced':len(TABLES),'complete_station_years':result['complete_station_years_checked'],
                'witnesses':result['witnesses_checked'],'independent_rolling_audit':'passed',
                'limits':'Existing regulation labels and station selection are supplied inputs; provider-native records, sensor accuracy, climate representativeness and rights are not independently validated.'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
