PYTHON ?= python

.PHONY: test evidence-snapshot hosting-audit submission-gate p0-protocol reproduce-paper validate-review-revision

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
	@echo "Rebuilding the major-revision analysis, figures, tables, and manifests."
	$(PYTHON) scripts/34_run_major_revision.py
	$(PYTHON) scripts/35_validate_review_revision.py

validate-review-revision:
	$(PYTHON) scripts/35_validate_review_revision.py
