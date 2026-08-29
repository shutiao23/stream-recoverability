# Strongest-Baseline Harmonization Analysis — agent_b (adversarial pair)

**Task**: definitive empirical-vs-strongest-fair-baseline comparison for the
Water Resources Research revision. The strongest fair baseline is the
**station × horizon historical mean of fitting-period MAE** (t03 ladder rung
`r6_station_gap`): it matches the proposed method's information access
(fitting-period observed recovery losses at the same stations/horizons) and is
the strongest non-proposed rung on the direct subset.

**Agent**: sbase_b (adversarial pair; sibling sbase_a runs the same analysis
independently; a senior reviewer reconciles). Everything here was computed
from the revision-v12 artifacts listed below; nothing was trusted from the
reviewer report or the claim matrix until verified. All code, inputs, and
outputs live in this directory (`results/revision_v13/strongest_baseline/agent_b/`).
Runtime ≈ 2.5 min.

---

## 1. Inputs (read-only) and pipeline validation

| File | Contents |
|---|---|
| `results/revision_v12/t01_paired_comparison/agent_a/predictions.csv` | 1,446 second-panel rows; `simple_fitperiod`, `empirical_transfer_prediction`, `observed_recovery_loss`, `provider`, `domain`, `horizon_group` |
| `results/revision_v12/t03_baseline_ladder/agent_a/unit_predictions_second.csv` | same 1,446 rows + `r6_station_gap`, `r4_network`, `r5_network_gap`, `r8_simple`, `surface_prediction_mae`, `empirical` |
| `results/revision_v12/t03_baseline_ladder/agent_a/unit_predictions_first.csv` | 1,440 first-panel rows (no `horizon_group`; carries `r6_station_gap`, `r8_simple`, `surface_prediction_mae`) |
| `results/revision_v12/t03_baseline_ladder/agent_a/master_ladder_table.csv` | aggregate per-rung metrics per panel/subset (verification target) |
| `results/revision_v12/t03_baseline_ladder/agent_a/paired_bootstrap.csv` | empirical-vs-r6 paired bootstrap (seed 0) — verification target |

**Consistency checks performed (all passed):**
- Second panel: t01 and t03 files agree exactly on keys and on
  `empirical_transfer_prediction`, `observed_recovery_loss`,
  `simple_fitperiod` (max |diff| ≤ 4.4e−16). First panel:
  `empirical == empirical_transfer_prediction` (max |diff| < 1e−12).
- `r8_simple == simple_fitperiod` (second panel; max diff 4.4e−16) — the
  ladder's r8 IS the t01 fit-period simple predictor.
- `r11_surface == surface_prediction_mae` (exact, both panels) — the ladder's
  r11 IS the surface prediction column used here.
- Second panel: the `horizon_group` column is exactly the rule
  `gap_length ∈ {7,30,90,180} → direct` (874 rows), so the first panel's
  missing `horizon_group` was reconstructed with the identical rule
  (858 direct / 582 fallback rows) — matching t03's `DIRECT_HORIZONS` rule.

**Metric conventions (bit-compatible with `scripts/rev_v12_t03_baseline_ladder_a.py`)**
- Pooled Spearman: unit-level (station-gap) Spearman of prediction vs
  observed recovery loss.
- Network Spearman: Spearman over network means (mean prediction, mean
  observed) of the 57 / 42 networks.
- Calibration: equal-network-weighted OLS of observed on prediction with root
  weights `w = sqrt(1/n_units_in_network)` (t03 `_fit_linear`, `lstsq`).
- R² (ordinary, pooled), RMSE (ordinary, pooled).
- Network-mean-only pooled control: replace each unit's prediction with its
  network's mean **observed** loss (perfect in-sample network benchmark) and
  compute pooled Spearman; subset-level quantity, identical for all methods.
- Within-network Spearman: per-network Spearman (≥ 4 units, non-constant both
  arrays); median/mean across networks.
- Network-demeaned (residualized) pooled ρ: pooled Spearman after subtracting
  each network's mean from both prediction and observed.
- Paired bootstrap (t03 convention): resample 57 / 42 networks with
  replacement, relabel duplicate draws `draw_0..draw_k` so every draw appears
  exactly once as a "network", recompute pooled + network Spearman for both
  predictors on the same resampled frame, record deltas. 2,000 draws;
  95% percentile CI (2.5/97.5). No degenerate draws skipped.

**Verification (two independent controls, both machine-precision):**
1. **Ladder reproduction**: all 16 (panel × subset × method) cells reproduced
   from the unit files reproduce `master_ladder_table.csv` exactly
   (pooled ρ, network ρ, calib slope/intercept, R², RMSE; max |diff| < 1e−12).
   See `ladder_verification.csv`; failures = 0.
