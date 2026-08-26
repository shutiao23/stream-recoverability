#!/usr/bin/env python3
"""Build the HUC8 catalog v3 from on-disk USGS metadata.

Reads catalog start/end dates already on disk. Does not download daily
temperature values. Does not open sealed temperatures. Does not rewrite
network_catalog_v1.yaml or design_freeze_v9.yaml. Loire and Swiss
Aare-Rhine are not counted toward T8 or non-NA sealed.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.nldi_connectivity import (
    NLDI_DISTANCE_KM,
    assess_clusters_flow_connectivity,
    nwis_match_key,
)
from stream_recoverability.data.public_river_inventory import (
    cluster_by_huc8,
    cluster_rivers_from_catalog,
    cluster_rivers_from_catalog_v2,
    naive_huc_zfill_prefix,
    official_huc_prefix,
)

OUTPUT = ROOT / "results/framework/public_catalog"
SERIES = OUTPUT / "usgs_daily_temperature_series.csv"
LOCATIONS = OUTPUT / "usgs_long_temperature_locations.csv"
FREEZE = ROOT / "configs/design_freeze_v9.yaml"
V1_CATALOG = ROOT / "configs/network_catalog_v1.yaml"
CANDIDATES = ROOT / "configs/network_catalog_v3_huc8.yaml"
SPLIT_YAML = ROOT / "configs/network_catalog_v3_split.yaml"
FEASIBILITY = ROOT / "docs/network_catalog_v3_feasibility.md"
SHA_PATH = OUTPUT / "catalog_v3_split_sha256.txt"
SPLIT_TABLE = OUTPUT / "catalog_v3_split_table.csv"
NLDI_CACHE = OUTPUT / "nldi_cache"
GAGES_ARCHIVE = ROOT / "data/cache/regulation_panel_v1/basinchar_and_report_sept_2011.zip"

SPLIT_SEED = 20260826
HUC_CLIMATE = {
    "01": "humid_continental",
    "02": "humid_continental",
    "03": "humid_subtropical",
    "04": "humid_continental",
    "05": "humid_continental",
    "06": "humid_subtropical",
    "07": "humid_continental",
    "10": "cold_semiarid",
    "11": "humid_subtropical",
    "12": "subtropical_semiarid",
    "13": "cold_arid_highland",
    "14": "cold_arid_highland",
    "15": "hot_arid",
    "16": "cold_semiarid",
    "17": "marine_west_coast",
    "18": "mediterranean",
    "19": "subarctic",
    "20": "humid_continental",
}
NEVER_SEALED_NAME_TOKENS = (
    "jinsha",
    "chattahoochee",
    "delaware river",
    "willamette river",
    "suwannee river",
    "yellowstone river",
    "rio grande",
    "madison river",
    "cahaba river",
    "mckenzie river",
    "mahoning river",
    "roanoke river",
    "santa fe river",
    "clearwater river",
)
HISTORICAL_TOKENS = ("jinsha", "chattahoochee")
CANONICAL_SPLIT_COLUMNS = (
    "network_id",
    "role",
    "seed",
    "climate_band",
    "size_tertile",
    "regulation_stratum",
)


class _QuotedSiteId(str):
    """Keep USGS site numbers as quoted strings so leading zeros survive YAML."""


def _quoted_site_representer(dumper: yaml.Dumper, data: _QuotedSiteId) -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style="'")


class _CandidateDumper(yaml.SafeDumper):
    pass


_CandidateDumper.add_representer(_QuotedSiteId, _quoted_site_representer)


def _read_catalog(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"site_id": str, "huc": str, "name": str})


def _site_list(value: object) -> list[str]:
    return [item for item in str(value or "").split(",") if item]


def load_gages_major_dams(archive: Path) -> pd.DataFrame | None:
    if not archive.is_file():
        return None
    with zipfile.ZipFile(archive) as outer:
        nested = outer.read("spreadsheets-in-csv-format.zip")
    with zipfile.ZipFile(io.BytesIO(nested)) as inner:
        pieces = []
        for prefix in ("conterm", "AKHIPR"):
            dams = pd.read_csv(
                inner.open(f"{prefix}_hydromod_dams.txt"),
                dtype={"STAID": str},
                encoding="cp1252",
            )
            pieces.append(dams[["STAID", "MAJ_NDAMS_2009"]].copy())
    frame = pd.concat(pieces, ignore_index=True)
    frame["STAID"] = frame["STAID"].astype(str).str.strip().str.zfill(8)
    return frame.drop_duplicates("STAID")


def _staid_key(site_id: str) -> str:
    digits = re.sub(r"\D", "", str(site_id))
    if not digits:
        return ""
    if len(digits) <= 8:
        return digits.zfill(8)
    return digits


def regulation_stratum(site_ids: list[str], gages: pd.DataFrame | None) -> str:
    if gages is None:
        return "unknown_until_gages"
    keys = {_staid_key(item) for item in site_ids if _staid_key(item)}
    matched = gages.loc[gages["STAID"].isin(keys)]
    if matched.empty:
        return "unmatched_gages"
    major = pd.to_numeric(matched["MAJ_NDAMS_2009"], errors="coerce")
    if major.ge(1).any():
        return "regulated"
    return "unregulated"


def _never_sealed_site_keys(v1: dict, never_ids: list[str]) -> set[str]:
    wanted = set(never_ids)
    keys: set[str] = set()
    for network in v1.get("networks") or []:
        network_id = str(network.get("network_id") or "")
        if network_id not in wanted:
            continue
        for site_id in network.get("candidate_station_ids") or []:
            key = nwis_match_key(site_id)
            if key:
                keys.add(key)
    return keys


def classify_lock_flags(row: pd.Series, burned_site_keys: set[str]) -> tuple[bool, bool]:
    haystack = f"{row.get('river_names') or ''} {row.get('network_id') or ''}".lower()
    historical = any(token in haystack for token in HISTORICAL_TOKENS)
    name_hit = any(token in haystack for token in NEVER_SEALED_NAME_TOKENS)
    site_hit = bool({nwis_match_key(item) for item in _site_list(row.get("site_ids"))} & burned_site_keys)
    return bool(historical or name_hit or site_hit), bool(historical)


def climate_band(huc2: object) -> str:
    return HUC_CLIMATE.get(str(huc2 or ""), "unspecified")


def assign_split_roles(pool: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Stratify remaining candidates on climate_band × size tertile."""

    if pool.empty:
        return pool
    rng = np.random.default_rng(int(seed))
    work = pool.sort_values("network_id").copy()
    ranks = pd.to_numeric(work["n_stations"], errors="coerce").rank(method="first")
    if len(work) < 3:
        work["size_tertile"] = "T1_small"
    else:
        try:
            work["size_tertile"] = pd.qcut(
                ranks, 3, labels=["T1_small", "T2_mid", "T3_large"]
            ).astype(str)
        except ValueError:
            work["size_tertile"] = "T1_small"
    work["climate_band"] = work["huc2"].map(climate_band)
    work["stratum"] = work["climate_band"] + "|" + work["size_tertile"]
    pieces = []
    for _, group in work.groupby("stratum", sort=True):
        group = group.sort_values("network_id")
        order = rng.permutation(len(group))
        pieces.append(group.iloc[list(order)])
    shuffled = pd.concat(pieces, ignore_index=True)
    n = len(shuffled)
    n_dev = int(round(n * 0.50))
    n_val = int(round(n * 0.20))
    if n_dev + n_val > n:
        n_val = max(0, n - n_dev)
    # Shuffle inside climate × size strata, then cut 50/20/30 on the
    # concatenated order. Per-stratum integer division dumped remainders
    # into sealed (small strata got 0 validation). Global cut hits the
    # locked fractions; strata only randomize order.
    shuffled["role"] = (
        ["development"] * n_dev
        + ["validation"] * n_val
        + ["sealed"] * (n - n_dev - n_val)
    )
    return shuffled


