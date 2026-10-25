"""Report the retrieved national panel while preserving unresolved eligibility."""
from __future__ import annotations
import json
import pandas as pd


def national_evidence(out):
    folder = out / "national_meaning"
    if not (folder / "status.json").exists():
        return None
    status = json.loads((folder / "status.json").read_text())
    if not status.get("execution_complete_on_retrieved_panel"):
        return None
    acquisition = json.loads((folder / "acquisition.json").read_text())
    application = json.loads((folder / "application/status.json").read_text())
    if (not acquisition.get("all_planned_attempted") or acquisition.get("service_stop")
            or application.get("partial") or not application.get("application_complete")
            or not application.get("model_weights_unchanged")):
        raise RuntimeError("National reporting requires full acquisition and fixed-model application")
    panel = pd.read_parquet(folder / "application/annual_panel.parquet", columns=["station_id"])
    processed = panel.station_id.nunique()
    unknown = status["n_metadata_candidates"] - processed
    if (processed != status["n_numeric_processed_sites"]
            or processed != application["n_processed_stations"]
            or unknown != status["unresolved_or_no_annual_record_candidates"]
            or bool(status["complete"]) != (unknown == 0)):
        raise RuntimeError("National panel counts or unresolved-eligibility flag disagree")
    tables = {}
    for name in ["network_and_regional_summary", "field_significance", "spatial_coverage",
                 "hot_year_frequency_network_region", "same_roster_same_span_trends"]:
        tables[name] = pd.read_csv(folder / "application/meaning" / (name + ".csv"))
    coverage = tables["spatial_coverage"].set_index("rule")
    for rule, count in status["eligibility_lower_counts"].items():
        if rule not in coverage.index or coverage.loc[rule, "n_eligible_stations"] != count:
            raise RuntimeError("National eligibility differs from its geographical report")
        if status["eligibility_upper_counts_allowing_unresolved"][rule] != count + unknown:
            raise RuntimeError("National unknown-eligibility bounds disagree")
    return {"status": status, "tables": tables}


