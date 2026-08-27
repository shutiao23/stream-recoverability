# Protocol change v9 to v9.1

Date: 2026-08-26  
Status: next-paper freeze **amendment**；不是结果，不是标题许可，不是对 T2 的放宽。  
Amends: `docs/protocol_change_v8_to_v9.md` + `configs/design_freeze_v9.yaml`  
Supersedes: 无。v9 的 T2 数字地板、密封规则、never_sealed 清单全部继承。  
Does not touch: `configs/design_freeze_v4.yaml`、`DEFAULT_DESIGN_PATH`、`EXECUTABLE_DESIGN_VERSION`、金沙江 / Chattahoochee 历史稿、134k-run 历史流水线、全国面板冻结哈希、`recoverability_study_freeze_v1.yaml`、BL-001–BL-015 已冻结表述、`configs/network_catalog_v1.yaml` 作为历史对照目录

这是**下一篇研究冻结的修正案**，不是对 `design_freeze_v4` 的静默改写，也不是把 `design_freeze_v9` 换成一份新的可执行设定。  
`design_id` 仍是 `design_freeze_v9`。v9.1 只追加 `protocol_amendment: v9.1`。  
`DEFAULT_DESIGN_PATH` / `EXECUTABLE_DESIGN_VERSION` 必须保持 `design_freeze_v4`。任何人不得把 v9.1 门槛回写进 v4，也不得把金沙江 / Chattahoochee 的已看结果重新标成 confirmatory。

v9.1 修正三处**规范错误 / 分组缺陷 / 计算预算未锁**，全部在打开任何新水温、下载任何新日值之前写入。  
它不是因为 6 河试点没过关而改规则。6 河 Spearman ≈ 0.77、区间下沿约 −0.01 仍是**没过关的试点**，不是把 0.60 / 0.40 改松的许可证。`public_river_check.json` 的 0.821 / 0.094 含 Clearwater，不得引用。

---

## Strictness proof（E5；一段，不得删）

旧 E5 门槛是坝标签上的分类合取：算子 AUC≥0.85，且每个单变量 AUC≤0.65。新门槛换成已知 \(\Sigma\) 上的真实条件风险（或真实最优 MAE），逐节点 × 逐缺口，三个数字合取，外加一格旧 2×2 从未实例化的硬负例：算子 Spearman\((\hat{\mathcal R},\text{true recoverability})\ge 0.90\)，四个预先登记单变量里最好的 Spearman \(\le 0.70\)，算子校准斜率 \(\in[0.9,1.1]\)（单变量无校准要求），并且 **Twin E 必须作为独立格子过关**，不得并进 A–D 的混合表冒充过关。这不是把 0.65 抬到 0.70。0.65 是 `is_dam_like` 上的分类 AUC；0.70 是把边际 ACF 与 donor \(R^2\) 配平之后、连续真可恢复性上的 Spearman。二者量纲不同、总体不同、可被边际签名打满的程度不同，禁止做减法。旧门槛可以（且已经）被「高 AR + 隔离」同时打满算子和单变量（AUC 皆 1.0），所以 `gate_pass: false` 是无信息，不是负结果。新门槛在 Twin E 上把那条边际签名关掉：单变量被设计成接近机会水平，算子却仍须在连续真风险上排到 0.90 并落进校准带。多出来的约束是更高的排序地板（0.90>0.85，且作用在连续、跨缺口的真值上，而不是 7 正 / 73 负的坝标签）、一条旧门槛没有的校准带、以及一格条件结构硬负例。任何「单变量天花板从 0.65 放到 0.70」「Spearman 0.90 ≈ AUC 0.85」「因为六河没过所以改 E5」的读法，本修正一律拒绝。

---

## Why

v9 把下一篇的标题论题、Schur 主算子、T2/T3 数字地板和 never_sealed 锁对了。它没有锁三件会在扩量之前把 confirmatory 写坏的事：

