# Referee report — Water Resources Research

**Manuscript:** *Conditional reconstruction of stream temperature: using historical
observations to decide when reconstruction improves a completed stream-temperature
record* (`paper_archived/v16/manuscript.md`, claim matrix `paper_archived/v16/claims_v16.md`).

**Review round:** second independent adversarial read, 2026-09-23.
**Basis:** the manuscript, the claim matrix, `results/wrr_revision/step1`–`step10`,
`SUCCESS_CRITERION.json`, and my own recomputation from the authors' archived
CSV artifacts. I refit nothing and changed no original result. Every number I
quote below that is not in the manuscript was recomputed by me from the authors'
own tables and is reproducible from them.

**Recommendation: Reject.** Resubmission as a new manuscript is encouraged, but
this specific study cannot be repaired by revision.

---

## 0. Summary of the recommendation

I want to be clear at the outset that my recommendation has nothing to do with
the quality of the execution. The provenance discipline in this project is
better than that of most manuscripts I referee. The authors freeze success
criteria in advance, keep a claim matrix, mark which panels have been opened,
refuse to relabel development data as confirmation, and — most unusually —
report their own null result and withdraw their own earlier claims. That is
genuinely admirable, and I would like the authors to hear that before they read
the rest of this report.

The problem is upstream of all of it. **The central experiment of this paper was
designed around a decision that cannot matter, and no amount of additional
experimentation inside that design will change the outcome.** I demonstrate this
below with the authors' own numbers: the total benefit available to *any*
decision rule in the action space they defined — including a rule with perfect
foresight — is between +0.02 and +0.07 °C on the primary endpoint. The authors'
own pre-registered non-inferiority margin is 0.05 °C, and the measurement
precision they cite to justify that margin is 0.1–0.2 °C. The entire prize is
smaller than the ruler. The ten-step program that follows was therefore a very
careful, very honest search for a signal that the design had already made
impossible to find.

The manuscript's current positive contribution — the training-mismatch diagnosis
in §3.1 — is correct, is well supported, and should survive. But it is a
correction of an error in the authors' own earlier pipeline. That is a technical
note or a short comment; it is not a WRR paper. WRR evaluates on significance
and broad implications, and "our previous trainer leaked an interpolated target
boundary, and when we stopped doing that the failure went away" does not meet
that bar on its own, however useful it is to the authors.

So the recommendation is Reject. But I think the authors are perhaps two or
three months of work away from a genuinely strong WRR paper, because the assets
they have built — 284 networks across nine agencies and nine countries, 5,307
river station-years with fully observed calendar-year truth, a working replay
harness, and an unusually clean provenance ledger — are exactly what that paper
needs. They have been pointing this apparatus at the wrong question. Section 6
of this report says what I think the right question is, and Section 7 says how
I would prove it.

---

## 1. Major comment 1 — the decision problem has no headroom, and this is
provable from the authors' own artifacts before any model is fit

This is my principal objection and it subsumes most of the others.

The manuscript's estimand is the incremental benefit `B_q` of a policy over a
day-of-year climatology default, measured as the absolute error of the hottest
consecutive 30-day mean on a completed calendar year. The action space is
binary: adopt a supported reconstruction, or keep the default. The paper's
thesis is that a historically calibrated rule can choose between these two
actions better than a simple always-reconstruct policy.

I recomputed the ceiling on that thesis. From `step2_fair_recovery/
placement_scores.csv` (303,426 rows, 33,714 matched placements × 9 recoverers),
restricting to the deployable simple set {donor-only ridge, long-block XGB
without boundary, linear interpolation, smooth climatology, DOY climatology}
and taking, for each placement, the best possible action with perfect hindsight:

| action space | mean hottest-30 benefit (°C) | headroom over best fixed method |
|---|---:|---:|
| best fixed method (donor-only ridge) | +0.2301 | — |
| oracle choosing the best *method* per case | +0.2796 | **+0.0495** |
| oracle choosing adopt/reject of the best fixed method | +0.2495 | **+0.0194** |

The same computation on daily MAE gives +0.0934 and +0.0232 respectively. At the
station-year level, in the authors' own `step2_simple_headroom/REPORT.md`, the
oracle-minus-donor headroom is +0.033 °C on development and +0.074 °C on the
846-case retrospective subset; in `step10_unseen_confirmation/REPORT.md` the
oracle is +0.227 against always-donor-only at +0.175, i.e. +0.052 °C.

