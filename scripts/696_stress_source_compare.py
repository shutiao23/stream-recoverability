#!/usr/bin/env python3
"""Six-way common-cohort comparison of stress and source-model versions."""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[name]='1'
os.umask(0o077)
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
M=T.load_script('stress_source_compare_dependencies',ROOT/'scripts/694_stress_source_sensitivity.py')
KEY=['family','mode','station_key','replicate','estimator','retention','dependence']
VERSIONS=['original','strict_original','candidate']
SIDES=['baseline','stress']

def read_table(folder):
    return pd.read_csv(folder/'trends.csv')

def check_baseline(original,other):
    a=json.loads((original/'design.json').read_text())
    b=json.loads((other/'design.json').read_text())
    if a['station_key']!=b['station_key'] or a['masks']!=b['masks'] or b['hidden_values_present_in_visible_archive']!=0:
        raise ValueError('Baseline source version changed masks or exposed hidden target')
    x=read_table(original).merge(read_table(other),on=KEY,how='outer',suffixes=('_a','_b'),indicator=True,validate='one_to_one')
    if not x._merge.eq('both').all():raise ValueError('Baseline version keys differ')
    plug=x[x.estimator.eq('plug_in')&x.dependence.eq('point')]
    if not plug.available_a.eq(plug.available_b).all() or not np.allclose(plug.error_a,plug.error_b,rtol=0,atol=1e-8,equal_nan=True):
        raise ValueError('Baseline unchanged plug-in differs')

def load_pairs(scenario,roster):
    rows=[]
    for site in roster.itertuples(index=False):
        for rep in range(5):
            rel=M.suffix(site.station_key,rep)
            base_original=M.BASE/rel
            stress_original=M.EXP/scenario/rel
            base_strict=M.STRICT/'whole_archive'/rel if site.region=='usgs_huc17' else base_original
            stress_strict=M.STAGE/'strict_original'/scenario/rel if site.region=='usgs_huc17' else stress_original
            base_candidate=M.CAND/'whole_archive'/rel
            stress_candidate=M.STAGE/'candidate'/scenario/rel
            check_baseline(base_original,base_candidate)
            if site.region=='usgs_huc17':check_baseline(base_original,base_strict)
            for version,base,stress in [('original',base_original,stress_original),('strict_original',base_strict,stress_strict),('candidate',base_candidate,stress_candidate)]:
                for side,folder in [('baseline',base),('stress',stress)]:
                    if side=='stress' and version!='original' and not (folder/'receipt.json').is_file():
                        if not version=='strict_original' and site.region!='usgs_huc17':raise ValueError('Missing source stress receipt')
                    if side=='stress' and (folder/'receipt.json').is_file():
                        receipt=json.loads((folder/'receipt.json').read_text())
                        source_root=M.STRICT if version=='strict_original' else M.CAND
                        calibration=source_root/'strict_archive_calibration.json' if version=='strict_original' else source_root/'calibrations/forward'/f'{site.region}.json'
                        model=source_root/'refits/before_2010/seed_00'/f'{site.region}.joblib'
                        expected={}
                        if receipt['inputs']!=expected:
                            raise ValueError('Source stress receipt or file changed')
                    x=read_table(folder)
                    x=x[x.estimator.isin(['D2','stochastic_calibrated']) & x.retention.eq('all') & x.dependence.isin(['point','independent'])].copy()
                    if len(x)!=4 or x.duplicated(KEY).any():raise ValueError('Missing or duplicated trend case')
                    x['version']=version;x['side']=side;x['scenario']=scenario
                    rows.append(x)
    return pd.concat(rows,ignore_index=True)

