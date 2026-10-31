#!/usr/bin/env python3
"""Develop an air-conditioned probability reference using only old validation."""
from __future__ import annotations

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

import wrr_r3_common as C
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v19_revision.data import station_air_series
from stream_recoverability.experiments.v19_revision.state_trajectory import sample_crps
from stream_recoverability.experiments.v19_revision.trajectory import trajectory_features, window_means
from stream_recoverability.seeds import plain_seed, position_index

OUT = C.READY / "followup_20261021/probability_development"
CONFIG = C.ROOT / "configs/wrr_probability_budget_20261021.json"
OLD = C.RUN / "r3_11_probabilistic_reference"
# Last seed part for the per-station-year choice of a fitting mask.
TRAINING_MASK_SEED = 1


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def standardize(series, year, dates):
    history = series.loc[series.index.year != year].dropna()
    mean = float(history.mean()) if len(history) else 0.0
    scale = max(float(history.std(ddof=1)), 0.1) if len(history) > 1 else 1.0
    return (series.reindex(dates).to_numpy(dtype=float) - mean) / scale, mean, scale


def mask_design(name, n_days, peak_start):
    mask = np.zeros(n_days, dtype=bool)
    if name == "peak30":
        runs = [(int(peak_start), 30)]
    elif name == "peak90":
        runs = [(min(max(int(peak_start) - 30, 0), n_days - 90), 90)]
    elif name == "start60":
        runs = [(0, 60)]
    elif name == "end60":
        runs = [(n_days - 60, 60)]
    elif name == "fragmented60":
        runs = [(140, 30), (210, 30)]
    else:
        raise ValueError(name)
    for start, length in runs:
        mask[start:start + length] = True
    return mask


