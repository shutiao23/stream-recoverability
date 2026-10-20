#!/usr/bin/env python3
"""Acquire continuous external observations under the metadata-locked roles."""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import wrr_r3_common as C

from stream_recoverability.data.v2_download_policy import last_check_site_ids

OUT = C.RUN / "r3_02_external_resource"
RAW = C.ROOT / "data/external/wrr_revision_20261020c/provider_responses"
DAILY = C.ROOT / "data/external/wrr_revision_20261020c/daily"
ROLES = OUT / "external_station_roles.csv"
FOEN_QUERY = """query DailyWaterTemperature($station: String!, $from: AWSDateTime!, $to: AWSDateTime!) {
  water { observations { data_1day_mean(where: {
    station: {no: {_eq: $station}}, parameterName: {_eq: "WT"},
    timestamp: {_gte: $from, _lt: $to}
  }, limit: 10000) {timestamp parameterName value unitSymbol releaseState station {no}}}}
}"""


def document(url: str, destination: Path, *, body: dict | None = None) -> dict:
    if destination.exists():
        return json.loads(destination.read_text())
    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            response = requests.post(url, json=body, timeout=(15, 90)) if body else requests.get(url, timeout=(15, 90))
            response.raise_for_status()
            payload = response.json()
            temporary = destination.with_suffix(".partial")
            temporary.write_bytes(response.content)
            temporary.replace(destination)
            return payload
        except (requests.RequestException, ValueError):
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    raise RuntimeError("Unreachable retry state")


def foen_series(row: dict) -> tuple[pd.DataFrame, dict]:
    body = {"query": FOEN_QUERY, "variables": {"station": str(row["original_id"]), "from": "2008-01-01T00:00:00Z", "to": "2023-01-01T00:00:00Z"}}
    payload = document("https://data.bafu.admin.ch/api", RAW / "foen" / f"{row['station_ID']}_2008_2022.json", body=body)
    if payload.get("errors"):
        raise RuntimeError("FOEN returned GraphQL errors; no response values are treated as observations")
    records = payload.get("data", {}).get("water", {}).get("observations", {}).get("data_1day_mean", [])
    if len(records) >= 10000:
        raise RuntimeError("FOEN reached its record limit; request must be split before use")
    accepted = []
    for item in records:
        if str(item.get("releaseState")) not in {"2", "3"}:
            continue
        if str(item.get("station", {}).get("no")) != str(row["original_id"]) or item.get("parameterName") != "WT":
            continue
        if item.get("unitSymbol") not in {"°C", "C", "degC"}:
            raise RuntimeError("Unexpected FOEN temperature unit")
        accepted.append({"date": item.get("timestamp"), "temperature_c": item.get("value"), "release_state": int(item["releaseState"])})
    frame = pd.DataFrame(accepted, columns=["date", "temperature_c", "release_state"])
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame.date, utc=True).dt.tz_localize(None).dt.normalize()
        frame["temperature_c"] = pd.to_numeric(frame.temperature_c, errors="coerce")
        frame = frame.sort_values(["date", "release_state"]).drop_duplicates("date", keep="last")
    return frame[["date", "temperature_c"]], {"measurement_contract": "provider_daily_mean", "quality": "provider_released_states_2_or_3", "day_definition": "UTC date of daily-mean record timestamp, consistent with the existing FOEN adapter"}


def hubeau_window(station: str, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    query = {"code_station": station, "date_debut_mesure": start.strftime("%Y-%m-%d"), "date_fin_mesure": end.strftime("%Y-%m-%d"), "size": 20000, "page": 1, "sort": "asc"}
    url = requests.Request("GET", "https://hubeau.eaufrance.fr/api/v1/temperature/chronique", params=query).prepare().url
    filename = f"{station}_{start:%Y%m%d}_{end:%Y%m%d}.json"
    payload = document(url, RAW / "hubeau" / filename)
    data = payload.get("data") or []
    if payload.get("next") or int(payload.get("count") or 0) >= 20000:
        if start == end:
            raise RuntimeError("Hub'Eau daily request exceeds paging limit")
        middle = start + (end - start) // 2
        return hubeau_window(station, start, middle) + hubeau_window(station, middle + pd.Timedelta(days=1), end)
    return data


def hubeau_series(row: dict) -> tuple[pd.DataFrame, dict]:
    station = str(row["original_id"]).zfill(8)
    if station in last_check_site_ids():
        raise RuntimeError("Station is reserved by an existing last-check protocol")
    parts = []
    for year in range(2008, 2023):
        records = hubeau_window(station, pd.Timestamp(year, 1, 1), pd.Timestamp(year, 12, 31))
        frame = pd.DataFrame(records)
        if frame.empty:
            continue
        required = {"date_mesure_temp", "resultat", "code_qualification"}
        if not required.issubset(frame):
            raise RuntimeError("Hub'Eau response lacks required measurement metadata")
        frame = frame.loc[frame.code_qualification.astype(str).isin(["1", "4"])]
        if "heure_mesure_temp" not in frame:
            raise RuntimeError("Hub'Eau response lacks its separate measurement-time field")
        measurement_time = frame.date_mesure_temp.astype(str).str[:10] + "T" + frame.heure_mesure_temp.astype(str)
        timestamps = pd.to_datetime(measurement_time, errors="coerce").dt.tz_localize("Europe/Paris", ambiguous="NaT", nonexistent="NaT")
        frame = pd.DataFrame({"timestamp": timestamps, "temperature_c": pd.to_numeric(frame.resultat, errors="coerce"), "qualification": frame.code_qualification.astype(str)})
        frame = frame.dropna(subset=["timestamp", "temperature_c"]).drop_duplicates("timestamp")
        frame["date"] = frame.timestamp.dt.tz_localize(None).dt.normalize()
        frame["hour"] = frame.timestamp.dt.hour
        daily = frame.groupby("date").agg(temperature_c=("temperature_c", "mean"), n_observations=("temperature_c", "size"), first_hour=("hour", "min"), last_hour=("hour", "max"))
        daily = daily.loc[(daily.n_observations >= 4) & ((daily.last_hour - daily.first_hour) >= 18)]
        parts.append(daily.reset_index()[["date", "temperature_c"]])
    frame = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["date", "temperature_c"])
    return frame, {"measurement_contract": "project_aggregated_subdaily", "quality": "Sandre_1_or_4_retained_unqualified_not_promoted", "day_definition": "Europe/Paris local day, at least four observations spanning at least 18 hours"}


