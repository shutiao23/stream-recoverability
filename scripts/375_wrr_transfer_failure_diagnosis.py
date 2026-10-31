#!/usr/bin/env python3
"""Trace frozen failures and separate information loss from domain attribution."""
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
from joblib import Parallel, delayed

import wrr_r3_common as C
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v17_fitness.estimators import StationModels
from stream_recoverability.experiments.v19_revision.data import station_air_series
from stream_recoverability.experiments.v19_revision.learning import predict_score

OUT = C.READY / "followup_20261021/transfer"
KEYS = ["network_id", "station_id", "year", "realization_id"]


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def mask_from_runs(runs, n):
    mask = np.zeros(n, dtype=bool)
    for run in runs.split(";"):
        start, length = map(int, run.split(":"))
        mask[start:start + length] = True
    return mask


def correlation(a, b):
    valid = np.isfinite(a) & np.isfinite(b)
    return float(np.corrcoef(a[valid], b[valid])[0, 1]) if valid.sum() > 2 and np.std(a[valid]) > 0 and np.std(b[valid]) > 0 else np.nan


def finite_mean(values):
    values = np.asarray(values)
    return float(values[np.isfinite(values)].mean()) if np.isfinite(values).any() else np.nan


def diagnose(protocol):
    transfer = C.RUN / "r3_09_frozen_transfer"
    bank = {row["identity"]: row for row in json.loads((transfer / "head_bank.json").read_text())["heads"]}
    plan = next(row for row in json.loads((transfer / "deployment_plans.json").read_text())["plans"]
                if row["mode"] == "frozen_source" and row["target_provider"] == "foen"
                and f"uncertain_support__{protocol}__documented_daily_mean__source_only__all_providers" in row["head_identity"])
    record = bank[plan["head_identity"]]
    head = joblib.load(record["model_path"])
    source = C.RUN / "r3_10_external_decisions/test" / protocol / "admission/cofailure_0/case_information.parquet"
    frame = pd.read_parquet(source)
    frame = frame.loc[frame.provider.eq("foen") & frame.statistic_class.isin(["daily_mean", "documented_daily_mean"])].copy()
    frame["frozen_score"] = predict_score(head["model"], frame, tuple(head["features"]), head["kind"])
    frame["admitted"] = frame.frozen_score <= plan["thresholds"]["empirical"]
    frame["failed_admission"] = frame.admitted & frame.policy_bad
    frame["signed_error_C"] = frame.policy_metric - frame.truth_hottest30
    recovery = C.RUN / "r3_08_external_recovery/test" / protocol / "admission/cofailure_0"
    jobs = json.loads((recovery / "jobs.json").read_text())["jobs"]
    raw = C.ROOT / "data/external/wrr_revision_20261020c/hydroshare"
    q = pd.read_csv(raw / "MEAS_Qt", sep=None, engine="python")
    date = next(name for name in q if name.lower() in {"date", "datetime"})
    q.index = pd.to_datetime(q[date])
    panels = {job["station_id"]: (job, read_temperature_panel(job["input_path"])) for job in jobs if job["station_id"] in set(frame.station_id)}
    diagnosis, daily = [], []
    for (station, year), block in frame.groupby(["station_id", "year"]):
        job, panel = panels[station]
        target = panel[station]
        index = target.index[target.index.year == year]
        truth = target.reindex(index).to_numpy(dtype=float)
        allowed = pd.Series(target.index.year < year if protocol == "strictly_prior_years" else target.index.year != year, index=target.index)
        air = station_air_series(Path(job["air_input_path"]), job["network_id"], station, target.index)
        models = StationModels(target=target, donors=panel.drop(columns=station), air=air, train_mask=allowed)
        center = models.air_predict(index)
        residual = truth - center
        flow = pd.to_numeric(q[station], errors="coerce").where(lambda x: x >= 0) if station in q else pd.Series(dtype=float)
        history = flow.loc[flow.index.year < year if protocol == "strictly_prior_years" else flow.index.year != year]
        monthly = history.groupby(history.index.month).quantile(0.2)
        values = flow.reindex(index).to_numpy(dtype=float)
        limits = pd.Series(index.month).map(monthly).to_numpy(dtype=float)
        low = np.isfinite(values) & np.isfinite(limits) & (values <= limits)
        temperature_air = air.reindex(index).to_numpy(dtype=float) if air is not None else np.full(len(index), np.nan)
        for row in block.itertuples(index=False):
            mask = mask_from_runs(row.mask_runs, len(index))
            diagnosis.append({**{key: getattr(row, key) for key in KEYS}, "gap_start": str(index[np.flatnonzero(mask)[0]].date()),
                              "gap_end": str(index[np.flatnonzero(mask)[-1]].date()), "gap_days": int(mask.sum()),
                              "gap_air_proxy_bias_C": finite_mean(-residual[mask]),
                              "visible_air_proxy_bias_C": finite_mean(-residual[~mask]),
                              "gap_daily_air_water_correlation": correlation(truth[mask], temperature_air[mask]),
                              "visible_daily_air_water_correlation": correlation(truth[~mask], temperature_air[~mask]),
                              "gap_flow_coverage": float(np.isfinite(values[mask]).mean()),
                              "gap_lowflow_fraction": float(low[mask].sum() / np.isfinite(values[mask]).sum()) if np.isfinite(values[mask]).any() else np.nan,
                              "gap_flow_mean": finite_mean(values[mask])})
        if station == "CH_2327":
            daily.append(pd.DataFrame({"date": index, "station_id": station, "year": year, "water_C": truth,
                                       "air_C": temperature_air, "air_proxy_C": center, "flow": values, "lowflow": low}))
    detail = frame.merge(pd.DataFrame(diagnosis), on=KEYS, validate="one_to_one")
    output = OUT / protocol
    output.mkdir(parents=True, exist_ok=True)
    detail.to_parquet(output / "case_diagnosis.parquet", index=False)
    detail.loc[detail.failed_admission].to_csv(output / "accepted_failures.csv", index=False)
    pd.concat(daily, ignore_index=True).to_csv(output / "CH_2327_daily.csv", index=False)
    station_rows, year_rows, influence = [], [], []
    def summary(block):
        return {"n_cases": len(block), "n_station_years": len(block[["station_id", "year"]].drop_duplicates()),
                "admitted": int(block.admitted.sum()), "failures": int(block.failed_admission.sum()),
                "risk": float(block.failed_admission.sum() / block.admitted.sum()) if block.admitted.any() else np.nan,
                "mean_signed_error_C": float(block.signed_error_C.mean()), "h30_mae_C": float(block.abserr_policy.mean())}
    for station, block in detail.groupby("station_id"):
        station_rows.append({"station_id": station, **summary(block)})
        influence.append({"omitted_station": station, **summary(detail.loc[~detail.station_id.eq(station)]),
                          "purpose": "influence diagnosis only; original primary population retained"})
    for (station, year), block in detail.groupby(["station_id", "year"]):
        year_rows.append({"station_id": station, "year": year, **summary(block)})
    pd.DataFrame(station_rows).to_csv(output / "station_results.csv", index=False)
    pd.DataFrame(year_rows).to_csv(output / "station_year_results.csv", index=False)
    pd.DataFrame(influence).to_csv(output / "leave_station_out_influence.csv", index=False)
    # A common source pool with interventions on available information, using precomputed reconstructions.
    source_frame = pd.read_parquet(C.source_cases(protocol))
    source_frame = source_frame.loc[source_frame.statistic_class.isin(["daily_mean", "documented_daily_mean"])].copy()
    information = []
    for label, data in (("source", source_frame), ("Swiss_test", frame)):
        for channel in ("original", "no_donors", "air_only", "local_only"):
            if channel == "original":
                point = data.policy_metric.to_numpy()
                choice = data.policy_choice.to_numpy()
            else:
                methods = {"no_donors": ["air_ridge", "linear_interp", "smooth_climatology", "doy_climatology"],
                           "air_only": ["air_ridge"], "local_only": ["linear_interp", "smooth_climatology", "doy_climatology"]}[channel]
                point = np.full(len(data), np.nan)
                choice = np.full(len(data), "unavailable", dtype=object)
                for method in methods:
                    candidate = data[f"hottest30_{method}"].to_numpy()
                    take = ~np.isfinite(point) & np.isfinite(candidate)
                    if method == "linear_interp":
                        take &= data.longest_run.to_numpy() <= 30
                    point[take], choice[take] = candidate[take], method
            available = np.isfinite(point)
            error = np.abs(point - data.truth_hottest30.to_numpy())
            information.append({"population": label, "information": channel, "n_candidates": len(data), "available": int(available.sum()),
                                "mae_on_available_C": float(error[available].mean()), "failure_fraction_original_pool": float((~available | (error > 0.5)).mean()),
                                "donor_share": float((choice == "donor_ridge").mean()), "air_share": float((choice == "air_ridge").mean()),
                                "interpretation": "paired reconstruction intervention; original screen is not reused with stale uncertainty"})
    pd.DataFrame(information).to_csv(output / "information_channel_reconstruction.csv", index=False)
    C.write_json(output / "run_record.json", run_record({"cases": source, "source_cases": C.source_cases(protocol), "frozen_head": Path(record["model_path"]), "plans": transfer / "deployment_plans.json", "flow": raw / "MEAS_Qt"}, new_confirmation=False, hydrological_causes_identified=False))
    print(f"[375] {protocol}: {int(detail.failed_admission.sum())} frozen failures traced", flush=True)


