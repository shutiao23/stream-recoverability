# 免登录备用水温资料资格核查

**后续更新（2026-10-27）：**本文件记述当时的资料状态。此后已从文中同一CC BY作者归档读取24站PRT半小时温度，按固定单传感器和质量标志进行日历年资格检查；没有获得独立数字温度计备份，且没有站满足四个严格完整参照年。新结果见 `results/wrr_review_response_20261027/external_neon/`；不得把本文件的历史“未打开温度表”描述当作当前状态。

本轮取得了七个 USGS 河流测站的双通道原始记录，按读取温度前锁定的规则核查了 25 个候选通道对站年，合格参考年为零。NEON 的研究者公开归档提供了 24 个河流站的 PRT 文件目录，但尚未取得独立数字温度计的配对参考。真实缺测确认和新的独立确认仍未完成。

继续检索后，澳大利亚 Water Data Online 提供了可免登录取得的日均与原始点记录。已核查 148 站日均响应、869 个原始站年，80 个预定候选站年通过质量与采样支持检查。它们的独立组件数仍不足以支持已冻结的正式确认，当时 F2 专属测试的状态记录为未打开，其他模型随后对同一批站年的使用见招募记录更新，详见 [新参考资料招募记录](NEW_REFERENCE_RECRUITMENT_ZH.md)。这批记录提供人工缺口参考候选，尚未提供独立备份下的真实缺测真值。

新增 [USGS 参考接入](USGS_REFERENCE_INTAKE_ZH.md) 仍处于元数据阶段。旧缓存排除后剩余 543 个候选，河网获取受到实际限流，定时控制进程遵守服务给出的等待时间；没有读取新的温度观测或打开新的 H30 误差。

