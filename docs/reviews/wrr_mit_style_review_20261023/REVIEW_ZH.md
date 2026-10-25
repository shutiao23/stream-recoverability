# WRR 模拟审稿意见（第四轮：对抗式重读）

稿件：*Incomplete river-temperature years are more useful than completeness rules assume*（Water Resources Research，Research Article）

配套文件：[核算记录](AUDIT_ZH.md)、[改进计划](NEXT_STEPS_ZH.md)。前几轮意见见 [第一轮](../wrr_mit_style_review_20261021/REVIEW_ZH.md)、[第二轮](../wrr_mit_style_review_20261022/REVIEW_ZH.md)、[第三轮（三位审稿人）](../wrr_three_reviewer_round3_20261022/REVIEW_ZH.md) 和 [研究脉络](../wrr_three_reviewer_round3_20261022/LINEAGE_ZH.md)。

---

## 审稿设置

本轮按 MIT 土木与环境工程系一位长期从事水文统计与不确定性量化的资深教授的标准审阅，方式是对抗式重读。我不评价文字和代码，只问一件事：作者的设计能不能证明作者所主张的东西，以及它是否比更简单的做法更好。

审阅对象是 2026-10-22 晚、随机种子改为普通整数并全部重算之后的稿件、补充材料和结果文件。第三轮三位审稿人提出的意见（记录延展的谱系与 MOVE 对照、标签无关阈值的谱系、失败地图、选站实验等）仍然有效，而且稿件尚未处理；本轮不再逐条重复，只在需要时引用。本轮的新意见主要来自我对病例级结果的重新核算，口径和数字见 [AUDIT_ZH.md](AUDIT_ZH.md)。第四节把同类问题在国际顶级团队中通行的实验要求与本稿对照。

---

## 一、投稿结果预判

| 结果 | 概率 |
|---|---:|
| 编辑直接拒稿 | 约 15% |
| 送审后拒稿 | 约 35% |
| 大修 | 约 45% |
| 小修或接收 | 约 5% |

这是我个人的判断，不是编辑部的数据。

不至于直接拒稿的理由：题目是 WRR 的读者关心的问题，资料规模大，结论对资料使用者和机构有直接用处，稿件对未通过的终点照实报告，编辑会愿意送审。

送审后被拒的风险比上一轮高。原因有五。第一，稿件唯一的迁移证据——两次附加资料集上的评估——在随机数改动之后已经不是盲测，稿件自己也这样承认。第二，第一份预注册的主要终点 P1 已经翻为“未通过”，而且翻转只是因为换了一组随机数，这会让统计审稿人怀疑其他“通过”的终点同样脆弱。第三，水文审稿人会认为“回归补全压缩极值”是 MOVE 一系四十年前就解决的问题，而稿件至今没有引用这一传统，也没有与 MOVE.1 比较。第四，一位仔细的统计审稿人会发现，本文推荐的筛选规则会放行模型自己认为大概率出错的单个值（真实档案中最高 0.73），并让约四分之一的放行病例落在实际风险超过 7% 的组里。第五，稿件证明了“误差变小”，但没有证明哪一个科学结论因此改变。

最可能的结果是：两位审稿人建议大修，一位建议拒稿，编辑给出大修。

---

## 二、审稿意见

### 总体评价

这篇稿件研究河流水温档案中的不完整年份：是按完整度规则丢弃，还是补全后计算年度热极值（最热连续 30 天平均水温，H30）。作者在 581 个站、6,170 个完整站年上，把真实的缺测日历和受控的长缺口移植到完整年份上，比较了 15 条已发表的规则、六类估计器、一个只用训练期信息的“恢复律”、一个用于判断估计值能否使用的标签无关阈值，以及丢弃与保留两种做法对站点升温趋势的影响，最后在澳大利亚和 70 个新的 USGS 站上检验了阈值的迁移，并用年 7 日最小流量做了一次跨变量的示范。

我认为这项工作最有价值的发现有三个，而且都很扎实。一是缺测与炎热只有弱关联，但随年代显著减少（每十年比值比约 0.68），所以整年丢弃会系统性地丢掉早期年份。二是已发表的完整度规则丢掉了大量能恢复的年份：在真实缺测日历下，被拒的年份中 77%–98% 用分布回归可以恢复到 0.5°C 以内，即使只用 plug-in 补全也有 71%–97%。三是 plug-in 补全在峰窗被遮时偏冷，而且偏冷的程度取决于信息层：气温层补全的中位 R² 只有 0.57，邻站层为 0.82。

但我重新核算病例级结果之后，得出的结论是：这篇稿件证明了“应当保留不完整年份”，也证明了“峰窗被遮时补全会偏冷”，却还没有证明它自己的设计——分布回归估计器 D2*、恢复律和标签无关阈值——是必要的，或者比更简单的做法更好。问题不在实验做得少，而在实验的重心与问题的重心不一致：真正危险的年份只占不完整年份的一小部分，而且在交付前就能用一个特征认出来；在这一小部分年份里，任何估计器都无法达到 0.5°C 的容差；在其余大部分年份里，最简单的补全就已经足够。下面逐条说明。

### 这篇稿件已经站住的部分

缺测机制的审计是认真做的：站点固定效应的条件 logit、时间分层的病例交叉设计、低流量指标、热夏对照，结论有说服力，边界也写清楚了。15 条规则在同一实际风险下的比较，是这一领域我没有见过的工作，它对资料使用者的价值不依赖于本文的其他部件。保留年份对趋势有利这一点，方向在两次运行中都稳定。巴登-符腾堡的例子说明了一个过去很少被讨论的后果：只有 27% 的站年完整，2003 年有资料的 17 个站无一完整，完整年规则会改变一个区域记录所描述的时期。作者把未通过的 P2、P3 照实报告，把附加资料集上的评估改写为“不再是盲测”，这种诚实值得肯定。

### 主要问题

#### 1. 问题的重心与 Design 的重心不一致

我按交付时就能算出的“气候峰窗被遮比例”，把档案中约 4,000 个真实的不完整站年分了层（核算第 1 节）。73.5% 的缺口完全不碰气候峰窗，19.3% 遮住不到一半，只有 7.2% 遮住一半以上，其中由气温层补全的只有 4.0%。在源域的真实日历病例上，这三层的失败率分别是：plug-in 为 0.3%、3.1% 和 36.2%；D2* 为 0.2%、1.6% 和 29.7%。D2* 在真实日历下的全部失败中，86% 落在最后一层。

这组数字说明了三件事。第一，对四分之三以上的不完整年份，任何合理的补全都给出正确的 H30，这里不需要任何复杂的设计。第二，真正的危险集中在约 8% 的年份里，而且这些年份在交付前就能认出来。第三，在这 8% 的年份里，最好的估计器仍有 30% 的失败率，90% 区间的平均宽度是 1.65°C，是容差的三倍多。换句话说，这些年份的 H30 用现有的可见信息恢复不到 0.5°C；对它们而言，最有价值的不是一个更好的点估计，而是一个诚实的“不能恢复”的标记。

最能说明问题的是一个平凡的对照：只按“气候峰窗被遮是否少于一半”这一个特征筛选，就能使用 93.3% 的不完整年份，交付 plug-in 值时实际风险只有 0.65%，交付 D2* 值时 0.33%（核算第 2 节，按机构加权，与表 2 同口径）。它的留存高于表 2 中的每一条已发表规则；在同样交付 plug-in 值时，表现最好的峰值时段规则与它相当（锚定站点峰值的俄勒冈式规则留存 89.5%、风险 0.33%，“暖季最长缺口不超过 30 天”留存 90.5%、风险 0.60%）。这说明在真实日历下，起作用的只是“缺口是否遮住峰窗”这一个信息，最好的峰值时段规则已经近似地用到了它；被大量浪费的，主要是只数天数的规则（USGS 指标规则 55%、WMO 45%、ETCCDI 36%）。在这一总体里，学习出来的部件没有施展的余地。在受控长缺口下，它们确实有增量：5% 风险处，单特征规则使用 60% 的病例，恢复律 75%，R7b 81%，oracle 93%；而在真实日历下，四者都使用 100%。

所以我要求作者：(1) 把单特征规则加入表 2、图 4 和所有风险–留存比较，作为任何学习部件都必须打败的最低基线；(2) 用真实不完整年份中各层的比例加权，报告每一种做法在档案层面的效果，例如“每 1,000 个不完整站年中的预期失败数”，以及恢复律和 R7b 相对单特征规则改变了多少个站年的判断；(3) 重新组织论文的主线：先说明风险高度集中、交付前可识别，再说明危险年份能恢复多少、不能恢复多少，最后说明学习部件在哪些情形下比单特征规则多出价值。按这个结构，D2* 和恢复律的位置会比现在清楚得多，也更容易被接受。

#### 2. 主要终点量错了 Design 的价值

P1 的定义是“气温层、真实峰窗至少一半被遮的病例中，D2* 相对 plug-in 的平均有符号偏差降幅”。这个终点无法区分 D2* 和一张查表。我做了一个最简单的对照：对每个病例，减去其他区域中同一决策时格子（缺口长度 × 峰窗被遮五档 × 信息层）的平均误差（核算第 4 节）。在 P1 层，它把偏差从 −0.47°C 降到 −0.11°C，降幅 76%；D2* 是 −0.12°C，降幅 75%。也就是说，一张几十个数的查表就能通过 P1 的偏差门槛。

D2* 和查表的差别在病例层面：P1 层的平均绝对误差 0.46°C 对 0.64°C，失败率 32% 对 47%。这才是 D2* 的价值，但稿件没有把它当作主要证据。更重要的是，同样在病例层面，泛函去偏 P2（一个梯度提升回归，直接预测 plug-in 的误差）与 D2* 几乎打平：MAE 0.460°C 对 0.456°C，失败率 33.1% 对 32.4%；在真实日历的危险层也是 32.3% 对 29.7%。所以 D2* 相对一个简单得多的去偏方法，增量只剩区间；而区间按预注册的口径是不合格的（P1 覆盖率 84.8%，下限 85%），校正之后在危险层是 88%，宽度 1.65°C。

不过，有一类年份里学习的去偏确实重要，而稿件没有把它单独拿出来：交付时气温就显示为热年的危险年份（核算第 10 节）。在这些年份里，plug-in 的冷偏差明显加重（真实日历 −0.50°C，其他年份 −0.22°C），失败率 48%；P2 把偏差降到 −0.10°C、失败率 41%，D2* 为 −0.14°C、35%，区间覆盖 85%。这正是热浪研究最关心的年份，也是第三轮审稿人 C 要求的“单年演示”所需要的证据。作者应当把它作为估计器价值的主要例证，并说明样本只有 210 个真实日历病例。相反，如果按真值是否偏热来挑年份，D2* 在危险层的覆盖只有 77%，偏差 −0.54°C；这部分来自“水温比气温所示更热”的异常，任何只用可见信息的方法都无法恢复，应当在讨论中写成恢复的极限。这里还有一个评价方法上的问题：按真值是否极端挑选病例、再比较估计器，正是 Lerch 等（2017）所说的“预报者困境”，这样的比较会奖励总是往极端方向报的方法。对热年的评价应当按交付时可见的量分层，或者用阈值加权的 CRPS（Gneiting 和 Ranjan 2011），而不是按真值分层。

