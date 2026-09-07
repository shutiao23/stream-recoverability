# Step 2 analysis

- networks scored: 42 / 42
- missing: none
- stations: 225
- rows: 303426

## Mean MAE benefit by duration (same-information recoverers)

               recoverer  gap_length  n_placements  benefit_mean  harmful_rate  hottest_30_benefit
        donor_only_ridge           7          4380      0.937589      0.118721            0.012825
         doy_climatology           7          4380      0.000000      0.000000            0.000000
           linear_interp           7          4380      0.830395      0.147945            0.015634
 ridge_neighbor_boundary           7          4380      1.014182      0.071918            0.016815
      smooth_climatology           7          4380      0.044325      0.392694            0.000715
  xgb_longblock_boundary           7          4380      0.910246      0.117580            0.011591
xgb_longblock_noboundary           7          4380      0.893399      0.125799            0.011137
   xgb_neighbor_boundary           7          4380      0.998620      0.071689            0.015106
 xgb_neighbor_noboundary           7          4380      0.906971      0.123288            0.011476
        donor_only_ridge          14          4380      0.923224      0.095434            0.016882
         doy_climatology          14          4380      0.000000      0.000000            0.000000
           linear_interp          14          4380      0.632625      0.193836            0.014194
 ridge_neighbor_boundary          14          4380      0.897958      0.073059            0.019845
      smooth_climatology          14          4380      0.044512      0.360959            0.000386
  xgb_longblock_boundary          14          4380      0.896751      0.089726            0.016299
xgb_longblock_noboundary          14          4380      0.883627      0.098630            0.015457
   xgb_neighbor_boundary          14          4380      0.891481      0.071005            0.018792
 xgb_neighbor_noboundary          14          4380      0.898282      0.091781            0.015979
        donor_only_ridge          30          4380      0.905857      0.079909            0.032591
         doy_climatology          30          4380      0.000000      0.000000            0.000000
           linear_interp          30          4380      0.395548      0.269635            0.021549
 ridge_neighbor_boundary          30          4380      0.754544      0.095890            0.034711
      smooth_climatology          30          4380      0.043713      0.320320            0.000119
  xgb_longblock_boundary          30          4380      0.882217      0.070776            0.032731
xgb_longblock_noboundary          30          4380      0.870464      0.078539            0.030999
   xgb_neighbor_boundary          30          4380      0.750996      0.088128            0.034916
 xgb_neighbor_noboundary          30          4380      0.886516      0.072146            0.032202
        donor_only_ridge          60          4380      0.909208      0.062557            0.129874
         doy_climatology          60          4380      0.000000      0.000000            0.000000
           linear_interp          60          4380      0.100744      0.416438            0.016210
 ridge_neighbor_boundary          60          4380      0.566978      0.173516            0.068566
      smooth_climatology          60          4380      0.044147      0.255251           -0.002092
  xgb_longblock_boundary          60          4380      0.874060      0.059361            0.116224
xgb_longblock_noboundary          60          4380      0.865561      0.064155            0.112872
   xgb_neighbor_boundary          60          4380      0.567733      0.162100            0.061401
 xgb_neighbor_noboundary          60          4380      0.881931      0.057991            0.117600
        donor_only_ridge          90          4380      0.901564      0.050685            0.159447
         doy_climatology          90          4380      0.000000      0.000000            0.000000
           linear_interp          90          4380     -0.204852      0.556164           -0.107962
 ridge_neighbor_boundary          90          4380      0.361161      0.257991           -0.020673
      smooth_climatology          90          4380      0.044349      0.218037           -0.003684
  xgb_longblock_boundary          90          4380      0.873915      0.049315            0.151645
xgb_longblock_noboundary          90          4380      0.868191      0.053425            0.150423
   xgb_neighbor_boundary          90          4380      0.367596      0.255023           -0.028336
 xgb_neighbor_noboundary          90          4380      0.882745      0.049543            0.155280
        donor_only_ridge         120          2532      0.903905      0.047788            0.264525
         doy_climatology         120          2532      0.000000      0.000000            0.000000
           linear_interp         120          2532     -0.799802      0.735782           -0.468803
 ridge_neighbor_boundary         120          2532     -0.020604      0.409953           -0.253892
      smooth_climatology         120          2532      0.042338      0.211690           -0.009380
  xgb_longblock_boundary         120          2532      0.873938      0.048973            0.236407
