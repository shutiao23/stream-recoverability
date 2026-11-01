#!/usr/bin/env python3
"""Fault-inject only 983's temporary reference copy, never the real package.

The verifier and its assertions run unchanged. Copying is wrapped solely to
change one expected comparison value after extraction; regeneration uses the
unaltered compact scientific inputs.
"""
from pathlib import Path
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import math
import sys

import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'results/wrr_revision_review_20261101/probes'


def clean(value):
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
    if isinstance(value,list):return [clean(v) for v in value]
    if isinstance(value,float) and not math.isfinite(value):return str(value)
    return value


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['baseline','numeric_case','label']);args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('review_983',ROOT/'scripts/983_verify_extension_replay.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    original_copytree=module.shutil.copytree
    mutations=[]
    def injected_copy(src,dst,*positional,**keyword):
        result=original_copytree(src,dst,*positional,**keyword)
        if Path(dst).name=='extension_reference' and args.mode!='baseline':
            filename='retention_geometry_cases.csv' if args.mode=='numeric_case' else 'retention_family_summary.csv'
            path=Path(dst)/filename;frame=pd.read_csv(path)
            column='estimate_mse' if args.mode=='numeric_case' else 'family'
            before=frame.loc[0,column]
            after=float(before)+1.0 if args.mode=='numeric_case' else 'reviewer_fault_injected_label'
            frame.loc[0,column]=after;frame.to_csv(path,index=False)
            mutations.append(dict(file=filename,row=0,column=column,before=str(before),after=str(after)))
        return result
    protected=[ROOT/'paper/wrr_tr/review_completion_article.tex',ROOT/'paper/wrr_tr/stanford_geometry_supporting.tex',ROOT/'results/wrr_final_revision_20261031/retention_geometry_cases.csv',ROOT/'results/wrr_final_revision_20261031/retention_family_summary.csv',ROOT/'results/final_release_20261031_r2/acceptance.json']
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    module.shutil.copytree=injected_copy
    receipt=OUT/(args.mode+'_verifier_receipt.json')
    previous_argv=sys.argv
    try:
        sys.argv=['983_verify_extension_replay.py','--archive',str(ROOT/'dist/wrr_final_candidate_20261031_r2.zip'),'--output',str(receipt)]
        with contextlib.redirect_stdout(io.StringIO()):code=module.main()
    finally:
        module.shutil.copytree=original_copytree;sys.argv=previous_argv
    result=json.loads(receipt.read_text())
    assert len(mutations)==(0 if args.mode=='baseline' else 1)
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    report=dict(mode=args.mode,actual_verifier_status=result['status'],actual_exit_code=code,expected_to_reject=args.mode!='baseline',mutations=mutations,reported_numeric_differences=clean(result.get('numeric_differences')),reported_maximum=clean(result.get('max_numeric_difference')),production_files_unchanged=True,scope='Only the temporary expected/reference copy is changed; the real candidate, compact inputs and original verification receipts are unchanged. This probes 983 numeric/label comparison, not package identity checks.')
    (OUT/(args.mode+'_probe.json')).write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps(report,ensure_ascii=False,allow_nan=False),flush=True)


if __name__=='__main__':main()