另外，P1 层是用“真实峰窗”定义的，这是只有在知道真值时才能算出的量。按它分层评价一个只用决策时信息的估计器，会把“条件于不可见量的回归效应”混进结果。稿件自己在图 3 中按决策时的气候峰窗分层，这才应当是主要的评价口径。

我要求：(1) 估计器的主要指标改为病例层面的恰当评分——MAE、失败率、CRPS 和 90% 区间得分——并按决策时分层报告；(2) 对照至少包括查表去偏、P2、MOVE.1 日补全和随机回归多重插补（后两者见第三轮审稿人 A 的意见）；(3) 摘要中“去掉了 75% 的偏差”应当改为病例层面的结论，并如实写出 P2 与 D2* 在点估计上不分上下。如果作者愿意，我认为最诚实也最有用的结论是：“均值偏差可以用简单的去偏去掉；分布回归的贡献是给出近似校准的区间，并在危险年份中把失败率从 36% 降到约 30%。”

#### 3. 恢复律的证据要换一种拿法

稿件用“恢复律解释了 27 个格子失败率方差的 95%，而没有拟合任何误差”作为恢复律的主要证据。这个数字本身不能说明恢复律有用。我用格子均值做了对照：只按“峰窗被遮的类别 × 信息层”取样本内平均，9 个参数就能解释 95.1%；只按峰窗被遮的类别，3 个参数解释 71%（核算第 3 节）。格子之间的差异主要由设计变量本身决定，任何随遮盖比例单调变化的量都能解释其中的大部分。

恢复律真正的证据在病例层面，而且比稿件写的更强。与留一区域的格子查表相比，恢复律的 Brier 技巧是 0.27 对 0.15，AUC 是 0.87 对 0.77；在同一个格子内部，它仍能区分会失败与不会失败的病例，按病例数加权的 AUC 为 0.81。这说明恢复律携带了站点层面的信息——残差持续性、峰值距平的大小——而不只是重复了设计变量。作者应当用这些数字代替格子层面的方差解释。

恢复律的弱点在尾部。在最难的格子里，它预测 34% 的失败，实际是 39%；误差中有 11.5% 超出两倍预测标准差，超额峰度约 13，方差比预测大 23%。这是高斯 AR(1) 近似的局限，不是参数估计的问题。对使用者最有价值的检验，是能否在危险层（峰窗被遮一半以上）内部区分“能恢复的”与“不能恢复的”年份，稿件没有做。我核算的结果对作者有利：在这一层内部，恢复律的 AUC 为 0.77–0.79，R7b 为 0.79–0.81；在 5% 风险处，R7b 能从危险层中放行 30%（真实日历）到 47%（受控长缺口）的病例，而单特征规则会把这一层全部拒绝（核算第 2 节）。这才是学习部件真正的价值：它把“一刀切地拒绝危险年份”变成“救回其中三到五成”。按真实档案中危险层约 7% 的比例折算，这相当于在单特征规则之外再多用约 2 个百分点的不完整年份。稿件应当把这个结果作为恢复律和 R7b 的主要证据，并说清楚它的规模。我还建议把“律”（law）改称“模型”（model）：它是一个在尾部失效的近似，称为“律”会招来不必要的批评。

#### 4. 标签无关阈值优化的是一个错误的目标

这条规则在被筛选的集合中按预测失败概率从小到大放行，直到 k 倍的放行平均概率达到 5%。它控制的是整个集合的平均风险，因此只要容易的病例足够多，就会放行一部分困难的病例。我核算了它在真实档案和新站上的行为（核算第 6、7 节）。在 3,876 个真实不完整站年中，规则放行 98.8%；放行的站年里，有 120 个的预测失败概率超过 0.3，最高的一个为 0.73。在新站检验的真实日历下，风险最高的组 `usgsnew_g041` 放行了 22 个病例，它们的平均预测失败概率是 0.33，实际失败 45%——分数已经指出这些值多半不可用，规则仍然放行。在放行不少于 20 例的组中，真实日历下 29 组里有 9 组、长缺口下 40 组里有 10 组的实际风险超过 7%，这些组占全部放行病例的四分之一。长缺口下的超标组还有另一个问题：它们的平均预测只有 5%–6%，实际是 11%–14%，这是组层面的校准失真。

对一个要决定“这一年的值能不能用”的使用者，决策单位是单个站年，而不是整个集合。放行一个模型自己估计有七成会出错的值，不能叫“适用性判断”。在统计上，这对应两个不同的问题：逐例的选择性预测（Chow 1970 意义上的最优拒绝规则，按每个值的失败概率与使用者的损失比取阈值），和集合层面的错误发现控制（运行平均的局部错误发现规则）。稿件需要先说清楚它要解决的是哪一个，再选规则。我的建议是：单个值的发布或监管判定用逐例阈值；趋势和区域平均用集合层面的期望风险，但加一个逐例上限，并同时报告组层面的风险分布。我用作者自己的分数试算了逐例阈值（核算第 9 节）：按真实档案中各层的比例折算，每 1,000 个不完整站年中，“R7b ≤ 0.10 才放行”用上 936 个站年，其中 2.3 个误差超过 0.5°C；单特征规则用上 928 个，错 4.5 个；“全部保留”用上 1,000 个，错 26–34 个。也就是说，作者的分数本身是好的，用错的是决策规则。组层面的保证可以用按组分别应用规则、重叠组上的条件校准（Gibbs、Cherian 和 Candès 2025）或层次模型来实现，代价应当报告。

系数 k 的估计方式也需要换。现在的 k 是 14 个源区域“实际/预测”之比的第 80 百分位，按设计就允许约五分之一的新区域超出。临床预测模型的外部验证处理的是同一个问题，而且有成熟的做法（Riley 等 2016；Debray 等 2017）：在区域之间做内外交叉验证，对各区域的“实际/预测”比做随机效应荟萃分析，给出新区域比值的预测区间，再报告“新区域风险超过 7% 的预测概率”。这比一个经验百分位透明，也直接回答使用者的问题。另外，选择性预测在分布移动下会放大组间差异，平均风险下降的同时最差组的风险上升（Jones 等 2021；Kamath、Jia 和 Liang 2020）。`usgsnew_g041` 上看到的正是这种现象，讨论中应当引用这些工作并正面说明。

这条规则的谱系和保证问题，第三轮审稿人 B 已经详细说明，我同意，不再重复。在此基础上我还要强调两点。第一，新站检验在真实日历下没有信息量：不筛选时 D2* 的失败率只有 4.8%，规则放行了 99.6%，这一半检验等于检验“全部放行时风险是否低于 7%”。有信息量的长缺口总体中，不加系数时风险为 7.0%，恰在门槛上；加系数后为 5.6%，上界 6.8%。所以这次“通过”取决于 k，而 k 本身是从 14 个源区域中取的第 80 百分位。第二，这次评估已经不是盲测。迁移这一环在稿件里实际上仍是开放的。

#### 5. 下游降幅由少数站决定，“结论改变”还没有出现

P4 用 42 个站上趋势误差的均方根来比较多重插补（C）与暖季 90% 规则（A1）。我拆开了这个均方根（核算第 5 节）。C 的总平方误差中，一个站（usgs|13342500）占 47%，前三个站占 72%；plug-in（B）的前三个站占 86%。逐站看，C/A1 的 RMSE 比中位数是 0.32，但四分位上界是 1.25，约四分之一的站上 C 比 A1 更差。趋势绝对误差的中位数，A1 是 0.0033°C/10 年，B 是 0.0004，C 是 0.0003，而站点完整记录趋势的中位数是 0.66。也就是说，对典型的站，三种“保留年份”的做法都几乎没有误差，P4 的降幅主要反映少数站的情况。随机数改变时降幅从 76% 移到 65%，“保留年份所占比例”从 77% 移到 60%，区间是 [33%, 95%]，都与这一点一致。

需要公平地说，结论的方向并不脆弱。我按 Broderick、Giordano 和 Meager 提出的问题（去掉多少数据才能推翻结论）检查了一遍：P4 的比较是两组站点平方误差之和的比，可以精确求出最少要去掉哪些站。要让 C 相对 A1 的降幅低于预注册的 20%，至少要去掉 42 个站中的 28 个；要让 C 不再优于 A1，至少要去掉 30 个（分属 16 个独立组）。在至少 15 个完整年的 104 个站上，这两个数是 84 和 87。按独立组汇总，18 个组中有 16 个 C 优于 A1。只保留年份、不做多重插补的 B，方向同样成立（要去掉 17 个站才翻转），但只要去掉 7 个站，降幅就低于 20%。所以我的意见不是“P4 站不住”，而是“P4 证明了方向，降幅的大小由少数站决定，正文不应强调具体的百分比”。

我还把每个站的趋势误差分解成偏差和方差（核算第 5 节）。A1 的误差中 83%–89% 是方差；完全随机缺测时 A1 的 RMSE 是 0.052，主要情景是 0.057，几乎没有差别。也就是说，P4 测到的主要是丢掉年份损失了多少精度，而不是丢掉年份带来了多少偏差。这与缺失数据文献的一般结论一致：缺测与结果的关系很弱时，完整个案分析近似无偏，多重插补的收益主要是效率（White 和 Carlin 2010；Hughes 等 2019）。这不削弱“保留年份”的建议，但改变了它的理由；同时也说明，稿件的状态相关情景没有对方法构成真正的压力。真正的压力测试是缺测与炎热强相关的情形，例如间歇性河流断流时传感器露出水面，或者高温导致设备故障。在那种情形下 A1 会有偏差，而 H30 本身也可能恢复不了。作者应当至少构造一个这样的情景，说明两种做法各自在什么条件下失效。

稿件也承认，在单站上检出升温的能力，A1 与 C 几乎相同（99.8% 对 100%）。这意味着，下游实验证明的是“趋势的数值误差变小”，而不是“某个科学判断发生了改变”。WRR 的编辑和读者最想知道的恰恰是后者。

