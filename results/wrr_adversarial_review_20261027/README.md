# Adversarial-review revision evidence

This directory contains the post-review analyses added for the 2026-10-27 revision. The scripts that generate them are `scripts/926_rule_accounting.py` through `scripts/929_manuscript_inputs.py`.

## Contents

- `figure_cohort_audit.json` — audit of the old 820-row versus 807-row retention contrast. `all_paired_rmse` is the all-year RMSE on the common 807 station-repetition rows (0.1695); the old figure used the 820-row value (0.1735). Figure 3 now uses the common cohort.
- `rule_accounting/` — all 2,700 eligible station-years under explicit completeness rules, the two excluded warm-season witnesses (0.150 and 0.113 °C above the rule-accepted record), measurement-margin sensitivity, and the admitted new-window facts.
- `failure_strata/` — peak-visibility, gap-length, training-peak-overlap, visible-donor and region strata on the common crossed forward cases, plus group-bootstrap intervals and leave-one-region-out differences.
- `rank_convergence/` — fixed-marginal numerical sensitivity for independent ranks, auxiliary shared-parameter ranks and three-year residual blocks at 256, 1,024 and 4,096 stratified samples with three seeds. The larger-sample runs use separately stratified annual marginals, not prefixes of a larger marginal grid.
- `metadata_correction/` — correction statement for the 3,320 historical `design.json` files. The original files were not rewritten.

## Limits

- Repeated masks are not independent rivers or climates.
- The peak-visibility stratum uses the withheld complete reference and is unavailable at decision time.
- The rank constructions are dependence sensitivities, not posterior samples or coverage theorems.
- The reported check uses 256, 1,024 and 4,096 samples. The 16,384-draw extension was not required; at 4,096 samples, five of six constructions meet the 0.3-point coverage-stability rule and undercoverage persists.
- Group bootstrap intervals describe the sampled archive, not a population guarantee.
- All analyses use saved predictions and opened data; they do not constitute independent external validation.
