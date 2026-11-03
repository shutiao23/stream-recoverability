# EMS 双审稿修订计划与执行台账

日期：2026-11-02（北京时间）

对象：`docs/reviews/ems_dual_review_20261102/REVIEW_ZH.md`。目标不是继续修补 WRR 稿件，而是并行建立一个可送 EMS 的最小投稿包；冻结的 WRR `_r4` 包、科学 CSV 和验收记录保持不动。

## 一、边界与原则

1. **不动冻结件**：不修改 `results/wrr_final_revision_20261031/` 的科学 CSV、`_r4` 包、`_r4` 验收记录和 WRR 主文/SI。EMS 版本放在新目录，避免污染已验收身份。
2. **先交付、再扩实验**：P0 的格式、软件、开放源模型和作者/访问材料优先；需要新数据、长期训练或外部登记的事项单列为依赖项，不用旧结果冒充。
3. **每个任务两个子 agent**：一个主做，一个独立复核；复核者不改主做者的文件，只写审计记录或在自己的目录实现。
4. **数字必须可追溯**：EMS 主文中的每个新数字都要对应 `results/ems_revision_20261102/` 下的文件或已有冻结表。
5. **不编造外部状态**：DOI、GitHub release、作者信息、LUBW 许可、OSF 登记如未实际取得，只能写“待完成”，不能写成已完成。

## 二、任务矩阵（每项两个子 agent）

| ID | 任务 | 子 agent 1（主做） | 子 agent 2（独立复核/并行） | 产物 | 状态 |
|---|---|---|---|---|---|
| T1 | 趋势尺度与统计证据 | 扩展 `slope_signal_audit.py`：Sen 斜率、MK/Hamed–Rao、误差/SE、符号翻转、显著性改变；生成表与 JSON | 独立从冻结表复算关键数字，写审计记录 | `results/ems_revision_20261102/trend_signal.*`、`paper/ems/trend_signal.tex`、`TREND_AUDIT_ZH.md` | 完成（数值复核一致；A2 的自相关稳健 MK 未做） |
| T2 | 软件库与元数据 | 建立独立小库 `gapbench/`：API、文档、示例、测试、MIT | 统一版本/描述/CITATION/LICENSE，修 Docker 安装面，做干净安装冒烟测试 | `gapbench/`、`docs/software/`、`pyproject.toml`、`CITATION.cff`、`Dockerfile` | 部分完成（`[test]` 干净安装/示例/13 测试通过；DOI/发布未完成） |
| T3 | EMS 稿件 | `paper/ems/main.tex`：elsarticle、Highlights、≤200 词摘要、声明、Software and Data Availability | `paper/ems/body.tex`：压缩后的科学主线、结果、讨论、Limitations、决策表 | `paper/ems/*.tex`、`main.pdf`、`highlights.txt` | 部分完成（37 页可编译；26 处作者/法律/DOI 占位符） |
| T4 | 随机数嵌套与流量诊断 | `ar1_bridge_pathwise`（SeedSequence.spawn）+ 嵌套性质测试 | 用现有 zero-flow / flow-comparator 输出写最低限度流量诊断；不伪造新流量 | `src/.../baselines.py`、`tests/test_ar1_bridge_nesting.py`、`paper/ems/open_source_flow.tex` | 部分完成（pathwise 嵌套 5 测试通过；流量仅代理诊断，A3 PARTIAL） |
| T5 | 文献与图件 | `references_ems.bib` 扩充到 40–60 条并接入正文 | 6–8 图/3–4 表选择、研究区示意图、Graphical abstract 素材 | `paper/ems/references_ems.bib`、`paper/ems/figures.tex` | 完成（52 refs、7 图、4 表；0 undefined/0 `(author?)`；残余非阻断 WARN） |
| T6 | 编译与独立审计 | 编译 PDF、检查 Highlights/摘要词数/声明/软件可用性 | 对照 REVIEW_ZH 逐条写 `RESPONSE_ZH.md`，标完成/部分/阻塞 | `paper/ems/main.pdf`、`RESPONSE_ZH.md` | 完成（T6 历史审计；投稿未就绪） |
| T7 | EMS Supporting Information | 建立 `supporting_information.tex` 与 S1–S11 表 | 独立复核数值、编译、主文 SI 引用与禁用措辞 | `paper/ems/supporting_information.pdf`、`SI_AUDIT_ZH.md` | 完成（13 页/11 表；H7→S5；release-rule SI 引用已移除；T9 来源/口径 WARN 关闭，SI 审计 PASS） |
| T10 | 提交审计与收尾 | 复核全部交付物并修复缺陷；补齐本地可完成的 PENDING 项；提交、打 v1.2.0 tag 并创建 GitHub release | wild cluster bootstrap（B6）、程序规模/内存实测（B8 部分）、版本元数据与发布 | 本文件 T10 节、`FINAL_STATUS_ZH.md` T10 节、`results/ems_revision_20261102/wild_cluster_bootstrap.*` | 完成（DOI 仍为外部依赖） |
| T8 | 最终整合审计 | 重编译主文/SI、干净安装、r4 冻结件、关键数字复核 | 更新 `RESPONSE_ZH.md`/`PLAN_ZH.md`，写 `FINAL_STATUS_ZH.md` | `FINAL_STATUS_ZH.md`、状态表 | 完成（submission-shaped，not submission-ready；外部 P0 与缺失实验未关闭） |

