#!/usr/bin/env python3
"""Compare original and stricter-region forward release on identical cases.

Only the two source models affected by a verified role issue are replaced; all
other regions retain the original output. This is a post-hoc sensitivity, not a
new confirmatory test or a climate-independent risk guarantee.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.outputs import release_states
from stream_recoverability.seeds import plain_seed

ROOT=T.ROOT
SOURCE=ROOT/'results/wrr_review_completion_20261024'
REV=ROOT/'results/wrr_review_response_20261027'
OUT=REV/'strict_region_holdout'
PRIVATE=ROOT/'private/wrr_strict_region_holdout_20261026'
KEY=['network_id','station_key','year','design_family','realization_id']
REGIONS=['nve_hydapi','usgs_huc17']


def limits(source,region,roles):
    seed=plain_seed(7,0,sorted(source.region.unique()).index(region))
    _,_,weights=roles(source,region,seed)
    fit=source.loc[weights['estimator']>0]
    if fit.empty:raise ValueError('empty estimator role')
    return {name:float(fit[name].abs().quantile(.99)) for name in ['visible_edge_anomaly','air_gap_z_mean']}


def states(frame,thresholds):
    f=frame.copy();bound=f.observed_lower_bound__observed_days.to_numpy(float);point=f.D2.to_numpy(float)
    f['D2']=np.where(np.isfinite(bound),np.maximum(point,bound),point)
    f['output']=release_states(f,thresholds,np.zeros(len(f),dtype=bool))
    return f


def metrics(frame):
    y=frame.eval_truth_h30.to_numpy(float);d=frame.D2.to_numpy(float);risk=frame.risk_score.to_numpy(float)
    return {'estimate_all':np.isfinite(d),'fixed_risk':np.isfinite(d)&np.isfinite(risk)&(risk<=.1),
            'three_outputs':frame.output.eq('estimate').to_numpy()}


def main():
    refit_status=json.loads((OUT/'refit_status.json').read_text())
    if refit_status['status']!='strict_models_refitted':raise RuntimeError('strict source models are not ready')
    refit=T.load_script('strict_future_refit_roles',ROOT/'scripts/610_strict_region_refit.py');strict=refit.strict_module()
    original=T.load_script('original_future_refit_roles',ROOT/'scripts/466_review_completion_refit.py')
    source=pd.read_parquet(SOURCE/'cases/before_2010/seed_00.parquet')
    source=source.loc[source.policy_choice.ne('unavailable')&source.eval_truth_h30.notna()].reset_index(drop=True)
    design=json.loads((REV/'release_outputs/design.json').read_text())
    saved=pd.read_parquet(REV/'release_outputs/future_years.parquet')
    if saved.duplicated(KEY).any():raise ValueError('saved future cases duplicate')
    altered=[];limit_rows=[];max_numeric_difference=0.;states_mismatch=0
    for region in REGIONS:
        old=pd.read_parquet(SOURCE/'refits/before_2010/seed_00'/f'{region}.parquet')
        new=pd.read_parquet(PRIVATE/'refits/before_2010/seed_00'/f'{region}.parquet')
        if 'training_partition' in old:old=old.loc[old.training_partition.eq('test')].copy()
        if 'training_partition' in new:new=new.loc[new.training_partition.eq('test')].copy()
        if old.duplicated(KEY).any() or new.duplicated(KEY).any():raise ValueError('region prediction cases duplicate')
        oldlimits=limits(source,region,original.roles);newlimits=limits(source,region,strict.roles)
        stored=design['limits_by_training_split_and_held_region']['before_2010'][region]
        for name in oldlimits:
            if not np.isclose(oldlimits[name],stored[name],atol=1e-12,rtol=0):raise ValueError('original gate limits differ')
        limit_rows.extend({'region':region,'feature':name,'original_limit':oldlimits[name],'strict_limit':newlimits[name]} for name in oldlimits)
        old=states(old,oldlimits);new=states(new,newlimits)
        current=saved.loc[saved.region.eq(region)]
        check=old.merge(current,on=KEY,how='outer',suffixes=('_computed','_saved'),indicator=True,validate='one_to_one')
        if not check._merge.eq('both').all():raise ValueError('original prediction keys differ from saved future output')
        for col in ['D2','risk_score','eval_truth_h30']:
            x=check[col+'_computed'].to_numpy(float);y=check[col+'_saved'].to_numpy(float)
            if not np.allclose(x,y,rtol=0,atol=1e-8,equal_nan=True):raise ValueError('original values differ from saved future output: '+col)
            good=np.isfinite(x)&np.isfinite(y)
            if good.any():max_numeric_difference=max(max_numeric_difference,float(np.max(abs(x[good]-y[good]))))
        states_mismatch+=int(check.output_computed.ne(check.output_saved).sum())
        if states_mismatch:raise ValueError('original release states differ from saved output')
        paired=old.merge(new,on=KEY,how='outer',suffixes=('_old','_strict'),indicator=True,validate='one_to_one')
        if not paired._merge.eq('both').all():raise ValueError('strict target cohort differs')
        for name in ['eval_truth_h30','observed_lower_bound__observed_days','h30__policy']:
            if not np.allclose(paired[name+'_old'],paired[name+'_strict'],rtol=0,atol=1e-8,equal_nan=True):raise ValueError('target truth, bound or plugin differs')
        keep=KEY+['D2','risk_score','output']
        update=new[keep].copy()
        if update.duplicated(KEY).any():raise ValueError('strict update duplicates')
        altered.append(update)
    updates=pd.concat(altered,ignore_index=True)
    strict_saved=saved.merge(updates,on=KEY,how='left',suffixes=('','_strict'),validate='one_to_one',indicator=True)
    selected=strict_saved.region.isin(REGIONS)
    if not strict_saved.loc[selected,'_merge'].eq('both').all() or not strict_saved.loc[~selected,'_merge'].eq('left_only').all():raise ValueError('replacement scope differs')
    for col in ['D2','risk_score','output']:strict_saved.loc[selected,col]=strict_saved.loc[selected,col+'_strict'].to_numpy()
    strict_saved=strict_saved[saved.columns].copy()
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    case_path=PRIVATE/'future_strict_outputs.parquet'
    if case_path.exists():raise RuntimeError('existing strict future case output will not be overwritten')
    strict_saved.to_parquet(case_path,index=False);case_path.chmod(0o600)
    rows=[]
    for scope in ['all_regions',*REGIONS]:
        a=saved if scope=='all_regions' else saved.loc[saved.region.eq(scope)]
        b=strict_saved if scope=='all_regions' else strict_saved.loc[strict_saved.region.eq(scope)]
        for family in ['calendar','crossed']:
            x=a.loc[a.design_family.eq(family)];y=b.loc[b.design_family.eq(family)]
            if len(x)!=len(y):raise ValueError('comparison denominator changed')
            old_methods=metrics(x);new_methods=metrics(y)
            for method in old_methods:
                result={'scope':scope,'family':family,'method':method,'n_eligible':len(x)}
                for label,block,mask in [('original',x,old_methods[method]),('strict',y,new_methods[method])]:
                    error=abs(block.D2.to_numpy(float)-block.eval_truth_h30.to_numpy(float))
                    n=int(mask.sum());bad=int((mask&(error>.5)).sum())
                    result.update({f'{label}_published':n,f'{label}_bad':bad,
                                   f'{label}_retention':n/len(block) if len(block) else np.nan,
                                   f'{label}_selected_failure':bad/n if n else np.nan})
                rows.append(result)
    summary=pd.DataFrame(rows);summary.to_csv(OUT/'future_release_comparison.csv',index=False)
    pd.DataFrame(limit_rows).to_csv(OUT/'future_gate_limits.csv',index=False)
    transitions=pd.crosstab(saved.loc[saved.region.isin(REGIONS),'output'],strict_saved.loc[strict_saved.region.isin(REGIONS),'output'])
    transitions.to_csv(OUT/'future_state_transitions.csv')
    status={'status':'passed','total_future_cases':len(saved),'affected_region_cases':int(selected.sum()),
       'matched_original_values_max_difference':max_numeric_difference,'original_state_mismatches':states_mismatch,
       'same_case_keys_and_truth':True,'strict_regions_replaced':REGIONS,
       'scope':'original and strict before-2010 held-test cases; two affected regional models refitted, other regions unchanged; gate thresholds recomputed from filtered estimator role',
       'limitation':'post-hoc sensitivity with different source sample sizes; raw classifier scores and selected risk do not provide group or climate-transfer guarantees'}
    (OUT/'future_comparison_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(summary.to_string(index=False));print(json.dumps(status,indent=2))

if __name__=='__main__':main()
