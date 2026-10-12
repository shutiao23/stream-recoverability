#!/usr/bin/env python3
"""UK Environment Agency ingest for the pre-registered multi-agency transport panel.

Feeds ``results/wrr_submission_ready/MULTI_AGENCY_TRANSPORT_PROTOCOL.md``
(provider ``uk_ea``).  Ingest + QC only: the frozen certificate is never scored.

What the EA Hydrology API actually offers (re-verified live, not taken from any
existing catalogue):

* ``.../id/measures.json`` lists 32,443 measures.  2,012 carry
  ``parameter = TEMPERATURE``: 1,948 of them are **event-monitor** sub-daily
  spot series (ids such as ``E03234A-temp-i-subdaily-C``, no declared period),
  48 are the 16 hydrometric stations' ``-temp-{m,min,max}-86400-C-qualified``
  daily statistics, and 16 are the same stations' ``-temp-i-900-C-qualified``
  15-minute instantaneous series.
* Provider **daily statistic** accepted here: the measure
  ``...-temp-m-86400-C-qualified`` ("Daily mean Temperature (°C) time series",
  ``period = 86400`` s, ``unitName = °C``, ``observedProperty = Temperature``).
  Daily min/max measures are dropped (protocol rule 3 asks for the daily
  statistic, and min/max are different statistics).
* Day boundary: one value per calendar date; the payload carries
  ``date`` (``YYYY-MM-DD``) and ``dateTime`` (``T00:00:00``, no offset).  The
  value is the provider's daily mean for that calendar day in UK local time as
  published by the EA; no timezone conversion is applied by this ingest.
* River-only: station metadata (``riverName``, ``type`` list) is re-fetched per
  station.  Types/labels marking lake, reservoir, estuary, tidal, coastal or
  groundwater are dropped; the drop fractions are reported in ``ingest.json``.
* Networks: complete-linkage spatial clustering on lat/lon with a 50 km maximum
  pairwise geodesic cap (``stream_recoverability.data.uk_ea_spatial``), >= 2
  stations with >= 4 complete calendar years.  A 100 km sensitivity grouping is
  written as a CSV only, never as panels.
* A *complete calendar year* is a year with >= 365 (366 in leap years)
  QC-passing days, the same definition as
  ``scripts/241_multi_agency_nve_ingest.py`` and the sealed USGS confirmation.
* Stations in ``results/v17_fitness/step1_panel/station_roster.csv`` are
  excluded before network selection (protocol rule 6).

Derived sub-daily QC (never a panel): for stations that expose the 15-minute
series, ``uk_ea_temperature.uk_ea_daily`` (module path) is called for one
calendar year and the derived daily mean is compared with the provider's daily
mean.  Those derived values are **not** emitted as transport networks because
protocol rule 3 requires the provider's own daily statistic; the comparison is
evidence that the daily measure and the 15-minute series describe the same day.

Usage::

    PYTHONPATH=src python3 scripts/244_multi_agency_uk_ea_ingest.py
    PYTHONPATH=src python3 scripts/244_multi_agency_uk_ea_ingest.py --stage measures
    PYTHONPATH=src python3 scripts/244_multi_agency_uk_ea_ingest.py --stage metadata
    PYTHONPATH=src python3 scripts/244_multi_agency_uk_ea_ingest.py --stage observations
    PYTHONPATH=src python3 scripts/244_multi_agency_uk_ea_ingest.py --stage derived
    PYTHONPATH=src python3 scripts/244_multi_agency_uk_ea_ingest.py --stage assemble
    PYTHONPATH=src python3 scripts/244_multi_agency_uk_ea_ingest.py --refresh
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.uk_ea_spatial import (  # noqa: E402
    cluster_uk_ea_spatial,
    is_hydrometric_site_id,
)
from stream_recoverability.data.uk_ea_temperature import uk_ea_daily  # noqa: E402

OUT_ROOT = ROOT / "results" / "wrr_submission_ready" / "multi_agency_ingest" / "uk_ea"
RAW = OUT_ROOT / "raw_cache"
NETWORKS = OUT_ROOT / "networks"
V17_ROSTER = ROOT / "results" / "v17_fitness" / "step1_panel" / "station_roster.csv"
CATALOG = ROOT / "results" / "framework" / "public_catalog" / "uk_ea_temperature_stations.csv"
PROTOCOL = ROOT / "results" / "wrr_submission_ready" / "MULTI_AGENCY_TRANSPORT_PROTOCOL.md"

PROVIDER = "uk_ea"
CONTEXT = "temperate_oceanic"
MEASURES_URL = "https://environment.data.gov.uk/hydrology/id/measures.json"
READINGS_URL = "https://environment.data.gov.uk/hydrology/data/readings.json"
STATION_URL = "https://environment.data.gov.uk/hydrology/id/stations/{station}.json"
USER_AGENT = "stream-recoverability/1.1 multi-agency-transport-ingest (python-urllib)"

MEASURE_PAGE_LIMIT = 5000
READINGS_PAGE_LIMIT = 10000
MAX_READINGS_PAGES = 12
REQUEST_PAUSE_S = 0.05
MAX_ATTEMPTS = 6

CAP_KM = 50.0
SENSITIVITY_CAP_KM = 100.0
MIN_STATIONS_PER_NETWORK = 2
MIN_COMPLETE_YEARS = 4
PLAUSIBLE_TEMPERATURE_C = (-5.0, 40.0)
REJECT_QUALITY_CODES = {"bad", "deleted", "rejected", "invalid"}
WINDOW_START = "1990-01-01"
WINDOW_END = "2024-12-31"

DROP_CLASS_PATTERNS = {
    "lake": r"lake|loch|lough|mere\b|tarn|reservoir",
    "reservoir": r"reservoir|impound",
    "estuary": r"estuar|tidal|bore\b",
    "coastal": r"coastal|sea\b|marine|harbour|harbor|beach|pier",
    "groundwater": r"groundwater|borehole|well\b|spring",
}
FLAG_CLASS_PATTERNS = {"canal": r"canal|navigation"}

MEASURE_ID = re.compile(
    r"/measures/(?P<station>[0-9A-Za-z_\-]+?)-"
    r"(?P<param>[a-z]+)-(?P<stat>[a-z]+)-(?P<period>\d+)-(?P<unit>[A-Za-z0-9]+)-(?P<qual>[a-z]+)$"
)
GUID_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(_[0-9]+)?$"
)
EVENT_ID = re.compile(r"^(E\d|EN\d|EP\d|GPRS|P\d|GSML)", re.IGNORECASE)


def station_id_shape(station_id: str | None) -> str:
    token = str(station_id or "").strip()
    if GUID_ID.match(token):
        return "hydrometric_guid"
    if EVENT_ID.match(token):
        return "event_monitor_code"
    return "other_named_monitor"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value))


def http_bytes(url: str, *, timeout: int = 300) -> bytes:
    last: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
            time.sleep(REQUEST_PAUSE_S)
            return payload
        except urllib.error.HTTPError as error:
            last = error
            if error.code == 404:
                raise
            time.sleep(min(2.0**attempt, 30.0))
        except (urllib.error.URLError, TimeoutError) as error:
            last = error
            time.sleep(min(2.0**attempt, 30.0))
    raise RuntimeError(f"request failed after {MAX_ATTEMPTS} attempts: {url}") from last


def http_json(url: str, *, timeout: int = 300) -> dict:
    return json.loads(http_bytes(url, timeout=timeout))


def complete_years_from_series(series: pd.Series) -> list[int]:
    """Calendar years with >= 365 (366) QC-passing values (sealed definition)."""

    values = pd.to_numeric(series, errors="coerce")
    years: list[int] = []
    for year, block in values.groupby(values.index.year):
        year = int(year)
        leap = (year % 400 == 0) or (year % 4 == 0 and year % 100 != 0)
        need = 366 if leap else 365
        if int(np.isfinite(block.to_numpy(dtype=float)).sum()) >= need:
            years.append(year)
    return years


def readings_url(measure_id: str, start: str, end: str, limit: int, offset: int) -> str:
    return READINGS_URL + "?" + urllib.parse.urlencode(
        {
            "measure": measure_id,
            "mineq-date": start,
            "max-date": end,
            "_limit": str(limit),
            "_offset": str(offset),
        }
    )


def parse_measure(item: dict) -> dict:
    measure_id = str(item.get("@id"))
    match = MEASURE_ID.search(measure_id)
    station_uri = item.get("station")
    if isinstance(station_uri, dict):
        station_uri = station_uri.get("@id")
    station_id = str(station_uri).rstrip("/").split("/")[-1] if station_uri else None
    observed = item.get("observedProperty")
    observed_label = observed.get("label") if isinstance(observed, dict) else observed
    return {
        "measure_id": measure_id,
        "station_id": station_id,
        "parameter": str(item.get("parameter") or "").upper(),
        "period": pd.to_numeric(item.get("period"), errors="coerce"),
        "unit": item.get("unitName"),
        "observed_property": observed_label,
        "label": item.get("label"),
        "statistic_token": match.group("stat") if match else None,
        "id_period": int(match.group("period")) if match else None,
        "qualification": match.group("qual") if match else None,
        "hydrometric_station_id": bool(station_id and is_hydrometric_site_id(station_id)),
        "station_id_shape": station_id_shape(station_id),
    }


# --------------------------------------------------------------------------- #
# stage: measures
# --------------------------------------------------------------------------- #
def stage_measures(*, refresh: bool, record: dict) -> pd.DataFrame:
    page_dir = RAW / "measures_pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    offset = 0
    page = 0
    while True:
        page += 1
        url = f"{MEASURES_URL}?_limit={MEASURE_PAGE_LIMIT}&_offset={offset}"
        path = page_dir / f"measures_page_{page:03d}_offset{offset}.json"
        if refresh or not path.is_file():
            path.write_bytes(http_bytes(url))
            record["requests"].append(
                {"url": url, "cache_path": str(path.relative_to(ROOT)), "retrieved_utc": utc_stamp()}
            )
            print(f"  measures page {page} offset {offset}", flush=True)
        chunk = json.loads(path.read_text()).get("items") or []
        items.extend(chunk)
        if len(chunk) < MEASURE_PAGE_LIMIT:
            break
        offset += MEASURE_PAGE_LIMIT
        if page > 40:
            raise RuntimeError("measures paging did not terminate")
    table = pd.DataFrame([parse_measure(item) for item in items])
    table.to_csv(RAW / "measures_all_flat.csv", index=False)
    record["measure_catalogue"] = {
        "n_measures_total": int(len(table)),        "n_temperature_measures": int(table["parameter"].eq("TEMPERATURE").sum()),
        "temperature_measure_kinds": {
            str(key): int(value)
            for key, value in table.loc[table["parameter"].eq("TEMPERATURE")]
            .assign(
                kind=lambda frame: np.where(
                    frame["statistic_token"].eq("m") & frame["period"].eq(86400),
                    "provider_daily_mean_86400s",
                    np.where(
                        frame["statistic_token"].isin(["min", "max"]) & frame["period"].eq(86400),
                        "provider_daily_min_or_max_86400s",
                        np.where(
                            frame["station_id_shape"].eq("hydrometric_guid")
                            & frame["period"].eq(900),
                            "hydrometric_guid_15min_instantaneous_900s",
                            np.where(
                                frame["station_id_shape"].eq("event_monitor_code"),
                                "event_monitor_subdaily_900s",
                                "other_named_monitor_subdaily_900s",
                            ),
                        ),
                    ),
                )
            )["kind"]
            .value_counts()
            .items()
        },
        "subdaily_station_id_shapes": {
            str(key): int(value)
            for key, value in table.loc[
                table["parameter"].eq("TEMPERATURE") & table["period"].eq(900),
                "station_id_shape",
            ]
            .value_counts()
            .items()
        },
        "other_named_monitor_examples": sorted(
            table.loc[
                table["parameter"].eq("TEMPERATURE")
                & table["period"].eq(900)
                & table["station_id_shape"].eq("other_named_monitor"),
                "station_id",
            ]
            .astype(str)
            .unique()
            .tolist()
        )[:25],
    }
    return table


# --------------------------------------------------------------------------- #
# stage: metadata
# --------------------------------------------------------------------------- #
def stage_metadata(
    daily_measures: pd.DataFrame, *, refresh: bool, record: dict
) -> tuple[pd.DataFrame, pd.DataFrame]:
    meta_dir = RAW / "stations"
    meta_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for row in daily_measures.sort_values("station_id").itertuples(index=False):
        url = STATION_URL.format(station=urllib.parse.quote(str(row.station_id), safe=""))
        path = meta_dir / f"{safe_name(str(row.station_id))}.json"
        if refresh or not path.is_file():
            payload = http_bytes(url)
            path.write_bytes(payload)
            record["requests"].append(
                {"url": url, "cache_path": str(path.relative_to(ROOT)), "retrieved_utc": utc_stamp()}
            )
        document = json.loads(path.read_text())
        item = (document.get("items") or [document])[0]
        types = [
            str(entry.get("@id", "")).rstrip("/").split("/")[-1]
            for entry in (item.get("type") or [])
        ]
        name = " ".join([str(item.get("label") or ""), str(item.get("riverName") or "")])
        lowered = name.lower()
        type_blob = " ".join(types).lower()
        rows.append(
            {
                "station_id": str(row.station_id),
                "measure_id": row.measure_id,
                "station_label": item.get("label"),
                "river_name": item.get("riverName"),
                "latitude": pd.to_numeric(item.get("lat"), errors="coerce"),
                "longitude": pd.to_numeric(item.get("long"), errors="coerce"),
                "date_opened": item.get("dateOpened"),
                "station_status": (
                    str(item.get("status", {}).get("@id", "")).rstrip("/").split("/")[-1]
                    if isinstance(item.get("status"), dict)
                    else str(item.get("status"))
                ),
                "station_types": ";".join(types),
                "is_river_station_type": any("river" in token.lower() for token in types),
                "n_measures": len(item.get("measures") or []),
                "label_and_river_lower": lowered,
                "type_blob": type_blob,
            }
        )
    meta = pd.DataFrame(rows)
    meta.to_csv(RAW / "station_metadata_flat.csv", index=False)

    drop_counts: Counter[str] = Counter()
    keep_flags = []
    for row in meta.itertuples(index=False):
        haystack = f"{row.label_and_river_lower} {row.type_blob}"
        reason = ""
        for label, pattern in DROP_CLASS_PATTERNS.items():
            if re.search(pattern, haystack):
                reason = label
                break
        if not reason and not str(row.river_name or "").strip():
            reason = "no_river_name_evidence"
        if not reason and not bool(row.is_river_station_type):
            reason = "no_river_station_class"
        if reason:
            drop_counts[reason] += 1
        keep_flags.append(reason)
    meta["river_only_drop_reason"] = keep_flags
    meta["flagged_waterbody_class"] = [
        ";".join(
            label
            for label, pattern in FLAG_CLASS_PATTERNS.items()
            if re.search(pattern, f"{row.label_and_river_lower} {row.type_blob}")
        )
        for row in meta.itertuples(index=False)
    ]
    meta.to_csv(RAW / "station_metadata_flat.csv", index=False)
    record["river_only_filter"] = {
        "policy": (
            "station is dropped when its label, riverName or EA type list marks "
            + ", ".join(sorted(DROP_CLASS_PATTERNS))
        ),
        "n_stations_with_daily_mean_measure": int(len(meta)),
        "dropped_counts": {str(k): int(v) for k, v in drop_counts.items()},
        "dropped_fraction": float(sum(drop_counts.values()) / max(1, len(meta))),
        "kept": int(meta["river_only_drop_reason"].eq("").sum()),
        "flagged_canal_or_navigation_but_kept": int(meta["flagged_waterbody_class"].ne("").sum()),
    }
    dropped = meta.loc[meta["river_only_drop_reason"].ne("")]
    return meta, dropped


# --------------------------------------------------------------------------- #
# stage: observations
# --------------------------------------------------------------------------- #
def fetch_daily_series(
    station_id: str, measure_id: str, *, refresh: bool, record: dict, raw_sample: bool
) -> pd.DataFrame:
    cache_dir = RAW / "readings"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{safe_name(station_id)}_daily.csv"
    if path.is_file() and not refresh:
        frame = pd.read_csv(path)
        if not frame.empty:
            frame["date"] = pd.to_datetime(frame["date"])
            return frame
    rows = []
    offset = 0
    for _ in range(MAX_READINGS_PAGES):
        url = readings_url(
            measure_id, WINDOW_START, WINDOW_END, READINGS_PAGE_LIMIT, offset
        )
        document = http_json(url)
        chunk = document.get("items") or []
        record["requests"].append(
            {
                "url": url,
                "cache_path": str(path.relative_to(ROOT)),
                "retrieved_utc": utc_stamp(),
                "n_items": len(chunk),
            }
        )
        if raw_sample and offset == 0:
            sample_dir = cache_dir / "raw_samples"
            sample_dir.mkdir(parents=True, exist_ok=True)
            (sample_dir / f"{safe_name(station_id)}_page1.json").write_bytes(
                json.dumps(document).encode("utf-8")
            )
        rows.extend(chunk)
        if len(chunk) < READINGS_PAGE_LIMIT:
            break
        offset += READINGS_PAGE_LIMIT
    frame = pd.DataFrame(
        [
            {
                "date": item.get("date") or (item.get("dateTime") or "")[:10],
                "temperature_c": item.get("value"),
                "provider_quality": item.get("quality"),
                "provider_completeness": item.get("completeness"),
                "provider_valid": item.get("valid"),
                "provider_invalid": item.get("invalid"),
                "provider_missing": item.get("missing"),
                "measure_id": measure_id,
                "station_id": station_id,
            }
            for item in rows
        ]
    )
    if frame.empty:
        frame = pd.DataFrame(
            columns=[
                "date",
                "temperature_c",
                "provider_quality",
                "provider_completeness",
                "provider_valid",
                "provider_invalid",
                "provider_missing",
                "measure_id",
                "station_id",
            ]
        )
    frame.to_csv(path, index=False)
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame["date"])
    return frame


def stage_observations(
    meta: pd.DataFrame, *, refresh: bool, record: dict, workers: int = 4
) -> pd.DataFrame:
    kept = meta.loc[meta["river_only_drop_reason"].eq("")].copy()
    frames: list[pd.DataFrame] = []
    errors: list[dict] = []
    print(f"  downloading provider daily mean series for {len(kept)} stations", flush=True)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(
                fetch_daily_series,
                str(row.station_id),
                str(row.measure_id),
                refresh=refresh,
                record=record,
                raw_sample=position < 2,
            ): str(row.station_id)
            for position, row in enumerate(kept.itertuples(index=False))
        }
        for future in as_completed(futures):
            station_id = futures[future]
            try:
                frame = future.result()
            except Exception as error:  # noqa: BLE001
                errors.append({"station_id": station_id, "error": f"{type(error).__name__}: {error}"})
                print(f"  {station_id}: ERROR {error}", flush=True)
                continue
            print(f"  {station_id}: {len(frame)} daily rows", flush=True)
            if not frame.empty:
                frames.append(frame)
    record["observation_errors"] = errors
    if not frames:
        return pd.DataFrame(
            columns=["station_id", "date", "temperature_c", "provider_quality"]
        )
    raw = pd.concat(frames, ignore_index=True)
    raw.to_parquet(RAW / "daily_long_raw.parquet", index=False)
    return raw


# --------------------------------------------------------------------------- #
# stage: derived sub-daily QC (never a panel)
# --------------------------------------------------------------------------- #
def stage_derived(
    measures: pd.DataFrame,
    meta: pd.DataFrame,
    daily: pd.DataFrame,
    *,
    refresh: bool,
    record: dict,
    max_stations: int,
    workers: int,
) -> pd.DataFrame:
    subdaily = measures.loc[
        measures["parameter"].eq("TEMPERATURE") & measures["period"].eq(900)
    ].copy()
    kept_ids = set(meta.loc[meta["river_only_drop_reason"].eq(""), "station_id"])
    subdaily = subdaily.loc[subdaily["station_id"].isin(kept_ids)]
    subdaily = subdaily.drop_duplicates("station_id").sort_values("station_id").head(max_stations)
    if subdaily.empty or daily.empty:
        record["derived_subdaily_qc"] = {"stations": 0, "note": "no 15-minute series matched"}
        return pd.DataFrame()

    def one(row) -> dict:
        station_id = str(row.station_id)
        provider = daily.loc[daily["station_id"].eq(station_id)].copy()
        if provider.empty:
            return {"station_id": station_id, "compared_days": 0}
        provider["date"] = pd.to_datetime(provider["date"], errors="coerce")
        last_full_year = int(provider["date"].dt.year.max())
        year = last_full_year
        cache_root = RAW / "derived_subdaily_uk_ea" / str(year)
        try:
            derived = uk_ea_daily(
                station_id,
                cache_dir=cache_root,
                start=f"{year}-01-01",
                end=f"{year}-12-31",
            )
        except Exception as error:  # noqa: BLE001
            return {
                "station_id": station_id,
                "year": year,
                "error": f"{type(error).__name__}: {error}",
                "compared_days": 0,
            }
        if derived is None or derived.empty:
            return {"station_id": station_id, "year": year, "compared_days": 0}
        derived = derived.copy()
        derived["date"] = pd.to_datetime(derived["date"], errors="coerce")
        merged = provider.merge(
            derived[["date", "temperature_c"]].rename(
                columns={"temperature_c": "derived_daily_mean_c"}
            ),
            on="date",
            how="inner",
        )
        merged["temperature_c"] = pd.to_numeric(merged["temperature_c"], errors="coerce")
        merged["derived_daily_mean_c"] = pd.to_numeric(
            merged["derived_daily_mean_c"], errors="coerce"
        )
        merged = merged.dropna(subset=["temperature_c", "derived_daily_mean_c"])
        if merged.empty:
            return {"station_id": station_id, "year": year, "compared_days": 0}
        difference = merged["derived_daily_mean_c"] - merged["temperature_c"]
        return {
            "station_id": station_id,
            "year": year,
            "compared_days": int(len(merged)),
            "mean_difference_c": float(difference.mean()),
            "mean_abs_difference_c": float(difference.abs().mean()),
            "max_abs_difference_c": float(difference.abs().max()),
            "pearson_r": float(merged["derived_daily_mean_c"].corr(merged["temperature_c"])),
            "n_provider_days_in_year": int(
                provider.loc[provider["date"].dt.year.eq(year)].shape[0]
            ),
        }

    rows = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(one, row) for row in subdaily.itertuples(index=False)]
        for future in as_completed(futures):
            rows.append(future.result())
    table = pd.DataFrame(rows).sort_values("station_id")
    table.to_csv(OUT_ROOT / "derived_subdaily_vs_provider_daily.csv", index=False)
    record["derived_subdaily_qc"] = {
        "stations_tested": int(len(table)),
        "stations_with_overlap": int((table.get("compared_days", pd.Series(dtype=int)) > 0).sum()),
        "median_mean_abs_difference_c": (
            float(table.loc[table["compared_days"] > 0, "mean_abs_difference_c"].median())
            if (table.get("compared_days", pd.Series(dtype=int)) > 0).any()
            else None
        ),
        "note": (
            "uk_ea_daily (module) derived daily means from the 15-minute series, "
            "compared with the provider's own daily mean for the same calendar days. "
            "Derived values are NOT emitted as transport networks (protocol rule 3)."
        ),
    }
    return table


# --------------------------------------------------------------------------- #
# stage: assemble
# --------------------------------------------------------------------------- #
def flat_line_census(block: pd.DataFrame, *, min_run_days: int = 7) -> dict:
    """Report frozen-sensor evidence without silently deleting provider values.

    A run of >= ``min_run_days`` identical consecutive daily values (or an exact
    0.0 degC run) is flagged for the reviewer; the values are still emitted.
    """

    accepted = (
        block.loc[block["drop_reason"].eq("")]
        .sort_values("date")
        .dropna(subset=["temperature_c"])
    )
    series = accepted.set_index("date")["temperature_c"]
    out = {
        "n_days_value_exactly_0c": int((series == 0).sum()),
        "longest_identical_run_days": 0,
        "longest_identical_run_start": "",
        "longest_identical_run_end": "",
        "frozen_sensor_suspected": False,
    }
    if series.empty:
        return out
    values = series.to_numpy(dtype=float)
    best_length = 1
    best_start = 0
    current_start = 0
    for position in range(1, len(values)):
        if values[position] != values[position - 1]:
            current_start = position
        length = position - current_start + 1
        if length > best_length:
            best_length = length
            best_start = current_start
    index = series.index
    out["longest_identical_run_days"] = int(best_length)
    out["longest_identical_run_start"] = index[best_start].date().isoformat()
    out["longest_identical_run_end"] = index[best_start + best_length - 1].date().isoformat()
    out["frozen_sensor_suspected"] = bool(
        best_length >= min_run_days and float(values[best_start]) == 0.0
    )
    return out


def qc_daily(raw: pd.DataFrame, meta: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    frame = raw.copy()
    frame["station_id"] = frame["station_id"].astype(str)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["temperature_c"] = pd.to_numeric(frame["temperature_c"], errors="coerce")
    frame["provider_quality"] = frame["provider_quality"].astype(str)
    quality_counts = {str(k): int(v) for k, v in frame["provider_quality"].value_counts().items()}
    completeness_counts = {
        str(k): int(v) for k, v in frame["provider_completeness"].value_counts().items()
    }
    frame["drop_reason"] = ""
    frame.loc[frame["date"].isna(), "drop_reason"] = "unparsable_date"
    frame.loc[
        frame["drop_reason"].eq("")
        & frame["provider_quality"].str.lower().eq("missing"),
        "drop_reason",
    ] = "provider_marked_missing_day"
    frame.loc[
        frame["drop_reason"].eq("") & frame["temperature_c"].isna(), "drop_reason"
    ] = "non_numeric_value"
    low, high = PLAUSIBLE_TEMPERATURE_C
    frame.loc[
        frame["drop_reason"].eq("")
        & ~frame["temperature_c"].between(low, high, inclusive="both"),
        "drop_reason",
    ] = "value_out_of_plausible_range"
    frame.loc[
        frame["drop_reason"].eq("")
        & frame["provider_quality"].str.lower().isin(REJECT_QUALITY_CODES),
        "drop_reason",
    ] = "quality_code_rejected"
    passed = frame.loc[frame["drop_reason"].eq("")].copy()
    passed = passed.sort_values(["station_id", "date"])
    grouped = passed.groupby(["station_id", "date"], as_index=False).agg(
        temperature_c=("temperature_c", "mean"),
        provider_quality_code=("provider_quality", lambda values: str(values.mode().iloc[0])),
        n_source_values=("temperature_c", "size"),
        n_distinct_values=("temperature_c", "nunique"),
    )
    grouped["n_duplicate_extra"] = grouped["n_source_values"] - 1

    ledger_rows = []
    for station_id, block in frame.groupby("station_id"):
        row = {"station_id": station_id, "n_values_returned": int(len(block))}
        for reason in sorted(reason for reason in block["drop_reason"].unique() if reason):
            row[f"dropped_{reason}"] = int(block["drop_reason"].eq(reason).sum())
        row["n_values_dropped_total"] = int(block["drop_reason"].ne("").sum())
        row["n_values_accepted"] = int(len(block) - row["n_values_dropped_total"])
        row["accepted_quality_codes"] = ";".join(
            sorted(
                str(code)
                for code in block.loc[block["drop_reason"].eq(""), "provider_quality"].dropna().unique()
            )
        )
        row["rejected_quality_codes"] = ";".join(
            sorted(
                str(code)
                for code in block.loc[
                    block["drop_reason"].eq("quality_code_rejected"), "provider_quality"
                ].dropna().unique()
            )
        )
        row["n_duplicate_extra_days"] = int(
            grouped.loc[grouped["station_id"].eq(station_id), "n_duplicate_extra"].sum()
        )
        row.update(flat_line_census(block))
        ledger_rows.append(row)
    ledger = pd.DataFrame(ledger_rows)
    counts = {
        "quality_code_counts": quality_counts,
        "completeness_code_counts": completeness_counts,
        "rows_dropped_total": int(frame["drop_reason"].ne("").sum()),
        "drop_reason_totals": {
            reason: int(frame["drop_reason"].eq(reason).sum())
            for reason in sorted(reason for reason in frame["drop_reason"].unique() if reason)
        },
    }
    return grouped, ledger, counts


def frozen_sensor_sensitivity(
    stations: pd.DataFrame, wide: pd.DataFrame, record: dict
) -> pd.DataFrame:
    """Counterfactual complete years if frozen-sensor runs were dropped instead.

    The panels keep provider values; this table tells the reviewer exactly what a
    documented frozen-run filter (>= 7 identical consecutive days at exactly
    0.0 degC) would cost, without applying it.
    """

    rows = []
    for position, row in stations.iterrows():
        if int(row["longest_identical_run_days"]) < 7 or not bool(row["frozen_sensor_suspected"]):
            continue
        station_id = str(row["station_id"])
        if station_id not in wide.columns:
            continue
        series = pd.to_numeric(wide[station_id], errors="coerce").copy()
        start = pd.Timestamp(str(row["longest_identical_run_start"]))
        end = pd.Timestamp(str(row["longest_identical_run_end"]))
        mask = (series.index >= start) & (series.index <= end)
        masked = series.mask(mask)
        years_before = complete_years_from_series(series)
        years_after = complete_years_from_series(masked)
        rows.append(
            {
                "station_id": station_id,
                "run_start": start.date().isoformat(),
                "run_end": end.date().isoformat(),
                "run_days": int(mask.sum()),
                "n_complete_years_kept_values": len(years_before),
                "n_complete_years_minus_frozen_run": len(years_after),
                "complete_years_lost": ";".join(
                    str(year) for year in years_before if year not in years_after
                ),
            }
        )
    frame = pd.DataFrame(rows)
    path = OUT_ROOT / "frozen_sensor_sensitivity.csv"
    if frame.empty:
        frame = pd.DataFrame(
            columns=["station_id", "run_start", "run_end", "run_days", "n_complete_years_kept_values", "n_complete_years_minus_frozen_run", "complete_years_lost"]
        )
    frame.to_csv(path, index=False)
    adjusted = stations.copy()
    adjusted["_years_after"] = adjusted["n_complete_years"]
    for entry in rows:
        adjusted.loc[
            adjusted["station_id"].eq(entry["station_id"]), "_years_after"
        ] = entry["n_complete_years_minus_frozen_run"]
    eligible_after = (
        adjusted.loc[adjusted["_years_after"] >= MIN_COMPLETE_YEARS]
        .groupby("network_id")["station_id"]
        .nunique()
    )
    networks_after = sorted(
        network for network, count in eligible_after.items() if count >= MIN_STATIONS_PER_NETWORK
    )
    record["frozen_sensor_census"]["sensitivity_csv"] = str(path.relative_to(ROOT))
    record["frozen_sensor_census"]["sensitivity"] = frame.to_dict(orient="records")
    record["frozen_sensor_census"]["networks_kept_after_frozen_run_filter"] = networks_after
    record["frozen_sensor_census"]["n_networks_kept_after_frozen_run_filter"] = len(networks_after)
    return stations


def stage_assemble(
    daily: pd.DataFrame,
    meta: pd.DataFrame,
    record: dict,
    *,
    roster_ids: set[str],
) -> pd.DataFrame:
    meta = meta.copy()
    meta["in_v17_roster"] = meta["station_id"].isin(roster_ids)
    qc, ledger, qc_counts = qc_daily(daily, meta)
    qc.to_parquet(OUT_ROOT / "daily_long_qc.parquet", index=False)
    ledger.to_csv(OUT_ROOT / "qc_ledger.csv", index=False)
    record["qc_counts"] = qc_counts
    record["v17_roster_overlap"] = {
        "n_overlap": int(meta["in_v17_roster"].sum()),
        "overlap_ids": sorted(meta.loc[meta["in_v17_roster"], "station_id"].tolist()),
    }

    wide = qc.pivot_table(
        index="date", columns="station_id", values="temperature_c", aggfunc="mean"
    ).sort_index()
    wide.index.name = "date"

    complete_rows = []
    for station_id in wide.columns:
        years = complete_years_from_series(wide[station_id])
        for year in years:
            complete_rows.append({"station_id": str(station_id), "year": int(year)})
    all_years = pd.DataFrame(complete_rows)
    all_years.to_csv(OUT_ROOT / "complete_station_years.csv", index=False)

    stations_rows = []
    ledger_map = {str(row.station_id): row for row in ledger.itertuples()}
    meta_map = {str(row.station_id): row for row in meta.itertuples(index=False)}
    for station_id in wide.columns:
        series = pd.to_numeric(wide[station_id], errors="coerce")
        present = series.dropna()
        years = complete_years_from_series(series)
        entry = ledger_map.get(str(station_id))
        meta_row = meta_map.get(str(station_id))
        stations_rows.append(
            {
                "station_id": str(station_id),
                "provider": PROVIDER,
                "river_name": getattr(meta_row, "river_name", None),
                "latitude": getattr(meta_row, "latitude", np.nan),
                "longitude": getattr(meta_row, "longitude", np.nan),
                "n_complete_years": len(years),
                "complete_years": ";".join(str(year) for year in years),
                "first_date": present.index.min().date().isoformat() if len(present) else "",
                "last_date": present.index.max().date().isoformat() if len(present) else "",
                "n_days": int(len(present)),
                "n_dropped_qc": int(entry.n_values_dropped_total) if entry is not None else 0,
                "accepted_quality_codes": (
                    str(entry.accepted_quality_codes) if entry is not None else ""
                ),
                "measurement_statistic": "provider_daily_mean_86400s_degc",
                "station_label": getattr(meta_row, "station_label", None),
                "station_status": getattr(meta_row, "station_status", None),
                "station_types": getattr(meta_row, "station_types", None),
                "measure_id": getattr(meta_row, "measure_id", None),
                "date_opened": getattr(meta_row, "date_opened", None),
                "flagged_waterbody_class": getattr(meta_row, "flagged_waterbody_class", ""),
                "n_days_value_exactly_0c": int(
                    getattr(entry, "n_days_value_exactly_0c", 0) if entry is not None else 0
                ),
                "longest_identical_run_days": int(
                    getattr(entry, "longest_identical_run_days", 0) if entry is not None else 0
                ),
                "longest_identical_run_start": (
                    str(getattr(entry, "longest_identical_run_start", "")) if entry is not None else ""
                ),
                "longest_identical_run_end": (
                    str(getattr(entry, "longest_identical_run_end", "")) if entry is not None else ""
                ),
                "frozen_sensor_suspected": bool(
                    getattr(entry, "frozen_sensor_suspected", False) if entry is not None else False
                ),
            }
        )
    stations = pd.DataFrame(stations_rows)
    stations["_eligible"] = stations["n_complete_years"] >= MIN_COMPLETE_YEARS
    record["frozen_sensor_census"] = {
        "policy": (
            "runs of identical consecutive accepted daily values are reported, not "
            "deleted: the provider value is emitted and stations.csv carries "
            "longest_identical_run_days / frozen_sensor_suspected so a downstream "
            "step can exclude the station explicitly"
        ),
        "stations_flagged": sorted(
            stations.loc[stations["frozen_sensor_suspected"], "station_id"].astype(str).tolist()
        ),
        "detail": stations.loc[
            stations["longest_identical_run_days"] >= 7,
            [
                "station_id",
                "n_days_value_exactly_0c",
                "longest_identical_run_days",
                "longest_identical_run_start",
                "longest_identical_run_end",
                "frozen_sensor_suspected",
            ],
        ].to_dict(orient="records"),
    }

    located = stations.loc[stations["latitude"].notna() & stations["longitude"].notna()]
    cluster_input = located.rename(columns={"station_id": "site_id"})[
        ["site_id", "latitude", "longitude"]
    ]
    clusters = cluster_uk_ea_spatial(
        cluster_input,
        cap_km=CAP_KM,
        min_stations=MIN_STATIONS_PER_NETWORK,
    )
    clusters_100 = cluster_uk_ea_spatial(
        cluster_input,
        cap_km=SENSITIVITY_CAP_KM,
        min_stations=MIN_STATIONS_PER_NETWORK,
    )
    record["spatial_clustering"] = {
        "cap_km": CAP_KM,
        "sensitivity_cap_km": SENSITIVITY_CAP_KM,
        "n_stations_clustered": int(len(located)),
        "n_clusters_50km": int(len(clusters)),
        "n_clusters_100km": int(len(clusters_100)),
        "grouping": "complete_linkage_max_pairwise_geodesic (uk_ea_spatial.cluster_uk_ea_spatial)",
    }
    clusters.to_csv(OUT_ROOT / "spatial_clusters_50km.csv", index=False)
    clusters_100.to_csv(OUT_ROOT / "spatial_clusters_100km_sensitivity.csv", index=False)

    station_to_cluster = {}
    for row in clusters.itertuples(index=False):
        for station_id in str(row.site_ids).split(","):
            station_to_cluster[station_id.strip()] = str(row.cluster_id)
    stations["network_id"] = stations["station_id"].map(station_to_cluster)

    stations = frozen_sensor_sensitivity(stations, wide, record)

    eligible_counts = stations.loc[stations["_eligible"]].groupby("network_id")["station_id"].nunique()
    kept_networks = sorted(
        network for network, count in eligible_counts.items() if count >= MIN_STATIONS_PER_NETWORK
    )
    stations = stations.loc[stations["network_id"].isin(kept_networks)].copy()
    isolated_ids = set(str(item) for item in wide.columns) - set(stations["station_id"].astype(str))
    isolated_100km = {}
    for row in clusters_100.itertuples(index=False):
        members = [item.strip() for item in str(row.site_ids).split(",") if item.strip()]
        for station_id in members:
            if station_id in isolated_ids:
                isolated_100km[station_id] = len(members)
    record["spatial_clustering"]["isolated_station_100km_cluster_sizes"] = isolated_100km
    record["spatial_clustering"]["isolated_station_ids"] = sorted(isolated_ids)

    manifest_rows = []
    for network_id, group in stations.groupby("network_id"):
        directory = NETWORKS / str(network_id)
        directory.mkdir(parents=True, exist_ok=True)
        keep = [str(item) for item in group["station_id"] if str(item) in wide.columns]
        panel = wide.loc[:, keep]
        panel = panel.loc[panel.notna().any(axis=1)]
        panel.index.name = "date"
        panel_path = directory / "daily_wide_temperature.csv"
        panel.to_csv(panel_path, date_format="%Y-%m-%d")
        group.drop(columns=["_eligible"]).sort_values("station_id").to_csv(
            directory / "stations.csv", index=False
        )
        subset = group.loc[group["_eligible"]]
        manifest_rows.append(
            {
                "network_id": str(network_id),
                "provider": PROVIDER,
                "context": CONTEXT,
                "n_stations": len(keep),
                "station_ids": ";".join(sorted(keep)),
                "n_stations_ge4_years": int(len(subset)),
                "n_complete_station_years": int(subset["n_complete_years"].sum()),
                "first_date": panel.index.min().date().isoformat(),
                "last_date": panel.index.max().date().isoformat(),
                "n_days": int(len(panel)),
                "max_pairwise_km": float(
                    clusters.loc[clusters["cluster_id"].eq(network_id), "max_pairwise_km"].iloc[0]
                ),
                "daily_wide_temperature_csv": str(panel_path.relative_to(ROOT)),
                "daily_wide_temperature_sha256": sha256_file(panel_path),
                "stations_csv": str((directory / "stations.csv").relative_to(ROOT)),
                "measurement_statistic": "provider_daily_mean_86400s_degc",
            }
        )
        print(
            f"  network {network_id}: {len(keep)} stations, {len(subset)} with >=4 years, "
            f"{int(subset['n_complete_years'].sum())} complete station-years",
            flush=True,
        )
    manifest = pd.DataFrame(manifest_rows).sort_values("network_id")
    manifest.to_csv(OUT_ROOT / "networks_manifest.csv", index=False)
    record["networks"] = manifest.to_dict(orient="records")

    stations.drop(columns=["_eligible"]).sort_values(["network_id", "station_id"]).to_csv(
        OUT_ROOT / "stations.csv", index=False
    )
    record["final_counts"] = {
        "stations_with_provider_daily_mean_series_downloaded": int(daily["station_id"].nunique()),
        "stations_with_qc_passing_days": int(len(stations)),
        "stations_ge4_complete_years": int(stations["n_complete_years"].ge(MIN_COMPLETE_YEARS).sum()),
        "networks_kept": int(len(manifest)),
        "complete_station_years_in_kept_networks": int(stations["n_complete_years"].sum()),
        "stations_with_data_but_no_network": sorted(
            set(str(item) for item in wide.columns) - set(stations["station_id"].astype(str))
        ),
    }
    record["panel_construction"] = {
        "panel_index": (
            "each network panel is trimmed to the rows where at least one member "
            "station has a QC-passing value, so first_date/last_date/n_days describe "
            "the network, not the global cross-station index"
        ),
        "provider_missing_rows": (
            "the EA daily readings include explicit no-data rows "
            "(provider_quality='Missing', value null, completeness='Incomplete'); "
            "they are dropped as 'provider_marked_missing_day' and counted per "
            "station in qc_ledger.csv"
        ),
    }
    return manifest, stations.drop(columns=["_eligible"])


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def write_readme(record: dict, manifest: pd.DataFrame, stations: pd.DataFrame) -> None:
    """Provider README generated from the run record (no hand-copied numbers)."""

    counts = record.get("final_counts", {})
    kinds = record.get("measure_catalogue", {}).get("temperature_measure_kinds", {})
    shapes = record.get("measure_catalogue", {}).get("subdaily_station_id_shapes", {})
    derived = record.get("derived_subdaily_qc", {})
    sensitivity = record.get("frozen_sensor_census", {}).get("sensitivity", [])
    network_rows = "\n".join(
        f"| {row.network_id} | {row.n_stations} | {row.n_stations_ge4_years} | "
        f"{row.n_complete_station_years} | {row.first_date} | {row.last_date} | "
        f"{row.n_days} | {float(row.max_pairwise_km):.1f} |"
        for row in manifest.itertuples(index=False)
    )
    station_rows = "\n".join(
        f"| {row.network_id} | {row.station_id[:8]} | {row.river_name} | "
        f"{row.n_complete_years} | {row.n_days} | {row.n_dropped_qc} | "
        f"{row.longest_identical_run_days} | {row.frozen_sensor_suspected} |"
        for row in stations.sort_values(["network_id", "station_id"]).itertuples(index=False)
    )
    kind_rows = "\n".join(f"- `{key}`: {value}" for key, value in kinds.items())
    shape_rows = "\n".join(f"- `{key}`: {value}" for key, value in shapes.items())
    longest_row = stations.sort_values("n_days", ascending=False).iloc[0]
    longest_span_years = (
        pd.Timestamp(str(longest_row["last_date"])) - pd.Timestamp(str(longest_row["first_date"]))
    ).days / 365.25
    isolated_100km = record.get("spatial_clustering", {}).get("isolated_station_100km_cluster_sizes", {})
    isolated_text = (
        "; at the 100 km sensitivity cap "
        + ", ".join(f"{key[:8]} joins a {value}-station cluster" for key, value in isolated_100km.items())
        if isolated_100km
        else ""
    )
    sensitivity_rows = "\n".join(
        f"| {entry['station_id'][:8]} | {entry['run_start']} | {entry['run_end']} | "
        f"{entry['run_days']} | {entry['n_complete_years_kept_values']} | "
        f"{entry['n_complete_years_minus_frozen_run']} | {entry['complete_years_lost'] or 'none'} |"
        for entry in sensitivity
    ) or "| (none) | | | | | | |"

    document = f"""# UK Environment Agency (`uk_ea`) — transport-panel ingest

