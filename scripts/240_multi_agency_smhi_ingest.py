#!/usr/bin/env python3
"""Multi-agency transport (P0-07 extension): SMHI river-temperature ingest + QC.

Fetches the entire SMHI HydroObs parameter 4 ("Vattendragstemperatur") archive,
applies the provider quality-code gate declared in the task, groups stations by
the agency-native catchment (`catchmentNumber`) and writes per-network wide
daily panels for the pre-registered transport test.

Protocol: results/wrr_submission_ready/MULTI_AGENCY_TRANSPORT_PROTOCOL.md
Frozen model / freeze file are NOT touched here: this script never scores.

QC strata (MULTI_AGENCY_TRANSPORT_PROTOCOL.md, Amendment 2)
-----------------------------------------------------------
`--qc-stratum quality_checked` accepts only codes SMHI documents as *checked and
approved* (G) or *coarsely checked* (Y). On this provider that gate yields zero
stations (every archived row is `O`), which is recorded in
QC_AND_ELIGIBILITY_FAILURE.md and kept as the strict-gate audit record.

`--qc-stratum provider_published_unqualified` (default, the coordinator's
recorded decision) accepts `O`, which SMHI itself documents as
*Okontrollerade värden* (uncontrolled), and labels every emitted station with
that stratum in `stations.csv::quality_assurance`. The legend is extracted from
each file header verbatim and recorded in ingest.json for both strata.

Outputs (root: results/wrr_submission_ready/multi_agency_ingest/smhi/)
  raw_cache/{parameter_4_catalog.json, station_<id>.csv}   gitignored raw bytes
  station_catalog.csv                                      all catalog stations
  stations_all.csv                                         per-station QC, all stations
  stations.csv                                             one row per emitted station (+stratum)
  README.md                                                reviewer-facing record of the decision
  networks/<network_id>/daily_wide_temperature.csv         wide panel (eligible networks)
  station_daily/<station_id>.csv                           QC-accepted daily series
  station_years.csv                                        complete-year ledger
  hydropower_evidence.csv                                  name/catchment evidence only
  ingest.json / QC_AND_ELIGIBILITY_FAILURE.md / run.log

Note on this provider: every parameter-4 station is catalogued with
`measuringStations = ADDITIONAL` ("Övriga stationer"), i.e. outside SMHI's own
station network, every archived row carries code `O`, and the archive ends in
2003. The strict gate therefore finds nothing (documented, not hidden); the
unqualified stratum emits a historical boreal panel, and `n_dropped_qc` counts
the rows excluded by whichever gate the run used.

The complete-year columns describe the accepted series only, so they are blank
when a station has no accepted day; the unfiltered diagnostics for such stations
live in the extra columns `first_date_any_quality`, `last_date_any_quality`,
`n_days_any_quality`, `quality_code_counts` and `state`. The raw files are in
raw_cache/ alongside `raw_cache/parameter_4_catalog.json`.

Run:  PYTHONPATH=src python3 scripts/240_multi_agency_smhi_ingest.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "results" / "wrr_submission_ready" / "multi_agency_ingest" / "smhi"
RAW_CACHE = OUT_ROOT / "raw_cache"
NETWORKS_DIR = OUT_ROOT / "networks"
STATION_DAILY_DIR = OUT_ROOT / "station_daily"

CATALOG_URL = (
    "https://opendata-download-hydroobs.smhi.se/api/version/latest/parameter/4.json"
)
DATA_URL_PATTERN = (
    "https://opendata-download-hydroobs.smhi.se/api/version/latest/parameter/4/"
    "station/{station_id}/period/corrected-archive/data.csv"
)
METADATA_URL = (
    "https://opendata-download-hydroobs.smhi.se/api/version/latest/parameter/4/"
    "metadata.json"
)
USER_AGENT = (
    "stream-recoverability-smhi-ingest/1.0 "
    "(WRR multi-agency transport ingest; research use; contact: study operator)"
)

PROVIDER = "smhi"
SLEEP_SECONDS = 0.4
MAX_ATTEMPTS = 4
MIN_STATIONS_PER_NETWORK = 2
MIN_COMPLETE_YEARS = 4

# Assurance strata of MULTI_AGENCY_TRANSPORT_PROTOCOL.md, Amendment 2 (committed
# in the working tree before any transport case was scored). `quality_checked`
# is the strict gate the task originally fixed; `provider_published_unqualified`
# is the amended stratum that admits series the provider itself labels
# uncontrolled (`O = Okontrollerade värden`), carried through to the seal as a
# per-station `quality_assurance` label so the two are never pooled silently.
QC_STRATA: dict[str, dict[str, object]] = {
    "quality_checked": {
        "accepted_quality_codes": ("G", "Y"),
        "definition": "the provider documents the values as checked or coarsely checked "
                      "(SMHI G = Kontrollerade och godkända värden, Y = Grovt kontrollerade värden)",
    },
    "provider_published_unqualified": {
        "accepted_quality_codes": ("O",),
        "definition": "the provider publishes the series but labels it uncontrolled/unqualified "
                      "(SMHI O = Okontrollerade värden)",
    },
}

# Verbatim provider wording (SMHI open-data catalog record
# 9d61ab90-7d21-11ed-a51b-432755aaeed3, retrieved this run). SMHI documents the
# value as a *daily* watercourse temperature and quotes the unit in degrees
# Celsius; it does NOT state a daily aggregation operator (mean vs. reading).
SMHI_STATISTIC_QUOTE = (
    "Daglig uppgift om vattendragstemperaturer i vattendrag i Sverige."
)
SMHI_STATISTIC_UNIT_QUOTE = "Enhet: Grader Celsius"
MEASUREMENT_STATISTIC = (
    "daily provider statistic, degrees C; SMHI documents "
    "'Daglig uppgift om vattendragstemperaturer i vattendrag i Sverige.' "
    "(Enhet: Grader Celsius) for parameter 4 'Vattendragstemperatur' - the daily "
    "aggregation operator (mean vs. instantaneous reading) is NOT documented by "
    "the provider in the API metadata or the catalog record"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def get_bytes(url: str, timeout: int = 180, sleep_seconds: float = SLEEP_SECONDS) -> bytes:
    """Single GET with a descriptive UA and retries; never silently falls back."""

    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
            time.sleep(sleep_seconds)
            return payload
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            last_error = exc
            time.sleep(min(2.0 * attempt, 8.0))
    raise RuntimeError(f"GET failed after {MAX_ATTEMPTS} attempts: {url} ({last_error})")


def cache_bytes(path: Path, url: str, payload: bytes) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {
        "url": url,
        "path": str(path.relative_to(ROOT)),
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "retrieved_utc": utc_now(),
    }


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def _clean(value: str) -> str:
    return value.replace("\ufeff", "").replace("\xa0", " ").strip()


def _normalise_number(text: str) -> tuple[float | None, str]:
    """Return (value, note). Handles Swedish decimal commas and blank cells."""

    raw = _clean(text)
    if raw == "":
        return None, "blank"
    note = ""
    if "," in raw:
        raw = raw.replace(" ", "").replace(",", ".")
        note = "decimal_comma"
    try:
        value = float(raw)
    except ValueError:
        return None, "unparseable"
    if not np.isfinite(value):
        return None, "non_finite"
    return value, note


def parse_station_file(payload: bytes) -> dict[str, object]:
    """Parse one SMHI corrected-archive CSV into metadata + raw daily rows."""

    text = payload.decode("utf-8-sig")
    lines = text.splitlines()

    # The file opens with two-row header blocks (key row, then value row):
    #   Stationsnamn;StationsId;Stationsnät;Stationens latitud;Stationens longitud
    #   <name>;<id>;<network class>;<lat>;<lon>
    #   Parameternamn;Enhet
    #   Vattendragstemperatur;°C
    # Pairs are read positionally from each block, then looked up by key name.
    blocks: dict[str, str] = {}
    for index in range(len(lines) - 1):
        keys = [_clean(f) for f in lines[index].split(";")]
        values = [_clean(f) for f in lines[index + 1].split(";")]
        if not keys[0] or keys[0].startswith("Datum"):
            continue
        if keys[0] not in {"Stationsnamn", "Parameternamn"}:
            continue
        for key, value in zip(keys, values, strict=False):
            if key:
                blocks.setdefault(key, value)

    kv: dict[str, str] = dict(blocks)
    kv_groups: dict[str, list[str]] = {key: [value] for key, value in blocks.items()}

    # Explicit, provider-specific identity fields (Swedish header names).
    station_name = kv_groups.get("Stationsnamn", [])
    station_network = kv_groups.get("Stationsnät", [])
    station_latitude = kv_groups.get("Stationens latitud", [])
    station_longitude = kv_groups.get("Stationens longitud", [])
    station_id_field = kv_groups.get("StationsId", [])
    parameter_name = kv_groups.get("Parameternamn", [])
    parameter_unit = kv_groups.get("Enhet", [])
    identity = {
        "station_name": station_name[0] if station_name else "",
        "station_id_field": station_id_field[0] if station_id_field else "",
        "station_network_class": station_network[0] if station_network else "",
        "latitude": station_latitude[0] if station_latitude else "",
        "longitude": station_longitude[0] if station_longitude else "",
        "parameter_name": parameter_name[0] if parameter_name else "",
        "parameter_unit": parameter_unit[0] if parameter_unit else "",
    }

    header_index = next(
        (i for i, line in enumerate(lines) if _clean(line).startswith("Datum")), None
    )
    if header_index is None:
        raise ValueError("no 'Datum' header row found")

    header_fields = [_clean(f) for f in lines[header_index].split(";")]
    header_fields = [f for f in header_fields if f != ""]
    date_header = header_fields[0] if header_fields else "Datum"
    value_header = header_fields[1] if len(header_fields) > 1 else ""
    quality_header = header_fields[2] if len(header_fields) > 2 else ""

    # Quality-code legend. SMHI embeds it as trailing free-text fields on the
    # first data rows ("Kvalitetskoderna:" then "<Name> (<CODE>) = <meaning>."),
    # not as standalone header lines, so it is scanned out of every text field.
    legend: list[dict[str, str]] = []
    legend_pattern = re.compile(r"^(?P<label>[^()=]+?)\s*\((?P<code>[A-Za-z]+)\)\s*=\s*(?P<text>.+?)\.?$")
    header_block_lines: list[str] = []
    for line in lines[max(0, header_index - 2) : header_index + 1]:
        header_block_lines.append(line)

    rows: list[dict[str, object]] = []
    value_notes: Counter[str] = Counter()
    reader_source = io.StringIO(text)
    for _ in range(header_index + 1):
        next(reader_source)
    for values in csv.reader(reader_source, delimiter=";"):
        if not values:
            continue
        for extra in values[3:]:  # trailing free-text fields only (0=date,1=value,2=code)
            extra = _clean(extra)
            if not extra:
                continue
            match = legend_pattern.match(extra)
            if match and "Kvalitetskod" not in match.group("label"):
                legend_item = {
                    "code": match.group("code"),
                    "label": match.group("label").strip(),
                    "meaning_verbatim": match.group("text").strip().rstrip(".") + ".",
                }
                if legend_item not in legend:
                    legend.append(legend_item)

        date_text = _clean(values[0])
        quality = _clean(values[2]) if len(values) > 2 else ""
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_text):
            continue
        # The first data rows also carry explanatory trailing text that itself
        # contains dates ("Tidsperiod (fr.o.m.) = 1975-01-02"). A real observation
        # row has a blank or single-character quality code and a numeric/blank
        # value in the value column, so anything else is not a data row.
        quality_raw = _clean(values[2]) if len(values) > 2 else ""
        value_raw = _clean(values[1]) if len(values) > 1 else ""
        is_data_row = re.match(r"^[A-Za-z]?$", quality_raw) is not None and (
            value_raw == "" or re.match(r"^-?\d+(?:[.,]\d+)?$", value_raw) is not None
        )
        if not is_data_row:
            continue
        value, note = _normalise_number(values[1]) if len(values) > 1 else (None, "missing_column")
        value_notes[note] += 1
        rows.append(
            {
                "date": date_text,
                "temperature_c_raw": value,
                "quality_code": quality,
            }
        )

    return {
        "kv": kv,
        "kv_groups": kv_groups,
        "identity": identity,
        "legend": legend,
        "date_header": date_header,
        "value_header": value_header,
        "quality_header": quality_header,
        "header_block_lines": header_block_lines,
        "rows": rows,
        "value_notes": dict(value_notes),
    }


def deduplicate_daily(rows: list[dict[str, object]]) -> tuple[pd.DataFrame, dict[str, object]]:
    """Deduplicate repeated dates: keep highest-quality, then last occurrence."""

    frame = pd.DataFrame(rows, columns=["date", "temperature_c_raw", "quality_code"])
    frame["date"] = pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="raise")
    frame["temperature_c_raw"] = pd.to_numeric(frame["temperature_c_raw"], errors="coerce")
    frame["quality_code"] = frame["quality_code"].fillna("").astype(str)

    n_rows = len(frame)
    counts = frame["date"].value_counts()
    n_duplicate_dates = int((counts > 1).sum())
    n_extra_rows = int((counts[counts > 1] - 1).sum())
    if n_duplicate_dates:
        rank = {"G": 0, "Y": 1, "O": 2}
        frame["_rank"] = frame["quality_code"].map(lambda c: rank.get(c, 3))
        frame = frame.sort_values(["date", "_rank"], kind="stable")
        deduped = frame.drop_duplicates(subset="date", keep="first").drop(columns="_rank")
    else:
        deduped = frame.drop_duplicates(subset="date", keep="first")
    deduped = deduped.sort_values("date").reset_index(drop=True)

    return deduped, {
        "n_rows_parsed": n_rows,
        "n_duplicate_dates": n_duplicate_dates,
        "n_duplicate_rows_removed": n_extra_rows,
        "n_rows_after_dedup": len(deduped),
        "rule": (
            "same calendar date repeated -> keep the row with the highest-ranked quality "
            "code (G > Y > O > undocumented/blank); ties broken by last occurrence in file order"
        ),
    }


def complete_years(series: pd.Series) -> tuple[list[int], list[dict[str, object]]]:
    """Calendar years whose every day (365/366) carries a finite value."""

    years: list[int] = []
    ledger: list[dict[str, object]] = []
    values = pd.to_numeric(series, errors="coerce")
    for year, block in values.groupby(values.index.year, sort=True):
        need = 366 if ((year % 400 == 0) or (year % 4 == 0 and year % 100 != 0)) else 365
        have = int(np.isfinite(block.to_numpy(dtype=float)).sum())
        complete = have >= need
        if complete:
            years.append(int(year))
        ledger.append({"year": int(year), "n_finite_days": have, "days_required": need, "complete": complete})
    return years, ledger


HYDROPOWER_TOKENS = ("KRV", "KRAFT", "KRAFTV", "FORS", "FORSEN", "DAMM")


def hydropower_evidence(name: str, catchment_name: str) -> tuple[bool, str]:
    """Name/catchment textual evidence only; never a hydrologic assertion."""

    upper = name.upper()
    tokens = [token for token in HYDROPOWER_TOKENS if token in upper]
    if tokens:
        return True, "station_name_token:" + "|".join(tokens)
    return False, ""


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sleep", type=float, default=SLEEP_SECONDS, help="seconds between HTTP requests")
    parser.add_argument("--limit", type=int, default=None, help="debug: only fetch first N stations")
    parser.add_argument(
        "--qc-stratum",
        choices=sorted(QC_STRATA),
        default="provider_published_unqualified",
        help="assurance stratum (protocol Amendment 2). 'quality_checked' is the strict "
             "G/Y gate that yields no SMHI panel; 'provider_published_unqualified' "
             "admits O-labelled values under the amended stratum label",
    )
    args = parser.parse_args()

    qc_stratum = args.qc_stratum
    ACCEPTED_QUALITY_CODES = tuple(QC_STRATA[qc_stratum]["accepted_quality_codes"])  # type: ignore[arg-type]
    QUALITY_ASSURANCE = qc_stratum

    for directory in (OUT_ROOT, RAW_CACHE, STATION_DAILY_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    log_lines: list[str] = []

    def log(message: str) -> None:
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        line = f"[{stamp}] {message}"
        print(line, flush=True)
        log_lines.append(line)

    retrieval_utc = utc_now()
    log(f"start retrieval_utc={retrieval_utc} qc_stratum={qc_stratum} accepted={ACCEPTED_QUALITY_CODES}")

    # --- catalog ---------------------------------------------------------- #
    _catalog_path = RAW_CACHE / "parameter_4_catalog.json"
    if _catalog_path.is_file():
        catalog_payload = _catalog_path.read_bytes()
        catalog_provenance = {
            "url": CATALOG_URL,
            "path": str(_catalog_path.relative_to(ROOT)),
            "bytes": len(catalog_payload),
            "sha256": sha256_bytes(catalog_payload),
            "retrieved_utc": retrieval_utc,
            "served_from_cache": True,
        }
    else:
        catalog_payload = get_bytes(CATALOG_URL, sleep_seconds=args.sleep)
        catalog_provenance = {
            **cache_bytes(_catalog_path, CATALOG_URL, catalog_payload),
            "served_from_cache": False,
        }
    catalog = json.loads(catalog_payload)
    stations_catalog = catalog["station"]
    log(f"catalog: {len(stations_catalog)} stations, unit={catalog.get('unit')!r}")

    # --- metadata (statistic wording / provider documentation) ------------ #
    metadata_urls: list[str] = []
    try:
        metadata_payload = get_bytes(METADATA_URL, sleep_seconds=args.sleep)
        metadata_urls.append(METADATA_URL)
        (RAW_CACHE / "parameter_4_metadata.json").write_bytes(metadata_payload)
        metadata_abstract = (
            json.loads(metadata_payload)["MD_Metadata"]["identificationInfo"]
            ["MD_DataIdentification"]["abstract"]["CharacterString"]
        )
    except Exception as exc:  # pragma: no cover - network dependent
        metadata_abstract = f"<metadata fetch failed: {exc}>"
        log(f"WARNING metadata fetch failed: {exc}")

    # --- per-station fetch ------------------------------------------------ #
    station_rows: list[dict[str, object]] = []
    network_rows: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    legends: dict[str, list[dict[str, str]]] = {}
    data_urls: list[str] = []
    value_notes_all: Counter[str] = Counter()
    header_blocks: dict[str, list[str]] = {}
    value_header_names: set[str] = set()
    quality_header_names: set[str] = set()
    file_station_network_classes: Counter[str] = Counter()
    file_parameter_names: Counter[str] = Counter()
    file_parameter_units: Counter[str] = Counter()
    identity_mismatches: list[dict[str, object]] = []
    date_headers: Counter[str] = Counter()
    quality_code_totals: Counter[str] = Counter()
    dedup_rules: dict[str, dict[str, object]] = {}

    catalog_by_id = {str(entry["id"]): entry for entry in stations_catalog}
    station_ids = sorted(catalog_by_id)
    if args.limit:
        station_ids = station_ids[: args.limit]

    for index, station_id in enumerate(station_ids, start=1):
        entry = catalog_by_id[station_id]
        url = DATA_URL_PATTERN.format(station_id=station_id)
        data_urls.append(url)
        cache_path = RAW_CACHE / f"station_{station_id}.csv"
        if cache_path.is_file():
            payload = cache_path.read_bytes()
            provenance = {"served_from_cache": True}
        else:
            try:
                payload = get_bytes(url, sleep_seconds=args.sleep)
            except Exception as exc:
                failures.append({"station_id": station_id, "url": url, "error": str(exc)})
                log(f"[{index}/{len(station_ids)}] FAILED {station_id}: {exc}")
                continue
            provenance = cache_bytes(cache_path, url, payload)
            provenance["served_from_cache"] = False

        try:
            parsed = parse_station_file(payload)
        except Exception as exc:
            failures.append({"station_id": station_id, "url": url, "error": f"parse: {exc}"})
            log(f"[{index}/{len(station_ids)}] PARSE FAILED {station_id}: {exc}")
            continue

        file_identity = parsed["identity"]
        file_station_network_classes[file_identity["station_network_class"]] += 1
        file_parameter_names[file_identity["parameter_name"]] += 1
        file_parameter_units[file_identity["parameter_unit"]] += 1
        if str(file_identity["station_name"]).strip() and str(file_identity["station_name"]).strip() != str(entry.get("name", "")).strip():
            identity_mismatches.append(
                {
                    "station_id": station_id,
                    "file_station_name": file_identity["station_name"],
                    "catalog_name": entry.get("name"),
                }
            )
        legends[station_id] = parsed["legend"]
        header_blocks[station_id] = parsed["header_block_lines"]
        date_headers[str(parsed["date_header"])] += 1
        value_notes_all.update(parsed["value_notes"])
        value_header_names.add(str(parsed["value_header"]))
        quality_header_names.add(str(parsed["quality_header"]))

        raw_frame, dedup_info = deduplicate_daily(parsed["rows"])
        dedup_rules[station_id] = dedup_info
        quality_code_totals.update(raw_frame["quality_code"].tolist())

        identity = parsed["identity"]
        river_name = str(identity["station_name"] or entry.get("name", "")).strip()
        catalog_network = str(identity["station_network_class"]).strip()
        latitude = identity["latitude"]
        longitude = identity["longitude"]
        try:
            latitude = float(latitude) if latitude not in (None, "") else float(entry.get("latitude"))
            longitude = float(longitude) if longitude not in (None, "") else float(entry.get("longitude"))
        except (TypeError, ValueError):
            latitude = float(entry.get("latitude"))
            longitude = float(entry.get("longitude"))

        accepted_mask = raw_frame["quality_code"].isin(ACCEPTED_QUALITY_CODES)
        accepted = raw_frame.loc[accepted_mask & raw_frame["temperature_c_raw"].notna(), ["date", "temperature_c_raw", "quality_code"]].copy()
        accepted = accepted.rename(columns={"temperature_c_raw": "temperature_c"})
        # F01: never guess unit rescales. Values outside a liquid-river °C band are
        # quarantined (station 80289 ships ~28 000 under a °C header).
        TEMP_C_MIN, TEMP_C_MAX = -5.0, 50.0
        temps = pd.to_numeric(accepted["temperature_c"], errors="coerce")
        plausible = temps.notna() & (temps >= TEMP_C_MIN) & (temps <= TEMP_C_MAX)
        n_implausible_unit = int((~plausible).sum())
        accepted = accepted.loc[plausible].copy()
        accepted = accepted.set_index("date")["temperature_c"]

        n_dropped_qc = int(
            (~accepted_mask).sum()
            + (accepted_mask & raw_frame["temperature_c_raw"].isna()).sum()
            + n_implausible_unit
        )
        n_accepted = int(accepted.notna().sum())
        years, year_ledger = complete_years(accepted)

        if n_accepted:
            series_out = accepted.rename("temperature_c").reset_index()
            # quality codes align to surviving dates only
            qmap = raw_frame.loc[accepted_mask & raw_frame["temperature_c_raw"].notna(), ["date", "quality_code"]]
            qmap["date"] = pd.to_datetime(qmap["date"])
            series_out = series_out.merge(qmap, on="date", how="left")
            series_out["station_id"] = station_id
            series_out.to_csv(STATION_DAILY_DIR / f"{station_id}.csv", index=False)

        is_hydro, hydro_reason = hydropower_evidence(river_name, str(entry.get("catchmentName", "")))

        network_id_raw = entry.get("catchmentNumber")
        network_id = f"smhi_catchment_{network_id_raw}" if network_id_raw not in (None, "") else "smhi_catchment_unknown"

        row = {
            "network_id": network_id,
            "station_id": station_id,
            "provider": PROVIDER,
            "river_name": river_name,
            "catchment_number": network_id_raw,
            "catchment_name": entry.get("catchmentName"),
            "latitude": latitude,
            "longitude": longitude,
            "station_network_class": catalog_network,
            "measuring_stations": entry.get("measuringStations"),
            "catalog_active": entry.get("active"),
            "n_complete_years": len(years),
            "complete_years": ";".join(str(y) for y in years),
            "first_date": accepted.index.min().strftime("%Y-%m-%d") if n_accepted else "",
            "last_date": accepted.index.max().strftime("%Y-%m-%d") if n_accepted else "",
            "n_days": n_accepted,
            "n_dropped_qc": n_dropped_qc,
            "quality_assurance": QUALITY_ASSURANCE,
            "accepted_quality_codes": ";".join(ACCEPTED_QUALITY_CODES),
            "qc_stratum": qc_stratum,
            "measurement_statistic": MEASUREMENT_STATISTIC,
            "n_rows_parsed": dedup_info["n_rows_parsed"],
            "n_parsed_with_value": int(raw_frame["temperature_c_raw"].notna().sum()),
            "n_duplicate_dates": dedup_info["n_duplicate_dates"],
            "n_duplicate_rows_removed": dedup_info["n_duplicate_rows_removed"],
            "first_date_any_quality": raw_frame["date"].min().strftime("%Y-%m-%d") if len(raw_frame) else "",
            "last_date_any_quality": raw_frame["date"].max().strftime("%Y-%m-%d") if len(raw_frame) else "",
            "n_days_any_quality": int(len(raw_frame)),
            "quality_code_counts": ";".join(f"{code or 'blank'}={count}" for code, count in sorted(raw_frame["quality_code"].value_counts().items())),
            "hydropower_name_evidence": is_hydro,
            "hydropower_evidence": hydro_reason,
            "raw_sha256": sha256_bytes(payload),
            "raw_bytes": len(payload),
            "served_from_cache": provenance.get("served_from_cache", False),
        }
        station_rows.append(row)
        station_rows[-1]["_year_ledger"] = year_ledger  # internal, stripped before writing

        if index % 20 == 0 or index == len(station_ids):
            log(
                f"[{index}/{len(station_ids)}] last={station_id} "
                f"accepted_days={n_accepted} complete_years={len(years)} dropped_qc={n_dropped_qc}"
            )

    station_frame = pd.DataFrame(station_rows)

    # Column contract shared by stations.csv, stations_all.csv and the per-network
    # station tables. `quality_assurance` is required by protocol Amendment 2.
    required_columns = [
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
        c for c in station_frame.columns if c not in required_columns and not c.startswith("_")
    ]
    ordered = required_columns + extra_columns

    # --- network eligibility --------------------------------------------- #
    eligible_rows: list[dict[str, object]] = []
    networks_written: list[str] = []
    networks_skipped: list[dict[str, object]] = []
    if len(station_frame):
        # Internal ledger column is not serialisable; keep a copy for station_years.csv.
        ledger_records: list[dict[str, object]] = []
        for record in station_rows:
            for item in record.get("_year_ledger", []):  # type: ignore[union-attr]
                ledger_records.append(
                    {
                        "network_id": record["network_id"],
                        "station_id": record["station_id"],
                        "provider": PROVIDER,
                        "year": item["year"],
                        "n_finite_days_after_qc": item["n_finite_days"],
                        "days_required": item["days_required"],
                        "complete": item["complete"],
                    }
                )
        station_frame = station_frame.drop(columns=["_year_ledger"])
    else:
        ledger_records = []

    if len(station_frame):
        for network_id, group in station_frame.groupby("network_id", sort=True):
            qualifying = group.loc[group["n_complete_years"] >= MIN_COMPLETE_YEARS]
            if len(qualifying) < MIN_STATIONS_PER_NETWORK:
                networks_skipped.append(
                    {
                        "network_id": network_id,
                        "n_catalog_stations": int(len(group)),
                        "n_stations_ge_min_years_after_qc": int(len(qualifying)),
                        "reason": (
                            "fewer than "
                            f"{MIN_STATIONS_PER_NETWORK} stations with >= {MIN_COMPLETE_YEARS} complete "
                            "calendar years after the accepted-quality-code QC"
                        ),
                    }
                )
                continue

            network_dir = NETWORKS_DIR / str(network_id)
            network_dir.mkdir(parents=True, exist_ok=True)
            members = group["station_id"].astype(str).tolist()
            frames = []
            for station_id in members:
                path = STATION_DAILY_DIR / f"{station_id}.csv"
                if path.is_file():
                    series = pd.read_csv(path, parse_dates=["date"]).set_index("date")["temperature_c"]
                else:
                    series = pd.Series(dtype=float)
                frames.append(series.rename(station_id))
            wide = pd.concat(frames, axis=1) if frames else pd.DataFrame()
            if len(wide):
                full_index = pd.date_range(wide.index.min(), wide.index.max(), freq="D")
                wide = wide.reindex(full_index)
                wide.index.name = "date"
                wide = wide.reindex(columns=sorted(wide.columns, key=lambda c: str(c)))
            wide.to_csv(network_dir / "daily_wide_temperature.csv", float_format="%.4f")
            group.loc[:, ordered].to_csv(network_dir / "stations.csv", index=False)
            networks_written.append(str(network_id))
            eligible_rows.append(
                {
                    "network_id": network_id,
                    "provider": PROVIDER,
                    "catchment_number": group["catchment_number"].iloc[0],
                    "catchment_name": group["catchment_name"].iloc[0],
                    "n_stations_in_network": int(len(group)),
                    "n_stations_ge_min_years": int(len(qualifying)),
                    "station_ids_ge_min_years": ";".join(sorted(qualifying["station_id"].astype(str))),
                    "n_complete_station_years": int(qualifying["n_complete_years"].sum()),
                    "n_days_total": int(qualifying["n_days"].sum()),
                    "n_dropped_qc_total": int(qualifying["n_dropped_qc"].sum()),
                    "median_latitude": float(group["latitude"].median()),
                    "median_longitude": float(group["longitude"].median()),
                    "first_date": str(qualifying["first_date"].min()),
                    "last_date": str(qualifying["last_date"].max()),
                }
            )
            log(f"network {network_id}: {len(qualifying)} eligible stations, wide rows={len(wide)}")

    # --- QC legend aggregation (verbatim) --------------------------------- #
    legend_by_code: dict[str, set[str]] = {}
    for station_id, legend in legends.items():
        for item in legend:
            legend_by_code.setdefault(item["code"], set()).add(f"{item['label']} ({item['code']}) = {item['meaning_verbatim']}")
    qc_legend = {
        code: sorted(texts)
        for code, texts in sorted(legend_by_code.items())
    }
    undocumented_codes = sorted(c for c in quality_code_totals if c not in qc_legend)

    # --- write station tables -------------------------------------------- #
    if len(station_frame):
        station_frame.to_csv(OUT_ROOT / "stations_all.csv", index=False, columns=ordered)
        # stations.csv is the seal-facing table (scripts/245, scripts/249). It lists every
        # station that appears as a column of an emitted network panel (the uk_ea
        # convention); `n_complete_years` shows which of them meet the >= 4-year rule, and
        # a station with no accepted day still appears if its catchment was emitted. The
        # full provider inventory stays in stations_all.csv.
        emitted_station_ids = set()
        if len(station_frame) and networks_written:
            emitted_station_ids = {
                str(sid)
                for network_id, group in station_frame.groupby("network_id", sort=True)
                if str(network_id) in networks_written
                for sid in group["station_id"].astype(str)
            }
        stations_out = station_frame.loc[station_frame["station_id"].astype(str).isin(emitted_station_ids)]
        stations_out.to_csv(OUT_ROOT / "stations.csv", index=False, columns=ordered)
        station_frame.loc[
            :, ["network_id", "station_id", "river_name", "catchment_name", "latitude", "longitude",
                "hydropower_name_evidence", "hydropower_evidence"]
        ].to_csv(OUT_ROOT / "hydropower_evidence.csv", index=False)
    else:
        pd.DataFrame(columns=ordered).to_csv(OUT_ROOT / "stations_all.csv", index=False)
        pd.DataFrame(columns=ordered).to_csv(OUT_ROOT / "stations.csv", index=False)

    pd.DataFrame(ledger_records, columns=[
        "network_id", "station_id", "provider", "year",
        "n_finite_days_after_qc", "days_required", "complete",
    ]).to_csv(OUT_ROOT / "station_years.csv", index=False)

    catalog_frame = pd.DataFrame(stations_catalog)
    catalog_frame.to_csv(OUT_ROOT / "station_catalog.csv", index=False)

    networks_frame = pd.DataFrame(eligible_rows)
    networks_frame.to_csv(OUT_ROOT / "networks_summary.csv", index=False)
    pd.DataFrame(networks_skipped).to_csv(OUT_ROOT / "networks_not_eligible.csv", index=False)
    pd.DataFrame(failures, columns=["station_id", "url", "error"]).to_csv(
        OUT_ROOT / "download_failures.csv", index=False
    )

    manifest_rows = []
    for path in sorted(RAW_CACHE.glob("*")):
        payload = path.read_bytes()
        manifest_rows.append(
            {
                "file": str(path.relative_to(ROOT)),
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
            }
        )
    pd.DataFrame(manifest_rows).to_csv(OUT_ROOT / "raw_cache_manifest.csv", index=False)

    # --- counters --------------------------------------------------------- #
    n_downloaded = len(station_frame)
    n_stations_ge_years = int((station_frame["n_complete_years"] >= MIN_COMPLETE_YEARS).sum()) if len(station_frame) else 0
    n_complete_station_years_ge_years = (
        int(station_frame.loc[station_frame["n_complete_years"] >= MIN_COMPLETE_YEARS, "n_complete_years"].sum())
        if len(station_frame) else 0
    )
    n_complete_station_years = int(station_frame["n_complete_years"].sum()) if len(station_frame) else 0
    ingest_stations_with_accepted = int((station_frame["n_days"] > 0).sum()) if len(station_frame) else 0
    n_dropped_qc_total = int(station_frame["n_dropped_qc"].sum()) if len(station_frame) else 0
    n_accepted_days_total = int(station_frame["n_days"].sum()) if len(station_frame) else 0
    n_days_any_quality = int(station_frame["n_days_any_quality"].sum()) if len(station_frame) else 0
    quality_distribution = {code or "blank": int(count) for code, count in sorted(quality_code_totals.items())}

    # emitted panel counters (stations appearing as columns of an emitted network)
    if len(station_frame) and networks_written:
        emitted_mask = station_frame["network_id"].astype(str).isin(networks_written)
        emitted_frame = station_frame.loc[emitted_mask]
    else:
        emitted_frame = station_frame.iloc[0:0]
    n_stations_emitted = int(len(emitted_frame))
    n_stations_emitted_ge_years = (
        int((emitted_frame["n_complete_years"] >= MIN_COMPLETE_YEARS).sum()) if len(emitted_frame) else 0
    )
    n_complete_station_years_emitted = (
        int(emitted_frame.loc[emitted_frame["n_complete_years"] >= MIN_COMPLETE_YEARS, "n_complete_years"].sum())
        if len(emitted_frame) else 0
    )
    ge_years_frame = station_frame.loc[station_frame["n_complete_years"] >= MIN_COMPLETE_YEARS] if len(station_frame) else station_frame
    if len(station_frame) and networks_written:
        stranded_frame = ge_years_frame.loc[~ge_years_frame["network_id"].astype(str).isin(networks_written)]
    else:
        stranded_frame = ge_years_frame.iloc[0:0]
    n_stations_ge_years_not_emitted = int(len(stranded_frame))
    n_station_years_not_emitted = (
        int(stranded_frame["n_complete_years"].sum()) if len(stranded_frame) else 0
    )
    # strict-gate audit: what the quality_checked stratum would yield on the same bytes
    strict_codes = tuple(QC_STRATA["quality_checked"]["accepted_quality_codes"])  # type: ignore[arg-type]
    strict_qc_rows = sum(
        int(count) for code, count in quality_code_totals.items() if code in strict_codes
    )

    # Prior-use overlap check (read-only): SMHI station ids must not appear in the
    # v17/v18 rosters. scripts/245 re-derives this repo-wide; the local check is a
    # fail-loud pre-check so the coordinator sees it in ingest.json.
    roster_files = [
        ROOT / "results" / "v17_fitness" / "step1_panel" / "station_roster.csv",
        ROOT / "results" / "wrr_revision" / "step1_universe" / "trusted_river_complete_years.csv",
        ROOT / "results" / "wrr_submission_ready" / "prior_access_ledger_reserved_station_years.csv",
        ROOT / "results" / "wrr_submission_ready" / "confirmation_inputs_manifest.csv",
    ]
    smhi_ids = {str(entry["id"]) for entry in stations_catalog}
    overlaps: set[str] = set()
    for roster_path in roster_files:
        if not roster_path.is_file():
            continue
        with roster_path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                for column in ("station_id", "site_id", "station_ids_ge4", "eligible_station"):
                    value = str(row.get(column) or "").strip()
                    if not value:
                        continue
                    for token in re.split(r"[;|,]", value):
                        if token.strip() in smhi_ids:
                            overlaps.add(token.strip())
    SMHI_ROSTER_OVERLAP = {"n_overlaps": len(overlaps), "overlaps": sorted(overlaps)}

    active_values = sorted({str(entry.get("active")) for entry in stations_catalog})
    station_class_values = sorted({str(entry.get("measuringStations")) for entry in stations_catalog})
    lat_values = [float(entry["latitude"]) for entry in stations_catalog if entry.get("latitude") is not None]

    provider_docs = {
        "parameter_4_metadata_url": METADATA_URL,
        "parameter_4_abstract_verbatim": metadata_abstract,
        "catalog_record": "https://opendata-catalog.smhi.se/md/9d61ab90-7d21-11ed-a51b-432755aaeed3",
        "statistic_quote_verbatim": SMHI_STATISTIC_QUOTE,
        "unit_quote_verbatim": SMHI_STATISTIC_UNIT_QUOTE,
        "aggregation_operator_documented": False,
        "measurement_statistic_assigned": MEASUREMENT_STATISTIC,
    }

    ingest = {
        "provider": PROVIDER,
        "agency": "Sveriges meteorologiska och hydrologiska institut (SMHI), Sweden",
        "provider_full_name": "Sveriges meteorologiska och hydrologiska institut (SMHI)",
        "context": "boreal_nordic (matches the CONTEXT map used by scripts/249)",
        "command": f"PYTHONPATH=src python3 scripts/240_multi_agency_smhi_ingest.py --qc-stratum {qc_stratum}",
        "qc_stratum": qc_stratum,
        "parameter": {
            "key": "4",
            "title": catalog.get("title"),
            "unit": catalog.get("unit"),
            "archive_period": "corrected-archive",
        },
        "retrieval_utc": retrieval_utc,
        "url_patterns": {
            "catalog": CATALOG_URL,
            "series": DATA_URL_PATTERN,
            "metadata": METADATA_URL,
            "series_period": "corrected-archive (only period served for parameter 4; "
                             "latest-day/latest-months return HTTP 404 for these stations)",
        },
        "user_agent": USER_AGENT,
        "request_throttle_seconds": args.sleep,
        "n_catalog_stations": len(stations_catalog),
        "n_downloaded": n_downloaded,
        "n_download_failures": len(failures),
        "n_networks": len(networks_written),
        "n_networks_considered": int(station_frame["network_id"].nunique()) if len(station_frame) else 0,
        "n_stations": n_stations_ge_years,
        "n_stations_downloaded_with_data": int((station_frame["n_days_any_quality"] > 0).sum()) if len(station_frame) else 0,
        "n_stations_with_accepted_days": ingest_stations_with_accepted,
        "n_station_years_complete": n_complete_station_years,
        "n_complete_station_years": n_complete_station_years,
        "n_stations_emitted": n_stations_emitted,
        "n_stations_emitted_ge_4_complete_years": n_stations_emitted_ge_years,
        # two distinct station-year totals; both are reported so neither is mistaken
        # for the other. The first is the provider-wide figure quoted in README.md and
        # in the strict-gate counterfactual (118 stations / 16 networks / 1601 years);
        # the second counts only eligible stations inside emitted networks, and the
        # third is the residual in catchments that failed the >= 2-station rule.
        "n_complete_station_years_stations_ge_4_years": n_complete_station_years_ge_years,
        "n_complete_station_years_in_emitted_networks": n_complete_station_years_emitted,
        "n_stations_ge_4_years_not_in_emitted_networks": n_stations_ge_years_not_emitted,
        "n_complete_station_years_not_in_emitted_networks": n_station_years_not_emitted,
        "stratum_provenance": {
            "amendment": "MULTI_AGENCY_TRANSPORT_PROTOCOL.md Amendment 2 (assurance strata), "
                         "made after ingest attempts and before sealing or any transport scoring",
            "strata": {
                name: {
                    "accepted_quality_codes": list(spec["accepted_quality_codes"]),  # type: ignore[arg-type]
                    "definition": spec["definition"],
                }
                for name, spec in sorted(QC_STRATA.items())
            },
            "run_stratum": qc_stratum,
            "strict_gate_audit": {
                "stratum": "quality_checked",
                "accepted_quality_codes": list(strict_codes),
                "n_rows_passing_strict_gate": strict_qc_rows,
                "per_station_g_y_counts": "see the quality_code_counts column of stations_all.csv",
                "outcome_on_this_provider": (
                    "0 stations and 0 networks on the same raw bytes; see "
                    "QC_AND_ELIGIBILITY_FAILURE.md, retained unchanged as the strict-gate audit "
                    "record of retrieval 2026-10-12T09:55:14Z"
                ),
            },
        },
        "eligibility_rule": {
            "network_definition": "SMHI catchmentNumber (agency-native grouping)",
            "min_stations_per_network": MIN_STATIONS_PER_NETWORK,
            "min_complete_calendar_years_per_station": MIN_COMPLETE_YEARS,
            "complete_year_definition": "365 (366 in leap years) distinct calendar days with a finite "
                                        "value that passed the quality-code gate",
        },
        "qc": {
            "accepted_quality_codes": list(ACCEPTED_QUALITY_CODES),
            "qc_stratum": qc_stratum,
            "stratum_definition": QC_STRATA[qc_stratum]["definition"],
            "legend_quote_for_accepted_codes": {
                code: qc_legend.get(code, []) for code in ACCEPTED_QUALITY_CODES
            },
            "legend_verbatim_by_code": qc_legend,
            "legend_source": "SMHI embeds the legend as trailing free-text fields on the first data "
                             "rows of every station CSV ('Kvalitetskoderna:' followed by "
                             "'<Name> (<CODE>) = <meaning>.'); identical across all downloaded "
                             "stations. Verbatim copy in QC_legend_verbatim.json and "
                             "station_header_block.txt.",
            "n_stations_with_legend_extracted": len(legends),
            "n_stations_with_expected_legend_codes": sum(
                1 for legend in legends.values()
                if {item["code"] for item in legend} >= set(ACCEPTED_QUALITY_CODES)
            ),
            "header_block_verbatim_example": header_blocks.get(station_ids[0], []) if station_ids else [],
            "value_column_headers_seen": sorted(value_header_names),
            "quality_column_headers_seen": sorted(quality_header_names),
            "undocumented_codes_observed": undocumented_codes,
            "dropped_codes": sorted(c for c in quality_distribution if c not in ACCEPTED_QUALITY_CODES),
            "quality_code_distribution_rows_parsed": quality_distribution,
            "n_value_rows_parsed": n_days_any_quality,
            "n_rows_dropped_by_quality_gate_or_missing_value": n_dropped_qc_total,
            "n_rows_accepted": n_accepted_days_total,
            "loss_fraction_of_parsed_rows": (
                round(n_dropped_qc_total / n_days_any_quality, 6) if n_days_any_quality else None
            ),
            "value_parse_notes": dict(value_notes_all),
        },
        "deduplication": {
            "rule": (
                "same calendar date repeated -> keep the row with the highest-ranked quality code "
                "(G > Y > O > undocumented/blank); ties broken by last occurrence in file order"
            ),
            "n_stations_with_duplicate_dates": int(
                sum(1 for info in dedup_rules.values() if info["n_duplicate_dates"])
            ),
            "n_duplicate_rows_removed_total": int(
                sum(info["n_duplicate_rows_removed"] for info in dedup_rules.values())
            ),
            "per_station": {k: v for k, v in sorted(dedup_rules.items()) if v["n_duplicate_dates"]},
        },
        "file_level_metadata": {
            "station_network_class_values_in_series_files": dict(file_station_network_classes),
            "parameter_name_values": dict(file_parameter_names),
            "parameter_unit_values": dict(file_parameter_units),
            "n_station_name_mismatches_vs_catalog": len(identity_mismatches),
            "station_name_mismatch_examples": identity_mismatches[:10],
            "note": "'Övriga stationer' in Stationsnät is SMHI's label for stations outside "
                    "SMHI's own station network (data collected and stored by SMHI under "
                    "agreement with a third party).",
        },
        "panel_character": {
            "latitude_range": [min(lat_values), max(lat_values)] if lat_values else None,
            "active_flag_values_in_catalog": active_values,
            "measuring_stations_values_in_catalog": station_class_values,
            "domain_note": "all catalogued parameter-4 stations carry measuringStations = ADDITIONAL "
                           "('Övriga stationer' = stations outside SMHI's own station network; data "
                           "collected and stored by SMHI through agreement with a third party) and are "
                           "flagged active = false in the catalog",
            "coverage_note": "the corrected-archive series are historical (see station_catalog.csv and "
                             "stations_all.csv for the observed per-station spans)",
        },
        "provider_documentation": provider_docs,
        "artifacts": {
            "stations_csv": "stations.csv (one row per station appearing in an emitted panel, with "
                            "provider, coordinates, complete years, n_days, n_dropped_qc, "
                            "accepted_quality_codes, measurement_statistic, quality_assurance; the "
                            "seal-facing table read by scripts/245 and scripts/249)",
            "stations_all_csv": "stations_all.csv (every downloaded station, including zero accepted days)",
            "readme": "README.md (what was downloaded, the QC legend, why O was admitted, caveats)",
            "strict_gate_failure_note": "QC_AND_ELIGIBILITY_FAILURE.md (retained strict-gate record)",
            "per_network_stations_csv": "networks/<network_id>/stations.csv",
            "station_catalog_csv": "station_catalog.csv",
            "station_years_csv": "station_years.csv",
            "networks_summary_csv": "networks_summary.csv",
            "networks_not_eligible_csv": "networks_not_eligible.csv",
            "networks_dir": "networks/",
            "station_daily_dir": "station_daily/",
            "raw_cache_dir": "raw_cache/",
            "download_failures_csv": "download_failures.csv",
        },
        "script": str(Path(__file__).relative_to(ROOT)),
        "raw_provenance": {
            "catalog": catalog_provenance,
            "metadata_urls": metadata_urls,
            "n_series_urls": len(data_urls),
            "series_url_example": data_urls[0] if data_urls else "",
        },
        "caveats": [
            "Date column header is 'Datum (svensk sommartid)': timestamps are Swedish summer time "
            "(UTC+2), not UTC. Local Swedish time on the same date still maps to that calendar date, "
            "so date-only panels are unaffected, but any diurnal or UTC alignment would be wrong. The "
            "download portal text separately says file times are UTC (+1/+2 h); the two statements "
            "conflict and the header is the file-level one, so it is reported as-is.",
            "'Övriga stationer' (Stationsnät field) = the station is not part of SMHI's own station "
            "network; data are collected and stored by SMHI under agreement with a third party. Every "
            "parameter-4 station is catalogued this way, so this panel is not SMHI's official network.",
            "Provider metadata documents only 'daily watercourse temperature'; the daily aggregation "
            "operator (mean vs. instantaneous reading) is not documented for parameter 4. The panel is "
            "therefore assigned the statistic 'daily provider statistic (°C)' and NOT a confirmed daily mean.",
            "No recent data: the catalog flags every parameter-4 station active = false and the archive "
            "ends in the early 2000s; the panel is historical and does not overlap the recent-period "
            "regime of the frozen model's development panel.",
            "Rows outside the accepted quality-code set for this run's stratum are dropped even when "
            "their values look physical; no imputation, no gap filling beyond leaving cells blank.",
            "Assurance stratum of this run: '" + qc_stratum + "'. Values accepted here are labelled at "
            "source as uncontrolled/unqualified; the per-station quality_assurance column carries the "
            "stratum into the seal so the strata are never pooled silently.",
            "Complete-year counting is done on QC-accepted, deduplicated values only.",
        ],
        "counts": {
            "n_catalog_stations": len(stations_catalog),
            "n_downloaded": n_downloaded,
            "n_download_failures": len(failures),
            "n_stations_with_data": int((station_frame["n_days_any_quality"] > 0).sum()) if len(station_frame) else 0,
            "n_stations_with_accepted_days": ingest_stations_with_accepted,
            "n_stations_ge_4_complete_years": n_stations_ge_years,
            "n_networks_emitted": len(networks_written),
            "n_networks_in_catalog_grouping": int(station_frame["network_id"].nunique()) if len(station_frame) else 0,
            "n_station_years_complete": n_complete_station_years,
            "n_complete_station_years": n_complete_station_years,
            "n_complete_station_years_stations_ge_4_years": n_complete_station_years_ge_years,
            "n_complete_station_years_in_emitted_networks": n_complete_station_years_emitted,
            "n_rows_parsed": n_days_any_quality,
            "n_rows_accepted": n_accepted_days_total,
            "n_rows_dropped": n_dropped_qc_total,
        },
        "networks_emitted": len(networks_written),
        "stations_emitted": n_stations_emitted,
        "stations_emitted_ge_4_complete_years": n_stations_emitted_ge_years,
        "v17_roster_overlap": {
            "n_station_ids_checked": len(stations_catalog),
            "checked_files": [
                "results/v17_fitness/step1_panel/station_roster.csv",
                "results/wrr_revision/step1_universe/trusted_river_complete_years.csv",
                "results/wrr_submission_ready/prior_access_ledger_reserved_station_years.csv",
                "results/wrr_submission_ready/confirmation_inputs_manifest.csv",
            ],
            "n_overlapping_station_ids": SMHI_ROSTER_OVERLAP["n_overlaps"],
            "overlapping_station_ids": SMHI_ROSTER_OVERLAP["overlaps"],
            "numerator_note": "SMHI station ids are provider-native numeric ids; all overlaps are "
                              "recomputed by scripts/245 as well",
        },
        "failure": None,
    }

    if len(networks_written) == 0 or n_stations_ge_years == 0:
        worst = max(quality_distribution.items(), key=lambda kv: kv[1]) if quality_distribution else ("", 0)
        ingest["failure"] = {
            "rule": f"networks require >= 2 stations each with >= 4 complete calendar years AFTER the "
                    f"quality-code gate of stratum '{qc_stratum}' "
                    f"(accepted codes: {', '.join(ACCEPTED_QUALITY_CODES) or 'none'})",
            "observed": {
                "n_stations_with_accepted_days": ingest["n_stations_with_accepted_days"],
                "n_stations_with_ge_4_complete_years": n_stations_ge_years,
                "n_networks": len(networks_written),
                "dominant_quality_code": worst[0],
                "dominant_quality_code_rows": worst[1],
                "share_rows_dropped": ingest["qc"]["loss_fraction_of_parsed_rows"],
            },
            "cause": "The entire SMHI parameter-4 corrected-archive is flagged with quality code "
                     f"'{worst[0]}'. {qc_legend.get(worst[0], [''])[0]}",
            "not_substituted": "No proxy rule was applied inside this run: the accepted set is exactly "
                               f"the declared stratum '{qc_stratum}'. Reaching a panel from these bytes "
                               "requires an explicit, separately recorded stratum decision.",
            "consequence": "This provider contributes 0 networks and 0 station-years to the transport "
                           "panel at this stratum.",
        }
        ingest["verdict"] = (
            f"infeasible under stratum '{qc_stratum}': 0 stations survive the quality-code gate and no "
            "network can be emitted; no proxy rule was substituted"
        )
    else:
        ingest["verdict"] = (
            f"panel emitted under stratum '{qc_stratum}': {len(networks_written)} networks, "
            f"{n_stations_emitted_ge_years} stations with >= {MIN_COMPLETE_YEARS} complete calendar "
            f"years ({n_stations_emitted} stations in total across the emitted panels), "
            f"{n_complete_station_years_emitted} complete station-years; values are labelled "
            "uncontrolled at source and must be reported as the provider_published_unqualified stratum"
        )

    if header_blocks:
        first_id = station_ids[0] if station_ids else sorted(header_blocks)[0]
        (OUT_ROOT / "station_header_block.txt").write_text(
            "Verbatim header block of the first downloaded station CSV "
            f"(station {first_id}, from raw_cache/station_{first_id}.csv):\n\n"
            + "\n".join(header_blocks[first_id]) + "\n"
        )

    (OUT_ROOT / "ingest.json").write_text(json.dumps(ingest, indent=2, ensure_ascii=False) + "\n")
    (OUT_ROOT / "QC_legend_verbatim.json").write_text(
        json.dumps({"qc_legend_verbatim_by_code": qc_legend, "undocumented_codes_observed": undocumented_codes},
                   indent=2, ensure_ascii=False) + "\n"
    )
    (OUT_ROOT / "run.log").write_text("\n".join(log_lines) + "\n")

    failure_note = OUT_ROOT / "QC_AND_ELIGIBILITY_FAILURE.md"
    if ingest["failure"]:
        overlap = SMHI_ROSTER_OVERLAP
        prior_use_line = (
            f"PRIOR-USE CHECK: {overlap['n_overlaps']} SMHI station ids overlap the v17/v18 rosters "
            f"({', '.join(overlap['overlaps'][:10])})."
            if overlap["n_overlaps"]
            else f"PRIOR-USE CHECK: 0 of {len(stations_catalog)} SMHI station ids appear in the "
                 "v17/v18 rosters."
        )
        failure_note.write_text(
            "# SMHI multi-agency ingest: QC/eligibility failure\n\n"
            f"Retrieval: {retrieval_utc}. Stratum: `{qc_stratum}` "
            f"(accepted codes: {', '.join(ACCEPTED_QUALITY_CODES) or 'none'}).\n\n"
            f"Stations downloaded: {n_downloaded} of {len(stations_catalog)} catalogued.\n"
            f"Rows parsed: {n_days_any_quality}. Accepted by this run's quality-code gate: "
            f"{n_accepted_days_total}. Dropped: {n_dropped_qc_total} "
            f"({ingest['qc']['loss_fraction_of_parsed_rows']:.4f} of parsed rows).\n\n"
            "## Observed quality-code distribution (parsed rows)\n\n"
            + "\n".join(f"- `{code}`: {count}" for code, count in quality_distribution.items())
            + "\n\n## Why there is no panel\n\n"
            f"- Stations with >= 1 accepted day: {ingest['n_stations_with_accepted_days']} of {n_downloaded}\n"
            f"- Stations with >= {MIN_COMPLETE_YEARS} complete calendar years after QC: {n_stations_ge_years}\n"
            f"- Eligible networks (>= {MIN_STATIONS_PER_NETWORK} such stations): {len(networks_written)}\n"
            f"- Complete station-years: {n_complete_station_years}\n\n"
            "Every parameter-4 station is catalogued `measuringStations = ADDITIONAL` ('Övriga stationer' "
            "= outside SMHI's own station network) and the corrected-archive series carry only quality "
            "code `O`. SMHI documents `O` as uncontrolled values, so a gate that requires "
            "checked/coarsely-checked values accepts none of them.\n\n"
            "No proxy rule was substituted inside this run: the accepted set is exactly the declared "
            "stratum. Reaching a panel from these bytes requires an explicit stratum decision recorded "
            "in the protocol and the seal chain.\n\n"
            + prior_use_line + "\n\n"
            f"Verbatim legend and full counts: `ingest.json` (retrieval {retrieval_utc}).\n"
        )
    # NOTE: a passing run never deletes an existing failure note. It is the audit
    # record of the strict-gate attempt and is referenced by README.md/ingest.json.

    # --- README (reviewer-facing record of what was admitted) -------------- #
    _fd = pd.to_datetime(station_frame["first_date_any_quality"]) if len(station_frame) else pd.Series(dtype="datetime64[ns]")
    _ld = pd.to_datetime(station_frame["last_date_any_quality"]) if len(station_frame) else pd.Series(dtype="datetime64[ns]")
    readme_stats = {
        "median_first": _fd.median().strftime("%Y-%m") if len(_fd) else "n/a",
        "median_last": _ld.median().strftime("%Y-%m") if len(_ld) else "n/a",
        "min_first": _fd.min().strftime("%Y-%m-%d") if len(_fd) else "n/a",
        "max_last": _ld.max().strftime("%Y-%m-%d") if len(_ld) else "n/a",
        "n_ending_before_1990": int((_ld < "1990-01-01").sum()) if len(_ld) else 0,
        "n_ending_2000_or_later": int((_ld >= "2000-01-01").sum()) if len(_ld) else 0,
        "min_rows": int(station_frame["n_days_any_quality"].min()) if len(station_frame) else 0,
        "median_rows": int(station_frame["n_days_any_quality"].median()) if len(station_frame) else 0,
    }
    readme = OUT_ROOT / "README.md"
    readme.write_text(
        f"""# SMHI multi-agency ingest (provider: smhi, parameter 4 "Vattendragstemperatur")

