#!/usr/bin/env python3
"""Reproduce USGS parent-series qualification and fixed/civil H30 checks.

Uses only this snapshot's attributed public USGS and NASA POWER inputs. Does not
load a model, reconstruct model predictions, verify sensor accuracy or resolve
source/network independence. Output is written to the extracted snapshot.
"""
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
 receipts=json.loads((BASE/'metadata/continuous_receipts.json').read_text());roster=pd.read_csv(BASE/'metadata/target_roster.csv',dtype={'station_id':str});meta=pd.read_csv(BASE/'metadata/cohort_metadata.csv',dtype={'station_id':str}).set_index('station_id')
 expected=pd.read_parquet(BASE/'results/continuous_qualification_days.parquet');expected['day']=pd.to_datetime(expected.day);annual=pd.read_csv(BASE/'results/continuous_qualification_years.csv',dtype={'station_id':str}).set_index(['station_id','year','clock']);clock=pd.read_csv(BASE/'results/reference_clock_comparison.csv',dtype={'station_id':str}).set_index(['station_id','year']);record=[];days_checked=0
 if len(receipts)!=8 or len(roster)!=8 or roster.station_id.nunique()!=4:raise ValueError('Unexpected frozen target cohort')
 for item in receipts:
  site=item['station_id'];year=int(item['year']);rows=[]
  if item['status']!='completed':raise ValueError('Unknown acquisition outcome')
  for page in item['pages']:
   f=(BASE/'raw'/page['file']).resolve()
   if not f.is_relative_to((BASE/'raw').resolve()):raise ValueError('Raw USGS page changed')
   with gzip.open(f,'rt') as stream:doc=json.load(stream)
   if len(doc['features'])!=page['features']:raise ValueError('USGS page row count changed')
   rows += [x['properties'] for x in doc['features']]
  counts=collections.Counter(datetime.fromisoformat(r['time'].replace('Z','+00:00')).astimezone(timezone.utc) for r in rows)
  daily=pd.read_parquet(BASE/'daily'/(site+'.parquet'));daily['date']=pd.to_datetime(daily.date);pub={r.date.date():float(r.water_c) for r in daily.itertuples(index=False) if bool(r.reported) and not bool(r.unapproved) and not bool(r.ambiguous) and not bool(r.estimated) and pd.notna(r.water_c) and np.isfinite(r.water_c)}
  ref=[pub.get(date(year,1,1)+timedelta(days=i),float('nan')) for i in range(366 if pd.Timestamp(year,12,31).is_leap_year else 365)]
  if not all(math.isfinite(x) for x in ref):raise ValueError('Daily reference fails saved completeness rule')
  ref_h30=max(sum(ref[i:i+30])/30 for i in range(len(ref)-29));expected_h=float(clock.loc[(site,year),'published_daily_h30'])
  if not math.isclose(ref_h30,expected_h,abs_tol=1e-10):raise AssertionError('Published daily H30 differs')
  m=meta.loc[site];offset={'MST':-7,'CST':-6}[m.time_zone_abbreviation]
  for label,zone in [('fixed_standard',timezone(timedelta(hours=offset))),('native_civil',ZoneInfo(m.native_zone))]:
   groups=collections.defaultdict(list)
   for r in rows:
    t=datetime.fromisoformat(r['time'].replace('Z','+00:00')).astimezone(timezone.utc);local=t.astimezone(zone).date()
    if local.year!=year:continue
    try:v=float(r['value'])
    except (ValueError,TypeError):v=float('nan')
    good=str(r.get('approval_status','')).lower()=='approved' and empty(r.get('qualifier')) and math.isfinite(v) and t.minute%15==0 and t.second==0 and t.microsecond==0 and counts[t]==1
    groups[local].append((t,v,good))
   total_h=total_q=0;diff=[];quarter_means=[]
   for i in range(len(ref)):
    day=date(year,1,1)+timedelta(days=i);begin=datetime.combine(day,datetime.min.time(),tzinfo=zone).astimezone(timezone.utc);end=datetime.combine(day+timedelta(days=1),datetime.min.time(),tzinfo=zone).astimezone(timezone.utc);nq=int((end-begin).total_seconds()/900);nh=nq//4
    expq={begin+timedelta(minutes=15*j) for j in range(nq)};exph={begin+timedelta(hours=j) for j in range(nh)};observed=groups.get(day,[]);clean=bool(observed) and all(x[2] for x in observed);slots={x[0] for x in observed};hours={x[0].replace(minute=0,second=0,microsecond=0) for x in observed};hour=clean and hours==exph;quarter=clean and len(observed)==nq and slots==expq
    mean=sum(x[1] for x in observed)/len(observed) if quarter else float('nan');z=expected[(expected.station_id==site)&(expected.year==year)&(expected.clock==label)&(expected.day==pd.Timestamp(day))]
    if len(z)!=1:raise ValueError('Expected day missing')
    x=z.iloc[0]
    if int(x.expected_hours)!=nh or int(x.n_rows)!=len(observed) or bool(x.hourly_complete)!=hour or bool(x.quarter_complete)!=quarter or not np.isclose(x.subdaily_mean,mean,atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Continuous day differs')
    if not np.isclose(x.published_daily,ref[i],atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Published day differs')
    if quarter:diff.append(mean-ref[i])
    quarter_means.append(mean);total_h+=hour;total_q+=quarter;days_checked+=1
   y=annual.loc[(site,year,label)];d=np.asarray(diff,float)
   checks={'days':len(ref),'hourly_complete_days':total_h,'quarter_complete_days':total_q,'hourly_complete_year':total_h==len(ref),'quarter_complete_year':total_q==len(ref),'comparison_days':len(d),
    'mean_abs_daily_difference_c':np.mean(np.abs(d)) if len(d) else np.nan,'max_abs_daily_difference_c':max(np.abs(d)) if len(d) else np.nan,'days_abs_diff_at_most_0_05_c':int((np.abs(d)<=.05+1e-10).sum())}
   for key,value in checks.items():
    if not np.isclose(value,y[key],atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Annual mismatch '+key)
   if total_q==len(ref):
    h30=max(sum(quarter_means[i:i+30])/30 for i in range(len(ref)-29))
    if not np.isclose(h30,clock.loc[(site,year),label+'_continuous_h30'],atol=1e-10,rtol=0):raise AssertionError('Continuous H30 differs')
   record.append((site,year,label,total_h==len(ref),total_q==len(ref)))
  print('Replayed USGS target',len(record)//2,'of 8',flush=True)
 # Rebuild saved gridded air from the four NASA POWER JSON responses.
 manifest=json.loads((BASE/'power/manifest.json').read_text());frames=[]
 for item in manifest['records']:
  p=BASE/'power'/item['file']
  if item['parameters']['time-standard']!='LST':raise ValueError('NASA input changed')
  with gzip.open(p,'rt') as f:data=json.load(f)
  v=data['properties']['parameter']['T2M'];dates=pd.date_range('2011-01-01','2024-12-31');series=pd.to_numeric(pd.Series([v.get(t.strftime('%Y%m%d'),np.nan) for t in dates]),errors='coerce');series=series.where(series.gt(-990));frames.append(pd.DataFrame({'date':dates,'air_temperature_c':series,'station_id':item['station_id'],'network_id':'usgs_partial_'+item['station_id']}))
 air=pd.concat(frames,ignore_index=True).sort_values(['station_id','date']).reset_index(drop=True);saved=pd.read_parquet(BASE/'power/daily_air.parquet').sort_values(['station_id','date']).reset_index(drop=True);pd.testing.assert_frame_equal(air,saved,check_dtype=False,atol=1e-10,rtol=0)
 q=[r for r in record if r[2]=='fixed_standard'];out={'status':'passed','sites':int(roster.station_id.nunique()),'target_years':len(roster),'day_clock_rows':days_checked,'fixed_hourly_complete_years':sum(x[3] for x in q),'fixed_quarter_complete_years':sum(x[4] for x in q),
  'published_daily_h30_checked':len(roster),'NASA_daily_rows':len(air),'scope':'Public source response and processed published-daily snapshots, two-clock completeness/quality and H30, and saved NASA forcing.',
  'limitations':'This does not fit models, reproduce model scores, establish actual clock convention, verify physical sensor accuracy or source/climate independence. Source daily preprocessing is reused.'}
 (BASE/'results/public_reference_replay.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
