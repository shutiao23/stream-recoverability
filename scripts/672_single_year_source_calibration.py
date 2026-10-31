#!/usr/bin/env python3
"""Explore group-disjoint annual expansion based on single-year source masks.

Source correction is frozen before any target data are opened in this script.
The empirical radius provides no group-conformal or climate-transfer guarantee.
"""
from __future__ import annotations
import os
for v in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[v]='1'
os.umask(0o077)
import json
from pathlib import Path
import subprocess
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity'
PRIVATE=ROOT/'private/wrr_open_source_sensitivity_20261026';STAGE=PRIVATE/'whole_archive'
TARGET_PRIVATE=ROOT/'private/wrr_review_case_evidence_20261027'
LEVELS=[5,10,25,50,75,90,95];METHODS={'D2':'D2','stochastic_calibrated':'stochastic_cal'}
KEY=['family','mode','replicate','station_key','year'];TOL=1e-8

def check_plan():
    plan=json.loads((OUT/'single_year_calibration_plan.json').read_text())
    if plan['status']!='posthoc_frozen_before_single_year_source_residuals':raise ValueError('Source calibration plan missing')
    if subprocess.run(['git','check-ignore','-q',str(PRIVATE.relative_to(ROOT))+'/probe'],cwd=ROOT).returncode:
        raise ValueError('Private destination is not ignored')
    return plan

