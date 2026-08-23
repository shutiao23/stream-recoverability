# Boundary ledger

## BL-001 — Proposed model versus donor regression

**Observed.** Proposed lost to donor regression in 27 of 36 difficult validation
cells. Proposed seed 22 had overall skill -0.667, long-gap skill -0.606, and
outage skill -0.756; it selected epoch 33 versus 214 and 173 for seeds 11 and 33.

**Expected.** The gated multisource model was expected to equal or exceed donor
regression on compound or long gaps.

**Difference decomposition.** Experimental validity is implicated because one
required seed selected a premature checkpoint. A regime boundary is also
plausible: train-only anomaly donor $R^2$ is 0.464 at B1, 0.470 at S2, and 0.106
at P3. The validation objective itself includes point, short-block, long-block,
and station-outage masks, losses are finite, and scaling is seed-independent.

**Claim update.** C3, "the proposed model adds value," is withdrawn. C3' asks
whether any stable learner exceeds the frozen analytic information budget.
Unstable runs cannot answer that question. The gated architecture remains an
ablation instrument for mechanism consistency, not a performance contribution.

**Next action.** Apply the `best_epoch >= 50` roster validity rule and compare
only stable formal models with the prediction frozen before dense aggregation.

## BL-002 — CSDI compute scope

**Observed.** CSDI validation skill was -0.157 (rank 11/13). At amendment time,
one of 900 dense scenarios and no aggregate existed; one CPU seed required about
eight hours of training.

**Claim update.** CSDI cannot define the main frontier. It is retained only as a
seed-11 probabilistic diagnostic at gaps 7, 30, 90, and 180 days.

**Boundary.** This is a scope amendment after validation evidence and before a
dense aggregate, recorded in `docs/protocol_change_v4_to_v5.md`.

## BL-003 — External station typology before evaluate-once

**Observed without performance.** Feasibility passed 60/60 scenarios. A
2012--2020 train-only covariance calculation classified four Chattahoochee sites
as donor-dominated and one as memory-dominated.

**Prediction.** The four donor-dominated sites should show comparatively flat
long-gap curves; site 02334430 should decay more strongly with gap length.

**Boundary.** No model was trained, no recovery metric was computed, and no
once-lock was created. Whether these predictions are accurate remains unopened.
