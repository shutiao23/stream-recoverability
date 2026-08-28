# v11 scientific and code red-team audit

## Verdict

The open-development run is now internally matched at 55 networks, 217
stations, and 1,260 station-by-gap units. Every station uses identical donor,
meteorology, hydraulics, and training-year rosters in the VAR operator and the
XGBoost recovery outcome. The literal B+D+M+H conditional risk is the primary;
the ACF-weighted boundary construction is diagnostic only.

Route B fails the complete written gate. Literal operator LONO Spearman gains
0.127 over donor R2, exceeding the +0.10 rank floor, but its nested increment
after the strongest available simple model is only +0.01710 R2, below +0.05.
The route decision is therefore Route A: simple outage geometry and
redundancy.

## Corrected evidence

| Requirement | Current evidence | Verdict |
| --- | --- | --- |
| Complete B/D/M/H binding | All 217 stations have five meteorological features; 175 have one hydraulic feature and 42 have two. The shared joint-consecutive selector applies the same minimum 365 fitting pairs to D, then M, then H. | Met for the 55-network matched set. |
| Exact operator/outcome roster match | `operator_recovery_roster_audit.csv` compares donor IDs, M IDs, H IDs, and training years at every station. All 217/217 rows match on every field. | Met. |
| No post-70% leakage | Operator and recovery training-year strings match in all 55 networks, and all scored gaps begin afterward. A counterfactual test changes post-cutoff temperature and auxiliary values without changing operator output. | No leakage found. |
| True daily VAR transitions | Temperature panels are expanded to a daily index before year splitting and adjacent-pair selection. Dropped-date and explicit-missing-date inputs give identical output. | Fixed. |
| Strongest available simple model | Each outer network fold evaluates 60 declared combinations of gap length, ACF, donor R2, the additive heuristic, nearest-donor correlation, and paired seasonal coordinates in an inner LONO loop using equal-network RMSE. Forty-seven folds select the original four plus nearest correlation, seven select the original four, and one selects the original four plus season. | Met for the declared simple roster. |
| Cross-network operator intervals | Point calibration weights networks equally. Each outer fold uses maximum absolute residuals from inner held-out networks for a 90% block interval. | Met in code; intervals are very wide. |
| Route A uncertainty | Every outer simple prediction has a training-network block interval. The summary reports rank, calibration, row coverage, network-equal coverage, simultaneous-network coverage, and width. | Met. |
| Placement estimand | Selected stations are retained donors and every unretained station is a target. Proposed and oracle selection use the scored gap length, and budgets stop at n-1. | Fixed. |
| MI/regret independence | Result rows state `synthetic_implementation_only`, `independent_realized_outcomes=false`, and `selection_and_evaluation_share_true_covariance=true`. | Not H3 evidence; implementation benchmark only. |
| No hashes or locks in v11 | The v11 config, runners, analysis modules, and replaceable outputs contain no hash or lock mechanism. | Met. |

## H1 and H2 results

The literal complete operator has:

- station-gap Spearman 0.4382 and network-summary Spearman 0.2908;
- equal-network calibration intercept 0.2197 and slope 0.8286;
- row coverage 0.9960, network-equal row coverage 0.9937, and simultaneous
  whole-network coverage 0.9091 for the nominal 90% interval; and
- mean interval width 11.52 degrees C.

Good simultaneous coverage is achieved only with an interval too wide to be
operationally useful. Rank transport is modest and equal-network magnitude
calibration misses the 0.9--1.1 planning band.

The selected Route A simple model has:

- station-gap Spearman 0.7019 and network-summary Spearman 0.7889;
- equal-network calibration intercept 0.0337 and slope 0.9756;
- row coverage 0.9937, network-equal row coverage 0.9905, and simultaneous
  whole-network coverage 0.8909; and
- mean interval width 6.48 degrees C.

Thus the simple model ranks and calibrates much better and produces materially
narrower intervals. Its simultaneous-network coverage is 0.891 rather than
exactly 0.900, which must be reported rather than rounded into a pass.

## Large-gap behavior

Strict feature completeness leaves 217 stations at 7--30 days, 210 at 60
days, 200 at 90 days, 138 at 180 days, and 61 at 365 days. To hold composition
fixed, the table below uses the same 61 stations that support every gap:

| Gap (days) | Realized loss | Regime-weighted diagnostic | Literal complete risk |
| ---: | ---: | ---: | ---: |
| 7 | 0.544 | 0.471 | 0.379 |
| 14 | 0.667 | 0.461 | 0.408 |
| 30 | 0.815 | 0.456 | 0.431 |
| 60 | 0.975 | 0.455 | 0.442 |
| 90 | 1.240 | 0.454 | 0.445 |
| 180 | 2.432 | 0.454 | 0.449 |
| 365 | 4.719 | 0.453 | 0.451 |

The literal risk has the correct aggregate direction but saturates far below
realized large-gap loss. The regime-weighted construction moves downward and
is therefore unsuitable as the primary. Across all 217 stations, it decreases
with gap at least once in 204 stations, versus 35 for literal risk. The sample
contains 175 low-memory and 42 transition stations and no high-memory station,
so it cannot establish the proposed benefit of ACF weighting in high-memory
regimes.

## Remaining evidence gaps

1. The 55-network matched run is large enough to make the Route A decision,
   but it is still open development, not new confirmation.
2. No real nonstationarity or cross-domain transfer output is produced by the
   106 runner. Library functions and synthetic tests are not evidence for
   those claims.
3. The placement curve shares a known synthetic covariance between policy
   selection and scoring. It cannot pass empirical H3 or support a deployment
   claim.
4. Long-gap support is selective: only 61 of 217 matched stations retain a
   365-day cell. All pooled gap summaries must report their changing N.

The evidence supports stopping Route B and carrying the calibrated simple
model, its explicit completeness envelope, and its network-block uncertainty
into a wholly new confirmation design.

## Post-audit completion

The remaining executable items were completed after the core red-team pass:

- nearest-donor correlation and paired placement-season coordinates entered a
  60-model inner LONO contest; nearest correlation was selected in 47/55 outer
  folds and season in one;
- network-bootstrap intervals were added for development and confirmation;
- 45 wholly new stream networks passed source QC and 42 produced confirmation
  scores;
- cross-domain and thermal-state-change metrics were computed from observed
  confirmation data; and
- the fixed development gap-triage thresholds were applied unchanged in
  confirmation.

Confirmation station-gap Spearman was 0.803 (95% network-bootstrap interval
0.747--0.855), but calibration slope was 0.806 (0.728--0.876) and simultaneous
whole-network coverage was 0.857 (0.762--0.952). The cross-domain slope was
0.753 and state-shift slope was 0.270. The triage false-release rate was 10%,
above its 5% cap. These results close the earlier evidence gaps with negative
operational findings rather than by changing thresholds.
