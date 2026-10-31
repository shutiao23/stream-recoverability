# WRR 稿件格式与字体检查（2026-10-26）

**后续版本说明：**本报告对应2026-10-26的历史稿件，不是2026-10-27修订后的页数、图件或测试结论。当前稿件与测试状态以 `results/wrr_review_response_20261027/audit/` 及重新编译的PDF为准。

检查对象：`paper/wrr_tr/review_completion_article.tex` 及其编译产物 `review_completion_article.pdf`（32 页）。
模板：官方 `agujournal2025.cls`（AGU/WRR），`draft,linenumbers` 选项，Letter 纸，正文双倍行距并带行号。
本报告只记录可重复的机械检查与逐页目视检查；不代替期刊 production 的最终排版。

## 1. PDF 级检查

| 检查 | 结果 | 证据 |
|---|---|---|
| 页数 | 32 | `pdfinfo` |
| 页面尺寸 | 612 × 792 pt（8.5 × 11 in） | `pdfinfo` |
| PDF 版本 | 1.7 | `pdfinfo` |
| 版心宽度 | 32.25 pc = 5.375 in | `agujournal2025.cls` 第 405 行 |
| 字体嵌入 | 全部嵌入（0 个未嵌入） | `pdffonts` |
| 栅格图 | 0（所有图均为矢量 PDF） | `pdfimages -list` |
| 未解析引用 | 0（无 `??`） | `pdftotext` |
| 最严重 overfull box | 0.18 pt | `review_completion_article.log` |
| BibTeX warning | 0 | `review_completion_article.blg` |
| 参考文献条目 | 37 | `.bbl` 中 `\bibitem` 计数 |
| 摘要长度 | 219 words（< 250） | 源码计数 |
| Key points | 3 条，111 / 121 / 120 字符（< 140） | 源码计数 |

正文使用模板的 10 pt 字号、20 pt 基线（draft 双倍行距）；标题、节标题、图表标题均由模板控制。已启用 `linenumbers`，行号位于左侧页边距，不覆盖正文、表格或图件。

## 2. 图件检查

| 图 | 来源 | 介质 | 最小字号（印刷尺寸） | 目视检查 |
|---|---|---|---|---|
| Fig. 1 证据架构 | `figures/architecture/fig1_study_architecture.drawio` | draw.io → PDF，矢量 | 约 6.0 pt | 第 6 页：框、箭头、文字无重叠 |
| Fig. 2 观测纪录反证 | `figures/simple_research/01_observed_records.pdf` | Python → PDF，矢量 | 约 6.0 pt（轴刻度），正文约 8 pt | 第 14 页：图例不压点，双面板不重叠 |
| Fig. 3 年度估计比较 | `02_annual_comparators.pdf` | Python → PDF，矢量 | 约 6.0 pt | 第 26 页：误差棒、标签、虚线不重叠 |
| Fig. 4 整档案因子分解 | `03_archive_factorial.pdf` | Python → PDF，矢量 | 约 6.0 pt | 第 28 页：对数轴改为 0.01/0.1 十进制标签，无指数级小字 |
| Fig. 5 联合不确定性 | `04_joint_uncertainty.pdf` | Python → PDF，矢量 | 约 6.0 pt | 第 28 页：图例在轴内/轴外均不压线 |
| Fig. 6 释放系统设计 | `figures/architecture/fig2_release_system.drawio` | draw.io → PDF，矢量 | 约 6.0 pt（pass/fail 标签），正文约 8 pt | 第 29 页：三条路径、Tier 框、底部规则不重叠 |
| Fig. 7 三类输出 | `05_output_boundaries.pdf` | Python → PDF，矢量 | 约 6.0 pt | 第 29 页：右图标签已缩短，无相互覆盖 |

说明：
- draw.io 源文件与导出说明见 `paper/wrr_tr/figures/architecture/README.md`；PDF 由 draw.io Desktop v32.6.1 导出，页面尺寸即印刷尺寸。
- 结果图由 `scripts/524_research_report.py` 生成，设计宽度 7.2–7.4 in，插入时缩放到 5.375 in，字号约 8 pt；轴刻度最小约 6 pt。
- 所有图均无栅格化文字；`pdffonts` 只显示 LiberationSans（图）与 Computer Modern（正文/数学）。
- 逐页检查了第 4、6、14、26、28、29、30 页；未发现文字相互覆盖、裁切或越出页面。

## 3. 表格检查

| 表 | 处理 | 结果 |
|---|---|---|
| Table 1 证据映射 | 8 pt，四列 ragged-right，`\tabcolsep=4pt` | 页 4，完整落在版心内；无 overfull |
| Table 2 整档案趋势误差 | 自然宽度，9 pt | 页 26，列对齐正常 |
| Table 3 历史注册结论 | 移除 `\resizebox`，恢复自然宽度 | 页 26，不再出现被放大到 20 pt 的异常 |
| Table 4–5 方向稳定性 | 保留 `\resizebox`（列多、天然较宽） | 页 27，文字约 9 pt，无越界 |
| Table 6 观测窗口纪录 | 移除 `\resizebox`，自然宽度 | 页 28，居中、可读 |

所有 6 个主表都在正文中被 `\ref` 调用；没有孤立表格。

## 4. 文本与版式

- 标题、作者占位、 affiliation 占位、Key points、Abstract、Plain Language Summary 均按模板顺序排列。
- 摘要 219 words；Key points 3 条均 < 140 字符。
- 正文双倍行距，段落无首行缩进异常；节标题层级为 1–3 级。
- 参考文献 37 条，作者–年份制，悬挂缩进；`apacite` 输出正常。
- 公式、单位（°C、°C per decade）、百分号、en dash/em dash 均正常；未发现未转义 `%` 或断行错误。
- 页眉为模板默认的 "manuscript submitted to Water Resources Research"；首页页脚页码正常。

## 5. 构建与测试

```text
latexmk -pdf review_completion_article.tex   # rc=0, 32 pages, 0 BibTeX warnings
latexmk -pdf review_completion_supporting.tex # rc=0, 34 pages
make review-test                              # 98 passed
```

## 6. 仍需作者完成的事项

1. 填写作者姓名、单位、通讯作者、基金和致谢；当前为占位符。
2. 已启用行号；若编辑要求连续行号或特定起始编号，按期刊说明调整。
3. 最终投稿前由作者确认数据/代码 DOI、版权与数据可用性声明。
4. 若编辑要求图件单独上传，使用 `figures/architecture/*.pdf` 与 `figures/simple_research/*.pdf` 的矢量文件；不要使用 PNG 检查副本。
