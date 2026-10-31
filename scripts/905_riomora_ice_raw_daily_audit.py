#!/usr/bin/env python3
"""Check whether raw USGS daily qualifiers expose continuous ICE flags."""
import argparse,collections,gzip,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');USGS=ROOT/'results/additional_usgs_observed';DATA=ROOT/'data/external/additional_usgs_observed';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');RAW=STAGE/'expansion_raw';SITE='08377900'
def blank(v):
 if v is None:return True
 if isinstance(v,list):return all(not str(x).strip() for x in v)
 return not str(v).strip()
def ice(v):
 if isinstance(v,list):return any(str(x).strip().upper()=='ICE' for x in v)
 return str(v).strip().upper()=='ICE'
def freeze():
 path=STAGE/'expansion_ice_raw_daily_plan.json'
 if path.exists():raise FileExistsError('Preserve raw qualifier plan')
 audit=json.loads((STAGE/'expansion_independent_audit.json').read_text());receipt=STAGE/'expansion_receipts.json'
 if audit['status']!='passed':raise ValueError('Initial ICE audit not verified')
 files=[receipt,STAGE/'expansion_independent_audit.json',STAGE/'expansion_ice_daily_mismatch.csv',DATA/'raw/08377900.json.gz',USGS/'cohort_metadata.csv',Path(__file__)]
 for item in json.loads(receipt.read_text()):
  for page in item['pages']:files.append(RAW/page['file'])
 p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after continuous ICE and processed-daily mismatch results were inspected, before raw-daily qualifier comparison',
    'cohort':'All five fixed Rio Mora expansion years, both fixed-standard and native-civil clocks, including zero-ICE years.',
    'comparison':'Identify calendar dates containing any continuous observation explicitly qualified ICE. Compare those dates with the original previously downloaded USGS daily API rows: unique row, approval, finite value, and blank/nonblank daily qualifier. Do not infer that either representation is accurate or wrong.',
    'limitation':'Daily and continuous products may use different time conventions, revisions or processing. A blank daily qualifier is not proof of absent uncertainty; an ICE qualifier does not by itself invalidate the daily mean. The source and data were previously opened and are not independent.',
    }
 path.write_text(json.dumps(p,indent=2)+'\n');print('Frozen raw daily-versus-continuous qualifier audit')
def run():
 p=json.loads((STAGE/'expansion_ice_raw_daily_plan.json').read_text())
 meta=pd.read_csv(USGS/'cohort_metadata.csv',dtype={'station_id':str}).set_index('station_id').loc[SITE];expected=pd.read_csv(STAGE/'expansion_ice_daily_mismatch.csv',dtype={'station_id':str}).set_index(['station_id','year','clock'])
 with gzip.open(DATA/'raw/08377900.json.gz','rt') as f:daily_doc=json.load(f)
 daily=collections.defaultdict(list)
 for item in daily_doc['features']:
  r=item.get('properties',item);text=str(r['time']);t=pd.Timestamp(text)
  if len(text)!=10 and t.tzinfo is not None:t=t.tz_convert(meta.native_zone).tz_localize(None)
  daily[t.date()].append(r)
 results=[]
 for item in json.loads((STAGE/'expansion_receipts.json').read_text()):
  year=int(item['year']);raw=[]
  for page in item['pages']:
   with gzip.open(RAW/page['file'],'rt') as f:doc=json.load(f)
   raw.extend(x['properties'] for x in doc['features'])
  for label,zone in [('fixed_standard',timezone(timedelta(hours=-7))),('native_civil',ZoneInfo(meta.native_zone))]:
   dates=set()
   for r in raw:
    t=datetime.fromisoformat(r['time'].replace('Z','+00:00')).astimezone(zone)
    if t.year==year and ice(r.get('qualifier')):dates.add(t.date())
   good=absent=multi=nonblank=unapproved=nonfinite=0
   for day in sorted(dates):
    items=daily.get(day,[])
    if not items:absent+=1;continue
    if len(items)!=1:multi+=1;continue
    d=items[0]
    try:v=float(d['value'])
    except (TypeError,ValueError):v=float('nan')
    if not np.isfinite(v):nonfinite+=1;continue
    if str(d.get('approval_status','')).lower()!='approved':unapproved+=1;continue
    if not blank(d.get('qualifier')):nonblank+=1;continue
    good+=1
   if len(dates)!=int(expected.loc[(SITE,year,label),'days_with_ICE']):raise AssertionError('ICE date count differs')
   results.append({'station_id':SITE,'year':year,'clock':label,'ICE_flagged_continuous_days':len(dates),'daily_approved_finite_blank_qualifier_days':good,
      'daily_absent_days':absent,'daily_multiple_rows_days':multi,'daily_nonblank_qualifier_days':nonblank,'daily_unapproved_days':unapproved,'daily_nonfinite_days':nonfinite})
 table=pd.DataFrame(results);file=STAGE/'expansion_ice_raw_daily_comparison.csv';table.to_csv(file,index=False);subset=table[table.clock.eq('fixed_standard')]
 result={'status':'passed','years':len(subset),'fixed_standard_ICE_days':int(subset.ICE_flagged_continuous_days.sum()),
    'fixed_standard_ICE_days_with_approved_finite_blank_daily_qualifier':int(subset.daily_approved_finite_blank_qualifier_days.sum()),
    'limitations':p['limitation'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'expansion_ice_raw_daily_status.json').write_text(json.dumps(result,indent=2)+'\n');print(table.to_string(index=False));print(json.dumps(result,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
