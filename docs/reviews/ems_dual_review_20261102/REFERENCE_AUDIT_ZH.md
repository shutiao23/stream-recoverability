# EMS 参考文献独立审计（REFERENCE_AUDIT_ZH）

- **审计对象**：`paper/ems/references_ems.bib`
- **审计时点**：2026-11-02 18:24 UTC（最终写入；审计启动时 32 条，literature agent 完成后为 52 条）
- **引用源**：`paper/ems/body.tex`；`paper/ems/open_source_flow.tex` 的 3 个 key 也都在 body 中
- **审计方式**：Crossref REST（44 个 DOI 逐条解析）、OpenAlex、NeurIPS/ICLR/JMLR 官方页面、OpenReview、出版社/机构库；人工核对 20 个新增 key 与全部 6 个 `\citet` 上下文
- **限制**：只读审计，未修改代码、论文、bib、结果或冻结产物；Diaz et al. (2025) 全文在付费墙后，仅核对摘要与 Crossref 元数据，其余关键断言尽量核对全文或摘要

## 1. 总体结论

| 检查项 | 结果 | 状态 |
|---|---|---|
| 参考文献总数（目标 40–60） | **52** | PASS |
| 唯一 citation key | **52 个，无重复** | PASS |
| body.tex 引用 key 解析 | **52/52 可解析，0 个未解析** | PASS |
| bib 条目被引用情况 | **52/52 均被 body.tex 引用，无孤立条目** | PASS |
| DOI 解析 | **44/44 可解析**；题名、作者、年、卷、期、页与 Crossref 一致 | PASS |
| 元数据条目状态 | **42 PASS / 10 WARN / 0 FAIL** | 见 §2 |
| 新增 20 个 key 的引用语义 | **20/20 匹配** | PASS |
| 6 个 `\citet` 的引用语义 | **6/6 匹配**（其中 diaz2025 为摘要级核验） | PASS |
| `\citet` 排版 | 当前 `elsarticle-num` 下 6 处渲染为 `(author?) [n]` | **WARN（需修，非 bib 错误）** |
| BibTeX 构建 | 52 个 bibitem；0 个缺失引用；1 个 BibTeX warning（angelopoulos2024 空页码）；6 个 natbib `Author undefined` warning（即 `(author?)`） | WARN（非阻断） |

**结论**：未发现 FAIL。52 条文献全部可解析、全部被引用、无重复 key、无重复 DOI。10 个 WARN 中，8 个是 NeurIPS/ICLR/JMLR 等不发行 DOI 的 venue（可接受），1 个是 `vanvliet2011` 缺页码（可精确修正），1 个是 `gibbs2023` 的 key 年份与正式出版年不一致（建议改 key）。另有一个独立的排版问题：`\citet` 与 `elsarticle-num` 不兼容，PDF 中出现 `(author?)`，必须在投稿前修复。

## 2. 需修正/需确认条目（WARN）

### 2.1 可直接修正

**(1) `vanvliet2011`：缺页码**

- Crossref 只暴露内部稿号 `2010WR009198`，没有 page 字段；OpenAlex 也没有 first/last page。
- WUR 机构库（`research.wur.nl`）明确标注：**Article number W02544, 19 pages**，期刊 `Water Resources Research` 47(2), 2011。
- 精确修正：在 `vanvliet2011` 条目中增加

```bibtex
pages = {W02544},
```

> 不建议写 `pages = {2010WR009198}`；这是 AGU 的内部稿号，不是文章编号。

**(2) `gibbs2023`：key 年份与正式出版年不一致**

- 条目元数据本身正确：`Journal of the Royal Statistical Society Series B: Statistical Methodology`, **87(4): 1100–1126, 2025**, DOI `10.1093/jrsssb/qkaf008`；`note = {Preprint arXiv:2305.12616, 2023}` 也正确（arXiv API 已核实）。
- 问题只在 key：`gibbs2023` 会让读者以为引用的是 2023 预印本，而条目实际是 2025 正式版。
- 建议：将 key 改为 `gibbs2025`，并同步 `paper/ems/body.tex:185` 的 `\citep{gibbs2023}`。若作者确实想引用 2023 预印本，则应改为 `@misc`/arXiv 条目并把 `year` 改为 2023；二选一，不要像现在这样 key 与 year 混用。

### 2.2 无需修正、仅记录

**(3) 8 个无 DOI 条目**：`angelopoulos2024`、`cao2018`、`geifman2017`、`gibbs2021`、`meinshausen2006`、`romano2019`、`tashiro2021`、`tibshirani2019`。

