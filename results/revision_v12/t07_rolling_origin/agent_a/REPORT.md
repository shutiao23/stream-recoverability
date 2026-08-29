# Revision v12, task 07 (agent a): rolling-origin stability, history-length learning curve, training-data comparability

**Date:** 2026-08-28
**Script:** `scripts/rev_v12_t07_rolling_origin_a.py`
**Namespace:** `results/revision_v12/t07_rolling_origin/agent_a/`
**Panels:** first confirmation panel (`results/development_v11/route_a_confirmation`, 42 networks) and development panel (51 networks); subsets of ≤ 20 networks per analysis.

All machinery is reused from the frozen v11 empirical-transfer pipeline (`stream_recoverability.experiments.recovery_roster`: `fitting_period_empirical_losses` / `empirical_transfer_predictions`) and the frozen fit-losses tables in `results/development_v11/reviewer_completion/` (which carry `inner_fit_years` / `inner_score_years`). Every number below was produced by the script from the data; nothing is fabricated.

---

## 0. Cross-checks (all pass exactly)

| Check | Expected | Reproduced |
|---|---|---|
| First panel, canonical 70% split, supported cells (frozen table, 20 placements/season) | 780 units; pooled Spearman 0.9341049; network Spearman 0.9218864; calibration slope 0.8635905 | 780; 0.9341049; 0.9218864; 0.8635905 — bit-identical |
| First panel, complete-cell set (network-mean fallback included) | network Spearman 0.7666316 | 0.7666316 |
| Development panel, canonical 70% (frozen table) | 823 units; pooled 0.8179; network 0.7871; slope 0.8562 | 823; 0.8179; 0.7871; 0.8562 |

Stored in `manifest.json` → `cross_checks` (all `match: true`).

---

## 1. Rolling-origin evaluation (3 outer chronological cutoffs)

**Design.** For cutoff f ∈ {0.6, 0.7, 0.8}: outer split of panel years at f (first f·100% train, remainder evaluate); the stress curve is built strictly inside the training block with the canonical inner 70/30 split (fit first 70% of training years, score artificial gaps in the remaining 30%), then transferred to the placements whose gap starts fall in the later years of the same panel. Network-level Spearman, weighted calibration slope (network-count weights), and R² are reported on supported station-gap cells (curve-matched cells; the same scope as the canonical headline). New stress-curve builds use 10 placements/season (frozen tables: 20); the agreement of the two conventions is quantified in §3 (network-level rank Spearman 0.974), so cutoffs are comparable.

**Per-cutoff results (first panel, supported cells):**

| Cutoff | Eval years (avg share) | n units | n networks | Pooled Spearman | Network Spearman | Cal. slope | R² |
|---|---|---|---|---|---|---|---|
| 60% | last 40% | 324 | 14 | 0.947 | 0.947 | 0.895 | 0.875 |
| 70% | last 30% | 502 | 20 | 0.908 | 0.922 | 0.734 | 0.743 |
| 80% | last 20% | 549 | 20 | 0.927 | 0.949 | 0.869 | 0.852 |
| 70% (frozen table, subset 20) | — | 502 | 20 | 0.915 | 0.962 | 0.721 | 0.735 |
| 70% (frozen table, all 42, canonical) | — | 780 | 42 | 0.934 | 0.922 | 0.864 | 0.812 |

Network-level Spearman is 0.92–0.95 across all three cutoffs — the ranking claim is stable under the choice of cutoff. Calibration slope is 0.73–0.89 (always below 1, i.e., predicted loss compresses realized loss; see §3).

**Attrition at the 60% cutoff (a substantive finding).** 6 of 20 networks (gkd_bayern_alz, gkd_bayern_donau, gkd_bayern_main, gkd_bayern_vils, huc8_17090004, lubw_neckar) produce **zero** feasible stress curves at 60%: moving the outer cutoff to 60% shifts the artificial-gap score window to years (e.g., 2000–2007 for gkd, 2011–2015 for huc8_17090004) that precede the start of the current station/donor rosters, and the machinery requires every donor to be complete across each gap window. The 60% evaluation therefore rests on 14 networks with shorter records; this is honest rolling-origin attrition, not a modeling failure, but it limits the 60% leg.

**Rank stability across cutoffs** (14 networks present at all three cutoffs; ranks = per-network mean predicted loss; rank 1 = lowest predicted loss):
- Kendall's W = **0.917**
- Mean pairwise Spearman of predicted network ranks = **0.875** (min 0.824; 60-vs-70 = 0.974, 60-vs-80 = 0.824, 70-vs-80 = 0.829)
- Mean pairwise Kendall τ = 0.751 (0.67–0.89)

The predicted network ordering is largely stable as the training/evaluation windows roll forward; the largest disagreement is between the two extreme cutoffs (60 vs 80), driven by the 6-network attrition and the changing network roster.

---

## 2. History-length learning curve

**Design.** For each of 12 first-panel + 12 development networks (longest records, all lengths feasible): the stress model is fit on the first 2/4/6/8 years of the panel record, artificial gaps are scored in the *same* canonical inner score years (fixed evaluation-window design, isolating fit length), and curves are transferred to the canonical outer placements. "full" = the frozen canonical table (inner 70% of the training block, per network ~4–29 fit years). Metrics on supported cells, aggregated over the networks present.

**First panel (12 networks, n=350 cells at every length):**

| History (y) | Network Spearman | Pooled Spearman | Cal. slope | R² |
|---|---|---|---|---|
| 2 | 0.678 | 0.687 | 0.443 | −0.50 |
| 4 | 0.881 | 0.809 | 0.608 | 0.53 |
| 6 | 0.930 | 0.829 | 0.606 | 0.55 |
| 8 | 0.951 | 0.834 | 0.641 | 0.61 |
| full | 0.965 | 0.893 | 0.643 | 0.69 |

