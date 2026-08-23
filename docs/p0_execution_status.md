# P0 execution status

This file records what the P0 wave actually completed. It is not a results
paper and it does not waive the submission gate.

| ID | Status | Honest note |
| --- | --- | --- |
| P0-00 | Protocol complete; GitHub admin settings not flipped from here | Snapshot helper and CI record exist. Branch protection needs repository admin. |
| P0-01 | Recorded, not history-rewritten | Restricted bytes remain on the public tip. Audit script writes the defect. Git history is not rewritten in this wave. |
| P0-02 | Complete | Split QC fields are implemented. `published_v2` and the three v2 sensitivities were built from `published_v1`. Provider QC is `unknown`, never `approved`. Artifact hashes are not pinned in the freeze. |
| P0-03 | Complete | `design_freeze_v4.yaml` and `docs/protocol_change_v3_to_v4.md`. Formal epoch budget remains 400. |
| P0-04 | Contract migration complete; rerun pending | Selection, roster, formal, confirmatory, registry, aggregation, and analysis derive `published_v2` from v4. Old runs remain historical. |
| P0-05 | Gate implemented at roster freeze; roster still absent | Stage 2 already rejects a seed-11 cap hit. Stage 3 now excludes any finalist whose required seed has `hit_epoch_limit=true`. The v4 roster loader reads `validation_anchors_v2.csv`. |
| P0-06 | Blocked on roster | Formal suites cannot start. |
| P0-07 | Formal suite and analysis wiring complete; no numbers | v4 provides the same-checkpoint donor-C runner and requires the validation-frozen best-simple lookup, dual frontiers, and donor-C effects/decision artifacts. |
| P0-08 | Blocked on roster | Feasibility-only remains forbidden before roster freeze. |
| P0-09 | Blocked on P0-08 | Evaluate-once is not opened. |
| P0-10 | Infrastructure only | Makefile, Dockerfile, snapshot, and gate exist. No DOI is invented. |
| P0-11 | Consistency rewrite | RESULTS_PENDING remains. 6,000-scenario and local-vs-official contradictions are repaired. |
| P0-12 | Fail-closed | `scripts/27_submission_gate.py` is `no_go` until formal evidence exists. |
| P0.1-v5 | Complete | The old dense process was stopped with 1/900 scenarios present. CSDI is diagnostic-only at seed 11 and gaps 7/30/90/180. |
| P0.2-v5 | Complete | Validation objective/scaler/loss histories were diagnosed. `best_epoch < 50` is now `training_unstable` and excludes a model from the roster. |
| P0.3-v5 | Complete | `recoverability_prediction_v1.json` is frozen from 2006--2015 before a dense aggregate. |
| P1-v5 | Complete | Claim matrix converted to an effect ledger; `paper/boundary_ledger.md` records counterevidence and claim changes. |
