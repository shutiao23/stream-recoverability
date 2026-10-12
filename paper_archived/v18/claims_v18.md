# Claim matrix — v18 closure programme

A claim is allowed only after the named artifact exists. Claims tested on
reserved networks were pre-registered in
`results/v17_fitness/step9_freeze/SUCCESS_CRITERION_v17.json` before the panel
was opened on 2026-09-23. **Everything added in v18 was developed after that
opening and is therefore reported on development cases**; reserved numbers
appear only where they are informative and are labelled as no longer blind. The
v17 confirmation is not re-scored.

**Submission readiness (2026-10-12).** Authoritative evidence identity for
headline claims is `results/wrr_submission_ready/claim_registry.csv`. The v17
reserved panel is a retrospective network holdout (28/36 networks have prior
access); it is not an unseen confirmation set for v18. Claims marked
`pending_new_confirmation`, `invalid_pending_recompute`, or `rewrite_required`
in that registry must not enter the WRR abstract or conclusions.

## What changed from v17, and why

| ID | Change | Reason |
|---|---|---|
| C1 | The filled limit of Johnson et al. (2021) corrected from 91 days to **140 days** | The source says "approximately 20 weeks", not thirteen. `frontier.py` and §5.6 were wrong. The correction makes the incumbent more permissive (85.1% retention on the reserved panel, not 74.0%) and reduces the screen's advantage at that point from 6.2 to **4.4** points |
| C2 | The dichotomy restated as a **continuum with a measured crossover** | `warm_observed_fraction`, the best-performing "timing" axis, correlates −0.86 with the longest run: it is a length measure with a domain restriction. The axis labels were wrong even though the ordering was right |
| C3 | The practice being corrected is now **documented with citations**, and it is a transfer of a threshold rather than the threshold | Johnson et al. estimate sine-fit parameters, not warm-season extremes. As written, v17 refuted a claim nobody made |
| C4 | Air forcing joined for **all 457 stations** | 2.3% coverage made the fairness argument in v17 §5.5 untestable against the reconstruction this field actually uses |
| C5 | The rule applied to **2,422 real incomplete station-years** | v17 used them only as a source of outage geometry |
| C6 | **Representativeness** reported alongside the error rate | v17 asked which catchments the screen *gains* on, not which it *keeps* |

## The law

| ID | Claim | Artifact | Status |
|---|---|---|---|
| L1 | Error of a derived statistic is governed by the share of that statistic's support the outage hides | `e6_support_width/support_width_sweep.csv` | **exploratory / not a proportion law for headlines** — support-restricted axis ranks well; unconditional proportionality withdrawn pending residual/window tests (`claim_registry` L1) |
| L2 | The governing axis moves continuously with the support width, and the two "regimes" are its ends | `e6_support_width/auc_contrasts_by_width.csv` | **exploratory_post_open** — AUC continuum on opened panel; not sealed confirmation |
| L3 | The crossover is at a support width near three months | `e6_support_width/summary.json` | **exploratory_post_open** — 91.0 days on development (interpolated sparse grid); opened reserved ≈119 days; not headline-precise |
| L4 | The support-restricted advantage decays **monotonically** in *k* | `e6_support_width/` | **does not stand** — it is a hump peaking at *k* = 60 (+0.089) and falling on both sides |
| L5 | The estimand's own support is the best conditioning set at every *k* | `e6_support_width/conditioning_width_matrix.csv` | **does not stand** — below *k* = 30 a fixed 30-day window beats it, by 0.064 AUC at *k* = 1 |
| L6 | L4 and L5 fail because the support's *location* is uncertain, and the right conditioning set is the support dilated by that uncertainty | `e6_support_width/conditioning_width_matrix.csv` | **stands** — the gain from widening (+0.102 at *k* = 1 to 0 at *k* ≥ 90) tracks the year-to-year wander of the realised window (16.7 d to 7.4 d) |
| L7 | One conditioning window serves the whole warm-season family | same | **exploratory_post_open** — report in SI/methods narrative; not abstract until never-used confirmation |

