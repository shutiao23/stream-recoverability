# Step 8 — what changes downstream (H4)

Stations with at least six complete years and one outage realization per year: **275** stations on **84** networks. The length-rule threshold is set to match the certificate's retention, so the comparison is at equal cost in discarded station-years.

## Trend in the annual thermal peak, exceedance counts, and hottest-year identification

           treatment  n_stations  slope_bias_c_per_year  slope_rmse_c_per_year  slope_mae_c_per_year  mean_years_kept  exceed18_bias_years  exceed20_bias_years  exceed20_mae_years  hottest_year_accuracy
   observed_days_all         275               -0.00341                0.14299               0.04369         12.99636             -0.79636             -0.75636             0.76364                0.82545
     reconstruct_all         275                0.00080                0.04406               0.01926         12.99636             -0.05455             -0.08000             0.13818                0.89091
     length_screened         251                0.00082                0.04823               0.02017         11.02909             -0.53403             -0.31554             0.43922                0.83273
certificate_screened         240                0.00306                0.04109               0.01872         10.95273              0.04967              0.06073             0.31274                0.83636

## The per-year product: exceedance of an ecological threshold

 threshold_c            treatment  retention  n_scored  misclassification_rate  false_negative_rate  false_positive_rate
        18.0    observed_days_all     1.0000      3823                  0.0612               0.0882               0.0048
        18.0      reconstruct_all     1.0000      3823                  0.0102               0.0104               0.0097
        18.0      length_screened     0.8569      3276                  0.0073               0.0078               0.0064
        18.0 certificate_screened     0.8480      3242                  0.0031               0.0022               0.0050
        20.0    observed_days_all     1.0000      3823                  0.0560               0.1148               0.0005
        20.0      reconstruct_all     1.0000      3823                  0.0107               0.0167               0.0051
        20.0      length_screened     0.8569      3276                  0.0061               0.0088               0.0035
        20.0 certificate_screened     0.8480      3242                  0.0031               0.0019               0.0043

## Trend sign errors

           treatment   n  sign_disagreement_rate  large_slope_error_rate
   observed_days_all 275                  0.0945                  0.2036
     reconstruct_all 275                  0.0582                  0.0982
     length_screened 251                  0.0518                  0.1036
certificate_screened 240                  0.0542                  0.1000

## Mean absolute slope error, each treatment minus the certificate

Positive means the treatment is worse than the certificate. Clustered by network.

```json
{
  "observed_days_all": {
    "point": 0.02497468797261466,
    "low": 0.009165368829207854,
    "high": 0.04502448742500462,
    "se": 0.00955048737263887,
    "n_clusters": 84
  },
  "reconstruct_all": {
    "point": 0.0005442859747519513,
    "low": -0.006575085400228366,
    "high": 0.007025826800385727,
    "se": 0.003461605952553967,
    "n_clusters": 84
  },
  "length_screened": {
    "point": 0.0014542684138580432,
    "low": -0.0073020813092245715,
    "high": 0.009045700189256798,
    "se": 0.004135178847871934,
    "n_clusters": 84
  }
}
```
