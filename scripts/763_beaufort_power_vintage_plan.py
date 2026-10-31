#!/usr/bin/env python3
"""Record an after-results check against current NASA POWER API responses."""
from __future__ import annotations
from datetime import datetime,timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/beaufort_proxy'
PRIVATE=ROOT/'private/wrr_beaufort_proxy_20261027';COORD=ROOT/'data/interim/v18_station_coordinates.csv'

def main():
    path=OUT/'power_vintage_plan.json'
    if path.exists():raise FileExistsError('Preserve existing NASA provenance-check plan')
    if json.loads((OUT/'independent_audit.json').read_text())['status']!='passed':raise ValueError('Finish original proxy audit first')
    roster=pd.read_csv(OUT/'roster.csv',dtype={'station_id':str,'network_id':str})
    coords=pd.read_csv(COORD,dtype={'station_id':str,'network_id':str})
    merged=roster.merge(coords[['station_id','network_id','latitude','longitude']],on=['station_id','network_id'],how='left',validate='one_to_one')
    if len(merged)!=22 or merged[['latitude','longitude']].isna().any().any():raise ValueError('Missing source-station coordinates')
    air=pd.read_parquet(OUT/'air_snapshot.parquet');air['date']=pd.to_datetime(air.date)
    fingerprints={}
    for item in merged.sort_values('station_key').itertuples(index=False):
        g=air[air.station_key.eq(item.station_key)].sort_values('date')
        if len(g)!=639 or g.date.duplicated().any() or not np.isfinite(g.air_temperature_c.to_numpy(float)).all():
            raise ValueError('Stored air series is incomplete')
        fingerprints.setdefault(tuple(np.round(g.air_temperature_c.to_numpy(float), 6)), []).append(item)
    records=[]
    for index,(_,items) in enumerate(sorted(fingerprints.items(),key=lambda kv:kv[1][0].station_key)):
        rep=items[0]
        records.append({'request_index':index,'station_key':rep.station_key,'provider':rep.provider,
                        'latitude':float(rep.latitude),'longitude':float(rep.longitude),
                        'cached_series_group_members':[x.station_key for x in items]})
    if len(records)!=15:raise ValueError('Unexpected count of distinct saved air series')
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);private=PRIVATE/'power_vintage_roster.json'
    if private.exists():raise FileExistsError('Preserve existing NASA request roster')
    private.write_text(json.dumps(records,indent=2)+'\n');private.chmod(0o600)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'posthoc after proxy model results and historical processed air were inspected',
          'selection':'Choose one lexicographically first station for each byte-identical saved 639-day air series; this reduces redundant provider requests, but does not prove that other stations share current provider values.',
          'stations_in_prior_proxy':22,'distinct_saved_series':15,'representative_requests':15,
          'request':'NASA POWER daily point API, T2M, community AG, 2009-01-01 through 2017-12-31, explicit local solar time; at most two concurrent requests.',
          'comparison':'For each representative compare the previously saved 639 June22–August31 values with the current response on identical dates; report availability and differences, with 1e-5 C rounding tolerance.',
          'prior_exposure':'Prior thermal-peak target values, fitted-model results and stored air series were already inspected. Current NASA responses were not read before this plan.',
          'limitations':'Current API data may have revised vintages or processing relative to the historical cached values. A match does not establish original service version, all other stations, weather accuracy, water-day alignment, sensor quality or independent climate. Missing or failed requests remain unavailable.',
          'storage':'Coordinates, raw API responses and station-level comparisons remain local private; aggregate provider counts only.',
          }
    path.write_text(json.dumps(plan,indent=2)+'\n')
    print('Recorded post-hoc NASA POWER provenance check for 15 representative series.')

if __name__=='__main__':main()
