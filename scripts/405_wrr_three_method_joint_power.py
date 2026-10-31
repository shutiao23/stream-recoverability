#!/usr/bin/env python3
"""Refit, calibrate and evaluate the fixed three-method/two-reference procedure."""
from __future__ import annotations

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
from functools import lru_cache
import importlib
import json

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.special import xlogy
from scipy.stats import beta

import wrr_r3_common as C
from stream_recoverability.experiments.v19_revision import decision_baselines as D
from stream_recoverability.experiments.v19_revision.learning import GENERIC, WINDOW_INFORMATION
from stream_recoverability.experiments.v19_revision.risk import bounded_mean_upper, fixed_training_candidates

J = importlib.import_module("386_wrr_joint_power_plan")
P = importlib.import_module("390_wrr_developed_probability_system")
OUT = C.READY / "followup_20261021/three_method_joint_power"
CONFIG = C.ROOT / "configs/wrr_three_method_joint_power_20261021.json"
KINDS = ("native_CDF", "boost_direct", "boost_window")


def bounded_mean_below_cap(means, n_groups, cap, alpha):
    """Equivalent to the fixed Chernoff-KL upper bound <= cap, without root fits."""
    values = np.asarray(means, dtype=float)
    divergence = xlogy(values, values / cap) + xlogy(1 - values, (1 - values) / (1 - cap))
    return (values <= cap) & (divergence >= np.log(1 / alpha) / n_groups)


def choose_formal(accepted, failed, totals, composition, n_groups, cap, alpha):
    a, b = accepted / totals[:, None], failed / totals[:, None]
    mean_a = composition @ a / n_groups
    loss = composition @ (b + cap * (1 - a)) / n_groups
    eligible = np.flatnonzero(bounded_mean_below_cap(np.clip(loss, 0, 1), n_groups, cap, alpha / accepted.shape[1]) & (mean_a > 0))
    return int(eligible[-1]) if len(eligible) else None


def choose_empirical(accepted, failed, bootstrap, composition, cap, alpha):
    a = bootstrap @ accepted
    rates = np.divide(bootstrap @ failed, a, out=np.ones_like(a, dtype=float), where=a > 0)
    upper = np.quantile(rates, 1 - alpha / accepted.shape[1], axis=0)
    eligible = np.flatnonzero((upper <= cap) & (composition @ accepted > 0))
    return int(eligible[-1]) if len(eligible) else None


def joint_evidence(admission, failures, weights, cap, margin, alpha_risk, alpha_gain):
    """Three methods share the same sampled groups; neither reference is dropped."""
    admission, failures = np.asarray(admission), np.asarray(failures)
    weights = np.asarray(weights)
    if admission.shape != failures.shape or admission.shape[0] != 3 or admission.shape[1] != len(weights):
        raise ValueError("Three methods require identical paired group support")
    n = int(weights.sum())
    a, b = admission @ weights / n, failures @ weights / n
    loss = np.clip(b + cap * (1 - a), 0, 1)
    risk_ok = bool(bounded_mean_below_cap(loss, n, cap, alpha_risk).all() and (a > 0).all())
    gains = (admission[2] - admission[:2]) @ weights / n
    lower = gains - np.sqrt(2 * np.log(1 / alpha_gain) / n)
    population_a, population_b = admission.mean(axis=1), failures.mean(axis=1)
    risks = np.divide(population_b, population_a, out=np.full(3, np.inf), where=population_a > 0)
    population_gains = (admission[2] - admission[:2]).mean(axis=1)
    target_met = bool((risks <= cap).all() and (population_gains > margin).all())
    passed = risk_ok and bool((lower > margin).all())
    return {"risk_evidence_all_three": risk_ok, "joint_pass": passed,
            "population_target_met": target_met, "true_joint_success": passed and target_met,
            "minimum_population_gain": float(population_gains.min()),
            "gain_over_native_CDF": float(gains[0]), "gain_over_boost_direct": float(gains[1]),
            "gain_lower_over_native_CDF": float(lower[0]), "gain_lower_over_boost_direct": float(lower[1]),
            "candidate_population_risk": float(risks[2]) if np.isfinite(risks[2]) else None,
            "positive_admission_all_three": bool((a > 0).all())}