def download(row: dict) -> dict:
    base = {"station_ID": row["station_ID"], "provider": row["provider"], "external_role": row["external_role"], "independence_group": row["independence_group"]}
    manifest_path = DAILY / row["external_role"] / f"{row['station_ID']}.json"
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text())
        if payload.get("status") == "downloaded" and C.digest(Path(payload["daily_path"])) == payload["sha256"]:
            return payload
    if row["provider"] not in {"foen", "hubeau"}:
        return {**base, "status": "continuous_source_unresolved", "reason": "official_ehyd_catalog_offers_monthly_temperature" if row["provider"] == "ehyd" else "continuous_nve_route_requires_source_resolution"}
    try:
        frame, provenance = foen_series(row) if row["provider"] == "foen" else hubeau_series(row)
        if frame.empty:
            return {**base, "status": "no_accepted_daily_values", **provenance}
        series = frame.set_index("date").temperature_c.sort_index().asfreq("D")
        physically_plausible = series.between(-5, 45) | series.isna()
        series = series.where(physically_plausible)
        complete = []
        for year, block in series.groupby(series.index.year):
            expected = 366 if pd.Timestamp(int(year), 12, 31).is_leap_year else 365
            if len(block) == expected and np.isfinite(block.to_numpy()).all():
                complete.append(int(year))
        destination = DAILY / row["external_role"] / f"{row['station_ID']}.parquet"
        destination.parent.mkdir(parents=True, exist_ok=True)
        series.rename("temperature_c").rename_axis("date").reset_index().to_parquet(destination, index=False)
        result = {**base, **provenance, "status": "downloaded", "n_calendar_days": len(series), "n_observed_days": int(series.notna().sum()), "complete_years": complete, "eligible_four_complete_years": len(complete) >= 4, "daily_path": str(destination), "sha256": C.digest(destination), "source_partition_sha256": C.digest(ROLES), "performance_outcomes_inspected": False}
        C.write_json(manifest_path, result)
        return result
    except (requests.RequestException, ValueError, RuntimeError, KeyError) as error:
        return {**base, "status": "acquisition_failed", "error_type": type(error).__name__, "reason": str(error)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--providers", default="foen,hubeau")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    C.protocol()
    roles = pd.read_csv(ROLES, dtype={"original_id": str})
    selected = roles.loc[roles.eligible_new_component.eq(True) & roles.provider.isin(args.providers.split(","))]
    contract_path = OUT / "daily_acquisition_contract.json"
    if not contract_path.exists():
        C.write_json(contract_path, {"station_partition_sha256": C.digest(ROLES), "start": "2008-01-01", "end_exclusive": "2023-01-01", "strict_complete_years_required": 4, "physical_qc_temperature_range_C": [-5, 45], "hubeau_minimum_daily_observations": 4, "hubeau_minimum_daily_span_hours": 18, "foen_query": FOEN_QUERY, "eligibility_checks_only_before_method_freeze": True})
    rows = []
    print(f"[353] acquiring {len(selected)} stations under immutable metadata roles", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download, row): row["station_ID"] for row in selected.to_dict("records")}
        for future in as_completed(futures):
            result = future.result()
            rows.append(result)
            print(f"[353] {result['station_ID']}: {result['status']}, complete years={len(result.get('complete_years', []))}", flush=True)
    output = OUT / f"daily_acquisition_{args.providers.replace(',', '_')}.json"
    C.write_json(output, {"stations": rows, "performance_outcomes_inspected": False})
    table = pd.DataFrame(rows)
    if len(table):
        table.to_csv(output.with_suffix(".csv"), index=False)
    C.write_json(output.with_name(output.stem + "_fingerprint.json"), C.fingerprint(Path(__file__), {"roles": ROLES, "acquisition_contract": contract_path}))
    print(table.groupby(["provider", "status"]).size().to_string() if len(table) else "No eligible stations", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
