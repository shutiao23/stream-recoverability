#!/usr/bin/env python3
"""Compare H30 points using a shared developed conditional H30 distribution."""
from __future__ import annotations

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_r3_common as C
from stream_recoverability.experiments.v19_revision import decision_baselines as D
from stream_recoverability.experiments.v19_revision.learning import GENERIC, WINDOW_INFORMATION, empirical_threshold
from stream_recoverability.experiments.v19_revision.risk import fixed_training_candidates, select_group_threshold
from stream_recoverability.experiments.v19_revision.trajectory import window_means
from stream_recoverability.seeds import plain_seed

PROB = C.READY / "followup_20261021/probability_development"
OUT = C.READY / "followup_20261021/system_factorial_developed"
KEYS = ["network_id", "station_id", "year", "realization_id"]
# Chunk seeds: plain_seed(ROLE_CODES[role], first case position of the chunk, CHUNK_SEED).
ROLE_CODES = {"development": 0, "calibration": 1, "test": 2}
CHUNK_SEED = 1
_CHUNK_MODELS = {}


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def h30_ensembles(samples, cases, originals):
    values = []
    for position, case in enumerate(cases.to_dict("records")):
        observed = originals[position]
        mask = np.zeros(len(observed), dtype=bool)
        mask[np.array(case["mask_positions"].split(";"), dtype=int)] = True
        draws = samples[position, :, :len(observed), 0].astype(float) * case["scale"] + case["mean"]
        draws[:, ~mask] = observed[~mask]
        values.append(window_means(draws).max(axis=1))
    return values


def evaluate_probability(role):
    core = C.load_script("developed_probability_distribution", C.ROOT / "scripts/385_wrr_probability_development.py")
    source = C.RUN / "r3_08_external_recovery" / role / "leave_one_year_out/crossed/cofailure_0"
    jobs = json.loads((source / "jobs.json").read_text())["jobs"]
    water_sources = list(dict.fromkeys(job["input_path"] for job in jobs))
    air_sources = list(dict.fromkeys(job["air_input_path"] for job in jobs))
    original = core.prediction_rows
    original_factory = core.model_instance
    def factory(name, threads):
        model = original_factory(name, threads)
        def predict(data, n_sampling_times):
            return parallel_sample_predict(name, role, data, n_sampling_times)
        model.predict = predict
        return model
    def extended(samples, cases, originals):
        frame = original(samples, cases, originals)
        frame["h30_samples_C"] = h30_ensembles(samples, cases, originals)
        return frame
    core.prediction_rows = extended
    core.model_instance = factory
    core.evaluate(role, 4)
    inputs = {"inference": Path(core.__file__), "selection": PROB / "selection.json", "cases": PROB / role / "cases.parquet"}
    inputs.update({f"air_source_{i}": path for i, path in enumerate(air_sources)})
    inputs.update({f"water_source_{i}": path for i, path in enumerate(water_sources)})
    C.write_json(PROB / role / "ensemble_extension.json", run_record(inputs, shared_distribution=True, observed_values_preserved=True,
                 sampling="32 independent repeated inputs, one conditional draw each; same model law; 12 case-chunk workers, one torch thread and batch 32 each; distinct deterministic chunk seeds; random-number ordering differs from serial sampling"))


def sample_chunk(name, role, start, values, n_sampling_times):
    """Independent reproducible random stream for each chunk, with resumable draws."""
    seed = plain_seed(ROLE_CODES[role], start, CHUNK_SEED)
    checkpoint = PROB / name / "model.pypots"
    destination = PROB / role / "sampling_chunks" / f"case_{start:05d}.npz"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        with np.load(destination) as cached:
            return cached["samples"]
    import torch
    if name not in _CHUNK_MODELS:
        core = C.load_script("developed_CSDI_chunk_core", C.ROOT / "scripts/385_wrr_probability_development.py")
        model = core.model_instance(name, 1)
        model.load(str(checkpoint))
        model.batch_size = 32
        _CHUNK_MODELS[name] = model
    torch.manual_seed(seed)
    np.random.seed(seed)
    samples = repeated_sample_predict(_CHUNK_MODELS[name].predict, {"X": values}, n_sampling_times)["imputation"]
    temporary = destination.with_name(destination.stem + f".{os.getpid()}.partial.npz")
    np.savez_compressed(temporary, samples=samples)
    temporary.replace(destination)
    return samples


def chunk_worker(*args):
    import importlib
    return importlib.import_module("390_wrr_developed_probability_system").sample_chunk(*args)


