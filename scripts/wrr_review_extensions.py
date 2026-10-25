"""Reporting for the remaining review requirements; consumes computed evidence."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd


def finish_extensions(out,doc,paper,tex_table):
    evidence=out/"evidence"
    deletion=pd.read_csv(out/"robustness/group_deletions_all_seeds.csv")
    historical=pd.read_csv(out/"robustness/historical_N1_deletions.csv")
    ss=pd.read_csv(out/"semi_rcps/summary.csv")
    conditional=pd.read_csv(out/"conditional_conformal/rules_all_seeds.csv")
    regional=pd.read_csv(out/"regional_rankings/same_roster_same_span_summary.csv")
    records=pd.read_csv(out/"observed_records/summary.csv")
    record_design=json.loads((out/"observed_records/design.json").read_text())
    planning=pd.read_csv(out/"independent_study/sample_size_planning.csv").set_index("independent_groups")
    assert deletion.seed.nunique()==20 and conditional.seed.nunique()==20
    assert {"coarse_overlapping_groups_randomized","held_region_group_randomized"}.issubset(conditional.method.unique())
    assert json.loads((out/"conditional_conformal/design.json").read_text())["implementation_version"]=="group-units-v4-binary-LAC"
    rows=[]
    for labels,b in deletion.groupby(["family","rule","reference","endpoint"]):
        x=b.minimum_groups.dropna()
        rows.append(dict(zip(["family","rule","reference","endpoint"],labels),repeats=b.seed.nunique(),
                         finite_minimum_repeats=len(x),already_failed=int(b.status.isin(["already_above_cap","no_initial_qualified_advantage"]).sum()),
                         minimum_median=float(x.median()) if len(x) else np.nan,minimum_low=float(x.min()) if len(x) else np.nan,minimum_high=float(x.max()) if len(x) else np.nan))
    ds=pd.DataFrame(rows);ds.to_csv(evidence/"group_deletion_summary.csv",index=False)
    cr=[]
    for labels,b in conditional.groupby(["family","method","nominal_coverage"]):
        admitted_mass=float(b.retention_group_equal.mean())
        failed_mass=float(b.false_admission_frequency_group_equal.mean())
        cr.append(dict(zip(["family","method","nominal_coverage"],labels),seeds=b.seed.nunique(),
                       region_mean_retention=admitted_mass,region_mean_coverage=float(b.coverage_group_equal.mean()),
                       selected_risk_group_mixture=failed_mass/admitted_mass if admitted_mass else np.nan,
                       region_mean_false_admission_frequency=failed_mass,
                       region_mean_case_weighted_retention=float(b.retention_case_weighted.mean()),
                       n_admitted=int(b.n_admitted.sum()),median_calibration_groups=float(b.n_calibration_groups.median()),
                       maximum_solver_fallback=float(b.solver_fallback_fraction.max()),
                       selected_risk_nonempty_region_median=float(b.risk_case_weighted.median())))
    cs=pd.DataFrame(cr);cs.to_csv(evidence/"formal_conditional_summary.csv",index=False)
    cs["max_solver_fallback_percent"]=100*cs.maximum_solver_fallback
    ss.to_csv(evidence/"formal_semi_rcps_summary.csv",index=False)
    computed=regional.loc[regional.status.eq("computed")]
    computed.to_csv(evidence/"same_roster_regional_summary.csv",index=False)
    records.to_csv(evidence/"observed_record_summary.csv",index=False)
    probability=pd.read_csv(out/"probability_ablation/summary.csv")
    probability.to_csv(evidence/"probability_calibration_ablation.csv",index=False)
    trend=pd.read_csv(evidence/"trend_summary_per_seed.csv")
    stability=pd.read_csv(evidence/"trend_robustness_per_seed.csv")
    p4=[]
    for (seed,scenario),b in trend.groupby(["seed","scenario"]):
        learned=b.loc[b.pipeline.eq("D2_multiple_imputation")].iloc[0]
        reference=b.loc[b.pipeline.eq("A1")].iloc[0]
        reduction=float(stability.loc[stability.seed.eq(seed)&stability.scenario.eq(scenario),"rmse_reduction"].iloc[0])
        covariance=float(learned.missing_component_coverage)
        p4.append(dict(seed=seed,scenario=scenario,rmse_reduction=reduction,missing_component_coverage=covariance,total_interval_coverage=float(learned.coverage),
                       criterion_met=bool(reduction>=.2 and abs(learned.bias)<=abs(reference.bias)+.01 and .90<=covariance<=.97),
                       status="exploratory redesigned stress analogue; historical P4 unchanged"))
    p4=pd.DataFrame(p4);p4.to_csv(evidence/"P4_analogue_per_seed.csv",index=False)
    p4_summary=p4.groupby("scenario").agg(repeats=("seed","nunique"),passing=("criterion_met","sum"),missing_coverage_median=("missing_component_coverage","median"),total_coverage_median=("total_interval_coverage","median"),rmse_reduction_median=("rmse_reduction","median")).reset_index()
    p4_summary.to_csv(evidence/"P4_analogue_summary.csv",index=False)
    exposure_path=out/"air_exposure/summary_all_seeds.csv"
    exposure_summary=pd.DataFrame();exposure_release=pd.DataFrame()
    if exposure_path.exists() and (out/"air_exposure/design.json").exists():
        raw=pd.read_csv(exposure_path)
        exposure_summary=raw.loc[raw.pipeline.notna()].groupby(["condition","scenario","pipeline"]).agg(
            mask_seeds=("seed","nunique"),rmse=("rmse","median"),bias=("bias","median"),
            missing_coverage=("missing_component_coverage","median"),total_coverage=("total_coverage","median")).reset_index()
        exposure_release=pd.read_csv(out/"air_exposure/release_metrics_all_seeds.csv").groupby(["condition","family"]).agg(
            mask_seeds=("seed","nunique"),retention=("retention","median"),risk=("risk","median"),
            groups_above_10=("fraction_groups_above_10","median"),worst_group_risk=("worst_group_risk","median")).reset_index()
        exposure_summary.to_csv(evidence/"air_exposure_trends_summary.csv",index=False)
        exposure_release.to_csv(evidence/"air_exposure_release_summary.csv",index=False)
    observed_path=out/"inputs/observed_air_full_source_exact/paired_summary.csv"
    observed=pd.DataFrame()
    if observed_path.exists():
        observed_audit=json.loads((observed_path.parent/"original_core_control_audit.json").read_text())
        if not observed_audit.get("exact_source_verified"):raise RuntimeError("Nearby observed-air benchmark has not reproduced its original source control")
        observed=pd.read_csv(observed_path)
        observed.to_csv(evidence/"observed_air_full_source_summary.csv",index=False)
    full_forcing_path=out/"inputs/forcing_full_source_exact/paired_summary.csv"
    full_forcing=pd.DataFrame()
    if full_forcing_path.exists():
        forcing_audit=json.loads((full_forcing_path.parent/"original_core_control_audit.json").read_text())
        if not forcing_audit.get("exact_source_verified"):raise RuntimeError("Full-source forcing control has not reproduced the original source")
        full_forcing=pd.read_csv(full_forcing_path)
        full_forcing.to_csv(evidence/"forcing_full_source_summary.csv",index=False)
    from wrr_review_forcing_reporting import europe_evidence
    european=europe_evidence(out)
    european_forcing=pd.DataFrame()
    if european["full_source"]:
        european_forcing=pd.read_csv(european["folder"]/"paired_summary.csv")
        european_forcing.to_csv(evidence/"europe_full_source_summary.csv",index=False)

    macros={"RRecordDenominator":record_design["eligible_stations"],"RRecordStationYears":int(records.loc[records.margin_c.eq(0),"n_station_years"].iloc[0]),
            "RRecordStations":int(records.loc[records.margin_c.eq(0),"n_stations"].iloc[0]),"RRecordHalfStations":int(records.loc[records.margin_c.eq(.5),"n_stations"].iloc[0])}
    with (paper/"review_completion_claims.tex").open("a") as stream:
        for name,value in macros.items():stream.write("\\newcommand{\\"+name+"}{"+str(value)+"}\n")
        for budget,name in [(20,"Twenty"),(40,"Forty"),(100,"Hundred"),(200,"TwoHundred")]:
            stream.write("\\newcommand{\\RPlan"+name+"}{"+f"{100*planning.loc[budget,'joint_E1_E2_probability']:.1f}"+"}\n")
    si=(paper/"review_completion_tables_si.tex").read_text()
    selected=ds.loc[ds.reference.ne("one_feature_50")&ds.endpoint.eq("retention_advantage_lost")]
    si+=tex_table(selected,"Exact frozen-admission deletion sensitivity. The best published comparator is fixed using opened full-data outcomes at a 5 percent point-risk cap. A zero is an initial failure; unavailable reversal minima remain undefined.","tab:group-deletions",
                  ["family","rule","repeats","finite_minimum_repeats","already_failed","minimum_median"])
    si+=tex_table(historical,"Historical opened N1 uses a 7 percent point-risk criterion. Fixed-admission minima and batch-rule reapplication at the witness answer different questions; historical verdicts do not change.","tab:historical-n1-deletion",
                  ["population","n_groups","minimum_groups","remaining_risk","reapplied_witness_risk"])
    si+=tex_table(cs,"Conditional conformal prediction-set comparators over twenty seeds. Conditional coverage targets false-admission frequency per eligible representative, not selected risk. Region means are descriptive under held-region shift; empty releases have undefined selected risk.","tab:formal-conditional",
                  ["family","method","nominal_coverage","seeds","region_mean_retention","region_mean_coverage","selected_risk_group_mixture","max_solver_fallback_percent"])
    si+=tex_table(probability,"Identical classifier and cap: isolate Platt probability calibration from its additional empirical overlapping-group factors. These are exploratory source repetition medians, not the formal conditional-conformal algorithm.","tab:probability-ablation")
    for family in ["calendar","crossed"]:
        si+=tex_table(ss.loc[ss.family.eq(family)],"General-loss semi-supervised and labeled-only RCPS with WSR bounds. The unit is an independent group. Distinct unlabeled calibration groups and untouched test groups are required.","tab:formal-semi"+family,
                      ["method","budget_groups","n_runs","nonempty_fraction","unlabeled_budget_insufficient"])
    si+=tex_table(computed,"Same-roster and same-span regional sensitivity, 1981--2025. Annual means require 80 percent fixed-roster support. Common-year and expanded-year rankings differ. Regions with fewer than three independent groups have no bootstrap interval.","tab:same-roster-ranks",
                  ["region","n_stations","n_groups","common_years","top_complete","top_retained","difference_of_regional_medians"])
    si+=tex_table(records,"Observed-window record certificates among "+str(record_design["eligible_stations"])+" stations with at least fifteen complete observed years in 1981--2025. Each incomplete-year lower bound exceeds every complete-year H30 at the same station; it need not be the unique full-record maximum.","tab:observed-records")
    si+=tex_table(planning.reset_index(),"Source-only joint E1/E2 planning across all twenty algorithm and group-composition repetitions. Each budget has 40,000 empirical group simulations. Seed quantiles do not represent independent-climate uncertainty; E1 uses a planning delta approximation.","tab:joint-planning")
    si+=tex_table(p4_summary,"Exploratory redesigned P4 analogues. Original numeric criteria require RMSE reduction at least 20 percent, bias no worse by over 0.01 degrees per decade, and missing-component coverage 90--97 percent. Total interval coverage cannot substitute for missing-component coverage. Historical P4 is unchanged.","tab:p4-analogue")
    if len(exposure_summary):
        display=exposure_summary.loc[exposure_summary.pipeline.isin(["A1","D2_multiple_imputation","stochastic_calibrated_MI"])].copy()
        display["condition"]=display.condition.map({"clean":"Clean","unflagged_air_exposure":"Air"})
        display["scenario"]=display.scenario.map({"mcar":"Random","strong_heat":"Heat"})
        si+=tex_table(display,"Unflagged visible-air exposure: medians of three mask/trajectory seeds with clean source-fit seed zero held fixed. Missing-component and total coverage refer to 95 percent trend intervals. Air replaces seven consecutive visible warm-day water readings; the underlying target remains defined. Random and strongly heat-associated missingness have matched marginals. Censored trends are omitted because contaminated windows are no longer valid lower bounds. This is synthetic measurement contamination, not dry-bed water truth or twenty-fit stability.","tab:air-exposure-trends",
                      ["condition","scenario","pipeline","rmse","bias","missing_coverage","total_coverage"])
        release_display=exposure_release.copy();release_display["condition"]=release_display.condition.map({"clean":"Clean","unflagged_air_exposure":"Air"})
        si+=tex_table(release_display,"The same clean source failure classifier and individual cap 0.1 under unflagged air exposure. Three mask/trajectory seeds share one source fit. Group risks require at least twenty admissions; no contaminated labels recalibrate the score.","tab:air-exposure-release",
                      ["condition","family","retention","risk","groups_above_10","worst_group_risk"])
    if len(observed):
        forcing_display=observed.rename(columns={"observed_TAVG_mae":"alternative_mae"}).assign(product="NOAA TAVG")
        if len(full_forcing):
            forcing_display=pd.concat([full_forcing.rename(columns={"arm":"product"}),forcing_display],ignore_index=True)
        if len(european_forcing):
            forcing_display=pd.concat([forcing_display,european_forcing.rename(columns={"arm":"product"})],ignore_index=True)
        forcing_display["product"]=forcing_display["product"].replace({"POWER_flow":"POWER + flow"})
        forcing_display["stratum"]=forcing_display["stratum"].replace({"all":"All","danger":"Danger","air_layer_danger":"Air, danger"})
        forcing_display=forcing_display.rename(columns={"product":"Input","stratum":"Stratum","n_eligible":"Eligible","n_paired":"Paired","n_paired_stations":"Stations","POWER_mae":"POWER MAE","alternative_mae":"Alternative MAE"})
        europe_caption=(f" The European extension covers all {european['selected']} source sites, with {european['control']['case_rows']:,} exact original POWER control identities." if european["full_source"] else "")
        si+=tex_table(forcing_display,"Matched forcing sensitivities at all 319 benchmarkable USGS source sites. MAE is in degrees C. Exact original panels, forcing and daily Ridge code reproduce all 67,316 POWER control identities and available points."+europe_caption+" Each alternative has its own shared-case reference; different rows must not be compared as if they used one sample. Missing inputs stay in eligible denominators. Daymet uses a minimum/maximum midpoint; daily time conventions also vary. Nearby TAVG is not a perfect co-located or clock-matched oracle.","tab:observed-air-source",
                      ["Input","Stratum","Eligible","Paired","Stations","POWER MAE","Alternative MAE"])
    (paper/"review_completion_tables_si.tex").write_text(si)
    with (paper/"review_completion_tables_main.tex").open("a") as stream:
        stream.write(tex_table(records,"Observed-window record attribution on reported daily series, with no imputation. The eligible population contains "+str(record_design["eligible_stations"])+" stations and at least fifteen complete observed years per station in 1981--2025. Positive excess means the complete-only record cannot be the full-record maximum.","tab:observed-record-main"))

    def table(b,cols=None):return (b if cols is None else b[cols]).to_markdown(index=False,floatfmt=".4f")
    text=["", "## 8. 补齐的删除审计与正式校准对照", "",
          "组删除审计已覆盖全部 20 个种子，并用穷举小问题核验整数规划。这里冻结已拟合预测及原放行集合，和 P4 的冻结误差删除审计一致；不冒充删除组后重训练整个系统。比较对象是在完整已打开评估集上、实际风险 ≤5% 的最佳已发表规则，或固定单特征规则。这个比较对象选择使用了评估标签，因而只作影响诊断。", "",
          table(selected,["family","rule","finite_minimum_repeats","already_failed","minimum_median","minimum_low","minimum_high"]), "",
          "真实日历中，逐例上限 0.1 相对最佳已发表规则的留存优势，最少删除组数中位 150.5/185；相对单特征规则为 104/185。受控缺口下，集合规则本来已超过 5% 风险，删除数为 0，不能以留存高称其胜出。", "",
          "历史新 USGS 的 N1 原始点风险与留存已逐项重现。冻结原放行集合时，两类缺口都需删 10/40 组才越过原 7% 风险线；但在这两组删除方案上重新应用集合规则，风险分别是 5.56% 和 6.20%，仍不过线。因此 10 是冻结放行集合的精确敏感性，不能叫重新运行批量决策的最小翻转数。原 N1 判定保留。", "",table(historical,["population","minimum_groups","full_risk","remaining_risk","reapplied_witness_risk"]), "",
          "已运行 Gibbs–Cherian–Candès 正式有限基条件保形对照，使用标准二分类 LAC 分数、作者的 `conditionalconformal==0.0.4`、等价边界线性规划及独立组代表病例，未把重叠组经验乘数冒充该方法。保守与逐病例独立随机化两版分开；后者按原论文的均匀对偶阈值实现，不共享一个组硬币来代替病例随机化。表内选中风险是同一地区等权、组等权抽样混合下的误放质量除以放行质量；不以非空区域的风险均值代替这个比值。", "",
          table(cs), "",
          "预测集合覆盖保证约束的是组内总体的误放频率。即使只在预测集合为 `{不失败}` 时发布，`P(失败且发布|组) ≤ α` 也不能推出 `P(失败|发布,组) ≤ α`。未见过的完整区域指示变量没有源校准支持，非随机版退化成全集，随机版为全集或空集，都无法单值发布。粗组版本也不保证任意新区域；源区和留区代表的可交换性尚未成立。", "",
          "Einbinder–Ringel–Romano 的一般损失半监督 RCPS（算法 1）和有限样本 WSR 上界（算法 4）已按独立组实现并跑完 20 个种子。损失用 `B_g + 0.05(1-A_g)`，对应组等权选中风险比 `E[B_g]/E[A_g]`。校准、无标签校准、测试组互斥；无标签组不够时单列，不重复使用同一组凑独立样本。两个方法在现有 2–16 标签组预算中均无非空证书。旧正态 PPI 仍只是平均风险诊断，不能借用这个新增方法的有限样本保证。", "",
          table(ss), "",
          "全局概率校准与额外的组经验因子也已分开消融：此前“组校正”同时包含 Platt 概率映射，不能把相对原始分类分数的全部变化归因给分组。三条规则用相同预测值、相同病例、相同 0.1 上限比较。", "",table(probability), "",
          "## 9. 同站同时间跨度与观测纪录证据", "",
          "趋势不确定性的完整关口也已重核：随机缺测与强热情景下，分布回归 MI 的 95% 缺测分量区间覆盖中位仅约 79.2%/79.6%，总趋势区间却接近 100%。按历史 P4 的数值标准套用到这些探索性重设计压力情景，20 次均未过关。历史 P4 原判定保留；新的 RMSE 收益不能替代缺测不确定性的校准。经典校正随机 MI 的缺测分量覆盖约 72.5%/72.7%，同样不合格。年度边际区间近似校准，不意味着趋势联合误差区间已经校准。", "",table(p4_summary), "",
          "补充了固定站点名单、两种处理完全相同的站点时间边界，以及共同可用年份和扩展年份集的区域最热年排名。巴伐利亚、USGS HUC03 和 HUC04 的最热年点排名分别从 2022→2018、2011→2010、2020→2012；只比较两法都达到固定名单 80% 支持的共同年份时，三者原最热年均不变。这些变化主要来自纳入了原先被排除的年份。它们是已打开面板的推断敏感性，不是已确认的真实全区域纪录。", "",
          table(computed,["region","n_stations","n_groups","common_years","top_complete","top_retained","difference_of_regional_medians","median_paired_station_difference"]), "",
          "更直接的证据不需要任何插补：在 1981–2025 年有至少 15 个完整观测年的 "+str(record_design["eligible_stations"])+" 个站中，20 个站的 35 个不完整年，存在原始日值连续完整的 30 日窗口，其均值已经超过该站所有完整年的 H30；6 个站超过至少 0.5°C。全部完整年参照 H30 和 30 日日值见证都从原始 `water_c` 重新核验。旧“最热完整年”因此不可能是这些报告序列的全记录最热年；尚不能证明某个不完整年就是唯一真正的最热年，因为别的不完整年仍可能更热。", "",
          table(records), "",
          "这一观测证据闭合了“哪个结论改变”的有限面板例子，也进一步说明保留年份的价值不依赖 D2。窗口原始 30 个日值、日期、完整年参照和超出下界保存在 `observed_records/observed_record_certificates.csv`；不将报告序列的逻辑界宣称为无测量误差的物理真值。", ""]
    national_path=out/"national_availability/summary.json"
    national=json.loads(national_path.read_text()) if national_path.exists() else None
    transition_path=out/"national_availability/phase_transition_to_source_values.json"
    if transition_path.exists():
        transition=json.loads(transition_path.read_text());old_progress=transition["last_progress"]
        current_path=out/"national_meaning/progress.json"
        current=json.loads(current_path.read_text()) if current_path.exists() else {}
        text += ["## 10. 全国资料范围、采集阶段与未完成项", "",
                 f"全国元数据范围仍固定为 4,285 个 USGS 河流及渠系目录站，1,273 个有十五年日期支持潜力或范围未知的主日均序列。纯日期阶段最后记录处理 {old_progress['processed_sites']} 个、解析 {old_progress['date_calendars_resolved']} 个日历；其原始文件完整保留。该控制进程因后续 H30 所需数据合并而明确停止，未因安静或观察超时重启。", "",
                 f"后续 `500` 在同一元数据名单上获取日值与审批，使用官方文档支持的 50,000 条请求并防止旧版 10,000 条上限截断，沿用已知 Retry-After。最新输入进度文件（{current.get('updated_utc','not yet recorded')}）记录处理 {current.get('processed_sites',0)} / {current.get('requested_sites',1273)} 个；这是包含数值的已打开源域分析，不再称为纯日期或独立盲检验。新西兰独立队列的水温仍未请求。", "",
                 "原生日期、机构审批、数值可用性和真正未报告日期分别记录；provisional 不重编码为实际缺测。固定源年度模型及区间校准不重训，局地日补全仍按既定其他年份配方拟合。尚未拿到全范围资料和完整全国 H30 分析，不把缓存或小批试运行当全国率。资格无法核实时给出未知分母和上下界，不以空响应冒充已证明没有历史资料。", "",
                 "501 按 NASA POWER 原生气象网格和本地太阳时归并请求；已有 82 组同单元旧缓存的公共日期数值完全一致，旧源气温可复用。POWER 日值默认 LST，不能误称 UTC。502/503 的小批管线检查与完整全国运行分目录；只有资料、气温和模型输入范围一致才可进入完整分析，未知资格不能使完成关口变绿。", ""]
    elif national is not None:
        resolved=national.get("availability_resolved_sites",national.get("calendar_qualified_sites",0))
        text += ["## 10. 全国可用性分母与未完成项", "",
                 f"已有全国目录固定了 {national['national_stream_sites']} 个 USGS 河流站的规范主日均水温序列；按 1981–2025 年时间支持筛选，有 {national['metadata_possible_15year_sites']} 个可能达到 15 年或跨度未知的站需要逐日可用性核查，其余可由元数据排除。最近完成批次已解析 {resolved} 个日期/审批日历，另有 {national['unresolved_sites']} 个尚未解析；当前数字是非随机完成子集，不能外推成全国通过率。采集程序按服务 `Retry-After` 等待续页并保存检查点。", "",
                 "请求明确只有 `time,approval_status`，日期型字段保持机构本地日期，不把 YYYY-MM-DD 当 UTC 后错移一天。临时未批准观测不重编码为缺测；此类年份不能用于严格批准资料资格。全国 H30 趋势尚未计算，本轮未请求新站水温值。", ""]
        progress_path=out/"national_availability/progress.json"
        if progress_path.exists() and not national.get("all_metadata_possible_sites_resolved"):
            progress=json.loads(progress_path.read_text())
            text += [f"续取进度文件（{progress.get('updated_utc')}）另记录：已处理 {progress.get('processed_sites')} / {progress.get('requested_sites')} 个待核站，已解析 {progress.get('date_calendars_resolved')} 个日期日历。该进度不替代上面最近完整批次的逐站资格汇总；两者都不是全国通过率。", ""]
    screening=out/"independent_study/horizons_metadata/qualification_summary.json"
    if screening.exists():
        meta=json.loads(screening.read_text())
        text += ["## 11. 新候选元数据资格与注册执行边界", "",
                 f"Horizons 的 WaterTemperature 集合已逐站核查 {meta['collection_sites']} 个站、{meta['series_rows']} 条审查记录，全部请求为目录、测量类型、可用范围或站点属性；没有水温观测请求。当前公开连续档案中，满足四个七月至六月热年时间支持并符合河流元数据要求的潜在候选为 {meta['potentially_eligible_sites']} 个。检查记录、湖泊与不明类型不算连续河流资料。这个零不是预测失败率，而是该公开档案不满足既定采样资格。", "",
                 "替补顺序在任何新水温值之前固定为 Greater Wellington 的公开连续档案；后续是否合格仍由元数据和登记后的固定质控决定，不看模型误差补站。独立组不能从站点数推算；按机构管理区保守合并并把水温供体限制在合并区内，跨区天气和误差的独立/交换性仍是假设。", "",
                 "新增 494–498 的元数据、固定源模型分析、原生采集/病例与名单冻结入口。OSF 检查显式固定 API 版本，要求已接受公共注册及其存档附件字节匹配；可编辑原项目的同名文件不能替代注册快照。采集方案、名单、源模拟配置和分类器目标均已本地固定，仍无公共登记，所以在任何新河温请求前停止。文件核查用于确定公开附件的版本，登记时间始终以 OSF 平台为准。E1/E2 的空放行、无标签及组不足均不能算通过；E3/E4 输出预定点标准，当前小队列的十标签组 E5 事前不可实施。", "",
                 "主参照只使用规则日内采样完整且机构质量码为 600 的日值，使用固定 NZST（UTC+12）而非有夏令时的城市时钟；所有候选 TimeRange 均确认 +12。未知、合成和检查记录不算完整参照。气温固定用 ERA5-Land 小时值同钟聚合。日内水温/质量解析已在合成输入上验证，天气小时接口只查了两天完整原生气温日；新水温接口和完整年资格须待公共登记后检验。固定推断入口也已在 540 条已打开源病例上检查记分卡与端点接口，未改动源模型，但这不是新区域结果。", ""]
        other=out/"independent_study/greater_wellington/qualification_summary.json"
        if other.exists():
            m=json.loads(other.read_text())
            text += [f"Greater Wellington 元数据结果：已解析 {m['collection_sites']} 个目录站，潜在合格 {m['potentially_eligible_sites']} 站，保守管理区合并 {m['potential_conservative_groups']} 组。日期支持不证明完整观测年，管理区也不自动等于独立水文单元；未据此声称 E1/E2 已有统计功效。", ""]
    if len(exposure_summary):
        text += ["## 12. 传感器空气暴露的测量污染压力", "",
                 "三个普通掩码/轨迹种子 0、1、2 使用相同的干净源拟合种子 0；所有外区模型、分类器和区间偏移固定，没有用污染标签重训。这不是三个新模型划分，更不是 20 次稳定性证明。新旧病例、遮罩和真实 H30 逐条相同，约 97.6% 的病例可在可见暖季放入连续七天暴露，替换日气温比真实水温平均高约 2.3°C。暴露窗口只由可见性、暖季和气温选，不用隐藏水温。", "",
                 "只在被抽为不完整的年份使用污染输出，完整年仍为原观测；因此随机缺测与最热十分位 0.90/其他 0.18 的强热缺测可配对比较。这里仍有定义明确的水温目标，模拟的是未标记的空气暴露记录；真正干涸河床不存在可要求恢复的水温真值。删失趋势不在这项压力里重跑，因为污染窗口已不能提供有效的物理下界；原干净源域的删失对照保留。", "",
                 table(exposure_release), "",table(exposure_summary.loc[exposure_summary.pipeline.isin(["A1","D2_multiple_imputation","stochastic_calibrated_MI"])]),"",
                 "这个压力中，源 0.1 上限的真实日历放行失败率从约 0.7% 升到 36.9%，留存仍达 95.0%；受控缺口失败从约 4.9% 升到 37.9%。强热情景下，D2 MI 缺测分量覆盖从约 80% 降至 16.1%，相对 A1 的 RMSE 收益缩至约 8%。源种子 0 的干净对照与原分析 552 个共同记分格的十项指标完全一致，见 `air_exposure/source_control_parity.json`。", "",
                 "这些结果只检验固定严重程度、未被质量标记的观测污染，不估计现场暴露发生率，也不用来重新挑选源阈值或更换独立队列。独立检验的完整原生日和机构质量码要求已事前固定；通过缺测完整度规则不等于通过测量质量检查。", ""]
    if len(observed):
        text += ["## 13. 邻近实测气温与日历滞后核查", "",
                 "NOAA GHCN-Daily TAVG 的匹配已扩展到全部 319 个可评估 USGS 源站：仅按距离 ≤25km 和记录范围选最近站，147 站元数据合格，122 站实际有共同可用病例。非空 QFLAG 不进入天气输入，不在误差结果后换第二近站。Source S 是截至 2400 UTC 的平均，其他来源时间约定不一，因此这是附近实测输入敏感性，不是河岸完全同钟真值或完美上限。", "",
                 "初始 float32/截取过的日表与原始输入历史不同；最终改回各个河网—站点的原始全精度水温面板及站点气温，并调用原始 StationModels。21 个物理站有两个源输入河网，不能用站号代替输入身份。全部 67,316 个 POWER 控制病例的可用性和点值精确重现，最大差为 0，见 `original_core_control_audit.json`。", "",table(observed), "",
                 "气温层危险病例共同 3,010 例、112 个物理站，H30 MAE 约 0.678→0.671°C，逐站不差比例约 50.9%；未见普遍的大幅改进。隐藏日 MAE 在完全相同病例和日子上配对；全年日指标另用双方同日可用的记录，不拿不同覆盖率的两组 R² 比较。", "",
                 "原驱动消融的稀疏日序列会按行而非日历移动。现先建立每日索引，再计算气温及流量滞后；没有给缺日填数。不可用输入逐病例保留，原 18,033 行变为 18,717 行，各 arm 6,239 病例。原始 POWER 控制不变；Daymet 气温危险配对由 1,165 变为 1,159，MAE 0.804/0.815°C，仍未优于 POWER。第一次输出备份晚于重写，因此没有宣称保住旧输出原始字节；旧算法从既存附件中的脚本与同一缓存另行重现，其 1,165 与 0.817450 数字和旧文相符。对照及代码摘要见 `inputs/calendar_lag_correction_audit.json`。", ""]
    from wrr_review_flow_reporting import finish_flow_reporting
    text += finish_flow_reporting(out,doc,paper)
    from wrr_review_focused_reporting import finish_focused_reporting
    text += finish_focused_reporting(out,doc,paper)
    from wrr_review_zero_flow_reporting import finish_zero_flow_reporting
    text += finish_zero_flow_reporting(out,doc,paper)
    with (doc/"EXECUTION_REPORT_ZH.md").open("a") as stream:stream.write("\n".join(text)+"\n")
    status_path=evidence/"completion_status.json";state=json.loads(status_path.read_text())
    state["source_core_complete"]=True
    state["additional_local_experiments"]={"group_deletion_seeds":int(deletion.seed.nunique()),"conditional_conformal_seeds":int(conditional.seed.nunique()),"formal_semi_rcps_seeds":len(json.loads((out/"semi_rcps/design.json").read_text())["seeds"]),"observed_record_stations":macros["RRecordStations"],"regional_comparisons":len(computed)}
    state["additional_local_experiments"]["air_exposure_mask_seeds"]=int(exposure_summary.mask_seeds.max()) if len(exposure_summary) else 0
    state["national_availability_complete"]=bool(national and national["all_metadata_possible_sites_resolved"])
    national_h30_path=out/"national_meaning/status.json"
    state["national_h30_analysis_complete"]=bool(national_h30_path.exists() and json.loads(national_h30_path.read_text()).get("complete"))
    state["local_evidence_complete"]=state["national_availability_complete"] and state["national_h30_analysis_complete"]
    state_path_text=json.dumps(state,ensure_ascii=False,indent=2)+"\n";status_path.write_text(state_path_text)
