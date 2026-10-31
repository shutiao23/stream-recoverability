# 2026-10-31 模拟小修完成报告

本报告对应 [SIMULATED_WRR_REVIEW_ZH.md](SIMULATED_WRR_REVIEW_ZH.md) 提出的六项表达与交付修订。审核日期为 2026-10-31（北京时间）。本报告只记录当前工作区的实际改动、编译、测试和包验收入口；不把旧包的通过状态转写成当前通过，也不代填作者、许可或永久保存信息。

## 一、任务清单

| 审核项 | 本轮状态 | 证据 |
|---|---|---|
| 必须：同步 SI 与最终候选包 | 已完成当前源码→PDF→包→验收记录的绑定 | 主文 41 页、SI 102 页；SI 标题与 1981–2025 缺口行已进入 PDF；新包和外部验收记录见下 |
| 必须：限定主要收益来自控制缺口和有限记录目标 | 已完成 | 摘要明确 805 个前推控制缺口、30–90 天、有限记录 H30 斜率；第三个 Key Point 使用审核建议的表述 |
| 建议：限定 RMSE/中位斜率比例 | 已完成 | 结果节说明 59.1% 与 22.5% 是总体误差尺度对总体位置统计量；结论改用绝对 RMSE |
| 建议：补同数优化的局地异质性 | 已完成 | 讨论新增 41/41 站、17/17 群组同向，以及 CDF 14/41 站、3/17 群组和 Sxx 7/41 站、2/17 群组反向 |
| 建议：群组区间的条件范围 | 已完成 | 方法节明确区间条件于已保存年度预测、既定连接群组和当前比较规则，不含重训或规则选择不确定性 |
| 建议：凝练摘要和中心贡献 | 已完成 | 摘要由 246 词降至 218 词；讨论新增档案使用建议，并说明计算台账服务于该论证 |
| 投稿前：作者、合法审稿访问、永久保存 | 作者待办，未代填 | [POSTING_CHECKLIST.md](POSTING_CHECKLIST.md) 列出需作者确认的字段、材料路径和限制 |

## 二、正文修改

### 1. 摘要与 Key Points

摘要现在把比较对象写成“805 个前推控制缺口档案（30–90 天）上的有限记录 H30 斜率”，并直接报告绝对 RMSE：

> Recovering all supported years gives slope RMSE 0.170 °C per decade, versus 0.446 under warm-season screening; calendar-position controls that include the fixed complete years reduce it to 0.428 and 0.402.

摘要不再用“超过中位斜率一半”承担主要意义，也不再把 2,370 个来源案例、三个种子和两个地区端点范围逐项铺开；来源校准敏感性压缩为一句，并保留“500 条路径不证明收敛、不证明普遍优胜估计器”的边界。摘要经与 `scripts/930_delivery_consistency.py` 相同的词数口径计为 **218 词**。Plain Language Summary 也把年选择实验限定为 controlled 30–90-day gaps。

第三个 Key Point 改为审核建议的方向：

> Calendar-based selection reduced slope error at fixed counts in controlled gaps; recovery of all supported years reduced it further.

三个 Key Point 的长度分别为 103、136、131 字符，均低于 140 字符限制。

### 2. RMSE 与斜率中位数的比例

结果节保留原有数值作为量级背景，但明确其统计含义：

> This is 59.1% of the median complete-record slope, and all-year RMSE 0.1697 is 22.5% of it. These percentages compare an aggregate error scale with an aggregate slope location; they are not per-archive relative errors, do not imply a uniform warming underestimation, and are not ecological thresholds.

结论节不再使用“超过一半/低于四分之一”的比例表述，改为绝对 RMSE：

> Warm-season screening gives an aggregate slope RMSE of 0.4459 °C per decade; restoring all supported years reduces it to 0.1697.

### 3. 同数年份优化的局地异质性

讨论新增一段，直接区分总体改善与逐站/逐群组改善：

> In the saved 805-archive summaries, recovering all supported years improves on warm-season screening at every evaluated station (41/41) and connected group (17/17). The fixed-count calendar controls are less uniform: CDF is worse than warm-season screening at 14 of 41 stations and 3 of 17 groups, and Sxx at 7 of 41 and 2 of 17.