@lru_cache(maxsize=64)
def read_panel(path):
    panel = read_temperature_panel(path).asfreq("D")
    panel.columns = panel.columns.astype(str)
    return panel


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "dataset_contract.json").exists():
        print("[385] existing old-group dataset retained", flush=True)
        return
    core = C.load_script("probability_budget_source_jobs", C.ROOT / "scripts/351_wrr_representative_recovery.py")
    jobs, _ = core.source_jobs("leave_one_year_out", False)
    groups = pd.read_csv(C.RUN / "r3_06_independence_risk/complete_network_independence.csv").set_index("network_id").independence_group
    job_of = {}
    for job in jobs:
        job["independence_group"] = groups[job["network_id"]]
        job_of.setdefault((job["provider"], job["station_id"]), job)
    membership = pd.read_csv(OLD / "old_record_training_membership.csv", dtype={"station_id": str, "group": str})
    training = membership.loc[membership.role.eq("training")].copy()
    validation = membership.loc[membership.role.eq("validation")].sort_values(["year", "station_id"], kind="stable").drop_duplicates("group")
    if set(training.group) & set(validation.group):
        raise RuntimeError("Old fitting and validation groups overlap")
    settings = json.loads(CONFIG.read_text())
    training_stations = position_index(training.station_id)
    air_path = C.ROOT / "data/interim/v18_air_forcing.parquet"
    train_arrays, train_patterns, val_arrays, val_masked = [], [], [], []
    normalizers, validation_cases, validation_inputs = [], [], []
    custody = []
    for role, data in (("training", training), ("validation", validation)):
        for row in data.itertuples(index=False):
            job = job_of[(row.provider, row.station_id)]
            if str(job["independence_group"]) != str(row.group):
                raise RuntimeError("Old validation group map changed")
            panel = read_panel(job["input_path"])
            target = panel[row.station_id]
            dates = target.index[target.index.year == row.year]
            truth = target.reindex(dates).to_numpy(dtype=float)
            air = station_air_series(air_path, job["network_id"], row.station_id, target.index)
            if air is None:
                air = pd.Series(np.nan, index=target.index)
            water_z, water_mean, water_scale = standardize(target, row.year, dates)
            air_z, air_mean, air_scale = standardize(air, row.year, dates)
            array = np.full((366, 2), np.nan, dtype=np.float32)
            array[:len(dates), 0], array[:len(dates), 1] = water_z, air_z
            allowed = pd.Series(target.index.year != row.year, index=target.index)
            climatology = target.loc[allowed].groupby(target.loc[allowed].index.dayofyear).mean()
            climate = pd.Series(dates.dayofyear).map(climatology).interpolate(limit_direction="both").to_numpy()
            peak_start = int(np.argmax(window_means(climate)))
            normalizers.append({"role": role, "provider": row.provider, "station_id": row.station_id, "group": row.group, "year": int(row.year),
                                "water_mean": water_mean, "water_scale": water_scale, "air_mean": air_mean, "air_scale": air_scale,
                                "air_available_fraction": float(np.isfinite(air_z).mean())})
            custody.append({"provider": row.provider, "station_id": row.station_id, "group": row.group, "input_path": job["input_path"]})
            if role == "training":
                mask_name = settings["validation_masks"][plain_seed(training_stations[row.station_id], int(row.year), TRAINING_MASK_SEED) % len(settings["validation_masks"])]
                mask = mask_design(mask_name, len(dates), peak_start)
                pattern = np.isfinite(array).astype(np.float32)
                pattern[np.flatnonzero(mask), 0] = 0
                train_arrays.append(array)
                train_patterns.append(pattern)
            else:
                for name in settings["validation_masks"]:
                    mask = mask_design(name, len(dates), peak_start)
                    observed = array.copy()
                    observed[np.flatnonzero(mask), 0] = np.nan
                    val_arrays.append(array)
                    val_masked.append(observed)
                    validation_inputs.append(truth)
                    validation_cases.append({"provider": row.provider, "station_id": row.station_id, "independence_group": row.group,
                                             "year": int(row.year), "mask": name, "n_days": len(dates), "mean": water_mean, "scale": water_scale,
                                             "mask_positions": ";".join(map(str, np.flatnonzero(mask))), "truth_h30": float(window_means(truth).max())})
    train_arrays = np.stack(train_arrays)
    # Old standardized water tensors provide an independent alignment check.
    old_arrays = np.load(OLD / "training_arrays.npz")
    if not np.allclose(train_arrays[:, :, 0], old_arrays["X"][:, :, 0], equal_nan=True):
        raise RuntimeError("Old fitting membership/normalization no longer aligns")
    np.savez_compressed(OUT / "arrays.npz", X=train_arrays, pattern=np.stack(train_patterns), validation_X=np.stack(val_masked), validation_X_ori=np.stack(val_arrays))
    pd.DataFrame(normalizers).to_csv(OUT / "normalizers.csv", index=False)
    pd.DataFrame(validation_cases).to_csv(OUT / "validation_cases.csv", index=False)
    pd.DataFrame(custody).drop_duplicates(["provider", "station_id"]).to_csv(OUT / "input_custody.csv", index=False)
    membership.to_csv(OUT / "old_group_membership.csv", index=False)
    C.write_json(OUT / "dataset_contract.json", run_record({"membership": OLD / "old_record_training_membership.csv", "old_arrays": OLD / "training_arrays.npz", "source_air": air_path, "budget": CONFIG}, n_training_years=len(training), n_validation_groups=len(validation), n_validation_masks=len(val_masked), new_external_values_used_for_selection=False, target_year_excluded_from_all_normalizers=True))
    print(f"[385] {len(training)} fitting years, {len(validation)} held-out groups, {len(val_masked)} task-validation masks", flush=True)


def model_instance(name, threads):
    import torch
    from pypots.imputation import CSDI
    from pypots.optim import Adam
    settings = json.loads(CONFIG.read_text())
    torch.set_num_threads(threads)
    torch.manual_seed(settings["seed"])
    np.random.seed(settings["seed"])
    return CSDI(**settings["shared"], **settings["configurations"][name], optimizer=Adam(lr=settings["learning_rate"]), saving_path=str(OUT / name / "training"))


