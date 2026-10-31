#!/usr/bin/env python3
"""Independently recompute source factorial targets, scores and group contrasts."""
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'source_partial_history_factorial';OPEN=REV/'open_observed_record_snapshot';PRIVATE=ROOT/'private/wrr_source_partial_history_factorial_20261027'

def main():
    worker=T.load_script('source_history_audit_worker',ROOT/'scripts/850_source_partial_history_factorial.py');worker.verify()
    status=json.loads((OUT/'scoring_status.json').read_text())
    r=pd.read_csv(OUT/'roster.csv');case=pd.read_parquet(PRIVATE/'scored_cases.parquet');daily=pd.read_parquet(OPEN/'daily_temperature.parquet');daily['date']=pd.to_datetime(daily.date)
    truth={}
    for station in r.station_key:
        d=daily[daily.station_key.eq(station)&daily.date.dt.year.eq(2017)].sort_values('date')
        if len(d)!=365 or not np.isfinite(d.water_c).all():raise ValueError('Reference incomplete')
        t=max(sum(d.water_c.iloc[i:i+30].astype(float))/30 for i in range(336));truth[station]=t
    cases={};variants={('full',0),('full',8),('partial',0),('partial',8)}
    for key,g in case.groupby(['station_key','realization_id']):
        if len(g)!=4 or set(zip(g.history_mode,g.counterfactual_complete_count))!=variants or g.mask_runs.nunique()!=1:raise AssertionError('Factorial mask/cohort differs')
        if not np.allclose(g.truth,truth[key[0]],atol=1e-5,rtol=0):raise AssertionError('Reported H30 differs')
        cases[key]={(x.history_mode,int(x.counterfactual_complete_count)):x for x in g.itertuples(index=False)}
    if len(cases)!=status['target_cases']:raise AssertionError('Target case count differs')
    metrics=[];effects=[]
    for (station,realization),v in cases.items():
        y=truth[station];valid=True
        for x in v.values():
            valid &= all(math.isfinite(float(getattr(x,k))) for k in ['D2','D2_q05','D2_q95','h30__policy','stochastic_cal_q05','stochastic_cal_q50','stochastic_cal_q95'])
        if not valid:continue
        info=r.set_index('station_key').loc[station];errors={}
        for mode,count in [('full',0),('full',8),('partial',0),('partial',8)]:
            x=v[(mode,count)];label=f'D2_{mode}_count{count}';error=abs(float(x.D2)-y);lo=float(x.D2_q05);hi=float(x.D2_q95);bound=float(x.observed_lower_bound__observed_days)
            if np.isfinite(bound) and min(float(x.D2),lo)<bound-1e-9:raise AssertionError('D2 below observed bound')
            errors[label]=error;metrics.append({'station':station,'group':info.independence_group,'scenario':label,'error':error,'bias':float(x.D2)-y,
              'coverage':lo<=y<=hi,'width':hi-lo,'interval_score':hi-lo+20*max(lo-y,0)+20*max(y-hi,0)})
        for mode,count in [('full',8),('partial',0)]:
            x=v[(mode,count)]
            for name,point,lo,hi in [('plug_in',float(x.h30__policy),None,None),('stochastic',float(x.stochastic_cal_q50),float(x.stochastic_cal_q05),float(x.stochastic_cal_q95))]:
                label=f'{name}_{mode}';error=abs(point-y);errors[label]=error
                item={'station':station,'group':info.independence_group,'scenario':label,'error':error,'bias':point-y}
                if lo is not None:item.update(coverage=lo<=y<=hi,width=hi-lo,interval_score=hi-lo+20*max(lo-y,0)+20*max(y-hi,0))
                metrics.append(item)
        effect={'D2_actual_partial_minus_full':errors['D2_partial_count0']-errors['D2_full_count8'],
          'D2_history_effect_averaged_counts':((errors['D2_partial_count0']-errors['D2_full_count0'])+(errors['D2_partial_count8']-errors['D2_full_count8']))/2,
          'D2_count8_minus0_averaged_histories':((errors['D2_full_count8']-errors['D2_full_count0'])+(errors['D2_partial_count8']-errors['D2_partial_count0']))/2,
          'D2_history_count_interaction':(errors['D2_partial_count8']-errors['D2_partial_count0'])-(errors['D2_full_count8']-errors['D2_full_count0']),
          'plugin_partial_minus_full':errors['plug_in_partial']-errors['plug_in_full'],
          'stochastic_partial_minus_full':errors['stochastic_partial']-errors['stochastic_full']}
        effects.extend({'station':station,'group':info.independence_group,'provider':info.provider,'contrast':k,'value':z} for k,z in effect.items())
    met=pd.DataFrame(metrics);eff=pd.DataFrame(effects);summary=pd.read_csv(OUT/'score_summary.csv');paired=pd.read_csv(OUT/'paired_effects.csv');grouped=pd.read_csv(OUT/'group_effects.csv')
    for row in summary.itertuples(index=False):
        g=met[met.scenario.eq(row.scenario)];checks={'common_cases':len(g),'stations':g.station.nunique(),'groups':g.group.nunique(),
           'mae_case_equal':g.error.mean(),'bias_case_equal':g.bias.mean(),'mae_station_equal':g.groupby('station').error.mean().mean(),'mae_group_equal':g.groupby('group').error.mean().mean()}
        if row.scenario.startswith(('D2_','stochastic_')):checks.update(coverage90=g.coverage.mean(),width90=g.width.mean(),interval_score90=g.interval_score.mean())
        for col,value in checks.items():
            if not math.isclose(float(value),float(getattr(row,col)),abs_tol=1e-8,rel_tol=0):raise AssertionError('Score mismatch '+col)
    rng=np.random.default_rng(20261027)
    for row in paired.itertuples(index=False):
        g=eff[eff.contrast.eq(row.contrast)];gv=g.groupby('group').value.mean();boot=rng.choice(gv.to_numpy(float),size=(4000,len(gv)),replace=True).mean(axis=1)
        checks={'common_cases':len(g),'case_equal':g.value.mean(),'station_equal':g.groupby('station').value.mean().mean(),'group_equal':gv.mean(),
                'group_bootstrap_low':np.quantile(boot,.025),'group_bootstrap_high':np.quantile(boot,.975),'n_groups':len(gv)}
        for col,value in checks.items():
            if not math.isclose(float(value),float(getattr(row,col)),abs_tol=1e-8,rel_tol=0):raise AssertionError('Contrast mismatch '+col)
        for group,val in gv.items():
            h=grouped[(grouped.contrast==row.contrast)&(grouped.independence_group==group)]
            if len(h)!=1 or not math.isclose(float(h.mean_contrast.iloc[0]),float(val),abs_tol=1e-8,rel_tol=0):raise AssertionError('Group result differs')
    result={'status':'passed','stations':len(r),'complete_target_years':len(truth),'target_cases':len(cases),'factorial_case_rows':len(case),
      'summary_cells':len(summary),'paired_contrasts':len(paired),'group_contrasts':len(grouped),'bootstrap_draws_per_contrast':4000,
      'scope':'Independently recomputes source-reference H30 from 365 saved daily values, common masks, scalar scores, factorial contrasts, six-group bootstrap and observed-bound constraints.',
      'limitations':'Does not refit source models, validate source sensor QA, establish independent climates or prove an operational interpretation for false history-count interventions.'}
    (OUT/'independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
