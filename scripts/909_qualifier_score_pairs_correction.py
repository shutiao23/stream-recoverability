#!/usr/bin/env python3
"""Correct duplicated paired-summary rows without changing any predictions."""
import json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np,pandas as pd
STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
def main():
 source=STAGE/'qualifier_aware_score_pairs.csv';status=json.loads((STAGE/'qualifier_aware_score_status.json').read_text());plan=json.loads((STAGE/'qualifier_aware_score_plan.json').read_text());p=STAGE/'qualifier_aware_pairs_correction.json'
 if p.exists():raise FileExistsError('Preserve correction record')
 a=pd.read_csv(source);keys=['cohort','method']
 if len(a)!=12 or a.groupby(keys).size().ne(2).any():raise ValueError('Unexpected duplicate pattern')
 for _,g in a.groupby(keys):
  if len(g[['cases','mean_MAE_change_c']].drop_duplicates())!=1:raise ValueError('Duplicate paired results differ')
 b=a.drop_duplicates().sort_values(keys).reset_index(drop=True);dest=STAGE/'qualifier_aware_score_pairs_corrected.csv';b.to_csv(dest,index=False)
 out={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'corrected_duplicate_summary_rows','reason':'The scoring loop appended identical paired contrasts once per history version. Each of six cohort/method contrasts was duplicated exactly.',
  'original_rows':len(a),'corrected_rows':len(b),'scientific_values_or_predictions_changed':False,'original_file_retained':True,'limitations':plan['limitations'],'storage':'temporary RAM filesystem; not durable'}
 p.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
