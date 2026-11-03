# EMS 双审稿修订：T6/T8 独立审计与逐条回应

日期：2026-11-02（T8 最终整合审计更新，UTC）  
审计对象：`paper/ems/`（含 `supporting_information.tex`、`si_tables/S1..S11`）、`gapbench/`、`docs/software/`、`tests/test_ar1_bridge_nesting.py`、`results/ems_revision_20261102/`、`results/final_release_20261101_r4/`、`results/wrr_final_revision_20261031/`。  
审计边界：只更新本文件、`PLAN_ZH.md` 并新增 `FINAL_STATUS_ZH.md`；未修改论文、代码、bib、测试、科学 CSV、元数据或 r4 冻结件。  
审计结论：**EMS 包已具备投稿形态，但尚不是 submission-ready。** SI 已建立并通过编译/引用核对；剩余阻塞是外部 P0（作者/法律/DOI/审稿访问）和缺失实验，以及若干非阻断的 SI 来源标注 WARN。第 8 节的 T8 状态覆盖第 7 节的 T6 历史状态。

## 1. 构建与 PDF 审计

### 1.1 精确命令与结果

T8 在 `/tmp/ems_clean/paper/ems` 的隔离副本中重建（`paper/wrr_tr` 以只读 symlink 提供图件），以免改写交付目录。主文与 SI 均从干净状态开始：

```bash
cd /tmp/ems_clean/paper/ems
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
# exit 0；Output written on main.pdf (37 pages, 734012 bytes)

bibtex main
# exit 0；Warning--empty pages in angelopoulos2024（唯一 BibTeX warning）

latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
# exit 0；37 pages；main.log 中 0 Warning / 0 Overfull / 0 Underfull / 0 undefined

latexmk -pdf -interaction=nonstopmode -halt-on-error supporting_information.tex
# exit 0；Output written on supporting_information.pdf (13 pages, 302377 bytes)
# supporting_information.log 中 0 Warning / 0 Overfull / 0 Underfull / 0 undefined
```

`bibtex` 唯一告警是 `angelopoulos2024` 缺页码（ICLR 不编页码，属预期）。`main.bbl` 含 52 个 `\bibitem`。磁盘上的 `paper/ems/main.pdf`（37 页，734012 bytes）与 `supporting_information.pdf`（13 页，302377 bytes）与重建页数、文本内容一致；字节哈希因 PDF 构建元数据不同而不同。

### 1.2 PDF 文本检查

```bash
pdftotext main.pdf /tmp/ems_main.txt
grep -o '??' /tmp/ems_main.txt | wc -l          # 0
grep -o '(author?)' /tmp/ems_main.txt | wc -l   # 0
```

| 检查项 | 结果 |
|---|---:|
| 主文页数 | 37 |
| SI 页数 | 13 |
| 图 | 7（Figure 1–7） |
| 表 | 4（Table 1–4） |
| SI 表 | 11（Table S1–S11） |
| 参考文献 | 52（`main.bbl` 中 52 个 `\bibitem`） |
| Highlights | 5 条 |
| 摘要词数（源文件 / PDF 文本） | 185 / 185 |
| Highlights 字符数（含空格，`--` 按 1 字符） | 76 / 76 / 79 / 80 / 83，均 ≤85 |
| `??` | 0 |
| `(author?)` | 0 |
| Overfull / Underfull | 0 / 0 |
| undefined citation / reference | 0 / 0 |
| `Water Resources Research` | 0 |
| `Key Points` | 0 |
| `Plain Language Summary` | 0 |
| `contact the authors` | 0 |
| `available on request` / `available upon request` | 0 / 0 |
| `agujournal` | 0 |

`AGU` 大小写不敏感只命中参考文献作者名 `Agustí-Panareda`，不是 AGU 期刊身份。PDF 首页是 `elsarticle` 的 Highlights/标题/摘要，未出现 WRR 标题、Key Points 或 PLS。

### 1.3 仍可见的占位符

PDF 文本中共 26 处占位符：18 处 `[AUTHOR TO CONFIRM]`、1 处 `[AFFILIATIONS TO CONFIRM]`、1 处 `[AUTHOR TO CONFIRM, email address]`、2 处 `[EDITORIAL/LEGAL CONFIRMATION REQUIRED]`、4 处 `[PENDING]`。这直接决定 P0 的作者/法律/DOI 项不能标 DONE。

## 2. `gapbench` 干净安装

T8 使用任务指定的 `[test]` extra 重新做了干净安装：

```bash
rm -rf /tmp/gapbench-final-venv
python3 -m venv /tmp/gapbench-final-venv
/tmp/gapbench-final-venv/bin/python -m pip install -q --upgrade pip
/tmp/gapbench-final-venv/bin/python -m pip install -e "gapbench[test]"
# exit 0；gapbench-1.2.0；pytest 9.2.0、numpy 2.4.6、pandas 3.1.0

/tmp/gapbench-final-venv/bin/python gapbench/examples/quickstart.py
# exit 0；20 年序列、4 个缺口、16 个完整年、CDF/Sxx 各 18 年、S/R/E identity_ok=True

/tmp/gapbench-final-venv/bin/python -m pytest -q gapbench/tests
# 13 passed in 0.13 s
```

