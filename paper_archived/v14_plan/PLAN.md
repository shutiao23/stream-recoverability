# v14 执行计划:从"预测模型误差"转向"预测重建收益"

状态:**P0–P3 已执行(GO),P5 写作草稿已建立**。P0 全部四项门(G1–G4)在第二面板通过
(网络级逐时长 Spearman 0.718/0.551/0.662/0.647;placement 级 90/180 d 通过、7/30 d 处于
0.25–0.35 部分区间)。完整记录见 `paper/v14_plan/EXECUTION_STATUS.md`,门判定见
`results/v14/p0_differential/REPORT.md`。取代 `paper/development_v13/` 的修补路线。

**修订备注(2026-09-03):** §3.4 的 G2/G3 已在对抗性审稿(依据 `paper/v14_plan/REVIEW_v14.md`
Major 1,修订发生在任何新实验数据之前)后重定义:原 G2(配对 Δρ vs 旧风险曲线)降级为诊断,
原 G3(跨时长 top-20% ≥ 1.3× 全panel、有害率 < 15%)作废。§3.4 原文保持不动,作为历史记录;
完整修订日志见 protocol_v5.md "Gate revision log (2026-09-03)"与
`results/v14/p0_differential/GATE_REVISION_v2.md`。

## 0. 一句话定位

> 把历史块压力测试同时施加于**恢复模型**和**它将要取代的默认处理方式**,预测两者之差(增量收益),
> 用于回答"哪些数据缺口值得重建"。

## 1. 为什么换:三个已验证的事实

| # | 事实 | 数值 | 来源 |
|---|---|---|---|
| F1 | 风险分数排"模型 MAE"有效,排"收益"无效且反向 | ρ = +0.726 vs **−0.230** | `t08/agent_a/placement_thermal_metrics.csv`, n=1965 |
| F2 | 真正排出收益的是**默认方法的难度**,不是模型的难度 | climatology_MAE→收益 ρ = **+0.659**;risk 与 climatology_MAE 仅相关 0.304 | 同上 |
| F3 | 换成"收益"作为预测对象,留一法可行性检验成立 | 收益排序 ρ **+0.363**;top-20% 预算每缺口收益 +0.147 → **+0.992 °C**;有害率 37.7% → **6.9%** | 同上,LOO station×duration |

F3 是评估期内留一法,属**可行性上界**,不是前瞻验证。P0 的任务就是把它变成真正的前瞻验证。

旧估计量失败的结构性原因:模型 MAE 已被 (station, duration) 两个可观测量决定,
因此任何按该二元组分组求均值的做法(r6)都能追平;而收益 = 默认难度 − 模型难度,
信号在被减数里,旧设计从未测量过被减数。

---

## 2. 阶段总览与判定门

| 阶段 | 内容 | 工期 | 判定门 |
|---|---|---|---|
| **P0** | 差分压力测试 —— 决胜实验 | 1 周 | **GO/NO-GO**,见 §3 |
| **P1** | 基线套件(含 R&H γ_m 先验技术) | 1 周 | 必须战胜 Tier-0 全部 |
| **P2** | 决策层(EC(ξ)/δ、风险–覆盖、REV) | 2 周 | 至少一条价值曲线全程为正 |
| **P3** | 边界与稳健性(非平稳分层、谐调) | 2 周 | 无硬门,产出边界刻画 |
| **P4** | 下游扩展(180/365 天、第三默认) | 1.5 周 | 无硬门 |
| **P5** | 写作 + protocol v5 + 外部注册 | 2 周 | 投稿 |

总计约 9.5 周。P0 是唯一的硬门:若 P0 失败,不进入 P1–P5(应对见 §3.5)。

---

## 3. P0:差分压力测试(决胜实验)

### 3.1 核心洞察 —— 现有机器可原样复用

`src/stream_recoverability/experiments/recovery_roster.py` 中:

