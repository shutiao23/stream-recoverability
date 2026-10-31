#!/usr/bin/env python3
"""Independently rebuild source offsets and conditional support-score summaries."""
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
import collections,json,math,sys
from pathlib import Path
import joblib,numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');sys.path.insert(0,str(ROOT/'scripts'))
import wrr_tr_common as T, wrr_tr_features as F
from stream_recoverability.seeds import plain_seed
REV=ROOT/'results/wrr_review_response_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');LEVELS=np.asarray(F.QUANTILES);EPS=[0.,.01,.05,.2]
def counts_offset(errors,weights):
 expanded=np.repeat(errors,weights.astype(int),axis=0);out=[]
 for j,p in enumerate(LEVELS):
  z=np.sort(expanded[:,j]);n=len(z);k=math.ceil((n-1)*p) if p>=.5 else math.floor((n-1)*p);out.append(float(z[k]))
 return np.array(out)
def difficulty(c):
 overlap=c.peak_overlap.to_numpy(float);bins=np.where(overlap<=0,0,np.searchsorted([0,.25,.5,.75,1],overlap,side='left'));layer=c.policy_choice.where(c.policy_choice.isin(['air_ridge','donor_ridge']),'other').astype(str)
 return np.asarray([f'{a}|{b}' for a,b in zip(bins,layer)])
def project(q,lower,eps):
 result=np.array(q,copy=True);b=np.asarray(lower,float)-eps;good=np.isfinite(b);result[good]=np.maximum(result[good],b[good,None]);return result