1. **E5 测的是坝检测，不是可恢复性。**  
   `results/framework/synthetic_v2/twin_design_manifest.json`：`operator_auc: 1.0`，`univariate_max_auc: 1.0`，`gate_pass: false`，`identifiability_status: operator_separable_univariates_also_separable`。因变量是 `is_dam_like`。这正好是 v9 已经禁止写进标题的那件事（`reservoir_mechanism_in_headline: false`，`national_dam_auc_is_recoverability_evidence: false`）。生成器给坝节点的是边际签名（高 AR + 隔离），与拓扑正交，所以任何看得见 ACF 或 donor \(R^2\) 的单变量都能完美分开。想测的混叠从未被实例化。这是**规范错误**（BL-016），不是 T5 完成，也不是「算子在可恢复性上失败」。禁止为了把单变量 AUC 压到 0.65 去改 \(\varphi\) 或噪声。Twin E 是设计修正（把混叠实例化），不是 \(\varphi\)-hacking。

2. **name×HUC2 字符串分组是假天花板，不是数据上限。**  
   审稿复算：同一份 USGS 日值目录，HUC8、≥3 站、≥8 年目录共同窗口得到约 161 组。name×HUC2 的 98 / 四站 31 漏掉异名同网、又把 `missouri_river_huc10` 那种跨整个 HUC2 的 18 站伪网络算成一条。换成 HUC8 **不是**把四站/HUC2 放宽到三站/HUC8 来凑 150。v9 已经把科学目标锁在每网 ≥3 站；三站地板不是本修正发明的。HUC8 是更紧的空间单元（子流域，约 1,000–5,000 km²），不是更松的收录规则。若有人把 161 写成「放宽之后多找到 63 条河」，那是索赔违规，本文件预先禁止。161 是目录起止日交集，**不是**每年 300 个 approved 日值 × 8 年，**不是** T2。下载后衰减按 25–40% 预登；161×0.65≈105 只说明有机会碰到 CI 地板 100，不授权把 161 当库存、当合格河网、当「T2 已达」。

3. **九模型全网格在 161 候选上的预算没有预注册。**  
   试点只用了 `donor_regression`。若不在下载前锁两层预算，事后砍模型就是 unequal_tuning_budgets / 事后缩水，与 v9 `primary_evidence_forbids` 同类。两层必须现在锁：全量廉价层产生 T2 的 \(y\)；约 30 网分层子样本加空气—水体和深度模型，缺口只跑已经写死的 30/90/180 三档，禁止看完 envelope 再挑 90 或 180（BL-006 类）。

另补第四件，必须写进同一份修正，否则扩量会把 Clearwater 类污染做成静默偏倚：

4. **摄入 QC。**  
   `13343000` 在 1848 个非空值里只有 2 个 NWIS sentinel（−999999；约 0.11%）。「NA 化比例 > 1% → `rejected_sentinel`」会放行该站。协议锁死：值域里出现任意 NWIS sentinel ⇒ `rejected_sentinel`。1% 只是对超范围值 NA 化之后的附加站级拒绝，不是 sentinel 规则本身。

这四件事全部是看新水温之前的规范锁。不是结果驱动改口。

---

## What changed

1. **v9.1 是修正案，不是新的历史 executable。**  
   `configs/design_freeze_v9.yaml` 原地追加 `protocol_amendment: v9.1` 和 `protocol_change_v9_1: docs/protocol_change_v9_to_v9.1.md`（生产合并后的路径；本对抗包写在 `scratch/adversarial/w1c/`）。  
   `protocol_change:` 仍指向 `docs/protocol_change_v8_to_v9.md`。v8→v9 那份文件不删、不改写。  
   `design_id` / `design_version` 仍是 `design_freeze_v9`。  
   `not_an_executable_design: true`，`executable: false`。  
   `formal_evidence: false`，`headline_claim_licensed: false`，`reservoir_mechanism_in_headline: false`，`sealed_outcomes_opened: false`。  
   禁止新建一份 `design_freeze_v9.1.yaml` 去抢 `DEFAULT_STUDY_FREEZE`。禁止改 `DEFAULT_DESIGN_PATH`。

