#!/usr/bin/env python3
"""Paired annual diagnostics after stricter region exclusion in HUC17."""
from __future__ import annotations
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import wrr_tr_common as T

ROOT=T.ROOT; REV=ROOT/'results/wrr_review_response_20261027'; OUT=REV/'strict_region_holdout';PRIVATE=ROOT/'private/wrr_strict_region_holdout_20261026'; SOURCE=ROOT/'results/wrr_review_completion_20261024'
KEY=['family','mode','replicate','station_key','year']
LEVELS=[5,10,25,50,75,90,95]; METHODS=['D2','stochastic_cal']


def replace_annual_quantiles(old, strict, quantile_columns):
    """Replace by case identity, including when input indices are nonconsecutive."""
    original=old.reset_index(drop=True)
    new=original.merge(strict[KEY+quantile_columns],on=KEY,how='left',suffixes=('','_strict'),validate='one_to_one',indicator=True,sort=False)
    affected=new.region.eq('usgs_huc17')
    if not new.loc[affected,'_merge'].eq('both').all() or not new.loc[~affected,'_merge'].eq('left_only').all():
        raise ValueError('strict replacement scope differs')
    for col in quantile_columns:
        new.loc[affected,col]=new.loc[affected,col+'_strict'].to_numpy()
    return new[original.columns].copy()


