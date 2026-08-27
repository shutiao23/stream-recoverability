# Corpus floor gap (v9.1)

Date: 2026-08-27  
Status: honest accounting. Network CI floor not met.

## Current qualified total: 67 / 100

| Component | Count | QC status |
|-----------|------:|-----------|
| USGS open-role (`failure_closure6`) | 67 | complete_enough |
| Sealed custody (HUC8 + FOEN metadata) | 44 networks | bytes not opened (`qc_permitted: 0`) |
| Europe UK EA spatial supplement | 0 | 15 clusters downloaded, none `complete_enough` |
| **Qualified sum** | **67** | floor gap **33** |

## Why open-role alone cannot reach 100 today

- Split pool: 103 open-role networks downloaded (all selected dev+val rows).
- 67 pass 6-year overlap + 3-station + 5×365 concurrent-day QC.
- Best-case open ceiling without new downloads: **103** (needs 33 of 36 marginal networks to flip—data-limited, not a QC-script bug).
- Near-miss example: `huc8_14050006` has 7.5 overlap years but only 1564 concurrent days (< 1825 required).

## Sealed QC path

44 sealed HUC8 networks have write-only vault bytes. Development QC is blocked by `HUC8CorpusGate` (`SealedOutcomeAccessError`). T7 evaluate-once is required before temperature bytes can be QC'd and counted.

Preflight: `scripts/90_preflight_sealed_evaluator.py`  
Readiness audit: `scripts/80_audit_sealed_evaluation_readiness.py`

## Reproduce accounting

```bash
PYTHONPATH=src python scripts/97_build_global_attrition_table.py
PYTHONPATH=src python scripts/100_build_qualified_corpus_manifest.py
```

Writes `data_versions/global_network_corpus_v1/qualified_corpus_v1/qualified_corpus_manifest.json`.
