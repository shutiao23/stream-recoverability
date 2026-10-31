#!/usr/bin/env python3
"""Acquire fixed same-agency WQP records for the scored DWR station."""
import argparse
from datetime import datetime,timezone
import gzip
import io
import json
from pathlib import Path
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027';URL='https://www.waterqualitydata.us/data/Result/search'

def freeze():
    dest=OUT/'wqp_same_site_plan.json'
    if dest.exists():raise FileExistsError('Preserve WQP same-site plan')
    metadata=json.loads((OUT/'wqp_site_search_status.json').read_text());distance=PRIVATE/'wqp_station_distance_audit.csv'
    if metadata['status']!='completed_metadata_only':raise ValueError('Site metadata not frozen')
    sites=pd.read_csv(distance,dtype=str);sites['distance_km']=pd.to_numeric(sites.distance_km,errors='coerce')
    close=sites[sites.distance_km.le(.25)];dwr=pd.read_csv(OUT/'station_metadata_03.csv',dtype=str).set_index('Station_Code')
    selected=str(dwr.loc['TRB8','WDL_Station_Code']);same=close[close.MonitoringLocationIdentifier.str.endswith('-'+selected,na=False)]
    if len(close)!=1 or len(same)!=1 or same.iloc[0].OrganizationIdentifier!='CALWR_WQX':raise ValueError('Reassess metadata candidate selection')
    years=sorted(pd.read_csv(PRIVATE/'exploratory_roster.csv').year.astype(int).unique().tolist())
    if years!=[2011,2013,2014,2020]:raise ValueError('Prior exploratory years changed')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'posthoc after target model scores and WQP station metadata were seen, before retrieving WQP water-temperature results',
          'selection':'The only WQP water-temperature site within 0.25 km, whose station identifier matches the DWR water-data-library code of the scored TRB8 station.',
          'wqp_site_id':same.iloc[0].MonitoringLocationIdentifier,'organization':same.iloc[0].OrganizationIdentifier,'years':years,
          'request':'All WQP result records for Temperature, water in each of the four already-scored calendar years; retain source metadata, timestamps, units, value type and quality/status fields.',
          'intended_use':'First describe provenance, time-zone and measurement fields and whether records may be same-source duplicates. Any numeric comparisons require a subsequent recorded plan; do not label the data an independent sensor or climate.',
          'limits':'Both datasets are DWR records for the same WDL station. A different portal does not prove another instrument, independent measurement or independent QA. WQP historical profile may lack subsequent revisions and source-specific reuse terms require review.',
          }
    dest.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded same-agency WQP acquisition plan')

def fetch():
    plan=json.loads((OUT/'wqp_same_site_plan.json').read_text());dest=OUT/'wqp_same_site_acquisition.json'
    if dest.exists():raise FileExistsError('Preserve prior acquisition')
    folder=PRIVATE/'wqp_same_site';folder.mkdir(parents=True,exist_ok=True,mode=0o700);results=[]
    for year in plan['years']:
        params={'siteid':plan['wqp_site_id'],'characteristicName':'Temperature, water','startDateLo':f'01-01-{year}',
                'startDateHi':f'12-31-{year}','mimeType':'csv','zip':'no','sorted':'no'}
        item={'year':year,'status':'unknown'}
        try:
            response=requests.get(URL,params=params,timeout=50,headers={'User-Agent':'stream-temperature reference provenance research/1.0'})
            item.update(http_status=response.status_code,response_bytes=len(response.content))
            if response.status_code==204:item.update(status='completed_empty',rows=0)
            elif response.status_code==200:
                frame=pd.read_csv(io.BytesIO(response.content),dtype=str)
                required={'MonitoringLocationIdentifier','ActivityStartDate','CharacteristicName'}
                if not required.issubset(frame.columns) or not frame.MonitoringLocationIdentifier.eq(plan['wqp_site_id']).all() or not frame.CharacteristicName.eq('Temperature, water').all():raise ValueError('Unexpected WQP result identity or schema')
                path=folder/f'{year}.csv.gz'
                if path.exists():raise FileExistsError('Preserve WQP response')
                with gzip.open(path,'wb',compresslevel=5) as f:f.write(response.content)
                path.chmod(0o600);item.update(status='completed',rows=len(frame),columns=list(frame.columns))
        except (requests.RequestException,ValueError,KeyError,pd.errors.ParserError,OSError) as e:item['error_type']=type(e).__name__
        results.append(item);print('WQP year',year,item['status'],flush=True)
    receipt=folder/'acquisition.json';receipt.write_text(json.dumps(results,indent=2)+'\n');receipt.chmod(0o600)
    ok=sum(x['status'] in ('completed','completed_empty') for x in results)
    result={'status':'completed' if ok==len(results) else 'partial_unknown','years_requested':len(plan['years']),'years_completed':ok,
            'result_rows':sum(x.get('rows',0) for x in results),'numerical_comparison_performed':False,'independent_instrument_verified':False,'limitations':plan['limits']}
    dest.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','fetch']);a=p.parse_args();freeze() if a.action=='freeze' else fetch()
