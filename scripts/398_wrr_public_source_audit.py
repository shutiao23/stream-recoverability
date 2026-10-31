#!/usr/bin/env python3
"""Reproduce metadata staging and audit the no-login backup-source search."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import wrr_r3_common as C

RAW = C.ROOT / "data/external/wrr_public_backup_20261021"
NEON = C.ROOT / "data/external/wrr_neon_backup_20261021"
OUT = C.READY / "followup_20261021/public_backup_search"
CONFIGS = [C.ROOT / "configs/wrr_usgs_backup_20261021.json",
           C.ROOT / "configs/wrr_usgs_named_instruments_20261021.json"]


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def metadata():
    sources = {
        RAW / "usgs_national_instantaneous_temperature_metadata.json":
            "https://api.waterdata.usgs.gov/ogcapi/v0/collections/time-series-metadata/items?f=json&parameter_code=00010&computation_identifier=Instantaneous&limit=10000",
        RAW / "usgs_continuous_queryables.json":
            "https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/queryables?f=json",
        RAW / "usgs_timeseries_queryables.json":
            "https://api.waterdata.usgs.gov/ogcapi/v0/collections/time-series-metadata/queryables?f=json",
        RAW / "figshare_28074452_metadata.json": "https://api.figshare.com/v2/articles/28074452",
        RAW / "dryad_gtht76j16_metadata.json": "https://datadryad.org/api/v2/datasets/doi%3A10.5061%2Fdryad.gtht76j16",
        RAW / "dryad_gtht76j16_files.json": "https://datadryad.org/api/v2/versions/449434/files",
        RAW / "Boulder_SOP_2020.pdf": "https://watershed.center/wp-content/uploads/2023/08/2020_0908_WQ_Monitoring_SOP-002_COB.pdf",
    }
    sites = {item["site"] for config in CONFIGS for item in json.loads(config.read_text())["candidates"]}
    for site in sites | {"04092750", "15564880"}:
        sources[RAW / f"usgs_site_{site}_metadata.json"] = f"https://api.waterdata.usgs.gov/ogcapi/v0/collections/monitoring-locations/items/USGS-{site}?f=json"
    for product in ["DP1.20053.001", "DP1.20054.001", "DP1.20288.001"]:
        sources[NEON / f"{product}.json"] = f"https://data.neonscience.org/api/v0/products/{product}"
    sources[NEON / "sites.json"] = "https://data.neonscience.org/api/v0/sites"
    for path, url in sources.items():
        if not path.exists():
            response = requests.get(url, timeout=90)
            response.raise_for_status()
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_bytes(response.content)
    probe = NEON / "access_probe.json"
    if not probe.exists():
        url = "https://data.neonscience.org/api/v0/data/DP1.20053.001/ARIK/2020-01?package=basic&release=RELEASE-2026"
        response = requests.get(url, timeout=60)
        C.write_json(probe, {"url": url, "http_status": response.status_code,
                            "NEON_API_TOKEN_available": False,
                            "download_catalogue_acquired": response.ok, "token_recorded": False})
    C.write_json(OUT / "metadata_sources.json", {
        "sources": [{"url": url, "path": str(path.relative_to(C.ROOT))} for path, url in sources.items()],
        "access": "anonymous public metadata only; no account/token requested or used",
        "vintage": "Existing local snapshots retained. Fresh provider metadata form a new source vintage rather than overwriting existing snapshots."})
    print(f"[398] {len(sources)} public metadata snapshots staged", flush=True)


def audit():
    checks, inputs, frames, summaries = [], {}, [], []
    def check(name, passed):
        checks.append({"check": name, "passed": bool(passed)})
    candidates, native_bytes, native_files = [], 0, 0
    for index, config in enumerate(CONFIGS):
        folder = OUT if index == 0 else OUT / "named_instruments"
        settings = json.loads(config.read_text())
        inputs[f"configuration_{index}"] = config
        candidates.extend(settings["candidates"])
        quality = pd.read_csv(folder / "usgs_pair_year_qualification.csv", dtype={"site": str})
        channels = pd.read_csv(folder / "usgs_channel_quality.csv", dtype={"site": str})
        summary = json.loads((folder / "usgs_qualification_summary.json").read_text())
        summaries.append(summary)
        inputs[f"pair_quality_{index}"] = folder / "usgs_pair_year_qualification.csv"
        inputs[f"channel_quality_{index}"] = folder / "usgs_channel_quality.csv"
        inputs[f"metadata_selection_{index}"] = folder / "usgs_metadata_selection.json"
        inputs[f"acquisition_{index}"] = folder / "usgs_acquisition.json"
        check(f"all_prespecified_pair_years_retained_{index}", len(quality) == sum(len(item["candidate_years"]) for item in settings["candidates"]))
        check(f"no_pending_acquisitions_promoted_{index}", not quality.acquisition_pending.any())
        check(f"no_provisional_reference_promotion_{index}", not channels.provisional_values_accepted_as_reference.any())
        check(f"no_recovery_errors_used_in_resource_selection_{index}", not quality.temperature_reconstruction_errors_evaluated.any())
        check(f"no_unverified_hardware_claimed_independent_{index}", not quality.independently_verified_natural_gap_confirmation.any())
        expected = (quality.has_actual_primary_missing_days & quality.primary_annual_boundaries_observed &
                    quality.backup_covers_every_missing_primary_day &
                    (quality.approved_visible_overlap_days >= settings["reference_QC"]["minimum_visible_overlap_days"]) &
                    (quality.visible_pair_MAE_C <= settings["reference_QC"]["maximum_visible_daily_MAE_C"]) &
                    (quality.visible_pair_abs95_C <= settings["reference_QC"]["maximum_visible_daily_abs95_C"]) &
                    quality.has_three_complete_prior_primary_years)
        check(f"eligibility_recomputed_from_locked_conditions_{index}", np.array_equal(expected.to_numpy(), quality.record_reference_eligible.to_numpy()))
        original = json.loads((C.ROOT / "configs/wrr_natural_backup_20261021_v2.json").read_text())
        check(f"original_hour_coverage_and_sensor_consistency_rules_retained_{index}", all(settings[key] == original[key] for key in ["coverage", "reference_QC", "gross_water_temperature_range_C"]))
        acquisition = json.loads((folder / "usgs_acquisition.json").read_text())
        for row in acquisition["records"]:
            path = C.ROOT / row["path"]
            native_bytes += path.stat().st_size
            native_files += 1
        frames.append(quality)
    metadata_table = []
    national_path = RAW / "usgs_national_instantaneous_temperature_metadata.json"
    national = json.loads(national_path.read_text())
    channel_metadata = {item["properties"]["id"]: item["properties"] for item in national["features"]}
    for item in candidates:
        site_metadata = json.loads((RAW / f"usgs_site_{item['site']}_metadata.json").read_text())
        metadata_table.append({"site": item["site"], "site_metadata": site_metadata,
                               "primary": channel_metadata[item["primary_metadata_id"]],
                               "backup": channel_metadata[item["backup_metadata_id"]]})
    C.write_json(OUT / "selected_public_channel_metadata.json", {"sites": metadata_table,
                 "national_instantaneous_temperature_channels": len(national["features"]),
                 "site_or_channel_labels_do_not_prove_independent_hardware": True})
    coverage_path = C.READY / "major_revision_20261014/p0_06_coverage_recompute/final_coverage_table.csv"
    coverage = pd.read_csv(coverage_path, dtype=str)
    overlaps = coverage.loc[coverage.station_id.isin({item["site"] for item in candidates}),
                            ["network_id", "station_id", "split_role", "first_year", "last_year"]]
    overlaps.to_csv(OUT / "exact_station_overlap_with_opened_panel.csv", index=False)
    inputs["opened_panel_inventory"] = coverage_path
    neon_summary_path = OUT / "neon_public_archive_summary.json"
    neon = json.loads(neon_summary_path.read_text())
    check("public_NEON_measurement_tables_remain_unopened", not neon["temperature_measurement_payloads_opened"])
    check("public_NEON_primary_resource_not_claimed_as_backup_confirmation", not neon["independent_backup_reference_acquired"] and not neon["independent_new_confirmation_executed"])
    inputs["neon_archive_metadata_audit"] = neon_summary_path
    inputs["neon_anonymous_access_probe"] = NEON / "access_probe.json"
    inputs["Boulder_provider_SOP"] = RAW / "Boulder_SOP_2020.pdf"
    inputs["Dryad_file_metadata"] = RAW / "dryad_gtht76j16_files.json"
    inputs["Dryad_access_status"] = OUT / "dryad_access_status.json"
    ogc_path = OUT / "named_instruments/ogc_acquisition_05578100.json"
    ogc = json.loads(ogc_path.read_text())
    native = pd.read_csv(C.ROOT / ogc["composite_path"], sep="\t", comment="#", dtype=str).iloc[1:]
    check("all_OGC_native_observations_survive_serialization", len(native) == sum(item["rows"] for item in ogc["provider_pages"]))
    inputs["ogc_acquisition"] = ogc_path
    for script in range(394, 398):
        path = next((C.ROOT / "scripts").glob(f"{script}_*.py"))
        inputs[f"implementation_{script}"] = path
    frame = pd.concat(frames, ignore_index=True)
    frame.to_csv(OUT / "all_usgs_pair_year_qualification.csv", index=False)
    payload = {
        "USGS": {"metadata_channel_count": len(national["features"]), "selected_natural_stream_sites": native_files,
                 "candidate_pair_years": len(frame), "native_composite_bytes": native_bytes,
                 "record_reference_eligible_pair_years": int(frame.record_reference_eligible.sum()),
                 "independently_verified_natural_gap_confirmations": int(frame.independently_verified_natural_gap_confirmation.sum()),
                 "pending_candidate_pair_years": int(frame.acquisition_pending.sum()),
                 "exact_station_overlap_with_opened_panel": sorted(overlaps.station_id.unique()),
                 "catchment_and_region_event_independence_verified": False},
        "NEON": {"official_anonymous_data_http_status": json.loads((NEON / "access_probe.json").read_text())["http_status"],
                 "user_has_no_token": True, "public_author_archive_PRT_sites": next(item for item in neon["manifests"] if item["kind"] == "prt")["sites"],
                 "public_author_archive_backup_reference_acquired": False,
                 "underlying_eligible_pair_years": None, "new_confirmation_executed": False},
        "source_constraints": {"Boulder": "Provider SOP describes paired sensors; hourly master data available upon request. No paired native records acquired.",
                               "Dryad_10.5061_dryad.gtht76j16": "Metadata available; public download returned 403 and API download 401; file contents not acquired. Access failure is not a zero underlying record count."},
        "paid_information_acquisition_enabled": False, "independent_new_confirmation_completed": False,
        "full_goal_achieved": False, "checks_passed": sum(row["passed"] for row in checks), "checks_total": len(checks),
    }
    C.write_json(OUT / "summary.json", payload)
    note = (
        f"A further metadata-led search considered {native_files} USGS natural-stream sites and "
        f"{len(frame)} candidate temperature-channel pair-years. "
        f"{int(frame.record_reference_eligible.sum())} pair-years passed all "
        "prespecified reference requirements. Qualification retained the original daily support "
        "(at least twenty distinct hours spanning twenty hours), three completely observed "
        "prior primary years, observed primary annual boundaries, complete backup coverage of "
        "primary gaps, and visible-sensor agreement (at least ninety overlap days; absolute "
        "mean difference at most 0.25 degrees and 95th percentile at most 0.5 degrees). "
        "Only approved unflagged native observations entered the main reference. "
        "Provisional values and access failures retain separate status. "
        "For Mississippi River at Clinton, 2019 meets the gap-coverage and history conditions "
        "but fails sensor agreement; its 208 primary daily deficits are therefore not promoted "
        "to a reference experiment. All candidate outcomes and native-response records are retained "
        "under \\texttt{public\\_backup\\_search/}.\n\n"
        "Salt Creek legacy retrieval returned HTTP 503; the public replacement OGC API supplied "
        f"{sum(item['rows'] for item in ogc['provider_pages']):,} native observations on "
        f"{len(ogc['provider_pages'])} pages, with approval and qualifier strings preserved. "
        "DST offsets are handled explicitly. Distinct series identifiers do not themselves "
        "verify separate sensor hardware or an identical sampling position. Exact station "
        "identities 01193500 and 05578100 already occur in the opened panel, and catchment/event "
        "independence for the remaining sites is unverified. The search is a reference-eligibility "
        "audit, not an independent recovery test.\n\n"
        "A public CC-BY author archive also provides PRT metadata for twenty-four NEON stream "
        "sites. The inspected archive contains no digital surface-water thermistor subarchive, "
        "and its checked water-quality schema contains no measured temperature field. "
        "Only ZIP directories and bounded schema, location and issue metadata have been opened. "
        "The official monthly catalogue was not anonymously accessible at acquisition "
        "(HTTP 403); underlying eligible pairs remain unknown. No costly information-acquisition "
        "action is inferred from these free-source searches.\n")
    (C.ROOT / "paper/wrr/r7_public_backup_notes.tex").write_text(note)
    pd.DataFrame(checks).to_csv(OUT / "checks.csv", index=False)
    C.write_json(OUT / "run_record.json", run_record(inputs,
                 predictor_and_decision_thresholds_changed=False, no_cost_or_reference_truth_invented=True))
    if not all(row["passed"] for row in checks):
        raise RuntimeError("Public source audit failed")
    print(f"[398] {native_files} USGS sites / {len(frame)} candidate pair-years; {int(frame.record_reference_eligible.sum())} record-reference eligible; {len(checks)} source checks passed", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["metadata", "audit"])
    args = parser.parse_args()
    metadata() if args.action == "metadata" else audit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
