#!/usr/bin/env python3
"""Evaluate the complete candidate pool, paired admission contrasts and decision utility."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_r3_common as C

from stream_recoverability.experiments.v17_fitness.paths import stable_seed

OUT = C.RUN / "r3_07_decision_report"


def pooled_metrics(frame: pd.DataFrame, admitted: np.ndarray) -> dict:
    admitted = np.asarray(admitted, dtype=bool)
    failures = frame.policy_bad.to_numpy(dtype=bool)
    available = np.isfinite(frame.policy_metric.to_numpy(dtype=float))
    admitted = admitted & available
    n_admitted = int(admitted.sum())
    groups = frame.independence_group.astype(str)
    temporary = pd.DataFrame({"group": groups, "admit": admitted.astype(float), "bad_admit": admitted * failures})
    grouped = temporary.groupby("group").mean()
    group_rates = grouped.bad_admit / grouped.admit.replace(0, np.nan)
    station_year = frame.provider.astype(str) + "|" + frame.station_id.astype(str) + "|" + frame.year.astype(str)
    counts = station_year.map(station_year.value_counts()).to_numpy(dtype=float)
    weights = 1 / counts
    denominator = float(weights[admitted].sum())
    return {
        "n_candidates": len(frame), "n_admitted": n_admitted,
        "n_abstained": int((~admitted).sum()), "n_unavailable": int((~available).sum()),
        "n_failed_among_admitted": int((admitted * failures).sum()),
        "retention": float(admitted.mean()),
        "risk_among_admitted": float(failures[admitted].mean()) if n_admitted else np.nan,
        "failure_and_admission_fraction": float((admitted * failures).mean()),
        "equal_group_retention": float(grouped.admit.mean()),
        "equal_group_selected_risk_ratio": float(grouped.bad_admit.mean() / grouped.admit.mean()) if grouped.admit.mean() else np.nan,
        "mean_group_conditional_risk": float(group_rates.mean()) if group_rates.notna().any() else np.nan,
        "n_groups_with_admissions": int((grouped.admit > 0).sum()),
        "n_groups_sample_risk_above_5pct": int((group_rates > 0.05).sum()),
        "station_year_weighted_retention": float(weights[admitted].sum() / weights.sum()),
        "station_year_weighted_risk": float(weights[admitted & failures].sum() / denominator) if denominator else np.nan,
    }


def paired_retention(frame: pd.DataFrame, left: np.ndarray, right: np.ndarray, *, seed: int, draws: int) -> dict:
    group = frame.independence_group.astype(str).to_numpy()
    units, codes = np.unique(group, return_inverse=True)
    total = np.bincount(codes, minlength=len(units))
    difference = np.asarray(left, dtype=float) - np.asarray(right, dtype=float)
    numerator = np.bincount(codes, weights=difference, minlength=len(units))
    rng = np.random.default_rng(seed)
    weights = rng.multinomial(len(units), np.full(len(units), 1 / len(units)), size=draws)
    bootstrap = (weights @ numerator) / (weights @ total)
    lower, upper = np.quantile(bootstrap, [0.025, 0.975])
    return {"difference": float(difference.mean()), "ci_low": float(lower), "ci_high": float(upper), "n_independent_groups": len(units), "uncertainty_scope": "conditional on fitted models and calibrated thresholds"}


def confusion(frame: pd.DataFrame, admitted: np.ndarray, threshold: np.ndarray, predicted_hot_override: np.ndarray | None = None) -> dict:
    truth_hot = frame.truth_hottest30.to_numpy() > threshold
    prediction = frame.policy_metric.to_numpy()
    admitted = np.asarray(admitted, dtype=bool)
    if predicted_hot_override is None:
        admitted = admitted & np.isfinite(prediction)
    predicted_hot = prediction > threshold if predicted_hot_override is None else np.asarray(predicted_hot_override, dtype=bool)
    near_threshold = np.abs(frame.truth_hottest30.to_numpy() - threshold) <= 0.5
    false_negative = admitted & truth_hot & ~predicted_hot
    false_positive = admitted & ~truth_hot & predicted_hot
    return {
        "n": len(frame), "true_hot": int(truth_hot.sum()), "true_cool": int((~truth_hot).sum()),
        "true_positive": int((admitted & truth_hot & predicted_hot).sum()),
        "true_negative": int((admitted & ~truth_hot & ~predicted_hot).sum()),
        "false_negative": int(false_negative.sum()), "false_positive": int(false_positive.sum()),
        "abstained": int((~admitted).sum()),
        "abstained_hot": int((~admitted & truth_hot).sum()), "abstained_cool": int((~admitted & ~truth_hot).sum()),
        "hot_refusal_rate": float((~admitted & truth_hot).sum() / truth_hot.sum()) if truth_hot.any() else np.nan,
        "cool_refusal_rate": float((~admitted & ~truth_hot).sum() / (~truth_hot).sum()) if (~truth_hot).any() else np.nan,
        "overall_refusal_rate": float((~admitted).mean()),
        "truth_hot_fraction": float(truth_hot.mean()),
        "admitted_hot_fraction": float(predicted_hot[admitted].mean()) if admitted.any() else np.nan,
        "retained_truth_hot_fraction": float(truth_hot[admitted].mean()) if admitted.any() else np.nan,
        "selected_frequency_error": float(predicted_hot[admitted].mean() - truth_hot.mean()) if admitted.any() else np.nan,
        "original_pool_hot_frequency_lower": float((admitted & predicted_hot).mean()),
        "original_pool_hot_frequency_upper": float(((admitted & predicted_hot) | ~admitted).mean()),
        "near_threshold_candidates": int(near_threshold.sum()),
        "near_threshold_errors": int(((false_negative | false_positive) & near_threshold).sum()),
        "near_threshold_abstentions": int((~admitted & near_threshold).sum()),
        "network_coverage": float(frame.loc[admitted, "network_id"].nunique() / frame.network_id.nunique()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", default="leave_one_year_out", choices=["leave_one_year_out", "strictly_prior_years"])
    parser.add_argument("--measurement-scope", default="documented_daily_mean", choices=["documented_daily_mean", "all"])
    parser.add_argument("--cohort", choices=["admission", "controlled"], default="admission")
    args = parser.parse_args()
    settings = C.protocol()
    source = C.source_cases(args.protocol, args.cohort)
    scores_dir = C.RUN / "r3_04_uncertainty_ablation" / args.cohort / args.protocol / args.measurement_scope
    finished = scores_dir / "completed_scores.json"
    if not finished.exists():
        raise RuntimeError("Complete the corresponding ablation before evaluating its outcomes")
    score_records = json.loads(finished.read_text())["scores"]
    data = pd.read_parquet(source)
    data["event_overlap"] = np.where(data.n_hidden_event_days > 0, "gap_intersects_event", "gap_does_not_intersect_event")
    data["local_threshold_margin"] = np.where(np.abs(data.truth_hottest30 - data.local_hot_threshold_C) <= settings["tolerance_c"], "near", "far")
    group_map_path = C.RUN / "r3_06_independence_risk/complete_network_independence.csv"
    group_map = pd.read_csv(group_map_path).set_index("network_id").independence_group
    data["independence_group"] = data.network_id.map(group_map)
    output = OUT / args.cohort / args.protocol / args.measurement_scope
    output.mkdir(parents=True, exist_ok=True)
    operating, utility, stratified, group_rows, contrasts = [], [], [], [], []
    all_admissions = {}
    reference_frame = None
    for record in score_records:
        name, seed = record["name"], record["fold_seed"]
        if record["input_sha256"] != C.digest(source):
            raise RuntimeError("A score belongs to a different recovery case table")
        saved = np.load(scores_dir / f"{name}_{seed}.npz")
        frame = data.loc[saved["case_row"]].reset_index(drop=True)
        if reference_frame is None:
            reference_frame = frame
        elif not frame[["network_id", "station_id", "year", "realization_id"]].equals(reference_frame[["network_id", "station_id", "year", "realization_id"]]):
            raise RuntimeError("Score arms do not judge an identical candidate pool")
        for protocol_name in ("empirical", "certified", "fixed70"):
            admitted = saved[f"admit_{protocol_name}"]
            all_admissions[(name, seed, protocol_name)] = admitted
            operating.append({"arm": name, "fold_seed": seed, "selection": protocol_name, **pooled_metrics(frame, admitted)})
            if protocol_name != "empirical":
                continue
            for dimension in ["provider", "design_family", "warm_anomaly", "regulation_status", "policy_choice", "event_overlap", "local_threshold_margin"]:
                for value, indices in frame.groupby(dimension).groups.items():
                    indices = np.asarray(list(indices), dtype=int)
                    stratified.append({"arm": name, "fold_seed": seed, "stratum_type": dimension, "stratum": value, **pooled_metrics(frame.iloc[indices], admitted[indices])})
            for group, indices in frame.groupby("independence_group").groups.items():
                indices = np.asarray(list(indices), dtype=int)
                group_rows.append({"arm": name, "fold_seed": seed, "group": group, **pooled_metrics(frame.iloc[indices], admitted[indices])})
    if reference_frame is None:
        raise RuntimeError("No completed score results")
    frame = reference_frame
    available = np.isfinite(frame.policy_metric.to_numpy())
    baselines = {"reconstruct_all": available, "published_length_49": available & (frame.longest_run.to_numpy() <= 49), "published_imputed_length_140": available & (frame.longest_run.to_numpy() <= 140)}
    for name, admitted in baselines.items():
        operating.append({"arm": name, "fold_seed": 0, "selection": "fixed_rule", **pooled_metrics(frame, admitted)})
    thresholds = {"local_training_q90": frame.local_hot_threshold_C.to_numpy(), "fixed18": np.full(len(frame), 18.0), "fixed20": np.full(len(frame), 20.0)}
    decision_arms = [(name, seed, admitted, None) for (name, seed, selected), admitted in all_admissions.items() if selected == "empirical"] + [(name, 0, admitted, None) for name, admitted in baselines.items()]
    for threshold_name, threshold in thresholds.items():
        baseline_confusion = confusion(frame, available, threshold)
        lower, upper = frame.h30_interval_lower_C.to_numpy(), frame.h30_interval_upper_C.to_numpy()
        interval_admission = available & np.isfinite(lower) & np.isfinite(upper) & ((upper <= threshold) | (lower > threshold))
        threshold_arms = decision_arms + [("uncalibrated_scenario_interval", 0, interval_admission, lower > threshold)]
        for name, seed, admitted, predicted_hot in threshold_arms:
            counts = confusion(frame, admitted, threshold, predicted_hot)
            for false_negative_cost in settings["false_negative_costs"]:
                no_abstention_loss = false_negative_cost * counts["false_negative"] + counts["false_positive"]
                reconstruct_loss = false_negative_cost * baseline_confusion["false_negative"] + baseline_confusion["false_positive"]
                extra_abstentions = counts["abstained"] - baseline_confusion["abstained"]
                break_even = (reconstruct_loss - no_abstention_loss) / extra_abstentions if extra_abstentions else np.nan
                for abstention_cost in settings["abstention_costs"]:
                    loss = (no_abstention_loss + abstention_cost * counts["abstained"]) / len(frame)
                    reference_loss = (reconstruct_loss + abstention_cost * baseline_confusion["abstained"]) / len(frame)
                    utility.append({"arm": name, "fold_seed": seed, "threshold_definition": threshold_name, "false_negative_cost": false_negative_cost, "abstention_cost": abstention_cost, "loss_per_original_candidate": loss, "reconstruct_all_loss": reference_loss, "loss_difference_vs_reconstruct_all": loss - reference_loss, "break_even_abstention_cost": break_even, **counts})
    required = [
        ("uncertain_support", "generic_target_disagreement"),
        ("uncertain_support", "generic_direct_h30_uncertainty"),
        ("uncertain_support", "certificate"),
        ("uncertain_support", "policy_certificate"),
        ("uncertain_support", "complete_diagnostic_model"),
        ("uncertain_support", "historical_h30_error_rule"),
        ("uncertain_support", "generic_both_diagnostics"),
        ("generic_direct_h30_uncertainty", "generic_both_diagnostics"),
        ("generic_both_diagnostics", "generic_target_disagreement"),
        ("uncertain_support", "uncertain_support_no_competition"),
        ("uncertain_support", "uncertain_support_no_window_uncertainty"),
        ("uncertain_support", "uncertain_support_no_donor_features"),
        ("generic_target_disagreement", "generic_daily_disagreement"),
        ("generic_plus_climatological_support", "generic_target_disagreement"),
        ("small_logit_plus_support", "small_logit"),
        ("season_spline_plus_support", "season_spline"),
    ]
    for seed in settings["fold_seeds"]:
        for left, right in required:
            left_key, right_key = (left, seed, "empirical"), (right, seed, "empirical")
            if left_key not in all_admissions or right_key not in all_admissions:
                continue
            contrast = paired_retention(frame, all_admissions[left_key], all_admissions[right_key], seed=stable_seed("r3-contrast", seed, left, right), draws=settings["bootstrap_draws"])
            contrasts.append({"left": left, "right": right, "fold_seed": seed, **contrast, "exceeds_five_point_estimate": contrast["difference"] > settings["superiority_margin_retention"], "five_point_margin_supported_by_interval": contrast["ci_low"] > settings["superiority_margin_retention"], "interval_inside_two_point_equivalence_margin": contrast["ci_low"] > -settings["equivalence_margin_retention"] and contrast["ci_high"] < settings["equivalence_margin_retention"]})
    for name, rows in [("operating_points", operating), ("paired_contrasts", contrasts), ("stratum_results", stratified), ("group_results", group_rows), ("decision_costs", utility)]:
        pd.DataFrame(rows).to_csv(output / f"{name}.csv", index=False)
    primary = [row for row in contrasts if row["left"] == "uncertain_support" and row["right"] == settings["primary_comparator"]]
    C.write_json(output / "summary.json", {"cohort": args.cohort, "n_candidates": len(frame), "n_groups": frame.independence_group.nunique(), "protocol": args.protocol, "measurement_scope": args.measurement_scope, "primary_h2_contrasts": primary, "formal_and_empirical_risk_are_distinct": True, "reported_confidence_intervals_include_training_variability": False, "new_external_validation": False})
    C.write_json(output / "protocol_fingerprint.json", C.fingerprint(Path(__file__), {"cases": source, "scores": finished, "group_map": group_map_path}))
    print(f"[357] {len(operating)} operating points and {len(utility)} original-pool cost scenarios", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
