# 审稿问题修正与研究交付（2026-10-27）

主命题是：不完整记录可以保留极值信息，但年度恢复、发布数值和趋势推断需要分别验证。复杂估计器不必胜出；未通过的科学结论保留为未通过。

原始结果保留在原目录；本次修订结果位于 results/wrr_review_response_20261027。年度点值及分位数对已观测窗口下界一致投影，整档案两种方法在原源域校准组重新计算偏移；20次年度源域对比则对原有校准结果做相同的事后投影。外尾采用相邻正态分位数间距延伸，这是需要敏感性评价的假设。

| 主张         | 主要比较或事实                                       | 主要指标                               | 结果及限制                                                                                  | 证据                                                                            |
|:-------------|:-----------------------------------------------------|:---------------------------------------|:--------------------------------------------------------------------------------------------|:--------------------------------------------------------------------------------|
| 观测事实     | 不完整年份可以已观测窗口否定完整年纪录               | 观测窗口下界减完整年纪录               | 20/96站、35站年；不确定唯一最热年                                                           | observed_records/observed_record_certificates.csv                               |
| 年度恢复     | 目标指标恢复优于简单点填补，但不预设优于合格随机重建 | H30 MAE、CRPS、区间覆盖和宽度          | 同等校准对照；不主张D2普遍必要                                                              | results/wrr_review_response_20261027/annual/source_scorecard_summary.csv        |
| 整档案趋势   | 统一隐藏多年观测后，保留集合与估计器分别影响趋势误差 | 趋势RMSE、配对MSE主效应与交互          | 42站、20次重复；邻站仍可观测                                                                | results/wrr_review_response_20261027/whole_archive/factorial_paired_summary.csv |
| 联合不确定性 | 年度校准不能替代趋势校准                             | 缺失分量覆盖、区间宽度、评分和可用率   | 前推长缺口覆盖不足；任务校准支持不足                                                        | results/wrr_review_response_20261027/whole_archive/paired_task_intervals.csv    |
| 输出边界     | 数值、观测下界、未知状态分别评价                     | 数值错误率、输出率、热年案例召回与误报 | 严重污染条件付出高输出损失；不能泛化为通用质控                                              | results/wrr_review_response_20261027/release_outputs/release_metrics.csv        |
| 外部资料     | 实际确认资格，并检验原先选定的观测纪录主张           | 完整参照年数、批准窗口与纪录差值       | 新西兰九站无合格精度参照；加拿大4站以已发表日均值进行探索性遮挡评分，但逐日24小时完整性未知 | results/additional_usgs_observed/robust_record_witnesses.csv                    |

## 整档案实验

共 3,320 组站点重复，42站、7地区、20次掩码重复。离线42站，前推41站；芬兰站记录止于1994年，不能参加2010年以后的前推评价。真实日历和受控长缺口分别报告。每次先统一隐藏目标站多年数据，再拟合每日模型、气候态和残差；邻站在此试验中保持可观测。年度模型与校准排除目标测试连接组及其隐藏真值，但前推HUC17估计器保留一个同地区其他训练组，NVE前推区间校准保留两个同地区其他训练组；因此前推并非对所有模型严格外区。年度模型统一使用源拟合种子0；其独立源资料未退化，因此复用既有权重，20次档案掩码不等于20次全局模型重拟合。

前推方法的年度模型、每日模型、依赖结构及任务校准误差均来自2010年以前；任务校准另行生成，不使用2010年以后的校准误差。

| family   | mode    | left    | right                 |   n_common |   left_rmse |   right_rmse |   paired_mse_difference |
|:---------|:--------|:--------|:----------------------|-----------:|------------:|-------------:|------------------------:|
| calendar | forward | D2      | stochastic_calibrated |        701 |     0.06178 |      0.05134 |                 0.00118 |
| calendar | forward | D2      | plug_in               |        820 |     0.06728 |      0.08824 |                -0.00326 |
| calendar | offline | D2      | stochastic_calibrated |        835 |     0.00873 |      0.01124 |                -0.00005 |
| calendar | offline | D2      | plug_in               |        840 |     0.00873 |      0.01368 |                -0.00011 |
| calendar | offline | plug_in | precomputed_plugin    |        840 |     0.01368 |      0.01372 |                -0.00000 |
| crossed  | forward | D2      | stochastic_calibrated |        738 |     0.16381 |      0.14658 |                 0.00535 |
| crossed  | forward | D2      | plug_in               |        820 |     0.17346 |      0.22815 |                -0.02196 |
| crossed  | offline | D2      | stochastic_calibrated |        838 |     0.02780 |      0.03208 |                -0.00026 |
| crossed  | offline | D2      | plug_in               |        840 |     0.02777 |      0.04553 |                -0.00130 |
| crossed  | offline | plug_in | precomputed_plugin    |        840 |     0.04553 |      0.04442 |                 0.00010 |

## 保留集合与估计器

在同一掩码、同一完整参考趋势下，交叉比较两种保留集合和三种估计器。四个配对MSE单元采用对称分解，同时保留交互，不再使用固定的“60%来自保留”归因。

| family   | mode    | estimator             |   n_paired |   retention |   estimator_gain |   total_gain |   interaction |   retention_fraction |
|:---------|:--------|:----------------------|-----------:|------------:|-----------------:|-------------:|--------------:|---------------------:|
| calendar | forward | D2                    |        820 |     0.00679 |          0.00171 |      0.00850 |      -0.00311 |              0.79918 |
| calendar | forward | stochastic_calibrated |        701 |     0.00647 |          0.00223 |      0.00870 |      -0.00410 |              0.74357 |
| calendar | offline | D2                    |        840 |     0.00045 |          0.00006 |      0.00050 |      -0.00011 |              0.88742 |
| calendar | offline | stochastic_calibrated |        835 |     0.00042 |          0.00003 |      0.00045 |      -0.00006 |              0.93121 |
| crossed  | forward | D2                    |        807 |     0.15923 |          0.01029 |      0.16952 |      -0.02073 |              0.93933 |
| crossed  | forward | stochastic_calibrated |        725 |     0.13731 |          0.01119 |      0.14850 |      -0.02237 |              0.92468 |
| crossed  | offline | D2                    |        840 |     0.00870 |          0.00065 |      0.00935 |      -0.00130 |              0.93039 |
| crossed  | offline | stochastic_calibrated |        838 |     0.00858 |          0.00052 |      0.00910 |      -0.00105 |              0.94247 |

## 完整率规则与观测事实

独立实现的卷积和逐日历日核查，从同一规范化日值档案重算96站的2139个完整参考站年、545个不完整站年及35个见证，均与保存结果一致；这不是独立的原始传感器或测量误差验证。另对210个见证—规则判断和35个目标年扰动进行了核查。10个额外USGS站的已保存日值响应中，8个完整参考站年与9个见证窗口的算术一致，但未独立重跑质量筛选选窗。

96站来自34个项目输入面板，共比较971673个有限日值；缺失状态及float32转换均无差异，最大单日舍入差为0.00000153°C，35个见证及0.5°C阈值分类没有变化。这些仍是项目处理后的输入面板，而非提供方原始传感器资料。

逐站暖季使用排除目标年份的五个月气候态。被规则排除的见证若超过已保留年份的最大观测窗口，仅说明超过规则下的已报告窗口记录；保留的不完整年份真实H30可能更高。49日缺口与七八月完整仅作文献情境比较，不冒称相关研究为H30制定了相同规则。

| rule                     |   witness_years |   admitted_witness_years |   excluded_witness_years |   admitted_witness_stations |   excluded_exceed_reported_record |   excluded_exceed_reported_record_stations |
|:-------------------------|----------------:|-------------------------:|-------------------------:|----------------------------:|----------------------------------:|-------------------------------------------:|
| complete_100             |              35 |                        0 |                       35 |                           0 |                                35 |                                         20 |
| annual_95                |              35 |                       31 |                        4 |                          18 |                                 3 |                                          3 |
| warm_90_station_specific |              35 |                       32 |                        3 |                          19 |                                 2 |                                          2 |
| warm_90_fixed_original   |              35 |                       32 |                        3 |                          19 |                                 2 |                                          2 |
| july_aug_complete        |              35 |                       30 |                        5 |                          18 |                                 3 |                                          3 |
| gap_le_49_days_context   |              35 |                       34 |                        1 |                          19 |                                 1 |                                          1 |

## 联合不确定性与任务校准

独立逐年、共享参数、三年残差块采用逐年完全相同的边际样本，只改变联合次序。所有趋势区间针对缺失引起的有限档案斜率误差；不把气候回归噪声加进来掩盖欠覆盖。

| family   | mode    | estimator             | retention   | dependence        |   n_eligible |   n_available |   availability |   rmse |    bias |   missing_coverage95 |   width95 |   interval_score95 |
|:---------|:--------|:----------------------|:------------|:------------------|-------------:|--------------:|---------------:|-------:|--------:|---------------------:|----------:|-------------------:|
| crossed  | forward | D2                    | all         | independent       |          820 |           820 |         1.0000 | 0.1735 | -0.0086 |               0.8805 |    0.4498 |             0.8661 |
| crossed  | forward | D2                    | all         | residual_blocks   |          820 |           820 |         1.0000 | 0.1735 | -0.0086 |               0.8902 |    0.4486 |             0.8281 |
| crossed  | forward | D2                    | all         | shared_parameters |          820 |           820 |         1.0000 | 0.1735 | -0.0086 |               0.8793 |    0.4420 |             0.8519 |
| crossed  | forward | stochastic_calibrated | all         | independent       |          820 |           738 |         0.9000 | 0.1466 | -0.0115 |               0.8631 |    0.3835 |             0.8574 |
| crossed  | forward | stochastic_calibrated | all         | residual_blocks   |          820 |           738 |         0.9000 | 0.1466 | -0.0115 |               0.8726 |    0.3831 |             0.8390 |
| crossed  | forward | stochastic_calibrated | all         | shared_parameters |          820 |           738 |         0.9000 | 0.1466 | -0.0115 |               0.8618 |    0.3791 |             0.8571 |
| crossed  | offline | D2                    | all         | independent       |          840 |           840 |         1.0000 | 0.0278 | -0.0071 |               0.9405 |    0.0894 |             0.1272 |
| crossed  | offline | D2                    | all         | residual_blocks   |          840 |           840 |         1.0000 | 0.0278 | -0.0071 |               0.9476 |    0.0946 |             0.1281 |
| crossed  | offline | D2                    | all         | shared_parameters |          840 |           840 |         1.0000 | 0.0278 | -0.0071 |               0.9452 |    0.0922 |             0.1294 |
| crossed  | offline | stochastic_calibrated | all         | independent       |          840 |           838 |         0.9976 | 0.0321 | -0.0100 |               0.9021 |    0.0812 |             0.1419 |
| crossed  | offline | stochastic_calibrated | all         | residual_blocks   |          840 |           838 |         0.9976 | 0.0321 | -0.0100 |               0.9117 |    0.0854 |             0.1362 |
| crossed  | offline | stochastic_calibrated | all         | shared_parameters |          840 |           838 |         0.9976 | 0.0321 | -0.0100 |               0.9165 |    0.0836 |             0.1373 |

任务校准使用年度拟合及年度区间校准未使用的规则校准组；组总权重相同。实际前推任务校准的最后源年为 2009。少于3个非退化组、零因子或目标宽度不在源域范围时不输出任务校准；这是经验支持筛查，不提供覆盖保证。

| family   | mode    | estimator             |   n |   missing_coverage95 |   width95 |   interval_score95 |   minimum_source_groups |   n_eligible |   availability |
|:---------|:--------|:----------------------|----:|---------------------:|----------:|-------------------:|------------------------:|-------------:|---------------:|
| calendar | forward | D2                    |  40 |               0.9750 |    0.1510 |             0.1537 |                       3 |          820 |         0.0488 |
| calendar | forward | stochastic_calibrated |  38 |               1.0000 |    0.1650 |             0.1650 |                       3 |          820 |         0.0463 |
| calendar | offline | D2                    |  95 |               0.9579 |    0.0300 |             0.0320 |                       3 |          840 |         0.1131 |
| calendar | offline | stochastic_calibrated |  88 |               0.9886 |    0.0297 |             0.0386 |                       3 |          840 |         0.1048 |
| crossed  | forward | D2                    |  39 |               1.0000 |    0.5128 |             0.5128 |                       3 |          820 |         0.0476 |
| crossed  | forward | stochastic_calibrated |  38 |               1.0000 |    0.4713 |             0.4713 |                       3 |          820 |         0.0463 |
| crossed  | offline | D2                    | 301 |               0.9801 |    0.1072 |             0.1154 |                       3 |          840 |         0.3583 |
| crossed  | offline | stochastic_calibrated | 307 |               0.9511 |    0.0915 |             0.1220 |                       3 |          840 |         0.3655 |

| family   | mode    | estimator             |   n_common |   task_coverage95 |   independent_coverage95 |   task_width95 |   independent_width95 |   task_interval_score95 |   independent_interval_score95 |   width_ratio |
|:---------|:--------|:----------------------|-----------:|------------------:|-------------------------:|---------------:|----------------------:|------------------------:|-------------------------------:|--------------:|
| calendar | forward | D2                    |         40 |            0.9750 |                   0.9250 |         0.1510 |                0.1594 |                  0.1537 |                         0.1848 |        0.9469 |
| calendar | forward | stochastic_calibrated |         38 |            1.0000 |                   1.0000 |         0.1650 |                0.2135 |                  0.1650 |                         0.2135 |        0.7726 |
| calendar | offline | D2                    |         95 |            0.9579 |                   0.9368 |         0.0300 |                0.0257 |                  0.0320 |                         0.0282 |        1.1670 |
| calendar | offline | stochastic_calibrated |         88 |            0.9886 |                   0.9773 |         0.0297 |                0.0243 |                  0.0386 |                         0.0308 |        1.2251 |
| crossed  | forward | D2                    |         39 |            1.0000 |                   1.0000 |         0.5128 |                0.4610 |                  0.5128 |                         0.4610 |        1.1123 |
| crossed  | forward | stochastic_calibrated |         38 |            1.0000 |                   1.0000 |         0.4713 |                0.4643 |                  0.4713 |                         0.4643 |        1.0150 |
| crossed  | offline | D2                    |        301 |            0.9801 |                   0.9767 |         0.1072 |                0.0867 |                  0.1154 |                         0.0935 |        1.2360 |
| crossed  | offline | stochastic_calibrated |        307 |            0.9511 |                   0.9479 |         0.0915 |                0.0826 |                  0.1220 |                         0.1039 |        1.1079 |

### 欠覆盖的后续诊断

评价端的年度误差矩阵区分站点斜率偏差、误差方差及年际协方差贡献；它使用已知评价真值，仅作诊断，没有进入恢复模型或区间校准。协方差项可以为负，不能由“有相关性”推导“趋势区间一定更宽”。

| family   | mode    | estimator             |   n_mask_repetitions |   slope_bias |   squared_bias |   slope_error_variance |   diagonal_error_variance |   covariance_contribution |   mean_missing_year_bias |   level_bias_slope_component |   remaining_slope_bias |
|:---------|:--------|:----------------------|---------------------:|-------------:|---------------:|-----------------------:|--------------------------:|--------------------------:|-------------------------:|-----------------------------:|-----------------------:|
| calendar | forward | D2                    |             20.00000 |     -0.00565 |        0.00050 |                0.00424 |                   0.00407 |                   0.00017 |                 -0.02002 |                     -0.00196 |               -0.00369 |
| calendar | forward | stochastic_calibrated |             17.09756 |     -0.00622 |        0.00061 |                0.00314 |                   0.00319 |                  -0.00004 |                 -0.01333 |                     -0.00381 |               -0.00241 |
| calendar | offline | D2                    |             20.00000 |     -0.00087 |        0.00001 |                0.00007 |                   0.00007 |                   0.00000 |                 -0.00439 |                     -0.00054 |               -0.00033 |
| calendar | offline | stochastic_calibrated |             19.88095 |     -0.00110 |        0.00002 |                0.00012 |                   0.00011 |                   0.00000 |                 -0.00499 |                     -0.00067 |               -0.00043 |
| crossed  | forward | D2                    |             20.00000 |     -0.00861 |        0.00506 |                0.02635 |                   0.02650 |                  -0.00015 |                 -0.15533 |                     -0.00456 |               -0.00405 |
| crossed  | forward | stochastic_calibrated |             18.00000 |     -0.01302 |        0.00372 |                0.02267 |                   0.02291 |                  -0.00024 |                 -0.12319 |                     -0.00786 |               -0.00516 |
| crossed  | offline | D2                    |             20.00000 |     -0.00715 |        0.00021 |                0.00059 |                   0.00053 |                   0.00006 |                 -0.03606 |                     -0.00447 |               -0.00267 |
| crossed  | offline | stochastic_calibrated |             19.95238 |     -0.01003 |        0.00030 |                0.00077 |                   0.00069 |                   0.00008 |                 -0.04552 |                     -0.00528 |               -0.00475 |

