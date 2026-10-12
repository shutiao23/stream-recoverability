# Step 21 — which rivers are hard?

United States stations matched to GAGES-II basin characteristics: **140** stations on **57** networks. Signs were declared before the regressions were run.

## Rank correlations, network-clustered intervals

  predictor                target  n_stations  spearman_rho  ci_low  ci_high  p_value  excludes_zero                                                              expected_sign
    BFI_AVE       donor_synchrony         136       -0.1894 -0.4149   0.1000   0.0272          False     negative: groundwater damps the shared atmospheric signal donors carry
    CONTACT       donor_synchrony         136        0.2247 -0.0236   0.4386   0.0086          False negative: longer subsurface contact time decouples the stream from weather
log_storage       donor_synchrony         136       -0.1779 -0.3383   0.0103   0.0382          False                                                              none declared
   log_area       donor_synchrony         136       -0.0123 -0.2718   0.2479   0.8868          False                                                              none declared
ELEV_SITE_M       donor_synchrony         136       -0.2883 -0.4609  -0.0753   0.0007           True                                                              none declared
  SLOPE_PCT       donor_synchrony         136       -0.3087 -0.5124  -0.0715   0.0003           True                                                              none declared
    BFI_AVE        mean_abs_error         140       -0.1287 -0.2846   0.0651   0.1296          False     negative: groundwater damps the shared atmospheric signal donors carry
    CONTACT        mean_abs_error         140       -0.1423 -0.3939   0.0778   0.0934          False negative: longer subsurface contact time decouples the stream from weather
log_storage        mean_abs_error         140        0.1482 -0.0828   0.3222   0.0806          False                                                              none declared
   log_area        mean_abs_error         140       -0.1099 -0.3432   0.0790   0.1961          False                                                              none declared
ELEV_SITE_M        mean_abs_error         140        0.2404  0.0620   0.4326   0.0042           True                                                              none declared
  SLOPE_PCT        mean_abs_error         140        0.1318 -0.0388   0.3446   0.1205          False                                                              none declared
    BFI_AVE    consequential_rate         140       -0.0814 -0.2653   0.1194   0.3393          False     negative: groundwater damps the shared atmospheric signal donors carry
    CONTACT    consequential_rate         140       -0.1562 -0.3943   0.0556   0.0653          False negative: longer subsurface contact time decouples the stream from weather
log_storage    consequential_rate         140        0.1474 -0.0681   0.3129   0.0823          False                                                              none declared
   log_area    consequential_rate         140       -0.1171 -0.3495   0.0788   0.1684          False                                                              none declared
ELEV_SITE_M    consequential_rate         140        0.2545  0.0806   0.4321   0.0024           True                                                              none declared
  SLOPE_PCT    consequential_rate         140        0.1432 -0.0184   0.3550   0.0915          False                                                              none declared
    BFI_AVE      peak_magnitude_c         140       -0.4671 -0.5975  -0.2599   0.0000           True     negative: groundwater damps the shared atmospheric signal donors carry
    CONTACT      peak_magnitude_c         140        0.5217  0.3048   0.6719   0.0000           True negative: longer subsurface contact time decouples the stream from weather
log_storage      peak_magnitude_c         140        0.0119 -0.1540   0.2087   0.8888          False                                                              none declared
   log_area      peak_magnitude_c         140        0.2129  0.0004   0.4169   0.0116           True                                                              none declared
ELEV_SITE_M      peak_magnitude_c         140       -0.3135 -0.4829  -0.1563   0.0002           True                                                              none declared
  SLOPE_PCT      peak_magnitude_c         140       -0.5885 -0.7206  -0.3909   0.0000           True                                                              none declared
    BFI_AVE screening_gain_points         140       -0.0840 -0.2926   0.1302   0.3236          False     negative: groundwater damps the shared atmospheric signal donors carry
    CONTACT screening_gain_points         140       -0.0800 -0.3131   0.1247   0.3472          False negative: longer subsurface contact time decouples the stream from weather
