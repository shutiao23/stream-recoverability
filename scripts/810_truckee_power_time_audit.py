#!/usr/bin/env python3
"""Independently recompute the Truckee NASA POWER time-standard comparison."""
from datetime import datetime,timedelta
import gzip
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027';CACHE=PRIVATE/'power_time_standards'

def main():
    plan=json.loads((OUT/'power_time_standards_plan.json').read_text());status=json.loads((OUT/'power_time_comparison.json').read_text())
    acquisition=json.loads((OUT/'power_time_acquisition.json').read_text());receipt=CACHE/'acquisition.json'
    if status['status']!='computed_posthoc' or acquisition['status']!='completed':
        raise ValueError('Time-standard acquisition incomplete')
    daily=PRIVATE/'exploratory_power_response.json'
    raw=json.loads(daily.read_text());previous=raw['properties']['parameter']['T2M'];pairs={};versions=set()
    for item in json.loads(receipt.read_text()):
        path=CACHE/f"{item['year']}_{item['standard']}.json.gz"
        with gzip.open(path,'rt') as f:body=json.load(f)
        if body['header']['time_standard']!=item['standard'] or body['parameters']['T2M']['units']!='C':raise ValueError('Time standard or unit differs')
        pairs[(item['year'],item['standard'])]=body['properties']['parameter']['T2M'];versions.add(body['header']['api']['version'])
    counts={'expected_hours':0,'finite_hour_pairs':0,'hour_pairs_equal_1e_6':0,'expected_days':0,
            'complete_hourly_and_daily_pairs':0,'daily_differences_le_0_01':0};hour_errors=[];daily_errors=[]
    for year in plan['years']:
        day=datetime(year,1,1);last=datetime(year,12,30);utc=pairs[(year,'UTC')];lst=pairs[(year,'LST')]
        while day<=last:
            hourly=[]
            for hour in range(24):
                local=day+timedelta(hours=hour);time_utc=local+timedelta(hours=8)
                a=float(lst.get(local.strftime('%Y%m%d%H'),float('nan')));b=float(utc.get(time_utc.strftime('%Y%m%d%H'),float('nan')))
                if a<=-990:a=float('nan')
                if b<=-990:b=float('nan')
                counts['expected_hours']+=1
                if math.isfinite(a) and math.isfinite(b):
                    diff=abs(a-b);counts['finite_hour_pairs']+=1;counts['hour_pairs_equal_1e_6']+=int(diff<=1e-6);hour_errors.append(diff)
                hourly.append(a)
            counts['expected_days']+=1;d=float(previous.get(day.strftime('%Y%m%d'),float('nan')))
            if d<=-990:d=float('nan')
            if math.isfinite(d) and all(math.isfinite(x) for x in hourly):
                error=abs(d-math.fsum(hourly)/24);counts['complete_hourly_and_daily_pairs']+=1
                counts['daily_differences_le_0_01']+=int(error<=.01000001);daily_errors.append(error)
            day+=timedelta(days=1)
    for key,value in counts.items():
        if value!=status[key]:raise AssertionError('Time comparison count differs: '+key)
    for key,value in [('max_hour_difference_c',max(hour_errors)),('max_daily_difference_c',max(daily_errors)),
                      ('mean_daily_difference_c',math.fsum(daily_errors)/len(daily_errors))]:
        if not math.isclose(value,status[key],abs_tol=1e-10,rel_tol=0):raise AssertionError('Time difference differs: '+key)
    if sorted(versions)!=status['api_versions']:raise AssertionError('Hourly API versions differ')
    result={'status':'passed','hour_pairs_recomputed':counts['finite_hour_pairs'],'daily_pairs_recomputed':counts['complete_hourly_and_daily_pairs'],
            'hourly_api_versions':sorted(versions),'daily_api_version':raw['header']['api']['version'],
            'scope':'Independent datetime and scalar arithmetic over the same current NASA POWER responses.',
            'limitations':'This tests NASA POWER UTC/LST product alignment, not whether the provider water sensor used a fixed PST clock, source vintage, meteorological accuracy or independent-climate performance.'}
    (OUT/'power_time_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
