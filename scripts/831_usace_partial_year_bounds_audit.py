#!/usr/bin/env python3
"""Independently reconstruct H30 interval bounds using pandas group operations."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/wrr_review_response_20261027/external_usace_reservoir'
DATA = ROOT/'data/external/wrr_usace_reservoir_20261027'
PRIVATE = ROOT/'private/wrr_usace_reservoir_reference_20261027'

def main():
    plan=json.loads((OUT/'partial_year_bounds_plan.json').read_text())
    status=json.loads((OUT/'partial_year_bounds_status.json').read_text())
    saved=PRIVATE/'partial_year_h30_bounds.csv'
    if status['status']!='completed_bounds_only':
        raise ValueError('Bounds or inputs changed')
    out=[]
    for item in json.loads((DATA/'manifest.json').read_text())['records']:
        path=DATA/item['file']
        x=pd.read_csv(path,compression='gzip',dtype=str)
        time=pd.to_datetime(x.timestamp,errors='raise')
        if time.dt.tz is not None:
            time=time.dt.tz_convert('Etc/GMT+7').dt.tz_localize(None)
        x['time']=time; x=x[x.time.dt.year.between(2021,2025)].copy()
        x['day']=x.time.dt.normalize()
        x['ongrid']=x.time.dt.minute.mod(15).eq(0)&x.time.dt.second.eq(0)&x.time.dt.microsecond.eq(0)
        off=set(x.loc[~x.ongrid,'day'])
        x=x[x.ongrid].copy()
        x['value']=pd.to_numeric(x.temp_degC,errors='coerce')
        if ((np.isfinite(x.value))&~x.value.between(-5,50)).any():raise ValueError('Observed value outside assumed bounds')
        # A duplicate slot is unusable even if the values agree.
        x=x[~x.time.duplicated(keep=False)]
        x=x[np.isfinite(x.value) & ~x.day.isin(off)]
        daily=x.groupby('day').value.agg(['sum','count'])
        if daily['count'].gt(96).any():raise ValueError('More than 96 unique finite on-grid slots')
        for year in range(2021,2026):
            idx=pd.date_range(f'{year}-01-01',f'{year}-12-31',freq='D')
            d=daily.reindex(idx,fill_value=0)
            lower=(d['sum']-5*(96-d['count']))/96
            upper=(d['sum']+50*(96-d['count']))/96
            low=lower.rolling(30,min_periods=30).mean().max()
            high=upper.rolling(30,min_periods=30).mean().max()
            out.append({'resource_id':item['resource_id'],'year':year,'h30_lower_c':low,'h30_upper_c':high,
                'h30_interval_width_c':high-low,'complete_days':int(d['count'].eq(96).sum()),
                'missing_or_ambiguous_slots':int((96-d['count']).sum()),'expected_days':len(idx)})
        print('Independently audited',len(out)//5,'of 10 resources',flush=True)
    actual=pd.DataFrame(out).sort_values(['resource_id','year']).reset_index(drop=True)
    expected=pd.read_csv(saved).sort_values(['resource_id','year']).reset_index(drop=True)
    if not actual[['resource_id','year']].equals(expected[['resource_id','year']]):raise AssertionError('Cohort differs')
    for col in ['h30_lower_c','h30_upper_c','h30_interval_width_c','complete_days','missing_or_ambiguous_slots','expected_days']:
        if not np.allclose(actual[col],expected[col],atol=1e-10,rtol=0):raise AssertionError('Different '+col)
    if len(actual)!=50:raise AssertionError('Unexpected denominator')
    result={'status':'passed','resources':10,'station_years_recomputed':len(actual),
        'scope':'Independent pandas duplicate filtering, daily sums and 30-day rolling bounds compared for every fixed station-year.',
        'limitations':'Agreement does not verify the assumed physical range, source QA or independent climates. No model prediction was evaluated.'}
    (OUT/'partial_year_bounds_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