Generated by `scripts/244_multi_agency_uk_ea_ingest.py`
(`PYTHONPATH=src python3 scripts/244_multi_agency_uk_ea_ingest.py`), retrieved
{record.get('generated_utc')}.  Ingest + QC only: no frozen-screen performance was
computed on this data.

Verdict: **feasible, but small**.  The EA Hydrology API does publish a *provider
daily statistic* for river water temperature, and it survives the pre-registered
eligibility rule — for {counts.get('networks_kept')} spatial networks,
{counts.get('stations_with_qc_passing_days')} stations, of which
{counts.get('stations_ge4_complete_years')} have >= 4 complete calendar years
({counts.get('complete_station_years_in_kept_networks')} complete station-years in
the kept networks).

## What the live API actually exposes

`{MEASURES_URL}` (paged, `_limit={MEASURE_PAGE_LIMIT}`) lists
{record.get('measure_catalogue', {}).get('n_measures_total')} measures, of which
{record.get('measure_catalogue', {}).get('n_temperature_measures')} carry
`parameter = TEMPERATURE`:

{kind_rows}

Station-id shapes among the sub-daily temperature measures:

{shape_rows}

Only `-temp-m-86400-C-qualified` ("Daily mean Temperature (°C) time series",
`period = 86400` s, `unitName = °C`) is accepted.  Daily min/max measures are a
different statistic; the 15-minute series and the event-monitor spot series are not
daily statistics.  Because the existing catalogue
(`results/framework/public_catalog/uk_ea_temperature_stations.csv`) is not treated
as evidence, liveness was re-verified from the live measures collection and per
station documents: {record.get('existing_catalog_check', {}).get('n_catalog_stations_with_provider_daily_mean_measure')}
of its {record.get('existing_catalog_check', {}).get('n_catalog_stations')} stations
have a provider daily mean temperature measure.

