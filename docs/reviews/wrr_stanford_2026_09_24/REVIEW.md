# Referee report — *Water Resources Research*

**Manuscript:** "Which property of a data gap matters depends on which thermal
metric you want: outage timing governs warm-season extremes, outage length
governs the annual mean" (`paper_archived/v17/manuscript.md`, draft of 2026-09-23).

**Reviewer:** third referee, invited by the editor after two prior rounds.

**Recommendation: MAJOR REVISION.** I want to be candid about the width of that
verdict. The internal validity of this study is in the top decile of what I
referee for this journal: the population is large and multi-national, the split
is declared at the right clustering level, the confirmation panel was opened
once, four claims are reported as failed, and the incumbent is handed an oracle
reconstruction and still loses. If the paper's only problem were polish I would
recommend minor revision and be pleased to see it in WRR. It is not. The paper
has a *population* problem, a *deployment* problem, and one *citation* problem,
and each of the three attacks the headline claim from a different side. A less
sympathetic referee — and given how small this subfield is, one of your
referees is likely to be an author of the guidance you are correcting — would
convert my comment 3 into a rejection. I am recommending major revision because
I believe every one of my objections is answerable with data you already hold,
and because I ran four of the checks myself to make sure I was not asking for
the impossible. The scripts are in `docs/reviews/wrr_stanford_2026_09_24/probe.py`
and every number I quote below comes from them.

---

## 1. What the paper claims, stated in my own words

A derived thermal statistic inherits its sensitivity to missing data from its
functional form. An annual mean is a sum over all days, so its error scales with
how many days are gone. A hottest-30-day mean is an extreme supported on a short
window, so its error scales with whether that window survived. Therefore a
record-admission rule that thresholds the longest consecutive gap — the
quantitative guidance that exists — is conditioning on the wrong variable
whenever the target statistic is a warm-season extreme, and the two regimes
should reverse. The authors demonstrate the reversal on 5,114 fully observed
station-years with 51,524 transplanted outages, build a screening rule on the
correct axis, freeze it, and score it once on 36 reserved networks, where it
cuts the consequential-error rate from 9.7% to 2.5% at matched retention.

That is a clean argument, and it is correct as far as it goes. My objections are
about how far it goes.

---

## 2. Major comments

### Major comment 1 — The headline number is computed on a population that does not exist, and the paper knows it

This is my principal objection.

The abstract, the key points, the conclusion and the title all rest on the
−7.1-point contrast. Section 5.7 then reports that this number is a weighted
average over two arms whose base rates differ by an order of magnitude, and that
on the **empirical arm — the one built from the outage geometry these very
networks actually experience — the reserved contrast is −0.71 points with a 95%
interval of (−2.36, +0.05) that contains zero.** The pre-registered five-point
effect is met on the stratified arm and on the pooled mixture, and is not met on
the only arm that describes reality. The supplement (S3) records that the
weighting between the two arms was never declared in the freeze.

I want to state plainly what this means, because §5.7 states it gently. The
pooled contrast is not an estimate of anything an agency will experience. It is
an estimate of what would happen if outages were drawn from a design the authors
constructed to make the response surface estimable. That design was the right
thing to build — I would have insisted on it — but it is an instrument for
measuring the mechanism, not a population for measuring a benefit. Reporting a
number computed on it as *the* result, in the abstract, in the key points, and
in the sentence "reduces the consequential-error rate by 7.1 percentage points
relative to published guidance", is overclaiming of a kind this journal should
not print. The honest headline is two numbers, not one: the mechanism is large
and general; the operational benefit is conditional on outage regime and, under
the regime these agencies currently experience, it is not resolvable on this
panel.

I do not think this is fatal, because I think the authors have the material to
explain *why* the empirical arm is null, and the explanation is itself a
hydrological finding they are currently sitting on. I ran the check. Across all
457 stations in your own archive there are 6,472 real interior gaps. Their start
months are close to uniform for short gaps, but for gaps of 30 days or more the
distribution is strongly non-uniform (χ² = 44.3 on 11 df, p = 6.5 × 10⁻⁶):
**55.8% of long outages start between September and January and only 30.7%
between March and July.** Long outages in these networks begin in autumn and
winter — after the warm season has been recorded. The empirical arm is null
because agency failure-and-maintenance calendars already protect the summer
peak, largely by accident. That is a far more interesting sentence than the one
currently in §5.7, it converts an embarrassing null into a mechanism, it is a
result about rivers and the people who monitor them rather than about
estimators, and it makes §6's monitoring-design argument quantitative instead of
hypothetical. It also sharpens the scope of your recommendation: the axis
substitution matters for the archives, regions and years in which long outages
*do* fall in summer, and you should identify who those are.

