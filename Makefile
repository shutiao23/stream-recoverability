PYTHON ?= python
export PYTHONPATH := $(CURDIR)/src$(if $(PYTHONPATH),:$(PYTHONPATH))

WORKERS ?= 16
REPLICATES ?= 20
ANNUAL_WORKERS ?= 3
REVIEW_RESPONSE := results/wrr_review_response_20261027
.PHONY: review-open-observed-reproduction review-usgs-observed-reproduction review review-archive review-annual review-annual-interval-expansion review-release review-stress review-integrated review-independent review-report review-test review-bundle review-figures-from-summaries review-package-check review-bc-audit review-nechako-qualification review-poudre-qualification review-nova-portal-completeness review-nova-exploratory-audit review-nova-clock-audit review-local-case-evidence review-local-case-audit review-private-annual-evidence review-private-annual-audit review-projection-stage-replay review-peak-visibility review-peak-visibility-local-audit review-observed-audit

review:
	$(MAKE) review-archive
	$(MAKE) review-annual
	$(MAKE) review-release
	$(MAKE) review-stress
	$(MAKE) review-integrated
	$(MAKE) review-independent
	$(MAKE) review-observed-audit
	$(MAKE) review-report
	$(MAKE) review-bundle
	$(MAKE) review-package-check

review-archive:
	$(PYTHON) scripts/521_whole_archive.py --workers $(WORKERS) --replicates $(REPLICATES) --reanalyze --output $(REVIEW_RESPONSE)/whole_archive
	$(PYTHON) scripts/521_whole_archive.py --modes calibration --workers $(WORKERS) --replicates $(REPLICATES) --resume --output $(REVIEW_RESPONSE)/whole_archive
	$(PYTHON) scripts/523_trend_calibration.py --output $(REVIEW_RESPONSE)/whole_archive
	$(PYTHON) scripts/527_review_response_robustness.py
	$(PYTHON) scripts/562_support_projection_diagnostics.py
	$(MAKE) review-projection-stage-replay
	$(MAKE) review-peak-visibility
	$(MAKE) review-annual-interval-expansion
	$(PYTHON) scripts/593_nova_scotia_prior_contact_audit.py

review-annual:
	$(PYTHON) scripts/528_review_response_annual.py --workers $(ANNUAL_WORKERS)

review-annual-interval-expansion:
	$(PYTHON) scripts/581_source_annual_interval_expansion.py

review-release:
	$(PYTHON) scripts/522_release_outputs.py --workers $(WORKERS) --reuse-quality results/release_outputs --output $(REVIEW_RESPONSE)/release_outputs
	$(PYTHON) scripts/556_release_matched_retention.py
	$(PYTHON) scripts/558_source_calibrated_release.py
	$(PYTHON) scripts/559_source_calibrated_audit.py
	$(PYTHON) scripts/560_release_regional_sensitivity.py

review-stress:
	$(PYTHON) scripts/526_review_response_rules.py
	$(PYTHON) scripts/521_whole_archive.py --scenario synchronized_donors --workers $(WORKERS) --replicates 5 --limit-stations 7 --reanalyze --output $(REVIEW_RESPONSE)/scenario_donors
	$(PYTHON) scripts/521_whole_archive.py --scenario heat_associated --workers $(WORKERS) --replicates 5 --limit-stations 7 --reanalyze --output $(REVIEW_RESPONSE)/scenario_heat
	$(PYTHON) scripts/531_scenario_comparison.py

review-integrated:
	$(PYTHON) scripts/532_integrated_release_trend.py --workers $(WORKERS)
	$(PYTHON) scripts/534_integrated_release_comparison.py
	$(PYTHON) scripts/539_quality_availability_sensitivity.py
	$(PYTHON) scripts/533_review_response_audit.py

review-independent:
	$(PYTHON) scripts/472_review_completion_prereg.py
	$(PYTHON) scripts/496_review_completion_independent_acquisition.py --acquire
	$(PYTHON) scripts/497_review_completion_independent_cases.py --prepare-cases --workers $(WORKERS) --resume
	$(PYTHON) scripts/495_review_completion_independent_analysis.py --cases results/wrr_review_completion_20261024/independent_study/acquired/cases.parquet --output results/wrr_review_completion_20261024/independent_study/evaluation
	$(PYTHON) scripts/525_external_observed_records.py
	$(PYTHON) scripts/529_neon_reference_qualification.py
	$(PYTHON) scripts/530_new_usgs_reference.py
	$(PYTHON) scripts/535_prior_contact_audit.py
	$(PYTHON) scripts/540_hubeau_reunion_reference.py
	$(PYTHON) scripts/541_hubeau_reunion_score.py
	$(PYTHON) scripts/543_bc_reference_qualification.py
	$(PYTHON) scripts/544_bc_exploratory_score.py
	$(MAKE) review-bc-audit
	$(PYTHON) scripts/545_bc_score_summary.py
	$(PYTHON) scripts/546_bc_prior_contact_audit.py
	$(PYTHON) scripts/547_usgs_metadata_count_roster.py
	$(PYTHON) scripts/548_usgs_approved_count_preflight.py
	$(PYTHON) scripts/549_nve_public_metadata_screen.py
	$(PYTHON) scripts/550_nve_chart_reference_probe.py
	$(PYTHON) scripts/564_eccc_red_reference_plan.py
	$(PYTHON) scripts/565_eccc_red_qualification.py
	$(PYTHON) scripts/566_eccc_opened_cache_screen.py

review-observed-audit:
	$(PYTHON) scripts/570_reaudit_observed_records.py
	$(PYTHON) scripts/574_input_panel_precision_audit.py
	$(PYTHON) scripts/571_reaudit_screening_rules.py
	$(PYTHON) scripts/572_reaudit_usgs_witnesses.py

review-local-case-evidence:
	$(PYTHON) scripts/568_prepare_private_case_evidence.py
	$(MAKE) review-local-case-audit

review-local-case-audit:
	$(PYTHON) scripts/569_verify_private_case_evidence.py

.PHONY: review-isolated-local-evidence
review-isolated-local-evidence:
	$(PYTHON) scripts/727_isolated_review_evidence_check.py

.PHONY: review-isolated-groupmax
review-isolated-groupmax:
	$(PYTHON) scripts/728_isolated_groupmax_check.py

.PHONY: review-heat-gap-source-replay review-heat-gap-source-audit
review-heat-gap-source-replay:
	$(PYTHON) scripts/742_heat_gap_source_sensitivity.py run --workers 1
	$(MAKE) review-heat-gap-source-audit

review-heat-gap-source-audit:
	$(PYTHON) scripts/743_heat_gap_source_compare.py
	$(PYTHON) scripts/744_heat_gap_source_independent_audit.py
	$(PYTHON) scripts/746_heat_gap_source_interactions.py
	$(PYTHON) scripts/747_heat_gap_interaction_audit.py
	$(PYTHON) scripts/748_heat_gap_interaction_influence.py
	$(PYTHON) scripts/749_heat_gap_interaction_influence_audit.py
	$(PYTHON) scripts/745_heat_gap_source_report.py

.PHONY: review-nova-field-audit
review-nova-field-audit:
	$(PYTHON) scripts/750_nova_field_source.py acquire
	$(PYTHON) scripts/753_nova_field_range_check.py
	$(PYTHON) scripts/755_nova_field_hour_membership.py
	$(PYTHON) scripts/756_nova_field_independent_audit.py
	$(PYTHON) scripts/757_nova_field_report.py

.PHONY: review-isolated-nova-field
review-isolated-nova-field:
	$(PYTHON) scripts/758_nova_field_cleanroom.py

.PHONY: review-beaufort-proxy-open-replay
review-beaufort-proxy-open-replay:
	$(PYTHON) scripts/767_beaufort_proxy_open_replay.py

.PHONY: review-summer-proxy-archive-audit
review-summer-proxy-archive-audit:
	$(PYTHON) scripts/770_summer_proxy_archive_analysis.py
	$(PYTHON) scripts/771_summer_proxy_independent_audit.py
	$(PYTHON) scripts/772_summer_proxy_archive_report.py

.PHONY: review-donor-provenance-local review-donor-usgs-snapshot
review-donor-provenance-local:
	$(PYTHON) scripts/773_candidate_donor_provenance.py run
	$(PYTHON) scripts/774_candidate_donor_provenance_audit.py
	$(PYTHON) scripts/776_donor_metadata_independent_audit.py
	$(PYTHON) scripts/779_usgs_donor_daily_comparison.py compare
	$(PYTHON) scripts/780_usgs_donor_daily_audit.py
	$(PYTHON) scripts/781_usgs_donor_ambiguous_dates.py run
	$(PYTHON) scripts/782_usgs_ambiguity_independent_audit.py

review-donor-usgs-snapshot:
	$(PYTHON) scripts/778_donor_usgs_snapshot_replay.py
	$(PYTHON) scripts/784_usgs_donor_daily_snapshot_replay.py

.PHONY: review-truckee-open-reference review-truckee-peak-local review-truckee-wqp-local
.PHONY: review-usace-open-reference
.PHONY: review-source-partial-history-reference
review-source-partial-history-reference:
	$(PYTHON) scripts/854_source_history_open_reference_replay.py

review-usace-open-reference:
	$(PYTHON) scripts/829_usace_open_reference_replay.py
	$(PYTHON) scripts/834_usace_bounds_open_replay.py
	$(PYTHON) scripts/847_usace_partial_power_replay.py

