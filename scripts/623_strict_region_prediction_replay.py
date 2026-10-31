#!/usr/bin/env python3
"""Replay all saved strict archive annual predictions from their current model."""
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;PRIVATE=ROOT/'private/wrr_strict_region_holdout_20261026';OUT=ROOT/'results/wrr_review_response_20261027/strict_region_holdout'
LEVELS=[5,10,25,50,75,90,95]

def main():
 model=PRIVATE/'refits/before_2010/seed_00/usgs_huc17.joblib';
 bundle=joblib.load(model);cal=json.loads((PRIVATE/'strict_archive_calibration.json').read_text());bundle['offsets']=cal['D2_offsets']
 infer=T.load_script('strict_archive_prediction_replay',ROOT/'scripts/495_review_completion_independent_analysis.py')
 files=sorted((PRIVATE/'whole_archive').glob('*/forward/replicate_*/*/annual_predictions.parquet'))
 if len(files)!=120:raise ValueError('strict archive settings incomplete')
 checked=0;maximum=0.;empty=0
 columns=['D2','risk_score','P2']+[f'{m}_q{level:02d}' for m in ['D2','stochastic_cal','state_cal'] for level in LEVELS]
 for path in files:
  c=pd.read_parquet(path)
  if c.empty:empty+=1;continue
  new=infer.classical_predictions(infer.predict(c,bundle),cal)
  if not c.prediction_supported.eq(new.prediction_supported).all():raise ValueError('prediction support differs')
  for col in columns:
   x=c[col].to_numpy(float);y=new[col].to_numpy(float)
   if not np.allclose(x,y,rtol=0,atol=1e-8,equal_nan=True):raise ValueError('strict cached prediction differs from current model: '+col)
   valid=np.isfinite(x)&np.isfinite(y)
   if valid.any():maximum=max(maximum,float(np.max(np.abs(x[valid]-y[valid]))))
  checked+=len(c)
 status={'status':'passed','strict_archive_settings':len(files),'empty_settings':empty,'annual_cases_replayed':checked,'numeric_fields_replayed':len(columns),'maximum_absolute_difference':maximum,
  'scope':'current strict HUC17 source model and calibration replayed on every saved affected archive annual feature row; prediction support, scores, D2 and comparator quantiles checked',
  'limitation':'does not independently re-fit daily models, verify original source data rights, or validate trend draws, physical measurement uncertainty or independent climate transfer'}
 (OUT/'archive_prediction_replay_status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))
if __name__=='__main__':main()
