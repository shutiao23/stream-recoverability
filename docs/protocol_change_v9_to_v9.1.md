# Protocol change v9 to v9.1

Date: 2026-08-26  
Status: specification-error correction；不是结果，也不是标题许可。  
Amends in place: `configs/design_freeze_v9.yaml`（`design_id` 仍是 `design_freeze_v9`）  
Does not replace: `docs/protocol_change_v8_to_v9.md`  
Does not touch: `configs/design_freeze_v4.yaml`、`DEFAULT_DESIGN_PATH` / `EXECUTABLE_DESIGN_VERSION`、`configs/recoverability_study_freeze_v1.yaml`、`network_catalog_v1` 作为 executable catalog 的地位

这是 **v9 冻结上的协议修订**，不是新冻结文件，也不是对 `design_freeze_v4` 的改写。  
`design_id` 仍是 `design_freeze_v9`。v9.1 只追加 `protocol_amendment: v9.1`。  
`DEFAULT_DESIGN_PATH` / `EXECUTABLE_DESIGN_VERSION` 必须保持 `design_freeze_v4`。禁止新建 `design_freeze_v9.1.yaml`，禁止把 v9.1 门槛回写进 v4。  
修订在打开任何**新的**密封或扩容水温之前写入。不下载新水温。不重调孪生生成器。不声称 formal evidence、标题许可或 T2/T5 已过关。

v9 把 T2/T3 数字门槛锁死了，但把三条规格写错了：河网分组用了 name×HUC2 假天花板；E5 门槛用了 v9 标题禁止的坝样分类 AUC；全模型全格子被写成好像算力无限。v9.1 只改这三类规格错误。T2 的 Spearman 0.60 / CI 下沿 0.40 **不得降低**。  
它不是因为 6 河试点没过关而改规则。6 河 Spearman ≈ 0.77、区间下沿约 −0.01 仍是**没过关的试点**，不是把 0.60 / 0.40 改松的许可证。

---

## Strictness proof（E5；一段，不得删）

旧 E5 门槛是坝标签上的分类合取：算子 AUC≥0.85，且每个单变量 AUC≤0.65。新门槛换成已知 \(\Sigma\) 上的真实条件风险（或真实最优 MAE），逐节点 × 逐缺口，三个数字合取，外加一格旧 2×2 从未实例化的硬负例：算子 Spearman\((\hat{\mathcal R},\text{true recoverability})\ge 0.90\)，四个预先登记单变量里最好的 Spearman \(\le 0.70\)，算子校准斜率 \(\in[0.9,1.1]\)（单变量无校准要求），并且 **Twin E 必须作为独立格子过关**，不得并进 A–D 的混合表冒充过关。这不是把 0.65 抬到 0.70。0.65 是 `is_dam_like` 上的分类 AUC；0.70 是把边际 ACF 与 donor \(R^2\) 配平之后、连续真可恢复性上的 Spearman。二者量纲不同、总体不同、可被边际签名打满的程度不同，禁止做减法。旧门槛可以（且已经）被「高 AR + 隔离」同时打满算子和单变量（AUC 皆 1.0），所以 `gate_pass: false` 是无信息，不是负结果。新门槛在 Twin E 上把那条边际签名关掉：单变量被设计成接近机会水平，算子却仍须在连续真风险上排到 0.90 并落进校准带。多出来的约束是更高的排序地板（0.90>0.85，且作用在连续、跨缺口的真值上，而不是 7 正 / 73 负的坝标签）、一条旧门槛没有的校准带、以及一格条件结构硬负例。任何「单变量天花板从 0.65 放到 0.70」「把 Spearman 0.90 等同于旧分类 AUC 0.85」「因为六河试点未过关而改写 E5」的读法，本修正一律拒绝。

---

## Why

这不是看了新数以后降低 T2 地板，也不是结果驱动改口。四处错误在扩容下载之前就已经写在协议里：