review-truckee-open-reference:
	$(PYTHON) scripts/805_truckee_open_reference_replay.py
	$(PYTHON) scripts/812_truckee_power_time_open_replay.py
	$(PYTHON) scripts/818_truckee_wqp_open_replay.py

review-truckee-peak-local:
	$(PYTHON) scripts/807_truckee_peak_visibility.py run
	$(PYTHON) scripts/808_truckee_peak_visibility_audit.py

review-truckee-wqp-local:
	$(PYTHON) scripts/816_truckee_wqp_field_audit.py audit

review-private-annual-evidence:
	$(PYTHON) scripts/575_export_private_annual_predictions.py --resume --workers 2
	$(MAKE) review-private-annual-audit

review-private-annual-audit:
	$(PYTHON) scripts/576_verify_private_annual_predictions.py

review-projection-stage-replay:
	$(PYTHON) scripts/577_replay_annual_projection_stages.py

review-peak-visibility:
	$(PYTHON) scripts/578_peak_visibility_diagnostics.py --workspace

review-peak-visibility-local-audit:
	$(PYTHON) scripts/580_verify_peak_visibility_case_subset.py

review-bc-audit:
	$(PYTHON) scripts/554_bc_reference_integrity.py
	$(PYTHON) scripts/555_bc_hidden_value_audit.py

review-nechako-qualification:
	$(PYTHON) scripts/585_nechako_reference_qualification.py qualify
	$(PYTHON) scripts/586_nechako_reference_report.py

review-poudre-qualification:
	$(PYTHON) scripts/587_poudre_metadata_preflight.py qualify
	$(PYTHON) scripts/588_poudre_reference_report.py

review-nova-portal-completeness:
	$(PYTHON) scripts/590_nova_scotia_portal_audit.py portal_completeness

review-nova-exploratory-audit:
	$(PYTHON) scripts/599_nova_scotia_exploratory_integrity.py

review-nova-clock-audit:
	$(PYTHON) scripts/606_nova_clock_sensitivity_integrity.py

review-open-observed-reproduction:
	$(PYTHON) scripts/654_verify_open_observed_snapshot.py

review-usgs-observed-reproduction:
	$(PYTHON) scripts/652_verify_usgs_observed_reproduction.py

review-package-check:
	$(PYTHON) scripts/553_verify_review_package.py

.PHONY: review-delivery-check
review-delivery-check:
	$(PYTHON) scripts/930_delivery_consistency.py --archive dist/wrr_review_response_candidate.zip

.PHONY: review-process-revision review-process-revision-check review-process-revision-package-check review-current-observation-replay
review-process-revision:
	$(PYTHON) scripts/960_process_region_identification.py
	$(PYTHON) scripts/961_process_time_support.py
	$(PYTHON) scripts/964_process_gap_and_archive.py
	$(PYTHON) scripts/process_review_water_air.py
	$(PYTHON) scripts/962_process_trajectory_budget.py --replay
	$(PYTHON) scripts/963_process_revision_report.py
	$(PYTHON) scripts/970_process_experiment_report.py
	$(PYTHON) scripts/524_research_report.py
	$(PYTHON) scripts/929_manuscript_inputs.py
	cd paper/wrr_tr && TEXINPUTS=.:../wrr/template: latexmk -pdf -silent -interaction=nonstopmode -halt-on-error review_completion_article.tex
	cd paper/wrr_tr && TEXINPUTS=.:../wrr/template: latexmk -pdf -silent -interaction=nonstopmode -halt-on-error review_completion_supporting.tex

review-process-revision-check:
	$(PYTHON) scripts/965_process_revision_audit.py
	$(PYTHON) -m pytest tests/test_wrr_process_revision.py tests/test_wrr_trajectory_revision.py tests/test_wrr_process_time_gap_revision.py tests/test_process_review_region_water.py tests/test_current_observation_replay.py tests/test_review_manuscript_structure.py tests/test_review_bundle_atomic_write.py tests/test_review_completion_current_evidence.py
	$(PYTHON) scripts/930_delivery_consistency.py

review-current-observation-replay:
	$(PYTHON) scripts/967_current_observation_replay.py prepare
	$(PYTHON) scripts/967_current_observation_replay.py replay

review-process-revision-package-check:
	$(PYTHON) scripts/966_process_revision_delivery.py

.PHONY: review-process-experiments review-process-experiments-check review-process-experiments-package-check
review-process-experiments:
	$(PYTHON) scripts/960_process_region_identification.py --output results/wrr_process_experiments_20261029/region_water/regenerated --paper results/wrr_process_experiments_20261029/region_water/tex
	$(PYTHON) scripts/process_review_water_air.py --output results/wrr_process_experiments_20261029/region_water/regenerated --paper results/wrr_process_experiments_20261029/region_water/tex
	$(PYTHON) scripts/audit_region_water_experiments.py
	$(PYTHON) scripts/968_process_source_calibration.py --stage full --workers 2 --resume
	$(PYTHON) scripts/969_time_gap_sensitivity.py
	$(PYTHON) scripts/981_stanford_revision.py
	$(PYTHON) scripts/971_independent_calibration_audit.py
	$(PYTHON) scripts/974_independent_time_gap_audit.py
	$(PYTHON) scripts/975_replay_source_calibration.py --freeze-inputs --check-isolated
	$(PYTHON) scripts/977_replay_time_support.py --freeze-inputs --check-isolated
	$(PYTHON) scripts/963_process_revision_report.py
	$(PYTHON) scripts/929_manuscript_inputs.py
	$(PYTHON) scripts/979_crps_grid_sensitivity.py
	$(PYTHON) scripts/970_process_experiment_report.py
	$(PYTHON) scripts/972_experiment_data_catalog.py
	cd paper/wrr_tr && TEXINPUTS=.:../wrr/template: latexmk -pdf -silent -interaction=nonstopmode -halt-on-error review_completion_article.tex
	cd paper/wrr_tr && TEXINPUTS=.:../wrr/template: latexmk -pdf -silent -interaction=nonstopmode -halt-on-error review_completion_supporting.tex

review-process-experiments-check:
	$(PYTHON) scripts/971_independent_calibration_audit.py
	$(PYTHON) scripts/974_independent_time_gap_audit.py
	$(PYTHON) scripts/976_calibration_leakage_probe.py
	$(PYTHON) -m pytest tests/test_wrr_source_trajectory_calibration.py tests/test_independent_calibration_audit.py tests/test_process_time_gap_sensitivity.py tests/test_region_water_adversarial.py tests/test_experiment_data_catalog.py tests/test_process_experiment_delivery.py tests/test_wrr_process_revision.py tests/test_review_manuscript_structure.py tests/test_stanford_revision.py tests/test_final_release_freshness.py
	$(PYTHON) scripts/930_delivery_consistency.py

review-process-experiments-package-check:
	$(PYTHON) scripts/978_process_experiment_delivery.py

.PHONY: review-final-tests
review-final-tests:
	$(PYTHON) scripts/982_final_release_tests.py

.PHONY: review-extension-replay
review-extension-replay:
	$(PYTHON) scripts/983_verify_extension_replay.py

review-figures-from-summaries:
	$(PYTHON) scripts/552_recreate_aggregate_figures.py

.PHONY: review-summer-snapshot
review-summer-snapshot:
	$(PYTHON) scripts/712_verify_summer_snapshot.py

.PHONY: review-past-season-snapshot
review-past-season-snapshot:
	$(PYTHON) scripts/718_verify_past_season_snapshot.py

review-report:
	$(PYTHON) scripts/726_groupmax_annual_trend_report.py
	$(PYTHON) scripts/717_past_season_report.py
	$(PYTHON) scripts/711_summer_window_report.py
	$(PYTHON) scripts/765_beaufort_proxy_report.py
	$(PYTHON) scripts/772_summer_proxy_archive_report.py
	$(PYTHON) scripts/806_truckee_exploratory_report.py
	$(PYTHON) scripts/704_projected_risk_report.py
	$(PYTHON) scripts/698_stress_source_report.py
	$(PYTHON) scripts/693_expanded_stress_report.py
	$(PYTHON) scripts/741_heat_gap_matched_report.py
	$(PYTHON) scripts/745_heat_gap_source_report.py
	$(PYTHON) scripts/687_archive_matched_release_report.py
	$(PYTHON) scripts/680_focused_supporting_tables.py
	$(PYTHON) scripts/679_single_year_trend_report.py
	$(PYTHON) scripts/675_single_year_calibration_report.py
	$(PYTHON) scripts/670_open_source_annual_report.py
	$(PYTHON) scripts/664_open_source_sensitivity_report.py
	$(PYTHON) scripts/659_archive_source_rights_report.py
	$(PYTHON) scripts/651_usgs_late_start_report.py
	$(PYTHON) scripts/648_au_prior_exposure_report.py
	$(PYTHON) scripts/644_njdep_report.py
	$(PYTHON) scripts/611_region_holdout_report.py
	$(PYTHON) scripts/615_strict_region_report.py
	$(PYTHON) scripts/542_uncertainty_paired_diagnostics.py
	$(PYTHON) scripts/563_support_projection_report.py
	$(PYTHON) scripts/579_peak_visibility_report.py
	$(PYTHON) scripts/582_source_annual_interval_report.py
	$(PYTHON) scripts/584_usgs_unresolved_count_report.py
	$(PYTHON) scripts/586_nechako_reference_report.py
	$(PYTHON) scripts/588_poudre_reference_report.py
	$(PYTHON) scripts/592_nova_scotia_reference_report.py
	$(PYTHON) scripts/602_nova_scotia_exploratory_report.py
	$(PYTHON) scripts/757_nova_field_report.py
	$(PYTHON) scripts/608_nova_clock_sensitivity_report.py
	$(PYTHON) scripts/567_eccc_red_report.py
	$(PYTHON) scripts/573_observed_reaudit_report.py
	$(PYTHON) scripts/557_release_matched_report.py
	$(PYTHON) scripts/561_release_regional_report.py
	$(PYTHON) scripts/545_bc_score_summary.py
	dot -Tpdf paper/wrr_tr/figures/architecture/fig1_evidence_actual.dot -o paper/wrr_tr/figures/architecture/fig1_evidence_actual.pdf
	dot -Tpdf paper/wrr_tr/figures/architecture/fig2_release_actual.dot -o paper/wrr_tr/figures/architecture/fig2_release_actual.pdf
	$(PYTHON) scripts/960_process_region_identification.py
	$(PYTHON) scripts/961_process_time_support.py
	$(PYTHON) scripts/962_process_trajectory_budget.py
	$(PYTHON) scripts/964_process_gap_and_archive.py
	$(PYTHON) scripts/963_process_revision_report.py
	$(PYTHON) scripts/524_research_report.py
	cd paper/wrr_tr && TEXINPUTS=.:../wrr/template: latexmk -pdf -silent -interaction=nonstopmode -halt-on-error review_completion_article.tex
	cd paper/wrr_tr && TEXINPUTS=.:../wrr/template: latexmk -pdf -silent -interaction=nonstopmode -halt-on-error review_completion_supporting.tex

