#!/usr/bin/env python3
"""Four-cell objective/window comparison with grouped out-of-fold decisions."""
from __future__ import annotations

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
import json

import joblib
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_r3_common as C
from stream_recoverability.experiments.v19_revision import decision_baselines as D
from stream_recoverability.experiments.v19_revision.learning import (
    GENERIC, DIRECT_UNCERTAINTY, WINDOW_INFORMATION, empirical_threshold, group_roles,
)
from stream_recoverability.experiments.v19_revision.risk import fixed_training_candidates, select_group_threshold
from stream_recoverability.seeds import plain_seed

OUT = C.READY / "followup_20261021"
CONFIG = C.ROOT / "configs/wrr_followup_20261021.json"
KEYS = ["network_id", "station_id", "year", "realization_id"]
BASE = GENERIC + DIRECT_UNCERTAINTY
# Seed streams: the last part of every seed names what it draws.
SEED_CODES = {"matched_model": 1, "tie_break": 2}


def load_cases(protocol):
    frame = pd.read_parquet(C.source_cases(protocol))
    frame = frame.loc[frame.statistic_class.isin(["daily_mean", "documented_daily_mean"])].copy()
    groups = pd.read_csv(C.RUN / "r3_06_independence_risk/complete_network_independence.csv").set_index("network_id").independence_group
    frame["independence_group"] = frame.network_id.map(groups)
    if frame.independence_group.isna().any() or frame[KEYS].duplicated().any():
        raise RuntimeError("Missing group or duplicated candidate identity")
    if protocol == "strictly_prior_years" and (frame.maximum_training_calendar_year >= frame.year).any():
        raise RuntimeError("Future input in prospective analysis")
    frame["threshold_margin_C"] = frame.policy_metric - frame.local_hot_threshold_C
    return frame.reset_index(names="source_row")


def fit_fold(frame, protocol, seed, fold, settings):
    destination = OUT / "factorial" / protocol / f"seed_{seed}" / f"fold_{fold}"
    destination.mkdir(parents=True, exist_ok=True)
    if (destination / "predictions.parquet").exists() and (destination / "selection.json").exists():
        return str(destination)
    roles = group_roles(frame.independence_group.to_numpy(), seed, fold)
    role = frame.independence_group.astype(str).map(roles)
    train, cal, test = (frame.loc[role.eq(part)] for part in ("train", "calibration", "test"))
    if set(train.independence_group) & set(cal.independence_group) or set(test.independence_group) & (set(train.independence_group) | set(cal.independence_group)):
        raise RuntimeError("Group leakage")
    membership = pd.DataFrame({"group": list(roles), "role": list(roles.values())})
    membership.to_csv(destination / "membership.csv", index=False)
    prediction = test[["source_row", *KEYS, "independence_group", "policy_metric", "truth_hottest30", "policy_bad", "local_hot_threshold_C"]].copy()
    selection = []
    # Common seed and calibration resamples across cells reduce irrelevant Monte Carlo noise.
    model_seed = plain_seed(seed, fold, SEED_CODES["matched_model"])
    for objective in settings["objectives"]:
        for window in settings["windows"]:
            arm = f"{objective}_{'window' if window else 'direct'}"
            features = BASE + (WINDOW_INFORMATION if window else ())
            y = train.abserr_policy if objective == "quantile" else train.policy_bad.astype(int)
            model = D.fit_matched(train, features, y, objective=objective, seed=model_seed)
            scores = [D.predict_matched(model, block, features, objective=objective) for block in (train, cal, test)]
            scores = [np.where(np.isfinite(block.policy_metric), score, np.inf) for block, score in zip((train, cal, test), scores)]
            candidates = fixed_training_candidates(scores[0])
            empirical = empirical_threshold(scores[1], cal.policy_bad.to_numpy(), cal.independence_group.to_numpy(), candidates,
                                            seed=model_seed, draws=settings["bootstrap_draws"], risk_cap=settings["risk_cap"], alpha=settings["alpha"])
            formal = select_group_threshold(scores[1], cal.policy_bad.to_numpy(), cal.independence_group.to_numpy(), candidates,
                                            risk_cap=settings["risk_cap"], alpha=settings["alpha"])
            prediction[f"score_{arm}"] = scores[2]
            prediction[f"admit_{arm}"] = np.isfinite(scores[2]) & (scores[2] <= empirical["threshold"])
            prediction[f"certified_{arm}"] = np.isfinite(scores[2]) & (scores[2] <= formal.threshold)
            selection.append({"arm": arm, "features": list(features), "empirical": empirical,
                              "formal_status": formal.status, "formal_threshold": formal.threshold,
                              "n_train_groups": train.independence_group.nunique(), "n_cal_groups": cal.independence_group.nunique(),
                              "n_test_groups": test.independence_group.nunique()})
            joblib.dump({"model": model, "features": features, "objective": objective}, destination / f"{arm}.joblib", compress=3)
    # The hot-probability baseline is estimated for the use itself, with the same feature boundary.
    for name in settings["hot_thresholds"]:
        threshold = (lambda block: block.local_hot_threshold_C.to_numpy()) if name == "local_training_q90" else (lambda block: np.full(len(block), float(name[5:])))
        for window in settings["windows"]:
            features = BASE + (WINDOW_INFORMATION if window else ()) + ("policy_metric", "local_hot_threshold_C", "threshold_margin_C")
            response = (train.truth_hottest30.to_numpy() > threshold(train)).astype(int)
            model = D.fit_matched(train, features, response, objective="probability", seed=model_seed)
            cal_probability, test_probability = [D.predict_matched(model, block, features, objective="probability") for block in (cal, test)]
            calibrated = D.probability_calibration(cal_probability, cal.truth_hottest30.to_numpy() > threshold(cal), test_probability)
            suffix = f"{name}_{'window' if window else 'direct'}"
            prediction[f"hot_raw_{suffix}"] = test_probability
            prediction[f"hot_cal_{suffix}"] = calibrated
    prediction["fold"] = fold
    prediction.to_parquet(destination / "predictions.parquet", index=False)
    # Threshold -inf means reject-all, encoded explicitly rather than nonstandard JSON numbers.
    for row in selection:
        for key in ("threshold",):
            if not np.isfinite(row["empirical"][key]):
                row["empirical"][key] = None
        if not np.isfinite(row["formal_threshold"]):
            row["formal_threshold"] = None
    C.write_json(destination / "selection.json", {"cells": selection})
    print(f"[374] {protocol} seed={seed} fold={fold}, n={len(test)}", flush=True)
    return str(destination)