**Development (12 networks):** 2y: 0.345 (n=189, 10 networks), 4y: 0.364, 6y: 0.503, 8y: 0.608, full (12-net subset): 0.580; the full 51-network development panel reaches 0.787 (canonical).

**Headline (min history for usable ranking, network Spearman ≥ 0.7):**
- **First panel: 4 years** (0.881 ≥ 0.7 at 4y; 0.678 at 2y; 8y ≈ full).
- **Development: not reached on the 12-network subset** (max 0.608 at 8y; the subset is all long-record US huc8 networks — a harder, more homogeneous ranking problem). The canonical full-length curve reaches 0.787 network Spearman on all 51 networks, so the dev panel's shortfall at short histories is partly selection, partly a genuine lower plateau.

Files: `learning_curve_metrics.csv`, `learning_curve_predictions.csv`, `learning_curve.png` (network Spearman and calibration slope vs history length, dashed lines = full-length reference).

---

## 3. Training-data comparability (stress model ~49% of record vs deployment 70%)

**Design (canonical 70% split, 20 first-panel networks).** The deployed recovery model trains on the first 70% of the record; the frozen stress curve trains on 49% (70% of the 70% training block) and is scored in the middle 21% block. "Matched" stress curves were built with the *full* 70% training block (deployment-equal length) and artificial gaps scored in the outer evaluation window on starts that are disjoint from the actual scored placements (so the curve never uses the evaluation placements' own outcomes). All matched/unmatched comparisons below are on the same 502 supported cells / 20 networks.

| Metric (unit level, supported cells) | Unmatched (49% length) | Matched (70% length) |
|---|---|---|
| Pooled Spearman | 0.908 | 0.985 |
| Network Spearman | 0.922 | 0.982 |
| Calibration slope | 0.734 | 1.008 |
| Calibration intercept | 0.177 | −0.006 |
| R² | 0.743 | 0.983 |
| RMSE (°C) | 0.391 | 0.100 |

Prediction agreement between the two curves: network-level Spearman 0.940, Pearson 0.875; pooled Spearman 0.908; mean |Δ| at network level 0.135 °C (max 0.887); 10% of networks move >3 rank positions (max 6 of 20).

**Finding.** The ~49%-vs-70% training-length gap explains essentially all of the stress curve's magnitude under-calibration: with deployment-equal training length the curve is calibrated (slope 1.01, intercept ≈ 0, RMSE 0.10) instead of compressed (slope 0.73). Ranking conclusions change only mildly: network Spearman rises from 0.92 to 0.98 and the two curves' network rankings correlate at 0.94 (only 2 of 20 networks move more than 3 positions). **Conclusion: the length gap does not overturn the paper's ranking claim, but it does mean the stress curve's loss magnitudes are conservative (compressed) relative to deployment; recalibration before use in magnitude-based triage is warranted.** The matched curve is a diagnostic only — it requires the evaluation window and cannot replace the pre-evaluation stress curve.

**Placement-count convention (20 vs 10 per season) is not a confound:** frozen (20/season) vs rebuilt (10/season) curves at the same 49% length agree at pooled Spearman 0.995 and network-level 0.974.

Files: `comparability_summary.csv`, `comparability_network_level.csv`, `comparability_cutoff_metrics.csv`, `comparability_matched_predictions.csv`, `comparability_unmatched_predictions.csv`.

---

## 4. Outputs

| File | Contents |
|---|---|
| `rolling_origin_metrics.csv` | per-cutoff × scope × curve-source metrics (all rows incl. canonical) |
| `rolling_metrics_subset_cutoff_{60,70,80}.csv` | subset-20 per-cutoff metrics |
| `rolling_predictions_cutoff_{60,70,80}.csv` | unit-level predictions per cutoff (subset rebuilds) |
| `rolling_predictions_cutoff_70_frozen_all42.csv` | canonical 70% unit-level predictions (all 42) |
| `rolling_origin_network_ranks.csv` | per-network predicted-loss ranks per cutoff (14 complete networks) |
| `rolling_origin_rank_stability.csv` | Kendall's W, pairwise Spearman/Kendall-τ |
| `learning_curve_metrics.csv`, `learning_curve_predictions.csv`, `learning_curve.png` | history-length learning curve |
| `comparability_*.csv` | matched-vs-unmatched analysis |
| `fit_losses_cutoff_{60,80}.csv`, `fit_losses_cutoff_70_subset.csv`, `fit_losses_matched_70.csv`, `learning_fit_losses_*_Ny.csv` | regenerable stress-curve tables (cache) |
| `manifest.json` | subsets, design notes, cross-checks, headline |
| `REPORT.md` | this report |

## 5. Caveats

1. New stress-curve builds use 10 artificial placements per season-gap cell (frozen tables: 20); agreement quantified (§3, 0.974 network-level) and labeled `curve_source` in every table.
2. The 60% leg attrites 6/20 networks (donor-completeness infeasibility in the earlier score window); rank stability is computed on the 14 complete networks and the attrition is reported, not hidden.
3. Development learning-curve short histories rest on fewer networks (10 of 12 at 2y) and the 12-network subset is all long-record huc8 networks; the 51-network canonical full-length dev curve (0.787) is the better reference for the dev panel.
4. The "matched" comparability curve scores artificial gaps inside the outer evaluation window (disjoint starts); it quantifies the training-length gap and is not a deployable alternative to the pre-evaluation stress curve.
5. Runtime budget respected (≈25 min per run; script caches per-network fit-loss tables for resumability).
