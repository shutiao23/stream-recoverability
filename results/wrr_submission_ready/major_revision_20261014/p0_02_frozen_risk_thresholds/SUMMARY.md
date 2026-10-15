# P0-02 — frozen, pre-registered admission thresholds

Replaces the post-hoc operating point of `scripts/305_wrr_mr_step6_calibration_decision.py::max_retention_under_risk`, which searched the *evaluation* set's true errors for the largest retention with a realised false-admit rate <= 5%. That rule is not deployable: at deployment the labels do not exist. This script implements the honest version and reports both, side by side.

## Version note — corrected `length_rule` number (read before citing)

Two internal runs preceded this file. The first (fold seed 101 only, 200 bootstrap draws, written 09:56 local and overwritten since) reported `length_rule` honest retention **1.72%** with a realised false-admit rate of **9.38%**, with **4 of 5** length-rule folds admitting nothing (`no_admissible_grid_point`). **That number is wrong and is withdrawn.**

Cause: the tie-break helper multiplied its jitter scale by the score's observed spread. For `longest_run` (scale 1.0 day, spread 280.0 days on the primary panel) the noise reached hundreds of days, so the object being evaluated was `longest_run + U[0, spread)` — very close to a random permutation of candidates — and not a completeness rule at all. `peak_overlap_rule` (spread 1.0) and the two certificate bounds (relative 1e-9 x spread) were unaffected, which is why their first-pass numbers already match this file.

Fix: jitter is now added in the score's own units — `longest_run + U[0,1)` day, exactly the construction in scripts 301/305 — and the relative form is used only for the continuous bound and risk scores. `scripts/311_wrr_p0_02_frozen_risk_thresholds.py` at this revision contains only the corrected code.

Exact orientation test on the delivered score (not a correlation, a monotonicity check): 
    - `wave2_confirmation`: sorting all cases by the evaluated `length_rule` score leaves the raw `longest_run` column non-decreasing (True); distinct gap lengths are 137 integer values, minimum spacing 1.0 day, so the <1-day jitter can only break ties inside a gap-length block.
    - `development`: sorting all cases by the evaluated `length_rule` score leaves the raw `longest_run` column non-decreasing (True); distinct gap lengths are 132 integer values, minimum spacing 1.0 day, so the <1-day jitter can only break ties inside a gap-length block.

Reproduction of the withdrawn number and the orientation evidence are kept in `scratch/p0_02/verify_311_version_note.py` and its output `scratch/p0_02/version_note_evidence.json` (the buggy score is rebuilt there and the first pass reproduces exactly: pooled retention 1.72%, false-admit 9.375%, 224 admitted, 4 folds admitting nothing, fold-4 threshold 73.009935). The same artifact shows the inverted orientation is not in play: admitting longest-gap-first would give a 38.7% false-admit rate at 10% retention, whereas the delivered rule admits shortest-gap-first (raw gap <= 30 days: 50.1% of candidates at 4.06% false-admit).

Corrected numbers to cite: the `## Headline` table below.

## Protocol (frozen before any result below was computed)

1. Candidate pools. Primary: `results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/wave2_cases.parquet` (13,017 cases / 49 networks) row-joined by position with `wave2_certificates.parquet`. Secondary sanity replication: `results/v17_fitness/step4_ceiling/development_cases.parquet` (40,704 cases / 110 networks) with `development_certificates.parquet`.
2. Alignment is *proved*, not assumed: equal length, and for every row `certificate_metric == metric_<certificate_choice>` together with `certificate_abs_error == |certificate_metric - truth_metric|`.
3. Target event: `certificate_abs_error > 0.5` C. `abserr_policy` is substituted only where the certificate value is missing (fallbacks — wave2_confirmation: 0, development: 0; cases with neither error would count as consequential, none do here).
4. Scores: `length_rule`, `peak_overlap_rule`, `fitted_risk`, `uncalibrated_bound`, `calibrated_bound` plus supplementary `fitted_risk_certtarget`. All are deterministic given the inputs.
5. 5-fold cross-fitting by `network_id` (never by case), repeated under fold seeds [101, 202, 303].
6. Per fold: fit the score model on the other folds; choose the admission threshold on those calibration folds only. Grid = calibration score quantiles at retention 0.10..0.95 step 0.01. Rule = the largest calibration retention whose calibration false-admit rate plus a one-sided 95% upper bound is <= 5%. Bound = `network_clustered_bootstrap_onesided95_percentile` (1000 draws). The exact binomial (Clopper-Pearson) bound is computed next to it; the frozen rule uses the clustered bound because cases are clustered in networks and a case-level binomial bound would assume independence the design does not have.
7. The frozen threshold is applied to the held-out fold exactly once; nothing downstream re-selects an operating point.
8. The pooled held-out folds are the headline estimate, labelled "cross-fitted, selection honest".
9. For `fitted_risk` the calibration-fold scores are inner out-of-fold predictions (4 inner network folds) and the held-out fold is scored by a model refit on all calibration cases.

