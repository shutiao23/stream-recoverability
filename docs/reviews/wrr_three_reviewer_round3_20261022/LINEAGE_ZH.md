# 这项研究从哪里来，为什么做，有什么意义

本文回答三个问题：这项工作是在哪些前人工作的基础上发展来的；为什么现在值得做；它的意义和真正的新意在哪里。文献来自 2026-10-22 的四路调研，条目都通过 DOI、Crossref、arXiv 或出版社页面核对过，个别只核到题名的已在文中注明。三位审稿人的意见见 [REVIEW_ZH.md](REVIEW_ZH.md)，下一步的详细安排见 [NEXT_STEPS_ZH.md](NEXT_STEPS_ZH.md)。

---

## 一、一句话

这项研究回答的是：河流水温档案里大量不完整的年份，能不能、以及应当怎样，用来计算年度热极值（最热连续 30 天平均水温，H30）和它的长期趋势。

它的答案由三部分组成：补全后直接取最大会低估热峰，这个偏差可以预测，也可以去掉大半；按完整度规则整年丢弃，丢掉的大多是能恢复的年份，保留它们能让趋势更准；如果一定要筛选，阈值应当跟着新区域的风险水平走，而不是固定在一个概率上。

---

## 二、它从哪里来：六条源流

这项工作不是从零开始的。它的每一个部件都能在前人工作中找到来源，新意在于把这些来源放到“年度热极值 + 不完整日资料”这个具体问题上，并做了系统的检验。下面逐条说明前人确立了什么、本研究继承了什么、又新增了什么。

### 源流 1：水文记录延展与方差保持（1964 年至今）

这是本研究最直接、也是目前稿件完全没有引用的来源。

- Matalas 和 Jacobs（1964，USGS Professional Paper 434-E）用回归加上与残差离散度相当的随机噪声来延长短记录，使延展后序列的均值和方差无偏。这本质上就是 1964 年的“随机回归补全”。
- Hirsch（1982，*WRR* 18:1081–1088）比较了四种流量记录延展方法，提出 MOVE.1（有机相关线）和 MOVE.2，指出普通回归和“回归加噪声”在矩、顺序统计量和历史低流量特征上都有严重缺陷。
- Vogel 和 Stedinger（1985，*WRR* 21:715–723）给出短记录均值和方差的最小方差增补估计，增补的对象是统计量本身而不是序列；Grygier、Stedinger 和 Yin（1989，*WRR*）把 MOVE 推广到多站并保持互相关。
- Moog、Whiting 和 Thomas（1999，*WRR* 35:243–254）明确指出，普通最小二乘给出的是“每一天的最优估计，而不是总体的最优描述”，因此低估方差；Box-Cox 形式的 MOVE 改善了顺序统计量和一个非线性泛函（累积推移质）的估计。这是与 H30 最接近的先例。
- 美国地调局（USGS）至今用 MOVE.1 估计部分记录站的低流量统计量（Ries 和 Friesz 2000，WRIR 00-4135；Eng 等 2011，*Hydrol. Process.* 25:2211–2220；Colarullo 等 2018，OFR 2018-1089）。
- USGS 的统计教科书（Helsel、Hirsch、Ryberg、Archfield 和 Gilroy 2020，*Statistical Methods in Water Resources*，TM 4-A3，§10.2.2）写得更直接：用最小二乘延展的值会按 r² 损失方差，洪水、干旱或超标事件的频率因此被低估；要“最好的单个值”用最小二乘，要“最好的一组值”用 MOVE。
- 补全方法对极值统计量影响的评估：Hughes 和 Smakhtin（1996，*HSJ*）的流量历时曲线等百分位补全；Harvey、Dixon 和 Hannaford（2012，*Hydrol. Res.*）比较了 15 种邻站补全方法；Khalil 和 Adamowski（2012，*HESS*）发现最小二乘低估高百分位、高估低百分位；Solanki 和 Mishra（2026，*WRR*）发现缺口使 50 年和 100 年一遇流量的估计偏移超过 40%。
- 在河温上，调研没有找到 MOVE 一类方法的应用。最接近的证据是 Arismendi 等（2014，*ERL* 9:084015）：以气温为自变量的河温回归“在所有站点都经常漏掉最冷和最热的时段”。

本研究继承了什么：plug-in 偏差的方向和成因（条件均值补全压缩方差），以及流量示范中 7 日最小流量偏高这一结论。后者在水文学中已经是教科书内容。

