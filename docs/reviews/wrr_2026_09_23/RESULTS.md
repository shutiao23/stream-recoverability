# Execution record — the v17 programme, built and attacked three times

Companion to `REVIEW.md` (round 1, on the v16 submission), `PLAN.md` (the
redesign it specified), `REVIEW_ROUND2.md` (round 2, on the first v17 draft)
and `REVIEW_ROUND3.md` (round 3, on the revision). All three rounds and all
execution happened on 2026-09-23. This file records what happened, including
the parts that did not go the way the plan expected and the defects each round
found in the previous round's own work.

All numbers come from the run behind the deterministic, order-stable case
table. Numbers produced before those repairs are discarded, not reported
alongside.

## Scale

| | the v16 programme | v17 |
|---|---:|---:|
| eligible networks | 161 (42 used for development) | **146** (110 development) |
| stations | 547 (225 used) | **457** |
| complete station-years | 5,307 (918 dev + 82 unseen scored) | **5,114** |
| scored cases | 11,060 dev + 2,501 | **51,524** |
| endpoints | 1 | **4** |
| reserved confirmation station-years | 82 | **1,069** |
| reserved networks | 36, donor-poor by accident | 36, **stratified on provider × donor regime** |

## The gate, run before anything was fit

| action space | oracle ceiling | 3 × resolvable margin | verdict |
|---|---:|---:|---|
| adopt or reject a fixed reconstruction (the v16 question) | +0.038 °C | 0.136 °C | **fails** |
| choose among reconstruction methods | +0.080 °C | 0.136 °C | **fails** |
| retain or exclude the station-year | 14.9 points | 8.1 points | **passes** |

This reproduces, on a 45× larger and independently constructed case set, the
central finding of round 1: the v16 decision problem had no headroom, and no
rule inside it could have succeeded.

## Claim by claim

| claim | outcome |
|---|---|
| **S0 — timing governs gap-affected records in general** | **withdrawn**: true for warm-season extremes, false for the annual mean and the cold extreme |
| M1 — which axis wins depends on the endpoint | **holds**: peak 0.819/0.820 vs 0.750 for timing/length; annual mean 0.672/0.818 vs **0.845**; cold extreme 0.447 vs **0.803** |
| M2 — that ordering is not a tolerance artefact | **holds**: identical winner at 0.25, 0.47 and 1.0 interannual SD |
| P1 — recorded-days metrics cost more than one interannual SD | **holds**: 1.305 °C = 1.23 SD |
| H1a — peak-window overlap dominates length, at fixed length | **holds**: 30 d over the peak 18.2%; 200 d off the peak 8.7% |
| H1b — length adds nothing once timing is in the model | **holds**: permutation importance −0.004 against 0.194 |
| H1d/H1e — donor quality, and synchronous anomalies | **hold**: +0.082 °C at equal count; +0.234 °C phase-shuffled |
| H2 — the certificate beats fixed-length screening, reserved panel | **holds as pre-registered**: −7.13 points (CI −8.98 to −5.41) |
| H2a — in every donor regime | **holds**: −6.6, −7.2, −6.7 |
| H2b — the absolute advantage is regime-independent | **fails**: −8.7 on the stratified arm, −0.71 (CI includes zero) on the reserved empirical arm |
| H2d — the incumbent was not handicapped | **holds**: beats a length rule armed with a non-deployable oracle reconstruction |
| H2e — not carried by the largest agencies | **holds**: every weighting clears the declared effect; 83% of reserved networks favour it |
| H3 — conformal coverage, marginal and by stratum | **holds**: 0.909; 0.863–0.949 |
| H3b — coverage at an individual new site, pooled calibration | **fails**: minimum 0.778, five of 36 networks below 0.85 |
| H3c — site-level validity is reachable at a stated price | **holds**: 1.5× width, no network below 0.85 |
| H3d — the screen does not depend on the calibration | **holds**: 2.53% at 70% retention under every setting |
| H4a — per-year judgements improve | **holds**: missed 20 °C exceedances 0.23% → 0.00%; count bias −0.32 → +0.06 years |
| H4b — multi-year trends improve | **weak**: reconstructing at all is the dominant step |
| H5 — agency transfer | **holds**: nine of nine providers, all intervals excluding zero |
| H6/H7 — the axis matters more than the model, and the simple rule is deployable | **hold**: three variables give −3.71 of −6.31 points and −5.44 on the reserved panel alone |
| H8 — no dependence on estimators seeing future years | **holds**: −6.35 → −5.92 points |

Five claims did not stand and are in the paper as failures. One of them was
never pre-registered, because the freeze omitted a weighting between the two
outage arms.

## What each round found in the previous round's work

**Round 2, on the first v17 draft.** The case table was seeded from Python's
salted `hash()` and could not be regenerated; a shared summary filename let one
run overwrite another's counts; the methods promised a strictly-prior-years
sensitivity that did not exist; the framing led with the model when the
ablations showed the axis was the contribution; the intervals were described as
conditionally valid when per-network coverage said otherwise; and two
references dangled while a figure caption carried a stale count. Two attacks
failed and strengthened the paper: the incumbent loses even when armed with a
non-deployable oracle reconstruction, and the claim survives the stricter
fitting protocol.

