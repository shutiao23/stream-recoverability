#!/usr/bin/env python3
"""Score-bootstrap sensitivity intervals for the paired RMSE comparisons.

The frozen case study resamples 17 connected groups with replacement
(multinomial group bootstrap). With so few clusters that interval can be
narrow or unstable. This script adds cluster-robust alternatives that never
resample clusters: a score bootstrap on the linearized RMSE-difference
statistic (centered influence function reweighted by Rademacher or Webb
six-point cluster signs, in the sense of Kline and Santos 2012), and a wild
interval for the paired mean difference of squared errors. Neither carries a
finite-sample coverage guarantee with 17 unequal clusters; both are reported
as sensitivity checks against the group-resampling intervals. Inputs are the
frozen per-archive tables; nothing is refitted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "results/wrr_final_revision_20261031/retention_geometry_cases.csv"
INTERVALS = ROOT / "results/wrr_final_revision_20261031/retention_paired_intervals.csv"
TRENDS = ROOT / "results/wrr_review_response_20261027/whole_archive/trends.csv"
ESTIMATOR = ROOT / "results/wrr_final_revision_20261031/estimator_paired_comparisons.csv"
OUT = ROOT / "results/ems_revision_20261102"
KEY = ["station_key", "replicate", "independence_group"]
DRAWS = 10_000
SEED = 20261102
WEBB = np.array([-np.sqrt(1.5), -1.0, -np.sqrt(0.5), np.sqrt(0.5), 1.0, np.sqrt(1.5)])


def cluster_shares(labels: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    groups = sorted(set(labels))
    counts = np.array([(labels == g).sum() for g in groups], float)
    return np.array(groups), counts / counts.sum()


def wild_influence_interval(mse_a: np.ndarray, mse_b: np.ndarray, labels: np.ndarray,
                            weights: str = "rademacher", seed: int = SEED,
                            draws: int = DRAWS) -> dict:
    """Score-bootstrap CI for RMSE_A - RMSE_B on the linearized statistic.

    The influence function of sqrt(mean(mse)) at observation i is
    (mse_i - mean(mse)) / (2 sqrt(mean(mse))), so the influence function of the
    RMSE difference is exactly mean-zero. Cluster means of this centered
    influence function are reweighted with Rademacher or Webb signs; clusters
    are never resampled. This is a score bootstrap on the linearized statistic
    in the sense of Kline and Santos (2012); with 17 unequal clusters it has no
    finite-sample coverage guarantee and is reported as a sensitivity check.
    """
    mse_a = np.asarray(mse_a, float)
    mse_b = np.asarray(mse_b, float)
    if mse_a.shape != mse_b.shape or labels.shape != mse_a.shape:
        raise ValueError("aligned arrays required")
    if not (np.isfinite(mse_a).all() and np.isfinite(mse_b).all()):
        raise ValueError("squared errors must be finite")
    root_a = float(np.sqrt(mse_a.mean()))
    root_b = float(np.sqrt(mse_b.mean()))
    estimate = root_a - root_b
    influence = (mse_a - mse_a.mean()) / (2 * root_a) - (mse_b - mse_b.mean()) / (2 * root_b)
    if abs(float(influence.mean())) > 1e-12 * max(1.0, abs(estimate)):
        raise RuntimeError("influence function is not centered")
    groups, share = cluster_shares(pd.Series(labels))
    contributions = np.array([influence[labels == g].mean() for g in groups])
    rng = np.random.default_rng(seed)
    if weights == "rademacher":
        w = rng.choice([-1.0, 1.0], size=(draws, len(groups)))
    elif weights == "webb":
        w = rng.choice(WEBB, size=(draws, len(groups)))
    else:
        raise ValueError("weights must be rademacher or webb")
    draws_stat = w @ (share * contributions)
    low, high = np.quantile(draws_stat, [0.025, 0.975])
    return {
        "estimate": estimate,
        "ci_low": float(estimate + low),
        "ci_high": float(estimate + high),
        "groups": int(len(groups)),
        "draws": draws,
        "weights": weights,
        "seed": seed,
    }


def wild_mean_mse_interval(mse_a: np.ndarray, mse_b: np.ndarray, labels: np.ndarray,
                           seed: int = SEED, draws: int = DRAWS) -> dict:
    """Wild cluster CI for the paired mean difference of squared errors."""
    difference = np.asarray(mse_a, float) - np.asarray(mse_b, float)
    estimate = float(difference.mean())
    groups, share = cluster_shares(pd.Series(labels))
    contributions = np.array([difference[labels == g].mean() for g in groups]) - estimate
    rng = np.random.default_rng(seed)
    w = rng.choice([-1.0, 1.0], size=(draws, len(groups)))
    draws_stat = w @ (share * contributions)
    low, high = np.quantile(draws_stat, [0.025, 0.975])
    return {"estimate": estimate, "ci_low": float(estimate + low), "ci_high": float(estimate + high)}


def retention_rows() -> list[dict]:
    cases = pd.read_csv(CASES)
    saved = pd.read_csv(INTERVALS).set_index(["family", "scheme"])
    rows = []
    for family, block in cases.groupby("family"):
        wide = block.pivot(index=KEY, columns="scheme", values="estimate_mse")
        labels = wide.index.get_level_values("independence_group").to_numpy()
        for scheme in ["uniform_exact", "cdf_all_years", "sxx_all_years", "all"]:
            pair = wide[["warm90", scheme]].dropna()
            mask = np.isin(labels, sorted(set(pair.index.get_level_values("independence_group"))))
            row_labels = labels[mask]
            rademacher = wild_influence_interval(pair[scheme].to_numpy(), pair["warm90"].to_numpy(), row_labels)
            webb = wild_influence_interval(pair[scheme].to_numpy(), pair["warm90"].to_numpy(), row_labels, weights="webb")
            mean_mse = wild_mean_mse_interval(pair[scheme].to_numpy(), pair["warm90"].to_numpy(), row_labels)
            reference = saved.loc[(family, scheme)]
            rows.append({
                "comparison": "retention",
                "family": family,
                "contrast": scheme + " minus warm90",
                "n": int(len(pair)),
                "groups": rademacher["groups"],
                "estimate": rademacher["estimate"],
                "group_boot_ci_low": float(reference.ci_low),
                "group_boot_ci_high": float(reference.ci_high),
                "group_boot_width": float(reference.ci_high - reference.ci_low),
                "wild_rademacher_ci_low": rademacher["ci_low"],
                "wild_rademacher_ci_high": rademacher["ci_high"],
                "wild_webb_ci_low": webb["ci_low"],
                "wild_webb_ci_high": webb["ci_high"],
                "wild_mean_mse_ci_low": mean_mse["ci_low"],
                "wild_mean_mse_ci_high": mean_mse["ci_high"],
            })
    return rows


def estimator_rows() -> list[dict]:
    trends = pd.read_csv(TRENDS)
    saved = pd.read_csv(ESTIMATOR).set_index(["family", "comparator"])
    selected = trends.loc[
        trends["mode"].eq("forward") & trends.dependence.eq("point") & trends.retention.eq("all")
    ]
    rows = []
    for family, block in selected.groupby("family"):
        valid = block.loc[block.available & block.error.notna()]
        wide = valid.pivot(index=KEY, columns="estimator", values="error")
        pair = wide[["D2", "stochastic_calibrated"]].dropna()
        labels = pair.index.get_level_values("independence_group").to_numpy()
        mse_d2 = pair["D2"].to_numpy(float) ** 2
        mse_classic = pair["stochastic_calibrated"].to_numpy(float) ** 2
        rademacher = wild_influence_interval(mse_d2, mse_classic, labels)
        webb = wild_influence_interval(mse_d2, mse_classic, labels, weights="webb")
        mean_mse = wild_mean_mse_interval(mse_d2, mse_classic, labels)
        reference = saved.loc[(family, "stochastic_calibrated")]
        rows.append({
            "comparison": "estimator",
            "family": family,
            "contrast": "D2 minus stochastic_calibrated",
            "n": int(len(pair)),
            "groups": rademacher["groups"],
            "estimate": rademacher["estimate"],
            "group_boot_ci_low": float(reference.ci_low),
            "group_boot_ci_high": float(reference.ci_high),
            "group_boot_width": float(reference.ci_high - reference.ci_low),
            "wild_rademacher_ci_low": rademacher["ci_low"],
            "wild_rademacher_ci_high": rademacher["ci_high"],
            "wild_webb_ci_low": webb["ci_low"],
            "wild_webb_ci_high": webb["ci_high"],
            "wild_mean_mse_ci_low": mean_mse["ci_low"],
            "wild_mean_mse_ci_high": mean_mse["ci_high"],
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rows = retention_rows() + estimator_rows()
    frame = pd.DataFrame(rows)
    frame["wild_rademacher_width"] = frame.wild_rademacher_ci_high - frame.wild_rademacher_ci_low
    frame["width_ratio_wild_over_group"] = frame.wild_rademacher_width / frame.group_boot_width
    frame.to_csv(args.out / "wild_cluster_bootstrap.csv", index=False)
    crossing = frame.loc[
        (frame.wild_rademacher_ci_low <= 0) & (frame.wild_rademacher_ci_high >= 0)
        & (frame.comparison.eq("retention"))
    ]
    report = {
        "schema": "wild_cluster_bootstrap_v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "draws": DRAWS,
        "seed": SEED,
        "clusters": 17,
        "method": ("score bootstrap on the centered influence function of the RMSE difference "
                   "(Kline and Santos 2012); Rademacher and Webb six-point cluster weights; "
                   "clusters are never resampled; no finite-sample coverage guarantee"),
        "scope": ("frozen per-archive tables only; no refit, no new masks; the group-bootstrap "
                  "columns reproduce the saved multinomial group intervals for comparison"),
        "rows": int(len(frame)),
        "retention_directions": {
            f"{row.family}/{row.contrast}": {
                "group_boot_excludes_zero": bool(row.group_boot_ci_low > 0 or row.group_boot_ci_high < 0),
                "wild_rademacher_excludes_zero": bool(row.wild_rademacher_ci_low > 0 or row.wild_rademacher_ci_high < 0),
                "wild_webb_excludes_zero": bool(row.wild_webb_ci_low > 0 or row.wild_webb_ci_high < 0),
            }
            for row in frame.loc[frame.comparison.eq("retention")].itertuples(index=False)
        },
        "mean_width_ratio_wild_over_group": float(frame.width_ratio_wild_over_group.mean()),
        "median_width_ratio_wild_over_group": float(frame.width_ratio_wild_over_group.median()),
    }
    (args.out / "wild_cluster_bootstrap.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps({
        "rows": len(frame),
        "median_width_ratio": report["median_width_ratio_wild_over_group"],
        "calendar_cdf_wild": [
            float(frame.loc[(frame.family.eq("calendar")) & (frame.contrast.eq("cdf_all_years minus warm90")), "wild_rademacher_ci_low"].iloc[0]),
            float(frame.loc[(frame.family.eq("calendar")) & (frame.contrast.eq("cdf_all_years minus warm90")), "wild_rademacher_ci_high"].iloc[0]),
        ],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
