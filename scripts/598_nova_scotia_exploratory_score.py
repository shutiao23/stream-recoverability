#!/usr/bin/env python3
"""Run frozen nonconfirmatory NS single-year masking with source-fixed models.

Inputs are reported-clock daily means, not quality-qualified or error-free
truth. Two sites share a province; repeated gaps are not independent climates.
Case-level predictions are retained in an ignored local-only directory.
"""
from __future__ import annotations
import os
for variable in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[variable]='1'
os.umask(0o077)
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from stream_recoverability.seeds import position_index
from stream_recoverability.experiments.tr_revision.statistics import ensemble_crps,interval_score

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory'
SOURCE=ROOT/'results/wrr_review_completion_20261024'
PRIVATE=ROOT/'private/wrr_nova_scotia_exploratory_20261026'
LEVELS=[5,10,25,50,75,90,95]

def score_tables(data,draw_function):
    """Score on all eligible cases and pair quantile methods on identical cases."""
    if not data.design_family.eq('crossed').all():raise ValueError('unexpected mask family')
    if not np.isfinite(data.eval_truth_h30.to_numpy(float)).all():raise ValueError('missing reported reference')
    rows=[];pairs=[];site_rows=[]
    for stratum,mask in [('all',np.ones(len(data),bool)),('danger',data.peak_overlap.ge(.5).to_numpy())]:
        b=data.loc[mask].copy();y=b.eval_truth_h30.to_numpy(float);lower=b.observed_lower_bound__observed_days.to_numpy(float)
        for name,column,prefix in [('plug_in','h30__policy',None),('D2','D2','D2'),('stochastic_calibrated','stochastic_cal_q50','stochastic_cal')]:
            point=b[column].to_numpy(float);point=np.where(np.isfinite(lower),np.maximum(point,lower),point)
            valid=np.isfinite(point)&np.isfinite(y)
            row={'stratum':stratum,'estimator':name,'n_eligible':len(b),'n_point_available':int(valid.sum()),
                 'point_availability':float(valid.mean()) if len(b) else np.nan,'n_interval_available':0}
            if valid.any():
                error=point[valid]-y[valid]
                row.update(mae=float(np.mean(abs(error))),bias=float(np.mean(error)),failure_rate=float(np.mean(abs(error)>.5)))
            if prefix:
                q=b[[f'{prefix}_q{x:02d}' for x in LEVELS]].to_numpy(float)
                good=valid&np.isfinite(q).all(axis=1)
                row['n_interval_available']=int(good.sum())
                if good.any():
                    if (q[good,0]>q[good,-1]+1e-8).any() or np.any(np.isfinite(lower[good]) & (q[good,0]<lower[good]-1e-8)):
                        raise ValueError('quantile ordering or support violation')
                    samples=draw_function(q[good],lower[good]);lo=q[good,0];hi=q[good,-1]
                    row.update(coverage90=float(np.mean((y[good]>=lo-1e-8)&(y[good]<=hi+1e-8))),
                      width90=float(np.mean(hi-lo)),interval_score90=float(np.mean(interval_score(lo,hi,y[good]))),
                      crps=float(np.mean(ensemble_crps(samples,y[good]))))
            rows.append(row)
        a=b.D2.to_numpy(float);s=b.stochastic_cal_q50.to_numpy(float)
        qa=b[[f'D2_q{x:02d}' for x in LEVELS]].to_numpy(float);qs=b[[f'stochastic_cal_q{x:02d}' for x in LEVELS]].to_numpy(float)
        common=np.isfinite(a)&np.isfinite(s)&np.isfinite(y)&np.isfinite(qa).all(axis=1)&np.isfinite(qs).all(axis=1)
        pair={'stratum':stratum,'n_eligible':len(b),'n_common':int(common.sum()),'common_availability':float(common.mean()) if len(b) else np.nan,
              'stations':int(b.loc[common,'station_key'].nunique()),'station_years':len(b.loc[common,['station_key','year']].drop_duplicates())}
        if common.any():
            for name,point,q in [('D2',a,qa),('stochastic',s,qs)]:
                yv=y[common];lo=q[common,0];hi=q[common,-1]
                pair[name+'_mae']=float(np.mean(abs(point[common]-yv)))
                pair[name+'_coverage90']=float(np.mean((yv>=lo-1e-8)&(yv<=hi+1e-8)))
                pair[name+'_width90']=float(np.mean(hi-lo))
                pair[name+'_interval_score90']=float(np.mean(interval_score(lo,hi,yv)))
                pair[name+'_crps']=float(np.mean(ensemble_crps(draw_function(q[common],lower[common]),yv)))
        pairs.append(pair)
    for (site,year),g in data.groupby(['station_key','year'],sort=True):
        y=g.eval_truth_h30.to_numpy(float);a=g.D2.to_numpy(float);s=g.stochastic_cal_q50.to_numpy(float)
        q1=g[[f'D2_q{x:02d}' for x in LEVELS]].to_numpy(float);q2=g[[f'stochastic_cal_q{x:02d}' for x in LEVELS]].to_numpy(float)
        ok=np.isfinite(a)&np.isfinite(s)&np.isfinite(y)&np.isfinite(q1).all(axis=1)&np.isfinite(q2).all(axis=1)
        row={'station_key':site,'year':int(year),'n_eligible':len(g),'n_common':int(ok.sum())}
        if ok.any():
            row.update(D2_mae=float(np.mean(abs(a[ok]-y[ok]))),stochastic_mae=float(np.mean(abs(s[ok]-y[ok]))),
                D2_coverage90=float(np.mean((y[ok]>=q1[ok,0]-1e-8)&(y[ok]<=q1[ok,-1]+1e-8))),
                stochastic_coverage90=float(np.mean((y[ok]>=q2[ok,0]-1e-8)&(y[ok]<=q2[ok,-1]+1e-8))))
        site_rows.append(row)
    return pd.DataFrame(rows),pd.DataFrame(pairs),pd.DataFrame(site_rows)

