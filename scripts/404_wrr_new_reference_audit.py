#!/usr/bin/env python3
"""Reproduce public metadata intake and audit sealed new-reference qualification."""
from __future__ import annotations

import argparse
import importlib
import json

import pandas as pd
import requests

import wrr_r3_common as C

R = importlib.import_module("402_wrr_au_reference_acquisition")
A = importlib.import_module("400_wrr_au_metadata_recruitment")
RAW, OUT = R.RAW, R.OUT
GEOMETRY = "https://hosting.wsapi.cloud.bom.gov.au/arcgis/rest/services/ahgf/Geofabric_V3x_All_Products/FeatureServer/49"


def metadata():
    """Keep existing vintages; a fresh download never replaces a frozen snapshot."""
    RAW.mkdir(exist_ok=True, parents=True)
    OUT.mkdir(exist_ok=True, parents=True)
    common = {"service": "kisters", "type": "queryServices", "datasource": "0", "format": "json"}
    recipes = [
        ("bom_parameter_list_valid.json", R.ENDPOINT, {"request": "getParameterList"}),
        ("bom_temperature_station_metadata.json", R.ENDPOINT, {
            "request": "getStationList", "parametertype_id": "11765", "flatten": "true",
            "returnfields": "station_id,station_no,station_name,station_latitude,station_longitude,catchment_no,catchment_id,catchment_name,object_type,object_type_shortname,river_id,river_name,site_name,ca_sta"}),
        ("bom_daily_mean_temperature_metadata.json", R.ENDPOINT, {
            "request": "getTimeseriesList", "parametertype_id": "11765", "ts_name": "DMQaQc.Merged.DailyMean.24HR",
            "returnfields": "station_name,station_no,station_id,station_latitude,station_longitude,ts_id,ts_name,parametertype_name,ts_unitsymbol,catchment_no,catchment_id,catchment_name,coverage,ts_spacing,ts_density,ts_path"}),
        ("bom_native_temperature_metadata.json", R.ENDPOINT, {
            "request": "getTimeseriesList", "parametertype_id": "11765", "ts_name": "DMQaQc.Merged.AsStored.1",
            "returnfields": "station_id,station_no,ts_id,ts_name,ts_density,ts_spacing,coverage"}),
        ("bom_quality_codes.json", R.ENDPOINT, {"request": "getQualityCodes"}),
        ("bom_all_station_catchment_attributes.json", GEOMETRY + "/query", {
            "f": "json", "where": "1=1", "outFields": "*", "returnGeometry": "false"}),
    ]
    ledger = []
    for name, endpoint, fields in recipes:
        parameters = {**common, **fields} if endpoint == R.ENDPOINT else fields
        path = RAW / name
        existed = path.exists()
        if not existed:
            response = requests.get(endpoint, params=parameters, timeout=120)
            response.raise_for_status()
            if len(response.content) > 64 << 20:
                raise RuntimeError("Metadata response exceeds intake bound")
            payload = response.json()
            if isinstance(payload, dict) and ("error" in payload or "errors" in payload):
                raise RuntimeError("Provider rejected metadata request")
            path.write_bytes(response.content)
        ledger.append({"path": str(path.relative_to(C.ROOT)),
                       "bytes": path.stat().st_size, "endpoint": endpoint,
                       "equivalent_provider_retrieval_parameters": parameters,
                       "original_metadata_request_captured_at_acquisition": not existed,
                       "metadata_only": True})
    settings = json.loads(R.CONFIG.read_text())
    parameters = A.table(RAW / "bom_parameter_list_valid.json")
    names = parameters.groupby("station_id").parametertype_name.agg(set)
    eligible = {identifier for identifier, values in names.items()
                if set(settings["metadata_recruitment"]["require_parameters"]).issubset(values)
                and not any(token in name for token in settings["metadata_recruitment"]["exclude_parameter_tokens"] for name in values)}
    numbers = set(A.table(RAW / "bom_temperature_station_metadata.json").loc[lambda d: d.station_id.isin(eligible), "station_no"])
    features = json.loads((RAW / "bom_all_station_catchment_attributes.json").read_text())["features"]
    ids = [str(f["attributes"]["objectid"]) for f in features if f["attributes"]["stationno"] in numbers]
    params = {"f": "geojson", "objectIds": ",".join(ids), "outFields": "*",
              "returnGeometry": "true", "outSR": "4326", "geometryPrecision": "6"}
    path = RAW / "bom_matched_station_catchments.geojson"
    existed = path.exists()
    if not existed:
        response = requests.get(GEOMETRY + "/query", params=params, timeout=120)
        response.raise_for_status()
        if len(response.content) > 64 << 20 or response.json().get("type") != "FeatureCollection":
            raise RuntimeError("Invalid or oversized provider catchment response")
        path.write_bytes(response.content)
    ledger.append({"path": str(path.relative_to(C.ROOT)),
                   "bytes": path.stat().st_size, "endpoint": GEOMETRY + "/query",
                   "equivalent_provider_retrieval_parameters": params,
                   "original_metadata_request_captured_at_acquisition": not existed,
                   "metadata_only": True})
    # This post-intake recipe ledger is not backdated into the original intake.
    C.write_json(OUT / "metadata_retrieval_recipes.json", {
        "scope": "equivalent public retrieval recipes; existing source vintages are preserved",
        "not_a_claim_that_all_original_metadata_wire_requests_were_logged": True,
        "sources": ledger, "temperature_values_requested": False})
    print(f"[404] {len(ledger)} metadata snapshot recipes retained", flush=True)


