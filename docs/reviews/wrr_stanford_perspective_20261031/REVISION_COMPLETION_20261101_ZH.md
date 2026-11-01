# 2026-11-01 修正版完成与验收状态

本记录对应 `docs/reviews/wrr_plan_audit_20261101/REVIEW_AND_PLAN_ZH.md` 的复核意见。r2（`7ac1c2e0…c1d9feb`）保留为历史候选；本文件描述修正后的候选，不把旧通过记录当作新版本证据。

## 状态摘要

- W0、W2、W3 的核心修订保留；W1 的公式表述已修正；W4 的重放、清单、入口和局部测试已补强。
- 日期为 2026-11-01 的候选包为 `dist/wrr_final_candidate_20261101.zip`。包哈希、主文/SI 哈希、测试计数和验收范围以 `results/final_release_20261101/acceptance.json` 为准；包内 README 不嵌入自身哈希。
- 作者姓名、单位、基金、CRediT、利益冲突、LUBW 合法审稿访问和永久保存仍是作者外部事项，未在本记录中代填或声称完成。

## W1：子集 OLS 公式

已把 SI 定义改为对每个集合 \(A\in\{F,S\}\) 分别使用

\[
x_{A,y}=(y-\bar y_A)/10,\qquad
S_{xx,A}=\sum_{z\in A}x_{A,z}^{2},\qquad
w_{A,y}=
\begin{cases}
x_{A,y}/S_{xx,A}, & y\in A,\\
0, & y\notin A.
\end{cases}
\]

因此 \(d=w_S-w_F\) 在同一完整参考年份索引上满足 \(d^\top\mathbf{1}=0\)、\(d^\top x_F=0\)，并有

\[
S_{\mathrm{set}}=d^\top h=d^\top e,\qquad
d^\top d=\frac{1}{S_{xx,S}}-\frac{1}{S_{xx,F}}.
\]

新增测试覆盖：偏向序列一端的非对称选集、严格线性序列、常数平移、年份原点平移、权重差正交性、权重平方距离与方差系数一致性，以及旧“截断全体权重”反例。数值代码本来就在重新中心化，8,115 行结果未因公式修正而改变。

## W2：扩展重放比较器

`scripts/983_verify_extension_replay.py` 现在从包内 `table_spec.json` 读取 11 张科学表的主键、标签、数值列和合法缺失规则，逐表检查：

- 列集合与顺序；
- 主键存在、无缺失、无重复；
- 键集合完全一致；
- 非数值标签逐项一致；
- 合法 NaN 位置一致，非预期 NaN 和 Inf 拒绝；
- 有限数值使用 `rtol=0, atol=1e-12`；
- 每个文件的最终最大差必须有限。

新增 `tests/test_extension_replay_validator.py` 做故障注入：有限值加 \(10^{-6}\)、标签变化、有限值变 NaN、NaN 变有限值、重复键、缺失键、额外列、区间表变化、manifest 自哈希和旧哈希都必须被拒绝；结构性合法 NaN 必须通过。重放正常包时 11 张表全部通过，实际最大有限差由新比较器写入 `extension_replay.json`，不预设为旧值。

## W2/W3：清单、计数、容差与接口

- `data_manifest.json` 在科学表、`table_spec.json` 和 `scope.json` 写完之后生成；不再记录自身哈希；生成后立即校验所有声明输出。连续运行两次都验证 16 个输出哈希有效。
- 随机规则的符号不一致量拆为 `sign_disagreement_count` 与 `sign_disagreement_expected_count`。控制缺口期望值为 55.3519119769，经验日历为 8.2404761905；确定性规则的 3/5/4/0 不变。
- `table_spec.json` 记录 11 张表的粒度、单位、主键、合法 NaN 和输入/输出身份；983 读取同一规格，避免两套名单漂移。
- `np.isclose` 的算术检查统一写明 `rtol=0, atol=1e-12`，不再沿用默认相对容差。
- `981` 的 `--out` 与 `--paper` 已实际传递到所有写入函数；自定义目录测试验证论文片段、结果表和清单写入指定路径。紧凑输入回退使用 `--out`，不再读取全局目录。

## 前推/offline 范围

主文现在写明：前推分析的 \(Y_i\subseteq\{2010,\ldots,2025\}\)；offline 分析使用相应的历史完整参考年集合；“恢复全部支持年”指恢复 \(Y_i\) 内的受掩膜年份，不是补齐整个日历跨度。相关术语统一为 specified reference-year set。

## 测试与 CI

- 声明的最终发布测试：124 项通过，0 失败，0 错误，0 跳过。
- 全库测试：1,692 项，1,691 通过，0 失败，0 错误，1 跳过（本地 Python 3.11 环境）。
- CI 同命令 `ruff check --select E4,E7,E9,F src`：通过。此前 160 项已按意图修复；未使用变量在没有明确意图时删除，在承载文件大小/阈值校验意图时补上实际校验。
- 声明的证据步骤 `25_build_evidence_snapshot.py`、`26_audit_restricted_hosting.py`、`27_submission_gate.py --allow-no-go` 在 `PYTHONPATH=src` 下运行，最终为 `inventory_only`。这是本地等价检查，不是本次修订的远端 CI 运行。

## 仍待作者处理

- 真实作者、单位、ORCID、基金、CRediT、利益冲突和致谢；
- LUBW 及其他受限材料的合法审稿访问和再分发许可；
- 永久仓库保存、软件/数据 DOI 和可引用路径；
- 编辑部对受限数据例外的书面接受（如适用）。

这些事项不由本地验收记录代填，也不因 `acceptance.complete=true` 自动完成。
