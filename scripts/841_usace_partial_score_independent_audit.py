#!/usr/bin/env python3
"""Independently recalculate interval-censored scores and paired extrema."""
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir'
PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027';DATA=ROOT/'data/external/wrr_usace_reservoir_20261027'

def main():
    runner=T.load_script('usace_score_audit_runner',ROOT/'scripts/838_usace_partial_history_predict.py')
    status=json.loads((OUT/'partial_history_score_status.json').read_text());src=PRIVATE/'partial_history_scored_cases.parquet'
    cases=pd.read_parquet(src);bounds=pd.read_csv(DATA/'partial_year_h30_bounds.csv').set_index(['resource_id','year'])
    roster=pd.read_csv(PRIVATE/'partial_history_roster.csv');original=[]
    for r in roster.itertuples(index=False):
        path=PRIVATE/'partial_history_predictions'/r.resource_id/str(r.year)/'predictions.parquet'
        item=pd.read_parquet(path);item['resource_id']=r.resource_id;original.append(item)
    raw=pd.concat(original,ignore_index=True).set_index(['resource_id','year','realization_id'],verify_integrity=True)
    labels={'plug_in':'h30__policy','D2':'D2','stochastic':'stochastic_cal_q50'}
    metrics=[];pair_values=[]
    for r in cases.itertuples(index=False):
        key=(r.resource_id,r.year,r.realization_id);o=raw.loc[key];b=bounds.loc[(r.resource_id,r.year)]
        l=float(b.h30_lower_c);u=float(b.h30_upper_c)
        if not math.isclose(l,r.h30_lower_c,abs_tol=1e-10) or not math.isclose(u,r.h30_upper_c,abs_tol=1e-10):raise AssertionError('Bound join changed')
        predictions={name:float(o[col]) for name,col in labels.items()}
        if not all(math.isfinite(x) for x in predictions.values()):continue
        for name,x in predictions.items():
            low=0.0 if l<=x<=u else min(abs(x-l),abs(x-u));high=max(abs(x-l),abs(x-u))
            if not math.isclose(low,getattr(r,name+'_err_low'),abs_tol=1e-10) or not math.isclose(high,getattr(r,name+'_err_high'),abs_tol=1e-10):raise AssertionError('Incorrect absolute error interval')
            item={'resource_id':r.resource_id,'year':r.year,'narrow':u-l<=.1+1e-12,'estimator':name,
                  'low':low,'high':high,'bias_low':x-u,'bias_high':x-l,'definite_fail':low>.5,'possible_fail':high>.5}
            if name!='plug_in':
                prefix='D2' if name=='D2' else 'stochastic_cal';a=float(o[prefix+'_q05']);z=float(o[prefix+'_q95'])
                item.update(interval_finite=math.isfinite(a) and math.isfinite(z),definite_coverage=a<=l+1e-10 and z>=u-1e-10,
                            possible_coverage=a<=u+1e-10 and z>=l-1e-10,width=z-a)
                if item['interval_finite'] != getattr(r,name+'_interval_finite') or item['definite_coverage'] != getattr(r,name+'_definite_coverage') or item['possible_coverage'] != getattr(r,name+'_possible_coverage'):
                    raise AssertionError('Coverage interval differs')
            metrics.append(item)
        x=predictions['D2']
        for name in ['plug_in','stochastic']:
            q=predictions[name];knots=[l,u,min(max(x,l),u),min(max(q,l),u)]
            differences=[abs(x-t)-abs(q-t) for t in knots]
            pair_values.append({'narrow':u-l<=.1+1e-12,'contrast':'D2_minus_'+name,'low':min(differences),'high':max(differences)})
    met=pd.DataFrame(metrics);pairs=pd.DataFrame(pair_values);saved=pd.read_csv(OUT/'partial_history_score_summary.csv');saved_pairs=pd.read_csv(OUT/'partial_history_score_pairs.csv')
    for cohort in ['all','reference_width_at_most_0.1_posthoc']:
        for name in labels:
            t=met[met.estimator.eq(name)&(met.narrow if cohort!='all' else True)];s=saved[(saved.cohort==cohort)&(saved.estimator==name)].iloc[0]
            checks={'common_cases':len(t),'common_station_years':len(t[['resource_id','year']].drop_duplicates()),'common_sites':t.resource_id.nunique(),
              'mae_lower_c':t.low.mean(),'mae_upper_c':t.high.mean(),'bias_lower_c':t.bias_low.mean(),'bias_upper_c':t.bias_high.mean(),
              'failure_rate_definite':t.definite_fail.mean(),'failure_rate_possible':t.possible_fail.mean()}
            if name!='plug_in':
                v=t[t.interval_finite];checks.update(interval_common_cases=len(v),coverage_definite=v.definite_coverage.mean(),coverage_possible=v.possible_coverage.mean(),mean_interval_width_c=v.width.mean())
            for key,value in checks.items():
                if not math.isclose(value,float(s[key]),abs_tol=1e-10,rel_tol=0):raise AssertionError('Summary mismatch: '+key)
        for label in ['D2_minus_plug_in','D2_minus_stochastic']:
            t=pairs[pairs.contrast.eq(label)&(pairs.narrow if cohort!='all' else True)];s=saved_pairs[(saved_pairs.cohort==cohort)&(saved_pairs.contrast==label)].iloc[0]
            if not math.isclose(t.low.mean(),s.mean_absolute_error_difference_lower_c,abs_tol=1e-10) or not math.isclose(t.high.mean(),s.mean_absolute_error_difference_upper_c,abs_tol=1e-10):raise AssertionError('Paired extrema differ')
    result={'status':'passed','cases_checked':len(cases),'common_cases_checked':len(met)//3,'summary_cells_checked':len(saved),'paired_cells_checked':len(saved_pairs),
      'scope':'Scalar point-to-reference bounds, coverage and paired extrema from saved predictions and annual reference intervals; common-cohort summaries recomputed.',
      'limitations':'This audit does not independently fit the source model, verify source data quality, justify interval assumptions, or establish independent climates.'}
    (OUT/'partial_history_score_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
