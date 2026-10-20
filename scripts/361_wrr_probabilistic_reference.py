#!/usr/bin/env python3
"""Train a CSDI reference on old records and evaluate fixed crossed external cases."""

from __future__ import annotations

import os

for thread_variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[thread_variable] = "1"

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_r3_common as C

from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v17_fitness.paths import stable_seed
from stream_recoverability.experiments.v19_revision.trajectory import window_means

OUT = C.RUN / "r3_11_probabilistic_reference"
MODEL_ARGS = {"n_steps": 366, "n_features": 1, "n_layers": 2, "n_heads": 2, "n_channels": 32, "d_time_embedding": 64, "d_feature_embedding": 16, "d_diffusion_embedding": 64, "n_diffusion_steps": 50, "target_strategy": "mix", "batch_size": 32, "epochs": 30, "patience": 5, "num_workers": 0, "device": "cpu", "verbose": False}


def annual_samples(job: dict) -> list[dict]:
    module = C.load_script("r3_csdi_data_core", C.ROOT / "scripts/351_wrr_representative_recovery.py")
    panel = read_temperature_panel(job["input_path"])
    panel.columns = panel.columns.astype(str)
    if job["station_id"] not in panel:
        return []
    target = panel[job["station_id"]]
    years = module.complete_years(target)
    rows = []
    for year in years:
        history = target.loc[target.index.year != year].dropna()
        if len(history) < 3 * 365:
            continue
        mean, scale = float(history.mean()), max(float(history.std()), 0.1)
        values = target.loc[target.index.year == year].to_numpy(dtype=float)
        array = np.full((366, 1), np.nan, dtype=np.float32)
        array[: len(values), 0] = (values - mean) / scale
        mask = np.ones((366, 1), dtype=np.float32)
        length = [30, 60, 90][stable_seed("r3-csdi-length", job["station_id"], year) % 3]
        start = stable_seed("r3-csdi-start", job["station_id"], year) % (len(values) - length - 1) + 1
        mask[start : start + length] = 0
        mask[len(values) :] = 0
        rows.append({"station_id": job["station_id"], "provider": job["provider"], "group": job["independence_group"], "year": year, "array": array, "pattern": mask})
    return rows


def training_data(workers: int) -> tuple[dict, dict, pd.DataFrame]:
    core = C.load_script("r3_csdi_source_jobs", C.ROOT / "scripts/351_wrr_representative_recovery.py")
    jobs, _ = core.source_jobs("leave_one_year_out", False)
    groups = pd.read_csv(C.RUN / "r3_06_independence_risk/complete_network_independence.csv").set_index("network_id").independence_group
    jobs = [job for job in jobs if job["statistic_class"] in {"daily_mean", "documented_daily_mean"}]
    for job in jobs:
        job["independence_group"] = groups[job["network_id"]]
    gathered = Parallel(n_jobs=workers)(delayed(annual_samples)(job) for job in jobs)
    samples = [sample for station in gathered for sample in station]
    unique = {}
    for sample in samples:
        unique.setdefault((sample["provider"], sample["station_id"], sample["year"]), sample)
    samples = list(unique.values())
    validation_groups = {sample["group"] for sample in samples if int(hashlib.sha256(f"csdi-validation|{sample['group']}".encode()).hexdigest()[:8], 16) % 5 == 0}
    training = [sample for sample in samples if sample["group"] not in validation_groups]
    validation = {}
    for sample in sorted(samples, key=lambda item: (item["year"], item["station_id"])):
        if sample["group"] in validation_groups:
            validation.setdefault(sample["group"], sample)
    validation = list(validation.values())
    train_set = {"X": np.stack([sample["array"] for sample in training]), "for_pattern_mask": np.stack([sample["pattern"] for sample in training])}
    originals = np.stack([sample["array"] for sample in validation])
    patterns = np.stack([sample["pattern"] for sample in validation])
    masked = originals.copy()
    masked[patterns == 0] = np.nan
    val_set = {"X": masked, "X_ori": originals}
    ledger = pd.DataFrame([{key: value for key, value in sample.items() if key not in {"array", "pattern"}} | {"role": "validation" if sample["group"] in validation_groups else "training"} for sample in samples])
    return train_set, val_set, ledger


def model_instance():
    import torch
    from pypots.imputation import CSDI
    from pypots.optim import Adam

    torch.set_num_threads(8)
    torch.manual_seed(20261020)
    np.random.seed(20261020)
    return CSDI(**MODEL_ARGS, optimizer=Adam(lr=0.001), saving_path=str(OUT / "training"))


