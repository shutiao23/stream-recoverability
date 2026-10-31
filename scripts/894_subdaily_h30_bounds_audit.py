#!/usr/bin/env python3
"""Independently recompute conditional subdaily H30 bounds via UTC slot sets."""
import collections,gzip,json,math
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');USGS=ROOT/'results/additional_usgs_observed';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');RAW=STAGE/'raw'
def empty(v):
 if v is None:return True
 if isinstance(v,list):return all(not str(x).strip() for x in v)
 return not str(v).strip()
def main():
 p=json.loads((STAGE/'subdaily_h30_bounds_plan.json').read_text());status=json.loads((STAGE/'subdaily_h30_bounds_status.json').read_text())
 days=pd.read_parquet(STAGE/'subdaily_h30_bounds_days.parquet');days['day']=pd.to_datetime(days.day);years=pd.read_csv(STAGE/'subdaily_h30_bounds_years.csv',dtype={'station_id':str}).set_index(['station_id','year','clock']);meta=pd.read_csv(USGS/'cohort_metadata.csv',dtype={'station_id':str}).set_index('station_id');checked=0;results=[]
 for item in json.loads((STAGE/'continuous_tmpfs_receipts.json').read_text()):
  site=item['station_id'];year=item['year'];raw=[]
  for page in item['pages']:
   f=RAW/page['file']
   with gzip.open(f,'rt') as stream:doc=json.load(stream)
   raw.extend(x['properties'] for x in doc['features'])
  m=meta.loc[site];offset={'MST':-7,'CST':-6}[m.time_zone_abbreviation]
  for label,zone in [('fixed_standard',timezone(timedelta(hours=offset))),('native_civil',ZoneInfo(m.native_zone))]:
   group=collections.defaultdict(list)
   for row in raw:
    t=datetime.fromisoformat(row['time'].replace('Z','+00:00')).astimezone(timezone.utc);day=t.astimezone(zone).date()
    if day.year!=year:continue
    try:v=float(row['value'])
    except (TypeError,ValueError):v=float('nan')
    grid=t.minute%15==0 and t.second==0 and t.microsecond==0
    good=str(row.get('approval_status','')).lower()=='approved' and empty(row.get('qualifier')) and math.isfinite(v) and grid
    group[day].append((t,v,grid,good))
   n=366 if pd.Timestamp(year,12,31).is_leap_year else 365;low=[];high=[];known_total=0;unknown_total=0
   for j in range(n):
    day=date(year,1,1)+timedelta(days=j);begin=datetime.combine(day,datetime.min.time(),tzinfo=zone).astimezone(timezone.utc);end=datetime.combine(day+timedelta(days=1),datetime.min.time(),tzinfo=zone).astimezone(timezone.utc);nslot=int((end-begin).total_seconds()/900);expected={begin+timedelta(minutes=15*i) for i in range(nslot)};obs=group.get(day,[]);off=sum(not x[2] for x in obs);counter=collections.Counter(x[0] for x in obs)
    values=[] if off else [x[1] for x in obs if x[3] and counter[x[0]]==1]
    if any(x[0] not in expected for x in obs if x[3]) or any(not -5<=v<=50 for v in values):raise ValueError('Unexpected observed value/slot')
    k=len(values);lower=(sum(values)+(nslot-k)*-5)/nslot;upper=(sum(values)+(nslot-k)*50)/nslot
    q=days[(days.station_id==site)&(days.year==year)&(days.clock==label)&(days.day==pd.Timestamp(day))]
    if len(q)!=1:raise AssertionError('Missing saved day')
    r=q.iloc[0]
    for name,val in [('expected_slots',nslot),('known_slots',k),('unknown_slots',nslot-k),('offgrid_rows',off),('lower_c',lower),('upper_c',upper)]:
     if not np.isclose(r[name],val,atol=1e-10,rtol=0):raise AssertionError('Daily bound mismatch '+name)
    low.append(lower);high.append(upper);known_total+=k;unknown_total+=nslot-k;checked+=1
   L=max(sum(low[i:i+30])/30 for i in range(n-29));U=max(sum(high[i:i+30])/30 for i in range(n-29));r=years.loc[(site,year,label)]
   for name,val in [('known_slots',known_total),('unknown_slots',unknown_total),('h30_lower_c',L),('h30_upper_c',U),('h30_interval_width_c',U-L)]:
    if not np.isclose(r[name],val,atol=1e-10,rtol=0):raise AssertionError('Annual bound mismatch '+name)
   results.append((site,year,label,L,U))
  print('Audited subdaily H30 bounds',len(results)//2,'of 8',flush=True)
 for label in ['fixed_standard','native_civil']:
  vals=[x for x in results if x[2]==label];s=status['clock_summaries'][label];width=[x[4]-x[3] for x in vals]
  if len(vals)!=s['years'] or sum(x<=1e-10 for x in width)!=s['zero_width_years'] or sum(x<=.01+1e-10 for x in width)!=s['width_at_most_0_01_c_years'] or sum(x<=.1+1e-10 for x in width)!=s['width_at_most_0_1_c_years']:raise AssertionError('Aggregate bounds differ')
 out={'status':'passed','target_years':len(results)//2,'day_clock_rows':checked,'fixed_zero_width_years':status['clock_summaries']['fixed_standard']['zero_width_years'],'scope':'Independent scalar UTC-slot set and rolling-window reconstruction for all eight years and both clocks.','limitations':p['assumption']+' '+p['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'subdaily_h30_bounds_independent_audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