我要求：(1) 用多种子重复报告 P4，并给出逐站比值的分布、按独立组的结果，以及“最少去掉多少个站会推翻结论”；(2) 说明误差最大的那几个站有什么特点；(3) 做第三轮审稿人 C 建议的选站实验：按近年高影响力研究实际采用的选站规则（完整年超过 14 年、90% 完整、75% 有效、只用完整日历年），统计 USGS 全部日水温站中能进入分析的站数，与“保留并估计”比较站数、空间覆盖、全国趋势中位数及其区间、热浪年频率。如果可用站数成倍增加、区间显著变窄或结论改变，这就是全文最有力的意义证据；如果不变，照实写出，也同样有用。

#### 6. 机制是经典的，强对照仍然缺失

“回归补全压缩方差、低估极值”在水文学中有很长的历史：Matalas 和 Jacobs（1964）用回归加噪声保持方差，Hirsch（1982）提出 MOVE.1，Vogel 和 Stedinger（1985）直接对统计量做最小方差增补，USGS 的统计教科书（Helsel 等 2020）明确写道最小二乘延展会按 r² 损失方差并低估极端事件的频率。稿件的引言仍然写“没有为统计量而不是日序列设计的估计器”，这与文献不符。这些第三轮已经指出，研究脉络文件中有完整的整理。我核对了稿件的 53 条参考文献，Matalas–Jacobs、Hirsch 和 Vogel–Stedinger 一条也没有。对 WRR 来说，这是一个会直接影响新颖性判断的遗漏。

同一传统里还有一个稿件没有考虑的做法：不补全，而把不完整年份当作删失信息。洪水频率分析中的期望矩算法（Cohn、Lane 和 Baier 1997；Bulletin 17C，England 等 2018）就是这样使用历史洪水和不完整记录的。对 H30 而言，如果一个不完整年份中有完整观测的 30 天窗口，那么这些窗口均值的最大值就是真实 H30 的下界，这一年可以作为左删失观测进入趋势回归，而不需要任何补全模型。这是“保留年份”最便宜的版本。如果它在趋势上与多重插补（C）相当，稿件的估计器对趋势研究就不是必需的；如果明显更差，这就是多重插补价值的直接证据。

在此之上，我要补充一个机制层面的检验。稿件用“岭回归与无收缩回归的冷偏差相同”来证明偏差来自条件均值而不是岭收缩。这个消融只在线性模型之间比较。机制主张——任何以均方误差为目标的补全都会在峰窗被遮时偏冷——需要一个非线性的、更强的条件均值模型来检验，例如一个梯度提升的日补全模型，以及一个跨站训练的 LSTM（USGS 和宾州州立大学的大尺度河温产品都用这类结构）。如果它们在危险层同样偏冷，机制主张就是一般的；如果偏差明显变小，论文的建议就需要修改。这个检验也回答了水文审稿人会问的另一个问题：现在的 plug-in 是不是一个太弱的基线。

我建议再加一个更锋利的对照：一个从条件分布中抽样、而不是返回条件均值的概率型序列补全方法，例如条件扩散模型 CSDI（Tashiro 等 2021），与一个点补全的深度方法（例如 SAITS，Du、Côté 和 Liu 2023）并列。如果机制主张成立，由抽样计算的 H30 应当不偏冷，而点补全方法即使日误差更小也会偏冷。这样，“机制”就从一个事后解释变成了一个事先可检验的预测；它同时说明，时间序列插补基准（TSI-Bench，Du 等 2024；Khayati 等 2020）普遍使用的逐点误差，衡量不了下游泛函的好坏。还有一个必须正面回答的问题：欧洲的河温研究已经开始用 LSTM 从气象资料重建 1985–2020 年的完整日序列，用来研究河流热浪的趋势（Frank 等 2026，基于 TempER 的 4,000 多个站）。对这一群体的读者，第一个问题就是“为什么不直接用重建序列”。

#### 7. 输入资料和河流类型没有被当作设计变量

气温层补全是失败的主要来源，而气温来自 NASA POWER，网格约 0.5° × 0.625°。对小流域而言，这个分辨率很粗。气温层的中位 R² 只有 0.57，其中有多少是方法的问题、多少是驱动资料的问题，稿件没有区分。美国站可以换用 Daymet（1 km）或 PRISM，欧洲站可以换用 E-OBS 或 ERA5-Land，有站点气温的可以作为上限对照。另外，档案中 336 个 USGS 站有 287 个下载到了日流量，而低流量期河流对气温更敏感，热峰也多与低流量同时出现；在气温层回归中加入流量，可能显著降低危险层的失败率。如果驱动或流量能明显降低失败，论文最实用的建议就应当是“先改进输入资料”，这比改进估计器便宜得多。

新站检验中风险最高的组只有一个站，即德克萨斯州的 Big Sandy Creek（USGS 08086290，`usgsnew_g041`）。它的 H30 约 29.0°C，源域中达到这一水平的站年只有 4.2%；真实日历下 plug-in 的偏差是正的（+0.21°C），失败率 26%，与全文的“冷偏差”方向相反。它很可能是一条间歇性河流，也可能处在水温对气温响应趋于饱和的区间（Mohseni 等 1998）。第三轮审稿人 A 要求的失败地图、河流类型分层（间歇性、受调控、湖泊出口、极热河流）和日最高温上的检验，仍然是必要的。

#### 8. 证据的确认性已经消耗得差不多了

这项研究有两份预注册、十二条偏离记录；半球与季节定义是在第一次评估之后修正的，区间校正是在 P1 判定之后加入的，标签无关规则是在第一次评估失败之后提出的，最后整套随机数又在两次评估之后改变，所有结果重算。每一步都有合理的理由，作者也都如实记录了。但累加起来，读者已经很难分清哪些结论是确认性的，哪些是在看到资料之后形成的。

更具体的问题是，几个终点用点估计是否越过门槛来判定，而点估计离门槛很近：P1 的覆盖率 85.1% 与 84.8% 分属“通过”和“未通过”，N1 在长缺口下不加系数时恰为 7.0%。这类判定对随机数非常敏感。我要求：(1) 用至少 20 个种子重复整个流程，给出每个终点的分布和“通过”的次数；(2) 今后的成功标准改用区间（例如单侧上界）而不是点估计；(3) 正文用一张表把确认性结果和探索性结果分开；(4) 在一个新的机构或气候区上，做一次在公开平台（例如 OSF Registries）注册的独立检验，终点包括组层面的风险。

### 次要问题

1. 表 2 的最后一列只报告“被拒年份中 D2* 能恢复的比例”。请同时报告 plug-in 能恢复的比例（由“被拒年份的 plug-in 失败率”可知为 71%–97%）。这一列会让读者看到，即使不用 D2*，大多数被拒年份也能用。
2. 流量示范的受控缺口中，峰窗被遮一半以上时，分布回归的偏差（对数单位 +0.036）是 plug-in（+0.018）的两倍；作为真值的完整气候年中包含 USGS 的获准估计值（`e` 标记）。请在正文写明这两点，加入 MOVE.1 对照，并把流量部分移到补充材料，写成对已知机制的跨变量确认。
3. N2 把两个总体和各信息层合并计算。请分别报告：按重算后的 `e10_sealed_usgs/sealed_coverage.csv`，真实日历下峰窗被遮 50%–75% 的病例覆盖率为 79%–81%（气温层与邻站层各二十余例），峰窗被遮 75% 以上的邻站层病例为 81%（80 例）；受控缺口下邻站层各档为 85%–87%。合并后的 87.4% 掩盖了这些不足。
4. 0.5°C 的容差需要与测量不确定度和用途对应起来论证，并给出误差的连续分布曲线，而不只给超阈比例。
5. 正文的代号太多（P0、P1–P5、D2*、R1–R8、A0–C、P1–P4、N1–N4），非专业读者几乎无法跟上。正文请只保留描述性的名字。
6. 用 Holm 方法控制族错误率，与“点估计是否过门槛”的判定方式不相容，请删去或改写。
7. 摘要中的数字太多。保留三个即可：被拒年份中可恢复的比例、危险年份的比例及其失败率、独立检验的风险。
8. D2* 交付的是预测分布的中位数，而主要终点是 |误差| > 0.5°C 的比例。对这个损失，最优的交付值是使 [x − 0.5, x + 0.5] 包含最大概率的 x；只有分布对称且单峰时，它才等于中位数（点预测应当与评分函数一致，见 Gneiting 2011）。请说明为什么交付中位数，或者报告按这一损失选值时的失败率。如果差别很小，一句话即可。
9. 多重插补需要多少次，取决于缺失信息的比例（von Hippel 2018）。请说明 20 次对趋势标准误是否足够。

### 给作者的问题

1. 如果只允许你推荐一种做法给机构的资料产品负责人，它是什么？是单特征规则加 plug-in，还是本文的全部设计？请用档案层面的数字说明选择的理由。
2. 在危险层中，D2* 仍然失败的那 30% 年份，有什么共同特征？它们是可以通过更好的输入资料恢复的，还是原则上不可恢复的？
3. 趋势实验中误差最大的几个站，在“保留并估计”之下的趋势误差是多少？去掉它们之后，P4 还剩多少？
4. 你所说的“使用者”是谁？单个值的发布、监管判定、趋势研究，三者需要的决策规则不同，稿件目前只给出了一种。
5. 多重插补以当年的气温为条件，但不以年份为条件。如果水温趋势中有与气温无关的部分（流量减少、河岸遮荫变化、水库调度），插补会把这部分拉回训练期的平均状态，使趋势偏向零；这是插补模型与分析模型不相容的典型情形（Meng 1994）。在一个人为加入非气温趋势的情景中，C 的趋势偏差是多少？

---

## 三、新颖性评分与端到端闭环

### 评分（满分 10 分）

| 维度 | 分数 | 理由 |
|---|---:|---|
| 问题的重要性 | 7 | 对资料使用者和机构有直接价值；但危险年份只占不完整年份的约 8%，下游的科学意义尚未展示 |
| Idea 的新颖性 | 5.5 | 核心机制（回归补全压缩极值）是经典结论；新的是把“丢弃还是补全”放在同一目标统计量风险下比较，量化规则的浪费，以及发现缺测随年代减少 |
| Design 的新颖性 | 5 | 恢复律是最有原创性的部件（单看这一部件约 7 分）；D2* 是分布回归加分组保形校正，标签无关阈值是平均置信度加运行均值规则加经验系数，都是已知部件的组合 |
| Design 的完整性 | 5 | 没有区分单个值与集合两种决策；没有把输入资料和河流类型当作设计变量；没有为危险年份给出“不能恢复”的明确出口 |
| 端到端闭环 | 5.5 | 源域部分扎实；估计器与简单对照的比较不完整；迁移证据不再是盲测；下游意义未展示 |
| 外部效度 | 4 | 两次附加评估都不是盲测，新站属于已覆盖的机构和流域，没有新气候区 |
| 写作与可读性 | 5 | 结构清楚，但代号过多，确认性与探索性结果混在一起 |