- `fitting_period_empirical_losses(network_id, panel, placements, gaps=(7,30,90,180), ...)`
  在**内层拟合切分**内打分,返回逐 placement 的 `mae_deg_c`。
- `empirical_transfer_predictions(empirical_losses, evaluation_placements)`
  按 `(network_id, station_id, gap_length, season)` 分组求均值构建曲线,
  并实现四级回退(station×gap → network×gap → network mean)。

**关键点:`empirical_transfer_predictions` 对损失列是泛型的——它只对 `mae_deg_c` 做
groupby-mean。因此只要把喂进去的 `mae_deg_c` 换成"收益",曲线构建、支持层级、
回退逻辑、映射到评估 placement 的全部代码一行不改即可复用。**

### 3.2 需要新写的代码(估计 150–250 行)

新建 `src/stream_recoverability/experiments/differential_stress.py`:

```
def default_handling_losses(network_id, panel, placements, *, handler, ...) -> DataFrame
    # 与 fitting_period_empirical_losses 完全相同的内层切分与 placement 集合,
    # 但用 handler 而不是 XGBoost 来填补,返回同样 schema 的 mae_deg_c。
    # handler ∈ {climatology, linear_interp, nofill}

def differential_fitting_losses(model_losses, default_losses) -> DataFrame
    # 按 (network_id, station_id, gap_length, season, placement) 对齐,
    # 输出 schema 与 fitting_period_empirical_losses 一致,但
    #   mae_deg_c := default_mae − model_mae      ← 收益,可正可负
    # 保留 model_mae / default_mae 两列备查。
```

三个 handler 的实现成本:

| handler | 实现 | 成本 |
|---|---|---|
| climatology | 直接调用 `development_recovery._climatology_prediction(target, inner_fit_mask, index)` | **已存在**,传内层掩码即可 |
| linear_interp | 缺口两端点线性内插 | ~15 行 |
| nofill | 缺口日丢弃;MAE 未定义,只在下游指标层有意义 | 标记为不可计算,P4 处理 |

⚠ 必须保证:默认方法的参数(气候学日历日中位数)**只用内层拟合年份**估计,
与模型的训练掩码完全一致。否则收益曲线会泄漏。

### 3.3 实验设计

- **面板**:第一面板(42 网络 / 1,440 单元)先跑,作为开发;第二面板(57 网络 / 1,446 单元)作为前瞻验证。
- **切分**:沿用现有嵌套时序切分,不改。收益曲线建在**拟合年份**,在**评估年份**打分。
- **目标量**:评估期实现收益 `B = MAE_default − MAE_model`,逐 placement。
- **主指标**:
  - 分时长报告 Spearman(**不做跨时长池化**,见 §4.2);
  - 网络级 Spearman + 配对 network bootstrap(2000 draws);
  - (network × duration) 格内跨站点 Spearman 的均值/中位数/正比例。
- **必须并列的对照**(全部在同一批单元上算):
  1. 旧的经验风险曲线(模型 MAE 预测器)—— 预期为负,这是论文的反面基线;
  2. r6 的差分版:station × horizon 的历史收益均值;
  3. 仅缺口时长;
  4. 默认方法难度的历史曲线(单独作为预测器,因为 F2 显示它本身就强)。

### 3.4 GO 判定标准(投稿前冻结,不得事后放宽)

在第二面板直接支持时长上,**全部满足**才算 GO:

- **G1** 收益排序的网络级 Spearman ≥ 0.35,且配对 bootstrap 95% CI 下界 > 0;
- **G2** 显著优于旧风险曲线:配对 Δρ 的 95% CI 完全在零以上;
- **G3** top-20% 预算下每缺口平均实现收益 ≥ 全panel 平均的 1.3 倍,且有害处理率 < 15%;
- **G4** 至少在两个时长(7/30/90/180 中)上 G1 独立成立。

