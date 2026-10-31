#!/usr/bin/env python3
"""Use-matched hot-probability comparison on the original Swiss candidate pool."""
from __future__ import annotations

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import wrr_r3_common as C
from stream_recoverability.experiments.v19_revision import decision_baselines as D
from stream_recoverability.experiments.v19_revision.learning import GENERIC, DIRECT_UNCERTAINTY, WINDOW_INFORMATION, group_roles, predict_score

OUT = C.READY / "followup_20261021/external_cost"


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], required=True)
    args = parser.parse_args()
    protocol = args.protocol
    source_path = C.source_cases(protocol)
    source = pd.read_parquet(source_path)
    source = source.loc[source.statistic_class.isin(["daily_mean", "documented_daily_mean"])].copy()
    groups = pd.read_csv(C.RUN / "r3_06_independence_risk/complete_network_independence.csv").set_index("network_id").independence_group
    source["independence_group"] = source.network_id.map(groups)
    if protocol == "strictly_prior_years":
        source = source.loc[source.year <= 2018]
    roles = group_roles(source.independence_group.to_numpy(), 20261020, 0)
    train, calibration = source.loc[~source.independence_group.map(roles).eq("calibration")].copy(), source.loc[source.independence_group.map(roles).eq("calibration")].copy()
    target = {}
    paths = {"source": source_path}
    for role in ("calibration", "test"):
        path = C.RUN / "r3_08_external_recovery" / role / protocol / "admission/cofailure_0/cases.parquet"
        paths[f"target_{role}"] = path
        frame = pd.read_parquet(path)
        frame = frame.loc[frame.provider.eq("foen") & frame.statistic_class.eq("daily_mean")].copy()
        if protocol == "strictly_prior_years":
            frame = frame.loc[frame.year.between(2019, 2022)].copy()
        target[role] = frame
    test = target["test"]
    transfer = C.RUN / "r3_09_frozen_transfer"
    head = next(row for row in json.loads((transfer / "head_bank.json").read_text())["heads"] if row["name"] == "uncertain_support" and row["protocol"] == protocol and row["regime"] == "source_only" and row["scope"] == "documented_daily_mean")
    paths["frozen_head"] = Path(head["model_path"])
    frozen = joblib.load(head["model_path"])
    score = predict_score(frozen["model"], test, tuple(frozen["features"]), frozen["kind"])
    admitted = score <= head["source_thresholds"]["empirical"]
    units, codes = np.unique(test.independence_group.astype(str), return_inverse=True)
    weights = np.random.default_rng(20261021).multinomial(len(units), np.full(len(units), 1 / len(units)), size=2000)
    denominator = weights @ np.bincount(codes, minlength=len(units))
    output = OUT / protocol
    output.mkdir(parents=True, exist_ok=True)
    rows, reliable, saved = [], [], []
    for threshold_name in ("local_training_q90", "fixed18", "fixed20"):
        threshold = lambda block: block.local_hot_threshold_C.to_numpy() if threshold_name == "local_training_q90" else np.full(len(block), float(threshold_name[5:]))
        truth = test.truth_hottest30.to_numpy() > threshold(test)
        point_hot = test.policy_metric.to_numpy() > threshold(test)
        probabilities = {}
        for window in (False, True):
            features = GENERIC + DIRECT_UNCERTAINTY + (WINDOW_INFORMATION if window else ()) + ("policy_metric", "threshold_margin_C")
            for block in (train, calibration, target["calibration"], test):
                block["threshold_margin_C"] = block.policy_metric.to_numpy() - threshold(block)
            model = D.fit_matched(train, features, train.truth_hottest30.to_numpy() > threshold(train), objective="probability", seed=20261021)
            raw = D.predict_matched(model, test, features, objective="probability")
            for cal_name, cal_frame in (("source", calibration), ("local", target["calibration"])):
                cal_p = D.predict_matched(model, cal_frame, features, objective="probability")
                p = D.probability_calibration(cal_p, cal_frame.truth_hottest30.to_numpy() > threshold(cal_frame), raw)
                name = f"direct_cost_{cal_name}_{'window' if window else 'direct'}"
                probabilities[name] = p
                reliable.append({"threshold": threshold_name, "arm": name, "brier": np.mean((p - truth) ** 2), "n_candidates": len(test)})
                case = test[["network_id", "station_id", "year", "realization_id", "independence_group"]].copy()
                case["threshold"], case["arm"], case["probability"], case["truth_hot"] = threshold_name, name, p, truth
                saved.append(case)
        for fn_cost in (1, 5, 10):
            for abstention_cost in (0, 0.01, 0.025, 0.05, 0.1, 0.25):
                actions = {"reconstruct_all": point_hot.astype(int), "frozen_magnitude_screen": np.where(admitted, point_hot.astype(int), 2),
                           "all_unknown": np.full(len(test), 2), "all_hot": np.ones(len(test), dtype=int), "all_cool": np.zeros(len(test), dtype=int)}
                for name, probability in probabilities.items():
                    actions[name] = D.cost_action(probability, fn_cost, abstention_cost)
                base_loss = D.action_loss(actions["reconstruct_all"], truth, fn_cost, abstention_cost)
                for name, action in actions.items():
                    loss = D.action_loss(action, truth, fn_cost, abstention_cost)
                    grouped = np.bincount(codes, weights=loss - base_loss, minlength=len(units))
                    lo, hi = np.quantile((weights @ grouped) / denominator, [0.025, 0.975])
                    rows.append({"protocol": protocol, "threshold": threshold_name, "fn_cost": fn_cost, "abstention_cost": abstention_cost, "arm": name,
                                 "loss": loss.mean(), "difference_vs_all": (loss - base_loss).mean(), "difference_low": lo, "difference_high": hi,
                                 "counts_are_expectations": False, **D.action_counts(action, truth)})
                retention = admitted.mean()
                counts = D.action_counts(actions["reconstruct_all"], truth)
                for key in ("false_negative", "false_positive", "true_positive", "true_negative"):
                    counts[key] *= retention
                counts["unknown"] = int((~admitted).sum())
                expected = retention * base_loss + (1 - retention) * abstention_cost
                rows.append({"protocol": protocol, "threshold": threshold_name, "fn_cost": fn_cost, "abstention_cost": abstention_cost, "arm": "random_matched_screen", "loss": expected.mean(), "difference_vs_all": (expected - base_loss).mean(), "counts_are_expectations": True, **counts})
    pd.DataFrame(rows).to_csv(output / "decision_costs.csv", index=False)
    pd.DataFrame(reliable).to_csv(output / "probability_quality.csv", index=False)
    pd.concat(saved, ignore_index=True).to_parquet(output / "probabilities.parquet", index=False)
    C.write_json(output / "run_record.json", run_record(paths, supplementary_after_opening_test=True, original_frozen_screen_unchanged=True, hot_model_training="same original 80/20 source group roles; forward source targets through 2018", uncertainty="conditional group bootstrap; not simultaneous cost-grid inference"))
    print(f"[381] {protocol}: all decision references on {len(test)} original candidates", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
