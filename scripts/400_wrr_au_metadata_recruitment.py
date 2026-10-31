#!/usr/bin/env python3
"""Recruit a new water-temperature reference pool using metadata only."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union

import wrr_r3_common as C
from stream_recoverability.seeds import plain_seed

RAW = C.ROOT / "data/external/wrr_au_confirmation_20261021"
OUT = C.READY / "followup_20261021/au_confirmation"
CONFIG = C.ROOT / "configs/wrr_au_reference_qualification_20261021.json"
# Fixed seed of the one uniform draw per component label that assigns roles.
ROLE_SEED = 400


def table(path):
    payload = json.loads(path.read_text())
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        raise ValueError(f"Expected a public metadata table: {path}")
    return pd.DataFrame(payload[1:], columns=payload[0])


def component_group(members):
    """Readable component label: the smallest member station identifier."""
    return "au_" + sorted(map(str, members))[0]


def component_roles(groups, settings):
    """One seeded uniform draw per sorted component label decides its role."""
    labels = sorted(set(groups))
    numbers = np.random.default_rng(plain_seed(ROLE_SEED)).random(len(labels))
    fractions = settings["roles"]["fractions"]
    return {label: "development" if number < fractions["development"] else "calibration" if number < fractions["development"] + fractions["calibration"] else "test"
            for label, number in zip(labels, numbers)}


def main():
    settings = json.loads(CONFIG.read_text())
    OUT.mkdir(exist_ok=True, parents=True)
    parameters = table(RAW / "bom_parameter_list_valid.json")
    stations = table(RAW / "bom_temperature_station_metadata.json")
    series = table(RAW / "bom_daily_mean_temperature_metadata.json")
    if stations.station_id.duplicated().any() or series.station_id.duplicated().any():
        raise ValueError("Ambiguous station or daily-mean series metadata")
    types = parameters.groupby("station_id").parametertype_name.agg(set)
    required = set(settings["metadata_recruitment"]["require_parameters"])
    eligible_parameter_ids = {
        identifier for identifier, names in types.items()
        if required.issubset(names) and not any(token in name for token in settings["metadata_recruitment"]["exclude_parameter_tokens"] for name in names)
    }
    daily = series[["station_id", "ts_id", "ts_name", "ts_unitsymbol", "ts_spacing", "from", "to"]]
    frame = stations.merge(daily, on="station_id", how="inner", validate="one_to_one")
    frame["metadata_watercourse_candidate"] = frame.station_id.isin(eligible_parameter_ids)
    frame = frame.loc[frame.metadata_watercourse_candidate].copy().reset_index(drop=True)
    frame["medium_status"] = np.where(frame.object_type.isin(settings["metadata_recruitment"]["allowed_object_types"]), "watercourse_parameter_supported", "pending_object_type_review")
    for token in settings["metadata_recruitment"]["medium_review_name_tokens"]:
        frame.loc[frame.station_name.str.upper().str.contains(token, regex=False), "medium_status"] = "pending_engineered_or_ambiguous_medium_review"
    if not frame.ts_name.eq(settings["time_series_name"]).all() or not frame.ts_spacing.eq("P1D").all():
        raise ValueError("Reference metadata are not the declared daily mean")
    if not frame.ts_unitsymbol.eq("°C").all():
        raise ValueError("Unverified water-temperature units")
    frame["owner_state"] = frame.DATA_OWNER_NAME.str.extract(r"^([A-Z]{2,3})\s+-", expand=False)
    frame["local_standard_offset_hours"] = frame.owner_state.map(settings["daily_reference"]["owner_state_offsets_hours"])
    shape_payload = json.loads((RAW / "bom_matched_station_catchments.geojson").read_text())
    grouped_geometry, attributes = {}, {}
    project = Transformer.from_crs(4326, 3577, always_xy=True)
    for feature in shape_payload["features"]:
        info = feature["properties"]
        identifier = str(info["stationno"])
        geom = make_valid(shape(feature["geometry"]))
        grouped_geometry.setdefault(identifier, []).append(geom)
        attributes.setdefault(identifier, []).append(info)
    geometries, member_positions = {}, []
    for position, row in frame.iterrows():
        reasons = []
        if row.medium_status != "watercourse_parameter_supported":
            reasons.append(row.medium_status)
        if not np.isfinite(row.local_standard_offset_hours):
            reasons.append("unverified_local_calendar_offset")
        if row.station_no not in grouped_geometry:
            reasons.append("no_exact_official_station_catchment")
        else:
            notes = " ".join(str(a.get("catchnotes") or "") for a in attributes[row.station_no]).lower()
            if any(token in notes for token in settings["metadata_recruitment"]["retired_geometry_note_tokens"]):
                reasons.append("historical_or_uncertain_station_geometry_note")
            polygon = unary_union(grouped_geometry[row.station_no])
            projected = transform(project.transform, polygon)
            point = transform(project.transform, Point(float(row.station_longitude), float(row.station_latitude)))
            if projected.distance(point) > settings["metadata_recruitment"]["gauge_to_catchment_tolerance_m"]:
                reasons.append("station_coordinate_outside_declared_catchment_tolerance")
            if projected.area <= 0:
                reasons.append("invalid_catchment_area")
            if not reasons:
                geometries[position] = projected
                member_positions.append(position)
            frame.loc[position, "catchment_area_km2"] = float(projected.area / 1e6)
            frame.loc[position, "drainage_division"] = ";".join(sorted({str(a.get("divname")) for a in attributes[row.station_no]}))
            frame.loc[position, "river_region"] = ";".join(sorted({str(a.get("rivregname")) for a in attributes[row.station_no]}))
        frame.loc[position, "metadata_pending_reasons"] = ";".join(reasons)
    parent = {i: i for i in member_positions}
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    overlap = []
    for k, left in enumerate(member_positions):
        for right in member_positions[k + 1:]:
            a, b = geometries[left], geometries[right]
            if not a.intersects(b):
                continue
            ratio = a.intersection(b).area / min(a.area, b.area)
            if ratio > settings["metadata_recruitment"]["overlap_share_of_smaller_catchment_for_grouping"]:
                parent[find(right)] = find(left)
                overlap.append({"station_a": frame.loc[left, "station_id"], "station_b": frame.loc[right, "station_id"], "overlap_share_smaller_catchment": float(ratio)})
    components = {}
    for position in member_positions:
        components.setdefault(find(position), []).append(position)
    frame["independence_group"] = ""
    frame["role"] = "pending_metadata"
    labels = {root: component_group(frame.loc[positions, "station_id"].tolist()) for root, positions in components.items()}
    roles = component_roles(labels.values(), settings)
    for root, positions in components.items():
        frame.loc[positions, "independence_group"] = labels[root]
        frame.loc[positions, "role"] = roles[labels[root]]
    frame["daily_reference_qualified"] = False
    frame["new_temperature_prediction_errors_opened"] = False
    frame.to_csv(OUT / "metadata_candidates_and_roles.csv", index=False)
    pd.DataFrame(overlap, columns=["station_a", "station_b", "overlap_share_smaller_catchment"]).to_csv(OUT / "nested_catchment_connections.csv", index=False)
    resolved = frame.role.ne("pending_metadata")
    C.write_json(OUT / "metadata_summary.json", {
        "water_temperature_station_parameters": int(series.station_id.nunique()),
        "watercourse_colocated_without_ground_or_storage_parameters": len(frame),
        "geometrically_resolved_watercourse_stations": int(resolved.sum()),
        "pending_metadata_stations": int((~resolved).sum()),
        "connected_catchment_components": len(components),
        "component_roles": frame.loc[resolved].groupby("role").independence_group.nunique().to_dict(),
        "station_roles": frame.loc[resolved].role.value_counts().to_dict(),
        "provider_daily_mean_reference_quality_still_to_be_checked": True,
        "quality_code_A_is_not_independent_backup_truth": True,
        "record_geometry_disjointness_does_not_prove_independent_regional_weather": True,
        "new_confirmation_completed": False,
        "test_prediction_errors_opened": False,
        "pending_is_not_zero_eligible": True,
    })
    print(f"[400] {int(resolved.sum())} stations in {len(components)} metadata-connected components; {int((~resolved).sum())} pending; references and test errors remain unassessed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
