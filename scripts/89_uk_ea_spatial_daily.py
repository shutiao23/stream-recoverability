#!/usr/bin/env python3
"""UK EA spatial clustering and daily-mean overlap for W6 Europe.

Clusters all catalog stations on lat/lon (no riverName, no dateOpened span).
Downloads the largest N 50 km 3+ clusters via uk_ea_daily. Catalog clusters
are not T8. Hub'Eau Sandre Correcte is unused. Loire/last-check unused.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.public_temperature import river_wide_panel
from stream_recoverability.data.uk_ea_spatial import (
    DEFAULT_CAP_KM,
    DEFAULT_DOWNLOAD_STATIONS_PER_CLUSTER,
    SENSITIVITY_CAP_KM,
    cluster_uk_ea_spatial,
    hydrometric_stations,
    is_hydrometric_site_id,
    score_spatial_cluster_overlap,
    select_download_site_ids,
    select_largest_spatial_clusters,
    w6_europe_spatial_manifest,
)
from stream_recoverability.data.uk_ea_temperature import uk_ea_daily

CATALOG_STATIONS = ROOT / "results/framework/public_catalog/uk_ea_temperature_stations.csv"
CLUSTER_TABLE = ROOT / "results/framework/public_catalog/uk_ea_spatial_clusters.csv"
CLUSTER_TABLE_100 = ROOT / "results/framework/public_catalog/uk_ea_spatial_clusters_100km.csv"
HYDROMETRIC_CLUSTER_TABLE = (
    ROOT / "results/framework/public_catalog/uk_ea_hydrometric_spatial_clusters.csv"
)
OUTPUT = ROOT / "results/framework/public_rivers_europe"
CACHE = ROOT / "data/public_rivers"


def _named_count(stations: pd.DataFrame) -> int:
    if stations.empty or "river" not in stations.columns:
        return 0
    return int(stations["river"].fillna("").astype(str).str.strip().ne("").sum())


def _write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )


def cluster_catalog(
    stations: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    clusters_50 = cluster_uk_ea_spatial(stations, cap_km=DEFAULT_CAP_KM)
    clusters_100 = cluster_uk_ea_spatial(stations, cap_km=SENSITIVITY_CAP_KM)
    hydro = hydrometric_stations(stations)
    hydro_50 = cluster_uk_ea_spatial(hydro, cap_km=DEFAULT_CAP_KM)
    CLUSTER_TABLE.parent.mkdir(parents=True, exist_ok=True)
    clusters_50.to_csv(CLUSTER_TABLE, index=False)
    clusters_100.to_csv(CLUSTER_TABLE_100, index=False)
    hydro_50.to_csv(HYDROMETRIC_CLUSTER_TABLE, index=False)
    return clusters_50, clusters_100, hydro, hydro_50


def _fetch_daily(
    site_id: str, cache_dir: Path, *, retries: int = 4
) -> tuple[str, pd.DataFrame | None, str | None]:
    last_error = "empty"
    for attempt in range(max(1, int(retries))):
        try:
            daily = uk_ea_daily(site_id, cache_dir=cache_dir)
        except Exception as error:  # noqa: BLE001
            last_error = str(error)
            if "HTTP 403" in last_error and attempt + 1 < retries:
                time.sleep(1.5 * (2**attempt))
                continue
            return site_id, None, last_error
        if daily is None or daily.empty:
            return site_id, None, "empty"
        return site_id, daily, None
    return site_id, None, last_error


def score_downloaded_cluster(
    row: pd.Series,
    stations: pd.DataFrame,
    daily_by_site: dict[str, pd.DataFrame],
    site_ids: list[str],
) -> dict:
    network_id = str(row.cluster_id)
    frames = [daily_by_site[site_id] for site_id in site_ids if site_id in daily_by_site]
    if not frames:
        return {
            "network_id": network_id,
            "n_stations": 0,
            "n_stations_requested": len(site_ids),
            "ok": False,
            "complete_enough": False,
            "continent": "europe",
            "countable_toward_t8": False,
            "catalog_n_stations": int(row.n_stations),
            "catalog_max_pairwise_km": float(row.max_pairwise_km),
            "omitted_spatial_cap": False,
            "derived_from": "uk_ea_subdaily_readings_daily_mean",
        }
    wide = river_wide_panel(frames)
    if wide.empty:
        return {
            "network_id": network_id,
            "n_stations": 0,
            "n_stations_requested": len(site_ids),
            "ok": False,
            "complete_enough": False,
            "continent": "europe",
            "countable_toward_t8": False,
            "catalog_n_stations": int(row.n_stations),
            "catalog_max_pairwise_km": float(row.max_pairwise_km),
            "omitted_spatial_cap": False,
            "derived_from": "uk_ea_subdaily_readings_daily_mean",
        }
    wide.to_csv(OUTPUT / f"{network_id}_daily_wide.csv")
    report = score_spatial_cluster_overlap(wide, stations, cap_km=float(row.cap_km))
    report["network_id"] = network_id
    report["n_stations_requested"] = len(site_ids)
    report["catalog_n_stations"] = int(row.n_stations)
    report["catalog_max_pairwise_km"] = float(row.max_pairwise_km)
    print(
        f"{network_id}: stations={report['n_stations']} "
        f"years={report.get('overlap_years')} complete={report['complete_enough']}",
        flush=True,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-only", action="store_true")
    parser.add_argument("--max-clusters", type=int, default=15)
    parser.add_argument(
        "--max-stations-per-cluster",
        type=int,
        default=DEFAULT_DOWNLOAD_STATIONS_PER_CLUSTER,
        help="Per-cluster download cap. 0 means every member (too large for 15 clusters).",
    )
    parser.add_argument("--max-workers", type=int, default=2)
    parser.add_argument("--cache-dir", type=Path, default=CACHE)
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if not CATALOG_STATIONS.is_file():
        manifest = w6_europe_spatial_manifest(
            n_stations_catalog=0,
            n_with_river_name=0,
            n_spatial_clusters_3plus_50km=0,
            n_spatial_clusters_3plus_100km=0,
            n_clusters_downloaded=0,
            n_complete_enough=0,
        )
        manifest["ok"] = False
        manifest["error"] = "uk_ea_temperature_stations.csv missing"
        _write_json(OUTPUT / "uk_ea_spatial_daily_manifest.json", manifest)
        print(json.dumps(manifest, indent=2))
        return
    stations = pd.read_csv(CATALOG_STATIONS)
    clusters_50, clusters_100, hydro, hydro_50 = cluster_catalog(stations)
    n_catalog = int(len(stations.drop_duplicates("site_id"))) if not stations.empty else 0
    n_named = _named_count(stations)
    n_50 = int(len(clusters_50))
    n_100 = int(len(clusters_100))
    n_hydro = int(len(hydro.drop_duplicates("site_id"))) if not hydro.empty else 0
    n_event = n_catalog - n_hydro
    n_hydro_50 = int(len(hydro_50))
    print(
        f"catalog={n_catalog} named={n_named} hydrometric={n_hydro} "
        f"event={n_event} clusters_50km={n_50} hydro_50km={n_hydro_50}",
        flush=True,
    )
    if args.cluster_only:
        manifest = w6_europe_spatial_manifest(
            n_stations_catalog=n_catalog,
            n_with_river_name=n_named,
            n_spatial_clusters_3plus_50km=n_50,
            n_spatial_clusters_3plus_100km=n_100,
            n_clusters_downloaded=0,
            n_complete_enough=0,
            n_hydrometric_stations=n_hydro,
            n_event_monitor_stations=n_event,
            n_hydrometric_spatial_clusters_3plus_50km=n_hydro_50,
        )
        manifest["download_skipped"] = True
        manifest["download_roster"] = "hydrometric_only"
        _write_json(OUTPUT / "uk_ea_hydrometric_spatial_daily_manifest.json", manifest)
        print(json.dumps(manifest, indent=2, default=str))
        return
    selected = select_largest_spatial_clusters(
        hydro_50, n=args.max_clusters, cap_km=DEFAULT_CAP_KM
    )
    cluster_sites: dict[str, list[str]] = {}
    wanted: list[str] = []
    for row in selected.itertuples(index=False):
        members = [item.strip() for item in str(row.site_ids).split(",") if item.strip()]
        chosen = [
            site_id
            for site_id in select_download_site_ids(
                members, hydro, max_stations=args.max_stations_per_cluster
            )
            if is_hydrometric_site_id(site_id)
        ]
        cluster_sites[str(row.cluster_id)] = chosen
        wanted.extend(chosen)
    unique_sites = list(dict.fromkeys(wanted))
    daily_by_site: dict[str, pd.DataFrame] = {}
    workers = max(1, int(args.max_workers))
    error_counts = {"http_403": 0, "empty": 0, "other": 0}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_fetch_daily, site_id, args.cache_dir): site_id
            for site_id in unique_sites
        }
        for future in as_completed(futures):
            site_id, daily, error = future.result()
            if error:
                print(f"{site_id}: {error}", flush=True)
                if "HTTP 403" in error:
                    error_counts["http_403"] += 1
                elif error == "empty":
                    error_counts["empty"] += 1
                else:
                    error_counts["other"] += 1
                continue
            assert daily is not None
            daily_by_site[site_id] = daily
            print(f"{site_id}: {len(daily)} daily rows", flush=True)
    overlap_rows = []
    for row in selected.itertuples(index=False):
        overlap_rows.append(
            score_downloaded_cluster(
                row,
                hydro,
                daily_by_site,
                cluster_sites[str(row.cluster_id)],
            )
        )
    overlap = pd.DataFrame(overlap_rows)
    hydro_overlap_path = OUTPUT / "uk_ea_hydrometric_spatial_overlap.csv"
    hydro_manifest_path = OUTPUT / "uk_ea_hydrometric_spatial_daily_manifest.json"
    if not overlap.empty:
        overlap.to_csv(hydro_overlap_path, index=False)
    n_complete = (
        int(overlap["complete_enough"].fillna(False).astype(bool).sum()) if not overlap.empty else 0
    )
    manifest = w6_europe_spatial_manifest(
        n_stations_catalog=n_catalog,
        n_with_river_name=n_named,
        n_spatial_clusters_3plus_50km=n_50,
        n_spatial_clusters_3plus_100km=n_100,
        n_clusters_downloaded=int(len(selected)),
        n_complete_enough=n_complete,
        n_hydrometric_stations=n_hydro,
        n_event_monitor_stations=n_event,
        n_hydrometric_spatial_clusters_3plus_50km=n_hydro_50,
    )
    manifest["n_stations_requested"] = len(unique_sites)
    manifest["n_stations_with_daily"] = len(daily_by_site)
    manifest["n_stations_http_403"] = error_counts["http_403"]
    manifest["n_stations_empty"] = error_counts["empty"]
    manifest["n_stations_other_error"] = error_counts["other"]
    manifest["n_stations_per_cluster_download_cap"] = int(args.max_stations_per_cluster)
    manifest["download_roster"] = "hydrometric_only"
    _write_json(hydro_manifest_path, manifest)
    print(json.dumps(manifest, indent=2, default=str))


if __name__ == "__main__":
    main()
