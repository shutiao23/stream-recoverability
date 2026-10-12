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
		$(PYTHON) scripts/188_v17_figures.py
	WRR_JOURNAL_FIGURES=1 WRR_FIGURE_DIR=$(CURDIR)/paper/wrr/figures \
		$(PYTHON) scripts/204_v17_figures_q1.py
	WRR_JOURNAL_FIGURES=1 WRR_FIGURE_DIR=$(CURDIR)/paper/wrr/figures \
		$(PYTHON) scripts/220_v18_figures.py
	$(PYTHON) scripts/205_v17_drawio_export.py
	cp figures/v17/f0_problem_frame.pdf figures/v17/f1_system_architecture.pdf \
	   figures/v17/f2_experiment_design.pdf figures/v17/f3_evidence_chain.pdf \
	   figures/v17/f4_deployment_workflow.pdf paper/wrr/figures/

wrr-check:
	$(PYTHON) scripts/223_wrr_build.py --skip-build

# Submission-readiness tree: evidence identity, manifests, predict deploy, preflight.
# Does not invent author metadata; build remains NOT submission-ready until humans fill
# metadata/submission_author_metadata.json.
wrr-submission-ready:
	PYTHONPATH=src $(PYTHON) scripts/229_wrr_preflight.py
	PYTHONPATH=src $(PYTHON) scripts/232_wrr_measurement_provenance.py
	PYTHONPATH=src $(PYTHON) scripts/228_wrr_rebuild_from_inputs.py
	PYTHONPATH=src $(PYTHON) scripts/231_wrr_certificate_deploy_predict.py
	$(PYTHON) scripts/223_wrr_build.py --skip-build
	@echo "See results/wrr_submission_ready/STATUS.md and SUBMISSION_CHECKLIST.md"