**What I require.** (i) Restate the abstract, key points and conclusion so that
the primary operational claim is arm-specific and the pooled number is not
presented as an unconditional effect. (ii) Add the real-outage seasonality
analysis above, with the χ² and the monthly distribution, as a subsection, and
use it to explain the empirical-arm null. (iii) Report the fraction of real
station-years in your own archive that fall in the regime where the axis matters
— I make it 28.7% of incomplete years having at least one peak-window day
missing and 261 years with more than half the peak window gone — so the reader
can size the affected population instead of guessing.

### Major comment 2 — The loop is never closed on a real incomplete record

Every number in this paper is computed on a complete station-year with a
synthetic hole punched in it. That is the only way to have truth, and I accept
the design. But it means the paper never once exercises its rule on a record
that actually has a gap, and a reader of this journal will notice that the
2,422 genuinely incomplete station-years sitting in your own archive — 32% of it
— appear in the manuscript only as a source of "realistic outage geometry."
They are the population the rule is for, and they have been used for their
shape and discarded for their substance.

You cannot score accuracy on them. You can do three other things, and all three
are more convincing than another robustness table.

First, **report the decision flip rate.** I did this. Of the 2,422 incomplete
station-years, the Johnson unfilled limit (longest run ≤ 49 d) admits 83.2% and
a peak-window rule at 10% hidden admits 81.2% — nearly equal retention, exactly
the comparison your paper insists on — and **the two rules disagree on 15.1% of
station-years.** 207 years are admitted by the incumbent and rejected on timing:
these are records that enter archives today with their peak window hidden. 158
are rejected by the incumbent and admitted on timing: long but off-peak outages
that are being discarded for nothing. Those two integers are the most
practically consequential numbers I can extract from this work and neither
appears in the manuscript.

Second, **transport the validated error model.** You have a conformal object
calibrated on cases and validated out of sample. Apply it to the real incomplete
years, report the predicted consequential-error rate of the incumbent-admitted
set against the timing-admitted set, and be explicit that this is a model-based
extrapolation with the exchangeability assumption stated. A referee will accept
a clearly labelled extrapolation; a referee will not accept the population being
ignored.

Third, **show the scientific consequence on the real archive.** Recompute a
regional quantity — count of station-years above a cold-water criterion, or the
distribution of annual peaks — over the archive admitted by each rule, and show
whether the picture changes. If it does not change, say so; that is a useful,
publishable, deflationary result. If it does, you have the paper's best figure.

### Major comment 3 — The incumbent is mis-stated, and the endpoint you attribute to it is not the endpoint it was written for

This is the comment I would expect to kill the paper if it goes to the wrong
referee, and it is entirely repairable.

Section 1 states that Johnson et al. (2021) find records missing "up to about
seven to nine consecutive weeks still support annual thermal-signal estimation,
and imputation extends the tolerable window to roughly thirteen weeks."
`frontier.py` hard-codes `JOHNSON_FILLED_DAYS = 91` and §5.4 places a comparison
"at the retention implied by the published thirteen-week guideline." The source
says something else. Its abstract states that "imputation of missing data
expanded this range to approximately **20 weeks**, with the greatest improvements
in parameter estimation between 9 and 27 weeks of imputed missing data," and its
closing guideline sentence names "more than approximately seven consecutive
weeks of missing data or **20 weeks** of imputed data." Thirteen weeks is not in
the paper. The imputed limit is 140 days, not 91. Your operating point for the
incumbent is therefore placed at a threshold 50 days stricter than the guidance
you name — which happens to flatter the incumbent at that point, so this is not
a self-serving error, but it is an error in the one citation the whole paper is
positioned against, and it is checkable in thirty seconds.

The deeper version of the same comment is more serious. Johnson et al. estimate
**mean, phase and amplitude from a sine-wave linear regression** fitted to the
annual series. They do not compute a hottest-30-day mean and they make no claim
about warm-season extremes. Your framing — "published completeness guidance
screens records on gap length, which is the weaker axis for the summer extreme
used in cold-water habitat assessment" — is therefore an argument about the
*misapplication* of their guidance, not about their guidance. As written, a
reader can fairly accuse you of refuting a claim nobody made. Two things are
needed and neither is optional. First, say explicitly that the guidance was
derived for sine-fit annual parameters and is being applied in practice beyond
its stated endpoints, and **document that practice with citations** — agency
monitoring standards, published studies that screen on a completeness threshold
and then report a summer statistic. At present the sentence "Agency monitoring
standards specify a minimum share of the year that must be present" carries no
citation at all, and the entire premise of the paper is that this practice
exists. Second, and this is the opportunity rather than the obligation:
**reproduce their estimator on your panel.** Fit the sine-wave regression, take
their three parameters as three additional endpoints, and run your axis
comparison on them. Your theory makes a sharp, falsifiable, and rather beautiful
prediction here — the sine-fit *mean* is a whole-year functional and should be
length-governed; the *phase* is a location parameter and should be timing-
governed; the *amplitude* sits between. If that comes out as predicted, you will
have explained Johnson et al.'s own reported inconsistency on Johnson et al.'s
own estimands, rather than by analogy from a different statistic, and comment 3
turns from your biggest liability into your strongest result. If it does not
come out as predicted, you need to know that before a referee does.