逐年比较两方法共同有完整分位数且有下界的评价案例：统计区间端点和中位数落在观测下界、90%区间零宽及其参考覆盖。零宽是年度边际性质，不能与任务校准斜率区间混同。参考是有限档案报告值，不包含传感器测量误差。

| family   | mode    | estimator             |   annual_rows |   complete_quantile_rows |   nonfinite_median_rows |   bound_finite_rows |   paired_rows |   stations |   groups |   below_bound |   quantile_crossings |   lower_endpoint_at_bound |   median_at_bound |   median_at_bound_truth_equal |   median_at_bound_truth_above |   truth_below_bound |   truth_equal_bound |   zero_width90 |   zero_width90_at_bound |   zero_width90_covered |   zero_width90_missed |   zero_width90_missed_stations |   zero_width90_missed_station_years |   zero_width90_truth_above_bound |   zero_width90_missed_max_abs_error |   zero_width90_missed_error_over_half_c |   mean_width90 |   n_eligible |   n_available |
|:---------|:--------|:----------------------|--------------:|-------------------------:|------------------------:|--------------------:|--------------:|-----------:|---------:|--------------:|---------------------:|--------------------------:|------------------:|------------------------------:|------------------------------:|--------------------:|--------------------:|---------------:|------------------------:|-----------------------:|----------------------:|-------------------------------:|------------------------------------:|---------------------------------:|------------------------------------:|----------------------------------------:|---------------:|-------------:|--------------:|
| calendar | forward | D2                    |          3806 |                     3806 |                       0 |                3804 |          3674 |         41 |       17 |             0 |                    0 |                      3254 |              2874 |                          2856 |                            18 |                   0 |                3125 |           1476 |                    1476 |                   1476 |                     0 |                              0 |                                   0 |                                0 |                              0.0000 |                                       0 |         0.1180 |         3806 |          3806 |
| calendar | forward | stochastic_calibrated |          3806 |                     3676 |                     130 |                3804 |          3674 |         41 |       17 |             0 |                    0 |                      3194 |              3117 |                          3107 |                            10 |                   0 |                3125 |           2977 |                    2977 |                   2977 |                     0 |                              0 |                                   0 |                                0 |                              0.0000 |                                       0 |         0.0881 |         3806 |          3676 |
| calendar | offline | D2                    |          6942 |                     6942 |                       0 |                6935 |          6919 |         42 |       18 |             0 |                    0 |                      5984 |              4913 |                          4909 |                             4 |                   0 |                5891 |           4538 |                    4538 |                   4538 |                     0 |                              0 |                                   0 |                                0 |                              0.0000 |                                       0 |         0.0945 |         6942 |          6942 |
| calendar | offline | stochastic_calibrated |          6942 |                     6926 |                      16 |                6935 |          6919 |         42 |       18 |             0 |                    0 |                      5967 |              5875 |                          5865 |                            10 |                   0 |                5891 |           5482 |                    5482 |                   5482 |                     0 |                              0 |                                   0 |                                0 |                              0.0000 |                                       0 |         0.0661 |         6942 |          6926 |
| crossed  | forward | D2                    |          3777 |                     3777 |                       0 |                3777 |          3683 |         41 |       17 |             0 |                    0 |                      2090 |              1186 |                          1122 |                            64 |                   0 |                1537 |            323 |                     323 |                    323 |                     0 |                              0 |                                   0 |                                0 |                              0.0000 |                                       0 |         0.8262 |         3777 |          3777 |
| crossed  | forward | stochastic_calibrated |          3777 |                     3683 |                      94 |                3777 |          3683 |         41 |       17 |             0 |                    0 |                      1821 |              1375 |                          1314 |                            61 |                   0 |                1537 |           1091 |                    1091 |                   1088 |                     3 |                              2 |                                   3 |                                3 |                              0.1433 |                                       0 |         0.6931 |         3777 |          3683 |
| crossed  | offline | D2                    |          6921 |                     6921 |                       0 |                6921 |          6919 |         42 |       18 |             0 |                    0 |                      3408 |              2052 |                          2020 |                            32 |                   0 |                2787 |           1391 |                    1391 |                   1391 |                     0 |                              0 |                                   0 |                                0 |                              0.0000 |                                       0 |         0.7304 |         6921 |          6921 |
| crossed  | offline | stochastic_calibrated |          6921 |                     6919 |                       2 |                6921 |          6919 |         42 |       18 |             0 |                    0 |                      3460 |              2753 |                          2674 |                            79 |                   0 |                2787 |           2030 |                    2030 |                   2029 |                     1 |                              1 |                                   1 |                                1 |                              0.2100 |                                       0 |         0.6598 |         6921 |          6919 |

重新调用原模型并固定原校准参数，逐案例核对保存的全部分位数，再记录原始、首次投影、校准修正后和最后投影后的零宽计数。经典方法的原始分位数来自保留已观测日值的有限次插补，因此原始并不意味着不受观测约束。首次投影和投影感知校准仍存在于最后投影前的结果；这不是重新拟合无投影校准的因果试验。

|    n |   pre_zero |   final_zero |   zero_created |   zero_retained |   zero_lost |   final_zero_missed |   created_zero_missed |   pre_below_bound |   final_projection_changed |   pre_covered |   final_covered |   pre_width_sum |   final_width_sum | family   | mode    | estimator             |   raw_zero |   first_projection_zero |   first_projection_created_zero |   offset_correction_created_zero |   offset_correction_lost_zero |   stations |   groups |
|-----:|-----------:|-------------:|---------------:|----------------:|------------:|--------------------:|----------------------:|------------------:|---------------------------:|--------------:|----------------:|----------------:|------------------:|:---------|:--------|:----------------------|-----------:|------------------------:|--------------------------------:|---------------------------------:|------------------------------:|-----------:|---------:|
| 3674 |       1096 |         1476 |            380 |            1096 |           0 |                   0 |                     0 |               775 |                        775 |          3610 |            3610 |        450.7721 |          433.4628 | calendar | forward | D2                    |          0 |                       2 |                               2 |                             1096 |                             2 |         41 |       17 |
| 3674 |       2977 |         2977 |              0 |            2977 |           0 |                   0 |                     0 |                65 |                         65 |          3604 |            3604 |        328.1002 |          323.5461 | calendar | forward | stochastic_calibrated |       3090 |                    3090 |                               0 |                                0 |                           113 |         41 |       17 |
| 6919 |       4402 |         4538 |            136 |            4402 |           0 |                   0 |                     0 |               341 |                        341 |          6815 |            6815 |        657.9136 |          653.8491 | calendar | offline | D2                    |          0 |                       0 |                               0 |                             4402 |                             0 |         42 |       18 |
| 6919 |       5482 |         5482 |              0 |            5482 |           0 |                   0 |                     0 |               371 |                        371 |          6742 |            6742 |        464.3264 |          457.0078 | calendar | offline | stochastic_calibrated |       5818 |                    5818 |                               0 |                                0 |                           336 |         42 |       18 |
| 3683 |        227 |          323 |             96 |             227 |           0 |                   0 |                     0 |              1087 |                       1087 |          3313 |            3313 |       3177.6996 |         3042.8958 | crossed  | forward | D2                    |          0 |                       0 |                               0 |                              227 |                             0 |         41 |       17 |
| 3683 |       1091 |         1091 |              0 |            1091 |           0 |                   3 |                     0 |               529 |                        529 |          3203 |            3203 |       2626.6727 |         2552.5198 | crossed  | forward | stochastic_calibrated |       1362 |                    1362 |                               0 |                                0 |                           271 |         41 |       17 |
| 6919 |       1376 |         1391 |             15 |            1376 |           0 |                   0 |                     0 |              1228 |                       1228 |          6514 |            6514 |       5139.1350 |         5053.7395 | crossed  | offline | D2                    |          0 |                       1 |                               1 |                             1376 |                             1 |         42 |       18 |
| 6919 |       2030 |         2030 |              0 |            2030 |           0 |                   1 |                     0 |              1189 |                       1189 |          6411 |            6411 |       4696.0885 |         4565.1846 | crossed  | offline | stochastic_calibrated |       2491 |                    2491 |                               0 |                                0 |                           461 |         42 |       18 |

使用完整参考H30与已观测下界的关系，将共同评价案例事后分成‘已观测窗口达到参考热峰’和‘参考热峰高于下界’；这必须知道隐藏真值，不能作为发布或模型选择规则。同一站年在不同掩码下可能进入两个组。下面报告按案例加权的覆盖、误差及连接群组重采样区间；群组重采样不能证明独立气候迁移。

| family   | mode    | stratum                 | estimator             |    n |   stations |   station_years |   groups |   coverage90 |   coverage90_bootstrap_low |   coverage90_bootstrap_high |    mae |   width90 |
|:---------|:--------|:------------------------|:----------------------|-----:|-----------:|----------------:|---------:|-------------:|---------------------------:|----------------------------:|-------:|----------:|
| calendar | forward | all                     | D2                    | 3674 |         41 |             531 |       17 |       0.9826 |                     0.9700 |                      0.9929 | 0.0287 |    0.1180 |
| calendar | forward | all                     | stochastic_calibrated | 3674 |         41 |             531 |       17 |       0.9809 |                     0.9686 |                      0.9927 | 0.0229 |    0.0881 |
| calendar | forward | bound_matches_reference | D2                    | 3125 |         41 |             524 |       17 |       1.0000 |                     1.0000 |                      1.0000 | 0.0002 |    0.0175 |
| calendar | forward | bound_matches_reference | stochastic_calibrated | 3125 |         41 |             524 |       17 |       0.9990 |                     0.9962 |                      1.0000 | 0.0004 |    0.0041 |
| calendar | forward | unobserved_peak_excess  | D2                    |  549 |         31 |             227 |       15 |       0.8834 |                     0.8462 |                      0.9316 | 0.1906 |    0.6900 |
| calendar | forward | unobserved_peak_excess  | stochastic_calibrated |  549 |         31 |             227 |       15 |       0.8780 |                     0.8414 |                      0.9354 | 0.1508 |    0.5660 |
| calendar | offline | all                     | D2                    | 6919 |         42 |             998 |       18 |       0.9850 |                     0.9758 |                      0.9908 | 0.0185 |    0.0945 |
| calendar | offline | all                     | stochastic_calibrated | 6919 |         42 |             998 |       18 |       0.9744 |                     0.9642 |                      0.9871 | 0.0179 |    0.0661 |
| calendar | offline | bound_matches_reference | D2                    | 5891 |         42 |             992 |       18 |       0.9988 |                     0.9963 |                      1.0000 | 0.0004 |    0.0110 |
| calendar | offline | bound_matches_reference | stochastic_calibrated | 5891 |         42 |             992 |       18 |       0.9995 |                     0.9981 |                      1.0000 | 0.0001 |    0.0031 |
| calendar | offline | unobserved_peak_excess  | D2                    | 1028 |         32 |             445 |       16 |       0.9056 |                     0.8685 |                      0.9292 | 0.1223 |    0.5731 |
| calendar | offline | unobserved_peak_excess  | stochastic_calibrated | 1028 |         32 |             445 |       16 |       0.8307 |                     0.7983 |                      0.8866 | 0.1196 |    0.4269 |
| crossed  | forward | all                     | D2                    | 3683 |         41 |             536 |       17 |       0.8995 |                     0.8375 |                      0.9571 | 0.2249 |    0.8262 |
| crossed  | forward | all                     | stochastic_calibrated | 3683 |         41 |             536 |       17 |       0.8697 |                     0.7925 |                      0.9476 | 0.2115 |    0.6931 |
| crossed  | forward | bound_matches_reference | D2                    | 1537 |         41 |             501 |       17 |       0.9935 |                     0.9891 |                      0.9981 | 0.0117 |    0.1662 |
| crossed  | forward | bound_matches_reference | stochastic_calibrated | 1537 |         41 |             501 |       17 |       0.9440 |                     0.8905 |                      0.9934 | 0.0250 |    0.0955 |
| crossed  | forward | unobserved_peak_excess  | D2                    | 2146 |         41 |             528 |       17 |       0.8322 |                     0.7258 |                      0.9301 | 0.3776 |    1.2989 |
| crossed  | forward | unobserved_peak_excess  | stochastic_calibrated | 2146 |         41 |             528 |       17 |       0.8164 |                     0.7225 |                      0.9168 | 0.3451 |    1.1210 |
| crossed  | offline | all                     | D2                    | 6919 |         42 |             998 |       18 |       0.9415 |                     0.9279 |                      0.9594 | 0.1731 |    0.7304 |
| crossed  | offline | all                     | stochastic_calibrated | 6919 |         42 |             998 |       18 |       0.9266 |                     0.9063 |                      0.9471 | 0.1746 |    0.6598 |
| crossed  | offline | bound_matches_reference | D2                    | 2787 |         42 |             943 |       18 |       0.9932 |                     0.9893 |                      0.9965 | 0.0078 |    0.0775 |
| crossed  | offline | bound_matches_reference | stochastic_calibrated | 2787 |         42 |             943 |       18 |       0.9975 |                     0.9953 |                      0.9994 | 0.0052 |    0.0551 |
| crossed  | offline | unobserved_peak_excess  | D2                    | 4132 |         42 |             986 |       18 |       0.9066 |                     0.8847 |                      0.9363 | 0.2846 |    1.1708 |
| crossed  | offline | unobserved_peak_excess  | stochastic_calibrated | 4132 |         42 |             986 |       18 |       0.8788 |                     0.8460 |                      0.9127 | 0.2889 |    1.0677 |

年度区间另试验源群组加权的经验扩展：来源是与拟合、原区间校准及目标地区分离的规则校准群组；不足三个群组或经验修正为零时标记不可支持。下表的分母是两方法共同可用案例，前后结果只在同一有支持子集比较。这是看过现有结果后开展的探索，未实现分布无关的群组保证，也没有重建联合趋势分布。

| family   | mode    | estimator             |   n_eligible |   n_supported |   availability |   stations |   baseline_paired_coverage90 |   expanded_paired_coverage90 |   baseline_paired_width90 |   expanded_paired_width90 |   baseline_paired_interval_score90 |   expanded_paired_interval_score90 |
|:---------|:--------|:----------------------|-------------:|--------------:|---------------:|-----------:|-----------------------------:|-----------------------------:|--------------------------:|--------------------------:|-----------------------------------:|-----------------------------------:|
| calendar | forward | D2                    |         3676 |             0 |         0.0000 |          0 |                     nan      |                     nan      |                  nan      |                  nan      |                           nan      |                           nan      |
| calendar | forward | stochastic_calibrated |         3676 |             0 |         0.0000 |          0 |                     nan      |                     nan      |                  nan      |                  nan      |                           nan      |                           nan      |
| calendar | offline | D2                    |         6926 |             0 |         0.0000 |          0 |                     nan      |                     nan      |                  nan      |                  nan      |                           nan      |                           nan      |
| calendar | offline | stochastic_calibrated |         6926 |             0 |         0.0000 |          0 |                     nan      |                     nan      |                  nan      |                  nan      |                           nan      |                           nan      |
| crossed  | forward | D2                    |         3683 |            92 |         0.0250 |          1 |                       1.0000 |                       1.0000 |                    0.5315 |                    0.5426 |                             0.5315 |                             0.5426 |
| crossed  | forward | stochastic_calibrated |         3683 |            92 |         0.0250 |          1 |                       1.0000 |                       1.0000 |                    0.5553 |                    0.5670 |                             0.5553 |                             0.5670 |
| crossed  | offline | D2                    |         6919 |             0 |         0.0000 |          0 |                     nan      |                     nan      |                  nan      |                  nan      |                           nan      |                           nan      |
| crossed  | offline | stochastic_calibrated |         6919 |             0 |         0.0000 |          0 |                     nan      |                     nan      |                  nan      |                  nan      |                           nan      |                           nan      |

