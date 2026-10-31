#!/usr/bin/env python3
"""Inventory an unscored USGS reference resource using metadata alone."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re

import numpy as np
import pandas as pd
from pyproj import Geod
import requests

import wrr_r3_common as C

RAW = C.ROOT / "data/external/wrr_usgs_new_reference_20261021/metadata"
OUT = C.READY / "followup_20261021/usgs_reference_preflight"
CONFIG = C.ROOT / "configs/wrr_usgs_reference_preflight_20261021.json"
BASE = "https://api.waterdata.usgs.gov/ogcapi/v1/collections"
FIELDS = "id,monitoring_location_id,monitoring_location_number,monitoring_location_name,agency_code,country_code,state_name,site_type_code,site_type,hydrologic_unit_code,altitude,drainage_area,time_zone_abbreviation,uses_daylight_savings,horizontal_positional_accuracy,unit_of_measure,parameter_code,statistic_id,begin,end,data_type,computation_identifier,sublocation_identifier,primary,parent_time_series_id"
OLD = C.ROOT / "data/external/wrr_neon_confirmation_20261021/old_usgs_station_metadata.csv"
HEADERS = OLD.parent / "old_header_station_inventory.csv"
BACKUP = OUT.parent / "public_backup_search/selected_public_channel_metadata.json"


def station_number(value):
    """Normalize a provider prefix only; never guess lost zeros or suffixes."""
    text = str(value).strip().removeprefix("USGS-")
    if not re.fullmatch(r"\d{8,15}", text):
        raise ValueError(f"Unverified USGS station identity: {value!r}")
    return text


def huc8(value):
    """A reported HUC8/10/12 prefix is a screen, not a connectivity proof."""
    text = str(value).strip()
    return text[:8] if re.fullmatch(r"\d{8}(?:\d{2}){0,2}", text) and set(text[:8]) != {"0"} else ""


def interval_can_support(begin, end, target_year, history_years=3):
    """Necessary period bounds only; missing dates and approvals remain unknown.

    A 24-hour outer allowance accommodates metadata expressed in UTC instead of
    the local daily label. Actual reference qualification must use the verified
    local calendar and native observations; this deliberately optimistic test
    does not certify even a single complete year.
    """
    start, stop = pd.to_datetime(begin, utc=True, errors="coerce"), pd.to_datetime(end, utc=True, errors="coerce")
    if pd.isna(start) or pd.isna(stop) or stop < start:
        return False
    required_start = pd.Timestamp(f"{target_year - history_years}-01-01", tz="UTC") + pd.Timedelta(days=1)
    required_end = pd.Timestamp(f"{target_year}-12-31", tz="UTC") - pd.Timedelta(days=1)
    return bool(start <= required_start and stop >= required_end)


def cached_collection(path, endpoint, parameters):
    """Acquire bounded public metadata; no observation endpoint is allowed."""
    allowed = {f"{BASE}/time-series-metadata/items", f"{BASE}/combined-metadata/items"}
    if endpoint not in allowed:
        raise ValueError("Only the two declared metadata endpoints are allowed")
    ledger_path = path.with_suffix(".request.json")
    if path.exists():
        ledger = json.loads(ledger_path.read_text())
        if ledger["endpoint"] != endpoint or ledger["parameters"] != parameters:
            raise RuntimeError("Metadata cache retrieval recipe changed")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(endpoint, params=parameters, timeout=50)
        # Authentication, access, quota and transport failures do not become
        # empty candidate catalogs, and never trigger an alternate endpoint.
        response.raise_for_status()
        if len(response.content) > 32 << 20:
            raise RuntimeError("Metadata response exceeds the declared bound")
        payload = response.json()
        if payload.get("type") != "FeatureCollection":
            raise ValueError("Expected a public metadata FeatureCollection")
        path.write_bytes(response.content)
        C.write_json(ledger_path, {"endpoint": endpoint, "parameters": parameters,
                     "bytes": len(response.content),
                     "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
                     "temperature_values_requested": False})
    payload = json.loads(path.read_text())
    if payload.get("type") != "FeatureCollection" or any(link["rel"] == "next" for link in payload.get("links", [])):
        raise RuntimeError("National metadata response is incomplete; do not report a partial source count")
    identifiers = [feature["id"] for feature in payload["features"]]
    if len(set(identifiers)) != len(identifiers) or payload.get("numberReturned", len(identifiers)) != len(identifiers):
        raise RuntimeError("Metadata identifiers or returned count are inconsistent")
    if any("value" in feature["properties"] for feature in payload["features"]):
        raise RuntimeError("A metadata response unexpectedly contains measurement values")
    return payload


def collections():
    series = cached_collection(RAW / "daily_mean_temperature_catalog.json", f"{BASE}/time-series-metadata/items", {
        "f": "json", "parameter_code": "00010", "statistic_id": "00003", "computation_period_identifier": "Daily", "primary": "Primary", "limit": 10000})
    combined = cached_collection(RAW / "combined_daily_mean_temperature_metadata.json", f"{BASE}/combined-metadata/items", {
        "f": "json", "parameter_code": "00010", "statistic_id": "00003", "primary": "Primary", "properties": FIELDS, "limit": 10000})
    return series, combined


def prior_records():
    """Keep both records and the conservative header-only exposure inventory."""
    old = pd.read_csv(OLD, dtype=str)
    headers = pd.read_csv(HEADERS, dtype=str)
    numbers = {station_number(value) for value in old.site_no} | {station_number(value) for value in headers.station_id}
    contexts = {huc8(value) for value in old.huc_cd} - {""}
    locations = [{"site": station_number(row.site_no), "longitude": float(row.dec_long_va), "latitude": float(row.dec_lat_va)} for row in old.itertuples(index=False)]
    for site in json.loads(BACKUP.read_text())["sites"]:
        number = station_number(site["site"])
        numbers.add(number)
        feature = site["site_metadata"]
        coordinates = feature["geometry"]["coordinates"]
        locations.append({"site": number, "longitude": float(coordinates[0]), "latitude": float(coordinates[1])})
        context = huc8(feature["properties"]["hydrologic_unit_code"])
        if context:
            contexts.add(context)
    locations = pd.DataFrame(locations).drop_duplicates(["site", "longitude", "latitude"])
    if not np.isfinite(locations[["longitude", "latitude"]]).all().all():
        raise ValueError("Some previously inventoried coordinates remain unresolved")
    return numbers, contexts, locations


def series_scope(series, combined, settings, old_numbers, old_contexts, old_locations):
    """Preserve every series, candidate and review flag without assigning roles."""
    first = {feature["id"]: feature for feature in series["features"]}
    second = {feature["id"]: feature for feature in combined["features"]}
    if set(first) - set(second):
        raise RuntimeError("Some catalog series lack combined location metadata")
    channel_counts = pd.Series([f["properties"]["monitoring_location_id"] for f in first.values()]).value_counts()
    rows = []
    geod = Geod(ellps="WGS84")
    years = sorted({year for values in settings["role_target_years"].values() for year in values})
    for identifier in sorted(first):
        source, meta = first[identifier], second[identifier]
        p, q = source["properties"], meta["properties"]
        for field, expected in (("parameter_code", "00010"), ("statistic_id", "00003"), ("computation_identifier", "Mean"), ("primary", "Primary"), ("unit_of_measure", "degC")):
            if p.get(field) != expected or q.get(field) != expected:
                raise ValueError(f"Catalog filter/units mismatch for {field}")
        if p.get("computation_period_identifier") != "Daily" or q.get("data_type") != "Daily values":
            raise ValueError("Continuous or noncalendar data cannot become a daily reference")
        identity = str(p["monitoring_location_id"])
        if q["monitoring_location_id"] != identity:
            raise ValueError("Time-series and location identities disagree")
        if q.get("agency_code") == "USGS":
            number = station_number(identity)
            if not identity.startswith("USGS-") or station_number(q["monitoring_location_number"]) != number:
                raise ValueError("Time-series and location identities disagree")
        else:
            # The federal service also catalogs other agencies. Retain their
            # explicit identities and exclude them by the unchanged agency rule.
            number = identity
        geom = meta.get("geometry") or {}
        coordinates = geom.get("coordinates") if geom.get("type") == "Point" else None
        valid_coordinate = (isinstance(coordinates, list) and len(coordinates) == 2 and
                            np.isfinite(coordinates).all() and -180 <= coordinates[0] <= 180 and -90 <= coordinates[1] <= 90)
        near = []
        if valid_coordinate:
            distance = geod.inv(old_locations.longitude.tolist(), old_locations.latitude.tolist(),
                                [coordinates[0]] * len(old_locations), [coordinates[1]] * len(old_locations))[2]
            near = sorted(set(old_locations.loc[np.asarray(distance) <= settings["prior_record_screen"]["near_duplicate_tolerance_m"], "site"]))
        context = huc8(q.get("hydrologic_unit_code"))
        feasible = [year for year in years if interval_can_support(p["begin"], p["end"], year, settings["minimum_complete_prior_history_years"]) and
                    interval_can_support(q["begin"], q["end"], year, settings["minimum_complete_prior_history_years"])]
        reasons = []
        if number in old_numbers:
            reasons.append("previous_exact_station_access")
        if near:
            reasons.append("previous_station_within_250m")
        if q.get("agency_code") != "USGS" or q.get("country_code") != "US":
            reasons.append("outside_declared_agency_or_country")
        if q.get("site_type_code") != settings["reference_site_type_code"]:
            reasons.append("outside_declared_stream_medium")
        if not valid_coordinate:
            reasons.append("pending_location_coordinate")
        if not context:
            reasons.append("pending_HUC_metadata")
        if not feasible:
            reasons.append("metadata_period_cannot_support_prespecified_years")
        if channel_counts[p["monitoring_location_id"]] != 1:
            reasons.append("pending_multiple_primary_daily_channels")
        name = q.get("monitoring_location_name") or ""
        if any(token in name.upper() for token in settings["engineered_name_review_tokens"]):
            reasons.append("pending_engineered_location_review")
        rows.append({
            "series_id": identifier, "station_id": number, "station_name": name, "agency_code": q.get("agency_code"),
            "site_type_code": q.get("site_type_code"), "state_name": q.get("state_name"),
            "longitude": coordinates[0] if valid_coordinate else np.nan,
            "latitude": coordinates[1] if valid_coordinate else np.nan,
            "HUC": q.get("hydrologic_unit_code"), "HUC8": context, "HUC2_region_proxy": context[:2],
            "same_HUC8_as_prior_record": context in old_contexts if context else False,
            "previous_stations_within_250m": ";".join(near),
            "begin": p["begin"], "end": p["end"], "parent_time_series_id": p.get("parent_time_series_id"),
            "metadata_feasible_target_years": ";".join(map(str, feasible)),
            "initial_metadata_candidate": not reasons,
            "scope_status": ";".join(reasons) if reasons else "pending_network_prior_pool_event_and_reference_qualification",
            "reference_quality_qualified": False, "native_daily_support_verified": False,
            "new_role_assigned": False, "new_prediction_errors_opened": False,
            "new_temperature_value_access_allowed": False,
        })
    return pd.DataFrame(rows)


def summarize():
    settings = json.loads(CONFIG.read_text())
    if any(settings[name] for name in ("new_temperature_values_may_be_requested", "new_roles_may_be_assigned", "new_prediction_errors_may_be_opened")):
        raise RuntimeError("This preflight must not authorize new observations, roles or prediction errors")
    series, combined = collections()
    numbers, contexts, locations = prior_records()
    OUT.mkdir(parents=True, exist_ok=True)
    frame = series_scope(series, combined, settings, numbers, contexts, locations)
    frame.to_csv(OUT / "all_daily_series_scope.csv", index=False)
    candidates = frame.loc[frame.initial_metadata_candidate].copy()
    candidates.to_csv(OUT / "metadata_candidates.csv", index=False)
    year_rows = []
    for role, years in settings["role_target_years"].items():
        for year in years:
            work = candidates.loc[candidates.metadata_feasible_target_years.str.split(";").map(lambda values: str(year) in values)]
            outside = work.loc[~work.same_HUC8_as_prior_record]
            year_rows.append({"planned_role_year": role, "year": year, "necessary_period_sites": work.station_id.nunique(),
                              "HUC8_proxies": work.HUC8.nunique(), "sites_outside_previous_HUC8": outside.station_id.nunique(),
                              "HUC8_proxies_outside_previous_HUC8": outside.HUC8.nunique(),
                              "roles_assigned": False, "daily_quality_and_native_support_verified": False,
                              "HUC8_does_not_verify_network_or_weather_independence": True})
    pd.DataFrame(year_rows).to_csv(OUT / "necessary_period_support.csv", index=False)
    summary = {
        "status": "metadata_candidates_not_new_reference_records_or_confirmation",
        "national_primary_daily_mean_series": len(frame), "national_primary_daily_mean_stations": frame.station_id.nunique(),
        "USGS_primary_daily_mean_stations": frame.loc[frame.agency_code.eq("USGS"), "station_id"].nunique(),
        "other_agency_series_retained_and_excluded": int(frame.agency_code.ne("USGS").sum()),
        "old_exact_station_numbers_excluded_from_eligibility": len(numbers),
        "not_in_current_exact_station_inventory": frame.loc[~frame.station_id.isin(numbers), "station_id"].nunique(),
        "initial_metadata_candidate_stations": candidates.station_id.nunique(),
        "initial_metadata_candidate_HUC8_proxies": candidates.HUC8.nunique(),
        "candidate_stations_outside_previous_HUC8": candidates.loc[~candidates.same_HUC8_as_prior_record, "station_id"].nunique(),
        "candidate_HUC8_proxies_outside_previous_HUC8": candidates.loc[~candidates.same_HUC8_as_prior_record, "HUC8"].nunique(),
        "HUC8_is_not_verified_hydrologic_or_event_independence": True,
        "repository_prior_access_audit_complete": False,
        "network_connection_and_event_dependence_audit_complete": False,
        "reference_quality_qualified_station_years": None,
        "new_temperature_observations_acquired": False, "new_roles_assigned": False,
        "new_H30_prediction_errors_opened": False, "new_independent_confirmation_completed": False,
        "catalog_interval_is_not_completeness_or_approval_evidence": True,
        "next_action": "Verify network and prior-pool connections before fixing new component roles and requesting reference temperatures.",
    }
    C.write_json(OUT / "summary.json", summary)
    print(f"[410] {len(frame)} daily-mean series / {frame.station_id.nunique()} sites; "
          f"{candidates.station_id.nunique()} initial metadata candidates; no new temperatures or roles", flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["fetch", "summarize"])
    args = parser.parse_args()
    if args.action == "fetch":
        collections()
        return 0
    return summarize()


if __name__ == "__main__":
    raise SystemExit(main())
