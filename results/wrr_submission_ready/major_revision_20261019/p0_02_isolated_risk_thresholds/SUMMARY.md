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
6. Per fold: fit the score model on the other folds; choose the admission threshold on those calibration folds only. Grid = calibration score quantiles at retention 0.10..0.95 step 0.01. Rule = the largest calibration retention whose calibration false-admit rate plus a one-sided 95% upper bound is <= 5%. Bound = `independence_group_clustered_bootstrap_bonferroni_over_86_grid_points` (1000 draws). The exact binomial (Clopper-Pearson) bound is computed next to it; the frozen rule uses the clustered bound because cases are clustered in networks and a case-level binomial bound would assume independence the design does not have.
7. The frozen threshold is applied to the held-out fold exactly once; nothing downstream re-selects an operating point.
8. The pooled held-out folds are the headline estimate, labelled "cross-fitted, selection honest".
9. For `fitted_risk` the calibration-fold scores are inner out-of-fold predictions (4 inner network folds) and the held-out fold is scored by a model refit on all calibration cases.

## Headline — honest cross-fitted protocol (pooled held-out folds)

### wave2_confirmation (13,017 cases, 49 networks, error rate 15.96%)

                 score  fold seed retention ret CI lo ret CI hi false-admit FA CI lo FA CI hi  admitted  cases  nets
      calibrated_bound        101    74.63%    71.42%    77.58%       3.37%    2.67%    4.23%      9715  13017    41
      calibrated_bound        202    74.96%    71.82%    77.78%       3.43%    2.70%    4.26%      9757  13017    41
      calibrated_bound        303    74.98%    72.00%    78.02%       3.44%    2.70%    4.24%      9760  13017    41
           fitted_risk        101    72.84%    69.50%    75.82%       2.64%    2.07%    3.30%      9481  13017    41
           fitted_risk        202    72.56%    69.41%    75.61%       2.73%    2.14%    3.43%      9445  13017    41
           fitted_risk        303    72.50%    69.49%    75.52%       2.87%    2.29%    3.49%      9437  13017    41
fitted_risk_certtarget        101    74.31%    71.20%    77.18%       2.93%    2.37%    3.58%      9673  13017    41
fitted_risk_certtarget        202    75.11%    72.17%    77.79%       3.49%    2.79%    4.30%      9777  13017    41
fitted_risk_certtarget        303    74.76%    71.84%    77.60%       3.56%    2.79%    4.45%      9732  13017    41
           length_rule        101    43.92%    41.41%    46.07%       2.57%    1.66%    3.80%      5717  13017    41
           length_rule        202    45.00%    42.74%    46.84%       2.99%    2.08%    4.22%      5857  13017    41
           length_rule        303    43.47%    41.31%    45.38%       2.70%    1.69%    4.02%      5659  13017    41
     peak_overlap_rule        101    69.56%    67.85%    71.03%       3.34%    2.59%    4.14%      9055  13017    41
     peak_overlap_rule        202    69.92%    68.22%    71.51%       3.41%    2.65%    4.24%      9101  13017    41
     peak_overlap_rule        303    69.74%    68.09%    71.19%       3.43%    2.67%    4.27%      9078  13017    41
    uncalibrated_bound        101    74.63%    71.42%    77.58%       3.37%    2.67%    4.23%      9715  13017    41
    uncalibrated_bound        202    74.43%    71.26%    77.33%       3.24%    2.54%    4.06%      9689  13017    41
    uncalibrated_bound        303    74.98%    72.00%    78.02%       3.44%    2.70%    4.24%      9760  13017    41

Across fold seeds (descriptive; the per-seed rows above carry the intervals):

                 score retention_mean retention_min retention_max fa_mean fa_min fa_max
      calibrated_bound         74.86%        74.63%        74.98%   3.41%  3.37%  3.44%
           fitted_risk         72.63%        72.50%        72.84%   2.75%  2.64%  2.87%
fitted_risk_certtarget         74.73%        74.31%        75.11%   3.32%  2.93%  3.56%
           length_rule         44.13%        43.47%        45.00%   2.75%  2.57%  2.99%
     peak_overlap_rule         69.74%        69.56%        69.92%   3.39%  3.34%  3.43%
    uncalibrated_bound         74.68%        74.43%        74.98%   3.35%  3.24%  3.44%

