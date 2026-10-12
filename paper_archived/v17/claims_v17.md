# Claim matrix — v17 fitness-for-use programme

A claim is allowed only after the named artifact exists. Claims tested on
reserved networks were pre-registered in
`results/v17_fitness/step9_freeze/SUCCESS_CRITERION_v17.json` before the panel
was opened on 2026-09-23. Numbers come from the run behind the deterministic,
order-stable case table; everything produced before those repairs is discarded.

## Scope

| ID | Claim | Artifact | Status |
|---|---|---|---|
| S0 | Outage timing governs the error of a gap-affected stream-temperature record in general | `step17_metric_generality/` | **withdrawn** — true for warm-season extremes, false for the annual mean and the cold extreme. The title and the abstract are scoped accordingly |
| M1 | For the hottest 30-day mean and the amplitude, timing is the better axis; for the annual mean and the coldest 30-day mean, outage length is | `step17_metric_generality/metric_generality.csv` | **stands** (AUC 0.819/0.820 vs 0.750 for the peak; 0.672/0.818 vs **0.845** for the mean; 0.447 vs **0.803** for the cold extreme) |
| M2 | That ordering is not an artefact of where the tolerance is set | `step17_metric_generality/tolerance_sweep.csv` | **stands** — identical winner at 0.25, 0.47 and 1.0 interannual SD for all four endpoints; pinned by a test |
| M3 | The dichotomy explains Johnson et al.'s "inconsistent in space and time" | §6 | stated as an interpretation, not a measurement |
| M6 | The axis contrast is a separation, not an ordering | `step22_robustness/auc_contrasts.csv` | **stands** — all five clustered intervals exclude zero (+0.072 for the 7-day peak to −0.184 for the cold extreme) |
| M7 | A shorter extreme should show a *stronger* timing effect | `step22_robustness/auc_contrasts.csv` | **stands** — predicted before measurement; the 7-day peak has the largest contrast of any endpoint (+0.072 against +0.070) |
| M4 | The mechanism behind the dichotomy is measurable, not only plausible | `step20_round4/mechanism_gradients.csv` | **stands** — error grows 3.5× along the missing-days axis and 9.6× along the peak-overlap axis for the peak; 10.2× and 1.5× for the annual mean |
| M5 | The timing side of the dichotomy is confirmed on both of its members | `step20_round4/amplitude_screen.json` | **stands** — an amplitude screen saves 4.0 points on the reserved panel (development 4.6) |

## The gate and the decision problem

| ID | Claim | Artifact | Status |
|---|---|---|---|
| G1 | The adopt/reject action space has a ceiling below the resolution of any confirmation this corpus supports | `step4_ceiling/` | **stands** (+0.038 °C against a 0.136 °C gate) |
| G2 | Method selection among reconstruction estimators has the same problem | `step4_ceiling/` | **stands** (+0.080 °C) |
| G3 | Retain/exclude clears the gate | `step4_ceiling/` | **stands** (14.9 points against 8.1) |
| P1 | Computing the annual peak on recorded days alone carries an error larger than one interannual standard deviation | `step4_ceiling/estimator_tolerances.csv` | **stands** (1.305 °C = 1.23 SD; 24.9% of years wrong by > 1 °C) |

## Mechanism, for the peak endpoint

| ID | Claim | Artifact | Status |
|---|---|---|---|
| H1a | At fixed outage length, hiding the climatological peak window dominates the error | `step5_mechanism/length_by_overlap.csv` | **stands** (30 d over the peak 18.2%; 200 d off the peak 8.7%) |
| H1b | Outage length adds nothing measurable once timing is in the model | `step5_mechanism/permutation_importance.csv` | **stands** (−0.004 against 0.194 for peak overlap) |
| H1b′ | Length is nonetheless not irrelevant, and its negative weight in a linear score is collinearity | §3.2 | **stated as a limit on H1b** (at zero overlap the rate still rises 0.6% → 8.7%; corr(length, warm coverage) = −0.86) |
| H1c | Each information layer adds discrimination beyond the length axis | `step5_mechanism/nested_feature_sets.csv` | **stands** (0.742 → 0.845 → 0.858 → 0.884) |
| H1d | Donor quality, not donor count, drives the residual error | `step5_mechanism/donor_control_contrasts.csv` | **stands** (+0.082 °C at equal donor count) |
| H1e | Donors supply synchronous anomaly information, not a seasonal shape | `step5_mechanism/donor_control_contrasts.csv` | **stands** (+0.234 °C phase-shuffled) |

