# WRR 投稿前清单（2026-10-31）

这些是作者提交事项，不是本轮科学小修。未完成的条目不得由本地重放成功替代，也不得用占位符冒充真实信息。

## 已完成的本地材料路径

- [x] 主文 PDF：`paper/wrr_tr/review_completion_article.pdf`（41 页）
- [x] SI PDF：`paper/wrr_tr/review_completion_supporting.pdf`（102 页）
- [x] 封面信标题与当前稿件一致：`paper/wrr_tr/review_completion_cover_letter.txt`（不进入 PDF；收益限定为 805 个 30–90 天控制缺口档案）
- [x] 最终候选包：`dist/wrr_final_candidate_20261031.zip`
- [x] 包清单：`dist/wrr_final_candidate_20261031.manifest.json`
- [x] 包内逐文件清单：`CONTENT_MANIFEST.sha256`
- [x] 包内发布回执：`RELEASE_RECEIPT.json`
- [x] 当前验收记录：`results/final_release_20261031/acceptance.json`
- [x] 小修完成报告：`docs/reviews/wrr_multiview_review_20261031/MINOR_REVISION_COMPLETION_ZH.md`
- [x] 旧包保留为历史冻结版本：`dist/wrr_process_experiments_20261029.zip`；其 `validation.json` 不覆盖当前稿件

## 作者与声明

- [ ] 确认作者姓名、顺序、ORCID 和通讯作者。
- [ ] 确认单位、基金、CRediT 贡献、利益冲突和致谢。
- [ ] 用作者确认的内容替换主文和 SI 中的占位作者块。
- [ ] 确认专投与水资源研究相关期刊的声明。
- [ ] 不根据仓库别名推断真实姓名或法律声明。

当前模板：[metadata/submission_author_metadata.json](../../../metadata/submission_author_metadata.json)。该文件明确标注 `complete: false`、`approved_by_all_authors: false`，本轮未填写。

## 合法审稿访问

- [ ] 提供 42 站评估所用源观测的合法审稿访问路径。
- [ ] 解决 LUBW 重用与再分发，再共享含 LUBW 正权案例的估计器或校准派生文件。
- [ ] 保持 96 站中 95 站公开见证子集可用于 35 个观测见证的算术审计。
- [ ] 明确哪些个案表、模型权重和修复表只能通过受限审稿渠道提供。
- [ ] 不把未解决的提供方许可写成开放许可。

包 README 已说明：其他底层源观测、主模型个案表和训练权重不在包内；`make` 目标不能仅凭该包重建整项研究。LUBW 条款仍需单独解决。

## 永久保存与引用

- [ ] 为代码、处理表和图脚本分配永久仓库与可引用标识。
- [ ] 为冻结的整档预测、来源校准结果和时间选集结果建立永久副本。
- [ ] 在每个归档旁记录许可与访问条件。
- [ ] 决定是否将本次候选包作为审稿附件或补充材料；若作为附件，使用包清单中的内容指纹固定版本。
- [ ] 在 DOI 真正建立前，不把 `CITATION.cff` 的早期 v1.1.0 条目当作本次稿件修订的引用。
- [ ] 不虚构 Zenodo、HydroShare 或其他 DOI。

当前 `CITATION.cff` 只描述早期代码发布，并明确 `doi` 未设置。本次稿件修订的作者与归档引用仍待作者提供。

## 版本绑定

- [x] 当前主文/SI 由当前 TeX 源重建，并经隔离解压编译核对。
- [x] 新包与当前工作区逐文件一致（生成文件除外）。
- [x] 新验收记录引用新包内容指纹、成员数、两个 PDF 内容、测试和重放结果。
- [x] 人读报告和清单不重复列哈希值；机器可核验内容指纹保留在 `acceptance.json`、包清单和包内 `CONTENT_MANIFEST`。
- [ ] 作者确认最终提交版本后，重新生成一次候选包和验收记录；不要把本记录当成投稿后的永久冻结。

## 明确不声称

- 不声称干净环境依赖安装已经通过。
- 不声称全部原始提供方资料可以从零重建。
- 不声称所有模型已从零训练。
- 不声称已有跨气候独立外部确认。
- 不声称作者、合法访问或永久保存已经完成。
