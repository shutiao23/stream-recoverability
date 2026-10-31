#!/usr/bin/env python3
"""Expand prior-record exclusions using ignored cache headers and request metadata."""
from __future__ import annotations

import csv
import importlib
import json
import re
import subprocess
from urllib.parse import parse_qs, urlsplit

import numpy as np
import pandas as pd

import wrr_r3_common as C

P = importlib.import_module("410_wrr_usgs_reference_preflight")
CONFIG = C.ROOT / "configs/wrr_usgs_prior_cache_audit_20261021.json"
OUT = P.OUT.parent / "usgs_prior_cache_audit"


def inspect_cache_identity(path, root):
    """Return identity evidence from schemas and requests, not temperatures."""
    relative = path.relative_to(root).as_posix()
    if relative.startswith("data/external/wrr_usgs_new_reference_20261021/"):
        return []
    evidence = []
    daily = re.search(r"(?:^|/)nwis/(\d{8,15})_\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}\.csv$", relative)
    if daily:
        with path.open(newline="") as handle:
            header = next(csv.reader(handle), [])
        if {"site_id", "date", "temperature_c", "qualifier"}.issubset(header):
            evidence.append((daily[1], "daily_temperature_cache_filename_and_schema", "T"))
        return evidence
    modern = re.search(r"/raw/usgs/daily/(\d{8,15})/([TFL])/[^/]+\.response\.json$", relative)
    if modern:
        evidence.append((modern[1], "saved_daily_water_response_path", modern[2]))
        return evidence
    native = re.fullmatch(r"usgs_(\d{8,15})_native_temperature\.rdb", path.name)
    if native and "wrr_public_backup" in relative:
        evidence.append((native[1], "saved_native_temperature_response_filename", "T"))
        return evidence
    if "usgs_legacy" in relative and path.name == "request.json":
        # Only the method and URL are consulted. Request headers, credentials
        # and measurement response fields are never emitted or used.
        request = json.loads(path.read_text())
        address = urlsplit(request.get("url", ""))
        if address.hostname not in {"waterservices.usgs.gov", "nwis.waterdata.usgs.gov"} or "/nwis/dv" not in address.path:
            return []
        if not (path.parent / "response.rdb").exists():
            return []
        query = parse_qs(address.query)
        parameters = {code for field in ("parameterCd", "parameterCode") for value in query.get(field, []) for code in value.split(",")}
        channel = "T" if "00010" in parameters else "F" if "00060" in parameters else "L" if "00065" in parameters else "unknown_water_channel"
        for field in ("sites", "siteNo"):
            for group in query.get(field, []):
                for number in group.split(","):
                    evidence.append((P.station_number(number), "saved_legacy_daily_request_and_response", channel))
    return evidence


def discover(root, settings):
    result = subprocess.run(["rg", "--files", "--no-ignore", *settings["scan_roots"]], cwd=root,
                            capture_output=True, text=True, check=True)
    rows, sources = [], {}
    for relative in sorted(result.stdout.splitlines()):
        if not any(token in relative.lower() for token in ("nwis", "usgs")):
            continue
        path = root / relative
        evidence = inspect_cache_identity(path, root)
        if not evidence:
            continue
        size = path.stat().st_size
        sources[relative] = {"path": relative, "bytes": size}
        for number, kind, channel in evidence:
            rows.append({"station_id": number, "source_path": relative, "source_bytes": size,
                         "evidence_kind": kind, "water_channel": channel,
                         "temperature_values_parsed": False, "outcome_tuning_proven": False})
    return pd.DataFrame(rows, columns=["station_id", "source_path", "source_bytes", "evidence_kind", "water_channel",
                                       "temperature_values_parsed", "outcome_tuning_proven"]), sources


def effective_scope(candidates, prior_numbers):
    """Append exclusions to the unchanged preflight; never reshuffle roles."""
    result = candidates.copy()
    result["expanded_prior_cache_contact"] = result.station_id.isin(prior_numbers)
    result["effective_metadata_candidate"] = ~result.expanded_prior_cache_contact
    result["effective_scope_status"] = np.where(result.expanded_prior_cache_contact,
         "exclude_prior_cached_water_record_from_new_confirmation", "pending_network_prior_pool_event_and_reference_qualification")
    result["new_role_assigned"] = False
    result["new_temperature_value_access_allowed"] = False
    result["new_prediction_errors_opened"] = False
    return result


