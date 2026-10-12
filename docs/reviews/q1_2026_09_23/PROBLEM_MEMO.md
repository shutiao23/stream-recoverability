# Problem memo

Written before the manuscript was restructured, to force the question into a
form that can be wrong. One page per the framework: what the field does, what
contradicts it, why the strongest existing work cannot settle it, what it costs
to leave unsettled, and the problem in one sentence.

## 1. What the field currently does

Every thermal archive is screened before its station-years are used. The
screening rule is, almost universally, a **threshold on record completeness**:

- a minimum fraction of the calendar year present, or
- a maximum length of the longest consecutive gap.

The most cited quantitative guidance for annual stream-temperature metrics
(Johnson et al., 2021) is of the second kind: records missing up to about seven
to nine consecutive weeks still support annual thermal-signal estimation, and
imputation extends the tolerable window to roughly thirteen weeks. Agency
standards use the first kind.

Two assumptions are embedded in this practice and are almost never stated:

- **A1.** The relevant property of an outage is its *size* — how many days, or
  how long the longest run.
- **A2.** One screening rule serves every derived metric: the same completeness
  threshold is applied whether the analyst wants an annual mean, a summer
  maximum, or a count of threshold exceedances.

Both assumptions are what a completeness rule *is*. Neither has been tested
against an alternative on a large panel with known truth.

## 2. The contradiction

A1 and A2 cannot both be right, because the derived metrics do not depend on
the record in the same way.

An annual mean is a sum over days. Removing *k* days removes *k* terms, and it
matters little which. Its error should scale with the count.

A thirty-day summer maximum is an extreme localised in a window. If the outage
misses that window, the statistic is recoverable from the observed days almost
exactly, however long the outage is. If the outage covers it, the statistic
must be inferred, however short the outage is.

Restated as a falsifiable prediction: **at fixed outage length, hiding the
station's climatological peak window should dominate the error of a
warm-season extreme and be nearly irrelevant to the annual mean; at fixed
timing, the day count should dominate the mean and matter much less to the
extreme.**

This is not a subtle effect if it exists. It predicts that a 30-day outage over
the peak is worse than a 200-day outage that misses it — an ordering the
incumbent rule gets exactly backwards.

Johnson et al. already saw the shadow of this. They report that the *timing*
of missing data affected thermal-signal estimates "inconsistently in space and
time". Working across metrics that include the annual mean, phase and
amplitude, a mixture of two opposite regimes is precisely what would look
inconsistent.

## 3. Why the strongest existing work cannot settle it

Not a straw-man list; these are the strongest adjacent efforts and each fails
for a structural reason, not for lack of care.

| work | what it optimises | why it cannot answer this |
|---|---|---|
| Johnson et al. (2021), record-completeness guidance | the tolerable amount of missing data | measures along one axis only, so it cannot compare axes; reports the timing anomaly without a covariate that could explain it |
| Li et al. (2017), space–time gap filling | accuracy of the interpolated series | optimises the interpolant, not the decision of whether the completed year is fit to use |
| Beaufort et al. (2022), effect of filling on heat peaks | the bias filling introduces | quantifies the effect of a fixed treatment; issues no per-case decision and screens nothing |
| the ML stream-temperature literature (57 studies, 2020–2024) | daily prediction skill | rarely propagates to a derived annual metric, and never to an admission decision |
| reject-option regression | error rate at a fixed rejection rate | the rejection rate is the control variable; an analyst needs a tolerance in degrees on the quantity they report |
| agency completeness standards | auditability and uniformity | deliberately metric-agnostic, which is the assumption under test |

The common structural gap: **none of them conditions the screening decision on
what the target statistic actually depends on.** That is a modelling choice
nobody has had reason to question, because the axis was never compared.

## 4. What it costs to leave unsettled

Concretely, not by appeal to importance:

- Computing the annual peak from recorded days alone — the default when a year
  passes a completeness screen — carries a mean absolute error of **1.31 °C**,
  which is **1.23 interannual standard deviations** of the quantity being
  measured. One in four station-years is wrong by more than a degree.
- A screen on the wrong axis retains the wrong years. At the retention implied
  by the published thirteen-week guideline, **9.7%** of retained station-years
  carry a peak error above 0.5 °C; on the right axis at the same retention the
  figure is **2.5%**.
- The errors are not symmetric in consequence. Understating a summer peak by
  more than a degree converts a thermally stressful year into an unremarkable
  one. Under the incumbent rule that happens in **2.0%** of retained years.
- Because the bias is one-directional and correlated with outage season, it
  propagates: the count of years exceeding an ecological threshold is biased by
  **−0.32 years per station** under length screening, against −0.01 on the
  right axis.

Everything above is measured in this study on 5,114 fully observed
station-years, not asserted.

## 5. The problem in one sentence

> In archives of daily stream temperature, screening rules assume the relevant
> property of an outage is its size and that one rule serves every derived
> metric. But a derived metric's error depends on whichever feature of the
> record it is a function of, so for a warm-season extreme the governing
> property should be whether the outage hid the peak window rather than how
> long it was. We therefore ask which outage property governs which thermal
> metric, whether the answer is predictable in advance from the form of the
> metric, and what an archive gains by screening on the governing property
> instead of on record length.

## 6. What would show the problem is not real

Declared before the experiments, so the study could fail:

- If peak-window overlap and outage length discriminate consequential error
  about equally for the summer extreme, there is no dichotomy and no paper.
- If the ordering flips with the tolerance, the effect is an artefact of where
  the line is drawn.
- If the ordering is the same for the annual mean as for the extreme, the
  mechanism is wrong even if a screen still helps.
- If a screen on the better axis does not transfer to networks and agencies
  never used for fitting, the finding is local and not guidance.
- If the advantage disappears once the reference series is perturbed by
  instrument-scale noise, the effect is inside the measurement error.

All five were run. The third is the one that could most cleanly have killed the
paper, and it is the one that produced the reversal the title now carries.
