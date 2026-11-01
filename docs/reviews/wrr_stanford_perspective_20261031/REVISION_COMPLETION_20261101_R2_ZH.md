# 2026-11-01 第二轮收尾完成与验收状态

本记录对应 `docs/reviews/wrr_postfix_review_20261101/REVIEW_ZH.md`。上一份 `REVISION_COMPLETION_20261101_ZH.md` 和 r2/`2b0afcfe…468143a` 包保留为历史；本文件描述修正后的 `_r2` 候选。

## 已完成的四项收尾

1. **仓库外 `--out` 紧凑重放**
   - 981 的紧凑输入指纹改用统一的 `relative_label`，不再对仓库外路径调用 `relative_to(ROOT)`。
   - 新增集成测试：无原始 case 缓存、结果目录和论文目录都在仓库外，仍能完成 8,115 行重算、论文片段写出、manifest 生成和全部输出哈希校验。

2. **全库测试摘要的验收条件**
   - 新增 `scripts/release_provenance.py`、`984_full_pytest_summary.py` 和 `985_build_local_ci_summary.py`。
   - 全库摘要从真实 JUnit 生成，绑定 `junit_sha256`、执行命令、解释器、Python 版本和 `src` 树哈希。
   - 980 现在拒绝：非零退出码、零执行、零通过、全跳过、负数、`passed != tests − failures − errors − skipped`、JUnit 哈希不符、源码树不符。
   - 新增负向测试覆盖上述反例；正常 1,699 项摘要仍被接受。

3. **表规格与单位**
   - `masks` 明确为“年份 → `start:length` 多区段编码”的 JSON 对象；`start` 是该年日索引中的零起点行位置，`length` 是连续日数，多区段用 `;` 分隔。
   - 几何表新增逐字段单位：斜率类为 °C/十年，MSE 与交叉项为 (°C/十年)²，残差方差为 °C²，权重平方距离为 十年⁻²。表级 `unit` 仅作摘要。

4. **显示与摘要**
   - SI 中全 1 向量改用 `\mathbf{1}`；重编译后文本抽取为 `h = α1 + bx_F + ε`，不再是 `⊮`。
   - 摘要增加经验日历对照：818 档案上暖季 RMSE 0.114、全保留 0.067，CDF 区间包含零；摘要 247 词，仍低于 250 词限制。
   - 主文继续保留控制缺口的 0.446→0.170 和两类队列不可相减的边界。

## 当前验收数字

- 全库测试：1,699 项，1,698 通过，0 失败，0 错误，1 跳过。
- 声明的发布测试：131 项全部通过。
- 源码检查：`ruff check --select E4,E7,E9,F src`，0 findings。
- 证据门：本地 `inventory_only`，未声称作者/权利阻塞已解决。
- 严格扩展重放：11 张表通过，最大有限差 2.1316282072803006e-14。
- 主文 43 页，SI 107 页，摘要 247 词。

候选包、manifest 和验收记录：

- `dist/wrr_final_candidate_20261101_r2.zip`
- `dist/wrr_final_candidate_20261101_r2.manifest.json`
- `results/final_release_20261101_r2/acceptance.json`

包哈希、主文/SI 哈希、JUnit 哈希、测试计数和重放记录均在验收记录中；包内 README 不嵌入自身哈希。旧 `wrr_final_candidate_20261101.zip`（`2b0afcfe…468143a`）保留为历史候选。

## 仍未完成

作者姓名、单位、ORCID、基金、CRediT、利益冲突、LUBW 合法审稿访问、永久仓库/DOI 和编辑部受限数据例外仍需作者处理。本地 `acceptance.complete=true` 不替代这些事项。
