#!/usr/bin/env python3
"""Build a station-disjoint candidate pool for Route A confirmation two."""

from __future__ import annotations

from pathlib import Path
import re
import sys

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CATALOG = ROOT / "results/framework/public_catalog/usgs_daily_temperature_series.csv"
CLUSTERS = ROOT / "results/development_v11/confirmation_candidates.csv"
V3 = ROOT / "configs/network_catalog_v3_huc8.yaml"
DEVELOPMENT = ROOT / "results/development_v11/station_gap_outcomes.csv"
FIRST_CONFIRMATION = ROOT / "results/development_v11/route_a_confirmation/predictions.csv"
OUTPUT = ROOT / "results/development_v11/second_confirmation/candidates.csv"


def _qualified_concurrent_subset(frame: pd.DataFrame) -> pd.DataFrame:
    """Greedily remove limiting endpoints until eight common catalog years."""

    selected = frame.copy()
    while len(selected) >= 3:
        overlap_days = (selected["daily_end"].min() - selected["daily_begin"].max()).days
        if overlap_days / 365.25 >= 8.0:
            return selected.sort_values("site_id")
        limiting = {
            selected["daily_begin"].idxmax(),
            selected["daily_end"].idxmin(),
        }
        choices = []
        for index in limiting:
            reduced = selected.drop(index)
            improvement = (
                reduced["daily_end"].min() - reduced["daily_begin"].max()
            ).days
            choices.append((improvement, str(selected.loc[index, "site_id"]), index))
        selected = selected.drop(max(choices)[2])
    return selected.iloc[0:0]


def new_usgs_basin_candidates(
    catalog: pd.DataFrame,
    *,
    excluded_stations: set[str],
    used_huc8: set[str],
) -> pd.DataFrame:
    """Allocate untouched stations once across HUC6, then HUC4, then HUC2."""

    stations = catalog.loc[
        ~catalog["site_id"].isin(excluded_stations)
        & pd.to_numeric(catalog["span_years"], errors="coerce").ge(8.0)
        & catalog["huc"].notna()
        & catalog["site_type"].eq("Stream")
    ].copy()
    stations["huc"] = (
        stations["huc"].str.replace(r"\.0$", "", regex=True).str.zfill(8)
    )
    stations["daily_begin"] = pd.to_datetime(stations["daily_begin"])
    stations["daily_end"] = pd.to_datetime(stations["daily_end"])
    allocated: set[str] = set()
    rows: list[dict[str, object]] = []

    for digits in (6, 4, 2):
        available = stations.loc[~stations["site_id"].isin(allocated)].copy()
        groups = []
        for basin, group in available.groupby(available["huc"].str[:digits]):
            if any(huc8.startswith(str(basin)) for huc8 in used_huc8):
                continue
            qualified = _qualified_concurrent_subset(group)
            if len(qualified) >= 3:
                groups.append((str(basin), qualified))
        for basin, group in sorted(groups, key=lambda item: (-len(item[1]), item[0])):
            group = _qualified_concurrent_subset(
                group.loc[~group["site_id"].isin(allocated)]
            )
            if len(group) < 3:
                continue
            site_ids = tuple(group["site_id"].astype(str))
            allocated.update(site_ids)
            common_start = group["daily_begin"].max()
            common_end = group["daily_end"].min()
            rows.append(
                {
                    "network_id": f"usgs2_huc{digits}_{basin}",
                    "provider": "usgs",
                    "domain": "united_states",
                    "river_group": f"untouched HUC{digits} basin {basin}",
                    "n_catalog_stations": len(group),
                    "site_ids": "|".join(site_ids),
                    "latitude": float(group["latitude"].mean()),
                    "longitude": float(group["longitude"].mean()),
                    "catalog_common_start": common_start.strftime("%Y-%m-%d"),
                    "catalog_common_end": common_end.strftime("%Y-%m-%d"),
                    "catalog_common_years": float(
                        (common_end - common_start).days / 365.25
                    ),
                    "prior_temperature_values_seen": False,
                    "candidate_status": "new_metadata_candidate_pending_daily_qc",
                    "basin_grouping": f"huc{digits}",
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    existing = pd.read_csv(CLUSTERS, dtype={"site_ids": str})
    first_scored = set(pd.read_csv(FIRST_CONFIRMATION)["network_id"].astype(str))
    carry = existing.loc[~existing["network_id"].astype(str).isin(first_scored)].copy()
    carry["candidate_status"] = "carried_unscored_candidate"

    v3 = yaml.safe_load(V3.read_text(encoding="utf-8"))
    excluded_stations = {
        str(station)
        for network in v3["networks"]
        for station in network["candidate_station_ids"]
    }
    excluded_stations.update(
        station
        for roster in existing["site_ids"].dropna().astype(str)
        for station in roster.split("|")
        if station
    )
    used_networks = set(pd.read_csv(DEVELOPMENT)["network_id"].astype(str))
    used_networks.update(first_scored)
    used_huc8 = {
        re.sub(r"^huc8_", "", network)
        for network in used_networks
        if network.startswith("huc8_")
    }
    catalog = pd.read_csv(CATALOG, dtype={"site_id": str, "huc": str})
    new = new_usgs_basin_candidates(
        catalog,
        excluded_stations=excluded_stations,
        used_huc8=used_huc8,
    )
    candidates = pd.concat([carry, new], ignore_index=True, sort=False)
    candidates = candidates.sort_values(
        ["candidate_status", "domain", "network_id"], kind="mergesort"
    ).reset_index(drop=True)
    if candidates["network_id"].duplicated().any():
        raise ValueError("second-confirmation network identifiers are not unique")
    new_rosters = [set(value.split("|")) for value in new["site_ids"]]
    if any(left & right for index, left in enumerate(new_rosters) for right in new_rosters[index + 1 :]):
        raise ValueError("new USGS second-confirmation station rosters overlap")
    if len(candidates) < 150:
        raise ValueError(f"candidate floor failed: {len(candidates)} < 150")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(OUTPUT, index=False)
    summary = {
        "candidate_networks": int(len(candidates)),
        "carried_unscored_candidates": int(len(carry)),
        "new_usgs_candidates": int(len(new)),
        "new_usgs_stations": int(
            len({station for value in new["site_ids"] for station in value.split("|")})
        ),
        "candidate_floor_150_passed": bool(len(candidates) >= 150),
        "first_confirmation_networks_excluded": bool(
            not set(candidates["network_id"]).intersection(first_scored)
        ),
    }
    pd.Series(summary).to_json(
        OUTPUT.with_name("candidate_summary.json"), indent=2
    )
    print(summary)


if __name__ == "__main__":
    main()