尾部敏感性在相同随机次序下比较常数端点与相邻分位数间距给出的正态尾部；两者均施加已观测窗口支持约束。结果不能当作已证明的真实尾部分布或全部归因为联合结构。

| family   | mode    | estimator             | tails    |   n |   coverage95 |   width95 |   interval_score95 |
|:---------|:--------|:----------------------|:---------|----:|-------------:|----------:|-------------------:|
| calendar | forward | D2                    | constant | 818 |       0.9462 |    0.0912 |             0.1977 |
| calendar | forward | D2                    | normal   | 818 |       0.9572 |    0.1156 |             0.1867 |
| calendar | forward | stochastic_calibrated | constant | 699 |       0.9456 |    0.0622 |             0.1479 |
| calendar | forward | stochastic_calibrated | normal   | 699 |       0.9528 |    0.0752 |             0.1399 |
| calendar | offline | D2                    | constant | 840 |       0.9226 |    0.0150 |             0.0262 |
| calendar | offline | D2                    | normal   | 840 |       0.9488 |    0.0181 |             0.0259 |
| calendar | offline | stochastic_calibrated | constant | 835 |       0.9174 |    0.0124 |             0.0305 |
| calendar | offline | stochastic_calibrated | normal   | 835 |       0.9329 |    0.0149 |             0.0283 |
| crossed  | forward | D2                    | constant | 818 |       0.8301 |    0.3805 |             0.9866 |
| crossed  | forward | D2                    | normal   | 818 |       0.8875 |    0.4511 |             0.8596 |
| crossed  | forward | stochastic_calibrated | constant | 736 |       0.8139 |    0.3234 |             0.9196 |
| crossed  | forward | stochastic_calibrated | normal   | 736 |       0.8628 |    0.3835 |             0.8551 |
| crossed  | offline | D2                    | constant | 840 |       0.9167 |    0.0776 |             0.1270 |
| crossed  | offline | D2                    | normal   | 840 |       0.9417 |    0.0901 |             0.1286 |
| crossed  | offline | stochastic_calibrated | constant | 838 |       0.8640 |    0.0699 |             0.1507 |
| crossed  | offline | stochastic_calibrated | normal   | 838 |       0.9069 |    0.0815 |             0.1395 |

下面固定同一可评价子集，同时报告年度覆盖、尾部处理和固定年度边际的联合排序。尾部和排序实验各自内部配对，但两个实验的抽样随机数不同，年度失配也没有被实验性修正，故不能把差异相加当成因果分解。群组重采样区间为描述性结果。

| family   | mode    | estimator             |   n_all |   n_common |   fraction_common |   stations |   groups |   incomplete_years |   annual_coverage90_weighted |   annual_coverage90_station_replicate |   annual_mae_weighted |   annual_width90_weighted |   independent_coverage95 |   independent_width95 |   independent_interval_score95 |   shared_parameters_coverage95 |   shared_parameters_width95 |   shared_parameters_interval_score95 |   residual_blocks_coverage95 |   residual_blocks_width95 |   residual_blocks_interval_score95 |   constant_coverage95 |   constant_width95 |   constant_interval_score95 |   normal_coverage95 |   normal_width95 |   normal_interval_score95 |
|:---------|:--------|:----------------------|--------:|-----------:|------------------:|-----------:|---------:|-------------------:|-----------------------------:|--------------------------------------:|----------------------:|--------------------------:|-------------------------:|----------------------:|-------------------------------:|-------------------------------:|----------------------------:|-------------------------------------:|-----------------------------:|--------------------------:|-----------------------------------:|----------------------:|-------------------:|----------------------------:|--------------------:|-----------------:|--------------------------:|
| calendar | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3806 |                       0.9821 |                                0.9804 |                0.0288 |                    0.1369 |                   0.9597 |                0.1158 |                         0.1859 |                         0.9609 |                      0.1159 |                               0.1866 |                       0.9633 |                    0.1154 |                             0.1774 |                0.9462 |             0.0912 |                      0.1977 |              0.9572 |           0.1156 |                    0.1867 |
| calendar | forward | stochastic_calibrated |     820 |        699 |            0.8524 |         41 |       17 |               3146 |                       0.9822 |                                0.9811 |                0.0210 |                    0.0839 |                   0.9542 |                0.0750 |                         0.1407 |                         0.9542 |                      0.0748 |                               0.1404 |                       0.9571 |                    0.0752 |                             0.1371 |                0.9456 |             0.0622 |                      0.1479 |              0.9528 |           0.0752 |                    0.1399 |
| calendar | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6942 |                       0.9847 |                                0.9847 |                0.0190 |                    0.0973 |                   0.9500 |                0.0180 |                         0.0256 |                         0.9512 |                      0.0182 |                               0.0259 |                       0.9488 |                    0.0183 |                             0.0260 |                0.9226 |             0.0150 |                      0.0262 |              0.9488 |           0.0181 |                    0.0259 |
| calendar | offline | stochastic_calibrated |     840 |        835 |            0.9940 |         42 |       18 |               6866 |                       0.9742 |                                0.9763 |                0.0181 |                    0.0676 |                   0.9317 |                0.0148 |                         0.0283 |                         0.9329 |                      0.0149 |                               0.0282 |                       0.9329 |                    0.0149 |                             0.0281 |                0.9174 |             0.0124 |                      0.0305 |              0.9329 |           0.0149 |                    0.0283 |
| crossed  | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3777 |                       0.9010 |                                0.8960 |                0.2254 |                    0.8337 |                   0.8802 |                0.4509 |                         0.8682 |                         0.8790 |                      0.4431 |                               0.8540 |                       0.8900 |                    0.4497 |                             0.8301 |                0.8301 |             0.3805 |                      0.9866 |              0.8875 |           0.4511 |                    0.8596 |
| crossed  | forward | stochastic_calibrated |     820 |        736 |            0.8976 |         41 |       17 |               3328 |                       0.8810 |                                0.8709 |                0.2012 |                    0.6875 |                   0.8628 |                0.3845 |                         0.8597 |                         0.8614 |                      0.3802 |                               0.8594 |                       0.8723 |                    0.3842 |                             0.8413 |                0.8139 |             0.3234 |                      0.9196 |              0.8628 |           0.3835 |                    0.8551 |
| crossed  | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6921 |                       0.9415 |                                0.9479 |                0.1730 |                    0.7304 |                   0.9405 |                0.0894 |                         0.1272 |                         0.9452 |                      0.0922 |                               0.1294 |                       0.9476 |                    0.0946 |                             0.1281 |                0.9167 |             0.0776 |                      0.1270 |              0.9417 |           0.0901 |                    0.1286 |
| crossed  | offline | stochastic_calibrated |     840 |        838 |            0.9976 |         42 |       18 |               6904 |                       0.9264 |                                0.9308 |                0.1747 |                    0.6599 |                   0.9021 |                0.0812 |                         0.1419 |                         0.9165 |                      0.0836 |                               0.1373 |                       0.9117 |                    0.0854 |                             0.1362 |                0.8640 |             0.0699 |                      0.1507 |              0.9069 |           0.0815 |                    0.1395 |

| family   | mode    | estimator             |   n_all |   n_common |   fraction_common |   stations |   groups |   incomplete_years | contrast                 | metric           |   difference |   cluster_bootstrap_lower |   cluster_bootstrap_upper |
|:---------|:--------|:----------------------|--------:|-----------:|------------------:|-----------:|---------:|-------------------:|:-------------------------|:-----------------|-------------:|--------------------------:|--------------------------:|
| calendar | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3806 | normal_minus_constant    | coverage95       |       0.0110 |                    0.0000 |                    0.0239 |
| calendar | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3806 | normal_minus_constant    | width95          |       0.0243 |                    0.0140 |                    0.0359 |
| calendar | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3806 | normal_minus_constant    | interval_score95 |      -0.0109 |                   -0.0413 |                    0.0185 |
| calendar | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3806 | shared_minus_independent | coverage95       |       0.0012 |                   -0.0040 |                    0.0056 |
| calendar | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3806 | shared_minus_independent | width95          |       0.0001 |                   -0.0008 |                    0.0012 |
| calendar | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3806 | shared_minus_independent | interval_score95 |       0.0008 |                   -0.0024 |                    0.0034 |
| calendar | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3806 | blocks_minus_independent | coverage95       |       0.0037 |                    0.0000 |                    0.0080 |
| calendar | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3806 | blocks_minus_independent | width95          |      -0.0004 |                   -0.0025 |                    0.0009 |
| calendar | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3806 | blocks_minus_independent | interval_score95 |      -0.0084 |                   -0.0195 |                   -0.0013 |
| calendar | forward | stochastic_calibrated |     820 |        699 |            0.8524 |         41 |       17 |               3146 | normal_minus_constant    | coverage95       |       0.0072 |                    0.0000 |                    0.0162 |
| calendar | forward | stochastic_calibrated |     820 |        699 |            0.8524 |         41 |       17 |               3146 | normal_minus_constant    | width95          |       0.0130 |                    0.0071 |                    0.0206 |
| calendar | forward | stochastic_calibrated |     820 |        699 |            0.8524 |         41 |       17 |               3146 | normal_minus_constant    | interval_score95 |      -0.0080 |                   -0.0241 |                    0.0073 |
| calendar | forward | stochastic_calibrated |     820 |        699 |            0.8524 |         41 |       17 |               3146 | shared_minus_independent | coverage95       |       0.0000 |                   -0.0049 |                    0.0040 |
| calendar | forward | stochastic_calibrated |     820 |        699 |            0.8524 |         41 |       17 |               3146 | shared_minus_independent | width95          |      -0.0002 |                   -0.0007 |                    0.0001 |
| calendar | forward | stochastic_calibrated |     820 |        699 |            0.8524 |         41 |       17 |               3146 | shared_minus_independent | interval_score95 |      -0.0003 |                   -0.0017 |                    0.0009 |
| calendar | forward | stochastic_calibrated |     820 |        699 |            0.8524 |         41 |       17 |               3146 | blocks_minus_independent | coverage95       |       0.0029 |                   -0.0038 |                    0.0105 |
| calendar | forward | stochastic_calibrated |     820 |        699 |            0.8524 |         41 |       17 |               3146 | blocks_minus_independent | width95          |       0.0002 |                   -0.0005 |                    0.0008 |
| calendar | forward | stochastic_calibrated |     820 |        699 |            0.8524 |         41 |       17 |               3146 | blocks_minus_independent | interval_score95 |      -0.0036 |                   -0.0129 |                    0.0010 |
| calendar | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6942 | normal_minus_constant    | coverage95       |       0.0262 |                    0.0131 |                    0.0460 |
| calendar | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6942 | normal_minus_constant    | width95          |       0.0031 |                    0.0017 |                    0.0053 |
| calendar | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6942 | normal_minus_constant    | interval_score95 |      -0.0002 |                   -0.0021 |                    0.0025 |
| calendar | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6942 | shared_minus_independent | coverage95       |       0.0012 |                   -0.0043 |                    0.0083 |
| calendar | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6942 | shared_minus_independent | width95          |       0.0002 |                    0.0000 |                    0.0004 |
| calendar | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6942 | shared_minus_independent | interval_score95 |       0.0002 |                    0.0000 |                    0.0006 |
| calendar | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6942 | blocks_minus_independent | coverage95       |      -0.0012 |                   -0.0060 |                    0.0050 |
| calendar | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6942 | blocks_minus_independent | width95          |       0.0003 |                    0.0001 |                    0.0005 |
| calendar | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6942 | blocks_minus_independent | interval_score95 |       0.0004 |                   -0.0003 |                    0.0018 |
| calendar | offline | stochastic_calibrated |     840 |        835 |            0.9940 |         42 |       18 |               6866 | normal_minus_constant    | coverage95       |       0.0156 |                    0.0049 |                    0.0299 |
| calendar | offline | stochastic_calibrated |     840 |        835 |            0.9940 |         42 |       18 |               6866 | normal_minus_constant    | width95          |       0.0025 |                    0.0014 |                    0.0040 |
| calendar | offline | stochastic_calibrated |     840 |        835 |            0.9940 |         42 |       18 |               6866 | normal_minus_constant    | interval_score95 |      -0.0021 |                   -0.0046 |                    0.0009 |
| calendar | offline | stochastic_calibrated |     840 |        835 |            0.9940 |         42 |       18 |               6866 | shared_minus_independent | coverage95       |       0.0012 |                   -0.0036 |                    0.0077 |
| calendar | offline | stochastic_calibrated |     840 |        835 |            0.9940 |         42 |       18 |               6866 | shared_minus_independent | width95          |       0.0001 |                   -0.0000 |                    0.0002 |
| calendar | offline | stochastic_calibrated |     840 |        835 |            0.9940 |         42 |       18 |               6866 | shared_minus_independent | interval_score95 |      -0.0000 |                   -0.0002 |                    0.0001 |
| calendar | offline | stochastic_calibrated |     840 |        835 |            0.9940 |         42 |       18 |               6866 | blocks_minus_independent | coverage95       |       0.0012 |                   -0.0035 |                    0.0081 |
| calendar | offline | stochastic_calibrated |     840 |        835 |            0.9940 |         42 |       18 |               6866 | blocks_minus_independent | width95          |       0.0001 |                    0.0000 |                    0.0002 |
| calendar | offline | stochastic_calibrated |     840 |        835 |            0.9940 |         42 |       18 |               6866 | blocks_minus_independent | interval_score95 |      -0.0001 |                   -0.0013 |                    0.0011 |
| crossed  | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3777 | normal_minus_constant    | coverage95       |       0.0575 |                    0.0286 |                    0.0874 |
| crossed  | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3777 | normal_minus_constant    | width95          |       0.0706 |                    0.0597 |                    0.0848 |
| crossed  | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3777 | normal_minus_constant    | interval_score95 |      -0.1270 |                   -0.2617 |                   -0.0068 |
| crossed  | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3777 | shared_minus_independent | coverage95       |      -0.0012 |                   -0.0088 |                    0.0071 |
| crossed  | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3777 | shared_minus_independent | width95          |      -0.0078 |                   -0.0132 |                   -0.0044 |
| crossed  | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3777 | shared_minus_independent | interval_score95 |      -0.0142 |                   -0.0361 |                   -0.0017 |
| crossed  | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3777 | blocks_minus_independent | coverage95       |       0.0098 |                   -0.0101 |                    0.0279 |
| crossed  | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3777 | blocks_minus_independent | width95          |      -0.0012 |                   -0.0142 |                    0.0083 |
| crossed  | forward | D2                    |     820 |        818 |            0.9976 |         41 |       17 |               3777 | blocks_minus_independent | interval_score95 |      -0.0381 |                   -0.0729 |                   -0.0136 |
| crossed  | forward | stochastic_calibrated |     820 |        736 |            0.8976 |         41 |       17 |               3328 | normal_minus_constant    | coverage95       |       0.0489 |                    0.0267 |                    0.0769 |
| crossed  | forward | stochastic_calibrated |     820 |        736 |            0.8976 |         41 |       17 |               3328 | normal_minus_constant    | width95          |       0.0602 |                    0.0499 |                    0.0700 |
| crossed  | forward | stochastic_calibrated |     820 |        736 |            0.8976 |         41 |       17 |               3328 | normal_minus_constant    | interval_score95 |      -0.0645 |                   -0.1454 |                    0.0040 |
| crossed  | forward | stochastic_calibrated |     820 |        736 |            0.8976 |         41 |       17 |               3328 | shared_minus_independent | coverage95       |      -0.0014 |                   -0.0144 |                    0.0115 |
| crossed  | forward | stochastic_calibrated |     820 |        736 |            0.8976 |         41 |       17 |               3328 | shared_minus_independent | width95          |      -0.0044 |                   -0.0088 |                   -0.0006 |
| crossed  | forward | stochastic_calibrated |     820 |        736 |            0.8976 |         41 |       17 |               3328 | shared_minus_independent | interval_score95 |      -0.0003 |                   -0.0208 |                    0.0164 |
| crossed  | forward | stochastic_calibrated |     820 |        736 |            0.8976 |         41 |       17 |               3328 | blocks_minus_independent | coverage95       |       0.0095 |                   -0.0033 |                    0.0272 |
| crossed  | forward | stochastic_calibrated |     820 |        736 |            0.8976 |         41 |       17 |               3328 | blocks_minus_independent | width95          |      -0.0004 |                   -0.0097 |                    0.0089 |
| crossed  | forward | stochastic_calibrated |     820 |        736 |            0.8976 |         41 |       17 |               3328 | blocks_minus_independent | interval_score95 |      -0.0184 |                   -0.0368 |                   -0.0036 |
| crossed  | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6921 | normal_minus_constant    | coverage95       |       0.0250 |                    0.0122 |                    0.0362 |
| crossed  | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6921 | normal_minus_constant    | width95          |       0.0125 |                    0.0100 |                    0.0172 |
| crossed  | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6921 | normal_minus_constant    | interval_score95 |       0.0017 |                   -0.0060 |                    0.0100 |
| crossed  | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6921 | shared_minus_independent | coverage95       |       0.0048 |                   -0.0016 |                    0.0097 |
| crossed  | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6921 | shared_minus_independent | width95          |       0.0027 |                    0.0014 |                    0.0043 |
| crossed  | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6921 | shared_minus_independent | interval_score95 |       0.0022 |                    0.0007 |                    0.0043 |
| crossed  | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6921 | blocks_minus_independent | coverage95       |       0.0071 |                   -0.0036 |                    0.0153 |
| crossed  | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6921 | blocks_minus_independent | width95          |       0.0051 |                    0.0035 |                    0.0066 |
| crossed  | offline | D2                    |     840 |        840 |            1.0000 |         42 |       18 |               6921 | blocks_minus_independent | interval_score95 |       0.0009 |                   -0.0025 |                    0.0042 |
| crossed  | offline | stochastic_calibrated |     840 |        838 |            0.9976 |         42 |       18 |               6904 | normal_minus_constant    | coverage95       |       0.0430 |                    0.0236 |                    0.0606 |
| crossed  | offline | stochastic_calibrated |     840 |        838 |            0.9976 |         42 |       18 |               6904 | normal_minus_constant    | width95          |       0.0116 |                    0.0093 |                    0.0152 |
| crossed  | offline | stochastic_calibrated |     840 |        838 |            0.9976 |         42 |       18 |               6904 | normal_minus_constant    | interval_score95 |      -0.0113 |                   -0.0230 |                    0.0004 |
| crossed  | offline | stochastic_calibrated |     840 |        838 |            0.9976 |         42 |       18 |               6904 | shared_minus_independent | coverage95       |       0.0143 |                    0.0068 |                    0.0250 |
| crossed  | offline | stochastic_calibrated |     840 |        838 |            0.9976 |         42 |       18 |               6904 | shared_minus_independent | width95          |       0.0024 |                    0.0012 |                    0.0037 |
| crossed  | offline | stochastic_calibrated |     840 |        838 |            0.9976 |         42 |       18 |               6904 | shared_minus_independent | interval_score95 |      -0.0046 |                   -0.0104 |                    0.0005 |
| crossed  | offline | stochastic_calibrated |     840 |        838 |            0.9976 |         42 |       18 |               6904 | blocks_minus_independent | coverage95       |       0.0095 |                    0.0000 |                    0.0182 |
| crossed  | offline | stochastic_calibrated |     840 |        838 |            0.9976 |         42 |       18 |               6904 | blocks_minus_independent | width95          |       0.0042 |                    0.0032 |                    0.0052 |
| crossed  | offline | stochastic_calibrated |     840 |        838 |            0.9976 |         42 |       18 |               6904 | blocks_minus_independent | interval_score95 |      -0.0057 |                   -0.0124 |                    0.0013 |

