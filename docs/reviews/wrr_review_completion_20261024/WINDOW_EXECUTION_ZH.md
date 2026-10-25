# H7 目标特定重算

此项扩展原计划第 23 项的固定预测规格曲线。原生目标是“七日连续日均水温窗口均值的年最大值”，不是日最高水温的 7DADM。

重新生成气候峰窗及受控缺口位置、训练期七日极值和异常、峰窗残差、历史缺口重放、条件路径的七日函数量、MOVE 年度增补及 AR1 桥抽样。然后重拟合年度分布模型、功能去偏、失败分类器及互斥组校准，按同样的 20 个整数种子和 27 个外区执行。日历病例要求至少 30 个可见日的原入组下限保持一致。

`target_windows/h7/full/seed_*.parquet` 保留真实 h7 字段，也保留计算得到的次要 H30 真值。内部拟合视图先删除真正的 H30 字段，再将 h7 字段显式改为旧引擎字段名；这些视图放在 `cases/h7_spec_refit/`，不能把其 h30 列解释成三十日量。外部导出的原生预测重新使用 h7 名称。

全部 20 个种子的原生资料、540 个留区拟合、评分及趋势实验已完成，并通过各区域原生目标和点估计的身份核验。最终完成以 `target_windows/h7/full/completion.json`、逐种子的分析摘要及身份审计为准。

已经完成的原始输入核验包含 16 个不同机构–补全层的病例：七日真值、真正三十日真值、七日点估计、训练期七日均值/标准差/90 分位、气候峰值、峰窗遮挡及七日观测下界逐项独立重算一致。另将默认 H30 分支重算的 240 个病例、201 个共同字段与原源域及既有随机桥修复核对，一致到 1e-11 容差。

历史 H30 注册判定保持原样。H7 的重新校准不构成新的盲检验，也不等于把每个深度模型、容差与阈值组合全部重训。

复现：

```bash
python scripts/506_review_completion_window_refits.py --workers 48 --resume --with-trends
python scripts/509_review_completion_window_evidence.py
```

`511_review_completion_window_finish.py` 可等待已有生成进程，随后顺序完成拟合、分析与证据核查；它不会启动第二个生成器。日志与失败阶段保存在 `scratch/review_completion_h7_full_*.log` 和 `target_windows/h7/full/finish_progress.json`。

## 已核验结果

| family   | estimator                        |   n_seeds |   mae_median |   crps_median |   twcrps_median |   coverage90_median |
|:---------|:---------------------------------|----------:|-------------:|--------------:|----------------:|--------------------:|
| calendar | distribution_regression          |        20 |       0.4940 |        0.3650 |          0.0645 |              0.8735 |
| calendar | functional_debias                |        20 |       0.5223 |      nan      |        nan      |            nan      |
| calendar | plug_in                          |        20 |       0.6378 |      nan      |        nan      |            nan      |
| calendar | stochastic_regression_calibrated |        20 |       0.5158 |        0.3803 |          0.0676 |              0.8584 |
| crossed  | distribution_regression          |        20 |       0.3481 |        0.2566 |          0.0459 |              0.8919 |
| crossed  | functional_debias                |        20 |       0.3753 |      nan      |        nan      |            nan      |
| crossed  | plug_in                          |        20 |       0.4233 |      nan      |        nan      |            nan      |
| crossed  | stochastic_regression_calibrated |        20 |       0.3596 |        0.2654 |          0.0475 |              0.8932 |

