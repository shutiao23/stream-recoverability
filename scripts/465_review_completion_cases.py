#!/usr/bin/env python3
"""Generate all 20 opened-source repetitions, sharing only deterministic fits.

Each mask, calendar and trajectory has an independent integer seed. Source
station histories and fitted daily regressions are shared across repetitions;
no Australian/new-USGS outcome is acquired here. Differential splits refit all
upstream quantities after excluding ALL hot/future years, including from donors.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"
import argparse
import json
import time
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq
from joblib import Parallel, delayed
import wrr_tr_common as T


def one(job, settings, generator, pool, resume):
    module = T.load_script("r4_case_worker", T.ROOT / "scripts/431_tr_cases.py")
    return module.station_cases(job, settings, generator, pool, resume)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--split", choices=["leave_one_year_out", "cold_to_hot", "before_2010","non_air_refit","air_exposure"], default="leave_one_year_out")
    p.add_argument("--workers", type=int, default=48)
    p.add_argument("--seeds", type=int, nargs="+")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--resume", action="store_true")
    a = p.parse_args()
    config = json.loads((T.ROOT / "configs/wrr_review_completion_20261024.json").read_text())
    seeds = a.seeds if a.seeds is not None else config["seeds"]
    output = T.ROOT / config["out"] / "cases" / a.split
    if a.limit:
        output = output / f"smoke_{a.limit}"
    output.mkdir(parents=True, exist_ok=True)
    settings = T.settings() | {"version": f"review_completion_20261024/{a.split}/seeds_{'_'.join(map(str,seeds))}" + (f"_smoke_{a.limit}" if a.limit else ""), "replication_seeds": seeds, "classical_baselines": True, "trajectory_targets": ["h30"], "training_split": a.split}
    if a.split in ["cold_to_hot","before_2010"]:
        settings["version"]+="/v2_full_upstream_exclusion"
    if a.split=="non_air_refit":
        settings["synthetic_water_trend_c_decade"]=.2
    if a.split=="air_exposure":
        settings.update(training_split="leave_one_year_out",visible_air_exposure_days=7,visible_air_exposure_top_fraction=.1)
    T.write_json(output / "generation_settings.json", settings)
    core = T.load_script("r4_case_parent", T.ROOT / "scripts/431_tr_cases.py")
    jobs = core.jobs_for("source")
    # Always construct calendars from the entire opened source roster, even in a smoke run.
    pools = core.calendar_pool("source", jobs)
    if a.limit:
        jobs = jobs[:a.limit]
    generator = json.loads((T.E1_MISSINGNESS / "mnar_generator.json").read_text())
    start = time.monotonic()
    results = Parallel(n_jobs=a.workers, verbose=10)(delayed(one)(job, settings, generator, core.pool_for(job, pools), a.resume) for job in jobs)
    # Read each station cache once. Re-reading the mixed-seed parquet twenty
    # times needlessly decodes every long residual-history string twenty times.
    # The declared 20-seed roster fits in this study's memory budget; --seeds
    # permits smaller batches on machines with less RAM.
    by_seed={seed:[] for seed in seeds}
    for position,result in enumerate(results):
        if result.get("cache"):
            if "replication_seed" not in pq.ParquetFile(result["cache"]).schema_arrow.names:
                continue
            frame=pd.read_parquet(result["cache"])
            for seed,block in frame.groupby("replication_seed",sort=False):
                if int(seed) in by_seed:
                    by_seed[int(seed)].append(block)
        if position%100==0:
            print(f"assembling station cache {position}/{len(results)}",flush=True)
    for seed in seeds:
        frames=by_seed.pop(seed)
        if frames:
            frame = pd.concat(frames, ignore_index=True)
            unsupported=~frame.policy_choice.isin(["air_ridge","donor_ridge"])
            for column in ["h30__move1_annual","h30__move1_warm","h30__move1_h30"]:
                if column in frame:
                    frame.loc[unsupported,column]=float("nan")
            frame.to_parquet(output / f"seed_{seed:02d}.parquet", index=False)
            print(f"seed {seed}: {len(frame)} cases, {frame.station_key.nunique()} stations", flush=True)
    T.write_json(output / "summary.json", {"split": a.split, "seeds": seeds, "station_jobs": len(jobs), "station_outputs": results, "elapsed_seconds": time.monotonic()-start, "smoke": bool(a.limit), "evidence_role": "opened-source exploratory replication"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
