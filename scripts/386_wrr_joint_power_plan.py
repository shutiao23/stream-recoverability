#!/usr/bin/env python3
"""Refit models and recalibrate across explicit simulated component budgets."""
from __future__ import annotations

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
from functools import lru_cache
import json

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.stats import beta, norm

import wrr_r3_common as C
from stream_recoverability.experiments.v19_revision import decision_baselines as D
from stream_recoverability.experiments.v19_revision.learning import GENERIC, DIRECT_UNCERTAINTY, WINDOW_INFORMATION, group_roles
from stream_recoverability.experiments.v19_revision.risk import bounded_mean_upper, fixed_training_candidates

OUT = C.READY / "followup_20261021/joint_power"
CONFIG = C.ROOT / "configs/wrr_joint_power_20261021.json"


def hoeffding_gain_lower(mean, n_groups, alpha):
    return np.asarray(mean) - np.sqrt(2 * np.log(1 / alpha) / n_groups)


def group_counts(frame, score, candidates):
    total, accepted, failed, names = [], [], [], []
    for name, positions in frame.groupby("independence_group", sort=True).indices.items():
        values = np.asarray(score)[positions]
        ordered = np.argsort(values, kind="stable")
        ranks = np.searchsorted(values[ordered], candidates, side="right")
        failures = frame.iloc[positions].policy_bad.to_numpy(dtype=int)[ordered]
        prefix = np.r_[0, np.cumsum(failures)]
        names.append(str(name))
        total.append(len(positions))
        accepted.append(ranks)
        failed.append(prefix[ranks])
    return np.asarray(accepted), np.asarray(failed), np.asarray(total), names


def empirical_index(accepted, failed, composition, n_groups, rng, *, draws, risk_cap):
    # Bootstrap the virtual iid components through their finite empirical support.
    weights = rng.multinomial(n_groups, composition / n_groups, size=draws)
    denominator = weights @ accepted
    rates = np.divide(weights @ failed, denominator, out=np.ones_like(denominator, dtype=float), where=denominator > 0)
    upper = np.quantile(rates, 1 - 0.05 / accepted.shape[1], axis=0)
    permitted = np.flatnonzero((upper <= risk_cap) & (composition @ accepted > 0))
    return int(permitted[-1]) if len(permitted) else None


def formal_index(accepted, failed, totals, composition, n_groups, risk_cap, alpha):
    a, b = accepted / totals[:, None], failed / totals[:, None]
    x = (composition @ (b + risk_cap * (1 - a))) / n_groups
    upper = np.array([bounded_mean_upper(float(np.clip(value, 0, 1)), n_groups, alpha=alpha / len(x)) for value in x])
    permitted = np.flatnonzero((upper <= risk_cap) & (composition @ a > 0))
    return int(permitted[-1]) if len(permitted) else None


@lru_cache(maxsize=1)
def source_parts():
    frame = pd.read_parquet(C.source_cases("strictly_prior_years"))
    frame = frame.loc[frame.statistic_class.isin(["daily_mean", "documented_daily_mean"])].copy()
    groups = pd.read_csv(C.RUN / "r3_06_independence_risk/complete_network_independence.csv").set_index("network_id").independence_group
    frame["independence_group"] = frame.network_id.map(groups)
    if (frame.maximum_training_calendar_year >= frame.year).any():
        raise RuntimeError("Future local inputs entered power planning")
    roles = group_roles(frame.independence_group.to_numpy(), 20261021, 0)
    parts = []
    for role in ("train", "calibration", "test"):
        part = frame.loc[frame.independence_group.map(roles).eq(role)]
        part = part.loc[part.year <= 2018] if role != "test" else part.loc[part.year.between(2019, 2022)]
        parts.append(part.reset_index(drop=True))
    if any(set(left.independence_group) & set(right.independence_group) for i, left in enumerate(parts) for right in parts[i + 1:]):
        raise RuntimeError("Power roles share original components")
    return parts


