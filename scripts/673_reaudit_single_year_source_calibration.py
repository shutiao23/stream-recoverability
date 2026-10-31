#!/usr/bin/env python3
"""Re-predict source calibration cases and independently audit target expansion.

Outputs aggregate-only reproducibility and descriptive group sensitivity.
Neither the empirical correction nor the group bootstrap certifies coverage.
"""
from __future__ import annotations
import os
for v in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[v]='1'
import json
import math
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity'
PRIVATE=ROOT/'private/wrr_open_source_sensitivity_20261026';TARGET_PRIVATE=ROOT/'private/wrr_review_case_evidence_20261027'
KEY=['family','mode','replicate','station_key','year'];LEVELS=[5,10,25,50,75,90,95]
METHODS={'D2':'D2','stochastic_calibrated':'stochastic_cal'};TOL=1e-8

def source_reaudit(plan,support):
    source_evidence=pd.read_parquet(PRIVATE/'single_year_calibration/source_cases.parquet')
    inference=T.load_script('single_year_independent_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
    repair=T.load_script('single_year_independent_repair',ROOT/'scripts/467_review_completion_analysis.py')
    rows_checked=0;case_count=0
    for mode,split in [('offline','leave_one_year_out'),('forward','before_2010')]:
        source=pd.read_parquet(PRIVATE/'candidate_cases'/split/'seed_00.parquet')
        source=source.loc[source.policy_choice.ne('unavailable')&source.eval_truth_h30.notna()].reset_index(drop=True)
        source=repair.apply_bridge_repairs(source,0,split)
        for item in [r for r in plan['model_roles'] if r['mode']==mode]:
            region=item['region'];bundle=joblib.load(PRIVATE/'refits'/split/'seed_00'/(region+'.joblib'))
            calibration=json.loads((PRIVATE/'calibrations'/mode/(region+'.json')).read_text());bundle['offsets']=calibration['D2_offsets']
            roles={k:set(v) for k,v in bundle['roles'].items()};rule=roles['rule_calibration']
            if any(rule&roles[r] for r in ['estimator','interval_calibration','risk_learning']):raise ValueError('Source role overlap')
            forbidden=set(source.loc[source.region.eq(region),'independence_group'])
            if rule&forbidden:raise ValueError('Target-region group appears in source')
            source_part=source.loc[source.independence_group.isin(rule)&source.region.ne(region)].copy()
            if mode=='forward':
                source_part=source_part.loc[source_part.training_partition.eq('train')]
                if source_part.year.ge(2010).any():raise ValueError('Forward source year after cutoff')
            for family in ['calendar','crossed']:
                sub=source_part.loc[source_part.design_family.eq(family)].copy()
                predicted=inference.classical_predictions(inference.predict(sub,bundle),calibration) if len(sub) else pd.DataFrame()
                for estimator,prefix in METHODS.items():
                    row=support.loc[support.family.eq(family)&support['mode'].eq(mode)&support.region.eq(region)&support.estimator.eq(estimator)]
                    if len(row)!=1:raise ValueError('Source support identity missing')
                    row=row.iloc[0]
                    if len(predicted):
                        y=predicted.eval_truth_h30.to_numpy(float);lo=predicted[f'{prefix}_q05'].to_numpy(float);hi=predicted[f'{prefix}_q95'].to_numpy(float);groups=predicted.independence_group.to_numpy()
                        valid=np.isfinite(y)&np.isfinite(lo)&np.isfinite(hi)&pd.notna(groups)
                        f=predicted.loc[valid,['station_key','independence_group','year']].reset_index(drop=True)
                        saved=source_evidence.loc[source_evidence.family.eq(family)&source_evidence['mode'].eq(mode)&source_evidence.region.eq(region)&source_evidence.estimator.eq(estimator)].reset_index(drop=True)
                        if len(f)!=len(saved) or not f.station_key.equals(saved.station_key) or not f.independence_group.equals(saved.independence_group) or not f.year.equals(saved.year):raise ValueError('Source prediction identities differ')
                        for name,values in [('truth',y[valid]),('lower',lo[valid]),('upper',hi[valid])]:
                            if not np.allclose(saved[name],values,atol=1e-10,rtol=0):raise ValueError('Source prediction values differ')
                        yy,ll,hh,gg=y[valid],lo[valid],hi[valid],groups[valid]
                    else:
                        saved=source_evidence.loc[source_evidence.family.eq(family)&source_evidence['mode'].eq(mode)&source_evidence.region.eq(region)&source_evidence.estimator.eq(estimator)]
                        if len(saved):raise ValueError('Unexpected source evidence')
                        yy=ll=hh=np.array([]);gg=np.array([])
                    names, inverse, counts=np.unique(gg,return_inverse=True,return_counts=True)
                    if len(yy):
                        score=np.maximum.reduce([ll-yy,yy-hh,np.zeros(len(yy))])
                        weights=1/counts[inverse];order=np.argsort(score,kind='mergesort')
                        at=np.searchsorted(np.cumsum(weights[order]),.9*len(names),side='left')
                        radius=float(score[order[min(at,len(order)-1)]])
                        expected_status='insufficient_source_groups' if len(names)<3 else ('zero_source_correction' if radius<=TOL else 'supported_exploratory')
                        if not np.isclose(radius,row.empirical_radius,atol=1e-10,rtol=0):raise ValueError('Empirical source radius differs')
                        rank=math.ceil((len(names)+1)*.9)
                        maxscore=np.array([score[inverse==i].max() for i in range(len(names))])
                        maxradius=float(np.sort(maxscore)[rank-1]) if rank<=len(names) else np.nan
                        if not np.isclose(maxradius,row.group_max_radius,atol=1e-10,rtol=0,equal_nan=True):raise ValueError('Group-max rank radius differs')
                    else:expected_status='no_source_cases'
                    if expected_status!=row.status or len(yy)!=row.n_source_cases or len(names)!=row.n_source_groups:
                        raise ValueError('Source support status or denominator differs')
                    case_count+=len(yy);rows_checked+=1
    if rows_checked!=len(support) or case_count!=len(source_evidence):raise ValueError('Source evidence row total differs')
    return rows_checked,case_count

def target_reaudit(support):
    old=T.load_script('single_year_audit_old',ROOT/'scripts/578_peak_visibility_diagnostics.py').load_cases(TARGET_PRIVATE)
    annual=T.load_script('single_year_audit_inputs',ROOT/'scripts/668_open_source_annual_diagnostics.py');_,receipts=annual.input_checks();candidate,_=annual.read_candidates(receipts)
    x=old.merge(candidate,on=KEY,how='outer',suffixes=('_old','_candidate'),indicator=True,validate='one_to_one')
    if not x._merge.eq('both').all() or not x.independence_group_old.eq(x.independence_group_candidate).all():raise ValueError('Target keys or groups changed')
    bound='observed_lower_bound__observed_days'
    if not np.allclose(x[bound+'_old'],x[bound+'_candidate'],atol=TOL,rtol=0,equal_nan=True):raise ValueError('Target bound changed')
    names=[f'{method}_q{level:02d}' for method in METHODS.values() for level in LEVELS]
    valid=np.isfinite(x[[n+'_old' for n in names]].to_numpy(float)).all(axis=1)&np.isfinite(x[[n+'_candidate' for n in names]].to_numpy(float)).all(axis=1)
    valid &= np.isfinite(x.reference_h30)&np.isfinite(x[bound+'_old'])
    target=x.loc[valid].drop(columns='_merge').copy().reset_index(drop=True);truth=target.reference_h30.to_numpy(float);bounds=target[bound+'_old'].to_numpy(float)
    if (truth<bounds-TOL).any():raise ValueError('Target reference below bound')
    target['stratum']=np.where(truth-bounds<=TOL,'bound_matches_reference','unobserved_peak_excess')
    evidence=pd.read_parquet(PRIVATE/'single_year_calibration/target_cases.parquet')
    if evidence.duplicated(KEY+['estimator']).any() or len(evidence)!=2*len(target):raise ValueError('Target evidence identity count differs')
    checked=[]
    for estimator,prefix in METHODS.items():
        saved=evidence.loc[evidence.estimator.eq(estimator)]
        aligned=target.merge(saved,on=KEY,how='outer',suffixes=('','_saved'),indicator=True,validate='one_to_one')
        if not aligned._merge.eq('both').all() or not aligned.stratum.eq(aligned.stratum_saved).all() or not aligned.region.eq(aligned.region_saved).all() or not aligned.independence_group_old.eq(aligned.independence_group_old_saved).all():raise ValueError('Target evidence metadata mismatch')
        p=support.loc[support.estimator.eq(estimator),['family','mode','region','status','empirical_radius']]
        aligned=aligned.merge(p,on=['family','mode','region'],how='left',validate='many_to_one')
        is_supported=aligned.status.eq('supported_exploratory').to_numpy()
        if not np.array_equal(is_supported,aligned.supported.to_numpy(bool)):raise ValueError('Target support status differs')
        radius=np.where(is_supported,aligned.empirical_radius.to_numpy(float),0.)
        y=aligned.reference_h30.to_numpy(float);boundvals=aligned[bound+'_old'].to_numpy(float)
        low=aligned[f'{prefix}_q05_candidate'].to_numpy(float);high=aligned[f'{prefix}_q95_candidate'].to_numpy(float)
        newlow=np.maximum(low-radius,boundvals);newhigh=np.maximum(high+radius,boundvals)
        def values(a,b):return {'coverage90':((y>=a-TOL)&(y<=b+TOL)).astype(float),'width90':b-a,
            'interval_score90':b-a+20*(np.maximum(a-y,0)+np.maximum(y-b,0)), 'zero90':(abs(b-a)<=TOL).astype(float)}
        for label,interval in [('baseline',values(low,high)),('expanded',values(newlow,newhigh))]:
            for metric,observed in interval.items():
                if not np.allclose(observed,aligned[label+'_'+metric],atol=1e-9,rtol=0):raise ValueError('Target per-case interval score differs: '+label+' '+metric)
        checked.append(saved)
    cases=pd.concat(checked,ignore_index=True)
    return cases,len(target)

def summarize_and_sensitivity(cases):
    saved=pd.read_csv(OUT/'single_year_target_summary.csv');rows=[];loo=[];verified=0
    for offset,((family,mode,estimator),g) in enumerate(cases.groupby(['family','mode','estimator'],sort=True)):
      for stratum in ['all','bound_matches_reference','unobserved_peak_excess']:
       h=g if stratum=='all' else g.loc[g.stratum.eq(stratum)]
       for scope in ['estimator_supported','both_methods_supported']:
        selected=h.loc[h.supported if scope=='estimator_supported' else h.both_supported]
        row=saved.loc[saved.family.eq(family)&saved['mode'].eq(mode)&saved.estimator.eq(estimator)&saved.stratum.eq(stratum)&saved.scope.eq(scope)]
        if len(row)!=1 or int(row.iloc[0].n_eligible)!=len(h) or int(row.iloc[0].n_supported)!=len(selected):raise ValueError('Target summary denominators differ')
        for metric in ['coverage90','width90','interval_score90','zero90']:
            for prefix,frame,col in [('all_baseline',h,'baseline_'),('paired_baseline',selected,'baseline_'),('paired_expanded',selected,'expanded_')]:
                value=float(frame[col+metric].mean()) if len(frame) else np.nan
                if not np.isclose(value,row.iloc[0][prefix+'_'+metric],atol=1e-10,rtol=0,equal_nan=True):raise ValueError('Target summary score differs')
        verified+=1
       selected=h.loc[h.both_supported]
       if not len(selected):continue
       labels=selected.independence_group_old.to_numpy();groups=sorted(set(labels));result={'family':family,'mode':mode,'estimator':estimator,'stratum':stratum,'n':len(selected),'stations':selected.station_key.nunique(),'groups':len(groups)}
       for index,metric in enumerate(['coverage90','width90','interval_score90']):
        delta=(selected['expanded_'+metric]-selected['baseline_'+metric]).to_numpy(float)
        sums=np.array([delta[labels==group].sum() for group in groups]);sizes=np.array([(labels==group).sum() for group in groups])
        rng=np.random.default_rng(673000+100*offset+index);draws=rng.integers(len(groups),size=(4000,len(groups)))
        boot=sums[draws].sum(axis=1)/sizes[draws].sum(axis=1)
        result[metric+'_difference']=float(delta.mean());result[metric+'_group_equal_difference']=float(np.mean(sums/sizes))
        result[metric+'_bootstrap_low'],result[metric+'_bootstrap_high']=map(float,np.quantile(boot,[.025,.975]))
       rows.append(result)
       for region in sorted(selected.region.unique()):
        kept=selected.loc[selected.region.ne(region)]
        if not len(kept):continue
        row={'family':family,'mode':mode,'estimator':estimator,'stratum':stratum,'excluded_region':region,'n':len(kept),'groups':kept.independence_group_old.nunique()}
        for metric in ['coverage90','width90','interval_score90']:
            row[metric+'_difference']=float((kept['expanded_'+metric]-kept['baseline_'+metric]).mean())
        loo.append(row)
    if verified!=len(saved):raise ValueError('Target summary row count differs')
    pd.DataFrame(rows).to_csv(OUT/'single_year_group_sensitivity.csv',index=False)
    pd.DataFrame(loo).to_csv(OUT/'single_year_leave_region_out.csv',index=False)
    return verified,len(rows),len(loo)

def main():
    plan=json.loads((OUT/'single_year_calibration_plan.json').read_text());freeze=json.loads((OUT/'single_year_source_freeze.json').read_text());status=json.loads((OUT/'single_year_calibration_status.json').read_text())
    if status['status']!='passed' or freeze['status']!='source_corrections_frozen_before_target_scoring':
        raise ValueError('Frozen source calibration or target status changed')
    support=pd.read_csv(OUT/'single_year_source_support.csv')
    source_rows,source_cases=source_reaudit(plan,support)
    print('Independent source model predictions and radii checked:',source_rows,source_cases,flush=True)
    target,common=target_reaudit(support)
    verified,groups,loo=summarize_and_sensitivity(target)
    report={'status':'passed','source_support_rows_checked':source_rows,'source_prediction_rows_checked':source_cases,
            'target_common_cases':common,'target_estimator_rows_checked':len(target),'target_summary_rows_checked':verified,
            'paired_group_sensitivity_rows':groups,'leave_region_out_rows':loo,'bootstrap_draws':4000,
            'limitation':'Same stored source cases, fitted models and target data are re-evaluated. This is not a provider-native data rebuild, an independent climate test or a finite-sample coverage guarantee.'}
    names=['single_year_calibration_plan.json','single_year_source_freeze.json','single_year_source_support.csv',
           'single_year_calibration_status.json','single_year_target_summary.csv',
           'single_year_group_sensitivity.csv','single_year_leave_region_out.csv']
    (OUT/'single_year_independent_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        (OUT/'single_year_independent_audit.json').write_text(json.dumps({'status':'failed','error':f'{type(exc).__name__}: {exc}'},indent=2)+'\n')
        raise
