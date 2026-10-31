# 目标感知恢复研究（2026-10-21）

按 [改进计划](../wrr_mit_style_review_20261021/IMPROVEMENT_PLAN_ZH.md) 执行的新研究。

- [PREREGISTRATION_ZH.md](PREREGISTRATION_ZH.md)：唯一的预注册文件，含 E8 运行前的一处修订。
- [RESULTS_ZH.md](RESULTS_ZH.md)：全部实验结果、四个主要终点与关口、闭环检查、偏离记录。
- 新稿：[paper/wrr_tr/](../../../paper/wrr_tr/)。
- 结果：`results/wrr_target_recovery_20261021/`；脚本 `scripts/426`–`449` 与 `scripts/wrr_tr_*.py`。

复现：`make wrr-tr`（开发实验）、`make wrr-tr-sealed`（澳大利亚封存测试，已执行过一次，脚本会拒绝重跑）、`make wrr-tr-paper`（图、数字宏、表与 PDF）、`make wrr-tr-check`（单元测试）。

第二轮（2026-10-22）的修正、第二份预注册和新 USGS 站的封存测试见 [../wrr_target_recovery_20261022/](../wrr_target_recovery_20261022/README.md)。第一轮的结果文件保持不变。
