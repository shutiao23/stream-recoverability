# R2-03 three windows and the exact identity

## Identity check

n_cases_checked                                     9.449000e+03
max_abs_identity_residual_C                         1.629807e-13
min_false_peak_channel_C                           -1.009470e-13
share_false_peak_channel_negative_beyond_1e-9       0.000000e+00
share_hide_channel_zero_when_true_window_visible    1.000000e+00

## Hiding channel and false-peak channel by true hidden-share class

     reconstructor true_hidden_class  n_cases  mean_abs_error_C  mean_abs_error_lo  mean_abs_error_hi  mean_hide_channel_C  hide_lo  hide_hi  mean_false_peak_channel_C  false_lo  false_hi  share_false_peak_cases  share_lo  share_hi
         air_ridge              none      769             0.025              0.013              0.039                0.000    0.000    0.000                      0.025     0.013     0.039                   0.046     0.023     0.071
         air_ridge           partial      749             0.469              0.367              0.602               -0.395   -0.645   -0.202                      0.169     0.116     0.238                   0.348     0.273     0.434
         air_ridge               all      378             0.848              0.663              1.100               -0.712   -1.112   -0.400                      0.176     0.115     0.257                   0.365     0.283     0.455
         air_ridge            pooled     1896             0.365              0.279              0.467               -0.298   -0.465   -0.161                      0.112     0.078     0.151                   0.229     0.184     0.278
       donor_ridge              none      750             0.017              0.006              0.029                0.000    0.000    0.000                      0.017     0.006     0.029                   0.036     0.016     0.056
       donor_ridge           partial      736             0.252              0.186              0.315               -0.085   -0.149   -0.033                      0.060     0.035     0.091                   0.156     0.096     0.220
       donor_ridge               all      370             0.437              0.318              0.550               -0.172   -0.296   -0.064                      0.063     0.033     0.107                   0.146     0.088     0.216
       donor_ridge            pooled     1856             0.194              0.139              0.245               -0.068   -0.114   -0.027                      0.043     0.023     0.067                   0.106     0.063     0.148
   doy_climatology              none      772             0.060              0.039              0.086                0.000    0.000    0.000                      0.060     0.039     0.084                   0.093     0.074     0.113
   doy_climatology           partial      749             0.589              0.474              0.715               -0.362   -0.453   -0.282                      0.316     0.266     0.373                   0.571     0.519     0.628
   doy_climatology               all      378             0.918              0.736              1.099               -0.751   -0.919   -0.607                      0.433     0.353     0.516                   0.722     0.663     0.781
   doy_climatology            pooled     1899             0.440              0.359              0.524               -0.292   -0.355   -0.240                      0.235     0.199     0.274                   0.407     0.382     0.431
     linear_interp              none      772             0.012              0.005              0.020                0.000    0.000    0.000                      0.012     0.005     0.020                   0.026     0.013     0.044
     linear_interp           partial      749             0.374              0.309              0.455               -0.316   -0.390   -0.252                      0.189     0.156     0.225                   0.431     0.376     0.480
     linear_interp               all      378             1.256              1.027              1.550               -2.232   -2.640   -1.889                      1.023     0.854     1.188                   0.934     0.912     0.957
     linear_interp            pooled     1899             0.402              0.331              0.483               -0.569   -0.668   -0.476                      0.283     0.240     0.324                   0.367     0.337     0.394
smooth_climatology              none      772             0.056              0.034              0.084                0.000    0.000    0.000                      0.056     0.033     0.082                   0.080     0.061     0.099
smooth_climatology           partial      749             0.561              0.460              0.665               -0.410   -0.512   -0.318                      0.291     0.242     0.342                   0.543     0.490     0.605
smooth_climatology               all      378             0.923              0.731              1.112               -0.811   -0.995   -0.656                      0.376     0.303     0.445                   0.593     0.534     0.663
smooth_climatology            pooled     1899             0.428              0.344              0.515               -0.323   -0.393   -0.261                      0.213     0.177     0.248                   0.365     0.337     0.395

