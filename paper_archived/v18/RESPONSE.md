# Response to the referee report of 2026-09-24

Reference: `docs/reviews/wrr_stanford_2026_09_24/REVIEW.md`. The referee ran four
checks against our own artifacts before writing; we have reproduced all four,
and three of them became sections of the paper. We answer each comment with
what changed, where, and what the evidence now is — including the three places
where a prediction we declared for this round failed.

Section numbers refer to `paper/v18/manuscript.md`.

---

## Major comment 1 — the headline number is computed on a population that does not exist

**Accepted, in full.**

The abstract, key points and conclusion no longer present −7.1 points as an
unconditional effect. The abstract now states that the mechanism is general and
the operational gain regime-dependent, and §5.9 says plainly that the headline
is an effect on a mixture that includes a designed arm and is not an estimate of
what any agency will experience next year.

The referee asked us to explain the empirical-arm null and suggested the outage
calendar. We built that analysis (E1) and it is partly what was suggested and
partly not, so we report both halves. Across 6,472 real interior gaps, outages of
**90 days and longer** start overwhelmingly in autumn and winter — 72.3% between
September and January against 17.9% between March and July, χ² = 86.1,
p = 9.5 × 10⁻¹⁴ — but outages of **30 to 89 days are uniform** in start month
(χ² = 4.0, p = 0.97). The protection is real and it is confined to seasonal
shutdowns. Claim A3 in the matrix records the half that failed.

We then priced the calendar properly, which the referee did not ask for and which
we think is the most useful number in the paper. Holding the real outage-length
distribution fixed and changing only *when* outages begin, a March-to-July
calendar raises the consequential-error rate from 8.7% to **13.2%** and a
September-to-January calendar lowers it to **4.9%** — swings of +4.4 and −3.9
points against a screening gain of 6.3. §6 now opens with this rather than with
the screening rule, because it is available before any data are lost.

Finally, §4.1 and §5.10 give the size of the affected population: 28.7% of real
incomplete station-years have at least one peak-window day missing and 261 have
more than half of it gone.

## Major comment 2 — the loop is never closed on a real incomplete record

**Accepted. This is now §5.10, and it is the section we would point an editor
at.**

All three things the referee asked for are there.

*The flip rate.* At the unfilled limit the length rule admits 83.2% of the 2,422
real incomplete station-years and a peak-window rule at 10% hidden admits 81.2%;
they disagree on **15.1%** — 207 admitted by the incumbent and rejected on
timing, 158 the other way. At the corrected imputed limit (comment 3) the
incumbent admits 91.7% and the disagreement is 11.6%, of which 267 are in the
dangerous direction.

*The transported risk.* A model of P(consequential error) fitted on development
cases from decision-time features only, and checked for calibration on the
reserved panel before use (largest decile miscalibration 6.2 points, under 1.6 in
nine of ten deciles), predicts 0.98% among the years the unfilled limit admits
and **0.26%** among those the peak-window rule admits at essentially equal
retention. It is labelled an extrapolation everywhere it appears, and §5.13 tests
the exchangeability it assumes.

*The scientific consequence.* Here we report against ourselves. The choice of
screening rule moves the archive's mean annual peak by **less than 0.1 °C** and
the share of station-years above 20 °C by 0.6 points. Claim D4 is recorded as
not standing. What the rule does change, and what needs no truth to see, is
composition: the published imputed limit admits **17 station-years whose annual
peak was never observed** and 82 whose peak window is mostly gone; the unfilled
limit admits 2 and 45; the peak-window rule admits none of either.

## Major comment 3 — the incumbent is mis-stated, and its endpoint is not ours

**Accepted, and the referee was right on both halves. This was the most serious
error in the previous version.**

*The number.* `frontier.py` hard-coded 91 days. Johnson et al. say twenty weeks.
`JOHNSON_FILLED_DAYS` is now 140 and every artifact that used it was re-run. The
consequence is material and is against us: the incumbent's retention at that
operating point rises from 74.0% to **85.1%** on the reserved panel and the
screen's advantage there falls from 6.2 to **4.4** points. §5.6 reports the
corrected point, S3 records the error, and a test pins the constant.

*The endpoints.* We reproduced Johnson et al.'s sine-wave linear regression on
our panel and scored our axis comparison on their three parameters (§5.4). The
result is that **on the estimands their guidance was derived for, their guidance
is right**: a completeness threshold is the best axis for the fitted mean
(0.845 against 0.672 for peak-window overlap) and within 0.02 AUC of the best for
the phase. Claim J7 — that the standing guidance gets an ordering backwards — is
**withdrawn**. What we correct is the transfer of a threshold to an estimand it
was not derived for, and §1 now says so in those words.

