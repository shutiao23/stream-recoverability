#!/usr/bin/env python3
"""Independent W0--W4 review; no manuscript or production-result edits.

Checks the published algebra with a counterexample, compares the new numerical
tables against the preceding independent review, and checks provenance hashes.
"""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'results/wrr_revision_review_20261101'
NEW=ROOT/'results/wrr_final_revision_20261031'
OLD=ROOT/'results/wrr_stanford_perspective_20261031'
OUT.mkdir(parents=True,exist_ok=True)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, report):
    (OUT/name).write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def algebra():
    years=np.arange(2000,2006);x=(years-years.mean())/10
    h=x.copy();full=x/(x@x)
    clipped=full.copy();clipped[-1]=0
    subset=np.zeros(6);xs=(years[:-1]-years[:-1].mean())/10;subset[:-1]=xs/(xs@xs)
    d=subset-full
    report=dict(reference_years=years.tolist(),retained_years=years[:-1].tolist(),annual_sequence='Centered strictly linear annual anomaly; slope 1 C per decade',full_slope=float(full@h),correct_selected_slope=float(subset@h),SI_clipped_selected_slope=float(clipped@h),SI_clipped_weight_sum=float(clipped.sum()),correct_difference_sum=float(d.sum()),correct_difference_dot_year=float(d@x),correct_weight_distance=float(d@d),correct_variance_coefficient=float(1/(xs@xs)-1/(x@x)),SI_full_center_variance_coefficient=float(1/(x[:-1]@x[:-1])-1/(x@x)),conclusion='The SI definitions of subset weights and subset Sxx are incorrect; the production code recomputes the subset mean and implements the correct weights.')
    assert abs(report['correct_selected_slope']-1)<1e-12
    assert abs(report['SI_clipped_selected_slope']-1)>.1
    assert abs(report['correct_weight_distance']-report['correct_variance_coefficient'])<1e-12
    save('published_algebra_counterexample.json',report)


def compare_tables():
    keys=['family','station_key','replicate','independence_group','scheme']
    new=pd.read_csv(NEW/'retention_geometry_cases.csv').set_index(keys).sort_index()
    old=pd.read_csv(OLD/'retention_geometry_cases.csv').set_index(keys).sort_index()
    assert new.index.is_unique and old.index.is_unique and new.index.equals(old.index)
    assert set(new.columns)==set(old.columns)
    old=old[new.columns]
    numeric=[c for c in new if pd.api.types.is_numeric_dtype(new[c])]
    differences={}
    for c in numeric:
        a,b=new[c].to_numpy(float),old[c].to_numpy(float)
        assert np.array_equal(np.isnan(a),np.isnan(b)),c
        finite=np.isfinite(a)&np.isfinite(b)
        assert np.all(np.isfinite(a)|np.isnan(a)) and np.all(np.isfinite(b)|np.isnan(b)),c
        difference=float(np.max(abs(a[finite]-b[finite]))) if finite.any() else 0.
        assert difference<1e-10,(c,difference)
        differences[c]=difference
    for c in set(new.columns)-set(numeric):
        assert new[c].fillna('<NA>').equals(old[c].fillna('<NA>')),c
    save('independent_case_table_comparison.json',dict(status='passed',rows=len(new),key_unique=True,keys_and_missingness_match=True,all_columns_compared=True,finite_max_difference=max(differences.values()),per_column_max_difference=differences,scope='New production output compared with the prior reviewer implementation, using keys, nonnumeric values, explicit NaN masks and finite numeric tolerances.'))
    original=new.reset_index();perturbed=original.copy()
    index=int(np.flatnonzero(perturbed.estimate_mse.notna())[0]);perturbed.loc[index,'estimate_mse']+=1.
    columns=[c for c in original if pd.api.types.is_numeric_dtype(original[c])]
    legacy_max=np.max(abs(original[columns].to_numpy(float)-perturbed[columns].to_numpy(float)))
    summary=1.11e-16;reported=max([summary,legacy_max,3.552713678800501e-15,3.552713678800501e-15])
    save('nan_comparator_counterexample.json',dict(numeric_nan_cells=int(original[columns].isna().sum().sum()),injected_column='estimate_mse',injected_finite_change=1.0,legacy_per_table_difference_is_nan=bool(np.isnan(legacy_max)),legacy_aggregate_max=float(reported),legacy_tolerance_test_passes=bool(reported<=1e-12),conclusion='The numeric max used in 983 cannot certify the case table when structural NaNs are present.'))


def manifest():
    record=json.loads((NEW/'data_manifest.json').read_text());rows=[]
    for relative,h in record['outputs'].items():
        path=ROOT/relative if relative.startswith('paper/') else NEW/relative
        rows.append(dict(path=relative,recorded=h,current=sha(path) if path.exists() else None,matches=h is not None and path.exists() and h==sha(path)))
    input_changes=[]
    for relative,h in record['inputs'].items():
        path=ROOT/relative
        if not path.exists() or sha(path)!=h:input_changes.append(relative)
    save('extension_manifest_audit.json',dict(outputs=rows,output_mismatches=[r['path'] for r in rows if not r['matches']],input_mismatches=input_changes,explanation='The generator hashes data_manifest.json and scope.json before overwriting them; package-level hashes are a separate check.'))


if __name__=='__main__':
    algebra();compare_tables();manifest()
    save('review_scope.json',dict(date='2026-11-01 Asia/Shanghai',version='7ac1c2e0327afb665ef0c0554e5f81fd9489c7c6478367579785f4e15c1d9feb',inputs_sha256={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'paper/wrr_tr/review_completion_article.tex',ROOT/'paper/wrr_tr/stanford_geometry_supporting.tex',ROOT/'scripts/980_final_release.py',ROOT/'scripts/981_stanford_revision.py',ROOT/'scripts/983_verify_extension_replay.py',NEW/'retention_geometry_cases.csv',NEW/'data_manifest.json',NEW/'scope.json']},production_artifacts_changed=False))
    print('Independent algebra, case-table and manifest checks completed',flush=True)
