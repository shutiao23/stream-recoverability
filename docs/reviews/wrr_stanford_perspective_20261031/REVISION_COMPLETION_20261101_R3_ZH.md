# 2026-11-01 第三轮收尾完成与验收状态

本记录对应 `docs/reviews/wrr_r2_review_20261101/REVIEW_ZH.md`。上一版 `_r2` 候选（`7d1d5b9a…469c395`）保留为历史；本文件描述修正后的 `_r3` 候选。

## 已完成的验收加固

1. **失败数与错误数重新成为独立条件**
   - `release_provenance.validate_summary()` 现在明确要求 `failures == 0` 和 `errors == 0`，不再只检查 `passed = tests − failures − errors − skipped` 的计数恒等式。
   - 980 的全库测试、发布测试和 985 汇总入口复用同一校验函数。

2. **JUnit 实际计数与摘要逐项核对**
   - 校验器解析已核对哈希的 JUnit，并比较 `tests`、`passed`、`failures`、`errors`、`skipped` 五项。
   - JUnit 哈希正确但摘要计数不符、失败 XML 配零失败摘要、正失败数、正错误数、零执行、全跳过、非零退出码和源码树不符均被拒绝。
   - 新增 5 个负向回归测试，覆盖全库失败数、错误数、JUnit 计数不符、失败 XML 和发布测试失败数。

3. **摘要中的区间对象**
   - 经验日历句改为：`the CDF selector's paired RMSE-difference interval from warm-season screening includes zero`。
   - 明确“选择器”“配对”“RMSE 差”和对照对象；摘要 249 词，仍低于 250 词限制。轨迹句中的 seed/region 细节已压缩，负结果未被改写。

4. **身份范围说明**
   - `source_identity.src_tree_sha256` 覆盖 `src/**/*.py` 和 `pyproject.toml`。本记录不把它扩大为所有 `scripts` 或 `tests` 文件都与测试执行时版本绑定；测试清单和 JUnit 哈希另行绑定。

## 当前验收数字

- 全库测试：1,704 项，1,703 通过，0 失败，0 错误，1 跳过；JUnit 哈希与摘要逐项一致。
- 声明的发布测试：136 项全部通过。
- 源码检查：`ruff check --select E4,E7,E9,F src`，0 findings。
- 证据门：本地 `inventory_only`，未声称作者/权利阻塞已解决。
- 严格扩展重放：11 张表通过，最大有限差 2.1316282072803006e-14。
- 主文 43 页，SI 107 页，摘要 249 词。

候选包、manifest 和验收记录：

- `dist/wrr_final_candidate_20261101_r3.zip`
- `dist/wrr_final_candidate_20261101_r3.manifest.json`
- `results/final_release_20261101_r3/acceptance.json`

包哈希、主文/SI 哈希、JUnit 哈希、测试计数和重放记录均在验收记录中；包内 README 不嵌入自身哈希。旧 `_r2` 包和更早候选保留为历史。

## 仍未完成

作者姓名、单位、ORCID、基金、CRediT、利益冲突、LUBW 合法审稿访问、永久仓库/DOI 和编辑部受限数据例外仍需作者处理。本地 `acceptance.complete=true` 不替代这些事项。
