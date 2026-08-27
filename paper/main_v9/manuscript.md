# Pre-fit information risk for stream-temperature gap recoverability across unseen river networks

**Status:** draft skeleton — confirmatory sentences marked `[pending]`.

**Lineage:** `paper/main_v9/` · `configs/design_freeze_v10_executable.yaml` · not the v4 case study.

## Abstract

1. Monitoring outages remove weeks to months of stream-temperature records; recoverability depends on which temporal and network information remains, not on which imputer wins a leaderboard.
2. We propose a fitting-period Schur conditional-covariance operator that summarizes boundary memory, synchronous donor redundancy, and (when available) meteorological and hydraulic forcing before any recovery model is fit.
3. `[pending — 探索期数据，不可写入结论]` Whole-network splits across independent river networks; sealed confirmatory panel size and split hash.
4. `[pending]` Primary calibration of predicted risk against fixed-model recovery loss; incremental value versus gap length, ACF, donor R², and legacy heuristics.
5. `[pending]` Placement or triage utility at frozen management thresholds; failure boundaries if simple proxies suffice.

## 1. Introduction

### 1.1 Monitoring gaps destroy management-relevant thermal statistics

Long gaps in stream-temperature records bias annual means, seasonal amplitude, annual maxima, heat-wave duration, long-term trends, and exceedance days against ecological thresholds. Gap length, timing, and site hydrology type can change whether annual thermal state is preserved after imputation; groundwater-influenced sites may fare worse after gap filling than simpler reaches.

### 1.2 Research gap

Existing work asks whether a given method can fill a gap. Less work estimates, before model fitting, the information recoverability boundary for a specific network and outage geometry, or converts that estimate into backup-station design or safe-fill triage. Large-scale gap-filling benchmarks, spatial stream-network models, and monitoring-network design studies provide context but do not replace a pre-fit risk estimator tested on unseen whole networks.

### 1.3 Conceptual model

Recoverability depends on three information coalitions:

$$\text{local boundary memory} + \text{synchronous network redundancy} + \text{meteorological/hydraulic forcing}$$

**Predicted conditional risk** is computed from fitting-period covariances (Schur complement). **Actual recovery loss** is realized skill of a frozen recovery model on held-out gaps. Hard memory/donor type labels are descriptive only.

### 1.4 Falsifiable hypotheses

- **H1 (Predictability):** fitting-period conditional risk calibrates unseen-network recovery loss.
- **H2 (Incremental value):** the full operator adds out-of-network information beyond gap length, ACF, donor R², the legacy $d/4$ heuristic, and nearest-donor proxies.
- **H3 (Decision utility):** risk-based placement or triage beats the strongest preregistered non-oracle rule on sealed networks.

Regulation, groundwater, climate zone, and network size enter only as effect modifiers.

## 2. Methods

See `configs/design_freeze_v10_executable.yaml` for frozen primary gap horizon, loss, model roster, masks, thresholds, and evaluate-once ceremony.

Development context (not confirmatory): `paper/main_v9/results.md`.

## 3. Results

`[pending — sealed T7 not opened]`

Development stop-loss (n=44 public networks): network-level Spearman operator 0.67 vs donor R² 0.80. W8 incremental ΔR² vs donor R² only: \(6.88\times10^{-5}\). Placement: 2/10 rivers pass 15% worst-MAE gate. Triage at 5% false release: 0 safe fills for both operator and length-only rules.

## 4. Discussion

If sealed T7 confirms H1 but not H2–H3, the paper closes as **simple-proxy sufficiency**: synchronous network redundancy captures most predictable recoverability variation; the conditional-covariance operator adds little sealed-network value.

## 5. Conclusions

`[pending — 探索期数据，不可写入结论]`

If H2 fails on sealed data:

> A simple measure of synchronous network redundancy captured most of the predictable variation in stream-temperature recoverability; the more elaborate conditional-covariance operator added little sealed-network value.

## Data and code availability

Public USGS and catalog metadata in-repo. Sealed temperature bytes remain unopened until T7 evaluate-once. Software archival DOI: `[pending]`.