Every one of these numbers is at or below the pre-registered non-inferiority
margin ε = 0.05 °C, and all of them are below the 0.1–0.2 °C in-situ probe
accuracy the authors cite in `SUCCESS_CRITERION.json` to justify that margin.
Even at 365-day outages, where the authors' own duration table shows the largest
effects, the per-placement method-selection headroom is only +0.150 °C.

I want to state the implication plainly, because it is the most important
sentence in this report. **A decision layer over this action space could not have
succeeded even if it were perfect.** The ten-step program did not fail to find a
good decision rule; it correctly discovered that the best conceivable decision
rule in this action space is worth about three hundredths of a degree. The
authors' conclusion — "adopt/reject is not the source of gain once the recoverer
no longer collapses" (§3.2) — is right, but they treat it as a finding about
their rule when it is a finding about their problem formulation.

A referee is entitled to ask why this ceiling was never computed. The oracle in
`step2_simple_headroom` is defined as `max(gated donor-only benefit, 0)` — that
is, an oracle over adopt/reject only. An oracle over the *method set* was never
reported, and neither oracle was ever compared against the pre-registered ε
before the confirmation experiment was run. Had that comparison been made at
Step 3, the program would have stopped and been redesigned, saving Steps 4
through 10. I would ask any resubmission to make "compute the ceiling of the
action space, and compare it to the declared margin" a mandatory gate before
any decision experiment is run.

## 2. Major comment 2 — the pre-registered success criterion is internally
inconsistent, so the confirmation test could only fail

Section 3.5 reports that the frozen thermal overlay achieved +0.060 °C against
always-simple at +0.146 °C, a shortfall of 0.086 °C, "outside ε = 0.05", and
therefore fails. The authors accept this as a scientific verdict. It is not one;
it is an arithmetic consequence of how the criterion was written.

Consider the structure. A rejecting rule that declines to reconstruct a fraction
*p* of station-years forfeits, in expectation, approximately *p* × (mean benefit
of reconstruction) — because on rejected years the policy returns exactly the
default and `B_q` is exactly zero. On the unseen panel the mean benefit is
+0.175 °C for always-donor-only. Therefore any rejecting rule with rejection
rate *p* loses roughly 0.175 *p* °C of mean benefit, and the constraint "lose no
more than ε = 0.05 °C" is equivalent to "reject no more than about 29% of
station-years". The frozen overlay rejected 84% (adoption 0.16). It was
mechanically impossible for it to pass.

This is not a subtle point about statistics; it is a design contradiction
written into `SUCCESS_CRITERION.json`. The document declares the primary claim
to be *risk control*, whose entire purpose is to buy safety by declining cases,
and then imposes a mean-benefit constraint so tight that essentially no
declining is affordable. The two halves of the criterion are incompatible for
any rule that actually rejects. A risk-control claim must be evaluated on a
*frontier* — harm or tail error as a function of retention — not by a scalar
mean test with a margin drawn from probe precision. Probe precision is the wrong
scale to import here: it tells you how well you can read a thermometer, not how
much mean benefit a screening rule may responsibly trade for a reduction in
severe error.

I would also note that the criterion's own risk-control conditions were partly
satisfied — harm fell from 0.38 to 0.06 on the unseen panel — and were discarded
because the mean test failed first. A frontier analysis would have reported that
the overlay converts 0.086 °C of mean benefit into a sixfold reduction in harm
rate, and then asked whether that exchange rate is better than what a length
rule or random rejection achieves. That is a scientific question. The scalar
test asked a different and less interesting one.

## 3. Major comment 3 — development and confirmation panels differ in the one
covariate that drives the entire result, so the null is uninformative

I recomputed the covariate distributions of the two panels from the authors'
`year_policies.csv` files.

| panel | eval station-years | networks | share with any donor | mean donor count | mean donor correlation |
|---|---:|---:|---:|---:|---:|
| development (`step5_thermal_decision`) | 918 | 42 | 0.907 | 5.85 | 0.749 |
| unseen confirmation (`step10`) | 82 | 36 | 0.585 | **0.59** | 0.728 |

The rule being confirmed is, in the authors' own words, a policy whose first
branch is "donor-only whenever synchronous donors are observed". It was
developed on a panel where stations have on average almost six synchronous
donors, and confirmed on a panel where they have on average one half of one
donor. The Step-1 roster makes the same point independently: the
`candidate_unseen` pool has median `n_donors_full_year` of 0 and a 75th
percentile of 1, against a development median of 3 and 75th percentile of 7.