2. **E5 因变量从 `is_dam_like` 换成真实可恢复性（BL-016）。**  
   主问题：在拓扑与「坝样」混叠的条件下，拟合期 Schur 算子对**已知真值**可恢复性的排序和校准，是否优于四个预先登记单变量？  
   不是：算子能不能把坝标签分出来。  
   真值：从已知 \(\Sigma\) 直接算 \(\Sigma_{G\mid O}\) 得到的真实条件风险（或真实最优 MAE），格子是节点 × 缺口长度。缺口至少锁 30/90/180，与两层恢复预算的深度层一致；禁止事后只留最好看的一档。  
   指标：Spearman 与校准斜率。**禁止再用分类 AUC 作为 E5 过关数字。** 旧 AUC 表可以留作「规范错误的审计」，标签必须写 `superseded_dam_detection_gate`。  
   现有 `gate_pass: false` 的法律地位：无信息。错误估计量 + 单变量同样 AUC 1.0。不得写入 T5 完成，不得当作负向可恢复性结果，不得引用顶层 `identifiability_status: operator_separable_univariates_also_separable` 当作过关或「算子可分」。联合门才是唯一可引用的状态，而旧联合门在错误 \(y\) 上。

3. **新 E5 数字门槛（必须同时满足；只许加严，不许放宽）。**  
   - 算子对真实可恢复性的 Spearman \(\ge 0.90\)。  
   - 四个单变量（gap-length only 不适用合成节点风险时：donor \(R^2\) only、acf only、additive \(d/4\)、nearest-donor hops/distance）里**最好的** Spearman \(\le 0.70\)。  
   - 算子校准斜率 \(\in[0.9,1.1]\)。单变量不做校准要求。  
   - Twin E 作为独立格子：上述三条在 Twin E 上单独成立。禁止把 A–D 的好数字平均掉 Twin E 的失败。  
   - 设计图集不得等于评分图集（承接已接受的孪生红队 leftover）：过关声明需要在锁门之后、评分之前登记的 hold-out 族。本修正先锁门；hold-out 族在第一次重跑 E5 之前写入 freeze，不得看完 AUC 再挑图。  
   旧门槛 `OPERATOR_AUC_MIN = 0.85` / `UNIVARIATE_AUC_MAX = 0.65` **作废，保留为被取代审计**。不得把旧 `gate_pass: false` 改写成新门槛下的通过。

4. **Twin E 是设计修正，不是救门。**  
   新增一格：坝样节点与端点节点具有**相同边际 ACF**和**相同 donor \(R^2\)**，只在条件结构 \(\Sigma_{G\mid O}\) 上不同。  
   做法锁死为：调 donor 数量和方向使 \(R^2_{\mathrm{donor}}\) 相等；用传播时滞让一侧边界信息与 donor 高度冗余、另一侧互补。  
   禁止：改 \(\varphi\)、改隔离、改噪声、改 AR 对角线，把单变量坝标签 AUC 压到 0.65 以下。那是 \(\varphi\)-hacking。  
   Twin A–D 可以保留为几何对照。Twin D 若仍是 Twin B 的克隆，不得再称为独立格子（已有 leftover；修克隆不是本修正的放宽）。  
   若算子在 Twin E 上仍赢不过单变量：这是可发表的负结果（「二阶条件结构在这类网上不携带超出边际统计量的信息」）。写入 ledger，不重调。不得为了保住 T1 新颖性去改生成器。

5. **分组单元换成 HUC8 + 精确最大重叠子集 + NLDI 协变量（BL-017）。**  
   下一篇候选集的科学分组是 USGS HUC8 子流域，不是 `river_name × huc.str[:2]`，也不是 HUC8-only 混名探索表（v2 的 166 不得混进诚实库存）。  
   对照分组（name×HUC2）必须继续落盘，用来证明差异来自单元定义，不是来自「放宽四站」。  
   共同窗口：精确最大重叠子集（区间扫描）。审稿 161 对 >12 站组做过截断组合，可能偏低；正式数以精确搜索为准。精确搜索多出来的组**仍然是目录重叠，不是 T2**。  
   NLDI UM+DM：不连通的组**不删**，标记 `spatially_proximate_not_flow_connected`，当协变量。删除不连通组会把对照样本藏起来，属于藏数据，不是加严。  
   两两距离：大地测量千米。缺 lat/lon 的站必须有显式政策，不得把 `max_pair_km` 写成 0 或 inf。  
   `missouri_river_huc10` 式伪网络不得作为一条独立河网存活。  
   **禁止下载 name×HUC2 的 98 名单。** 那是错误候选集。

