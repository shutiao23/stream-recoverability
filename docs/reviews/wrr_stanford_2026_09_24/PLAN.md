# v18 修改计划 — 从 major revision 走到 accept

> **状态：已全部执行完毕（2026-09-24）。** 实际结果、三条失败的预注册预测和三处
> 对论文不利的发现，见同目录的 [STATUS.md](STATUS.md)。论文在 `paper_archived/v18/`，
> 回应函在 `paper_archived/v18/RESPONSE.md`。

针对 `docs/reviews/wrr_stanford_2026_09_24/REVIEW.md` 的七条主要意见。每个实验
给出：为什么审稿人要它、怎么做、写到哪个脚本和产物、**做之前先写下的可证伪预测**、
验收标准、以及它改变正文的哪一段。

排序原则：**先做能改变结论的，再做能补强结论的，最后做写作**。E1/E2/E3 三条
如果不做，这篇稿子在 WRR 拿不到 accept；E4/E5/E6 决定分数高低；E7 是防御性的。

---

## 阶段 0 — 立刻修正的事实错误（半天，必须先做）

**0.1 Johnson et al. (2021) 的填补上限是 20 周，不是 13 周。**
原文摘要：`imputation of missing data expanded this range to approximately 20
weeks`，结论句：`more than approximately seven consecutive weeks of missing data
or 20 weeks of imputed data`。仓库里
`src/stream_recoverability/experiments/v17_fitness/frontier.py:22` 写死
`JOHNSON_FILLED_DAYS = 91`，正文 §1 和 §5.4 随之错。

- 改 `JOHNSON_FILLED_DAYS = 140`，重跑 `184`、`187`、`192`、`193`、`199`。
- §1 改写为："seven weeks unfilled, twenty weeks with imputation"。
- §5.4 的"thirteen-week guideline"操作点整段重算。注意 91 天比 140 天**更严**，
  所以现在这个操作点其实是**高估**了现行规则的表现，改过来之后对比只会更有利；
  但这不影响它是一个必须修的引用错误。

**0.2 说清楚 Johnson 的估计量不是你的估计量。**
他们估的是正弦回归拟合出的 mean / phase / amplitude，不是最热 30 天均值。现在
的行文有"打稻草人"的风险。§1 必须显式写：该指南是为正弦拟合年参数导出的，而
实践中被外推到它没有验证过的端点上；**并且把这个外推用引用坐实**（见 0.3）。

**0.3 把"现行实践"文献化。**
现在 §1 那句 "Agency monitoring standards specify a minimum share of the year"
一个引用都没有，而整篇论文的前提就是这个实践存在。需要补：
(a) 至少 3 份机构监测标准/QA 手册里写明完整度阈值的原文（USGS、EPA 区域水温
准则、欧洲机构的 QA 文档、州级 TMDL 水温监测协议）；
(b) 至少 5 篇**先用完整度阈值筛年、再报告夏季统计量**的已发表研究，作为"外推
确实在发生"的证据；
(c) WRR 参考文献 6 条太少，目标 35–50 条，补齐热状态指标、冷水准则、
air–water 回归、large-sample hydrology 基准（Caravan 一类）的引用。

---

## 阶段 1 — 三个决定成败的实验

### E1 — 真实断测的季节学，用来解释 empirical arm 的空结果

**审稿人为什么要它.** §5.7 报告了 empirical arm 上确认集效应 −0.71 点、区间含 0，
但没有解释。一个没有解释的空结果，在审稿人眼里等于"你的方法在现实里没用"。

**做法.** 对全部 457 个站的原始序列提取真实内部断测（`probe.py::probe_informative_missingness`
已经实现）：起始月份、长度、断测前后 7 天相对于该站 day-of-year 气候态的距平。
按长度分层统计起始月份分布，做均匀性 χ² 检验。

**已经跑出来的结果（可直接引用，已复现）.** 6,472 个真实断测；中位长度 2 天，
95 分位 43 天；≥30 天的 466 个断测起始月份显著非均匀，χ² = 44.3，p = 6.5×10⁻⁶；
**55.8% 起始于 9 月–次年 1 月，30.7% 起始于 3–7 月**。

