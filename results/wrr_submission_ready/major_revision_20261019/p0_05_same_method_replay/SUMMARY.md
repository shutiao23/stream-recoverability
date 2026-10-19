# Same locked method on the real-calendar replay and the hot-year split

The fitted risk score is the development outer-fold model from the isolated run. Each replay network is scored by the model fitted on the other folds, and the threshold is that fold's simultaneous-bound threshold. Peak-window and length rules use the thresholds selected for those scores on the same fold. The reconstruction being accepted or refused is the stored policy reconstruction for that co-failure level. Observed-window-only output is not counted as an admission.

This replay was built from the 418 candidate groups already placed. It does not add a new sealed panel.

## Admission

| level | seed | method | admitted share | error rate among admitted | mean abs error °C |
|---|---:|---|---:|---:|---:|
| target_only | 101 | fitted_risk | 0.947 | 0.008 | 0.030 |
| target_only | 101 | peak_overlap_rule | 0.943 | 0.008 | 0.029 |
| target_only | 101 | length_rule | 0.778 | 0.000 | 0.023 |
| target_only | 101 | reconstruct_all | 1.000 | 0.029 | 0.055 |
| target_only | 202 | fitted_risk | 0.947 | 0.010 | 0.031 |
| target_only | 202 | peak_overlap_rule | 0.943 | 0.008 | 0.029 |
| target_only | 202 | length_rule | 0.778 | 0.000 | 0.023 |
| target_only | 202 | reconstruct_all | 1.000 | 0.029 | 0.055 |
| target_only | 303 | fitted_risk | 0.955 | 0.008 | 0.031 |
| target_only | 303 | peak_overlap_rule | 0.935 | 0.008 | 0.028 |
| target_only | 303 | length_rule | 0.778 | 0.000 | 0.023 |
| target_only | 303 | reconstruct_all | 1.000 | 0.029 | 0.055 |
| partial_donor_failure | 101 | fitted_risk | 0.938 | 0.005 | 0.030 |
| partial_donor_failure | 101 | peak_overlap_rule | 0.943 | 0.005 | 0.032 |
| partial_donor_failure | 101 | length_rule | 0.778 | 0.000 | 0.026 |
| partial_donor_failure | 101 | reconstruct_all | 1.000 | 0.026 | 0.058 |
| partial_donor_failure | 202 | fitted_risk | 0.935 | 0.005 | 0.030 |
| partial_donor_failure | 202 | peak_overlap_rule | 0.943 | 0.005 | 0.032 |
| partial_donor_failure | 202 | length_rule | 0.778 | 0.000 | 0.026 |
| partial_donor_failure | 202 | reconstruct_all | 1.000 | 0.026 | 0.058 |
| partial_donor_failure | 303 | fitted_risk | 0.943 | 0.005 | 0.033 |
| partial_donor_failure | 303 | peak_overlap_rule | 0.935 | 0.005 | 0.032 |
| partial_donor_failure | 303 | length_rule | 0.778 | 0.000 | 0.026 |
| partial_donor_failure | 303 | reconstruct_all | 1.000 | 0.026 | 0.058 |
| all_donor_failure | 101 | fitted_risk | 0.940 | 0.008 | 0.024 |
| all_donor_failure | 101 | peak_overlap_rule | 0.943 | 0.010 | 0.026 |
| all_donor_failure | 101 | length_rule | 0.778 | 0.000 | 0.015 |
| all_donor_failure | 101 | reconstruct_all | 1.000 | 0.041 | 0.059 |
| all_donor_failure | 202 | fitted_risk | 0.940 | 0.010 | 0.026 |
| all_donor_failure | 202 | peak_overlap_rule | 0.943 | 0.010 | 0.026 |
| all_donor_failure | 202 | length_rule | 0.778 | 0.000 | 0.015 |
| all_donor_failure | 202 | reconstruct_all | 1.000 | 0.041 | 0.059 |
| all_donor_failure | 303 | fitted_risk | 0.940 | 0.013 | 0.027 |
| all_donor_failure | 303 | peak_overlap_rule | 0.935 | 0.008 | 0.024 |
| all_donor_failure | 303 | length_rule | 0.778 | 0.000 | 0.015 |
| all_donor_failure | 303 | reconstruct_all | 1.000 | 0.041 | 0.059 |

## Admitted-share difference, fitted risk minus the named rule

