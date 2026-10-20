#!/usr/bin/env python3
"""Fit source and local heads, then freeze all choices before external testing."""

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
from stream_recoverability.experiments.v19_revision.learning import certificate_delivery, empirical_threshold, fit_score, group_roles, predict_score, specifications
from stream_recoverability.experiments.v19_revision.risk import fixed_training_candidates, select_group_threshold

OUT = C.RUN / "r3_09_frozen_transfer"
SPECS = specifications()
SPECS["certificate_joint"] = (SPECS["certificate"][0], "certificate_joint")
RULES = {"length_rule": "longest_run", "peak_overlap_rule": "peak_overlap", "warm_coverage_rule": "warm_observed_fraction", "probabilistic_support_rule": "probabilistic_hidden_support", "upper_support_rule": "hidden_support_upper90", "direct_h30_uncertainty": "direct_h30_uncertainty", "daily_disagreement_rule": "daily_estimator_disagreement", "target_disagreement_rule": "estimator_disagreement"}
RULES.update({"historical_h30_error_rule": "historical_mask_h30_abs90", "scaled_support_rule": "scaled_support_uncertainty", "oof_daily_sd_rule": "reconstructor_oof_daily_sd"})
PROTOCOLS = ("leave_one_year_out", "strictly_prior_years")
SCOPES = ("documented_daily_mean", "all")


def raw_score(frame: pd.DataFrame, name: str) -> np.ndarray:
    score = pd.to_numeric(frame[RULES[name]], errors="coerce").to_numpy(dtype=float)
    if name == "warm_coverage_rule":
        score = -score
    return np.where(np.isfinite(frame.policy_metric) & np.isfinite(score), score, np.inf)


