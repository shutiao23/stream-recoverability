#!/usr/bin/env python3
"""Record a post-hoc matched-gap sensitivity before its new scores are read."""
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import wrr_tr_common as T

ROOT=T.ROOT
OUT=ROOT/'results/wrr_review_response_20261027/heat_gap_matched'
PRIVATE=ROOT/'private/wrr_heat_gap_matched_20261027'

def main():
    path=OUT/'plan.json'
    if path.exists():raise FileExistsError('Preserve existing matched-gap sensitivity plan')
    if subprocess.run(['git','check-ignore','-q',str(PRIVATE.relative_to(ROOT))+'/probe'],cwd=ROOT).returncode:
        raise ValueError('Restricted output directory must be ignored by Git')
    old=T.load_script('heat_gap_old_plan_check',ROOT/'scripts/691_expanded_stress_comparison.py').verify_plan()
    if old['roster_count']!=41 or old['replicates']!=list(range(5)):
        raise ValueError('Original sensitivity cohort changed')
    paths=['scripts/734_gap_matched_heat_stress.py','scripts/691_expanded_stress_comparison.py',
           'results/wrr_review_response_20261027/expanded_stress/plan.json',
           'private/wrr_expanded_stress_20261027/roster.csv',
           'private/wrr_expanded_stress_20261027/input_manifest.json',
           'results/wrr_review_completion_20261024/repairs/before_2010/seed_00.parquet']
    OUT.mkdir(parents=True,exist_ok=True);PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'post-hoc plan after previous results and mask feasibility inspection; not preregistered',
          'scope':'41 existing forward-eligible stations, first five existing masks, crossed family; 205 settings',
          'selection':'Same heat-weighted selected years as 689: fixed original year count, weight five for air-hot years using pre-2010 burn-in and a separate seeded stream.',
          'gap_assignment':'Retain original masks for years selected in both scenarios. Assign remaining original whole offset/length templates to newly selected years, placing longer-ending templates first into the earliest feasible non-leap year then leap year. Reject if any template cannot fit.',
          'matched':'Identical number of masked years, multiset of original gap templates and aggregate gap days per archive; timestamps and years can change.',
          'measurement':'Paired available trend outcomes, coverage, width and interval score; report common-case and group counts, connected-group resampling and fixed-prediction leave-region-out.',
          'limitations':'Post-hoc after previous target results, scenario masks and feasibility were seen; selected years and positions change together, and transferring templates can alter their relation to seasonal peaks. Reuses source models, forcing and target archives; not a causal effect, natural-outage validation, independent climate or safety guarantee.',
          'privacy':'Station-level masks, target cases and model predictions remain local private; aggregate outputs only.',
          }
    path.write_text(json.dumps(plan,indent=2)+'\n')
    print('Recorded post-hoc matched-gap plan; no new scenario scores have been read.')

if __name__=='__main__':main()
