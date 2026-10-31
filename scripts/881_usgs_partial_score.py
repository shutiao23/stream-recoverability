#!/usr/bin/env python3
"""Score all USGS daily targets and posthoc subdaily-support subsets."""
import argparse,json,sys
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');sys.path.insert(0,str(ROOT/'scripts'))
import wrr_tr_common as T
OUT=ROOT/'results/wrr_review_response_20261027/external_usgs_partial_daily';DATA=ROOT/'data/external/additional_usgs_observed';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
def freeze():
 dest=STAGE/'score_execution_plan.json'
 if dest.exists():raise FileExistsError('Preserve scoring execution plan')
 pred=json.loads((STAGE/'predictions_status.json').read_text());probe=json.loads((STAGE/'hidden_probe_status.json').read_text())
 if pred['status']!='predictions_complete_not_scored' or probe['status']!='passed':raise ValueError('Predictions or probe incomplete')
 roster=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str});receipts={}
 for r in roster.itertuples(index=False):
  d=STAGE/'predictions'/r.station_id/str(r.year);info=json.loads((d/'receipt.json').read_text())
 path=STAGE/'score_receipts.json';path.write_text(json.dumps(receipts,indent=2,sort_keys=True)+'\n')
 from datetime import datetime,timezone
 p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after previously opened daily outcomes and observed continuous qualification; before computing model errors in this experiment',
   'cohort':'All eight fixed years and their target masks, with unavailable outputs retained; separately report fixed-standard full-hour support and full-quarter support as posthoc subsets. Every hourly-supported year belongs to one site, so masks/years are not independent climates.',
   'metrics':'Against complete reported approved daily H30 calculate point MAE, bias, failure>0.5 C, availability, D2/stochastic 90% interval coverage, width and interval score; use common finite cases for comparisons and preserve per-year results. Also compare published H30 with fixed-standard and civil 15-minute H30 where every day has full quarter support; this is a clock/measurement sensitivity, not a substitute ground truth.',
   'limitations':'Daily values were inspected in earlier witness analysis and continuous availability has been inspected. Daily means may contain unflagged corrections or variable subdaily support. Partial-history interpolation and only 0-2 complete training years are out-of-support for the fixed source model. Station identity/source overlap, climate independence and NASA-water daily alignment remain unresolved. Synthetic masks repeat the same years.',
   }
 dest.write_text(json.dumps(p,indent=2)+'\n');print('Frozen complete-cohort and posthoc subdaily-support scoring')