## The screen

| ID | Claim | Artifact | Status |
|---|---|---|---|
| H2 | The certificate beats fixed-length screening at equal retention on networks never used for fitting | `step10_confirmation/verdict.json` | **stands as pre-registered** (−7.13 points, CI −8.98 to −5.41; declared 5 points) |
| H2a | The gain holds in every donor regime | `step10_confirmation/verdict.json` | **stands** (−6.6, −7.2, −6.7; all exclude zero) |
| H2b | The absolute advantage is stable across outage regimes | `step11_arm_robustness/` | **does not stand** — met on the stratified arm (−8.7) and pooled, not on the reserved empirical arm (−0.71, CI −2.36 to +0.05) |
| H2c | The relative reduction is stable across outage regimes | `step11_arm_robustness/` | **stands** |
| H2d | The incumbent was not handicapped by a weak reconstruction | `step15_baseline_strength/` | **stands** — the certificate beats the length rule paired with a non-deployable oracle reconstruction (2.53% against 4.19%) |
| H2e | The result is not carried by the largest agencies | `step19_weighting/` | **stands** — case-equal −7.01, provider-equal −6.30, network-equal −5.82, station-equal −5.54, all clearing the declared effect; 83% of reserved networks favour the certificate |
| H6 | Most of the benefit comes from the screening axis, not the model | `step12_ablations/` | **stands** (three-variable logit −3.71 of −6.31 points; peak overlap alone −3.62) |
| H7 | A three-variable rule is deployable and clears the pre-registered effect on its own | `step16_simple_rule/` | **stands** (reserved −5.44 points, CI −6.85 to −3.96) |
| H8 | The result does not depend on estimators seeing future years | `step13_prior_years/` | **stands** (−6.35 → −5.92 points under strictly-prior-years fitting) |
| H5 | The result transfers across agencies | `step10_confirmation/leave_one_provider_out.csv` | **stands** — negative with an interval excluding zero in all nine providers |

## Which rivers are hard

| ID | Claim | Artifact | Status |
|---|---|---|---|
| HY1 | Topography predicts difficulty: elevation and slope reduce donor synchrony and raise error | `step21_hydrology/correlations.csv` | **stands** — elevation ρ = −0.29 (−0.46, −0.08) with synchrony and +0.24 (0.06, 0.43) with error; slope ρ = −0.31 (−0.51, −0.07) |
| HY2 | Groundwater-influenced sites are harder, as the standing guidance reports | `step21_hydrology/verdict.json` | **does not stand** — high-baseflow stations are 0.043 °C *easier* (CI −0.081 to −0.004) |
| HY3 | The reason is two opposing effects, and damping is the larger | `step21_hydrology/` | **stands** — baseflow reduces synchrony (0.70 → 0.59 across tertiles) but also damps the peak (22.7 → 18.1 °C, ρ = −0.47) |
| HY4 | Regulation makes station-years harder | `step21_hydrology/verdict.json` | **does not stand** — reference minus non-reference +0.004 °C (CI −0.051, +0.093) |
| HY5 | Catchment attributes should be inputs to the screen | `step21_hydrology/correlations.csv` | **not claimed** — no attribute predicts the screening benefit (all intervals contain zero), and they are unavailable outside the US panel |

## Robustness of the assumptions

| ID | Claim | Artifact | Status |
|---|---|---|---|
| R4 | The conclusion is not inside reference-series measurement error | `step22_robustness/noise_sensitivity.json` | **stands** — perturbing the reference by 0.15 °C moves the reserved contrast from 7.06 to 6.67 points |
| R5 | The exceedance result is not an artefact of the 20 °C threshold | `step22_robustness/threshold_sweep.csv` | **stands** — swept 14–24 °C, the screen stays at 0.18–0.37% against the length rule's 0.84–1.53% |
| R6 | The 7-day regulatory window behaves like the 30-day one | `step17_metric_generality/`, `step22_robustness/` | **stands** — timing wins at all three tolerances and by the largest margin of any endpoint |