本研究新增了什么：缺口相对峰窗的位置如何控制“年窗口最大值”的偏差；把 (1 − R²)、AR(1) 持续性和窗口尺度的收缩合成一个闭式的失败律，并在不同缺口几何上检验；在大样本河温资料上量化偏差（气温补全、峰窗过半被遮时约 −0.47°C）；在统计量层面直接估计 H30 的分布。调研没有找到任何研究量化过补全对 H30、MWAT 或 7DADM 一类河温热指标的偏差。

### 源流 2：条件均值估计的平滑效应与条件模拟

- 地统计学很早就知道，克里金插值是条件均值，会抹平空间变异；凡是结果依赖变异性的非线性问题，都要用条件模拟（Journel 1974，*Econ. Geol.* 69:673–687；教科书见 Journel 和 Huijbregts 1978，Goovaerts 1997，Deutsch 和 Journel 1998，Chilès 和 Delfiner 2012）。
- 气候降尺度中有过一场“方差膨胀”之争：Karl 等（1990，*J. Climate*）提出膨胀回归结果的方差，von Storch（1999，*J. Climate* 12:3505–3506）反对膨胀，主张用加性的随机化方法；Maraun（2013，*J. Climate* 26:2137–2143）进一步指出分位数映射在时间结构、极值和趋势上重演了膨胀的问题，需要随机化的偏差校正。
- 网格化气候资料同样存在这个问题：Hofstra、New 和 McSweeney（2010，*Clim. Dyn.* 35:841–858）发现插值造成的平滑在高百分位最严重，会扭曲极端指数；Beguería 等（2016，*IJC*；2019，*J. Climate* 32:7797–7821）发现补全会使方差、极端分位数和趋势产生偏差，并且必须在“拟合优度”与“方差偏差”之间取舍。
- Farmer 和 Vogel（2016，*WRR* 52:5619–5633）指出忽略残差会扭曲分布，应当把残差以随机方式加回去。

本研究继承了什么：D2* 和条件模拟背后的思路——对模拟轨迹取泛函，而不是对条件均值序列取泛函。

本研究新增了什么：在年窗口极值上的具体实现，以及按缺口难度分层检验区间覆盖率。

### 源流 3：缺失数据理论与“保留并插补”

- Rubin（1976，*Biometrika* 63:581–592）定义了随机缺失和可忽略性；Rubin（1987）和 Little 与 Rubin（2019）系统阐述了多重插补，以及整例剔除的低效；van Buuren（2018，*Flexible Imputation of Missing Data*）强调“补全不是预测”。Barnard 和 Rubin（1999，*Biometrika*）给出了小样本自由度。
- 气候资料补全的代表是 Schneider（2001，*J. Climate* 14:853–871）的 RegEM：用岭回归迭代估计缺失值，得到的是条件均值。稿件中的邻站岭回归在性质上就是 RegEM 一类的方法。
- 缺测对趋势的影响已有不少研究：Slater 和 Villarini（2017，*IJC*）发现缺口越长、越远离序列中段，年最大值的趋势检出率越低；Schlegel 和 Smit（2016，*J. Climate*）发现缺测达到 5% 以上时第一类和第二类错误都会增加；Zhang 和 Post（2018，*HESS* 22:4593–4604）发现 10% 以内的缺测对年流量趋势影响很小；Teegavarapu 和 Nayak（2017，*J. Hydrol.*）发现补全资料会使趋势产生偏差，只核到摘要片段；Isaak 等（2012，*Climatic Change*）发现河温夏季趋势在原始资料和重建资料上分别为 0.17 和 0.22°C/10 年。

本研究继承了什么：多重插补优于整例剔除这一原则。

本研究新增了什么：在真实缺测日历下，量化“保留年份”和“改进估计器”各自对河温 H30 趋势的贡献（前者约占四分之三）；发现缺测随年代显著减少（每十年比值比约 0.68，调研没有找到已发表的同类估计），因此整年剔除会改变一个区域记录所描述的时期。

### 源流 4：资料完整度规则与河温资料实践

