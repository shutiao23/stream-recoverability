# REPORT — Support-hierarchy ablation for the empirical predictor (agent a)

Namespace: `results/revision_v12/t02_support_hierarchy/agent_a/`
Script: `scripts/rev_v12_t02_support_hierarchy_a.py` (run with `PYTHONPATH=$PWD/src python3 scripts/rev_v12_t02_support_hierarchy_a.py`)
All numbers below come from code run by this agent in this namespace. No git, no writes outside the namespace.

---

## 1. Key answer to the review question

On the second panel's 874 direct-horizon (7/30/90/180 d) units, the network-level
Spearman 0.805 is **overwhelmingly driven by exact station x duration x season
curves**, not by station-duration or network-duration fallbacks:

| Direct-horizon subset | Units | Networks | Network Spearman | Pooled Spearman |
|---|---|---|---|---|
| All 874 direct-horizon units | 874 | 57 | 0.8049 | 0.9453 |
| Exact local support (`station_gap_season`) | 841 (96.2%) | 57 | **0.8872** | 0.9681 |
| Station-duration fallback (`station_gap`) | 9 | 2 | −1.00 | −0.183 |
| Cross-duration fallback (`network_mean_fallback`) at direct horizons | 24 (4@90 d, 20@180 d) | 6 | 0.886 | — |
| All fallback-tier direct units (9 + 24) | 33 | 14 | 0.7857 | 0.6205 |

The exact tier alone reproduces and exceeds the headline 0.805 (0.887). The 33
fallback units are too few to drive the network rank. Note the manuscript's
"874 directly supported units" actually contains 24 units whose station had no
same-horizon curve and that used the network-mean fallback; and the manuscript's
"572 network-mean fallbacks" counts only horizon-unsupported units — 24
additional direct-horizon units also fall back to the network mean (596 total
`network_mean_fallback` units in the second panel).

## 2. Tier definitions and unit-level assignment

Tiers (most specific → least), identical to the builder in
`src/stream_recoverability/experiments/recovery_roster.py:277-363`
(`empirical_transfer_predictions`):

1. `station_gap_season` — exact station x gap x season fitting-period curve
2. `station_gap` — station x gap curve (season collapsed)
3. `network_gap` — network x gap curve (station collapsed)
4. `network_mean_fallback` — network-wide mean over all fitting-period losses
5. `unavailable` — no fitting-period support at all

**Unit-level rule (documented):** a station-gap unit has ~20 placements whose
individual sources can differ. We assign the **most-specific available source**
across the unit's placements and report mixing: 80/1446 second-panel units,
31/1440 first-panel units, 91/1460 development units mix `station_gap` with
`station_gap_season`; the remaining units are uniform. First- and
development-panel sources come from the stored per-placement
`empirical_transfer_source` columns
(`reviewer_completion/{confirmation,development}_empirical_predictions.csv`).

## 3. Second-panel source reconstruction (exact, not approximated)

`second_confirmation/scoring/empirical_predictions.csv` has no source column;
the pipeline (`scripts/131_run_second_confirmation.py:67-76`) dropped it in
`_empirical_summary`. We **re-ran the exact builder**: for all 57 scored
networks, `fitting_period_empirical_losses` (XGBoost, gaps 7/30/90/180, 20
placements per season) on the frozen second-panel daily QC panels
(`second_confirmation/daily_qc/networks/*/daily_wide_temperature.csv`, with the
same `panel_path` fallback to first-panel QC as the original script), using the
stored second-panel placement roster
(`second_confirmation/scoring/placement_losses.csv`, B_union_D), then
`empirical_transfer_predictions`. Regenerated 63,863 fit-loss rows
(`second_fit_losses.csv`, ~3.5 min wall with 8 workers).

**Verification against the frozen artifact:** all 1,446 units matched the
stored `empirical_predictions.csv`; max |Δprediction| = 4.4e-16; 100% within
1e-6 → reconstruction is exact (`reconstruction_verified: true`). No heuristic
approximation was needed. The gap-length shortcut (14/60/365 → network mean)
is nonetheless consistent: 572 units at unsupported horizons all fall to
`network_mean_fallback`.

## 4. Per-tier counts and performance

Pooled = station-gap Spearman; network = Spearman of network-mean
prediction/observed; within-network = mean per-network Spearman (networks with
≥3 units); calibration slope = network-weighted OLS of observed on predicted
(same weighting as `route_a_confirmation.point_prediction_metrics`).