def train(name, threads):
    if not (OUT / "dataset_contract.json").exists():
        raise RuntimeError("Prepare and freeze the old-only dataset first")
    destination = OUT / name
    destination.mkdir(exist_ok=True)
    model_path = destination / "model.pypots"
    if model_path.exists():
        print(f"[385] completed {name} checkpoint retained", flush=True)
        return
    data = np.load(OUT / "arrays.npz")
    model = model_instance(name, threads)
    started = time.monotonic()
    # Early stopping uses the predeclared masked-water loss on old validation.
    model.fit({"X": data["X"], "for_pattern_mask": data["pattern"]}, {"X": data["validation_X"], "X_ori": data["validation_X_ori"]})
    model.save(str(model_path))
    C.write_json(destination / "training.json", run_record({"budget": CONFIG, "arrays": OUT / "arrays.npz", "contract": OUT / "dataset_contract.json"}, name=name, wall_seconds=time.monotonic() - started, maximum_epochs=30, patience=5, threads=threads, completed=True))
    print(f"[385] trained {name}", flush=True)


def prediction_rows(samples, cases, originals):
    rows = []
    for position, case in enumerate(cases.to_dict("records")):
        truth = originals[position]
        mask = np.zeros(len(truth), dtype=bool)
        mask[np.array([int(value) for value in case["mask_positions"].split(";")], dtype=int)] = True
        draws = samples[position, :, :len(truth), 0].astype(float) * case["scale"] + case["mean"]
        draws[:, ~mask] = truth[~mask]
        if not np.isfinite(draws).all():
            rows.append({**case, "available": False})
            continue
        h30 = window_means(draws).max(axis=1)
        point = float(np.median(h30))
        lower, upper = np.quantile(h30, [0.05, 0.95])
        row = {**case, "available": True, "h30_point": point, "h30_pointwise_median": float(window_means(np.median(draws, axis=0)).max()),
               "absolute_error_C": abs(point - case["truth_h30"]), "signed_error_C": point - case["truth_h30"],
               "crps_C": sample_crps(h30, case["truth_h30"]), "covered90": bool(lower <= case["truth_h30"] <= upper),
               "lower_C": lower, "upper_C": upper, "interval_width_C": upper - lower, "n_samples": len(h30)}
        row.update(trajectory_features(draws, mask, point))
        for n in (8, 16, 32):
            subset = h30[:n]
            row[f"point_{n}"] = float(np.median(subset))
            row[f"crps_{n}"] = sample_crps(subset, case["truth_h30"])
        if "local_hot_threshold_C" in case:
            p = float((h30 > case["local_hot_threshold_C"]).mean())
            row["hot_probability"] = p
            row["brier_hot"] = (p - float(case["truth_h30"] > case["local_hot_threshold_C"])) ** 2
        rows.append(row)
    return pd.DataFrame(rows)


def validate(name, threads):
    model_path = OUT / name / "model.pypots"
    model = model_instance(name, threads)
    model.load(str(model_path))
    data = np.load(OUT / "arrays.npz")
    cases = pd.read_csv(OUT / "validation_cases.csv", dtype={"station_id": str})
    originals = [data["validation_X_ori"][i, :int(case.n_days), 0].astype(float) * case.scale + case.mean for i, case in enumerate(cases.itertuples(index=False))]
    sampled = model.predict({"X": data["validation_X"]}, n_sampling_times=32)["imputation"]
    result = prediction_rows(sampled, cases, originals)
    result.to_parquet(OUT / name / "validation.parquet", index=False)
    group_score = result.groupby("independence_group").crps_C.mean()
    C.write_json(OUT / name / "validation.json", {"configuration": name, "n_groups": len(group_score), "n_candidates": len(result), "n_available": int(result.available.sum()), "equal_group_h30_crps_C": float(group_score.mean()), "selection_uses_external_outcomes": False})
    print(f"[385] {name} old-group H30 CRPS={group_score.mean():.4f} C", flush=True)


def select():
    settings = json.loads(CONFIG.read_text())
    records = [json.loads((OUT / name / "validation.json").read_text()) for name in settings["configurations"]]
    if not all(row["n_available"] == row["n_candidates"] for row in records):
        raise RuntimeError("Unsupported validation predictions require a prespecified penalty; do not silently select on remaining cases")
    chosen = min(records, key=lambda row: (row["equal_group_h30_crps_C"], row["configuration"]))
    C.write_json(OUT / "selection.json", {"selected": chosen["configuration"], "criterion": "old-only equal-group H30 CRPS", "candidates": records,
                                         "new_external_test_outcomes_used": False,
                                         "status": "supplementary model development, not a new independent confirmation"})
    pd.DataFrame(records).to_csv(OUT / "development_results.csv", index=False)
    print(f"[385] selected {chosen['configuration']} from old validation only", flush=True)