1. **分组（P1）。** name×HUC2 字符串分组给出 98（v2 name+HUC2、3 站、8 年子集）和 31（v1 整组重叠、4 站、8 年）。那是分组规则的假天花板，不是公开 USGS 目录的数据上限。`missouri_river_huc10` 这类伪河网把一条名字相同、HUC2 相同、地理上不相干的站点捆成一个推断单元。换成 HUC8 **不是**把四站/HUC2 放到三站/HUC8 来凑 150。v9 已经把科学目标锁在每网 ≥3 站；三站地板不是本修正发明的。HUC8 是更紧的空间单元，不是更松的收录规则。若有人把目录计数写成「放宽之后多出六十三条河」，那是索赔违规，本文件预先禁止。审稿约 161 在本目录上可被 naive `str(huc).zfill(8)[:8]` 精确复现；>12 站截断组合在本目录上仍是 166，解释不了 161。W1-A 用 `official_huc_prefix` 的精确最大重叠子集得到 **166**。166 是目录单元，**不是**每年 300 个 approved 日值 × 8 年，**不是** T2。预登下载后衰减 25–40%。
2. **E5 估计量（P2）。** 旧门槛用 `is_dam_like` 分类 AUC。这是在做坝检测。v9 已经把 `reservoir_mechanism_in_headline: false` 和 `national_dam_auc_is_recoverability_evidence: false` 锁死。当前孪生记录 `operator_auc=1`、`univariate_max_auc=1`、`identifiability_status: operator_separable_univariates_also_separable`、`gate_pass: false`。这是**无信息结果**，不是负结果，也不是 T5 过关。禁止引用顶层 `identifiability_status` 当作过关或「算子可分」。禁止为了救 0.65 去重调 φ / 噪声。Twin E 是设计修正（把混叠实例化），不是 \(\varphi\)-hacking。
3. **恢复模型预算（P5）。** v9 把 cheap 和 deep 模型写在同一条全语料 roster 上。那不是可执行预算。下载前必须把两档算力锁死，否则事后会按「谁跑得完」收缩格子。第二档 \(n\) 锁在 28–32，缺口 30 **与** 90 **与** 180 全部跑；禁止看完 envelope 再挑 90 或 180。
4. **入库 QC（P4）。** 扩容前必须有站级门，不能等下载后再发明剔除规则。已经看过的 Clearwater 序列里，1848 个值中有 2 个 NWIS sentinel（约 0.11%）。只设 1% 比例阈值会放行。任何值里出现 NWIS sentinel ⇒ `rejected_sentinel`。1% 只用于超范围值 NA 化之后的 `rejected_range`，不能代替 sentinel 规则。0 °C 不是 sentinel。

BL-016、BL-017 与本文件同时打开。不重写 BL-015。

---

## What changed

1. **仍是 `design_freeze_v9`，加 `protocol_amendment: v9.1`。**  
   不新建替代冻结、不改 `DEFAULT_STUDY_FREEZE`、不改 `DEFAULT_DESIGN_PATH`。  
   `protocol_change` 仍指向 `docs/protocol_change_v8_to_v9.md`。  
   `protocol_change_path` 指向本文件。  
   `formal_evidence`、`sealed_outcomes_opened`、`headline_claim_licensed`、`reservoir_mechanism_in_headline`、`not_an_executable_design`、`executable` 全部保持原值。

