#!/usr/bin/env python3
"""Put catalog-confirmed rivers into the candidate list.

Does not download last-check temperatures. Does not invent overlap that the
catalog did not show.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.analysis.study_freeze import load_study_freeze
from stream_recoverability.data.network_catalog import load_network_catalog, validate_catalog

CLUSTERS = ROOT / "results/framework/public_catalog/usgs_river_clusters.csv"
CATALOG = ROOT / "configs/network_catalog_v1.yaml"
LAST_CHECK_NAMES = {
    "colorado river",
    "columbia river",
    "ohio river",
    "deschutes river",
}
ALREADY_USED = {"chattahoochee river"}

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
}


def _regime(name: str) -> str:
    text = name.lower()
    if any(key in text for key in ("suwannee", "deschutes", "platte", "snake")):
        return "groundwater_dominated"
    if any(key in text for key in ("colorado", "tennessee", "columbia", "sacramento", "missouri")):
        return "regulated"
    if any(key in text for key in ("mississippi", "ohio", "delaware", "missouri")):
        return "large_river"
    return "atmospheric"


def _entry(row, *, split_role: str, use: str, extra_notes: str) -> dict:
    site_ids = [item for item in str(row.site_ids).split(",") if item]
    return {
        "network_id": row.network_id,
        "display_name": f"{row.river_name} (HUC2 {row.huc2})",
        "split_role": split_role,
        "historical_seen": False,
        "regime": _regime(str(row.river_name)),
        "climate_or_ecoregion": HUC_CLIMATE.get(str(row.huc2), "unspecified"),
        "candidate_station_ids": site_ids[:8],
        "temperature_record_unverified": True,
        "sealed_outcomes_opened": False,
        "feasibility_status": "catalog_overlap_checked",
        "use": use,
        "notes": (
            f"目录同期约 {float(row.catalog_overlap_years):.1f} 年，{int(row.n_stations)} 站。"
            f"{extra_notes}"
        ),
    }


def main() -> None:
    if not CLUSTERS.is_file():
        raise SystemExit("run scripts/49_national_temperature_catalog.py first")
    clusters = pd.read_csv(CLUSTERS)
    usable = clusters.loc[clusters["enough_overlap_years"].fillna(False)].copy()
    document = load_network_catalog()
    kept = [
        network
        for network in document["networks"]
        if network.get("historical_seen") or network.get("use") == "last_check"
    ]
    build_rows = []
    reserved_last = []
    for row in usable.itertuples(index=False):
        name = str(row.river_name).lower()
        if name in ALREADY_USED:
            continue
        if name in LAST_CHECK_NAMES:
            reserved_last.append(row)
            continue
        build_rows.append(row)
    development = [_entry(row, split_role="development", use="build", extra_notes="用来定方法。") for row in build_rows[:8]]
    validation = [_entry(row, split_role="validation", use="lock", extra_notes="用来锁设定。") for row in build_rows[8:12]]
    if not development:
        development = [
            network
            for network in document["networks"]
            if network.get("use") in {"build", "development"}
            or network.get("split_role") == "development"
        ]
    if not validation:
        validation = [
            network
            for network in document["networks"]
            if network.get("use") in {"lock", "validation"}
            or network.get("split_role") == "validation"
        ]
    # Keep previous last-check entries; refresh USGS IDs if the catalog found the same river.
    last_check = []
    existing_last = [item for item in kept if item.get("use") == "last_check"]
    by_name = {str(row.river_name).lower(): row for row in reserved_last}
    for item in existing_last:
        display = str(item.get("display_name") or item["network_id"]).lower()
        match = None
        for river_name, row in by_name.items():
            if river_name.split()[0] in display:
                match = row
                break
        if match is not None:
            item = dict(item)
            item["candidate_station_ids"] = str(match.site_ids).split(",")[:8]
            item["feasibility_status"] = "catalog_only_last_check"
            item["notes"] = (
                "留到最后看。目录已核验站年，不下载水温。"
                f" 目录同期约 {float(match.catalog_overlap_years):.1f} 年。"
            )
        last_check.append(item)
    historical = [item for item in kept if item.get("historical_seen")]
    document["networks"] = historical + development + validation + last_check
    never_sealed = set(
        load_study_freeze()["split_rule"].get("never_sealed_networks") or []
    )
    sealed_burned = [
        str(item.get("network_id"))
        for item in document["networks"]
        if item.get("split_role") == "sealed"
        and str(item.get("network_id")) in never_sealed
    ]
    if sealed_burned:
        raise SystemExit(
            "refusing to write sealed roles for never-sealed networks: "
            + ", ".join(sealed_burned)
        )
    document["status"] = "catalog_checked"
    document["note"] = (
        "候选河名单已按公开目录的站年和同期更新。"
        "标成 last_check 的河只记目录，不下载水温。"
    )
    violations = validate_catalog(document)
    if violations:
        raise SystemExit("catalog violations: " + "; ".join(violations))
    CATALOG.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(
        "wrote",
        CATALOG,
        "historical",
        len(historical),
        "build",
        len(development),
        "lock",
        len(validation),
        "last_check",
        len(last_check),
    )


if __name__ == "__main__":
    main()
