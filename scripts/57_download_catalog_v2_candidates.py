#!/usr/bin/env python3
"""Download catalog-v2 public USGS candidates that are not last-check.

Does not rewrite network_catalog_v1. Does not open sealed last-check
temperatures. Does not remap burned rivers into sealed. Catalog overlap is
not treated as download concurrency.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.nwis_temperature import nwis_daily_temperature
from stream_recoverability.data.public_temperature import overlap_report, river_wide_panel
from stream_recoverability.data.v2_download_policy import plan_v2_downloads

OUTPUT = ROOT / "results/framework/public_rivers_v2"
CACHE = ROOT / "data/public_rivers"
START = "2000-01-01"
END = "2024-12-31"
MIN_STATIONS = 3
COMPLETE_DAYS = 5 * 365


def _cache_path(site_id: str) -> Path:
    return CACHE / "nwis" / f"{site_id}_{START}_{END}.csv"


def _download_site(site_id: str, pause_s: float) -> pd.DataFrame | None:
    cached = _cache_path(site_id).is_file()
    try:
        frame = nwis_daily_temperature(site_id, START, END, cache_dir=CACHE)
    except Exception as error:
        print(f"{site_id}: {error}", flush=True)
        return None
    if not cached:
        time.sleep(pause_s)
    return frame


def _complete_enough(report: dict, min_stations: int = MIN_STATIONS) -> bool:
    years = float(report.get("overlap_years") or 0.0)
    days = int(report.get("days_with_min_stations") or 0)
    stations = int(report.get("n_stations") or 0)
    return bool(
        stations >= min_stations
        and years >= 8.0
        and days >= COMPLETE_DAYS
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-networks", type=int, default=0)
    parser.add_argument("--max-sites", type=int, default=0)
    parser.add_argument("--pause-s", type=float, default=0.35)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    plan = plan_v2_downloads()
    downloadable = list(plan["downloadable"])
    if args.max_networks > 0:
        downloadable = downloadable[: int(args.max_networks)]

    blocked_rows = []
    for row in plan["blocked"]:
        blocked_rows.append(
            {
                "network_id": row.get("network_id"),
                "block_reason": row.get("block_reason"),
                "n_catalog_sites": len(row.get("candidate_station_ids") or []),
            }
        )
    pd.DataFrame(blocked_rows).to_csv(OUTPUT / "blocked.csv", index=False)

    if args.dry_run:
        manifest = {
            **{k: plan[k] for k in (
                "n_v2_candidates",
                "n_downloadable",
                "n_independent_downloadable",
                "n_download_sites",
                "network_catalog_v1_rewritten",
                "sealed_outcomes_opened",
                "last_check_temperatures_opened",
            )},
            "dry_run": True,
            "temperatures_downloaded": False,
            "what_this_is": "Download plan for v2 candidates. No temperatures fetched.",
            "what_this_is_not": "Not concurrency. Not a T2 count. Not last-check.",
        }
        (OUTPUT / "v2_download_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(manifest, indent=2))
        return

    overlap_rows = []
    sites_fetched = 0
    for network in downloadable:
        if args.max_sites > 0 and sites_fetched >= args.max_sites:
            break
        network_id = str(network["network_id"])
        site_ids = list(network.get("download_site_ids") or [])
        if args.max_sites > 0:
            remaining = int(args.max_sites) - sites_fetched
            site_ids = site_ids[:remaining]
        frames = []
        for site_id in site_ids:
            frame = _download_site(site_id, args.pause_s)
            sites_fetched += 1
            if frame is None or frame.empty:
                continue
            frames.append(frame)
        wide = river_wide_panel(frames)
        if wide.empty:
            overlap_rows.append(
                {
                    "network_id": network_id,
                    "display_name": network.get("display_name"),
                    "ok": False,
                    "complete_enough": False,
                    "independent_unit": bool(network.get("independent_unit", True)),
                    "n_requested_sites": len(site_ids),
                    "climate_or_ecoregion": network.get("climate_or_ecoregion"),
                }
            )
            continue
        wide.to_csv(OUTPUT / f"{network_id}_daily_wide.csv")
        report = overlap_report(wide, min_stations=min(MIN_STATIONS, wide.shape[1]))
        report["complete_enough"] = _complete_enough(
            report, min_stations=MIN_STATIONS
        )
        report.update(
            {
                "network_id": network_id,
                "display_name": network.get("display_name"),
                "ok": report["complete_enough"],
                "independent_unit": bool(network.get("independent_unit", True)),
                "climate_or_ecoregion": network.get("climate_or_ecoregion"),
                "n_requested_sites": len(site_ids),
                "catalog_overlap_is_not_concurrency": True,
            }
        )
        overlap_rows.append(report)
        print(
            f"{network_id}: stations={report['n_stations']} "
            f"overlap_years={report['overlap_years']:.2f} "
            f"complete_enough={report['complete_enough']}",
            flush=True,
        )

    overlap = pd.DataFrame(overlap_rows)
    overlap.to_csv(OUTPUT / "overlap.csv", index=False)
    concurrent = overlap.loc[overlap["complete_enough"].fillna(False)] if not overlap.empty else overlap
    independent_concurrent = (
        concurrent.loc[concurrent["independent_unit"].fillna(True)]
        if not concurrent.empty and "independent_unit" in concurrent.columns
        else concurrent
    )
    climates: list[str] = []
    if not independent_concurrent.empty and "climate_or_ecoregion" in independent_concurrent.columns:
        climates = sorted(
            {
                str(item)
                for item in independent_concurrent["climate_or_ecoregion"].tolist()
                if str(item) not in {"", "nan", "None", "unspecified"}
            }
        )
    manifest = {
        "what_this_is": (
            "Daily USGS temperatures for v2 name+HUC2 candidates that are not "
            "last-check, not historical, and not the already-downloaded burned set."
        ),
        "what_this_is_not": (
            "Not a T2 count. Catalog overlap is not concurrency. Not last-check. "
            "Not confirmatory. Honest USGS catalog remains 98. Target remains 150."
        ),
        "n_v2_candidates": plan["n_v2_candidates"],
        "best_honest_catalog_count": 98,
        "target_independent_networks": 150,
        "n_downloadable_planned": plan["n_downloadable"],
        "n_independent_downloadable_planned": plan["n_independent_downloadable"],
        "n_rivers_attempted": int(len(overlap)),
        "n_rivers_with_any_daily": int(overlap["n_stations"].gt(0).sum()) if not overlap.empty and "n_stations" in overlap.columns else 0,
        "n_complete_enough": int(len(concurrent)),
        "n_independent_complete_enough": int(len(independent_concurrent)),
        "complete_enough_climates": climates,
        "n_complete_enough_climates": int(len(climates)),
        "sites_fetched_or_cached": int(sites_fetched),
        "last_check_temperatures_opened": False,
        "sealed_outcomes_opened": False,
        "network_catalog_v1_rewritten": False,
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "confirmatory_eligible": False,
        "continents": ["north_america"],
        "europe_daily_years_invented": False,
    }
    (OUTPUT / "v2_download_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, default=str))


if __name__ == "__main__":
    main()
