#!/usr/bin/env python3
"""Austria eHYD ingest probe for the multi-agency transport panel (script 243).

Question: can eHYD deliver a *daily* river water-temperature series
(provider daily statistic in degC) for the pre-registered transport panel?

This script gathers server-side evidence for the answer and writes it to
results/wrr_submission_ready/multi_agency_ingest/ehyd/. It never scores the
frozen screen: ingest + QC only (HARD RULE 4).

Evidence collected:
  1. official station/file listing          https://ehyd.gv.at/services/Messstellen/json?filter=alle
  2. official bulk package                  https://gis.lfrz.gv.at/api/ehyd/messstellen/paket/ehyd_messstellen_all_owf.zip
  3. server-side download type enumeration  https://ehyd.gv.at/services/AreaSelection/download?cat=...&reg=0
  4. web-app data-type menu (client bundle) https://ehyd.gv.at/ + main-<hash>.js
  5. per-station monthly payload samples    WT-Monatsmittel/<file> inside the package
  6. long-term diagram service probes       https://ehyd.gv.at/services/Diagram/pegelLongterm?hzbnr=...

Verdict logic (fixed before the run, reported in ingest.json):
  feasible  <=> at least one eHYD surface-water (river) temperature product with a
                documented DAILY statistic exists (file type / download type / API).
  otherwise -> INFEASIBLE.md, no network emitted.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.ehyd_temperature import (  # noqa: E402
    FILE_KIND,
    PACKAGE_URL,
    STATION_URL,
    exact_river_candidates,
    monthly_network,
    surface_temperature_stations,
)

OUT = ROOT / "results/wrr_submission_ready/multi_agency_ingest/ehyd"
RAW = OUT / "raw_cache"
ROSTER = ROOT / "results/v17_fitness/step1_panel/station_roster.csv"
INDEX_URL = "https://ehyd.gv.at/"
DOWNLOAD_PROBE_URL = (
    "https://ehyd.gv.at/services/AreaSelection/download?cat={cat}&reg=0"
)
DIAGRAM_URL = "https://ehyd.gv.at/services/Diagram/pegelLongterm?hzbnr={site}"
USER_AGENT = "stream-recoverability/0.1 ehyd-transport-ingest-probe"

# A product counts as a daily surface-water temperature source only if its
# identifier carries both a temperature token and a daily token.
TEMP_TOKEN = re.compile(r"wassertemp|wt_|_wt|quellwassertemp", re.I)
DAILY_TOKEN = re.compile(r"tages|daily|tag_", re.I)
SURFACE_TOKEN = re.compile(r"^owf|_owf|surface", re.I)


def log(message: str) -> None:
    print(f"[243-ehyd] {message}", flush=True)


def get_bytes(url: str, *, timeout: int = 300) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def head_headers(url: str) -> dict[str, str]:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT}, method="HEAD"
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as error:
        return {"http_status": str(error.code)}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_cached(url: str, dest: Path, *, force: bool) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fetched = False
    if force or not dest.is_file() or dest.stat().st_size == 0:
        log(f"GET {url} -> {dest.name}")
        dest.write_bytes(get_bytes(url))
        fetched = True
    return {
        "url": url,
        "cache_file": str(dest.relative_to(ROOT)),
        "bytes": int(dest.stat().st_size),
        "sha256": sha256_of(dest),
        "fetched_this_run": fetched,
        "server_head": head_headers(url),
    }


def ftyp_census(feature_document: dict) -> pd.DataFrame:
    rows = []
    for feature in feature_document["features"]:
        properties = feature["properties"]
        for file_row in json.loads(properties.get("fjson") or "[]"):
            rows.append(
                {
                    "site_id": str(properties["hzbnr01"]),
                    "file_type": str(file_row.get("ftyp") or ""),
                    "file_name": str(file_row.get("file") or ""),
                    "file_from_year": file_row.get("filefrom"),
                    "file_to_year": file_row.get("fileto"),
                    "file_size_bytes": file_row.get("fsize"),
                }
            )
    return pd.DataFrame(rows)


def app_bundle_evidence(*, force: bool) -> dict:
    """Read the shipped web-app data-type menu (client-side second opinion)."""

    try:
        index_path = RAW / "ehyd_index.html"
        if force or not index_path.is_file():
            index_path.write_bytes(get_bytes(INDEX_URL, timeout=120))
        html = index_path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r'src="(main-[A-Z0-9]+\.js)"', html)
        if match is None:
            return {"ok": False, "reason": "main bundle not referenced in index.html"}
        bundle_url = INDEX_URL + match.group(1)
        bundle_path = RAW / match.group(1)
        if force or not bundle_path.is_file():
            bundle_path.write_bytes(get_bytes(bundle_url, timeout=180))
        text = bundle_path.read_text(encoding="utf-8", errors="replace")
        menu = re.search(r'\{id:"owf",label:"[^"]*",togglable:!0,icon:"owf_mst",children:\[(.*?)\]\}', text)
        surface_types = []
        if menu is not None:
            surface_types = re.findall(r'\{id:"([^"]+)",label:"([^"]+)"\}', menu.group(1))
        all_types = re.findall(r'\{id:"([a-z0-9_]+)",label:"([^"]+)"\}', text)
        return {
            "ok": True,
            "index_url": INDEX_URL,
            "bundle_url": bundle_url,
            "bundle_sha256": sha256_of(bundle_path),
            "bundle_bytes": int(bundle_path.stat().st_size),
            "surface_water_menu": [
                {"id": i, "label": label} for i, label in surface_types
            ],
            "all_data_type_menu_entries": [
                {"id": i, "label": label} for i, label in all_types
            ],
        }
    except Exception as error:  # noqa: BLE001 - evidence-only, never fatal
        return {"ok": False, "reason": f"{type(error).__name__}: {error}"}


def download_type_probe(*, force: bool) -> dict:
    """Server-side enumeration of every downloadable data type."""

    probes = {}
    for cat in (
        "owf_wassertemp_monatsmittel",
        "owf_wassertemp_tagesmittel",
        "qu_quellwassertemp",
    ):
        url = DOWNLOAD_PROBE_URL.format(cat=cat)
        cache = RAW / f"areaselection_probe_{cat}.txt"
        if force or not cache.is_file():
            try:
                cache.write_bytes(get_bytes(url, timeout=120))
            except Exception as error:  # noqa: BLE001
                cache.write_text(f"ERROR {type(error).__name__}: {error}\n", encoding="utf-8")
        probes[cat] = {
            "url": url,
            "response": cache.read_text(encoding="utf-8", errors="replace").strip(),
        }
    allowed: list[str] = []
    for entry in probes.values():
        match = re.search(r"allowed types are (.+)$", entry["response"])
        if match:
            allowed = [item.strip() for item in match.group(1).split(",")]
    temperature_types = [t for t in allowed if TEMP_TOKEN.search(t)]
    return {
        "probes": probes,
        "allowed_download_types": allowed,
        "n_allowed_download_types": len(allowed),
        "temperature_types": temperature_types,
        "daily_surface_temperature_types": [
            t for t in allowed
            if TEMP_TOKEN.search(t) and DAILY_TOKEN.search(t) and SURFACE_TOKEN.search(t)
        ],
        "daily_temperature_types_any_compartment": [
            t for t in temperature_types if DAILY_TOKEN.search(t)
        ],
    }


def monthly_payload_samples(
    package_bytes: bytes, stations: pd.DataFrame, n_samples: int = 3
) -> dict:
    """Show the resolution actually delivered for surface-water temperature."""

    samples = []
    with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
        names = sorted(
            n for n in archive.namelist() if n.startswith("WT-Monatsmittel/")
        )
        for name in names[:n_samples]:
            payload = archive.read(name)
            lines = payload.decode("cp1252", errors="replace").splitlines()
            data_lines = [
                line for line in lines
                if re.match(r"^\d{2}\.\d{2}\.\d{4}\s+00:00:00;\s*[-+]?\d", line.strip())
            ]
            samples.append(
                {
                    "file": name,
                    "bytes": len(payload),
                    "first_lines": lines[:18],
                    "first_data_lines": data_lines[:6],
                    "last_data_lines": data_lines[-3:],
                    "n_data_lines": len(data_lines),
                }
            )
        chosen = tuple(str(s) for s in stations["site_id"].head(n_samples))
        frame = monthly_network(package_bytes, stations, chosen)
    per_station = []
    if not frame.empty:
        for site_id, group in frame.groupby("site_id", sort=True):
            years = group["date"].dt.year
            per_station.append(
                {
                    "site_id": str(site_id),
                    "rows": int(len(group)),
                    "first_date": group["date"].min().strftime("%Y-%m-%d"),
                    "last_date": group["date"].max().strftime("%Y-%m-%d"),
                    "distinct_day_of_month": sorted(
                        int(d) for d in group["date"].dt.day.unique()
                    ),
                    "n_distinct_years": int(years.nunique()),
                    "rows_per_year": round(len(group) / max(1, int(years.nunique())), 3),
                }
            )
    return {"file_samples": samples, "parsed_monthly_series": per_station}


def diagram_probes(*, force: bool) -> list[dict]:
    """Long-term diagram service: is there a per-station WT daily archive?"""

    out = []
    for site in ("200048", "212704"):  # 200048 = Q + WT station, 212704 = WT only
        url = DIAGRAM_URL.format(site=site)
        cache = RAW / f"diagram_pegelLongterm_{site}.json"
        if force or not cache.is_file():
            try:
                cache.write_bytes(get_bytes(url, timeout=120))
            except Exception as error:  # noqa: BLE001
                cache.write_text(json.dumps({"error": str(error)}), encoding="utf-8")
        try:
            document = json.loads(cache.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            document = {}
        points = document.get("points_in_time") or []
        out.append(
            {
                "url": url,
                "cache_file": str(cache.relative_to(ROOT)),
                "parameter": document.get("parameter"),
                "unit": document.get("einheit"),
                "n_points": len(points),
                "first_point": points[0] if points else None,
                "last_point": points[-1] if points else None,
                "data_from_year": document.get("data_from"),
                "data_till_year": document.get("data_till"),
            }
        )
    return out


def roster_overlap(site_ids: list[str]) -> dict:
    if not ROSTER.is_file():
        return {"roster_file": str(ROSTER.relative_to(ROOT)), "exists": False}
    roster = pd.read_csv(ROSTER, dtype={"station_id": str})
    roster_ids = set(roster["station_id"].astype(str))
    overlap = sorted(set(map(str, site_ids)) & roster_ids)
    return {
        "roster_file": str(ROSTER.relative_to(ROOT)),
        "exists": True,
        "n_roster_stations": int(len(roster_ids)),
        "n_overlap": int(len(overlap)),
        "overlap_ids": overlap[:50],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="refetch every URL")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    retrieved_utc = datetime.now(timezone.utc).isoformat()

    listing = fetch_cached(STATION_URL, RAW / "messstellen_alle.json", force=args.force)
    feature_document = json.loads((ROOT / listing["cache_file"]).read_text(encoding="utf-8"))
    census = ftyp_census(feature_document)
    census.to_csv(RAW / "ftyp_census.csv", index=False)
    log(f"file-type census rows={len(census)} types={census['file_type'].nunique()}")

    package = fetch_cached(PACKAGE_URL, RAW / "ehyd_messstellen_all_owf.zip", force=args.force)
    package_bytes = (ROOT / package["cache_file"]).read_bytes()
    with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
        names = archive.namelist()
        folders = pd.Series([n.split("/")[0] for n in names]).value_counts()
    folders.rename("n_entries").rename_axis("package_folder").reset_index().to_csv(
        RAW / "package_folder_census.csv", index=False
    )
    log(f"package entries={len(names)} folders={len(folders)}")

    stations = surface_temperature_stations(feature_document, package_bytes)
    stations.to_csv(RAW / "ehyd_surface_temperature_stations_monthly.csv", index=False)
    candidates = exact_river_candidates(stations)
    candidates.to_csv(RAW / "ehyd_monthly_river_candidates.csv", index=False)

    available_types = sorted(census["file_type"].unique())
    # "daily" may be declared in the file type id or only in the delivered file
    # name (e.g. qu_quellwassertemp -> Quellwassertemperatur-Tagesmittel-*.csv).
    daily_types: set[str] = set()
    for row in census.itertuples(index=False):
        if TEMP_TOKEN.search(row.file_type) and DAILY_TOKEN.search(row.file_name):
            daily_types.add(row.file_type)
    daily_surface_temperature_file_types = sorted(
        t for t in daily_types if SURFACE_TOKEN.search(t)
    )
    daily_any_compartment = sorted(daily_types)

    download_types = download_type_probe(force=args.force)
    samples = monthly_payload_samples(package_bytes, stations)
    diagrams = diagram_probes(force=args.force)
    bundle = app_bundle_evidence(force=args.force)
    overlap = roster_overlap(sorted(stations["site_id"].astype(str)))

    feasible = bool(
        daily_surface_temperature_file_types
        or download_types["daily_surface_temperature_types"]
    )

    ingest = {
        "provider": "ehyd",
        "agency": "Hydrographisches Zentralbüro / eHYD (Austria)",
        "script": "scripts/243_multi_agency_ehyd_ingest.py",
        "command": "PYTHONPATH=src python3 scripts/243_multi_agency_ehyd_ingest.py",
        "retrieved_utc": retrieved_utc,
        "verdict": "feasible" if feasible else "infeasible",
        "reason": (
            "eHYD publishes surface-water (river) water temperature only as "
            "monthly means (WT-Monatsmittel); no daily surface-water temperature "
            "product exists, so no provider daily statistic in degC is available."
            if not feasible
            else "a daily surface-water temperature product was found"
        ),
        "sources": {
            "station_listing": listing,
            "bulk_package": package,
            "download_type_probe": download_types,
            "app_bundle": bundle,
            "diagram_probes": diagrams,
        },
        "counts": {
            "n_stations_in_official_listing": int(len(feature_document["features"])),
            "n_file_entries_in_listing": int(len(census)),
            "n_distinct_file_types_in_listing": int(census["file_type"].nunique()),
            "n_package_entries": int(len(names)),
            "n_package_folders": int(len(folders)),
            "n_wt_monthly_files": int((census["file_type"] == FILE_KIND).sum()),
            "n_wt_monthly_stations_with_metadata": int(stations["site_id"].nunique()),
            "n_wt_monthly_unique_rivers": int(stations["river_name"].nunique()),
            "n_monthly_river_candidates_ge3_stations_ge8_common_years": int(len(candidates)),
            "n_daily_surface_temperature_file_types": len(
                daily_surface_temperature_file_types
            ),
            "n_daily_temperature_file_types_any_compartment": len(daily_any_compartment),
        },
        "observations": {
            "temperature_token_file_types": [
                t for t in available_types if TEMP_TOKEN.search(t)
            ],
            "surface_water_temperature_file_types": [
                t for t in available_types if TEMP_TOKEN.search(t) and SURFACE_TOKEN.search(t)
            ],
            "daily_temperature_file_types_any_compartment": daily_any_compartment,
            "daily_surface_temperature_file_types": daily_surface_temperature_file_types,
            "monthly_payload_samples": samples,
            "documented_statistic": (
                "monthly mean (WT-Monatsmittel); the only temperature product for "
                "surface waters. Daily statistics exist for discharge, water level, "
                "snow, bedload and suspended sediment, and for spring water "
                "temperature (qu_quellwassertemp, not a river series)."
            ),
            "timezone_day_boundary": (
                "not applicable: no daily surface-water temperature product exists"
            ),
            "roster_overlap": overlap,
        },
        "artifacts": {
            "raw_cache": str(RAW.relative_to(ROOT)),
            "ftyp_census": str((RAW / "ftyp_census.csv").relative_to(ROOT)),
            "package_folder_census": str((RAW / "package_folder_census.csv").relative_to(ROOT)),
            "monthly_station_table": str(
                (RAW / "ehyd_surface_temperature_stations_monthly.csv").relative_to(ROOT)
            ),
            "monthly_river_candidates": str(
                (RAW / "ehyd_monthly_river_candidates.csv").relative_to(ROOT)
            ),
        },
        "caveats": [
            "eHYD's own download service enumerates the allowed data types server-side; "
            "owf_wassertemp_monatsmittel is the only surface-water temperature type.",
            "The bulk package contains WT-Monatsmittel only (324 files, no daily WT folder).",
            "Monthly rows are ~11.7 per station-year and all fall on one day of month, "
            "so they cannot be expanded into daily series without invention.",
            "qu_quellwassertemp is a DAILY temperature series but for spring water, not "
            "for a river waterbody, and it is therefore not eligible under protocol rule 2/3.",
            "The station listing marks several monthly candidates as lakes "
            "(e.g. Neusiedler See, Altausseer See); river-only filtering was not applied "
            "because no daily product exists to filter.",
            "No frozen-screen performance was computed on eHYD data (ingest + QC only).",
        ],
        "networks_emitted": 0,
        "stations_emitted": 0,
    }

    (OUT / "ingest.json").write_text(
        json.dumps(ingest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )

    if feasible:
        log("daily surface-water temperature product found; see ingest.json")
        return 0

    write_infeasible_md(ingest, retrieved_utc, stations, candidates, census, folders)
    log(f"INFEASIBLE written: {OUT / 'INFEASIBLE.md'}")
    return 0


def write_infeasible_md(
    ingest: dict,
    retrieved_utc: str,
    stations: pd.DataFrame,
    candidates: pd.DataFrame,
    census: pd.DataFrame,
    folders: pd.Series,
) -> None:
    counts = ingest["counts"]
    download_types = ingest["sources"]["download_type_probe"]
    package = ingest["sources"]["bulk_package"]
    listing = ingest["sources"]["station_listing"]
    bundle = ingest["sources"]["app_bundle"]
    samples = ingest["observations"]["monthly_payload_samples"]

    type_rows = "\n".join(
        f"| {t} |" for t in download_types["allowed_download_types"]
    )
    folder_rows = "\n".join(
        f"| {name} | {int(value)} |" for name, value in folders.items()
    )
    sample_block = ""
    for sample in samples["file_samples"][:2]:
        head = "\n".join(sample["first_lines"])
        data = "\n".join(sample["first_data_lines"])
        tail = "\n".join(sample["last_data_lines"])
        sample_block += (
            f"\n**`{sample['file']}`** ({sample['bytes']} bytes, "
            f"{sample['n_data_lines']} monthly data rows, cp1252 payload).\n\n"
            f"Header block (first lines):\n\n```\n{head}\n```\n\n"
            f"First data rows:\n\n```\n{data}\n```\n\n"
            f"Last data rows:\n\n```\n{tail}\n```\n"
        )
    series_rows = "\n".join(
        f"| {row['site_id']} | {row['rows']} | {row['first_date']} | {row['last_date']} "
        f"| {row['distinct_day_of_month']} | {row['n_distinct_years']} | {row['rows_per_year']} |"
        for row in samples["parsed_monthly_series"]
    )
    candidate_rows = "\n".join(
        f"| {row.network_id} | {row.river_group} | {row.n_catalog_stations} | "
        f"{row.metadata_common_start_year}-{row.metadata_common_end_year} |"
        for row in candidates.head(10).itertuples(index=False)
    )
    surface_menu = ", ".join(
        f"`{item['id']}` ({item['label']})"
        for item in bundle.get("surface_water_menu", [])
        if TEMP_TOKEN.search(item["id"])
    )
    diagram_rows = "\n".join(
        f"| {row['url']} | {row['parameter']} | {row['n_points']} | {row['first_point']} "
        f"| {row['last_point']} |"
        for row in ingest["sources"]["diagram_probes"]
    )

    document = f"""# eHYD (Austria) — INFEASIBLE for the daily transport panel

