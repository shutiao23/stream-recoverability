"""Keep the low-flow mechanism comparison separate from thermal confirmation."""
from __future__ import annotations
import json
import pandas as pd


def finish_flow_reporting(out, doc, paper):
    folder = out / "flow_comparators"
    if not (folder / "status.json").exists():
        return []
    status = json.loads((folder / "status.json").read_text())
    control = json.loads((folder / "historical_control_audit.json").read_text())
    if not status.get("complete") or not control.get("passed"):
        return []
    score = pd.read_csv(folder / "scorecard.csv")
    paired = pd.read_csv(folder / "paired_effects.csv")
    rules = pd.read_csv(folder / "rules.csv")
    shown = score.loc[score.scope.eq("donor_danger")]
    for name, table in [("scorecard", score), ("paired_effects", paired), ("rules", rules)]:
        table.to_csv(out / "evidence" / ("flow_" + name + ".csv"), index=False)
    text = ["## 低流量的同病例经典对照", "",
        f"已打开示范的 {status['n_sites']} 站、{status['n_complete_years']:,} 个完整气候年、{status['n_cases']:,} 个病例全部重现；原始 {control['historical_columns_compared']} 个特征/结果字段在 1e-10 绝对容差内一致，未覆盖旧输出。新分支使用同一随机流和缺口，额外随机桥另设种子；历史 D2 预测固定。", "",
        "MOVE.1 与单供体 Ridge 使用同一最佳供体、相同其他年份的对数流量异常；历史 Ridge 和随机桥使用最多三供体。随机桥为二十次 Gaussian AR1 路径，使用其他年份的样本内残差；没有独立区间校正，不将其当作已校准分布。无供体的年份保持经典方法不可用。", "",
        shown.to_markdown(index=False, floatfmt=".4f"), "",
        paired.loc[paired.scope.eq("donor_danger")].to_markdown(index=False, floatfmt=".4f"), "",
        "MOVE.1 相对相同信息的单供体 Ridge，在两种缺口下都未降低危险层 MAE；随机桥亦没有优于历史 D2。保方差或抽路径并不自动校正低流量函数量。对数误差均值的 exp(error)-1 为几何比偏差；先对 log(Q) 回归再取指数不是原始流量单位的条件均值，不能据此证明与 H30 相同的普遍偏差方向。此项仅一次已打开示范，不是二十次稳定性或独立迁移。", "",
        "流量阈值沿用旧示范：log(7Q) 跨年标准差中位数的一半，约 0.1654；不得与河温 0.5°C 容差混用。逐规则留存和风险保存在 `flow_comparators/rules.csv`，无输出不计为成功。", ""]
    (doc / "FLOW_EXECUTION_ZH.md").write_text("# 低流量示范的经典对照\n\n" + "\n".join(text) + "\n")
    supporting = paper / "review_completion_supporting.tex"
    content = supporting.read_text().replace(
        "It lacks the present matched MOVE.1/stochastic calibration comparison; exponentiating a log-flow prediction also differs from a conditional mean in original discharge units.",
        "A separate matched extension reproduces all 134,925 historical cases and adds best-donor MOVE.1, the same single-donor Ridge, and twenty Gaussian AR1 log-flow bridges. These working bridges use other-year in-sample residuals without independent interval calibration. In 33,609 controlled dangerous donor cases, log-scale MAE is 0.090 for single-donor Ridge and 0.106 for MOVE.1; the multidonor bridge gives 0.104 and historical D2 gives 0.075. The variance-preserving methods can change bias direction without improving MAE. Exponentiating a log-flow prediction differs from a conditional mean in original discharge units.")
    supporting.write_text(content)
    claim = doc / "CLAIM_EVIDENCE_ZH.md"
    claim.write_text(claim.read_text().replace("现有 7Q 示范；日最高温 7DADM 敏感性",
        "7Q 同病例 MOVE.1/单供体 Ridge/随机桥（未支持通用偏差修复）；7DADM 敏感性"))
    return [*text, "复现和限制见 [低流量执行记录](FLOW_EXECUTION_ZH.md)。", ""]
