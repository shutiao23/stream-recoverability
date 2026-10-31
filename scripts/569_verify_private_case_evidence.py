#!/usr/bin/env python3
"""Recalculate selected manuscript statistics from local case-evidence files.

This does not re-read raw daily source data or refit models. The case table may
contain restricted third-party derivatives and must stay local until rights are
resolved. Run from the package code with an explicit evidence directory.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd
from stream_recoverability.experiments.tr_revision.archive import factorial_contrasts

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'private/wrr_review_case_evidence_20261027'


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def compare(actual,expected,keys,columns,tol=1e-8):
    if actual.duplicated(keys).any() or expected.duplicated(keys).any():raise ValueError(f'duplicate comparison keys: {keys}')
    merged=actual.merge(expected,on=keys,how='outer',suffixes=('_actual','_expected'),indicator=True,validate='one_to_one')
    if not merged._merge.eq('both').all():raise ValueError(f'missing comparison rows for {keys}')
    for c in columns:
        a=pd.to_numeric(merged[c+'_actual'],errors='raise').to_numpy(float)
        b=pd.to_numeric(merged[c+'_expected'],errors='raise').to_numpy(float)
        if not np.isclose(a,b,rtol=1e-8,atol=tol,equal_nan=True).all():raise ValueError(f'metric {c} differs for keys {keys}')
    return len(merged)*len(columns)


def verify(root):
    rev=root/'results/wrr_review_response_20261027';arch=rev/'whole_archive';rel=rev/'release_outputs';integ=rev/'integrated_release_trend'
    checks={}
    # Independent window arithmetic uses saved 30 values; complete-year maxima
    # remain assertions in the certificate, because raw full years are absent.
    witness_specs=[('results/wrr_review_completion_20261024/observed_records/observed_record_certificates.csv',
                    'verified_daily_values','observed_window_mean','maximum_complete_year_H30','record_excess_lower_bound'),
                   ('results/additional_usgs_observed/robust_record_witnesses.csv',
                    'approved_window_values','window_mean','maximum_raw_complete_H30','excess')]
    n_witness=0
    for path,values_col,mean_col,max_col,excess_col in witness_specs:
        f=pd.read_csv(root/path)
        for r in f.itertuples(index=False):
            v=[float(x) for x in getattr(r,values_col).split(';')]
            if len(v)!=30 or not np.isfinite(v).all():raise ValueError('invalid witness daily values')
            if abs(np.mean(v)-getattr(r,mean_col))>1e-8:raise ValueError('witness window mean mismatch')
            if abs(getattr(r,mean_col)-getattr(r,max_col)-getattr(r,excess_col))>1e-8:raise ValueError('witness excess mismatch')
            if (pd.Timestamp(r.observed_window_end)-pd.Timestamp(r.observed_window_start)).days!=29:raise ValueError('witness window not 30 calendar days')
        n_witness+=len(f)
    checks['witness_window_arithmetic']={'records':n_witness,'scope':'stored 30 values and recorded maxima; complete-reference maxima checked separately below'}
    # Re-run independent daily-reference arithmetic from the 96-station
    # canonical daily subset, not from native provider files.
    record=module('local_record_reaudit','570_reaudit_observed_records.py')
    record.ROOT=root;record.S=root/'results/wrr_review_completion_20261024/observed_records'
    record_result=record.audit()
    if not record_result['passed']:raise ValueError('canonical daily record re-audit failed')
    checks['canonical_daily_record_reaudit']={'stations':record_result['eligible_stations'],
        'complete_reference_years':record_result['reference_station_years_recomputed'],
        'incomplete_years':record_result['incomplete_station_years_recomputed'],
        'witnesses':record_result['certificate_station_years']}
    rules=module('local_rules_reaudit','571_reaudit_screening_rules.py')
    rules.ROOT=root;rules.RULES=root/'results/wrr_review_response_20261027/rules'
    rules.SOURCE=root/'results/wrr_review_completion_20261024/observed_records'
    rules_result=rules.audit()
    if not rules_result['passed']:raise ValueError('screening-rule re-audit failed')
    checks['canonical_daily_rule_reaudit']={'station_years':rules_result['station_years_checked'],
        'witness_rule_decisions':rules_result['witness_rule_decisions_checked'],
        'held_year_perturbations':rules_result['target_year_perturbation_probes'],
        'changed_climatology':rules_result['changed_climatology_probes']}
    usgs=module('local_usgs_reaudit','572_reaudit_usgs_witnesses.py')
    usgs_result=usgs.audit(root)
    if not usgs_result['passed']:raise ValueError('USGS daily reference re-audit failed')
    checks['usgs_daily_record_reaudit']={'stations':usgs_result['stations_acquired'],
        'complete_reference_years':usgs_result['complete_approved_station_years'],
        'witnesses':usgs_result['witness_station_years_checked']}
    a=pd.read_parquet(arch/'annual_case_evidence.parquet')
    keys=['family','mode','replicate','station_key','year']
    if a.duplicated(keys).any():raise ValueError('duplicate annual case identities')
    projection=module('local_projection','562_support_projection_diagnostics.py').summarize(a)
    expected=pd.read_csv(arch/'support_projection_summary.csv')
    projection_cols=[x for x in projection.columns if x not in ['family','mode','estimator']]
    checks['annual_boundary_summary_cells']=compare(projection,expected,['family','mode','estimator'],projection_cols)
    # Annual and trend summaries are recomputed from original case aggregates.
    annual=pd.read_csv(arch/'annual.csv')
    annual_recomputed=annual.groupby(['family','mode','estimator'],as_index=False).agg(
      n_eligible=('n_eligible','sum'),n_available=('n_available','sum'),mean_station_mae=('mae','mean'),
      mean_station_coverage90=('coverage90','mean'),mean_station_width90=('width90','mean'))
    checks['annual_summary_cells']=compare(annual_recomputed,pd.read_csv(arch/'annual_summary.csv'),
       ['family','mode','estimator'],['n_eligible','n_available','mean_station_mae','mean_station_coverage90','mean_station_width90'])
    trends=pd.read_csv(arch/'trends.csv');keys=['family','mode','estimator','retention','dependence'];rows=[]
    for key,g in trends.groupby(keys):
        valid=g.loc[g.available];row=dict(zip(keys,key))|{'n_eligible':len(g),'n_available':len(valid),'availability':len(valid)/len(g)}
        if len(valid):
            row|={'rmse':float(np.sqrt(valid.squared_error.mean())),'bias':float(valid.error.mean())}
            for col in ['missing_coverage95','width95','interval_score95']:
                row[col]=float(pd.to_numeric(valid[col],errors='coerce').mean())
        rows.append(row)
    checks['trend_summary_cells']=compare(pd.DataFrame(rows),pd.read_csv(arch/'trend_summary.csv'),keys,
        ['n_eligible','n_available','availability','rmse','bias','missing_coverage95','width95','interval_score95'])
    chosen=trends.loc[trends.dependence.eq('point')&trends.estimator.isin(['plug_in','stochastic_calibrated','D2'])]
    actual=factorial_contrasts(chosen)
    expected=pd.read_csv(arch/'factorial_contrasts.csv')
    fk=['family','mode','station_key','replicate','estimator']
    checks['factorial_case_cells']=compare(actual,expected,fk,['retention_at_plugin','retention_at_estimator','estimator_at_warm90','estimator_at_all','interaction','symmetric_retention','symmetric_estimator','total_gain'])
    records=pd.read_csv(rev/'annual/source_scorecard.csv');summaries=[]
    for (family,stratum,method),g in records.groupby(['family','stratum','estimator']):
        row=dict(family=family,stratum=stratum,estimator=method,n_seeds=g.seed.nunique())
        for col in ['mae','bias','failure_rate','coverage90','width90','interval_score90','crps','twcrps','availability']:
            vals=g[col].dropna()
            if len(vals):row.update({col+'_median':vals.median(),col+'_lower':vals.quantile(.025),col+'_upper':vals.quantile(.975)})
        summaries.append(row)
    saved=pd.read_csv(rev/'annual/source_scorecard_summary.csv');actual=pd.DataFrame(summaries)
    checks['source_seed_summary_cells']=compare(actual,saved,['family','stratum','estimator'],[x for x in saved.columns if x not in ['family','stratum','estimator']])
    # Release policies all operate on same saved cases; checks do not train scores.
    metrics=pd.read_csv(rel/'release_metrics.csv');matched=pd.read_csv(rel/'matched_numerical_retention.csv')
    matcher=module('local_matched_release','556_release_matched_retention.py');n=0;nm=0
    thresholds=pd.read_csv(rel/'source_rule_thresholds.csv')
    source_summary=pd.read_csv(rel/'source_calibrated_release_summary.csv')
    for condition in ['clean','air_exposure','hot_year_extrapolation','future_years','smooth_non_air_shift']:
        d=pd.read_parquet(rel/(condition+'.parquet'))
        for family,b in d.groupby('design_family'):
            for method in ['estimate_all','warm90_plugin','fixed_risk','three_outputs']:
                keep={'estimate_all':b.D2.notna(),'warm90_plugin':b.warm_observed_fraction.ge(.9)&b.h30__policy.notna(),
                      'fixed_risk':b.risk_score.le(.1)&b.D2.notna(),'three_outputs':b.output.eq('estimate')}[method]
                point=b.h30__policy if method=='warm90_plugin' else b.D2
                error=(point-b.eval_truth_h30).abs();r=metrics.loc[metrics.condition.eq(condition)&metrics.family.eq(family)&metrics.method.eq(method)].iloc[0]
                values={'n_eligible':len(b),'n_published':int(keep.sum()),'n_bad':int((keep&error.gt(.5)).sum()),
                        'retention':float(keep.mean()),'risk':float(error[keep].gt(.5).mean()) if keep.any() else np.nan,
                        'mae':float(error[keep].mean()) if keep.any() else np.nan}
                for col,val in values.items():
                    if not np.isclose(val,r[col],rtol=1e-8,atol=1e-8,equal_nan=True):raise ValueError(f'release mismatch {condition}/{family}/{method}/{col}')
                    n+=1
            chosen=b.output.eq('estimate').to_numpy();baseline,_,_=matcher.select_score_only(b,int(chosen.sum()))
            bad=(b.D2-b.eval_truth_h30).abs().gt(.5).to_numpy();r=matched.loc[matched.condition.eq(condition)&matched.family.eq(family)].iloc[0]
            for col,val in {'n_eligible':len(b),'n_equal_numerical':int(chosen.sum()),'three_output_bad':int((chosen&bad).sum()),'score_only_bad':int((baseline&bad).sum())}.items():
                if int(r[col])!=val:raise ValueError(f'matched release mismatch {condition}/{family}/{col}')
                nm+=1
        if condition=='clean':
            c=d.merge(thresholds[['region','family','score_cutoff']],left_on=['region','design_family'],right_on=['region','family'],how='left',indicator=True,validate='many_to_one')
            if not c._merge.eq('both').all():raise ValueError('missing source threshold')
            for family,b in c.groupby('design_family'):
                for method in ['three_outputs','score_only']:
                    keep=b.output.eq('estimate') if method=='three_outputs' else b.risk_score.le(b.score_cutoff)&b.D2.notna()
                    bad=(b.D2-b.eval_truth_h30).abs().gt(.5)
                    r=source_summary.loc[source_summary.family.eq(family)&source_summary.method.eq(method)].iloc[0]
                    if int(r.n_eligible)!=len(b) or int(r.n_published)!=int(keep.sum()) or int(r.n_bad)!=int((keep&bad).sum()):raise ValueError('source-threshold target counts mismatch')
    checks['release_summary_cells']=n;checks['matched_release_count_cells']=nm;checks['source_threshold_target_counts']='passed'
    # Validate annual state partition and arithmetic on saved trend estimates.
    decisions=pd.read_parquet(integ/'annual_decisions.parquet');keys=['family','mode','station_key','replicate']
    if decisions.duplicated(keys+['year']).any():raise ValueError('duplicate release-year decision')
    states=decisions.groupby(keys+['output_state']).size().unstack(fill_value=0)
    for state in ['estimate','observed_bound','unknown']:
        if state not in states:states[state]=0
    states=states[['estimate','observed_bound','unknown']].reset_index()
    reps=pd.read_csv(integ/'station_repetitions.csv');joined=reps.merge(states,on=keys,how='left',validate='many_to_one')
    for left,right in [('n_estimates','estimate'),('n_bounds','observed_bound'),('n_unknown','unknown')]:
        if not joined[left].eq(joined[right]).all():raise ValueError('integrated state count mismatch')
    if not joined.n_masked.eq(joined.estimate+joined.observed_bound+joined.unknown).all():raise ValueError('integrated denominator mismatch')
    selected=joined.loc[joined.available]
    if not np.allclose(selected.slope-selected.truth_slope,selected.error,atol=1e-8) or not np.allclose(selected.error**2,selected.squared_error,atol=1e-8):raise ValueError('integrated slope error mismatch')
    checks['integrated_release_rows']={'annual_decisions':len(decisions),'station_method_rows':len(reps),'available_slope_rows':len(selected)}
    return checks


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,default=DEFAULT);a=p.parse_args()
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'scope':'local case arithmetic and aggregation only',
            'not_tested':['provider-native raw measurements for the 96 source stations','subdaily USGS observations','measurement error and source provenance','re-estimation of underlying predictive models','20 source-seed case predictions (see separate annual_source_case_audit.json)','source-model and threshold fitting','joint random draws','rights and external availability']}
    try:report['checks']=verify(a.evidence);report['status']='passed'
    except Exception as exc:report.update(status='failed',error=f'{type(exc).__name__}: {exc}')
    out=a.evidence/'local_case_audit.json';out.write_text(json.dumps(report,indent=2)+'\n');out.chmod(0o600)
    print(json.dumps(report,indent=2))
    if report['status']!='passed':raise SystemExit(1)

if __name__=='__main__':main()
