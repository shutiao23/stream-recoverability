# Protocol change v8 to v9

Date: 2026-08-26  
Status: new-study freeze；不是结果，也不是标题许可。  
Supersedes: `docs/protocol_change_v7_to_v8.md` + `configs/recoverability_study_freeze_v1.yaml`（章程持有、门槛未锁）  
Does not touch: `configs/design_freeze_v4.yaml`、金沙江 / Chattahoochee 历史稿、134k-run 历史流水线

这是**下一篇研究的新冻结**，不是对 `design_freeze_v4` 的静默改写。  
v4 仍然是历史稿和它那条 134k-run 流水线的 once-lock。`DEFAULT_DESIGN_PATH` 不改指向。全国面板冻结哈希不改。金沙江源质量边界仍是 BL-014。密封水温仍然不打开。

v8 在 6 条可评河试点未过关之后，把问题写进了章程，但把数字门槛留成「先不定死」。那是持有姿态，不是可重复的 confirmatory 协议。v9 把门槛锁死，避免下一轮再出现「标签冻了、数字没冻」的空冻结。

---

## Why

现在这篇金沙江 / Chattahoochee 稿子已经按 BL-011 到 BL-014 把不该说的话说回去了：全国混合 AUC 不是有效推广度量，重叠锚点不能当独立样本，标题不再写水库结构预测可恢复性，金沙江没有可追溯的逐值质量码。继续改词句改变不了「两条河上的描述撑不起外推」。

v8（`research_charter_v1.md` + `recoverability_study_freeze_v1.yaml`）已经把下一问写成：拟合之前能不能预估缺口补得有多差，并按预估选备用站。但它明确写了「数字门槛先不定死」，库存目标仍是 12–20 条河，切分仍是 40/20/40，主估计仍是技能比而不是已经写好的 Schur 算子。第一次整条河留出没有过关，选站没有稳定赢过 15%。在这个位置再开一轮「先看数再锁门槛」的 confirmatory，会重复 v8 的空冻结。

所以 v9 换冻结，不换历史稿。

**标题论题从「水库结构预测可恢复性」改为「可恢复性是可预测、可迁移的网络属性」。**  
建坝 / 调节只是协变量和机制检验，不是标题。没有水库运行记录，就不写水库因果。

---

## What changed

1. **新研究冻结，不是改写 v4。**  
   下一篇的冻结文件叫 `configs/design_freeze_v9.yaml`。  
   `configs/recoverability_study_freeze_v1.yaml` **被取代，但不删除**。它仍是 2026-08-25 的 v8 持有记录。  
   历史稿、`design_freeze_v4`、134k-run 流水线、全国面板冻结哈希，全部留在原处。任何人不得把 v9 门槛回写进 v4，也不得把金沙江 / Chattahoochee 的已看结果重新标成 confirmatory。

2. **标题论题。**  
   旧标题论题（BL-013 已撤回、此处再冻结一次）：reservoir structure predicts recoverability。  
   新标题论题：recoverability is a predictable, transferable network property。  
   调节是 covariate / mechanism，不是 headline。没有 operations data，禁止水库因果句。`reservoir_mechanism_in_headline` 必须保持 `false`。`headline_claim_licensed` 必须保持 `false`，直到密封一次打开并且 T2/T3（或书面降级后的 T2）过关。

3. **主估计量换成已经实现的 Schur 补算子。**  
   主估计量不再是 v8 冻结里的技能比  
   `1 - E[L(Y_G, f_S)] / E[L(Y_G, f_0)]`，  
   也不再是加性 `d/4` 启发式。  
   主算子就是 `src/stream_recoverability/analysis/conditional_observability.py` 里已经实现的条件观测算子：

   \[
   \Sigma_{G\mid O}=\Sigma_{GG}-\Sigma_{GO}\Sigma_{OO}^{-1}\Sigma_{OG},
   \]

   \[
   \mathcal R=1-\sqrt{\overline{\mathrm{diag}}\Sigma_{G|O}/\overline{\mathrm{diag}}\Sigma_{G|\mathrm{clim}}}.
   \]

   拟合期协方差先算 \(\hat{\mathcal R}\)，再拿到没用来改方法的河网上对 achieved skill。  
   该文件里的 `predicted_skill`（高斯 MAE 比 \(1-\mathrm{mae}_S/\mathrm{mae}_0\)）和 `normalized_conditional_variance` 仍是次级摘要，不能代替上面的 \(\mathcal R\)。加性 `d/4` **不是**这个算子的实现。