def main():
    audit=json.loads((OUT/'archive_sensitivity_status.json').read_text())
    if audit['archive_settings']!=120 or not audit['same_masks_verified']:raise ValueError('strict archive audit incomplete')
    annual=T.load_script('strict_annual_visibility',ROOT/'scripts/578_peak_visibility_diagnostics.py')
    scoring=T.load_script('strict_annual_scoring',ROOT/'scripts/576_verify_private_annual_predictions.py')
    old=annual.load_workspace_cases();old=old.loc[old['mode'].eq('forward')].copy().reset_index(drop=True)
    cols=['station_key','independence_group','year','observed_lower_bound__observed_days','D2']+[f'{m}_q{q:02d}' for m in METHODS for q in LEVELS]
    chunks=[];paths=sorted(PRIVATE.glob('whole_archive/*/forward/replicate_*/*/annual_predictions.parquet'))
    if len(paths)!=120:raise ValueError('incorrect strict annual settings')
    for path in paths:
        if pq.ParquetFile(path).metadata.num_rows==0:continue
        c=pd.read_parquet(path,columns=cols);c['family']=path.parents[3].name;c['mode']='forward';c['replicate']=int(path.parents[1].name.split('_')[-1]);chunks.append(c)
    strict=pd.concat(chunks,ignore_index=True)
    affected=old.region.eq('usgs_huc17')
    paired=old.loc[affected].merge(strict,on=KEY,how='outer',suffixes=('_original','_strict'),indicator=True,validate='one_to_one')
    if not paired._merge.eq('both').all():raise ValueError('strict annual keys differ')
    if not paired.independence_group_original.eq(paired.independence_group_strict).all():raise ValueError('strict annual groups differ')
    if not np.allclose(paired.observed_lower_bound__observed_days_original,paired.observed_lower_bound__observed_days_strict,atol=1e-8,rtol=0,equal_nan=True):raise ValueError('strict visible bounds differ')
    new=replace_annual_quantiles(old,strict,[f'{m}_q{q:02d}' for m in METHODS for q in LEVELS])
    if len(old)!=len(new):raise ValueError('target row count changed')
    old=old.reset_index(drop=True);new=new.reset_index(drop=True)
    qcols=[f'{m}_q{q:02d}' for m in METHODS for q in LEVELS]
    valid=np.isfinite(old[qcols].to_numpy(float)).all(axis=1)&np.isfinite(new[qcols].to_numpy(float)).all(axis=1)&np.isfinite(old.reference_h30)&np.isfinite(old.observed_lower_bound__observed_days)
    if not np.allclose(old.reference_h30,new.reference_h30,rtol=0,atol=1e-12,equal_nan=True):raise ValueError('reference changed')
    g=old.loc[valid].copy().reset_index(drop=True);h=new.loc[valid].copy().reset_index(drop=True)
    g['stratum']=annual.classify(g.reference_h30,g.observed_lower_bound__observed_days)
    rows=[]
    for method in METHODS:
        for label,data in [('original',g),('strict',h)]:
            q=data[[f'{method}_q{level:02d}' for level in LEVELS]].to_numpy(float); y=data.reference_h30.to_numpy(float); b=data.observed_lower_bound__observed_days.to_numpy(float)
            if (q<b[:,None]-1e-8).any():raise ValueError('quantile below observed bound')
            scores=annual.case_metrics(q,y,b,scoring)
            for metric in annual.METRICS:g[label+'_'+method+'_'+metric]=scores[metric].to_numpy()
        for (family,stratum),block in pd.concat([g.assign(scope='all'),g.assign(scope=g.stratum)],ignore_index=True).groupby(['family','scope']):
            for scope,part in [('all_regions',block),('huc17',block.loc[block.region.eq('usgs_huc17')])]:
                if part.empty:continue
                row={'scope':scope,'family':family,'stratum':stratum,'estimator':'stochastic_calibrated' if method=='stochastic_cal' else method,'n_common':len(part),'stations':part.station_key.nunique(),'groups':part.independence_group.nunique()}
                for label in ['original','strict']:
                    for metric in annual.METRICS:row[label+'_'+metric]=float(part[label+'_'+method+'_'+metric].mean())
                rows.append(row)
    out=pd.DataFrame(rows)
    # Baseline comparison to the separately produced annual visibility report.
    prior=pd.read_csv(REV/'whole_archive/peak_visibility_annual.csv')
    check=out.loc[out.scope.eq('all_regions')].merge(prior.loc[prior['mode'].eq('forward')],on=['family','stratum','estimator'],validate='one_to_one')
    if len(check)!=12 or not check.n_common.eq(check.n).all():raise ValueError('paired baseline denominator differs from previous audit')
    for metric in annual.METRICS:
        if not np.allclose(check['original_'+metric],check[metric],atol=1e-9,rtol=0,equal_nan=True):raise ValueError('previous annual score differs: '+metric)
    out.to_csv(OUT/'annual_paired_diagnostics.csv',index=False)
    # A subset with one source group cannot become supported by changing fitted residuals.
    oldbundle=joblib.load(SOURCE/'refits/before_2010/seed_00/usgs_huc17.joblib');strictbundle=joblib.load(PRIVATE/'refits/before_2010/seed_00/usgs_huc17.joblib')
    original_roles=set(oldbundle['roles']['rule_calibration']);strict_roles=set(strictbundle['roles']['rule_calibration'])
    if original_roles!=strict_roles:raise ValueError('rule calibration source groups changed; explicit recalibration required')
    for filename in ['annual_interval_expansion/source_support.csv','whole_archive/task_calibration_sources.csv']:
        x=pd.read_csv(REV/filename);x=x.loc[x['mode'].eq('forward')&x.region.eq('usgs_huc17')]
        if len(x)!=4 or not x.status.eq('insufficient_source_groups').all() or x.n_source_groups.max()>=3:raise ValueError('HUC17 calibration support assumption no longer valid')
        if not set(x.n_source_groups.astype(int)).issubset({0,1,2}):raise ValueError('unexpected group count')
    status={'status':'passed','strict_archive_settings':120,'affected_annual_cases':len(paired),'forward_paired_finite_cases':int(valid.sum()),
      'original_annual_scores_match_existing_audit':True,'same_keys_truth_bounds_and_groups':True,
      'calibration_support_invariant':'for the affected HUC17 forward region, same rule group assignments and fewer than three contributing groups imply existing source annual expansion and task calibration remain unsupported; estimated radii and error distributions were not re-estimated',
      'limitation':'post-hoc case-weighted sensitivity; repeated masks are not independent climates; outcome stratum is known only using the complete reference; no physical measurement-error guarantee'}
    (OUT/'annual_diagnostics_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(out.to_string(index=False));print(json.dumps(status,indent=2))
if __name__=='__main__':main()