xgb_longblock_noboundary         120          2532      0.871349      0.048578            0.238616
   xgb_neighbor_boundary         120          2532     -0.012869      0.407188           -0.292263
 xgb_neighbor_noboundary         120          2532      0.885232      0.042259            0.245253
        donor_only_ridge         150          2454      0.909205      0.037490            0.342567
         doy_climatology         150          2454      0.000000      0.000000            0.000000
           linear_interp         150          2454     -1.275571      0.834148           -0.831070
 ridge_neighbor_boundary         150          2454     -0.271780      0.518745           -0.457438
      smooth_climatology         150          2454      0.043693      0.188672           -0.010495
  xgb_longblock_boundary         150          2454      0.885498      0.032600            0.315830
xgb_longblock_noboundary         150          2454      0.884266      0.031785            0.318805
   xgb_neighbor_boundary         150          2454     -0.265486      0.521597           -0.521762
 xgb_neighbor_noboundary         150          2454      0.897525      0.029747            0.328904
        donor_only_ridge         180          3948      0.916441      0.035461            0.431045
         doy_climatology         180          3948      0.000000      0.000000            0.000000
           linear_interp         180          3948     -2.053039      0.922746           -1.485240
 ridge_neighbor_boundary         180          3948     -0.759108      0.650963           -0.901187
      smooth_climatology         180          3948      0.042014      0.167427           -0.016400
  xgb_longblock_boundary         180          3948      0.893540      0.029635            0.401243
xgb_longblock_noboundary         180          3948      0.895837      0.027862            0.406172
   xgb_neighbor_boundary         180          3948     -0.720289      0.644630           -0.974841
 xgb_neighbor_noboundary         180          3948      0.905548      0.025583            0.416572
        donor_only_ridge         365          2880      0.952020      0.009375            1.043625
         doy_climatology         365          2880      0.000000      0.000000            0.000000
           linear_interp         365          2880     -4.546255      0.999653           -6.734372
 ridge_neighbor_boundary         365          2880     -2.306389      0.905903           -3.943706
      smooth_climatology         365          2880      0.041644      0.089931           -0.041014
  xgb_longblock_boundary         365          2880      0.924025      0.013194            0.956912
xgb_longblock_noboundary         365          2880      0.932641      0.006944            0.983370
   xgb_neighbor_boundary         365          2880     -2.157139      0.903125           -4.069303
 xgb_neighbor_noboundary         365          2880      0.939518      0.006597            1.015245

## Fraction of stations with an observed MAE-benefit crossing

                          n_stations  frac_crossed  n_right_censored
recoverer                                                           
donor_only_ridge                 219      0.018265          0.981735
doy_climatology                  219      0.000000          1.000000
linear_interp                    219      0.995434          0.004566
ridge_neighbor_boundary          219      0.821918          0.178082
smooth_climatology               219      0.146119          0.853881
xgb_longblock_boundary           219      0.041096          0.958904
xgb_longblock_noboundary         219      0.036530          0.963470
xgb_neighbor_boundary            219      0.808219          0.191781
xgb_neighbor_noboundary          219      0.031963          0.968037

## Long-gap mean benefit

recoverer   donor_only_ridge  doy_climatology  linear_interp  ridge_neighbor_boundary  smooth_climatology  xgb_longblock_boundary  xgb_longblock_noboundary  xgb_neighbor_boundary  xgb_neighbor_noboundary
gap_length                                                                                                                                                                                                 
180                 0.916441              0.0      -2.053039                -0.759108            0.042014                0.893540                  0.895837              -0.720289                 0.905548
365                 0.952020              0.0      -4.546255                -2.306389            0.041644                0.924025                  0.932641              -2.157139                 0.939518

- xgb_neighbor_boundary @180d benefit: -0.720
- xgb_longblock_boundary @180d benefit: 0.894
- donor_only_ridge @180d benefit: 0.916
- withdraw universal threshold law: True
- development recoverer if freeze now: donor_only_ridge