review-bundle:
	$(PYTHON) scripts/537_prepare_source_rights.py
	$(PYTHON) scripts/536_prepare_review_bundle.py
	$(PYTHON) scripts/538_completion_audit.py

review-test:
	$(PYTHON) -m pytest tests/test_wrr_source_trajectory_calibration.py tests/test_independent_calibration_audit.py tests/test_process_time_gap_sensitivity.py tests/test_region_water_adversarial.py tests/test_experiment_data_catalog.py tests/test_process_experiment_delivery.py
	$(PYTHON) -m pytest tests/test_wrr_process_revision.py tests/test_wrr_trajectory_revision.py tests/test_wrr_process_time_gap_revision.py tests/test_process_review_region_water.py tests/test_current_observation_replay.py
	$(PYTHON) -m pytest tests/test_review_bundle_atomic_write.py
	$(PYTHON) -m pytest tests/test_review_completion_current_evidence.py
	$(PYTHON) -m pytest tests/test_usace_open_reference_replay.py
	$(PYTHON) -m pytest tests/test_usace_partial_year_h30_bounds.py
	$(PYTHON) -m pytest tests/test_usace_partial_history_scores.py
	$(PYTHON) -m pytest tests/test_usace_partial_history_engine.py
	$(PYTHON) -m pytest tests/test_source_partial_history_factorial.py
	$(PYTHON) -m pytest tests/test_partial_history_feature_support.py
	$(PYTHON) -m pytest tests/test_source_support_rule_evaluation.py
	$(PYTHON) -m pytest tests/test_usgs_partial_daily_feasibility.py
	$(PYTHON) -m pytest tests/test_usgs_partial_power_status.py
	$(PYTHON) -m pytest tests/test_usgs_public_snapshot_manifest.py
	$(PYTHON) -m pytest tests/test_usgs_subdaily_measurement_bounds.py
	$(PYTHON) -m pytest tests/test_isolated_groupmax_review.py
	$(PYTHON) -m pytest tests/test_isolated_review_evidence.py
	$(PYTHON) -m pytest tests/test_groupmax_annual_calibration.py
	$(PYTHON) -m pytest tests/test_past_season_screening.py
	$(PYTHON) -m pytest tests/test_summer_window_comparison.py
	$(PYTHON) -m pytest tests/test_projected_risk_sensitivity.py
	$(PYTHON) -m pytest tests/test_stress_source_common_cohort.py
	$(PYTHON) -m pytest tests/test_matched_heat_stress.py
	$(PYTHON) -m pytest tests/test_archive_matched_release_trend.py
	$(PYTHON) -m pytest tests/test_nz_quality_bound.py
	$(PYTHON) -m pytest tests/test_heat_gap_matched.py
	$(PYTHON) -m pytest tests/test_heat_gap_source_common.py
	$(PYTHON) -m pytest tests/test_nova_field_range_check.py
	$(PYTHON) -m pytest tests/test_nova_field_cleanroom.py
	$(PYTHON) -m pytest tests/test_beaufort_proxy.py
	$(PYTHON) -m pytest tests/test_archive_summer_proxy.py
	$(PYTHON) -m pytest tests/test_candidate_donor_provenance.py
	$(PYTHON) -m pytest tests/test_camelsh_metadata_screen.py
	$(PYTHON) -m pytest tests/test_truckee_wqp_pairing.py
	$(PYTHON) -m pytest tests/test_annual_bridge_dependencies.py
	$(PYTHON) -m pytest tests/test_review_manuscript_structure.py tests/test_single_year_trend_audit.py tests/test_single_year_trend_propagation.py tests/test_single_year_source_calibration.py tests/test_open_source_annual_scores.py tests/test_open_source_archive_summary.py tests/test_open_source_archive_sensitivity.py tests/test_open_observed_snapshot.py tests/test_usgs_observed_snapshot.py tests/test_wrr_usgs_late_start_counts.py tests/test_au_prior_exposure.py tests/test_njdep_metadata_preflight.py tests/test_rivtemp_date_upper_bound.py tests/test_andrews_source_overlap_audit.py tests/test_strict_region_holdout.py tests/test_nova_clock_sensitivity_reference.py tests/test_nova_clock_sensitivity_score.py tests/test_nova_scotia_exploratory_score.py tests/test_nova_scotia_location_audit.py tests/test_nova_scotia_label_completeness.py tests/test_nova_scotia_portal_comparison.py tests/test_poudre_metadata_preflight.py tests/test_nechako_reference_qualification.py tests/test_usgs_unresolved_network_count_screen.py tests/test_source_annual_interval_expansion.py tests/test_peak_visibility_diagnostics.py tests/test_projection_stage_replay.py tests/test_private_annual_score.py tests/test_whole_archive.py tests/test_release_outputs.py tests/test_integrated_release_trend.py tests/test_hubeau_reunion_reference.py tests/test_uncertainty_paired_diagnostics.py tests/test_bc_reference_qualification.py tests/test_bc_reference_integrity.py tests/test_release_matched_retention.py tests/test_source_calibrated_release.py tests/test_release_regional_sensitivity.py tests/test_support_projection_diagnostics.py tests/test_eccc_red_qualification.py tests/test_eccc_opened_cache_screen.py tests/test_private_case_audit.py tests/test_observed_record_reaudit.py tests/test_screening_rule_reaudit.py tests/test_usgs_observed_reaudit.py tests/test_input_panel_precision_audit.py tests/test_usgs_approved_count_preflight.py tests/test_nve_chart_reference_probe.py tests/test_external_observed_records.py tests/test_wrr_review_completion.py tests/test_wrr_target_recovery.py tests/test_wrr_review_independent.py tests/test_wrr_review_national.py tests/test_wrr_review_windows.py tests/test_wrr_review_forcing_evidence.py tests/test_wrr_forcing_residual_history.py tests/test_wrr_national_coverage.py

.PHONY: test development-v11 development-v11-inventory development-v11-candidates development-v11-score development-v11-mixed development-v11-confirm development-v11-stratify development-v11-triage development-v11-plots development-v11-reviewer-completion development-v11-recurrent-sensitivity development-v11-process-sensitivity development-v11-matched-outage validate-development-v11-reviewer-completion goal-completion-audit second-confirmation-candidates second-confirmation-nve second-confirmation-canada-audit second-confirmation-readiness second-confirmation-score confirmation-daily-qc ehyd-source-audit rws-daily-qc arso-daily-qc evidence-snapshot hosting-audit submission-gate blueprint-audit p0-protocol reproduce-paper reproduce-paper-full validate-review-revision research-charter recoverability-framework check-public-rivers download-build-rivers download-catalog-v2 catalog-v3-huc8 score-natural-outages gap-triage v2-operator-ablation w2-phase4-gap-specific hubeau-daily uk-ea-catalog uk-ea-daily uk-ea-spatial matched-regulation public-confirmatory-lock ingest-qc-clearwater national-temperature-catalog reservoir-operations-check apply-catalog-clusters
.PHONY: second-confirmation-placement second-confirmation-finalize development-v11-lstm-sensitivity development-v11-us-heterogeneity independent-air2stream-equivalent

test:
	$(PYTHON) -m pytest

development-v11:
	$(PYTHON) scripts/106_run_development_v11.py

development-v11-inventory:
	$(PYTHON) scripts/109_build_development_inventory.py

development-v11-candidates:
	$(PYTHON) scripts/110_build_confirmation_candidates.py

development-v11-score:
	$(PYTHON) scripts/108_score_development_recovery.py

development-v11-mixed:
	$(PYTHON) scripts/121_run_development_mixed_model.py

development-v11-confirm:
	$(PYTHON) scripts/115_run_route_a_confirmation.py

development-v11-stratify:
	$(PYTHON) scripts/118_stratify_route_a_confirmation.py

development-v11-triage:
	$(PYTHON) scripts/119_run_route_a_triage.py

development-v11-plots:
	$(PYTHON) scripts/120_plot_route_a_confirmation.py

