# Twin E hold-out publishable negative result

Date: 2026-08-27  
Status: locked falsification record. Not confirmatory T2 or T5.

## Decision

The locked Twin E hold-out (`E5_twin_e_locked_holdout`) was scored once after
`configs/twin_e_holdout_freeze_v1.yaml` was committed clean. The gate failed on
**operator calibration slope**, not on ranking or univariate ceilings.

| Metric | Observed | Threshold | Met |
|--------|----------|-----------|-----|
| Operator Spearman | 0.936 | ≥ 0.90 | yes |
| Best univariate Spearman | 0.459 (`gap_length_only`) | ≤ 0.70 | yes |
| Operator calibration slope | 0.760 | ∈ [0.9, 1.1] | **no** |
| Gate `passed` | false | true | **no** |

`gate.status = twin_e_operator_calibration_miss`.

## Interpretation

This is a **publishable negative design result** under v9.1: the finite-training
hat-Σ operator ranks recoverability well on the aliasing twin but is
miscalibrated in slope. That falsifies the hold-out gate as written; it does
**not** license retuning φ, noise, donor geometry, or the generator to recover
the band.

Per `design_freeze_v9.yaml`:

> if_operator_cannot_beat_univariates_on_twin_e: publishable_negative_do_not_retune_phi_or_noise

Here the operator beats univariates on Spearman yet still fails calibration.
The same non-retuning rule applies.

## Forbidden responses

- Retune φ, isolation, or process noise to move the slope into band
- Retune the hold-out generator or relabel the failure as a pass
- Average Twin E into Twins A–D or cite exploratory A–D as compensating evidence
- Quote this as confirmatory T5 or as evidence that the Schur operator fails on
  real rivers

## Reproduce

```bash
PYTHONPATH=src python scripts/99_write_twin_e_holdout_negative_result.py
```

Writes
`results/framework/synthetic_v2/twin_e_holdout/twin_e_holdout_negative_result.json`.