def canonical_split_text(frame: pd.DataFrame, seed: int) -> str:
    table = frame.loc[:, list(CANONICAL_SPLIT_COLUMNS)].copy()
    table["seed"] = int(seed)
    table = table.sort_values("network_id").reset_index(drop=True)
    return table.to_csv(index=False, lineterminator="\n")


def _candidate_entry(row: pd.Series) -> dict:
    site_ids = [_QuotedSiteId(item) for item in _site_list(row.site_ids)]
    historical = bool(row.historical)
    never_sealed = bool(row.never_sealed) or historical
    flow = str(row.get("flow_connected") or "not_queried")
    max_km = pd.to_numeric(pd.Series([row.get("max_pair_km")]), errors="coerce").iloc[0]
    return {
        "network_id": str(row.network_id),
        "display_name": f"{row.river_names} (HUC8 {row.huc8})",
        "split_role": "historical" if historical else "catalog_candidate",
        "historical_seen": historical,
        "never_sealed": never_sealed,
        "climate_or_ecoregion": climate_band(row.huc2),
        "regulation_stratum": str(row.regulation_stratum),
        "candidate_station_ids": site_ids,
        "temperature_record_unverified": True,
        "sealed_outcomes_opened": False,
        "feasibility_status": "catalog_v3_huc8_subset_overlap_only",
        "use": "already_used" if historical else "catalog_v3_candidate",
        "grouping": "huc8",
        "flow_connected": flow,
        "spatially_proximate_not_flow_connected": flow in {"false", "partial"},
        "notes": (
            f"Largest concurrent HUC8 subset: {int(row.n_stations)} stations, "
            f"catalog overlap about {float(row.catalog_overlap_years):.1f} years, "
            f"max pairwise {('unknown' if pd.isna(max_km) else f'{float(max_km):.1f} km')}, NLDI {flow}. "
            "Metadata only. Temperatures not downloaded."
            + (" Never sealed." if never_sealed else "")
            + (" Historical." if historical else "")
        ),
    }


