# 本轮实验数据指南

数据根目录为`results/wrr_process_experiments_20261029/`。本轮重用保存案例、来源角色、年度预测和逐日观测；旧审稿及旧科学结果保留。数据是本地研究与审阅材料，清单不另行赋予来源数据或模型的再分发权。

`dataset_catalog.csv`由`python scripts/972_experiment_data_catalog.py`读取当前文件生成，包含SHA256、字节数、实际表行数/列数、统计粒度、声明键及其实际唯一性、分析角色、来源、权重与支持条件。`data_dictionary.csv`逐字段记录dtype、单位、定义和缺失/非有限数。`declared`键来自生成器的数据设计；`candidate_not_declared`只表示候选标识组合在当前表上唯一，不能据此创造新的科学统计单位。没有可靠定义的单位写`documented_feature`，元数据写`not_applicable`。

表字段的`missing_count`按表行计，不递归扫描list内每条轨迹；NPZ的缺失/非有限计数按数组元素计。对象列的`nonfinite_count=not_applicable`不是“全部有限”的证明，轨迹可用性以专门的native20和source-pool检查为准。

目录本身、字典及其报告排除自哈希；最终`validation.json`也排除，避免循环依赖。目录的`inventory_generated_not_scientific_validation`状态只说明清单已生成。最终验收必须看实际产生的本轮`validation.json`，不能从单个计算报告或日志代推。

## 先区分这些单位

| 名称 | 正确定义 | 不应混用 |
|---|---|---|
| 来源校准案例 | 来源站年×缺口设计/实现/重建器的案例，带原来源角色正权 | 不是目标评分案例，也不是2,370个独立站年 |
| 目标站年 | 固定的27站年，来自6站、2连接群组 | 729个三层评分行不是729个独立观测 |
| `native20` | 原来以20为数组规模调用随机生成器得到的历史20条轨迹；已另行复现 | 不是以500为规模调用后截取的前20条 |
| `nested20/100/500` | 同一seed的500条生成结果的三个前缀 | 同seed不保证nested20与native20相同；跨seed不是新站点 |
| `replicate` | 整档案掩码重复0–19；改变某档案的缺测设计 | 不是桥接seed、选年seed或独立气候 |
| `seed` / `draw_seed` | C的桥接流0/1/2，或B的选年流0–199；见具体文件 | 不是来源角色的群组bootstrap重复权重 |
| `count` | C的桥接路径预算20/100/500 | 公共CRPS的256点是七分位数近似积分，不能叫256条新桥接轨迹 |
| B的精确随机期望 | 先每档案内对所有同数可行集合均匀平均平方误差，再按所选跨档案权重平均并开根号 | 不是把5,758个集合直接等权混成一池，也不是`E[RMSE]` |
| 观测不完整站年 | 实际观测一年一行，无人工mask重复 | 不与试验站年×掩码重复合并作独立样本 |

所有温度误差及年度分位数以°C计；斜率误差为°C/十年，MSE及`cross_term`为(°C/十年)²。覆盖率和比例的CSV数值通常为0–1，`difference_pp`才是百分点。水气年度斜率单位为°C水/°C气。日期mask采用零起点`start:length`，长度单位天。

## C：来源校准与目标评分分开

来源：`scripts/968_process_source_calibration.py`，原`cases/before_2010/seed_00.parquet`、原桥接修复、原保存角色及`whole_archive/classical_calibration.json`。`source_calibration/plan.json`保留具体输入哈希、角色、正权群组和规则。

