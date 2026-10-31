#!/usr/bin/env python3
"""Recompute peak-visibility aggregates from a separate local case subset."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'private/wrr_review_case_evidence_20261027'
RESULT=ROOT/'results/wrr_review_response_20261027/whole_archive'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def compare(a,b,keys):
    if set(a.columns)!=set(b.columns):raise ValueError('aggregate column sets differ')
    a=a.sort_values(keys).reset_index(drop=True);b=b.sort_values(keys).reset_index(drop=True)
    if a.duplicated(keys).any() or b.duplicated(keys).any() or len(a)!=len(b):raise ValueError('aggregate keys or denominators differ')
    for col in a:
        if pd.api.types.is_numeric_dtype(a[col]) and pd.api.types.is_numeric_dtype(b[col]):
            if not np.allclose(a[col],b[col],rtol=0,atol=1e-12,equal_nan=True):raise ValueError(f'aggregate differs: {col}')
        elif not a[col].equals(b[col]):raise ValueError(f'aggregate keys or labels differ: {col}')
    return len(a)*len(a.columns)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,default=DEFAULT)
    parser.add_argument('--result',type=Path,default=RESULT);args=parser.parse_args()
    report_path=args.evidence/'peak_visibility_case_subset_audit.json'
    try:
        status=json.loads((args.result/'peak_visibility_status.json').read_text())
        if status['status']!='passed':raise ValueError('workspace analysis status is not passed')
        m=load('local_peak_visibility',ROOT/'scripts/578_peak_visibility_diagnostics.py')
        scoring=load('local_peak_scoring',ROOT/'scripts/576_verify_private_annual_predictions.py')
        frame=m.load_cases(args.evidence)
        rows,pairs,cohorts=m.evaluate(frame,scoring,int(status['bootstrap_draws']))
        names=['peak_visibility_annual.csv','peak_visibility_paired.csv','peak_visibility_cohorts.csv']
        keys=[['family','mode','stratum','estimator'],['family','mode','stratum'],['family','mode']]
        counts=[compare(a,pd.read_csv(args.result/n),k) for a,n,k in zip([rows,pairs,cohorts],names,keys)]
        report={'status':'passed','case_rows':len(frame),'aggregate_cells_compared':dict(zip(names,counts)),
                'tolerance':1e-12,'scope':'separate local case subset versus workspace case files; same models and complete reference, no refit or external validation'}
    except Exception as exc:
        report={'status':'failed','error':f'{type(exc).__name__}: {exc}'}
    report_path.write_text(json.dumps(report,indent=2)+'\n');report_path.chmod(0o600)
    print(json.dumps(report,indent=2))
    if report['status']!='passed':raise SystemExit(1)

if __name__=='__main__':main()