These are not two samples from one population. They are two different
information regimes, and the design under test is a function of exactly that
information. The drop in achievable benefit from +0.33 °C to +0.175 °C between
the panels is very largely a covariate-shift effect, not a generalization
failure of the rule, and the manuscript does not separate the two. When a
confirmation panel differs from the development panel on the design's primary
conditioning variable by an order of magnitude, a null result carries almost no
evidential weight against the design. The honest reading of Step 10 is not "the
overlay does not generalize"; it is "the reserved pool could not test the
overlay". The paper currently reports the former.

The remedy is not to discard the unseen pool — it is a legitimate and valuable
*donor-poor* stratum. The remedy is to declare information regime as a
stratification variable up front, to reserve confirmation networks *within* each
regime, and to report results by regime. A design whose value is conditional on
donor availability should be confirmed on panels that contain both conditions in
known proportions.

## 4. Major comment 4 — the confirmation experiment had no power against its own
margin, and the manuscript does not report a precision calculation

From the development table I computed the network-level paired difference
between the overlay and always-simple: mean −0.0354 °C with a between-network
standard deviation of 0.0955 °C across 42 networks. On that variance, resolving
a 0.05 °C margin at 95% confidence needs roughly 14 networks *with development-
like precision per network* — but precision per network is not a constant. The
development panel contributes 918 station-years across 42 networks (21.9 per
network); the unseen panel contributes 82 station-years across 36 networks (2.3
per network). Per-network means on the unseen panel are each estimated from
about two station-years drawn from a distribution whose case-level standard
deviation is 0.79 °C. The resulting network means carry standard errors of order
0.5 °C, an order of magnitude larger than the margin being tested.

The manuscript reports a confidence interval of 0.07–0.31 °C on a point estimate
of +0.175 °C — a width of 0.24 °C, nearly five times ε. No pre-registered
precision or power calculation appears anywhere in `SUCCESS_CRITERION.json` or
the protocol, and none appears in the manuscript. A confirmation test whose
resolution is five times coarser than its decision margin cannot deliver
evidence in either direction: it could not have accepted the design and it
cannot reject it. Reporting its outcome as a scientific verdict — and rewriting
the paper's contribution around that verdict — is the most serious inferential
error in the manuscript.

I recognize the authors were trying to be conservative by reserving an unopened
pool. That instinct is right. But reserving 82 station-years when 5,307 eligible
river station-years exist in the same roster is not conservatism; it is an
underpowered design that spends the study's credibility on a test that cannot
speak. The Step-1 artifact shows 161 eligible networks, 547 stations, and 5,307
complete station-years. The confirmation used 1.5% of them.

## 5. Major comment 5 — the evaluation population is one-third degenerate, and
the mean is the wrong summary of it

From `step5_thermal_decision/year_policies.csv`, on the 918 development
evaluation station-years under `always_simple`:

- 29.2% of cases have |`B_q`| < 0.01 °C, and 35.4% have |`B_q`| < 0.05 °C;
- the median `B_q` is +0.048 °C while the mean is +0.406 °C;
- the distribution is strongly right-skewed with a heavy left tail
  (5th percentile −0.329, 95th percentile +2.038, minimum −3.423, maximum +4.98).

Under `always_donor_only` the degenerate share rises to 36.5%. The reason is
structural and should have been anticipated: the endpoint is a 30-day maximum
over a calendar year, and when an outage falls outside the station's warm
season, the completed and default records return *identically* the observed
peak. The decision is then irrelevant by construction.

This has two consequences. First, a mean computed over a population that is
one-third exactly zero is a poor summary — it is neither the typical case
(median +0.048) nor the consequential case (the tail). It systematically
understates the stakes where the decision matters and manufactures apparent
agreement between policies where nothing is at stake. Second, and more
importantly, it dilutes every statistical comparison in the paper: a third of
the sample contributes zero signal and full degrees of freedom. The tiny
headroom of Section 1 and the absent power of Section 4 are both partly
manufactured by this.

Any resubmission must define the decision-relevant subpopulation explicitly —
outages that overlap the station's climatological peak window — report results
stratified by that variable, and stop averaging consequential and inconsequential
cases into a single number.

## 6. Major comment 6 — the operational scale of the endpoint is never
established, and when I establish it the paper is targeting the wrong quantity

Nowhere does the manuscript say how large a hottest-30 error has to be before
anyone's judgement changes. Without that, +0.33 °C and +0.05 °C are
uninterpretable, and ε = 0.05 °C is a number with no referent.

