#!/usr/bin/env python3
"""Lock independent external components using identities and catchment geometry."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely import Point, STRtree, from_wkt, make_valid
import yaml

import wrr_r3_common as C

RAW = C.ROOT / "data/external/wrr_revision_20261020c/hydroshare"
OUT = C.RUN / "r3_02_external_resource"
COVERAGE = C.READY / "major_revision_20261014/p0_06_coverage_recompute/final_coverage_table.csv"
COORDINATES = C.ROOT / "data/interim/v18_station_coordinates.csv"
PRIOR_SPLIT = C.ROOT / "configs/foen_prospective_split_v2.yaml"


def provider_for(region: str) -> str:
    if region == "Swiss Alps":
        return "foen"
    if region == "Austrian Alps":
        return "ehyd"
    if region == "Scandinavian Mountains":
        return "nve"
    return "hubeau"


def canonical_id(provider: str, raw: str) -> str:
    provider = "nve" if provider.startswith("nve") else provider
    raw = str(raw).strip()
    if provider == "nve":
        match = re.search(r"\d+\.\d+\.\d+", raw)
        return match.group() if match else raw
    digits = re.sub(r"\D", "", raw)
    return digits.lstrip("0") or raw


def main() -> int:
    settings = C.protocol()
    OUT.mkdir(parents=True, exist_ok=True)
    stations = pd.read_csv(RAW / "Selected_stations.csv", dtype=str)
    catchments = pd.read_csv(RAW / "Selected_catchments.csv")
    stations["provider"] = stations.Mountain_region.map(provider_for)
    stations["canonical_original_id"] = [canonical_id(provider, raw) for provider, raw in zip(stations.provider, stations.original_id)]
    prior = pd.read_csv(COVERAGE, dtype=str)
    prior["provider"] = prior.provider.str.replace("nve_hydapi", "nve", regex=False)
    existing_ids = {(provider, canonical_id(provider, raw)) for provider, raw in zip(prior.provider, prior.station_id)}
    old_split = yaml.safe_load(PRIOR_SPLIT.read_text())
    reserved_ids = {
        str(station)
        for network in old_split["networks"] if network.get("role") == "sealed"
        for station in network["station_ids"]
    }
    geometries = [make_valid(from_wkt(value)) for value in catchments.WKT]
    geometry_of = dict(zip(catchments.station_ID.astype(str), geometries))
    ordered_geometry = [geometry_of[name] for name in stations.station_ID]
    parent = list(range(len(stations)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    tree = STRtree(ordered_geometry)
    connectivity = []
    for left, geometry in enumerate(ordered_geometry):
        for right in tree.query(geometry, predicate="intersects"):
            right = int(right)
            if right <= left:
                continue
            smaller_area = min(geometry.area, ordered_geometry[right].area)
            overlap = geometry.intersection(ordered_geometry[right]).area / smaller_area if smaller_area > 0 else 0
            if overlap > 0.01:
                union(left, right)
                connectivity.append({"station_a": stations.iloc[left].station_ID, "station_b": stations.iloc[right].station_ID, "overlap_share_of_smaller_catchment": overlap})
    coordinates = pd.read_csv(COORDINATES)
    longitude = pd.to_numeric(coordinates.longitude, errors="coerce").to_numpy()
    latitude = pd.to_numeric(coordinates.latitude, errors="coerce").to_numpy()
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
    east, north = transformer.transform(longitude, latitude)
    old_points = [Point(easting, northing) if np.isfinite(easting) and np.isfinite(northing) else Point() for easting, northing in zip(east, north)]
    overlap_rows = []
    for index, row in stations.iterrows():
        reasons = []
        if (row.provider, row.canonical_original_id) in existing_ids:
            reasons.append("original_station_id_already_in_existing_archive")
        if row.provider == "foen" and str(row.original_id) in reserved_ids:
            reasons.append("reserved_under_existing_foen_protocol")
        source_east, source_north = transformer.transform(float(row["lon_EPSG:4326"]), float(row["lat_EPSG:4326"]))
        distances = np.hypot(east - source_east, north - source_north)
        nearby = np.flatnonzero(distances <= 250)
        contained = [position for position, point in enumerate(old_points) if not point.is_empty and ordered_geometry[index].covers(point)]
        if len(nearby):
            reasons.append("existing_station_within_250m_possible_alias")
        if contained:
            reasons.append("catchment_contains_existing_observation_station")
        overlap_rows.append({"station_ID": row.station_ID, "direct_exclusion_reasons": ";".join(reasons), "n_existing_stations_within_250m": len(nearby), "n_existing_stations_inside_catchment": len(contained)})
    stations = stations.merge(pd.DataFrame(overlap_rows), on="station_ID", validate="one_to_one")
    components = {}
    for index, station in enumerate(stations.station_ID):
        components.setdefault(find(index), []).append(station)
    component_of = {station: "external_" + hashlib.sha256("|".join(sorted(members)).encode()).hexdigest()[:16] for members in components.values() for station in members}
    stations["independence_group"] = stations.station_ID.map(component_of)
    excluded_components = set(stations.loc[stations.direct_exclusion_reasons.ne(""), "independence_group"])
    stations["eligible_new_component"] = ~stations.independence_group.isin(excluded_components)
    salt = settings["external_partition_salt"]
    fractions = settings["external_partition_fractions"]

    def role(component: str) -> str:
        fraction = int(hashlib.sha256(f"{salt}|{component}".encode()).hexdigest()[:16], 16) / 2**64
        if fraction < fractions["development"]:
            return "development"
        if fraction < fractions["development"] + fractions["calibration"]:
            return "calibration"
        return "test"

    stations["external_role"] = stations.independence_group.map(role)
    stations.loc[~stations.eligible_new_component, "external_role"] = "excluded_existing_or_connected"
    attributes = catchments.drop(columns="WKT").copy()
    stations = stations.merge(attributes, on="station_ID", validate="one_to_one")
    from io import StringIO
    from wrr_r3_hydrology import hydrological_strata

    stations["hydrological_stratum"] = hydrological_strata(stations)
    destination = OUT / "external_station_roles.csv"
    proposed = stations.to_csv(index=False)
    if destination.exists():
        original = pd.read_csv(destination, dtype=str).drop(columns="hydrological_stratum")
        current = pd.read_csv(StringIO(proposed), dtype=str).drop(columns="hydrological_stratum")
        if not original.equals(current):
            raise RuntimeError("External metadata partition already exists and differs; preserve the original lock")
    else:
        destination.write_text(proposed)
    stations[["station_ID", "Glaciers %", "Pt as snow", "hydrological_stratum"]].to_csv(OUT / "external_hydrology_corrected.csv", index=False)
    pd.DataFrame(connectivity).to_csv(OUT / "nested_catchment_connections.csv", index=False)
    summary = {
        "n_catalog_stations": len(stations),
        "n_independent_components": stations.independence_group.nunique(),
        "n_eligible_new_stations": int(stations.eligible_new_component.sum()),
        "eligible_components_by_role": stations.loc[stations.eligible_new_component].groupby("external_role").independence_group.nunique().to_dict(),
        "eligible_stations_by_provider": stations.loc[stations.eligible_new_component].groupby("provider").size().to_dict(),
        "continuous_temperature_acquisition_still_required": True,
        "temperature_performance_outcomes_inspected": False,
        "prior_foen_reserved_networks_opened": False,
        "prior_coordinate_coverage_note": "457 base stations have coordinates; additional previously used stations also excluded by provider-normalized identity",
        "nested_catchments_threshold": "intersection area exceeds 1% of smaller catchment",
        "partition_sha256": C.digest(destination),
    }
    C.write_json(OUT / "identity_audit.json", summary)
    C.write_json(OUT / "identity_protocol_fingerprint.json", C.fingerprint(Path(__file__), {"station_metadata": RAW / "Selected_stations.csv", "catchments": RAW / "Selected_catchments.csv", "existing_coverage": COVERAGE, "coordinates": COORDINATES, "prior_reserved_roles": PRIOR_SPLIT}))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
