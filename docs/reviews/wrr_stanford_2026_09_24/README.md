# Adversarial review of `paper_archived/v17` — WRR framing, 2026-09-24

A third-referee reading of the v17 manuscript, written against the standard a
Q1 water-resources journal applies to the *design* and the *experiments*, not to
the code. Four of the checks in the report were run rather than asserted; the
script that runs them is here.

| file | what it is |
|---|---|
| `REVIEW.md` | the referee report: recommendation, seven major comments, ten minor, scores, and an explicit verdict on end-to-end closure |
| `NOVELTY.md` | novelty scored in four layers, and why the loop closes in simulation but not to practice |
| `PLAN.md` | the v18 work plan: seven experiments with falsifiable predictions and acceptance criteria, plus the rewrite and figure work |
| `probe.py` | the four referee probes, reproducible against the authors' own artifacts |
| `probe_output/` | their output |

## The four probes, and what they found

**P1 — representativeness of the retained archive.** At 70% retention the
calibrated screen's per-station retention correlates with site elevation at
ρ = −0.259 (p = 0.011) on development and ρ = −0.273 (p = 0.077) on the reserved
panel, while the incumbent length rule is elevation-neutral (ρ = −0.053 and
−0.101). By donor regime the screen keeps 57.1% of donor-less station-years
against 72.5% of donor-rich ones on development; the length rule tilts the other
way. The retained development archive's mean annual peak shifts +0.18 °C against
+0.01 °C for the incumbent.

**P2 — is the bias expensive to remove?** Applying the screen at equal retention
within donor regime costs 0.23 points on development (2.93% → 3.17%) and nothing
on the reserved panel (2.53% → 2.52%). It does not fix the elevation tilt
(ρ = −0.235 after balancing), so elevation neutrality needs its own stratum.

**P3 — is missingness informative?** Across 6,472 real interior gaps the mean
anomaly of the seven days preceding a gap is +0.018 °C for 1–7 day gaps
(p = 0.44), +0.038 °C for 8–29 day (p = 0.56), −0.002 °C for 30–89 day (p = 0.98)
and −0.215 °C for 90 day and longer (p = 0.081, n = 150). The transplant design's
exchangeability assumption is empirically defensible except for very long gaps —
which the manuscript should say, with these numbers. Separately, the start month
of long gaps is strongly non-uniform (χ² = 44.3, p = 6.5 × 10⁻⁶): 55.8% of gaps
of 30 days or more begin between September and January and 30.7% between March
and July, which is why the empirical arm is null.

**P4 — deployment on the real archive.** Of the 2,422 genuinely incomplete
station-years, the Johnson unfilled limit admits 83.2% and a peak-window rule at
10% hidden admits 81.2%; the two disagree on **15.1%** of station-years — 207
admitted by the incumbent and rejected on timing, 158 the other way. 28.7% of
incomplete years have at least one peak-window day missing and 261 have more
than half the window gone.

## Reproducing them

```
python3 docs/reviews/wrr_stanford_2026_09_24/probe.py
```

About twenty minutes; it reads `results/v17_fitness/` and the raw network panels
and writes to `probe_output/`.