同段明确这些是同一已打开档案的事后描述，不是独立确认，也不能把“逐一删除群组后总体方向仍在”读成“每个群组本身都获益”。计数直接来自 [逐站与群组复核](/mnt/lzq-nvme2p4/lzq/stream-recoverability/results/wrr_multiview_review_20261031/time_station_group_heterogeneity.csv)。

### 4. 群组区间的条件范围

方法节在原有“探索性、点对点、未作多重调整”之后补充：

> They are conditional on the saved annual predictions, the predefined connected groups and the rules compared here; they do not include uncertainty from retraining source models or from selecting the rule.

这与审核要求一致：不增加全面嵌套重训，也不把现有区间改写成包含全部训练不确定性的确认性区间。

### 5. 中心贡献与档案使用认识

讨论首段新增：

> The practical implication is an archive-use recommendation: preserve directly observed windows as facts, state the finite period and year-selection rule for any slope, and report recovery and numerical uncertainty separately rather than certifying one annual value. The calculation ledger supports that argument rather than constituting the contribution.

中心贡献因此落在“筛选改变时间支撑、恢复与筛选误差竞争、直接事实与恢复值/斜率承担不同证据要求”这条主线上，而不是运行了多少验证模块。

## 三、SI 与版本同步

| 材料 | 本轮保存文件 | 当前源码隔离重编译 | 判断 |
|---|---:|---:|---|
| 主文 | 41 页 | 41 页 | 文本一致 |
| SI | 102 页 | 102 页 | 文本一致；标题与 1981–2025 缺口行进入 PDF |

当前保存 PDF：

| 文件 | 字节 |
|---|---:|
| `paper/wrr_tr/review_completion_article.tex` | 49,734 |
| `paper/wrr_tr/review_completion_article.pdf` | 571,673 |
| `paper/wrr_tr/review_completion_supporting.tex` | 15,354 |
| `paper/wrr_tr/review_completion_supporting.pdf` | 480,671 |

编译命令：

```bash
cd paper/wrr_tr
TEXINPUTS=.:../wrr/template: latexmk -pdf -silent -interaction=nonstopmode -halt-on-error review_completion_article.tex
TEXINPUTS=.:../wrr/template: latexmk -pdf -silent -interaction=nonstopmode -halt-on-error review_completion_supporting.tex
```

主文和 SI 均无未定义引用或重复标签。主文有 40 个不超过约 0.183 pt 的微小行盒警告，未发现内容裁切；这是排版警告，不是科学问题。SI 标题现为 “Supporting Information for ‘Retaining incomplete river-temperature records: time support of finite-record heat slopes’”；年度最长缺口表包含 “Observed 1981–2025 220 31 3 32.4 11.36%” 行。

包内还有一处不进入 PDF、但会随投稿材料一起提交的版本差异：封面信此前仍使用上一版标题 “temporal support and uncertainty in sustained-heat trends”。现已改为当前标题 “time support of finite-record heat slopes”，并把斜率收益明确限定在 805 个 30–90 天前推控制缺口档案上。封面信不参与两个 PDF 的编译，因此页码与 PDF 内容不变；候选包因该文件更新而重新生成。最终发布脚本现在同时检查封面信标题与这一控制缺口限定，避免再次出现“PDF 已改、附件未改”的错配。

## 四、最终候选包

最终包由当前工作区构建，而不是由旧包改名：

- 基础范围：旧 `dist/wrr_process_experiments_20261029.zip` 中的 3,313 个科学文件（论文、代码、配置、测试、结果和已许可数据），逐文件取当前工作区字节。
- 新增：本轮小修报告、投稿清单、审核报告、逐站/群组异质性 CSV、时间选集复核 CSV/JSON、测试与工作区一致性记录、最终发布构建器。
- 生成：`REVIEW_PACKAGE_README.txt`、`dependency_inventory.json`、`RELEASE_RECEIPT.json`、`CONTENT_MANIFEST.sha256`。
- 不包含：已确认的作者/基金/利益冲突声明（`metadata/` 中仅保留空模板）、LUBW 授权、受限个案证据、永久 DOI。旧包的 `validation.json` 和 `delivery_check.json` 不作为当前通过证据。