@lru_cache(maxsize=1)
def source_parts():
    result = []
    for role in ("development", "calibration", "test"):
        frame = P.role_data(role)
        if role != "test":
            available = np.isfinite(frame.h30_reconstructed) & frame.h30_samples_C.map(lambda value: isinstance(value, (list, np.ndarray)) and np.isfinite(value).all())
            frame = frame.loc[available]
        part = P.prepare_point(frame.reset_index(drop=True), "csdi_developed_air")
        part["policy_bad"] = part.own_failure
        result.append(part)
    if any(set(left.independence_group) & set(right.independence_group) for i, left in enumerate(result) for right in result[i + 1:]):
        raise RuntimeError("Opened planning roles share original components")
    return result


def refit(training_size, repetition, settings):
    destination = OUT / "refits" / f"train_{training_size}" / f"rep_{repetition:04d}.json"
    if destination.exists():
        old = json.loads(destination.read_text())
        if old.get("settings") == settings:
            return old["rows"]
    source, calibration, test = source_parts()
    rng = np.random.default_rng(settings["seed"] + 10000 * training_size + repetition)
    mapping = {str(name): block for name, block in source.groupby("independence_group")}
    chosen = rng.choice(sorted(mapping), size=training_size, replace=True)
    train = pd.concat([mapping[name] for name in chosen], ignore_index=True)
    generic = tuple(name for name in GENERIC if name != "estimator_disagreement")
    direct = ("reconstruction_point", "threshold_margin_C", "NN_failure_probability", "NN_target_abs90", "NN_h30_sd", "NN_width90")
    tables = []
    for kind in KINDS:
        features = generic + direct + (tuple(name + "_NN" for name in WINDOW_INFORMATION) if kind == "boost_window" else ())
        if kind == "native_CDF":
            values = [block.NN_failure_probability.to_numpy() for block in (train, calibration, test)]
        else:
            model = D.fit_matched(train, features, train.own_failure.astype(int), objective="probability", seed=settings["seed"] + repetition)
            values = [D.predict_matched(model, block, features, objective="probability") for block in (train, calibration, test)]
        values = [np.where(block.cdf_available & np.isfinite(block.reconstruction_point), score, np.inf)
                  for block, score in zip((train, calibration, test), values)]
        candidates = fixed_training_candidates(values[0])
        tables.append({role: J.group_counts(frame, score, candidates)
                       for role, frame, score in [("calibration", calibration, values[1]), ("test", test, values[2])]})
    for role in ("calibration", "test"):
        if any(table[role][3] != tables[0][role][3] for table in tables[1:]):
            raise RuntimeError("Methods do not share the same planning group support")
    ncal, ntest = len(tables[0]["calibration"][2]), len(tables[0]["test"][2])
    test_weights = {n: rng.multinomial(n, np.full(ntest, 1 / ntest)) for n in settings["simulated_test_groups"]}
    cap, margin = settings["risk_cap"], settings["practical_gain"]
    alpha = settings["alpha_allocation"]
    rows = []
    for cal_budget in settings["simulated_calibration_groups"]:
        composition = rng.multinomial(cal_budget, np.full(ncal, 1 / ncal))
        bootstrap = rng.multinomial(cal_budget, composition / cal_budget, size=settings["calibration_bootstrap_draws"])
        for policy in settings["calibration_policies"]:
            indices = []
            for table in tables:
                a, b, total, _ = table["calibration"]
                index = choose_formal(a, b, total, composition, cal_budget, cap, alpha["formal_calibration_per_method"]) if policy == "formal" else choose_empirical(a, b, bootstrap, composition, cap, settings["empirical_sensitivity_calibration_alpha"])
                indices.append(index)
            admission, failures = [], []
            for table, index in zip(tables, indices):
                a, b, total, _ = table["test"]
                admission.append(a[:, index] / total if index is not None else np.zeros(ntest))
                failures.append(b[:, index] / total if index is not None else np.zeros(ntest))
            for test_budget, weights in test_weights.items():
                evidence = joint_evidence(admission, failures, weights, cap, margin,
                                          alpha["evaluation_risk_per_method"], alpha["paired_gain_per_reference"])
                rows.append({"training_groups": training_size, "calibration_groups": cal_budget,
                             "test_groups": test_budget, "policy": policy, "repetition": repetition,
                             "source_training_support": len(mapping), "source_calibration_support": ncal,
                             "source_test_support": ntest, "sampled_distinct_training_components": len(set(chosen)),
                             "calibration_positive_all_three": all(index is not None for index in indices), **evidence})
    C.write_json(destination, {"settings": settings, "rows": rows})
    return rows


