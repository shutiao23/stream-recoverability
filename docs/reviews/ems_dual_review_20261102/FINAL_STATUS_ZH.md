# EMS 最终状态审计（T8）

- 日期：2026-11-02 19:16 UTC
- 审计对象：`paper/ems/`、`paper/ems/supporting_information.tex`、`paper/ems/si_tables/S1..S11`、`gapbench/`、`tests/test_ar1_bridge_nesting.py`、`.zenodo.json`、`pyproject.toml`、`CITATION.cff`、`results/final_release_20261101_r4/`、`results/wrr_final_revision_20261031/`
- 审计边界：只读复核；未修改论文、代码、bib、SI、元数据、结果或 r4 冻结件。只更新 `RESPONSE_ZH.md`、`PLAN_ZH.md` 并新增本文件。
- 审计时 HEAD：`bef47bf663927cc9726c4ec632ca750a3881d528`

## 1. 结论

**EMS 包已经是 submission-shaped，但不是 submission-ready。**

可以作为“可送审形态”的部分：主文与 SI 均可由 `latexmk + bibtex` 从源码重建；格式、摘要、Highlights、参考文献、图/表数量、SI 11 表、软件小库、随机数嵌套代码/测试、r4 冻结件均通过本轮复核。

仍不能投稿的原因：作者/单位/ORCID/基金/CRediT/COI 仍是占位符；LUBW 法律与审稿访问未落实；无 v1.2.0 tag、GitHub release 或 Zenodo DOI；program size/full-replay memory 未测；审稿人要求的缺失实验（流量、现代基线、多重插补、群组推断、强迫/稀缺/机制、计算成本、锁定确认）未完成。**在这些外部项和缺失实验完成前，不应把稿件描述为“已可投稿”。**

## 2. 已具备的投稿形态（本轮实测）

| 项目 | 结果 |
|---|---|
| 主文构建 | `latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex` exit 0；37 页；734,012 bytes |
| 主文 BibTeX | `bibtex main` exit 0；52 个 `\bibitem`；唯一 warning：`angelopoulos2024` 空页码（ICLR 预期，不编造页码） |
| 主文 LaTeX 日志 | 0 Warning / 0 Overfull / 0 Underfull / 0 undefined citation / 0 undefined reference |
| 主文结构 | 7 图（Figure 1–7）、4 表（Table 1–4）、52 条参考文献 |
| 摘要 | 源文件 185 词；PDF 文本 185 词；≤200 |
| Highlights | 5 条；76 / 76 / 79 / 80 / 83 字符（含空格，`--` 按 1 字符）；均 ≤85 |
| 禁用标识 | `??` 0；`(author?)` 0；`Water Resources Research` 0；`Key Points` 0；`Plain Language Summary` 0；`contact the authors` 0；`available on request` 0；`available upon request` 0；`agujournal` 0 |
| AGU 命中 | 大小写不敏感唯一命中是参考文献作者 `Agustí-Panareda`，不是 AGU 文档类/期刊身份 |
| SI 构建 | `latexmk -pdf ... supporting_information.tex` exit 0；13 页；302,377 bytes；0 Warning / 0 Overfull / 0 Underfull / 0 undefined |
| SI 表 | 11 表，S1–S11 连续，均有 caption、label 与 Source 行；T9 复核 PASS |
| SI 引用 | 主文 H7 三处（`body.tex:125,167,205`）均由 `Table S5` 支撑；`body.tex:191,207` 的 release rule 改为 `not in this Supporting Information`，SI 无 three-output/release-rule 小节；原 SI 审计 FAIL 关闭 |
| 版本 | `.zenodo.json`、根 `pyproject.toml`、`gapbench/pyproject.toml`、`CITATION.cff`、preferred-citation 均为 1.2.0 |
| 版本检查 | `python scripts/check_version_consistency.py` → `RESULT: PASS`；WARN 仅历史 v1.0.0 tag；INFO 为 DOI 未设置 |
| 软件包 | `gapbench` 1.2.0；MIT；6 个公开函数；24 个文件；270,461 bytes |
| 干净安装 | `/tmp/gapbench-final-venv`；`pip install -e "gapbench[test]"` exit 0；pytest 9.2.0 / numpy 2.4.6 / pandas 3.1.0 |
| quickstart | exit 0；20 年 7,300 日值；4 缺口；105/7,300 masked（1.44%）；16 完整年；CDF/Sxx 各选 18 年；S/R/E identity_ok=True |
| 库测试 | `python -m pytest -q gapbench/tests` → 13 passed in 0.13 s |
| 嵌套测试 | `python3 -m pytest -q tests/test_ar1_bridge_nesting.py` → 5 passed |
| r4 包 | 202,074,883 bytes；SHA-256 `cae27ba49a02f0e6da165868bdf78017245b6e1fe549a899b10f1955b4cb2d9e` |
| r4 CSV | `results/wrr_final_revision_20261031/` 11/11 CSV 与 `git cat-file HEAD:...`、`scientific_csv_identity.json` 的 r4 值一致 |
| r4 手稿 | article/supporting `.tex` 与 `.pdf` SHA-256 均与 `results/final_release_20261101_r4/acceptance.json` 一致 |
| CSV 修改 | 全仓库无 tracked CSV 修改；新增 EMS/综合审稿 CSV 位于新目录，不是对冻结 r4 科学 CSV 的改写 |

