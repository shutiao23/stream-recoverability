# 全国源域资料与 H30 分析

此项执行第 6.1 步，属于已打开 USGS 源域的探索性应用。与新西兰独立检验分开：本轮全国下载的任何 USGS 站都不能再当作从未打开的独立站点。NZ 河温仍必须等公开登记和匹配附件，500–503 不调用其观测接口。

名单在水温数值分析之前由既有全国元数据固定：4,285 个 USGS 河流及渠系目录站，每站仅选一个主日均序列；1,273 个可能有至少十五个完整支持年或元数据范围未知的站进入核查，3,012 个跨度短的站仍列入分母及排除原因。最长支持跨度、默认子位置及 ID 的排序不使用误差；不合并不同传感器。日期分析窗为 1981–2025，额外取得 1980 和 2026 年初仅用于边界及历史输入。

原 490 纯日期阶段的原始缓存不改动，停止与移交的实际记录在 `national_availability/phase_transition_to_source_values.json`。后续 500 将审批/日期和全国 H30 所需数值合并到一次源域请求；保留旧缓存出处，不再把这一阶段称为纯日期。官方现代接口支持每页 50,000 条；旧端点若恰好返回 10,000 条会继续翻页，防止误截断。已知 Retry-After 在新控制器中继续有效，401/403 或参数/投影错误停止新增请求。

500 保留报告日期、未审批、歧义重复和真正无日期记录的区别。数值门沿用已有源域 ingest：摄氏、批准值、哨兵和固定范围检查，任何被拒站都保留在总体分母。先按共同的原生日期与取得范围筛选，再质控；不因旧缓存的更早或更晚记录改变新请求的质控范围。歧义重复不平均为单个传感器值。批准的 Estimated 保留并另计，未知或错误记录不填成恢复成功。

501 只为至少四个完整历史年、十五个支持年且存在不完整年的模型候选准备 NASA POWER T2M。采用与源输入一致的日 LST，按 0.5°×0.625° 原生气象单元及太阳时带复用；无同网格重复请求。已有 82 个同单元缓存对在公共日期完全一致。它是网格气温输入，不是站点实测气象上限。缺气温和其他预测器按不可用或既定回退报告，不伪造值。

502 固定年度分布回归、P2、失败分类器和经典区间偏移，只按既定配方拟合目标站其他年份的局地日模型。年份定义明确为日历年，包括可能出现的南半球 USGS 地点；保留真实坐标。元数据支持年份可显式传入，避免截取分析窗后把原本有效的边界年错误排除。每轮河网水温/气温面板单独保存，输入变化使病例缓存失效。所有完整年仍用原观测，不被年度校正覆盖。

503 比较完整年、全年 90%/75%、固定 May–September 90% 和保留估计等规则。资格年数和实际可计算 H30 的年数分开；观测日算法仍要求 30 日窗口至少有 80% 有效日。原年度估计保持主要结果；已知完整窗口下界投影仅作另列敏感性，没有下界时不丢掉有效估计，也不把下界当作缺失点估计。另列随机 MI、MOVE 和右删失工作似然。

趋势报告站点、区域、同站同时间跨度、空间块自助、BH 与同步时间置换/循环位移。保守大流域合并不是误差独立性的证明；条件插补范围也不是已验证的 95% 置信覆盖。真实缺测年没有真值，不能给出实际覆盖率。全国结果是该监测网络的敏感性，不等于全部美国河流的总体气候参数。

观测纪录证明需要至少十五个完整参考年，并从日值逐项核验全部参考 H30 及连续三十日见证；不需要插补，也不识别唯一真正最热年。未完成或空响应站保留为未知资格，报告相应计数上下界。只有全部要求都有证据时才关闭全国完成关口。

完整执行顺序：

```bash
python scripts/500_review_completion_national_inputs.py --workers 2
python scripts/501_review_completion_national_forcing.py --workers 2
python scripts/502_review_completion_national_application.py --workers 24 --resume
python scripts/503_review_completion_national_meaning.py --bootstrap 2000
```

小批检查必须加 `--partial` 并使用单独的 `smoke_*` 目录，不能填入全国完成标志。当前实际进度以 `national_meaning/progress.json`、逐站结果和完整 `status.json` 为准；没有完整资料时不把此说明当作结果。

本次采集与后续分析由 `508_review_completion_national_finish.py --watch-pid <实际采集 PID>` 接续执行并已结束。它只在既有采集结束且完整执行标志成立后，顺序运行 501、502、503；各阶段日志和错误保留在 `finish_progress.json`，不会启动第二个河温采集器。完成执行与全部资格已解析分别报告。