- 这些 venue（ICLR、NeurIPS、JMLR）不发行 DOI；条目均提供了官方 URL 或 arXiv 标识，且页码/卷号已用 NeurIPS 官方 BibTeX、JMLR 页面或 OpenAlex 核实。
- 不建议为了“补齐 DOI”而编造或引用非官方 DOI；保持现状即可。

**(4) `angelopoulos2024` 空页码**：ICLR 2024 不编页码，BibTeX 的 `Warning--empty pages` 属预期。不要编造页码；若要消除 warning，可将条目改为 `@misc` 并在 `note` 中写 `ICLR 2024`，但当前 `@inproceedings` + `booktitle` 的写法在语义上更清楚。

**(5) 未发现其他可疑元数据**：未发现错刊、错卷、错年、作者错位或 DOI 指向他文。Crossref 的少量差异均为源数据格式问题：`cameron2008` 的刊名 “The”、`hamed1998` 的 family name、`salmon2011` 的题名截断、`chernozhukov2010` 的作者字段缺失；bib 侧均正确，不应按 Crossref 的格式差异回改。

## 3. 逐条审计表（52/52）

状态：**PASS** = 元数据与权威源一致且引用语境匹配；**WARN** = 有可接受或可修正的问题；**FAIL** = 错误或无法解析。本次 **0 FAIL**。

