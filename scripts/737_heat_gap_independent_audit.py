#!/usr/bin/env python3
"""Independently rebuild matched masks and paired scores from stored inputs.

The same panels, forcing, seeds and fitted predictions are reused; this is
not independent climate validation or a repeat of the daily model fitting.
"""
from __future__ import annotations
import os
for v in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[v]='1'
import calendar
from collections import Counter
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'heat_gap_matched'
PRIVATE=ROOT/'private/wrr_heat_gap_matched_20261027';RUN=PRIVATE/'run'
BASE=REV/'whole_archive';OLD=ROOT/'private/wrr_expanded_stress_20261027/heat_associated_matched'
KEY=['station_key','replicate','estimator','retention','dependence']
DEPS=['point','independent','shared_parameters','residual_blocks'];METHODS=['D2','stochastic_calibrated']


def independent_assignment(base,heat):
    chosen=set(heat);common=set(base)&chosen
    out={y:base[y] for y in common};remaining=set(chosen)-common
    def end(s):return max(sum(map(int,t.split(':'))) for t in str(s).split(';'))
    ordered=sorted((y for y in base if y not in common),key=lambda y:(-end(base[y]),int(y)))
    for source_year in ordered:
        options=sorted((y for y in remaining if end(base[source_year])<=365+calendar.isleap(int(y))),
                       key=lambda y:(calendar.isleap(int(y)),int(y)))
        if not options:raise ValueError('No feasible year for frozen template')
        out[options[0]]=base[source_year];remaining.remove(options[0])
    if remaining:raise ValueError('Unused selected heat year')
    return out


def independent_masks():
    old=T.load_script('independent_heat_masks',ROOT/'scripts/692_expanded_stress_independent_audit.py')
    core=T.load_script('independent_heat_jobs',ROOT/'scripts/431_tr_cases.py')
    jobs={j['station_key']:j for j in core.jobs_for('source')}
    roster=pd.read_csv(ROOT/'private/wrr_expanded_stress_20261027/roster.csv')
    ref=pd.read_parquet(ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet',
                        columns=['station_key','year','design_family','mask_runs'])
    n=0;finite_base=finite_new=slots_base=slots_new=0
    for station in roster.station_key:
        sub=ref[ref.station_key.eq(station)&ref.design_family.eq('crossed')]
        for rep in range(5):
            baseline,heat,panel=old.rebuild(jobs[station],sub,rep)
            if heat is None:raise ValueError('Unavailable air reference in frozen cohort')
            suffix=Path('crossed/forward')/f'replicate_{rep:02d}'/station.replace('|','_')
            base=json.loads((BASE/suffix/'design.json').read_text())['masks']
            previous=json.loads((OLD/suffix/'design.json').read_text())['masks']
            current=json.loads((RUN/suffix/'design.json').read_text())
            if baseline!=base or heat!=previous:raise ValueError('Independent prior-year or gap selection differs')
            expected=independent_assignment(baseline,heat)
            if current['masks']!=expected or Counter(current['masks'].values())!=Counter(baseline.values()):
                raise ValueError('Independent matched template assignment differs')
            if current['hidden_values_present_in_visible_archive']!=0:raise ValueError('Hidden target remains visible')
            for masks,side in [(baseline,'baseline'),(current['masks'],'matched')]:
                finite=slots=0
                for year,runs in masks.items():
                    block=panel.loc[panel.index.year==int(year),jobs[station]['station_id']]
                    for item in runs.split(';'):
                        start,length=map(int,item.split(':'));part=block.iloc[start:start+length]
                        slots+=len(part);finite+=int(np.isfinite(part.to_numpy(float)).sum())
                if side=='baseline':finite_base+=finite;slots_base+=slots
                else:finite_new+=finite;slots_new+=slots
            n+=1
    if n!=205:raise ValueError('Incorrect independent mask denominator')
    return n,{'baseline_slots':slots_base,'baseline_finite_target_values':finite_base,
              'matched_slots':slots_new,'matched_finite_target_values':finite_new}


def read_trends(folder):
    f=pd.read_csv(folder/'trends.csv')
    f=f[(f.family=='crossed')&(f['mode']=='forward')&(f.replicate<5)&(f.retention=='all')
        &f.estimator.isin(METHODS)&f.dependence.isin(DEPS)]
    if len(f)!=1640 or f.duplicated(KEY).any():raise ValueError('Original trend table is incomplete')
    return f


