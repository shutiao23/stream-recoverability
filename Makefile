PYTHON ?= python

.PHONY: test evidence-snapshot hosting-audit submission-gate p0-protocol reproduce-paper reproduce-paper-full validate-review-revision research-charter recoverability-framework check-public-rivers download-build-rivers download-catalog-v2 catalog-v3-huc8 score-natural-outages gap-triage v2-operator-ablation w2-phase4-gap-specific hubeau-daily uk-ea-catalog uk-ea-daily uk-ea-spatial matched-regulation public-confirmatory-lock ingest-qc-clearwater national-temperature-catalog reservoir-operations-check apply-catalog-clusters

test:
	$(PYTHON) -m pytest

evidence-snapshot:
	$(PYTHON) scripts/25_build_evidence_snapshot.py

hosting-audit:
	$(PYTHON) scripts/26_audit_restricted_hosting.py

submission-gate:
	$(PYTHON) scripts/27_submission_gate.py --allow-no-go

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
