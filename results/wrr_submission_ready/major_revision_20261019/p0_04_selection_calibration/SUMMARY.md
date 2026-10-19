# Selection-rule calibration

2000 synthetic repetitions. Each repetition fits the threshold on 32 groups and scores 16 fresh groups. The data-generating false-admit probability increases with the score and has a group intercept.

- Pointwise 95% bound, then max over 86 grid points: test false-admit rate exceeds 5% in 0.192 of repetitions (Monte Carlo SE 0.009).
- Deployed Bonferroni bound: exceedance rate 0.085 (Monte Carlo SE 0.006).
- Mean retention: pointwise 0.359, Bonferroni 0.205.

No network-count recommendation is issued from this simulation. The old design-effect formula that divided the network count by a case-level design effect is not used.