## 数值发布率配平比较

在同一批评价案例中，分数规则按原始个体分类器分数从低到高排序，发布数量严格配平三类规则；分数相同按案例标识确定次序。匹配只使用评价特征分布和三类规则的发布数量，不使用隐藏标签，但阈值仍是评价集配平的描述性阈值，不是预先可部署的策略。相同数值数量并不意味着下界和未知状态提供的信息相同；群组重采样区间仅作描述，不能视为普遍安全保证。

| condition              | family   |   n_eligible |   n_equal_numerical |   retention |   n_groups |   score_cutoff |   n_at_cutoff |   n_selected_with_tied_score |   three_output_bad |   score_only_bad |   three_output_risk |   score_only_risk |   risk_difference |   three_only |   score_only |   uncertainty_low |   uncertainty_high |   bootstrap_valid |   bootstrap_draws |
|:-----------------------|:---------|-------------:|--------------------:|------------:|-----------:|---------------:|--------------:|-----------------------------:|-------------------:|-----------------:|--------------------:|------------------:|------------------:|-------------:|-------------:|------------------:|-------------------:|------------------:|------------------:|
| clean                  | calendar |        31672 |               27090 |      0.8553 |        185 |         0.0006 |             1 |                            1 |                190 |                4 |              0.0070 |            0.0001 |            0.0069 |         2669 |         2669 |            0.0052 |             0.0088 |              2000 |              2000 |
| clean                  | crossed  |       114012 |               82169 |      0.7207 |        185 |         0.0581 |             1 |                            1 |               4026 |             3249 |              0.0490 |            0.0395 |            0.0095 |         4780 |         4780 |            0.0078 |             0.0112 |              2000 |              2000 |
| hot_year_extrapolation | calendar |         7453 |                6363 |      0.8538 |        185 |         0.0003 |             1 |                            1 |                146 |                7 |              0.0229 |            0.0011 |            0.0218 |          710 |          710 |            0.0169 |             0.0272 |              2000 |              2000 |
| hot_year_extrapolation | crossed  |        26730 |               20368 |      0.7620 |        185 |         0.0341 |             1 |                            1 |               2534 |             1999 |              0.1244 |            0.0981 |            0.0263 |         1888 |         1888 |            0.0200 |             0.0326 |              2000 |              2000 |
| future_years           | calendar |         7310 |                5402 |      0.7390 |         60 |         0.0005 |             1 |                            1 |                 75 |                7 |              0.0139 |            0.0013 |            0.0126 |         1094 |         1094 |            0.0081 |             0.0162 |              2000 |              2000 |
| future_years           | crossed  |        27846 |               17583 |      0.6314 |         60 |         0.0132 |             1 |                            1 |               1924 |             1220 |              0.1094 |            0.0694 |            0.0400 |         3287 |         3287 |            0.0241 |             0.0575 |              2000 |              2000 |
| air_exposure           | calendar |        31672 |                  88 |      0.0028 |        185 |         0.0000 |             1 |                            1 |                 19 |               23 |              0.2159 |            0.2614 |           -0.0455 |           88 |           88 |           -0.2705 |             0.1063 |              2000 |              2000 |
| air_exposure           | crossed  |       114012 |                   0 |      0.0000 |        185 |       nan      |             0 |                            0 |                  0 |                0 |            nan      |          nan      |          nan      |            0 |            0 |          nan      |           nan      |                 0 |              2000 |
| smooth_non_air_shift   | calendar |        31672 |               27082 |      0.8551 |        185 |         0.0006 |             1 |                            1 |                178 |                7 |              0.0066 |            0.0003 |            0.0063 |         2658 |         2658 |            0.0050 |             0.0079 |              2000 |              2000 |
| smooth_non_air_shift   | crossed  |       114012 |               81177 |      0.7120 |        185 |         0.0578 |             1 |                            1 |               3825 |             3047 |              0.0471 |            0.0375 |            0.0096 |         4766 |         4766 |            0.0080 |             0.0113 |              2000 |              2000 |

另一项干净回顾性试验中，每个目标地区的分数阈值只用模型的其他地区、组不重叠的规则校准集决定，以近似匹配源集三类规则的发布率。阈值不使用目标标签或目标发布数量；目标侧发布率可以不同。对185个连接组重采样仅作描述，阈值拟合不确定性及气候间依赖未得到保证。

| family   | method        |   n_eligible |   n_published |   retention |   n_bad |   risk |   regions |   groups |
|:---------|:--------------|-------------:|--------------:|------------:|--------:|-------:|----------:|---------:|
| calendar | three_outputs |        31672 |         27090 |      0.8553 |     190 | 0.0070 |        27 |      185 |
| calendar | score_only    |        31672 |         26896 |      0.8492 |       8 | 0.0003 |        27 |      185 |
| crossed  | three_outputs |       114012 |         82169 |      0.7207 |    4026 | 0.0490 |        27 |      185 |
| crossed  | score_only    |       114012 |         80980 |      0.7103 |    3133 | 0.0387 |        27 |      185 |

| family   | metric                       |   lower |   upper |   valid_draws |   groups |
|:---------|:-----------------------------|--------:|--------:|--------------:|---------:|
| calendar | retention_difference         | -0.0193 |  0.0317 |          2000 |      185 |
| calendar | conditional_error_difference |  0.0051 |  0.0088 |          2000 |      185 |
| crossed  | retention_difference         | -0.0074 |  0.0257 |          2000 |      185 |
| crossed  | conditional_error_difference |  0.0079 |  0.0131 |          2000 |      185 |

按地区和连接组分别汇总；仅保留两种方法都发布至少一个数值的组来计算组等权条件错误率，零发布的条件错误率为未定义。删去一个地区只删除该地区的评价案例，模型及其他地区的源阈值不重训；不同地区数值发布率可能相差很大，不能把条件错误率的方向计数解释成独立显著性检验。

| design_family   |   n_regions |   n_both_defined |   n_three_higher |   n_three_lower |   n_equal |   n_undefined |
|:----------------|------------:|-----------------:|-----------------:|----------------:|----------:|--------------:|
| calendar        |          27 |               26 |               20 |               0 |         6 |             1 |
| crossed         |          27 |               26 |               24 |               2 |         0 |             1 |

| design_family   |   n_groups |   n_both_defined |   n_score_zero |   n_three_zero |   score_mean_group_error |   three_mean_group_error |   group_mean_error_difference |
|:----------------|-----------:|-----------------:|---------------:|---------------:|-------------------------:|-------------------------:|------------------------------:|
| calendar        |        185 |              172 |              0 |             13 |                   0.0001 |                   0.0083 |                        0.0081 |
| crossed         |        185 |              172 |              0 |             13 |                   0.0460 |                   0.0596 |                        0.0136 |

| design_family   | region               |     n |   score_kept |   three_kept |   score_bad |   three_bad |   score_retention |   three_retention |   score_error |   three_error |   retention_difference |   conditional_error_difference |
|:----------------|:---------------------|------:|-------------:|-------------:|------------:|------------:|------------------:|------------------:|--------------:|--------------:|-----------------------:|-------------------------------:|
| calendar        | arso                 |  2532 |         2124 |         2272 |           1 |          31 |            0.8389 |            0.8973 |        0.0005 |        0.0136 |                 0.0585 |                         0.0132 |
| calendar        | chmi                 |  3016 |         1887 |         2553 |           0 |          47 |            0.6257 |            0.8465 |        0.0000 |        0.0184 |                 0.2208 |                         0.0184 |
| calendar        | foen                 |   276 |          276 |          261 |           0 |           0 |            1.0000 |            0.9457 |        0.0000 |        0.0000 |                -0.0543 |                         0.0000 |
| calendar        | gkd_bayern           |  7158 |         6885 |         6702 |           4 |          16 |            0.9619 |            0.9363 |        0.0006 |        0.0024 |                -0.0256 |                         0.0018 |
| calendar        | hubeau               |   311 |          166 |            0 |           0 |           0 |            0.5338 |            0.0000 |        0.0000 |      nan      |                -0.5338 |                       nan      |
| calendar        | lubw                 |  1168 |         1094 |         1091 |           0 |           6 |            0.9366 |            0.9341 |        0.0000 |        0.0055 |                -0.0026 |                         0.0055 |
| calendar        | nve_hydapi           |  1681 |         1409 |         1290 |           1 |          20 |            0.8382 |            0.7674 |        0.0007 |        0.0155 |                -0.0708 |                         0.0148 |
| calendar        | rws_waterwebservices |   192 |          165 |          190 |           0 |           1 |            0.8594 |            0.9896 |        0.0000 |        0.0053 |                 0.1302 |                         0.0053 |
| calendar        | syke                 |   384 |          333 |           62 |           0 |           1 |            0.8672 |            0.1615 |        0.0000 |        0.0161 |                -0.7057 |                         0.0161 |
| calendar        | usgs_huc01           |   865 |          803 |          727 |           2 |           8 |            0.9283 |            0.8405 |        0.0025 |        0.0110 |                -0.0879 |                         0.0085 |
| calendar        | usgs_huc02           |  1784 |         1554 |         1459 |           0 |          10 |            0.8711 |            0.8178 |        0.0000 |        0.0069 |                -0.0533 |                         0.0069 |
| calendar        | usgs_huc03           |  2676 |         2443 |         2322 |           0 |          12 |            0.9129 |            0.8677 |        0.0000 |        0.0052 |                -0.0452 |                         0.0052 |
| calendar        | usgs_huc04           |  1009 |          895 |          839 |           0 |           0 |            0.8870 |            0.8315 |        0.0000 |        0.0000 |                -0.0555 |                         0.0000 |
| calendar        | usgs_huc05           |  1606 |         1391 |         1301 |           0 |           3 |            0.8661 |            0.8101 |        0.0000 |        0.0023 |                -0.0560 |                         0.0023 |
| calendar        | usgs_huc06           |   152 |          137 |          134 |           0 |           1 |            0.9013 |            0.8816 |        0.0000 |        0.0075 |                -0.0197 |                         0.0075 |
| calendar        | usgs_huc07           |   314 |          245 |          275 |           0 |           3 |            0.7803 |            0.8758 |        0.0000 |        0.0109 |                 0.0955 |                         0.0109 |
| calendar        | usgs_huc08           |   203 |          165 |          111 |           0 |           0 |            0.8128 |            0.5468 |        0.0000 |        0.0000 |                -0.2660 |                         0.0000 |
| calendar        | usgs_huc09           |    53 |           43 |           27 |           0 |           0 |            0.8113 |            0.5094 |        0.0000 |        0.0000 |                -0.3019 |                         0.0000 |
| calendar        | usgs_huc10           |   957 |          835 |          825 |           0 |           9 |            0.8725 |            0.8621 |        0.0000 |        0.0109 |                -0.0104 |                         0.0109 |
| calendar        | usgs_huc11           |   160 |          130 |          125 |           0 |           1 |            0.8125 |            0.7812 |        0.0000 |        0.0080 |                -0.0312 |                         0.0080 |
| calendar        | usgs_huc12           |   106 |           90 |           52 |           0 |           0 |            0.8491 |            0.4906 |        0.0000 |        0.0000 |                -0.3585 |                         0.0000 |
| calendar        | usgs_huc14           |   216 |          183 |          157 |           0 |           2 |            0.8472 |            0.7269 |        0.0000 |        0.0127 |                -0.1204 |                         0.0127 |
| calendar        | usgs_huc15           |    80 |           65 |           37 |           0 |           1 |            0.8125 |            0.4625 |        0.0000 |        0.0270 |                -0.3500 |                         0.0270 |
| calendar        | usgs_huc16           |    55 |           49 |           52 |           0 |           0 |            0.8909 |            0.9455 |        0.0000 |        0.0000 |                 0.0545 |                         0.0000 |
| calendar        | usgs_huc17           |  3813 |         2829 |         3437 |           0 |          11 |            0.7419 |            0.9014 |        0.0000 |        0.0032 |                 0.1595 |                         0.0032 |
| calendar        | usgs_huc18           |   429 |          372 |          387 |           0 |           4 |            0.8671 |            0.9021 |        0.0000 |        0.0103 |                 0.0350 |                         0.0103 |
| calendar        | usgs_huc19           |   476 |          328 |          402 |           0 |           3 |            0.6891 |            0.8445 |        0.0000 |        0.0075 |                 0.1555 |                         0.0075 |
| crossed         | arso                 |  7596 |         6399 |         6450 |         221 |         244 |            0.8424 |            0.8491 |        0.0345 |        0.0378 |                 0.0067 |                         0.0033 |
| crossed         | chmi                 | 15336 |         9093 |        10891 |         214 |         585 |            0.5929 |            0.7102 |        0.0235 |        0.0537 |                 0.1172 |                         0.0302 |
| crossed         | foen                 |  4968 |         4590 |         4818 |          61 |          97 |            0.9239 |            0.9698 |        0.0133 |        0.0201 |                 0.0459 |                         0.0068 |
| crossed         | gkd_bayern           | 21960 |        17186 |        17110 |         740 |         769 |            0.7826 |            0.7791 |        0.0431 |        0.0449 |                -0.0035 |                         0.0019 |
| crossed         | hubeau               |  1314 |          671 |            0 |          14 |           0 |            0.5107 |            0.0000 |        0.0209 |      nan      |                -0.5107 |                       nan      |
| crossed         | lubw                 |  3528 |         2837 |         2777 |         151 |         164 |            0.8041 |            0.7871 |        0.0532 |        0.0591 |                -0.0170 |                         0.0058 |
| crossed         | nve_hydapi           |  5094 |         3942 |         3788 |         325 |         371 |            0.7739 |            0.7436 |        0.0824 |        0.0979 |                -0.0302 |                         0.0155 |
| crossed         | rws_waterwebservices |   576 |          448 |          477 |          21 |          29 |            0.7778 |            0.8281 |        0.0469 |        0.0608 |                 0.0503 |                         0.0139 |
| crossed         | syke                 |  1278 |          745 |          127 |          66 |           5 |            0.5829 |            0.0994 |        0.0886 |        0.0394 |                -0.4836 |                        -0.0492 |
| crossed         | usgs_huc01           |  2988 |         1833 |         1765 |         123 |         128 |            0.6135 |            0.5907 |        0.0671 |        0.0725 |                -0.0228 |                         0.0054 |
| crossed         | usgs_huc02           |  6372 |         4110 |         3787 |         174 |         189 |            0.6450 |            0.5943 |        0.0423 |        0.0499 |                -0.0507 |                         0.0076 |
| crossed         | usgs_huc03           |  9270 |         7288 |         7474 |         293 |         380 |            0.7862 |            0.8063 |        0.0402 |        0.0508 |                 0.0201 |                         0.0106 |
| crossed         | usgs_huc04           |  3546 |         2600 |         2542 |          47 |          66 |            0.7332 |            0.7169 |        0.0181 |        0.0260 |                -0.0164 |                         0.0079 |
| crossed         | usgs_huc05           |  5724 |         3504 |         3520 |         130 |         167 |            0.6122 |            0.6150 |        0.0371 |        0.0474 |                 0.0028 |                         0.0103 |
| crossed         | usgs_huc06           |   522 |          399 |          411 |          29 |          34 |            0.7644 |            0.7874 |        0.0727 |        0.0827 |                 0.0230 |                         0.0100 |
| crossed         | usgs_huc07           |  1134 |          679 |          750 |          23 |          53 |            0.5988 |            0.6614 |        0.0339 |        0.0707 |                 0.0626 |                         0.0368 |
| crossed         | usgs_huc08           |   720 |          462 |          379 |           2 |           2 |            0.6417 |            0.5264 |        0.0043 |        0.0053 |                -0.1153 |                         0.0009 |
| crossed         | usgs_huc09           |   180 |          104 |           55 |           3 |           2 |            0.5778 |            0.3056 |        0.0288 |        0.0364 |                -0.2722 |                         0.0075 |
| crossed         | usgs_huc10           |  3294 |         2219 |         2281 |         130 |         166 |            0.6736 |            0.6925 |        0.0586 |        0.0728 |                 0.0188 |                         0.0142 |
| crossed         | usgs_huc11           |   594 |          366 |          358 |          26 |          27 |            0.6162 |            0.6027 |        0.0710 |        0.0754 |                -0.0135 |                         0.0044 |
| crossed         | usgs_huc12           |   360 |          245 |          158 |           6 |           9 |            0.6806 |            0.4389 |        0.0245 |        0.0570 |                -0.2417 |                         0.0325 |
| crossed         | usgs_huc14           |   738 |          472 |          373 |          38 |          23 |            0.6396 |            0.5054 |        0.0805 |        0.0617 |                -0.1341 |                        -0.0188 |
| crossed         | usgs_huc15           |   270 |          165 |           88 |           7 |           6 |            0.6111 |            0.3259 |        0.0424 |        0.0682 |                -0.2852 |                         0.0258 |
| crossed         | usgs_huc16           |   198 |          112 |          143 |           4 |          11 |            0.5657 |            0.7222 |        0.0357 |        0.0769 |                 0.1566 |                         0.0412 |
| crossed         | usgs_huc17           | 13284 |         8541 |         9157 |         206 |         332 |            0.6430 |            0.6893 |        0.0241 |        0.0363 |                 0.0464 |                         0.0121 |
| crossed         | usgs_huc18           |  1458 |         1063 |         1183 |          62 |          90 |            0.7291 |            0.8114 |        0.0583 |        0.0761 |                 0.0823 |                         0.0178 |
| crossed         | usgs_huc19           |  1710 |          907 |         1307 |          17 |          77 |            0.5304 |            0.7643 |        0.0187 |        0.0589 |                 0.2339 |                         0.0402 |

