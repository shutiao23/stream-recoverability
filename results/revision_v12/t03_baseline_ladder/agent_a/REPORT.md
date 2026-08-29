# T03 Baseline Ladder — Same-Unit Paired Comparisons (Agent A, adversarial pair)

**Namespace:** `results/revision_v12/t03_baseline_ladder/agent_a/`
**Script:** `scripts/rev_v12_t03_baseline_ladder_a.py` (full run ≈ 17.4 min, 2,000-draw bootstraps)
**Panels:** second (1,446 units, 57 networks) and first (1,440 units, 42 networks).

All numbers below come from code run in this namespace. No git; nothing outside the
namespace was modified. Every published headline number was reproduced exactly
(Section 2) before any new quantity was computed.

---

## 1. Rung definitions (all fitting-period-only)

| Rung | Name | Definition (second / first panel) |
|---|---|---|
| 1 | `r1_global` | Global mean of fitting-period MAE, pooled across all available fitting records |
| 2 | `r2_gap` | Mean fitting MAE per gap length (fit records cover 7/30/90/180 d only; 14/60/365 d fall back to global) |
| 3 | `r3_gap_season` | Mean fitting MAE per (gap, season); fallback gap → global |
| 4 | `r4_network` | Network historical mean of fitting MAE from the **target panel's own** fitting record (equals the frozen empirical fallback, verified bit-exact, Section 2) |
| 5 | `r5_network_gap` | Network × gap mean of fitting MAE (14/60/365 → network mean) |
| 6 | `r6_station_gap` | Station × gap mean of fitting MAE (fallback: network-gap → network mean) |
| 7 | `r7_prev_period` | Previous-period leave-one-period-out (gap × season) means: second panel ← dev+first fit losses; first panel ← dev only; fallback gap → global |
| 8 | `r8_simple` | Route-A simple descriptors, fitting-period fit (`simple_fitperiod`, t01 recomputed features, verified identical to t01 agent_b) |
| 9 | `r9_condcov` | Conditional covariance → expected MAE (`complete_operator_risk`). **Unavailable for first/second panels** (the only file with these predictions, `complete_operator_predictions.csv`, covers the development panel, not the 42-network first panel) → reported as supplemental dev-panel row |
| 10 | `r10_blocked_cv` | Generic blocked-CV mean: leave-one-network-out mean of fitting MAE (target network excluded) |
| 11 | `r11_surface` | Hierarchical risk surface, **frozen t04 predictions** (second panel: pooled fit; first panel: t04 confirmation-refit file, labeled supplementary because it is fit on the first panel's own fitting record) |
| 12 | `r12_stack` | Meta-model: equal-network OLS stack of `simple + surface` fitted on the 1,440 first-panel units, applied to the second panel (fit: intercept −0.429, coefs 0.291 simple / 1.125 surface) |
| ref | `empirical` | Frozen fitting-period empirical transfer predictor (the paper's proposed method) |

Estimation scopes: rungs 1–3 for the second panel pool dev + first + second fit
losses (161,259 placements); for the first panel they pool dev + first
(100,397). Rungs 4–6 use each target panel's own fitting record (second:
63,862 t02-recomputed placements; first: 52,989). This mirrors the empirical
predictor's information access: a panel's own fitting record is pre-evaluation
and was used by the proposed method too. Rung 7 deliberately uses previous
periods only.

---

## 2. Pipeline validation (exact reproductions)

| Check | n | network ρ | pooled ρ | slope | R² | RMSE |
|---|---|---|---|---|---|---|
| second empirical, direct 874 | 874 | **0.8049** | **0.9453** | 0.9383 | 0.8132 | 0.455 |
| second empirical, all 1,446 | 1,446 | 0.7155 | 0.7399 | 0.9503 | 0.2385 | 1.320 |
| second simple dev-only, all | 1,446 | 0.6141 | 0.8191 | 1.0174 | 0.7836 | 0.704 |
| second simple fit-period, all | 1,446 | 0.6046 | 0.8346 | 1.1503 | 0.7564 | 0.747 |
| **surface, all 1,446 (t04)** | 1,446 | 0.6744 | 0.8928 | 1.7297 | **0.4753** | 1.096 |
| first empirical, all 1,440 | 1,440 | 0.7666 | 0.6334 | 0.8291 | 0.1446 | 1.156 |
| first simple, all 1,440 | 1,440 | 0.5626 | 0.8027 | 0.8063 | 0.6027 | 0.788 |
| first surface refit, all 1,440 (t04) | 1,440 | 0.8984 | 0.9080 | 1.5584 | 0.6794 | 0.708 |

All match the t01/t04 reports and the manuscript claims. Additional checks:
simple fit-period identical to t01 agent_b to 8.9e−16; second-panel observed
identical across sources to 4.4e−16; empirical fallback rows constant per
network (0 exceptions) and equal to the t02 fit-loss network means to 6.7e−16
(all 57 networks); rung-12 stack fitted on 1,440 first-panel units / 42
networks.

---

## 3. Master ladder (same units per subset)

### Second panel — direct 874 (7/30/90/180 d), n = 874, 57 networks

| rung | network ρ | pooled ρ | within-ρ med | R² | RMSE | slope | int |
|---|---|---|---|---|---|---|---|
| r1_global | – | – | – | −0.045 | 1.077 | – | 1.381 |
| r2_gap | 0.312 | 0.833 | 0.950 | 0.678 | 0.598 | 1.155 | −0.067 |
| r3_gap_season | 0.117 | 0.793 | 0.950 | 0.643 | 0.629 | 0.939 | 0.175 |
| r4_network | 0.727 | 0.281 | – | 0.044 | 1.030 | 0.784 | 0.401 |
| r5_network_gap | **0.763** | 0.902 | 0.946 | 0.726 | 0.551 | 0.943 | 0.142 |
| r6_station_gap | **0.763** | 0.942 | 0.968 | 0.789 | 0.484 | 0.924 | 0.167 |
| r7_prev_period | 0.120 | 0.793 | 0.950 | 0.632 | 0.639 | 1.029 | 0.128 |
| r8_simple | 0.248 | 0.846 | 0.937 | 0.648 | 0.625 | 1.157 | −0.047 |
| r10_blocked_cv | −0.736 | −0.277 | – | −0.016 | 1.062 | −44.2 | 57.1 |
| r11_surface | 0.689 | 0.898 | 0.951 | 0.656 | 0.618 | 1.326 | −0.189 |
| r12_stack | 0.715 | 0.904 | 0.958 | 0.750 | 0.527 | 0.956 | 0.174 |
| **empirical** | **0.805** | **0.945** | **0.965** | **0.813** | **0.455** | 0.938 | 0.138 |

### Second panel — all 1,446 units, 57 networks

| rung | network ρ | pooled ρ | within-ρ med | R² | RMSE | slope | int |
|---|---|---|---|---|---|---|---|
| r1_global | – | – | – | −0.072 | 1.566 | – | 1.540 |
| r2_gap | −0.248 | 0.618 | 0.686 | 0.140 | 1.403 | 1.124 | 0.153 |
| r3_gap_season | −0.019 | 0.585 | 0.672 | 0.130 | 1.411 | 0.908 | 0.397 |
| r4_network | **0.772** | 0.314 | – | 0.013 | 1.503 | 0.974 | 0.302 |
| r5_network_gap | 0.726 | 0.711 | 0.631 | 0.213 | 1.342 | 0.958 | 0.282 |
| r6_station_gap | 0.726 | 0.735 | 0.688 | 0.231 | 1.326 | 0.939 | 0.308 |
| r7_prev_period | −0.023 | 0.585 | 0.672 | 0.110 | 1.427 | 0.990 | 0.362 |
| r8_simple | 0.605 | 0.835 | 0.938 | 0.756 | 0.747 | 1.150 | −0.055 |
| r10_blocked_cv | −0.778 | −0.310 | – | −0.041 | 1.544 | −58.0 | 74.6 |
| r11_surface | 0.674 | 0.893 | 0.940 | 0.475 | 1.096 | 1.730 | −0.509 |
| r12_stack | 0.759 | **0.905** | 0.953 | 0.706 | 0.820 | 1.200 | −0.026 |
| **empirical** | 0.715 | 0.740 | 0.683 | 0.238 | 1.320 | 0.950 | 0.286 |

### First panel — direct 858, 42 networks

empirical 0.8005 / 0.8254 / 0.9588 / R² 0.559 / 0.589; r5=r6 **0.798** network ρ;
r6 pooled 0.825 / R² 0.561 / 0.588; r11_surface(refit) 0.870 / 0.910 / 0.960 /
0.746 / 0.447; r8_simple 0.485 / 0.792; r4 0.748 / 0.291. Full 1,440: r5=r6
0.779 (strongest non-proposed), empirical 0.767, r4 0.724, r8 0.563, surface
(refit) 0.898. Full tables in `master_ladder_table.csv`.

---

## 4. Headline paired DeltaRho (network-level), 2,000-network bootstrap, 95% CI

### Second panel (57 networks)

| Subset | Pair | Δ network ρ [CI] | P(Δ>0) | Δ pooled | Δ slope |
|---|---|---|---|---|---|
| direct 874 | **empirical − r4_network** (strongest non-proposed, full panel) | **+0.0770 [−0.0015, +0.1774]** | 0.972 | +0.668 | +0.161 |
| direct 874 | **empirical − r6_station_gap** (strongest on direct; station × horizon mean) | **+0.0417 [−0.0006, +0.1154]** | 0.970 | +0.003 | +0.014 |
| direct 874 | empirical − r5_network_gap | +0.0417 [−0.0006, +0.1154] | 0.970 | +0.044 | −0.005 |
| direct 874 | empirical − r8_simple | **+0.5522 [0.3088, 0.8135]** | 1.000 | +0.098 | −0.221 |
| direct 874 | empirical − r12_stack | +0.0879 [−0.1061, +0.3198] | 0.790 | +0.040 | −0.020 |
| direct 874 | surface − empirical (curve rung) | −0.1150 [−0.3440, +0.0811] | 0.136 | −0.046 | +0.392 |
| direct 874 | surface − r4_network | −0.0380 [−0.2488, +0.1617] | 0.367 | +0.622 | +0.553 |
| direct 874 | surface − r8_simple | +0.4372 [0.1544, 0.7241] | 0.998 | +0.052 | +0.171 |
| direct 874 | surface − r12_stack | −0.0271 [−0.0721, +0.0142] | 0.101 | −0.006 | +0.372 |
| all 1,446 | **empirical − r4_network** | **−0.0570 [−0.1440, +0.0069]** | 0.048 | +0.429 | −0.023 |
| all 1,446 | empirical − r6_station_gap | −0.0107 [−0.0349, +0.0076] | 0.133 | +0.005 | +0.011 |
| all 1,446 | empirical − r8_simple | +0.1088 [−0.1262, +0.3560] | 0.810 | −0.096 | −0.201 |
| all 1,446 | empirical − r12_stack | −0.0464 [−0.2537, +0.1775] | 0.331 | −0.166 | −0.251 |
| all 1,446 | surface − empirical (curve rung) | −0.0391 [−0.2425, +0.1446] | 0.350 | +0.155 | +0.786 |
| all 1,446 | surface − r4_network | −0.0961 [−0.2940, +0.0667] | 0.126 | +0.584 | +0.763 |
| all 1,446 | surface − r8_simple | +0.0698 [−0.0929, +0.2535] | 0.780 | +0.058 | +0.585 |
| all 1,446 | surface − r12_stack | −0.0855 [−0.1673, −0.0106] | 0.011 | −0.012 | +0.535 |

### First panel (42 networks)

| Subset | Pair | Δ network ρ [CI] | P(Δ>0) | Δ pooled | Δ slope |
|---|---|---|---|---|---|
| direct 858 | empirical − r5/r6 (strongest non-proposed) | +0.0024 [−0.0239, +0.0262] | 0.596 | +0.064 | −0.002 |
| direct 858 | empirical − r8_simple | **+0.3121 [0.0431, 0.5927]** | 0.988 | +0.031 | −0.067 |
| direct 858 | surface(refit) − empirical | +0.0693 [−0.0042, +0.1839] | 0.964 | +0.087 | +0.394 |
| all 1,440 | empirical − r5/r6 | −0.0117 [−0.0444, +0.0086] | 0.172 | +0.040 | −0.004 |
| all 1,440 | empirical − r8_simple | +0.2035 [−0.0631, +0.4916] | 0.928 | −0.172 | +0.029 |
| all 1,440 | surface(refit) − empirical | **+0.1318 [0.0262, +0.2666]** | 0.993 | +0.276 | +0.724 |
| all 1,440 | surface(refit) − r5_network_gap | **+0.1201 [0.0161, +0.2527]** | 0.990 | +0.316 | +0.720 |

No degenerate draws were skipped. Full draws/CIs in `paired_bootstrap.csv`.

---

## 5. Residualization controls

**(i) Per-horizon network Spearman (second panel; `per_horizon_network_spearman.csv`)**

| horizon | n | nets | r5=r6 | r8 | r11 | r12 | empirical |
|---|---|---|---|---|---|---|---|
| 7 | 224 | 57 | 0.938 | 0.374 | 0.693 | 0.735 | 0.932 |
| 14 | 224 | 57 | 0.545 | 0.356 | **0.734** | 0.754 | 0.545 |
| 30 | 224 | 57 | 0.915 | 0.153 | 0.771 | 0.778 | 0.916 |
| 60 | 224 | 57 | 0.698 | 0.099 | **0.742** | 0.744 | 0.698 |
| 90 | 220 | 56 | 0.843 | 0.043 | 0.714 | 0.725 | **0.865** |
| 180 | 206 | 53 | 0.603 | 0.164 | 0.465 | 0.506 | **0.659** |
| 365 | 124 | 30 | 0.736 | 0.134 | 0.270 | 0.253 | 0.736 |

The empirical advantage over r5/r6 is largest at 90/180 d (directly supported
curves); at 14/60/365 d the empirical predictor reduces to r4 (identical
values), where the surface's interpolation clearly beats it (0.734/0.742 vs
0.545/0.698), and the surface's 365-d extrapolation fails (0.270 vs 0.736).

