#!/usr/bin/env python3
"""Air2stream-3/8 recovery using training-only calibration and observed gap anchors."""

from __future__ import annotations

import os

for thread_variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[thread_variable] = "1"

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_r3_common as C

from stream_recoverability.experiments import air2stream_equivalent as physics
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v17_fitness.paths import stable_seed
from stream_recoverability.experiments.v19_revision.process import enable_compiled_reference, simulate_eight, simulate_three
from stream_recoverability.experiments.v19_revision.trajectory import window_means

OUT = C.RUN / "r3_12_process_reference"
RAW = C.ROOT / "data/external/wrr_revision_20261020c/hydroshare"


def forcing_table(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, sep=None, engine="python")
    date = next(name for name in frame if name.lower() in {"date", "datetime"})
    frame.index = pd.to_datetime(frame[date], errors="coerce")
    return frame.drop(columns=date).apply(pd.to_numeric, errors="coerce")


def calibration_segment(index: pd.DatetimeIndex, water: np.ndarray, air: np.ndarray, flow: np.ndarray | None, year: int, prospective: bool) -> tuple[int, int]:
    allowed = index.year < year if prospective else index.year != year
    valid = allowed & np.isfinite(air)
    if flow is not None:
        valid &= np.isfinite(flow) & (flow > 0)
    starts = np.flatnonzero(valid & ~np.r_[False, valid[:-1]])
    ends = np.flatnonzero(valid & ~np.r_[valid[1:], False]) + 1
    if not len(starts):
        raise ValueError("No continuous permitted forcing period")
    counts = [np.isfinite(water[start:end]).sum() for start, end in zip(starts, ends)]
    selected = int(np.argmax(counts))
    return int(starts[selected]), int(ends[selected])