## Uncertainty

| ID | Claim | Artifact | Status |
|---|---|---|---|
| H3 | Conformal intervals attain nominal marginal and stratum coverage out of sample | `step10_confirmation/coverage.csv` | **stands** (marginal 0.909; strata 0.863–0.949) |
| H3b | The intervals are valid at an individual new site under pooled calibration | `step12_ablations/per_network_coverage.csv` | **does not stand** (per-network minimum 0.778; five of 36 networks below 0.85) |
| H3c | Site-level validity is reachable, at a stated price | `step18_cluster_conformal/` | **stands** — cluster calibration at the 0.9 level puts no network below 0.85 for a 1.5× widening |
| H3d | The screening result does not depend on the calibration choice | `step18_cluster_conformal/` | **stands** — the rate at 70% retention is 2.53% under every setting, because the ranking is a monotone transform of the bound |

## Downstream

| ID | Claim | Artifact | Status |
|---|---|---|---|
| H4a | Screening improves per-year threshold judgements | `step10_confirmation/per_year_threshold.csv`, `step20_round4/near_threshold.csv` | **stands, with the zero qualified** — 0.00% of 938 retained years overall, but 3.38% restricted to years within 0.5 °C of the threshold against 10.24% under length screening; the headline zero is mostly a statement about how few years are close |
| H4c | Screening is the best use of the certificate for a threshold judgement | `step20_round4/abstain_versus_screen.csv` | **does not stand** — abstaining only where the interval straddles the threshold judges 92.7% of years at 0.42% error against screening's 67.5% at 0.36%. Both action spaces are now reported, with the question each answers |
| H4b | Screening improves multi-year trend estimation | `step8_downstream/` | **weak** — slope RMSE 0.048 (length screening) → 0.041 (certificate); reconstructing at all is the dominant step (0.143 → 0.044) |

## Reproducibility

| ID | Claim | Artifact | Status |
|---|---|---|---|
| R1 | The case table's content is reproducible | `tests/test_v17_fitness.py` | **stands after repair** — seeded from a deterministic digest. Before the repair it was not |
| R2 | The case table's row order is reproducible | `tests/test_v17_fitness.py` | **stands after repair** — written in a declared order. Before the repair it was not, and the headline moved by 0.1 points between runs |
| R3 | The manuscript's numbers equal the artifacts | `paper_numbers.json`, `manuscript_audit.json`, test suite | **stands after repair** — 101 automated checks over every table cell and the audited inline claims; four prose errors were found and corrected, and the check is now a test rather than a proofread |

## Not claimed

| ID | Statement | Why |
|---|---|---|
| N1 | Prediction at ungauged sites | the certificate uses the station's own history |
| N2 | The air-driven branch generalizes | forcing exists for 0.85% of reserved cases; the certificate picks it for 0.07% |
| N3 | Outages that straddle a calendar year | the design places outages within one year and cannot represent this case |
| L | A universal recoverability threshold independent of model and training | forbidden, carried over |
| J | Johnson's unfilled limit as independent numerical validation | forbidden; it is the incumbent we compare against, and §3.2 now explains rather than contradicts it |

## Carried forward unchanged

Neighbour-boundary training creates a long-gap sign change that matched
long-block training does not; donor regression does not require the right flank
and support is method-specific; imputing absent donor columns is harmful while
retraining on the visible subset is not, and the v17 donor estimator retrains.

## Ledger

Reserved networks (36) were opened once, with the Step-9 model applied without
retuning. Development networks (110) were used for the gate, the mechanism
analysis, model fitting, conformal calibration and every ablation. No
station-year appears in both roles. The pipeline was re-run in full after each
reproducibility repair, and the pre-repair scorings are discarded rather than
reported alongside.