总体而言，这是一项问题选得对、资料做得扎实、设计纪律很强，但设计的重心偏离了问题重心的工作。如果按改进计划把论文重新组织为“分诊—估计—下游”，并补上简单对照、组层面的决策规则、意义实验和一次新的独立检验，我预计端到端闭环可以到 7–8 分，外部效度到 6 分。

### 闭环逐环检查

| 主张 | 需要的证据 | 现有证据 | 判断 |
|---|---|---|---|
| 缺测与炎热只有弱关联 | 站点固定效应与病例交叉审计；间歇性河流分层 | 审计完成；未分层 | 基本闭合 |
| 补全在峰窗被遮时偏冷，机制是条件均值 | 受控遮盖；线性与非线性条件均值模型；MOVE 对照 | 线性模型间的消融；无非线性模型，无 MOVE | 部分闭合 |
| 恢复律能在交付前识别危险 | 病例层面与格内区分度，相对查表和单特征规则；危险层内的区分度 | 病例层面证据存在但未报告；正文用的是不能区分的格子方差 | 证据在，但拿错了 |
| D2* 比简单方法更好 | 恰当评分下与查表、P2、MOVE.1、随机回归多重插补比较；热年单独检验 | 平均偏差与查表相同；一般年份的点估计与 P2 打平；气温显示为热年的危险年份中略优于 P2（失败率 35% 对 41%，210 例）；区间按预注册不合格 | 大部分未证明 |
| 规则浪费可用年份 | 同风险比较；单特征规则 | 表 2 完成；缺单特征规则 | 闭合，需补对照 |
| 目标感知判断在同风险下更好 | 长缺口与真实日历两种总体 | 长缺口下明显更好；真实日历下与单特征规则相同 | 部分闭合 |
| 判断规则可以安全地用于新站 | 盲测；组层面风险；逐例风险 | 非盲测；四分之一放行病例在超标组；放行高风险单值 | 未闭合 |
| 保留年份使趋势更准 | 多种子；逐站分布；去站稳健性 | 方向稳定（要去掉 42 个站中的 30 个才翻转）；幅度由少数站决定；没有改变任何科学判断 | 方向闭合，意义未闭合 |
| 处理方式改变科学结论 | 选站实验；热浪年判定 | 未做 | 未闭合 |
| 机制可推广到其他极值 | 流量示范，含经典对照 | 机制成立；估计器在受控缺口上更差；无 MOVE | 部分闭合 |

---

## 四、对照国际顶级团队：同类问题需要哪些实验

这一节回答一个具体的问题：如果这篇稿件分别送到与它最接近的几个研究群体手里，他们会要求哪些实验才承认设计成立？我查阅了七个群体的代表性工作，包括美国的水文统计传统，河温与大样本机器学习水文，统计学习中的选择性预测与风险控制，缺失数据与时间序列插补，极值统计，工业界与中国团队的天气和洪水模型，以及水文模型检验与确认性研究的规范。每一部分先说明这些团队通常怎样证明一个方法，再对照本稿做到了什么、缺什么。文中引用的文献都核对过 DOI 或 arXiv 编号，列在本文末尾。

### 1. 水文统计：记录延展、统计量增补与删失信息（康奈尔、塔夫茨、USGS）

这一传统对“补全后再算统计量”有非常明确的检验方式。Hirsch（1979，1982）比较记录延展方法时，看的不是逐日误差，而是延展后序列的均值、方差和极端值是否被保留；MOVE.1 正是因为普通回归会按 r² 压缩方差、低估极端事件才提出来的。Vogel 和 Stedinger（1985）更进一步，直接对目标统计量做最小方差增补，而不经过日序列。洪水频率分析中，USGS 和美国陆军工程兵团的 Bulletin 17C（England 等 2018）用期望矩算法（Cohn、Lane 和 Baier 1997）把历史洪水和不完整记录当作删失或区间信息使用，这是“既不丢弃、也不补全”的第三条路。Kroll 和 Stedinger（1996）讨论的删失资料矩估计，Eng 等（2011）关于指数站方法系统性偏高或偏低的分析，也属于这一脉。

按这一传统的标准，本稿的同风险规则比较是这一领域此前没有的工作，这一点站得住。但它缺三样东西：与 MOVE.1 的比较，按目标统计量直接增补的对照，以及把不完整年份当作删失观测的趋势分析。前两者决定 D2* 是否只是重新发现了 MOVE 的结论；第三者决定多重插补对趋势研究是否必需。这一传统的审稿人还会要求一张 Hirsch（1982）式的表，把每种方法对 H30 的偏差、方差和对极端年份的保留情况并列，而不是只报告失败率。

### 2. 河温模型与大样本机器学习水文（USGS、宾州州立、JKU Linz 与 Google、ETH 与 SLF、EPFL、特伦托、BOKU）

河温模型这几年发展得很快。宾州州立大学 Shen 组的 LSTM 河温模型（Rahmani 等 2020，2021）说明，加入流量会显著提高日水温的预测，尤其是在受调控和资料稀少的流域；USGS 的团队把这类模型用于业务化的近期预报（Zwart 等 2023）和全美尺度的日水温预测（Diaz、Oliver 和 Gorski 2025），并专门检验了环境变化下的外推（Topp 等 2023）。在欧洲，Brunner 组用 LSTM 和 TempER 的 4,000 多个站，从气象资料重建了 1985–2020 年的完整日水温序列，用于研究河流热浪趋势（Frank 等 2026）；van Hamel、Janzing 和 Brunner（2026）则说明，河温对大气热浪的响应受流量和融水调制。特伦托的 air2stream（Toffolon 和 Piccolroaz 2015；Piccolroaz 等 2016）、BOKU 的机器学习比较（Feigl 等 2021）和 EPFL 的瑞士长序列分析（Michel 等 2020）是常用的对照。

这个群体证明一个方法时，有几条大家默认的做法。第一，按流域或区域留出，并报告逐站指标的分布，而不只报告合并后的平均（Kratzert 等 2019a）。第二，用多个随机种子训练并集成，因为单个种子会出现与种子有关的严重失败（Kratzert 等 2019b 用了 8 个种子）。第三，专门检验极端事件，而且最好是在训练中不含极端事件、在极端事件上检验（Frame 等 2022）。第四，用概率指标评价不确定性（Klotz 等 2022）。第五，注意在不同资料划分上计算的指标可能互相矛盾，合并指标会掩盖分层的失败（Klotz 等 2024）。

对照本稿，留一区域的交叉拟合是做了的，第三条和第五条部分做了。缺的是：一个跨站训练的 LSTM 或至少一个以重建序列为输入的对照；流量作为输入；逐站指标的分布；多种子。最后一点在本稿中尤其要紧，因为随机数改变已经翻转过一个主要终点。这个群体的审稿人最可能提出的问题是：如果 Frank 等（2026）那样的重建序列已经可以给出完整的日序列，那么 H30 应当用重建序列计算，还是用本稿的方法？稿件需要在同一组病例上回答这个问题。

### 3. 选择性预测与风险控制（斯坦福、伯克利、MIT、CMU、芝加哥、沃顿；以色列理工、特拉维夫、魏茨曼）

本稿的标签无关阈值，在统计学习里有一整套对应的文献，而这一群体对“保证”的要求最严格。首先是估计目标要说清楚。按运行平均的后验错误概率放行，就是 Sun 和 Cai（2007）的自适应局部错误发现规则；它控制的是边际错误发现率，而且只有后验概率正确时才成立。要给出有限样本的保证，就需要有标签的校准资料，例如风险控制预测集（Bates 等 2021）、Learn then Test（Angelopoulos 等 2025）和基于保形 p 值的选择（Jin 和 Candès 2023）。分布移动下，加权保形方法只处理协变量移动（Tibshirani 等 2019），一般移动下的覆盖损失受总变差距离约束（Barber 等 2023）。

其次是组层面。斯坦福 Liang 组的两项工作与本稿的情形非常接近：选择性分类在降低平均风险的同时，可能提高最差组的风险（Jones 等 2021）；在分布移动下，在源域学到的置信度会放行过多的错误答案（Kamath、Jia 和 Liang 2020）。MIT 的 Fisch、Jaakkola 和 Barzilay（2022）要求被放行的集合本身是校准的；Hébert-Johnson 等（2018）的多重校准说明，整体校准的模型在可识别的子群上可以严重失准。Gibbs、Cherian 和 Candès（2025）给出了重叠组上的条件保证。

再次是少量标签和无标签估计。以色列理工 Romano 组的半监督风险控制（Einbinder、Ringel 和 Romano 2025）和伯克利的预测驱动推断（Angelopoulos 等 2023）说明，少量标签加大量预测就能给出有效的推断，而只用预测做推断可能是无效的。无标签的性能估计（Garg 等 2022 的 ATC；Rosenfeld 和 Garg 2023）在理论上与“找到最优预测器”一样难，必须写明移动的假设；魏茨曼的 Nadler 与合作者（Parisi 等 2014）给出了无标签情况下给多个预测器排序的方法。以色列理工的 El-Yaniv 和 Geifman（Geifman 和 El-Yaniv 2017）奠定了深度模型选择性分类的风险–覆盖框架。

这个群体会要求的实验，我按优先级列出：(1) 写明控制的是哪一个量，是边际错误发现率、错误发现比例的期望，还是“错误发现比例超过 5% 的概率”；(2) 在已知真值的合成移动上（分别移动基础失败率、缺口模式和气候）检验规则，并给出使用真实失败概率的 oracle；(3) 对照至少包括先验比例修正（Saerens、Latinne 和 Decaestecker 2002）、ATC、加权保形选择，以及用 0、5、10、20、50 个本地有标签组的预测驱动风险控制；(4) 在至少 100 次重抽上画出实际风险和放行比例的分布，以及风险–覆盖曲线和最差组风险–覆盖曲线。本稿目前只做到了留一区域的经验系数和“本地需要几个组”的粗略估计，与这一标准相距较远。我在第二节第 4 条中提出的逐例阈值、组层面风险和随机效应的“实际/预测”比，就是按这一标准提出的最低要求。

### 4. 缺失数据与插补（Rubin 与 Meng 一脉、ETH、Inria、时间序列插补基准）

