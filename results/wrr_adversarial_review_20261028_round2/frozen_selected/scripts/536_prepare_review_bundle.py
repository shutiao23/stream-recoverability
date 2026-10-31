#!/usr/bin/env python3
"""Create a local, explicitly incomplete source-and-summary review package.

The archive includes attributed CC BY author inputs but omits other third-party
daily records, trained weights and detailed case tables until rights are resolved.
It is a reviewable staging artifact, not an AGU-compliant public deposit.
"""
from __future__ import annotations
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "dist/wrr_review_response_candidate.zip"
REV = ROOT / "results/wrr_review_response_20261027"


def write_review_archive(destination, files, readme, inventory, root=ROOT):
    """Keep an existing candidate intact if any required file cannot be read."""
    destination = Path(destination)
    files = sorted(files)
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        raise RuntimeError("Required package files missing: " + ", ".join(missing))
    members = [(path, path.relative_to(root).as_posix()) for path in files]
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + destination.name + ".", suffix=".tmp", dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.writestr("REVIEW_PACKAGE_README.txt", readme)
            z.writestr("dependency_inventory.json", json.dumps({"created_utc":datetime.now(timezone.utc).isoformat(),
                        "status":"incomplete_local_staging_only", "inputs":inventory}, indent=2) + "\n")
            for path, member in members:
                z.write(path, member)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(output=None):
    destination = Path(output) if output is not None else DEST
    files = set()
    for folder, suffixes in [("scripts", {".py"}), ("src", {".py"}), ("tests", {".py"}),
                             ("configs", {".json", ".yaml", ".yml"}),
                             ("paper/wrr_tr", {".tex", ".bib", ".pdf", ".dot", ".drawio", ".txt"}),
                             ("paper/wrr/template", {".tex", ".cls", ".sty", ".pdf", ".md"})]:
        files.update(p for p in (ROOT / folder).rglob("*") if p.is_file() and p.suffix in suffixes
                     and "__pycache__" not in p.parts)
    for name in ["README.md", "LICENSE", "CITATION.cff", "DATA_RIGHTS.md", "Makefile",
                 "pyproject.toml", "environment.yml", "constraints.txt", "requirements-wrr-review-replay.txt", "requirements-wrr-partial-history-replay.txt"]:
        path = ROOT / name
        if path.exists():
            files.add(path)
    files.add(ROOT / "docs/reviews/wrr_review_response_20261027/EXTERNAL_REFERENCE_LEADS_ZH.md")
    files.add(ROOT / "docs/reviews/wrr_review_response_20261027/LOCAL_CASE_AUDIT_ZH.md")
    files.add(ROOT / "docs/reviews/wrr_followup_20261021/NEW_REFERENCE_RECRUITMENT_ZH.md")
    files.add(ROOT / "docs/reviews/wrr_review_response_20261027/ADVERSARIAL_REVIEW_ZH.md")
    files.add(ROOT / "docs/reviews/wrr_review_response_20261027/USGS_LOCAL_REPLAY_ZH.md")
    files.add(ROOT / "docs/reviews/wrr_review_response_20261027/EDITORIAL_REORGANIZATION_ZH.md")
    files.add(ROOT / "docs/reviews/wrr_review_response_20261027/RESPONSE_TO_TASKBOOK_20261027_ZH.md")
    files.add(ROOT / "metadata/submission_author_metadata.json")
    files.add(ROOT / "metadata/data_rights.csv")
    files.add(REV / "audit/si_format_audit_20261027.json")
    reservoir = ROOT / "data/external/wrr_usace_reservoir_20261027"
    reservoir_manifest = reservoir / "manifest.json"
    files.update([reservoir_manifest, reservoir / "ATTRIBUTION.txt"])
    for item in json.loads(reservoir_manifest.read_text())["records"]:
        path = (reservoir / item["file"]).resolve()
        files.add(path)
    reservoir_results = REV / "external_usace_reservoir"
    files.update(reservoir_results.glob("*.json"))
    files.add(reservoir_results / "finite_reference_years.csv")
    files.add(REV / "audit/usace_open_reference_replay.json")
    for filename in ["finite_daily.parquet", "partial_year_h30_bounds.csv", "partial_year_record_screen.csv"]:
        path = reservoir / filename
        if not path.is_file():
            raise RuntimeError("Reservoir derived reference changed: " + filename)
        files.add(path)
    files.add(reservoir / "DERIVED_ATTRIBUTION.txt")
    files.add(REV / "audit/usace_bounds_open_replay.json")
    roster = reservoir / "partial_history_roster.csv"
    plan = json.loads((reservoir_results / "partial_history_evaluation_plan.json").read_text())
    files.add(roster)
    power = reservoir / "partial_history_power"
    power_manifest = power / "manifest.json"
    power_data = json.loads(power_manifest.read_text())
    files.update([power_manifest, power / "ATTRIBUTION.txt"])
    for item in power_data["records"]:
        path = (power / item["file"]).resolve()
        files.add(path)
    path = power / power_data["daily_file"]
    files.add(path)
    for name in ["partial_history_score_summary.csv", "partial_history_score_pairs.csv", "partial_history_site_sensitivity.csv", "partial_history_network_sensitivity.csv",
                 "partial_history_feature_support_summary.csv", "partial_history_clipping_summary.csv", "partial_history_clipping_leaf_audit.csv"]:
        files.add(reservoir_results / name)
    files.add(REV / "audit/usace_partial_power_open_replay.json")
    files.add(ROOT / "results/wrr_review_completion_20261024/independent_study/source_case_settings.json")
    factorial = REV / "source_partial_history_factorial"
    factorial_plan = json.loads((factorial / "plan.json").read_text())
    files.update(factorial.glob("*.json"))
    for name in ["roster.csv", "air_snapshot.parquet", "air_availability.csv"]:
        path = factorial / name
        files.add(path)
    for name in ["score_summary.csv", "paired_effects.csv", "group_effects.csv", "AIR_ATTRIBUTION.txt"]:
        files.add(factorial / name)
    files.add(REV / "audit/source_partial_history_open_reference_replay.json")
    usgs_partial = ROOT / "data/external/wrr_usgs_partial_daily_20261027"
    usgs_manifest = json.loads((usgs_partial / "manifest.json").read_text())
    files.add(usgs_partial / "manifest.json")
    for item in usgs_manifest["files"]:
        candidate = (usgs_partial / item["path"]).resolve()
        files.add(candidate)
    usgs_results = REV / "external_usgs_partial_daily"
    files.update(usgs_results.glob("*.json"))
    files.update(usgs_results.glob("*.csv"))
    files.add(ROOT / "docs/reviews/wrr_review_response_20261027/USGS_EXPLORATORY_REPORT_ZH.md")
    warning = REV / "source_ood_release"
    warning_status = json.loads((warning / "status.json").read_text())
    margin_status = json.loads((warning / "margin_sensitivity_status.json").read_text())
    if json.loads((warning / "independent_audit.json").read_text())["status"] != "passed" or json.loads((warning / "margin_sensitivity_independent_audit.json").read_text())["status"] != "passed":
        raise RuntimeError("Source support-warning audits incomplete")
    for name in ["policy_summary.csv", "margin_sensitivity.csv"]:
        path = warning / name
        files.add(path)
    files.update(warning.glob("*.json"))
    # The Truckee source and derived reference are public; model weights and
    # per-case predictions remain outside this local candidate.
    truckee = ROOT / "data/external/wrr_truckee_dwr_20261027"
    manifest = truckee / "manifest.json"
    files.update([manifest, truckee / "ATTRIBUTION.txt"])
    for item in json.loads(manifest.read_text())["files"]:
        path = (truckee / item["file"]).resolve()
        files.add(path)
    hourly = truckee / "power_time_standards"
    hourly_manifest = hourly / "manifest.json"
    files.update([hourly_manifest, hourly / "ATTRIBUTION.txt"])
    for item in json.loads(hourly_manifest.read_text())["records"]:
        path = (hourly / item["file"]).resolve()
        files.add(path)
    field = truckee / "wqp_field_snapshot"
    field_manifest = field / "manifest.json"
    files.update([field_manifest, field / "ATTRIBUTION.txt"])
    field_meta = json.loads(field_manifest.read_text())
    for key in ["field_results", "station_metadata"]:
        item = field_meta[key]
        path = (field / item["file"]).resolve()
        files.add(path)
    editorial_archive = ROOT / "docs/reviews/wrr_review_response_20261027/editorial_archive_20261027"
    for name in ["README.md", "review_completion_article.tex", "review_completion_article.pdf",
                 "review_completion_supporting.tex", "review_completion_supporting.pdf"]:
        files.add(editorial_archive / name)
    files.add(ROOT / "paper/wrr_tr/figures/architecture/README.md")
    # Include only the frozen USGS observation evidence and its public-source snapshot.
    usgs_manifest = REV / "audit/usgs_observed_snapshot_manifest.json"
    files.add(usgs_manifest)
    for item in json.loads(usgs_manifest.read_text())["files"]:
        path = (ROOT / item["path"]).resolve()
        files.add(path)
    files.add(REV / "audit/usgs_observed_reproduction.json")
    # Include only licensed, processed station data in the open witness subset.
    open_observed = REV / "open_observed_record_snapshot"
    open_manifest = open_observed / "manifest.json"
    files.add(open_manifest)
    for item in json.loads(open_manifest.read_text())["files"]:
        path = (open_observed / item["path"]).resolve()
        files.add(path)
    files.add(REV / "audit/open_observed_reproduction.json")
    files.add(ROOT / "data/external/wrr_nechako_nhg_20261026/01_Data.zip")
    files.add(ROOT / "data/external/wrr_nechako_nhg_20261026/ATTRIBUTION.txt")
    files.add(ROOT / "data/external/wrr_poudre_ross_20261026/ATTRIBUTION.txt")
    for year in range(2020, 2025):
        files.add(ROOT / f"data/external/wrr_poudre_ross_20261026/CSU_ROSS_{year}_raw.parquet")
    files.add(ROOT / "data/external/wrr_nova_scotia_open_20261026/ATTRIBUTION.txt")
    files.add(ROOT / "data/external/wrr_nova_scotia_open_20261026/exploratory_selected_reported_daily.parquet")
    files.add(ROOT / "data/external/wrr_nova_scotia_open_20261026/clock_sensitivity_reported_daily.parquet")
    ns_exp=REV / "external_nova_scotia_exploratory"
    ns_clock=REV / "external_nova_scotia_clock_sensitivity"
    files.add(ns_exp / "air_forcing.parquet")
    files.add(ns_exp / "weather/ATTRIBUTION.txt")
    for site in ['NS01DL0009','NS01FB0001']:
        files.add(ns_exp / "panels" / f"{site}.csv")
        files.add(ns_exp / "weather" / f"{site}.json.gz")
        files.add(ns_exp / "weather" / f"{site}.request.json")
        for shift in [-1,0,1]:
            files.add(ns_clock / "panels" / f"shift_{shift:+d}" / f"{site}.csv")
    portal=json.loads((REV / "external_nova_scotia_verified/portal_acquisition.json").read_text())
    portal_root=(ROOT / "data/external/wrr_nova_scotia_open_20261026").resolve()
    for page in portal['pages']:
        path=(ROOT / page['file']).resolve()
        if not path.is_relative_to(portal_root) or not path.is_file():raise RuntimeError('Invalid or missing Nova Scotia portal page')
        files.add(path)
    for figure_name in ["02_annual_comparators", "03_archive_factorial", "04_joint_uncertainty", "05_output_boundaries"]:
        files.add(ROOT / "paper/wrr_tr/figures/simple_research" / (figure_name + ".png"))
    # The supporting manuscript references this figure outside paper/wrr_tr.
    files.add(ROOT / "results/wrr_review_completion_20261024/failure_map/failure_map.pdf")
    summaries = [
        "groupmax_annual_calibration/plan.json", "groupmax_annual_calibration/source_support.csv",
        "groupmax_annual_calibration/source_freeze.json", "groupmax_annual_calibration/summary_correction.json",
        "groupmax_annual_calibration/source_repair_dependency.json", "groupmax_annual_calibration/source_repair_effect.csv",
        "groupmax_annual_calibration/before_correction_summary.csv", "groupmax_annual_calibration/before_correction_leave_region_out.csv",
        "groupmax_annual_calibration/before_correction_status.json", "groupmax_annual_calibration/summary.csv",
        "groupmax_annual_calibration/leave_region_out.csv", "groupmax_annual_calibration/status.json",
        "groupmax_annual_calibration/independent_audit.json", "groupmax_annual_calibration/trend_plan.json",
        "groupmax_annual_calibration/trend_execution.json", "groupmax_annual_calibration/trend_summary.csv",
        "groupmax_annual_calibration/trend_paired_contrasts.csv", "groupmax_annual_calibration/trend_leave_region_out.csv",
        "groupmax_annual_calibration/trend_empirical_overlap.csv", "groupmax_annual_calibration/trend_independent_audit.json",
        "past_season_screening/plan.json", "past_season_screening/multirule_correction.json",
        "past_season_screening/station_year_decisions.csv", "past_season_screening/witness_decisions.csv",
        "past_season_screening/summary.csv", "past_season_screening/transitions.csv", "past_season_screening/status.json",
        "past_season_screening/independent_audit.json", "audit/past_season_snapshot_reproduction.json",
        "summer_window_comparison/plan.json", "summer_window_comparison/station_groups.csv",
        "summer_window_comparison/summary.json", "summer_window_comparison/complete_year_windows.csv",
        "summer_window_comparison/station_mean_gaps.csv", "summer_window_comparison/witness_comparison.csv",
        "summer_window_comparison/screening_counts.csv", "summer_window_comparison/provider_summary.csv",
        "summer_window_comparison/independent_audit.json", "summer_window_comparison/influence_plan.json",
        "summer_window_comparison/station_regulation_labels.csv", "summer_window_comparison/influence_summary.csv",
        "summer_window_comparison/selected_station_peak_windows.csv", "summer_window_comparison/influence_status.json",
        "summer_window_comparison/influence_independent_audit.json", "audit/summer_snapshot_reproduction.json",
        "beaufort_proxy/plan.json", "beaufort_proxy/roster.csv", "beaufort_proxy/air_snapshot.parquet",
        "beaufort_proxy/air_availability.csv", "beaufort_proxy/AIR_ATTRIBUTION.txt", "beaufort_proxy/air_snapshot_status.json",
        "beaufort_proxy/summary.csv", "beaufort_proxy/leave_provider_out.csv", "beaufort_proxy/status.json",
        "beaufort_proxy/independent_audit.json", "beaufort_proxy/power_vintage_plan.json",
        "beaufort_proxy/power_vintage_summary.csv", "beaufort_proxy/power_vintage_status.json", "beaufort_proxy/power_vintage_independent_audit.json",
        "summer_proxy_archive/plan.json", "summer_proxy_archive/analysis_plan.json", "summer_proxy_archive/pilot.json",
        "summer_proxy_archive/execution.json", "summer_proxy_archive/status.json", "summer_proxy_archive/independent_audit.json",
        "summer_proxy_archive/annual_paired_summary.csv", "summer_proxy_archive/trend_paired_summary.csv",
        "summer_proxy_archive/proxy_support_summary.csv", "summer_proxy_archive/leave_region_out.csv",
        "external_camelsh_hourly/plan.json", "external_camelsh_hourly/record_metadata.json", "external_camelsh_hourly/archive_members.csv",
        "external_camelsh_hourly/index_status.json", "external_camelsh_hourly/contact_plan.json", "external_camelsh_hourly/contact_status.json",
        "external_camelsh_hourly/metadata_plan.json", "external_camelsh_hourly/metadata_status.json", "external_camelsh_hourly/count_plan.json",
        "external_camelsh_hourly/count_status.json", "external_camelsh_hourly/unlisted_metadata_plan.json", "external_camelsh_hourly/unlisted_metadata_acquisition.json",
        "external_camelsh_hourly/current_screen_plan.json", "external_camelsh_hourly/current_metadata_status.json",
        "external_truckee_dwr/plan.json", "external_truckee_dwr/metadata_status.json", "external_truckee_dwr/entity_metadata.json",
        "external_truckee_dwr/station_metadata_plan.json", "external_truckee_dwr/station_metadata_access_amendment.json",
        "external_truckee_dwr/station_metadata_status.json", "external_truckee_dwr/prior_proximity_plan.json", "external_truckee_dwr/prior_proximity_status.json",
        "external_truckee_dwr/time_upper_bound_plan.json", "external_truckee_dwr/time_acquisition.json", "external_truckee_dwr/time_upper_bound_status.json",
        "external_truckee_dwr/time_upper_bound_independent_audit.json", "external_truckee_dwr/finite_reference_plan.json", "external_truckee_dwr/finite_reference_status.json",
        "external_truckee_dwr/finite_reference_independent_audit.json", "external_truckee_dwr/exploratory_score_plan.json", "external_truckee_dwr/exploratory_run_plan.json",
        "external_truckee_dwr/exploratory_forcing_status.json", "external_truckee_dwr/exploratory_score_status.json", "external_truckee_dwr/exploratory_score_summary.csv",
        "external_truckee_dwr/exploratory_paired_summary.csv", "external_truckee_dwr/exploratory_score_independent_audit.json", "external_truckee_dwr/exploratory_hidden_probe.json",
        "audit/truckee_open_reference_replay.json",
        "external_truckee_dwr/peak_visibility_plan.json", "external_truckee_dwr/peak_visibility_status.json", "external_truckee_dwr/peak_visibility_summary.csv",
        "external_truckee_dwr/peak_visibility_independent_audit.json", "external_truckee_dwr/power_time_standards_plan.json", "external_truckee_dwr/power_time_acquisition.json",
        "external_truckee_dwr/power_time_comparison.json", "external_truckee_dwr/power_time_independent_audit.json", "audit/truckee_power_time_open_replay.json",
        "external_truckee_dwr/wqp_site_search_plan.json", "external_truckee_dwr/wqp_site_search_status.json",
        "external_truckee_dwr/wqp_same_site_plan.json", "external_truckee_dwr/wqp_same_site_acquisition.json",
        "external_truckee_dwr/wqp_field_comparison_plan.json", "external_truckee_dwr/wqp_field_comparison.csv",
        "external_truckee_dwr/wqp_field_comparison_status.json", "external_truckee_dwr/wqp_time_strata_plan.json",
        "external_truckee_dwr/wqp_time_strata_summary.csv", "external_truckee_dwr/wqp_field_independent_audit.json", "audit/truckee_wqp_open_replay.json",
        "open_source_sensitivity/donor_provenance_plan.json", "open_source_sensitivity/donor_provenance_status.json",
        "open_source_sensitivity/donor_provenance_panels.csv", "open_source_sensitivity/donor_provenance_cases.csv",
        "open_source_sensitivity/donor_provenance_roles.csv", "open_source_sensitivity/donor_provenance_independent_audit.json",
        "open_source_sensitivity/donor_usgs_metadata_plan.json", "open_source_sensitivity/donor_usgs_metadata_status.json",
        "open_source_sensitivity/donor_metadata_independent_audit.json",
        "open_source_sensitivity/donor_usgs_snapshot/request_manifest.json", "open_source_sensitivity/donor_usgs_snapshot/ATTRIBUTION.txt",
        "open_source_sensitivity/donor_usgs_snapshot/batch_01.rdb", "open_source_sensitivity/donor_usgs_snapshot/batch_02.rdb",
        "open_source_sensitivity/donor_usgs_daily_plan.json", "open_source_sensitivity/donor_usgs_daily_acquisition.json",
        "open_source_sensitivity/donor_usgs_daily_comparison.json", "open_source_sensitivity/donor_usgs_daily_independent_audit.json",
        "open_source_sensitivity/donor_usgs_ambiguous_plan.json", "open_source_sensitivity/donor_usgs_ambiguous_summary.json",
        "open_source_sensitivity/donor_usgs_ambiguous_independent_audit.json",
        "open_source_sensitivity/donor_usgs_daily_snapshot/request_manifest.json", "open_source_sensitivity/donor_usgs_daily_snapshot/ATTRIBUTION.txt",
        "open_source_sensitivity/donor_usgs_daily_snapshot/batch_01.json.gz", "open_source_sensitivity/donor_usgs_daily_snapshot/batch_02.json.gz",
        "open_source_sensitivity/donor_usgs_daily_snapshot/batch_03.json.gz", "open_source_sensitivity/donor_usgs_daily_snapshot/batch_04.json.gz",
        "open_source_sensitivity/donor_usgs_daily_snapshot/batch_05.json.gz", "open_source_sensitivity/donor_usgs_daily_snapshot/batch_06.json.gz",
        "open_source_sensitivity/donor_usgs_daily_snapshot/batch_07.json.gz",
        "projected_risk_sensitivity/plan.json", "projected_risk_sensitivity/source_support.csv",
        "projected_risk_sensitivity/source_cutoffs.csv", "projected_risk_sensitivity/source_freeze.json",
        "projected_risk_sensitivity/reference_score_amendment.json", "projected_risk_sensitivity/reference_score_status.json",
        "projected_risk_sensitivity/unscored_summary.csv", "projected_risk_sensitivity/unscored_leave_region_out.csv",
        "projected_risk_sensitivity/unscored_status.json", "projected_risk_sensitivity/summary.csv",
        "projected_risk_sensitivity/leave_region_out.csv", "projected_risk_sensitivity/status.json",
        "projected_risk_sensitivity/independent_audit.json",
        "expanded_stress_source_sensitivity/plan.json", "expanded_stress_source_sensitivity/pilot.json",
        "expanded_stress_source_sensitivity/execution.json", "expanded_stress_source_sensitivity/summary_correction.json",
        "expanded_stress_source_sensitivity/six_way_summary.csv", "expanded_stress_source_sensitivity/leave_one_region_out.csv",
        "expanded_stress_source_sensitivity/status.json", "expanded_stress_source_sensitivity/independent_audit.json",
        "expanded_stress_source_sensitivity/baseline_audit.json",
        "expanded_stress/plan.json", "expanded_stress/plan_clarification.json",
        "expanded_stress/mask_summary.csv", "expanded_stress/paired_summary.csv",
        "expanded_stress/leave_one_region_out.csv", "expanded_stress/status.json", "expanded_stress/independent_audit.json",
        "heat_gap_matched/plan.json", "heat_gap_matched/plan_clarification.json", "heat_gap_matched/mask_summary.json",
        "heat_gap_matched/paired_summary.csv", "heat_gap_matched/leave_region_out.csv", "heat_gap_matched/status.json",
        "heat_gap_matched/independent_audit.json", "heat_gap_matched/threeway_summary.csv", "heat_gap_matched/threeway_contrasts.csv",
        "heat_gap_matched/threeway_status.json", "heat_gap_matched/threeway_independent_audit.json",
        "heat_gap_source_sensitivity/plan.json", "heat_gap_source_sensitivity/pilot.json",
        "heat_gap_source_sensitivity/execution.json", "heat_gap_source_sensitivity/execution_note.json",
        "heat_gap_source_sensitivity/six_way_summary.csv", "heat_gap_source_sensitivity/leave_region_out.csv",
        "heat_gap_source_sensitivity/status.json", "heat_gap_source_sensitivity/independent_audit.json",
        "heat_gap_source_sensitivity/source_interactions.csv", "heat_gap_source_sensitivity/source_interactions_status.json",
        "heat_gap_source_sensitivity/source_interactions_independent_audit.json",
        "heat_gap_source_sensitivity/source_interactions_pre_correction.csv", "heat_gap_source_sensitivity/source_interactions_correction.json",
        "heat_gap_source_sensitivity/source_interaction_influence_summary.csv", "heat_gap_source_sensitivity/source_interaction_influence_status.json",
        "heat_gap_source_sensitivity/source_interaction_influence_independent_audit.json",
        "archive_matched_release_trend/plan.json", "archive_matched_release_trend/empty_input_amendment.json",
        "archive_matched_release_trend/summary.csv", "archive_matched_release_trend/group_summary.csv",
        "archive_matched_release_trend/status.json", "archive_matched_release_trend/independent_audit.json",
        "archive_matched_release_trend/independent_likelihood_audit.json",
        "external_nz_quality_bounds/plan.json", "external_nz_quality_bounds/performance_amendment.json",
        "external_nz_quality_bounds/site_counts.csv", "external_nz_quality_bounds/year_counts.csv",
        "external_nz_quality_bounds/summary.json", "external_nz_quality_bounds/independent_count_audit.json",
        "audit/australia_prior_exposure_by_role.csv", "audit/australia_prior_exposure_status.json", "audit/australia_prior_exposure_independent.json",
        "audit/archive_restricted_source_roles.csv", "audit/archive_restricted_source_roles.json",
        "audit/clean_lock_model_environment.json", "audit/replay_model_environment.json",
        "audit/annual_bridge_repair_dependency.json", "audit/annual_bridge_repair_effect.csv",
        "open_source_sensitivity/archive_bridge_repair_dependency.json", "open_source_sensitivity/archive_bridge_repair_effect.csv",
        "open_source_sensitivity/plan.json", "open_source_sensitivity/pilot_status.json",
        "open_source_sensitivity/candidate_input_integrity.json", "open_source_sensitivity/candidate_source_role_audit.json",
        "open_source_sensitivity/candidate_source_role_audit.csv", "open_source_sensitivity/archive_summary_status.json",
        "open_source_sensitivity/archive_four_way_comparison.csv", "open_source_sensitivity/archive_factorial_paired.csv",
        "open_source_sensitivity/archive_paired_summary.csv", "open_source_sensitivity/independent_summary_audit.json",
        "open_source_sensitivity/report.json",
        "open_source_sensitivity/annual_sensitivity_plan.json", "open_source_sensitivity/annual_sensitivity_status.json",
        "open_source_sensitivity/annual_sensitivity_scores.csv", "open_source_sensitivity/annual_sensitivity_paired.csv",
        "open_source_sensitivity/annual_sensitivity_cohorts.csv", "open_source_sensitivity/annual_sensitivity_leave_region_out.csv",
        "open_source_sensitivity/annual_sensitivity_independent_audit.json", "open_source_sensitivity/annual_sensitivity_report.json",
        "open_source_sensitivity/single_year_calibration_plan.json", "open_source_sensitivity/single_year_source_freeze.json",
        "open_source_sensitivity/single_year_source_support.csv", "open_source_sensitivity/single_year_calibration_status.json",
        "open_source_sensitivity/single_year_target_summary.csv", "open_source_sensitivity/single_year_independent_audit.json",
        "open_source_sensitivity/single_year_support_alignment.json", "open_source_sensitivity/single_year_group_sensitivity.csv",
        "open_source_sensitivity/single_year_leave_region_out.csv", "open_source_sensitivity/single_year_calibration_report.json",
        "open_source_sensitivity/single_year_trend_plan.json", "open_source_sensitivity/single_year_trend_plan_amendment.json",
        "open_source_sensitivity/single_year_trend_pilot.json", "open_source_sensitivity/single_year_trend_execution.json",
        "open_source_sensitivity/single_year_trend_summary.csv", "open_source_sensitivity/single_year_trend_paired_contrasts.csv",
        "open_source_sensitivity/single_year_trend_leave_region_out.csv", "open_source_sensitivity/single_year_trend_independent_audit.json",
        "open_source_sensitivity/single_year_trend_report.json",
        "audit/region_holdout_role_audit.csv", "audit/region_holdout_role_status.json", "audit/region_holdout_role_report.json",
        "strict_region_holdout/plan.json", "strict_region_holdout/refit_summary.csv", "strict_region_holdout/refit_status.json",
        "strict_region_holdout/future_release_comparison.csv", "strict_region_holdout/future_gate_limits.csv", "strict_region_holdout/future_state_transitions.csv", "strict_region_holdout/future_comparison_status.json",
        "strict_region_holdout/robustness_paired_bootstrap.csv", "strict_region_holdout/robustness_leave_one_region_out.csv", "strict_region_holdout/robustness_status.json",
        "strict_region_holdout/archive_prediction_replay_status.json",
        "strict_region_holdout/scenario_paired_sensitivity.csv", "strict_region_holdout/scenario_sensitivity_status.json",
        "strict_region_holdout/uncertainty_common_paired_sensitivity.csv", "strict_region_holdout/uncertainty_strict_contrasts.csv", "strict_region_holdout/uncertainty_sensitivity_status.json",
        "strict_region_holdout/integrated_paired_summary.csv", "strict_region_holdout/integrated_state_transitions.csv", "strict_region_holdout/integrated_release_status.json",
        "strict_region_holdout/annual_paired_diagnostics.csv", "strict_region_holdout/annual_diagnostics_status.json",
        "strict_region_holdout/all_source_role_effects.csv", "strict_region_holdout/all_source_role_effects_status.json",
        "strict_region_holdout/future_matched_retention.csv", "strict_region_holdout/future_matched_retention_status.json",
        "strict_region_holdout/calibration_source_upper_bound.csv", "strict_region_holdout/calibration_source_upper_bound_status.json",
        "strict_region_holdout/archive_affected_paired.csv", "strict_region_holdout/archive_sensitivity_status.json", "strict_region_holdout/archive_pooled_paired.csv", "strict_region_holdout/archive_estimator_four_way_paired.csv", "strict_region_holdout/archive_factorial_paired.csv", "strict_region_holdout/archive_pooled_status.json",
        "annual/source_scorecard_summary.csv", "annual/source_paired.csv",
        "annual/single_year_coverage_numeric_plan.json", "annual/single_year_coverage_numeric_seeds.csv", "annual/single_year_coverage_numeric_summary.csv", "annual/single_year_coverage_numeric_status.json", "annual/single_year_coverage_scalar_audit.json",
        "whole_archive/status.json", "whole_archive/annual_summary.csv", "whole_archive/trend_summary.csv",
        "whole_archive/factorial_paired_summary.csv", "whole_archive/paired_trend_estimators.csv",
        "whole_archive/task_calibration_summary.csv", "whole_archive/task_calibration_sources.csv",
        "whole_archive/paired_task_intervals.csv", "whole_archive/quantile_tail_summary.csv",
        "whole_archive/uncertainty_paired_summary.csv", "whole_archive/uncertainty_paired_contrasts.csv",
        "whole_archive/uncertainty_cohort_availability.csv", "whole_archive/uncertainty_paired_design.json",
        "whole_archive/support_projection_summary.csv", "whole_archive/support_projection_status.json", "whole_archive/support_projection_report.json",
        "whole_archive/projection_stage_summary.csv", "whole_archive/projection_stage_status.json",
        "whole_archive/peak_visibility_annual.csv", "whole_archive/peak_visibility_paired.csv",
        "whole_archive/peak_visibility_cohorts.csv", "whole_archive/peak_visibility_status.json", "whole_archive/peak_visibility_report.json",
        "whole_archive/main_coverage_numeric_corrected_summary.csv", "whole_archive/main_coverage_numeric_corrected_status.json", "whole_archive/main_coverage_numeric_scalar_audit.json", "whole_archive/main_coverage_numeric_correction.txt", "whole_archive/main_coverage_numeric_plan.json", "whole_archive/main_coverage_numeric_corrected_plan.json",
        "annual_interval_expansion/source_support.csv", "annual_interval_expansion/paired_summary.csv",
        "annual_interval_expansion/status.json", "annual_interval_expansion/report.json",
        "rules/rule_summary.csv", "rules/measurement_margin_sensitivity.csv", "rules/design.json",
        "robustness/region_roster.csv", "robustness/paired_cluster_bootstrap.csv", "robustness/leave_one_region_out.csv",
        "release_outputs/release_metrics.csv", "release_outputs/output_states.csv", "release_outputs/hot_event_metrics.csv",
        "release_outputs/matched_numerical_retention.csv", "release_outputs/matched_retention_design.json", "release_outputs/matched_retention_status.json",
        "release_outputs/source_calibrated_release_summary.csv", "release_outputs/source_rule_thresholds.csv",
        "release_outputs/source_calibrated_release_design.json", "release_outputs/source_calibrated_audit.json", "release_outputs/source_calibrated_group_bootstrap.csv",
        "release_outputs/source_release_by_region.csv", "release_outputs/source_release_equal_group.csv", "release_outputs/source_release_leave_one_region_out.csv",
        "release_outputs/source_release_region_directions.csv", "release_outputs/source_release_regional_status.json", "release_outputs/source_release_regional_report.json",
        "scenarios/paired_summary.csv", "scenarios/design.json", "audit/scientific_checks.json",
        "audit/observed_record_independent_reaudit.json", "audit/screening_rule_reaudit.json", "audit/usgs_observed_independent_reaudit.json", "audit/input_panel_precision_audit.json",
        "external_walla_metadata/plan.json", "external_walla_metadata/access_probe_plan.json", "external_walla_metadata/access_probe_status.json",
        "external_hbrc_metadata/plan.json", "external_hbrc_metadata/status.json", "external_hbrc_metadata/followup_status.json",
        "external_njdep_metadata/plan.json", "external_njdep_metadata/metadata_status.json", "external_njdep_metadata/water_type_amendment.json", "external_njdep_metadata/all_water_types_status.json",
        "external_njdep_metadata/count_probe_plan.json", "external_njdep_metadata/count_probe_extension_plan.json", "external_njdep_metadata/count_probe_status.json",
        "external_njdep_metadata/count_semantics_plan.json", "external_njdep_metadata/count_semantics_status.json", "external_njdep_metadata/all_candidate_counts_plan.json", "external_njdep_metadata/all_candidate_counts_status.json",
        "external_njdep_metadata/subdaily_qualification_plan.json", "external_njdep_metadata/subdaily_acquisition.json", "external_njdep_metadata/timestamp_screen_status.json", "external_njdep_metadata/independent_timestamp_audit.json",
        "external_njdep_metadata/subdaily_extension_plan.json", "external_njdep_metadata/subdaily_extension_acquisition.json", "external_njdep_metadata/subdaily_extension_clock_status.json", "external_njdep_metadata/report.json",
        "external_andrews_metadata/status.json", "external_andrews_metadata/source_group_roster.csv",
        "external_rivtemp_metadata/plan.json", "external_rivtemp_metadata/acquisition.json", "external_rivtemp_metadata/roster_freeze.json", "external_rivtemp_metadata/prior_contact_status.json",
        "external_rivtemp_metadata/date_label_upper_bound.json", "external_rivtemp_metadata/expanded_year_amendment.json", "external_rivtemp_metadata/expanded_date_label_upper_bound.json",
        "external_rivtemp_metadata/partner_screen_plan.json", "external_rivtemp_metadata/partner_roster_freeze.json", "external_rivtemp_metadata/partner_date_upper_bound.json", "external_rivtemp_metadata/independent_date_audit.json",
        "external_neon/status.json", "external_neon/intake_plan.json", "external_neon/qualification.csv",
        "external_usgs/status.json", "external_usgs/prior_contact_addendum.csv",
        "external_usgs_fresh/status.json", "external_usgs_fresh/qualification.csv", "external_usgs_fresh/prior_contact_addendum.csv",
        "external_hubeau_reunion/status.json", "external_hubeau_reunion/qualification.csv", "external_hubeau_reunion/plan.json",
        "external_bc_air2stream/status.json", "external_bc_air2stream/qualification.csv", "external_bc_air2stream/qualification_years.csv",
        "external_bc_air2stream/plan.json", "external_bc_air2stream/roster.csv", "external_bc_air2stream/roster_source.csv",
        "external_bc_air2stream/request.json", "external_bc_air2stream/prior_contact_audit.json", "external_bc_air2stream/nearest_prior_usgs.csv", "external_bc_air2stream/annual_scorecard.csv", "external_bc_air2stream/paired_annual.csv",
        "external_bc_air2stream/site_scorecard.csv", "external_bc_air2stream/reference_integrity.json", "external_bc_air2stream/hidden_value_audit.json", "external_bc_air2stream/ts_all_58.csv", "external_bc_air2stream/ATTRIBUTION.txt",
        "external_usgs_count_screen/plan.json", "external_usgs_count_screen/candidate_roster.csv",
        "external_usgs_count_screen/approved_counts.csv", "external_usgs_count_screen/candidate_counts.csv",
        "external_usgs_count_screen/cohort.csv", "external_usgs_count_screen/preflight_status.json", "external_usgs_count_screen/pilot_contact_audit.json",
        "external_usgs_unresolved_network/plan.json", "external_usgs_unresolved_network/candidate_roster.csv",
        "external_usgs_unresolved_network/approved_counts.csv", "external_usgs_unresolved_network/candidate_counts.csv", "external_usgs_unresolved_network/status.json",
        "external_usgs_unresolved_network/extension_2025_plan.json", "external_usgs_unresolved_network/approved_counts_2025.csv",
        "external_usgs_unresolved_network/candidate_counts_2010_2025.csv", "external_usgs_unresolved_network/extension_2025_status.json",
        "external_usgs_unresolved_network/unresolved_2025_series_metadata.csv", "external_usgs_unresolved_network/unresolved_2025_metadata_status.json",
        "external_usgs_unresolved_network/report.json",
        "external_usgs_late_start/plan.json", "external_usgs_late_start/candidate_roster.csv",
        "external_usgs_late_start/approved_counts.csv", "external_usgs_late_start/candidate_counts.csv",
        "external_usgs_late_start/preflight_status.json", "external_usgs_late_start/report.json",
        "external_nechako_nhg/metadata_roster.csv", "external_nechako_nhg/candidate_roster.csv", "external_nechako_nhg/plan.json",
        "external_nechako_nhg/acquisition.json", "external_nechako_nhg/qualification_years.csv", "external_nechako_nhg/qualification_flags.csv",
        "external_nechako_nhg/qualification_status.json", "external_nechako_nhg/report.json",
        "external_csu_ross/plan.json", "external_csu_ross/site_metadata.csv", "external_csu_ross/candidate_roster.csv",
        "external_csu_ross/field_note_catalog.json", "external_csu_ross/candidate_deployment_events.csv",
        "external_csu_ross/candidate_logged_removal_pairs.csv", "external_csu_ross/deployment_years.csv", "external_csu_ross/deployment_status.json",
        "external_csu_ross/qualification_plan.json", "external_csu_ross/temperature_file_catalog.json", "external_csu_ross/qualification_unit_mapping.json",
        "external_csu_ross/acquisition.json", "external_csu_ross/qualification_years.csv", "external_csu_ross/qualification_qc_counts.csv",
        "external_csu_ross/candidate_qualification.csv", "external_csu_ross/qualification_status.json", "external_csu_ross/report.json",
        "external_nova_scotia_verified/plan.json", "external_nova_scotia_verified/candidate_roster.csv", "external_nova_scotia_verified/acquisition.json",
        "external_nova_scotia_verified/workbook_schema.json", "external_nova_scotia_verified/completeness_plan.json",
        "external_nova_scotia_verified/reported_label_completeness.csv", "external_nova_scotia_verified/reported_label_site_summary.csv", "external_nova_scotia_verified/reported_label_status.json",
        "external_nova_scotia_verified/portal_comparison_plan.json", "external_nova_scotia_verified/portal_station_counts.csv", "external_nova_scotia_verified/portal_count_status.json",
        "external_nova_scotia_verified/portal_value_comparison_plan.json", "external_nova_scotia_verified/portal_key_probe.json", "external_nova_scotia_verified/portal_acquisition.json",
        "external_nova_scotia_verified/portal_label_completeness.csv", "external_nova_scotia_verified/portal_label_site_summary.csv", "external_nova_scotia_verified/portal_label_status.json",
        "external_nova_scotia_verified/portal_workbook_comparison.csv", "external_nova_scotia_verified/portal_workbook_status.json",
        "external_nova_scotia_verified/portal_difference_diagnostic_plan.json", "external_nova_scotia_verified/portal_difference_by_year.csv", "external_nova_scotia_verified/portal_difference_by_station.csv", "external_nova_scotia_verified/portal_difference_status.json",
        "external_nova_scotia_verified/complete_label_year_overlap.csv", "external_nova_scotia_verified/common_complete_label_years.csv", "external_nova_scotia_verified/common_complete_label_site_summary.csv", "external_nova_scotia_verified/report.json",
        "external_nova_scotia_verified/prior_contact_audit.json",
        "external_nova_scotia_verified/exploratory_location_audit.csv", "external_nova_scotia_verified/exploratory_location_status.json",
        "external_nova_scotia_exploratory/plan.json", "external_nova_scotia_exploratory/reference_year_roster.csv",
        "external_nova_scotia_exploratory/source_calibration_lock.json", "external_nova_scotia_exploratory/reference_integrity.csv",
        "external_nova_scotia_exploratory/reference_status.json", "external_nova_scotia_exploratory/forcing_qualification.csv", "external_nova_scotia_exploratory/forcing_status.json",
        "external_nova_scotia_exploratory/score_summary.csv", "external_nova_scotia_exploratory/paired_summary.csv", "external_nova_scotia_exploratory/site_year_summary.csv",
        "external_nova_scotia_exploratory/score_status.json", "external_nova_scotia_exploratory/integrity_status.json", "external_nova_scotia_exploratory/hidden_value_probe.json",
        "external_nova_scotia_exploratory/paired_posthoc_diagnostics.csv", "external_nova_scotia_exploratory/diagnostic_status.json", "external_nova_scotia_exploratory/report.json",
        "external_nova_field_checks/plan.json", "external_nova_field_checks/acquisition.json",
        "external_nova_field_checks/metadata_status.json", "external_nova_field_checks/comparison_plan.json",
        "external_nova_field_checks/range_summary.csv", "external_nova_field_checks/status.json",
        "external_nova_field_checks/hour_membership_plan.json", "external_nova_field_checks/hour_membership_summary.csv",
        "external_nova_field_checks/hour_membership_status.json", "external_nova_field_checks/selected_year_range_summary.csv",
        "external_nova_field_checks/independent_audit.json",
        "external_nova_scotia_clock_sensitivity/plan.json", "external_nova_scotia_clock_sensitivity/boundary_year_availability.csv",
        "external_nova_scotia_clock_sensitivity/boundary_site_availability.csv", "external_nova_scotia_clock_sensitivity/reference_status.json",
        "external_nova_scotia_clock_sensitivity/run_availability.csv", "external_nova_scotia_clock_sensitivity/paired_summary.csv",
        "external_nova_scotia_clock_sensitivity/paired_by_station.csv", "external_nova_scotia_clock_sensitivity/paired_differences.csv",
        "external_nova_scotia_clock_sensitivity/reference_h30_changes.csv", "external_nova_scotia_clock_sensitivity/score_status.json",
        "external_nova_scotia_clock_sensitivity/integrity_status.json", "external_nova_scotia_clock_sensitivity/prediction_movement.csv",
        "external_nova_scotia_clock_sensitivity/prediction_movement_status.json", "external_nova_scotia_clock_sensitivity/report.json",
        "external_nve_seriekart_metadata/status.json", "external_nve_seriekart_metadata/catalog_metadata.csv", "external_nve_seriekart_metadata/unmatched_metadata_candidates.csv",
        "external_nve_seriekart_metadata/chart_candidate_roster.csv", "external_nve_seriekart_metadata/chart_plan.json", "external_nve_seriekart_metadata/chart_probe.csv", "external_nve_seriekart_metadata/chart_status.json",
        "external_eccc_red/plan.json", "external_eccc_red/file_roster.json", "external_eccc_red/station_metadata.csv", "external_eccc_red/prior_contact_audit.json",
        "external_eccc_red/request_log.json", "external_eccc_red/status.json", "external_eccc_red/identity_counts.csv", "external_eccc_red/status_grade_counts.csv",
        "external_eccc_red/qualification_years.csv", "external_eccc_red/prior_eccc_cache_upper_bound.csv", "external_eccc_red/prior_eccc_cache_status.json", "external_eccc_red/report.json",
        "external_eccc_red/auto-water-qual-eau-stations.csv", "external_eccc_red/auto-water-qual-eau-variableinfo.csv", "external_eccc_red/auto-water-qual-eau-tabledescriptions.csv",
        "integrated_release_trend/summary.csv", "integrated_release_trend/paired_baselines.csv",
        "integrated_release_trend/design.json", "integrated_release_trend/withhold_unassessed_summary.csv",
        "source_rights/provider_counts.csv", "source_rights/provider_source_inventory.csv", "source_rights/lubw_station_year_scope.csv",
        "source_rights/lubw_terms_review_20261027.json", "external_hubbard_metadata/plan.json", "external_hubbard_metadata/report.json",
        "external_validation_plan.json",
    ]
    missing = [str(REV / name) for name in summaries if not (REV / name).exists()]
    if missing:
        raise RuntimeError("Required summaries missing: " + ", ".join(missing))
    files.update(REV / name for name in summaries)
    adversarial = ROOT / "results/wrr_adversarial_review_20261027"
    extra_results = [
        REV / "whole_archive/uncertainty_common_cases.csv",
        adversarial / "rule_accounting/rule_accounting_summary.csv",
        adversarial / "rule_accounting/warm90_excluded_increments.csv",
        adversarial / "rule_accounting/rule_accounting_measurement_margins.csv",
        adversarial / "failure_strata/failure_strata_summary.csv",
        adversarial / "failure_strata/failure_strata_cases.parquet",
        adversarial / "failure_strata/failure_strata_leave_region_out.csv",
        adversarial / "failure_strata/failure_strata_report.json",
        adversarial / "rank_convergence/rank_convergence_summary.csv",
        adversarial / "rank_convergence/rank_convergence_cases.csv.gz",
        adversarial / "rank_convergence/rank_convergence_report.json",
        adversarial / "uncertainty_two_method_intersection.csv",
        adversarial / "metadata_correction/design_correction_manifest.csv",
        adversarial / "metadata_correction/README.md",
        adversarial / "README.md",
        ROOT / "results/wrr_review_completion_20261024/independent_study/greater_wellington/qualification_summary.json",
    ]
    absent = [str(path) for path in extra_results if not path.is_file()]
    if absent:
        raise RuntimeError("Required consistency results missing: " + ", ".join(absent))
    files.update(extra_results)
    dependencies = [
        "results/wrr_review_completion_20261024/cases/leave_one_year_out",
        "results/wrr_review_completion_20261024/cases/before_2010/seed_00.parquet",
        "results/wrr_review_completion_20261024/refits/leave_one_year_out",
        "results/wrr_review_completion_20261024/refits/before_2010/seed_00",
        "results/wrr_target_recovery_20261021/e1_archive/station_years.parquet",
        "scratch/wrr_target_recovery_20261021/archive_daily.parquet",
        "results/whole_archive", "results/release_outputs",
    ]
    inventory = [{"path": p, "present_locally": (ROOT / p).exists(),
                  "included_in_package": False,
                  "reason": "third-party records, model outputs or caches require separate rights and deposit decisions"}
                 for p in dependencies]
    readme = """REVIEW CANDIDATE — NOT A COMPLETE PUBLICATION DEPOSIT

This local archive contains project code, manuscript files and selected aggregate
results. The BC published daily input, unmodified Nechako author archive, and
Poudre author raw Parquet files are included under CC BY 4.0 with attribution.
The additional USGS observation-only daily API snapshot is included with
source attribution and acquisition queries. Run
`make review-usgs-observed-reproduction` to replay its original selection and
independently audit the nine reported windows using the supplied payloads.
This does not establish full-day sampling or model accuracy.
The main-record observation subset contains processed daily values for 95 of
the original 96 eligible stations and all 35 witness years; the LUBW station
is omitted. Run `make review-open-observed-reproduction` for its independent
record arithmetic and six screening-rule checks. It cannot establish eligibility
for the omitted station, sensor quality, upstream QC, or model accuracy.
The selected Nova Scotia portal JSON pages are included under the province's
Open Government Licence with attribution; the separately obtained legacy
workbooks remain local because their specific reuse terms are unresolved.
The original forward role assignment can retain other same-region source
groups. The bundled strict-region sensitivity covers affected release models
three archive stations, annual intervals and release-then-trend; it is not a complete strict-region rebuild. Its
restricted trained models and case-level outputs remain local.
The original source models depend on positive-weight LUBW cases even when
their target stations come from sources with recorded reuse paths. A post-hoc
candidate-provider, strict-region sensitivity is complete and its aggregate
comparisons are included. Its local models and case-level data are not included;
it is not a replacement for the original comparisons.
Other underlying source observations, main-model case-level tables and trained
model weights are not included. Make targets therefore cannot reproduce the study
from this archive alone. See dependency_inventory.json and DATA_RIGHTS.md.
A separate local-only case audit can be run if the rights-restricted evidence
is available; the restricted evidence itself is not included here.
The bundled Nechako archive contains all 32 source sites. Re-run the selected
site's reference qualification using `make review-nechako-qualification`;
its frozen screen found no qualifying complete reference year and did not
evaluate a reconstruction model.
The Poudre source files contain multiple sites and parameters. Re-run the
four selected sites using `make review-poudre-qualification`; no examined
site-year qualified and no reconstruction model was scored.
The USACE reservoir subset contains attributed time and temperature columns
from ten level-1 files. Run `make review-usace-open-reference` to reproduce
the 69 station-year availability results and the later conditional H30-bound
and observed-record screening; no full year met the stringent rule. The
conditional bounds assume missing samples lie within -5 to 50 degrees C and
do not validate source measurement quality or model accuracy.
The separate reservoir partial-history comparison additionally stages its
roster, weather, plans and aggregate scores. Its source-model weights and
per-case predictions, full source missingness generator and source calibration
are not included; the model comparison cannot be replayed from the candidate
alone. Given authorized access to those exact files, copy the included
`data/external/wrr_usace_reservoir_20261027/partial_history_roster.csv` into
`private/wrr_usace_reservoir_reference_20261027/partial_history_roster.csv`
and run `python scripts/838_usace_partial_history_predict.py`. The plan records
the exact paths of the additional required inputs. History
interpolation and zero actually complete training years differ from the original
complete-history model regime. The additional numerical dependencies used by
this generator are listed in `requirements-wrr-partial-history-replay.txt`.
The post-hoc feature-support, clipping and numerical-gate diagnostics include
aggregate reports and methods. Recomputing source training extrema, model leaf
paths or individual cases requires the restricted source-case table and model.
The source-history factorial sensitivity includes its selected processed water
and air inputs and aggregate scores. `make review-source-partial-history-reference`
checks water-year qualification and target H30; rerunning model predictions
requires separately restricted region-held models, calibration and source
missingness generator. It is an in-source, posthoc sensitivity, not independent
climate confirmation.
The USGS partial-history snapshot includes eight years of public continuous
observations, the processed daily source inputs, NASA forcing and a portable
reference replay. Run `python data/external/wrr_usgs_partial_daily_20261027/scripts/890_public_usgs_reference_replay.py`.
It does not reproduce model scores, because restricted source weights and
case-level predictions are not included. The evaluated observations were
previously opened; their clock and instrument quality remain unresolved.
The source support-warning evaluation includes the post-hoc aggregate policy
and tolerance summaries. Replaying its source cases or model outputs requires
the separately restricted source-case table and model; the matched-score
comparison uses the evaluated score distribution and is not prospective.
The Nova Scotia portal's reported-label completeness can be rerun using
`make review-nova-portal-completeness` without the legacy workbooks. This
does not establish timezone, point-level quality or independent validation.
The separate two-site Nova Scotia exploratory comparison includes selected
reported-clock daily inputs and attributed NASA POWER forcing, but not the
source-model weights or local-only case predictions. Its score audit requires
those local case files and does not establish strict-reference qualification.
The reported-day +/-1-hour sensitivity includes its attributed shifted daily
inputs and aggregate results; its per-case audit also requires locally held
baseline and shifted predictions, which are not in this package.

To recreate manuscript figures 2--5 using only the included aggregate tables:
    make review-figures-from-summaries
This checks figure rendering and assumes the summary tables; it does not
refit a model, verify individual cases, recreate Figure 1, or establish
independent scientific validation. See the original main and supporting PDFs.

The 2026-10-28 consistency materials are included: the all-station-year rule
accounting, failure-stratum cases, rank-convergence cases, the two-method
intersection table, the uncertainty case table, and the design-correction
manifest. From an extracted copy run
`python scripts/930_delivery_consistency.py`
to recompute those summaries and compare them with the manuscript text.
Compile review_completion_article.tex and review_completion_supporting.tex
afterward. This does not refit models or replace a restricted-data replay.
CITATION.cff describes an earlier v1.1.0 code-only release; it does not
identify or authorize this uncommitted manuscript revision. The authors and
archival citation for this revision are pending.

No software or dataset DOI is claimed for this revision. Author names, affiliations, funding,
conflicts, reviewer access and permanent data/code deposits remain to be
supplied or established. Do not submit this as a completed Open Research package.

The NEON qualification summarizes the CC BY 4.0 archive by Nicholas Marzolf,
https://doi.org/10.6084/m9.figshare.28074452.v1, and does not constitute an
independent backup-sensor or reconstruction-accuracy validation.
"""
    write_review_archive(destination, files, readme, inventory)
    print(f"Created {destination} with {len(files)} files; other source observations, author details and permanent deposits remain outstanding.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Candidate ZIP destination; default is dist/wrr_review_response_candidate.zip")
    main(parser.parse_args().output)
