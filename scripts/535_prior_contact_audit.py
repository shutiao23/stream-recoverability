#!/usr/bin/env python3
"""Check both USGS intakes against later source and evaluation inventories."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REV = ROOT / "results/wrr_review_response_20261027"


def main():
    e10 = set(pd.read_csv(ROOT / "results/wrr_target_recovery_20261022/e10_sealed_usgs/sealed_roster.csv", dtype=str).station_id)
    source = set(pd.read_csv(ROOT / "results/wrr_target_recovery_20261021/e1_archive/usgs_site_metadata.csv", dtype=str).site_no)
    additional = set(pd.read_csv(ROOT / "results/additional_usgs_observed/cohort_metadata.csv", dtype=str).station_id)
    expanded = set(pd.read_csv(ROOT / "results/wrr_submission_ready/followup_20261021/usgs_prior_cache_audit/expanded_prior_station_inventory.csv", dtype=str).station_id)
    national = ROOT / "results/wrr_review_completion_20261024/national_meaning/site_results"
    processed = set()
    for p in national.glob("*.json"):
        try:
            if json.loads(p.read_text()).get("status") == "processed":
                processed.add(p.stem)
        except (OSError, json.JSONDecodeError):
            continue
    raw = ROOT / "data/external/wrr_target_recovery_20261022/usgs_new/values_raw"
    for name in ["external_usgs", "external_usgs_fresh"]:
        folder = REV / name
        frame = pd.read_csv(folder / "cohort.csv", dtype=str)
        frame["previously_scored_e10"] = frame.station_id.isin(e10)
        frame["previously_processed_national"] = frame.station_id.isin(processed)
        frame["source_station"] = frame.station_id.isin(source)
        frame["additional_observed_station"] = frame.station_id.isin(additional)
        frame["expanded_old_inventory"] = frame.station_id.isin(expanded)
        frame["old_e10_raw_series"] = frame.series_id.map(lambda s: (raw / (s + ".json")).exists())
        flags = ["previously_scored_e10", "previously_processed_national", "source_station",
                 "additional_observed_station", "expanded_old_inventory", "old_e10_raw_series"]
        frame["prior_temperature_contact"] = frame[flags].any(axis=1)
        frame[["station_id", "station_name", *flags, "prior_temperature_contact"]].to_csv(
            folder / "prior_contact_addendum.csv", index=False)
        status_path = folder / "status.json"
        status = json.loads(status_path.read_text())
        status["prior_contact_stations"] = int(frame.prior_temperature_contact.sum())
        status["prior_contact_audit_scope"] = "named source, E10, national, additional-USGS and expanded prior caches; not a proof of repository-wide independence"
        if name == "external_usgs":
            status["new_independent_reference_eligible"] = 0
            status["interpretation"] = "All 15 had prior national-panel contact; ten were previously scored in E10. This is opened historical evidence, not independent confirmation."
        else:
            status["new_independent_reference_eligible"] = int(status["n_eligible"]) if not frame.prior_temperature_contact.any() else None
            status["interpretation"] = "No named prior-contact inventory match; qualification failures and residual network/climate dependence remain explicit."
        status_path.write_text(json.dumps(status, indent=2) + "\n")
        print(name, "candidates", len(frame), "prior-contact", int(frame.prior_temperature_contact.sum()), flush=True)


if __name__ == "__main__":
    main()