| key | 状态 | 年 | DOI / 标识 | 核查结论 |
|---|---|---|---|---|
| `angelopoulos2024` | WARN | 2024 | arXiv:2208.02814 / ICLR | 无 DOI、无页码（ICLR 不编页码）；OpenReview 确认 **ICLR 2024 spotlight**；5 位作者与题名正确；空页码 warning 非阻断。 |
| `arismendi2014` | PASS | 2014 | 10.1088/1748-9326/9/8/084015 | ERL 9(8):084015；Crossref 一致；引用匹配。 |
| `barker2022` | PASS | 2022 | 10.1038/s41597-022-01710-x | Sci Data 9(1):622；Crossref 一致；FAIR 软件语境匹配。 |
| `beaufort2022` | PASS | 2022 | 10.5194/hess-26-3477-2022 | HESS 26(13):3477–3495；一致；`\citet` 语义匹配（thermal peak + climate correction 已全文核实）。 |
| `bennett2013` | PASS | 2013 | 10.1016/j.envsoft.2012.09.011 | EMS 40:1–20；一致；性能表征框架语境匹配。 |
| `cameron2008` | PASS | 2008 | 10.1162/rest.90.3.414 | REStat 90(3):414–427；一致；cluster bootstrap 语境匹配。刊名含 “The” 与官方刊名一致，Crossref 省略 “The” 不算错。 |
| `cao2018` | WARN | 2018 | NeurIPS proceedings URL | 无 DOI（NeurIPS 不发行）；31:6775–6785 已核实；URL 正确；BRITS 语境匹配。 |
| `chernozhukov2010` | PASS | 2010 | 10.3982/ECTA7880 | Econometrica 78(3):1093–1125；Crossref 作者字段为空，OpenAlex 确认 3 位作者与 bib 一致；引用匹配。 |
| `cornes2018` | PASS | 2018 | 10.1029/2017JD028200 | JGR Atmos 123(17):9391–9409；一致；E-OBS 语境匹配。 |
| `diaz2025` | PASS | 2025 | 10.1016/j.envsoft.2025.106655 | EMS 193:106655；Crossref 一致；摘要确认按 groundwater/reservoir 分层评估；`thermal-discharge` 为全文级细节，未独立核验（付费墙），引用方向一致。 |
| `du2023` | PASS | 2023 | 10.1016/j.eswa.2023.119619 | ESWA 219:119619；一致；SAITS 语境匹配。 |
| `dwork2015` | PASS | 2015 | 10.1126/science.aaa9375 | Science 349(6248):636–638；一致；reusable holdout 语境匹配。 |
| `feigl2021` | PASS | 2021 | 10.5194/hess-25-2951-2021 | HESS 25(5):2951–2977；一致；ML 温度预测语境匹配。 |
| `gallice2015` | PASS | 2015 | 10.5194/hess-19-3727-2015 | HESS 19(9):3727–3753；一致；物理统计模型/地下水语境匹配。 |
| `geifman2017` | WARN | 2017 | NeurIPS proceedings URL | 无 DOI；30:4878–4887 已核实；URL 正确；selective classification 语境匹配。 |
| `gibbs2021` | WARN | 2021 | NeurIPS proceedings URL | 无 DOI；34:1660–1672 已由 NeurIPS 官方 BibTeX 核实；URL 正确；ACI 语境匹配。 |
| `gibbs2023` | WARN | 2025 | 10.1093/jrsssb/qkaf008 | 条目为 JRSS-B 2025, 87(4):1100–1126；key 仍为 2023（预印本年）；note 的 arXiv:2305.12616 正确。建议 key 改 `gibbs2025` 并同步 body.tex:185。 |
| `hamed1998` | PASS | 1998 | 10.1016/S0022-1694(97)00125-X | J Hydrol 204(1–4):182–196；一致；Crossref 把作者 family 存为 “Ramachandra Rao”，bib 的 `Rao, A. Ramachandra` 是正确姓名，勿改。 |
| `hare2021` | PASS | 2021 | 10.1038/s41467-021-21651-0 | Nat Commun 12(1):1450；一致；`\citet` 的 “197 of 1,424、>14 complete years” 已对 Nature Comms 全文核实。 |
| `hoge2023` | PASS | 2023 | 10.5194/essd-15-5755-2023 | ESSD 15(12):5755–5784；一致；CAMELS-CH 语境匹配。 |
| `hutton2016` | PASS | 2016 | 10.1002/2016WR019285 | WRR 52(10):7548–7555；一致；可重复性语境匹配。 |
| `isaak2012` | PASS | 2012 | 10.1007/s10584-011-0326-z | Clim Change 113(2):499–524；一致；`\citet` 的 reconstructed trends 已对 Springer 全文核实。 |
| `jakeman2006` | PASS | 2006 | 10.1016/j.envsoft.2006.01.004 | EMS 21(5):602–614；一致；十步迭代语境匹配。 |
| `johnson2021` | PASS | 2021 | 10.1016/j.ecolind.2020.107229 | Ecol Indic 122:107229；一致；`\citet` 的 mean/phase/amplitude + imputation + groundwater 限制已摘要核实。 |
| `kapoor2023` | PASS | 2023 | 10.1016/j.patter.2023.100804 | Patterns 4(9):100804；一致；`\citet` 的 8 类 leakage taxonomy 已摘要核实。 |
| `klingler2021` | PASS | 2021 | 10.5194/essd-13-4529-2021 | ESSD 13(9):4529–4565；一致；LamaH-CE 语境匹配。 |
| `lehner2011` | PASS | 2011 | 10.1890/100125 | Front Ecol Environ 9(9):494–502；一致；全球大坝数据语境匹配。 |
| `linke2019` | PASS | 2019 | 10.1038/s41597-019-0300-6 | Sci Data 6(1):283；一致；HydroATLAS 语境匹配。 |
| `little2019` | PASS | 2019 | 10.1002/9781119482260 | Wiley 3rd ed.；Crossref 一致；MI 专著语境匹配。 |
| `loritz2024` | PASS | 2024 | 10.5194/essd-16-5625-2024 | ESSD 16(12):5625–5642；一致；CAMELS-DE 语境匹配。 |
| `meinshausen2006` | WARN | 2006 | JMLR URL | 无 DOI（JMLR 不发行）；7:983–999 已核实；URL 正确；quantile forest 语境匹配。 |
| `meng1994` | PASS | 1994 | 10.1214/ss/1177010269 | Stat Sci 9(4):538–558；一致；uncongenial MI 语境匹配。 |
| `mitchell2019` | PASS | 2019 | 10.1145/3287560.3287596 | FAT* '19, 220–229；一致；model card 语境匹配。 |
| `mohseni1998` | PASS | 1998 | 10.1029/98WR01877 | WRR 34(10):2685–2692；一致；非线性温度模型语境匹配。 |
| `molder2021` | PASS | 2021 | 10.12688/f1000research.29032.2 | F1000Research 10:33（article no.）；一致；Snakemake/workflow DAG 语境匹配。 |
| `moritz2017` | PASS | 2017 | 10.32614/RJ-2017-009 | R Journal 9(1):207–218；一致；imputeTS 语境匹配。 |
| `munoz2021` | PASS | 2021 | 10.5194/essd-13-4349-2021 | ESSD 13(9):4349–4383；一致；ERA5-Land 语境匹配。 |
| `orr2015` | PASS | 2015 | 10.1002/hyp.10181 | Hydrol Process 29(5):752–766；一致；river temperature trend 语境匹配。 |
| `rahmani2021` | PASS | 2021 | 10.1002/hyp.14400 | Hydrol Process 35(11):e14400；一致；DL 温度预测语境匹配。 |
| `roberts2017` | PASS | 2017 | 10.1111/ecog.02881 | Ecography 40(8):913–929；一致；结构化交叉验证语境匹配。 |
| `romano2019` | WARN | 2019 | NeurIPS proceedings URL | 无 DOI；32:3538–3548 已核实；URL 正确；CQR 语境匹配。 |
| `rubin1987` | PASS | 1987 | 10.1002/9780470316696 | Wiley 专著；Crossref 一致；MI/Rubin's rules 语境匹配。 |
| `salmon2011` | PASS | 2011 | 10.1145/2063384.2063405 | SC '11, 1–12；Crossref 题名截断为 “Parallel random numbers”，DOI 正确；Random123/counter-based RNG 语境匹配。 |
| `stekhoven2012` | PASS | 2012 | 10.1093/bioinformatics/btr597 | Bioinformatics 28(1):112–118；一致；missForest 语境匹配。 |
| `tashiro2021` | WARN | 2021 | NeurIPS proceedings URL | 无 DOI；34:24804–24816 已由 NeurIPS 官方 BibTeX 核实；URL 正确；CSDI 语境匹配。 |
| `tibshirani2019` | WARN | 2019 | NeurIPS proceedings URL | 无 DOI；32:2526–2536 已核实；URL 正确；covariate shift 语境匹配。 |
| `toffolon2015` | PASS | 2015 | 10.1088/1748-9326/10/11/114011 | ERL 10(11):114011；一致；air2stream/流量语境匹配。 |
| `vanbuuren2018` | PASS | 2018 | 10.1201/9780429492259 | Chapman and Hall/CRC 2nd ed.；Crossref 一致；MI 设计语境匹配。 |
| `vanvliet2011` | WARN | 2011 | 10.1029/2010WR009198 | WRR 47(2)；**缺页码**；WUR 机构库确认 Article no. **W02544**（19 pp）。修正：`pages = {W02544}`。 |
| `webb2008` | PASS | 2008 | 10.1002/hyp.6994 | Hydrol Process 22(7):902–918；一致；综述语境匹配。 |
| `yue2002` | PASS | 2002 | 10.1002/hyp.1095 | Hydrol Process 16(9):1807–1829；一致；autocorrelation/TFPW 语境匹配。 |
| `zwart2023` | PASS | 2023 | 10.3389/frwa.2023.1184992 | Front Water 5:1184992；一致；unmonitored forecast 语境匹配。 |

