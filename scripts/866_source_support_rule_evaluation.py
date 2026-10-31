#!/usr/bin/env python3
"""Test a fixed marginal-support warning on disjoint source-rule groups."""
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T
import wrr_tr_features as F

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'source_ood_release';EXTERNAL=REV/'external_usace_reservoir';SOURCE=ROOT/'results/wrr_review_completion_20261024';PRIVATE=ROOT/'private/wrr_source_ood_release_20261027';USACE=ROOT/'private/wrr_usace_reservoir_reference_20261027'

def source_data():
    helper=T.load_script('source_ood_global_roles',ROOT/'scripts/856_partial_history_feature_support_plan.py')
    source,groups,weights,bundle=helper.roles();hold=(weights['rule_calibration']>0)&source.design_family.eq('crossed').to_numpy()
    if np.any(hold&(weights['estimator']>0)) or np.any(hold&(weights['interval_calibration']>0)) or np.any(hold&(weights['risk_learning']>0)):raise ValueError('Source roles overlap')
    return helper,source,groups,weights,bundle,hold

def source_support_flags(c,bundle,support):
    x=F.design_matrix(c,simulation=True).reindex(columns=bundle['features']);names=[n for n in bundle['features'] if n!='n_complete_years'];flags=np.zeros((len(c),len(names)),bool)
    for j,name in enumerate(names):
        train=support.loc[name];v=x[name].to_numpy(float);finite=np.isfinite(v)
        if np.isfinite(train.source_min) and np.isfinite(train.source_max):
            outside=finite&((v<train.source_min)|(v>train.source_max))
        else:outside=finite
        unseen=(np.isnan(v)&(train.source_estimator_nan_rows==0))|(np.isposinf(v)&(train.source_estimator_posinf_rows==0))|(np.isneginf(v)&(train.source_estimator_neginf_rows==0))
        flags[:,j]=outside|unseen
    return flags.any(axis=1),flags.sum(axis=1)

def metrics(frame,emit):
    fail=frame.failed.to_numpy(bool);emit=np.asarray(emit,bool);w=1/frame.groupby('independence_group').independence_group.transform('size').to_numpy(float)
    if not emit.any():return {'numerical_retention':0.,'numerical_errors':0,'conditional_failure':np.nan,'group_weighted_retention':0.,'group_weighted_failure':np.nan}
    return {'numerical_retention':float(emit.mean()),'numerical_errors':int((emit&fail).sum()),'conditional_failure':float(fail[emit].mean()),
            'group_weighted_retention':float(w[emit].sum()/w.sum()),'group_weighted_failure':float(w[emit&fail].sum()/w[emit].sum())}

def matched_risk_only(frame,n):
    # Deterministic tie-break uses identifiers, never evaluation truth.
    ordered=frame.sort_values(['risk_score','station_key','year','design_family','realization_id','network_id','policy_choice'],kind='mergesort').index
    result=np.zeros(len(frame),bool);result[ordered[:n]]=True
    return result

