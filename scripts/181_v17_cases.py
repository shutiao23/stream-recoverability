#!/usr/bin/env python3
"""Steps 2-3 of the v17 programme: outage design and the case table.

One case is (station, calendar year, outage realization). Every supported
estimator completes the year, the completed year produces the thermal metric,
and the metric produces an error against fully observed truth. Only
decision-time-visible features are recorded alongside.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.cases import build_station_cases  # noqa: E402
from stream_recoverability.experiments.v17_fitness.panel import station_jobs, station_roster  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import STEP1_PANEL, STEP3_CASES  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=64)
    parser.add_argument("--limit", type=int, default=0, help="debug: first N stations only")
    parser.add_argument("--out", type=str, default="cases.parquet")
    parser.add_argument(
        "--fit-protocol",
        choices=("leave_one_year_out", "strictly_prior_years"),
        default="leave_one_year_out",
        help="how the estimators see the record: offline repair, or repair as the record accrues",
    )
    args = parser.parse_args()

    STEP3_CASES.mkdir(parents=True, exist_ok=True)
    roster = station_roster()
    split = pd.read_csv(STEP1_PANEL / "network_split.csv")
    split["network_id"] = split["network_id"].astype(str)
    jobs = station_jobs(roster, split)
    for job in jobs:
        job["fit_protocol"] = args.fit_protocol
    if args.limit:
        jobs = jobs[: args.limit]
    print(f"stations to score: {len(jobs)}", flush=True)

    frames: list[pd.DataFrame] = []
    failures: list[dict] = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(build_station_cases, job): job for job in jobs}
        done = 0
        for future in as_completed(futures):
            job = futures[future]
            try:
                frame = future.result()
            except Exception as error:  # noqa: BLE001 - recorded, not silenced
                failures.append(
                    {"network_id": job["network_id"], "station_id": job["station_id"], "error": repr(error)}
                )
                frame = pd.DataFrame()
            if not frame.empty:
                frames.append(frame)
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(jobs)} stations", flush=True)

    if not frames:
        print("no cases built")
        return 1
    # Deterministic row order. Workers return in completion order, so the
    # concatenation order varies between runs even though the content does not.
    # Anything downstream that assigns positionally (jitter) or breaks ties by
    # row order would then move between runs.
    cases = pd.concat(frames, ignore_index=True)
    cases = cases.sort_values(
        ["network_id", "station_id", "year", "arm", "realization_id"], kind="mergesort"
    ).reset_index(drop=True)
    stem = Path(args.out).stem
    suffix = "" if stem == "cases" else f"_{stem}"
    cases.to_parquet(STEP3_CASES / args.out, index=False)
    pd.DataFrame(failures).to_csv(STEP3_CASES / f"failures{suffix}.csv", index=False)

    summary = {
        "output": args.out,
        "fit_protocol": args.fit_protocol,
        "n_cases": int(len(cases)),
        "n_networks": int(cases["network_id"].nunique()),
        "n_stations": int(cases.groupby(["network_id", "station_id"]).ngroups),
        "n_station_years": int(cases.groupby(["network_id", "station_id", "year"]).ngroups),
        "n_failures": int(len(failures)),
        "by_split": cases.groupby("split_role").size().to_dict(),
        "by_arm": cases.groupby("arm").size().to_dict(),
        "by_donor_regime": cases.groupby("donor_regime").size().to_dict(),
    }
    (STEP3_CASES / f"summary{suffix}.json").write_text(
        json.dumps(summary, indent=2, default=int), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, default=int))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