缺失数据理论对本稿最重要的提醒有三条。第一，插补的好坏要按它是否再现条件分布来评价，而不是按逐点误差。ETH 的 Meinshausen 组提出了插补评分（Näf 等 2023），Näf、Scornet 和 Josse（2024）进一步说明，在随机缺失下，好的插补应当从正确的条件分布中抽样；稿件已经引用了前者，这正是本稿“条件均值补全使极值偏冷”这一机制的理论基础。第二，插补模型要与分析模型相容（Meng 1994；Xie 和 Meng 2016），否则 Rubin 规则的区间可能失效，Bartlett 和 Hughes（2020）给出了不相容时的自助法推断。第三，缺测与结果的关系很弱时，完整个案分析近似无偏，多重插补的收益主要是效率（White 和 Carlin 2010；Hughes 等 2019）；本轮核算的偏差–方差分解说明，P4 正属于这种情形。插补次数的要求见 von Hippel（2018）。

机器学习的时间序列插补近年有大量基准：BRITS、SAITS（Du、Côté 和 Liu 2023）、条件扩散模型 CSDI（Tashiro 等 2021，斯坦福 Ermon 组）、图神经网络 GRIN（Cini、Marisca 和 Alippi 2022）、清华龙明盛组的 TimesNet（Wu 等 2023），以及 ImputeFormer（Nie 等 2024）、TSI-Bench（Du 等 2024）和弗里堡大学的块状缺测基准（Khayati 等 2020）。这些基准几乎都只用逐点 MAE 或 MSE 评价。本稿相对它们的贡献，恰恰是指出逐点最优不等于泛函最优；但稿件没有用一个这样的方法来证明这一点。我建议至少加入一个点补全的深度方法和一个概率型方法，在同一组病例上同时报告日 MAE 和 H30 误差。如果出现“日 MAE 更小、H30 更偏冷”的情形，这会是全文最容易被机器学习读者记住的一张图。

### 5. 极值统计与极端事件的评价（兰卡斯特、UCL、日内瓦、ETH、海德堡、伯尔尼）

极值统计对本稿有两方面的要求。一方面是缺测下的极值。Robinson 和 Tawn（2000）讨论了不同采样频率下过程极值之间的关系；Simpson 和 Northrop（2026，UCL）专门处理缺测对年最大值建模的影响，稿件已经引用；McVittie 和 Murphy（2025）在风暴潮极值中处理缺测。在回归设定下，日内瓦 Engelke 组的极端分位数回归（Velthoen 等 2023；Pasche 和 Engelke 2024，以瑞士 Aare 河的洪水为例；Gnecco、Terefe 和 Engelke 2024）以及 ETH 的 engression（Shen 和 Meinshausen 2025）都是为训练范围之外的外推设计的。对本稿而言，后者与 `usgsnew_g041` 这类极热河流直接相关：在源域中只有 4.2% 的站年达到这一水平时，分位数回归的上尾几乎没有资料支撑。

另一方面是怎样评价极端事件。Lerch 等（2017）的“预报者困境”说明，按观测到的极端事件挑选样本再比较方法，会奖励总是往极端方向报的方法；正确的做法是阈值加权的恰当评分（Gneiting 和 Ranjan 2011），或者伯尔尼的 Allen、Ginsbourger 和 Ziegel（2023）提出的变换核评分。点预测还要与评分函数一致（Gneiting 2011）。这一群体的审稿人会要求：在决策时分层之外，用阈值加权 CRPS 评价最热年份；检验恢复模型尾部的校准（例如换用 t 分布或广义帕累托尾）；报告训练范围之外的覆盖率。本稿目前只做了按真值分层的热年分析，按 Lerch 等的标准，这部分要改写。

### 6. 工业界与中国团队的天气、洪水模型（Google、DeepMind、Microsoft、NVIDIA、华为、复旦、清华、上海人工智能实验室）

这些团队的问题与本稿不同，但它们证明“新方法可以替代现行做法”的方式，对本稿的意义部分很有借鉴价值。Google 的全球洪水预报（Nearing 等 2024）在训练中没有出现过的站点和时段上检验，把对照组（GloFAS）放在有利的位置上比较，并逐站报告“新方法不差于对照”的站点比例、显著性和效应量；Google 与希伯来大学的 Morin 等合作的业务化洪水预报（Nevo 等 2022）还说明了从研究走向业务需要哪些检验。WeatherBench 2（Rasp 等 2024）把评价写成一张固定的“记分卡”，使用留出的年份和一组事先规定的确定性与概率指标。DeepMind 的 GraphCast（Lam 等 2023）在常规指标之外单独检验了热带气旋路径、大气河和极端温度；GenCast（Price 等 2025）用 CRPS 评价概率预报，并用相对经济价值曲线（Richardson 2000）检验极端高温、低温预报对不同成本损失比的使用者有多大价值。Microsoft 的 Aurora（Bodnar 等 2025）检验了微调到新任务后的表现，NVIDIA 的 FourCastNet（Kurth 等 2023）以计算效率为重点。

中国团队在这方面同样有代表性的工作。华为的盘古（Bi 等 2023）和复旦的 FuXi（Chen 等 2023）都以欧洲中期天气预报中心的业务系统为对照，在同一目标上比较。清华龙明盛组与 Jordan 合作的 NowcastNet（Zhang 等 2023）除了高阈值的评分外，还请 62 位业务预报员做了盲评，在 71% 的个例中排名第一。上海人工智能实验室（与上海交大、中国科大的作者合作）的 ExtremeCast（Xu 等 2024）专门针对机器学习预报低估极值的问题，用 SEDI 等极端依赖指标评价。Olivetti 和 Messori（2024）则说明，数据驱动模型在一般指标上领先，并不意味着在极端事件上领先。

对本稿可以直接借用的有四条。(1) 一张固定的记分卡：所有估计器乘以所有决策时分层乘以所有指标，在一张表中给出，而不是分散在正文和补充材料中。(2) 逐站或逐组的配对比较：报告新方法不差于对照的站点比例和效应量。(3) 决策价值：用相对经济价值曲线代替单一的 5% 风险水平，说明在不同的“错放与错拒的代价比”下，逐例阈值、单特征规则和全部保留各自的价值；这与第二节第 4 条的逐例阈值是同一件事。(4) 事件层面的评价：把“是否判为热年”当作一个事件，报告命中率、误报率和 SEDI 一类的指标，而不只报告漏判比例。

### 7. 检验层级、空间验证、稳健性与确认性研究

水文模型检验有一个四十年来被反复使用的层级。Klemeš（1986）提出，模型必须在与率定条件不同的条件下检验，包括差异分割样本检验和替代流域检验；Coron 等（2012）在 216 个澳大利亚流域上用这一思路做了“碰撞测试”，Thirel 等（2015）把它写成了检验变化条件的标准协议，Refsgaard 和 Knudsen（1996）及 Refsgaard 和 Henriksen（2004）把它用于业务化验证。Ewen 和 Parkin（1996）提出了“盲验证”：在看到检验资料之前写下预测和成功标准。Seibert（2001）和 Seibert 等（2018）要求每个模型都与下界基准（最简单的做法）和上界基准比较，Kratzert 等（2019b）评价 LSTM 时就采用了这一做法。对本稿而言，冷年训练、热年检验的差异分割样本检验，单特征规则这样的下界基准，以及一次真正的盲检验，是这一传统的最低要求。

空间预测有类似的规范。Roberts 等（2017）和 Ploton 等（2020）说明，随机交叉验证会高估空间预测的精度；明斯特的 Meyer 和 Pebesma（2021，2022）提出用“适用域”标出预测变量空间中模型可以使用的范围，Wadoux 等（2021）则提醒空间交叉验证也有它的偏差。本稿的适用边界规则可以直接用适用域的方法来定义。

在稳健性方面，机器学习界的标准比水文界更严格。Henderson 等（2018）和 Bouthillier 等（2021）要求随机化所有变异来源（种子、数据划分、超参数），再比较方法；以色列理工 Reichart 组（Dror 等 2018，2019）给出了多种子下比较两个模型的检验方法。Kapoor 和 Narayanan（2023）总结了机器学习科学研究中的泄漏问题，Dwork 等（2015）说明反复使用同一份留出资料会使保证失效；后者正是本稿两次检验在重算后不再是盲测的原因。Broderick、Giordano 和 Meager 提出的“去掉多少数据会推翻结论”，以及规格曲线（Simonsohn、Simmons 和 Nelson 2020）和多重宇宙分析（Steegen 等 2016），都是报告分析选择敏感性的标准方式。区域趋势的结论需要场显著性检验（Renard 等 2008；Wilks 2016）。确认性研究的做法见 Nosek 等（2018）和 Chambers 和 Tzavella（2022），注册平台可以用 OSF（Foster 和 Deardorff 2017），以平台的公开时间戳为准。在没有完美参照的情况下估计几种产品的误差方差，可以用三重配置（Stoffelen 1998；MIT Entekhabi 组的 McColl 等 2014），这可以用于真实缺口上的检验，但要注意气温补全和邻站补全的误差可能相关。

### 8. 实验清单

下表把以上要求汇总成一张清单。“必须”是指不做的话，审稿人有充分理由认为对应的主张没有被证明。

| 实验 | 依据 | 本稿现状 | 优先级 |
|---|---|---|---|
| 单特征规则和查表去偏作为下界基准，oracle 作为上界基准 | Seibert 2001；Seibert 等 2018 | 只有 oracle | 必须 |
| MOVE.1 日补全与按统计量增补 | Hirsch 1982；Vogel 和 Stedinger 1985 | 无 | 必须 |
| 不完整年份作为删失观测的趋势回归 | Cohn 等 1997；England 等 2018 | 无 | 建议 |
| 非线性与跨站深度补全；概率型补全与点补全的对照 | Rahmani 等 2021；Frank 等 2026；Tashiro 等 2021；Du 等 2023 | 只有线性模型 | 必须 |
| 病例层面的恰当评分，按决策时分层，加阈值加权 CRPS | Gneiting 和 Raftery 2007；Gneiting 和 Ranjan 2011；Lerch 等 2017 | CRPS 只用于选择模型 | 必须 |
| 一张固定的记分卡 | Rasp 等 2024 | 结果分散 | 建议 |
| 逐站、逐组的指标分布和配对胜率 | Kratzert 等 2019a；Nearing 等 2024；Klotz 等 2024 | 以合并指标为主 | 必须 |
| 至少 20 个种子，并随机化数据划分 | Kratzert 等 2019b；Henderson 等 2018；Bouthillier 等 2021；Dror 等 2019 | 一次重抽 | 必须 |
| 去掉多少站或组会推翻结论 | Broderick、Giordano 和 Meager | 本轮核算只做了 P4 | 建议 |
| 差异分割样本检验（冷年训练、热年检验；按年代分割） | Klemeš 1986；Coron 等 2012；Thirel 等 2015；Frame 等 2022 | 无 | 必须 |
| 新机构或新气候区上的盲检验，事先公开注册 | Ewen 和 Parkin 1996；Nosek 等 2018；Dwork 等 2015 | 两次检验都已不是盲测 | 必须 |
| 组层面风险与最差组风险–覆盖曲线 | Jones 等 2021；Gibbs、Cherian 和 Candès 2025；Hébert-Johnson 等 2018 | 无保证 | 必须 |
| 逐例阈值与相对经济价值曲线 | Chow 1970；Richardson 2000；Price 等 2025 | 无 | 必须 |
| 新区域风险的预测区间（随机效应的“实际/预测”比） | Riley 等 2016；Debray 等 2017 | 经验百分位 | 建议 |
| 少量标签的对照曲线 | Angelopoulos 等 2023；Einbinder、Ringel 和 Romano 2025 | 只有本地组数 | 建议 |
| 已知真值的合成移动，加 oracle | Ovadia 等 2019；Garg 等 2022 | 无 | 建议 |
| 热年判定的命中率、误报率和极端依赖指标 | Nearing 等 2024；Xu 等 2024 | 只有漏判比例 | 建议 |
| 适用域与失败地图 | Meyer 和 Pebesma 2021；Ploton 等 2020 | 无 | 建议 |
| 缺测与炎热强相关的情景；含非气温趋势的情景 | Hughes 等 2019；Meng 1994 | 只有弱相关情景 | 建议 |
| 真实缺口上的检验（同址传感器、三重配置） | Stoffelen 1998；McColl 等 2014 | 无 | 建议 |
| 驱动资料与流量的消融 | Thornton 等 2021；Cornes 等 2018；Muñoz-Sabater 等 2021；Rahmani 等 2020 | 无 | 建议 |
| 选站实验中的场显著性 | Renard 等 2008；Wilks 2016 | 选站实验未做 | 必须（若做选站实验） |
| 分析选择的规格曲线（容差、风险水平、窗口长度、规则阈值） | Simonsohn 等 2020；Steegen 等 2016 | 部分敏感性分析 | 建议 |

