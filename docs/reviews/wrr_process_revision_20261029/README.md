# 本轮科学修订的本地复现

逐条科学回复见 [RESPONSE_TO_REVIEW_ZH.md](RESPONSE_TO_REVIEW_ZH.md)。当前可支持的主张、未执行事项与明确范围见 [scope.json](../../../results/wrr_process_revision_20261029/scope.json)。最终测试、论文构建和文件核验记录以 [validation.json](../../../results/wrr_process_revision_20261029/validation.json) 为准；本说明不预先宣称其通过。

以下命令从仓库根目录运行，复用已有保存案例、完整年度参考、遮挡设计和冻结日模型输入。它们不下载新站点，也不对外发布。`962` 本身不重估来源角色偏移；该项由随后的 `make review-process-experiments` / `scripts/968_process_source_calibration.py` 完成，并已写入当前主文。

```bash
export PYTHONPATH="$PWD/src"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

python scripts/960_process_region_identification.py
python scripts/961_process_time_support.py
python scripts/962_process_trajectory_budget.py --replay
python scripts/964_process_gap_and_archive.py
python scripts/process_review_water_air.py
python scripts/963_process_revision_report.py
python scripts/970_process_experiment_report.py
```

960、961、962、964 和水气脚本的本轮表格/报告写入 `results/wrr_process_revision_20261029/`；论文输入写入 `paper/wrr_tr/process_*revision_*.tex`。963 汇总现有与本轮证据、生成图表与兼容宏；它保留旧审稿结果作为输入，不应通过改写旧审稿 CSV 来使新论述成立。主文图 10/11（`03_time_support`、`04_trajectory_budget`）由 970 从已保存的实验表写出；962/963 只写带 `_uncalibrated` / `_legacy` 后缀的参考图，不再覆盖这两张图。`scope.json` 和中文回复是本轮验收记录，不由每个分析脚本自动重写；更改科学口径时需同步核对。

962 已保存 27 个冻结输入及其哈希。常规重复运行使用现有冻结输入；如需要从原 whole-archive 设计重新生成日拟合冻结输入，可在同一命令增加 `--refresh-frozen`。该选项会更新本轮的冻结输入，但不改变原始六站名单，也不重训 D2。脚本验证种子 0 的原 20/100/500 分位数再进行三个种子的嵌套抽样；失败时会终止，不应绕过一致性检查。

直接检查共同权重、within 估计、配对区间、交叉项、805/807 分母与年度缺口单位：

```bash
python -m pytest tests/test_process_review_region_water.py tests/test_wrr_process_time_gap_revision.py
```

轨迹冻结输入/分层检查及主文、SI、图表和包的一致性由最终 `validation.json` 记录其实际执行命令。局部检查通过不能替代总体主张验收。962 包不能把未执行的来源角色重校准写成已完成；当前论文采用的来源重校准证据以 `results/wrr_process_experiments_20261029/` 及其 `validation.json` 为准。

作者信息、数据权限与永久存储由用户自行处理，属于用户明确排除的本次工作范围，不作为本地科学修订的待办或阻塞条件。

统一入口也可运行 `make review-process-revision` 和 `make review-process-revision-check`。本地候选包生成后，用 `make review-process-revision-package-check` 校验 ZIP 字节一致性、解压副本的主文/SI构建，以及27个冻结输入的三种子轨迹重放。该隔离重放复用当前安装环境，不是全量原始数据重建。最终 `validation.json` 为包外验收记录，包含当前候选 ZIP 的 SHA256；它不通过打包自身来证明自身。

本轮观测内容冻结与重放使用 `make review-current-observation-replay`。它在本轮 `replay_integrity/` 创建独立的新清单，并通过两验证器的 `--manifest` 参数重放；旧清单不回填哈希。新清单标识当前内容，不认证历史来源。当前快照包含95/96站的35个热窗口和210项规则决策，额外USGS含10站、8个完整参考年和9个窗口。旧桥接报告及候选档案收据若缺少原内容哈希，当前验证器会明确拒绝其再次认证，详见 `verification_code_repairs_report.json`；这不改变本轮已复算的A/B/C结果，也不等于全量原始资料重建。