## 4. 新增 20 个 key 的引用语义抽查

这 20 个 key 是相对审计开始时 32 条版本新增的条目；逐条对照 body.tex 语境与论文题名/摘要，全部匹配。

| key | body.tex 中的用途 | 判定 |
|---|---|---|
| `barker2022` | FAIR research software / 可重复性论证 | PASS |
| `bennett2013` | 环境模型 performance-characterization 框架 | PASS |
| `cornes2018` | E-OBS 强迫敏感性（未完成项） | PASS |
| `dwork2015` | 反复使用 holdout 会侵蚀名义有效性 | PASS |
| `hamed1998` | 自相关下的 modified Mann–Kendall 方差 | PASS |
| `hoge2023` | 瑞士 CAMELS-CH 大样本集合 | PASS |
| `hutton2016` | 计算水文学不可重复性 | PASS |
| `jakeman2006` | 模型开发—评估的十步迭代框架 | PASS |
| `klingler2021` | 中欧 LamaH-CE 集合 | PASS |
| `lehner2011` | 全球水库/大坝数据 | PASS |
| `linke2019` | 全球河段属性（HydroATLAS） | PASS |
| `loritz2024` | 德国 CAMELS-DE 集合 | PASS |
| `molder2021` | 工作流 DAG / Snakemake | PASS |
| `munoz2021` | ERA5-Land 再分析 | PASS |
| `orr2015` | England/Wales 河流温度趋势 | PASS |
| `roberts2017` | 时空/层级结构数据的交叉验证 | PASS |
| `salmon2011` | counter-based random streams（Random123） | PASS |
| `vanbuuren2018` | 多重插补的设计要求 | PASS |
| `yue2002` | 自相关对趋势检测的影响 / TFPW | PASS |
| `zwart2023` | 无监测站点的温度重建/预报 | PASS |

## 5. 全部 `\citet` 用法核查（6 处）