| design_family   | excluded_region      |           n |   score_kept |   three_kept |   score_bad |   three_bad |   score_retention |   three_retention |   score_error |   three_error |   retention_difference |   conditional_error_difference |
|:----------------|:---------------------|------------:|-------------:|-------------:|------------:|------------:|------------------:|------------------:|--------------:|--------------:|-----------------------:|-------------------------------:|
| calendar        | arso                 |  29140.0000 |   24772.0000 |   24818.0000 |      7.0000 |    159.0000 |            0.8501 |            0.8517 |        0.0003 |        0.0064 |                 0.0016 |                         0.0061 |
| calendar        | chmi                 |  28656.0000 |   25009.0000 |   24537.0000 |      8.0000 |    143.0000 |            0.8727 |            0.8563 |        0.0003 |        0.0058 |                -0.0165 |                         0.0055 |
| calendar        | foen                 |  31396.0000 |   26620.0000 |   26829.0000 |      8.0000 |    190.0000 |            0.8479 |            0.8545 |        0.0003 |        0.0071 |                 0.0067 |                         0.0068 |
| calendar        | gkd_bayern           |  24514.0000 |   20011.0000 |   20388.0000 |      4.0000 |    174.0000 |            0.8163 |            0.8317 |        0.0002 |        0.0085 |                 0.0154 |                         0.0083 |
| calendar        | hubeau               |  31361.0000 |   26730.0000 |   27090.0000 |      8.0000 |    190.0000 |            0.8523 |            0.8638 |        0.0003 |        0.0070 |                 0.0115 |                         0.0067 |
| calendar        | lubw                 |  30504.0000 |   25802.0000 |   25999.0000 |      8.0000 |    184.0000 |            0.8459 |            0.8523 |        0.0003 |        0.0071 |                 0.0065 |                         0.0068 |
| calendar        | nve_hydapi           |  29991.0000 |   25487.0000 |   25800.0000 |      7.0000 |    170.0000 |            0.8498 |            0.8603 |        0.0003 |        0.0066 |                 0.0104 |                         0.0063 |
| calendar        | rws_waterwebservices |  31480.0000 |   26731.0000 |   26900.0000 |      8.0000 |    189.0000 |            0.8491 |            0.8545 |        0.0003 |        0.0070 |                 0.0054 |                         0.0067 |
| calendar        | syke                 |  31288.0000 |   26563.0000 |   27028.0000 |      8.0000 |    189.0000 |            0.8490 |            0.8638 |        0.0003 |        0.0070 |                 0.0149 |                         0.0067 |
| calendar        | usgs_huc01           |  30807.0000 |   26093.0000 |   26363.0000 |      6.0000 |    182.0000 |            0.8470 |            0.8557 |        0.0002 |        0.0069 |                 0.0088 |                         0.0067 |
| calendar        | usgs_huc02           |  29888.0000 |   25342.0000 |   25631.0000 |      8.0000 |    180.0000 |            0.8479 |            0.8576 |        0.0003 |        0.0070 |                 0.0097 |                         0.0067 |
| calendar        | usgs_huc03           |  28996.0000 |   24453.0000 |   24768.0000 |      8.0000 |    178.0000 |            0.8433 |            0.8542 |        0.0003 |        0.0072 |                 0.0109 |                         0.0069 |
| calendar        | usgs_huc04           |  30663.0000 |   26001.0000 |   26251.0000 |      8.0000 |    190.0000 |            0.8480 |            0.8561 |        0.0003 |        0.0072 |                 0.0082 |                         0.0069 |
| calendar        | usgs_huc05           |  30066.0000 |   25505.0000 |   25789.0000 |      8.0000 |    187.0000 |            0.8483 |            0.8577 |        0.0003 |        0.0073 |                 0.0094 |                         0.0069 |
| calendar        | usgs_huc06           |  31520.0000 |   26759.0000 |   26956.0000 |      8.0000 |    189.0000 |            0.8490 |            0.8552 |        0.0003 |        0.0070 |                 0.0062 |                         0.0067 |
| calendar        | usgs_huc07           |  31358.0000 |   26651.0000 |   26815.0000 |      8.0000 |    187.0000 |            0.8499 |            0.8551 |        0.0003 |        0.0070 |                 0.0052 |                         0.0067 |
| calendar        | usgs_huc08           |  31469.0000 |   26731.0000 |   26979.0000 |      8.0000 |    190.0000 |            0.8494 |            0.8573 |        0.0003 |        0.0070 |                 0.0079 |                         0.0067 |
| calendar        | usgs_huc09           |  31619.0000 |   26853.0000 |   27063.0000 |      8.0000 |    190.0000 |            0.8493 |            0.8559 |        0.0003 |        0.0070 |                 0.0066 |                         0.0067 |
| calendar        | usgs_huc10           |  30715.0000 |   26061.0000 |   26265.0000 |      8.0000 |    181.0000 |            0.8485 |            0.8551 |        0.0003 |        0.0069 |                 0.0066 |                         0.0066 |
| calendar        | usgs_huc11           |  31512.0000 |   26766.0000 |   26965.0000 |      8.0000 |    189.0000 |            0.8494 |            0.8557 |        0.0003 |        0.0070 |                 0.0063 |                         0.0067 |
| calendar        | usgs_huc12           |  31566.0000 |   26806.0000 |   27038.0000 |      8.0000 |    190.0000 |            0.8492 |            0.8566 |        0.0003 |        0.0070 |                 0.0073 |                         0.0067 |
| calendar        | usgs_huc14           |  31456.0000 |   26713.0000 |   26933.0000 |      8.0000 |    188.0000 |            0.8492 |            0.8562 |        0.0003 |        0.0070 |                 0.0070 |                         0.0067 |
| calendar        | usgs_huc15           |  31592.0000 |   26831.0000 |   27053.0000 |      8.0000 |    189.0000 |            0.8493 |            0.8563 |        0.0003 |        0.0070 |                 0.0070 |                         0.0067 |
| calendar        | usgs_huc16           |  31617.0000 |   26847.0000 |   27038.0000 |      8.0000 |    190.0000 |            0.8491 |            0.8552 |        0.0003 |        0.0070 |                 0.0060 |                         0.0067 |
| calendar        | usgs_huc17           |  27859.0000 |   24067.0000 |   23653.0000 |      8.0000 |    179.0000 |            0.8639 |            0.8490 |        0.0003 |        0.0076 |                -0.0149 |                         0.0072 |
| calendar        | usgs_huc18           |  31243.0000 |   26524.0000 |   26703.0000 |      8.0000 |    186.0000 |            0.8490 |            0.8547 |        0.0003 |        0.0070 |                 0.0057 |                         0.0067 |
| calendar        | usgs_huc19           |  31196.0000 |   26568.0000 |   26688.0000 |      8.0000 |    187.0000 |            0.8516 |            0.8555 |        0.0003 |        0.0070 |                 0.0038 |                         0.0067 |
| crossed         | arso                 | 106416.0000 |   74581.0000 |   75719.0000 |   2912.0000 |   3782.0000 |            0.7008 |            0.7115 |        0.0390 |        0.0499 |                 0.0107 |                         0.0109 |
| crossed         | chmi                 |  98676.0000 |   71887.0000 |   71278.0000 |   2919.0000 |   3441.0000 |            0.7285 |            0.7223 |        0.0406 |        0.0483 |                -0.0062 |                         0.0077 |
| crossed         | foen                 | 109044.0000 |   76390.0000 |   77351.0000 |   3072.0000 |   3929.0000 |            0.7005 |            0.7094 |        0.0402 |        0.0508 |                 0.0088 |                         0.0106 |
| crossed         | gkd_bayern           |  92052.0000 |   63794.0000 |   65059.0000 |   2393.0000 |   3257.0000 |            0.6930 |            0.7068 |        0.0375 |        0.0501 |                 0.0137 |                         0.0126 |
| crossed         | hubeau               | 112698.0000 |   80309.0000 |   82169.0000 |   3119.0000 |   4026.0000 |            0.7126 |            0.7291 |        0.0388 |        0.0490 |                 0.0165 |                         0.0102 |
| crossed         | lubw                 | 110484.0000 |   78143.0000 |   79392.0000 |   2982.0000 |   3862.0000 |            0.7073 |            0.7186 |        0.0382 |        0.0486 |                 0.0113 |                         0.0105 |
| crossed         | nve_hydapi           | 108918.0000 |   77038.0000 |   78381.0000 |   2808.0000 |   3655.0000 |            0.7073 |            0.7196 |        0.0364 |        0.0466 |                 0.0123 |                         0.0102 |
| crossed         | rws_waterwebservices | 113436.0000 |   80532.0000 |   81692.0000 |   3112.0000 |   3997.0000 |            0.7099 |            0.7202 |        0.0386 |        0.0489 |                 0.0102 |                         0.0103 |
| crossed         | syke                 | 112734.0000 |   80235.0000 |   82042.0000 |   3067.0000 |   4021.0000 |            0.7117 |            0.7277 |        0.0382 |        0.0490 |                 0.0160 |                         0.0108 |
| crossed         | usgs_huc01           | 111024.0000 |   79147.0000 |   80404.0000 |   3010.0000 |   3898.0000 |            0.7129 |            0.7242 |        0.0380 |        0.0485 |                 0.0113 |                         0.0104 |
| crossed         | usgs_huc02           | 107640.0000 |   76870.0000 |   78382.0000 |   2959.0000 |   3837.0000 |            0.7141 |            0.7282 |        0.0385 |        0.0490 |                 0.0140 |                         0.0105 |
| crossed         | usgs_huc03           | 104742.0000 |   73692.0000 |   74695.0000 |   2840.0000 |   3646.0000 |            0.7036 |            0.7131 |        0.0385 |        0.0488 |                 0.0096 |                         0.0103 |
| crossed         | usgs_huc04           | 110466.0000 |   78380.0000 |   79627.0000 |   3086.0000 |   3960.0000 |            0.7095 |            0.7208 |        0.0394 |        0.0497 |                 0.0113 |                         0.0104 |
| crossed         | usgs_huc05           | 108288.0000 |   77476.0000 |   78649.0000 |   3003.0000 |   3859.0000 |            0.7155 |            0.7263 |        0.0388 |        0.0491 |                 0.0108 |                         0.0103 |
| crossed         | usgs_huc06           | 113490.0000 |   80581.0000 |   81758.0000 |   3104.0000 |   3992.0000 |            0.7100 |            0.7204 |        0.0385 |        0.0488 |                 0.0104 |                         0.0103 |
| crossed         | usgs_huc07           | 112878.0000 |   80301.0000 |   81419.0000 |   3110.0000 |   3973.0000 |            0.7114 |            0.7213 |        0.0387 |        0.0488 |                 0.0099 |                         0.0101 |
| crossed         | usgs_huc08           | 113292.0000 |   80518.0000 |   81790.0000 |   3131.0000 |   4024.0000 |            0.7107 |            0.7219 |        0.0389 |        0.0492 |                 0.0112 |                         0.0103 |
| crossed         | usgs_huc09           | 113832.0000 |   80876.0000 |   82114.0000 |   3130.0000 |   4024.0000 |            0.7105 |            0.7214 |        0.0387 |        0.0490 |                 0.0109 |                         0.0103 |
| crossed         | usgs_huc10           | 110718.0000 |   78761.0000 |   79888.0000 |   3003.0000 |   3860.0000 |            0.7114 |            0.7215 |        0.0381 |        0.0483 |                 0.0102 |                         0.0102 |
| crossed         | usgs_huc11           | 113418.0000 |   80614.0000 |   81811.0000 |   3107.0000 |   3999.0000 |            0.7108 |            0.7213 |        0.0385 |        0.0489 |                 0.0106 |                         0.0103 |
| crossed         | usgs_huc12           | 113652.0000 |   80735.0000 |   82011.0000 |   3127.0000 |   4017.0000 |            0.7104 |            0.7216 |        0.0387 |        0.0490 |                 0.0112 |                         0.0102 |
| crossed         | usgs_huc14           | 113274.0000 |   80508.0000 |   81796.0000 |   3095.0000 |   4003.0000 |            0.7107 |            0.7221 |        0.0384 |        0.0489 |                 0.0114 |                         0.0105 |
| crossed         | usgs_huc15           | 113742.0000 |   80815.0000 |   82081.0000 |   3126.0000 |   4020.0000 |            0.7105 |            0.7216 |        0.0387 |        0.0490 |                 0.0111 |                         0.0103 |
| crossed         | usgs_huc16           | 113814.0000 |   80868.0000 |   82026.0000 |   3129.0000 |   4015.0000 |            0.7105 |            0.7207 |        0.0387 |        0.0489 |                 0.0102 |                         0.0103 |
| crossed         | usgs_huc17           | 100728.0000 |   72439.0000 |   73012.0000 |   2927.0000 |   3694.0000 |            0.7192 |            0.7248 |        0.0404 |        0.0506 |                 0.0057 |                         0.0102 |
| crossed         | usgs_huc18           | 112554.0000 |   79917.0000 |   80986.0000 |   3071.0000 |   3936.0000 |            0.7100 |            0.7195 |        0.0384 |        0.0486 |                 0.0095 |                         0.0102 |
| crossed         | usgs_huc19           | 112302.0000 |   80073.0000 |   80862.0000 |   3116.0000 |   3949.0000 |            0.7130 |            0.7200 |        0.0389 |        0.0488 |                 0.0070 |                         0.0099 |

