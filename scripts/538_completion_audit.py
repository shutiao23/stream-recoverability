#!/usr/bin/env python3
"""Record what the review-response evidence proves and what is still missing."""
from __future__ import annotations
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import re
import subprocess
import zipfile
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REV = ROOT / "results/wrr_review_response_20261027"
OUT = REV / "audit/completion_status.json"

def read(path):
    return json.loads(path.read_text())

def package_evidence(root):
    """Distinguish checks of the current candidate from checks of older files."""
    archive = root / "dist/wrr_review_response_candidate.zip"
    paths = [
        "paper/wrr_tr/review_completion_article.tex",
        "paper/wrr_tr/review_completion_article.pdf",
        "paper/wrr_tr/review_completion_supporting.tex",
        "paper/wrr_tr/review_completion_supporting.pdf",
        "paper/wrr/template/agutexSI2019.cls",
        "paper/wrr_tr/figures/architecture/fig1_evidence_actual.dot",
        "paper/wrr_tr/figures/architecture/fig2_release_actual.dot",
        "DATA_RIGHTS.md",
        "metadata/data_rights.csv",
        "metadata/submission_author_metadata.json",
        "results/wrr_review_response_20261027/source_rights/provider_source_inventory.csv",
        "paper/wrr_tr/lubw_permission_request_draft.txt",
        "docs/reviews/wrr_review_response_20261027/RESPONSE_TO_TASKBOOK_20261027_ZH.md",
    ]
    if not archive.is_file():
        return {"status": "missing_candidate", "compared_paths": paths}
    mismatches = []
    with zipfile.ZipFile(archive) as z:
        names = set(z.namelist())
        for name in paths:
            path = root / name
            if name not in names or not path.is_file() or z.read(name) != path.read_bytes():
                mismatches.append(name)
    archive_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
    checks = []
    report_paths = sorted((root / "results/wrr_review_response_20261027/audit").glob("*package_check*.json"))
    for relative in ["results/wrr_process_revision_20261029/delivery_check.json",
                     "results/wrr_process_experiments_20261029/delivery_check.json"]:
        current_delivery = root / relative
        if current_delivery.is_file():
            report_paths.append(current_delivery)
    for path in report_paths:
        record = read(path)
        if record.get("status") == "passed" and record.get("archive_sha256") == archive_sha256:
            checks.append({"path": str(path.relative_to(root)),
                           "environment": record.get("environment", {}),
                           "checks": len(record.get("checks", {}))})
    environments = {json.dumps(x["environment"], sort_keys=True) for x in checks if x["environment"]}
    return {"status": "current_candidate_checked" if not mismatches and checks else "stale_or_unchecked_candidate",
            "compared_paths": paths,
            "workspace_mismatches": mismatches, "matching_reports": checks,
            "archive_sha256": archive_sha256,
            "distinct_environments": len(environments),
            "scope": "Named manuscript, figure, rights, author and response artifacts only; this does not prove full raw-data reconstruction, data rights or independent accuracy."}

