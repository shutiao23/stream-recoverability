# 第四轮审稿改进执行

本目录执行 [2026-10-23 的第 0–9 步计划](../wrr_mit_style_review_20261023/NEXT_STEPS_ZH.md)，保留原三份审稿文件及历史注册判定。

- [主张与证据矩阵](CLAIM_EVIDENCE_ZH.md)：先定义科学主张、基线、成功条件及失败写法。
- [执行报告](EXECUTION_REPORT_ZH.md)：自动汇总实际完成的种子数、结果、各步状态和外部依赖；缺数据不会写成通过。
- [23 项交付清单](EXPERIMENT_CHECKLIST_ZH.md)：每项列明完成、负结果、有限完成或外部待验及文件出处。
- [公开注册草稿](PREREGISTRATION_DRAFT_ZH.md)：新西兰独立检验的资格、E1–E5、停止规则及预写结果。尚未在 OSF 注册。
- [独立检验执行说明](INDEPENDENT_EXECUTION_ZH.md)：固定的 9 站/3 个保守管理区名单、原生质量/时钟处理，以及公开登记后的采集、病例生成和分析命令。
- [投稿材料核对](SUBMISSION_CHECKLIST_ZH.md)及[审稿问答草稿](REVIEWER_RESPONSE_DRAFT_ZH.md)：字数、图表、投稿信、主要质疑的回复和仍待实际检验的内容。
- [全国资料与 H30 执行](NATIONAL_EXECUTION_ZH.md)：元数据固定的源域数值采集、资格未知分母、同钟输入、固定年度模型和全国推断范围。
- [稿件源文件](../../../paper/wrr_tr/review_completion_article.tex)：按分诊、估计和推断改写。少于 20 次时 PDF 明示开发草稿。
- [结果与代码包](../../../results/wrr_review_completion_20261024/)：逐例结果、组角色、数值表和待注册附件。

`make wrr-review-completion` 运行全部本地阶段；各阶段可分别运行：`wrr-review-cases`、`wrr-review-refits`、`wrr-review-deep`、`wrr-review-inputs`、`wrr-review-analyses`、`wrr-review-prereg`、`wrr-review-paper`、`wrr-review-check`。生成和拟合均可按已完成站点/区域续跑；不能把文件存在当作新的公开注册。依赖可用 `pip install -e '.[review]'` 安装。

入口脚本为 `scripts/465_review_completion_cases.py` 至 `scripts/499_review_completion_air_exposure.py`；报告辅助为 `scripts/wrr_review_reporting.py` 和 `scripts/wrr_review_extensions.py`。486–488 增加冻结删除、正式半监督/条件保形对照；489/491 增加同站区域比较与观测纪录反证；490 只取全国日期/审批状态并按服务配额续页；492/493 区分概率校准和局地非线性适配。494–498 负责新候选元数据、源模型固定分析、登记后原生采集/病例、名单冻结；公开登记缺失时会停止。499 评估未标记空气暴露的合成记录污染。476 编排本地依赖和失败日志，不下载独立检验水温。前一版稿件保留在 `paper_archived/wrr_tr_20261023/`。

完成独立检验仍需公开 OSF 注册和匹配附件，以及足够多合格独立组；源域联合终点规划不支持“加大样本即可通过”。作者、机构、资助与 OSF/Zenodo 字段按用户要求留给用户填写。没有合格自然缺口参照时，审计与样本量计算不能替代精度验证。

500–503 是全国 USGS 源域阶段：数值与审批采集、原生网格 POWER LST、固定年度权重应用和选站/场显著性分析。它们保留原纯日期记录，开放的 USGS 数据不再作为新盲检验；小批结果必须标记为管线检查，不能填入全国完成标志。