def interval(values, codes, weights, denominator):
    sums = np.bincount(codes, weights=values, minlength=weights.shape[1])
    draws = (weights @ sums) / denominator
    return tuple(np.quantile(draws, [0.025, 0.975]))


def summarize(frame, protocol, seed, settings):
    destination = OUT / "factorial" / protocol / f"seed_{seed}"
    predictions = pd.concat([pd.read_parquet(destination / f"fold_{fold}/predictions.parquet") for fold in range(5)], ignore_index=True).sort_values("source_row").reset_index(drop=True)
    if len(predictions) != len(frame) or predictions.source_row.duplicated().any():
        raise RuntimeError("Out-of-fold evaluation did not cover each candidate exactly once")
    predictions.to_parquet(destination / "predictions.parquet", index=False)
    units, codes = np.unique(predictions.independence_group.astype(str), return_inverse=True)
    weights = np.random.default_rng(seed).multinomial(len(units), np.full(len(units), 1 / len(units)), size=settings["bootstrap_draws"])
    totals = np.bincount(codes, minlength=len(units))
    denominator = weights @ totals
    identity = {"protocol": protocol, "seed": seed, "n_groups": len(units), "uncertainty": "conditional group bootstrap; fitting/calibration not resampled"}
    failures = predictions.policy_bad.to_numpy(dtype=bool)
    operating, curves, contrasts, costs, reliability = [], [], [], [], []
    arms = [f"{objective}_{window}" for objective in settings["objectives"] for window in ("direct", "window")]
    # Seeded random tie breaking: one fixed rank per candidate (rows follow source_row),
    # shared by every arm and seed and independent of error labels.
    tie_rank = np.random.default_rng(plain_seed(SEED_CODES["tie_break"])).permutation(len(predictions))
    for arm in arms:
        for mode, column in (("empirical", f"admit_{arm}"), ("formal", f"certified_{arm}")):
            admitted = predictions[column].to_numpy()
            accepted = weights @ np.bincount(codes, weights=admitted, minlength=len(units))
            bad = weights @ np.bincount(codes, weights=admitted * failures, minlength=len(units))
            risks = np.divide(bad, accepted, out=np.full(len(bad), np.nan), where=accepted > 0)
            lo, hi = np.nanquantile(risks, [0.025, 0.975]) if np.isfinite(risks).any() else (np.nan, np.nan)
            operating.append({**identity, "arm": arm, "selection": mode, "n_candidates": len(predictions), "accepted": int(admitted.sum()), "failed": int((admitted & failures).sum()),
                              "retention": admitted.mean(), "risk": failures[admitted].mean() if admitted.any() else np.nan, "risk_low": lo, "risk_high": hi})
        for coverage in np.arange(0.05, 1.01, 0.05):
            admitted = np.zeros(len(predictions), dtype=bool)
            for _, positions in predictions.groupby("fold").indices.items():
                values = predictions.iloc[positions][f"score_{arm}"].to_numpy()
                order = np.lexsort((tie_rank[positions], values))[:int(np.floor(coverage * len(positions)))]
                admitted[positions[order[np.isfinite(values[order])]]] = True
            curves.append({**identity, "arm": arm, "requested_retention": coverage, "retention": admitted.mean(), "accepted": int(admitted.sum()), "failed": int((admitted & failures).sum()), "risk": failures[admitted].mean() if admitted.any() else np.nan})
    for left, right in [("quantile_window", "quantile_direct"), ("probability_window", "probability_direct"), ("probability_direct", "quantile_direct"), ("probability_window", "quantile_window")]:
        diff = predictions[f"admit_{left}"].astype(float).to_numpy() - predictions[f"admit_{right}"].astype(float).to_numpy()
        lo, hi = interval(diff, codes, weights, denominator)
        contrasts.append({**identity, "left": left, "right": right, "retention_difference": diff.mean(), "ci_low": lo, "ci_high": hi})
    # Interaction: does the objective change the incremental value of windows?
    interaction = (predictions.admit_probability_window.astype(float) - predictions.admit_probability_direct.astype(float)
                   - predictions.admit_quantile_window.astype(float) + predictions.admit_quantile_direct.astype(float)).to_numpy()
    lo, hi = interval(interaction, codes, weights, denominator)
    contrasts.append({**identity, "left": "window_objective_interaction", "right": "zero", "retention_difference": interaction.mean(), "ci_low": lo, "ci_high": hi})
    available = np.isfinite(predictions.policy_metric.to_numpy())
    for threshold_name in settings["hot_thresholds"]:
        threshold = predictions.local_hot_threshold_C.to_numpy() if threshold_name == "local_training_q90" else np.full(len(predictions), float(threshold_name[5:]))
        truth = predictions.truth_hottest30.to_numpy() > threshold
        hot = predictions.policy_metric.to_numpy() > threshold
        for window in ("direct", "window"):
            for calibration in ("raw", "cal"):
                probability = predictions[f"hot_{calibration}_{threshold_name}_{window}"].to_numpy()
                for bin_number in range(settings["reliability_bins"]):
                    selected = np.minimum((probability * settings["reliability_bins"]).astype(int), settings["reliability_bins"] - 1) == bin_number
                    reliability.append({**identity, "threshold": threshold_name, "features": window, "calibration": calibration, "bin": bin_number, "n": int(selected.sum()), "mean_probability": probability[selected].mean() if selected.any() else np.nan, "observed_fraction": truth[selected].mean() if selected.any() else np.nan, "brier_overall": np.mean((probability - truth) ** 2)})
        for fn_cost in settings["false_negative_costs"]:
            for abstention_cost in settings["abstention_costs"]:
                actions = {"reconstruct_all": np.where(available, hot.astype(int), 2), "all_unknown": np.full(len(truth), 2),
                           "all_hot": np.ones(len(truth), dtype=int), "all_cool": np.zeros(len(truth), dtype=int)}
                for arm in arms:
                    actions[f"magnitude_{arm}"] = np.where(predictions[f"admit_{arm}"], hot.astype(int), 2)
                for window in ("direct", "window"):
                    actions[f"cost_probability_{window}"] = D.cost_action(predictions[f"hot_cal_{threshold_name}_{window}"].to_numpy(), fn_cost, abstention_cost)
                baseline_loss = D.action_loss(actions["reconstruct_all"], truth, fn_cost, abstention_cost)
                for name, action in actions.items():
                    losses = D.action_loss(action, truth, fn_cost, abstention_cost)
                    lo, hi = interval(losses - baseline_loss, codes, weights, denominator)
                    costs.append({**identity, "threshold": threshold_name, "fn_cost": fn_cost, "abstention_cost": abstention_cost, "arm": name, "loss": losses.mean(),
                                  "difference_vs_all": (losses - baseline_loss).mean(), "difference_low": lo, "difference_high": hi, "counts_are_expectations": False, **D.action_counts(action, truth)})
                # Exact expectation of uniform rejection among available predictions at matched retention.
                for arm in arms:
                    retention = float(predictions[f"admit_{arm}"].sum() / available.sum()) if available.any() else 0
                    base_counts = D.action_counts(actions["reconstruct_all"], truth)
                    counts = {key: (value * retention if key in {"false_negative", "false_positive", "true_positive", "true_negative"} else value) for key, value in base_counts.items()}
                    counts["unknown"] = float(len(truth) - retention * available.sum())
                    expected = retention * baseline_loss + (1 - retention) * abstention_cost
                    lo, hi = interval(expected - baseline_loss, codes, weights, denominator)
                    costs.append({**identity, "threshold": threshold_name, "fn_cost": fn_cost, "abstention_cost": abstention_cost, "arm": f"random_matched_{arm}", "loss": expected.mean(), "difference_vs_all": (expected - baseline_loss).mean(), "difference_low": lo, "difference_high": hi, "counts_are_expectations": True, **counts})
    for name, rows in (("operating", operating), ("risk_retention", curves), ("contrasts", contrasts), ("decision_costs", costs), ("probability_reliability", reliability)):
        pd.DataFrame(rows).to_csv(destination / f"{name}.csv", index=False)
    print(f"[374] summarized {protocol} seed={seed}: {len(predictions)} candidates, {len(units)} groups", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], required=True)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()
    settings = json.loads(CONFIG.read_text())
    frame = load_cases(args.protocol)
    if not args.summarize_only:
        Parallel(n_jobs=args.workers)(delayed(fit_fold)(frame, args.protocol, seed, fold, settings) for seed in settings["fold_seeds"] for fold in range(5))
    for seed in settings["fold_seeds"]:
        summarize(frame, args.protocol, seed, settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