空响应诊断已取得 v1 官方 schema/queryables，并显式投影正确字段。已知有值的正对照 USGS 01010000 成功返回对应序列的日值；06800500 的同类查询得到服务器“Long running query has been cancelled”，因此该错误反映服务查询失败。这个站的当前 v1 元数据仅列连续父序列，另一次旧 DV 接口请求返回零序列。原始响应和时间戳保存在 `api_version_probes/`，仍不足以证明全部历史日值不存在；不确定资格继续进入上下界分母。

## 空序列的进一步核查

同一套 v1 站号/参数/统计量查询在已知有值的 01010000 返回记录，在 06800500 和 06805000 返回零记录。06805500 虽返回日均记录，但其 UUID 为旧的 `c45d86478ae94abb9bb8d7d171f5bc5c`、子位置为 QW Monitor old，目录范围 2002-10 至 2007-07，仅有四个完整日历年；它不同于固定的 2007 年后主序列，不能替换为十五年样本，也不合并传感器。核查记录在 `api_version_probes/station_native_daily_summary.json`，保留历史可用性的未知状态。

## 空间覆盖与热年频率

`configs/wrr_review_national_supplement_20261024.json` 固定新增描述量。空间覆盖报告 1° 经纬网格占据数及 HUC2 站点分布，不将网格数量解释成流域面积；未解析资格和缺坐标带来明确的网格数上界。热年阈值在每站使用 1981–2010 年至少五个完整批准年的 H30 第 90 百分位，所有方法共用该阈值，估计值与未来年份均不参与阈值拟合。参照不足保持不可用。分别输出全期、参照期和 2011–2025 年频率，并列出同站同时间跨度与共同年份对照。由连续完整观测窗口确认的热年另给频率下界，不依赖插补；其余不完整年的事件分类是模型/统计量敏感性，不能测得自然缺口的命中率。

新增输出为 `spatial_coverage*.csv`、`hot_year_reference_thresholds.csv`、`hot_year_frequency_station.csv`、`hot_year_frequency_network_region.csv` 与 `hot_year_frequency_same_roster_span.csv`。小批实际面板只用于实现核对，不作为全国结果。

## 全国取得面板的已核验结果

固定 4,285 个目录站、1,273 个候选的请求已全部执行。数值面板包含 933 站；另有 340 个候选无可解析年度面板，资格保持未知。下表给出未知候选均不合格/均合格两端的资格计数，不是全部美国河流的总体率。

| rule                     |   eligible_lower |   eligible_upper_allowing_unresolved |
|:-------------------------|-----------------:|-------------------------------------:|
| MaySep90_15              |              522 |                                  862 |
| annual75_15              |              525 |                                  865 |
| annual90_15              |              462 |                                  802 |
| complete15               |              100 |                                  440 |
| retained_MOVE1           |              521 |                                  861 |
| retained_bound_projected |              521 |                                  861 |
| retained_individual      |              496 |                                  836 |
| retained_raw             |              521 |                                  861 |
| retained_stochastic      |              519 |                                  859 |

趋势单位为 °C/十年。各规则的站点和年度支持不同，网络中位数不能解释为同站因果效应。同站同跨度、BH、同步置换/循环位移、区域和空间块结果另存 CSV。插补范围是条件模型敏感性，无自然缺口真值核验覆盖。

| rule                     |   n_stations |   median_slope |   n_positive_p005 |   n_positive_BH |   n_blocks |   block_lower |   block_upper |   huc2 |
|:-------------------------|-------------:|---------------:|------------------:|----------------:|-----------:|--------------:|--------------:|-------:|
| MaySep90_15              |          522 |         0.2136 |          118.0000 |         56.0000 |         14 |        0.1547 |        0.3037 |    nan |
| annual75_15              |          525 |         0.2453 |          133.0000 |         60.0000 |         14 |        0.1759 |        0.3394 |    nan |
| annual90_15              |          462 |         0.2393 |          112.0000 |         54.0000 |         14 |        0.1690 |        0.3314 |    nan |
| complete15               |          100 |         0.2448 |           22.0000 |          8.0000 |         11 |        0.0451 |        0.3613 |    nan |
| retained_MOVE1           |          521 |         0.2206 |          130.0000 |         58.0000 |         13 |        0.1507 |        0.2773 |    nan |
| retained_bound_projected |          521 |         0.2183 |          131.0000 |         63.0000 |         13 |        0.1486 |        0.2956 |    nan |
| retained_individual      |          496 |         0.2199 |          125.0000 |         61.0000 |         13 |        0.1409 |        0.3098 |    nan |
| retained_raw             |          521 |         0.2183 |          131.0000 |         63.0000 |         13 |        0.1453 |        0.2956 |    nan |
| retained_stochastic      |          519 |         0.2067 |          131.0000 |         60.0000 |         13 |        0.1419 |        0.2970 |    nan |