- 气候与水文的通用规则：WMO-1203（2017）的 11/5 规则；ETCCDI 指数的规则（Zhang 等 2011，*WIREs Climate Change*）；GSIM 的每年至少 350 天，作者自己称之为“非常保守”、可以放宽（Gudmundsson 等 2018，*ESSD* 10:787–804）；USGS 统计服务和 SWToolbox 的“季节内有缺测即不计算”（Kiang 等 2018，TM 4-A11）；USGS 河温指标数据发布的计天数规则（Johnson 2024）。
- 河温领域：Johnson 等（2021，*Ecol. Indic.* 122:107229）在完整年中插入缺口，发现连续缺测约 7 周以内对年参数可以接受，补全后可放宽到约 20 周；Beaufort 等（2022，*HESS* 26:3477–3495）提出“热峰”即 H30，并直接接受 7–8 月完整的年份；NorWeST 用 8 月至少 90% 的天数（Isaak 等 2017，*WRR*）；俄勒冈州在温度除名判定中要求关键期至少 80% 的天数；Sowder 和 Steel（2012，*Water*）、Dunham 等（2005）讨论了测温计的故障与资料清洗。
- 其他变量上处理不完整年份的做法：HYADES 用蒙特卡洛确定的阈值从不完整记录中提取年最大日降水，在 96.73% 的情况下取到真实最大值（Vargas Godoy、Papalexiou 和 Markonis 2024，*Sci. Data* 11:298）；Simpson 和 Northrop（2026，*Environmetrics* 37:e70075）在 GEV 中按每块的缺测比例调整参数；美国洪水频率分析的 Bulletin 17C 把不完整记录当作区间或删失资料处理（England 等 2019，TM 4-B5）。

本研究继承了什么：规则本身，以及“缺口时机比缺口长度更重要”的直觉（Johnson 等已经提出）。

本研究新增了什么：在同一实际风险下系统比较 15 条已发表规则；说明这些规则按天数而不是按目标统计量来判断；在真实缺测日历下，被规则丢掉的年份中有 74%–97% 能恢复到 0.5°C 以内。

### 源流 5：选择性预测、风险控制与无标签的风险估计

稿件的“标签无关阈值”看上去是新方法，但在统计学和机器学习中有完整的谱系。

- 根源：Chow（1970，*IEEE Trans. Inf. Theory* 16:41–46）证明最优拒绝规则就是对后验概率取阈值，而且只要后验概率正确，错误率–拒绝率曲线不需要标签就能算出。Newton 等（2004，*Biostatistics*）和 Sun 与 Cai（2007，*JASA* 102:901–912）给出了“按局部错误发现概率从小到大选择、直到运行平均达到 α”的规则——这正是稿件的选择方式。Saerens、Latinne 和 Decaestecker（2002，*Neural Computation* 14:21–41）用 EM 在无标签的新数据上估计基础比例的变化并修正后验概率。
- 无标签的性能估计：Hendrycks 和 Gimpel（2017，ICLR）的平均置信度是最基本的基线；Ovadia 等（2019，NeurIPS）发现分布偏移越大，校准越差；Guillory 等（2021，ICCV）的 DoC、Garg 等（2022，ICLR）的 ATC 都在多个偏移基准上显著改进，后者还证明，在一般情况下识别目标域精度与识别最优预测器一样难，任何方法都依赖对偏移的假设；Rosenfeld 和 Garg（2023，NeurIPS）发现点估计器在相当一部分偏移下会严重低估误差。与稿件最接近的已发表工作是 Kivimäki 等（2025，*JAIR* 82:209–240）的置信度估计器（只要分数在被监测的资料上是校准的，平均置信度就无偏）和 Białek 等（2025，NeurIPS）的 PAPE（用密度比重新校准后再做平均置信度估计，同样基于梯度提升树）。
- 有保证的风险控制：Geifman 和 El-Yaniv（2017，NeurIPS）的 SGR；Learn-then-Test（Angelopoulos 等 2025，*Ann. Appl. Stat.* 19:1641–1662）与保形风险控制（2024，ICLR）；加权保形（Tibshirani 等 2019，NeurIPS）；保形选择（Jin 和 Candès 2023，*JMLR*；2025，*Biometrika*，协变量偏移下）。预测驱动推断（Angelopoulos、Bates、Fannjiang、Jordan 和 Zrnic 2023，*Science* 382:669–674）及其扩展说明，少量标签加大量预测就能得到有效的区间；Einbinder、Ringel 和 Romano（2025，*IEEE TPAMI*）把它用于半监督的风险控制。
- 组层面的保证：Jones 等（2021，ICLR）发现选择性预测在提高平均准确率的同时可能让某些组更差；Gibbs、Cherian 和 Candès（2025，*JRSS-B* 87:1100–1126）给出对重叠组同时有效的覆盖保证；Dunn、Wasserman 和 Ramdas（2023，*JASA*）与 Duchi 等（2025，*Stat. Sci.*）讨论了新的组或新环境上的有效性。