G1 的阈值 0.35 参照 F3 的 LOO 上界 0.363 设定为"接近上界";
前瞻验证通常低于 LOO 上界,若落在 0.25–0.35 之间视为**部分 GO**,进入 §3.5 的方案 B。

### 3.5 NO-GO 应对(必须事先想好,避免事后找补)

- **方案 B(部分 GO,ρ ∈ 0.25–0.35)**:把主张收缩为"收益的**方向**可预测(是否有害)",
  改做二分类:预测 `B < 0`(治疗有害)。用 AUC + precision@k 评估。
  依据 F3 的有害率 37.7% → 6.9%,这个弱化版大概率成立,且操作价值明确
  ("别修这些缺口")。
- **方案 C(NO-GO)**:回到 v13 的证据,按 §7 拆成一篇诚实的负结果短文投 HESS Technical Note,
  不再追求 WRR 正刊。

### 3.6 P0 产出

```
results/v14/p0_differential/
  differential_fitting_losses_{first,second}.csv
  unit_predictions_{first,second}.csv      # 每单元:预测收益 / 实现收益 / 各对照
  metrics_by_horizon.csv
  paired_bootstrap.csv
  budget_curve.csv
  REPORT.md                                 # 含 G1–G4 逐条判定
```

---

## 4. P1:基线套件

### 4.1 必须实现的四层基线

**Tier 0 —— 收益预测的平凡基线(必须全部战胜)**

| 基线 | 说明 | 状态 |
|---|---|---|
| 全局常数 | 全panel 收益均值 | 新写,5 行 |
| 仅缺口时长 | 按 gap_length 的收益均值 | 新写,5 行 |
| **R&H γ_m** | **Richardson & Hollinger (2007) 先验技术**:按月份分箱拟合"误差 vs 缺口长度"斜率,前瞻应用 | **新写,必做,见 §4.3** |
| 站点历史收益均值 (r6-diff) | station × horizon 收益均值 | 复用 groupby |
| 默认方法难度曲线 | 只预测 climatology MAE,不预测差 | 复用 P0 中间产物 |
| 信号幅度代理 | 局部方差 / 季节振幅 / 热变幅 | 新写,~30 行 |

**Tier 1 —— 平凡恢复方法**(确保被预测的误差不是弱模型放大的):
均值/中位数填补、LOCF、线性插值、日历日气候学、最近邻站点加偏移、气温回归。
其中气候学和线性插值在 P0 已实现。

**Tier 2 —— 水温领域 SOTA 恢复模型**:air2stream 八参数(仓库已有
`experiments/air2stream_equivalent.py`)、Mohseni logistic、气温多元回归。
用途:证明收益不是建立在弱恢复模型上的假象。

**Tier 3 —— 排序参照曲线**:随机排序(下界)+ 按真实收益的 oracle 排序(上界)。
所有排序类结果必须落在这两条之间并归一化(见 §5.2 的 E-AURC)。

### 4.2 报告规范(强制)

- **禁止跨时长池化 Spearman。** 逐时长报告,附加网络级与格内。
  依据:Forman & Scholz (2010) SIGKDD Explorations 12(1):49–57;
  Airola et al. (2011) Comput. Stat. Data Anal.(跨折叠汇集预测给 AUC 引入负偏)。
  **主动在 Methods 里引用这两篇说明为什么不池化**,把方法学弱点转成素养展示。
- 所有网络级相关系数必须附 network bootstrap CI。
- n < 15 网络的格子一律标注为 illustrative case study,不作迁移主张。
  依据:Hanczar et al. (2010) Bioinformatics 26:822;Kratzert et al. (2024) HESS 28:4187。

### 4.3 R&H γ_m 的实现细节(必做,不可省)

这是本项目最容易被拒的单点:`richardson2007longgaps` 已在 `paper/references.bib`,
v13 只把它当作"人工缺口是成熟工具"引用,**从未作为比较器实现**。其原方法:

