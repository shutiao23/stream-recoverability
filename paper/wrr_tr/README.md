# Current research manuscript

`review_completion_article.tex` and `review_completion_supporting.tex` are the current manuscript and supplement. Run `make review-report` to regenerate the five result figures, research report and PDFs from the existing revised results. Run `make review` to update the local workflow, which depends on existing source observations, model weights and daily-fit caches.

The current figures and manuscript inputs come from `scripts/524_research_report.py`, using `results/wrr_review_response_20261027`. The study architecture has an editable draw.io source; the evaluated release and selected-trend diagram has an editable Graphviz source. The censored trend is an exploratory working likelihood, not a calibrated missing-data uncertainty guarantee.

The compact bibliography audit is in `../../docs/reviews/wrr_reference_audit_20261026.md`. Earlier annual-comparison tables and numerical macros remain produced by `scripts/473_review_completion_evidence.py`; these historical analyses are retained with their original scope.

See [the current research report](../../docs/SIMPLE_WORKFLOW_ZH.md) and [claim/evidence table](../../docs/CLAIM_EVIDENCE_ZH.md). New Zealand, NEON, a fresh USGS cohort and five Réunion sites do not provide eligible external reconstruction references under their recorded criteria. A separate earlier USGS intake supplies observation-only witnesses but cannot validate recovery accuracy. Author details, provider permissions and durable data/software deposits remain unresolved; the local staging bundle is not a completed submission package.

Older `wrr_tr_manuscript.tex`, transfer versions and their numerical inputs are historical versions, not the current manuscript.

The supplement now uses the publisher-named `agutexSI2019` class; its source and retrieval limitations are recorded in `../wrr/template/AGU_SI_PROVENANCE.md`. The wrapper retains embedded summary tables through the class's saved standard LaTeX float interfaces. The format change retains the scientific body and all 34 text sections and 40 tables. Current task-level evidence and incomplete external requirements are listed in `../../docs/reviews/wrr_review_response_20261027/RESPONSE_TO_TASKBOOK_20261027_ZH.md`.