def run():
 p=json.loads((STAGE/'score_execution_plan.json').read_text())
 helper=T.load_script('usgs_partial_score_parser',ROOT/'scripts/871_usgs_partial_daily_feasibility.py');roster=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str});receipts=json.loads((STAGE/'score_receipts.json').read_text());q=pd.read_csv(STAGE/'continuous_qualification_years.csv',dtype={'station_id':str});fixed=q[q.clock.eq('fixed_standard')].set_index(['station_id','year']);civil=q[q.clock.eq('native_civil')].set_index(['station_id','year']);refdaily=pd.read_parquet(STAGE/'continuous_qualification_days.parquet');refdaily.day=pd.to_datetime(refdaily.day)
 pieces=[];yeartruth=[]
 for r in roster.itertuples(index=False):
  d=STAGE/'predictions'/r.station_id/str(r.year);rec=json.loads((d/'receipt.json').read_text())
  s=helper.valid_daily(pd.read_parquet(DATA/'daily'/(r.station_id+'.parquet')));idx=pd.date_range(f'{r.year}-01-01',f'{r.year}-12-31');values=s.reindex(idx)
  if not np.isfinite(values).all():raise ValueError('Target truth not fully observed')
  truth=float(values.rolling(30,min_periods=30).mean().max());x=pd.read_parquet(d/'predictions.parquet');x['station_id']=r.station_id;x['reference_h30']=truth
  fq=fixed.loc[(r.station_id,r.year)];cq=civil.loc[(r.station_id,r.year)];x['hourly_reference_posthoc']=bool(fq.hourly_complete_year);x['quarter_reference_posthoc']=bool(fq.quarter_complete_year)
  b=x.observed_lower_bound__observed_days.to_numpy(float)
  if np.any(np.isfinite(b)&(b>truth+1e-9)):raise ValueError('Observed lower bound contradicts daily truth')
  pieces.append(x);row={'station_id':r.station_id,'year':r.year,'published_daily_h30':truth,'fixed_hourly_complete':bool(fq.hourly_complete_year),'fixed_quarter_complete':bool(fq.quarter_complete_year),'civil_hourly_complete':bool(cq.hourly_complete_year),'civil_quarter_complete':bool(cq.quarter_complete_year)}
  for clock,complete in [('fixed_standard',fq.quarter_complete_year),('native_civil',cq.quarter_complete_year)]:
   if complete:
    z=refdaily[(refdaily.station_id.eq(r.station_id))&refdaily.year.eq(r.year)&refdaily.clock.eq(clock)].sort_values('day');v=z.subdaily_mean.to_numpy(float)
    if len(v)!=len(idx) or not np.isfinite(v).all():raise ValueError('Subdaily full reference changed')
    row[clock+'_continuous_h30']=float(pd.Series(v).rolling(30,min_periods=30).mean().max());row[clock+'_minus_published_h30']=row[clock+'_continuous_h30']-truth
  yeartruth.append(row)
 frame=pd.concat(pieces,ignore_index=True);methods={'plug_in':'h30__policy','D2':'D2','stochastic':'stochastic_cal_q50'}
 common=np.logical_and.reduce([np.isfinite(pd.to_numeric(frame[col],errors='coerce')) for col in methods.values()]);frame['common']=common
 summary=[];byyear=[];pairs=[]
 for cohort,sel in [('all',np.ones(len(frame),bool)),('fixed_standard_full_hour_posthoc',frame.hourly_reference_posthoc.to_numpy(bool)),('fixed_standard_full_quarter_posthoc',frame.quarter_reference_posthoc.to_numpy(bool))]:
  z=frame.loc[sel];commonz=z[z.common]
  for name,col in methods.items():
   finite=np.isfinite(pd.to_numeric(z[col],errors='coerce'));g=commonz;y=g.reference_h30.to_numpy(float);v=g[col].to_numpy(float);err=v-y
   row={'cohort':cohort,'method':name,'cases':len(z),'available':int(finite.sum()),'common_cases':len(g),'sites':int(g.station_id.nunique()),'station_years':len(g[['station_id','year']].drop_duplicates()),'mae':float(np.mean(np.abs(err))) if len(err) else np.nan,'bias':float(np.mean(err)) if len(err) else np.nan,'failure_rate':float(np.mean(np.abs(err)>.5)) if len(err) else np.nan}
   if name!='plug_in':
    pref='D2' if name=='D2' else 'stochastic_cal';lo=g[pref+'_q05'].to_numpy(float);hi=g[pref+'_q95'].to_numpy(float);valid=np.isfinite(lo)&np.isfinite(hi)
    row.update(interval_cases=int(valid.sum()),coverage90=float(np.mean((lo[valid]<=y[valid])&(y[valid]<=hi[valid]))) if valid.any() else np.nan,
      width90=float(np.mean(hi[valid]-lo[valid])) if valid.any() else np.nan,
      interval_score90=float(np.mean(hi[valid]-lo[valid]+20*np.maximum(lo[valid]-y[valid],0)+20*np.maximum(y[valid]-hi[valid],0))) if valid.any() else np.nan)
   summary.append(row)
  if len(commonz):
   y=commonz.reference_h30.to_numpy(float);d=np.abs(commonz.D2.to_numpy(float)-y)
   for name in ['plug_in','stochastic']:
    diff=d-np.abs(commonz[methods[name]].to_numpy(float)-y);pairs.append({'cohort':cohort,'contrast':'D2_minus_'+name,'common_cases':len(diff),'mean_absolute_error_difference_c':float(diff.mean())})
 for (site,year),g in frame[frame.common].groupby(['station_id','year'],sort=True):
  y=g.reference_h30.to_numpy(float)
  for name,col in methods.items():byyear.append({'station_id':site,'year':year,'method':name,'cases':len(g),'mae':float(np.abs(g[col].to_numpy(float)-y).mean())})
 pd.DataFrame(summary).to_csv(STAGE/'score_summary.csv',index=False);pd.DataFrame(pairs).to_csv(STAGE/'score_pairs.csv',index=False);pd.DataFrame(byyear).to_csv(STAGE/'score_by_year.csv',index=False);pd.DataFrame(yeartruth).to_csv(STAGE/'reference_clock_comparison.csv',index=False);frame.to_parquet(STAGE/'scored_cases.parquet',index=False)
 out={'status':'completed_posthoc_daily_reference_scoring','sites':int(frame.station_id.nunique()),'target_years':len(roster),'cases':len(frame),'common_cases':int(common.sum()),'strict_independent_climate_validated':False,'original_complete_history_protocol':False,'target_daily_reported_not_physical_truth':True,
  'limitations':p['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'score_status.json').write_text(json.dumps(out,indent=2)+'\n');print(pd.DataFrame(summary).to_string(index=False));print(pd.DataFrame(pairs).to_string(index=False));print(json.dumps(out,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