*The practice.* §1 documents the practice with citations rather than asserting
it: Mauger et al. (2015) for an agency standard that specifies a deployment
window, Mauger et al. (2017) for a published study that screens site-years at 90%
completeness and then reports a warm-season extreme, WAC 173-201A-020 for the
regulatory metric and its criteria. The reference list has grown from 6 to 18.

*The bonus the referee predicted.* Their three parameters have three different
supports — a constant, two lobes at the extremes, two lobes at the transitions —
so a timing effect appears for one of them and not the others. That is what
"inconsistent in space and time" looks like from inside, and §5.4 now reports it
as a measurement rather than an interpretation (claim J6, upgraded).

## Major comment 4 — screening on difficulty selects on catchment type

**Accepted. This is §5.12, and we agree it should have been in the previous
version.**

The referee's numbers reproduce. At 70% retention the calibrated screen's
per-station retention correlates with site elevation at ρ = −0.26 (p = 0.011) on
development and −0.27 (p = 0.077) on the reserved panel, while the incumbent is
elevation-neutral (−0.05 and −0.10). On the reserved panel the screen keeps 77.7%
of station-years in the lowest elevation tertile and 66.9% in the highest, a
10.8-point spread against 1.7 for the length rule; by donor regime the spread is
15.4 points on development.

We took the referee's suggestion to present the fix as a design contribution
rather than a concession. §5.12 gives the error-against-representativeness table
for six rules. Stratifying within donor regime *and* elevation tertile costs
**0.31 points** on development and 0.30 on reserved and flattens both
distortions. The referee also correctly anticipated that donor-regime balancing
alone does not fix the elevation tilt (ρ = −0.235 after balancing); claim R4
records that, and §6 now recommends that a screening rule be specified with its
strata and that retention by covariate be reported alongside the error rate.

## Major comment 5 — the field's standard reconstruction is absent

**Accepted, and fixed at the root.**

The obstacle was, as the referee diagnosed, that station coordinates were never
carried into the pipeline. We assembled them for all **457 of 457** stations —
from the providers' own catalogues, the USGS NWIS site service for 195 gauges,
and ARSO's public feed for 47 — and pulled NASA POWER daily 2 m air temperature
for the whole panel, 1981 to 2026, 16,679 days per station. Air support rises
from 2.3% to **98.6%** of development cases and from 0.85% to 100% of reserved
cases.

Four results follow (§5.7). The problem shrinks: the deployable reconstruction
error falls from 0.242 to 0.225 °C and the oracle from 0.165 to 0.130 °C. The
axis conclusion does not move — the timing-minus-length AUC contrast is +0.070
without universal air forcing and +0.081 with it — which is the direction that
matters, since the claim is about which cases are hard rather than how well they
are repaired. The screen uses the new information, selecting the air-driven
estimator for 20.0% of cases against 0.07% before. And the incumbent is **not**
rescued: pairing the length rule with an always-air Beaufort-style regression
makes it worse (15.16% against 9.00% for the information-conditioned policy).

One unexpected result is reported because it was unexpected: the *fixed*
information-conditioned policy gets slightly worse at donor-less stations when
air becomes available (0.340 → 0.364 °C), because its preference ladder was
written when air was rare. A fixed ladder is not robust to a change in what is
available; per-case selection is. Claim M4.

The pre-registered confirmation is **not** re-scored against the new forcing;
§5.7 is a development-panel sensitivity analysis and says so.

## Major comment 6 — the axes are mislabelled, and the right label is a stronger result

**Accepted, and this became the paper's main contribution.**

The referee is right that `warm_observed_fraction` is a count of missing days
restricted to a window — it correlates −0.86 with the longest run — so
"timing beats length" was the wrong name for the finding. §5.2 now says this
explicitly.

We ran the experiment the referee proposed. Sweeping the hottest-*k*-day mean for
*k* ∈ {1, 3, 7, 15, 30, 60, 90, 182, 365}, the advantage of a fixed peak window
over whole-year completeness runs +0.074 AUC at *k* = 1, holds flat to *k* = 30,
decays to +0.050 at *k* = 60, **crosses zero at 91 days**, and reaches −0.173 at
the annual mean. Every network-clustered interval excludes zero except the one at
*k* = 90, which is where the crossing is. The title, the abstract and §1 are
rewritten around this.

