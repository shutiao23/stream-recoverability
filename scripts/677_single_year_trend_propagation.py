#!/usr/bin/env python3
"""Replay paired joint trend draws under two annual-interval extensions.

All sampled records remain local; this is a post-hoc sensitivity, not a
calibrated joint distribution or an independent-climate validation.
"""
from __future__ import annotations
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[key]='1'
os.umask(0o077)
import argparse
import json
from pathlib import Path
import subprocess
import numpy as np
import pandas as pd
from joblib import Parallel,delayed
import wrr_tr_common as T
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v19_revision.data import station_air_series
from stream_recoverability.experiments.tr_revision.archive import (LEVELS, apply_observed_lower_bound, history_ranks,
    marginal_draws, mask_archive, reorder_marginals, trend_result)
from stream_recoverability.seeds import plain_seed

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity'
PRIVATE=ROOT/'private/wrr_open_source_sensitivity_20261026';STAGE=PRIVATE/'whole_archive'
BASE=ROOT/'results/wrr_review_completion_20261024';METHODS={'D2':'D2','stochastic_calibrated':'stochastic_cal'}
DEPENDENCES=['independent','shared_parameters','residual_blocks'];TOL=1e-8

def adjust_quantiles(q,bounds,mask,radius,scheme):
    q=np.asarray(q,float);bounds=np.asarray(bounds,float);mask=np.asarray(mask,bool)
    if q.ndim!=2 or q.shape[1]!=7 or bounds.shape!=(len(q),) or mask.shape!=(len(q),):raise ValueError('invalid marginal shapes')
    if radius<0 or not np.isfinite(radius) or not np.isfinite(q).all() or (np.diff(q,axis=1)<-TOL).any():raise ValueError('invalid source quantiles or radius')
    weights={'baseline':np.zeros(7),'endpoint_only':np.array([-1,0,0,0,0,0,1.]),
             'tapered':np.array([-1,-.8,-.4,0,.4,.8,1.])}.get(scheme)
    if weights is None:raise ValueError('unknown marginal scheme')
    out=q.copy();out[mask]+=radius*weights
    out=apply_observed_lower_bound(out,bounds)
    if (np.diff(out,axis=1)<-TOL).any() or not np.allclose(out[:,3],q[:,3],atol=TOL,rtol=0):raise ValueError('adjustment changed order or median')
    if not np.allclose(out[~mask],q[~mask],atol=TOL,rtol=0):raise ValueError('complete-year distribution changed')
    return out

def hashes(plan):
    receipts=sorted(STAGE.glob('crossed/forward/replicate_*/*/open_source_receipt.json'))
    for p in receipts:sig.update(str(p.relative_to(STAGE)).encode()+b'\0'+p.read_bytes())
    if len(receipts)!=820:
        raise ValueError('Candidate archive receipts changed')

def compare_saved(computed,saved):
    for col in ['truth_slope','slope','error','squared_error','lower95','upper95','width95','interval_score95']:
        if not np.isclose(float(computed[col]),float(saved[col]),atol=1e-8,rtol=0,equal_nan=True):
            raise ValueError('Replayed baseline differs: '+col)
    if bool(computed['missing_coverage95'])!=bool(saved['missing_coverage95']):raise ValueError('Replayed baseline coverage differs')