def train(workers: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    model_path = OUT / "csdi_reference.pypots"
    if model_path.exists():
        print("[361] existing frozen reference retained", flush=True)
        return
    C.write_json(OUT / "training_contract.json", {"model_arguments": MODEL_ARGS, "sampling_draws_for_reference_evaluation": 8, "evaluation_cases": "all eligible external station-years, replicate-zero 3x3 crossed cells", "primary_reference_point": "H30 of pointwise sample-median completed series", "secondary_reference_point": "sample median of H30 values", "prospective_claim": False, "hyperparameter_selection_on_new_external_outcomes": False, "validation": "one metadata-determined station-year per held-out old independent group", "normalization": "station history excluding evaluation year; observed values preserved"})
    training, validation, ledger = training_data(workers)
    ledger.to_csv(OUT / "old_record_training_membership.csv", index=False)
    np.savez_compressed(OUT / "training_arrays.npz", X=training["X"], patterns=training["for_pattern_mask"], validation_X=validation["X"], validation_X_ori=validation["X_ori"])
    print(f"[361] training on {len(training['X'])} old station-years; {len(validation['X'])} independent validation groups", flush=True)
    model = model_instance()
    model.fit(training, validation)
    model.save(str(model_path))
    C.write_json(OUT / "training_manifest.json", {"model_path": str(model_path), "model_sha256": C.digest(model_path), "n_training_years": len(training["X"]), "n_validation_groups": len(validation["X"]), "new_external_temperature_used_for_training": False, "reference_scope": "retrospective univariate imputation, eight posterior draws, 50 diffusion steps"})
    C.write_json(OUT / "training_fingerprint.json", C.fingerprint(Path(__file__), {"training_membership": OUT / "old_record_training_membership.csv", "contract": OUT / "training_contract.json"}))
    print("[361] frozen probabilistic reference saved", flush=True)


def evaluate(role: str) -> None:
    gate = C.load_script("r3_csdi_external_gate", C.ROOT / "scripts/358_wrr_external_recovery.py")
    gate.verify_role_access(role)
    source = C.RUN / "r3_08_external_recovery" / role / "leave_one_year_out/crossed/cofailure_0"
    frame = pd.read_parquet(source / "cases.parquet")
    frame = frame.loc[frame.replicate.eq(0) & frame.design_family.eq("crossed_contiguous")].copy()
    jobs = json.loads((source / "jobs.json").read_text())["jobs"]
    panels = {job["network_id"]: read_temperature_panel(job["input_path"]) for job in jobs}
    inputs, normalizers = [], []
    for row in frame.itertuples(index=False):
        target = panels[row.network_id][row.station_id]
        values = target.loc[target.index.year == row.year].to_numpy(dtype=float)
        history = target.loc[target.index.year != row.year].dropna()
        mean, scale = float(history.mean()), max(float(history.std()), 0.1)
        observed = np.full((366, 1), np.nan, dtype=np.float32)
        observed[: len(values), 0] = (values - mean) / scale
        mask = np.zeros(len(values), dtype=bool)
        for run in row.mask_runs.split(";"):
            start, length = map(int, run.split(":"))
            mask[start : start + length] = True
        observed[np.flatnonzero(mask), 0] = np.nan
        inputs.append(observed)
        normalizers.append((values, mask, mean, scale))
    model = model_instance()
    model.load(str(OUT / "csdi_reference.pypots"))
    print(f"[361] evaluating {len(frame)} crossed {role} cases with eight draws", flush=True)
    samples = model.predict({"X": np.stack(inputs)}, n_sampling_times=8)["imputation"]
    rows = []
    for position, row in enumerate(frame.itertuples(index=False)):
        truth, mask, mean, scale = normalizers[position]
        trajectories = samples[position, :, : len(truth), 0].astype(float) * scale + mean
        trajectories[:, ~mask] = truth[~mask]
        available = bool(np.isfinite(trajectories).all())
        point = np.median(trajectories, axis=0) if available else np.full(len(truth), np.nan)
        h30_samples = window_means(trajectories).max(axis=1)
        h30_series = float(window_means(point).max())
        h30_functional = float(np.median(h30_samples))
        rows.append({"station_id": row.station_id, "network_id": row.network_id, "independence_group": row.independence_group, "year": row.year, "realization_id": row.realization_id, "gap_length": row.longest_run, "overlap_class": row.overlap_class, "truth_h30": row.truth_hottest30, "available": available, "h30_pointwise_median_series": h30_series, "h30_median_of_samples": h30_functional, "absolute_error_series_point": abs(h30_series - row.truth_hottest30), "absolute_error_functional_point": abs(h30_functional - row.truth_hottest30), "failure_series_point": not available or abs(h30_series - row.truth_hottest30) > 0.5, "failure_functional_point": not available or abs(h30_functional - row.truth_hottest30) > 0.5, "hidden_daily_rmse_C": float(np.sqrt(np.mean((point[mask] - truth[mask]) ** 2))), "n_sampling_draws": 8})
    pd.DataFrame(rows).to_parquet(OUT / f"external_{role}_cases.parquet", index=False)
    C.write_json(OUT / f"external_{role}_fingerprint.json", C.fingerprint(Path(__file__), {"cases": source / "cases.parquet", "model": OUT / "csdi_reference.pypots"}))
    print(f"[361] completed fixed {role} reference evaluation", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluate", choices=["development", "calibration", "test"])
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    C.protocol()
    evaluate(args.evaluate) if args.evaluate else train(args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
