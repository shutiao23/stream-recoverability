# Environmental Modelling & Software 投稿前模拟审稿：双审稿人报告

日期：2026-11-02（北京时间）

审阅对象：当前未提交的 r4 工作区，包括主文 [review_completion_article.tex](../../../paper/wrr_tr/review_completion_article.tex)（PDF 44 页，11 图 15 表）、SI [review_completion_supporting.pdf](../../../paper/wrr_tr/review_completion_supporting.pdf)（109 页，73 张表）、`src/`、`scripts/`、`tests/`、`Makefile`、[r4 科学表](../../../results/wrr_final_revision_20261031/)和候选包。

审阅方式：通读主文和关键 SI 章节，抽查核心实现，包括 D2 特征、AR(1) 残差桥、air2stream 实现、打包、CI 和 Docker 配置。另用已保存的 r4 表做了一项新的独立复算，见附录 A 和 [slope_signal_audit.py](slope_signal_audit.py)。本轮没有修改论文、科学 CSV、候选包或验收记录。

**说明：本报告是模拟审稿。** 审稿人 A 的关注点参照杨大文教授公开的研究方向设定：分布式水文模型 GBHM 与水热耦合 GBEHM、寒区与青藏高原水文、流域水热过程及气候变化归因。审稿人 B 是虚构的 MIT 计算机系教授，关注机器学习、统计推断和科学软件工程。两份意见都不代表任何真实学者或期刊的正式意见。

---

## 〇、编辑初审预判

**结论：如果按当前形态投 EMS，编辑直接退稿的风险很高。原因主要不在科学质量，而在于它仍是一篇 WRR 稿件。**