### Second panel (57 networks, 1,446 units)
| Tier | Units | Networks | Pooled ρ | Network ρ | Within ρ | Cal slope | Pooled R² | Network R² |
|---|---|---|---|---|---|---|---|---|
| station_gap_season | 841 | 57 | 0.9681 | 0.8872 | 0.9585 | 0.973 | 0.895 | 0.837 |
| station_gap | 9 | 2 | −0.183 | −1.00 | 0.900 | −0.140 | −9.58 | −19.0 |
| network_gap | 0 | 0 | — | — | — | — | — | — |
| network_mean_fallback | 596 | 57 | 0.3387 | 0.5624 | n.d.* | 1.157 | −0.045 | −0.043 |
| **all** | **1,446** | **57** | **0.7399** | **0.7155** | **0.6952** | **0.950** | **0.238** | **0.294** |

*Within-network rank is undefined for fallback units (constant prediction within a network; 0 networks with ≥3 units).

### First panel (42 networks, 1,440 units)
| Tier | Units | Networks | Pooled ρ | Network ρ | Within ρ | Cal slope | Pooled R² | Network R² |
|---|---|---|---|---|---|---|---|---|
| station_gap_season | 673 | 42 | 0.9661 | 0.9537 | 0.9637 | 0.912 | 0.915 | 0.848 |
| station_gap | 0 | 0 | — | — | — | — | — | — |
| network_gap | 107 | 12 | 0.7924 | 0.8392 | 0.6999 | 0.614 | −0.047 | −0.328 |
| network_mean_fallback | 660 | 42 | 0.1830 | 0.5041 | n.d. | 0.693 | −0.139 | −0.479 |
| **all** | **1,440** | **42** | **0.6334** | **0.7666** | **0.6167** | **0.829** | **0.145** | **0.200** |

### Development (51 networks, 1,460 units with prediction; 88 all-unavailable units dropped)
| Tier | Units | Networks | Pooled ρ | Network ρ | Within ρ | Cal slope | Pooled R² | Network R² |
|---|---|---|---|---|---|---|---|---|
| station_gap_season | 635 | 51 | 0.9522 | 0.9113 | 0.8765 | 0.910 | 0.895 | 0.815 |
| station_gap | 5 | 1 | 0.300 | — | 0.300 | −0.276 | −4.05 | — |
| network_gap | 183 | 18 | 0.4143 | 0.1414 | 0.7342 | 0.420 | −0.740 | −3.87 |
| network_mean_fallback | 637 | 51 | 0.4745 | 0.6367 | 0.123 (3 nets) | 1.112 | 0.058 | 0.203 |
| **all** | **1,460** | **51** | **0.6805** | **0.7794** | **0.5925** | **0.898** | **0.239** | **0.547** |

Gap composition per tier (`tier_gap_composition_*.csv`):
- Second: exact 841 = 224@7, 224@30, 216@90, 177@180; station_gap 9@180;
  fallback 596 = 224@14, 224@60, 124@365 + 4@90 + 20@180.
- First: exact 673 = 184@7, 184@30, 178@90, 127@180; network_gap 107 =
  35@7, 35@30, 26@90, 11@180; fallback 660 = 219@14, 219@60, 144@365 +
  15@90 + 63@180.
- Development: exact 635; station_gap 5@90; network_gap 183; fallback 637 =
  254@14, 246@60, 70@365 + 31@90 + 36@180.

## 5. Support-aware uncertainty

Definitions (per placement, averaged to unit):
- **Effective support** = number of fitting-period placements in the curve cell
  the placement used (exact cell; station-gap cell; network-gap cell; network
  total as tier depth decreases).
- **Distance to nearest supported cell** = min over supported exact cells of
  `|gap − gap'| + 10·[season mismatch] + 100·[station mismatch]` (station match
  dominates; same-station, same-season cells always preferred).

### Rank terciles (ties split by row order; documented in script)
Second panel, all 1,446 units, terciles by distance:
| Group | Units | Distance range | Pooled ρ | Network ρ | Cal slope |
|---|---|---|---|---|---|
| t1 (closest) | 482 | 0 | 0.9708 | 0.9464 | 0.994 |
| t2 | 482 | 0–7 | 0.7784 | 0.8149 | 0.989 |
| t3 (farthest) | 482 | 7–275 | 0.3504 | 0.5078 | 0.811 |

Second panel, 874 direct units, terciles by effective support:
| Group | Units | Support range | Pooled ρ | Network ρ |
|---|---|---|---|---|
| t1 | 292 | 8.75–20 | 0.9533 | 0.9178 |
| t2 | 291 | 20 (full cell) | 0.9750 | 0.9234 |
| t3 | 291 | 20–960 | 0.9170 | 0.7286 |

