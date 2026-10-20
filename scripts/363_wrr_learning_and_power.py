#!/usr/bin/env python3
"""Repeated learning curves and whole-admission-procedure network bootstrap."""

from __future__ import annotations

import os

for thread_variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[thread_variable] = "1"

import argparse
import importlib
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_r3_common as C

from stream_recoverability.experiments.v17_fitness.paths import stable_seed
from stream_recoverability.experiments.v19_revision.learning import empirical_threshold, fit_score, group_roles, predict_score, specifications
from stream_recoverability.experiments.v19_revision.risk import fixed_training_candidates

OUT = C.RUN / "r3_13_learning_power/admission"
NAMES = ("generic_target_disagreement", "generic_direct_h30_uncertainty", "uncertain_support", "generic_both_diagnostics")
SPECS = specifications()


@lru_cache(maxsize=2)
def data_parts(protocol_name: str) -> dict:
    source = C.source_cases(protocol_name)
    features = list(dict.fromkeys(feature for name in NAMES for feature in SPECS[name][0]))
    columns = list(dict.fromkeys(["network_id", "station_id", "year", "statistic_class", "independence_group", "policy_metric", "abserr_policy", "policy_bad", "maximum_training_calendar_year", *features]))
    frame = pd.read_parquet(source, columns=columns)
    groups = pd.read_csv(C.RUN / "r3_06_independence_risk/complete_network_independence.csv").set_index("network_id").independence_group
    frame["independence_group"] = frame.network_id.map(groups)
    frame = frame.loc[frame.statistic_class.isin(["daily_mean", "documented_daily_mean"])]
    roles = group_roles(frame.independence_group.to_numpy(), 20261020, 0)
    role = frame.independence_group.map(roles)
    result = {}
    for name in ["train", "calibration", "test"]:
        part = frame.loc[role.eq(name)]
        if protocol_name == "strictly_prior_years":
            part = part.loc[part.year <= 2018] if name != "test" else part.loc[part.year.between(2019, 2022)]
            if (part.maximum_training_calendar_year >= part.year).any():
                raise RuntimeError("Prospective power inputs contain future information")
        result[name] = part.reset_index(drop=True)
        result[f"{name}_groups"] = {group: np.asarray(list(indices)) for group, indices in result[name].groupby("independence_group").groups.items()}
    return result


def resample_groups(frame: pd.DataFrame, mapping: dict, chosen: list[str], *, relabel: bool) -> pd.DataFrame:
    pieces = []
    for copy, group in enumerate(chosen):
        part = frame.iloc[mapping[group]]
        if relabel:
            part = part.copy()
            part["independence_group"] = f"bootstrap_{copy}"
        pieces.append(part)
    return pd.concat(pieces, ignore_index=True)


