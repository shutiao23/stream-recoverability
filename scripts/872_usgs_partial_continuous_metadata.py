#!/usr/bin/env python3
"""Inspect USGS instantaneous series metadata for all daily-qualified sites."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import pandas as pd
import requests
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_usgs_partial_daily';USGS=ROOT/'results/additional_usgs_observed';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027'
URL='https://api.waterdata.usgs.gov/ogcapi/v0/collections/time-series-metadata/items'

def freeze():
    h=T.load_script('usgs_partial_metadata_hash',ROOT/'scripts/871_usgs_partial_daily_feasibility.py');path=OUT/'continuous_metadata_plan.json'
    if path.exists():raise FileExistsError('Preserve metadata plan')
    s=json.loads((OUT/'feasibility_status.json').read_text());roster=PRIVATE/'daily_target_roster.csv'
    if s['status']!='completed_feasibility_only':raise ValueError('Daily feasibility not verified')
    target=pd.read_csv(roster,dtype={'station_id':str});ids=sorted(target.loc[target.eligible_partial_history,'station_id'].unique())
    candidates=PRIVATE/'continuous_candidate_ids.json';candidates.write_text(json.dumps(ids,indent=2)+'\n');candidates.chmod(0o600)
    p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc metadata check after daily reference values, observation witnesses and history feasibility were examined; before continuous water values or model errors',
      'cohort':'All sites with at least one fully qualified daily target and three eligible historical years; retain all candidates regardless of continuous metadata.',
      'request':'Public water-temperature time-series metadata for these sites, identifying instantaneous time-series IDs and comparing with the original daily series parent IDs. No instantaneous water readings requested.',
      'interpretation':'Metadata time envelopes do not demonstrate year completeness, quality, instrument equivalence, clock convention or independent climate. A missing parent or multiple series is unknown and is not resolved by selecting temperatures.',
      'site_count':len(ids),'endpoint':URL}
    path.write_text(json.dumps(p,indent=2)+'\n');print('Frozen continuous-series metadata request')

def run():
    h=T.load_script('usgs_partial_metadata_hash2',ROOT/'scripts/871_usgs_partial_daily_feasibility.py');p=json.loads((OUT/'continuous_metadata_plan.json').read_text())
    ids=json.loads((PRIVATE/'continuous_candidate_ids.json').read_text());data=pd.read_csv(USGS/'cohort_metadata.csv',dtype={'station_id':str,'parent_time_series_id':str}).set_index('station_id')
    result={'status':'unknown','sites_requested':len(ids),'temperature_values_requested':False,'limitations':p['interpretation']}
    try:
        params={'f':'json','monitoring_location_id':','.join('USGS-'+x for x in ids),'parameter_code':'00010','limit':1000}
        r=requests.get(URL,params=params,timeout=35,headers={'User-Agent':'stream-temperature reference qualification/1.0'});result['http_status']=r.status_code
        if r.status_code==200:
            doc=r.json()
            if not isinstance(doc.get('features'),list) or any(x.get('rel')=='next' for x in doc.get('links',[])):raise ValueError('Unexpected paginated metadata')
            rows=[]
            for item in doc['features']:
                x=item['properties'];site=str(x.get('monitoring_location_id','')).removeprefix('USGS-')
                if site not in ids or str(x.get('parameter_code'))!='00010':raise ValueError('Unexpected series metadata')
                if x.get('computation_identifier')!='Instantaneous':continue
                ident=str(x.get('id') or item['id']);parent=data.loc[site,'parent_time_series_id']
                rows.append({'station_id':site,'series_id':ident,'begin':x.get('begin_utc') or x.get('begin'),'end':x.get('end_utc') or x.get('end'),
                  'primary':x.get('primary'),'statistic_id':x.get('statistic_id'),'daily_parent_match':bool(pd.notna(parent) and ident==str(parent))})
            raw=PRIVATE/'continuous_metadata.json';raw.write_bytes(r.content);raw.chmod(0o600)
            table=pd.DataFrame(rows,columns=['station_id','series_id','begin','end','primary','statistic_id','daily_parent_match']);f=PRIVATE/'continuous_metadata.csv';table.to_csv(f,index=False);f.chmod(0o600)
            result.update(status='completed_metadata_only',instantaneous_series=len(table),sites_with_instantaneous_series=int(table.station_id.nunique()),
               sites_with_exact_daily_parent=int(table.loc[table.daily_parent_match,'station_id'].nunique()),)
    except (requests.RequestException,ValueError,KeyError,TypeError) as e:result['error_type']=type(e).__name__
    (OUT/'continuous_metadata_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
