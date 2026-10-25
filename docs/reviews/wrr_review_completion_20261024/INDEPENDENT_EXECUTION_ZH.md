# 独立检验的执行边界

本说明对应第 7 步。作者、机构和平台字段由用户填写。现有材料仍是注册前草稿；尚无新河温检验结果。

`scripts/494_review_completion_independent_metadata.py` 仅允许 Hilltop 的 SiteList、MeasurementList、TimeRange、SiteInfo 和 CollectionList。它拒绝含观测的响应，用 `%20` 编码站名空格，保留原 XML、请求 URL、获取时间和 SHA256。连续记录、检查记录和离散抽样分开；日期支持不是完整观测年的证明。

Horizons 的 WaterTemperature 集合共 58 站，产生 64 条审查记录（含未找到精确连续温度序列的站），当前公开档案的潜在合格站数为零。主要连续序列从 2024 年开始，只支持两个完整七月至六月热年的时间范围。没有因此改变四年的资格门槛，也没有进行误差检验。替补 Greater Wellington 的 218 个目录站也已核完，固定 9 个潜在站、3 个保守管理区合并组，名单位于 `independent_study/greater_wellington/registration_roster.csv`。九站不是九个独立组，也不是九个已经通过完整日值质控的站。

`acquisition_plan.json` 已固定每站及合并组、名单与源模型、日内测量/质量接口、明确时钟、质量/采样/日聚合规则、供体范围和旧资料排除核查。所有候选 TimeRange 的偏移均为 UTC+12。参照日只接受质量码 600 的完整规则日内采样，未知、合成和检查记录不算完整；不使用机构日均虚拟统计替代完整性核查。空气驱动用 ERA5-Land 的完整 24 小时在同一固定 NZST 日聚合。日内水温、质量与日期解析已用合成输入测试；实际机构观测接口仍保持未打开。

当前方案为小样本失败检测研究：供体仅在保守合并区内共享；跨区天气和误差的交换性仍是假设。三个合并区无法实施十个标签组的 E5，预先报告不可用；没有达到 80% 的规划功效。严格质控后不足四个完整热年的站将报告不合格，不放宽阈值或看误差补站。

`make wrr-review-prereg` 重现元数据、源输入、名单和代码包；公共记录出现后不会重打包该注册。用户自行填写平台身份与投稿信息，上传最后生成的代码/模型包、`protocol_draft.json` 与 `file_sha256.json` 到同一个 OSF 注册存档。公开登记后执行：

```bash
python scripts/472_review_completion_prereg.py --osf-registration <注册ID> --verify-attachments
python scripts/495_review_completion_independent_analysis.py --check-only
```

第一条读取已接受的公开注册，逐字节比较注册存档附件。它不会重新生成已上传的压缩包。第二条还要求采集方案及名单确实存在于同一注册快照中；本地事后填写或改动不会通过。当前缺的是公共登记，因此预期会停止。附件校验只用于确定执行的是哪份公开方案，登记时间的依据始终是 OSF 平台，不以本地时间或文件代替。

登记后，496 采集原生河温和阶梯质量序列、应用固定日值质控；497 获取气温并用冻结的源模拟设置和普通种子 0 生成受控与真实日历病例。年度分布回归、P2 和失败分类器参数、经典区间偏移及决策热年阈值固定于源域。日补全的局地气温/供体系数、气候态和残差模型按登记配方使用目标站其他历史年份拟合，被评估整年排除在外。这是离线历史修复，可用其他较晚历史年份；不声称实时预报，也不声称完全没有使用目标站历史水温拟合。

```bash
python scripts/496_review_completion_independent_acquisition.py --acquire
python scripts/497_review_completion_independent_cases.py --prepare-cases --workers 8 --resume
```

原始请求记录、质控日值、病例和 `acquisition_receipt.json` 均保留。该收据记录注册 ID、首个河温请求 UTC 时间、原生日值质控过程及病例 SHA256；它是执行出处，不是能够证明全部过去访问行为的密码学证据。

```bash
python scripts/495_review_completion_independent_analysis.py \
  --cases results/wrr_review_completion_20261024/independent_study/acquired/registered_cases.parquet \
  --output results/wrr_review_completion_20261024/independent_evaluation
```

分析入口不重新拟合源模型、不校准目标概率、不换阈值；不支持的预测保留在资格分母。E1 按整个合并组自助，空自助放行按风险一保守处理；无标签放行和空放行均不能通过。E2 对至少放行 20 例的可评价组计算超过 10% 风险的比例，无组可评价时不能通过。E3 报覆盖、宽度和区间得分，E4 报共同病例误差；另输出同一源记分卡的 CRPS、twCRPS、基线与事件表。E3/E4 只判登记点标准，没有优效假设检验，故不把未做 Holm 的结果称为显著。E5 在本队列预先不可实施。

当前尚未完成的是公共登记、实际日内河温/质量接口与参照资格核验，以及新资料的固定分析。原生适配器、名单及本地测试不能替代这些结果；不会把元数据筛选、绿色代码检查或分析入口称作独立验证已经完成。

## 执行版本一致性

观测入口现在同时检查登记快照中的执行文件：所有归档的 `src/`、`scripts/` Python 文件、必要配置、当前激活的源配置、冻结生成设置/缺测生成器，以及全局源权重和经典校准均须逐字节匹配。方案和名单仍须在同一登记快照内。文稿与作者行政字段不被当作执行代码；代码有后续修改时应在登记归档的独立解压目录运行，不重写原公开归档。校验失败会在任何观测 HTTP 请求和 `acquired/` 创建之前停止。

`python scripts/516_review_completion_archive_smoke.py` 在临时解压目录验证源模型推断及合成日序列病例生成，禁用网络并检查没有导入当前工作目录的项目代码。该检查使用已打开源特征和合成水温，不能代替 OSF 公共登记或新的独立结果。

需要从归档目录执行时，先在原工作目录解压并复制原包本身；压缩包不能包含它自身，而后续登记核验需要这份确切原件：

```bash
mkdir -p scratch/registered_frozen_run
tar -xzf results/wrr_review_completion_20261024/independent_study/registration_code_and_protocol.tar.gz -C scratch/registered_frozen_run
cp results/wrr_review_completion_20261024/independent_study/registration_code_and_protocol.tar.gz scratch/registered_frozen_run/results/wrr_review_completion_20261024/independent_study/
cd scratch/registered_frozen_run
PYTHONPATH=src python scripts/472_review_completion_prereg.py --osf-registration <真实注册ID> --verify-attachments
PYTHONPATH=src python scripts/495_review_completion_independent_analysis.py --check-only
```

核验通过后仍在该目录、使用 `PYTHONPATH=src` 执行上述 496、497、495 命令。不要在已公开的归档目录运行重新打包入口。
