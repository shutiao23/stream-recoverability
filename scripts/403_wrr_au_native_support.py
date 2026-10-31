#!/usr/bin/env python3
"""Verify native sampling support without computing a new H30 prediction error."""
from __future__ import annotations

import argparse
import calendar
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import importlib
import json
import time

import numpy as np
import pandas as pd
import requests

import wrr_r3_common as C

R = importlib.import_module("402_wrr_au_reference_acquisition")
F = importlib.import_module("399_wrr_neon_recruitment_feasibility")
RAW, OUT, CONFIG = R.RAW, R.OUT, R.CONFIG
DIRECTORY = RAW / "native_support"


def quarterly_parameters(parameters, year):
    offset = parameters["from"][19:]
    result = []
    for first, last in [(1, 3), (4, 6), (7, 9), (10, 12)]:
        item = dict(parameters)
        item["from"] = f"{year}-{first:02d}-01T00:00:00{offset}"
        item["to"] = f"{year}-{last:02d}-{calendar.monthrange(year, last)[1]:02d}T23:59:59{offset}"
        result.append(item)
    return result


def merge_native_parts(entries):
    if len(entries) != 4:
        raise ValueError("Require all four native quarters; do not fill a failed part")
    first = entries[0]
    for item in entries:
        if item.get("ts_id") != first.get("ts_id") or item.get("columns") != first.get("columns"):
            raise ValueError("Native quarter identities or schemas differ")
    combined = dict(first)
    combined["data"] = [row for item in entries for row in item["data"]]
    combined["rows"] = str(len(combined["data"]))
    return combined


def acquire_months(job, parameters, quarter_path):
    """Recover a gateway-failed quarter from its three exact source intervals."""
    first, last = int(parameters["from"][5:7]), int(parameters["to"][5:7])
    if last - first != 2:
        raise ValueError("Monthly retry requires one complete calendar quarter")
    entries, parts = [], []
    offset = parameters["from"][19:]
    for month in range(first, last + 1):
        params = dict(parameters)
        params["from"] = f"{job['year']}-{month:02d}-01T00:00:00{offset}"
        params["to"] = f"{job['year']}-{month:02d}-{calendar.monthrange(job['year'], month)[1]:02d}T23:59:59{offset}"
        part = DIRECTORY / f"{job['station_id']}_{job['year']}_M{month:02d}.json.gz"
        request_file = part.with_suffix(".request.json")
        if not part.exists():
            response = requests.get(R.ENDPOINT, params=params, timeout=120)
            if response.status_code != 200:
                return {**job, "status": "pending_month_access", "month": month,
                        "http_status": response.status_code}
            if len(response.content) > 128 << 20:
                raise RuntimeError("Native month exceeds bounded acquisition size")
            payload = response.json()
            if not isinstance(payload, list) or len(payload) != 1 or "data" not in payload[0] or str(payload[0].get("ts_id")) != str(job["native_ts_id"]):
                return {**job, "status": "pending_month_schema", "month": month}
            temporary = part.with_suffix(".partial")
            with temporary.open("wb") as file:
                with gzip.GzipFile(fileobj=file, mode="wb", filename="", mtime=0) as compressed:
                    compressed.write(response.content)
            temporary.replace(part)
            C.write_json(request_file, {"parameters": params, "raw_response_bytes": len(response.content)})
        saved = json.loads(request_file.read_text())
        if saved["parameters"] != params:
            raise RuntimeError("Native month cached request changed")
        with gzip.open(part, "rt") as file:
            entry = json.load(file)[0]
        if entry["data"]:
            names = [s.strip() for s in entry["columns"].split(",")]
            times = pd.to_datetime([row[names.index("Timestamp")] for row in entry["data"]], utc=True, format="mixed")
            if times.min() < pd.Timestamp(params["from"]).tz_convert("UTC") or times.max() > pd.Timestamp(params["to"]).tz_convert("UTC"):
                raise ValueError("Native month response does not respect its interval")
        if entries and (entry.get("ts_id") != entries[0].get("ts_id") or entry.get("columns") != entries[0].get("columns")):
            raise ValueError("Native month identities or schemas differ")
        entries.append(entry)
        parts.append({"path": str(part.relative_to(C.ROOT)), **saved})
    combined = dict(entries[0])
    combined["data"] = [row for entry in entries for row in entry["data"]]
    combined["rows"] = str(len(combined["data"]))
    serialized = json.dumps([combined], separators=(",", ":"), allow_nan=False).encode()
    temporary = quarter_path.with_suffix(".partial")
    with temporary.open("wb") as file:
        with gzip.GzipFile(fileobj=file, mode="wb", filename="", mtime=0) as compressed:
            compressed.write(serialized)
    temporary.replace(quarter_path)
    C.write_json(quarter_path.with_suffix(".request.json"), {
        "parameters": parameters,
        "source_mode": "lossless_value_merge_of_three_provider_months", "source_parts": parts,
        "no_native_point_interpolated_or_synthesized": True})
    return None