1. **格式和期刊身份不对。** 稿件使用 `agujournal2025` 文档类，并写着 `\journalname{Water Resources Research}`（[第2行](../../../paper/wrr_tr/review_completion_article.tex#L2)、[第60行](../../../paper/wrr_tr/review_completion_article.tex#L60)）。Key Points、Plain Language Summary 和 AGU 式 Open Research 都需要替换成 Elsevier 格式。需要准备的内容包括：
   - Highlights：Elsevier 常规要求为 3–5 条，每条不超过 85 个字符（含空格）；
   - 关键词；
   - 建议提供 Graphical abstract；
   - Software and data availability 节；
   - CRediT 作者贡献、利益冲突声明和资助信息；
   - 生成式 AI 使用声明：如果写作中使用过 AI 辅助工具，Elsevier 要求在稿件中声明。本仓库有 56 条提交带 Cursor 代理的共同署名，请按现行政策如实填写。

   当前摘要 245 词。旧版作者指南曾写摘要不超过 200 词；现行上限请以官网 Guide for Authors 为准，建议提前压到 200 词以内。
2. **刊物定位不清。** EMS 的范围说明要求作者清楚说明模型或软件的目标和开发步骤。软件工作应尽可能提供可用性、可靠性和验证的定量证据，并说明许可与开源获取方式。当前稿件把贡献写成"一项河流水温档案的实证评估"，没有把任何可复用的建模方法或软件列为贡献。编辑很可能会认为这是一篇缺少通用建模或软件贡献的应用研究。
3. **软件与数据可用性不满足期刊要求。** EMS 将 Software and data availability 作为期刊特色。"contact the authors"不被接受；论文依赖的软件在审稿期间必须让审稿人能够获取。当前 Open Research 写的是 "Permanent repository identifiers are not yet available"（[第245行](../../../paper/wrr_tr/review_completion_article.tex#L245)）。LUBW 受限材料的审稿访问尚未落实，作者信息也仍是占位符。
4. **可读性差。** 主文由 60 多个 `\input` 文件拼成，其中 44 个是数值宏文件。正文含内嵌表格和图注约 9,700 词，几乎每句话都带限定语。读者在前两页找不到"结论是什么"。

**策略提示：** EMS 能否送审，取决于作者是否愿意把"方法框架加开源软件"列为一级贡献并真正交付（见第四部分 P0）。如果不打算投入软件化，本稿更自然的去向仍是水文类期刊，例如 WRR、HESS 或 J. Hydrol.。在 EMS 上硬投的性价比不高。

以下两份意见假定稿件已经送外审。

---

## 一、审稿人 A：水文水资源视角

### 总体评价

作者处理的是监测实践中常见的真实问题：缺测年份应该删除还是补齐，以及这个选择如何影响夏季热极值的多年趋势。研究工作量很大。作者对信息泄漏、样本分母和负结果的交代非常透明，这在水文文献中少见，值得肯定。

但作为一篇水文建模论文，我认为它有三个根本问题。

- **科学问题用统计学语言表述，缺乏水文过程的锚点。**
- **主要结论的实际意义没有放在"短序列趋势本身的不确定性"这个尺度下衡量。**
- **重建模型忽略了控制河流水温的一阶过程变量，包括流量、湖泊和调节。** 因此"区域差异"无法得到水文解释。

**建议：大修。**

### 主要意见

**A1. 科学问题需要用水文语言重新表述，并让 RQ2 成为主线。**

- 标题 "time support of finite-record heat slopes"，以及 "finite-record H30 slope on a specified reference-year set"、"source-role calibration" 等术语，对水文和环境建模读者都不直观。核心问题可以用一句话说清："夏季出现长缺测时，计算多年热极值趋势应删除这些年份，还是先重建再计算？两种做法的误差有多大，在什么条件下失效？"
- 引言应先交代水文背景，再引出完整年筛选问题：
  - 河流水温的控制过程：辐射与气温、流量与热容量、地下水补给、融雪融冰、湖泊和水库调节、遮荫；
  - 夏季长缺测为什么与这些过程有关：低流量时传感器出露、热浪期集中维护、汛期设备损坏。
- 大样本研究因完整性筛选丢弃大量站点，这是本文最有力的动机，但目前没有写进引言。例如此前审稿整理过：Hare 等（2021）只对完整年超过 14 年的站做趋势分析，1,424 站中仅保留 197 站（引用前请核对原文）。请把这类证据放进引言第一段。
- RQ1（观测窗口事实）相对暖季规则的增量只有 2 个站年，超出量为 0.150 和 0.113 °C（[第155行](../../../paper/wrr_tr/review_completion_article.tex#L155)）。这与常见水温传感器的标称精度（约 ±0.1–0.2 °C）在同一量级。建议把 RQ1 降为"数据使用原则加实例"，主文用一段文字和一张图即可，让 RQ2（筛年与重建对趋势的影响）成为主线。
- 结果各节的顺序与 RQ1–RQ3 的编号不一致：区域失败（RQ3）出现在年份选择（RQ2）之前。引言[第81行](../../../paper/wrr_tr/review_completion_article.tex#L81)和[第89行](../../../paper/wrr_tr/review_completion_article.tex#L89)对 Johnson 和 Beaufort 的比较写了两遍。

**A2. 主要结论的实际意义，必须相对于趋势本身的抽样不确定性来衡量（本报告新复算）。**

我用作者保存的 r4 表做了复算（附录 A）。

- **作为"真值"的完整记录斜率，本身大多不显著。**
  - 41 个前推站的参考年份数中位数仅 14 年。
  - 完整记录 H30 的 OLS 斜率中位数为 0.754 °C/10a，但其标准误中位数为 0.59 °C/10a。H30 年际标准差的中位数为 1.01 °C。
  - 41 站中只有 3 站的 OLS 斜率在 5% 水平显著，Kendall 检验为 4 站。
  - 也就是说，这个"真值"在约九成站点上与零无法区分。
- **控制缺口（30–90 天）下：**
  - 暖季筛选的斜率误差中位数是该站斜率标准误的 0.36 倍；误差超过 1 个标准误的档案占 13.4%；斜率符号翻转 53/805。
  - 全保留重建后，三项分别为 0.11 倍、0.75% 和 16/805。
- **经验缺测日历下：** 暖季筛选误差的 90% 分位数仅为 0.28 个标准误；误差超过 1 个标准误的档案只有 2/818；符号翻转 3/818。
- **现稿的比例写法有误导性。** 现稿把 0.446 °C/10a 写成"中位斜率的 59.1%"（[第197行](../../../paper/wrr_tr/review_completion_article.tex#L197)）。读者很容易把它理解为"低估了约六成增温"，而作者自己也承认这不是逐档案的相对误差。更有水文意义的尺度是误差与斜率标准误之比、符号翻转率和显著性判断的改变率。

建议：

- (a) 用上述尺度重写主要结论。
- (b) 把最有用、也最诚实的信息直接写出来："在严重的夏季长缺测下，重建优于删年；在实际观测到的典型缺测格局下，两种处理对约 14 年趋势的影响远小于趋势本身的不确定性。"
- (c) 补充 Sen 斜率和考虑序列自相关的 Mann–Kendall 检验（Hamed & Rao 1998；Yue et al. 2002）。这是水文趋势分析的标准做法；本数据中 OLS 与 Sen 斜率之差的中位数约 0.10 °C/10a，不可忽略。
- (d) 离线长记录的 D2 斜率 RMSE 只有 0.009–0.028 °C/10a（[表](../../../paper/wrr_tr/simple_research_tables.tex)），而前推 16 年窗口约为 0.067–0.173。这说明"删还是补"主要在短记录中要紧，而短记录恰恰是趋势最难检出的情形。讨论部分需要正面回应这个张力。

**A3. 重建模型缺少流量这一一阶控制变量。**

- D2 的特征（[wrr_tr_features.py](../../../scripts/wrr_tr_features.py)）、各个日重建器和主文对比中都没有流量。主文的过程型对照是不含流量的 air2stream-3。仓库里已经实现了含流量的 air2stream-8（[air2stream_equivalent.py](../../../src/stream_recoverability/experiments/air2stream_equivalent.py)），但它没有进入主分析。
- 流量通过热容量和停留时间，调节水温对气象强迫的响应；干旱低流量会放大热浪期的水温升高（van Vliet et al. 2011；Toffolon & Piccolroaz 2015）。2015、2018、2019、2022 年的中欧夏季，正是热浪叠加低流量。
- 巴伐利亚 air-ridge 重建在隐藏峰值上的表现符合这一机制的特征：90% 区间覆盖率只有 67.9%，中位偏差 −0.479 °C，30.2% 的真值高于区间上端。系统性低估，正是"只用气温、不用流量"的模型在低流量热浪年最可能出现的表现。
- 此前面向 WRR 的模拟审稿把流量机制列为"后续研究"。我理解这一取舍，但对 EMS 和水文审稿人而言，RQ3 的核心结论目前是"无法识别原因"，这是全文最弱的一环。FOEN 和巴伐利亚 GKD 都公开日流量，补数据的成本并不高。建议分两档完成：
  - 最低限度：补齐 34 个巴伐利亚和瑞士站的日流量，诊断隐藏峰值误差与缺口期流量距平的关系。
  - 完整版：把流量（或流量距平）加入日重建器和 D2 特征，并以 air2stream-8 作为过程型基准。

  如果流量能解释大部分巴伐利亚失效，RQ3 就从"无法识别"变成一个有水文含义的结论。

**A4. "瑞士与巴伐利亚的区域差异"更可能是河流类型差异。**

- **瑞士站点基本是一条湖泊缓冲的河链。** 根据 SI 站点表的坐标，瑞士 10 站中有 9 站属于同一连通群组 g0029，主要沿阿勒河（Aare）河链分布，靠近布里恩茨湖、图恩湖和比尔湖的出入口。湖泊出口的水温被湖体热惯性平滑，同一河链上下游站点高度相关，donor-ridge 方法自然表现好。
- **巴伐利亚站点以受调节的大中型河流为主。** 按坐标判断，24 站主要分布在多瑙河干流（g0032，9 站）、美因河（4 站）、伊萨尔河（3 站）、伊勒河（3 站）和因河（2 站），梯级水电与调节普遍。请作者核实河流归属。
- **请核查热电厂运行变化是否造成非平稳。** Gundremmingen（多瑙河）、Grafenrheinfeld（美因河）和 Isar（伊萨尔河）等电厂在 2010–2025 年间相继停运，其冷却水热排放的变化，可能让下游站点的水–气关系出现非平稳。而前推模型只用 2010 年以前的数据训练。
- **因此，这个"区域"对比实际上是：** 湖泊缓冲的单一河链，对受调节的大河网络，再叠加训练历史长度的不平衡。
- **建议按河流类型或流域属性分层。** 可用的属性包括流域面积、高程、湖泊比例、冰川比例、基流指数和调节程度，可以直接从 CAMELS-CH（Höge et al. 2023）、CAMELS-DE（Loritz et al. 2024）、LamaH-CE（Klingler et al. 2021）和 HydroATLAS（Linke et al. 2019）获取。EMS 2025 年发表的 Diaz、Oliver、Gorski 美国水温研究，就按地下水、水库和热电厂影响河段分别评估了区间覆盖率。这篇文献已在项目 bib 中，但主文没有引用。
- 现稿写道 "If area, elevation or discharge were complete they would be summarized; they are not"（[第112行](../../../paper/wrr_tr/review_completion_article.tex#L112)）。对于 42 个知名的欧洲和美国长序列站，水文审稿人很难接受这一点。
- 35/42 站的调节状态标签是 `unmatched_gages`，这个标签对读者没有意义。建议用 GRanD 或区域水电数据库给出上游调节程度的定量指标。

**A5. 气象强迫数据的空间代表性需要检验。**

- NASA POWER 的气象变量来自 MERRA-2，格点约 0.5°×0.625°。在阿尔卑斯和前阿尔卑斯地形中，格点高程与站点或流域高程可能相差数百米，气温的偏差和日变化都可能失真。
- 建议做强迫数据敏感性分析，可选数据包括 E-OBS（0.1°，Cornes et al. 2018）、ERA5-Land（0.1°）、MeteoSwiss 格点数据，以及 DWD 站点或 HYRAS 数据。至少应报告格点与站点的高程差，并检验 air-ridge 的失效是否与它相关。
- 如果为了可迁移性只能使用一种全球产品，应在方法部分说明这一选择的代价。

**A6. 样本代表性不足：方法是在最不需要它的地方被检验的。**

- 主评估的 42 站是 581 站档案中的"长完整尾部"：完整年数中位数为 31 年，其余 539 站只有 8 年。前推的 41 站中，巴伐利亚 24 站、瑞士 10 站。这些站历史长、邻站多、缺测少。真正需要重建的，往往是历史短、邻站少、地处偏远、冬季冰冻或维护困难的站。本项目最初研究的金沙江上游站点，以及青藏高原等寒区河流，都属于这一类。
- 建议做"历史长度与邻站消融"，不需要新数据：在同一批站上，把训练历史截短到 3、5、10 年，把可用邻站人为减少到 0–1 个，观察 D2 与经典法的比较以及筛年规则的结论如何变化。这能直接回答"方法能否推广到资料稀缺地区"。
- 寒区站点的缺测机制不同：冬季冰冻、汛期冲毁居多。H30 是夏季指标，结论能否迁移需要在讨论中划定边界。
- 可选的前瞻方向：把过程模型（例如水热耦合的分布式模型）模拟的水温，作为 D2 的一个"虚拟邻站"或特征，用于没有邻站的流域。这可以放在讨论中作为展望，不必在本稿完成。

**A7. H30 指标的生态与管理含义需要说明。**

- H30（年最大 30 日滑动平均）不是生态或水质标准中常用的指标。常用的是 MWAT（最大周平均温度）、7DADM（7 日日最高温滑动平均，美国 EPA Region 10 采用）和超阈天数。仓库里已经有 H7 的重算结果，但没有报告（[第110行](../../../paper/wrr_tr/review_completion_article.tex#L110)）。
- 建议：
  - (a) 在 SI 中给出 H7 下的关键结论，检验结论对窗口长度是否稳健；
  - (b) 讨论日均值与日最高值的差别，以及基于日均值的 H30 能在多大程度上代表鱼类热胁迫；
  - (c) 说明哪些管理决策实际使用 H30 一类的指标，可以 Beaufort 等（2022）的热峰指标作为联系点。

**A8. 缺测机制应先用观测资料检验，再设计压力情景。**

- 2010–2025 年间，41 站共有 109 个不完整站年，分布在 29 站。最长连续缺口的中位数只有 4 天，不少于 30 天的占 11.93%，约 13 个站年，约为 41 站×16 年总量的 2%（[第135行](../../../paper/wrr_tr/review_completion_article.tex#L135)）。
- 控制缺口实验则在 7 年预热期后，对每个参考年以 0.35 的概率施加 30–90 天缺口。长缺口的发生率比实际高一个数量级以上。
- 0.35 的概率、7 年预热期，以及"热年优先缺测"的强度，都需要观测依据。建议直接用 581 站档案估计缺测日的发生是否与气温距平、流量距平（低流量）和季节有关，例如用逻辑回归或生存分析。这既检验了 MNAR 假设，也为压力情景提供了经验参数。
- 摘要和结论的核心数字应以经验日历结果（0.114→0.067）为主，控制缺口作为压力测试。这比现在的写法更符合水文读者的预期。

**A9. 需要一个实践者能直接使用的结论。**

- 讨论中的建议是"保留观测事实、说明参考年份集合和选年规则、分别报告重建误差与数值不确定性"。这些都对，但过于抽象。
- 建议给出决策流程图或决策表：输入是缺口长度与位置、历史长度、可用邻站、是否有流量；输出是删年、只给观测下界，还是重建。每个分支都对应论文中的证据和预期误差范围，误差以趋势标准误为单位。
- 再配一个真实站点的完整案例：2018 或 2022 年夏季长缺测的日水温过程线、缺口位置、观测下界、D2 与经典法的区间，以及对该站趋势的影响。水文读者需要看到方法在一条真实河流上如何工作。

**A10. 图件需要达到水文和环境建模期刊的基本标准。**

- 图 2（研究区）只是一张经纬度散点图，从美国西部一直延伸到芬兰，约九成画面是空白，没有河网、湖泊、地形、国界或流域边界。应改为带底图的研究区图：主图为欧洲中部（巴伐利亚与瑞士），小图显示美国和芬兰站点；用符号区分河流类型或连通群组，并标出湖泊和主要水库、电厂。
- 图 9 只有 3 根柱，可以并入表格。图 11 字号过小，纵轴标签难以辨认。
- 目前缺少展示日尺度过程的图，例如缺口、重建结果和区间，建议增加（与 A9 的案例图可以合并）。

### 次要意见（A）

1. 需要给出"connected group"的水文定义：同一河网的上下游连通，还是同一流域？并说明判定方法。
2. 说明原始数据的时间分辨率、日均值的计算方式（子日数据不完整的日子如何处理），以及各数据提供方质量码的处理办法。
3. 对 1981–2025 年观测见证分析中"站点特定暖季"（按气候学取连续 5 个暖月）的选取结果，给出各站暖季月份的分布。
4. **主文正文只引用了 11 篇文献**（`review_completion_article.bbl` 只有 11 条），这对 EMS 和水文审稿人都明显不足。项目 bib 中已有但未在主文引用的文献包括：Diaz 等（2025，EMS）、Isaak 等（2012）、Toffolon & Piccolroaz（2015）、Arismendi 等（2014）、Gallice 等（2015）、Orr 等（2015）和 Zwart 等（2023）。还应补充：
   - Webb 等（2008）：综述；
   - Mohseni 等（1998）：水温与气温的非线性关系；
   - van Vliet 等（2011）：流量对水温敏感性的影响；
   - Feigl 等（2021）和 Rahmani 等（2021）：机器学习水温模型；
   - Hare 等（2021）及其他因完整性筛选丢弃大量站点的大样本研究。

   其中 Isaak 等（2012）利用重建填补不完整记录来估计长期水温趋势，与本文目标最接近，必须讨论。
5. 统一单位写法（°C per decade 与 °C/10a）；"station-year"、"station–repetition–setting"等样本单位在首次出现时给出定义。
6. 摘要写"42 long complete records"，而趋势分析用的是 41 站（一站 1994 年结束）。请在摘要中统一，或用一句话说明两者的关系。

---

## 二、审稿人 B：计算机科学视角（机器学习、统计推断、科学软件工程）

### 总体评价

作者在防止信息泄漏、保留负结果、把数字绑定到结果文件等方面投入了罕见的工程努力，值得肯定。但从 EMS 的角度看，这篇论文目前既不是一篇清晰的方法论文，也不是一篇软件论文。

- **可复用的软件贡献尚未被定义和交付。**
- **方法与已有文献脱节，基线也不足。** 方法是几种已知技术的组合：残差分位数回归加分组校准、残差桥蒙特卡洛、边际采样加秩耦合。但论文没有把它们与相应的机器学习和统计文献对接，也缺少现代基线。
- **统计推断的有效样本量小，并且存在适应性过拟合风险。** 同一队列经历了多轮修订和事后分析。

**建议：大修。如果软件不能在审稿期间交付，倾向退修重投。**

### 主要意见

**B1. 软件贡献需要被定义、打包和验证。**

- **现状**（我的统计）：
  - `src/` 有 244 个模块，约 11 万行；
  - `scripts/` 有 981 个编号脚本，约 24 万行；
  - `tests/` 有 289 个文件、1,623 个测试函数；
  - Makefile 有 245 个目标，62 KB。
- **核心流程分散在编号脚本和以项目阶段命名的模块中。** 例如 [521_whole_archive.py](../../../scripts/521_whole_archive.py) 从 `experiments.v19_revision`、`experiments.tr_revision` 和 `development_recovery` 导入函数。模块名（t2_*、v17_fitness、v18_closure、v19_revision、wrr_revision）记录的是项目历史，不是领域概念。
- **元数据彼此不一致：**
  - [pyproject.toml](../../../pyproject.toml) 版本为 0.1.0，描述仍是 "for the Jinsha River monitoring network"；
  - [CITATION.cff](../../../CITATION.cff) 版本为 1.1.0，摘要提到 "reservoir causation" 和 "monitoring-placement replay"；
  - git 标签为 v1.0.0；
  - [LICENSE](../../../LICENSE) 的前言列出了 China Hydrological Yearbook、CMA 等与本文无关的数据源。
- **建议把仓库拆成两层：**
  - **(a) 一个小而稳定的库**（名称如 `gapbench` 或 `h30gap`，规模几千行而不是几十万行），暴露清晰的 API，例如：
    - `observed_window_bound(series)`
    - `mask_archive(archive, generator, seed)`
    - `fit_annual_error_model(...)`
    - `sample_bridges(..., n_paths, seed)`
    - `select_years(calendar, method="cdf"|"sxx")`
    - `decompose_slope_error(...)`
    - `group_splits(groups, roles)`

    配套 API 文档、教程 notebook 和一份可公开再分发的小示例数据（例如 USGS 公开站点），在笔记本电脑上 30 分钟内能端到端跑通。
  - **(b) 一个"论文复现 compendium"**，只保留生成本文图表所需的脚本。其他历史阶段的代码归档到单独分支或 Zenodo 历史版本。
- **按 EMS 要求写 Software and data availability 节**（模板见第五部分），并在审稿期间提供可以访问的版本：GitHub release 加 Zenodo DOI；必要时提供密码保护的下载链接。

**B2. 可复现性：把工程投入从"身份核验"转向"可重跑"。**

- README 的复现分层表承认 "Clean-environment installation: Not proved" 和 "Full raw-provider retraining: Not proved"。对 EMS 审稿人来说，这两项比 SHA-256 清单、JUnit 解析和 r1–r4 验收门都重要。当前 [Dockerfile](../../../Dockerfile) 只安装 `.[dev]` 并运行 `make test`，不运行任何分析。LightGBM 位于 `review` extra 中，并未安装，所以容器里连 D2 都无法运行。
- 主文承认存在一个后来才发现的隐性依赖："stored stochastic bridge-repair tables … checked retrospectively"（[第121行](../../../paper/wrr_tr/review_completion_article.tex#L121)）。第 213 行还提到，两个零掩膜档案因为预测表 schema 为空，在旧诊断中被排除。这两件事说明，工作流的数据依赖和数据契约都没有被显式声明。
- 建议：
  - 用显式 DAG 工作流（Snakemake、DVC，或至少是带输入哈希的 Make 规则）管理从原始数据到图表的依赖；
  - 用 schema 校验（例如 pandera）在流程中拦截空表或缺列的表；
  - 在 CI 中构建 Docker 镜像，在小样本上跑通端到端流程，并发布镜像摘要。
- 测试应更多覆盖算法性质，而不是文件身份：
  - 已知答案测试：例如 AR(1) 桥的解析矩；OLS 斜率权重之和为零，且与年份中心化变量的内积为 1；
  - 性质测试（例如用 Hypothesis 库）：任意掩膜下都有 `H30 ≥ L_y`；
  - 从接口层面保证"选年不读取水温"：选年函数的签名中根本不接收水温；
  - 在小型公开数据上做端到端回归测试。
- **LUBW 问题已经解决了一半，应当把剩下的做完并放到前面。**
  - 按 [DATA_RIGHTS.md](../../../DATA_RIGHTS.md) 的记录，原模型 13 个估计器角色组合全部含有正权重的 LUBW 案例。
  - 仓库里已有一个"候选提供方"敏感性分析：只用候选提供方的源案例，并严格排除目标区域群组。它的主要结果与原模型很接近（[open_source_values.tex](../../../paper/wrr_tr/open_source_values.tex)）：
    - D2 与经典法在共同档案上的趋势 RMSE，从 0.164/0.147 变为 0.158/0.156；
    - 保留贡献份额从 93.9% 变为 93.7%；
    - D2 趋势区间覆盖率从 88.0% 变为 87.6%。
  - 但这个模型及其案例输出仍只保存在本地，主文也只用一句话带过（[第175行](../../../paper/wrr_tr/review_completion_article.tex#L175)）。
  - 建议：
    - (a) 核实它的全部数据源，包括邻站的上游来源，都可以公开再分发；
    - (b) 公开它的模型权重和案例输出，把它定为开放复现路线的主模型；
    - (c) 在主文中用一句话报告："改用开放源模型后，主要结论不变。"

    做到这三点，开放复现路线就能覆盖全部主结论，数据权利问题就从审稿阻塞降为一条附注。

**B3. 方法需要与机器学习和统计文献对接。**

- **D2 实际上就是 Mondrian 版的 CQR。** D2 对 plug-in 年值的残差做 LightGBM 分位数回归，再在不相交的群组上估计经验偏移。这实质上是分组（Mondrian）版本的共形化分位数回归（CQR，Romano et al. 2019），应明确写出这层对应关系。
  - 共形方法的覆盖保证依赖于校准样本与测试样本的可交换性。区域之间、时期之间存在分布漂移时，巴伐利亚 air-ridge 67.9% 的覆盖率正是可以预期的"条件覆盖失效"。
  - 可以讨论或试验以下方法：加权共形预测（协变量漂移，Tibshirani et al. 2019）、自适应共形推断（时间漂移，Gibbs & Candès 2021）、带条件保证的共形方法（Gibbs, Cherian & Candès 2023）。项目的依赖中已经有 `conditionalconformal` 包。
- **有效校准样本量很小。** 轨迹实验中每个角色只有 4 个正权重连通群组（[第146行](../../../paper/wrr_tr/review_completion_article.tex#L146)）。案例在群组内相关时，有效校准样本数接近群组数，覆盖率的抽样波动会很大；split conformal 的条件覆盖率服从 Beta 分布。仅凭这一点，就可能产生区域间十几个百分点的覆盖差异。应先量化这一"零假设"下的波动范围，再讨论水文机制。
- **分位数交叉与尾部外推。**
  - 分位数交叉用排序修正，这对应 rearrangement 方法（Chernozhukov et al. 2010），应引用。
  - 只有 7 个分位水平，外尾用正态间距外推，这是一个没有验证过的假设。建议增加分位水平（例如 19 或 99 个），或者改用分布回归：直接以 CRPS 为损失的模型、NGBoost 或分位数回归森林（Meinshausen 2006）。
  - 应给出 PIT 直方图或可靠性图，而不只报告名义覆盖率。
- **超参数来源。** LightGBM 超参数"固定、未重调"（300 棵树、学习率 0.05、31 片叶子等），需要说明来源；至少在源角色内部做嵌套交叉验证或敏感性分析。
- **"D2"这个名字从未解释过**，而且在方法部分定义之前，引言[第89行](../../../paper/wrr_tr/review_completion_article.tex#L89)就已经出现。建议改用描述性名称，例如 "annual residual quantile model"。

**B4. 基线不足。**

- **日尺度插补基线**，至少应包括：
  - 一个状态空间或卡尔曼平滑基线（imputeTS 一类）；
  - 一个多变量插补基线（MICE 或 missForest）；
  - 一个深度学习插补基线（BRITS 或 SAITS）。

  仓库中已有基于 PyPOTS 1.5 的 BRITS/SAITS 适配器（[reference_baselines.py](../../../src/stream_recoverability/models/reference_baselines.py)），`pypots==1.5` 也在依赖列表里，但当前论文没有使用。应当纳入，或者说明为什么放弃。
- **概率插补基线。** CSDI（Tashiro et al. 2021）等概率时间序列插补方法可以直接生成联合样本路径，正是本文需要的。
- **河流水温专用模型。** 例如 LSTM 水温模型（Rahmani et al. 2021；Feigl et al. 2021 系统比较了多种机器学习方法），以及含流量的 air2stream-8。
- **评估方式。** 所有基线应在相同掩膜上，同时评估日尺度误差和下游指标（年 H30 与斜率）。"日误差小不等于下游统计量准"本来就是本文的论点之一，基线对比正好能把它变成一个有证据的发现。

**B5. 趋势不确定性的传播，应采用多重插补框架。**

- **当前做法**：先得到年边际分布（7 个分位数，加插值和外推），再用独立秩、辅助 Ridge 自助状态或 3 年残差块把它们"耦合"成联合样本，最后计算 OLS 斜率。
- **问题**：三种耦合方式都保持边际不变，但都不是同一个联合生成模型的后验样本。在 4,096 个样本下，趋势区间覆盖率仍只有 87.4–89.9%（名义 95%），而作者无法确定欠覆盖的来源。
- **这其实是在重新发明多重插补。** 规范做法是：从一个联合模型中抽取完整的日序列路径（保持跨年依赖），对每条路径计算 H30 和斜率，再按 Rubin 规则合并（Rubin 1987；Little & Rubin 2019；van Buuren 2018）。同时应讨论插补模型与分析模型是否相容（congeniality，Meng 1994）。
- **建议**：至少用一个联合模型（AR、状态空间或 CSDI）实现这一流程，作为对照。

**B6. 统计推断与研究设计。**

- **有效样本量小。** 样本只有 41 站、17–18 个连通群组，其中瑞士只有 2 个；20 次掩膜重复属于伪重复。群组数少时，群组自助法的百分位区间可能偏窄（Cameron, Gelbach & Miller 2008）。建议改用 wild cluster bootstrap，或者用以群组和站点为随机效应的混合效应模型给出主要对比。
- **存在适应性过拟合风险。**
  - 同一个 41 站队列已经历多轮修订和大量事后分析，作者已将这些分析标为探索性。在适应性数据分析中反复使用同一个"测试集"，会导致过拟合（Dwork et al. 2015）。
  - 对一篇方法或软件论文而言，最能提升可信度的不是更多内部诊断，而是一次锁定的确认性检验：冻结代码和选择规则；事先在 OSF 登记假设，例如"全保留重建的斜率 RMSE 低于暖季筛选"、"CDF 选择器在经验日历下不劣于暖季规则"；然后在从未打开过的新站点上只运行一次。
  - 仓库已有 USGS、Hub'Eau（法国）和 UK EA 等公开数据的采集代码，可以作为新站点来源。
- **分母太多。** 文中出现 805、807、818、820、736、701、738 等多个分母。请用 CONSORT 式流程图交代每一步排除的原因和数量。

**B7. 随机数设计导致"原生 20 路径不等于嵌套 500 路径的前缀"。**

- 原因：[baselines.py 第38行](../../../src/stream_recoverability/experiments/tr_revision/baselines.py#L38)的 `ar1_bridge` 在每一天调用 `rng.normal(..., draws)`，随机流的消耗量取决于总路径数。所以同一编号的路径会随预算改变。作者因此不得不在方法（[第146行](../../../paper/wrr_tr/review_completion_article.tex#L146)）、结果、图 11 和讨论中反复区分 "native 20" 与 "nested 500 prefix"。
- 修复：给每条路径一个独立的随机流，嵌套关系就能由构造保证。例如 `np.random.SeedSequence(case_seed).spawn(n_paths)`，或以 (case, path) 为键的计数型生成器（Philox；Salmon et al. 2011）。这样预算比较只剩一种定义，相关的约半节文字可以删除。
- 所有蒙特卡洛估计（覆盖率、端点、CRPS）都应附上蒙特卡洛标准误，而不是只给三个种子的范围。

**B8. 计算成本与可扩展性。**

- EMS 读者会关心每种方法的计算成本。请报告：
  - 每个站年的墙钟时间、CPU 时间和内存，分别针对 plug-in、D2 训练与推断、经典法 20 路径和 500 路径；
  - 扩展到国家级监测网（成千上万个站）时的复杂度。
- 讨论中提到"没有实际计时"。对 EMS 来说，这是一个很容易补上的缺口。

**B9. 泄漏控制与元数据一致性。**

- 作者对隐藏日、2010 年前训练和连通群组分割的处理值得称赞。
- 但有两处会让读者质疑其他元数据：
  - 前推实验实际上只排除了被测群组，而不是整个区域：HUC17 估计器和 NVE 区间校准都保留了同区域的其他群组；
  - 3,320 个 `design.json` 文件里 "held region excluded" 的描述并不准确（[simple_research_methods.tex](../../../paper/wrr_tr/simple_research_methods.tex) 末段）。

  建议重新生成正确的元数据，而不是只附一份更正清单。
- 建议在 SI 中附一张泄漏检查表（参照 Kapoor & Narayanan 2023 的分类），以及 D2 的"模型卡"（Mitchell et al. 2019），写明训练数据、适用范围和已知的失效区域，例如巴伐利亚 air-ridge 的隐藏峰值。

**B10. 发布规则：用选择性预测框架评估，或者移出主文。**

- 三输出规则（给出数值、只给下界、标为未知）本质上是带弃权的选择性预测。
- 在数值输出数量相同时，它不优于简单的分数排序：错误率 10.94% 对 6.94%。任务校准仅覆盖 4.8% 的案例（39/820）。
- 建议用风险–覆盖率曲线（Geifman & El-Yaniv 2017）或共形风险控制（Angelopoulos et al. 2024）重新评估。如果结果仍为负，就移到 SI，主文用一句话交代。

**B11. 写作结构。**

- **限定语重复。** 当前正文读起来像审计日志：每个数字都附带分母、随机种子和限定语，同一条限定在方法、结果和讨论中重复三四次。
- **建议的改法：**
  - 每条限定只在一个集中的 Limitations 节里说明一次；
  - 每节以一句结论开头；
  - 方法部分用算法框（伪代码）描述 D2、残差桥、选年规则和误差分解；
  - 加一张符号表。
- **篇幅建议：** 目前主文 15 张表、11 张图，SI 有 73 张表、109 页。建议主文控制在 6–8 张图、3–4 张表，SI 控制在 30 张表以内。历史版本的对照（旧的单次随机抽取、弱间距规则、两个种子的比较等）移入 SI，或直接删除。

### 次要意见（B）

1. 对 "available"、"common"、"paired" 等样本集合名词，在全文统一定义一次并一致使用。
2. 两个 bootstrap 种子（2026102969 和 20261031）分别用于不同的表，这一点应集中在一个地方说明。更好的做法是在同一流程中统一种子，再报告区间对种子的敏感性；前一轮已复核 21 个种子，方向一致，可以引用这一结果。
3. 数值从结果表自动写入 LaTeX 宏的做法，值得在软件节中作为可复现实践介绍；但宏名不应进入任何读者可见的文字。
4. 脚本中硬编码了 `OMP_NUM_THREADS=1` 等线程设置。应在文档中说明并行策略与结果确定性的关系，因为 LightGBM 多线程可能带来非确定性。
5. 说明 `torch` 和 `xgboost` 是否只用于历史基线。如果是，就从核心依赖中移出，以缩小安装面。

---

## 三、两位审稿人的共识与分歧

**共识：**

1. 研究问题真实，工作量大，透明度高。
2. 当前稿件不是 EMS 的形态，需要重构为"方法与软件框架，加案例研究"。
3. 主要结论要换一个更有意义的尺度，即相对于趋势本身的不确定性，并把经验日历结果放在前面。
4. 需要更强的基线和过程变量。
5. 一次锁定的外部确认，比继续增加内部诊断更有价值。
6. 写作必须大幅压缩。

**分歧与取舍：**

- **A 和 B 的优先方向不同。** A 希望补充流量、流域属性和河流类型分层，让失效有水文解释；B 更关心统计框架（共形方法、多重插补）和软件交付。如果时间有限，优先做 A3（流量诊断）和 B1/B2（软件与复现）：前者决定科学可信度，后者决定 EMS 是否送审。
- **压缩方向一致。** A 倾向于把 RQ1 降格，B 倾向于把发布规则移出主文。两者指向同一个方向：主文只讲一个故事，即"筛年与重建对趋势的影响，以及何时失效"。

**预计结论：** 审稿人 A 给大修；审稿人 B 给大修，偏向退修重投。如果不完成第四部分的 P0 项，编辑初审被退回的可能性较高。

---

## 四、修改路线图（按优先级）

工作量为粗略估计，假设一人全职、计算资源与现有仓库相同。

| 优先级 | 任务 | 具体做法 | 工作量 | 完成标志 |
|---|---|---|---|---|
| P0 | EMS 版贡献表述 | 写出三条贡献：可复用、防泄漏的整档案联合退化基准框架；开源软件；河流水温案例的定量发现与失效边界 | 1–2 天 | 引言末段和 cover letter 能用三句话说清 |
| P0 | 格式转换 | 改为 elsarticle；删除 Key Points 和 PLS；写 Highlights；准备 Graphical abstract；摘要压到 200 词以内（以官网为准）；加 CRediT、利益冲突、资助和生成式 AI 声明 | 1–2 天 | 对照官网 Guide for Authors 逐项核对 |
| P0 | 软件交付 | 抽取核心库，配文档、示例数据和教程；统一版本号；更新 pyproject 描述、CITATION 和 LICENSE；GitHub release 加 Zenodo DOI | 1–2 周 | 干净环境中 `pip install` 后，30 分钟内跑通示例 |
| P0 | 开放源模型前置 | 核实已有候选提供方敏感性的全部数据源（含邻站上游来源）可以公开；公开模型权重和案例输出；主文报告"结论不变" | 2–5 天（取决于权利核查） | 开放复现路线覆盖主结论 |
| P0 | 作者、访问与保存 | 见 [SUBMISSION_READINESS_ZH.md](../wrr_comprehensive_review_20261102/SUBMISSION_READINESS_ZH.md) | 视外部进度 | 无占位文字 |
| P1 | 实际意义重述 | 报告误差与斜率标准误之比、符号翻转、显著性改变，以及 Sen/MK 结果（附录 A 已给出前两项） | 1–2 天 | 摘要和结论改用新尺度 |
| P1 | 流量与流域属性 | 补齐 FOEN 和 GKD 日流量；诊断失效与流量距平的关系；加入 air2stream-8 基准和 D2 流量特征；按河流类型分层 | 1–3 周 | RQ3 给出有水文含义的结论，或明确的阴性结果 |
| P1 | 现代基线 | SAITS/BRITS（已有适配器）、卡尔曼平滑、LSTM；可选 CSDI | 1–3 周 | 同一掩膜上的日尺度与下游指标对比表 |
| P1 | 多重插补式趋势区间 | 从联合模型抽取日路径，按 Rubin 规则合并 | 1–2 周 | 与现有三种耦合方式在同一批案例上比较覆盖率 |
| P1 | 随机数嵌套修复 | 改用 SeedSequence.spawn 或 Philox；给出蒙特卡洛标准误 | 1–2 天 | 删除 native 与 nested 的区分 |
| P1 | 群组推断 | wild cluster bootstrap 或混合效应模型 | 2–3 天 | 主要区间与现有群组自助法对照 |
| P1 | 资料稀缺消融 | 训练历史截短到 3/5/10 年，邻站减少到 0–1 个 | 3–5 天 | 给出适用边界曲线 |
| P1 | 强迫数据敏感性 | 用 E-OBS 或 ERA5-Land 替换；报告格点与站点高程差 | 3–5 天 | 判断 air-ridge 失效是否对强迫数据敏感 |
| P1 | H7 稳健性 | 在 SI 中报告 H7 下的关键结论 | 1–2 天 | 结论方向一致，或差异被如实报告 |
| P1（可选，最有分量） | 锁定确认 | OSF 登记假设，在新的公开站点上只运行一次 | 2–4 周 | 一张确认性结果表 |
| P2 | 结构重写 | 主文 6–8 图、3–4 表；SI 不超过 30 张表；设集中的 Limitations 节；加算法框和符号表 | 1–2 周 | 正文 7,000–8,000 词左右 |
| P2 | 图件 | 研究区地图、日过程案例图、CONSORT 流程图、Graphical abstract | 3–5 天 | 图件独立可读 |
| P2 | 文献 | 主文引用扩充到 40–60 篇（见次要意见 A4 和附录 B） | 2–3 天 | 引言和讨论与相关文献逐一对接 |

**时间有限时的最小可投稿版本：** 完成全部 P0 项，以及"实际意义重述"、"随机数嵌套修复"、P2 三项、流量的最低限度诊断，再加 SAITS/BRITS 与卡尔曼平滑两个基线。按一人全职估计，约需 4–6 周。

---

## 五、给作者的 EMS 版素材草案

下面的草案只在完成相应分析或软件交付后才能使用；带"待完成"标记的内容现在不能写进稿件。

### 标题候选

1. *Discard or reconstruct? A leakage-safe benchmark of gap handling for annual heat extremes and their trends in river-temperature archives*
2. *Screening versus reconstructing incomplete years: an open benchmarking framework for heat extremes in environmental monitoring records*

### Highlights 草案（均不超过 85 个字符，已计数）

- Joint whole-archive masking benchmarks year screening against reconstruction（76）
- Observed 30-day windows in incomplete years can exceed complete-year records（76）
- Under 30-90-day gaps, recovering all years cut H30 trend RMSE from 0.45 to 0.17（79）
- Under realistic gap calendars, screening errors stay below the trend's own noise（80；需先把附录 A 的分析写进论文）
- Open Python toolkit with leakage-safe group splits and interval calibration（75；待软件交付）

### 摘要草案（约 170 词，只使用已有结果和附录 A 的复算）

> Long-term analyses of river temperature commonly discard incomplete years, but how this screening affects annual heat extremes and their trends has rarely been quantified against reconstruction. We present an open, leakage-safe benchmarking framework that jointly masks multi-year station archives, reconstructs annual maxima of 30-day mean water temperature (H30) with distributional and stochastic models, and scores the resulting trends against complete-record references. Fully observed 30-day windows in incomplete years exceeded complete-year records at 20 of 96 long-record stations. Across 41 European and US stations, warm-season screening and full reconstruction gave trend RMSEs of 0.114 and 0.067 °C per decade under realistic gap calendars, both well below the trends' own sampling error (median 0.59 °C per decade). Under severe 30–90-day summer gaps, reconstruction reduced RMSE from 0.446 to 0.170 °C per decade; calendar-aware year selection helped at fixed counts but less than reconstruction. Interval undercoverage concentrated in air-temperature-based reconstructions in Bavaria. The framework, released as an open-source Python package, separates year-selection, reconstruction and Monte Carlo errors and applies to other incomplete environmental records.

最后一句需在软件交付后保留；如果加入了流量分析，应把倒数第二句改为对应结论。

### 建议的论文结构

1. Introduction：问题、现有做法、研究缺口，以及三条贡献。
2. Framework：用一张图串起整档案联合退化、年值恢复、选年和斜率评估，并说明泄漏控制。
3. Software implementation：架构图、API、测试与验证、计算成本。
4. Case study data and design：研究区地图、站点与流域属性、实际缺测特征。
5. Results，四个发现：
   - 观测窗口事实；
   - 筛年与重建的对比，以趋势标准误为尺度；
   - 何时失效，包括流量和河流类型；
   - 数值预算。
6. Discussion：实践决策表、与已有文献的比较、集中的 Limitations。
7. Conclusions。
8. Software and data availability。

### Software and data availability 模板

> **Software name:** [package], version [x.y.z]. **Developers:** [names]. **Contact:** [email]. **Year first available:** 2026. **Hardware required:** standard x86-64 computer; [RAM] GB RAM for the full replay [to be measured]. **Software required:** Python ≥ 3.10; dependencies pinned in `constraints.txt`. **Program language:** Python. **Program size:** [MB]. **Availability:** [GitHub URL]; archived at Zenodo [DOI]; reviewer access via [link]. **License:** MIT (code). **Cost:** free.
>
> **Data:** daily water temperature from FOEN, GKD Bayern, USGS NWIS, [other providers], under each provider's terms; NASA POWER meteorology. Observations from LUBW are subject to provider restrictions: [access route]. Processed annual tables required to reproduce all figures are archived at [DOI].

不要写 "available on request" 或 "contact the authors"。

---

## 附录 A：本报告新增的复算

脚本：[slope_signal_audit.py](slope_signal_audit.py)；输出：[slope_signal_audit.json](slope_signal_audit.json)。

脚本只读取 r4 已保存的 `reference_truths.csv`、`reference_year_sets.csv` 和 `retention_geometry_cases.csv`，不拟合任何新模型。复算的符号翻转数与稿件宏完全一致（经验日历：暖季规则 3、CDF 5、Sxx 4、全保留 0；控制缺口暖季规则 53），说明读表口径与作者相同。

运行命令（在仓库根目录）：

```bash
python docs/reviews/ems_dual_review_20261102/slope_signal_audit.py
```

**站点层面：完整记录的 H30 斜率（参考年份集合，OLS，单位 °C/10a）**

| 指标 | 数值 |
|---|---:|
| 站点数 | 41 |
| 参考年份数中位数 | 14 |
| 斜率中位数 | 0.754 |
| 斜率标准误中位数 | 0.59 |
| OLS p < 0.05 的站数 | 3 |
| Kendall p < 0.05 的站数 | 4 |
| \|OLS − Sen\| 中位数 | 0.102 |
| H30 年际标准差中位数（°C） | 1.01 |

**档案层面：斜率误差与该站斜率标准误之比**

| 队列 / 方案 | n | RMSE | 中位误差/SE | P90 误差/SE | 误差超过 1 SE 的比例 | 符号翻转 |
|---|---:|---:|---:|---:|---:|---:|
| 控制缺口 / 暖季 90% | 805 | 0.446 | 0.36 | 1.15 | 13.4% | 53 |
| 控制缺口 / CDF | 805 | 0.428 | 0.35 | 1.12 | 12.6% | 51 |
| 控制缺口 / Sxx | 805 | 0.402 | 0.32 | 1.00 | 9.9% | 42 |
| 控制缺口 / 全保留 | 805 | 0.170 | 0.11 | 0.46 | 0.75% | 16 |
| 经验日历 / 暖季 90% | 818 | 0.114 | 0.00 | 0.28 | 0.24% | 3 |
| 经验日历 / CDF | 818 | 0.098 | 0.00 | 0.20 | 0% | 5 |
| 经验日历 / Sxx | 818 | 0.086 | 0.00 | 0.17 | 0.12% | 4 |
| 经验日历 / 全保留 | 818 | 0.067 | 0.00 | 0.10 | 0.12% | 0 |

经验日历下误差中位数约为 0，是因为 530/818 个档案在两种方案下年份集合相同。

**限制：**

- 标准误按完整参考年份上的经典 OLS 公式计算，没有考虑序列自相关，所以是对真实不确定性的下限估计。
- 这些比值描述的是同一批已经打开过的模拟档案，不能当作新河流上的概率。

---

## 附录 B：审稿意见中提到的文献

只列作者、年份和刊物，引用前请核对卷期页码。

**水文与水温**

- Arismendi et al. (2014) *Environ. Res. Lett.*：用气温预测水温变化的局限。
- Beaufort et al. (2022) *HESS*。
- Cornes et al. (2018) *J. Geophys. Res. Atmos.*：E-OBS 集合版。
- Diaz, Oliver & Gorski (2025) *Environmental Modelling & Software* 193:106655：美国日水温机器学习预测，按过程类型评估覆盖率。
- Feigl et al. (2021) *HESS*：水温预测的机器学习方法比较。
- Gallice et al. (2015) *HESS*：瑞士无资料流域水温预测。
- Hamed & Rao (1998) *J. Hydrol.*：考虑自相关的 Mann–Kendall 检验。
- Hare et al. (2021) *Nat. Commun.*：大样本研究中的完整性筛选。
- Höge et al. (2023) *ESSD*：CAMELS-CH。
- Isaak et al. (2012) *Climatic Change*：利用重建估计长期水温趋势。
- Klingler, Schulz & Herrnegger (2021) *ESSD*：LamaH-CE。
- Lehner et al. (2011) *Front. Ecol. Environ.*：GRanD。
- Linke et al. (2019) *Sci. Data*：HydroATLAS。
- Loritz et al. (2024) *ESSD*：CAMELS-DE。
- Mohseni, Stefan & Erickson (1998) *WRR*。
- Muñoz-Sabater et al. (2021) *ESSD*：ERA5-Land。
- Orr et al. (2015) *Hydrol. Process.*。
- Rahmani et al. (2021) *Hydrol. Process.*：LSTM 水温模型。
- Toffolon & Piccolroaz (2015) *Environ. Res. Lett.*：air2stream。
- US EPA Region 10 (2003)：水温水质标准指南（7DADM）。
- van Vliet et al. (2011) *WRR*：流量对水温敏感性的影响。
- Webb et al. (2008) *Hydrol. Process.*。
- Yue et al. (2002) *Hydrol. Process.*：自相关对趋势检测的影响。
- Zwart et al. (2023) *Frontiers in Water*。

**机器学习、统计与软件**

- Angelopoulos et al. (2024) ICLR：共形风险控制。
- Barker et al. (2022) *Sci. Data*：FAIR4RS。
- Bennett et al. (2013) *EMS*：环境模型性能评价。
- Cameron, Gelbach & Miller (2008) *Rev. Econ. Stat.*：少聚类的 bootstrap。
- Cao et al. (2018) NeurIPS：BRITS。
- Chernozhukov, Fernández-Val & Galichon (2010) *Econometrica*：分位数重排。
- Du, Côté & Liu (2023) *Expert Syst. Appl.*：SAITS。
- Duan et al. (2020) ICML：NGBoost。
- Dwork et al. (2015) *Science*：可重用的保留集。
- Geifman & El-Yaniv (2017) NeurIPS：选择性预测。
- Gibbs & Candès (2021) NeurIPS：自适应共形推断。
- Gibbs, Cherian & Candès (2023) arXiv:2305.12616：带条件保证的共形预测。
- Hutton et al. (2016) *WRR*：计算水文学的可复现性。
- Jakeman, Letcher & Norton (2006) *EMS*：环境模型开发与评价的十个迭代步骤。
- Kapoor & Narayanan (2023) *Patterns*：机器学习科学中的数据泄漏。
- Little & Rubin (2019)：*Statistical Analysis with Missing Data*，第 3 版。
- Meinshausen (2006) *JMLR*：分位数回归森林。
- Meng (1994) *Stat. Sci.*：插补模型的相容性。
- Mitchell et al. (2019) FAT*：模型卡。
- Mölder et al. (2021) *F1000Research*：Snakemake。
- Moritz & Bartz-Beielstein (2017) *R Journal*：imputeTS。
- Roberts et al. (2017) *Ecography*：结构化数据的交叉验证。
- Romano, Patterson & Candès (2019) NeurIPS：CQR。
- Rubin (1987)：*Multiple Imputation for Nonresponse in Surveys*。
- Salmon et al. (2011) SC'11：计数型随机数生成器。
- Stekhoven & Bühlmann (2012) *Bioinformatics*：missForest。
- Tashiro et al. (2021) NeurIPS：CSDI。
- Tibshirani et al. (2019) NeurIPS：协变量漂移下的共形预测。
- van Buuren (2018)：*Flexible Imputation of Missing Data*。
