#!/usr/bin/env python3
"""Compare selected saved air series with current NASA POWER responses.

This is an after-results provenance sensitivity, not proof of historical API
version, data quality or water-clock alignment. Provider requests are limited
to two workers and failures remain explicitly unavailable.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import time
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/beaufort_proxy'
PRIVATE=ROOT/'private/wrr_beaufort_proxy_20261027';PLAN=OUT/'power_vintage_plan.json';RAW=PRIVATE/'power_vintage_raw'
ENDPOINT='https://power.larc.nasa.gov/api/temporal/daily/point'

def request_one(item):
    path=RAW/f"request_{int(item['request_index']):02d}.json";receipt=path.with_suffix('.receipt.json')
    if path.exists():
        if not receipt.is_file():raise ValueError('Existing NASA response lacks matching receipt')
    else:
        if receipt.exists():raise ValueError('Existing NASA receipt has no response')
        params={'parameters':'T2M','community':'AG','longitude':item['longitude'],'latitude':item['latitude'],
                'start':'20090101','end':'20171231','time-standard':'LST','format':'JSON'}
        response=None
        for attempt in range(3):
            try:response=requests.get(ENDPOINT,params=params,timeout=(20,55),headers={'User-Agent':'stream-temperature-research/1.0'})
            except requests.RequestException as exc:
                if attempt==2:return {'request_index':item['request_index'],'status':'unavailable','reason':type(exc).__name__}
                time.sleep(2*(attempt+1));continue
            if response.status_code not in (429,500,502,503,504):break
            if attempt<2:time.sleep(3*(attempt+1))
        if response is None:return {'request_index':item['request_index'],'status':'unavailable','reason':'no_response'}
        if response.status_code!=200:return {'request_index':item['request_index'],'status':'unavailable','reason':'HTTP '+str(response.status_code)}
        if len(response.content)>5_000_000:raise ValueError('NASA response exceeds fixed limit')
        payload=response.json()
        if not isinstance(payload.get('properties',{}).get('parameter',{}).get('T2M'),dict):raise ValueError('NASA response has no T2M values')
        partial=path.with_suffix('.json.part')
        if partial.exists():raise ValueError('Partial NASA response is preserved for review')
        with partial.open('xb') as f:
            os.chmod(partial,0o600);f.write(response.content)
        partial.rename(path)
        receipt.write_text(json.dumps({'request_parameters':params,
                                       'retrieved_utc':datetime.now(timezone.utc).isoformat()},indent=2)+'\n');receipt.chmod(0o600)
    payload=json.loads(path.read_text());values=payload.get('properties',{}).get('parameter',{}).get('T2M',{})
    return {'request_index':item['request_index'],'status':'available','values':values,
            'header':payload.get('header',{}),}

def main():
    plan=json.loads(PLAN.read_text());roster_path=PRIVATE/'power_vintage_roster.json'
    roster=json.loads(roster_path.read_text());RAW.mkdir(parents=True,exist_ok=True,mode=0o700)
    snapshot=pd.read_parquet(OUT/'air_snapshot.parquet');snapshot['date']=pd.to_datetime(snapshot.date)
    records=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(request_one,item):item for item in roster}
        for future in as_completed(futures):
            item=futures[future];result=future.result()
            row={'request_index':item['request_index'],'station_key':item['station_key'],'provider':item['provider'],
                 'status':result['status'],'reason':result.get('reason')}
            if result['status']=='available':
                cached=snapshot[snapshot.station_key.eq(item['station_key'])].sort_values('date')
                current=pd.Series(result['values'],dtype='object');current.index=pd.to_datetime(current.index,format='%Y%m%d',errors='coerce')
                if current.index.isna().any() or current.index.duplicated().any():raise ValueError('NASA date labels invalid')
                now=pd.to_numeric(current.reindex(cached.date),errors='coerce').to_numpy(float);now[now<=-998]=np.nan
                old=cached.air_temperature_c.to_numpy(float);valid=np.isfinite(now)&np.isfinite(old);difference=np.abs(now[valid]-old[valid])
                row.update(expected_days=len(cached),both_finite_days=int(valid.sum()),
                           matching_days_at_1e_5_c=int((difference<=1e-5).sum()),
                           mean_absolute_difference_c=float(difference.mean()) if len(difference) else None,
                           maximum_absolute_difference_c=float(difference.max()) if len(difference) else None,
                           response_header=result['header'])
            records.append(row)
            print('NASA provenance requests completed:',len(records),'of',len(roster),flush=True)
    records.sort(key=lambda x:x['request_index']);(PRIVATE/'power_vintage_records.json').write_text(json.dumps(records,indent=2)+'\n')
    (PRIVATE/'power_vintage_records.json').chmod(0o600)
    results=pd.DataFrame([{k:v for k,v in r.items() if k not in ('station_key','response_header','request_index')} for r in records])
    summaries=[]
    for label,g in [('all',results),*list(results.groupby('provider',sort=True))]:
        ok=g[g.status.eq('available')]
        summaries.append({'provider':label,'requested':len(g),'responses_available':len(ok),
                          'expected_days':int(ok.expected_days.sum()) if len(ok) else 0,
                          'both_finite_days':int(ok.both_finite_days.sum()) if len(ok) else 0,
                          'matching_days_at_1e_5_c':int(ok.matching_days_at_1e_5_c.sum()) if len(ok) else 0,
                          'maximum_absolute_difference_c':float(ok.maximum_absolute_difference_c.max()) if len(ok) else None})
    pd.DataFrame(summaries).to_csv(OUT/'power_vintage_summary.csv',index=False)
    state={'status':'completed' if results.status.eq('available').all() else 'partial_provider_responses',
           'requests_planned':len(roster),'responses_available':int(results.status.eq('available').sum()),
           'reasons_unavailable':results.loc[results.status.ne('available'),'reason'].value_counts().to_dict(),
           'scope':'One representative per exact stored air-series group, requested after the prior model results were inspected.',
           'limitations':plan['limitations']}
    (OUT/'power_vintage_status.json').write_text(json.dumps(state,indent=2)+'\n')
    print(pd.DataFrame(summaries).to_string(index=False));print(json.dumps(state,indent=2))

if __name__=='__main__':main()