**Round 3, on the revision.** The general claim did not survive a change of
endpoint — on the annual mean, which is what the cited guidance studied, outage
length is the better axis and the timing rule buys nothing. That narrows the
title and, more usefully, explains the "inconsistent in space and time"
observation the paper had been quoting as an open puzzle. A third
reproducibility defect of the same family as the first two: the case table's
row order was nondeterministic, which moved the headline by 0.1 points through
positional tie-break jitter. The open problem round 2 named was closable and
should have been closed rather than named. The point estimate was
case-weighted on an unbalanced panel. Cross-year outages are excluded by
construction and were not stated.

## The verification pass after round 3

The three review rounds each found defects the previous round had missed, so
the revision was checked the same way rather than proofread. Every table cell
in the manuscript, and the inline claims a table check cannot see, are
re-derived from the artifacts by `scripts/199_v17_audit_manuscript.py`, which
the test suite runs.

The 94 table cells were all correct. The prose was not, and the audit found
four errors that three rounds of reading had not:

1. the count of retained station-years in the per-year result was quoted as 946
   against an actual 938;
2. the leave-one-provider-out range was quoted as −12.0 to −1.5 points against
   an actual −11.6 to −1.2;
3. the natural scale of the peak is 1.06 °C over the full roster but 1.08 °C
   inside the development case table, so the cross-metric comparison in §3.2
   uses a tolerance of 0.51 °C where the rest of the paper uses 0.50 °C — a
   discrepancy the text did not acknowledge;
4. the median interval width at zero peak overlap was rounded to 0.05 °C from
   an actual 0.057, and the widest stratum was given as "about 1.9" rather than
   1.87.

A fifth item was not an arithmetic error but a provenance one: §2.5 quoted
exact coverage figures for the superseded additive calibration, whose artifacts
were discarded with the pre-repair run. Those are now described qualitatively.

None of these changes a conclusion. All four would have been found by a referee
with a calculator, and the fact that they survived three careful readings is
the argument for making the check a test.

## Round 4, on the current text

The fourth read is the first that would not reject. It ran four experiments
instead of raising four objections.

1. **The mechanism was asserted where it could be measured.** Error grows 3.5×
   along the missing-days axis and **9.6×** along the peak-overlap axis for the
   annual peak; **10.2×** and 1.5× for the annual mean. The two ratios swap by
   an order of magnitude in each direction, which is what the story predicts.
   Now in §3.2.
2. **The dichotomy was confirmed on one endpoint of the two it claims.** A
   screen trained on the amplitude also beats the length rule out of sample,
   saving 4.0 points on the reserved panel. Now reported.
3. **A perfect 0 of 938 was an easy-sample artefact.** Restricted to years
   within 0.5 °C of the 20 °C threshold, the certificate misclassifies 3.38%
   against 10.24% under length screening — a larger proportional advantage but
   not a zero. The restricted rows now sit beside the headline.
4. **The paper had picked the wrong action space for its own headline
   downstream use.** Abstaining only where the calibrated interval straddles
   the threshold judges **92.7%** of station-years at 0.42% error, against
   screening's 67.5% at 0.36%. Screening is right for deciding what enters an
   archive; abstention is right for making one judgement from it. Both are now
   reported.

The fourth item is the one that changed a recommendation rather than a number.

## Scores

Same subjective ten-point scale as `REVIEW.md`.

| dimension | v16 | v17 draft | after round 2 | after round 3 |
|---|---:|---:|---:|---:|
| importance of the problem as posed | 3/10 | 7/10 | 7/10 | **7/10** |
| novelty of the idea | 3/10 | 7/10 | 7/10 | **8/10** |
| novelty of the design | 2/10 | 6/10 | 5/10 | **5/10** |
| strength of evidence for the design | 1/10 | 7/10 | 8/10 | **8/10** |
| end-to-end closure | 2/10 | 7/10 | 8/10 | **9/10** |
| honesty of reporting | 8/10 | 8/10 | 9/10 | **9/10** |

After round 4: idea **8/10**, design **5/10**, evidence **8/10**, end-to-end
closure **9/10**, honesty **9/10**, and the verdict moves from major revision to
**minor revision** — the first round at which this referee would not reject.

Idea novelty went **up** in round 3 even though the claim got smaller, because
a result that says which axis belongs to which endpoint, and predicts the
reversal before measuring it, is a better contribution than a blanket claim
that happens to be half wrong. Design novelty stays at 5: the ablations are
clear that the model is the smaller half. Closure reaches 9 because the failure
modes are now measured rather than asserted — including the one that reverses
the headline.

Not 10, for reasons that are specific and unlikely to move: the absolute
benefit under realistic outage geometry is small because under realistic outage
geometry most station-years are fine; the certificate needs the station's own
history; and cross-year outages are outside the design.

## Where a referee will still push

1. **"Your outage design chose your answer."** Partly, and §3.4 says so,
   including that the reserved empirical arm's interval includes zero.
2. **"Then why the machine learning?"** For the interval, and for the last 2.6
   of 6.3 points. The paper says this rather than burying it.
3. **"Complete calendar years are your best stations."** True by selection.
4. **"Your outages never cross New Year."** Correct, and now stated.
5. **"Why 0.5 °C?"** It is 0.47 interannual standard deviations, and the
   frontier is reported at 0.25, 0.5 and 1.0.

## Artifacts

Code `src/stream_recoverability/experiments/v17_fitness/`, scripts `180`–`200`,
tests `tests/test_v17_fitness.py` (22 tests, passing, including the manuscript audit over 126 checks), results
`results/v17_fitness/step1_panel` … `step19_weighting`, figures `figures/v17/`,
paper `paper_archived/v17/`. Full rebuild is about fifty minutes on 128 cores and the
case table is byte-reproducible including row order.
