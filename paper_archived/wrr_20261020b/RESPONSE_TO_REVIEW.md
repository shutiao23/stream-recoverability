# Response to the review of 2026-10-20 (commit `e7fc9050df`)

Reviewed commit: `e7fc9050df3d215afa7aa60d0c1410bbadc4c83f`.
Revision: the attribution round of 2026-10-20b, with artifacts under
`results/wrr_submission_ready/major_revision_20261020b/` and the command
`make wrr-round-20261020b`. The earlier response (to the 2026-10-19 review) is kept
below.

The review's judgement was *major revision*: the paper has a worthwhile question and a
positive result for the method, but it had not established that the mechanism is
read correctly, that the key design is necessary, that the method works under
independent conditions, or that adopting it helps. It asked for experiments that
exclude competing explanations rather than for more models. We ran them. Four of
the answers go against the manuscript as it stood, and we changed the manuscript
rather than the question:

1. **The design was not what the text said.** The 53,721 outages are not a factorial
   design: they are single contiguous runs (33,749) and transplanted real geometries
   (19,972); no scattered days exist; the lengths are 14 to 270 days, not 30 to 180;
   gap length and true hidden share still correlate at +0.52 in them. The controlled
   panel is a separately generated 1,899-outage crossed panel on 211 station-years.
   The "+0.45 observed in real records" was the pooled designed-panel value; the real
   replay gives +0.71 [0.44, 0.89].
2. **The fitted score does not need the support feature.** The same model without the
   peak-window share keeps 73.4 % of the external panel against 73.9 % with it
   (+0.3 to +0.8 points, every interval includes zero). Its 7 to 8 point gain over the
   peak-window rule comes from donor information and reconstruction diagnostics.
3. **Refusing hot years is not a hot-year harm.** The fitted score refuses 24.5 % of true
   hot years and 25.5 % of all records; hot years are refused slightly less often
   (excess −1.0 point [−1.6, −0.3]). The abstract and conclusions had joined a
   designed-panel refusal to the real-calendar result; both are separated now.
4. **Most of the "misalignment" contrast is hidden share.** Held fixed within
   strata the contrast falls from 0.66 to 0.19 °C [0.07, 0.26] for climatology.

| review item | status | where |
|---|---|---|
| Op. 1 novelty: move from "support matters" to "how to decide" | done | Introduction, Section 5.1 (prior work credited; the contribution is the attribution) |
| Op. 2 design vs diagnostic groups; feasible region and station-year counts | done, and eight description errors found | Section 2.3, Table 2, SI Tables S7 to S9, `scripts/340` |
| Op. 3 three windows; exact error relation | done | Section 2.1, 3.5, 4.3, Figure 4a to c, `scripts/342` |
| Op. 4 contribution decomposition at one capacity | done | Section 4.3, Table 3, Figure 4d, SI Tables S10 to S12, `scripts/341` |
| Op. 4 "five points" wording; seeds are not independent | done | Section 4.4.1 (lower limits 5.0, 4.6, 4.3 stated) |
| Op. 5 frozen transfer vs local re-fit | **scoped, not run** | Limitations (needs a sealed panel); no frozen-transfer claim is made |
| Op. 6 "no screen" rule | tested, limited | Section 4.4.3, SI Tables S19 to S20, `scripts/344` |
| Op. 7 hot-year null; refusal vs harm; action | done | Section 4.4.2, Figure 5c, SI Tables S21 to S22, `scripts/343` |
| Op. 7 abstract and conclusion mixing designed and real populations | fixed | Abstract, Conclusions |
| Op. 8 risk control by hydrological type and anomalous years | **not done** | the real replay is opened by network (Figure 5b); no hydrological-type or anomalous-year stratification exists |
| Step 1 three falsifiable hypotheses | partly | the three questions of the Introduction were rewritten to match; no separate table |
| Step 5 uncertain-support design | diagnostic only | the true-hidden-share oracle bounds the room (Section 4.3); no implementation |
| Step 6 anomaly replay; co-failure and transfer | **not done** | no anomalous-event or frozen-transfer data in the archive |

## What the audit of our own text found

These are errors in the manuscript, not in the review. `scripts/340` and `scripts/335`
found them while answering Op. 2, and each is fixed:

* "with the remaining missing days scattered at random" -- the generator adds none.
* "target length in {30, 60, 90, 180}" -- the lengths are {14, 30, 60, 90, 120, 180, 270}.
* "their correlation falls to the design value instead of the +0.45 observed in
  real records" -- +0.45 is the pooled designed value; the design value is not reached
  in the 53,721 and the real value is +0.71.
