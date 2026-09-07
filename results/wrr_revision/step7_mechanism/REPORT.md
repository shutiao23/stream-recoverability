# Step 7 — generative mechanism battery

Command: `PYTHONPATH=src python scripts/164_wrr_mechanism.py` (seed=1).
The generating process is a seasonal mean plus a residual AR(1), with optional
air and donor terms. `structurally_correct` is an AR(1) bridge on residuals
(high-memory) or the correctly specified ridge (air / donor / season).
Crossing means mean MAE benefit \(\le 0\) on any length in
`(7, 14, 30, 60, 90, 120, 150, 180, 365)`.

## Decision: drop the universal recoverability-law claim

`structurally_correct` does not cross in any of the four systems.
A duration threshold that is supposed to be an information law would have to
appear for the correctly specified recoverer. It does not.

`summary.json`: `retain_universal_law=false`,
`decision=drop_law_claim_write_as_prediction_and_decision`.

## Verdicts

| scenario | neighbor crosses | long-block crosses | structurally correct crosses | predeclaration |
|---|---|---|---|---|
| high_memory_weak_donor | yes (min B −4.24) | no (+0.072) | no (+0.291) | neighbor yes, struct no — match |
| low_memory_strong_donor | no (+0.407) | no (+0.408) | no (+0.406) | neither — match |
| air_driven | yes (min B −0.199) | no (+0.053) | no (+0.331) | neighbor yes, struct no — match |
| no_information_loss | yes (min B −0.016) | no (+0.047) | no (+0.046) | neither; neighbor has a tiny miss |

The neighbor/long-block split in `high_memory_weak_donor` and `air_driven` is
training mismatch: same gaps and features, only the training geometry changes,
and the crossing disappears. The tiny neighbor crossing under
`no_information_loss` is the same point in miniature: a model that is not
nested in climatology can go slightly negative without any information limit.

Linear interpolation is scored as a separate recoverer, not as the structural
benchmark.
