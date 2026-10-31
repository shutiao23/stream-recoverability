#!/usr/bin/env python3
"""Pair expanded stresses with original archives and verify visible masks.

Writes case-level detail only to the local private directory. Repeated masks
are not independent climates; neither scenario guarantees out-of-sample safety.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[name]='1'
os.umask(0o077)
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v19_revision.data import station_air_series

ROOT=T.ROOT
REV=ROOT/'results/wrr_review_response_20261027'
OUT=REV/'expanded_stress'
PRIVATE=ROOT/'private/wrr_expanded_stress_20261027'
BASE=REV/'whole_archive'
SCENARIOS=['synchronized_donors','heat_associated_matched']
KEY=['station_key','replicate','estimator','retention','dependence']

def verify_plan():
    plan=json.loads((OUT/'plan.json').read_text())
    manifest=PRIVATE/'input_manifest.json'
    for row in json.loads(manifest.read_text()):
        path=Path(row['path']);path=path if path.is_absolute() else ROOT/path
    return plan

def station_data(job, reference):
    panel=read_temperature_panel(job['input_path']).asfreq('D')
    panel.columns=panel.columns.astype(str)
    original_index=panel.index
    air=station_air_series(Path(job['air_input_path']),job['network_id'],job['station_id'],original_index)
    shift=T.hemisphere_shift_days(job.get('latitude'))
    panel.index+=pd.Timedelta(days=shift)
    hot={}
    if air is not None:
        air.index=panel.index
        years=sorted(reference.year.unique())
        means=[]
        for year in years:
            vals=air.loc[air.index.year==year].to_numpy(float)
            means.append(float(np.max(T.window_means(vals,30))) if len(vals)>=30 and np.isfinite(vals).all() else np.nan)
        means=np.asarray(means)
        if np.isfinite(means[:7]).sum()>=4 and np.isfinite(means).all():
            cutoff=np.nanquantile(means[:7],.8)
            hot=dict(zip(map(int,years),map(bool,means>=cutoff)))
    return panel,hot

def gap_observation_counts(panel,station,masks):
    hidden_days=0; donor_values=0; donors=set()
    others=panel.columns.difference([station])
    for year,runs in masks.items():
        block=panel.loc[panel.index.year==int(year)]
        for run in str(runs).split(';'):
            if not run:continue
            start,length=map(int,run.split(':'))
            selected=block.iloc[start:start+length]
            hidden_days+=len(selected)
            finite=np.isfinite(selected[others].to_numpy(float))
            donor_values+=int(finite.sum())
            donors.update(others[finite.any(axis=0)].tolist())
    return hidden_days,donor_values,len(donors)

def main():
    plan=verify_plan()
    roster=pd.read_csv(PRIVATE/'roster.csv')
    core=T.load_script('expanded_stress_jobs',ROOT/'scripts/431_tr_cases.py')
    jobs={j['station_key']:j for j in core.jobs_for('source')}
    ref=pd.read_parquet(ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet',columns=['station_key','year','design_family'])
    baseline=pd.read_csv(BASE/'trends.csv')
    baseline=baseline[(baseline.family=='crossed') & (baseline['mode']=='forward') & (baseline.replicate<5)]
    audit=[]
    for site in roster.itertuples(index=False):
        job=jobs[site.station_key]
        panel,hot=station_data(job,ref[(ref.station_key==site.station_key)&(ref.design_family=='crossed')])
        for rep in plan['replicates']:
            suffix=Path('crossed')/'forward'/f'replicate_{rep:02d}'/site.station_key.replace('|','_')
            original=json.loads((BASE/suffix/'design.json').read_text())
            base_masks=original['masks']
            base_days,removed_donor_values,affected_donors=gap_observation_counts(panel,job['station_id'],base_masks)
            for scenario in SCENARIOS:
                folder=PRIVATE/scenario/suffix
                p=folder/'design.json'
                row={'scenario':scenario,'station_key':site.station_key,'replicate':rep,'region':site.region,'independence_group':site.independence_group,
                     'available':p.exists() and (folder/'trends.csv').exists(),'baseline_mask_years':len(base_masks),
                     'baseline_hidden_days':base_days,'donor_observations_removed':removed_donor_values,'affected_donors':affected_donors,
                     'unavailable_reason':None}
                if not row['available']:
                    unavailable=folder/'unavailable.json'
                    row['unavailable_reason']=json.loads(unavailable.read_text()).get('reason','unknown') if unavailable.exists() else 'missing scenario output'
                    audit.append(row);continue
                current=json.loads(p.read_text()); masks=current['masks']
                if current['station_key']!=site.station_key or current['hidden_values_present_in_visible_archive']!=0:
                    raise ValueError(f'Hidden target or station mismatch: {scenario}/{site.station_key}/{rep}')
                if len(base_masks)!=len(masks):raise ValueError(f'Masked-year count changed: {scenario}/{site.station_key}/{rep}')
                if scenario=='synchronized_donors' and base_masks!=masks or current['hidden_donor_values_present']!=0:
                    raise ValueError(f'Donor or target mask mismatch: {site.station_key}/{rep}')
                stress_days,_,_=gap_observation_counts(panel,job['station_id'],masks)
                row.update(stress_mask_years=len(masks),stress_hidden_days=stress_days,
                           identical_masks=base_masks==masks,
                           baseline_hot_years=sum(hot.get(int(y),False) for y in base_masks) if hot else np.nan,
                           stress_hot_years=sum(hot.get(int(y),False) for y in masks) if hot else np.nan,
                           heat_assessed=bool(hot))
                if scenario=='heat_associated_matched' and not hot:
                    raise ValueError('Heat-selected case lacks sufficient air history')
                audit.append(row)
    checks=pd.DataFrame(audit)
    if len(checks)!=2*plan['roster_count']*len(plan['replicates']) or checks.duplicated(['scenario','station_key','replicate']).any():
        raise ValueError('Scenario denominator differs from the frozen roster')
    checks.to_parquet(PRIVATE/'mask_audit.parquet',index=False)
    audit_rows=[]
    for scenario,group in checks.groupby('scenario'):
        ok=group[group.available]
        audit_rows.append({'scenario':scenario,'n_expected':len(group),'n_available':len(ok),'n_unavailable':int((~group.available).sum()),
            'n_stations_available':ok.station_key.nunique(),'n_groups_available':ok.independence_group.nunique(),
            'baseline_masked_years':int(ok.baseline_mask_years.sum()),'stress_masked_years':int(ok.stress_mask_years.sum()),
            'baseline_hidden_days':int(ok.baseline_hidden_days.sum()),'stress_hidden_days':int(ok.stress_hidden_days.sum()),
            'settings_mask_changed':int((~ok.identical_masks.astype(bool)).sum()),
            'settings_with_any_donor_observation_removed':int(ok.donor_observations_removed.gt(0).sum()),
            'stations_with_any_donor_observation_removed':ok.loc[ok.donor_observations_removed.gt(0),'station_key'].nunique(),
            'donor_observations_removed_counting_repeated_masks':int(ok.donor_observations_removed.sum()),
            'baseline_hot_masked_years':int(ok.baseline_hot_years.sum()),'stress_hot_masked_years':int(ok.stress_hot_years.sum()),
            'n_heat_assessed':int(ok.heat_assessed.sum()),
            'masked_years_with_heat_assessment':int(ok.loc[ok.heat_assessed.astype(bool),'baseline_mask_years'].sum()),
            'unavailable_reasons':json.dumps(group.loc[~group.available,'unavailable_reason'].value_counts().to_dict(),ensure_ascii=False)})
    pd.DataFrame(audit_rows).to_csv(OUT/'mask_summary.csv',index=False)
    summaries=[];regional=[]; rng=np.random.default_rng(691)
    for scenario in SCENARIOS:
        stress=pd.read_csv(PRIVATE/scenario/'trends.csv')
        pair=baseline.merge(stress,on=KEY,how='left',suffixes=('_baseline','_stress'),validate='one_to_one')
        pair['available_stress']=pair.available_stress.fillna(False).astype(bool)
        pair.to_parquet(PRIVATE/(scenario+'_paired_trends.parquet'),index=False)
        for estimator in ['D2','stochastic_calibrated']:
            for dep in ['point','independent']:
                g=pair[(pair.estimator==estimator)&(pair.retention=='all')&(pair.dependence==dep)]
                if len(g)!=plan['roster_count']*len(plan['replicates']):raise ValueError('Incorrect expected case count')
                valid=g[g.available_baseline & g.available_stress].copy()
                if len(valid) and not np.allclose(valid.truth_slope_baseline,valid.truth_slope_stress,rtol=0,atol=1e-9):raise ValueError('Reference slope changed')
                delta=valid.squared_error_stress-valid.squared_error_baseline
                groups=valid.assign(delta=delta).groupby('independence_group_baseline')['delta'].agg(['sum','count','mean'])
                draws=rng.integers(len(groups),size=(4000,len(groups))) if len(groups) else np.empty((0,0),int)
                boot=groups['sum'].to_numpy()[draws].sum(axis=1)/groups['count'].to_numpy()[draws].sum(axis=1) if len(groups) else np.array([])
                row={'scenario':scenario,'estimator':estimator,'dependence':dep,'n_expected':len(g),
                     'baseline_available':int(g.available_baseline.sum()),'stress_available':int(g.available_stress.sum()),
                     'n_common':len(valid),'n_stations':valid.station_key.nunique(),'n_groups':len(groups),
                     'baseline_rmse':float(np.sqrt(valid.squared_error_baseline.mean())) if len(valid) else np.nan,
                     'stress_rmse':float(np.sqrt(valid.squared_error_stress.mean())) if len(valid) else np.nan,
                     'mean_mse_difference':float(delta.mean()) if len(valid) else np.nan,
                     'equal_group_mse_difference':float(groups['mean'].mean()) if len(groups) else np.nan,
                     'bootstrap_low':float(np.quantile(boot,.025)) if len(boot) else np.nan,
                     'bootstrap_high':float(np.quantile(boot,.975)) if len(boot) else np.nan}
                if dep=='independent':
                    for field in ['missing_coverage95','width95','interval_score95']:
                        for side in ['baseline','stress']:
                            row[side+'_'+field]=float(valid[field+'_'+side].mean()) if len(valid) else np.nan
                summaries.append(row)
                for region in sorted(valid.region_baseline.unique()):
                    remain=valid[valid.region_baseline!=region]
                    regional.append({'scenario':scenario,'estimator':estimator,'dependence':dep,'removed_region':region,'n_common':len(remain),
                                     'n_groups':remain.independence_group_baseline.nunique(),
                                     'baseline_rmse':float(np.sqrt(remain.squared_error_baseline.mean())) if len(remain) else np.nan,
                                     'stress_rmse':float(np.sqrt(remain.squared_error_stress.mean())) if len(remain) else np.nan,
                                     'mse_difference':float((remain.squared_error_stress-remain.squared_error_baseline).mean()) if len(remain) else np.nan})
    result=pd.DataFrame(summaries);result.to_csv(OUT/'paired_summary.csv',index=False)
    pd.DataFrame(regional).to_csv(OUT/'leave_one_region_out.csv',index=False)
    status={'status':'computed','expected_per_scenario':plan['roster_count']*len(plan['replicates']),
            'all_frozen_input_hashes_verified':True,'target_and_synchronized_donor_hidden_values_checked':True,
            'heat_year_count_matched_per_available_archive':True,'masks_and_per_case_scores':'local private',
            'limitation':plan['limitations'],'heat_limitation':plan['heat_limits']}
    (OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(pd.DataFrame(audit_rows).to_string(index=False),flush=True)
    print(result.to_string(index=False),flush=True)

if __name__=='__main__':main()