def audit():
    rows = []
    def check(name, passed, detail):
        rows.append({"check": name, "passed": bool(passed), "detail": str(detail)})
    plan = json.loads((OUT / "native_support_plan.json").read_text())["jobs"]
    record = json.loads((OUT / "native_support_acquisition.json").read_text())
    native = record["results"]
    check("native_plan_complete", {(r["station_id"], r["year"]) for r in plan} == {(r["station_id"], r["year"]) for r in native}, len(native))
    check("all_native_requests_resolved", all(r["status"] == "evaluated" for r in native), "access failure is pending, never zero observations")
    daily = json.loads((OUT / "daily_acquisition.json").read_text())["results"]
    check("all_daily_sources_acquired", all(r["status"] == "acquired" for r in daily), len(daily))
    qualified = pd.read_csv(OUT / "observed_reference_release.csv", dtype={"station_id": str})
    selected = qualified.loc[qualified.observed_sampling_reference_eligible.eq(True)]
    lookup = {(r["station_id"], int(r["year"])): r for r in native}
    valid_history = True
    for row in selected.itertuples(index=False):
        history = [int(x) for x in row.permitted_strictly_prior_history.split(";")]
        valid_history &= len(history) >= 3 and max(history) < row.year
        valid_history &= all(lookup[(row.station_id, year)]["complete_native_support"] for year in [*history, row.year])
    check("all_released_references_have_observed_target_and_history", valid_history, len(selected))
    roles = pd.read_csv(OUT / "metadata_candidates_and_roles.csv", dtype={"station_id": str}).set_index("station_id")
    check("roles_unchanged", all(row.role == roles.loc[row.station_id, "role"] and row.independence_group == roles.loc[row.station_id, "independence_group"] for row in qualified.itertuples(index=False)), "no quality-based role reshuffling")
    check("new_test_error_gate_closed", qualified.primary_test_error_access_allowed.eq(False).all(), "source acquisition and qualification only")
    summary = json.loads((OUT / "observed_reference_summary.json").read_text())
    check("summary_matches_reference_table", summary["qualified_observed_sampling_station_years"] == len(selected), len(selected))
    specification = json.loads((OUT / "source_head_specification.json").read_text())
    replay = {r["score_kind"]: [r["old_implementation_replay_accepted"], r["old_implementation_replay_failed"]] for r in specification["heads"]}
    check("source_only_implementation_replay", replay == {"native_CDF": [474, 12], "boost_direct": [370, 6], "boost_window": [446, 16]}, "opened old data; not Australian confirmation")
    check("no_formal_source_threshold_certified", all(r["formal_threshold"] is None for r in specification["heads"]), "insufficient independent calibration evidence retained")
    pd.DataFrame(rows).to_csv(OUT / "checks.csv", index=False)
    C.write_json(OUT / "audit_summary.json", {"checks_passed": sum(r["passed"] for r in rows),
                 "checks_total": len(rows), "all_passed": all(r["passed"] for r in rows),
                 "new_independent_confirmation_completed": False,
                 "natural_backup_confirmation_completed": False,
                 "counts_are_qualification_evidence_not_method_effects": True})
    print(f"[404] {sum(r['passed'] for r in rows)}/{len(rows)} intake checks pass; primary evaluation remains sealed", flush=True)
    return int(not all(r["passed"] for r in rows))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["metadata", "audit"])
    args = parser.parse_args()
    return metadata() if args.action == "metadata" else audit()


if __name__ == "__main__":
    raise SystemExit(main())