**判定：`[test]` 干净安装 PASS，quickstart PASS，13/13 测试 PASS。** 基础安装 `pip install -e gapbench` 仍只装运行时依赖、不含 pytest；`docs/software/INSTALL.md` 和 `gapbench/README.md` 已把测试命令写成 `pip install -e "gapbench[test]"`，因此任务指定的 clean-install 路径不再失败。注意：在仓库根目录用 `python -c "import gapbench"` 会优先命中仓库根的同名目录（namespace package），而不是已安装的 `gapbench/gapbench`；`gapbench.__version__` 在安装包内定义为 `"1.2.0"`。这是运行路径问题，不是版本不一致。

## 3. `ar1_bridge_pathwise` 嵌套与冻结轨迹

```bash
python3 -m pytest -q tests/test_ar1_bridge_nesting.py
# 5 passed
```

代码检查：`ar1_bridge_pathwise` 使用 `np.random.SeedSequence(seed).spawn(draws)`，每条路径一个 `default_rng(child)`；路径 `i` 的随机流不依赖总路径数，因此 20 路径是 500 路径的前缀。测试覆盖逐元素前缀一致性。  
`ar1_bridge` 与 git HEAD 的函数体一致，差异仅为模块 docstring 和函数末尾两个空行；旧采样器未被改写。论文明确写“frozen trajectories are unchanged”，没有声称用 `ar1_bridge_pathwise` 重跑 r4 轨迹。**判定：PASS（代码/测试），但稿件仍保留 native 20 与 nested 500 的 frozen 说明，且未补蒙特卡洛标准误，故 B7 整体为 PARTIAL。**  
环境说明：该测试属于研究代码，导入 `stream_recoverability` 时需要 PyYAML 等研究依赖；在只有 `gapbench[test]` 的干净 venv 中 collection 会因 `No module named 'yaml'` 失败，因此本次在仓库环境运行并通过。这个边界不影响 `gapbench` 的 13 个库测试。

## 4. 元数据与发布材料

```bash
python scripts/check_version_consistency.py
# PASS：pyproject.toml、CITATION.cff、preferred-citation 均为 1.2.0
# WARN：最新 git tag v1.0.0 是历史标签，不代表 1.2.0
# INFO：CITATION.cff 无 DOI（符合尚未 mint DOI 的状态）
# RESULT: PASS
```

| 项目 | 结果 |
|---|---|
| `pyproject.toml` | 版本 1.2.0；描述已改为 leakage-safe gap handling；`review` extra 含 `lightgbm>=4.6,<5` |
| `CITATION.cff` | 版本 1.2.0；标题/摘要改为 gapbench；DOI 未设置；作者仅为别名/邮箱，不是完整作者信息 |
| `Dockerfile` | `pip install -c constraints.txt ".[review,dev]"`；显式 `import lightgbm`；默认运行 gapbench quickstart |
| `LICENSE` | MIT 正文；前言列出 FOEN、GKD Bayern、USGS、NASA POWER、LUBW 及其他提供方，声明不转授数据权利 |
| `docs/software/INSTALL.md` | 存在；干净安装、quickstart、LightGBM、Docker、版本检查均有说明 |
| `docs/software/RELEASE_CHECKLIST.md` | 存在；明确区分本地包、GitHub release、Zenodo DOI；多数发布项仍未勾选 |
| `.zenodo.json` | 版本 1.2.0、gapbench 描述；明确写“No archival DOI, GitHub release, or v1.2.0 git tag exists yet”；与 pyproject/CITATION 一致 |
| `scripts/check_version_consistency.py` | `RESULT: PASS`：pyproject.toml、CITATION.cff、preferred-citation、`.zenodo.json` 均为 1.2.0；WARN 仅历史 v1.0.0 tag；INFO 为 DOI 未设置 |
| git tag / GitHub release / Zenodo DOI | `git tag` 与 `git ls-remote --tags origin` 仅见历史 `v1.0.0`；`gh release list` 仅见 v1.0.0；无 v1.2.0 tag、release 或 DOI |
| `docker build --check .` | exit 1：`permission denied ... /var/run/docker.sock`；这是 daemon 权限问题，不是 Dockerfile 语法结论；未运行完整镜像构建 |

**判定：元数据一致性 PASS；发布状态 BLOCKED。** `.zenodo.json` 的 1.1.0 旧版本问题已关闭。仍需：创建 `v1.2.0` tag、GitHub release、Zenodo DOI；在 acceptance/Release notes 记录 package hash；测量 program size 与 full-replay memory；在具备 Docker 权限的环境运行 `docker build --check .` 和一次快速镜像构建。

## 5. 关键数字交叉核对

