#!/usr/bin/env python3
"""Build a conservative, qualifier-aware alternative for all fixed USGS targets."""
import argparse,gzip,importlib.util,json,sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');sys.path.insert(0,str(ROOT/'scripts'))
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.national import native_daily_dates
USGS=ROOT/'results/additional_usgs_observed';DATA=ROOT/'data/external/additional_usgs_observed';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
def blank(v):
 if v is None:return True
 if isinstance(v,list):return all(not str(x).strip() for x in v)
 return not str(v).strip()
def freeze():
 dest=STAGE/'qualifier_aware_history_plan.json'
 if dest.exists():raise FileExistsError('Preserve history plan')
 for f in ['expansion_independent_audit.json','expansion_ice_raw_daily_status.json','score_independent_audit.json','hidden_all_status.json']:
  if json.loads((STAGE/f).read_text())['status']!='passed':raise ValueError('Prior audit incomplete: '+f)
 roster=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str});files=[PRIVATE/'continuous_target_roster.csv',USGS/'cohort_metadata.csv',ROOT/'scripts/871_usgs_partial_daily_feasibility.py',ROOT/'src/stream_recoverability/experiments/tr_revision/national.py',STAGE/'expansion_independent_audit.json',STAGE/'expansion_ice_raw_daily_status.json',STAGE/'score_independent_audit.json',STAGE/'hidden_all_status.json',Path(__file__)]
 for s in sorted(roster.station_id.unique()):files += [DATA/'raw'/(s+'.json.gz'),DATA/'daily'/(s+'.parquet')]
 plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after original eight-year scores and Rio Mora continuous/daily ICE qualifiers were examined; before qualifier-aware alternative histories or model scores',
  'cohort':'All eight original target years at four sites, including any site with no flagged history. Do not drop a target because the stricter history is unavailable; report unsupported.',
  'history_rule':'Start from previously processed approved/nonestimated/unambiguous daily values, then treat any day with any nonempty original USGS daily qualifier as unavailable, even if approved and numeric. Reapply the existing >=75%, observed endpoints and longest-gap<=45-day history eligibility to each originally eligible history year. Interpolate remaining missing days only within each eligible year; use actual complete-history count. Dropping a flagged value is conservative sensitivity, not a conclusion that it is erroneous.',
  'target':'All original eight target years remain subject to approved, finite, unambiguous and no nonempty raw daily qualifier. Hold target year out of local training. Later replay the exact original artificial masks; never select a new mask or site based on predictive error.',
  'comparisons':'On both original and qualifier-aware histories report every target and availability; compare plug-in, fixed-source D2 and stochastic on common cases. Separately retain the already seen three-year Rio Mora subdaily-supported subset. Fewer histories and excluding flagged dates both change local inputs, so differences do not isolate a causal effect of ice or a particular observation.',
  'limitations':'Posthoc, same station, target years and outcomes previously opened; no independent-climate, sensor-accuracy, actual physical error or release guarantee. Raw qualifiers may indicate different kinds of uncertainty or processing rather than incorrect values.',
  }
 dest.write_text(json.dumps(plan,indent=2)+'\n');print('Frozen all-eight-target qualifier-aware history sensitivity')
def run():
 p=json.loads((STAGE/'qualifier_aware_history_plan.json').read_text())
 r=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str});meta=pd.read_csv(USGS/'cohort_metadata.csv',dtype={'station_id':str}).set_index('station_id');parser=T.load_script('qualifier_history_original',ROOT/'scripts/871_usgs_partial_daily_feasibility.py');records=[];data=[];detail=[]
 for site in sorted(r.station_id.unique()):
  daily=parser.valid_daily(pd.read_parquet(DATA/'daily'/(site+'.parquet')))
  with gzip.open(DATA/'raw'/(site+'.json.gz'),'rt') as f:doc=json.load(f)
  props=[x.get('properties',x) for x in doc['features']];date=native_daily_dates([x['time'] for x in props],meta.loc[site,'native_zone']);flagged={d for d,x in zip(date,props) if not blank(x.get('qualifier'))}
  strict=daily.copy();strict.loc[strict.index.isin(flagged)]=np.nan
  for day,value in strict.items():data.append({'station_id':site,'date':day,'water_c':value})
  for row in r[r.station_id.eq(site)].itertuples(index=False):
   target=strict.reindex(pd.date_range(f'{row.year}-01-01',f'{row.year}-12-31'));target_complete=bool(target.notna().all());original=[int(x) for x in row.history_years.split(';')];kept=[];excluded=[];actual_complete=0
   for year in original:
    idx=pd.date_range(f'{year}-01-01',f'{year}-12-31');before=daily.reindex(idx);after=strict.reindex(idx)
    if parser.history_ok(after):kept.append(year);actual_complete+=int(after.notna().all())
    else:excluded.append(year)
    detail.append({'station_id':site,'target_year':int(row.year),'history_year':year,'before_usable_days':int(before.notna().sum()),'after_usable_days':int(after.notna().sum()),
      'removed_qualified_days':int((before.notna()&after.isna()).sum()),'original_history_complete':bool(before.notna().all()),'qualifier_aware_history_complete':bool(after.notna().all()),'retained':parser.history_ok(after)})
   records.append({'station_id':site,'year':int(row.year),'history_years':';'.join(map(str,kept)),'original_history_years':row.history_years,
      'excluded_history_years':';'.join(map(str,excluded)),'eligible_histories':len(kept),'complete_history_years':actual_complete,
      'target_daily_complete':target_complete,'eligible_partial_history':bool(target_complete and len(kept)>=3),'latitude':row.latitude,'longitude':row.longitude,'native_zone':row.native_zone,'huc2':str(row.huc2)})
 frame=pd.DataFrame(records);x=pd.DataFrame(detail);daily=pd.DataFrame(data);f=STAGE/'qualifier_aware_roster.csv';g=STAGE/'qualifier_aware_history_details.csv';v=STAGE/'qualifier_aware_daily.parquet';frame.to_csv(f,index=False);x.to_csv(g,index=False);daily.to_parquet(v,index=False)
 result={'status':'completed_qualifier_aware_feasibility','target_years':len(frame),'sites':int(frame.station_id.nunique()),'target_years_still_complete':int(frame.target_daily_complete.sum()),
   'target_years_with_three_histories':int(frame.eligible_partial_history.sum()),'target_years_with_history_exclusions':int(frame.excluded_history_years.fillna('').ne('').sum()),
   'history_year_assignments_excluded':int((~x.retained).sum()),'history_assignment_flagged_days_removed':int(x.removed_qualified_days.sum()),
   'model_predictions_calculated':False,'limitations':p['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'qualifier_aware_history_status.json').write_text(json.dumps(result,indent=2)+'\n');print(frame.to_string(index=False));print(json.dumps(result,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
