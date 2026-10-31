#!/usr/bin/env python3
"""Check nearby USGS water-temperature series metadata, without values."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027';URL='https://api.waterdata.usgs.gov/ogcapi/v0/collections/time-series-metadata/items'

def freeze():
    dest=OUT/'usgs_partner_metadata_plan.json'
    if dest.exists():raise FileExistsError('Preserve partner metadata plan')
    finite=json.loads((OUT/'finite_reference_status.json').read_text());audit=json.loads((OUT/'finite_reference_independent_audit.json').read_text())
    if finite['status']!='finite_level1_reference_screened' or audit['status']!='passed':raise ValueError('Reference qualification not verified')
    roster=PRIVATE/'roster.csv';network=json.loads((OUT/'network_status.json').read_text());gage=PRIVATE/'nldi_metadata/gage_summary.csv'
    f=pd.read_csv(roster,dtype={'resource_id':str,'gage_ids':str});f=f[f.metadata_candidate]
    ids=sorted({s for x in f.gage_ids for s in x.split(';') if s});dest_ids=PRIVATE/'usgs_partner_ids.json';dest_ids.write_text(json.dumps(ids,indent=2)+'\n');dest_ids.chmod(0o600)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
        'status':'posthoc after viewing timestamp and finite-reference availability, before requesting partner time-series metadata or partner water values',
        'cohort':'All 11 USGS gages referenced in the 10 previously selected resource metadata entries; no selection by temperature or model error.',
        'request':'Current public USGS time-series metadata for water-temperature parameter 00010, with any statistic. No daily or subdaily water observations are requested.',
        'goal':'Identify possible separately maintained temperature series for evaluating source-data agreement and whether natural gaps might have a backup. Metadata envelopes and physical proximity do not establish shared water, sensor independence or adequate quality.',
        'limitations':'USACE sensors may be offset from the named USGS gage; some gages have known prior network links. Missing or absent series metadata is unknown, not proof that no measurement exists. No independent climate or annual reference is established.',
        'gage_count':len(ids),'endpoint':URL}
    dest.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded partner-series metadata plan for',len(ids),'USGS gages')

def fetch():
    plan=json.loads((OUT/'usgs_partner_metadata_plan.json').read_text())
    ids=json.loads((PRIVATE/'usgs_partner_ids.json').read_text());status={'status':'unknown','gages_requested':len(ids),'temperature_values_requested':False,'prediction_errors_opened':False,'limitations':plan['limitations']}
    try:
        params={'f':'json','monitoring_location_id':','.join('USGS-'+x for x in ids),'parameter_code':'00010','limit':1000}
        r=requests.get(URL,params=params,timeout=35,headers={'User-Agent':'stream-temperature reference qualification/1.0'});status['http_status']=r.status_code
        if r.status_code==200:
            d=r.json()
            if not isinstance(d.get('features'),list) or any(x.get('rel')=='next' for x in d.get('links',[])):raise ValueError('Missing or paginated series metadata')
            rows=[]
            for item in d['features']:
                x=item['properties'];site=str(x.get('monitoring_location_id','')).removeprefix('USGS-')
                if site not in ids or str(x.get('parameter_code'))!='00010':raise ValueError('Unexpected site or parameter')
                rows.append({'site':site,'series_id':str(x.get('id') or item['id']),'statistic_id':str(x.get('statistic_id') or ''),
                             'begin':x.get('begin'),'end':x.get('end'),'primary':x.get('primary'),'unit':x.get('unit_of_measure')})
            raw=PRIVATE/'usgs_partner_metadata.json';raw.write_bytes(r.content);raw.chmod(0o600)
            cols=['site','series_id','statistic_id','begin','end','primary','unit'];frame=pd.DataFrame(rows,columns=cols);path=PRIVATE/'usgs_partner_series.csv';frame.to_csv(path,index=False);path.chmod(0o600)
            status.update(status='completed_metadata_only',series_records=len(frame),gages_with_any_temperature_series=int(frame.site.nunique()),
                gages_with_daily_mean=int(frame.loc[frame.statistic_id.eq('00003'),'site'].nunique()),
                gages_with_other_or_unspecified_statistic=int(frame.loc[~frame.statistic_id.eq('00003'),'site'].nunique()),
                null_begin_records=int(frame.begin.isna().sum()),null_end_records=int(frame.end.isna().sum()),
                )
    except (requests.RequestException,ValueError,KeyError,TypeError) as e:status['error_type']=type(e).__name__
    (OUT/'usgs_partner_metadata_status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','fetch']);a=p.parse_args();freeze() if a.action=='freeze' else fetch()
