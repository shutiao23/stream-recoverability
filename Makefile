PYTHON ?= python
export PYTHONPATH := $(CURDIR)/src$(if $(PYTHONPATH),:$(PYTHONPATH))

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
# Seal once, then score once; the score script refuses a second run.
wrr-transport-seal:
	PYTHONPATH=src $(PYTHON) scripts/245_multi_agency_prior_access_audit.py
	PYTHONPATH=src $(PYTHON) scripts/249_multi_agency_transport_seal.py --seal

wrr-transport-score:
	PYTHONPATH=src $(PYTHON) scripts/250_multi_agency_transport_score.py --unseal-score

# P2-03 companion dataset and static dashboard (tracked dataset in docs/companion,
# self-contained HTML in dist/companion).
wrr-companion:
	PYTHONPATH=src $(PYTHON) scripts/264_wrr_companion_dataset.py

# Fourth-review redesign on opened outcomes. No target acquisition is hidden
# behind these targets; public registration is a separate external dependency.
.PHONY: wrr-review-completion wrr-review-cases wrr-review-refits wrr-review-windows wrr-review-analyses wrr-review-deep wrr-review-inputs wrr-review-national wrr-review-prereg wrr-review-deployment wrr-review-paper wrr-review-check

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

wrr-review-paper:
	$(PYTHON) scripts/473_review_completion_evidence.py
	cd paper/wrr_tr && TEXINPUTS=.:../wrr/template: latexmk -pdf -interaction=nonstopmode -halt-on-error review_completion_article.tex
	cd paper/wrr_tr && TEXINPUTS=.:../wrr/template: latexmk -pdf -interaction=nonstopmode -halt-on-error review_completion_supporting.tex

wrr-review-check:
	$(PYTHON) -m pytest tests/test_wrr_review_completion.py tests/test_wrr_target_recovery.py tests/test_wrr_review_independent.py tests/test_wrr_review_national.py tests/test_wrr_review_windows.py tests/test_wrr_review_forcing_evidence.py tests/test_wrr_forcing_residual_history.py tests/test_wrr_national_coverage.py
	$(PYTHON) scripts/516_review_completion_archive_smoke.py
	$(PYTHON) scripts/474_review_completion_validate.py
	$(PYTHON) scripts/512_review_completion_delivery.py

wrr-review-completion:
	$(MAKE) wrr-review-cases
	$(MAKE) wrr-review-refits
	$(MAKE) wrr-review-windows
	$(MAKE) wrr-review-deep
	$(MAKE) wrr-review-inputs
	$(MAKE) wrr-review-analyses
	$(MAKE) wrr-review-deployment
	$(MAKE) wrr-review-national
	$(MAKE) wrr-review-prereg
	$(MAKE) wrr-review-paper
	$(PYTHON) scripts/472_review_completion_prereg.py
	$(MAKE) wrr-review-check