def _missouri_split(
    contrast: pd.DataFrame, huc8: pd.DataFrame, stations: pd.DataFrame
) -> str:
    if contrast.empty:
        return "missouri_river_huc10 was not present in the name×HUC2 contrast."
    match = contrast.loc[contrast["network_id"].eq("missouri_river_huc10")]
    if match.empty:
        return "missouri_river_huc10 was not present in the name×HUC2 contrast."
    if "rule" in match.columns:
        v2 = match.loc[match["rule"].eq("name_huc2_v2_subset_3st_8y")]
        if not v2.empty:
            match = v2
    sites = _site_list(match.iloc[0]["site_ids"])
    site_keys = {nwis_match_key(item) for item in sites}
    occupancy: list[str] = []
    if not stations.empty and "site_id" in stations.columns:
        for row in stations.itertuples(index=False):
            if nwis_match_key(getattr(row, "site_id", "")) not in site_keys:
                continue
            prefix = official_huc_prefix(getattr(row, "huc", ""), 8)
            if prefix:
                occupancy.append(prefix)
    occupancy_ids = sorted(set(occupancy))
    hit = []
    for row in huc8.itertuples(index=False):
        keys = {nwis_match_key(item) for item in _site_list(row.site_ids)}
        if keys & site_keys:
            hit.append(str(row.network_id))
    hit = sorted(set(hit))
    occupancy_text = ", ".join(occupancy_ids) if occupancy_ids else "none"
    hit_text = ", ".join(hit) if hit else "none"
    return (
        f"name×HUC2 `missouri_river_huc10` has {len(sites)} catalog stations; "
        f"those stations occupy {len(occupancy_ids)} HUC8 codes ({occupancy_text}). "
        f"{len(hit)} of those HUC8s currently form a 3-station/8-year cluster that "
        f"still contains Missouri sites ({hit_text}). The name×HUC2 token does not "
        "survive as one HUC8 network."
    )


