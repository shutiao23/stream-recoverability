#!/usr/bin/env python3
"""Summarize independent-group, region and paired old/new sensitivities."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "results/whole_archive"
NEW = ROOT / "results/wrr_review_response_20261027/whole_archive"
OUT = ROOT / "results/wrr_review_response_20261027/robustness"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    trend = pd.read_csv(NEW / "trends.csv")
    station_roster = trend[["station_key", "independence_group", "region"]].drop_duplicates()
    station_roster.to_csv(OUT / "station_groups.csv", index=False)
    roster_summary = station_roster.groupby("region").agg(
        n_stations=("station_key", "nunique"), n_groups=("independence_group", "nunique")
    ).reset_index()
    roster_summary.to_csv(OUT / "region_roster.csv", index=False)

    points = trend.loc[trend.dependence.eq("point") & trend.retention.eq("all")]
    index = ["family", "mode", "station_key", "independence_group", "region", "replicate"]
    pivot = points.pivot(index=index, columns="estimator", values="squared_error")
    pairs, leave_out = [], []
    rng = np.random.default_rng(20261027)
    for (family, mode), block in pivot.groupby(level=["family", "mode"]):
        for left, right in [("D2", "stochastic_calibrated"), ("D2", "plug_in")]:
            common = block[[left, right]].dropna()
            if common.empty:
                continue
            difference = (common[left] - common[right]).rename("mse_difference")
            groups = difference.groupby(level="independence_group").agg(["sum", "count", "mean"])
            n = len(groups)
            ix = rng.integers(n, size=(4000, n))
            boot = groups["sum"].to_numpy()[ix].sum(axis=1) / groups["count"].to_numpy()[ix].sum(axis=1)
            equal_boot = groups["mean"].to_numpy()[ix].mean(axis=1)
            pairs.append(dict(family=family, mode=mode, left=left, right=right,
                              n_common=len(common), n_groups=n,
                              n_stations=common.index.get_level_values("station_key").nunique(),
                              pooled_mse_difference=difference.mean(),
                              pooled_cluster_bootstrap_low=np.quantile(boot, .025),
                              pooled_cluster_bootstrap_high=np.quantile(boot, .975),
                              group_equal_mse_difference=groups["mean"].mean(),
                              group_equal_bootstrap_low=np.quantile(equal_boot, .025),
                              group_equal_bootstrap_high=np.quantile(equal_boot, .975)))
            for region in difference.index.get_level_values("region").unique():
                remaining = difference.loc[difference.index.get_level_values("region") != region]
                leave_out.append(dict(family=family, mode=mode, left=left, right=right,
                                      excluded_region=region, n_remaining=len(remaining),
                                      n_groups=remaining.index.get_level_values("independence_group").nunique(),
                                      pooled_mse_difference=remaining.mean()))
    pd.DataFrame(pairs).to_csv(OUT / "paired_cluster_bootstrap.csv", index=False)
    pd.DataFrame(leave_out).to_csv(OUT / "leave_one_region_out.csv", index=False)

    intervals = trend.loc[trend.retention.eq("all") & trend.dependence.ne("point")].copy()
    regional = intervals.groupby(["family", "mode", "estimator", "dependence", "region"]).agg(
        eligible=("available", "size"), available=("available", "sum"),
        n_stations=("station_key", "nunique"), n_groups=("independence_group", "nunique"),
        coverage95=("missing_coverage95", "mean"), width95=("width95", "mean"),
        interval_score95=("interval_score95", "mean"),
    ).reset_index()
    regional.to_csv(OUT / "interval_by_region.csv", index=False)

    old = pd.read_csv(OLD / "annual.csv")
    new = pd.read_csv(NEW / "annual.csv")
    keys = ["family", "mode", "station_key", "replicate", "estimator"]
    annual = old.merge(new, on=keys, suffixes=("_old", "_new"), validate="one_to_one")
    changes = annual.groupby(["family", "mode", "estimator"]).agg(
        n_paired=("replicate", "size"),
        old_station_mae=("mae_old", "mean"), new_station_mae=("mae_new", "mean"),
        old_station_coverage90=("coverage90_old", "mean"),
        new_station_coverage90=("coverage90_new", "mean"),
        old_available_years=("n_available_old", "sum"), new_available_years=("n_available_new", "sum"),
    ).reset_index()
    changes.to_csv(OUT / "annual_before_after.csv", index=False)

    old_intervals = pd.read_csv(OLD / "trends.csv")
    old_intervals = old_intervals.loc[old_intervals.retention.eq("all") & old_intervals.dependence.ne("point")]
    common = old_intervals.merge(intervals, on=keys + ["dependence"],
                                 suffixes=("_old", "_new"), validate="one_to_one")
    common = common.loc[common.available_old & common.available_new]
    interval_changes = common.groupby(["family", "mode", "estimator", "dependence"]).agg(
        n_common=("replicate", "size"),
        old_coverage95=("missing_coverage95_old", "mean"),
        new_coverage95=("missing_coverage95_new", "mean"),
        old_width95=("width95_old", "mean"), new_width95=("width95_new", "mean"),
        old_interval_score95=("interval_score95_old", "mean"),
        new_interval_score95=("interval_score95_new", "mean"),
    ).reset_index()
    interval_changes.to_csv(OUT / "interval_before_after.csv", index=False)
    print(roster_summary.to_string(index=False), flush=True)
    print(pd.DataFrame(pairs).to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