def expanded_locations(old_locations, features, prior):
    """Concatenate by position so a deduplicated index cannot overwrite rows."""
    additions = []
    for feature in features:
        p, geometry = feature["properties"], feature.get("geometry") or {}
        number = str(p.get("monitoring_location_id", "")).removeprefix("USGS-")
        point = geometry.get("coordinates")
        if (p.get("agency_code") == "USGS" and number in prior and geometry.get("type") == "Point" and
                isinstance(point, list) and len(point) == 2 and np.isfinite(point).all()):
            additions.append({"site": number, "longitude": point[0], "latitude": point[1]})
    locations = pd.concat([old_locations, pd.DataFrame(additions, columns=["site", "longitude", "latitude"])], ignore_index=True)
    locations = locations.drop_duplicates(["site", "longitude", "latitude"]).reset_index(drop=True)
    if not set(old_locations.site).issubset(set(locations.site)):
        raise RuntimeError("An old source identity disappeared from the location inventory")
    return locations


def main():
    settings = json.loads(CONFIG.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    rows, sources = discover(C.ROOT, settings)
    initial, _, old_locations = P.prior_records()
    prior = initial | set(rows.station_id)
    candidates = pd.read_csv(P.OUT / "metadata_candidates.csv", dtype={"station_id": str})
    scope = effective_scope(candidates, prior)
    rows.to_csv(OUT / "cache_identity_occurrences.csv", index=False)
    scope.to_csv(OUT / "candidate_prior_cache_scope.csv", index=False)
    inventory = pd.DataFrame({"station_id": sorted(prior)})
    inventory["in_initial_inventory"] = inventory.station_id.isin(initial)
    inventory["additional_cache_identity"] = inventory.station_id.isin(set(rows.station_id) - initial)
    inventory.to_csv(OUT / "expanded_prior_station_inventory.csv", index=False)
    # Use location metadata only; this lookup neither opens temperatures nor
    # proves that differently named stations are distinct hydrologic units.
    combined = P.RAW / "combined_daily_mean_temperature_metadata.json"
    locations = expanded_locations(old_locations, json.loads(combined.read_text())["features"], prior)
    locations.to_csv(OUT / "expanded_prior_locations.csv", index=False)
    added = prior - initial
    summary = {"status": "prior_cache_exclusion_addendum_not_new_reference_or_confirmation",
               "initial_prior_station_numbers": len(initial), "expanded_prior_station_numbers": len(prior),
               "additional_prior_cached_station_numbers": len(added), "cache_source_files": len(sources),
               "cache_identity_occurrences": len(rows), "initial_metadata_candidates": len(candidates),
               "initial_candidates_with_prior_cache_contact": int(scope.expanded_prior_cache_contact.sum()),
               "remaining_effective_metadata_candidates": int(scope.effective_metadata_candidate.sum()),
               "expanded_prior_identities_without_current_location": len(prior - set(locations.site)),
               "temperature_values_parsed_or_used": False, "new_temperature_observations_requested": False,
               "outcome_based_tuning_inferred_from_cache_presence": False,
               "initial_preflight_and_network_plan_files_modified": False, "new_roles_assigned": False,
               "new_H30_prediction_errors_opened": False, "new_independent_confirmation_completed": False,
               "full_repository_prior_access_audit_complete": False,
               "unrecognized_formats_aliases_and_network_event_relations_remain_required": True}
    if len(scope) != len(candidates) or set(old_locations.site) - set(locations.site):
        raise RuntimeError("Original candidates or old location identities were lost")
    C.write_json(OUT / "summary.json", summary)
    print(f"[412] prior identities {len(initial)} -> {len(prior)}; {int(scope.expanded_prior_cache_contact.sum())} "
          f"preliminary candidates have old cache contact; {int(scope.effective_metadata_candidate.sum())} remain unqualified metadata candidates", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
