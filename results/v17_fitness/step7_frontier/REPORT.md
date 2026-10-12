# Steps 6-7 — the certificate and the retention-error frontier

Development cases: **40,704** on **110** networks. All certificates are out-of-fold: no network appears in its own fitting or calibration set.

## Share of retained station-years with hottest-30 error above 0.5 °C

screen     certificate  certificate_screen_only  estimator_disagreement  length_rule  missing_fraction_rule  oracle  peak_overlap_rule  random  warm_coverage_rule
retention                                                                                                                                                         
0.30            0.0010                   0.0006                  0.0050       0.0231                 0.0279  0.0000             0.0166  0.1512              0.0068
0.35            0.0020                   0.0015                  0.0046       0.0349                 0.0404  0.0000             0.0167  0.1513              0.0125
0.40            0.0028                   0.0022                  0.0047       0.0453                 0.0467  0.0000             0.0163  0.1521              0.0163
0.45            0.0045                   0.0041                  0.0052       0.0494                 0.0485  0.0000             0.0170  0.1526              0.0221
0.50            0.0078                   0.0081                  0.0122       0.0556                 0.0602  0.0000             0.0213  0.1511              0.0343
0.55            0.0116                   0.0123                  0.0187       0.0664                 0.0705  0.0000             0.0286  0.1496              0.0417
0.60            0.0179                   0.0186                  0.0276       0.0742                 0.0771  0.0000             0.0367  0.1492              0.0443
0.65            0.0220                   0.0234                  0.0375       0.0843                 0.0865  0.0000             0.0435  0.1484              0.0559
0.70            0.0293                   0.0311                  0.0485       0.0924                 0.0938  0.0000             0.0564  0.1497              0.0687
0.75            0.0393                   0.0410                  0.0620       0.0986                 0.1017  0.0000             0.0705  0.1491              0.0737
0.80            0.0522                   0.0541                  0.0773       0.1061                 0.1083  0.0000             0.0876  0.1492              0.0829
0.85            0.0679                   0.0696                  0.0931       0.1118                 0.1116  0.0000             0.1052  0.1489              0.0978
0.90            0.0885                   0.0908                  0.1112       0.1213                 0.1198  0.0541             0.1217  0.1485              0.1129
0.95            0.1139                   0.1167                  0.1302       0.1306                 0.1309  0.1039             0.1363  0.1488              0.1310
1.00            0.1456                   0.1487                  0.1487       0.1487                 0.1487  0.1487             0.1487  0.1487              0.1487

## Mean absolute error among retained station-years (°C)

screen     certificate  certificate_screen_only  estimator_disagreement  length_rule  missing_fraction_rule  oracle  peak_overlap_rule  random  warm_coverage_rule
retention                                                                                                                                                         
0.30            0.0040                   0.0037                  0.0094       0.0524                 0.0601  0.0000             0.0340  0.2450              0.0175
0.35            0.0070                   0.0067                  0.0086       0.0729                 0.0783  0.0000             0.0341  0.2443              0.0303
0.40            0.0113                   0.0110                  0.0086       0.0863                 0.0876  0.0000             0.0332  0.2446              0.0379
0.45            0.0173                   0.0173                  0.0100       0.0919                 0.0906  0.0000             0.0348  0.2435              0.0485
0.50            0.0251                   0.0257                  0.0232       0.1004                 0.1066  0.0006             0.0445  0.2440              0.0665
0.55            0.0338                   0.0350                  0.0379       0.1152                 0.1212  0.0030             0.0577  0.2426              0.0772
0.60            0.0438                   0.0453                  0.0559       0.1264                 0.1306  0.0074             0.0714  0.2423              0.0821
0.65            0.0538                   0.0560                  0.0736       0.1410                 0.1443  0.0140             0.0824  0.2415              0.0991
0.70            0.0658                   0.0680                  0.0912       0.1539                 0.1555  0.0231             0.1011  0.2430              0.1174
0.75            0.0801                   0.0822                  0.1106       0.1638                 0.1664  0.0351             0.1217  0.2424              0.1250
0.80            0.0968                   0.0990                  0.1306       0.1745                 0.1766  0.0511             0.1475  0.2421              0.1392
0.85            0.1167                   0.1192                  0.1544       0.1839                 0.1828  0.0726             0.1746  0.2423              0.1611
0.90            0.1430                   0.1463                  0.1823       0.1988                 0.1961  0.1016             0.1998  0.2413              0.1837
0.95            0.1797                   0.1839                  0.2130       0.2138                 0.2139  0.1461             0.2219  0.2412              0.2138
1.00            0.2361                   0.2416                  0.2416       0.2416                 0.2416  0.2416             0.2416  0.2416              0.2416