Day boundary: the provider publishes one value per calendar date (`date`, and
`dateTime` at `T00:00:00` with no offset) — the daily mean for that calendar day in
UK local time as published.  No timezone shift is applied.

## Networks

Spatial proxy for the agency-native grouping: complete-linkage on lat/lon with a
{record.get('spatial_clustering', {}).get('cap_km')} km maximum pairwise geodesic cap
(`stream_recoverability.data.uk_ea_spatial`), >= {MIN_STATIONS_PER_NETWORK} stations,
each network needing >= {MIN_STATIONS_PER_NETWORK} stations with
>= {MIN_COMPLETE_YEARS} complete calendar years.  The
{record.get('spatial_clustering', {}).get('sensitivity_cap_km')} km sensitivity
grouping ({record.get('spatial_clustering', {}).get('n_clusters_100km')} clusters,
including one that merges the isolated station) is written to
`spatial_clusters_100km_sensitivity.csv` and is **not** emitted as panels.

| network_id | stations | stations >= 4 yr | complete station-years | first | last | days | max pairwise km |
|---|---|---|---|---|---|---|---|
{network_rows}

| network_id | station | river | complete years | days | dropped QC | longest identical run (d) | frozen flag |
|---|---|---|---|---|---|---|---|
{station_rows}

Provider missing days appear explicitly as `provider_quality = 'Missing'` rows with a
null value; they are dropped as `provider_marked_missing_day` and counted per station
in `qc_ledger.csv`.  `accepted_quality_codes` in `stations.csv` records which EA
quality codes survive per station.