| family   | reference                        | endpoint                 |   passing |   n_seeds |   median_gain |
|:---------|:---------------------------------|:-------------------------|----------:|----------:|--------------:|
| calendar | MOVE1_H30                        | danger_MAE_gain_positive |        20 |        20 |        0.6118 |
| calendar | MOVE1_annual                     | danger_MAE_gain_positive |        20 |        20 |        0.2113 |
| calendar | MOVE1_warm                       | danger_MAE_gain_positive |        20 |        20 |        0.1188 |
| calendar | air2stream3                      | danger_MAE_gain_positive |        20 |        20 |        0.2885 |
| calendar | air_state_calibrated             | danger_MAE_gain_positive |        19 |        20 |        0.0233 |
| calendar | air_state_simulation             | danger_MAE_gain_positive |        18 |        20 |        0.0242 |
| calendar | functional_debias                | danger_MAE_gain_positive |        20 |        20 |        0.0522 |
| calendar | lookup_debias                    | danger_MAE_gain_positive |        20 |        20 |        0.2297 |
| calendar | observed_days                    | danger_MAE_gain_positive |        20 |        20 |        0.8593 |
| calendar | plug_in                          | danger_MAE_gain_positive |        20 |        20 |        0.2293 |
| calendar | stochastic_regression            | danger_MAE_gain_positive |        20 |        20 |        0.0436 |
| calendar | stochastic_regression_calibrated | danger_MAE_gain_positive |        20 |        20 |        0.0485 |
| calendar | triage_hybrid                    | danger_MAE_gain_positive |         0 |        20 |       -0.0000 |
| crossed  | MOVE1_H30                        | danger_MAE_gain_positive |        20 |        20 |        0.7286 |
| crossed  | MOVE1_annual                     | danger_MAE_gain_positive |        20 |        20 |        0.2379 |
| crossed  | MOVE1_warm                       | danger_MAE_gain_positive |        20 |        20 |        0.2289 |
| crossed  | air2stream3                      | danger_MAE_gain_positive |        20 |        20 |        0.3643 |
| crossed  | air_state_calibrated             | danger_MAE_gain_positive |        20 |        20 |        0.0791 |
| crossed  | air_state_simulation             | danger_MAE_gain_positive |        20 |        20 |        0.0775 |
| crossed  | functional_debias                | danger_MAE_gain_positive |        20 |        20 |        0.0712 |
| crossed  | lookup_debias                    | danger_MAE_gain_positive |        20 |        20 |        0.1948 |
| crossed  | observed_days                    | danger_MAE_gain_positive |        20 |        20 |        0.6415 |
| crossed  | plug_in                          | danger_MAE_gain_positive |        20 |        20 |        0.1769 |
| crossed  | stochastic_regression            | danger_MAE_gain_positive |        20 |        20 |        0.0278 |
| crossed  | stochastic_regression_calibrated | danger_MAE_gain_positive |        20 |        20 |        0.0294 |
| crossed  | triage_hybrid                    | danger_MAE_gain_positive |         0 |        20 |       -0.0000 |
| calendar | air_state_calibrated             | crps_gain_positive       |        12 |        20 |        0.0011 |
| calendar | air_state_calibrated             | twcrps_gain_positive     |        20 |        20 |        0.0028 |
| calendar | air_state_simulation             | crps_gain_positive       |        12 |        20 |        0.0026 |
| calendar | air_state_simulation             | twcrps_gain_positive     |        20 |        20 |        0.0032 |
| calendar | stochastic_regression            | crps_gain_positive       |        20 |        20 |        0.0164 |
| calendar | stochastic_regression            | twcrps_gain_positive     |        18 |        20 |        0.0026 |
| calendar | stochastic_regression_calibrated | crps_gain_positive       |        20 |        20 |        0.0154 |
| calendar | stochastic_regression_calibrated | twcrps_gain_positive     |        20 |        20 |        0.0034 |
| crossed  | air_state_calibrated             | crps_gain_positive       |        20 |        20 |        0.0167 |
| crossed  | air_state_calibrated             | twcrps_gain_positive     |        20 |        20 |        0.0043 |
| crossed  | air_state_simulation             | crps_gain_positive       |        20 |        20 |        0.0169 |
| crossed  | air_state_simulation             | twcrps_gain_positive     |        20 |        20 |        0.0043 |
| crossed  | stochastic_regression            | crps_gain_positive       |        20 |        20 |        0.0067 |
| crossed  | stochastic_regression            | twcrps_gain_positive     |        19 |        20 |        0.0012 |
| crossed  | stochastic_regression_calibrated | crps_gain_positive       |        20 |        20 |        0.0076 |
| crossed  | stochastic_regression_calibrated | twcrps_gain_positive     |        20 |        20 |        0.0016 |