I computed the natural scale from the authors' own Step-1 roster. Across the 457
stations with at least four fully observed calendar years, the *interannual
standard deviation* of the annual hottest-30 mean is 1.06 °C (median 1.02,
interquartile range 0.72–1.34), and the within-station range across years
averages 3.28 °C. This is the signal that a thermal-regime study is trying to
resolve: whether a given year was unusually hot, whether a trend exists, whether
a threshold was crossed.

Against that yardstick:

- ε = 0.05 °C is 5% of one year's natural variability. It is inaudible. No
  management or ecological judgement turns on it.
- The mean benefit of the best policy, +0.33 °C, is 31% of a standard deviation.
  Real, but modest.
- And here is the number the manuscript never reports: **10.4% of completed
  station-years carry an absolute hottest-30 error greater than 1.0 °C — roughly
  a full interannual standard deviation — and 23.2% exceed 0.5 °C.** Under the
  climatology default these rates are 30.3% and 50.5%.

So the paper has spent ten steps optimizing a mean that is 31% of a standard
deviation, using a decision margin that is 5% of one, while leaving untouched
the one in ten completed years whose error is as large as the entire signal. The
tail is where the science is. A hottest-30 error of 1 °C inserted into a
multi-year record does not shift a mean slightly; it can invent or erase a hot
year, flip a threshold exceedance, and materially bias a trend slope. That is
the quantity a WRR reader cares about, and it is the quantity with room to
improve: the authors' own oracle drives harm to zero, so the achievable range on
the tail endpoint is 100%, against 20% on the mean endpoint.

## 7. Major comment 7 — the state of practice is absent from the baseline set

The manuscript's default action is "insert a day-of-year median climatology".
That is one reasonable default, and the authors are right that rejecting a
reconstruction means adopting it rather than leaving a hole. But it is not what
practitioners do, and the paper therefore never competes with the alternatives
its readers actually use. Two are missing.

First, the **observed-days estimator**: compute the thermal metric from whatever
days were recorded and ignore the gap. This is overwhelmingly the most common
treatment in agency practice and in the ecological literature, and it is the
estimator whose behaviour Johnson et al. (2021) actually characterize. It is not
in the comparison set anywhere in the manuscript.

Second, **fixed gap-length screening**: exclude the station-year from analysis if
the outage exceeds a threshold. Johnson et al. (2021) is precisely such a rule —
records missing up to about seven to nine consecutive weeks still support annual
thermal-signal estimation, and imputation extends the tolerable window to about
thirteen weeks. Agency data-completeness standards work the same way, with
fixed percentage-coverage cut-offs. This is the operational incumbent that any
new screening or adoption proposal must beat, and it appears in the manuscript
only as a literature citation that the authors correctly decline to treat as
numerical validation. It is never run as a baseline on the authors' own data.

The `simple_length_season` policy in the code is not a substitute: it adopts
reconstructions for short summer gaps rather than screening station-years for
fitness of use, and it performs so poorly (+0.013 °C) that it functions as a
straw man rather than as the incumbent.

Without these two baselines the paper cannot answer the question a WRR reviewer
will ask first: *compared to what people do now, what do I gain?*

## 8. Major comment 8 — the deployed decision rule ignores the paper's own best
diagnostic, and the signal it discards is large

Step 4 establishes, convincingly, that donor *quality* governs outcomes: with
partially missing donors, imputing the missing columns in the full ridge costs
−1.56 °C while retraining on the visible subset gains +0.74 °C; with weak donors
the full model is −2.59 °C against +0.26 °C for air ridge. Step 8 adds that high
training-period donor synchrony sustains long-gap benefit at +0.49 °C while low
synchrony gives −0.08 °C.

The deployed policy uses none of this. `information_conditioned_recoverer()`
branches on four booleans — donors observed, right flank present, air present,
gap length ≤ 30 — and never consults donor correlation, even though
`mean_donor_corr` is computed and carried in the year table. The adopt/reject
overlay is a hierarchical mean of *realized year-level benefit* over a
calibration split of 424 station-years spread across 42 networks, i.e. roughly
one to two prior years per station, thresholded at zero. That is not a decision
model; it is a station-level average of two noisy numbers.

