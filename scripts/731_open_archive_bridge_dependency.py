#!/usr/bin/env python3
"""Post-hoc replay of open-source archive classical calibration offsets.

Reuses the stored source cases and role assignments; it does not refit models,
reproduce provider acquisition, or establish redistribution rights.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[name]='1'
import json
import hashlib
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity'
PRIVATE=ROOT/'private/wrr_open_source_sensitivity_20261026'
SOURCE=ROOT/'results/wrr_review_completion_20261024'

def main():
    plan=json.loads((OUT/'plan.json').read_text())
    strict=T.load_script('bridge_strict',ROOT/'scripts/610_strict_region_refit.py').strict_module()
    strict.OUT=PRIVATE
    repair=T.load_script('bridge_repair',ROOT/'scripts/467_review_completion_analysis.py')
    archive=T.load_script('bridge_archive',ROOT/'scripts/521_whole_archive.py')
    rows=[]
    pinned=[OUT/'plan.json',OUT/'single_year_calibration_plan.json',ROOT/'scripts/731_open_archive_bridge_dependency.py']
    pinned += [SOURCE/'repairs'/split/'seed_00.parquet' for split in ('leave_one_year_out','before_2010')]
    hashes={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in pinned}
    for mode,split in [('offline','leave_one_year_out'),('forward','before_2010')]:
        path=SOURCE/'repairs'/split/'seed_00.parquet';relative=str(path.relative_to(ROOT))
        if not path.is_file():
            raise ValueError('Bridge repair differs from later single-year source plan: '+relative)
        raw=pd.read_parquet(PRIVATE/'candidate_cases'/split/'seed_00.parquet')
        fixed=repair.apply_bridge_repairs(raw.copy(),0,split)
        for item in [x for x in plan['target_mode_region_stations'] if x['mode']==mode]:
            region=item['region']
            saved=json.loads((PRIVATE/'calibrations'/mode/(region+'.json')).read_text())['offsets']
            with_repair=archive.classical_calibration(fixed,region,strict)['offsets']
            without=archive.classical_calibration(raw,region,strict)['offsets']
            for method in ('stochastic','state'):
                if saved[method].keys()!=with_repair[method].keys() or saved[method].keys()!=without[method].keys():
                    raise ValueError('Calibration cells changed')
                a=np.array([with_repair[method][k] for k in sorted(saved[method])],float)
                b=np.array([without[method][k] for k in sorted(saved[method])],float)
                c=np.array([saved[method][k] for k in sorted(saved[method])],float)
                if not np.allclose(a,c,atol=1e-10,rtol=0,equal_nan=True):raise ValueError('Repaired calibration differs from saved offsets')
                rows.append({'mode':mode,'region':region,'method':method,'offset_values':a.size,
                             'changed_offset_values':int((np.abs(a-b)>1e-10).sum()),
                             'maximum_offset_change':float(np.max(np.abs(a-b)))})
            print('Checked archive calibration',mode,region,flush=True)
    result=pd.DataFrame(rows)
    if len(result)!=26 or result.duplicated(['mode','region','method']).any():raise ValueError('Archive calibration cohort changed')
    if any(hashlib.sha256(path.read_bytes()).hexdigest()!=hashes[str(path.relative_to(ROOT))] for path in pinned):
        raise ValueError('Archive bridge dependency changed during replay')
    out=OUT/'archive_bridge_repair_effect.csv';result.to_csv(out,index=False)
    hashes[str(out.relative_to(ROOT))]=hashlib.sha256(out.read_bytes()).hexdigest()
    report={'status':'passed','posthoc':True,'repaired_calibrations_match_saved':True,
            'input_sha256':hashes,
            'calibration_cells_checked':len(result),'cells_with_changed_offsets':int(result.changed_offset_values.gt(0).sum()),
            'changed_offset_values':int(result.changed_offset_values.sum()),'limitation':'Post-hoc replay of stored cases and calibration roles; this is not a source refit, an independent climate evaluation, provider validation, or proof of rights.'}
    (OUT/'archive_bridge_repair_dependency.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