2. **Seed-0 bootstrap reproduction**: running the paired bootstrap with seed 0
   reproduces every empirical-vs-r6 row of the archived
   `t03/paired_bootstrap.csv` to |diff| ≤ 1e−16 (means, CIs, win fractions,
   all 8 level × subset rows). See `paired_bootstrap_seed0_verification.csv`.

The final deliverables use **seed 42** (mandated by the task) — the seed-0
run exists purely as the pipeline-validation control.

---

## 2. Panel composition (fixes the manuscript's "35 US" bug)

| Panel | Networks | Stations | Units | Direct units | Fallback units |
|---|---|---|---|---|---|
| second | 57 | 224 | 1,446 | 874 | 572 |
| first | 42 | 219 | 1,440 | 858 | 582 |

Second panel (57 networks): **united_states 32** networks / 114 stations /
703 units; czechia 15 / 69 / 478; norway 10 / 41 / 265.
→ The manuscript's "35 US networks" is wrong; the correct count is **32**
(32 + 15 + 10 = 57).

First panel (42 networks): united_states 17 / 95 / 583; slovenia 12 / 47 /
329; germany 11 / 65 / 444; switzerland 1 / 9 / 63; netherlands 1 / 3 / 21.
(17 + 12 + 11 + 1 + 1 = 42 networks; 95 + 47 + 65 + 9 + 3 = 219 stations;
583 + 329 + 444 + 63 + 21 = 1,440 units.) Full table: `panel_composition.csv`.

---

## 3. Unit-level comparison tables

`unit_comparison_second.csv` (1,446 rows) and `unit_comparison_first.csv`
(1,440 rows): one row per unit with `network_id`, `station_id`, `gap_length`,
`horizon_group`, `empirical`, `r6`, `simple`, `surface`,
`observed_recovery_loss`, `subset` (direct/all). These are the canonical
same-unit comparison tables for all downstream cells.

---

## 4. Summary metrics per (panel, subset, method)

Pooled ρ / network ρ / network-mean-only pooled ρ / equal-network calib slope
& intercept / R² / RMSE. Source: `summary_metrics.csv`. All four methods
(empirical, r6, simple, surface) evaluated on identical units per cell.

### Second panel — direct 874 (n = 874, 57 networks; network-mean-only pooled ρ = 0.326)

| Method | pooled ρ | network ρ | calib slope | calib int | R² | RMSE |
|---|---|---|---|---|---|---|
| **empirical** | **0.9453** | **0.8049** | 0.9383 | 0.1383 | **0.8132** | **0.4553** |
| r6 (station×horizon mean) | 0.9424 | 0.7632 | 0.9235 | 0.1670 | 0.7893 | 0.4836 |
| simple (fit-period) | 0.8459 | 0.2475 | 1.1571 | −0.0465 | 0.6477 | 0.6254 |
| surface | 0.8979 | 0.6887 | 1.3258 | −0.1886 | 0.6563 | 0.6177 |

### Second panel — all 1,446 (57 networks; network-mean-only pooled ρ = 0.309)

| Method | pooled ρ | network ρ | calib slope | calib int | R² | RMSE |
|---|---|---|---|---|---|---|
| empirical | 0.7399 | 0.7155 | 0.9503 | 0.2862 | 0.2385 | 1.3201 |
| r6 | 0.7353 | 0.7256 | 0.9385 | 0.3077 | 0.2315 | 1.3262 |
| **simple** | **0.8346** | 0.6046 | 1.1503 | −0.0548 | **0.7564** | **0.7466** |
| surface | 0.8928 | 0.6744 | 1.7297 | −0.5085 | 0.4753 | 1.0958 |

### First panel — direct 858 (n = 858, 42 networks; network-mean-only pooled ρ = 0.350)

| Method | pooled ρ | network ρ | calib slope | calib int | R² | RMSE |
|---|---|---|---|---|---|---|
| **empirical** | 0.8254 | **0.8005** | 0.8313 | 0.1995 | 0.5591 | 0.5890 |
| r6 | 0.8250 | 0.7984 | 0.8410 | 0.1897 | 0.5613 | 0.5876 |
| simple | 0.7916 | 0.4846 | 0.9041 | −0.0766 | 0.5199 | 0.6147 |
| surface (supplementary refit) | **0.9103** | 0.8704 | 1.2309 | −0.1853 | 0.7456 | 0.4475 |

