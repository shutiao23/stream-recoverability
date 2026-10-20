# R2-02 same-capacity ablation

One learner, one training set, one calibration procedure, one decision protocol.
Retention is at the 5 % cap on the admitted policy reconstruction (mean of three fold seeds).

Determinism check (generic+support == the 330 fitted score): True

## wave2_confirmation

| score | retention at cap | false-admit | failure rate at fixed 70 % |
|---|---:|---:|---:|
| gap_season | 0.632 | 0.029 | 0.042 |
| gap_season+support | 0.667 | 0.029 | 0.037 |
| gap_season+donors | 0.687 | 0.031 | 0.035 |
| gap_season+donors+support | 0.715 | 0.030 | 0.029 |
| gap_season+donors+residual | 0.740 | 0.031 | 0.021 |
| gap_season+donors+residual+support | 0.748 | 0.032 | 0.021 |
| generic | 0.734 | 0.031 | 0.024 |
| generic+support | 0.739 | 0.031 | 0.022 |
| logit_small | 0.624 | 0.032 | 0.045 |
| logit_small+support | 0.689 | 0.032 | 0.034 |
| generic+oracle_support | 0.750 | 0.029 | 0.015 |
| peak_overlap_rule | 0.666 | 0.033 | 0.037 |
| length_rule | 0.396 | 0.018 | 0.083 |
| calibrated_bound | 0.729 | 0.032 | 0.028 |
| warm_coverage_rule | 0.507 | 0.020 | 0.060 |
| oracle_support_rule | 0.720 | 0.032 | 0.026 |
| reconstruct_all | 1.000 | 0.153 | - |

## development

| score | retention at cap | false-admit | failure rate at fixed 70 % |
|---|---:|---:|---:|
| gap_season | 0.587 | 0.034 | 0.056 |
| gap_season+support | 0.604 | 0.033 | 0.054 |
| gap_season+donors | 0.624 | 0.031 | 0.044 |
| gap_season+donors+support | 0.633 | 0.029 | 0.042 |
| gap_season+donors+residual | 0.702 | 0.030 | 0.030 |
| gap_season+donors+residual+support | 0.705 | 0.030 | 0.030 |
| generic | 0.704 | 0.030 | 0.030 |
| generic+support | 0.705 | 0.030 | 0.030 |
| logit_small | 0.463 | 0.028 | 0.057 |
| logit_small+support | 0.598 | 0.031 | 0.051 |
| generic+oracle_support | 0.739 | 0.031 | 0.021 |
| peak_overlap_rule | 0.604 | 0.038 | 0.057 |
| length_rule | 0.305 | 0.024 | 0.092 |
| calibrated_bound | 0.727 | 0.036 | 0.032 |
| warm_coverage_rule | 0.443 | 0.020 | 0.068 |
| oracle_support_rule | 0.691 | 0.035 | 0.037 |
| reconstruct_all | 1.000 | 0.149 | - |

## Paired contrasts (retention, percentage points; group-clustered 95 % interval)

