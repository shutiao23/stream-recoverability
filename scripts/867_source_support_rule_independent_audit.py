#!/usr/bin/env python3
"""Independently reconstruct source warning decisions and matched errors."""
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T
import wrr_tr_features as F

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'source_ood_release';PRIVATE=ROOT/'private/wrr_source_ood_release_20261027';USACE=ROOT/'private/wrr_usace_reservoir_reference_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024'

def main():
    helper=T.load_script('source_ood_audit_hash',ROOT/'scripts/856_partial_history_feature_support_plan.py');plan=json.loads((OUT/'plan.json').read_text());status=json.loads((OUT/'status.json').read_text())
    c=pd.read_parquet(PRIVATE/'evaluated_cases.parquet');support=pd.read_csv(USACE/'partial_history_feature_support.csv').set_index('feature')
    bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib');cal=json.loads((REV/'external_bc_air2stream/source_calibration.json').read_text())
    independent=T.load_script('source_ood_booster_audit',ROOT/'scripts/863_partial_history_clipping_audit.py')
    raw,leaf,q,risk,cleaf=independent.booster_evaluate(c,bundle,cal['D2_offsets'])
    if not np.allclose(q[:,3],c.D2,atol=1e-10,rtol=0,equal_nan=True) or not np.allclose(risk,c.risk_score,atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Booster scores differ')
    design=F.design_matrix(c,simulation=True).reindex(columns=bundle['features']);warning=np.zeros(len(c),bool)
    for name in bundle['features']:
        if name=='n_complete_years':continue
        v=design[name].to_numpy(float);s=support.loc[name];finite=np.isfinite(v)
        if np.isfinite(s.source_min) and np.isfinite(s.source_max):out=finite&((v<s.source_min)|(v>s.source_max))
        else:out=finite
        out|=(np.isnan(v)&(s.source_estimator_nan_rows==0))|(np.isposinf(v)&(s.source_estimator_posinf_rows==0))|(np.isneginf(v)&(s.source_estimator_neginf_rows==0))
        warning|=out
    failure=np.abs(c.D2.to_numpy(float)-c.eval_truth_h30.to_numpy(float))>.5
    if not np.array_equal(warning,c.support_warning.to_numpy(bool)) or not np.array_equal(failure,c.failed.to_numpy(bool)):raise AssertionError('Warning or failure differs')
    lowrisk=c.risk_score.le(.1).to_numpy(bool);new=lowrisk&~warning;n=int(new.sum())
    keys=['risk_score','station_key','year','design_family','realization_id','network_id','policy_choice']
    # Explicit Python sorting independently implements the fixed deterministic ranking.
    sort_values=list(c[keys].itertuples(index=False,name=None));order=sorted(range(len(c)),key=sort_values.__getitem__);matched=np.zeros(len(c),bool);matched[order[:n]]=True
    if not np.array_equal(new,c.risk_plus_range_emit.to_numpy(bool)) or not np.array_equal(matched,c.risk_matched_emit.to_numpy(bool)):raise AssertionError('Decision differs')
    summaries=pd.read_csv(OUT/'policy_summary.csv').set_index('policy')
    for name,emit in [('risk_score_at_most_0.1',lowrisk),('risk_score_at_most_0.1_and_inside_range',new),('risk_only_same_numerical_count_posthoc',matched)]:
        group_size=c.groupby('independence_group').independence_group.transform('size').to_numpy(float);w=1/group_size
        values={'eligible_cases':len(c),'groups':c.independence_group.nunique(),'numerical_retention':emit.mean(),'numerical_errors':(emit&failure).sum(),
          'conditional_failure':failure[emit].mean(),'group_weighted_retention':w[emit].sum()/w.sum(),'group_weighted_failure':w[emit&failure].sum()/w[emit].sum()}
        for key,v in values.items():
            if not np.isclose(v,summaries.loc[name,key],atol=1e-10,rtol=0):raise AssertionError('Policy mismatch '+name+' '+key)
    actual={'cases_flagged':int(warning.sum()),'failures':int(failure.sum()),'true_positive':int((warning&failure).sum()),
       'false_positive':int((warning&~failure).sum()),'false_negative':int((~warning&failure).sum()),'true_negative':int((~warning&~failure).sum())}
    if any(status['warning'][k]!=v for k,v in actual.items()):raise AssertionError('Confusion matrix differs')
    saved=pd.read_csv(PRIVATE/'group_counts.csv').set_index('independence_group');records=[]
    for group,indices in c.groupby('independence_group',sort=True).groups.items():
        ii=np.asarray(list(indices),dtype=int);ff=failure[ii];ww=warning[ii];a=new[ii];b=matched[ii]
        x={'cases':len(ii),'failures':ff.sum(),'warnings':ww.sum(),'true_positive':(ff&ww).sum(),'false_positive':(~ff&ww).sum(),
           'risk_ood_emitted':a.sum(),'risk_ood_errors':(a&ff).sum(),'risk_matched_emitted':b.sum(),'risk_matched_errors':(b&ff).sum()}
        if any(int(saved.loc[group,k])!=int(v) for k,v in x.items()):raise AssertionError('Group totals differ')
        records.append(x)
    g=pd.DataFrame(records);rng=np.random.default_rng(20261027);ix=rng.integers(0,len(g),size=(4000,len(g)))
    a=g.risk_ood_emitted.to_numpy()[ix].sum(axis=1);b=g.risk_matched_emitted.to_numpy()[ix].sum(axis=1);valid=(a>0)&(b>0)
    dif=g.risk_ood_errors.to_numpy()[ix].sum(axis=1)[valid]/a[valid]-g.risk_matched_errors.to_numpy()[ix].sum(axis=1)[valid]/b[valid]
    target=status['matched_comparison']
    if len(dif)!=target['valid_bootstrap_draws'] or not np.allclose(np.quantile(dif,[.025,.975]),[target['group_bootstrap_low'],target['group_bootstrap_high']],atol=1e-10,rtol=0):raise AssertionError('Bootstrap differs')
    result={'status':'passed','eligible_cases':len(c),'groups':len(g),'model_cases_recomputed':len(c),'warning_cases':actual['cases_flagged'],
      'warning_failures_detected':actual['true_positive'],'matched_numeric_cases_per_policy':n,'group_bootstrap_draws':len(dif),
      'scope':'Direct Booster inference with independently applied calibration/support projection, feature warnings, truth-free matched-score ranking, per-group confusion counts and cluster bootstrap.',
      'limits':'Same source cases, feature-design code and fixed model are reused; does not establish unseen climates, sensor accuracy, prospective threshold validity or an operational risk guarantee.'}
    (OUT/'independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