def calculate_source(plan):
    inference=T.load_script('single_year_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
    repair=T.load_script('single_year_repairs',ROOT/'scripts/467_review_completion_analysis.py')
    expansion=T.load_script('single_year_expansion',ROOT/'scripts/581_source_annual_interval_expansion.py')
    roleplan=json.loads((OUT/'plan.json').read_text());allowed=set(roleplan['allowed_providers']);rows=[];sourcecases=[]
    for mode,split in [('offline','leave_one_year_out'),('forward','before_2010')]:
        source=pd.read_parquet(PRIVATE/'candidate_cases'/split/'seed_00.parquet')
        source=source.loc[source.policy_choice.ne('unavailable')&source.eval_truth_h30.notna()].reset_index(drop=True)
        source=repair.apply_bridge_repairs(source,0,split)
        if not set(source.provider).issubset(allowed):raise ValueError('Unexpected source provider')
        for item in [x for x in plan['model_roles'] if x['mode']==mode]:
            region=item['region'];bundle=joblib.load(PRIVATE/'refits'/split/'seed_00'/(region+'.joblib'))
            calibration=json.loads((PRIVATE/'calibrations'/mode/(region+'.json')).read_text())
            bundle['offsets']=calibration['D2_offsets'];roles={k:set(v) for k,v in bundle['roles'].items()};rule=roles['rule_calibration']
            if len(rule)!=item['assigned_rule_groups'] or any(rule&roles[x] for x in ['estimator','interval_calibration','risk_learning']):
                raise ValueError('Calibration groups do not match disjoint frozen roles')
            forbidden=set(source.loc[source.region.eq(region),'independence_group'])
            if rule&forbidden:raise ValueError('Calibration role overlaps target-region groups')
            sub=source.loc[source.independence_group.isin(rule)&source.region.ne(region)].copy()
            if mode=='forward':
                sub=sub.loc[sub.training_partition.eq('train')].copy()
                if sub.year.ge(2010).any():raise ValueError('Forward calibration contains post-2009 source cases')
            for family in ['calendar','crossed']:
                cases=sub.loc[sub.design_family.eq(family)].copy()
                if len(cases):
                    predicted=inference.classical_predictions(inference.predict(cases,bundle),calibration)
                else:predicted=pd.DataFrame()
                for estimator,prefix in METHODS.items():
                    if len(predicted):
                        y=predicted.eval_truth_h30.to_numpy(float);lo=predicted[f'{prefix}_q05'].to_numpy(float);hi=predicted[f'{prefix}_q95'].to_numpy(float)
                        groups=predicted.independence_group.to_numpy();valid=np.isfinite(y)&np.isfinite(lo)&np.isfinite(hi)&pd.notna(groups)
                        c=expansion.correction(y,lo,hi,groups)
                        c['n_source_stations']=int(predicted.loc[valid,'station_key'].nunique())
                        c['last_source_year']=int(predicted.loc[valid,'year'].max()) if valid.any() else None
                        kept=predicted.loc[valid,['station_key','independence_group','year','eval_truth_h30',f'{prefix}_q05',f'{prefix}_q95']].copy()
                        kept=kept.rename(columns={'eval_truth_h30':'truth',f'{prefix}_q05':'lower',f'{prefix}_q95':'upper'})
                        kept['mode']=mode;kept['region']=region;kept['family']=family;kept['estimator']=estimator;sourcecases.append(kept)
                    else:c={'status':'no_source_cases','n_source_cases':0,'n_source_groups':0,'n_source_stations':0,'last_source_year':None}
                    rows.append({'family':family,'mode':mode,'region':region,'estimator':estimator,'assigned_rule_groups':len(rule),**c})
                print(f'Prepared source {mode}/{region}/{family}: {len(cases)} cases',flush=True)
    support=pd.DataFrame(rows)
    if len(support)!=52 or support.duplicated(['family','mode','region','estimator']).any():raise ValueError('Incomplete source support table')
    fwd=support.loc[support['mode'].eq('forward')]
    if fwd.assigned_rule_groups.ge(9).any() or fwd.group_max_radius.notna().any():raise ValueError('Forward group-maximum rank unexpectedly finite')
    support_path=OUT/'single_year_source_support.csv';frozen=OUT/'single_year_source_freeze.json'
    if frozen.exists():
        saved=json.loads(frozen.read_text())
        if not support_path.is_file():
            raise ValueError('Existing frozen source support changed')
        prior=pd.read_csv(support_path)
        pd.testing.assert_frame_equal(prior,support,check_dtype=False,atol=1e-10,rtol=1e-10)
    else:
        support.to_csv(support_path,index=False)
        frozen.write_text(json.dumps({'status':'source_corrections_frozen_before_target_scoring','selection':'source-group identities, time and estimator availability only'},indent=2)+'\n')
    private=PRIVATE/'single_year_calibration';private.mkdir(parents=True,exist_ok=True,mode=0o700)
    evidence=private/'source_cases.parquet';frame=pd.concat(sourcecases,ignore_index=True)
    if evidence.exists():
        if not pd.read_parquet(evidence).equals(frame):raise ValueError('Existing private source evidence differs')
    else:frame.to_parquet(evidence,index=False);evidence.chmod(0o600)
    return support

def target_cases():
    annual=T.load_script('single_year_target_annual',ROOT/'scripts/578_peak_visibility_diagnostics.py')
    cand=T.load_script('single_year_target_integrity',ROOT/'scripts/668_open_source_annual_diagnostics.py')
    _,receipts=cand.input_checks()
    old=annual.load_cases(TARGET_PRIVATE);new,_=cand.read_candidates(receipts)
    paired=old.merge(new,on=KEY,how='outer',suffixes=('_old','_candidate'),indicator=True,validate='one_to_one')
    if not paired._merge.eq('both').all() or not paired.independence_group_old.eq(paired.independence_group_candidate).all():raise ValueError('Target identities or groups differ')
    bound='observed_lower_bound__observed_days'
    if not np.allclose(paired[bound+'_old'],paired[bound+'_candidate'],atol=TOL,rtol=0,equal_nan=True):raise ValueError('Target lower bound changed')
    names=[f'{method}_q{level:02d}' for method in METHODS.values() for level in LEVELS]
    valid=np.isfinite(paired[[x+'_old' for x in names]].to_numpy(float)).all(axis=1)&np.isfinite(paired[[x+'_candidate' for x in names]].to_numpy(float)).all(axis=1)
    valid &= np.isfinite(paired.reference_h30.to_numpy(float))&np.isfinite(paired[bound+'_old'].to_numpy(float))
    target=paired.loc[valid].copy().reset_index(drop=True)
    target['stratum']=annual.classify(target.reference_h30,target[bound+'_old'])
    return target,len(paired)

def evaluate_target(target,support):
    expansion=T.load_script('single_year_target_expansion',ROOT/'scripts/581_source_annual_interval_expansion.py')
    rows=[]
    for (family,mode,region),h in target.groupby(['family','mode','region'],sort=True):
        plans=support.loc[support.family.eq(family)&support['mode'].eq(mode)&support.region.eq(region)].set_index('estimator')
        if set(plans.index)!=set(METHODS):raise ValueError('Source support missing for target region')
        both=all(plans.loc[name,'status']=='supported_exploratory' for name in METHODS)
        for name,prefix in METHODS.items():
            p=plans.loc[name];qlo=h[f'{prefix}_q05_candidate'].to_numpy(float);qhi=h[f'{prefix}_q95_candidate'].to_numpy(float)
            y=h.reference_h30.to_numpy(float);bound=h.observed_lower_bound__observed_days_old.to_numpy(float)
            if (qlo<bound-TOL).any() or (qhi<qlo-TOL).any():raise ValueError('Target interval violates support')
            supported=p['status']=='supported_exploratory';radius=float(p.empirical_radius) if supported else 0.
            lo,hi=expansion.intervals(qlo,qhi,bound,radius);before=expansion.scores(y,qlo,qhi);after=expansion.scores(y,lo,hi)
            frame=h[KEY+['region','independence_group_old','stratum']].copy();frame['estimator']=name
            frame['supported']=supported;frame['both_supported']=both
            for metric in before:frame['baseline_'+metric]=before[metric];frame['expanded_'+metric]=after[metric]
            rows.append(frame)
    data=pd.concat(rows,ignore_index=True)
    if data.duplicated(KEY+['estimator']).any():raise ValueError('Duplicate scored target cases')
    out=[]
    for (family,mode,estimator),g in data.groupby(['family','mode','estimator'],sort=True):
      for stratum in ['all','bound_matches_reference','unobserved_peak_excess']:
       h=g if stratum=='all' else g.loc[g.stratum.eq(stratum)]
       for scope in ['estimator_supported','both_methods_supported']:
        flags=h.supported if scope=='estimator_supported' else h.both_supported
        selected=h.loc[flags];row={'family':family,'mode':mode,'estimator':estimator,'stratum':stratum,'scope':scope,
            'n_eligible':len(h),'n_supported':len(selected),'availability':len(selected)/len(h) if len(h) else None,
            'supported_stations':selected.station_key.nunique(),'supported_groups':selected.independence_group_old.nunique()}
        for metric in ['coverage90','width90','interval_score90','zero90']:
            row['all_baseline_'+metric]=float(h['baseline_'+metric].mean()) if len(h) else None
            row['paired_baseline_'+metric]=float(selected['baseline_'+metric].mean()) if len(selected) else None
            row['paired_expanded_'+metric]=float(selected['expanded_'+metric].mean()) if len(selected) else None
        out.append(row)
    return data,pd.DataFrame(out)

def main():
    plan=check_plan()
    support=calculate_source(plan)
    print('Source correction table frozen; opening target data.',flush=True)
    target,n_total=target_cases();data,summary=evaluate_target(target,support)
    eligible_counts=target.groupby(['family','mode']).size();expected=pd.read_csv(OUT/'annual_sensitivity_cohorts.csv').set_index(['family','mode']).common_four_way
    if not eligible_counts.sort_index().equals(expected.sort_index()):raise ValueError('Target common annual denominators differ from previous audit')
    selected=summary.loc[summary.n_supported.gt(0)]
    for metric in ['coverage90','width90']:
        if (selected['paired_expanded_'+metric]<selected['paired_baseline_'+metric]-TOL).any():raise ValueError('Interval expansion decreased coverage or width')
    private=PRIVATE/'single_year_calibration';path=private/'target_cases.parquet'
    if path.exists():
        if not pd.read_parquet(path).equals(data):raise ValueError('Existing private target evidence differs')
    else:data.to_parquet(path,index=False);path.chmod(0o600)
    summary.to_csv(OUT/'single_year_target_summary.csv',index=False)
    status={'status':'passed','source_corrections_frozen_before_target_scoring':True,
            'source_support_rows':len(support),'target_all_cases':n_total,'target_common_cases':len(target),
            'source_status_counts':support.status.value_counts().to_dict(),
            'forward_finite_group_max_corrections':int(support.loc[support['mode'].eq('forward'),'group_max_radius'].notna().sum()),
            'limitation':plan['limitations'],}
    (OUT/'single_year_calibration_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(summary.loc[summary.family.eq('crossed')&summary['mode'].eq('forward')&summary.stratum.eq('all')&summary.scope.eq('both_methods_supported')].to_string(index=False))
    print(json.dumps(status,indent=2))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        (OUT/'single_year_calibration_status.json').write_text(json.dumps({'status':'failed','error':f'{type(exc).__name__}: {exc}'},indent=2)+'\n')
        raise
