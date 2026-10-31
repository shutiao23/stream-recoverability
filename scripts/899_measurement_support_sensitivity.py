#!/usr/bin/env python3
"""Source-recalibrated tolerance sensitivity for observation support."""
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
import argparse,json,sys
from datetime import datetime,timezone
from pathlib import Path
import joblib,numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');sys.path.insert(0,str(ROOT/'scripts'))
import wrr_tr_common as T, wrr_tr_features as F
from stream_recoverability.seeds import plain_seed
REV=ROOT/'results/wrr_review_response_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');LEVELS=np.asarray(F.QUANTILES);MARGINS=(0.,.01,.05,.2)
def freeze():
 path=STAGE/'measurement_support_plan.json'
 if path.exists():raise FileExistsError('Preserve support plan')
 for n in ['subdaily_h30_bounds_independent_audit.json','subdaily_bounded_score_independent_audit.json','reporting_resolution_independent_audit.json']:
  if json.loads((STAGE/n).read_text())['status']!='passed':raise ValueError('Prior audit incomplete')
 files=[SOURCE/'cases/leave_one_year_out/seed_00.parquet',SOURCE/'repairs/leave_one_year_out/seed_00.parquet',SOURCE/'deployment/global_source_candidate.joblib',
  REV/'external_bc_air2stream/source_calibration.json',ROOT/'scripts/466_review_completion_refit.py',ROOT/'scripts/467_review_completion_analysis.py',ROOT/'scripts/521_whole_archive.py',ROOT/'scripts/wrr_tr_features.py',
  STAGE/'scored_cases.parquet',STAGE/'score_status.json',STAGE/'subdaily_h30_bounds_years.csv',STAGE/'subdaily_h30_bounds_independent_audit.json',STAGE/'subdaily_bounded_score_independent_audit.json',STAGE/'reporting_resolution_independent_audit.json',STAGE/'continuous_qualification_days.parquet',Path(__file__)]
 p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after daily-versus-subdaily coverage, raw target observations and rounding-scale differences were inspected; not a prospective calibration',
  'goal':'Evaluate conditional, symmetric observation-support margins while recalibrating both D2 and stochastic source offsets for each margin. Do not present any selected margin as validated sensor error or deployable guarantee.',
  'support':'For a reported visible 30-day lower bound L, apply L-epsilon before and after quantile calibration to both methods. This changes the target support assumption: reported-daily H30 itself satisfies >=L, whereas a latent/continuous target satisfies >=L-epsilon only if daily value discrepancies are uniformly bounded by epsilon and clocks/measurements are comparable.',
  'margins_c':list(MARGINS),'margin_interpretation':'0, 0.01, 0.05 and 0.20 C are posthoc sensitivity values; not measured instrument tolerances. All available clean quarter-hour days have reported-versus-continuous discrepancies summarized separately; unmatched or corrected times remain unknown.',
  'calibration':'For each epsilon use the same positive-weight global source interval-calibration groups, bootstrap multiplicities, difficulty cells and fallback logic as the original source recalibration. Recompute both D2 and stochastic residual offsets using source reported daily H30; source reference is not latent temperature, so calibration transfer to continuous target is unproven. Models, masks, target histories and features are fixed.',
  'baseline':'At epsilon=0 all source calibration offsets and saved target quantiles must reproduce existing values; otherwise stop. No target observations or outcomes enter recalibration.',
  'evaluation':'On all 144 masks and posthoc full-hour subset of 54 masks, compare source-recalibrated 90% quantiles against conditional subdaily H30 intervals under fixed standard and local civil clocks: MAE bounds, definite/possible coverage, width, proper interval-score bounds, published-daily coverage and fraction of q05 below the unsoftened reported bound. Report plug-in unchanged for context. All three hourly years are one site.',
  'limitations':'Measurements, sensor accuracy, time alignment, source role exchangeability, independent climates, partial-history extrapolation and held-out pre-registration are unresolved. Changing support requires a changed estimand and measurement-error assumption, and the experiment is not a full operational recalibration or deployment safety assessment.',
  }
 path.write_text(json.dumps(p,indent=2)+'\n');print('Frozen posthoc source-recalibrated observation-support sensitivity')
