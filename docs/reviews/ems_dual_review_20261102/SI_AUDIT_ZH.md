# EMS Supporting Information 独立审计（T9 复核）

- 日期：2026-11-02
- 审计对象：`paper/ems/supporting_information.tex`、`paper/ems/supporting_information.pdf`、`paper/ems/si_tables/S1..S11`
- 对照文件：`paper/ems/body.tex`（SI 引用）、`results/ems_revision_20261102/trend_signal.csv`、`flow_diagnostic.json`、`results/wrr_final_revision_20261031/`、H7 源文件、`results/wrr_comprehensive_review_20261102/archive_level_comparisons.csv`、`results/wrr_adversarial_review_20261027/rank_convergence/`、`results/wrr_review_completion_20261024/flow_comparators/`、`results/wrr_review_completion_20261024/zero_flow_missingness/`
- 边界：只读复核；未修改 SI、主文、代码、结果或冻结件；仅更新本审计文件。SI 的干净重建在 `/tmp/si_audit_build` 隔离副本中完成，未改写交付目录。
- 总体：**PASS**。原 T7 的 1 个 FAIL（three-output release rule 的 SI 引用无内容）已通过主文改为 “not in this Supporting Information” 关闭；原 T7 的来源行、S3 `uniform_exact`、S4 端点口径、S8 MAE 分母等 WARN 均已关闭。11 表均有显式 Source 行；本轮复核的数值全部与保存源一致；干净重建为 13 页、11 表、0 warning。没有需要保留的阻断性 WARN。

## 一、T7 问题关闭情况

| T7 项 | T9 复核证据 | 状态 |
|---|---|---|
| **FAIL**：three-output release rule 的 SI 引用无对应内容 | `body.tex:191,207` 现写 “we retain it only as a boundary result in the research repository, **not in this Supporting Information**”；SI 全文检索无 `three-output`、`release rule` 小节；`main.pdf` 文本同样如此。该 FAIL 通过删除 SI 引用关闭，不是新增 S12。 | 关闭 |
| **WARN**：S1/S3/S4/S5/S6/S7/S8/S10 缺显式来源路径 | S1–S11 每表均有 `Source:` 行；所列文件均存在（见第二节）。S2 原有来源保留，S9 现指向 `trend_signal.csv`，S11 明确无保存数值文件。 | 关闭 |
| **WARN**：S3 未列 `uniform_exact` | SI 第 40 行与 S3 表注（第 26 行）均说明其 archive-level 误差未保存，并给出 cohort RMSE 0.449（controlled）/0.135（calendar）与 55/8 sign flips；数值与 `trend_signal.csv` 一致。 | 关闭 |
| **WARN**：S4 把区间端点写成点估计范围 | S4 表注（第 20 行）明确 87.4–89.9% 是 4,096 draws 的**最小 lower / 最大 upper 端点**，对应点估计为 87.5–89.7%；复算一致。 | 关闭 |
| **WARN**：S8 MAE 分母/口径不清 | S8 表注（第 19 行）明确 log-MAE、valid-case 分母、availability 0.817、66,099/33,609 common cases、210 sites，以及主文 paired basis 的 0.0495/0.0745；逐格复算一致。 | 关闭 |
| **WARN**：S11 来源 | S11 表注明确 “Source: provider terms ...; no saved numerical file underlies this table.”；该表无数值结果，标为 N/A 合理。 | 关闭/N/A |

## 二、11 表来源行与存在性