### 2.1 关键数字抽查

| 核对项 | 稿件值 | 保存源 | 结果 |
|---|---|---|---|
| 受控缺口 4 方案 RMSE / 符号翻转 | 0.446 / 0.428 / 0.402 / 0.170；53 / 51 / 42 / 16 | `results/wrr_final_revision_20261031/retention_family_summary.csv`（crossed） | 一致（n=805） |
| 经验日历 4 方案 RMSE / 符号翻转 | 0.114 / 0.098 / 0.086 / 0.067；3 / 5 / 4 / 0 | 同上（calendar） | 一致（n=818） |
| 档案方向计数 | 630/169/6；231/57/530；288 | `results/wrr_comprehensive_review_20261102/archive_level_comparisons.csv` | 一致 |
| 开放源敏感性 | 0.164/0.147 → 0.158/0.156；93.9→93.7；88.0→87.6 | `results/ems_revision_20261102/flow_diagnostic.json`；`paper/wrr_tr/open_source_values.tex` | 一致；738 pairs / 17 groups / 807 / 820 |
| 零流量 proxy OR | 0.594 [0.409,0.813]；0.474 [0.265,0.676]；0.969 [0.897,1.046] | `flow_diagnostic.json` | 四舍五入一致 |
| 流量 comparator MAE | MOVE.1 0.0734/0.0602；0.0734/0.0495；stochastic 0.0716/0.0495 | `flow_diagnostic.json`；`flow_diagnostic.csv` | 一致；66,099 共同案例 / 210 站 / 17 组 |
| H7 方向稳定性 | crossed 2.94%；calendar 4.85%；CRPS 与 tail CRPS 20/20 | `results/wrr_review_completion_20261024/evidence/H7_refit_direction_stability.csv` | 一致；crossed `median_gain=0.029414`，calendar `0.048454` |
| H7 Panel C | 81.2%（79.1–86.2）MCAR；80.7%（78.9–87.4）strong heat；4.5%（3.8–5.6）non-air | `results/wrr_review_completion_20261024/target_windows/h7/full/trends_per_seed.csv` | 一致；trend-target missingness 分量，不是 H7 年度覆盖 |

未发现数值 mismatch。两点限定：

- H7 的 2.94% 是 crossed 家族 danger-case 值，4.85% 是 calendar 家族；正文与 SI 均已写明两个家族。
- 摘要中的 “20 of 96 long-record stations” 本轮没有独立重算；它不在本次指定的五个关键抽查源内。不要把它说成已由 T8 复算。

## 3. 仍阻塞投稿的事项

### 3.1 外部 P0：BLOCKED

| 项 | 现状 | 关闭条件 |
|---|---|---|
| 作者/单位/ORCID/基金/CRediT/COI | PDF 仍有 26 处占位符：18 `[AUTHOR TO CONFIRM]`、1 email、1 `[AFFILIATIONS TO CONFIRM]`、2 `[EDITORIAL/LEGAL CONFIRMATION REQUIRED]`、4 `[PENDING]` | 填完整作者信息、单位、ORCID、基金号、CRediT 角色、COI；删除全部占位符 |
| LUBW 法律/审稿访问 | `software_availability.tex` 与 SI S11 均写 reviewer access pending；法律确认未完成 | 取得 provider 许可与 editorial/legal 确认，或明确可接受的替代访问方案 |
| v1.2.0 tag / GitHub release / Zenodo DOI | 仅历史 `v1.0.0` tag/release；`git ls-remote --tags` 与 `gh release list` 均无 v1.2.0；无 DOI | 创建 tag/release/DOI；更新 `.zenodo.json` 与 `CITATION.cff` 并记录 package hash |
| program size / full-replay memory | `software_availability.tex` 仍 `[PENDING]` | 从 release archive 实测并填入 |
| 永久保存 | `paper/ems/` 与 `gapbench/` 当前是 git 未跟踪目录（`?? paper/ems/`、`?? gapbench/`） | 提交到版本库，形成可归档 commit/tag；当前 HEAD 不包含这些交付物 |