| 核对项 | 稿件值 | 保存源 | 结果 |
|---|---|---|---|
| 受控缺口 4 方案 RMSE/符号翻转 | 0.446/0.428/0.402/0.170；53/51/42/16 | `results/wrr_final_revision_20261031/retention_family_summary.csv`（crossed 行） | 4/4 行一致（n=805） |
| 经验日历 4 方案 RMSE/符号翻转 | 0.114/0.098/0.086/0.067；3/5/4/0 | 同上（calendar 行） | 4/4 行一致（n=818） |
| 0.446 为 0.754 的 59.1% | 0.446 / 0.754 = 59.15% | `paper/ems/trend_signal.tex` + retention CSV | 一致 |
| 开放源敏感性 | 0.164/0.147 → 0.158/0.156；93.9→93.7；88.0→87.6 | `paper/wrr_tr/open_source_values.tex`、`results/ems_revision_20261102/flow_diagnostic.json` | 0 处不一致 |
| 零流量 proxy OR | 0.594 [0.409,0.813]；0.474 [0.265,0.676]；0.969 [0.897,1.046] | `flow_diagnostic.json` | 四舍五入一致；n/事件数也一致 |
| 流量 comparator MAE | MOVE.1 0.0734/0.0602；0.0734/0.0495；stochastic 0.0716/0.0495 | `flow_diagnostic.json`；`flow_diagnostic.csv` | 一致；66,099 共同案例、210 站、17 组 |
| 630/169/6、231/57/530、288 | 正文与图注 | `results/wrr_final_revision_20261031/retention_geometry_cases.csv` 复算 | 全部一致 |
| H7 2.94% / 4.85% | “median paired MAE reduction” crossed / calendar | `results/wrr_review_completion_20261024/evidence/H7_refit_direction_stability.csv`：`stochastic_regression_calibrated` / `danger_MAE_gain_positive`，crossed `median_gain=0.029414`、calendar `0.048454` | 有保存源；正文已同时写出两个家族 |
| H7 20/20 | CRPS 与 tail CRPS | 同一 direction CSV：crossed / stochastic_regression_calibrated，crps 20/20、twcrps 20/20；calendar 也 20/20 | 有保存源 |
| H7 ≈81% | trend missingness 覆盖 | `results/wrr_review_completion_20261024/target_windows/h7/full/trends_per_seed.csv`：D2_multiple_imputation 的 `missing_component_coverage` 中位数 81.2%（79.1–86.2）MCAR、80.7%（78.9–87.4）strong heat、4.5%（3.8–5.6）non-air | 有保存源；指 trend 缺测分量，不是 H7 年度覆盖 87.4% |
| S1–S11 SI 主文引用 | H7 引用 S5；无 release-rule SI 引用 | `body.tex:125,167,205` 均写 `Supporting Information Table~S5`；`body.tex:191,207` 写 release rule 只在 research repository、`not in this Supporting Information`；SI 无 `three-output`/`release rule` 小节 | SI 审计 FAIL 已关闭（改为不引用，而非新增 S12） |

**未发现数值冲突。** 两点需标注：(1) 正文 0.337/0.336、89.3/89.8 可追到 `paper/wrr_tr/simple_research_claims.tex` 宏与 `focused_supporting_tables.tex`，不在上述五个指定文件中，本次未独立复算；不构成 mismatch，但可追溯性弱于趋势表。(2) H7 Panel C 是 trend-target 缺测分量覆盖，不是 H7 年度覆盖；SI S5 已把这个区别写清。

## 6. WRR r4 冻结件

```bash
sha256sum dist/wrr_final_candidate_20261101_r4.zip
# cae27ba49a02f0e6da165868bdf78017245b6e1fe549a899b10f1955b4cb2d9e

git status --porcelain -- results/wrr_final_revision_20261031/
# 0 行
```

| 检查项 | 结果 |
|---|---|
| `acceptance.json` package sha256 | `cae27ba4...cb2d9e`，与任务给定值一致 |
| 实际 `dist/wrr_final_candidate_20261101_r4.zip` SHA-256 | 复算一致 |
| `paper/wrr_tr/review_completion_article.pdf` | SHA-256 与 acceptance 记录一致（`ae6357...`） |
| `paper/wrr_tr/review_completion_supporting.pdf` | SHA-256 与 acceptance 记录一致（`aa2c72...`） |
| WRR article/supporting `.tex` | SHA-256 与 acceptance 记录一致 |
| `results/wrr_final_revision_20261031/` 的 11 个 CSV | 11/11 的当前 SHA-256 与 `git cat-file HEAD:...` 逐一相同；也与 `scientific_csv_identity.json` 的 r4 值相同（`all_identical=true`） |
| `results/wrr_final_revision_20261031/` git status | 0 行变更；全仓库无 tracked CSV 修改 |
| `dist/wrr_final_candidate_20261101_r4.zip` | 202,074,883 bytes；SHA-256 `cae27ba49a02f0e6da165868bdf78017245b6e1fe549a899b10f1955b4cb2d9e` |