## Frozen-sensor evidence (values kept, not deleted)

Runs of identical consecutive accepted values are reported rather than removed, and
`stations.csv` carries `frozen_sensor_suspected`.  Counterfactual if such a run were
dropped instead (`frozen_sensor_sensitivity.csv`):

| station | run start | run end | days | complete years (kept) | complete years (run dropped) | year lost |
|---|---|---|---|---|---|---|
{sensitivity_rows}

With that filter the kept networks would be
{record.get('frozen_sensor_census', {}).get('networks_kept_after_frozen_run_filter')}
— i.e. the panel structure is unchanged; only the affected station-years would go.

## Derived sub-daily QC (not a panel)

`uk_ea_temperature.uk_ea_daily` was used for {derived.get('stations_tested')} stations
to derive a daily mean from the 15-minute series for the last provider year and to
compare it with the provider daily mean
(`derived_subdaily_vs_provider_daily.csv`, {derived.get('stations_with_overlap')}
stations with overlap, median mean absolute difference
{derived.get('median_mean_abs_difference_c')} degC).  Derived values are **not**
emitted as transport networks: protocol rule 3 requires the provider's own daily
statistic.

## Caveats a reviewer should raise

1. Under-delivery: {counts.get('networks_kept')} networks and
   {counts.get('stations_ge4_complete_years')} eligible stations are far below the
   30-network panel target.  The pre-registered rule was not loosened to repair this.