本研究的规则在这个谱系中的位置：平均置信度估计 + 运行均值的局部错误发现规则 + 一个用留一区域经验确定的安全系数 k。它没有有限样本保证；它的有效性依赖分数在新区域的校准，而这一点没有标签就无法检验。按可交换性推断，k 取源域各区域“实际与预测之比”的第 80 百分位数，大致相当于对一个与源域可交换的新区域有约八成把握，而不是 95%。

本研究新增了什么：把这类规则用于回归误差的超阈事件；用留一区域确定安全系数，并在冻结后的新站上做了一次设计有效的检验；如实报告了局部超标（一个独立组 43%，一个二级流域 8.4%）。需要说明的是，由于随机种子的生成方式已经按要求改为普通整数，所有病例都将重新生成，而那两批资料已经读过，这次检验在重跑后不再是独立检验，需要在新资料上重做（见 [NEXT_STEPS_ZH.md](NEXT_STEPS_ZH.md)）。

### 源流 6：按下游任务评价补全，以及水文中的不确定性量化

- 补全的价值取决于下游任务：Le Morvan 等（2021，NeurIPS）、Wang 等（2024，NeurIPS）、Shadbahr 等（2023，*Commun. Med.*）；Näf 等（2023，*Ann. Appl. Stat.*）指出“遮盖后算平方误差”偏爱条件均值补全；Zaffran 等（2023，ICML）发现先补全再做保形预测时，整体覆盖成立，但特定缺测模式下覆盖不足。
- 水文中的不确定性量化：Klotz 等（2022，*HESS* 26:1673–1693）的基准方案；Auer 等（2024，*HESS* 28:4099–4126）用保形区间发现只用本地信息在洪峰上会失败；Zwart 等（2023，*Front. Water*）发现区间在有测站河段接近名义水平、在无测站河段过于自信；Diaz、Oliver 和 Gorski（2025，*EMS* 193:106655）的全美日河温产品 90% 区间覆盖 90.7%，并评估了年最高 7 日均温（R² 0.76）——这是年度热指标上最接近的竞争工作；Baste 等（2026，*HESS*）发现确定性 LSTM 低估 97% 的最大流量事件；Saadi 等（2026，*HESS*）研究了 LSTM 对河温极值的改进。
- 深度学习补全：Fankhauser、Bigler 和 Riesen（2024，ICPRAM）在瑞士 81 站上用 LSTM 补全水温，只报告 RMSE；Bhavsar 等（2026，arXiv:2607.21200）用扩散模型补全包括水温在内的水文序列，没有评估年极值或趋势；Yang 等（2026，*WRR*）用扩散模型做小时流量的预测与同化。
- 重尾误差的建模：Schoups 和 Vrugt（2010，*WRR*）的广义似然（偏态、重尾）；McInerney 等（2017，*WRR*）的异方差残差；Velthoen 等（2023，*Extremes*）的极端分位数提升树；Pasche 和 Engelke（2024，*Ann. Appl. Stat.*）的极端分位数神经网络；Pasche、Lam 和 Engelke（2025，arXiv:2505.08578）的极端保形预测。

本研究继承了什么：“目标特异性”的原则，以及按条件分层评价覆盖率的做法。

本研究新增了什么：把这一原则用到河温年极值上，并检验区间在缺口难度各层的覆盖。调研没有找到把保形方法用于河温的已发表研究，也没有找到为年度派生统计量报告校准区间的深度学习补全研究。

---

## 三、为什么现在做

第一，河温研究正处在一个快速增长期，而它们共同的瓶颈正是资料不完整。2023–2026 年，河流升温和河流热浪的研究接连发表在 *Nature Climate Change*、*PNAS*、*Nature Communications*、*Nature Water* 和 *WRR* 上：Zhi 等（2023）、Tassone 等（2023，*L&O Letters*）、van Vliet 等（2023，*Nat. Rev. Earth Environ.*）、Ficklin 等（2023，*Nature Water*）、van Hamel 与 Brunner（2024）及其后续工作（2025 *Nature Water*，2026 *Commun. Earth Environ.*）、Sadayappan 与 Li（2025，*PNAS*）、Chen 等（2026，*Nat. Commun.*）。这些研究的作者自己指出了瓶颈：Chen 等写道，由于缺少长期的实测日水温，全球河流热浪的模拟指标无法直接用观测验证；Sadayappan 与 Li 写道，分析受到“碎片化资料”的阻碍；IPCC AR6 第二工作组第 4 章指出，全球水质变化的证据有限，因为许多研究彼此孤立、区域覆盖有限。

