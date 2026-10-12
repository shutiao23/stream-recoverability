#!/usr/bin/env python3
"""Multi-agency transport panel ingest, hedge providers (BE + ES).

Provider A -- ``waterinfo_be``: Flanders (Vlaamse waterbeheerders / VMM),
KiWIS (KISTERS WISKI) web service at
``https://download.waterinfo.be/tsmdownload/KiWIS/KiWIS``.  The provider
publishes a native **daily mean** water-temperature series
(``parametertype_name = WT``, ``ts_name = DagGem``, ``ts_unitname =
"degree Celsius"``), which is used as-is.  No sub-daily value is aggregated
into the panel; the 15-minute series is fetched only as day-boundary QC
evidence.

Provider B -- ``roea_es``: CEDEX *Anuario de Aforos* / ROEA probe.  The probe
records HTTP evidence for every candidate endpoint and writes
``INFEASIBLE.md`` when no provider daily river water-temperature product
exists.

Rules honoured (results/wrr_submission_ready/MULTI_AGENCY_TRANSPORT_PROTOCOL.md):
  * provider daily statistic only (rule 3), no re-aggregation into the panel;
  * river watercourses only by station-name evidence (rule 2); lakes,
    reservoirs, sea/estuary, docks, canals, WWTP and test monitors are dropped;
  * a network is a provider-native watercourse group with >= 2 stations having
    >= 4 complete calendar years (rule 4);
  * a *complete calendar year* is a year with >= 365 (366 in leap years)
    QC-passing daily values -- identical to the sealed definition in
    ``scripts/244_multi_agency_uk_ea_ingest.py``;
  * ingest + QC only.  **No frozen-screen performance is computed here.**

Usage
-----
    python3 scripts/260_multi_agency_be_es_ingest.py                # both providers
    python3 scripts/260_multi_agency_be_es_ingest.py --provider be
    python3 scripts/260_multi_agency_be_es_ingest.py --provider es
    python3 scripts/260_multi_agency_be_es_ingest.py --provider be --refresh
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INGEST_ROOT = ROOT / "results" / "wrr_submission_ready" / "multi_agency_ingest"
BE_ROOT = INGEST_ROOT / "waterinfo_be"
ES_ROOT = INGEST_ROOT / "roea_es"

KIWIS_BASE = "https://download.waterinfo.be/tsmdownload/KiWIS/KiWIS"
KIWIS_COMMON = {"service": "kisters", "type": "queryServices", "datasource": "0"}

PROVIDER_BE = "waterinfo_be"
PROVIDER_ES = "roea_es"

#: day range accepted for a river water-temperature daily mean (deg C)
VALUE_MIN_C = -5.0
VALUE_MAX_C = 45.0

MIN_COMPLETE_YEARS = 4
MIN_STATIONS_PER_NETWORK = 2

#: values are the provider daily mean for one calendar day; the KiWIS timestamp
#: is local clock time 01:00 with the Brussels UTC offset of that day.
EXPECTED_LOCAL_TIME = "01:00:00"

HTTP_TIMEOUT_S = 240
MAX_ATTEMPTS = 7
#: the provider help page states the service is protected against over-querying,
#: so requests are serialised with a pause and 429/503 answers back off
REQUEST_PAUSE_S = 1.0
RATE_LIMIT_SLEEP_S = 20.0
USER_AGENT = "stream-recoverability-multi-agency-ingest/1.0 (research; contact: repo owner)"

# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #


class CreditLimitExceeded(RuntimeError):
    """The provider's per-IP credit quota is exhausted (KiWIS AuthCreditLimit)."""


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def gzip_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb", compresslevel=6) as handle:
        handle.write(payload)


def gzip_read(path: Path) -> bytes:
    with gzip.open(path, "rb") as handle:
        return handle.read()


