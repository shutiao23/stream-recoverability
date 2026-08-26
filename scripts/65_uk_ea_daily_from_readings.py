#!/usr/bin/env python3
"""Derive daily means from UK EA hydrology temperature readings.

River Derwent is the only 3-station name cluster in the catalog. Not T8
until concurrent daily overlap is measured. Last-check unused.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.public_temperature import overlap_report, river_wide_panel
from stream_recoverability.data.uk_ea_temperature import uk_ea_daily

OUTPUT = ROOT / "results/framework/public_rivers_europe"
CACHE = ROOT / "data/public_rivers"
CLUSTERS = ROOT / "results/framework/public_catalog/uk_ea_river_clusters.csv"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if not CLUSTERS.is_file():
        manifest = {
            "what_this_is": "UK EA daily derivation skipped: cluster table missing.",
            "countable_toward_t8": False,
            "ok": False,
        }
        (OUTPUT / "uk_ea_daily_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(manifest, indent=2))
        return
    clusters = pd.read_csv(CLUSTERS)
    overlap_rows = []
    for row in clusters.itertuples(index=False):
        river = str(row.river)
        network_id = "uk_ea_" + river.lower().replace(" ", "_")
        site_ids = [item for item in str(row.site_ids).split(",") if item][:5]
        frames = []
        for site_id in site_ids:
            try:
                daily = uk_ea_daily(site_id, cache_dir=CACHE)
            except Exception as error:
                print(f"{network_id} {site_id}: {error}", flush=True)
                continue
            if daily is None or daily.empty:
                print(f"{network_id} {site_id}: empty", flush=True)
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
        report = overlap_report(wide, min_stations=3)
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
                "derived_from": "uk_ea_subdaily_readings_daily_mean",
            }
        )
        overlap_rows.append(report)
        print(
            f"{network_id}: stations={report['n_stations']} "
            f"years={report.get('overlap_years')} complete={complete}",
            flush=True,
        )
    overlap = pd.DataFrame(overlap_rows)
    if not overlap.empty:
        overlap.to_csv(OUTPUT / "uk_ea_overlap.csv", index=False)
    n_complete = int(overlap["complete_enough"].fillna(False).sum()) if not overlap.empty else 0
    manifest = {
        "what_this_is": "Daily-mean temperature derived from public UK EA hydrology readings.",
        "what_this_is_not": "Not invented years. Not T8 unless complete_enough.",
        "n_rivers_attempted": int(len(overlap)),
        "n_complete_enough": n_complete,
        "countable_toward_t8": bool(n_complete > 0),
        "europe_daily_years_invented": False,
        "last_check_temperatures_opened": False,
        "temporal_resolution_source": "subdaily_resampled_to_daily_mean",
        "formal_evidence": False,
    }
    (OUTPUT / "uk_ea_daily_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, default=str))


if __name__ == "__main__":
    main()