def write_feasibility(payload: dict) -> str:
    counts = payload["counts"]
    nldi = payload["nldi"]
    split = payload["split"]
    n8 = counts["huc8_3st_8y"]
    retained = int(round(n8 * 0.65))
    lines = [
        "# Catalog v3 feasibility (HUC8 grouping-rule correction)",
        "",
        "This is a station-year inventory, not a recovery score. Daily temperature",
        "values were not downloaded. Sealed temperatures were not opened. The 12",
        "already-downloaded rivers and Jinsha / Chattahoochee were inherited as",
        "`never_sealed` and were **not** remapped into sealed. Loire and Swiss",
        "Aare-Rhine are **not** in this USGS HUC8 catalog and still cannot count",
        "toward T8 or the 10 non-North-America sealed networks until public dated",
        "daily values exist.",
        "",
        "## This is a grouping-rule correction, not a relaxation",
        "",
        "v1 and v2 name×HUC2 group by watercourse name inside a 2-digit region.",
        "That both splits real networks (renamed tributaries) and invents fake ones",
        "(one Missouri-in-HUC2-10 cluster spanning many subbasins). HUC8 grouping",
        "is spatially **stricter**: it is a subbasin, not a region. Official USGS",
        "HUC prefixes are used (`official_huc_prefix`). The reviewer's",
        "`str(huc).zfill(8)[:8]` is the intent for 7-digit codes such as `3130004`;",
        "`official_huc_prefix` is the correct implementation for catalog values",
        "such as `190101060106.0` and `11000020108`.",
        "",
        "Within each HUC8, `largest_overlapping_subset` keeps the largest set whose",
        "interval intersection is at least T years. The search is exact (interval",
        "scan over begin dates). **Nothing was truncated at 12 stations.** A",
        "truncated combo search (n>12 → 12) still yields the same *network* count",
        f"on this catalog (**{n8}**); it only undercounts `n_stations` inside large",
        "groups. The reviewer's published **161** is reproduced exactly by naive",
        "`str(huc).zfill(8)[:8]`, not by truncation.",
        "",
        f"- Exact HUC8 3-station / 8-year count (`official_huc_prefix`): **{n8}**.",
        f"- Naive `zfill(8)[:8]` HUC8 3-station / 8-year count: **{counts.get('huc8_3st_8y_naive_zfill', 'n/a')}**.",
        f"- {payload['missouri']}",
        "",
        "## Catalog span is not data density",
        "",
        "`daily_begin` / `daily_end` are first/last catalog dates. Qualified years",
        "happen after download and QC. Expected post-download attrition is 25–40%.",
        f"{n8} × 0.65 ≈ {retained} still clears `n_networks_min` 100 if that attrition",
        "holds. 150 still needs Europe and/or a documented 3-station / 6-year",
        "failure-closure. This file does not relax T2.",
        "",
        "## Counts",
        "",
        "| grouping | 3 stations / 8 years | 4 stations / 8 years |",
        "| --- | ---: | ---: |",
        f"| name×HUC2 (v2 subset, official HUC2) | {counts['name_huc2_3st_8y']} | {counts['name_huc2_4st_8y']} |",
        f"| HUC4-only (official prefix, exact subset) | {counts['huc4_3st_8y']} | {counts['huc4_4st_8y']} |",
        f"| HUC6-only (official prefix, exact subset) | {counts['huc6_3st_8y']} | {counts['huc6_4st_8y']} |",
        f"| HUC8-only (official prefix, exact subset) | {counts['huc8_3st_8y']} | {counts['huc8_4st_8y']} |",
        f"| HUC8 naive zfill(8)[:8] (diagnostic, not the rule) | {counts['huc8_3st_8y_naive_zfill']} | — |",
        f"| HUC8, max pairwise ≤ 100 km | {counts['huc8_3st_8y_max100km']} | {counts['huc8_4st_8y_max100km']} |",
        f"| HUC8, max pairwise ≤ 50 km | {counts['huc8_3st_8y_max50km']} | {counts['huc8_4st_8y_max50km']} |",
        "",
        f"v1 name×HUC2 whole-group overlap (4 stations / 8 years, raw HUC prefix): {counts['v1_name_huc2_4st_8y']}.",
        "",
        "Spatial-filter policy: compute the overlap subset first, then **omit**",
        "groups whose maximum pairwise geodesic distance (haversine, Earth radius",
        "6371 km) exceeds the cap. Groups are not silently shrunk.",
        "",
        f"Long-station filter: catalog span ≥ 8 years, matching the v2 builder's",
        "8-year case. Stream / ST / Streamgage only.",
        "",
        "## NLDI flow connectivity",
        "",
        "HUC8 does not guarantee flow connectivity. Each group is queried from its",
        "median station (lat, then lon, then site_id) on NLDI UM and DM at 200 km.",
        "Disconnected groups are **retained** as covariate",
        "`spatially_proximate_not_flow_connected` (true when NLDI status is",
        "`false` or `partial`). Connectivity is not faked.",
        "",
        f"- queried distance: {nldi['distance_km']} km",
        f"- true (all other stations on UM∪DM): {nldi['true']}",
        f"- partial: {nldi['partial']}",
        f"- false (none besides origin): {nldi['false']}",
        f"- not_queried (API failed after retries; cache of successes kept): {nldi['not_queried']}",
        f"- cache directory: `{nldi['cache_dir']}`",
        f"- {nldi['note']}",
        "",
        "## Split lock (before any new download)",
        "",
        f"- seed: {split['seed']}",
        f"- SHA-256 of canonical split table: `{split['sha256']}`",
        f"- split pool (excluding never_sealed and historical): {split['n_pool']}",
        f"- development / validation / sealed: {split['n_development']} / {split['n_validation']} / {split['n_sealed']}",
        "- assignment: shuffle inside climate × size strata, then cut 50/20/30 on the concatenated order so small strata cannot dump remainders into sealed.",
        f"- never_sealed excluded from random split: {split['n_never_sealed']}",
        f"- historical excluded from random split: {split['n_historical']}",
        f"- sealed ≥ 40 is a **target after Europe**. USGS-only sealed count is {split['n_sealed']}.",
        f"- non-North-America sealed: {split['n_non_na_sealed']} (target 10). Loire/Swiss were not placed in sealed.",
        f"- regulation_stratum: {split['regulation_note']}",
        f"- {split['shortfall']}",
        "",
        "Strata for the random assignment are climate_band (HUC2 map from",
        "scripts/55) × network-size tertiles (`rank(method='first')` because",
        "`n_stations` piles up at 3). GAGES-II `MAJ_NDAMS_2009` is joined as",
        "`regulation_stratum` and written on every row; it is **not** a third",
        "random-split axis, because unmatched STAID cells would be an incomplete",
        "factor. Dam labels were not invented from river names.",
        "",
        "never_sealed networks do not appear as `split_role: sealed`.",
        "",
        "## Honesty",
        "",
        "- Exact max-overlap subset search; no 12-station truncation.",
        "- Spatial filter omits over-wide groups; it does not drop the farthest",
        "  station to salvage a cluster.",
        "- Reviewer 161 equals naive zfill on this catalog; truncated combo does not.",
        "- Catalog overlap is not concurrent daily completeness.",
        "- DEFAULT_CATALOG remains `configs/network_catalog_v1.yaml`.",
        "- This script does not rewrite `configs/design_freeze_v9.yaml` or",
        "  `network_catalog_v1.yaml`. Split artifacts are separate files.",
        "- design_freeze_v4 was not retargeted. Sealed temperatures were not opened.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    if not SERIES.is_file() or not LOCATIONS.is_file():
        raise SystemExit("need on-disk USGS catalog CSVs; do not download values here")
    series = _read_catalog(SERIES)
    locations = _read_catalog(LOCATIONS)
    freeze = yaml.safe_load(FREEZE.read_text(encoding="utf-8"))
    never_ids = list((freeze.get("split_rule") or {}).get("never_sealed_networks") or [])
    v1_doc = yaml.safe_load(V1_CATALOG.read_text(encoding="utf-8"))
    burned_keys = _never_sealed_site_keys(v1_doc, never_ids)
    gages = load_gages_major_dams(GAGES_ARCHIVE)
    regulation_note = (
        "GAGES-II hydromod_dams is on disk; regulation_stratum is regulated / "
        "unregulated / unmatched_gages from MAJ_NDAMS_2009. Incomplete until every "
        "candidate STAID matches."
        if gages is not None
        else "GAGES-II archive was not on disk; regulation_stratum is unknown_until_gages."
    )

    print("clustering HUC4/HUC6/HUC8 and name×HUC2 contrast", flush=True)
    v1 = cluster_rivers_from_catalog(series, locations)
    v1_ok_n = int(v1["enough_overlap_years"].fillna(False).sum()) if not v1.empty else 0
    contrast_parts = []
    if not v1.empty:
        v1 = v1.copy()
        v1["rule"] = "name_huc2_v1_whole_group"
        contrast_parts.append(v1)
    for min_stations in (3, 4):
        chunk = cluster_rivers_from_catalog_v2(
            series,
            locations,
            min_stations=min_stations,
            min_overlap_years=8.0,
            min_span_years=8.0,
            huc_levels=("huc2",),
            include_huc8_only=False,
        )
        if not chunk.empty:
            chunk = chunk.copy()
            chunk["rule"] = f"name_huc2_v2_subset_{min_stations}st_8y"
            contrast_parts.append(chunk)
    contrast = pd.concat(contrast_parts, ignore_index=True) if contrast_parts else pd.DataFrame()

    def _huc_counts(width: int, min_stations: int, cap: float | None = None) -> int:
        frame = cluster_by_huc8(
            series,
            locations,
            min_stations=min_stations,
            min_overlap_years=8,
            max_pair_km=cap,
            huc_width=width,
        )
        return int(len(frame))

    huc8_unfiltered = cluster_by_huc8(series, locations, min_stations=3, min_overlap_years=8)
    huc8_100 = cluster_by_huc8(
        series, locations, min_stations=3, min_overlap_years=8, max_pair_km=100
    )
    huc8_50 = cluster_by_huc8(
        series, locations, min_stations=3, min_overlap_years=8, max_pair_km=50
    )
    huc8_4 = cluster_by_huc8(series, locations, min_stations=4, min_overlap_years=8)
    huc8_4_100 = cluster_by_huc8(
        series, locations, min_stations=4, min_overlap_years=8, max_pair_km=100
    )
    huc8_4_50 = cluster_by_huc8(
        series, locations, min_stations=4, min_overlap_years=8, max_pair_km=50
    )

    print(
        "huc8 3st/8y",
        len(huc8_unfiltered),
        "max100",
        len(huc8_100),
        "max50",
        len(huc8_50),
        "4st",
        len(huc8_4),
        flush=True,
    )

    print("querying NLDI UM/DM (cache-first; failures stay not_queried)", flush=True)
    stations = series.copy()
    if not locations.empty:
        stations = series.merge(locations, on="site_id", how="left", suffixes=("", "_loc"))
        for column in ("latitude", "longitude", "name", "huc", "site_type"):
            loc_column = f"{column}_loc"
            if column not in stations.columns and loc_column in stations.columns:
                stations[column] = stations[loc_column]
            elif column in stations.columns and loc_column in stations.columns:
                stations[column] = stations[column].where(
                    stations[column].notna(), stations[loc_column]
                )
    NLDI_CACHE.mkdir(parents=True, exist_ok=True)
    huc8_nldi = assess_clusters_flow_connectivity(
        huc8_unfiltered,
        stations,
        cache_dir=NLDI_CACHE,
        distance_km=NLDI_DISTANCE_KM,
        pause_s=0.15,
        timeout=90,
    )
    nldi_cols = [
        "network_id",
        "flow_connected",
        "n_connected_stations",
        "spatially_proximate_not_flow_connected",
        "origin_site_id",
        "connected_site_ids",
        "nldi_distance_km",
    ]
    nldi_cols = [column for column in nldi_cols if column in huc8_nldi.columns]
    nldi_lookup = huc8_nldi[nldi_cols].copy()

    def _with_nldi(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        return frame.merge(nldi_lookup, on="network_id", how="left")

    huc8_export = pd.concat(
        [huc8_nldi, _with_nldi(huc8_100), _with_nldi(huc8_50)],
        ignore_index=True,
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    huc8_export.to_csv(OUTPUT / "usgs_river_clusters_v3_huc8.csv", index=False)
    contrast.to_csv(OUTPUT / "usgs_river_clusters_v1_name_huc2_contrast.csv", index=False)

    def _v2_name_count(min_stations: int) -> int:
        if contrast.empty:
            return 0
        keep = contrast["rule"].eq(f"name_huc2_v2_subset_{min_stations}st_8y")
        if "enough_overlap_years" in contrast.columns:
            keep = keep & contrast["enough_overlap_years"].fillna(False)
        return int(contrast.loc[keep, "network_id"].nunique())

    counts = {
        "v1_name_huc2_4st_8y": v1_ok_n,
        "name_huc2_3st_8y": _v2_name_count(3),
        "name_huc2_4st_8y": _v2_name_count(4),
        "huc4_3st_8y": _huc_counts(4, 3),
        "huc4_4st_8y": _huc_counts(4, 4),
        "huc6_3st_8y": _huc_counts(6, 3),
        "huc6_4st_8y": _huc_counts(6, 4),
        "huc8_3st_8y": int(len(huc8_unfiltered)),
        "huc8_3st_8y_naive_zfill": int(
            len(
                cluster_by_huc8(
                    series,
                    locations,
                    min_stations=3,
                    min_overlap_years=8,
                    huc_prefix=naive_huc_zfill_prefix,
                )
            )
        ),
        "huc8_4st_8y": int(len(huc8_4)),
        "huc8_3st_8y_max100km": int(len(huc8_100)),
        "huc8_3st_8y_max50km": int(len(huc8_50)),
        "huc8_4st_8y_max100km": int(len(huc8_4_100)),
        "huc8_4st_8y_max50km": int(len(huc8_4_50)),
    }

    base = huc8_nldi.copy()
    flags = [classify_lock_flags(row, burned_keys) for _, row in base.iterrows()]
    base["never_sealed"] = [item[0] for item in flags]
    base["historical"] = [item[1] for item in flags]
    base["regulation_stratum"] = [
        regulation_stratum(_site_list(row.site_ids), gages) for row in base.itertuples(index=False)
    ]
    base["climate_band"] = base["huc2"].map(climate_band)

    document = {
        "catalog_id": "network_catalog_v3_huc8",
        "status": "metadata_only_candidates",
        "frozen_on": "2026-08-26",
        "sealed_outcomes_opened": False,
        "temperature_records_unverified": True,
        "default_catalog_unchanged": "configs/network_catalog_v1.yaml",
        "design_freeze_v9_edited": False,
        "note": (
            "Metadata-only v3 HUC8 candidates from public USGS catalog dates. "
            "Grouping-rule correction, not a relaxation. Not a remapping of "
            "network_catalog_v1. Sealed outcomes are unopened. Jinsha, "
            "Chattahoochee, and the 12 burned rivers are never sealed. Loire and "
            "Swiss Aare-Rhine are omitted and do not count toward T8. Split roles "
            "other than historical/catalog_candidate live in network_catalog_v3_split.yaml."
        ),
        "target_independent_networks": 150,
        "exact_huc8_3st_8y_count": counts["huc8_3st_8y"],
        "networks": [_candidate_entry(row) for _, row in base.iterrows()]
        if not base.empty
        else [],
    }
    if any(item.get("sealed_outcomes_opened") for item in document["networks"]):
        raise SystemExit("refusing to write opened sealed flags")
    if any(item.get("temperature_record_unverified") is not True for item in document["networks"]):
        raise SystemExit("every new network must stay temperature-unverified")
    if any(item.get("split_role") == "sealed" for item in document["networks"]):
        raise SystemExit("refusing to assign sealed roles in v3 candidates yaml")
    if any(
        item.get("never_sealed") and item.get("split_role") == "sealed"
        for item in document["networks"]
    ):
        raise SystemExit("never_sealed network assigned sealed")
    CANDIDATES.write_text(
        yaml.dump(document, Dumper=_CandidateDumper, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    historical = base.loc[base["historical"]].copy()
    never_pool = base.loc[base["never_sealed"] & ~base["historical"]].copy()
    pool = base.loc[~base["never_sealed"] & ~base["historical"]].copy()
    assigned = assign_split_roles(pool, SPLIT_SEED)
    if assigned.empty:
        assigned = pool.copy()
        assigned["role"] = pd.Series(dtype=object)
        assigned["size_tertile"] = pd.Series(dtype=object)
    split_rows = []
    for frame, role in (
        (assigned, None),
        (never_pool, "never_sealed"),
        (historical, "historical"),
    ):
        if frame.empty:
            continue
        piece = frame.copy()
        if role is not None:
            piece["role"] = role
            piece["size_tertile"] = "excluded"
        piece["seed"] = SPLIT_SEED
        if "climate_band" not in piece.columns:
            piece["climate_band"] = piece["huc2"].map(climate_band)
        split_rows.append(piece)
    split_frame = pd.concat(split_rows, ignore_index=True) if split_rows else pd.DataFrame()
    if split_frame.empty:
        raise SystemExit("no HUC8 candidates to lock")
    if (
        split_frame["never_sealed"].fillna(False)
        & split_frame["role"].eq("sealed")
    ).any():
        raise SystemExit("never_sealed network appeared as sealed in the split lock")
    sealed_forbidden = split_frame["role"].eq("sealed") & split_frame["network_id"].astype(
        str
    ).str.contains("loire|swiss|aar", case=False, regex=True)
    if sealed_forbidden.any():
        raise SystemExit("refusing to put Loire/Swiss into sealed")

    canonical = canonical_split_text(split_frame, SPLIT_SEED)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    SPLIT_TABLE.write_text(canonical, encoding="utf-8")
    SHA_PATH.write_text(digest + "\n", encoding="utf-8")

    n_dev = int(split_frame["role"].eq("development").sum())
    n_val = int(split_frame["role"].eq("validation").sum())
    n_seal = int(split_frame["role"].eq("sealed").sum())
    n_never = int(split_frame["role"].eq("never_sealed").sum())
    n_hist = int(split_frame["role"].eq("historical").sum())
    n_pool = int(len(pool))
    shortfall_bits = []
    if n_seal < 40:
        shortfall_bits.append(
            f"USGS-only sealed is {n_seal}, below the after-Europe target of 40."
        )
    else:
        shortfall_bits.append(
            f"USGS-only sealed is {n_seal}, which meets the numeric 40 floor before Europe, "
            "but this is still a catalog-span lock, not a qualified-year lock."
        )
    shortfall_bits.append(
        "non-North-America sealed is 0 vs target 10; Loire/Swiss were not inserted to close the gap."
    )
    split_meta = {
        "catalog_id": "network_catalog_v3_split",
        "status": "locked_before_download",
        "frozen_on": "2026-08-26",
        "seed": SPLIT_SEED,
        "sha256": digest,
        "canonical_columns": list(CANONICAL_SPLIT_COLUMNS),
        "fractions_target": {"development": 0.50, "validation": 0.20, "sealed": 0.30},
        "sealed_target_after_europe": 40,
        "non_na_sealed_target": 10,
        "usgs_only": True,
        "temperatures_downloaded": False,
        "sealed_outcomes_opened": False,
        "loire_swiss_placed_in_sealed": False,
        "n_pool": n_pool,
        "n_development": n_dev,
        "n_validation": n_val,
        "n_sealed": n_seal,
        "n_never_sealed": n_never,
        "n_historical": n_hist,
        "n_non_na_sealed": 0,
        "regulation_note": regulation_note,
        "shortfall": " ".join(shortfall_bits),
        "networks": [
            {
                "network_id": str(row.network_id),
                "role": str(row.role),
                "seed": SPLIT_SEED,
                "climate_band": str(row.climate_band),
                "size_tertile": str(row.size_tertile),
                "regulation_stratum": str(row.regulation_stratum),
                "never_sealed": bool(row.never_sealed),
                "n_stations": int(row.n_stations),
            }
            for row in split_frame.sort_values("network_id").itertuples(index=False)
        ],
    }
    SPLIT_YAML.write_text(
        yaml.dump(split_meta, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    nldi_counts = {"true": 0, "partial": 0, "false": 0, "not_queried": 0}
    if "flow_connected" in base.columns:
        for key, value in base["flow_connected"].fillna("not_queried").value_counts().items():
            nldi_counts[str(key)] = int(value)
    n_cache = len(list(NLDI_CACHE.glob("*.json"))) if NLDI_CACHE.is_dir() else 0
    nldi_note = (
        f"Wrote/reused {n_cache} cached NLDI JSON files. "
        "Failed live queries are not_queried and were not cached as successes."
    )
    feasibility = write_feasibility(
        {
            "counts": counts,
            "missouri": _missouri_split(contrast, huc8_unfiltered, stations),
            "nldi": {
                "distance_km": NLDI_DISTANCE_KM,
                "cache_dir": str(NLDI_CACHE.relative_to(ROOT)),
                "note": nldi_note,
                **nldi_counts,
            },
            "split": split_meta,
        }
    )
    FEASIBILITY.write_text(feasibility, encoding="utf-8")

    print(json.dumps(counts, indent=2))
    print("nldi", nldi_counts, "cache_files", n_cache)
    print("split", n_dev, n_val, n_seal, "sha256", digest)
    print("wrote", OUTPUT / "usgs_river_clusters_v3_huc8.csv")
    print("wrote", OUTPUT / "usgs_river_clusters_v1_name_huc2_contrast.csv")
    print("wrote", CANDIDATES, "n", len(document["networks"]))
    print("wrote", SPLIT_YAML)
    print("wrote", SHA_PATH)
    print("wrote", FEASIBILITY)


if __name__ == "__main__":
    main()