def finish_national_reporting(out, doc, paper):
    result = national_evidence(out)
    main = paper / "review_completion_national_results.tex"
    si = paper / "review_completion_national_details.tex"
    if result is None:
        main.write_text("% National retrieved-panel analysis pending.\n")
        si.write_text("% National retrieved-panel analysis pending.\n")
        return
    status, tables = result["status"], result["tables"]
    for name, table in tables.items():
        table.to_csv(out / "evidence" / ("national_" + name + ".csv"), index=False)
    lower = status["eligibility_lower_counts"]
    unknown = status["unresolved_or_no_annual_record_candidates"]
    counts = pd.DataFrame([{"rule": rule, "eligible_lower": n,
        "eligible_upper_allowing_unresolved": n + unknown} for rule, n in lower.items()])
    network = tables["network_and_regional_summary"]
    network = network.loc[network.huc2.isna()] if "huc2" in network else network
    network_by_rule = network.set_index("rule")
    geography = tables["spatial_coverage"].set_index("rule")
    paired = tables["same_roster_same_span_trends"]
    paired_raw = paired.loc[paired.rule.eq("retained_raw"), "difference"]
    paired_change = paired_raw.median()
    field = tables["field_significance"].set_index("rule")
    circular_p = field.loc[["complete15", "retained_raw"], "synchronized_circular_shift_p"]
    warming = bool(network_by_rule.loc[["complete15", "retained_raw"], "median_slope"].gt(0).all() and circular_p.lt(.05).all())
    field_sentence = ("Both rules retain field-significant network warming in the synchronized sensitivities. " if warming
                      else "The field tests and network directions require separate interpretation for the two rosters. ")
    events = tables["hot_year_frequency_network_region"]
    events = events.loc[events.huc2.eq("all")]
    text = ["## 全国取得面板的已核验结果", "",
        f"固定 {status['n_catalog_sites']:,} 个目录站、{status['n_metadata_candidates']:,} 个候选的请求已全部执行。数值面板包含 {status['n_numeric_processed_sites']:,} 站；另有 {unknown:,} 个候选无可解析年度面板，资格保持未知。下表给出未知候选均不合格/均合格两端的资格计数，不是全部美国河流的总体率。", "",
        counts.to_markdown(index=False), "",
        "趋势单位为 °C/十年。各规则的站点和年度支持不同，网络中位数不能解释为同站因果效应。同站同跨度、BH、同步置换/循环位移、区域和空间块结果另存 CSV。插补范围是条件模型敏感性，无自然缺口真值核验覆盖。", "",
        network.to_markdown(index=False, floatfmt=".4f"), "",
        f"完整年规则与保留估计的网络趋势中位数分别为 {network_by_rule.loc['complete15','median_slope']:.4f}/{network_by_rule.loc['retained_raw','median_slope']:.4f} °C/十年；共同 {len(paired_raw)} 站、相同时间跨度的趋势变化中位数为 {paired_change:.4f} °C/十年。两种处理的同步循环位移场检验 p 值分别为 {circular_p.loc['complete15']:.6f}/{circular_p.loc['retained_raw']:.6f}。站数增加或不同名单的中位数差不能当作已验证的趋势偏差修复。", "",
        tables["field_significance"].to_markdown(index=False, floatfmt=".4f"), "",
        "1° 网格占据数描述监测站地理范围，不是流域面积；未知资格进入网格数上界。", "",
        tables["spatial_coverage"].to_markdown(index=False), "",
        "各方法共用 1981–2010 年至少五个完整批准年 H30 的站点第 90 百分位阈值。参照不足不填零；观测窗口热年频率下界不依赖插补。", "",
        events.to_markdown(index=False, floatfmt=".4f"), "",
        f"原始连续观测窗口在 {status['observed_record_stations']} 站、{status['observed_record_station_years']} 个不完整站年超过完整年纪录。见证及完整参照已回查原生日值；这只反证该报告序列的完整年纪录归属，不识别唯一物理最热年。", ""]
    document = doc / "NATIONAL_EXECUTION_ZH.md"
    prefix = document.read_text().split("\n## 全国取得面板的已核验结果\n")[0]
    prefix = prefix.replace("当前采集进程另由", "本次采集与后续分析由")
    prefix = prefix.replace("等待。它只在", "接续执行并已结束。它只在")
    document.write_text(prefix + "\n" + "\n".join(text) + "\n")
    report = doc / "EXECUTION_REPORT_ZH.md"
    content = report.read_text()
    start = content.index("## 10. 全国"); finish = content.index("## 11.", start)
    content = content[:start] + "\n".join(text).replace("## 全国取得面板的已核验结果", "## 10. 全国取得面板的已核验结果", 1) + "\n" + content[finish:]
    report.write_text(content.replace("全国时间可用性仍在采集。", "全国取得面板的分析已完成，未解析资格保留上下界。"))
    main.write_text(
        f"The metadata-fixed national USGS extension attempts all {status['n_metadata_candidates']:,} candidates within a {status['n_catalog_sites']:,}-site catalog. "
        f"The retrieved annual panel contains {status['n_numeric_processed_sites']:,} sites, with eligibility unresolved for {unknown:,} candidates. "
        f"At least fifteen statistic years are available at {lower['complete15']:,} sites under complete-year selection and {lower['retained_raw']:,} under retention with estimation. "
        f"Occupied one-degree station cells increase from {int(geography.loc['complete15','occupied_cells_lower'])} to {int(geography.loc['retained_raw','occupied_cells_lower'])}. "
        f"Network median slopes are {network_by_rule.loc['complete15','median_slope']:.3f} and {network_by_rule.loc['retained_raw','median_slope']:.3f} degrees C per decade; the same-roster/span median contrast is {paired_change:.4f}. "
        + field_sentence +
        f"Observed thirty-day windows exceed the complete-year record at {status['observed_record_stations']:,} sites in {status['observed_record_station_years']:,} incomplete station-years. "
        "These network descriptions retain unknown-eligibility bounds; they neither represent all US rivers nor validate natural-gap imputation accuracy. Supplementary files report spatial coverage, hot-year frequency, same-roster contrasts and field significance.\n")
    si.write_text(
        "The national extension fixes one canonical mean-temperature series per catalog site before numerical analysis, without combining sensors. "
        f"All {status['n_metadata_candidates']:,} candidates are attempted; {unknown:,} retain unresolved eligibility. "
        "National CSVs give eligibility bounds, one-degree station-grid occupancy, HUC2 counts, trends, basin-block stability, BH and synchronized field tests. "
        "Hot-year methods share a station threshold from the 90th percentile of at least five complete approved 1981--2010 H30 values; insufficient references remain unavailable. "
        "Same-roster/span and common-year comparisons separate added support from changed values. Observed windows provide hot-frequency lower bounds and record witnesses without imputation. "
        "Conditional imputation ranges are model sensitivities, not validated confidence coverage.\n")
    article = paper / "review_completion_article.tex"
    article.write_text(article.read_text().replace("It has not completed national H30 inference and is not new independent validation.",
        "The retrieved-panel analysis retains unresolved eligibility bounds and is not new independent validation."))
    checklist = doc / "EXPERIMENT_CHECKLIST_ZH.md"
    content = checklist.read_text().replace("面板完成，全国源域采集及后续流水线运行中", "面板与全国取得面板完成，未知资格保留上下界")
    content = content.replace("日期/审批核查按服务配额续取；尚无全国 H30 趋势。", "全国取得面板的 H30、空间覆盖、热年频率与场显著性已计算，未知资格给上下界。")
    content = content.replace("全国时间可用性普查仍采集，不声称全国物理趋势结论。", "全国取得面板的敏感性已计算，未知资格保留上下界，不声称全部河流的物理趋势。")
    checklist.write_text(content)
    submission = doc / "SUBMISSION_CHECKLIST_ZH.md"
    submission.write_text(submission.read_text().replace("日期/审批普查仍续取；尚无全国 H30 趋势", "全国取得面板已分析；未知资格给上下界，不外推全部河流"))
    path = out / "evidence/completion_status.json"
    state = json.loads(path.read_text())
    state.update(national_retrieved_panel_execution_complete=True, national_unresolved_candidates=unknown)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
