# P0 execution status

This file records what the P0 wave actually completed. It is not a results
paper and it does not waive the submission gate.

| ID | Status | Honest note |
| --- | --- | --- |
| P0-00 | Protocol complete; GitHub admin settings not flipped from here | Snapshot helper and CI record exist. Branch protection needs repository admin. |
| P0-01 | Recorded, not history-rewritten | Restricted bytes remain on the public tip. Audit script writes the defect. Git history is not rewritten in this wave. |
| P0-02 | Complete | Split QC fields are implemented. `published_v2` and the three v2 sensitivities were built from `published_v1` and named in `design_freeze_v3.yaml`. Provider QC is `unknown`, never `approved`. |
| P0-03 | Complete | `design_freeze_v3.yaml` and `docs/protocol_change_v2_to_v3.md`. Formal epoch budget is 400. |
| P0-04 | Pipeline ready; not silently stamped from v2 | Stage 1/2 must be re-run under the v3 hash. Old 945 units are not v3 evidence. |
| P0-05 | Gate implemented; roster absent | `hit_epoch_limit` is `budget_unstable`. No roster is issued from stale diagnostics. |
| P0-06 | Blocked on roster | Formal suites cannot start. |
| P0-07 | Estimators implemented; no numbers | Dual frontiers and donor-C falsification run only on complete formal tables. |
| P0-08 | Blocked on roster | Feasibility-only remains forbidden before roster freeze. |
| P0-09 | Blocked on P0-08 | Evaluate-once is not opened. |
| P0-10 | Infrastructure only | Makefile, Dockerfile, snapshot, and gate exist. No DOI is invented. |
| P0-11 | Consistency rewrite | RESULTS_PENDING remains. 6,000-scenario and local-vs-official contradictions are repaired. |
| P0-12 | Fail-closed | `scripts/27_submission_gate.py` is `no_go` until formal evidence exists. |
