# Strongest-Baseline Harmonization Analysis — agent_a

**Task**: definitive empirical-vs-strongest-fair-baseline comparison for the WRR revision.
The strongest fair baseline is the **station × horizon historical mean of fitting-period MAE**
(t03 ladder rung `r6_station_gap`), which matches the proposed method's information access
(observed recovery losses on the same stations/horizons during the fitting period) and is the
strongest non-proposed rung on the direct subset.

**Agent**: sbase_a (adversarial pair — sibling sbase_b runs the same analysis independently;
a senior reviewer reconciles). All code, inputs, and outputs are in this directory.
Runtime: ~2 minutes.

---

## 1. Inputs (read-only)

| File | Contents |
|---|---|
| `results/revision_v12/t01_paired_comparison/agent_a/predictions.csv` | 1,446 second-panel rows; empirical transfer predictions, observed loss, simple fit-period, horizon_group |
| `results/revision_v12/t03_baseline_ladder/agent_a/unit_predictions_second.csv` | same rows + per-unit rungs incl. `r6_station_gap`, `surface_prediction_mae` |
| `results/revision_v12/t03_baseline_ladder/agent_a/unit_predictions_first.csv` | 1,440 first-panel rows (no `horizon_group`; has `r8_simple`, `surface_prediction_mae`, `r6_station_gap`) |
| `results/revision_v12/t03_baseline_ladder/agent_a/master_ladder_table.csv` | aggregate rungs per panel/subset (verification target) |
| `results/revision_v12/t01_paired_comparison/agent_a/paired_bootstrap.csv` | empirical-vs-r6 paired bootstrap (seed 0) — verification target |

**Input consistency checks (all passed):**
- t01 and t03 second-panel files are identical on `network_id/station_id/gap_length` and agree exactly
  (to float precision) on `empirical_transfer_prediction`, `observed_recovery_loss`, `simple_fitperiod`.
- `r8_simple == simple_fitperiod`, `r11_surface == surface_prediction_mae`,
  `empirical == empirical_transfer_prediction` in both panel files (exact).
- Second panel: `horizon_group` column equals the rule `gap_length ∈ {7,30,90,180} → direct` (874 rows) — used as given.
- First panel: no `horizon_group`; derived with the **same rule** → 858 direct / 582 fallback, 42 networks
  (matches `first_direct_858` / `first_all_1440` in the master ladder; 219+219+219+201 = 858).

**Method column mapping** (`unit_comparison_*.csv` / `summary_metrics.csv`):
`empirical` = `empirical_transfer_prediction`; `r6` = `r6_station_gap`; `simple` = `simple_fitperiod`
(second panel; identical to `r8_simple`) / `r8_simple` (first panel); `surface` = `surface_prediction_mae`.

**Metric definitions** (identical to `scripts/rev_v12_t01_paired_comparison_a.py` / `rev_v12_t03_baseline_ladder_a.py`,
so numbers are directly comparable with v12 artifacts):
- `pooled_spearman` — Spearman ρ between prediction and observed over all units in the cell.
- `network_spearman` — Spearman ρ over network means (mean prediction vs mean observed per network).
- `network_mean_only_pooled` — control: Spearman ρ between the **network mean of observed loss** (assigned to
  each unit) and unit-level observed loss (t01 `within_network_decomposition` definition; constant within a cell).
  `netmean_pred_only_pooled` — supplementary per-method control: Spearman ρ between network-mean *prediction*
  (assigned to each unit) and unit-level observed loss (between-network-only skill).
- `calibration_slope`/`calibration_intercept` — equal-network-weighted OLS (weight = 1/√(units per network),
  intercept included; `np.linalg.lstsq`), same routine as the route-A fit.
- `r2` — sklearn `r2_score` equivalent: 1 − Σ(y−ŷ)² / Σ(y−ȳ)² at unit level (unweighted).
- `rmse` — unit-level √mean((ŷ−y)²).
- Within-network ρ — Spearman per network (≥4 units, constant pred/obs skipped); median/mean across networks.
- Network-demeaned pooled ρ — Spearman on (pred − network-mean pred) vs (obs − network-mean obs).
- Paired bootstrap — network-cluster resampling: sample 57 (or 42) networks with replacement, relabel each
  occurrence as a distinct cluster (`draw_N`), compute both predictors' metrics on the same resampled units.
  Levels: `pooled` (station-gap level) and `network`; 95% percentile CI; win fraction = share of draws with Δρ>0.