def main():
    role_audit = read(REV / "audit/region_holdout_role_report.json")
    strict_archive = read(REV / "strict_region_holdout/archive_pooled_status.json")
    strict_future = read(REV / "strict_region_holdout/future_comparison_status.json")
    strict_integrated = read(REV / "strict_region_holdout/integrated_release_status.json")
    strict_role_effects = read(REV / "strict_region_holdout/all_source_role_effects_status.json")
    strict_annual = read(REV / "strict_region_holdout/annual_diagnostics_status.json")
    strict_robustness = read(REV / "strict_region_holdout/robustness_status.json")
    strict_prediction_replay = read(REV / "strict_region_holdout/archive_prediction_replay_status.json")
    strict_uncertainty = read(REV / "strict_region_holdout/uncertainty_sensitivity_status.json")
    strict_scenario = read(REV / "strict_region_holdout/scenario_sensitivity_status.json")
    strict_support_cap = read(REV / "strict_region_holdout/calibration_source_upper_bound_status.json")
    science = read(REV / "audit/scientific_checks.json")
    observed = read(REV / "audit/observed_record_independent_reaudit.json")
    precision = read(REV / "audit/input_panel_precision_audit.json")
    screening = read(REV / "audit/screening_rule_reaudit.json")
    open_observed = read(REV / "audit/open_observed_reproduction.json")
    archive_source_rights = read(REV / "audit/archive_restricted_source_roles.json")
    open_source_pilot = read(REV / "open_source_sensitivity/pilot_status.json")
    open_source_inputs = read(REV / "open_source_sensitivity/candidate_input_integrity.json")
    open_source_report = read(REV / "open_source_sensitivity/report.json")
    annual_bridge = read(REV / "audit/annual_bridge_repair_dependency.json")
    archive_bridge = read(REV / "open_source_sensitivity/archive_bridge_repair_dependency.json")
    open_source_annual = read(REV / "open_source_sensitivity/annual_sensitivity_report.json")
    single_year_expansion = read(REV / "open_source_sensitivity/single_year_calibration_report.json")
    single_year_trend = read(REV / "open_source_sensitivity/single_year_trend_report.json")
    usgs_witness = read(REV / "audit/usgs_observed_independent_reaudit.json")
    usgs_reproduction = read(REV / "audit/usgs_observed_reproduction.json")
    support = read(REV / "whole_archive/support_projection_report.json")
    visibility = read(REV / "whole_archive/peak_visibility_report.json")
    expansion = read(REV / "annual_interval_expansion/report.json")
    archive = read(REV / "whole_archive/status.json")
    au_prior = read(REV / "audit/australia_prior_exposure_status.json")
    au_prior_independent = read(REV / "audit/australia_prior_exposure_independent.json")
    nz_quality_bound = read(REV / "external_nz_quality_bounds/summary.json")
    nz_count_audit = read(REV / "external_nz_quality_bounds/independent_count_audit.json")
    matched_archive = read(REV / "archive_matched_release_trend/status.json")
    matched_archive_audit = read(REV / "archive_matched_release_trend/independent_audit.json")
    matched_likelihood_audit = read(REV / "archive_matched_release_trend/independent_likelihood_audit.json")
    expanded_stress = read(REV / "expanded_stress/status.json")
    expanded_stress_audit = read(REV / "expanded_stress/independent_audit.json")
    heat_gap = read(REV / "heat_gap_matched/status.json")
    heat_gap_audit = read(REV / "heat_gap_matched/independent_audit.json")
    heat_gap_threeway = read(REV / "heat_gap_matched/threeway_independent_audit.json")
    heat_gap_clarification = read(REV / "heat_gap_matched/plan_clarification.json")
    heat_gap_source = read(REV / "heat_gap_source_sensitivity/status.json")
    heat_gap_source_audit = read(REV / "heat_gap_source_sensitivity/independent_audit.json")
    heat_gap_interaction_audit = read(REV / "heat_gap_source_sensitivity/source_interactions_independent_audit.json")
    heat_gap_influence_audit = read(REV / "heat_gap_source_sensitivity/source_interaction_influence_independent_audit.json")
    stress_source = read(REV / "expanded_stress_source_sensitivity/status.json")
    stress_source_audit = read(REV / "expanded_stress_source_sensitivity/independent_audit.json")
    stress_source_baseline_audit = read(REV / "expanded_stress_source_sensitivity/baseline_audit.json")
    projected_risk = read(REV / "projected_risk_sensitivity/status.json")
    projected_risk_audit = read(REV / "projected_risk_sensitivity/independent_audit.json")
    summer_window = read(REV / "summer_window_comparison/summary.json")
    beaufort_proxy = read(REV / "beaufort_proxy/status.json")
    beaufort_proxy_audit = read(REV / "beaufort_proxy/independent_audit.json")
    beaufort_air_audit = read(REV / "beaufort_proxy/power_vintage_independent_audit.json")
    summer_archive = read(REV / "summer_proxy_archive/status.json")
    summer_archive_audit = read(REV / "summer_proxy_archive/independent_audit.json")
    donor_provenance = read(REV / "open_source_sensitivity/donor_provenance_status.json")
    donor_daily = read(REV / "open_source_sensitivity/donor_usgs_daily_comparison.json")
    donor_daily_audit = read(REV / "open_source_sensitivity/donor_usgs_daily_independent_audit.json")
    camelsh_count = read(REV / "external_camelsh_hourly/count_status.json")
    camelsh_current = read(REV / "external_camelsh_hourly/current_metadata_status.json")
    truckee_finite = read(REV / "external_truckee_dwr/finite_reference_status.json")
    truckee_score = read(REV / "external_truckee_dwr/exploratory_score_status.json")
    truckee_score_audit = read(REV / "external_truckee_dwr/exploratory_score_independent_audit.json")
    truckee_hidden = read(REV / "external_truckee_dwr/exploratory_hidden_probe.json")
    truckee_reference_replay = read(REV / "audit/truckee_open_reference_replay.json")
    truckee_peak = read(REV / "external_truckee_dwr/peak_visibility_status.json")
    truckee_peak_audit = read(REV / "external_truckee_dwr/peak_visibility_independent_audit.json")
    truckee_power = read(REV / "external_truckee_dwr/power_time_comparison.json")
    truckee_power_audit = read(REV / "external_truckee_dwr/power_time_independent_audit.json")
    truckee_power_replay = read(REV / "audit/truckee_power_time_open_replay.json")
    truckee_wqp = read(REV / "external_truckee_dwr/wqp_field_comparison_status.json")
    truckee_wqp_audit = read(REV / "external_truckee_dwr/wqp_field_independent_audit.json")
    truckee_wqp_replay = read(REV / "audit/truckee_wqp_open_replay.json")
    reservoir = read(REV / "external_usace_reservoir/finite_reference_status.json")
    reservoir_network = read(REV / "external_usace_reservoir/network_status.json")
    reservoir_replay = read(REV / "audit/usace_open_reference_replay.json")
    reservoir_bounds = read(REV / "external_usace_reservoir/partial_year_bounds_status.json")
    reservoir_record = read(REV / "external_usace_reservoir/partial_year_record_screen_status.json")
    reservoir_bounds_replay = read(REV / "audit/usace_bounds_open_replay.json")
    partial_score = read(REV / "external_usace_reservoir/partial_history_score_status.json")
    partial_score_audit = read(REV / "external_usace_reservoir/partial_history_score_independent_audit.json")
    partial_probe = read(REV / "external_usace_reservoir/partial_history_paired_hidden_observed_status.json")
    partial_replay = read(REV / "external_usace_reservoir/partial_history_prediction_replay_status.json")
    partial_power = read(REV / "audit/usace_partial_power_open_replay.json")
    partial_support = read(REV / "external_usace_reservoir/partial_history_feature_support_status.json")
    partial_support_audit = read(REV / "external_usace_reservoir/partial_history_feature_support_independent_audit.json")
    partial_phi = read(REV / "external_usace_reservoir/partial_history_autocorrelation_status.json")
    partial_phi_audit = read(REV / "external_usace_reservoir/partial_history_autocorrelation_independent_audit.json")
    partial_clip = read(REV / "external_usace_reservoir/partial_history_clipping_independent_audit.json")
    partial_gate = read(REV / "external_usace_reservoir/partial_history_gate_status.json")
    source_history = read(REV / "source_partial_history_factorial/scoring_status.json")
    source_history_audit = read(REV / "source_partial_history_factorial/independent_audit.json")
    source_history_probe = read(REV / "source_partial_history_factorial/hidden_probe_status.json")
    source_history_reference = read(REV / "audit/source_partial_history_open_reference_replay.json")
    source_history_prediction_replay = read(REV / "source_partial_history_factorial/local_prediction_replay_status.json")
    warning = read(REV / "source_ood_release/status.json")
    warning_audit = read(REV / "source_ood_release/independent_audit.json")
    warning_margin = read(REV / "source_ood_release/margin_sensitivity_status.json")
    warning_margin_audit = read(REV / "source_ood_release/margin_sensitivity_independent_audit.json")
    summer_audit = read(REV / "summer_window_comparison/independent_audit.json")
    summer_influence_audit = read(REV / "summer_window_comparison/influence_independent_audit.json")
    past_season = read(REV / "past_season_screening/status.json")
    past_season_audit = read(REV / "past_season_screening/independent_audit.json")
    groupmax_annual = read(REV / "groupmax_annual_calibration/status.json")
    groupmax_audit = read(REV / "groupmax_annual_calibration/independent_audit.json")
    groupmax_trend = read(REV / "groupmax_annual_calibration/trend_independent_audit.json")
    groupmax_repair = read(REV / "groupmax_annual_calibration/source_repair_dependency.json")
    walla = read(REV / "external_walla_metadata/access_probe_status.json")
    njdep = read(REV / "external_njdep_metadata/report.json")
    andrews = read(REV / "external_andrews_metadata/status.json")
    rivtemp = read(REV / "external_rivtemp_metadata/plan.json")
    rivtemp_dates = read(REV / "external_rivtemp_metadata/date_label_upper_bound.json")
    rivtemp_extended = read(REV / "external_rivtemp_metadata/expanded_date_label_upper_bound.json")
    rivtemp_partners = read(REV / "external_rivtemp_metadata/partner_date_upper_bound.json")
    rivtemp_check = read(REV / "external_rivtemp_metadata/independent_date_audit.json")
    neon = read(REV / "external_neon/status.json")
    fresh = read(REV / "external_usgs_fresh/status.json")
    reunion = read(REV / "external_hubeau_reunion/status.json")
    count_screen = read(REV / "external_usgs_count_screen/preflight_status.json")
    unresolved = read(REV / "external_usgs_unresolved_network/report.json")
    late_usgs = read(REV / "external_usgs_late_start/report.json")
    nechako = read(REV / "external_nechako_nhg/report.json")
    poudre = read(REV / "external_csu_ross/report.json")
    nova = read(REV / "external_nova_scotia_verified/report.json")
    nova_exp = read(REV / "external_nova_scotia_exploratory/report.json")
    nova_clock = read(REV / "external_nova_scotia_clock_sensitivity/report.json")
    nova_field = read(REV / "external_nova_field_checks/status.json")
    nova_field_audit = read(REV / "external_nova_field_checks/independent_audit.json")
    nova_field_ranges = pd.read_csv(REV / "external_nova_field_checks/selected_year_range_summary.csv")
    nova_field_selected_rows = nova_field_ranges[(nova_field_ranges.scope=='modeled_years') &
                                                 (nova_field_ranges.site=='both_sites') &
                                                 (nova_field_ranges.window=='same_day')]
    if len(nova_field_selected_rows)!=1:raise ValueError('Nova Scotia field comparison summary is not unique')
    nova_field_selected = nova_field_selected_rows.iloc[0]
    nve_chart = read(REV / "external_nve_seriekart_metadata/chart_status.json")
    first = read(REV / "external_usgs/status.json")
    eccc = read(REV / "external_eccc_red/status.json")
    eccc_prior = read(REV / "external_eccc_red/prior_eccc_cache_status.json")
    bc = read(REV / "external_bc_air2stream/status.json")
    bc_integrity = read(REV / "external_bc_air2stream/reference_integrity.json")
    bc_hidden = read(REV / "external_bc_air2stream/hidden_value_audit.json")
    author = read(ROOT / "metadata/submission_author_metadata.json")
    hubbard_metadata = read(REV / "external_hubbard_metadata/report.json")
    lubw_terms_scope = read(REV / "source_rights/lubw_terms_review_20261027.json")
    usgs_qualifier = ROOT / "data/external/wrr_usgs_partial_daily_20261027/qualifier"
    usgs_history_audit = read(usgs_qualifier / "qualifier_aware_history_independent_audit.json")
    usgs_score_audit = read(usgs_qualifier / "qualifier_aware_score_independent_audit.json")
    usgs_prediction_replay = read(usgs_qualifier / "qualifier_replay_status.json")
    numeric_archive = read(REV / "whole_archive/main_coverage_numeric_scalar_audit.json")
    numeric_source = read(REV / "annual/single_year_coverage_scalar_audit.json")
    bundle = package_evidence(ROOT)
    si_format = read(REV / "audit/si_format_audit_20261027.json")
    si_format_current = (ROOT / "paper/wrr_tr/review_completion_supporting.pdf").is_file()
    matched = pd.read_csv(REV / "release_outputs/matched_numerical_retention.csv")
    matched_clean = matched.loc[matched.condition.eq("clean") & matched.family.eq("calendar")].iloc[0]
    source_audit = read(REV / "release_outputs/source_calibrated_audit.json")
    regional_release = read(REV / "release_outputs/source_release_regional_report.json")
    source_matched = pd.read_csv(REV / "release_outputs/source_calibrated_release_summary.csv")
    rules = pd.read_csv(REV / "rules/rule_summary.csv").set_index("rule")
    task = pd.read_csv(REV / "whole_archive/task_calibration_summary.csv")
    task_forward = task.loc[task.family.eq("crossed") & task["mode"].eq("forward") & task.estimator.eq("D2")].iloc[0]
    integrated = pd.read_csv(REV / "integrated_release_trend/summary.csv")
    selected = integrated.loc[integrated.family.eq("crossed") & integrated["mode"].eq("forward") & integrated.method.eq("released_values_and_bounds")].iloc[0]
    case_states = pd.read_parquet(REV / "integrated_release_trend/annual_decisions.parquet",
                                  columns=["output_state", "quality_flag"])
    scored = pd.read_csv(REV / "annual/source_scorecard_summary.csv")
    d2 = scored.loc[scored.family.eq("crossed") & scored.stratum.eq("danger") & scored.estimator.eq("distribution_regression")].iloc[0]
    tests = subprocess.run(["make", "review-test"], cwd=ROOT, capture_output=True, text=True)
    (REV / "audit/test_output.txt").write_text(tests.stdout + tests.stderr)
    status = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Evidence audit for the current working tree; not an acceptance prediction or a clean-room rebuild.",
        "requirements": [
            {"item":"Forward-region role discrepancy and strict sensitivity", "status":"found_and_sensitivity_evaluated_not_full_rebuild",
             "held_test_group_overlap":role_audit["held_target_group_overlap"],
             "models_audited":role_audit["models_checked"],
             "affected_archive_settings":strict_archive["strict_archive_settings"],
             "affected_future_case_rows":strict_future["affected_region_cases"],
             "integrated_original_annual_decisions_replayed":strict_integrated["original_annual_rows_replayed"],
             "global_role_station_overlap":strict_role_effects["held_station_overlap_anywhere"],
             "affected_annual_cases":strict_annual["affected_annual_cases"],
             "strict_annual_model_predictions_replayed":strict_prediction_replay["annual_cases_replayed"],
             "strict_original_region_robustness_reproduced":strict_robustness["original_pooled_and_leave_region_out_reproduced"],
             "original_tail_rows_reproduced":strict_uncertainty["original_tail_rows_replayed"],
             "affected_strict_stress_settings":strict_scenario["strict_scenario_settings"],
             "source_group_upper_bound":strict_support_cap["source_group_upper_bound_before_model_predictions"],
             "limitation":strict_archive["limitation"]},
            {"item":"Support constraint and revised tail assumption", "status":"computed_and_checked",
             "below_bound":science["n_annual_quantiles_below_observed_bound"],
             "interval_tail":"adjacent normal-quantile continuation, constrained by the observation bound; assumption remains unverified"},
            {"item":"Annual interval boundary and degeneracy", "status":"computed_against_complete_reference",
             "forward_calendar_common_cases":support["forward_calendar_common_cases"],
             "D2_zero_width":support["D2_zero_width"], "stochastic_zero_width":support["stochastic_zero_width"],
             "D2_zero_created_by_final_projection":support["forward_calendar_D2_zero_created_last_projection"],
             "D2_zero_pre_final_projection":support["forward_calendar_D2_zero_before_last_projection"],
             "stochastic_zero_created_by_final_projection":support["forward_calendar_stochastic_zero_created_last_projection"],
             "controlled_stochastic_zero_width_missed":support["controlled_stochastic_zero_width_missed"],
             "limitation":"pre-final predictions retain first projection and projection-aware offsets; no alternative calibration fitted; cases include repeated masks and physical measurement error is not assessed"},
            {"item":"Annual fair comparator", "status":"computed", "source_seeds":int(d2.n_seeds),
             "D2_mae":float(d2.mae_median), "bridge_dependency_audit":annual_bridge["status"],
             "seed_case_rows_newly_available_with_repair":annual_bridge["became_valid_with_repair"],
             "risk":"20 repeated fits share the same archive; repair dependency reconstructed post hoc"},
            {"item":"Retrospective reference-bound stratification", "status":"computed_outcome_defined",
             "forward_calendar_common_cases":visibility["calendar_forward_common"],
             "forward_calendar_bound_matches_reference":visibility["calendar_reference_bound_matches"],
             "forward_calendar_reference_above_bound":visibility["calendar_reference_above_bound"],
             "forward_controlled_reference_above_bound":visibility["controlled_reference_above_bound"],
             "forward_controlled_D2_coverage":visibility["controlled_hidden_d2_coverage90"],
             "forward_controlled_stochastic_coverage":visibility["controlled_hidden_stochastic_coverage90"],
             "limitation":visibility["limitation"]},
            {"item":"Candidate-provider strict-region annual interval sensitivity", "status":"computed_posthoc_not_calibrated",
             "matched_annual_cases":open_source_annual["annual_cases"],
             "forward_controlled_hidden_peak_cases":open_source_annual["hidden_forward_crossed_cases"],
             "D2_original_coverage90":open_source_annual["D2_original_coverage90"],
             "D2_candidate_coverage90":open_source_annual["D2_candidate_coverage90"],
             "classic_original_coverage90":open_source_annual["classic_original_coverage90"],
             "classic_candidate_coverage90":open_source_annual["classic_candidate_coverage90"],
             "archive_bridge_dependency_audit":archive_bridge["status"],
             "archive_calibration_cells_affected":archive_bridge["cells_with_changed_offsets"],
             "independent_summary_rows":open_source_annual["score_rows_checked"],
             "limitation":open_source_annual["limitations"]},
            {"item":"Single-year annual expansion propagated to trends", "status":"computed_posthoc_not_calibrated",
             "groupmax_annual_common_cases":groupmax_annual["forward_common_annual_cases"],
             "groupmax_annual_independent_audit":groupmax_audit["status"],
             "groupmax_bridge_repair_audit":groupmax_repair["status"],
             "groupmax_source_radii_changed_if_repair_omitted":groupmax_repair["cells_with_changed_radius"],
             "groupmax_trend_common_archives":groupmax_trend["matched_nontrivial_archives"],
             "groupmax_trend_independent_audit":groupmax_trend["status"],
             "all_forward_controlled_archives":single_year_trend["all_forward_crossed_archives"],
             "source_supported_archives":single_year_trend["source_supported_archives"],
             "common_nontrivial_archives":single_year_trend["common_nontrivial_archives"],
             "D2_independent_coverage":single_year_trend["D2_independent_coverage"],
             "classic_independent_coverage":single_year_trend["classic_independent_coverage"],
             "audit_scope":single_year_trend["audit_scope"],
             "limitation":single_year_trend["limitations"]},
            {"item":"Single-year source annual expansion", "status":"computed_exploratory_not_a_guarantee",
             "forward_controlled_eligible":single_year_expansion["forward_crossed_eligible"],
             "forward_controlled_both_supported":single_year_expansion["forward_crossed_supported_both"],
             "D2_paired_coverage_before":single_year_expansion["D2_before90"],
             "D2_paired_coverage_after":single_year_expansion["D2_after90"],
             "classic_paired_coverage_before":single_year_expansion["classic_before90"],
             "classic_paired_coverage_after":single_year_expansion["classic_after90"],
             "hidden_both_supported":single_year_expansion["hidden_supported"],
             "forward_finite_group_max_corrections":single_year_expansion["forward_finite_group_max"],
             "limitation":single_year_expansion["limitations"]},
            {"item":"Source-only annual interval expansion", "status":"computed_exploratory_not_a_guarantee",
             "forward_controlled_common":expansion["forward_controlled_common"],
             "forward_controlled_supported":expansion["forward_controlled_supported"],
             "supported_stations":expansion["forward_controlled_supported_stations"],
             "D2_coverage_before":expansion["forward_d2_coverage_before"],
             "D2_coverage_after":expansion["forward_d2_coverage_after"],
             "finite_group_max_corrections":expansion["finite_group_max_corrections"],
             "limitation":expansion["limitations"]},
            {"item":"Whole-archive refit and paired retention", "status":"computed",
             "station_repetitions":archive["completed_station_repetitions"], "stations":archive["n_stations"],
             "hidden_target_values":science["n_hidden_target_values_present"]},
            {"item":"Task calibration safety", "status":"implemented_but_coverage_not_established",
             "zero_width_incomplete":science["n_zero_width_task_intervals_on_incomplete_archives"],
             "forward_long_gap_available":float(task_forward.availability),
             "source_groups_below_minimum":science["n_supported_task_models_below_three_source_groups"]},
            {"item":"Observed record arithmetic re-audit", "status":"computed_on_same_archived_daily_values",
             "source_reference_years":observed["reference_station_years_recomputed"],
             "source_witnesses":observed["certificate_station_years"],
             "open_source_subset_stations":open_observed["included_stations"],
             "open_source_subset_witnesses_recomputed":open_observed["witness_station_years"],
             "open_source_subset_rule_decisions":open_observed["rule_decisions_checked"],
             "input_panel_finite_values_compared":precision["finite_daily_values_compared"],
             "input_panel_cast_disagreements":precision["float32_cast_disagreements"],
             "witness_changes_from_rounding":precision["witness_identity_changes"],
             "screening_decisions":screening["witness_rule_decisions_checked"],
             "USGS_approved_reference_years":usgs_witness["complete_approved_station_years"],
             "USGS_witnesses":usgs_witness["witness_station_years_checked"],
             "USGS_packaged_observation_only_replay":usgs_reproduction["status"],
             "USGS_replayed_tables":usgs_reproduction["tables_reproduced"],
             "limitation":"source uses canonical float32 daily archive, not provider-native raw; USGS subdaily quality and source sensor accuracy remain unverified"},
            {"item":"Practical screening comparison", "status":"computed",
             "seasonal_complete_station_years":summer_window["complete_station_years"],
             "seasonal_stations":summer_window["stations"],
             "seasonal_windows_above_tolerance":summer_window["different_above_tolerance_years"],
             "seasonal_window_independent_audit":summer_audit["status"],
             "seasonal_influence_independent_audit":summer_influence_audit["status"],
             "past_season_station_years":past_season["station_years"],
             "past_season_independent_audit":past_season_audit["status"],
             "original_witnesses":int(rules.loc["warm_90_station_specific", "witness_years"]),
             "witnesses_passing_warm90":int(rules.loc["warm_90_station_specific", "admitted_witness_years"]),
             "excluded_above_reported_record":int(rules.loc["warm_90_station_specific", "excluded_exceed_reported_record"])},
            {"item":"Published-method-inspired interannual summer peak", "status":"computed_posthoc_adaptation",
             "stations":beaufort_proxy["available_stations"],"connected_groups":beaufort_proxy["planned_groups"],
             "case_masks":beaufort_proxy["station_case_rows"],"independent_arithmetic_audit":beaufort_proxy_audit["status"],
             "current_air_response_audit":beaufort_air_audit["status"],
             "limitation":beaufort_proxy["limitations"]},
            {"item":"Published-method-inspired annual and archive proxy", "status":"computed_posthoc_adaptation",
             "archive_settings":summer_archive["archive_settings"], "masked_year_rows":summer_archive["annual_rows"],
             "representative_case_audit":summer_archive_audit["status"],
             "limitation":summer_archive["interpretation"]},
            {"item":"Heat-associated and synchronized-donor stresses", "status":"computed_expanded_exploratory_not_causal",
             "expanded_forward_settings_per_scenario":expanded_stress["expected_per_scenario"],
             "expanded_independent_mask_audit":expanded_stress_audit["status"],
             "matched_gap_settings":heat_gap["mask_audit"]["settings"],
             "matched_gap_independent_audit":heat_gap_audit["status"],
             "matched_gap_threeway_audit":heat_gap_threeway["status"],
             "matched_gap_source_replays":heat_gap_source["source_replays"],
             "matched_gap_source_independent_audit":heat_gap_source_audit["status"],
             "matched_gap_source_interaction_audit":heat_gap_interaction_audit["status"],
             "matched_gap_group_influence_audit":heat_gap_influence_audit["status"],
             "matched_gap_daily_feature_files_checked":heat_gap_source_audit["daily_feature_files_compared"],
             "heat_burnin_stations_with_2010_or_later_year":heat_gap_clarification["stations_with_any_2010_or_later_burnin"],
             "stress_alternative_source_reanalyses":stress_source["scenario_reanalyses"],
             "stress_source_independent_summary_audit":stress_source_audit["status"],
             "stress_source_candidate_baseline_receipts":stress_source_baseline_audit["candidate_baseline_receipts_verified"],
             "stress_source_strict_baselines_replayed":stress_source_baseline_audit["strict_huc17_baselines_replayed"],
             "different_donor_masks":science["n_synchronized_donor_cases_with_different_masks"],
             "hidden_donor_values":science["n_synchronized_donor_cases_with_visible_hidden_donors"]},
            {"item":"Matched numerical release comparison", "status":"computed_transductive_descriptive",
             "projected_risk_masked_cases":projected_risk["target_masked_cases"],
             "projected_risk_reference_available":projected_risk["reference_available"],
             "projected_risk_independent_audit":projected_risk_audit["status"],
             "clean_matched_outputs":int(matched_clean.n_equal_numerical),
             "three_output_bad":int(matched_clean.three_output_bad),
             "score_only_bad":int(matched_clean.score_only_bad),
             "limitation":"cutoff matches evaluation-set release count, not a prespecified prospective policy; lower bounds and unknowns are not held equal"},
            {"item":"Source-derived release thresholds", "status":"computed_clean_group_disjoint_exploratory",
             "held_cases":source_audit["n_target_cases"], "held_region_family_thresholds":source_audit["n_source_thresholds"],
             "missing_threshold_cases":source_audit["missing_threshold_cases"], "target_audit_passed":source_audit["passed"],
             "crossed_region_directions":regional_release["regions_crossed"],
             "common_groups":int(regional_release["common_group_means_calendar"]["n_both_defined"]),
             "limitation":"one retrospective model seed, differing target retention, and no group-risk or climate-transfer guarantee"},
            {"item":"Release followed by selected trend", "status":"computed_working_likelihood_only",
             "archive_matched_count_comparison":matched_archive["status"],
             "archive_matched_archive_settings":matched_archive["matched_archives"],
             "archive_matched_independent_audit":matched_archive_audit["status"],
             "archive_matched_likelihoods_checked":matched_likelihood_audit["working_fits_checked"],
             "forward_long_gap_rmse":float(selected.rmse),
             "working_coverage95":float(selected.total_working_coverage95),
             "working_width95":float(selected.total_working_width95),
             "annual_states":case_states.output_state.value_counts().to_dict(),
             "quality_diagnostic_unassessed":int(case_states.loc[case_states.output_state.ne("complete_observed"), "quality_flag"].isna().sum()),
             "limitation":"working interval includes regression variability; not a calibrated missingness-only interval"},
            {"item":"Independent accuracy reference", "status":"not_available",
             "Hubbard_Brook_metadata_screen":hubbard_metadata["status"],
             "Hubbard_Brook_metadata_documents":hubbard_metadata["metadata_documents"],
             "Hubbard_Brook_temperature_tables_downloaded":hubbard_metadata["measurement_tables_downloaded"],
             "NZ_quality_blind_cached_sites":nz_quality_bound["n_sites"],
             "NZ_quality_blind_possible_four_year_sites":nz_quality_bound["n_sites_possibly_four_years"],
             "NZ_quality_blind_independent_count_audit":nz_count_audit["all_counts_match"],
             "Australian_candidate_station_years":au_prior["original_reference_station_years"],
             "Australian_candidates_in_earlier_evaluable_cases":au_prior["round1_prior_evaluation_eligible_station_years"],
             "Australian_old_F2_test_years_in_earlier_evaluation":au_prior["round1_original_test_role_evaluated"],
             "Australian_prior_exposure_independent_audit":au_prior_independent["status"],
             "Australian_F2_errors_computed_by_this_audit":au_prior["new_F2_predictions_or_errors_computed_by_this_audit"],
             "Walla_Walla_current_access":walla["status"],
             "Walla_Walla_temperature_scored":walla["temperature_data_saved_or_scored"],
             "NJDEP_metadata_station_options":njdep["metadata_station_options"],
             "NJDEP_freshwater_missing_span_unknown":njdep["freshwater_options_without_qa_dates"],
             "NJDEP_selected_stations":njdep["screened_stations"],
             "NJDEP_station_years_missing_reported_dates":njdep["station_years_missing_reported_dates"],
             "NJDEP_independent_timestamp_recounts_passed":njdep["independent_timestamp_recounts_passed"],
             "NJDEP_csv_rows_match_provider_count":njdep["station_year_csv_count_endpoint_matches"],
             "Andrews_Lookout_existing_source_station":andrews["source_station_alias"],
             "Andrews_existing_source_group_stations":andrews["connected_source_stations"],
             "Andrews_temperature_values_scored":andrews["hja_measurement_rows_downloaded_or_scored"],
             "RivTemp_initial_plan":rivtemp["status"],
             "RivTemp_MFFP_station_ids":rivtemp_dates["n_roster_ids"],
             "RivTemp_MFFP_four_year_label_upper_bound_2010_2020":rivtemp_dates["n_station_ids_four_possible_years"],
             "RivTemp_MFFP_four_year_label_upper_bound_full_published_period":rivtemp_extended["n_station_ids_four_possible_years"],
             "RivTemp_other_partner_results":rivtemp_partners["datasets"],
             "RivTemp_independent_date_audit":rivtemp_check["status"],
             "NEON_eligible":neon["strict_reference_eligible"], "fresh_USGS_eligible":fresh["n_eligible"],
             "reunion_eligible":reunion["n_eligible"], "reunion_unavailable":reunion["n_unavailable"],
             "first_USGS_cohort_prior_contact":first["prior_contact_stations"],
             "ECCC_red_complete_wallclock_years_under_frozen_rule":eccc["complete_local_wallclock_years"],
             "ECCC_red_identity_unresolved_rows":eccc["n_identity_unresolved_rows"],
             "ECCC_red_same_river_as_source":eccc["prior_same_river_source"],
             "ECCC_prior_opened_stations":eccc_prior["opened_stations"],
             "NVE_chart_candidates":nve_chart["candidate_stations"],
             "NVE_chart_points_returned":nve_chart["points_returned"],
             "USGS_count_candidates":count_screen["metadata_candidates"],
             "USGS_count_eligible_2010_2024":count_screen["preflight_pass"],
             "USGS_count_not_returned":count_screen["statistics_not_returned"],
             "USGS_late_start_metadata_candidates":late_usgs["candidate_sites"],
             "USGS_late_start_count_confirmed_four_years":late_usgs["count_confirmed_four_years"],
             "USGS_late_start_unreturned_statistics_are_unknown":True,
             "USGS_unresolved_network_count_candidates":unresolved["initial_candidates"],
             "USGS_unresolved_network_initial_count_pass":unresolved["initial_count_pass"],
             "USGS_unresolved_network_posthoc_2025_pass":unresolved["extension_count_pass"],
             "USGS_unresolved_network_posthoc_2025_unknown":unresolved["extension_count_unknown"],
             "Nechako_updated_metadata_candidates":nechako["metadata_candidates"],
             "Nechako_updated_qualified_years":nechako["qualified_reference_years"],
             "Nechako_same_river_as_previous_BC":nechako["same_river_as_previous_bc_case"],
             "Poudre_selected_sites":poudre["sites"],
             "Poudre_examined_site_years":poudre["site_years"],
             "Poudre_author_pass_complete_years":poudre["complete_author_pass_years"],
             "Nova_Scotia_sites_four_equal_complete_label_years":nova["stations_with_four_equal_complete_label_years"],
             "Nova_Scotia_strict_reference_status":nova["strict_reference_qualification"],
             "Nova_Scotia_release_numeric_differences_gt_half_c":nova["numeric_different_over_0p5_c"],
             "Nova_Scotia_exploratory_scored":bool(nova_exp["cases"]),
             "Nova_Scotia_exploratory_cases":nova_exp["cases"],
             "Nova_Scotia_exploratory_stations":nova_exp["stations"],
             "Nova_Scotia_exploratory_strict_reference":nova_exp["strict_reference_qualified"],
             "Nova_Scotia_clock_common_cases":nova_clock["common_cases"],
             "Nova_Scotia_clock_max_reference_change_c":nova_clock["max_reference_h30_change_c"],
             "Nova_Scotia_clock_max_D2_prediction_change_c":nova_clock["max_d2_point_change_c"],
             "Nova_Scotia_field_status":nova_field["status"],
             "Nova_Scotia_field_independent_arithmetic_audit":nova_field_audit["status"],
             "Nova_Scotia_field_modeled_site_dates_compared":int(nova_field_selected.compared_site_dates),
             "Nova_Scotia_field_modeled_site_dates_outside_reported_range":int(nova_field_selected.site_dates_any_outside),
             "Nova_Scotia_field_time_labels_present":nova_field["time_label_present"],
             "BC_strict_24h_eligible":bc["n_strict_24h_eligible"],
             "BC_exploratory_published_daily_stations":bc["n_scored_stations"],
             "BC_reference_arithmetic_checked_cases":bc_integrity["cases"],
             "BC_hidden_value_probe_cases":bc_hidden["n_cases"],
             "BC_hidden_value_probe_passed":bc_hidden["passed"],
             "Truckee_complete_finite_years":truckee_finite["complete_finite_station_years"],
             "Truckee_stations_with_four_finite_years":truckee_finite["stations_with_four_finite_reference_years"],
             "Truckee_scored_stations":truckee_score["stations"], "Truckee_scored_years":truckee_score["reference_years"],
             "Truckee_mask_cases":truckee_score["cases"], "Truckee_strict_reference_qualified":truckee_score["strict_reference_qualified"],
             "Truckee_score_arithmetic_audit":truckee_score_audit["status"], "Truckee_hidden_probe":truckee_hidden["status"],
             "Truckee_public_reference_replay":truckee_reference_replay["status"],
             "Truckee_peak_reference_above_bound_cases":truckee_peak["cases_by_stratum"]["reference_above_bound"],
             "Truckee_peak_stratum_independent_audit":truckee_peak_audit["status"],
             "Truckee_POWER_hour_pairs":truckee_power["finite_hour_pairs"],
             "Truckee_POWER_hour_pairs_equal":truckee_power["hour_pairs_equal_1e_6"],
             "Truckee_POWER_time_audit":truckee_power_audit["status"], "Truckee_POWER_public_replay":truckee_power_replay["status"],
             "Truckee_WQP_same_agency_pairs":truckee_wqp["comparable_rows"],
             "Truckee_WQP_independent_sensor_verified":truckee_wqp["independent_sensor_verified"],
             "Truckee_WQP_field_audit":truckee_wqp_audit["status"], "Truckee_WQP_public_replay":truckee_wqp_replay["status"],
             "USACE_reservoir_candidates":reservoir["resources"], "USACE_reservoir_station_years":reservoir["station_years"],
             "USACE_reservoir_complete_finite_years":reservoir["complete_finite_station_years"],
             "USACE_reservoir_gages_with_prior_network_hits":reservoir_network["gages_with_prior_hits"],
             "USACE_reservoir_public_replay":reservoir_replay["status"],
             "USACE_bounded_station_years":reservoir_bounds["station_years"],
             "USACE_bounded_years_width_at_most_point_1_c":reservoir_bounds["year_counts_width_at_most_c"]["0.1"],
             "USACE_added_95_percent_rule_record_witnesses":reservoir_record["rules"]["95"]["guaranteed_added_record_years"],
             "USACE_bounds_public_replay":reservoir_bounds_replay["status"],
             "USACE_partial_history_cases":partial_score["cases"], "USACE_partial_history_target_years":partial_score["target_station_years"],
             "USACE_partial_history_score_audit":partial_score_audit["status"],
             "USACE_partial_history_hidden_probes":partial_probe["paired_output_passes"],
             "USACE_partial_history_local_prediction_replay":partial_replay["status"],
             "USACE_partial_history_POWER_public_replay":partial_power["status"],
             "USACE_partial_other_feature_outside_training_cases":partial_support["target"]["outside_minmax_excluding_complete_count_cases"],
             "USACE_partial_support_audit":partial_support_audit["status"],
             "USACE_partial_observed_only_phi_outside_training_years":partial_phi["observed_only_phi_outside_training_range_years"],
             "USACE_partial_phi_audit":partial_phi_audit["status"],
             "USACE_partial_clipped_leaf_audit":partial_clip["status"],
             "USACE_partial_history_gate_numeric_cases":partial_gate["numeric_states_with_no_quality_flag_and_no_optional_limits"],
             "source_partial_history_stations":source_history["stations"],
             "source_partial_history_groups":source_history["groups"],
             "source_partial_history_common_cases":source_history["common_cases"],
             "source_partial_history_score_audit":source_history_audit["status"],
             "source_partial_history_hidden_probe":source_history_probe["status"],
             "source_partial_history_public_reference":source_history_reference["status"],
             "source_partial_history_local_prediction_replay":source_history_prediction_replay["status"],
             "source_ood_rule_eligible_cases":warning["eligible_cases"], "source_ood_rule_groups":warning["eligible_groups"],
             "source_ood_warning_failure_recall":warning["warning"]["failure_recall"],
             "source_ood_equal_count_combined_errors":warning["matched_comparison"]["risk_plus_range_errors"],
             "source_ood_equal_count_score_errors":warning["matched_comparison"]["risk_only_matched_errors"],
             "source_ood_rule_audit":warning_audit["status"], "source_ood_margin_audit":warning_margin_audit["status"],
             "CAMELSH_count_screen_sites":camelsh_count["sites"],
             "CAMELSH_count_screen_four_confirmed_year_sites":camelsh_count["sites_four_confirmed_complete_count_years"],
             "CAMELSH_current_metadata_candidates":camelsh_current["metadata_candidates"],
             "limitation":"NZ, NEON, prior USGS and Reunion did not qualify; Nova Scotia quality and timezone remain unresolved; BC and Truckee are exploratory, and Truckee is one managed watershed with prior data contact and unknown estimated/corrected-value flags. No independent-climate validation or coverage guarantee is established."},
            {"item":"Data permissions and permanent reviewer access", "status":"pending_external_arrangements",
             "LUBW_specific_terms_review":lubw_terms_scope["status"],
             "LUBW_acquisition_and_metadata_terms_locator_match":lubw_terms_scope["actual_acquisition_landing_links_to_same_terms"],
             "LUBW_terms_body_live_status":lubw_terms_scope["terms_body_live_status"],
             "LUBW_redistribution_authorized_by_review":lubw_terms_scope["redistribution_authorized_by_this_review"],
             "whole_archive_source_model_combinations":archive_source_rights["model_mode_region_combinations"],
             "whole_archive_estimator_roles_with_lubw":archive_source_rights["estimator_combinations_with_lubw_positive_weight"],
             "whole_archive_calibration_roles_with_lubw":archive_source_rights["interval_calibration_combinations_with_lubw_positive_weight"],
             "open_source_sensitivity_pilot":open_source_pilot["status"],
             "open_source_pilot_archive_settings":open_source_pilot["archive_settings"],
             "open_source_case_input_integrity":open_source_inputs["status"],
             "open_source_completed_models":open_source_report["models"],
             "open_source_completed_archive_settings":open_source_report["archive_settings"],
             "open_source_role_audit":open_source_report["source_role_audit"],
             "open_source_independent_summary_audit":open_source_report["independent_summary_audit"],
             "candidate_donor_visibility_reconstructed":donor_provenance["donor_visibility_counts_match_saved_cases"],
             "candidate_donor_source_roles_checked":donor_provenance["roles_checked"],
             "current_usgs_donor_unambiguous_days_compared":donor_daily["compared_days"],
             "current_usgs_donor_daily_independent_audit":donor_daily_audit["status"],
             "LUBW_source_stations":20, "detail":"Source-specific UIS terms are linked by the provider metadata and acquisition landing; archived-export vintage and derivative applicability remain unconfirmed. Operational sharing hold and unsent clarification drafts remain; permanent deposit is unresolved."},
            {"item":"USGS qualifier-aware history and fixed-mask sensitivity", "status":"computed_posthoc_not_independent_validation",
             "history_audit":usgs_history_audit["status"], "targets":usgs_history_audit["targets"],
             "excluded_history_assignments":usgs_history_audit["history_assignments_removed"],
             "score_audit":usgs_score_audit["status"], "cases":usgs_score_audit["target_cases"],
             "prediction_replay":usgs_prediction_replay["status"],
             "limitation":"Raw ICE qualifiers and available history years change together. Repeated masks at one affected station do not establish independent climate transfer or physical sensor accuracy."},
            {"item":"Numerical endpoint comparison sensitivity", "status":"computed_on_saved_cases",
             "whole_archive_audit":numeric_archive["status"], "whole_archive_summary_cells":numeric_archive["summary_cells"],
             "source_audit":numeric_source["status"], "source_seed_summary_cells":numeric_source["seed_family_stratum_method_cells"],
             "limitation":"Numerical comparison tolerances are not measurement-error bounds; no new model or reference was fitted."},
            {"item":"Supporting-information format", "status":"publisher_named_class_locally_compiled" if si_format_current else "stale_format_audit",
             "class":"agutexSI2019", "official_download_status":"403; identical class blob obtained from two public mirrors",
             "format_audit_matches_current_files":si_format_current, "pages":si_format["pages"],
             "science_body_unchanged":si_format["science_body_unchanged"],
             "limitation":"Template use does not establish editorial acceptance or resolve pending author metadata."},
            {"item":"Current local review delivery", **bundle},
            {"item":"Author details and declarations", "status":"pending_user",
             "author_metadata_complete":bool(author.get("complete")), "detail":"user indicated author information is pending"},
            {"item":"Specified scientific tests", "status":"passed" if tests.returncode == 0 else "failed",
             "exit_code":tests.returncode,
             "passed_tests":sum(int(x) for x in re.findall(r"(?m)^=*\s*(\d+) passed\b", tests.stdout)),
             "evidence":"audit/test_output.txt"},
        ],
        "not_claimed": ["WRR acceptance", "universal 95% trend coverage", "safe group-level release", "complete independent validation", "complete open-data deposit"],
    }
    OUT.write_text(json.dumps(status, indent=2, default=str) + "\n")
    print(json.dumps(status, indent=2, default=str), flush=True)
    if tests.returncode:
        raise SystemExit(tests.returncode)

if __name__ == "__main__":
    main()