| level | seed | contrast | difference | 95% interval | networks |
|---|---:|---|---:|---|---:|
| target_only | 101 | fitted_admit_minus_peak_admit | 0.005 | [-0.007, 0.024] | 14 |
| target_only | 101 | fitted_admit_minus_length_admit | 0.170 | [0.102, 0.268] | 14 |
| target_only | 202 | fitted_admit_minus_peak_admit | 0.005 | [-0.005, 0.021] | 14 |
| target_only | 202 | fitted_admit_minus_length_admit | 0.170 | [0.100, 0.256] | 14 |
| target_only | 303 | fitted_admit_minus_peak_admit | 0.019 | [0.005, 0.038] | 14 |
| target_only | 303 | fitted_admit_minus_length_admit | 0.177 | [0.108, 0.262] | 14 |
| partial_donor_failure | 101 | fitted_admit_minus_peak_admit | -0.005 | [-0.010, 0.000] | 14 |
| partial_donor_failure | 101 | fitted_admit_minus_length_admit | 0.160 | [0.091, 0.237] | 14 |
| partial_donor_failure | 202 | fitted_admit_minus_peak_admit | -0.007 | [-0.024, 0.000] | 14 |
| partial_donor_failure | 202 | fitted_admit_minus_length_admit | 0.158 | [0.088, 0.243] | 14 |
| partial_donor_failure | 303 | fitted_admit_minus_peak_admit | 0.007 | [-0.015, 0.032] | 14 |
| partial_donor_failure | 303 | fitted_admit_minus_length_admit | 0.165 | [0.104, 0.248] | 14 |
| all_donor_failure | 101 | fitted_admit_minus_peak_admit | -0.002 | [-0.006, 0.000] | 14 |
| all_donor_failure | 101 | fitted_admit_minus_length_admit | 0.163 | [0.097, 0.244] | 14 |
| all_donor_failure | 202 | fitted_admit_minus_peak_admit | -0.002 | [-0.008, 0.000] | 14 |
| all_donor_failure | 202 | fitted_admit_minus_length_admit | 0.163 | [0.095, 0.246] | 14 |
| all_donor_failure | 303 | fitted_admit_minus_peak_admit | 0.005 | [-0.013, 0.019] | 14 |
| all_donor_failure | 303 | fitted_admit_minus_length_admit | 0.163 | [0.100, 0.239] | 14 |

## Hot-year composition, seed 101

p_full is the hot-year share of every candidate. p_A is the true hot-year share among admitted records. p_hat_A is the predicted hot-year share among those same records. prediction_error = p_hat_A - p_A. selection_shift = p_A - p_full. total_bias = p_hat_A - p_full. Shares are case-weighted.

| panel | hot °C | method | admitted share | p_full | p_A | p_hat_A | prediction | selection | total |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| development | 18 | fitted_risk | 0.705 | 0.671 | 0.674 | 0.673 | -0.001 | 0.003 | 0.002 |
| development | 18 | peak_overlap_rule | 0.619 | 0.671 | 0.676 | 0.675 | -0.001 | 0.005 | 0.004 |
| development | 18 | length_rule | 0.349 | 0.671 | 0.685 | 0.684 | -0.001 | 0.014 | 0.013 |
| development | 18 | calibrated_bound | 0.732 | 0.671 | 0.689 | 0.688 | -0.001 | 0.018 | 0.017 |
| development | 18 | reconstruct_all | 1.000 | 0.671 | 0.671 | 0.665 | -0.006 | 0.000 | -0.006 |
| development | 20 | fitted_risk | 0.705 | 0.477 | 0.478 | 0.477 | -0.001 | 0.001 | -0.001 |
| development | 20 | peak_overlap_rule | 0.619 | 0.477 | 0.482 | 0.480 | -0.002 | 0.005 | 0.003 |
| development | 20 | length_rule | 0.349 | 0.477 | 0.501 | 0.500 | -0.001 | 0.024 | 0.023 |
| development | 20 | calibrated_bound | 0.732 | 0.477 | 0.489 | 0.488 | -0.001 | 0.011 | 0.010 |
| development | 20 | reconstruct_all | 1.000 | 0.477 | 0.477 | 0.469 | -0.008 | 0.000 | -0.008 |
| wave2_confirmation | 18 | fitted_risk | 0.728 | 0.917 | 0.924 | 0.924 | -0.000 | 0.006 | 0.006 |
| wave2_confirmation | 18 | peak_overlap_rule | 0.696 | 0.917 | 0.918 | 0.918 | 0.000 | 0.000 | 0.000 |
| wave2_confirmation | 18 | length_rule | 0.439 | 0.917 | 0.929 | 0.929 | -0.000 | 0.011 | 0.011 |
| wave2_confirmation | 18 | calibrated_bound | 0.746 | 0.917 | 0.920 | 0.919 | -0.000 | 0.002 | 0.002 |
| wave2_confirmation | 18 | reconstruct_all | 1.000 | 0.917 | 0.917 | 0.918 | 0.000 | 0.000 | 0.000 |
| wave2_confirmation | 20 | fitted_risk | 0.728 | 0.857 | 0.870 | 0.866 | -0.003 | 0.012 | 0.009 |
| wave2_confirmation | 20 | peak_overlap_rule | 0.696 | 0.857 | 0.859 | 0.857 | -0.002 | 0.002 | -0.000 |
| wave2_confirmation | 20 | length_rule | 0.439 | 0.857 | 0.871 | 0.870 | -0.002 | 0.014 | 0.013 |
| wave2_confirmation | 20 | calibrated_bound | 0.746 | 0.857 | 0.869 | 0.865 | -0.004 | 0.012 | 0.008 |
| wave2_confirmation | 20 | reconstruct_all | 1.000 | 0.857 | 0.857 | 0.852 | -0.006 | 0.000 | -0.006 |