def rebuild_station(job, settings):
    core = C.load_script("followup_no_donor_worker", C.ROOT / "scripts/351_wrr_representative_recovery.py")
    return core.build_station(job, settings)


def rebuild_no_donors(protocol, workers):
    core = C.load_script("followup_no_donor_core", C.ROOT / "scripts/351_wrr_representative_recovery.py")
    jobs = json.loads((C.source_cases(protocol).parent / "jobs.json").read_text())["jobs"]
    for job in jobs:
        # Full donor co-failure also gives these stations their own cache folder in script 351.
        job["cofailure_fraction"] = 1
    settings = C.protocol()
    results = Parallel(n_jobs=workers, verbose=10)(delayed(rebuild_station)(job, settings) for job in jobs)
    frames = [pd.read_parquet(row["cache"]) for row in results if row.get("cache")]
    frame = pd.concat([block for block in frames if len(block)], ignore_index=True)
    original = pd.read_parquet(C.source_cases(protocol), columns=KEYS + ["mask_runs"])
    matched = original.merge(frame[KEYS + ["mask_runs"]], on=KEYS, suffixes=("_old", "_new"), validate="one_to_one")
    if len(matched) != len(original) or len(frame) != len(original) or not matched.mask_runs_old.equals(matched.mask_runs_new):
        raise RuntimeError("Information intervention changed candidate masks")
    if frame.n_visible_donors.max() != 0:
        raise RuntimeError("Donor intervention did not remove every donor")
    output = OUT / protocol / "source_no_donors"
    output.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output / "cases.parquet", index=False)
    C.write_json(output / "jobs.json", {"jobs": jobs, "results": results})
    C.write_json(output / "run_record.json", run_record({"original_cases": C.source_cases(protocol), "core": Path(core.__file__)}, candidate_masks_unchanged=True, donors_removed_from_reconstruction_and_diagnostics=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], required=True)
    parser.add_argument("--rebuild-source-no-donors", action="store_true")
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()
    if args.rebuild_source_no_donors:
        rebuild_no_donors(args.protocol, args.workers)
    else:
        diagnose(args.protocol)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