def compare(v,expect,name):
    if not np.isclose(v,expect,atol=1e-10,rtol=1e-10,equal_nan=True):raise ValueError('Recomputed value differs: '+name)


def audit_scores():
    saved=pd.read_csv(OUT/'paired_summary.csv');regional=pd.read_csv(OUT/'leave_region_out.csv')
    lefts={'baseline_vs_matched':BASE,'previous_heat_vs_matched':OLD};right=read_trends(RUN);n=0;regions=0
    for label,folder in lefts.items():
        left=read_trends(folder)
        x=left.merge(right,on=KEY,suffixes=('_left','_right'),validate='one_to_one')
        if len(x)!=1640:raise ValueError('Paired identities differ')
        for di,dep in enumerate(DEPS):
            a=x[x.dependence.eq(dep)]
            flags={}
            for key,g in a.groupby(['station_key','replicate']):
                flags[key]=len(g)==2 and all(g.available_left & g.available_right)
            for mi,method in enumerate(METHODS):
                g=a[a.estimator.eq(method)]
                for scope in ['estimator_common','both_methods_common']:
                    good=g.available_left & g.available_right
                    if scope=='both_methods_common':good &= np.array([flags[k] for k in zip(g.station_key,g.replicate)],dtype=bool)
                    q=g[good];row=saved[(saved.comparison==label)&(saved.estimator==method)&(saved.dependence==dep)&(saved.scope==scope)]
                    if len(row)!=1:raise ValueError('Summary row missing')
                    r=row.iloc[0]
                    for name,val in [('n_eligible',len(g)),('n_common',len(q)),('groups',q.independence_group_left.nunique()),
                                     ('left_available',g.available_left.sum()),('right_available',g.available_right.sum())]:
                        if int(r[name])!=int(val):raise ValueError('Denominator differs: '+name)
                    if len(q):
                        delta=q.squared_error_right-q.squared_error_left
                        for name,val in [('left_rmse',np.sqrt(q.squared_error_left.mean())),('right_rmse',np.sqrt(q.squared_error_right.mean())),
                                         ('mse_difference',delta.mean()),('equal_group_mse_difference',q.assign(d=delta).groupby('independence_group_left').d.mean().mean())]:compare(val,r[name],name)
                        names=sorted(q.independence_group_left.unique())
                        sums=np.array([delta[q.independence_group_left.eq(name)].sum() for name in names])
                        counts=np.array([q.independence_group_left.eq(name).sum() for name in names])
                        seed=73600+1000*(['baseline_vs_matched','previous_heat_vs_matched'].index(label))+100*di+10*mi+(scope=='both_methods_common')
                        draw=np.random.default_rng(seed).integers(len(names),size=(4000,len(names)))
                        boot=sums[draw].sum(axis=1)/counts[draw].sum(axis=1)
                        compare(np.quantile(boot,.025),r.bootstrap_low,'bootstrap lower')
                        compare(np.quantile(boot,.975),r.bootstrap_high,'bootstrap upper')
                        if dep!='point':
                            for metric in ['missing_coverage95','width95','interval_score95']:
                                for side in ['left','right']:compare(q[metric+'_'+side].mean(),r[side+'_'+metric],metric)
                    if scope=='both_methods_common':
                        for region in sorted(q.region_left.unique()):
                            k=q[q.region_left!=region]
                            row=regional[(regional.comparison==label)&(regional.estimator==method)&(regional.dependence==dep)&(regional.excluded_region==region)]
                            if len(row)!=1 or int(row.iloc[0].n_common)!=len(k):raise ValueError('Leave-region denominator differs')
                            compare(np.sqrt(k.squared_error_left.mean()),row.iloc[0].left_rmse,'leave region left RMSE')
                            compare(np.sqrt(k.squared_error_right.mean()),row.iloc[0].right_rmse,'leave region right RMSE')
                            regions+=1
                    n+=1
    if n!=len(saved) or regions!=len(regional):raise ValueError('Unverified summary rows remain')
    return n,regions


def main():
    n,visible=independent_masks();cells,regions=audit_scores()
    report={'status':'passed','independent_masks_checked':n,'paired_summary_rows_checked':cells,
            'leave_region_rows_checked':regions,'original_target_values_in_scheduled_gaps':visible,
            'scope':'Reconstructs selected masks from the original seed and air series, then directly pairs saved trend results and recomputes summary cells and seeded group-bootstrap quantiles. The data, fitted models and daily refits are shared; physical data quality, causal attribution and external validity are not independently established.'}
    (OUT/'independent_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