* Figure 3b was drawn with the station-year-paired estimator on 11 station-years in 6
  networks while the text quoted a network-subset estimator with different numbers;
  the two disagree about whether a length effect exists for climatology. The figure
  now shows the station-year-paired estimate at two pre-declared cut-offs (48
  station-years in 12 networks; 11 in 6), the text quotes it, and the other estimator
  is a sensitivity in SI Table S17. The effect is small and distinguishable from zero
  for four reconstructors (0.05 to 0.14 °C) and large for interpolation.
* Figure 3c silently dropped the exact-zero hidden-share class and listed an air
  regression that has no series on the external panel; fixed.
* "the ordering of the five methods at 90 days is the same as at 30" -- interpolation
  moves from second cheapest to most expensive; the 2026-10-20 audit had recorded this
  as fixed, but the sentence was still in the text.
* the peak-window rule's external retention is 66.6 %, not 66.7 %.
* the 418 real-calendar groups rest on 59 recorded gaps and 67 target station-years.
* the crossed panel is not a subset of the 53,721.

## Op. 4 -- where the gain comes from

One learner, one training set, one nested cross-fit, one calibration; the full
specification reproduces the aligned round's fitted score bit for bit
(`determinism_check` in the fingerprint). External retention at the 5 % cap, mean of
three seeds: gap and season 63.2 %, + donors 68.7 %, + reconstruction diagnostics
74.0 %, + station history 73.4 %, + peak-window share 73.9 %. The 2026-10-14
same-information ablation had already found 0.00 points [−1.00, +1.00] for the
support share; the manuscript did not carry it. A small logistic model *does* need
the share (+6.2 to +6.8 points external, +11.4 to +16.3 development). A model given
the true hidden share (not deployable) gains 0.6 to 1.8 points over the one given
the climatological share; a rule that reads it keeps 5.0 to 5.9 points more than the
climatological rule.

## Op. 3 -- the identity

`H30(completed) − H30(truth) = max_W(ē_W − D_W) = ē_S + F`, `F ≥ 0`, verified to
2×10⁻¹³ °C on 9,449 cases. With the true window observed the error is all false peak
(0.06 °C, climatology); with it hidden the hiding channel is −0.75 °C and the false
peak +0.43 °C. Permuting the gap residuals lowers the error by 12 to 27 %, removing
the gap mean by 49 to 59 %. The competing-peak relation was not intervened on and is
reported as before (SI Table S18).

## Op. 6 -- the rule

A composition rule built from designed outages only predicts a pooled failure rate of
3.5 % for the real replay (observed 2.6 to 4.1 %) and never says "no screen" for a
network that needed one (zero of two to four), at the price of advising a screen for
one to three others. The pooled rate hides that two to four of 14 networks fail at 7
to 83 %. The evidence is 3 to 6 station-years per failing network, so the manuscript
offers a description, not a boundary. The cell edges were fixed after the replay's
summaries had been seen; this is disclosed.

## Op. 5 and Op. 8 -- not done

We have no sealed panel and no anomalous-event data, so we did not run a frozen-model
transfer, a risk-control check by hydrological type, or an anomalous-year replay. The
manuscript now says that the external comparison is a local cross-fit and what that
does and does not answer.

---

# Response to the review of 2026-10-19 (commit `bfc797ef43`)

Reviewed commit: `bfc797ef43c28d6346ce68ce51846e20fb2b2e77`.
Revision: the aligned-policy round of 2026-10-20. Every number below is
regenerated by the scripts named in the last column; the round's artifacts are
under `results/wrr_submission_ready/major_revision_20261020/`.

The review's central judgement was that the same method's risk control, actual
replay and environmental judgement had not been closed, because the admitted
object was the policy reconstruction while the calibrated event was the
certificate error. We agree, and we rebuilt the chain rather than patching the
prose. The rebuild changed the headline: with the right object and a
deployment-consistent tie rule, the fitted score's advantage over the
peak-window rule is 7.0–8.3 points on the external panel, not 2.6–3.3, and it
clears the pre-specified five-point margin. It still does not beat the
certificate bound, and on real calendars no screen is needed. The paper is now
written as a method paper with a named regime boundary, not as a claim of
general superiority.

