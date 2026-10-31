#!/usr/bin/env python3
"""Score a fixed 2x2 history-by-count experiment on common target cases."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'source_partial_history_factorial';OPEN=REV/'open_observed_record_snapshot'
PRIVATE=ROOT/'private/wrr_source_partial_history_factorial_20261027'

def inputs():
    worker=T.load_script('source_history_score_worker',ROOT/'scripts/850_source_partial_history_factorial.py');worker.verify()
    status=json.loads((OUT/'prediction_status.json').read_text());roster=pd.read_csv(OUT/'roster.csv')
    if status['status']!='factorial_predictions_complete_not_scored' or status['stations']!=len(roster):raise ValueError('Predictions incomplete')
    receipt={}
    for row in roster.itertuples(index=False):
        base=PRIVATE/'cases'/row.station_key.replace('|','_');info=json.loads(base.with_suffix('.json').read_text());data=base.with_suffix('.parquet')
    return worker,roster,receipt

def freeze():
    path=OUT/'scoring_plan.json'
    if path.exists():raise FileExistsError('Preserve scoring plan')
    worker,roster,receipt=inputs();file=PRIVATE/'scoring_receipts.json';file.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n');file.chmod(0o600)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc analysis fixed after original source and USACE results; factorial predictions exist but reference-error comparisons have not been opened',
      'truth':'Compute 2017 H30 from all 365 saved reported daily values for every fixed station; independently check against saved station-year reference.',
      'cohort':'Require every D2 factorial point and q05/q95 and both history modes plug-in and calibrated stochastic point and q05/q95 to be finite on each station and target mask. Record all exclusions and denominators.',
      'metrics':'On the same common cases report MAE, bias, nominal 90% coverage, width and 90% interval score. Also report equal-station and equal-connected-group means. Classifiers and risk scores are not evaluated.',
      'effects':'For D2 paired absolute errors e(history,count), report true-mode effect e(partial,0)-e(full,8); history effect averaged over count; count effect averaged over history; and interaction [e(partial,8)-e(partial,0)]-[e(full,8)-e(full,0)]. False count settings are counterfactual diagnostics only. For plug-in and stochastic compare partial and full under their actual counts.',
      'uncertainty':'Use fixed-prediction connected-group bootstrap, 4000 resamples of the six observed groups with equal group weighting, seed 20261027; descriptive only. Also report per-group and per-provider contrasts without refitting models.',
      'limitations':'Fifteen preselected source stations, six connected groups, two regions, one target year and a single synthetic warm-season history gap are not representative independent climates. The count intervention is not an operational choice and the factorial effect is specific to this adaptation.',
      }
    path.write_text(json.dumps(plan,indent=2)+'\n');print('Frozen common-case source factorial scoring')

def interval_score(l,u,y):return (u-l)+20*np.maximum(l-y,0)+20*np.maximum(y-u,0)

def run():
    worker,roster,receipt=inputs();plan=json.loads((OUT/'scoring_plan.json').read_text())
    if json.loads((PRIVATE/'scoring_receipts.json').read_text())!=receipt:raise ValueError('Receipt mapping changed')
    pieces=[]
    for r in roster.itertuples(index=False):pieces.append(pd.read_parquet(PRIVATE/'cases'/(r.station_key.replace('|','_')+'.parquet')))
    cases=pd.concat(pieces,ignore_index=True)
    daily=pd.read_parquet(OPEN/'daily_temperature.parquet');daily['date']=pd.to_datetime(daily.date)
    saved=pd.read_parquet(OPEN/'station_years.parquet');saved=saved[saved.year.eq(2017)].set_index('station_key')
    truths={}
    for r in roster.itertuples(index=False):
        a=daily.loc[daily.station_key.eq(r.station_key)&daily.date.dt.year.eq(2017)].sort_values('date')
        dates=pd.date_range('2017-01-01','2017-12-31')
        if len(a)!=365 or not np.array_equal(a.date.to_numpy(),dates.to_numpy()) or not np.isfinite(a.water_c).all():raise ValueError('Target daily reference incomplete')
        h=float(a.water_c.astype(float).rolling(30,min_periods=30).mean().max());truths[r.station_key]=h
        if not np.isclose(h,float(saved.loc[r.station_key,'truth_h30']),atol=1e-5,rtol=0):raise ValueError('Reference H30 differs from saved source')
    cases['truth']=cases.station_key.map(truths)
    key=['station_key','realization_id'];expected=set(zip(roster.station_key.repeat(9),np.tile([f'fixed_{length}_{name}' for length in (30,60,90) for name in ('spring','summer','autumn')],len(roster))))
    if set(zip(cases.station_key,cases.realization_id))!=expected:raise ValueError('Target masks differ from plan')
    variants={}
    for mode in ['full','partial']:
        for count in [0,8]:
            part=cases[cases.history_mode.eq(mode)&cases.counterfactual_complete_count.eq(count)].set_index(key,verify_integrity=True)
            variants[(mode,count)]=part
    index=variants[('full',8)].index
    if any(not v.index.equals(index) for v in variants.values()):raise ValueError('Factorial case order or identity changed')
    masks=np.stack([v.mask_runs.to_numpy() for v in variants.values()]);
    if not np.all(masks==masks[0]):raise ValueError('Target mask differs across interventions')
    for mode in ['full','partial']:
        a,b=variants[(mode,0)],variants[(mode,8)]
        if not np.allclose(a.h30__policy,b.h30__policy,atol=1e-10,rtol=0,equal_nan=True):raise ValueError('Feature-only intervention changed plug-in')
        for col in ['stochastic_cal_q05','stochastic_cal_q50','stochastic_cal_q95']:
            if not np.allclose(a[col],b[col],atol=1e-10,rtol=0,equal_nan=True):raise ValueError('Feature-only intervention changed stochastic output')
    common=np.ones(len(index),dtype=bool)
    for v in variants.values():
        for name in ['D2','D2_q05','D2_q95','h30__policy','stochastic_cal_q05','stochastic_cal_q50','stochastic_cal_q95']:
            common &= np.isfinite(pd.to_numeric(v[name],errors='coerce').to_numpy(float))
    meta=variants[('full',8)].loc[common,['provider','independence_group','truth']].copy()
    if not len(meta):raise ValueError('No common target case')
    summaries=[];errors={};intervals={}
    for (mode,count),v in variants.items():
        v=v.loc[common];y=v.truth.to_numpy(float);point=v.D2.to_numpy(float);lo=v.D2_q05.to_numpy(float);hi=v.D2_q95.to_numpy(float)
        label=f'D2_{mode}_count{count}';errors[label]=pd.Series(np.abs(point-y),index=v.index)
        intervals[label]=pd.DataFrame({'error':np.abs(point-y),'bias':point-y,'coverage':(lo<=y)&(y<=hi),'width':hi-lo,'score':interval_score(lo,hi,y)},index=v.index)
    for mode,count in [('full',8),('partial',0)]:
        v=variants[(mode,count)].loc[common];y=v.truth.to_numpy(float)
        for name,point,lo,hi in [('plug_in',v.h30__policy.to_numpy(float),None,None),('stochastic',v.stochastic_cal_q50.to_numpy(float),v.stochastic_cal_q05.to_numpy(float),v.stochastic_cal_q95.to_numpy(float))]:
            label=f'{name}_{mode}';errors[label]=pd.Series(np.abs(point-y),index=v.index)
            d={'error':np.abs(point-y),'bias':point-y}
            if lo is not None:d.update(coverage=(lo<=y)&(y<=hi),width=hi-lo,score=interval_score(lo,hi,y))
            intervals[label]=pd.DataFrame(d,index=v.index)
    for label,v in intervals.items():
        joined=meta.join(v);row={'scenario':label,'common_cases':len(v),'stations':v.index.get_level_values('station_key').nunique(),'groups':meta.independence_group.nunique(),
          'mae_case_equal':v.error.mean(),'bias_case_equal':v.bias.mean(),'mae_station_equal':v.groupby(level='station_key').error.mean().mean(),
          'mae_group_equal':joined.groupby('independence_group').error.mean().mean()}
        if 'coverage' in v:row.update(coverage90=v.coverage.mean(),width90=v.width.mean(),interval_score90=v.score.mean())
        summaries.append(row)
    e=errors;contrasts={
      'D2_actual_partial_minus_full':e['D2_partial_count0']-e['D2_full_count8'],
      'D2_history_effect_averaged_counts':((e['D2_partial_count0']-e['D2_full_count0'])+(e['D2_partial_count8']-e['D2_full_count8']))/2,
      'D2_count8_minus0_averaged_histories':((e['D2_full_count8']-e['D2_full_count0'])+(e['D2_partial_count8']-e['D2_partial_count0']))/2,
      'D2_history_count_interaction':(e['D2_partial_count8']-e['D2_partial_count0'])-(e['D2_full_count8']-e['D2_full_count0']),
      'plugin_partial_minus_full':e['plug_in_partial']-e['plug_in_full'],
      'stochastic_partial_minus_full':e['stochastic_partial']-e['stochastic_full']}
    rng=np.random.default_rng(20261027);group_rows=[];summary_contrasts=[]
    for label,v in contrasts.items():
        z=meta[['provider','independence_group']].copy();z['contrast']=v;groups=z.groupby('independence_group').contrast.mean();values=groups.to_numpy(float)
        boot=rng.choice(values,size=(4000,len(values)),replace=True).mean(axis=1)
        summary_contrasts.append({'contrast':label,'common_cases':len(v),'case_equal':v.mean(),'station_equal':v.groupby(level='station_key').mean().mean(),
          'group_equal':groups.mean(),'group_bootstrap_low':np.quantile(boot,.025),'group_bootstrap_high':np.quantile(boot,.975),'n_groups':len(groups)})
        for g,val in groups.items():group_rows.append({'contrast':label,'independence_group':g,'provider':z.loc[z.independence_group.eq(g),'provider'].iloc[0],'mean_contrast':val,'cases':int(z.independence_group.eq(g).sum())})
    pd.DataFrame(summaries).to_csv(OUT/'score_summary.csv',index=False);pd.DataFrame(summary_contrasts).to_csv(OUT/'paired_effects.csv',index=False);pd.DataFrame(group_rows).to_csv(OUT/'group_effects.csv',index=False)
    local=PRIVATE/'scored_cases.parquet';cases.to_parquet(local,index=False);local.chmod(0o600)
    result={'status':'completed_posthoc_source_factorial','stations':len(roster),'groups':roster.independence_group.nunique(),'target_cases':len(index),'common_cases':int(common.sum()),
      'limitations':plan['limitations']}
    (OUT/'scoring_status.json').write_text(json.dumps(result,indent=2)+'\n');print(pd.DataFrame(summaries).to_string(index=False));print(pd.DataFrame(summary_contrasts).to_string(index=False));print(json.dumps(result,indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
