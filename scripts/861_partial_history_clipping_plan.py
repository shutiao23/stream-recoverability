#!/usr/bin/env python3
"""Freeze post-hoc tree-boundary sensitivity of unsupported input features."""
from datetime import datetime,timezone
import json
from pathlib import Path
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024'

def main():
    helper=T.load_script('usace_clipping_plan_hash',ROOT/'scripts/856_partial_history_feature_support_plan.py')
    path=OUT/'partial_history_clipping_plan.json'
    if path.exists():raise FileExistsError('Preserve clipping plan')
    for name in ['partial_history_feature_support_independent_audit.json','partial_history_autocorrelation_independent_audit.json']:
        if json.loads((OUT/name).read_text())['status']!='passed':raise ValueError('Prior feature audit incomplete')
    files=[PRIVATE/'partial_history_feature_support.csv',PRIVATE/'partial_history_scored_cases.parquet',
           SOURCE/'deployment/global_source_candidate.joblib',ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json',
           ROOT/'scripts/495_review_completion_independent_analysis.py',ROOT/'scripts/wrr_tr_features.py',
           OUT/'partial_history_feature_support_independent_audit.json',OUT/'partial_history_autocorrelation_independent_audit.json',
           ROOT/'scripts/862_partial_history_clipping_sensitivity.py',Path(__file__)]
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
      'status':'posthoc after external scores, all-feature support flags and observed-only correlation analysis; before clipping predictions were calculated',
      'cohort':'All 306 fixed external partial-history cases and the same saved global model, source calibration and observation-support projection.',
      'interventions':'Hold all features fixed except, separately, n_complete_years, law_phi_a, law_phi_r, or all three. Clip each selected feature to the finite min/max of positive-weight global estimator-role training rows. Keep missing inputs missing.',
      'metrics':'First recompute original D2 point, all seven quantiles and individual score and check against saved predictions. For every clipping variant compare all seven raw quantile-regression outputs and all projected/calibrated D2 quantiles, point estimate and classifier score with unmodified inputs. Report changed case counts and maximum absolute changes, not target errors or outcomes.',
      'meaning':'Artificially changing a complete-history count or other features does not reconstruct a valid history and is not a recommended deployment procedure. The exercise only checks whether the frozen tree ensemble differentiates these particular out-of-range inputs from training-edge values. It does not prove calibration or valid transfer.',
      'limits':'One-dimensional ranges ignore joint feature support. A lack of response can arise from model splits or lower-bound projection; report raw model outputs separately. Previous targets and source results have been inspected; no independent test or climate guarantee.',
      }
    path.write_text(json.dumps(plan,indent=2)+'\n');print('Frozen post-hoc clipping sensitivity for 306 cases')

if __name__=='__main__':main()
