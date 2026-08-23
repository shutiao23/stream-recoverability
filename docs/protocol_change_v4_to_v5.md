# Protocol amendment: CSDI scope and deep-training validity

This amendment was recorded on 2026-08-23 after validation-only stability
results were available and before a dense development-test aggregate existed.
It amends the executable v4 file in place so completed validation artifacts keep
their scientific identity; `protocol_amendment_id: v5` records the change.

## Evidence state at amendment

- CSDI validation mean skill was -0.157 relative to climatology (rank 11/13).
- Exactly 1 of 900 planned target-T dense scenarios was present:
  `SCI-DENSE-BLK-B1-T-D001-PUBLISHED_V2-DEVELOPMENT_TEST-R0101`.
- No dense aggregate, frontier, confidence interval, or cross-gap comparison existed.
- Measured CPU training time for CSDI seed 11 was about 8 hours.
- BRITS seeds 33 and 44 produced MAE 3.526 and 3.930 degC on the only one-day
  cell, while PCHIP produced 0.021 degC.
- Proposed seed 22 selected epoch 33; seeds 11 and 33 selected epochs 214 and 173.

## Changes

1. CSDI is removed from the formal frontier roster. It remains a probabilistic
   diagnostic at seed 11 for gaps 7, 30, 90, and 180 days only. A model below
   the climatology denominator cannot define the main frontier.
2. A deep checkpoint with `best_epoch < 50` is labelled `training_unstable` and
   cannot enter the formal roster. This applies in addition to the existing
   finite-value and epoch-cap checks.
3. The analytic recoverability-budget predictor is frozen from 2006--2015 only,
   before any dense aggregate is constructed.

The epoch floor is a validity repair made after seeing validation stability
evidence. It is not represented as an original preregistration, and affected
models cannot support a "deep learning is ineffective" claim without a stable
rerun. No model hyperparameter, mask, split, target, or development outcome was
tuned by this amendment.
