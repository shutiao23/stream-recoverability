# v14 auxiliary text (Key Points, plain-language summary, abstract)

Round-2 revision (2026-09-04, REVIEW_v14_round2.md). Every benefit figure below
is over the calendar-day climatology default and names it (reporting norm (v),
manuscript §2.7). Threshold statements follow
`results/v14/p4_flip_analysis/mae_crossing_ci.csv`; the withdrawn ~60-d figure
carries no claim status.

## Proposed title

When is reconstructing a missing stream-temperature record worth it? Incremental
benefit over calendar-day climatology fill, its duration structure, and
differential stress testing

## Key Points (four bullets)

1. Scoring a recovery model against the default handling on identical artificial
   gaps shows that reconstruction over calendar-day climatology fill is
   net-beneficial only for short gaps: realized benefit declines monotonically
   with gap duration, and the share of units made worse by reconstruction jumps
   from 0.0–0.4% at ≤ 30 d to 27.4% / 46.8% at 90 d and 83.6% / 95.6% at 180 d.
   The unit-mean benefit crosses zero at 105 d on the first panel (95% CI
   98–114) and 91 d on the second (95% CI 85–95); downstream thermal-regime
   metrics flip earlier (family medians 39–60 d).
2. These intervals bracket the independent m_max = 49-day threshold of Johnson
   et al. (2021) — different stations, methods, and target metrics — which
   falls inside our downstream 39–60-day window and at roughly half the MAE-scale
   crossing.
3. Ranking gaps by model error is the wrong instrument for benefit: the legacy
   loss-based risk curve correlates negatively with realized benefit at 90/180 d
   (−0.19/−0.54), and simply negating it matches the differential curve at
   180 d (0.54 vs 0.56, second panel) but ranks realized benefit with the wrong
   sign at 7–30 d (−0.18/−0.13) and leaves it unranked at 60 d (−0.02). The
   differential benefit curve is the only tested estimator that ranks benefit
   within short-gap strata (placement-level ρ 0.297 / 0.303 / 0.327 at 7/30/60 d,
   second panel) and it beats the strongest station-history baseline in 10 of 12
   paired cells, including all six second-panel cells.
4. Within-duration fixed budgets over the climatology default, benefit ranking
   beats gap-length and risk rankings at every duration — including harm
   avoidance at 180 d, where it selects a least-harmful fifth (−0.64 °C, 63%
   harmful) instead of treating by duration (−1.65 °C, 86%) or by the old risk
   curve (−2.88 °C, 98%).

## Plain-language summary

When a stream-temperature logger fails, the record it would have collected is
missing until the gap is closed. Managers then choose between reconstructing the
gap with a model and falling back on the simplest handling — here, filling each
calendar day with its historical average ("climatology fill"). We asked when
reconstruction actually beats that default, using thousands of artificial gaps
cut into real records from two independent sets of rivers. The answer has a
clean duration structure: for gaps of about a week to a month, reconstruction
over climatology fill improves accuracy by roughly 0.5–1.0 °C on almost every
gap; the advantage shrinks with gap length, disappears between roughly one and
three months, and turns into real damage beyond — at six months, 84–96% of gaps
are made worse by reconstruction, by 0.9–1.5 °C on average. Thermal-regime
summaries (annual means, heat-wave days, seasonal amplitude) are damaged even
earlier, between about 40 and 60 days. These intervals bracket an independent
49-day threshold published by Johnson et al. (2021), and the rule holds across
three structurally different reconstruction models — it is a property of
stream-temperature records, not of one model. Within a gap length, deciding
which gaps are worth treating still needs a ranking tool: ranking gaps by how
hard they are for the model is the wrong instrument, but ranking them by the
model's *benefit over the default* works — most at short gaps, where the simple
rankings fail. Long gaps should not be reconstructed automatically at all, and
when a decision is forced there, the benefit score at least selects the least
harmful gaps.

## Abstract (final ~240 words, two paragraphs)

*Paragraph 1 and paragraph 2 mirror manuscript §Abstract exactly (kept in sync
with `manuscript_v14_skeleton.md`); final trim at submission per WRR length
rules. Text lives in the skeleton — do not edit here without mirroring.*