2. **分组规则换成 HUC8 + 最大重叠子集 + NLDI 协变量（BL-017）。**  
   作废作为推断单元的 name×HUC2 字符串分组。  
   锁死规则：
   - 空间单元：HUC8（HUC 先补零到 8 或 12 位再取前缀）。
   - 同期：组内 **exact max-overlap subset**（最大子集的目录区间交集），不是「组内每一个站都必须共享同一个窗口」。
   - 可选：站对公里距离，作诊断，不单独当河网定义。
   - NLDI UM+DM 连通性是 **协变量**，不断开就不丢站；不断开的站留在 HUC8 单元里并记下 `nldi_connected: false`。
   - 这比 name×HUC2 **更严**：`missouri_river_huc10` 这类伪河网被拆开；同名干流跨多个 HUC8 不再算一条独立河网。三站地板是 v9 已锁的科学目标，不得与本条 HUC8 写成同一句「放宽」。
   - 目录重叠 ≠ 合格年。下载后的同期日值、300 天年、QC 门另算。预登衰减 25–40%。衰减后若合格河网 <100，走 v9 已写的 3 站 / 6 年失败分支并报告；不得把 HUC8 分组本身说成那次放宽。
   - 约 161 在本目录上等于 naive `zfill(8)[:8]`，不是精确计数，也不是截断组合（截断在本目录上仍给出 166）。W1-A 精确最大重叠子集给出目录级 **166**。**166 不是 T2 完成**，也不是 150 条合格河网已经到手。禁止 161≥150 或 166≥150 所以 T2；禁止「比 98 多 63 条」或「比 98 多 68 条」。v2 混名 HUC8-only 表的 166 仍排除在诚实库存之外；W1-A 的 166 是同一规则下的精确目录单元，仍然只是目录重叠。
   - `never_sealed_networks` 原 14 个 id **一字不删、不改 token、不用补零 HUC2 重命名 `*_huc20` / `*_huc31` / `*_huc50`：** `jinsha_upper`，`chattahoochee_upper_middle`，`delaware_river_huc20`，`willamette_river_huc17`，`suwannee_river_huc31`，`yellowstone_river_huc10`，`rio_grande_huc13`，`madison_river_huc10`，`cahaba_river_huc31`，`mckenzie_river_huc17`，`mahoning_river_huc50`，`roanoke_river_huc30`，`santa_fe_river_huc31`，`clearwater_river_huc17`。
   - 切分：整条河网 50/20/30，按 climate × regulation × size 分层，seed + SHA-256，**下载前锁死**。实现文件在写出后为 `configs/network_catalog_v3_huc8.yaml` 与 `configs/network_catalog_v3_split.yaml`。本修订只锁规则，不把 `network_catalog_v1` 重映射成 executable catalog。
   - 禁止下载 name×HUC2 的 98 名单来「凑」T2。
   - `loire_mainstem` 与 `swiss_aar_rhine` 仍不得计入 T8 或 10 条非北美密封，直到日值公开可下载。

3. **E5 估计量换成已知 Σ 上的真可恢复性（BL-016）。旧门槛作废，不是过关。**  
   因变量：每个节点 × 每个缺口长度上、由已知 \(\Sigma\) 给出的真可恢复性（真条件风险或真最优 MAE）。  
   指标：Spearman 与校准斜率。**禁止**再用 `is_dam_like` 分类 AUC 当 E5 过关门。  
   四个单变量仍是 v9 锁死的那四个：gap-length only、acf only、donor \(R^2\) only、additive \(d/4\)。  

   **新门槛（必须同时满足）：**
   - 算子对真可恢复性的 Spearman \(\ge 0.90\)；
   - 四个单变量里最好的 Spearman \(\le 0.70\)；
   - 算子校准斜率 \(\in[0.9,1.1]\)；
   - 单变量 **没有** 校准要求。

   **Twin E（新硬负例，必须作为独立格子过关）：** 坝样节点与端点共享同一边际 ACF、同一 donor \(R^2\)，只在条件结构 \(\Sigma_{G|O}\) 上不同。用邻站个数/方向把 donor \(R^2\) 对齐；用传播时间滞后，让一个节点的边界信息与邻站冗余、另一个互补。Twin E **不得**并进 A–D 的混合表冒充过关。Twin A–D 的几何 2×2 仍保留，但不再用坝标签 AUC 打分。Twin D 若仍是 Twin B 的克隆，不得再称为独立格子（修克隆不是本修正的降门槛）。

   **Hold-out 族必须在评分前锁死。** 设计图集不得等于评分图集。过关声明需要在锁门之后、第一次重跑 E5 之前写入 freeze 的 hold-out 族；不得看完 AUC 再挑图。

   旧门槛记录（作废，不得改写成 pass）：`operator_auc=1`，`univariate_max_auc=1`，`identifiability_status: operator_separable_univariates_also_separable`，`gate_pass: false`。不重调生成器去救旧门。若算子在 Twin E 上仍赢不了单变量，那是可发表的负结果；不重调 φ / 噪声。没有把单变量 AUC 压到 0.65 的救援舱口。

4. **E5 新门槛比旧门槛更严。** 严格性论证见下一节。禁止把「单变量上限从 AUC 0.65 改成 Spearman 0.70」读成降低门槛。禁止「把 Spearman 0.90 等同于旧分类 AUC 0.85」。禁止「因为六河试点未过关而改写 E5」。