## 三类输出和既有失败条件

输出数值、观测窗口下界或未知。可见诊断在源域确定，污染标签和隐藏温度仅用于最后评分。空气贴合诊断只针对既有七日精确替换情景，不能作为通用设备故障识别器。完全拒绝发布时风险为未定义；保留下界仍要求测量有效。

| condition              | family   |   n_eligible |   estimate_fraction |   bound_fraction |   unknown_fraction |   quality_flag_fraction |   false_bound_fraction_among_bounds |   observed_hot_information_fraction |   retained_hot_information_fraction |
|:-----------------------|:---------|-------------:|--------------------:|-----------------:|-------------------:|------------------------:|------------------------------------:|------------------------------------:|------------------------------------:|
| clean                  | calendar |        31672 |              0.8553 |           0.1422 |             0.0024 |                  0.0000 |                              0.0000 |                              0.1441 |                              0.1441 |
| clean                  | crossed  |       114012 |              0.7207 |           0.2793 |             0.0000 |                  0.0000 |                              0.0000 |                              0.0870 |                              0.0870 |
| air_exposure           | calendar |        31672 |              0.0028 |           0.0321 |             0.9651 |                  0.9641 |                              0.0000 |                              0.2591 |                              0.0018 |
| air_exposure           | crossed  |       114012 |              0.0000 |           0.0204 |             0.9796 |                  0.9796 |                              0.0000 |                              0.1785 |                              0.0014 |
| hot_year_extrapolation | calendar |         7453 |              0.8538 |           0.1448 |             0.0015 |                  0.0000 |                              0.0000 |                              0.8662 |                              0.8662 |
| hot_year_extrapolation | crossed  |        26730 |              0.7620 |           0.2380 |             0.0000 |                  0.0000 |                              0.0000 |                              0.5667 |                              0.5667 |
| future_years           | calendar |         7310 |              0.7390 |           0.2580 |             0.0030 |                  0.0000 |                              0.0000 |                              0.3525 |                              0.3525 |
| future_years           | crossed  |        27846 |              0.6314 |           0.3686 |             0.0000 |                  0.0000 |                              0.0000 |                              0.2380 |                              0.2380 |
| smooth_non_air_shift   | calendar |        31672 |              0.8551 |           0.1425 |             0.0024 |                  0.0000 |                              0.0000 |                              0.1446 |                              0.1446 |
| smooth_non_air_shift   | crossed  |       114012 |              0.7120 |           0.2880 |             0.0000 |                  0.0000 |                              0.0000 |                              0.0876 |                              0.0876 |

| condition              |   n_true_hot |   n_hot_detected |   n_hot_missed_or_withheld |   n_false_hot |   hot_recall |
|:-----------------------|-------------:|-----------------:|---------------------------:|--------------:|-------------:|
| clean                  |         5403 |             4984 |                        419 |            47 |       0.9225 |
| air_exposure           |         5403 |               62 |                       5341 |             3 |       0.0115 |
| hot_year_extrapolation |         7453 |             7020 |                        433 |             0 |       0.9419 |
| future_years           |         2927 |             2728 |                        199 |            10 |       0.9320 |
| smooth_non_air_shift   |         5424 |             4987 |                        437 |            43 |       0.9194 |

漏检或保留未知的热事件、错误热事件和错误数值发布均单独记录于修订结果的热事件表与发布表。风险阈值是原始个体分类分数而非群组风险证书。不同污染比例是情景曲线，不是全国发生率估计。

## 地区与独立组敏感性

42站归为18个连接组。配对误差差异按组重采样并分别列出逐地区删除结果；群组和年份之间的气候独立性仍是条件假设。

| family   | mode    | left   | right                 |   n_common |   n_groups |   n_stations |   pooled_mse_difference |   pooled_cluster_bootstrap_low |   pooled_cluster_bootstrap_high |   group_equal_mse_difference |   group_equal_bootstrap_low |   group_equal_bootstrap_high |
|:---------|:--------|:-------|:----------------------|-----------:|-----------:|-------------:|------------------------:|-------------------------------:|--------------------------------:|-----------------------------:|----------------------------:|-----------------------------:|
| calendar | forward | D2     | stochastic_calibrated |        701 |         17 |           41 |                 0.00118 |                       -0.00020 |                         0.00269 |                      0.00054 |                    -0.00068 |                      0.00173 |
| calendar | forward | D2     | plug_in               |        820 |         17 |           41 |                -0.00326 |                       -0.00555 |                        -0.00140 |                     -0.00420 |                    -0.00715 |                     -0.00183 |
| calendar | offline | D2     | stochastic_calibrated |        835 |         18 |           42 |                -0.00005 |                       -0.00014 |                        -0.00001 |                     -0.00010 |                    -0.00023 |                     -0.00000 |
| calendar | offline | D2     | plug_in               |        840 |         18 |           42 |                -0.00011 |                       -0.00023 |                        -0.00004 |                     -0.00017 |                    -0.00035 |                     -0.00004 |
| crossed  | forward | D2     | stochastic_calibrated |        738 |         17 |           41 |                 0.00535 |                        0.00087 |                         0.01008 |                      0.00350 |                    -0.00018 |                      0.00696 |
| crossed  | forward | D2     | plug_in               |        820 |         17 |           41 |                -0.02196 |                       -0.03503 |                        -0.00901 |                     -0.02155 |                    -0.03350 |                     -0.01151 |
| crossed  | offline | D2     | stochastic_calibrated |        838 |         18 |           42 |                -0.00026 |                       -0.00061 |                        -0.00006 |                     -0.00048 |                    -0.00109 |                     -0.00005 |
| crossed  | offline | D2     | plug_in               |        840 |         18 |           42 |                -0.00130 |                       -0.00263 |                        -0.00045 |                     -0.00208 |                    -0.00414 |                     -0.00042 |

| family   | mode    | left   | right                 | excluded_region   |   n_remaining |   n_groups |   pooled_mse_difference |
|:---------|:--------|:-------|:----------------------|:------------------|--------------:|-----------:|------------------------:|
| calendar | forward | D2     | stochastic_calibrated | foen              |           501 |         15 |                 0.00165 |
| calendar | forward | D2     | stochastic_calibrated | gkd_bayern        |           332 |          9 |                -0.00021 |
| calendar | forward | D2     | stochastic_calibrated | usgs_huc03        |           681 |         16 |                 0.00121 |
| calendar | forward | D2     | stochastic_calibrated | usgs_huc04        |           681 |         16 |                 0.00128 |
| calendar | forward | D2     | stochastic_calibrated | usgs_huc10        |           669 |         15 |                 0.00127 |
| calendar | forward | D2     | stochastic_calibrated | usgs_huc17        |           641 |         14 |                 0.00131 |
| calendar | forward | D2     | plug_in               | foen              |           620 |         15 |                -0.00431 |
| calendar | forward | D2     | plug_in               | gkd_bayern        |           340 |          9 |                -0.00225 |
| calendar | forward | D2     | plug_in               | usgs_huc03        |           800 |         16 |                -0.00334 |
| calendar | forward | D2     | plug_in               | usgs_huc04        |           800 |         16 |                -0.00292 |
| calendar | forward | D2     | plug_in               | usgs_huc10        |           780 |         15 |                -0.00325 |
| calendar | forward | D2     | plug_in               | usgs_huc17        |           760 |         14 |                -0.00314 |
| calendar | offline | D2     | stochastic_calibrated | foen              |           635 |         16 |                -0.00007 |
| calendar | offline | D2     | stochastic_calibrated | gkd_bayern        |           356 |         10 |                -0.00009 |
| calendar | offline | D2     | stochastic_calibrated | syke              |           819 |         17 |                -0.00005 |
| calendar | offline | D2     | stochastic_calibrated | usgs_huc03        |           815 |         17 |                -0.00005 |
| calendar | offline | D2     | stochastic_calibrated | usgs_huc04        |           815 |         17 |                -0.00005 |
| calendar | offline | D2     | stochastic_calibrated | usgs_huc10        |           795 |         16 |                -0.00004 |
| calendar | offline | D2     | stochastic_calibrated | usgs_huc17        |           775 |         15 |                -0.00003 |
| calendar | offline | D2     | plug_in               | foen              |           640 |         16 |                -0.00015 |
| calendar | offline | D2     | plug_in               | gkd_bayern        |           360 |         10 |                -0.00014 |
| calendar | offline | D2     | plug_in               | syke              |           820 |         17 |                -0.00011 |
| calendar | offline | D2     | plug_in               | usgs_huc03        |           820 |         17 |                -0.00011 |
| calendar | offline | D2     | plug_in               | usgs_huc04        |           820 |         17 |                -0.00011 |
| calendar | offline | D2     | plug_in               | usgs_huc10        |           800 |         16 |                -0.00007 |
| calendar | offline | D2     | plug_in               | usgs_huc17        |           780 |         15 |                -0.00011 |
| crossed  | forward | D2     | stochastic_calibrated | foen              |           538 |         15 |                 0.00759 |
| crossed  | forward | D2     | stochastic_calibrated | gkd_bayern        |           331 |          9 |                -0.00014 |
| crossed  | forward | D2     | stochastic_calibrated | usgs_huc03        |           718 |         16 |                 0.00550 |
| crossed  | forward | D2     | stochastic_calibrated | usgs_huc04        |           718 |         16 |                 0.00572 |
| crossed  | forward | D2     | stochastic_calibrated | usgs_huc10        |           707 |         15 |                 0.00576 |
| crossed  | forward | D2     | stochastic_calibrated | usgs_huc17        |           678 |         14 |                 0.00528 |
| crossed  | forward | D2     | plug_in               | foen              |           620 |         15 |                -0.02896 |
| crossed  | forward | D2     | plug_in               | gkd_bayern        |           340 |          9 |                -0.00590 |
| crossed  | forward | D2     | plug_in               | usgs_huc03        |           800 |         16 |                -0.02253 |
| crossed  | forward | D2     | plug_in               | usgs_huc04        |           800 |         16 |                -0.02193 |
| crossed  | forward | D2     | plug_in               | usgs_huc10        |           780 |         15 |                -0.02214 |
| crossed  | forward | D2     | plug_in               | usgs_huc17        |           760 |         14 |                -0.02271 |
| crossed  | offline | D2     | stochastic_calibrated | foen              |           638 |         16 |                -0.00033 |
| crossed  | offline | D2     | stochastic_calibrated | gkd_bayern        |           359 |         10 |                -0.00047 |
| crossed  | offline | D2     | stochastic_calibrated | syke              |           818 |         17 |                -0.00025 |
| crossed  | offline | D2     | stochastic_calibrated | usgs_huc03        |           818 |         17 |                -0.00025 |
| crossed  | offline | D2     | stochastic_calibrated | usgs_huc04        |           818 |         17 |                -0.00027 |
| crossed  | offline | D2     | stochastic_calibrated | usgs_huc10        |           799 |         16 |                -0.00009 |
| crossed  | offline | D2     | stochastic_calibrated | usgs_huc17        |           778 |         15 |                -0.00026 |
| crossed  | offline | D2     | plug_in               | foen              |           640 |         16 |                -0.00168 |
| crossed  | offline | D2     | plug_in               | gkd_bayern        |           360 |         10 |                -0.00194 |
| crossed  | offline | D2     | plug_in               | syke              |           820 |         17 |                -0.00119 |
| crossed  | offline | D2     | plug_in               | usgs_huc03        |           820 |         17 |                -0.00133 |
| crossed  | offline | D2     | plug_in               | usgs_huc04        |           820 |         17 |                -0.00134 |
| crossed  | offline | D2     | plug_in               | usgs_huc10        |           800 |         16 |                -0.00072 |
| crossed  | offline | D2     | plug_in               | usgs_huc17        |           780 |         15 |                -0.00134 |

## 热相关缺测和邻站同时缺测

每地区按既定顺序各取一站、每站五次掩码。邻站试验对目标站与同一面板邻站同步隐藏相同日期；热相关试验以最早七年气温热峰确定阈值，选择热年及其他年的缺测概率分别为0.90和0.18，因而两臂掩码和缺测率并不完全相同。芬兰站因气温数据不足在热相关情景中不可用。

| family   | mode    | estimator   | retention   | dependence   | scenario            |   paired_rows |   both_available |   baseline_availability |   stress_availability |   n_stations |   n_groups |   baseline_incomplete_years |   stress_incomplete_years |   baseline_rmse |   stress_rmse |   baseline_coverage95 |   stress_coverage95 |   baseline_width95 |   stress_width95 |   baseline_interval_score95 |   stress_interval_score95 |
|:---------|:--------|:------------|:------------|:-------------|:--------------------|--------------:|-----------------:|------------------------:|----------------------:|-------------:|-----------:|----------------------------:|--------------------------:|----------------:|--------------:|----------------------:|--------------------:|-------------------:|-----------------:|----------------------------:|--------------------------:|
| crossed  | forward | D2          | all         | independent  | synchronized_donors |            30 |               30 |                 1.00000 |               1.00000 |            6 |          6 |                     5.26667 |                   5.26667 |         0.07938 |       0.11641 |               0.96667 |             0.90000 |            0.39806 |          0.51850 |                     0.40276 |                   0.69361 |
| crossed  | offline | D2          | all         | independent  | synchronized_donors |            35 |               35 |                 1.00000 |               1.00000 |            7 |          7 |                     6.85714 |                   6.85714 |         0.03713 |       0.04726 |               0.91429 |             0.94286 |            0.09240 |          0.14711 |                     0.16355 |                   0.19260 |
| crossed  | forward | D2          | all         | independent  | heat_associated     |            30 |               30 |                 1.00000 |               1.00000 |            6 |          6 |                     5.26667 |                   5.93333 |         0.07938 |       0.08849 |               0.96667 |             1.00000 |            0.39806 |          0.44096 |                     0.40276 |                   0.44096 |
| crossed  | offline | D2          | all         | independent  | heat_associated     |            35 |               30 |                 1.00000 |               0.85714 |            7 |          7 |                     6.03333 |                   6.63333 |         0.03524 |       0.05782 |               0.93333 |             0.80000 |            0.09324 |          0.11403 |                     0.13258 |                   0.23264 |

