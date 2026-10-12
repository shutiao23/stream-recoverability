# Referee report — SCI Q1 water-resources journal

**Manuscript:** *Screening gap-affected stream-temperature records: outage
timing governs warm-season extremes, outage length governs the annual mean*
(`paper_archived/v17/manuscript.md`).

**Reviewer framing.** I have read this as an editor's second reviewer for a Q1
water-resources journal (WRR / HESS / Journal of Hydrology class). I judged it
against one chain and nothing else:

> real problem → sharp contradiction → falsifiable hypothesis → design
> principle → minimum necessary mechanism → fair experiment → bounded
> conclusion

I did not assess code quality. I assessed whether the design is complete,
whether the experiments can discriminate between the hypotheses the paper
raises, and whether the conclusions are the size the evidence supports.

**Recommendation: Major revision.** The scientific core is sound and, in
places, better than most of what I referee — the problem is real, the
contradiction is sharp, the key hypothesis is falsifiable and was actually
falsified in one half, the pre-registration is genuine, and the boundary
reporting is exemplary. But as submitted this is **not yet a water-resources
paper**. It is a well-executed applied-statistics study that happens to use
stream temperature as its substrate, and it is written as a laboratory
notebook rather than as a scientific argument. Three of my six major comments
are about missing hydrology; two are about structure; one is about a
measurement assumption that is currently invisible.

---

## Assessment against the chain

| link | verdict | note |
|---|---|---|
| real problem | **strong** | archives are screened by fixed completeness rules; the cost is quantified (1.31 °C, 1.23 interannual SD) before any method is proposed |
| sharp contradiction | **strong** | published guidance screens on gap length; the paper shows length is the weaker axis for the endpoint the guidance is most used for |
| falsifiable hypothesis | **strong** | the extreme-versus-average dichotomy makes a directional prediction and it reverses on two of four endpoints, as predicted |
| design principle | **adequate** | "condition the screen on what the estimand actually depends on" is stated and followed |
| minimum necessary mechanism | **strong** | the ablations are unusually honest: 59% of the benefit comes from three variables, and the paper says so |
| fair experiment | **strong with one gap** | incumbent armed with an oracle reconstruction still loses; but the truth is treated as exact (comment 4) |
| bounded conclusion | **strong** | four claims are reported as failed; the empirical-arm null is not hidden |
| **hydrological content** | **weak** | see comments 1–3 |
| **scientific writing** | **weak** | see comments 5–6 |

---

## Major comment 1 — Where is the hydrology? The paper explains its own
mechanism statistically and never physically

This is my principal objection and the one most likely to decide the paper's
fate at this journal.

The paper's mechanism, as stated in §3.2, is a *property of estimators and
estimands*: an average is a sum over days so it depends on how many days are
missing; an extreme lives in a window so it depends on whether the window
survived. That argument is correct, it is well evidenced by the gradient
ratios, and it would be equally true of rainfall, of air quality, or of
electricity demand. Nothing in it is about rivers.

The same is true of the second mechanism. Section 3.2 shows that donor
*quality* rather than donor count drives the residual error, and that
phase-shuffling donor anomalies costs 0.234 °C — an elegant control. But
"donor synchrony" is a correlation coefficient. A water-resources reader will
immediately ask the physical question the paper never asks: **why is synchrony
high at some sites and low at others?** Candidate answers are standard in this
literature — groundwater contribution, upstream regulation, catchment area and
thermal capacity, elevation and lapse-rate differences, riparian shading,
distance between donor and target along the network. The paper has none of
them.

This matters beyond presentation, because it is precisely the question the
guidance the paper is correcting already raised. Johnson et al. (2021) report
that filling can harm groundwater-influenced sites. That is a physical claim
about a class of rivers, it is directly adjacent to this paper's subject, the
paper cites it, and the paper does not test it. A reviewer who notices that
will conclude the authors avoided the one hydrological hypothesis in their own
introduction.

I checked whether the test is feasible before writing this, because it is
unfair to demand data an author does not have. The repository already contains
the GAGES-II basin characteristics archive, and **140 of the 204 eligible
United States stations match a GAGES-II identifier**, carrying baseflow index
(`BFI_AVE`), mean basin elevation, drainage area, slope, and dam storage and
density variables. That is a sufficient panel for a stratified analysis. I
would require:

1. donor synchrony regressed on baseflow index, drainage area, elevation
   difference and regulation, with the sign of each effect stated in advance;
2. the completed-year error and the screening benefit reported by baseflow-index
   stratum, so the reader learns whether groundwater-influenced sites are
   harder, as the literature asserts;
3. an explicit test of the Johnson et al. claim — are groundwater-influenced
   sites the ones where reconstruction hurts? — reported whichever way it comes
   out.

If the answer is that basin attributes explain little, that is publishable and
useful: it would say the screening problem is governed by outage geometry and
network configuration rather than by catchment physics, which is itself a
hydrological finding. What is not acceptable is not asking.

## Major comment 2 — The ecological threshold is asserted, and it carries the
paper's most quotable result

Section 3.8 rests its headline downstream claim on the count of years exceeding
20 °C. Twenty degrees appears without a species, a standard, a jurisdiction or
a citation. In a water-resources journal that is a soft target: thermal
criteria for salmonids, cyprinids and macroinvertebrates differ by several
degrees, many jurisdictions regulate on a seven-day average of daily maxima
rather than a thirty-day mean, and a reader in one region will simply not
recognise the number.

The paper's own framework supplies the fix. The authors already anchor
tolerances to the interannual standard deviation; they should anchor the
threshold to something equally defensible and then **show the result is not an
artefact of the choice** by sweeping it. I would require the exceedance
analysis repeated across a range of thresholds spanning the published
cold-water and cool-water criteria, with the sensitivity reported, and one
paragraph justifying the primary choice against a named standard.

While the threshold is being swept, the metric definition deserves the same
treatment. The paper's endpoint is the hottest consecutive thirty-day mean.
Much regulatory practice uses a seven-day rolling mean of daily maxima. The
authors should state why the thirty-day mean was chosen and, at minimum,
confirm that the axis dichotomy survives a shorter window, since a seven-day
extreme is even more localised in time and the mechanism predicts the timing
effect should be *stronger*. That is a prediction the paper can test cheaply
and it would strengthen the mechanism claim considerably.

## Major comment 3 — The truth is treated as exact, and it is not

Every error in this paper is measured against an observed series treated as
ground truth. In-situ water-temperature loggers carry accuracy of roughly 0.1
to 0.2 °C, with drift, and the paper's own earlier programme cited exactly
those figures to justify a different margin. The consequence is that a
"consequential error" of 0.5 °C is about three times sensor accuracy, which is
probably comfortable — but the paper never says so, and never checks.

Two things are needed. First, a sentence establishing that the primary
tolerance is safely above instrument accuracy. Second, a perturbation
analysis: add plausible measurement noise to the reference series, recompute
the endpoint, and confirm the axis dichotomy and the screening contrast are
unchanged. If the ranking of axes is sensitive to 0.15 °C of noise on the
truth, the reader must know.

## Major comment 4 — The statistical presentation of the central comparison is
weaker than the rest of the paper

The dichotomy in §3.2 is established with four AUCs per endpoint reported as
point estimates with no uncertainty, and it is those bare numbers that justify
the title. Elsewhere the paper is scrupulous about network-clustered intervals;
here it is not. I would require clustered intervals on the AUC differences, at
least for the peak and the annual mean, so that "0.819 versus 0.750" and "0.672
versus 0.845" are shown to be separations rather than orderings.

Related: the paper compares four endpoints at three tolerances and reports the
winner in each of twelve cells, without acknowledging multiplicity. In this
instance I am not worried about the inference — the effects are large and the
direction was predicted in advance, which is the right defence — but the paper
must say that, rather than leave a reviewer to wonder whether twelve tests were
run and the favourable ones reported.

## Major comment 5 — The manuscript is written as a project record, not as a
scientific argument

This is not a stylistic complaint. In its current form the paper cannot be sent
to a journal.

The opening states that it is a "Draft of 2026-09-23, revised after three
adversarial reviews". Section 3.4 reports "a defect in our own freeze, which we
record rather than repair". Section 5 is titled "Carried forward from the
earlier programme" and describes results from a previous version of the
authors' own pipeline. Section 2.5 refers to "a first implementation" whose
artifacts "have been discarded". Section 2.1 contains a paragraph of
bookkeeping about why one quantity has two values.