5. **恢复基准改成下载前锁定的两档预算。**  
   - **Tier 1（全语料）：** climatology、PCHIP/linear、Kalman、donor_regression、XGBoost，跑完整 gap × placement × information 格子。这档产出 T2 主 \(y\)（achieved skill）。  
   - **Tier 2（约 30 条河网，敏感性，不是主 \(y\)）：** 抽样规则现在锁死，不得下载后再「看哪些河算得动」：
     - \(n\) 目标 30，允许范围 \([28,32]\)；越界必须写 ledger，禁止静默变成 12 或 6。分层：气候带 × 调控状态 × 网络规模。样本与 SHA 在**下载前**锁死（`sample_locked_before_download: true`）。
     - 加上 air2stream、SAITS、CSDI、GRIN。SAITS 与 CSDI 与 GRIN 都在名单里；禁止写成 `csdi_or_grin` 一槽或。
     - 缺口 **30 与 90 与 180 全部跑**。禁止「30、90 或 180」。禁止看完 envelope 只报 90 或只报 180（BL-006 类）。`recovery_benchmark.primary_evidence_forbids` 与 `forbidden_after_seal` 同样列入 `selecting_the_better_of_90_and_180_days` 和 `posthoc_roster_shrink_after_download`。
     - 用途：强模型会不会改变可恢复性校准。答「会」或「不会」都不是把第二层提成 T2 主 \(y\) 的许可证。  
   - `pgdl_or_graph_wavenet` 仍留在 roster 上，归入 Tier 2 同类算力，不因为没写进「先跑这四个」就被事后踢出。  
   - 这是 **preregistered budget**，不是看了谁跑得完再收缩。  
   - `primary_evidence_forbids` 保持并追加：禁止 `best_epoch<50` 事后整类丢掉，禁止不等调参预算，禁止事后挑选 90/180，禁止下载后收缩 roster。

6. **站级入库 QC 在扩容前登记。**  
   每站必须过：NWIS sentinel、物理范围、approval A、常数段、跳跃、年 \(\ge 300\) 天。输出逐站 verdict 和 attrition 表。  
   Clearwater 已看过的序列：1848 值里 2 个 sentinel（\(\approx 0.11\%\)）。**禁止**只设 1% 比例阈值。任何值里出现 NWIS sentinel ⇒ `rejected_sentinel`。  
   本条登记的是门；实现由并行的 ingest QC 工作完成。本修订不改 `public_river_inventory` 聚类代码。  
   只做站级判决。禁止把整条河因一个污染站默删而不留站级行。1% 只是超范围 NA 化之后的 `rejected_range`，不能代替 sentinel 规则。0 °C 不是 sentinel。

7. **区间规则把 BL-012 内化到下一篇的网络单元（不改历史稿）。**  
   网络级 CI 仍需要 ≥100 个独立河网。  
   **12 河试点、6 河 W2 pipeline 重做、以及任何 \(n<100\) 的 development stop-loss，一律不得报告网络级 CI**，不得把 cluster-bootstrap 区间写进表或正文当推断。  
   网内描述性规则仍是 ≥5 个 site-year / overlap component（历史稿 BL-012）；那是另一套冻结、另一套单元。  
   W2 重做 6 河 pipeline：manifest 必须写 `n_networks: 6`，`passed: false`，`purpose: pipeline_verification_not_evidence`。判定标准是 gap_length 的 \(\Delta R^2\) 非零、不同缺口的前几行不再相同，不是「算子赢没赢」。`evaluate_success` 在区间被 withhold 或 \(n<100\) 时不得 confirmatory 通过 T2。

---

## Strictness argument (E5)

旧门：多图上算子分类 AUC \(\ge 0.85\)，且每个单变量 AUC \(\le 0.65\)；标签是生成器自己的 `is_dam_like`（高 AR + 隔离）。

新门：节点×缺口格子上，算子对**真可恢复性** Spearman \(\ge 0.90\)，四个单变量最好的 \(\le 0.70\)，算子校准斜率 \(\in[0.9,1.1]\)，并且 **Twin E 必须作为独立格子过关**（边际 ACF 与 donor \(R^2\) 被设计成相同），不得把 A–D 的好数字平均掉 Twin E 的失败。

