# Literature notes

核验日期：2026-08-15。`references.bib` 共收录 24 条，仅保留与当前研究问题、方法或数据来源直接相关且能核对作者、题名、年份及 DOI/URL 的记录。以下是写作与实验设计备忘，不是本项目结果陈述。

## 河流水温缺失与气温/流量重建

| BibTeX key | 本研究中的用途 | 使用边界 |
|---|---|---|
| `li2017streamairimputation` | 直接支持“配对气温—水温 + 空间邻站”用于河流水温缺失段重建的研究动机。 | 对象为美国东南部溪流和日最高温；空间结构、气候与金沙江不同，不能直接移用其参数或性能结论。 |
| `bal2023streamtemperature` | 支持以气温和可选流量进行日尺度概率水温重建，并明确传播不确定性。 | 只在两条温带河流上展示；贝叶斯分解结构与本项目模型不同，适合作为方法参照而非性能基准。 |
| `johnson2021datagap` | 支持使用连续块状缺失而非仅随机点缺失，并在重建后检查年度热信号。 | 关注年度均值、振幅和相位等汇总量；其站点和缺口阈值不应外推为金沙江通用规则。 |
| `mee2014guanyinyan` | 官方确认观音岩为金沙江中游最后一级、具周调节性能、距攀枝花市约 27 km，并记录 2014 年蓄水阶段。 | 用于工程位置与运行背景，不单独证明 P3 温度变化的因果性。 |
| `cdt2026guanyinyan` / `nea2016powerreport` | 核实首台机组 2014-12-20 投产、2015 年三台投产及 2016 年五台全部运行。 | 企业/行业时间线与观测转折一致；仍以“regulation-consistent”措辞。 |
| `usgs1973buford` | USGS 站点说明给出 02334430 位于 Buford Dam 下游 1,200 ft（366 m）。 | 历史站点位置依据；当前元数据名称也独立核对。 |
| `usace2017buford` | USACE 说明水电机组从水库近底层释放冷水，并描述分层与下游水质。 | 支持冷水下泄机制，不把单站协方差当成完整热量平衡。 |

## 时间序列插补模型与 benchmark

| BibTeX key | 本研究中的用途 | 使用边界 |
|---|---|---|
| `cao2018brits` | 循环网络类确定性插补基线。 | 原文数据域并非河流水文；不直接给出概率区间。 |
| `du2023saits` | 自注意力确定性插补基线。 | 原文主要使用人工缺失设置；必须在本项目相同掩码、切分和可用协变量条件下比较。 |
| `tashiro2021csdi` | 扩散式概率插补基线，并为分布预测和 CRPS 比较提供模型背景。 | 采样成本较高；通用环境/医疗数据上的表现不能替代金沙江数据上的实验。 |
| `cini2022grin` | 当站点关系图可可靠定义时，作为图时空插补基线。 | 对图结构和跨站同步观测有依赖；站点少或拓扑定义不稳时不宜强行使用。 |
| `du2024tsibench` | 用于设计统一的缺失率、缺失形态、算法和数据切分比较框架。 | 这是 arXiv 预印本；ICLR 2025 的 OpenReview 记录为撤回稿，只按预印本引用，不表述为已接收论文。 |
| `toye2025realworldbenchmark` | 提醒 benchmark 应覆盖更贴近真实机制的缺失，而不只做独立随机删除。 | 测试对象为健康传感器时间序列，不能据此推断河流水温方法排序。 |

## 水文缺输入与可恢复性

| BibTeX key | 本研究中的用途 | 使用边界 |
|---|---|---|
| `gauch2025missinginputs` | 支持把“部分驱动变量不可用时仍能预测”作为水文模型的独立稳健性问题，并用于组织缺输入情景。 | 目标是缺气象输入下的流量预测，不是缺失水温真值重建；其稳健性定义不能直接等同于本项目的可恢复性。题名中的 `w___` 是原题名，不是录入错误。 |
| `jeung2026informationquality` | 为“信息数量、信息质量与水文预测能力”之间的分析框架提供领域内参照。 | 研究使用特定流域、SWAT 输出与 ML 模型；信息量或传递熵与性能的关系不是因果定律，也不自动验证本项目指标。 |