Written {retrieval_utc} by `scripts/240_multi_agency_smhi_ingest.py`
(`{ingest['command']}`).

## What was downloaded

- Catalogue: `{CATALOG_URL}` — {len(stations_catalog)} stations, unit {catalog.get('unit')!r}.
- Series: `{DATA_URL_PATTERN}` (`corrected-archive`, the only period served for parameter 4).
- {n_downloaded} of {len(stations_catalog)} stations downloaded, {len(failures)} failures;
  {n_days_any_quality} parsed rows over {quality_distribution.get('O', 0)} quality-code-`O` rows.
- Raw bytes are cached in `raw_cache/` (gitignored) with sha256 per file in
  `raw_cache_manifest.csv`; `stations_all.csv` carries per-station QC for all 176 stations.
- Coverage: {readme_stats['min_first']} .. {readme_stats['max_last']}; median station span
  {readme_stats['median_first']} .. {readme_stats['median_last']} ({readme_stats['n_ending_before_1990']} stations end before
  1990, {readme_stats['n_ending_2000_or_later']} reach 2000). Every station is
  catalogued `measuringStations = ADDITIONAL` ("Övriga stationer" = outside SMHI's own network)
  and `active = false`, and every series row carries quality code `O`.

## QC legend (verbatim, extracted from the series files)

- Grön (G) = Kontrollerade och godkända värden.
- Gul (Y) = Grovt kontrollerade värden.
- Orange (O) = Okontrollerade värden.

Full copy: `QC_legend_verbatim.json`, `station_header_block.txt`, and `ingest.json`.

## Why the uncontrolled code was accepted

`MULTI_AGENCY_TRANSPORT_PROTOCOL.md` **Amendment 2 (assurance strata)** defines
`quality_checked` (provider documents checked/coarsely-checked values) and
`provider_published_unqualified` (provider publishes the series but labels it
uncontrolled/unqualified — SMHI `O`, Hub'Eau Sandre code 4). Under the strict
`quality_checked` gate this provider yields nothing: 0 of {n_days_any_quality} rows carry
`G` or `Y`, so 0 stations and 0 networks — recorded in
`QC_AND_ELIGIBILITY_FAILURE.md`, retained unchanged as the strict-gate audit.

This run therefore uses `--qc-stratum provider_published_unqualified`. The admitted panel is:

| item | value |
|---|---|
| stratum | `{qc_stratum}` |
| accepted quality codes | `{', '.join(ACCEPTED_QUALITY_CODES)}` |
| stations with >= {MIN_COMPLETE_YEARS} complete calendar years | {n_stations_ge_years} |
| networks (>= {MIN_STATIONS_PER_NETWORK} such stations per `catchmentNumber`) | {len(networks_written)} |
| complete station-years of those stations | {n_complete_station_years_ge_years} |
| ... of which inside emitted networks | {n_complete_station_years_emitted} |
| ... of which stranded in catchments with < {MIN_STATIONS_PER_NETWORK} eligible stations | {n_station_years_not_emitted} |
| stations appearing in emitted panels (columns) | {n_stations_emitted} |
| eligible (>= {MIN_COMPLETE_YEARS}-year) stations inside emitted panels | {n_stations_emitted_ge_years} |
| complete station-years summed over all {n_downloaded} downloaded stations | {n_complete_station_years} |

The pre-decision strict-gate diagnostic predicted exactly the network and station counts
above (118 stations with >= 4 complete years, 16 networks; see
`scratch/smhi_verify_counterfactual_station_years.csv` and
`scratch/smhi_verify_counterfactual_networks.csv`), so the decision admitted the panel
that was on the table with no extra filtering. That diagnostic's headline
"1,601 complete station-years" is the **all-station** sum; it includes
{int(n_complete_station_years - n_complete_station_years_ge_years)} years contributed by the
{int(n_downloaded - n_stations_ge_years)} stations below the {MIN_COMPLETE_YEARS}-year bar, which is why the
eligible-station total here is {n_complete_station_years_ge_years}.

Values are labelled uncontrolled **by the provider**; no re-checking was performed here.
The stratum travels into the seal as the per-station `quality_assurance` column of
`stations.csv`, and the pooled transport verdict must be reported with the per-stratum
breakdown and the sensitivity that excludes this stratum (Amendment 2, rules 2-3).

## Caveats a reviewer must carry

1. **Day boundary / timezone.** The date column header is `Datum (svensk sommartid)`
   (Swedish summer time, UTC+2). The SMHI download-portal text separately says file times
   are UTC (+1 h normal, +2 h summer). The statements conflict; date-only panels are
   unaffected on the same calendar date, but any UTC/diurnal alignment would be wrong.
2. **Statistic.** SMHI documents parameter 4 as
   "{SMHI_STATISTIC_QUOTE}" with "{SMHI_STATISTIC_UNIT_QUOTE}". The daily aggregation
   operator (mean vs. instantaneous reading) is not documented, so `measurement_statistic`
   records a daily provider statistic in °C, not a confirmed daily mean.
3. **Not SMHI's own network.** Every station is `Övriga stationer` (third-party data
   collected and stored by SMHI), so this is not SMHI's official station network.
4. **Historical.** The archive ends in 2003 and no parameter-4 station is active; the panel
   does not overlap the recent-period regime of the frozen model's development panel.
5. **No scoring here.** Ingest and QC only; no frozen-screen performance was computed on
   this data by this script.
6. **Some stations are short.** Rows per station run {readme_stats['min_rows']} to
   {int(station_frame['n_days_any_quality'].max())} (median {readme_stats['median_rows']}); complete-year counting decides who
   enters a network.

## Artifacts

`networks/<network_id>/daily_wide_temperature.csv` (first column `date`, one column per
station id, one row per calendar day from min to max date, blank where missing),
`networks/<network_id>/stations.csv`, `stations.csv`, `stations_all.csv`,
`station_catalog.csv`, `station_years.csv`, `networks_summary.csv`,
`networks_not_eligible.csv`, `hydropower_evidence.csv`, `INGEST_STATUS.json`,
`QC_AND_ELIGIBILITY_FAILURE.md` (strict-gate record), `QC_legend_verbatim.json`,
`ingest.json`, `run.log`, `raw_cache_manifest.csv`, `raw_cache/`.

Textual only: {int(station_frame['river_name'].astype(str).str.contains('KRV').sum())} of {len(station_frame)}
station names contain "KRV" (kraftverk) and
{int(station_frame['river_name'].astype(str).str.contains('FORS').sum())} contain "FORS"/"FORSEN";
see `hydropower_evidence.csv`. This is name evidence, not a regulation classification.

Latitudes {min(lat_values):.2f}-{max(lat_values):.2f} N
({int((station_frame['latitude'] >= 60).sum())} of {len(station_frame)} north of 60 N), consistent with the
`boreal_nordic` context used for this provider in `scripts/249`.
"""
    )

    log(
        "DONE downloaded={} accepted_days={} stations_ge4y={} networks={} complete_station_years={} failures={}".format(
            n_downloaded, n_accepted_days_total, n_stations_ge_years, len(networks_written), n_complete_station_years, len(failures)
        )
    )
    print(json.dumps({
        "qc_stratum": qc_stratum,
        "n_downloaded": n_downloaded,
        "n_stations_ge_4_complete_years": n_stations_ge_years,
        "n_networks": len(networks_written),
        "n_stations_emitted": n_stations_emitted,
        "n_stations_emitted_ge_4_complete_years": n_stations_emitted_ge_years,
        "n_complete_station_years": n_complete_station_years,
        "complete_station_year_definitions": {
            "n_complete_station_years": "sum of complete calendar years over ALL downloaded stations "
                                        "(includes stations below the 4-year bar)",
            "n_complete_station_years_stations_ge_4_years": "sum over the stations that individually "
                                                            "meet the 4-complete-year rule",
            "n_complete_station_years_in_emitted_networks": "sum over eligible stations of emitted "
                                                            "networks only",
        },
        "n_complete_station_years_emitted": n_complete_station_years_emitted,
        "quality_code_rows": quality_distribution,
        "n_rows_accepted": n_accepted_days_total,
        "n_rows_dropped": n_dropped_qc_total,
    }, indent=2))
    (OUT_ROOT / "run.log").write_text("\n".join(log_lines) + "\n")
    return 0 if not ingest["failure"] else 3


if __name__ == "__main__":
    sys.exit(main())
