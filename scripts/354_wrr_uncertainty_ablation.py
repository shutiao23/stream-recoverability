#!/usr/bin/env python3
"""Evaluate matched-information screens with disjoint fitting and calibration groups."""

from __future__ import annotations

import os

for thread_variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[thread_variable] = "1"

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_r3_common as C

from stream_recoverability.experiments.v17_fitness.paths import stable_seed
from stream_recoverability.experiments.v19_revision.learning import empirical_threshold, fit_score, group_roles, predict_score, specifications
from stream_recoverability.experiments.v19_revision import learning, risk
from stream_recoverability.experiments.v19_revision.risk import fixed_training_candidates, select_group_threshold

OUT = C.RUN / "r3_04_uncertainty_ablation"
SPECS = specifications()
RULES = {"length_rule": "longest_run", "peak_overlap_rule": "peak_overlap", "warm_coverage_rule": "warm_observed_fraction", "probabilistic_support_rule": "probabilistic_hidden_support", "upper_support_rule": "hidden_support_upper90", "direct_h30_uncertainty": "direct_h30_uncertainty", "daily_disagreement_rule": "daily_estimator_disagreement", "target_disagreement_rule": "estimator_disagreement"}
RULES.update({"historical_h30_error_rule": "historical_mask_h30_abs90", "scaled_support_rule": "scaled_support_uncertainty", "oof_daily_sd_rule": "reconstructor_oof_daily_sd"})


def raw_rule(frame: pd.DataFrame, name: str) -> np.ndarray:
    values = pd.to_numeric(frame[RULES[name]], errors="coerce").to_numpy(dtype=float)
    if name == "warm_coverage_rule":
        values = -values
    valid = np.isfinite(values) & np.isfinite(frame.policy_metric.to_numpy(dtype=float))
    return np.where(valid, values, np.inf)


