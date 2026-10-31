#!/usr/bin/env python3
"""Reassess range warnings under fixed feature-scaled tolerance margins."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
import wrr_tr_common as T
import wrr_tr_features as F

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'source_ood_release';EXTERNAL=REV/'external_usace_reservoir';PRIVATE=ROOT/'private/wrr_source_ood_release_20261027';USACE=ROOT/'private/wrr_usace_reservoir_reference_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024'
MARGINS=(0.,.000001,.01)

def freeze():
    h=T.load_script('source_margin_hash',ROOT/'scripts/856_partial_history_feature_support_plan.py');audit=json.loads((OUT/'independent_audit.json').read_text());status=json.loads((OUT/'status.json').read_text())
    if audit['status']!='passed':raise ValueError('Earlier rule audit incomplete')
    path=OUT/'margin_sensitivity_plan.json'
    if path.exists():raise FileExistsError('Preserve margin plan')
    files=[PRIVATE/'evaluated_cases.parquet',USACE/'partial_history_scored_cases.parquet',USACE/'partial_history_feature_support.csv',
      SOURCE/'deployment/global_source_candidate.joblib',ROOT/'scripts/wrr_tr_features.py',ROOT/'scripts/866_source_support_rule_evaluation.py',
      OUT/'independent_audit.json',OUT/'status.json',Path(__file__)]
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
      'status':'posthoc after exact-range detector and model outcomes were inspected; fixed tolerance levels before this sensitivity',
      'cohort':'All 8010 prior eligible source rule-role cases and all 306 previously scored external partial-history cases.',
      'margins':'For each feature except complete-history count, enlarge the observed training minimum and maximum by fractions 0, 0.000001 and 0.01 of its source weighted 1%-99% span; if that span is nonpositive use the finite training full range, and if that is also zero use scale 1. Nonfinite categories unseen in training remain warnings irrespective of margin. These tolerances are descriptive, not prespecified regulatory or sensor-error limits.',
      'evaluation':'For each margin compute source failure recall and false-positive rate, source risk<=0.1 plus no-warning retention and error, a target-score-ranked risk-only policy with exactly the same numerical count, and 4000 connected-group bootstrap draws for the difference in conditional error. Also report flagged external cases and station-years without evaluating any new target truth.',
      'limitations':'Margins and their scale were chosen after source and target results; no prospective selection or calibration guarantee. Source rule groups were previously opened for other analyses and source mask cases repeat. Bounds do not establish multivariate support, valid release or independent climates.',
      'margins':list(MARGINS),}
    path.write_text(json.dumps(plan,indent=2)+'\n');print('Frozen posthoc support-margin sensitivity')

def warning(design,support,names,margin):
    flags=np.zeros((len(design),len(names)),bool)
    for j,name in enumerate(names):
        s=support.loc[name];v=design[name].to_numpy(float);finite=np.isfinite(v);lo=float(s.source_min);hi=float(s.source_max);ql=float(s.source_weighted_q01);qh=float(s.source_weighted_q99)
        if np.isfinite(lo) and np.isfinite(hi):
            scale=qh-ql if np.isfinite(ql) and np.isfinite(qh) and qh>ql else hi-lo
            if not np.isfinite(scale) or scale<=0:scale=1.
            outside=finite&((v<lo-margin*scale)|(v>hi+margin*scale))
        else:outside=finite
        unseen=(np.isnan(v)&(s.source_estimator_nan_rows==0))|(np.isposinf(v)&(s.source_estimator_posinf_rows==0))|(np.isneginf(v)&(s.source_estimator_neginf_rows==0))
        flags[:,j]=outside|unseen
    return flags.any(axis=1)

def run():
    h=T.load_script('source_margin_run_hash',ROOT/'scripts/856_partial_history_feature_support_plan.py');plan=json.loads((OUT/'margin_sensitivity_plan.json').read_text())
    source=pd.read_parquet(PRIVATE/'evaluated_cases.parquet');target=pd.read_parquet(USACE/'partial_history_scored_cases.parquet');support=pd.read_csv(USACE/'partial_history_feature_support.csv').set_index('feature')
    bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib');names=[x for x in bundle['features'] if x!='n_complete_years']
    a=F.design_matrix(source,simulation=True).reindex(columns=names);b=F.design_matrix(target,simulation=True).reindex(columns=names)
    policy=T.load_script('source_margin_policy',ROOT/'scripts/866_source_support_rule_evaluation.py');fail=source.failed.to_numpy(bool);lowrisk=source.risk_score.le(.1).to_numpy(bool);rows=[]
    for margin in MARGINS:
        ws=warning(a,support,names,margin);wt=warning(b,support,names,margin)
        if margin==0 and not np.array_equal(ws,source.support_warning.to_numpy(bool)):raise AssertionError('Zero margin differs from original warning')
        combined=lowrisk&~ws;matched=policy.matched_risk_only(source,int(combined.sum()))
        x=source[['independence_group']].copy();x['a']=combined;x['b']=matched;x['ae']=combined&fail;x['be']=matched&fail
        g=x.groupby('independence_group',sort=True)[['a','b','ae','be']].sum();rng=np.random.default_rng(20261027);index=rng.integers(0,len(g),size=(4000,len(g)))
        an=g.a.to_numpy()[index].sum(axis=1);bn=g.b.to_numpy()[index].sum(axis=1);ae=g.ae.to_numpy()[index].sum(axis=1);be=g.be.to_numpy()[index].sum(axis=1);ok=(an>0)&(bn>0)
        dif=ae[ok]/an[ok]-be[ok]/bn[ok]
        ext=target.loc[wt,['resource_id','year']].drop_duplicates()
        rows.append({'margin_fraction':margin,'source_eligible_cases':len(source),'source_warning_cases':int(ws.sum()),
          'source_failed_cases':int(fail.sum()),'source_warning_detected_failures':int((ws&fail).sum()),
          'source_recall':float((ws&fail).sum()/fail.sum()),'source_false_positive_rate':float((ws&~fail).sum()/(~fail).sum()),
          'source_combined_numeric':int(combined.sum()),'source_combined_errors':int((combined&fail).sum()),
          'source_score_matched_numeric':int(matched.sum()),'source_score_matched_errors':int((matched&fail).sum()),
          'conditional_failure_difference':float(fail[combined].mean()-fail[matched].mean()),
          'group_bootstrap_low':float(np.quantile(dif,.025)),'group_bootstrap_high':float(np.quantile(dif,.975)),'bootstrap_valid':int(ok.sum()),
          'external_cases':len(target),'external_warning_cases':int(wt.sum()),'external_flagged_station_years':len(ext),'external_flagged_stations':ext.resource_id.nunique()})
    table=pd.DataFrame(rows);table.to_csv(OUT/'margin_sensitivity.csv',index=False)
    result={'status':'completed_posthoc_sensitivity','margins':list(MARGINS),'source_cases':len(source),'external_cases':len(target),
      'source_groups':int(source.independence_group.nunique()),'limitations':plan['limitations']}
    (OUT/'margin_sensitivity_status.json').write_text(json.dumps(result,indent=2)+'\n');print(table.to_string(index=False));print(json.dumps(result,indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