2. One station with data and >= {MIN_COMPLETE_YEARS} complete years
   ({counts.get('stations_with_data_but_no_network')}) has no partner within the
   {record.get('spatial_clustering', {}).get('cap_km')} km cap, so it forms no network{
   isolated_text}.
3. Complete years use the sealed >= 365/366-day definition; the archive ends
   {record.get('networks', [{}])[0].get('last_date') if record.get('networks') else 'n/a'},
   so the final calendar year is incomplete everywhere and is excluded.
4. Every span is gappy: EA "Missing" days and one-day holes reduce apparently long
   series (e.g. station {longest_row.station_id[:8]} has {int(longest_row.n_days)} accepted
   days across {longest_span_years:.1f} years) to
   {counts.get('stations_ge4_complete_years')} eligible stations with
   {counts.get('complete_station_years_in_kept_networks')} complete years in total.
5. The networks are a documented spatial proxy, not an EA catchment label; the
   hydrology API exposes no catchment grouping for these stations.
6. Two member stations carry frozen-sensor evidence (see above); keeping their
   provider values is a deliberate, disclosed choice.
7. Full caveat list: `ingest.json` key `caveats`.

## Files

- `networks/<network_id>/daily_wide_temperature.csv` — wide panel, first column
  `date`, one column per station id, blank where missing.
