#!/usr/bin/env python3
"""Refit each reconstruction's own error head, admission and use decision."""
from __future__ import annotations

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_r3_common as C
from stream_recoverability.experiments.v19_revision import decision_baselines as D
from stream_recoverability.experiments.v19_revision.learning import GENERIC, WINDOW_INFORMATION, empirical_threshold
from stream_recoverability.experiments.v19_revision.risk import fixed_training_candidates, select_group_threshold

OUT = C.READY / "followup_20261021/system_factorial"
KEYS = ["network_id", "station_id", "year", "realization_id"]
FEATURES = tuple(name for name in GENERIC if name != "estimator_disagreement") + ("reconstruction_point", "threshold_margin_C")


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def role_cases(role):
    source = C.RUN / "r3_08_external_recovery" / role / "leave_one_year_out/crossed/cofailure_0/cases.parquet"
    base = pd.read_parquet(source)
    base = base.loc[base.replicate.eq(0) & base.design_family.eq("crossed_contiguous") & base.statistic_class.eq("daily_mean")].copy()
    values = {"priority": base[KEYS].assign(reconstruction_point=base.policy_metric)}
    process = pd.read_parquet(C.RUN / "r3_12_process_reference" / role / "leave_one_year_out/cases.parquet")
    for method in ("air2stream3", "air2stream8"):
        values[method] = process.loc[process.method.eq(method) & process.status.eq("available"), KEYS + ["h30_reconstructed"]].rename(columns={"h30_reconstructed": "reconstruction_point"})
    probabilistic = pd.read_parquet(C.RUN / "r3_11_probabilistic_reference" / f"external_{role}_cases.parquet")
    values["csdi_fixed8"] = probabilistic.loc[probabilistic.available, KEYS + ["h30_pointwise_median_series"]].rename(columns={"h30_pointwise_median_series": "reconstruction_point"})
    trajectory = pd.read_parquet(C.READY / "followup_20261021/trajectory/leave_one_year_out" / role / "cases.parquet")
    trajectory = trajectory.loc[trajectory.n_draws.eq(128) & trajectory.status.eq("available")]
    for variant in ("raw_block14", "visible_adjustment", "seasonal_state_slow_short"):
        values[variant] = trajectory.loc[trajectory.variant.eq(variant), KEYS + ["h30_point"]].rename(columns={"h30_point": "reconstruction_point"})
    return base, values


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    roles = {role: role_cases(role) for role in ("development", "calibration", "test")}
    # Comparisons distinguish input tiers; no common complete-case intersection across tiers.
    tables = {
        "air_common": ["priority", "air2stream3", "csdi_fixed8"],
        "air_flow_common": ["priority", "air2stream8", "seasonal_state_slow_short", "raw_block14", "visible_adjustment"],
    }
    operating, costs, availability = [], [], []
    original_operating, original_costs = [], []
    predictions = []
    for tier, methods in tables.items():
        datasets = {method: {} for method in methods}
        for role, (base, values) in roles.items():
            common = base[KEYS]
            for method in methods:
                valid = values[method].loc[np.isfinite(values[method].reconstruction_point), KEYS]
                common = common.merge(valid, on=KEYS, validate="one_to_one")
            for method in methods:
                data = base.merge(common, on=KEYS, validate="one_to_one").merge(values[method], on=KEYS, validate="one_to_one")
                data["threshold_margin_C"] = data.reconstruction_point - data.local_hot_threshold_C
                data["own_error"] = np.abs(data.reconstruction_point - data.truth_hottest30)
                data["own_failure"] = data.own_error > 0.5
                datasets[method][role] = data
                availability.append({"tier": tier, "role": role, "method": method, "original_candidates": len(base), "supported_by_method": len(base[KEYS].merge(values[method], on=KEYS)), "common_candidates": len(data), "groups": data.independence_group.nunique()})
        for method, data in datasets.items():
            train, calibration, test = (data[role] for role in ("development", "calibration", "test"))
            if set(train.independence_group) & (set(calibration.independence_group) | set(test.independence_group)) or set(calibration.independence_group) & set(test.independence_group):
                raise RuntimeError("Reference pipeline has group leakage")
            truth = (test.truth_hottest30 > test.local_hot_threshold_C).to_numpy()
            point_hot = (test.reconstruction_point > test.local_hot_threshold_C).to_numpy().astype(int)
            for window in (False, True):
                features = FEATURES + (WINDOW_INFORMATION if window else ())
                # All methods receive the same common-reconstruction window diagnostics.
                # No model is given another model's direct uncertainty as its own.
                risk_model = D.fit_matched(train, features, train.own_failure.astype(int), objective="probability", seed=20261021)
                train_score, cal_score, score = [D.predict_matched(risk_model, block, features, objective="probability") for block in (train, calibration, test)]
                candidates = fixed_training_candidates(train_score)
                selected = empirical_threshold(cal_score, calibration.own_failure.to_numpy(), calibration.independence_group.to_numpy(), candidates, seed=20261021, draws=2000)
                formal = select_group_threshold(cal_score, calibration.own_failure.to_numpy(), calibration.independence_group.to_numpy(), candidates)
                admit = score <= selected["threshold"]
                identity = {"tier": tier, "method": method, "window": window, "n_candidates": len(test), "n_groups": test.independence_group.nunique()}
                operating.append({**identity, "mae_C": test.own_error.mean(), "retention": admit.mean(), "accepted": int(admit.sum()), "failures": int((admit & test.own_failure.to_numpy()).sum()),
                                  "risk": test.own_failure.to_numpy()[admit].mean() if admit.any() else np.nan,
                                  "formal_accepted": int((score <= formal.threshold).sum()), "formal_status": formal.status})
                hot_model = D.fit_matched(train, features, (train.truth_hottest30 > train.local_hot_threshold_C).astype(int), objective="probability", seed=20261021)
                cal_p, test_p = [D.predict_matched(hot_model, block, features, objective="probability") for block in (calibration, test)]
                probability = D.probability_calibration(cal_p, calibration.truth_hottest30 > calibration.local_hot_threshold_C, test_p)
                # Also evaluate every original controlled candidate, keeping unavailable
                # reconstructions as unknown instead of silently restricting utility.
                original_base, original_values = roles["test"]
                original_test = original_base.merge(original_values[method], on=KEYS, how="left", validate="one_to_one")
                original_test["threshold_margin_C"] = original_test.reconstruction_point - original_test.local_hot_threshold_C
                supported = np.isfinite(original_test.reconstruction_point.to_numpy())
                original_admit = np.zeros(len(original_test), dtype=bool)
                original_probability = np.full(len(original_test), np.nan)
                original_admit[supported] = D.predict_matched(risk_model, original_test.loc[supported], features, objective="probability") <= selected["threshold"]
                original_raw_p = D.predict_matched(hot_model, original_test.loc[supported], features, objective="probability")
                original_probability[supported] = D.probability_calibration(cal_p, calibration.truth_hottest30 > calibration.local_hot_threshold_C, original_raw_p)
                original_truth = (original_test.truth_hottest30 > original_test.local_hot_threshold_C).to_numpy()
                original_hot = (original_test.reconstruction_point > original_test.local_hot_threshold_C).to_numpy().astype(int)
                original_error = np.abs(original_test.reconstruction_point.to_numpy() - original_test.truth_hottest30.to_numpy())
                original_failure = ~supported | (original_error > 0.5)
                original_identity = {"tier": tier, "method": method, "window": window, "n_candidates": len(original_test), "n_groups": original_test.independence_group.nunique()}
                original_operating.append({**original_identity, "n_available": int(supported.sum()), "n_unavailable": int((~supported).sum()),
                                           "mae_on_available_C": original_error[supported].mean() if supported.any() else np.nan,
                                           "accepted": int(original_admit.sum()), "failures": int((original_admit & original_failure).sum()),
                                           "retention": original_admit.mean(), "risk": original_failure[original_admit].mean() if original_admit.any() else np.nan,
                                           "training_and_calibration": "same matched development/calibration subset as tier comparison"})
                saved = test[KEYS + ["independence_group", "reconstruction_point", "truth_hottest30"]].copy()
                saved["admitted"], saved["failure"], saved["hot_probability"] = admit, test.own_failure.to_numpy(), probability
                for key, value in identity.items():
                    saved[key] = value
                predictions.append(saved)
                for fn_cost in (1, 5, 10):
                    for abstention_cost in (0, 0.01, 0.025, 0.05, 0.1, 0.25):
                        actions = {"reconstruct_all": point_hot, "magnitude_screen": np.where(admit, point_hot, 2),
                                   "direct_cost": D.cost_action(probability, fn_cost, abstention_cost),
                                   "all_unknown": np.full(len(test), 2), "all_hot": np.ones(len(test), dtype=int), "all_cool": np.zeros(len(test), dtype=int)}
                        for policy, action in actions.items():
                            costs.append({**identity, "policy": policy, "fn_cost": fn_cost, "abstention_cost": abstention_cost,
                                          "loss": D.action_loss(action, truth, fn_cost, abstention_cost).mean(), **D.action_counts(action, truth)})
                        original_direct = np.full(len(original_test), 2)
                        original_direct[supported] = D.cost_action(original_probability[supported], fn_cost, abstention_cost)
                        original_actions = {"reconstruct_all": np.where(supported, original_hot, 2), "magnitude_screen": np.where(original_admit, original_hot, 2),
                                            "direct_cost": original_direct, "all_unknown": np.full(len(original_test), 2),
                                            "all_hot": np.ones(len(original_test), dtype=int), "all_cool": np.zeros(len(original_test), dtype=int)}
                        for policy, action in original_actions.items():
                            original_costs.append({**original_identity, "policy": policy, "fn_cost": fn_cost, "abstention_cost": abstention_cost,
                                                   "loss": D.action_loss(action, original_truth, fn_cost, abstention_cost).mean(), **D.action_counts(action, original_truth)})
                        original_retention = original_admit.sum() / supported.sum() if supported.any() else 0
                        original_base_counts = D.action_counts(original_actions["reconstruct_all"], original_truth)
                        original_random = {key: value * original_retention if key in {"true_positive", "true_negative", "false_positive", "false_negative"} else value for key, value in original_base_counts.items()}
                        original_random["unknown"] = int((~original_admit).sum())
                        original_base_loss = D.action_loss(original_actions["reconstruct_all"], original_truth, fn_cost, abstention_cost)
                        original_costs.append({**original_identity, "policy": "random_matched_screen", "fn_cost": fn_cost, "abstention_cost": abstention_cost,
                                               "loss": (original_retention * original_base_loss + (1 - original_retention) * abstention_cost).mean(),
                                               "counts_are_expectations": True, **original_random})
                        base_loss = D.action_loss(point_hot, truth, fn_cost, abstention_cost)
                        costs.append({**identity, "policy": "random_matched_screen", "fn_cost": fn_cost, "abstention_cost": abstention_cost,
                                      "loss": (admit.mean() * base_loss + (1 - admit.mean()) * abstention_cost).mean(),
                                      "counts_are_expectations": True, "n_candidates": len(test), "unknown": int((~admit).sum()),
                                      "false_negative": float(admit.mean() * ((point_hot == 0) & truth).sum()), "false_positive": float(admit.mean() * ((point_hot == 1) & ~truth).sum())})
    for name, rows in (("operating", operating), ("decision_costs", costs), ("availability", availability),
                       ("original_pool_operating", original_operating), ("original_pool_costs", original_costs)):
        pd.DataFrame(rows).to_csv(OUT / f"{name}.csv", index=False)
    pd.concat(predictions, ignore_index=True).to_parquet(OUT / "test_predictions.parquet", index=False)
    inputs = {"decision_implementation": C.ROOT / "src/stream_recoverability/experiments/v19_revision/decision_baselines.py"}
    for role in roles:
        inputs[f"base_{role}"] = C.RUN / "r3_08_external_recovery" / role / "leave_one_year_out/crossed/cofailure_0/cases.parquet"
        inputs[f"process_{role}"] = C.RUN / "r3_12_process_reference" / role / "leave_one_year_out/cases.parquet"
        inputs[f"csdi_{role}"] = C.RUN / "r3_11_probabilistic_reference" / f"external_{role}_cases.parquet"
        inputs[f"trajectory_{role}"] = C.READY / "followup_20261021/trajectory/leave_one_year_out" / role / "cases.parquet"
    C.write_json(OUT / "run_record.json", run_record(inputs, new_confirmation=False, scope="retrospective Swiss opened data; own error refitting; shared window information", model_development_budget="CSDI fixed eight-draw reference retains original limitations; not a probabilistic SOTA claim"))
    print("[379] reconstruction, admission and direct-cost factorial complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