为什么这更严，而不是更容易：

1. **估计量更硬。** 旧标签是生成器旋钮。算子和单变量都可以对着同一个旋钮拿到 AUC 1.00。那不是「算子会预测可恢复性」。新因变量是已知 \(\Sigma\) 的真条件风险 / 真最优 MAE。要通过，算子必须排出 \(\Sigma_{G|O}\) 的连续谱，而不是认出坝开关。
2. **0.90 Spearman 严于 0.85 AUC。** 分类 AUC 0.85 允许相当一部分排序错误。在节点×缺口的连续真值上 Spearman 0.90 是更紧的秩相关。旧门的 0.85 还是在一个已经泄漏的二分类标签上。
3. **校准是旧门没有的硬约束。** 斜率 \(\in[0.9,1.1]\) 要求幅度对，不只是排序对。单变量不要求校准，所以这条只加在算子上。T2 密封校准带是 \([0.8,1.2]\)；E5 已知 \(\Sigma\) 上用更窄的 \([0.9,1.1]\)，与「合成真值应当更准」一致。
4. **单变量 0.70 不是把 0.65 抬高。** 两个数字单位不同、标签不同。旧 0.65 是坝标签 AUC，当前实现里单变量已经是 1.00，那个 0.65 从未构成真实约束。新 0.70 是对真可恢复性的 Spearman 上限。唯一性间隔同样是 0.20（0.90−0.70 对 0.85−0.65），但间隔是加在连续真值上，再加校准，再加 Twin E。禁止把 0.70 与 0.65 做跨度量比较后宣称门槛降低。任何「单变量天花板从 0.65 放到 0.70」「把 Spearman 0.90 等同于旧分类 AUC 0.85」「因为六河试点未过关而改写 E5」的读法，本修正一律拒绝。
5. **Twin E 是旧 2×2 没有的硬负例。** 旧失败模式是 ACF / donor \(R^2\) 直接编码坝旋钮。Twin E 把这两条单变量对齐，只留下 \(\Sigma_{G|O}\) 的差。过关必须在这条硬负例上仍然满足 0.90 / 0.70 / 校准。这比「再调小一点 φ 直到单变量 AUC 掉到 0.65」更难。
6. **失败是结果，不是调参理由。** 若算子在 Twin E 上仍不比单变量好，写入负结果。禁止重调生成器、禁止改 0.90/0.70/[0.9,1.1]、禁止退回坝标签 AUC。

因此：新门在估计量、秩相关地板、校准带和硬负例上都严于旧门。本修订不是为了让当前 AUC=1/1 变成 pass。

---

## What did not change

1. `design_id` / `design_version` 仍是 `design_freeze_v9`。不是 executable。`DEFAULT_DESIGN_PATH` / `EXECUTABLE_DESIGN_VERSION` 仍是 `design_freeze_v4`。
2. 历史 once-lock、全国面板冻结哈希、BL-014、BL-015、密封未打开、`formal_evidence: false`、标题许可 false、水库不进标题。
3. T2 地板：`out_of_network_spearman_min` 不得低于 0.60；`network_bootstrap_lower_bound_min` 不得低于 0.40。两条 CI 规则仍在。定方法阶段只许加严这些数。六河没过关不是改这些数的理由。12 河 / 6 河 / 任何 \(n<100\) 不得报告网络级 CI。
4. `never_sealed_networks` 的 14 个 id 原样保留。金沙江 / Chattahoochee / 已下载 12 条河永远不当 sealed。
5. Loire / Swiss 仍不能计入 T8 或 10 条非北美密封。
6. 不删除 `recoverability_study_freeze_v1.yaml`。不把 `network_catalog_v1` 重映射成 executable catalog。不打开新的水温。不重调孪生生成器。
7. `tests/test_reference_runner.py` 与 `tests/test_formal_registry_builder.py` 里把 `design_freeze_v9` 当作 dummy mismatch 的用法不改。
8. 旧 E5 的 AUC 数字保持为失败/无信息记录。不得改写成 pass，也不得当成「T5 已做完」。
9. `forbidden_after_seal` 已有的 `selecting_the_better_of_90_and_180_days` 继续有效，并下放到密封前的第二层预算与 `recovery_benchmark.primary_evidence_forbids`。
10. `provisional_success_criterion.intended_locks_after_phase_4` 只是已锁 T2 数字的副本，不是下载后再锁的第二本日历。

