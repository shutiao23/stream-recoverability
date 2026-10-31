#!/usr/bin/env python3
"""Audit whether existing seed-zero source roles exclude full held regions.

This distinguishes a same-region, different-group source observation from
leakage of an actual held target group. Counts are aggregate; no source values
or site identifiers are exported.
"""
from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import wrr_tr_common as T
from stream_recoverability.seeds import plain_seed

ROOT=T.ROOT
SOURCE=ROOT/'results/wrr_review_completion_20261024'
REV=ROOT/'results/wrr_review_response_20261027'
OUT=REV/'audit'
SPLITS=['leave_one_year_out','before_2010','cold_to_hot','non_air_refit']


def main():
    refit=T.load_script('role_audit_refit',ROOT/'scripts/466_review_completion_refit.py')
    results=[];models=[]
    for split in SPLITS:
        path=SOURCE/'cases'/split/'seed_00.parquet';schema=pq.ParquetFile(path).schema.names
        columns=['region','independence_group','station_key','year','policy_choice','eval_truth_h30']
        if 'training_partition' in schema:columns.append('training_partition')
        c=pd.read_parquet(path,columns=columns)
        c=c.loc[c.policy_choice.ne('unavailable')&c.eval_truth_h30.notna()].reset_index(drop=True)
        regions=sorted(c.region.unique())
        paths=sorted((SOURCE/'refits'/split/'seed_00').glob('*.joblib'))
        for path in paths:
            region=path.stem;bundle=joblib.load(path)
            seed=plain_seed(7,0,regions.index(region));held,roles,weights=refit.roles(c,region,seed)
            if roles!=bundle['roles']:raise ValueError(f'saved roles do not match recomputation: {split}/{region}')
            held_groups=set(c.loc[held,'independence_group']);held_stations=set(c.loc[held,'station_key'])
            region_groups=set(c.loc[c.region.eq(region),'independence_group'])
            model={'split':split,'region':region,'held_test_groups':len(held_groups),'held_test_stations':len(held_stations),
                   'all_region_groups':len(region_groups),'training_partition_present':'training_partition' in c}
            for role,groups in roles.items():
                group_set=set(groups);weight=np.asarray(weights[role]);positive=weight>0
                if group_set&held_groups or set(c.loc[positive,'independence_group'])&held_groups:
                    raise ValueError(f'held test group appears in training role: {split}/{region}/{role}')
                same=positive&c.region.eq(region).to_numpy()
                cross_same_groups=group_set&region_groups
                same_data=c.loc[same]
                direct_same_station=set(same_data.station_key)&held_stations
                if direct_same_station:raise ValueError(f'held target station appears in source role: {split}/{region}/{role}')
                after_cutoff=int((same_data.year.ge(2010)).sum()) if split=='before_2010' else 0
                if after_cutoff:raise ValueError('forward source role contains post-2009 same-region cases')
                row=model|{'role':role,'same_region_groups_listed':len(cross_same_groups),
                     'same_region_groups_with_positive_weight':int(same_data.independence_group.nunique()),
                     'same_region_stations_with_positive_weight':int(same_data.station_key.nunique()),
                     'same_region_cases_with_positive_weight':len(same_data),
                     'same_region_bootstrap_weighted_cases':int(weight[same].sum()),
                     'held_test_group_intersection':0,'held_test_station_intersection':0,
                     'max_same_region_source_year':int(same_data.year.max()) if len(same_data) else None}
                results.append(row)
            models.append(model)
        print('Audited',split,'models',len(paths),flush=True)
    table=pd.DataFrame(results);table.to_csv(OUT/'region_holdout_role_audit.csv',index=False)
    affected=table.loc[table.same_region_groups_with_positive_weight.gt(0)]
    regions=affected.groupby('split').region.nunique().to_dict()
    trends=pd.read_csv(REV/'whole_archive/trends.csv')
    q=trends.loc[trends['mode'].eq('forward')&trends.region.eq('usgs_huc17')&trends.estimator.eq('D2')&trends.retention.eq('all')&trends.dependence.eq('independent')]
    future=pd.read_parquet(REV/'release_outputs/future_years.parquet',columns=['region'])
    report={'status':'passed_audit_with_finding','models_checked':len(models),'role_rows_checked':len(table),
       'same_region_positive_weight_role_rows':len(affected),'affected_region_models_by_split':{k:int(v) for k,v in regions.items()},
       'held_test_group_overlap':0,'held_test_station_overlap':0,
       'forward_usgs_huc17_archive_station_repetitions':len(q),'forward_usgs_huc17_archive_stations':int(q.station_key.nunique()),
       'future_release_target_cases_in_affected_regions':int(future.region.isin(['nve_hydapi','usgs_huc17']).sum()),
       'scope':'seed-zero source model roles for the four source splits used by release/stress analyses; recorded role assignments and bootstrap weights, not re-trained models',
       'finding':'for partitioned splits, held test groups are excluded but other training-only groups within the same named region can enter source roles; this is not evidence that a held target station was in model fitting',
       'limitation':'stored roles and reproducible bootstrap weights identify positive-weight source cases; hidden observations, model sensitivity and non-seed-zero split variants are not audited here'}
    (OUT/'region_holdout_role_status.json').write_text(json.dumps(report,indent=2)+'\n')
    print(affected[['split','region','role','same_region_groups_with_positive_weight','same_region_stations_with_positive_weight','same_region_cases_with_positive_weight','same_region_bootstrap_weighted_cases','max_same_region_source_year']].to_string(index=False))
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
