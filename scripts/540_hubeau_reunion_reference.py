#!/usr/bin/env python3
"""Qualify a fixed new-island Hub'Eau cohort before prediction scoring.

Only provider qualification code 1, complete reported calendar days with all
24 distinct hours, and complete July--June reference years are accepted.
Reported day boundaries are retained because a site-specific time-zone
statement has not been established. This is unregistered exploratory work.
"""
from __future__ import annotations
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import time
import numpy as np
import pandas as pd
import requests
from joblib import Parallel, delayed
from pyproj import Geod
from stream_recoverability.data.v2_download_policy import last_check_site_ids

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_review_response_20261027/external_hubeau_reunion"
CATALOG = ROOT / "results/wrr_submission_ready/multi_agency_ingest/hubeau/raw_cache/catalog/station_catalog.json.gz"
ENDPOINT = "https://hubeau.eaufrance.fr/api/v1/temperature/chronique"


def index_cached_splits(site, start, end):
    """Record already downloaded split windows without re-requesting a year."""
    path = OUT / "raw" / f"{site}_{start}_{end}.json.gz"
    if path.exists():
        return True
    a, b = pd.Timestamp(start), pd.Timestamp(end)
    if a >= b:
        return False
    mid = a + (b - a) // 2
    windows = [(a.strftime("%Y-%m-%d"), mid.strftime("%Y-%m-%d")),
               ((mid + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d"))]
    if all(index_cached_splits(site, x, y) for x, y in windows):
        path.write_bytes(gzip.compress(json.dumps({"split":windows}).encode()))
        return True
    return False


def metadata_roster():
    document = json.loads(gzip.decompress(CATALOG.read_bytes()))
    stations = pd.DataFrame(document["document"]["data"])
    previous = set(last_check_site_ids())
    for folder in [ROOT / "results/wrr_submission_ready/multi_agency_ingest/hubeau/raw_cache/qualification_station",
                   ROOT / "results/wrr_submission_ready/multi_agency_ingest/hubeau/raw_cache/chronique"]:
        for item in folder.rglob("*"):
            match = re.search(r"(\d{8})", item.name)
            if match:
                previous.add(match.group(1))
    source = pd.read_parquet(ROOT / "results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet",
                             columns=["provider", "station_key"])
    previous.update(source.loc[source.provider.eq("hubeau"), "station_key"].str.removeprefix("hubeau|"))
    f = stations.loc[stations.code_departement.eq("974") & ~stations.code_station.isin(previous)].copy()
    f = f.loc[pd.to_datetime(f.date_mise_en_service, errors="coerce").dt.year.le(2012)]
    f = f.loc[f.date_mise_hors_service.isna() | pd.to_datetime(f.date_mise_hors_service, errors="coerce").dt.year.ge(2024)]
    f = f.loc[~f.libelle_station.fillna("").str.contains("LAC|ETANG|CANAL|BARRAGE|RESERVOIR", case=False)]
    f = f.dropna(subset=["latitude", "longitude", "code_masse_eau"])
    f = f.sort_values(["date_mise_en_service", "code_station"])
    geod = Geod(ellps="WGS84")
    selected = []
    for row in f.to_dict("records"):
        if any(row["code_masse_eau"] == old["code_masse_eau"] for old in selected):
            continue
        if any(geod.inv(row["longitude"], row["latitude"], old["longitude"], old["latitude"])[2] < 10000 for old in selected):
            continue
        selected.append(row)
        if len(selected) == 5:
            break
    fields = ["code_station", "libelle_station", "latitude", "longitude", "code_masse_eau", "code_bassin", "date_mise_en_service", "date_mise_hors_service"]
    return pd.DataFrame(selected)[fields]


def fetch_window(site, start, end, session, log):
    path = OUT / "raw" / f"{site}_{start}_{end}.json.gz"
    if path.exists():
        cached = json.loads(gzip.decompress(path.read_bytes()))
        if "split" in cached:
            return sum((fetch_window(site, a, b, session, log) for a, b in cached["split"]), [])
        return cached["data"]
    params = {"code_station":site, "code_qualification":"1", "date_debut_mesure":start,
              "date_fin_mesure":end, "size":20000, "page":1, "sort":"asc",
              "fields":"code_station,date_mesure_temp,heure_mesure_temp,resultat,symbole_unite,code_qualification"}
    response = session.get(ENDPOINT, params=params, timeout=120)
    log.append(dict(url=response.url, status=response.status_code,
                    requested_utc=datetime.now(timezone.utc).isoformat(), retry_after=response.headers.get("Retry-After")))
    if response.status_code == 429:
        raise RuntimeError("Provider rate limit; preserve the remaining requests for later")
    response.raise_for_status()
    doc = response.json()
    time.sleep(.4)
    if doc.get("next") or int(doc.get("count") or 0) > 20000:
        a, b = pd.Timestamp(start), pd.Timestamp(end)
        if a >= b:
            raise RuntimeError("One-day response exceeds the provider page limit")
        mid = a + (b - a) // 2
        windows = [(a.strftime("%Y-%m-%d"), mid.strftime("%Y-%m-%d")),
                   ((mid + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d"))]
        rows = sum((fetch_window(site, x, y, session, log) for x, y in windows), [])
        path.write_bytes(gzip.compress(json.dumps({"split":windows}).encode()))
        return rows
    path.write_bytes(gzip.compress(json.dumps(doc, ensure_ascii=False).encode()))
    return doc.get("data") or []


def quality_daily(records):
    """Aggregate only correct-quality, nonconflicting, fully observed hours."""
    frame = pd.DataFrame(records)
    if frame.empty:
        return pd.DataFrame(columns=["temperature_c", "n_hours"]), 0, 0
    frame["value"] = pd.to_numeric(frame.resultat, errors="coerce")
    frame["time"] = pd.to_datetime(frame.date_mesure_temp.astype(str) + " " + frame.heure_mesure_temp.astype(str), errors="coerce")
    frame = frame.loc[frame.code_qualification.astype(str).eq("1") & frame.symbole_unite.eq("°C")
                      & frame.time.notna() & frame.value.between(-2, 40)].copy()
    if frame.empty:
        return pd.DataFrame(columns=["temperature_c", "n_hours"]), 0, 0
    conflicts = frame.groupby("time").value.nunique().gt(1)
    bad = conflicts[conflicts].index
    frame = frame.loc[~frame.time.isin(bad)].drop_duplicates("time")
    frame["date"] = frame.time.dt.normalize()
    frame["hour"] = frame.time.dt.hour
    hourly = frame.groupby(["date", "hour"]).value.mean().reset_index()
    daily = hourly.groupby("date").agg(temperature_c=("value", "mean"), n_hours=("hour", "nunique"))
    daily["temperature_c"] = daily.temperature_c.where(daily.n_hours.eq(24))
    return daily, len(hourly), len(bad)


def one(row):
    site = str(row["code_station"])
    session = requests.Session()
    session.headers["User-Agent"] = "river-temperature reference qualification"
    log_path = OUT / "requests" / (site + ".json")
    logs = json.loads(log_path.read_text()) if log_path.exists() else []
    raw = []
    try:
        for year in range(2010, 2026):
            raw.extend(fetch_window(site, f"{year}-01-01", f"{year}-12-31", session, logs))
        log_path.write_text(json.dumps(logs, indent=2) + "\n")
        if not raw:
            return dict(site=site, status="acquired_no_qualified_observations", n_complete_hot_years=0, eligible=False)
        if any(str(item.get("code_station")) != site for item in raw):
            raise ValueError("Provider response contains a different station identity")
        daily, n_hours, n_conflicts = quality_daily(raw)
        if daily.empty:
            return dict(site=site, status="acquired_no_usable_observations", n_complete_hot_years=0, eligible=False)
        daily.reset_index().to_parquet(OUT / "daily" / (site + ".parquet"), index=False)
        series = daily.temperature_c
        complete = []
        for year in range(2010, 2025):
            dates = pd.date_range(f"{year}-07-01", f"{year+1}-06-30")
            if series.reindex(dates).notna().all():
                complete.append(year)
        return dict(site=site, status="acquired", n_raw_observations=len(raw),
                    n_correct_unique_hours=n_hours, n_complete_hot_years=len(complete),
                    complete_hot_years=";".join(map(str, complete)), eligible=len(complete)>=4,
                    n_conflicting_timestamps=n_conflicts)
    except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
        log_path.write_text(json.dumps(logs, indent=2) + "\n")
        return dict(site=site, status="unavailable", eligible=False,
                    reason=f"{type(exc).__name__}: {exc}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for folder in ["raw", "daily", "requests"]:
        (OUT / folder).mkdir(exist_ok=True)
    roster = metadata_roster()
    path = OUT / "cohort.csv"
    if path.exists():
        old = pd.read_csv(path, dtype={"code_station":str})
        if old.code_station.tolist() != roster.code_station.tolist():
            raise RuntimeError("Metadata-only roster has changed")
    else:
        roster.to_csv(path, index=False)
    plan = {"n_metadata_candidates":len(roster), "selection":"five longest metadata service histories on Reunion, distinct waterbody codes and at least 10 km apart, excluding known old and reserved station IDs; no temperature errors used",
            "pilot_before_roster":"one metadata-only qualification-count request for station 10615120; no temperature value requested",
            "quality":"Sandre qualification 1 and finite Celsius values; conflicting timestamps excluded",
            "daily":"mean of 24 distinct observed hourly bins on the provider-reported calendar day; no interpolation; time-zone convention not yet verified",
            "reference":"at least four complete July-June years, 2010-2025; one-hour values are point observations, not a time-weighted instrument truth",
            "independence":"distinct waterbody codes and 10 km separation do not establish independent climate or catchment errors",
            "status":"unregistered exploratory qualification; no target prediction errors used in selection"}
    (OUT / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    for site in roster.code_station:
        for year in range(2010, 2026):
            index_cached_splits(site, f"{year}-01-01", f"{year}-12-31")
    results = Parallel(n_jobs=2, prefer="threads", verbose=10)(delayed(one)(row) for row in roster.to_dict("records"))
    qualification = roster.merge(pd.DataFrame(results), left_on="code_station", right_on="site", how="left", validate="one_to_one")
    qualification.to_csv(OUT / "qualification.csv", index=False)
    status = dict(n_candidates=len(roster), n_acquired=int(qualification.status.str.startswith("acquired").sum()),
                  n_unavailable=int(qualification.status.eq("unavailable").sum()), n_eligible=int(qualification.eligible.sum()),
                  reconstruction_accuracy_evaluated=False,
                  limitation="Provider time-zone interpretation and hydrological dependence require verification; 24-hour point averages are not perfect time-weighted ground truth.")
    (OUT / "status.json").write_text(json.dumps(status, indent=2) + "\n")
    print(qualification.to_string(index=False), flush=True)
    print(json.dumps(status, indent=2), flush=True)


if __name__ == "__main__":
    main()