### 3.2 缺失实验：NOT DONE / PARTIAL

| 项 | 状态 | 说明 |
|---|---|---|
| A3 流量一阶控制 | **PARTIAL** | 只有 zero-flow proxy 与 opened flow comparator；未补 34 站 FOEN/GKD 日流量，未重训 air2stream-8，未加流量特征/流域属性分层 |
| B4 现代基线 | **NOT DONE** | Kalman/imputeTS、missForest、BRITS、SAITS 未在同一 805/818 mask 上运行 |
| B5 多重插补 | **NOT DONE** | 当前秩耦合不是联合后验；未按 Rubin 规则合并 |
| B6 群组推断 | **NOT DONE** | 未跑 wild cluster bootstrap 或 station/group 随机效应；group bootstrap 仍偏窄 |
| B8 计算成本 | **NOT DONE** | 无 wall-clock/CPU/memory；只有 budget 数值敏感性 |
| A5 强迫代表性 | **NOT DONE** | E-OBS/ERA5-Land 强迫敏感性未做；格点-站点高程差未报告 |
| A6 资料稀缺 | **NOT DONE** | 历史长度 3/5/10 年截短与邻站 0–1 消融未做 |
| A8 缺测机制 | **NOT DONE** | 未估计 missingness ~ air/flow/season 的经验模型 |
| 锁定确认 | **BLOCKED** | 无 OSF 预登记；无新站点一次性确认运行；不能用内部诊断替代 |
| B9 泄漏控制/元数据 | **PARTIAL** | 有 HUC17/NVE 同区域组保留与 strict-region 敏感性说明；无 3,320 个 `design.json` 重生成记录、leakage checklist、D2 model card |
| B10 发布规则 | **PARTIAL** | 已明确不推荐、只在 research repository 保留为 boundary result；未做 risk–coverage/conformal risk control |

### 3.3 非阻断 WARN

- **T9 已关闭的 SI WARN**：S1–S11 均加入 Source 行；S3 注明 `uniform_exact` 的 archive-level 误差未保存（给出 0.449/0.135 与 55/8 flips）；S4 区分 4,096 draws 的区间端点（87.4–89.9%）与点估计（87.5–89.7%）；S8 明确 log-MAE、paired common-case 分母 66,099/33,609、210 站/17 组。`SI_AUDIT_ZH.md` 状态为 PASS。
- **参考文献**：52 条；44 个 DOI 可解析；0 未解析/0 重复/0 孤立；0 `(author?)`；0 undefined citation。剩余 WARN 是 8 个不发行 DOI 的 venue 条目；`diaz2025` 摘要级核验是残余风险，不是 FAIL；`vanvliet2011` 页码与 `gibbs2023` key/year 注释已按审计修正。
- **研究测试环境**：`tests/test_ar1_bridge_nesting.py` 需要 PyYAML 等研究依赖；在只有 `gapbench[test]` 的 clean venv 中 collection 会失败（`No module named 'yaml'`），因此该测试在仓库环境运行并通过 5/5。这不是 `gapbench` 库测试失败。
- **仓库根同名目录**：在仓库根目录直接 `python -c "import gapbench"` 会优先命中 `gapbench/` 这个 namespace 目录，因而没有 `__version__`；从其他目录导入安装包时 `gapbench.__version__ == "1.2.0"`。这是运行路径问题，不影响安装/测试，但发布说明应避免在仓库根做导入检查。
- **CITATION.cff 的 `date-released`**：当前为 `2026-11-02`，而仓库尚无 v1.2.0 tag/GitHub release/Zenodo DOI。该字段是 CFF 的版本日期，不等同于 release 声明，且 `notes` 已明确写无 release/DOI；但在正式 mint DOI 前，建议把它与 release 日期对齐，避免读者误读。
- **PDF 字节哈希**：磁盘 PDF 与干净重建的页数/文本一致，但 SHA-256 不同（构建元数据差异）；交付哈希应使用磁盘文件，不要用重建哈希替代。