development-v11-reviewer-completion:
	$(PYTHON) scripts/124_run_reviewer_completion.py
	$(PYTHON) scripts/132_run_recurrent_sensitivity.py
	$(PYTHON) scripts/133_run_process_hybrid_sensitivity.py
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 $(PYTHON) scripts/138_run_matched_outage_geometry.py
	$(PYTHON) scripts/136_run_lstm_sensitivity.py
	$(PYTHON) scripts/139_run_us_heterogeneity.py

development-v11-recurrent-sensitivity:
	$(PYTHON) scripts/132_run_recurrent_sensitivity.py

development-v11-process-sensitivity:
	$(PYTHON) scripts/133_run_process_hybrid_sensitivity.py

development-v11-matched-outage:
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 $(PYTHON) scripts/138_run_matched_outage_geometry.py

development-v11-lstm-sensitivity:
	$(PYTHON) scripts/136_run_lstm_sensitivity.py

development-v11-us-heterogeneity:
	$(PYTHON) scripts/139_run_us_heterogeneity.py

independent-air2stream-equivalent:
	$(PYTHON) scripts/137_run_independent_air2stream_equivalent.py

validate-development-v11-reviewer-completion:
	$(PYTHON) scripts/125_validate_reviewer_completion.py

second-confirmation-candidates:
	$(PYTHON) scripts/126_build_second_confirmation_candidates.py

second-confirmation-nve:
	$(PYTHON) scripts/127_qc_nve_second_confirmation.py

second-confirmation-readiness:
	$(PYTHON) scripts/128_build_second_confirmation_readiness.py

second-confirmation-canada-audit:
	$(PYTHON) scripts/129_audit_canada_second_confirmation.py

goal-completion-audit:
	$(PYTHON) scripts/130_build_goal_completion_audit.py

second-confirmation-score:
	$(PYTHON) scripts/131_run_second_confirmation.py
	$(PYTHON) scripts/135_run_second_confirmation_placement.py
	$(PYTHON) scripts/134_finalize_second_confirmation.py

second-confirmation-placement:
	$(PYTHON) scripts/135_run_second_confirmation_placement.py

second-confirmation-finalize:
	$(PYTHON) scripts/134_finalize_second_confirmation.py

confirmation-daily-qc:
	$(PYTHON) scripts/111_qc_confirmation_candidates.py

ehyd-source-audit:
	$(PYTHON) scripts/113_audit_ehyd_temperature.py

rws-daily-qc:
	$(PYTHON) scripts/114_qc_rws_temperature.py

arso-daily-qc:
	$(PYTHON) scripts/116_qc_arso_temperature.py

evidence-snapshot:
	$(PYTHON) scripts/25_build_evidence_snapshot.py

hosting-audit:
	$(PYTHON) scripts/26_audit_restricted_hosting.py

submission-gate:
	$(PYTHON) scripts/27_submission_gate.py --allow-no-go

blueprint-audit:
	$(PYTHON) scripts/100_build_qualified_corpus_manifest.py
	$(PYTHON) scripts/104_build_qualified_network_catalog.py
	$(PYTHON) scripts/105_build_blueprint_completion_audit.py

p0-protocol: evidence-snapshot hosting-audit submission-gate
	$(PYTHON) scripts/28_run_p0_pipeline.py

reproduce-paper:
	@echo "Applying claim-safe inference, tables, and SI from frozen artifacts."
	$(PYTHON) scripts/41_apply_wrr_evidence_revision.py
	$(PYTHON) scripts/39_build_submission_package.py --markdown-only
	$(PYTHON) scripts/35_validate_review_revision.py

reproduce-paper-full:
	@echo "Rebuilding expensive revision diagnostics, then the claim-safe overlay."
	$(PYTHON) scripts/36_run_external_validation_uncertainty.py --skip-existing
	$(PYTHON) scripts/37_run_p3_change_point.py
	$(PYTHON) scripts/34_run_major_revision.py
	$(PYTHON) scripts/41_apply_wrr_evidence_revision.py
	$(PYTHON) scripts/39_build_submission_package.py --markdown-only
	$(PYTHON) scripts/35_validate_review_revision.py

validate-review-revision:
	$(PYTHON) scripts/35_validate_review_revision.py

research-charter:
	$(PYTHON) scripts/45_validate_research_charter.py

recoverability-framework: research-charter
	$(PYTHON) scripts/43_build_network_catalog.py
	$(PYTHON) scripts/44_run_recoverability_framework.py

check-public-rivers:
	$(PYTHON) scripts/46_check_public_rivers.py

download-build-rivers:
	$(PYTHON) scripts/47_download_and_check_build_rivers.py

download-catalog-v2:
	$(PYTHON) scripts/57_download_catalog_v2_candidates.py

catalog-v3-huc8:
	$(PYTHON) scripts/56_build_catalog_v3_huc8.py

score-natural-outages:
	$(PYTHON) scripts/58_score_natural_outages.py

gap-triage:
	$(PYTHON) scripts/59_run_gap_triage.py

v2-operator-ablation:
	$(PYTHON) scripts/61_v2_public_river_operator_ablation.py

w2-phase4-gap-specific:
	$(PYTHON) scripts/67_w2_phase4_gap_specific.py

hubeau-daily:
	$(PYTHON) scripts/62_hubeau_daily_from_chronique.py

uk-ea-catalog:
	$(PYTHON) scripts/63_uk_ea_temperature_catalog.py

uk-ea-daily:
	$(PYTHON) scripts/65_uk_ea_daily_from_readings.py

uk-ea-spatial:
	$(PYTHON) scripts/89_uk_ea_spatial_daily.py

matched-regulation:
	$(PYTHON) scripts/64_matched_regulation.py

public-confirmatory-lock:
	$(PYTHON) scripts/66_propose_public_confirmatory_lock.py

ingest-qc-clearwater:
	$(PYTHON) scripts/65_ingest_qc_report.py

national-temperature-catalog:
	$(PYTHON) scripts/49_national_temperature_catalog.py

apply-catalog-clusters:
	$(PYTHON) scripts/51_apply_catalog_clusters.py

reservoir-operations-check:
	$(PYTHON) scripts/50_check_reservoir_operations.py

# Architecture and system-design figures.  The .drawio sources under
# figures/v17/drawio/ are the editable originals; the PDFs in the article are
# derived from them and must never be edited directly.  Where the draw.io
# desktop application is installed, prefer `make figures-drawio-native`.
figures-drawio:
	$(PYTHON) scripts/205_v17_drawio_export.py