| 文件组 | grain / key | 单位与来源、分析角色 | 权重、缺失与支持条件 |
|---|---|---|---|
| `source_role_cases.csv`；`source_union_cases.parquet` | 角色表：`calibration_region×case_id`；去重并集：`case_id`。原案例身份也保留network/station/year/family/realization/policy/mask | 校准输入。`calibration_weight`为整数重复权重；普通特征未知单位不猜测 | 2,370案例来自19站、102唯一站年；正权来源年≤2009且与相应目标群组分离。不能把来源目标地区名当数据提供地区。 |
| `frozen_source_reference.parquet`；`frozen_target_manifest.csv` | 来源`case_id`，2,370行；目标`station_key×year`，27行 | 975当前冻结重放的最小原native来源参考和固定D2/native目标参考；`stochastic_h30_draws`为°C的原生20条年度H30数组 | 是本轮内容快照，不是新增来源案例/目标站年，也不补造更早的来源证明。 |
| `historical_source_fallbacks.csv`；`full/source_reestimated_offsets.csv` | 前者`calibration_region×cell`；后者`region×seed×count×cell`，288行 | 来源七分位偏移及相对历史原生20偏移变化，°C；不是目标残差校准 | 单元至少50个有限正权案例才局部校准，否则使用整个正权来源池。门槛按未乘重复权重的案例数，随后按原multiplicity拟合。 |
| `full/source_frozen_manifest.csv`；`source_frozen_inputs/*.npz` | manifest为`case_id`；NPZ为站点×年度数组包，`case_position`联接observed/mean行，`residual_index`联接`residual_*` | 复原并冻结的日输入；温度/残差为°C。数组形状见字典，不虚构一个表行数 | 复原原留出年和pre-2010训练条件；隐藏目标日保留NaN。原生20轨迹检查确认原路径数值后，后续预算共用这些日输入。 |
| `full/source_native20_checks.csv`；`full/source_nested_draws.parquet`；`full/source_nested_quantiles.csv` | 分别`case_id`（2,370行）、`case_id×seed`（7,110行）、`case_id×seed×count`（21,330行） | 历史复现与新路径/七分位数；轨迹与分位数为°C；不作为独立评分样本 | `native20`只在相应参考位置提供，不给其他seed伪造原生轨迹。分位数进入原来源角色加权校准。 |
| `full/source_pool_availability.csv`；`source_unavailable_cases.csv` | `case_id×seed` | 来源支持/不可用台账；布尔或计数 | 当前7,110记录可用性不变；不可用台账为有表头的零行。零行表示本集合无此情形，不证明所有来源均有支持。 |
| `fixed_target_cases.csv`；`full/target_native20_checks.csv`；`full/target_nested_draws.parquet` | 固定`station_key×year`（27行）；路径加`seed`（81行） | 目标索引、历史参考和新路径。truth仅作评分；bound为观测窗口下界 | 不参与来源偏移拟合；2目标连接群组，不能按路径数扩大样本量。 |
| `full/target_historical_reference.csv` | `station_key×year×method`，54行 | 历史原生20经典法与固定D2，七分位数、绝对误差、CRPS等为°C | 同27目标等案例评分；不能将它当nested20新校准层。 |
| `full/target_three_layer_cases.csv`；`target_three_layer_summary.csv` | 案例表`station_key×year×seed×count×layer`，729行；汇总加`region×reconstructor`，54行 | 三层：`uncalibrated`已做观测下界投影但未加偏移；`fixed_old_offset`固定旧来源偏移；`reestimated_source_offset`本seed/预算重估来源偏移 | 同目标、同seed、同预算跨层配对。汇总为层内等案例；整27例须按案例数18/9加权合并，不能将两地区各给一半权重。 |
| `full/target_budget_case_deltas.csv`；`target_budget_tail_summary.csv` | 同目标×seed×layer×comparison；汇总加region/reconstructor | 同流`nested20→100/500`端点变化、宽度和覆盖计数；端点°C | 是条件于固定来源/目标的预算敏感性；不是历史native20到500的单因素因果分解。 |
| `full/target_source_offset_stage_contrasts.csv` | `station_key×year×seed×count×metric`，1,701行 | 同目标轨迹上重估偏移减旧偏移；`source_offset_change`单位由metric决定 | 分位数/温度评分为°C，覆盖变化为0/1。不能给整列盲贴统一温度单位。 |

`full/station_parts/`保存各来源站的路径、manifest、原生20核对和输入哈希分片；它们是全量表的可追踪组成，不能重复汇总。`pilot/`只是试运行，不替代full来源校准。最终计算记录在`full/execution.json`；首次全重构另有`full_reconstruction_execution.json`，不能把后续resume运行时间称为首次重构耗时。

冻结目标数组另在`frozen_target_inputs/*.npz`，每包是一个目标站年的日数组；`observed`、`mean`和`residual`为°C。来源`full/source_frozen_inputs/*.npz`可含同一站年多个掩码案例，`residual_index`是索引，不是温度。`frozen_replay_dependency_manifest.json`列141项实际依赖，加清单本身共142文件；`replay_receipt.json`是当前冻结参数重放收据。默认`python scripts/975_replay_source_calibration.py`不依赖原日面板、原case cache、joblib或968原配置，但不因此成为原始数据预处理/拟合或全量D2的重建。

`calibration_leakage_probe.json`来自976的年度校准/评分接口反事实实验，改变评价标签或来源标签，并在临时输出中检查应变/不变。它及相关日志、收据不是新增实测案例，不能并入目标729行或来源2,370行计算样本数；其边界不涵盖原始隐藏日修改后的上游日模型重训。

当前有真实来源重校准且排序敏感，不能沿用“尚未执行来源校准检查”的旧总括。也不能反过来宣称经典法普遍胜出或500条已收敛。只有两个目标群组，七分位数之间/外侧仍使用共同的插值与正态间距尾部近似。

## B：保存预测上的选年与误差分解

