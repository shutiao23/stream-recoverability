# Step 2 — same-info support ablation (development OOF + reserved curves)

Claim C1: engineered `peak_overlap` adds inductive bias beyond a same-capacity generic risk model.

## Development OOF operating points

                              screen  kind  rate_above_0.5_at_70  mean_abs_error_c_at_70  retention_at_risk_cap_5pct  rate_above_0.5_at_risk_cap  n_retained_at_risk_cap
                             generic model              0.029902                0.064948                        0.77                    0.048051                   31342
                generic_plus_support model              0.030358                0.065341                        0.77                    0.048338                   31342
generic_plus_support_plus_peakmargin model              0.030429                0.065615                        0.77                    0.049008                   31342
         estimator_disagreement_rule  rule              0.048503                0.091238                        0.70                    0.048503                   28493
                   peak_overlap_rule  rule              0.056330                0.101173                        0.67                    0.048291                   27272
                  warm_coverage_rule  rule              0.068719                0.117495                        0.63                    0.049641                   25644
                         length_rule  rule              0.092374                0.153558                        0.46                    0.049295                   18724

## Network-clustered contrasts (rate diff at 70% / 0.5 °C, percentage points)

- `generic_plus_support__minus__peak_overlap_rule`: Δ rate = -2.60 pp [-3.11, -2.19]
- `generic_plus_support__minus__generic`: Δ rate = 0.05 pp [-0.17, 0.23]
- `generic_plus_support_plus_peakmargin__minus__generic_plus_support`: Δ rate = 0.01 pp [-0.19, 0.18]
- `generic_plus_support_plus_peakmargin__minus__peak_overlap_rule`: Δ rate = -2.59 pp [-3.16, -2.14]
- `generic__minus__peak_overlap_rule`: Δ rate = -2.64 pp [-3.12, -2.20]
- `generic_plus_support__minus__length_rule`: Δ rate = -6.20 pp [-7.16, -5.36]
- `retention_at_risk5__generic_plus_support__minus__peak_overlap_rule`: Δ retention = 10.00 pp [7.00, 12.00] (success≥+5pp & CI>0: True)
- `retention_at_risk5__generic_plus_support__minus__generic`: Δ retention = 0.00 pp [-1.00, 1.00] (success≥+5pp & CI>0: False)
- `retention_at_risk5__generic_plus_support_plus_peakmargin__minus__peak_overlap_rule`: Δ retention = 10.00 pp [7.00, 12.00] (success≥+5pp & CI>0: True)

## Learning curves (reserved retrospective panel)

                         feature_set  n_train_networks  rate_above_0.5_at_70  retention_at_risk_cap_5pct
                             generic                10              0.035780                        0.74
                             generic                25              0.028915                        0.78
                             generic                50              0.036572                        0.74
                             generic               110              0.023633                        0.78
                generic_plus_support                10              0.035252                        0.75
                generic_plus_support                25              0.024162                        0.79
                generic_plus_support                50              0.035252                        0.75
                generic_plus_support               110              0.023633                        0.79
generic_plus_support_plus_peakmargin                10              0.032612                        0.75
generic_plus_support_plus_peakmargin                25              0.024954                        0.78
generic_plus_support_plus_peakmargin                50              0.026802                        0.77
generic_plus_support_plus_peakmargin               110              0.021653                        0.79

Reserved panel is retrospective (opened). Do not treat as sealed confirmation.