## Headline — honest cross-fitted protocol (pooled held-out folds)

### wave2_confirmation (13,017 cases, 49 networks, error rate 15.96%)

                 score  fold seed retention ret CI lo ret CI hi false-admit FA CI lo FA CI hi  admitted  cases  nets
      calibrated_bound        101    76.36%    73.82%    78.77%       3.89%    3.15%    4.74%      9940  13017    49
      calibrated_bound        202    76.81%    74.15%    79.34%       4.04%    3.31%    4.85%      9998  13017    49
      calibrated_bound        303    76.79%    74.08%    79.33%       4.08%    3.33%    4.95%      9996  13017    49
           fitted_risk        101    74.38%    71.11%    77.33%       3.74%    2.98%    4.59%      9682  13017    49
           fitted_risk        202    76.15%    72.97%    79.09%       4.16%    3.15%    5.36%      9913  13017    49
           fitted_risk        303    75.98%    72.76%    78.98%       4.29%    3.38%    5.41%      9890  13017    49
fitted_risk_certtarget        101    75.62%    72.95%    78.05%       3.82%    3.14%    4.61%      9844  13017    49
fitted_risk_certtarget        202    76.11%    73.32%    78.63%       3.81%    3.09%    4.69%      9907  13017    49
fitted_risk_certtarget        303    76.53%    73.83%    78.97%       4.03%    3.23%    4.97%      9962  13017    49
           length_rule        101    48.81%    46.58%    50.66%       3.87%    2.87%    5.04%      6353  13017    49
           length_rule        202    49.06%    46.93%    50.84%       3.87%    2.96%    5.01%      6386  13017    49
           length_rule        303    48.87%    46.86%    50.36%       3.79%    2.85%    5.05%      6362  13017    49
     peak_overlap_rule        101    71.67%    70.12%    73.00%       4.03%    3.22%    4.98%      9329  13017    49
     peak_overlap_rule        202    71.96%    70.53%    73.26%       4.05%    3.24%    4.90%      9367  13017    49
     peak_overlap_rule        303    71.84%    70.17%    73.14%       4.00%    3.20%    4.92%      9352  13017    49
    uncalibrated_bound        101    76.36%    73.82%    78.77%       3.89%    3.15%    4.74%      9940  13017    49
    uncalibrated_bound        202    76.81%    74.15%    79.34%       4.04%    3.31%    4.85%      9998  13017    49
    uncalibrated_bound        303    76.79%    74.08%    79.33%       4.08%    3.33%    4.95%      9996  13017    49

Across fold seeds (descriptive; the per-seed rows above carry the intervals):

                 score retention_mean retention_min retention_max fa_mean fa_min fa_max
      calibrated_bound         76.65%        76.36%        76.81%   4.01%  3.89%  4.08%
           fitted_risk         75.50%        74.38%        76.15%   4.06%  3.74%  4.29%
fitted_risk_certtarget         76.09%        75.62%        76.53%   3.88%  3.81%  4.03%
           length_rule         48.91%        48.81%        49.06%   3.84%  3.79%  3.87%
     peak_overlap_rule         71.82%        71.67%        71.96%   4.03%  4.00%  4.05%
    uncalibrated_bound         76.65%        76.36%        76.81%   4.01%  3.89%  4.08%

### development (40,704 cases, 110 networks, error rate 14.56%)

                 score  fold seed retention ret CI lo ret CI hi false-admit FA CI lo FA CI hi  admitted  cases  nets
      calibrated_bound        101    75.95%    73.02%    78.43%       4.15%    3.42%    4.99%     30913  40704   110
      calibrated_bound        202    76.00%    73.17%    78.66%       4.14%    3.43%    4.97%     30937  40704   110
      calibrated_bound        303    75.62%    72.69%    78.20%       4.05%    3.34%    4.85%     30779  40704   110
           fitted_risk        101    73.45%    69.81%    77.15%       3.96%    3.17%    4.98%     29898  40704   110
           fitted_risk        202    74.00%    70.57%    77.85%       3.97%    3.37%    4.75%     30119  40704   110
           fitted_risk        303    75.69%    72.76%    78.86%       4.69%    3.76%    5.85%     30810  40704   110