### Major comment 4 — Screening on difficulty selects on catchment type, and the paper does not look

Section 5.3 asks whether basin attributes predict how much the screen *gains*
and correctly reports that none does. That is not the question that matters for
an archive. The question is which stations the screen *keeps*, because a rule
that lowers the average error by preferentially discarding hard sites has bought
accuracy with representativeness, and in this application the hard sites are not
a random subset — §5.3 says so itself: high-elevation, steep catchments have the
least exchangeable donors. Those are cold-water headwaters. They are the reason
anyone computes a summer thermal extreme.

I ran this. At 70% retention on development cases, per-station retention under
the calibrated screen correlates with site elevation at Spearman ρ = **−0.259
(p = 0.011)**, and on the reserved panel at ρ = **−0.273 (p = 0.077)**. Under the
incumbent length rule the same correlation is ρ = −0.053 (p = 0.60) and
ρ = −0.101 (p = 0.52) — that is, **the length rule is elevation-neutral and your
screen is not.** The same pattern appears in donor regime, which is the variable
you stratified the split on: on development cases the screen retains **57.1% of
station-years at donor-less stations against 72.5% at donor-rich stations**,
while the length rule retains 73.6% and 68.8% — it tilts the other way.
Dispersion of per-station retention rises from 0.095 under the length rule to
0.151 under the screen, and the worst-served network falls from 37.5% retention
to 27.6%. The mean annual peak of the retained development archive shifts by
+0.18 °C under the screen against +0.01 °C under the incumbent, which is a
selection-induced warm bias of a third of an interannual standard deviation in
the quantity the archive exists to report.

None of this invalidates the paper. All of it needs to be in the paper, because
it is the first thing a monitoring agency will ask and because an unexamined
version of it is how a well-intentioned quality rule quietly deletes the
mountain stations from a national thermal archive.

It also has a cheap fix, and I checked that too. Applying the screen at equal
retention *within* donor regime rather than globally costs **0.23 points on
development (2.93% → 3.17%) and is free on the reserved panel (2.53% → 2.52%)**,
and it equalises retention across donor regimes exactly. It does *not* fix the
elevation tilt (ρ = −0.235 after balancing), so if you want elevation neutrality
you must stratify on elevation, and you should report what that costs. I would
present this as a design contribution rather than a concession: a screening rule
for a public archive has two objectives, error and representativeness, and you
are in a position to show the trade-off curve between them. That is a better
methodological contribution than the conformal machinery, which §5.6 already
concedes is worth 0.2 points.

### Major comment 5 — The reconstruction library cannot support the claim that the comparison is fair, because the field's standard method is absent

Section 5.5 argues persuasively that the incumbent was not handicapped, by
pairing it with an oracle over the *available* estimators. The weakness is in
the word "available." Your estimator set is: observed days, day-of-year
climatology, smoothed climatology, linear interpolation, donor ridge, and an
air-driven ridge. The air branch is supported on **2.3% of development cases and
0.85% of reserved cases**, and the supplement says NASA POWER was used only
"where it was already available in the archive."

For a water-resources audience this is the most exposed part of the paper.
Air-temperature-driven regression is *the* standard method for filling stream
temperature; Beaufort et al. (2022), which you correctly identify as the closest
prior work, uses exactly that to reconstruct thermal peaks, and the ML review
you cite counts 57 studies most of which are air-forced. Meanwhile 36 of your
110 development networks have no synchronous donors at all, so for those the
entire estimator library reduces to climatology and interpolation. Your
headline "problem exists" number — 1.31 °C on recorded days against 0.242 °C for
the best reconstruction — is therefore a statement about a library that omits
the method a practitioner would reach for first, at precisely the sites where
they would need it most.