I tested how much was being left on the table, using nothing but the authors'
own year table and the features already present in it. Predicting whether a
completed station-year's hottest-30 error exceeds 0.5 °C, with a gradient-
boosted classifier, seven crude features (gap length, mean gap length, gap count,
donor count, mean donor correlation, donor presence, air presence, plus season of
the longest gap), and **grouped five-fold cross-validation clustered by network**
so that no network appears in both folds:

| predictor | AUC for |error| > 0.5 °C | AUC for |error| > 1.0 °C |
|---|---:|---:|
| gradient boosting on 7 visible features | **0.740** | **0.679** |
| gap length alone (the Johnson-type axis) | 0.613 | 0.610 |
| warm-season timing alone | 0.605 | 0.617 |
| donor correlation alone | 0.682 | 0.712 |

Two things follow. First, the decision-time information needed to identify
unreliable station-years exists, generalizes across networks, and is substantially
more informative than the gap-length axis on which the published guidance rests.
Second, the manuscript's deployed rule throws most of it away — donor correlation
alone outperforms the length rule, and the authors compute it and then do not use
it. The concentration is easy to see directly in their table: station-years in
the lowest quartile of donor correlation have a 31.1% harm rate and carry 44% of
all negative benefit mass, while the top quartile has 16.1%; station-years with
no donors at all have mean benefit −0.003 °C and a 57.6% harm rate.

This is the paper that should have been written. The authors discovered the
mechanism in Steps 4 and 8, and then confirmed a rule that does not use it.

## 9. Minor but substantive points

**9.1 Hierarchical benefit means and `diff` are the same estimator.** The
manuscript is right to report the 8.88 × 10⁻¹⁶ identity and right to stop
treating them as two methods. I would go further: this identity should be
removed from the results and stated once in the methods as a definition, because
as presented it invites the reader to think a comparison was made.

**9.2 Right-boundary gating.** The withdrawal of C5 is correct, and the analysis
that produced it — that donor-only regression does not read the right flank, so
hiding it cannot change the prediction — is exactly the right kind of negative
control. Keep it. It is a small, clean methodological contribution.

**9.3 Transplanted outage geometry.** Preserving month and length while ignoring
inter-station co-occurrence, per-year frequency, and the hydrological state at
failure is a reasonable first approximation but should not be described as
realistic failure replay. The co-missing donor experiment (§3.3) is the correct
instinct; it needs to be the main geometry, not a sensitivity.

**9.4 Heat-event definition.** A 90th percentile of the full-record water
temperature identifies warm days, not heat events. It conflates seasonal normal
warmth with anomalous persistent events, which is the distinction that matters
for thermal-regime judgement. Use a seasonally varying threshold with a minimum
duration.

**9.5 Air forcing coverage.** NASA POWER forcing exists for 8 networks and 14
stations in `daily_forcing.parquet`. The air-driven branch of the
information-conditioned policy is therefore supported on a very small fraction
of the panel, and the air2stream-3 result (C8), while correct and worth keeping,
rests on 17 networks. This should be stated as a coverage limitation wherever
the policy is described, since the policy's second branch is essentially
inoperative on most of the corpus.

**9.6 Non-river objects.** The removal of the North Sea, the Wadden Sea, lakes
and canals from the river confirmation average was necessary and is correctly
handled now. I have no further objection here.

**9.7 Provenance.** The claim matrix, the opened-panel ledger and the refusal to
relabel opened data are exemplary and should be retained verbatim in any
resubmission. They are one of the reasons I believe a strong paper is reachable.

---

## 10. Scores

Ten-point scale; 5 means useful but of limited contribution, 8 means a clear
increment with strong evidence. This is my subjective scale, not a WRR
instrument.

| dimension | score | justification |
|---|---:|---|
| importance of the underlying problem (data usability for thermal-regime judgement) | 7/10 | Real, widespread, and under-served; agencies screen records with fixed rules and report no uncertainty on derived metrics |
| importance of the problem *as posed* (adopt vs climatology on mean `B_q`) | 3/10 | A niche framing of the real problem, and the one with the least room to move |
| novelty of the current idea | 3/10 | Reject-option regression applied to a setting where the reject option is nearly worthless; adjacent work already fills gaps and recomputes heat peaks |
| novelty of the current design | 2/10 | Information-presence gating plus a hierarchical mean of one to two prior years thresholded at zero; donor quality computed and then unused |
| strength of the training-mismatch diagnosis | 8/10 | Well controlled, multiple matched counterfactuals, correctly withdraws the earlier law claim — the best thing in the paper |
| strength of evidence that the new design is superior | 1/10 | Not established, and could not have been established: oracle headroom ≤ 0.05 °C against a 0.05 °C margin |
| end-to-end closure of the experimental logic | 2/10 | The pipeline runs to the endpoint, but the loop closes on a null produced by an underpowered, covariate-shifted test of a decision with no headroom |
| execution, provenance, reproducibility | 9/10 | Better than most submissions; not what is holding the paper back |
| **overall recommendation** | **Reject** | Redesign required, not revision |