def evaluate(role, threads):
    selection = json.loads((OUT / "selection.json").read_text())
    name = selection["selected"]
    model_path = OUT / name / "model.pypots"
    source = C.RUN / "r3_08_external_recovery" / role / "leave_one_year_out/crossed/cofailure_0"
    base = pd.read_parquet(source / "cases.parquet")
    base = base.loc[base.replicate.eq(0) & base.design_family.eq("crossed_contiguous") & base.statistic_class.eq("daily_mean")]
    jobs = json.loads((source / "jobs.json").read_text())["jobs"]
    job_of = {job["station_id"]: job for job in jobs}
    arrays, originals, case_rows = [], [], []
    for case in base.itertuples(index=False):
        job = job_of[case.station_id]
        panel = read_panel(job["input_path"])
        target = panel[case.station_id]
        dates = target.index[target.index.year == case.year]
        truth = target.reindex(dates).to_numpy(dtype=float)
        air = station_air_series(Path(job["air_input_path"]), case.network_id, case.station_id, target.index)
        if air is None:
            air = pd.Series(np.nan, index=target.index)
        water_z, mean, scale = standardize(target, case.year, dates)
        air_z, _, _ = standardize(air, case.year, dates)
        observed = np.full((366, 2), np.nan, dtype=np.float32)
        observed[:len(dates), 0], observed[:len(dates), 1] = water_z, air_z
        mask = np.zeros(len(dates), dtype=bool)
        for run in case.mask_runs.split(";"):
            start, length = map(int, run.split(":"))
            mask[start:start + length] = True
        observed[np.flatnonzero(mask), 0] = np.nan
        arrays.append(observed)
        originals.append(truth)
        case_rows.append({"network_id": case.network_id, "station_id": case.station_id, "independence_group": case.independence_group, "year": int(case.year),
                          "realization_id": case.realization_id, "mask_positions": ";".join(map(str, np.flatnonzero(mask))), "n_days": len(dates),
                          "mean": mean, "scale": scale, "truth_h30": case.truth_hottest30, "local_hot_threshold_C": case.local_hot_threshold_C,
                          "air_available_fraction": float(np.isfinite(air_z).mean()), "gap_length": case.longest_run, "warm_anomaly": bool(case.warm_anomaly)})
    model = model_instance(name, threads)
    model.load(str(model_path))
    started = time.monotonic()
    samples = model.predict({"X": np.stack(arrays)}, n_sampling_times=32)["imputation"]
    result = prediction_rows(samples, pd.DataFrame(case_rows), originals)
    output = OUT / role
    output.mkdir(exist_ok=True)
    result.to_parquet(output / "cases.parquet", index=False)
    result.groupby("available").agg(n=("year", "size"), groups=("independence_group", "nunique"), mae_C=("absolute_error_C", "mean"), crps_C=("crps_C", "mean"), coverage90=("covered90", "mean"), width_C=("interval_width_C", "mean"), brier_hot=("brier_hot", "mean")).to_csv(output / "summary.csv")
    C.write_json(output / "run_record.json", run_record({"selected_checkpoint": model_path, "selection": OUT / "selection.json", "cases": source / "cases.parquet"}, model_name=name, wall_seconds=time.monotonic() - started, n_sampling_times=32, supplementary_development=True, new_confirmation=False))
    print(f"[385] selected air-conditioned CSDI evaluated on {len(result)} {role} cases", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "train", "validate", "select", "evaluate"])
    parser.add_argument("--configuration", choices=["air32", "air64"], default="air32")
    parser.add_argument("--role", choices=["development", "calibration", "test"], default="development")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "train":
        train(args.configuration, args.threads)
    elif args.action == "validate":
        validate(args.configuration, args.threads)
    elif args.action == "select":
        select()
    else:
        evaluate(args.role, args.threads)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
