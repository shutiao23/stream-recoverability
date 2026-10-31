#!/usr/bin/env python3
"""Audit matched gap templates and compare paired whole-archive outcomes.

All station-level masks and prediction rows remain local. This post-hoc
comparison reuses source models, forcing, stations and target reference series.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
os.umask(0o077)
from collections import Counter
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027'
OUT=REV/'heat_gap_matched';PRIVATE=ROOT/'private/wrr_heat_gap_matched_20261027';RUN=PRIVATE/'run'
BASE=REV/'whole_archive';OLD=ROOT/'private/wrr_expanded_stress_20261027/heat_associated_matched'
KEY=['station_key','replicate','estimator','retention','dependence']
METHODS=['D2','stochastic_calibrated'];DEPS=['point','independent','shared_parameters','residual_blocks']


def verify_masks():
    inherited=T.load_script('matched_gap_old_audit',ROOT/'scripts/691_expanded_stress_comparison.py')
    core=T.load_script('matched_gap_jobs',ROOT/'scripts/431_tr_cases.py')
    jobs={j['station_key']:j for j in core.jobs_for('source')}
    roster=pd.read_csv(ROOT/'private/wrr_expanded_stress_20261027/roster.csv')
    ref=pd.read_parquet(ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet',
                        columns=['station_key','year','design_family'])
    rows=[]
    for site in roster.itertuples(index=False):
        job=jobs[site.station_key]
        panel,hot=inherited.station_data(job,ref[(ref.station_key==site.station_key)&ref.design_family.eq('crossed')])
        if not hot:raise ValueError('Air-hot status unavailable')
        for rep in range(5):
            suffix=Path('crossed/forward')/f'replicate_{rep:02d}'/site.station_key.replace('|','_')
            base=json.loads((BASE/suffix/'design.json').read_text())
            old=json.loads((OLD/suffix/'design.json').read_text())
            new=json.loads((RUN/suffix/'design.json').read_text())
            a=base['masks'];b=old['masks'];c=new['masks']
            if (new['station_key']!=site.station_key or new['hidden_values_present_in_visible_archive']!=0
                    or len(a)!=len(c) or set(b)!=set(c) or Counter(a.values())!=Counter(c.values())):
                raise ValueError('Hidden values, selected years, or gap templates differ')
            if any(a[y]!=c[y] for y in set(a)&set(c)):raise ValueError('Common masked year changed')
            days_a,_,_=inherited.gap_observation_counts(panel,job['station_id'],a)
            days_b,_,_=inherited.gap_observation_counts(panel,job['station_id'],b)
            days_c,_,_=inherited.gap_observation_counts(panel,job['station_id'],c)
            if days_a!=days_c:raise ValueError('Actual matched hidden-day count changed')
            rows.append({'station_key':site.station_key,'region':site.region,'independence_group':site.independence_group,
                         'replicate':rep,'masked_years':len(a),'baseline_days':days_a,'old_heat_days':days_b,'matched_heat_days':days_c,
                         'baseline_hot_years':sum(hot.get(int(y),False) for y in a),
                         'heat_hot_years':sum(hot.get(int(y),False) for y in c),
                         'changed_year_selection':set(a)!=set(c),'changed_templates_against_prior_heat':b!=c})
    audit=pd.DataFrame(rows)
    if len(audit)!=205 or audit.duplicated(['station_key','replicate']).any():raise ValueError('Unexpected roster')
    audit.to_parquet(PRIVATE/'mask_audit.parquet',index=False)
    summary={'settings':len(audit),'stations':int(audit.station_key.nunique()),'groups':int(audit.independence_group.nunique()),
             'baseline_masked_years':int(audit.masked_years.sum()),'matched_masked_years':int(audit.masked_years.sum()),
             'baseline_hidden_days':int(audit.baseline_days.sum()),'matched_hidden_days':int(audit.matched_heat_days.sum()),
             'previous_heat_hidden_days':int(audit.old_heat_days.sum()),
             'baseline_air_hot_masked_years':int(audit.baseline_hot_years.sum()),
             'matched_air_hot_masked_years':int(audit.heat_hot_years.sum()),
             'settings_with_changed_year_selection':int(audit.changed_year_selection.sum()),
             'settings_with_changed_masks_vs_previous_heat':int(audit.changed_templates_against_prior_heat.sum()),
             'all_hidden_target_values_absent':True,'same_heat_years_as_previous_sensitivity':True,
             'same_gap_template_multiset_and_actual_hidden_days_per_archive':True}
    (OUT/'mask_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


def read_trends(folder):
    x=pd.read_csv(folder/'trends.csv')
    x=x[x.family.eq('crossed')&x['mode'].eq('forward')&x.replicate.lt(5)&x.retention.eq('all')
        &x.estimator.isin(METHODS)&x.dependence.isin(DEPS)].copy()
    if len(x)!=205*len(METHODS)*len(DEPS) or x.duplicated(KEY).any():raise ValueError('Trend cohort incomplete')
    return x


def summarize_pair(left,right,label):
    x=left.merge(right,on=KEY,suffixes=('_left','_right'),validate='one_to_one')
    if len(x)!=len(left) or len(x)!=len(right):raise ValueError('Pairing dropped trend settings')
    x.to_parquet(PRIVATE/(label+'_paired_trends.parquet'),index=False)
    rows=[];regional=[]
    for dep_index,dep in enumerate(DEPS):
        pair=x[x.dependence.eq(dep)].copy()
        availability=pair.assign(both=pair.available_left.astype(bool)&pair.available_right.astype(bool))
        method_common=availability.groupby(['station_key','replicate']).both.agg(['all','size'])
        if not method_common['size'].eq(2).all():raise ValueError('Missing comparator')
        common_keys=set(method_common.index[method_common['all']])
        for method_index,method in enumerate(METHODS):
            g=pair[pair.estimator.eq(method)].copy()
            valid=g.available_left.astype(bool)&g.available_right.astype(bool)
            if valid.any() and not np.allclose(g.loc[valid,'truth_slope_left'],g.loc[valid,'truth_slope_right'],atol=1e-9,rtol=0):
                raise ValueError('Reference slope changed')
            for scope in ['estimator_common','both_methods_common']:
                flag=valid.copy()
                if scope=='both_methods_common':flag &= pd.MultiIndex.from_frame(g[['station_key','replicate']]).isin(common_keys)
                q=g.loc[flag];labels=q.independence_group_left
                delta=q.squared_error_right-q.squared_error_left
                groups=q.assign(delta=delta).groupby('independence_group_left').delta.agg(['sum','count','mean'])
                rng=np.random.default_rng(73600+1000*(['baseline_vs_matched','previous_heat_vs_matched'].index(label))+100*dep_index+10*method_index+(scope=='both_methods_common'))
                draws=rng.integers(len(groups),size=(4000,len(groups))) if len(groups) else np.empty((0,0),int)
                boot=groups['sum'].to_numpy()[draws].sum(axis=1)/groups['count'].to_numpy()[draws].sum(axis=1) if len(groups) else np.array([])
                row={'comparison':label,'estimator':method,'dependence':dep,'scope':scope,'n_eligible':len(g),
                     'left_available':int(g.available_left.sum()),'right_available':int(g.available_right.sum()),
                     'n_common':len(q),'stations':int(q.station_key.nunique()),'groups':len(groups),
                     'left_rmse':float(np.sqrt(q.squared_error_left.mean())) if len(q) else np.nan,
                     'right_rmse':float(np.sqrt(q.squared_error_right.mean())) if len(q) else np.nan,
                     'mse_difference':float(delta.mean()) if len(q) else np.nan,
                     'equal_group_mse_difference':float(groups['mean'].mean()) if len(groups) else np.nan,
                     'bootstrap_low':float(np.quantile(boot,.025)) if len(boot) else np.nan,
                     'bootstrap_high':float(np.quantile(boot,.975)) if len(boot) else np.nan}
                if dep!='point':
                    for col in ['missing_coverage95','width95','interval_score95']:
                        for side in ['left','right']:row[side+'_'+col]=float(q[col+'_'+side].mean()) if len(q) else np.nan
                rows.append(row)
                if scope=='both_methods_common':
                    for region in sorted(q.region_left.unique()):
                        keep=q[q.region_left.ne(region)]
                        regional.append({'comparison':label,'estimator':method,'dependence':dep,'excluded_region':region,
                                         'n_common':len(keep),'groups':int(keep.independence_group_left.nunique()),
                                         'left_rmse':float(np.sqrt(keep.squared_error_left.mean())) if len(keep) else np.nan,
                                         'right_rmse':float(np.sqrt(keep.squared_error_right.mean())) if len(keep) else np.nan,
                                         'mse_difference':float((keep.squared_error_right-keep.squared_error_left).mean()) if len(keep) else np.nan})
    return rows,regional


def main():
    T.load_script('matched_gap_execution',ROOT/'scripts/734_gap_matched_heat_stress.py').verify_plan()
    cal=[json.loads((folder/'classical_calibration.json').read_text())['forward'] for folder in (BASE,OLD,RUN)]
    if cal[0]!=cal[1] or cal[0]!=cal[2]:raise ValueError('Source model calibration changed')
    mask=verify_masks()
    base,prior,new=map(read_trends,[BASE,OLD,RUN]);rows=[];regions=[]
    for x,label in [(base,'baseline_vs_matched'),(prior,'previous_heat_vs_matched')]:
        a,b=summarize_pair(x,new,label);rows.extend(a);regions.extend(b)
    pd.DataFrame(rows).to_csv(OUT/'paired_summary.csv',index=False)
    pd.DataFrame(regions).to_csv(OUT/'leave_region_out.csv',index=False)
    report={'status':'computed_posthoc','mask_audit':mask,'comparison_rows':len(rows),'leave_region_rows':len(regions),
            'source_calibrations_match':True,'bootstrap_draws':4000,
            'limitations':json.loads((OUT/'plan.json').read_text())['limitations']}
    (OUT/'status.json').write_text(json.dumps(report,indent=2)+'\n')
    print(pd.DataFrame(rows).query("comparison == 'baseline_vs_matched' and scope == 'both_methods_common' and dependence == 'independent'").to_string(index=False),flush=True)
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
