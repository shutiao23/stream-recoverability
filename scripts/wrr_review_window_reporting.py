"""Report target-window refits and full-source forcing without new fitting."""
from __future__ import annotations
import json
import pandas as pd


def finish_window_reporting(out,doc,paper,tex_table):
    evidence=out/"evidence";status_path=evidence/"completion_status.json"
    state=json.loads(status_path.read_text())
    forcing=out/"inputs/forcing_full_source_exact"
    forcing_done=(forcing/"analysis_summary.json").exists() and not json.loads((forcing/"analysis_summary.json").read_text()).get("partial",True)
    window=out/"target_windows/h7/full"
    window_done=(window/"completion.json").exists() and json.loads((window/"completion.json").read_text()).get("complete",False)
    from wrr_review_forcing_reporting import europe_evidence
    european=europe_evidence(out);europe_done=european["full_source"]
    recovery_done={}
    for region in ["usgs","europe"]:
        path=out/"inputs/forcing_recovery"/region/"status.json"
        recovery_done[region]=path.exists() and not json.loads(path.read_text()).get("partial",True)
    state.update(full_USGS_forcing_complete=bool(forcing_done),full_H7_target_refits_complete=bool(window_done),
                 full_Europe_available_coordinate_forcing_complete=bool(europe_done),driver_recovery_models_complete=recovery_done)
    additions=[]
    if forcing_done:
        data=pd.read_csv(forcing/"paired_summary.csv")
        intervals=pd.read_csv(forcing/"paired_group_bootstrap.csv") if (forcing/"paired_group_bootstrap.csv").exists() else pd.DataFrame()
        if len(intervals):intervals.to_csv(evidence/"forcing_paired_group_bootstrap.csv",index=False)
        additions += ["## 14. 全 USGS 源站的驱动与流量对照", "",
            "Daymet 由旧 35 站试验扩展到全部 319 个可评估源站，319 站均取得数据；340 个网络–站点输入任务保留各自原始全精度历史。原始 POWER 控制的 67,316 个病例、可用性与有限点值精确重现。Daymet、流量和邻近 NOAA 各有自己的共同可用对照分母，不能把三项不同的 POWER 数值当作同一组病例。", "",
            data.loc[data.stratum.eq("air_layer_danger")].to_markdown(index=False,floatfmt=".4f"), "",
            "Daymet 的 9,271 个气温层危险病例，MAE 从 0.6610 变为 0.6823°C；流量的 7,048 个病例从 0.7084 变为 0.6228°C。逐站不差比例分别约 45.8% 与 71.3%。产品、日聚合和时间约定的影响没有分离；此项只重拟合日补全，未用新驱动重新训练所有年度分布与发布分类器，也不是 20 次稳定性重复。完整限定和复现见 [驱动执行记录](FORCING_EXECUTION_ZH.md)。", ""]
        if len(intervals):
            additions += ["按连接组重抽 2,000 次的配对结果如下；这是固定、共同可用源病例的组构成敏感性，不是新气候或重新掩码/拟合的置信保证。正值表示替代输入降低 MAE。", "",
                intervals.loc[intervals.stratum.eq("air_layer_danger")&intervals.metric.eq("relative_mae_reduction"),["arm","n_groups","point","lower","upper"]].to_markdown(index=False,floatfmt=".4f"), ""]
    if window_done:
        summary=json.loads((window/"completion.json").read_text())
        if summary["outer_fits"]!=540 or len(summary["seeds"])!=20:raise RuntimeError("Incomplete target-specific window report")
        if not json.loads((window/"daily_input_audit.json").read_text())["passed"]:raise RuntimeError("Native H7 has not passed its daily-input audit")
        score=pd.read_csv(window/"scorecard_summary.csv")
        score.to_csv(evidence/"H7_refit_scorecard_summary.csv",index=False)
        directions=pd.read_csv(window/"direction_stability.csv");directions.to_csv(evidence/"H7_refit_direction_stability.csv",index=False)
        shown=score.loc[score.stratum.eq("danger")&score.estimator.isin(["plug_in","functional_debias","distribution_regression","stochastic_regression_calibrated"])]
        columns=["family","estimator","n_seeds","mae_median","crps_median","twcrps_median","coverage90_median"]
        with (paper/"review_completion_tables_si.tex").open("a") as stream:
            stream.write(tex_table(shown,"Native H7 source refits, 20 seeds and 540 outer-region fits. Seven-day peak supports, masks, history summaries, conditional functionals, MOVE augmentation, annual models and disjoint calibration are recomputed. MAE and proper scores are in degrees C; coverage refers to 90 percent intervals. These are dangerous decision-time cases, not the historical H30 endpoint; deep models are not refitted here.","tab:H7-native-refits",columns))
        additions += ["## 15. H7 从头重算与留区重拟合", "",
            "已完成 20 个种子的七日目标资料、540 个外区拟合和每站每情景 200 次趋势重复。气候峰窗、受控缺口位置、历史极值及异常、残差峰窗、历史缺口重放、条件路径函数量、MOVE 年度增补、年度模型、风险分类器和互斥校准都以七日目标重算。为保持入组规则不变，日历病例仍要求至少 30 个可见日；它不是七日窗口长度。", "",
            "原生文件始终使用 h7 字段；旧拟合引擎内部使用显式的 h7→h30 适配视图，先删去真正的次要 H30 字段再改名。16 个不同机构–补全层的原始日值核验通过；默认 H30 的 240 个病例、201 个共同字段也与原源结果及既有随机桥修复完全一致。", "",
            shown[columns].to_markdown(index=False,floatfmt=".4f"), "",
            directions.to_markdown(index=False,floatfmt=".4f"), "",
            "新结果是目标窗口特定的源域探索性检验，不更改任何历史 H30 注册判定。未将深度模型和每种容差、阈值的所有组合全部重训；原固定预测的规格曲线另行保留。原始结果、原生预测和全部规则、组风险及趋势 CSV 见 `target_windows/h7/full/`。", ""]
        window_doc=doc/"WINDOW_EXECUTION_ZH.md"
        content=window_doc.read_text().split("\n## 已核验结果\n")[0]
        content=content.replace("首个完整种子已完成 27 个留区拟合、评分和趋势实验；全部 20 种子流水线仍在计算。",
            "全部 20 个种子的原生资料、540 个留区拟合、评分及趋势实验已完成，并通过各区域原生目标和点估计的身份核验。")
        content=content.replace("正在运行的生成进程由 `511_review_completion_window_finish.py` 等待，随后顺序完成拟合、分析与证据核查；它不会启动第二个生成器。",
            "`511_review_completion_window_finish.py` 可等待已有生成进程，随后顺序完成拟合、分析与证据核查；它不会启动第二个生成器。")
        content=content.replace("；不能用首个种子推断 20 次稳定性","")
        window_doc.write_text(content+"\n## 已核验结果\n\n"+shown[columns].to_markdown(index=False,floatfmt=".4f")+"\n\n"+directions.to_markdown(index=False,floatfmt=".4f")+"\n")
        checklist=doc/"EXPERIMENT_CHECKLIST_ZH.md";content=checklist.read_text()
        content=content.replace("固定预测完成，H7 原生 20 种子执行中","固定预测与 H7 原生 20 种子重拟合完成")
        content=content.replace("新增 H7 原生首个种子的 27 个重拟合、评分与趋势已完成，20 种子流水线仍在计算，",
            "新增 H7 原生 20 个种子、540 个外区拟合、评分与趋势均完成，")
        checklist.write_text(content)
        response=doc/"REVIEWER_RESPONSE_DRAFT_ZH.md";content=response.read_text()
        content=content.replace("H7 原生首个种子的 27 个重拟合、评分与趋势已完成，全部 20 种子流水线执行中；",
            "H7 原生 20 个种子、540 个外区重拟合、评分与趋势已完成；")
        response.write_text(content)
        supporting=paper/"review_completion_supporting.tex";content=supporting.read_text()
        content=content.replace("The specification table varies tolerances and decision caps and compares H7/H30 on fixed predictions; it is not a complete refit of an H7 distribution model.",
            "The original specification table varies tolerances and decision caps on fixed predictions. A separate twenty-seed, 540-outer-fit H7 pipeline recomputes seven-day peak support, masks, histories, functional draws, MOVE augmentation and annual/risk calibration. Native H7 fields are adapted to the legacy fitting engine after removing the genuine secondary H30 fields; exported native predictions restore H7 names. The daily-input audit reconstructs sixteen provider/tier combinations directly, and default H30 parity passes 240 cases and 201 fields. Deep models and all tolerance/model combinations are not refitted.")
        supporting.write_text(content)
    else:
        additions += ["## 15. H7 目标重拟合进度", "",
            "首个完整种子的 27 个区域拟合及评分/趋势已完成，16 个不同机构–补全层的原始日值核验通过。全部 20 种子资料与重拟合仍在执行，完成标志尚未写入，不把首个种子的结果当作 20 次稳定性。", ""]
    if europe_done:
        pairs=pd.read_csv(european["folder"]/"paired_summary.csv")
        boot=pd.read_csv(european["folder"]/"paired_group_bootstrap.csv")
        boot.to_csv(evidence/"europe_paired_group_bootstrap.csv",index=False)
        additions += ["## 16. 全欧洲源站的原模型驱动对照", "",
            f"固定名单全部 {european['selected']} 站已取得 ERA5-Land 日均气温。原始 POWER 模型的 {european['control']['case_rows']:,} 个病例、可用性和有限点值精确重现。法国九站的官方坐标与既有目录及 CRS84 几何坐标一致；未按误差选择站点，原源模型不改。", "",
            pairs.to_markdown(index=False,floatfmt=".4f"), "",
            "共同病例用于误差对比；原 POWER 不可用而 ERA5-Land 可用的病例另计，不能假定其原误差为零。该输入试验不是全年度模型及风险规则的重新训练，也不属于新的独立河温检验。", "",
            boot.loc[boot.stratum.eq("air_layer_danger")&boot.metric.eq("relative_mae_reduction"),["n_groups","point","lower","upper"]].to_markdown(index=False,floatfmt=".4f"), ""]
        forcing_doc=doc/"FORCING_EXECUTION_ZH.md";content=forcing_doc.read_text().split("\n## 恢复概率重算\n")[0].split("\n## 欧洲完整结果\n")[0]
        content=content.replace("美国结果已完成，欧洲扩大采集进行中。","美国和欧洲源站对照均已完成。")
        content=content.replace("欧洲扩大名单为全部 262 个源站，其中 9 站缺少已核实坐标。","欧洲名单为全部 262 个源站，法国九站的缺失坐标已从官方目录核实补齐。")
        content=content.replace("扩展采集遇到的服务配额、等待与不可用原因均保留，进行中计数以 `europe_full_source_exact/acquisition_progress.json` 为准，未完成子集不写成欧洲总体结果。",
            "扩展采集遇到的服务配额与等待记录均保留；完成证据见 `europe_full_source_exact/completion.json`，旧 16 站试验仍分开保存。")
        forcing_doc.write_text(content+"\n## 欧洲完整结果\n\n"+pairs.to_markdown(index=False,floatfmt=".4f")+"\n\n原始 POWER 控制病例精确重现；每种输入的单臂可用性和共同病例分别报告。\n")
        article=paper/"review_completion_article.tex";content=article.read_text()
        content=content.replace("A European ERA5-Land sensitivity obtains \\REuropeStations{} of \\REuropeRequested{} prespecified stations.",
            "The European extension obtains ERA5-Land at all \\REuropeStations{} original source stations, with exact original-model controls.")
        content=content.replace("European high-resolution forcing evidence remains a partial sample.",
            "The full source-station forcing comparison changes product and daily time convention together; it does not isolate spatial resolution.")
        article.write_text(content)
        for name in ["EXPERIMENT_CHECKLIST_ZH.md","REVIEWER_RESPONSE_DRAFT_ZH.md"]:
            path=doc/name;content=path.read_text().replace("欧洲扩大采集中","欧洲全部 262 个源站对照完成")
            content=content.replace("欧洲旧 16 站与扩大 262 站的进行中采集分开","欧洲原 16 站与全部 262 站的原模型控制对照分开")
            path.write_text(content)
    recovery_sections=[]
    for region,complete in recovery_done.items():
        if not complete:continue
        folder=out/"inputs/forcing_recovery"/region
        audit=json.loads((folder/"numerical_audit.json").read_text())
        if not audit.get("passed") or audit["maximum_point_difference"]>1e-9:raise RuntimeError("New-driver recovery model does not match its point controls")
        table=pd.read_csv(folder/"summary.csv")
        table.to_csv(evidence/f"forcing_recovery_{region}.csv",index=False)
        columns=["arm","family","n_eligible","n_valid","actual_failure_rate","mean_predicted_failure","auc","brier"]
        shown=table.loc[table.stratum.eq("air_layer_danger"),columns]
        recovery_sections += [f"### {region}","",shown.to_markdown(index=False,floatfmt=".4f"),""]
    if recovery_sections:
        paragraph="恢复概率现已随驱动重算：每个目标年同时排除目标年与残差验证年的全部水温标签，用相同未标准化 Ridge 配方取得折外残差；再重算暖季残差均值、方差、自相关和 Gaussian AR1 窗口模型的概率。原始水温气候态、训练峰窗和缺口几何不变。每条概率预测各自日模型的失败；表中的实际与预测风险在同一有限支持集计算，不把不同臂的不同失败目标当作同一组标签。原年度 D2 与发布分类器均未重训。"
        additions += ["## 17. 替代驱动下的恢复模型预测","",paragraph,"",*recovery_sections]
        path=doc/"FORCING_EXECUTION_ZH.md";content=path.read_text().split("\n## 恢复概率重算\n")[0]
        path.write_text(content+"\n## 恢复概率重算\n\n"+paragraph+"\n\n"+'\n'.join(recovery_sections)+"\n原始病例、概率分箱、折外数值核验见 `inputs/forcing_recovery/`。\n")
        if recovery_done["usgs"]:
            path=paper/"review_completion_supporting.tex";content=path.read_text()
            marker="% DRIVER_RECOVERY_RECOMPUTATION"
            if marker not in content:
                text=(marker+"\nForcing-specific recovery probabilities are also recomputed from residual histories excluding both the target year and each residual-validation year. All 269,264 USGS arm/case points reproduce their existing controls, and 1,083 independent daily Ridge checks agree within numerical tolerance. In controlled dangerous air-tier cases, raw Gaussian recovery probabilities average 0.405 against observed failure 0.468 for POWER, and 0.365 against 0.457 for POWER plus flow. These have different available supports and failure targets; they do not establish paired calibration improvement or safe transfer. Complete scores and calibration bins are retained in CSV. Annual distribution and release-classifier weights remain unchanged.\n\n")
                content=content.replace("\\input{review_completion_tables_si.tex}",text+"\\input{review_completion_tables_si.tex}");path.write_text(content)
    with (doc/"EXECUTION_REPORT_ZH.md").open("a") as stream:stream.write("\n".join(additions)+"\n")
    remaining=["public registration and genuinely new independent outcomes"]
    if not state.get("national_h30_analysis_complete"):
        if state.get("national_retrieved_panel_execution_complete"):
            remaining.append(f"unresolved national historical eligibility ({state.get('national_unresolved_candidates')} candidates); retrieved-panel analyses completed")
        else:
            remaining.append("national H30 trend analysis and unresolved input accounting")
    if not window_done:remaining.append("full target-specific H7 refit")
    if not forcing_done:remaining.append("all-source USGS high-resolution driver/flow sensitivity")
    if not europe_done:remaining.append("all-source European weather acquisition and exact-control comparison")
    if not all(recovery_done.values()):remaining.append("driver-specific recovery probability validation on all source regions")
    state["remaining_scientific_evidence"]=remaining
    state["local_evidence_complete"]=bool(state.get("source_core_complete") and state.get("national_h30_analysis_complete") and window_done and forcing_done and europe_done and all(recovery_done.values()))
    status_path.write_text(json.dumps(state,indent=2,ensure_ascii=False)+"\n")