log_storage screening_gain_points         140        0.0851 -0.1129   0.2509   0.3176          False                                                              none declared
   log_area screening_gain_points         140       -0.1207 -0.3287   0.0897   0.1556          False                                                              none declared
ELEV_SITE_M screening_gain_points         140        0.1513 -0.0234   0.3234   0.0743          False                                                              none declared
  SLOPE_PCT screening_gain_points         140        0.0451 -0.1333   0.2631   0.5968          False                                                              none declared

## Standardised multivariate coefficients

  predictor  standardised_coefficient          target     r2   n
    BFI_AVE                    0.0073 donor_synchrony 0.2203 136
    CONTACT                    0.0163 donor_synchrony 0.2203 136
log_storage                   -0.0628 donor_synchrony 0.2203 136
   log_area                    0.0332 donor_synchrony 0.2203 136
ELEV_SITE_M                   -0.0566 donor_synchrony 0.2203 136
  SLOPE_PCT                   -0.0522 donor_synchrony 0.2203 136
    BFI_AVE                   -0.0297  mean_abs_error 0.1324 140
    CONTACT                   -0.0121  mean_abs_error 0.1324 140
log_storage                    0.0229  mean_abs_error 0.1324 140
   log_area                   -0.0215  mean_abs_error 0.1324 140
ELEV_SITE_M                    0.0282  mean_abs_error 0.1324 140
  SLOPE_PCT                    0.0216  mean_abs_error 0.1324 140

## Outcomes by stratum

stratum  n_stations  median_value  donor_synchrony  mean_abs_error  consequential_rate  peak_magnitude_c  peak_interannual_sd_c  screening_gain_points    variable
    low          47       40.5000           0.6986          0.2181              0.1406           22.6595                 0.9838                 5.4946     BFI_AVE
 middle          46       59.9500           0.6959          0.2350              0.1578           20.9587                 0.9288                 6.1124     BFI_AVE
   high          47       72.6000           0.5942          0.2014              0.1400           18.0523                 0.7607                 5.0802     BFI_AVE
    low          47        0.0000           0.6822          0.2167              0.1395           19.7990                 0.8675                 5.6646 log_storage
 middle          46        1.7399           0.7179          0.1893              0.1352           22.4271                 0.7441                 4.5511 log_storage
   high          47        2.4562           0.5925          0.2474              0.1633           19.4757                 1.0577                 6.4382 log_storage
    low          47        2.2615           0.6732          0.2374              0.1566           19.3330                 0.9578                 5.6413    log_area
 middle          46        3.1754           0.6375          0.2214              0.1482           20.6553                 0.9454                 6.0479    log_area
   high          47        4.0723           0.6787          0.1954              0.1334           21.6757                 0.7705                 4.9965    log_area

## Directional tests from the literature

```json
{
  "n_stations": 140,
  "n_networks": 57,
  "johnson_groundwater_test": {
    "statement": "Johnson et al. (2021) report that filling can harm groundwater-influenced sites. Directional prediction: high baseflow index implies larger completed-year error.",
    "difference_high_minus_low_bfi_c": -0.042952340007241435,
    "ci": [
      -0.08109309687487858,
      -0.003653660391846295
    ],
    "supported": false
  },
  "reference_versus_disturbed": {
    "statement": "Directional prediction: reference basins are easier than disturbed ones.",
    "difference_ref_minus_nonref_c": 0.004334722474154451,
    "ci": [
      -0.0508418632023575,
      0.09336408470388062
    ],
    "supported": false
  },
  "expected_signs": {
    "BFI_AVE": "negative: groundwater damps the shared atmospheric signal donors carry",
    "CONTACT": "negative: longer subsurface contact time decouples the stream from weather",
    "STOR_NID_2009": "negative: upstream storage imposes a release regime donors do not share",
    "DRAIN_SQKM": "positive: thermal inertia makes large rivers track regional rather than local forcing",
    "ELEV_SITE_M": "none declared",
    "SLOPE_PCT": "none declared"
  }
}
```
