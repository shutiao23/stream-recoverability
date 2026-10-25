"""Report the two planned station profiles and the named-year event examples."""
from __future__ import annotations
import json
import pandas as pd


def finish_focused_reporting(out, doc, paper):
    folder = out / "focused_diagnostics"
    if not (folder / "status.json").exists():
        return []
    status = json.loads((folder / "status.json").read_text())
    if not status.get("complete"):
        return []
    profiles = pd.read_csv(folder / "prespecified_station_profiles.csv")
    effects = pd.read_csv(folder / "prespecified_station_trend_summary.csv")
    examples = pd.read_csv(folder / "hot_year_examples_summary.csv")
    qualification = pd.read_csv(folder / "US_year_qualification.csv")
    eu = examples.loc[examples.illustration.str.startswith("Europe")]
    for name, table in [("station_profiles", profiles), ("station_trends", effects), ("hot_year_examples", examples)]:
        table.to_csv(out / "evidence" / ("focused_" + name + ".csv"), index=False)
    text = ["## 原计划指定站点与热年演示", "",
        "两个站号由原计划 1.4 指定，没有按新结果选择。下表给出参与实验的完整年份范围及个数，不将它们称为连续完整档案。缺日和信息层是种子 0 的描述，趋势效应为二十次种子中位数。", "",
        profiles.to_markdown(index=False, floatfmt=".4f"), "",
        effects.to_markdown(index=False, floatfmt=".4f"), "",
        "Clearwater River at Spalding 和 Missouri River at Toston 都有二十个参与评价的完整年，日历缺日中位数分别为 9/16 日，供体层占约 92%/75%。随机缺测下，两站的 A1 平方误差贡献中位数约为 13.0%/6.1%，其 D2/A1 RMSE 比约为 0.28/0.33；两站不是全部误差。GAGES-II 2009 快照列出 3/15 座上游主要坝，所取得流量记录无零值，但这些资料不确定热量控制机制、现场断流或今天的调控状况。完整年跨度、完整度删选与日补全误差需要分开解释，不从坝数量作因果归因。主要比较继续使用原定平方误差比，并保留逐站比值与删站敏感性。", "",
        "欧洲演示年份固定为原计划的 2003、2018、2022。美国各源区域在至少三站具有完整水温参照的年份中，按种子 0 的区域站点气温距平中位数选最高且为正的一年；按气温选择后才提取逐年误差。这些是档案内暖年演示，不当作已核实的区域热浪目录。未满足条件的区域保留不可用原因，不用相对偏冷年份充当热年。", "",
        qualification.to_markdown(index=False, floatfmt=".4f"), "",
        "仅取决策时峰窗被遮 ≥50% 的病例；每次重复、每种缺口、每个演示中四种估计器使用相同的有限病例和同一训练期 H30 第 90 百分位事件阈值。表为逐种子指标中位数，n_common 可以是非整数。原始命中/漏报/误报/正确拒绝计数、未校正命中率/误报率及半计数校正 SEDI 均保留；没有事件或非事件时 SEDI 未定义。", "",
        eu.to_markdown(index=False, floatfmt=".4f"), "",
        "2003 年危险日历共同病例每次仅 6–22 例，不能用来确立稳定的分年总体效应：D2 的 MAE 中位约 0.913°C，MOVE.1 为 0.595°C。2018 年分别为 0.608/0.576°C，2022 年为 0.440/0.512°C。估计器的排序随年份变化，不添加“D2 在每次热浪更重要”的主张。美国全部可评价区域以及二十次原始指标另见 CSV；种子变化不是二十个独立气候样本。", ""]
    (doc / "FOCUSED_DIAGNOSTICS_ZH.md").write_text("# 指定站点与热年演示\n\n" + "\n".join(text) + "\n")
    supporting = paper / "review_completion_supporting.tex"
    content = supporting.read_text()
    marker = "% FOCUSED_STATION_AND_YEAR_DIAGNOSTICS"
    if marker not in content:
        paragraph = (marker + "\nThe two stations specified in the review plan, USGS 13342500 and 06054500, each contribute twenty complete evaluation years; their median shares of random-missingness A1 squared error are 13.0 and 6.1 percent. Historical dam and zero-flow metadata do not identify thermal causation. Named European 2003, 2018 and 2022 examples use common finite cases across all four estimators and preserve event contingency counts, hit/false-alarm rates and undefined SEDI. The 2003 dangerous calendar sample has only 6--22 cases per repetition; median MAE is 0.913 degrees C for D2 and 0.595 for MOVE.1. US illustration years are selected using positive regional air anomalies with at least three complete-water stations, preserving unavailable regions. These opened examples do not establish universal estimator rankings.\n\n")
        content = content.replace("\\input{review_completion_national_details.tex}", paragraph + "\\input{review_completion_national_details.tex}")
        supporting.write_text(content)
    checklist = doc / "EXPERIMENT_CHECKLIST_ZH.md"
    content = checklist.read_text().replace("无事件/非事件时 SEDI 未定义，不填造高技能。",
        "无事件/非事件时 SEDI 未定义，不填造高技能；另补欧洲 2003/2018/2022 与 15 个美国区域暖年演示，逐例共同支持和小样本均明示，见 [指定演示](FOCUSED_DIAGNOSTICS_ZH.md)。")
    checklist.write_text(content)
    return [*text, "完整出处见 [指定站点与热年记录](FOCUSED_DIAGNOSTICS_ZH.md)。", ""]