- **All resampling: `np.random.default_rng(42)` (2,000 draws).** The v12 reference scripts used seed 0; a
  seed-0 verification run is included (`paired_bootstrap_seed0_verification.csv`) and matches v12 exactly.

---

## 2. Summary metrics (all four cells)

`summary_metrics.csv`. Values verified **exact** (1e-9 tolerance) against
`master_ladder_table.csv` for all 16 rows (see `master_ladder_verification.csv`, all True).

| panel | subset | method | pooled ρ | network ρ | slope | intercept | R² | RMSE |
|---|---|---|---|---|---|---|---|---|
| second | direct_874 | **empirical** | **0.9453** | **0.8049** | 0.9383 | 0.1383 | 0.8132 | 0.4553 |
| second | direct_874 | **r6** | 0.9424 | 0.7632 | 0.9235 | 0.1670 | 0.7893 | 0.4836 |
| second | direct_874 | simple | 0.8459 | 0.2475 | 1.1571 | −0.0465 | 0.6477 | 0.6254 |
| second | direct_874 | surface | 0.8979 | 0.6887 | 1.3258 | −0.1886 | 0.6563 | 0.6177 |
| second | all_1446 | empirical | 0.7399 | 0.7155 | 0.9503 | 0.2862 | 0.2385 | 1.3201 |
| second | all_1446 | r6 | 0.7353 | **0.7256** | 0.9385 | 0.3077 | 0.2315 | 1.3262 |
| second | all_1446 | simple | 0.8346 | 0.6046 | 1.1503 | −0.0548 | 0.7564 | 0.7466 |
| second | all_1446 | surface | 0.8928 | 0.6744 | 1.7297 | −0.5085 | 0.4753 | 1.0958 |
| first | direct_858 | **empirical** | 0.8254 | **0.8005** | 0.8313 | 0.1995 | 0.5591 | 0.5890 |
| first | direct_858 | **r6** | 0.8250 | 0.7984 | 0.8410 | 0.1897 | 0.5613 | 0.5876 |
| first | direct_858 | simple | 0.7916 | 0.4846 | 0.9041 | −0.0766 | 0.5199 | 0.6147 |
| first | direct_858 | surface | 0.9103 | 0.8704 | 1.2309 | −0.1853 | 0.7456 | 0.4475 |
| first | all_1440 | empirical | 0.6334 | 0.7666 | 0.8291 | 0.3937 | 0.1446 | 1.1564 |
| first | all_1440 | r6 | 0.6330 | **0.7793** | 0.8399 | 0.3827 | 0.1453 | 1.1560 |
| first | all_1440 | simple | 0.8027 | 0.5626 | 0.8063 | 0.0184 | 0.6027 | 0.7881 |
| first | all_1440 | surface | 0.9080 | 0.8984 | 1.5584 | −0.4506 | 0.6794 | 0.7079 |

Controls (`network_mean_only_pooled`, observed-structure control): second direct_874 **0.3257**,
second all_1446 **0.3091**, first direct_858 **0.3496**, first all_1440 **0.3607** — i.e., the pooled ρ
values (0.94) are far above what between-network mean structure alone can explain. Per-method
between-network-only controls (`netmean_pred_only_pooled`): empirical 0.2836 / r6 0.2807 on
second direct_874 — the two predictors carry virtually identical between-network signal.

Notes: (i) r6's network ρ equals r5's by construction (station means averaged within network × horizon);
(ii) on the **first** panel the t04 surface (refit) is stronger than empirical at all levels (0.9103/0.8704) —
it is not a fitting-period baseline and is out of scope for the strongest-*fair*-baseline claim; (iii) the
empirical-vs-r6 ranking inverts at the network level on the **full** panels (all_1446 / all_1440: r6 0.7256 >
empirical 0.7155; r6 0.7793 > empirical 0.7666) — the empirical advantage is specific to the directly
supported horizons (see §4).

---

## 3. Paired network bootstrap, empirical − r6 (2,000 draws)

`paired_bootstrap.csv` (official, seed 42).