1. 把年份分成 12 个月份箱;
2. 对每个月 m,在拟合期人工缺口上拟合 `σ(误差) vs 缺口长度` 的斜率 γ_m;
3. 前瞻应用:每个真实缺口的长度 × 其月份的 γ_m。

产出 `results/v14/p1_baselines/rh_gamma_curve.csv` 与逐单元预测,
在 Figure 2 中与 r6、时长均值并列。

---

## 5. P2:决策层

### 5.1 主呈现:Laio & Tamea 连续成本–损失曲线

**不需要把问题二值化。** Laio & Tamea (2007) HESS 11:1267 给出连续变量版本:

- 归一化损失 `ρ_ξ(x, χ) = |χ − x| + 2(ξ − 0.5)(χ − x)`,单参数 ξ = c/l;
- 最优决策 `χ* = P⁻¹(1 − ξ)`(`p_t = C/L` 的连续类比);
- 参照 = 气候学均值预测,其期望成本 = 平均绝对离差 δ;
- **画 `EC(ξ)/δ` 对 ξ 的曲线**,低于 1 即优于参照;强调 ξ < 0.5 是水文现实区间;
- 恒等式 `∫₀¹ EC(ξ)dξ = CRPS` —— 可用来论证"为什么报曲线而非单一 CRPS"
  (均匀权重过度加权 ξ > 0.5 的不现实区间)。

### 5.2 分流实验:风险–覆盖曲线 + E-AURC

弃用自创的 `CapturedLoss@B`,改用 selective prediction 的标准对象:

- 按预测收益排序,扫阈值,画 **selective risk vs coverage**;
- 汇总量必须是 **E-AURC**(= AURC − oracle 排序的 AURC),
  即在随机排序(下界)与 oracle(上界)之间归一化。原始 AURC 依赖数据集,不可比。
- 参照:Geifman & El-Yaniv (NeurIPS 2017);
  Bernhardt et al. (NeurIPS 2024, arXiv:2407.01032) 的缺陷清单当自查表
  (协议一致性 / 置信基线数量 / **置信区间与显著性检验** / 评估范围)。
- 理论最优基线:**Zaoui, Denis & Hebiri (NeurIPS 2020)** 证明最优选择性回归器
  阈值化的是**条件方差函数**。→ 把 v13 §3.7 被降级的条件协方差算子
  **重新提上来作为"理论最优基线"**,而不是当作失败的机制叙事。几乎零成本。

### 5.3 二值决策补充:Richardson REV

若同时呈现"修 / 不修"的二值动作,加画 V(α) 曲线:

```
E_A = C,  E_N = o·L,  E_C = min(C, o·L),  E_P = o·C
E_F = (a+b)·C + c·L
V(α) = (E_C − E_F) / (E_C − E_P)
```

必须遵守的三条(否则会被抓):
1. V 依赖 H 和 F 两个量,单一评分不足以刻画不同用户;
2. **V_max 出现在 α = 基率处,且 V_max = H − F = Peirce/TSS**;
3. **BSS ≈ 价值下界,ROC 面积 ≈ 价值上界 —— 不得把 AUC 当作决策价值报告。**

呈现:V(α) 对 **log(C/L)** 作图(罕见事件惯例);给出**跨决策阈值的包络**;
并像 Roulin (2007) 那样额外报告"用固定次优阈值时损失多少价值"——那才是现实数字。

### 5.4 必须主动防御的攻击:Laugesen et al. (2023) HESS 27:873

这是 REV 框架当前最强的批评,2026 年的审稿人最可能拿它打你。它指出 REV:
(a) 只适用风险中性用户;(b) 只处理二值决策;(c) 二值化**会高估价值**;
(d) 假设用户能在结果揭晓前完美自校准阈值(**包络线本身是乐观的**)。

**防御:** 主结果用 §5.1 的连续曲线(天然规避 b、c),
主动引用 Laugesen 讨论 (a)(d),明确声明报告的是**潜在价值**而非实际价值。

