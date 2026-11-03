# 2026-11-01 第四轮收尾完成与验收状态

本记录对应 `docs/reviews/wrr_r2_review_20261101/REVIEW_ZH.md`。`_r3` 候选保留为历史；本文件描述进一步加固后的 `_r4` 候选。

## 已完成的验收加固

1. **失败数与错误数仍是独立成功条件**
   - `release_provenance.validate_summary()` 明确要求 `failures == 0` 和 `errors == 0`，并保留非负整数、非零执行、退出码、计数恒等式、源码树身份、命令和解释器检查。
   - 980 的全库测试、发布测试和 985 汇总入口继续复用同一校验函数。

2. **JUnit 计数从 testcase 结果解析，并与摘要逐项核对**
   - `parse_junit()` 现在按 `<testcase>` 节点统计 `tests`、`failures`、`errors`、`skipped` 和派生的 `passed`。
   - 套件属性必须与 testcase 结果一致；只有套件属性、没有 testcase 的伪记录会被拒绝。
   - 校验器在核对 JUnit 哈希后，将五项计数与 JSON 摘要逐项比较。
   - JUnit 路径必须位于本次结果目录内；指向目录外文件的摘要会被拒绝。
   - 发布测试的 JUnit 必须实际覆盖 `TARGETED_TEST_FILES` 中的每个测试文件，而不是只在摘要的 `files` 字段声明完整清单。

3. **新增负向回归**
   - 全库路径保留正失败数、正错误数、JUnit 计数不符、失败 XML 配零失败摘要等反例。
   - 发布测试路径补齐正错误数、JUnit 计数不符、失败 XML 配正常摘要。
   - 新增 testcase 含失败但套件计数为零、无 testcase 的伪 JUnit、JUnit 路径逃逸，以及 JUnit 未覆盖声明测试文件四类反例。

4. **摘要数值与区间对象**
   - 验收时核对摘要中的关键数值仍为保存结果对应的 0.170、0.446、0.428、0.402、0.114、0.067 和 67.9%。
   - 经验日历句改为：`the year-distribution selector's paired RMSE-difference interval from warm-season screening includes zero`。
   - 明确“年份分布选择器”“配对区间”“RMSE 差”和对照对象；摘要 245 词，低于 250 词限制。

5. **身份范围说明**
   - `source_identity.src_tree_sha256` 覆盖 `src/**/*.py` 和 `pyproject.toml`。本记录不把它扩大为所有 `scripts` 或 `tests` 文件都与测试执行时版本绑定；测试清单和 JUnit 哈希另行绑定。

## 当前验收数字

- 全库测试：1,711 项，1,710 通过，0 失败，0 错误，1 跳过；JUnit 与摘要逐项一致。
- 声明的发布测试：143 项全部通过，并覆盖清单中的全部 18 个测试文件。
- 源码检查：`ruff check --select E4,E7,E9,F src`，0 findings。
- 证据门：本地 `inventory_only`，未声称作者/权利阻塞已解决。
- 严格扩展重放：11 张表通过，最大有限差 2.1316282072803006e-14。
- 主文 44 页，SI 109 页，摘要 245 词。
- 11 张科学 CSV 与 `_r2`、`_r3` 候选保持字节相同。

候选包、manifest 和验收记录：

- `dist/wrr_final_candidate_20261101_r4.zip`
- `dist/wrr_final_candidate_20261101_r4.manifest.json`
- `results/final_release_20261101_r4/acceptance.json`

包哈希、主文/SI 哈希、JUnit 哈希、测试计数和重放记录均在验收记录中；包内 README 不嵌入自身哈希。旧 `_r3`、`_r2` 包和更早候选保留为历史。

## 仍未完成

作者姓名、单位、ORCID、基金、CRediT、利益冲突、LUBW 合法审稿访问、永久仓库/DOI 和编辑部受限数据例外仍需作者处理。本地 `acceptance.complete=true` 不替代这些事项。

## 2026-11-02 综合审稿响应

本轮针对 `docs/reviews/wrr_comprehensive_review_20261102/REVIEW_ZH.md` 增补以下内容：

- 逐档案方向计数：控制缺口 805 例中 630 例绝对误差更小、169 例更大、6 例数值相同；经验日历 818 例中 231/57/530；年份集合实际改变的 288 例中 231 例改善、57 例变差。
- 扩展 bootstrap seed 披露：原始对照使用 `2026102969`，双家族扩展表使用 `20261031`，均为 10,000 次连接群组重采样。
- 新增不确定性范围表，区分年度 H30 区间、有限记录斜率区间、配对群组区间和三个随机种子的数值范围。
- 贡献与覆盖文字明确有限记录目标、长期完整站样本边界，以及“总体 RMSE 改善不等于每个档案改善”。
- README 增加当前候选命令，并把 `make review-package-check` 与 `make review-process-experiments-package-check` 标注为历史默认包检查。
- 访问材料整理为 `docs/reviews/wrr_comprehensive_review_20261102/SUBMISSION_READINESS_ZH.md`、`OPEN_RESEARCH_ACCESS_PLAN_ZH.md` 和 `CLAIM_EVIDENCE_ACCESS.csv`。

既有验收数字不改：发布测试 143 项；全库 1,711 项（1,710 通过、1 跳过）。P0 的作者信息、LUBW 合法审稿访问、受限数据例外和永久仓库/DOI 仍全部待办，本轮未完成、未对外确认，也未在文档中声称完成。