def main():
 plan=json.loads((STAGE/'measurement_support_plan.json').read_text());s=json.loads((STAGE/'measurement_support_status.json').read_text());calstatus=json.loads((STAGE/'measurement_support_calibration_status.json').read_text())
 calfile=STAGE/'measurement_support_calibrations.json'
 stored=json.loads(calfile.read_text());source=pd.read_parquet(SOURCE/'cases/leave_one_year_out/seed_00.parquet');repair=T.load_script('support_audit_repair',ROOT/'scripts/467_review_completion_analysis.py');source=repair.apply_bridge_repairs(source,0,'leave_one_year_out');source=source.loc[source.policy_choice.ne('unavailable')&source.eval_truth_h30.notna()].reset_index(drop=True)
 if 'training_partition' in source:raise ValueError('Unexpected partition')
 config=json.loads((ROOT/'configs/wrr_review_completion_20261024.json').read_text());bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib');groups=np.array(sorted(source.independence_group.unique()));region='global_source_candidate';number=sorted(set(source.region.unique())|{region}).index(region);rng=np.random.default_rng(plain_seed(7,0,number));rng.shuffle(groups);cuts=np.maximum.accumulate(np.round(np.cumsum(config['fit_role_shares'])[:-1]*len(groups)).astype(int));parts=np.split(groups,cuts)
 role={k:list(map(str,v)) for k,v in zip(config['fit_role_names'],parts)}
 if role!=bundle['roles']:raise AssertionError('Independent source roles differ')
 weights={}
 for name,part in zip(config['fit_role_names'],parts):
  freq=collections.Counter(rng.choice(part,len(part),replace=True).tolist());weights[name]=source.independence_group.map(freq).fillna(0).to_numpy(int)
 selected=weights['interval_calibration']>0;cal=source.loc[selected];cw=weights['interval_calibration'][selected];dcal=difficulty(cal);dall=difficulty(source);X=F.design_matrix(cal,simulation=True).reindex(columns=bundle['features']);raw=np.column_stack([m.booster_.predict(X,num_threads=1) for m in bundle['quantile_models']])+cal.h30__policy.to_numpy(float)[:,None];raw=np.sort(raw,axis=1)
 all_stoch=source[[f'stochastic_h30_q{int(q*100):02d}' for q in LEVELS]].to_numpy(float);source_truth=source.eval_truth_h30.to_numpy(float);target=pd.read_parquet(STAGE/'scored_cases.parquet');Xtarget=F.design_matrix(target,simulation=True).reindex(columns=bundle['features']);target_raw=np.sort(np.column_stack([m.booster_.predict(Xtarget,num_threads=1) for m in bundle['quantile_models']])+target.h30__policy.to_numpy(float)[:,None],axis=1);target_d=difficulty(target);stored_cases=pd.read_parquet(STAGE/'measurement_support_cases.parquet');summary=pd.read_csv(STAGE/'measurement_support_summary.csv');bound_table=pd.read_csv(STAGE/'subdaily_h30_bounds_years.csv',dtype={'station_id':str});checked_offsets=0;checked_target_rows=0
 for eps in EPS:
  dq=project(raw,cal.observed_lower_bound__observed_days,eps);d_offsets={}
  for cell in sorted(set(dall)):
   use=dcal==cell
   if use.sum()<50:use=np.ones(len(cal),bool)
   d_offsets[cell]=counts_offset(cal.eval_truth_h30.to_numpy(float)[use,None]-dq[use],cw[use])
  sq=project(all_stoch,source.observed_lower_bound__observed_days,eps);valid=np.isfinite(sq).all(axis=1);s_offsets={}
  for cell in ['__pooled__',*sorted(set(dall))]:
   use=(weights['interval_calibration']>0)&valid
   if cell!='__pooled__' and (use&(dall==cell)).sum()>=50:use &= dall==cell
   s_offsets[cell]=counts_offset(source_truth[use,None]-sq[use],weights['interval_calibration'][use])
  saved=stored[str(eps)]
  for key,computed in [('D2_offsets',d_offsets),('stochastic_offsets',s_offsets)]:
   if set(computed)!=set(saved[key]):raise AssertionError('Calibration cell mismatch')
   for cell,v in computed.items():
    if not np.allclose(v,saved[key][cell],atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Calibration mismatch '+key+' '+cell)
    checked_offsets+=len(v)
  low=target.observed_lower_bound__observed_days.to_numpy(float);dq=project(target_raw,low,eps);sq=project(target[[f'stochastic_h30_q{int(q*100):02d}' for q in LEVELS]].to_numpy(float),low,eps)
  for cell in sorted(set(target_d)):
   use=target_d==cell;dq[use]+=d_offsets[cell];sq[use]+=s_offsets.get(cell,s_offsets['__pooled__'])
  dq=project(np.sort(dq,axis=1),low,eps);sq=project(np.sort(sq,axis=1),low,eps)
  for clock in ['fixed_standard','native_civil']:
   actual=stored_cases[stored_cases.support_margin_c.eq(eps)&stored_cases.continuous_clock.eq(clock)].reset_index(drop=True)
   if len(actual)!=len(target) or not actual[['station_id','year','realization_id']].equals(target[['station_id','year','realization_id']].reset_index(drop=True)):raise AssertionError('Target cases mismatch')
   for values,prefix in [(dq,'tolerance_d2'),(sq,'tolerance_stochastic')]:
    if not np.allclose(values[:,[0,3,6]],actual[[prefix+'_q05',prefix+'_q50',prefix+'_q95']],atol=1e-9,rtol=0,equal_nan=True):raise AssertionError('Target recalibrated quantiles differ')
   ref=bound_table[bound_table.clock.eq(clock)].set_index(['station_id','year']);expected=[]
   for row in target.itertuples(index=False):
    t=ref.loc[(row.station_id,row.year)];expected.append((float(t.h30_lower_c),float(t.h30_upper_c)))
   refs=np.asarray(expected);L,U=refs[:,0],refs[:,1]
   if not np.allclose(actual.h30_lower_c,L,atol=1e-10) or not np.allclose(actual.h30_upper_c,U,atol=1e-10):raise AssertionError('Reference join differs')
   for cohort,mask in [('all',np.ones(len(target),bool)),('fixed_standard_full_hour_posthoc',target.hourly_reference_posthoc.to_numpy(bool))]:
    for method,arr in [('D2',dq),('stochastic',sq)]:
     i=np.flatnonzero(mask);lo,point,hi=arr[i,0],arr[i,3],arr[i,6];l,u=L[i],U[i];published=target.reference_h30.to_numpy(float)[i];reported_bound=low[i];valid=np.isfinite(lo)&np.isfinite(point)&np.isfinite(hi)&np.isfinite(l)&np.isfinite(u)
     lo,point,hi,l,u,published,reported_bound=[z[valid] for z in [lo,point,hi,l,u,published,reported_bound]];errors=[];scores=[]
     for aa,bb,x,y,z in zip(l,u,point,lo,hi):
      emin=0. if aa<=x<=bb else min(abs(x-aa),abs(x-bb));emax=max(abs(x-aa),abs(x-bb));width=z-y
      def interval_score(t):return width+20*max(y-t,0)+20*max(t-z,0)
      knots=[aa,bb,min(max(y,aa),bb),min(max(z,aa),bb)];errors.append((emin,emax));scores.append((min(interval_score(t) for t in knots),max(interval_score(aa),interval_score(bb))))
     errors=np.asarray(errors);scores=np.asarray(scores);row=summary[(summary.epsilon_c.eq(eps))&summary.clock.eq(clock)&summary.cohort.eq(cohort)&summary.method.eq(method)].iloc[0]
     checks={'cases':len(i),'valid_cases':len(lo),'sites':target.iloc[i[valid]].station_id.nunique(),'station_years':len(target.iloc[i[valid]][['station_id','year']].drop_duplicates()),'mae_lower_c':errors[:,0].mean(),'mae_upper_c':errors[:,1].mean(),'coverage_definite':np.mean((lo<=l)&(hi>=u)),
       'coverage_possible':np.mean((lo<=u)&(hi>=l)),'width90':np.mean(hi-lo),'interval_score_lower':scores[:,0].mean(),'interval_score_upper':scores[:,1].mean(),
       'reported_daily_coverage90':np.mean((lo<=published)&(hi>=published)),'q05_below_reported_bound_cases':int((np.isfinite(reported_bound)&(lo<reported_bound-1e-9)).sum()),'q50_below_reported_bound_cases':int((np.isfinite(reported_bound)&(point<reported_bound-1e-9)).sum())}
     for key,value in checks.items():
      if not np.isclose(value,row[key],atol=1e-9,rtol=0,equal_nan=True):raise AssertionError('Score mismatch '+str(eps)+' '+clock+' '+cohort+' '+method+' '+key)
     checked_target_rows+=1
 qdays=pd.read_parquet(STAGE/'continuous_qualification_days.parquet');diff=pd.read_csv(STAGE/'measurement_daily_difference_counts.csv').set_index('clock')
 for clock in ['fixed_standard','native_civil']:
  z=qdays[qdays.clock.eq(clock)];a=(z.subdaily_mean-z.published_daily).abs().dropna();r=diff.loc[clock]
  if len(a)!=r.paired_complete_quarter_days or not np.isclose(a.max(),r.max_abs_daily_difference_c,atol=1e-10):raise AssertionError('Daily differences mismatch')
  for eps in EPS:
   k=f'days_above_{str(eps).replace(".","_")}_c'
   if int((a>eps+1e-10).sum())!=int(r[k]):raise AssertionError('Daily tolerance count mismatch')
 out={'status':'passed','source_calibration_cases':int(selected.sum()),'source_calibration_groups':int(cal.independence_group.nunique()),'weighted_offset_values_checked':checked_offsets,'target_summary_cells_checked':checked_target_rows,
  'scope':'Independent group bootstrap-multiplicity reconstruction, sorted order-statistic source offsets, Booster quantiles, conditional error/coverage/interval-score formulas and observed daily differences.',
  'limitations':plan['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'measurement_support_independent_audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