这些实验的具体做法、顺序和判定标准见 [改进计划](NEXT_STEPS_ZH.md)。

---

## 参考文献

以下文献都核对过 DOI（Crossref）或 arXiv 编号。会议论文没有 DOI 的，给出 arXiv 编号。

**水文统计与记录延展**

- Cohn, T. A., Lane, W. L., & Baier, W. G. (1997). An algorithm for computing moments-based flood quantile estimates when historical flood information is available. *Water Resources Research*, 33(9), 2089–2096. https://doi.org/10.1029/97WR01640
- Eng, K., Kiang, J. E., Chen, Y.-Y., Carlisle, D. M., & Granato, G. E. (2011). Causes of systematic over- or underestimation of low streamflows by use of index-streamgage approaches in the United States. *Hydrological Processes*, 25(14), 2211–2220. https://doi.org/10.1002/hyp.7976
- England, J. F., Jr., Cohn, T. A., Faber, B. A., Stedinger, J. R., Thomas, W. O., Jr., Veilleux, A. G., Kiang, J. E., & Mason, R. R., Jr. (2018). *Guidelines for determining flood flow frequency—Bulletin 17C*. USGS Techniques and Methods 4-B5. https://doi.org/10.3133/tm4B5
- Helsel, D. R., Hirsch, R. M., Ryberg, K. R., Archfield, S. A., & Gilroy, E. J. (2020). *Statistical methods in water resources*. USGS Techniques and Methods 4-A3. https://doi.org/10.3133/tm4A3
- Hirsch, R. M. (1979). An evaluation of some record reconstruction techniques. *Water Resources Research*, 15(6), 1781–1790. https://doi.org/10.1029/WR015i006p01781
- Hirsch, R. M. (1982). A comparison of four streamflow record extension techniques. *Water Resources Research*, 18(4), 1081–1088. https://doi.org/10.1029/WR018i004p01081
- Kroll, C. N., & Stedinger, J. R. (1996). Estimation of moments and quantiles using censored data. *Water Resources Research*, 32(4), 1005–1012. https://doi.org/10.1029/95WR03294
- Matalas, N. C., & Jacobs, B. (1964). *A correlation procedure for augmenting hydrologic data*. USGS Professional Paper 434-E. https://doi.org/10.3133/pp434E
- Mohseni, O., Stefan, H. G., & Erickson, T. R. (1998). A nonlinear regression model for weekly stream temperatures. *Water Resources Research*, 34(10), 2685–2692. https://doi.org/10.1029/98WR01877
- Vogel, R. M., & Stedinger, J. R. (1985). Minimum variance streamflow record augmentation procedures. *Water Resources Research*, 21(5), 715–723. https://doi.org/10.1029/WR021i005p00715

**河温模型与大样本机器学习水文**

- Diaz, J., Oliver, S., & Gorski, G. (2025). Evaluation of daily stream temperature predictions (1979–2021) across the contiguous United States using a spatiotemporal aware machine learning algorithm. *Environmental Modelling & Software*, 193, 106655. https://doi.org/10.1016/j.envsoft.2025.106655
- Feigl, M., Lebiedzinski, K., Herrnegger, M., & Schulz, K. (2021). Machine-learning methods for stream water temperature prediction. *Hydrology and Earth System Sciences*, 25(5), 2951–2977. https://doi.org/10.5194/hess-25-2951-2021
- Frame, J. M., Kratzert, F., Klotz, D., Gauch, M., Shalev, G., Gilon, O., et al. (2022). Deep learning rainfall–runoff predictions of extreme events. *Hydrology and Earth System Sciences*, 26, 3377–3392. https://doi.org/10.5194/hess-26-3377-2022
- Frank, C., Gauch, M., Chartier-Rescan, C., Grundmann, M., & Brunner, M. (2026). Mapping riverine heatwave trends across Europe using reconstructed river temperature time-series. EGU General Assembly 2026, EGU26-14281（会议摘要）. https://doi.org/10.5194/egusphere-egu26-14281
- Klotz, D., Kratzert, F., Gauch, M., Keefe Sampson, A., Brandstetter, J., Klambauer, G., et al. (2022). Uncertainty estimation with deep learning for rainfall–runoff modeling. *Hydrology and Earth System Sciences*, 26(6), 1673–1693. https://doi.org/10.5194/hess-26-1673-2022
- Klotz, D., Gauch, M., Kratzert, F., Nearing, G., & Zscheischler, J. (2024). Technical note: The divide and measure nonconformity – how metrics can mislead when we evaluate on different data partitions. *Hydrology and Earth System Sciences*, 28(15), 3665–3673. https://doi.org/10.5194/hess-28-3665-2024
- Kratzert, F., Klotz, D., Herrnegger, M., Sampson, A. K., Hochreiter, S., & Nearing, G. S. (2019a). Toward improved predictions in ungauged basins: Exploiting the power of machine learning. *Water Resources Research*, 55, 11344–11354. https://doi.org/10.1029/2019WR026065
- Kratzert, F., Klotz, D., Shalev, G., Klambauer, G., Hochreiter, S., & Nearing, G. (2019b). Towards learning universal, regional, and local hydrological behaviors via machine learning applied to large-sample datasets. *Hydrology and Earth System Sciences*, 23, 5089–5110. https://doi.org/10.5194/hess-23-5089-2019
- Michel, A., Brauchli, T., Lehning, M., Schaefli, B., & Huwald, H. (2020). Stream temperature and discharge evolution in Switzerland over the last 50 years: annual and seasonal behaviour. *Hydrology and Earth System Sciences*, 24(1), 115–142. https://doi.org/10.5194/hess-24-115-2020
- Nearing, G., Cohen, D., Dube, V., Gauch, M., Gilon, O., Harrigan, S., et al. (2024). Global prediction of extreme floods in ungauged watersheds. *Nature*, 627, 559–563. https://doi.org/10.1038/s41586-024-07145-1
- Nevo, S., Morin, E., Gerzi Rosenthal, A., Metzger, A., Barshai, C., Weitzner, D., et al. (2022). Flood forecasting with machine learning models in an operational framework. *Hydrology and Earth System Sciences*, 26, 4013–4032. https://doi.org/10.5194/hess-26-4013-2022
- Piccolroaz, S., Calamita, E., Majone, B., Gallice, A., Siviglia, A., & Toffolon, M. (2016). Prediction of river water temperature: a comparison between a new family of hybrid models and statistical approaches. *Hydrological Processes*, 30(21), 3901–3917. https://doi.org/10.1002/hyp.10913
- Rahmani, F., Lawson, K., Ouyang, W., Appling, A., Oliver, S., & Shen, C. (2020). Exploring the exceptional performance of a deep learning stream temperature model and the value of streamflow data. *Environmental Research Letters*. https://doi.org/10.1088/1748-9326/abd501
- Rahmani, F., Shen, C., Oliver, S., Lawson, K., & Appling, A. (2021). Deep learning approaches for improving prediction of daily stream temperature in data-scarce, unmonitored, and dammed basins. *Hydrological Processes*, 35(11), e14400. https://doi.org/10.1002/hyp.14400
- Toffolon, M., & Piccolroaz, S. (2015). A hybrid model for river water temperature as a function of air temperature and discharge. *Environmental Research Letters*, 10(11), 114011. https://doi.org/10.1088/1748-9326/10/11/114011
- Topp, S. N., Barclay, J., Diaz, J., Sun, A. Y., Jia, X., Lu, D., et al. (2023). Stream temperature prediction in a shifting environment: Explaining the influence of deep learning architecture. *Water Resources Research*, 59(4), e2022WR033880. https://doi.org/10.1029/2022WR033880
- van Hamel, A., Janzing, J., & Brunner, M. (2026). River temperature response to atmospheric heatwaves is modulated by discharge and meltwater. *Communications Earth & Environment*, 7, 296. https://doi.org/10.1038/s43247-026-03269-6
- Zwart, J. A., Oliver, S. K., Watkins, W. D., Sadler, J. M., Appling, A. P., Corson-Dosch, H. R., et al. (2023). Near-term forecasts of stream temperature using deep learning and data assimilation in support of management decisions. *Journal of the American Water Resources Association*. https://doi.org/10.1111/1752-1688.13093

**驱动资料**

- Cornes, R. C., van der Schrier, G., van den Besselaar, E. J. M., & Jones, P. D. (2018). An ensemble version of the E-OBS temperature and precipitation data sets. *Journal of Geophysical Research: Atmospheres*, 123, 9391–9409. https://doi.org/10.1029/2017JD028200
- Muñoz-Sabater, J., Dutra, E., Agustí-Panareda, A., Albergel, C., Arduini, G., Balsamo, G., et al. (2021). ERA5-Land: a state-of-the-art global reanalysis dataset for land applications. *Earth System Science Data*, 13, 4349–4383. https://doi.org/10.5194/essd-13-4349-2021
- Thornton, P. E., Shrestha, R., Thornton, M., Kao, S.-C., Wei, Y., & Wilson, B. E. (2021). Gridded daily weather data for North America with comprehensive uncertainty quantification. *Scientific Data*, 8, 190. https://doi.org/10.1038/s41597-021-00973-0

