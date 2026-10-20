#!/usr/bin/env python3
"""Separate realistic admission and held-group event/calendar information-loss assays."""

from __future__ import annotations

import os

for thread_variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[thread_variable] = "1"

import argparse
import json
from pathlib import Path

import pandas as pd
from joblib import Parallel, delayed

import wrr_r3_common as C

OUT = C.RUN / "r3_14_monitoring_replay"


def run_station(job: dict, settings: dict, salt: str) -> dict:
    module = C.load_script("r3_monitoring_recovery_worker", C.ROOT / "scripts/351_wrr_representative_recovery.py")
    return module.build_station(job, settings, salt)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], default="leave_one_year_out")
    parser.add_argument("--family", choices=["admission", "events", "real_calendars"], default="admission")
    parser.add_argument("--cofailure", type=float, choices=[0, 0.5, 1], default=0)
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()
    settings = C.protocol()
    core_path = C.ROOT / "scripts/351_wrr_representative_recovery.py"
    core = C.load_script("r3_monitoring_source_jobs", core_path)
    jobs, roster = core.source_jobs(args.protocol, False)
    groups_path = C.RUN / "r3_06_independence_risk/complete_network_independence.csv"
    group_map = pd.read_csv(groups_path).set_index("network_id").independence_group
    for job in jobs:
        job["design_mode"] = args.family
        job["cofailure_fraction"] = args.cofailure
        job["independence_group"] = group_map[job["network_id"]]
    output = OUT / args.protocol / args.family / f"cofailure_{args.cofailure:g}"
    output.mkdir(parents=True, exist_ok=True)
    core.CACHE.mkdir(parents=True, exist_ok=True)
    roster.to_csv(output / "source_roster.csv", index=False)
    salt = C.digest(core_path) + C.digest(C.ROOT / "src/stream_recoverability/experiments/v19_revision/trajectory.py") + args.family
    print(f"[364] {args.family}, {args.protocol}, cofailure={args.cofailure}, {len(jobs)} station-network records", flush=True)
    results = Parallel(n_jobs=args.workers, verbose=10)(delayed(run_station)(job, settings, salt) for job in jobs)
    frames = [pd.read_parquet(result["cache"]) for result in results if result["cache"]]
    frames = [frame for frame in frames if len(frame)]
    if not frames:
        raise RuntimeError("No eligible monitoring-replay case")
    cases = pd.concat(frames, ignore_index=True)
    cases.to_parquet(output / "cases.parquet", index=False)
    C.write_json(output / "jobs.json", {"jobs": jobs, "station_results": results})
    C.write_json(output / "summary.json", {"family": args.family, "protocol": args.protocol, "cofailure": args.cofailure, "n_cases": len(cases), "n_networks": cases.network_id.nunique(), "n_independent_groups": cases.independence_group.nunique(), "n_station_years": len(cases[["station_id", "year"]].drop_duplicates()), "case_families": cases.design_family.value_counts().to_dict(), "n_cases_with_visible_donors": int((cases.n_visible_donors > 0).sum()), "n_uncertainty_available": int(cases.uncertainty_status.eq("available").sum()), "role": "opened-source admission benchmark or held-group information-loss assay, not independent confirmation"})
    C.write_json(output / "protocol_fingerprint.json", C.fingerprint(Path(__file__), {"core": core_path, "groups": groups_path}))
    print(f"[364] {len(cases)} monitoring cases complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