---

## Falsifiers and failure closure (additions)

承接 v9 证伪，v9.1 追加：

1. **`e5_wrong_estimand_reinstated` / `e5_wrong_estimand_cited_as_result`：** 任何把 `is_dam_like` 分类 AUC 重新写成 E5 / T5 过关，或把旧 `gate_pass: false` 写成 T5 / 负向可恢复性。
2. **`twin_e_operator_no_better_than_univariates` / `aliasing_not_instantiated`：** Twin E 上算子 Spearman \(< 0.90\)，或最好单变量 \(> 0.70\)，或算子校准斜率落在 \([0.9,1.1]\) 外，或 Twin E 未作为独立格子报告。这是可发表的负结果。**不许**为了过关去重调 φ、噪声、邻站几何或缺口长度。
3. **`name_huc2_98_downloaded_as_if_inventory`：** 下载 name×HUC2 的 98 名单并把它写成 T2 语料。分组规则已经作废。
4. **`catalog_count_sold_as_t2` / `extra_rivers_by_loosening_claim`：** 把 31、98、约 161、W1-A 166 或任何目录重叠计数写成合格河网或 T2 过关，或写成「放宽后多 63 条」。
5. **`posthoc_model_budget_shrinkage` / `horizon_selected_after_envelope`：** 下载后因为算力不够才把 SAITS/CSDI/GRIN 踢出全格子，或只保留好看的缺口。两档预算必须在下载前锁死。
6. **`one_percent_sentinel_rule` / `sentinel_missed_by_percent_rule`：** 用 1% 比例阈值放行含 NWIS sentinel 的站。Clearwater 的 0.11% 已经说明这条规则不够。
7. **`network_ci_below_100`：** 12 河或 6 河或任何 \(n<100\) 报告网络级 CI。
8. **`never_sealed_or_t8_breach`：** 重写 never_sealed 14 个 token，或把 Loire/Swiss 计入 T8。
9. **`generator_retuned_to_save_gate`：** 为过旧门或新门而改 \(\varphi\) / 隔离 / 噪声。

失败闭合：E5 负结果写入 ledger，不重调生成器，不把水库检测救回标题。分组失败则停在目录级，不下载 98 名单，不降低 T2 地板来凑 \(n\)，不把约 161 当 T2。\(n<100\) 则 withhold 网络级 CI。第二层算不动则写预算失败，不事后缩 roster。

---

## Phase note

本修订属于 Phase 0/3 边界上的 **规格纠错**：在看新水温之前把分组、E5 估计量、算力预算和入库 QC 锁死。  
不替代 Phase 2 已写出的 Twin A–D 实现；那些图仍在，旧 AUC 门作废。Twin E 是新规格，实现另做，本文件不改生成器。  
`configs/network_catalog_v3_huc8.yaml` 与 `configs/network_catalog_v3_split.yaml` 由并行目录工作写出；本文件只要求冻结指向它们（文件存在时），并禁止在写出前下载新水温。

禁止：打开新的密封或扩容水温；改历史 `design_freeze_v4`；删除 v1 study freeze；声称 formal evidence / 标题许可 / 水库因果；把 12/6/5 河当确认；把审稿约 161 或 W1-A 目录 166 当 T2；下载 98 名单；为旧 E5 门调生成器。

---

## Phase 0 / v9.1 pass gate

```text
python scripts/45_validate_research_charter.py
PYTHONPATH=src python -m pytest tests/test_network_catalog_and_charter.py tests/test_design_contracts.py tests/test_p0_protocol.py -q
```

必须：本文件存在；`paper/boundary_ledger.md` 含 BL-016 与 BL-017；`design_freeze_v9.yaml` 含 `protocol_amendment: v9.1` 与新的 E5 Spearman / Twin E 键；T2 地板未被降低；`never_sealed_networks` 仍含原 14 个 id；`DEFAULT_DESIGN_PATH` 仍是 `design_freeze_v4`。