6. **161 的唯一合法句子。**  
   允许：约 161 是公开 USGS 目录上、HUC8、≥3 站、目录起止日交集 ≥8 年的**候选组数**（精确重算后改数字，不改法律地位）。  
   禁止：161 条河已在手；161≥150 所以 T2 过关；合格八年；比 98 多 63 条是放宽标准找来的；HUC8-only 166 是诚实库存；把 6 年重叠写进诚实 T2 计数。  
   合格年：下载后、摄入 QC 后，该站该年 approved 日值 ≥300，且这样的年 ≥8。目录 `daily_begin`/`daily_end` 不是这个。  
   预登衰减：25–40%。衰减后若合格河网 <100，走 v9 已写的失败分支（放宽到 3 站 / 6 年并**报告这次放宽**）；不得把 HUC8 分组本身说成那次放宽。6 年放宽是失败分支，不是现在的诚实计数。  
   T2 数字地板不改：库存目标仍 ≥150；独立河网 \(n\ge 100\) 才允许报告网络级 CI；Spearman ≥0.60；同一条 95% CI 下界 >0.40 **并且**高于四个单变量点估计；校准 |bias| 中位 <0.10、斜率 ∈[0.8,1.2]。定方法阶段的把握分析只许加严这些数，不许放宽。

7. **区间规则把 BL-012 内化到下一篇的网络单元（不改历史稿）。**  
   网络级 CI 仍需要 ≥100 个独立河网。  
   **12 河试点和 6 河（或 5 河）止损 / pipeline 核查一律不得报告网络级 CI，不得把 cluster-bootstrap 区间写进表或正文当推断。**  
   网内描述性规则仍是 ≥5 个 site-year / overlap component（历史稿 BL-012）；那是另一套冻结、另一套单元。  
   W2 重做 6 河 pipeline：manifest 必须写 `n_networks: 6`，`passed: false`，`purpose: pipeline_verification_not_evidence`。判定标准是 gap_length 的 \(\Delta R^2\) 非零、不同缺口的前几行不再相同，不是「算子赢没赢」。

8. **never_sealed 一字不改。Loire / Swiss 仍不能计入 T8。**  
   下列 14 个 ID 必须原样出现在 `split_rule.never_sealed_networks`，可追加新 ID，**禁止删除、禁止改 token、禁止用补零 HUC2 重命名来「修好」`*_huc20` / `*_huc31` / `*_huc50`：**  
   `jinsha_upper`，`chattahoochee_upper_middle`，`delaware_river_huc20`，`willamette_river_huc17`，`suwannee_river_huc31`，`yellowstone_river_huc10`，`rio_grande_huc13`，`madison_river_huc10`，`cahaba_river_huc31`，`mckenzie_river_huc17`，`mahoning_river_huc50`，`roanoke_river_huc30`，`santa_fe_river_huc31`，`clearwater_river_huc17`。  
   `loire_mainstem` 与 `swiss_aar_rhine` 仍在 `not_countable_as_public_daily_or_non_na_sealed_until_daily_history_is_public`。没有公开、带日期的日值之前，不得计入 T8，不得计入 ≥10 条北美以外密封。不得用 `river_catalog_summary.csv` 里那行伪造的 14 站八年日值把 Loire 救进密封。  
   划分：剩余候选按 气候带 × 调控状态 × 网络规模 分层，目标 50/20/30，密封绝对下限 40。种子、分层表、SHA-256 在**第一次新下载之前**落盘（`configs/network_catalog_v3_split.yaml` 或同等文件）。本协议只锁规则与指针；不在 Phase 0 重切 `network_catalog_v1.yaml`。

