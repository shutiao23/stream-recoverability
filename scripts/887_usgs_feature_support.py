#!/usr/bin/env python3
"""Check USGS target feature support and the original history release gate."""
import argparse,importlib.util,json,sys
from datetime import datetime,timezone
from pathlib import Path
import joblib,numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');sys.path.insert(0,str(ROOT/'scripts'))
import wrr_tr_common as T, wrr_tr_features as F
from stream_recoverability.experiments.tr_revision.outputs import release_states
REV=ROOT/'results/wrr_review_response_20261027';USACE=ROOT/'private/wrr_usace_reservoir_reference_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
def freeze():
 p=STAGE/'feature_support_plan.json'
 if p.exists():raise FileExistsError('Preserve support plan')
 if json.loads((STAGE/'score_independent_audit.json').read_text())['status']!='passed' or json.loads((STAGE/'prediction_replay_status.json').read_text())['status']!='passed':raise ValueError('Target score or model replay not verified')
 files=[STAGE/'scored_cases.parquet',STAGE/'score_status.json',STAGE/'score_independent_audit.json',STAGE/'prediction_replay_status.json',USACE/'partial_history_feature_support.csv',REV/'external_usace_reservoir/partial_history_feature_support_independent_audit.json',SOURCE/'deployment/global_source_candidate.joblib',ROOT/'scripts/wrr_tr_features.py',ROOT/'src/stream_recoverability/experiments/tr_revision/outputs.py',Path(__file__)]
 doc={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after USGS target predictions, errors, source-range and reservoir results were inspected',
 'scope':'All 144 USGS cases, comparing the fixed global model inputs to its previously audited positive-weight estimator feature minima/maxima. Separately exclude n_complete_years, and apply 0 and 1% source weighted 1st-99th-percentile-span margins previously used in the reservoir sensitivity; unknown nonfinite types remain flags.',
 'release_gate':'Apply the original mandatory n_complete_years>=4 gate, risk score <=0.1 and availability. For illustration only assume no quality flags and omit optional range limits; actual quality flags are unknown. Report observed-bound/unknown outcomes as conditional, not actual releases.',
 'limitations':'Source estimator feature ranges are one-dimensional and do not prove joint support or risk. All 8 years and earlier source/target results were previously opened; repeated masks, clock/sensor uncertainty, source overlap and independent-climate questions remain. No target performance or status is altered.',
 }
 p.write_text(json.dumps(doc,indent=2)+'\n');print('Frozen USGS source-support and history-gate diagnostic')
def run():
 p=json.loads((STAGE/'feature_support_plan.json').read_text())
 c=pd.read_parquet(STAGE/'scored_cases.parquet');s=pd.read_csv(USACE/'partial_history_feature_support.csv').set_index('feature');b=joblib.load(SOURCE/'deployment/global_source_candidate.joblib');x=F.design_matrix(c,simulation=True).reindex(columns=b['features']);counts=[];summaries=[]
 for margin in [0.,.01]:
  flags=np.zeros((len(c),len(b['features'])),bool)
  for j,name in enumerate(b['features']):
   z=x[name].to_numpy(float);q=s.loc[name];lo=float(q.source_min);hi=float(q.source_max);ql=float(q.source_weighted_q01);qh=float(q.source_weighted_q99);scale=qh-ql if np.isfinite(ql) and np.isfinite(qh) and qh>ql else hi-lo
   if not np.isfinite(scale) or scale<=0:scale=1.
   bad=np.isfinite(z)&((z<lo-margin*scale)|(z>hi+margin*scale)) if np.isfinite(lo) and np.isfinite(hi) else np.isfinite(z)
   bad|=(np.isnan(z)&(q.source_estimator_nan_rows==0))|(np.isposinf(z)&(q.source_estimator_posinf_rows==0))|(np.isneginf(z)&(q.source_estimator_neginf_rows==0));flags[:,j]=bad
   counts.append({'margin_fraction':margin,'feature':name,'flagged_cases':int(bad.sum())})
  keep=np.asarray(b['features'])!='n_complete_years';hour=c.hourly_reference_posthoc.to_numpy(bool)
  summaries.append({'margin_fraction':margin,'cases':len(c),'any_feature_flagged':int(flags.any(axis=1).sum()),'any_noncount_feature_flagged':int(flags[:,keep].any(axis=1).sum()),
    'target_years_noncount_flagged':len(c.loc[flags[:,keep].any(axis=1),['station_id','year']].drop_duplicates()),'hourly_supported_cases':int(hour.sum()),'hourly_supported_noncount_flagged':int((flags[:,keep].any(axis=1)&hour).sum())})
 states=release_states(c,limits={},quality_flag=np.zeros(len(c),bool));
 if c.n_complete_years.ge(4).any() or (states=='estimate').any():raise AssertionError('Mandatory history gate unexpected')
 metrics={'cases':len(c),'complete_history_counts':{str(k):int(v) for k,v in c.n_complete_years.value_counts().sort_index().items()},'individual_score_le_0_1':int(c.risk_score.le(.1).sum()),
   'numerical_states_if_no_quality_flag_or_optional_limits':int((states=='estimate').sum()),'bound_states_if_no_quality_flag_or_optional_limits':int((states=='observed_bound').sum()),'unknown_states_if_no_quality_flag_or_optional_limits':int((states=='unknown').sum()),'actual_quality_flags_available':False}
 pd.DataFrame(counts).to_csv(STAGE/'feature_support_counts.csv',index=False);pd.DataFrame(summaries).to_csv(STAGE/'feature_support_summary.csv',index=False)
 out={'status':'completed_posthoc_support_and_conditional_gate','support':summaries,'gate':metrics,'limitations':p['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'feature_support_status.json').write_text(json.dumps(out,indent=2)+'\n');print(pd.DataFrame(summaries).to_string(index=False));print(json.dumps(metrics,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
