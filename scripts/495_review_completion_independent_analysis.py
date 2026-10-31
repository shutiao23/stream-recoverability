#!/usr/bin/env python3
"""Apply source annual models and score all quality-qualified target cases."""

from __future__ import annotations
import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"
import argparse
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T
import wrr_tr_features as F
from stream_recoverability.experiments.tr_revision.independent import (
    evaluate_endpoints,
    load_acquisition_plan,
)
from stream_recoverability.experiments.tr_revision.archive import apply_observed_lower_bound

STUDY = T.ROOT / "results/wrr_review_completion_20261024/independent_study"


def predict(c, bundle):
    if c.empty:
        return c.assign(
            **{
                name: np.nan
                for name in [
                    "D2",
                    "risk_score",
                    *[f"D2_q{int(100 * level):02d}" for level in F.QUANTILES],
                ]
            }
        )
    x = F.design_matrix(c, simulation=True).reindex(columns=bundle["features"])
    point = c.h30__policy.to_numpy(float)
    q = np.sort(
        np.column_stack([m.predict(x) for m in bundle["quantile_models"]])
        + point[:, None],
        axis=1,
    )
    if "observed_lower_bound__observed_days" in c:
        q = apply_observed_lower_bound(q, c.observed_lower_bound__observed_days)
    overlap = c.peak_overlap.to_numpy()
    bins = np.where(
        overlap <= 0, 0, np.searchsorted([0, 0.25, 0.5, 0.75, 1], overlap, side="left")
    )
    layers = c.policy_choice.where(
        c.policy_choice.isin(["air_ridge", "donor_ridge"]), "other"
    )
    difficulty = pd.Series(
        [f"{i}|{layer}" for i, layer in zip(bins, layers)], index=c.index
    )
    supported = np.isfinite(point) & c.policy_choice.ne("unavailable").to_numpy()
    for label in difficulty.unique():
        selected = difficulty.eq(label).to_numpy()
        if label not in bundle["offsets"]:
            supported[selected] = False
        else:
            q[selected] += bundle["offsets"][label]
    q = np.sort(q, axis=1)
    if "observed_lower_bound__observed_days" in c:
        q = apply_observed_lower_bound(q, c.observed_lower_bound__observed_days)
    classifier = bundle["classifier"]
    score = (
        classifier.predict_proba(x)[:, 1]
        if classifier is not None
        else np.full(len(c), bundle["constant_probability"])
    )
    out = c.copy()
    out["D2"] = q[:, 3]
    out["risk_score"] = score
    mean = bundle.get("mean_model")
    out["P2"] = (
        point
        + mean.predict(
            F.design_matrix(c, simulation=False).reindex(
                columns=bundle["plain_features"]
            )
        )
        if mean is not None
        else np.nan
    )
    if "observed_lower_bound__observed_days" in c:
        out["P2"] = apply_observed_lower_bound(
            out["P2"].to_numpy()[:, None], c.observed_lower_bound__observed_days
        )[:, 0]
    out["difficulty"] = difficulty
    for j, level in enumerate(F.QUANTILES):
        out[f"D2_q{int(100 * level):02d}"] = q[:, j]
    columns = [
        "D2",
        "risk_score",
        *[f"D2_q{int(100 * level):02d}" for level in F.QUANTILES],
    ]
    out.loc[~supported, columns] = np.nan
    out["prediction_supported"] = supported
    return out


def classical_predictions(c, calibration):
    out = c.copy()
    for prefix in ["stochastic", "state"]:
        names = [f"{prefix}_h30_q{int(100 * q):02d}" for q in F.QUANTILES]
        q = out.reindex(columns=names).to_numpy(float)
        if "observed_lower_bound__observed_days" in out:
            q = apply_observed_lower_bound(q, out.observed_lower_bound__observed_days)
        for cell in out.difficulty.unique():
            offsets = calibration["offsets"][prefix].get(
                cell, calibration["offsets"][prefix]["__pooled__"]
            )
            q[out.difficulty.eq(cell).to_numpy()] += np.asarray(offsets)
        q = np.sort(q, axis=1)
        if "observed_lower_bound__observed_days" in out:
            q = apply_observed_lower_bound(q, out.observed_lower_bound__observed_days)
        for j, level in enumerate(F.QUANTILES):
            out[f"{prefix}_cal_q{int(100 * level):02d}"] = q[:, j]
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", type=Path, default=STUDY)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    status_path = args.study / "public_registration_status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    plan = load_acquisition_plan(args.study)
    if args.check_only:
        print("Measurement plan loaded.")
        return 0
    if args.cases is None or args.output is None:
        parser.error("--cases and --output are required")
    model_path = (
        T.ROOT
        / "results/wrr_review_completion_20261024/deployment/global_source_candidate.joblib"
    )
    calibration_path = model_path.parent / "classical_calibration.json"
    c = pd.read_parquet(args.cases)
    result = predict(c, joblib.load(model_path))
    if len(result):
        result = classical_predictions(result, json.loads(calibration_path.read_text()))
        result["decision_hot"] = result.air_warm_z_mean.ge(
            plan["source_decision_hot_cutoff"]
        )
    endpoints, group_table = evaluate_endpoints(result)
    args.output.mkdir(parents=True, exist_ok=True)
    result.to_parquet(args.output / "predictions.parquet", index=False)
    group_table.to_csv(args.output / "group_risks.csv", index=False)
    if len(result):
        scoring = T.load_script(
            "registered_independent_fixed_scoring",
            T.ROOT / "scripts/467_review_completion_analysis.py",
        )
        for filename, table in zip(
            [
                "scorecard",
                "paired_effects",
                "events",
                "unit_effects",
                "distribution_pairs",
            ],
            scoring.scorecard(result, 0),
        ):
            table.to_csv(args.output / (filename + ".csv"), index=False)
    endpoints["E5"] = {
        "label_budget_groups": 10,
        "n_available_groups": int(result.independence_group.nunique()),
        "status": "not_implementable_fewer_than_11_groups"
        if result.independence_group.nunique() <= 10
        else "requires_separate_prespecified_small_label_curve",
        "guaranteed_retention": None,
    }
    T.write_json(args.output / "primary_endpoints.json", endpoints)
    T.write_json(
        args.output / "evaluation_receipt.json",
        {
            "registration_id": status.get("registration_id"),
            "annual_model_refitted_on_target": False,
            "failure_classifier_refitted_on_target": False,
            "primary_cutoff": 0.1,
            "local_daily_history_use": "Other-year target histories fit daily models/climatology by the source recipe; the evaluated whole year is excluded, including when later historical years are available",
            "scope": "Primary E1/E2 and descriptive E3/E4. E5 requires the separate small-label analysis; it is not produced by this entry point.",
        },
    )
    T.write_json(
        args.study / "independent_evaluation_status.json",
        {
            "registration_id": status.get("registration_id"),
            "output_directory": str(args.output.resolve()),
            "n_evaluable_controlled_cases": endpoints["n_eligible"],
            "joint_primary_passed": endpoints["joint_primary_passed"],
            "source_model_refitted_on_target": False,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
