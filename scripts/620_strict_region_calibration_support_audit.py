#!/usr/bin/env python3
"""Upper-bound source group availability before strict model predictions."""
import json
from pathlib import Path
import joblib
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'strict_region_holdout';SOURCE=ROOT/'results/wrr_review_completion_20261024';PRIVATE=ROOT/'private/wrr_strict_region_holdout_20261026'


def main():
    old=joblib.load(SOURCE/'refits/before_2010/seed_00/usgs_huc17.joblib');new=joblib.load(PRIVATE/'refits/before_2010/seed_00/usgs_huc17.joblib')
    role=set(old['roles']['rule_calibration'])
    if role!=set(new['roles']['rule_calibration']):raise ValueError('HUC17 source rule roles changed')
    mod=T.load_script('strict_calibration_source',ROOT/'scripts/581_source_annual_interval_expansion.py')
    rows=[]
    for family in ['calendar','crossed']:
        src=mod.read_source(family,'forward');selected=src.loc[src.independence_group.isin(role)]
        n=selected.independence_group.nunique()
        if n>=3:raise ValueError('raw source group upper bound permits calibration; full recomputation needed')
        if selected.year.ge(2010).any() or selected.region.eq('usgs_huc17').any():raise ValueError('invalid source temporal or region exclusion')
        for name in ['annual_interval_expansion/source_support.csv','whole_archive/task_calibration_sources.csv']:
            a=pd.read_csv(REV/name);a=a.loc[a.family.eq(family)&a['mode'].eq('forward')&a.region.eq('usgs_huc17')]
            if len(a)!=2 or not a.status.eq('insufficient_source_groups').all() or (a.n_source_groups>n).any():raise ValueError('recorded calibration support not bounded by source roster')
        rows.append({'family':family,'source_cases_before_prediction':len(selected),'eligible_group_upper_bound':int(n),'minimum_required_groups':3,
          'strict_annual_expansion':'unsupported_by_group_count','strict_task_calibration':'unsupported_by_group_count'})
    pd.DataFrame(rows).to_csv(OUT/'calibration_source_upper_bound.csv',index=False)
    status={'status':'passed','source_group_upper_bound_before_model_predictions':max(x['eligible_group_upper_bound'] for x in rows),
      'minimum_groups_required':3,'original_and_strict_rule_groups_match':True,
      'conclusion':'strict HUC17 annual expansion and task calibration remain unsupported for either estimator because raw eligible source groups are too few; no model-dependent calibration radius is asserted',
      'scope':'forward HUC17 only; original source archive calibration cases and identical strict rule-role list; not an independent validation or a group-risk guarantee'}
    (OUT/'calibration_source_upper_bound_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(pd.DataFrame(rows).to_string(index=False));print(json.dumps(status,indent=2))
if __name__=='__main__':main()
