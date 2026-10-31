#!/usr/bin/env python3
"""Independently recompute support-margin flags and matched-score summaries."""
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T
import wrr_tr_features as F

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'source_ood_release';PRIVATE=ROOT/'private/wrr_source_ood_release_20261027';USACE=ROOT/'private/wrr_usace_reservoir_reference_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024'

def main():
    h=T.load_script('source_margin_audit_hash',ROOT/'scripts/856_partial_history_feature_support_plan.py');plan=json.loads((OUT/'margin_sensitivity_plan.json').read_text());status=json.loads((OUT/'margin_sensitivity_status.json').read_text())
    source=pd.read_parquet(PRIVATE/'evaluated_cases.parquet');target=pd.read_parquet(USACE/'partial_history_scored_cases.parquet');support=pd.read_csv(USACE/'partial_history_feature_support.csv').set_index('feature');bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib')
    names=[x for x in bundle['features'] if x!='n_complete_years'];a=F.design_matrix(source,simulation=True).reindex(columns=names);b=F.design_matrix(target,simulation=True).reindex(columns=names)
    summary=pd.read_csv(OUT/'margin_sensitivity.csv');fail=np.abs(source.D2.to_numpy(float)-source.eval_truth_h30.to_numpy(float))>.5
    for row in summary.itertuples(index=False):
        sflag=np.zeros(len(source),bool);tflag=np.zeros(len(target),bool)
        for name in names:
            p=support.loc[name];lo=float(p.source_min);hi=float(p.source_max);ql=float(p.source_weighted_q01);qh=float(p.source_weighted_q99)
            scale=qh-ql if np.isfinite(ql) and np.isfinite(qh) and qh>ql else hi-lo
            if not np.isfinite(scale) or scale<=0:scale=1.
            for matrix,output in [(a,sflag),(b,tflag)]:
                z=matrix[name].to_numpy(float);outside=np.isfinite(z)&((z<lo-row.margin_fraction*scale)|(z>hi+row.margin_fraction*scale)) if np.isfinite(lo) and np.isfinite(hi) else np.isfinite(z)
                missing=(np.isnan(z)&(p.source_estimator_nan_rows==0))|(np.isposinf(z)&(p.source_estimator_posinf_rows==0))|(np.isneginf(z)&(p.source_estimator_neginf_rows==0))
                output|=outside|missing
        combined=source.risk_score.le(.1).to_numpy(bool)&~sflag;n=int(combined.sum());keys=['risk_score','station_key','year','design_family','realization_id','network_id','policy_choice']
        tuples=list(source[keys].itertuples(index=False,name=None));rank=sorted(range(len(source)),key=tuples.__getitem__);matched=np.zeros(len(source),bool);matched[rank[:n]]=True
        groups=[]
        for _,indices in source.groupby('independence_group',sort=True).groups.items():
            i=np.asarray(list(indices),int);groups.append((int(combined[i].sum()),int(matched[i].sum()),int((combined[i]&fail[i]).sum()),int((matched[i]&fail[i]).sum())))
        g=np.asarray(groups,int);rng=np.random.default_rng(20261027);ix=rng.integers(0,len(g),size=(4000,len(g)));sums=g[ix].sum(axis=1);valid=(sums[:,0]>0)&(sums[:,1]>0);d=sums[valid,2]/sums[valid,0]-sums[valid,3]/sums[valid,1]
        ext=target.loc[tflag,['resource_id','year']].drop_duplicates();checks={'source_eligible_cases':len(source),'source_warning_cases':sflag.sum(),
         'source_failed_cases':fail.sum(),'source_warning_detected_failures':(sflag&fail).sum(),'source_recall':(sflag&fail).sum()/fail.sum(),
         'source_false_positive_rate':(sflag&~fail).sum()/(~fail).sum(),'source_combined_numeric':n,'source_combined_errors':(combined&fail).sum(),
         'source_score_matched_numeric':matched.sum(),'source_score_matched_errors':(matched&fail).sum(),
         'conditional_failure_difference':fail[combined].mean()-fail[matched].mean(),'group_bootstrap_low':np.quantile(d,.025),
         'group_bootstrap_high':np.quantile(d,.975),'bootstrap_valid':len(d),'external_cases':len(target),'external_warning_cases':tflag.sum(),
         'external_flagged_station_years':len(ext),'external_flagged_stations':ext.resource_id.nunique()}
        for key,value in checks.items():
            if not np.isclose(value,getattr(row,key),atol=1e-10,rtol=0):raise AssertionError('Mismatch '+str(row.margin_fraction)+' '+key)
    out={'status':'passed','source_cases':len(source),'source_groups':source.independence_group.nunique(),'external_cases':len(target),
      'margins_checked':len(summary),'bootstrap_draws_per_margin':4000,'scope':'Independent feature-margin flags, deterministic score ranking, group totals and bootstrap summaries.',
      'limitations':'Same observed features, frozen source extrema and model outputs are reused. Tolerances are posthoc and do not establish error calibration, prospective release or independent climates.'}
    (OUT/'margin_sensitivity_independent_audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':main()
