# Step 6 — calibration as decision module

## A. Archive admission at ≤5% false-admit (0.5 °C)

                 panel                      rule                              task  risk_cap  retention_at_risk_cap  false_admit_rate_at_risk_cap  n_admitted_at_risk_cap  false_admit_rate_at_70  n_candidates  n_networks  tolerance_c
reserved_retrospective               length_rule archive_admission_ranked_risk_cap      0.05               0.520000                      0.047636                    5626                0.086744         10820          36          NaN
reserved_retrospective         peak_overlap_rule archive_admission_ranked_risk_cap      0.05               0.730000                      0.046841                    7899                0.037629         10820          36          NaN
reserved_retrospective        uncalibrated_bound archive_admission_ranked_risk_cap      0.05               0.780000                      0.046564                    8440                0.025350         10820          36          NaN
reserved_retrospective          calibrated_bound archive_admission_ranked_risk_cap      0.05               0.780000                      0.046564                    8440                0.025350         10820          36          NaN
reserved_retrospective uncalibrated_bound_le_tol  archive_admission_absolute_bound       NaN               0.662200                      0.017725                    7165                     NaN         10820          36          0.5
reserved_retrospective   calibrated_bound_le_tol  archive_admission_absolute_bound       NaN               0.675139                      0.020260                    7305                     NaN         10820          36          0.5
        wave2_designed               length_rule archive_admission_ranked_risk_cap      0.05               0.550000                      0.048191                    7159                0.087138         13017          49          NaN
        wave2_designed         peak_overlap_rule archive_admission_ranked_risk_cap      0.05               0.740000                      0.046714                    9633                0.033911         13017          49          NaN
        wave2_designed        uncalibrated_bound archive_admission_ranked_risk_cap      0.05               0.790000                      0.048818                   10283                0.023486         13017          49          NaN
        wave2_designed          calibrated_bound archive_admission_ranked_risk_cap      0.05               0.790000                      0.048818                   10283                0.023486         13017          49          NaN
        wave2_designed uncalibrated_bound_le_tol  archive_admission_absolute_bound       NaN               0.620727                      0.012005                    8080                     NaN         13017          49          0.5
        wave2_designed   calibrated_bound_le_tol  archive_admission_absolute_bound       NaN               0.636245                      0.013523                    8282                     NaN         13017          49          0.5

## Calibration retention contrast (calibrated − uncalibrated), pp

[
  {
    "panel": "reserved_retrospective",
    "contrast": "calibrated_minus_uncalibrated_retention_at_risk_cap_5pct",
    "point_pp": 0.0,
    "ci_low_pp": 0.0,
    "ci_high_pp": 0.0,
    "n_clusters": 36
  },
  {
    "panel": "wave2_designed",
    "contrast": "calibrated_minus_uncalibrated_retention_at_risk_cap_5pct",
    "point_pp": 0.0,
    "ci_low_pp": 0.0,
    "ci_high_pp": 0.0,
    "n_clusters": 49
  }
]

## B. Threshold judgment (same candidate pool)

                 panel  threshold_c                    rule               task  n_candidates  n_networks  share_judged  share_abstained  misclassification_among_judged  false_negative_among_judged  false_positive_among_judged  n_correct_judgments  n_incorrect_judgments  n_abstentions
