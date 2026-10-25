"""Report the requested missingness stratification and its physical limits."""
from __future__ import annotations
import json
import pandas as pd


def finish_zero_flow_reporting(out, doc, paper):
    folder = out / "zero_flow_missingness"
    if not (folder / "status.json").exists():
        return []
    status = json.loads((folder / "status.json").read_text())
    if not status.get("complete"):
        return []
    cohorts = pd.read_csv(folder / "cohort_counts.csv")
    summary = pd.read_csv(folder / "conditional_logit_summary.csv")
    air = summary.loc[summary.covariate.eq("z_air")]
    for name, table in [("cohorts", cohorts), ("conditional_logit", summary)]:
        table.to_csv(out / "evidence" / ("zero_flow_missingness_" + name + ".csv"), index=False)
    text = ["## 零流量代理下的缺测–炎热关联", "",
        "使用原 E1 站年样本中的 336 个 USGS 站、6,479 个站年，不将它与仅有完整年评价资格的源模型面板混用。批准日流量为非负有限值；同站同日矛盾值不投票归零。287 站有有效流量，其中 21 站至少记录过一个零值，16 站达到三十个零值；其余 49 站保留为缺流量资料。没有零值不证明常流河，零值也不自动识别间歇性河流、传感器暴露或河床干涸。", "",
        cohorts.to_markdown(index=False, floatfmt=".4f"), "",
        "沿用原站点固定效应条件 logit：暖季不完整年份作为响应，站内标准化夏季气温和线性年代项为解释量；另列加入站内标准化流量的模型。每组按原独立组划分自助四百次，保留重复分层标签。以下为气温每升高一个站内标准差的 OR；这种组自助依赖交换性，不是独立气候样本或因果保证。", "",
        air.to_markdown(index=False, floatfmt=".4f"), "",
        "零流量记录组的未加流量模型 OR=1.208，区间 0.882–1.564，21 站/17 组、380 个站年；至少三十个零日的敏感性为 1.282（0.876–1.889），16 站/14 组。未记录零值的组为 1.058（0.988–1.134）。这些区间不能证明组间效应相同，也不能排除零流量代理组更强的关联。加入流量的结果使用更小的可用样本，不能把两行差异解释成流量的中介效应。C1 仍限定为已打开档案的平均描述，不扩展为真实间歇性河流的规律或 MAR 证明。源模拟器、估计器和发布阈值未因本项结果改变。", "",
        "最初的并行运行因动态模块别名不能被工作进程导入而失败。修正为实际文件名导入，并通过两工作进程回归测试；没有把程序失败计为科学结果。原错误日志字节未保留，已将观察到的错误及限制另记 `worker_import_failure_20261024.json`，不伪称保存了原始 stderr。", ""]
    (doc / "ZERO_FLOW_MISSINGNESS_ZH.md").write_text("# 零流量代理分层与 C1 边界\n\n" + "\n".join(text) + "\n")
    article = paper / "review_completion_article.tex"
    content = article.read_text()
    marker = "% ZERO_FLOW_MISSINGNESS_BOUNDARY"
    if marker not in content:
        paragraph = (marker + "\nThe historical missingness sample includes 21 USGS sites with recorded approved zero flow. Their temperature--incompleteness odds ratio is 1.21, with a group-bootstrap interval of 0.88--1.56. This imprecise proxy analysis permits stronger associations and does not classify intermittent rivers; archive-average associations cannot establish dry-bed sensor validity.\n\n")
        content = content.replace("\\subsection{Driver, metric and transfer boundaries}", paragraph + "\\subsection{Driver, metric and transfer boundaries}")
        article.write_text(content)
    supporting = paper / "review_completion_supporting.tex"
    content = supporting.read_text()
    if marker not in content:
        paragraph = (marker + "\nThe C1 stratification retains the original 336-USGS-site, 6,479-station-year missingness sample. Approved discharge yields 21 sites with recorded zeros, 266 without a recorded zero and 49 with unavailable flow. A station-conditional logistic model adjusts standardized summer air temperature for linear decade trend; 400 independence-group bootstrap repetitions give OR 1.208 [0.882, 1.564] for the zero-record group and 1.058 [0.988, 1.134] for the available-flow group without recorded zeros. Requiring thirty zero days gives 16 sites and OR 1.282 [0.876, 1.889]. Flow-adjusted specifications have smaller available samples and do not establish mediation. Zero flow is a limited historical proxy, and group exchangeability remains assumed.\n\n")
        content = content.replace("\\input{review_completion_national_details.tex}", paragraph + "\\input{review_completion_national_details.tex}")
        supporting.write_text(content)
    claim = doc / "CLAIM_EVIDENCE_ZH.md"
    content = claim.read_text()
    content += "\nC1 补项见 [零流量代理分层](ZERO_FLOW_MISSINGNESS_ZH.md)：21 个零记录站的 OR 区间仍宽；未确立真正间歇性河流的效应或干涸观测有效性。\n" if "C1 补项见" not in content else ""
    claim.write_text(content)
    return [*text, "详见 [C1 分层执行记录](ZERO_FLOW_MISSINGNESS_ZH.md)。", ""]
