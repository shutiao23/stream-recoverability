#!/usr/bin/env python3
"""Hub'Eau non-Loire river-name clusters and optional chronique date spans.

Does not download Loire last-check temperatures. Does not invent daily years.
Spans are public chronique first/last timestamps. Not a T8 count until a
river has dated daily overlap of at least eight years.
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
    hubeau_spans_for_sites,
)
from stream_recoverability.data.public_river_inventory import inventory_hubeau_stations
from stream_recoverability.data.v2_download_policy import last_check_site_ids

OUTPUT = ROOT / "results/framework/public_catalog"
STATION_CSV = OUTPUT / "hubeau_all_stations.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-spans", action="store_true")
    parser.add_argument("--max-rivers", type=int, default=8)
    parser.add_argument("--refresh-stations", action="store_true")
    args = parser.parse_args()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.refresh_stations or not STATION_CSV.is_file():
        stations = inventory_hubeau_stations()
        stations.to_csv(STATION_CSV, index=False)
    else:
        stations = pd.read_csv(STATION_CSV, dtype={"site_id": str})

    clusters = cluster_hubeau_rivers(stations, min_stations=3, exclude_loire=True)
    clusters.to_csv(OUTPUT / "hubeau_non_loire_clusters.csv", index=False)
    last_check = last_check_site_ids()
    if args.fetch_spans and not clusters.empty:
        chosen = clusters.head(int(args.max_rivers))
        site_ids = []
        for row in chosen.itertuples(index=False):
            for site_id in str(row.site_ids).split(","):
                if site_id and site_id not in last_check:
                    site_ids.append(site_id)
        spans = hubeau_spans_for_sites(site_ids)
        spans.to_csv(OUTPUT / "hubeau_non_loire_chronicle_spans.csv", index=False)
        n_with_years = int(pd.to_numeric(spans["span_years"], errors="coerce").ge(8).sum()) if not spans.empty else 0
        n_instantaneous_ge8 = n_with_years
        n_daily_ge8 = 0
    else:
        n_with_years = 0
        spans = pd.DataFrame()

    manifest = {
        "what_this_is": (
            "Hub'Eau non-Loire name clusters from the public station table, "
            "optionally dated by chronique first/last points."
        ),
        "what_this_is_not": (
            "Not Loire last-check temperatures. Not invented daily years. "
            "Name clusters are not eight-year concurrent networks."
        ),
        "n_hubeau_stations": int(len(stations)),
        "n_non_loire_name_clusters_3plus": int(len(clusters)),
        "n_span_rows": int(len(spans)) if spans is not None and not spans.empty else 0,
        "n_sites_span_ge_8yr": n_with_years,
        "n_sites_instantaneous_span_ge_8yr": n_with_years,
        "n_sites_daily_span_ge_8yr": 0,
        "temporal_resolution": "instantaneous_not_daily",
        "loire_downloaded": False,
        "last_check_temperatures_opened": False,
        "europe_daily_years_invented": False,
        "countable_toward_t8": False,
        "formal_evidence": False,
    }
    (OUTPUT / "hubeau_non_loire_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