| 表 | Source 行内容（摘要） | 文件存在 | 结论 |
|---|---|---|---|
| S1 | `results/wrr_final_revision_20261031/reference_year_sets.csv`、`retention_choice_counts.csv` | 是 | PASS |
| S2 | `results/ems_revision_20261102/trend_signal.csv` | 是 | PASS |
| S3 | `results/wrr_comprehensive_review_20261102/archive_level_comparisons.csv`；uniform-exact 值来自 `results/ems_revision_20261102/trend_signal.csv` | 是 | PASS |
| S4 | `results/wrr_adversarial_review_20261027/rank_convergence/rank_convergence_summary.csv` | 是 | PASS |
| S5 | `results/wrr_review_completion_20261024/evidence/H7_refit_scorecard_summary.csv`、`H7_refit_direction_stability.csv`、`target_windows/h7/full/trends_per_seed.csv`、`completion.json` | 是 | PASS |
| S6 | `results/ems_revision_20261102/flow_diagnostic.json`；`paper/wrr_tr/open_source_values.tex` | 是 | PASS |
| S7 | `results/wrr_review_completion_20261024/zero_flow_missingness/conditional_logit_summary.csv`、`cohort_counts.csv` | 是 | PASS |
| S8 | `results/wrr_review_completion_20261024/flow_comparators/scorecard.csv`、`paired_effects.csv`；计数来自 `status.json`、`design.json` | 是 | PASS |
| S9 | `results/ems_revision_20261102/trend_signal.csv`（805/818） | 是 | PASS |
| S10 | `gapbench/pyproject.toml`、`CITATION.cff`、`Dockerfile`、`gapbench/tests` | 是 | PASS |
| S11 | provider terms 与主文 software/data-availability statement；明确无保存数值文件 | N/A | PASS/N/A |

## 三、本轮变更点的数值复核

### 3.1 S3 的 `uniform_exact`

- `trend_signal.csv`：`crossed/uniform_exact` 的 `rmse=0.4492246021194079`、`n=805`、`sign_flips=55`；`calendar/uniform_exact` 的 `rmse=0.1354803620766518`、`n=818`、`sign_flips=8`。显示值为 **0.449 / 0.135** 与 **55 / 8**，舍入正确。
- 同一 CSV 的 `meta` 行明确写 “uniform_exact has no saved archive-level estimate error”，与 SI 第 40 行和 S3 表注的“不列表原因”一致。
- S3 表内 12 行（2 families × 3 schemes × 2 subsets）与 `archive_level_comparisons.csv` 的 `n`、`smaller_absolute_error`、`larger_absolute_error`、`numerically_equal`、`median_absolute_error_change`（4 位小数）完全一致，**0 mismatch**。

### 3.2 S4 的区间端点与点估计

- `rank_convergence_summary.csv` 在 `draws=4096` 的 6 个 method×construction 组合：
  - `coverage_min` 最小值 = 0.873641 → **87.4%**；`coverage_max` 最大值 = 0.898533 → **89.9%**。
  - `coverage_mean` 最小值 = 0.875453、最大值 = 0.897311 → 点估计 **87.5–89.7%**。
- S4 表注把 87.4–89.9% 明确定义为端点范围，并给出 87.5–89.7% 的点估计范围；与源文件逐值吻合，原先“端点被读成点估计”的 WARN 关闭。

### 3.3 S8 的 log-MAE、分母与 common-case 计数

- `scorecard.csv`（family=`crossed`）逐格复核，全部与 S8 显示值一致：
  - Historical D2：all `0.0499631898→0.0500`，danger `0.0742998634→0.0743`。
  - Historical multidonor Ridge：all `0.0563580730→0.0564`，danger `0.0829034313→0.0829`。
  - Single-donor Ridge：all `0.0602190798→0.0602`，danger `0.0896047036→0.0896`。
  - Observed days：all `0.0645684513→0.0646`，danger `0.1004182141→0.1004`。
  - Stochastic AR(1) median：all `0.0716059910→0.0716`，danger `0.1038408887→0.1038`。
  - MOVE.1：all `0.0733789839→0.0734`，danger `0.1061887439→0.1062`。