def acquire_quarters(job, parameters):
    path = DIRECTORY / f"{job['station_id']}_{job['year']}.json.gz"
    marker = DIRECTORY / f"{job['station_id']}_{job['year']}_quarter_plan.json"
    C.write_json(marker, {"reason": "annual native request returned a gateway/transport failure",
                         "logical_annual_parameters": parameters, "statistical_qualification_unchanged": True})
    entries, parts = [], []
    for index, params in enumerate(quarterly_parameters(parameters, job["year"]), 1):
        part = DIRECTORY / f"{job['station_id']}_{job['year']}_Q{index}.json.gz"
        request_file = part.with_suffix(".request.json")
        if not part.exists():
            response = requests.get(R.ENDPOINT, params=params, timeout=120)
            if response.status_code in {500, 502, 503, 504}:
                pending = acquire_months(job, params, part)
                if pending is not None:
                    return pending
                # The composite remains distinguishable from the original
                # monthly responses in the recursively retained source ledger.
                response = None
            if response is None:
                pass
            elif response.status_code != 200:
                return {**job, "status": "pending_quarter_access", "http_status": response.status_code, "quarter": index}
            elif len(response.content) > 128 << 20:
                raise RuntimeError("Native quarter exceeds bounded acquisition size")
            if response is not None:
                payload = response.json()
                if not isinstance(payload, list) or len(payload) != 1 or "data" not in payload[0] or str(payload[0].get("ts_id")) != str(job["native_ts_id"]):
                    return {**job, "status": "pending_quarter_schema", "quarter": index}
                temporary = part.with_suffix(".partial")
                with temporary.open("wb") as file:
                    with gzip.GzipFile(fileobj=file, mode="wb", filename="", mtime=0) as compressed:
                        compressed.write(response.content)
                temporary.replace(part)
                C.write_json(request_file, {"parameters": params, "raw_response_bytes": len(response.content)})
        saved = json.loads(request_file.read_text())
        if saved["parameters"] != params:
            raise RuntimeError("Native quarter cached request changed")
        with gzip.open(part, "rt") as file:
            entry = json.load(file)[0]
        if entry["data"]:
            names = [s.strip() for s in entry["columns"].split(",")]
            column = names.index("Timestamp")
            times = pd.to_datetime([row[column] for row in entry["data"]], utc=True, format="mixed")
            if times.min() < pd.Timestamp(params["from"]).tz_convert("UTC") or times.max() > pd.Timestamp(params["to"]).tz_convert("UTC"):
                raise ValueError("Native quarter response does not respect its exact interval")
        entries.append(entry)
        parts.append({"path": str(part.relative_to(C.ROOT)), **saved})
    combined = merge_native_parts(entries)
    serialized = json.dumps([combined], separators=(",", ":"), allow_nan=False).encode()
    temporary = path.with_suffix(".partial")
    with temporary.open("wb") as file:
        with gzip.GzipFile(fileobj=file, mode="wb", filename="", mtime=0) as compressed:
            compressed.write(serialized)
    temporary.replace(path)
    C.write_json(path.with_suffix(".request.json"), {
        "parameters": parameters,
        "source_mode": "lossless_value_merge_of_four_provider_quarters",
        "source_parts": parts, "no_native_point_interpolated_or_synthesized": True,
        "prediction_errors_opened": False})
    return acquire(job)


