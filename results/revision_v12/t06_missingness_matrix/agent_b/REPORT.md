# Missingness-Mechanism Matrix (revision v12, task t06, agent B)

**Adversarial-pair deliverable.** Independent implementation; no coordination
with agent A. Every number below is computed by
`scripts/rev_v12_t06_missingness_b.py` from the QC'd daily panels under
`results/development_v11/confirmation_daily_qc/` (plus NASA POWER T2M for
mechanism (g)). Nothing was copied from the paired agent.

## 1. Task and design

Reviewers demanded a missingness-mechanism matrix beyond uniform grid gaps.
This analysis builds, per mechanism, a **mechanism-specific fitting-period
empirical stress curve** (nested chronological split: first 70% of fitting
years fit the paper's XGBoost recovery family — 300 trees, depth 4, lr 0.05,
boundary + donor features, B_union_D; the remaining fitting years receive
injected mechanism gaps whose mean MAE forms a station x horizon x season
curve, up to 20 placements per cell, horizons 7/30/90/180), injects the
**same mechanism** into the evaluation years (recovery model fit on all
fitting years, up to 20 placements per station-gap, mirroring
`scripts/106/108` and `src/.../recovery_roster.fitting_period_empirical_losses`
+ `empirical_transfer_predictions`), computes the outer loss, and evaluates
risk -> loss transfer (network-level Spearman on network-mean predicted vs
observed; equal-network weighted calibration slope/intercept) per mechanism.