## Misaligned minus aligned, pooled and within hidden-share classes

     reconstructor                          stratum                           contrast  point_C   lo_C   hi_C  n_misaligned  n_aligned  n_networks  share_misaligned
         air_ridge                           pooled misaligned_minus_aligned_abs_error    0.488  0.354  0.653           954        942          12             0.503
         air_ridge                             none misaligned_minus_aligned_abs_error    0.441  0.341  0.521            44        725          10             0.057
         air_ridge                          partial misaligned_minus_aligned_abs_error    0.185  0.071  0.289           584        165          12             0.780
         air_ridge                              all misaligned_minus_aligned_abs_error   -0.352 -0.792 -0.090           326         52          11             0.862
         air_ridge clim_class_x_true_class_weighted misaligned_minus_aligned_abs_error    0.168  0.065  0.247           954        942          12             0.503
       donor_ridge                           pooled misaligned_minus_aligned_abs_error    0.315  0.225  0.387           670       1186          12             0.361
       donor_ridge                             none misaligned_minus_aligned_abs_error    0.300  0.171  0.393            42        708          11             0.056
       donor_ridge                          partial misaligned_minus_aligned_abs_error    0.203  0.140  0.258           398        338          12             0.541
       donor_ridge                              all misaligned_minus_aligned_abs_error    0.161  0.083  0.232           230        140          12             0.622
       donor_ridge clim_class_x_true_class_weighted misaligned_minus_aligned_abs_error    0.206  0.143  0.259           670       1186          12             0.361
   doy_climatology                           pooled misaligned_minus_aligned_abs_error    0.656  0.524  0.790          1144        755          12             0.602
   doy_climatology                             none misaligned_minus_aligned_abs_error    0.548  0.378  0.745            85        687          12             0.110
   doy_climatology                          partial misaligned_minus_aligned_abs_error    0.172  0.104  0.231           689         60          11             0.920
   doy_climatology                              all misaligned_minus_aligned_abs_error    0.104 -0.391  0.442           370          8           4             0.979
   doy_climatology clim_class_x_true_class_weighted misaligned_minus_aligned_abs_error    0.190  0.070  0.259          1144        755          12             0.602
     linear_interp                           pooled misaligned_minus_aligned_abs_error    0.657  0.545  0.787          1049        850          12             0.552
     linear_interp                             none misaligned_minus_aligned_abs_error    0.248  0.152  0.318            36        736          12             0.047
     linear_interp                          partial misaligned_minus_aligned_abs_error    0.095  0.040  0.143           635        114          12             0.848
     linear_interp                              all misaligned_minus_aligned_abs_error      NaN    NaN    NaN             0          0           0             1.000
     linear_interp clim_class_x_true_class_weighted misaligned_minus_aligned_abs_error    0.130  0.069  0.173          1049        850          12             0.552
smooth_climatology                           pooled misaligned_minus_aligned_abs_error    0.631  0.519  0.742          1099        800          12             0.579
smooth_climatology                             none misaligned_minus_aligned_abs_error    0.542  0.345  0.781            80        692          12             0.104
smooth_climatology                          partial misaligned_minus_aligned_abs_error    0.157  0.065  0.237           653         96          12             0.872
smooth_climatology                              all misaligned_minus_aligned_abs_error    0.240 -0.249  0.442           366         12           6             0.968
smooth_climatology clim_class_x_true_class_weighted misaligned_minus_aligned_abs_error    0.230  0.113  0.301          1099        800          12             0.579

## Distances between the three windows (days)

     reconstructor                            pair  median_days  p90_days  share_equal  share_ge_7_days  share_ge_30_days
         air_ridge          climatological_vs_true         12.0      29.0        0.043            0.706             0.095
         air_ridge           reconstructed_vs_true          1.0      20.0        0.497            0.261             0.052
         air_ridge reconstructed_vs_climatological         12.0      30.0        0.034            0.703             0.106
       donor_ridge          climatological_vs_true         12.0      29.0        0.044            0.703             0.097
       donor_ridge           reconstructed_vs_true          0.0      13.0        0.639            0.149             0.036
       donor_ridge reconstructed_vs_climatological         12.0      30.0        0.044            0.694             0.103
   doy_climatology          climatological_vs_true         12.0      29.0        0.043            0.706             0.095
   doy_climatology           reconstructed_vs_true          3.0      26.0        0.398            0.400             0.071
   doy_climatology reconstructed_vs_climatological          9.0      28.0        0.092            0.608             0.080
     linear_interp          climatological_vs_true         12.0      29.0        0.043            0.706             0.095
     linear_interp           reconstructed_vs_true          1.0      32.0        0.448            0.367             0.116
     linear_interp reconstructed_vs_climatological         14.0      33.0        0.024            0.771             0.171
smooth_climatology          climatological_vs_true         12.0      29.0        0.043            0.706             0.095
smooth_climatology           reconstructed_vs_true          2.0      26.0        0.421            0.395             0.068
smooth_climatology reconstructed_vs_climatological          9.0      28.0        0.070            0.597             0.088