fitted_risk_certtarget        101    74.01%    70.03%    78.03%       3.98%    3.23%    4.97%     30125  40704   110
fitted_risk_certtarget        202    74.70%    71.35%    78.63%       4.03%    3.39%    4.89%     30407  40704   110
fitted_risk_certtarget        303    75.81%    72.60%    79.23%       4.58%    3.69%    5.76%     30859  40704   110
           length_rule        101    38.81%    35.43%    42.00%       4.08%    3.33%    5.10%     15798  40704   110
           length_rule        202    39.34%    35.78%    42.65%       4.03%    3.32%    5.01%     16011  40704   110
           length_rule        303    38.48%    35.17%    41.54%       3.95%    3.22%    4.94%     15664  40704   110
     peak_overlap_rule        101    65.75%    64.06%    67.41%       4.23%    3.57%    4.94%     26762  40704   110
     peak_overlap_rule        202    66.05%    64.19%    67.72%       4.26%    3.58%    4.95%     26884  40704   110
     peak_overlap_rule        303    65.96%    64.24%    67.72%       4.25%    3.58%    4.98%     26847  40704   110
    uncalibrated_bound        101    76.00%    73.09%    78.63%       4.12%    3.44%    4.93%     30934  40704   110
    uncalibrated_bound        202    76.23%    73.35%    79.00%       4.18%    3.52%    5.00%     31030  40704   110
    uncalibrated_bound        303    75.73%    72.88%    78.43%       4.07%    3.40%    4.91%     30824  40704   110

Across fold seeds (descriptive; the per-seed rows above carry the intervals):

                 score retention_mean retention_min retention_max fa_mean fa_min fa_max
      calibrated_bound         75.86%        75.62%        76.00%   4.11%  4.05%  4.15%
           fitted_risk         74.38%        73.45%        75.69%   4.21%  3.96%  4.69%
fitted_risk_certtarget         74.84%        74.01%        75.81%   4.20%  3.98%  4.58%
           length_rule         38.88%        38.48%        39.34%   4.02%  3.95%  4.08%
     peak_overlap_rule         65.92%        65.75%        66.05%   4.25%  4.23%  4.26%
    uncalibrated_bound         75.99%        75.73%        76.23%   4.12%  4.07%  4.18%

## Folds that admitted nothing

0 of 180 (score x fold seed x fold) cells admitted nothing.

Every fold found an admissible grid point, so no fold fell back to admitting nothing.

Clustered vs exact-binomial selection disagreed on whether *any* grid point qualifies in 0 of 180 cells; the frozen rule uses the clustered bound. Clustered-vs-binomial retained fractions per cell are in `crossfit_risk_cap_table.csv`.
A simultaneous (Bonferroni over the 86 grid points) clustered bound would have reached the same admit-nothing verdict in 180 of 180 cells; the Bonferroni retention for every cell is in `crossfit_risk_cap_table.csv` (`bonferroni_retention`).

## RETROSPECTIVE / not deployable vs honest (same scores, same panel)

### wave2_confirmation

                 score posthoc_retention posthoc_false_admit  posthoc_admitted honest_retention honest_false_admit retention_gap_pp false_admit_gap_pp
      calibrated_bound            79.00%               4.88%             10283           76.65%              4.01%            -2.35              -0.88
           fitted_risk            77.00%               4.82%             10023           75.50%              4.06%            -1.50              -0.76
fitted_risk_certtarget            78.00%               4.72%             10153           76.09%              3.88%            -1.91              -0.83
           length_rule            55.00%               4.87%              7159           48.91%              3.84%            -6.09              -1.03
     peak_overlap_rule            75.00%               4.99%              9763           71.82%              4.03%            -3.18              -0.96
    uncalibrated_bound            79.00%               4.88%             10283           76.65%              4.01%            -2.35              -0.88

- `calibrated_bound`: honest minus post-hoc retention -2.35 pp; honest minus post-hoc false-admit rate -0.88 pp.
- `fitted_risk`: honest minus post-hoc retention -1.50 pp; honest minus post-hoc false-admit rate -0.76 pp.
- `fitted_risk_certtarget`: honest minus post-hoc retention -1.91 pp; honest minus post-hoc false-admit rate -0.83 pp.
- `length_rule`: honest minus post-hoc retention -6.09 pp; honest minus post-hoc false-admit rate -1.03 pp.
- `peak_overlap_rule`: honest minus post-hoc retention -3.18 pp; honest minus post-hoc false-admit rate -0.96 pp.
- `uncalibrated_bound`: honest minus post-hoc retention -2.35 pp; honest minus post-hoc false-admit rate -0.88 pp.

