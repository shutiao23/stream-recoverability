# Step 3 — fixed-reconstructor crossed mechanism

Panel: 12 networks, 24 stations, 1899 crossed-class cases.
Note: air_available==0 on this panel; air_ridge omitted.

## Position contrasts (full − none °C) with network CIs

 length  point_C  ci_low_C  ci_high_C  n_networks  n_station_years  ci_excludes_zero      reconstructor                        contrast
     30 0.642211  0.546185   0.742566          12              211              True    doy_climatology full_minus_none_at_fixed_length
     60 0.867284  0.707071   1.037441          12              211              True    doy_climatology full_minus_none_at_fixed_length
     90 0.894555  0.758139   1.040268          12              211              True    doy_climatology full_minus_none_at_fixed_length
     30 0.594528  0.508311   0.684845          12              211              True smooth_climatology full_minus_none_at_fixed_length
     60 0.849204  0.690038   1.021189          12              211              True smooth_climatology full_minus_none_at_fixed_length
     90 0.882313  0.751153   1.021906          12              211              True smooth_climatology full_minus_none_at_fixed_length
     30 0.240283  0.199278   0.281956          12              208              True        donor_ridge full_minus_none_at_fixed_length
     60 0.364208  0.291734   0.439510          12              204              True        donor_ridge full_minus_none_at_fixed_length
     90 0.393764  0.312453   0.474855          12              203              True        donor_ridge full_minus_none_at_fixed_length
     30 0.340589  0.279930   0.397353          12              211              True      linear_interp full_minus_none_at_fixed_length
     60 0.746345  0.624965   0.871824          12              211              True      linear_interp full_minus_none_at_fixed_length
     90 1.309867  1.106803   1.510102          12              211              True      linear_interp full_minus_none_at_fixed_length

## Length contrasts (long − short °C) with network CIs

overlap_class   point_C  ci_low_C  ci_high_C  n_networks  n_station_years  ci_excludes_zero      reconstructor                          contrast
         full  0.253265  0.210696   0.292199          12              211              True    doy_climatology long_minus_short_at_fixed_overlap
         none  0.000921 -0.012952   0.018246          12              211             False    doy_climatology long_minus_short_at_fixed_overlap
      partial  0.024167 -0.042093   0.083099          12              211             False    doy_climatology long_minus_short_at_fixed_overlap
         full  0.287556  0.234919   0.331368          12              211              True smooth_climatology long_minus_short_at_fixed_overlap
         none -0.000230 -0.014052   0.016187          12              211             False smooth_climatology long_minus_short_at_fixed_overlap
      partial  0.038610 -0.026288   0.098993          12              211             False smooth_climatology long_minus_short_at_fixed_overlap
         full  0.153372  0.109152   0.195527          12              207              True        donor_ridge long_minus_short_at_fixed_overlap
         none  0.007099 -0.005317   0.019790          12              204             False        donor_ridge long_minus_short_at_fixed_overlap
      partial  0.014228  0.001044   0.027615          12              204              True        donor_ridge long_minus_short_at_fixed_overlap
         full  0.982581  0.824347   1.130249          12              211              True      linear_interp long_minus_short_at_fixed_overlap
         none  0.013303  0.005548   0.021570          12              211              True      linear_interp long_minus_short_at_fixed_overlap
      partial  0.158989  0.048684   0.249637          12              211              True      linear_interp long_minus_short_at_fixed_overlap

## Failure-mode rates

     reconstructor  n_cases  rate_false_peak  rate_climate_mismatch  rate_competing_peaks_proxy  rate_any_labelled  mean_abserr_when_false_peak
   doy_climatology     1899         0.023697               0.058978                    0.021590           0.088994                     1.202124
smooth_climatology     1899         0.021590               0.058978                    0.021590           0.089521                     1.186575
       donor_ridge     1856         0.005927               0.059806                    0.008082           0.071121                     0.914045
     linear_interp     1899         0.010532               0.058978                    0.019484           0.078462                     0.838086

## Stability across reconstructors

{
  "length_30": {
    "n_reconstructors": 4,
    "all_positive_full_worse": true,
    "all_ci_exclude_zero": true,
    "points_C": {
      "doy_climatology": 0.6422112902175275,
      "smooth_climatology": 0.5945276035874775,
      "donor_ridge": 0.24028305347244674,
      "linear_interp": 0.3405887549840431
    }
  },
  "length_60": {
    "n_reconstructors": 4,
    "all_positive_full_worse": true,
    "all_ci_exclude_zero": true,
    "points_C": {
      "doy_climatology": 0.867283942171304,
      "smooth_climatology": 0.8492041208001,
      "donor_ridge": 0.3642084815452163,
      "linear_interp": 0.7463452402921175
    }
  },
  "length_90": {
    "n_reconstructors": 4,
    "all_positive_full_worse": true,
    "all_ci_exclude_zero": true,
    "points_C": {
      "doy_climatology": 0.8945552336608578,
      "smooth_climatology": 0.882313416092461,
      "donor_ridge": 0.39376417685393955,
      "linear_interp": 1.309867486532291
    }
  }
}

Claim status: conditional risk / mechanism evidence only — not a dominance law.