### First panel — all 1,440 (42 networks; network-mean-only pooled ρ = 0.361)

| Method | pooled ρ | network ρ | calib slope | calib int | R² | RMSE |
|---|---|---|---|---|---|---|
| empirical | 0.6334 | 0.7666 | 0.8291 | 0.3937 | 0.1446 | 1.1564 |
| r6 | 0.6330 | 0.7793 | 0.8399 | 0.3827 | 0.1453 | 1.1560 |
| simple | 0.8027 | 0.5626 | 0.8063 | 0.0184 | 0.6027 | 0.7881 |
| surface (supplementary refit) | 0.9080 | 0.8984 | 1.5584 | −0.4506 | 0.6794 | 0.7079 |

**Reading**: on the direct subsets the empirical predictor is first or tied
with r6 on every metric; its largest advantage over r6 is at the **network
level** (0.8049 vs 0.7632 on second; 0.8005 vs 0.7984 on first). On the full
panels, r6's network ρ (0.7256 / 0.7793) edges out empirical (0.7155 /
0.7666) because the 572 / 582 constant network-mean fallback rows erase the
empirical predictor's curve component at network rank (composition effect
documented in t03 Section 6, reproduced here by the identical aggregate
values).

---

## 5. Paired bootstrap: empirical − r6 (2,000 draws)

Primary (seed 42, `paired_bootstrap.csv`); archived comparison (seed 0,
`paired_bootstrap_seed0_verification.csv`, verified identical to
t03/paired_bootstrap.csv to 1e−16).

| Panel / subset | Level | Δρ mean | 95% CI | win fraction |
|---|---|---|---|---|
| second direct 874 | network | **+0.0412** | [−0.0004, +0.1140] | 0.9705 |
| second direct 874 | station-gap (pooled) | +0.0028 | [−0.0004, +0.0066] | 0.9505 |
| second all 1,446 | network | −0.0110 | [−0.0356, +0.0079] | 0.1295 |
| second all 1,446 | station-gap (pooled) | +0.0045 | [+0.0010, +0.0088] | 0.9960 |
| first direct 858 | network | **+0.0025** | [−0.0237, +0.0274] | 0.5995 |
| first direct 858 | station-gap (pooled) | +0.0002 | [−0.0037, +0.0039] | 0.5605 |
| first all 1,440 | network | −0.0118 | [−0.0453, +0.0086] | 0.1650 |
| first all 1,440 | station-gap (pooled) | +0.0003 | [−0.0024, +0.0028] | 0.5965 |

Bootstrap mean network ρ per predictor (seed 42): second direct — empirical
0.7974 vs r6 0.7562; first direct — 0.7883 vs 0.7859. On the direct-874 cell,
97.05% of draws favor the empirical predictor at the network level; the 95% CI
has a small negative lower bound (−0.0004 at seed 42; −0.0006 at seed 0), i.e.
the difference is marginally not significant at the 2.5% level in the
unfavorable tail.

---

## 6. Per-horizon network Spearman (second panel, direct subset)

Source: `per_horizon_network_spearman.csv`.

| Horizon | n units | n networks | empirical | r6 | simple |
|---|---|---|---|---|---|
| 7 d | 224 | 57 | 0.9321 | **0.9384** | 0.3744 |
| 30 d | 224 | 57 | **0.9157** | 0.9154 | 0.1530 |
| 90 d | 220 | 56 | **0.8648** | 0.8435 | 0.0429 |
| 180 d | 206 | 53 | **0.6594** | 0.6035 | 0.1640 |

The empirical advantage over r6 is concentrated at 90/180 d (+0.021 / +0.056);
at 7 d r6 slightly outranks the empirical curve (−0.006), and at 30 d they are
equal. Simple descriptors are far behind at every horizon.

---

## 7. Predictor correlation (empirical vs r6, empirical vs simple)

Source: `predictor_correlation.csv`. The review's "≈0.992" is the **Pearson**
correlation of predictions; Spearman is higher (0.996).

| Subset | empirical–r6 Pearson | empirical–r6 Spearman | empirical–simple Pearson | empirical–simple Spearman |
|---|---|---|---|---|
| second direct 874 | 0.9917 | 0.9959 | 0.7643 | 0.8010 |
| second all 1,446 | 0.9923 | 0.9958 | 0.3927 | 0.6053 |
| first direct 858 | 0.9948 | 0.9976 | 0.5895 | 0.6210 |
| first all 1,440 | 0.9954 | 0.9983 | 0.2661 | 0.4225 |