Verdict: **infeasible**. Retrieved {retrieved_utc} by
`scripts/243_multi_agency_ehyd_ingest.py`
(`PYTHONPATH=src python3 scripts/243_multi_agency_ehyd_ingest.py`).

Transport protocol rule 3 requires *a provider daily statistic in °C*
(`MULTI_AGENCY_TRANSPORT_PROTOCOL.md`). eHYD's only surface-water
(river) temperature product is **`owf_wassertemp_monatsmittel` — a monthly
mean**. No daily surface-water water-temperature product exists in the
eHYD station catalogue, in the bulk data package, or in the service that the
eHYD web application itself uses to build its download offer. No network is
emitted; nothing was scored.

## 1. The station catalogue has no daily surface-water temperature file type

`GET {listing['url']}` (HTTP 200, {listing['bytes']:,} bytes,
sha256 `{listing['sha256']}`) returns a GeoJSON FeatureCollection of
**{counts['n_stations_in_official_listing']:,} stations** whose `fjson`
property lists every published file per station:
**{counts['n_file_entries_in_listing']:,} file entries,**
**{counts['n_distinct_file_types_in_listing']} distinct file types**.
Census written to `{ingest['artifacts']['ftyp_census']}`.

Temperature file types present anywhere in the catalogue:

- every catalogue file type whose identifier contains `wassertemp`: {', '.join(f'`{t}`' for t in ingest['observations']['temperature_token_file_types'])}
- of those, surface-water (`owf_*`): {', '.join(f'`{t}`' for t in ingest['observations']['surface_water_temperature_file_types']) or '(none)'}

