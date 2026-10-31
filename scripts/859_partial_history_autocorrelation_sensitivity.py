#!/usr/bin/env python3
"""Compare interpolated versus observed-only history anomaly autocorrelation."""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.v17_fitness.estimators import StationModels

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'external_usace_reservoir';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027';DATA=ROOT/'data/external/wrr_usace_reservoir_20261027'

def freeze():
    helper=T.load_script('usace_phi_plan_helper',ROOT/'scripts/856_partial_history_feature_support_plan.py')
    if json.loads((OUT/'partial_history_feature_support_independent_audit.json').read_text())['status']!='passed':raise ValueError('Support audit incomplete')
    path=OUT/'partial_history_autocorrelation_plan.json'
    if path.exists():raise FileExistsError('Preserve autocorrelation plan')
    files=[PRIVATE/'partial_history_roster.csv',PRIVATE/'partial_history_scored_cases.parquet',PRIVATE/'partial_history_feature_support.csv',DATA/'finite_daily.parquet',
           OUT/'partial_history_feature_support_independent_audit.json',ROOT/'scripts/431_tr_cases.py',Path(__file__)]
    receipts={}
    roster=pd.read_csv(PRIVATE/'partial_history_roster.csv')
    for r in roster.itertuples(index=False):
        d=PRIVATE/'partial_history_predictions'/r.resource_id/str(r.year);receipt=json.loads((d/'receipt.json').read_text())
    receipt=PRIVATE/'partial_history_phi_inputs.json';receipt.write_text(json.dumps(receipts,sort_keys=True,indent=2)+'\n');receipt.chmod(0o600);files.append(receipt)
    p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after target scores and all-feature support audit; before observed-only autocorrelations were computed',
      'cohort':'All 17 target years. Use only their previously fixed other-year local histories, never target-year water. Evaluate one scalar per station-year rather than treating repeated masks as independent.',
      'comparison':'Recompute law_phi_a from the saved interpolated training panel and independently verify the previously saved value. Recalculate it with only fully observed daily means in the same history years, leaving missing days as NaN; rebuild the smooth climatology from those observed days. Hold fixed the five warm months of the interpolated version so the contrast does not change the seasonal definition.',
      'formula':'Within the training-year index, compute daily anomaly = observed or interpolated water minus the corresponding training-only smooth climatology. Retain the fixed warm months, then Pearson lag-one correlation over pairs whose two values are finite. Report pair counts and compare each variant with the fixed global estimator-role minimum and maximum.',
      'interpretation':'This is a retrospective sensitivity to two different historical-data treatments, including changed climatology and finite pair selection; it does not isolate the causal effect of interpolation alone or alter the saved model predictions. No alternate model accuracy is claimed.',
      'limitations':'The original feature formula can concatenate nonconsecutive selected years; the same rule is used in both variants. Source and target climate or sensor quality are not known independent. Source training min/max are marginal bounds, not a failure probability; law_phi_r is not recomputed here.',
      }
    path.write_text(json.dumps(p,indent=2)+'\n');print('Frozen all-target observed-only autocorrelation sensitivity')

def anomaly_phi(s,histories,months):
    mask=pd.Series(s.index.year.isin(histories),index=s.index)
    model=StationModels(target=s,donors=pd.DataFrame(index=s.index),air=None,train_mask=mask)
    idx=s.index[mask.to_numpy()];anomaly=s.loc[mask]-model.smooth_climatology(idx)
    a=anomaly.where(anomaly.index.month.isin(months)).to_numpy(float)
    pairs=np.isfinite(a[:-1])&np.isfinite(a[1:]);n=int(pairs.sum())
    if n<=10:return np.nan,n
    return float(np.corrcoef(a[:-1][pairs],a[1:][pairs])[0,1]),n

def run():
    helper=T.load_script('usace_phi_run_helper',ROOT/'scripts/856_partial_history_feature_support_plan.py');p=json.loads((OUT/'partial_history_autocorrelation_plan.json').read_text())
    roster=pd.read_csv(PRIVATE/'partial_history_roster.csv');cases=pd.read_parquet(PRIVATE/'partial_history_scored_cases.parquet');daily=pd.read_parquet(DATA/'finite_daily.parquet');daily['day']=pd.to_datetime(daily.day)
    support=pd.read_csv(PRIVATE/'partial_history_feature_support.csv').set_index('feature').loc['law_phi_a'];low=float(support.source_min);high=float(support.source_max)
    expected=json.loads((PRIVATE/'partial_history_phi_inputs.json').read_text());rows=[]
    for r in roster.itertuples(index=False):
        panel_path=PRIVATE/'partial_history_predictions'/r.resource_id/str(r.year)/'panel.csv'
        panel=pd.read_csv(panel_path,parse_dates=['date']).set_index('date')[r.resource_id].astype(float)
        raw=daily[daily.resource_id.eq(r.resource_id)].set_index('day').mean_c.reindex(panel.index).astype(float)
        history=[int(x) for x in r.history_years.split(';')]
        cohort=cases[cases.resource_id.eq(r.resource_id)&cases.year.eq(r.year)]
        if len(cohort)!=18 or cohort.warm_months.nunique()!=1:raise ValueError('Unexpected seasonal definition')
        months=[int(x) for x in cohort.warm_months.iloc[0].split(';')]
        phi_inter,n_inter=anomaly_phi(panel,history,months);phi_obs,n_obs=anomaly_phi(raw,history,months)
        if not np.allclose(cohort.law_phi_a,phi_inter,atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Interpolated feature does not reproduce')
        rows.append({'resource_id':r.resource_id,'year':r.year,'phi_interpolated':phi_inter,'phi_observed_only':phi_obs,
           'change_interpolated_minus_observed':phi_inter-phi_obs,'pairs_interpolated':n_inter,'pairs_observed_only':n_obs,
           'interpolated_outside_training_range':bool(np.isfinite(phi_inter) and phi_inter<low or phi_inter>high),
           'observed_only_outside_training_range':bool(np.isfinite(phi_obs) and phi_obs<low or phi_obs>high)})
    df=pd.DataFrame(rows);dest=PRIVATE/'partial_history_autocorrelation_sensitivity.csv';df.to_csv(dest,index=False);dest.chmod(0o600)
    result={'status':'completed_posthoc_sensitivity','target_years':len(df),'resources':df.resource_id.nunique(),
      'interpolated_phi_outside_training_range_years':int(df.interpolated_outside_training_range.sum()),
      'observed_only_phi_outside_training_range_years':int(df.observed_only_outside_training_range.sum()),
      'both_outside_years':int((df.interpolated_outside_training_range&df.observed_only_outside_training_range).sum()),
      'interpolated_outside_observed_inside_years':int((df.interpolated_outside_training_range&~df.observed_only_outside_training_range).sum()),
      'interpolated_inside_observed_outside_years':int((~df.interpolated_outside_training_range&df.observed_only_outside_training_range).sum()),
      'median_interpolated_minus_observed_phi':float(df.change_interpolated_minus_observed.median()),
      'min_interpolated_minus_observed_phi':float(df.change_interpolated_minus_observed.min()),
      'max_interpolated_minus_observed_phi':float(df.change_interpolated_minus_observed.max()),
      'mean_pairs_interpolated':float(df.pairs_interpolated.mean()),'mean_pairs_observed_only':float(df.pairs_observed_only.mean()),
      'limitations':p['limitations']+' '+p['interpretation']}
    (OUT/'partial_history_autocorrelation_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