9. **两层恢复模型预算，下载前锁死（P5）。**  
   **第一层（全语料，产生 T2 主 \(y\)）：** climatology，PCHIP/线性，Kalman，donor_regression，XGBoost。全缺口 × 全 placement（每格 ≥20）× 全信息条件。  
   **第二层（约 30 条河，敏感性，不是主 \(y\)）：** 在第一层之上加 air2stream、SAITS、CSDI、GRIN。  
   第二层抽样规则现在锁死，不得下载后再「看哪些河算得动」：  
   - 目标 \(n \approx 30\)（允许 28–32，越界必须写 ledger，禁止静默变成 12 或 6）。  
   - 分层：气候带（v9 的 ≥3 类）× 调控状态（regulated / not）× 网络规模（站数或流域面积三分位）。每层至少抽到，缺层则缩小该层而不是改层定义。  
   - 缺口：**30 与 90 与 180 全部跑**。禁止「30、90 或 180」。禁止看完 envelope 只报 90 或只报 180（BL-006 类；`forbidden_after_seal` 已有 `selecting_the_better_of_90_and_180_days`，本条把同一禁令下放到密封打开之前的第二层）。  
   - 目的：强模型会不会改变 recoverability 标定。答「会」或「不会」都不是把第二层模型提成 T2 主 \(y\) 的许可证。  
   仍禁止：`best_epoch<50` 整类踢出、不等调参预算、event-wise best envelope 当主证据。SAITS 与 CSDI 与 GRIN 都在第二层名单里；禁止写成 `csdi_or_grin` 一槽或。  
   这是预注册计算预算。下载之后发现算不动，只许走失败闭合（降标题、写 ledger），不许把九模型名单缩成「试点那个 donor_regression」。

10. **摄入 QC 预注册（P4）。**  
    站级门，在任何新日值进入协方差或 skill 之前：  
    - 值域出现任意 NWIS sentinel（至少 −999999、−99999、−9999、99999、9999；0 °C **不是** sentinel）⇒ 整站 `rejected_sentinel`。Clearwater `13343000`（2 / 1848）是回归锚点：1% 规则必须抓不住，本规则必须抓住。  
    - 值 < −5 °C 或 > 45 °C → 该值置 NA 并计数；随后 NA 化比例 > 1% → `rejected_range`（这是附加规则，**不能代替** sentinel 规则）。  
    - approval 非 approved → 置 NA，不入主分析；Estimated-approved 可标旗，不得当 provisional 直接丢，也不得把旧 `quality_approved` 别名当成 USGS approval。  
    - 连续常数 >14 天 → `suspect_constant_run`（旗，不单凭此拒绝）。  
    - 日间跳变 >10 °C → `suspect_jump`（旗，不是 \(|x-\mathrm{median}|>10\)）。  
    - 该年 approved 日数 <300 → 该年不计入 `evaluable_site_years`。  
    输出逐站 `ingest_qc_report.csv`：`n_raw, n_sentinel, n_out_of_range, n_provisional_dropped, n_constant_run_days, n_jump, qualified_years, verdict`。  
    `verdict` ∈ {`accepted`, `accepted_with_flags`, `rejected_<reason>`}。拒绝原因必须逐站落盘。论文 attrition 表的合法分子是「候选组 → 下载 → QC → 合格年」，不是 161。  
    只做站级判决。禁止把整条河因一个污染站默删而不留站级行（Clearwater 整河剔除曾掩盖根因）。

11. **BL-016、BL-017 写入 ledger。**  
    五问结构与 BL-015 相同。BL-016 是 E5 规范错误。BL-017 是分组缺陷。两者都不重开历史 confirmatory 结局，都不改写 BL-006 的类型预测，都不把 540-unit 一次打开说成可以重跑。

---

## What did not change

1. 历史 once-lock。`design_freeze_v4`、540-unit 一次打开、train-only 启发式、2018--2020 development-test 可见性标签，全部不动。`DEFAULT_DESIGN_PATH` 仍是 v4。
2. T2 数字地板。Spearman 0.60、CI 下界 0.40、四基线点估计规则、校准 0.10 / [0.8,1.2]、库存目标 150、网络级 CI 的 100 网地板。6 河没过关不是改这些数的理由。
3. T3(a)/(b) 决策门槛、T4 自然缺测、T6 SEPlains×BFI、T7 密封一次打开、T8 公开数据优先。
4. 全国面板冻结哈希。BL-011 的 pooled LOEO AUC 0.407 仍是历史稿的冻结主数字。
5. 金沙江源质量边界 BL-014。
6. 密封结果仍然未打开。目录阶段只许查站在不在、目录年份够不够，不许用水温给方法打分。
7. `formal_evidence: false`。没有标题许可。12 河 / 6 河 / 5 河试点数字不是 confirmatory。
8. 硬类型标签不是主结果（BL-015 不改写）。event-wise best envelope 不是主结果。全国「有没有坝」AUC 不是可恢复性证据。
9. 没有水库运行记录，就不写水库因果。E10 仍是 companion only。
10. `never_sealed_networks` 的 14 个 token。Loire / Swiss 的 T8 阻断。
11. 不删除 `recoverability_study_freeze_v1.yaml`。不把 `network_catalog_v1.yaml` 重映射成可执行目录。
12. `tests/test_reference_runner.py` 和 `tests/test_formal_registry_builder.py` 里把字符串 `design_freeze_v9` 当作 dummy mismatch 的用法不改。
13. `forbidden_after_seal` 已有的 `selecting_the_better_of_90_and_180_days` 继续有效，并下放到密封前的第二层预算。

