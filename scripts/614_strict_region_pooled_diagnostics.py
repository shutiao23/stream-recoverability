#!/usr/bin/env python3
"""Compare original and post-hoc strict-region forward archive results on paired cases."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
REV=ROOT/'results/wrr_review_response_20261027'
OUT=REV/'strict_region_holdout'
PRIVATE=ROOT/'private/wrr_strict_region_holdout_20261026/whole_archive'
KEY=['family','mode','region','station_key','replicate','estimator','retention','dependence']


def main():
    status=json.loads((OUT/'archive_sensitivity_status.json').read_text())
    if status['archive_settings']!=120 or not status['same_masks_verified']:raise ValueError('full sensitivity required')
    old=pd.read_csv(REV/'whole_archive/trends.csv')
    old=old.loc[old['mode'].eq('forward')].copy()
    paths=sorted(PRIVATE.glob('*/*/replicate_*/*/trends.csv'))
    if len(paths)!=120:raise ValueError('incorrect strict archive count')
    changed=pd.concat([pd.read_csv(p) for p in paths],ignore_index=True)
    keep=~old.region.eq('usgs_huc17')
    new=pd.concat([old.loc[keep],changed],ignore_index=True)
    paired=old.merge(new,on=KEY,how='outer',suffixes=('_original','_strict'),indicator=True,validate='one_to_one')
    if not paired._merge.eq('both').all():raise ValueError('original and strict keys differ')
    if not np.allclose(paired.truth_slope_original,paired.truth_slope_strict,equal_nan=True,atol=1e-12):raise ValueError('truth differs')
    result=[]
    for keys,g in paired.groupby(['family','estimator','retention','dependence'],sort=True):
        valid=g.available_original & g.available_strict
        row=dict(zip(['family','estimator','retention','dependence'],keys))
        row.update(n_eligible=len(g),n_stations=g.station_key.nunique(),original_available=int(g.available_original.sum()),strict_available=int(g.available_strict.sum()),n_common=int(valid.sum()))
        for suffix in ['original','strict']:
            sub=g.loc[valid]
            for field in ['error','squared_error','missing_coverage95','width95','interval_score95']:
                row[f'{suffix}_{field}']=float(sub[f'{field}_{suffix}'].mean()) if len(sub) else np.nan
            row[f'{suffix}_rmse']=float(np.sqrt(row[f'{suffix}_squared_error']))
        result.append(row)
    pd.DataFrame(result).to_csv(OUT/'archive_pooled_paired.csv',index=False)
    # Four-arm common cohort: same case available for both estimators in both versions.
    point=paired.loc[paired.retention.eq('all') & paired.dependence.eq('point') & paired.estimator.isin(['D2','stochastic_calibrated'])]
    ident=['family','mode','region','station_key','replicate']
    d=point.loc[point.estimator.eq('D2')]
    s=point.loc[point.estimator.eq('stochastic_calibrated')]
    both=d.merge(s,on=ident,suffixes=('_d2','_stoch'),validate='one_to_one')
    common=both.available_original_d2 & both.available_strict_d2 & both.available_original_stoch & both.available_strict_stoch
    both=both.loc[common]
    if not np.allclose(both.truth_slope_original_d2,both.truth_slope_original_stoch,atol=1e-12):raise ValueError('estimator truth differs')
    rows=[]
    for family,g in both.groupby('family'):
        row={'family':family,'n_common':len(g),'n_stations':g.station_key.nunique()}
        for version in ['original','strict']:
            for label in ['d2','stoch']:
                row[f'{version}_{label}_rmse']=float(np.sqrt(g[f'squared_error_{version}_{label}'].mean()))
        rows.append(row)
    pd.DataFrame(rows).to_csv(OUT/'archive_estimator_four_way_paired.csv',index=False)
    # Replicate the factorial interaction on the same eight-cell common cohort.
    pt=paired.loc[paired.dependence.eq('point') & paired.estimator.isin(['plug_in','D2','stochastic_calibrated'])]
    rows=[]
    for family,g in pt.groupby('family'):
        for estimator in ['D2','stochastic_calibrated']:
            z=g.loc[g.estimator.isin(['plug_in',estimator])].copy()
            pivot=z.pivot(index=ident,columns=['retention','estimator'],values=['squared_error_original','squared_error_strict'])
            needed=[(v,r,e) for v in ['squared_error_original','squared_error_strict'] for r in ['all','warm90'] for e in ['plug_in',estimator]]
            p=pivot[needed].dropna()
            row={'family':family,'estimator':estimator,'n_common':len(p),'n_stations':p.index.get_level_values('station_key').nunique()}
            for version in ['original','strict']:
                v='squared_error_'+version
                a=p[(v,'warm90','plug_in')];b=p[(v,'all','plug_in')];c=p[(v,'warm90',estimator)];d=p[(v,'all',estimator)]
                row[version+'_total_gain']=float((a-d).mean())
                row[version+'_symmetric_retention']=float((((a-b)+(c-d))/2).mean())
                row[version+'_symmetric_estimator']=float((((a-c)+(b-d))/2).mean())
                row[version+'_interaction']=float(((a-b)-(c-d)).mean())
            rows.append(row)
    pd.DataFrame(rows).to_csv(OUT/'archive_factorial_paired.csv',index=False)
    counts={'status':'passed','strict_archive_settings':len(paths),'paired_rows':len(paired),'same_truth_and_keys':True,
       'same_masks_and_hidden_value_check':'verified in 120 individual strict receipts',
       'strict_scope':'HUC17 three forward stations only; other original forward archives unchanged',
       'limitation':'post-hoc sensitivity with smaller source samples, not a complete strict-region rerun of every analysis; cases and repetitions are not independent climates'}
    (OUT/'archive_pooled_status.json').write_text(json.dumps(counts,indent=2)+'\n')
    print(pd.DataFrame(rows).to_string(index=False));print(pd.read_csv(OUT/'archive_estimator_four_way_paired.csv').to_string(index=False));print(json.dumps(counts,indent=2))
if __name__=='__main__':main()