当前 `paper/wrr_tr/*.pdf/tex` 相对 HEAD 显示 modified，但其 SHA-256 与 r4 acceptance 完全一致；说明它们就是 r4 验收时的版本，不是本轮 EMS 工作改动的结果。`results/final_release_20261101_r4/` 本身是未跟踪的验收证据目录；`results/ems_revision_20261102/` 与 `results/wrr_comprehensive_review_20261102/` 下新增的 CSV 是新证据文件，不是对冻结 r4 科学 CSV 的修改。

## 7. 逐条回应矩阵（T6 历史快照；最终状态见第 8 节）

### 7.1 编辑 P0

| ID | 状态 | 证据 | 具体剩余动作 |
|---|---|---|---|
| P0-1 EMS 格式/Highlights/摘要 | **DONE** | `paper/ems/main.tex`（elsarticle + `elsarticle-harv`）、`abstract.tex`（源文件 185 词；PDF 文本 185 词）、`highlights.txt`（5 条，76/76/79/80/83 字符）、`main.pdf`（37 页/7 图/4 表/52 refs）；0 个 AGU 文档类/Key Points/PLS/WRR 标题 | 无格式性动作；Graphical abstract 已有独立 PDF，但未嵌入正文，按期刊系统要求单独上传 |
| P0-2 ELS 声明 | **PARTIAL** | `declarations.tex` 已有 CRediT、COI、Funding、Ethics、AI 声明；但 PDF 中 18 处 `[AUTHOR TO CONFIRM]`、1 处 email、1 处 affiliation、2 处 `[EDITORIAL/LEGAL CONFIRMATION REQUIRED]`、4 处 `[PENDING]`；Funding/CRediT 未填 | 填作者、单位、ORCID、基金号、CRediT 角色、COI；确认 ethics 与 AI 措辞；删除全部 26 处占位符 |
| P0-3 软件可用性 | **PARTIAL（DOI/审稿访问子项 BLOCKED）** | `software_availability.tex` 有软件名、版本 1.2.0、依赖、MIT、公共仓库；`gapbench` 干净安装、quickstart、13 tests 通过；DOI `[PENDING]`、program size/memory `[PENDING]`；LUBW 审稿访问未落实 | mint DOI；测量 program size 与 full-replay memory；落实 LUBW reviewer access 或明确替代访问方案 |
| P0-4 开放源模型 | **PARTIAL** | `open_source_flow.tex` 报告 0.164/0.147→0.158/0.156、93.9→93.7、88.0→87.6；明确写“candidate route, not legal clearance” | 核实七个 candidate provider 及邻站上游来源的再分发权；公开权重/案例输出；把它定为开放复现主模型或明确不定的理由 |
| P0-5 作者/法律/DOI/审稿访问/保存 | **BLOCKED** | `frontmatter.tex`、`declarations.tex`、`CITATION.cff`、`.zenodo.json`、`RELEASE_CHECKLIST.md`；`.zenodo.json` 已到 1.2.0，但仅历史 v1.0.0 tag/release，无 v1.2.0 tag、release、DOI；LUBW access 未落实 | 完成作者/单位/ORCID/基金/COI；LUBW 法律确认；tag + GitHub release + Zenodo DOI；记录 reviewer access |

### 7.2 审稿人 A

| ID | 状态 | 证据 | 具体剩余动作 |
|---|---|---|---|
| A1 水文语言/RQ2 主线 | **DONE** | `body.tex:3-15` 先写水温控制过程与缺测机制，再给三个问题；观测窗口结果被明确降为 data-use principle | 无结构性动作；可继续压缩 RQ1 段落 |
| A2 趋势尺度/Sen/MK | **PARTIAL** | `trend_signal.tex`、`body.tex:137-141` 已用误差/SE、符号翻转、Sen、tie-corrected MK；明确 SE 未计自相关 | 补 Hamed–Rao/Yue 自相关稳健 MK；正面讨论离线 D2 RMSE 0.009–0.028 与前推 0.067–0.173 的张力 |
| A3 流量一阶控制 | **PARTIAL** | `open_source_flow.tex` 有 zero-flow proxy 与 flow comparator；正文明确“no 34-station daily flow merge / no air2stream-8” | 补齐 34 站 FOEN/GKD 日流量；诊断隐藏峰值误差与流量距平；把流量加入 D2 特征并以 air2stream-8 为过程基准 |
| A4 区域差异/河流类型 | **PARTIAL** | `body.tex:155-159` 报告 Bavaria/Switzerland 失败差异、group deletion、reconstructor-conditioned 反差；明确“cause unidentified” | 用 CAMELS-CH/DE、LamaH-CE、HydroATLAS 做流域属性/河流类型/调节程度分层；核查热电厂停运造成的非平稳 |
| A5 气象强迫代表性 | **NOT DONE** | `body.tex:205` 明确 E-OBS/ERA5-Land forcing sensitivity 未完成 | 做 E-OBS 或 ERA5-Land 替换；报告格点与站点高程差；检验 air-ridge 失效是否对强迫敏感 |
| A6 样本代表性/资料稀缺 | **NOT DONE** | `body.tex:195-197` 承认 long-complete tail；无 history/neighbor ablation | 训练历史截短到 3/5/10 年；邻站减到 0–1 个；给出适用边界曲线；讨论寒区缺测机制 |
| A7 H7 生态含义 | **PARTIAL** | `body.tex:125,167,205` 的 H7 引用已由 `Supporting Information Table~S5` 支撑；SI S5 报告 2.94%/4.85%、20/20、81.2%/80.7%/4.5%；但日均 H30 与日最高/7DADM 的生态/管理含义仍讨论不足 | 讨论 H30 与 7DADM/超阈天数的差别；说明管理使用场景；不要把 H7 当作 H30 确认 |
| A8 缺测机制经验检验 | **NOT DONE** | `body.tex:121` 有观测缺口统计与 controlled stress；没有 missingness ~ air/flow/season 的 logistic/survival 模型 | 用 581 站档案估计缺测发生与气温距平、流量距平、季节的关系；用经验参数校准 0.35/7 年预热等情景 |
| A9 实践决策表/案例 | **PARTIAL** | `decision_table.tex` 给出 7 种情境、误差尺度与证据；`body.tex:179` 给三步流程 | 增加一个真实站 2018/2022 日过程案例：缺口位置、观测下界、D2/经典法区间、对趋势的影响 |
| A10 图件 | **PARTIAL** | `figures.tex` 有 7 图；新增 `figures/study_stations.pdf` 定位图，但只是 Natural Earth 国界定位图，无河网/湖泊/水库/电厂；无日过程案例图 | 改成带河网、湖泊、水库、国界/地形的研究区图；加日过程案例图；检查字号与可读性；3 柱图已不再作为独立图 |

