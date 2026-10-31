#!/usr/bin/env python3
"""Hold target years fixed while varying history and boundary/fragmented gaps."""
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
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v17_fitness.estimators import StationModels, usable_donors
from stream_recoverability.experiments.v19_revision.data import station_air_series
from stream_recoverability.experiments.v19_revision.trajectory import window_means

OUT = C.READY / "followup_20261021/history_boundaries"


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def station(job, protocol):
    core = C.load_script("followup_history_core", C.ROOT / "scripts/351_wrr_representative_recovery.py")
    panel = read_temperature_panel(job["input_path"]).asfreq("D")
    panel.columns = panel.columns.astype(str)
    target, donors = panel[job["station_id"]], panel.drop(columns=job["station_id"])
    years = core.complete_years(target)
    air = station_air_series(Path(job["air_input_path"]), job["network_id"], job["station_id"], panel.index)
    rows, exclusions = [], []
    for year in years:
        if protocol == "strictly_prior_years" and not 2019 <= year <= 2022:
            continue
        permitted = [value for value in years if (value < year if protocol == "strictly_prior_years" else value != year)]
        if len(permitted) < 10:
            exclusions.append({"station_id": job["station_id"], "year": year, "reason": "fewer_than_ten_shared_eligible_history_years"})
            continue
        order = sorted(permitted, reverse=True) if protocol == "strictly_prior_years" else sorted(permitted, key=lambda value: (abs(value - year), value))
        index = target.index[target.index.year == year]
        truth = target.reindex(index).to_numpy(dtype=float)
        for budget in (3, 5, 10):
            training_years = order[:budget]
            allowed = pd.Series(target.index.year.isin(training_years), index=target.index)
            model = StationModels(target=target, donors=donors, air=air, train_mask=allowed)
            training_h30 = [float(window_means(target.loc[target.index.year == value].to_numpy()).max()) for value in training_years]
            threshold = float(np.quantile(training_h30, 0.9))
            climate_start = int(np.argmax(window_means(model.smooth_climatology(index))))
            designs = {"start30": [(0, 30)], "end30": [(len(index) - 30, 30)], "start90": [(0, 90)],
                       "end90": [(len(index) - 90, 90)], "interior60": [(170, 60)], "fragmented60": [(140, 30), (210, 30)]}
            for name, runs in designs.items():
                mask = np.zeros(len(index), dtype=bool)
                for start, length in runs:
                    mask[start:start + length] = True
                observed = truth.copy()
                observed[mask] = np.nan
                visible = usable_donors(donors, index, mask)
                fills = core.predictions(model, observed, index, visible)
                choice = core.select_policy(fills, mask, max(length for _, length in runs))
                completed = observed.copy()
                if choice:
                    completed[mask] = fills[choice][mask]
                point = float(window_means(completed).max()) if np.isfinite(completed).all() else np.nan
                rows.append({"protocol": protocol, "role": job["split_role"], "station_id": job["station_id"], "network_id": job["network_id"],
                             "independence_group": job["independence_group"], "year": year, "history_years": budget, "training_years": ";".join(map(str, training_years)),
                             "latest_training_year": max(training_years), "design": name, "policy_choice": choice or "unavailable", "available": np.isfinite(point),
                             "h30_point": point, "truth_h30": float(window_means(truth).max()), "absolute_error_C": abs(point - window_means(truth).max()),
                             "failed": not np.isfinite(point) or abs(point - window_means(truth).max()) > 0.5,
                             "local_q90_C": threshold, "climate_peak_start": climate_start})
    return pd.DataFrame(rows), pd.DataFrame(exclusions)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    jobs, inputs = [], {}
    for role in ("development", "test"):
        path = C.RUN / "r3_08_external_recovery" / role / args.protocol / "admission/cofailure_0/jobs.json"
        inputs[role] = path
        jobs.extend(job for job in json.loads(path.read_text())["jobs"] if job["provider"] == "foen")
    result = Parallel(n_jobs=args.workers)(delayed(station)(job, args.protocol) for job in jobs)
    cases = pd.concat([frame for frame, _ in result], ignore_index=True)
    output = OUT / args.protocol
    output.mkdir(parents=True, exist_ok=True)
    cases.to_parquet(output / "cases.parquet", index=False)
    pd.concat([frame for _, frame in result], ignore_index=True).to_csv(output / "exclusions.csv", index=False)
    cases.groupby(["history_years", "design"]).agg(n=("year", "size"), groups=("independence_group", "nunique"),
        available=("available", "sum"), mae_C=("absolute_error_C", "mean"), failure_fraction=("failed", "mean")).to_csv(output / "summary.csv")
    # Fixed target-year contrasts expose historical-threshold and peak-position instability.
    annual = cases.drop_duplicates(["network_id", "station_id", "year", "history_years"])
    wide = annual.pivot(index=["independence_group", "network_id", "station_id", "year"], columns="history_years", values=["local_q90_C", "climate_peak_start"])
    differences = wide.index.to_frame(index=False)
    differences["threshold_3_minus_10_C"] = (wide[("local_q90_C", 3)] - wide[("local_q90_C", 10)]).to_numpy()
    differences["peak_start_3_minus_10_days"] = (wide[("climate_peak_start", 3)] - wide[("climate_peak_start", 10)]).to_numpy()
    differences.to_csv(output / "history_target_differences.csv", index=False)
    C.write_json(output / "run_record.json", run_record(inputs, same_target_years_across_history_budgets=True, new_confirmation=False, reference_minimum_ten_years="comparison subset only; does not replace primary population"))
    print(f"[382] {args.protocol}: {len(cases)} history/boundary cases", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