def native_support(entry, offset, year, *, minimum_hours=20, minimum_span=20):
    columns = entry.get("columns")
    if isinstance(columns, str):
        columns = [s.strip() for s in columns.split(",")]
    if not isinstance(columns, list) or not {"Timestamp", "Value", "Quality Code"}.issubset(columns):
        raise ValueError("Unverified native water-temperature observation schema")
    data = pd.DataFrame(entry["data"], columns=columns)
    dates = pd.date_range(f"{year}-01-01", f"{year}-12-31")
    if data.empty:
        return pd.DataFrame({"date": dates, "occupied_hours": 0, "span_hours": 0., "native_support": False})
    utc = pd.to_datetime(data.Timestamp, utc=True, format="mixed", errors="raise")
    local = (utc + pd.to_timedelta(offset, unit="h")).dt.tz_localize(None)
    value = pd.to_numeric(data.Value, errors="coerce")
    settings = json.loads(CONFIG.read_text())
    valid = pd.to_numeric(data["Quality Code"], errors="coerce").eq(10) & np.isfinite(value)
    valid &= ~value.isin(settings["daily_reference"]["sentinel_values"])
    frame = pd.DataFrame({"time": local, "value": value.where(valid)})
    conflicts = frame.groupby("time").value.nunique(dropna=True)
    frame.loc[frame.time.isin(conflicts.index[conflicts > 1]), "value"] = np.nan
    observed = frame.groupby("time").value.first().dropna().rename("value").to_frame()
    observed = observed.loc[observed.index.year == year]
    if observed.empty:
        return pd.DataFrame({"date": dates, "occupied_hours": 0, "span_hours": 0., "native_support": False})
    observed["hour"] = observed.index.hour
    grouped = observed.groupby(observed.index.floor("D"))
    hours = grouped.hour.nunique().reindex(dates, fill_value=0)
    spans = grouped.apply(lambda block: (block.index.max() - block.index.min()).total_seconds() / 3600).reindex(dates, fill_value=0)
    return pd.DataFrame({"date": dates, "occupied_hours": hours.to_numpy(), "span_hours": spans.to_numpy(),
                         "native_support": ((hours >= minimum_hours) & (spans >= minimum_span)).to_numpy()})


def plan():
    plan_path = OUT / "native_support_plan.json"
    if plan_path.exists():
        return json.loads(plan_path.read_text())["jobs"]
    cases = pd.read_csv(OUT / "reference_station_year_qualification.csv", dtype={"station_id": str})
    quality = pd.read_csv(OUT / "daily_reference_quality.csv", dtype={"station_id": str})
    meta = pd.read_csv(OUT / "metadata_candidates_and_roles.csv", dtype={"station_id": str, "station_no": str, "ts_id": str}).set_index("station_id")
    native = R.table(RAW / "bom_native_temperature_metadata.json") if hasattr(R, "table") else None
    if native is None:
        payload = json.loads((RAW / "bom_native_temperature_metadata.json").read_text())
        native = pd.DataFrame(payload[1:], columns=payload[0])
    if native.station_id.duplicated().any():
        raise ValueError("Native temperature series are ambiguous")
    native = native.set_index("station_id")
    eligible = cases.loc[cases.reference_eligible.eq(True)]
    latest = eligible.groupby("station_id").year.max().to_dict()
    jobs = []
    for row in quality.itertuples(index=False):
        identifier = row.station_id
        if identifier not in latest:
            continue
        years = [int(s) for s in str(row.complete_calendar_years).split(";") if s.isdigit() and int(s) <= latest[identifier]]
        if identifier not in native.index:
            raise ValueError("A mean-reference station has no native observation-series metadata")
        for year in years:
            jobs.append({"station_id": identifier, "station_no": meta.loc[identifier, "station_no"],
                         "native_ts_id": native.loc[identifier, "ts_id"], "year": year,
                         "offset": float(meta.loc[identifier, "local_standard_offset_hours"]),
                         "role": meta.loc[identifier, "role"],
                         "independence_group": meta.loc[identifier, "independence_group"]})
    jobs.sort(key=lambda row: (row["station_id"], row["year"]))
    C.write_json(plan_path, {
        "jobs": jobs, "minimum_distinct_local_hours": 20, "minimum_observation_span_hours": 20,
        "scope": "additional observed-sampling release gate; provider-mean QC results retained separately",
        "timing": "after daily-reference acquisition and a two-day timestamp-only schema probe; before full native-value audit and all new prediction errors",
        "reason": "A daily product name and quality flag alone do not establish a densely observed temperature reference for irregular point records.",
        "roles_predictors_and_joint_success_rule_unchanged": True,
        "no_H30_or_new_prediction_error_computed": True})
    return jobs


