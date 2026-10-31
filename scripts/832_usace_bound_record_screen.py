#!/usr/bin/env python3
"""Compare visible 30-day windows and annual completeness screening."""
from datetime import datetime,timezone
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir'
PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027'

def freeze():
    path=OUT/'partial_year_record_screen_plan.json'
    if path.exists():raise FileExistsError('Preserve record-screen plan')
    a=json.loads((OUT/'partial_year_bounds_independent_audit.json').read_text())
    s=json.loads((OUT/'partial_year_bounds_status.json').read_text())
    f=json.loads((OUT/'finite_reference_status.json').read_text())
    if a['status']!='passed':
        raise ValueError('Bounds or finite daily inputs changed')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
      'status':'posthoc after inspecting whole-cohort H30 bound widths, before this record-screen comparison',
      'cohort':'All ten resources and all 2021-2025 station-years; chronological comparisons limited to the study window.',
      'visible_window':'Largest 30-day mean using only fully observed 96-value days. No threshold is imposed on the observed 30-day window.',
      'annual_rules':'Accept an annual observation if complete 96-reading days comprise at least 95% or 100% of the calendar year. These are generic sensitivity rules, not claims about a particular published H30 protocol.',
      'guaranteed_added_record':'For a rejected target year with a complete visible 30-day window, require at least one earlier accepted year under the same gate and visible lower bound strictly above every earlier accepted year annual upper H30 bound. This proves a higher target H30 only among those earlier accepted years and only under the assumed slot bounds and reported values.',
      'limitations':'Bound assumptions, possible corrections, instrument accuracy, sensor clock, source overlaps and climate independence remain unresolved; neither full historical records nor model accuracy are evaluated.',
      }
    path.write_text(json.dumps(plan,indent=2)+'\n');print('Frozen record-screen calculation')

def run():
    p=json.loads((OUT/'partial_year_record_screen_plan.json').read_text())
    bounds=pd.read_csv(PRIVATE/'partial_year_h30_bounds.csv')
    daily=pd.read_parquet(PRIVATE/'finite_daily.parquet');daily['day']=pd.to_datetime(daily.day)
    rows=[]
    for row in bounds.itertuples(index=False):
        idx=pd.date_range(f'{row.year}-01-01',f'{row.year}-12-31',freq='D')
        values=daily.loc[(daily.resource_id==row.resource_id)&daily.day.isin(idx)].set_index('day').mean_c.reindex(idx)
        if len(values)!=row.expected_days or int(values.notna().sum())!=row.complete_days:raise ValueError('Daily snapshot mismatch')
        roll=values.rolling(30,min_periods=30).mean()
        l=float(roll.max()) if roll.notna().any() else np.nan
        if np.isfinite(l) and l>row.h30_upper_c+1e-9:raise ValueError('Visible lower bound exceeds interval upper bound')
        rows.append({'resource_id':row.resource_id,'year':row.year,'observed_h30_lower_c':l,
            'complete_days':row.complete_days,'expected_days':row.expected_days,
            'h30_lower_c':row.h30_lower_c,'h30_upper_c':row.h30_upper_c,'h30_interval_width_c':row.h30_interval_width_c,
            'accept_95':row.complete_days/row.expected_days>=.95,'accept_100':row.complete_days==row.expected_days})
    frame=pd.DataFrame(rows).sort_values(['resource_id','year']).reset_index(drop=True)
    for name in ['95','100']:
        flag='accept_'+name; record=[]; baseline=[]
        for r in frame.itertuples(index=False):
            old=frame[(frame.resource_id==r.resource_id)&(frame.year<r.year)&frame[flag]]
            baseline.append(len(old))
            record.append(bool(not getattr(r,flag)
                and len(old)>0
                and np.isfinite(r.observed_h30_lower_c)
                and r.observed_h30_lower_c>old.h30_upper_c.max()+1e-10))
        frame['prior_accepted_'+name]=baseline;frame['guaranteed_added_record_'+name]=record
    dest=PRIVATE/'partial_year_record_screen.csv';frame.to_csv(dest,index=False);dest.chmod(0o600)
    out={'status':'completed','resources':int(frame.resource_id.nunique()),'station_years':len(frame),
        'visible_30_day_window_years':int(frame.observed_h30_lower_c.notna().sum()),
        'rules':{name:{'accepted_years':int(frame['accept_'+name].sum()),
             'rejected_years_with_visible_window':int((~frame['accept_'+name]&frame.observed_h30_lower_c.notna()).sum()),
             'rejected_with_prior_accepted_year':int((~frame['accept_'+name]&frame['prior_accepted_'+name].gt(0)).sum()),
             'guaranteed_added_record_years':int(frame['guaranteed_added_record_'+name].sum())} for name in ['95','100']},
        'limitations':p['limitations']}
    (OUT/'partial_year_record_screen_status.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args();freeze() if a.action=='freeze' else run()
