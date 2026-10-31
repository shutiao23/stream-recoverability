#!/usr/bin/env python3
"""Curate the required NASA POWER-based air input from the saved project table.

This is a processed-input snapshot, not a fresh provider download or proof of
alignment with water-temperature clock conventions.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/beaufort_proxy'
SOURCE=ROOT/'data/interim/tr_air_forcing.parquet'

def main():
    plan=json.loads((OUT/'plan.json').read_text())
    roster=pd.read_csv(OUT/'roster.csv',dtype={'station_id':str,'network_id':str})
    source=pd.read_parquet(SOURCE,columns=['station_id','network_id','date','air_temperature_c'])
    source['station_id']=source.station_id.astype(str);source['network_id']=source.network_id.astype(str)
    f=source.merge(roster[['station_key','station_id','network_id']],on=['station_id','network_id'],how='inner',validate='many_to_one')
    f['date']=pd.to_datetime(f.date)
    f=f[f.date.dt.year.between(2009,2017)&(((f.date.dt.month==6)&f.date.dt.day.ge(22))|f.date.dt.month.isin([7,8]))].copy()
    if f.duplicated(['station_key','date']).any():raise ValueError('Duplicate air station-date')
    dates=pd.DatetimeIndex([d for year in range(2009,2018) for d in pd.date_range(f'{year}-06-22',f'{year}-08-31')])
    rows=[];available=[]
    for item in roster.itertuples(index=False):
        values=f[f.station_key.eq(item.station_key)].set_index('date').air_temperature_c.reindex(dates)
        rows.append(pd.DataFrame({'station_key':item.station_key,'date':dates,'air_temperature_c':values.to_numpy(float)}))
        available.append({'station_key':item.station_key,'expected_days':len(dates),'finite_days':int(np.isfinite(values).sum()),
                          'complete_for_lags':bool(np.isfinite(values).all())})
    snapshot=pd.concat(rows,ignore_index=True);status=pd.DataFrame(available)
    path=OUT/'air_snapshot.parquet'
    if path.exists():pd.testing.assert_frame_equal(pd.read_parquet(path),snapshot,check_dtype=False)
    else:snapshot.to_parquet(path,index=False)
    status.to_csv(OUT/'air_availability.csv',index=False)
    attribution=('Air temperatures are extracted from the project\'s processed daily T2M table, documented as NASA POWER.\n'
                 'NASA POWER project: https://power.larc.nasa.gov/ ; acknowledge NASA Langley Research Center POWER.\n'
                 'The original API response and version for these 22 stations were not retained; this is not a raw provider snapshot.\n'
                 'POWER daily air defaults to local solar time; water-day alignment is not established.\n')
    (OUT/'AIR_ATTRIBUTION.txt').write_text(attribution)
    report={'status':'processed_air_snapshot_created','stations':len(roster),'expected_station_days':len(snapshot),
            'stations_complete_for_all_lags':int(status.complete_for_lags.sum()),
            'stations_with_missing_air':int((~status.complete_for_lags).sum()),
            'limitations':'Previously assembled processed NASA POWER-based table; raw API responses, service version and water-day alignment are not established for this cohort.'}
    (OUT/'air_snapshot_status.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
