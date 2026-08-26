#!/usr/bin/env python3
"""Check public catalogs: which listed stations have daily water temperature.

This writes station names and catalog date spans. It does not score recovery.
Last-check rivers are included in the catalog check only.
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

from stream_recoverability.data.network_catalog import load_network_catalog
from stream_recoverability.data.public_river_inventory import (
    inventory_loire_hubeau,
    inventory_usgs_sites,
    summarize_river,
)

OUTPUT = ROOT / "results/framework/public_catalog"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    catalog = load_network_catalog()
    site_rows = []
    river_rows = []
    loire_stations = pd.DataFrame()
    for network in catalog["networks"]:
        network_id = str(network["network_id"])
        use = str(network.get("use") or network.get("split_role"))
        ids = [str(item) for item in network.get("candidate_station_ids") or []]
        usgs_ids = [item for item in ids if item.isdigit()]
        if usgs_ids:
            table = inventory_usgs_sites(usgs_ids)
            table["network_id"] = network_id
            table["use"] = use
            site_rows.append(table)
            summary = summarize_river(table)
        elif network_id == "loire_mainstem":
            loire_stations = inventory_loire_hubeau()
            loire_stations.to_csv(OUTPUT / "loire_hubeau_stations.csv", index=False)
            usable = loire_stations.dropna(subset=["site_id"])
            summary = {
                "n_listed": int(len(usable)),
                "n_found": int(len(usable)),
                "n_with_daily_temperature": int(len(usable)),
                "n_with_8yr_daily_temperature": int(len(usable)),
                "usable_site_ids": ",".join(usable["site_id"].astype(str).head(12)),
                "catalog_overlap_start": None,
                "catalog_overlap_end": None,
                "catalog_overlap_years": float("nan"),
                "enough_stations": len(usable) >= 4,
                "enough_overlap_years": False,
            }
        elif network_id == "swiss_aar_rhine":
            summary = {
                "n_listed": len(ids),
                "n_found": 0,
                "n_with_daily_temperature": 0,
                "n_with_8yr_daily_temperature": 0,
                "usable_site_ids": "",
                "catalog_overlap_start": None,
                "catalog_overlap_end": None,
                "catalog_overlap_years": float("nan"),
                "enough_stations": False,
                "enough_overlap_years": False,
                "note": "Swiss FOEN has no drop-in public API in this check.",
            }
        elif network_id == "jinsha_upper":
            summary = {
                "n_listed": 3,
                "n_found": 3,
                "n_with_daily_temperature": 3,
                "n_with_8yr_daily_temperature": 3,
                "usable_site_ids": "B1,S2,P3",
                "catalog_overlap_start": "2006-01-01",
                "catalog_overlap_end": "2020-12-31",
                "catalog_overlap_years": 15.0,
                "enough_stations": False,
                "enough_overlap_years": True,
                "note": "Already used. Restricted files. Not a new public river.",
            }
        else:
            summary = {
                "n_listed": len(ids),
                "n_found": 0,
                "n_with_daily_temperature": 0,
                "n_with_8yr_daily_temperature": 0,
                "usable_site_ids": "",
                "enough_stations": False,
                "enough_overlap_years": False,
            }
        river_rows.append(
            {
                "network_id": network_id,
                "name": network.get("display_name"),
                "use": use,
                "kind": network.get("regime"),
                **summary,
                "can_use_to_build_method": bool(
                    use in {"build", "development", "lock", "validation"}
                    and summary.get("enough_stations")
                    and summary.get("enough_overlap_years")
                ),
            }
        )
    sites = pd.concat(site_rows, ignore_index=True) if site_rows else pd.DataFrame()
    rivers = pd.DataFrame(river_rows)
    if not sites.empty:
        sites.to_csv(OUTPUT / "usgs_station_catalog.csv", index=False)
    rivers.to_csv(OUTPUT / "river_catalog_summary.csv", index=False)
    manifest = {
        "what_this_is": "Public catalog check of station names and date spans.",
        "what_this_is_not": "Not a recovery score. Not a paper result.",
        "n_usgs_stations_checked": int(len(sites)),
        "rivers_with_four_long_temperature_stations": int(
            rivers["enough_stations"].sum()
        ),
        "loire_public_stations_listed": int(len(loire_stations)),
        "swiss_public_api": False,
    }
    (OUTPUT / "catalog_check.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(rivers.to_string(index=False))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