### development (40,704 cases, 110 networks, error rate 14.56%)

                 score  fold seed retention ret CI lo ret CI hi false-admit FA CI lo FA CI hi  admitted  cases  nets
      calibrated_bound        101    73.24%    70.26%    75.62%       3.62%    2.93%    4.38%     29811  40704   110
      calibrated_bound        202    72.66%    69.70%    75.30%       3.42%    2.74%    4.18%     29574  40704   110
      calibrated_bound        303    73.25%    70.05%    76.06%       3.56%    2.93%    4.26%     29815  40704   110
           fitted_risk        101    70.47%    66.87%    74.13%       3.01%    2.44%    3.78%     28685  40704   110
           fitted_risk        202    70.85%    67.51%    74.79%       3.01%    2.50%    3.68%     28839  40704   110
           fitted_risk        303    70.66%    67.40%    74.17%       3.00%    2.45%    3.72%     28760  40704   110
fitted_risk_certtarget        101    71.59%    68.23%    74.99%       3.17%    2.60%    3.95%     29142  40704   110
fitted_risk_certtarget        202    71.12%    67.97%    74.75%       3.05%    2.54%    3.71%     28950  40704   110
fitted_risk_certtarget        303    71.39%    68.07%    74.95%       3.11%    2.59%    3.80%     29057  40704   110
           length_rule        101    34.86%    31.17%    38.16%       3.34%    2.62%    4.33%     14188  40704   110
           length_rule        202    35.40%    31.83%    38.73%       3.27%    2.59%    4.18%     14411  40704   110
           length_rule        303    34.69%    31.31%    37.78%       3.17%    2.48%    4.08%     14121  40704   110
     peak_overlap_rule        101    61.85%    60.07%    63.57%       3.74%    3.13%    4.39%     25177  40704   110
     peak_overlap_rule        202    62.14%    60.13%    63.92%       3.80%    3.16%    4.45%     25295  40704   110
     peak_overlap_rule        303    62.06%    60.18%    63.73%       3.72%    3.08%    4.38%     25259  40704   110
    uncalibrated_bound        101    73.02%    69.99%    75.63%       3.41%    2.78%    4.15%     29724  40704   110
    uncalibrated_bound        202    73.43%    70.39%    76.21%       3.52%    2.88%    4.29%     29888  40704   110
    uncalibrated_bound        303    73.22%    70.12%    76.07%       3.44%    2.84%    4.15%     29803  40704   110

Across fold seeds (descriptive; the per-seed rows above carry the intervals):

                 score retention_mean retention_min retention_max fa_mean fa_min fa_max
      calibrated_bound         73.05%        72.66%        73.25%   3.53%  3.42%  3.62%
           fitted_risk         70.66%        70.47%        70.85%   3.01%  3.00%  3.01%
fitted_risk_certtarget         71.37%        71.12%        71.59%   3.11%  3.05%  3.17%
           length_rule         34.98%        34.69%        35.40%   3.26%  3.17%  3.34%
     peak_overlap_rule         62.02%        61.85%        62.14%   3.75%  3.72%  3.80%
    uncalibrated_bound         73.22%        73.02%        73.43%   3.46%  3.41%  3.52%

## Folds that admitted nothing

0 of 180 (score x fold seed x fold) cells admitted nothing.

Every fold found an admissible grid point, so no fold fell back to admitting nothing.

The deployed rule uses the simultaneous Bonferroni clustered bound. It disagreed with the exact binomial bound on whether any grid point qualifies in 0 of 180 cells. The pointwise 95% clustered bound is not used for admission.
Because admission already uses the simultaneous bound, the admit-nothing verdict matches the Bonferroni column in 180 of 180 cells.

## RETROSPECTIVE / not deployable vs honest (same scores, same panel)

### wave2_confirmation

                 score posthoc_retention posthoc_false_admit  posthoc_admitted honest_retention honest_false_admit retention_gap_pp false_admit_gap_pp
      calibrated_bound            79.00%               4.88%             10283           74.86%              3.41%            -4.14              -1.47
           fitted_risk            78.00%               4.90%             10153           72.63%              2.75%            -5.37              -2.16
fitted_risk_certtarget            79.00%               4.76%             10283           74.73%              3.32%            -4.27              -1.43
           length_rule            55.00%               4.87%              7159           44.13%              2.75%           -10.87              -2.12
     peak_overlap_rule            75.00%               4.99%              9763           69.74%              3.39%            -5.26              -1.60
    uncalibrated_bound            79.00%               4.88%             10283           74.68%              3.35%            -4.32              -1.53