## 三、本轮承诺完成的 P0/P1 子集

- EMS 版标题、Highlights、≤200 词摘要、关键词、CRediT/COI/资助/AI 声明模板。
- Elsevier `elsarticle` 主文骨架，删除 Key Points/PLS，Software and Data Availability 节。
- 趋势标准误尺度的主结论：重写摘要/结论，加入误差/SE、符号翻转、显著性改变、Sen/MK 表。
- 开放源敏感性前置：报告 D2/经典法 0.158/0.156、保留率 93.7%、覆盖率 87.6%，说明主结论不变；不声称 LUBW 权利已解决。
- 流量最低限度诊断：使用现有 zero-flow 逻辑回归与 flow-comparator 表，报告关联方向和限制；不声称已完成 34 站日流量补齐或 air2stream-8 重训。
- 软件：独立 `gapbench` 小库、API 文档、示例、测试；版本/描述/CITATION 统一；Docker 安装 `.[review]` 含 LightGBM。
- 随机数：新增按路径独立随机流的桥实现和嵌套性质测试；旧 `ar1_bridge` 保留用于历史结果，不篡改冻结表。
- 文献：主文引用扩充到 40–60 条；图件压缩到 6–8 图、3–4 表。

## 四、明确不作为本轮完成的事项

这些事项需要新数据、长时间训练或外部机构，不能由本地代码/旧表替代：

- 34 站 FOEN/GKD 日流量补齐与 air2stream-8 重训；
- SAITS/BRITS、Kalman、LSTM 在同一 805/818 掩膜上的完整下游比较；
- 从联合模型抽日路径并按 Rubin 规则合并的多重插补实验；
- 历史长度/邻站消融、E-OBS/ERA5-Land 强迫敏感性；
- 新站点锁定确认和 OSF 预登记；
- Zenodo DOI、GitHub release、审稿人实际访问、作者/单位/ORCID/基金/COI/CRediT 和永久保存。

上述事项在 `RESPONSE_ZH.md` 中逐条标注“未完成/需外部依赖”，不得写成“已完成”。

## 五、验收门

1. `paper/ems/main.pdf` 可编译；Highlights 每条 ≤85 字符；摘要 ≤200 词；无 Key Points/PLS/AGU 文档类。
2. EMS 主文所有新数字能在 `results/ems_revision_20261102/` 或冻结表中找到。
3. `gapbench` 在干净虚拟环境可 `pip install -e "gapbench[test]"`，示例 30 分钟内跑通，`pytest -q gapbench/tests` 通过（本机冒烟测试）。
4. `ar1_bridge_pathwise` 的前 20 条路径与 500 条路径的前 20 条逐元素一致。
5. 现有 WRR 测试不被新代码破坏；新增测试通过。
6. `RESPONSE_ZH.md` 对 REVIEW_ZH 的每条主要意见给出“完成/部分/阻塞”及证据路径。

## 六、T6 历史审计状态（2026-11-02）

- 构建与格式：`paper/ems/main.pdf` 37 页、7 图、4 表、52 条参考文献；摘要 185 词；Highlights 最长 83 字符；PDF 文本 0 个 `??`、0 个 `(author?)`、0 个 AGU 期刊身份/WRR 标题（AGU 大小写不敏感唯一命中是参考文献作者 `Agustí-Panareda`）。
- 软件：干净 venv 中 `pip install -e gapbench` 与 quickstart 通过；任务原命令 `python -m pytest -q gapbench/tests` 因基础安装不含 pytest 而失败，补装后 13/13 通过。
- 冻结件：`dist/wrr_final_candidate_20261101_r4.zip` 的 SHA-256 复算为 `cae27ba49a02f0e6da165868bdf78017245b6e1fe549a899b10f1955b4cb2d9e`；`results/wrr_final_revision_20261031/` 下 11 个科学 CSV 与 git HEAD、r4 identity 全部一致。
- 结论：稿件已具备 EMS 投稿形态，但作者/法律/DOI/审稿访问和缺失实验未完成，不能标为 submission-ready。