第二，现有研究处理不完整年份的方式各不相同，而且大多是两种极端。一种是自定阈值整年剔除：Michel 等（2020）只用完整日历年且缺口不超过两周；Hare 等（2021，*Nat. Commun.*）要求连续两年无 30 天以上缺口，趋势只在完整年超过 14 年的站上计算，1,424 个站中只剩 197 个；Isaak 等（2018）要求至少 70% 的天数；Rahmani 等（2021）要求 60% 以上；Tassone 等（2023）的代码要求至少 90%；van Hamel 与 Brunner（2024）要求至少 5 个完整年；Chen 等（2026）要求 75% 以上有效，最后只用了 76 个 USGS 站。另一种是用模型重建替代观测：Zhi 等（2023）、Sadayappan 与 Li（2025）用 LSTM 重建的日序列计算趋势和热浪，没有逐年检查哪些年份真的可以恢复。最接近“保留并带上不确定性”的先例是 Daigle 和 Légaré（2024，*HSJ*）在魁北克合并多源资料时评估了不确定性，以及 Bal 和 de Eyto（2023，*PLoS ONE*）的贝叶斯河温重建。

第三，大型数据集正在出现，但都没有回答“哪一年能用”。TempER 汇集了 26 个欧洲国家 4,757 个站、最长 72 年的日水温（EGU 2026 摘要，尚无数据论文）；Caravan-Qual、USGS 多机构汇编（Oliver 等 2024）、CAMELS-CH-Chem（do Nascimento 等 2025）都没有给出逐年的可恢复性标记或不确定性。

第四，管理决策直接依赖年度热极值。瑞士《水体保护条例》附件 2 规定水温不得超过 25°C、鳟鱼河段增温不超过 1.5°C；2025 年 6 月阿勒河在贝兹瑙核电站下游达到 25°C，两台机组被要求降到约 50% 出力。德国 2016 年《地表水条例》按鱼类群落规定夏季最高温（20–28°C）；法国 2010 年的分级用资料序列的第 90 百分位数；俄勒冈州的 303(d) 列名使用 7 日平均最高温标准，并有一条以第 90 百分位界定异常炎热年份的“气温排除”条款；欧盟《水框架指令》把热状况列为支持性要素。

把这几点放在一起：领域公认资料不完整是瓶颈；现有做法要么丢掉大量年份，要么用没有经过逐年检验的重建替代观测；而管理和科学结论都依赖年度热极值。一个有检验、带不确定性的“保留可恢复年份”的方法，正好回应这个瓶颈。

---

## 四、它的意义

**对科学结论。** 在缺测随年代减少的档案里，整年剔除会系统性地丢掉早期年份，改变一个区域记录描述的时期。巴登-符腾堡就是一个例子：只有 27% 的站年完整，2003 年有资料的 17 个站无一完整，只用完整年时区域趋势约 0.72°C/10 年，纳入不完整年后约 0.32–0.35°C/10 年，而且 2003 年从记录中消失。对全国或全大陆尺度的研究，保留可恢复年份意味着能用的站数会成倍增加（这一点需要用实验证明，见下一步计划）。

**对资料使用者和机构。** 完整度规则应当按目标统计量来定，而不是统一数天数；能估计的年份应当估计并带上区间，而不是丢弃；需要筛选时，阈值应当随新区域的风险水平调整。恢复律可以作为“这类缺口在这类站上是否危险”的事前预警。

**对方法学。** 把水文记录延展的经典传统（MOVE 及其后续）与现代的分布无关推断、无标签性能估计接起来；在环境资料上示范预注册、冻结后在新资料上检验的做法。这一做法在机器学习基准中也不常见。

---

## 五、新意的准确表述

### 对照表