## Shapley、互信息与传递熵

| BibTeX key | 本研究中的用途 | 使用边界 |
|---|---|---|
| `shapley1953value` | 为对全部信息源子集价值函数进行精确 Shapley 分摊提供原始定义与效率性质来源。 | 分摊结果取决于所选价值函数和可用联盟；它是边际贡献分配，不是因果效应，也不是模型内部的 SHAP 近似。 |
| `shannon1948communication` | 互信息、熵与信息量表述的基础来源。 | 提供理论定义，不提供有限样本估计器，也不处理时间序列自相关。 |
| `kraskov2004mutualinformation` | 对应当前连续变量 kNN 互信息估计的直接方法来源。 | 对样本量、邻居数、尺度和时间依赖敏感；估计值不带方向，且不能单独证明可恢复性。 |
| `schreiber2000transferentropy` | 传递熵及其方向性条件信息定义的原始来源。 | 离散化、滞后、历史长度和样本量都会影响估计；共同驱动与未观测混杂仍可能造成非因果关联。 |

## 分位数、CRPS、区间覆盖与趋势

| BibTeX key | 本研究中的用途 | 使用边界 |
|---|---|---|
| `koenker1978quantiles` | 分位数损失（pinball/check loss）和条件分位数估计的原始依据。 | 单个分位数损失只评价对应分位点，不保证完整预测分布或时间路径合理。 |
| `gneiting2007scoringrules` | 支持使用 proper scoring rules、CRPS 和区间分数，并把覆盖率与区间宽度共同报告。 | 只看覆盖率会奖励过宽区间；当前由有限分位点积分得到的是近似 CRPS，应在正文中明确。 |
| `mann1945trend` | Mann–Kendall 单调趋势检验的原始方法依据。 | 日序列的自相关、季节性和重复值会影响显著性；不能把朴素检验直接解释为独立样本推断。 |
| `sen1968slope` | 以两两斜率中位数估计稳健单调趋势幅度。 | Sen slope 是单一单调变化摘要，不识别突变点、周期或多阶段趋势。 |

## 金沙江站点、水温、流量和气象来源

| BibTeX key | 可支持的来源声明 | 使用边界 |
|---|---|---|
| `wei2026flowcomposition` | Nature Portfolio 旗下 *Communications Earth & Environment* 论文明确列出上金沙江 Zhimenda、Gangtuo、Batang、Shigu 四站，说明 2006–2020 年日流量和水温取自中国水文年鉴（其中 Gangtuo 水温截至 2018 年），并说明气象数据来自 CMA。 | 论文同时包含模型模拟和情景投影；引用时要区分观测、模拟与投影，不能把论文模型输出当成原始观测。该文不是 *Nature* 正刊。 |
| `wang2024yangtzetemperature` | *Water* 论文给出长江上中游 21 个控制站及水温、流量来自《中华人民共和国水文年鉴》第 VI 卷、气象数据来自 CMA 的来源说明。 | 原始水温/流量数据声明为向作者申请，并非论文附件中的公开原始表；它能支持来源链，不能替代逐文件溯源。 |
| `wei2026figshare` | Figshare v4 数据说明包含上金沙江 2006–2020 年观测流量/水温、模拟水温及修改后的 SWAT 源文件，许可为 CC BY 4.0。 | 数据包混合观测与模拟；使用前必须按工作表/字段区分。它是研究数据包，不替代中国水文年鉴这一上游来源。 |
| `noaa2025gsod` | NOAA/NCEI 官方 GSOD 记录可支持气温、降水、风等日汇总字段及其数据产品来源。 | GSOD 从逐小时/天气报文派生，以 UTC 日汇总；站点覆盖、缺报、单位换算和特殊缺失码必须按官方说明处理。BibTeX 年份 2025 指官方目录记录的最后更新时间，不是观测序列起始年。 |
| `nmic2012chinadaily` | CMA 国家气象信息中心的 V3.0 日值数据集记录可支持气温、降水、相对湿度、风等中国站点日值来源；数据代码为 `SURF_CLI_CHN_MUL_DAY_V3.0`。 | 官方记录注明实名注册访问并持续更新；其存在不能单独证明项目内某个文件就是该产品的原样导出。BibTeX 年份取官方记录的制作时间 2012。 |

