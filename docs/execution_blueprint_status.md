# Execution blueprint status

Date: 2026-08-27  
Review lock: `main@c77804bdb09e460c14f773003f015ac7f0f3b28c`  
Tracker for the WRR adversarial review blueprint (P0–P2).

## Verdict summary

| Lineage | WRR readiness | Action |
| --- | ---: | --- |
| v4 case study (`paper/case_study_v1/`) | 2.5/10 | JoH case study; abstract/conclusion tightened |
| v9 main (`paper/main_v9/`) | 2/10 now; 8/10 potential | Complete sealed T7 after corpus floor |

## P0 blockers

| ID | Task | Status | Evidence |
| --- | --- | --- | --- |
| P0-0 | Split two paper lineages | **done** | `paper/study_manifest.json`, `paper/case_study_v1/`, `paper/main_v9/` |
| P0-1 | Qualified network catalog ≥100 | **near floor** | 96/100 (`qualified_corpus_manifest.json`); gap 4 |
| P0-2 | Executable v10 protocol | **done (gated)** | `configs/design_freeze_v10_executable.yaml`; corpus floor not met |
| P0-3 | Operator identification (synthetic) | **partial** | `twin_e_holdout_negative_result.json`; gate not informative |
| P0-4 | Paired source ablation (same model) | **partial** | W7 B/D/B∪D slices; M/H blocked |
| P0-5 | Empirical gap geometry | **partial** | 1,470 real segments catalogued; not in primary sealed run |
| P0-6 | Dev/validation power audit | **partial** | `tier2_development_subsample_manifest.json`; n<100 withholds CI |
| P0-7 | Sealed evaluate-once | **QC complete** | T7 opened 2880 objects; 29 HUC8 eligible (floor 40 not met) |
| P0-8 | Placement/triage utility | **dev failed** | 2/10 placement; 0 safe fills at 5% FPR |
| P0-9 | Manuscript + FAIR package | **partial** | Case study rewritten; v9 skeleton; submission gate NO-GO |

## P1 (pre-review prep)

| ID | Task | Status |
| --- | --- | --- |
| P1-1 | Structural SOTA sensitivity (tier 2) | roster frozen; not run at scale |
| P1-2 | Topology-matched falsification (T5) | 5 pairs; ΔR ≈ −0.03; not passed |
| P1-3 | Thermal state / extreme events | specified |
| P1-4 | Risk calibration intervals | not on sealed data |
| P1-5 | Online protocol estimand | separate workload manifest exists |

## P2 (Nature Water / follow-on)

Not started. Requires sealed T7 success + operational thresholds + cross-continental panel.

## Critical path

```
P0-0 ✓ → P0-1 (blocked: +33 networks) → P0-2 ✓ → P0-6 → P0-7 → P0-8 → P0-9
```

Parallel: restricted-data editor exception · GEMS upload · Zenodo DOI

## Commands

```bash
# Corpus accounting
PYTHONPATH=src python scripts/100_build_qualified_corpus_manifest.py

# Study manifest validation
PYTHONPATH=src python scripts/103_validate_study_manifest.py

# Submission gate (expected NO-GO)
PYTHONPATH=src python scripts/27_submission_gate.py --allow-no-go

# Sealed preunseal audit
PYTHONPATH=src python scripts/80_audit_sealed_evaluation_readiness.py
```

## Honest development outcomes (do not retune)

- n=44 stop-loss: operator Spearman 0.67 vs donor R² 0.80
- W8 ΔR² vs donor R²: \(6.88\times10^{-5}\)
- Placement: Delaware + Santa Fe only (2/10)
- Triage at 5% false release: 0 safe fills (both rules)

If sealed T7 confirms these patterns, publish **simple-proxy sufficiency**, not operator superiority.