**On the end-to-end question specifically**, since the authors ask it directly:
no, the experiments do not close a loop that proves the design. They close a
loop that proves the design cannot be proved. The pipeline is complete — panel,
truth, recoverers, replay, ablations, faults, freeze, confirmation — and that is
a real achievement of execution. But a closed loop requires that the endpoint be
capable of registering the design's value, that the test population be
exchangeable with the development population, and that the test have resolution
finer than the declared decision margin. None of the three holds here. What the
authors have built is a rigorous null-result machine.

---

## 11. What I would do instead

I set out the reframing here and the detailed experimental programme in
`PLAN.md` in this directory. In brief.

**Keep the assets, change the question.** The apparatus is right; the question is
wrong. The question with scientific and operational value in this corpus is not
*should I adopt this reconstruction?* — reconstruction almost always helps, as
the authors have now shown three times — but:

> **Given an outage pattern and the information actually available at the
> station, is the completed year's thermal metric fit for use, and with what
> uncertainty?**

This is the question agencies answer today with a fixed rule of thumb — Johnson
et al.'s seven-to-nine weeks unfilled, thirteen weeks filled — and it is the
question their own results say is answerable far better than that. The
deliverable is a per-station-year *certificate*: a calibrated prediction interval
on the completed-year metric, and a fitness-for-use decision at a tolerance the
user names.

**Why this has room where the old question had none.** The old endpoint had
0.02–0.07 °C of oracle headroom on a 1.06 °C natural scale. The new endpoint —
the rate of consequential error among retained station-years — runs from 23.2%
(retain everything) to 0% (oracle), and the incumbent length rule sits at an
AUC of 0.61 while the visible information supports 0.74. The gap between
incumbent and achievable is the size of the contribution, and here it is large
and measurable rather than a rounding error.

**Why it is novel.** Johnson et al. (2021) established that timing of missing
data matters but reported it as inconsistent in space and time; nobody has shown
that the inconsistency resolves once you condition on peak-window overlap and
donor information quality. Beaufort et al. (2022) quantify the effect of filling
on heat peaks but issue no per-case decision. Li et al. (2017) optimize the
interpolant, not the usability judgement. The recent machine-learning stream-
temperature literature — the 2025 HESS review counts 57 studies in 2020–2024 —
optimizes daily prediction skill and almost never propagates to derived annual
metrics or to a screening decision. A calibrated, information-aware,
out-of-sample-validated replacement for a fixed-length data-screening guideline,
demonstrated across nine agencies, is a contribution WRR readers will use.

**Why it closes the loop.** Mechanism (what makes a year unusable) → design (a
screen that uses exactly those variables) → calibration (intervals with
guaranteed coverage) → dominance over the incumbent on a frontier → consequence
(trend slopes and threshold-exceedance counts recovered) → out-of-sample
confirmation on networks and agencies never used for fitting. Each arrow is a
falsifiable experiment, and none of them is a mean difference of 0.05 °C.

Specific requirements for the resubmission, which I would want to see met before
I recommend acceptance:

1. Compute and report the ceiling of every action space *before* testing a rule
   in it, and refuse to run a confirmation whose declared margin exceeds it.
2. Report a precision or power calculation for the confirmation, pre-registered,
   in units of the endpoint.
3. Stratify the reserved confirmation pool on donor regime and agency, so that
   the test population is exchangeable with the development population by
   construction.
4. Include the observed-days estimator and fixed gap-length screening as
   baselines everywhere, since these are the incumbents.
5. Report the frontier, not a scalar: error or harm as a function of retention,
   with the incumbent rule marked as a point on it.
6. Anchor every effect size to the interannual standard deviation of the metric
   at the same stations (1.06 °C in this corpus), and justify every tolerance in
   those units.
7. Demonstrate at least one downstream consequence on a quantity a reader cares
   about — a trend, a threshold count, a ranking of years.
8. Keep the training-mismatch diagnosis, the right-boundary negative control,
   the non-river exclusion, and the provenance ledger. They are good work.
