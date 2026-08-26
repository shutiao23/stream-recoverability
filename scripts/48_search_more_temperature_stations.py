#!/usr/bin/env python3
"""Search public USGS names for more daily temperature stations on the build rivers."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.public_river_inventory import (
    inventory_loire_hubeau,
    inventory_usgs_name_search,
    summarize_river,
)

OUTPUT = ROOT / "results/framework/public_catalog"

SEARCHES = {
    "delaware_mainstem": "Delaware River",
    "sacramento_mainstem": "Sacramento River",
    "willamette_mainstem": "Willamette River",
    "connecticut_mainstem": "Connecticut River",
    "suwannee_florida": "Suwannee River",
    "potomac_mainstem": "Potomac River",
    "tennessee_mainstem": "Tennessee River",
    "colorado_front_range": "South Platte",
}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    summaries = []
    for network_id, name in SEARCHES.items():
        table = inventory_usgs_name_search(name)
        if table.empty:
            summaries.append({"network_id": network_id, "query": name, "n": 0})
            continue
        table["network_id"] = network_id
        table["query"] = name
        table.to_csv(OUTPUT / f"name_search_{network_id}.csv", index=False)
        usable = table.loc[
            table["has_daily_temperature"].fillna(False) & table["span_years"].ge(8)
        ]
        summary = summarize_river(table)
        summary.update(
            {
                "network_id": network_id,
                "query": name,
                "n_name_matches": int(len(table)),
            }
        )
        summaries.append(summary)
        print(
            network_id,
            "name_matches",
            len(table),
            "long_daily_T",
            int(len(usable)),
            "ids",
            ",".join(usable["site_id"].astype(str).head(8)),
        )
    loire = inventory_loire_hubeau(size=80)
    loire.to_csv(OUTPUT / "loire_hubeau_stations.csv", index=False)
    print("loire_rows", len(loire), "rivers", sorted(set(loire.get("river", [])))[:12])
    import pandas as pd

    pd.DataFrame(summaries).to_csv(OUTPUT / "name_search_summary.csv", index=False)


if __name__ == "__main__":
    main()