def acquire(job):
    DIRECTORY.mkdir(exist_ok=True, parents=True)
    path = DIRECTORY / f"{job['station_id']}_{job['year']}.json.gz"
    record_path = path.with_suffix(".request.json")
    hours = job["offset"]
    minute_offset = int(round(hours * 60))
    sign = "+" if minute_offset >= 0 else "-"
    offset = f"{sign}{abs(minute_offset)//60:02d}:{abs(minute_offset)%60:02d}"
    params = {"service": "kisters", "type": "queryServices", "request": "getTimeseriesValues",
              "format": "dajson", "datasource": "0", "ts_id": str(job["native_ts_id"]),
              "from": f"{job['year']}-01-01T00:00:00{offset}", "to": f"{job['year']}-12-31T23:59:59{offset}",
              "timezone": "individual", "dateformat": "yyyy-MM-dd'T'HH:mm:ssXXX",
              "returnfields": "Timestamp,Value,Quality Code"}
    if not path.exists():
        if (DIRECTORY / f"{job['station_id']}_{job['year']}_quarter_plan.json").exists():
            return acquire_quarters(job, params)
        response = None
        for attempt in range(2):
            try:
                response = requests.get(R.ENDPOINT, params=params, timeout=120, stream=True)
            except requests.RequestException:
                response = None
                if attempt:
                    break
                time.sleep(1)
                continue
            if response.status_code == 200:
                break
            response.close()
            if response.status_code not in {500, 502, 503, 504}:
                break
            if not attempt:
                time.sleep(1)
        if response is None or response.status_code in {500, 502, 503, 504}:
            return acquire_quarters(job, params)
        if response.status_code != 200:
            return {**job, "status": "pending_access", "http_status": response.status_code}
        temporary = path.with_suffix(".partial")
        length = 0
        with temporary.open("wb") as file:
            with gzip.GzipFile(fileobj=file, mode="wb", filename="", mtime=0) as compressed:
                for block in response.iter_content(1 << 20):
                    length += len(block)
                    if length > 128 << 20:
                        raise RuntimeError("Native station-year exceeds 128 MiB; split acquisition required")
                    compressed.write(block)
        with gzip.open(temporary, "rt") as file:
            payload = json.load(file)
        if not isinstance(payload, list) or len(payload) != 1 or "data" not in payload[0] or str(payload[0].get("ts_id")) != str(job["native_ts_id"]):
            temporary.unlink()
            return {**job, "status": "pending_response_schema"}
        temporary.replace(path)
        C.write_json(record_path, {"parameters": params, "raw_response_bytes": length,
                                   "compression": "lossless gzip with fixed mtime", "prediction_errors_opened": False})
    saved = json.loads(record_path.read_text())
    if saved["parameters"] != params:
        raise RuntimeError("Native source request changed")
    with gzip.open(path, "rt") as file:
        entry = json.load(file)[0]
    support = native_support(entry, job["offset"], job["year"])
    support.to_csv(DIRECTORY / f"{job['station_id']}_{job['year']}_support.csv", index=False)
    return {**job, "status": "evaluated", "native_rows": len(entry["data"]),
            "supported_days": int(support.native_support.sum()), "calendar_days": len(support),
            "complete_native_support": bool(support.native_support.all()),
            "path": str(path.relative_to(C.ROOT)),
            "source_mode": saved.get("source_mode", "annual_provider_response"),
            "source_parts": saved.get("source_parts")}