完整年规则与保留估计的网络趋势中位数分别为 0.2448/0.2183 °C/十年；共同 100 站、相同时间跨度的趋势变化中位数为 0.0026 °C/十年。两种处理的同步循环位移场检验 p 值分别为 0.000500/0.000500。站数增加或不同名单的中位数差不能当作已验证的趋势偏差修复。

| rule                     |   observed_positive_significant |   year_permutation_p |   synchronized_circular_shift_p |   draws |
|:-------------------------|--------------------------------:|---------------------:|--------------------------------:|--------:|
| MaySep90_15              |                             118 |               0.0005 |                          0.0005 |    2000 |
| annual75_15              |                             133 |               0.0005 |                          0.0005 |    2000 |
| annual90_15              |                             112 |               0.0005 |                          0.0005 |    2000 |
| complete15               |                              22 |               0.0005 |                          0.0005 |    2000 |
| retained_MOVE1           |                             130 |               0.0005 |                          0.0005 |    2000 |
| retained_bound_projected |                             131 |               0.0005 |                          0.0005 |    2000 |
| retained_individual      |                             125 |               0.0005 |                          0.0005 |    2000 |
| retained_raw             |                             131 |               0.0005 |                          0.0005 |    2000 |
| retained_stochastic      |                             131 |               0.0005 |                          0.0005 |    2000 |

1° 网格占据数描述监测站地理范围，不是流域面积；未知资格进入网格数上界。

| rule                     |   n_eligible_stations |   n_with_coordinates |   n_without_coordinates |   occupied_cells_lower |   occupied_cells_upper_allowing_unresolved |   n_huc2_with_eligible_stations |   n_unresolved_candidates |   grid_degrees | scope                                                                                    |
|:-------------------------|----------------------:|---------------------:|------------------------:|-----------------------:|-------------------------------------------:|--------------------------------:|--------------------------:|---------------:|:-----------------------------------------------------------------------------------------|
| MaySep90_15              |                   522 |                  522 |                       0 |                    205 |                                        283 |                              19 |                       340 |              1 | geographical station-grid occupancy; not watershed area or population representativeness |
| annual75_15              |                   525 |                  525 |                       0 |                    205 |                                        282 |                              19 |                       340 |              1 | geographical station-grid occupancy; not watershed area or population representativeness |
| annual90_15              |                   462 |                  462 |                       0 |                    179 |                                        260 |                              19 |                       340 |              1 | geographical station-grid occupancy; not watershed area or population representativeness |
| complete15               |                   100 |                  100 |                       0 |                     49 |                                        161 |                              13 |                       340 |              1 | geographical station-grid occupancy; not watershed area or population representativeness |
| retained_MOVE1           |                   521 |                  521 |                       0 |                    207 |                                        284 |                              18 |                       340 |              1 | geographical station-grid occupancy; not watershed area or population representativeness |
| retained_bound_projected |                   521 |                  521 |                       0 |                    207 |                                        284 |                              18 |                       340 |              1 | geographical station-grid occupancy; not watershed area or population representativeness |
| retained_individual      |                   496 |                  496 |                       0 |                    196 |                                        277 |                              18 |                       340 |              1 | geographical station-grid occupancy; not watershed area or population representativeness |
| retained_raw             |                   521 |                  521 |                       0 |                    207 |                                        284 |                              18 |                       340 |              1 | geographical station-grid occupancy; not watershed area or population representativeness |
| retained_stochastic      |                   519 |                  519 |                       0 |                    206 |                                        283 |                              18 |                       340 |              1 | geographical station-grid occupancy; not watershed area or population representativeness |

各方法共用 1981–2010 年至少五个完整批准年 H30 的站点第 90 百分位阈值。参照不足不填零；观测窗口热年频率下界不依赖插补。

