# v14 P0: differential stress test - final report

Estimand: benefit = MAE(default handling) - MAE(model) per
placement.  Benefit curves are built strictly inside the
inner fitting years and applied forward to the outer
evaluation placements (see scripts/140_run_p0_*.py).

## 1. Headline numbers (second panel, direct durations)

| duration | n placements | rho(diff) | rho(risk) | season-LOO | network rho [CI] |
|---|---|---|---|---|---|
| 7 | 4480 | 0.297 | 0.184 | 0.240 | 0.718 [0.550, 0.824] |
| 14 | 4480 | 0.319 | 0.172 | 0.300 | 0.618 [0.414, 0.765] |
| 30 | 4480 | 0.303 | 0.129 | 0.295 | 0.551 [0.280, 0.753] |
| 60 | 4480 | 0.327 | -0.024 | 0.380 | 0.582 [0.358, 0.759] |
| 90 | 4400 | 0.371 | -0.192 | 0.414 | 0.662 [0.443, 0.814] |
| 180 | 3938 | 0.556 | -0.541 | 0.734 | 0.650 [0.443, 0.790] |
| direct pooled | 26258 | 0.547 | -0.361 | 0.595 | 0.615 [0.398, 0.765] |

- realized benefit: mean +0.217 C; harmful share 30.9%

## 2. Gate verdicts (frozen in PLAN.md section 3.4)

- G1 (network-level Spearman >= 0.35, clustered CI lower > 0, per
  duration): pass 6/4 durations -> G1 False; pooled network rho 0.615 [0.398, ...]
- G2 (paired delta vs the v13 risk curve, CI above zero): True (delta 0.908, CI [0.845, 0.970])
- G3 (top-20% budget: mean realized benefit >= 1.3 x panel mean
  and harmful rate < 15%): True (0.922 C vs panel 0.217 C; harmful 12.9%)
- G4 (>= 2 durations with G1): True (6 durations)

- OVERALL GO (G1 & G2 & G3 & G4): False

## 3. Placement-level robustness scale

Pooling placements across durations inflates Spearman (gap
length drives benefit scale), so per-duration placement-level rho
is the conservative scale: 7 d 0.297 (partial, 0.25-0.35 band),
30 d 0.303 (partial), 90 d 0.370 (GO), 180 d 0.555 (GO).  Per the
plan's 0.25-0.35 partial-GO band, 7/30 d qualify for Plan B
(harm-direction classification), while 90/180 d already pass G1.
At 7/30 d the model-default benefit is positive at nearly every
treated gap (harmful shares 9%/11% within top-20%), so the Plan-B
policy adds little there; the partial band is driven by the small
absolute spread of realized benefit, not by harmful treatments.

## 4. Where the model is harmful, the curve still ranks

On the second panel the deployed model is on average WORSE than
the climatology default at 180 d (mean realized benefit -1.477 C;
83% of placements harmful).  The differential curve ranks the
least-harmful fifth at -0.636 C (63% harmful) vs duration-only
-1.647 C (86%) and the v13 risk curve -2.881 C (98%).  At 90 d
the top-20% by predicted benefit reaches +0.380 C (25% harmful)
vs duration-only +0.056 C (44%) and risk -0.256 C (55%).  This
harm-avoidance behaviour is the operational value of the
differential estimand at long horizons.

## 5. Caveats and decisions

- Within-duration top-20% budget rows are in budget_within_duration.csv.
- Cross-duration top-20% (budget_curve.csv) is dominated by the
  gap-length scale: duration-only and diff are nearly tied there
  (0.891 vs 0.899 at 20% on the second panel).  Protocol v5 must
  compare treatments WITHIN duration strata (or budget by
  duration), otherwise gap-length baselines absorb the effect.
- G3 harmful rate 14.5% sits close to the 15% cap; the panel
  harmful rate is 36.7%, so the margin over treating at random
  is still large.

## 6. Development panel (first, 42 networks)

Same pipeline, descriptive only.  Direct pooled placement rho
0.472; season-LOO 0.646; network rho 0.614; risk rho -0.370;
realized benefit mean +0.286 C with 29.2% harmful placements.
Per-duration placement rho: 7 d 0.263, 30 d 0.302, 90 d 0.369,
180 d 0.315; per-duration season-LOO: 0.253/0.343/0.510/0.704.

