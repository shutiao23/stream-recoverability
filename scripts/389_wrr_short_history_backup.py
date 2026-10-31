#!/usr/bin/env python3
"""Evaluate actual short-history logger gaps without changing primary support."""
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
import requests

import wrr_r3_common as C
from stream_recoverability.experiments.v19_revision.state_trajectory import sample_crps
from stream_recoverability.experiments.v19_revision.trajectory import window_means

BASE = C.READY / "followup_20261021/natural_backup"
OUT = BASE / "short_history"
CONFIG = C.ROOT / "configs/wrr_natural_backup_secondary_20261021.json"
PROBABILITY = C.READY / "followup_20261021/probability_development"


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def conditional_peak_interval(observed, upper_bound_C):
    observed = pd.Series(np.asarray(observed, dtype=float))
    lower = float(observed.rolling(30).mean().max())
    upper = float(observed.fillna(upper_bound_C).rolling(30).mean().max())
    return lower, upper


def sampling_audit(cases):
    rows = []
    raw_root = C.ROOT / "data/external/wrr_followup_backup"
    for case in cases.drop_duplicates(["primary_daily_path", "year"]).to_dict("records"):
        raw = pd.read_csv(raw_root / case["file"], dtype={"Serial": str})
        raw = raw.loc[raw.Station.eq(case["station"]) & raw.Serial.eq(case["primary_serial"])
                      & pd.to_numeric(raw.Latitude, errors="coerce").round(6).eq(case["latitude"])
                      & pd.to_numeric(raw.Longitude, errors="coerce").round(6).eq(case["longitude"])].copy()
        raw["time"] = pd.to_datetime(raw.Time_UTC, format="mixed", utc=True, errors="coerce")
        raw["value"] = pd.to_numeric(raw.WaterTemperature_Celsius, errors="coerce")
        primary = read_daily(case["primary_daily_path"])
        dates = pd.date_range(f"{case['year']}-01-01", f"{case['year']}-12-31")
        for day in dates[primary.reindex(dates).isna()]:
            block = raw.loc[raw.time.dt.date.eq(day.date())]
            finite = block.loc[block.value.between(-2, 40)]
            rows.append({"river": case["river"], "station": case["station"], "primary_serial": case["primary_serial"], "year": case["year"],
                         "missing_qualified_day": str(day.date()), "raw_rows": len(block), "finite_gross_screened_rows": len(finite),
                         "distinct_hours": finite.time.dt.hour.nunique(), "kind": "no_raw_records" if block.empty else "partial_or_unqualified_daily_sampling"})
    return pd.DataFrame(rows)


