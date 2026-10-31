#!/usr/bin/env python3
"""Numerical convergence of the three fixed-marginal joint-rank constructions.

The annual quantiles, observed bounds and evaluation years are fixed.  Only the
number of stratified annual samples and the joint-rank construction change.
This is a post-hoc numerical sensitivity on the difficult forward controlled
gaps, not an independent validation or a posterior for the annual model.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_tr_common as T
from stream_recoverability.experiments.development_recovery import (
    read_temperature_panel,
)
from stream_recoverability.experiments.tr_revision.archive import (
    LEVELS,
    history_ranks,
    marginal_draws,
    mask_archive,
    reorder_marginals,
    slope,
)
from stream_recoverability.experiments.tr_revision.statistics import interval_score
from stream_recoverability.experiments.v19_revision.data import station_air_series
from stream_recoverability.seeds import plain_seed

BASE = T.ROOT / "results/wrr_review_response_20261027/whole_archive"
OUT = T.ROOT / "results/wrr_adversarial_review_20261027/rank_convergence"
REFERENCE = T.ROOT / "results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet"
DRAWS = [256, 1024, 4096]
SEEDS = [0, 1, 2]
CONSTRUCTIONS = ["independent", "shared_parameters", "residual_blocks"]
TOL = 1e-8


def reference_table() -> pd.DataFrame:
    reference = pd.read_parquet(
        REFERENCE,
        columns=["station_key", "year", "design_family", "eval_truth_h30"],
    )
    if reference.groupby(["station_key", "year", "design_family"]).eval_truth_h30.nunique().max() != 1:
        raise RuntimeError("Reference truth is not unique by station-year-family")
    return reference.drop_duplicates(
        ["station_key", "year", "design_family"]
    ).rename(columns={"design_family": "family", "eval_truth_h30": "reference_h30"})


def annual_archives(station: str) -> list[Path]:
    return sorted(
        (BASE / "crossed" / "forward").glob(
            f"replicate_*/*/annual_predictions.parquet"
        )
    )


def process_station(job: dict, replicates: list[int], reference: pd.DataFrame) -> list[dict]:
    panel = read_temperature_panel(job["input_path"]).asfreq("D")
    panel.columns = panel.columns.astype(str)
    shift = T.hemisphere_shift_days(job.get("latitude"))
    real_index = panel.index
    analysis = panel.copy()
    analysis.index += pd.Timedelta(days=shift)
    air = station_air_series(
        Path(job["air_input_path"]), job["network_id"], job["station_id"], real_index
    )
    if air is not None:
        air.index = analysis.index
    years_all = np.sort(
        reference.loc[reference.station_key.eq(job["station_key"]) & reference.family.eq("crossed"), "year"].unique()
    )
    years = years_all[years_all >= 2010]
    truth_frame = (
        reference.loc[reference.station_key.eq(job["station_key"]) & reference.family.eq("crossed")]
        .drop_duplicates("year")
        .set_index("year")
    )
    rows = []
    for replicate in replicates:
        folder = (
            BASE
            / "crossed"
            / "forward"
            / f"replicate_{replicate:02d}"
            / job["station_key"].replace("|", "_")
        )
        prediction_path = folder / "annual_predictions.parquet"
        design_path = folder / "design.json"
        if not prediction_path.exists() or not design_path.exists():
            continue
        design = json.loads(design_path.read_text())
        masks = {int(year): runs for year, runs in design.get("masks", {}).items()}
        incomplete = np.isin(years, list(masks))
        if not incomplete.any() or len(years) < 5:
            continue
        truth = truth_frame.loc[years, "reference_h30"].to_numpy(float)
        predictions = pd.read_parquet(prediction_path).set_index("year").reindex(years)
        if predictions.empty:
            continue
        bounds = predictions.get(
            "observed_lower_bound__observed_days", pd.Series(np.nan, index=years)
        ).to_numpy(float)
        bounds[~incomplete] = truth[~incomplete]
        visible = mask_archive(analysis, job["station_id"], masks)
        history_target = visible[job["station_id"]].copy()
        for method, prefix in [("D2", "D2"), ("stochastic_cal", "stochastic_cal")]:
            qcols = [f"{prefix}_q{int(100 * level):02d}" for level in LEVELS]
            if not set(qcols).issubset(predictions.columns):
                continue
            quantiles = predictions[qcols].to_numpy(float)
            quantiles[~incomplete] = truth[~incomplete, None]
            if not np.isfinite(quantiles).all():
                continue
            point = predictions[f"{prefix}_q50"].to_numpy(float)
            point[~incomplete] = truth[~incomplete]
            for seed_index in SEEDS:
                seed = plain_seed(730, job["station_index"], replicate, seed_index)
                rng = np.random.default_rng(seed)
                ranks = {
                    "independent": rng.normal(size=(max(DRAWS), len(years))),
                    "shared_parameters": history_ranks(
                        history_target,
                        air,
                        masks,
                        years,
                        draws=max(DRAWS),
                        seed=seed,
                        block=1,
                        fit_before=2010,
                    ),
                    "residual_blocks": history_ranks(
                        history_target,
                        air,
                        masks,
                        years,
                        draws=max(DRAWS),
                        seed=seed,
                        block=3,
                        fit_before=2010,
                    ),
                }
                for construction in CONSTRUCTIONS:
                    rank = ranks[construction]
                    if rank is None:
                        continue
                    for draws in DRAWS:
                        base = marginal_draws(
                            quantiles, draws, lower_bounds=bounds
                        )
                        samples = reorder_marginals(base, rank[:draws])
                        slopes = slope(years, samples)
                        low, high = np.quantile(slopes, [0.025, 0.975])
                        reference_slope = float(slope(years, truth))
                        rows.append(
                            {
                                "station_key": job["station_key"],
                                "independence_group": job["independence_group"],
                                "region": job["region"],
                                "replicate": replicate,
                                "method": method,
                                "construction": construction,
                                "draws": draws,
                                "seed": seed_index,
                                "covered": bool(
                                    low - 1e-12 <= reference_slope <= high + 1e-12
                                ),
                                "lower_error": float(low - reference_slope),
                                "upper_error": float(high - reference_slope),
                                "width": float(high - low),
                                "interval_score": float(
                                    interval_score(low, high, reference_slope, alpha=0.05)
                                ),
                            }
                        )
    return rows


def group_bootstrap(
    frame: pd.DataFrame, value: str, groups: str = "independence_group", draws: int = 2000
) -> tuple[float, float]:
    rng = np.random.default_rng(20261027)
    unique = np.array(sorted(frame[groups].unique()))
    values = frame[value].to_numpy(float)
    labels = frame[groups].to_numpy()
    estimates = []
    for _ in range(draws):
        chosen = rng.choice(unique, size=len(unique), replace=True)
        index = np.concatenate([np.flatnonzero(labels == group) for group in chosen])
        estimates.append(float(np.mean(values[index])))
    return float(np.quantile(estimates, 0.025)), float(np.quantile(estimates, 0.975))


def summarize(cases: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    summary_rows = []
    contrast_rows = []
    for (method, construction, draws), block in cases.groupby(
        ["method", "construction", "draws"], sort=True
    ):
        per_seed = block.groupby("seed").agg(
            n=("covered", "size"),
            coverage=("covered", "mean"),
            width=("width", "mean"),
            interval_score=("interval_score", "mean"),
        )
        summary_rows.append(
            {
                "method": method,
                "construction": construction,
                "draws": draws,
                "n_archives": int(block[["station_key", "replicate"]].drop_duplicates().shape[0]),
                "coverage_mean": float(per_seed.coverage.mean()),
                "coverage_min": float(per_seed.coverage.min()),
                "coverage_max": float(per_seed.coverage.max()),
                "width_mean": float(per_seed.width.mean()),
                "width_min": float(per_seed.width.min()),
                "width_max": float(per_seed.width.max()),
                "interval_score_mean": float(per_seed.interval_score.mean()),
                "interval_score_min": float(per_seed.interval_score.min()),
                "interval_score_max": float(per_seed.interval_score.max()),
            }
        )
    for method in ["D2", "stochastic_cal"]:
        for draws in DRAWS:
            for seed in SEEDS:
                block = cases.loc[
                    cases.method.eq(method)
                    & cases.draws.eq(draws)
                    & cases.seed.eq(seed)
                ]
                pivot = block.pivot_table(
                    index=["station_key", "replicate"],
                    columns="construction",
                    values=["covered", "width", "interval_score"],
                )
                for construction in ["shared_parameters", "residual_blocks"]:
                    for metric in ["covered", "width", "interval_score"]:
                        left = pivot[(metric, construction)]
                        right = pivot[(metric, "independent")]
                        common = pd.concat([left, right], axis=1).dropna()
                        if common.empty:
                            continue
                        difference = (
                            common.iloc[:, 0] - common.iloc[:, 1]
                        ).rename("difference")
                        frame = difference.reset_index()
                        frame["independence_group"] = frame.station_key.map(
                            cases.drop_duplicates("station_key").set_index("station_key").independence_group
                        )
                        low, high = group_bootstrap(frame, "difference")
                        contrast_rows.append(
                            {
                                "method": method,
                                "draws": draws,
                                "seed": seed,
                                "construction": construction,
                                "metric": metric,
                                "difference": float(difference.mean()),
                                "bootstrap_low": low,
                                "bootstrap_high": high,
                                "n_archives": len(common),
                            }
                        )
    summary = pd.DataFrame(summary_rows)
    contrasts = pd.DataFrame(contrast_rows)
    checks = []
    for (method, construction), block in summary.groupby(["method", "construction"]):
        row = {"method": method, "construction": construction}
        available = sorted(int(value) for value in block.draws.unique())
        comparisons = [
            (lower, upper)
            for lower, upper in zip(available[:-1], available[1:])
        ]
        convergence_comparisons = (
            [(available[-2], available[-1])] if len(available) >= 2 else []
        )
        for lower, upper in comparisons:
            a = block.loc[block.draws.eq(lower)].iloc[0]
            b = block.loc[block.draws.eq(upper)].iloc[0]
            row[f"coverage_change_{lower}_{upper}_pp"] = 100 * (b.coverage_mean - a.coverage_mean)
            row[f"width_relative_change_{lower}_{upper}"] = (b.width_mean - a.width_mean) / a.width_mean
            row[f"score_relative_change_{lower}_{upper}"] = (
                b.interval_score_mean - a.interval_score_mean
            ) / a.interval_score_mean
        converges = bool(convergence_comparisons)
        for lower, upper in convergence_comparisons:
            if abs(row[f"coverage_change_{lower}_{upper}_pp"]) > 0.3:
                converges = False
            if abs(row[f"width_relative_change_{lower}_{upper}"]) > 0.01:
                converges = False
            if abs(row[f"score_relative_change_{lower}_{upper}"]) > 0.01:
                converges = False
        row["meets_numerical_stability_rule"] = converges
        row["stability_pair"] = (
            f"{convergence_comparisons[0][0]}-{convergence_comparisons[0][1]}"
            if convergence_comparisons
            else ""
        )
        checks.append(row)
    summary = summary.merge(
        pd.DataFrame(checks), on=["method", "construction"], how="left"
    )
    report = {
        "scope": "post-hoc numerical sensitivity on saved crossed forward controlled gaps",
        "draws": DRAWS,
        "seeds": SEEDS,
        "constructions": CONSTRUCTIONS,
        "fixed": "annual quantiles, observed bounds, evaluation years and point estimates",
        "convergence_rule": "coverage change <= 0.3 percentage points and width/score relative change <= 1% between 1024 and 4096; 256 is reported as the original small-sample sensitivity",
        "checks": checks,
        "limits": [
            "same opened data, not independent validation",
            "seed range is not a confidence interval",
            "rank couplings are dependence sensitivities, not posterior samples",
            "the rank sequence is generated at the largest draw count and truncated for smaller counts; annual marginals are regenerated separately for each draw count",
        ],
    }
    return summary, contrasts, report


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if "--summarize-only" in sys.argv:
        cases = pd.read_csv(OUT / "rank_convergence_cases.csv.gz")
        summary, contrasts, report = summarize(cases)
        summary.to_csv(OUT / "rank_convergence_summary.csv", index=False)
        contrasts.to_csv(OUT / "rank_convergence_contrasts.csv", index=False)
        (OUT / "rank_convergence_report.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        print(summary.to_string(index=False), flush=True)
        print(pd.DataFrame(report["checks"]).to_string(index=False), flush=True)
        return 0
    core = T.load_script(
        "rank_convergence_cases", T.ROOT / "scripts/431_tr_cases.py"
    )
    reference = reference_table()
    jobs = {
        job["station_key"]: job
        for job in core.jobs_for("source")
        if job["station_key"] in set(reference.station_key)
    }
    tasks = []
    for station, job in sorted(jobs.items()):
        replicates = sorted(
            int(path.parent.parent.name.removeprefix("replicate_"))
            for path in (BASE / "crossed" / "forward").glob(
                f"replicate_*/*/annual_predictions.parquet"
            )
            if path.parent.name == station.replace("|", "_")
        )
        if replicates:
            tasks.append((job, replicates))
    rows = Parallel(n_jobs=8, verbose=10)(
        delayed(process_station)(job, replicates, reference)
        for job, replicates in tasks
    )
    cases = pd.DataFrame([row for block in rows for row in block])
    cases.to_csv(OUT / "rank_convergence_cases.csv.gz", index=False, compression="gzip")
    summary, contrasts, report = summarize(cases)
    summary.to_csv(OUT / "rank_convergence_summary.csv", index=False)
    contrasts.to_csv(OUT / "rank_convergence_contrasts.csv", index=False)
    (OUT / "rank_convergence_report.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(summary.to_string(index=False), flush=True)
    print(pd.DataFrame(report["checks"]).to_string(index=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