def http_bytes(
    url: str,
    *,
    accept: str = "application/json, text/csv, text/html;q=0.9, */*;q=0.8",
    timeout: int = HTTP_TIMEOUT_S,
    attempts: int | None = None,
) -> bytes:
    """GET ``url`` with retries.  Raises ``HTTPError`` for 4xx (kept by callers).

    A per-IP credit exhaustion (KiWIS answers 429 with ``AuthCreditLimit``) is
    raised as :class:`CreditLimitExceeded` so callers can stop a bulk loop
    instead of hammering the service.
    """

    last: Exception | None = None
    for attempt in range(1, (attempts or MAX_ATTEMPTS) + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
            time.sleep(REQUEST_PAUSE_S)
            return payload
        except urllib.error.HTTPError as error:
            last = error
            body = b""
            try:
                body = error.read()
            except Exception:  # pragma: no cover - defensive
                pass
            if error.code == 429 or b"AuthCreditLimit" in body or b"Credit limit exceeded" in body:
                raise CreditLimitExceeded(
                    f"HTTP {error.code} credit limit for {url}: {body[:200].decode('utf-8', errors='replace')}"
                ) from error
            if 400 <= error.code < 500 and error.code != 408:
                raise
            time.sleep(min(2.0**attempt, 30.0))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            last = error
            time.sleep(min(2.0**attempt, 30.0))
    raise RuntimeError(f"request failed after {attempts or MAX_ATTEMPTS} attempts: {url}") from last


def curl_fetch(url: str, *, accept: str, timeout: int) -> tuple[int, bytes]:
    """Fetch with the system curl (some provider TLS stacks fail under Python's OpenSSL).

    Returns (http_status, body).  Used only as a fallback and recorded as such.
    """

    command = [
        "curl", "-sS", "-L", "--max-time", str(timeout), "-A", USER_AGENT,
        "-H", f"Accept: {accept}", "-w", "\n%{http_code}", url,
    ]
    completed = subprocess.run(command, capture_output=True, timeout=timeout + 30, check=False)
    if completed.returncode != 0 and not completed.stdout:
        raise RuntimeError(f"curl failed ({completed.returncode}): {completed.stderr[:200].decode('utf-8', errors='replace')}")
    body, _, status_text = completed.stdout.rpartition(b"\n")
    try:
        status = int(status_text.strip())
    except ValueError:
        status = 0
        body = completed.stdout
    return status, body


def fetch_with_fallback(
    url: str,
    *,
    accept: str = "application/json, text/csv, text/html;q=0.9, */*;q=0.8",
    timeout: int = 120,
    attempts: int = 2,
) -> tuple[int, bytes, str]:
    """Fetch returning (status, body, transport); curl is used when urllib cannot."""

    try:
        return 200, http_bytes(url, accept=accept, timeout=timeout, attempts=attempts), "urllib"
    except urllib.error.HTTPError as error:
        body = b""
        try:
            body = error.read()
        except Exception:  # pragma: no cover - defensive
            pass
        return int(error.code), body, "urllib"
    except (urllib.error.URLError, TimeoutError, ConnectionError, RuntimeError):
        status, body = curl_fetch(url, accept=accept, timeout=timeout)
        return status, body, "curl"


def record_probe(
    url: str, *, accept: str = "*/*", timeout: int = 60, keep_body: bool = False
) -> dict[str, Any]:
    """GET ``url`` once and return an evidence record (never raises for HTTP status).

    ``keep_body=True`` stores the payload under the private ``_body`` key so the
    caller can parse it without a second request.
    """

    started = time.time()
    record: dict[str, Any] = {"url": url, "retrieved_utc": utc_stamp()}
    try:
        payload = http_bytes(url, accept=accept, timeout=timeout, attempts=1)
        record.update(
            status=200,
            bytes=len(payload),
            sha256=sha256_bytes(payload),
            content_type="(via urllib)",
            sample=payload[:400].decode("utf-8", errors="replace"),
            transport="urllib",
        )
    except urllib.error.HTTPError as error:
        body = b""
        try:
            body = error.read()
        except Exception:  # pragma: no cover - defensive
            pass
        record.update(
            status=int(error.code),
            bytes=len(body),
            sha256=sha256_bytes(body) if body else None,
            content_type=error.headers.get("Content-Type") if error.headers else None,
            sample=body[:400].decode("utf-8", errors="replace"),
            error=str(error),
        )
    except (urllib.error.URLError, TimeoutError, ConnectionError, RuntimeError) as error:
        # some provider TLS stacks (e.g. ceh.cedex.es) fail under Python's OpenSSL:
        # retry with the system curl so the probe still produces provider evidence
        try:
            status, body = curl_fetch(url, accept=accept, timeout=timeout)
            record.update(
                status=status,
                bytes=len(body),
                sha256=sha256_bytes(body),
                content_type="(via curl)",
                sample=body[:400].decode("utf-8", errors="replace"),
                transport="curl",
                urllib_error=f"{type(error).__name__}: {error}",
            )
        except Exception as curl_error:  # noqa: BLE001 - evidence over exceptions
            record.update(
                status=None,
                error=f"urllib: {type(error).__name__}: {error}; curl: {type(curl_error).__name__}: {curl_error}",
            )
    except Exception as error:  # noqa: BLE001 - evidence over exceptions
        record.update(status=None, error=f"{type(error).__name__}: {error}")
    record["elapsed_s"] = round(time.time() - started, 3)
    if keep_body:
        if record.get("transport") == "curl":
            _, body = curl_fetch(url, accept=accept, timeout=timeout)
            record["_body"] = body
        else:
            try:
                record["_body"] = http_bytes(url, accept=accept, timeout=timeout, attempts=1)
            except Exception:  # noqa: BLE001 - the sample already carries evidence
                record["_body"] = b""
    print(f"  probe {record.get('status')} {record.get('bytes')} {url}", flush=True)
    return record


def kiwis_url(request: str, **params: Any) -> str:
    query = {**KIWIS_COMMON, "request": request, "format": "json", **params}
    return KIWIS_BASE + "?" + urllib.parse.urlencode(query)


def parse_kiwis_table(payload: bytes) -> pd.DataFrame:
    """KiWIS table responses are ``[[header...], [row...], ...]``."""

    document = json.loads(payload)
    if not isinstance(document, list) or not document:
        raise ValueError(f"unexpected KiWIS payload: {payload[:200]!r}")
    if isinstance(document[0], str):
        raise ValueError(f"KiWIS returned a message instead of a table: {document}")
    header = [str(column) for column in document[0]]
    return pd.DataFrame(document[1:], columns=header)


def slugify(value: str, *, max_length: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug[:max_length] or "unnamed"


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


def longest_identical_run(values: pd.Series) -> tuple[int, str | None, str | None]:
    """Longest run of an identical non-null value (frozen-sensor evidence only)."""

    best = 0
    best_start = best_end = None
    start = 0
    array = values.to_numpy(dtype=object)
    for index in range(1, len(array) + 1):
        if index < len(array) and array[index] == array[start] and not pd.isna(array[index]):
            continue
        run = index - start
        if run > best and not pd.isna(array[start]):
            best = run
            best_start = str(values.index[start].date())
            best_end = str(values.index[index - 1].date())
        start = index
    return best, best_start, best_end


# --------------------------------------------------------------------------- #
# provider A: waterinfo_be
# --------------------------------------------------------------------------- #

#: watercourse-token patterns that are not a river channel (protocol rule 2).
#: Patterns are anchored where a bare substring would produce a false positive
#: (for example 'GroteStruisbeek' contains 'test', and 'KanaalPlassendale'
#: contains 'plas'); every pattern below was checked against the full
#: watercourse census written to raw_cache/watercourse_census.csv.
NON_RIVER_TOKEN_PATTERNS: tuple[tuple[str, str], ...] = (
    ("ends_dok", r"dok$|dok\d"),
    ("word_test", r"^test|test$"),
    ("ends_zwin", r"zwin$"),
    ("ends_vijver", r"vijver$"),
    ("contains_sluis", r"sluis"),
    ("ends_brug", r"brug$"),
    ("ends_pomp", r"pomp"),
    ("starts_spb", r"^spb"),
    ("starts_wetland", r"^wetland"),
    ("ends_serres", r"serres$"),
    ("ends_topsoil", r"topsoil$"),
    ("ends_veedijk", r"veedijk$"),
    ("ends_straat", r"straat$"),
    ("contains_blankaart", r"blankaart"),
    ("contains_zeedijk", r"zeedijk"),
    ("contains_rwzi_wwtp", r"rwzi|wwtp|influent|effluent|zuivering"),
    ("polder_code", r"^wo\d"),
    ("leading_digit", r"^\d"),
)

#: artificial, heavily regulated waterways (recorded, not used as river panel).
#: 'bvrdyk' is the catalogue's own abbreviation of 'Grote Beverdijkvaart'
#: ('LoReninge/DIEP Busbrug OPW/GrBvrdyk' vs 'Nieuwpoort/Grote Beverdijkvaart').
CANAL_TOKEN_PATTERNS: tuple[tuple[str, str], ...] = (
    ("kanaal", r"kanaal"),
    ("vaart", r"vaart"),
    ("gracht", r"gracht"),
    ("leiding", r"leiding"),
    ("kan_prefix", r"^kan"),
    ("grote_beverdijk_abbrev", r"bvrdyk"),
)

BE_MEASUREMENT_STATISTIC = (
    "provider daily mean, degrees C: KiWIS ts_name 'DagGem' (daggemiddelde) of "
    "parametertype WT, ts_unitname 'degree Celsius', ts_unitsymbol '\u00b0C'; "
    "one value per calendar day, KiWIS timestamp is local clock 01:00 with the "
    "Brussels UTC offset of that date"
)
BE_QUALITY_ASSURANCE = "provider_published_unqualified"
BE_QUALITY_NOTE = (
    "the KiWIS values payload carries no quality flag ('Timestamp,Value' only) and no "
    "provider statement that these series are checked/approved was found on "
    "https://www.waterinfo.vlaanderen.be/ (disclaimer read 2026-10-12); the umbrella "
    "disclaimer states the data are offered for informative, non-commercial use"
)

BE_DISCLAIMER_URL = "https://www.waterinfo.vlaanderen.be/default.aspx?path=NL/Algemene_Info/Disclaimer"


def watercourse_class(token: str) -> tuple[str, str]:
    """Classify a watercourse token -> (class, matched pattern name)."""

    if not token:
        return "excluded_no_watercourse_token", "no_slash_in_station_name"
    key = re.sub(r"[^a-z0-9]+", "", token.lower())
    for name, pattern in NON_RIVER_TOKEN_PATTERNS:
        if re.search(pattern, key):
            return "excluded_non_river", name
    for name, pattern in CANAL_TOKEN_PATTERNS:
        if re.search(pattern, key):
            return "canal", name
    return "river", ""


def be_stage_station_catalogue(refresh: bool, record: dict[str, Any], *, offline: bool = False) -> pd.DataFrame:
    raw = BE_ROOT / "raw_cache"
    raw.mkdir(parents=True, exist_ok=True)

    url = kiwis_url("getStationList", parametertype="noType")
    cache = raw / "station_list.json.gz"
    fresh = (refresh or not cache.exists()) and not offline
    payload = http_bytes(url) if fresh else gzip_read(cache)
    if fresh:
        gzip_write(cache, payload)
    record["station_list"] = {
        "url": url,
        "sha256": sha256_bytes(payload),
        "bytes": len(payload),
        "served_from_cache": not fresh,
    }
    stations = parse_kiwis_table(payload)
    stations = stations.rename(columns={"station_latitude": "latitude", "station_longitude": "longitude"})
    print(f"  station catalogue: {len(stations)} stations", flush=True)
    return stations


def be_stage_timeseries_catalogue(refresh: bool, record: dict[str, Any], *, offline: bool = False) -> pd.DataFrame:
    raw = BE_ROOT / "raw_cache"
    raw.mkdir(parents=True, exist_ok=True)

    all_wt_url = kiwis_url("getTimeseriesList", parametertype_name="WT")
    all_wt_cache = raw / "timeseries_list_WT.json.gz"
    fresh = (refresh or not all_wt_cache.exists()) and not offline
    all_wt_payload = http_bytes(all_wt_url) if fresh else gzip_read(all_wt_cache)
    if fresh:
        gzip_write(all_wt_cache, all_wt_payload)

    daily_url = kiwis_url("getTimeseriesList", station_name="*", ts_name="DagGem", parametertype_name="WT")
    daily_cache = raw / "timeseries_list_WT_DagGem.json.gz"
    fresh_daily = (refresh or not daily_cache.exists()) and not offline
    daily_payload = http_bytes(daily_url) if fresh_daily else gzip_read(daily_cache)
    if fresh_daily:
        gzip_write(daily_cache, daily_payload)

    all_wt = parse_kiwis_table(all_wt_payload)
    daily = parse_kiwis_table(daily_payload)
    record["timeseries_catalogue"] = {
        "all_WT": {"url": all_wt_url, "sha256": sha256_bytes(all_wt_payload), "bytes": len(all_wt_payload), "rows": int(len(all_wt))},
        "WT_DagGem": {"url": daily_url, "sha256": sha256_bytes(daily_payload), "bytes": len(daily_payload), "rows": int(len(daily))},
    }
    all_wt_daily = all_wt[all_wt["ts_name"] == "DagGem"]
    record["timeseries_catalogue"]["cross_check"] = {
        "all_WT_series": int(len(all_wt)),
        "all_WT_DagGem_series": int(len(all_wt_daily)),
        "filtered_DagGem_series": int(len(daily)),
        "identical_ts_id_sets": bool(set(all_wt_daily["ts_id"]) == set(daily["ts_id"])),
        "ts_name_census_all_WT": {str(k): int(v) for k, v in all_wt["ts_name"].value_counts().items()},
    }
    print(f"  timeseries catalogue: {len(all_wt)} WT series, {len(daily)} daily-mean series", flush=True)
    return daily


def be_stage_values(
    series: pd.DataFrame, refresh: bool, record: dict[str, Any], *, offline: bool = False
) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    """Fetch every daily-mean WT series (raw cache) and return long rows + per-series info.

    ``offline=True`` uses only the raw cache; uncached series are skipped and
    listed in ``record['download_failures']``.
    """

    cache_dir = BE_ROOT / "raw_cache" / "timeseries"
    cache_dir.mkdir(parents=True, exist_ok=True)
    end = (date.today() + timedelta(days=1)).isoformat()
    frames: list[pd.DataFrame] = []
    info: dict[str, dict[str, Any]] = {}
    total = len(series)
    credit_stop: str | None = None
    for position, row in enumerate(series.sort_values("ts_id").itertuples(index=False), start=1):
        ts_id = str(row.ts_id)
        url = kiwis_url("getTimeseriesValues", ts_id=ts_id, **{"from": "1990-01-01", "to": end}, metadata="true")
        cache = cache_dir / f"{ts_id}.json.gz"
        fresh = (refresh or not cache.exists()) and not offline
        if offline and not cache.exists():
            info[ts_id] = {
                "station_no": row.station_no,
                "error": "not in raw cache and --offline was requested",
                "url": url,
            }
            continue
        if fresh:
            try:
                payload = http_bytes(url)
            except CreditLimitExceeded as error:
                credit_stop = str(error)
                print(f"  CREDIT LIMIT reached at series {position}/{total}; stopping downloads", flush=True)
                info[ts_id] = {
                    "station_no": row.station_no,
                    "error": f"CreditLimitExceeded: {error}",
                    "url": url,
                }
                break
            except Exception as error:  # noqa: BLE001 - recorded as a failure
                info[ts_id] = {"station_no": row.station_no, "error": f"{type(error).__name__}: {error}", "url": url}
                print(f"  [{position}/{total}] FAILED {ts_id}: {error}", flush=True)
                continue
            gzip_write(cache, payload)
        else:
            payload = gzip_read(cache)
        document = json.loads(payload)
        entry = document[0] if isinstance(document, list) and document else {}
        data = entry.get("data") or []
        station_no = str(entry.get("station_no") or row.station_no)
        info[ts_id] = {
            "station_no": station_no,
            "station_name": entry.get("station_name"),
            "parametertype_name": entry.get("parametertype_name"),
            "ts_name": entry.get("ts_name"),
            "ts_unitname": entry.get("ts_unitname"),
            "ts_unitsymbol": entry.get("ts_unitsymbol"),
            "latitude": entry.get("station_latitude"),
            "longitude": entry.get("station_longitude"),
            "rows": int(entry.get("rows") or len(data)),
            "url": url,
            "raw_sha256": sha256_bytes(payload),
            "raw_bytes": len(payload),
            "served_from_cache": not fresh,
        }
        if not data:
            continue
        frame = pd.DataFrame(data, columns=["timestamp", "value"])
        frame.insert(0, "ts_id", ts_id)
        frame.insert(1, "station_no", station_no)
        frames.append(frame)
        if position % 50 == 0:
            print(f"  [{position}/{total}] series fetched", flush=True)
    long = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["ts_id", "station_no", "timestamp", "value"])
    record["value_requests"] = {
        "template": kiwis_url("getTimeseriesValues", ts_id="<ts_id>", **{"from": "1990-01-01", "to": end}, metadata="true"),
        "end_date_used": end,
        "series_requested": int(total),
        "series_returned_rows": int(len(long)),
        "series_failed": int(sum(1 for value in info.values() if "error" in value)),
    }
    failures = [
        {
            "ts_id": ts_id,
            "station_no": meta.get("station_no"),
            "url": meta.get("url"),
            "error": meta.get("error"),
        }
        for ts_id, meta in sorted(info.items())
        if "error" in meta
    ]
    if failures:
        pd.DataFrame(failures).to_csv(BE_ROOT / "download_failures.csv", index=False)
    record["download_failures"] = failures
    record["download_stopped_by_credit_limit"] = credit_stop
    record["series_served_from_cache"] = int(
        sum(1 for value in info.values() if value.get("served_from_cache") and "error" not in value)
    )
    return long, info


def be_build_long_qc(long: pd.DataFrame, record: dict[str, Any]) -> pd.DataFrame:
    if long.empty:
        return long.assign(date=[], value_num=[])
    frame = long.copy()
    frame["date"] = frame["timestamp"].astype(str).str.slice(0, 10)
    frame["local_time"] = frame["timestamp"].astype(str).str.slice(11, 19)
    frame["utc_offset"] = frame["timestamp"].astype(str).str.slice(19)
    frame["value_num"] = pd.to_numeric(frame["value"], errors="coerce")

    record["timestamp_shape"] = {
        "n_rows": int(len(frame)),
        "local_time_census": {str(k): int(v) for k, v in frame["local_time"].value_counts().items()},
        "utc_offset_census": {str(k): int(v) for k, v in frame["utc_offset"].value_counts().items()},
        "expected_local_time": EXPECTED_LOCAL_TIME,
        "n_rows_unexpected_local_time": int((frame["local_time"] != EXPECTED_LOCAL_TIME).sum()),
    }

    n_null = int(frame["value_num"].isna().sum())
    dropped = frame[frame["value_num"].notna()].copy()

    duplicate_mask = dropped.duplicated(subset=["station_no", "date"], keep="last")
    n_duplicates = int(duplicate_mask.sum())
    duplicate_conflicts = 0
    if n_duplicates:
        grouped = dropped.groupby(["station_no", "date"])["value_num"].nunique()
        duplicate_conflicts = int((grouped > 1).sum())
    dropped = dropped[~duplicate_mask]

    out_of_range = (dropped["value_num"] < VALUE_MIN_C) | (dropped["value_num"] > VALUE_MAX_C)
    n_out_of_range = int(out_of_range.sum())
    kept = dropped[~out_of_range].copy()

    kept["n_dropped_qc"] = 0
    record["qc"] = {
        "rule": (
            f"value present; duplicate (station_no, calendar date) rows dropped keeping the last "
            f"API row; value within [{VALUE_MIN_C}, {VALUE_MAX_C}] degC"
        ),
        "rows_retrieved": int(len(frame)),
        "dropped_null_value": n_null,
        "dropped_duplicate_date": n_duplicates,
        "duplicate_date_value_conflicts": duplicate_conflicts,
        "dropped_out_of_range": n_out_of_range,
        "range_degc": [VALUE_MIN_C, VALUE_MAX_C],
        "rows_kept": int(len(kept)),
    }
    return kept


def be_build_stations(
    long: pd.DataFrame,
    long_qc: pd.DataFrame,
    info: dict[str, dict[str, Any]],
    stations: pd.DataFrame,
    record: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    """One row per provider station; series index is a DatetimeIndex of dates."""

    master = stations.rename(columns={"station_no": "station_no"}).copy()
    master["latitude"] = pd.to_numeric(master["latitude"], errors="coerce")
    master["longitude"] = pd.to_numeric(master["longitude"], errors="coerce")
    coordinates = master.set_index("station_no")[["latitude", "longitude"]]
    raw_rows_by_station = long.groupby("station_no").size().to_dict() if not long.empty else {}

    rows: list[dict[str, Any]] = []
    series_by_station: dict[str, pd.Series] = {}
    dropped_by_station: dict[str, int] = {}

    for station_no, block in long_qc.groupby("station_no"):
        series = (
            block.assign(day=pd.to_datetime(block["date"]))
            .set_index("day")["value_num"]
            .sort_index()
        )
        series_by_station[str(station_no)] = series
        dropped_by_station[str(station_no)] = int(raw_rows_by_station.get(station_no, 0) - len(block))
        years = complete_years_from_series(series)
        ts_ids = sorted(set(block["ts_id"]))
        first_info = info.get(ts_ids[0], {})
        run_length, run_start, run_end = longest_identical_run(series)
        lat = coordinates["latitude"].get(station_no, np.nan)
        lon = coordinates["longitude"].get(station_no, np.nan)
        if (isinstance(lat, float) and math.isnan(lat)) and first_info.get("latitude") not in (None, ""):
            lat = float(first_info["latitude"])
            lon = float(first_info["longitude"])
        station_name = str(first_info.get("station_name") or "")
        token = station_name.split("/")[-1].strip() if "/" in station_name else ""
        klass, rule = watercourse_class(token)
        rows.append(
            {
                "station_id": str(station_no),
                "station_name": station_name,
                "kiwis_ts_ids": ";".join(ts_ids),
                "kiwis_station_id": str(master.loc[master["station_no"] == station_no, "station_id"].iloc[0])
                if (master["station_no"] == station_no).any()
                else "",
                "river_name": token,
                "watercourse_key": re.sub(r"[^a-z0-9]+", "", token.lower()),
                "watercourse_class": klass,
                "watercourse_class_rule": rule,
                "latitude": float(lat) if lat is not None and not (isinstance(lat, float) and math.isnan(lat)) else None,
                "longitude": float(lon) if lon is not None and not (isinstance(lon, float) and math.isnan(lon)) else None,
                "n_complete_years": len(years),
                "complete_years": ";".join(str(year) for year in years),
                "first_date": series.index.min().date().isoformat(),
                "last_date": series.index.max().date().isoformat(),
                "n_days": int(len(series)),
                "n_dropped_qc": int(dropped_by_station[str(station_no)]),
                "longest_identical_run_days": int(run_length),
                "longest_identical_run_start": run_start,
                "longest_identical_run_end": run_end,
                "values_min_degc": float(series.min()) if len(series) else None,
                "values_max_degc": float(series.max()) if len(series) else None,
                "value_exactly_0c_days": int((series == 0).sum()),
                "raw_sha256": ";".join(info.get(ts, {}).get("raw_sha256", "") for ts in ts_ids),
                "raw_bytes": int(sum(info.get(ts, {}).get("raw_bytes", 0) for ts in ts_ids)),
            }
        )

    return pd.DataFrame(rows), series_by_station


def be_day_boundary_qc(refresh: bool, record: dict[str, Any], long_qc: pd.DataFrame) -> pd.DataFrame:
    """Compare the provider daily mean against the provider 15-minute series.

    Evidence only: the panel uses the provider daily statistic unchanged.  The
    comparison fixes the calendar-day convention of the KiWIS ``DagGem`` stamp.
    """

    raw = BE_ROOT / "raw_cache"
    subdaily_list = record.get("subdaily_series", [])
    if not subdaily_list:
        return pd.DataFrame()

    cache_dir = raw / "subdaily_qc"
    cache_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    daily_by_station = {
        station: block.set_index(pd.to_datetime(block["date"]))["value_num"].sort_index()
        for station, block in long_qc.groupby("station_no")
    }
    for item in subdaily_list:
        ts_id, station_no = item["ts_id"], item["station_no"]
        url = kiwis_url(
            "getTimeseriesValues", ts_id=ts_id, **{"from": "2023-06-01", "to": "2023-08-31"}, metadata="true"
        )
        cache = cache_dir / f"{ts_id}_2023summer.json.gz"
        fresh = refresh or not cache.exists()
        if fresh:
            try:
                payload = http_bytes(url)
            except Exception as error:  # noqa: BLE001
                item["error"] = f"{type(error).__name__}: {error}"
                continue
            gzip_write(cache, payload)
        else:
            payload = gzip_read(cache)
        entry = json.loads(payload)[0]
        data = entry.get("data") or []
        item.update(
            url=url,
            rows=int(entry.get("rows") or len(data)),
            ts_unitname=entry.get("ts_unitname"),
            raw_sha256=sha256_bytes(payload),
        )
        if not data:
            continue
        frame = pd.DataFrame(data, columns=["timestamp", "value"])
        frame["date"] = frame["timestamp"].astype(str).str.slice(0, 10)
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
        per_day = frame.dropna(subset=["value"]).groupby("date")["value"].agg(["count", "mean"])
        daily = daily_by_station.get(station_no)
        if daily is None:
            continue
        same = pd.DataFrame({"subdaily_mean_same_day": per_day["mean"], "n_subdaily": per_day["count"]})
        same.index = pd.to_datetime(same.index)
        same["provider_daily_same_day"] = daily.reindex(same.index)
        previous = daily.copy()
        previous.index = previous.index + pd.Timedelta(days=1)
        same["provider_daily_previous_day"] = previous.reindex(same.index)
        both_same = same.dropna(subset=["provider_daily_same_day"])
        both_prev = same.dropna(subset=["provider_daily_previous_day"])
        rows.append(
            {
                "station_no": station_no,
                "subdaily_ts_id": ts_id,
                "window": "2023-06-01..2023-08-31",
                "n_days_with_subdaily": int(len(same)),
                "n_subdaily_per_day_min": int(same["n_subdaily"].min()),
                "n_subdaily_per_day_median": float(same["n_subdaily"].median()),
                "n_subdaily_per_day_max": int(same["n_subdaily"].max()),
                "n_days_matched_same_day": int(len(both_same)),
                "median_abs_diff_same_day_degc": float((both_same["subdaily_mean_same_day"] - both_same["provider_daily_same_day"]).abs().median())
                if len(both_same)
                else None,
                "n_days_matched_previous_day": int(len(both_prev)),
                "median_abs_diff_previous_day_degc": float((both_prev["subdaily_mean_same_day"] - both_prev["provider_daily_previous_day"]).abs().median())
                if len(both_prev)
                else None,
            }
        )
    qc = pd.DataFrame(rows)
    if not qc.empty:
        qc.to_csv(raw / "day_boundary_qc.csv", index=False)
    return qc


def be_write_networks(
    stations: pd.DataFrame, series_by_station: dict[str, pd.Series], record: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    networks_dir = BE_ROOT / "networks"
    networks_dir.mkdir(parents=True, exist_ok=True)

    eligible = stations[
        (stations["n_complete_years"] >= MIN_COMPLETE_YEARS) & (stations["watercourse_class"] == "river")
    ].copy()

    manifest_rows: list[dict[str, Any]] = []
    emitted: set[str] = set()
    for key, group in eligible.groupby("watercourse_key"):
        if len(group) < MIN_STATIONS_PER_NETWORK:
            continue
        network_id = f"waterinfo_be_{slugify(key)}"
        suffix = 1
        while network_id in emitted:
            suffix += 1
            network_id = f"waterinfo_be_{slugify(key)}_{suffix}"
        emitted.add(network_id)
        river_name = str(group["river_name"].mode().iloc[0])
        members = sorted(group["station_id"].astype(str))
        wide = pd.DataFrame({station: series_by_station[station] for station in members}).sort_index()
        wide = wide.reindex(pd.date_range(wide.index.min(), wide.index.max(), freq="D"))
        wide.index.name = "date"
        wide = wide.reset_index()
        wide["date"] = wide["date"].dt.date.astype(str)
        target = networks_dir / network_id
        target.mkdir(parents=True, exist_ok=True)
        wide.to_csv(target / "daily_wide_temperature.csv", index=False)
        manifest_rows.append(
            {
                "network_id": network_id,
                "river_name": river_name,
                "provider": PROVIDER_BE,
                "n_stations": int(len(members)),
                "station_ids": ";".join(members),
                "n_complete_years_total": int(group["n_complete_years"].sum()),
                "first_date": str(wide["date"].min()),
                "last_date": str(wide["date"].max()),
                "n_days": int(len(wide)),
            }
        )

    manifest = pd.DataFrame(manifest_rows).sort_values("network_id") if manifest_rows else pd.DataFrame()
    if not manifest.empty:
        manifest.to_csv(BE_ROOT / "networks_manifest.csv", index=False)

    # ineligible census: every watercourse group that did not reach the floor
    census_rows: list[dict[str, Any]] = []
    for key, group in stations.groupby("watercourse_key"):
        n_eligible = int(
            ((group["n_complete_years"] >= MIN_COMPLETE_YEARS) & (group["watercourse_class"] == "river")).sum()
        )
        census_rows.append(
            {
                "watercourse_key": key,
                "river_name": str(group["river_name"].mode().iloc[0]) if len(group) else "",
                "watercourse_class": ";".join(sorted(set(group["watercourse_class"]))),
                "n_stations": int(len(group)),
                "n_stations_ge4_complete_years_river": n_eligible,
                "emitted_network": bool(len(group) >= MIN_STATIONS_PER_NETWORK and n_eligible >= MIN_STATIONS_PER_NETWORK),
                "station_ids": ";".join(sorted(group["station_id"].astype(str))),
                "max_complete_years": int(group["n_complete_years"].max()),
            }
        )
    census = pd.DataFrame(census_rows).sort_values(["n_stations", "max_complete_years"], ascending=False)
    census.to_csv(BE_ROOT / "networks_not_eligible.csv", index=False)

    token_census = (
        stations.groupby(["watercourse_key", "watercourse_class", "watercourse_class_rule", "river_name"])
        .agg(
            n_stations=("station_id", "size"),
            max_complete_years=("n_complete_years", "max"),
            n_stations_ge4=("n_complete_years", lambda values: int((values >= MIN_COMPLETE_YEARS).sum())),
        )
        .reset_index()
        .sort_values(["watercourse_class", "n_stations"], ascending=[True, False])
    )
    token_census.to_csv(BE_ROOT / "raw_cache" / "watercourse_census.csv", index=False)

    summary = {
        "stations_with_daily_mean_WT": int(len(stations)),
        "stations_ge4_complete_years": int((stations["n_complete_years"] >= MIN_COMPLETE_YEARS).sum()),
        "stations_ge4_complete_years_river_class": int(len(eligible)),
        "watercourse_groups": int(stations["watercourse_key"].nunique()),
        "networks_emitted": int(len(manifest)),
        "stations_in_emitted_networks": int(manifest["n_stations"].sum()) if not manifest.empty else 0,
        "complete_station_years_in_emitted_networks": int(manifest["n_complete_years_total"].sum()) if not manifest.empty else 0,
        "watercourse_class_census": {str(k): int(v) for k, v in stations["watercourse_class"].value_counts().items()},
    }
    record["networks"] = summary
    return manifest, census, summary


def run_be(refresh: bool, *, offline: bool = False) -> dict[str, Any]:
    print("== provider A: waterinfo_be (KiWIS)", flush=True)
    record: dict[str, Any] = {
        "provider": PROVIDER_BE,
        "context": "Flanders (Belgium): Vlaamse waterbeheerders / VMM, waterinfo.be KiWIS web service",
        "generated_utc": utc_stamp(),
        "script": "scripts/260_multi_agency_be_es_ingest.py",
        "command": "python3 scripts/260_multi_agency_be_es_ingest.py --provider be",
        "api": {
            "base": KIWIS_BASE,
            "common_params": KIWIS_COMMON,
            "requests_used": ["getStationList", "getTimeseriesList", "getTimeseriesValues"],
        },
        "licence": {
            "disclaimer_url": BE_DISCLAIMER_URL,
            "statement_nl_verbatim": (
                "De toegang tot de informatie op deze website is kosteloos, doch houdt de aanvaarding in "
                "door de gebruiker van de hierna volgende voorwaarden. De gegevens van deze website zijn "
                "bedoeld voor informatieve en niet-commerci\u00eble doeleinden en worden aangeboden door de "
                "Vlaamse waterbeheerders en kennisinstituten."
            ),
            "interpretation": "informative and non-commercial use; academic research use recorded, redistribution not asserted",
            "help_url": "https://www.waterinfo.vlaanderen.be/default.aspx?path=NL/Algemene_Info/Help_algemeen",
        },
        "measurement_statistic": BE_MEASUREMENT_STATISTIC,
        "quality_assurance": BE_QUALITY_ASSURANCE,
        "quality_assurance_note": BE_QUALITY_NOTE,
    }

    stations = be_stage_station_catalogue(refresh, record, offline=offline)
    series = be_stage_timeseries_catalogue(refresh, record, offline=offline)

    # one cheap probe records the per-IP credit state at run time (script-generated
    # evidence for the AuthCreditLimit condition that interrupted the first bulk run)
    quota_probe_id = str(series.sort_values("ts_id").iloc[0]["ts_id"]) if len(series) else ""
    record["quota_probe"] = record_probe(
        kiwis_url("getTimeseriesValues", ts_id=quota_probe_id, **{"from": "2024-01-01", "to": "2024-01-02"}),
        timeout=60,
        keep_body=False,
    )
    long, info = be_stage_values(series, refresh, record, offline=offline)
    long_qc = be_build_long_qc(long, record)
    stations_table, series_by_station = be_build_stations(long, long_qc, info, stations, record)

    # unusable series (no rows at all) still deserve a row in the census
    known = set(stations_table["station_id"].astype(str))
    empty_rows = []
    for ts_id, meta in info.items():
        station_no = str(meta.get("station_no") or "")
        if station_no in known or "error" in meta:
            continue
        station_name = str(meta.get("station_name") or "")
        token = station_name.split("/")[-1].strip() if "/" in station_name else ""
        klass, rule = watercourse_class(token)
        empty_rows.append(
            {
                "station_id": station_no,
                "station_name": station_name,
                "kiwis_ts_ids": ts_id,
                "kiwis_station_id": "",
                "river_name": token,
                "watercourse_key": re.sub(r"[^a-z0-9]+", "", token.lower()),
                "watercourse_class": klass,
                "watercourse_class_rule": rule,
                "latitude": None,
                "longitude": None,
                "n_complete_years": 0,
                "complete_years": "",
                "first_date": None,
                "last_date": None,
                "n_days": 0,
                "n_dropped_qc": 0,
                "longest_identical_run_days": 0,
                "longest_identical_run_start": None,
                "longest_identical_run_end": None,
                "values_min_degc": None,
                "values_max_degc": None,
                "value_exactly_0c_days": 0,
                "raw_sha256": meta.get("raw_sha256", ""),
                "raw_bytes": int(meta.get("raw_bytes", 0)),
            }
        )
    all_stations = pd.concat([stations_table, pd.DataFrame(empty_rows)], ignore_index=True) if empty_rows else stations_table
    record["stations_without_values"] = int(len(empty_rows))
    record["stations_without_coordinates"] = int(all_stations["latitude"].isna().sum())

    # sub-daily series available for the day-boundary QC (same station, ts_name P.15)
    subdaily_url = kiwis_url("getTimeseriesList", station_name="*", ts_name="P.15", parametertype_name="WT")
    subdaily_cache = BE_ROOT / "raw_cache" / "timeseries_list_WT_P15.json.gz"
    fresh = refresh or not subdaily_cache.exists()
    try:
        subdaily_payload = http_bytes(subdaily_url) if fresh else gzip_read(subdaily_cache)
        if fresh:
            gzip_write(subdaily_cache, subdaily_payload)
        subdaily = parse_kiwis_table(subdaily_payload)
    except Exception as error:  # noqa: BLE001
        record["subdaily_catalogue_error"] = f"{type(error).__name__}: {error}"
        subdaily = pd.DataFrame(columns=["station_no", "ts_id", "ts_name"])
    subdaily = subdaily[subdaily["station_no"].astype(str).isin(set(all_stations["station_id"].astype(str)))]
    subdaily = subdaily.sort_values("station_no")
    record["subdaily_series"] = [
        {"ts_id": str(row.ts_id), "station_no": str(row.station_no)} for row in subdaily.head(3).itertuples(index=False)
    ]
    boundary = be_day_boundary_qc(refresh, record, long_qc)
    record["day_boundary_qc"] = boundary.to_dict(orient="records") if not boundary.empty else []

    manifest, census, summary = be_write_networks(all_stations, series_by_station, record)

    kept_ids = set(manifest["station_ids"].str.split(";").explode()) if not manifest.empty else set()
    panel = all_stations[all_stations["station_id"].astype(str).isin(kept_ids)].copy() if kept_ids else all_stations.iloc[0:0].copy()
    station_to_network: dict[str, str] = {}
    if not manifest.empty:
        for row in manifest.itertuples(index=False):
            for station in str(row.station_ids).split(";"):
                station_to_network[station] = str(row.network_id)
    panel["network_id"] = panel["station_id"].astype(str).map(station_to_network)
    panel["provider"] = PROVIDER_BE
    panel["accepted_quality_codes"] = "(none published in the KiWIS values payload)"
    panel["measurement_statistic"] = BE_MEASUREMENT_STATISTIC
    panel["quality_assurance"] = BE_QUALITY_ASSURANCE

    station_columns = [
        "network_id",
        "station_id",
        "provider",
        "river_name",
        "latitude",
        "longitude",
        "n_complete_years",
        "complete_years",
        "first_date",
        "last_date",
        "n_days",
        "n_dropped_qc",
        "accepted_quality_codes",
        "measurement_statistic",
        "quality_assurance",
    ]
    extra_columns = [
        "station_name",
        "watercourse_key",
        "watercourse_class",
        "watercourse_class_rule",
        "kiwis_station_id",
        "kiwis_ts_ids",
        "longest_identical_run_days",
        "longest_identical_run_start",
        "longest_identical_run_end",
        "values_min_degc",
        "values_max_degc",
        "value_exactly_0c_days",
        "raw_sha256",
        "raw_bytes",
    ]
    panel = panel[station_columns + extra_columns].sort_values(["network_id", "station_id"])
    panel.to_csv(BE_ROOT / "stations.csv", index=False)
    all_stations.sort_values("station_id").to_csv(BE_ROOT / "stations_all.csv", index=False)

    long_qc_out = long_qc[["station_no", "ts_id", "date", "value_num"]].rename(
        columns={"station_no": "station_id", "value_num": "temperature_degc"}
    )
    long_qc_out.sort_values(["station_id", "date"]).to_csv(BE_ROOT / "daily_long_qc.csv.gz", index=False, compression="gzip")

    record["final_counts"] = {
        "stations_in_panel": int(len(panel)),
        "networks": int(len(manifest)),
        "complete_station_years_in_panel": int(panel["n_complete_years"].sum()),
        "days_in_panel": int(panel["n_days"].sum()),
    }
    # ---- under-delivery evidence (script-generated, so no number is hand-copied)
    tranche = all_stations[all_stations["n_days"] > 0]
    try:
        year_counts = (
            long_qc.assign(year=pd.to_datetime(long_qc["date"]).dt.year)
            .groupby(["station_no", "year"])
            .size()
            .rename("values")
            .reset_index()
        )
        year_counts["days_in_year"] = year_counts["year"].map(
            lambda year: 366 if ((year % 4 == 0 and year % 100 != 0) or year % 400 == 0) else 365
        )
        year_counts["shortfall_days"] = year_counts["days_in_year"] - year_counts["values"]
        record["complete_year_gap_evidence"] = {
            "note": (
                "the sealed complete-calendar-year definition needs >= 365 (366) QC-passing values, "
                "i.e. a gap-free year; these are the shortfalls of the retrieved tranche"
            ),
            "station_years": int(len(year_counts)),
            "gap_free_station_years": int((year_counts["shortfall_days"] <= 0).sum()),
            "gap_free_share": float((year_counts["shortfall_days"] <= 0).mean()),
            "shortfall_days_median": float(year_counts["shortfall_days"].median()),
            "shortfall_days_p90": float(year_counts["shortfall_days"].quantile(0.9)),
            "shortfall_days_max": int(year_counts["shortfall_days"].max()),
            "min_shortfall_days_per_station_median": float(
                year_counts.groupby("station_no")["shortfall_days"].min().median()
            ),
        }
    except Exception as error:  # noqa: BLE001
        record["complete_year_gap_evidence"] = {"error": f"{type(error).__name__}: {error}"}

    cached_series = int(sum(1 for value in info.values() if value.get("served_from_cache") and "error" not in value))
    record["retrieval_status"] = {
        "catalogued_daily_mean_WT_series": int(len(series)),
        "series_in_raw_cache": cached_series,
        "series_not_retrieved": int(len(series) - cached_series),
        "stopped_by_credit_limit": record.get("download_stopped_by_credit_limit"),
        "quota_probe_status": (record.get("quota_probe") or {}).get("status"),
        "quota_probe_sample": ((record.get("quota_probe") or {}).get("sample") or "")[:180],
        "run_mode": "offline (raw cache only)" if offline else "download",
        "resume_command": "python3 scripts/260_multi_agency_be_es_ingest.py --provider be",
        "note": (
            "the KiWIS service applies a per-IP credit quota; when it is exhausted every request "
            "answers HTTP 429 with an ExceptionReport exceptionCode='AuthCreditLimit'. The ingest "
            "stops there, keeps the raw cache, and resumes from it on the next run "
            "(no --refresh), so nothing is downloaded twice."
        ),
    }
    record["under_delivery"] = {
        "stations_retrieved": int(len(tranche)),
        "stations_ge4_complete_years_in_tranche": int((tranche["n_complete_years"] >= MIN_COMPLETE_YEARS).sum()),
        "max_complete_years_in_tranche": int(tranche["n_complete_years"].max()) if len(tranche) else 0,
        "networks_emitted": int(len(manifest)),
        "verdict": (
            "UNDER-DELIVERY in the retrieved tranche: no station of the retrieved Flemish daily-mean "
            "series reaches the frozen >= 4 complete calendar years, so the provider contributes no "
            "network yet. This is a reported failure, not a silent drop."
            if len(manifest) == 0
            else "networks emitted from the retrieved tranche"
        ),
        "extrapolation_warning": (
            "only the retrieved tranche is evidence; the unretrieved series were blocked by the "
            "provider credit quota and must be fetched before any provider-level claim is made"
        ),
    }
    probe_path = ROOT / "scratch" / "be_manual_probe_complete_years.csv"
    if probe_path.exists():
        probe = pd.read_csv(probe_path)
        record["under_delivery"]["manual_probe_series"] = {
            "file": "scratch/be_manual_probe_complete_years.csv",
            "script": "scratch/be_manual_probe_complete_years.py",
            "note": (
                "three further long daily-mean series (2010-2025/2026) fetched by hand before the credit "
                "limit was reached, judged with the same complete-calendar-year rule"
            ),
            "n_series": int(len(probe)),
            "n_series_ge4_complete_years": int((probe["n_complete_years"] >= MIN_COMPLETE_YEARS).sum()),
            "max_complete_years": int(probe["n_complete_years"].max()),
        }

    record["artifacts"] = {
        "stations_csv": "results/wrr_submission_ready/multi_agency_ingest/waterinfo_be/stations.csv",
        "stations_all_csv": "results/wrr_submission_ready/multi_agency_ingest/waterinfo_be/stations_all.csv",
        "networks_dir": "results/wrr_submission_ready/multi_agency_ingest/waterinfo_be/networks/<network_id>/daily_wide_temperature.csv",
        "networks_manifest": "results/wrr_submission_ready/multi_agency_ingest/waterinfo_be/networks_manifest.csv",
        "networks_not_eligible": "results/wrr_submission_ready/multi_agency_ingest/waterinfo_be/networks_not_eligible.csv",
        "daily_long_qc": "results/wrr_submission_ready/multi_agency_ingest/waterinfo_be/daily_long_qc.csv.gz",
        "raw_cache": "results/wrr_submission_ready/multi_agency_ingest/waterinfo_be/raw_cache/",
    }
    record["caveats"] = [
        "Provider daily statistic only: the accepted series are the KiWIS WT 'DagGem' (daily mean) series. No sub-daily value is aggregated into the panel; the 15-minute series is read for day-boundary QC evidence only.",
        "The KiWIS daily stamp is local clock 01:00 with the Brussels UTC offset of that date; day-identity is taken from the stamp's calendar date. The day-boundary QC block ('day_boundary_qc' and raw_cache/day_boundary_qc.csv) compares the provider daily mean with the mean of the provider 15-minute series for the same and the previous calendar day, so the convention is checked rather than assumed.",
        "Quality assurance is 'provider_published_unqualified': the API payload carries no quality flag and no provider statement that these series are checked/approved was found; the site disclaimer (URL recorded) offers the data for informative, non-commercial use.",
        "Network identity is provider name evidence: KiWIS station_name has the form '<municipality>/<watercourse>', and the network key is the watercourse token lowercased with non-alphanumerics removed (so 'Grote Nete' == 'GroteNete'). Networks are watercourse groups, not catchments.",
        "Waterbody filter is name based: tokens matching dock/harbour/sluice/tidal-inlet/pond/reservoir/dike/WWTP/test/street/soil are classed excluded_non_river and canal/vaart/gracht/leiding tokens are classed 'canal'; neither class enters a river network. networks_not_eligible.csv lists every group with its class so the filter is auditable.",
        "Some catalogue entries are process monitors of the water utilities (WWTP influent/effluent, CSO, spaarbekken, docks) that share the same KiWIS surface as the river network; they are dropped by the class filter, and those without a '<municipality>/<watercourse>' name are classed excluded_no_watercourse_token.",
        "Complete calendar year == >= 365 (366 leap) QC-passing daily values, the sealed definition used for the UK EA and SMHI providers; because the provider statistic is one value per day this requires a gap-free year.",
        "No frozen-screen endpoint, retention, model or score is computed by this script (ingest and QC only).",
    ]
    BE_ROOT.mkdir(parents=True, exist_ok=True)
    (BE_ROOT / "ingest.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_be_readme(record)
    print(f"  BE networks={summary['networks_emitted']} stations={summary['stations_in_emitted_networks']}", flush=True)
    return record


def write_be_readme(record: dict[str, Any]) -> None:
    status = record.get("retrieval_status", {})
    under = record.get("under_delivery", {})
    counts = record.get("final_counts", {})
    lines = [
        "# waterinfo.be (Flanders, Belgium) -- multi-agency transport ingest",
        "",
        "Provider: Vlaamse waterbeheerders / Vlaamse Milieumaatschappij (VMM) via the waterinfo.be",
        "KiWIS (KISTERS WISKI) web service.",
        "",
        "## Statistic used",
        "",
        f"- {record.get('measurement_statistic')}",
        "- the provider's own daily statistic is used as published; no sub-daily value is aggregated",
        "  into the panel",
        f"- quality assurance: `{record.get('quality_assurance')}` -- {record.get('quality_assurance_note')}",
        f"- licence/terms: {record.get('licence', {}).get('disclaimer_url')}",
        "",
        "## Retrieval status (read this before using the panel)",
        "",
        f"- catalogued daily-mean water-temperature series: {status.get('catalogued_daily_mean_WT_series')}",
        f"- series in the raw cache (used here): {status.get('series_in_raw_cache')}",
        f"- series not retrieved: {status.get('series_not_retrieved')}",
        f"- stopped by the provider credit limit: `{status.get('stopped_by_credit_limit')}`",
        f"- resume with: `{status.get('resume_command')}`",
        "",
        "The KiWIS service answers HTTP 429 with `exceptionCode='AuthCreditLimit'` once the per-IP",
        "credit quota is exhausted. The ingest stops at that point, keeps the raw cache and resumes",
        "from it on the next run, so nothing is downloaded twice.",
        "",
        "## Panel yield",
        "",
        f"- stations retrieved: {under.get('stations_retrieved')}",
        f"- stations with >= 4 complete calendar years: {under.get('stations_ge4_complete_years_in_tranche')}",
        f"- maximum complete calendar years seen: {under.get('max_complete_years_in_tranche')}",
        f"- networks emitted: {counts.get('networks')}",
        "",
        f"**{under.get('verdict')}**",
        "",
        f"{under.get('extrapolation_warning')}",
        "",
        "The frozen complete-calendar-year definition needs >= 365 (366) QC-passing values, i.e. a",
        "gap-free year. The retrieved Flemish daily means have scattered single missing days, which is",
        "why so few years qualify; `ingest.json` carries the shortfall distribution under",
        "`complete_year_gap_evidence`.",
        "",
        "## Files",
        "",
        "- `stations.csv` -- panel rows (may be header-only when no network reaches the floor)",
        "- `stations_all.csv` -- every retrieved station with class, rule and completeness columns",
        "- `networks_manifest.csv`, `networks/<network_id>/daily_wide_temperature.csv`",
        "- `networks_not_eligible.csv` -- per-watercourse census including the reason nothing was emitted",
        "- `daily_long_qc.csv.gz` -- QC-passing long table",
        "- `raw_cache/` -- station list, series catalogue, per-series raw JSON (gzip), watercourse census",
        "- `download_failures.csv` -- series that failed or were cut off by the credit limit",
        "",
        "## Reproduction",
        "",
        "```bash",
        "python3 scripts/260_multi_agency_be_es_ingest.py --provider be",
        "# re-process a partial ingest without downloading:",
        "python3 scripts/260_multi_agency_be_es_ingest.py --provider be --offline",
        "```",
        "",
    ]
    (BE_ROOT / "README.md").write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
# provider B: roea_es (CEDEX Anuario de Aforos / ROEA) -- feasibility probe
# --------------------------------------------------------------------------- #

ES_CANDIDATE_ENDPOINTS = [
    "http://ceh-flumen64.cedex.es/anuarioaforos/",
    "https://ceh.cedex.es/anuarioaforos/default.asp",
    "https://ceh.cedex.es/anuarioaforos/afo/estaf-codigo.asp",
    "https://ceh.cedex.es/anuarioaforos/Repositorio_Anuarios.asp",
    "https://ceh.cedex.es/anuarioaforos/api/estaciones",
    "https://ceh.cedex.es/anuarioaforos/api/datos",
    "https://ceh.cedex.es/anuarioaforos/datos/temperatura",
    "https://ceh.cedex.es/roea/",
    "https://ceh.cedex.es/roea/api/estaciones",
]

#: the Spanish series actually ingested: SAIH Ebro (Confederacion Hidrografica
#: del Ebro), the only national/regional operator reachable in the time-box that
#: publishes a provider *daily* water-temperature statistic in degC.
SAIH_API = "https://www.saihebro.com/api/datos-historicos"
SAIH_DATOS_URL = "https://www.saihebro.com/datos/historicos"
SAIH_PROVISIONALITY_URL = "https://www.saihebro.com/info/datos-provisionales-ebro"
SAIH_LEGAL_URL = "https://www.chebro.es/web/guest/aviso-legal"
SAIH_PROVIDER = "saih_ebro"
SAIH_MEASUREMENT_STATISTIC = (
    "provider daily mean, degrees C: consolidated daily CSV column 'MEDIA (oC)' for "
    "'FECHA_GRUPO' (calendar day); the same file also carries 'MINIMO (oC)' / "
    "'MAXIMO (oC)' with their intra-day timestamps"
)
SAIH_QUALITY_ASSURANCE = "provider_published_unqualified"
SAIH_QUALITY_NOTE = (
    "the ingested series come from the 'diario' (consolidated daily) endpoint of the provider's "
    "'Datos historicos' API, not from the real-time feed, but no fetched page states that these "
    "consolidated values are checked/approved. The provider's own notice "
    f"({SAIH_PROVISIONALITY_URL}) says real-time data are 'de naturaleza provisional hasta que sean "
    "revisados, depurados y validados por el Servicio de Hidrologia'; the human-facing "
    f"'Datos historicos' page ({SAIH_DATOS_URL}) asks for a (free) user account, while the API "
    "endpoint answered without credentials at retrieval time."
)
#: how the river/waterbody name is parsed out of the station label
SAIH_STATION_LABEL_RE = re.compile(r"^(?P<code>\S+)\s*-\s*(?P<label>.+)$")
SAIH_RIVER_RE = re.compile(r"^r[ií]o\s+(?P<river>.+?)\s+en\s+", re.I)



def _es_file_links(html: str) -> list[str]:
    links = set()
    for match in re.finditer(r'href="([^"]+)"', html, flags=re.I):
        href = match.group(1).replace("\\", "/").strip()
        if href.lower().endswith((".csv", ".rar", ".zip", ".txt", ".xlsx", ".pdf")):
            links.add(href)
    return sorted(links)


def run_es_probe(refresh: bool) -> dict[str, Any]:
    print("== provider B: roea_es (CEDEX Anuario de Aforos) feasibility probe", flush=True)
    ES_ROOT.mkdir(parents=True, exist_ok=True)
    (ES_ROOT / "raw_cache").mkdir(parents=True, exist_ok=True)
    evidence: dict[str, Any] = {
        "provider": PROVIDER_ES,
        "context": "Spain, CEDEX Anuario de Aforos / Red Oficial de Estaciones de Aforo (ROEA)",
        "generated_utc": utc_stamp(),
        "script": "scripts/260_multi_agency_be_es_ingest.py",
        "command": "python3 scripts/260_multi_agency_be_es_ingest.py --provider es",
        "endpoint_probes": [],
        "demarcacion_pages": [],
        "file_census_by_demarcacion": {},
        "station_catalogue_probe": None,
    }

    for url in ES_CANDIDATE_ENDPOINTS:
        evidence["endpoint_probes"].append(record_probe(url, timeout=90))

    file_names: dict[str, int] = {}
    demarcaciones_url = "https://ceh.cedex.es/anuarioaforos/demarcaciones.asp"
    status, demarcaciones_body, transport = fetch_with_fallback(
        demarcaciones_url, accept="text/html", timeout=90, attempts=1
    )
    evidence["demarcaciones_root"] = {
        "url": demarcaciones_url, "status": status, "bytes": len(demarcaciones_body), "transport": transport
    }
    if status != 200:
        raise RuntimeError(f"cannot read the Anuario demarcaciones index: HTTP {status} ({demarcaciones_url})")
    demarcaciones_html = demarcaciones_body.decode("utf-8", errors="replace")
    if "\ufffd" in demarcaciones_html:
        demarcaciones_html = demarcaciones_body.decode("cp1252", errors="replace")
    (ES_ROOT / "raw_cache" / "demarcaciones.asp.html").write_text(demarcaciones_html, encoding="utf-8")
    demarcacion_links = sorted(
        {
            href
            for href in re.findall(r'href="([^"]+)"', demarcaciones_html, flags=re.I)
            if href.lower().endswith(".asp")
        }
    )
    evidence["demarcacion_links"] = demarcacion_links
    for link in demarcacion_links:
        url = urllib.parse.quote(urllib.parse.urljoin(demarcaciones_url, link), safe=":/?&=%")
        page = record_probe(url, accept="text/html", timeout=90, keep_body=True)
        page["demarcacion_page"] = link
        body = page.pop("_body", b"")
        evidence["demarcacion_pages"].append(page)
        if page.get("status") != 200:
            continue
        html = body.decode("utf-8", errors="replace")
        if "\ufffd" in html:
            html = body.decode("cp1252", errors="replace")
        name = slugify(Path(link).stem)
        (ES_ROOT / "raw_cache" / f"listing_{name}.html").write_text(html, encoding="utf-8")
        links = _es_file_links(html)
        evidence["file_census_by_demarcacion"][link] = links
        for data_link in links:
            file_name = data_link.split("/")[-1]
            file_names[file_name] = file_names.get(file_name, 0) + 1

    evidence["file_name_census"] = dict(sorted(file_names.items()))
    evidence["file_name_census_note"] = (
        "distinct published data-file names across the demarcacion download pages of the "
        "current Anuario de Aforos edition; the census is the evidence for which variable "
        "families the Anuario publishes"
    )

    station_url = "https://ceh-flumen64.cedex.es/anuarioaforos/anuario-2021-2022/EBRO/estaf.csv"
    discharge_url = "https://ceh-flumen64.cedex.es/anuarioaforos/anuario-2021-2022/EBRO/afliq.csv"
    station_path = ES_ROOT / "raw_cache" / "anuario_2021_2022_EBRO_estaf.csv"
    record = record_probe(station_url, timeout=180)
    try:
        if record.get("status") == 200:
            if refresh or not station_path.exists():
                status, body, transport = fetch_with_fallback(station_url, timeout=180, attempts=1)
                record["transport"] = transport
                record["status"] = status
                station_path.write_bytes(body)
            header = station_path.read_text(encoding="latin-1", errors="replace").splitlines()[0]
            record["header"] = header
            record["columns"] = header.split(";")
            record["has_temperature_column"] = any("temp" in column.lower() for column in record["columns"])
            record["cached_path"] = str(station_path.relative_to(ROOT))
    except Exception as error:  # noqa: BLE001
        record["parse_error"] = f"{type(error).__name__}: {error}"
    evidence["station_catalogue_probe"] = record

    evidence["discharge_file_header_probe"] = es_head_probe(discharge_url, "anuario-2021-2022/EBRO/afliq.csv")

    temperature_files = [
        name for name in file_names if any(token in name.lower() for token in ("temp", "term", "calid"))
    ]
    evidence["temperature_like_files"] = temperature_files
    evidence["verdict"] = "infeasible" if not temperature_files else "needs_review"

    (ES_ROOT / "raw_cache" / "evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    write_es_infeasible(evidence)

    spain = run_es_saih(refresh)
    write_es_readme(evidence, spain)
    return spain


def es_head_probe(url: str, label: str, *, n_bytes: int = 600) -> dict[str, Any]:
    """Read only the first bytes of a large provider file (header evidence)."""

    record: dict[str, Any] = {"url": url, "label": label, "retrieved_utc": utc_stamp()}
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Range": f"bytes=0-{n_bytes - 1}"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            head = response.read(n_bytes)
            record.update(status=int(response.status), content_type=response.headers.get("Content-Type"), transport="urllib")
    except Exception as error:  # noqa: BLE001 - fall back to curl's byte range
        record["urllib_error"] = f"{type(error).__name__}: {error}"
        command = [
            "curl", "-sS", "-L", "--max-time", "90", "-A", USER_AGENT, "-r", f"0-{n_bytes - 1}",
            "-w", "\n%{http_code}", url,
        ]
        completed = subprocess.run(command, capture_output=True, timeout=120, check=False)
        body, _, status_text = completed.stdout.rpartition(b"\n")
        try:
            record.update(status=int(status_text.strip()), transport="curl", content_type=None)
        except ValueError:
            record.update(status=None, transport="curl")
            body = completed.stdout
        head = body
    first_line = head.decode("utf-8", errors="replace").splitlines()[0] if head else ""
    record["first_line"] = first_line
    record["n_bytes_read"] = len(head)
    print(f"  head-probe {record.get('status')} {url} -> {str(record.get('first_line'))[:80]}", flush=True)
    return record


# --------------------------------------------------------------------------- #
# provider B (continued): SAIH Ebro daily water temperature
# --------------------------------------------------------------------------- #


def saih_get(path: str, **params: Any) -> bytes:
    url = f"{SAIH_API}/{path}?" + urllib.parse.urlencode(params)
    return http_bytes(url, accept="application/json, application/zip, */*")


def saih_json(path: str, **params: Any) -> tuple[Any, str]:
    url = f"{SAIH_API}/{path}?" + urllib.parse.urlencode(params)
    return json.loads(http_bytes(url, accept="application/json")), url


def saih_csv_zip(payload: bytes) -> tuple[str, str]:
    """Return (csv text, entry name) from the provider's zip-of-one-csv download."""

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        text = archive.read(names[0]).decode("utf-8-sig", errors="replace")
    return text, names[0]


def run_es_saih(refresh: bool) -> dict[str, Any]:
    print("== provider B2: saih_ebro (Spain) daily water temperature", flush=True)
    raw = ES_ROOT / "raw_cache"
    (raw / "daily").mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "provider": SAIH_PROVIDER,
        "country": "Spain",
        "context": "Confederacion Hidrografica del Ebro (CHE) -- SAIH Ebro automatic hydrologic information system",
        "generated_utc": utc_stamp(),
        "script": "scripts/260_multi_agency_be_es_ingest.py",
        "command": "python3 scripts/260_multi_agency_be_es_ingest.py --provider es",
        "api": {"base": SAIH_API, "requests_used": [
            "getTiposSenal", "getEstaciones", "getSenales", "getPeriodo", "obtenerDatosHistoricos",
        ]},
        "catalogue": {},
        "series": [],
        "licence": {
            "legal_notice_url": SAIH_LEGAL_URL,
            "statement_verbatim": (
                "Aviso legal de la Confederacion Hidrografica del Ebro. The notice cites the Ley 37/2007 "
                "sobre reutilizacion de la informacion del sector publico and its Reglamento (RD 1495/2011) "
                "for the reuse of the information published on the portal."
            ),
            "access_note": (
                f"the human-facing download page {SAIH_DATOS_URL} ('Datos historicos') asks for a free user "
                "account; the underlying api/datos-historicos endpoints answered HTTP 200 without credentials "
                "at retrieval time, and that is what this ingest used"
            ),
        },
        "measurement_statistic": SAIH_MEASUREMENT_STATISTIC,
        "quality_assurance": SAIH_QUALITY_ASSURANCE,
        "quality_assurance_note": SAIH_QUALITY_NOTE,
    }

    # ---- catalogue: which consolidated signal types exist, and which stations carry water temperature
    tipos_payload, tipos_url = saih_json("getTiposSenal", tipoConsolidado="diario")
    (raw / "catalogue_getTiposSenal_diario.json").write_bytes(json.dumps(tipos_payload, ensure_ascii=False, indent=1).encode())
    record["catalogue"]["signal_types_url"] = tipos_url
    record["catalogue"]["signal_types"] = {item["id"]: item["text"] for item in tipos_payload}
    record["catalogue"]["water_temperature_signal_present"] = any(
        item["id"] == "TEMPA" for item in tipos_payload
    )

    stations_payload, stations_url = saih_json("getEstaciones", tipoConsolidado="diario", tiposSenal="TEMPA")
    (raw / "catalogue_getEstaciones_diario_TEMPA.json").write_bytes(
        json.dumps(stations_payload, ensure_ascii=False, indent=1).encode()
    )
    record["catalogue"]["stations_url"] = stations_url
    record["catalogue"]["stations_with_daily_water_temperature"] = stations_payload

    entries: list[dict[str, Any]] = []
    for item in stations_payload:
        match = SAIH_STATION_LABEL_RE.match(str(item.get("text", "")))
        code = match.group("code") if match else str(item.get("id"))
        label = match.group("label").strip() if match else str(item.get("text", ""))
        river_match = SAIH_RIVER_RE.match(label)
        kind = "river" if river_match else ("reservoir" if label.lower().startswith("embalse") else "other")
        entries.append(
            {
                "station_id": code,
                "station_label": label,
                "tree_id": item.get("id"),
                "watercourse_class": kind,
                "river_name": river_match.group("river").strip() if river_match else "",
            }
        )
    record["catalogue"]["station_classification"] = entries

    # ---- per station: signal id, available period, full daily download
    period_end = date.today().strftime("%d/%m/%Y")
    frames: list[pd.DataFrame] = []
    for entry in entries:
        if entry["watercourse_class"] != "river":
            entry["skipped"] = "not a river station (protocol rule 2)"
            continue
        signals, signals_url = saih_json(
            "getSenales", tipoConsolidado="diario", tiposSenal="TEMPA", estaciones=entry["station_id"]
        )
        entry["signals_url"] = signals_url
        entry["signals"] = signals
        if not signals:
            entry["skipped"] = "no daily signal"
            continue
        signal_id = str(signals[0]["id"])
        entry["signal_id"] = signal_id
        entry["signal_text"] = signals[0].get("text")
        period, period_url = saih_json("getPeriodo", tipoConsolidado="diario", senales=signal_id)
        entry["period_url"] = period_url
        entry["period"] = period
        download_url = (
            f"{SAIH_API}/obtenerDatosHistoricos?"
            + urllib.parse.urlencode(
                {
                    "tipoConsolidado": "diario",
                    "senalesSeleccionadas": signal_id,
                    "fechaIni": "01/01/2000 00:00",
                    "fechaFin": f"{period_end} 00:00",
                    "formato": "csv",
                }
            )
        )
        cache = raw / "daily" / f"{entry['station_id']}_{signal_id}_diario.zip"
        fresh = refresh or not cache.exists()
        try:
            payload = http_bytes(download_url, accept="application/zip") if fresh else cache.read_bytes()
        except Exception as error:  # noqa: BLE001
            entry["download_error"] = f"{type(error).__name__}: {error}"
            continue
        if fresh:
            cache.write_bytes(payload)
        entry["download_url"] = download_url
        entry["raw_zip"] = str(cache.relative_to(ROOT))
        entry["raw_sha256"] = sha256_bytes(payload)
        entry["raw_bytes"] = len(payload)
        entry["served_from_cache"] = not fresh
        text, entry_name = saih_csv_zip(payload)
        entry["csv_entry"] = entry_name
        parsed = pd.read_csv(io.StringIO(text), sep=";", dtype=str)
        entry["csv_columns"] = list(parsed.columns)
        frame = pd.DataFrame(
            {
                "station_id": entry["station_id"],
                "river_name": entry["river_name"],
                "date": pd.to_datetime(parsed["FECHA_GRUPO"], format="%d/%m/%Y", errors="coerce"),
                "daily_mean_degc": pd.to_numeric(parsed["MEDIA (oC)"], errors="coerce"),
                "daily_min_degc": pd.to_numeric(parsed["MINIMO (oC)"], errors="coerce"),
                "daily_max_degc": pd.to_numeric(parsed["MAXIMO (oC)"], errors="coerce"),
                "min_timestamp": parsed.get("FECHA_MINIMO"),
                "max_timestamp": parsed.get("FECHA_MAXIMO"),
            }
        )
        entry["csv_rows"] = int(len(frame))
        frames.append(frame)
        print(f"  {entry['station_id']} {entry['river_name']}: {len(frame)} daily rows", flush=True)

    long = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if long.empty:
        record["verdict"] = "infeasible"
        (ES_ROOT / "ingest.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return record

    # ---- QC (same rule as the Belgian provider)
    n_blank = int(long["daily_mean_degc"].isna().sum())
    kept = long[long["daily_mean_degc"].notna() & long["date"].notna()].copy()
    duplicate_mask = kept.duplicated(subset=["station_id", "date"], keep="last")
    n_duplicates = int(duplicate_mask.sum())
    kept = kept[~duplicate_mask]
    out_of_range = (kept["daily_mean_degc"] < VALUE_MIN_C) | (kept["daily_mean_degc"] > VALUE_MAX_C)
    n_out_of_range = int(out_of_range.sum())
    kept = kept[~out_of_range].copy()
    kept["day_identity_ok"] = kept.apply(
        lambda row: bool(
            isinstance(row["min_timestamp"], str)
            and isinstance(row["max_timestamp"], str)
            and row["min_timestamp"][:10] == row["date"].strftime("%d/%m/%Y")
            and row["max_timestamp"][:10] == row["date"].strftime("%d/%m/%Y")
        ),
        axis=1,
    )
    record["qc"] = {
        "rule": (
            f"daily mean present; duplicate (station, calendar day) rows dropped keeping the last "
            f"downloaded row; value within [{VALUE_MIN_C}, {VALUE_MAX_C}] degC"
        ),
        "rows_downloaded": int(len(long)),
        "dropped_blank_daily_mean": n_blank,
        "dropped_duplicate_date": n_duplicates,
        "dropped_out_of_range": n_out_of_range,
        "rows_kept": int(len(kept)),
        "min_max_within_day_share": float(kept["day_identity_ok"].mean()) if len(kept) else None,
    }

    # ---- per-station table and complete years
    rows: list[dict[str, Any]] = []
    series_by_station: dict[str, pd.Series] = {}
    for station_id, block in kept.groupby("station_id"):
        series = block.set_index("date")["daily_mean_degc"].sort_index()
        series_by_station[str(station_id)] = series
        years = complete_years_from_series(series)
        entry = next(item for item in entries if item["station_id"] == station_id)
        run_length, run_start, run_end = longest_identical_run(series)
        rows.append(
            {
                "station_id": str(station_id),
                "station_label": entry["station_label"],
                "provider": SAIH_PROVIDER,
                "river_name": entry["river_name"],
                "watercourse_key": re.sub(r"[^a-z0-9]+", "", entry["river_name"].lower()),
                "watercourse_class": "river",
                "latitude": None,
                "longitude": None,
                "n_complete_years": len(years),
                "complete_years": ";".join(str(year) for year in years),
                "first_date": series.index.min().date().isoformat(),
                "last_date": series.index.max().date().isoformat(),
                "n_days": int(len(series)),
                "n_dropped_qc": int(len(long[long["station_id"] == station_id]) - len(series)),
                "accepted_quality_codes": "(none published; consolidated daily archive)",
                "measurement_statistic": SAIH_MEASUREMENT_STATISTIC,
                "quality_assurance": SAIH_QUALITY_ASSURANCE,
                "signal_id": entry.get("signal_id"),
                "available_period": json.dumps(entry.get("period")),
                "longest_identical_run_days": int(run_length),
                "longest_identical_run_start": run_start,
                "longest_identical_run_end": run_end,
                "values_min_degc": float(series.min()),
                "values_max_degc": float(series.max()),
                "value_exactly_0c_days": int((series == 0).sum()),
                "raw_sha256": entry.get("raw_sha256", ""),
                "raw_bytes": int(entry.get("raw_bytes", 0)),
            }
        )
    stations_all = pd.DataFrame(rows).sort_values("station_id")

    # ---- networks: agency-native grouping == river watercourse (protocol rule 4)
    networks_dir = ES_ROOT / "networks"
    networks_dir.mkdir(parents=True, exist_ok=True)
    eligible = stations_all[stations_all["n_complete_years"] >= MIN_COMPLETE_YEARS]
    manifest: list[dict[str, Any]] = []
    for key, group in eligible.groupby("watercourse_key"):
        if len(group) < MIN_STATIONS_PER_NETWORK:
            continue
        network_id = f"{SAIH_PROVIDER}_{slugify(key)}"
        members = sorted(group["station_id"].astype(str))
        wide = pd.DataFrame({station: series_by_station[station] for station in members}).sort_index()
        wide = wide.reindex(pd.date_range(wide.index.min(), wide.index.max(), freq="D"))
        wide.index.name = "date"
        wide = wide.reset_index()
        wide["date"] = wide["date"].dt.date.astype(str)
        target = networks_dir / network_id
        target.mkdir(parents=True, exist_ok=True)
        wide.to_csv(target / "daily_wide_temperature.csv", index=False)
        manifest.append(
            {
                "network_id": network_id,
                "grouping_rule": "provider river watercourse name parsed from the station label ('Rio <name> en <place>')",
                "provider": SAIH_PROVIDER,
                "river_name": str(group["river_name"].iloc[0]),
                "n_stations": int(len(members)),
                "station_ids": ";".join(members),
                "n_complete_years_total": int(group["n_complete_years"].sum()),
                "first_date": str(wide["date"].min()),
                "last_date": str(wide["date"].max()),
                "n_days": int(len(wide)),
                "caveat": (
                    "SAIH Ebro watercourse labels are river names, but the CHE basin is a single agency-native "
                    "unit; A027 (Ebro at Tortosa) is at the tidal limit of the Ebro"
                    if key == "ebro"
                    else ""
                ),
            }
        )

    # basin-level fallback grouping, flagged, so the coordinator can decide
    basin_eligible = eligible[eligible["station_id"].isin(["A017", "A027", "A263"])]
    if len(basin_eligible) >= MIN_STATIONS_PER_NETWORK:
        network_id = f"{SAIH_PROVIDER}_ebro_basin"
        members = sorted(basin_eligible["station_id"].astype(str))
        wide = pd.DataFrame({station: series_by_station[station] for station in members}).sort_index()
        wide = wide.reindex(pd.date_range(wide.index.min(), wide.index.max(), freq="D"))
        wide.index.name = "date"
        wide = wide.reset_index()
        wide["date"] = wide["date"].dt.date.astype(str)
        target = networks_dir / network_id
        target.mkdir(parents=True, exist_ok=True)
        wide.to_csv(target / "daily_wide_temperature.csv", index=False)
        manifest.append(
            {
                "network_id": network_id,
                "grouping_rule": (
                    "AGENCY BASIN grouping (whole SAIH Ebro basin), NOT a single river watercourse: the "
                    "provider is a basin authority and its stations are spread over different rivers"
                ),
                "provider": SAIH_PROVIDER,
                "river_name": "Ebro basin (mixed: Rio Ebro, Rio Cinca)",
                "n_stations": int(len(members)),
                "station_ids": ";".join(members),
                "n_complete_years_total": int(basin_eligible["n_complete_years"].sum()),
                "first_date": str(wide["date"].min()),
                "last_date": str(wide["date"].max()),
                "n_days": int(len(wide)),
                "caveat": (
                    "stations lie on different rivers (Ebro at Tortosa, Cinca at Fraga) hundreds of km apart; "
                    "emitted only as a flagged fallback for the coordinator, not as a river network"
                ),
            }
        )

    manifest_frame = pd.DataFrame(manifest).sort_values("network_id") if manifest else pd.DataFrame()
    if not manifest_frame.empty:
        manifest_frame.to_csv(ES_ROOT / "networks_manifest.csv", index=False)

    stations_all.to_csv(ES_ROOT / "stations_all.csv", index=False)
    kept_ids = set(manifest_frame["station_ids"].str.split(";").explode()) if not manifest_frame.empty else set()
    panel = stations_all[stations_all["station_id"].isin(kept_ids)].copy()
    station_to_network = {}
    if not manifest_frame.empty:
        for row in manifest_frame.itertuples(index=False):
            for station in str(row.station_ids).split(";"):
                station_to_network.setdefault(station, []).append(str(row.network_id))
    panel["network_id"] = panel["station_id"].map(lambda value: ";".join(station_to_network.get(value, [])))
    station_columns = [
        "network_id", "station_id", "provider", "river_name", "latitude", "longitude",
        "n_complete_years", "complete_years", "first_date", "last_date", "n_days", "n_dropped_qc",
        "accepted_quality_codes", "measurement_statistic", "quality_assurance",
    ]
    extra_columns = [
        "station_label", "watercourse_key", "watercourse_class", "signal_id", "available_period",
        "longest_identical_run_days", "longest_identical_run_start", "longest_identical_run_end",
        "values_min_degc", "values_max_degc", "value_exactly_0c_days", "raw_sha256", "raw_bytes",
    ]
    panel = panel[station_columns + extra_columns].sort_values(["network_id", "station_id"])
    panel.to_csv(ES_ROOT / "stations.csv", index=False)
    kept.sort_values(["station_id", "date"]).to_csv(ES_ROOT / "daily_long_qc.csv.gz", index=False, compression="gzip")

    record["series"] = entries
    record["stations_in_panel"] = int(len(panel))
    record["networks"] = manifest
    record["final_counts"] = {
        "river_stations_with_daily_water_temperature": int(len(stations_all)),
        "river_stations_ge4_complete_years": int(len(eligible)),
        "networks_emitted": int(len(manifest_frame)),
        "complete_station_years_in_panel": int(panel["n_complete_years"].sum()) if len(panel) else 0,
    }
    record["caveats"] = [
        "Only three SAIH Ebro river stations publish a consolidated daily water-temperature signal (A017 Rio Cinca en Fraga, A027 Rio Ebro en Tortosa, A263 Rio Ebro en Gelsa); a fourth TEMPA station is a reservoir (E104 Embalse de Nagore) and is dropped by protocol rule 2.",
        "Complete-year floor bites: A263 (Ebro at Gelsa) has only 3 complete calendar years, so the river-watercourse network 'Ebro' does not reach >= 2 stations x >= 4 complete years. The only grouping that does is the flagged basin-level fallback 'saih_ebro_ebro_basin' (A017 + A027), whose stations are on different rivers hundreds of km apart.",
        "A027 'Rio Ebro en Tortosa' sits at the tidal limit of the Ebro; if the coordinator reads protocol rule 2 strictly (no estuary-influenced sites) the Spanish panel becomes empty.",
        "The provider publishes no coordinates in these API responses, so latitude/longitude are blank; station identity is the CHE station code and the river name comes from the station label ('Rio <name> en <place>').",
        "The daily file also carries 'MINIMO (oC)' and 'MAXIMO (oC)' with intra-day timestamps; the ingest QC records the share of days whose min/max timestamps fall inside the stamped calendar day (evidence that the daily stamp is the calendar day).",
        SAIH_QUALITY_NOTE,
        "No frozen-screen endpoint, retention, model or score is computed by this script (ingest and QC only).",
    ]
    (ES_ROOT / "ingest.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"  ES stations={record['final_counts']['river_stations_ge4_complete_years']} "
        f"networks={record['final_counts']['networks_emitted']}",
        flush=True,
    )
    return record


def write_es_readme(cedex: dict[str, Any], spain: dict[str, Any]) -> None:
    lines = [
        "# Spain (`roea_es`) -- what is in this directory and why",
        "",
        "Two different things live here; do not conflate them.",
        "",
        "1. **CEDEX / ROEA *Anuario de Aforos* -> infeasible** (`INFEASIBLE.md`, `raw_cache/evidence.json`):",
        "   the national aforo archive publishes discharge, reservoir, canal, evaporation and",
        "   water-quality-sampling tables, but no water-temperature series at all.",
        "2. **SAIH Ebro -> the Spanish series that do exist** (`stations.csv`, `networks*/`,",
        "   `daily_long_qc.csv.gz`, `ingest.json`): the Confederacion Hidrografica del Ebro (CHE)",
        "   automatic hydrologic information system publishes a *consolidated daily* water",
        "   temperature (column `MEDIA (oC)`, i.e. a provider daily mean) through",
        f"   `{SAIH_API}`. The `provider` column of every row is `{SAIH_PROVIDER}`, **not** `roea_es`:",
        "   the directory name was fixed by the ingest contract and is kept for the coordinator's",
        "   file layout, but no CEDEX/ROEA value is present anywhere in the panel files.",
        "",
        "## Headline counts (from `ingest.json`)",
        "",
        f"- river stations with a daily water-temperature signal: "
        f"{spain.get('final_counts', {}).get('river_stations_with_daily_water_temperature')}",
        f"- of those, stations with >= 4 complete calendar years: "
        f"{spain.get('final_counts', {}).get('river_stations_ge4_complete_years')}",
        f"- networks emitted: {spain.get('final_counts', {}).get('networks_emitted')}",
        f"- complete station-years in the emitted panel: "
        f"{spain.get('final_counts', {}).get('complete_station_years_in_panel')}",
        "",
        "## Caveats the coordinator must read before sealing",
        "",
    ]
    lines += [f"- {caveat}" for caveat in spain.get("caveats", [])]
    lines += [
        "",
        "## Reproduction",
        "",
        "```bash",
        "python3 scripts/260_multi_agency_be_es_ingest.py --provider es",
        "```",
        "",
    ]
    (ES_ROOT / "README.md").write_text("\n".join(lines), encoding="utf-8")



def write_es_infeasible(evidence: dict[str, Any]) -> None:
    lines: list[str] = []
    add = lines.append
    add("# ROEA / CEDEX *Anuario de Aforos* (Spain) \u2014 INFEASIBLE for the daily transport panel")
    add("")
    add(f"Verdict: **{evidence['verdict']}**. Retrieved {evidence['generated_utc']} by")
    add("`scripts/260_multi_agency_be_es_ingest.py`")
    add("(`python3 scripts/260_multi_agency_be_es_ingest.py --provider es`).")
    add("")
    add("The transport protocol needs a **daily river water-temperature** series in \u00b0C with a")
    add("provider statistic (`MULTI_AGENCY_TRANSPORT_PROTOCOL.md` rules 2\u20133). The Spanish")
    add("national aforo archive publishes **discharge, reservoir, canal, evaporation and")
    add("water-quality-sampling** tables, but no water-temperature series. No network is emitted;")
    add("nothing was scored.")
    add("")
    add("## 1. Endpoint probe (HTTP evidence)")
    add("")
    add("| URL | HTTP | bytes | transport | note |")
    add("|---|---|---|---|---|")
    root_url = (evidence.get("demarcaciones_root") or {}).get("url")
    for record in evidence["endpoint_probes"]:
        if root_url and record.get("url") == root_url:
            continue  # reported separately below with its own transport record
        status = record.get("status")
        if status in (200,) or (isinstance(status, int) and 400 <= status < 500):
            sample = (record.get("sample") or "").strip().splitlines()[0] if record.get("sample") else ""
            note = sample[:80].replace("|", "/")
        else:
            note = str(record.get("error") or "")[:80].replace("|", "/")
        add(
            f"| `{record['url']}` | {status} | {record.get('bytes')} | "
            f"{record.get('transport', 'urllib')} | {note} |"
        )
    root = evidence.get("demarcaciones_root") or {}
    add("")
    add(
        f"The demarcaci\u00f3n index `{root.get('url')}` was read separately "
        f"(HTTP {root.get('status')}, {root.get('bytes')} bytes, transport {root.get('transport')})."
    )
    add("")
    add("No data API is exposed. Under `/anuarioaforos/` the `api/` and `datos/` paths answer 403, and")
    add("`/roea/` and `/roea/api/estaciones` both return the CHE portal landing page (HTTP 200,")
    add("byte-identical 4,580-byte soft 404) rather than data. The site serves an ASP/HTML download")
    add("tree plus per-demarcaci\u00f3n CSV packages. Python's OpenSSL cannot complete the TLS handshake")
    add("with `ceh.cedex.es` (`SSL: UNEXPECTED_EOF_WHILE_READING`); those probes were repeated with the")
    add("system `curl`, and the transport column records which client produced each answer.")
    add("")
    add("## 2. Published data files (variable census)")
    add("")
    add("Distinct file names found on the per-demarcaci\u00f3n download pages (`<DEMARCACION>_csv.asp`):")
    add("")
    add("| file | demarcaciones publishing it |")
    add("|---|---|")
    for name, count in sorted(evidence["file_name_census"].items()):
        add(f"| `{name}` | {count} |")
    add("")
    add("File families (Anuario de Aforos 2021-2022 edition): `afliq*` aforos l\u00edquidos")
    add("(discharge measurements), `mensual_*`/`anual_*`/`estadis_*` monthly/annual statistics,")
    add("`embalse`/`canal`/`evap` reservoir, canal and evaporation tables, `estaf`/`estev` station")
    add("catalogues, `gr_cuenca`/`hojas50`/`muni`/`prov` geography. **No temperature table exists.**")
    add("")
    temperature_like = evidence.get("temperature_like_files") or []
    add(f"File names matching temp/term/calid: `{temperature_like}`")
    add("")
    add("## 3. Station catalogue columns")
    add("")
    station = evidence.get("station_catalogue_probe") or {}
    if station.get("columns"):
        add(f"`{station_url_label(station)}` (HTTP {station.get('status')}, {station.get('bytes')} bytes):")
        add("")
        add("```")
        add(str(station.get("header")))
        add("```")
        add("")
        add(f"temperature column present: **{station.get('has_temperature_column')}**")
    else:
        add(f"station catalogue probe: {json.dumps(station)[:500]}")
    add("")
    add("## 4. The Spanish series that do exist (found instead)")
    add("")
    add("Spanish river water temperature is published by the per-confederaci\u00f3n SAIH telemetry")
    add("systems, not by CEDEX. The only reachable operator with a **provider daily** water")
    add("temperature statistic is SAIH Ebro (Confederaci\u00f3n Hidrogr\u00e1fica del Ebro):")
    add("`https://www.saihebro.com/api/datos-historicos` with `tipoConsolidado=diario`,")
    add("`tiposSenal=TEMPA` and a daily CSV column `MEDIA (oC)`. Its coverage is small and is")
    add("reported in this directory's `README.md`, `stations.csv` and `ingest.json` (provider")
    add("column `saih_ebro`). CEDEX/ROEA itself contributes nothing.")
    add("")
    add("## 5. Reproduction")
    add("")
    add("```bash")
    add("python3 scripts/260_multi_agency_be_es_ingest.py --provider es")
    add("```")
    add("")
    add("Raw evidence: `results/wrr_submission_ready/multi_agency_ingest/roea_es/raw_cache/evidence.json`")
    add("and the cached listing HTML files in the same directory.")
    add("")
    (ES_ROOT / "INFEASIBLE.md").write_text("\n".join(lines), encoding="utf-8")


def station_url_label(record: dict[str, Any]) -> str:
    return str(record.get("url", ""))


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["be", "es", "both"], default="both")
    parser.add_argument("--refresh", action="store_true", help="re-download even when a raw cache exists")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="rewrite the Spanish INFEASIBLE.md/README.md from the cached evidence (no requests)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="use only the raw cache; never download (for re-processing a partial ingest)",
    )
    args = parser.parse_args(argv)

    if args.report_only:
        evidence = json.loads((ES_ROOT / "raw_cache" / "evidence.json").read_text(encoding="utf-8"))
        spain = json.loads((ES_ROOT / "ingest.json").read_text(encoding="utf-8"))
        write_es_infeasible(evidence)
        write_es_readme(evidence, spain)
        print("rewrote roea_es/INFEASIBLE.md and roea_es/README.md from the cached evidence")
        return 0
    if args.provider in ("be", "both"):
        run_be(args.refresh, offline=args.offline)
    if args.provider in ("es", "both"):
        run_es_probe(args.refresh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
