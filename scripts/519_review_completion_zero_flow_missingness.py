#!/usr/bin/env python3
"""Requested C1 stratification using recorded zero flow as a limited proxy.

Preserves the historical station-year sample, exposure and conditional-logit
specification. Unknown discharge stays unknown. Zero flow does not establish
an intermittent-river class, sensor exposure, or a defined dry-bed temperature.
"""
from __future__ import annotations
import os
for key in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"]:
    os.environ[key] = "1"
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

OUT = T.ROOT / "results/wrr_review_completion_20261024/zero_flow_missingness"


def zero_flow_proxy(flow):
    numeric = pd.to_numeric(flow.flow_cms, errors="coerce")
    good = flow.flow_code.astype(str).str.startswith("A") & numeric.ge(0) & np.isfinite(numeric)
    values = flow.loc[good].copy()
    values["flow_cms"] = numeric.loc[good]
    # Count unique native dates, preserving contradictory duplicate dates as
    # unavailable rather than creating a zero-flow label from one channel.
    groups = values.groupby(["site", "date"]).flow_cms
    unique = groups.agg(value="first", n_values="nunique").reset_index()
    unique = unique.loc[unique.n_values.eq(1)]
    summary = unique.groupby("site").agg(approved_days=("date", "size"),
        zero_days=("value", lambda x: int(x.eq(0).sum())), first_date=("date", "min"), last_date=("date", "max")).reset_index()
    summary["station_key"] = "usgs|" + summary.site.astype(str)
    return summary


def missingness_model():
    # The real file stem is importable in spawned workers. A transient alias
    # registered only in the parent cannot be unpickled by joblib.
    return importlib.import_module("430_tr_e1_missingness")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--draws", type=int, default=400)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    source = T.E1.parent / "e1_missingness/station_year_sample.parquet"
    flow_path = T.E1 / "usgs_flow.parquet"
    sample = pd.read_parquet(source)
    sample = sample.loc[sample.provider.eq("usgs")].copy()
    proxy = zero_flow_proxy(pd.read_parquet(flow_path, columns=["site", "date", "flow_cms", "flow_code"]))
    proxy.to_csv(OUT / "zero_flow_station_proxy.csv", index=False)
    sample = sample.merge(proxy[["station_key", "approved_days", "zero_days"]], on="station_key", how="left", validate="many_to_one")
    sample["proxy_class"] = np.select([sample.zero_days.gt(0), sample.zero_days.eq(0)],
        ["recorded_zero_flow", "no_zero_in_available_flow"], default="no_approved_flow")
    sample.to_parquet(OUT / "station_year_sample.parquet", index=False)
    model = missingness_model()
    rows, cohorts = [], []
    subsets = [(label, b) for label, b in sample.groupby("proxy_class")]
    subsets += [("at_least30_zero_days", sample.loc[sample.zero_days.ge(30)]),
                ("fewer_than30_zero_days", sample.loc[sample.zero_days.lt(30)])]
    for number, (label, block) in enumerate(subsets):
        cohorts.append({"proxy_class": label, "n_station_year_rows": len(block), "n_physical_stations": block.station_key.nunique(),
            "n_independence_groups": block.independence_group.nunique(), "incomplete_fraction": block.warm_incomplete.mean()})
        specifications = [("air_and_trend", ["z_air", "trend"])]
        if label != "no_approved_flow":
            specifications.append(("air_flow_and_trend", ["z_air", "z_flow", "trend"]))
        for name, covariates in specifications:
            point = model.conditional_fit(block, "warm_incomplete", covariates, "station_key")
            boot = model.bootstrap_conditional(block, "warm_incomplete", covariates, "station_key", args.draws, 519+number, args.workers)
            boot.to_csv(OUT / f"bootstrap_{label}_{name}.csv", index=False)
            results = model.summarise(point, boot, covariates, name)
            for row in results:
                row["proxy_class"] = label
                row["n_physical_stations_in_cohort"] = block.station_key.nunique()
                row["n_independence_groups_in_cohort"] = block.independence_group.nunique()
            rows.extend(results)
            print(f"Completed {label} {name}: {point.get('n_events', 0)} events", flush=True)
    pd.DataFrame(rows).to_csv(OUT / "conditional_logit_summary.csv", index=False)
    pd.DataFrame(cohorts).to_csv(OUT / "cohort_counts.csv", index=False)
    sources = [source, flow_path, Path(__file__), T.ROOT / "scripts/430_tr_e1_missingness.py"]
    T.write_json(OUT / "status.json", {"complete": True, "bootstrap_draws": args.draws,
        "n_USGS_station_year_rows": len(sample), "n_USGS_physical_stations": sample.station_key.nunique(),
        "n_flow_stations_with_recorded_zero": int(proxy.zero_days.gt(0).sum()),
        "source_sha256": {str(p.relative_to(T.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        "limits": "Recorded approved zero flow is a historical proxy, not an intermittent-river or dry-bed classification. No recorded zero does not prove perennial flow. Association is not causation, a missing-at-random test or a rule for sensor validity.",
        "new_NZ_water_values_requested": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