- availability：donor-dependent 行为 `0.8167327724`（all）与 `0.8171010406`（danger），显示 **0.817**；historical D2、historical multidonor Ridge、observed days 为 1.000。
- 计数：eligible `80,931`（all）/`41,132`（danger）；paired `n_common=66,099`（all）/`33,609`（danger）；`n_sites=210`；full cohort `255` sites、`8,999` complete climatic years、`134,925` cases、`17` HUC2 groups。均与 `scorecard.csv`、`paired_effects.csv`、`status.json` 一致。
- 主文 paired basis 的 D2 `right_mae_log`：all `0.0495395391→0.0495`，danger `0.0745124439→0.0745`；S8 表注已明确其与表内 per-estimator 值的差别。
- S8 表注明确 “log-MAE (mean absolute error in log-flow units) on each estimator's valid cases”、donor-dependent 的 valid-case 分母，以及 “paired log-MAE comparisons are restricted to these common cases”；原 WARN 关闭。

### 3.4 其余数值表复核

- **S1 PASS**：站点数 10/24/1/1/2/3（合计 41），组数 2/8/1/1/2/3（合计 17），中位参考年 16/13/14/11/14/12，总中位 14（7–16），有内部缺测年站点 24；与 `reference_year_sets.csv` + `retention_choice_counts.csv` 一致。
- **S2 PASS**：41 行、41 个唯一 station key；`n`、OLS slope/SE/p、Sen slope、MK p、H30 SD 在 5×10⁻⁴ 舍入容差下 **0 mismatch**；两处 `p<0.001` 的源值为 5.224×10⁻⁴ 与 7.336×10⁻⁴，支持该写法。
- **S5 PASS**：Panel A 的 8 行 danger-scope MAE/CRPS/tail CRPS/coverage 与 `H7_refit_scorecard_summary.csv` 一致（例如 calendar D2 0.494/0.365/0.065/0.874，crossed D2 0.348/0.257/0.046/0.892）；Panel B 的 2.94/4.85 与 20/20、20/20 与 `H7_refit_direction_stability.csv` 一致；Panel C 的 9 个 median/range 与 `trends_per_seed.csv` 一致（含 MCAR 81.2 [79.1,86.2]、strong heat 80.7 [78.9,87.4]、non-air 4.5 [3.8,5.6]）。`completion.json` 支持 20 seeds、540 outer fits。
- **S6 PASS**：0.164→0.158、0.147→0.156、93.9→93.7、88.0→87.6、738/17/807/820 全部与 `flow_diagnostic.json` 一致；“seven candidate providers” 由 `paper/wrr_tr/open_source_sensitivity_supporting.tex` 支持（`flow_diagnostic.json` 的 `source_files/open_source_supporting` 记录该文件）。
- **S7 PASS**：4 个 cohort 的 n/events/stations/groups 与 OR/CI 全部与 `conditional_logit_summary.csv` 一致；6,479 station-years/336 physical stations 与 `zero_flow_missingness/status.json` 一致，400 bootstrap draws 也有源文件支持。
- **S9 PASS**：805/818 与 `trend_signal.csv` 的 cohort n 一致；定义与主文一致。
- **S10 PASS**：`gapbench` 1.2.0、Python ≥3.10、NumPy ≥1.24、pandas ≥2.0、6 个公开函数、13 tests、20 年/4 gaps/16 complete/18 selected quickstart、Docker 3.11 + LightGBM 均实测吻合；`python -m pytest -q gapbench/tests` 为 **13 passed**；`scripts/check_version_consistency.py` 为 **RESULT: PASS**，仅保留历史 v1.0.0 tag 的 WARN。
- **S11**：无数值单元；访问/许可表述与主文一致；法律状态不在本次数值审计范围内独立核验。

## 四、编译与主文 SI 引用