## 4. 精确路径与哈希

| 对象 | 路径 | SHA-256 / 身份 |
|---|---|---|
| EMS 主文 PDF | `paper/ems/main.pdf` | `234195dbbd9adb91b499a47d56146b3307628b4425dc92e3d511c7e8205efc33`；37 页；734,012 bytes |
| EMS SI PDF | `paper/ems/supporting_information.pdf` | `4ee1857a32c47c122945f78b9b18ae87994c9338c0e967c7b6ea20298b5f7d1c`；13 页；302,377 bytes |
| r4 冻结包 | `dist/wrr_final_candidate_20261101_r4.zip` | `cae27ba49a02f0e6da165868bdf78017245b6e1fe549a899b10f1955b4cb2d9e`；202,074,883 bytes |
| r4 科学 CSV 身份 | `results/final_release_20261101_r4/scientific_csv_identity.json` | 11 个 CSV，r2/r3/r4 全部 `all_identical=true` |
| r4 验收记录 | `results/final_release_20261101_r4/acceptance.json` | package / article / supporting / cover letter / tests 哈希 |
| 软件库 | `gapbench/` | `gapbench` 1.2.0；270,461 bytes；24 files；Python ≥3.10 |
| 软件源码树哈希 | `gapbench/gapbench/*.py` 按路径排序后的 `sha256sum` 汇总 | `6c89182abed7772dad3417fe90bb26ac8ecd9897c085df0a8dfd2db014ebc24f` |
| EMS TeX/Bib/TXT 源文件树哈希 | `paper/ems/*.tex`、`*.bib`、`*.txt` 按路径排序后的 `sha256sum` 汇总 | `47e472b2499d52a6730ca8102bb66d1f526060d5dc2c2a0e5c6c1074dc9168ae` |
| git HEAD | 仓库 | `bef47bf663927cc9726c4ec632ca750a3881d528`；不包含未跟踪的 `paper/ems/` 与 `gapbench/` |

说明：源文件树哈希的精确复算命令见第 5 节。它是审计时的快照；任何源文件改动都会改变该值。

## 5. 证据命令

### 5.1 主文与 SI 重建（隔离副本，不改交付目录）

```bash
rm -rf /tmp/ems_clean
mkdir -p /tmp/ems_clean/paper
cp -a paper/ems /tmp/ems_clean/paper/ems
ln -s "$PWD/paper/wrr_tr" /tmp/ems_clean/paper/wrr_tr
cd /tmp/ems_clean/paper/ems
rm -f main.aux main.bbl main.blg main.fdb_latexmk main.fls main.log main.pdf main.spl \
      supporting_information.aux supporting_information.fdb_latexmk \
      supporting_information.fls supporting_information.log supporting_information.pdf supporting_information.spl
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
bibtex main
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
latexmk -pdf -interaction=nonstopmode -halt-on-error supporting_information.tex

pdfinfo main.pdf | egrep 'Pages|File size'
pdfinfo supporting_information.pdf | egrep 'Pages|File size'
grep -c '\\bibitem' main.bbl
for f in main.log supporting_information.log; do
  echo "$f"
  grep -c 'Warning' "$f"; grep -c 'Overfull' "$f"; grep -c 'Underfull' "$f"; grep -ci 'undefined' "$f"
done
```

### 5.2 PDF 文本检查

```bash
sha256sum paper/ems/main.pdf paper/ems/supporting_information.pdf
# 234195dbbd9adb91b499a47d56146b3307628b4425dc92e3d511c7e8205efc33  paper/ems/main.pdf
# 4ee1857a32c47c122945f78b9b18ae87994c9338c0e967c7b6ea20298b5f7d1c  paper/ems/supporting_information.pdf

pdftotext paper/ems/main.pdf /tmp/ems_main.txt
pdftotext paper/ems/supporting_information.pdf /tmp/ems_si.txt

for p in '??' '(author?)' 'Key Points' 'Plain Language Summary' \
         'Water Resources Research' 'contact the authors' \
         'available on request' 'available upon request'; do
  printf '%s: ' "$p"; grep -oF "$p" /tmp/ems_main.txt | wc -l
done
grep -o 'Table S[0-9]*:' /tmp/ems_si.txt | sort -u
```