def worker(*args):
    return importlib.import_module("405_wrr_three_method_joint_power").refit(*args)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--training-size", type=int)
    args = parser.parse_args()
    settings = json.loads(CONFIG.read_text())
    sizes = [args.training_size] if args.training_size else settings["simulated_training_groups"]
    repetitions = args.repetitions or settings["repetitions_per_training_size"]
    OUT.mkdir(exist_ok=True, parents=True)
    runs = Parallel(n_jobs=args.workers, verbose=10)(delayed(worker)(n, rep, settings) for n in sizes for rep in range(repetitions))
    frame = pd.DataFrame([row for run in runs for row in run])
    suffix = f"train_{sizes[0]}_reps_{repetitions}" if len(sizes) == 1 or repetitions != settings["repetitions_per_training_size"] else "all"
    frame.to_parquet(OUT / f"procedures_{suffix}.parquet", index=False)
    summary = frame.groupby(["training_groups", "calibration_groups", "test_groups", "policy"]).agg(
        repetitions=("repetition", "size"), calibration_positive_fraction=("calibration_positive_all_three", "mean"),
        population_target_fraction=("population_target_met", "mean"), joint_pass_fraction=("joint_pass", "mean"),
        true_joint_power=("true_joint_success", "mean"), risk_evidence_fraction=("risk_evidence_all_three", "mean"),
        mean_minimum_population_gain=("minimum_population_gain", "mean"),
        source_training_support=("source_training_support", "first"), source_calibration_support=("source_calibration_support", "first"),
        source_test_support=("source_test_support", "first")).reset_index()
    counts = np.rint(summary.true_joint_power * summary.repetitions).astype(int)
    summary["mc_lower"] = [float(beta.ppf(.025, k, n - k + 1)) if k else 0. for k, n in zip(counts, summary.repetitions)]
    summary["mc_upper"] = [float(beta.ppf(.975, k + 1, n - k)) if k < n else 1. for k, n in zip(counts, summary.repetitions)]
    summary.to_csv(OUT / f"power_{suffix}.csv", index=False)
    full = repetitions == settings["repetitions_per_training_size"] and sizes == settings["simulated_training_groups"]
    supported = summary.loc[summary.policy.eq("formal") & summary.mc_lower.ge(settings["target_joint_power"])]
    C.write_json(OUT / f"decision_{suffix}.json", {
        "scope": "opened_old_role_empirical_full_F2_head_refit_calibration_evaluation_planning",
        "complete_prespecified_run": full, "completed_paired_head_refits": len(runs), "budget_cells": len(summary),
        "actual_old_group_support_by_role": [part.independence_group.nunique() for part in source_parts()],
        "maximum_formal_true_joint_power": float(summary.loc[summary.policy.eq("formal"), "true_joint_power"].max()),
        "maximum_empirical_sensitivity_true_joint_power": float(summary.loc[summary.policy.eq("empirical_sensitivity"), "true_joint_power"].max()),
        "supported_old_like_formal_budgets": supported.to_dict("records") if full else [],
        "recommended_new_target_recruitment_N": None,
        "reasons_no_new_population_sample_size_claim": ["only eleven/nine/seven old role support groups", "role-wise iid empirical simulation does not generate new climates, processes or regional events", "new target recruitment and dependence conditions remain unverified"],
        "three_methods_two_references_and_shared_alpha_included": True,
        "probability_reconstruction_frozen_not_retrained_in_the_F2_specification": True,
        "new_Australian_measurements_or_prediction_errors_used": False,
        "simulated_group_budgets_are_not_acquired_units": True,
        "primary_claim_requires_new_independent_confirmation": True})
    print(f"[405] {len(runs)} complete paired-head refits, {len(summary)} cells; old-like supported formal budgets {len(supported)}; no new-target N recommended", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