| panel | subset | level | Δρ mean | 95% CI | P(Δρ>0) | ρ̂_emp boot | ρ̂_r6 boot |
|---|---|---|---|---|---|---|---|
| second | direct_874 | pooled | +0.00283 | [−0.00045, +0.00656] | 0.9505 | 0.94469 | 0.94187 |
| second | direct_874 | **network** | **+0.04123** | **[−0.00039, +0.11399]** | **0.9705** | 0.79744 | 0.75621 |
| second | all_1446 | pooled | +0.00449 | [+0.00103, +0.00880] | 0.9960 | 0.73909 | 0.73460 |
| second | all_1446 | network | −0.01101 | [−0.03556, +0.00786] | 0.1295 | 0.71120 | 0.72221 |
| first | direct_858 | pooled | +0.00019 | [−0.00372, +0.00385] | 0.5605 | 0.82674 | 0.82655 |
| first | direct_858 | **network** | **+0.00245** | **[−0.02369, +0.02745]** | **0.5995** | 0.78834 | 0.78589 |
| first | all_1440 | pooled | +0.00029 | [−0.00239, +0.00282] | 0.5965 | 0.63246 | 0.63217 |
| first | all_1440 | network | −0.01184 | [−0.04529, +0.00861] | 0.1650 | 0.75283 | 0.76467 |

Interpretation:
- **Headline (second, direct_874, network level):** Δρ = +0.041, CI [−0.0004, +0.1140]; the CI lower bound is
  marginally negative, and the empirical predictor beats r6 in **97.05 %** of draws. This is the correct wording
  for the manuscript/claim matrix: "positive in 97% of bootstrap draws", *not* "CI excludes zero".
- The pooled-level advantage (+0.0028) is small but positive in 95.05 % of draws; note the pooled ρ difference is
  driven by within-(network × horizon) station rank order, where r6 is the station mean of the same units.
- On the full panels the network-level Δρ is negative (r6 wins in 87 % / 84 % of draws) — the empirical
  advantage over the station × horizon mean is confined to the direct-horizon subset. Any manuscript claim must
  scope the claim to direct units.
- First panel: Δρ ≈ 0 at both levels (win fraction ≈ 0.56–0.60) — consistent with the review's +0.0024.

**Verification vs v12 (seed 0, `paired_bootstrap_seed0_verification.csv`):** identical to
`t01_paired_comparison/agent_a/paired_bootstrap.csv` to 5 decimals in every cell (e.g., second direct_874
network: ours 0.04175 [−0.00059, 0.11543] vs t01 0.041749 [−0.000588, 0.115431]; first direct_858 network:
ours 0.00244 [−0.02388, 0.02616] vs t01 0.002444 [−0.023881, 0.026164]). Seed-42 vs seed-0 differences are
pure Monte-Carlo noise (≤ 0.0015 on CI endpoints).

**Median within-network Spearman on direct subsets** (see §5): empirical 0.9650 vs r6 0.9676 (second);
0.9588 vs 0.9510 (first). The within-network levels are statistically indistinguishable; the empirical
advantage is at the between-network level.

---

## 4. Per-horizon network Spearman (second panel, direct horizons)

