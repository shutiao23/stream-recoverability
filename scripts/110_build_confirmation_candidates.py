#!/usr/bin/env python3
"""Build a wholly-new metadata candidate pool for the next confirmation."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "results/framework/public_catalog"
OUTPUT = ROOT / "results/development_v11/confirmation_candidates.csv"


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def hubeau_candidates() -> list[dict[str, object]]:
    stations = pd.read_csv(
        CATALOG / "hubeau_all_stations.csv", dtype={"site_id": str}
    )
    prior_loire = set(
        pd.read_csv(
            CATALOG / "loire_hubeau_stations.csv", dtype={"site_id": str}
        )["site_id"]
    )
    stations = stations.loc[~stations["site_id"].isin(prior_loire)]
    rows = []
    for river, group in stations.groupby("river"):
        if len(group) < 3 or not str(river).strip():
            continue
        rows.append(
            {
                "network_id": f"hubeau_{slug(str(river))}",
                "provider": "hubeau",
                "domain": "france",
                "river_group": str(river),
                "n_catalog_stations": len(group),
                "site_ids": "|".join(sorted(group["site_id"].astype(str))),
                "latitude": float(group["latitude"].mean()),
                "longitude": float(group["longitude"].mean()),
                "prior_temperature_values_seen": False,
            }
        )
    return rows


def foen_candidates() -> list[dict[str, object]]:
    stations = pd.read_csv(
        CATALOG / "foen_temperature_station_metadata_20260826.csv",
        dtype={"site_id": str},
    )
    burned_networks = set()
    qc = ROOT / "results/framework/t2_sealed_confirmatory_v1/sealed_qc_v1"
    for path in qc.glob("*.csv"):
        table = pd.read_csv(path)
        if "network_id" in table:
            burned_networks.update(table["network_id"].dropna().astype(str))
    burned_rivers = {
        network.removeprefix("foen_").split("_")[0]
        for network in burned_networks
        if network.startswith("foen_")
    }
    burned_sites = set(
        pd.read_csv(qc / "station_qc.csv", dtype={"site_id": str})["site_id"]
    )
    rows = []
    unseen = stations.loc[~stations["site_id"].isin(burned_sites)]
    for river_key, group in unseen.groupby("river_key"):
        if len(group) < 3 or str(river_key) in burned_rivers:
            continue
        catchments = sorted(group["catchment_key"].dropna().astype(str).unique())
        suffix = catchments[0] if len(catchments) == 1 else "multi"
        network = f"foen_{river_key}_{suffix}"
        rows.append(
            {
                "network_id": network,
                "provider": "foen",
                "domain": "switzerland",
                "river_group": str(group["river_name"].iloc[0]),
                "n_catalog_stations": len(group),
                "site_ids": "|".join(sorted(group["site_id"].astype(str))),
                "latitude": float(group["latitude"].mean()),
                "longitude": float(group["longitude"].mean()),
                "prior_temperature_values_seen": False,
            }
        )
    return rows


def usgs_never_seen_candidates() -> list[dict[str, object]]:
    split = yaml.safe_load(
        (ROOT / "configs/network_catalog_v3_split.yaml").read_text(encoding="utf-8")
    )
    station_catalog = pd.read_csv(
        CATALOG / "usgs_daily_temperature_series.csv", dtype={"site_id": str}
    )
    network_catalog = yaml.safe_load(
        (ROOT / "configs/network_catalog_v3_huc8.yaml").read_text(encoding="utf-8")
    )
    station_rosters = {
        row["network_id"]: row["candidate_station_ids"]
        for row in network_catalog["networks"]
    }
    rows = []
    for network in split["networks"]:
        if network["role"] != "never_sealed" or network["n_stations"] < 3:
            continue
        station_ids = station_rosters[network["network_id"]]
        stations = station_catalog.loc[station_catalog["site_id"].isin(station_ids)]
        rows.append(
            {
                "network_id": network["network_id"],
                "provider": "usgs",
                "domain": "united_states",
                "river_group": network["network_id"],
                "n_catalog_stations": len(station_ids),
                "site_ids": "|".join(station_ids),
                "latitude": float(stations["latitude"].mean()),
                "longitude": float(stations["longitude"].mean()),
                "prior_temperature_values_seen": False,
            }
        )
    return rows


def usgs_name_huc4_candidates() -> list[dict[str, object]]:
    """New name-by-HUC4 groups after removing every v3 station."""

    clusters = pd.read_csv(
        CATALOG / "usgs_river_clusters_v2.csv",
        dtype={"site_ids": str, "huc4": str},
    )
    clusters = clusters.loc[
        clusters["grouping"].eq("name_huc4")
        & pd.to_numeric(clusters["min_stations"]).eq(3)
        & pd.to_numeric(clusters["min_overlap_years"]).eq(8.0)
        & pd.to_numeric(clusters["min_span_years"]).eq(8.0)
    ].copy()
    catalog = pd.read_csv(
        CATALOG / "usgs_daily_temperature_series.csv", dtype={"site_id": str}
    )
    catalog["daily_begin"] = pd.to_datetime(catalog["daily_begin"])
    catalog["daily_end"] = pd.to_datetime(catalog["daily_end"])
    catalog["span_years"] = pd.to_numeric(catalog["span_years"])
    v3 = yaml.safe_load(
        (ROOT / "configs/network_catalog_v3_huc8.yaml").read_text(encoding="utf-8")
    )
    excluded = {
        str(station)
        for network in v3["networks"]
        for station in network["candidate_station_ids"]
    }
    eligible_groups = []
    for cluster in clusters.to_dict("records"):
        remaining = [
            station
            for station in str(cluster["site_ids"]).split(",")
            if station and station not in excluded
        ]
        stations = catalog.loc[
            catalog["site_id"].isin(remaining) & catalog["span_years"].ge(8.0)
        ].drop_duplicates("site_id")
        common_start = stations["daily_begin"].max()
        common_end = stations["daily_end"].min()
        common_years = float((common_end - common_start).days / 365.25)
        if len(stations) >= 3 and common_years >= 8.0:
            eligible_groups.append((cluster, stations, common_years))

    used: set[str] = set()
    rows = []
    for cluster, stations, _ in sorted(
        eligible_groups,
        key=lambda item: (-len(item[1]), -item[2], str(item[0]["network_id"])),
    ):
        stations = stations.loc[~stations["site_id"].isin(used)].copy()
        common_start = stations["daily_begin"].max()
        common_end = stations["daily_end"].min()
        common_years = float((common_end - common_start).days / 365.25)
        if len(stations) >= 3 and common_years >= 8.0:
            station_roster = tuple(sorted(stations["site_id"].astype(str)))
            used.update(station_roster)
            rows.append(
                {
                    "network_id": f"usgs_{cluster['network_id']}",
                    "provider": "usgs",
                    "domain": "united_states",
                    "river_group": (
                        f"{cluster['river_name']} (HUC4 {cluster['huc4']})"
                    ),
                    "n_catalog_stations": len(station_roster),
                    "site_ids": "|".join(station_roster),
                    "latitude": float(stations["latitude"].mean()),
                    "longitude": float(stations["longitude"].mean()),
                    "prior_temperature_values_seen": False,
                }
            )
    return rows


def usgs_name_huc2_candidates() -> list[dict[str, object]]:
    """New exact-name HUC2 groups beyond v3 and selected name-HUC4 stations."""

    clusters = pd.read_csv(
        CATALOG / "usgs_river_clusters_v2.csv",
        dtype={"site_ids": str, "huc2": str},
    )
    clusters = clusters.loc[
        clusters["grouping"].eq("name_huc2")
        & pd.to_numeric(clusters["min_stations"]).eq(3)
        & pd.to_numeric(clusters["min_overlap_years"]).eq(8.0)
        & pd.to_numeric(clusters["min_span_years"]).eq(8.0)
    ].copy()
    catalog = pd.read_csv(
        CATALOG / "usgs_daily_temperature_series.csv", dtype={"site_id": str}
    )
    catalog["daily_begin"] = pd.to_datetime(catalog["daily_begin"])
    catalog["daily_end"] = pd.to_datetime(catalog["daily_end"])
    catalog["span_years"] = pd.to_numeric(catalog["span_years"])
    v3 = yaml.safe_load(
        (ROOT / "configs/network_catalog_v3_huc8.yaml").read_text(encoding="utf-8")
    )
    excluded = {
        str(station)
        for network in v3["networks"]
        for station in network["candidate_station_ids"]
    }
    excluded.update(
        station
        for candidate in usgs_name_huc4_candidates()
        for station in str(candidate["site_ids"]).split("|")
    )
    eligible_groups = []
    for cluster in clusters.to_dict("records"):
        remaining = [
            station
            for station in str(cluster["site_ids"]).split(",")
            if station and station not in excluded
        ]
        stations = catalog.loc[
            catalog["site_id"].isin(remaining) & catalog["span_years"].ge(8.0)
        ].drop_duplicates("site_id")
        common_years = float(
            (stations["daily_end"].min() - stations["daily_begin"].max()).days
            / 365.25
        )
        if len(stations) >= 3 and common_years >= 8.0:
            eligible_groups.append((cluster, stations, common_years))

    used: set[str] = set()
    rows = []
    for cluster, stations, _ in sorted(
        eligible_groups,
        key=lambda item: (-len(item[1]), -item[2], str(item[0]["network_id"])),
    ):
        stations = stations.loc[~stations["site_id"].isin(used)].copy()
        common_years = float(
            (stations["daily_end"].min() - stations["daily_begin"].max()).days
            / 365.25
        )
        if len(stations) >= 3 and common_years >= 8.0:
            station_roster = tuple(sorted(stations["site_id"].astype(str)))
            used.update(station_roster)
            rows.append(
                {
                    "network_id": f"usgs_{cluster['network_id']}",
                    "provider": "usgs",
                    "domain": "united_states",
                    "river_group": (
                        f"{cluster['river_name']} (HUC2 {cluster['huc2']})"
                    ),
                    "n_catalog_stations": len(station_roster),
                    "site_ids": "|".join(station_roster),
                    "latitude": float(stations["latitude"].mean()),
                    "longitude": float(stations["longitude"].mean()),
                    "prior_temperature_values_seen": False,
                }
            )
    return rows


def main() -> None:
    core = pd.DataFrame(
        [
            *hubeau_candidates(),
            *foen_candidates(),
            *usgs_never_seen_candidates(),
            *usgs_name_huc4_candidates(),
            *usgs_name_huc2_candidates(),
        ]
    )
    core["candidate_status"] = "metadata_candidate_pending_daily_qc"
    if OUTPUT.exists():
        existing = pd.read_csv(OUTPUT, dtype={"site_ids": str})
        external = existing.loc[
            ~existing["provider"].isin(("hubeau", "foen", "usgs"))
        ]
        candidates = pd.concat([core, external], ignore_index=True, sort=False)
    else:
        candidates = core
    candidates = candidates.sort_values(["domain", "network_id"])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(OUTPUT, index=False)
    print(
        candidates.groupby(["domain", "provider"]).agg(
            networks=("network_id", "size"),
            stations=("n_catalog_stations", "sum"),
        )
    )
    print(f"total_candidates={len(candidates)}")


if __name__ == "__main__":
    main()