def finalize(results):
    records = pd.DataFrame(results)
    records.to_csv(OUT / "native_station_year_support.csv", index=False)
    cases = pd.read_csv(OUT / "reference_station_year_qualification.csv", dtype={"station_id": str})
    successful = {(row["station_id"], int(row["year"])): row for row in results if row["status"] == "evaluated"}
    pending = {(row["station_id"], int(row["year"])) for row in results if row["status"] != "evaluated"}
    max_history = json.loads(CONFIG.read_text())["predictive_choice_before_new_recovery_results"]["maximum_local_complete_history_years"]
    rows = []
    for row in cases.to_dict("records"):
        base = row["reference_eligible"]
        good, reason, years = None, "pending_mean_reference_QC", []
        if pd.notna(base) and not bool(base):
            good, reason = False, row["qualification_status"]
        elif pd.notna(base):
            key = (row["station_id"], int(row["year"]))
            result = successful.get(key)
            if result is None:
                good, reason = None, "pending_native_target_support"
            elif not result["complete_native_support"]:
                good, reason = False, "native_observations_do_not_support_every_target_day"
            else:
                years = sorted({year for (station, year), value in successful.items()
                                if station == row["station_id"] and year < row["year"] and value["complete_native_support"]})
                unknown = any(station == row["station_id"] and year < row["year"] for station, year in pending)
                if len(years) >= 3:
                    good, reason = True, "mean_QC_and_native_sampling_reference_qualified"
                elif unknown:
                    good, reason = None, "pending_native_prior_year_support"
                else:
                    good, reason = False, "fewer_than_three_natively_supported_prior_years"
        rows.append({**row, "observed_sampling_reference_eligible": good,
                     "observed_sampling_status": reason,
                     "permitted_strictly_prior_history": ";".join(map(str, years[-max_history:])),
                     "primary_test_error_access_allowed": False})
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "observed_reference_release.csv", index=False)
    qualified = frame.observed_sampling_reference_eligible.eq(True)
    groups = frame.loc[qualified].groupby("role").independence_group.nunique().to_dict()
    floor = F.ideal_group_floor(.05, .005)
    C.write_json(OUT / "observed_reference_summary.json", {
        "qualified_observed_sampling_station_years": int(qualified.sum()),
        "qualified_station_years_by_role": frame.loc[qualified].role.value_counts().to_dict(),
        "qualified_catchment_components_by_role": groups,
        "pending_observed_sampling_station_years": int(frame.observed_sampling_reference_eligible.isna().sum()),
        "native_jobs": len(results), "native_access_or_schema_pending": len(pending),
        "new_H30_prediction_errors_opened": False,
        "primary_test_error_access_allowed": False,
        "recruitment_and_full_joint_power_review_still_required": True,
        "ideal_one_threshold_group_floor_not_a_sample_size_recommendation": floor,
        "standalone_calibration_test_group_floor_met": groups.get("calibration", 0) >= floor and groups.get("test", 0) >= floor,
        "natural_gap_backup_confirmation_completed": False})
    C.write_json(OUT / "native_support_acquisition.json", {"results": results,
                 "no_new_prediction_or_H30_error_computed": True})
    print(f"[403] {int(qualified.sum())} reference station-years pass native sampling; new test errors remain sealed", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, choices=[1, 2], default=2)
    parser.add_argument("--retry-pending", action="store_true",
                        help="Retry only failed intervals; keep every evaluated station-year")
    args = parser.parse_args()
    jobs = plan()
    if not jobs:
        raise RuntimeError("No mean-QC candidate references for the native support audit")
    if args.retry_pending:
        previous = json.loads((OUT / "native_support_acquisition.json").read_text())
        by_key = {(row["station_id"], int(row["year"])): row for row in previous["results"]}
        if set(by_key) != {(row["station_id"], int(row["year"])) for row in jobs}:
            raise RuntimeError("Retry acquisition does not match the frozen native plan")
        results, retry = [], []
        for job in jobs:
            row = by_key[(job["station_id"], int(job["year"]))]
            if row["status"] == "evaluated":
                results.append(row)
            else:
                retry.append(job)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(acquire, job): job for job in retry}
            for future in as_completed(futures):
                job = futures[future]
                try:
                    row = future.result()
                except (requests.RequestException, ValueError, RuntimeError) as error:
                    row = {**job, "status": "pending_acquisition_or_schema", "error": str(error)}
                results.append(row)
                print(f"[403] retry {job['station_id']} {job['year']} {row['status']}", flush=True)
        results.sort(key=lambda row: (row["station_id"], row["year"]))
        finalize(results)
        return int(any(row["status"] != "evaluated" for row in results))
    # Check one genuine native response before submitting a larger request batch.
    first = acquire(jobs[0])
    if first["status"] != "evaluated":
        C.write_json(OUT / "native_preflight_pending.json", first)
        raise RuntimeError("Native sampling schema/access unresolved; batch not launched")
    results = [first]
    print(f"[403] preflight evaluated; {len(jobs)} native station-years planned", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(acquire, job): job for job in jobs[1:]}
        for future in as_completed(futures):
            job = futures[future]
            try:
                result = future.result()
            except (requests.RequestException, ValueError, RuntimeError) as error:
                result = {**job, "status": "pending_acquisition_or_schema", "error": str(error)}
            results.append(result)
            print(f"[403] {len(results)}/{len(jobs)} {job['station_id']} {job['year']} {result['status']}", flush=True)
    results.sort(key=lambda row: (row["station_id"], row["year"]))
    finalize(results)
    return int(any(row["status"] != "evaluated" for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