| rule                     | period    | huc2   |   n_eligible_stations |   n_with_reference_and_values |   n_statistic_years |   n_incomplete_statistic_years |   n_hot |   pooled_frequency |   n_supported_years |   observed_window_frequency_lower_bound |   station_equal_frequency | scope                                                                                                                                                          |
|:-------------------------|:----------|:-------|----------------------:|------------------------------:|--------------------:|-------------------------------:|--------:|-------------------:|--------------------:|----------------------------------------:|--------------------------:|:---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| MaySep90_15              | all       | all    |                   522 |                           177 |                4921 |                           2274 |    1029 |             0.2091 |                5859 |                                  0.1796 |                    0.2180 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| MaySep90_15              | recent    | all    |                   522 |                           174 |                2276 |                            978 |     614 |             0.2698 |                2509 |                                  0.2491 |                    0.2708 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| MaySep90_15              | reference | all    |                   522 |                           177 |                2645 |                           1296 |     415 |             0.1569 |                3350 |                                  0.1275 |                    0.1630 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| annual75_15              | all       | all    |                   525 |                           176 |                5073 |                           2430 |    1030 |             0.2030 |                5758 |                                  0.1792 |                    0.2129 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| annual75_15              | recent    | all    |                   525 |                           169 |                2257 |                            951 |     603 |             0.2672 |                2434 |                                  0.2510 |                    0.2669 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| annual75_15              | reference | all    |                   525 |                           176 |                2816 |                           1479 |     427 |             0.1516 |                3324 |                                  0.1267 |                    0.1575 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| annual90_15              | all       | all    |                   462 |                           171 |                4646 |                           2035 |     978 |             0.2105 |                5637 |                                  0.1799 |                    0.2189 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| annual90_15              | recent    | all    |                   462 |                           168 |                2185 |                            880 |     587 |             0.2686 |                2419 |                                  0.2518 |                    0.2680 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| annual90_15              | reference | all    |                   462 |                           171 |                2461 |                           1155 |     391 |             0.1589 |                3218 |                                  0.1259 |                    0.1619 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| complete15               | all       | all    |                   100 |                            90 |                1688 |                              0 |     331 |             0.1961 |                3101 |                                  0.1728 |                    0.1965 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| complete15               | recent    | all    |                   100 |                            90 |                 894 |                              0 |     228 |             0.2550 |                1348 |                                  0.2441 |                    0.2391 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| complete15               | reference | all    |                   100 |                            90 |                 794 |                              0 |     103 |             0.1297 |                1753 |                                  0.1181 |                    0.1347 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| retained_MOVE1           | all       | all    |                   521 |                           188 |                5661 |                           2934 |    1176 |             0.2077 |                6125 |                                  0.1775 |                    0.2170 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| retained_MOVE1           | recent    | all    |                   521 |                           179 |                2422 |                           1109 |     651 |             0.2688 |                2579 |                                  0.2458 |                    0.2704 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| retained_MOVE1           | reference | all    |                   521 |                           188 |                3239 |                           1825 |     525 |             0.1621 |                3546 |                                  0.1277 |                    0.1693 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| retained_bound_projected | all       | all    |                   521 |                           188 |                5664 |                           2937 |    1166 |             0.2059 |                6125 |                                  0.1775 |                    0.2158 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| retained_bound_projected | recent    | all    |                   521 |                           179 |                2422 |                           1109 |     651 |             0.2688 |                2579 |                                  0.2458 |                    0.2704 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| retained_bound_projected | reference | all    |                   521 |                           188 |                3242 |                           1828 |     515 |             0.1589 |                3546 |                                  0.1277 |                    0.1676 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| retained_individual      | all       | all    |                   496 |                           185 |                5420 |                           2717 |    1116 |             0.2059 |                6045 |                                  0.1783 |                    0.2158 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| retained_individual      | recent    | all    |                   496 |                           177 |                2367 |                           1061 |     640 |             0.2704 |                2552 |                                  0.2473 |                    0.2719 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| retained_individual      | reference | all    |                   496 |                           185 |                3053 |                           1656 |     476 |             0.1559 |                3493 |                                  0.1280 |                    0.1630 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| retained_raw             | all       | all    |                   521 |                           188 |                5664 |                           2937 |    1166 |             0.2059 |                6125 |                                  0.1775 |                    0.2158 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| retained_raw             | recent    | all    |                   521 |                           179 |                2422 |                           1109 |     651 |             0.2688 |                2579 |                                  0.2458 |                    0.2704 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| retained_raw             | reference | all    |                   521 |                           188 |                3242 |                           1828 |     515 |             0.1589 |                3546 |                                  0.1277 |                    0.1676 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| retained_stochastic      | all       | all    |                   519 |                           187 |                5643 |                           2921 |    1158 |             0.2052 |                6080 |                                  0.1771 |                    0.2142 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| retained_stochastic      | recent    | all    |                   519 |                           178 |                2416 |                           1103 |     644 |             0.2666 |                2564 |                                  0.2457 |                    0.2654 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |
| retained_stochastic      | reference | all    |                   519 |                           187 |                3227 |                           1818 |     514 |             0.1593 |                3516 |                                  0.1271 |                    0.1675 | descriptive frequencies on each rule's available annual values; incomplete-year classifications are model/statistic dependent, not verified natural-gap events |

原始连续观测窗口在 43 站、70 个不完整站年超过完整年纪录。见证及完整参照已回查原生日值；这只反证该报告序列的完整年纪录归属，不识别唯一物理最热年。

