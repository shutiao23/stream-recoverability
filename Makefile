PYTHON ?= python

.PHONY: test evidence-snapshot hosting-audit submission-gate p0-protocol reproduce-paper

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
	@echo "Rebuilding publication figures requires a complete current-protocol formal bundle."
	$(PYTHON) scripts/27_submission_gate.py
	$(PYTHON) scripts/11_make_figures.py