## Climatological design class vs true hidden-share class (day-of-year climatology)

climatological_class true_class  n_cases  mean_abs_error_C  median_abs_clim_minus_true_days  share_of_climatological_class
                full        all      279             0.951                              7.0                          0.441
                full       none       27             0.586                             33.0                          0.043
                full    partial      327             0.719                             15.0                          0.517
                none       none      594             0.005                             12.0                          0.938
                none    partial       39             0.232                             21.0                          0.062
             partial        all       99             0.827                             21.0                          0.156
             partial       none      151             0.185                             22.0                          0.239
             partial    partial      383             0.515                              7.0                          0.605

## Interventions on the gap residuals

     reconstructor true_hidden_class  n_cases  recorded_C  recorded_lo  recorded_hi  permuted_within_gap_C  permuted_within_gap_lo  permuted_within_gap_hi  mean_removed_C  mean_removed_lo  mean_removed_hi  mean_only_C  mean_only_lo  mean_only_hi  permuted_minus_recorded_C  permuted_minus_recorded_lo  permuted_minus_recorded_hi  mean_removed_minus_recorded_C  mean_removed_minus_recorded_lo  mean_removed_minus_recorded_hi  mean_only_minus_recorded_C  mean_only_minus_recorded_lo  mean_only_minus_recorded_hi
         air_ridge            pooled     1896       0.365        0.284        0.469                  0.268                   0.218                   0.321           0.173            0.121            0.244        0.266         0.216         0.319                     -0.097                      -0.156                      -0.060                         -0.192                          -0.231                          -0.152                      -0.099                       -0.153                       -0.060
         air_ridge              none      769       0.025        0.012        0.039                  0.022                   0.010                   0.036           0.003            0.001            0.006        0.020         0.008         0.034                     -0.004                      -0.012                       0.003                         -0.022                          -0.033                          -0.010                      -0.005                       -0.013                        0.001
         air_ridge           partial      749       0.469        0.361        0.606                  0.361                   0.299                   0.428           0.220            0.146            0.321        0.355         0.295         0.420                     -0.109                      -0.180                      -0.059                         -0.249                          -0.298                          -0.200                      -0.114                       -0.184                       -0.062
         air_ridge               all      378       0.848        0.657        1.114                  0.584                   0.469                   0.719           0.423            0.305            0.597        0.588         0.470         0.728                     -0.264                      -0.409                      -0.163                         -0.425                          -0.538                          -0.334                      -0.260                       -0.391                       -0.164
       donor_ridge            pooled     1856       0.194        0.140        0.245                  0.154                   0.112                   0.193           0.080            0.060            0.102        0.151         0.109         0.190                     -0.040                      -0.054                      -0.027                         -0.114                          -0.148                          -0.076                      -0.043                       -0.056                       -0.030
       donor_ridge              none      750       0.017        0.006        0.030                  0.010                   0.003                   0.020           0.004            0.001            0.009        0.009         0.003         0.019                     -0.007                      -0.013                      -0.002                         -0.012                          -0.022                          -0.005                      -0.008                       -0.016                       -0.002
       donor_ridge           partial      736       0.252        0.186        0.315                  0.206                   0.151                   0.261           0.101            0.076            0.128        0.201         0.145         0.256                     -0.046                      -0.063                      -0.029                         -0.151                          -0.201                          -0.101                      -0.051                       -0.070                       -0.035
       donor_ridge               all      370       0.437        0.308        0.567                  0.341                   0.247                   0.433           0.189            0.139            0.253        0.339         0.245         0.433                     -0.096                      -0.130                      -0.061                         -0.248                          -0.329                          -0.167                      -0.098                       -0.131                       -0.064
   doy_climatology            pooled     1899       0.440        0.352        0.526                  0.355                   0.294                   0.417           0.198            0.156            0.245        0.341         0.281         0.403                     -0.085                      -0.117                      -0.055                         -0.241                          -0.299                          -0.190                      -0.099                       -0.133                       -0.067
   doy_climatology              none      772       0.060        0.039        0.086                  0.051                   0.031                   0.075           0.012            0.008            0.018        0.045         0.024         0.069                     -0.009                      -0.017                      -0.001                         -0.048                          -0.069                          -0.030                      -0.015                       -0.025                       -0.007
   doy_climatology           partial      749       0.589        0.482        0.717                  0.489                   0.414                   0.575           0.265            0.200            0.342        0.466         0.394         0.550                     -0.100                      -0.145                      -0.058                         -0.324                          -0.408                          -0.250                      -0.123                       -0.167                       -0.074
   doy_climatology               all      378       0.918        0.729        1.106                  0.710                   0.588                   0.836           0.447            0.361            0.542        0.698         0.576         0.824                     -0.209                      -0.291                      -0.126                         -0.472                          -0.574                          -0.364                      -0.221                       -0.314                       -0.138
     linear_interp            pooled     1899       0.402        0.327        0.481                  0.352                   0.291                   0.412           0.204            0.169            0.242        0.358         0.296         0.418                     -0.050                      -0.072                      -0.029                         -0.198                          -0.242                          -0.158                      -0.044                       -0.066                       -0.023
     linear_interp              none      772       0.012        0.005        0.020                  0.013                   0.007                   0.021           0.006            0.002            0.010        0.011         0.006         0.018                      0.002                      -0.001                       0.004                         -0.006                          -0.012                          -0.001                      -0.000                       -0.003                        0.002
     linear_interp           partial      749       0.374        0.305        0.453                  0.340                   0.283                   0.405           0.224            0.185            0.271        0.330         0.276         0.391                     -0.034                      -0.056                      -0.016                         -0.149                          -0.189                          -0.114                      -0.044                       -0.071                       -0.022
     linear_interp               all      378       1.256        1.029        1.550                  1.067                   0.879                   1.289           0.569            0.477            0.697        1.122         0.925         1.360                     -0.189                      -0.277                      -0.113                         -0.687                          -0.844                          -0.547                      -0.134                       -0.212                       -0.057