包级内容指纹、成员数和验收检查结果记录在包外：

- `dist/wrr_final_candidate_20261031.zip`
- `dist/wrr_final_candidate_20261031.manifest.json`
- `results/final_release_20261031/acceptance.json`

为避免正文重复机器指纹，本报告和投稿清单只列路径、页数/字节与验收结论；具体内容指纹保存在上述机器记录和包内内容清单中。

旧包保留原名，继续作为历史冻结版本；旧包过去通过验收与当前版本需要新验收可以同时成立。

## 五、验收执行

本轮实际执行：

- 15 个相关测试文件共 **94 项**，全部通过（0 失败、0 错误、0 跳过）。范围是当前评审与交付测试，不是全仓库测试。
- `scripts/930_delivery_consistency.py` 的保存结果转写检查通过；当前摘要 **218 词**。
- 主文与 SI 从当前源码重编译，页数与文本一致。
- 新包解压后执行 `scripts/930_delivery_consistency.py` 的转写/编译检查，通过。
- 新包解压后执行 `scripts/978_process_experiment_delivery.py` 的冻结输入重放，返回 `passed`：来源校准 2,370 案例/27 目标，年度选集 10,860 行/820 档案，当前观测 95 站/35 见证与 10 站/8 完整年，包内转写与编译通过。

测试记录：[targeted_tests_summary.json](/mnt/lzq-nvme2p4/lzq/stream-recoverability/results/final_release_20261031/targeted_tests_summary.json)。包级检查结果以包外 `results/final_release_20261031/` 下的验收记录为准。

## 六、作者、合法访问与永久保存

这些是作者提交事项，本轮没有代填、没有对外联系、没有虚构 DOI 或许可：

- 作者姓名、顺序、ORCID、单位、通讯作者、基金、CRediT、利益冲突和致谢仍为空模板：[metadata/submission_author_metadata.json](/mnt/lzq-nvme2p4/lzq/stream-recoverability/metadata/submission_author_metadata.json)。
- LUBW 重用/再分发条款、含 LUBW 正权案例的模型与个案派生文件的审稿访问仍需作者与提供方解决。
- 永久保存和可引用 DOI 尚未建立；`CITATION.cff` 只描述早期 v1.1.0 代码发布，不标识本次稿件修订。
- 当前可取得的材料路径是最终候选包、其内容清单、主文/SI PDF 和验收记录；这些路径已写入 [POSTING_CHECKLIST.md](POSTING_CHECKLIST.md)。

## 七、未声称的范围

本轮证明了：当前保存结果的算术核对、冻结输入后的采样/校准重放、当前环境下的隔离编译，以及新包与当前工作区逐文件一致。

本轮没有证明：干净环境依赖安装、全部原始提供方资料重建、所有模型从零训练、跨气候独立外部确认、作者/许可/永久保存已经完成。这些边界与 README、Open Research 和包 README 的表述一致。

## 八、对抗式复核后的收口

对“是否真的做完”再做一次反向检查，结论如下：

- 六项可执行小修已关闭；第七项作者、合法审稿访问和永久保存仍按作者待办处理，没有代填。
- 发布检查原先对若干科学表述只做抽样字符串检查；现在改为从包内异质性 CSV 重算 41/41、17/17、14/41、3/17、7/41、2/17，并逐项检查控制缺口范围、比例限定、条件区间和档案使用建议。
- 人读报告和投稿清单不再重复列内容指纹；机器可核验的指纹保留在 `acceptance.json`、包清单和 `CONTENT_MANIFEST` 中。删除这些机器记录会使“当前论文—当前包—当前验收”的绑定失效，因此没有随文档清理一起删除。
- 历史审稿报告仍保留审稿时状态（SI 101 页、旧包差异）；其后的修订结论以本报告和当前验收记录为准。
