#!/usr/bin/env python3
"""Independent UTC-slot audit and ICE-qualifier versus daily-history check."""
import collections,gzip,json,math
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');USGS=ROOT/'results/additional_usgs_observed';DATA=ROOT/'data/external/additional_usgs_observed';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');RAW=STAGE/'expansion_raw'
def empty(v):
 if v is None:return True
 if isinstance(v,list):return all(not str(x).strip() for x in v)
 return not str(v).strip()
def ice(v):
 if isinstance(v,list):return any(str(x).strip().upper()=='ICE' for x in v)
 return str(v).strip().upper()=='ICE'
def main():
 p=json.loads((STAGE/'expansion_qualification_plan.json').read_text());s=json.loads((STAGE/'expansion_qualification_status.json').read_text())
 expected=pd.read_parquet(STAGE/'expansion_qualification_days.parquet');expected.day=pd.to_datetime(expected.day);bounds=pd.read_parquet(STAGE/'expansion_bounds_days.parquet');bounds.day=pd.to_datetime(bounds.day);yearly=pd.read_csv(STAGE/'expansion_qualification_years.csv',dtype={'station_id':str}).set_index(['station_id','year','clock']);meta=pd.read_csv(USGS/'cohort_metadata.csv',dtype={'station_id':str}).set_index('station_id').loc['08377900'];d=pd.read_parquet(DATA/'daily/08377900.parquet');d.date=pd.to_datetime(d.date);pub={x.date.date():float(x.water_c) for x in d.itertuples(index=False) if bool(x.reported) and not bool(x.unapproved) and not bool(x.ambiguous) and not bool(x.estimated) and pd.notna(x.water_c) and np.isfinite(x.water_c)}
 out=[];ice_info=[];checked=0
 for n,item in enumerate(json.loads((STAGE/'expansion_receipts.json').read_text()),1):
  site=item['station_id'];year=item['year'];raw=[]
  for page in item['pages']:
   f=RAW/page['file']
   with gzip.open(f,'rt') as stream:doc=json.load(stream)
   raw.extend(x['properties'] for x in doc['features'])
  count=collections.Counter(datetime.fromisoformat(r['time'].replace('Z','+00:00')).astimezone(timezone.utc) for r in raw);offset={'MST':-7,'CST':-6}[meta.time_zone_abbreviation]
  for label,zone in [('fixed_standard',timezone(timedelta(hours=offset))),('native_civil',ZoneInfo(meta.native_zone))]:
   grouped=collections.defaultdict(list);ice_days=set();ice_readings=0
   for r in raw:
    t=datetime.fromisoformat(r['time'].replace('Z','+00:00')).astimezone(timezone.utc);day=t.astimezone(zone).date()
    if day.year!=year:continue
    try:v=float(r['value'])
    except (ValueError,TypeError):v=float('nan')
    grid=t.minute%15==0 and t.second==0 and t.microsecond==0;quality=str(r.get('approval_status','')).lower()=='approved' and empty(r.get('qualifier')) and math.isfinite(v) and grid and count[t]==1
    if ice(r.get('qualifier')):ice_days.add(day);ice_readings+=1
    grouped[day].append((t,v,grid,quality))
   nday=366 if pd.Timestamp(year,12,31).is_leap_year else 365;hcount=qcount=0;low=[];high=[];unknown=0;diff=[]
   for j in range(nday):
    day=date(year,1,1)+timedelta(days=j);begin=datetime.combine(day,datetime.min.time(),tzinfo=zone).astimezone(timezone.utc);end=datetime.combine(day+timedelta(days=1),datetime.min.time(),tzinfo=zone).astimezone(timezone.utc);nslot=int((end-begin).total_seconds()/900);hour=nslot//4;expq={begin+timedelta(minutes=15*i) for i in range(nslot)};exph={begin+timedelta(hours=i) for i in range(hour)};obs=grouped.get(day,[]);clean=bool(obs) and all(x[3] for x in obs);off=sum(not x[2] for x in obs)
    slots={x[0] for x in obs};hours={x[0].replace(minute=0,second=0,microsecond=0) for x in obs};hh=clean and hours==exph;qq=clean and len(obs)==nslot and slots==expq;mean=sum(x[1] for x in obs)/len(obs) if qq else float('nan');known=[] if off else [x[1] for x in obs if x[3]]
    if any(not -5<=v<=50 for v in known):raise ValueError('Clean observed temperature outside assumed range')
    L=(sum(known)+(nslot-len(known))*-5)/nslot;U=(sum(known)+(nslot-len(known))*50)/nslot
    qa=expected[(expected.station_id==site)&expected.year.eq(year)&expected.clock.eq(label)&expected.day.eq(pd.Timestamp(day))];bb=bounds[(bounds.station_id==site)&bounds.year.eq(year)&bounds.clock.eq(label)&bounds.day.eq(pd.Timestamp(day))]
    if len(qa)!=1 or len(bb)!=1:raise AssertionError('Missing saved day')
    qa=qa.iloc[0];bb=bb.iloc[0]
    checks={'expected_hours':hour,'n_rows':len(obs),'hourly_complete':hh,'quarter_complete':qq,'subdaily_mean':mean,'published_daily':pub.get(day,float('nan'))}
    for k,v in checks.items():
     if not np.isclose(qa[k],v,atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Qualification mismatch '+k)
    checks={'expected_slots':nslot,'known_slots':len(known),'unknown_slots':nslot-len(known),'offgrid_rows':off,'lower_c':L,'upper_c':U}
    for k,v in checks.items():
     if not np.isclose(bb[k],v,atol=1e-10,rtol=0):raise AssertionError('Bounds mismatch '+k)
    if qq and day in pub:diff.append(mean-pub[day])
    hcount+=hh;qcount+=qq;low.append(L);high.append(U);unknown+=nslot-len(known);checked+=1
   L=max(sum(low[i:i+30])/30 for i in range(nday-29));U=max(sum(high[i:i+30])/30 for i in range(nday-29));r=yearly.loc[(site,year,label)];diff=np.asarray(diff,float)
   checks={'days':nday,'hourly_complete_days':hcount,'quarter_complete_days':qcount,'hourly_complete_year':hcount==nday,'quarter_complete_year':qcount==nday,'unknown_slots':unknown,'h30_lower_c':L,'h30_upper_c':U,'h30_interval_width_c':U-L,'comparison_days':len(diff),'mean_abs_daily_difference_c':np.mean(abs(diff)) if len(diff) else np.nan,'max_abs_daily_difference_c':max(abs(diff)) if len(diff) else np.nan}
   for k,v in checks.items():
    if not np.isclose(r[k],v,atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Year mismatch '+k)
   out.append((site,year,label,L,U));ice_info.append({'station_id':site,'year':year,'clock':label,'ICE_readings':ice_readings,'days_with_ICE':len(ice_days),'days_with_ICE_and_retained_daily_value':sum(x in pub for x in ice_days)})
  print('Independent Rio Mora expansion audit',n,'of 5',flush=True)
 iceframe=pd.DataFrame(ice_info);icefile=STAGE/'expansion_ice_daily_mismatch.csv';iceframe.to_csv(icefile,index=False);targets=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str});r=targets[targets.station_id.eq('08377900')];iceyears=set(iceframe[(iceframe.clock=='fixed_standard')&iceframe.days_with_ICE_and_retained_daily_value.gt(0)].year);affected=sum(bool(set(map(int,x.split(';')))&iceyears) for x in r.history_years)
 result={'status':'passed','expansion_years':len(out)//2,'day_clock_rows':checked,'fixed_zero_width_H30_years':sum(x[2]=='fixed_standard' and abs(x[4]-x[3])<=1e-10 for x in out),
   'prior_riomora_target_years_with_ICE_flagged_continuous_history':int(affected),'scope':'Independent scalar reconstruction of subdaily qualification and conditional H30 bounds; compare continuous ICE flags with previously retained daily values and history-year rosters.',
   'limitations':'Daily and continuous status can differ by source processing or reporting clock; an ICE qualifier does not itself prove a daily mean is wrong. Same downloaded data and existing daily QC are reused; no independent climate or causal performance claim.','storage':'temporary RAM filesystem; not durable'}
 (STAGE/'expansion_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(iceframe.to_string(index=False));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