`per_horizon_network_spearman.csv` (matches t01's empirical column exactly: 0.9321 / 0.9157 / 0.8648 / 0.6594).

| horizon | n_units | n_networks | empirical | r6 | simple |
|---|---|---|---|---|---|
| 7 d | 224 | 57 | 0.9321 | **0.9384** | 0.3744 |
| 30 d | 224 | 57 | **0.9157** | 0.9154 | 0.1530 |
| 90 d | 220 | 56 | **0.8648** | 0.8435 | 0.0429 |
| 180 d | 206 | 53 | **0.6594** | 0.6035 | 0.1640 |

The empirical advantage over r6 grows with horizon: −0.006 at 7 d (r6 ahead), +0.000 at 30 d,
**+0.021** at 90 d, **+0.056** at 180 d. Simple descriptors are far behind at every horizon.
Recommended manuscript framing: "advantage concentrated at 90–180 d".

---

## 5. Predictor correlations

`predictor_correlation.csv`.

| panel | subset | corr(emp, r6) Spearman | corr(emp, r6) Pearson | corr(emp, simple) Spearman | corr(emp, simple) Pearson |
|---|---|---|---|---|---|
| second | direct_874 | 0.9959 | **0.9917** | 0.8010 | 0.7643 |
| second | all_1446 | 0.9958 | 0.9923 | 0.6053 | 0.3927 |
| first | direct_858 | 0.9976 | 0.9948 | 0.6210 | 0.5895 |
| first | all_1440 | 0.9983 | 0.9954 | 0.4225 | 0.2661 |

The review's "predictor correlation ≈0.992" corresponds to the **Pearson** correlation on second direct_874
(0.9917 → 0.992); the Spearman (rank) correlation is 0.9959. If the manuscript intends rank correlation,
the value should read ≈0.996. The empirical predictor and r6 are near-collinear by design (both summarize
observed fitting-period losses), which is precisely why the fair comparison rests on the paired
same-unit bootstrap rather than pooled differences.

---

## 6. Within-network decomposition (direct subsets)

`within_network_decomposition.csv`. Empirical values on second direct_874 reproduce the review's
"0.936 / 0.965": network-demeaned pooled ρ **0.9359**, median within-network ρ **0.9650**.

| panel | subset | method | network-demeaned pooled ρ | median within ρ | mean within ρ | n networks defined |
|---|---|---|---|---|---|---|
| second | direct_874 | empirical | 0.9359 | 0.9650 | 0.9295 | 57 |
| second | direct_874 | r6 | 0.9298 | 0.9676 | 0.9335 | 57 |
| second | direct_874 | simple | 0.8958 | 0.9371 | 0.9110 | 57 |
| second | direct_874 | surface | 0.9034 | 0.9510 | 0.9140 | 57 |
| first | direct_858 | empirical | 0.8015 | 0.9588 | 0.8774 | 42 |
| first | direct_858 | r6 | 0.8002 | 0.9510 | 0.8784 | 42 |
| first | direct_858 | simple | 0.8494 | 0.9063 | 0.8686 | 42 |
| first | direct_858 | surface | 0.9055 | 0.9599 | 0.9317 | 42 |

After removing between-network mean differences, empirical (0.9359) and r6 (0.9298) are near-identical
in pooled within-network rank order; the empirical advantage is a **between-network** phenomenon
(+0.042 network-level Δρ with a 0.97 win fraction, §3). Within-network median ρ is slightly in r6's favor
on the second panel (0.9676 vs 0.9650) and in empirical's favor on the first panel (0.9588 vs 0.9510) —
differences are not statistically separable.

---

## 7. Panel composition (corrected counts)

`panel_composition.csv`. Both CSVs (t01 and t03) agree exactly on all network counts.

| panel | domain | n_networks | n_stations | n_units (all) | n_units (direct) |
|---|---|---|---|---|---|
| second | united_states (USGS) | **32** | 114 | 703 | 434 |
| second | czechia (CHMI) | 15 | 69 | 478 | 276 |
| second | norway (NVE) | 10 | 41 | 265 | 164 |
| second | **TOTAL** | **57** | **224** | **1446** | **874** |
| first | united_states (USGS) | 17 | 95 | 583 | 362 |
| first | germany (GKD/LUBW) | 11 | 65 | 444 | 260 |
| first | slovenia (ARSO) | 12 | 47 | 329 | 188 |
| first | switzerland (FOEN) | 1 | 9 | 63 | 36 |
| first | netherlands (RWS) | 1 | 3 | 21 | 12 |
| first | **TOTAL** | **42** | **219** | **1440** | **858** |

**This fixes the manuscript's "35 US" bug:** the second panel contains **32** US (USGS) networks,
not 35. Both independent input CSVs give 32. First panel: 17 US networks, 25 European (11 DE, 12 SI,
1 CH, 1 NL).

---

## 8. Discrepancy log — review quotes vs artifact-derived values

| # | Review quote | Artifact-derived value | Resolution |
|---|---|---|---|
| 1 | direct-874 pooled 0.945 vs 0.942 | 0.9453 (empirical) vs 0.9424 (r6) | **Confirmed**, 4 decimals. |
| 2 | network 0.805 vs 0.763 | 0.8049 vs 0.7632 | **Confirmed** (r6 network ρ = r5's, 0.7632, by construction). |
| 3 | paired network Δρ +0.042 (CI [−0.0006, +0.1154]) | seed-0 reproduction: +0.04175 [−0.00059, +0.11543] (exact match to t01); official seed-42: **+0.04123 [−0.00039, +0.11399]** | **Confirmed**; MC noise between seeds ≤0.0015 on CI endpoints. CI lower bound is marginally negative in both seeds; win fraction 0.9705 — phrase as "positive in 97.0% of draws". |
| 4 | first-panel Δρ +0.0024 | +0.00244 (seed 0) / +0.00245 (seed 42), CI [−0.0237, +0.0275], win 0.60 | **Confirmed**. |
| 5 | predictor correlation ≈0.992 | Pearson **0.9917**; Spearman 0.9959 (second direct_874) | **Refined**: 0.992 is the Pearson value; if rank correlation is intended, use 0.996. |
| 6 | empirical 0.936/0.965 (within-network) | network-demeaned pooled 0.9359; median within-network 0.9650 (second direct_874) | **Confirmed**; r6: 0.9298 / 0.9676. |
| 7 | (implicit) "35 US" networks | **32** US networks in second panel (t01 and t03 agree); first panel has 17 US | **Corrected**: 57 = 32 US + 15 CZ + 10 NO. |
| 8 | — (not quoted by review) | second all_1446 network-level Δρ = **−0.01101** (CI [−0.0356, +0.0079], win 0.1295); first all_1440 network Δρ = −0.01184 (win 0.165) | **New**: the empirical advantage over r6 is confined to the direct-horizon subset; full-panel network-level ranking favors r6. Must be scoped in the claim matrix. |
| 9 | — (not quoted) | per-horizon network ρ: r6 ahead at 7 d (0.9384 vs 0.9321), empirical ahead at 90 d (+0.021) and 180 d (+0.056) | **New**: advantage concentrated at 90–180 d. |
| 10 | — (not quoted) | first-panel surface (t04 refit) exceeds empirical at all levels (pooled 0.9103 vs 0.8254; network 0.8704 vs 0.8005) | **New / caveat**: surface is not a fitting-period baseline; out of scope for the strongest-fair-baseline claim, but must be disclosed for the first panel (already flagged in t03). |

---

## 9. Which values feed the manuscript deliverables

- **Figure 2** (network-level comparison): network ρ empirical 0.8049 vs r6 0.7632 (second direct_874);
  per-horizon network ρ table (§4: 7 d 0.9321/0.9384, 30 d 0.9157/0.9154, 90 d 0.8648/0.8435,
  180 d 0.6594/0.6035); optional panel-composition annotations (57 = 32+15+10).
- **Abstract**: pooled 0.945 vs 0.942; network 0.805 vs 0.763; paired Δρ **+0.041** (CI [−0.0004, +0.1140],
  P(Δ>0) = 0.9705) on direct-874; first-panel Δρ +0.0024 (CI [−0.0237, +0.0275]); predictor correlation
  0.992 (Pearson; 0.996 Spearman — state which).
- **claim_matrix_v13**: use `paired_bootstrap.csv` (seed 42) — rows for second direct_874 (network +0.04123,
  CI [−0.00039, +0.11399], win 0.9705), second all_1446 (network −0.01101, win 0.1295 — scope the claim to
  direct units), first direct_858 (+0.00245, win 0.5995), first all_1440 (−0.01184, win 0.1650);
  `summary_metrics.csv` for all point estimates; `within_network_decomposition.csv` for the 0.936/0.965
  decomposition claims; `predictor_correlation.csv` for the near-collinearity disclosure.
- **manuscript_v13**: `panel_composition.csv` (fixes "35 US" → 32 US; 57 = 32+15+10; first 42 = 17+11+12+1+1;
  224/219 stations; 1446/1440 units); per-horizon table (§4) with the "advantage at 90–180 d" framing; the
  full-panel network-level inversion (§3) as a scoping caveat.

---

## 10. Reproducibility

- Run: `python3 analysis.py` from this directory (or any CWD; paths are absolute to the repo root).
- Deterministic: all resampling via `np.random.default_rng(42)` (official) and seed 0 (verification only);
  no file writes outside this directory; no modifications to any input; no git operations; no model training.
- Pipeline verification: `master_ladder_verification.csv` (16/16 rows exact vs v12 master ladder) and
  `paired_bootstrap_seed0_verification.csv` (exact vs v12 t01 paired bootstrap) are written alongside the
  outputs; `verification_summary.json` bundles both.