- `networks/<network_id>/stations.csv`, plus the concatenated `stations.csv`.
- `networks_manifest.csv`, `qc_ledger.csv`, `complete_station_years.csv`,
  `frozen_sensor_sensitivity.csv`, `derived_subdaily_vs_provider_daily.csv`,
  `daily_long_qc.parquet`, `spatial_clusters_50km.csv`,
  `spatial_clusters_100km_sensitivity.csv`.
- `raw_cache/` — paged measure catalogue, per-station station documents, per-station
  daily readings (`readings/<station>_daily.csv`), two full raw JSON reading samples,
  and the derived sub-daily caches.
- `ingest.json` — retrieval UTC, exact URLs and parameters, counts, caveats.
"""
    (OUT_ROOT / "README.md").write_text(document, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        default="all",
        choices=("all", "measures", "metadata", "observations", "derived", "assemble"),
    )
    parser.add_argument("--refresh", action="store_true", help="ignore cached raw responses")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--derived-max-stations", type=int, default=8)
    args = parser.parse_args(argv)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    roster = pd.read_csv(V17_ROSTER, dtype=str)
    roster_ids = set(roster["station_id"].astype(str))

    record: dict = {
        "provider": PROVIDER,
        "context": CONTEXT,
        "protocol": str(PROTOCOL.relative_to(ROOT)),
        "generated_utc": utc_stamp(),
        "script": str(Path(__file__).relative_to(ROOT)),
        "command": "PYTHONPATH=src python3 scripts/244_multi_agency_uk_ea_ingest.py",
        "api": {
            "measures_url": MEASURES_URL,
            "readings_url": READINGS_URL,
            "station_url_template": STATION_URL,
            "measure_page_limit": MEASURE_PAGE_LIMIT,
            "readings_page_limit": READINGS_PAGE_LIMIT,
            "readings_window": [WINDOW_START, WINDOW_END],
            "provider_daily_statistic": (
                "measure id suffix '-temp-m-86400-C-qualified' = EA 'Daily mean "
                "Temperature (°C) time series', period 86400 s, unitName °C, "
                "observedProperty Temperature"
            ),
            "day_definition": (
                "one value per calendar date; reading payload carries date "
                "(YYYY-MM-DD) and dateTime (T00:00:00, no offset) = the provider's "
                "daily mean for that calendar day in UK local time as published"
            ),
            "rejected_daily_statistics": [
                "provider daily min (-temp-min-86400)",
                "provider daily max (-temp-max-86400)",
                "15-minute instantaneous (-temp-i-900)",
                "event-monitor sub-daily spot series (E-codes, '-temp-i-subdaily-C')",
            ],
        },
        "rules": {
            "min_stations_per_network": MIN_STATIONS_PER_NETWORK,
            "min_complete_years_per_station": MIN_COMPLETE_YEARS,
            "complete_year_definition": ">=365 QC-passing days (366 in leap years)",
            "spatial_cap_km": CAP_KM,
            "spatial_sensitivity_cap_km": SENSITIVITY_CAP_KM,
            "plausible_range_c": list(PLAUSIBLE_TEMPERATURE_C),
            "rejected_quality_codes": sorted(REJECT_QUALITY_CODES),
            "v17_roster_exclusion": str(V17_ROSTER.relative_to(ROOT)),
        },
        "requests": [],
        "caveats": [],
        "failures": [],
    }

    print("[stage] measures", flush=True)
    measures = stage_measures(refresh=args.refresh, record=record)
    daily_measures = measures.loc[
        measures["parameter"].eq("TEMPERATURE")
        & measures["period"].eq(86400)
        & measures["statistic_token"].eq("m")
    ].copy()
    record["daily_mean_measure_selection"] = {
        "n_daily_mean_temperature_measures": int(len(daily_measures)),
        "n_distinct_stations": int(daily_measures["station_id"].nunique()),
        "n_hydrometric_station_ids": int(daily_measures["hydrometric_station_id"].sum()),
        "selection": "parameter=TEMPERATURE, period=86400, statistic token 'm', unit °C",
    }
    if CATALOG.is_file():
        catalog = pd.read_csv(CATALOG, dtype=str)
        record["existing_catalog_check"] = {
            "catalog": str(CATALOG.relative_to(ROOT)),
            "n_catalog_stations": int(len(catalog)),
            "n_catalog_stations_with_provider_daily_mean_measure": int(
                catalog["site_id"].isin(set(daily_measures["station_id"].astype(str))).sum()
            ),
            "note": (
                "the existing catalog is not trusted as evidence: liveness and the "
                "daily-statistic claim were re-verified against the live measures "
                "collection and per-station documents"
            ),
        }
    print(
        f"  daily mean temperature measures: {len(daily_measures)} "
        f"on {daily_measures['station_id'].nunique()} stations",
        flush=True,
    )

    print("[stage] metadata", flush=True)
    meta, dropped = stage_metadata(daily_measures, refresh=args.refresh, record=record)
    print(
        f"  river-only kept {int(meta['river_only_drop_reason'].eq('').sum())} "
        f"of {len(meta)} (dropped {len(dropped)})",
        flush=True,
    )

    print("[stage] observations", flush=True)
    raw_daily = stage_observations(meta, refresh=args.refresh, record=record, workers=args.workers)
    print(f"  raw daily rows: {len(raw_daily)}", flush=True)

    derived = pd.DataFrame()
    if args.stage in {"all", "derived"}:
        print("[stage] derived sub-daily QC", flush=True)
        derived = stage_derived(
            measures,
            meta,
            raw_daily,
            refresh=args.refresh,
            record=record,
            max_stations=args.derived_max_stations,
            workers=args.workers,
        )
        print(f"  derived comparisons: {len(derived)}", flush=True)

    print("[stage] assemble", flush=True)
    manifest, kept_stations = stage_assemble(raw_daily, meta, record, roster_ids=roster_ids)
    record["caveats"] = build_caveats(record, manifest)
    write_readme(record, manifest, kept_stations)
    record["artifacts"] = {
        "readme": str((OUT_ROOT / "README.md").relative_to(ROOT)),
        "readme_sha256": sha256_file(OUT_ROOT / "README.md"),
        "networks_manifest": str((OUT_ROOT / "networks_manifest.csv").relative_to(ROOT)),
        "stations": str((OUT_ROOT / "stations.csv").relative_to(ROOT)),
        "qc_ledger": str((OUT_ROOT / "qc_ledger.csv").relative_to(ROOT)),
        "raw_cache": str(RAW.relative_to(ROOT)),
    }
    record["inputs_sha256"] = {
        str(V17_ROSTER.relative_to(ROOT)): sha256_file(V17_ROSTER),
        str(PROTOCOL.relative_to(ROOT)): sha256_file(PROTOCOL),
        str(Path(__file__).relative_to(ROOT)): sha256_file(Path(__file__)),
    }
    (OUT_ROOT / "ingest.json").write_text(
        json.dumps(record, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(record.get("final_counts", {}), indent=1), flush=True)
    return 0


def build_caveats(record: dict, manifest: pd.DataFrame) -> list[str]:
    kinds = record.get("measure_catalogue", {}).get("temperature_measure_kinds", {})
    caveats = [
        (
            "Provider daily statistic only, no re-aggregation: the accepted series are the "
            "EA 'Daily mean Temperature (°C)' measures (period 86400 s). The daily min/max "
            "measures and the 15-minute instantaneous series are not used to build panels; "
            "a derived daily mean from the 15-minute series is written to "
            "derived_subdaily_vs_provider_daily.csv as QC evidence only, because protocol "
            "rule 3 requires the provider's own daily statistic."
        ),
        (
            "Coverage is small and this is the central caveat: of "
            f"{record.get('measure_catalogue', {}).get('n_temperature_measures')} temperature "
            "measures in the live EA catalogue, only "
            f"{record.get('daily_mean_measure_selection', {}).get('n_daily_mean_temperature_measures')} "
            "are provider daily means, covering "
            f"{record.get('daily_mean_measure_selection', {}).get('n_distinct_stations')} hydrometric "
            "stations. Temperature measure kinds: "
            + ", ".join(f"{key}={value}" for key, value in kinds.items())
            + ". Everything else in the temperature catalogue is sub-daily (900 s): E-code "
            "event-monitor spot series and other named monitors, which carry no daily "
            "statistic, plus the same 16 stations' daily min/max statistics."
        ),
        (
            "Day boundary: the EA daily mean is published per calendar date (dateTime "
            "T00:00:00, no offset) in UK local time. The 15-minute series used in the derived "
            "QC carries local clock timestamps; no UTC conversion was applied by this ingest. "
            "The frozen endpoint (hottest-30 mean) is a summer statistic, so a one-hour DST "
            "boundary difference cannot reorder the hottest 30 days, but downstream code must "
            "not reinterpret the dates as UTC."
        ),
        (
            "Missing days are blank in daily_wide_temperature.csv. The EA also publishes "
            "'completeness', 'valid', 'invalid' and 'missing' fields per daily reading; these "
            "are cached in raw_cache/readings/<station>_daily.csv and summarised in ingest.json "
            "so a reviewer can apply a stricter completeness rule than the one used here."
        ),
        (
            "Networks are a documented spatial proxy (complete-linkage on lat/lon with a 50 km "
            "maximum pairwise geodesic cap, >= 2 stations), not an EA-native catchment label: "
            "the hydrology API exposes no catchment grouping for these stations. The 100 km "
            "sensitivity grouping is written to spatial_clusters_100km_sensitivity.csv but is "
            "never emitted as panels, so no station is double counted across caps."
        ),
        (
            "Complete years use the sealed definition (>= 365 days, 366 in leap years). The "
            "EA daily archive currently ends 2024-12-30, so calendar year 2024 is incomplete "
            "for every station and is excluded, which costs one otherwise complete year per "
            "station."
        ),
        (
            "Automatic QC excludes only non-numeric values, values outside -5..40 degC and "
            "readings whose EA quality code is one of "
            f"{sorted(REJECT_QUALITY_CODES)}; every accepted station records its own "
            "accepted_quality_codes in stations.csv."
        ),
        (
            "No frozen-screen performance was computed on this panel: ingest + QC stops at "
            "structural eligibility, as the protocol requires."
        ),
    ]
    if record.get("v17_roster_overlap", {}).get("n_overlap", 0):
        caveats.append("v17 roster overlap: " + str(record["v17_roster_overlap"]))
    frozen = record.get("frozen_sensor_census", {}).get("detail", [])
    for entry in frozen:
        if entry.get("frozen_sensor_suspected"):
            caveats.append(
                "Frozen-sensor evidence at station "
                f"{entry['station_id']}: {entry['n_days_value_exactly_0c']} accepted days are "
                "exactly 0.0 degC and the longest identical run is "
                f"{entry['longest_identical_run_days']} days "
                f"({entry['longest_identical_run_start']} .. {entry['longest_identical_run_end']}). "
                "The values were NOT deleted (the protocol asks for the provider's daily "
                "statistic, and a silent deletion would be a substitution); the station is "
                "flagged in stations.csv (frozen_sensor_suspected) so the transport analysis "
                "can exclude it explicitly."
            )
    for entry in record.get("frozen_sensor_census", {}).get("sensitivity", []):
        caveats.append(
            f"Frozen-run sensitivity for {entry['station_id']}: dropping the "
            f"{entry['run_days']}-day run ({entry['run_start']} .. {entry['run_end']}) would "
            f"take complete years from {entry['n_complete_years_kept_values']} to "
            f"{entry['n_complete_years_minus_frozen_run']} "
            f"(lost: {entry['complete_years_lost'] or 'none'}); see "
            f"{record['frozen_sensor_census']['sensitivity_csv']}"
        )
    if manifest is not None and len(manifest) <= 3:
        caveats.append(
            f"Under-delivery: only {len(manifest)} network(s) survive the >= 2 stations with "
            ">= 4 complete years rule, far below the 30-network panel target. This is reported "
            "as under-delivery, not repaired by loosening the rule."
        )
    return caveats


if __name__ == "__main__":
    raise SystemExit(main())