- **干净重建：PASS**。在 `/tmp/si_audit_build` 副本执行 `latexmk -pdf -interaction=nonstopmode -halt-on-error supporting_information.tex`，rc=0；**13 页**，305,495 bytes；PDF 中 `Table S1:` 至 `Table S11:` 各出现 1 次，共 **11 表**；日志中 **0 LaTeX Warning / 0 Overfull / 0 Underfull / 0 undefined**。交付目录的 `supporting_information.log` 同样为 0 warning、13 页。
- **与交付 PDF 一致**：对干净重建 PDF 与 `paper/ems/supporting_information.pdf` 分别执行 `pdftotext`，文本 diff 为空（页面布局/文本一致；二进制哈希因构建时间不同而不同）。交付 PDF SHA-256：`95ab800c5b1b25531afbe17a7272a02b577ed526b1b5aa2023c40cd2348283b3`。
- **与 T8 台账的差异**：`FINAL_STATUS_ZH.md:106` 记录的 SI PDF 为 `4ee1857a32c47c122945f78b9b18ae87994c9338c0e967c7b6ea20298b5f7d1c`、302,377 bytes，对应修复前构建；当前交付 PDF 为 `95ab800...`、305,495 bytes（13 页不变）。若 T8 台账继续作为最终状态，应同步更新 §4 的该哈希/大小，并更新 §3.3 的 SI WARN 列表及 §6/§7 的相应状态。
- **H7 的 SI 引用：PASS**。`body.tex:125,167,205` 均指向 `Supporting Information Table~S5`；S5 完整支撑 2.94%/4.85%、20/20、81.2%/80.7%/4.5% 等表述。
- **three-output release rule：PASS（原 FAIL 关闭）**。`body.tex:191,207` 两处均写该规则只保留在 research repository、`not in this Supporting Information`；SI 无 three-output/release-rule 内容；`main.pdf` 文本确认一致。主文不再声称 SI 包含该内容，故原 FAIL 不再成立。
- 全文检索 `paper/ems/*.tex`，除上述 H7 三处与两处 three-output 说明外，没有其它指向 SI 内容的引用。

## 五、残余备注

- **剩余 FAIL/WARN：无。** 原 T7 的 FAIL 与来源/口径 WARN 均已关闭；本轮未发现新的阻断性来源或数值问题。
- 以下为非阻断的来源行可选补充（数值均已与保存文件核对无误，不改变 PASS）：
  1. S2 的 Group 列（如 `g0029`）来自 `results/wrr_final_revision_20261031/retention_choice_counts.csv` 的 `independence_group`，不在 S2 所引的 `trend_signal.csv` 中；该文件已在 S1 的 Source 行中列出，属跨表可追溯。若要求逐表自包含，可在 S2 表注补该路径。
  2. S7 表注中的 6,479 station-years / 336 physical stations 来自 `results/wrr_review_completion_20261024/zero_flow_missingness/status.json`（同步记录于 `results/ems_revision_20261102/flow_diagnostic.json`），未在 S7 的 Source 行点名；数值正确。若要求逐值自包含，可在 S7 表注补 `status.json`。
  3. S10 的 quickstart 具体值（20 年/4 gaps/16 complete/18 selected）在 `gapbench/examples/quickstart.py`；所引 `Dockerfile` 的 CMD 明确运行该脚本，测试套件另支撑 13 tests。若要求逐文件自包含，可在 S10 表注补 `gapbench/examples/quickstart.py`。
- **外部状态（非 SI 追溯问题）**：LUBW 法律/审稿访问、v1.2.0 tag、Zenodo DOI、program size/full-replay memory 仍为 pending，SI 已诚实标注；这些是 `FINAL_STATUS_ZH.md` 记录的投稿前外部 P0 项，不属于本次 SI 追溯修复范围，也不改变本审计的 PASS。

## 六、结论

- **SI 状态：PASS。** 11 表来源行齐全；S3 的 `uniform_exact` 缺失数据说明与保存值正确；S4 已区分区间端点与点估计；S8 已写清 log-MAE、paired common-case 分母、availability 与 66,099/33,609；所有复核数值与保存源一致；干净重建 13 页、11 表、0 warning。原 T7 的 FAIL 与 WARN 均已关闭，没有剩余阻断性 WARN。
