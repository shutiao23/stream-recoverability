#!/usr/bin/env python3
"""Distinguish unlocated requested identifiers from retained observation rows."""
from __future__ import annotations

import csv
import io
import json

import pandas as pd

import wrr_r3_common as C

BASE = C.READY / "followup_20261021"
OUT = BASE / "usgs_empty_cache_scope"


def cache_row_state(payload):
    reader = csv.reader(io.StringIO(payload.decode("utf-8-sig")))
    header = next(reader, None)
    expected = {"site_id", "date", "temperature_c", "qualifier"}
    if header is None or set(header) != expected or len(header) != len(expected):
        return "unverified_cache_schema", None
    # Inspect row presence only. Do not convert or emit any water value.
    rows = sum(1 for row in reader if row)
    return ("header_only_no_retained_observation_rows" if rows == 0 else "cache_contains_rows"), rows


def main():
    OUT.mkdir(exist_ok=True, parents=True)
    inventory_path = BASE / "usgs_prior_cache_audit/expanded_prior_station_inventory.csv"
    occurrences_path = BASE / "usgs_prior_cache_audit/cache_identity_occurrences.csv"
    locations_path = BASE / "usgs_intake_evidence/expanded_prior_locations.csv"
    inventory = pd.read_csv(inventory_path, dtype=str)
    occurrences = pd.read_csv(occurrences_path, dtype=str)
    locations = pd.read_csv(locations_path, dtype=str)
    unresolved = sorted(set(inventory.station_id) - set(locations.site))
    selected = occurrences.loc[occurrences.station_id.isin(unresolved)].copy()
    rows = []
    for row in selected.itertuples(index=False):
        path = C.ROOT / row.source_path
        if row.evidence_kind != "daily_temperature_cache_filename_and_schema":
            state, count = "other_evidence_requires_review", None
        else:
            state, count = cache_row_state(path.read_bytes())
        rows.append({"station_id": row.station_id, "source_path": row.source_path,
                     "bytes": path.stat().st_size,
                     "row_state": state, "retained_data_rows": count,
                     "temperature_values_numerically_parsed": False})
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "unlocated_identity_cache_rows.csv", index=False)
    identities = []
    for identifier in unresolved:
        item = frame.loc[frame.station_id.eq(identifier)] if not frame.empty else frame
        supported = bool(len(item) and item.row_state.eq("header_only_no_retained_observation_rows").all())
        identities.append({"station_id": identifier, "source_occurrences": len(item),
                           "all_retained_sources_are_header_only": supported,
                           "physical_station_location_resolved": False,
                           "conservative_prior_exclusion_removed": False})
    identity = pd.DataFrame(identities)
    identity.to_csv(OUT / "identity_scope.csv", index=False)
    C.write_json(OUT / "summary.json", {
        "status": "dated_retained_cache_row_presence_audit_not_a_new_reference_release",
        "unlocated_requested_identifiers": len(unresolved), "source_occurrences": len(frame),
        "identifiers_with_only_header_sources": int(identity.all_retained_sources_are_header_only.sum()),
        "sources_with_retained_rows": int(frame.row_state.eq("cache_contains_rows").sum()),
        "identifiers_with_other_or_missing_custody": int((~identity.all_retained_sources_are_header_only).sum()),
        "temperature_values_numerically_parsed": False,
        "does_not_prove_absence_of_observations_outside_retained_caches": True,
        "physical_locations_recovered": 0, "prior_inventory_or_roles_edited": False,
        "leading_zero_aliases_guessed": False, "new_temperature_or_prediction_errors_opened": False,
        "scope": "the unresolved identifiers remain conservative exclusions, but these retained sources contain no observation rows; request names are not observed independent records"})
    print(f"[420] {len(unresolved)} unlocated request identifiers; {int(identity.all_retained_sources_are_header_only.sum())} have only header-only retained sources; conservative exclusions unchanged", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