def station_reference(job: dict, cases: pd.DataFrame, protocol_name: str) -> pd.DataFrame:
    enable_compiled_reference()
    panel = read_temperature_panel(job["input_path"])
    panel.columns = panel.columns.astype(str)
    target = pd.to_numeric(panel[job["station_id"]], errors="coerce")
    air_data, flow_data = forcing_table(RAW / "CERRA_Ta"), forcing_table(RAW / "MEAS_Qt")
    if job["station_id"] not in air_data:
        return pd.DataFrame([{**row, "method": method, "status": "air_forcing_unavailable"} for row in cases.to_dict("records") for method in ["air2stream3", "air2stream8"]])
    air = air_data[job["station_id"]].reindex(target.index).to_numpy(dtype=float)
    flow = flow_data[job["station_id"]].reindex(target.index).to_numpy(dtype=float) if job["station_id"] in flow_data else None
    water = target.to_numpy(dtype=float)
    output = []
    for year, records in cases.groupby("year"):
        for method in ("air2stream3", "air2stream8"):
            fitted = None
            status = "available"
            try:
                if method == "air2stream8" and flow is None:
                    raise ValueError("Discharge unavailable")
                start, end = calibration_segment(target.index, water, air, flow if method == "air2stream8" else None, int(year), protocol_name == "strictly_prior_years")
                dates = target.index[start:end]
                if int(year) in dates.year or (protocol_name == "strictly_prior_years" and dates.year.max() >= year):
                    raise RuntimeError("Target or future observations reached process-model calibration")
                if method == "air2stream3":
                    fitted = physics.fit_air2stream3(dates, water[start:end], air[start:end], max_nfev=200)
                else:
                    fitted = physics.fit_air2stream8(dates, water[start:end], air[start:end], flow[start:end], max_nfev=500, seed=stable_seed("r3-air2stream", job["station_id"], year))
            except ValueError as error:
                status = str(error)
            target_index = target.index[target.index.year == year]
            truth = target.loc[target_index].to_numpy(dtype=float)
            yearly_air = pd.Series(air, index=target.index).reindex(target_index).to_numpy(dtype=float)
            yearly_flow = pd.Series(flow, index=target.index).reindex(target_index).to_numpy(dtype=float) if flow is not None else None
            for row in records.to_dict("records"):
                result = {"station_id": job["station_id"], "network_id": job["network_id"], "independence_group": job["independence_group"], "year": int(year), "realization_id": row["realization_id"], "gap_length": row["longest_run"], "overlap_class": row["overlap_class"], "method": method, "status": status, "truth_h30": row["truth_hottest30"]}
                if fitted is None:
                    output.append(result)
                    continue
                completed = truth.copy()
                try:
                    for run in row["mask_runs"].split(";"):
                        gap_start, gap_length = map(int, run.split(":"))
                        if gap_start < 1:
                            raise ValueError("No observed left anchor for process recovery")
                        gap_end = gap_start + gap_length
                        segment = slice(gap_start - 1, gap_end)
                        if method == "air2stream3":
                            reconstructed = simulate_three(target_index[segment], yearly_air[segment], fitted.parameters, initial_water_temperature_c=float(truth[gap_start - 1]))
                        else:
                            reconstructed = simulate_eight(target_index[segment], yearly_air[segment], yearly_flow[segment], fitted.parameters, initial_water_temperature_c=float(truth[gap_start - 1]), discharge_reference=fitted.discharge_reference)
                        completed[gap_start:gap_end] = reconstructed[1:]
                    value = float(window_means(completed).max())
                    if not np.isfinite(value):
                        raise ValueError("Nonfinite process reconstruction")
                    result.update({"h30_reconstructed": value, "absolute_error_C": abs(value - row["truth_hottest30"]), "consequential_failure": abs(value - row["truth_hottest30"]) > 0.5, "n_training_observations": fitted.n_training_observations, "training_first_date": str(dates.min().date()), "training_last_date": str(dates.max().date()), "parameters": json.dumps(fitted.parameters.tolist())})
                    result.update({"training_rmse_C": fitted.training_rmse, "optimizer_status": fitted.optimizer_status})
                except ValueError as error:
                    result["status"] = str(error)
                output.append(result)
    return pd.DataFrame(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["development", "calibration", "test"], default="development")
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], default="leave_one_year_out")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    C.protocol()
    gate = C.load_script("r3_process_external_gate", C.ROOT / "scripts/358_wrr_external_recovery.py")
    gate.verify_role_access(args.role)
    source = C.RUN / "r3_08_external_recovery" / args.role / args.protocol / "crossed/cofailure_0"
    frame = pd.read_parquet(source / "cases.parquet")
    frame = frame.loc[frame.replicate.eq(0) & frame.design_family.eq("crossed_contiguous")]
    if args.protocol == "strictly_prior_years":
        frame = frame.loc[frame.year.between(2019, 2022)]
    jobs = json.loads((source / "jobs.json").read_text())["jobs"]
    selected = [(job, frame.loc[frame.station_id.eq(job["station_id"])]) for job in jobs]
    selected = [(job, rows) for job, rows in selected if len(rows)]
    print(f"[362] {len(selected)} stations, process references on identical crossed cases", flush=True)
    results = Parallel(n_jobs=args.workers, verbose=10)(delayed(station_reference)(job, rows, args.protocol) for job, rows in selected)
    output = OUT / args.role / args.protocol
    output.mkdir(parents=True, exist_ok=True)
    cases = pd.concat(results, ignore_index=True)
    cases.to_parquet(output / "cases.parquet", index=False)
    cases.groupby(["method", "status"]).size().to_csv(output / "availability.csv")
    C.write_json(output / "protocol_fingerprint.json", C.fingerprint(Path(__file__), {"cases": source / "cases.parquet", "air": RAW / "CERRA_Ta", "flow": RAW / "MEAS_Qt", "published_equation_implementation": C.ROOT / "src/stream_recoverability/experiments/air2stream_equivalent.py"}, normalization="training forcing only; target year excluded; strictly earlier segment prospectively", anchor="last visible target observation preceding each interior outage"))
    print(f"[362] {len(cases)} process-method cases, availability reported explicitly", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
