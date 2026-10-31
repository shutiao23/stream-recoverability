#!/usr/bin/env python3
"""Verify open source-year and forcing inputs for partial-history experiment."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'source_partial_history_factorial';OPEN=REV/'open_observed_record_snapshot'

def main():
    plan=json.loads((OUT/'plan.json').read_text())
    paths=[OPEN/'daily_temperature.parquet',OPEN/'station_years.parquet',OUT/'roster.csv',OUT/'air_snapshot.parquet',OUT/'air_availability.csv']
    roster=pd.read_csv(OUT/'roster.csv',dtype={'station_id':str});water=pd.read_parquet(OPEN/'daily_temperature.parquet');water['date']=pd.to_datetime(water.date)
    annual=pd.read_parquet(OPEN/'station_years.parquet');air=pd.read_parquet(OUT/'air_snapshot.parquet');air['date']=pd.to_datetime(air.date);availability=pd.read_csv(OUT/'air_availability.csv').set_index('station_key')
    counts=0
    for r in roster.itertuples(index=False):
        w=water[water.station_key.eq(r.station_key)].set_index('date').water_c
        if w.index.has_duplicates:raise ValueError('Duplicate water date')
        for year in range(2009,2018):
            idx=pd.date_range(f'{year}-01-01',f'{year}-12-31');s=w.reindex(idx)
            if len(s)!=len(idx) or not np.isfinite(s).all():raise ValueError('Water year is incomplete')
            counts+=1
            if year==2017:
                h=float(np.max(np.convolve(s.to_numpy(float),np.ones(30)/30,mode='valid')))
                y=annual[(annual.station_key==r.station_key)&annual.year.eq(year)]
                if len(y)!=1 or not bool(y.complete_year.iloc[0]) or not np.isclose(h,y.truth_h30.iloc[0],atol=1e-5,rtol=0):raise ValueError('Saved target H30 differs')
        a=air[(air.station_id.astype(str)==r.station_id)&air.network_id.eq(r.network_id)]
        idx=pd.date_range('2009-01-01','2017-12-31')
        if len(a)!=len(idx) or a.date.duplicated().any() or set(a.date)!=set(idx) or int(np.isfinite(a.air_temperature_c).sum())!=int(availability.loc[r.station_key,'finite_air_days']):raise ValueError('Air availability differs')
    result={'status':'passed','stations':len(roster),'complete_station_years':counts,'target_h30_values_checked':len(roster),
      'air_rows':len(air),'finite_air_values':int(np.isfinite(air.air_temperature_c).sum()),
      'scope':'Open processed water-year eligibility and complete-target H30, plus the selected saved air input snapshot.',
      'limitations':'The air table is a processed historical snapshot, not a raw source-service replay; no model is fitted or scored, and source quality, physical clock, climate independence and restricted-model rights remain unresolved.'}
    p=REV/'audit/source_partial_history_open_reference_replay.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
