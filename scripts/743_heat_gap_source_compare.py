#!/usr/bin/env python3
"""Compare source-model versions on the same matched-gap archive settings.

This descriptive post-hoc analysis reuses saved source models and daily fits.
"""
from __future__ import annotations
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
os.umask(0o077)
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
S=T.load_script('gap_source_analysis',ROOT/'scripts/742_heat_gap_source_sensitivity.py')
OLD=S.M
BASE_AUDIT=T.load_script('gap_baseline_receipts',ROOT/'scripts/699_stress_source_baseline_audit.py')
KEY=['family','mode','station_key','replicate','estimator','retention','dependence']
METHODS=['D2','stochastic_calibrated'];DEPS=['point','independent','shared_parameters','residual_blocks']
VERSIONS=['original','strict_original','candidate'];SIDES=['baseline','stress']

def data():
    roster=pd.read_csv(S.EXP/'roster.csv');frames=[]
    for row in roster.itertuples(index=False):
        model=S.CAND/'refits/before_2010/seed_00'/f'{row.region}.joblib';cal=S.CAND/'calibrations/forward'/f'{row.region}.json'
        for rep in range(5):
            rel=OLD.suffix(row.station_key,rep);original=S.BASE/rel;stress=S.GAP/rel;candidate=S.CAND/'whole_archive'/rel
            strict=S.STRICT/'whole_archive'/rel if row.region=='usgs_huc17' else original
            candidate_stress=S.STAGE/'candidate/heat_gap_matched'/rel
            strict_stress=S.STAGE/'strict_original/heat_gap_matched'/rel if row.region=='usgs_huc17' else stress
            BASE_AUDIT.verify_candidate_receipt(original,candidate,model,cal)
            OLD.verify_plugin(original,candidate)
            if row.region=='usgs_huc17':OLD.verify_plugin(original,strict)
            for version,base,altered in [('original',original,stress),('strict_original',strict,strict_stress),('candidate',candidate,candidate_stress)]:
                if version=='candidate' or version=='strict_original' and row.region=='usgs_huc17':
                    model_path=model if version=='candidate' else S.STRICT/'refits/before_2010/seed_00/usgs_huc17.joblib'
                    cal_path=cal if version=='candidate' else S.STRICT/'strict_archive_calibration.json'
                    receipt=json.loads((altered/'receipt.json').read_text())
                    expected={}
                    if receipt['inputs']!=expected:
                        raise ValueError('Source replay receipt changed')
                    OLD.verify_plugin(stress,altered)
                for side,folder in [('baseline',base),('stress',altered)]:
                    x=pd.read_csv(folder/'trends.csv')
                    x=x[x.estimator.isin(METHODS)&x.retention.eq('all')&x.dependence.isin(DEPS)].copy()
                    if len(x)!=8 or x.duplicated(KEY).any():raise ValueError('Missing source trend cells')
                    if not x.station_key.eq(row.station_key).all() or not x.region.eq(row.region).all() or not x.independence_group.eq(row.independence_group).all():
                        raise ValueError('Station group metadata changed')
                    x['version']=version;x['side']=side;frames.append(x)
    f=pd.concat(frames,ignore_index=True)
    if len(f)!=205*3*2*2*4:raise ValueError('Source replay cohort incomplete')
    f.to_parquet(S.STAGE/'six_way_trends.parquet',index=False)
    return f