### 7.3 审稿人 B

| ID | 状态 | 证据 | 具体剩余动作 |
|---|---|---|---|
| B1 软件贡献定义/打包/验证 | **PARTIAL** | `gapbench/` 1.2.0；6 个公开函数；13 测试；README；synthetic quickstart；Dockerfile | 做 GitHub release + Zenodo DOI；补 API 文档站点、教程 notebook、可再分发小示例数据；公开 release 的 package hash |
| B2 可复现性 | **PARTIAL** | `[test]` 干净 venv 安装/quickstart/13 tests 通过；Dockerfile 装 `.[review,dev]` 并 import LightGBM；但无 DAG/schema 校验、无 CI Docker build、无 full raw-provider retrain | 加 Snakemake/DVC 或带哈希的 Make 规则；加 schema 校验；CI 构建镜像并跑端到端小样本 |
| B3 方法与 ML/统计文献 | **PARTIAL** | `body.tex:55` 明确 D2 = Mondrian CQR；引 Romano、Tibshirani、Gibbs、Chernozhukov、Meinshausen；讨论七分位与外尾假设 | 说明 LightGBM 超参数来源并做敏感性/嵌套 CV；补 PIT/可靠性图；增加分位水平或改用分布回归 |
| B4 基线 | **NOT DONE** | `body.tex:187,205` 明确 Kalman/imputeTS、missForest、BRITS、SAITS、CSDI 未在同一 mask 上运行 | 在相同 805/818 mask 上跑 Kalman/imputeTS、missForest、BRITS/SAITS；同时报告日误差与 H30/斜率下游误差 |
| B5 多重插补 | **NOT DONE** | `body.tex:187` 明确当前秩耦合不是联合后验；未按 Rubin 规则合并 | 用一个联合日模型（AR/状态空间/CSDI）抽完整日路径；按 Rubin 规则合并；讨论 congeniality |
| B6 群组推断 | **NOT DONE** | `body.tex:189` 讨论 41 站/17 组、伪重复、group bootstrap 偏窄；未运行 wild cluster bootstrap 或混合效应 | 跑 wild cluster bootstrap 或 station/group 随机效应模型；给主要对比的替代区间；补 CONSORT 式分母流程 |
| B7 随机数嵌套 | **PARTIAL** | `ar1_bridge_pathwise` + 5 个嵌套测试通过；`ar1_bridge` 未改；论文明确 frozen r4 未重跑 | 在非冻结 release 中用 pathwise sampler 重跑并替换 native/nested 说明；补 MC 标准误；删除约半节 legacy 文字 |
| B8 计算成本 | **NOT DONE** | `body.tex:77` 只有 budget 数值敏感性；无 wall-clock/CPU/memory | 报告 plug-in、D2 训练/推断、经典 20/500 路径的每站年墙钟/CPU/内存；给国家级网络的复杂度 |
| B9 泄漏控制/元数据 | **PARTIAL** | `body.tex:23` 已明确 HUC17/NVE 保留同区域组、strict-region 敏感性移除；`9,743` 个 `design.json` 中 0 个含精确短语 `held region excluded`；但无 3,320 文件重生成记录、无 leakage checklist/model card | 重生成并记录 3,320 个 design.json；加 leakage 检查表（Kapoor–Narayanan 分类）与 D2 model card |
| B10 发布规则 | **PARTIAL** | `body.tex:191,207` 明确三输出规则不推荐、只在 research repository 保留为 boundary result，且不在 SI；未做 risk–coverage/共形风险控制 | 用 risk–coverage 曲线或 conformal risk control 重评；保持 boundary result 或删除 |
| B11 写作结构 | **PARTIAL** | 37 页、7 图、4 表；SI 13 页、11 表（≤30）；有 Procedure 1、集中 Limitations、决策表、S9 符号表；但仍密集，无 D2/bridge 专用算法框，主文长度未压缩 | 压到 EMS 常见长度；加 D2/bridge 算法框；把历史版本对照移入 SI 或删除 |