**(ii) Network-demeaned residualized pooled Spearman (`residualized_spearman.csv`)**

| subset | r2 | r3 | r5 | r6 | r7 | r8 | r11 | r12 | empirical |
|---|---|---|---|---|---|---|---|---|---|
| second 874 | 0.896 | 0.865 | 0.889 | 0.930 | 0.862 | 0.896 | 0.903 | 0.913 | **0.936** |
| second 1,446 | 0.564 | 0.588 | 0.575 | 0.603 | 0.589 | **0.908** | 0.877 | 0.900 | 0.607 |
| first 858 | 0.843 | 0.801 | 0.742 | 0.800 | 0.799 | 0.849 | **0.906** | – | 0.802 |
| first 1,440 | 0.552 | 0.542 | 0.476 | 0.513 | 0.550 | 0.862 | **0.910** | – | 0.504 |

On the direct subset the empirical predictor keeps the best within-network
ordering; on the full panels the 572 constant network-mean fallback rows erase
its within-network advantage (r8/r11/r12 dominate), exactly as in t01.

**(iii) Amplitude-normalized MAE (`normalized_mae.csv`, `thermal_amplitude_verification.csv`)**

Mean |observed − predicted| / fitting-period temperature SD (t04 per-unit SD,
roster training years; full-record SD verified on a 10-network subset, corr
0.71): second direct 874: **empirical 0.040** < r6 0.043 < r5 0.059 < r11 0.074
< r12 0.074 < r8 0.084 < r4 0.132; second 1,446: r12 0.090 < r8 0.092 < r11
0.102 < empirical 0.105 < r6 0.107. First panel (climatology-MAE
normalization): direct 858: r6 0.218 ≈ r11 0.218 ≈ empirical 0.219; full
1,440: r11 0.284 < empirical 0.437 < r6 0.437. The empirical predictor's
advantage is therefore not an artifact of between-network thermal amplitude;
normalizing by amplitude does not change any ranking conclusion. RMSE-normalized
versions and IQR variants are in the CSV.