## 发布后趋势：数值与删失下界

已将实际三类输出接入趋势：数值视为精确观测，观测下界作为右删失，未知年份保留在可用率分母。Gaussian工作区间包含回归变化，不是已校准的缺测部分区间；分别与所有年份D2和暖季规则在共同案例上比较。

| family   | mode    | method                     |   n_eligible |   n_available |   availability |   n_stations |   n_groups |   total_masked |   total_estimates |   total_bounds |   total_unknown |   rmse |    bias |   total_working_coverage95 |   total_working_width95 |   total_working_interval_score95 |
|:---------|:--------|:---------------------------|-------------:|--------------:|---------------:|-------------:|-----------:|---------------:|------------------:|---------------:|----------------:|-------:|--------:|---------------------------:|------------------------:|---------------------------------:|
| calendar | forward | released_values_and_bounds |          820 |           819 |         0.9988 |           41 |         17 |           3806 |              3435 |            371 |               0 | 0.1240 |  0.0035 |                     1.0000 |                  3.3980 |                           3.3980 |
| calendar | forward | released_values_only       |          820 |           819 |         0.9988 |           41 |         17 |           3806 |              3435 |            371 |               0 | 0.1345 | -0.0085 |                   nan      |                nan      |                         nan      |
| calendar | offline | released_values_and_bounds |          840 |           840 |         1.0000 |           42 |         18 |           6942 |              6345 |            590 |               7 | 0.0198 |  0.0021 |                     0.9976 |                  2.8710 |                           2.8713 |
| calendar | offline | released_values_only       |          840 |           840 |         1.0000 |           42 |         18 |           6942 |              6345 |            590 |               7 | 0.0202 | -0.0024 |                   nan      |                nan      |                         nan      |
| crossed  | forward | released_values_and_bounds |          820 |           820 |         1.0000 |           41 |         17 |           3777 |              3174 |            603 |               0 | 0.2024 |  0.0017 |                     0.9976 |                  3.2615 |                           3.2667 |
| crossed  | forward | released_values_only       |          820 |           820 |         1.0000 |           41 |         17 |           3777 |              3174 |            603 |               0 | 0.2099 | -0.0141 |                   nan      |                nan      |                         nan      |
| crossed  | offline | released_values_and_bounds |          840 |           840 |         1.0000 |           42 |         18 |           6921 |              5543 |           1378 |               0 | 0.0405 | -0.0034 |                     0.9940 |                  1.9855 |                           1.9876 |
| crossed  | offline | released_values_only       |          840 |           840 |         1.0000 |           42 |         18 |           6921 |              5543 |           1378 |               0 | 0.0429 | -0.0065 |                   nan      |                nan      |                         nan      |

| family   | mode    | release_method             | baseline   |   n_eligible |   n_common |   baseline_availability |   release_availability |   n_groups |   baseline_rmse |   release_rmse |   paired_mse_difference |   group_equal_mse_difference |   cluster_bootstrap_low |   cluster_bootstrap_high |
|:---------|:--------|:---------------------------|:-----------|-------------:|-----------:|------------------------:|-----------------------:|-----------:|----------------:|---------------:|------------------------:|-----------------------------:|------------------------:|-------------------------:|
| calendar | forward | released_values_only       | warm90     |          820 |        819 |                  1.0000 |                 0.9988 |         17 |          0.1135 |         0.1345 |                  0.0052 |                       0.0005 |                 -0.0038 |                   0.0124 |
| calendar | offline | released_values_only       | warm90     |          840 |        840 |                  1.0000 |                 1.0000 |         18 |          0.0240 |         0.0202 |                 -0.0002 |                      -0.0002 |                 -0.0004 |                   0.0000 |
| crossed  | forward | released_values_only       | warm90     |          820 |        807 |                  0.9841 |                 1.0000 |         17 |          0.4453 |         0.2062 |                 -0.1558 |                      -0.1046 |                 -0.2591 |                  -0.0743 |
| crossed  | offline | released_values_only       | warm90     |          840 |        840 |                  1.0000 |                 1.0000 |         18 |          0.1006 |         0.0429 |                 -0.0083 |                      -0.0078 |                 -0.0127 |                  -0.0042 |
| calendar | forward | released_values_and_bounds | warm90     |          820 |        819 |                  1.0000 |                 0.9988 |         17 |          0.1135 |         0.1240 |                  0.0025 |                      -0.0004 |                 -0.0014 |                   0.0048 |
| calendar | offline | released_values_and_bounds | warm90     |          840 |        840 |                  1.0000 |                 1.0000 |         18 |          0.0240 |         0.0198 |                 -0.0002 |                      -0.0002 |                 -0.0004 |                   0.0000 |
| crossed  | forward | released_values_and_bounds | warm90     |          820 |        807 |                  0.9841 |                 1.0000 |         17 |          0.4453 |         0.1991 |                 -0.1587 |                      -0.1085 |                 -0.2623 |                  -0.0774 |
| crossed  | offline | released_values_and_bounds | warm90     |          840 |        840 |                  1.0000 |                 1.0000 |         18 |          0.1006 |         0.0405 |                 -0.0085 |                      -0.0080 |                 -0.0130 |                  -0.0044 |
| calendar | forward | released_values_only       | all        |          820 |        819 |                  1.0000 |                 0.9988 |         17 |          0.0672 |         0.1345 |                  0.0136 |                       0.0094 |                  0.0036 |                   0.0232 |
| calendar | offline | released_values_only       | all        |          840 |        840 |                  1.0000 |                 1.0000 |         18 |          0.0087 |         0.0202 |                  0.0003 |                       0.0004 |                  0.0002 |                   0.0005 |
| crossed  | forward | released_values_only       | all        |          820 |        820 |                  1.0000 |                 1.0000 |         17 |          0.1735 |         0.2099 |                  0.0140 |                       0.0147 |                  0.0091 |                   0.0199 |
| crossed  | offline | released_values_only       | all        |          840 |        840 |                  1.0000 |                 1.0000 |         18 |          0.0278 |         0.0429 |                  0.0011 |                       0.0011 |                  0.0007 |                   0.0015 |
| calendar | forward | released_values_and_bounds | all        |          820 |        819 |                  1.0000 |                 0.9988 |         17 |          0.0672 |         0.1240 |                  0.0109 |                       0.0086 |                  0.0053 |                   0.0164 |
| calendar | offline | released_values_and_bounds | all        |          840 |        840 |                  1.0000 |                 1.0000 |         18 |          0.0087 |         0.0198 |                  0.0003 |                       0.0004 |                  0.0002 |                   0.0005 |
| crossed  | forward | released_values_and_bounds | all        |          820 |        820 |                  1.0000 |                 1.0000 |         17 |          0.1735 |         0.2024 |                  0.0109 |                       0.0106 |                  0.0051 |                   0.0169 |
| crossed  | offline | released_values_and_bounds | all        |          840 |        840 |                  1.0000 |                 1.0000 |         18 |          0.0278 |         0.0405 |                  0.0009 |                       0.0009 |                  0.0005 |                   0.0013 |

将无法计算水温—气温贴合诊断的年份视为未知，是一个探索性保守选择；原规则未评估并不等于诊断通过。

| family   | mode    | method                     |   n_eligible |   n_common |   strict_availability |   original_availability |   n_unassessed_years |   strict_estimates |   original_estimates |   original_rmse |   strict_rmse |
|:---------|:--------|:---------------------------|-------------:|-----------:|----------------------:|------------------------:|---------------------:|-------------------:|---------------------:|----------------:|--------------:|
| calendar | forward | released_values_and_bounds |          820 |        819 |                0.9988 |                  0.9988 |                    0 |               3435 |                 3435 |          0.1240 |        0.1240 |
| calendar | forward | released_values_only       |          820 |        819 |                0.9988 |                  0.9988 |                    0 |               3435 |                 3435 |          0.1345 |        0.1345 |
| calendar | offline | released_values_and_bounds |          840 |        840 |                1.0000 |                  1.0000 |                  185 |               6345 |                 6345 |          0.0198 |        0.0196 |
| calendar | offline | released_values_only       |          840 |        840 |                1.0000 |                  1.0000 |                  185 |               6345 |                 6345 |          0.0202 |        0.0202 |
| crossed  | forward | released_values_and_bounds |          820 |        820 |                1.0000 |                  1.0000 |                    0 |               3174 |                 3174 |          0.2024 |        0.2024 |
| crossed  | forward | released_values_only       |          820 |        820 |                1.0000 |                  1.0000 |                    0 |               3174 |                 3174 |          0.2099 |        0.2099 |
| crossed  | offline | released_values_and_bounds |          840 |        840 |                1.0000 |                  1.0000 |                  185 |               5543 |                 5543 |          0.0405 |        0.0404 |
| crossed  | offline | released_values_only       |          840 |        840 |                1.0000 |                  1.0000 |                  185 |               5543 |                 5543 |          0.0429 |        0.0429 |

## 新西兰实际资格结果

9/9站已取得日值资料。按原标准接受质量码600，0站有合格完整热年支持。返回的历史质量码没有被重贴为600，因此没有把未确认质量的记录当作参照真值，也没有计算不存在的预测精度。该检验未预注册。若要建立新区域精度证据，需要确认机构质量码定义或取得符合标准的参照资料。

## 额外批准观测对主要事实的检验

另行取得十个元数据选定USGS站的批准日均水温，未按恢复误差挑选或替换站点。七个候选位于源站未覆盖的HUC2 13/20，另外三个是既有源区域内的额外站点检验。十站均不满足原四个完整年数值恢复参照要求，因此未进行或宣称外部恢复精度验证。原先选择的主要观测主张则有不同的数学条件：只要有非空完整年纪录，就能检验不完整年的已观测窗口是否已经超出它。四站有非空批准完整年参照，其中3站、9站年出现反证。

这个额外比较保留了全部批准有限值组成的完整年作为更宽的参照集合；观测窗口排除估计值，并要求原始记录确有缺失、空值、矛盾或未批准日。仅额外质控删值不能制造证据。每个窗口的30个原始批准数值都在证据表中。额外站点仅有1—3个完整参照年，不能与原20/96长期站比例合并或解释为总体发生率，也不能确定唯一最热年或外部趋势可靠性。

|   station_id |   year |   n_raw_complete_years |   window_mean |   maximum_raw_complete_H30 |   excess |
|-------------:|-------:|-----------------------:|--------------:|---------------------------:|---------:|
|     08377900 |   2016 |                      3 |      14.99000 |                   14.85333 |  0.13667 |
|     08377900 |   2018 |                      3 |      15.53667 |                   14.85333 |  0.68333 |
|     08377900 |   2020 |                      3 |      15.73667 |                   14.85333 |  0.88333 |
|     08405200 |   2013 |                      2 |      28.69333 |                   28.32667 |  0.36667 |
|     08405200 |   2015 |                      2 |      28.70333 |                   28.32667 |  0.37667 |
|     08405200 |   2016 |                      2 |      28.53667 |                   28.32667 |  0.21000 |
|     08405200 |   2019 |                      2 |      28.83333 |                   28.32667 |  0.50667 |
|     08405200 |   2020 |                      2 |      28.97000 |                   28.32667 |  0.64333 |
|     07364133 |   2015 |                      1 |      29.42667 |                   28.76667 |  0.66000 |

## 新外部参考资格与旧接触核查

NEON公开作者归档的24站已按事先列明的单传感器、UTC日和质量标志处理；严格48/48半小时及46/48敏感性均有0站达到四个完整日历年，因此不报告恢复精度。

首次USGS参考尝试取得15站，但身份复核发现15站此前已在全国资料中处理，不能当作新独立验证。更新排除清单后另行取得8/8站，其中0站达到四个完整质量合格年；未达到资格不生成恢复精度。

留尼汪岛Hub'Eau目录按先固定的名单取得5/5站；要求正确质量码、每个报告日24个小时及四个完整7月至次年6月热年后，0站合格，0站获取不可用。该数据的报告日时区仍待提供方核实，小时均值不是无误差现场真值。

进一步从网络和既有接触清单中固定5个USGS候选，仅筛查2010—2024年官方年度已批准日值数量；0站未返回统计，0站达到至少4个计数完整年，因此没有新站进入逐日评分。计数可能包含估计值，不能代替逐日质量检查；2010—2024以外年份不在此预筛选范围。接口试点站02450250此前已在E10及早期恢复对比中评分，且本次已打开年度汇总，不能视为新站，已排除。

挪威机构公开目录中98条记录未在命名原始缓存及确认站点中匹配，其他历史接触、年份质量及河网关系仍未完成核实。排除已读原始站点所在流域后固定3站，图表服务返回0站有值、3站无值；没有因此证明无历史数据，也没有评分。机构HydAPI正式访问需要注册。英国、加拿大候选的其他来源级限制见 [外部参考线索](reviews/wrr_review_response_20261027/EXTERNAL_REFERENCE_LEADS_ZH.md)。

加拿大联邦Red River at Emerson的6个文件已获取：所选站点与源样本一站同属Red River，不是独立流域。目录字典给出V和数字1/2等级，但实际状态、等级用词不同；16209条明确写VALIDATED却缺等级，13932条站号与目录不一致。按预先固定的字面V与数字1/2条件，0个完整墙钟年；这不意味着被排除资料不可信。地方时间的夏令时约定仍未确认，不进行恢复精度评分。以前已读取的13站旧缓存，即使把每天至少24行当作乐观必要条件，最多也只有2个可能完整年，旧缓存不含唯一小时与等级信息。

Greater Wellington机构说明QC200是未经验证的数据；其具体站点旧码映射仍需提供方确认。新西兰零合格参考不能被改称成功验证。

加拿大BC作者公开数据全部23站中，4站有至少四个已发表日均值完整年份；加拿大水文部门称水温为未经统一质量保证的辅助输出，原研究自行检查并允许每天只有20小时，逐小时质控标记未公开，故严格24小时参考0站。参考清洗还使用水气温比较。四站、16个站年完成逐年留一受控缺测探索，案例并非独立气候，三站属于Fraser河流域（Nechako、Thompson和Fraser）。实际日界线未知，气温使用四舍五入到0.01度的站点坐标。以下数值不是整档案趋势外部验证。

独立重算全部372个案例的30日日均最大值、遮挡后下界和遮挡天数，并重算52项得分汇总；差异均在数值容差内。每站另选一个90日缺口，隐藏真值加5°C后四个探针的特征和预测均未变化；这不能证明其他案例或路径全部无泄漏。

