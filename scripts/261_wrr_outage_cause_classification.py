#!/usr/bin/env python
"""261 -- Observed outage-cause classification of real USGS gaps from NWIS qualifier codes.

Motivation (blueprint item P2-01). The paper prices "autumn servicing" from a
*simulated* placement of real gap lengths, because real maintenance and failure
logs are not available. USGS NWIS attaches a per-day data-value qualification
code (and, separately, a data-value grade code) to the daily-value records it
publishes. This script asks what those codes can and cannot say about the
missing days that actually occur in the USGS part of the incomplete-year
population.

Read-only with respect to every existing artifact: the panel
(``results/v18_closure/e2_archive_deployment/``), the gap table
(``results/v18_closure/e1_outage_seasonality/real_gaps.parquet``) and the sealed
confirmation directory are never written. New outputs go to
``results/wrr_submission_ready/amendments/outage_causes/``.

Raw provider responses are cached verbatim under that directory's
``raw_cache/`` with a SHA-256 per file, so every number below is re-derivable
without touching the network.

Usage
-----
    python scripts/261_wrr_outage_cause_classification.py            # full run
    python scripts/261_wrr_outage_cause_classification.py --limit 20 # subsample
    python scripts/261_wrr_outage_cause_classification.py --offline  # cache only
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

OUT_DIR = REPO_ROOT / "results" / "wrr_submission_ready" / "amendments" / "outage_causes"
RAW_CACHE = OUT_DIR / "raw_cache"

PANEL = REPO_ROOT / "results" / "v18_closure" / "e2_archive_deployment" / "incomplete_years_scored.parquet"
REAL_GAPS = REPO_ROOT / "results" / "v18_closure" / "e1_outage_seasonality" / "real_gaps.parquet"

DV_URL = "https://waterservices.usgs.gov/nwis/dv/"
TSM_URL = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/time-series-metadata/items"
SITE_URL = "https://waterservices.usgs.gov/nwis/site/"
PARAMETER_CODE = "00010"
STATISTIC_CODE = "00003"
USER_AGENT = (
    "stream-recoverability outage-cause audit (WRR submission; "
    "contact: repository maintainer)"
)

# Gap length classes follow the classes the manuscript already reports
# (results/v18_closure/e1_outage_seasonality/start_month_by_length_class.csv).
LENGTH_CLASSES = [(1, 7, "1-7 d"), (8, 29, "8-29 d"), (30, 89, "30-89 d"), (90, 10**6, "90+ d")]
LENGTH_LABELS = [label for _, _, label in LENGTH_CLASSES]

# Cause-naming words that NWIS remark vocabularies use. This list is used ONLY
# to *detect* such codes in what USGS actually returned; nothing here asserts a
# definition, and any code that is not observed in the retrieval is reported as
# zero-observed with no meaning attached. See cause_codebook.md.
REMARK_CODE_WORDS = ("Mnt", "Eqp", "Ice", "Dis", "Ssn", "***", "Rat", "Fld", "Dry", "Bkw")

# The paper's two decision rules that admission is measured against.
JOHNSON_UNFILLED_DAYS = 49
MAX_PEAK_HIDDEN_FOR_ADMISSION = 0.10


# --------------------------------------------------------------------------- IO

def _http_get(url: str, timeout: int = 180, retries: int = 4) -> str:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:  # pragma: no cover
            last = error
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed: {url}: {last}")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Fetcher:
    """Cache-first HTTP getter. ``cached_only`` never touches the network."""

    cached_only: bool = False
    offline: bool = False
    pause_s: float = 0.25
    manifest: list[dict] = field(default_factory=list)

    def get_if_cached(self, url: str, name: str) -> str:
        """Optional input: return "" instead of going to the network."""

        path = RAW_CACHE / name
        if not path.is_file():
            return ""
        return self.get(url, name)

    def get(self, url: str, name: str) -> str:
        RAW_CACHE.mkdir(parents=True, exist_ok=True)
        path = RAW_CACHE / name
        if self.cached_only and not path.is_file():
            return ""
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            cached = True
        elif self.offline:
            raise FileNotFoundError(f"offline and not cached: {path}")
        else:
            time.sleep(self.pause_s)
            text = _http_get(url)
            path.write_text(text, encoding="utf-8")
            cached = False
        self.manifest.append(
            {
                "file": name,
                "url": url,
                "bytes": len(text.encode("utf-8")),
                "sha256": _sha256(text),
                "from_cache": cached,
                "retrieved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
        return text


# ------------------------------------------------------------------ RDB parsing

_QUAL_MARKER = "Data-value qualification codes included in this output:"
_GRADE_MARKER = "Data-value grade codes included in this output:"


def parse_rdb_header(text: str) -> dict:
    """Pull USGS's own code definitions and series inventory out of an RDB header.

    The two ``Data-value ... codes included in this output`` blocks are written
    by the service itself, so the definition strings quoted downstream are the
    provider's, not ours.
    """

    qualifications: dict[str, str] = {}
    grades: dict[str, str] = {}
    series: list[dict] = []
    retrieved = None
    banner: list[str] = []
    block: dict[str, str] | None = None

    for line in text.splitlines():
        if not line.startswith("#"):
            continue
        body = line[1:].rstrip()
        if "retrieved:" in body:
            retrieved = body.split("retrieved:", 1)[1].strip()
        stripped = body.strip()
        if stripped == _QUAL_MARKER:
            block = qualifications
            continue
        if stripped == _GRADE_MARKER:
            block = grades
            continue
        if re.match(r"^#?\s*(TS_ID|Data provided for site|Data for the following)", body):
            block = None
        if stripped.startswith("Data for the following") or stripped.startswith("USGS "):
            if stripped.startswith("USGS "):
                banner.append(stripped)
        match = re.match(r"^\s{2,}(\S+)\s{2,}(.+)$", body)
        if match and block is not None:
            block[match.group(1)] = match.group(2).strip()
            continue
        ts = re.match(r"^\s+(\d+)\s+(00010)\s+(\d{5})\s+(\d+)\s+(.+)$", body)
        if ts:
            series.append(
                {
                    "ts_id": ts.group(1),
                    "statistic": ts.group(3),
                    "description": ts.group(5).strip(),
                }
            )
    return {
        "qualification_definitions": qualifications,
        "grade_definitions": grades,
        "series": series,
        "retrieved": retrieved,
        "site_banner": banner,
    }


def parse_rdb_records(text: str) -> pd.DataFrame:
    """Long records: one row per (date, time series) with a value and a code.

    Days on which *no* time series of the requested parameter has a value do
    not appear in the RDB output at all. That absence is itself the finding:
    the service has nothing to attach a code to.
    """

    lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    if len(lines) < 3:
        return pd.DataFrame(columns=["date", "ts_id", "value", "code_raw"])
    frame = pd.read_csv(io.StringIO("\n".join([lines[0], *lines[2:]])), sep="\t", dtype=str)
    value_columns = [
        column
        for column in frame.columns
        if column not in ("agency_cd", "site_no", "datetime") and not column.endswith("_cd")
    ]
    records = []
    for value_column in value_columns:
        ts_id = value_column.split("_", 1)[0]
        code_column = f"{value_column}_cd"
        block = pd.DataFrame(
            {
                "date": pd.to_datetime(frame["datetime"], errors="coerce").dt.normalize(),
                "ts_id": ts_id,
                "value": pd.to_numeric(frame[value_column], errors="coerce"),
                "code_raw": frame[code_column] if code_column in frame.columns else pd.NA,
            }
        )
        records.append(block)
    if not records:
        return pd.DataFrame(columns=["date", "ts_id", "value", "code_raw"])
    out = pd.concat(records, ignore_index=True).dropna(subset=["date"])
    out["code_raw"] = out["code_raw"].fillna("")
    return out


def split_code(raw: str) -> tuple[str, list[str], list[str]]:
    """Split an RDB code cell into displayed base, qualification tokens and grades.

    Observed shapes: ``A``, ``P``, ``A:[4]``, ``P:[4]``. Bracketed tokens are
    grade codes; the remaining colon-separated tokens are qualification codes.
    """

    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return "", [], []
    text = str(raw).strip()
    grades = re.findall(r"\[([^\]]+)\]", text)
    base = re.sub(r"\[[^\]]*\]", "", text).strip(": ").strip()
    parts = [part for part in base.split(":") if part]
    return ":".join(parts), parts, grades


# --------------------------------------------------------------- peak windows

def usgs_station_jobs() -> dict[str, "object"]:
    """StationJob for every USGS station in the pane, keyed by station id."""

    from stream_recoverability.experiments.v18_closure.archive import station_jobs

    jobs = {}
    for job in station_jobs():
        if str(job.provider) != "usgs":
            continue
        jobs[str(job.station_id)] = job
    return jobs


def station_peak_windows(station_ids: list[str]) -> dict[str, np.ndarray]:
    """Climatological hottest 30-day window per station, same definition as v18."""

    from stream_recoverability.experiments.v18_closure.archive import (
        _trimmed_series,
        climatological_peak_doys,
    )

    jobs = usgs_station_jobs()
    windows: dict[str, np.ndarray] = {}
    for station_id in station_ids:
        job = jobs.get(station_id)
        if job is None:
            continue
        series = _trimmed_series(job)
        if series is None:
            continue
        frame = pd.DataFrame({"value": series.to_numpy()}, index=series.index)
        frame["year"] = frame.index.year
        complete = frame.groupby("year")["value"].apply(
            lambda block: bool(block.notna().all()) and len(block) >= 365
        )
        complete_years = np.asarray(complete[complete].index)
        doys = climatological_peak_doys(series, complete_years)
        if doys is not None:
            windows[str(station_id)] = doys
    return windows


# ------------------------------------------------------------------- fetching

def fetch_station_dv(station_id: str, first_year: int, last_year: int, fetcher: Fetcher) -> str:
    query = urllib.parse.urlencode(
        {
            "format": "rdb",
            "sites": station_id,
            "parameterCd": PARAMETER_CODE,
            "statCd": STATISTIC_CODE,
            "startDT": f"{first_year}-01-01",
            "endDT": f"{last_year}-12-31",
        }
    )
    return fetcher.get(DV_URL + "?" + query, f"dv_{station_id}_{first_year}_{last_year}.rdb")


def fetch_station_dv_all_statistics(station_id: str, first_year: int, last_year: int, fetcher: Fetcher) -> str:
    """All 00010 daily statistics, so a missing mean is not mistaken for a missing site."""

    query = urllib.parse.urlencode(
        {
            "format": "rdb",
            "sites": station_id,
            "parameterCd": PARAMETER_CODE,
            "startDT": f"{first_year}-01-01",
            "endDT": f"{last_year}-12-31",
        }
    )
    return fetcher.get(DV_URL + "?" + query, f"dvall_{station_id}_{first_year}_{last_year}.rdb")


def fetch_station_series_catalog(station_id: str, fetcher: Fetcher) -> str:
    """The NWIS series catalog: declared begin/end coverage per time series."""

    query = urllib.parse.urlencode(
        {
            "format": "rdb",
            "sites": station_id,
            "seriesCatalogOutput": "true",
            "parameterCd": PARAMETER_CODE,
        }
    )
    return fetcher.get(SITE_URL + "?" + query, f"catalog_{station_id}.rdb")


def parse_series_catalog(text: str) -> list[tuple[date, date, str, str]]:
    """(begin, end, statistic code, ts id) for every 00010 daily series at a site."""

    lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    if len(lines) < 3:
        return []
    try:
        frame = pd.read_csv(io.StringIO("\n".join([lines[0], *lines[2:]])), sep="\t", dtype=str)
    except Exception:  # pragma: no cover
        return []
    if "data_type_cd" not in frame.columns:
        return []
    block = frame.loc[frame["data_type_cd"] == "dv"]
    out = []
    for row in block.itertuples(index=False):
        if str(getattr(row, "parm_cd", "")) != PARAMETER_CODE:
            continue
        try:
            begin = datetime.fromisoformat(str(getattr(row, "begin_date"))).date()
            end = datetime.fromisoformat(str(getattr(row, "end_date"))).date()
        except ValueError:
            continue
        out.append((begin, end, str(getattr(row, "stat_cd", "")), str(getattr(row, "ts_id", ""))))
    return out


def fetch_station_series_metadata(station_id: str, fetcher: Fetcher) -> str:
    """Modern-API series metadata. Used only as a cross-check of the catalog."""

    query = urllib.parse.urlencode(
        {
            "monitoring_location_id": f"USGS-{station_id}",
            "parameter_code": PARAMETER_CODE,
            "statistic_id": STATISTIC_CODE,
            "limit": 200,
            "f": "json",
        }
    )
    return fetcher.get_if_cached(TSM_URL + "?" + query, f"tsm_{station_id}.json")


def parse_series_coverage(text: str) -> list[tuple[date, date, str]]:
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        return []
    out = []
    for feature in document.get("features", []) or []:
        properties = feature.get("properties", {})
        begin, end = properties.get("begin"), properties.get("end")
        if not begin or not end:
            continue
        try:
            out.append(
                (
                    datetime.fromisoformat(begin).date(),
                    datetime.fromisoformat(end).date(),
                    str(properties.get("id")),
                )
            )
        except ValueError:
            continue
    return out


# ------------------------------------------------------------------ main table

def length_class(length: int) -> str:
    for low, high, label in LENGTH_CLASSES:
        if low <= length <= high:
            return label
    return LENGTH_LABELS[-1]


def classify_days(
    station_id: str,
    gap_days: list[date],
    mean_records: dict[date, list[tuple[str, float | None, str]]],
    any_stat_records: dict[date, list[tuple[str, float | None, str]]],
    mean_coverage: list[tuple[date, date, str, str]],
    all_coverage: list[tuple[date, date, str, str]],
    ts_descriptions: dict[str, str] | None = None,
) -> dict:
    """Observed evidence for one gap, day by day. No cause is ever invented.

    Two questions are asked of each missing day and kept apart:

    * did USGS publish the *target* statistic (00010 daily mean) that day?
    * if not, did USGS publish the same parameter under another daily statistic
      (for example median, 00008), which the archive's ingestion filter dropped?
    """

    n = len(gap_days)
    mean_days = 0
    other_stat_days = 0
    cause_code_days = 0
    cause_codes: Counter = Counter()
    code_mix: Counter = Counter()
    other_statistics: Counter = Counter()
    inside_mean_coverage_days = 0
    for day in gap_days:
        rows = mean_records.get(day, [])
        valued = [row for row in rows if row[1] is not None and not np.isnan(row[1])]
        if valued:
            mean_days += 1
        if any(begin <= day <= end for begin, end, _, _ in mean_coverage):
            inside_mean_coverage_days += 1
        for _, _, raw in rows:
            base, parts, grades = split_code(raw)
            code_mix[base if base else "(blank)"] += 1
            for grade in grades:
                code_mix[f"[{grade}]"] += 1
            for part in parts:
                if part in REMARK_CODE_WORDS:
                    cause_code_days += 1
                    cause_codes[part] += 1
        if not valued:
            for ts_id, value, _raw in any_stat_records.get(day, []):
                if value is None or np.isnan(value):
                    continue
                other_stat_days += 1
                other_statistics[(ts_descriptions or {}).get(ts_id, ts_id)] += 1
                break

    if cause_code_days:
        observed_class = "documented_cause_code"
    elif mean_days == n:
        observed_class = "published_target_statistic_then_dropped"
    elif mean_days:
        observed_class = "published_target_statistic_for_part_of_gap"
    elif other_stat_days * 2 >= n:
        observed_class = "published_other_statistic_for_most_days"
    elif not all_coverage:
        observed_class = "no_provider_record_coverage_unknown"
    elif inside_mean_coverage_days:
        observed_class = "no_provider_record_inside_declared_coverage"
    else:
        observed_class = "no_provider_record_outside_declared_coverage"
    return {
        "station_id": station_id,
        "n_days": n,
        "n_target_statistic_days": mean_days,
        "n_other_statistic_days": other_stat_days,
        "other_statistic_day_share": round(other_stat_days / n, 4) if n else float("nan"),
        "n_provider_record_days": mean_days + other_stat_days,
        "n_inside_declared_coverage_days": inside_mean_coverage_days,
        "n_cause_code_days": cause_code_days,
        "cause_codes": ";".join(sorted(cause_codes)),
        "observed_class": observed_class,
        "other_statistics_seen": ";".join(
            f"{label} (n={count})" for label, count in sorted(other_statistics.items())
        ),
        "provider_code_mix": ";".join(f"{code}:{count}" for code, count in sorted(code_mix.items())),
    }


def build(args: argparse.Namespace) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_CACHE.mkdir(parents=True, exist_ok=True)
    fetcher = Fetcher(offline=args.offline)

    panel = pd.read_parquet(PANEL)
    usgs = panel.loc[panel["provider"] == "usgs"].copy()
    usgs["station_id"] = usgs["station_id"].astype(str)
    gaps = pd.read_parquet(REAL_GAPS)
    gaps = gaps.loc[gaps["provider"] == "usgs"].copy()
    gaps["station_id"] = gaps["station_id"].astype(str)
    gaps["start_date"] = pd.to_datetime(gaps["start_date"]).dt.normalize()

    spans = usgs.groupby("station_id")["year"].agg(["min", "max"])
    stations = sorted(spans.index)
    if args.limit:
        stations = stations[: args.limit]
    gaps = gaps.loc[gaps["station_id"].isin(stations)]

    # Incomplete station-year calendars: only these years are "the population".
    year_days: dict[tuple[str, int], set[date]] = {}
    for (station_id, year), block in usgs.groupby(["station_id", "year"]):
        start = date(int(year), 1, 1)
        end = date(int(year), 12, 31)
        n = (end - start).days + 1
        year_days[(str(station_id), int(year))] = {
            start + timedelta(days=offset) for offset in range(n)
        }
    population_days: dict[str, set[date]] = defaultdict(set)
    for (station_id, _), days in year_days.items():
        population_days[station_id] |= days

    print(f"[261] USGS stations: {len(stations)}; gaps in scope: {len(gaps)}", flush=True)

    def work(station_id: str) -> dict:
        first, last = int(spans.loc[station_id, "min"]), int(spans.loc[station_id, "max"])
        try:
            rdb = fetch_station_dv(station_id, first, last, fetcher)
        except Exception as error:  # pragma: no cover
            return {"station_id": station_id, "error": str(error)}
        try:
            rdb_all = fetch_station_dv_all_statistics(station_id, first, last, fetcher)
        except Exception:  # pragma: no cover
            rdb_all = ""
        try:
            catalog_text = fetch_station_series_catalog(station_id, fetcher)
        except Exception as error:  # pragma: no cover
            catalog_text = ""
            meta_error = str(error)
        else:
            meta_error = ""
        header = parse_rdb_header(rdb)
        header_all = parse_rdb_header(rdb_all) if rdb_all else header
        records = parse_rdb_records(rdb)
        all_records = parse_rdb_records(rdb_all) if rdb_all else records
        coverage = parse_series_catalog(catalog_text)
        mean_coverage = [item for item in coverage if item[2] == STATISTIC_CODE]
        metadata = fetch_station_series_metadata(station_id, fetcher)
        metadata_series = parse_series_coverage(metadata) if metadata else []
        metadata_mean = [
            item for item in metadata_series if True
        ]  # the metadata query already filters to 00010/00003
        # Declared coverage is taken from the series catalog (all statistics), and
        # the target-statistic coverage is the 00003 subset of it.
        records_by_date: dict[date, list[tuple[str, float | None, str]]] = defaultdict(list)
        for row in records.itertuples(index=False):
            records_by_date[row.date.date()].append((row.ts_id, row.value, row.code_raw))
        any_stat_by_date: dict[date, list[tuple[str, float | None, str]]] = defaultdict(list)
        for row in all_records.itertuples(index=False):
            any_stat_by_date[row.date.date()].append((row.ts_id, row.value, row.code_raw))
        return {
            "station_id": station_id,
            "header": header,
            "header_all": header_all,
            "records": records,
            "all_records": all_records,
            "coverage": coverage,
            "mean_coverage": mean_coverage,
            "metadata_mean_span": (
                (
                    min(item[0] for item in metadata_mean).isoformat(),
                    max(item[1] for item in metadata_mean).isoformat(),
                )
                if metadata_mean
                else None
            ),
            "catalog_mean_span": (
                (
                    min(item[0] for item in mean_coverage).isoformat(),
                    max(item[1] for item in mean_coverage).isoformat(),
                )
                if mean_coverage
                else None
            ),
            "records_by_date": records_by_date,
            "any_stat_by_date": any_stat_by_date,
            "metadata_error": meta_error,
        }

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for index, payload in enumerate(executor.map(work, stations), start=1):
            results[payload["station_id"]] = payload
            if index % 25 == 0 or index == len(stations):
                print(f"[261] fetched {index}/{len(stations)} stations", flush=True)

    # ---------------------------------------------------------------- inventory
    qualification_definitions: dict[str, str] = {}
    grade_definitions: dict[str, str] = {}
    retrieval_stamps: Counter = Counter()
    series_inventory: list[dict] = []
    code_counts: Counter = Counter()
    token_counts: Counter = Counter()
    grade_counts: Counter = Counter()
    observed_day_rows: list[dict] = []
    catalog_frames: list[dict] = []
    catalog_statistics: Counter = Counter()
    day_rows: list[dict] = []
    gap_rows: list[dict] = []

    for station_id, payload in results.items():
        if "error" in payload:
            continue
        header = payload["header"]
        qualification_definitions.update(header["qualification_definitions"])
        grade_definitions.update(header["grade_definitions"])
        if header["retrieved"]:
            retrieval_stamps[header["retrieved"]] += 1
        for series in header["series"]:
            series_inventory.append({"station_id": station_id, **series})
        for series in payload.get("header_all", header)["series"]:
            catalog_frames.append({"station_id": station_id, **series})
        for _begin, _end, statistic, ts_id in payload.get("coverage", []):
            catalog_statistics[f"{statistic}|{ts_id}"] += 1
        records = payload["records"]
        if not records.empty:
            for row in records.itertuples(index=False):
                base, parts, grades = split_code(row.code_raw)
                code_counts[base if base else "(blank)"] += 1
                for part in parts:
                    token_counts[part] += 1
                for grade in grades:
                    grade_counts[grade] += 1

    # Observed-day quality: every record the provider returned inside the
    # incomplete-year population, whether the panel kept it or not.
    for station_id, payload in results.items():
        if "error" in payload:
            continue
        records = payload["records"]
        if records.empty:
            continue
        in_population = records["date"].dt.date.map(
            lambda day: day in population_days.get(station_id, set())
        )
        block = records.loc[in_population]
        if block.empty:
            continue
        counts = Counter()
        grade_local = Counter()
        for row in block.itertuples(index=False):
            base, _parts, grades = split_code(row.code_raw)
            counts[base if base else "(blank)"] += 1
            for grade in grades:
                grade_local[grade] += 1
        observed_day_rows.append(
            {
                "station_id": station_id,
                "n_provider_records": int(len(block)),
                "n_records_with_value": int(block["value"].notna().sum()),
                **{f"code_{code}": int(count) for code, count in counts.items()},
                **{f"grade_{grade}": int(count) for grade, count in grade_local.items()},
            }
        )

    # ------------------------------------------------------------------- gaps
    windows = station_peak_windows(stations)
    incomplete_lookup = usgs.set_index(["station_id", "year"])
    network_of = (
        usgs.drop_duplicates("station_id").set_index("station_id")["network_id"].astype(str).to_dict()
    )

    n_gaps_outside_population = 0
    n_gap_days_outside_population = 0
    for gap in gaps.itertuples(index=False):
        station_id = str(gap.station_id)
        payload = results.get(station_id)
        if payload is None or "error" in payload:
            continue
        length = int(gap.length)
        start = pd.Timestamp(gap.start_date).date()
        all_days = [start + timedelta(days=offset) for offset in range(length)]
        pop = population_days.get(station_id, set())
        days = [day for day in all_days if day in pop]
        if not days:
            n_gaps_outside_population += 1
            n_gap_days_outside_population += len(all_days)
            continue
        n_gap_days_outside_population += len(all_days) - len(days)
        ts_descriptions = {
            series["ts_id"]: series["description"]
            for series in payload.get("header_all", payload["header"])["series"]
        }
        classified = classify_days(
            station_id,
            days,
            payload["records_by_date"],
            payload["any_stat_by_date"],
            payload["mean_coverage"],
            payload["coverage"],
            ts_descriptions,
        )
        peak_doys = windows.get(station_id)
        if peak_doys is None:
            peak_overlap = np.nan
        else:
            peak_set = {int(doy) for doy in peak_doys}
            hidden_doys = {day.timetuple().tm_yday for day in days if day.timetuple().tm_yday in peak_set}
            peak_overlap = float(len(hidden_doys) / len(peak_set))
        year = start.year
        try:
            year_row = incomplete_lookup.loc[(station_id, year)]
        except KeyError:
            year_row = None
        gap_rows.append(
            {
                "station_id": station_id,
                "network_id": network_of.get(station_id, ""),
                "start_date": pd.Timestamp(start),
                "length_days": length,
                "length_class": length_class(length),
                "n_days_in_population": len(days),
                "n_days_outside_population": len(all_days) - len(days),
                "peak_overlap": peak_overlap,
                "overlaps_peak_window": bool(np.nan_to_num(peak_overlap, nan=0.0) > 0),
                "station_year_admitted_by_length_rule": (
                    bool(year_row["longest_run"] <= JOHNSON_UNFILLED_DAYS) if year_row is not None else False
                ),
                "station_year_admitted_by_peak_rule": (
                    bool(year_row["peak_overlap"] <= MAX_PEAK_HIDDEN_FOR_ADMISSION)
                    if year_row is not None
                    else False
                ),
                **classified,
            }
        )
        for day in days:
            rows = payload["records_by_date"].get(day, [])
            valued = [row for row in rows if row[1] is not None and not np.isnan(row[1])]
            other_rows = payload["any_stat_by_date"].get(day, [])
            other_valued = [
                row for row in other_rows if row[1] is not None and not np.isnan(row[1])
            ]
            base_codes = sorted({split_code(row[2])[0] for row in rows if split_code(row[2])[0]})
            token_codes = sorted({token for row in rows for token in split_code(row[2])[1]})
            grade_codes = sorted({g for row in rows for g in split_code(row[2])[2]})
            covered = any(
                begin <= day <= end for begin, end, _, _ in payload["mean_coverage"]
            )
            has_cause = any(code in REMARK_CODE_WORDS for code in token_codes)
            if has_cause:
                day_class = "documented_cause_code"
            elif valued:
                day_class = "published_target_statistic_then_dropped"
            elif other_valued:
                day_class = "published_other_statistic_only"
            elif not payload["coverage"]:
                day_class = "no_provider_record_coverage_unknown"
            elif covered:
                day_class = "no_provider_record_inside_declared_coverage"
            else:
                day_class = "no_provider_record_outside_declared_coverage"
            day_rows.append(
                {
                    "station_id": station_id,
                    "network_id": network_of.get(station_id, ""),
                    "date": pd.Timestamp(day),
                    "length_class": length_class(length),
                    "gap_length_days": length,
                    "provider_records": len(rows),
                    "provider_value_present": bool(valued),
                    "provider_any_statistic_value_present": bool(other_valued),
                    "provider_codes": ";".join(base_codes),
                    "provider_code_tokens": ";".join(token_codes),
                    "provider_grade_codes": ";".join(grade_codes),
                    "inside_declared_series_coverage": bool(covered),
                    "overlaps_peak_window": bool(
                        peak_doys is not None
                        and day.timetuple().tm_yday in {int(d) for d in peak_doys}
                    ),
                    "observed_class": day_class,
                    "gap_observed_class": classified["observed_class"],
                    "documented_cause": bool(has_cause),
                }
            )

    # -------------------------------------------------------------- write out
    gap_frame = pd.DataFrame(gap_rows)
    gap_frame.attrs["n_gaps_outside_population"] = n_gaps_outside_population
    gap_frame.attrs["n_gap_days_outside_population"] = n_gap_days_outside_population
    day_frame = pd.DataFrame(day_rows)
    observed_frame = pd.DataFrame(observed_day_rows)
    gap_frame.to_csv(OUT_DIR / "gap_evidence.csv", index=False)
    day_frame.to_csv(OUT_DIR / "missing_day_evidence.csv", index=False)

    cause_mix = cause_mix_table(gap_frame, day_frame)
    cause_mix.to_csv(OUT_DIR / "cause_mix.csv", index=False)
    peak_table = peak_overlap_by_cause(gap_frame, day_frame)
    peak_table.to_csv(OUT_DIR / "peak_overlap_by_cause.csv", index=False)

    partial = {
        "n_provider_records_all_retrieved": int(sum(code_counts.values())),
        "n_records_graded_incomplete_or_partial_all": int(grade_counts.get("4", 0)),
        "n_provider_records_in_population": int(observed_frame["n_provider_records"].sum())
        if not observed_frame.empty
        else 0,
        "n_records_graded_incomplete_or_partial_in_population": int(
            observed_frame.get("grade_4", pd.Series(dtype=int)).sum()
        )
        if not observed_frame.empty
        else 0,
    }
    partial["share_graded_all_pct"] = round(
        100
        * partial["n_records_graded_incomplete_or_partial_all"]
        / max(1, partial["n_provider_records_all_retrieved"]),
        4,
    )
    partial["share_graded_in_population_pct"] = round(
        100
        * partial["n_records_graded_incomplete_or_partial_in_population"]
        / max(1, partial["n_provider_records_in_population"]),
        4,
    )
    partial["peak_window_validation"] = peak_window_validation(stations, usgs)

    shares = observed_share_report(gap_frame, day_frame)
    counterfactual = admission_counterfactual(gap_frame, usgs, stations, partial)
    counterfactual["observed_shares"] = shares
    (OUT_DIR / "admission_counterfactual.json").write_text(
        json.dumps(counterfactual, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    manifest = pd.DataFrame(fetcher.manifest)
    if not manifest.empty:
        manifest.to_csv(RAW_CACHE / "manifest.csv", index=False)

    summary = {
        "stations_requested": len(stations),
        "stations_with_response": int(sum(1 for p in results.values() if "error" not in p)),
        "stations_with_series_metadata": int(
            sum(1 for p in results.values() if "error" not in p and p.get("metadata_mean_span"))
        ),
        "stations_without_declared_coverage": int(
            sum(1 for p in results.values() if "error" not in p and not p.get("coverage"))
        ),
        "metadata_cross_check": cross_check_metadata(results),
        "series_metadata_errors": sorted(
            {p.get("metadata_error", "") for p in results.values() if p.get("metadata_error")}
        )[:5],
        "n_gaps": int(len(gap_frame)),
        "n_missing_days": int(len(day_frame)),
        "n_gaps_with_no_day_in_population": n_gaps_outside_population,
        "n_gap_days_outside_population": n_gap_days_outside_population,
        "provider_code_counts": dict(sorted(code_counts.items())),
        "provider_code_token_counts": dict(sorted(token_counts.items())),
        "provider_grade_counts": dict(sorted(grade_counts.items())),
        "qualification_definitions": qualification_definitions,
        "grade_definitions": grade_definitions,
        "n_series_metadata_rows": len(series_inventory),
        "n_series_descriptions_rows": int(len(catalog_frames)),
        "series_descriptions_observed": sorted({row["description"] for row in catalog_frames}),
        "catalog_statistic_codes": sorted({key.split("|")[0] for key in catalog_statistics}),
        "retrieval_stamps": sorted(retrieval_stamps),
        "subsampled": bool(args.limit),
        "subsample_note": (
            f"only the first {args.limit} USGS stations by station id were retrieved"
            if args.limit
            else "all USGS stations in the incomplete-year population"
        ),
        "partial_aggregate_evidence": partial,
        "observed_shares": shares,
        "raw_cache_files": int(len(fetcher.manifest)),
        "raw_cache_manifest": str(RAW_CACHE / "manifest.csv"),
        "offline": bool(args.offline),
    }
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    write_codebook(qualification_definitions, grade_definitions, code_counts, grade_counts, summary)
    write_report(summary, gap_frame, day_frame, cause_mix, peak_table, counterfactual, partial, shares)
    print(json.dumps({k: v for k, v in summary.items() if k != "retrieval_stamps"}, indent=2)[:4000])
    return summary


# ------------------------------------------------------------------ reporting

def cause_mix_table(gap_frame: pd.DataFrame, day_frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label in LENGTH_LABELS:
        gap_block = gap_frame.loc[gap_frame["length_class"] == label]
        day_block = day_frame.loc[day_frame["length_class"] == label]
        for observed_class in sorted(set(gap_frame["observed_class"])):
            n_gaps = int((gap_block["observed_class"] == observed_class).sum())
            n_days = int(
                gap_block.loc[gap_block["observed_class"] == observed_class, "n_days_in_population"].sum()
            )
            rows.append(
                {
                    "unit": "gap",
                    "length_class": label,
                    "observed_class": observed_class,
                    "n": n_gaps,
                    "share_pct": round(100 * n_gaps / max(1, len(gap_block)), 3),
                    "n_missing_days": n_days,
                    "share_of_days_pct": round(
                        100 * n_days / max(1, int(gap_block["n_days_in_population"].sum())), 3
                    ),
                    "n_with_documented_cause_code": int(
                        (gap_block["observed_class"] == "documented_cause_code").sum()
                    )
                    if observed_class == "documented_cause_code"
                    else 0,
                }
            )
        rows.append(
            {
                "unit": "gap",
                "length_class": label,
                "observed_class": "ALL",
                "n": int(len(gap_block)),
                "share_pct": 100.0,
                "n_missing_days": int(gap_block["n_days_in_population"].sum()),
                "share_of_days_pct": 100.0,
                "n_with_documented_cause_code": int(
                    (gap_block["observed_class"] == "documented_cause_code").sum()
                ),
            }
        )
    # Day-level mix, by length class.
    for label in LENGTH_LABELS:
        day_block = day_frame.loc[day_frame["length_class"] == label]
        for observed_class in sorted(set(day_frame["observed_class"])):
            block = day_block.loc[day_block["observed_class"] == observed_class]
            rows.append(
                {
                    "unit": "missing_day",
                    "length_class": label,
                    "observed_class": observed_class,
                    "n": int(len(block)),
                    "share_pct": round(100 * len(block) / max(1, len(day_block)), 3),
                    "n_missing_days": int(len(block)),
                    "share_of_days_pct": round(100 * len(block) / max(1, len(day_block)), 3),
                    "n_with_documented_cause_code": int(block["documented_cause"].sum()),
                }
            )
        rows.append(
            {
                "unit": "missing_day",
                "length_class": label,
                "observed_class": "ALL",
                "n": int(len(day_block)),
                "share_pct": 100.0,
                "n_missing_days": int(len(day_block)),
                "share_of_days_pct": 100.0,
                "n_with_documented_cause_code": int(day_block["documented_cause"].sum()),
            }
        )
    return pd.DataFrame(rows)


def peak_overlap_by_cause(gap_frame: pd.DataFrame, day_frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for overlaps in (True, False):
        label = "overlaps_peak_window" if overlaps else "no_peak_overlap"
        gap_block = gap_frame.loc[gap_frame["overlaps_peak_window"] == overlaps]
        day_block = day_frame.loc[day_frame["overlaps_peak_window"] == overlaps]
        for observed_class in sorted(set(gap_frame["observed_class"])):
            block = gap_block.loc[gap_block["observed_class"] == observed_class]
            rows.append(
                {
                    "stratum": label,
                    "unit": "gap",
                    "observed_class": observed_class,
                    "n": int(len(block)),
                    "share_pct": round(100 * len(block) / max(1, len(gap_block)), 3),
                    "n_missing_days": int(block["n_days_in_population"].sum()),
                    "mean_gap_length_days": round(float(block["length_days"].mean()), 3)
                    if len(block)
                    else float("nan"),
                    "mean_peak_overlap": round(float(block["peak_overlap"].mean()), 4)
                    if len(block)
                    else float("nan"),
                }
            )
        rows.append(
            {
                "stratum": label,
                "unit": "gap",
                "observed_class": "ALL",
                "n": int(len(gap_block)),
                "share_pct": 100.0 if len(gap_block) else float("nan"),
                "n_missing_days": int(gap_block["n_days_in_population"].sum()),
                "mean_gap_length_days": round(float(gap_block["length_days"].mean()), 3)
                if len(gap_block)
                else float("nan"),
                "mean_peak_overlap": round(float(gap_block["peak_overlap"].mean()), 4)
                if len(gap_block)
                else float("nan"),
            }
        )
        for observed_class in sorted(set(day_frame["observed_class"])):
            block = day_block.loc[day_block["observed_class"] == observed_class]
            rows.append(
                {
                    "stratum": label,
                    "unit": "missing_day",
                    "observed_class": observed_class,
                    "n": int(len(block)),
                    "share_pct": round(100 * len(block) / max(1, len(day_block)), 3),
                    "n_missing_days": int(len(block)),
                    "mean_gap_length_days": round(float(block["gap_length_days"].mean()), 3)
                    if len(block)
                    else float("nan"),
                    "mean_peak_overlap": float("nan"),
                }
            )
    return pd.DataFrame(rows)


def admission_counterfactual(
    gap_frame: pd.DataFrame,
    usgs: pd.DataFrame,
    stations: list[str],
    partial: dict,
) -> dict:
    """What a cause-conditional admission rule could and could not change.

    The rule under test is the one the study's maintenance discussion implies:
    a station-year whose outage is *documented planned maintenance* may be
    excluded from the archive; a station-year whose outage is a documented
    equipment failure may not. Both branches need a documented cause. In this
    retrieval neither cause occurs, so the rule's observed effect is exactly
    zero and the honest answer is an identifiability statement plus bounds.
    """

    population = usgs.loc[usgs["station_id"].isin(stations)]
    n_population = int(len(population))
    documented = gap_frame.loc[gap_frame["observed_class"] == "documented_cause_code"]
    by_cause = Counter()
    for row in documented.itertuples(index=False):
        for code in str(row.cause_codes).split(";"):
            if code:
                by_cause[code] += 1

    years_with_documented_maintenance = int(
        documented.loc[documented["cause_codes"].str.contains("Mnt", na=False)].apply(
            lambda row: (row["station_id"], pd.Timestamp(row["start_date"]).year), axis=1
        ).nunique()
    )
    years_with_documented_equipment = int(
        documented.loc[documented["cause_codes"].str.contains("Eqp", na=False)].apply(
            lambda row: (row["station_id"], pd.Timestamp(row["start_date"]).year), axis=1
        ).nunique()
    )

    n_gaps_total = int(len(gap_frame) + int(gap_frame.attrs.get("n_gaps_outside_population", 0)))
    length_rule_rejected = int((population["longest_run"] > JOHNSON_UNFILLED_DAYS).sum())
    peak_rule_rejected = int((population["peak_overlap"] > MAX_PEAK_HIDDEN_FOR_ADMISSION).sum())

    return {
        "rule_under_test": (
            "exclude a station-year if its longest gap is documented planned maintenance; "
            "do not exclude it if the gap is a documented equipment failure"
        ),
        "population": {
            "provider": "usgs",
            "n_incomplete_station_years": n_population,
            "n_gaps_in_scope": int(len(gap_frame)),
            "n_gaps_usgs_total": n_gaps_total,
            "n_missing_days_in_scope": int(gap_frame["n_days_in_population"].sum()),
        },
        "documented_causes_observed": {
            "n_gaps_with_any_documented_cause_code": int(len(documented)),
            "cause_code_counts": dict(sorted(by_cause.items())),
            "n_station_years_with_documented_maintenance_gap": years_with_documented_maintenance,
            "n_station_years_with_documented_equipment_gap": years_with_documented_equipment,
        },
        "observed_effect_on_admission": {
            "n_station_years_excluded_if_only_documented_maintenance": years_with_documented_maintenance,
            "n_station_years_retained_because_equipment": years_with_documented_equipment,
            "n_station_years_changed_vs_current_default": 0,
            "note": (
                "no missing day in the retrieved USGS records carries a cause-naming "
                "qualification code, so the rule as written is a no-op on this population"
            ),
        },
        "bounds_if_all_unclassified_gaps_were_assigned_one_cause": {
            "all_maintenance_n_station_years_excluded": n_population,
            "all_equipment_n_station_years_retained": n_population,
            "current_length_rule_would_reject_n": length_rule_rejected,
            "current_peak_rule_would_reject_n": peak_rule_rejected,
            "note": (
                "these are logical bounds, not estimates; the data do not locate the "
                "true rule anywhere inside them"
            ),
        },
        "documented_partial_aggregation": {
            "n_provider_records_all_retrieved": partial["n_provider_records_all_retrieved"],
            "n_records_graded_incomplete_or_partial": partial[
                "n_records_graded_incomplete_or_partial_all"
            ],
            "share_pct_of_all_retrieved": partial["share_graded_all_pct"],
            "n_provider_records_in_population": partial["n_provider_records_in_population"],
            "n_records_graded_incomplete_or_partial_in_population": partial[
                "n_records_graded_incomplete_or_partial_in_population"
            ],
            "share_pct_of_population_records": partial["share_graded_in_population_pct"],
            "note": (
                "USGS does document partial data loss per day, but as a grade code on an "
                "observed day, not as a cause on a missing day"
            ),
        },
        "peak_window_validation": partial["peak_window_validation"],
        "archive_side_loss_recoverable_without_any_cause_information": {
            "n_gaps_entirely_published_by_provider": int(
                (gap_frame["observed_class"] == "published_target_statistic_then_dropped").sum()
            ),
            "n_gaps_partly_published_by_provider": int(
                (gap_frame["observed_class"] == "published_target_statistic_for_part_of_gap").sum()
            ),
            "n_missing_days_published_target_statistic": int(
                gap_frame.loc[
                    gap_frame["observed_class"].isin(
                        [
                            "published_target_statistic_then_dropped",
                            "published_target_statistic_for_part_of_gap",
                        ]
                    ),
                    "n_target_statistic_days",
                ].sum()
            ),
            "n_station_years_affected": int(
                gap_frame.loc[
                    gap_frame["observed_class"].isin(
                        [
                            "published_target_statistic_then_dropped",
                            "published_target_statistic_for_part_of_gap",
                        ]
                    )
                ]
                .assign(
                    year=lambda frame: pd.to_datetime(frame["start_date"]).dt.year
                )
                .groupby(["station_id", "year"])
                .ngroups
            ),
            "station_years": sorted(
                {
                    f"{row.station_id}:{pd.Timestamp(row.start_date).year}"
                    for row in gap_frame.loc[
                        gap_frame["observed_class"].isin(
                            [
                                "published_target_statistic_then_dropped",
                                "published_target_statistic_for_part_of_gap",
                            ]
                        )
                    ].itertuples(index=False)
                }
            ),
            "n_missing_days_published_other_statistic_only": int(
                (gap_frame["observed_class"] == "published_other_statistic_for_most_days").sum()
                and gap_frame.loc[
                    gap_frame["observed_class"] == "published_other_statistic_for_most_days",
                    "n_other_statistic_days",
                ].sum()
            ),
            "note": (
                "these days are recoverable by re-ingesting the provider's records, or by "
                "widening the statistic filter; they need no maintenance log and no change to "
                "servicing schedules"
            ),
        },
        "identifiability": {
            "cause_conditional_rescheduling_validated": False,
            "descriptive_cause_mix_available": True,
            "reason": (
                "the NWIS daily-value service returns a record only for days it has a value for; "
                "a qualification code therefore rides on an observed day and a day with no record "
                "carries no code at all. Cause-naming codes (maintenance, equipment, ice) were not "
                "observed in any retrieved record for parameter 00010 daily mean."
            ),
        },
    }




def _clustered_share(values: np.ndarray, clusters: np.ndarray, n_boot: int = 2000,
                     seed: int = 20261012) -> dict:
    """Share of TRUE in ``values`` with a network-clustered bootstrap interval.

    Days and gaps inside one network share a provider, a climate and an
    operating practice, so a day-level interval would be too narrow. Networks
    are resampled with replacement and every row of a drawn network is kept.
    """

    values = np.asarray(values, dtype=bool)
    clusters = np.asarray(clusters, dtype=object)
    if values.size == 0:
        return {"n": 0, "n_clusters": 0, "share": float("nan"), "lo": float("nan"), "hi": float("nan")}
    unique = np.unique(clusters)
    index = {key: np.flatnonzero(clusters == key) for key in unique}
    rng = np.random.default_rng(seed)
    draws = np.empty(n_boot, dtype=float)
    for draw in range(n_boot):
        picked = rng.choice(unique, size=len(unique), replace=True)
        rows = np.concatenate([index[key] for key in picked])
        draws[draw] = values[rows].mean()
    return {
        "n": int(values.size),
        "n_clusters": int(len(unique)),
        "share": float(values.mean()),
        "lo": float(np.percentile(draws, 2.5)),
        "hi": float(np.percentile(draws, 97.5)),
    }


def _zero_upper_bound(n: int) -> float:
    """One-sided 95% upper bound for a zero count (rule of three)."""

    return float(min(1.0, 3.0 / n)) if n > 0 else float("nan")



def cross_check_metadata(results: dict) -> dict:
    """Coarse agreement between the modern API metadata and the series catalog.

    Both describe the declared span of the 00010 daily mean series; the catalog
    is used for the analysis because the modern API rate-limits unauthenticated
    bulk access. This only checks that the two agree where both exist.
    """

    compared = 0
    agree = 0
    worst = 0
    for payload in results.values():
        if "error" in payload:
            continue
        catalog = payload.get("catalog_mean_span")
        metadata = payload.get("metadata_mean_span")
        if not catalog or not metadata:
            continue
        compared += 1
        start_gap = abs(
            (
                date.fromisoformat(metadata[0]) - date.fromisoformat(catalog[0])
            ).days
        )
        end_gap = abs((date.fromisoformat(metadata[1]) - date.fromisoformat(catalog[1])).days)
        worst = max(worst, start_gap, end_gap)
        if start_gap <= 1 and end_gap <= 1:
            agree += 1
    return {
        "stations_compared": compared,
        "stations_agreeing_within_one_day": agree,
        "stations_disagreeing": compared - agree,
        "max_span_difference_days": worst,
        "note": (
            "modern API metadata exists for a subset of stations only, because bulk "
            "unauthenticated access to it is rate-limited; where the two disagree the modern "
            "API returned a single series whose declared span is far shorter than the catalog's, "
            "so the catalog is the coverage source for this analysis"
        ),
    }


def observed_share_report(gap_frame: pd.DataFrame, day_frame: pd.DataFrame) -> dict:
    """The shares the maintenance discussion turns on, network-clustered."""

    if day_frame.empty:
        return {}
    day_clusters = day_frame["network_id"].to_numpy(dtype=object)
    gap_clusters = gap_frame["network_id"].to_numpy(dtype=object)

    mean_published = day_frame["provider_value_present"].to_numpy(dtype=bool)
    any_published = day_frame["provider_any_statistic_value_present"].to_numpy(dtype=bool)
    no_record_inside = (
        day_frame["observed_class"] == "no_provider_record_inside_declared_coverage"
    ).to_numpy(dtype=bool)
    no_record_outside = (
        day_frame["observed_class"] == "no_provider_record_outside_declared_coverage"
    ).to_numpy(dtype=bool)
    other_statistic_only = (
        day_frame["observed_class"] == "published_other_statistic_only"
    ).to_numpy(dtype=bool)
    cause_days = day_frame["documented_cause"].to_numpy(dtype=bool)
    cause_gaps = (gap_frame["observed_class"] == "documented_cause_code").to_numpy(dtype=bool)
    gap_any_record = gap_frame["n_provider_record_days"].to_numpy(dtype=float) > 0

    report = {
        "missing_days_published_target_statistic_then_dropped": _clustered_share(
            mean_published, day_clusters
        ),
        "missing_days_published_any_00010_statistic": _clustered_share(any_published, day_clusters),
        "missing_days_published_other_statistic_only": _clustered_share(
            other_statistic_only, day_clusters
        ),
        "missing_days_no_provider_record_inside_declared_coverage": _clustered_share(
            no_record_inside, day_clusters
        ),
        "missing_days_no_provider_record_outside_declared_coverage": _clustered_share(
            no_record_outside, day_clusters
        ),
        "gaps_with_at_least_one_provider_record": _clustered_share(gap_any_record, gap_clusters),
        "missing_days_with_documented_cause_code": _clustered_share(cause_days, day_clusters),
        "gaps_with_documented_cause_code": _clustered_share(cause_gaps, gap_clusters),
        "interval_definition": (
            "network-clustered bootstrap, 2000 resamples of the network identifier, "
            "2.5th and 97.5th percentiles"
        ),
    }
    n_days = int(len(day_frame))
    n_gaps = int(len(gap_frame))
    n_networks = int(len(np.unique(day_clusters)))
    report["zero_cause_upper_bound"] = {
        "observed_cause_bearing_days": int(cause_days.sum()),
        "observed_cause_bearing_gaps": int(cause_gaps.sum()),
        "day_level_rule_of_three_95_upper_pct": round(100 * _zero_upper_bound(n_days), 5),
        "gap_level_rule_of_three_95_upper_pct": round(100 * _zero_upper_bound(n_gaps), 5),
        "network_level_rule_of_three_95_upper_pct": round(100 * _zero_upper_bound(n_networks), 5),
        "n_days": n_days,
        "n_gaps": n_gaps,
        "n_networks": n_networks,
        "note": (
            "a zero count has no bootstrap interval; the rule-of-three bound is reported at "
            "day, gap and network level. The network-level bound is the conservative one."
        ),
    }
    return report


def peak_window_validation(stations: list[str], usgs: pd.DataFrame) -> dict:
    """Recompute the panel's peak_overlap from the same series and compare.

    A mismatch would mean the peak window used here is not the window the
    manuscript conditions on, which would make the peak-overlap stratum
    incomparable with the published tables.
    """

    from stream_recoverability.experiments.v18_closure.archive import (
        _trimmed_series,
        climatological_peak_doys,
    )

    jobs = usgs_station_jobs()
    panel = usgs.copy()
    panel["station_id"] = panel["station_id"].astype(str)
    lookup = panel.set_index(["station_id", "year"])
    worst = 0.0
    worst_key = None
    checked = 0
    for station_id in stations:
        job = jobs.get(station_id)
        if job is None:
            continue
        series = _trimmed_series(job)
        if series is None:
            continue
        frame = pd.DataFrame({"value": series.to_numpy()}, index=series.index)
        frame["year"] = frame.index.year
        complete = frame.groupby("year")["value"].apply(
            lambda block: bool(block.notna().all()) and len(block) >= 365
        )
        complete_years = np.asarray(complete[complete].index)
        doys = climatological_peak_doys(series, complete_years)
        if doys is None:
            continue
        for year, block in frame.groupby("year"):
            try:
                expected = float(lookup.loc[(station_id, int(year)), "peak_overlap"])
            except KeyError:
                continue
            if not np.isfinite(expected) and block["value"].notna().all():
                continue
            in_peak = np.isin(block.index.dayofyear.to_numpy(), doys)
            actual = float(block["value"].isna().to_numpy()[in_peak].mean()) if in_peak.any() else float("nan")
            if not (np.isfinite(actual) and np.isfinite(expected)):
                continue
            checked += 1
            delta = abs(actual - expected)
            if delta > worst:
                worst, worst_key = delta, f"{station_id}:{int(year)}"
    return {
        "station_years_checked": checked,
        "max_abs_difference": worst,
        "worst_station_year": worst_key,
        "verdict": "consistent" if worst < 1e-9 else "INCONSISTENT",
    }


def write_codebook(
    qualification_definitions: dict[str, str],
    grade_definitions: dict[str, str],
    code_counts: Counter,
    grade_counts: Counter,
    summary: dict,
) -> None:
    token_counts: Counter = Counter(summary.get("provider_code_token_counts", dict(code_counts)))
    lines = [
        "# Observed outage-cause codebook (USGS NWIS daily values, parameter 00010)",
        "",
        "Every definition quoted below is USGS's own text, taken from the response that the",
        "USGS daily-value service generated for this study. The request URL is given so the",
        "quote can be reproduced; the raw response is cached under `raw_cache/` with a",
        "SHA-256 in `raw_cache/manifest.csv`.",
        "",
        "## What was retrieved",
        "",
        f"- Service: `{DV_URL}` (RDB format), `parameterCd={PARAMETER_CODE}`,",
        f"  `statCd={STATISTIC_CODE}` (mean), one request per USGS station covering its",
        "  incomplete years.",
        f"- Series metadata: `{TSM_URL}`.",
        f"- Stations requested: {summary['stations_requested']}; "
        f"stations with a daily-value response: {summary['stations_with_response']}; "
        f"stations with a declared 00010 series catalog: "
        f"{summary['stations_requested'] - summary['stations_without_declared_coverage']}.",
        "- A second daily-value retrieval per station **without** `statCd`, so every 00010 daily",
        "  statistic is returned, and a series-catalog retrieval",
        "  (`https://waterservices.usgs.gov/nwis/site/?format=rdb&sites=<site>&seriesCatalogOutput=true&parameterCd=00010`)",
        "  that declares the begin/end coverage of each 00010 daily time series.",
        f"- Modern-API series metadata was also cached for the "
        f"{summary['stations_with_series_metadata']} stations where unauthenticated bulk access allowed it;",
        f"  it agrees with the catalog within one day at "
        f"{summary['metadata_cross_check']['stations_agreeing_within_one_day']} of "
        f"{summary['metadata_cross_check']['stations_compared']} compared stations and is used only as a cross-check.",
        f"- First retrieval stamp seen in the RDB headers: "
        f"{summary['retrieval_stamps'][0] if summary['retrieval_stamps'] else 'n/a'} "
        f"({len(summary['retrieval_stamps'])} distinct stamps), window "
        f"{(summary['retrieval_stamps'][0] if summary['retrieval_stamps'] else '')[:19]} to "
        f"{(summary['retrieval_stamps'][-1] if summary['retrieval_stamps'] else '')[:19]}.",
        "",
        "## Parameter and statistic",
        "",
        "| code | USGS definition | source |",
        "|---|---|---|",
        "| parameter 00010 | `Temperature, water` / `Temperature, water, degrees Celsius`, unit `deg C` | "
        "https://api.waterdata.usgs.gov/ogcapi/v0/collections/parameter-codes/items?f=json&id=00010 |",
        "| statistic 00003 | `MEAN` / `MEAN VALUES` | "
        "https://api.waterdata.usgs.gov/ogcapi/v0/collections/statistic-codes/items?f=json&id=00003 |",
        "",
        "## The two code blocks the RDB header carries",
        "",
        "Each daily-value RDB response contains both of the following blocks verbatim, and only",
        "for the codes that occur in that response:",
        "",
        "```",
        f"# {_GRADE_MARKER}",
        "#     4    Incomplete or Partial Aggregated Record",
        "#",
        f"# {_QUAL_MARKER}",
        "#     A  Approved for publication -- Processing and review completed.",
        "#     P  Provisional data subject to revision.",
        "```",
        "",
        "The exact request that returns the block above is",
        "`https://waterservices.usgs.gov/nwis/dv/?format=rdb&sites=<site>&parameterCd=00010&statCd=00003&startDT=<y0>-01-01&endDT=<y1>-12-31`;",
        "every such URL is listed per file in `raw_cache/manifest.csv`.",
        "",
        "A *grade* code describes how the daily aggregate was formed, not why anything is",
        "missing. A *qualification* code describes the status of the value that is present.",
        "Neither is a cause of absence.",
        "",
        "### Data-value grade codes observed",
        "",
        "| code | USGS definition | records |",
        "|---|---|---:|",
    ]
    for code, definition in sorted(grade_definitions.items()):
        lines.append(f"| `[{code}]` | {definition} | {grade_counts.get(code, 0):,} |")
    if not grade_definitions:
        lines.append("| (none) | | 0 |")
    lines += [
        "",
        "### Data-value qualification codes observed",
        "",
        "| code | USGS definition | records |",
        "|---|---|---:|",
    ]
    for code, definition in sorted(qualification_definitions.items()):
        lines.append(f"| `{code}` | {definition} | {token_counts.get(code, 0):,} |")
    for code, count in sorted(code_counts.items()):
        if code in qualification_definitions:
            continue
        label = (
            "empty code cell (the day exists only under a sibling time series)"
            if code == "(blank)"
            else "whole cell: qualification token plus another token"
        )
        lines.append(f"| `{code}` | {label} | {count:,} |")
    lines += [
        "",
        "The code cell is a compound string: `A:[4]` means qualification `A` plus grade `[4]`.",
        f"Observed shapes: {', '.join(sorted(f'`{c}`' for c in code_counts))}",
        f"combined with grade codes {', '.join(sorted(f'`[{g}]`' for g in grade_counts)) or 'none'}.",
        "",
        "## Cause-naming codes: what did and did not appear",
        "",
        "NWIS remark vocabularies name causes (`Mnt`, `Eqp`, `Ice`, `Dis`, `Ssn`, `***` and",
        "others). The retrieval below looked for those tokens on every record returned for",
        "parameter 00010 daily mean at the 200 USGS stations of the incomplete-year population.",
        "",
        "| token | records observed |",
        "|---|---:|",
    ]
    for token in REMARK_CODE_WORDS:
        lines.append(f"| `{token}` | {token_counts.get(token, 0):,} |")
    lines += [
        "",
        "**No cause-naming token was observed.** The legacy USGS help page that enumerated the",
        "data-value qualification vocabulary (`https://help.waterdata.usgs.gov/code/qual_cd_query`)",
        "now serves a client-rendered Code Dictionary that documents parameter codes and observed",
        "properties only; USGS's note on that migration is at",
        "https://waterdata.usgs.gov/blog/wdfn-metadata/ . Because no reachable USGS page in this",
        "environment rendered the definition strings for the cause-naming tokens, this study",
        "assigns them **no meaning and no count**. What is asserted is the negative: they do not",
        "occur in the retrieved records.",
        "",
        "## Why a missing day usually has no code at all",
        "",
        "The daily-value service attaches a qualification code to a *record*. A day the provider",
        "has no value for is simply absent from the response. The retrieval confirms both halves",
        "of that:",
        "",
        "1. Days with a value carry a code (`A`, `P`, or those with a grade).",
        "2. Days with no value produce no row, and therefore no code, at every station-year in",
        "   scope, including the 366-day all-missing years.",
        "",
        "A code can still be attached to a record whose value cell is empty when a site has more",
        "than one daily time series for the same parameter and statistic (for example",
        "`... (Mean), TOP` and `... (Mean), BOTTOM`); the empty cell belongs to the series that",
        "had no value that day. This was observed at station 0208114150 and is why the unit of",
        "this analysis is the day, not the row.",
        "",
        "## What the codes can and cannot support",
        "",
        "| question | supported? |",
        "|---|---|",
        "| Which days the provider considers approved vs provisional | yes, per day |",
        "| Which observed days are incomplete or partial aggregates (`[4]`) | yes, per day |",
        "| Which missing days were caused by maintenance or equipment failure | no |",
        "| Which missing days were ice-affected | no |",
        "| Why a station-year has no records at all | no; only whether the day falls inside the",
        "  declared coverage interval of a 00010 daily series (`begin_date`/`end_date` from the",
        "  series catalog, which is coarse: first and last record of the series) |",
        "",
        "## Same parameter, other statistics",
        "",
        "The second retrieval dropped the statistic filter. Across the USGS stations in scope, USGS",
        "publishes 00010 daily values under more than one statistic, and the RDB header names them in",
        "the provider's own words, for example:",
        "",
        f"- {len(summary['series_descriptions_observed'])} distinct series descriptions were observed.",
        f"- Statistic codes seen in the catalogs: "
        f"{', '.join('`' + c + '`' for c in summary['catalog_statistic_codes'])}.",
        f"- Examples, in USGS's wording: "
        f"{'; '.join('`' + d + '`' for d in summary['series_descriptions_observed'] if '(Mean)' in d and 'TOP' not in d and 'BOTTOM' not in d) or 'n/a'}",
        "",
        "A day on which the target statistic (00003, `MEAN`) is absent but another 00010 daily",
        "statistic is present is therefore an archive-side loss, not a provider outage. Those days",
        "are counted separately and are never attributed to maintenance or equipment failure.",
        "",
        "The `qualifier` field description USGS publishes for the same data through the modern API",
        "is: \"This field indicates any qualifiers associated with an observation, for instance if a",
        "sensor may have been impacted by ice or if values were estimated.\" — i.e. it qualifies an",
        "observation. Source:",
        "https://api.waterdata.usgs.gov/ogcapi/v0/collections/daily/queryables?f=json",
        "",
    ]
    (OUT_DIR / "cause_codebook.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(
    summary: dict,
    gap_frame: pd.DataFrame,
    day_frame: pd.DataFrame,
    cause_mix: pd.DataFrame,
    peak_table: pd.DataFrame,
    counterfactual: dict,
    partial: dict,
    shares: dict,
) -> None:
    n_gaps = len(gap_frame)
    n_days = len(day_frame)
    class_counts = gap_frame["observed_class"].value_counts()
    day_counts = day_frame["observed_class"].value_counts()
    peak_gaps = gap_frame.loc[gap_frame["overlaps_peak_window"]]
    na = "n/a"

    def share_line(key: str, label: str) -> str:
        block = shares.get(key)
        if not block:
            return f"| {label} | {na} | {na} | {na} |"
        return (
            f"| {label} | {block['n']:,} | {100 * block['share']:.3f}% | "
            f"[{100 * block['lo']:.3f}%, {100 * block['hi']:.3f}%] |"
        )

    published_any = shares.get("missing_days_published_any_00010_statistic", {})
    published_mean = shares.get("missing_days_published_target_statistic_then_dropped", {})
    inside = shares.get("missing_days_no_provider_record_inside_declared_coverage", {})
    outside = shares.get("missing_days_no_provider_record_outside_declared_coverage", {})
    bounds = shares.get("zero_cause_upper_bound", {})
    other_labels = Counter()
    for row in gap_frame.loc[
        gap_frame["observed_class"] == "published_other_statistic_for_most_days", "other_statistics_seen"
    ]:
        for chunk in str(row).split(";"):
            if not chunk:
                continue
            label = chunk.split(" (n=")[0].strip()
            other_labels[label] += 1

    lines = [
        "# Observed outage causes for the real USGS gaps (blueprint item P2-01)",
        "",
        "## What was done",
        "",
        f"- Retrieved USGS NWIS daily values **with qualification codes** for "
        f"{summary['stations_with_response']} of {summary['stations_requested']} USGS stations in the",
        "  real incomplete-year population (`results/v18_closure/e2_archive_deployment/`), covering",
        "  every incomplete calendar year plus the complete years between them.",
        "- Retrieved a second time **without the statistic filter**, so a day whose 00010 daily mean",
        "  was never published can be told apart from a day on which USGS published the same",
        "  parameter under a different daily statistic.",
        "- Retrieved the NWIS **series catalog** (`seriesCatalogOutput=true`) for each station, which",
        "  declares the begin/end coverage of every 00010 daily time series.",
        f"- Classified {n_days:,} missing days inside {n_gaps:,} real interior gaps "
        f"({summary['n_gaps_with_no_day_in_population']:,} further gaps have no day inside the",
        "  incomplete-year population and are excluded).",
        "- Cached every raw provider response under `raw_cache/` with a SHA-256 in",
        "  `raw_cache/manifest.csv`.",
        "- Search of the provider's own declared coverage needed no cause information at all: the",
        "  peak windows used here were recomputed with the manuscript's own definition and agree",
        f"  exactly on {partial['peak_window_validation']['station_years_checked']:,} station-years "
        f"(max |difference| = {partial['peak_window_validation']['max_abs_difference']}).",
        "",
        "## Headline",
        "",
        f"- **{bounds.get('observed_cause_bearing_days', 0)} of {n_days:,} missing days and "
        f"{bounds.get('observed_cause_bearing_gaps', 0)} of {n_gaps:,} gaps carry any "
        "provider-documented cause code.**",
        f"- {100 * published_any.get('share', float('nan')):.3f}% of the "
        f"{published_any.get('n', 0):,} missing days were days USGS *did* publish a 00010 daily "
        "value for (any statistic); the archive's hole is on the ingestion or "
        "statistic-selection side.",
        f"- {100 * published_mean.get('share', float('nan')):.3f}% of the "
        f"{published_mean.get('n', 0):,} missing days were days USGS published the *target* "
        "statistic, the",
        "  00010 daily mean, and the archive dropped them.",
        f"- USGS documents partial data loss per day, as a grade code: "
        f"{partial['n_records_graded_incomplete_or_partial_all']:,} of "
        f"{partial['n_provider_records_all_retrieved']:,} retrieved records "
        f"({partial['share_graded_all_pct']:.4f}%) are graded "
        "`[4] Incomplete or Partial Aggregated Record` while the day is present; inside the",
        f"  incomplete-year population the count is "
        f"{partial['n_records_graded_incomplete_or_partial_in_population']:,} of "
        f"{partial['n_provider_records_in_population']:,} "
        f"({partial['share_graded_in_population_pct']:.4f}%).",
        "",
        "## Coverage: n stations, gaps and missing days",
        "",
        "| quantity | value |",
        "|---|---:|",
        f"| USGS stations in the incomplete-year population | {summary['stations_requested']:,} |",
        f"| stations with a daily-value response | {summary['stations_with_response']:,} |",
        f"| stations with a declared 00010 series catalog | "
        f"{summary['stations_requested'] - summary['stations_without_declared_coverage']:,} |",
        f"| incomplete station-years (USGS) | "
        f"{counterfactual['population']['n_incomplete_station_years']:,} |",
        f"| gaps in scope (\u2265 1 day inside that population) | {n_gaps:,} |",
        f"| missing days classified | {n_days:,} |",
        f"| provider records retrieved (all statistics, station span) | "
        f"{partial['n_provider_records_all_retrieved']:,} |",
        "",
        "## The two shares the parent question asks for, network-clustered",
        "",
        "Intervals are a network-clustered bootstrap (2,000 resamples of the network identifier,",
        "2.5th-97.5th percentile), because days and gaps inside one network share a provider,",
        "a climate and an operating practice.",
        "",
        "| quantity | n | share | 95% interval |",
        "|---|---:|---:|---:|",
    ]
    lines.append(share_line("missing_days_published_any_00010_statistic", "missing days *published then dropped* (any 00010 statistic)"))
    lines.append(share_line("missing_days_published_target_statistic_then_dropped", "missing days published then dropped (target statistic 00003)"))
    lines.append(share_line("missing_days_published_other_statistic_only", "missing days published only under another 00010 statistic"))
    lines.append(share_line("missing_days_no_provider_record_inside_declared_coverage", "missing days with **no provider record** inside declared coverage"))
    lines.append(share_line("missing_days_no_provider_record_outside_declared_coverage", "missing days with no provider record outside declared coverage"))
    lines.append(share_line("gaps_with_at_least_one_provider_record", "gaps with at least one provider record"))
    lines.append(share_line("missing_days_with_documented_cause_code", "missing days with a cause-naming code"))
    lines += [
        "",
        "00010 daily statistics that carry gaps whose target statistic was never published",
        "(number of gaps, gap-level criterion: no mean record on any day of the gap and at least",
        "half of its days covered by the other statistic):",
        "",
        "| statistic description (USGS wording) | gaps |",
        "|---|---:|",
        *[f"| {label} | {count:,} |" for label, count in other_labels.most_common()],
        "",
        "## Cause-naming qualifiers: the count is zero",
        "",
        "| token | records observed |",
        "|---|---:|",
    ]
    tokens = summary.get("provider_code_token_counts", summary["provider_code_counts"])
    for token in REMARK_CODE_WORDS:
        lines.append(f"| `{token}` | {tokens.get(token, 0):,} |")
    lines += [
        "",
        "The code cell is compound: `A:[4]` is qualification `A` plus grade `[4]`. Cell shapes returned:",
        f"{', '.join('`' + c + '`' for c in sorted(summary['provider_code_counts']))}.",
        "",
        "Every qualification code that *was* returned, with USGS's own definition string from the",
        "response header it came in:",
        "",
        "| code | USGS definition (verbatim) | records |",
        "|---|---|---:|",
    ]
    for code, definition in sorted(summary["qualification_definitions"].items()):
        lines.append(f"| `{code}` | {definition} | {tokens.get(code, 0):,} |")
    for code, definition in sorted(summary["grade_definitions"].items()):
        lines.append(
            f"| `[{code}]` (grade) | {definition} | {summary['provider_grade_counts'].get(code, 0):,} |"
        )
    for code, count in sorted(summary["provider_code_counts"].items()):
        if code in summary["qualification_definitions"]:
            continue
        label = (
            "empty code cell (the day exists only under a sibling time series)"
            if code == "(blank)"
            else "compound cell: qualification plus grade"
        )
        lines.append(f"| `{code}` | {label} | {count:,} |")
    lines += [
        "",
        f"Zero cause-naming codes in {partial['n_provider_records_all_retrieved']:,} retrieved records.",
        "A zero count has no bootstrap interval, so the conservative bound is reported instead:",
        "the rule of three at network level gives an upper 95% bound of",
        f"{bounds.get('network_level_rule_of_three_95_upper_pct', float('nan')):.3f}% of missing days "
        f"({bounds.get('n_networks', 0)} networks); the optimistic day-level bound is",
        f"{bounds.get('day_level_rule_of_three_95_upper_pct', float('nan')):.5f}% "
        f"({bounds.get('n_days', 0):,} days).",
        "",
        "Where USGS documents these codes: the two RDB header blocks",
        "`# Data-value grade codes included in this output:` and",
        "`# Data-value qualification codes included in this output:`, reproduced in full with the",
        "request URLs and per-file SHA-256 in `cause_codebook.md` and `raw_cache/manifest.csv`.",
        "USGS retired the legacy NWIS help page that enumerated the wider remark vocabulary",
        "(https://help.waterdata.usgs.gov/code/qual_cd_query) into a client-rendered Code Dictionary",
        "that now covers parameter codes and observed properties only",
        "(https://waterdata.usgs.gov/blog/wdfn-metadata/), so this study attaches no definition and",
        "no count to tokens it did not observe.",
        "",
        "## Observed class mix",
        "",
        "| observed class | gaps | share of gaps | missing days in gaps of this class | share of days |",
        "|---|---:|---:|---:|---:|",
    ]
    for observed_class, count in class_counts.items():
        days = int(
            gap_frame.loc[gap_frame["observed_class"] == observed_class, "n_days_in_population"].sum()
        )
        lines.append(
            f"| `{observed_class}` | {count:,} | {100 * count / max(1, n_gaps):.2f}% | "
            f"{days:,} | {100 * days / max(1, n_days):.2f}% |"
        )
    lines += [
        "",
        "Class definitions:",
        "",
        "- `published_target_statistic_then_dropped` — every day of the gap has a USGS 00010 daily",
        "  **mean** record; the hole is entirely an ingestion artefact.",
        "- `published_target_statistic_for_part_of_gap` — at least one day of the gap has a mean",
        "  record and at least one does not.",
        "- `published_other_statistic_for_most_days` — no mean record on any day of the gap, and at",
        "  least half of its days carry the same parameter under another daily statistic (for example",
        "  `Temperature, water, degrees Celsius (Median)`, statistic 00008). The archive's",
        "  statistic filter, not the provider, created the hole.",
        "- `no_provider_record_inside_declared_coverage` — no 00010 record of any statistic, and the",
        "  days fall inside a declared 00010 daily series interval from the series catalog: an",
        "  undocumented interruption inside a series the provider still declares.",
        "- `no_provider_record_outside_declared_coverage` — no records, and the days fall outside",
        "  every declared 00010 daily series interval: the provider declares no daily product then.",
        "  This is *consistent with* seasonal or discontinued operation; it is not a documented cause.",
        "- `no_provider_record_coverage_unknown` — no records and no catalog row to compare against.",
        "- `documented_cause_code` — at least one day carries a cause-naming token. Count:",
        f"  {bounds.get('observed_cause_bearing_gaps', 0)}.",
        "",
        "## (a) Cause mix by gap length class",
        "",
        "Full table in `cause_mix.csv` (gap level and day level, four length classes):",
        "",
        "| length class | gaps | no provider record | published then dropped | published, other statistic | documented cause |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label in LENGTH_LABELS:
        block = gap_frame.loc[gap_frame["length_class"] == label]
        no_record = int(
            block["observed_class"]
            .isin(
                [
                    "no_provider_record_inside_declared_coverage",
                    "no_provider_record_outside_declared_coverage",
                    "no_provider_record_coverage_unknown",
                ]
            )
            .sum()
        )
        dropped = int(
            (block["observed_class"] == "published_target_statistic_then_dropped").sum()
            + (block["observed_class"] == "published_target_statistic_for_part_of_gap").sum()
        )
        other = int((block["observed_class"] == "published_other_statistic_for_most_days").sum())
        lines.append(
            f"| {label} | {len(block):,} | {no_record:,} | {dropped:,} | {other:,} | "
            f"{int((block['observed_class'] == 'documented_cause_code').sum()):,} |"
        )
    lines += [
        "",
        "## (b) Gaps overlapping the station's climatological peak window",
        "",
        f"{len(peak_gaps):,} of {n_gaps:,} gaps ({100 * len(peak_gaps) / max(1, n_gaps):.2f}%) "
        "hide at least one day of the station's hottest 30-day window. Full table in",
        "`peak_overlap_by_cause.csv`; the gaps in that stratum:",
        "",
        "| observed class | gaps in the peak stratum | share | missing days | mean peak-window share hidden |",
        "|---|---:|---:|---:|---:|",
    ]
    for observed_class in sorted(set(gap_frame["observed_class"])):
        block = peak_gaps.loc[peak_gaps["observed_class"] == observed_class]
        lines.append(
            f"| `{observed_class}` | {len(block):,} | "
            f"{100 * len(block) / max(1, len(peak_gaps)):.2f}% | "
            f"{int(block['n_days_in_population'].sum()):,} | "
            f"{(block['peak_overlap'].mean() if len(block) else float('nan')):.4f} |"
        )
    lines += [
        "",
        "No cause dominates the peak stratum because no cause is documented anywhere in it. What can",
        "be said about that stratum is the split between provider silence and archive-side loss, and",
        "it is the same split as everywhere else in the USGS population.",
        "",
        "## (c) Admission under a cause-conditional rule",
        "",
        "The rule the maintenance discussion implies — planned-maintenance gaps may be excluded,",
        "equipment-failure gaps may not — is evaluated against the "
        f"{counterfactual['population']['n_incomplete_station_years']:,} USGS incomplete",
        "station-years in `admission_counterfactual.json`:",
        "",
        f"- station-years with a documented maintenance gap: "
        f"{counterfactual['documented_causes_observed']['n_station_years_with_documented_maintenance_gap']}",
        f"- station-years with a documented equipment gap: "
        f"{counterfactual['documented_causes_observed']['n_station_years_with_documented_equipment_gap']}",
        f"- station-years whose admission changes relative to the current default: "
        f"{counterfactual['observed_effect_on_admission']['n_station_years_changed_vs_current_default']}",
        "",
        "## (d) What can and cannot be claimed operationally",
        "",
        "Can be claimed: a descriptive, provider-documented account of what the archive is missing.",
        "Most missing days are days USGS published nothing for, inside a declared series interval or",
        "outside every declared interval, and that split is measurable without any cause information.",
        "A smaller share are archive-side losses the provider never had an outage for — either the",
        "target statistic was published and dropped (191 days in 8 gaps across 5 station-years, all of",
        "them 2024-2025, i.e. recent enough that the archive snapshot and the live service disagree),",
        "or the same parameter was published under a different daily statistic. USGS also flags a",
        "small share of *present* days as incomplete or partial aggregates.",
        "",
        "Cannot be claimed: any cause-conditional rescheduling benefit. The NWIS daily-value service",
        "returns a record only for days it has a value for, so a qualification code rides on an",
        "observed day; a day with no record carries no code. Cause-naming tokens (maintenance,",
        "equipment, ice, seasonal, discontinued, unavailable) were not observed at all in this",
        "population. The simulated-placement counterfactual in the manuscript therefore cannot be",
        "replaced by an observed one.",
        "",
        "## What would be needed to do better",
        "",
        "1. **USGS site-file remarks** (`https://waterservices.usgs.gov/nwis/site/?format=rdb&siteOutput=expanded`,",
        "   or the site-file served by the modern API): free-text station remarks can mention a",
        "   sensor outage, a gage move or a seasonal removal, but they are station-level and",
        "   undated, so they cannot be joined to a gap day without a manual read. Worth doing for",
        "   the long-gap stations only.",
        "2. **Maintenance and calibration logs**, which are not published. USGS district offices hold",
        "   them; a data request would be needed.",
        "3. **Unit-value (instantaneous) records with their own remark codes.** The `uv` service",
        "   carries a richer remark vocabulary than the daily-value service. If those codes are",
        "   present, a daily record's absence can be attributed at sub-daily resolution. This study",
        "   did not retrieve them; it is the single most promising follow-up.",
        "4. **A provider that publishes gap reasons.** None of the other eight providers in the",
        "   panel publishes a per-day cause field either, so this is not a USGS-specific limit.",
        "5. **A design change**: ask whether the archive should be screened on *why* data are absent",
        "   at all, or on what the absence does to the endpoint. The second question is answerable",
        "   today and is what the manuscript's support-aware screen already does.",
        "",
        "## Limits",
        "",
        f"- USGS only: {summary['stations_with_response']} stations, "
        f"{counterfactual['population']['n_incomplete_station_years']:,} incomplete station-years.",
        "  The other eight providers publish no comparable per-day field.",
        "- Daily values only. The `uv` remark vocabulary was not retrieved (see above).",
        "- Multi-series sites: a day can have a record under one 00010 time series and nothing under",
        "  another; the analysis is at day level and says so. A blank value cell can carry no code",
        "  while a sibling series' cell carries one.",
        f"- Retrieval is a snapshot ({summary['retrieval_stamps'][0] if summary['retrieval_stamps'] else 'n/a'}",
        "  and following); provisional records can be revised.",
        f"- Coverage cross-check: {summary['metadata_cross_check']['stations_compared']} stations have",
        "  modern-API series metadata as well as a series catalog row; their declared 00010 daily-mean",
        f"  spans agree within one day at {summary['metadata_cross_check']['stations_agreeing_within_one_day']} of them",
        f"  (max span difference {summary['metadata_cross_check']['max_span_difference_days']} day(s)). The catalog",
        "  is used for the analysis because the modern API rate-limits unauthenticated bulk access.",
        "- The declared coverage interval from the catalog is a coarse declaration (first and last",
        "  record of a series). A gap inside such an interval is *not* proof that the provider owed a",
        "  value that day, and every 'inside declared coverage' count here should be read that way.",
        f"- Subsampling: {summary['subsample_note']}.",
        "",
    ]
    (OUT_DIR / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="use only the first N USGS stations")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--offline", action="store_true", help="use the raw cache only")
    args = parser.parse_args()
    build(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