**选择性预测、风险控制与外部验证**

- Angelopoulos, A. N., Bates, S., Fannjiang, C., Jordan, M. I., & Zrnic, T. (2023). Prediction-powered inference. *Science*, 382, 669–674. https://doi.org/10.1126/science.adi6000
- Angelopoulos, A. N., Bates, S., Candès, E. J., Jordan, M. I., & Lei, L. (2025). Learn then test: Calibrating predictive algorithms to achieve risk control. *Annals of Applied Statistics*, 19(2), 1641–1662. https://doi.org/10.1214/24-AOAS1998
- Barber, R. F., Candès, E. J., Ramdas, A., & Tibshirani, R. J. (2023). Conformal prediction beyond exchangeability. *Annals of Statistics*, 51(2), 816–845. https://doi.org/10.1214/23-AOS2276
- Bates, S., Angelopoulos, A., Lei, L., Malik, J., & Jordan, M. (2021). Distribution-free, risk-controlling prediction sets. *Journal of the ACM*, 68(6), 1–34. https://doi.org/10.1145/3478535
- Chow, C. K. (1970). On optimum recognition error and reject tradeoff. *IEEE Transactions on Information Theory*, 16(1), 41–46. https://doi.org/10.1109/TIT.1970.1054406
- Debray, T. P. A., Damen, J. A. A. G., Snell, K. I. E., Ensor, J., et al. (2017). A guide to systematic review and meta-analysis of prediction model performance. *BMJ*, 356, i6460. https://doi.org/10.1136/bmj.i6460
- Einbinder, B.-S., Ringel, L., & Romano, Y. (2025). Semi-supervised risk control via prediction-powered inference. *IEEE Transactions on Pattern Analysis and Machine Intelligence*, 47(12), 11080–11090. https://doi.org/10.1109/TPAMI.2025.3594263
- Fisch, A., Jaakkola, T., & Barzilay, R. (2022). Calibrated selective classification. *Transactions on Machine Learning Research*. arXiv:2208.12084
- Garg, S., Balakrishnan, S., Lipton, Z. C., Neyshabur, B., & Sedghi, H. (2022). Leveraging unlabeled data to predict out-of-distribution performance. *ICLR*. arXiv:2201.04234
- Geifman, Y., & El-Yaniv, R. (2017). Selective classification for deep neural networks. *NeurIPS*. arXiv:1705.08500
- Gibbs, I., Cherian, J. J., & Candès, E. J. (2025). Conformal prediction with conditional guarantees. *Journal of the Royal Statistical Society Series B*, 87(4), 1100–1126. https://doi.org/10.1093/jrsssb/qkaf008
- Hébert-Johnson, U., Kim, M. P., Reingold, O., & Rothblum, G. N. (2018). Multicalibration: Calibration for the (computationally-identifiable) masses. *ICML*. arXiv:1711.08513
- Jin, Y., & Candès, E. J. (2023). Selection by prediction with conformal p-values. *Journal of Machine Learning Research*, 24(244), 1–41. arXiv:2210.01408
- Jones, E., Sagawa, S., Koh, P. W., Kumar, A., & Liang, P. (2021). Selective classification can magnify disparities across groups. *ICLR*. arXiv:2010.14134
- Kamath, A., Jia, R., & Liang, P. (2020). Selective question answering under domain shift. *Proceedings of ACL 2020*, 5684–5696. https://doi.org/10.18653/v1/2020.acl-main.503
- Ovadia, Y., Fertig, E., Ren, J., Nado, Z., Sculley, D., Nowozin, S., et al. (2019). Can you trust your model's uncertainty? Evaluating predictive uncertainty under dataset shift. *NeurIPS*. arXiv:1906.02530
- Parisi, F., Strino, F., Nadler, B., & Kluger, Y. (2014). Ranking and combining multiple predictors without labeled data. *PNAS*, 111(4), 1253–1258. https://doi.org/10.1073/pnas.1219097111
- Riley, R. D., Ensor, J., Snell, K. I. E., Debray, T. P. A., et al. (2016). External validation of clinical prediction models using big datasets from e-health records or IPD meta-analysis: opportunities and challenges. *BMJ*, 353, i3140. https://doi.org/10.1136/bmj.i3140
- Rosenfeld, E., & Garg, S. (2023). (Almost) provable error bounds under distribution shift via disagreement discrepancy. *NeurIPS*. arXiv:2306.00312
- Saerens, M., Latinne, P., & Decaestecker, C. (2002). Adjusting the outputs of a classifier to new a priori probabilities: A simple procedure. *Neural Computation*, 14(1), 21–41. https://doi.org/10.1162/089976602753284446
- Sun, W., & Cai, T. T. (2007). Oracle and adaptive compound decision rules for false discovery rate control. *Journal of the American Statistical Association*, 102(479), 901–912. https://doi.org/10.1198/016214507000000545
- Tibshirani, R. J., Barber, R. F., Candès, E. J., & Ramdas, A. (2019). Conformal prediction under covariate shift. *NeurIPS*. arXiv:1904.06019

**缺失数据与插补**

- Bartlett, J. W., & Hughes, R. A. (2020). Bootstrap inference for multiple imputation under uncongeniality and misspecification. *Statistical Methods in Medical Research*, 29(12), 3533–3546. https://doi.org/10.1177/0962280220932189
- Cini, A., Marisca, I., & Alippi, C. (2022). Filling the G_ap_s: Multivariate time series imputation by graph neural networks. *ICLR*. arXiv:2108.00298
- Du, W., Côté, D., & Liu, Y. (2023). SAITS: Self-attention-based imputation for time series. *Expert Systems with Applications*, 219, 119619. https://doi.org/10.1016/j.eswa.2023.119619
- Du, W., Wang, J., Qian, L., Yang, Y., Ibrahim, Z., Liu, F., et al. (2024). TSI-Bench: Benchmarking time series imputation. arXiv:2406.12747
- Hughes, R. A., Heron, J., Sterne, J. A. C., & Tilling, K. (2019). Accounting for missing data in statistical analyses: multiple imputation is not always the answer. *International Journal of Epidemiology*, 48(4), 1294–1304. https://doi.org/10.1093/ije/dyz032
- Khayati, M., Lerner, A., Tymchenko, Z., & Cudré-Mauroux, P. (2020). Mind the gap: An experimental evaluation of imputation of missing values techniques in time series. *Proceedings of the VLDB Endowment*, 13(5), 768–782. https://doi.org/10.14778/3377369.3377383
- Meng, X.-L. (1994). Multiple-imputation inferences with uncongenial sources of input. *Statistical Science*, 9(4), 538–558. https://doi.org/10.1214/ss/1177010269
- Näf, J., Spohn, M.-L., Michel, L., & Meinshausen, N. (2023). Imputation scores. *Annals of Applied Statistics*, 17(3), 2452–2472. https://doi.org/10.1214/22-AOAS1727
- Näf, J., Scornet, E., & Josse, J. (2024). What is a good imputation under MAR missingness? arXiv:2403.19196
- Nie, T., Qin, G., Ma, W., Mei, Y., & Sun, J. (2024). ImputeFormer: Low rankness-induced transformers for generalizable spatiotemporal imputation. *Proceedings of KDD 2024*. https://doi.org/10.1145/3637528.3671751
- Tashiro, Y., Song, J., Song, Y., & Ermon, S. (2021). CSDI: Conditional score-based diffusion models for probabilistic time series imputation. *NeurIPS*. arXiv:2107.03502
- von Hippel, P. T. (2018). How many imputations do you need? A two-stage calculation using a quadratic rule. *Sociological Methods & Research*, 49(3), 699–718. https://doi.org/10.1177/0049124117747303
- White, I. R., & Carlin, J. B. (2010). Bias and efficiency of multiple imputation compared with complete-case analysis for missing covariate values. *Statistics in Medicine*, 29(28), 2920–2931. https://doi.org/10.1002/sim.3944
- Wu, H., Hu, T., Liu, Y., Zhou, H., Wang, J., & Long, M. (2023). TimesNet: Temporal 2D-variation modeling for general time series analysis. *ICLR*. arXiv:2210.02186
- Xie, X., & Meng, X.-L. (2016). Dissecting multiple imputation from a multi-phase inference perspective: What happens when God's, imputer's and analyst's models are uncongenial? *Statistica Sinica*. https://doi.org/10.5705/ss.2014.067

**极值统计与极端事件的评价**

- Allen, S., Ginsbourger, D., & Ziegel, J. (2023). Evaluating forecasts for high-impact events using transformed kernel scores. *SIAM/ASA Journal on Uncertainty Quantification*, 11, 906–940. https://doi.org/10.1137/22M1532184
- Gnecco, N., Terefe, E. M., & Engelke, S. (2024). Extremal random forests. *Journal of the American Statistical Association*, 119, 3059–3072. https://doi.org/10.1080/01621459.2023.2300522
- Gneiting, T. (2011). Making and evaluating point forecasts. *Journal of the American Statistical Association*, 106(494), 746–762. https://doi.org/10.1198/jasa.2011.r10138
- Gneiting, T., & Raftery, A. E. (2007). Strictly proper scoring rules, prediction, and estimation. *Journal of the American Statistical Association*, 102(477), 359–378. https://doi.org/10.1198/016214506000001437
- Gneiting, T., & Ranjan, R. (2011). Comparing density forecasts using threshold- and quantile-weighted scoring rules. *Journal of Business & Economic Statistics*, 29(3), 411–422. https://doi.org/10.1198/jbes.2010.08110
- Lerch, S., Thorarinsdottir, T. L., Ravazzolo, F., & Gneiting, T. (2017). Forecaster's dilemma: Extreme events and forecast evaluation. *Statistical Science*, 32(1), 106–127. https://doi.org/10.1214/16-STS588
- McVittie, J. H., & Murphy, O. A. (2025). Estimating extreme wave surges in the presence of missing data. *Environmetrics*, 36(6), e70036. https://doi.org/10.1002/env.70036
- Pasche, O. C., & Engelke, S. (2024). Neural networks for extreme quantile regression with an application to forecasting of flood risk. *Annals of Applied Statistics*, 18(4), 2818–2839. https://doi.org/10.1214/24-AOAS1907
- Robinson, M. E., & Tawn, J. A. (2000). Extremal analysis of processes sampled at different frequencies. *Journal of the Royal Statistical Society Series B*, 62(1), 117–135. https://doi.org/10.1111/1467-9868.00223
- Shen, X., & Meinshausen, N. (2025). Engression: Extrapolation through the lens of distributional regression. *Journal of the Royal Statistical Society Series B*, 87(3), 653–677. https://doi.org/10.1093/jrsssb/qkae108
- Simpson, E. S., & Northrop, P. J. (2026). Accounting for missing data when modelling block maxima. *Environmetrics*, 37(2), e70075. https://doi.org/10.1002/env.70075
- Velthoen, J., Dombry, C., Cai, J.-J., & Engelke, S. (2023). Gradient boosting for extreme quantile regression. *Extremes*, 26(4), 639–667. https://doi.org/10.1007/s10687-023-00473-x