### 5.5 响应有效性链(最容易被拒的一条,必须补)

三项独立研究都发现:**响应有效性/依从率是决策价值的最大不确定性来源,超过预报技巧本身。**

- Verkade & Werner (2011) HESS 15:3751:`La = Lp × R × Pa × Pr × Pe`,按 DEFRA 值取 `La = 0.5 Lp`;
- Khader et al. (2013) HESS 17:1797:依从概率 A1–A4,依从率下降则 VOI 下降;
- Pappenberger et al. (2015) / JRC EUR 27533:损失削减系数(按警报操作可动防洪设施 ≈30%,搬移财物 ≈6%),
  敏感性分析结论是该系数是最大不确定源。

**映射到本项目:** 重建的收益 ≠ MAE 差值,而是
`MAE 差值 × (下游用户真的使用重建值的比例) × (该失真真的会改变结论的比例)`。
当前的 `B = D(default) − D(model) − λC` 里完全没有这一环。

**做法:** 在 B 里显式加入乘子 `η ∈ [0,1]`,给出 η 的敏感性包络(而非点估计),
并在 Discussion 里说明 η 的取值依据。哪怕只是一个带区间的显式乘子,
也足以把主张从"漂亮的数学"变成"审稿人认可的论证"。

### 5.6 模型选择实验:修或删

现状:候选族总空间只有 **0.100 °C**(oracle 1.1705 vs 永远用 donor_ridge 1.2705),
两个主力族 54:45 近乎五五开,平均损失相差 0.004 °C。这是近乎退化的任务。
且 v13 自己的固定覆盖率曲线显示,在 protocol v4 的覆盖率下限处,
三种释放判据里两种比 best_fixed 更差,唯一占优的只有 10–12%,不到自设 20% 成功线的一半。

**决策:默认删除。** 用两段写成负面发现("候选族过于同质,逐单元选择的理论上界仅 7.9% MAE"),
篇幅让给分流与下游。

若要保留,必须先重建候选集为**结构互补**的族(边界插值 / donor ridge / air2stream / climatology fallback),
并**先报告 oracle 空间**:若 oracle regret < 0.05 °C 则不值得做。

---

## 6. P3:边界与稳健性

### 6.1 非平稳性分层(最高优先级,这是模型条件性唯一可能兑现的地方)

现状:Chattahoochee 案例(预测 skill 0.414,热状态漂移后实测 −0.300)是全文最有意思的
一句话,却只是一个轶事。这里藏着**方法唯一可能真正战胜历史均值的场景**:
r6 之所以能追平,是因为一切平稳;一旦 regime shift,纯历史均值就该失效。

**做法:**
1. 用拟合期与评估期之间的热状态漂移(年均温差 / 方差比 / donor 相关性衰减)
   把第二面板 57 个网络分层为 稳定 / 中等 / 漂移 三档;
2. 在每一层里分别报告 差分曲线 vs r6-diff vs R&H γ_m;
3. 预注册方向性假设:漂移层里差分曲线的优势 > 稳定层。

**产出的两种结局都可发表:**
- 有优势 → 拿到 model conditionality 的**第一个实证证据**(v13 写了三版都只有概念论证);
- 无优势 → 诚实报告"该方法要求近似平稳",这是一条清晰的适用边界。

数据已有:`data_versions/b1_shift_sensitivity_v2/`。

### 6.2 谐调或删除(二选一,不得再拖)

| 项目 | 冲突 | 处理 |
|---|---|---|
| missingness 矩阵 | donor-sync 匹配迁移 0.979(agent_a) vs 0.490(agent_b);uniform 0.531 vs 0.944 **反向**;12 网络面板仅共享 5 个;forcing 定义不同 | 统一面板 + 统一 forcing + 统一打分约定重跑一次;**做不到就整节删除** |
| BiLSTM 行 | 0.28 vs 0.68 取决于约定;source 与 target 是不同训练实例 | source 与 target 必须同一实例;否则降为 illustrative |
| rolling-origin | 正文 0.947/0.922/0.949 (W=0.917) 与台账 canonical 0.984/0.944/0.911 (W=0.811) 互相矛盾 | 统一到一个约定,正文与台账一致 |
| 条件协方差节 | 增量 R² = 0.017,阈值 0.05 | **不删**,按 §5.2 改造成"理论最优基线" |

