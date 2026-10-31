# USGS 探索：迁移后的本地保存与重放

项目原路径 `/home/lzq/workspace/parttime/stream-recoverability` 当前通过软链接指向第二块 NVMe。批准公开的 USGS／NASA 参考快照位于 `data/external/wrr_usgs_partial_daily_20261027/`；本地受限的逐案例预测、校准敏感性、冻结方案、源响应和 430 个原临时分析文件保存在 `private/wrr_usgs_partial_daily_20261027/tmpfs_analysis_20261027/`，不应在未解决来源权利时公开分发。此目录的 `analysis_copy_manifest_20261027.json` 记录文件和权限。原有计划中出现的 `/dev/shm` 路径是历史执行位置，不能仅凭永久保存就认定全部模型可从公开材料重建。

在仓库根目录，以下命令检查永久保存的私有分析快照；它不会修改或覆盖快照：

```bash
python scripts/923_restore_usgs_analysis.py
```

如果重启之后 `/dev/shm/wrr_usgs_partial_daily_20261027` 不存在，需要重现原本依赖该目录的本地历史脚本时，可运行：

```bash
python scripts/923_restore_usgs_analysis.py --restore-to /dev/shm/wrr_usgs_partial_daily_20261027
```

工具会核对文件是否齐全及权限模式，并拒绝覆盖任何已有目标；执行失败可能留下部分目标目录，检查后由使用者处理。历史计划还要求原仓库路径、源数据和模型保持可用。恢复临时目录不是独立模型重训，也不建立科学结论或数据授权。

公开参考快照提供离线脚本 `890_public_usgs_reference_replay.py`、`892_public_usgs_raw_daily_audit.py`、`901_public_subdaily_bounds_replay.py`、`916_public_qualifier_history_replay.py` 和 `917_public_riomora_expansion_replay.py`；其精确运行命令、归属及限制见快照中的 `README.md`。这些脚本核对来源观测和算术，不重现受限源模型评分。NASA POWER 数据再分发通知及其他来源权限仍待作者处理；本地候选包不是永久归档或已完成的投稿材料。
