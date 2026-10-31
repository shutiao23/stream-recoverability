#!/usr/bin/env python3
"""Check source size, upstream overlap and verified site context before temperatures."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Geod
from shapely.geometry import Point, shape
import yaml

import wrr_r3_common as C
from stream_recoverability.experiments.v19_revision.risk import bounded_mean_upper

RAW = C.ROOT / "data/external/wrr_neon_confirmation_20261021"
OUT = C.READY / "followup_20261021/neon_recruitment"
SPEC = C.ROOT / "configs/wrr_next_confirmation_20261021.yaml"


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def ideal_group_floor(risk_cap, alpha, candidate_count=1):
    """Necessary floor for this fixed rule, even at zero loss and full admission."""
    if not 0 < risk_cap < 1 or not 0 < alpha < 1 or candidate_count < 1:
        raise ValueError("Invalid risk/evidence allocation")
    count = math.ceil(math.log(alpha / candidate_count) / math.log1p(-risk_cap))
    while bounded_mean_upper(0.0, count, alpha=alpha / candidate_count) > risk_cap:
        count += 1
    return count


def main():
    sites = json.loads((RAW / "selected_site_metadata.json").read_text())["sites"]
    settings = yaml.safe_load(SPEC.read_text())
    cap = settings["selected_risk_cap"]
    alpha = settings["joint_error_allocation"]["formal_calibration_per_method"]
    floor = ideal_group_floor(cap, alpha)
    old = pd.read_csv(RAW / "old_usgs_station_metadata.csv", dtype=str)
    latitude = pd.to_numeric(old.dec_lat_va, errors="coerce").to_numpy()
    longitude = pd.to_numeric(old.dec_long_va, errors="coerce").to_numpy()
    if not (np.isfinite(latitude).all() and np.isfinite(longitude).all()):
        raise ValueError("Some previously accessed station coordinates remain unavailable")
    polygons = {f["properties"]["SiteID"]: shape(f["geometry"]) for f in
                json.loads((RAW / "neon_watersheds.geojson").read_text())["features"]}
    geod = Geod(ellps="WGS84")
    rows = []
    for site in sites:
        code = site["siteCode"]
        _, _, distances = geod.inv(longitude, latitude,
                                  np.full(len(old), site["siteLongitude"]),
                                  np.full(len(old), site["siteLatitude"]))
        near = old.loc[distances <= 250, "site_no"].tolist()
        inside = [row.site_no for row in old.itertuples(index=False)
                  if polygons[code].covers(Point(float(row.dec_long_va), float(row.dec_lat_va)))]
        rows.append({"site": code, "name": site["siteName"], "domain": site["domainCode"],
                     "latitude": site["siteLatitude"], "longitude": site["siteLongitude"],
                     "prior_station_within_250m": ";".join(near),
                     "prior_stations_within_NEON_upstream_watershed": ";".join(inside),
                     "downstream_prior_record_disjointness_verified": False,
                     "new_temperature_measurement_tables_opened": False,
                     "standalone_primary_recruitment": False})
    # Facts are scoped to the provider's site description, not inferred from
    # a country's climate or the mere presence of a dam somewhere downstream.
    facts = [
        ("BLUE", "groundwater_supported_perennial", "Provider describes perennial flow supplied by the Arbuckle Simpson aquifer."),
        ("MCRA", "groundwater_dominated_with_possible_zero_flow", "Provider identifies groundwater as dominant; rare summer zero-flow days remain possible."),
        ("ARIK", "seasonal_disconnected_pools", "Summer flow can cease and leave standing pools."),
        ("KING", "intermittent_and_sometimes_dry", "Provider describes intermittent flow and annual low-flow or dry periods."),
        ("PRIN", "seasonal_disconnected_pools", "Provider describes summer drying into separate pools."),
        ("SYCA", "seasonal_channel_drying", "Provider describes sections that dry in spring and fall."),
        ("CARI", "seasonal_sensor_removal", "Aquatic instruments are removed in winter to prevent freeze damage."),
        ("OKSR", "seasonally_frozen_solid_lake_inputs", "Provider describes lake inputs and frozen-solid zero-discharge months."),
        ("HOPB", "reservoir_downstream_not_upstream_regulation_proof", "The monitored stream drains into Quabbin Reservoir; upstream thermal regulation is unverified."),
        ("MART", "former_dam_removed_2012", "A former dam was removed before NEON instrument operation; active regulation is not inferred."),
    ]
    OUT.mkdir(exist_ok=True, parents=True)
    pd.DataFrame(rows).to_csv(OUT / "metadata_overlap_and_scope.csv", index=False)
    process = pd.DataFrame(facts, columns=["site", "verified_context", "scope"])
    process["source_url"] = process.site.map(lambda s: "https://www.neonscience.org/field-sites/" + s.lower())
    process["hydrological_effect_on_H30_identified"] = False
    process.to_csv(OUT / "verified_process_context.csv", index=False)
    payload = {
        "status": "metadata_only_standalone_primary_source_infeasible_under_fixed_evidence_rule",
        "candidate_sites": len(sites), "domain_proxies": len({s["domainCode"] for s in sites}),
        "prior_USGS_record_identities_geolocated": len(old),
        "optimistic_independent_unit_upper_bound": len(sites),
        "risk_cap": cap, "formal_alpha_per_method": alpha,
        "necessary_ideal_groups_one_threshold": floor,
        "necessary_ideal_groups_21_thresholds": ideal_group_floor(cap, alpha, 21),
        "best_possible_bounded_loss_upper_using_all_sites_as_independent": bounded_mean_upper(0.0, len(sites), alpha=alpha),
        "optimistic_necessary_calibration_plus_test_units": 2 * floor,
        "group_floor_is_not_joint_power_or_recruitment_recommendation": True,
        "assumptions_for_floor": "zero group loss, full admission, one pre-fixed threshold; no multiplicity penalty and every station independent",
        "standalone_primary_joint_success_possible_under_fixed_rule": len(sites) >= 2 * floor,
        "upstream_or_alias_overlap_sites": [r["site"] for r in rows if r["prior_station_within_250m"] or r["prior_stations_within_NEON_upstream_watershed"]],
        "complete_downstream_independence_audit_finished": False,
        "temperature_measurement_tables_opened": False,
        "independent_confirmation_executed": False,
        "reference_eligible_station_years": None,
        "candidate_scored_or_selected_from_new_temperature_results": False,
        "next_action": "Seek a larger, independently recruited public reference resource; retain NEON measurements unopened for a pooled design or separate backup-reference work.",
    }
    C.write_json(OUT / "summary.json", payload)
    inputs = {"future_specification": SPEC, "selected_sites": RAW / "selected_site_metadata.json",
              "prior_header_membership": RAW / "old_header_station_inventory.csv",
              "prior_station_locations": RAW / "old_usgs_station_metadata.csv",
              "provider_watersheds": RAW / "NEONAquaticWatershed_1.zip",
              "transformed_watersheds": RAW / "neon_watersheds.geojson",
              "fixed_risk_implementation": C.ROOT / "src/stream_recoverability/experiments/v19_revision/risk.py"}
    for site, _, _ in facts:
        inputs[f"profile_{site}"] = RAW / "site_profiles" / f"{site}.html"
    C.write_json(OUT / "run_record.json", run_record(inputs,
                 shapefile_parser="pyshp 2.3.1; provider CRS WGS84", recruitment_uses_only_metadata=True,
                 no_model_threshold_or_primary_evidence_rule_changed=True))
    print(f"[399] {len(sites)} sites / {payload['domain_proxies']} domain proxies; ideal one-threshold floor {floor}; primary standalone source infeasible before temperature outcomes", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