def work(job,reference,rep,radii,stage,plan_hash,impl_hash):
    folder=stage/f'replicate_{rep:02d}'/job['station_key'].replace('|','_')
    candidate=STAGE/'crossed'/'forward'/f'replicate_{rep:02d}'/job['station_key'].replace('|','_')
    if not (candidate/'open_source_receipt.json').is_file():raise ValueError('Missing candidate receipt')
    src=candidate/'annual_predictions.parquet';trends=candidate/'trends.csv';design=candidate/'design.json'
    original=json.loads((candidate/'open_source_receipt.json').read_text())
    folder.mkdir(parents=True,exist_ok=True,mode=0o700);receipt=folder/'propagation_receipt.json'
    if receipt.exists():
        prior=json.loads(receipt.read_text())
        return prior
    if (folder/'metrics.csv').exists() or (folder/'marginals_and_ranks.npz').exists():raise ValueError('Incomplete existing output; preserve it for inspection')
    rng=np.random.default_rng(plain_seed(521,job['station_index'],rep))
    all_years=np.array(sorted(reference.year.unique()))
    selected=pd.DataFrame([g.iloc[int(rng.integers(len(g)))] for _,g in reference.groupby('year',sort=True)])
    missing=(rng.random(len(all_years))<.35)&(np.arange(len(all_years))>=7);missing &= all_years>=2010
    masks=dict(zip(all_years[missing],selected.loc[missing,'mask_runs']))
    original_design=json.loads(design.read_text())
    if {str(k):v for k,v in masks.items()}!=original_design['masks'] or original_design['hidden_values_present_in_visible_archive']!=0:
        raise ValueError('Reconstructed masks or hidden-target check differ')
    years=all_years[all_years>=2010];ref=selected.set_index('year');truth=ref.loc[years,'eval_truth_h30'].to_numpy(float)
    if not np.isfinite(truth).all() or len(years)<5:raise ValueError('Invalid complete reference archive')
    mask=np.isin(years,list(masks));n_incomplete=int(mask.sum())
    record={'station_key':job['station_key'],'region':job['region'],'independence_group':job['independence_group'],
            'replicate':rep,'n_incomplete':n_incomplete,}
    if not n_incomplete:
        record['status']='no_incomplete_years';receipt.write_text(json.dumps(record,indent=2)+'\n');return record
    c=pd.read_parquet(src)
    if c.duplicated('year').any() or not set(c.year).issubset(set(years[mask])):raise ValueError('Candidate annual case identities differ from masks')
    positions=pd.Index(years).get_indexer(c.year);quantiles={};bounds=np.full(len(years),np.nan)
    bounds[~mask]=truth[~mask]
    if len(c):bounds[positions]=c.observed_lower_bound__observed_days.to_numpy(float)
    for name,prefix in METHODS.items():
        q=np.repeat(truth[:,None],len(LEVELS),axis=1);q[mask]=np.nan
        if len(c):q[positions]=c[[f'{prefix}_q{int(100*k):02d}' for k in LEVELS]].to_numpy(float)
        quantiles[name]=q
    if not all(np.isfinite(q).all() for q in quantiles.values()):
        record['status']='one_or_both_annual_distributions_unavailable';receipt.write_text(json.dumps(record,indent=2)+'\n');return record
    if np.any(mask & ~np.isfinite(bounds)):
        record['status']='missing_observed_bound';receipt.write_text(json.dumps(record,indent=2)+'\n');return record
    panel=read_temperature_panel(job['input_path']).asfreq('D');panel.columns=panel.columns.astype(str)
    real_index=panel.index;analysis=panel.copy();analysis.index += pd.Timedelta(days=T.hemisphere_shift_days(job.get('latitude')))
    visible=mask_archive(analysis,job['station_id'],masks)
    air=station_air_series(Path(job['air_input_path']),job['network_id'],job['station_id'],real_index)
    if air is not None:air.index=visible.index
    ranks={'independent':rng.normal(size=(256,len(years)))}
    for dep,block in [('shared_parameters',1),('residual_blocks',3)]:
        ranks[dep]=history_ranks(visible[job['station_id']],air,masks,years,draws=256,
            seed=plain_seed(522,job['station_index'],rep),block=block,fit_before=2010)
    if any(v is None for v in ranks.values()):
        record['status']='one_or_more_rank_constructions_unavailable';receipt.write_text(json.dumps(record,indent=2)+'\n');return record
    saved=pd.read_csv(trends);rows=[];npz={'years':years,'truth':truth,'bounds':bounds,'mask':mask,
        'rank_independent':ranks['independent'],'rank_shared_parameters':ranks['shared_parameters'],'rank_residual_blocks':ranks['residual_blocks']}
    for method,q in quantiles.items():
        npz['q_'+method]=q;npz['radius_'+method]=np.array(radii[method]);point=truth.copy();point[mask]=q[mask,3]
        representations={s:adjust_quantiles(q,bounds,mask,radii[method],s) for s in ['baseline','endpoint_only','tapered']}
        if not np.allclose(representations['endpoint_only'][:,[0,-1]],representations['tapered'][:,[0,-1]],atol=TOL,rtol=0):
            raise ValueError('Adjusted 90% endpoints differ')
        for scheme,qscheme in representations.items():
            marginal=marginal_draws(qscheme,draws=256,tails='normal',lower_bounds=bounds)
            for dep in DEPENDENCES:
                draws=reorder_marginals(marginal,ranks[dep])
                if not np.allclose(np.sort(draws,axis=0),np.sort(marginal,axis=0),atol=TOL,rtol=0):raise ValueError('Joint rank changed annual marginals')
                result=trend_result(years,truth,point,draws)
                if scheme=='baseline':
                    comparison=saved.loc[saved.estimator.eq(method)&saved.retention.eq('all')&saved.dependence.eq(dep)]
                    if len(comparison)!=1 or not bool(comparison.iloc[0].available):raise ValueError('Baseline candidate trend unavailable')
                    compare_saved(result,comparison.iloc[0])
                rows.append({'station_key':job['station_key'],'region':job['region'],'independence_group':job['independence_group'],
                             'replicate':rep,'n_incomplete':n_incomplete,'estimator':method,'scheme':scheme,'dependence':dep,**result})
    pd.DataFrame(rows).to_csv(folder/'metrics.csv',index=False)
    np.savez_compressed(folder/'marginals_and_ranks.npz',**npz)
    record.update(status='passed',)
    receipt.write_text(json.dumps(record,indent=2)+'\n')
    return record

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--pilot',type=int,default=0,help='First N supported stations, replicate zero only');parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    if args.pilot<0 or args.workers<1:raise ValueError('Invalid pilot/worker setting')
    if subprocess.run(['git','check-ignore','-q',str(PRIVATE.relative_to(ROOT))+'/probe'],cwd=ROOT).returncode:raise ValueError('Private output is not git-ignored')
    plan_path=OUT/'single_year_trend_plan.json';plan=json.loads(plan_path.read_text());amend=json.loads((OUT/'single_year_trend_plan_amendment.json').read_text())
    if plan['status']!='posthoc_frozen_before_new_trend_propagation' or amend['status']!='clarified_before_trend_propagation':raise ValueError('Frozen trend plan or amendment invalid')
    if list(amend['taper_weights_by_quantile'].values())!=[-1.,-.8,-.4,0.,.4,.8,1.]:raise ValueError('Taper weights do not match frozen amendment')
    hashes(plan)
    support=pd.read_csv(OUT/'single_year_source_support.csv');regions=set(plan['source_supported_regions'])
    radius={}
    for region in regions:
        f=support.loc[support.family.eq('crossed')&support['mode'].eq('forward')&support.region.eq(region)].set_index('estimator')
        if set(f.index)!=set(METHODS) or not f.status.eq('supported_exploratory').all():raise ValueError('Both source radii must be supported')
        radius[region]={m:float(f.loc[m,'empirical_radius']) for m in METHODS}
    core=T.load_script('single_year_trend_jobs',ROOT/'scripts/431_tr_cases.py')
    roster=set(json.loads((ROOT/'results/wrr_review_response_20261027/whole_archive/design.json').read_text())['station_keys'])
    jobs=sorted([j for j in core.jobs_for('source') if j['region'] in regions and j['station_key'] in roster],key=lambda x:x['station_key'])
    if len(jobs)!=plan['supported_target_stations']:raise ValueError('Supported station roster changed')
    if args.pilot:jobs=jobs[:args.pilot]
    reference=pd.read_parquet(BASE/'cases/leave_one_year_out/seed_00.parquet',columns=['station_key','year','design_family','mask_runs','h30__policy','eval_truth_h30'])
    reference=reference.loc[reference.design_family.eq('crossed')]
    consistency=reference.groupby(['station_key','year']).eval_truth_h30.agg(['min','max','count'])
    if consistency['count'].eq(0).any() or (consistency['max']-consistency['min']).gt(TOL).any():raise ValueError('Complete references differ within year')
    stage=PRIVATE/'single_year_trend_propagation'/('pilot_'+str(args.pilot) if args.pilot else 'full');stage.mkdir(parents=True,exist_ok=True,mode=0o700)
    reps=[0] if args.pilot else range(plan['replicates'])
    tasks=[(job,reference.loc[reference.station_key.eq(job['station_key'])],rep,radius[job['region']],stage,plan_hash,impl_hash) for job in jobs for rep in reps]
    print('Paired trend settings:',len(tasks),'pilot:',bool(args.pilot),flush=True)
    results=Parallel(n_jobs=args.workers,verbose=10)(delayed(work)(*task) for task in tasks)
    counts=pd.Series([r['status'] for r in results]).value_counts().to_dict()
    report={'status':'pilot_passed' if args.pilot else 'complete', 'archive_settings':len(results),'status_counts':counts,
            'scope':'post-hoc paired trend propagation with same target masks and rank matrices; no guaranteed joint calibration',
            }
    report_path=OUT/('single_year_trend_pilot.json' if args.pilot else 'single_year_trend_execution.json')
    report_path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