### 5.3 摘要与 Highlights

```bash
python3 - <<'PY'
import re
h=open('paper/ems/highlights.txt').read().splitlines()
for i,l in enumerate([x for x in h if x.strip()],1):
    s=l.strip().lstrip('\\item').strip().replace('--','-')
    print(i,len(s))
a=open('paper/ems/abstract.tex').read()
a=re.sub(r'\\[a-zA-Z]+\*?(\\[[^]]*\\])?(\\{[^{}]*\\})?',' ',a)
a=re.sub(r'[{}$]',' ',a)
print('abstract source words',len(a.split()))
PY
```

### 5.4 版本一致性

```bash
python scripts/check_version_consistency.py
grep -n '^version' pyproject.toml gapbench/pyproject.toml
grep -n '"version"' .zenodo.json
grep -n '^version:\|version: "' CITATION.cff
git tag --list
git ls-remote --tags origin
gh release list -R shutiao23/stream-recoverability
```

期望：`RESULT: PASS`；版本均 1.2.0；只有历史 `v1.0.0`；无 v1.2.0 release/DOI。

### 5.5 干净安装与测试

```bash
rm -rf /tmp/gapbench-final-venv
python3 -m venv /tmp/gapbench-final-venv
/tmp/gapbench-final-venv/bin/python -m pip install -q --upgrade pip
/tmp/gapbench-final-venv/bin/python -m pip install -e "gapbench[test]"
/tmp/gapbench-final-venv/bin/python gapbench/examples/quickstart.py
/tmp/gapbench-final-venv/bin/python -m pytest -q gapbench/tests

python3 -m pytest -q tests/test_ar1_bridge_nesting.py
```

期望：安装 exit 0；quickstart exit 0；`13 passed`；嵌套测试 `5 passed`。

### 5.6 r4 冻结件

```bash
sha256sum dist/wrr_final_candidate_20261101_r4.zip
# cae27ba49a02f0e6da165868bdf78017245b6e1fe549a899b10f1955b4cb2d9e

git status --porcelain -- results/wrr_final_revision_20261031/
# 空

python3 - <<'PY'
import hashlib, subprocess, pathlib
files=sorted(pathlib.Path('results/wrr_final_revision_20261031').glob('*.csv'))
print('count',len(files))
ok=True
for p in files:
    cur=hashlib.sha256(p.read_bytes()).hexdigest()
    head=hashlib.sha256(subprocess.check_output(['git','cat-file','-p',f'HEAD:{p.as_posix()}'])).hexdigest()
    ok &= cur==head
    print(('OK' if cur==head else 'DIFF'),p.name,cur)
print('ALL_MATCH_HEAD',ok)
PY
```

### 5.7 源文件树哈希

```bash
(cd paper/ems && find . -type f \( -name '*.tex' -o -name '*.bib' -o -name '*.txt' \) -print0 \
  | sort -z | xargs -0 sha256sum | sha256sum)
# 47e472b2499d52a6730ca8102bb66d1f526060d5dc2c2a0e5c6c1074dc9168ae

(cd gapbench && find gapbench -type f -name '*.py' -print0 \
  | sort -z | xargs -0 sha256sum | sha256sum)
# 6c89182abed7772dad3417fe90bb26ac8ecd9897c085df0a8dfd2db014ebc24f
```

## 6. 交接清单

投稿前必须完成：

- [ ] 填作者、单位、ORCID、基金、CRediT、COI、AI 声明；删除 26 处占位符。
- [ ] 完成 LUBW 法律确认与审稿访问；更新 `software_availability.tex`、SI S11 和 `DATA_RIGHTS.md`。
- [ ] 把 `paper/ems/`、`gapbench/`、`tests/test_ar1_bridge_nesting.py`、`docs/software/` 提交到版本库；创建 `v1.2.0` tag 和 GitHub release；mint Zenodo DOI；更新 `.zenodo.json`/`CITATION.cff`；记录 release package hash。
- [ ] 测量 program size 与 full-replay memory，填入 `software_availability.tex`。
- [ ] 完成缺失实验：A3 34 站日流量与 air2stream-8；B4 Kalman/imputeTS、missForest、BRITS/SAITS；B5 联合模型多重插补 + Rubin；B6 wild cluster bootstrap/混合效应；B8 wall-clock/CPU/memory；A5 E-OBS/ERA5-Land；A6 历史长度/邻站消融；A8 缺测机制经验模型。
- [ ] 完成锁定确认：OSF 预登记 + 新站点一次性运行；在完成前保持 **BLOCKED**。
- [ ] 清理非阻断 SI WARN：每表来源行、S3 `uniform_exact`、S4 端点表述、S8 MAE 分母；把 H7 保持为 S5 稳健性检查，不作 H30 确认。
- [ ] 在修改后重新构建主文/SI，重新记录 PDF 哈希与页数；不要把重建哈希当作交付哈希。
- [ ] 不声称开放源模型已获法律 clearance，不声称 H7 确认 H30，不声称已完成锁定确认，不声称已有 DOI/tag/release。