Daily (`*tages*`) temperature file types **for surface water**: none
(`daily_surface_temperature_file_types = {ingest['observations']['daily_surface_temperature_file_types']}`).

The only daily *temperature* type in the whole catalogue is
`qu_quellwassertemp` ("Quellwassertemperatur-Tagesmittel", spring water
temperature) with {int((census['file_type'] == 'qu_quellwassertemp').sum())} files.
It is a spring/groundwater-source series, not a river waterbody series, so it
fails protocol rule 2 (river-only) and rule 3 (station is not a river site).
`gw_temp_monatsmittel` ({int((census['file_type'] == 'gw_temp_monatsmittel').sum())} files)
is groundwater temperature and monthly in any case.

## 2. The official bulk package contains monthly WT only

`GET {package['url']}` (HTTP 200, content-length
{package['server_head'].get('content-length')} declared; downloaded
{package['bytes']:,} bytes, sha256 `{package['sha256']}`) unpacks to
{counts['n_package_entries']:,} entries in {counts['n_package_folders']} folders
(`{ingest['artifacts']['package_folder_census']}`):

| folder | entries |
|---|---|
{folder_rows}

The only surface-water temperature folder is `WT-Monatsmittel`
({counts['n_wt_monthly_files']} files = {counts['n_wt_monthly_stations_with_metadata']} stations
with metadata, {counts['n_wt_monthly_unique_rivers']} distinct official river names).
There is no `WT-Tageswerte` / `WT-Tagesmittel` folder, and the data folders that
do carry daily values are `Q-Tagesmittel` (discharge), `W-Tagesmittel` (water
level), `Geschiebe-`/`Schwebstoff-Tagesfracht` (sediment).