def run_score(path: str, destination: str, name: str, seed: int, settings: dict, measurement_scope: str = "documented_daily_mean") -> dict:
    output = Path(destination)
    completed = output / f"{name}_{seed}.npz"
    details = output / f"{name}_{seed}.json"
    input_hash = C.digest(Path(path))
    implementation_hash = C.digest(Path(__file__)) + C.digest(Path(learning.__file__)) + C.digest(Path(risk.__file__))
    if completed.exists() and details.exists():
        stored = json.loads(details.read_text())
        if stored["input_sha256"] == input_hash and stored.get("implementation_hash") == implementation_hash:
            return stored
    feature_names, kind = SPECS.get(name, ((), "rule"))
    columns = list(dict.fromkeys(["network_id", "station_id", "year", "realization_id", "statistic_class", "independence_group", "policy_metric", "abserr_policy", "policy_bad", *feature_names, *([RULES[name]] if name in RULES else [])]))
    if kind in {"certificate", "policy_certificate"}:
        columns += ["truth_hottest30", "longest_run_month", "policy_choice"] + [f"hottest30_{method}" for method in ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge")]
        columns = list(dict.fromkeys(columns))
    frame = pd.read_parquet(path, columns=columns)
    group_map = pd.read_csv(C.RUN / "r3_06_independence_risk/complete_network_independence.csv").set_index("network_id").independence_group
    frame["independence_group"] = frame.network_id.map(group_map)
    if frame.independence_group.isna().any():
        raise RuntimeError("A network has no complete target-and-donor independence group")
    if measurement_scope == "documented_daily_mean":
        frame = frame.loc[frame.statistic_class.isin(["daily_mean", "documented_daily_mean"])]
    case_rows = frame.index.to_numpy()
    groups = frame.independence_group.astype(str).to_numpy()
    score = np.full(len(frame), np.inf)
    admit_empirical = np.zeros(len(frame), dtype=bool)
    admit_certified = np.zeros(len(frame), dtype=bool)
    admit_fixed70 = np.zeros(len(frame), dtype=bool)
    fold_ids = np.full(len(frame), -1, dtype=int)
    folds = []
    for fold in range(5):
        roles = group_roles(groups, seed, fold)
        role = np.array([roles[group] for group in groups])
        train = frame.loc[role == "train"]
        calibration = frame.loc[role == "calibration"]
        test = frame.loc[role == "test"]
        if name in RULES:
            train_score, cal_score, test_score = (raw_rule(block, name) for block in (train, calibration, test))
        else:
            model = fit_score(train, feature_names, kind, seed=stable_seed("r3-model", name, seed, fold))
            train_score, cal_score, test_score = (predict_score(model, block, feature_names, kind) for block in (train, calibration, test))
            joblib.dump({"model": model, "features": feature_names, "kind": kind}, output / "models" / f"{name}_{seed}_{fold}.joblib", compress=3)
        candidates = fixed_training_candidates(train_score)
        empirical = empirical_threshold(cal_score, calibration.policy_bad.to_numpy(dtype=bool), calibration.independence_group.to_numpy(), candidates, seed=stable_seed("r3-calibration", name, seed, fold), risk_cap=settings["risk_cap"], alpha=settings["alpha"])
        formal = select_group_threshold(cal_score, calibration.policy_bad.to_numpy(dtype=bool), calibration.independence_group.to_numpy(), candidates, risk_cap=settings["risk_cap"], alpha=settings["alpha"])
        positions = np.flatnonzero(role == "test")
        score[positions] = test_score
        admit_empirical[positions] = test_score <= empirical["threshold"]
        admit_certified[positions] = test_score <= formal.threshold
        case_key = pd.util.hash_pandas_object(test[["network_id", "station_id", "year", "realization_id"]].astype(str), index=False).to_numpy()
        ranked = np.lexsort((case_key, test_score))
        retained = ranked[: int(np.floor(0.7 * len(test)))]
        finite = retained[np.isfinite(test_score[retained])]
        admit_fixed70[positions[finite]] = True
        fold_ids[positions] = fold
        folds.append({"fold": fold, "n_train_groups": train.independence_group.nunique(), "n_calibration_groups": calibration.independence_group.nunique(), "n_test_groups": test.independence_group.nunique(), "empirical_threshold": empirical["threshold"] if np.isfinite(empirical["threshold"]) else None, "empirical_status": empirical["status"], "formal_threshold": formal.threshold if np.isfinite(formal.threshold) else None, "formal_status": formal.status, "minimum_formal_loss_upper": float(formal.bounded_loss_upper.min()), "n_fixed_candidates": len(candidates)})
    if (fold_ids < 0).any():
        raise RuntimeError("An evaluation record was never held out")
    np.savez_compressed(completed, case_row=case_rows, score=score, admit_empirical=admit_empirical, admit_certified=admit_certified, admit_fixed70=admit_fixed70, fold=fold_ids)
    metadata = {"name": name, "fold_seed": seed, "features": list(feature_names), "kind": kind, "measurement_scope": measurement_scope, "input_sha256": input_hash, "script_sha256": C.digest(Path(__file__)), "implementation_hash": implementation_hash, "folds": folds, "calibration_protocol": "five outer folds; independent 60/20/20 fitting/calibration/testing; training-fixed candidate thresholds"}
    C.write_json(details, metadata)
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], default="leave_one_year_out")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--measurement-scope", choices=["documented_daily_mean", "all"], default="documented_daily_mean")
    parser.add_argument("--scores")
    parser.add_argument("--cohort", choices=["admission", "controlled"], default="admission")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    settings = C.protocol()
    source = C.source_cases(args.protocol, args.cohort)
    output = (C.ROOT / "scratch/wrr_revision_20261020c/ablation_smoke" if args.smoke else OUT) / args.cohort / args.protocol / args.measurement_scope
    output.mkdir(parents=True, exist_ok=True)
    (output / "models").mkdir(exist_ok=True)
    if args.smoke:
        data = pd.read_parquet(source)
        data = data.loc[data.replicate.eq(0)]
        source = output / "cases.parquet"
        data.to_parquet(source, index=False)
    names = ["generic_target_disagreement", "uncertain_support", "season_spline", "direct_h30_uncertainty"] if args.smoke else list(SPECS) + list(RULES)
    if args.scores:
        names = args.scores.split(",")
        if set(names) - (set(SPECS) | set(RULES)):
            raise ValueError("Unknown requested screening specification")
    seeds = [101] if args.smoke else settings["fold_seeds"]
    C.write_json(output / "analysis_contract.json", {"specifications": {name: {"features": list(features), "kind": kind} for name, (features, kind) in SPECS.items()}, "rules": RULES, "split": "60/20/20 independent groups", "measurement_scope": args.measurement_scope, "primary_risk": "case-weighted empirical selected risk", "formal_risk": "new independent group with declared uniform within-group sampling; bounded-mean KL test", "formal_bound_assumptions": "independent deployment-representative groups and a fixed predictor and threshold family independent of calibration", "source_sha256": C.digest(source)})
    print(f"[354] {len(names) * len(seeds)} score tasks, {args.protocol}", flush=True)
    results = Parallel(n_jobs=args.workers, verbose=10)(delayed(run_score)(str(source), str(output), name, seed, settings, args.measurement_scope) for name in names for seed in seeds)
    C.write_json(output / "completed_scores.json", {"scores": results})
    C.write_json(output / "protocol_fingerprint.json", C.fingerprint(Path(__file__), {"cases": source}))
    print(f"[354] completed {len(results)} score tasks", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