### 数据来源链的写法边界

- 可写：相关 Nature Portfolio 论文和 *Water* 论文均声明水温/流量来自中国水文年鉴；Figshare v4 提供论文配套的观测与模拟数据包；CMA 与 NOAA/NCEI 是气象数据产品来源。
- 不可写：Figshare、NOAA 或 CMA 是中国水文年鉴水温/流量的原始发布者；现有来源不支持这一说法。
- 未为《中国水文年鉴》单独建立 BibTeX：目前只核验到两篇论文中的来源说明，未核验到与实际卷册、年份对应的官方在线书目。正文如需把年鉴列为独立参考文献，应先取得所用卷册封面/版权页或官方目录记录。

## 核验来源

- 插补模型与 benchmark：[NeurIPS BRITS](https://proceedings.neurips.cc/paper_files/paper/2018/hash/734e6bfcd358e25ac1db0a4241b95651-Abstract.html)、[Elsevier SAITS](https://doi.org/10.1016/j.eswa.2023.119619)、[NeurIPS CSDI](https://proceedings.neurips.cc/paper/2021/hash/cfe8504bda37b575c70ee1a8276f3486-Abstract.html)、[OpenReview GRIN](https://openreview.net/forum?id=kOu3-S3wJ7)、[arXiv TSI-Bench](https://arxiv.org/abs/2406.12747)、[PMLR real-world benchmark](https://proceedings.mlr.press/v287/toye25a.html)。
- 河流水温与水文缺输入：[Wiley paired air–water imputation](https://doi.org/10.1002/env.2426)、[PLOS daily stream-temperature reconstruction](https://doi.org/10.1371/journal.pone.0291239)、[Elsevier stream-temperature data gaps](https://doi.org/10.1016/j.ecolind.2020.107229)、[HESS missing inputs](https://hess.copernicus.org/articles/29/6221/2025/)、[HESS information quantity/quality](https://hess.copernicus.org/articles/30/1077/2026/)。
- 原始统计与信息方法：[Princeton/De Gruyter Shapley chapter](https://doi.org/10.1515/9781400881970-018)、[Wiley Shannon](https://doi.org/10.1002/j.1538-7305.1948.tb01338.x)、[APS mutual information estimator](https://doi.org/10.1103/PhysRevE.69.066138)、[APS transfer entropy](https://doi.org/10.1103/PhysRevLett.85.461)、[JSTOR regression quantiles](https://doi.org/10.2307/1913643)、[Taylor & Francis scoring rules](https://doi.org/10.1198/016214506000001437)、[JSTOR Mann trend test](https://doi.org/10.2307/1907187)、[Taylor & Francis Sen slope](https://doi.org/10.1080/01621459.1968.10480934)。
- 金沙江/长江与数据产品：[Communications Earth & Environment 2026](https://doi.org/10.1038/s43247-026-03340-2)、[Water 2024](https://doi.org/10.3390/w16121669)、[Figshare v4](https://doi.org/10.6084/m9.figshare.29002466.v4)、[NOAA/NCEI GSOD catalog](https://catalog.data.gov/dataset/global-surface-summary-of-the-day-gsod)、[CMA 中国气象数据网](http://data.cma.cn/)。

条目总数：**24**。