来源：`scripts/969_time_gap_sensitivity.py`、原逐档案`design.json`/`annual_predictions.parquet`、唯一参考年H30、上轮保留年集合。选择CDF/Sxx只读年份和可用性；温度在集合固定后用于评分。探索性规则与平局次序在`time_gap_exploratory_plan.json`。

| 文件组 | grain / key | 单位、角色 | 权重、缺失与支持条件 |
|---|---|---|---|
| `time_archive_accounting.csv/.parquet`；`time_availability_burden.csv` | 档案键`station_key×replicate×independence_group`，820行；burden为cohort | 原分母及支持台账，年份计数/年份串、全保留斜率误差 | 807原共同；其中2例零遮挡；805实际遮挡；468可选择。13例暖季仅3/4年，不悄然纳入配对。 |
| `time_all_feasible_subsets.parquet` | 档案键加`subset_id`，5,758行 | 每种可行集合、均匀概率、选中标记及E/S/R；Sxx单位decade²、CDF距离无量纲 | 每档案内部概率和为1，包含全部固定完整年且新增k相同。不同档案可行集合数不同，不能直接跨表行等权。 |
| `time_fixed_geometry_selections.parquet` | 档案键加scheme | 暖季、旧一次随机、旧仅新增年均衡、CDF、Sxx、全保留；每档案固定预测评分 | 同数规则仍不可评价不足五年档案；全保留数量不同，年集合真值误差为0是目标定义。 |
| `time_exact_random_expectations.parquet` | 档案键加scheme，807行 | 先在档案内均匀平均MSE及交叉项；不是先平均误差再平方 | 先在档案内平均，再跨档案按指定权重汇总。`sqrt(E[MSE])`的完整定义见主计划。 |
| `time_random_selection_draws.parquet`；`time_random_seed_summary.csv`；`time_random_selection_variation.csv` | 档案×draw_seed（161,400行）；队列×权重×draw_seed；队列×权重 | 200个预列种子的选集变异；平均RMSE与平均MSE开根号分别保存 | 每seed是一套完整档案选年实现。分位数是选择变异，不是bootstrap置信区间或200个独立气候。 |
| `time_sensitivity_summary.csv`；`time_sensitivity_paired_cluster.csv` | scope×weighting×scheme；配对表再加field | 斜率RMSE为°C/十年；MSE/交叉项为(°C/十年)²。配对表虽field名为estimate_mse，最终对比及区间是开根号后的RMSE差 | equal_archive为主，equal_station/equal_group为敏感性；17群组重采样携带所有配对档案行，10,000次。不能称等效性检验。 |
| `time_secondary_leave_group_out.csv` | removed_group×scheme | 新控制结果出现后加入的固定预测影响诊断；RMSE差 | 删除某群组再汇总，不重训、不另选最有利seed，不伪装成计划前确认。 |

误差定义为：`S`是选定年集合上的完整年斜率减全记录目标；`R`是同集合估计斜率减完整年斜率；`E=S+R`。每个集合与汇总保留有符号`cross_term=2 mean(SR)`。均方项不是相互独立的物理/因果份额。

本轮较强同数CDF/Sxx控制有改善；“no advantage”只能描述旧随机及弱heuristic结果，不能代表当前所有同数策略。有限记录目标与年份位置仍未得到独立因果识别。

## 真实缺口与同日重叠

来源：既有`eligible_station_years.csv`、canonical `archive_daily.parquet`及两类保存的forward mask。`gap_overlap_station_year_cases.csv`键为`source×replicate×station_key×year`；`gap_overlap_summary.csv`为`source×period`；`gap_overlap_by_replicate.csv`再加replicate。

年度最长连续缺测统一以天计，试验段按零起点日历位置并集计算；不把每档案段长中位数冒充年度最长值。主时期2010–2025，1981–2025观测仅为补充。观测每不完整站年等权，试验每不完整站年×掩码重复等权；后者不是新独立观测。

`shared_year_fraction_all_incomplete`保留旧同年口径，分母是全部不完整站年行。新`shared_year_fraction_peer_evaluable`和`same_day_overlap_fraction_peer_evaluable`只使用另有同群可评价队列站的站年；排除数单列`n_no_evaluable_peer_excluded`。`shared_missing_day_fraction`为共同缺测站日/有peer的缺测站日，不是全部日历日概率。此处peer只在41站前推队列及各来源可评价年份内定义，不包括所有实际邻站或模型实际使用供体。

## A与年度水气关系

来源：`scripts/audit_region_water_experiments.py`对保存区域案例和留一年来源站年独立复算；`regenerated/`为本轮生成器复现，`baseline_snapshot/`为18份上轮文件及其哈希，不能与新表相加。

