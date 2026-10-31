#!/usr/bin/env python3
"""Post-hoc one-station annual counts; no temperature observations requested."""
from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_njdep_metadata'
ENDPOINT='https://njdep.rutgers.edu/continuous/api/latest/count/'


def get_count(session,station,start='',end=''):
    payload={'station':station,'startDate':start,'endDate':end,'affiliation':'','project':'','watertype':'','stationType':'','county':'','municipality':'','huc14':''}
    try:
        r=session.post(ENDPOINT,data=payload,timeout=25)
        if r.status_code!=200:return {'status':'http_error','http_status':r.status_code,'count':None}
        data=r.json(); raw=data.get('payload',{}).get('count')
        if data.get('status')!='OK' or raw is None:return {'status':'invalid_response','http_status':r.status_code,'count':None}
        value=int(raw)
        if value<0:raise ValueError('negative provider count')
        return {'status':'returned','http_status':r.status_code,'count':value}
    except (requests.RequestException,ValueError,TypeError) as e:return {'status':'request_or_parse_error','error_type':type(e).__name__,'count':None}


def main():
    plan=json.loads((OUT/'count_probe_extension_plan.json').read_text())
    if plan['status']!='posthoc_single_station_all_year_counts' or plan['station_id']!='01399820':raise ValueError('count-only plan not frozen')
    target=OUT/'count_probe_status.json'
    if target.exists():raise RuntimeError('existing probe status preserved')
    station=plan['station_id'];session=requests.Session();control=get_count(session,station)
    rows=[]
    for year in plan['years']:
        row={'year':year}|get_count(session,station,f'01/01/{year}',f'12/31/{year}')
        rows.append(row);print(year,row['status'],row['count'],flush=True)
    status={'status':'count_probe_completed','completed_utc':datetime.now(timezone.utc).isoformat(),'station_id':station,'control_all_dates':control,'year_counts':rows,
      'no_water_temperature_values_requested':True,'no_model_predictions_scored':True,
      'interpretation':'provider count endpoint; counts can aggregate parameters or records with missing/estimated measurements; no unique timestamps or water-specific completeness established',
      'limitation':'post-hoc single-site probe; zero or error may reflect endpoint filtering, access, data absence or date conventions; not a reference-quality conclusion'}
    target.write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))
if __name__=='__main__':main()