def read_daily(path):
    frame = pd.read_csv(path, parse_dates=["date"])
    return pd.Series(pd.to_numeric(frame.temperature_C, errors="coerce").to_numpy(), index=frame.date)


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    protocol_record = OUT / "analysis_protocol.json"
    if not protocol_record.exists():
        C.write_json(protocol_record, run_record({"secondary_spec": CONFIG, "reference_qualification": BASE / "qualification_summary.json", "primary_protocol": BASE / "analysis_protocol.json"}, recovery_errors_inspected=False, primary_protocol_not_changed=True))
    eligible = pd.read_csv(BASE / "qualification_exclusions.csv", dtype={"primary_serial": str, "backup_serial": str})
    eligible = eligible.loc[eligible.reason.eq("fewer_than_three_complete_prior_primary_years")].copy()
    eligible.to_csv(OUT / "case_references.csv", index=False)
    rows, arrays, support = [], [], []
    for key, cases in eligible.groupby(["primary_daily_path", "year"], sort=True):
        primary = read_daily(key[0])
        year = int(key[1])
        dates = pd.date_range(f"{year}-01-01", f"{year}-12-31")
        observed = primary.reindex(dates).to_numpy(dtype=float)
        history = primary.loc[primary.index.year < year].dropna()
        values = history.to_numpy() if len(history) >= 30 else observed[np.isfinite(observed)]
        mean, scale = float(values.mean()), max(float(values.std(ddof=1)), 0.1)
        record = cases.iloc[0]
        source_id = f"{Path(key[0]).stem}_{year}"
        air_file = OUT / f"air_{source_id}.json"
        first_year = int(min(primary.index.year.min(), year - 1))
        if not air_file.exists():
            response = requests.get("https://power.larc.nasa.gov/api/temporal/daily/point", params={"parameters": "T2M", "community": "AG", "longitude": record.longitude, "latitude": record.latitude,
                                     "start": f"{first_year}0101", "end": f"{year}1231", "format": "JSON", "time-standard": "UTC"}, timeout=120)
            response.raise_for_status()
            air_file.write_bytes(response.content)
        forcing = json.loads(air_file.read_text())["properties"]["parameter"]["T2M"]
        air = pd.Series({pd.to_datetime(day, format="%Y%m%d"): float(value) if float(value) > -900 else np.nan for day, value in forcing.items()}).sort_index()
        historical_air = air.loc[air.index.year < year].dropna()
        air_mean, air_scale = float(historical_air.mean()), max(float(historical_air.std()), 0.1)
        array = np.full((366, 2), np.nan, dtype=np.float32)
        array[:len(dates), 0] = (observed - mean) / scale
        array[:len(dates), 1] = (air.reindex(dates).to_numpy() - air_mean) / air_scale
        arrays.append(array)
        for upper_bound in (40, 60, 100):
            lower, upper = conditional_peak_interval(observed, upper_bound)
            support.append({"input_id": source_id, "river": record.river, "year": year, "assumed_upper_C": upper_bound,
                            "observed_window_lower_C": lower, "conditional_h30_upper_C": upper, "conditionally_identified": bool(abs(upper - lower) < 1e-8),
                            "interpretation": "illustrative support sensitivity, not a verified physical or sensor-error guarantee"})
        rows.append({"input_id": source_id, "primary_daily_path": key[0], "year": year, "station": record.station, "river": record.river, "primary_serial": record.primary_serial,
                     "mean": mean, "scale": scale, "n_days": len(dates), "prior_finite_days": len(history), "normalization_origin": "earlier_primary_observations" if len(history) >= 30 else "visible_current_primary",
                     "latest_prior_date": str(history.index.max().date()) if len(history) else None, "air_path": str(air_file)})
    np.savez_compressed(OUT / "inputs.npz", X=np.stack(arrays))
    pd.DataFrame(rows).to_csv(OUT / "input_records.csv", index=False)
    pd.DataFrame(support).to_csv(OUT / "conditional_peak_support.csv", index=False)
    sampling_audit(eligible).to_csv(OUT / "gap_sampling_audit.csv", index=False)
    C.write_json(OUT / "preparation.json", {"n_pair_year_references": len(eligible), "n_unique_primary_year_inputs": len(rows), "independent_cohort_count": 1,
                 "backup_values_in_model_input": False, "NASA_forcing_is_free_input_not_costly_query": True, "primary_support_relaxed": False})
    C.write_json(OUT / "preparation_run_record.json", run_record({"specification": CONFIG, "references": OUT / "case_references.csv", "inputs": OUT / "inputs.npz"}, recovery_errors_used_for_selection=False))
    print(f"[389] prepared {len(rows)} primary inputs and {len(eligible)} measured backup references", flush=True)


