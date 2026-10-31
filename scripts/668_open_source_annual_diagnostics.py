#!/usr/bin/env python3
"""Paired annual uncertainty and peak-visibility sensitivity across source refits.

Outcomes are stratified using the hidden complete reference: this is not a
prospective diagnostic. Individual inputs remain in restricted local paths.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import wrr_tr_common as T

ROOT=T.ROOT
REV=ROOT/'results/wrr_review_response_20261027'
OUT=REV/'open_source_sensitivity'
BASE=REV/'whole_archive'
STAGE=ROOT/'private/wrr_open_source_sensitivity_20261026/whole_archive'
KEY=['family','mode','replicate','station_key','year']
LEVELS=[5,10,25,50,75,90,95]
METHODS=['D2','stochastic_cal']
METRICS=['mae','bias','coverage90','width90','interval_score90','crps','zero90']

def input_checks():
    plan=json.loads((OUT/'annual_sensitivity_plan.json').read_text())
    if plan['status']!='posthoc_frozen_before_candidate_annual_scores':raise ValueError('Annual sensitivity plan absent')
    paths=sorted(STAGE.glob('*/?*/replicate_*/*/open_source_receipt.json'))
    for p in paths:signature.update(str(p.relative_to(STAGE)).encode()+b'\0'+p.read_bytes())
    if len(paths)!=plan['receipt_count']:
        raise ValueError('Candidate archive receipts changed')
    return plan,paths

def read_candidates(paths):
    columns=['station_key','independence_group','year','observed_lower_bound__observed_days','D2']+[f'{m}_q{i:02d}' for m in METHODS for i in LEVELS]
    chunks=[];nonempty=0
    for receipt_path in paths:
        target=receipt_path.parent;rel=target.relative_to(STAGE)
        family,mode,rep,station=rel.parts
        old=BASE/family/mode/rep/station/'annual_predictions.parquet'
        new=target/'annual_predictions.parquet'
        receipt=json.loads(receipt_path.read_text())
        oldn=pq.ParquetFile(old).metadata.num_rows;newn=pq.ParquetFile(new).metadata.num_rows
        if oldn!=newn:raise ValueError('Annual case count changed for archive setting')
        if not newn:continue
        c=pd.read_parquet(new,columns=columns);c['family']=family;c['mode']=mode;c['replicate']=int(rep.split('_')[-1]);chunks.append(c);nonempty+=1
    result=pd.concat(chunks,ignore_index=True)
    if result.duplicated(KEY).any():raise ValueError('Duplicate candidate annual keys')
    return result,nonempty

def main():
    plan,paths=input_checks()
    annual=T.load_script('candidate_peak_visibility',ROOT/'scripts/578_peak_visibility_diagnostics.py')
    scoring=T.load_script('candidate_annual_scoring',ROOT/'scripts/576_verify_private_annual_predictions.py')
    original=annual.load_workspace_cases();candidate,nonempty=read_candidates(paths)
    merged=original.merge(candidate,on=KEY,how='outer',suffixes=('_old','_candidate'),indicator=True,validate='one_to_one')
    if not merged._merge.eq('both').all():raise ValueError('Annual target case identities differ')
    if not merged.independence_group_old.eq(merged.independence_group_candidate).all():raise ValueError('Connected-group identities differ')
    bound='observed_lower_bound__observed_days'
    if not np.allclose(merged[bound+'_old'],merged[bound+'_candidate'],atol=1e-8,rtol=0,equal_nan=True):raise ValueError('Observed bounds differ')
    # Reproduce all original summaries on their original (not new selected) cohorts.
    prior=pd.read_csv(BASE/'peak_visibility_annual.csv')
    qs=[f'{m}_q{i:02d}' for m in METHODS for i in LEVELS]
    baseline_checked=0
    output=[];paired=[];cohorts=[];loo=[]
    for offset,((family,mode),f) in enumerate(merged.groupby(['family','mode'],sort=True)):
        qold=np.isfinite(f[[c+'_old' for c in qs]].to_numpy(float)).all(axis=1)
        qnew=np.isfinite(f[[c+'_candidate' for c in qs]].to_numpy(float)).all(axis=1)
        physical=np.isfinite(f.reference_h30.to_numpy(float)) & np.isfinite(f[bound+'_old'].to_numpy(float))
        oldvalid=qold&physical;newvalid=qnew&physical;common=oldvalid&newvalid
        cohorts.append({'family':family,'mode':mode,'all_cases':len(f),'original_finite_both':int(oldvalid.sum()),
                        'candidate_finite_both':int(newvalid.sum()),'common_four_way':int(common.sum()),
                        'original_only':int((oldvalid&~newvalid).sum()),'candidate_only':int((newvalid&~oldvalid).sum())})
        if not common.any():raise ValueError('No common annual cases')
        baseline=f.loc[oldvalid].copy();baseline['stratum']=annual.classify(baseline.reference_h30,baseline[bound+'_old'])
        for method in METHODS:
            quantiles=baseline[[f'{method}_q{i:02d}_old' for i in LEVELS]].to_numpy(float)
            metrics=annual.case_metrics(quantiles,baseline.reference_h30.to_numpy(float),baseline[bound+'_old'].to_numpy(float),scoring)
            for metric in METRICS:baseline[method+'_'+metric]=metrics[metric].to_numpy()
            for stratum in ['all','bound_matches_reference','unobserved_peak_excess']:
                part=baseline if stratum=='all' else baseline.loc[baseline.stratum.eq(stratum)]
                previous=prior.loc[prior.family.eq(family)&prior['mode'].eq(mode)&prior.stratum.eq(stratum)&prior.estimator.eq('stochastic_calibrated' if method=='stochastic_cal' else method)]
                if len(previous)!=1 or len(part)!=int(previous.iloc[0].n):raise ValueError('Original annual baseline denominator differs')
                for metric in METRICS:
                    if not np.isclose(part[method+'_'+metric].mean(),previous.iloc[0][metric],atol=1e-9,rtol=0,equal_nan=True):raise ValueError('Original annual baseline differs: '+metric)
                baseline_checked+=1
        g=f.loc[common].copy().reset_index(drop=True)
        g['stratum']=annual.classify(g.reference_h30,g[bound+'_old'])
        y=g.reference_h30.to_numpy(float);boundvals=g[bound+'_old'].to_numpy(float)
        for method in METHODS:
            for version in ['old','candidate']:
                q=g[[f'{method}_q{i:02d}_{version}' for i in LEVELS]].to_numpy(float)
                if (q<boundvals[:,None]-1e-8).any():raise ValueError('A quantile is below the observed bound')
                if method=='D2' and not np.allclose(g['D2_'+version],q[:,3],atol=1e-8,rtol=0):raise ValueError('D2 median and point prediction differ')
                result=annual.case_metrics(q,y,boundvals,scoring)
                for metric in METRICS:g[version+'_'+method+'_'+metric]=result[metric].to_numpy()
        for stratum in ['all','bound_matches_reference','unobserved_peak_excess']:
            part=g if stratum=='all' else g.loc[g.stratum.eq(stratum)]
            if part.empty:continue
            base={'family':family,'mode':mode,'stratum':stratum,'n_common':len(part),
                  'stations':part.station_key.nunique(),'station_years':len(part[['station_key','year']].drop_duplicates()),
                  'groups':part.independence_group_old.nunique(),'regions':part.region.nunique()}
            for method in METHODS:
                name='stochastic_calibrated' if method=='stochastic_cal' else method
                for version in ['old','candidate']:
                    row=base|{'estimator':name,'version':version}
                    for metric in METRICS:row[metric]=float(part[version+'_'+method+'_'+metric].mean())
                    output.append(row)
                diffrow=base|{'estimator':name}
                for i,metric in enumerate(METRICS):
                    difference=part['candidate_'+method+'_'+metric].to_numpy(float)-part['old_'+method+'_'+metric].to_numpy(float)
                    ci,equal=annual.cluster_bootstrap(part.independence_group_old,difference,4000,seed=668000+100*offset+i)
                    diffrow[metric+'_difference']=float(difference.mean())
                    diffrow[metric+'_group_equal_difference']=equal
                    diffrow[metric+'_bootstrap_low']=float(ci[0]);diffrow[metric+'_bootstrap_high']=float(ci[1])
                paired.append(diffrow)
                for removed in sorted(part.region.unique()):
                    keep=part.loc[part.region.ne(removed)]
                    if keep.empty:continue
                    row=base|{'estimator':name,'excluded_region':removed,'n_remaining':len(keep),
                              'groups_remaining':keep.independence_group_old.nunique()}
                    for metric in ['coverage90','mae','width90','interval_score90','crps']:
                        row[metric+'_difference']=float((keep['candidate_'+method+'_'+metric]-keep['old_'+method+'_'+metric]).mean())
                    loo.append(row)
    pd.DataFrame(output).to_csv(OUT/'annual_sensitivity_scores.csv',index=False)
    pd.DataFrame(paired).to_csv(OUT/'annual_sensitivity_paired.csv',index=False)
    pd.DataFrame(cohorts).to_csv(OUT/'annual_sensitivity_cohorts.csv',index=False)
    pd.DataFrame(loo).to_csv(OUT/'annual_sensitivity_leave_region_out.csv',index=False)
    status={'status':'passed','archive_settings':len(paths),'nonempty_annual_settings':nonempty,'matched_annual_cases':len(merged),
            'original_summary_cells_reproduced':baseline_checked,'same_keys_groups_and_bounds':True,
            'four_way_common_cohorts':len(cohorts),'bootstrap_draws':4000,'source_status':'posthoc_filtered_provider_and_strict_region',
            'limitations':plan['limitations'],'scope':'annual results only; no new calibration or external validation'}
    (OUT/'annual_sensitivity_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(pd.DataFrame(output).loc[lambda x:x['mode'].eq('forward') & x.family.eq('crossed') & x.stratum.eq('unobserved_peak_excess'),['estimator','version','n_common','stations','groups','coverage90','width90','interval_score90','mae']].to_string(index=False))
    print(json.dumps(status,indent=2))

if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/'annual_sensitivity_status.json').write_text(json.dumps({
            'status':'failed','error':f'{type(exc).__name__}: {exc}',
            'limitation':'Prior aggregate files may remain and must not be treated as a successful current run.'
        },indent=2)+'\n')
        raise
