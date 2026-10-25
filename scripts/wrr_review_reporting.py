"""Final reporting from frozen fourth-review results; never refits a model."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq


def deep_tables(out):
    """Use finite predictions in every metric, including failures and coverage.

    The air-only comparison is important: neural methods do not receive the
    neighbor series used by the daily reconstruction priority policy.
    """
    rows, paired = [], []
    identity = ["network_id", "station_key", "year", "design_family", "realization_id", "policy_choice"]
    for seed in [0, 1, 2]:
        methods = {}
        for path in sorted((out / f"deep/seed_{seed:02d}").glob("*_cases.parquet")):
            name = path.name.removesuffix("_cases.parquet")
            b = pd.read_parquet(path)
            assert not b.duplicated(identity).any(), path
            methods[name] = b
            for family, block in b.groupby("design_family"):
                scopes = {"all": block, "danger": block.loc[block.peak_overlap.ge(.5)],
                          "air_danger": block.loc[block.peak_overlap.ge(.5) & block.policy_choice.eq("air_ridge")]}
                for scope, eligible in scopes.items():
                    valid = eligible.loc[np.isfinite(eligible.h30_error)]
                    row = dict(seed=seed, model=name, family=family, scope=scope,
                               n_eligible=len(eligible), n_valid=len(valid),
                               availability=len(valid) / len(eligible) if len(eligible) else np.nan,
                               bias=float(valid.h30_error.mean()), mae=float(valid.h30_error.abs().mean()),
                               failure_rate=float(valid.h30_error.abs().gt(.5).mean()) if len(valid) else np.nan)
                    for column in ["daily_mae", "crps", "twcrps", "coverage90", "interval_score90"]:
                        row[column] = float(pd.to_numeric(valid[column]).mean()) if column in valid and len(valid) else np.nan
                    if "h30_draws" in valid and len(valid):
                        expected=valid.h30_draws.map(lambda x:float(np.asarray(x,float).mean()))
                        error=expected-valid.truth_h30
                        row["functional_mean_bias"]=float(error.mean());row["functional_mean_mae"]=float(error.abs().mean())
                    rows.append(row)
        if "distribution_regression_calibrated" not in methods:
            continue
        d2 = methods["distribution_regression_calibrated"][identity + ["h30_error"]]
        for reference, block in methods.items():
            if reference.startswith("distribution_regression"):
                continue
            common = d2.merge(block[identity + ["h30_error", "peak_overlap"]], on=identity,
                              suffixes=("_D2", "_reference"), validate="one_to_one")
            common = common.loc[np.isfinite(common.h30_error_D2) & np.isfinite(common.h30_error_reference)]
            for family, b in common.groupby("design_family"):
                for scope, v in {"danger": b.loc[b.peak_overlap.ge(.5)],
                                 "air_danger": b.loc[b.peak_overlap.ge(.5) & b.policy_choice.eq("air_ridge")]}.items():
                    a, c = v.h30_error_D2.abs(), v.h30_error_reference.abs()
                    paired.append(dict(seed=seed, family=family, scope=scope, reference=reference,
                                       n_common=len(v), D2_mae=a.mean(), reference_mae=c.mean(),
                                       mae_difference=(a-c).mean(),
                                       relative_reduction=1-a.mean()/c.mean() if len(v) and c.mean()>0 else np.nan))
    return pd.DataFrame(rows), pd.DataFrame(paired)


def finish_evidence(out, doc, paper, config, collect, aggregate, tex_table, claims, summaries, trend, robust):
    evidence = out / "evidence"
    deep, deep_pairs = deep_tables(out)
    deep.to_csv(evidence / "deep_scorecard_per_seed.csv", index=False)
    deep_pairs.to_csv(evidence / "deep_paired_effects_per_seed.csv", index=False)
    deep_summary = aggregate(deep, ["family", "scope", "model"],
                             ["mae", "bias", "functional_mean_bias", "functional_mean_mae", "failure_rate", "daily_mae", "crps", "twcrps", "coverage90", "interval_score90", "availability"])
    deep_summary.to_csv(evidence / "deep_scorecard_summary.csv", index=False)
    aux = []
    for split in ["cold_to_hot", "before_2010", "non_air_refit", "opened_transfer"]:
        b = collect("scorecard", split)
        if not b.empty:
            b["split"] = split
            aux.append(b)
    aux = pd.concat(aux, ignore_index=True) if aux else pd.DataFrame()
    aux.to_csv(evidence / "differential_and_opened_scorecard.csv", index=False)
    daily_trends = []
    for path in sorted((out / "analyses/non_air_refit").glob("seed_*/trends.parquet")):
        b = pd.read_parquet(path)
        for (seed, scenario, method), v in b.groupby(["seed", "scenario", "pipeline"]):
            daily_trends.append(dict(seed=seed, scenario=scenario, pipeline=method,
                                     rmse=float(np.sqrt((v.error**2).mean())), n_stations=v.station.nunique()))
    daily_trends = pd.DataFrame(daily_trends)
    daily_trends.to_csv(evidence / "daily_non_air_refit_trends_per_seed.csv", index=False)
    labels = pd.concat([pd.read_csv(p) for p in (out / "adaptation").glob("seed_*/small_label_curve.csv")], ignore_index=True)
    label_summary = labels.groupby(["family", "budget_groups"]).agg(
        n_runs=("n_admitted", "size"), nonempty_certificate_fraction=("n_admitted", lambda x: float(x.gt(0).mean())),
        mean_retention=("retention", "mean"), risk_among_nonempty=("risk", "mean")).reset_index()
    label_summary.to_csv(evidence / "small_label_summary.csv", index=False)
    archive = collect("archive_per_1000")
    archive_summary = aggregate(archive, ["delivery", "rule"], ["used_per_1000", "failures_per_1000", "expected_absolute_error_among_used", "unsupported_population_per_1000"])
    archive_summary.to_csv(evidence / "archive_per_1000_summary.csv", index=False)
    analogues = collect("primary_analogues")
    analogue_summary = analogues.groupby(["endpoint", "version"]).agg(
        n_repeats=("seed", "nunique"), passing=("criterion_met", "sum"), coverage90=("coverage90", "median"), gain=("gain", "median")).reset_index()
    analogue_summary.to_csv(evidence / "primary_analogue_summary.csv", index=False)
    from wrr_review_forcing_reporting import europe_evidence
    europe=europe_evidence(out);europe_pairs=europe["pairs"]
    europe_scope="全部可评估欧洲源站，采用原始模型控制" if europe["full_source"] else "预定16站试验，完整扩展仍在采集"
    planning=pd.read_csv(out/"independent_study/sample_size_planning.csv").set_index("independent_groups")

    # Supplementary PDF contains small, interpretable slices; full Cartesian
    # scorecards and all repetition ranges remain in the machine-readable CSVs.
    si = (paper / "review_completion_tables_si.tex").read_text()
    for family in ["crossed", "calendar"]:
        d = deep_summary.loc[deep_summary.family.eq(family) & deep_summary.scope.eq("air_danger")]
        si += tex_table(d, f"Matched deep-comparator {family} cases with dangerous gaps and air-ridge information tier; three seeds only. Neighbor data are absent from neural inputs.", "tab:deep"+family,
                        ["model", "n_seeds", "mae_median", "bias_median", "availability_median"])
    si += tex_table(label_summary, "Nonempty bounded-group certification by local label budget. Undefined selected risks are not zero-risk successes.", "tab:local-labels")
    si += tex_table(archive_summary.loc[archive_summary.delivery.eq("distribution_regression")],
                    "Poststratified outcomes per 1,000 historically supported incomplete station-years. Empirical repetition medians; unsupported strata stay in the denominator.", "tab:per1000",
                    ["rule", "used_per_1000_median", "failures_per_1000_median", "unsupported_population_per_1000_median"])
    (paper / "review_completion_tables_si.tex").write_text(si)

    registration_path = out / "independent_study/public_registration_status.json"
    registration = json.loads(registration_path.read_text()) if registration_path.exists() else {"status": "not_publicly_registered"}
    n = int(summaries["scorecard"].n_seeds.max())
    case_counts = pd.DataFrame([
        {"seed": int(path.stem.removeprefix("seed_")),
         "n_cases": pq.read_metadata(path).num_rows}
        for path in sorted((out / "cases/leave_one_year_out").glob("seed_*.parquet"))
    ])
    if len(case_counts) != n:
        raise RuntimeError("Source case files do not match the reported repetition count")
    case_counts.to_csv(evidence / "source_case_counts_per_seed.csv", index=False)
    case_count_min = int(case_counts.n_cases.min())
    case_count_max = int(case_counts.n_cases.max())
    status = dict(full_seed_analyses=n, required_seed_analyses=20,
                  source_case_count_range=[case_count_min, case_count_max],
                  deep_models_by_seed={seed: sorted(deep.loc[deep.seed.eq(seed), "model"].unique()) for seed in [0,1,2]},
                  registration=registration, independent_test="not performed; no new water-temperature values acquired",
                  natural_reference="qualification complete; zero qualified natural gaps, so recovery accuracy unverified",
                  author_and_platform_fields="user-owned; user will fill authors, funding and OSF/Zenodo links",
                  local_evidence_complete=n==20, partial_run=n!=20,
                  all_user_requirements_complete=False,
                  remaining_scientific_evidence=["public registration and genuinely new independent outcomes", "national H30 trend analysis", "full target-specific H7 refit; current specification sensitivity uses fixed predictions", "all-study-site high-resolution driver sensitivity beyond the prespecified35US/16European sample"],
                  scientific_limits=["natural peak-window qualification has zero references; planned negative pathway completed", "nearby NOAA comparison completed for all benchmarkable source USGS sites but does not provide perfect co-location or clock equivalence", "conditional imputation and spatial exchangeability assumptions remain unverified"])
    (evidence / "completion_status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False)+"\n")

    def table(b, columns=None):
        return b[columns].to_markdown(index=False, floatfmt=".4f") if columns else b.to_markdown(index=False, floatfmt=".4f")

    source = summaries["scorecard"]
    source = source.loc[source.family.eq("crossed") & source.stratum.eq("danger") & source.estimator.isin(
        ["plug_in", "functional_debias", "distribution_regression", "stochastic_regression", "stochastic_regression_calibrated", "air_state_calibrated"])]
    rules = summaries["rules"]
    rules = rules.loc[rules.delivery.eq("distribution_regression") & rules.rule.isin(
        ["one_feature_50", "individual_0.1", "individual_group_adjusted", "average", "average_cap", "group_certificate"])]
    aux_small = aux.loc[aux.family.eq("crossed") & aux.stratum.eq("danger") & aux.estimator.isin(
        ["plug_in", "distribution_regression", "stochastic_regression_calibrated"])]
    aux_small = aux_small.groupby(["split", "dataset", "estimator"]).agg(seeds=("seed", "nunique"), mae=("mae", "median"), coverage90=("coverage90", "median")).reset_index()
    deep_small = deep_summary.loc[deep_summary.family.eq("crossed") & deep_summary.scope.eq("air_danger")]
    report = ["# 第四轮改进执行结果（2026-10-24）", "",
        "源域核心实验、增补对照、结果审计与稿件已交付；全国时间可用性仍在采集。数据未支持的主张已降级。**新的独立检验尚未执行；真实缺口按无合格参照的预定失败路径完成了资格核查与样本量计算，精度证据仍未闭合。趋势的缺测分量区间也未通过重设计关口，不能把全部科学证据链写成完成。** 作者、机构、资助及 OSF/Zenodo 信息按用户要求由用户填写，不作为本地工作缺项。", "",
        "原三份审稿文件和历史注册判定保留。原 P1 覆盖率 84.8% 未过 85% 下限；本轮探索性校正不能改变这个判定。两个旧附加数据集均是已打开资料。", "",
        "## 1. 重复设计与可核算结论", "",
        f"完成 {n}/20 个种子；每次重新抽掩码、日历、轨迹和独立组角色，在角色内有放回重抽。源病例每个种子 {case_count_min:,}–{case_count_max:,} 行，逐次计数见 `evidence/source_case_counts_per_seed.csv`；共 581 站、185 个连通独立组、27 个区域，区域级重拟合共 540 次。四类源域角色与最终留区组互不交叉。种子区间是同一已打开档案的算法与组构成变异，不是 20 个独立气候样本的置信区间。", "",
        "危险层统一以决策时气候峰窗被遮比例 ≥50% 定义；真实峰窗只作历史终点对照。主张稳定性表中 MAE/趋势为相对降幅，CRPS/twCRPS 为对照减 D2 的绝对得分差，正值有利于 D2。", "", table(claims), "",
        "危险层共同病例的 MAE：D2 比 plug-in 的中位降幅为 21.2%，20/20 同向；比 P2 只好 5.3%，0/20 达到预定 10% 实质改善。D2 与随机回归相当。校正后的随机回归还消除了原先的覆盖率不足，D2 的区间优势也不是独有的。不得推荐必须使用 D2。", "",
        table(source, ["estimator", "mae_median", "crps_median", "twcrps_median", "coverage90_median", "interval_score90_median", "availability_median"]), "",
        "以上单臂表保留各自可用性；相对效应使用相同可用病例，见 `evidence/paired_effects_all_seeds.csv` 与 `distribution_paired_effects_all_seeds.csv`。随机回归与状态模拟接受和 D2 完全相同的独立组校正角色、重抽权重和难度分层。探索性原始 P1 对应量 0/20 过关，校正后为 20/20，区间覆盖中位 88.0%；原注册 P1 的失败不变。P2 同风险留存增量仍为 0，20 次均未过关。", "",
        "残差桥曾错误地要求缺口以外的可见日也有中心值；已改为只要求隐藏日及有效边界，并用回归测试锁定。`repairs/` 保留逐行修复与计数。修复不改变学习特征或 D2 标签，无须重新拟合 D2。源种子 0 的全部掩码与原源病例一致，避免匹配深度对照时串病例。", "",
        "恢复模型在受控缺口的病例 AUC 为 0.867，格内 0.806，危险层 0.784；查表总体 AUC 0.785。危险层按真实标签诊断出来的 5% 风险留存为恢复模型约 24%、D2 失败分类器约 36%。这是排序上限诊断，不能当作源域固定阈值的部署保证。t5 只是名义尺度的重尾敏感性，不是匹配截断分布方差后的严格检验。", "",
        "## 2. 分割样本与深度机制预测", "", table(aux_small), "",
        "冷年训练、最热 20% 年检验时，D2 的危险层 90% 区间覆盖仅约 73.8%；按年代外推约 84.3%。冷/热与年代划分都在日回归、Air2stream、气候与气温基准、残差模拟和年度拟合前执行，防止间接使用检验年份。BOM 和 new-USGS 是源固定方法的已打开迁移诊断，不能称盲测。", "",
        "SAITS、CSDI、LSTM、MSE boosting 均完成 3 个固定独立组划分；另加岭回归同样的气温滞后 boosting 和有流量版本。下表只比较危险层中的 air-ridge 信息层；神经模型没有获得邻站输入，因此不拿所有信息层混在一起宣称算法公平。无流量预测为不可用，失败率分母只包含有限预测。", "",
        table(deep_small, ["model", "n_seeds", "mae_median", "bias_median", "functional_mean_bias_median", "daily_mae_median", "availability_median"]), "",
        "全局深度模型使用其他年份的站点气候态，但不重拟合局地水温–气温系数；经典日模型使用局地历史重新拟合。已另补同样局地训练范围的非线性 MSE boosting：气温滞后与岭回归完全一致，目标整年水温不进入训练或预处理；流量版按共同可用病例单列。抽样方法同时报告逐路径 H30 的均值与中位数，避免把 Jensen 关于条件期望的论证错用于中位数。CSDI 三个气温层危险病例划分的功能均值偏差为 −0.093、−0.003、+0.430°C，结论并非中位数选择造成。", "",
        "点模型未一致偏冷，抽样模型也未一致消除冷偏；删去“经验上与模型形式无关”的主张。Jensen 不等式只说明真条件均值经过最大窗口算子与条件期望的关系，不能保证有限训练的 SAITS/CSDI 误差符号。CPU 固定结构与训练预算不能代表这些模型的最优性能。", "",
        "## 3. 发布规则、成本与组风险", "", table(rules, ["family", "rule", "retention_median", "risk_median", "fraction_groups_above_10_median"]), "",
        "逐例上限 0.1 在真实日历保留约 94.8%、实际失败约 0.79%；受控缺口下保留约 76.8%、风险约 5.21%，但约 14.9% 可评估组仍超过 10% 风险。经验组校正将超标组降至约 2.7%，同时丢掉约 15 个百分点留存，超过计划允许的 5 个百分点。因此不能给出无本地标签的安全迁移建议。完整规则、成本曲线、最差组风险–覆盖与随机效应 O/E 预测区间均已保存。", "",
        "独立组证书的目标为先等权抽一个新组、再按规定抽病例的选中风险比 `E[B_g]/E[A_g]`；它既非每组保证，也不同于表中的病例加权总体风险。2–16 个本地有标签组下所有可评估运行均未得到非空证书。固定 8 阈值、5% 风险与 5% 总错误预算时，即使零损失也约需 99 个独立组（单固定阈值约 59）；数据不足不能写成零风险成功。PPI 仅为组等权平均风险的渐近诊断，没有半监督选择性风险的有限样本保证。", "",
        table(label_summary), "",
        "下表按有足够历史支持的真实不完整站年分布折算，每 1,000 个站年的未知/不支持层保留在分母；不是对所有现有站年的外推。与旧审计数不同是重新分组拟合、校正和严格保留不支持分母的结果。", "",
        table(archive_summary.loc[archive_summary.delivery.eq("distribution_regression")], ["rule", "used_per_1000_median", "failures_per_1000_median", "unsupported_population_per_1000_median"]), "",
        "## 4. 趋势与科学意义", "",
        "D2 多重插补相对暖季 90% 规则的随机缺测趋势 RMSE 降幅中位约 69.5%，20/20 同向；强热相关缺测约 69.6%。随机缺测按站匹配强热情景的边际缺测概率，避免把缺测率变化误作状态效应。A1 的随机缺测误差约 95% 是方差，支持的是精度与信息保留，不能声称主要纠正选择偏差。", "",
        "年度层面额外施加、却故意不让旧插补器适应的非气温趋势诊断中，D2 比 A1 差约 60%，0/20 改善。另有真正的全日序列非气温趋势重拟合：在全部完整水温及供体上加入 0.2°C/十年，保持气温不变，再从头拟合所有上游环节；3 个种子总体 RMSE 约 A1 0.039、D2 0.012°C/十年。前者是模型不相容的压力诊断，后者是平滑趋势可从历史适应的检验，两者不可互相替代。", "",
        "插补逐年独立抽分位数；Rubin 合并配有限自由度校正，并单列缺测分量区间。总趋势区间覆盖不等于缺测分量覆盖。右删失下界似然基线完成，但本设计里误差大于保留估计的办法，不支持用它替代全部年度估计。它不是 Bulletin 17C 的 EMA。", "",
        "已组装档案的可用站数从完整年规则 98 增至保留估计 255（暖季规则 230）。USGS 子面板为 36→163，区域趋势中位数 0.246→0.138°C/十年，不能直接解释为同一人群变冷：站点名单和年份支持都改变了。同站对照、组自助区间、站级 BH 和 2,000 次同步时间置换/循环位移均已输出。欧洲区域仍普遍升温；没有把增加显著站点数写成普遍科学结论反转。美国子面板循环位移场检验的 p 值由 0.057 变为 0.0005，是对该面板和拟合值的描述性敏感性，尚无自然缺口真值确认。", "",
        "`trend_robustness_per_seed.csv` 给出逐站比值、删去最差 1/3 站与精确翻转删除数；随机缺测翻转需删站数中位 31。`events_all_seeds.csv` 含命中、误报、SEDI。两个人工误差较大站的年数、缺口及河流代理属性见 `inputs/influential_station_profiles.csv`。", "",
        "## 5. 驱动、河流类型与真实缺口", "",
        "35 个预定美国站的日历滞后已修正：先补全每日索引再取滞后，不把稀疏序列的上一行当上一日，也不补入缺测值。Daymet 气温层危险病例共同 1,159 例，POWER 与 Daymet MAE 约 0.804 与 0.815°C；加入流量的共同 1,061 例从 0.848 降至 0.695°C。不可用输入按每病例保留。Daymet 用日最低/最高气温中点，产品和日聚合方式同时改变，不能只归因为空间分辨率。原位置滞后算法已从存档脚本与同一缓存独立重现；不是冒称旧输出原始字节仍在。", "",
        f"欧洲 ERA5-Land 当前主比较为{europe_scope}；取得 {europe['selected']} 站中的 {europe['retrieved']} 站，不可用原因 {len(europe['errors'])} 条保留。共 {int(europe_pairs.loc['all','n']):,} 个共同病例，气温层危险病例 {int(europe_pairs.loc['air_layer_danger','n'])} 个，POWER/ERA5-Land MAE 为 {europe_pairs.loc['air_layer_danger','POWER_mae']:.3f}/{europe_pairs.loc['air_layer_danger','ERA5_Land_mae']:.3f}°C；不外推为欧洲统一改善。新增 NOAA 近邻观测气温的全可评估 USGS 源域比较，详细范围、同日配对与控制核验见后文。7DADM 使用审核日最高水温：35 站中 34 合格，共 5,913 例；它是另一个热极值敏感性，不构成监管认证。", "",
        "失败地图覆盖 581 站（581 有坐标），大坝标签来自与 GAGES-II 2009 档案的精确站号连接；零流量只是代理，仅一处机构明确标注的湖泊出口已核实，其余保持未知。域外筛选为留区源距离上限诊断，不强行把已知失败站判域外，也不声称实现完整物理适用域。", "",
        "真实双传感器审查 180 个候选对年仍是 0 个合格自然峰窗参照，不能产生真实缺口精度结论。23 个站年的气温/邻站残差相关中位约 0.505；共享主传感器误差本身也会产生相关，因而这不是三重配置误差独立性的证明。参照精度计算只是在假定 Gaussian AR1 参数下的情景界。", "",
        "## 6. 独立检验材料与关口", "",
        "新西兰候选的目录类型与日期已核查：Horizons 58 站中，当前公开档案没有满足四年日期支持的潜在站；替补 Greater Wellington 的 218 个目录站中固定 9 个潜在站，合并为 3 个保守管理区组。全部新河温值仍未请求，完整参照年须在登记后的严格质量码/原生日值检查中判定。源域固定全局候选模型、角色、注册 E1–E5、样本量规划、名单及代码附件均已保存。发布值固定为 D2 中位数，因为失败分类器训练的对象就是它；随机回归的点估计优势不能直接继承 D2 的发布分数。三个组无法实施十标签组的 E5，已事前标为不可用。", "",
        "联合 E1/E2 规划已纳入全部 20 个源种子，每个种子、每个组数预算模拟 2,000 次，按种子等权混合。20/40/100/200 个独立组的联合通过率约 "+"/".join(f"{100*planning.loc[n,'joint_E1_E2_probability']:.1f}%" for n in [20,40,100,200])+"，没有规模达到 80%。200 组时源种子的 2.5%–97.5% 经验分位为 "+f"{100*planning.loc[200,'source_seed_lower']:.3f}%–{100*planning.loc[200,'source_seed_upper']:.1f}%"+"。这反映同一已打开档案的算法和组构成敏感性，不是新气候功效置信区间；不能写成“40 组足够”。方案定位为失败检测/边界研究，或在新公开注册前调整校准与目标，不能看新区域结果后更换终点。", "",
        "OSF 公开注册与完全匹配的协议/模型附件核验之后，才能下载新观测。作者和平台字段由用户填写；本地方案和压缩包不构成平台注册。原 P1–P3 未通过、C2 普遍机制不成立、C4 未胜过校正经典基线、C6 无标签安全迁移不成立，都在稿件中保留，不通过重算改成成功。", "",
        "## 7. 交付与复现", "",
        "- 稿件：[正文 PDF](../../../paper/wrr_tr/review_completion_article.pdf)、[补充材料 PDF](../../../paper/wrr_tr/review_completion_supporting.pdf)。", "- 数值入口：`results/wrr_review_completion_20261024/evidence/`；所有源种子、差异检验、深度病例和支持文件保留。", "- 命令：`make wrr-review-completion` 按依赖执行；`make wrr-review-paper` 汇总并编译；`make wrr-review-check` 检查数学及组隔离。", "- [23 项逐项交付清单](EXPERIMENT_CHECKLIST_ZH.md) 区分已完成、负结果、有限完成与外部待验。", "- 原工作树有大量既有改动；本轮未做整库提交，也未提交或发布论文。", "",
        "本地数值核验见 `evidence/validation.json`。可复现实验完成不等于外部证据齐全；当前新独立检验、合格自然缺口精度及部分驱动/物理类型上限仍未闭合。"]
    (doc / "EXECUTION_REPORT_ZH.md").write_text("\n".join(report)+"\n")