## Against the published fixed-length guidance, at equal retention

                                      rule  retention  rate_above_0.5  mean_abs_error_c  certificate_rate_above_0.5_at_equal_retention  certificate_mean_abs_error_at_equal_retention  absolute_points_saved
        length <= 49 d (Johnson, unfilled)     0.4646          0.0495            0.0922                                         0.0059                                         0.0194                 4.3674
length <= 140 d (Johnson, with imputation)     0.8355          0.1094            0.1793                                         0.0621                                         0.1095                 4.7282
                           length <= 180 d     0.9416          0.1276            0.2087                                         0.1091                                         0.1727                 1.8472

## Headline contrast, network-clustered bootstrap

Certificate minus fixed-length rule, in the rate of error above 0.5 °C at matched retention.
Negative means the certificate keeps a cleaner sample.

```json
{
  "retention_0.6": {
    "point": -0.056301695192858894,
    "low": -0.06783428944165786,
    "high": -0.04806677680902313,
    "se": 0.0051341621938253675,
    "n_clusters": 110,
    "retention": 0.6,
    "tolerance_c": 0.5
  },
  "retention_0.7": {
    "point": -0.06345418172884568,
    "low": -0.07120668285097914,
    "high": -0.05486145317140355,
    "se": 0.004187581182324614,
    "n_clusters": 110,
    "retention": 0.7,
    "tolerance_c": 0.5
  },
  "retention_0.8": {
    "point": -0.05457113902281731,
    "low": -0.0608567763163048,
    "high": -0.047849102838194935,
    "se": 0.003340442697551988,
    "n_clusters": 110,
    "retention": 0.8,
    "tolerance_c": 0.5
  },
  "retention_0.9": {
    "point": -0.032292405961674944,
    "low": -0.037883388401209125,
    "high": -0.02606998516267792,
    "se": 0.0030292569154600347,
    "n_clusters": 110,
    "retention": 0.9,
    "tolerance_c": 0.5
  }
}
```

## Conformal coverage at nominal 0.90

                     stratum       level     n  coverage  bound_coverage  median_width_c calibration
                         all    marginal 40704    0.8973          0.8956          0.5997       split
           donor_regime=none conditional  2512    0.8905          0.8901          0.8796       split
           donor_regime=rich conditional 25575    0.9058          0.9001          0.5552       split
         donor_regime=sparse conditional 12617    0.8815          0.8877          0.6617       split
         longest_run=(0, 30] conditional 16948    0.9133          0.9177          0.2058       split
        longest_run=(30, 90] conditional 11764    0.8896          0.8952          0.7310       split
       longest_run=(90, 180] conditional  9616    0.8900          0.8731          1.0745       split
      longest_run=(180, 400] conditional  2376    0.8514          0.8308          2.4883       split
peak_overlap=(-0.001, 0.001] conditional 17813    0.9224          0.9462          0.0795       split
   peak_overlap=(0.001, 0.5] conditional  9272    0.8903          0.8646          0.6996       split
   peak_overlap=(0.5, 1.001] conditional 13619    0.8694          0.8505          1.7058       split
                         all    marginal 40704    0.8973          0.8917          0.5997    mondrian
           donor_regime=none conditional  2512    0.8905          0.8941          0.8796    mondrian
           donor_regime=rich conditional 25575    0.9058          0.8828          0.5552    mondrian
         donor_regime=sparse conditional 12617    0.8815          0.9092          0.6617    mondrian
         longest_run=(0, 30] conditional 16948    0.9133          0.9148          0.2058    mondrian
        longest_run=(30, 90] conditional 11764    0.8896          0.8921          0.7310    mondrian
       longest_run=(90, 180] conditional  9616    0.8900          0.8693          1.0745    mondrian
      longest_run=(180, 400] conditional  2376    0.8514          0.8152          2.4883    mondrian
peak_overlap=(-0.001, 0.001] conditional 17813    0.9224          0.9455          0.0795    mondrian
   peak_overlap=(0.001, 0.5] conditional  9272    0.8903          0.8581          0.6996    mondrian
   peak_overlap=(0.5, 1.001] conditional 13619    0.8694          0.8441          1.7058    mondrian

## Self-selected operating point

```json
{
  "tolerance_c": 0.5,
  "retention": 0.6759286556603774,
  "rate_above_tolerance_retained": 0.026060407807218407,
  "rate_above_tolerance_excluded": 0.394890455613676,
  "mean_abs_error_retained": 0.06031834549852877
}
```
