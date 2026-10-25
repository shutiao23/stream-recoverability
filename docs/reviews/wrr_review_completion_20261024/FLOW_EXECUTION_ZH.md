# 低流量示范的经典对照

## 低流量的同病例经典对照

已打开示范的 255 站、8,999 个完整气候年、134,925 个病例全部重现；原始 21 个特征/结果字段在 1e-10 绝对容差内一致，未覆盖旧输出。新分支使用同一随机流和缺口，额外随机桥另设种子；历史 D2 预测固定。

MOVE.1 与单供体 Ridge 使用同一最佳供体、相同其他年份的对数流量异常；历史 Ridge 和随机桥使用最多三供体。随机桥为二十次 Gaussian AR1 路径，使用其他年份的样本内残差；没有独立区间校正，不将其当作已校准分布。无供体的年份保持经典方法不可用。

| family   | scope        | estimator                       |   n_eligible |   n_valid |   availability |   bias_log |   geometric_bias_percent |   mae_log |   failure_rate |
|:---------|:-------------|:--------------------------------|-------------:|----------:|---------------:|-----------:|-------------------------:|----------:|---------------:|
| calendar | donor_danger | historical_multidonor_log_Ridge |        14394 |     14394 |         1.0000 |     0.0419 |                   4.2768 |    0.1418 |         0.2812 |
| calendar | donor_danger | historical_D2                   |        14394 |     14394 |         1.0000 |     0.0442 |                   4.5165 |    0.1336 |         0.2578 |
| calendar | donor_danger | single_donor_log_Ridge          |        14394 |     14394 |         1.0000 |     0.0426 |                   4.3535 |    0.1510 |         0.2992 |
| calendar | donor_danger | MOVE1_log_anomaly               |        14394 |     14394 |         1.0000 |    -0.0188 |                  -1.8659 |    0.1668 |         0.3258 |
| calendar | donor_danger | stochastic_log_AR1_median       |        14394 |     14394 |         1.0000 |    -0.0940 |                  -8.9748 |    0.1766 |         0.3606 |
| calendar | donor_danger | observed_days                   |        14394 |     14394 |         1.0000 |     0.3500 |                  41.9113 |    0.3500 |         0.5077 |
| crossed  | donor_danger | historical_multidonor_log_Ridge |        33609 |     33609 |         1.0000 |     0.0101 |                   1.0113 |    0.0842 |         0.1638 |
| crossed  | donor_danger | historical_D2                   |        33609 |     33609 |         1.0000 |     0.0326 |                   3.3131 |    0.0745 |         0.1394 |
| crossed  | donor_danger | single_donor_log_Ridge          |        33609 |     33609 |         1.0000 |     0.0082 |                   0.8265 |    0.0896 |         0.1766 |
| crossed  | donor_danger | MOVE1_log_anomaly               |        33609 |     33609 |         1.0000 |    -0.0247 |                  -2.4416 |    0.1062 |         0.2060 |
| crossed  | donor_danger | stochastic_log_AR1_median       |        33609 |     33609 |         1.0000 |    -0.0529 |                  -5.1528 |    0.1038 |         0.2118 |
| crossed  | donor_danger | observed_days                   |        33609 |     33609 |         1.0000 |     0.1039 |                  10.9462 |    0.1039 |         0.2049 |

| family   | scope        | left                      | right                  |   n_common |   left_mae_log |   right_mae_log |   n_sites |   site_fraction_left_not_worse |
|:---------|:-------------|:--------------------------|:-----------------------|-----------:|---------------:|----------------:|----------:|-------------------------------:|
| calendar | donor_danger | MOVE1_log_anomaly         | single_donor_log_Ridge |      14394 |         0.1668 |          0.1510 |       210 |                         0.2952 |
| calendar | donor_danger | MOVE1_log_anomaly         | historical_D2          |      14394 |         0.1668 |          0.1336 |       210 |                         0.2667 |
| calendar | donor_danger | stochastic_log_AR1_median | historical_D2          |      14394 |         0.1766 |          0.1336 |       210 |                         0.2857 |
| crossed  | donor_danger | MOVE1_log_anomaly         | single_donor_log_Ridge |      33609 |         0.1062 |          0.0896 |       210 |                         0.1905 |
| crossed  | donor_danger | MOVE1_log_anomaly         | historical_D2          |      33609 |         0.1062 |          0.0745 |       210 |                         0.1476 |
| crossed  | donor_danger | stochastic_log_AR1_median | historical_D2          |      33609 |         0.1038 |          0.0745 |       210 |                         0.2952 |

MOVE.1 相对相同信息的单供体 Ridge，在两种缺口下都未降低危险层 MAE；随机桥亦没有优于历史 D2。保方差或抽路径并不自动校正低流量函数量。对数误差均值的 exp(error)-1 为几何比偏差；先对 log(Q) 回归再取指数不是原始流量单位的条件均值，不能据此证明与 H30 相同的普遍偏差方向。此项仅一次已打开示范，不是二十次稳定性或独立迁移。

流量阈值沿用旧示范：log(7Q) 跨年标准差中位数的一半，约 0.1654；不得与河温 0.5°C 容差混用。逐规则留存和风险保存在 `flow_comparators/rules.csv`，无输出不计为成功。