def refit(training_size, rep, settings):
    output = OUT / "refits" / f"train_{training_size}" / f"rep_{rep:04d}.json"
    if output.exists():
        return json.loads(output.read_text())["rows"]
    source, calibration, test = source_parts()
    rng = np.random.default_rng(20261021 + rep + 10000 * training_size)
    mapping = {str(name): block for name, block in source.groupby("independence_group")}
    chosen = rng.choice(sorted(mapping), size=training_size, replace=True)
    train = pd.concat([mapping[name] for name in chosen], ignore_index=True)
    tables = []
    for window in (False, True):
        features = GENERIC + DIRECT_UNCERTAINTY + (WINDOW_INFORMATION if window else ())
        model = D.fit_matched(train, features, train.policy_bad.astype(int), objective="probability", seed=20261021 + rep)
        predictions = [D.predict_matched(model, data, features, objective="probability") for data in (train, calibration, test)]
        predictions = [np.where(np.isfinite(data.policy_metric), score, np.inf) for data, score in zip((train, calibration, test), predictions)]
        candidates = fixed_training_candidates(predictions[0])
        tables.append({"calibration": group_counts(calibration, predictions[1], candidates), "test": group_counts(test, predictions[2], candidates)})
    if tables[0]["calibration"][3] != tables[1]["calibration"][3] or tables[0]["test"][3] != tables[1]["test"][3]:
        raise RuntimeError("Candidate and baseline do not have paired component support")
    n_cal_support = len(tables[0]["calibration"][2])
    n_test_support = len(tables[0]["test"][2])
    test_weights = {n: rng.multinomial(n, np.full(n_test_support, 1 / n_test_support)) for n in settings["simulated_test_groups"]}
    rows = []
    risk_cap, margin = settings["risk_cap"], settings["practical_gain"]
    for n_cal in settings["simulated_calibration_groups"]:
        composition = rng.multinomial(n_cal, np.full(n_cal_support, 1 / n_cal_support))
        for policy in settings["calibration_policies"]:
            selections = []
            for table in tables:
                accepted, failed, totals, _ = table["calibration"]
                if policy == "formal":
                    index = formal_index(accepted, failed, totals, composition, n_cal, risk_cap, settings["alpha_allocation"]["formal_calibration_per_model"])
                else:
                    index = empirical_index(accepted, failed, composition, n_cal, rng, draws=settings["calibration_bootstrap_draws"], risk_cap=risk_cap)
                selections.append(index)
            a_values, b_values = [], []
            for table, index in zip(tables, selections):
                accepted, failed, totals, _ = table["test"]
                a_values.append(accepted[:, index] / totals if index is not None else np.zeros(n_test_support))
                b_values.append(failed[:, index] / totals if index is not None else np.zeros(n_test_support))
            a_values, b_values = np.asarray(a_values), np.asarray(b_values)
            true_a, true_b = a_values.mean(axis=1), b_values.mean(axis=1)
            d = a_values[1] - a_values[0]
            dgp_gain = float(d.mean())
            true_risks = np.divide(true_b, true_a, out=np.full(2, np.inf), where=true_a > 0)
            population_met = bool((true_risks <= risk_cap).all() and dgp_gain > margin)
            for n_test, weights in test_weights.items():
                sample_a, sample_b = (weights @ values.T / n_test for values in (a_values, b_values))
                x = sample_b + risk_cap * (1 - sample_a)
                upper = np.array([bounded_mean_upper(float(np.clip(value, 0, 1)), n_test, alpha=settings["alpha_allocation"]["test_risk_per_model"]) for value in x])
                observed_gain = float(weights @ d / n_test)
                gain_lower = float(hoeffding_gain_lower(observed_gain, n_test, settings["alpha_allocation"]["paired_gain"]))
                variance = max(float(weights @ (d ** 2) / n_test - observed_gain ** 2), 0) * n_test / (n_test - 1)
                asymptotic_lower = observed_gain - norm.ppf(1 - settings["alpha_allocation"]["paired_gain"]) * np.sqrt(variance / n_test)
                risk_evidence = bool((upper <= risk_cap).all() and (sample_a > 0).all())
                primary_pass = risk_evidence and gain_lower > margin
                sensitivity_pass = risk_evidence and asymptotic_lower > margin
                rows.append({"training_groups": training_size, "calibration_groups": n_cal, "test_groups": n_test, "policy": policy, "repetition": rep,
                             "source_training_support": len(mapping), "sampled_distinct_training_components": len(set(chosen)),
                             "source_calibration_support": n_cal_support, "source_test_support": n_test_support,
                             "calibration_positive_both": all(index is not None for index in selections), "population_target_met": population_met,
                             "risk_evidence": risk_evidence, "primary_joint_pass": bool(primary_pass), "true_joint_success": bool(primary_pass and population_met),
                             "asymptotic_joint_pass": bool(sensitivity_pass), "asymptotic_true_joint_success": bool(sensitivity_pass and population_met),
                             "dgp_retention_gain": dgp_gain, "observed_retention_gain": observed_gain,
                             "gain_lower": gain_lower, "baseline_risk_upper": float(upper[0]), "candidate_risk_upper": float(upper[1])})
    C.write_json(output, {"rows": rows})
    return rows


