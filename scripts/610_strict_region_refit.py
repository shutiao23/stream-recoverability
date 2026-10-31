#!/usr/bin/env python3
"""Refit affected forward models after removing all same-region source groups.

This is an after-audit paired sensitivity. Original models and project results
are preserved. Existing role assignments and bootstrap multiplicities are
retained for all other groups; no replacement groups are selected.
"""
from __future__ import annotations
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
os.umask(0o077)
import json
from datetime import datetime,timezone
from pathlib import Path
import joblib
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'results/wrr_review_completion_20261024'
OUT=ROOT/'results/wrr_review_response_20261027/strict_region_holdout'
PRIVATE=ROOT/'private/wrr_strict_region_holdout_20261026'
REGIONS=['nve_hydapi','usgs_huc17']

def filtered_roles(c,region,seed,original_roles):
    held,roles,weights=original_roles(c,region,seed)
    forbidden=set(c.loc[c.region.eq(region),'independence_group'])
    forbidden_mask=c.independence_group.isin(forbidden).to_numpy()
    selected={name:[group for group in groups if group not in forbidden] for name,groups in roles.items()}
    adjusted={name:np.where(forbidden_mask,0.,np.asarray(weight,float)) for name,weight in weights.items()}
    for name,groups in selected.items():
        if len(groups)<2:raise ValueError(f'filtered {name} role has fewer than two groups')
        if set(groups)&forbidden or np.any(adjusted[name][forbidden_mask]>0):raise ValueError('same-region source group retained')
    return held,selected,adjusted

def strict_module():
    import wrr_tr_common as T
    refit=T.load_script('strict_region_refit',ROOT/'scripts/466_review_completion_refit.py')
    original=refit.roles
    refit.roles=lambda c,region,seed:filtered_roles(c,region,seed,original)
    refit.OUT=PRIVATE
    return refit

def main():
    audit=json.loads((ROOT/'results/wrr_review_response_20261027/audit/region_holdout_role_status.json').read_text())
    if audit['status']!='passed_audit_with_finding' or audit['held_test_group_overlap'] or audit['held_test_station_overlap']:
        raise RuntimeError('complete the original role audit first')
    if audit['affected_region_models_by_split']!={'before_2010':2}:raise RuntimeError('affected source model scope changed')
    OUT.mkdir(parents=True,exist_ok=True);PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);PRIVATE.chmod(0o700)
    source=SOURCE/'cases/before_2010/seed_00.parquet';config=ROOT/'configs/wrr_review_completion_20261024.json'
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'frozen_posthoc_sensitivity',
      'regions':REGIONS,'split':'before_2010','seed':0,'role_rule':'retain original role order and bootstrap multiplicities, then remove every group with any same-region source case from all source roles; no replacement groups',
      'evaluation':'original target groups and test-year cases retained; compare original versus strict models on common target cases; local whole-archive masks and inputs held fixed',
      'timing':'developed after the same-region source-role finding and earlier performance results; exploratory sensitivity, not a preregistered independent test',
      'limitation':'removing source groups also changes training or calibration sample size; source climate and recorded connected groups may remain dependent; region sensitivity does not prove causal effects'}
    plan_path=OUT/'plan.json'
    if plan_path.exists():
        prior=json.loads(plan_path.read_text())
        for k in ['regions','split','seed','role_rule']:
            if prior[k]!=plan[k]:raise RuntimeError(f'existing frozen plan differs: {k}')
    else:plan_path.write_text(json.dumps(plan,indent=2)+'\n')
    refit=strict_module();c=pd.read_parquet(source)
    c=c.loc[c.policy_choice.ne('unavailable')&c.eval_truth_h30.notna()].reset_index(drop=True)
    from stream_recoverability.seeds import plain_seed
    receipts_path=PRIVATE/'refit_receipts.json';receipts=json.loads(receipts_path.read_text()) if receipts_path.exists() else {}
    rows=[]
    for region in REGIONS:
        seed=plain_seed(7,0,sorted(c.region.unique()).index(region))
        held,roles,weights=refit.roles(c,region,seed)
        forbidden=set(c.loc[c.region.eq(region),'independence_group'])
        if any(set(groups)&forbidden for groups in roles.values()):raise ValueError('strict roles retain same-region groups')
        if any(np.any(w[c.region.eq(region).to_numpy()]>0) for w in weights.values()):raise ValueError('strict weights retain same-region cases')
        target=PRIVATE/'refits/before_2010/seed_00'/f'{region}.joblib'
        if target.exists() and region not in receipts:raise RuntimeError('existing strict model has no matching local receipt')
        result=refit.fit_region(0,region,'before_2010',str(source))
        if not target.is_file():raise RuntimeError('strict model was not saved')
        bundle=joblib.load(target)
        if bundle['roles']!=roles:raise ValueError('saved strict model roles differ')
        receipts[region]={'target_rows':int(held.sum()),'role_group_counts':{k:len(v) for k,v in roles.items()},
                          'same_region_positive_weight_cases':int(sum((w[c.region.eq(region).to_numpy()]>0).sum() for w in weights.values()))}
        receipts_path.write_text(json.dumps(receipts,indent=2)+'\n');receipts_path.chmod(0o600)
        rows.append({'region':region,'target_cases':int(held.sum()),'strict_source_same_region_cases':0,
                     **{f'{k}_groups':len(v) for k,v in roles.items()}})
        print('Strict source model ready:',region,'target cases',int(held.sum()),flush=True)
    table=pd.DataFrame(rows);table.to_csv(OUT/'refit_summary.csv',index=False)
    state={'status':'strict_models_refitted','regions':len(rows),'same_region_positive_weight_cases':0,
      'model_location':'local restricted directory, not in candidate bundle',
      'interpretation':'paired sensitivity preserves the old assignments and remaining multiplicities; no claim of independent climates or unchanged finite-sample guarantees'}
    (OUT/'refit_status.json').write_text(json.dumps(state,indent=2)+'\n')
    print(table.to_string(index=False));print(json.dumps(state,indent=2))

if __name__=='__main__':main()
