#!/usr/bin/env python3
"""Parallelize one unusually long station by seed, with identical case draws."""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
import json
import pandas as pd
from joblib import Parallel,delayed
import wrr_tr_common as T


def one(job,settings,generator,pool,seed):
    local=settings|{"replication_seeds":[seed],"version":settings["version"]+f"/tail_parallel/seed_{seed:02d}"}
    m=T.load_script("r4_tail_case_worker",T.ROOT/"scripts/431_tr_cases.py")
    return m.station_cases(job,local,generator,pool,True)


def main():
    p=argparse.ArgumentParser();p.add_argument("--network",required=True);p.add_argument("--station",required=True);p.add_argument("--workers",type=int,default=20);a=p.parse_args()
    config=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
    settings=json.loads((T.ROOT/config["out"]/"cases/leave_one_year_out/generation_settings.json").read_text())
    m=T.load_script("r4_tail_case_parent",T.ROOT/"scripts/431_tr_cases.py")
    jobs=m.jobs_for("source");job=next(j for j in jobs if j["network_id"]==a.network and j["station_id"]==a.station)
    pools=m.calendar_pool("source",jobs);pool=m.pool_for(job,pools)
    generator=json.loads((T.E1_MISSINGNESS/"mnar_generator.json").read_text())
    results=Parallel(n_jobs=a.workers,verbose=10)(delayed(one)(job,settings,generator,pool,seed) for seed in settings["replication_seeds"])
    frame=pd.concat([pd.read_parquet(r["cache"]) for r in results],ignore_index=True)
    target=m.cache_path(job,settings);target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix(".tail.parquet");frame.to_parquet(temporary,index=False);temporary.replace(target)
    print(f"Merged {len(frame)} cases for {a.network}/{a.station}; seeds retain station/year/local-design identity",flush=True)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
