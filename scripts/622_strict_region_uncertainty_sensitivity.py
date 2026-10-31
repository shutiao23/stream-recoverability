#!/usr/bin/env python3
"""Recompute paired tail and joint-rank sensitivity under strict source exclusion."""
from __future__ import annotations
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import wrr_tr_common as T
from stream_recoverability.seeds import plain_seed
from stream_recoverability.experiments.tr_revision.archive import LEVELS,marginal_draws,reorder_marginals,slope
from stream_recoverability.experiments.tr_revision.statistics import interval_score

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';BASE=REV/'whole_archive';OUT=REV/'strict_region_holdout';PRIVATE=ROOT/'private/wrr_strict_region_holdout_20261026';SOURCE=ROOT/'results/wrr_review_completion_20261024'
KEY=['family','mode','estimator','station_key','replicate']
TRENDKEY=['family','mode','station_key','replicate','estimator','retention','dependence']
ANNUALKEY=['family','mode','station_key','replicate','estimator']
TAILKEY=KEY+['tails']


def replace(original,replacement,keys,affected):
 if original.duplicated(keys).any() or replacement.duplicated(keys).any():raise ValueError('duplicate replacement keys')
 paired=original.loc[affected].merge(replacement,on=keys,how='outer',indicator=True,validate='one_to_one')
 if not paired._merge.eq('both').all():raise ValueError('replacement keys differ')
 extra=set(replacement.columns)-set(original.columns)
 replacement=replacement.drop(columns=list(extra))
 return pd.concat([original.loc[~affected],replacement.reindex(columns=original.columns)],ignore_index=True)


def group_bootstrap_difference(groups, differences, draws=2000, seed=622):
    """Paired case-weighted differences, resampling connected groups together."""
    frame=pd.DataFrame({'group':np.asarray(groups),'difference':np.asarray(differences,float)})
    if frame.group.isna().any() or not np.isfinite(frame.difference).all() or frame.empty:
        raise ValueError('invalid paired bootstrap inputs')
    totals=frame.groupby('group',sort=True).difference.agg(['sum','size'])
    selected=np.random.default_rng(seed).integers(0,len(totals),size=(draws,len(totals)))
    values=totals['sum'].to_numpy()[selected].sum(axis=1)/totals['size'].to_numpy()[selected].sum(axis=1)
    lo,hi=np.quantile(values,[.025,.975])
    return float(frame.difference.mean()),float(lo),float(hi),len(totals)


def group_numbers():
 # 523 groups every nonempty calibration/offline/forward case before skipping
 # calibration, therefore its sorted enumeration includes the calibration groups.
 groups=set()
 for family in ['calendar','crossed']:
  for path in (BASE/family).glob('*/replicate_*/*/annual_predictions.parquet'):
   if pq.ParquetFile(path).metadata.num_rows:
    d=json.loads((path.parent/'design.json').read_text());groups.add((family,path.parents[2].name,d['station_key']))
 return {key:i for i,key in enumerate(sorted(groups))}


def tail_rows(path,family,rep,station,number,reference,points):
 c=pd.read_parquet(path)
 if c.empty:return []
 years=reference.index.to_numpy();values=reference.to_numpy();expected=float(slope(years,values));pos=reference.index.get_indexer(c.year)
 if (pos<0).any() or c.year.duplicated().any():raise ValueError('invalid archive years')
 rows=[]
 for method,prefix in [('D2','D2'),('stochastic_calibrated','stochastic_cal')]:
  take=points.loc[points.family.eq(family)&points['mode'].eq('forward')&points.station_key.eq(station)&points.replicate.eq(rep)&points.estimator.eq(method)&points.retention.eq('all')&points.dependence.eq('point')]
  if len(take)!=1:raise ValueError('missing point trend')
  if not bool(take.iloc[0].available):continue
  q=np.repeat(values[:,None],len(LEVELS),axis=1);q[pos]=c[[f'{prefix}_q{int(100*level):02d}' for level in LEVELS]].to_numpy(float)
  if not np.isfinite(q).all():continue
  ranks=np.random.default_rng(plain_seed(525,number,rep)).normal(size=(256,len(years)))
  bounds=np.repeat(np.nan,len(years));bounds[pos]=c.observed_lower_bound__observed_days.to_numpy(float)
  for tail in ['constant','normal']:
   draws=reorder_marginals(marginal_draws(q,tails=tail,lower_bounds=bounds),ranks)
   lo,hi=np.quantile(slope(years,draws),[.025,.975])
   rows.append({'family':family,'mode':'forward','station_key':station,'replicate':rep,'estimator':method,'tails':tail,
      'coverage95':bool(lo-1e-12<=expected<=hi+1e-12),'width95':hi-lo,'interval_score95':float(interval_score(lo,hi,expected,alpha=.05))})
 return rows