def procedure(protocol_name: str, repetition: int, *, learning_size: int | None = None) -> dict:
    parts = data_parts(protocol_name)
    rng = np.random.default_rng(stable_seed("r3-procedure-bootstrap", protocol_name, repetition, learning_size))
    train_units = np.array(sorted(parts["train_groups"]))
    calibration_units = np.array(sorted(parts["calibration_groups"]))
    if learning_size is None:
        chosen_train = rng.choice(train_units, len(train_units), replace=True).tolist()
        chosen_calibration = rng.choice(calibration_units, len(calibration_units), replace=True).tolist()
        train = resample_groups(parts["train"], parts["train_groups"], chosen_train, relabel=False)
        calibration = resample_groups(parts["calibration"], parts["calibration_groups"], chosen_calibration, relabel=True)
    else:
        chosen_train = rng.choice(train_units, min(learning_size, len(train_units)), replace=False).tolist()
        chosen_calibration = calibration_units.tolist()
        train = resample_groups(parts["train"], parts["train_groups"], chosen_train, relabel=False)
        calibration = parts["calibration"]
    test = parts["test"]
    test_units = np.array(sorted(parts["test_groups"]))
    totals = np.array([len(parts["test_groups"][group]) for group in test_units])
    counts = []
    summaries = []
    for name in NAMES:
        features, kind = SPECS[name]
        seed = stable_seed("r3-procedure-learner", repetition)
        fitted = fit_score(train, features, kind, seed=seed)
        train_score = predict_score(fitted, train, features, kind)
        cal_score = predict_score(fitted, calibration, features, kind)
        test_score = predict_score(fitted, test, features, kind)
        candidates = fixed_training_candidates(train_score)
        choice = empirical_threshold(cal_score, calibration.policy_bad.to_numpy(dtype=bool), calibration.independence_group.to_numpy(), candidates, seed=stable_seed("r3-procedure-cal", repetition), draws=1000)
        admit = test_score <= choice["threshold"]
        accepted = np.array([admit[parts["test_groups"][group]].sum() for group in test_units])
        counts.append(accepted)
        summaries.append({"name": name, "retention": float(admit.mean()), "finite_test_risk": float(test.loc[admit, "policy_bad"].mean()) if admit.any() else None, "n_admitted": int(admit.sum())})
    return {"repetition": repetition, "training_size": learning_size, "unique_training_subset": ";".join(sorted(set(chosen_train))), "n_training_draws": len(chosen_train), "n_calibration_draws": len(chosen_calibration), "test_groups": test_units.tolist(), "totals": totals.tolist(), "admissions": np.asarray(counts).tolist(), "summaries": summaries}


def cached_procedure(protocol_name: str, repetition: int) -> dict:
    destination = OUT / protocol_name / "bootstrap" / f"rep_{repetition:04d}.json"
    if destination.exists():
        return json.loads(destination.read_text())
    result = procedure(protocol_name, repetition)
    C.write_json(destination, result)
    return result


def bootstrap_worker(protocol_name: str, repetition: int) -> dict:
    module = importlib.import_module("363_wrr_learning_and_power")
    return module.cached_procedure(protocol_name, repetition)


def learning_worker(protocol_name: str, repetition: int, size: int) -> dict:
    module = importlib.import_module("363_wrr_learning_and_power")
    return module.procedure(protocol_name, repetition, learning_size=size)


