#!/usr/bin/env python3
"""Explore annual group-maximum interval expansion from source-only roles.

Risk-learning groups have trained classifiers, but not the D2 quantile model
or its interval offsets; classifier outputs are not used for this analysis.
Exchangeability and matched source/target group designs are not established.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
os.umask(0o077)
import argparse
import json
import math
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
REV=ROOT/'results/wrr_review_response_20261027'
OLD=REV/'open_source_sensitivity'
OUT=REV/'groupmax_annual_calibration'
INPUT=ROOT/'private/wrr_open_source_sensitivity_20261026'
PRIVATE=ROOT/'private/wrr_groupmax_annual_calibration_20261027'
METHODS={'D2':'D2','stochastic_calibrated':'stochastic_cal'}
KEY=['family','mode','replicate','station_key','year']
TOL=1e-8

def verify_plan():
    plan=json.loads((OUT/'plan.json').read_text())
    return plan

def group_max_radius(truth,lower,upper,groups,alpha=.1):
    y,lo,hi=map(lambda x:np.asarray(x,float),(truth,lower,upper));g=np.asarray(groups)
    valid=np.isfinite(y)&np.isfinite(lo)&np.isfinite(hi)&pd.notna(g)
    y,lo,hi,g=y[valid],lo[valid],hi[valid],g[valid]
    if (hi<lo-TOL).any():raise ValueError('Reversed source interval')
    if not len(y):return {'status':'no_valid_source_cases','n_cases':0,'n_groups':0,'rank':None,'radius':None},pd.DataFrame()
    miss=np.maximum.reduce([lo-y,y-hi,np.zeros(len(y))])
    group=pd.DataFrame({'group':g,'miss':miss}).groupby('group',sort=True).miss.agg(['max','size']).reset_index()
    count=len(group);rank=int(math.ceil((count+1)*(1-alpha)-1e-12))
    radius=float(np.sort(group['max'].to_numpy(float))[rank-1]) if rank<=count else None
    status='insufficient_source_groups' if rank>count else ('zero_source_correction' if radius<=TOL else 'supported_exploratory')
    return {'status':status,'n_cases':len(y),'n_groups':count,'rank':rank,'radius':radius,
            'min_group_cases':int(group['size'].min()),'max_group_cases':int(group['size'].max())},group

def intervals(lower,upper,bound,radius):
    lo,hi,b=map(lambda x:np.asarray(x,float),(lower,upper,bound))
    return np.where(np.isfinite(b),np.maximum(lo-radius,b),lo-radius),hi+radius

def scores(y,lo,hi):
    return {'coverage90':((y>=lo-TOL)&(y<=hi+TOL)).astype(float),
            'width90':hi-lo,'interval_score90':hi-lo+20*(np.maximum(lo-y,0)+np.maximum(y-hi,0))}

def fit_source():
    plan=verify_plan()
    if (OUT/'source_freeze.json').exists():raise FileExistsError('Source radii already frozen')
    inference=T.load_script('groupmax_source_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
    repair=T.load_script('groupmax_source_repair',ROOT/'scripts/467_review_completion_analysis.py')
    raw=pd.read_parquet(INPUT/'candidate_cases/before_2010/seed_00.parquet')
    forbidden={region:set(g.independence_group) for region,g in raw.groupby('region')}
    source=raw[raw.policy_choice.ne('unavailable')&raw.eval_truth_h30.notna()&raw.training_partition.eq('train')].reset_index(drop=True)
    if source.year.ge(2010).any():raise ValueError('Post-2009 forward source case')
    source=repair.apply_bridge_repairs(source,0,'before_2010')
    roster=pd.read_csv(ROOT/'private/wrr_projected_risk_sensitivity_20261027/roster.csv')
    rows=[];groups=[];classifier_probes=0
    for region in sorted(roster.region.unique()):
        bundle=joblib.load(INPUT/'refits/before_2010/seed_00'/f'{region}.joblib')
        cal=json.loads((INPUT/'calibrations/forward'/f'{region}.json').read_text());bundle['offsets']=cal['D2_offsets']
        roles={name:set(value) for name,value in bundle['roles'].items()}
        if any(roles[a]&roles[b] for i,a in enumerate(roles) for b in list(roles)[i+1:]):raise ValueError('Source roles overlap')
        pool=roles['risk_learning']|roles['rule_calibration']
        target_groups=set(roster.loc[roster.region.eq(region),'independence_group'])
        if pool&(forbidden.get(region,set())|target_groups) or pool&(roles['estimator']|roles['interval_calibration']):
            raise ValueError('Calibration groups overlap target, estimator or interval-offset roles')
        sub=source[source.independence_group.isin(pool)].copy()
        for family in ['calendar','crossed']:
            part=sub[sub.design_family.eq(family)].copy()
            if part.empty:
                for method in METHODS:
                    rows.append({'region':region,'family':family,'estimator':method,'status':'no_valid_source_cases',
                                 'n_cases':0,'n_groups':0,'rank':None,'radius':None,
                                 'assigned_risk_groups':len(roles['risk_learning']),'assigned_rule_groups':len(roles['rule_calibration'])})
                continue
            predicted=inference.classical_predictions(inference.predict(part,bundle),cal)
            # Score-classifier perturbation tests that no classifier output is
            # used to construct either set of annual numerical quantiles.
            probe=part.iloc[:min(25,len(part))].copy()
            alternative=dict(bundle);alternative['classifier']=None;alternative['constant_probability']=.123
            a=inference.classical_predictions(inference.predict(probe,bundle),cal)
            b=inference.classical_predictions(inference.predict(probe,alternative),cal)
            for prefix in METHODS.values():
                for level in ['05','10','25','50','75','90','95']:
                    col=f'{prefix}_q{level}'
                    if not np.allclose(a[col],b[col],rtol=0,atol=1e-10,equal_nan=True):raise ValueError('Classifier affected annual quantile')
            classifier_probes+=len(probe)
            for method,prefix in METHODS.items():
                y=predicted.eval_truth_h30.to_numpy(float);lo=predicted[f'{prefix}_q05'].to_numpy(float);hi=predicted[f'{prefix}_q95'].to_numpy(float)
                bound=predicted.observed_lower_bound__observed_days.to_numpy(float)
                valid=np.isfinite(y)&np.isfinite(lo)&np.isfinite(hi)&np.isfinite(bound)
                if (y[valid]<bound[valid]-TOL).any() or (lo[valid]<bound[valid]-TOL).any():raise ValueError('Source observation support violated')
                result,by=group_max_radius(y[valid],lo[valid],hi[valid],predicted.independence_group.to_numpy()[valid])
                result.update(region=region,family=family,estimator=method,assigned_risk_groups=len(roles['risk_learning']),
                              assigned_rule_groups=len(roles['rule_calibration']))
                rows.append(result)
                if len(by):groups.append(by.assign(region=region,family=family,estimator=method))
            print('Prepared group-max source:',region,family,flush=True)
    support=pd.DataFrame(rows)
    if len(support)!=24 or support.duplicated(['region','family','estimator']).any():raise ValueError('Source cells incomplete')
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    group_data=pd.concat(groups,ignore_index=True);group_data.to_parquet(PRIVATE/'source_group_scores.parquet',index=False)
    support.to_csv(OUT/'source_support.csv',index=False)
    freeze={'status':'source_group_max_radii_frozen_before_new_target_scoring','classifier_invariance_source_cases_checked':classifier_probes,
            'limitation':'Source and target datasets and earlier results were already examined; source risk groups trained classifiers, but quantiles are invariant to classifier output. No independent-climate or exchangeability guarantee.'}
    (OUT/'source_freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    print(support[['region','family','estimator','status','n_groups','rank','radius']].to_string(index=False),flush=True)

def verify_source():
    plan=verify_plan();f=json.loads((OUT/'source_freeze.json').read_text())
    if f['status']!='source_group_max_radii_frozen_before_new_target_scoring':
        raise ValueError('Frozen source radii changed')
    return plan

def target_scores():
    module=T.load_script('groupmax_target_existing',ROOT/'scripts/672_single_year_source_calibration.py')
    target,n_total=module.target_cases()
    target=target[target['mode'].eq('forward')].copy()
    if target.duplicated(KEY).any():raise ValueError('Duplicate target case identity')
    support=pd.read_csv(OUT/'source_support.csv').set_index(['region','family','estimator'])
    empirical=pd.read_csv(OLD/'single_year_source_support.csv')
    empirical=empirical[empirical['mode'].eq('forward')].set_index(['region','family','estimator'])
    both_old=empirical.status.eq('supported_exploratory').groupby(level=['region','family']).all()
    both_new=support.status.eq('supported_exploratory').groupby(level=['region','family']).all()
    records=[]
    for (region,family),frame in target.groupby(['region','family'],sort=True):
        new_both=bool(both_new.loc[(region,family)]);old_both=bool(both_old.loc[(region,family)])
        for estimator,prefix in METHODS.items():
            info=support.loc[(region,family,estimator)];past=empirical.loc[(region,family,estimator)]
            y=frame.reference_h30.to_numpy(float);bound=frame.observed_lower_bound__observed_days_old.to_numpy(float)
            lo=frame[f'{prefix}_q05_candidate'].to_numpy(float);hi=frame[f'{prefix}_q95_candidate'].to_numpy(float)
            if (lo<bound-TOL).any() or (y<bound-TOL).any() or (hi<lo-TOL).any():raise ValueError('Target support invariant failed')
            selected=info.status=='supported_exploratory'
            lo2,hi2=intervals(lo,hi,bound,float(info.radius) if selected else 0.)
            old_selected=past.status=='supported_exploratory'
            lo3,hi3=intervals(lo,hi,bound,float(past.empirical_radius) if old_selected else 0.)
            part=frame[KEY+['region','independence_group_old','stratum']].copy();part['estimator']=estimator
            part['groupmax_supported']=selected;part['both_groupmax_supported']=new_both;part['both_empirical_supported']=old_both
            for name,vals in [('baseline',scores(y,lo,hi)),('groupmax',scores(y,lo2,hi2)),('empirical',scores(y,lo3,hi3))]:
                for metric,values in vals.items():part[name+'_'+metric]=values
            records.append(part)
    data=pd.concat(records,ignore_index=True)
    if data.duplicated(KEY+['estimator']).any():raise ValueError('Duplicate target scores')
    return data,len(target),n_total

def summarize(data):
    summaries=[];loo=[];rng=np.random.default_rng(720)
    for (family,estimator),all_cases in data.groupby(['family','estimator'],sort=True):
      for stratum in ['all','unobserved_peak_excess']:
       subset=all_cases if stratum=='all' else all_cases[all_cases.stratum.eq(stratum)]
       for scope in ['both_groupmax_supported','both_groupmax_and_empirical_supported']:
        mask=subset.both_groupmax_supported.to_numpy(bool)
        if scope=='both_groupmax_and_empirical_supported':mask &= subset.both_empirical_supported.to_numpy(bool)
        g=subset.loc[mask].copy();groups=sorted(g.independence_group_old.unique())
        row={'family':family,'estimator':estimator,'stratum':stratum,'scope':scope,'n_eligible':len(subset),
             'n_supported':len(g),'availability':len(g)/len(subset) if len(subset) else np.nan,
             'stations':g.station_key.nunique(),'groups':len(groups)}
        for version in ['baseline','groupmax']+(['empirical'] if scope=='both_groupmax_and_empirical_supported' else []):
            for metric in ['coverage90','width90','interval_score90']:
                row[version+'_'+metric]=float(g[version+'_'+metric].mean()) if len(g) else np.nan
            group_all=g.groupby('independence_group_old')[version+'_coverage90'].min()
            row[version+'_groups_all_cases_covered']=int(group_all.sum())
        if len(groups):
            labels=g.independence_group_old.to_numpy();draw=rng.integers(len(groups),size=(4000,len(groups)))
            for metric in ['coverage90','width90','interval_score90']:
                delta=(g['groupmax_'+metric]-g['baseline_'+metric]).to_numpy(float)
                total=np.array([delta[labels==group].sum() for group in groups]);sizes=np.array([(labels==group).sum() for group in groups])
                sample=total[draw].sum(axis=1)/sizes[draw].sum(axis=1)
                row[metric+'_difference_group_equal']=float(np.mean(total/sizes))
                row[metric+'_difference_ci_low']=float(np.quantile(sample,.025))
                row[metric+'_difference_ci_high']=float(np.quantile(sample,.975))
        summaries.append(row)
        for region in sorted(g.region.unique()):
            remain=g[g.region.ne(region)]
            loo.append({'family':family,'estimator':estimator,'stratum':stratum,'scope':scope,'removed_region':region,
                        'n_supported':len(remain),'groups':remain.independence_group_old.nunique(),
                        **{metric+'_difference':float((remain['groupmax_'+metric]-remain['baseline_'+metric]).mean()) if len(remain) else np.nan
                           for metric in ['coverage90','width90','interval_score90']}})
    return pd.DataFrame(summaries),pd.DataFrame(loo)

def score_target():
    plan=verify_source()
    if (OUT/'status.json').exists():raise FileExistsError('Target scores already exist')
    data,n_target,n_all=target_scores()
    data.to_parquet(PRIVATE/'target_scores.parquet',index=False)
    summary,loo=summarize(data)
    summary.to_csv(OUT/'summary.csv',index=False);loo.to_csv(OUT/'leave_region_out.csv',index=False)
    status={'status':'computed','forward_common_annual_cases':n_target,'all_modes_annual_cases_before_filter':n_all,
            'target_case_method_rows':len(data),'source_frozen_first':True,
            'limitation':plan['limitations']}
    (OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(summary[(summary.family=='crossed')&(summary.stratum=='all')].to_string(index=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['fit-source','score-target']);a=p.parse_args()
    fit_source() if a.action=='fit-source' else score_target()