带着 0.979 vs 0.490 的矛盾投出去,任何认真的审稿人都会把它当成整篇稿子质量的信号。

### 6.3 保留并前置的既有强证据

这些 v13 已经做出来、但被埋在负面结论里的东西,在 v14 里应作为**地基**用半页篇幅前置:

- 局部恢复难度持续性:(network × duration) 格内跨站点 ρ = 0.724 均值 / 0.800 中位 / **95.5% 为正**(112 格,542 单元);
- 分时长:0.913 / 0.904 / 0.873 / 0.683(7/30/90/180 d);
- 分提供方稳健:捷克 0.932 / 挪威 0.818 / 美国 0.753 —— **证明网络级结果不是提供方假象,v13 未报告,必须补上**;
- 时间稳定:rolling-origin Kendall W 0.81–0.92;最短可用历史 ≈ 4 年;
- 训练长度可比性:49% vs 70% 年份,配对 MAE 差 0.013 °C,ρ = 0.989。

### 6.4 评估设计本身写成 contribution

在四篇最接近的同类工作里(Husic 2025 HESS;Pechlivanidis 2020 **WRR**;
El Ouahabi 2026 HESS;Auer 2024 HESS),**没有一篇同时具备**空间留出、时间留出、
平凡基线、排序指标、弃权/覆盖分析。本项目五条全有。

**Introduction 里明确列为一条 contribution,并在正文放对照表。**
特别注意 Pechlivanidis (2020) 发表在 WRR,其 CART 技巧预测模型
**没有训练/测试划分、没有基线、没有报告任何精度指标**,且验证针对模型自身的
pseudo-observations。这是本领域实际门槛的校准点。

---

## 7. P4:下游扩展

1. **补 180 天与 365 天缺口。** 当前下游实验只有 7/30/90 天,
   而全文反复强调长缺口携带 28.9% 的损失质量 —— 即"重建对下游有价值"的证据
   恰好不覆盖自己认定的高风险区域。这是最重要的一条。
2. **补第三个默认:线性插值。** 三个预设默认只跑了两个,而现有两个已给出**相反符号**的结论;
   第三个落在哪边目前完全未知,下游结论方向本身仍是开放的。
3. **扩大网络数。** 当前 15 个。下游指标计算便宜,瓶颈是重建,而重建已做过。
   所有网络级相关系数必须补 bootstrap CI(n=15 时 0.764 / 0.089 之类的数字区间会很宽)。
4. **引用 Johnson et al. (2021) `johnson2021datagap`。** 该文已在 `paper/references.bib`
   但 v13 全文**从未引用**。它是最直接的水温竞争者:40 站点,缺口 0–357 天按 7 天步进,
   每组合 100 个随机起始日,目标量为年均/相位/振幅(与本文下游指标高度重合),
   并已发表操作性阈值 **m_max = 49 天**。必须在 Introduction 里说明相对它的增量
   (应为"模型条件 + 收益导向",而非"更准")。

---

## 8. P5:写作、protocol v5、注册

### 8.1 必须新增引用(经核查均不在 `paper/references.bib`)

`husic` / `pechlivanidis` / `ouahabi` / `araya` 均为零命中。需补:

