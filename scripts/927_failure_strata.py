#!/usr/bin/env python3
"""Describe when annual recovery fails, using strata visible in the saved cases.

The peak-visibility stratum uses the complete reference and is therefore an
evaluation-only description, not a deployable screening rule.  Gap length,
training-peak overlap and visible donor count are known at decision time, but
the bins here were chosen after inspection and remain descriptive.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.archive import LEVELS
from stream_recoverability.experiments.tr_revision.statistics import interval_score

BASE = T.ROOT / "results/wrr_review_response_20261027/whole_archive"
OUT = T.ROOT / "results/wrr_adversarial_review_20261027/failure_strata"
TOL = 1e-8
BOOTSTRAP = 2000


def truth_lookup() -> pd.DataFrame:
    reference = pd.read_parquet(
        T.ROOT / "results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet",
        columns=["station_key", "year", "design_family", "eval_truth_h30"],
    )
    if reference.groupby(["station_key", "year", "design_family"]).eval_truth_h30.nunique().max() != 1:
        raise RuntimeError("Reference truth is not unique by station-year-family")
    return reference.drop_duplicates(
        ["station_key", "year", "design_family"]
    ).rename(columns={"design_family": "family", "eval_truth_h30": "reference_h30"})


def load_cases(family: str = "crossed", mode: str = "forward") -> pd.DataFrame:
    truth = truth_lookup()
    parts = []
    for path in sorted((BASE / family / mode).glob("replicate_*/*/annual_predictions.parquet")):
        data = pd.read_parquet(path)
        if data.empty:
            continue
        data = data.copy()
        data["family"] = family
        data["mode"] = mode
        data["replicate"] = int(path.parent.parent.name.removeprefix("replicate_"))
        data["station_key"] = data["station_key"].astype(str)
        data["year"] = data["year"].astype(int)
        parts.append(data)
    if not parts:
        raise RuntimeError("No annual prediction files found")
    cases = pd.concat(parts, ignore_index=True)
    cases = cases.merge(
        truth, on=["station_key", "year", "family"], how="left", validate="many_to_one"
    )
    if not np.isfinite(cases.reference_h30).all():
        raise RuntimeError("Every evaluated year needs a finite complete reference")
    return cases


def overlap_labels(values: pd.Series) -> pd.Series:
    """Bin training-peak overlap so that ``at least half'' means overlap >= 0.5.

    Values at or below 0.001 stay in ``no overlap'', matching the previous
    numerical tolerance for a zero overlap. The boundary 0.5 itself is included
    in ``at least half'', consistent with the annual danger threshold.
    """
    x = pd.to_numeric(values, errors="raise").to_numpy(float)
    if np.any(~np.isfinite(x) | (x < -0.001) | (x > 1.001)):
        raise ValueError("Training-peak overlap is outside [-0.001, 1.001]")
    labels = np.full(len(x), "partial", dtype=object)
    labels[x <= 0.001] = "no overlap"
    labels[x >= 0.5] = "at least half"
    return pd.Series(
        pd.Categorical(
            labels,
            categories=["no overlap", "partial", "at least half"],
            ordered=True,
        ),
        index=values.index,
    )


def add_scores(cases: pd.DataFrame) -> pd.DataFrame:
    qcols = [f"{method}_q{int(100 * level):02d}" for method in ["D2", "stochastic_cal"] for level in LEVELS]
    finite = np.isfinite(cases[qcols].to_numpy(float)).all(axis=1) & cases.observed_lower_bound__observed_days.notna()
    work = cases.loc[finite].copy()
    for method, label in [("D2", "D2"), ("stochastic_cal", "stochastic")]:
        q = work[[f"{method}_q{int(100 * level):02d}" for level in LEVELS]].to_numpy(float)
        point = work[f"{method}_q50"].to_numpy(float)
        truth = work.reference_h30.to_numpy(float)
        work[f"mae_{label}"] = np.abs(point - truth)
        work[f"coverage90_{label}"] = ((q[:, 0] - TOL <= truth) & (truth <= q[:, -1] + TOL)).astype(float)
        work[f"width90_{label}"] = q[:, -1] - q[:, 0]
        work[f"interval_score90_{label}"] = [
            interval_score(low, high, target, alpha=0.10)
            for low, high, target in zip(q[:, 0], q[:, -1], truth)
        ]
    work["peak_visible"] = work.reference_h30 <= work.observed_lower_bound__observed_days + TOL
    work["peak_hidden"] = ~work.peak_visible
    work["gap_bin"] = pd.cut(
        work.longest_run,
        bins=[-0.1, 30.1, 60.1, np.inf],
        labels=["30 d", "31--60 d", "61--90 d"],
    )
    work["overlap_bin"] = overlap_labels(work.peak_overlap)
    work["donor_bin"] = pd.cut(
        work.n_visible_donors,
        bins=[-0.1, 0.1, 3.1, np.inf],
        labels=["0", "1--3", "4+"],
    )
    return work


def summarize(work: pd.DataFrame, column: str, label: str) -> pd.DataFrame:
    rows = []
    for value, block in work.groupby(column, observed=True, dropna=False):
        for method in ["D2", "stochastic"]:
            mae = block[f"mae_{method}"].to_numpy(float)
            coverage = block[f"coverage90_{method}"].to_numpy(float)
            width = block[f"width90_{method}"].to_numpy(float)
            score = block[f"interval_score90_{method}"].to_numpy(float)
            groups = block.independence_group.to_numpy()
            group_values = {
                "mae": pd.Series(mae).groupby(groups).mean().to_numpy(),
                "coverage": pd.Series(coverage).groupby(groups).mean().to_numpy(),
                "width": pd.Series(width).groupby(groups).mean().to_numpy(),
                "score": pd.Series(score).groupby(groups).mean().to_numpy(),
            }
            rng = np.random.default_rng(20261027)
            unique_groups = np.array(sorted(set(groups)))
            draws = {key: [] for key in group_values}
            for _ in range(BOOTSTRAP):
                chosen = rng.choice(unique_groups, size=len(unique_groups), replace=True)
                index = np.concatenate([np.flatnonzero(groups == group) for group in chosen])
                draws["mae"].append(float(np.mean(mae[index])))
                draws["coverage"].append(float(np.mean(coverage[index])))
                draws["width"].append(float(np.mean(width[index])))
                draws["score"].append(float(np.mean(score[index])))
            rows.append(
                {
                    "stratum_type": label,
                    "stratum": str(value),
                    "method": method,
                    "n": len(block),
                    "stations": block.station_key.nunique(),
                    "station_years": block[["station_key", "year"]].drop_duplicates().shape[0],
                    "groups": block.independence_group.nunique(),
                    "regions": block.region.nunique(),
                    "mae": float(np.mean(mae)),
                    "mae_group_equal": float(group_values["mae"].mean()),
                    "mae_bootstrap_low": float(np.quantile(draws["mae"], 0.025)),
                    "mae_bootstrap_high": float(np.quantile(draws["mae"], 0.975)),
                    "coverage90": float(np.mean(coverage)),
                    "coverage90_group_equal": float(group_values["coverage"].mean()),
                    "coverage90_bootstrap_low": float(np.quantile(draws["coverage"], 0.025)),
                    "coverage90_bootstrap_high": float(np.quantile(draws["coverage"], 0.975)),
                    "width90": float(np.mean(width)),
                    "width90_group_equal": float(group_values["width"].mean()),
                    "width90_bootstrap_low": float(np.quantile(draws["width"], 0.025)),
                    "width90_bootstrap_high": float(np.quantile(draws["width"], 0.975)),
                    "interval_score90": float(np.mean(score)),
                    "interval_score90_group_equal": float(group_values["score"].mean()),
                    "interval_score90_bootstrap_low": float(np.quantile(draws["score"], 0.025)),
                    "interval_score90_bootstrap_high": float(np.quantile(draws["score"], 0.975)),
                }
            )
    return pd.DataFrame(rows)


def leave_region_out(work: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for region in sorted(work.region.unique()):
        keep = work.region.ne(region)
        block = work.loc[keep]
        if block.empty:
            continue
        for metric in ["mae", "coverage90", "width90", "interval_score90"]:
            left = block[f"{metric}_D2"].to_numpy(float)
            right = block[f"{metric}_stochastic"].to_numpy(float)
            diff = left - right
            groups = block.independence_group.to_numpy()
            group_diff = pd.Series(diff).groupby(groups).mean().to_numpy()
            rng = np.random.default_rng(20261027)
            unique = np.array(sorted(set(groups)))
            draws = []
            for _ in range(BOOTSTRAP):
                chosen = rng.choice(unique, size=len(unique), replace=True)
                index = np.concatenate([np.flatnonzero(groups == group) for group in chosen])
                draws.append(float(np.mean(diff[index])))
            rows.append(
                {
                    "excluded_region": region,
                    "metric": metric,
                    "n_remaining": len(block),
                    "groups_remaining": block.independence_group.nunique(),
                    "difference_D2_minus_stochastic": float(np.mean(diff)),
                    "group_equal_difference": float(np.mean(group_diff)),
                    "bootstrap_low": float(np.quantile(draws, 0.025)),
                    "bootstrap_high": float(np.quantile(draws, 0.975)),
                }
            )
    return pd.DataFrame(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = add_scores(load_cases("crossed", "forward"))
    cases.to_parquet(OUT / "failure_strata_cases.parquet", index=False)
    frames = [
        summarize(cases, "peak_hidden", "reference peak"),
        summarize(cases, "gap_bin", "longest gap"),
        summarize(cases, "overlap_bin", "training peak overlap"),
        summarize(cases, "donor_bin", "visible donors"),
        summarize(cases, "region", "region"),
    ]
    # Rename the peak stratum for readability.
    peak = frames[0].copy()
    peak["stratum"] = peak.stratum.map({"True": "reference peak above bound", "False": "reference peak at bound"})
    frames[0] = peak
    summary = pd.concat(frames, ignore_index=True)
    summary.to_csv(OUT / "failure_strata_summary.csv", index=False)
    leave = leave_region_out(cases)
    leave.to_csv(OUT / "failure_strata_leave_region_out.csv", index=False)

    overall = summary.loc[
        summary.stratum_type.eq("reference peak")
        & summary.stratum.eq("reference peak at bound")
        | summary.stratum_type.eq("reference peak")
        & summary.stratum.eq("reference peak above bound")
    ]
    report = {
        "scope": "crossed forward controlled gaps, common finite D2 and stochastic quantiles",
        "cases": len(cases),
        "stations": int(cases.station_key.nunique()),
        "groups": int(cases.independence_group.nunique()),
        "regions": int(cases.region.nunique()),
        "peak_visible_n": int((~cases.peak_hidden).sum()),
        "peak_hidden_n": int(cases.peak_hidden.sum()),
        "peak_hidden_D2_coverage90": float(
            cases.loc[cases.peak_hidden, "coverage90_D2"].mean()
        ),
        "peak_hidden_stochastic_coverage90": float(
            cases.loc[cases.peak_hidden, "coverage90_stochastic"].mean()
        ),
        "peak_hidden_D2_mae": float(cases.loc[cases.peak_hidden, "mae_D2"].mean()),
        "peak_hidden_stochastic_mae": float(
            cases.loc[cases.peak_hidden, "mae_stochastic"].mean()
        ),
        "limits": [
            "peak visibility uses the complete reference and is not available at decision time",
            "gap, overlap and donor bins are post-hoc descriptive strata",
            "at least half includes overlap equal to 0.5; no overlap is overlap at most 0.001",
            "repeated masks are not independent rivers or climates",
            "group bootstrap is descriptive, not a population guarantee",
        ],
    }
    (OUT / "failure_strata_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(summary.loc[summary.stratum_type.eq("reference peak")].to_string(index=False), flush=True)
    print(leave.to_string(index=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