4. **加性 \(d/4\) 降为预先登记的基线 #4。**  
   四个单变量基线，顺序锁死：
   1. gap-length only
   2. acf only
   3. donor \(R^2\) only
   4. additive \(d/4\)（旧主估计，现为 preregistered baseline #4）

   另外必须有一条拓扑基线：nearest-donor distance 或 nearest-donor correlation。  
   选站对照里，非 oracle 最强基线集合包括 random、degree、distance、correlation，以及 Oh & Bartos 2025 QR。  
   旧公式 `R2_avail = R2_donor + (1 - R2_donor) * rho(d/4)^2` 只当最弱对照和退化展品。

5. **硬类型标签是设计缺陷，不是发现。**  
   当 \(R^2_{\mathrm{donor}}\ge 0.5\) 时，加性公式会强迫写成邻站型，不管本地记忆有多强。这是公式恒等，不是八站上的经验发现。  
   正式记录是 **BL-015**（已写入 `paper/boundary_ledger.md`）。它引用八站恒等和 `heuristic_degeneration.py`，数字来自 `results/revision/recoverability_type_classification_uncertainty.csv`。四站是 \(R^2_{\mathrm{donor}}\ge 0.5\) 的公式强制；B1/S2 不是恒等（\(D<0.5\)），只是实现的 30 天记忆远低于翻转阈值。不得把「六站都不含记忆信息」写成公式恒等。v8 的 `known_degeneration` 和 `hard_type_labels_are_primary: false` 继续有效。

6. **推断单元是 river network。**  
   站年嵌套在站里，站嵌套在河里。缺口、掩膜、锚点都是重复测量，不是独立样本。  
   区间估计用 cluster bootstrap，按河重抽样。  
   **只有独立河网数 \(\ge 100\)（或 `design_freeze_v9.yaml` 写明且不得低于此数的 floor）时，才允许报告置信区间。**  
   这与历史稿 BL-012 的「少于五个 site-year / overlap component 就扣住 p 值和 CI」是两套冻结、两套单元；历史稿规则不改，下一篇不再用 5 个站年当可报告区间的 floor。

7. **T2 / T3 数字门槛在读任何新的密封水温之前锁死。**  
   这取代章程里的「数字门槛先不定死」。那句话是 6 河试点未过关之后的 v8 持有姿态；v9 锁门槛，就是为了不让下一轮 confirmatory 再冻标签、不冻数字。

   **T2（大样本主检验，必须同时满足）**
   - 库存设计目标：\(\ge 150\) 条独立河网；每条 \(\ge 3\) 站且 \(\ge 8\) 年同期重叠；\(\ge 3\) 个气候带；\(\ge 2\) 个大陆。150 是目标，不是现状。公开目录目前审计到的上限大约是 USGS 四站/八年 31 条、下载后同期够用 6 条。
   - 推断单元 = river network；按河做 cluster bootstrap；独立河网 \(n\ge 100\) 时 CI 必须可报告。
   - 主数字：out-of-network Spearman\((\hat{\mathcal R},\text{achieved skill})\ge 0.60\)。
   - **两条 CI 规则同时锁死，不得只留一条：** (i) 95% CI 下界 \(> 0.40\)（v8 已写、6 河试点没过的那条，v9 不因为没过就丢掉）；(ii) 同一条 95% CI 下界还要高于四个预先登记单变量基线的**点估计**。
   - 校准：密封集上 |predicted − achieved| skill 的 median |bias| \(< 0.10\)，斜率 \(\in[0.8,1.2]\)。
   - 这些数字是 **confirmatory 地板**。定方法阶段的把握分析只许加严，不许放宽。6 河试点 Spearman ≈ 0.77、区间下沿约 −0.01 是**没过关的试点**，不是把 0.60 写成可达到的证据。`public_river_check.json` 的 0.821 / 0.094 含 Clearwater，不得引用。

   **T3（决策，必须 a 或 b）**
   - (a) Placement：greedy log-det 对最强非 oracle 基线（random、degree、distance、correlation、Oh & Bartos 2025 QR）的 worst-case MAE 降幅 \(\ge 15\%\)，且在 \(\ge 3\) 个气候带成立；同时报告与 oracle 的差距。
   - (b) Gap triage（更优先的标题路径）：固定误放行率锁死为 5% 的填补误差 \(>0.5^\circ\mathrm{C}\)（不是“例如”）。相对 length-only 的 safe-fill 提升 \(\ge 30\%\) 相对（\(\ge 15\) 个百分点绝对）。

   格子至少 20 次 placement。SAITS 与 CSDI（或 GRIN）留在 roster，禁止再用 `best_epoch<50` 整类踢出。  
   T1（单调性、log-det 次模、\(d/4\) 退化区、高斯 MAE 下界）、T4（自然缺测）、T5（拓扑匹配的调节效应）、T6（至少一个可检验的推广失败区，优先 SEPlains × BFI）、T7（密封 confirmatory）、T8（公开数据优先）仍按 `docs/v9_redesign_master_plan.md` 执行。过关路径是 T1–T7。T3 失败但 T1、T2、T4、T5、T7 成立时，标题从 decision 降为 predictability，不重开密封、不重调算子。

