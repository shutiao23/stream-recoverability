# Step 10 — the reserved networks, scored once

Reserved panel: **36** networks, **1,069** station-years, **10,820** cases. The certificate is the Step-9 object applied without retuning.

## Share of retained station-years with error above 0.5 °C

screen     certificate  certificate_screen_only  estimator_disagreement  length_rule  missing_fraction_rule  oracle  peak_overlap_rule  random  warm_coverage_rule
retention                                                                                                                                                         
0.30            0.0006                   0.0003                  0.0028       0.0194                 0.0213  0.0000             0.0068  0.1445              0.0000
0.35            0.0011                   0.0008                  0.0026       0.0217                 0.0277  0.0000             0.0082  0.1463              0.0045
0.40            0.0014                   0.0012                  0.0023       0.0363                 0.0434  0.0000             0.0090  0.1428              0.0141
0.45            0.0021                   0.0025                  0.0025       0.0505                 0.0520  0.0000             0.0090  0.1438              0.0154
0.50            0.0035                   0.0046                  0.0048       0.0512                 0.0540  0.0000             0.0092  0.1447              0.0240
0.55            0.0055                   0.0071                  0.0097       0.0654                 0.0674  0.0000             0.0146  0.1440              0.0413
0.60            0.0100                   0.0122                  0.0162       0.0762                 0.0776  0.0000             0.0222  0.1439              0.0421
0.65            0.0162                   0.0183                  0.0235       0.0896                 0.0894  0.0000             0.0326  0.1446              0.0459
0.70            0.0253                   0.0288                  0.0350       0.0966                 0.0960  0.0000             0.0420  0.1439              0.0638
0.75            0.0405                   0.0437                  0.0509       0.0994                 0.0992  0.0000             0.0578  0.1422              0.0741
0.80            0.0533                   0.0568                  0.0675       0.1064                 0.1070  0.0000             0.0764  0.1430              0.0826
0.85            0.0685                   0.0732                  0.0855       0.1125                 0.1126  0.0000             0.0968  0.1443              0.0973
0.90            0.0870                   0.0925                  0.1084       0.1228                 0.1221  0.0512             0.1152  0.1441              0.1100
0.95            0.1102                   0.1168                  0.1274       0.1314                 0.1317  0.1012             0.1308  0.1440              0.1304
1.00            0.1384                   0.1461                  0.1461       0.1461                 0.1461  0.1461             0.1461  0.1461              0.1461

## Against the published fixed-length guidance, at equal retention

                                      rule  retention  rate_above_0.5  mean_abs_error_c  certificate_rate_above_0.5_at_equal_retention  certificate_mean_abs_error_at_equal_retention  absolute_points_saved
        length <= 49 d (Johnson, unfilled)     0.4924          0.0520            0.0903                                         0.0032                                         0.0138                 4.8799
length <= 140 d (Johnson, with imputation)     0.8514          0.1129            0.1737                                         0.0688                                         0.1099                 4.4073
                           length <= 180 d     0.9538          0.1321            0.2002                                         0.1123                                         0.1658                 1.9767

## Conformal coverage

                     stratum       level     n  coverage  bound_coverage  median_width_c
                         all    marginal 10820    0.9085          0.9063          0.5352
           donor_regime=none conditional   925    0.9124          0.9092          0.6639
           donor_regime=rich conditional  5472    0.9187          0.9201          0.4876
         donor_regime=sparse conditional  4423    0.8951          0.8885          0.5834
         longest_run=(0, 30] conditional  5018    0.9269          0.9227          0.1506
        longest_run=(30, 90] conditional  2966    0.8918          0.8948          0.7213
       longest_run=(90, 180] conditional  2336    0.8938          0.8896          1.1592
      longest_run=(180, 400] conditional   500    0.8920          0.8880          2.2168
peak_overlap=(-0.001, 0.001] conditional  5078    0.9494          0.9622          0.0565
   peak_overlap=(0.001, 0.5] conditional  2396    0.8848          0.8598          0.7425
   peak_overlap=(0.5, 1.001] conditional  3346    0.8634          0.8548          1.8684

