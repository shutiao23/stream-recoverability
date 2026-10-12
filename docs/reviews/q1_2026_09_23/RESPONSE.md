# Response to the referee

Each requirement, what was done, and where the result is. Four of the six are
new experiments; two are rewriting. All numbers are re-derived from artifacts
by an automated audit that runs in the test suite.

---

## Requirement 1 — A hydrological attribution study, including an explicit test
of the groundwater claim

**Done, and the referee's expected answer did not hold.** New §5.3, new
Figure 6, `scripts/201_v17_hydrology.py`, `results/v17_fitness/step21_hydrology/`.

140 of 204 eligible United States stations across 57 networks were joined to
GAGES-II. Expected signs were declared in code before any regression was run.

- **Topography predicts difficulty, and it is the strongest signal we find.**
  Site elevation and basin slope both reduce donor synchrony (ρ = −0.29, CI
  −0.46 to −0.08; ρ = −0.31, −0.51 to −0.07) and elevation raises both
  completed-year error (ρ = +0.24, 0.06 to 0.43) and the consequential-error
  rate (ρ = +0.25, 0.08 to 0.43). Mountain stations are harder because their
  neighbours are less exchangeable.
- **The groundwater prediction is rejected in the direction stated.** Johnson
  et al. imply high baseflow index → larger error. Observed: high-baseflow
  stations are **0.043 °C easier** (CI −0.081 to −0.004).
- **The reason is a decomposition, not a contradiction.** Baseflow reduces
  donor synchrony as predicted (0.70 → 0.59 across tertiles) *and* damps the
  target: the mean annual peak falls 22.7 → 18.1 °C (ρ = −0.47, −0.60 to −0.26)
  and its interannual SD 0.98 → 0.76 °C. Groundwater degrades the information
  available while reducing the difficulty of what is being estimated, and the
  second effect is larger.
- **Regulation does not make years harder** (+0.004 °C, CI −0.051 to +0.093).
- **Catchment attributes explain a modest share** (R² = 0.22 for synchrony,
  0.13 for error) and **no attribute predicts the screening benefit** — every
  interval contains zero. We therefore report them as explanation and
  deliberately exclude them from the rule, which must run at nine agencies.

The referee's closing observation was right: the negative half is publishable.
The screening problem is governed mainly by outage geometry rather than
catchment physics, and that is now stated as a finding.

## Requirement 2 — Threshold sweep, a named justification, and the seven-day
window

**Done.** New material in §5.9 and §5.2, Figure 5c, `scripts/202_v17_robustness.py`.

- The exceedance threshold is swept from 14 °C to 24 °C. The screen's
  misclassification stays between **0.18% and 0.37%**; the length rule between
  0.84% and 1.53%. The result is not an artefact of 20 °C.
- The **seven-day peak** was added as a full endpoint. The mechanism predicted
  in advance that a shorter extreme, being more localised in time, should show
  a *stronger* timing effect. It does: +0.072 (0.063, 0.096) against +0.070
  (0.061, 0.098) for the thirty-day peak — the largest contrast of any
  endpoint. This is a successful prediction rather than an additional check.
- Both windows are reported side by side in Table 1 so a reader on either
  regulatory convention can find their case.

## Requirement 3 — Measurement-noise perturbation of the reference

**Done.** New §5.10, Figure 5b, `step22_robustness/noise_sensitivity.json`.

The reference series is perturbed by 0.15 °C of normal noise, the upper end of
logger accuracy, and the endpoint and every estimator error recomputed against
the perturbed reference. The development contrast moves from 6.32 to 6.21
points, the reserved contrast from 7.06 to 6.67, and the mean absolute error
from 0.2416 to 0.2418 °C. §4.3 now also states that the primary tolerance is
about three times sensor accuracy rather than leaving it implicit.

## Requirement 4 — Clustered intervals on the AUC contrasts, and multiplicity

**Done.** Table 1 now carries a network-clustered bootstrap interval on
AUC(timing) − AUC(length) for every endpoint. **All five exclude zero**, from
+0.072 for the seven-day peak to −0.184 for the cold extreme, so the reversal
is a separation rather than an ordering. §4.8 states the multiplicity position
explicitly: the direction of each contrast was predicted in advance from the
form of the statistic, making the comparisons confirmatory of a stated
prediction rather than a search over twelve cells.

## Requirement 5 — Remove project history from the article

**Done.** The article no longer contains the draft-history header, the
"carried forward from the earlier programme" section, the note about a defect
in our own freeze, the description of a discarded first implementation, or the
bookkeeping paragraph about one quantity having two values. A grep for that
material returns nothing.

All of it is preserved in `paper_archived/v17/SUPPLEMENT.md`: data sources, the
definition of a network and the QC rules, the two incomplete aspects of the
pre-registration, the two runs that were discarded and why, the verification
regime, and the reproduction path.

## Requirement 6 — A conventional scientific structure

**Done.** The article was rewritten end to end.

| section | what it now contains |
|---|---|
| Abstract | scenario, current practice and its assumption, what is wrong, the insight, what we did, evidence with its boundary |
| 1 Introduction | setting, paradigm and embedded assumptions, the contradiction, why existing work cannot settle it, the insight in one sentence, what we do, four contributions at four levels |
| 2 Related work | a problem map: six bodies of work by what they optimise, decision unit, conditioning axis, and whether they report uncertainty on the derived statistic — with this paper's row |
| 3 Problem formulation | notation, the derived statistic, the outage mask, the loss, a screening rule as a formal object, the retention–error frontier, and H1 stated so both halves can fail |
| 4 Data and study design | records and QC, split, endpoints and their natural scale, outage design, estimators, the rule, the action-space gate, inference |
| 5 Results | organised as RQ0 to RQ8, each subsection answering one stated question |
| 6 Discussion | what an agency should change, why the standing guidance saw an inconsistency, implications for monitoring design, uncertainty for derived statistics |
| 7 Limitations | seven named, each with the evidence that bounds it |
| 8 Conclusion | the finding and the recommendation to practice |

---

## Also changed, prompted by the review

- **The title** now states the dichotomy rather than one half of it.
- **Five supporting documents** were written to the framework the review
  applied: a problem memo, a claim–evidence matrix, a design rationale table,
  an experiment registry, and a machine-generated evidence ledger mapping each
  claim to its script, artifact and digest.
- **The audit was extended** from 101 to **141 checks**, now covering every
  table cell and 27 inline claims. It caught four errors while this revision
  was being written: three AUC values in Table 1 quoted without a source, a
  confirmation interval carried over from a superseded run, and a noise
  comparison that mixed two baselines. All are corrected.

## Claims that do not stand, and are reported as such

| claim | status |
|---|---|
| groundwater-influenced sites are harder | **rejected**; the opposite, with a mechanism |
| regulation makes station-years harder | **not supported** |
| catchment attributes should enter the screen | **not claimed**; none predicts the benefit |
| the absolute advantage is regime-independent | **rejected**; the reserved empirical arm's interval includes zero |
| the interval is valid at a single new site under pooled calibration | **rejected**; cluster calibration is required and costs width |
| screening is the best use of the calibrated object for a threshold call | **rejected**; abstention keeps 93% of years at the same error rate |
| screening improves decadal trend estimation | **weak**; reconstructing at all dominates |
