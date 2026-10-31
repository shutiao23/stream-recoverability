#!/usr/bin/env python3
"""Audit two-method support intersection and candidate baseline alignment."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity'
PRIVATE=ROOT/'private/wrr_open_source_sensitivity_20261026/single_year_calibration'
KEY=['family','mode','replicate','station_key','year'];EST=['D2','stochastic_calibrated']

def main():
    audit=json.loads((OUT/'single_year_independent_audit.json').read_text())
    if audit['status']!='passed':
        raise ValueError('Independent calibration audit required or its inputs changed')
    cases=pd.read_parquet(PRIVATE/'target_cases.parquet');plans=pd.read_csv(OUT/'single_year_source_support.csv')
    if cases.duplicated(KEY+['estimator']).any() or plans.duplicated(['family','mode','region','estimator']).any():raise ValueError('Duplicate identities')
    wide=plans.pivot(index=['family','mode','region'],columns='estimator',values='status')
    if not set(EST).issubset(wide.columns):raise ValueError('Method support missing')
    expected_both=wide[EST].eq('supported_exploratory').all(axis=1).rename('expected_both').reset_index()
    expected_own=plans[['family','mode','region','estimator','status']]
    c=cases.merge(expected_both,on=['family','mode','region'],validate='many_to_one').merge(expected_own,on=['family','mode','region','estimator'],validate='many_to_one')
    if not c.both_supported.eq(c.expected_both).all() or not c.supported.eq(c.status.eq('supported_exploratory')).all():raise ValueError('Support flags differ from source statuses')
    counts=c.groupby(KEY).estimator.nunique()
    if not counts.eq(2).all():raise ValueError('Target cases do not contain both methods')
    summary=pd.read_csv(OUT/'single_year_target_summary.csv')
    baseline=pd.read_csv(OUT/'annual_sensitivity_scores.csv')
    baseline=baseline.loc[baseline.version.eq('candidate')]
    check=summary.loc[summary.scope.eq('both_methods_supported')].merge(baseline,on=['family','mode','stratum','estimator'],validate='one_to_one')
    if len(check)!=24 or not check.n_eligible.eq(check.n_common).all():raise ValueError('Candidate baseline denominator differs')
    for metric in ['coverage90','width90','interval_score90','zero90']:
        if not np.allclose(check['all_baseline_'+metric],check[metric],atol=1e-10,rtol=0,equal_nan=True):raise ValueError('Candidate baseline score differs: '+metric)
    report={'status':'passed','target_estimator_rows':len(c),'two_method_cases':len(counts),
            'source_support_flags_verified':True,'baseline_score_rows_reproduced':len(check),
            'limitation':'Checks selected cases and stored source support; does not establish calibration exchangeability, source representativeness, or independent-climate coverage.'}
    (OUT/'single_year_support_alignment.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        (OUT/'single_year_support_alignment.json').write_text(json.dumps({
            'status':'failed','error':f'{type(exc).__name__}: {exc}'
        },indent=2)+'\n')
        raise