**可证伪预测（写在跑之前）.** 若长断测起始月份均匀，则 empirical arm 的空结果
无法用季节性解释，必须归因于样本量，结论要相应削弱。

**验收.** 新增一个小节（建议放在 §5.7 之前，作为"这些网络实际经历什么"），
给出月度分布表 + χ²；§5.7 的空结果用它解释；§6 的维护排期建议从假设性变成实测性。

**产物.** `results/v18/e1_outage_seasonality/`，脚本 `scripts/210_v18_outage_seasonality.py`。

---

### E2 — 在 2,422 个真实残缺站年上部署两条规则（闭环的关键一环）

**审稿人为什么要它.** 目前全部结论都建立在"完整年 + 人造洞"上，规则从未作用于
一条真有窟窿的记录。而这些记录就在你们自己的档案库里，占 32%。

**做法.** 分三层，一层比一层强，**全部都要做**：

**E2a 决策翻转率（无需真值）.** 对每个真实残缺站年算 longest_run 与
peak_missing_fraction（峰值窗口由该站完整年的气候态确定）。在等保留率下比较
Johnson 未填补限（≤49 d）与 timing 规则，报告交叉表。

已跑出的结果：长度规则接纳 83.2%，timing 规则接纳 81.2%，**15.1% 的站年决定相反**；
**207 个被长度规则接纳、被 timing 拒绝**（今天正带着被遮蔽的峰值窗口进入档案库）；
**158 个被长度拒绝、被 timing 接纳**（长但避开峰值，被白丢）。另有 28.7% 的残缺
站年至少丢失一个峰值窗口日，261 个丢失超过一半峰值窗口。

**E2b 风险迁移（模型外推，必须明确标注）.** 把确认过的 conformal 对象作用到真实
残缺站年上，报告两条规则各自接纳集的**预测**后果性误差率。必须在正文写明这是
model-based extrapolation，并写明它依赖的可交换性假设，以及 E7 对该假设的检验。

**E2c 区域结论是否改变.** 在两条规则各自接纳的档案上重算一个区域量：超过冷水
准则的站年计数、年峰值分布、以及（如果记录长度允许）区域趋势。**结果朝哪个方向
都要报**；如果没变，那是一个有用的、去戏剧化的结论。

**可证伪预测.** 若翻转率 < 3%，则换轴在现实档案上是无关紧要的，论文应降级为
纯机制论文，不得再给运行建议。（实测 15.1%，预测被推翻的风险已排除。）

**验收.** 新增 §5.11 "Deployment on the incomplete archive"，含交叉表、两个整数
（207 / 158）、迁移风险、区域量变化。这一节应该是论文最好的一张图。

**产物.** `results/v18/e2_archive_deployment/`，`scripts/211_v18_archive_deployment.py`。

---

### E3 — 在 Johnson 自己的估计量上复现轴对比（把最大软肋变成最强结果）

**审稿人为什么要它.** 你在纠正一份指南，但用的是另一个估计量。把它在**他们自己的
估计量**上做一遍，指控就消失了，而且能解释他们自己报告的"inconsistent in space
and time"。

**做法.** 在同一批 5,114 个完整站年上实现 Johnson 的正弦回归：
`T(t) = mean + amplitude · sin(2π(t − phase)/365)`，最小二乘拟合，取 mean、phase、
amplitude 三个参数作为三个新端点。对每个端点按现有方式计算 AUC(peak_overlap)、
AUC(warm_observed_fraction)、AUC(longest_run)、AUC(missing_fraction)，带 network
聚类区间，并做 0.25/0.47/1.0 三档容差扫描。

**可证伪预测（务必先写下来）.**
- 正弦 **mean** 是全年泛函 → length 轴胜（与 annual_mean 一致）。
- 正弦 **phase** 是位置参数 → timing 轴胜，且优势应大于 amplitude。
- 正弦 **amplitude** 由夏冬两端共同决定 → 介于两者之间，优势小而为正
  （与现有 amplitude30 的 +0.024 一致）。
- 因此 Johnson 在三个参数上同时观察，看到的必然是"时而有效时而无效"。

