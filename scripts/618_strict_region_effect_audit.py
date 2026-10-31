#!/usr/bin/env python3
"""Audit strict exclusion effects on all saved seed-zero source model roles.

Check globally for held test stations/groups, positive case weights, and the
classifier/probability split, including groups with zero bootstrap weight.
This does not evaluate nonzero seeds or any unrecorded data dependencies.
"""
from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import wrr_tr_common as T
from stream_recoverability.seeds import plain_seed

ROOT=T.ROOT;SOURCE=ROOT/'results/wrr_review_completion_20261024';REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'strict_region_holdout';PRIVATE=ROOT/'private/wrr_strict_region_holdout_20261026'
SPLITS=['leave_one_year_out','before_2010','cold_to_hot','non_air_refit']


def risk_masks(c,roles,weights):
    groups=np.asarray(roles['risk_learning']);cut=max(2,int(len(groups)*.75))
    classifier=c.independence_group.isin(groups[:cut]).to_numpy()&(weights['risk_learning']>0)
    probability=c.independence_group.isin(groups[cut:]).to_numpy()&(weights['risk_learning']>0)
    return classifier,probability


def main():
    original=T.load_script('strict_effect_original',ROOT/'scripts/466_review_completion_refit.py')
    strict=T.load_script('strict_effect_refit',ROOT/'scripts/610_strict_region_refit.py').strict_module()
    rows=[]
    for split in SPLITS:
        path=SOURCE/'cases'/split/'seed_00.parquet';schema=pq.ParquetFile(path).schema.names
        cols=['region','independence_group','station_key','year','policy_choice','eval_truth_h30']
        if 'training_partition' in schema:cols.append('training_partition')
        c=pd.read_parquet(path,columns=cols);c=c.loc[c.policy_choice.ne('unavailable')&c.eval_truth_h30.notna()].reset_index(drop=True)
        regions=sorted(c.region.unique())
        for path in sorted((SOURCE/'refits'/split/'seed_00').glob('*.joblib')):
            region=path.stem;seed=plain_seed(7,0,regions.index(region));held,roles,w=original.roles(c,region,seed);held2,newroles,nw=strict.roles(c,region,seed)
            bundle=joblib.load(path)
            if bundle['roles']!=roles or not np.array_equal(held,held2):raise ValueError('saved role or target cohort mismatch')
            held_groups=set(c.loc[held,'independence_group']);held_stations=set(c.loc[held,'station_key']); forbidden=set(c.loc[c.region.eq(region),'independence_group'])
            station_overlap=group_overlap=forbidden_positive=0;weight_changes=role_changes=0
            for role in roles:
                pos=w[role]>0
                station_overlap+=len(set(c.loc[pos,'station_key'])&held_stations)
                group_overlap+=len(set(c.loc[pos,'independence_group'])&held_groups)
                forbidden_positive+=int((c.independence_group.isin(forbidden).to_numpy()&(nw[role]>0)).sum())
                if split=='before_2010' and np.any(pos & c.year.ge(2010).to_numpy()):raise ValueError('forward role includes post-2009 case')
                weight_changes+=int(np.count_nonzero(w[role]!=nw[role]))
                role_changes+=int(roles[role]!=newroles[role])
            oldclass,oldprob=risk_masks(c,roles,w);newclass,newprob=risk_masks(c,newroles,nw)
            row={'split':split,'region':region,'held_station_overlap_anywhere':station_overlap,'held_group_overlap_anywhere':group_overlap,
              'strict_forbidden_positive_cases':forbidden_positive,'changed_positive_weight_case_roles':weight_changes,'changed_role_lists':role_changes,
              'changed_classifier_case_memberships':int(np.count_nonzero(oldclass!=newclass)),
              'changed_probability_case_memberships':int(np.count_nonzero(oldprob!=newprob))}
            if station_overlap or group_overlap or forbidden_positive:raise ValueError('held or forbidden data in source role: '+str(row))
            if split=='before_2010' and region in ['nve_hydapi','usgs_huc17']:
                saved=joblib.load(PRIVATE/'refits'/split/'seed_00'/f'{region}.joblib')
                if saved['roles']!=newroles:raise ValueError('strict saved bundle roles differ')
            rows.append(row)
        print('Audited strict exclusion effects:',split,len(rows),'cumulative models',flush=True)
    out=pd.DataFrame(rows); out.to_csv(OUT/'all_source_role_effects.csv',index=False)
    changed=out.loc[out.changed_positive_weight_case_roles.gt(0)|out.changed_classifier_case_memberships.gt(0)|out.changed_probability_case_memberships.gt(0)]
    expected={('before_2010','nve_hydapi'),('before_2010','usgs_huc17')}
    actual=set(zip(changed.split,changed.region))
    if actual!=expected:raise ValueError('affected fit scope differs from existing strict refit: '+str(actual))
    status={'status':'passed','models_checked':len(out),'held_station_overlap_anywhere':int(out.held_station_overlap_anywhere.sum()),
      'held_group_overlap_anywhere':int(out.held_group_overlap_anywhere.sum()),'strict_forbidden_positive_cases':int(out.strict_forbidden_positive_cases.sum()),
      'models_with_changed_positive_weights_or_classifier_split':len(changed),
      'changed_models':[{'split':s,'region':r} for s,r in sorted(actual)],
      'risk_learning_split_case_changes':int(out.changed_classifier_case_memberships.sum()+out.changed_probability_case_memberships.sum()),
      'scope':'four saved source splits, seed zero; verifies global station/group roles and source weights, plus effective classifier/probability memberships and strict saved roles',
      'limitation':'does not assess physical independence, nonzero seeds, unrecorded input dependencies or downstream results that depend on zero-weight role membership'}
    (OUT/'all_source_role_effects_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(out.loc[out.changed_role_lists.gt(0)].to_string(index=False));print(json.dumps(status,indent=2))
if __name__=='__main__':main()