| 部件 | 前人已有 | 本研究新增 | 证据现状 |
|---|---|---|---|
| plug-in 低估热峰 | 回归延展压缩方差，极值被低估（Matalas 和 Jacobs 1964；Hirsch 1982；Helsel 等 2020）；平滑效应（地统计、降尺度） | 峰窗位置对年窗口最大值偏差的控制；河温大样本量化 | 源域与新站都强 |
| 恢复律 | 自相关序列均值的方差、(1 − R²) 都是经典结果 | 把两者与窗口尺度收缩合成闭式失败律，并在缺口几何上检验 | 能预测失败率的分布；在最难条件下低估（重尾） |
| 目标感知估计 D2* | 条件模拟、统计量层面的增补（Vogel 和 Stedinger 1985） | H30 误差分位数的直接回归，按难度分层校正区间 | 偏差修正强；区间为近似校准 |
| 规则比较 | 各类完整度规则；Johnson 等 2021 | 15 条规则在同风险下比较；被丢年份中 74%–97% 可恢复 | 强 |
| 保留并多重插补 | 缺失数据理论；趋势受缺测影响的研究 | 把趋势改善拆成“保留年份”和“估计器”两部分 | 强；单站检出上差别很小 |
| 标签无关阈值 | 平均置信度、局部错误发现规则、Saerens 的先验修正、PAPE | 用于回归误差超阈事件；留一区域安全系数；冻结后检验 | 曾通过一次检验；种子改动后需在新资料上重做 |
| 流量示范 | MOVE 正是为低流量统计量而发展的 | 在真实缺测日历下的跨变量确认 | 机制成立，估计器帮助有限 |

### 建议写进引言的新意段落（英文草稿）

> Regression-based record extension is known to shrink variance and bias extreme statistics, which is why hydrologists developed variance-preserving extension for low-flow statistics (Matalas & Jacobs, 1964; Hirsch, 1982; Helsel et al., 2020), and multiple imputation is the standard alternative to discarding incomplete records (Rubin, 1987). What has not been established is how these principles play out for annual thermal extremes computed from incomplete daily river-temperature records, where the statistic is a maximum over a window whose position is itself uncertain. We show that the bias of the filled-series maximum is governed by the share of the peak window that is hidden and by the persistence of the reconstruction error, derive a closed-form law that predicts where it fails, compare fifteen published completeness rules at equal risk, separate the benefit of keeping years from the benefit of better estimation, and test a label-free admission threshold on stations that were not used to build it.

---

## 参考文献

以下按主题排列，列出本文提到的主要文献。带 DOI 的条目都已在 2026-10-22 核对；书籍与机构报告给出出处；“只核到题名”的已在正文注明。

**记录延展与方差保持**
- Matalas, N. C., & Jacobs, B. (1964). A correlation procedure for augmenting hydrologic data. USGS Professional Paper 434-E. https://doi.org/10.3133/pp434E
- Hirsch, R. M. (1982). A comparison of four streamflow record extension techniques. *WRR*, 18(4), 1081–1088. https://doi.org/10.1029/WR018i004p01081
- Vogel, R. M., & Stedinger, J. R. (1985). Minimum variance streamflow record augmentation procedures. *WRR*, 21(5), 715–723. https://doi.org/10.1029/WR021i005p00715
- Grygier, J. C., Stedinger, J. R., & Yin, H.-B. (1989). A generalized maintenance of variance extension procedure for extending correlated series. *WRR*, 25(3), 345–349. https://doi.org/10.1029/WR025i003p00345
- Moog, Whiting, & Thomas (1999). *WRR*, 35(1), 243–254. https://doi.org/10.1029/1998WR900014
- Ries & Friesz (2000). USGS WRIR 00-4135. https://doi.org/10.3133/wri004135
- Eng et al. (2011). *Hydrological Processes*, 25, 2211–2220. https://doi.org/10.1002/hyp.7976
- Colarullo et al. (2018). USGS OFR 2018-1089. https://doi.org/10.3133/ofr20181089
- Helsel, D. R., Hirsch, R. M., Ryberg, K. R., Archfield, S. A., & Gilroy, E. J. (2020). *Statistical Methods in Water Resources*. USGS TM 4-A3. https://doi.org/10.3133/tm4A3
- Hughes & Smakhtin (1996). *HSJ*, 41(6), 851–871. https://doi.org/10.1080/02626669609491555
- Harvey, Dixon, & Hannaford (2012). *Hydrology Research*, 43(5), 618–636. https://doi.org/10.2166/nh.2012.110
- Khalil & Adamowski (2012). *HESS*, 16, 2253–2266. https://doi.org/10.5194/hess-16-2253-2012
- Solanki, H., & Mishra, V. (2026). Filling streamflow data gaps in Indian catchments using machine learning and K-means clustering. *WRR*, 62, e2025WR042210. https://doi.org/10.1029/2025WR042210
- Arismendi, I., Safeeq, M., Dunham, J. B., & Johnson, S. L. (2014). *ERL*, 9, 084015. https://doi.org/10.1088/1748-9326/9/8/084015

