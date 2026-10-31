#!/usr/bin/env python3
"""Independent scalar/civil-clock audit of continuous qualification."""
import argparse,collections,gzip,json,math
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');OUT=ROOT/'results/wrr_review_response_20261027/external_usgs_partial_daily';USGS=ROOT/'results/additional_usgs_observed';DATA=ROOT/'data/external/additional_usgs_observed';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');RAW=STAGE/'raw'
def freeze():
 path=STAGE/'independent_audit_plan.json'
 if path.exists():raise FileExistsError('Preserve audit plan')
 s=json.loads((STAGE/'continuous_qualification_status.json').read_text())
 if s['status']!='completed_continuous_qualification':raise ValueError('Qualification incomplete')
 files=[STAGE/'continuous_qualification_status.json',STAGE/'continuous_qualification_years.csv',STAGE/'continuous_qualification_days.parquet',STAGE/'qualification_plan.json',STAGE/'continuous_tmpfs_receipts.json',USGS/'cohort_metadata.csv',Path(__file__)]
 p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after continuous eligibility and comparison summaries were examined',
  'scope':'Recompute all eight years using Python datetime, scalar qualification, UTC slot sets, independent daily means and both fixed-standard and civil reporting days. Recheck all saved day/year counts and numeric comparisons.',
  'limitations':'Same underlying source observations and previously processed daily records; a passed audit does not establish time convention, instrument accuracy, unrecorded corrections or source/climate independence.',
  }
 path.write_text(json.dumps(p,indent=2)+'\n');print('Frozen independent continuous audit')
def empty(v):
 if v is None:return True
 if isinstance(v,list):return all(not str(x).strip() for x in v)
 return not str(v).strip()
def run():
 p=json.loads((STAGE/'independent_audit_plan.json').read_text())
 expected=pd.read_parquet(STAGE/'continuous_qualification_days.parquet');expected['day']=pd.to_datetime(expected.day)
 ys=pd.read_csv(STAGE/'continuous_qualification_years.csv',dtype={'station_id':str}).set_index(['station_id','year','clock']);meta=pd.read_csv(USGS/'cohort_metadata.csv',dtype={'station_id':str}).set_index('station_id');count=0;yearrows=[]
 for n,item in enumerate(json.loads((STAGE/'continuous_tmpfs_receipts.json').read_text()),1):
  site=item['station_id'];year=item['year'];rows=[]
  for page in item['pages']:
   f=RAW/page['file']
   with gzip.open(f,'rt') as stream:doc=json.load(stream)
   rows += [x['properties'] for x in doc['features']]
  counts=collections.Counter(datetime.fromisoformat(r['time'].replace('Z','+00:00')).astimezone(timezone.utc) for r in rows)
  daily=pd.read_parquet(DATA/'daily'/(site+'.parquet'));daily['date']=pd.to_datetime(daily.date);pub={r.date.date():float(r.water_c) for r in daily.itertuples(index=False) if bool(r.reported) and not bool(r.unapproved) and not bool(r.ambiguous) and not bool(r.estimated) and pd.notna(r.water_c) and np.isfinite(r.water_c)}
  x=meta.loc[site];offset={'MST':-7,'CST':-6}[x.time_zone_abbreviation]
  for label,zone in [('fixed_standard',timezone(timedelta(hours=offset))),('native_civil',ZoneInfo(x.native_zone))]:
   grouped=collections.defaultdict(list)
   for r in rows:
    t=datetime.fromisoformat(r['time'].replace('Z','+00:00')).astimezone(timezone.utc);local=t.astimezone(zone).date()
    if local.year!=year:continue
    try:v=float(r['value'])
    except (ValueError,TypeError):v=float('nan')
    clean=str(r.get('approval_status','')).lower()=='approved' and empty(r.get('qualifier')) and math.isfinite(v) and t.minute%15==0 and t.second==0 and t.microsecond==0 and counts[t]==1
    grouped[local].append((t,v,clean))
   good_hours=good_quarters=0;diffs=[];days=366 if pd.Timestamp(year,12,31).is_leap_year else 365
   for i in range(days):
    day=date(year,1,1)+timedelta(days=i);begin=datetime.combine(day,datetime.min.time(),tzinfo=zone).astimezone(timezone.utc);end=datetime.combine(day+timedelta(days=1),datetime.min.time(),tzinfo=zone).astimezone(timezone.utc)
    nquarter=int((end-begin).total_seconds()/900);nhour=nquarter//4;expected_slots={begin+timedelta(minutes=15*j) for j in range(nquarter)};expected_hours={begin+timedelta(hours=j) for j in range(nhour)};obs=grouped.get(day,[])
    clean=bool(obs) and all(z[2] for z in obs);slots={z[0] for z in obs};hours={z[0].replace(minute=0,second=0,microsecond=0) for z in obs};h=clean and hours==expected_hours;q=clean and len(obs)==nquarter and slots==expected_slots
    value=sum(z[1] for z in obs)/len(obs) if q else float('nan');d=expected[(expected.station_id==site)&(expected.year==year)&(expected.clock==label)&(expected.day==pd.Timestamp(day))]
    if len(d)!=1:raise AssertionError('Missing saved day')
    z=d.iloc[0]
    if int(z.expected_hours)!=nhour or int(z.n_rows)!=len(obs) or bool(z.hourly_complete)!=h or bool(z.quarter_complete)!=q or not np.isclose(z.subdaily_mean,value,atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Daily qualification mismatch')
    pv=pub.get(day,float('nan'))
    if not np.isclose(z.published_daily,pv,atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Daily reference mismatch')
    if q and math.isfinite(pv):diffs.append(value-pv)
    good_hours+=h;good_quarters+=q;count+=1
   s=ys.loc[(site,year,label)];diff=np.asarray(diffs,float)
   checks={'days':days,'hourly_complete_days':good_hours,'quarter_complete_days':good_quarters,'hourly_complete_year':good_hours==days,'quarter_complete_year':good_quarters==days,'comparison_days':len(diff),'mean_abs_daily_difference_c':np.mean(np.abs(diff)) if len(diff) else np.nan,'max_abs_daily_difference_c':max(np.abs(diff)) if len(diff) else np.nan,'days_abs_diff_at_most_0_05_c':int((np.abs(diff)<=.05+1e-10).sum())}
   for k,v in checks.items():
    if not np.isclose(v,s[k],atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Year summary mismatch: '+k)
   yearrows.append((site,year,label,good_hours==days,good_quarters==days))
  print('Independent continuous audit',n,'of 8',flush=True)
 status=json.loads((STAGE/'continuous_qualification_status.json').read_text())
 for label in ['fixed_standard','native_civil']:
  z=[x for x in yearrows if x[2]==label];s=status['comparisons'][label]
  if len(z)!=s['station_years'] or sum(x[3] for x in z)!=s['hourly_complete_years'] or sum(x[4] for x in z)!=s['quarter_complete_years']:raise AssertionError('Aggregate year mismatch')
 result={'status':'passed','station_years':len(yearrows)//2,'day_clock_rows_recomputed':count,'fixed_standard_hourly_complete_years':status['comparisons']['fixed_standard']['hourly_complete_years'],'fixed_standard_quarter_complete_years':status['comparisons']['fixed_standard']['quarter_complete_years'],'scope':p['scope'],'limitations':p['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'independent_audit_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
