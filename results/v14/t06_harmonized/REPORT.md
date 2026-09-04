# t06 missingness matrix - canonical harmonized rerun

Status: **canonical run archived** (2026-09-03), per
`paper/v14_plan/harmonization_decisions.md` section 1.

## What this is

The single canonical re-execution of the missingness-mechanism matrix using
agent_b's frozen machinery, panel (12 networks), forcing (NASA POWER T2M
cache), and supported-unit scoring convention.  Script:
`scripts/rev_v12_t06_missingness_b.py`, run with
`--workers 24 --output results/v14/t06_harmonized`, runtime 77.0 s.

## Acceptance gate and reproduction

Gate from harmonization_decisions.md: uniform-block mechanism network
Spearman must land at ~0.92-0.94.

| check | value |
|---|---|
| uniform_block supported network Spearman | **0.944** (gate: 0.92-0.94 -> PASS) |
| bit-identity vs archived agent_b tables | all 7 tables identical (max numeric diff 0.0; mechanism_units 2407 rows, mechanism_curve_cells 114921, mechanism_eval_cells 48039) |
| bootstrap intervals | copied from archived agent_b (identical units by construction); donor_sync 0.490 [-0.236, 0.925], uniform_block 0.944 [0.688, 1.000] |

## Canonical values (reporting rule: SI only, with intervals)

| mechanism | supported network Spearman | 95% CI | calib. slope | n units |
|---|---|---|---|---|
| uniform_block (a) | 0.944 | [0.688, 1.000] | 1.021 | 306 |
| multi_block (b) | 0.888 | [0.533, 1.000] | 1.016 | 306 |
| summer_biased (c) | 0.909 | [0.651, 1.000] | 1.043 | 292 |
| high_temp_biased (d) | 0.958 | [0.779, 1.000] | 0.907 | 304 |
| donor_sync (f) | 0.490 | [-0.236, 0.925] | 0.743 | 306 |
| forcing_outage (g) | 0.937 | [0.697, 1.000] | 0.987 | 306 |
| online (h) | 0.965 | [0.806, 1.000] | 0.942 | 306 |

Implementation-invariant qualitative findings retained for main text: (1)
mechanism mismatch harms transfer in at least one direction (uniform curve on
donor-synchronous gaps collapses; donor-synchronous curve on uniform gaps
collapses - see mismatch_experiment.csv); (2) seasonal placement bias is the
mildest mismatch.  agent_a's archived implementation remains documented
independent evidence; its values are not presented beside the canonical set.

## Files

mechanism_metrics.csv, mechanism_units.csv, mechanism_curve_cells.csv,
mechanism_eval_cells.csv, mechanism_bootstrap_intervals.csv,
missingness_support_matrix.csv, mismatch_experiment.csv,
mechanism_stress_levels.csv, attrition_log.csv, provenance.json,
power_ta_cache/ (12 cached T2M series).