## The standing guidance's own estimands

| ID | Claim | Artifact | Status |
|---|---|---|---|
| J1 | On the sine-fit **mean**, outage size is the better axis | `e3_sine_endpoints/sine_axis_comparison.csv` | **stands** — 0.845 for the longest run and the missing fraction against 0.672 for peak overlap |
| J2 | On the sine-fit **phase**, two hand-chosen transition windows beat both peak overlap and outage length | same | **does not stand** — they beat peak overlap by +0.249 (0.231, 0.270) and tie outage length (0.831 against 0.836) |
| J3 | The **influence-weighted** hidden mass is the best axis where the influence is not uniform | `e3_sine_endpoints/auc_contrasts.csv` | **stands** — best for the amplitude (0.831) and the phase (0.847); for the mean it is uniform by construction and equals the missing fraction exactly |
| J4 | The amplitude sits between the mean and the phase in peak-window advantage | same | **stands** — peak minus length −0.089 for the amplitude against −0.173 (mean) and −0.252 (phase) |
| J5 | The ordering holds under the authors' own protocol, fitting the sine to observed days with no repair | same | **stands** — same winner for all three, at base rates of 32–34% |
| J6 | The dichotomy explains Johnson et al.'s "inconsistent in space and time" | §5.4 | **stands as a measurement**, upgraded from v17 where it was an interpretation: three estimands, three supports, and a timing effect for one of them |
| J7 | The standing guidance is wrong on its own endpoints | — | **withdrawn.** It is right on its own endpoints. What this paper corrects is carrying its threshold to an estimand it was not derived for |

## Deployment on records that really have holes

| ID | Claim | Artifact | Status |
|---|---|---|---|
| D1 | The two rules disagree on a material share of real incomplete station-years | `e2_archive_deployment/threshold_disagreement.csv` | **stands** — 15.1% at the unfilled limit and 11.6% at the imputed limit, against a declared immateriality threshold of 3% |
| D2 | The incumbent admits station-years whose annual peak was never observed | `e2_archive_deployment/archive_consequence.csv` | **rewrite_required** — counts wholly masked *climatological* peak windows; true annual peak unknown. Do not headline as verified unobserved peaks |
| D3 | A risk model fitted on scored cases transports to unscored records | `e2_archive_deployment/risk_model_calibration_on_reserved.csv` | **stands as an extrapolation** — largest decile miscalibration on the reserved panel 6.2 points, under 1.6 points in nine of ten deciles |
| D4 | Changing the screening rule changes a regional aggregate | `e2_archive_deployment/archive_consequence.csv` | **does not stand** — the mean annual peak moves by less than 0.1 °C and the share above 20 °C by 0.6 points across all four rules. Whether to repair matters; which rule screens afterwards does not, at that level |

## Where the gain is absent, and why

| ID | Claim | Artifact | Status |
|---|---|---|---|
| A1 | The absolute advantage is stable across outage regimes | `step11_arm_robustness/` | **does not stand**, carried from v17 — met on the stratified arm (−8.7) and pooled, not on the reserved empirical arm (−0.71, CI −2.36 to +0.05) |
| A2 | The empirical-arm null is explained by the seasonality of real outages | `e1_outage_seasonality/start_month_by_length_class.csv` | **stands for outages of 90 days and longer** — 72.3% begin September to January, 17.9% March to July, χ² = 86.1, p = 9.5 × 10⁻¹⁴ |
| A3 | The same seasonality holds for shorter outages | same | **does not stand** — gaps of 30 to 89 days are uniform in start month (χ² = 4.0, p = 0.97) |
| A4 | When outages happen is a lever comparable to which are screened | `e1_outage_seasonality/maintenance_calendars.csv` | **invalid_pending_recompute** — cross-year truncation bug in `scripts/210_v18_outage_seasonality.py` (fixed in code; numbers not yet recomputed). Withdrawn from conclusions |