def project(q,bound,epsilon):
 q=np.asarray(q,float);b=np.asarray(bound,float)-epsilon
 return np.where(np.isfinite(b[:,None]),np.maximum(q,b[:,None]),q)
def offset_vector(residual):return [float(np.quantile(residual[:,j],level,method='higher' if level>=.5 else 'lower')) for j,level in enumerate(LEVELS)]
def source_calibrate(source,refit,bundle,epsilon):
 source=source.loc[source.policy_choice.ne('unavailable')&source.eval_truth_h30.notna()].reset_index(drop=True)
 region='global_source_candidate';number=sorted(set(source.region.unique())|{region}).index(region);_,roles,weights=refit.roles(source,region,plain_seed(7,0,number))
 if roles!=bundle['roles']:raise ValueError('Global calibration roles differ')
 chosen=weights['interval_calibration']>0;cal=source.loc[chosen].copy();x=F.design_matrix(cal,simulation=True).reindex(columns=bundle['features']);raw=np.sort(np.column_stack([m.predict(x) for m in bundle['quantile_models']])+cal.h30__policy.to_numpy(float)[:,None],axis=1)
 raw=project(raw,cal.observed_lower_bound__observed_days,epsilon);d=refit.difficulty(cal);all_d=refit.difficulty(source);w=weights['interval_calibration'][chosen].astype(int);offsets={}
 for cell in sorted(all_d.unique()):
  pool=d.eq(cell).to_numpy()
  if pool.sum()<50:pool=np.ones(len(cal),bool)
  residual=np.repeat(cal.eval_truth_h30.to_numpy(float)[pool,None]-raw[pool],w[pool],axis=0);offsets[cell]=offset_vector(residual)
 all_d=refit.difficulty(source);q=source[[f'stochastic_h30_q{int(v*100):02d}' for v in LEVELS]].to_numpy(float);q=project(q,source.observed_lower_bound__observed_days,epsilon);valid=np.isfinite(q).all(axis=1);wfull=weights['interval_calibration'].astype(int);classical={}
 for cell in ['__pooled__',*sorted(all_d.unique())]:
  pool=(wfull>0)&valid
  if cell!='__pooled__' and (pool&all_d.eq(cell).to_numpy()).sum()>=50:pool &= all_d.eq(cell).to_numpy()
  if pool.sum()<2:raise ValueError('Insufficient source calibration')
  residual=np.repeat(source.eval_truth_h30.to_numpy(float)[pool,None]-q[pool],wfull[pool],axis=0);classical[cell]=offset_vector(residual)
 return {'D2_offsets':offsets,'stochastic_offsets':classical,'source_calibration_cases':int(chosen.sum()),'source_calibration_groups':int(cal.independence_group.nunique()),'source_calibration_total_weight':int(w.sum())}