### 7.4 次要意见（压缩）

| 项 | 状态 | 证据/动作 |
|---|---|---|
| A-1 connected group 定义 | **DONE** | `body.tex:23` 给出河网/记录家族定义与群组分割用途 |
| A-2 原始分辨率/日均/质量码 | **PARTIAL** | `body.tex:101` 说明 provider daily mean 与芬兰非日值排除；未说明子日不完整日与质量码处理 |
| A-3 暖季月份分布 | **NOT DONE** | 未给各站暖季月份分布；需补 SI 表或图 |
| A-4 文献 40–60 篇 | **DONE** | `references_ems.bib` 52 条；正文引用覆盖水文、ML、软件、统计 |
| A-5 单位/样本单位 | **DONE** | 统一 °C/10a；定义 station-year、archive、connected group、reference-year set |
| A-6 42 vs 41 站 | **DONE** | 摘要写 41；`body.tex:99` 解释 42 评估站、1 个芬兰记录 1994 结束故前推 41 |
| B-1 available/common/paired 术语 | **PARTIAL** | 关键术语已定义，但 available/common/paired 仍未集中统一定义 |
| B-2 bootstrap 种子 | **NOT DONE** | 正文只说 10,000 次 group resampling；未集中说明种子与种子敏感性 |
| B-3 数值宏读者可见性 | **DONE** | EMS 正文使用硬编码数值；宏名未进入读者可见文字 |
| B-4 线程设置/确定性 | **NOT DONE** | 未说明 `OMP_NUM_THREADS=1` 等设置与 LightGBM 非确定性 |
| B-5 torch/xgboost 安装面 | **NOT DONE** | `pyproject.toml` 核心依赖仍含 `torch`、`xgboost`；未移入历史/可选 extra |

## 8. T8 最终状态（覆盖第 7 节的 T6 历史状态）

T8 只读复核了主文、SI、`gapbench`、元数据和 r4 冻结件。以下状态是最终台账；与第 7 节冲突时以本节为准。

### 8.1 P0

| 任务 | 最终状态 | 证据 | 剩余动作 |
|---|---|---|---|
| EMS 格式/Highlights/摘要 | **DONE** | 37 页；7 图；4 表；52 refs；摘要源文件 185 词（PDF 文本 185 词）；Highlights 76/76/79/80/83 字符；0 `??`、0 `(author?)`、0 Overfull/Underfull、0 undefined；无 AGU 文档类/Key Points/PLS/WRR 标题/contact-authors/available-on-request | 无；Graphical abstract 按系统单独上传 |
| ELS 声明 | **PARTIAL** | `declarations.tex` 有 CRediT/COI/Funding/Ethics/AI 模板；PDF 仍有 26 处占位符（18 author、1 email、1 affiliation、2 legal、4 pending） | 填作者/单位/ORCID/基金/CRediT/COI；确认 ethics 与 AI 措辞 |
| 软件交付/软件库 | **DONE（库）/ BLOCKED（release）** | `gapbench` 1.2.0；`pip install -e "gapbench[test]"` PASS；quickstart PASS；13/13 tests PASS；6 个公开函数；MIT；Dockerfile 存在 | v1.2.0 tag、GitHub release、Zenodo DOI 仍 BLOCKED；Docker 构建未在 daemon 权限下验证 |
| 软件可用性元数据 | **PARTIAL（DOI/审稿访问 BLOCKED）** | `software_availability.tex` 有版本/依赖/许可证/公共仓库；program size 与 full-replay memory 仍 `[PENDING]`；LUBW reviewer access 未落实 | 测 program size/memory；落实 LUBW access；mint DOI |
| 开放源模型前置 | **PARTIAL** | 0.164/0.147→0.158/0.156；93.9→93.7；88.0→87.6；明确 candidate route, not legal clearance | 核实七个 candidate provider 与邻站上游来源再分发权；公开权重/案例输出 |
| 作者/法律/DOI/审稿访问/保存 | **BLOCKED** | 26 处占位符；仅历史 v1.0.0 tag/release；无 v1.2.0 tag、release、DOI；LUBW access pending | 完成作者/法律/DOI/reviewer access；永久保存与 hash 记录 |

### 8.2 P1

