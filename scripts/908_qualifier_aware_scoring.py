#!/usr/bin/env python3
"""Score original versus qualifier-aware USGS histories on fixed masks."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np,pandas as pd
STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');METHODS={'plug_in':'h30__policy','D2':'D2','stochastic':'stochastic_cal_q50'}
def inputs():
 status=json.loads((STAGE/'qualifier_aware_prediction_status.json').read_text());receipt=STAGE/'qualifier_aware_prediction_receipts.json'
 if status['status']!='completed_predictions_not_scored':raise ValueError('Alternative predictions not complete')
 for item in json.loads(receipt.read_text()):
  if item['status']=='completed':
   d=STAGE/'qualifier_aware_predictions'/item['station_id']/str(item['year'])
 return status

def freeze():
 path=STAGE/'qualifier_aware_score_plan.json'
 if path.exists():raise FileExistsError('Preserve alternative score plan')
 status=inputs()
 for name in ['score_independent_audit.json','subdaily_h30_bounds_independent_audit.json']:
  if json.loads((STAGE/name).read_text())['status']!='passed':raise ValueError('Reference audit incomplete')
 files=[STAGE/'scored_cases.parquet',STAGE/'score_status.json',STAGE/'score_independent_audit.json',STAGE/'subdaily_h30_bounds_years.csv',STAGE/'subdaily_h30_bounds_independent_audit.json',
   STAGE/'qualifier_aware_roster_v2.csv',STAGE/'qualifier_aware_prediction_plan.json',STAGE/'qualifier_aware_prediction_status.json',STAGE/'qualifier_aware_prediction_receipts.json',Path(__file__)]
 p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after baseline target scores, reported/subdaily reference discrepancies and ICE qualifier results; before alternative error summaries',
  'cohort':'All original eight target years and exact 144 original target masks. Report absent or unavailable alternative predictions and use the same finite cases for paired comparisons. Separately retain the previously selected three Rio Mora fixed-standard full-hour years.',
  'intervention':'Retain original versus all-nonempty-qualifier-excluded historical daily values, reapply history eligibility and refit local daily components. No source model or calibration is retrained; removing years and input values together prevents causal attribution to ice alone.',
  'reference':'Reported daily H30 is a fixed observed-series reference. Also report conditional error and 90% coverage bounds against the prior two-clock quarter-hour H30 enclosure under hypothetical [-5,50] C missing-slot values; these are different estimands.',
  'metrics':'For each history version, method and cohort calculate common-case MAE, bias, >0.5 C failures, 90% coverage, interval width and interval score against reported H30; for D2 report paired MAE change and per-year outcomes. For continuous H30 report MAE lower/upper and definite/possible coverage. No bootstrap because three Rio Mora years share one station.',
  'limitations':'Posthoc after outcomes and qualifiers, one site is affected by removing histories, three years belong to one river, target time/quality and source-network overlap are unresolved; no independent-climate accuracy, sensor error or risk guarantee. A qualifier does not prove a value is wrong.',
  }
 path.write_text(json.dumps(p,indent=2)+'\n');print('Frozen all-eight-target qualifier-aware score comparison')
def run():
 p=json.loads((STAGE/'qualifier_aware_score_plan.json').read_text())
 status=inputs();old=pd.read_parquet(STAGE/'scored_cases.parquet');new=[]
 for r in json.loads((STAGE/'qualifier_aware_prediction_receipts.json').read_text()):
  if r['status']=='completed':new.append(pd.read_parquet(STAGE/'qualifier_aware_predictions'/r['station_id']/str(r['year'])/'predictions.parquet'))
 new=pd.concat(new,ignore_index=True);keys=['station_id','year','realization_id'];combined=old.merge(new,on=keys,how='outer',suffixes=('_old','_new'),validate='one_to_one',indicator=True)
 if not combined._merge.eq('both').all() or not combined.mask_runs_old.eq(combined.mask_runs_new).all():raise ValueError('Target identities or masks changed')
 if not np.allclose(combined.observed_lower_bound__observed_days_old,combined.observed_lower_bound__observed_days_new,atol=1e-10,rtol=0,equal_nan=True):raise ValueError('Target observation bounds changed')
 for col in METHODS.values():combined=combined[np.isfinite(pd.to_numeric(combined[col+'_old'],errors='coerce'))&np.isfinite(pd.to_numeric(combined[col+'_new'],errors='coerce'))]
 if combined.empty:raise ValueError('No common target cases')
 bounds=pd.read_csv(STAGE/'subdaily_h30_bounds_years.csv',dtype={'station_id':str});summary=[];paired=[];year_rows=[]
 for cohort,sel in [('all',np.ones(len(combined),bool)),('fixed_standard_full_hour_posthoc',combined.hourly_reference_posthoc.to_numpy(bool))]:
  z=combined.loc[sel];truth=z.reference_h30.to_numpy(float)
  for version,suffix in [('original','old'),('qualifier_aware','new')]:
   for name,col in METHODS.items():
    point=z[col+'_'+suffix].to_numpy(float);err=point-truth;row={'reference':'reported_daily','clock':'reported','cohort':cohort,'history':version,'method':name,'cases':len(z),'sites':z.station_id.nunique(),'target_years':len(z[['station_id','year']].drop_duplicates()),'mae_c':float(np.abs(err).mean()),'bias_c':float(err.mean()),'failure_rate':float((abs(err)>.5).mean())}
    if name!='plug_in':
     prefix='D2' if name=='D2' else 'stochastic_cal';lo=z[prefix+'_q05_'+suffix].to_numpy(float);hi=z[prefix+'_q95_'+suffix].to_numpy(float);ok=np.isfinite(lo)&np.isfinite(hi);y=truth[ok];lo=lo[ok];hi=hi[ok];row.update(interval_cases=int(ok.sum()),coverage90=float(((lo<=y)&(hi>=y)).mean()),width90_c=float((hi-lo).mean()),interval_score90=float((hi-lo+20*np.maximum(lo-y,0)+20*np.maximum(y-hi,0)).mean()))
    summary.append(row)
   for name,col in METHODS.items():
    difference=np.abs(z[col+'_new'].to_numpy(float)-truth)-np.abs(z[col+'_old'].to_numpy(float)-truth);paired.append({'cohort':cohort,'method':name,'cases':len(z),'mean_MAE_change_c':float(difference.mean())})
 for clock in ['fixed_standard','native_civil']:
  b=bounds[bounds.clock.eq(clock)][['station_id','year','h30_lower_c','h30_upper_c']];x=combined.merge(b,on=['station_id','year'],validate='many_to_one')
  for cohort,sel in [('all',np.ones(len(x),bool)),('fixed_standard_full_hour_posthoc',x.hourly_reference_posthoc.to_numpy(bool))]:
   z=x.loc[sel];L=z.h30_lower_c.to_numpy(float);U=z.h30_upper_c.to_numpy(float)
   for version,suffix in [('original','old'),('qualifier_aware','new')]:
    for name,col in METHODS.items():
     point=z[col+'_'+suffix].to_numpy(float);elo=np.maximum.reduce([L-point,np.zeros(len(z)),point-U]);ehi=np.maximum(abs(point-L),abs(point-U));row={'reference':'conditional_subdaily','clock':clock,'cohort':cohort,'history':version,'method':name,'cases':len(z),'sites':z.station_id.nunique(),'target_years':len(z[['station_id','year']].drop_duplicates()),'mae_lower_c':float(elo.mean()),'mae_upper_c':float(ehi.mean())}
     if name!='plug_in':
      prefix='D2' if name=='D2' else 'stochastic_cal';lo=z[prefix+'_q05_'+suffix].to_numpy(float);hi=z[prefix+'_q95_'+suffix].to_numpy(float);ok=np.isfinite(lo)&np.isfinite(hi);row.update(interval_cases=int(ok.sum()),coverage_definite=float(((lo[ok]<=L[ok])&(hi[ok]>=U[ok])).mean()),coverage_possible=float(((lo[ok]<=U[ok])&(hi[ok]>=L[ok])).mean()),width90_c=float((hi[ok]-lo[ok]).mean()))
     summary.append(row)
 for (site,year),z in combined.groupby(['station_id','year'],sort=True):
  y=z.reference_h30.to_numpy(float)
  for method,col in METHODS.items():year_rows.append({'station_id':site,'year':int(year),'method':method,'cases':len(z),'original_mae':float(abs(z[col+'_old'].to_numpy(float)-y).mean()),'qualifier_aware_mae':float(abs(z[col+'_new'].to_numpy(float)-y).mean())})
 f=STAGE/'qualifier_aware_score_summary.csv';g=STAGE/'qualifier_aware_score_pairs.csv';yy=STAGE/'qualifier_aware_score_by_year.csv';detail=STAGE/'qualifier_aware_scored_cases.parquet';pd.DataFrame(summary).to_csv(f,index=False);pd.DataFrame(paired).to_csv(g,index=False);pd.DataFrame(year_rows).to_csv(yy,index=False);combined.to_parquet(detail,index=False)
 out={'status':'completed_posthoc_qualifier_aware_comparison','target_years':len(combined[['station_id','year']].drop_duplicates()),'sites':combined.station_id.nunique(),'common_cases':len(combined),'unsupported_years':status['unsupported_years'],
   'limitations':p['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'qualifier_aware_score_status.json').write_text(json.dumps(out,indent=2)+'\n');print(pd.DataFrame(summary).to_string(index=False));print(pd.DataFrame(paired).to_string(index=False));print(json.dumps(out,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
