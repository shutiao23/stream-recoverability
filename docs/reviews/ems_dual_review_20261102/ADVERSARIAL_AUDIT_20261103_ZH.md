# EMS 投稿前对抗式审计（第二轮）

- 日期：2026-11-03
- 对象：HEAD `ea161bb85d`。包括 EMS 投稿包、gapbench 1.2.0、wild cluster bootstrap、v1.2.0 发布记录，以及公开 GitHub 仓库的外观。
- 方法：只读审计加独立复算。复算脚本是 [adversarial_checks_20261103.py](adversarial_checks_20261103.py)，输出在 [adversarial_checks_20261103.json](adversarial_checks_20261103.json)。脚本只读取已保存的表，不修改任何论文、代码或结果。
- 实际运行的检查：
  - 从 GitHub 下载 release 资产，在全新的 Python 3.10 虚拟环境里安装，运行 quickstart 和测试。
  - 在本地运行与 EMS 相关的 28 个测试，以及 ruff 检查。
  - 用 `gh` 查询仓库、CI、许可证识别结果和 release。
  - 查询 PyPI 上的包名占用情况。
  - 读取 Elsevier 生成式 AI 政策的原文（2026 年 6 月版）。
- 视角：编辑初审、水文审稿人、统计/ML 审稿人、软件/可复现性审稿人、数据权利与研究诚信、写作与图件。这些审稿人视角都是模拟的，不代表任何真实学者的意见。

## 0. 结论速览

**完成度。** 你自己的台账结论是 "submission-shaped, not submission-ready"（[FINAL_STATUS_ZH.md](FINAL_STATUS_ZH.md) 第 7 节），这个判断是对的，而且实际情况比台账更差。本轮发现了 11 项此前没有识别的问题：

- 2 个统计实现 bug，错误结果已经写进 SI 和公开结果文件；
- 5 处方法描述与代码或数据不符；
- 若干公开仓库和元数据层面一眼可见的问题。

外部 P0（作者信息、LUBW、DOI）仍未关闭。

**现在投稿会怎样。**

- 编辑初审几乎肯定退回，原因有三：PDF 里还有 24 处方括号占位符，数据声明未定，封面信里直接写着"元数据未定"。
- 即使把占位符补齐，审稿人点开 GitHub 也会看到三件事：
  - 许可证显示 "Other"；
  - 最近 8 次 CI 运行全部失败；
  - README 写的是 WRR r4 候选包。

**最影响接受率的 10 件事，按性价比排序：**

1. 修复 2 个统计 bug 并重新报告结果，约 1 天：
   - wild bootstrap 的影响函数没有中心化；
   - Hamed–Rao 的方差修正写反了。
2. 改正方法描述，约 1 天：
   - 正文说"每年都缺测"，代码实际是每年以 0.35 的概率缺测；
   - 正文说缺口在"夏季、与峰值重叠"，实际有 23% 的缺口与 6–8 月完全不重叠；
   - "Mondrian CQR"的说法；
   - "counter-based RNG"的说法；
   - "框架由 gapbench 实现"的说法。
3. 整理仓库门面，约 1–2 天：LICENSE 只保留纯 MIT 文本、让 CI 变绿、把 README 改成 gapbench 和 EMS 论文的入口。
4. 补齐作者、单位、ORCID、资助、CRediT 信息。LUBW 问题有两种处理：改成"向数据提供方申请"的标准表述，或把开放源模型改为主分析。
5. Zenodo 只归档 gapbench，creators 填真名。归档必须放在许可证和受限数据核查之后。
6. 按 Elsevier 2026 年 6 月的 AI 政策，在 Methods 里如实说明 AI 辅助编码，并亲自重写由 AI 起草的段落，约 2–3 天。
7. 把 gapbench 补成真正的 benchmark，约 1–2 周：加上缺口生成器、评估框架、基线方法和 `annual_h30`。这是 EMS 软件贡献能否成立的关键。
8. 重构指标，约 1 天：
   - 只在"年集确实改变"的 288 个日历档案上报告结论；
   - 用"总趋势不确定性膨胀"补充或替代符号翻转数；
   - 说明 53 次翻转中有 43 次、16 次中有 16 次都发生在 |t|<1 的站。
9. 在主文说清 D2 与经典法之间可用性和精度的取舍，约半天。
10. 水文补强，约 1–2 周：补日流量、HydroATLAS 调节度、核电站停运核查，并把 heat-associated MNAR 情景从 6 站的试点扩大到 41 站。

另外有一个高价值的可选项：用观测下界 L_y 做删失似然趋势估计，作为"删年"和"重建"之外的第三选项，见第 5 节。

## 1. 你的工作完成了吗：逐项核验

