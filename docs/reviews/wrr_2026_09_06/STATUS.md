# WRR revision execution status

Objective: close the evidence chain in `REVIEW.md` so the paper can be
resubmitted without law/threshold claims the experiments do not support.

## Done (parent-verified)

| Step | Artifact | Verdict |
|---|---|---|
| 1 | `PROBLEM_DEFINITION.md`, `EXPERIMENT_PROTOCOL.md` | Frozen: offline repair, adopt/reject, hottest-30 primary |
| 2 | `results/wrr_revision/step2_fair_recovery/` 42/42 networks | Neighbour-boundary training creates the long-gap collapse; long-block and donor-only do not |
| 2b | `step2_external/` 17 POWER networks | Air ridge stays positive and weaker than donors; no air2stream (no discharge) |
| 3–4 | `step3_4_decision/` | `diff` ≡ seasonal empirical; MAE adopt/reject beats all-default on P0 pooled, **fails** second-panel 180 d |
| 5 | `step5_failures/` 42 networks | Donor co-missing and missing right boundary require reject-to-default |
| 6 | `step6_frozen_replay/` 42 nets, 11,066 cases | Ranked +0.194 hottest-30 vs always-donor +0.278; ranking loses |
| 7 | `step7_mechanism/` | Universal law dropped; AR(1) bridge never crosses |
| 8 recoverers | `step8_confirmation/` 36/36 eligible nets | Neighbour vs donor/long-block split transfers |
| 8 replay | `step8_frozen_replay/` 36 nets, 2,512 cases | Ranked +0.131 vs always-donor +0.133; mixed cases tied |
| Freeze | `DESIGN_FREEZE.json` | Duration switch + donor/right-boundary gates; law withdrawn; **not retuned** after confirmation |

## Claim the paper may make

The published neighbour-boundary trainer is a correctable training/feature
failure, not a recoverability law. Donor-only (or long-block / no-boundary)
stays beneficial at 180–365 d when donors and both flanks exist. A pre-fixed
recoverer plus donor/right-boundary gates improves hottest-30 relative to
all-default and a ≤30 d seasonal rule on held-out networks. A `τ=0` ranked
rule also beats all-default but is not stronger than always reconstructing
when those gates pass. That is an applicability result.

Johnson 49 d is not used as validation. The second panel is descriptive.

Sparse-history copies (biased pooled ranking) remain in
`step6_frozen_replay_sparse_hist/` and `step8_frozen_replay_sparse_hist/`.
