#!/usr/bin/env python3
"""Evaluate withholding cases whose seven-day quality diagnostic is unavailable."""
from __future__ import annotations
import os
for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
from pathlib import Path
import json
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from stream_recoverability.experiments.tr_revision.archive import slope
from stream_recoverability.experiments.tr_revision.statistics import lower_bound_trend

ROOT = Path(__file__).resolve().parents[1] / "results/wrr_review_response_20261027"
FOLDER = ROOT / "integrated_release_trend"


def one(key, block):
    family, mode, station, rep = key
    block = block.sort_values("year")
    years = block.year.to_numpy(int)
    truth = block.eval_reference_h30.to_numpy(float)
    expected = float(slope(years, truth))
    state = block.output_state.to_numpy(object).copy()
    unassessed = pd.isna(block.quality_flag).to_numpy() & (state != "complete_observed")
    state[unassessed] = "unknown"
    exact = np.where(state == "complete_observed", truth,
                     np.where(state == "estimate", block.released_estimate, np.nan))
    lower = np.where(state == "observed_bound", block.observed_lower_bound, np.nan)
    row = dict(family=family, mode=mode, station_key=station, replicate=rep,
               independence_group=block.independence_group.iloc[0],
               n_unassessed=int(unassessed.sum()), n_masked=int((block.output_state != "complete_observed").sum()),
               n_estimates=int((state == "estimate").sum()), n_bounds=int((state == "observed_bound").sum()),
               n_unknown=int((state == "unknown").sum()), truth_slope=expected)
    rows = []
    keep = np.isfinite(exact)
    value_only = row | {"method":"released_values_only", "available":int(keep.sum()) >= 5}
    if value_only["available"]:
        value_only["slope"] = float(slope(years[keep], exact[keep]))
        value_only["squared_error"] = (value_only["slope"] - expected) ** 2
    rows.append(value_only)
    model = lower_bound_trend(years, exact, lower)
    value_bound = row | {"method":"released_values_and_bounds", "available":bool(model["converged"])}
    if value_bound["available"]:
        value_bound["slope"] = model["slope"]
        value_bound["squared_error"] = (model["slope"] - expected) ** 2
    rows.append(value_bound)
    return rows


def main():
    decisions = pd.read_parquet(FOLDER / "annual_decisions.parquet")
    keys = ["family", "mode", "station_key", "replicate"]
    base = pd.read_csv(FOLDER / "station_repetitions.csv")
    missing = decisions.quality_flag.isna() & decisions.output_state.ne("complete_observed")
    needs_change = missing & decisions.output_state.isin(["estimate", "observed_bound"])
    stats = decisions.assign(unassessed=missing, changed=needs_change).groupby(keys).agg(
        n_unassessed=("unassessed", "sum"), changed=("changed", "sum")
    ).reset_index()
    affected = set(map(tuple, stats.loc[stats.changed.gt(0), keys].to_numpy()))
    groups = [(key, block) for key, block in decisions.groupby(keys, sort=True) if key in affected]
    rows = Parallel(n_jobs=8, verbose=10)(delayed(one)(key, block) for key, block in groups)
    changed = pd.DataFrame([row for pair in rows for row in pair])
    unchanged = base.merge(stats, on=keys, validate="many_to_one")
    unchanged = unchanged.loc[unchanged.changed.eq(0)].drop(columns="changed")
    strict = pd.concat([unchanged, changed], ignore_index=True)
    strict.to_csv(FOLDER / "withhold_unassessed_trends.csv", index=False)
    pairs = strict.merge(base, on=keys + ["method"], suffixes=("_strict", "_base"), validate="one_to_one")
    report = []
    for labels, group in pairs.groupby(["family", "mode", "method"]):
        valid = group.loc[group.available_strict & group.available_base]
        row = dict(zip(["family", "mode", "method"], labels), n_eligible=len(group),
                   n_common=len(valid), strict_availability=float(group.available_strict.mean()),
                   original_availability=float(group.available_base.mean()),
                   n_unassessed_years=int(group.n_unassessed.sum()),
                   strict_estimates=int(group.n_estimates_strict.sum()), original_estimates=int(group.n_estimates_base.sum()))
        if len(valid):
            row.update(original_rmse=float(np.sqrt(valid.squared_error_base.mean())),
                       strict_rmse=float(np.sqrt(valid.squared_error_strict.mean())))
        report.append(row)
    pd.DataFrame(report).to_csv(FOLDER / "withhold_unassessed_summary.csv", index=False)
    (FOLDER / "withhold_unassessed_design.json").write_text(json.dumps({
        "decision":"A missing air-agreement diagnostic forces unknown; no target outcomes enter the decision",
        "comparison":"same archive and source predictions; methods are compared on common available slopes",
        "limitation":"withholding is not evidence of numerical safety and is an exploratory choice"}, indent=2) + "\n")
    print(pd.DataFrame(report).to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
