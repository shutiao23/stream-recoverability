# Step 2 — strong simple methods on the trusted river complete-year panel

Existing frozen replay, no retraining. Opened confirmation years are retrospective.
Oracle = max(gated donor-only benefit, 0) and is not deployable.

{
  "development_all_existing": {
    "n_cases": 11060,
    "n_networks": 42,
    "n_station_years": 1657
  },
  "confirmation_all_existing": {
    "n_cases": 2501,
    "n_networks": 36,
    "n_station_years": 306
  },
  "development_river_complete_years": {
    "n_cases": 7787,
    "n_networks": 42,
    "n_station_years": 1115
  },
  "retrospective_confirmation_river_complete_years": {
    "n_cases": 846,
    "n_networks": 23,
    "n_station_years": 91
  },
  "retrospective_confirmation_opened_846_like": {
    "n_cases": 846,
    "n_networks": 23,
    "n_station_years": 91
  }
}

## Network-equal means

                                         subset                    strategy  n_cases  n_networks  n_stations  n_station_years  case_mean_hottest_30  network_mean_hottest_30  network_ci_low  network_ci_high  harm_rate  severe_harm_below_minus1C  mean_adopt_rate
                       development_all_existing                 all_default    11060          42         222             1657              0.000000                 0.000000        0.000000         0.000000   0.000000                        0.0         0.000000
                       development_all_existing               seasonal_le30    11060          42         222             1657              0.032536                 0.041909        0.031118         0.053737   0.030561                        6.0         0.491761
                       development_all_existing          always_donor_gated    11060          42         222             1657              0.278404                 0.275032        0.212124         0.339742   0.093309                       38.0         0.967722
                       development_all_existing         always_switch_gated    11060          42         222             1657              0.280164                 0.277246        0.214668         0.341672   0.090145                       38.0         0.971067
                       development_all_existing                 frozen_rule    11060          42         222             1657              0.194107                 0.236735        0.179181         0.297009   0.065099                       22.0         0.699634
                       development_all_existing          oracle_gated_donor    11060          42         222             1657              0.302875                 0.307766        0.247805         0.369797   0.000000                        NaN              NaN
                       development_all_existing headroom_oracle_minus_donor    11060          42         222             1657              0.024471                 0.032734        0.022200         0.046750        NaN                        NaN              NaN
                      confirmation_all_existing                 all_default     2501          36          70              306              0.000000                 0.000000        0.000000         0.000000   0.000000                        0.0         0.000000
                      confirmation_all_existing               seasonal_le30     2501          36          70              306              0.020241                 0.024697        0.015004         0.035492   0.029188                        0.0         0.320199
                      confirmation_all_existing          always_donor_gated     2501          36          70              306              0.133316                 0.137553        0.074736         0.203180   0.100360                        9.0         0.671731
                      confirmation_all_existing         always_switch_gated     2501          36          70              306              0.135483                 0.140286        0.077864         0.205000   0.097961                        9.0         0.708383
                      confirmation_all_existing                 frozen_rule     2501          36          70              306              0.130808                 0.132079        0.074882         0.192871   0.065974                        5.0         0.588565
                      confirmation_all_existing          oracle_gated_donor     2501          36          70              306              0.160897                 0.164713        0.107116         0.224416   0.000000                        NaN              NaN
                      confirmation_all_existing headroom_oracle_minus_donor     2501          36          70              306              0.027581                 0.027160        0.011816         0.045653        NaN                        NaN              NaN
               development_river_complete_years                 all_default     7787          42         216             1115              0.000000                 0.000000        0.000000         0.000000   0.000000                        0.0         0.000000
               development_river_complete_years               seasonal_le30     7787          42         216             1115              0.032881                 0.038893        0.028117         0.050681   0.028894                        4.0         0.467276
               development_river_complete_years          always_donor_gated     7787          42         216             1115              0.318406                 0.276588        0.210148         0.344038   0.097599                       29.0         0.972261
               development_river_complete_years         always_switch_gated     7787          42         216             1115              0.320106                 0.278575        0.212138         0.345485   0.094645                       29.0         0.974958
               development_river_complete_years                 frozen_rule     7787          42         216             1115              0.216777                 0.230593        0.172140         0.290658   0.069346                       16.0         0.684262
               development_river_complete_years          oracle_gated_donor     7787          42         216             1115              0.344122                 0.313074        0.252333         0.374894   0.000000                        NaN              NaN
               development_river_complete_years headroom_oracle_minus_donor     7787          42         216             1115              0.025715                 0.036486        0.022278         0.056167        NaN                        NaN              NaN