| 台账声明 | 本轮核验 | 判定 |
|---|---|---|
| 805/818 两族的关键数字 | 从冻结表重算 RMSE、符号翻转、误差/SE，全部一致。35 个观测见证、20 个站、6 个站超出 0.5 °C，与 `witness_rules.csv` 一致 | 通过 |
| gapbench v1.2.0 release | 下载 release 资产，SHA-256 `29752080…` 与记录一致。在全新的 Python 3.10.12 venv 中安装、运行 quickstart、13/13 测试通过 | 通过，另有两个小问题，见 2.4 节 |
| 新增测试 | `test_ar1_bridge_nesting`、`test_wild_cluster_bootstrap`、`test_submission_admin_packets` 和 gapbench 测试共 28 个，全部通过 | 通过，但 wild bootstrap 测试的验收区间发现不了 bug，见 2.1 节 |
| B6 wild cluster bootstrap | 实现有 bug，修正后结论的措辞必须改 | **需要重做** |
| T1 趋势信号（含 Hamed–Rao） | Hamed–Rao 实现有 bug。主文和表 S2 没有用到它，但公开的 JSON/CSV 里有错误值 | **部分完成** |
| B7 随机数嵌套 | 代码和测试通过。正文仍写"counter-based"，仍保留关于旧采样器的半节说明 | 部分完成 |
| B8 计算成本 | 已实测。但 9.7 s / 289 MiB 是研究包的完整重放，不是 gapbench 本身，写在 gapbench 的 Hardware 字段里容易被误读 | 基本完成 |
| v1.2.0 tag 和 release | 已存在 | 完成，DOI 尚未生成 |
| 台账内部一致性 | 三处互相矛盾：[RESPONSE_ZH.md](RESPONSE_ZH.md) 第 8 节仍写 B6、B8 NOT DONE；[paper/ems/README.md:77](../../../paper/ems/README.md#L77) 仍写"没有 GitHub release 和 v1.2.0 tag"，第 99 行仍写 program size PENDING；FINAL_STATUS 第 3 节与第 8–9 节矛盾 | 需要同步 |
| 公开 CI | 最近 8 次运行全部失败。最近一次（10-31）失败在 `ruff check`，共 160 个错误。之后的提交都没有触发 CI。本地 ruff 0.16.2 已经通过 | **未完成** |
| 你已列出的未完成项 | 作者、LUBW、DOI；A3 流量、B4 基线、B5 多重插补、A5/A6/A8、锁定确认 | 未完成 |

## 2. 本轮新发现的硬伤

### 2.1 两个统计实现 bug

**(a) Wild cluster bootstrap 的影响函数没有中心化**

位置：[scripts/986_wild_cluster_bootstrap.py:51](../../../scripts/986_wild_cluster_bootstrap.py#L51)。

RMSE_A − RMSE_B 的影响函数应该是 ½(a_i/RMSE_A − b_i/RMSE_B) − ½·estimate。代码减去的是整个 estimate，所以影响值的均值变成了 −estimate/2，而不是 0。以受控族全保留对比为例，均值是 +0.138。

在 Rademacher 权重下，这个常数项会进入抽样方差，所以估计值越大，区间被额外加宽得越多。修正后的结果如下：

| 指标 | 现稿 / 表 S12 | 修正后 |
|---|---|---|
| wild 与群组重抽样的区间宽度比（中位数） | 1.02 | **0.88** |
| 受控族，全保留 − warm90 | [−0.384, −0.169]，宽 0.215 | [−0.353, −0.200]，宽 0.153 |
| 日历族，全保留 − warm90 | [−0.072, −0.021] | [−0.064, −0.029] |
| 结论依赖方法的对比个数 | 正文说"只有一个"：日历族 D2 − 经典法 | **两个**：日历族 D2 − 经典法，以及日历族 uniform_exact − warm90 |

关于 uniform_exact 这一项：在你现有的保存结果里，它的 wild 区间 [0.0032, 0.0406] 已经不含 0，而群组重抽样区间 [−0.0036, 0.0369] 含 0。也就是说，正文原本就漏报了一个依赖方法的对比。

所有主要方向结论都不变，但需要做三处修改：

- [body.tex:57](../../../paper/ems/body.tex#L57) 中 "median wild-to-resampled width ratio of 1.02" 和 "the one method-dependent comparison" 两处要改；
- 表 S12 要重新生成；
- 测试 [tests/test_wild_cluster_bootstrap.py:60](../../../tests/test_wild_cluster_bootstrap.py#L60) 要改。它的验收条件是 `0.88 <= coverage <= 1.0`，会接受过宽的区间，所以发现不了这个 bug。建议：
  - 增加"影响函数均值为 0"的断言；
  - 把覆盖率窗口收紧到名义值附近，例如 0.92–0.98；
  - 同时增加模拟次数。

另外，群组只有 17 个，而且非常不均衡（瑞士只有 2 组）。在这种情况下，不施加零假设的 wild 百分位区间本身就没有覆盖保证。如果要写进正文，有两个选择：

- 更准确地改称 score bootstrap on the linearized statistic（Kline & Santos, 2012）；
- 或者改用 CR2/Bell–McCaffrey 方差，配合 t(G−1) 临界值。

**(b) Hamed–Rao 方差修正写反**

位置：[slope_signal_audit.py:101-107](slope_signal_audit.py#L101-L107)。

Hamed & Rao (1998) 的修正因子是

n/n\* = 1 + 2/[n(n−1)(n−2)] · Σ(n−k)(n−k−1)(n−k−2)ρ_k

修正后的方差是 Var\*(S) = Var(S)·(n/n\*)。脚本把这个因子命名为 `n_star`，然后计算 `var_s * n / n_star`，结果等于 Var(S)·n\*。这样一来，方差比未修正的值放大了约 n/(n/n\*) 倍：当 n=14、修正因子约 0.8 时，放大约 18 倍。

此外还有两处偏离原方法：

- 求秩之前没有先用 Sen 斜率去趋势；
- 没有只保留显著的滞后项。

结果对比：

- 保存的结果是 0/41 个站显著，"n\*"的中位数是 0.79。有效样本量小于 1，一眼就能看出不合理。
- 按原方法计算（先去趋势，只保留 5% 显著的滞后），8/41 个站 p<0.05，另有 1 个站的修正因子 ≤0，无法计算。不过 n=14 时滞后自相关的估计本身就很不稳定，这个结果也不可靠。

主文和表 S2 没有引用 Hamed–Rao 的数值，这一点是对的。但公开的 `results/ems_revision_20261102/trend_signal.{json,csv}` 里含有错误值。

建议二选一：直接改用 pyMannKendall（Hussain & Mahmud, 2019, JOSS）的 `hamed_rao_modification_test`，或者删掉这两列。正文继续保留"n≈14 时自相关修正不稳定"的表述即可。

### 2.2 方法描述与代码或数据不符

审稿人只要对照代码，就会发现以下问题。

| 位置 | 稿件的说法 | 代码或数据的事实 | 怎么改 |
|---|---|---|---|
| [body.tex:21](../../../paper/ems/body.tex#L21) | 每个档案 "receives a contiguous mask in every year of the analysis window" | [scripts/521_whole_archive.py:184](../../../scripts/521_whole_archive.py#L184) 中，每年以 0.35 的概率缺测，前 7 年不缺测，前推模式只从 2010 年开始。805 个档案中，有缺口的年份占比中位数为 36%，没有任何一个档案所有年份都缺测 | 把 0.35、7 年预热期和 2010 年起点如实写出来 |
| [body.tex:121](../../../paper/ems/body.tex#L121)、摘要 | 受控缺口 "overlap of at least half the training-period climatological peak"；摘要写 "30–90-day summer gaps" | 805 个档案共 3,711 段缺口。其中 23.4% 与 6–8 月完全不重叠，21.1% 在第 120 天之前就开始（例如从第 26、32、53 天开始） | 先核查掩膜池里是否混入了 none 或 partial overlap 类，然后二选一：改写文字，或只用与峰值重叠的子集重算 |
| [body.tex:55](../../../paper/ems/body.tex#L55)、[:185](../../../paper/ems/body.tex#L185) | "D2 is a Mondrian CQR" | [scripts/466_review_completion_refit.py:136-145](../../../scripts/466_review_completion_refit.py#L136-L145) 的实际做法：按 difficulty 类别对每个分位数做经验平移；类别少于 50 例时回退到全池；没有 (1+1/n) 的有限样本修正；按权重复制行。正文里的 "group" 在这里指 difficulty 类别，不是 connected group | 改写为 per-quantile split recalibration stratified by difficulty class, analogous to Mondrian CQR but without its finite-sample guarantee |
| [body.tex:77](../../../paper/ems/body.tex#L77) | pathwise 采样器 "designed around addressable counter-based random streams" | 实际实现是 `SeedSequence(seed).spawn()` 加 `default_rng`，生成器是 PCG64，不是 counter-based | 改为 per-path spawned streams，或者真的换成 `np.random.Philox` |
| [abstract.tex](../../../paper/ems/abstract.tex)、[CITATION.cff:15](../../../CITATION.cff#L15) | 摘要："The framework, implemented as open-source gapbench 1.2.0, separates … Monte Carlo errors"。CITATION.cff 声称提供 joint archive-level gap masks、annual recovery 和 command-line examples | gapbench 没有 Monte Carlo，没有年度重建，没有联合掩膜生成器，也没有命令行工具，只有 6 个原语函数 | 要么改写描述，要么按 3.4 节补齐功能 |

### 2.3 稿件内部会被抓住的问题

1. **流量对照表其实是另一个变量。** [open_source_flow.tex:7-30](../../../paper/ems/open_source_flow.tex#L7) 和表 `tab:ems_flow_comparators` 报告的是 255 个 USGS 站年流量的重建 MAE。指标单位是 log-flow，年份按 4 月到次年 3 月的水文年划分，方法是 MOVE.1 等，与河温 H30 无关。这张表放在"流量代理诊断"一节里，读者会以为是河温结果。
   - 建议删除。
   - 如果想展示框架的通用性，可以在 SI 单列一节"把同一基准用于流量"，并写清目标量是什么。
2. **"offline"没有定义。** Fig. 4（`03_archive_factorial`）左栏有 Cal. offline 和 Ctrl. offline 两组，但正文从来没有出现过 offline 设计。要么定义它，要么重画图，只保留 forward。
3. **"三输出发布规则"一段出现了两次，而且全文都没有定义它。** 见 [body.tex:191](../../../paper/ems/body.tex#L191) 和 [:207](../../../paper/ems/body.tex#L207)，段中还写着 "not in this Supporting Information"。EMS 读者没有看过 WRR 版本，这两段都应整段删除。
4. **符号冲突。**
   - S 同时表示"所选年集"和"年集误差"，见 [body.tex:63-65](../../../paper/ems/body.tex#L63-L65)。
   - Y_i 表示参考年集，Y_{yd} 表示日水温（[:109](../../../paper/ems/body.tex#L109)），两者冲突。
   - 公式中的 h 和 e 没有定义。
5. **同一个方法有三个名字**：classical comparator、calibrated stochastic regression、stochastic comparator。应统一成一个名字，并在第一次出现时定义。
6. **D2 的定位没有讲清。**
   - 在共同案例上，经典法的趋势 RMSE 更低：受控族 0.147 对 0.164。差值的区间在群组重抽样下是 [0.004, 0.027]，用 wild bootstrap 也同样不含 0。
   - 但经典法在 82/820 个受控档案和 119/820 个日历档案上无法给出估计。这些档案也更难：D2 在其上的 RMSE 分别是 0.244 和 0.093。
   - 这是可用性与精度之间的合理取舍，但正文只在开放源敏感性分析里顺带提了一句"0.164/0.147"。审稿人一定会问"为什么主推一个更差的复杂模型"。应在主文里讲清楚，并写进决策表。
7. **Fig. 1 还在用 WRR 的术语**："release tests"、"numerical release, bound or unknown"、"release-then-trend working likelihood"。这些在 EMS 正文里都没有定义。
8. **内部用语漏进了正文**："local review candidate"（[body.tex:203](../../../paper/ems/body.tex#L203)），以及 "no new experiment is introduced by the comparison"（[:15](../../../paper/ems/body.tex#L15)）。

### 2.4 公开仓库与元数据的可见问题

| 问题 | 证据 | 怎么改 |
|---|---|---|
| GitHub 把许可证识别为 "Other" | `gh repo view` 返回 `licenseInfo=other`。[LICENSE](../../../LICENSE) 前 19 行是关于数据的说明 | LICENSE 只保留 MIT 原文，数据说明移到 NOTICE 或 DATA_RIGHTS.md |
| LICENSE 自己写着"公开仓库里有受限列，清理是后续工作" | [LICENSE:12-18](../../../LICENSE#L12-L18) | 我抽查了数据权利登记表中 25 项不可再分发、7 项受限的文件，它们既没有被 git 跟踪，也不在提交历史里。如果确认没有受限内容，就删掉这句话；如果有，先清理再归档 |
| CI 全红 | 最近 8 次运行全部失败。最近一次（10-31）失败在 [ci.yml:66](../../../.github/workflows/ci.yml#L66) 的 ruff 步骤，共 160 个错误。之后的提交都没有运行 CI，而本地 ruff 已经通过 | 增加 `workflow_dispatch` 触发；固定 ruff 版本；在投稿用的 commit 上跑通 CI；另加一个只测 gapbench 的快速 job（Python 3.10–3.13），并在 README 放徽章 |
| README 是 WRR r4 候选包的说明 | [README.md](../../../README.md) 开头写着 "r4 is uncommitted" 和 WRR minor revision | 改成 gapbench 和 EMS 论文的入口，WRR 的历史移到 `docs/history` |
| 仓库有 1.6 GB | `gh repo view` 返回的 diskUsage | 审稿人只需要 gapbench，建议把它拆成独立的轻量仓库 |
| gapbench 声明了 pandas 依赖但从未使用 | [gapbench/pyproject.toml:14](../../../gapbench/pyproject.toml#L14)；源码里没有任何 pandas 导入 | 删掉这个依赖，或者把它用在日期感知的 API 上 |
| release 的 zip 包不规范 | 包含 `.pytest_cache`；没有顶层目录；`license = {text=...}` 的写法会触发 setuptools 弃用警告 | 改用 `python -m build` 生成 sdist 和 wheel 再上传 |
| Docker 的说法未经验证 | 本机没有 docker 权限，镜像从未构建过。镜像安装 `.[review,dev]`，而根包的核心依赖就包括 torch 和 xgboost，只为运行一个只需要 numpy 的 quickstart | 在 CI 里构建并运行一次；或者把 "Docker smoke environment" 从正文和封面信里删掉 |
| 软件可用性声明缺少"开发者联系方式" | [software_availability.tex:6](../../../paper/ems/software_availability.tex#L6) | 这是 EMS 软件可用性要求的字段之一 |
| quickstart 的演示有误导 | [quickstart.py:50](../../../gapbench/examples/quickstart.py#L50) 对整段 20 年序列求最大窗口，结果落在完整年 2018，而不是"某个不完整年的观测下界" | 改成对每个不完整年计算 L_y 并与真值对比，这样正好演示 RQ1 |
| PyPI 包名 | `gapbench` 在 PyPI 上还没被占用；但 GitHub 上已有 gap-packages/gapbench（GAP 计算机代数系统的基准） | 尽快发布到 PyPI 占住名字，或者换一个更具体的名字 |

## 3. 多角度对抗式审核

### 3.1 编辑初审

- **必然退回的项：**
  - 24 处方括号占位符，另有一句 Funding 模板句；
  - 封面信第 17–19 行写着 "marks unresolved author, funding, CRediT, and legal metadata"；
  - 正文中出现 [EDITORIAL/LEGAL CONFIRMATION REQUIRED]。
- **期刊适配度。** EMS 期待的是可复用的方法或软件。现在的"框架"只在研究包里实现，gapbench 只有原语函数。编辑会问："读者用 gapbench 能复现你的基准吗？"目前的答案是不能。
- **封面信。** 不要在封面信里罗列弱点，例如锁定确认、LUBW、元数据，这些放进 Limitations。封面信只讲期刊适配、新意和可用性。
- **DOI。** 摘要写着 "archival DOI pending"。投稿时最好已经有 DOI。

### 3.2 水文审稿人（模拟，关注水热过程和区域机理）

1. **短记录有没有意义。**
   - 参考年数的中位数是 14 年，41 个站中只有 3 个站 |t|≥2。审稿人会问：14 年的 H30 斜率有管理上的意义吗？
   - 引言应说明使用场景，例如监测网年报、短记录站点的评估。
   - 讨论中应给出"记录多长时，缺测处理开始变得重要"的估计。可以用 iid 公式 Var(S)=σ²(1/Sxx_S − 1/Sxx_F) 外推。
2. **符号翻转。** 受控族 warm90 的 53 次翻转中有 43 次、全保留的 16 次中有 16 次，都发生在 |β|<1 SE 的站上，也就是真值符号本身就不确定的站。3 个 |t|≥2 的站一次翻转都没有。应改为报告"|t|≥1 的站上的翻转"或"显著性判断的改变"，否则会被认为是在夸大问题。
3. **更直观的实际意义指标。** 把缺测处理带来的误差看成叠加在趋势抽样误差上的额外方差，总不确定性的膨胀为 sqrt(1 + mean((e/SE)²)) − 1。结果是：
   - 受控族：筛选 21.5%，重建 3.7%；
   - 日历族：筛选 1.8%，重建 0.5%。

   这比"误差等于中位斜率的 59.1%"直观，也直接支撑第 4 条 highlight。
4. **日历族的结论应只在年集确实改变的档案上报告。**
   - 818 个日历档案中，有 530 个在筛选和全保留两种方案下年集完全相同，这稀释了 RMSE。
   - 只看年集改变的 288 个档案：
     - 筛选：RMSE 0.191，|e|/SE 中位数 0.151，P90 0.559；
     - 全保留：RMSE 0.112，|e|/SE 中位数 0.026，P90 0.225。

     结论仍然成立，而且这样报告更诚实。
   - 另外，瑞士 200 个日历档案的误差全部为 0，因为实际缺口都很短。所以日历族的结论其实来自巴伐利亚和 USGS 的站点，正文应该说明。
5. **流量与调节（A3/A4）仍然是最大的缺口。** 最低限度可以做三件事：
   - 补 FOEN 和 GKD 34 个站的日流量，数据都是公开的。
   - 把站点挂到 HydroRIVERS/RiverATLAS 上，提取调节度（DOR）、湖泊比例、上游面积和高程。你已经引用了 HydroATLAS（linke2019），审稿人会追问为什么不用。
   - 核查巴伐利亚各站与几座核电站的上下游关系：Isar 1（2011 年停运）、Grafenrheinfeld（2015 年）、Gundremmingen B 和 C（2017 年和 2021 年）。评估期 2010–2025 正好覆盖这些热排放变化，而训练期在 2010 年之前，所以这是 air-ridge 失效的一个强候选解释。停运年份请自行核实。
6. **缺测机制（A8）：仓库里其实已经有素材。**
   - 已经实现了 heat-associated MNAR 情景：热年缺测概率 0.90，其他年份 0.18，见 [521_whole_archive.py:201](../../../scripts/521_whole_archive.py#L201)。但目前只有 6 个站的试点。
   - 扩大到 41 个站后，可以直接回答引言里"长缺口不是随机的"这一论点：在信息性缺测下，筛选带来的是系统性偏差，而不只是方差。这比随机 0.35 掩膜更有水文说服力。
   - USGS 零流量 logit 的结果也属于 MNAR 证据：在有零流量记录的 21 个站里，夏季对数流量每升高 1 个标准差，暖季缺测的 odds 降为 0.59；常流河子集中这一比值为 0.97，不显著。这个结果应该用作研究动机，而不是埋在"诊断"一节里。
7. **气象强迫（A5）。** NASA POWER 的分辨率是 0.5°×0.625°。至少应报告格点与站点之间的高程差，并用 E-OBS 或 DWD/MeteoSwiss 的站点气温做一次替换敏感性分析。

### 3.3 统计/ML 审稿人

1. 两个统计实现 bug，见 2.1 节。
2. **"Mondrian CQR"的说法，见 2.2 节。** D2 的区间并没有共形覆盖保证，原因有四：
   - 校准行重复使用；
   - 按权重复制行；
   - 站与站之间相关；
   - 没有有限样本修正。

   正文应把它当作经验校准来写，不要写成共形保证。
3. **20 条路径的区间系统性偏窄。** 用 20 条路径时，5% 和 95% 分位数实际上就是第 1 和第 20 个次序统计量，区间会系统性偏窄。路径从 20 条增加到 500 条时，区间宽度增加 15.9%，正是这个效应。建议的修改顺序：
   - 用 pathwise 采样器把 27 例的预算实验重跑一遍，耗时只有几分钟；
   - 报告 Monte Carlo 标准误；
   - 把 Fig. 7 移到 SI；
   - 删掉关于 native 和 nested 采样的那半节。
4. **年度精度与趋势精度不一致。** 两种方法的年度点误差几乎一样（MAE 0.337 对 0.336），但经典法的趋势 RMSE 更低。正文应解释原因，候选解释包括误差的年际相关性和对端点年份的敏感性。
5. **多重插补和现代基线（B4/B5）。** 最低限度：在一个子集（例如 2 个群组）上跑一次 SAITS（PyPOTS 已经在依赖里）和一次状态空间 Kalman 平滑，报告下游的 H30 和趋势误差。不必全量运行，但需要有一个对照点。
6. **同一批站被反复分析。** 如果做不了锁定确认，至少在正文给出分析决策的时间线，或者事先说明哪些结果是确认性的、哪些是探索性的。

### 3.4 软件/可复现性审稿人

1. **最核心的问题：gapbench 叫 benchmark，却没有 benchmark。** 缺少以下几部分：
   - `annual_h30(series_with_dates)`：需要能识别日期，处理闰年和缺失日，并同时返回 L_y 和"是否完整年"的标记。这是论文最核心的量，现在只在 quickstart 里手写了一遍。
   - 缺口生成器：包括受控缺口（长度 × 峰值重叠 × 年缺测概率 × 预热期）和经验日历的迁移。
   - 评估框架：`run_benchmark(daily, reconstructor, design)`，返回年度误差、趋势误差和 S/R/E 分解，其中 reconstructor 是用户传入的可调用对象。
   - 2–3 个基线重建方法：气候态、气温回归、pathwise AR(1) 桥。
   - 可选：删失似然趋势估计，见第 5 节。

   做到这些，"读者能用 gapbench 复现论文的基准设计，并评估自己的方法"这句话才成立。
2. **`group_splits` 的问题。** 它与 sklearn 的 `GroupKFold` 功能重复，而且不是论文实际使用的 0.55/0.15/0.15/0.15 角色划分。要么实现这种角色划分，要么在文档里说明两者的差异。
3. **发布与工程规范。**
   - 发布到 PyPI；
   - 建文档站（mkdocs 或 sphinx，含 API 参考）；
   - 补 CHANGELOG、项目 URL、分类器和 `py.typed`；
   - CI 矩阵覆盖 Python 3.10–3.13 和 Linux/macOS/Windows；
   - 增加基于属性的测试，例如：S+R=E 对任意随机输入都成立；选年函数的结果不随温度改变。
4. **研究包的可复现性。** 至少提供一条命令（例如 `make ems-tables`），能从保存的 CSV 重建 EMS 的全部表和图，并在 CI 里运行。
5. Docker 的问题见 2.4 节。

### 3.5 数据权利与研究诚信

1. **Elsevier 的 AI 政策（2026 年 6 月更新）。**
   - **政策要点：**
     - 写作中允许：整理结构、改善作者自己所写文字的清晰度、对照投稿指南做检查。
     - 不允许："Generating sections of a manuscript without genuine intellectual contribution from the author"。
     - 研究过程中使用 AI（包括 AI 辅助编码），需要在 Methods 中详细描述。
     - AI 声明放在参考文献的正上方。
   - **本项目的现状：**
     - 292 个提交中有 56 个带 Cursor 共同署名；
     - 根据 PLAN 的 T3 任务，EMS 正文由子 agent 起草；
     - 声明只写了 "language editing" 和 "including Cursor"；
     - Methods 中没有任何关于 AI 辅助编码的说明；
     - 声明后面还隔着一节 Software availability，没有放在参考文献正上方。
   - **建议：**
     - 在 Methods 中加一段，说明哪些代码由 AI 工具辅助编写，以及如何验证（测试数量、独立复算、冻结文件的哈希）；
     - 在声明中如实列出所有用到的工具和用途；
     - 最重要的一条：亲自重写引言、讨论和结论，确保自己能当面为每一个论断辩护。
   - **图件：**
     - 解释性示意图（Fig. 1、图形摘要）如果是用 AI 写的代码绘制的，政策要求在图注中披露；
     - 图形摘要不能用通用的生成式图像工具来做。你的图形摘要是用脚本绘制的，属于允许的范围，但仍需披露。
2. **LUBW 最省力的出路。**
   - 把开放源的 candidate-provider 模型定为主分析，LUBW 版本降为敏感性分析。在开放源模型下结论不变：D2/经典法的趋势 RMSE 为 0.158/0.156，保留率 93.7%，覆盖率 87.6%。
   - 这样主结果就不依赖受限数据，数据声明可以写成标准表述："LUBW 数据可按其 UIS 使用协议向 LUBW 申请"。正文里的两处 [EDITORIAL/LEGAL CONFIRMATION REQUIRED] 就可以删掉。
   - 代价是需要用开放源模型把 805 和 818 两族的主表重跑一遍。
3. **归档顺序。**
   - 先修好 LICENSE、核查完受限内容，再生成 DOI。Zenodo 记录一旦发布，里面的文件就无法撤回。
   - 不要对整个 1.6 GB 的仓库开启 Zenodo–GitHub 集成，只对 gapbench 单独归档。
   - creators 要用真名加 ORCID。目前 `.zenodo.json` 和 `CITATION.cff` 里的作者都只有别名 shutiao23。
4. **重复投稿核查。**
   - 我在仓库里没有找到真实的 WRR 稿号，docs 里的 WRR 审稿意见看起来都是模拟的。
   - 请自行确认 WRR 版本从未投出，或者已经正式撤稿，因为 EMS 封面信写的是 "not under consideration elsewhere"。
   - 公开 README 中 "WRR minor revision" 一类的措辞会让审稿人误以为在并行投稿，应当删除。
5. **DATA_RIGHTS.md 的审稿访问路径。** 登记表 `metadata/data_rights.csv` 的审稿访问路径一栏仍写着 AGU/GEMS（`agu_gems_confidential...`），这对 EMS 不适用，需要改。

### 3.6 写作与图件

1. **否定句太多。** 正文约 6,800 词、319 句，其中 99 句含 "not"，占 31%；"not a" 出现了 25 次。很多句子是在回应历次模拟审稿的意见。建议每个限定条件只在 Limitations 里说一次，结果段直接陈述发现。
2. **数字重复。** 0.446 出现 7 次，"53 次翻转"出现 8 次，67.9% 出现 4 次，分布在摘要、结果、讨论、结论和决策表中。结论段可以不再重复这些数字。
3. **图件建议。** 仍可保持 7 张图，但换掉部分内容：
   - 新 Fig. 1：画出基准流程，并标明每一步由 gapbench 的哪个函数完成。
   - 研究区图：加上河网、湖泊、水库和核电站，按调节度着色，并标出 air-ridge 失效的站。
   - 新增一张实例图：一个真实的站年，包括日序列、缺口、L_y、重建值及其区间、真值。这是 EMS 读者最容易理解的图。
   - 主结果图：画 |e|/SE 的 ECDF，按族 × 方案分组，并标出 1 SE 线。
   - Fig. 6（区域恢复）：加上 90% 名义覆盖线、聚类 bootstrap 误差棒和样本数 n。
   - Fig. 7（预算）移到 SI。
   - Fig. 4：去掉 offline 组，或者在正文定义 offline。

## 4. 路线图

**P0：投稿前必须完成。** 共约 1–2 周，其中部分事项依赖外部。

| # | 事项 | 工作量 |
|---|---|---|
| P0-1 | 修复 wild bootstrap 和 Hamed–Rao；重新生成表 S12 和 trend_signal 结果；修改 body.tex:57 | 1 天 |
| P0-2 | 改正 2.2 节的 5 处描述，包括摘要中的"summer"措辞和 CITATION.cff 的摘要 | 1 天 |
| P0-3 | 按 2.3 节清理正文：删除流量对照表；删除重复的发布规则段落；定义 offline 或从图中去掉；统一术语和符号；讲清 D2 的取舍 | 1–2 天 |
| P0-4 | 整理仓库门面：纯 MIT 的 LICENSE、CI 变绿、改写 README、release 改用 build 生成的包 | 1–2 天 |
| P0-5 | 补齐作者、单位、ORCID、资助、CRediT、利益冲突声明；删除全部 24 处占位符；重写封面信 | 依赖外部 |
| P0-6 | LUBW：把开放源模型改为主分析，或使用标准的申请表述；DATA_RIGHTS 改为 EMS 适用的访问路径 | 依赖外部；如需重跑，另需 2–5 天 |
| P0-7 | Zenodo：单独归档 gapbench，creators 填真名；回填 DOI 到稿件和 CITATION.cff | 半天，另需外部操作 |
| P0-8 | AI 披露：在 Methods 中补充说明；把声明移到参考文献正上方；亲自重写由 AI 起草的段落 | 2–3 天 |
| P0-9 | 软件可用性声明：补开发者联系方式；quickstart 的命令与 release zip 的结构保持一致；Docker 要么删掉，要么验证 | 半天 |
| P0-10 | 同步内部台账：RESPONSE_ZH 第 8 节、paper/ems/README、FINAL_STATUS | 半天 |

**P1：能显著提高接受率。** 共约 3–5 周。

| # | 事项 | 工作量 |
|---|---|---|
| P1-1 | 按 3.4 节把 gapbench 补成真正的 benchmark，并完成 PyPI 发布、文档和 CI 矩阵 | 1–2 周 |
| P1-2 | 重构指标：在年集改变的档案上报告、报告不确定性膨胀、符号翻转按 \|t\| 分层 | 1 天 |
| P1-3 | 补流量、HydroATLAS 属性和核电站核查，并据此对 air-ridge 失效做分层分析 | 1 周 |
| P1-4 | 把 heat-associated MNAR 情景扩大到 41 个站 | 计算需数天 |
| P1-5 | 用 pathwise 采样器重跑 27 例预算实验，报告 Monte Carlo 标准误；Fig. 7 移到 SI | 1–2 天 |
| P1-6 | 在一个子集上与现代基线做对照（SAITS 和 Kalman 平滑） | 3–5 天 |
| P1-7 | 按 3.6 节重做图件，并在全文去掉防御性写法 | 1 周 |
| P1-8 | 在 SI 中补 D2 的 model card 和 Kapoor–Narayanan 泄漏核查表，各 1 页 | 1 天 |

**P2：锦上添花。**

- 用 E-OBS 或 DWD 的气温替换强迫数据；
- 历史记录长度和邻站数量的消融实验；
- OSF 预登记，加上新站点的一次性确认；
- Snakemake 工作流；
- 删失似然趋势估计（如果 P1 阶段时间不够）。

## 5. 一个值得考虑的叙事升级：删失似然作为第三选项

现在 RQ1 和 RQ2 是分开的：

- RQ1 证明了不完整年份中的观测窗口是一个事实下界，即 H30_y ≥ L_y；
- RQ2 比较的是"删年"与"重建"。

可以把两者连起来：把 L_y 当作右删失观测，也就是真值 ≥ L_y，再用 Tobit 型线性趋势似然来估计斜率。

- **似然的构成。** 完整年贡献正态密度；不完整年贡献 P(H30_y ≥ L_y) = 1 − Φ((L_y − a − b·x_y)/σ)。
- **好处一：不需要任何重建模型。** 因此不依赖 LUBW 训练数据，也不受 air-ridge 失效的影响。
- **好处二：水文审稿人熟悉这个思路。** 洪水频率分析处理历史年最大值和删失年最大值时用的是同一思路，例如 Bulletin 17C 和 Expected Moments Algorithm。
- **好处三：把两个问题串起来。** 在 805 和 818 两族掩膜上把它与"删年"和"重建"并列比较，RQ1 和 RQ2 就连成了一条线。标题也可以改成 "Discard, bound, or reconstruct?"。

需要注意的前提：如果缺口与高温相关（MNAR），删失发生的位置本身就带有信息，似然需要相应的假设。这一点可以在 P1-4 的 MNAR 情景下直接检验。

## 6. 做得好的地方（不要动）

- 数字可追溯：本轮抽查的数字全部一致，r4 冻结件没有被改动。
- 局限性写得诚实；决策表的思路正确；以斜率标准误为尺度衡量误差的思路正确。
- release 资产在干净的 Python 3.10 环境里可以安装、可以测试。
- 参考文献经过逐条核验，hare2021 已对照全文核实。
- `ar1_bridge_pathwise` 的实现和嵌套测试都是对的。

## 附录 A：复算与核查命令

```bash
# 重算本报告引用的全部数字（只读保存表）
python docs/reviews/ems_dual_review_20261102/adversarial_checks_20261103.py

# release 资产的干净安装（在任意空目录中运行）
gh release download v1.2.0 -R shutiao23/stream-recoverability -p 'gapbench-1.2.0.zip'
sha256sum gapbench-1.2.0.zip   # 29752080915f3a536797a596528cccc82621bbfccd2c53457bcd70c078178e87
unzip -q gapbench-1.2.0.zip -d src && python3.10 -m venv venv
venv/bin/pip install "./src[test]" && venv/bin/python src/examples/quickstart.py
(cd src && ../venv/bin/python -m pytest -q tests)   # 13 passed

# 公开仓库外观
gh repo view shutiao23/stream-recoverability --json licenseInfo,diskUsage,visibility
gh run list -R shutiao23/stream-recoverability -L 8
```

## 附录 B：来源

- Elsevier, Generative AI policies for journals（读取于 2026-11-03，页面标注 "Policy updated June 2026"）：https://www.elsevier.com/about/policies-and-standards/generative-ai-policies-for-journals
- EMS 期刊页面：https://shop.elsevier.com/journals/environmental-modelling-and-software/1364-8152
- EMS 旧版作者指南的转载（其中写明摘要 ≤200 词，以及软件可用性所需的字段）：https://gzw.lib.whu.edu.cn/ensci/show.asp?id=13949 。这是旧版本，以 Elsevier 官网当前的 Guide for Authors 为准。
- Hamed, K.H., Rao, A.R. (1998). A modified Mann-Kendall trend test for autocorrelated data. Journal of Hydrology 204, 182–196.
- Hussain, M.M., Mahmud, I. (2019). pyMannKendall: a python package for non parametric Mann Kendall family of trend tests. Journal of Open Source Software 4(39), 1556.
- Kline, P., Santos, A. (2012). A score based approach to wild bootstrap inference. Journal of Econometric Methods 1(1), 23–41.
- England, J.F. Jr. et al. (2019). Guidelines for determining flood flow frequency—Bulletin 17C. USGS Techniques and Methods 4-B5.