The obstacle is not data availability; it is that station coordinates were never
carried into the v17 pipeline. ERA5-Land and NASA POWER are global, free, daily,
and cover every one of your nine providers; GAGES-II already gives you latitude
and longitude for 140 US stations and every European provider publishes station
coordinates. I would require air forcing joined for all 457 stations, the
air-driven estimator re-enabled, and three numbers rerun: the recorded-days
baseline, the best-reconstruction baseline, and the oracle in Table 3. I expect
the axis result to survive — it is a statement about which cases are hard, not
about how well they are repaired — but the *size* of the problem and the
fairness argument both depend on it, and a referee who works on air–water
regression will not let this pass.

### Major comment 6 — The dichotomy is real but the two axes are mislabelled, and the correct label is a stronger result

Table 1 reports two "timing" axes. Peak-window overlap reaches AUC 0.819 for the
30-day peak; warm-season observed fraction reaches 0.820. But warm-season
observed fraction is *a count of missing days restricted to a window* — it is a
length measure with a domain restriction. In your own development cases it
correlates with the longest run at −0.86 and with total missing days at −0.855.
So the finding is not "timing beats length." The finding is that **missingness
must be measured on the support of the estimand rather than on the calendar
year**, and "timing versus length" is the special case of that principle you get
when the estimand is an extreme.

This is not pedantry; three things follow from it, all of which strengthen the
paper.

First, the two regimes stop being a reversal to be explained and become one law
with a parameter. For the annual mean the support is the whole year and the
correct statistic is the total missing fraction; for the 30-day peak the support
is the peak window and the correct statistic is the hidden fraction of that
window. Your own `metric_generality.csv` already shows warm-season coverage
within 0.03 AUC of the best axis for *every one of the five endpoints*, which is
what a single unifying statistic looks like.

Second, it generates a new falsifiable prediction with a continuous knob, which
is the thing this paper currently lacks and which would move it from a good
empirical study to a law. Compute the hottest-*k*-day mean for k = 1, 3, 7, 15,
30, 60, 90, 182, 365 on your existing station-years and plot the AUC advantage
of support-restricted missingness over whole-year missingness against k. The
theory predicts a monotone decay to zero as the support widens to the year, and
it predicts where the crossover sits. One figure, one script, existing data. If
the curve is monotone you have a quantitative law; if it is not, you have found
something you need to explain. I regard this as the single highest-return
experiment available to you.

Third, it fixes the title, which currently asserts a dichotomy the paper's own
evidence says is a continuum.

### Major comment 7 — The transplant design assumes missingness is uninformative and never tests it

Every case is a real-or-designed mask transplanted onto a complete year. That is
valid only if the mask is independent of the hidden values given the covariates
— and in this domain there are obvious reasons it might not be. Loggers are lost
to floods, buried by ice, and fouled in low flow, and all three co-occur with
anomalous thermal conditions. If real outages are informative, the study
systematically understates the error of every estimator, because it has replaced
"the days you lost" with "days like the ones you kept."

Say so, and then test it, because the test is easy and — I ran it — the answer is
mostly in your favour. Across the 6,472 real gaps in your archive, the mean
anomaly of the seven days preceding a gap, relative to that station's
day-of-year climatology, is +0.018 °C for 1–7 day gaps (p = 0.44), +0.038 °C for
8–29 day gaps (p = 0.56) and −0.002 °C for 30–89 day gaps (p = 0.98). Only for
gaps of 90 days or more is there any hint of structure (−0.215 °C, p = 0.081),
and those are 150 gaps. So for the overwhelming majority of real outages the
exchangeability your design needs is empirically defensible, and you should say
that with the numbers rather than leaving a referee to raise it as a hole. Add a
paragraph, a table, and a limitation confined to very long outages.

---

## 3. Minor comments

1. **§4.1, the denominator.** 5,114 complete station-years from 457 stations is
   about eleven years per station, and §5.9 computes Theil–Sen slopes on them.
   A decadal trend on ~10 points is not a trend; either drop the trend
   subsection to a sentence or report the slope uncertainty alongside the RMSE
   so the reader can see how little is being resolved.