**验收.** 三个预测全中 → §6 "Why the standing guidance saw an inconsistency"
从解释升级为测量，claim matrix 里 M3 从 "interpretation" 升级为 "stands"。
任何一个不中 → 必须在论文里报告，并重新审视二分律的普适性。

**产物.** `results/v18/e3_sine_endpoints/`，`scripts/212_v18_sine_endpoints.py`。

---

## 阶段 2 — 三个决定分数高低的实验

### E4 — 保留集的代表性，以及 error–representativeness 前沿

**审稿人为什么要它.** §5.3 问的是"哪些流域**受益**更多"，没问"筛完之后**留下**
了哪些站"。一条靠丢掉困难站点来降低平均误差的规则，是用代表性换精度，而在这个
应用里困难站点恰好是高海拔冷水源头——正是算夏季极值的理由。

**已跑出的结果.** 70% 保留率下，每站保留率与站点高程的 Spearman 相关：
- 校准筛：development ρ = **−0.259 (p = 0.011)**，reserved ρ = **−0.273 (p = 0.077)**
- 长度规则：development ρ = −0.053 (p = 0.60)，reserved ρ = −0.101 (p = 0.52)

即**长度规则对高程中性，校准筛不是**。按 donor regime 看更明显：development 上
校准筛保留无 donor 站年的 **57.1%**、donor 丰富站年的 **72.5%**；长度规则是
73.6% / 68.8%，方向相反。每站保留率的标准差从 0.095 升到 0.151，最差 network 的
保留率从 37.5% 掉到 27.6%。保留档案的平均年峰值偏移 **+0.18 °C**（长度规则
+0.01 °C），相当于目标量年际标准差的三分之一的选择性暖偏。

**设计贡献（这才是重点）.** 把它做成一条可选择的前沿，而不是一个认错：
- 方案 A：全局阈值（现状）。
- 方案 B：按 donor regime 分层等保留率。实测代价 development 2.93% → **3.17%**
  （0.23 点），reserved 2.53% → **2.52%**（免费），donor regime 保留率完全拉平。
- 方案 C：按高程分位分层。**注意：方案 B 修不好高程偏斜**（分层后 ρ 仍为 −0.235），
  要高程中性必须直接对高程分层，代价需要实测。
- 画出「后果性误差率 vs 代表性失真度」的权衡曲线，代表性失真度用保留率与属性的
  Spearman |ρ|、或保留档案与全档案在属性分布上的 Wasserstein 距离来度量。

**可证伪预测.** 若分层的代价超过 1 个百分点，则代表性与精度存在实质冲突，必须在
建议里明写；若低于 0.5 点（实测 0.23），则应把分层筛作为**默认推荐**。

**验收.** 新增 §5.12 与一张前沿图；§6 的建议改为"按支撑集换轴 + 分层施加阈值"。

**产物.** `results/v18/e4_representativeness/`，`scripts/213_v18_representativeness.py`。
（`probe.py::probe_representativeness` 已有可直接搬运的实现。）

---

### E5 — 把气温强迫补齐到全部 457 个站

**审稿人为什么要它.** 气温驱动回归是这个领域填补水温的标准方法（Beaufort et al.
2022 就是用它重建热峰值的），而本文的 air 分支只覆盖 **development 2.3% /
reserved 0.85%** 的 case。同时 110 个 development network 里有 36 个完全没有同步
donor——对这些站，整个估计器库只剩气候态和插值。§5.5 的"对手没有被削弱"论证因此
有一个明显的缺口。

**做法.**
1. 补站点坐标：GAGES-II 已有 140 个美国站的经纬度；其余八个机构的站点坐标都公开
   （USGS NWIS site service、FOEN、NVE HydAPI、SYKE、ARSO、CHMI、GKD、LUBW、RWS）。
   落地为 `data/interim/v18_station_coordinates.csv`，带来源和匹配方式两列。
2. 拉 ERA5-Land 或 NASA POWER 日尺度 2 m 气温，按最近格点匹配，
   落地 `data/interim/v18_air_forcing.parquet`。
3. 重新启用 air ridge，并**新增一个真正对标 Beaufort 的估计器**：以气温为唯一
   预测子、带季节项的回归（非线性 S 型或分段线性），对每个站 leave-one-year-out 拟合。