def power_projection(records: list[dict], settings: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    source_groups = len(records[0]["test_groups"])
    totals = np.asarray([record["totals"] for record in records], dtype=float)
    admissions = np.asarray([record["admissions"] for record in records], dtype=float)
    rows, uncertainty = [], []
    comparisons = [("uncertain_support", "generic_target_disagreement"), ("generic_direct_h30_uncertainty", "generic_target_disagreement"), ("uncertain_support", "generic_direct_h30_uncertainty"), ("generic_direct_h30_uncertainty", "generic_both_diagnostics")]
    sizes = sorted(set([7, 19, 27, 53, source_groups, 100, 200, 400]))
    for left, right in comparisons:
        difference = admissions[:, NAMES.index(left)] - admissions[:, NAMES.index(right)]
        reference_mean = float((difference.sum(axis=1) / totals.sum(axis=1)).mean())
        rng = np.random.default_rng(stable_seed("r3-power-projection", left, right))
        original_bootstrap = []
        for record_index in range(len(records)):
            selection = rng.integers(0, source_groups, source_groups)
            original_bootstrap.append(float(difference[record_index, selection].sum() / totals[record_index, selection].sum()))
        low, high = np.quantile(original_bootstrap, [0.025, 0.975])
        uncertainty.append({"left": left, "right": right, "mean_refitted_procedure_difference": reference_mean, "whole_procedure_ci_low": float(low), "whole_procedure_ci_high": float(high), "n_fully_refitted_procedures": len(records), "n_evaluation_groups": source_groups})
        for size in sizes:
            simulated_null = []
            for record_index in range(len(records)):
                selection = rng.integers(0, source_groups, size)
                value = difference[record_index, selection].sum() / totals[record_index, selection].sum()
                simulated_null.append(value - reference_mean)
            simulated_null = np.asarray(simulated_null)
            critical = float(np.quantile(simulated_null, 0.975))
            for alternative in (0.05, 0.08, 0.10):
                for null_margin in (0.0, settings["superiority_margin_retention"]):
                    power = float((simulated_null + alternative > critical + null_margin).mean())
                    rows.append({"left": left, "right": right, "planned_test_groups": size, "assumed_true_gain": alternative, "null_margin": null_margin, "projected_power": power, "n_refitted_procedures": len(records), "projection_assumption": "source-like independent group distribution and location-shift alternative; common-risk feasibility is not established by this projection"})
    return pd.DataFrame(rows), pd.DataFrame(uncertainty)


def learning_curves(protocol_name: str, workers: int) -> pd.DataFrame:
    parts = data_parts(protocol_name)
    pool_size = len(parts["train_groups"])
    sizes = [size for size in (10, 25, 50, 75) if size <= pool_size] + [pool_size]
    tasks = [(size, draw) for size in sorted(set(sizes)) for draw in range(20 if size != pool_size else 3)]
    records = Parallel(n_jobs=workers, verbose=10)(delayed(learning_worker)(protocol_name, draw, size) for size, draw in tasks)
    rows = []
    for record in records:
        for summary in record["summaries"]:
            rows.append({"training_groups": record["training_size"], "draw": record["repetition"], "draw_kind": "full_fixed_pool_learner_seed" if record["training_size"] == pool_size else "network_subset", "unique_training_subset": record["unique_training_subset"], **summary})
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], default="leave_one_year_out")
    parser.add_argument("--workers", type=int, default=48)
    parser.add_argument("--repetitions", type=int, default=1000)
    parser.add_argument("--learning-only", action="store_true")
    args = parser.parse_args()
    settings = C.protocol()
    output = OUT / args.protocol
    output.mkdir(parents=True, exist_ok=True)
    C.write_json(output / "power_contract.json", {"n_complete_admission_procedure_refits": args.repetitions, "model_names": list(NAMES), "split": "disjoint old-source 60/20/20 independent groups", "bootstrap_units": "whole independent components, including every local station history and outage", "local_reconstruction_recomputed": False, "local_reconstruction_cache_justification": "resampling a whole component leaves all local reconstruction inputs and deterministic fits unchanged; global risk learners and thresholds are refitted", "prospective_global_fit_and_calibration_years": "through 2018", "prospective_old_source_evaluation_years": "2019-2022", "power_assumptions": "source-like independent groups; location-shift retention alternatives conditional on common-risk feasibility", "assumed_retention_gains": [0.05, 0.08, 0.10], "tested_null_margins": [0.0, 0.05], "new_external_outcomes_used": False})
    if args.learning_only:
        curves = learning_curves(args.protocol, args.workers)
        curves.to_csv(output / "learning_curves.csv", index=False)
        print("[363] repeated learning curves complete", flush=True)
        return 0
    print(f"[363] {args.repetitions} whole-procedure refits, four paired models, {args.protocol}", flush=True)
    results = Parallel(n_jobs=args.workers, verbose=10)(delayed(bootstrap_worker)(args.protocol, repetition) for repetition in range(args.repetitions))
    projections, intervals = power_projection(results, settings)
    projections.to_csv(output / "power_projections.csv", index=False)
    intervals.to_csv(output / "whole_procedure_intervals.csv", index=False)
    C.write_json(output / "summary.json", {"n_completed_refitted_procedures": len(results), "n_fitted_risk_models": len(results) * len(NAMES), "protocol": args.protocol, "source_only_power_projection": True, "new_external_outcomes_used": False})
    C.write_json(output / "protocol_fingerprint.json", C.fingerprint(Path(__file__), {"cases": C.source_cases(args.protocol), "contract": output / "power_contract.json"}))
    print("[363] whole-procedure intervals and power projections complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