---

## Falsifiers and failure closure

在 v9 已登记证伪之外，v9.1 追加：

1. E5 仍用 `is_dam_like` AUC 过关，或把旧 `gate_pass: false` 写成 T5 / 负向可恢复性（`e5_wrong_estimand_cited_as_result`）。
2. 为过旧门或新门而改 \(\varphi\) / 隔离 / 噪声（`generator_retuned_to_save_gate`）。
3. Twin E 未实例化边际配平，或未作为独立格子报告（`aliasing_not_instantiated`）。
4. 把 161（或精确重算）写成 T2 库存，或写成「放宽后多 63 条」（`catalog_count_sold_as_t2`）。
5. 12 河或 6 河报告网络级 CI（`network_ci_below_100`）。
6. 第二层看完 envelope 只留 90 或 180（`horizon_selected_after_envelope`）。
7. 下载后才改两层名单或把 \(n\approx 30\) 缩到试点河（`posthoc_model_budget_shrink`）。
8. 1% NA 化规则放行 sentinel 站（`sentinel_missed_by_percent_rule`）。
9. 重写 never_sealed 或把 Loire/Swiss 计入 T8（`never_sealed_or_t8_breach`）。

失败闭合，禁止用重调去救：

- **Twin E 上算子赢不过单变量：** 可发表负结果；**不许改 \(\varphi\)。** T5 合成格失败时，真河匹配仍按 v9 `t5_confound_control.matching_factors` 做；不得把无信息的旧门失败写进摘要。
- **合格河网 <100：** 走 v9 已写的 3 站 / 6 年放宽并报告；不降低 Spearman / 0.40；不把 HUC8 说成这次放宽。
- **目录 161 下载后不够 150：** 150 仍是目标，不是把 161 改口成已达。欧洲补充是 T8 路径，不是把 Loire/Swiss 无日值算进去。
- **第二层算不动：** 写预算失败，不事后踢深度模型；T2 主 \(y\) 仍是第一层。
- **密封未过关：** 写入 ledger，不解冻，不换更好看的 90/180 天。历史两河稿仍是描述性病例。

---

## Relation to phases

| 已锁 | v9.1 追加 |
| --- | --- |
| Phase 0 的 v9 文件、BL-015、T2/T3 地板 | 本文件、BL-016、BL-017、freeze 补丁；不打开密封 |
| Phase 2 旧 E5 坝检测门 | 门作废；Twin E + 真风险 Spearman 门；不重跑冒充确认 |
| Phase 3 语料扩容 | 候选集 = HUC8 目录组，不是 98；先 QC 门；先锁划分与两层预算 |
| Phase 4 主实验 | 主 \(y\) = 第一层全网格 skill；6 河重做只验 pipeline |
| Phase 7 一次打开 | 门槛不因本修正降低 |

Phase 0/v9.1 禁止：打开密封水温；改历史 `design_freeze_v4` 执行路径；删除 v8 冻结文件；声称 formal evidence、标题许可或水库因果；把 12/6/5 河当确认；编造新的八站数字；下载 98 名单；把 161 当 T2；为旧 E5 门调生成器。

---

## Pass gate（对抗包不改生产校验器；合并后必须）

```text
python scripts/45_validate_research_charter.py
```

合并后必须额外断言：本协议存在；BL-016 / BL-017 存在；E5 新键与 Spearman 地板存在；`never_sealed` 14 个 ID 仍在；T2 Spearman ≥0.60 且 CI 地板 ≥0.40；`design_freeze_v4` 仍是 executable；`formal_evidence` 仍 false。  
钉住 `design_freeze_v4` 的历史 formal-roster 测试必须继续通过。
