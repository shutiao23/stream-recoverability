#!/usr/bin/env python3
"""Check the original history gate on the partial-history external cases."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.outputs import release_states

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027'

def freeze():
    h=T.load_script('usace_gate_plan_hash',ROOT/'scripts/856_partial_history_feature_support_plan.py');path=OUT/'partial_history_gate_plan.json'
    if path.exists():raise FileExistsError('Preserve gate plan')
    if json.loads((OUT/'partial_history_feature_support_independent_audit.json').read_text())['status']!='passed':raise ValueError('Feature audit incomplete')
    files=[PRIVATE/'partial_history_scored_cases.parquet',ROOT/'src/stream_recoverability/experiments/tr_revision/outputs.py',
           OUT/'partial_history_feature_support_independent_audit.json',Path(__file__)]
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after external predictions, scores and feature-support findings',
      'analysis':'Apply the original release_states function to all 306 external cases with no optional range limits and quality_flag=False solely to isolate the mandatory complete-history gate. Separately count individual classifier scores <=0.1 and finite observed bounds.',
      'interpretation':'The <=0.1 score is not a calibrated group-risk guarantee. Empty limits and quality_flag=False are explicit hypothetical assumptions because source quality flags and the deployment thresholds are not established for these data; resulting bounds/unknown counts are conditional, not actual releases.',
      'limits':'A mandatory n_complete_years>=4 gate independently prevents numeric release when actual complete history is zero, regardless of risk score, optional thresholds or quality flag. This diagnostic does not validate risk or operational safety.',
      }
    path.write_text(json.dumps(plan,indent=2)+'\n');print('Frozen partial-history gate diagnostic')

def run():
    h=T.load_script('usace_gate_run_hash',ROOT/'scripts/856_partial_history_feature_support_plan.py');p=json.loads((OUT/'partial_history_gate_plan.json').read_text())
    c=pd.read_parquet(PRIVATE/'partial_history_scored_cases.parquet');lower=c.observed_lower_bound__observed_days.to_numpy(float)
    if len(c)!=306 or not c.n_complete_years.eq(0).all() or np.isinf(lower).any():raise ValueError('Unexpected cases or bound values')
    states=release_states(c,limits={},quality_flag=np.zeros(len(c),bool))
    expected=np.where(np.isfinite(lower),'observed_bound','unknown')
    if not np.array_equal(states,expected):raise AssertionError('Mandatory history gate did not determine the numeric state')
    out={'status':'completed_hypothetical_quality','cases':len(c),'actual_history_count_zero':int(c.n_complete_years.eq(0).sum()),
         'D2_finite':int(np.isfinite(c.D2).sum()),'individual_score_at_most_0_1':int(c.risk_score.le(.1).sum()),
         'numeric_states_with_no_quality_flag_and_no_optional_limits':int((states=='estimate').sum()),
         'bound_states_with_no_quality_flag_and_no_optional_limits':int((states=='observed_bound').sum()),
         'unknown_states_with_no_quality_flag_and_no_optional_limits':int((states=='unknown').sum()),
         'actual_quality_flags_available':False,'limits':p['interpretation']+' '+p['limits']}
    (OUT/'partial_history_gate_status.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
