# 目标感知恢复研究：第二轮（2026-10-22）

按第二轮审稿后的 [改进计划](../wrr_mit_style_review_20261022/NEXT_STEPS_ZH.md) 执行的工作。

- [RESULTS_2_ZH.md](RESULTS_2_ZH.md)：全部结果、三个关口、P1–P4 与 N1–N4、闭环检查、偏离记录。
- [PREREGISTRATION_2_ZH.md](PREREGISTRATION_2_ZH.md)：第二份预注册（新 USGS 站的封存测试）。已写定，不得修改。
- [TRANSPARENCY_ZH.md](TRANSPARENCY_ZH.md)：第一份预注册的时间线和修改记录（M7）。
- 稿件：[paper/wrr_tr/](../../../paper/wrr_tr/)；迁移一节的两个事先版本在 `paper/wrr_tr/transfer_versions/`。
- 结果：`results/wrr_target_recovery_20261022/`；脚本 `scripts/450`–`464`，并沿用 `scripts/431`–`445` 与 `scripts/wrr_tr_*.py`。

复现：`make wrr-tr2`（开发与冻结）、`make wrr-tr2-sealed`（新站封存测试，已执行过一次，评估脚本会拒绝重跑）、`make wrr-tr-paper`（图、数字宏、表与 PDF）、`make wrr-tr-check`（单元测试）。