- **Richardson & Hollinger (2007)** —— 已在 bib(`richardson2007longgaps`),但需重新定位为**先验技术与比较器**;
- **Johnson et al. (2021)** —— 已在 bib(`johnson2021datagap`),**从未引用**,必须引;
- El Ouahabi et al. (2026) HESS 30:3549 —— 最直接的方法学竞争者;
- Husic et al. (2025) HESS 29:4457;Pechlivanidis et al. (2020) WRR 56:e2019WR026987;
- Laio & Tamea (2007) HESS 11:1267;Richardson (2000) QJRMS 126:649;
- Laugesen et al. (2023) HESS 27:873;Verkade & Werner (2011) HESS 15:3751;
  Khader et al. (2013) HESS 17:1797(注意是 HESS 不是 WRR);Roulin (2007) HESS 11:725;
- Geifman & El-Yaniv (2017);Zaoui et al. (2020);Bernhardt et al. (2024);
- Seibert et al. (2018) 上下界基准;Roberts et al. (2017) Ecography;Wenger & Olden (2012);
- Forman & Scholz (2010);Airola et al. (2011);Hanczar et al. (2010);
- Pfister & Kirchner (2017) WRR Debates(为证据角色标注辩护);Mason (2004)。

### 8.2 PUB 基准括号(Seibert et al. 2018)

用它把"r6 追平我们"从失败重述为定位问题:

- **上界基准** = 用目标站点自己未来真实缺口拟合的收益模型(不可部署的 oracle);
- **下界基准** = 汇集的全局收益曲线;
- 差分曲线、r6-diff、R&H γ_m 都落在中间,按位置报告。

### 8.3 protocol v5

**放弃 protocol v4 现有主要终点。** 依据:v13 自己的
`results/revision_v13/decision_harmonization/agent_a/coverage_regret_curve.csv` 显示,
在 ≥50% 单元 / ≥60% 网络的覆盖率下限处,三种释放判据中两种劣于 best_fixed,
唯一占优者仅 10–12%,不足自设 20% 成功线的一半。拿已知会失败的终点去申请第三面板是浪费。

**v5 主要终点:** 固定处理预算 B ∈ {10%, 20%, 30%} 下,按**预测增量收益**排序所获得的
每缺口平均实现收益,相对三个比较器的差异:
(i) 按缺口长度排序;(ii) 随机排序;(iii) **按预测模型 MAE 排序(即 v13 的旧方法)**。
配对 network bootstrap 检验。把旧方法纳入比较器是自我对抗,审稿人会欣赏。

次要终点:收益排序的分时长 Spearman(对照 r6-diff 与 R&H γ_m,零 margin,方向复制)。

**注册:** AGU/WRR **没有 Registered Report 通道**;WRR 属 TOP 框架签署方,
可强制执行的是数据/代码可得性与分析透明度。因此:
- OSF/Zenodo 外部注册在本领域属**超出常规的加分项**,继续做;
- 但不得把内部 hash-bound 冻结描述为 "preregistered confirmation"
  —— v13 现有措辞("frozen … not externally verifiable preregistration")正确,保持;
- 事后分析继续按 Pfister & Kirchner (2017) 的要求明确标注为探索性,并**主动引用该文为自己辩护**。

### 8.4 图集(全部需新绘;v13 五张图一张未画)

| 图 | 内容 |
|---|---|
| **Fig 1** | **thesis statement**:左 = 横轴预测模型 MAE、纵轴实现收益(向下的散点,ρ=−0.230);右 = 横轴换成预测增量收益(向上)。同批点,按时长着色。 |
| Fig 2 | 强基线对照:差分曲线 vs r6-diff vs **R&H γ_m** vs 仅时长 vs 默认难度曲线,分时长面板 + 配对 bootstrap 分布 |
| Fig 3 | 支持层级与时长:精确格 / 回退格,插值区与外推区,弃权权衡 |
| Fig 4 | 决策:`EC(ξ)/δ` 曲线(ξ<0.5 高亮)+ 风险–覆盖曲线与 E-AURC,含随机与 oracle 参照带 |
| Fig 5 | 下游增量收益:三个默认 × 三种排序策略 × 各指标,含 η 敏感性包络 |
| Fig 6 | 非平稳分层:稳定/中等/漂移三档下 差分曲线 vs r6-diff |