4. 重跑：RQ0 的问题规模（1.305 / 0.402 / 0.242 / 0.165 这四个数）、Table 3 的
   oracle 行、以及 §5.6 的估计器选择比例。

**可证伪预测.** 轴的结论**不应**改变（它是关于哪些 case 难，不是关于修得多好），
但 best-reconstruction 基线应当下降，尤其在无 donor 的 36 个 network 上；若轴的
结论改变，则 H1 的证据依赖于估计器库的贫乏，必须重新评估。

**验收.** Table 3 增加 "always air regression (Beaufort-style)" 一行；§5.1 四个
数字更新；N2（air 分支不泛化）这条 not-claimed 撤销或改写。

**产物.** `results/v18/e5_air_forcing/`，`scripts/214_v18_air_forcing.py`。

---

### E6 — 支撑宽度连续律（把"反转"升级成"定律"）

**审稿人为什么要它.** 这是把 novelty 从 6.5 推到 7.5–8 的唯一一步，而且成本极低。

**核心观察.** Table 1 里的两条 timing 轴，`warm_observed_fraction` 其实是
**限制在窗口内的缺失天数计数**——它是一个长度度量。在 development case 上它与
longest_run 相关 −0.863、与 total_missing 相关 −0.855。所以真正的定律不是
"timing 打败 length"，而是：**缺失必须在估计量的支撑集上度量，而不是在日历年上度量**。
"timing vs length"只是估计量为极值时的特例。证据已经在你们自己的
`metric_generality.csv` 里：`warm_observed_fraction` 对五个端点中的**每一个**都在
最优轴的 0.03 AUC 以内。

**做法.** 在现有完整站年上计算最热 *k* 日均值，k ∈ {1, 3, 7, 15, 30, 60, 90, 182, 365}
（k = 365 即年均值）。对每个 k：
- 定义支撑集 = 该站气候态最热 k 日窗口；
- 计算"支撑集内缺失比例"这一条统一轴；
- 报告 AUC(支撑集轴) − AUC(全年缺失比例)，带 network 聚类区间；
- 把这个差对 log k 作图。

**可证伪预测.** 该差应随 k 单调递减，在 k → 365 时趋于 0（甚至略负），并在某个
k\* 处穿越 0；且统一轴对每个 k 都不劣于 max(peak_overlap, longest_run) 超过噪声。
若曲线非单调，说明还有第二个因素（很可能是极值窗口的年际漂移），必须找出来。

**验收.** 一张图 + 一个表 + 标题改写。建议新标题方向：
*"Missingness must be measured on the support of the estimand: a continuous law
for screening gap-affected stream-temperature records"*。摘要把二分作为推论呈现。

**产物.** `results/v18/e6_support_width/`，`scripts/215_v18_support_width.py`。

---

## 阶段 3 — 防御性实验

### E7 — 缺失是否是信息性的（MNAR 检验）

**审稿人为什么要它.** 全部 case 都是"把 mask 移植到完整年上"，这只有在 mask 与被
遮蔽的值条件独立时才成立。洪水冲走仪器、结冰掩埋、枯水期附着污染——都与异常热状态
同时发生。不检验就是一个洞。

**已跑出的结果（对论文有利，应主动写出来）.** 6,472 个真实断测，断测前 7 天相对
day-of-year 气候态的平均距平：1–7 天断测 +0.018 °C (p = 0.44)，8–29 天 +0.038 °C
(p = 0.56)，30–89 天 −0.002 °C (p = 0.98)，仅 ≥90 天为 −0.215 °C (p = 0.081，n = 150)。
即**绝大多数真实断测的可交换性在经验上站得住**，只有超长断测有一点结构。

**要补的更强版本.** 再加两个检验：(a) 断测发生概率对当日气温/流量距平的 logistic
回归（有强迫数据之后，E5 的副产品）；(b) 与该 network 同期其他站的距平比较，检验
断测期间是否系统性偏冷/偏热。

**验收.** 新增一段 + 一个表；§7 的限制条款收窄到"≥90 天的断测"。

**产物.** `results/v18/e7_informative_missingness/`，`scripts/216_v18_mnar.py`。