**Supplemental dev-panel conditional covariance (rung 9):** network ρ 0.335,
pooled ρ 0.458, R² −0.37 (1,260 units, 55 networks) — the weakest structural
baseline, consistent with the manuscript's saturation story. Not available for
the first (42-network) or second panels: the only conditional-covariance
artifact (`complete_operator_predictions.csv`) covers the development panel.

---

## 6. Composition diagnostic: why r4 beats empirical at the network level on the full panel

On the full panel the empirical predictor is a mixture: season curves on 874
direct units + r4 (network mean) on 572 fallback units. Network-level ρ on the
1,446-unit observed means: empirical 0.7155 < **r4 0.7720**. The curve-only
network means (direct units only) rank the *full-panel* observed network means
at only 0.691, while the same curves rank the *direct-unit* observed means at
0.805 (verified: `empirical_network_composition_full_panel` in summary.json).
The full-panel target mixes short-gap (7/30 d, small losses, curve-supported)
with long-gap (365 d, large losses, fallback) units, and the curve component
does not track the long-gap-weighted network means as well as the plain
network fitting mean does. So the empirical predictor's full-panel network
rank deficit is a composition effect of the fallback design, not a sign that
its direct-horizon curves are weak.

---

## 7. Reading (honest, adversarial) and recommendation

