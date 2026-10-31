#!/usr/bin/env python3
"""Pair release-then-trend results with the archive's original trend baselines."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / "results/wrr_review_response_20261027"


def main():
    folder = ROOT / "integrated_release_trend"
    integrated = pd.read_csv(folder / "station_repetitions.csv")
    trend = pd.read_csv(ROOT / "whole_archive/trends.csv")
    bases = trend.loc[trend.dependence.eq("point") & trend.estimator.eq("D2")]
    keys = ["family", "mode", "station_key", "replicate"]
    rows = []
    rng = np.random.default_rng(20261027)
    for retention in ["warm90", "all"]:
        base = bases.loc[bases.retention.eq(retention)]
        for method in integrated.method.unique():
            comparison = integrated.loc[integrated.method.eq(method)].merge(
                base[keys + ["available", "squared_error"]], on=keys,
                suffixes=("_release", "_baseline"), validate="one_to_one")
            for (family, mode), block in comparison.groupby(["family", "mode"]):
                valid = block.loc[block.available_release & block.available_baseline]
                difference = valid.squared_error_release - valid.squared_error_baseline
                groups = valid.assign(difference=difference).groupby("independence_group").difference.agg(["sum", "count", "mean"])
                if len(groups):
                    ix = rng.integers(len(groups), size=(4000, len(groups)))
                    bootstrap = groups["sum"].to_numpy()[ix].sum(axis=1) / groups["count"].to_numpy()[ix].sum(axis=1)
                    low, high = np.quantile(bootstrap, [.025, .975])
                else:
                    low = high = np.nan
                rows.append(dict(family=family, mode=mode, release_method=method,
                                 baseline=retention, n_eligible=len(block), n_common=len(valid),
                                 baseline_availability=float(block.available_baseline.mean()),
                                 release_availability=float(block.available_release.mean()),
                                 n_groups=valid.independence_group.nunique(),
                                 baseline_rmse=float(np.sqrt(valid.squared_error_baseline.mean())) if len(valid) else np.nan,
                                 release_rmse=float(np.sqrt(valid.squared_error_release.mean())) if len(valid) else np.nan,
                                 paired_mse_difference=float(difference.mean()) if len(valid) else np.nan,
                                 group_equal_mse_difference=float(groups["mean"].mean()) if len(groups) else np.nan,
                                 cluster_bootstrap_low=low, cluster_bootstrap_high=high))
    result = pd.DataFrame(rows)
    result.to_csv(folder / "paired_baselines.csv", index=False)
    print(result.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
