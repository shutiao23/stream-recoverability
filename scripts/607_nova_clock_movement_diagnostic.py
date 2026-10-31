#!/usr/bin/env python3
"""Post-hoc paired prediction/feature movement under hypothetical clock shifts."""
import json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_clock_sensitivity'
PRIVATE=ROOT/'private/wrr_nova_scotia_clock_sensitivity_20261026'
KEY=['station_id','year','design_family','realization_id','mask_runs']


def main():
    integrity=json.loads((OUT/'integrity_status.json').read_text());status=json.loads((OUT/'score_status.json').read_text())
    if integrity['status']!='passed':raise RuntimeError('clock sensitivity integrity audit did not pass')
    f=pd.read_parquet(PRIVATE/'predictions.parquet');base=f.loc[f.shift_hours.eq(0)]
    rows=[]
    for shift in [-1,1]:
        d=f.loc[f.shift_hours.eq(shift)].merge(base,on=KEY,how='inner',validate='one_to_one',suffixes=('_shift','_base'))
        if len(d)!=status['all_shift_common_cases']:raise ValueError('movement cohort differs from paired scoring')
        policy=int(d.policy_choice_shift.ne(d.policy_choice_base).sum());difficulty=int(d.difficulty_shift.ne(d.difficulty_base).sum())
        for col in ['eval_truth_h30','h30__policy','D2','stochastic_cal_q50','peak_overlap']:
            x=d[col+'_shift'].to_numpy(float);y=d[col+'_base'].to_numpy(float)
            if not (np.isfinite(x)&np.isfinite(y)).all():raise ValueError('movement cohort has nonfinite values')
            delta=abs(x-y)
            rows.append({'shift_hours':shift,'variable':col,'unit':'fraction' if col=='peak_overlap' else 'degC',
              'n_common':len(d),'mean_abs_change':float(delta.mean()),
              'max_abs_change':float(delta.max()),'n_abs_change_gt_0p01':int((delta>.01).sum()),
              'policy_changed':policy,'difficulty_changed':difficulty})
    out=pd.DataFrame(rows);out.to_csv(OUT/'prediction_movement.csv',index=False)
    summary={'status':'passed','created_utc':datetime.now(timezone.utc).isoformat(),'cases_per_shift':status['all_shift_common_cases'],
      'posthoc':True,'scope':'changes in saved prediction points and selected training-derived features for the same masks',
      'limitation':'1-hour shifts and 0.01 thresholds are post-hoc; temperature thresholds are in C and peak-overlap threshold is dimensionless. This does not identify actual time zone, prove cause, sensor quality or independent climates'}
    (OUT/'prediction_movement_status.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(out.to_string(index=False));print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