I understand why all of this is there, and the instinct behind it —
transparency — is the right one. But a journal article is not a changelog. Every
one of these belongs in a supplement, a data-availability statement or a
version-control history. What a reader needs from §5 is not "what we carried
forward" but "what is known about reconstruction error that constrains our
estimator choice", stated as knowledge rather than as provenance.

## Major comment 6 — The scientific skeleton a reader expects is missing

Concretely, the following are absent and each is standard:

**No Introduction in the conventional sense.** Section 1 is four paragraphs
and never states a contribution list, never points at a figure, and never
articulates the core insight in one sentence. A reader finishes §1 without
knowing what the paper will claim.

**No Related Work.** Four sentences inside §1 mention four papers. For a
journal whose readers work on stream temperature, this is disqualifying. What
is needed is a problem map: what does each body of work optimise, on what
budget, at what decision granularity, and on which axis — and where this paper
sits in that space. Gap-filling methods, thermal-regime metrics, record
completeness guidance, uncertainty quantification for derived statistics, and
the machine-learning stream-temperature literature are five distinct
conversations and the paper is intervening in exactly one of them.

**No problem formalisation.** There is no notation, no loss function, no
statement of what a screening rule *is* as a mathematical object, no statement
of the decision problem. The paper's own contribution — that the screen should
condition on what the estimand depends on — is a formal claim and deserves a
formal statement.

**No research questions.** The results run 3.1 to 3.10 organised by topic. The
reader cannot tell which subsection answers which question, and several
subsections answer questions never posed.

**No Discussion and no Conclusion.** Section 4 is a list of what is and is not
established — valuable, and it should be kept as a limitations subsection — but
there is no section that interprets the findings for practice, states what an
agency should change on Monday, or says what this implies for the design of
monitoring networks.

---

## Scores

| dimension | score | justification |
|---|---:|---|
| significance of the problem | 8/10 | record screening governs what enters every thermal archive, and the cost of getting it wrong is quantified |
| novelty of the insight | 8/10 | the endpoint-dependent axis dichotomy is new, mechanistic, predicted in advance, and resolves rather than contradicts the standing guidance |
| novelty of the method | 5/10 | correctly self-assessed; the ablations show the axis carries 59% of the benefit and the machinery the rest |
| experimental design | 8/10 | problem existence, mechanism, main result, ablation, oracle, boundary, robustness and cost are all present and separated |
| fairness of comparison | 9/10 | the incumbent is given an undeployable oracle reconstruction and still loses; this is rarer than it should be |
| statistical rigour | 7/10 | clustered inference throughout except on the AUCs that carry the title; multiplicity unacknowledged |
| **hydrological content** | **4/10** | the mechanisms are statistical; basin physics is available in the repository and unused |
| **manuscript structure** | **3/10** | no related work, no formalisation, no RQs, no discussion; meta-narrative throughout |
| reproducibility | 9/10 | not the limiting factor |
| **overall** | **major revision** | the science is close; the paper is not |

**On end-to-end closure specifically.** The loop is closed on the statistical
question and open on the hydrological one. A reader learns which axis to screen
on and why in estimator terms; they do not learn which *rivers* are hard, and
that is the question this journal's readers will ask first.

---

## What I require for the next round

1. A hydrological attribution study using the basin characteristics already in
   the repository, including an explicit test of the groundwater claim the
   paper cites (comment 1).
2. A threshold sweep and a named justification for the primary ecological
   threshold, plus confirmation that the dichotomy survives a seven-day
   extreme (comment 2).
3. A measurement-noise perturbation of the reference series (comment 3).
4. Clustered intervals on the AUC contrasts that carry the title, and one
   sentence on multiplicity (comment 4).
5. Removal of all project-history narrative from the article; relocation of
   provenance to a supplement (comment 5).
6. A conventional scientific structure: introduction with a stated insight and
   contributions, related work as a problem map, formal problem statement,
   results organised by research question, discussion and conclusion
   (comment 6).

Items 1 to 4 are experiments. Items 5 and 6 are rewriting. None requires data
the authors do not already hold.
