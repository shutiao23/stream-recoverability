# Step 14 — tables the manuscript promises

## Frontier at 70% retention, across tolerances

      panel            screen  rate_above_0.25  rate_above_0.5  rate_above_1.0  mean_abs_error_c  severe_underestimate_rate
development       certificate           0.0837          0.0293          0.0049            0.0658                     0.0031
development       length_rule           0.1706          0.0924          0.0357            0.1539                     0.0237
development peak_overlap_rule           0.1113          0.0564          0.0215            0.1011                     0.0134
development            random           0.2464          0.1497          0.0687            0.2430                     0.0488
development            oracle           0.0000          0.0000          0.0000            0.0231                     0.0000
   reserved       certificate           0.0713          0.0253          0.0037            0.0563                     0.0029
   reserved       length_rule           0.1722          0.0966          0.0343            0.1508                     0.0202
   reserved peak_overlap_rule           0.0922          0.0420          0.0119            0.0751                     0.0066
   reserved            random           0.2387          0.1439          0.0558            0.2159                     0.0366
   reserved            oracle           0.0000          0.0000          0.0000            0.0202                     0.0000

## Which estimator is used, and how far the air-driven branch reaches

      panel                 estimator  share_chosen_by_certificate  share_chosen_by_information_rule  mean_abs_error_when_chosen_c
development                 air_ridge                       0.0054                            0.0042                        0.5170
development               donor_ridge                       0.5483                            0.7809                        0.1970
development           doy_climatology                       0.1226                            0.0000                        0.4021
development             linear_interp                       0.2169                            0.0533                        0.1312
development        smooth_climatology                       0.1068                            0.1615                        0.4453
development __air_forcing_available__                       0.0226                               NaN                           NaN
   reserved                 air_ridge                       0.0006                            0.0024                        0.7316
   reserved               donor_ridge                       0.5876                            0.8073                        0.2041
   reserved           doy_climatology                       0.0709                            0.0000                        0.4599
   reserved             linear_interp                       0.2289                            0.0570                        0.1155
   reserved        smooth_climatology                       0.1119                            0.1333                        0.2528
   reserved __air_forcing_available__                       0.0085                               NaN                           NaN
