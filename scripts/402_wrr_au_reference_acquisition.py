#!/usr/bin/env python3
"""Acquire and qualify provider daily means while new prediction errors stay sealed."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json

import numpy as np
import pandas as pd
import requests

import wrr_r3_common as C

RAW = C.ROOT / "data/external/wrr_au_confirmation_20261021"
OUT = C.READY / "followup_20261021/au_confirmation"
CONFIG = C.ROOT / "configs/wrr_au_reference_qualification_20261021.json"
ENDPOINT = "https://www.bom.gov.au/waterdata/services"


def metadata_can_support(row, year):
    return str(row["from"])[:10] <= f"{year - 3}-01-01" and str(row["to"])[:10] >= f"{year}-12-31"


def requested_stations(settings, frame):
    rows = []
    for row in frame.loc[frame.role.isin(settings["roles"]["target_years"])].to_dict("records"):
        if any(metadata_can_support(row, year) for year in settings["roles"]["target_years"][row["role"]]):
            rows.append(row)
    return rows


def request_parameters(row, settings):
    if not str(row["ts_id"]).isdigit():
        raise ValueError("Unexpected public timeseries identifier")
    return {"service": "kisters", "type": "queryServices", "request": "getTimeseriesValues",
            "datasource": "0", "format": "dajson", "ts_id": str(row["ts_id"]),
            "from": settings["archive_from"], "to": settings["archive_through"],
            "timezone": "individual", "dateformat": "yyyy-MM-dd'T'HH:mm:ssXXX",
            "returnfields": "Timestamp,Value,Quality Code,Aggregation Accuracy",
            "metadata": "true",
            "md_returnfields": "ts_id,ts_name,station_id,station_no,station_name,ts_unitsymbol,timezone,parametertype_name,ts_spacing"}


def acquire_one(row, settings):
    path = RAW / "daily_references" / f"{row['station_id']}_{row['ts_id']}.json"
    request_path = path.with_suffix(".request.json")
    parameters = request_parameters(row, settings)
    if path.exists():
        old = json.loads(request_path.read_text())
        if old["parameters"] != parameters:
            raise RuntimeError("Cached daily-reference request changed")
        return {"station_id": row["station_id"], "status": "acquired", "path": str(path.relative_to(C.ROOT)),
                "bytes": path.stat().st_size}
    response = requests.get(ENDPOINT, params=parameters, timeout=120, stream=True)
    if response.status_code != 200:
        return {"station_id": row["station_id"], "status": "pending_access", "http_status": response.status_code,
                "url": response.url, "eligible_reference_years": None}
    temporary = path.with_suffix(".partial")
    path.parent.mkdir(exist_ok=True, parents=True)
    total = 0
    with temporary.open("wb") as handle:
        for block in response.iter_content(1 << 20):
            total += len(block)
            if total > 64 << 20:
                raise RuntimeError("Single daily-mean response exceeded 64 MiB")
            handle.write(block)
    payload = json.loads(temporary.read_text())
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict) or "data" not in payload[0]:
        error = payload if isinstance(payload, dict) else {"schema": "unexpected"}
        temporary.unlink()
        return {"station_id": row["station_id"], "status": "pending_response_schema", "details": error,
                "eligible_reference_years": None}
    entry = payload[0]
    if str(entry.get("ts_id")) != str(row["ts_id"]):
        raise ValueError("Provider response timeseries does not match the frozen metadata")
    temporary.replace(path)
    C.write_json(request_path, {"endpoint": ENDPOINT, "parameters": parameters,
                               "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
                               "prediction_errors_opened": False})
    return {"station_id": row["station_id"], "status": "acquired", "path": str(path.relative_to(C.ROOT)),
            "bytes": total}


def fetch(workers):
    settings = json.loads(CONFIG.read_text())
    frame = pd.read_csv(OUT / "metadata_candidates_and_roles.csv", dtype={"station_id": str, "ts_id": str, "station_no": str})
    stations = requested_stations(settings, frame)
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(acquire_one, row, settings): row["station_id"] for row in stations}
        for future in as_completed(futures):
            identifier = futures[future]
            try:
                result = future.result()
            except (requests.RequestException, ValueError, RuntimeError) as error:
                result = {"station_id": identifier, "status": "pending_acquisition_error",
                          "error": str(error), "eligible_reference_years": None}
            results.append(result)
            print(f"[402] {len(results)}/{len(stations)} {identifier} {result['status']}", flush=True)
    results.sort(key=lambda item: item["station_id"])
    C.write_json(OUT / "daily_acquisition.json", {
        "requested_stations": len(stations), "results": results,
        "pending_stations": sum(item["status"] != "acquired" for item in results),
        "new_prediction_errors_opened": False,
        "pending_access_is_not_zero_underlying_data": True})
    return int(any(item["status"] != "acquired" for item in results))


def qualified_daily(entry, row, settings):
    columns = entry.get("columns")
    if isinstance(columns, str):
        columns = [name.strip() for name in columns.split(",")]
    if not isinstance(columns, list) or not {"Timestamp", "Value", "Quality Code"}.issubset(columns):
        raise ValueError("Unverified native daily-mean columns")
    if "Aggregation Accuracy %" in columns:
        if "Aggregation Accuracy" in columns:
            raise ValueError("Ambiguous aggregation-accuracy columns")
        columns = ["Aggregation Accuracy" if name == "Aggregation Accuracy %" else name for name in columns]
    if any(name.startswith("Aggregation Accuracy") and name != "Aggregation Accuracy" for name in columns):
        raise ValueError("Unverified aggregation-accuracy units")
    frame = pd.DataFrame(entry["data"], columns=columns)
    if frame.empty:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([])), {"native_rows": 0, "qualified_daily_values": 0, "conflicting_approved_days": 0}
    timestamps = pd.to_datetime(frame.Timestamp, utc=True, errors="raise", format="mixed")
    offset = float(row["local_standard_offset_hours"])
    if not np.isfinite(offset):
        raise ValueError("Unverified provider local-day offset")
    local = (timestamps + pd.to_timedelta(offset, unit="h")).dt.tz_localize(None)
    if not local.eq(local.dt.normalize()).all():
        raise ValueError("Daily-mean timestamps do not identify verified local-standard midnights")
    values = pd.to_numeric(frame.Value, errors="coerce")
    code = pd.to_numeric(frame["Quality Code"], errors="coerce")
    valid = code.eq(settings["daily_reference"]["quality_code"]) & np.isfinite(values)
    valid &= ~values.isin(settings["daily_reference"]["sentinel_values"])
    if "Aggregation Accuracy" in frame:
        raw_accuracy = frame["Aggregation Accuracy"]
        accuracy = pd.to_numeric(raw_accuracy, errors="coerce")
        empty = raw_accuracy.isna() | raw_accuracy.astype(str).str.strip().isin(["", "null", "None", "NaN", "nan"])
        if (accuracy.isna() & ~empty).any() or (accuracy.notna() & ~accuracy.between(0, 100)).any():
            raise ValueError("Unverified aggregation-accuracy units or missing-value code")
        valid &= empty | accuracy.ge(settings["daily_reference"]["minimum_aggregation_accuracy_percent_when_reported"])
    approved = pd.DataFrame({"date": local.dt.normalize(), "value": values.where(valid)})
    conflicts = approved.groupby("date").value.nunique(dropna=True)
    conflict_dates = conflicts.index[conflicts > 1]
    approved.loc[approved.date.isin(conflict_dates), "value"] = np.nan
    # A missing/unapproved duplicate never erases an available approved value.
    daily = approved.groupby("date").value.first().sort_index()
    return daily, {"native_rows": len(frame), "native_quality_A_rows": int(code.eq(10).sum()),
                   "qualified_daily_values": int(daily.notna().sum()),
                   "conflicting_approved_days": len(conflict_dates)}


def complete_years(series):
    years = []
    for year in sorted(set(series.index.year)):
        dates = pd.date_range(f"{year}-01-01", f"{year}-12-31")
        if series.reindex(dates).notna().all():
            years.append(int(year))
    return years


def qualify():
    settings = json.loads(CONFIG.read_text())
    frame = pd.read_csv(OUT / "metadata_candidates_and_roles.csv", dtype={"station_id": str, "ts_id": str, "station_no": str})
    acquisition = json.loads((OUT / "daily_acquisition.json").read_text())
    acquired = {item["station_id"]: item for item in acquisition["results"]}
    rows, native_quality = [], []
    for row in frame.loc[frame.role.isin(settings["roles"]["target_years"])].to_dict("records"):
        identifier = row["station_id"]
        needed = any(metadata_can_support(row, year) for year in settings["roles"]["target_years"][row["role"]])
        source = acquired.get(identifier)
        if not needed:
            status = "metadata_time_bounds_preclude_required_reference"
            daily, history = None, []
        elif source is None or source["status"] != "acquired":
            status = "pending_reference_acquisition"
            daily, history = None, []
        else:
            path = C.ROOT / source["path"]
            entry = json.loads(path.read_text())[0]
            try:
                daily, quality = qualified_daily(entry, row, settings)
                history = complete_years(daily)
                (RAW / "qualified_daily").mkdir(exist_ok=True)
                daily.rename("temperature_C").to_csv(RAW / "qualified_daily" / f"{identifier}.csv", index_label="date")
                status = "reference_QC_evaluated"
                native_quality.append({"station_id": identifier, **quality,
                                       "complete_calendar_years": ";".join(map(str, history))})
            except ValueError as error:
                status = "pending_reference_schema_or_calendar_definition"
                daily, history = None, []
                native_quality.append({"station_id": identifier, "pending_reason": str(error)})
        for year in settings["roles"]["target_years"][row["role"]]:
            metadata_possible = metadata_can_support(row, year)
            if not metadata_possible:
                eligible, reason, missing, n_prior = False, "metadata_time_bounds_preclude_required_reference", None, None
            elif daily is None:
                eligible, reason, missing, n_prior = None, status, None, None
            else:
                dates = pd.date_range(f"{year}-01-01", f"{year}-12-31")
                missing = int(daily.reindex(dates).isna().sum())
                n_prior = sum(prior < year for prior in history)
                eligible = missing == 0 and n_prior >= settings["daily_reference"]["minimum_complete_strictly_prior_primary_years"]
                reason = "eligible_reference_only" if eligible else "incomplete_quality_A_target_year" if missing else "fewer_than_three_complete_prior_primary_years"
            rows.append({"station_id": identifier, "station_no": row["station_no"], "station_name": row["station_name"],
                         "independence_group": row["independence_group"], "role": row["role"], "year": year,
                         "reference_eligible": eligible, "qualification_status": reason,
                         "missing_qualified_target_days": missing, "complete_prior_primary_years": n_prior,
                         "native_sampling_support_verified": False,
                         "primary_evaluation_eligible": False,
                         "new_prediction_errors_opened": False})
    cases = pd.DataFrame(rows)
    cases.to_csv(OUT / "reference_station_year_qualification.csv", index=False)
    pd.DataFrame(native_quality).to_csv(OUT / "daily_reference_quality.csv", index=False)
    eligible = cases.reference_eligible.eq(True)
    pending = cases.reference_eligible.isna()
    C.write_json(OUT / "reference_summary.json", {
        "metadata_resolved_stations": int(frame.role.ne("pending_metadata").sum()),
        "metadata_pending_stations_not_evaluated": int(frame.role.eq("pending_metadata").sum()),
        "candidate_station_years_with_fixed_roles": len(cases),
        "qualified_reference_station_years": int(eligible.sum()),
        "qualification_scope": "provider daily-mean/quality/calendar/history checks only; a separate native-sampling support audit is required before primary evaluation",
        "native_sampling_support_verified_for_full_years": False,
        "primary_evaluation_reference_station_years_released": 0,
        "pending_reference_station_years": int(pending.sum()),
        "qualified_station_years_by_role": cases.loc[eligible].role.value_counts().to_dict(),
        "qualified_components_by_role": cases.loc[eligible].groupby("role").independence_group.nunique().to_dict(),
        "qualified_reference_is_not_a_completed_prediction_test": True,
        "new_test_prediction_errors_opened": False,
        "natural_gap_independent_backup_validation_completed": False})
    print(f"[402] {int(eligible.sum())} qualified new reference station-years; {int(pending.sum())} pending; test prediction errors remain sealed", flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["fetch", "qualify"])
    parser.add_argument("--workers", type=int, default=2, choices=[1, 2, 3])
    args = parser.parse_args()
    return fetch(args.workers) if args.action == "fetch" else qualify()


if __name__ == "__main__":
    raise SystemExit(main())