def main():
    import wrr_tr_common as T
    plan=json.loads((OUT/'plan.json').read_text());lock=json.loads((OUT/'source_calibration_lock.json').read_text())
    ref=json.loads((OUT/'reference_status.json').read_text());forcing=json.loads((OUT/'forcing_status.json').read_text())
    if plan['status']!='frozen_exploratory_amendment' or ref['status']!='reported_clock_reference_built' or forcing['status']!='forcing_complete':raise RuntimeError('frozen inputs unavailable')
    model=ROOT/plan['source_model'];settings_path=SOURCE/'independent_study/source_case_settings.json';generator_path=SOURCE/'independent_study/source_missingness_generator.json';calpath=ROOT/lock['calibration_path']
    if not lock['source_roles_disjoint']:raise RuntimeError('source roles not confirmed')
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);PRIVATE.chmod(0o700)
    if (PRIVATE/'predictions.parquet').exists() or (OUT/'score_status.json').exists():raise RuntimeError('existing scoring output will not be overwritten')
    roster=pd.read_csv(OUT/'reference_year_roster.csv',dtype={'station_id':str})
    air=OUT/'air_forcing.parquet'
    inputs={'panels':sorted(roster.station_id.unique())}
    snapshot=PRIVATE/'score_inputs.json'
    if snapshot.exists():
        if json.loads(snapshot.read_text())!=inputs:raise RuntimeError('case-cache inputs changed')
    else:snapshot.write_text(json.dumps(inputs,indent=2)+'\n');snapshot.chmod(0o600)
    settings=json.loads(settings_path.read_text());settings['version']='review_ns_reported_clock_exploratory_20261026';settings['calendar_year_only']=True
    generator=json.loads(generator_path.read_text())
    jobs=[]
    for site,g in roster.groupby('station_id',sort=True):
        row=g.iloc[0]
        jobs.append({'network_id':'ns_'+site,'station_id':site,'station_key':'ns_exploratory|'+site,
          'provider':'ns_exploratory','independence_group':'nova_scotia_shared_climate','latitude':float(row.latitude),
          'input_path':str(OUT/'panels'/f'{site}.csv'),'air_input_path':str(air),
          'statistic_class':'reported_clock_24_hour_mean_QC_unknown','regulation_status':'unknown',
          'region':'nova_scotia','roster':'independent'})
    indices=position_index(f"{j['network_id']}|{j['station_id']}" for j in jobs)
    for job in jobs:job['station_index']=indices[f"{job['network_id']}|{job['station_id']}"]
    core=T.load_script('ns_exploratory_cases',ROOT/'scripts/431_tr_cases.py');core.CACHE=PRIVATE/'case_cache'
    parts=[];case_receipt=PRIVATE/'case_cache_receipt.json'
    existing=json.loads(case_receipt.read_text()) if case_receipt.exists() else {}
    for job in jobs:
        cache=core.cache_path(job,settings);site=job['station_id']
        if cache.exists() and site not in existing:raise RuntimeError('existing case cache has no matching receipt')
        result=core.station_cases(job,settings,generator,[],resume=True)
        if not result.get('cache'):raise RuntimeError(f"case generation unavailable for {site}: {result.get('reason')}")
        path=Path(result['cache']);path.chmod(0o600);case_receipt.write_text(json.dumps(existing,indent=2)+'\n');case_receipt.chmod(0o600)
        frame=pd.read_parquet(path)
        if set(frame.year.unique())!=set(roster.loc[roster.station_id.eq(site),'year']):raise ValueError('evaluated years differ from frozen roster')
        parts.append(frame);print('Generated masked cases for',site,'rows',len(frame),flush=True)
    cases=pd.concat(parts,ignore_index=True)
    if not cases.design_family.eq('crossed').all():raise ValueError('unplanned empirical calendars generated')
    if cases.duplicated(['station_key','year','design_family','realization_id','mask_runs']).any():raise ValueError('duplicate case identity')
    bundle=joblib.load(model);cal=json.loads(calpath.read_text())
    if cal['D2_calibration_groups']!=bundle['roles']['interval_calibration']:raise ValueError('source interval calibration role differs')
    bundle['offsets']=cal['D2_offsets']
    inference=T.load_script('ns_exploratory_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
    result=inference.classical_predictions(inference.predict(cases,bundle),cal)
    lower=result.observed_lower_bound__observed_days.to_numpy(float);truth=result.eval_truth_h30.to_numpy(float)
    if np.any(np.isfinite(lower)&np.isfinite(truth)&(truth<lower-1e-8)):raise ValueError('reference contradicts observed lower bound')
    scorer=T.load_script('ns_exploratory_quantiles',ROOT/'scripts/528_review_response_annual.py')
    summary,paired,by_year=score_tables(result,scorer.quantile_samples)
    cases.to_parquet(PRIVATE/'cases.parquet',index=False);(PRIVATE/'cases.parquet').chmod(0o600)
    result.to_parquet(PRIVATE/'predictions.parquet',index=False);(PRIVATE/'predictions.parquet').chmod(0o600)
    summary.to_csv(OUT/'score_summary.csv',index=False);paired.to_csv(OUT/'paired_summary.csv',index=False);by_year.to_csv(OUT/'site_year_summary.csv',index=False)
    status={'status':'exploratory_scored','cases':len(result),'stations':int(result.station_key.nunique()),
        'station_years':len(result[['station_key','year']].drop_duplicates()),'mask_family':'controlled crossed gaps only',
        'strict_reference_qualified':False,'prior_water_values_opened':True,'prior_prediction_outcomes_before_plan':False,
        'source_model':'fixed global source model with frozen source-only calibration','reference':'reported-clock means of 24 numeric hourly cells, matched between two releases of one provincial programme',
        'limitations':plan['limitations']+'; NASA POWER and water day may use different time bases; source-tail model remains assumed'}
    (OUT/'score_status.json').write_text(json.dumps(status,indent=2)+'\n')
    for name in ['reference_status.json','forcing_status.json']:
        path=OUT/name;prior=json.loads(path.read_text());prior['model_scoring_performed']=True
        prior['scoring_scope']='separate reported-clock exploratory experiment; strict reference remains unqualified'
        path.write_text(json.dumps(prior,indent=2)+'\n')
    print(summary.to_string(index=False));print(paired.to_string(index=False));print(json.dumps(status,indent=2))

if __name__=='__main__':main()
