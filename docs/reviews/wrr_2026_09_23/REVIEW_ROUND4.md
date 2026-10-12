# Referee report, fourth round — the current manuscript

**Manuscript:** *Screening gap-affected stream-temperature records: outage
timing governs warm-season extremes, outage length governs the annual mean*
(`paper_archived/v17/`), as it now stands after round 3 and the numbers audit.

**Review round:** fourth adversarial read, 2026-09-23. Rounds 1–3 reviewed the
v16 submission, the first v17 draft, and the round-2 revision. This report
reviews the current text, which nothing has attacked yet. I ran four
experiments rather than raising four objections, because objections that can be
settled with the data in hand should be.

---

## 1. Where this would land at Water Resources Research

**Recommendation: Minor revision.** This is the first round in which I would
not reject. The paper has a real question, a mechanism that makes a falsifiable
prediction, a deployable rule an agency can use next week, a pre-registered
out-of-sample confirmation with a precision calculation behind it, and a
failure list that is longer than most papers' contribution lists. I believe the
result.

What holds it at minor rather than accept is that the paper is still slightly
larger than its evidence in one place and slightly smaller than its evidence in
two others, and that it has chosen the wrong action space for the downstream
use it cares most about. All three are fixable with analyses the authors
already have the machinery for; I ran them below to show they are not
speculative.

I want to state clearly what I think the contribution is, because the authors
have moved it twice and should stop moving it. It is **not** the certificate.
It is the finding that the axis a data-completeness rule should use is
determined by whether the metric is an extreme or an average, that this is
predictable before any fitting, and that the published guidance is on the wrong
axis for exactly one half of that dichotomy. The certificate is the
demonstration that acting on the finding pays. A reader in a state agency will
take the three-variable rule and the dichotomy and never run the code, and that
is a success, not a dilution.

## 2. Novelty and end-to-end closure

**Idea, 8/10.** The question — which outage axis screens which metric — is one
nobody has asked in this literature, it has an answer, the answer is
mechanistic, and it resolves rather than contradicts the observation the
standing guidance reports as unexplained. It is not a 9 because the underlying
move (condition the screening rule on what the estimand actually depends on) is
obvious once stated; the work is in showing it matters and by how much.

**Design, 5/10.** Unchanged from round 3 and correctly so. The ablations in
§3.5 are candid that a three-variable logistic regression captures 59% of the
benefit and a single covariate 57%. The conformal machinery is standard, and
the one genuinely non-obvious piece — calibrating after the selection, because
taking the minimum of several bounds is a winner's curse — is a correction of
the authors' own first attempt rather than a new method. The design is
*appropriate*, which is a different virtue from novel, and the paper no longer
pretends otherwise.

**End-to-end closure, 9/10.** This is now a closed loop in the strict sense:
the mechanism predicts which endpoints should respond to which axis; the
prediction is tested on four endpoints and confirmed including the reversal;
the design uses exactly the variables the mechanism names; the gate proves
before any fitting that the chosen action space has room; the confirmation is
pre-registered with a precision calculation, scored once, and passes under
every weighting; and the failure modes are measured, not asserted. The missing
point is §5 below — the loop closes on a screening decision when the paper's
own downstream section shows a different decision is better for the use it
highlights.

**Evidence, 8/10.** Two attempts to break it failed on the data (an
oracle-armed incumbent, a stricter fitting protocol) and a third (weighting)
was answered completely. I add two more below that also fail to break it.

## 3. The mechanism is now asserted where it could be measured

Section 3.2 says an average is a sum over days so what matters is how many are
missing, while an extreme lives in a window so what matters is whether the
window survived. That is a sharp prediction and the paper states it as prose. I
tested it by binning development cases on both covariates at once and measuring
how the error grows along each axis with the other averaged out:

| endpoint | error ratio, most days missing vs fewest | error ratio, peak window hidden vs untouched |
|---|---:|---:|
| hottest 30-day mean | 3.5× | **9.6×** |
| annual mean | **10.2×** | 1.5× |

The two ratios swap by roughly an order of magnitude in each direction, which
is exactly what the story predicts and is far stronger evidence for it than the
AUC table. Put this in §3.2. A mechanism you can measure should not be left as
an argument.

## 4. The dichotomy is established on four endpoints and confirmed on one