def main():
 assert json.loads((OUT/'archive_pooled_status.json').read_text())['status']=='passed'
 paths=sorted((PRIVATE/'whole_archive').glob('*/forward/replicate_*/*/annual_predictions.parquet'))
 if len(paths)!=120:raise ValueError('strict archive settings missing')
 annual=pd.read_csv(BASE/'annual.csv');trends=pd.read_csv(BASE/'trends.csv');tails=pd.read_csv(BASE/'quantile_tail_sensitivity.csv')
 numbers=group_numbers()
 source=pd.read_parquet(SOURCE/'cases/leave_one_year_out/seed_00.parquet',columns=['station_key','year','design_family','eval_truth_h30'])
 truth={(f,s):g.drop_duplicates('year').set_index('year').eval_truth_h30.sort_index() for (f,s),g in source.groupby(['design_family','station_key'])}
 a=[];t=[];oldtails=[];newtails=[];names=set()
 for path in paths:
  d=json.loads((path.parent/'design.json').read_text());station=d['station_key'];family=d['family'];rep=int(d['replicate']);names.add(station)
  ref=truth[(family,station)];ref=ref.loc[ref.index>=2010];n=numbers.get((family,'forward',station))
  if n is None and pq.ParquetFile(path).metadata.num_rows:raise ValueError('source tail random seed group not found')
  a.append(pd.read_csv(path.parent/'annual.csv'));t.append(pd.read_csv(path.parent/'trends.csv'))
  if n is not None:
   oldpath=BASE/path.relative_to(PRIVATE/'whole_archive')
   oldtails.extend(tail_rows(oldpath,family,rep,station,n,ref,trends))
   newtails.extend(tail_rows(path,family,rep,station,n,ref,t[-1]))
 an=pd.concat(a,ignore_index=True);tn=pd.concat(t,ignore_index=True)
 to=pd.DataFrame(oldtails);ts=pd.DataFrame(newtails)
 if len(names)!=3:raise ValueError('affected station count changed')
 previous=tails.loc[tails['mode'].eq('forward')&tails.station_key.isin(names)]
 replay=previous.merge(to,on=TAILKEY,how='outer',suffixes=('_saved','_replayed'),indicator=True,validate='one_to_one')
 if not replay._merge.eq('both').all():raise ValueError('replayed original tail keys differ')
 for col in ['coverage95','width95','interval_score95']:
  if not np.allclose(replay[col+'_saved'].astype(float),replay[col+'_replayed'].astype(float),rtol=0,atol=1e-8,equal_nan=True):raise ValueError('replayed original tail metric differs: '+col)
 strict_annual=replace(annual,an,ANNUALKEY,annual['mode'].eq('forward')&annual.station_key.isin(names))
 strict_trends=replace(trends,tn,TRENDKEY,trends['mode'].eq('forward')&trends.station_key.isin(names))
 strict_tails=replace(tails,ts,TAILKEY,tails['mode'].eq('forward')&tails.station_key.isin(names))
 module=T.load_script('strict_uncertainty_common',ROOT/'scripts/542_uncertainty_paired_diagnostics.py')
 old_common,old_sum,_,_=module.summarize_common(annual,trends,tails)
 new_common,new_sum,_,_=module.summarize_common(strict_annual,strict_trends,strict_tails)
 prior=pd.read_csv(BASE/'uncertainty_paired_summary.csv')
 ck=old_sum.merge(prior,on=['family','mode','estimator'],suffixes=('_computed','_saved'),validate='one_to_one')
 if len(ck)!=len(prior):raise ValueError('original uncertainty summary scope differs')
 for col in ['n_common','annual_coverage90_weighted','constant_coverage95','normal_coverage95','independent_coverage95','shared_parameters_coverage95','residual_blocks_coverage95']:
  if not np.allclose(ck[col+'_computed'],ck[col+'_saved'],rtol=0,atol=1e-8,equal_nan=True):raise ValueError('original uncertainty summary differs: '+col)
 paired=old_common.merge(new_common,on=KEY,how='inner',suffixes=('_original','_strict'),validate='one_to_one')
 if not paired.independence_group_original.eq(paired.independence_group_strict).all() or not paired.n_eligible_original.eq(paired.n_eligible_strict).all():raise ValueError('common cohorts differ in group or target masks')
 rows=[];contrasts=[]
 for (family,mode,method),g in paired.groupby(['family','mode','estimator']):
  if mode!='forward':continue
  oldcount=len(old_common.loc[old_common.family.eq(family)&old_common['mode'].eq(mode)&old_common.estimator.eq(method)])
  newcount=len(new_common.loc[new_common.family.eq(family)&new_common['mode'].eq(mode)&new_common.estimator.eq(method)])
  row={'family':family,'mode':mode,'estimator':method,'n_common_both_versions':len(g),'original_complete_cohort':oldcount,'strict_complete_cohort':newcount,'stations':g.station_key.nunique(),'groups':g.independence_group_original.nunique(),'incomplete_years':int(g.n_eligible_original.sum())}
  for ver in ['original','strict']:
   weights=g['n_eligible_'+ver]
   for m in ['coverage90','width90','mae']:row[ver+'_annual_'+m+'_weighted']=float(np.average(g[m+'_'+ver],weights=weights))
   for method2 in ['constant','normal','independent','shared_parameters','residual_blocks']:
    for metric in ['coverage95','width95','interval_score95']:
     row[ver+'_'+method2+'_'+metric]=float(g[method2+'_'+metric+'_'+ver].mean())
  rows.append(row)
  for construction in ['constant','normal','independent','shared_parameters','residual_blocks']:
   for metric in ['coverage95','width95','interval_score95']:
    delta=pd.to_numeric(g[construction+'_'+metric+'_strict'],errors='raise').to_numpy(float)-pd.to_numeric(g[construction+'_'+metric+'_original'],errors='raise').to_numpy(float)
    mean,lo,hi,ng=group_bootstrap_difference(g.independence_group_original,delta)
    contrasts.append({'family':family,'mode':mode,'estimator':method,'construction':construction,'metric':metric,'n_common':len(g),'n_groups':ng,'strict_minus_original':mean,'cluster_bootstrap_low':lo,'cluster_bootstrap_high':hi,'bootstrap_draws':2000})
 result=pd.DataFrame(rows);result.to_csv(OUT/'uncertainty_common_paired_sensitivity.csv',index=False)
 pd.DataFrame(contrasts).to_csv(OUT/'uncertainty_strict_contrasts.csv',index=False)
 status={'status':'passed','strict_archive_settings':len(paths),'affected_stations':len(names),'original_tail_rows_replayed':len(replay),'original_tail_metrics_reproduced':True,'original_summary_reproduced':True,
  'uncertainty':'2000 connected-group resamples of case-weighted strict-minus-original paired differences, descriptive only',
  'comparison':'common station/repetition cases with all original and strict annual, tail and joint-rank outputs available; original and strict target masks and reference unchanged',
  'limitation':'post-hoc paired sensitivity; tail and dependence treatments use different random sequences, annual marginal coverage remains imperfect; repeated masks are not independent climates and no physical sensor error is evaluated'}
 (OUT/'uncertainty_sensitivity_status.json').write_text(json.dumps(status,indent=2)+'\n')
 print(result.to_string(index=False));print(json.dumps(status,indent=2))
if __name__=='__main__':main()