## 7. 一句话状态

**格式、SI、软件库和冻结件已经到位；作者/法律/DOI/审稿访问与缺失实验仍未到位。当前只能称 submission-shaped，不能称 submission-ready。**

## 8. T10 提交审计与收尾（2026-11-03）

对未提交的全部 EMS 交付物做对抗式复核，修复缺陷并完成本地可完成的 PENDING 项。

### 8.1 审计发现并修复

- `tests/test_submission_admin_packets.py::test_zenodo_json_matches_title_and_has_no_doi` 仍断言旧标题（Stream-Temperature Gap Recoverability…）与 1.1.0 版本；与已改为 gapbench 1.2.0 的 `.zenodo.json` 冲突，是全库唯一失败。已更新断言，全库测试恢复零失败。

### 8.2 B6 wild cluster bootstrap（新增，SI S12）

- 脚本：`scripts/986_wild_cluster_bootstrap.py`；测试：`tests/test_wild_cluster_bootstrap.py`（5 项，含 300 次模拟覆盖率检验，实测覆盖在 [0.88,1.0]）。
- 方法：对每个配对 RMSE 差统计量，取其影响函数的群组均值，用 Rademacher 与 Webb 六点符号重加权（10,000 抽取，seed 20261102），17 个连接群组从不重抽样；同时给出配对均方误差差的 wild 区间。群组重抽样列直接复用冻结区间。
- 结果（表 `wild_cluster_bootstrap.csv`，10 行）：
  - 中位 wild/群组重抽样宽度比 **1.02**；全保留对比约 1.24，估计器对比 0.90–0.99。
  - 日历 CDF：群组重抽样 [−0.0451, +0.0004]、wild [−0.0366, +0.0065]，**均含零**（结论不变）。
  - 日历 Sxx 与全保留、控制缺口全部主要方向在两种程序下一致（均不含零）。
  - 唯一方法依赖对比：日历 D2−经典法，群组重抽样 [−0.0028, +0.0178] 含零，wild Rademacher [+0.0011, +0.0197] 与 Webb [+0.0011, +0.0197] 不含零；正文与 SI S12 均按方法依赖表述，不升级为稳定排序。
- 正文新增一句引用（body.tex 区间段），SI 新增 S12 表与说明节。

### 8.3 B8 程序规模与运行成本（实测填充 PENDING）

- 程序规模：24 文件、1,012 行 Python、264 KiB 未压缩（23 KiB zip，剔除缓存）。
- 单核实测：quickstart 0.13 s / 35 MiB 峰值驻留；`983` 完整包内重放（1,623 档案、8,115 策略行）9.7 s / 289 MiB。
- `software_availability.tex` 与 SI S10 的 `[PENDING]` 已全部替换为上述实测值（DOI 项仍为 PENDING，属外部依赖）。

### 8.4 发布与元数据

- `CITATION.cff`（date-released 2026-11-03、release URL 标识符）、`.zenodo.json` notes、SI S10、软件可用性声明、根 README 统一为：GitHub release v1.2.0 标记本版本，Zenodo DOI 仍未 mint。
- 本轮提交后创建 `v1.2.0` annotated tag 与 GitHub release；`scripts/check_version_consistency.py` 的 v1.0.0 历史 WARN 随之消失。DOI 仍为外部依赖，不得写成已有。

### 8.5 构建复核（更新后）

| 项 | 结果 |
|---|---|
| 主文 | 37 页；734,937 bytes；0 Warning / 0 Overfull / 0 Underfull / 0 undefined；52 refs |
| SI | 15 页；12 表（S1–S12）；0 Warning / 0 Overfull / 0 Underfull / 0 undefined |
| 禁用标识 | `??`、`(author?)`、Key Points、PLS、WRR、contact/on request 均 0 |
| 全库测试 | 本轮修复后 0 失败；新增 wild bootstrap 5 项、EMS 收尾后待最终复跑确认 |
| 版本检查 | RESULT: PASS（1.2.0 一致） |

