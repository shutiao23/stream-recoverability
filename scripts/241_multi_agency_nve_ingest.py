#!/usr/bin/env python3
"""NVE HydAPI ingest for the pre-registered multi-agency transport panel.

Feeds ``results/wrr_submission_ready/MULTI_AGENCY_TRANSPORT_PROTOCOL.md``
(provider ``nve_hydapi``).  This script performs **ingest and QC only**: it
never scores the frozen certificate and never touches frozen-screen
performance.

Design decisions (all recorded in ``ingest.json``):

* Parameter ``1003`` (``Vanntemperatur`` / water temperature), resolution
  ``1440`` minutes.  HydAPI documents that the 1440 series is *the daily
  statistic for the calendar day in Norwegian normal time (UTC+1)*,
  timestamped ``11:00Z``; the per-series ``resolutionList`` entry carries the
  aggregation ``method`` (``Mean`` for genuine daily means, ``Instantaneous``
  for series whose "daily" archive is a snapshot).  Only ``Mean`` series are
  accepted by the transport eligibility rule ("provider *daily* statistic").
* ``observationPlace`` must start with ``Elv`` (river).  ``Innsjø`` (lake),
  ``Magasin`` (reservoir), ``Utslippspunkt``/``Kum``/``Inntak``/``Overløp``
  (plant/municipal infrastructure), ``Grunnvannsrør`` (groundwater),
  ``I rør`` (in pipe) and the air-temperature/soil place codes are dropped.
* ``measuredOrDerived`` must be ``Målt`` (measured, not derived).
* Quality: keep ``quality in {2, 3}`` (PrimaryControlled / SecondaryControlled)
  and ``correction == 0`` (no manual/ice correction, no interpolation, no
  model value, no "fetched from rejected period").  Dropped counts are
  reported per station.
* QC-passing values are snapped to the calendar day of the value in Norwegian
  normal time (fixed UTC+1, matching NVE's documented day definition) and
  averaged within a station-day; duplicates are counted.
* A *complete calendar year* is a year with >= 365 (366 in leap years)
  QC-passing days, the same definition used by the sealed USGS confirmation
  (`scripts/234_wrr_sealed_confirmation_score.py::_complete_years_from_series`).
* Networks are NVE drainage basins (``vassdrag``) from ``regineNo`` (REGINE),
  with the basin name taken from the station metadata ``hierarchy`` field.
  A network is kept when >= 2 stations have >= 4 complete calendar years.
* Any station id present in ``results/v17_fitness/step1_panel/station_roster.csv``
  is excluded before network selection (protocol rule 6).

Usage::

    PYTHONPATH=src python3 scripts/241_multi_agency_nve_ingest.py
    PYTHONPATH=src python3 scripts/241_multi_agency_nve_ingest.py --stage metadata
    PYTHONPATH=src python3 scripts/241_multi_agency_nve_ingest.py --stage observations
    PYTHONPATH=src python3 scripts/241_multi_agency_nve_ingest.py --stage assemble
    PYTHONPATH=src python3 scripts/241_multi_agency_nve_ingest.py --refresh   # ignore cache
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stream_recoverability.data.nve_water_temperature import (  # noqa: E402
    HYDAPI,
    discover_public_hydapi_key,
)

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "results" / "wrr_submission_ready" / "multi_agency_ingest" / "nve"
RAW = OUT_ROOT / "raw_cache"
NETWORKS = OUT_ROOT / "networks"
V17_ROSTER = ROOT / "results" / "v17_fitness" / "step1_panel" / "station_roster.csv"
PROTOCOL = ROOT / "results" / "wrr_submission_ready" / "MULTI_AGENCY_TRANSPORT_PROTOCOL.md"

PROVIDER = "nve_hydapi"
# Provider-level assurance stratum required by
# MULTI_AGENCY_TRANSPORT_PROTOCOL.md Amendment 2 ("every station carries
# quality_assurance in its stations.csv").  NVE HydAPI quality code 2/3 is
# PrimaryControlled/SecondaryControlled, i.e. checked at source, so admitted NVE
# series are `quality_checked`, never `provider_published_unqualified`.
QUALITY_ASSURANCE = "quality_checked"
PARAMETER = 1003
PARAMETER_NAME = "Vanntemperatur (water temperature)"
RESOLUTION_TIME = 1440
USER_AGENT = "stream-recoverability/1.1 multi-agency-transport-ingest (python-urllib)"
ACCEPT_OBSERVATION_PLACES = ("Elv",)
ACCEPT_MEASURED_OR_DERIVED = ("Målt",)
ACCEPT_AGGREGATION = ("Mean",)
ACCEPT_QUALITY = (2, 3)  # PrimaryControlled, SecondaryControlled
ACCEPT_CORRECTION = (0,)  # no manual/ice correction, interpolation or model value
PLAUSIBLE_TEMPERATURE_C = (-5.0, 40.0)
MIN_STATIONS_PER_NETWORK = 2
MIN_COMPLETE_YEARS = 4
NORWAY_STANDARD_OFFSET = timedelta(hours=1)  # Norwegian normal time, UTC+1
SVALBARD_BASIN_NUMBER = "400"  # Svalbard archipelago; kept out of the mainland panel
OBSERVATION_BATCH_TARGET = 20_000  # estimated records per Observations request
OBSERVATION_MAX_SERIES = 8  # HydAPI hard limit is 10 series per request; stay below
REQUEST_PAUSE_S = 0.25
MAX_ATTEMPTS = 6

# station ids already consumed by the v17/v18 programme: hard exclusion
V17_STATION_IDS: set[str] = set()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).replace(".", "_")


def http_json(url: str, *, api_key: str, timeout: int = 300) -> tuple[dict | None, dict]:
    """GET a HydAPI URL with retries; return (document, response headers).

    A 404 returns ``(None, {})``: HydAPI answers 404 when a station id is not
    in the current station registry (delisted stations keep their series).
    """

    last: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        request = urllib.request.Request(
            url,
            headers={
                "X-API-Key": api_key,
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                headers = {key.lower(): value for key, value in response.headers.items()}
                payload = json.loads(response.read())
            time.sleep(REQUEST_PAUSE_S)
            return payload, headers
        except urllib.error.HTTPError as error:  # 404/429/5xx
            last = error
            if error.code == 404:
                return None, {}
            if error.code == 400:
                # deterministic client error: retrying cannot help
                detail = error.read()[:300].decode("utf-8", "replace")
                raise RuntimeError(f"HTTP 400 for {url}: {detail}") from error
            sleep_for = min(2.0 ** attempt, 30.0)
            remaining = error.headers.get("x-rate-limit-remaining") if error.headers else None
            print(
                f"  HTTP {error.code} (remaining={remaining}); retry in {sleep_for:.0f}s",
                flush=True,
            )
            time.sleep(sleep_for)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last = error
            sleep_for = min(2.0 ** attempt, 30.0)
            print(f"  {type(error).__name__}: {error}; retry in {sleep_for:.0f}s", flush=True)
            time.sleep(sleep_for)
    raise RuntimeError(f"request failed after {MAX_ATTEMPTS} attempts: {url}") from last


def _cache_request_entry(path: Path, url: str | None = None) -> dict:
    """Provenance entry for a response served from the raw cache."""

    retrieved = None
    try:
        document = json.loads(path.read_text())
        url = url or document.get("_request_url") or document.get("currentLink")
        retrieved = document.get("_retrieved_utc") or document.get("createdAt")
    except (json.JSONDecodeError, OSError):
        pass
    return {
        "url": url,
        "cache_path": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "retrieved_utc": retrieved,
        "source": "cache",
    }


def complete_years_from_series(series: pd.Series) -> list[int]:
    """Calendar years with >= 365 (366) QC-passing values, sealed definition."""

    values = pd.to_numeric(series, errors="coerce")
    years: list[int] = []
    for year, block in values.groupby(values.index.year):
        year = int(year)
        leap = (year % 400 == 0) or (year % 4 == 0 and year % 100 != 0)
        need = 366 if leap else 365
        if int(np.isfinite(block.to_numpy(dtype=float)).sum()) >= need:
            years.append(year)
    return years


def basin_number(station_id: str) -> str:
    return str(station_id).split(".")[0].zfill(3)


# --------------------------------------------------------------------------- #
# stage 1: catalog + station metadata
# --------------------------------------------------------------------------- #
def fetch_catalog(api_key: str, *, refresh: bool, record: dict) -> pd.DataFrame:
    """Full parameter-1003 series catalog (all observation places)."""

    url = HYDAPI + "/Series?" + urllib.parse.urlencode({"Parameter": PARAMETER})
    path = RAW / "series_parameter_1003.json"
    if refresh or not path.is_file():
        document, headers = http_json(url, api_key=api_key)
        if document is None:
            raise RuntimeError(f"series catalog unavailable (HTTP 404): {url}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=1))
        record["requests"].append(
            {
                "retrieved_utc": utc_stamp(),
                "url": url,
                "cache_path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "rate_limit_limit": headers.get("x-rate-limit-limit"),
            }
        )
    else:
        print(f"  cache hit {path.relative_to(ROOT)}", flush=True)
        record["requests"].append(_cache_request_entry(path, url))
    document = json.loads(path.read_text())

    rows = []
    for series in document["data"]:
        if int(series.get("parameter") or -1) != PARAMETER:
            continue
        daily = None
        for item in series.get("resolutionList") or []:
            try:
                if int(item.get("resTime") or -1) == RESOLUTION_TIME:
                    daily = item
                    break
            except (TypeError, ValueError):
                continue
        if daily is None:
            continue
        rows.append(
            {
                "station_id": str(series["stationId"]),
                "station_name": series.get("stationName"),
                "parameter": int(series.get("parameter")),
                "parameter_name": series.get("parameterName"),
                "unit": series.get("unit"),
                "measured_or_derived": series.get("measuredOrDerived"),
                "observation_place": series.get("observationPlace"),
                "aggregation_method": daily.get("method"),
                "resolution_time_minutes": int(daily.get("resTime")),
                "time_offset_minutes": daily.get("timeOffset"),
                "daily_data_from": daily.get("dataFromTime"),
                "daily_data_to": daily.get("dataToTime"),
                "full_series_data_from": series.get("serieFrom"),
                "full_series_data_to": series.get("serieTo"),
                "latitude": series.get("latitude"),
                "longitude": series.get("longitude"),
                "county": series.get("countyName"),
                "council": series.get("councilName"),
                "masl": series.get("masl"),
            }
        )
    catalog = pd.DataFrame(rows)
    catalog["daily_start"] = pd.to_datetime(catalog["daily_data_from"], utc=True)
    catalog["daily_end"] = pd.to_datetime(catalog["daily_data_to"], utc=True)
    # A station can publish several versions of the parameter-1003 series; the
    # Observations endpoint returns the preferred version when VersionNumber is
    # omitted, so keep one catalog row per station (longest/most recent archive).
    before = len(catalog)
    catalog = (
        catalog.sort_values(
            ["station_id", "daily_end", "daily_start"], ascending=[True, False, True]
        )
        .drop_duplicates("station_id", keep="first")
        .reset_index(drop=True)
    )
    removed = before - len(catalog)
    catalog.to_csv(RAW / "station_catalog_daily_parameter_1003.csv", index=False)
    catalog.attrs["duplicate_series_rows_removed"] = removed
    return catalog


def fetch_station_metadata(
    api_key: str, station_ids: list[str], *, refresh: bool, record: dict
) -> pd.DataFrame:
    meta_dir = RAW / "station_metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    fetched = 0
    for position, station_id in enumerate(station_ids, start=1):
        path = meta_dir / f"{_safe_name(station_id)}.json"
        if refresh or not path.is_file():
            url = HYDAPI + "/Stations?" + urllib.parse.urlencode({"StationId": station_id})
            document, _headers = http_json(url, api_key=api_key)
            if document is None:
                document = {"itemCount": 0, "data": [], "http_status": 404}
            document["_request_url"] = url
            document["_retrieved_utc"] = utc_stamp()
            path.write_text(json.dumps(document, ensure_ascii=False, indent=1))
            fetched += 1
            if fetched % 100 == 0:
                print(f"  metadata {position}/{len(station_ids)}", flush=True)
        else:
            record["requests"].append(_cache_request_entry(path))
        document = json.loads(path.read_text())
        entry = (document.get("data") or [None])[0]
        if entry is None:
            rows.append({"station_id": station_id, "metadata_available": False})
            continue
        rows.append(
            {
                "station_id": station_id,
                "metadata_available": True,
                "regine_no": entry.get("regineNo"),
                "hierarchy": entry.get("hierarchy"),
                "river_name": entry.get("riverName"),
                "lake_no": entry.get("lakeNo"),
                "lake_name": entry.get("lakeName"),
                "reservoir_no": entry.get("reservoirNo"),
                "reservoir_name": entry.get("reservoirName"),
                "station_type_name": entry.get("stationTypeName"),
                "station_status_name": entry.get("stationStatusName"),
                "catchment_regulation_type": entry.get("catchmentRegTypeName"),
                "first_year_regulation": entry.get("firstYearRegulation"),
                "regulation_area": entry.get("regulationArea"),
                "drainage_basin_area": entry.get("drainageBasinArea"),
                "drainage_basin_key": entry.get("drainageBasinKey"),
                "height_minimum": entry.get("heightMinimum"),
                "height_maximum": entry.get("heightMaximum"),
                "gradient_river": entry.get("gradientRiver"),
                "metadata_masl": entry.get("masl"),
                "metadata_latitude": entry.get("latitude"),
                "metadata_longitude": entry.get("longitude"),
                "owner": entry.get("owner"),
                "n_series": len(entry.get("seriesList") or []),
            }
        )
    frame = pd.DataFrame(rows)
    frame.to_csv(RAW / "station_metadata_flat.csv", index=False)
    record["metadata_requests_fetched"] = fetched
    return frame


# --------------------------------------------------------------------------- #
# stage 2: observations
# --------------------------------------------------------------------------- #
def fetch_observations(
    api_key: str,
    catalog: pd.DataFrame,
    *,
    refresh: bool,
    record: dict,
) -> pd.DataFrame:
    obs_dir = RAW / "observations"
    obs_dir.mkdir(parents=True, exist_ok=True)

    work = catalog.copy()
    work["request_start"] = work["daily_start"].dt.date
    work["request_end"] = work["daily_end"].dt.date
    work["estimated_days"] = (work["daily_end"] - work["daily_start"]).dt.days + 1
    work = work.sort_values(["request_start", "station_id"]).reset_index(drop=True)

    batches: list[list[int]] = []
    current: list[int] = []
    total = 0
    for index, row in work.iterrows():
        estimate = int(max(row["estimated_days"], 1))
        if current and (
            total + estimate > OBSERVATION_BATCH_TARGET
            or len(current) >= OBSERVATION_MAX_SERIES
        ):
            batches.append(current)
            current, total = [], 0
        current.append(index)
        total += estimate
    if current:
        batches.append(current)

    rows = []
    fetched = 0
    empty_series = 0
    for position, batch in enumerate(batches, start=1):
        block = work.loc[batch]
        stations = list(block["station_id"])
        start = block["request_start"].min().isoformat()
        end = block["request_end"].max().isoformat()
        key = f"obs_{position:04d}_{_safe_name(stations[0])}__n{len(stations)}_{start}_{end}"
        path = obs_dir / f"{key}.json"
        if refresh or not path.is_file():
            url = HYDAPI + "/Observations?" + urllib.parse.urlencode(
                {
                    "StationId": ",".join(stations),
                    "Parameter": PARAMETER,
                    "ResolutionTime": RESOLUTION_TIME,
                    "ReferenceTime": f"{start}/{end}",
                }
            )
            document, _headers = http_json(url, api_key=api_key)
            if document is None:
                document = {"itemCount": 0, "data": [], "http_status": 404, "request_url": url}
            document["_request_url"] = url
            document["_retrieved_utc"] = utc_stamp()
            path.write_text(json.dumps(document, ensure_ascii=False))
            fetched += 1
            print(
                f"  observations batch {position}/{len(batches)} "
                f"stations={len(stations)} bytes={path.stat().st_size}",
                flush=True,
            )
        else:
            record["requests"].append(_cache_request_entry(path))
        document = json.loads(path.read_text())
        returned = {str(series["stationId"]) for series in document.get("data") or []}
        missing = [sid for sid in stations if sid not in returned]
        if missing:
            record["stations_absent_from_api_response"].extend(missing)
        for series in document.get("data") or []:
            station_id = str(series["stationId"])
            observations = series.get("observations") or []
            if not observations:
                empty_series += 1
            method = series.get("method")
            unit = series.get("unit")
            for item in observations:
                rows.append(
                    {
                        "station_id": station_id,
                        "time_raw": item.get("time"),
                        "value": item.get("value"),
                        "quality": item.get("quality"),
                        "correction": item.get("correction"),
                        "series_method": method,
                        "series_unit": unit,
                        "series_version": series.get("serieVersionNo"),
                    }
                )
    record["observation_requests_fetched"] = fetched
    record["observation_batches"] = len(batches)
    record["observation_series_empty"] = empty_series
    raw = pd.DataFrame(rows)
    if raw.empty:
        raise RuntimeError("no observations returned by HydAPI")
    raw.to_parquet(RAW / "observations_raw.parquet", index=False)
    return raw


# --------------------------------------------------------------------------- #
# stage 3: QC + networks
# --------------------------------------------------------------------------- #
def qc_observations(raw: pd.DataFrame, accepted: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = raw.copy()
    frame["quality"] = pd.to_numeric(frame["quality"], errors="coerce")
    frame["correction"] = pd.to_numeric(frame["correction"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["time_utc"] = pd.to_datetime(frame["time_raw"], utc=True, errors="coerce")
    frame["station_id"] = frame["station_id"].astype(str)
    frame = frame[frame["station_id"].isin(set(accepted["station_id"]))]

    # NVE documents the 1440 series as the calendar day in Norwegian normal
    # time (UTC+1); snap the UTC timestamp into that day.
    frame["date"] = (
        frame["time_utc"] + NORWAY_STANDARD_OFFSET
    ).dt.tz_localize(None).dt.normalize()

    frame["drop_reason"] = ""
    frame.loc[frame["time_utc"].isna(), "drop_reason"] = "unparsable_timestamp"
    frame.loc[
        frame["drop_reason"].eq("")
        & ~frame["quality"].isin(ACCEPT_QUALITY),
        "drop_reason",
    ] = "quality_not_primary_or_secondary_controlled"
    frame.loc[
        frame["drop_reason"].eq("") & ~frame["correction"].isin(ACCEPT_CORRECTION),
        "drop_reason",
    ] = "correction_nonzero"
    # HydAPI encodes a missing daily value as JSON null but still returns the
    # row with its quality/correction flags; classify that before the range test
    # so "out of range" keeps meaning "a number that is not plausible".
    frame.loc[frame["drop_reason"].eq("") & frame["value"].isna(), "drop_reason"] = (
        "value_missing_null"
    )
    low, high = PLAUSIBLE_TEMPERATURE_C
    frame.loc[
        frame["drop_reason"].eq("")
        & ~frame["value"].between(low, high, inclusive="both"),
        "drop_reason",
    ] = "value_out_of_plausible_range"
    frame.loc[
        frame["drop_reason"].eq("")
        & ~frame["series_method"].astype(str).isin(ACCEPT_AGGREGATION),
        "drop_reason",
    ] = "aggregation_method_not_mean"
    frame.loc[
        frame["drop_reason"].eq("")
        & ~frame["series_unit"].astype(str).eq("°C"),
        "drop_reason",
    ] = "unit_not_degc"
    frame.loc[frame["drop_reason"].eq("") & frame["date"].isna(), "drop_reason"] = (
        "unparsable_timestamp"
    )

    passed = frame[frame["drop_reason"].eq("")].copy()

    # duplicates within a station-day: count them, then average. Only the value
    # is aggregated; the provider flags are constant for a station (unit and
    # aggregation method come from the series metadata and are validated above).
    passed = passed.sort_values(["station_id", "date", "time_utc"])
    grouped = (
        passed.groupby(["station_id", "date"], as_index=False)
        .agg(
            temperature_c=("value", "mean"),
            provider_quality_code=("quality", "first"),
            provider_correction_code=("correction", "first"),
            provider_series_method=("series_method", "first"),
            n_source_values=("value", "size"),
        )
        .sort_values(["station_id", "date"])
    )
    grouped["provider_quality_code"] = grouped["provider_quality_code"].astype(int)
    grouped["provider_correction_code"] = grouped["provider_correction_code"].astype(int)
    grouped["n_duplicate_extra"] = grouped["n_source_values"] - 1

    # per-station / per-year QC ledger
    ledger_rows = []
    reasons = [reason for reason in frame["drop_reason"].unique() if reason]
    for station_id, block in frame.groupby("station_id"):
        row = {"station_id": station_id, "n_values_returned": len(block)}
        for reason in reasons:
            row[f"dropped_{reason}"] = int(block["drop_reason"].eq(reason).sum())
        row["n_values_dropped_total"] = int(block["drop_reason"].ne("").sum())
        row["n_values_accepted"] = len(block) - row["n_values_dropped_total"]
        row["accepted_quality_codes"] = ";".join(
            str(code) for code in sorted(block.loc[block["drop_reason"].eq(""), "quality"].dropna().unique())
        )
        row["accepted_correction_codes"] = ";".join(
            str(code)
            for code in sorted(block.loc[block["drop_reason"].eq(""), "correction"].dropna().unique())
        )
        row["n_duplicate_extra_days"] = int(grouped.loc[grouped["station_id"].eq(station_id), "n_duplicate_extra"].sum())
        ledger_rows.append(row)
    ledger = pd.DataFrame(ledger_rows)
    return grouped, ledger


def write_networks(wide: pd.DataFrame, stations: pd.DataFrame, record: dict) -> list[dict]:
    manifest_rows = []
    for network_id, group in stations.groupby("network_id"):
        if len(group) < MIN_STATIONS_PER_NETWORK:
            continue
        if int((group["n_complete_years"] >= MIN_COMPLETE_YEARS).sum()) < MIN_STATIONS_PER_NETWORK:
            continue
        directory = NETWORKS / str(network_id)
        directory.mkdir(parents=True, exist_ok=True)
        keep = [station for station in group["station_id"] if station in wide.columns]
        panel = wide.loc[:, keep]
        # trim the calendar grid to the days this network actually covers, so the
        # file's first/last date describe the network rather than the provider
        covered = panel.notna().any(axis=1)
        if covered.any():
            panel = panel.loc[covered.idxmax() : covered[::-1].idxmax()]
        panel.index.name = "date"
        path = directory / "daily_wide_temperature.csv"
        panel.to_csv(path, date_format="%Y-%m-%d")
        subset = group[group["station_id"].isin(keep)].copy()
        subset.to_csv(directory / "stations.csv", index=False)
        first = panel.index.min()
        last = panel.index.max()
        names = subset["network_name"].dropna().unique()
        manifest_rows.append(
            {
                "network_id": str(network_id),
                "network_name": str(names[0]) if len(names) else "",
                "provider": PROVIDER,
                "n_stations": len(keep),
                "network_in_v17_basin": bool(subset["network_in_v17_basin"].any()),
                "station_ids": ";".join(keep),
                "n_stations_ge4_years": int((subset["n_complete_years"] >= MIN_COMPLETE_YEARS).sum()),
                "n_complete_station_years": int(subset["n_complete_years"].sum()),
                "first_date": first.date().isoformat(),
                "last_date": last.date().isoformat(),
                "n_days": int(len(panel)),
                "daily_wide_temperature_csv": str(path.relative_to(ROOT)),
                "daily_wide_temperature_sha256": sha256_file(path),
                "stations_csv": str((directory / "stations.csv").relative_to(ROOT)),
            }
        )
        print(
            f"  network {network_id}: {len(keep)} stations, "
            f"{int(subset['n_complete_years'].sum())} complete station-years",
            flush=True,
        )
    manifest = pd.DataFrame(manifest_rows).sort_values("network_id")
    manifest.to_csv(OUT_ROOT / "networks_manifest.csv", index=False)
    record["networks"] = manifest.to_dict(orient="records")
    return manifest_rows


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def _load_catalog_with_metadata(api_key: str, *, refresh: bool, record: dict) -> pd.DataFrame:
    """Series catalog + station metadata + per-station keep/drop decision."""

    print("[stage] catalog", flush=True)
    catalog = fetch_catalog(api_key, refresh=refresh, record=record)
    print(f"  parameter {PARAMETER} daily series rows: {len(catalog)}", flush=True)

    catalog["is_river"] = catalog["observation_place"].astype(str).str.startswith(
        ACCEPT_OBSERVATION_PLACES
    )
    catalog["is_measured"] = (
        catalog["measured_or_derived"].astype(str).str.strip().isin(ACCEPT_MEASURED_OR_DERIVED)
    )
    catalog["is_mean"] = catalog["aggregation_method"].astype(str).isin(ACCEPT_AGGREGATION)
    catalog["in_v17_roster"] = catalog["station_id"].isin(V17_STATION_IDS)
    # v17 consumed whole NVE drainage basins; flag every candidate basin that the
    # v17 roster already touched so the downstream report can separate them
    v17_basin_numbers = {basin_number(value) for value in V17_STATION_IDS if "." in str(value)}

    print("[stage] station metadata", flush=True)
    metadata = fetch_station_metadata(
        api_key, sorted(catalog["station_id"]), refresh=refresh, record=record
    )
    catalog = catalog.merge(metadata, on="station_id", how="left")
    catalog["metadata_available"] = catalog["metadata_available"].fillna(False).astype(bool)
    catalog["drop_reason"] = np.nan
    catalog["drop_reason"] = catalog["drop_reason"].astype(object)
    catalog["basin_number"] = catalog["station_id"].map(basin_number)
    regine_prefix = (
        catalog["regine_no"].fillna("").astype(str).str.split(".").str[0].str.zfill(3)
    )
    catalog["regine_basin_number"] = regine_prefix.where(catalog["regine_no"].notna())
    catalog["basin_prefix_mismatch"] = catalog["regine_basin_number"].notna() & catalog[
        "regine_basin_number"
    ].ne(catalog["basin_number"])
    catalog["network_id"] = "nve_basin_" + catalog["basin_number"]
    catalog["network_in_v17_basin"] = catalog["basin_number"].isin(v17_basin_numbers)
    catalog["network_name"] = catalog["hierarchy"].fillna("").astype(str)
    missing_name = catalog["network_name"].eq("")
    catalog.loc[missing_name, "network_name"] = catalog.loc[missing_name, "river_name"].fillna("")
    catalog["network_name"] = catalog["network_name"].replace({"": np.nan})
    catalog["is_svalbard"] = catalog["basin_number"].eq(SVALBARD_BASIN_NUMBER) | catalog[
        "station_id"
    ].astype(str).str.startswith("400.")
    catalog["in_coastal_catchment"] = (
        catalog["river_name"].fillna("").astype(str).str.upper().str.contains("KYSTFELT")
    ) | (
        catalog["hierarchy"].fillna("").astype(str).str.upper().str.contains("KYSTFELT|FJORD")
    )

    catalog.loc[~catalog["is_river"], "drop_reason"] = "observation_place_not_river"
    catalog.loc[catalog["is_river"] & ~catalog["is_measured"], "drop_reason"] = "not_measured"
    catalog.loc[
        catalog["is_river"] & catalog["is_measured"] & ~catalog["is_mean"], "drop_reason"
    ] = "daily_resolution_aggregation_not_mean"
    catalog.loc[catalog["in_v17_roster"], "drop_reason"] = "in_v17_station_roster"
    catalog.loc[catalog["is_svalbard"], "drop_reason"] = "svalbard_non_mainland"
    # a dtype=str metadata merge can render an unset marker as the string "nan"
    catalog["drop_reason"] = catalog["drop_reason"].replace({"nan": np.nan, "": np.nan})
    candidates = catalog[catalog["drop_reason"].isna()].copy()

    place_counts = catalog["observation_place"].value_counts().to_dict()
    record["catalog_counts"] = {
        "parameter_1003_daily_series_rows": int(len(catalog)),
        "duplicate_version_series_rows_collapsed": int(
            catalog.attrs.get("duplicate_series_rows_removed", 0)
        ),
        "unique_stations": int(catalog["station_id"].nunique()),
        "observation_place_counts": {str(k): int(v) for k, v in place_counts.items()},
        "measured_or_derived_counts": {
            str(k): int(v) for k, v in catalog["measured_or_derived"].value_counts().items()
        },
        "aggregation_method_counts": {
            str(k): int(v) for k, v in catalog["aggregation_method"].value_counts().items()
        },
        "unit_counts": {str(k): int(v) for k, v in catalog["unit"].value_counts().items()},
        "river_measured_mean_rows": int(
            (catalog["is_river"] & catalog["is_measured"] & catalog["is_mean"]).sum()
        ),
        "dropped_observation_place_not_river": int((~catalog["is_river"]).sum()),
        "dropped_not_measured": int((catalog["is_river"] & ~catalog["is_measured"]).sum()),
        "dropped_daily_resolution_aggregation_not_mean": int(
            (catalog["is_river"] & catalog["is_measured"] & ~catalog["is_mean"]).sum()
        ),
        "dropped_v17_roster_stations": int(
            catalog["drop_reason"].eq("in_v17_station_roster").sum()
        ),
        "dropped_svalbard_non_mainland": int(
            catalog["drop_reason"].eq("svalbard_non_mainland").sum()
        ),
        "candidate_stations": int(len(candidates)),
    }
    catalog.to_csv(RAW / "station_decisions.csv", index=False)
    candidates.to_csv(OUT_ROOT / "candidate_stations.csv", index=False)

    record["candidate_counts"] = {
        "candidate_stations": int(len(candidates)),
        "candidate_basins": int(candidates["network_id"].nunique()),
        "metadata_available": int(candidates["metadata_available"].sum()),
        "stations_missing_metadata": int((~candidates["metadata_available"]).sum()),
        "basins_without_metadata_name": int(
            candidates.loc[candidates["network_name"].isna(), "network_id"].nunique()
        ),
        "basins_without_regine_number": int(
            candidates.loc[candidates["regine_basin_number"].isna(), "network_id"].nunique()
        ),
        "regine_prefix_mismatch_stations": int(candidates["basin_prefix_mismatch"].sum()),
        "regulated_stations": int(
            candidates["catchment_regulation_type"]
            .fillna("")
            .astype(str)
            .str.contains("regulert")
            .sum()
        ),
        "coastal_catchment_river_stations": int(candidates["in_coastal_catchment"].sum()),
    }
    return candidates


def _run_observations(
    api_key: str,
    candidates: pd.DataFrame,
    *,
    refresh: bool,
    record: dict,
) -> pd.DataFrame:
    print(f"[stage] observations for {len(candidates)} candidate stations", flush=True)
    raw = fetch_observations(api_key, candidates, refresh=refresh, record=record)
    print(f"  raw observation rows: {len(raw)}", flush=True)
    return raw


def _assemble(
    raw: pd.DataFrame, candidates: pd.DataFrame, record: dict, *, dev_limited: bool
) -> None:
    print("[stage] assemble", flush=True)
    accepted = candidates.dropna(subset=["network_id"]).copy()
    accepted["station_latitude"] = accepted["metadata_latitude"].fillna(accepted["latitude"])
    accepted["station_longitude"] = accepted["metadata_longitude"].fillna(accepted["longitude"])
    accepted["measurement_statistic"] = (
        "daily_mean_1440min_" + accepted["aggregation_method"].astype(str).str.lower()
    )

    daily, ledger = qc_observations(raw, accepted)
    daily.to_parquet(OUT_ROOT / "daily_long_qc.parquet", index=False)
    ledger.to_csv(OUT_ROOT / "qc_ledger.csv", index=False)

    record["qc_counts"] = {
        "raw_observation_rows": int(len(raw)),
        "stations_requested": int(raw["station_id"].nunique()),
        "qc_passing_station_days": int(len(daily)),
        "rows_dropped_total": int(ledger["n_values_dropped_total"].sum()),
        "drop_reason_totals": {
            column.replace("dropped_", ""): int(ledger[column].sum())
            for column in ledger.columns
            if column.startswith("dropped_") and column != "dropped_total"
        },
        "drop_reason_note": (
            "reasons are assigned in a fixed precedence order (place/aggregation "
            "screen first, then quality, correction, range, then missing null); a "
            "row failing several checks is counted under the first one, so the "
            "totals are disjoint and sum to rows_dropped_total"
        ),
        "stations_with_accepted_values": int(daily["station_id"].nunique()),
        "accepted_quality_code_counts": {
            str(int(k)): int(v)
            for k, v in daily["provider_quality_code"].value_counts().items()
        },
        "accepted_correction_code_counts": {
            str(int(k)): int(v)
            for k, v in daily["provider_correction_code"].value_counts().items()
        },
        "duplicate_station_days": int((daily["n_duplicate_extra"] > 0).sum()),
    }

    # complete-year screen (structural eligibility only; no scoring)
    year_rows = []
    for station_id, block in daily.groupby("station_id"):
        for year in complete_years_from_series(block.set_index("date")["temperature_c"]):
            year_rows.append({"station_id": station_id, "year": int(year)})
    year_frame = pd.DataFrame(year_rows, columns=["station_id", "year"])
    if len(year_frame):
        year_frame = year_frame.merge(
            accepted[["station_id", "network_id"]], on="station_id", how="left"
        )
        year_frame.to_csv(OUT_ROOT / "complete_station_years.csv", index=False)
    record["complete_year_counts"] = {
        "stations_with_complete_years": int(year_frame["station_id"].nunique())
        if len(year_frame)
        else 0,
        "complete_station_years": int(len(year_frame)),
        "stations_with_ge4_complete_years": int(
            year_frame.groupby("station_id").size().ge(MIN_COMPLETE_YEARS).sum()
        )
        if len(year_frame)
        else 0,
    }

    wide = daily.pivot_table(
        index="date", columns="station_id", values="temperature_c", aggfunc="mean"
    ).sort_index()
    wide.index.name = "date"

    ledger_map = {row.station_id: row for row in ledger.itertuples()}
    stations_rows = []
    for row in accepted.sort_values("station_id").itertuples():
        station_id = str(row.station_id)
        if station_id not in wide.columns:
            continue
        series = pd.to_numeric(wide[station_id], errors="coerce")
        years = complete_years_from_series(series)
        present = series.dropna()
        entry = ledger_map.get(station_id)
        stations_rows.append(
            {
                "network_id": row.network_id,
                "network_name": row.network_name,
                "station_id": station_id,
                "provider": PROVIDER,
                "river_name": row.river_name,
                "latitude": row.station_latitude,
                "longitude": row.station_longitude,
                "basin_number": row.basin_number,
                "regine_no": row.regine_no,
                "n_complete_years": len(years),
                "complete_years": ";".join(str(year) for year in years),
                "first_date": present.index.min().date().isoformat() if len(present) else "",
                "last_date": present.index.max().date().isoformat() if len(present) else "",
                "n_days": int(len(present)),
                "n_dropped_qc": int(entry.n_values_dropped_total) if entry is not None else 0,
                "accepted_quality_codes": str(entry.accepted_quality_codes)
                if entry is not None
                else "",
                "measurement_statistic": row.measurement_statistic,
                "quality_assurance": QUALITY_ASSURANCE,
                "catchment_regulation_type": row.catchment_regulation_type,
                "first_year_regulation": row.first_year_regulation,
                "in_coastal_catchment": bool(row.in_coastal_catchment),
                "network_in_v17_basin": bool(row.network_in_v17_basin),
            }
        )
    stations_frame = pd.DataFrame(stations_rows)
    if stations_frame.empty:
        record["failures"].append(
            "no station produced a QC-passing daily value; no network was written"
        )
        (OUT_ROOT / "ingest.json").write_text(
            json.dumps(record, indent=1, ensure_ascii=False, default=str)
        )
        print("FAILURE: no station has QC-passing values", flush=True)
        return

    eligible_mask = stations_frame["n_complete_years"] >= MIN_COMPLETE_YEARS
    eligible_pairs = (
        stations_frame[eligible_mask].groupby("network_id")["station_id"].nunique()
    )
    kept_networks = sorted(eligible_pairs[eligible_pairs >= MIN_STATIONS_PER_NETWORK].index)

    # only the stations that satisfy the structural eligibility rule enter the
    # written panel (a network may hold extra short-record stations that are
    # irrelevant to the frozen fit/donor design)
    stations_out = stations_frame[
        stations_frame["network_id"].isin(kept_networks) & eligible_mask
    ].copy()
    stations_out.sort_values(["network_id", "station_id"]).to_csv(
        OUT_ROOT / "stations.csv", index=False
    )
    year_frame = (
        year_frame[year_frame["station_id"].isin(set(stations_out["station_id"]))]
        if len(year_frame)
        else year_frame
    )
    if len(year_frame):
        year_frame.to_csv(OUT_ROOT / "complete_station_years.csv", index=False)

    print("[stage] writing networks", flush=True)
    manifest_rows = write_networks(wide, stations_out, record)

    record["final_counts"] = {
        "candidate_basins_scanned": int(candidates["network_id"].nunique()),
        "candidate_stations": int(len(candidates)),
        "networks_kept": int(len(manifest_rows)),
        "stations_in_kept_networks": int(len(stations_out)),
        "stations_ge4_complete_years_in_kept_networks": int(
            (stations_out["n_complete_years"] >= MIN_COMPLETE_YEARS).sum()
        ),
        "complete_station_years_in_kept_networks": int(stations_out["n_complete_years"].sum()),
        "basins_dropped_below_minimum_stations_or_years": int(
            candidates["network_id"].nunique() - len(kept_networks)
        ),
        "kept_networks_with_no_v17_station": int(
            sum(1 for row in manifest_rows if not row["network_in_v17_basin"])
        ),
        "kept_networks_sharing_a_v17_basin": int(
            sum(1 for row in manifest_rows if row["network_in_v17_basin"])
        ),
        "stations_in_kept_networks_with_no_v17_station": int(
            stations_out.loc[~stations_out["network_in_v17_basin"], "station_id"].nunique()
        ),
        "complete_station_years_in_kept_networks_with_no_v17_station": int(
            stations_out.loc[
                ~stations_out["network_in_v17_basin"], "n_complete_years"
            ].sum()
        ),
    }
    record["kept_networks_detail"] = [
        {
            "network_id": row["network_id"],
            "network_name": row["network_name"],
            "n_stations": int(row["n_stations"]),
            "n_complete_station_years": int(row["n_complete_station_years"]),
            "first_date": row["first_date"],
            "last_date": row["last_date"],
        }
        for _, row in pd.DataFrame(manifest_rows).iterrows()
    ]
    record["qc_ledger_totals"] = {
        "stations_in_qc_ledger": int(len(ledger)),
        "stations_with_zero_accepted_values": int(ledger["n_values_accepted"].eq(0).sum()),
    }
    record["caveats"] = build_caveats(record, stations_out, candidates)
    if dev_limited:
        record["caveats"].insert(
            0,
            "DEVELOPMENT RUN with --dev-limit-stations: counts above cover only a "
            "truncated station list and must not be reported.",
        )
    write_record(record)
    print(json.dumps(record["final_counts"], indent=1), flush=True)


def write_record(record: dict, *, merge_previous: bool = False) -> None:
    """Write ingest.json.

    With ``merge_previous`` the request log, stage counts and API-derived counts
    from an earlier partial run of the *same* scope are carried forward, so that
    running ``--stage catalog`` / ``--stage observations`` / ``--stage assemble``
    in sequence (or re-running one stage against the cache) still yields one
    cumulative record instead of losing the retrieval provenance.
    """

    path = OUT_ROOT / "ingest.json"
    if merge_previous and path.is_file():
        previous = json.loads(path.read_text())
        if previous.get("run_scope") == record.get("run_scope"):
            known = {item.get("url") for item in record.get("requests", [])}
            for item in previous.get("requests", []):
                if item.get("url") not in known:
                    record.setdefault("requests", []).append(item)
            for key in (
                "api",
                "rules",
                "catalog_counts",
                "candidate_counts",
                "observation_requests_fetched",
                "observation_batches",
                "observation_series_empty",
            ):
                if key not in record and key in previous:
                    record[key] = previous[key]
            record["stations_absent_from_api_response"] = sorted(
                set(record.get("stations_absent_from_api_response", []))
                | set(previous.get("stations_absent_from_api_response", []))
            )
    record["inputs_sha256"] = {
        str(V17_ROSTER.relative_to(ROOT)): sha256_file(V17_ROSTER),
        str(PROTOCOL.relative_to(ROOT)): sha256_file(PROTOCOL),
        str(Path(__file__).relative_to(ROOT)): sha256_file(Path(__file__)),
    }
    (OUT_ROOT / "ingest.json").write_text(
        json.dumps(record, indent=1, ensure_ascii=False, default=str)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        default="all",
        choices=("all", "catalog", "metadata", "observations", "assemble"),
    )
    parser.add_argument("--refresh", action="store_true", help="ignore cached raw responses")
    parser.add_argument(
        "--dev-limit-stations",
        type=int,
        default=0,
        help="development smoke test: ingest at most N candidate stations",
    )
    args = parser.parse_args(argv)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    NETWORKS.mkdir(parents=True, exist_ok=True)

    record: dict = {
        "provider": PROVIDER,
        "protocol": str(PROTOCOL.relative_to(ROOT)),
        "generated_utc": utc_stamp(),
        "run_scope": (
            f"stage={args.stage}"
            + (f", dev_limit_stations={args.dev_limit_stations}" if args.dev_limit_stations else "")
            + (", refresh_cache" if args.refresh else "")
        ),
        "script": str(Path(__file__).relative_to(ROOT)),
        "api": {
            "base": HYDAPI,
            "parameter": PARAMETER,
            "parameter_name": PARAMETER_NAME,
            "resolution_time_minutes": RESOLUTION_TIME,
            "aggregation_method_accepted": list(ACCEPT_AGGREGATION),
            "day_definition": (
                "HydAPI 1440-minute series: daily statistic for the calendar day in "
                "Norwegian normal time (UTC+1), timestamped 11:00Z; aggregation method "
                "reported per series in the Observations response 'method' field"
            ),
            "quality_codes": {
                "accepted": list(ACCEPT_QUALITY),
                "meaning": {
                    "0": "Unknown",
                    "1": "Uncontrolled",
                    "2": "PrimaryControlled",
                    "3": "SecondaryControlled",
                },
            },
            "correction_codes_accepted": list(ACCEPT_CORRECTION),
            "observation_places_accepted_prefix": list(ACCEPT_OBSERVATION_PLACES),
            "measured_or_derived_accepted": list(ACCEPT_MEASURED_OR_DERIVED),
            "plausible_range_c": list(PLAUSIBLE_TEMPERATURE_C),
        },
        "rules": {
            "min_stations_per_network": MIN_STATIONS_PER_NETWORK,
            "min_complete_years_per_station": MIN_COMPLETE_YEARS,
            "complete_year_definition": ">=365 QC-passing days (366 in leap years)",
            "v17_roster_exclusion": str(V17_ROSTER.relative_to(ROOT)),
        },
        "requests": [],
        "stations_absent_from_api_response": [],
        "caveats": [],
        "failures": [],
    }

    api_key = discover_public_hydapi_key()
    roster = pd.read_csv(V17_ROSTER, dtype=str)
    global V17_STATION_IDS
    V17_STATION_IDS = set(roster["station_id"].astype(str))
    print(f"v17 roster stations excluded: {len(V17_STATION_IDS)}", flush=True)

    candidates = _load_catalog_with_metadata(api_key, refresh=args.refresh, record=record)
    if args.stage in ("catalog", "metadata"):
        write_record(record, merge_previous=True)
        print("catalog + metadata stages complete", flush=True)
        return 0

    candidates_for_run = candidates
    if args.dev_limit_stations:
        candidates_for_run = candidates.head(args.dev_limit_stations).copy()

    if args.stage == "assemble":
        raw_path = RAW / "observations_raw.parquet"
        if not raw_path.is_file():
            raise RuntimeError(
                f"stage=assemble needs {raw_path.relative_to(ROOT)}; run the observations stage first"
            )
        raw = pd.read_parquet(raw_path)
        print(f"  loaded cached raw observations: {len(raw)} rows", flush=True)
    else:
        raw = _run_observations(
            api_key,
            candidates_for_run,
            refresh=args.refresh,
            record=record,
        )
        if args.stage == "observations":
            print("observations stage complete", flush=True)
            return 0

    _assemble(raw, candidates_for_run, record, dev_limited=bool(args.dev_limit_stations))
    return 0

def build_caveats(record: dict, stations: pd.DataFrame, candidates: pd.DataFrame) -> list[str]:
    caveats = [
        (
            "PROTOCOL SCOPE: MULTI_AGENCY_TRANSPORT_PROTOCOL.md Amendment 1 states "
            "that nve_hydapi 'is not part of the sealed transport panel' because the "
            "provider participated in v17 development, and that new NVE basins are "
            "'reported separately as a secondary probe, never as transport "
            "confirmation'. This ingest is therefore a secondary-probe feed. Networks "
            "are flagged network_in_v17_basin when the station-id basin number already "
            "appears in the v17 station roster; use those flags to separate "
            "previously-touched basins from genuinely new ones."
        ),
        (
            "Assurance stratum (Amendment 2): every station is written with "
            f"quality_assurance={QUALITY_ASSURANCE}. NVE HydAPI quality codes 2 and 3 "
            "are PrimaryControlled / SecondaryControlled, i.e. checked at source; "
            "uncontrolled (1) and unknown (0) values were dropped, so no NVE series in "
            "this panel is provider_published_unqualified."
        ),
        (
            "Value resolution: HydAPI 1440-minute water temperature is returned as a "
            "float with ~6 decimals; NVE does not publish a rounding step, so the "
            "ingest neither rounds nor rescales. Accepted series are the provider's own "
            "daily statistic (aggregation method 'Mean' in the Observations response), "
            "not a re-aggregation of hourly or instantaneous data. Series whose "
            "1440-minute archive reports method 'Instantaneous' were dropped."
        ),
        (
            "Day definition: HydAPI timestamps 1440-minute values at 11:00Z because the "
            "daily statistic is the calendar day in Norwegian normal time (UTC+1, fixed "
            "offset, no DST). The ingest snaps each value to that UTC+1 calendar day. A "
            "UTC-day interpretation would move 13 of 24 hours per value; the choice "
            "follows NVE's own documentation."
        ),
        (
            "Missing-day convention: missing daily values arrive as JSON null (about "
            "one third of all returned rows) and are dropped, as are quality/correction "
            "rejects; absent days stay blank in daily_wide_temperature.csv. Downstream "
            "readers must decide whether a blank is an outage or an unchecked day. "
            "qc_ledger.csv reports per-station drop counts and reasons, in a fixed "
            "precedence order."
        ),
        (
            "Regulation: Norwegian river temperature series are frequently downstream of "
            "hydropower regulation. catchmentRegTypeName and firstYearRegulation are "
            "carried in candidate_stations.csv and stations.csv so the transport "
            "analysis can stratify or report regulation status; the ingest does not "
            "exclude regulated basins."
        ),
        (
            "Basin grouping uses the station-id drainage-basin number (NVE vassdrag "
            "number, zero-padded), which matches the REGINE prefix of regineNo for "
            "every candidate station whose metadata still exists. NVE's current station "
            "registry returned HTTP 404 for many historical stations, so "
            "regineNo/riverName/hierarchy are missing for a large share of candidates "
            "(see ingest.json candidate_counts); the basin number from the station id "
            "is therefore used as the grouping key and network names fall back to the "
            "station river name. Networks are full vassdrag groupings, much larger than "
            "the 1-8 station subsets of the earlier p0_07 NVE probe."
        ),
        (
            "Svalbard stations (station-id basin 400, Ny-Alesund/Longyearbyen/"
            "Barentsburg/Pyramiden) were dropped as non-mainland; the panel is mainland "
            "Norway only."
        ),
        (
            "Dropped observation places: the parameter-1003 daily catalogue also "
            "contains Utslippspunkt (outfall), Innsjo (lake), Kum (manhole), Magasin "
            "(reservoir), Inntak (intake), Overlop (spillway), Grunnvannsror "
            "(groundwater), I ror (in pipe), Overforingstunnel (transfer tunnel), air "
            "temperature and snow-pillow series. None of them is river water "
            "temperature, so none is in this panel; see catalog_counts in ingest.json."
        ),
        (
            "No frozen-screen performance was computed on this panel: the ingest stops "
            "at QC and structural eligibility (>= 2 stations with >= 4 complete "
            "calendar years)."
        ),
    ]
    regulated = int(
        candidates["catchment_regulation_type"].fillna("").astype(str).str.contains("regulert").sum()
    )
    if regulated:
        caveats.append(
            f"{regulated} of {len(candidates)} candidate stations carry a "
            "catchmentRegTypeName that indicates regulation (regulert); the share "
            "inside the kept networks is reported in stations.csv."
        )
    n_coastal = int(candidates["in_coastal_catchment"].sum())
    if n_coastal:
        caveats.append(
            f"{n_coastal} candidate stations sit in a coastal REGINE catchment "
            "(riverName/hierarchy contains KYSTFELT or FJORD). They are genuine river "
            "temperature series (observationPlace starts with 'Elv') and are kept, but "
            "a reviewer may want them flagged as fjord-influenced; the flag "
            "in_coastal_catchment is written per station."
        )
    return caveats


if __name__ == "__main__":
    raise SystemExit(main())
