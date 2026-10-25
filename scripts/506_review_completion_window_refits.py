#!/usr/bin/env python3
"""Full source H7 generation and group-disjoint annual/risk refitting.

Peak support, mask placement, historical summaries, conditional paths, MOVE
augmentation and calibration all target seven days. This is not a post-hoc
replacement of H30 labels or a frozen-prediction window sensitivity.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
import json
import pandas as pd
from joblib import Parallel,delayed
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.windows import primary_view,native_view

OUT=T.ROOT/"results/wrr_review_completion_20261024"


def generate_one(job,settings,generator,pool,resume):
    core=T.load_script("h7_native_source_worker",T.ROOT/"scripts/431_tr_cases.py")
    return core.station_cases(job,settings,generator,pool,resume)


def refit_one(seed,region,split):
    m=T.load_script("h7_source_annual_worker",T.ROOT/"scripts/466_review_completion_refit.py")
    return m.fit_region(seed,region,split)


def analyse_one(seed,split,skip_trends):
    m=T.load_script("h7_source_analysis_worker",T.ROOT/"scripts/467_review_completion_analysis.py")
    return m.analyse(seed,split,200,skip_trends)


def main():
    p=argparse.ArgumentParser();p.add_argument("--stage",choices=["generate","refit","analyse","all"],default="all")
    p.add_argument("--seeds",type=int,nargs="+",default=list(range(20)));p.add_argument("--workers",type=int,default=32)
    p.add_argument("--limit",type=int,default=0);p.add_argument("--resume",action="store_true");p.add_argument("--with-trends",action="store_true")
    a=p.parse_args();split="h7_spec_refit"+(f"_smoke_{a.limit}" if a.limit else "")
    native=OUT/"target_windows/h7"/(f"smoke_{a.limit}" if a.limit else "full")
    work=OUT/"cases"/split
    native.mkdir(parents=True,exist_ok=True);work.mkdir(parents=True,exist_ok=True)
    settings=T.settings()|{"version":"review_completion_h7_v1/seeds_"+'_'.join(map(str,a.seeds))+(f"_smoke_{a.limit}" if a.limit else ""),
        "primary_window_days":7,"replication_seeds":a.seeds,"trajectory_targets":["h7"],"classical_baselines":True,"training_split":"leave_one_year_out"}
    design={"target":"H7 annual maximum of seven consecutive daily means","primary_window_days":7,"seeds":a.seeds,
        "observed_availability_floor":"same30 observed days for calendar-mask eligibility as H30, to hold this population rule fixed",
        "regenerated":["training climate peak/support","crossed masks","historical peak anomalies and residuals","window-specific historical mask replay","raw/state predictive quantiles","MOVE annual augmentation","AR1 bridge functional draws"],
        "refitted":["annual quantile regression","functional debiasing","failure classifier","disjoint interval and rule calibration"],
        "internal_legacy_aliases":"Native files keep h7 names; cases/"+split+" has an explicitly documented internal h7-to-h30 adapter for the unchanged fitting/scoring engine. Secondary H30 values are removed before aliasing.",
        "historical_endpoints":"unchanged, exploratory source specification only","partial":bool(a.limit)}
    if a.stage in ["generate","all"]:
        T.write_json(native/"design.json",design)
        T.write_json(native/"generation_settings.json",settings)
    else:
        completed=json.loads((native/"generation_summary.json").read_text())
        if not completed.get("complete") or set(a.seeds)-{r["seed"] for r in completed["results"]}:
            raise RuntimeError("The requested seeds do not have complete native generation")
    T.write_json(native/(a.stage+"_request.json"),{"seeds":a.seeds,"with_trends":a.with_trends,"partial":bool(a.limit)})
    if a.stage in ["generate","all"]:
        core=T.load_script("h7_native_source_parent",T.ROOT/"scripts/431_tr_cases.py")
        jobs=core.jobs_for("source");pools=core.calendar_pool("source",jobs)
        if a.limit:jobs=jobs[:a.limit]
        generator=json.loads((T.E1_MISSINGNESS/"mnar_generator.json").read_text())
        results=Parallel(n_jobs=a.workers,verbose=10)(delayed(generate_one)(job,settings,generator,core.pool_for(job,pools),a.resume) for job in jobs)
        parts={seed:[] for seed in a.seeds}
        for result in results:
            if not result.get("cache"):continue
            frame=pd.read_parquet(result["cache"])
            if frame.empty:continue
            for seed,block in frame.groupby("replication_seed",sort=False):
                if int(seed) in parts:parts[int(seed)].append(block)
        summary=[]
        for seed in a.seeds:
            if not parts[seed]:raise RuntimeError(f"No native H7 cases for seed{seed}")
            frame=pd.concat(parts.pop(seed),ignore_index=True)
            frame.to_parquet(native/f"seed_{seed:02d}.parquet",index=False)
            primary_view(frame).to_parquet(work/f"seed_{seed:02d}.parquet",index=False)
            summary.append({"seed":seed,"cases":len(frame),"physical_stations":frame.station_key.nunique(),"groups":frame.independence_group.nunique()})
        T.write_json(native/"generation_summary.json",{"complete":True,"results":summary,"station_jobs":len(jobs)})
    if a.stage in ["refit","all"]:
        tasks=[]
        for seed in a.seeds:
            c=pd.read_parquet(work/f"seed_{seed:02d}.parquet",columns=["region"])
            tasks.extend((seed,r) for r in sorted(c.region.unique()))
        result=Parallel(n_jobs=a.workers,verbose=10)(delayed(refit_one)(seed,region,split) for seed,region in tasks)
        T.write_json(native/"refit_summary.json",{"complete":True,"seeds":a.seeds,"outer_fits":len(result),"target":"H7, not historical H30 endpoint replacement"})
    if a.stage in ["analyse","all"]:
        Parallel(n_jobs=min(a.workers,len(a.seeds)),verbose=10)(delayed(analyse_one)(seed,split,not a.with_trends) for seed in a.seeds)
        for seed in a.seeds:
            folder=native/"predictions"/f"seed_{seed:02d}";folder.mkdir(parents=True,exist_ok=True)
            for path in sorted((OUT/"refits"/split/f"seed_{seed:02d}").glob("*.parquet")):
                native_view(pd.read_parquet(path)).to_parquet(folder/path.name,index=False)
        T.write_json(native/"analysis_summary.json",{"complete":True,"target":"H7","seeds":a.seeds,"with_trends":a.with_trends,"partial":bool(a.limit)})
    return 0


if __name__=="__main__":raise SystemExit(main())