def run():
    helper,source,groups,weights,bundle,hold=source_data();plan=json.loads((OUT/'plan.json').read_text())
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    if int(hold.sum())!=plan['source_rule_crossed_cases']:raise ValueError('Source rule cohort changed')
    support=pd.read_csv(USACE/'partial_history_feature_support.csv').set_index('feature')
    c=source.loc[hold].copy().reset_index(drop=True);cal=json.loads((REV/'external_bc_air2stream/source_calibration.json').read_text())
    if cal['D2_calibration_groups']!=bundle['roles']['interval_calibration']:raise ValueError('Calibration role mismatch')
    bundle['offsets']=cal['D2_offsets'];inference=T.load_script('source_ood_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
    pred=inference.predict(c,bundle);flag,count=source_support_flags(pred,bundle,support);pred['support_warning']=flag;pred['support_warning_features']=count
    pred['failed']=np.abs(pred.D2.to_numpy(float)-pred.eval_truth_h30.to_numpy(float))>.5
    finite=np.isfinite(pred.D2.to_numpy(float))&np.isfinite(pred.risk_score.to_numpy(float))&np.isfinite(pred.eval_truth_h30.to_numpy(float))
    lower=pd.to_numeric(pred.observed_lower_bound__observed_days,errors='coerce').to_numpy(float)
    eligible=finite&np.isfinite(lower)&pred.n_complete_years.ge(4).to_numpy();frame=pred.loc[eligible].copy().reset_index(drop=True)
    if frame.empty:raise ValueError('No source cases meet the fixed evaluation cohort')
    warning=frame.support_warning.to_numpy(bool);failure=frame.failed.to_numpy(bool);lowrisk=frame.risk_score.le(.1).to_numpy(bool)
    risk_ood=lowrisk&~warning;matched=matched_risk_only(frame,int(risk_ood.sum()))
    decisions={'risk_score_at_most_0.1':lowrisk,'risk_score_at_most_0.1_and_inside_range':risk_ood,'risk_only_same_numerical_count_posthoc':matched}
    table=pd.DataFrame([{'policy':name,'eligible_cases':len(frame),'groups':frame.independence_group.nunique(),**metrics(frame,mask)} for name,mask in decisions.items()])
    table.to_csv(OUT/'policy_summary.csv',index=False)
    tp=int((warning&failure).sum());fp=int((warning&~failure).sum());fn=int((~warning&failure).sum());tn=int((~warning&~failure).sum())
    group_rows=[]
    for group,g in frame.groupby('independence_group',sort=True):
        idx=g.index.to_numpy();ff=failure[idx];ww=warning[idx];a=risk_ood[idx];b=matched[idx]
        group_rows.append({'independence_group':group,'cases':len(g),'failures':int(ff.sum()),'warnings':int(ww.sum()),
           'true_positive':int((ff&ww).sum()),'false_positive':int((~ff&ww).sum()),
           'risk_ood_emitted':int(a.sum()),'risk_ood_errors':int((a&ff).sum()),'risk_matched_emitted':int(b.sum()),'risk_matched_errors':int((b&ff).sum())})
    g=pd.DataFrame(group_rows);g.to_csv(PRIVATE/'group_counts.csv',index=False)
    # Paired group bootstrap recomputes the selected-value error rates; group
    # selection was based on target scores/flags, never target outcomes.
    rng=np.random.default_rng(20261027);ii=rng.integers(0,len(g),size=(4000,len(g)))
    aN=g.risk_ood_emitted.to_numpy()[ii].sum(axis=1);bN=g.risk_matched_emitted.to_numpy()[ii].sum(axis=1)
    ae=g.risk_ood_errors.to_numpy()[ii].sum(axis=1);be=g.risk_matched_errors.to_numpy()[ii].sum(axis=1);ok=(aN>0)&(bN>0)
    differences=ae[ok]/aN[ok]-be[ok]/bN[ok]
    out={'status':'completed_posthoc_source_rule_evaluation','source_rule_crossed_cases':len(c),'eligible_cases':len(frame),'eligible_groups':int(frame.independence_group.nunique()),
      'excluded_history_or_reference_or_inference':int(len(c)-len(frame)),'failure_threshold_c':.5,
      'warning':{'cases_flagged':int(warning.sum()),'failures':int(failure.sum()),'true_positive':tp,'false_positive':fp,'false_negative':fn,'true_negative':tn,
                 'failure_recall':tp/(tp+fn) if tp+fn else None,'false_positive_rate':fp/(fp+tn) if fp+tn else None},
      'matched_comparison':{'risk_plus_range_numerical':int(risk_ood.sum()),'risk_only_matched_numerical':int(matched.sum()),
        'risk_plus_range_errors':int((risk_ood&failure).sum()),'risk_only_matched_errors':int((matched&failure).sum()),
        'conditional_failure_difference':float(failure[risk_ood].mean()-failure[matched].mean()) if risk_ood.any() and matched.any() else None,
        'group_bootstrap_low':float(np.quantile(differences,.025)) if len(differences) else None,'group_bootstrap_high':float(np.quantile(differences,.975)) if len(differences) else None,
        'valid_bootstrap_draws':int(ok.sum())},
      'limitations':plan['limitations']}
    path=PRIVATE/'evaluated_cases.parquet'
    frame['risk_plus_range_emit']=risk_ood;frame['risk_matched_emit']=matched;frame.to_parquet(path,index=False);path.chmod(0o600)
    (OUT/'status.json').write_text(json.dumps(out,indent=2)+'\n');print(table.to_string(index=False));print(json.dumps(out,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['run']);p.parse_args();run()
