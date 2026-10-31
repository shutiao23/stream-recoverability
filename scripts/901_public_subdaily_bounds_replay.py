#!/usr/bin/env python3
"""Reproduce conditional H30 bounds from the portable USGS source snapshot."""
import collections,gzip,json,math
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np,pandas as pd
BASE=Path(__file__).resolve().parents[1]
def empty(v):
 if v is None:return True
 if isinstance(v,list):return all(not str(x).strip() for x in v)
 return not str(v).strip()
def main():
 receipts=json.loads((BASE/'metadata/continuous_receipts.json').read_text());meta=pd.read_csv(BASE/'metadata/cohort_metadata.csv',dtype={'station_id':str}).set_index('station_id');status=json.loads((BASE/'results/subdaily_h30_bounds_status.json').read_text());yearfile=BASE/'results/subdaily_h30_bounds_years.csv';dayfile=BASE/'results/subdaily_h30_bounds_days.parquet'
 days=pd.read_parquet(dayfile);days.day=pd.to_datetime(days.day);years=pd.read_csv(yearfile,dtype={'station_id':str}).set_index(['station_id','year','clock']);rows=[];checked=0
 for item in receipts:
  site=item['station_id'];year=int(item['year']);raw=[]
  if item['status']!='completed':raise ValueError('Unknown continuous intake')
  for page in item['pages']:
   f=(BASE/'raw'/page['file']).resolve()
   if not f.is_relative_to((BASE/'raw').resolve()):raise ValueError('Continuous source changed')
   with gzip.open(f,'rt') as stream:doc=json.load(stream)
   raw.extend(x['properties'] for x in doc['features'])
  m=meta.loc[site];offset={'MST':-7,'CST':-6}[m.time_zone_abbreviation]
  for label,zone in [('fixed_standard',timezone(timedelta(hours=offset))),('native_civil',ZoneInfo(m.native_zone))]:
   grouped=collections.defaultdict(list)
   for row in raw:
    t=datetime.fromisoformat(row['time'].replace('Z','+00:00')).astimezone(timezone.utc);d=t.astimezone(zone).date()
    if d.year!=year:continue
    try:v=float(row['value'])
    except (TypeError,ValueError):v=float('nan')
    grid=t.minute%15==0 and t.second==0 and t.microsecond==0;good=str(row.get('approval_status','')).lower()=='approved' and empty(row.get('qualifier')) and math.isfinite(v) and grid
    grouped[d].append((t,v,grid,good))
   n=366 if pd.Timestamp(year,12,31).is_leap_year else 365;lower=[];upper=[];known_sum=unknown_sum=0
   for j in range(n):
    day=date(year,1,1)+timedelta(days=j);begin=datetime.combine(day,datetime.min.time(),tzinfo=zone).astimezone(timezone.utc);end=datetime.combine(day+timedelta(days=1),datetime.min.time(),tzinfo=zone).astimezone(timezone.utc);expected_n=int((end-begin).total_seconds()/900);expected={begin+timedelta(minutes=15*i) for i in range(expected_n)};obs=grouped.get(day,[]);off=sum(not q[2] for q in obs);counts=collections.Counter(q[0] for q in obs)
    val=[] if off else [q[1] for q in obs if q[3] and counts[q[0]]==1]
    if any(q[0] not in expected for q in obs if q[3]) or any(not -5<=v<=50 for v in val):raise ValueError('Unexpected slot or value')
    k=len(val);lo=(sum(val)+(expected_n-k)*-5)/expected_n;hi=(sum(val)+(expected_n-k)*50)/expected_n
    d=days[(days.station_id==site)&days.year.eq(year)&days.clock.eq(label)&days.day.eq(pd.Timestamp(day))]
    if len(d)!=1:raise ValueError('Saved day missing')
    r=d.iloc[0]
    for name,value in [('expected_slots',expected_n),('known_slots',k),('unknown_slots',expected_n-k),('offgrid_rows',off),('lower_c',lo),('upper_c',hi)]:
     if not np.isclose(value,r[name],atol=1e-10,rtol=0):raise AssertionError('Daily bound differs: '+name)
    lower.append(lo);upper.append(hi);known_sum+=k;unknown_sum+=expected_n-k;checked+=1
   L=max(sum(lower[i:i+30])/30 for i in range(n-29));U=max(sum(upper[i:i+30])/30 for i in range(n-29));r=years.loc[(site,year,label)]
   for name,value in [('known_slots',known_sum),('unknown_slots',unknown_sum),('h30_lower_c',L),('h30_upper_c',U),('h30_interval_width_c',U-L)]:
    if not np.isclose(value,r[name],atol=1e-10,rtol=0):raise AssertionError('Annual bound differs: '+name)
   rows.append((site,year,label,L,U))
  print('Replayed conditional subdaily bounds',len(rows)//2,'of 8',flush=True)
 for label in ['fixed_standard','native_civil']:
  a=[r[4]-r[3] for r in rows if r[2]==label];saved=status['clock_summaries'][label]
  if len(a)!=saved['years'] or sum(x<=1e-10 for x in a)!=saved['zero_width_years'] or sum(x<=.01+1e-10 for x in a)!=saved['width_at_most_0_01_c_years'] or sum(x<=.1+1e-10 for x in a)!=saved['width_at_most_0_1_c_years']:raise AssertionError('Aggregate bounds differ')
 out={'status':'passed','target_years':len(rows)//2,'day_clock_rows':checked,'fixed_zero_width_years':status['clock_summaries']['fixed_standard']['zero_width_years'],
   'scope':'Public continuous-source records, conditional daily slot bounds and annual 30-day maxima for two clocks.',
   'limitations':'The [-5,50] C range for missing samples is an assumption, not sensor accuracy. Does not evaluate models, establish actual clock, source/climate independence or validate physical water temperature.'}
 (BASE/'results/subdaily_bounds_reference_replay.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