Verbatim `scripts/305_wrr_mr_step6_calibration_decision.py::admission_table` output on the same inputs (this is what the manuscript currently quotes, with that function's own tie-break draw):

             score retention false_admit_rate  n_admitted
       length_rule    55.00%            4.82%        7159
 peak_overlap_rule    74.00%            4.67%        9633
uncalibrated_bound    79.00%            4.88%       10283
  calibrated_bound    79.00%            4.88%       10283

Where the verbatim row and the `posthoc_*` row disagree for `length_rule` / `peak_overlap_rule`, the cause is the tie-break draw over a coarse discrete score, not the risk cap: the old post-hoc frontier is not even reproducible across tie-break seeds.

### development

                 score posthoc_retention posthoc_false_admit  posthoc_admitted honest_retention honest_false_admit retention_gap_pp false_admit_gap_pp
      calibrated_bound            79.00%               4.97%             32156           75.86%              4.11%            -3.14              -0.86
           fitted_risk            77.00%               4.89%             31342           74.38%              4.21%            -2.62              -0.69
fitted_risk_certtarget            77.00%               4.83%             31342           74.84%              4.20%            -2.16              -0.63
           length_rule            49.00%               4.99%             19945           38.88%              4.02%           -10.12              -0.97
     peak_overlap_rule            68.00%               4.76%             27679           65.92%              4.25%            -2.08              -0.51
    uncalibrated_bound            79.00%               4.85%             32156           75.99%              4.12%            -3.01              -0.73

- `calibrated_bound`: honest minus post-hoc retention -3.14 pp; honest minus post-hoc false-admit rate -0.86 pp.
- `fitted_risk`: honest minus post-hoc retention -2.62 pp; honest minus post-hoc false-admit rate -0.69 pp.
- `fitted_risk_certtarget`: honest minus post-hoc retention -2.16 pp; honest minus post-hoc false-admit rate -0.63 pp.
- `length_rule`: honest minus post-hoc retention -10.12 pp; honest minus post-hoc false-admit rate -0.97 pp.
- `peak_overlap_rule`: honest minus post-hoc retention -2.08 pp; honest minus post-hoc false-admit rate -0.51 pp.
- `uncalibrated_bound`: honest minus post-hoc retention -3.01 pp; honest minus post-hoc false-admit rate -0.73 pp.

Verbatim `scripts/305_wrr_mr_step6_calibration_decision.py::admission_table` output on the same inputs (this is what the manuscript currently quotes, with that function's own tie-break draw):

             score retention false_admit_rate  n_admitted
       length_rule    48.00%            4.94%       19538
 peak_overlap_rule    68.00%            4.79%       27679
uncalibrated_bound    79.00%            4.85%       32156
  calibrated_bound    79.00%            4.97%       32156

Where the verbatim row and the `posthoc_*` row disagree for `length_rule` / `peak_overlap_rule`, the cause is the tie-break draw over a coarse discrete score, not the risk cap: the old post-hoc frontier is not even reproducible across tie-break seeds.

`posthoc_*` = `max_retention_under_risk` on the whole panel, i.e. the operating point is chosen with the evaluation labels (RETROSPECTIVE / not deployable). `honest_*` = mean over fold seeds of the cross-fitted pooled held-out result. A large negative retention gap is the headline disagreement: the published frontier bought its retention with labels the agency will not have.

## Equal-risk and equal-retention contrasts (defect F03)

At the common frozen <=5% risk target the comparison is on retention; at a pre-declared 70% retention the comparison is on the false-admit rate. Both are paired network-clustered contrasts with 95% intervals, in percentage points.

### wave2_confirmation — risk_cap_5pct_frozen (retention, pp)

       score_left        score_right point_pp point_min_pp point_max_pp ci_low_min ci_high_max  ci_excludes_zero_all_seeds
      fitted_risk        length_rule    26.59        25.57        27.10      22.12       30.25                        True
peak_overlap_rule        length_rule    22.91        22.86        22.97      21.41       24.89                        True
      fitted_risk  peak_overlap_rule     3.68         2.71         4.19      -0.07        6.85                       False
 calibrated_bound uncalibrated_bound     0.00         0.00         0.00       0.00        0.00                       False
      fitted_risk   calibrated_bound    -1.15        -1.98        -0.65      -4.21        1.42                       False
      fitted_risk uncalibrated_bound    -1.15        -1.98        -0.65      -4.21        1.42                       False
peak_overlap_rule uncalibrated_bound    -4.83        -4.95        -4.69      -7.06       -2.56                        True
peak_overlap_rule   calibrated_bound    -4.83        -4.95        -4.69      -7.06       -2.56                        True
      length_rule   calibrated_bound   -27.74       -27.92       -27.56     -30.42      -24.83                        True
      length_rule uncalibrated_bound   -27.74       -27.92       -27.56     -30.42      -24.83                        True

### wave2_confirmation — fixed_retention_70_perfold (false_admit_rate, pp)

       score_left        score_right point_pp point_min_pp point_max_pp ci_low_min ci_high_max  ci_excludes_zero_all_seeds
      length_rule uncalibrated_bound     6.42         6.27         6.57       5.27        7.57                        True
      length_rule   calibrated_bound     6.42         6.27         6.57       5.27        7.57                        True
peak_overlap_rule   calibrated_bound     1.03         1.00         1.04       0.56        1.50                        True
peak_overlap_rule uncalibrated_bound     1.03         1.00         1.04       0.56        1.50                        True
 calibrated_bound uncalibrated_bound     0.00         0.00         0.00       0.00        0.00                       False
      fitted_risk   calibrated_bound    -0.28        -0.34        -0.23      -0.79        0.09                       False
      fitted_risk uncalibrated_bound    -0.28        -0.34        -0.23      -0.79        0.09                       False
      fitted_risk  peak_overlap_rule    -1.31        -1.34        -1.27      -1.91       -0.73                        True
peak_overlap_rule        length_rule    -5.40        -5.53        -5.22      -6.51       -4.32                        True
      fitted_risk        length_rule    -6.70        -6.84        -6.50      -8.03       -5.40                        True

### development — risk_cap_5pct_frozen (retention, pp)

       score_left        score_right point_pp point_min_pp point_max_pp ci_low_min ci_high_max  ci_excludes_zero_all_seeds
      fitted_risk        length_rule    35.50        34.64        37.21      29.12       43.40                        True
peak_overlap_rule        length_rule    27.04        26.71        27.47      23.45       31.50                        True
      fitted_risk  peak_overlap_rule     8.46         7.70         9.74       4.43       12.59                        True
 calibrated_bound uncalibrated_bound    -0.13        -0.23        -0.05      -1.08        0.82                       False
      fitted_risk   calibrated_bound    -1.48        -2.49         0.08      -5.93        3.25                       False
      fitted_risk uncalibrated_bound    -1.61        -2.55        -0.03      -5.78        2.74                       False
peak_overlap_rule   calibrated_bound    -9.94       -10.20        -9.66     -12.73       -6.68                        True
peak_overlap_rule uncalibrated_bound   -10.07       -10.25        -9.77     -12.83       -7.06                        True
      length_rule   calibrated_bound   -36.98       -37.13       -36.67     -42.47      -31.70                        True
      length_rule uncalibrated_bound   -37.11       -37.24       -36.90     -42.90      -31.88                        True

### development — fixed_retention_70_perfold (false_admit_rate, pp)

       score_left        score_right point_pp point_min_pp point_max_pp ci_low_min ci_high_max  ci_excludes_zero_all_seeds
      length_rule uncalibrated_bound     5.89         5.80         5.95       4.84        6.98                        True
      length_rule   calibrated_bound     5.78         5.69         5.84       4.74        6.88                        True
peak_overlap_rule uncalibrated_bound     2.37         2.31         2.41       1.72        2.98                        True
peak_overlap_rule   calibrated_bound     2.26         2.20         2.29       1.61        2.87                        True
      fitted_risk uncalibrated_bound     0.16         0.04         0.37      -0.39        1.24                       False
 calibrated_bound uncalibrated_bound     0.11         0.11         0.12      -0.08        0.31                       False
      fitted_risk   calibrated_bound     0.05        -0.06         0.25      -0.56        1.14                       False
      fitted_risk  peak_overlap_rule    -2.21        -2.35        -2.04      -2.96       -1.22                        True
peak_overlap_rule        length_rule    -3.52        -3.64        -3.40      -4.50       -2.70                        True
      fitted_risk        length_rule    -5.73        -5.87        -5.56      -7.08       -4.51                        True

Levels behind these contrasts (retention and realised false-admit rate per score) are in `crossfit_risk_cap_table.csv` and `posthoc_vs_honest.csv`.

### Absolute scale vs ranking: `calibrated_bound` vs `uncalibrated_bound`

- `wave2_confirmation`: Spearman rank correlation between `certificate_bound` and `certificate_raw_bound` is 0.992327; the frozen rule admits exactly the same cases for the two scores in every fold (paired contrast exactly 0.00 pp, CI [0.00, 0.00]).
- `development`: Spearman rank correlation between `certificate_bound` and `certificate_raw_bound` is 0.979748; the frozen rule admits exactly the same cases for the two scores in every fold (paired contrast exactly 0.00 pp, CI [0.00, 0.00]).

So the calibration changes the absolute scale of the bound far more than its ordering on these pools: the admitted sets coincide exactly in every fold of this run and the rank correlation is high but not 1.0, i.e. only near-tied cases are reordered. Any decision value it has must therefore come from the absolute-scale semantics (admit iff bound <= tolerance, compared in degrees C), not from screening or ranking gain. A claim of the form 'calibration improves the screen at fixed retention' is unsupported here: the screening gain at fixed retention belongs to the certificate *score*, not to its calibration. This script's risk-cap comparison cannot show the absolute-scale value; that comparison is out of scope.

## Cap compliance of the held-out folds

- Pooled held-out cells: 0 of 36 have a point false-admit rate above 5%; the worst point estimate is 4.69%.
- Their 95% network-clustered intervals exceed 5% at the upper end in 9 of 36 cells (worst upper end 5.85%). The cap is therefore met on every point estimate, but for those cells the data are consistent with a true rate above 5%.
- Individual held-out folds: 34 of 180 fold cells have a point false-admit rate above 5% (worst 8.66%). Folds are small (6-27 networks), so this is the expected granularity of the guarantee, not a violation of the calibration rule.

Cells whose pooled interval upper end exceeds the cap: `development/fitted_risk/seed303` 4.69% [3.76%, 5.85%]; `development/fitted_risk_certtarget/seed303` 4.58% [3.69%, 5.76%]; `development/length_rule/seed101` 4.08% [3.33%, 5.10%]; `development/length_rule/seed202` 4.03% [3.32%, 5.01%]; `wave2_confirmation/fitted_risk/seed202` 4.16% [3.15%, 5.36%]; `wave2_confirmation/fitted_risk/seed303` 4.29% [3.38%, 5.41%]; `wave2_confirmation/length_rule/seed101` 3.87% [2.87%, 5.04%]; `wave2_confirmation/length_rule/seed202` 3.87% [2.96%, 5.01%]; `wave2_confirmation/length_rule/seed303` 3.79% [2.85%, 5.05%]

## Sensitivity: simultaneous (Bonferroni) band instead of the frozen per-cell band

The frozen rule is the pre-registered per-cell clustered band: for each grid point, the one-sided 95% percentile of the network-clustered bootstrap FPR. Because the rule then takes the maximum over 86 grid points, a hostile reader can ask for a simultaneous band. The same computation is therefore repeated with the 1 - 0.05/86 percentile (`bonferroni_sensitivity_pooled` rows in `crossfit_risk_cap_table.csv`, `risk_cap_5pct_bonferroni_sensitivity` rows in `risk_cap_contrasts.csv`, and `pooled_eval_bonferroni_sensitivity` in the JSON). This is a robustness check, not the protocol; it was not used to choose any number above.

### wave2_confirmation — Bonferroni band (sensitivity)

                 score  fold_seed test_retention test_false_admit_rate test_false_admit_ci95_low test_false_admit_ci95_high  test_n_admitted
      calibrated_bound        101         74.86%                 3.41%                     2.72%                      4.19%             9745
      calibrated_bound        202         75.30%                 3.50%                     2.79%                      4.32%             9802
      calibrated_bound        303         75.06%                 3.46%                     2.81%                      4.26%             9770
           fitted_risk        101         72.89%                 3.15%                     2.51%                      3.84%             9488
           fitted_risk        202         74.36%                 3.49%                     2.61%                      4.53%             9679
           fitted_risk        303         74.03%                 3.48%                     2.64%                      4.56%             9636
fitted_risk_certtarget        101         74.14%                 3.31%                     2.62%                      4.08%             9651
fitted_risk_certtarget        202         74.95%                 3.44%                     2.75%                      4.31%             9756
fitted_risk_certtarget        303         75.49%                 3.58%                     2.87%                      4.48%             9827
           length_rule        101         44.02%                 2.88%                     1.92%                      4.13%             5730
           length_rule        202         44.45%                 2.75%                     1.89%                      3.97%             5786
           length_rule        303         43.22%                 2.60%                     1.69%                      3.77%             5626
     peak_overlap_rule        101         69.66%                 3.44%                     2.71%                      4.24%             9067
     peak_overlap_rule        202         70.51%                 3.52%                     2.78%                      4.38%             9178
     peak_overlap_rule        303         70.06%                 3.44%                     2.76%                      4.27%             9120
    uncalibrated_bound        101         74.99%                 3.51%                     2.80%                      4.30%             9761
    uncalibrated_bound        202         74.79%                 3.35%                     2.69%                      4.15%             9736
    uncalibrated_bound        303         75.06%                 3.46%                     2.81%                      4.26%             9770

### development — Bonferroni band (sensitivity)

                 score  fold_seed test_retention test_false_admit_rate test_false_admit_ci95_low test_false_admit_ci95_high  test_n_admitted
      calibrated_bound        101         73.17%                 3.55%                     2.83%                      4.30%            29782
      calibrated_bound        202         72.95%                 3.48%                     2.86%                      4.22%            29694
      calibrated_bound        303         73.25%                 3.54%                     2.89%                      4.28%            29814
           fitted_risk        101         70.67%                 3.11%                     2.51%                      3.86%            28767
           fitted_risk        202         71.84%                 3.41%                     2.85%                      4.21%            29243
           fitted_risk        303         74.05%                 4.26%                     3.40%                      5.36%            30143
fitted_risk_certtarget        101         71.18%                 3.12%                     2.56%                      3.84%            28975
fitted_risk_certtarget        202         72.74%                 3.58%                     2.95%                      4.39%            29610
fitted_risk_certtarget        303         73.04%                 3.85%                     3.03%                      4.89%            29729
           length_rule        101         34.69%                 3.31%                     2.62%                      4.20%            14122
           length_rule        202         35.25%                 3.16%                     2.52%                      4.04%            14350
           length_rule        303         34.54%                 3.24%                     2.52%                      4.15%            14059
     peak_overlap_rule        101         61.46%                 3.67%                     3.04%                      4.30%            25017
     peak_overlap_rule        202         61.44%                 3.73%                     3.09%                      4.37%            25010
     peak_overlap_rule        303         61.81%                 3.82%                     3.20%                      4.52%            25158
    uncalibrated_bound        101         73.75%                 3.57%                     2.91%                      4.32%            30019
    uncalibrated_bound        202         73.30%                 3.51%                     2.91%                      4.23%            29837
    uncalibrated_bound        303         73.23%                 3.50%                     2.86%                      4.28%            29806

- `wave2_confirmation`, equal-risk contrast `fitted_risk` minus `length_rule` under the Bonferroni band: 29.86 pp [25.51, 33.85].
- `development`, equal-risk contrast `fitted_risk` minus `length_rule` under the Bonferroni band: 37.36 pp [30.53, 45.10].

## What would falsify this — observed verdicts

- *Falsifier 1*: the honest pooled false-admit rate materially exceeds the 5% cap. Observed: 0 of 36 pooled cells above the cap; worst point 4.69%; 9 of 36 interval upper ends above the cap. Falsifier not triggered, but not fully excluded either.
- *Falsifier 2*: the honest retention is far below the post-hoc frontier at the same cap. Observed: honest minus post-hoc retention runs from -10.12 pp (`length_rule` on `development`) to -1.50 pp (`fitted_risk` on `wave2_confirmation`). For the certificate and fitted scores the loss is -3.14 to -1.50 pp across panels and seeds; for the two engineered rules it reaches -10.12 pp. The post-hoc frontier is optimistic everywhere. Falsifier triggered in direction, modest in magnitude for the scores the manuscript relies on.
- *Falsifier 3*: `calibrated_bound` fails to beat the engineered rules at equal risk / equal retention. Observed (positive = the first score keeps more / admits worse):
    - risk-cap retention, `calibrated_bound` minus `peak_overlap_rule` 7.38 pp (range 4.69 to 10.20), CI excludes 0 in every fold seed
    - risk-cap retention, `calibrated_bound` minus `length_rule` 32.36 pp (range 27.56 to 37.13), CI excludes 0 in every fold seed
    - 70%-retention false-admit rate, `peak_overlap_rule` minus `calibrated_bound` 1.64 pp (range 1.00 to 2.29), CI excludes 0 in every fold seed
    - risk-cap retention, `fitted_risk` minus `calibrated_bound` -1.31 pp (range -2.49 to 0.08), CI includes 0 in at least one fold seed
    - 70%-retention false-admit rate, `fitted_risk` minus `calibrated_bound` -0.11 pp (range -0.34 to 0.25), CI includes 0 in at least one fold seed
    - against `uncalibrated_bound` both contrasts are exactly 0.00 pp in every fold seed. Falsifier survives in the weak form 'the certificate score beats the engineered rules'; it is triggered for the strong form 'calibration itself adds decision value', and it is unresolved against `fitted_risk`.
- *Falsifier 4*: the selected retention swings widely across fold seeds. Observed: the widest per (panel, score) retention spread across the three fold seeds is 2.24 pp (`fitted_risk` on `development`). Falsifier not triggered: the rule is stable across fold seeds.

## What this does NOT prove

- It does not make the wave-2 panel independent of the study. The wave-2 certificates come from the frozen development-trained certificate and `fitted_risk` is fitted on wave-2 networks (cross-fitted, but still wave-2 data).
- The development panel is a sanity replication only: it has already been opened and used to build the frozen certificate, so it is not a confirmation panel.
- The clustered bootstrap bound is marginal at each grid point, not simultaneous over the grid; a simultaneous band would admit weakly less.
- Bootstrap percentile bounds over ~40 calibration clusters are coarse; with 49 networks the effective sample size of the bound is small.
- Admission is evaluated on `certificate_abs_error`, i.e. the error of the estimator the certificate itself selects. It is not an independent reconstruction audit.
- Nothing here validates the certificate model itself; it shows how to turn its score into a deployable admission rule without touching evaluation labels.
- The rule is a one-sided safety rule: it bounds admitted false admits, it does not bound the errors of the cases it rejects.

## Where an interpretation had to be chosen

- fitted_risk target: scripts/301 fits its quantile learner on `abserr_policy`. This script keeps that construction (verified in-script to be numerically identical to m301._fit_predict_risk) even though the evaluated event is the certificate error. `fitted_risk_certtarget` repeats the same learner on `certificate_abs_error` as a check that nothing depends on that mismatch.
- Nested cross-fitting for fitted_risk: a threshold read off in-sample calibration scores would be optimistic, so the calibration folds are split again into 4 inner network folds, the threshold is read off the inner out-of-fold scores, and the held-out fold is scored by a model refit on all calibration cases.
- Selection bound: the pre-registered bound is the one-sided 95% percentile of a network-clustered bootstrap (1000 draws) over calibration networks, because cases are clustered in networks (13,017 cases in 49 networks; median 232 cases per network) and a case-level exact binomial bound would treat them as independent. The exact binomial (Clopper-Pearson) bound is reported alongside; the frozen rule uses the clustered bound.
- Known mild feature sharing: the stored certificate scores were cross-fitted under their own network splits (script 184 for development; the frozen dev fit for wave 2), not under this script's fold seeds. No evaluation label enters a certificate score, but a calibration-fold certificate may have been calibrated on networks that this script holds out. Certificate scores are used exactly as stored.
- Tie-breaking: every score gets a deterministic per-case jitter (longest_run scale 1.0, peak_overlap 1e-3, bounds and risk 1e-9 x spread) seeded from (panel, score, fold_seed), matching scripts 301/305 for the two rule scores. Exact ties are resolved reproducibly rather than by row order.
- Fixed-70% comparison: the 70% cut is the per-held-out-fold score quantile, so the rule uses no labels and retention is exactly 70% in every fold. The panel-wide top-70% variant that scripts 301/305 report is recomputed separately and labelled.
- 'Common risk target' means the same frozen <=5% calibration cap for every score, not an exactly equal realised false-admit rate; the realised rates are reported per score so the residual imbalance is visible.
- `calibrated_bound` and `uncalibrated_bound` turn out to admit the same case sets on both pools, so the contrasted 'calibration value' is zero at this risk cap. The place where a multiplicative calibration can change a decision is the absolute-scale rule (admit iff bound <= tolerance in degrees C); that rule is deliberately outside this script's scope because it is not a risk-cap comparison.
- The retrospective rows computed here with this script's seeded tie-break can differ from `scripts/305`'s own numbers for the coarse discrete scores; the verbatim script-305 output is reproduced in the same table (`*_script305_verbatim`) so both are visible.

## Files

- `final_admission_thresholds.json` — machine interface: per panel/score/fold seed, the fold thresholds in score units, calibration retention, calibration upper bound, the decision rule in words, and the pooled honest result.
- `crossfit_risk_cap_table.csv` — fold-level and pooled rows.
- `risk_cap_contrasts.csv` — paired network-clustered contrasts.
- `posthoc_vs_honest.csv` — retrospective vs honest in one table.
- `case_level_admissions_<panel>.parquet` — per-case scores, folds and admit flags.
- `fold_assignments.csv` — network-level fold assignment per fold seed.
- `models/` — the refit `fitted_risk` models behind each frozen threshold.
- `protocol_fingerprint.json` — script/input hashes, git HEAD, versions, self-checks.

Runtime: 98.9s. Self-checks: `{"risk_construction_matches_script301": true, "clustered_point_estimate_matches_direct": true}`.

