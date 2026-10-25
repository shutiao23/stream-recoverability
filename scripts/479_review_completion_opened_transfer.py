#!/usr/bin/env python3
"""Apply the redesigned source-only pipeline to the TWO ALREADY OPENED cohorts.

This is explicitly supplementary development evidence. It does not request a
new value or repair the lost blindness of the older evaluations.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import json
import pandas as pd
from joblib import Parallel,delayed
import wrr_tr_common as T

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=T.ROOT/CONFIG["out"]


def fit_opened(region,path):
    refit=T.load_script("r4_opened_refit_worker",T.ROOT/"scripts/466_review_completion_refit.py")
    return refit.fit_region(0,region,"opened_transfer",str(path))


def main():
    source=pd.read_parquet(OUT/"cases/leave_one_year_out/seed_00.parquet")
    source["training_partition"]="train"
    parts=[source]
    for name,relative in [("bom","e7_au_development/cases.parquet"),("usgs_new","e10_sealed_usgs/cases.parquet")]:
        f=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022"/relative)
        f["training_partition"]="test";f["evaluation_dataset"]=name;f["region"]="opened_"+name
        parts.append(f)
    folder=OUT/"opened_transfer";folder.mkdir(parents=True,exist_ok=True)
    path=folder/"source_and_opened_cases.parquet"
    pd.concat(parts,ignore_index=True).to_parquet(path,index=False)
    Parallel(n_jobs=2)(delayed(fit_opened)(region,path) for region in ["opened_bom","opened_usgs_new"])
    T.write_json(folder/"status.json",{"new_data_acquired":False,"independent_confirmation":False,"training":"all estimator, calibration and score roles are source-only; all opened external rows excluded from all roles","cohorts":["previously opened BOM","previously opened USGS additional stations"],"known_dependence":"USGS original HUC8 overlaps and Australian hydrologic grouping limitations remain descriptive; no renewed independent-population claim"})
    return 0


if __name__=="__main__":
    raise SystemExit(main())