Semantic support-quality groups (second panel):
- Distance: exact local (d=0, 761 units): network ρ 0.9309; station-level
  (0<d<100, 557 units): network ρ 0.6285; network-level (d≥100, 128 units):
  network ρ 0.7585.
- Effective support: full cell (734 units): network ρ 0.9203; partial cell
  (46 units): 0.8545; pooled cell (94 units): **0.5930**.

First panel behaves identically: exact-local 642 units network ρ 0.9511;
station-level 439 units 0.5480; network-level 359 units 0.4196; full-cell
direct 623 units 0.9506; pooled-cell direct 203 units 0.0934.

Interpretation: performance degrades monotonically as support moves away from
the exact station-season cell; units whose prediction pools several cells
(e.g., `network_gap`, or direct-horizon units without a same-horizon curve)
retain positive network rank but lose most of it.

## 6. Cross-checks (all reproduced)

| Check | Value |
|---|---|
| Second panel units / direct 874 / fallback 572 | 1,446 / 874 / 572 ✓ |
| Second panel network Spearman, all 1,446 | 0.7155 (paper 0.715) ✓ |
| Second panel direct 874 network / pooled | 0.8049 / 0.9453 (paper 0.805 / 0.945) ✓ |
| Second panel all-1446 pooled / cal slope | 0.7399 / 0.950 ✓ |
| First panel units / fallback units | 1,440 / 660 ✓ |
| First panel directly supported (exact+network_gap) | 673 + 107 = 780 (paper 780) ✓ |
| Development directly supported | 635 + 5 + 183 = 823 (paper 823) ✓ |
| Reconstruction vs frozen second artifact | max diff 4.4e-16, 1,446/1,446 ✓ |

## 7. Recommendation for the manuscript (renamed hierarchy)

Adopt a 5-level support hierarchy in place of the binary
supported/fallback split (paper §2.3):

1. **Exact local support** (`station_gap_season`) — 841 units, 58.2% of the
   second panel (673/46.7% first; 635/43.5% development). Network ρ 0.887
   second / 0.954 first / 0.911 development; pooled ρ ≈ 0.95-0.97; calibration
   slope ≈ 0.91-0.97; pooled R² ≈ 0.90. This tier carries the headline rank.
2. **Station-duration support** (`station_gap`) — 9 units (2 networks) second;
   5 units development. Too sparse to score; report count only.
3. **Network-duration support** (`network_gap`) — 0 second, 107 first (7.4%),
   183 development. Network ρ 0.839 first but 0.141 development; within-network
   ρ 0.70-0.73. Positive but unreliable rank; do not claim at network level.
4. **Cross-duration fallback** (`network_mean_fallback`) — 596 second (41.2%),
   660 first (45.8%), 637 development. Network ρ 0.562 / 0.504 / 0.637 but
   pooled ρ 0.34 / 0.18 / 0.47 and negative pooled R²; within-network rank
   undefined (constant per network). Report as descriptive only; the current
   manuscript sentence "572 network-mean fallbacks reduced these values to
   0.740, 0.715, and 0.950" should state 596 units (572 horizon-unsupported +
   24 direct-horizon) and per-tier numbers.
5. **Unavailable** — 0 units in scored panels (88 development units without
   prediction were dropped by the pipeline's `dropna`).

Suggested manuscript text: "At directly supported horizons the empirical
predictor reached network-level Spearman 0.805, driven by exact local
station-season curves (841/874 units, network Spearman 0.887); station- and
network-duration fallbacks contributed only 33 units. Extending the predictor
across all horizons with the cross-duration fallback reduced network Spearman
to 0.715 (596/1,446 units), where within-network ordering is undefined by
construction."

## 8. Artifacts

- `scripts/rev_v12_t02_support_hierarchy_a.py`
- `results/revision_v12/t02_support_hierarchy/agent_a/second_fit_losses.csv` (63,863 regenerated fit-loss rows)
- `second_placement_sources.csv` (28,557 per-placement reconstructed sources)
- `second_unit_tiers.csv`, `first_unit_tiers.csv`, `development_unit_tiers.csv` (unit-level tier + support quality)
- `tier_metrics_{second,first,development}.csv`, `tier_gap_composition_{second,first,development}.csv`
- `key_decomposition.json`, `crosschecks.json`, `mixing_diagnostics.json`, `support_quality_terciles.csv`, `renamed_hierarchy.csv`, `analysis_results.json`
- `REPORT.md`

Runtime: phase 1 (fit-loss regeneration) ~3.5 min with 8 workers; full run
< 6 min on CPU only. Results reproduce the frozen second-panel artifact to
4.4e-16 and agree with the independent agent_b analysis in the sibling
namespace.