---

## 阶段 4 — 架构图与系统设计图（draw.io）

**审稿人意见（minor 10）.** 一篇贡献是"决策流程"的论文，没有一张图说明这个流程
是什么：输入是什么、哪些信息禁止读取、标定在哪一步、两个动作空间分别在哪。
Figure 1–6 全是结果图。

**硬性要求（来自作者）.** 所有架构图必须在 draw.io 里画，源文件入库，导出 PDF 进
论文。落地方式见 `figures/v17/drawio/README.md`：

| 图 | 文件 | 内容 |
|---|---|---|
| Fig. 0 | `f0_problem_frame.drawio` | 问题框定：同一条记录、两个估计量、两个支撑集、两条轴，为什么单一完整度阈值不可能同时对 |
| Fig. 1 | `f1_system_architecture.drawio` | 筛选系统架构：输入特征组、信息屏障（禁止读取被遮蔽日）、估计器库与支持性判定、选择后 conformal 标定、两个动作空间（准入 / 弃权） |
| Fig. 2 | `f2_experiment_design.drawio` | 实验设计与数据流：146 network → 110/36 分层划分 → 两个断测 arm → 估计器 → 端点 → gate → 冻结 → 一次性开封 |
| Fig. 3 | `f3_evidence_chain.drawio` | 证据闭环：RQ0…RQ8 与 claim ID 的对应，标出哪些环闭合、哪两环（E2 部署、E2c 下游）待补 |
| Fig. 4 | `f4_deployment_workflow.drawio` | 机构部署工作流：一个机构周一早上按什么顺序做什么，三变量规则的落地路径 |

导出：`make figures-drawio`。环境中若装有 draw.io 桌面版，走官方
`drawio -x -f pdf`；否则走仓库内的 `scripts/205_v17_drawio_export.py`，它解析同一份
`.drawio` XML 渲染 SVG 再转 PDF，保证 PDF 与源文件同源。

---

## 阶段 5 — 写作层面的修改

1. **摘要 / key points 改口.** 主运行结论必须 arm-specific。建议写法：机制在两个
   arm 上都成立且方向一致；运行收益在长断测覆盖暖季的 regime 上为 −8.7 点，在这些
   网络当前经历的断测几何下不可分辨（−0.71，区间含 0），并给出真实档案里落在前一
   regime 的比例（28.7%）。
2. **标题改为支撑集律**（E6 之后）。
3. **§5.11 部署一节**（E2）、**§5.12 代表性一节**（E4）为新增。
4. **§7 限制**：收窄 MNAR 条款到 ≥90 天；新增"筛选会改变档案组成"条款并指向 §5.12。
5. **参考文献扩到 35–50 条**（阶段 0.3）。
6. **Theil–Sen 趋势那一段**：457 个站平均 11 年，10 个点估不出十年趋势。要么降为
   一句话，要么把斜率不确定度和 RMSE 并列报出来。
7. **claim matrix 更新**：新增 E1–E7 的 claim ID，M3 升级，N2 撤销或改写，
   新增 "the retained archive is not a random subsample" 这一条。

---

## 优先级与工作量

| 步骤 | 工作量 | 不做的后果 |
|---|---|---|
| 阶段 0 引用修正 | 0.5 天 | 被指南作者当场抓到，直接 reject |
| E1 断测季节学 | 1 天（探针已实现） | 空结果无解释 |
| E2 真实档案部署 | 3–4 天 | 闭环不闭，"would work" 而非 "does work" |
| E3 正弦端点 | 2–3 天 | 稻草人指控成立 |
| E4 代表性前沿 | 2 天（探针已实现） | 最容易被机构读者抓住的漏洞 |
| E5 气温强迫 | 4–5 天（含下载与匹配） | 公平性论证有缺口 |
| E6 支撑宽度律 | 2 天 | novelty 停在 6.5 |
| E7 MNAR | 1 天（探针已实现） | 设计假设未检验 |
| draw.io 五张图 | 1–2 天 | 决策流程无法被复现 |
| 重写 | 3–4 天 | — |

**总计约 20–25 个工作日。** 如果只能做三件事：阶段 0 + E2 + E3。