If timing governs the amplitude as well as the peak — and §3.2 says it does —
then a screen on the amplitude should also beat the length rule out of sample.
The paper never checks, which leaves its scope claim resting on an AUC. I
trained the same certificate on amplitude error and scored it on the reserved
networks at the amplitude's own tolerance:

| panel | length rule at 70% retention | certificate | points saved |
|---|---:|---:|---:|
| development | 7.37% | 2.73% | −4.64 |
| reserved | 7.50% | 3.54% | **−3.96** |

It transfers. The authors should report it, because "we found a dichotomy and
confirmed the screen on both members of the timing side" is a materially
stronger claim than what is written, and it costs one table.

## 5. Major comment — the paper picked the wrong action space for its own
headline downstream use

This is the one finding in this round that changes what the paper should
recommend.

Section 3.8 reports that under the certificate, 0 of 938 retained station-years
misses a 20 °C exceedance. I did not believe the zero, so I restricted the
judgement to years where the call is actually close:

| subset | observed days | reconstruct all | length-screened | certificate |
|---|---:|---:|---:|---:|
| all retained | 6.86% | 1.97% | 1.53% | 0.36% |
| truth within 1.0 °C of 20 | 16.84% | 9.50% | 7.26% | **1.92%** |
| truth within 0.5 °C of 20 | 19.10% | 13.12% | 10.24% | **3.38%** |

The zero was an artefact of a mostly easy sample. The certificate's advantage
survives the restriction and is proportionally larger on the hard cases — a 67%
reduction against length screening where the call is within half a degree — but
the honest number is 3.4%, not 0.0%, and the paper must report the restricted
row beside the headline. A referee who spots the zero and computes this himself
will not be charitable about the omission.

The deeper point is the next one. Discarding a station-year is a very blunt
response to uncertainty about one judgement. The natural alternative, which the
certificate is already equipped for and the paper never tries, is to keep every
year and decline only the specific call the interval cannot support — abstain
where the interval straddles 20 °C. On the reserved panel:

| policy | share of years judged | misclassification | missed exceedances |
|---|---:|---:|---:|
| screen at the 0.5 °C tolerance | 67.5% | 0.36% | 0.39% |
| **abstain where the interval straddles 20 °C** | **92.7%** | 0.42% | 0.64% |
| both | 65.7% | **0.08%** | 0.12% |

Keeping 93% of station-years instead of 68% at essentially the same error rate
is not a small difference to an analyst assembling a regional archive, and it
is available from the same object the paper has already built and calibrated.

I do not think this undermines the paper. It sharpens it: **screening is the
right action when you are deciding what enters an archive, and abstention is
the right action when you are making a particular judgement from it.** The
certificate supports both, and the paper currently presents only the first
while using the second's use case — threshold exceedance — as its headline
downstream result. Section 3.8 should present both policies and say which
question each answers.

## 6. Smaller points

**6.1** The paper is now two papers in one binding: a general dichotomy
established on four endpoints in a page and a half, and a screen for one of
them in eight. I would not ask for a split — the second is the evidence that
the first matters — but §3.2 should be given the space its status as the title
claim deserves, and the mechanism table from §3 above is the natural way to
spend it.

**6.2** The certificate selects linear interpolation for a quarter of reserved
cases, against 5.7% for the information rule, and interpolation carries the
lowest error of any choice when selected. The paper reports the share in an
artifact but never draws the conclusion: for short outages with both flanks,
interpolation beats donor regression, and the information-conditioned rule was
under-using it. That is a small, usable finding.

**6.3** Cross-year outages remain excluded and are now correctly stated as a
limit. I accept that for this submission. It is the obvious next study, because
a November-to-February failure damages two annual metrics while hiding neither
warm season, and the dichotomy predicts it should be nearly harmless for both
peaks and costly for both means. That prediction is cheap to test and would be
a strong opening for the follow-up.

## 7. What I would require before acceptance

1. Add the mechanism-gradient table to §3.2 (§3 above).
2. Add the amplitude confirmation to §3.2 or §3.3 (§4 above).
3. Report the near-threshold rows beside the 0-of-938 result, and stop leading
   with the zero (§5 above).
4. Present abstention alongside screening in §3.8, and state which question
   each action space answers (§5 above).
5. One sentence in §3.5 drawing the interpolation conclusion (§6.2).

None of these requires new data and all five are analyses the authors' own
pipeline already supports. With them I would recommend acceptance.
