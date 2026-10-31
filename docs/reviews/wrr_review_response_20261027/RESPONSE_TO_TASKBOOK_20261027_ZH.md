# 任务书逐项落实与剩余缺口

本表针对 2026-10-27 更新任务所引用的审稿意见，依据当前工作区及已保存结果填写。研究采用任务书建议的实证评估定位：比较不完整档案的信息保留、恢复与推断，并公开报告失败条件。模型没有取得普遍部署或录用保证；“已经完成试验”与“得到可靠覆盖”分别记录。

| 原意见与验收点 | 当前落实 | 可以核查的证据 | 尚未证明或仍待完成 |
|---|---|---|---|
| P0：所有方法尊重报告序列的观测下界 | 年度点值、分位数与样本统一采用有限下界投影；缺失预测仍保持不可用 | `src/stream_recoverability/experiments/tr_revision/archive.py`；`whole_archive/support_projection_report.json`；`tests/test_whole_archive.py` | 下界属于同一报告序列，不包含已知物理测量误差保证 |
| P0：修正两侧截尾，再固定年度边际比较联合结构 | 默认使用相邻正态分位间距延伸，保留常数尾部对照；跨年重排保留完全相同的年度样本 | `whole_archive/quantile_tail_summary.csv`；`whole_archive/uncertainty_paired_summary.csv`；`archive.py::marginal_draws`、`reorder_marginals` | 七个分位数不能识别真实尾部；辅助 Ridge 排序不是实际 D2 参数后验 |
| P0：拒绝退化或来源不足的任务校准 | 明确不足来源群组、退化来源误差和不匹配半宽等状态；零因子不再直接发布零宽趋势区间 | `archive.py::task_calibration_support`；`whole_archive/task_calibration_sources.csv`；`whole_archive/paired_task_intervals.csv` | 可用率低，不能据少量支持子集宣称总体校准改善 |
| P0：系统图与代码一致 | 图中区分单个分类器分数、数值发布和探索性发布后趋势；目标缺口与仍可见观测边界已改正 | `paper/wrr_tr/figures/architecture/fig1_evidence_actual.dot`、`fig2_release_actual.dot`；`tests/test_review_manuscript_structure.py` | 个体分数没有群组风险保证，工作似然区间也不是缺测不确定性的校准区间 |
| P1：对照实际完整率规则与相关文献 | 逐案例核对 35 个观测见证；32 个通过目标年排除的站点暖季规则、31 个通过全年 95% 规则；加入 Johnson 和 Beaufort 的适用目标区别及方法适配 | `audit/screening_rule_reaudit.json`；`summer_window_comparison/`、`past_season_screening/`、`beaufort_proxy/`；主稿引言及观测结果 | 核心观测事实主要反驳严格完整年筛选，不能把 35 个见证全部归因于较宽松筛选规则 |
| P1：独立单位、共同分母与地区稳健性 | 报告 42 站对应 18 个连接群组，使用共同可用样本、群组重采样、地区剔除和扩展缺测机制 | `whole_archive/paired_trend_estimators.csv`；`expanded_stress/`；`heat_gap_matched/`、`heat_gap_source_sensitivity/` | 重复掩码不是独立河流；地区不平衡、事后选择和合成缺测限制外推 |
| P1：区分年度失配、尾部与依赖的影响 | 比较年度覆盖、趋势尾部、固定边际排序、区间宽度、区间评分及可用率；保留未观测峰值分层和区间扩张的代价 | `whole_archive/uncertainty_paired_contrasts.csv`；`whole_archive/peak_visibility_annual.csv`；`groupmax_annual_calibration/` | 两组使用不同随机样本的敏感性不是可相加的因果贡献分解；可靠前推覆盖尚未建立 |
| 若三类输出保留为主要设计：真实发布后再推断，并与简单规则比较 | 已实际形成数值／下界／未知决策并拟合工作趋势；补充相同数值数量比较，保留不优于简单分数规则的结果 | `integrated_release_trend/annual_decisions.parquet`；`archive_matched_release_trend/summary.csv`、`independent_likelihood_audit.json` | 相同数量可选不同年份；结果没有证明通用安全收益，故主文将其作为证据边界而非部署推荐 |
| 新外部参考与质量资格 | 实际获取并核查多批来源；USGS 连续数据、ICE 历史敏感性、两种时钟及条件 H30 界均有保存和独立算术复核 | [USGS 探索报告](USGS_EXPLORATORY_REPORT_ZH.md)；`data/external/wrr_usgs_partial_daily_20261027/` | 合格的独立气候恢复或趋势确认仍未取得；部分历史适配、未知仪器质量和先前接触不能改称严格确认 |
| P2：少数水文学问题组织主文，保留负结果 | 当前主稿围绕观测事实、年度恢复、档案保留与推断边界组织；旧稿和工程史保留在本地档案；主稿明确经典法有时更好 | `paper/wrr_tr/review_completion_article.tex`；[编辑记录](EDITORIAL_REORGANIZATION_ZH.md) | 正式审稿仍可能要求进一步压缩或改变叙述重点，无法从本地检查推断录用 |
| P2：补充材料格式和引用 | 改用 AGU 指南点名的 `agutexSI2019`，保留 34 个文本节和 40 个表；正文与输入声明在格式切换前后逐字一致 | `paper/wrr/template/AGU_SI_PROVENANCE.md`；`review_completion_supporting.tex`；结构测试 | 官方 ZIP 本机返回 403，类文件由两个相同镜像取得；作者信息仍为占位 |
| 投稿前必要：代码、数据、许可、版本和访问方法 | 新盘中持久保存稿件、全部本地分析和候选包；具备原软链接路径的测试、公开参考重放及受限本地重放说明 | [本地重放说明](USGS_LOCAL_REPLAY_ZH.md)；`DATA_RIGHTS.md`；`audit/completion_status.json` | 审稿人所需全部受限源输入／模型的合法访问、永久仓库地址与正式版本仍未完成 |
| 投稿前必要：作者及声明 | 提供结构化填写文件，保留用户已明确答复的“待定”，不从用户名推断 | `metadata/submission_author_metadata.json`；`paper/wrr_tr/review_completion_cover_letter.txt` | 真实姓名、顺序、单位、通讯信息、基金、利益冲突与全体作者确认必须由作者给出 |

表中结果路径除特别注明外，均相对 `results/wrr_review_response_20261027/`。当前论文中的年度覆盖使用明确的数值端点容差；单年来源和整档案的独立标量敏感性审计分别位于 `annual/single_year_coverage_scalar_audit.json` 和 `whole_archive/main_coverage_numeric_scalar_audit.json`。数值容差不能作为仪器误差边界。

本次后续复核还确认了 LUBW 的实际下载入口与官方观测元数据均指向 UIS 专门使用条款。登记中的暂缓分发是当前操作决定，不再把网站通用版权页单独解释为所有数据和派生成果的法律禁止；完整条款的实时获取及归档版本和派生范围仍未确认。Hubbard Brook 的两份新线索则分别是空气温度和每周瞬时水温，未下载温度表或增加精度评分。

必须由外部条件解决的交付仍有：作者信息及声明、必要来源的合法审稿访问、永久数据和代码归档。独立参考不足和可靠覆盖不足属于科学证据限制，已在论文中披露；若希望恢复更强的跨气候或部署主张，还必须增加满足事先定义标准的证据。当前工作不能标记为“所有投稿条件完成”。
