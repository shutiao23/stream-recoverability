# 独立资料的直接执行

运行 `make review-independent`。步骤依次是写入本地研究计划、取得九站原生观测与质量序列、计算完整原生日均值、确认参考资格，再评价有合格真值的案例。已有原生文件按可读名称复用，不做注册附件校验。

```bash
python scripts/472_review_completion_prereg.py
python scripts/496_review_completion_independent_acquisition.py --acquire
python scripts/497_review_completion_independent_cases.py --prepare-cases --resume
python scripts/495_review_completion_independent_analysis.py \
  --cases results/wrr_review_completion_20261024/independent_study/acquired/cases.parquet \
  --output results/wrr_review_completion_20261024/independent_study/evaluation
```

站点和测量设置分别是 `independent_study/greater_wellington/cohort_roster.csv` 与 `independent_study/acquisition_plan.json`。实际原生观测、请求时间和日均值保存在 `independent_study/acquired/`。若经过机构证据确认后修改测量质量设置，可用 `496 --acquire --refresh` 从缓存原生观测重算日值；不需要重新取得同样的数据。

九站实际取得日值资料，但按原质量设置接受代码600，没有可用的合格完整热年。实际返回的历史质量码没有被默认为600。`observed_qualification.csv` 保留九站分母及其原生样本、质量码和完整年计数；`evaluation/primary_endpoints.json` 明确为没有可评价案例，不以空集合声称成功。

该检验未预注册。OSF记录可以作为真实元数据填写，不是运行前置条件。三管理区不等于充分的独立气候样本；若要报告新区域预测精度，仍需确认机构质量码与参考标准的兼容性或取得符合标准的参照资料。

## 额外批准观测的主要事实检验

`make review-independent` 另调用 `scripts/525_external_observed_records.py`，使用 `results/additional_usgs_observed/cohort_metadata.csv` 的十个候选。原四个完整参照年的要求没有降低，十站均不足以提供外部恢复精度试验。观测主张则由原始批准日值直接检验：四站有非空完整年纪录，其中三站、九个不完整站年有完整批准且非估计的30日窗口超过全部批准完整年H30。仅额外质控删值不能制造这些反证；原始参考年保留全部批准有限值。每个窗口的30个批准数值、实际缺失或未批准日数与参照年列表均保存于 `robust_record_witnesses.csv`。

额外参照只有1—3年，不与原20/96长期站分母合并，不用于发生率、唯一最热年或气候迁移保证。该检验未预注册，没有拟合或评价插补器；这是原先主要观测主张的额外佐证。