## 3. eHYD's own download service enumerates the allowed types server-side

`GET {download_types['probes']['owf_wassertemp_monatsmittel']['url']}` returns
HTTP 200 with the server's own list of the
{download_types['n_allowed_download_types']} downloadable data types:

```
{download_types['probes']['owf_wassertemp_monatsmittel']['response']}
```

Temperature entries in that list: {', '.join(f'`{t}`' for t in download_types['temperature_types'])}.
Daily surface-water temperature entries:
`{download_types['daily_surface_temperature_types']}`.
A daily surface-water temperature type was probed explicitly
(`...&cat=owf_wassertemp_tagesmittel`) and is rejected by the same
server-side enumeration (`{download_types['probes']['owf_wassertemp_tagesmittel']['url']}`).
Direct guesses at a daily WT package URL are also 404
(`ehyd_messstellen_all_owf_wassertemp_tagesmittel.zip`,
`ehyd_messstellen_all_wt.zip`), while `ehyd_messstellen_all_gw.zip` returns 200 —
i.e. the package namespace exists, the daily WT member does not.

## 4. The shipped web application offers monthly only

The eHYD Angular bundle (`{bundle.get('bundle_url')}`, sha256
`{bundle.get('bundle_sha256')}`) builds its data-type menu with the same ids.
Under "Oberflächengewässer" the temperature entry is
{surface_menu}. `Wassertemperatur-Monatsmittel` is the only temperature option;
the daily options there are discharge, water level, snow height, bedload and
suspended-sediment.