官方 [数字热敏温度计 RELEASE-2026](https://data.neonscience.org/data-products/DP1.20054.001/RELEASE-2026) 提供另一类仪器测得的温度观测；同位置与误差一致性仍须逐案核实。当前作者归档的特定深度产品只含 BLWA、FLNT、TOMB，与其 24 个 PRT 站目录不重叠。进一步核查相关论文的官方出版页面仍返回 HTTP 403，未取得补充温度文件。当前没有把这些访问限制记成零合格备份案例，也未绕过访问限制。

另对 DFO 三个仅因历史支持不足而排除的参考对核对了全站、所有同位置记录器的最早部署时间。即使允许跨记录器使用单个完整历史年，目标年前可能完整的站年上限也只有 0、0、1；因此零合格结果不是只认同一传感器序列号造成的。[部署时间上限核对](../../../results/wrr_submission_ready/followup_20261021/natural_backup/station_history_time_bounds.csv) 不拼接或补造历史，也没有改变原资格规则。

随后对原 180 个配对候选涉及的全部 14 个点、44 个点—目标年做了更宽的覆盖上限检查。即使允许任意同点传感器提供完整日，或者进一步忽略同名站的坐标差异及传感器一致性要求，目标年前最多仍只有两个完整年，没有一个达到三个。[跨记录器覆盖上限](../../../results/wrr_submission_ready/followup_20261021/natural_backup/history_coverage_bound/summary.json) 只说明日覆盖的最乐观可能性，未生成可用的合并温度序列，也未计算新的恢复误差。

NEON 作者归档另有 BLWA、FLNT、TOMB 三个大河站的定深温度链资料。现已检查两类产品的 24 个变量、位置、说明和问题日志元数据文件。三站的水质瞬时表均未列出水温测量字段，`fDOMTempQF` 仍只是温度校正标志。定深温度的分钟值与半小时均值来自同一温度链；位置表中的单探头和温度链名称共享浅层位置代码，测量表没有可区分它们的设备序列号，尚不能识别同时存在的两路独立备份。[三站逐表核查](../../../results/wrr_submission_ready/followup_20261021/neon_large_river_metadata/summary.json) 保持真实缺测资格数量未知，温度测量表未打开。问题日志将 BARC／CRAM 的历史深度更正列为在 RELEASE-2023 提供；这不证明本三站的传感器对应关系已经核实，也不能把旧通知直接当作本归档仍全部失效的依据。[定深温度产品](https://data.neonscience.org/data-products/DP1.20264.001)

## USGS 原始记录与资格

全国公开目录快照包含 6,555 路瞬时水温序列，包含河流以外的站型。先核查标注主／备用及水质仪的两站，再扩展到仪器名为 YSI、EXO、HOBO 的重叠序列；按元数据排除明确不同深度、不同取水位置、缺少潜在历史支持和运河站。该检索不能当作全部备用传感器的穷尽清单。[USGS 序列元数据接口](https://api.waterdata.usgs.gov/ogcapi/v1/collections/time-series-metadata/items?f=json&parameter_code=00010&computation_identifier=Instantaneous&limit=10000)

| 测站 | 候选年 | 主要限制 |
|---|---|---|
| 15008000 Salmon River near Hyder | 2024–2025 | 备用全为 provisional；2024 主记录完整且历史不足，2025 主记录缺少年末支撑 |
| 12056500 North Fork Skokomish | 2025 | 水质仪温度全为 provisional，未形成经批准的备用参考 |
| 01193500 Salmon River near East Hampton | 2017–2018 | 缺口覆盖与完整历史不足；2018 主记录本身完整 |
| 02054750 Roanoke River at Route 117 | 2019–2020 | 未覆盖全部主记录缺口，缺少三个完整历史年；2020 还有边界问题 |
| 05420500 Mississippi River at Clinton | 2016–2021 | 重叠日的传感器差异未通过预设一致性检验 |
| 05464420 Cedar River at Palo | 2018–2025 | 早期主通道后来不再提供完整记录，缺口覆盖、年度边界与历史支持不足 |
| 05578100 Salt Creek near Farmer City | 2022–2025 | 缺口年未通过一致性检验；2023 主记录完整且历史不足 |

延续原 DFO 资格要求：UTC 日均至少覆盖 20 个不同小时且跨度至少 20 小时；至少 90 个可见重叠日，日差绝对均值不超过 0.25°C、95 分位不超过 0.5°C；目标年前至少三个完全观测的主记录年，主记录年首尾有效，备用覆盖全部真实缺额。USGS 主分析另要求原始观测已获批准，并排除估计、结冰影响、设备故障等标记。provisional 观测的存在和数量保留在质量表中，未作为符合这一规则的参考。[USGS 状态与限定标记定义](https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/queryables?f=json)

接近资格的案例也保留。例如 Mississippi River 的 2019 年有 208 个主记录日缺额、备用覆盖全年，具备足够历史和年度边界，但 157 个可见重叠日的绝对均差为 1.002°C、95 分位为 1.857°C。Salt Creek 的 2024 年有 17 个缺额，绝对均差为 0.220°C，95 分位仍为 0.815°C。两者均依原规则排除，没有在看见这些差异后修改阈值或计算重建胜负。

Salt Creek 旧接口的整段及年度请求曾返回 503，随后通过公开 OGC 接口取得 16 页、536,116 条原始观测。审批与限定标记在转为统一表格时保留。已完成七站全部获取，访问失败没有计作零观测。DST 重复小时按各时间戳明确的时区缩写转为 UTC。

主、备用通道名称本身不足以证明独立硬件及相同水体位置。七站中，01193500 和 05578100 的站号已出现于打开过的旧研究面板；其余站的流域连接及区域事件独立性尚未核实。这批资格核查没有转为新独立确认样本。

## NEON 公开归档与其他来源

用户确认没有 NEON API 令牌。官方月度数据目录的匿名请求返回 403；产品与站点元数据、方法文档可公开读取。PRT 与数字温度计采用不同仪器，但仍需核查具体位置、深度、干涸标记和同步记录。该访问状态没有被解释为零个合格站年。[PRT 产品](https://data.neonscience.org/data-products/DP1.20053.001)、[数字温度计产品](https://data.neonscience.org/data-products/DP1.20054.001)、[官方接口认证说明](https://data.neonscience.org/data-api/authentication/)

可免登录读取的研究者归档为 *Ecosystem metabolism estimates from the National Ecological Observatory Network stream and river sites*，许可 CC BY 4.0。通过公开 ZIP 字节范围读取其目录、变量说明、位置和问题日志，未打开温度测量表。归档包含 24 站 PRT；没有数字温度计子归档，所核查的水质变量表也没有水温测量字段。水质表中的 `fDOMTempQF` 是温度校正标记，不能用作第二路温度。[公开归档](https://doi.org/10.6084/m9.figshare.28074452.v1)

数字温度计产品在 RELEASE 2025 中新发布；这也限制了从较早研究归档取得它的可能性。[NEON 发布说明](https://www.neonscience.org/data-samples/data-management/data-revisions-releases/release-2025)

Boulder 的官方监测 SOP 详细描述了主、备用探头及补齐步骤，但说明小时主数据需另行索取。本轮仅取得 SOP，没有取得双传感器原始导出，也没有发送请求。[提供方 SOP，第 20–27 页](https://watershed.center/wp-content/uploads/2023/08/2020_0908_WQ_Monitoring_SOP-002_COB.pdf)

另一个引用 NEON 数字温度计的研究在 Dryad 发布了目录和说明。目录包含实验数据压缩包、README，并列出现场水温分析脚本；API 下载返回 401，公开网页下载链接返回 403，文件内容未取得，不能据目录认定已获得连续备用温度。[Dryad 归档](https://doi.org/10.5061/dryad.gtht76j16)

## 三处大河站与备用历史

后续又核查了 NEON 的三个大河站 BLWA、FLNT、TOMB，共取得 24 个变量、位置及说明文件。水质表没有实测水温字段，深度温度表未提供可区分独立设备的键；同链的一分钟／半小时结果与不同深度不能直接作为两套仪器。浅层位置表的不同名称和位置编号，也不证明同时部署且相互独立。测量表未打开，合格真实缺测数保持未知。[三站模式核查](../../../results/wrr_submission_ready/followup_20261021/neon_large_river_metadata/summary.json) 及其来源绑定保留了这些范围限制。

DFO 的原 180 个配对站年还做了覆盖上限检查，涉及全部 14 个候选点、44 个点—目标年。先允许任一传感器提供完整日，再允许同点传感器的日内互补小时合并；更宽松地忽略同名站的坐标差异及一致性后，两种上限中的完整既往历史最多仍为两年。此处仅计有效采样覆盖，不生成合并温度或新的 H30 误差，不能据此放宽原三年要求。[逐点历史上限](../../../results/wrr_submission_ready/followup_20261021/natural_backup/history_coverage_bound/summary.json)

## NorWeST 与 EcoDrought 的追加核查

[NorWeST 官方页面](https://research.fs.usda.gov/rmrs/projects/norwest)提供观测日汇总入口，但本次对页面所列 29 个 “All Days Daily Summary” 链接逐一发出的 HEAD 请求，均被重定向到研究部门首页并返回 HTML，没有验证或取得温度压缩包。公开档案目录与元数据又指向项目页面，不能把目录存在算作已下载数据。可取得的观测点图层只有位置、年份和来源等七个字段，没有日温度真值；模拟情景也未用作观测参考。

[官方处理说明](https://research.fs.usda.gov/sites/default/files/2023-04/rmrs-norwest_dataprocessingprocedures.pdf)要求的八月覆盖不等于完整年度参考。日表的 `Nobs` 是记录数量，不能证明至少 20 个不同小时或 20 小时跨度；已按日均贡献的记录还可能没有该数量。即使以后恢复下载，也必须核查原始采样、时区、连续年度和独立设备出处，不能沿用目录规模当作合格站年数。

[EcoDrought 公开元数据](https://data.usgs.gov/datacatalog/metadata/USGS.61dca9a7d34ed7929400c02e.xml)描述 34 站，记录范围为 2018-09-06 至 2021-09-14。即使期间所有采样完整，该档案自身在目标年前最多提供 2019、2020 两个完整历史年。ScienceBase 的公开条目请求和文件入口请求本次返回 403；这不证明必须登录或底层记录不存在。原始文件清单和测量数据尚未取得，不能核实同位置独立备份。现场独立温度计的访问时点核对也不等于连续备份，温度推导的干湿标签不等于独立现场观测。[官方数据目录](https://catalog.data.gov/dataset/stream-temperature-in-the-donner-und-blitzen-basin-southeastern-oregon-2018-2021)

[追加来源保管记录](../../../results/wrr_submission_ready/followup_20261021/additional_public_source_scope/source_custody.json)、[逐下载入口响应](../../../results/wrr_submission_ready/followup_20261021/additional_public_source_scope/download_header_probes.csv) 和 [范围汇总](../../../results/wrr_submission_ready/followup_20261021/additional_public_source_scope/summary.json) 保留请求方法、实际时间、状态和响应类型。`make wrr-additional-source-scope` 从保留响应复现；仅在明确需要新版本时用 `python scripts/423_wrr_additional_source_scope.py --acquire` 更新元数据和 HEAD 探测，不请求温度测量表。

当前暂未排除的 155 个 USGS 候选与 AU 已合格参考的 33 个保守水系块加 1 个未定位站，即使全部独立合格，合计上限也只有 189 个单位。它低于现行错误预算下一阈值、全准入、零失败且忽略训练时，校准与测试合计最低 208 个独立单位。这个[必要数量筛查](../../../results/wrr_submission_ready/followup_20261021/reference_pool_feasibility/summary.json)只针对现有保留／合格名册，不包含 984 个未核实 AU 候选或其他未招募来源，不是最终招募量和联合功效结论。

## 可复核结果与复现

结果位于 [公开来源核查目录](../../../results/wrr_submission_ready/followup_20261021/public_backup_search/)。其中保留两次元数据预锁、逐站年全部失败条件、通道审批数量、旧面板站号重叠、公开归档目录及来源核查结果。原始导出与接口页面保存在本机忽略目录，不随代码重复提交。

运行 `make wrr-public-backup-metadata` 获取缺失的公开元数据及归档目录，随后运行 `make wrr-public-backup` 获取并核查候选记录。已有快照与锁保持原版本；供应方后来修订的记录可能需要另立数据版本。

这一轮没有修改预测器、阈值、原 H1–H3 或缺测资格门槛，也没有启用有成本补调。现有模型比较与论文定位仍以此前结果为准；新增资料核查提供了可追溯的排除依据。