reserved_retrospective         18.0         reconstruct_all threshold_judgment         10820          36      1.000000         0.000000                        0.015896                     0.010259                     0.005638                10648                    172              0
reserved_retrospective         18.0        length_screen_70 threshold_judgment         10820          36      0.700000         0.300000                        0.011883                     0.006866                     0.005017                 7484                     90           3246
reserved_retrospective         18.0    calibrated_screen_70 threshold_judgment         10820          36      0.700000         0.300000                        0.003301                     0.001980                     0.001320                 7549                     25           3246
reserved_retrospective         18.0     interval_abstention threshold_judgment         10820          36      0.931238         0.068762                        0.001886                     0.001389                     0.000496                10057                     19            744
reserved_retrospective         18.0 screen70_and_abstention threshold_judgment         10820          36      0.683364         0.316636                        0.000270                     0.000135                     0.000135                 7392                      2           3426
reserved_retrospective         20.0         reconstruct_all threshold_judgment         10820          36      1.000000         0.000000                        0.018484                     0.010351                     0.008133                10620                    200              0
reserved_retrospective         20.0        length_screen_70 threshold_judgment         10820          36      0.700000         0.300000                        0.013467                     0.006470                     0.006998                 7472                    102           3246
reserved_retrospective         20.0    calibrated_screen_70 threshold_judgment         10820          36      0.700000         0.300000                        0.004225                     0.002377                     0.001848                 7542                     32           3246
reserved_retrospective         20.0     interval_abstention threshold_judgment         10820          36      0.924214         0.075786                        0.003500                     0.001100                     0.002400                 9965                     35            820
reserved_retrospective         20.0 screen70_and_abstention threshold_judgment         10820          36      0.677357         0.322643                        0.000819                     0.000546                     0.000273                 7323                      6           3491
        wave2_designed         18.0         reconstruct_all threshold_judgment         13017          49      1.000000         0.000000                        0.003995                     0.001767                     0.002228                12965                     52              0
        wave2_designed         18.0        length_screen_70 threshold_judgment         13017          49      0.700008         0.299992                        0.002634                     0.000878                     0.001756                 9088                     24           3905
        wave2_designed         18.0    calibrated_screen_70 threshold_judgment         13017          49      0.700008         0.299992                        0.000768                     0.000439                     0.000329                 9105                      7           3905
        wave2_designed         18.0     interval_abstention threshold_judgment         13017          49      0.974649         0.025351                        0.000788                     0.000236                     0.000552                12677                     10            330
        wave2_designed         18.0 screen70_and_abstention threshold_judgment         13017          49      0.694937         0.305063                        0.000442                     0.000332                     0.000111                 9042                      4           3971
        wave2_designed         20.0         reconstruct_all threshold_judgment         13017          49      1.000000         0.000000                        0.015518                     0.009987                     0.005531                12815                    202              0
        wave2_designed         20.0        length_screen_70 threshold_judgment         13017          49      0.700008         0.299992                        0.008670                     0.005926                     0.002744                 9033                     79           3905
        wave2_designed         20.0    calibrated_screen_70 threshold_judgment         13017          49      0.700008         0.299992                        0.003841                     0.003183                     0.000658                 9077                     35           3905
        wave2_designed         20.0     interval_abstention threshold_judgment         13017          49      0.943382         0.056618                        0.001384                     0.000163                     0.001221                12263                     17            737
        wave2_designed         20.0 screen70_and_abstention threshold_judgment         13017          49      0.689022         0.310978                        0.000223                     0.000111                     0.000111                 8967                      2           4048

## Success checklist

{
  "reserved_retrospective": {
    "calibrated_retention": 0.78,
    "peak_overlap_retention": 0.73,
    "uncalibrated_retention": 0.78,
    "cal_minus_peak_pp": 5.000000000000004,
    "meets_plus5_vs_peak": true,
    "cal_minus_raw_pp": 0.0
  },
  "wave2_designed": {
    "calibrated_retention": 0.79,
    "peak_overlap_retention": 0.74,
    "uncalibrated_retention": 0.79,
    "cal_minus_peak_pp": 5.000000000000004,
    "meets_plus5_vs_peak": true,
    "cal_minus_raw_pp": 0.0
  },
  "threshold": {
    "reserved_retrospective|thr=18.0": {
      "abstention_share_judged": 0.9312384473197782,
      "abstention_misclf": 0.0018856689162366018,
      "screen70_share_judged": 0.7,
      "screen70_misclf": 0.003300765777660417,
      "abstention_judges_more": true,
      "abstention_misclf_le_0.5pct": true
    },
    "reserved_retrospective|thr=20.0": {
      "abstention_share_judged": 0.9242144177449169,
      "abstention_misclf": 0.0035,
      "screen70_share_judged": 0.7,
      "screen70_misclf": 0.004224980195405334,
      "abstention_judges_more": true,
      "abstention_misclf_le_0.5pct": true
    },
    "wave2_designed|thr=18.0": {
      "abstention_share_judged": 0.9746485365291542,
      "abstention_misclf": 0.0007882084023015686,
      "screen70_share_judged": 0.7000076822616579,
      "screen70_misclf": 0.0007682177348551361,
      "abstention_judges_more": true,
      "abstention_misclf_le_0.5pct": true
    },
    "wave2_designed|thr=20.0": {
      "abstention_share_judged": 0.9433817315817776,
      "abstention_misclf": 0.0013843648208469055,
      "screen70_share_judged": 0.7000076822616579,
      "screen70_misclf": 0.0038410886742756803,
      "abstention_judges_more": true,
      "abstention_misclf_le_0.5pct": true
    }
  }
}

Ranking-only frontiers cannot prove calibration value; this module isolates absolute-scale admit / abstain decisions.