8. **切分规则按整条河网锁，不在本协议里重映射现有目录。**  
   单元：entire network。禁止站级对半切。  
   目标比例：development 50% / validation 20% / sealed 30%。  
   密封集绝对下限：\(\ge 40\) 条河网。30% 是混合目标（150 条时约 45 条）。T7 取「至少 40」，不要同时写 30、40、45 三套地板。  
   其中 \(\ge 10\) 条必须在北美洲以外，**并且**主分析日值公开可复核（T8）。现在目录里的 `loire_mainstem`（无起止年）和 `swiss_aar_rhine`（历史日均要另订）**不能计入**这 10 条，直到日值真正公开且可下载。  
   禁止：把 `jinsha_upper`、`chattahoochee_upper_middle`，或已经下载过水温的 12 条河（Delaware、Willamette、Suwannee、Yellowstone、Rio Grande、Madison、Cahaba、McKenzie、Mahoning、Roanoke、Santa Fe、Clearwater）标成 sealed；在定方法阶段读取密封水温结果。  
   v8 冻结用的是 40/20/40 和 12–20 条河。那两套数作废。  
   **本协议只锁规则。当前 `network_catalog_v1.yaml` 不在 Phase 0 重切。目录扩容是 Phase 3。**

9. **库存目标从 12–20 提到 \(\ge 150\)。**  
   同时要求 \(\ge 3\) 个气候带、\(\ge 2\) 个大陆。每条合格河默认 \(\ge 3\) 站、\(\ge 8\) 年同期。  
   合格河网 \(<100\) 时走失败分支：放宽到 3 站 / 6 年，并在稿和 ledger 里写明这次放宽；RGCN 只当补充政策床，不顶主检验。不得事后把切分或资格改到刚好过关。

10. **金沙江和 Chattahoochee 永远是 `historical_seen`，永久失去 confirmatory 资格。**  
    目录已经这样标了（`jinsha_upper`、`chattahoochee_upper_middle`，`split_role: historical`，`historical_seen: true`，`use: already_used`）。本协议再写一遍：它们可以当背景和历史病例，不能进 sealed，不能进 leave-one-network-out 的 confirmatory 分子，不能因为「公开数据不够」而被救回最后检验。Jinsha 在公开数据路径里降为 SI 区域病例（T8），不改变 `historical_seen`。

11. **v8 章程那句「数字门槛先不定死」作废。**  
    原文在 `docs/research_charter_v1.md` 的「怎样算过关」，以及 `recoverability_study_freeze_v1.yaml` 的 note / `provisional_success_criterion.status: provisional_until_development_power_analysis`。  
    那是 6 河试点未过关之后的持有句。v9 在打开任何新的密封水温之前锁 T2/T3。后续不得再用「等定方法阶段算清把握再锁」把已锁数字改松。章程和校验器的更新是 Phase 0 的其余工作，不是本文件的静默生效。

---

## What did not change

1. 历史 once-lock。`design_freeze_v4`、540-unit 一次打开、train-only 启发式、2018--2020 development-test 可见性标签，全部不动。
2. 全国面板冻结哈希。BL-011 的 pooled LOEO AUC 0.407 仍是历史稿的冻结主数字，只当预先登记的有缺陷诊断，不重跑、不改估计量。
3. 金沙江源质量边界 BL-014。没有逐值质量码、仪器/率定、时区、水文日切割和「日温从未插值」的证明之前，金沙江仍是探索性背景网，不是 fully traceable artificial-mask 真值。
4. 密封结果仍然未打开。`sealed_outcomes_opened: false`。目录阶段只许查站在不在、目录年份够不够，不许用水温给方法打分。
5. `formal_evidence: false`。没有标题许可。`headline_claim_licensed` 保持 false。12 河试点数字不是 confirmatory。
6. 金沙江 / Chattahoochee 不得当作密封确认：`jinsha_outcomes_reusable_as_confirmation: false`，`chattahoochee_outcomes_reusable_as_confirmation: false`。
7. 硬类型标签不是主结果，event-wise best envelope 不是主结果，全国「有没有坝」AUC 不是可恢复性证据。
8. 没有水库运行记录，就不写水库因果。E10 仍是 companion only。
9. 不删除 `recoverability_study_freeze_v1.yaml`。不重映射当前目录。不打开密封水温。
10. `tests/test_reference_runner.py` 和 `tests/test_formal_registry_builder.py` 里把字符串 `design_freeze_v9` 当作 dummy mismatch 的用法不改。那些测试不读 yaml。以后写出真正的 `configs/design_freeze_v9.yaml` 时，不得为了「对上名字」去改这两处字符串。