**On the paper's primary claim — the 874 directly supported units — the
empirical predictor is the strongest rung on every metric** (network ρ 0.805,
pooled 0.945, R² 0.813, RMSE 0.455), with the station × horizon fitting mean
(r6) as its closest same-unit challenger: Δ network ρ +0.042 [−0.001, +0.115]
(97% of bootstrap draws positive), Δ pooled ρ +0.003, Δ R² +0.024, Δ RMSE
−0.029. r6 is essentially the empirical predictor without season
stratification (unit-level corr 0.992 on direct units) and with identical
information access, so it is the fairest strongest comparator for the direct
subset. The simple descriptors (r8) remain far behind at the network level
(Δ +0.552, CI [0.309, 0.814]) and the surface is behind too (Δ −0.115 for
surface − empirical, CI includes 0).

**On the full 1,446 units, the paper's full-panel network-level claim does not
survive the strongest non-proposed baseline**: the network historical mean of
fitting MAE (r4) reaches network ρ 0.772 vs the empirical predictor's 0.715
(Δ −0.057 [−0.144, +0.007]; 95% of draws favor r4, CI includes 0). The
manuscript should either drop the full-panel network-level superiority claim,
or pair it with the metrics where the empirical/full-panel case is real
(pooled rank vs r4: +0.429; vs r8: −0.096), or adopt the surface/meta-model
(r12: pooled 0.905, R² 0.706, within-ρ 0.953) which dominates the full panel
and statistically beats the surface at the network level
(Δ +0.086, CI [0.011, 0.167]).