## Representativeness

| ID | Claim | Artifact | Status |
|---|---|---|---|
| R1 | The calibrated screen retains high-elevation station-years less often than the incumbent | `e4_representativeness/elevation_retention.csv` | **stands** — ρ = −0.26 (p = 0.011) on development and −0.27 (p = 0.077) on reserved, against −0.05 and −0.10 for the length rule; reserved retention 77.7% (lowest tertile) against 66.9% (highest) |
| R2 | The same holds by donor regime | `e4_representativeness/representativeness_frontier.csv` | **stands** — 57.1% against 72.5% on development, a 15.4-point spread, while the length rule tilts the other way |
| R3 | The distortion can be removed at a stated price | same | **stands** — stratifying within donor regime and elevation tertile costs 0.31 points on development and 0.30 on reserved and flattens both |
| R4 | Stratifying on one attribute fixes the other | same | **does not stand** — donor-regime balancing leaves ρ = −0.235 with elevation; both must be declared |
| R5 | Catchment attributes should be inputs to the screen | `step21_hydrology/` | **not claimed**, carried from v17 — no attribute predicts the screening benefit, and they are unavailable outside the United States panel |

## Assumptions

| ID | Claim | Artifact | Status |
|---|---|---|---|
| M1 | Real missingness is uninformative about the values it hides | `e7_informative_missingness/` | **weakly false, and bounded** — donors run +0.063 °C warm through gaps of a week or less (p = 0.017), which is 3% of the within-station anomaly scale; the only class with an effect above a tenth of the tolerance is 90 days and longer (−0.215 °C on the leading flank, p = 0.081) |
| M2 | The transplant design is defensible | same | **stands on magnitude, not on a null** — stated that way in §5.13 |
| M3 | The axis conclusion depends on the estimator library | `e5_air_forcing/axis_stability.csv` | **does not stand**, which is the desired direction — the timing-minus-length contrast is +0.070 without universal air forcing and +0.081 with it |
| M4 | A fixed preference order over estimators is robust to a change in what is available | `e5_air_forcing/problem_size.csv` | **does not stand** — the information-conditioned policy gets *worse* at donor-less stations when air forcing is added (0.340 → 0.364 °C), because its ladder was written when air was rare. Per-case selection does not have this failure mode |
| M5 | The incumbent is handicapped by the absence of an air-driven reconstruction | `e5_air_forcing/fairness_with_air.csv` | **does not stand** — pairing the length rule with an always-air regression makes it worse (15.16% against 9.00%) |

## Carried forward from v17 unchanged

The gate before the rule (G1–G3), the size of the problem (P1), the mechanism
for the peak endpoint (H1a–H1e), the confirmation and its transfer (H2, H2a,
H2d, H2e, H5, H8), the ablation (H6, H7), the catchment attribution (HY1–HY5),
the calibration results (H3, H3b, H3c, H3d), the downstream results (H4a, H4b,
H4c) and the reproducibility repairs (R1–R3) all stand as recorded in
`paper/v17/claims_v17.md`. Only the operating-point rows that used the
mis-stated 140-day limit have moved.

## Not claimed

| ID | Statement | Why |
|---|---|---|
| N1 | Prediction at ungauged sites | the screen uses the station's own history |
| N2 | The 91-day crossover transfers to other climates or variables | it depends on how concentrated the thermal year is and how far the peak wanders; the *protocol* for measuring it is what transfers |
| N3 | Outages that straddle a calendar year | the design places outages within one year |
| N4 | A decadal trend | eleven complete years per station is too short, and the slope RMSE is reported as a diagnostic only |
| N5 | That changing the screening rule changes a regional mean | it does not, by more than 0.1 °C (D4) |
| L | A universal recoverability threshold independent of model and training | forbidden, carried over |