def parallel_sample_predict(name, role, data, n_sampling_times, workers=12):
    if set(data) != {"X"} or n_sampling_times < 1:
        raise ValueError("Require an X-only batch and a positive sampling count")
    values = np.asarray(data["X"])
    chunks = Parallel(n_jobs=workers, verbose=10)(delayed(chunk_worker)(name, role, start, values[start:start + 4], n_sampling_times) for start in range(0, len(values), 4))
    return {"imputation": np.concatenate(chunks, axis=0)}


def repeated_sample_predict(predict, data, n_sampling_times):
    if set(data) != {"X"} or n_sampling_times < 1:
        raise ValueError("Require an X-only batch and a positive sampling count")
    original = np.asarray(data["X"])
    repeated = np.repeat(original, n_sampling_times, axis=0)
    output = predict({"X": repeated}, n_sampling_times=1)
    sampled = output["imputation"]
    expected = (len(original) * n_sampling_times, 1, *original.shape[1:])
    if sampled.shape != expected:
        raise ValueError(f"Unexpected conditional sample shape {sampled.shape}; expected {expected}")
    return {"imputation": sampled.reshape(len(original), n_sampling_times, *original.shape[1:])}


def role_data(role):
    base = pd.read_parquet(C.RUN / "r3_08_external_recovery" / role / "leave_one_year_out/crossed/cofailure_0/cases.parquet")
    base = base.loc[base.replicate.eq(0) & base.design_family.eq("crossed_contiguous") & base.statistic_class.eq("daily_mean")].copy()
    probability = pd.read_parquet(PROB / role / "cases.parquet")
    probability = probability.loc[probability.available]
    columns = KEYS + ["h30_point", "h30_samples_C", *WINDOW_INFORMATION]
    merged = base.merge(probability[columns], on=KEYS, how="left", suffixes=("", "_NN"), validate="one_to_one")
    physics = pd.read_parquet(C.RUN / "r3_12_process_reference" / role / "leave_one_year_out/cases.parquet")
    physics = physics.loc[physics.method.eq("air2stream3") & physics.status.eq("available"), KEYS + ["h30_reconstructed"]]
    merged = merged.merge(physics, on=KEYS, how="left", validate="one_to_one")
    return merged


def prepare_point(frame, method):
    point_columns = {"priority": "policy_metric", "air2stream3": "h30_reconstructed", "csdi_developed_air": "h30_point"}
    result = frame.copy()
    result["reconstruction_point"] = pd.to_numeric(result[point_columns[method]], errors="coerce")
    ensembles, valid_cdf = ensemble_matrix(result.h30_samples_C)
    point = result.reconstruction_point.to_numpy()
    valid_point = valid_cdf & np.isfinite(point)
    result["cdf_available"] = valid_cdf
    for name in ("NN_failure_probability", "NN_target_abs90", "NN_h30_sd", "NN_width90"):
        result[name] = np.nan
    result.loc[valid_point, "NN_failure_probability"] = np.mean(np.abs(ensembles[valid_point] - point[valid_point, None]) > 0.5, axis=1)
    result.loc[valid_point, "NN_target_abs90"] = np.quantile(np.abs(ensembles[valid_point] - point[valid_point, None]), .9, axis=1)
    result.loc[valid_cdf, "NN_h30_sd"] = ensembles[valid_cdf].std(axis=1)
    result.loc[valid_cdf, "NN_width90"] = np.quantile(ensembles[valid_cdf], .95, axis=1) - np.quantile(ensembles[valid_cdf], .05, axis=1)
    result["threshold_margin_C"] = point - result.local_hot_threshold_C
    result["own_failure"] = ~np.isfinite(point) | (np.abs(point - result.truth_hottest30.to_numpy()) > .5)
    return result


def ensemble_matrix(values):
    valid = np.array([isinstance(value, (list, np.ndarray)) and len(value) > 0 and np.isfinite(value).all() for value in values])
    sizes = {len(value) for value, keep in zip(values, valid) if keep}
    if len(sizes) > 1:
        raise ValueError("Shared probability cases have inconsistent sampling budgets")
    n_samples = next(iter(sizes), 32)
    matrix = np.full((len(values), n_samples), np.nan)
    for position in np.flatnonzero(valid):
        matrix[position] = np.asarray(values.iloc[position] if hasattr(values, "iloc") else values[position])
    return matrix, valid