figures-drawio-native:
	@command -v drawio >/dev/null || { echo "draw.io desktop not installed; use 'make figures-drawio'"; exit 1; }
	@for f in figures/v17/drawio/*.drawio; do \
		drawio -x -f pdf --crop -o "figures/v17/$$(basename $$f .drawio).pdf" "$$f"; \
	done

# The v18 closure programme. See paper_archived/v18/PROTOCOL.md; the two steps that reach
# the network (station coordinates and NASA POWER) are separate targets so the
# rest can be rebuilt offline.
v18-closure:
	$(PYTHON) scripts/210_v18_outage_seasonality.py
	$(PYTHON) scripts/211_v18_archive_deployment.py
	$(PYTHON) scripts/212_v18_endpoint_cases.py --workers 96
	$(PYTHON) scripts/213_v18_representativeness.py
	$(PYTHON) scripts/214_v18_sine_endpoints.py
	$(PYTHON) scripts/215_v18_support_width.py
	$(PYTHON) scripts/216_v18_informative_missingness.py
	$(PYTHON) scripts/220_v18_figures.py
	$(PYTHON) scripts/221_v18_audit_manuscript.py

v18-air-forcing:
	$(PYTHON) scripts/217_v18_station_coordinates.py
	$(PYTHON) scripts/218_v18_air_forcing.py
	STREAM_AIR_FORCING=$(CURDIR)/data/interim/v18_air_forcing.parquet \
		$(PYTHON) scripts/181_v17_cases.py --workers 40 --out cases_air.parquet
	$(PYTHON) scripts/219_v18_air_sensitivity.py

v18-audit:
	$(PYTHON) scripts/221_v18_audit_manuscript.py
	$(PYTHON) -m pytest tests/test_v18_closure.py -q

# Reading copies. The Markdown is the source; these are build products.
v18-pdf:
	$(PYTHON) scripts/222_v18_build_pdf.py
	$(PYTHON) scripts/222_v18_build_pdf.py --source paper_archived/v18/SUPPLEMENT.md --output paper_archived/v18/supplement.pdf
	$(PYTHON) scripts/222_v18_build_pdf.py --source paper_archived/v18/RESPONSE.md --output paper_archived/v18/response_to_referee.pdf

# Water Resources Research submission. AGU's class is vendored under
# paper/wrr/template/; the build resolves it through TEXINPUTS.
wrr:
	$(PYTHON) scripts/223_wrr_build.py

# Re-render the figures at journal page size. Only needed after a figure
# changes; the built PDFs are committed alongside the manuscript.
wrr-figures:
	WRR_JOURNAL_FIGURES=1 WRR_FIGURE_DIR=$(CURDIR)/paper/wrr/figures \
		$(PYTHON) scripts/265_wrr_figure1_example.py
	WRR_JOURNAL_FIGURES=1 WRR_FIGURE_DIR=$(CURDIR)/paper/wrr/figures \
		$(PYTHON) scripts/267_wrr_heterogeneity_figures.py
	cp figures/wrr/f1_example.pdf figures/wrr/f2a_endpoint_ordering.pdf \
	   figures/wrr/f2b_panel_heterogeneity.pdf paper/wrr/figures/
	WRR_JOURNAL_FIGURES=1 WRR_FIGURE_DIR=$(CURDIR)/paper/wrr/figures \
		$(PYTHON) scripts/188_v17_figures.py
	WRR_JOURNAL_FIGURES=1 WRR_FIGURE_DIR=$(CURDIR)/paper/wrr/figures \
		$(PYTHON) scripts/204_v17_figures_q1.py
	WRR_JOURNAL_FIGURES=1 WRR_FIGURE_DIR=$(CURDIR)/paper/wrr/figures \
		$(PYTHON) scripts/220_v18_figures.py
	$(PYTHON) scripts/205_v17_drawio_export.py
	cp figures/v17/f0_problem_frame.pdf figures/v17/f1_system_architecture.pdf \
	   figures/v17/f2_experiment_design.pdf figures/v17/f3_evidence_chain.pdf \
	   figures/v17/f4_deployment_workflow.pdf paper/wrr/figures/

# Re-export the draw.io architecture and system-design sources at the printed
# 5.5 in width, so PDF type size equals printed type size.
wrr-schematics:
	$(PYTHON) scripts/205_v17_drawio_export.py
	cp figures/v17/f0_problem_frame.pdf figures/v17/f1_system_architecture.pdf \
	   figures/v17/f2_experiment_design.pdf figures/v17/f3_evidence_chain.pdf \
	   figures/v17/f4_deployment_workflow.pdf paper/wrr/figures/

# 2026-10-20 aligned-policy round: one object, one failure event, one tie rule.
# Order matters: 331 and 334 read 330's thresholds and calibration scores, and
# 333 reads 331's replay detail.
wrr-round-20261020:
	PYTHONPATH=src $(PYTHON) scripts/330_wrr_aligned_policy_admission.py
	PYTHONPATH=src $(PYTHON) scripts/332_wrr_selection_calibration_v2.py
	PYTHONPATH=src $(PYTHON) scripts/331_wrr_aligned_real_calendar.py
	PYTHONPATH=src $(PYTHON) scripts/333_wrr_aligned_hot_year_closure.py
	PYTHONPATH=src $(PYTHON) scripts/334_wrr_repair_attribution.py
	PYTHONPATH=src $(PYTHON) scripts/336_wrr_measurement_subset.py
	PYTHONPATH=src $(PYTHON) scripts/335_wrr_figures_v2.py
	$(PYTHON) scripts/223_wrr_build.py

# 2026-10-20b attribution round: what each design identifies, where the fitted
# score's gain comes from, how the error splits, what refusal costs, and whether
# a gap calendar says to screen.  Runs after wrr-round-20261020 (it reads 330's
# admissions and 331's replay).  343 reads 341's case admissions, and 345 and
# 346 read everything before them.
wrr-round-20261020b:
	PYTHONPATH=src $(PYTHON) scripts/340_wrr_design_audit.py
	PYTHONPATH=src $(PYTHON) scripts/341_wrr_same_capacity_ablation.py
	PYTHONPATH=src $(PYTHON) scripts/342_wrr_three_window_decomposition.py
	PYTHONPATH=src $(PYTHON) scripts/343_wrr_hot_year_selection_null.py
	PYTHONPATH=src $(PYTHON) scripts/344_wrr_screening_need_rule.py
	PYTHONPATH=src $(PYTHON) scripts/335_wrr_figures_v2.py
	PYTHONPATH=src $(PYTHON) scripts/345_wrr_figures_r2.py
	PYTHONPATH=src $(PYTHON) scripts/346_wrr_si_tables_r2.py
	PYTHONPATH=src $(PYTHON) scripts/347_wrr_claim_registry_r2.py
	$(PYTHON) scripts/223_wrr_build.py

wrr-figures-20261020:
	PYTHONPATH=src $(PYTHON) scripts/335_wrr_figures_v2.py
	PYTHONPATH=src $(PYTHON) scripts/345_wrr_figures_r2.py

.PHONY: wrr-round-20261020c wrr-r3-frozen-replay
wrr-round-20261020c:
	$(PYTHON) scripts/371_wrr_frozen_replay.py --check-only
	@for protocol in leave_one_year_out strictly_prior_years; do for family in admission crossed events real_calendars; do $(PYTHON) scripts/373_wrr_hydrological_strata.py --protocol $$protocol --family $$family || exit $$?; done; done
	$(PYTHON) scripts/367_wrr_revision_evidence.py
	$(PYTHON) scripts/369_wrr_revision_si.py
	$(PYTHON) scripts/368_wrr_revision_figures.py
	$(PYTHON) scripts/223_wrr_build.py
	pandoc paper/wrr/RESPONSE_TO_REVIEW.md --pdf-engine=xelatex -V geometry:margin=25mm -V fontsize=10pt -o paper/wrr/RESPONSE_TO_REVIEW.pdf
	$(PYTHON) scripts/266_wrr_figure_qa.py
	@PYTHONPATH=src $(PYTHON) -m pytest -q > scratch/wrr_revision_20261020c/full_tests.log 2>&1; status=$$?; printf '%s\n' "$$status" > scratch/wrr_revision_20261020c/full_tests.exitcode; cat scratch/wrr_revision_20261020c/full_tests.log; exit $$status
	$(PYTHON) scripts/370_wrr_revision_completion.py

wrr-r3-frozen-replay:
	$(PYTHON) scripts/371_wrr_frozen_replay.py

# Architecture and system-design figures are draw.io sources.  Point DRAWIO_BIN
# at the draw.io desktop executable; without it the script falls back to the
# repository's XML renderer and says so.
wrr-schematics-20261020:
	$(PYTHON) scripts/337_wrr_drawio_figures.py

# Field-by-field check of references.bib against the publisher deposits.
wrr-reference-audit:
	$(PYTHON) scripts/338_wrr_reference_audit.py

wrr-check:
	$(PYTHON) scripts/223_wrr_build.py --skip-build

# Font embedding, page geometry, text bounds, overlap and figure provenance.
wrr-figure-qa:
	$(PYTHON) scripts/266_wrr_figure_qa.py

# Submission-readiness tree: evidence identity, manifests, predict deploy, preflight.
# Does not invent author metadata; build remains NOT submission-ready until humans fill
# metadata/submission_author_metadata.json.
wrr-submission-ready:
	PYTHONPATH=src $(PYTHON) scripts/229_wrr_preflight.py
	PYTHONPATH=src $(PYTHON) scripts/232_wrr_measurement_provenance.py
	PYTHONPATH=src $(PYTHON) scripts/228_wrr_rebuild_from_inputs.py
	PYTHONPATH=src $(PYTHON) scripts/231_wrr_certificate_deploy_predict.py
	PYTHONPATH=src $(PYTHON) scripts/245_multi_agency_prior_access_audit.py
	$(PYTHON) scripts/223_wrr_build.py --skip-build
	@echo "See results/wrr_submission_ready/STATUS.md and SUBMISSION_CHECKLIST.md"

# P0-07 extension: multi-agency transport test (see
# results/wrr_submission_ready/MULTI_AGENCY_TRANSPORT_PROTOCOL.md). Ingest output
# lives under results/wrr_submission_ready/multi_agency_ingest/<provider>/.
# Assemble the eligible panel first, then score it.
wrr-transport-seal:
	PYTHONPATH=src $(PYTHON) scripts/245_multi_agency_prior_access_audit.py
	PYTHONPATH=src $(PYTHON) scripts/249_multi_agency_transport_seal.py

wrr-transport-score:
	PYTHONPATH=src $(PYTHON) scripts/250_multi_agency_transport_score.py

# P2-03 companion dataset and static dashboard (tracked dataset in docs/companion,
# self-contained HTML in dist/companion).
wrr-companion:
	PYTHONPATH=src $(PYTHON) scripts/264_wrr_companion_dataset.py

.PHONY: wrr-followup wrr-followup-evidence wrr-followup-check

# Follow-up development on opened outcomes; never changes the original results.
wrr-followup:
	$(PYTHON) scripts/374_wrr_objective_factorial.py --protocol leave_one_year_out --workers 12
	$(PYTHON) scripts/374_wrr_objective_factorial.py --protocol strictly_prior_years --workers 12
	$(PYTHON) scripts/375_wrr_transfer_failure_diagnosis.py --protocol leave_one_year_out
	$(PYTHON) scripts/375_wrr_transfer_failure_diagnosis.py --protocol strictly_prior_years
	$(PYTHON) scripts/375_wrr_transfer_failure_diagnosis.py --protocol leave_one_year_out --rebuild-source-no-donors
	$(PYTHON) scripts/375_wrr_transfer_failure_diagnosis.py --protocol strictly_prior_years --rebuild-source-no-donors
	$(PYTHON) scripts/376_wrr_common_population_mechanism.py --protocol leave_one_year_out
	$(PYTHON) scripts/376_wrr_common_population_mechanism.py --protocol strictly_prior_years
	$(PYTHON) scripts/377_wrr_information_and_calibration.py --protocol leave_one_year_out
	$(PYTHON) scripts/377_wrr_information_and_calibration.py --protocol strictly_prior_years
	$(PYTHON) scripts/358_wrr_external_recovery.py --role calibration
	$(PYTHON) scripts/362_wrr_process_reference.py --role calibration
	$(PYTHON) scripts/361_wrr_probabilistic_reference.py --evaluate calibration
	$(PYTHON) scripts/378_wrr_conditional_trajectory.py --role development
	$(PYTHON) scripts/378_wrr_conditional_trajectory.py --role calibration
	$(PYTHON) scripts/378_wrr_conditional_trajectory.py --role test
	$(PYTHON) scripts/378_wrr_conditional_trajectory.py --role development --protocol strictly_prior_years
	$(PYTHON) scripts/378_wrr_conditional_trajectory.py --role test --protocol strictly_prior_years
	$(PYTHON) scripts/379_wrr_reconstruction_decision_factorial.py
	$(PYTHON) scripts/380_wrr_event_and_procedure.py --protocol leave_one_year_out
	$(PYTHON) scripts/380_wrr_event_and_procedure.py --protocol strictly_prior_years
	$(PYTHON) scripts/380_wrr_event_and_procedure.py --events-only
	$(PYTHON) scripts/381_wrr_external_cost_baselines.py --protocol leave_one_year_out
	$(PYTHON) scripts/381_wrr_external_cost_baselines.py --protocol strictly_prior_years
	$(PYTHON) scripts/382_wrr_history_and_boundaries.py --protocol leave_one_year_out
	$(PYTHON) scripts/382_wrr_history_and_boundaries.py --protocol strictly_prior_years
	$(MAKE) wrr-probability-budget
	$(MAKE) wrr-joint-power
	$(MAKE) wrr-backup-resource
	$(MAKE) wrr-extended-evidence

wrr-followup-evidence:
	$(PYTHON) scripts/383_wrr_followup_evidence.py
	$(PYTHON) scripts/409_wrr_au_dependence_evidence.py
	$(PYTHON) scripts/223_wrr_build.py
	pandoc paper/wrr/RESPONSE_TO_REVIEW.md --pdf-engine=xelatex -V geometry:margin=25mm -V fontsize=10pt -o paper/wrr/RESPONSE_TO_REVIEW.pdf
	$(PYTHON) scripts/384_wrr_followup_audit.py

wrr-followup-check:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 pytest tests/test_wrr_decision_baselines.py tests/test_wrr_state_trajectory.py tests/test_wrr_followup_evidence.py tests/test_wrr_probability_and_joint_power.py tests/test_wrr_backup_and_developed_system.py tests/test_wrr_developed_calibration_budget.py
	$(PYTHON) scripts/371_wrr_frozen_replay.py --check-only
	$(PYTHON) scripts/384_wrr_followup_audit.py

.PHONY: wrr-probability-data wrr-probability-air32 wrr-probability-air64 wrr-probability-budget wrr-joint-power wrr-backup-resource wrr-extended-evidence

wrr-probability-data:
	$(PYTHON) scripts/385_wrr_probability_development.py prepare

wrr-probability-air32: wrr-probability-data
	$(PYTHON) scripts/385_wrr_probability_development.py train --configuration air32
	$(PYTHON) scripts/385_wrr_probability_development.py validate --configuration air32

wrr-probability-air64: wrr-probability-data
	$(PYTHON) scripts/385_wrr_probability_development.py train --configuration air64
	$(PYTHON) scripts/385_wrr_probability_development.py validate --configuration air64

# `make -j2 wrr-probability-budget` shares preparation and trains independent configs.
wrr-probability-budget: wrr-probability-air32 wrr-probability-air64
	$(PYTHON) scripts/385_wrr_probability_development.py select
	$(PYTHON) scripts/390_wrr_developed_probability_system.py evaluate-probability --role development
	$(PYTHON) scripts/390_wrr_developed_probability_system.py evaluate-probability --role calibration
	$(PYTHON) scripts/390_wrr_developed_probability_system.py evaluate-probability --role test
	$(PYTHON) scripts/390_wrr_developed_probability_system.py system
	$(PYTHON) scripts/393_wrr_developed_calibration_budget.py --workers 12

wrr-joint-power:
	$(PYTHON) scripts/386_wrr_joint_power_plan.py --workers 24
	$(PYTHON) scripts/391_wrr_extended_evidence.py --planning-only

wrr-backup-resource:
	$(PYTHON) scripts/387_wrr_backup_resource.py stage
	$(PYTHON) scripts/387_wrr_backup_resource.py metadata
	$(PYTHON) scripts/388_wrr_natural_backup_validation.py qualify
	$(PYTHON) scripts/389_wrr_short_history_backup.py prepare
	$(PYTHON) scripts/389_wrr_short_history_backup.py evaluate --method linear_interp
	$(PYTHON) scripts/389_wrr_short_history_backup.py evaluate --method air2stream3
	$(PYTHON) scripts/389_wrr_short_history_backup.py evaluate --method csdi_old
	$(PYTHON) scripts/389_wrr_short_history_backup.py evaluate --method csdi_developed

wrr-extended-evidence: wrr-three-method-power
	$(PYTHON) scripts/393_wrr_developed_calibration_budget.py --evidence-only
	$(PYTHON) scripts/391_wrr_extended_evidence.py
	$(MAKE) wrr-followup-evidence

.PHONY: wrr-public-backup-metadata wrr-public-backup
wrr-public-backup-metadata:
	$(PYTHON) scripts/398_wrr_public_source_audit.py metadata
	$(PYTHON) scripts/397_wrr_public_neon_metadata.py

wrr-public-backup: wrr-public-backup-metadata
	$(PYTHON) scripts/394_wrr_public_backup_resource.py fetch-usgs
	$(PYTHON) scripts/395_wrr_usgs_backup_qualification.py qualify
	$(PYTHON) scripts/396_wrr_usgs_named_instruments.py fetch
	$(PYTHON) scripts/396_wrr_usgs_named_instruments.py qualify
	$(PYTHON) scripts/398_wrr_public_source_audit.py audit

.PHONY: wrr-au-metadata wrr-au-source-freeze wrr-au-reference-qualify wrr-au-reference-retry wrr-new-reference-check
wrr-au-metadata:
	$(PYTHON) scripts/404_wrr_new_reference_audit.py metadata
	$(PYTHON) scripts/400_wrr_au_metadata_recruitment.py

wrr-au-source-freeze: wrr-au-metadata
	$(PYTHON) scripts/401_wrr_au_source_model_freeze.py

# These targets acquire/qualify references; they do not open new H30 errors.
wrr-au-reference-qualify: wrr-au-source-freeze
	$(PYTHON) scripts/402_wrr_au_reference_acquisition.py fetch --workers 2
	$(PYTHON) scripts/402_wrr_au_reference_acquisition.py qualify
	$(PYTHON) scripts/403_wrr_au_native_support.py --workers 2
	$(PYTHON) scripts/404_wrr_new_reference_audit.py audit

wrr-au-reference-retry:
	$(PYTHON) scripts/403_wrr_au_native_support.py --retry-pending --workers 2
	$(PYTHON) scripts/404_wrr_new_reference_audit.py audit

wrr-new-reference-check:
	OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 $(PYTHON) -m pytest tests/test_wrr_new_reference_recruitment.py tests/test_wrr_three_method_planning.py tests/test_wrr_au_dependence_audit.py tests/test_wrr_usgs_reference_preflight.py tests/test_wrr_usgs_network_intake.py tests/test_wrr_usgs_prior_cache_audit.py tests/test_wrr_usgs_network_resume.py tests/test_wrr_usgs_intake_audit.py -q
	$(PYTHON) scripts/404_wrr_new_reference_audit.py audit
	$(PYTHON) scripts/371_wrr_frozen_replay.py --check-only

.PHONY: wrr-three-method-power
wrr-three-method-power:
	$(PYTHON) scripts/405_wrr_three_method_joint_power.py --workers 24
	$(PYTHON) scripts/407_wrr_three_method_evidence.py

.PHONY: wrr-au-network-feasibility
wrr-au-network-feasibility:
	$(PYTHON) scripts/406_wrr_au_network_feasibility.py fetch
	$(PYTHON) scripts/406_wrr_au_network_feasibility.py summarize

.PHONY: wrr-au-dependence-audit
# Uses the retained topology snapshot; no new observations, roles or predictions.
wrr-au-dependence-audit:
	$(PYTHON) scripts/408_wrr_au_dependence_audit.py
	$(PYTHON) scripts/409_wrr_au_dependence_evidence.py

.PHONY: wrr-usgs-reference-preflight wrr-usgs-network-intake wrr-usgs-network-intake-retry
# Metadata only. Neither target assigns roles or downloads reference temperatures.
wrr-usgs-reference-preflight:
	$(PYTHON) scripts/410_wrr_usgs_reference_preflight.py fetch
	$(PYTHON) scripts/410_wrr_usgs_reference_preflight.py summarize
	$(PYTHON) scripts/412_wrr_usgs_prior_cache_audit.py

wrr-usgs-network-intake:
	$(PYTHON) scripts/411_wrr_usgs_network_intake.py fetch --workers 2
	$(PYTHON) scripts/411_wrr_usgs_network_intake.py summarize

wrr-usgs-network-intake-retry:
	$(PYTHON) scripts/413_wrr_usgs_network_resume.py

.PHONY: wrr-usgs-intake-audit
wrr-usgs-intake-audit:
	$(PYTHON) scripts/414_wrr_usgs_intake_audit.py audit

.PHONY: wrr-state-risk-development wrr-state-risk-factorial wrr-state-risk-evidence wrr-neon-large-river-metadata
# Preserve prior selection timestamps: a stage whose main output exists is not re-run.
wrr-state-risk-development:
	@if [ -f results/wrr_submission_ready/followup_20261021/state_risk_completion/trajectories/development/cases.parquet ]; then \
		echo "development trajectories already exist"; \
	else $(PYTHON) scripts/415_wrr_state_risk_generator.py --role development --workers 8; fi
	@if [ -f results/wrr_submission_ready/followup_20261021/state_risk_completion/factorial/development_selection.json ]; then \
		echo "development selection already exists"; \
	else $(PYTHON) scripts/416_wrr_state_risk_factorial.py select; fi

wrr-state-risk-factorial: wrr-state-risk-development
	@set -e; for role in calibration test; do \
		if [ -f results/wrr_submission_ready/followup_20261021/state_risk_completion/trajectories/$$role/cases.parquet ]; then \
			echo "$$role trajectories already exist"; \
		else $(PYTHON) scripts/415_wrr_state_risk_generator.py --role $$role --workers 8; fi; done
	@if [ -f results/wrr_submission_ready/followup_20261021/state_risk_completion/factorial/predictions.parquet ]; then \
		echo "factorial already exists"; \
	else $(PYTHON) scripts/416_wrr_state_risk_factorial.py evaluate; fi
	@if [ -f results/wrr_submission_ready/followup_20261021/state_risk_completion/system_factorial/predictions.parquet ]; then \
		echo "system factorial already exists"; \
	else $(PYTHON) scripts/417_wrr_state_risk_system.py; fi
	$(PYTHON) scripts/418_wrr_state_risk_evidence.py

wrr-state-risk-evidence:
	$(PYTHON) scripts/418_wrr_state_risk_evidence.py
	$(PYTHON) scripts/223_wrr_build.py

wrr-neon-large-river-metadata:
	$(PYTHON) scripts/419_wrr_neon_large_river_metadata.py

.PHONY: wrr-usgs-empty-cache-scope wrr-backup-history-bound
wrr-usgs-empty-cache-scope:
	$(PYTHON) scripts/420_wrr_usgs_empty_cache_scope.py

wrr-backup-history-bound:
	$(PYTHON) scripts/421_wrr_backup_history_upper_bound.py

.PHONY: wrr-reference-pool-feasibility
wrr-reference-pool-feasibility:
	$(PYTHON) scripts/422_wrr_reference_pool_feasibility.py

.PHONY: wrr-additional-source-scope
wrr-additional-source-scope:
	$(PYTHON) scripts/423_wrr_additional_source_scope.py

.PHONY: wrr-usgs-metadata-extension-prepare wrr-usgs-metadata-extension-fetch wrr-usgs-metadata-extension-audit
wrr-usgs-metadata-extension-prepare:
	$(PYTHON) scripts/424_wrr_usgs_metadata_extension.py prepare

wrr-usgs-metadata-extension-fetch:
	$(PYTHON) scripts/424_wrr_usgs_metadata_extension.py fetch

wrr-usgs-metadata-extension-audit:
	$(PYTHON) scripts/424_wrr_usgs_metadata_extension.py audit

.PHONY: wrr-au-catchment-scope-prepare wrr-au-catchment-scope-run wrr-au-catchment-scope-audit
wrr-au-catchment-scope-prepare:
	$(PYTHON) scripts/425_wrr_au_catchment_scope_extension.py prepare

wrr-au-catchment-scope-run:
	$(PYTHON) scripts/425_wrr_au_catchment_scope_extension.py run

wrr-au-catchment-scope-audit:
	$(PYTHON) scripts/425_wrr_au_catchment_scope_extension.py audit

# Target-recovery study (docs/reviews/wrr_target_recovery_20261021/). Development
# experiments on the opened archive; the sealed Australian test runs after the
# round-1 pipeline is frozen. Scripts import the shared modules from scripts/.
TR_ENV = PYTHONPATH=$(CURDIR)/src:$(CURDIR)/scripts
.PHONY: wrr-tr wrr-tr-sealed wrr-tr2 wrr-tr2-sealed wrr-tr-paper wrr-tr-check
# Round 1 (first preregistration, Australian sealed test) runs with its own configuration.
TR1_ENV = TR_CONFIG=$(CURDIR)/configs/wrr_target_recovery_20261021.json $(TR_ENV)

wrr-tr:
	$(TR1_ENV) $(PYTHON) scripts/427_tr_usgs_flow.py
	$(TR1_ENV) $(PYTHON) scripts/429_tr_air_extension.py
	$(TR1_ENV) $(PYTHON) scripts/426_tr_archive.py
	$(TR1_ENV) $(PYTHON) scripts/428_tr_au_sealed_prep.py
	$(TR1_ENV) $(PYTHON) scripts/430_tr_e1_missingness.py
	$(TR1_ENV) $(PYTHON) scripts/433_tr_prereg.py
	$(TR1_ENV) $(PYTHON) scripts/431_tr_cases.py --roster source
	$(TR1_ENV) $(PYTHON) scripts/432_tr_e4_estimators.py
	$(TR1_ENV) $(PYTHON) scripts/434_tr_e3_recovery_law.py
	$(TR1_ENV) $(PYTHON) scripts/435_tr_d2_selection.py
	$(TR1_ENV) $(PYTHON) scripts/436_tr_e5_rules.py
	$(TR1_ENV) $(PYTHON) scripts/445_tr_e5_waste.py
	$(TR1_ENV) $(PYTHON) scripts/449_tr_tolerance_sensitivity.py
	$(TR1_ENV) $(PYTHON) scripts/437_tr_e7_transfer.py
	$(TR1_ENV) $(PYTHON) scripts/442_tr_e6_multitarget.py
	$(TR1_ENV) $(PYTHON) scripts/443_tr_e11_ablation.py
	$(TR1_ENV) $(PYTHON) scripts/440_tr_e8_downstream.py
	$(TR1_ENV) $(PYTHON) scripts/440_tr_e8_downstream.py --min-years 15
	$(TR1_ENV) $(PYTHON) scripts/431_tr_cases.py --roster real

# Freezes the round-1 pipeline (438), then builds and evaluates the Australian cases.
wrr-tr-sealed:
	$(TR1_ENV) $(PYTHON) scripts/438_tr_freeze.py
	$(TR1_ENV) $(PYTHON) scripts/431_tr_cases.py --roster au
	$(TR1_ENV) $(PYTHON) scripts/439_tr_e7_sealed.py
	$(TR1_ENV) $(PYTHON) scripts/446_tr_sealed_diagnostics.py
	$(TR1_ENV) $(PYTHON) scripts/447_tr_e7_expected_risk.py
	$(TR1_ENV) $(PYTHON) scripts/441_tr_e9_application.py

# Round 2: hot years and station seasons, calibrated intervals, the label-free rule,
# the Australian development check, the availability-only design of the second sealed
# test and the second preregistration.
wrr-tr2:
	$(TR_ENV) $(PYTHON) scripts/450_tr2_tolerances.py
	$(TR_ENV) $(PYTHON) scripts/431_tr_cases.py --roster source
	$(TR_ENV) $(PYTHON) scripts/431_tr_cases.py --roster au
	$(TR_ENV) $(PYTHON) scripts/431_tr_cases.py --roster real
	$(TR_ENV) $(PYTHON) scripts/432_tr_e4_estimators.py
	$(TR_ENV) $(PYTHON) scripts/434_tr_e3_recovery_law.py
	$(TR_ENV) $(PYTHON) scripts/435_tr_d2_selection.py
	$(TR_ENV) $(PYTHON) scripts/451_tr2_cqr.py
	$(TR_ENV) $(PYTHON) scripts/436_tr_e5_rules.py
	$(TR_ENV) $(PYTHON) scripts/453_tr2_expected_risk.py
	$(TR_ENV) $(PYTHON) scripts/455_tr2_final_models.py
	$(TR_ENV) $(PYTHON) scripts/434_tr_e3_recovery_law.py --cases results/wrr_target_recovery_20261022/e7_au_development/cases.parquet --output results/wrr_target_recovery_20261022/e7_au_development/law
	$(TR_ENV) $(PYTHON) scripts/455_tr2_final_models.py --au-check
	$(TR_ENV) $(PYTHON) scripts/460_tr2_definition_check.py
	$(TR_ENV) $(PYTHON) scripts/452_tr2_usgs_availability.py
	$(TR_ENV) $(PYTHON) scripts/457_tr2_usgs_sealed_inputs.py --design
	$(TR_ENV) $(PYTHON) scripts/454_tr2_prereg.py
	$(TR_ENV) $(PYTHON) scripts/445_tr_e5_waste.py
	$(TR_ENV) $(PYTHON) scripts/449_tr_tolerance_sensitivity.py
	$(TR_ENV) $(PYTHON) scripts/437_tr_e7_transfer.py
	$(TR_ENV) $(PYTHON) scripts/442_tr_e6_multitarget.py
	$(TR_ENV) $(PYTHON) scripts/443_tr_e11_ablation.py
	$(TR_ENV) $(PYTHON) scripts/440_tr_e8_downstream.py
	$(TR_ENV) $(PYTHON) scripts/440_tr_e8_downstream.py --min-years 15
	$(TR_ENV) $(PYTHON) scripts/441_tr_e9_application.py
	$(TR_ENV) $(PYTHON) scripts/459_tr2_downstream_decomposition.py
	$(TR_ENV) $(PYTHON) scripts/461_tr2_flow_demo.py
	$(TR_ENV) $(PYTHON) scripts/462_tr2_law_diagnosis.py

# The second sealed test: values of the new USGS stations, their cases and the evaluation.
wrr-tr2-sealed:
	$(TR_ENV) $(PYTHON) scripts/457_tr2_usgs_sealed_inputs.py --values
	$(TR_ENV) $(PYTHON) scripts/431_tr_cases.py --roster usgs_new
	$(TR_ENV) $(PYTHON) scripts/458_tr2_sealed_eval.py

wrr-tr-paper:
	$(TR_ENV) $(PYTHON) scripts/464_tr2_figures.py
	$(TR_ENV) $(PYTHON) scripts/205_v17_drawio_export.py --output-dir figures/wrr_tr figures/wrr_tr/drawio/tr_s1_design.drawio
	cp figures/wrr_tr/tr_s1_design.pdf paper/wrr_tr/figures/
	$(TR_ENV) $(PYTHON) scripts/463_tr2_evidence.py
	cd paper/wrr_tr && TEXINPUTS=.:../wrr/template: latexmk -pdf -interaction=nonstopmode -halt-on-error wrr_tr_manuscript.tex
	cd paper/wrr_tr && TEXINPUTS=.:../wrr/template: latexmk -pdf -interaction=nonstopmode -halt-on-error wrr_tr_supporting_information.tex

wrr-tr-check:
	$(PYTHON) -m pytest tests/test_wrr_target_recovery.py

# Fourth-review redesign on opened outcomes. No target acquisition is hidden
# behind these targets; public registration is a separate external dependency.
.PHONY: wrr-review-completion wrr-review-cases wrr-review-refits wrr-review-windows wrr-review-analyses wrr-review-deep wrr-review-inputs wrr-review-national wrr-review-prereg wrr-review-deployment wrr-review-paper wrr-review-check wrr-review-adversarial-inputs

wrr-review-cases:
	$(PYTHON) scripts/465_review_completion_cases.py --workers 64 --resume
	$(PYTHON) scripts/465_review_completion_cases.py --split cold_to_hot --seeds 0 1 2 --workers 32 --resume
	$(PYTHON) scripts/465_review_completion_cases.py --split before_2010 --seeds 0 1 2 --workers 32 --resume
	$(PYTHON) scripts/465_review_completion_cases.py --split non_air_refit --seeds 0 1 2 --workers 32 --resume
	$(PYTHON) scripts/465_review_completion_cases.py --split air_exposure --seeds 0 1 2 --workers 48 --resume

wrr-review-refits:
	$(PYTHON) scripts/466_review_completion_refit.py --workers 48
	$(PYTHON) scripts/466_review_completion_refit.py --split cold_to_hot --seeds 0 1 2 --workers 32
	$(PYTHON) scripts/466_review_completion_refit.py --split before_2010 --seeds 0 1 2 --workers 32
	$(PYTHON) scripts/466_review_completion_refit.py --split non_air_refit --seeds 0 1 2 --workers 32
	$(PYTHON) scripts/479_review_completion_opened_transfer.py

wrr-review-analyses:
	$(PYTHON) scripts/483_review_completion_bridge_repair.py --workers 24
	$(PYTHON) scripts/467_review_completion_analysis.py --workers 16
	$(PYTHON) scripts/467_review_completion_analysis.py --split cold_to_hot --seeds 0 1 2 --workers 3 --skip-trends
	$(PYTHON) scripts/467_review_completion_analysis.py --split before_2010 --seeds 0 1 2 --workers 3 --skip-trends
	$(PYTHON) scripts/467_review_completion_analysis.py --split non_air_refit --seeds 0 1 2 --workers 3
	$(PYTHON) scripts/467_review_completion_analysis.py --split opened_transfer --seeds 0 --workers 1 --skip-trends
	$(PYTHON) scripts/470_review_completion_adaptation.py --workers 16
	$(PYTHON) scripts/471_review_completion_meaning.py
	$(PYTHON) scripts/482_review_completion_failure_map.py
	$(PYTHON) scripts/486_review_completion_group_robustness.py --workers 8
	$(PYTHON) scripts/487_review_completion_semi_rcps.py --workers 8
	$(PYTHON) scripts/488_review_completion_conditional_conformal.py --workers 8
	$(PYTHON) scripts/489_review_completion_regional_rankings.py
	$(PYTHON) scripts/491_review_completion_observed_record_bounds.py
	$(PYTHON) scripts/492_review_completion_probability_ablation.py
	$(PYTHON) scripts/499_review_completion_air_exposure.py --workers 3
	$(PYTHON) scripts/518_review_completion_focused_diagnostics.py
	$(PYTHON) scripts/519_review_completion_zero_flow_missingness.py --workers 24 --draws 400

wrr-review-deep:
	$(PYTHON) scripts/468_review_completion_deep.py --seed 0
	$(PYTHON) scripts/468_review_completion_deep.py --seed 1
	$(PYTHON) scripts/468_review_completion_deep.py --seed 2
	$(PYTHON) scripts/481_review_completion_deep_match.py
	$(PYTHON) scripts/484_review_completion_nonlinear_inputs.py
	$(PYTHON) scripts/493_review_completion_local_boosting.py

wrr-review-windows:
	$(PYTHON) scripts/506_review_completion_window_refits.py --workers 48 --resume --with-trends
	$(PYTHON) scripts/509_review_completion_window_evidence.py

wrr-review-inputs:
	$(PYTHON) scripts/517_review_completion_flow_comparators.py --workers 24
	$(PYTHON) scripts/469_review_completion_inputs.py --forcing
	$(PYTHON) scripts/513_review_completion_source_coordinates.py
	$(PYTHON) scripts/507_review_completion_full_forcing.py --workers 2 --analysis-workers 16
	$(PYTHON) scripts/505_review_completion_observed_air.py --all-source --exact-source-ridge
	$(PYTHON) scripts/515_review_completion_forcing_recovery.py --region usgs --workers 16
	$(PYTHON) scripts/475_review_completion_daily_max.py
	$(PYTHON) scripts/477_review_completion_europe_forcing.py
	$(PYTHON) scripts/510_review_completion_europe_full.py --workers 2 --analysis-workers 16
	$(PYTHON) scripts/515_review_completion_forcing_recovery.py --region europe --workers 16
	$(PYTHON) scripts/478_review_completion_reference_diagnostics.py
	$(PYTHON) scripts/490_review_completion_national_availability.py --metadata-only

wrr-review-national:
	$(PYTHON) scripts/500_review_completion_national_inputs.py --workers 2
	$(PYTHON) scripts/501_review_completion_national_forcing.py --workers 2
	$(PYTHON) scripts/502_review_completion_national_application.py --workers 24 --resume
	$(PYTHON) scripts/503_review_completion_national_meaning.py --bootstrap 2000

wrr-review-prereg:
	$(PYTHON) scripts/494_review_completion_independent_metadata.py
	$(PYTHON) scripts/494_review_completion_independent_metadata.py --agency greater_wellington
	$(PYTHON) scripts/472_review_completion_prereg.py
	$(PYTHON) scripts/498_review_completion_freeze_independent_roster.py
	$(PYTHON) scripts/472_review_completion_prereg.py

wrr-review-deployment:
	$(PYTHON) scripts/485_review_completion_deployment.py

wrr-review-adversarial-inputs:
	$(PYTHON) scripts/926_rule_accounting.py
	$(PYTHON) scripts/927_failure_strata.py
	$(PYTHON) scripts/928_rank_convergence.py
	$(PYTHON) scripts/929_manuscript_inputs.py

wrr-review-paper: wrr-review-adversarial-inputs
	$(PYTHON) scripts/473_review_completion_evidence.py
	$(PYTHON) scripts/524_research_report.py
	cd paper/wrr_tr && TEXINPUTS=.:../wrr/template: latexmk -pdf -interaction=nonstopmode -halt-on-error review_completion_article.tex
	cd paper/wrr_tr && TEXINPUTS=.:../wrr/template: latexmk -pdf -interaction=nonstopmode -halt-on-error review_completion_supporting.tex

wrr-review-check:
	$(PYTHON) -m pytest tests/test_wrr_review_completion.py tests/test_wrr_target_recovery.py tests/test_wrr_review_independent.py tests/test_wrr_review_national.py tests/test_wrr_review_windows.py tests/test_wrr_review_forcing_evidence.py tests/test_wrr_forcing_residual_history.py tests/test_wrr_national_coverage.py
	$(PYTHON) scripts/474_review_completion_validate.py
	$(PYTHON) scripts/512_review_completion_delivery.py

wrr-review-completion:
	$(MAKE) review

# Local paired strict-region follow-up; requires the restricted source models
# and masked-case features created by the earlier strict-region reanalysis.
.PHONY: review-strict-region-followup
STRICT_REGION_WORKERS ?= 2
review-strict-region-followup:
	$(PYTHON) scripts/621_strict_region_scenario_sensitivity.py --workers $(STRICT_REGION_WORKERS)
	$(PYTHON) scripts/622_strict_region_uncertainty_sensitivity.py
	$(PYTHON) scripts/623_strict_region_prediction_replay.py

.PHONY: review-andrews-source-overlap
review-andrews-source-overlap:
	$(PYTHON) scripts/624_andrews_source_overlap_audit.py

.PHONY: review-usgs-partial-reference
review-usgs-partial-reference:
	$(PYTHON) data/external/wrr_usgs_partial_daily_20261027/scripts/890_public_usgs_reference_replay.py
	$(PYTHON) data/external/wrr_usgs_partial_daily_20261027/scripts/892_public_usgs_raw_daily_audit.py
	$(PYTHON) data/external/wrr_usgs_partial_daily_20261027/scripts/901_public_subdaily_bounds_replay.py
