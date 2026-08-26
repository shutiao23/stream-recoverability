#!/usr/bin/env python3
"""Derive Hub'Eau daily means from public chronique. Loire last-check stays closed.

Name clusters are not T8 until 3 stations share ≥8 overlapping *daily* years.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.hubeau_temperature import (
    cluster_hubeau_rivers,
    hubeau_chronique_daily,
)
from stream_recoverability.data.public_temperature import overlap_report, river_wide_panel
from stream_recoverability.data.v2_download_policy import last_check_site_ids

OUTPUT = ROOT / "results/framework/public_rivers_europe"
CACHE = ROOT / "data/public_rivers"
STATIONS = ROOT / "results/framework/public_catalog/hubeau_all_stations.csv"
PREFERRED = ("La Garonne", "Le Rhône", "La Saône", "La Durance", "L'Aude")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-rivers", type=int, default=3)
    parser.add_argument("--max-sites-per-river", type=int, default=5)
    args = parser.parse_args()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    stations = pd.read_csv(STATIONS, dtype={"site_id": str})
    clusters = cluster_hubeau_rivers(stations, min_stations=3, exclude_loire=True)
    blocked = last_check_site_ids()
    ranked = []
    for preferred in PREFERRED:
        hit = clusters.loc[clusters["river"].str.fullmatch(preferred, case=False)]
        if not hit.empty:
            ranked.append(hit.iloc[0])
    for row in clusters.itertuples(index=False):
        if all(str(row.river) != str(item.river) for item in ranked):
            ranked.append(row)
    chosen = ranked[: int(args.max_rivers)]
    overlap_rows = []
    for row in chosen:
        river = str(row.river)
        network_id = (
            "hubeau_"
            + river.lower()
            .replace("'", "")
            .replace(" ", "_")
            .replace("é", "e")
            .replace("ô", "o")
        )
        site_ids = [
            item
            for item in str(row.site_ids).split(",")
            if item and item not in blocked
        ][: int(args.max_sites_per_river)]
        frames = []
        for site_id in site_ids:
            try:
                daily = hubeau_chronique_daily(site_id, cache_dir=CACHE)
            except Exception as error:
                print(f"{network_id} {site_id}: {error}", flush=True)
                continue
            if daily is None or daily.empty:
                continue
            frames.append(daily)
            print(f"{network_id} {site_id}: {len(daily)} daily rows", flush=True)
        wide = river_wide_panel(frames)
        if wide.empty:
            overlap_rows.append(
                {
                    "network_id": network_id,
                    "river": river,
                    "ok": False,
                    "complete_enough": False,
                    "continent": "europe",
                    "countable_toward_t8": False,
                }
            )
            continue
        wide.to_csv(OUTPUT / f"{network_id}_daily_wide.csv")
        report = overlap_report(wide, min_stations=min(3, wide.shape[1]))
        complete = bool(
            int(report.get("n_stations") or 0) >= 3
            and float(report.get("overlap_years") or 0) >= 8.0
            and int(report.get("days_with_min_stations") or 0) >= 5 * 365
        )
        report.update(
            {
                "network_id": network_id,
                "river": river,
                "ok": complete,
                "complete_enough": complete,
                "continent": "europe",
                "countable_toward_t8": complete,
                "derived_from": "hubeau_instantaneous_chronique_daily_mean",
                "loire_downloaded": False,
            }
        )
        overlap_rows.append(report)
        print(
            f"{network_id}: stations={report['n_stations']} "
            f"years={report['overlap_years']:.2f} complete={complete}",
            flush=True,
        )
    overlap = pd.DataFrame(overlap_rows)
    overlap.to_csv(OUTPUT / "overlap.csv", index=False)
    n_complete = int(overlap["complete_enough"].fillna(False).sum()) if not overlap.empty else 0
    manifest = {
        "what_this_is": (
            "Daily-mean temperature derived from public Hub'Eau chronique for "
            "non-Loire name clusters."
        ),
        "what_this_is_not": (
            "Not Loire last-check. Not invented years. Not T8 unless complete_enough."
        ),
        "n_rivers_attempted": int(len(overlap)),
        "n_complete_enough": n_complete,
        "countable_toward_t8": bool(n_complete > 0),
        "loire_downloaded": False,
        "last_check_temperatures_opened": False,
        "europe_daily_years_invented": False,
        "temporal_resolution_source": "instantaneous_resampled_to_daily_mean",
        "formal_evidence": False,
    }
    (OUTPUT / "hubeau_daily_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, default=str))


if __name__ == "__main__":
    main()
