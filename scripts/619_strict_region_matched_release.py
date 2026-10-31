#!/usr/bin/env python3
"""Re-evaluate same-count score baseline in strict future-year sensitivity."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT; REV=ROOT/'results/wrr_review_response_20261027'; OUT=REV/'strict_region_holdout'; PRIVATE=ROOT/'private/wrr_strict_region_holdout_20261026'
KEY=['network_id','station_key','year','design_family','realization_id']


def main():
    if json.loads((OUT/'future_comparison_status.json').read_text())['status']!='passed':raise ValueError('strict future cohort not verified')
    evaluate=T.load_script('strict_matched_release',ROOT/'scripts/556_release_matched_retention.py').evaluate
    old=pd.read_parquet(REV/'release_outputs/future_years.parquet');new=pd.read_parquet(PRIVATE/'future_strict_outputs.parquet')
    joined=old[KEY+['eval_truth_h30','independence_group']].merge(new[KEY+['eval_truth_h30','independence_group']],on=KEY,suffixes=('_old','_strict'),validate='one_to_one',indicator=True,how='outer')
    if not joined._merge.eq('both').all() or not np.allclose(joined.eval_truth_h30_old,joined.eval_truth_h30_strict,rtol=0,atol=1e-8) or not joined.independence_group_old.eq(joined.independence_group_strict).all():raise ValueError('future case keys, outcomes or groups changed')
    rows=[]
    for family in ['calendar','crossed']:
        for label,frame in [('original',old),('strict',new)]:
            summary,_=evaluate(frame.loc[frame.design_family.eq(family)].copy())
            if summary['three_only']!=summary['score_only']:raise ValueError('numerical counts differ')
            rows.append({'family':family,'version':label}|summary)
    table=pd.DataFrame(rows)
    prior=pd.read_csv(REV/'release_outputs/matched_numerical_retention.csv'); prior=prior.loc[prior.condition.eq('future_years')]
    check=table.loc[table.version.eq('original')].merge(prior,on='family',suffixes=('_replayed','_saved'),validate='one_to_one')
    for field in ['n_eligible','n_equal_numerical','three_output_bad','score_only_bad','three_only','score_only']:
        if not check[field+'_replayed'].eq(check[field+'_saved']).all():raise ValueError('original matched baseline differs: '+field)
    table.to_csv(OUT/'future_matched_retention.csv',index=False)
    status={'status':'passed','cases':len(joined),'same_keys_truth_and_groups':True,'original_matched_counts_reproduced':True,
      'scope':'future-year same-number numerical-output score comparator recalculated separately for original and strict source models',
      'limitation':'threshold is selected using the evaluated unlabeled score distribution and three-output count; selected cases and counts differ across versions, and lower-bound information is not matched; no prospective or climate-transfer guarantee'}
    (OUT/'future_matched_retention_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(table[['family','version','n_eligible','n_equal_numerical','three_output_bad','score_only_bad','three_output_risk','score_only_risk']].to_string(index=False));print(json.dumps(status,indent=2))
if __name__=='__main__':main()
