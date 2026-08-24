# Frozen terminology

Use these labels in the manuscript, SI, and README. Do not relabel a split
after seeing outcomes.

| Term | Meaning |
| --- | --- |
| `validation` | 2016–2017. Model selection only. |
| `development_test` | 2018–2020. Formal development evaluation. Seen before design freeze. Not an unseen test set. |
| `test` | Stored-data alias of `development_test` only. |
| `confirmatory` | External 2023–2025 evaluate-once panel after roster freeze. |
| `external temporal replication` | Retrain the frozen architecture on the external training period. Not zero-shot transfer. |
| `memory-dominated` | At 30 days, the frozen local-memory budget component exceeds the simultaneous donor component. |
| `donor-dominated` | At 30 days, the frozen simultaneous donor component is at least the local-memory component. |
| `regulation fingerprint` | Co-occurring compressed temperature range and extended anomaly memory; observational and not alone causal. |
| `state-matched diagnostic` | Post-hoc budget and climatology recalibration to 2016--2020; overlaps evaluation and is not predictive evidence. |
| `best-available node importance` | Failed-network best MAE minus full-network best MAE, with climatology included as a hard cap. |
| `reference_not_tested` | Baseline self-comparison retained for table completeness with no p-value. |
| `validation placement SD` | Sample SD across 20 masks on 2021--2022 external validation data; a noise scale, not a confirmatory CI. |
| `transport-limited maximum legal panel` | National panel after frozen official API fallback and exclusion of ambiguous multi-series sites. |
| `primary discrimination not supported` | National unadjusted/LOEO result; adjusted and distance profiles cannot overwrite it. |
| `offline recovery` | Reconstruction that may use both gap boundaries. |
| `online recovery` | Causal, forward-only recovery. Never pooled with offline ranks. |
| `analysis_eligible` | Allowed in the current analysis. |
| `provider_qc_status=unknown` | No per-value source quality flag. Not provider approval. |
| `quality_approved` | Legacy alias of `analysis_eligible`. Not provider QC. |
| `budget_unstable` | A required seed hit the frozen epoch cap. Ineligible for the roster. |
| `predictive attribution` | Information-group gain under fixed masks. Not a causal mechanism. |