**工业界与中国团队的天气、洪水模型**

- Bi, K., Xie, L., Zhang, H., Chen, X., Gu, X., & Tian, Q. (2023). Accurate medium-range global weather forecasting with 3D neural networks. *Nature*, 619, 533–538. https://doi.org/10.1038/s41586-023-06185-3
- Bodnar, C., Bruinsma, W. P., Lucic, A., Stanley, M., Allen, A., Brandstetter, J., et al. (2025). A foundation model for the Earth system. *Nature*, 641, 1180–1187. https://doi.org/10.1038/s41586-025-09005-y
- Chen, L., Zhong, X., Zhang, F., Cheng, Y., Xu, Y., Qi, Y., & Li, H. (2023). FuXi: a cascade machine learning forecasting system for 15-day global weather forecast. *npj Climate and Atmospheric Science*, 6, 190. https://doi.org/10.1038/s41612-023-00512-1
- Kurth, T., Subramanian, S., Harrington, P., Pathak, J., Mardani, M., Hall, D., et al. (2023). FourCastNet: Accelerating global high-resolution weather forecasting using adaptive Fourier neural operators. *Proceedings of PASC '23*. https://doi.org/10.1145/3592979.3593412
- Lam, R., Sanchez-Gonzalez, A., Willson, M., Wirnsberger, P., Fortunato, M., Alet, F., et al. (2023). Learning skillful medium-range global weather forecasting. *Science*, 382, 1416–1421. https://doi.org/10.1126/science.adi2336
- Olivetti, L., & Messori, G. (2024). Do data-driven models beat numerical models in forecasting weather extremes? A comparison of IFS HRES, Pangu-Weather, and GraphCast. *Geoscientific Model Development*, 17, 7915–7962. https://doi.org/10.5194/gmd-17-7915-2024
- Price, I., Sanchez-Gonzalez, A., Alet, F., Andersson, T. R., El-Kadi, A., Masters, D., et al. (2025). Probabilistic weather forecasting with machine learning. *Nature*, 637, 84–90. https://doi.org/10.1038/s41586-024-08252-9
- Rasp, S., Hoyer, S., Merose, A., Langmore, I., Battaglia, P., Russell, T., et al. (2024). WeatherBench 2: A benchmark for the next generation of data-driven global weather models. *Journal of Advances in Modeling Earth Systems*, 16, e2023MS004019. https://doi.org/10.1029/2023MS004019
- Richardson, D. S. (2000). Skill and relative economic value of the ECMWF ensemble prediction system. *Quarterly Journal of the Royal Meteorological Society*, 126, 649–667. https://doi.org/10.1002/qj.49712656313
- Xu, W., Chen, K., Han, T., Chen, H., Ouyang, W., & Bai, L. (2024). ExtremeCast: Boosting extreme value prediction for global weather forecast. arXiv:2402.01295
- Zhang, Y., Long, M., Chen, K., Xing, L., Jin, R., Jordan, M. I., & Wang, J. (2023). Skilful nowcasting of extreme precipitation with NowcastNet. *Nature*, 619, 526–532. https://doi.org/10.1038/s41586-023-06184-4

**检验层级、空间验证、稳健性与确认性研究**

- Bouthillier, X., Delaunay, P., Bronzi, M., Trofimov, A., Nichyporuk, B., Szeto, J., et al. (2021). Accounting for variance in machine learning benchmarks. *MLSys*. arXiv:2103.03098
- Broderick, T., Giordano, R., & Meager, R. An automatic finite-sample robustness metric: When can dropping a little data make a big difference? arXiv:2011.14999
- Chambers, C. D., & Tzavella, L. (2022). The past, present and future of Registered Reports. *Nature Human Behaviour*, 6, 29–42. https://doi.org/10.1038/s41562-021-01193-7
- Coron, L., Andréassian, V., Perrin, C., Lerat, J., Vaze, J., Bourqui, M., & Hendrickx, F. (2012). Crash testing hydrological models in contrasted climate conditions: An experiment on 216 Australian catchments. *Water Resources Research*, 48, W05552. https://doi.org/10.1029/2011WR011721
- Dror, R., Baumer, G., Shlomov, S., & Reichart, R. (2018). The hitchhiker's guide to testing statistical significance in natural language processing. *Proceedings of ACL 2018*. https://doi.org/10.18653/v1/P18-1128
- Dror, R., Shlomov, S., & Reichart, R. (2019). Deep dominance — how to properly compare deep neural models. *Proceedings of ACL 2019*, 2773–2785. https://doi.org/10.18653/v1/P19-1266
- Dwork, C., Feldman, V., Hardt, M., Pitassi, T., Reingold, O., & Roth, A. (2015). The reusable holdout: Preserving validity in adaptive data analysis. *Science*, 349(6248), 636–638. https://doi.org/10.1126/science.aaa9375
- Ewen, J., & Parkin, G. (1996). Validation of catchment models for predicting land-use and climate change impacts. 1. Method. *Journal of Hydrology*, 175, 583–594. https://doi.org/10.1016/S0022-1694(96)80026-6
- Foster, E. D., & Deardorff, A. (2017). Open Science Framework (OSF). *Journal of the Medical Library Association*, 105(2). https://doi.org/10.5195/jmla.2017.88
- Henderson, P., Islam, R., Bachman, P., Pineau, J., Precup, D., & Meger, D. (2018). Deep reinforcement learning that matters. *Proceedings of the AAAI Conference on Artificial Intelligence*, 32. https://doi.org/10.1609/aaai.v32i1.11694
- Kapoor, S., & Narayanan, A. (2023). Leakage and the reproducibility crisis in machine-learning-based science. *Patterns*, 4, 100804. https://doi.org/10.1016/j.patter.2023.100804
- Klemeš, V. (1986). Operational testing of hydrological simulation models. *Hydrological Sciences Journal*, 31(1), 13–24. https://doi.org/10.1080/02626668609491024
- McColl, K. A., Vogelzang, J., Konings, A. G., Entekhabi, D., Piles, M., & Stoffelen, A. (2014). Extended triple collocation: Estimating errors and correlation coefficients with respect to an unknown target. *Geophysical Research Letters*, 41(17), 6229–6236. https://doi.org/10.1002/2014GL061322
- Meyer, H., & Pebesma, E. (2021). Predicting into unknown space? Estimating the area of applicability of spatial prediction models. *Methods in Ecology and Evolution*, 12, 1620–1633. https://doi.org/10.1111/2041-210X.13650
- Meyer, H., & Pebesma, E. (2022). Machine learning-based global maps of ecological variables and the challenge of assessing them. *Nature Communications*, 13, 2208. https://doi.org/10.1038/s41467-022-29838-9
- Nosek, B. A., Ebersole, C. R., DeHaven, A. C., & Mellor, D. T. (2018). The preregistration revolution. *PNAS*, 115(11), 2600–2606. https://doi.org/10.1073/pnas.1708274114
- Ploton, P., Mortier, F., Réjou-Méchain, M., Barbier, N., Picard, N., Rossi, V., et al. (2020). Spatial validation reveals poor predictive performance of large-scale ecological mapping models. *Nature Communications*, 11, 4540. https://doi.org/10.1038/s41467-020-18321-y
- Refsgaard, J. C., & Henriksen, H. J. (2004). Modelling guidelines—terminology and guiding principles. *Advances in Water Resources*, 27, 71–82. https://doi.org/10.1016/j.advwatres.2003.08.006
- Refsgaard, J. C., & Knudsen, J. (1996). Operational validation and intercomparison of different types of hydrological models. *Water Resources Research*, 32(7), 2189–2202. https://doi.org/10.1029/96WR00896
- Renard, B., Lang, M., Bois, P., Dupeyrat, A., Mestre, O., Niel, H., et al. (2008). Regional methods for trend detection: Assessing field significance and regional consistency. *Water Resources Research*, 44, W08419. https://doi.org/10.1029/2007WR006268
- Roberts, D. R., Bahn, V., Ciuti, S., Boyce, M. S., Elith, J., Guillera-Arroita, G., et al. (2017). Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. *Ecography*, 40, 913–929. https://doi.org/10.1111/ecog.02881
- Seibert, J. (2001). On the need for benchmarks in hydrological modelling. *Hydrological Processes*, 15, 1063–1064. https://doi.org/10.1002/hyp.446
- Seibert, J., Vis, M. J. P., Lewis, E., & van Meerveld, H. J. (2018). Upper and lower benchmarks in hydrological modelling. *Hydrological Processes*, 32, 1120–1125. https://doi.org/10.1002/hyp.11476
- Simonsohn, U., Simmons, J. P., & Nelson, L. D. (2020). Specification curve analysis. *Nature Human Behaviour*, 4, 1208–1214. https://doi.org/10.1038/s41562-020-0912-z
- Steegen, S., Tuerlinckx, F., Gelman, A., & Vanpaemel, W. (2016). Increasing transparency through a multiverse analysis. *Perspectives on Psychological Science*, 11(5), 702–712. https://doi.org/10.1177/1745691616658637
- Stoffelen, A. (1998). Toward the true near-surface wind speed: Error modeling and calibration using triple collocation. *Journal of Geophysical Research: Oceans*, 103(C4), 7755–7766. https://doi.org/10.1029/97JC03180
- Thirel, G., Andréassian, V., Perrin, C., Audouy, J.-N., Berthet, L., Edwards, P., et al. (2015). Hydrology under change: an evaluation protocol to investigate how hydrological models deal with changing catchments. *Hydrological Sciences Journal*, 60(7–8), 1184–1199. https://doi.org/10.1080/02626667.2014.967248
- Wadoux, A. M. J.-C., Heuvelink, G. B. M., de Bruin, S., & Brus, D. J. (2021). Spatial cross-validation is not the right way to evaluate map accuracy. *Ecological Modelling*, 457, 109692. https://doi.org/10.1016/j.ecolmodel.2021.109692
- Wilks, D. S. (2016). "The stippling shows statistically significant grid points": How research results are routinely overstated and overinterpreted, and what to do about it. *Bulletin of the American Meteorological Society*, 97(12), 2263–2273. https://doi.org/10.1175/BAMS-D-15-00267.1