def evaluate_system():
    OUT.mkdir(parents=True, exist_ok=True)
    data = {role: role_data(role) for role in ("development", "calibration", "test")}
    common = {}
    for role, frame in data.items():
        mask = np.isfinite(frame.h30_reconstructed) & frame.h30_samples_C.map(lambda value: isinstance(value, (list, np.ndarray)) and np.isfinite(value).all())
        common[role] = frame.loc[mask].copy()
    generic = tuple(name for name in GENERIC if name != "estimator_disagreement")
    direct = ("reconstruction_point", "threshold_margin_C", "NN_failure_probability", "NN_target_abs90", "NN_h30_sd", "NN_width90")
    window_names = tuple(name + "_NN" for name in WINDOW_INFORMATION)
    operating, costs, strata, admission_cases, group_rows = [], [], [], [], []
    for method in ("priority", "air2stream3", "csdi_developed_air"):
        train, calibration = (prepare_point(common[role], method) for role in ("development", "calibration"))
        test = prepare_point(data["test"], method)
        if set(train.independence_group) & (set(calibration.independence_group) | set(test.independence_group)) or set(calibration.independence_group) & set(test.independence_group):
            raise RuntimeError("Developed probability system roles overlap")
        test_truth = test.truth_hottest30.to_numpy() > test.local_hot_threshold_C.to_numpy()
        point_hot = test.reconstruction_point.to_numpy() > test.local_hot_threshold_C.to_numpy()
        point_available = np.isfinite(test.reconstruction_point.to_numpy())
        # Classification depends on the same H30 law, not which numerical point is delivered.
        raw_cal = np.mean(np.stack(calibration.h30_samples_C.to_numpy()) > calibration.local_hot_threshold_C.to_numpy()[:, None], axis=1)
        test_samples, cdf_available = ensemble_matrix(test.h30_samples_C)
        raw_test = np.mean(test_samples[cdf_available] > test.local_hot_threshold_C.to_numpy()[cdf_available, None], axis=1)
        p_hot = np.full(len(test), np.nan)
        p_hot[cdf_available] = D.probability_calibration(raw_cal, calibration.truth_hottest30 > calibration.local_hot_threshold_C, raw_test)
        if method == "priority":
            reliability = pd.DataFrame({"raw_probability": np.where(cdf_available, np.mean(test_samples > test.local_hot_threshold_C.to_numpy()[:, None], axis=1), np.nan),
                                        "calibrated_probability": p_hot, "truth_hot": test_truth})
            bins = []
            for probability_kind in ("raw_probability", "calibrated_probability"):
                valid = reliability.loc[cdf_available].copy()
                valid["probability_bin"] = np.minimum((valid[probability_kind] * 10).astype(int), 9)
                grouped = valid.groupby("probability_bin").agg(n=("truth_hot", "size"), mean_probability=(probability_kind, "mean"), observed_fraction=("truth_hot", "mean")).reset_index()
                grouped["probability_kind"] = probability_kind
                bins.append(grouped)
            pd.concat(bins, ignore_index=True).to_csv(OUT / "probability_reliability.csv", index=False)
        for score_kind in ("native_CDF", "boost_direct", "boost_window"):
            window = score_kind == "boost_window"
            features = generic + direct + (window_names if window else ())
            if score_kind == "native_CDF":
                train_score, cal_score, score = [block.NN_failure_probability.to_numpy() for block in (train, calibration, test)]
                score = np.where(point_available & cdf_available, score, np.inf)
            else:
                model = D.fit_matched(train, features, train.own_failure.astype(int), objective="probability", seed=20261021)
                train_score, cal_score, score = [D.predict_matched(model, block, features, objective="probability") for block in (train, calibration, test)]
            candidates = fixed_training_candidates(train_score)
            empirical = empirical_threshold(cal_score, calibration.own_failure.to_numpy(), calibration.independence_group.to_numpy(), candidates, seed=20261021, draws=2000)
            formal = select_group_threshold(cal_score, calibration.own_failure.to_numpy(), calibration.independence_group.to_numpy(), candidates)
            admitted = point_available & cdf_available & (score <= empirical["threshold"])
            records = test[KEYS + ["independence_group", "reconstruction_point", "own_failure", "cdf_available"]].copy()
            records["method"], records["score_kind"] = method, score_kind
            records["score"], records["admitted"], records["hot_probability"] = score, admitted, p_hot
            admission_cases.append(records)
            group_a, group_b = [], []
            for name, positions in test.groupby("independence_group").indices.items():
                a = float(admitted[positions].mean())
                b = float((admitted[positions] & test.own_failure.to_numpy()[positions]).mean())
                group_a.append(a)
                group_b.append(b)
                group_rows.append({"method": method, "score_kind": score_kind, "independence_group": name, "n_candidates": len(positions),
                                   "admission_fraction": a, "failure_and_admission_fraction": b, "selected_risk": b / a if a else np.nan})
            identity = {"method": method, "score_kind": score_kind, "window": window, "n_candidates": len(test), "n_groups": test.independence_group.nunique(), "n_point_available": int(point_available.sum())}
            operating.append({**identity, "accepted": int(admitted.sum()), "failed": int((admitted & test.own_failure.to_numpy()).sum()), "retention": admitted.mean(),
                              "risk": test.own_failure.to_numpy()[admitted].mean() if admitted.any() else np.nan,
                              "equal_group_retention": float(np.mean(group_a)), "equal_group_risk": float(np.mean(group_b) / np.mean(group_a)) if np.mean(group_a) else np.nan,
                              "formal_accepted": int((point_available & cdf_available & (score <= formal.threshold)).sum()), "formal_status": formal.status,
                              "matched_subset_MAE_C": float(np.mean(np.abs(prepare_point(common["test"], method).reconstruction_point - common["test"].truth_hottest30)))})
            for air_status, positions in test.groupby("air_available").indices.items():
                mask = admitted[positions]
                strata.append({**identity, "air_available": bool(air_status), "stratum_candidates": len(positions), "accepted": int(mask.sum()),
                               "failed": int((mask & test.own_failure.to_numpy()[positions]).sum())})
            for fn_cost in (1, 5, 10):
                for abstention_cost in (0, .01, .025, .05, .1, .25):
                    direct_action = np.full(len(test), 2)
                    direct_action[cdf_available] = D.cost_action(p_hot[cdf_available], fn_cost, abstention_cost)
                    actions = {"reconstruct_all": np.where(point_available, point_hot.astype(int), 2), "magnitude_screen": np.where(admitted, point_hot.astype(int), 2),
                               "direct_calibrated_NN_cost": direct_action, "all_unknown": np.full(len(test), 2),
                               "all_hot": np.ones(len(test), dtype=int), "all_cool": np.zeros(len(test), dtype=int)}
                    for policy, action in actions.items():
                        costs.append({**identity, "policy": policy, "fn_cost": fn_cost, "abstention_cost": abstention_cost,
                                      "loss": D.action_loss(action, test_truth, fn_cost, abstention_cost).mean(), **D.action_counts(action, test_truth)})
                    retention = admitted.sum() / point_available.sum() if point_available.any() else 0
                    base_action = actions["reconstruct_all"]
                    counts = D.action_counts(base_action, test_truth)
                    for name in ("true_positive", "true_negative", "false_positive", "false_negative"):
                        counts[name] *= retention
                    counts["unknown"] = int((~admitted).sum())
                    base_loss = D.action_loss(base_action, test_truth, fn_cost, abstention_cost)
                    costs.append({**identity, "policy": "random_matched_screen", "fn_cost": fn_cost, "abstention_cost": abstention_cost,
                                  "loss": float((retention * base_loss + (1 - retention) * abstention_cost).mean()), "counts_are_expectations": True, **counts})
    pd.DataFrame(operating).to_csv(OUT / "operating.csv", index=False)
    pd.DataFrame(costs).to_csv(OUT / "decision_costs.csv", index=False)
    pd.DataFrame(strata).to_csv(OUT / "air_availability.csv", index=False)
    pd.DataFrame(group_rows).to_csv(OUT / "group_results.csv", index=False)
    pd.concat(admission_cases, ignore_index=True).to_parquet(OUT / "admission_cases.parquet", index=False)
    inputs = {"selection": PROB / "selection.json", "implementation": Path(D.__file__)}
    for role in data:
        inputs[role] = PROB / role / "cases.parquet"
    C.write_json(OUT / "run_record.json", run_record(inputs, same_air_information=True, same_NN_distribution_for_all_points=True,
                 direct_CDF_failure_probability_present_before_window_ablation=True, old_only_probability_development=True, independent_new_confirmation=False,
                 point_method_classification_has_a_common_distribution=True))
    print("[390] developed same-air probability reference: own point errors, calibrated admission, shared-CDF decisions", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["evaluate-probability", "system"])
    parser.add_argument("--role", choices=["development", "calibration", "test"], default="development")
    args = parser.parse_args()
    evaluate_probability(args.role) if args.action == "evaluate-probability" else evaluate_system()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