def worker(training_size, rep, settings):
    # Import a named module so the cached source reader is not pickled as __main__.
    import importlib
    module = importlib.import_module("386_wrr_joint_power_plan")
    return module.refit(training_size, rep, settings)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--training-size", type=int)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    settings = json.loads(CONFIG.read_text())
    repetitions = args.repetitions or settings["procedure_repetitions_per_training_size"]
    sizes = [args.training_size] if args.training_size else settings["simulated_training_groups"]
    results = Parallel(n_jobs=args.workers, verbose=10)(delayed(worker)(size, repetition, settings) for size in sizes for repetition in range(repetitions))
    records = pd.DataFrame([row for result in results for row in result])
    suffix = f"train_{sizes[0]}" if len(sizes) == 1 else "all"
    records.to_parquet(OUT / f"simulated_procedures_{suffix}.parquet", index=False)
    summary = records.groupby(["training_groups", "calibration_groups", "test_groups", "policy"]).agg(
        repetitions=("repetition", "size"), calibration_positive_fraction=("calibration_positive_both", "mean"), population_target_fraction=("population_target_met", "mean"),
        joint_pass_fraction=("primary_joint_pass", "mean"), true_joint_power=("true_joint_success", "mean"), asymptotic_true_joint_power=("asymptotic_true_joint_success", "mean"),
        source_training_support=("source_training_support", "first"), source_calibration_support=("source_calibration_support", "first"), source_test_support=("source_test_support", "first"),
        mean_distinct_training_support=("sampled_distinct_training_components", "mean"), mean_dgp_gain=("dgp_retention_gain", "mean")).reset_index()
    count = np.rint(summary.true_joint_power * summary.repetitions).astype(int)
    summary["mc_lower"] = [float(beta.ppf(0.025, k, n - k + 1)) if k else 0.0 for k, n in zip(count, summary.repetitions)]
    summary["mc_upper"] = [float(beta.ppf(0.975, k + 1, n - k)) if k < n else 1.0 for k, n in zip(count, summary.repetitions)]
    summary.to_csv(OUT / f"joint_power_{suffix}.csv", index=False)
    feasible = summary.loc[summary.mc_lower >= settings["target_joint_power"]]
    C.write_json(OUT / f"plan_decision_{suffix}.json", {"status": "source_like_planning_not_confirmatory_evidence", "completed_refits": len(results),
                 "has_supported_80pct_joint_power": not feasible.empty, "recommended_plans": feasible.to_dict("records"),
                 "actual_source_components_by_role": [part.independence_group.nunique() for part in source_parts()],
                 "simulated_budgets_are_not_acquired_components": True,
                 "risk_and_gain_bounds_are_conservative": True, "unseen_process_and_climate_types_not_simulated": True,
                 "stopping_decision": "do_not_recruit_for_a_claimed_power_target_without_a_supported_joint_design" if feasible.empty else "prospective_sampling_still_requires_independent_population_and_candidate_freeze"})
    print(f"[386] {len(results)} complete paired refits, {len(summary)} budget cells; supported plans={len(feasible)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