retrospective_confirmation_river_complete_years                 all_default      846          23          35               91              0.000000                 0.000000        0.000000         0.000000   0.000000                        0.0         0.000000
retrospective_confirmation_river_complete_years               seasonal_le30      846          23          35               91              0.010702                 0.008954       -0.003601         0.022350   0.024823                        0.0         0.252857
retrospective_confirmation_river_complete_years          always_donor_gated      846          23          35               91              0.172386                 0.082499       -0.056940         0.216748   0.094563                        7.0         0.619385
retrospective_confirmation_river_complete_years         always_switch_gated      846          23          35               91              0.174567                 0.085939       -0.053897         0.219895   0.092199                        7.0         0.656028
retrospective_confirmation_river_complete_years                 frozen_rule      846          23          35               91              0.170182                 0.096732        0.012788         0.198448   0.052009                        3.0         0.530536
retrospective_confirmation_river_complete_years          oracle_gated_donor      846          23          35               91              0.212570                 0.156574        0.071677         0.255862   0.000000                        NaN              NaN
retrospective_confirmation_river_complete_years headroom_oracle_minus_donor      846          23          35               91              0.040184                 0.074075        0.011977         0.169798        NaN                        NaN              NaN
     retrospective_confirmation_opened_846_like                 all_default      846          23          35               91              0.000000                 0.000000        0.000000         0.000000   0.000000                        0.0         0.000000
     retrospective_confirmation_opened_846_like               seasonal_le30      846          23          35               91              0.010702                 0.008954       -0.003601         0.022350   0.024823                        0.0         0.252857
     retrospective_confirmation_opened_846_like          always_donor_gated      846          23          35               91              0.172386                 0.082499       -0.056940         0.216748   0.094563                        7.0         0.619385
     retrospective_confirmation_opened_846_like         always_switch_gated      846          23          35               91              0.174567                 0.085939       -0.053897         0.219895   0.092199                        7.0         0.656028
     retrospective_confirmation_opened_846_like                 frozen_rule      846          23          35               91              0.170182                 0.096732        0.012788         0.198448   0.052009                        3.0         0.530536
     retrospective_confirmation_opened_846_like          oracle_gated_donor      846          23          35               91              0.212570                 0.156574        0.071677         0.255862   0.000000                        NaN              NaN
     retrospective_confirmation_opened_846_like headroom_oracle_minus_donor      846          23          35               91              0.040184                 0.074075        0.011977         0.169798        NaN                        NaN              NaN

## Paired contrasts versus gated donor-only

                                         subset                               contrast  case_mean_difference  network_mean_difference  network_ci_low  network_ci_high
                       development_all_existing         frozen_rule_minus_always_donor             -0.084297                -0.038297       -0.068111        -0.012845
                       development_all_existing always_switch_gated_minus_always_donor              0.001761                 0.002214        0.001330         0.003284
                       development_all_existing       seasonal_le30_minus_always_donor             -0.245868                -0.233123       -0.292002        -0.176156
                       development_all_existing  oracle_gated_donor_minus_always_donor              0.024471                 0.032734        0.022200         0.046750
                      confirmation_all_existing         frozen_rule_minus_always_donor             -0.002508                -0.005474       -0.026913         0.011215
                      confirmation_all_existing always_switch_gated_minus_always_donor              0.002167                 0.002733        0.000618         0.005587
                      confirmation_all_existing       seasonal_le30_minus_always_donor             -0.113076                -0.112856       -0.171297        -0.057026
                      confirmation_all_existing  oracle_gated_donor_minus_always_donor              0.027581                 0.027160        0.011816         0.045653
               development_river_complete_years         frozen_rule_minus_always_donor             -0.101630                -0.045995       -0.081596        -0.015500
               development_river_complete_years always_switch_gated_minus_always_donor              0.001699                 0.001987        0.000988         0.003158
               development_river_complete_years       seasonal_le30_minus_always_donor             -0.285525                -0.237695       -0.300589        -0.176580
               development_river_complete_years  oracle_gated_donor_minus_always_donor              0.025715                 0.036486        0.022278         0.056167
retrospective_confirmation_river_complete_years         frozen_rule_minus_always_donor             -0.002204                 0.014234       -0.050882         0.094903
retrospective_confirmation_river_complete_years always_switch_gated_minus_always_donor              0.002181                 0.003440        0.000407         0.007164
retrospective_confirmation_river_complete_years       seasonal_le30_minus_always_donor             -0.161684                -0.073545       -0.203052         0.058320
retrospective_confirmation_river_complete_years  oracle_gated_donor_minus_always_donor              0.040184                 0.074075        0.011977         0.169798
     retrospective_confirmation_opened_846_like         frozen_rule_minus_always_donor             -0.002204                 0.014234       -0.050882         0.094903
     retrospective_confirmation_opened_846_like always_switch_gated_minus_always_donor              0.002181                 0.003440        0.000407         0.007164
     retrospective_confirmation_opened_846_like       seasonal_le30_minus_always_donor             -0.161684                -0.073545       -0.203052         0.058320
     retrospective_confirmation_opened_846_like  oracle_gated_donor_minus_always_donor              0.040184                 0.074075        0.011977         0.169798