### 8.5 投稿

- 首选 **WRR**(决策导向 + cost-loss + 跨大陆面板,符合口味);
- 备选 **HESS**(对"方法学 + 诚实边界刻画"更友好;公开讨论制度对本项目的透明度有利);
- **并行动作:把现有 v13 单独发成负结果短文**(HESS Technical Note 或
  *Environmental Modelling & Software*),题目大意
  "预测重建误差:局部难度持续性是真实的,但站点历史已经捕捉了它"。
  所需材料已全部具备,且可成为 v14 里"我们此前证明了 X 不奏效"的自引。

### 8.6 投稿硬门(v13 遗留 TODO)

1. 归档 DOI 未铸造 —— WRR Open Research 政策的硬性门槛;
2. 全部图未绘;
3. t10 RMSE 转录冲突(0.631 CSV vs 0.694 注记);
4. rolling-origin 约定分歧(见 §6.2);
5. 参考文献重新生成。

---

## 9. 立即可执行的第一步

```
1. 新建 src/stream_recoverability/experiments/differential_stress.py
2. 实现 default_handling_losses(handler="climatology"),
   内部复用 development_recovery._climatology_prediction,传内层拟合掩码
3. 实现 differential_fitting_losses(),输出 schema 与
   fitting_period_empirical_losses 一致,mae_deg_c := default − model
4. 把结果喂进现有的 empirical_transfer_predictions()(不改一行)
5. 在第一面板 42 网络上跑通,产出 results/v14/p0_differential/
6. 对照 §3.4 的 G1–G4 判定
```

预计一周内可出数。**这一个实验决定这篇论文是零结果还是正结果。**

---

## 附录 A:已验证数字速查(可直接引用,均已对齐 artifact)

| 量 | 值 | 备注 |
|---|---|---|
| 第二面板 | 57 网络(32 US / 15 CZ / 10 NO),1,446 单元,874 直接支持 | |
| 旧法 pooled ρ(874) | 0.945 | 跨时长池化,**不应作 headline** |
| r6 pooled ρ(874) | 0.942 | 配对 Δρ +0.042,CI [−0.0006, +0.1154] 跨零 |
| 仅时长基线 pooled ρ | **0.833** | v13 从未报告 |
| 分时长 pooled ρ(旧法) | 0.913 / 0.904 / 0.873 / 0.683 | 7/30/90/180 d |
| 分时长 pooled ρ(r6) | 0.912 / 0.904 / 0.851 / 0.648 | 逐格重合 |
| 格内跨站点 ρ(旧法/r6) | 0.724 / 0.719(中位 0.800 / 0.800) | 112 格,542 单元,95.5% 为正 |
| 分提供方网络级 ρ | CZ 0.932 / NO 0.818 / US 0.753 | **不是提供方假象** |
| 预测器相关 | Pearson 0.9917 / Spearman 0.9959 | 旧法 vs r6 |
| 模型选择空间 | oracle 1.1705 vs best fixed 1.2705,regret 0.100(7.9%) | 近乎退化 |
| 覆盖率下限处 regret | 判据 a: 0.1147 vs 0.1300(−11.8%);判据 b: 0.0719 vs 0.0462(**更差**);判据 c: 0.0977 vs 0.0813(**更差**) | protocol v4 主要终点已先行失败 |
| 风险分数排 MAE / 排收益 | +0.726 / **−0.230** | 病根 |
| climatology_MAE 排收益 | **+0.659** | 信号所在 |
| LOO 收益曲线排收益 | **+0.363** | 可行性上界 |
| top-20% 每缺口收益 | 旧法 +0.147 / 时长 +0.283 / **收益曲线 +0.992** / 全panel +0.615 | |
| top-20% 有害率 | 旧法 37.7% / **收益曲线 6.9%** / 全panel 15.2% | |