| id | severity | status | what changed |
|---|---|---|---|
| F01 | Blocker | closed | every stage now reads `abserr_policy`; the certificate error survives only as a ranking score |
| F02 | Major | closed | population risk and finite-batch error are separated; the 8.5 % figure is retracted as a misreading |
| F03 | Major | closed | no jitter; whole tie blocks admitted in calibration, evaluation and deployment; the fixed-70 % rule uses a stable case key |
| F04 | Major | closed | `reconstruct_all` is a first-class arm; the regime boundary is measured, not asserted |
| F05 | Major | closed | all three fold seeds; confusion matrix, refusal cost, paired intervals, station-year weighting |
| F06 | Major | closed | the pre-specified margin is now met against the strong transparent baseline; the route decision is stated |
| F07 | Major | closed | manuscript and SI rewritten around one chain; old certificate numbers are historical |
| F08 | Major | closed | the "position governs" law is replaced by a conditional statement with the reconstructor counterexample |
| F09 | Major | accepted as scope | the external comparison is a cross-fit on an opened panel; no sealed claim is made |
| F10 | Minor | closed | counts, units and share-versus-points fixed; the measurement-stratum gap is disclosed |
| F11 | Minor | partly closed | scripts, fingerprints and manifests are in place; the author block remains a human gate |

## F01 — final reconstruction object and failure event

The two failure events disagree on 898 of 13,017 external cases (6.90 %): 408
cases fail only under the policy reconstruction and 490 only under the
certificate. On the development panel they disagree on 830 of 40,704 cases
(2.04 %).

We rebuilt the full protocol on the policy error. `scripts/330` asserts before
any computation that `abserr_policy = |hottest30_<policy_choice> −
truth_hottest30|` on every finite row, so an alignment error aborts the run. The
threshold, the evaluated event and the reported error are now the same column at
every stage; the certificate bounds are used only as ranking scores, which the
review explicitly allowed.

Consequence, measured on the same scores and folds (`scripts/334`):

| panel | event / tie | fitted − peak (pp) |
|---|---|---|
| external | certificate / jitter (old design) | +2.8 |
| external | certificate / whole block | +2.7 |
| external | policy / whole block (new) | +7.2 |
| development | certificate / jitter (old design) | +8.6 |
| development | policy / whole block (new) | +9.7 |

About 4.5 points of the external change come from the object and about 1.3 from
the tie rule. The fitted score now keeps 74.0 % of the external panel at the 5 %
cap (peaks 73.6–74.5 across seeds) against 66.7 % for the peak-window rule, and
the gain clears the pre-specified five-point margin at all three fold seeds. It
does **not** beat the certificate bound: +1.6 points [0.2, 3.1] on the external
panel, −2.6, −1.7 and −2.5 points on development.

Evidence: `p0_01_aligned_policy_admission/`, `p0_05_repair_attribution/`.

## F02 — what the selector's calibration means

The 8.5 % reported previously was the probability that a finite fresh test batch
exceeds the cap, not the probability that the selected threshold's population
risk does. We re-ran 2,000 repetitions per scenario with the deployed rule
imported from the analysis code, and measured the population risk of the
selected threshold on an independent 2,000,000-case reference draw.

| scenario | P(true risk > 5 %) | P(finite batch > 5 %) | retention |
|---|---:|---:|---:|
| baseline | 0.004 | 0.078 | 0.185 |
| near cap | 0.006 | 0.075 | 0.288 |
| unequal groups | 0.004 | 0.046 | 0.296 |
| twelve groups | 0.024 | 0.122 | 0.153 |

The rule is conservative, not miscalibrated. The price is retention: a pointwise
bound keeps 35.9 % in the baseline scenario but violates the cap about six times
as often (7.4 %). We also checked the extreme percentile: re-running the
selection with 10,000 instead of 1,000 bootstrap draws changes the chosen
threshold in 42 of 150 fold-by-score cells, moving the fitted score's retention
by at most 1.0 point and the discrete rules by at most 3.9 points. The paper now
describes the threshold as a calibration decision at this granularity, not a
stable optimum.

Evidence: `p0_02_selection_calibration/`, `p0_01_.../threshold_stability.csv`.

## F03 — one tie rule from calibration to deployment

No jitter is added anywhere. A threshold is an observed value of the raw score,
and admission is `s ≤ τ`, so a tie block is admitted whole in calibration, in
evaluation and at deployment. The fixed-70 % comparison, which is a second
deployment rule, breaks ties with a stable case key
(`network|station|year|realisation`) rather than row order. The ablation above
bounds the cost of the old inconsistency at about 1.3 points on the external
panel.

## F04 — does screening pay against "no screen"?