---

## Falsifiers and failure closure

预先登记的证伪（承接 v8，按 v9 主算子重写判定对象）：

1. 在已知对错的假河网上，算子把「谁有用」排反（`synthetic_wrong_information_ordering`）。
2. 换邻站方向或个数以后，结论只是河头河尾的假象（`topology_alias_after_donor_geometry_match`）。T5 要求坝样节点不在端点、端点不是坝样的 twin。
3. 并不比四个单变量基线更好，尤其是不比 donor \(R^2\) only 更好（`no_incremental_value_over_simple_predictors`）。
4. 密封集主门槛未过，或只靠一条河撑起来（`sealed_criterion_miss_or_single_network_driver`）。
5. 选站没有决策效用（`no_sensor_policy_utility`）。
6. 只在均匀假缺口上好用，真实缺测上不行（`natural_outage_failure`）。T4 必须在 `real_missing_blocks.csv` / `willamette_mainstem_real_missing_blocks.csv` 的自然缺测子集上复现主结论。

失败闭合，禁止用重调去救算子：

- **算子赢不过 donor \(R^2\)：** 标题改成 predictability；**不许为了保住 T1 新颖性去重调算子。** 加性 \(d/4\) 更不能救回主估计。
- **选站只比 random 好出个位数百分比：** 标题走 triage (b)，不把 placement 写成主结论。
- **高斯二阶在 PIT/QQ 上失败：** 保留单调性；改报分位宽度，不把高斯 MAE 下界写成已证实定理。
- **合格河网 \(<100\)：** 放宽到 3 站 / 6 年，并报告这次放宽；不降低 T2 的 Spearman / 校准数字来凑过关。
- **密封未过关：** 写入 ledger，不解冻，不改问题，不换更好看的 90/180 天。历史两河稿仍是描述性病例。

密封主门槛失败时，下一篇是负向基准，或强接受路径停止。不得把历史稿重新说成确认。

---

## Eight phases

高层执行顺序（细节以 `docs/v9_redesign_master_plan.md` 为准）：

| Phase | 目标 |
| --- | --- |
| 0 | Stop-loss + preregister：本文件、`configs/design_freeze_v9.yaml`、BL-015、章程/校验器改到 v9 |
| 1 | Operator + theory：`paper/theory.md`、算子扩展、Shapley、合成偏差表 |
| 2 | Identifiability + twins |
| 3 | Corpus：公开目录扩到库存目标，密封锁名单，质量旗标。**现在不切现有目录。** |
| 4 | Main experiment：嵌套消融、校准、按河 cluster bootstrap |
| 5 | Decision + real missing：政策曲线、triage ROC、自然缺测 |
| 6 | Mechanism：匹配后的调节效应、BFI、漂移规则 |
| 7 | Sealed once-open：confirmatory 冻结 + once-lock |
| 8 | Writing：新标题、key points、图计划 |

Phase 0 禁止：打开密封水温；改历史 `design_freeze_v4` 执行路径；删除 `recoverability_study_freeze_v1.yaml`；声称 formal evidence、标题许可或水库因果；把 12 河试点当确认；编造新的八站数字。

---

## Phase 0 pass gate

```text
python scripts/45_validate_research_charter.py
```

必须对 **v9 冻结**（`configs/design_freeze_v9.yaml`）以退出码 0 通过。  
`design_freeze_v9` 只是下一篇研究冻结的文件名，**不是**历史 executable。`DEFAULT_DESIGN_PATH` / `EXECUTABLE_DESIGN_VERSION` 必须保持 `design_freeze_v4`。  
钉住 `design_freeze_v4` 的历史 formal-roster 测试必须继续通过。  
BL-015 必须把 \(R^2_{\mathrm{donor}}\ge 0.5\) 的硬标签写成设计缺陷，而不是经验发现；B1/S2 单独标成「实际上翻不过」，不要写成公式强制。
