# 开放研究访问计划（草案，尚未执行）

日期：2026-11-02（北京时间）。对象：`_r4` 本地候选及其科学证据。

**状态声明：本文件是计划草案。它没有创建仓库、没有申请 DOI、没有联系 LUBW 或期刊编辑，也没有取得任何访问许可。** `[作者确认]`、`[编辑/法务确认]` 均为待落实占位，不代表已经同意。不得把本计划写成已执行的访问安排。

## 一、公开且可重放

以下材料可随候选包或公开仓库提供，用于重放已保存的科学表、紧凑输入、图和 PDF：

| 类别 | 现有路径 | 可重放范围 |
|---|---|---|
| 处理后年度表 | `results/wrr_final_revision_20261031/*.csv`（11 张科学 CSV） | 保存表的逐项算术、身份和严格重放 |
| 紧凑输入 | `results/wrr_final_revision_20261031/annual_predictions_compact.csv`、`case_designs.csv`、`reference_truths.csv`、`reference_year_sets.csv`、`retention_geometry_cases.csv`、`retention_choice_counts.csv` | 经验日历扩展、逐档案比较、区间重采样 |
| 图与报告脚本 | `scripts/552_recreate_aggregate_figures.py`、`scripts/981_stanford_revision.py`、`scripts/930_delivery_consistency.py` | 由聚合表重绘指定图、重算表内算术 |
| PDF 与 TeX | `paper/wrr_tr/review_completion_article.pdf`、`paper/wrr_tr/review_completion_supporting.pdf` 及对应 `.tex` | 文本与页面身份、解压后编译 |
| 验收与重放记录 | `results/final_release_20261101_r4/acceptance.json`、`package_verification.json`、`package_delivery_check.json`、`extension_replay.json`、`ci_local_summary.json` | 包哈希、成员身份、11 表重放、测试与源码检查记录 |
| 本轮审查证据 | `results/wrr_comprehensive_review_20261102/archive_level_comparisons.csv`、`bootstrap_seed_sensitivity.csv`、`scope_diagnostics.json`、`documentation_findings.json` | 逐档案计数、21 个 seed 的区间方向、文档核对 |
| 候选包 | `dist/wrr_final_candidate_20261101_r4.zip` | 本地候选；尚未提交，重建后哈希会变化 |

这些材料能支持“保存表算术与紧凑输入重放”，不能支持从原始提供方数据完整重训。

## 二、受限材料

以下材料不进入公开包，需单独授权或编辑中介访问：

- 原始 case 缓存与逐案例预测，例如 `private/wrr_review_case_evidence_20261027/`、`private/wrr_heat_gap_source_sensitivity_20261027/`、`private/wrr_groupmax_annual_calibration_20261027/`。
- 训练完成的源模型权重与部分校准对象；这些文件不在候选 ZIP 中，重训/重放依赖它们。
- 仅本地可用的证据与逐站点诊断，包括 `private/gems_reviewer_bundle/` 及 README 列出的 isolated local evidence。
- LUBW 依赖的原始观测、模型和派生结果；即使目标站不在 LUBW 集合内，正权重源角色仍可能包含 LUBW case，不能自动排除。
- 其他提供方条款未解决的原始缓存。

受限部分应由 `[作者确认]` 与 `[LUBW 法务确认]` 逐项标记，不能以“结果已聚合”替代再分发许可。

## 三、待定事项

- 作者顺序、单位、ORCID、基金、COI、CRediT：`[作者确认]`。
- LUBW 审稿访问与再分发许可：`[作者确认]` + `[LUBW 法务确认]`。
- 期刊对受限数据例外的书面处理：`[编辑/法务确认]`。
- 永久仓库、版本号与 DOI：`[作者/机构确认]`。
- 审稿访问联系人及访问日志责任人：`[作者确认]`。

## 四、建议的审稿访问路径（尚未执行）

1. **投稿前申请。** 通讯作者在送审前向期刊编辑说明受限材料范围，并请求编辑中介访问安排；不等到审稿人索要时才补。`[作者确认]` + `[编辑/法务确认]`
2. **编辑中介访问。** 由编辑或编辑部向指定审稿人提供限时、只读的受限证据包；作者不直接公开再分发。`[编辑/法务确认]`
3. **使用协议。** 审稿人签署仅用于评审、不得复制或再分发的使用条款；访问范围、期限和联系人记录在案。`[编辑/法务确认]`
4. **公开包与受限包分离。** 公开包保留聚合表、代码、重放脚本、PDF 和验收记录；受限文件只通过清单、哈希和访问说明引用，不嵌入公开 ZIP。
5. **LUBW 专项许可。** 对 LUBW 原始观测、训练模型和派生结果分别确认审稿访问与再分发条件；若未获许可，提供替代证据和明确的范围限制。`[作者确认]` + `[LUBW 法务确认]`
6. **发表后保存。** 录用后把可公开部分存入永久仓库并取得 DOI；受限部分按期刊和机构要求登记保存位置与访问条件。`[作者/机构确认]`

在上述步骤取得书面结果前，`dist/wrr_final_candidate_20261101_r4.zip` 只是本地发布候选，不是完整的 Open Research 包。相关 P0 清单见
[SUBMISSION_READINESS_ZH.md](SUBMISSION_READINESS_ZH.md)，逐主张映射见
[CLAIM_EVIDENCE_ACCESS.csv](CLAIM_EVIDENCE_ACCESS.csv)。