**Validation against the frozen reference pipeline:** my mechanism (a)
predictions reproduce `results/development_v11/reviewer_completion/
confirmation_empirical_predictions.csv` at the unit level on the 9 shared
networks (unit prediction correlation 0.996, observed 0.998; per-network means
within 0.01-0.02 °C; 236 of 239 reference units matched; network Spearman
0.933 vs the reference's 0.900 on that subset — within bootstrap noise).

## 2. Data

12 first-panel networks (all in the 42-network route-A panel), 91 stations
with scored units, all with daily QC temperature:

| provider | networks |
|---|---|
| chmi | labe, morava |
| foen | aare_aaregebiet |
| gkd_bayern | donau, isar |
| lubw | neckar |
| rws | rijn_lek_nederrijn |
| usgs | huc8_03150202, huc8_10020007, huc8_17090004, huc8_17090012, usgs_missouri_river_huc10 |

## 3. Mechanisms

| id | mechanism | definition | fitting-period curve support |
|---|---|---|---|
| (a) | uniform_block | single contiguous gap, uniform start, season cells DJF/MAM/JJA/SON | supported (reproduces the paper's grid) |
| (b) | multi_block | gap = 2-4 short blocks (block = ceil(g/n), 2-day separators); block-local linear boundaries | supported |
| (c) | summer_biased | starts restricted to Jul 1 - Aug 31 (peak summer) | supported (JJA cells only) |
| (d) | high_temp_biased | window mean >= 75th percentile of the station's fitting-period window means (threshold from model-fit years only) | supported |
| (e) | discharge_biased | **skipped** — no discharge in `data/processed` for the confirmation panel (daily_long/daily_wide/splits are the China corpus; auxiliary F/L exist only for development networks, none of my 12) | n/a |
| (f) | donor_sync | target + all donors masked inside the window (regional outage); same windows as (a) | supported |
| (g) | forcing_outage | target + air temperature (NASA POWER T2M at the network centroid, repo's own acquisition path) masked; model B∪D∪Ta | supported |
| (h) | online | no future boundary: model trained and scored with past-only boundary (last observed value carried forward) | supported |

For every implemented mechanism the fitting-period stress curve exists and
supports the vast majority of units directly (see Section 6).

## 4. Mechanism-stratified results (within-horizon supported units)

Primary convention matches the paper's 780-unit analysis: units whose
prediction used a fitting-period curve source other than the network-mean
fallback. Full-panel (fallback-inclusive) numbers are in
`mechanism_metrics.csv` (columns prefixed `full_`).

| mechanism | network Spearman | pooled Spearman | calib. slope | calib. intercept | n units | n nets | mean pred | mean obs (°C) | fallback frac |
|---|---|---|---|---|---|---|---|---|---|
| (a) uniform block | **0.944** | 0.915 | 1.021 | -0.041 | 306 | 12 | 1.007 | 0.981 | 0.116 |
| (b) multi-block | 0.888 | 0.888 | 1.016 | -0.034 | 306 | 12 | 0.599 | 0.567 | 0.116 |
| (c) summer-biased | 0.909 | 0.855 | 1.043 | -0.004 | 292 | 12 | 0.928 | 0.958 | 0.126 |
| (d) high-temp-biased | 0.958 | 0.876 | 0.907 | 0.045 | 304 | 12 | 1.271 | 1.180 | 0.114 |
| (f) donor-synchronous | **0.490** | 0.722 | **0.743** | 0.636 | 306 | 12 | 2.374 | 2.539 | 0.116 |
| (g) target+Ta outage | 0.937 | 0.913 | 0.987 | -0.029 | 306 | 12 | 1.104 | 1.065 | 0.116 |
| (h) online (no future) | 0.965 | 0.889 | 0.942 | 0.012 | 306 | 12 | 1.578 | 1.430 | 0.116 |

Network-bootstrap 95% intervals (2,000 resamples, `mechanism_bootstrap_intervals.csv`):
Spearman — (a) [0.69, 1.00], (b) [0.53, 1.00], (c) [0.65, 1.00], (d) [0.78, 1.00],
(f) [-0.24, 0.93], (g) [0.70, 1.00], (h) [0.81, 1.00]. Slope — (f) [0.53, 0.93], all
others ~[0.77, 1.16].

Mechanism stress levels (fitting-period curve mean vs evaluation realization):
uniform 1.12/1.11, multi-block 0.62/0.59, summer 0.98/1.01, high-temp 1.33/1.33,
donor-sync 2.69/2.71, forcing 1.23/1.18, online 1.65/1.52 °C. Horizon means (eval):
donor-sync rises 2.1 -> 4.0 °C from 7 to 180 days; uniform 0.43 -> 2.27; online
0.54 -> 2.80; multi-block stays 0.36 -> 0.81.

## 5. Mismatch experiment (support mismatch)

Uniform-block curve applied to summer-biased gaps (and symmetric/other pairs),
on units where both matched and mismatched predictions have within-horizon
support:

| direction | matched net ρ | mismatched net ρ | Δρ | matched slope | mismatched slope | Δslope | n units |
|---|---|---|---|---|---|---|---|
| uniform curve on summer gaps | 0.909 | 0.895 | **-0.014** | 1.043 | 0.851 | **-0.191** | 254 |
| summer curve on uniform gaps | 0.944 | 0.930 | -0.014 | 1.021 | 1.219 | +0.198 | 244 |
| uniform curve on donor-sync gaps | 0.490 | 0.524 | +0.035 | 0.743 | 0.732 | -0.010 | 255 |
| donor-sync curve on uniform gaps | 0.944 | 0.098 | **-0.846** | 1.021 | 0.176 | **-0.845** | 255 |
| uniform curve on multi-block gaps | 0.888 | 0.706 | -0.182 | 1.016 | 0.304 | **-0.712** | 255 |
| multi-block curve on uniform gaps | 0.944 | 0.566 | -0.378 | 1.021 | 2.313 | +1.293 | 255 |

**Answer to the review question:** support mismatch degrades transfer, but the
magnitude depends on *what* the mechanism changes. Calendar/temperature
selection (uniform -> summer) costs calibration (slope -0.19) while rank order
is nearly unchanged (-0.01). Mechanisms that change the information available
during recovery (donor availability, boundary structure) destroy calibration
when the curve's mechanism does not match (slope deltas of -0.85 for donor-sync
and -0.71 for multi-block in the damaging direction).

## 6. Missingness x support matrix

`missingness_support_matrix.csv` (full units, all sources). Supported-fraction
summary: (a) 88.4%, (b) 88.4%, (c) 87.4%, (d) 88.6%, (f) 88.4%, (g) 88.4%,
(h) 88.4% of units are within-horizon supported
(`station_gap_season` 81% + `station_gap` 2% + `network_gap` 15%); the
remaining ~11.6% use the network-mean fallback, concentrated at 180-day
horizons where several networks' donors are not jointly complete across a
180-day fitting-period window (the same behaviour as the reference pipeline,
whose 780-unit analysis excluded such units). No implemented mechanism lacks
fitting-period curve support; mechanism (e) was not implemented (see Section 3).

## 7. Cross-checks

- **Uniform grid:** paper reports network Spearman 0.922 on 780 first-panel
  units (42 networks). My mechanism (a): **0.944** on 306 supported units
  (12 networks) — same regime; and 0.933 vs the frozen reference's 0.900 on
  the 9 shared networks. Mechanism (a) therefore reproduces uniform-grid
  behavior on its subset.
- **Planted field geometry:** paper reports 0.566 with 85.8% fallback. My
  mechanisms are synthetic (no real outage catalog), so this is not directly
  reproduced; the closest analog is donor-synchronous outage (network
  Spearman 0.490), which shows that geometry that removes donor support does
  degrade the empirical-transfer ranking.

## 8. Main conclusion on geometry robustness

1. **Mechanism (a) is confirmed**: uniform-block stress curves transfer at the
   paper's level (0.94 vs 0.92).
2. **Rank transfer is robust to calendar and thermal selection** (summer,
   high-temp, online: ρ = 0.91-0.97) but **breaks when the outage removes
   donor information** (donor-synchronous: ρ = 0.49, slope 0.74).
3. **Magnitude/calibration is the fragile part**: every mechanism except
   multi-block shows slope < 1 or fallback-heavy tails; support mismatch
   degrades calibration (slope deltas -0.19 to -0.85) more than rank.
4. Fitting-period stress curves support all implemented mechanisms directly;
   a generic uniform-grid curve should not be quoted for donor-synchronous or
   block-structured outages.

## 9. Files

`results/revision_v12/t06_missingness_matrix/agent_b/`:
`mechanism_metrics.csv`, `mechanism_units.csv`, `mechanism_curve_cells.csv`,
`mechanism_eval_cells.csv`, `missingness_support_matrix.csv`,
`mismatch_experiment.csv`, `mechanism_stress_levels.csv`,
`mechanism_bootstrap_intervals.csv`, `attrition_log.csv`, `provenance.json`,
`power_ta_cache/` (NASA POWER T2M per network). Script:
`scripts/rev_v12_t06_missingness_b.py` (runtime ~95 s, 5 workers, no GPU).

Caveats: station-level donor selection prunes donors lacking evaluation-period
support (documented in `attrition_log.csv`); POWER T2M uses network-centroid
coordinates and NASA's daily grid; the first panel's evaluation model is fit
on all fitting years while the curve model is fit on the first 70% of fitting
years (both exactly as in the reference pipeline); no actual missing days were
scored — all gaps are injected.
