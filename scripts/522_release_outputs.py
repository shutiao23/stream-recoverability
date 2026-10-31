#!/usr/bin/env python3
"""Evaluate three outputs using existing clean and failure-scenario experiments.

Thresholds use visible features from the source estimator groups. Neither
hidden temperatures nor the intervention flag enter the output decision.
The 0.05 C water/air agreement diagnostic is specific to the existing synthetic
exposure scenario and is not presented as a general sensor-quality detector.
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
from joblib import Parallel, delayed

import wrr_tr_common as T
from stream_recoverability.experiments.development_recovery import (
    read_temperature_panel,
)
from stream_recoverability.experiments.v19_revision.data import station_air_series
from stream_recoverability.experiments.tr_revision.outputs import (
    water_air_agreement,
    release_states,
)
from stream_recoverability.experiments.tr_revision.simulation import (
    visible_air_exposure,
)
from stream_recoverability.seeds import plain_seed

SOURCE = T.ROOT / "results/wrr_review_completion_20261024"
OUT = T.ROOT / "results/release_outputs"


def visible_quality(job, block, exposed):
    panel = read_temperature_panel(job["input_path"]).asfreq("D")
    panel.columns = panel.columns.astype(str)
    air = station_air_series(
        Path(job["air_input_path"]), job["network_id"], job["station_id"], panel.index
    )
    shift = T.hemisphere_shift_days(job.get("latitude"))
    panel.index += pd.Timedelta(days=shift)
    if air is not None:
        air.index = panel.index
    result = []
    for year, cases in block.groupby("year", sort=False):
        index = panel.index[panel.index.year == year]
        water = panel.loc[index, job["station_id"]].to_numpy(float)
        weather = (
            air.reindex(index).to_numpy(float)
            if air is not None
            else np.full(len(index), np.nan)
        )
        for local_position, (position, row) in enumerate(cases.iterrows()):
            observed = water.copy()
            for run in row.mask_runs.split(";"):
                start, length = map(int, run.split(":"))
                observed[start : start + length] = np.nan
            if exposed:
                warm = index.month.isin([int(m) for m in row.warm_months.split(";")])
                observed, _ = visible_air_exposure(
                    observed,
                    weather,
                    warm,
                    days=7,
                    top_fraction=0.1,
                    seed=plain_seed(
                        8, 0, job["station_index"], int(year), local_position
                    ),
                )
            result.append((position, water_air_agreement(observed, weather)))
    return (
        pd.DataFrame(result, columns=["position", "agreement7"])
        .set_index("position")
        .agreement7
    )


def main():
    global OUT
    p = argparse.ArgumentParser()
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--output", type=Path, default=OUT)
    p.add_argument("--reuse-quality", type=Path,
                   help="Reuse previously computed visible-only quality diagnostics")
    args = p.parse_args()
    OUT = args.output
    OUT.mkdir(parents=True, exist_ok=True)
    core = T.load_script("release_case_roster", T.ROOT / "scripts/431_tr_cases.py")
    refit = T.load_script(
        "release_source_roles", T.ROOT / "scripts/466_review_completion_refit.py"
    )
    inference = T.load_script(
        "release_source_inference",
        T.ROOT / "scripts/495_review_completion_independent_analysis.py",
    )
    jobs = {(j["network_id"], j["station_key"]): j for j in core.jobs_for("source")}
    limits = {}
    for source_split in ["leave_one_year_out", "before_2010", "cold_to_hot", "non_air_refit"]:
        source = pd.read_parquet(SOURCE / "cases" / source_split / "seed_00.parquet")
        source = source.loc[
            source.policy_choice.ne("unavailable") & source.eval_truth_h30.notna()
        ].reset_index(drop=True)
        limits[source_split] = {}
        for i, region in enumerate(sorted(source.region.unique())):
            _, _, weights = refit.roles(source, region, plain_seed(7, 0, i))
            learning = source.loc[weights["estimator"] > 0]
            limits[source_split][region] = {
                column: float(learning[column].abs().quantile(0.99))
                for column in ["visible_edge_anomaly", "air_gap_z_mean"]
            }
    T.write_json(
        OUT / "design.json",
        {
            "feature_quantile": 0.99,
            "limits_by_training_split_and_held_region": limits,
            "air_agreement_threshold_c": 0.05,
            "quality_window_days": 7,
            "scope": "one source model seed; split-specific source-only thresholds; raw classifier score trained on the original D2, without a group-risk guarantee",
            "projection": "D2 point is constrained to each case's observed 30-day lower bound; stress refits retain their historical quantile offsets",
            "bound_assumption": "reported water observations are comparable and valid; flagged possible exposure gives unknown, not a bound",
            "stress_prevalence": "unknown; mixture rates are scenarios, not estimates",
        },
    )
    records, states, events = [], [], []
    for condition, split in [
        ("clean", "leave_one_year_out"),
        ("air_exposure", "air_exposure"),
        ("hot_year_extrapolation", "cold_to_hot"),
        ("future_years", "before_2010"),
        ("smooth_non_air_shift", "non_air_refit"),
    ]:
        if condition in ["clean", "air_exposure"]:
            c = pd.read_parquet(SOURCE / "cases" / split / "seed_00.parquet")
            if condition == "clean":
                c["eval_air_exposure_days"] = 0
            if args.reuse_quality:
                keys = ["network_id", "station_key", "year", "design_family", "realization_id"]
                quality = pd.read_parquet(args.reuse_quality / (condition + ".parquet"), columns=keys + ["agreement7"])
                if quality.duplicated(keys).any() or c.duplicated(keys).any():
                    raise ValueError("Visible-quality cache has nonunique case identities")
                previous = pd.MultiIndex.from_frame(quality[keys])
                current = pd.MultiIndex.from_frame(c[keys])
                if not current.isin(previous).all():
                    raise ValueError("Visible-quality cache does not cover the requested cases")
                c["agreement7"] = pd.Series(quality.agreement7.to_numpy(), index=previous).reindex(current).to_numpy()
            else:
                quality = Parallel(n_jobs=args.workers)(
                    delayed(visible_quality)(jobs[key], block, condition == "air_exposure")
                    for key, block in c.groupby(["network_id", "station_key"], sort=False)
                )
                c["agreement7"] = pd.concat(quality).reindex(c.index)
            parts = []
            for region, block in c.groupby("region"):
                parts.append(
                    inference.predict(
                        block,
                        joblib.load(
                            SOURCE
                            / "refits/leave_one_year_out/seed_00"
                            / f"{region}.joblib"
                        ),
                    )
                )
            c = pd.concat(parts).sort_index()
        else:
            c = pd.concat(
                [
                    pd.read_parquet(path)
                    for path in sorted(
                        (SOURCE / "refits" / split / "seed_00").glob("*.parquet")
                    )
                ],
                ignore_index=True,
            )
            # These scenarios do not inject sensor exposure. Only distribution diagnostics apply.
            c["agreement7"] = np.nan
            # These precomputed stress predictions retain their historical
            # offsets. Project the delivered point without relabeling its score.
            bound = c.observed_lower_bound__observed_days.to_numpy(float)
            point = c.D2.to_numpy(float)
            c["D2"] = np.where(np.isfinite(bound), np.maximum(point, bound), point)
        if "training_partition" in c:
            c = c.loc[c.training_partition.eq("test")].copy()
        outputs = pd.Series("unknown", index=c.index)
        for region, block in c.groupby("region"):
            outputs.loc[block.index] = release_states(
                block, limits["leave_one_year_out" if condition == "air_exposure" else split][region], block.agreement7.le(0.05)
            )
        c["output"] = outputs
        c["quality_flag"] = c.agreement7.le(0.05)
        c["condition"] = condition
        columns = [
            "condition",
            "network_id",
            "station_key",
            "independence_group",
            "region",
            "year",
            "design_family",
            "realization_id",
            "output",
            "quality_flag",
            "agreement7",
            "D2",
            "risk_score",
            "eval_truth_h30",
            "h30__policy",
            "warm_observed_fraction",
            "observed_lower_bound__observed_days",
            "train_h30_q90",
        ]
        c[columns].to_parquet(OUT / (condition + ".parquet"), index=False)
        for family, block in c.groupby("design_family"):
            methods = {
                "estimate_all": block.D2.notna(),
                "warm90_plugin": block.warm_observed_fraction.ge(0.9)
                & block.h30__policy.notna(),
                "fixed_risk": block.risk_score.le(0.1) & block.D2.notna(),
                "three_outputs": block.output.eq("estimate"),
            }
            for method, keep in methods.items():
                point = block.h30__policy if method == "warm90_plugin" else block.D2
                error = (point - block.eval_truth_h30).abs()
                bad = error.gt(0.5)
                groups = (
                    block.loc[keep]
                    .assign(bad=bad.loc[keep])
                    .groupby("independence_group")
                    .bad.agg(["size", "mean"])
                )
                groups = groups.loc[groups["size"] >= 20]
                records.append(
                    {
                        "condition": condition,
                        "family": family,
                        "method": method,
                        "n_eligible": len(block),
                        "n_published": int(keep.sum()),
                        "retention": float(keep.mean()),
                        "n_bad": int((keep & bad).sum()),
                        "risk": float(bad[keep].mean()) if keep.any() else np.nan,
                        "mae": float(error[keep].mean()) if keep.any() else np.nan,
                        "n_evaluable_groups": len(groups),
                        "fraction_groups_above_10": float(groups["mean"].gt(0.1).mean())
                        if len(groups)
                        else np.nan,
                    }
                )
                actual_hot = block.eval_truth_h30.gt(block.train_h30_q90)
                declared_hot = keep & point.gt(block.train_h30_q90)
                if method == "three_outputs":
                    declared_hot |= block.output.eq(
                        "observed_bound"
                    ) & block.observed_lower_bound__observed_days.gt(
                        block.train_h30_q90
                    )
                events.append(
                    {
                        "condition": condition,
                        "family": family,
                        "method": method,
                        "n_true_hot": int(actual_hot.sum()),
                        "n_declared_hot": int(declared_hot.sum()),
                        "n_hot_detected": int((actual_hot & declared_hot).sum()),
                        "n_hot_missed_or_withheld": int(
                            (actual_hot & ~declared_hot).sum()
                        ),
                        "n_false_hot": int((~actual_hot & declared_hot).sum()),
                        "hot_recall": float(declared_hot[actual_hot].mean())
                        if actual_hot.any()
                        else np.nan,
                    }
                )
            lower = block.observed_lower_bound__observed_days
            hidden_truth = block.eval_truth_h30
            states.append(
                {
                    "condition": condition,
                    "family": family,
                    "n_eligible": len(block),
                    "estimate_fraction": float(block.output.eq("estimate").mean()),
                    "bound_fraction": float(block.output.eq("observed_bound").mean()),
                    "unknown_fraction": float(block.output.eq("unknown").mean()),
                    "quality_flag_fraction": float(block.quality_flag.mean()),
                    "false_bound_fraction_among_bounds": float(
                        (
                            lower[block.output.eq("observed_bound")]
                            > hidden_truth[block.output.eq("observed_bound")] + 1e-8
                        ).mean()
                    ),
                    "observed_hot_information_fraction": float(
                        (lower > block.train_h30_q90).mean()
                    ),
                    "retained_hot_information_fraction": float(
                        (
                            (lower > block.train_h30_q90) & block.output.ne("unknown")
                        ).mean()
                    ),
                }
            )
        print(f"{condition}: {len(c)} cases", flush=True)
    pd.DataFrame(records).to_csv(OUT / "release_metrics.csv", index=False)
    pd.DataFrame(states).to_csv(OUT / "output_states.csv", index=False)
    pd.DataFrame(events).to_csv(OUT / "hot_event_metrics.csv", index=False)
    metrics = pd.DataFrame(records).set_index(["condition", "family", "method"])
    mixture = []
    for family in ["calendar", "crossed"]:
        for method in ["estimate_all", "warm90_plugin", "fixed_risk", "three_outputs"]:
            clean, exposed = (
                metrics.loc[("clean", family, method)],
                metrics.loc[("air_exposure", family, method)],
            )
            for prevalence in [0, 0.01, 0.05, 0.1, 0.25, 0.5, 1]:
                retention = (
                    1 - prevalence
                ) * clean.retention + prevalence * exposed.retention
                failures = (
                    (1 - prevalence) * clean.n_bad / clean.n_eligible
                    + prevalence * exposed.n_bad / exposed.n_eligible
                )
                mixture.append(
                    dict(
                        family=family,
                        method=method,
                        exposure_fraction=prevalence,
                        retention=retention,
                        failure_per_eligible=failures,
                        risk=failures / retention if retention else np.nan,
                    )
                )
    pd.DataFrame(mixture).to_csv(OUT / "exposure_mixtures.csv", index=False)
    T.write_json(
        OUT / "status.json",
        {
            "complete": True,
            "conditions": sorted(metrics.index.get_level_values(0).unique()),
            "limitations": [
                "synthetic exact air substitution is easier to detect than general sensor contamination",
                "a bound requires valid measurements",
                "output rules have no population-wide risk guarantee",
            ],
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