| family   | stratum   | estimator             |   n_eligible |   n_available |   availability |   stations |    mae |    bias |   failure_rate |   coverage90 |   width90 |     crps |   interval_score90 |
|:---------|:----------|:----------------------|-------------:|--------------:|---------------:|-----------:|-------:|--------:|---------------:|-------------:|----------:|---------:|-------------------:|
| calendar | all       | plug_in               |           84 |            84 |         1.0000 |          4 | 0.0340 | -0.0331 |         0.0119 |     nan      |  nan      | nan      |           nan      |
| calendar | all       | D2                    |           84 |            84 |         1.0000 |          4 | 0.0304 |  0.0059 |         0.0238 |       0.9881 |    0.1323 |   0.0221 |             0.1980 |
| calendar | all       | stochastic_calibrated |           84 |            84 |         1.0000 |          4 | 0.0237 | -0.0049 |         0.0119 |       0.9643 |    0.0866 |   0.0191 |             0.2365 |
| calendar | danger    | plug_in               |            4 |             4 |         1.0000 |          1 | 0.3979 | -0.3979 |         0.2500 |     nan      |  nan      | nan      |           nan      |
| calendar | danger    | D2                    |            4 |             4 |         1.0000 |          1 | 0.3760 |  0.0221 |         0.5000 |       0.7500 |    1.2733 |   0.2852 |             2.6521 |
| calendar | danger    | stochastic_calibrated |            4 |             4 |         1.0000 |          1 | 0.4317 | -0.1097 |         0.2500 |       0.7500 |    1.4810 |   0.3512 |             4.5860 |
| crossed  | all       | plug_in               |          288 |           288 |         1.0000 |          4 | 0.5156 | -0.5039 |         0.3438 |     nan      |  nan      | nan      |           nan      |
| crossed  | all       | D2                    |          288 |           288 |         1.0000 |          4 | 0.3058 |  0.0237 |         0.2396 |       0.9514 |    1.2336 |   0.2039 |             1.4429 |
| crossed  | all       | stochastic_calibrated |          288 |           288 |         1.0000 |          4 | 0.3022 | -0.1141 |         0.2535 |       0.9132 |    1.2014 |   0.2140 |             1.4659 |
| crossed  | danger    | plug_in               |          148 |           148 |         1.0000 |          4 | 0.9170 | -0.8979 |         0.5946 |     nan      |  nan      | nan      |           nan      |
| crossed  | danger    | D2                    |          148 |           148 |         1.0000 |          4 | 0.5393 |  0.0445 |         0.4527 |       0.9324 |    2.1670 |   0.3600 |             2.5044 |
| crossed  | danger    | stochastic_calibrated |          148 |           148 |         1.0000 |          4 | 0.5405 | -0.2001 |         0.4595 |       0.8649 |    2.1454 |   0.3824 |             2.5707 |

| station_key          | family   |   cases |   years |   plugin_available |   plugin_mae |   D2_available |   D2_mae |   stochastic_available |   stochastic_mae |
|:---------------------|:---------|--------:|--------:|-------------------:|-------------:|---------------:|---------:|-----------------------:|-----------------:|
| bc_published|08FF003 | calendar |      12 |       4 |                 12 |       0.0574 |             12 |   0.0343 |                     12 |           0.0085 |
| bc_published|08FF003 | crossed  |      72 |       4 |                 72 |       0.8331 |             72 |   0.4748 |                     72 |           0.5205 |
| bc_published|08JA017 | calendar |      24 |       4 |                 24 |       0.0140 |             24 |   0.0210 |                     24 |           0.0024 |
| bc_published|08JA017 | crossed  |      72 |       4 |                 72 |       0.2414 |             72 |   0.2434 |                     72 |           0.2026 |
| bc_published|08LF051 | calendar |      24 |       4 |                 24 |       0.0713 |             24 |   0.0644 |                     24 |           0.0727 |
| bc_published|08LF051 | crossed  |      72 |       4 |                 72 |       0.3829 |             72 |   0.2074 |                     72 |           0.2204 |
| bc_published|08MF040 | calendar |      24 |       4 |                 24 |       0.0049 |             24 |   0.0037 |                     24 |           0.0038 |
| bc_published|08MF040 | crossed  |      72 |       4 |                 72 |       0.6049 |             72 |   0.2978 |                     72 |           0.2652 |

Nechako作者水温资料已更新至2019—2024年。按公开起止日期冻结唯一可能覆盖2020—2023四个完整UTC年的河流候选；每个UTC日必须有96个唯一15分钟数值且标记为P或A。该候选四年中合格完整年为0，每年都有非有限记录，故未评分；其与已评价的BC站同一条河，不能作为独立气候确认。原始CC BY作者包和署名说明已包含在候选包中。

|   year |   calendar_days |   source_rows |   complete_days |   missing_days |   duplicate_rows |   off_grid_rows |   nonfinite_rows |   disallowed_flag_rows | qualified   |
|-------:|----------------:|--------------:|----------------:|---------------:|-----------------:|----------------:|-----------------:|-----------------------:|:------------|
|   2020 |             366 |         35136 |             341 |             25 |                0 |               0 |                1 |                   1918 | False       |
|   2021 |             365 |         35040 |             211 |            154 |                0 |               0 |             6523 |                  13982 | False       |
|   2022 |             365 |         35040 |             125 |            240 |                0 |               0 |            21021 |                  21889 | False       |
|   2023 |             365 |         35040 |             127 |            238 |                0 |               0 |            17076 |                  20129 | False       |

美国Poudre作者归档先按公开起止日期固定4站，随后核查2020—2024年的20个站年。每个站年都至少缺28个15分钟UTC时刻，且无完整PASS参考年，因此没有进行恢复评分。四站属于同一流域；作者称2019—2021未收集技术人员校准记录，不能视为独立气候或无误差参考。原始CC BY文件和署名已纳入候选包。

| site       |   year |   calendar_days |   source_rows |   complete_days |   missing_days |   duplicate_rows |   off_grid_rows |   nonfinite_rows |   disallowed_flag_rows | qualified   |   expected_quarter_hours |   missing_quarter_hour_timestamps |
|:-----------|-------:|----------------:|--------------:|----------------:|---------------:|-----------------:|----------------:|-----------------:|-----------------------:|:------------|-------------------------:|----------------------------------:|
| archery    |   2020 |             366 |         35108 |             290 |             76 |                0 |               0 |             4441 |                   3200 | False       |                    35136 |                                28 |
| archery    |   2021 |             365 |         23749 |             205 |            160 |                0 |               0 |             2835 |                   2135 | False       |                    35040 |                             11291 |
| archery    |   2022 |             365 |         21437 |             168 |            197 |                0 |               0 |             2289 |                     24 | False       |                    35040 |                             13603 |
| archery    |   2023 |             365 |         22960 |             168 |            197 |                0 |               0 |             1381 |                   1053 | False       |                    35040 |                             12080 |
| archery    |   2024 |             366 |         23708 |             207 |            159 |                0 |               0 |              830 |                    920 | False       |                    35136 |                             11428 |
| cottonwood |   2020 |             366 |         30639 |              11 |            355 |                0 |               0 |            11666 |                  10601 | False       |                    35136 |                              4497 |
| cottonwood |   2021 |             365 |             0 |               0 |            365 |                0 |               0 |                0 |                      0 | False       |                    35040 |                             35040 |
| cottonwood |   2022 |             365 |         19138 |             183 |            182 |                0 |               0 |              282 |                     22 | False       |                    35040 |                             15902 |
| cottonwood |   2023 |             365 |         23901 |             195 |            170 |                0 |               0 |              481 |                    466 | False       |                    35040 |                             11139 |
| cottonwood |   2024 |             366 |         23712 |             216 |            150 |                0 |               0 |              344 |                    438 | False       |                    35136 |                             11424 |
| riverbend  |   2020 |             366 |         35108 |             178 |            188 |                0 |               0 |             8852 |                   7992 | False       |                    35136 |                                28 |
| riverbend  |   2021 |             365 |         23757 |             227 |            138 |                0 |               0 |             1469 |                   1111 | False       |                    35040 |                             11283 |
| riverbend  |   2022 |             365 |         21436 |             190 |            175 |                0 |               0 |             1335 |                   1174 | False       |                    35040 |                             13604 |
| riverbend  |   2023 |             365 |         23044 |             188 |            177 |                0 |               0 |             1193 |                   1230 | False       |                    35040 |                             11996 |
| riverbend  |   2024 |             366 |         23703 |             210 |            156 |                0 |               0 |              148 |                    236 | False       |                    35136 |                             11433 |
| salyer     |   2020 |             366 |         35108 |             129 |            237 |                0 |               0 |             9622 |                   8005 | False       |                    35136 |                                28 |
| salyer     |   2021 |             365 |         23767 |             218 |            147 |                0 |               0 |             1507 |                   1144 | False       |                    35040 |                             11273 |
| salyer     |   2022 |             365 |         14770 |              88 |            277 |                0 |               0 |             4531 |                    804 | False       |                    35040 |                             20270 |
| salyer     |   2023 |             365 |         23902 |             200 |            165 |                0 |               0 |             1496 |                   1529 | False       |                    35040 |                             11138 |
| salyer     |   2024 |             366 |         23790 |             217 |            149 |                0 |               0 |              719 |                    770 | False       |                    35136 |                             11346 |

新斯科舍省固定四个河流站的旧版已核验工作簿与开放门户后，按报告时刻和有限数值检查完整性：两版本共有14个完整标签站年，其中12个所有数值在1e-6°C内容差一致，2站各有至少四年。全时段共有数值标签中1086个差异大于0.5°C，这是查看初次比对后追加的描述性阈值。两版本来自同一项目，逐点质量、估计处理及共同时间基准尚未确定，不能称为严格独立精度参考，也未进行模型评分。开放门户数据入包，旧工作簿条款未解决，保留本机。

| station_id   |   possible_complete_label_years_workbook |   possible_complete_label_years_portal |   common_complete_labels |   fully_equal_1e6 |   within_0p01 | four_or_more_equal_complete_label_years   |
|:-------------|-----------------------------------------:|---------------------------------------:|-------------------------:|------------------:|--------------:|:------------------------------------------|
| NS01DL0009   |                                        4 |                                      5 |                        4 |                 4 |             4 | True                                      |
| NS01ED9111   |                                        2 |                                      2 |                        1 |                 1 |             1 | False                                     |
| NS01EF0002   |                                        4 |                                      4 |                        3 |                 3 |             3 | False                                     |
| NS01FB0001   |                                        6 |                                      6 |                        6 |                 4 |             6 | True                                      |

在查看来源完整性和两版本一致性之后、查看模型误差之前，另行冻结新斯科舍探索性修订：两站、八个报告时刻完整站年，共144个受控缺口案例。源模型和源校准固定，每次只遮挡一个目标年，其余三个完整年用于本地训练。D2和随机重建的配对MAE分别为0.311和0.313°C；这是重复掩码，不是独立气候。逐案例算术检查通过，两个事后选择的隐藏值扰动探针通过；探针非穷尽。水温时区、估计值标记及逐点质量仍未知，NASA POWER采用地方太阳时，因此该结果不能称为严格独立参考、整档案前推或自然缺测验证。

| stratum   |   n_eligible |   n_common |   common_availability |   stations |   station_years |   D2_mae |   D2_coverage90 |   D2_width90 |   D2_interval_score90 |   D2_crps |   stochastic_mae |   stochastic_coverage90 |   stochastic_width90 |   stochastic_interval_score90 |   stochastic_crps |
|:----------|-------------:|-----------:|----------------------:|-----------:|----------------:|---------:|----------------:|-------------:|----------------------:|----------:|-----------------:|------------------------:|---------------------:|------------------------------:|------------------:|
| all       |          144 |        144 |                1.0000 |          2 |               8 |   0.3107 |          0.8819 |       0.9996 |                1.5717 |    0.2311 |           0.3129 |                  0.9306 |               1.2812 |                        1.7058 |            0.2250 |
| danger    |           76 |         76 |                1.0000 |          2 |               8 |   0.5385 |          0.8026 |       1.6862 |                2.5844 |    0.3970 |           0.5287 |                  0.8816 |               2.1667 |                        2.7882 |            0.3786 |

| stratum   |   n_eligible |   n_common |   common_availability |   stations |   station_years |   D2_mae |   D2_coverage90 |   D2_width90 |   D2_interval_score90 |   D2_crps |   stochastic_mae |   stochastic_coverage90 |   stochastic_width90 |   stochastic_interval_score90 |   stochastic_crps | axis       | level      |
|:----------|-------------:|-----------:|----------------------:|-----------:|----------------:|---------:|----------------:|-------------:|----------------------:|----------:|-----------------:|------------------------:|---------------------:|------------------------------:|------------------:|:-----------|:-----------|
| all       |           48 |         48 |                1.0000 |          2 |               8 |   0.2474 |          0.8958 |       0.7578 |                1.2723 |    0.1920 |           0.2314 |                  0.9375 |               1.0179 |                        1.3646 |            0.1645 | gap_length | 30         |
| all       |           48 |         48 |                1.0000 |          2 |               8 |   0.2973 |          0.9375 |       1.0506 |                1.2795 |    0.2176 |           0.3193 |                  0.9583 |               1.3430 |                        1.5957 |            0.2256 | gap_length | 60         |
| all       |           48 |         48 |                1.0000 |          2 |               8 |   0.3873 |          0.8125 |       1.1904 |                2.1634 |    0.2838 |           0.3881 |                  0.8958 |               1.4827 |                        2.1572 |            0.2849 | gap_length | 90         |
| all       |           72 |         72 |                1.0000 |          1 |               4 |   0.4003 |          0.8194 |       1.1429 |                1.9778 |    0.2950 |           0.3935 |                  0.9306 |               1.5075 |                        1.8730 |            0.2827 | station_id | NS01DL0009 |
| all       |           72 |         72 |                1.0000 |          1 |               4 |   0.2210 |          0.9444 |       0.8564 |                1.1657 |    0.1673 |           0.2324 |                  0.9306 |               1.0548 |                        1.5386 |            0.1673 | station_id | NS01FB0001 |

在查看原探索结果后，将报告日边界前后移动一小时：八个站年跨年边界小时在两版本均可用且一致；保留完全相同的144个掩码，重新拟合本地阶段并固定源模型、源校准和NASA气温。参考H30最大改变0.0023°C，单案例D2点预测最大改变0.094°C。此试验不确定真实时区、不能覆盖所有时区偏差，也不验证传感器质量或气候独立性。

| stratum   |   n_eligible |   n_common |   common_availability |   stations |   station_years |   D2_mae |   D2_coverage90 |   D2_width90 |   D2_interval_score90 |   D2_crps |   stochastic_mae |   stochastic_coverage90 |   stochastic_width90 |   stochastic_interval_score90 |   stochastic_crps |   shift_hours |
|:----------|-------------:|-----------:|----------------------:|-----------:|----------------:|---------:|----------------:|-------------:|----------------------:|----------:|-----------------:|------------------------:|---------------------:|------------------------------:|------------------:|--------------:|
| all       |          144 |        144 |                1.0000 |          2 |               8 |   0.3102 |          0.8889 |       0.9998 |                1.5547 |    0.2290 |           0.3128 |                  0.9236 |               1.2830 |                        1.7037 |            0.2249 |            -1 |
| danger    |           76 |         76 |                1.0000 |          2 |               8 |   0.5390 |          0.8158 |       1.6858 |                2.5473 |    0.3939 |           0.5284 |                  0.8684 |               2.1699 |                        2.7852 |            0.3784 |            -1 |
| all       |          144 |        144 |                1.0000 |          2 |               8 |   0.3107 |          0.8819 |       0.9996 |                1.5717 |    0.2311 |           0.3129 |                  0.9306 |               1.2812 |                        1.7058 |            0.2250 |             0 |
| danger    |           76 |         76 |                1.0000 |          2 |               8 |   0.5385 |          0.8026 |       1.6862 |                2.5844 |    0.3970 |           0.5287 |                  0.8816 |               2.1667 |                        2.7882 |            0.3786 |             0 |
| all       |          144 |        144 |                1.0000 |          2 |               8 |   0.3145 |          0.8681 |       0.9980 |                1.5718 |    0.2317 |           0.3134 |                  0.9306 |               1.2777 |                        1.7307 |            0.2258 |             1 |
| danger    |           76 |         76 |                1.0000 |          2 |               8 |   0.5441 |          0.7895 |       1.6850 |                2.5802 |    0.3973 |           0.5296 |                  0.8816 |               2.1605 |                        2.8346 |            0.3800 |             1 |

## 复现与交付

执行 `make review` 使用已有数据和拟合缓存更新修订分析、图表、稿件及测试。完整从原始数据和模型重建仍需要各来源缓存、许可和原始拟合；不可把缓存模式称为已验证的干净环境端到端重建。源样本含LUBW观测，相关再使用和分发条件须按提供方条款处理；作者与永久存档信息仍待提供。

五张主图位于 [paper/wrr_tr/figures/simple_research](../paper/wrr_tr/figures/simple_research/)。主稿和补充材料源文件位于 [paper/wrr_tr](../paper/wrr_tr/)。各提供方来源与当前记录条款位于 [来源清单](../results/wrr_review_response_20261027/source_rights/provider_source_inventory.csv)；LUBW咨询和编辑资料访问说明为未发送草稿。作者、机构、资助和存档字段由用户填写。

本轮结果支持问题与观测发现的价值，仍不支持通用安全发布、全情景趋势校准或独立气候迁移。不能以软件测试通过替代这些科学结论。