| 任务 | 最终状态 | 证据 | 剩余动作 |
|---|---|---|---|
| 实际意义重述（趋势） | **PARTIAL** | 摘要/结论已改用 RMSE、误差/SE、符号翻转、Sen/MK；0.446→0.170、0.114/0.067、0.590 SE 均与冻结表一致 | Hamed–Rao/Yue 自相关稳健 MK 未做；离线 D2 RMSE 0.009–0.028 与前推 0.067–0.173 的张力仍可展开 |
| 流量与流域属性（A3） | **PARTIAL** | 零流量 proxy OR 与 flow comparator 表已报告；明确“no 34-station daily flow merge / no air2stream-8” | 补齐 34 站 FOEN/GKD 日流量；诊断隐藏峰值误差与流量距平；air2stream-8；流域属性分层 |
| 现代基线（B4） | **NOT DONE** | `body.tex:205` 明确 Kalman/imputeTS、missForest、BRITS、SAITS 未在同一 mask 上运行 | 在 805/818 mask 上跑基线并报告日误差与下游 H30/斜率误差 |
| 多重插补（B5） | **NOT DONE** | 当前秩耦合不是联合后验，未按 Rubin 规则合并 | 联合日模型抽路径；Rubin 合并；讨论 congeniality |
| 随机数嵌套（B7） | **PARTIAL（code/test DONE）** | `ar1_bridge_pathwise` + 5 个嵌套测试通过；`ar1_bridge` 未改；frozen r4 未重跑 | 非冻结 release 用 pathwise sampler 重跑；补 MC 标准误；删除 native/nested 说明 |
| 群组推断（B6） | **NOT DONE** | 41 站/17 组、group bootstrap 偏窄已讨论；未跑 wild cluster bootstrap/混合效应 | 跑 wild cluster bootstrap 或 station/group 随机效应；给替代区间 |
| 资料稀缺消融（A6） | **NOT DONE** | 正文承认 long-complete tail；无 history/neighbor ablation | 训练历史截短 3/5/10 年；邻站减到 0–1；适用边界曲线 |
| 强迫数据敏感性（A5） | **NOT DONE** | 正文明确 E-OBS/ERA5-Land forcing sensitivity 未完成 | 做 E-OBS 或 ERA5-Land 替换；报告格点-站点高程差 |
| 缺测机制经验模型（A8） | **NOT DONE** | 只有观测缺口统计与 controlled stress | 用 581 站档案估计 missingness ~ air/flow/season |
| 计算成本（B8） | **NOT DONE** | 只有 budget 数值敏感性；无 wall-clock/CPU/memory | 报告 plug-in、D2、经典 20/500 路径的每站年成本 |
| 泄漏控制/元数据（B9） | **PARTIAL** | 正文明确 HUC17/NVE 同区域组保留与 strict-region 敏感性；未记录 3,320 个 `design.json` 的重生成，未加 leakage checklist/model card | 重生成并记录 design.json；补 leakage 检查表与 D2 model card |
| 发布规则（B10） | **PARTIAL** | 已明确不推荐、只在 research repository 保留为 boundary result，且不在 SI；未做 risk–coverage/conformal risk control | 保持 boundary result 或补 risk–coverage 重评 |
| H7 稳健性 | **DONE** | SI S5；2.94%/4.85%；CRPS 与 tail CRPS 20/20；Panel C 81.2%/80.7%/4.5% 与 `trends_per_seed.csv` 一致 | 保持为不同目标的稳健性检查，不作 H30 确认 |
| 锁定确认 | **BLOCKED** | 无 OSF 预登记；无新站点一次性确认运行 | 预登记 + 新站点一次性运行；当前不能用内部诊断替代 |

### 8.3 P2

| 任务 | 最终状态 | 证据 | 剩余动作 |
|---|---|---|---|
| 结构重写 | **PARTIAL** | 37 页、7 图、4 表；SI 13 页、11 表；Procedure 1、集中 Limitations、决策表、S9 符号表 | 压缩主文；补 D2/bridge 专用算法框；历史版本对照移入 SI 或删除 |
| 图件 | **PARTIAL** | 7 图，含研究区定位图；无河网/湖泊/水库/电厂图层，无日过程案例图 | 改研究区图；加日过程案例图；检查字号/可读性 |
| 文献 | **DONE** | 52 条；44 个 DOI 可解析；0 未解析/0 重复/0 孤立；0 `(author?)`；0 undefined citation | 8 个无 DOI venue 为非阻断 WARN；diaz2025 为摘要级核验残余风险 |
| SI | **DONE** | `supporting_information.pdf` 13 页、11 表 S1–S11；0 Overfull/Underfull/undefined；H7 → S5；release-rule 引用已移除；T9 已补每表 Source 行、S3 uniform_exact 说明、S4 端点表述、S8 MAE 分母；SI 审计 PASS | 无 |

### 8.4 非阻断警告

