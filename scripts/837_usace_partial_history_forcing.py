#!/usr/bin/env python3
"""Acquire public NASA POWER forcing for the fixed partial-history cohort."""
from datetime import datetime,timezone
import gzip
import json
from pathlib import Path
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir'
PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027';DATA=ROOT/'data/external/wrr_usace_reservoir_20261027/partial_history_power'
URL='https://power.larc.nasa.gov/api/temporal/daily/point'

def main():
    plan=json.loads((OUT/'partial_history_evaluation_plan.json').read_text());roster=PRIVATE/'partial_history_roster.csv'
    statuspath=OUT/'partial_history_forcing_status.json'
    if statuspath.exists():raise FileExistsError('Preserve acquired weather status')
    sites=pd.read_csv(roster).drop_duplicates('resource_id');DATA.mkdir(parents=True,exist_ok=True)
    records=[];frames=[]
    for row in sites.itertuples(index=False):
        params={'parameters':'T2M','community':'RE','latitude':round(row.latitude,2),'longitude':round(row.longitude,2),
                'start':'20210101','end':'20251231','format':'JSON','time-standard':'LST'}
        entry={'resource_id':row.resource_id,'parameters':params,'status':'unknown'}
        try:
            r=requests.get(URL,params=params,timeout=50,headers={'User-Agent':'stream-temperature partial-history research/1.0'});entry['http_status']=r.status_code;r.raise_for_status()
            response=r.json();values=response['properties']['parameter']['T2M'];idx=pd.date_range('2021-01-01','2025-12-31')
            series=pd.to_numeric(pd.Series([values.get(t.strftime('%Y%m%d'),np.nan) for t in idx]),errors='coerce');series=series.where(series.gt(-990))
            raw=DATA/(row.resource_id+'.json.gz')
            with gzip.open(raw,'wb') as f:f.write(r.content)
            frame=pd.DataFrame({'date':idx,'air_temperature_c':series,'station_id':row.resource_id,'network_id':'usace_'+row.resource_id})
            frames.append(frame);entry.update(status='completed',days=len(idx),finite_days=int(np.isfinite(series).sum()),file=raw.name,)
        except (requests.RequestException,ValueError,KeyError,TypeError) as e:entry['error_type']=type(e).__name__
        records.append(entry);print('NASA POWER request',len(records),'of',len(sites),entry['status'],flush=True)
    if frames:
        path=DATA/'daily_air.parquet';pd.concat(frames,ignore_index=True).to_parquet(path,index=False)
    manifest={'source':'NASA POWER daily API','endpoint':URL,'retrieved_utc':datetime.now(timezone.utc).isoformat(),
      'attribution':'NASA POWER Project, NASA Langley Research Center; NASA requests notification upon redistribution; none sent for this local candidate.',
      'records':records,'daily_file':'daily_air.parquet' if frames else None,}
    (DATA/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (DATA/'ATTRIBUTION.txt').write_text(manifest['attribution']+'\n'+URL+'\nLocal solar time may differ from the fixed-MST water day.\n')
    status={'status':'completed' if len(frames)==len(sites) else 'partial_unknown','resources_requested':len(sites),
      'resources_returned':len(frames),'finite_days':sum(x.get('finite_days',0) for x in records),
      'limitations':'Daily gridded air, not direct station measurement. LST versus fixed MST and actual sensor clock remain unresolved.'}
    statuspath.write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))

if __name__=='__main__':main()