### 8.6 仍未完成（与 3.1/3.2 相同）

作者/单位/ORCID/基金/CRediT/COI；LUBW 法律与审稿访问；Zenodo DOI；A3/B4/B5/A5/A6/A8 与锁定确认。这些不是本地代码可替代的，状态保持不变。

## 9. v1.2.0 发布证据（2026-11-03）

| 对象 | 值 |
|---|---|
| 提交 | `e72970b52d`（`feat(ems): add EMS submission package, gapbench 1.2.0 and wild cluster bootstrap`），已推送 `origin/main` |
| 标注 tag | `v1.2.0`，指向 `e72970b52d`，已推送 |
| GitHub release | https://github.com/shutiao23/stream-recoverability/releases/tag/v1.2.0 |
| Release 资产 | `gapbench-1.2.0.zip`，SHA-256 `29752080915f3a536797a596528cccc82621bbfccd2c53457bcd70c078178e87`（23,831 bytes，剔除 `__pycache__`/`*.pyc`/egg-info） |
| 版本检查 | `scripts/check_version_consistency.py` → `PASS: latest git tag v1.2.0 matches package version`；唯一 INFO 为 DOI 未设置（属实） |
| Zenodo DOI | 仍未 mint，属外部依赖；`CITATION.cff` 的 `doi` 保持未设置 |
| CI | 按既定要求，推送前临时禁用；该提交无 workflow run；工作流已恢复 active |

`paper/ems/`、`gapbench/`、`docs/software/`、`tests/test_ar1_bridge_nesting.py`、`tests/test_wild_cluster_bootstrap.py` 与 r4 证据目录现已进入版本库，"永久保存需先提交"这一阻断项的 Git 部分关闭；Zenodo/机构归档仍待作者完成。

## 10. T11 第二轮对抗审计修复（2026-11-03）

对应 [ADVERSARIAL_AUDIT_20261103_ZH.md](ADVERSARIAL_AUDIT_20261103_ZH.md)。审计发现的 11 项中，本地可完成的全部关闭：

### 10.1 统计实现缺陷（两项均修复并有回归测试）

- **wild bootstrap 影响函数未中心化**：修正为 (a-mean a)/(2R_A) - (b-mean b)/(2R_B)，运行时断言均值为 0；
  重生成全部结果。中位宽度比 1.02→**0.88**；方法依赖对比 1 个→**2 个**（日历 uniform-exact、日历 D2-经典法）。
  正文 body:57、SI S12 表与说明、`tests/test_wild_cluster_bootstrap.py`（6 项：中心化断言、总体真值覆盖率
  [0.90,0.99]、三明治尺度宽度 [0.7,1.3]、保存值断言）全部同步。方法表述改为 Kline--Santos 型 score
  bootstrap（不声称有限样本覆盖保证）。
- **Hamed--Rao 方差修正写反**：重写为先 Sen 斜率去趋势、秩残差 ACF、仅 5% 显著滞后、Var* = Var(S)·C；
  与 pyMannKendall 1.4 `hamed_rao_modification_test` 在全部 41 站逐站一致（p<0.05 共 **6/41**，2 站修正因子非正）。
  `results/ems_revision_20261102/trend_signal.{json,csv}` 重算，新增 `tests/test_slope_signal_audit.py`（4 项）。

### 10.2 方法描述与代码/数据对齐（5 处）

- 掩膜设计如实描述：每年 0.35 概率、7 年 burn-in、2010 前推起点、中位 36% 年份被掩、无全掩档案；
- 受控缺口季节性如实描述：3,711 段中 23.4% 与 6--8 月不重叠、21.1% 早于第 120 天，"controlled" 指长度而非季节，
  摘要与正文 "summer gaps" 相应改为 controlled gaps（仅引言动机句保留 summer）；
- "Mondrian CQR" 改为按难度类分层的分位数经验偏移校准（与 CQR 类似但无有限样本保证，列出四点原因），两处；
- "counter-based RNG" 改为 `SeedSequence.spawn` + PCG64 的每路径独立流（正文与实现一致，salmon2011 引用删除）；
- 摘要 "框架由 gapbench 实现" 改为"原语 + 日期感知基准层发布为 gapbench，完整流水线在公开研究包"，
  CITATION.cff/.zenodo 描述同步（含新增 API）。