The r6 baseline is essentially the empirical predictor's values (station ×
horizon mean) **without** its season stratification — confirming it is the
fairest possible strongest comparator. The empirical–simple correlation is
moderate (0.80 rank on direct units), which is why the simple descriptors lag
so far at the network level.

---

## 8. Within-network decomposition (direct subsets)

Source: `within_network_decomposition.csv`.

| Panel / subset | Method | Network-demeaned pooled ρ | Median within-network ρ | Mean within-network ρ |
|---|---|---|---|---|
| second direct 874 | empirical | **0.9359** | 0.9650 | 0.9295 |
| second direct 874 | r6 | 0.9298 | **0.9676** | 0.9335 |
| second direct 874 | simple | 0.8958 | 0.9371 | 0.9110 |
| second direct 874 | surface | 0.9034 | 0.9510 | 0.9140 |
| first direct 858 | empirical | 0.8015 | 0.9588 | 0.8774 |
| first direct 858 | r6 | 0.8002 | 0.9510 | 0.8784 |
| first direct 858 | simple | 0.8494 | 0.9063 | 0.8686 |
| first direct 858 | surface | 0.9055 | 0.9599 | 0.9317 |

Both predictors' power is overwhelmingly within-network: the empirical
predictor's network-demeaned pooled ρ (0.936) is nearly identical to its raw
pooled ρ (0.945) on the direct-874 cell, and the network-mean-only benchmark
reaches only 0.326 — i.e. the 0.805 network ρ is the upward aggregation of
within-network station ordering, not between-network difficulty. r6's
within-network median (0.968) slightly exceeds empirical's (0.965) while its
network-demeaned pooled ρ (0.930) trails empirical's (0.936); the empirical
edge is therefore in the between-network component of rank (network ρ +0.042).

---

## 9. Discrepancy log vs the review's quoted numbers

Every review value was checked against the artifacts. Values marked
"verified" were reproduced to the digits shown; the only procedural
difference is bootstrap seed (review/t03: 0; this run: 42, mandated by the
task), which changes Monte Carlo CIs in the 3rd decimal only.