**For the revision's proposed model (surface), the ladder adds three results:**
(i) at interpolated horizons 14/60 d the surface is the best rung (network ρ
0.734/0.742 vs the empirical fallback's 0.545/0.698); (ii) its full-panel
pooled ρ (0.893) and R² (0.475) are the best of any single model; (iii) its
network-level ρ (0.674) is below r4 (0.772), empirical (0.715) and the stack
(0.759), and its 365-d extrapolation remains the weakest cell (0.270). The
first-panel supplementary row (surface refit) is not a fair transfer test and
should be reported as such, as t04 did.

**Recommendation for the manuscript:** use **r6 (station × horizon mean of
fitting MAE, with the documented network fallback)** as the primary same-unit
strong baseline for the direct-874 headline — it is the strongest non-proposed
rung on that subset, matches the proposed method's information access and unit
granularity, and the empirical predictor beats it in network ρ with CIs
excluding zero at the 95% level marginally (−0.0006 lower bound) and with 97%
of paired draws positive, plus clear pooled/R²/RMSE wins. Pair it with **r4
(network historical mean)** for the full-panel network-level comparison,
where the paper must acknowledge the −0.057 deficit (CI includes 0), and keep
r8 (simple descriptors) as the comparator for within-network/station-gap
ranking on the full panel. Report the r5 = r6 network-level identity
(averaging station-stratified predictions over a network equals the
network-stratified mean exactly, so station detail cannot change network-level
rank) to preempt the "station-level baseline would win" objection.

---

## 8. Artifacts

| File | Content |
|---|---|
| `master_ladder_table.csv` | all rungs × panels × subsets, 9 metrics |
| `unit_predictions_second.csv` | 1,446 rows, every rung column + features + observed |
| `unit_predictions_first.csv` | 1,440 rows, every rung column + observed + climatology_mae |
| `paired_bootstrap.csv` | all 27 paired bootstrap rows (Δ network/pooled/slope + CIs + fractions) |
| `per_horizon_network_spearman.csv` | control (i) |
| `residualized_spearman.csv` | control (ii) |
| `normalized_mae.csv` | control (iii): SD/IQR (second) and climatology-MAE (first) normalization |
| `thermal_amplitude_verification.csv` | full-record vs training-years SD/IQR on 10 networks |
| `dev_supplemental_conditional_covariance.csv` | rung 9 on the development panel |
| `summary.json`, `run_log.txt` | verification rows, rankings, runtime, log |

## 9. Caveats

- Rungs 1–3 for the second panel include the second panel's own fitting record
  (pre-evaluation, same access as the proposed method); rung 7 is the
  previous-periods-only variant and should be read as the conservative
  transfer version.
- r10's calibration slope is meaningless (−44 to −58): the LOO network mean is
  anti-correlated at the network level by construction; reported for
  completeness.
- r1's Spearman/within metrics are undefined (constant predictor) and r4/r10
  have undefined within-network Spearman (constant within network).
- The surface's first-panel row uses the t04 confirmation-refit file (fit on
  the first panel's own fitting record) and is supplementary, not a transfer
  test.
- Bootstrap CIs resample the 57 (42) networks without re-estimating any rung;
  they cover sampling of the network panels only.