| key | 位置 | body.tex 中的具体断言 | 核验结果 | 判定 |
|---|---|---|---|---|
| `hare2021` | `body.tex:5` | “retained 197 of 1,424 stations after requiring more than 14 complete years” | Nature Communications 全文：1,424 个无大坝站点中，197 个有 >14 年完整年记录；数字与措辞一致。 | PASS |
| `johnson2021` | `body.tex:7` | “evaluated missing intervals and imputation for annual mean, phase and amplitude, and found river-dependent limitations” | 摘要确认 sine-wave 拟合的 mean/phase/amplitude 三参数、imputation，以及 groundwater-influenced 站点精度下降等限制；“river-dependent” 是合理概括。 | PASS |
| `beaufort2022` | `body.tex:7` | “built a multiyear thermal-peak metric from heterogeneous summer observations with climate correction” | HESS 全文 §2.3 明确为 “Climate correction of the thermal peak”；数据为 2009–2017 九年、1,700 站；“multiyear” 成立。 | PASS |
| `isaak2012` | `body.tex:7` | “used reconstructed records to estimate long-term thermal trends” | Springer 全文明确使用 multiple regression 得到 “reconstructed trend estimates”；引用准确。 | PASS |
| `diaz2025` | `body.tex:7` | “evaluated process-stratified machine-learning predictions of daily temperature with coverage by groundwater, reservoir and thermal-discharge setting” | 摘要确认按 stream type（reservoir/groundwater influence）分层并报告 90% PI coverage；`thermal-discharge` 为全文级细节，因付费墙未能独立核验，但引用方向与摘要一致。 | PASS（摘要级） |
| `kapoor2023` | `body.tex:189` | “data-leakage taxonomy” | 摘要明确 “a detailed taxonomy of eight types of leakage”；引用准确。 | PASS |

**重要排版问题（非 bib 元数据错误）**：当前 `main.tex` 使用 `\bibliographystyle{elsarticle-num}`，而正文使用 author–year 的 `\citet`。在 18:25 UTC 重建的 `main.pdf` 中，上述 6 处均渲染为 `(author?) [n]`（例如 `(author?) [13]`、`(author?) [5]`）。`main.log` 没有缺失引用（0 个 undefined citation），但有 6 个 `Package natbib Warning: Author undefined for citation`，正是这一问题的来源。修复二选一：

1. 改用 `elsarticle-harv`（作者—年份制），或
2. 保留 `elsarticle-num`，把 6 处 `\citet{key}` 改为“作者名 + `\citep{key}`”（例如 `Hare et al.~\citep{hare2021}`）。

这是投稿前必须修的可见缺陷；它不影响 bib 条目本身，也不影响本文档的 42 PASS / 10 WARN / 0 FAIL 统计。

## 6. 未解析、重复与计数

- **未解析 key**：**无（0 个）**。body.tex 的 52 个唯一 key 全部能在 bib 中找到；`open_source_flow.tex` 额外使用的 `vanvliet2011`、`toffolon2015`、`diaz2025` 也都在 bib 中。
- **未被引用的 bib 条目**：**无（0 个）**；52 条全部被 body.tex 引用。
- **重复 citation key**：**无（52 个 key 全部唯一）**。
- **重复 DOI**：**无**（44 个 DOI 全部唯一）。
- **总数**：**52 条**，在 40–60 目标区间内；相对审计启动时的 32 条新增 20 条，符合 literature agent 的扩充目标。
- **DOI 覆盖率**：44/52 = **84.6%**；8 条无 DOI 均为不发行 DOI 的 venue（ICLR/NeurIPS/JMLR），且均有官方 URL 或 arXiv 标识。

## 7. 构建证据与残余风险

- `paper/ems/main.bbl`（18:25 UTC）含 **52 个 `\bibitem`**；`main.log` 中 **0 个缺失引用、0 个 undefined reference**；但有 **6 个 `Package natbib Warning: Author undefined for citation`**（hare2021、johnson2021、beaufort2022、isaak2012、diaz2025、kapoor2023），对应 PDF 中的 `(author?)`。
- `main.blg` 仅 1 个 BibTeX warning：`Warning--empty pages in angelopoulos2024`；这是 ICLR 条目的预期行为，不建议编造页码。
- 残余风险：
  1. `diaz2025` 的 `thermal-discharge` 细节只做到摘要级核验；若审稿人追问，建议作者用原文核对这一短语。
  2. `gibbs2023` 的 key/year 混用会让读者误判版本；建议按 §2.1 改 key。
  3. `vanvliet2011` 的 `W02544` 来自 WUR 机构库；若期刊要求以 AGU 官网为准，可在校样阶段再确认一次，但 `W02544` 与 19 页的著录信息一致。
  4. `\citet` 的 `(author?)` 渲染是当前 PDF 的可见缺陷，优先级高于上述三条元数据 WARN。

**审计结论**：bib 元数据质量良好，**0 FAIL**；在修正 `vanvliet2011` 页码、统一 `gibbs2023` key/year、并修复 `\citet` 排版后，可视为通过参考文献审计。