def evaluate(method):
    records = pd.read_csv(OUT / "input_records.csv")
    references = pd.read_csv(OUT / "case_references.csv", dtype={"primary_serial": str, "backup_serial": str})
    inputs = np.load(OUT / "inputs.npz")["X"]
    samples = None
    if method == "csdi_old":
        core = C.load_script("backup_old_CSDI", C.ROOT / "scripts/361_wrr_probabilistic_reference.py")
        model = core.model_instance()
        model.load(str(C.RUN / "r3_11_probabilistic_reference/csdi_reference.pypots"))
        samples = model.predict({"X": inputs[:, :, :1]}, n_sampling_times=8)["imputation"]
    elif method == "csdi_developed":
        selection = json.loads((PROBABILITY / "selection.json").read_text())
        core = C.load_script("backup_developed_CSDI", C.ROOT / "scripts/385_wrr_probability_development.py")
        model = core.model_instance(selection["selected"], 4)
        model.load(str(PROBABILITY / selection["selected"] / "model.pypots"))
        samples = model.predict({"X": inputs}, n_sampling_times=32)["imputation"]
    rows = []
    for position, record in enumerate(records.to_dict("records")):
        primary = read_daily(record["primary_daily_path"])
        dates = pd.date_range(f"{record['year']}-01-01", f"{record['year']}-12-31")
        observed = primary.reindex(dates).to_numpy(dtype=float)
        missing = ~np.isfinite(observed)
        if method == "linear_interp":
            positions = np.arange(len(observed))
            completed = observed.copy()
            completed[missing] = np.interp(positions[missing], positions[~missing], observed[~missing])
            h30_samples = np.array([float(window_means(completed).max())])
        elif method == "air2stream3":
            from stream_recoverability.experiments import air2stream_equivalent as physics
            from stream_recoverability.experiments.v19_revision.process import enable_compiled_reference, simulate_three
            enable_compiled_reference()
            payload = json.loads(Path(record["air_path"]).read_text())["properties"]["parameter"]["T2M"]
            air = pd.Series({pd.to_datetime(day, format="%Y%m%d"): float(value) if float(value) > -900 else np.nan for day, value in payload.items()}).sort_index()
            prior_dates = air.index[air.index.year < record["year"]]
            try:
                fit = physics.fit_air2stream3(prior_dates, primary.reindex(prior_dates).to_numpy(), air.reindex(prior_dates).to_numpy())
                completed = observed.copy()
                starts = np.flatnonzero(missing & ~np.r_[False, missing[:-1]])
                ends = np.flatnonzero(missing & ~np.r_[missing[1:], False]) + 1
                for start, end in zip(starts, ends):
                    section = slice(start - 1, end)
                    values = simulate_three(dates[section], air.reindex(dates[section]).to_numpy(), fit.parameters, initial_water_temperature_c=float(observed[start - 1]))
                    completed[start:end] = values[1:]
                h30_samples = np.array([float(window_means(completed).max())])
                availability_reason = "available"
            except ValueError as error:
                h30_samples = None
                availability_reason = str(error)
        elif method.startswith("csdi"):
            completed = samples[position, :, :len(observed), 0].astype(float) * record["scale"] + record["mean"]
            completed[:, ~missing] = observed[~missing]
            h30_samples = window_means(completed).max(axis=1)
        else:
            raise ValueError(method)
        available = h30_samples is not None and np.isfinite(h30_samples).all()
        point = float(np.median(h30_samples)) if available else np.nan
        candidates = references.loc[references.primary_daily_path.eq(record["primary_daily_path"]) & references.year.eq(record["year"])]
        for case in candidates.to_dict("records"):
            backup = read_daily(case["backup_daily_path"]).reindex(dates).to_numpy(dtype=float)
            truth = observed.copy()
            truth[missing] = backup[missing]
            if not np.isfinite(truth).all():
                raise RuntimeError("A qualified backup reference is incomplete")
            truth_h30 = float(window_means(truth).max())
            lower, upper = np.quantile(h30_samples, [.05, .95]) if available else (np.nan, np.nan)
            rows.append({"method": method, "input_id": record["input_id"], "river": case["river"], "station": case["station"], "year": case["year"],
                         "primary_serial": case["primary_serial"], "backup_serial": case["backup_serial"], "missing_days": int(missing.sum()),
                         "available": bool(available), "availability_reason": availability_reason if method == "air2stream3" else "available" if available else "nonfinite_prediction",
                         "h30_point": point, "reference_h30": truth_h30, "absolute_error_C": abs(point - truth_h30), "reference_failure": bool(abs(point - truth_h30) > .5) if available else None,
                         "reference_CRPS_C": sample_crps(h30_samples, truth_h30) if available else np.nan, "covered90": bool(lower <= truth_h30 <= upper) if available else None, "interval_width_C": float(upper - lower),
                         "n_samples": len(h30_samples) if available else 0, "original_complete_history_support": False, "original_protocol_action": "unknown_outside_validated_support",
                         "free_backup_union_error_C": 0.0, "qualification": "winter partial daily sampling deficits; sensor-record reference; one dependent provincial cohort",
                         "illustrative_action_18C": int(point > 18) if available else 2, "illustrative_action_20C": int(point > 20) if available else 2,
                         "reference_hot_18C": bool(truth_h30 > 18), "reference_hot_20C": bool(truth_h30 > 20)})
    result = pd.DataFrame(rows)
    result.to_csv(OUT / f"{method}_results.csv", index=False)
    dependencies = {"specification": CONFIG, "inputs": OUT / "inputs.npz", "references": OUT / "case_references.csv"}
    if method == "csdi_old":
        dependencies["checkpoint"] = C.RUN / "r3_11_probabilistic_reference/csdi_reference.pypots"
    elif method == "csdi_developed":
        dependencies["selection"] = PROBABILITY / "selection.json"
        dependencies["checkpoint"] = PROBABILITY / selection["selected"] / "model.pypots"
    C.write_json(OUT / f"{method}_run_record.json", run_record(dependencies, reference_only_backup=True, original_support_unchanged=True, no_independent_case_risk_guarantee=True))
    print(f"[389] {method}: {len(result)} reference comparisons, {result.input_id.nunique()} primary years", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "evaluate"])
    parser.add_argument("--method", choices=["linear_interp", "air2stream3", "csdi_old", "csdi_developed"], default="linear_interp")
    args = parser.parse_args()
    prepare() if args.action == "prepare" else evaluate(args.method)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
