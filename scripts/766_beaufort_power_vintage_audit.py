#!/usr/bin/env python3
"""Independently recount current-provider versus cached air differences."""
import json
import math
from collections import Counter
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/beaufort_proxy'
PRIVATE=ROOT/'private/wrr_beaufort_proxy_20261027';RAW=PRIVATE/'power_vintage_raw'

def main():
    plan=json.loads((OUT/'power_vintage_plan.json').read_text());roster=json.loads((PRIVATE/'power_vintage_roster.json').read_text())
    saved=json.loads((PRIVATE/'power_vintage_records.json').read_text());lookup={x['request_index']:x for x in saved}
    if len(roster)!=len(saved) or len(lookup)!=len(saved):raise ValueError('Request identities differ')
    source=pd.read_parquet(OUT/'air_snapshot.parquet');source['date']=pd.to_datetime(source.date)
    rows=[];versions=Counter();invalid_headers=0
    for item in roster:
        i=item['request_index'];record=lookup[i]
        if record['status']!='available':
            rows.append({'provider':item['provider'],'available':False});continue
        path=RAW/f'request_{i:02d}.json';receipt=json.loads(path.with_suffix('.receipt.json').read_text())
        params=receipt['request_parameters']
        if params['parameters']!='T2M' or params['community']!='AG' or params['time-standard']!='LST' or params['start']!='20090101' or params['end']!='20171231' or float(params['latitude'])!=float(item['latitude']) or float(params['longitude'])!=float(item['longitude']):
            raise ValueError('NASA request parameters differ')
        payload=json.loads(path.read_text());header=payload.get('header',{});metadata=payload.get('parameters',{}).get('T2M',{})
        if header.get('time_standard')!='LST' or metadata.get('units')!='C':invalid_headers+=1
        versions[str(header.get('api',{}).get('version','unknown'))]+=1
        values=payload['properties']['parameter']['T2M'];table=source[source.station_key.eq(item['station_key'])].sort_values('date')
        if len(table)!=639:raise ValueError('Cached air denominator differs')
        differences=[]
        for entry in table.itertuples(index=False):
            raw=values.get(entry.date.strftime('%Y%m%d'))
            try:current=float(raw)
            except (TypeError,ValueError):continue
            if not math.isfinite(current) or current<=-998 or not math.isfinite(float(entry.air_temperature_c)):continue
            differences.append(abs(current-float(entry.air_temperature_c)))
        if len(differences)!=record['both_finite_days'] or sum(v<=1e-5 for v in differences)!=record['matching_days_at_1e_5_c']:
            raise ValueError('NASA comparison counts differ')
        if differences and not math.isclose(max(differences),record['maximum_absolute_difference_c'],rel_tol=0,abs_tol=1e-12):
            raise ValueError('NASA maximum difference differs')
        rows.append({'provider':item['provider'],'available':True,'expected':len(table),'matched':len(differences),
                     'within':sum(v<=1e-5 for v in differences),'maximum':max(differences) if differences else None})
    if invalid_headers:raise ValueError('Current NASA response time standard or units differ')
    observed=pd.read_csv(OUT/'power_vintage_summary.csv');checks=0
    for provider in ['all',*sorted(set(x['provider'] for x in rows))]:
        g=rows if provider=='all' else [x for x in rows if x['provider']==provider];available=[x for x in g if x['available']]
        match=observed[observed.provider.eq(provider)]
        if len(match)!=1:raise ValueError('NASA summary identity missing')
        row=match.iloc[0]
        for key,val in [('requested',len(g)),('responses_available',len(available)),('expected_days',sum(x['expected'] for x in available)),
                        ('both_finite_days',sum(x['matched'] for x in available)),('matching_days_at_1e_5_c',sum(x['within'] for x in available))]:
            if int(row[key])!=int(val):raise ValueError('NASA summary count differs: '+key)
        maxima=[x['maximum'] for x in available if x['maximum'] is not None]
        if maxima and not math.isclose(float(row.maximum_absolute_difference_c),max(maxima),rel_tol=0,abs_tol=1e-12):
            raise ValueError('NASA summary maximum differs')
        checks+=1
    report={'status':'passed','representative_requests_checked':len(rows),'available_responses_checked':sum(x['available'] for x in rows),
            'aggregate_rows_checked':checks,'current_api_versions':dict(versions),'current_response_time_standard':'LST','current_response_units':'C',
            'scope':'Recounts current-provider response versus saved processed-air values, using the same selected representative stations. Does not verify historical response version, omitted stations, physical air accuracy or water-clock alignment.'}
    (OUT/'power_vintage_independent_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
