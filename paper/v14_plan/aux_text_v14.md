# v14 auxiliary text (Key Points, plain-language summary, abstract)

Round-2 revision (2026-09-04, REVIEW_v14_round2.md); v15/W3 rewrite (2026-09-05,
WORKPLAN_v15.md Step 3.3): the title names the default as "relative to
climatology fill", the four Key Points each fit the 140-character WRR limit,
and the abstract is 249 words with the mechanism in its first paragraph.
Every benefit figure below is over the calendar-day climatology default and
names it (reporting norm (v), manuscript §2.7). Threshold statements follow
`results/v14/p4_flip_analysis/mae_crossing_ci.csv`; the withdrawn ~60-d figure
carries no claim status.

## Proposed title

When is reconstructing a missing stream-temperature record worth it? Incremental
benefit relative to climatology fill, its duration structure, and differential
stress testing

## Key Points (four bullets, each ≤ 140 characters)

1. Climatology-fill error is nearly flat in gap length while model error grows
   ~10×; reconstruction stops paying where the two curves cross.
2. That crossing is set by each station's own climatological error and is
   pre-computable (398 stations; ρ = +0.41/+0.24).
3. Ranking by model error anti-correlates with benefit at long gaps; ranking by
   benefit works within every duration stratum.
4. At a within-stratum 20% budget, benefit ranking realizes +1.22/+0.84/+0.38 °C
   at 7/30/90 d and turns harm-minimizing at 180 d.

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
rankings fail. Long gaps should not be reconstructed indiscriminately: even
there a small subset of gaps is still worth treating, and the benefit score
selects the least harmful ones.

## Abstract (249 words ≤ WRR 250, two paragraphs; paragraph 1 states the mechanism)

A missing stream-temperature record poses a practical question: not which model
is most accurate, but whether reconstruction beats the default handling the
user would otherwise apply. Realized benefit is the difference of two error
curves with different geometries: the climatology default's error is nearly
flat in gap length — a day-of-year predictor carries no boundary information —
while the model's error grows tenfold from 7 to 365 d. Reconstruction stops
paying where the model's expected error meets the station's own climatological
error: a closed-form crossing, pre-computable from the fitting record and
verified at station level (stations with harder climatological defaults
tolerate longer gaps; Spearman +0.41, 210 stations, p = 6e−10, prospective
panel).

On two outcome-disjoint multi-provider panels, unit-mean benefit over
climatology fill crosses zero at 91 d (95% CI 85–95) and 105 d (98–114);
downstream thermal-regime metrics flip earlier (medians 39–60 d, bracketing
Johnson et al.'s independent 49-d threshold); three structurally different
model families cross the same threshold line. Within a duration, ranking by
model error is the wrong instrument (ρ −0.19/−0.54 at 90/180 d); a
differential stress curve — fitting-period benefit scored by the model it
ranks — ranks benefit positively in every stratum (ρ 0.297–0.556) and is
irreplaceable only in the transition zone, as predicted. At fixed
within-stratum budgets it realizes +1.22/+0.84/+0.38/−0.64 °C at 7/30/90/180
d, selects a least-harmful fifth at 180 d, and captures 20–48% of a perfect
selector's value — still positive at 180 d (+0.38 °C): "do not reconstruct
indiscriminately", not "do not reconstruct".