| panel | left - right | seed 101 | seed 202 | seed 303 |
|---|---|---|---|---|
| wave2_confirmation | generic+support - generic | +0.4 [-0.6, +1.3] | +0.8 [-0.1, +1.8] | +0.3 [-0.4, +0.9] |
| wave2_confirmation | gap_season+donors+residual+support - gap_season+donors+residual | +1.2 [+0.5, +1.9] | +0.8 [+0.2, +1.6] | +0.3 [-0.5, +1.2] |
| wave2_confirmation | gap_season+donors+support - gap_season+donors | +3.0 [+1.6, +4.5] | +2.2 [+1.0, +3.4] | +3.3 [+1.8, +4.8] |
| wave2_confirmation | gap_season+support - gap_season | +2.4 [+1.5, +3.4] | +5.0 [+3.9, +6.2] | +3.0 [+2.2, +4.0] |
| wave2_confirmation | logit_small+support - logit_small | +6.2 [+5.1, +7.3] | +6.8 [+5.3, +8.4] | +6.6 [+5.3, +7.9] |
| wave2_confirmation | generic - peak_overlap_rule | +7.0 [+3.7, +10.0] | +6.7 [+3.2, +9.7] | +6.9 [+3.8, +9.7] |
| wave2_confirmation | generic+support - peak_overlap_rule | +7.4 [+4.3, +10.4] | +7.5 [+4.9, +9.8] | +7.2 [+4.4, +9.8] |
| wave2_confirmation | logit_small - peak_overlap_rule | -3.7 [-6.4, -1.2] | -4.4 [-7.2, -1.8] | -4.5 [-7.4, -1.8] |
| wave2_confirmation | gap_season - peak_overlap_rule | -2.0 [-3.3, -0.8] | -5.3 [-6.8, -4.1] | -2.7 [-4.0, -1.6] |
| wave2_confirmation | gap_season+donors - gap_season | +4.3 [+0.0, +8.8] | +6.9 [+2.7, +11.0] | +5.1 [+0.8, +9.2] |
| wave2_confirmation | gap_season+donors+residual - gap_season+donors | +5.4 [+3.8, +7.1] | +5.7 [+3.7, +7.8] | +4.8 [+3.3, +6.4] |
| wave2_confirmation | generic - gap_season+donors+residual | -0.7 [-1.9, +0.3] | -0.7 [-1.9, +0.6] | -0.2 [-1.5, +0.7] |
| wave2_confirmation | gap_season - length_rule | +24.8 [+23.0, +26.9] | +21.8 [+20.0, +23.9] | +24.4 [+22.7, +26.5] |
| wave2_confirmation | gap_season - warm_coverage_rule | +13.5 [+11.9, +15.1] | +9.6 [+8.1, +10.9] | +14.4 [+13.4, +15.3] |
| wave2_confirmation | generic - calibrated_bound | +0.6 [-1.2, +2.5] | +0.4 [-1.5, +2.3] | +0.6 [-1.3, +2.2] |
| wave2_confirmation | generic+support - calibrated_bound | +1.0 [-0.3, +2.3] | +1.2 [-0.5, +2.7] | +0.8 [-1.0, +2.4] |
| wave2_confirmation | oracle_support_rule - peak_overlap_rule | +5.9 [+5.1, +6.8] | +5.0 [+4.0, +6.1] | +5.5 [+4.6, +6.4] |
| wave2_confirmation | generic+oracle_support - generic+support | +1.8 [+0.8, +2.8] | +0.8 [-0.1, +1.7] | +0.6 [-0.2, +1.4] |
| wave2_confirmation | generic+oracle_support - generic | +2.2 [+1.4, +3.0] | +1.6 [+0.5, +2.5] | +0.9 [+0.1, +1.6] |
| development | generic+support - generic | -0.5 [-1.1, -0.0] | +0.4 [-0.1, +0.9] | +0.5 [+0.1, +0.9] |
| development | gap_season+donors+residual+support - gap_season+donors+residual | +0.6 [+0.1, +1.1] | -0.6 [-1.1, -0.2] | +1.1 [+0.7, +1.5] |
| development | gap_season+donors+support - gap_season+donors | +1.3 [+0.4, +2.2] | +0.7 [-0.5, +2.0] | +0.6 [-0.2, +1.5] |
| development | gap_season+support - gap_season | +2.7 [+1.4, +4.2] | +1.3 [+0.1, +2.7] | +1.3 [+0.1, +2.4] |
| development | logit_small+support - logit_small | +11.4 [+8.7, +14.5] | +16.3 [+11.6, +22.1] | +12.8 [+7.8, +18.8] |
| development | generic - peak_overlap_rule | +10.7 [+8.2, +13.7] | +9.8 [+6.9, +13.1] | +9.3 [+6.8, +12.4] |
| development | generic+support - peak_overlap_rule | +10.2 [+7.4, +13.4] | +10.3 [+7.2, +13.6] | +9.8 [+7.1, +13.0] |
| development | logit_small - peak_overlap_rule | -10.8 [-15.3, -6.5] | -18.3 [-26.3, -11.1] | -13.1 [-21.2, -5.7] |
| development | gap_season - peak_overlap_rule | -2.1 [-3.7, -0.6] | -1.2 [-3.0, +0.3] | -2.0 [-3.5, -0.6] |
| development | gap_season+donors - gap_season | +3.2 [+0.4, +6.5] | +3.2 [+0.2, +6.7] | +4.9 [+1.7, +8.3] |
| development | gap_season+donors+residual - gap_season+donors | +9.0 [+7.1, +11.0] | +8.2 [+6.2, +10.4] | +6.1 [+4.1, +8.4] |
| development | generic - gap_season+donors+residual | +0.6 [-0.2, +1.2] | -0.4 [-1.0, +0.4] | +0.4 [-0.4, +1.1] |
| development | gap_season - length_rule | +26.9 [+24.4, +29.9] | +29.1 [+26.4, +32.0] | +28.3 [+25.6, +31.4] |
| development | gap_season - warm_coverage_rule | +12.3 [+10.3, +14.3] | +15.9 [+14.0, +17.8] | +14.9 [+13.0, +17.1] |
| development | generic - calibrated_bound | -2.1 [-5.3, +0.9] | -1.9 [-5.5, +1.6] | -2.9 [-6.3, +0.5] |
| development | generic+support - calibrated_bound | -2.7 [-6.0, +0.5] | -1.5 [-5.0, +2.0] | -2.4 [-5.8, +0.9] |
| development | oracle_support_rule - peak_overlap_rule | +9.3 [+8.5, +10.1] | +8.2 [+7.5, +9.0] | +8.7 [+8.0, +9.5] |
| development | generic+oracle_support - generic+support | +4.1 [+2.9, +5.3] | +3.4 [+2.4, +4.3] | +2.8 [+1.9, +3.6] |
| development | generic+oracle_support - generic | +3.5 [+2.7, +4.3] | +3.8 [+2.8, +4.7] | +3.3 [+2.4, +4.1] |

