#!/usr/bin/env python3
"""Calibrate finite-record slope errors on source groups and score held regions.

The target test groups are excluded from source models. In partitioned forward
models, training-only groups from the named target region may remain; audit the
source role assignment before claiming full regional exclusion. Trend
calibration uses only the annual model's unused rule groups,
re-predicting their jointly masked archives with that same held-region model.
The empirical equal-group 95% error quantile is a practical comparator; small
calibration pools do not acquire a finite-sample coverage guarantee.
"""

from __future__ import annotations
import os

for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"

import argparse
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd

import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.archive import (
    LEVELS,
    marginal_draws,
    reorder_marginals,
    slope,
    task_calibration_support,
)
from stream_recoverability.experiments.tr_revision.statistics import interval_score
from stream_recoverability.seeds import plain_seed

SOURCE = T.ROOT / "results/wrr_review_completion_20261024"
OUT = T.ROOT / "results/whole_archive"


def uncertainty_diagnostics(cases, truth, points, output):
    """Evaluation-only error geometry and paired sensitivity to quantile tails."""
    errors, tail_rows = [], []
    grouped = cases.groupby(["_family", "_mode", "station_key"])
    for number, ((family, mode, station), group) in enumerate(grouped):
        if mode == "calibration":
            continue
        reference = truth[family, station]
        if mode == "forward":
            reference = reference.loc[reference.index >= 2010]
        years = reference.index.to_numpy()
        values = reference.to_numpy()
        x = (years - years.mean()) / 10
        weights = x / (x @ x)
        expected = float(slope(years, values))
        for estimator, point, prefix in [
            ("D2", "D2", "D2"),
            ("stochastic_calibrated", "stochastic_cal_q50", "stochastic_cal"),
        ]:
            current = points.loc[
                points.family.eq(family)
                & points["mode"].eq(mode)
                & points.station_key.eq(station)
                & points.estimator.eq(estimator)
                & points.available
            ]
            replicas = sorted(current.replicate.unique())
            positions_by_replica = {replica: i for i, replica in enumerate(replicas)}
            error_matrix = np.zeros((len(replicas), len(years)))
            level_components, levels = np.zeros(len(replicas)), []
            for replica, block in group.groupby("_replicate"):
                if replica not in positions_by_replica:
                    continue
                positions = reference.index.get_indexer(block.year)
                residual = block[point].to_numpy() - values[positions]
                error_matrix[positions_by_replica[replica], positions] = residual
                levels.append(float(residual.mean()))
                level_components[positions_by_replica[replica]] = float(
                    weights[positions].sum() * residual.mean()
                )
                q = np.repeat(values[:, None], len(LEVELS), axis=1)
                q[positions] = block[
                    [f"{prefix}_q{int(100 * level):02d}" for level in LEVELS]
                ].to_numpy(float)
                if not np.isfinite(q).all():
                    continue
                ranks = np.random.default_rng(
                    plain_seed(525, number, int(replica))
                ).normal(size=(256, len(years)))
                bounds = np.repeat(np.nan, len(years))
                bounds[positions] = block.observed_lower_bound__observed_days.to_numpy(float)
                for tails in ["constant", "normal"]:
                    draws = reorder_marginals(
                        marginal_draws(q, tails=tails, lower_bounds=bounds), ranks
                    )
                    low, high = np.quantile(slope(years, draws), [0.025, 0.975])
                    tail_rows.append(
                        dict(
                            family=family,
                            mode=mode,
                            station_key=station,
                            replicate=int(replica),
                            estimator=estimator,
                            tails=tails,
                            coverage95=bool(low - 1e-12 <= expected <= high + 1e-12),
                            width95=high - low,
                            interval_score95=float(
                                interval_score(low, high, expected, alpha=0.05)
                            ),
                        )
                    )
            if len(replicas) < 2:
                continue
            slope_errors = error_matrix @ weights
            variance = float(slope_errors.var(ddof=1))
            diagonal = float(np.sum(weights**2 * error_matrix.var(axis=0, ddof=1)))
            bias = float(slope_errors.mean())
            component = float(np.mean(level_components))
            errors.append(
                dict(
                    family=family,
                    mode=mode,
                    station_key=station,
                    estimator=estimator,
                    n_mask_repetitions=len(replicas),
                    slope_bias=bias,
                    squared_bias=bias**2,
                    slope_error_variance=variance,
                    diagonal_error_variance=diagonal,
                    covariance_contribution=variance - diagonal,
                    mean_missing_year_bias=float(np.mean(levels)),
                    level_bias_slope_component=component,
                    remaining_slope_bias=bias - component,
                )
            )
    errors = pd.DataFrame(errors)
    errors.to_csv(output / "evaluation_error_structure.csv", index=False)
    errors.groupby(["family", "mode", "estimator"]).mean(
        numeric_only=True
    ).reset_index().to_csv(output / "evaluation_error_summary.csv", index=False)
    tails = pd.DataFrame(tail_rows)
    tails.to_csv(output / "quantile_tail_sensitivity.csv", index=False)
    tails.groupby(["family", "mode", "estimator", "tails"]).agg(
        n=("coverage95", "size"),
        coverage95=("coverage95", "mean"),
        width95=("width95", "mean"),
        interval_score95=("interval_score95", "mean"),
    ).reset_index().to_csv(output / "quantile_tail_summary.csv", index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--min-source-groups", type=int, default=3)
    args = parser.parse_args()
    output = args.output
    trends = pd.read_csv(output / "trends.csv")
    calibrations = json.loads((output / "classical_calibration.json").read_text())
    inference = T.load_script(
        "task_calibration_inference",
        T.ROOT / "scripts/495_review_completion_independent_analysis.py",
    )
    reference = pd.read_parquet(
        SOURCE / "cases/leave_one_year_out/seed_00.parquet",
        columns=["station_key", "year", "design_family", "eval_truth_h30"],
    )
    truth = {
        (family, station): group.drop_duplicates("year")
        .set_index("year")
        .eval_truth_h30.sort_index()
        for (family, station), group in reference.groupby(
            ["design_family", "station_key"]
        )
    }
    parts = []
    for path in sorted(
        p
        for family in ["calendar", "crossed"]
        for p in (output / family).glob("*/replicate_*/*/annual_predictions.parquet")
    ):
        c = pd.read_parquet(path)
        if c.empty:
            continue
        c["_family"] = path.parents[3].name
        c["_mode"] = path.parents[2].name
        c["_replicate"] = int(path.parents[1].name.removeprefix("replicate_"))
        parts.append(c)
    cases = pd.concat(parts, ignore_index=True)
    results, plans, errors = [], [], []
    base = trends.loc[trends.dependence.eq("independent") & trends.retention.eq("all")]
    for (family, mode, region), evaluation in base.groupby(
        ["family", "mode", "region"]
    ):
        split = "before_2010" if mode == "forward" else "leave_one_year_out"
        bundle = joblib.load(SOURCE / "refits" / split / "seed_00" / f"{region}.joblib")
        if "D2_offsets" in calibrations[mode][region]:
            bundle["offsets"] = calibrations[mode][region]["D2_offsets"]
        groups = bundle["roles"]["rule_calibration"]
        calibration_mode = "calibration" if mode == "forward" else "offline"
        source = cases.loc[
            cases._family.eq(family)
            & cases._mode.eq(calibration_mode)
            & cases.independence_group.isin(groups)
        ].copy()
        if source.empty:
            plans.append(
                dict(
                    family=family,
                    mode=mode,
                    region=region,
                    n_source_groups=0,
                    status="unavailable",
                )
            )
            continue
        source = inference.classical_predictions(
            inference.predict(source, bundle), calibrations[mode][region]
        )
        records = []
        for number, ((station, replicate), block) in enumerate(
            source.groupby(["station_key", "_replicate"])
        ):
            reference_years = truth[family, station]
            if mode == "forward":
                reference_years = reference_years.loc[reference_years.index < 2010]
            years = reference_years.index.to_numpy()
            values = reference_years.to_numpy()
            expected = float(slope(years, values))
            for estimator, column, prefix in [
                ("D2", "D2", "D2"),
                ("stochastic_calibrated", "stochastic_cal_q50", "stochastic_cal"),
            ]:
                restored = reference_years.copy()
                restored.loc[block.year.to_numpy()] = block[column].to_numpy()
                if restored.isna().any():
                    continue
                error = float(slope(years, restored.to_numpy()) - expected)
                quantiles = np.repeat(values[:, None], len(LEVELS), axis=1)
                positions = reference_years.index.get_indexer(block.year)
                quantiles[positions] = block[
                    [f"{prefix}_q{int(100 * q):02d}" for q in LEVELS]
                ].to_numpy(float)
                if not np.isfinite(quantiles).all():
                    continue
                bounds = np.repeat(np.nan, len(years))
                bounds[positions] = block.observed_lower_bound__observed_days.to_numpy(float)
                samples = marginal_draws(quantiles, lower_bounds=bounds)
                ranks = np.random.default_rng(
                    plain_seed(523, number, int(replicate))
                ).normal(size=samples.shape)
                low, high = np.quantile(
                    slope(years, reorder_marginals(samples, ranks)), [0.025, 0.975]
                )
                scale = float((high - low) / 2)
                records.append(
                    dict(
                        station_key=station,
                        independence_group=block.independence_group.iloc[0],
                        replicate=int(replicate),
                        estimator=estimator,
                        error=error / scale if scale > 1e-8 else np.nan,
                        raw_error=error,
                        reference_half_width=scale,
                        last_calibration_year=int(years.max()),
                    )
                )
        records = pd.DataFrame(records)
        if records.empty:
            continue
        for estimator, all_pool in records.groupby("estimator"):
            # An exact or nearly exact source interval cannot identify a relative
            # calibration factor for uncertain target archives. Keep these rows
            # in diagnostics but do not turn an arbitrary epsilon into evidence.
            support, pool = task_calibration_support(all_pool, args.min_source_groups)
            plan = dict(
                family=family,
                mode=mode,
                region=region,
                estimator=estimator,
                n_source_groups=support["n_source_groups"],
                n_source_stations=pool.station_key.nunique(),
                n_source_station_repetitions=support["n_source_station_repetitions"],
                n_degenerate_source_repetitions=support["n_degenerate_source_repetitions"],
                source_groups=";".join(sorted(pool.independence_group.unique())),
                annual_fit_and_interval_groups_excluded=not bool(set(source.independence_group) & (set(bundle["roles"]["estimator"]) | set(bundle["roles"]["interval_calibration"]))),
                held_region_excluded=not bool(source.region.eq(region).any()),
                last_calibration_year=int(all_pool.last_calibration_year.max()),
            )
            if support["status"] != "supported":
                plans.append(plan | support)
                errors.append(all_pool.assign(family=family, mode=mode, held_region=region))
                continue
            # The forecast uncertainty itself is observable at decision time.
            # Refuse extrapolation beyond a source-only empirical support range.
            radius = support["scale_factor"]
            low_scale = support["minimum_supported_half_width"]
            high_scale = support["maximum_supported_half_width"]
            plan |= support
            plans.append(plan)
            errors.append(all_pool.assign(family=family, mode=mode, held_region=region))
            target = evaluation.loc[
                evaluation.estimator.eq(estimator) & evaluation.available
            ].copy()
            target_half_width = (target.upper95 - target.lower95) / 2
            target = target.loc[target_half_width.between(low_scale, high_scale)].copy()
            target["dependence"] = "task_calibrated"
            half_width = radius * (target.upper95 - target.lower95) / 2
            target["lower95"] = target.slope - half_width
            target["upper95"] = target.slope + half_width
            target["width95"] = 2 * half_width
            target["missing_coverage95"] = target.error.abs().le(half_width + 1e-12)
            target["interval_score95"] = interval_score(
                target.lower95, target.upper95, target.truth_slope, alpha=0.05
            )
            target["n_source_groups"] = plan["n_source_groups"]
            results.append(target)
        print(
            f"{family}/{mode}/{region}: {records.independence_group.nunique()} source calibration groups",
            flush=True,
        )
    calibrated = pd.concat(results, ignore_index=True) if results else base.iloc[:0].copy()
    calibrated.to_csv(output / "task_calibrated_trends.csv", index=False)
    pd.DataFrame(plans).to_csv(output / "task_calibration_sources.csv", index=False)
    (pd.concat(errors, ignore_index=True) if errors else pd.DataFrame()).to_csv(
        output / "task_calibration_errors.csv", index=False
    )
    summary = (
        calibrated.groupby(["family", "mode", "estimator"])
        .agg(
            n=("error", "size"),
            missing_coverage95=("missing_coverage95", "mean"),
            width95=("width95", "mean"),
            interval_score95=("interval_score95", "mean"),
            minimum_source_groups=("n_source_groups", "min"),
        )
        .reset_index()
    )
    denominators = (
        base.groupby(["family", "mode", "estimator"])
        .size()
        .rename("n_eligible")
        .reset_index()
    )
    summary = summary.merge(denominators, on=["family", "mode", "estimator"])
    summary["availability"] = summary.n / summary.n_eligible
    summary.to_csv(output / "task_calibration_summary.csv", index=False)
    keys = ["family", "mode", "region", "station_key", "replicate", "estimator"]
    paired_intervals = calibrated.merge(
        base[keys + ["missing_coverage95", "width95", "interval_score95"]],
        on=keys,
        suffixes=("_task", "_independent"),
    )
    paired_summary = (
        paired_intervals.groupby(["family", "mode", "estimator"])
        .agg(
            n_common=("replicate", "size"),
            task_coverage95=("missing_coverage95_task", "mean"),
            independent_coverage95=("missing_coverage95_independent", "mean"),
            task_width95=("width95_task", "mean"),
            independent_width95=("width95_independent", "mean"),
            task_interval_score95=("interval_score95_task", "mean"),
            independent_interval_score95=("interval_score95_independent", "mean"),
        )
        .reset_index()
    )
    paired_summary["width_ratio"] = (
        paired_summary.task_width95 / paired_summary.independent_width95
    )
    paired_summary.to_csv(output / "paired_task_intervals.csv", index=False)
    # Every comparison uses the exact same station/repetition rows.
    points = trends.loc[trends.dependence.eq("point") & trends.retention.eq("all")]
    pivot = points.pivot(
        index=["family", "mode", "station_key", "replicate"],
        columns="estimator",
        values="squared_error",
    )
    paired = []
    for (family, mode), block in pivot.groupby(level=["family", "mode"]):
        for left, right in [
            ("D2", "stochastic_calibrated"),
            ("D2", "plug_in"),
            ("plug_in", "precomputed_plugin"),
        ]:
            if left not in block or right not in block:
                continue
            common = block[[left, right]].dropna()
            paired.append(
                dict(
                    family=family,
                    mode=mode,
                    left=left,
                    right=right,
                    n_common=len(common),
                    left_rmse=float(np.sqrt(common[left].mean())),
                    right_rmse=float(np.sqrt(common[right].mean())),
                    paired_mse_difference=float((common[left] - common[right]).mean()),
                )
            )
    pd.DataFrame(paired).to_csv(output / "paired_trend_estimators.csv", index=False)
    # Store annual proper availability and common-case error comparisons.
    annual_pairs = []
    for (family, mode), block in cases.groupby(["_family", "_mode"]):
        if mode == "calibration":
            continue
        observed = np.array(
            [truth[family, row.station_key].loc[row.year] for row in block.itertuples()]
        )
        common = (
            block.D2.notna()
            & block.stochastic_cal_q50.notna()
            & block.h30__policy.notna()
        )
        for estimator, column in [
            ("D2", "D2"),
            ("stochastic_calibrated", "stochastic_cal_q50"),
            ("plug_in", "h30__policy"),
        ]:
            error = block.loc[common, column].to_numpy() - observed[common]
            annual_pairs.append(
                dict(
                    family=family,
                    mode=mode,
                    estimator=estimator,
                    n_common=int(common.sum()),
                    mae=float(np.mean(abs(error))),
                    bias=float(np.mean(error)),
                )
            )
    pd.DataFrame(annual_pairs).to_csv(
        output / "paired_annual_estimators.csv", index=False
    )
    uncertainty_diagnostics(cases, truth, points, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
