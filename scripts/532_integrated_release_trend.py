#!/usr/bin/env python3
"""Evaluate release decisions followed by finite-record trend inference.

This is an exploratory pipeline: a Gaussian censored likelihood treats
released estimates as exact and bounds as lower-censored observations. Its
interval includes working-model regression noise and is not a calibrated
missing-data-only interval or a safety guarantee.
"""
from __future__ import annotations
import os
for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.stats import norm
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.archive import slope
from stream_recoverability.experiments.tr_revision.outputs import release_states
from stream_recoverability.experiments.tr_revision.statistics import interval_score, lower_bound_trend

ROOT = T.ROOT / "results/wrr_review_response_20261027"
ARCHIVE = ROOT / "whole_archive"
OUT = ROOT / "integrated_release_trend"
SOURCE = T.ROOT / "results/wrr_review_completion_20261024"


def one(path, truth, jobs, limits):
    relative = path.relative_to(ARCHIVE)
    family, mode, replicate, _ = relative.parts[:4]
    rep = int(replicate.removeprefix("replicate_"))
    design = json.loads((path.parent / "design.json").read_text())
    station = design["station_key"]
    ref = truth[(family, station)]
    if mode == "forward":
        ref = ref.loc[ref.index >= 2010]
    years, original = ref.index.to_numpy(int), ref.to_numpy(float)
    expected = float(slope(years, original))
    masked = {int(y) for y in design["masks"]}
    complete = ~np.isin(years, list(masked))
    exact = np.where(complete, original, np.nan)
    lower = np.full(len(years), np.nan)
    states = np.where(complete, "complete_observed", "unknown").astype(object)
    observed_bound = np.full(len(years), np.nan)
    quality_flag = np.full(len(years), np.nan)
    c = pd.read_parquet(path)
    estimate_count = bound_count = unknown_count = 0
    if len(c):
        if c.year.duplicated().any():
            raise ValueError(f"Nonunique masked year in {path}")
        c = c.reset_index(drop=True)
        release = T.load_script("integrated_release_quality", T.ROOT / "scripts/522_release_outputs.py")
        agreement = release.visible_quality(jobs[station], c, False).reindex(c.index)
        c["agreement7"] = agreement
        c["output"] = release_states(c, limits["before_2010" if mode == "forward" else "leave_one_year_out"][design["region"]],
                                     agreement.le(.05).to_numpy())
        c["quality_flag"] = agreement.le(.05).to_numpy()
        for r in c.itertuples(index=False):
            pos = np.searchsorted(years, r.year)
            if pos >= len(years) or years[pos] != r.year or r.year not in masked:
                raise ValueError("An annual prediction does not match the masked archive")
            states[pos] = r.output
            observed_bound[pos] = r.observed_lower_bound__observed_days
            quality_flag[pos] = float(r.quality_flag) if np.isfinite(r.agreement7) else np.nan
            if r.output == "estimate":
                exact[pos] = r.D2
                estimate_count += 1
            elif r.output == "observed_bound":
                lower[pos] = r.observed_lower_bound__observed_days
                bound_count += 1
            else:
                unknown_count += 1
    unknown_count += len(masked - set(c.year.astype(int))) if len(c) else len(masked)
    if estimate_count + bound_count + unknown_count != len(masked):
        raise RuntimeError("Release states do not partition the masked-year denominator")
    common = dict(family=family, mode=mode, station_key=station,
                  independence_group=design["independence_group"], region=design["region"],
                  replicate=rep, n_years=len(years), n_masked=len(masked),
                  n_estimates=estimate_count, n_bounds=bound_count, n_unknown=unknown_count,
                  truth_slope=expected)
    rows = []
    keep = np.isfinite(exact)
    row = common | {"method":"released_values_only", "available":int(keep.sum()) >= 5}
    if row["available"]:
        row["slope"] = float(slope(years[keep], exact[keep]))
        row["error"] = row["slope"] - expected
        row["squared_error"] = row["error"] ** 2
    rows.append(row)
    fitted = lower_bound_trend(years, exact, lower)
    row = common | {"method":"released_values_and_bounds", "available":bool(fitted["converged"]),
                    "n_exact":fitted["n_exact"], "n_censored":fitted["n_censored"]}
    if row["available"]:
        row["slope"] = fitted["slope"]
        row["error"] = row["slope"] - expected
        row["squared_error"] = row["error"] ** 2
        if np.isfinite(fitted["se"]) and fitted["se"] > 0:
            half = norm.ppf(.975) * fitted["se"]
            lo, hi = row["slope"] - half, row["slope"] + half
            row.update(total_working_coverage95=bool(lo <= expected <= hi),
                       total_working_width95=hi - lo,
                       total_working_interval_score95=float(interval_score(lo, hi, expected, alpha=.05)))
    rows.append(row)
    annual = pd.DataFrame({"family":family, "mode":mode, "station_key":station,
                           "independence_group":design["independence_group"], "region":design["region"],
                           "replicate":rep, "year":years, "output_state":states,
                           "released_estimate":np.where(states == "estimate", exact, np.nan),
                           "observed_lower_bound":observed_bound, "quality_flag":quality_flag,
                           "eval_reference_h30":original})
    return rows, annual


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    ref = pd.read_parquet(SOURCE / "cases/leave_one_year_out/seed_00.parquet",
                          columns=["station_key", "year", "design_family", "eval_truth_h30"])
    truth = {(family, station): group.drop_duplicates("year").set_index("year").eval_truth_h30.sort_index()
             for (family, station), group in ref.groupby(["design_family", "station_key"])}
    core = T.load_script("integrated_jobs", T.ROOT / "scripts/431_tr_cases.py")
    jobs = {j["station_key"]: j for j in core.jobs_for("source")}
    limits = json.loads((ROOT / "release_outputs/design.json").read_text())["limits_by_training_split_and_held_region"]
    paths = sorted(p for family in ("calendar", "crossed")
                   for mode in ("offline", "forward")
                   for p in (ARCHIVE / family / mode).glob("replicate_*/*/annual_predictions.parquet"))
    if args.limit is not None:
        paths = paths[:args.limit]
    results = Parallel(n_jobs=args.workers, verbose=10)(delayed(one)(p, truth, jobs, limits) for p in paths)
    frame = pd.DataFrame([row for pair, _ in results for row in pair])
    pd.concat([annual for _, annual in results], ignore_index=True).to_parquet(
        output / "annual_decisions.parquet", index=False)
    frame.to_csv(output / "station_repetitions.csv", index=False)
    report = []
    for key, group in frame.groupby(["family", "mode", "method"]):
        valid = group.loc[group.available]
        row = dict(zip(["family", "mode", "method"], key), n_eligible=len(group), n_available=len(valid),
                   availability=len(valid)/len(group), n_stations=group.station_key.nunique(),
                   n_groups=group.independence_group.nunique(),
                   total_masked=int(group.n_masked.sum()), total_estimates=int(group.n_estimates.sum()),
                   total_bounds=int(group.n_bounds.sum()), total_unknown=int(group.n_unknown.sum()))
        if len(valid):
            row.update(rmse=float(np.sqrt(valid.squared_error.mean())), bias=float(valid.error.mean()))
            for column in ["total_working_coverage95", "total_working_width95", "total_working_interval_score95"]:
                if column in valid:
                    row[column] = float(valid[column].mean())
        report.append(row)
    pd.DataFrame(report).to_csv(output / "summary.csv", index=False)
    (output / "design.json").write_text(json.dumps({
        "cases":"all baseline whole-archive station/repetition rows",
        "decision":"same source-split raw score, range thresholds and visible quality diagnostic as the release experiment",
        "comparators":"released numerical values only; released numerical values plus lower-bound censored likelihood",
        "truth":"finite complete-record slope; no hidden evaluation values enter the release decision",
        "interval":"Gaussian working-likelihood regression interval; includes modeled regression variation and is not calibrated missingness-only uncertainty",
        "limitations":["selected estimates are treated as exact", "censoring can be informative", "quality flag only detects exact-air-like conditions; unavailable air agreement is not a passing quality test", "no group or trend coverage guarantee"]}, indent=2) + "\n")
    print(pd.DataFrame(report).to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
