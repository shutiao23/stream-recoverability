#!/usr/bin/env python3
"""Check the fixed model's response to counterfactual history-count clipping."""
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
import argparse,json,sys
from datetime import datetime,timezone
from pathlib import Path
import joblib,numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');sys.path.insert(0,str(ROOT/'scripts'))
import wrr_tr_common as T, wrr_tr_features as F
REV=ROOT/'results/wrr_review_response_20261027';USACE=ROOT/'private/wrr_usace_reservoir_reference_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
def freeze():
 p=STAGE/'history_count_leaf_plan.json'
 if p.exists():raise FileExistsError('Preserve leaf audit plan')
 support=json.loads((STAGE/'feature_support_status.json').read_text())
 if support['status']!='completed_posthoc_support_and_conditional_gate':raise ValueError('Feature support not evaluated')
 files=[STAGE/'scored_cases.parquet',STAGE/'feature_support_status.json',USACE/'partial_history_feature_support.csv',SOURCE/'deployment/global_source_candidate.joblib',REV/'external_bc_air2stream/source_calibration.json',ROOT/'scripts/863_partial_history_clipping_audit.py',ROOT/'scripts/wrr_tr_features.py',Path(__file__)]
 doc={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after USGS accuracy, feature-support and release-gate results',
   'procedure':'For all 144 target cases replace the complete-history count only with the estimator-role minimum where below range. Compare all seven LightGBM quantile Booster leaves/raw values and classifier leaves/probabilities and independently reconstructed projected/calibrated quantiles against original values.',
   'interpretation':'The altered count is knowingly false and is not a valid missing-history treatment or release workaround. No target outcomes are used in this diagnostic, and identical paths do not prove accuracy or joint support.',
   'limitations':'Frozen source model, source cases and target predictions reused; source model training, independence, point quality and model calibration are not validated.',
   }
 p.write_text(json.dumps(doc,indent=2)+'\n');print('Frozen USGS complete-history-count leaf diagnostic')
def run():
 p=json.loads((STAGE/'history_count_leaf_plan.json').read_text())
 c=pd.read_parquet(STAGE/'scored_cases.parquet');support=pd.read_csv(USACE/'partial_history_feature_support.csv').set_index('feature');lo=float(support.loc['n_complete_years','source_min']);hi=float(support.loc['n_complete_years','source_max']);b=joblib.load(SOURCE/'deployment/global_source_candidate.joblib');cal=json.loads((REV/'external_bc_air2stream/source_calibration.json').read_text());m=T.load_script('usgs_count_direct_booster',ROOT/'scripts/863_partial_history_clipping_audit.py')
 raw,leaf,q,risk,clf=m.booster_evaluate(c,b,cal['D2_offsets']);cols=[f'D2_q{int(x*100):02d}' for x in F.QUANTILES]
 if not np.allclose(q,c[cols].to_numpy(float),atol=1e-10,rtol=0,equal_nan=True) or not np.allclose(risk,c.risk_score,atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Manual baseline differs')
 changed=c.copy();v=changed.n_complete_years.to_numpy(float);changed['n_complete_years']=np.clip(v,lo,hi);raw2,leaf2,q2,risk2,clf2=m.booster_evaluate(changed,b,cal['D2_offsets'])
 out={'status':'completed_posthoc_leaf_diagnostic','cases':len(c),'clipped_history_count_cases':int((v!=changed.n_complete_years.to_numpy(float)).sum()),
 'quantile_leaf_changed_cases':int(np.any(leaf!=leaf2,axis=(1,2)).sum()),'classifier_leaf_changed_cases':int(np.any(clf!=clf2,axis=1).sum()),
 'max_raw_quantile_change':float(np.max(np.abs(raw-raw2))),'max_projected_quantile_change':float(np.max(np.abs(q-q2))),'max_classifier_score_change':float(np.max(np.abs(risk-risk2))),
 'estimator_min_history':lo,'estimator_max_history':hi,'baseline_manually_reproduced':True,'limitations':p['limitations']+' '+p['interpretation'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'history_count_leaf_status.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