**平滑效应与随机化**
- Journel, A. G. (1974). Geostatistics for conditional simulation of ore bodies. *Economic Geology*, 69(5), 673–687. https://doi.org/10.2113/gsecongeo.69.5.673
- Goovaerts, P. (1997). *Geostatistics for Natural Resources Evaluation*. Oxford University Press.
- Karl, T. R., et al. (1990). *J. Climate*, 3(10), 1053–1079. https://doi.org/10.1175/1520-0442(1990)003<1053:AMORGC>2.0.CO;2
- von Storch, H. (1999). On the use of "inflation" in statistical downscaling. *J. Climate*, 12(12), 3505–3506. https://doi.org/10.1175/1520-0442(1999)012<3505:OTUOII>2.0.CO;2
- Maraun, D. (2013). *J. Climate*, 26(6), 2137–2143. https://doi.org/10.1175/JCLI-D-12-00821.1
- Hofstra, N., New, M., & McSweeney, C. (2010). *Climate Dynamics*, 35(5), 841–858. https://doi.org/10.1007/s00382-009-0698-1
- Beguería, S., et al. (2019). *J. Climate*, 32(22), 7797–7821. https://doi.org/10.1175/JCLI-D-19-0244.1
- Farmer, W. H., & Vogel, R. M. (2016). *WRR*, 52(7), 5619–5633. https://doi.org/10.1002/2016WR019129

**缺失数据与趋势**
- Rubin, D. B. (1976). Inference and missing data. *Biometrika*, 63(3), 581–592. https://doi.org/10.1093/biomet/63.3.581
- Little, R. J. A., & Rubin, D. B. (2019). *Statistical Analysis with Missing Data* (3rd ed.). Wiley. https://doi.org/10.1002/9781119482260
- Schneider, T. (2001). Analysis of incomplete climate data. *J. Climate*, 14(5), 853–871. https://doi.org/10.1175/1520-0442(2001)014<0853:AOICDE>2.0.CO;2
- Slater, L. J., & Villarini, G. (2017). *IJC*, 37(10), 3976–3983. https://doi.org/10.1002/joc.4954
- Schlegel, R. W., & Smit, A. J. (2016). *J. Climate*, 29(24), 9113–9124. https://doi.org/10.1175/JCLI-D-16-0014.1
- Zhang, Y., & Post, D. (2018). How good are hydrological models for gap-filling streamflow data? *HESS*, 22, 4593–4604. https://doi.org/10.5194/hess-22-4593-2018
- Isaak, D. J., et al. (2012). *Climatic Change*, 113(2), 499–524. https://doi.org/10.1007/s10584-011-0326-z

**完整度规则与不完整记录**
- Johnson, Z. C., et al. (2021). Heed the data gap. *Ecological Indicators*, 122, 107229. https://doi.org/10.1016/j.ecolind.2020.107229
- Beaufort, A., Diamond, J. S., Sauquet, E., & Moatar, F. (2022). *HESS*, 26, 3477–3495. https://doi.org/10.5194/hess-26-3477-2022
- Gudmundsson, L., Do, H. X., Leonard, M., & Westra, S. (2018). *ESSD*, 10, 787–804. https://doi.org/10.5194/essd-10-787-2018
- Vargas Godoy, Papalexiou, & Markonis (2024). HYADES. *Scientific Data*, 11, 298. https://doi.org/10.1038/s41597-024-03109-2
- Simpson & Northrop (2026). Accounting for missing data when modelling block maxima. *Environmetrics*, 37, e70075. https://doi.org/10.1002/env.70075
- England, J. F., et al. (2019). Bulletin 17C. USGS TM 4-B5. https://doi.org/10.3133/tm4B5