def calibrate():
 p=json.loads((STAGE/'measurement_support_plan.json').read_text())
 out=STAGE/'measurement_support_calibrations.json'
 if out.exists():raise FileExistsError('Preserve recalibration results')
 refit=T.load_script('usgs_measurement_refit',ROOT/'scripts/466_review_completion_refit.py');analysis=T.load_script('usgs_measurement_repairs',ROOT/'scripts/467_review_completion_analysis.py');source=pd.read_parquet(SOURCE/'cases/leave_one_year_out/seed_00.parquet');source=analysis.apply_bridge_repairs(source,0,'leave_one_year_out');bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib');saved=json.loads((REV/'external_bc_air2stream/source_calibration.json').read_text());versions={}
 for eps in MARGINS:
  x=source_calibrate(source,refit,bundle,eps);versions[str(eps)]=x;print('Source-recalibrated epsilon',eps,flush=True)
 base=versions['0.0']
 for key,old in [('D2_offsets',saved['D2_offsets']),('stochastic_offsets',saved['offsets']['stochastic'])]:
  if set(base[key])!=set(old):raise AssertionError('Baseline calibration cells differ')
  for k,v in old.items():
   if not np.allclose(base[key][k],v,atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Zero-margin source offsets differ: '+key+' '+k)
 out.write_text(json.dumps(versions,indent=2)+'\n');status={'status':'completed_source_only_recalibration','margins_c':list(MARGINS),'baseline_offsets_match_saved':True,
  'source_calibration_cases':base['source_calibration_cases'],'source_calibration_groups':base['source_calibration_groups'],'source_calibration_total_weight':base['source_calibration_total_weight'],
  'target_values_used_for_calibration':False,'limitations':p['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'measurement_support_calibration_status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))
def target_predict(c,bundle,refit,cal,eps):
 x=F.design_matrix(c,simulation=True).reindex(columns=bundle['features']);d=refit.difficulty(c);bound=c.observed_lower_bound__observed_days.to_numpy(float);point=c.h30__policy.to_numpy(float)
 raw=np.sort(np.column_stack([m.predict(x) for m in bundle['quantile_models']])+point[:,None],axis=1);q=project(raw,bound,eps)
 for key in d.unique():
  if key not in cal['D2_offsets']:raise ValueError('Unsupported D2 cell')
  q[d.eq(key).to_numpy()]+=np.asarray(cal['D2_offsets'][key])
 q=project(np.sort(q,axis=1),bound,eps)
 classical=c[[f'stochastic_h30_q{int(v*100):02d}' for v in LEVELS]].to_numpy(float);classical=project(classical,bound,eps)
 for key in d.unique():
  classical[d.eq(key).to_numpy()]+=np.asarray(cal['stochastic_offsets'].get(key,cal['stochastic_offsets']['__pooled__']))
 classical=project(np.sort(classical,axis=1),bound,eps)
 return q,classical
def score():
 p=json.loads((STAGE/'measurement_support_plan.json').read_text())
 status=json.loads((STAGE/'measurement_support_calibration_status.json').read_text());calfile=STAGE/'measurement_support_calibrations.json'
 if status['status']!='completed_source_only_recalibration':raise ValueError('Recalibration missing or changed')
 versions=json.loads(calfile.read_text());c=pd.read_parquet(STAGE/'scored_cases.parquet');refit=T.load_script('usgs_measurement_target_refit',ROOT/'scripts/466_review_completion_refit.py');bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib');byclock=pd.read_csv(STAGE/'subdaily_h30_bounds_years.csv',dtype={'station_id':str});summary=[];details=[]
 for eps in MARGINS:
  d2,stoch=target_predict(c,bundle,refit,versions[str(eps)],eps)
  if eps==0:
   for arr,prefix in [(d2,'D2'),(stoch,'stochastic_cal')]:
    cols=[f'{prefix}_q{int(x*100):02d}' for x in LEVELS]
    if not np.allclose(arr,c[cols].to_numpy(float),atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Zero-margin target quantiles do not reproduce saved baseline '+prefix)
  c['tolerance_d2_q05']=d2[:,0];c['tolerance_d2_q50']=d2[:,3];c['tolerance_d2_q95']=d2[:,-1];c['tolerance_stochastic_q05']=stoch[:,0];c['tolerance_stochastic_q50']=stoch[:,3];c['tolerance_stochastic_q95']=stoch[:,-1]
  for clock in ['fixed_standard','native_civil']:
   b=byclock[byclock.clock.eq(clock)][['station_id','year','h30_lower_c','h30_upper_c']];x=c.merge(b,on=['station_id','year'],validate='many_to_one')
   for cohort,mask in [('all',np.ones(len(x),bool)),('fixed_standard_full_hour_posthoc',x.hourly_reference_posthoc.to_numpy(bool))]:
    z=x.loc[mask];L=z.h30_lower_c.to_numpy(float);U=z.h30_upper_c.to_numpy(float);published=z.reference_h30.to_numpy(float);bound=z.observed_lower_bound__observed_days.to_numpy(float)
    for method in ['D2','stochastic']:
     prefix='tolerance_d2' if method=='D2' else 'tolerance_stochastic';lo=z[prefix+'_q05'].to_numpy(float);point=z[prefix+'_q50'].to_numpy(float);hi=z[prefix+'_q95'].to_numpy(float);valid=np.isfinite(lo)&np.isfinite(point)&np.isfinite(hi)&np.isfinite(L)&np.isfinite(U)
     lo=lo[valid];point=point[valid];hi=hi[valid];l=L[valid];u=U[valid];y=published[valid];bb=bound[valid];w=hi-lo
     lower=np.maximum.reduce([l-point,np.zeros(len(point)),point-u]);upper=np.maximum(abs(point-l),abs(point-u));isl=w+20*np.maximum.reduce([lo-u,l-hi,np.zeros(len(point))]);isu=np.maximum(w+20*np.maximum(lo-l,0)+20*np.maximum(l-hi,0),w+20*np.maximum(lo-u,0)+20*np.maximum(u-hi,0))
     summary.append({'epsilon_c':eps,'clock':clock,'cohort':cohort,'method':method,'cases':len(z),'valid_cases':int(valid.sum()),'sites':z.loc[valid,'station_id'].nunique(),'station_years':len(z.loc[valid,['station_id','year']].drop_duplicates()),
       'mae_lower_c':float(lower.mean()),'mae_upper_c':float(upper.mean()),'coverage_definite':float(((lo<=l)&(hi>=u)).mean()),'coverage_possible':float(((lo<=u)&(hi>=l)).mean()),'width90':float(w.mean()),
       'interval_score_lower':float(isl.mean()),'interval_score_upper':float(isu.mean()),'reported_daily_coverage90':float(((lo<=y)&(hi>=y)).mean()),
       'q05_below_reported_bound_cases':int((np.isfinite(bb)&(lo<bb-1e-9)).sum()),'q50_below_reported_bound_cases':int((np.isfinite(bb)&(point<bb-1e-9)).sum())})
   x['support_margin_c']=eps;x['continuous_clock']=clock;details.append(x)
 table=pd.DataFrame(summary);table.to_csv(STAGE/'measurement_support_summary.csv',index=False);f=STAGE/'measurement_support_cases.parquet';pd.concat(details,ignore_index=True).to_parquet(f,index=False)
 qdays=pd.read_parquet(STAGE/'continuous_qualification_days.parquet');comparisons=[]
 for clock in ['fixed_standard','native_civil']:
  z=qdays[qdays.clock.eq(clock)];diff=(z.subdaily_mean-z.published_daily).abs().dropna();comparisons.append({'clock':clock,'paired_complete_quarter_days':len(diff),
    **{f'days_above_{str(eps).replace(".","_")}_c':int((diff>eps+1e-10).sum()) for eps in MARGINS},'max_abs_daily_difference_c':float(diff.max())})
 pd.DataFrame(comparisons).to_csv(STAGE/'measurement_daily_difference_counts.csv',index=False)
 result={'status':'completed_posthoc_source_recalibrated_support_sensitivity','margins_c':list(MARGINS),'target_cases':len(c),'summary_rows':len(table),
  'baseline_offsets_and_target_quantiles_reproduced':True,'target_values_used_for_calibration':False,
  'limitations':p['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'measurement_support_status.json').write_text(json.dumps(result,indent=2)+'\n');print(table.to_string(index=False));print(pd.DataFrame(comparisons).to_string(index=False));print(json.dumps(result,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','calibrate','score']);x=a.parse_args();{'freeze':freeze,'calibrate':calibrate,'score':score}[x.action]()