| 文件组 | grain / key | 单位、角色 | 权重、缺失与支持条件 |
|---|---|---|---|
| `independent_regional_standardization.csv`；`regenerated/region_standardized.csv` | matching×region×weighting×method，24行 | 地区标准化年度覆盖/误差汇总；覆盖存fraction、误差°C | raw_common_support为保留案例等权；min_count共同cell质量∝min(两地区计数)；equal_cell各共同cell等权。 |
| `regenerated/region_common_cells.csv`、`region_balance_*.csv`、`region_support_loss.csv` | matching×cell；matching×weighting×field；matching×region | 单元频数、连续/分类平衡、保留与损失分母 | 共同单元频率被统一不意味着训练年数或所有连续量已平衡；unknown单位的均值/矩须联接field原定义。 |
| `regional_leave_group_out.csv` | omitted_group×matching，20行 | 删除群组后的覆盖差，difference_pp为百分点 | 每次重新选共同支持、重新定权，比较总体也随之改变。 |
| `water_air_denominator_audit.csv`；`regenerated/water_air_complete_years.csv` | station_key×year，1,106行 | 站年去重/有限性台账；H30为°C | 原25,135掩码行去重。当前非有限排除为0，不把mask_rows当独立观测权重。 |
| `regenerated/water_air_station_period_moments.csv`、`water_air_summary.csv`、`water_air_paired_changes.csv` | 站点×时期；region×period×centering×bootstrap_unit；时期变化再加contrast | 年度关联斜率°C水/°C气、相关无量纲、残差尺度°C；矩字段未知单位不猜测 | 主估计唯一站年等权。bootstrap携带同一群组/站点两个时期；FOEN仅两群组，离散组成极少，不能证明等效。 |
| `water_air_weight_and_leave_group_sensitivity.csv` | region×analysis×omitted_group，14行；基线omitted为空是“不适用” | 站内年度关系的权重/删群敏感性 | equal_station_total_weight改变统计目标；删主要FOEN群组可只剩一站。年度关系不能推断日残差/热峰稳定。 |
| `independent_training_year_balance_checks.csv`；`water_air_direct_observation_bootstrap_checks.csv`；`regional_input_field_denominators.csv` | 实现对比的matching/weighting；region×period×centering×unit×metric；region×field | 数值一致性与分母核对；metric/field决定单位 | 接近零表示两种算术实现一致，不表示真实构成已平衡、效应为零或仪器无误差。 |

## 联接、空表与复现顺序

1. 先读各包plan及角色/分母表；不要从最小误差表反推入选集合。
2. C用`case_id`联接来源角色、冻结数组manifest及分位数；用目标`station_key×year`再加seed/count/layer配对评分。来源和目标表不混成训练池。
3. B用档案键联接分母、选集与评分；`subset_id`只在该档案内有意义。保留两份CSV/Parquet同名编码的等价版本，不能重复算样本。
4. 缺口日期表按source/replicate分别分组；观察1981–2025和2010–2025汇总有嵌套关系，不能把两行相加。
5. 不把零行`source_unavailable_cases.csv`读成缺文件，不把baseline `omitted_group`空值当缺少研究信息。一般非有限值与分类不适用值需分开处理；看catalog的missing/nonfinite列及各包支持协议。
6. 先运行968/969及区域审计，再重建972目录。970生成论文图表；971/974执行独立算术审计，975/977提供冻结输入重放，976执行校准接口反事实探针。最终状态由`validation.json`记录，清单不替代验收。

本轮响应与科学解释见[逐项账本](EXPERIMENT_RESPONSE_ZH.md)。当前主文和SI已同步新实验。作者、合法访问及永久保存由用户自行处理，不作为本轮科学实验目标的阻塞项。

## 选年实验的紧凑冻结输入

`time_frozen_replay/annual_inputs.parquet`包含820个档案的10,860个年度行，键为`station_key/replicate/independence_group/year`。`truth_h30`、`d2_point_h30`和`point_h30`单位均为°C；D2点值仅对实际缺口年保存，最终point在完整年使用观测H30。missing/warm_keep与两项original_*_evaluable是布尔状态，保留原五年规则。

运行`python scripts/977_replay_time_support.py`可在不读取原case cache的条件下重算5,758个可行集合、两个calendar选择器、807个精确条件期望及805/807/468的63项加权摘要。仅10个声明文件的临时副本已实际重放。这个闭包不重放200个随机实现、群组置信区间或实际同日缺口；它们分别由本地完整969与独立974结果覆盖。当前冻结不认证历史来源。

CRPS积分精度另存`source_calibration/target_crps_grid_cases.csv`及`target_crps_grid_summary.csv`。`grid`是256/1024/4096个概率积分点，`count`是桥接路径预算，两者不混用；基线行seed/count=-1表示不适用，历史native20的含义由method给出。`crps`单位为°C；`pooled_27`与分地区汇总是相同案例的不同汇总，不能叠加。