def columns_for(name: str) -> list[str]:
    features, kind = SPECS.get(name, ((), "rule"))
    columns = ["network_id", "station_id", "year", "independence_group", "provider", "statistic_class", "policy_metric", "abserr_policy", "policy_bad", "maximum_training_calendar_year", *features]
    if name in RULES:
        columns.append(RULES[name])
    if kind in {"certificate", "policy_certificate", "certificate_joint"}:
        columns.extend(["truth_hottest30", "longest_run_month", "policy_choice", *[f"hottest30_{method}" for method in ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge")]])
    return list(dict.fromkeys(columns))


def select_cases(path: Path, name: str, protocol_name: str, scope: str, *, old_source: bool) -> pd.DataFrame:
    frame = pd.read_parquet(path, columns=columns_for(name))
    if old_source:
        groups = pd.read_csv(C.RUN / "r3_06_independence_risk/complete_network_independence.csv").set_index("network_id").independence_group
        frame["independence_group"] = frame.network_id.map(groups)
    if scope == "documented_daily_mean":
        frame = frame.loc[frame.statistic_class.isin(["daily_mean", "documented_daily_mean"])]
    if protocol_name == "strictly_prior_years":
        frame = frame.loc[frame.year <= 2018]
        if (frame.maximum_training_calendar_year >= frame.year).any():
            raise RuntimeError("Prospective fitting contains future reconstruction information")
    return frame


def thresholds(scores: np.ndarray, frame: pd.DataFrame, candidates: np.ndarray, settings: dict, seed: int) -> dict:
    empirical = empirical_threshold(scores, frame.policy_bad.to_numpy(dtype=bool), frame.independence_group.to_numpy(), candidates, seed=seed, risk_cap=settings["risk_cap"], alpha=settings["alpha"])
    rigorous = select_group_threshold(scores, frame.policy_bad.to_numpy(dtype=bool), frame.independence_group.to_numpy(), candidates, risk_cap=settings["risk_cap"], alpha=settings["alpha"])
    return {"empirical": empirical["threshold"] if np.isfinite(empirical["threshold"]) else None, "empirical_status": empirical["status"], "empirical_upper": empirical["upper"], "certified": rigorous.threshold if np.isfinite(rigorous.threshold) else None, "certified_status": rigorous.status, "n_calibration_groups": frame.independence_group.nunique(), "n_calibration_cases": len(frame), "formal_minimum_bounded_loss_upper": float(rigorous.bounded_loss_upper.min())}


def fit_task(task: dict, settings: dict) -> dict:
    name, protocol_name, scope = task["name"], task["protocol"], task["scope"]
    regime, target = task["regime"], task["target_provider"]
    identity = "__".join(["admission", name, protocol_name, scope, regime, target or "all_providers"])
    manifest_path = OUT / "heads" / f"{identity}.json"
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        if previous["status"] == "fitted" and (previous["model_path"] is None or C.digest(Path(previous["model_path"])) == previous["model_sha256"]):
            return previous
    old_path = C.source_cases(protocol_name)
    local_path = C.RUN / "r3_08_external_recovery/development" / protocol_name / "admission/cofailure_0/cases.parquet"
    if regime == "local_fit":
        train = select_cases(local_path, name, protocol_name, scope, old_source=False)
        train = train.loc[train.provider.eq(target)]
        calibration = None
        sources = [local_path]
    else:
        source = select_cases(old_path, name, protocol_name, scope, old_source=True)
        if regime == "geographically_disjoint_source":
            source = source.loc[source.provider.eq("usgs")]
        if target:
            source = source.loc[~source.provider.eq(target)]
        roles = group_roles(source.independence_group.to_numpy(), settings["seed"], 0)
        role = source.independence_group.map(roles)
        train, calibration = source.loc[role.ne("calibration")], source.loc[role.eq("calibration")]
        sources = [old_path]
    if train.empty:
        record = {**task, "identity": identity, "status": "no_training_records_under_measurement_contract", "model_path": None}
        C.write_json(manifest_path, record)
        return record
    features, kind = SPECS.get(name, ((), "rule"))
    seed = stable_seed("r3-final-head", identity)
    model_path = None
    model = None
    if kind != "rule":
        model = fit_score(train, features, kind, seed=seed)
        model_path = OUT / "heads" / f"{identity}.joblib"
        joblib.dump({"model": model, "features": features, "kind": kind}, model_path, compress=3)
        if kind == "certificate_joint":
            train = certificate_delivery(model, train)
            if calibration is not None:
                calibration = certificate_delivery(model, calibration)
        train_score = predict_score(model, train, features, kind)
    else:
        train_score = raw_score(train, name)
    if not np.isfinite(train_score).any():
        record = {**task, "identity": identity, "status": "no_supported_training_score", "model_path": str(model_path) if model_path else None}
        C.write_json(manifest_path, record)
        return record
    candidates = fixed_training_candidates(train_score)
    source_thresholds = None
    if calibration is not None:
        score = raw_score(calibration, name) if kind == "rule" else predict_score(model, calibration, features, kind)
        source_thresholds = thresholds(score, calibration, candidates, settings, stable_seed("r3-final-source-cal", identity))
    record = {**task, "identity": identity, "status": "fitted", "kind": kind, "features": list(features), "model_path": str(model_path) if model_path else None, "model_sha256": C.digest(model_path) if model_path else None, "candidates": candidates.tolist(), "source_thresholds": source_thresholds, "n_training_cases": len(train), "n_training_groups": train.independence_group.nunique(), "training_providers": sorted(train.provider.unique()), "training_maximum_evaluation_year": int(train.year.max()), "source_inputs": [{"path": str(path), "sha256": C.digest(path)} for path in sources], "new_test_outcomes_used": False}
    C.write_json(manifest_path, record)
    return record


def fit_bank(workers: int, settings: dict) -> None:
    if (C.RUN / "method_lock.json").exists():
        raise RuntimeError("Method is already locked; do not refit after freezing")
    (OUT / "heads").mkdir(parents=True, exist_ok=True)
    tasks = []
    all_names = list(SPECS) + list(RULES)
    transfer_references = ["generic_target_disagreement", "generic_direct_h30_uncertainty", "uncertain_support", "certificate", "policy_certificate", "certificate_joint", "complete_diagnostic_model"]
    for protocol_name in PROTOCOLS:
        for scope in SCOPES:
            for name in all_names:
                tasks.append({"name": name, "protocol": protocol_name, "scope": scope, "regime": "source_only", "target_provider": None})
                for target in ("foen", "hubeau"):
                    if scope == "documented_daily_mean" and target == "hubeau":
                        continue
                    tasks.append({"name": name, "protocol": protocol_name, "scope": scope, "regime": "local_fit", "target_provider": target})
            for target in ("foen", "hubeau"):
                if scope == "documented_daily_mean" and target == "hubeau":
                    continue
                for name in transfer_references:
                    tasks.append({"name": name, "protocol": protocol_name, "scope": scope, "regime": "source_provider_excluded", "target_provider": target})
            for name in transfer_references:
                tasks.append({"name": name, "protocol": protocol_name, "scope": scope, "regime": "geographically_disjoint_source", "target_provider": None})
    print(f"[359] fitting {len(tasks)} predeclared heads/rules before new test evaluation", flush=True)
    records = Parallel(n_jobs=workers, verbose=10)(delayed(fit_task)(task, settings) for task in tasks)
    C.write_json(OUT / "head_bank.json", {"heads": records, "source_fitting_calibration_fraction": "80/20 independent groups", "prospective_deploy_date": "2018-12-31", "prospective_target_years": "2019-2022", "new_test_outcomes_opened": False})
    print("[359] head bank fitted; method lock still requires frozen reference models and code", flush=True)


def lock_method() -> None:
    bank = OUT / "head_bank.json"
    reference = C.RUN / "r3_11_probabilistic_reference/csdi_reference.pypots"
    required = [bank, reference, C.ROOT / "scripts/360_wrr_external_decisions.py", C.ROOT / "scripts/362_wrr_process_reference.py"]
    if any(not path.exists() for path in required):
        raise RuntimeError("Finish the head bank, probabilistic reference and final evaluation implementations before locking")
    code = list((C.ROOT / "src/stream_recoverability/experiments/v19_revision").glob("*.py"))
    code += list((C.ROOT / "src/stream_recoverability/experiments/v17_fitness").glob("*.py"))
    code += [C.ROOT / f"scripts/{name}" for name in ["wrr_r3_common.py", "351_wrr_representative_recovery.py", "357_wrr_decision_report.py", "358_wrr_external_recovery.py", "359_wrr_freeze_and_transfer.py", "360_wrr_external_decisions.py", "361_wrr_probabilistic_reference.py", "362_wrr_process_reference.py", "366_wrr_composition_transfer.py"]]
    code += [C.ROOT / "src/stream_recoverability/experiments/air2stream_equivalent.py"]
    code += [C.ROOT / "src/stream_recoverability/experiments/development_recovery.py"]
    inputs = {f"code_{index}": path for index, path in enumerate(code)}
    inputs.update({"head_bank": bank, "csdi_reference": reference, "external_eligibility": C.RUN / "r3_06_independence_risk/external_eligibility_addendum.csv", "protocol_lock": C.LOCK})
    inputs["composition_model"] = C.RUN / "r3_16_composition_transfer/composition_model.json"
    inputs["source_independence"] = C.RUN / "r3_06_independence_risk/complete_network_independence.csv"
    for name in ["DECISION_ADDENDUM.md", "TRANSFER_ADDENDUM.md", "COHORT_ADDENDUM.md"]:
        inputs[name] = C.DOCS / name
    for name in ["training_contract.json", "training_manifest.json", "old_record_training_membership.csv"]:
        inputs[f"csdi_{name}"] = C.RUN / "r3_11_probabilistic_reference" / name
    for name in ["CERRA_Ta", "MEAS_Qt", "WaterTemp_ExtremeEvents_perCatchment.csv"]:
        inputs[f"external_{name}"] = C.ROOT / "data/external/wrr_revision_20261020c/hydroshare" / name
    for index, path in enumerate(sorted((C.ROOT / "data/external/wrr_revision_20261020c/daily").rglob("*.parquet"))):
        inputs[f"acquired_daily_{index}"] = path
    for record in json.loads(bank.read_text())["heads"]:
        for source in record.get("source_inputs", []):
            if C.digest(Path(source["path"])) != source["sha256"]:
                raise RuntimeError("Head fitting input changed before method freeze")
            inputs[f"training_{record['identity']}_{Path(source['path']).parent.name}"] = Path(source["path"])
        if record.get("model_path"):
            inputs[f"head_{record['identity']}"] = Path(record["model_path"])
    destination = C.RUN / "method_lock.json"
    if destination.exists():
        raise RuntimeError("Immutable method lock already exists")
    C.write_json(destination, C.fingerprint(Path(__file__), inputs, status="all_predictive_choices_locked_before_new_calibration_or_test_errors", primary_h2_candidate="uncertain_support", compact_candidate="generic_direct_h30_uncertainty", primary_comparator="generic_target_disagreement"))
    print("[359] immutable method lock written", flush=True)


def calibrate(settings: dict) -> None:
    gate = C.load_script("r3_transfer_calibration_gate", C.ROOT / "scripts/358_wrr_external_recovery.py")
    gate.verify_role_access("calibration")
    bank = json.loads((OUT / "head_bank.json").read_text())["heads"]
    plans = []
    for record in bank:
        if record["status"] != "fitted":
            continue
        for provider in ("foen", "hubeau"):
            if record["target_provider"] and record["target_provider"] != provider:
                continue
            path = C.RUN / "r3_08_external_recovery/calibration" / record["protocol"] / "admission/cofailure_0/cases.parquet"
            frame = select_cases(path, record["name"], record["protocol"], record["scope"], old_source=False)
            frame = frame.loc[frame.provider.eq(provider)]
            if frame.empty:
                continue
            model = joblib.load(record["model_path"]) if record["model_path"] else None
            if record["kind"] == "certificate_joint":
                frame = certificate_delivery(model["model"], frame)
            score = raw_score(frame, record["name"]) if model is None else predict_score(model["model"], frame, tuple(model["features"]), model["kind"])
            local = thresholds(score, frame, np.asarray(record["candidates"]), settings, stable_seed("r3-target-cal", record["identity"], provider))
            if record["source_thresholds"] is not None:
                mode = {"source_only": "frozen_source", "source_provider_excluded": "frozen_unseen_provider", "geographically_disjoint_source": "frozen_intercontinental"}[record["regime"]]
                plans.append({"head_identity": record["identity"], "target_provider": provider, "mode": mode, "thresholds": record["source_thresholds"]})
            if record["regime"] == "source_only":
                plans.append({"head_identity": record["identity"], "target_provider": provider, "mode": "frozen_model_local_calibration", "thresholds": local})
            elif record["regime"] == "local_fit":
                plans.append({"head_identity": record["identity"], "target_provider": provider, "mode": "local_fit_and_calibration", "thresholds": local})
    destination = OUT / "deployment_plans.json"
    if destination.exists():
        raise RuntimeError("Deployment plans already frozen; do not recalibrate after testing")
    C.write_json(destination, {"plans": plans, "new_test_outcomes_opened": False})
    lock_inputs = {"method_lock": C.RUN / "method_lock.json", "deployment_plans": destination}
    for protocol_name in PROTOCOLS:
        lock_inputs[f"calibration_cases_{protocol_name}"] = C.RUN / "r3_08_external_recovery/calibration" / protocol_name / "admission/cofailure_0/cases.parquet"
    C.write_json(C.RUN / "deployment_lock.json", C.fingerprint(Path(__file__), lock_inputs, status="all_source_and_target_calibrated_decisions_frozen_before_test"))
    print(f"[359] {len(plans)} frozen deployment plans; new test outcomes may now be computed", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["fit", "lock", "calibrate"], default="fit")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    settings = C.protocol()
    if args.stage == "fit":
        fit_bank(args.workers, settings)
    elif args.stage == "lock":
        lock_method()
    else:
        calibrate(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