| # | Review / claim-matrix quote | Artifact-derived value (this run) | Resolution |
|---|---|---|---|
| 1 | direct-874 pooled: 0.945 vs 0.942 | empirical 0.9453 vs r6 0.9424 | **Verified** — exact. |
| 2 | network: 0.805 vs 0.763 | empirical 0.8049 vs r6 0.7632 | **Verified** — exact. |
| 3 | paired network Δρ +0.042 (CI [−0.0006, +0.1154]) | seed 0: +0.0417 [−0.0006, +0.1154]; seed 42: +0.0412 [−0.0004, +0.1140]; win fraction 0.9705 at both seeds | **Verified** — review's CI is the archived seed-0 CI, reproduced to 1e−16. Seed-42 CI differs in the 3rd decimal (Monte Carlo). CI spans zero in both seeds; 97.0% of draws positive. |
| 4 | first-panel Δρ +0.0024 | first direct 858: +0.0024 [−0.0239, +0.0262] (seed 0); +0.0025 [−0.0237, +0.0274] (seed 42); win 0.60 | **Verified** — matches (first-panel CI is seed 0's). |
| 5 | predictor correlation ≈0.992 | Pearson 0.9917 (direct 874), 0.9923 (all 1,446); Spearman 0.9959 / 0.9958 | **Verified with precision note** — "0.992" is the Pearson correlation; the Spearman rank correlation is 0.9959 (direct) / 0.9958 (all). Recommend quoting Pearson 0.9917 / 0.9923 (as claim_matrix_v13_b already does) or "rank 0.996". |
| 6 | paired pooled Δ +0.003 (direct 874) | +0.0029 (seed 0), +0.0028 (seed 42) | **Verified**. |
| 7 | manuscript "35 US networks" | second panel has **32** US networks (57 = 32 US + 15 CZ + 10 NO) | **Bug confirmed and fixed** — use 32. |
| 8 | r6 within-network median 0.968 (ladder) | 0.9676 | **Verified** — r6's within-network median slightly exceeds empirical's 0.9650. |
| 9 | empirical residualized pooled 0.936 | 0.9359 | **Verified**. |
| 10 | per-horizon empirical 0.932/0.916/0.865/0.659 | 0.9321 / 0.9157 / 0.8648 / 0.6594 | **Verified** — plus r6 per-horizon 0.938 / 0.915 / 0.843 / 0.603 (r6 slightly ahead at 7 d, behind at 90/180 d). |

No review number was found wrong beyond the "35 US" composition bug; the
precision note on #5 (Pearson vs Spearman) and the seed-42 CI deltas (#3, #4)
are the only other items a reconciler should be aware of.

---

## 10. Which values feed the revision artifacts

- **claim_matrix_v13_b (C1, honest sub-row)** — all of: pooled 0.942 vs 0.945
  (#1); network 0.763 vs 0.805 (#2); paired network Δ +0.0417 [−0.0006,
  +0.1154], 97.0% draws positive (#3); paired pooled Δ +0.003 (#6);
  correlation 0.9917 / 0.9923 (#5); first-panel Δ +0.0024 [−0.0239, +0.0262]
  (#4); simple +0.552 [+0.309, +0.814] (t01/t03 paired bootstrap, unchanged).
- **Abstract / manuscript_v13** — "at least as well as the strongest
  fitting-record baseline (station × horizon historical mean; pooled 0.945 vs
  0.942, network 0.805 vs 0.763; paired network difference +0.042 with CI
  spanning zero)". All four numbers verified here.
- **Figure 2** (figure_plan_v12: "rung 6 station × horizon mean, network
  0.763 on the 874; paired Δ +0.042") — verified; add the per-horizon r6
  series (0.938 / 0.915 / 0.843 / 0.603) alongside the empirical series
  (0.932 / 0.916 / 0.865 / 0.659) so the 90/180 d advantage is visible and
  the 7 d r6 edge is not hidden.
- **Manuscript panel composition sentence** — replace "35 US networks" with
  **32 US networks** (57 total = 32 US + 15 CZ + 10 NO; 224 stations;
  1,446 units). First panel: 42 networks, 219 stations, 1,440 units.
- **r6 as the primary same-unit baseline** — r6 is the strongest non-proposed
  rung on the direct-874 cell (network 0.763, pooled 0.942, R² 0.789,
  RMSE 0.484) and is collinear with the empirical predictor (Pearson 0.992),
  so it is the fairest strongest comparator; the empirical predictor beats it
  at the network level (+0.042, 97% of draws) and on pooled/R²/RMSE, with the
  CI's lower bound at −0.0004/−0.0006 (seed 42/0).

---

## 11. Limitations

- Bootstrap CIs cover resampling of the 57-/42-network panel only; the
  empirical transfer curve, the r6 means, and the simple coefficients are all
  frozen fitting-period quantities and are not re-estimated within draws.
- The relabeled-draw network bootstrap (t03 convention) treats duplicate
  network draws as distinct "networks" when computing network-level ρ; this
  inflates the effective number of network ranks per draw. It is kept
  bit-identical to the archived t03 procedure for reconciliation; CIs are
  still conservative coverage intervals for the panel-level ρ.
- The first-panel `horizon_group` is reconstructed with the t03 rule
  (`gap_length ∈ {7,30,90,180}`), not read from a column; this reproduces the
  t03 direct-858 count exactly (858), and all aggregate metrics reproduce the
  archived ladder table to machine precision, so the rule is the same.
- The first-panel surface row is the t04 confirmation-refit prediction, i.e.
  not a strict out-of-sample transfer object; it is reported as supplementary
  (as in t03/t04) and its superior first-panel numbers should not be read as
  evidence about the frozen surface.
- Full-panel (all 1,446 / 1,440) network-level comparisons favor r4/r6 over
  the empirical predictor because the empirical fallback rows are constant
  per network; the honest full-panel comparison is the r4 network-mean
  baseline (Δ −0.057 [−0.144, +0.007] vs empirical, t03), which this report
  does not alter.

---

## 12. Outputs (this directory)

| File | Contents |
|---|---|
| `analysis.py` | full pipeline (reproducible; seeds 0 and 42; no external writes) |
| `unit_comparison_second.csv` / `unit_comparison_first.csv` | per-unit tables (1,446 / 1,440 rows) |
| `summary_metrics.csv` | per panel/subset/method metrics (16 rows) |
| `paired_bootstrap.csv` | seed-42 paired bootstrap (8 rows) |
| `paired_bootstrap_seed0_verification.csv` | seed-0 control, matches t03 archive to 1e−16 |
| `per_horizon_network_spearman.csv` | 7/30/90/180 d network ρ for empirical/r6/simple |
| `predictor_correlation.csv` | Pearson + Spearman, empirical vs r6 / simple |
| `within_network_decomposition.csv` | network-demeaned ρ, within-network median/mean ρ |
| `panel_composition.csv` | networks/stations/units per panel and domain |
| `ladder_verification.csv` | 16-cell exact reproduction of `master_ladder_table.csv` |
| `verification_summary.json` | machine-readable verification flags |
