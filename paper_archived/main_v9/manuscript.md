# Pre-fit information risk for stream-temperature gap recoverability across unseen river networks

**Status:** non-submittable draft skeleton — the evaluate-once QC gate failed
before confirmatory scoring.

**Lineage:** `paper/main_v9/` · `configs/design_freeze_v10_executable.yaml` · not the v4 case study.

## Abstract

1. Monitoring outages remove weeks to months of stream-temperature records; recoverability depends on which temporal and network information remains, not on which imputer wins a leaderboard.
2. We propose a fitting-period Schur conditional-covariance operator that summarizes boundary memory, synchronous donor redundancy, and (when available) meteorological and hydraulic forcing before any recovery model is fit.
3. Evaluate-once QC retained 32 sealed networks (29 HUC8 and 3 FOEN), below the preregistered floor of 40; confirmatory recovery scoring was not performed.
4. Consequently, primary calibration, incremental value, and decision utility remain untested in this lineage.
5. Development results favor donor R² over the full operator and do not license a transferable or operational claim.

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

The evaluate-once ceremony read all 2,880 registered sealed objects for the
predeclared QC step. Thirty-two networks passed QC (29 HUC8 and 3 FOEN), fewer
than the sealed absolute floor of 40. The production authorization is consumed;
the fixed-model confirmatory scorer was not run and no confirmatory recovery
loss, calibration, rank correlation, or decision-utility result exists.

Development stop-loss (n=44 public networks): network-level Spearman operator 0.67 vs donor R² 0.80. W8 incremental ΔR² vs donor R² only: \(6.88\times10^{-5}\). Placement: 2/10 rivers pass 15% worst-MAE gate. Triage at 5% false release: 0 safe fills for both operator and length-only rules.

## 4. Discussion

The locked study did not reach the sample-size gate required to test H1–H3.
Development evidence is compatible with **simple-proxy sufficiency**, but this
interpretation is not a sealed-network conclusion.

## 5. Conclusions

The current lineage supports no confirmatory conclusion: sealed QC attrition
left too few networks to run the preregistered test. Development analyses show
that donor R² can outperform the more elaborate operator, motivating a future,
newly frozen test of simple redundancy sufficiency rather than an operator-
superiority claim.

## Data and code availability

Public USGS and catalog metadata are in-repo. Sealed temperature bytes were
opened once under the T7 QC authorization; they were not confirmatorily scored.
Software archival DOI: `[pending]`.