## 七、T8 最终整合审计状态（2026-11-02）

- 构建：隔离副本中 `latexmk + bibtex` 重建主文 37 页/734012 bytes、SI 13 页/302377 bytes；主文 7 图、4 表、52 refs；SI 11 表 S1–S11；两者 0 Overfull/Underfull、0 undefined；摘要 185 词，Highlights 76/76/79/80/83 字符。
- SI：H7 三处引用均由 `Table S5` 支撑；`body.tex:191,207` 的 release-rule 表述已改为 `not in this Supporting Information`，SI 无 release-rule 小节，SI 审计 FAIL 关闭。残余 WARN：每表来源行、S3 `uniform_exact`、S4 端点表述、S8 MAE 分母。
- 软件：`/tmp/gapbench-final-venv` 中 `pip install -e "gapbench[test]"` PASS；quickstart PASS；13/13 tests PASS；`tests/test_ar1_bridge_nesting.py` 在仓库环境 5/5 PASS（需要 PyYAML，不属 `gapbench[test]` 安装面）。
- 元数据：`.zenodo.json`、根 `pyproject.toml`、`gapbench/pyproject.toml`、`CITATION.cff`、preferred-citation 均 1.2.0；`scripts/check_version_consistency.py` `RESULT: PASS`；仅历史 v1.0.0 tag/release，无 v1.2.0 tag/release/DOI。
- 冻结件：r4 包 SHA-256 `cae27ba49a02f0e6da165868bdf78017245b6e1fe549a899b10f1955b4cb2d9e`；11/11 CSV 与 git HEAD 和 r4 identity 一致；无 tracked CSV 修改。
- 结论：**submission-shaped，not submission-ready。** 外部 P0（作者/法律/DOI/审稿访问）和缺失实验（A3 flow、B4 baselines、B5 MI、B6 cluster、B8 timing、A5/A6/A8、锁定确认）仍未关闭。详见 `FINAL_STATUS_ZH.md`。

## 八、T9 SI 可追溯性收尾（2026-11-02）

- S1–S11 全部加入 Source 行。
- S3 补 `uniform_exact` 未保存说明与 0.449/0.135、55/8 flips。
- S4 区分 4,096 draws 的区间端点（87.4–89.9%）与点估计（87.5–89.7%）。
- S8 明确 log-MAE、paired common cases 66,099/33,609、210 站/17 组。
- `SI_AUDIT_ZH.md` 由 WARN/FAIL 更新为 PASS；SI 重建 13 页、11 表、0 警告。

## 九、T10 提交审计与收尾（2026-11-03）

- 审计发现并修复：`tests/test_submission_admin_packets.py` 仍断言旧 `.zenodo.json` 标题与 1.1.0 版本，与 1.2.0 元数据冲突；已更新为 gapbench 标题与 1.2.0，全库测试恢复零失败。
- B6（部分关闭）：新增 `scripts/986_wild_cluster_bootstrap.py` 与 `tests/test_wild_cluster_bootstrap.py`（5 项测试含模拟覆盖率检验）。对 10 个配对 RMSE 差对比给出 Rademacher 与 Webb 六点 wild cluster 区间（影响函数法，17 群组不重抽样）；结果表 `results/ems_revision_20261102/wild_cluster_bootstrap.{csv,json}`。中位 wild/重抽样宽度比 1.02；日历 CDF 两种方法均含零；日历 D2−经典法在群组重抽样下含零、在两种 wild 权重下不含零，正文与 SI 均按方法依赖表述，不升级为稳定排序。新增 SI 表 S12。
- B8（部分关闭）：实测 quickstart 0.13 s / 35 MiB；完整 1,623 档案包内重放 9.7 s / 289 MiB（单核）。`software_availability.tex` 与 SI S10 的 PENDING 已用实测值填充；程序规模 24 文件 / 1,012 行 Python / 264 KiB（23 KiB 压缩）。
- 发布：`CITATION.cff`、`.zenodo.json`、SI S10、软件可用性声明与根 README 统一为“GitHub release v1.2.0 标记本版本；Zenodo DOI 仍未 mint”。提交后创建 `v1.2.0` 标注 tag 与 GitHub release。
- 构建复核：主文 37 页 / 0 Warning / 0 Overfull / 0 Underfull / 0 undefined；SI 15 页 / 12 表（S1–S12）/ 同样零警告；52 条参考文献不变。
- 仍未完成（外部/需新数据训练）：作者信息、LUBW 法律与审稿访问、Zenodo DOI、A3 日流量与 air2stream-8、B4 现代基线、B5 联合模型多重插补、A5/A6/A8、锁定确认。
