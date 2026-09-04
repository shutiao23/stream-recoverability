# Round-2 S1: MAE-scale zero-crossing of realized benefit with a network-cluster bootstrap CI

Threshold definition (pre-declared, this revision): the first positive-to-negative crossing of the unit-mean realized benefit over the climatology default, on the fitted horizon grid 7/14/30/60/90/180/365 d (all grid points except 365 d carry direct fitting support), located by piecewise-linear interpolation in log10(gap) (convention of `scripts/147_run_p4_flip_analysis.py`).  Interval: 2,000 network-cluster bootstrap draws, seed 20260903; 2.5/97.5 percentiles of the per-draw crossing day.  The old '~60 d' figure is retired: no reproducible artifact for an internal sub-grid analysis exists in `results/v14/` (REVIEW_v14_round2.md Major 1).

| panel | point crossing (d) | 95% CI (d) | grid unit rows | n networks |
|---|---|---|---|---|
| first | 105.3 | [97.6, 114.3] | 1440 | 42 |
| second | 91.5 | [85.3, 94.8] | 1446 | 57 |

- first panel: 0 of 2000 draws without a positive-to-negative flip on the resampled curve.
- second panel: 0 of 2000 draws without a positive-to-negative flip on the resampled curve.