**无标签风险估计与风险控制**
- Chow, C. K. (1970). *IEEE Trans. Inf. Theory*, 16(1), 41–46. https://doi.org/10.1109/TIT.1970.1054406
- Sun, W., & Cai, T. T. (2007). *JASA*, 102(479), 901–912. https://doi.org/10.1198/016214507000000545
- Saerens, M., Latinne, P., & Decaestecker, C. (2002). *Neural Computation*, 14(1), 21–41. https://doi.org/10.1162/089976602753284446
- Hendrycks, D., & Gimpel, K. (2017). ICLR. arXiv:1610.02136
- Ovadia, Y., et al. (2019). NeurIPS. arXiv:1906.02530
- Guillory, D., et al. (2021). ICCV, 1114–1124. https://doi.org/10.1109/ICCV48922.2021.00117
- Garg, S., et al. (2022). ICLR. arXiv:2201.04234
- Rosenfeld, E., & Garg, S. (2023). NeurIPS. arXiv:2306.00312
- Kivimäki, J., et al. (2025). *JAIR*, 82, 209–240. https://doi.org/10.1613/jair.1.16709
- Białek, J., et al. (2025). NeurIPS. arXiv:2401.08348
- Angelopoulos, A. N., Bates, S., Fannjiang, C., Jordan, M. I., & Zrnic, T. (2023). Prediction-powered inference. *Science*, 382(6671), 669–674. https://doi.org/10.1126/science.adi6000
- Einbinder, Ringel, & Romano (2025). *IEEE TPAMI*, 47(12), 11080–11090. https://doi.org/10.1109/TPAMI.2025.3594263
- Jin, Y., & Candès, E. J. (2023). Selection by prediction with conformal p-values. *JMLR*, 24(244). arXiv:2210.01408
- Gibbs, I., Cherian, J. J., & Candès, E. J. (2025). *JRSS-B*, 87(4), 1100–1126. https://doi.org/10.1093/jrsssb/qkaf008
- Duchi, J. C., et al. (2025). *Statistical Science*, 40(3), 392–416. https://doi.org/10.1214/24-STS973

**意义与使用者**
- Hare, Helton, Johnson, Lane, & Briggs (2021). *Nature Communications*, 12, 1450. https://doi.org/10.1038/s41467-021-21651-0
- Tassone et al. (2023). *Limnology and Oceanography Letters*, 8, 295–304. https://doi.org/10.1002/lol2.10284
- Zhi, W., Klingler, C., Liu, J., & Li, L. (2023). *Nature Climate Change*, 13, 1105–1113. https://doi.org/10.1038/s41558-023-01793-3
- van Vliet, M. T. H., et al. (2023). *Nature Reviews Earth & Environment*, 4, 687–702. https://doi.org/10.1038/s43017-023-00472-3
- Ficklin et al. (2023). *Nature Water*, 1, 125–128. https://doi.org/10.1038/s44221-023-00027-2
- van Hamel, A., & Brunner, M. I. (2024). *WRR*, 60, e2024WR037518. https://doi.org/10.1029/2024WR037518
- Sadayappan & Li (2025). *PNAS*, 122, e2503160122. https://doi.org/10.1073/pnas.2503160122
- Chen, Y., et al. (2026). *Nature Communications*, 17, 94. https://doi.org/10.1038/s41467-025-66868-5
- Daigle & Légaré (2024). *Hydrological Sciences Journal*, 69, 2214–2226. https://doi.org/10.1080/02626667.2024.2402946
- Bal, G., & de Eyto, E. (2023). Simple Bayesian reconstruction and forecasting of stream water temperature for ecologists. *PLoS ONE*, 18, e0291239. https://doi.org/10.1371/journal.pone.0291239
- Diaz, J. A., Oliver, S. K., & Gorski, G. (2025). *Environmental Modelling & Software*, 193, 106655. https://doi.org/10.1016/j.envsoft.2025.106655
- Caretta, M. A., et al. (2022). Water. IPCC AR6 WGII, Chapter 4. https://doi.org/10.1017/9781009325844.006

**不确定性量化与重尾**
- Klotz, D., et al. (2022). *HESS*, 26, 1673–1693. https://doi.org/10.5194/hess-26-1673-2022
- Auer et al. (2024). *HESS*, 28, 4099–4126. https://doi.org/10.5194/hess-28-4099-2024
- Zwart, J. A., et al. (2023). *Frontiers in Water*, 5, 1184992. https://doi.org/10.3389/frwa.2023.1184992
- Zaffran, M., Dieuleveut, A., Josse, J., & Romano, Y. (2023). Conformal prediction with missing values. ICML. arXiv:2306.02732
- Schoups, G., & Vrugt, J. A. (2010). A formal likelihood function for parameter and predictive inference of hydrologic models with correlated, heteroscedastic, and non-Gaussian errors. *WRR*, 46. https://doi.org/10.1029/2009WR008933
- McInerney, D., et al. (2017). *WRR*, 53, 2199–2239. https://doi.org/10.1002/2016WR019168
- Velthoen, J., et al. (2023). Gradient boosting for extreme quantile regression. *Extremes*, 26, 639–667. https://doi.org/10.1007/s10687-023-00473-x
- Pasche & Engelke (2024). *Ann. Appl. Stat.*, 18, 2818–2839. https://doi.org/10.1214/24-AOAS1907
