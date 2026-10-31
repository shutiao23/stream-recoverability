#!/usr/bin/env python3
"""Audit the previously implicit bridge-repair input to source group maxima.

The repair table and source data remain local. This is a post-hoc dependency
reconstruction, not an independent model fit or provider-quality validation.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
import json
import hashlib
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
M=T.load_script('bridge_dependency_groupmax',ROOT/'scripts/720_groupmax_annual_calibration.py')
REPAIR=ROOT/'results/wrr_review_completion_20261024/repairs/before_2010/seed_00.parquet'

def main():
    M.verify_source()
    if not REPAIR.is_file():raise FileNotFoundError('The source bridge-repair table is required')
    pinned=[REPAIR,M.OUT/'plan.json',M.OUT/'source_freeze.json',Path(__file__).resolve()]
    input_sha256={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in pinned}
    infer=T.load_script('bridge_dependency_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
    repair=T.load_script('bridge_dependency_repair',ROOT/'scripts/467_review_completion_analysis.py')
    raw=pd.read_parquet(M.INPUT/'candidate_cases/before_2010/seed_00.parquet')
    raw=raw[raw.policy_choice.ne('unavailable')&raw.eval_truth_h30.notna()&raw.training_partition.eq('train')].reset_index(drop=True)
    if raw.year.ge(2010).any():raise ValueError('Post-2009 source case')
    fixed=repair.apply_bridge_repairs(raw.copy(),0,'before_2010')
    roster=pd.read_csv(ROOT/'private/wrr_projected_risk_sensitivity_20261027/roster.csv')
    saved=pd.read_parquet(M.PRIVATE/'source_group_scores.parquet')
    rows=[]
    for region in sorted(roster.region.unique()):
        bundle=joblib.load(M.INPUT/'refits/before_2010/seed_00'/f'{region}.joblib')
        cal=json.loads((M.INPUT/'calibrations/forward'/f'{region}.json').read_text());bundle['offsets']=cal['D2_offsets']
        pool=set(bundle['roles']['risk_learning'])|set(bundle['roles']['rule_calibration'])
        for family in ['calendar','crossed']:
            mask=raw.independence_group.isin(pool)&raw.design_family.eq(family)
            before=infer.classical_predictions(infer.predict(raw.loc[mask].copy(),bundle),cal)
            after=infer.classical_predictions(infer.predict(fixed.loc[mask].copy(),bundle),cal)
            if len(before)!=len(after) or not before.index.equals(after.index):raise ValueError('Repair source identities differ')
            for estimator,prefix in M.METHODS.items():
                cols=[f'{prefix}_q05',f'{prefix}_q95']
                a=before[cols].to_numpy(float);b=after[cols].to_numpy(float)
                both=np.isfinite(a).all(axis=1)&np.isfinite(b).all(axis=1)
                changed=int((np.max(np.abs(a[both]-b[both]),axis=1)>1e-10).sum()) if both.any() else 0
                truth=after.eval_truth_h30.to_numpy(float);bound=after.observed_lower_bound__observed_days.to_numpy(float)
                groups=after.independence_group.to_numpy();base=np.isfinite(truth)&np.isfinite(bound)&pd.notna(groups)
                with_valid=base&np.isfinite(b).all(axis=1);without_valid=base&np.isfinite(a).all(axis=1)
                yes,yes_groups=M.group_max_radius(truth[with_valid],b[with_valid,0],b[with_valid,1],groups[with_valid])
                no,no_groups=M.group_max_radius(truth[without_valid],a[without_valid,0],a[without_valid,1],groups[without_valid])
                actual=saved[(saved.region==region)&(saved.family==family)&(saved.estimator==estimator)].sort_values('group').reset_index(drop=True)
                compare=yes_groups.sort_values('group').reset_index(drop=True)
                if not actual.group.equals(compare.group) or not actual['size'].equals(compare['size']) or not np.allclose(actual['max'],compare['max'],rtol=0,atol=1e-10):
                    raise ValueError('Repaired source group maxima do not match saved analysis')
                joined=yes_groups.merge(no_groups,on='group',how='outer',suffixes=('_with','_without'),indicator=True,validate='one_to_one')
                diff=joined._merge.ne('both') | ((joined['max_with']-joined['max_without']).abs()>1e-10)
                rows.append({'region':region,'family':family,'estimator':estimator,'source_cases':len(after),
                    'both_quantiles_finite_cases':int(both.sum()),'cases_with_changed_interval_endpoints':changed,
                    'groups_with_changed_maximum_or_availability':int(diff.sum()),'with_repair_groups':yes['n_groups'],
                    'without_repair_groups':no['n_groups'],'with_repair_valid_cases':yes['n_cases'],
                    'without_repair_valid_cases':no['n_cases'],
                    'with_repair_radius':yes['radius'],'without_repair_radius':no['radius']})
            print('Checked bridge dependency:',region,family,flush=True)
    result=pd.DataFrame(rows)
    if len(result)!=24 or result.duplicated(['region','family','estimator']).any():raise ValueError('Bridge dependency cohort differs')
    for path in pinned:
        if hashlib.sha256(path.read_bytes()).hexdigest()!=input_sha256[str(path.relative_to(ROOT))]:
            raise ValueError('Bridge dependency input changed during numerical audit: '+str(path))
    result.to_csv(M.OUT/'source_repair_effect.csv',index=False)
    effect=M.OUT/'source_repair_effect.csv'
    input_sha256[str(effect.relative_to(ROOT))]=hashlib.sha256(effect.read_bytes()).hexdigest()
    report={'status':'passed','source_cells_checked':len(result),'repair_table_rows':len(pd.read_parquet(REPAIR)),
            'repair_path':str(REPAIR.relative_to(ROOT)),'repaired_source_group_maxima_reproduced':True,
            'input_sha256':input_sha256,
            'cells_with_changed_interval_endpoints':int(result.cases_with_changed_interval_endpoints.gt(0).sum()),
            'cells_with_changed_group_maximum':int(result.groups_with_changed_maximum_or_availability.gt(0).sum()),
            'cells_with_changed_radius':int((~np.isclose(pd.to_numeric(result.with_repair_radius,errors='coerce').to_numpy(float),
                                                       pd.to_numeric(result.without_repair_radius,errors='coerce').to_numpy(float),rtol=0,atol=1e-10,equal_nan=True)).sum()),
            'limitation':'Post-hoc dependency reconstruction on same source models and source cases. No independent source fit, physical measurement check or inference about data rights.'}
    (M.OUT/'source_repair_dependency.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
