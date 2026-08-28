#!/usr/bin/env python3
"""Download reviewed ARSO daily river temperatures and run network QC."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.data.arso_temperature import (
    NETWORKS,
    candidate_table,
    download_station,
)
from stream_recoverability.data.confirmation_daily_qc import qc_candidate_network


CATALOG = ROOT / "results/framework/public_catalog"
DEVELOPMENT = ROOT / "results/development_v11"
CANDIDATES = DEVELOPMENT / "confirmation_candidates.csv"
OUTPUT = DEVELOPMENT / "confirmation_daily_qc"
SUMMARY = DEVELOPMENT / "confirmation_qc_summary.csv"
YEARS = tuple(range(2015, 2025))


def main() -> None:
    candidates = candidate_table()
    CATALOG.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(CATALOG / "arso_temperature_network_candidates.csv", index=False)
    existing = pd.read_csv(CANDIDATES, dtype={"site_ids": str})
    existing = existing.loc[~existing["provider"].eq("arso")]
    columns = list(existing.columns)
    combined = pd.concat(
        [existing, candidates.reindex(columns=columns)], ignore_index=True
    ).sort_values(["domain", "network_id"])
    combined.to_csv(CANDIDATES, index=False)

    tasks = [
        (str(candidate["river_group"]), station)
        for candidate in candidates.to_dict("records")
        for station in str(candidate["site_ids"]).split("|")
    ]
    with ThreadPoolExecutor(max_workers=16) as workers:
        downloaded = dict(
            zip(
                tasks,
                workers.map(
                    lambda item: download_station(item[0], item[1], YEARS), tasks
                ),
                strict=True,
            )
        )
    for candidate in candidates.to_dict("records"):
        river = str(candidate["river_group"])
        frames = [
            downloaded[(river, station)]
            for station in str(candidate["site_ids"]).split("|")
        ]
        result = qc_candidate_network(
            candidate, pd.concat(frames, ignore_index=True), OUTPUT
        )
        print(
            f"{candidate['network_id']}: values={result['n_stations_with_values']} "
            f"eligible={result['n_eligible_stations']} "
            f"complete={result['complete_enough']}",
            flush=True,
        )

    completed = pd.concat(
        [
            pd.read_csv(path)
            for path in sorted(OUTPUT.glob("networks/*/network_qc_summary.csv"))
        ],
        ignore_index=True,
    )
    summary = combined[
        ["network_id", "provider", "domain", "river_group", "n_catalog_stations"]
    ].merge(completed, on=["network_id", "provider", "river_group"], how="left")
    summary["qc_status"] = summary["qc_status"].fillna("not_processed")
    summary.to_csv(SUMMARY, index=False)
    arso = summary.loc[summary["provider"].eq("arso")]
    audit = {
        "provider": "Slovenia ARSO",
        "official_archive": "https://vode.arso.gov.si/hidarhiv/",
        "source_resolution": "reviewed daily river archive",
        "years_requested": list(YEARS),
        "n_exact_river_networks": len(candidates),
        "n_stations": sum(len(stations) for _, stations in NETWORKS.values()),
        "n_qualified_networks": int(arso["complete_enough"].fillna(False).sum()),
        "lake_or_coast_networks_included": 0,
    }
    (DEVELOPMENT / "arso_source_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