- `calibrated_bound`: honest minus post-hoc retention -4.14 pp; honest minus post-hoc false-admit rate -1.47 pp.
- `fitted_risk`: honest minus post-hoc retention -5.37 pp; honest minus post-hoc false-admit rate -2.16 pp.
- `fitted_risk_certtarget`: honest minus post-hoc retention -4.27 pp; honest minus post-hoc false-admit rate -1.43 pp.
- `length_rule`: honest minus post-hoc retention -10.87 pp; honest minus post-hoc false-admit rate -2.12 pp.
- `peak_overlap_rule`: honest minus post-hoc retention -5.26 pp; honest minus post-hoc false-admit rate -1.60 pp.
- `uncalibrated_bound`: honest minus post-hoc retention -4.32 pp; honest minus post-hoc false-admit rate -1.53 pp.

Verbatim `scripts/305_wrr_mr_step6_calibration_decision.py::admission_table` output on the same inputs (this is what the manuscript currently quotes, with that function's own tie-break draw):

             score retention false_admit_rate  n_admitted
       length_rule    55.00%            4.82%        7159
 peak_overlap_rule    74.00%            4.67%        9633
uncalibrated_bound    79.00%            4.88%       10283
  calibrated_bound    79.00%            4.88%       10283

Where the verbatim row and the `posthoc_*` row disagree for `length_rule` / `peak_overlap_rule`, the cause is the tie-break draw over a coarse discrete score, not the risk cap: the old post-hoc frontier is not even reproducible across tie-break seeds.

### development

                 score posthoc_retention posthoc_false_admit  posthoc_admitted honest_retention honest_false_admit retention_gap_pp false_admit_gap_pp
      calibrated_bound            79.00%               4.97%             32156           73.05%              3.53%            -5.95              -1.44
           fitted_risk            78.00%               4.99%             31749           70.66%              3.01%            -7.34              -1.98
fitted_risk_certtarget            78.00%               4.89%             31749           71.37%              3.11%            -6.63              -1.77
           length_rule            49.00%               4.99%             19945           34.98%              3.26%           -14.02              -1.73
     peak_overlap_rule            68.00%               4.76%             27679           62.02%              3.75%            -5.98              -1.00
    uncalibrated_bound            79.00%               4.85%             32156           73.22%              3.46%            -5.78              -1.40

- `calibrated_bound`: honest minus post-hoc retention -5.95 pp; honest minus post-hoc false-admit rate -1.44 pp.
- `fitted_risk`: honest minus post-hoc retention -7.34 pp; honest minus post-hoc false-admit rate -1.98 pp.
- `fitted_risk_certtarget`: honest minus post-hoc retention -6.63 pp; honest minus post-hoc false-admit rate -1.77 pp.
- `length_rule`: honest minus post-hoc retention -14.02 pp; honest minus post-hoc false-admit rate -1.73 pp.
- `peak_overlap_rule`: honest minus post-hoc retention -5.98 pp; honest minus post-hoc false-admit rate -1.00 pp.
- `uncalibrated_bound`: honest minus post-hoc retention -5.78 pp; honest minus post-hoc false-admit rate -1.40 pp.

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
      fitted_risk        length_rule    28.50        27.56        29.02      24.79       32.19                        True
peak_overlap_rule        length_rule    25.61        24.92        26.27      23.30       28.37                        True
      fitted_risk  peak_overlap_rule     2.89         2.64         3.27       0.33        5.68                        True
 calibrated_bound uncalibrated_bound     0.17         0.00         0.52       0.00        0.89                       False
      fitted_risk uncalibrated_bound    -2.05        -2.48        -1.80      -4.17       -0.50                        True
      fitted_risk   calibrated_bound    -2.23        -2.48        -1.80      -4.17       -0.73                        True
peak_overlap_rule uncalibrated_bound    -4.94        -5.24        -4.52      -7.49       -2.15                        True
peak_overlap_rule   calibrated_bound    -5.12        -5.24        -5.04      -7.49       -2.78                        True
      length_rule uncalibrated_bound   -30.55       -31.50       -29.44     -34.53      -26.52                        True
      length_rule   calibrated_bound   -30.73       -31.50       -29.96     -34.53      -27.08                        True

### wave2_confirmation — fixed_retention_70_perfold (false_admit_rate, pp)

       score_left        score_right point_pp point_min_pp point_max_pp ci_low_min ci_high_max  ci_excludes_zero_all_seeds
      length_rule uncalibrated_bound     6.37         6.26         6.45       5.21        7.60                        True
      length_rule   calibrated_bound     6.37         6.26         6.45       5.21        7.60                        True
peak_overlap_rule   calibrated_bound     0.98         0.91         1.06       0.47        1.49                        True
peak_overlap_rule uncalibrated_bound     0.98         0.91         1.06       0.47        1.49                        True
 calibrated_bound uncalibrated_bound     0.00         0.00         0.00       0.00        0.00                       False
      fitted_risk   calibrated_bound    -0.25        -0.41        -0.01      -0.78        0.43                       False
      fitted_risk uncalibrated_bound    -0.25        -0.41        -0.01      -0.78        0.43                       False
      fitted_risk  peak_overlap_rule    -1.24        -1.47        -0.99      -2.02       -0.51                        True
peak_overlap_rule        length_rule    -5.39        -5.50        -5.28      -6.53       -4.39                        True
      fitted_risk        length_rule    -6.63        -6.86        -6.27      -8.27       -5.26                        True

### development — risk_cap_5pct_frozen (retention, pp)

       score_left        score_right point_pp point_min_pp point_max_pp ci_low_min ci_high_max  ci_excludes_zero_all_seeds
      fitted_risk        length_rule    35.68        35.45        35.96      30.01       42.47                        True
peak_overlap_rule        length_rule    27.03        26.74        27.36      23.48       31.12                        True
      fitted_risk  peak_overlap_rule     8.64         8.60         8.71       5.55       12.26                        True
 calibrated_bound uncalibrated_bound    -0.18        -0.77         0.21      -1.70        1.35                       False
      fitted_risk   calibrated_bound    -2.39        -2.77        -1.81      -6.28        1.57                       False
      fitted_risk uncalibrated_bound    -2.56        -2.58        -2.55      -5.73        0.55                       False
peak_overlap_rule   calibrated_bound   -11.03       -11.38       -10.51     -13.86       -7.48                        True
peak_overlap_rule uncalibrated_bound   -11.21       -11.28       -11.16     -14.05       -8.47                        True
      length_rule   calibrated_bound   -38.06       -38.56       -37.25     -43.72      -32.34                        True
      length_rule uncalibrated_bound   -38.24       -38.53       -38.02     -43.99      -33.05                        True

### development — fixed_retention_70_perfold (false_admit_rate, pp)

       score_left        score_right point_pp point_min_pp point_max_pp ci_low_min ci_high_max  ci_excludes_zero_all_seeds
      length_rule uncalibrated_bound     5.96         5.90         5.99       5.01        7.06                        True
      length_rule   calibrated_bound     5.88         5.79         5.95       4.89        7.00                        True
peak_overlap_rule uncalibrated_bound     2.35         2.33         2.37       1.72        2.94                        True
peak_overlap_rule   calibrated_bound     2.27         2.22         2.31       1.66        2.91                        True
 calibrated_bound uncalibrated_bound     0.08         0.03         0.11      -0.15        0.25                       False
      fitted_risk uncalibrated_bound    -0.05        -0.12         0.02      -0.53        0.52                       False
      fitted_risk   calibrated_bound    -0.13        -0.21        -0.07      -0.64        0.43                       False
      fitted_risk  peak_overlap_rule    -2.39        -2.49        -2.31      -3.14       -1.57                        True
peak_overlap_rule        length_rule    -3.61        -3.64        -3.57      -4.44       -2.96                        True
      fitted_risk        length_rule    -6.01        -6.11        -5.88      -7.14       -4.90                        True

Levels behind these contrasts (retention and realised false-admit rate per score) are in `crossfit_risk_cap_table.csv` and `posthoc_vs_honest.csv`.

### Absolute scale vs ranking: `calibrated_bound` vs `uncalibrated_bound`

- `wave2_confirmation`: Spearman rank correlation between `certificate_bound` and `certificate_raw_bound` is 0.992327; the frozen rule admits exactly the same cases for the two scores in every fold (paired contrast exactly 0.00 pp, CI [0.00, 0.00]).
- `development`: Spearman rank correlation between `certificate_bound` and `certificate_raw_bound` is 0.979748; the frozen rule admits exactly the same cases for the two scores in every fold (paired contrast exactly 0.00 pp, CI [0.00, 0.00]).

So the calibration changes the absolute scale of the bound far more than its ordering on these pools: the admitted sets coincide exactly in every fold of this run and the rank correlation is high but not 1.0, i.e. only near-tied cases are reordered. Any decision value it has must therefore come from the absolute-scale semantics (admit iff bound <= tolerance, compared in degrees C), not from screening or ranking gain. A claim of the form 'calibration improves the screen at fixed retention' is unsupported here: the screening gain at fixed retention belongs to the certificate *score*, not to its calibration. This script's risk-cap comparison cannot show the absolute-scale value; that comparison is out of scope.

## Cap compliance of the held-out folds

- Pooled held-out cells: 0 of 36 have a point false-admit rate above 5%; the worst point estimate is 3.80%.
- Their 95% network-clustered intervals exceed 5% at the upper end in 0 of 36 cells (worst upper end 4.45%). The cap is therefore met on every point estimate, but for those cells the data are consistent with a true rate above 5%.
- Individual held-out folds: 11 of 180 fold cells have a point false-admit rate above 5% (worst 7.10%). Folds are small (6-27 networks), so this is the expected granularity of the guarantee, not a violation of the calibration rule.

## Deployed bound: simultaneous Bonferroni band

The deployed rule is the simultaneous band: for each grid point, the 1 - 0.05/86 percentile of the independence-group clustered bootstrap false-admit rate, then the largest grid point whose bound is still at most 5%. A pointwise 95% percentile would not be a 95% statement after maximising over 86 points, so it is not the admission rule. The simultaneous bound is still an empirical clustered bound for this grid, not a distribution-free guarantee for an unseen archive. `bonferroni_sensitivity_pooled` matches the deployed rows because that column now records the same rule.

### wave2_confirmation — Bonferroni band (sensitivity)

                 score  fold_seed test_retention test_false_admit_rate test_false_admit_ci95_low test_false_admit_ci95_high  test_n_admitted
      calibrated_bound        101         74.63%                 3.37%                     2.65%                      4.21%             9715
      calibrated_bound        202         74.96%                 3.43%                     2.69%                      4.30%             9757
      calibrated_bound        303         74.98%                 3.44%                     2.75%                      4.24%             9760
           fitted_risk        101         72.84%                 2.64%                     2.07%                      3.30%             9481
           fitted_risk        202         72.56%                 2.73%                     2.11%                      3.43%             9445
           fitted_risk        303         72.50%                 2.87%                     2.31%                      3.48%             9437
fitted_risk_certtarget        101         74.31%                 2.93%                     2.40%                      3.61%             9673
fitted_risk_certtarget        202         75.11%                 3.49%                     2.78%                      4.33%             9777
fitted_risk_certtarget        303         74.76%                 3.56%                     2.82%                      4.43%             9732
           length_rule        101         43.92%                 2.57%                     1.67%                      3.82%             5717
           length_rule        202         45.00%                 2.99%                     2.09%                      4.17%             5857
           length_rule        303         43.47%                 2.70%                     1.73%                      3.99%             5659
     peak_overlap_rule        101         69.56%                 3.34%                     2.60%                      4.17%             9055
     peak_overlap_rule        202         69.92%                 3.41%                     2.62%                      4.23%             9101
     peak_overlap_rule        303         69.74%                 3.43%                     2.68%                      4.23%             9078
    uncalibrated_bound        101         74.63%                 3.37%                     2.65%                      4.21%             9715
    uncalibrated_bound        202         74.43%                 3.24%                     2.52%                      4.06%             9689
    uncalibrated_bound        303         74.98%                 3.44%                     2.75%                      4.24%             9760

### development — Bonferroni band (sensitivity)

                 score  fold_seed test_retention test_false_admit_rate test_false_admit_ci95_low test_false_admit_ci95_high  test_n_admitted
      calibrated_bound        101         73.24%                 3.62%                     2.89%                      4.38%            29811
      calibrated_bound        202         72.66%                 3.42%                     2.76%                      4.17%            29574
      calibrated_bound        303         73.25%                 3.56%                     2.91%                      4.26%            29815
           fitted_risk        101         70.47%                 3.01%                     2.43%                      3.77%            28685
           fitted_risk        202         70.85%                 3.01%                     2.49%                      3.72%            28839
           fitted_risk        303         70.66%                 3.00%                     2.46%                      3.74%            28760
fitted_risk_certtarget        101         71.59%                 3.17%                     2.58%                      3.93%            29142
fitted_risk_certtarget        202         71.12%                 3.05%                     2.53%                      3.77%            28950
fitted_risk_certtarget        303         71.39%                 3.11%                     2.58%                      3.83%            29057
           length_rule        101         34.86%                 3.34%                     2.65%                      4.27%            14188
           length_rule        202         35.40%                 3.27%                     2.62%                      4.17%            14411
           length_rule        303         34.69%                 3.17%                     2.49%                      4.07%            14121
     peak_overlap_rule        101         61.85%                 3.74%                     3.11%                      4.39%            25177
     peak_overlap_rule        202         62.14%                 3.80%                     3.14%                      4.45%            25295
     peak_overlap_rule        303         62.06%                 3.72%                     3.10%                      4.38%            25259
    uncalibrated_bound        101         73.02%                 3.41%                     2.73%                      4.16%            29724
    uncalibrated_bound        202         73.43%                 3.52%                     2.90%                      4.26%            29888
    uncalibrated_bound        303         73.22%                 3.44%                     2.82%                      4.18%            29803

- `wave2_confirmation`, equal-risk contrast `fitted_risk` minus `length_rule` under the Bonferroni band: 28.50 pp [24.59, 32.63].
- `development`, equal-risk contrast `fitted_risk` minus `length_rule` under the Bonferroni band: 35.68 pp [30.19, 42.04].

## What would falsify this — observed verdicts

- *Falsifier 1*: the honest pooled false-admit rate materially exceeds the 5% cap. Observed: 0 of 36 pooled cells above the cap; worst point 3.80%; 0 of 36 interval upper ends above the cap. Falsifier not triggered, but not fully excluded either.
- *Falsifier 2*: the honest retention is far below the post-hoc frontier at the same cap. Observed: honest minus post-hoc retention runs from -14.02 pp (`length_rule` on `development`) to -4.14 pp (`calibrated_bound` on `wave2_confirmation`). For the certificate and fitted scores the loss is -7.34 to -4.14 pp across panels and seeds; for the two engineered rules it reaches -14.02 pp. The post-hoc frontier is optimistic everywhere. Falsifier triggered in direction, modest in magnitude for the scores the manuscript relies on.
- *Falsifier 3*: `calibrated_bound` fails to beat the engineered rules at equal risk / equal retention. Observed (positive = the first score keeps more / admits worse):
    - risk-cap retention, `calibrated_bound` minus `peak_overlap_rule` 8.07 pp (range 5.04 to 11.38), CI excludes 0 in every fold seed
    - risk-cap retention, `calibrated_bound` minus `length_rule` 34.39 pp (range 29.96 to 38.56), CI excludes 0 in every fold seed
    - 70%-retention false-admit rate, `peak_overlap_rule` minus `calibrated_bound` 1.63 pp (range 0.91 to 2.31), CI excludes 0 in every fold seed
    - risk-cap retention, `fitted_risk` minus `calibrated_bound` -2.31 pp (range -2.77 to -1.80), CI includes 0 in at least one fold seed
    - 70%-retention false-admit rate, `fitted_risk` minus `calibrated_bound` -0.19 pp (range -0.41 to -0.01), CI includes 0 in at least one fold seed
    - against `uncalibrated_bound` both contrasts are exactly 0.00 pp in every fold seed. Falsifier survives in the weak form 'the certificate score beats the engineered rules'; it is triggered for the strong form 'calibration itself adds decision value', and it is unresolved against `fitted_risk`.
- *Falsifier 4*: the selected retention swings widely across fold seeds. Observed: the widest per (panel, score) retention spread across the three fold seeds is 1.52 pp (`length_rule` on `wave2_confirmation`). Falsifier not triggered: the rule is stable across fold seeds.

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
- Nested cross-fitting for fitted_risk: each outer fold stores its own inner out-of-fold calibration scores. Those scores are produced by models whose training rows exclude that outer test fold. A later outer fold does not overwrite them. Inner folds are independence groups, not network-label strings.
- Selection bound: the deployed bound is the Bonferroni percentile 1 - 0.05/86 of an independence-group clustered bootstrap (1000 draws). The rule maximises over 86 grid points, so a pointwise 95% bound is not the admission rule. The pointwise percentile and the Clopper-Pearson binomial bound are reported beside it. This is a simultaneous bound for the grid that was searched, not a distribution-free guarantee for a new archive.
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

Runtime: 171.8s. Self-checks: `{"risk_construction_matches_script301": true, "clustered_point_estimate_matches_direct": true}`.

