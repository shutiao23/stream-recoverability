#!/usr/bin/env python3
"""Offline check of the POWER hourly UTC/LST and daily forcing alignment."""
import argparse
from datetime import datetime,timedelta
import gzip
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';SNAP=ROOT/'data/external/wrr_truckee_dwr_20261027';WEATHER=SNAP/'power_time_standards'

def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,default=ROOT/'results/wrr_review_response_20261027/audit/truckee_power_time_open_replay.json');args=p.parse_args()
    manifest=json.loads((WEATHER/'manifest.json').read_text());status=json.loads((OUT/'power_time_comparison.json').read_text())
    parent=json.loads((SNAP/'manifest.json').read_text());entry=[x for x in parent['files'] if x['file']=='exploratory_power_response.json']
    daily_file=SNAP/'exploratory_power_response.json'
    if len(entry)!=1:raise ValueError('Daily POWER response changed')
    daily=json.loads(daily_file.read_text())['properties']['parameter']['T2M'];series={}
    for item in manifest['records']:
        path=(WEATHER/item['file']).resolve()
        if not path.is_relative_to(WEATHER.resolve()):raise ValueError('POWER response changed')
        with gzip.open(path,'rt') as f:body=json.load(f)
        if body['header']['time_standard']!=item['standard'] or body['parameters']['T2M']['units']!='C':raise ValueError('POWER metadata differs')
        key=(item['year'],item['standard'])
        if key in series:raise ValueError('Duplicate POWER response')
        series[key]=body['properties']['parameter']['T2M']
    pairs=equal=valid_days=within=0;max_hour=0.;max_day=0.;sum_day=0.
    for year in (2011,2013,2014,2020):
        day=datetime(year,1,1);last=datetime(year,12,30);lst=series[(year,'LST')];utc=series[(year,'UTC')]
        while day<=last:
            samples=[]
            for h in range(24):
                t=day+timedelta(hours=h);a=float(lst.get(t.strftime('%Y%m%d%H'),float('nan')));b=float(utc.get((t+timedelta(hours=8)).strftime('%Y%m%d%H'),float('nan')))
                if a<=-990:a=float('nan')
                if b<=-990:b=float('nan')
                if math.isfinite(a) and math.isfinite(b):pairs+=1;equal+=int(abs(a-b)<=1e-6);max_hour=max(max_hour,abs(a-b))
                samples.append(a)
            d=float(daily.get(day.strftime('%Y%m%d'),float('nan')))
            if d>-990 and math.isfinite(d) and all(math.isfinite(x) for x in samples):
                e=abs(d-math.fsum(samples)/24);valid_days+=1;within+=int(e<=.01000001);max_day=max(max_day,e);sum_day+=e
            day+=timedelta(days=1)
    if pairs!=status['finite_hour_pairs'] or equal!=status['hour_pairs_equal_1e_6'] or valid_days!=status['complete_hourly_and_daily_pairs'] or within!=status['daily_differences_le_0_01']:
        raise ValueError('POWER source comparison counts differ')
    if not math.isclose(max_hour,status['max_hour_difference_c'],abs_tol=1e-10) or not math.isclose(max_day,status['max_daily_difference_c'],abs_tol=1e-10) or not math.isclose(sum_day/valid_days,status['mean_daily_difference_c'],abs_tol=1e-10):raise ValueError('POWER source numerical differences differ')
    result={'status':'passed','responses':len(series),'finite_hour_pairs':pairs,'equal_hour_pairs':equal,'daily_pairs':valid_days,
            'scope':'Offline replay of current public POWER UTC/LST hourly responses and the original daily forcing; no provider water clock or source-model predictions are checked.',
            'limitations':'Does not establish actual water sensor time convention, physical measurement accuracy, historical data vintage or independent-climate performance.'}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