def summarize(frame):
    out=[];regional=[];rng=np.random.default_rng(694)
    for scenario in M.SCENARIOS:
        block=frame[frame.scenario.eq(scenario)]
        for estimator in ['D2','stochastic_calibrated']:
            for dependence in ['point','independent']:
                x=block[block.estimator.eq(estimator)&block.dependence.eq(dependence)].copy()
                x['cell']=x.version+'_'+x.side
                cols=['available','truth_slope','error','squared_error','missing_coverage95','width95','interval_score95']
                index=['station_key','replicate','independence_group','region']
                if x.duplicated(index+['cell']).any():raise ValueError('Duplicate paired cells')
                wide=x.pivot(index=index,columns='cell',values=cols)
                wide.columns=[f'{a}__{b}' for a,b in wide.columns]
                wide=wide.reset_index()
                for name in wide.columns:
                    if name.startswith(('truth_slope__','error__','squared_error__','missing_coverage95__','width95__','interval_score95__')):
                        wide[name]=pd.to_numeric(wide[name],errors='raise')
                if len(wide)!=205:raise ValueError('Unexpected original archive denominator')
                labels=[v+'_'+s for v in VERSIONS for s in SIDES]
                flags=[wide['available__'+k].fillna(False).astype(bool) for k in labels]
                common=np.logical_and.reduce(flags);valid=wide.loc[common].copy()
                truth=valid['truth_slope__original_baseline'].to_numpy(float)
                for name in labels:
                    if not np.allclose(truth,valid['truth_slope__'+name],rtol=0,atol=1e-8,equal_nan=False):raise ValueError('Six-way truth reference differs')
                groups=sorted(valid.independence_group.unique())
                sampled=rng.integers(len(groups),size=(4000,len(groups))) if groups else np.empty((0,0),int)
                interval=common.copy()
                if dependence=='independent':
                    for name in labels:
                        for metric in ['missing_coverage95','width95','interval_score95']:
                            interval &= pd.to_numeric(wide[metric+'__'+name],errors='coerce').notna().to_numpy()
                iv=wide.loc[interval]
                for version in VERSIONS:
                    d=valid['squared_error__'+version+'_stress']-valid['squared_error__'+version+'_baseline']
                    cluster=valid.assign(delta=d).groupby('independence_group')['delta'].agg(['sum','count','mean']).reindex(groups)
                    bootstrap=cluster['sum'].to_numpy()[sampled].sum(axis=1)/cluster['count'].to_numpy()[sampled].sum(axis=1) if groups else np.array([])
                    row={'scenario':scenario,'estimator':estimator,'dependence':dependence,'version':version,
                         'n_expected':len(wide),'n_common_six_way':len(valid),'n_stations':valid.station_key.nunique(),'n_groups':len(groups),
                         'baseline_available':int(wide['available__'+version+'_baseline'].fillna(False).astype(bool).sum()),
                         'stress_available':int(wide['available__'+version+'_stress'].fillna(False).astype(bool).sum()),
                         'n_common_intervals':len(iv) if dependence=='independent' else None,
                         'baseline_rmse':float(np.sqrt(valid['squared_error__'+version+'_baseline'].mean())) if len(valid) else np.nan,
                         'stress_rmse':float(np.sqrt(valid['squared_error__'+version+'_stress'].mean())) if len(valid) else np.nan,
                         'baseline_bias':float(valid['error__'+version+'_baseline'].mean()) if len(valid) else np.nan,
                         'stress_bias':float(valid['error__'+version+'_stress'].mean()) if len(valid) else np.nan,
                         'mse_stress_minus_baseline':float(d.mean()) if len(valid) else np.nan,
                         'equal_group_mse_difference':float(cluster['mean'].mean()) if groups else np.nan,
                         'bootstrap_low':float(np.quantile(bootstrap,.025)) if len(bootstrap) else np.nan,
                         'bootstrap_high':float(np.quantile(bootstrap,.975)) if len(bootstrap) else np.nan}
                    if dependence=='independent':
                        for side in SIDES:
                            for metric in ['missing_coverage95','width95','interval_score95']:
                                row[side+'_'+metric]=float(iv[metric+'__'+version+'_'+side].mean()) if len(iv) else np.nan
                    out.append(row)
                    for region in sorted(valid.region.unique()):
                        remain=valid[valid.region!=region]
                        diff=remain['squared_error__'+version+'_stress']-remain['squared_error__'+version+'_baseline']
                        regional.append({'scenario':scenario,'estimator':estimator,'dependence':dependence,'version':version,
                                         'removed_region':region,'n_common':len(remain),'n_groups':remain.independence_group.nunique(),
                                         'baseline_rmse':float(np.sqrt(remain['squared_error__'+version+'_baseline'].mean())) if len(remain) else np.nan,
                                         'stress_rmse':float(np.sqrt(remain['squared_error__'+version+'_stress'].mean())) if len(remain) else np.nan,
                                         'mse_difference':float(diff.mean()) if len(remain) else np.nan})
    return pd.DataFrame(out),pd.DataFrame(regional)

def main():
    M.verify_plan()
    execution=json.loads((M.OUT/'execution.json').read_text())
    if execution['scenario_reanalyses']!=440:raise ValueError('Incomplete scenario execution')
    roster=pd.read_csv(M.EXP/'roster.csv')
    frame=pd.concat([load_pairs(s,roster) for s in M.SCENARIOS],ignore_index=True)
    frame.to_parquet(M.STAGE/'six_way_trends.parquet',index=False)
    summary,regional=summarize(frame)
    summary.to_csv(M.OUT/'six_way_summary.csv',index=False)
    regional.to_csv(M.OUT/'leave_one_region_out.csv',index=False)
    status={'status':'computed','scenario_reanalyses':440,'original_strict_huc17_settings':30,
            'candidate_provider_settings':410,'target_masks_and_daily_features':'identical across source versions',
            'comparison':'six-way common available baseline and stress cases separately for each estimator and dependence',
            'limitations':'Both sensitivities are post-hoc. Candidate providers, role assignments and sample size change together; strict-original excludes the affected HUC17 groups and reduces source sample size. Group bootstrap and fixed-prediction region deletions do not establish independent climate transfer.'}
    (M.OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(summary[summary.dependence.eq('point')].to_string(index=False),flush=True)

if __name__=='__main__':main()