def summary(frame):
    rows=[];region_rows=[]
    for di,dependence in enumerate(DEPS):
        block=frame[frame.dependence.eq(dependence)].copy();block['cell']=block.version+'_'+block.side
        labels=[version+'_'+side for version in VERSIONS for side in SIDES]
        index=['station_key','replicate','independence_group','region','estimator']
        fields=['available','truth_slope','error','squared_error','missing_coverage95','width95','interval_score95']
        if block.duplicated(index+['cell']).any():raise ValueError('Duplicate source cell')
        x=block.pivot(index=index,columns='cell',values=fields)
        x.columns=[f'{a}__{b}' for a,b in x.columns];x=x.reset_index()
        if len(x)!=410:raise ValueError('Unexpected archive-method count')
        x['six_available']=np.logical_and.reduce([x['available__'+v].fillna(False).astype(bool) for v in labels])
        both=x.groupby(['station_key','replicate']).six_available.agg(['all','size'])
        if not both['size'].eq(2).all():raise ValueError('Both-method cohort incomplete')
        bothkeys=set(both.index[both['all']])
        for mi,method in enumerate(METHODS):
            y=x[x.estimator.eq(method)].copy()
            for scope in ['estimator_six_way','both_methods_six_way']:
                selected=y.six_available.copy()
                if scope=='both_methods_six_way':selected &= pd.MultiIndex.from_frame(y[['station_key','replicate']]).isin(bothkeys)
                valid=y.loc[selected].copy()
                for field in fields[1:]:
                    for label in labels:valid[field+'__'+label]=pd.to_numeric(valid[field+'__'+label],errors='raise')
                truth=valid['truth_slope__original_baseline'].to_numpy(float)
                if any(not np.allclose(truth,valid['truth_slope__'+label],atol=1e-8,rtol=0) for label in labels):
                    raise ValueError('Source versions changed target trend reference')
                interval=np.ones(len(valid),dtype=bool)
                if dependence!='point':
                    for label in labels:
                        for metric in ['missing_coverage95','width95','interval_score95']:
                            interval &= np.isfinite(valid[metric+'__'+label].to_numpy(float))
                iv=valid.loc[interval]
                for vi,version in enumerate(VERSIONS):
                    delta=valid['squared_error__'+version+'_stress']-valid['squared_error__'+version+'_baseline']
                    groups=valid.assign(d=delta).groupby('independence_group').d.agg(['sum','count','mean'])
                    seed=74300+1000*di+100*mi+10*vi+(scope=='both_methods_six_way')
                    draws=np.random.default_rng(seed).integers(len(groups),size=(4000,len(groups))) if len(groups) else np.empty((0,0),int)
                    boot=groups['sum'].to_numpy()[draws].sum(axis=1)/groups['count'].to_numpy()[draws].sum(axis=1) if len(groups) else np.array([])
                    r={'estimator':method,'dependence':dependence,'scope':scope,'version':version,
                       'n_eligible':len(y),'n_common':len(valid),'stations':valid.station_key.nunique(),'groups':len(groups),
                       'baseline_available':int(y['available__'+version+'_baseline'].fillna(False).astype(bool).sum()),
                       'stress_available':int(y['available__'+version+'_stress'].fillna(False).astype(bool).sum()),
                       'interval_common':len(iv) if dependence!='point' else None,
                       'baseline_rmse':float(np.sqrt(valid['squared_error__'+version+'_baseline'].mean())) if len(valid) else np.nan,
                       'stress_rmse':float(np.sqrt(valid['squared_error__'+version+'_stress'].mean())) if len(valid) else np.nan,
                       'mse_difference':float(delta.mean()) if len(valid) else np.nan,
                       'equal_group_mse_difference':float(groups['mean'].mean()) if len(groups) else np.nan,
                       'bootstrap_low':float(np.quantile(boot,.025)) if len(boot) else np.nan,
                       'bootstrap_high':float(np.quantile(boot,.975)) if len(boot) else np.nan}
                    if dependence!='point':
                        for side in SIDES:
                            for metric in ['missing_coverage95','width95','interval_score95']:
                                r[side+'_'+metric]=float(iv[metric+'__'+version+'_'+side].mean()) if len(iv) else np.nan
                    rows.append(r)
                    if scope=='both_methods_six_way':
                        for region in sorted(valid.region.unique()):
                            q=valid[valid.region.ne(region)]
                            region_rows.append({'estimator':method,'dependence':dependence,'version':version,'removed_region':region,
                                'n_common':len(q),'groups':q.independence_group.nunique(),
                                'baseline_rmse':float(np.sqrt(q['squared_error__'+version+'_baseline'].mean())) if len(q) else np.nan,
                                'stress_rmse':float(np.sqrt(q['squared_error__'+version+'_stress'].mean())) if len(q) else np.nan,
                                'mse_difference':float((q['squared_error__'+version+'_stress']-q['squared_error__'+version+'_baseline']).mean()) if len(q) else np.nan})
    return pd.DataFrame(rows),pd.DataFrame(region_rows)

def main():
    S.verify_plan()
    if json.loads((S.OUT/'execution.json').read_text())['replays']!=220:raise ValueError('Source replays incomplete')
    frame=data();result,regional=summary(frame)
    result.to_csv(S.OUT/'six_way_summary.csv',index=False);regional.to_csv(S.OUT/'leave_region_out.csv',index=False)
    report={'status':'computed_posthoc','source_replays':220,'candidate_replays':205,'strict_huc17_replays':15,
            'stored_trend_rows':len(frame),'summary_rows':len(result),'leave_region_rows':len(regional),
            'same_masks_daily_features_and_plugin_checked':True,'baseline_candidate_receipts_checked':205,
            'limitations':json.loads((S.OUT/'plan.json').read_text())['limitations']}
    (S.OUT/'status.json').write_text(json.dumps(report,indent=2)+'\n')
    print(result.query("dependence == 'independent' and scope == 'both_methods_six_way'").to_string(index=False),flush=True)
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