smooth_climatology            pooled     1899       0.428        0.347        0.513                  0.344                   0.289                   0.403           0.206            0.165            0.254        0.333         0.278         0.391                     -0.083                      -0.114                      -0.055                         -0.222                          -0.272                          -0.174                      -0.095                       -0.128                       -0.066
smooth_climatology              none      772       0.056        0.034        0.084                  0.049                   0.028                   0.076           0.009            0.005            0.014        0.044         0.023         0.070                     -0.007                      -0.015                      -0.000                         -0.047                          -0.072                          -0.027                      -0.012                       -0.021                       -0.005
smooth_climatology           partial      749       0.561        0.462        0.668                  0.469                   0.400                   0.544           0.271            0.208            0.348        0.450         0.383         0.522                     -0.091                      -0.130                      -0.055                         -0.290                          -0.361                          -0.226                      -0.111                       -0.151                       -0.070
smooth_climatology               all      378       0.923        0.750        1.109                  0.699                   0.588                   0.820           0.479            0.400            0.573        0.693         0.579         0.815                     -0.224                      -0.311                      -0.143                         -0.444                          -0.549                          -0.338                      -0.231                       -0.325                       -0.149

## What a window switch costs

     reconstructor                      kind  n_cases  share_of_all_cases  median_abs_error_C  share_abs_error_le_0.1C  share_abs_error_le_0.5C  mean_false_peak_channel_C
         air_ridge overlapping shift (<30 d)      855               0.451               0.402                    0.149                    0.591                      0.184
         air_ridge  disjoint window (>=30 d)       99               0.052               0.588                    0.081                    0.444                      0.559
         air_ridge            all misaligned      954               0.503               0.418                    0.142                    0.575                      0.223
       donor_ridge overlapping shift (<30 d)      604               0.325               0.208                    0.321                    0.725                      0.083
       donor_ridge  disjoint window (>=30 d)       66               0.036               0.396                    0.121                    0.652                      0.447
       donor_ridge            all misaligned      670               0.361               0.229                    0.301                    0.718                      0.119
   doy_climatology overlapping shift (<30 d)     1009               0.531               0.493                    0.149                    0.501                      0.321
   doy_climatology  disjoint window (>=30 d)      135               0.071               0.633                    0.081                    0.437                      0.911
   doy_climatology            all misaligned     1144               0.602               0.503                    0.141                    0.494                      0.391
     linear_interp overlapping shift (<30 d)      828               0.436               0.347                    0.184                    0.607                      0.304
     linear_interp  disjoint window (>=30 d)      221               0.116               0.844                    0.086                    0.312                      1.294
     linear_interp            all misaligned     1049               0.552               0.430                    0.163                    0.545                      0.512
smooth_climatology overlapping shift (<30 d)      970               0.511               0.463                    0.166                    0.528                      0.306
smooth_climatology  disjoint window (>=30 d)      129               0.068               0.663                    0.062                    0.419                      0.830
smooth_climatology            all misaligned     1099               0.579               0.480                    0.154                    0.515                      0.367