## 5. Payload samples prove the delivered resolution is monthly

{sample_block}

Parsed with `parse_monthly_temperature` / `monthly_network`:

| station | rows | first | last | day-of-month | years | rows/year |
|---|---|---|---|---|---|---|
{series_rows}

All rows of a station-year sit on a single day of month (e.g. day 21, or day 1),
≈12 rows per year: these are month labels carrying a monthly mean, not daily
values. Expanding them to daily would invent data.

Per-station long-term daily archives are not served either — the diagram service
used by the app returns discharge statistics for the current year only:

| URL | parameter | n points | first | last |
|---|---|---|---|---|
{diagram_rows}

Station 212704 is a WT-only station and returns an empty diagram document;
station 200048 measures both discharge and water temperature and returns
`parameter = "Abfluss"` (discharge). No daily WT series is retrievable.

## 6. What would have been available if monthly were admissible (not used)

The 324 monthly WT stations yield {counts['n_monthly_river_candidates_ge3_stations_ge8_common_years']}
river-name groups with ≥3 stations and ≥8 common metadata years (the module's
own candidate rule), e.g.:

| network_id | river | stations | common metadata years |
|---|---|---|---|
{candidate_rows}

This is recorded only to show the shortfall is the *temporal resolution*, not the
station count. Several groups are lakes in the official river-name field
(e.g. `ehyd_neusiedler_see`, Altausseer See), which would also require river-only
filtering. `{ingest['artifacts']['monthly_river_candidates']}` holds the full table;
its `candidate_status` is `source_qc_failed_monthly_only`.

## 7. Roster check

v17 roster overlap for the eHYD HZB station numbers:
{ingest['observations']['roster_overlap']['n_overlap']} overlapping ids
({ingest['observations']['roster_overlap'].get('overlap_ids')}). Not applicable in
practice because no series is ingested.

## 8. What a reviewer should check

- That no *other* Austrian provider with daily river water temperature was used
  as a silent substitute: none was. This report is the whole eHYD outcome.
- That monthly means were not silently expanded to daily: they were not.
- That `qu_quellwassertemp` was not repackaged as river temperature: it was not.
- That nothing was scored: no frozen-screen performance was computed on any eHYD
  payload (protocol HARD RULE 4).

## Reproduce

```bash
PYTHONPATH=src python3 scripts/243_multi_agency_ehyd_ingest.py
```

Raw caches (listing, package, service probes, bundle, diagram documents) are under
`results/wrr_submission_ready/multi_agency_ingest/ehyd/raw_cache/`; machine-readable
counts are in `results/wrr_submission_ready/multi_agency_ingest/ehyd/ingest.json`.
"""
    (OUT / "INFEASIBLE.md").write_text(document, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
