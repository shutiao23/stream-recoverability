#!/usr/bin/env python3
"""Post-hoc summer-air proxy on the existing jointly masked archives.

The proxy adapts a published summer regression idea to a different target:
max(observed full-year 30-day bound, reconstructed July--August 30-day peak).
It is not the original interannual method, an independent-climate test or a
probabilistic forecast. All case-level outputs remain local private.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
os.umask(0o077)
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v19_revision.data import station_air_series

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';BASE=REV/'whole_archive'
OUT=REV/'summer_proxy_archive';PRIVATE=ROOT/'private/wrr_archive_summer_proxy_20261027'
SOURCE=ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet'
LAGS=np.arange(2,11);METHODS=['plug_in','D2','stochastic_calibrated','summer_air_proxy'];TOL=1e-5

def max_observed_window(values):
    x=np.asarray(values,float)
    if len(x)<30:return np.nan
    finite=np.isfinite(x);count=np.convolve(finite.astype(int),np.ones(30,dtype=int),'valid')
    sums=np.convolve(np.where(finite,x,0.),np.ones(30),'valid')
    return float(np.max(sums[count==30])/30) if np.any(count==30) else np.nan

def apply_masks(values,years,masks):
    """Mask every archive year before fitting; reject invalid or overlapping runs."""
    original=np.asarray(values,float);year=np.asarray(years,int);visible=original.copy()
    for key,runs in masks.items():
        index=np.flatnonzero(year==int(key));seen=set()
        if not len(index):raise ValueError('Mask year absent from input')
        for part in str(runs).split(';'):
            if not part:continue
            start,length=map(int,part.split(':'))
            if start<0 or length<=0 or start+length>len(index):raise ValueError('Mask extends beyond year')
            local=set(range(start,start+length))
            if seen&local:raise ValueError('Overlapping mask runs')
            seen|=local;visible[index[start:start+length]]=np.nan
    return visible

def fit_summer(visible,dates,lagged,target_year,mode,complete_years):
    """Choose a right-aligned 2--10-day air regression using visible training."""
    y=np.asarray(visible,float);idx=pd.DatetimeIndex(dates);x=np.asarray(lagged,float)
    if x.shape!=(len(idx),len(LAGS)) or len(y)!=len(idx):raise ValueError('Daily model dimensions differ')
    years=idx.year.to_numpy();eligible_years={int(k) for k in complete_years if int(k)!=target_year and mode!='forward' or int(k)<2010}
    if len(eligible_years)<3:return None
    train=np.isfinite(y)&idx.month.isin([7,8])&(years!=target_year)&np.isfinite(x).all(axis=1)
    if mode=='forward':train &= years<2010
    if train.sum()<30 or np.unique(years[train]).size<3:return None
    target=y[train];predictors=x[train];yc=target-target.mean();syy=float(yc@yc)
    centered=predictors-predictors.mean(axis=0);sxx=np.sum(centered*centered,axis=0);sxy=centered.T@yc
    good=(sxx>1e-12)&np.isfinite(sxx)&np.isfinite(sxy)&(syy>1e-12)
    if not good.any():return None
    r2=np.full(len(LAGS),-np.inf);r2[good]=sxy[good]**2/(sxx[good]*syy)
    j=int(np.argmax(r2));slope=float(sxy[j]/sxx[j]);intercept=float(target.mean()-slope*predictors[:,j].mean())
    return {'lag':int(LAGS[j]),'intercept':intercept,'slope':slope,'training_r2':float(r2[j]),
            'training_days':int(train.sum()),'training_years':int(np.unique(years[train]).size),
            'max_training_year':int(years[train].max())}

def predict_year(visible,dates,lagged,year,mode,complete_years):
    """Return an annual point respecting observed-window support, or unavailable."""
    idx=pd.DatetimeIndex(dates);block=(idx.year==int(year));summer=block&idx.month.isin([7,8])
    y=np.asarray(visible,float);b=max_observed_window(y[block]);summer_values=y[summer].copy()
    if len(summer_values)!=62:return {'available':False,'reason':'incomplete_summer_calendar','bound':b}
    missing=~np.isfinite(summer_values)
    if not missing.any():
        return {'available':bool(np.isfinite(b)),'reason':'observed_bound_only' if np.isfinite(b) else 'no_observed_window',
                'bound':b,'estimate':float(b) if np.isfinite(b) else np.nan,'summer_missing_days':0}
    model=fit_summer(y,idx,lagged,int(year),mode,complete_years)
    if model is None:return {'available':False,'reason':'insufficient_training_support','bound':b,'summer_missing_days':int(missing.sum())}
    predictor=np.asarray(lagged,float)[summer,model['lag']-2]
    if not np.isfinite(predictor[missing]).all():return {'available':False,'reason':'missing_air_on_gap','bound':b,'summer_missing_days':int(missing.sum())}
    summer_values[missing]=model['intercept']+model['slope']*predictor[missing]
    summer_peak=max_observed_window(summer_values)
    if not np.isfinite(summer_peak):return {'available':False,'reason':'no_reconstructed_summer_window','bound':b,'summer_missing_days':int(missing.sum())}
    estimate=max(float(b),summer_peak) if np.isfinite(b) else summer_peak
    return {'available':True,'reason':'summer_air_fill','bound':b,'estimate':estimate,'summer_missing_days':int(missing.sum()),**model}

def freeze():
    destination=OUT/'plan.json'
    if destination.exists():raise FileExistsError('Preserve existing archive-proxy plan')
    if subprocess.run(['git','check-ignore','-q',str(PRIVATE.relative_to(ROOT))+'/probe'],cwd=ROOT).returncode:
        raise ValueError('Case-level destination is not Git-ignored')
    core=T.load_script('archive_summer_plan_jobs',ROOT/'scripts/431_tr_cases.py');jobs={j['station_key']:j for j in core.jobs_for('source')}
    paths=sorted(BASE.glob('*/*/replicate_*/*/design.json'));entries=[];sites=set()
    for path in paths:
        d=json.loads(path.read_text());site=d['station_key']
        if d.get('family') not in ('calendar','crossed') or d.get('mode') not in ('offline','forward') or d.get('replicate') not in range(20):continue
        if d.get('hidden_values_present_in_visible_archive')!=0 or not d.get('all_masks_applied_before_fitting'):
            raise ValueError('Original archive does not certify jointly hidden target gaps')
        if site not in jobs:raise ValueError('Archive site missing source job')
        annual=path.parent/'annual_predictions.parquet';trends=path.parent/'trends.csv'
        if not annual.is_file() or not trends.is_file():raise FileNotFoundError('Original archive output missing')
        entries.append({'station_key':site,'family':d['family'],'mode':d['mode'],'replicate':int(d['replicate']),
                        'design':str(path.relative_to(ROOT)),'annual':str(annual.relative_to(ROOT)),'trends':str(trends.relative_to(ROOT))})
        sites.add(site)
    keys={(x['station_key'],x['family'],x['mode'],x['replicate']) for x in entries}
    if len(entries)!=3320 or len(keys)!=3320 or len(sites)!=42:raise ValueError('Original archive cohort differs')
    if any(jobs[s].get('latitude') is None or float(jobs[s]['latitude'])<0 for s in sites):
        raise ValueError('July--August proxy requires known Northern Hemisphere stations')
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);OUT.mkdir(parents=True,exist_ok=True)
    private_roster=[{'station_key':s,**jobs[s]} for s in sorted(sites)]
    if len({s.replace('|','_') for s in sites})!=len(sites):raise ValueError('Private filename collision')
    roster_path=PRIVATE/'jobs.json';roster_path.write_text(json.dumps(private_roster,indent=2)+'\n');roster_path.chmod(0o600)
    files=[Path(__file__),ROOT/'scripts/431_tr_cases.py',ROOT/'scripts/521_whole_archive.py',
           ROOT/'src/stream_recoverability/experiments/v19_revision/data.py',SOURCE,T.AIR,T.CONFIG]
    for site in sorted(sites):files.append(Path(jobs[site]['input_path']))
    for e in entries:
        for name in ['design','annual','trends']:files.append(ROOT/e[name])
    records=[]
    for f in dict.fromkeys(files):
        if not f.is_file() or not f.resolve().is_relative_to(ROOT):raise ValueError('Source input missing or outside workspace')
        records.append({'path':str(f.relative_to(ROOT)),})
    manifest=PRIVATE/'input_manifest.json';manifest.write_text(json.dumps(records,indent=2)+'\n');manifest.chmod(0o600)
    cases=PRIVATE/'archive_roster.json';cases.write_text(json.dumps(entries,indent=2)+'\n');cases.chmod(0o600)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'post-hoc after prior archive results and published-method proxy were seen; not preregistered',
          'cohort':'All 3,320 existing archive settings: 42 offline and 41 forward stations, calendar and crossed masks, 20 repetitions; same masks and finite-record target as existing comparisons.',
          'method':'Adapted summer-air point proxy, not the published interannual thermal-peak estimator. Simultaneously mask the original target gaps. For each incomplete year exclude that entire year from the local fit; in forward mode also exclude all years from 2010 onward. Use visible July–August water and 2–10-day right-aligned air means, common finite training rows, select the highest in-sample R-squared (shortest lag for ties). Require three complete training years and 30 finite training days.',
          'prediction':'Retain observed values and fill only missing July–August days. Use the larger of the resulting summer 30-day maximum and the fully observed full-year 30-day lower bound. If summer has no gaps, use the observed full-year bound. Unsupported fits, missing required air or unavailable windows are reported, not replaced with zero.',
          'comparison':'Point estimates only: proxy versus saved plug-in, D2 and calibrated stochastic, on shared annual cases and shared archive-level OLS slopes. Report each method availability, each pairwise cohort and a four-method common cohort; separate nontrivial masked archives. Same support projection for finite bounds.',
          'limitations':'Adaptation, not Beaufort et al. original code, target or data. Post-hoc and synthetic masks; all complete observations and target archive are reused. July–August fill cannot identify a missing peak outside summer. Air is NASA POWER-based, timing may not match water. Group bootstrap is descriptive; model source-region overlap, data rights and independent-climate validation remain unresolved. Deterministic point proxy has no predictive interval.',
          'privacy':'Station-year masks, inputs and case-level outputs are local only; aggregate results may be reviewed separately.',
          }
    destination.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded post-hoc plan for 3,320 original archive settings.',flush=True)

def verify_plan():
    plan=json.loads((OUT/'plan.json').read_text());manifest=PRIVATE/'input_manifest.json'
    for path in [manifest, PRIVATE/'jobs.json', PRIVATE/'archive_roster.json']:
        if not path.is_file():raise ValueError('Frozen archive-proxy roster changed')
    for record in json.loads(manifest.read_text()):
        p=ROOT/record['path']
        if not p.is_file():raise ValueError('Frozen archive input changed: '+record['path'])
    return plan

def source_truth(reference):
    grouped=reference.groupby('year').eval_truth_h30.agg(['min','max','count']).sort_index()
    if grouped.empty or grouped['count'].eq(0).any() or (grouped['max']-grouped['min']).gt(TOL).any():
        raise ValueError('Source reference is absent or inconsistent')
    return grouped['min']

def slope(years,values):
    x=(np.asarray(years,float)-np.mean(years))/10.;return float(np.dot(np.asarray(values,float),x)/(x@x))

def compute_site(job,entries,reference):
    site=job['station_key'];panel=read_temperature_panel(job['input_path']).asfreq('D');panel.columns=panel.columns.astype(str)
    if job['station_id'] not in panel:raise ValueError('Target station absent from panel')
    index=panel.index;air=station_air_series(Path(job['air_input_path']),job['network_id'],job['station_id'],index)
    shift=T.hemisphere_shift_days(job.get('latitude'));dates=index+pd.Timedelta(days=shift)
    water=pd.to_numeric(panel[job['station_id']],errors='coerce').to_numpy(float)
    if air is None:lags=np.full((len(index),len(LAGS)),np.nan)
    else:lags=np.column_stack([air.rolling(int(lag),min_periods=int(lag)).mean().to_numpy(float) for lag in LAGS])
    years=dates.year.to_numpy();annual_rows=[];trend_rows=[]
    complete_original=set()
    for year in np.unique(years):
        block=water[years==year];expected=len(pd.date_range(f'{year}-01-01',f'{year}-12-31'))
        if len(block)==expected and np.isfinite(block).all():complete_original.add(int(year))
    for entry in sorted(entries,key=lambda e:(e['family'],e['mode'],e['replicate'])):
        design=json.loads((ROOT/entry['design']).read_text());masks={int(k):str(v) for k,v in design['masks'].items()}
        visible=apply_masks(water,years,masks);complete=complete_original-set(masks)
        ref=source_truth(reference[reference.design_family.eq(entry['family'])]);eval_years=ref.index.to_numpy(int)
        if entry['mode']=='forward':eval_years=eval_years[eval_years>=2010]
        if len(eval_years)!=design['n_years'] or not set(masks).issubset(set(eval_years)):
            raise ValueError('Archive year set or mask count differs')
        truth=ref.reindex(eval_years).to_numpy(float)
        for yr,value in zip(eval_years,truth):
            observed=max_observed_window(water[years==yr])
            if not np.isclose(value,observed,atol=TOL,rtol=0):raise ValueError('Source reference differs from complete panel')
        annual_path=ROOT/entry['annual'];pred=pd.read_parquet(annual_path)
        if len(pred) and pred.year.duplicated().any() or not set(pred.year.astype(int)).issubset(set(masks)):raise ValueError('Baseline annual cases differ')
        pred=pred.set_index('year') if len(pred) else pd.DataFrame()
        points={m:truth.copy() for m in METHODS};year_details=[]
        for j,yr in enumerate(eval_years):
            if int(yr) not in masks:continue
            item=predict_year(visible,dates,lags,int(yr),entry['mode'],complete)
            baseline=pred.loc[yr] if len(pred) and yr in pred.index else None
            bound=float(item.get('bound',np.nan))
            if baseline is not None:
                old=float(baseline.get('observed_lower_bound__observed_days',np.nan))
                if not np.isclose(old,bound,atol=TOL,rtol=0,equal_nan=True):raise ValueError('Observed bound differs from archived case')
            values={'plug_in':float(baseline.get('h30__policy',np.nan)) if baseline is not None else np.nan,
                    'D2':float(baseline.get('D2',np.nan)) if baseline is not None else np.nan,
                    'stochastic_calibrated':float(baseline.get('stochastic_cal_q50',np.nan)) if baseline is not None else np.nan,
                    'summer_air_proxy':float(item.get('estimate',np.nan)) if item['available'] else np.nan}
            for method,val in values.items():
                if np.isfinite(val) and np.isfinite(bound):values[method]=max(val,bound)
                points[method][j]=values[method]
            year_details.append({'station_key':site,'independence_group':design['independence_group'],'region':design['region'],
                'family':entry['family'],'mode':entry['mode'],'replicate':entry['replicate'],'year':int(yr),'truth':float(truth[j]),
                'observed_bound':bound,'proxy_reason':item['reason'],'summer_missing_days':item.get('summer_missing_days'),
                'fit_lag':item.get('lag'),'fit_days':item.get('training_days'),'fit_max_year':item.get('max_training_year'),**values})
        annual_rows.extend(year_details)
        existing=pd.read_csv(ROOT/entry['trends']);existing=existing[existing.retention.eq('all')&existing.dependence.eq('point')].set_index('estimator')
        ref_slope=slope(eval_years,truth)
        for method in METHODS:
            valid=len(eval_years)>=5 and np.isfinite(points[method]).all()
            value=slope(eval_years,points[method]) if valid else np.nan
            if method!='summer_air_proxy':
                if method not in existing.index:raise ValueError('Missing archived point baseline')
                archived=existing.loc[method]
                if bool(archived.available)!=valid or valid and not np.isclose(float(archived.slope),value,atol=1e-8,rtol=0):
                    raise ValueError('Recomputed projected baseline differs from archived trend')
                if valid and not np.isclose(float(archived.truth_slope),ref_slope,atol=1e-8,rtol=0):raise ValueError('Reference slope differs')
            trend_rows.append({'station_key':site,'independence_group':design['independence_group'],'region':design['region'],
                'family':entry['family'],'mode':entry['mode'],'replicate':entry['replicate'],'n_years':len(eval_years),
                'n_incomplete':len(masks),'estimator':method,'available':bool(valid),'truth_slope':ref_slope,
                'slope':value,'error':value-ref_slope if valid else np.nan})
    return pd.DataFrame(annual_rows),pd.DataFrame(trend_rows)

def execute(workers,pilot):
    verify_plan();jobs=json.loads((PRIVATE/'jobs.json').read_text());entries=json.loads((PRIVATE/'archive_roster.json').read_text())
    if pilot:jobs=jobs[:2];entries=[e for e in entries if e['station_key'] in {x['station_key'] for x in jobs} and e['replicate']<2]
    reference=pd.read_parquet(SOURCE,columns=['station_key','year','design_family','eval_truth_h30'])
    target=PRIVATE/('pilot' if pilot else 'full');target.mkdir(parents=True,exist_ok=True,mode=0o700)
    def one(job):
        site=job['station_key'];annual,trends=compute_site(job,[x for x in entries if x['station_key']==site],reference[reference.station_key.eq(site)])
        for name,frame in [('annual',annual),('trends',trends)]:
            path=target/(site.replace('|','_')+'_'+name+'.parquet')
            if path.exists():pd.testing.assert_frame_equal(pd.read_parquet(path),frame,check_dtype=False,atol=1e-10,rtol=0)
            else:frame.to_parquet(path,index=False);path.chmod(0o600)
        return {'site':site,'annual_rows':len(annual),'trend_rows':len(trends)}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(one,job) for job in jobs];done=[]
        for future in as_completed(futures):
            done.append(future.result());print('Archive proxy stations completed:',len(done),'of',len(jobs),flush=True)
    if len(done)!=len(jobs):raise ValueError('Incomplete station replay')
    report={'status':'pilot_completed' if pilot else 'completed','stations':len(done),'archive_settings':sum(x['trend_rows'] for x in done)//len(METHODS),
            'annual_rows':sum(x['annual_rows'] for x in done),'trend_method_rows':sum(x['trend_rows'] for x in done),
            'scope':'Saved masks and baseline predictions with new train-only summer regression; case-level outputs remain private.',
            'limitations':json.loads((OUT/'plan.json').read_text())['limitations']}
    (OUT/('pilot.json' if pilot else 'execution.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['freeze','pilot','run']);parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args()
    if args.workers<1 or args.workers>8:raise ValueError('Worker count must be between 1 and 8')
    if args.action=='freeze':freeze()
    else:execute(args.workers,args.action=='pilot')