2. **§4.4.** In the stratified arm there are no cases with outages under 20 days
   and peak overlap above 0.75, which is geometry rather than a defect, but the
   headline illustration ("a 30-day outage over the peak is worse than a 200-day
   outage that misses it") should state the band over which the design supports
   it.
3. **§4.3.** The tolerance fraction 0.47 is described as a modelling choice in
   §7 but appears without that qualification in §4.3. Move the caveat forward.
4. **§5.2.** "Its permutation importance is −0.004" — a negative permutation
   importance means the feature is noise in that model, not that it is harmful;
   a clause saying so would prevent a misreading.
5. **§5.3.** The GAGES-II attribution rests on 136–140 stations in one country
   and is used to make a general statement about which rivers are hard. Say
   "in the United States subset" in the topic sentence, not only in §7.
6. **§5.8.** "The screening result is identical under every calibration, to four
   decimal places" — state the monotonicity argument first and the numerical
   check second; as written it reads as a coincidence.
7. **§6.** The maintenance-scheduling recommendation is currently a hypothetical.
   Given the September–January concentration of real long outages (comment 1),
   you can state it as a measured description of current practice and quantify
   the counterfactual cost of the opposite schedule.
8. **Table 5** would be clearer if the pooled row were shown alongside the two
   arms, so the reader can see the mixture weight doing the work.
9. **References.** Six references for a WRR submission is too few, and it is the
   visible symptom of major comment 3: the practice the paper overturns is
   undocumented. Agency standards, the thermal-regime metric literature, the
   cold-water criteria literature, and the large-sample hydrology benchmark
   conventions (e.g. Caravan) all belong here.
10. **No system diagram.** For a paper whose contribution is a decision
    procedure, there is no figure showing what the procedure is: what the
    inputs are, what may not be read, where calibration sits, what the two
    action spaces are. Figures 1–6 are all results. A reader cannot reconstruct
    the pipeline from prose.

---

## 4. Scores

| dimension | score | note |
|---|---:|---|
| significance of the problem | 8.5/10 | record admission governs every thermal archive; the cost is quantified before a method is proposed |
| novelty of the insight | 6.5/10 | "condition on the support of the estimand" is a known statistical principle; its application to record admission in hydrology, at this scale, with a reversal demonstrated, is new |
| novelty of the design | 5/10 | the screen is standard split-conformal selective prediction; the genuinely novel design element is the *gate-before-rule* protocol in §4.7, which is under-sold |
| experimental design (internal validity) | 9/10 | gate, mechanism, main result, ablation, oracle incumbent, boundary, transfer, reproducibility — all present and separated |
| experimental design (external validity) | 5/10 | the effect is measured on a constructed population; the real one is null and unexplained; real incomplete records are never touched |
| fairness of the comparison | 6/10 | excellent against the estimators present, but the field's standard air-driven estimator is supported on 0.85% of confirmation cases |
| statistical rigour | 8.5/10 | clustered throughout, pre-registered, multiplicity addressed by prediction |
| hydrological content | 6.5/10 | much improved by §5.3; still no physical account of *when* records fail, which the data supports |
| honesty about limits | 10/10 | four failed claims reported; I have rarely seen better |
| reproducibility | 9/10 | not the limiting factor |
| **overall** | **major revision** | the science is close; the claim is wider than the evidence |

## 5. On whether the design is closed end to end

Asked directly: **the loop closes in simulation and does not close to practice.**

The chain the paper completes is: real records → complete-year truth → designed
outage → reconstruction → error of the derived statistic → screening decision →
error among retained → held-out confirmation. Every link in that chain is
present, measured, and pre-registered, which is more than most papers in this
journal manage.

Two links that the argument requires are missing. The chain never returns to a
record that actually has a hole in it (major comment 2), so the paper
demonstrates that the rule *would* work rather than that it *does*. And the
chain never propagates to a scientific or management conclusion that changes:
the exceedance analysis in §5.9 is computed on the same synthetic cases, so the
"downstream consequence" is downstream of the simulation, not downstream of the
archive. Close those two and the paper is no longer arguable.

## 6. What I require for the next round

1. Restate the operational claim as arm-conditional; explain the empirical-arm
   null using the seasonality of real long outages (comment 1).
2. Deploy both rules on the 2,422 real incomplete station-years: flip rate,
   transported risk, and the change in a regional aggregate (comment 2).
3. Correct the Johnson et al. imputed limit to 20 weeks, rerun that operating
   point, document the practice being corrected with citations, and reproduce
   the sine-fit mean/phase/amplitude endpoints on your panel (comment 3).
4. Report retention by catchment attribute and donor regime under both rules,
   and give the error-versus-representativeness trade-off of a stratified screen
   (comment 4).
5. Join air forcing for all stations and re-enable the air estimator; rerun the
   problem-size and oracle tables (comment 5).
6. Add the support-width sweep over hottest-*k*; retitle around the support
   principle (comment 6).
7. Add the informative-missingness test and confine the limitation to long
   outages (comment 7).
8. Add a system/decision diagram and a study-design diagram (minor 10).

Items 1–7 are experiments; all seven use data already in the repository. Item 3
additionally requires a literature search, and item 5 requires one download.
