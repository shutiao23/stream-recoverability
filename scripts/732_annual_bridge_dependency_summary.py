#!/usr/bin/env python3
"""Combine the completed post-hoc source-seed bridge-repair replays."""
import json
import hashlib
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
OUT=ROOT/'results/wrr_review_response_20261027/audit'

def main():
    rows=[];hashes={}
    for seed in range(20):
        row=json.loads((OUT/'annual_bridge_dependency'/f'seed_{seed:02d}.json').read_text())
        repair=ROOT/'results/wrr_review_completion_20261024/repairs/leave_one_year_out'/f'seed_{seed:02d}.parquet'
        saved=ROOT/'private/wrr_review_case_evidence_20261027/annual_source_cases'/f'seed_{seed:02d}.parquet'
        if row['seed']!=seed or not row.get('input_sha256'):
            raise ValueError('Source-seed receipt or inputs changed: '+str(seed))
        for path in [repair,saved,ROOT/'scripts/730_annual_bridge_dependency.py']:
            key=str(path.relative_to(ROOT));expected=row['input_sha256'].get(key)
            if not path.is_file() or not expected or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError('Source-seed receipt or inputs changed: '+str(seed))
            hashes[key]=expected
        rows.append({key:value for key,value in row.items() if key!='input_sha256'})
    frame=pd.DataFrame(rows);path=OUT/'annual_bridge_repair_effect.csv';frame.to_csv(path,index=False)
    hashes[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    report={'status':'passed','posthoc':True,'seeds_checked':len(frame),'rows_checked':int(frame.rows.sum()),
            'input_sha256':hashes,
            'with_repair_valid':int(frame.with_repair_valid.sum()),'without_repair_valid':int(frame.without_repair_valid.sum()),
            'became_valid_with_repair':int(frame.became_valid_with_repair.sum()),
            'became_invalid_with_repair':int(frame.became_invalid_with_repair.sum()),
            'both_valid_changed_quantiles':int(frame.both_valid_changed_quantiles.sum()),
            'maximum_quantile_change':float(frame.max_both_valid_quantile_change.max()),
            'limitation':'Counts are seed-case records, not independent station-years; saved cached inputs and calibration roles are reused. Omission comparisons were assembled after observing earlier results, not preregistered. Not a model refit or provider-data validation.'}
    (OUT/'annual_bridge_repair_dependency.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
