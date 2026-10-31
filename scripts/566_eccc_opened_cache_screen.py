#!/usr/bin/env python3
"""Screen previously opened ECCC daily caches as an optimistic upper bound.

The old cache counts rows/day but not unique valid hours or grades. Thus even
an apparent complete year would require fresh native-time and quality checks.
These sites were already opened and are not new independent validation.
"""
from pathlib import Path
import json
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'results/development_v11/eccc_automated_temperature/stations'
OUT=ROOT/'results/wrr_review_response_20261027/external_eccc_red'


def screening(frame):
    d=frame.copy();d['date']=pd.to_datetime(d.date,errors='coerce')
    if d.date.isna().any() or d.date.duplicated().any():raise ValueError('Prior daily cache dates invalid or duplicated')
    hours=pd.to_numeric(d.hourly_observations,errors='coerce')
    possible=d.loc[hours.ge(24)]
    result=[]
    for year,block in possible.groupby(possible.date.dt.year):
        n=366 if pd.Timestamp(int(year),12,31).is_leap_year else 365
        if block.date.nunique()==n:result.append(int(year))
    return result


def main():
    paths=sorted(OLD.glob('*/daily_temperature.csv'));rows=[]
    for path in paths:
        d=pd.read_csv(path);years=screening(d)
        rows.append(dict(site=path.parent.name,n_daily_rows=len(d),
                         first_reported_date=str(d.date.min()),last_reported_date=str(d.date.max()),
                         possible_years_at_least_24_rows=len(years),possible_years=';'.join(map(str,years))))
    f=pd.DataFrame(rows);f.to_csv(OUT/'prior_eccc_cache_upper_bound.csv',index=False)
    status={'opened_stations':len(f),'max_possible_full_years':int(f.possible_years_at_least_24_rows.max()),
            'sites_with_four_possible_years':int(f.possible_years_at_least_24_rows.ge(4).sum()),
            'scope':'previously downloaded V-labeled daily caches only, date spans differ by site; not a new candidate',
            'limitation':'at least 24 rows is an optimistic necessary condition, not proof of unique hourly timestamps, daily quality, or coverage in subsequently updated data'}
    (OUT/'prior_eccc_cache_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(f.to_string(index=False));print(json.dumps(status,indent=2))

if __name__=='__main__':main()
