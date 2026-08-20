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
| `offline recovery` | Reconstruction that may use both gap boundaries. |
| `online recovery` | Causal, forward-only recovery. Never pooled with offline ranks. |
| `analysis_eligible` | Allowed in the current analysis. |
| `provider_qc_status=unknown` | No per-value source quality flag. Not provider approval. |
| `quality_approved` | Legacy alias of `analysis_eligible`. Not provider QC. |
| `budget_unstable` | A required seed hit the frozen epoch cap. Ineligible for the roster. |
| `predictive attribution` | Information-group gain under fixed masks. Not a causal mechanism. |
