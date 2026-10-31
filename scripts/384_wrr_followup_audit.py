#!/usr/bin/env python3
"""Check empirical closure separately from genuine future-data dependencies."""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
import yaml

import wrr_r3_common as C

RUN = C.READY / "followup_20261021"


def main():
    checks = []
    def check(name, condition):
        checks.append({"check": name, "passed": bool(condition)})
    for protocol in ("leave_one_year_out", "strictly_prior_years"):
        for seed in (101, 202, 303):
            operating = pd.read_csv(RUN / "factorial" / protocol / f"seed_{seed}/operating.csv")
            check(f"{protocol}_{seed}_four_cells", len(operating) == 8 and operating.arm.nunique() == 4)
            check(f"{protocol}_{seed}_no_zero_risk_for_reject_all", operating.loc[operating.accepted.eq(0), "risk"].isna().all())
        refits = pd.read_csv(RUN / "robustness" / protocol / "whole_procedure.csv")
        check(f"{protocol}_1000_full_refits", refits.repetition.nunique() == 1000 and len(refits) == 4000)
        costs = pd.read_csv(RUN / "external_cost" / protocol / "decision_costs.csv")
        counts = costs[["true_positive", "true_negative", "false_negative", "false_positive", "unknown"]].sum(axis=1)
        check(f"{protocol}_decision_denominators", np.allclose(counts, costs.n_candidates))
        history = pd.read_parquet(RUN / "history_boundaries" / protocol / "cases.parquet")
        check(f"{protocol}_shared_history_pool", history.groupby(["network_id", "station_id", "year", "design"]).history_years.nunique().eq(3).all())
        if protocol == "strictly_prior_years":
            check("history_future_excluded", (history.latest_training_year < history.year).all())
    quality = pd.read_csv(RUN / "evidence/trajectory_common_all.csv")
    check("trajectory_common_denominators", quality.groupby(["role", "draws"]).N.nunique().eq(1).all())
    system = pd.read_csv(RUN / "system_factorial/original_pool_costs.csv")
    system_counts = system[["true_positive", "true_negative", "false_negative", "false_positive", "unknown"]].sum(axis=1)
    check("system_unavailable_kept_in_original_denominator", np.allclose(system_counts, system.n_candidates) and system.n_candidates.nunique() == 1)
    probability = RUN / "probability_development"
    selection = json.loads((probability / "selection.json").read_text())
    validation = pd.read_csv(probability / "development_results.csv")
    check("probability_selection_uses_only_old_validation", not selection["new_external_test_outcomes_used"] and validation.n_groups.eq(30).all() and validation.n_candidates.eq(150).all() and validation.n_available.eq(150).all())
    membership = pd.read_csv(probability / "old_group_membership.csv")
    fitting_groups = set(membership.loc[membership.role.eq("training"), "group"])
    validation_groups = set(membership.loc[membership.role.eq("validation"), "group"])
    check("probability_old_fitting_validation_groups_disjoint", not fitting_groups.intersection(validation_groups))
    role_groups = {}
    for role in ("development", "calibration", "test"):
        frame = pd.read_parquet(probability / role / "cases.parquet")
        role_groups[role] = set(frame.independence_group)
        original = pd.read_parquet(C.RUN / "r3_08_external_recovery" / role / "leave_one_year_out/crossed/cofailure_0/cases.parquet")
        original = original.loc[original.replicate.eq(0) & original.design_family.eq("crossed_contiguous") & original.statistic_class.eq("daily_mean")]
        check(f"probability_{role}_full_pool_and_available_32_draw_distributions", len(frame) == len(original) and frame.loc[frame.available, "h30_samples_C"].map(lambda value: len(value) == 32 and np.isfinite(value).all()).all())
    if (probability / "parallel_backfill_contract.json").exists():
        scheduling = json.loads((probability / "parallel_backfill_contract.json").read_text())
        check("parallel_scheduling_canonical_sampler", not scheduling["model_or_statistical_budget_changed"])
    check("probability_external_roles_group_disjoint", all(not role_groups[a].intersection(role_groups[b]) for a, b in (("development", "calibration"), ("development", "test"), ("calibration", "test"))))
    developed = pd.read_csv(RUN / "system_factorial_developed/operating.csv")
    check("developed_system_nine_complete_cells", len(developed) == 9 and developed.method.nunique() == developed.score_kind.nunique() == 3 and developed.n_candidates.eq(945).all())
    check("developed_system_reject_all_risk_unestimated", developed.loc[developed.accepted.eq(0), "risk"].isna().all())
    developed_costs = pd.read_csv(RUN / "system_factorial_developed/decision_costs.csv")
    developed_counts = developed_costs[["true_positive", "true_negative", "false_negative", "false_positive", "unknown"]].sum(axis=1)
    check("developed_system_original_pool_decision_denominators", developed_costs.n_candidates.eq(945).all() and np.allclose(developed_counts, 945))
    direct = developed_costs.loc[developed_costs.policy.eq("direct_calibrated_NN_cost")]
    check("shared_distribution_cost_decision_independent_of_point", direct.groupby(["fn_cost", "abstention_cost"]).loss.nunique().eq(1).all())
    calibration_budget = pd.read_csv(RUN / "developed_calibration_budget/all_subsets.csv")
    calibration_summary = json.loads((RUN / "developed_calibration_budget/summary.json").read_text())
    check("developed_calibration_all_group_subsets", len(calibration_budget) == 741 and calibration_summary["distinct_subsets"] == 247 and calibration_summary["all_group_subsets_included"])
    check("developed_calibration_scores_and_full_budget_reproduce_original", calibration_summary["fixed_scores_match_original"] and calibration_summary["full_budget_reproduces_original"])
    check("developed_calibration_empty_risk_unestimated", calibration_budget.loc[calibration_budget.accepted.eq(0), "risk"].isna().all() and calibration_budget.formal_accepted.eq(0).all())
    check("developed_calibration_original_test_denominator", calibration_budget.n_candidates.eq(945).all() and np.allclose(calibration_budget[["true_positive", "true_negative", "false_positive", "false_negative", "unknown"]].sum(axis=1), 945))
    planning = pd.read_csv(RUN / "joint_power/joint_power_familywise_MC.csv")
    plan_decision = json.loads((RUN / "joint_power/final_sampling_decision.json").read_text())
    check("joint_power_full_refits_and_grid", plan_decision["source_like_complete_refits"] == 3000 and plan_decision["paired_model_fits"] == 6000 and len(planning) == 336 and planning.repetitions.eq(1000).all())
    check("joint_power_no_unsupported_recruitment_recommendation", plan_decision["recommended_recruitment_sample_size"] is None and not plan_decision["supported_80_percent_plans"] and (planning.mc_family_upper < .8).all())
    three_method = RUN / "three_method_joint_power"
    three_decision = json.loads((three_method / "decision_all.json").read_text())
    three_power = pd.read_csv(three_method / "power_all.csv")
    three_evidence = json.loads((three_method / "evidence_summary.json").read_text())
    check("three_method_complete_refits_and_budget_cells", three_decision["complete_prespecified_run"] and three_decision["completed_paired_head_refits"] == 3000 and len(three_power) == three_evidence["budget_cells"] == 432 and three_power.repetitions.eq(1000).all())
    check("three_method_planning_not_new_confirmation_or_recommended_N", three_decision["recommended_new_target_recruitment_N"] is None and not three_evidence["new_independent_confirmation_completed"] and three_decision["simulated_group_budgets_are_not_acquired_units"])
    dependence = RUN / "au_dependence_audit"
    dependence_summary = json.loads((dependence / "summary.json").read_text())
    dependence_evidence = json.loads((dependence / "evidence_summary.json").read_text())
    check("new_reference_original_qualification_and_roles_preserved", dependence_evidence["all_passed"] and dependence_summary["original_qualified_reference_station_years"] == dependence_evidence["same_qualified_station_years"] == 80 and not dependence_summary["original_role_and_qualification_files_modified"])
    check("new_reference_unresolved_and_cross_role_blocks_explicit", dependence_summary["qualified_reference_stations_pending_topology"] == 1 and dependence_summary["qualified_reference_blocks_spanning_original_roles"] == 6 and dependence_summary["qualified_references_in_role_counts_can_share_blocks"])
    check("new_reference_topology_not_claimed_event_independence", not dependence_summary["region_event_dependence_verified"] and not dependence_summary["earlier_opened_record_exclusion_fully_verified"] and dependence_summary["basin_connectivity_does_not_alone_prove_record_leakage"])
    check("new_reference_primary_error_gate_remains_closed", not dependence_summary["primary_test_error_access_allowed"] and not dependence_summary["new_temperature_values_or_H30_prediction_errors_opened"] and not dependence_summary["new_confirmation_completed"])
    backup = RUN / "natural_backup"
    qualification = json.loads((backup / "qualification_summary.json").read_text())
    check("natural_reference_unchanged_original_support_empty", qualification["n_pair_year_candidates"] == 180 and qualification["n_qualified_pair_years"] == 0)
    preparation = json.loads((backup / "short_history/preparation.json").read_text())
    check("natural_sensitivity_no_backup_as_model_input_or_artificial_cost", not preparation["backup_values_in_model_input"] and preparation["NASA_forcing_is_free_input_not_costly_query"] and not preparation["primary_support_relaxed"])
    gaps = pd.read_csv(backup / "short_history/gap_sampling_audit.csv")
    check("natural_sensitivity_partial_daily_sampling_reported", len(gaps) == 4 and gaps.distinct_hours.between(8, 19).all())
    for method in ("linear_interp", "air2stream3", "csdi_old", "csdi_developed"):
        short = pd.read_csv(backup / "short_history" / f"{method}_results.csv")
        check(f"natural_{method}_three_references_two_primary_years", len(short) == 3 and short.input_id.nunique() == 2)
    specification = yaml.safe_load((C.ROOT / "configs/wrr_next_confirmation_20261021.yaml").read_text())
    check("next_study_requires_joint_success", len(specification["joint_success"]) == 4 and specification["primary_use"] == "deliver_annual_H30_magnitude_in_archive")
    check("next_study_includes_both_strong_direct_references", len(specification["direct_reference_family"]) == 2 and "native_conditional_CDF_tolerance_exceedance_probability" in specification["direct_reference_family"] and "against_each_direct_reference" in specification["joint_success"][1])
    allocation = specification["joint_error_allocation"]
    allocated = allocation["methods"] * (allocation["formal_calibration_per_method"] + allocation["evaluation_risk_per_method"]) + allocation["direct_references"] * allocation["paired_gain_per_direct_reference"]
    check("next_study_three_methods_two_comparisons_share_alpha", allocation["methods"] == 3 and allocation["direct_references"] == 2 and np.isclose(allocated, specification["familywise_alpha"]) and not specification["sample_size"]["current_source_planning"]["covers_new_two_reference_joint_procedure"])
    state = RUN / "state_risk_completion"
    state_checks = pd.read_csv(state / "evidence/checks.csv")
    state_fixed = pd.read_csv(state / "factorial/operating.csv")
    state_system = pd.read_csv(state / "system_factorial/operating.csv")
    check("conditional_law_21_and_system_42_cells_retain_original_pool_and_formal_limit", len(state_checks) == 8 and state_checks.passed.all() and len(state_fixed) == 21 and len(state_system) == 42 and state_fixed.n_candidates.eq(945).all() and state_system.n_candidates.eq(945).all() and state_fixed.formal_accepted.eq(0).all() and state_system.formal_accepted.eq(0).all())
    main_text = (C.ROOT / "paper/wrr/wrr_manuscript.tex").read_text()
    check("three_claim_table_linked", "r4_claim_table.tex" in main_text)
    new_text = (C.ROOT / "paper/wrr/r4_results.tex").read_text()
    check("supplementary_status_explicit", "opened data" in new_text and "not" in new_text)
    build = json.loads((C.ROOT / "paper/wrr/build_report.json").read_text())
    check("paper_build_checks", not build["checks_failed"])
    ledger = [
        (1, "Three claims and primary archive use", "executed", "paper/wrr/r4_claim_table.tex"),
        (2, "Four-cell objective/window comparison", "executed", "factorial; robustness"),
        (3, "Use-matched and deterministic/random decision references", "executed", "external_cost"),
        (4, "Concentrated failure, channel loss and common mechanisms", "executed", "transfer; information_calibration; mechanism"),
        (5, "Primary use and meaningful joint endpoint", "specified", "configs/wrr_next_confirmation_20261021.yaml"),
        (6, "Visible-state target-risk candidate", "conditional_laws_and_32_128_512_draw_quality_executed_opened_data", "trajectory; state_risk_completion/factorial; state_risk_completion/evidence; no new independent confirmation"),
        (7, "Real costly data acquisition", "inactive_no_real_costly_action_user_reports_no_material", "public free backups incorporated; no artificial query costs"),
        (8, "Reconstruction/admission/decision factorial", "executed_old_only_probability_and_conditional_law_own_error_systems", "system_factorial; probability_development; system_factorial_developed; state_risk_completion/system_factorial: 24 air and 18 separate flow cells"),
        (9, "Artificial, calendar and independently backed natural gaps", "artificial_calendar_executed_original_support_backed_natural_validation_unfulfilled", "history_boundaries; original calendar replay; natural_backup; cross-sensor hourly coverage upper bound two prior years; public_backup_search; additional_public_source_scope; two winter partial-sampling years only"),
        (10, "Independent new deployment sample and planning", "old_role_planning_and_metadata_intake_executed_independent_new_cohort_unfinished", "joint_power; three_method_joint_power; developed_calibration_budget; au_confirmation; au_dependence_audit; usgs_intake_evidence; reference_pool_feasibility; new-population and verified-process evidence still needed"),
        (11, "Joint success and trajectory-quality criteria", "joint_rules_old_role_simulation_and_conditional_quality_executed_new_confirmation_not_executed", "robustness; trajectory; state_risk_completion/evidence; three_method_joint_power; prospective specification"),
        (12, "Stopping and claim selection", "current_superiority_not_established_future_rule_specified", "main discussion; prospective specification"),
    ]
    destination = RUN / "completion"
    destination.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(ledger, columns=["step", "requirement", "status", "evidence"]).to_csv(destination / "requirement_ledger.csv", index=False)
    pd.DataFrame(checks).to_csv(destination / "checks.csv", index=False)
    failures = [item["check"] for item in checks if not item["passed"]]
    C.write_json(destination / "summary.json", {"current_revision_checks_pass": not failures, "failed_checks": failures,
                 "new_independent_confirmation_completed": False, "real_backup_gap_validation_completed": False,
                 "costly_information_acquisition_experiment_completed": False,
                 "developed_probability_reference_completed": True, "source_like_joint_planning_completed": True,
                 "old_role_three_method_joint_planning_completed": True,
                 "new_reference_quality_qualification_completed": True,
                 "conservative_hydrologic_dependence_screen_completed": True,
                 "opened_data_conditional_law_and_complete_system_comparisons_completed": True,
                 "conditional_law_fixed_point_cells": 21, "conditional_law_own_error_system_cells": 42,
                 "conditional_law_formal_admissions_all_empty": True,
                 "new_reference_region_event_independence_verified": False,
                 "short_history_cold_partial_sampling_sensitivity_completed": True,
                 "user_reports_additional_backup_or_costly_material_available": False,
                 "interpretation": "supplements, developed probability, paired and three-method old-role planning, public-backup qualification and new-reference topology screen executed; no original-support natural case or independent new confirmation supplied"})
    print(f"[384] {len(checks)} checks; failures={failures}; future-data dependencies remain explicit", flush=True)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
