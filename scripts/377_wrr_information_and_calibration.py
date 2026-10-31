#!/usr/bin/env python3
"""Matched donor removal, source adjustment and target calibration budgets."""
from __future__ import annotations

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
from datetime import datetime, timezone
import itertools
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_r3_common as C
from stream_recoverability.experiments.v19_revision import decision_baselines as D
from stream_recoverability.experiments.v19_revision.learning import (
    GENERIC, DIRECT_UNCERTAINTY, WINDOW_INFORMATION, group_roles, empirical_threshold, predict_score,
)
from stream_recoverability.experiments.v19_revision.risk import fixed_training_candidates, select_group_threshold

OUT = C.READY / "followup_20261021/information_calibration"


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def metrics(frame, admitted):
    return {"n_candidates": len(frame), "n_groups": frame.independence_group.nunique(), "accepted": int(admitted.sum()),
            "failures": int((admitted & frame.policy_bad.to_numpy()).sum()), "retention": float(admitted.mean()),
            "risk": float(frame.policy_bad.to_numpy()[admitted].mean()) if admitted.any() else np.nan}


def information_cell(original, reduced, target, seed, objective, window, settings):
    features = GENERIC + DIRECT_UNCERTAINTY + (WINDOW_INFORMATION if window else ())
    roles = group_roles(original.independence_group.to_numpy(), seed, 0)
    rows, predictions = [], []
    for fitting_information, fitting in (("original", original), ("no_donors", reduced)):
        role = fitting.independence_group.map(roles)
        train = fitting.loc[role.eq("train")]
        model = D.fit_matched(train, features, train.abserr_policy if objective == "quantile" else train.policy_bad.astype(int), objective=objective, seed=seed)
        train_score = D.predict_matched(model, train, features, objective=objective)
        candidates = fixed_training_candidates(train_score)
        for calibration_information, calibration_pool in (("original", original), ("no_donors", reduced)):
            calibration = calibration_pool.loc[calibration_pool.independence_group.map(roles).eq("calibration")]
            calibration_score = D.predict_matched(model, calibration, features, objective=objective)
            selected = empirical_threshold(calibration_score, calibration.policy_bad.to_numpy(), calibration.independence_group.to_numpy(), candidates,
                                           seed=seed, draws=2000, risk_cap=0.05, alpha=0.05)
            for population, evaluation in (("source_original", original.loc[original.independence_group.map(roles).eq("test")]),
                                            ("source_no_donors", reduced.loc[reduced.independence_group.map(roles).eq("test")]), ("Swiss_opened_test", target)):
                score = D.predict_matched(model, evaluation, features, objective=objective)
                admitted = score <= selected["threshold"]
                identity = {"seed": seed, "objective": objective, "window": window, "fitting_information": fitting_information,
                            "calibration_information": calibration_information, "population": population}
                rows.append({**identity, **metrics(evaluation, admitted)})
                block = evaluation[["network_id", "station_id", "year", "realization_id", "independence_group", "policy_bad"]].copy()
                for key, value in identity.items():
                    block[key] = value
                block["admitted"], block["score"] = admitted, score
                predictions.append(block)
    return rows, pd.concat(predictions, ignore_index=True)


def calibration_budgets(protocol, settings):
    transfer = C.RUN / "r3_09_frozen_transfer"
    head = next(row for row in json.loads((transfer / "head_bank.json").read_text())["heads"] if row["name"] == "uncertain_support"
                and row["protocol"] == protocol and row["scope"] == "documented_daily_mean" and row["regime"] == "source_only")
    model = joblib.load(head["model_path"])
    data = {}
    for role in ("calibration", "test"):
        frame = pd.read_parquet(C.RUN / "r3_08_external_recovery" / role / protocol / "admission/cofailure_0/cases.parquet")
        frame = frame.loc[frame.provider.eq("foen") & frame.statistic_class.eq("daily_mean")]
        if protocol == "strictly_prior_years":
            frame = frame.loc[frame.year.between(2019, 2022)]
        data[role] = (frame, predict_score(model["model"], frame, tuple(model["features"]), model["kind"]))
    calibration, score = data["calibration"]
    test, test_score = data["test"]
    units = sorted(calibration.independence_group.unique())
    candidates = np.asarray(head["candidates"])
    rows = []
    for n in sorted(set([1, min(3, len(units)), min(5, len(units)), len(units)])):
        choices = list(itertools.combinations(units, n))
        if len(choices) > 30:
            indices = np.random.default_rng(20261021 + n).choice(len(choices), 30, replace=False)
            choices = [choices[i] for i in indices]
        for repetition, selected_units in enumerate(choices):
            mask = calibration.independence_group.isin(selected_units).to_numpy()
            selected = empirical_threshold(score[mask], calibration.policy_bad.to_numpy()[mask], calibration.independence_group.to_numpy()[mask], candidates,
                                           seed=20261021, draws=2000, risk_cap=0.05, alpha=0.05)
            formal = select_group_threshold(score[mask], calibration.policy_bad.to_numpy()[mask], calibration.independence_group.to_numpy()[mask], candidates)
            for mode, threshold in (("empirical", selected["threshold"]), ("formal", formal.threshold)):
                rows.append({"protocol": protocol, "n_calibration_groups": n, "repetition": repetition, "calibration_groups": ";".join(selected_units),
                             "n_calibration_cases": int(mask.sum()), "selection": mode, **metrics(test, test_score <= threshold),
                             "interpretation": "opened-target descriptive budget sensitivity; independent groups cannot be replaced by masks"})
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], required=True)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    settings = json.loads((C.ROOT / "configs/wrr_followup_20261021.json").read_text())
    output = OUT / args.protocol
    output.mkdir(parents=True, exist_ok=True)
    original_path = C.source_cases(args.protocol)
    reduced_path = C.READY / "followup_20261021/transfer" / args.protocol / "source_no_donors/cases.parquet"
    original, reduced = (pd.read_parquet(path) for path in (original_path, reduced_path))
    group_map = pd.read_csv(C.RUN / "r3_06_independence_risk/complete_network_independence.csv").set_index("network_id").independence_group
    def prepare(frame):
        frame = frame.loc[frame.statistic_class.isin(["daily_mean", "documented_daily_mean"])].copy()
        frame["independence_group"] = frame.network_id.map(group_map)
        return frame
    original, reduced = prepare(original), prepare(reduced)
    target_path = C.RUN / "r3_08_external_recovery/test" / args.protocol / "admission/cofailure_0/cases.parquet"
    target = pd.read_parquet(target_path)
    target = target.loc[target.provider.eq("foen") & target.statistic_class.eq("daily_mean")]
    if args.protocol == "strictly_prior_years":
        target = target.loc[target.year.between(2019, 2022)]
    results = Parallel(n_jobs=args.workers)(delayed(information_cell)(original, reduced, target, seed, objective, window, settings)
                                           for seed in settings["fold_seeds"] for objective in settings["objectives"] for window in settings["windows"])
    pd.DataFrame([row for result, _ in results for row in result]).to_csv(output / "information_operating.csv", index=False)
    pd.concat([result for _, result in results], ignore_index=True).to_parquet(output / "information_predictions.parquet", index=False)
    calibration_budgets(args.protocol, settings).to_csv(output / "calibration_budgets.csv", index=False)
    C.write_json(output / "run_record.json", run_record({"original": original_path, "reduced": reduced_path, "target": target_path}, new_confirmation=False, information_intervention_preserves_masks=True, source_roles="one 60/20/20 split per seed", prospective_scope="earlier local histories; global-head calendar not restricted"))
    print(f"[377] {args.protocol}: matched information and calibration budgets complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