- SI 审计的 FAIL 与 T8 列出的 WARN 已在 T9 关闭：S1–S11 均加入 Source 行；S3 说明 `uniform_exact` 未保存并给出 0.449/0.135、55/8；S4 区分 4,096 draws 的区间端点（87.4–89.9%）与点估计（87.5–89.7%）；S8 明确 log-MAE、paired common-case 66,099/33,609、210 站/17 组。`SI_AUDIT_ZH.md` 状态为 PASS。
- 参考文献审计 0 FAIL；8 个不发行 DOI 的 venue 条目仍是 WARN；`diaz2025` 的摘要级核验是残余风险，不是 FAIL；`vanvliet2011` 页码与 `gibbs2023` key/year 注释已按审计修正。
- `CITATION.cff` 的 `date-released: 2026-11-02` 是版本日期，不是 GitHub/Zenodo release 声明；在 mint DOI 前建议与 release 日期对齐，避免误读。
- `tests/test_ar1_bridge_nesting.py` 需要研究依赖（PyYAML）；在只有 `gapbench[test]` 的 venv 中不能 collection，因此该测试在仓库环境运行（5 passed）。这不是 `gapbench` 库测试失败。
- 磁盘 PDF 与当前源码的干净重建页数一致（37/13），文本内容一致；字节 SHA-256 会因 PDF 构建元数据不同而不同，不能把重建哈希当作交付哈希。

## 9. 结论

**EMS 包现在是 submission-shaped，不是 submission-ready。** 格式、Highlights、摘要、参考文献、图/表数量、SI（11 表）、软件库、随机数嵌套代码/测试和 r4 冻结件均已达到可送审的形态；`gapbench` 在 `[test]` 干净环境中安装、quickstart 和 13/13 测试通过。

但以下阻塞项仍未关闭：

1. **外部 P0**：作者/单位/ORCID/基金/CRediT/COI、LUBW 法律与审稿访问、v1.2.0 tag/GitHub release/Zenodo DOI、program size/full-replay memory；PDF 仍有 26 处占位符。
2. **缺失实验**：34 站日流量与 air2stream-8（A3 PARTIAL）、现代插补基线（B4 NOT DONE）、联合模型多重插补（B5 NOT DONE）、wild cluster bootstrap/混合效应（B6 NOT DONE）、E-OBS/ERA5-Land 强迫敏感性（A5 NOT DONE）、历史长度/邻站消融（A6 NOT DONE）、缺测机制经验模型（A8 NOT DONE）、计算成本（B8 NOT DONE）。
3. **锁定确认：BLOCKED**。没有在从未打开的新站点上只运行一次，也没有 OSF 预登记；这是审稿人 B 认为最能提升可信度的外部验证，当前无法用内部诊断替代。
4. **参考文献仍有非阻断 WARN**：8 个不发行 DOI 的 venue 条目，以及 diaz2025 的摘要级核验残余风险。SI 来源/口径 WARN 已在 T9 关闭，`SI_AUDIT_ZH.md` 为 PASS。
5. **不得 overclaim**：开放源模型仍只是 candidate route，不是法律 clearance；H7 是不同目标，不是 H30 确认；区域差异原因仍未识别；当前结果不是锁定确认性检验；无 DOI/tag/release。

在上述 P0 和缺失实验完成前，不应把本稿描述为“已可投稿”或“软件/数据权利已解决”。


## 10. T11 状态更正（2026-11-03 第二轮对抗审计后）

第 8-9 节为 T8 时的历史快照。本轮之后的状态更正如下（历史行不改写，以此节为准）：

- **B6 已完成**（本轮修正实现缺陷后完成）：`scripts/986_wild_cluster_bootstrap.py` 现为影响函数中心化的 score bootstrap
  （Kline--Santos 型，Rademacher 与 Webb 权重），中心化有回归断言，模拟覆盖与三明治尺度有校准测试；结果在
  `results/ems_revision_20261102/wild_cluster_bootstrap.{csv,json}`，SI 表 S12 与正文数字已同步（中位宽度比 0.88；
  两个方法依赖对比：日历 uniform-exact 与日历 D2-经典法）。
- **B8 已完成（本地实测）**：程序规模 17 文件 / 1,654 行 / 73 KiB（28 KiB zip）；quickstart 0.23 s / 37 MiB；
  研究包 1,623 档案重放 9.7 s / 289 MiB。已写入 software availability 与 SI S10。
- **v1.2.0 tag/release 已存在**；本轮升级为 **gapbench 1.3.0**（新增日期感知 annual_h30/L_y、缺口生成器、三条基线、
  run_benchmark，22 项测试），v1.3.0 tag/release 与 sdist/wheel 资产随本轮提交创建。Zenodo DOI 仍未 mint。
- **T1 Hamed--Rao 已修正**：先 Sen 去趋势、只取 5% 显著滞后、方差乘以修正因子；与 pyMannKendall 1.4 在全部 41 站
  一致（6/41 站 p<0.05，2 站修正因子非正）；`trend_signal.{json,csv}` 已重算，含不确定性膨胀、|t| 分层翻转与
  变更年集队列指标。
- 外部 P0（作者/单位/ORCID/基金/CRediT/COI、LUBW 法律、Zenodo DOI、锁定确认）与 A3/A5/A6/A8/B4/B5 等需新数据或
  重训练的项目仍为未完成。