Two of the three predictions we declared for that sweep failed, and the failures
produced a better result than success would have. The support-restricted
advantage is **not** monotone — it is a hump peaking at a 60-day support — and
the estimand's own support is **not** the best conditioning set below *k* = 30,
where a fixed 30-day window beats it by 0.064 AUC. The cause is that a support
has to be *located* before it can be conditioned on, and the climatological
window is an estimate whose location wanders. We measured the wander: the median
year-to-year circular standard deviation of the realised window's centre falls
from 16.7 days at *k* = 1 to 7.4 days at *k* = 90, and the gain from widening the
conditioning window tracks it almost exactly (+0.102 AUC at *k* = 1, zero at
*k* ≥ 90). The law therefore needs one correction — condition on the support
dilated by the uncertainty in its own location — and one very practical
consequence follows: AUC at the best conditioning window is 0.85 to 0.86 for
*every* estimand from the annual maximum to the half-year mean, and the best
window is 60 to 90 days throughout. An agency needs one window, not one per
metric. It also means the screen we deploy, which conditions on 30 days, leaves
0.025 AUC on the table for its own endpoint; §5.3 says so.

The third failure is on the sine-fit phase: two hand-chosen transition windows
beat peak-window overlap decisively (+0.249) but tie outage length. Weighting
every day by the influence function itself recovers the advantage (0.847, beating
whole-year missingness by +0.013 with a clustered interval excluding zero). The
lesson, now in §5.3, is that "condition on the support" is exact and "condition
on a window near the support" is an approximation whose quality depends on how
concentrated the influence is.

## Major comment 7 — the transplant design assumes missingness is uninformative

**Accepted. §5.13, and the answer is mostly but not entirely in our favour.**

Across the 6,472 real gaps, the mean anomaly of the seven days preceding a gap is
+0.018 °C for gaps of a week or less (p = 0.44), +0.038 °C for 8–29 days
(p = 0.56), −0.002 °C for 30–89 days (p = 0.98) and −0.215 °C for 90 days and
longer (p = 0.081). We added a second test the referee did not ask for: donors
that keep recording through a gap. They run **+0.063 °C warm** through gaps of a
week or less, which at this sample size is detectable (p = 0.017).

We therefore do not claim a null. §5.13 states that missingness is weakly
informative, that every effect is under half a tenth of the 0.5 °C tolerance and
under a seventh of the within-station anomaly scale, and that the design is
defended on magnitude rather than on absence of an effect. The limitation in §7
is confined to outages of three months and longer, where the leading flank runs
cold. Claim M1 records it as weakly false and bounded.

---

## Minor comments

1. **Trend on eleven years.** Reduced to a diagnostic. §5.11 now says the panel
   averages eleven complete years per station, that this is too short to resolve
   a decadal trend, and that the only claim drawn from the slope RMSE is that
   reconstructing at all is the dominant step. N4 records that no trend is
   claimed.
2. **Design coverage band.** §4.4 and §7 state the band over which the design
   supports the headline illustration.
3. **Tolerance caveat moved forward.** §4.3 now carries it.
4. **Negative permutation importance.** §5.2 explains that a negative
   permutation importance means the feature is noise in that model.
5. **GAGES-II scope in the topic sentence.** §5.5 and §5.12 both say "United
   States subset" where the claim is made, not only in the limitations.
6. **Monotonicity before the numerical check.** §5.13 gives the argument first.
7. **Maintenance scheduling as a measurement.** Done, and promoted: §6 opens
   with it and it is one of the three key points.
8. **Pooled row alongside the arms.** Table 8 keeps the arms; the pooled figure
   is the headline and is now explicitly identified as a mixture in the same
   paragraph.
9. **Reference list.** 6 → 19, covering agency standards, the regulatory metric,
   air–water regression, large-sample thermal databases, the influence function,
   missing-data theory and conformal inference.
10. **System diagram.** Four schematics, drawn in draw.io with the sources in the
    repository: the problem frame (Figure 1), the screening architecture
    (Figure 2), the study design (Figure 3) and the agency workflow (Figure 14),
    plus the evidence chain as Figure SI-1. A test checks that each PDF is
    regenerated from its source.

---

## What we did not do

We did not re-score the reserved panel. Everything added in this round — the
support sweep, the sine endpoints, the deployment, the representativeness
analysis, the air forcing — was developed after the panel was opened, so it is
reported on development cases and the reserved numbers that appear are labelled
as no longer blind. Re-freezing and re-confirming the widened conditioning window
of §5.3, which the evidence says is worth 0.025 AUC on our own endpoint, is the
obvious next study and we have not done it here.

We also did not fix the information-conditioned policy's preference ladder after
finding it mis-ordered under universal air forcing (M4). Doing so would change
the deployed reconstruction and require re-running the confirmation, so it is
reported as a finding and left for the next round.
