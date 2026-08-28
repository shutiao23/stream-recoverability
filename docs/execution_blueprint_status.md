# Execution blueprint status

Date: 2026-08-27  
Review lock: `main@c77804bdb09e460c14f773003f015ac7f0f3b28c`  
Tracker for the WRR adversarial review blueprint (P0–P2).

Machine-readable/current requirement audit:
`results/audits/blueprint_completion_audit.json`; rendered audit:
`docs/blueprint_completion_audit.md`.

## Verdict summary

| Lineage | WRR readiness | Action |
| --- | ---: | --- |
| v4 case study (`paper/case_study_v1/`) | 2.5/10 | JoH case study; abstract/conclusion tightened |
| v9 main (`paper/main_v9/`) | 2/10; current lineage closed before scoring | Sealed QC retained 32/40; a future test needs a new prospective protocol and untouched networks |

## P0 blockers

| ID | Task | Status | Evidence |
| --- | --- | --- | --- |
| P0-0 | Split two paper lineages | **done** | `paper/study_manifest.json`, `paper/case_study_v1/`, `paper/main_v9/` |
| P0-1 | Qualified network catalog ≥100 | **outputs complete; gate failed by 1** | 99/100 plus 78-row exclusion ledger and five-dimension balance report |
| P0-2 | Executable v10 protocol | **done; execution gate failed** | Frozen pre-unseal protocol is preserved; current state is in the results registry |
| P0-3 | Operator identification (synthetic) | **complete negative** | holdout Spearman 0.936; calibration slope 0.760 missed frozen band; no retuning |
| P0-4 | Paired source ablation (same model) | **partial** | W7 B/D/B∪D slices; M/H blocked |
| P0-5 | Empirical gap geometry | **binding complete; inference negative/withheld** | 2,355 observed counterparts + 5,406 adversarial cells on 67 open networks |
| P0-6 | Dev/validation power audit | **complete; empirical floors failed** | max recorded simulation power 0.9125; Tier-2 and n≥100 gates still fail |
| P0-7 | Sealed evaluate-once | **QC complete; scoring withheld** | T7 opened 2,880 objects; 32 eligible (29 HUC8 + 3 FOEN), below 40; authorization consumed |
| P0-8 | Placement/triage utility | **dev failed** | 2/10 placement; 0 safe fills at 5% FPR |
| P0-9 | Manuscript + FAIR package | **local failure package complete; external NO-GO** | separate v4/v9 manuscripts, SI, package manifests, registry; four external blockers |

## P1 (pre-review prep)

| ID | Task | Status |
| --- | --- | --- |
| P1-1 | Structural SOTA sensitivity (tier 2) | roster frozen; not run at scale |
| P1-2 | Topology-matched falsification (T5) | complete negative: only 2 unique network pairs; confound balance inadequate |
| P1-3 | Thermal state / extreme events | specified |
| P1-4 | Risk calibration intervals | not on sealed data |
| P1-5 | Online protocol estimand | 1,384,025-item one-sided workload + bounded ten-item smoke; full run NO-GO |

## P2 (Nature Water / follow-on)

Not started. The current T7 lineage cannot unlock P2 because its sealed QC gate failed.

## Critical path

```
P0-0 ✓ → P0-1 (99/100, failed) → P0-2 ✓ → P0-7 QC (32/40, failed) → scoring withheld
```

This path is closed for v10. Do not repair it by rerunning, replacing attrited
networks, or lowering floors. See `docs/sealed_t7_qc_failure_closure.md`.

Parallel: restricted-data editor exception · GEMS upload · Zenodo DOI

## Commands

```bash
# Rebuild corpus, exclusion/balance reports, and the P0--P2 audit
make blueprint-audit

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

These development outcomes motivate **simple-proxy sufficiency**, but the v10
sealed run did not reach scoring and therefore cannot confirm that conclusion.