Yes on designed outages, no on the real calendars. On the external panel,
`reconstruct_all` fails at 15.3 %, so the 5 % cap binds and retention is the
comparison. On the 418 real calendars the median gap is 7 days, the median
missing fraction is 2.2 %, and 5.7 % of candidates hide more than half the peak
window; admitting every reconstruction puts 2.6–4.1 % of records over the
tolerance, already under the cap. The screens keep 93–96 % and reduce the failure
rate to 0.5–1.7 %; the fitted score's advantage over the peak-window rule falls
to 0.2–2.4 points, and only two of nine level-by-seed intervals exclude zero. We
did not tighten the cap to make screening look necessary; the regime boundary is
the result.

Evidence: `p0_03_real_calendar_adoption/`, manuscript §4.4 and §5.3.

## F05 — the environmental judgement

The hot-year analysis now covers all three fold seeds, both hot thresholds and
both weightings, with a full confusion table and paired group-clustered
intervals. At 20 °C on the external panel, the fitted score's total deviation of
the admitted hot-year share is +0.7 points [−0.3, +1.6]; the unique-station-year
weighting gives +0.9 [0.0, 1.8] and leaves the ordering unchanged. The cost that
a signed bias hides is the refusal column: the fitted score leaves out 24.5 % of
true hot years, the certificate bound 26.2 %, the peak-window rule 33.2 % and the
gap-length rule 59.5 %, against 0 % for reconstructing everything (which instead
misjudges 1.3 % of hot years as cool). The paper reports both columns.

Evidence: `p0_04_hot_year_closure/`, SI Table S24.

## F06 — innovation and the practical threshold

The pre-specified margin was five points against the peak-window rule, not
against the length rule. With the object repaired the margin is met: +8.0, +7.3
and +7.0 points on the external panel, +10.3, +10.1 and +9.7 on development. It
is not met against the certificate bound, which is a strong transparent
alternative and keeps more records on development. The paper therefore claims a
gain over a baseline that ignores support, not over every alternative, and it
names the regime in which even that gain has no decision value. This follows the
pre-declared rule rather than a post-hoc redefinition: the margin was not
lowered, and the arm that beats us is reported.

## F07 — one chain in the text

The manuscript was rewritten rather than amended. Methods describe the aligned
protocol; Results follow the four reasoning steps (phenomenon, reconstructor,
mechanism, decision); the old certificate-screen numbers appear only in the SI as
history. The SI was rewritten to match, with new tables for the repair
attribution, the selector calibration, retention and the hot-year composition.

## F08 — mechanism and causal boundary

The claim "position, not length, governs" is withdrawn. What the crossed design
supports is: the sign of the support effect is the same for every reconstructor,
its size ranges from 0.24 to 0.64 °C at 30 days, and linear interpolation retains
a length effect of 1.16 °C between 90 and 30 days even at full hidden support.
The mechanism is window misalignment (0.28–0.70 °C when the reconstructed window
lands away from the truth), reinforced by residual persistence (median lag-1
autocorrelation 0.84–0.88; higher-autocorrelation cases carry 0.16–0.36 °C more
error under three methods). A competing peak does not order the error and is
reported as a negative control.

## F09 — validation scope

Unchanged and now stated in the abstract's last sentence and in the limitations:
the external panel is already opened, every comparison on it is a cross-fit
within that panel, and no claim of a sealed confirmation is made. The real-
calendar replay is a development-period probe with 418 groups in 14 networks.

## F10 — units, eligibility and the SI

All counts now come from the aligned run: 5,114 complete station-years (146
networks, 457 stations); 40,704 development and 13,017 external designed cases
(53,721 total); 2,422 incomplete real station-years; 418 replay groups. Shares are
reported as fractions, differences in points. The measurement-stratum check that
was open in the first draft of this response is now run: thresholds re-selected
inside the documented-daily-mean subset give a fitted-vs-peak advantage of
8.0/7.3/7.3 points on the external subset and 8.8/8.7/10.4 on development, so the
ranking does not depend on the project-aggregate or undocumented providers
(`p1_measurement_subset/`).

## F11 — FAIR and administration

Each analysis writes a protocol fingerprint (script hash, input hashes, git
head), the figure sources are written next to the figures, and the build refuses
to call the manuscript submission-ready while the author block is a placeholder.
We did not independently re-derive every figure from the raw daily observations
in this round, and we do not claim that we did.

## What remains open

1. **A pristine panel.** None remains for this method. The paper is a cross-fit
   method study with a stated scope, and a sealed confirmation would need new
   data.
2. **The measurement-stratum check.** Re-estimating the aligned advantage inside
   the documented-daily-mean subset is a one-day analysis we flag rather than
   assume.
3. **The author block.** Human gate; names, affiliations, funding and ORCID
   identifiers are not inferred from a version-control alias.
