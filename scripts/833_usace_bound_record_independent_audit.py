#!/usr/bin/env python3
"""Recompute complete-window and prior-accepted comparisons independently."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir'
PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027'

def main():
    plan=json.loads((OUT/'partial_year_record_screen_plan.json').read_text());status=json.loads((OUT/'partial_year_record_screen_status.json').read_text())
    path=PRIVATE/'partial_year_record_screen.csv'
    daily=pd.read_parquet(PRIVATE/'finite_daily.parquet');daily['day']=pd.to_datetime(daily.day)
    dates={(r.resource_id,r.day.date()):r.mean_c for r in daily.itertuples(index=False)}
    bounds=pd.read_csv(PRIVATE/'partial_year_h30_bounds.csv')
    saved=pd.read_csv(path).sort_values(['resource_id','year']).reset_index(drop=True)
    rows=[]
    for r in bounds.itertuples(index=False):
        index=pd.date_range(f'{r.year}-01-01',f'{r.year}-12-31')
        values=[dates.get((r.resource_id,d.date()),float('nan')) for d in index]
        valid=[float(np.mean(values[k:k+30])) for k in range(len(values)-29) if all(np.isfinite(values[k:k+30]))]
        maximum=max(valid) if valid else np.nan
        if np.isfinite(maximum) and maximum>r.h30_lower_c+1e-9:raise AssertionError('Observed window exceeds the lower bound')
        n=sum(np.isfinite(values))
        rows.append({'resource_id':r.resource_id,'year':r.year,'observed_h30_lower_c':maximum,
            'accept_95':n/r.expected_days>=.95,'accept_100':n==r.expected_days,'h30_upper_c':r.h30_upper_c})
    actual=pd.DataFrame(rows).sort_values(['resource_id','year']).reset_index(drop=True)
    for col in ['resource_id','year','accept_95','accept_100']:
        if not actual[col].equals(saved[col]):raise AssertionError('Mismatch '+col)
    if not np.allclose(actual.observed_h30_lower_c,saved.observed_h30_lower_c,atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Window mismatch')
    for gate in ['95','100']:
        nprior=[];witness=[]
        for r in actual.itertuples(index=False):
            prior=actual[(actual.resource_id==r.resource_id)&(actual.year<r.year)]
            old=prior[prior['accept_'+gate]]
            nprior.append(len(old));witness.append(bool(not getattr(r,'accept_'+gate) and len(old)>0 and np.isfinite(r.observed_h30_lower_c) and all(r.observed_h30_lower_c>q+1e-10 for q in old.h30_upper_c)))
        if nprior!=saved['prior_accepted_'+gate].tolist() or witness!=saved['guaranteed_added_record_'+gate].tolist():raise AssertionError('Record comparison mismatch')
        if sum(witness)!=status['rules'][gate]['guaranteed_added_record_years']:raise AssertionError('Aggregate mismatch')
    result={'status':'passed','station_years_recomputed':len(actual),'rules_recomputed':2,
      'visible_window_years':int(actual.observed_h30_lower_c.notna().sum()),
      'guaranteed_added_record_years_95':status['rules']['95']['guaranteed_added_record_years'],
      'scope':'Independent 30-day loops and chronological accepted-year comparisons; conditional on the same saved daily values and annual intervals.',
      'limitations':'No independent sensor verification, physical accuracy, full historical record or reconstruction accuracy assessed.'}
    (OUT/'partial_year_record_screen_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