## Per-year exceedance judgement

 threshold_c            treatment  retention  n_scored  misclassification_rate  false_negative_rate  false_positive_rate
        18.0    observed_days_all     1.0000      1030                  0.0136               0.0161               0.0098
        18.0      reconstruct_all     1.0000      1030                  0.0058               0.0064               0.0049
        18.0      length_screened     0.9136       941                  0.0043               0.0051               0.0028
        18.0 certificate_screened     0.9107       938                  0.0011               0.0017               0.0000
        20.0    observed_days_all     1.0000      1030                  0.0107               0.0170               0.0054
        20.0      reconstruct_all     1.0000      1030                  0.0039               0.0021               0.0054
        20.0      length_screened     0.9136       941                  0.0043               0.0023               0.0060
        20.0 certificate_screened     0.9107       938                  0.0011               0.0000               0.0021

## Leave-one-provider-out inside development (agency transfer)

            provider  n_cases  n_networks  contrast_points  ci_low_points  ci_high_points  coverage
                arso     3389          10           -3.921         -5.900          -1.940     0.930
                chmi     5994          12           -8.174        -10.233          -5.297     0.825
                foen     2855           2           -1.151         -1.613          -1.007     0.962
          gkd_bayern    10443           7           -5.800         -7.568          -4.669     0.897
                lubw     1854           6           -6.009         -7.884          -4.836     0.890
          nve_hydapi     2188          13           -5.157         -6.261          -2.597     0.899
rws_waterwebservices      327           2           -2.620         -2.620          -1.852     0.911
                syke      705           2          -11.562        -14.124          -6.810     0.905
                usgs    12949          56           -5.902         -7.127          -4.879     0.918

## Which variables separate a consequential error on the reserved panel

               feature    auc       direction     n
          peak_overlap 0.8508 higher is worse 10820
warm_observed_fraction 0.8265  lower is worse 10820
  observed_peak_margin 0.7763  lower is worse 10820
           longest_run 0.7446 higher is worse 10820
      missing_fraction 0.7376 higher is worse 10820
         total_missing 0.7366 higher is worse 10820
        donor_corr_max 0.6454  lower is worse  9895
       donor_corr_mean 0.6170  lower is worse  9895
                n_runs 0.5758  lower is worse 10820
    seasonal_amplitude 0.5433 higher is worse 10820
        train_resid_sd 0.5328 higher is worse 10820
      n_visible_donors 0.5242  lower is worse 10820
       train_metric_sd 0.5239 higher is worse 10820
   donor_coverage_mean 0.5137  lower is worse 10466

## Verdict

```json
{
  "reserved_networks_opened": true,
  "opened_on": "2026-09-23",
  "n_cases": 10820,
  "n_networks": 36,
  "n_station_years": 1069,
  "primary": {
    "retention": 0.7,
    "contrast_points": -7.129654079746501,
    "ci_points": [
      -8.965660197802626,
      -5.3573631548047524
    ],
    "declared_effect_points": 5.0,
    "passes_effect_size": true,
    "passes_interval_excludes_zero": true,
    "passes": true
  },
  "coverage": {
    "marginal": 0.9085027726432532,
    "passes_marginal_band": true,
    "conditional_min": 0.8634190077704722,
    "conditional_max": 0.949389523434423,
    "passes_conditional_band": true
  },
  "by_donor_regime": {
    "none": {
      "point": -0.06635802469135803,
      "low": -0.09578979449669105,
      "high": -0.04653941879207358,
      "se": 0.012361365797016594,
      "n_clusters": 24.0,
      "retention": 0.7,
      "tolerance_c": 0.5
    },
    "rich": {
      "point": -0.07154046997389034,
      "low": -0.10408404710845094,
      "high": -0.04151051107522227,
      "se": 0.015358102553685372,
      "n_clusters": 11.0,
      "retention": 0.7,
      "tolerance_c": 0.5
    },
    "sparse": {
      "point": -0.06686046511627906,
      "low": -0.08673068684103281,
      "high": -0.046766476833742514,
      "se": 0.010345172016226657,
      "n_clusters": 30.0,
      "retention": 0.7,
      "tolerance_c": 0.5
    }
  }
}
```