### 10.3 稿件内部清理

- 删除主文流量对照表（USGS log-flow 目标，非水温），改为指向 SI S8 的一句话并明确"不同目标变量"；
- 删除两段重复且未定义的"三输出发布规则"段（保留泄漏分类法/模型卡引用一句并入群组推断段）；
- 符号统一：所选年集 S→A（w_S→w_A、S_{xx,S}→S_{xx,A}），h 与 e 在正文定义，日水温 Y_{yd}→T_{yd}；
- 经典法命名统一为 "the stochastic comparator (calibrated stochastic regression)"，首现定义；
- 正文新增 D2 与经典法"可用性 vs 精度"段（0.147 vs 0.164；82/820、119/820 不可用子集上 D2 RMSE 0.244/0.093），
  决策表新增对应行；决策表 "summer gap" 行改措辞；
- Fig.4 caption 定义 offline（1981--2025 全窗掩膜）与 forward（2010 起）模式；
- Fig.1 以 `paper/ems/figures/fig1_ems.dot/pdf` 重绘，删除 "release tests/release-then-trend" 等 WRR 术语，
  caption 同步为 0.35 概率设计；
- 删除 "local review candidate" 与 "no new experiment..." 内部用语。

### 10.4 新指标（P1-2，全部由冻结表复算）

- 总趋势不确定性膨胀 sqrt(1+mean((e/SE)^2))-1：受控族筛选 21.5% vs 重建 3.7%；日历族 1.8% vs 0.5%
  （摘要、结果、结论、表 trend_signal_cohorts 新增 Infl. 列）；
- 符号翻转 |t| 分层：受控筛选 43/53、全保留 16/16 发生在 |β|<1 SE 站；|t|≥2 的 3 站零翻转（正文与表 Weak 列）；
- 日历族限定 288 个"年集确实改变"档案：筛选 RMSE 0.191（中位 0.151 / P90 0.559）vs 全保留 0.112（0.026 / 0.225）；
- 200 个 FOEN（瑞士）日历档案全部零筛选误差（正文与表注）。

### 10.5 仓库门面与工程

- LICENSE 改为纯 MIT 文本（GitHub 识别），数据范围说明移入 DATA_RIGHTS.md；
- `metadata/data_rights.csv` 审稿访问路径从 AGU/GEMS 改为 provider/EMS 适用表述；
- CI：新增 `workflow_dispatch` 触发与独立 gapbench job（Python 3.10--3.13，仅 numpy+pytest）；
- README 重写为 gapbench/EMS 入口，WRR r4 历史移至 `docs/history/wrr_r4_candidate.md`；
- gapbench 升级 **1.3.0**：新增 `annual_h30`（日期感知、闰年、L_y、完整性标记）、`generate_gaps`（每年独立流的
  可复现受控缺口设计）、三条基线（气候态、线性插值、AR(1) 路径桥）、`run_benchmark`；删除未用 pandas 依赖；
  quickstart 改为按不完整年报告 L_y 与真值对比 + 基线基准；22 项测试全过；CHANGELOG 新增；
- 软件可用性：开发者联系方式字段补充（占位）；quickstart 描述与实际一致；Docker 措辞移除；
- 版本元数据五处一致 1.3.0，v1.3.0 tag/release（sdist+wheel 资产）随本轮创建；Zenodo DOI 仍为外部依赖。

### 10.6 AI 披露（政策对齐）

- 声明移到参考文献正上方（software availability 之后、bibliography 之前），并如实扩展：Cursor 共同署名提交、
  agent 辅助代码、AI 辅助起草待作者改写、无生成图像；
- Methods 新增 "Use of AI-assisted tools in code development" 段（置于 Verification 小节），说明验证方式
  （测试规模、独立复算、冻结输入脚本）。

### 10.7 仍未完成（外部/需新数据）

与审计一致：作者/单位/ORCID/基金/CRediT/COI；LUBW 法律与审稿访问（开放源转主分析为候选方案，需重跑主表）；
Zenodo DOI；A3 流量与 air2stream-8；A5/A6/A8；B4 现代基线；B5 联合模型多重插补；锁定确认；图 7 移 SI 与
27 例 pathwise 预算重跑（本地可做但属 P1 呈现项，未在本轮完成）。
