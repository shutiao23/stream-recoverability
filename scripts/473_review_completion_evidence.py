#!/usr/bin/env python3
"""Generate auditable fourth-review tables, figures, claims and Chinese status.

No absent experiment is turned into a pass. External registration, natural
reference qualification and author identity are separate from computed results.
"""
from __future__ import annotations
import os
os.environ["MPLBACKEND"]="Agg"
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.statistics import removal_count

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=T.ROOT/CONFIG["out"]
DOC=T.ROOT/"docs/reviews/wrr_review_completion_20261024"
PAPER=T.ROOT/"paper/wrr_tr"
FIG=PAPER/"figures/review_completion"
LABELS={"plug_in":"Daily plug-in","functional_debias":"Functional debiasing","lookup_debias":"Lookup debiasing","MOVE1_annual":"Annual MOVE.1","MOVE1_warm":"Warm-season MOVE.1","MOVE1_H30":"H30 MOVE.1","air2stream3":"Air2stream-3",
        "distribution_regression":"Distribution regression","stochastic_regression":"Stochastic regression","stochastic_regression_calibrated":"Calibrated stochastic",
        "air_state_simulation":"State simulation","air_state_calibrated":"Calibrated state","observed_days":"Observed days",
        "average":"Batch average","average_cap":"Batch + individual cap","individual_0.1":"Individual score <=0.10","individual_group_adjusted":"Probability + group adjustment","group_certificate":"Group certificate",
        "one_feature_50":"Peak overlap <50%","complete_year":"Complete years","coverage_75":"75% annual coverage","retain_and_estimate":"Retain and estimate","warm_90":"90% warm-season coverage",
        "A0":"Discard incomplete years","A1":"90% warm-season rule","D2_multiple_imputation":"Distribution-regression MI","stochastic_regression_MI":"Stochastic MI","stochastic_calibrated_MI":"Calibrated stochastic MI","censored_trend":"Censored trend"}
LABELS.update({"coarse_overlapping_groups":"Coarse groups, conservative","coarse_overlapping_groups_randomized":"Coarse groups, randomized","held_region_group_required":"Full region, conservative","held_region_group_randomized":"Full region, randomized",
               "labeled_WSR_RCPS":"Labeled-only WSR","semi_supervised_general_WSR_RCPS":"Semi-supervised WSR","boosting_local_air":"Local air boosting","boosting_local_flow":"Local flow boosting",
               "boosting_lagged_air":"Global lagged-air boosting","boosting_with_flow":"Global flow boosting","csdi":"CSDI","saits":"SAITS","lstm":"LSTM","raw_classifier":"Raw classifier","Platt_probability_calibration":"Platt probability calibration","Platt_plus_empirical_groups":"Probability + group adjustment"})


def display_name(value):
    return LABELS.get(str(value),str(value).replace("_"," "))


def claim_display(frame):
    rows=[]
    for row in frame.itertuples():
        code=row.claim
        if code.startswith("D2_mae_vs_"):
            metric="MAE reduction";comparison=display_name(code.removeprefix("D2_mae_vs_"))
        elif code.startswith("D2_crps_improvement_vs_"):
            metric="CRPS improvement";comparison=display_name(code.removeprefix("D2_crps_improvement_vs_"))
        elif code.startswith("D2_twcrps_improvement_vs_"):
            metric="Tail CRPS improvement";comparison=display_name(code.removeprefix("D2_twcrps_improvement_vs_"))
        else:
            metric="Trend RMSE reduction";comparison=code.removeprefix("trend_").replace("_"," ")
        rows.append(dict(metric=metric,comparison=comparison,positive=row.positive_repeats,repeats=row.n_repeats,median=row.median))
    return pd.DataFrame(rows)


def collect(name,split="leave_one_year_out"):
    files=sorted((OUT/"analyses"/split).glob(f"seed_*/{name}.csv"))
    files=[p for p in files if p.with_name("summary.json").exists() and json.loads(p.with_name("summary.json").read_text()).get("analysis_version")==CONFIG["analysis_version"]]
    return pd.concat([pd.read_csv(p) for p in files],ignore_index=True) if files else pd.DataFrame()


def tex_escape(value):
    text=str(value)
    text=text.replace("_",r"\_").replace("%",r"\%").replace("&",r"\&")
    return text.replace("<=",r"\(\leq\)").replace(">=",r"\(\geq\)").replace("<",r"\(<\)").replace(">",r"\(>\)")


def tex_table(frame,caption,label,columns=None):
    if columns is not None:
        frame=frame[columns]
    if frame.empty:
        return ""
    short={"fraction_groups_above_10_median":"groups >10%","retention_median":"retention","risk_median":"risk","mae_median":"MAE","crps_median":"CRPS","coverage90_median":"coverage","n_seeds":"seeds","positive_repeats":"positive","n_repeats":"repeats",
           "region_mean_retention":"retention","region_mean_coverage":"coverage","selected_risk_group_mixture":"selected risk","max_solver_fallback_percent":"LP fallback (%)","finite_minimum_repeats":"finite minima","already_failed":"initial failures","minimum_median":"median min. groups","budget_groups":"labels (groups)","n_runs":"runs","nonempty_fraction":"nonempty","unlabeled_budget_insufficient":"unlabeled shortage","difference_of_regional_medians":"trend difference"}
    short["groups_above_10"]="groups >10%"
    short["twcrps_median"]="twCRPS"
    headings=[tex_escape(short.get(c,c.replace("_"," "))) for c in frame]
    lines=[r"\begin{table}[p]",r"\caption{"+caption+"}",r"\label{"+label+"}",r"\centering\small",r"\resizebox{\textwidth}{!}{%",r"\begin{tabular}{"+"l"*len(headings)+"}",r"\toprule"," & ".join(headings)+r" \\",r"\midrule"]
    for row in frame.itertuples(index=False,name=None):
        entries=["--" if pd.isna(v) else f"{v:.3f}" if isinstance(v,(float,np.floating)) else tex_escape(LABELS.get(str(v),v)) for v in row]
        lines.append(" & ".join(entries)+r" \\")
    lines += [r"\bottomrule",r"\end{tabular}","}",r"\end{table}"]
    return "\n".join(lines)+"\n"


def aggregate(frame,keys,values):
    if frame.empty:
        return pd.DataFrame()
    rows=[]
    for labels,b in frame.groupby(keys,dropna=False):
        labels=labels if isinstance(labels,tuple) else (labels,)
        row=dict(zip(keys,labels))
        row["n_seeds"]=int(b.seed.nunique())
        for value in values:
            if value not in b:
                continue
            x=b[value].dropna().to_numpy()
            row[value+"_n_seeds"]=int(len(x))
            if len(x):
                row[value+"_median"]=float(np.median(x));row[value+"_lower"]=float(np.quantile(x,.025));row[value+"_upper"]=float(np.quantile(x,.975))
        rows.append(row)
    return pd.DataFrame(rows)


def trends():
    parts=[]
    robustness=[]
    for path in sorted((OUT/"analyses/leave_one_year_out").glob("seed_*/trends.parquet")):
        b=pd.read_parquet(path)
        if b.empty:
            continue
        b["squared"]=b.error**2
        for (seed,scenario,pipeline),v in b.groupby(["seed","scenario","pipeline"]):
            site=v.groupby(["station","group"]).error.agg(["mean","var","count"])
            per=v.groupby("station").squared.mean()
            mean_sq=float(v.squared.mean());bias_sq=float(np.mean(site["mean"]**2))
            parts.append(dict(seed=seed,scenario=scenario,pipeline=pipeline,n_stations=v.station.nunique(),n_groups=v.group.nunique(),availability=float(v.error.notna().mean()),rmse=float(np.sqrt(mean_sq)),bias=float(v.error.mean()),bias_squared_fraction=bias_sq/mean_sq if mean_sq>0 else np.nan,coverage=float(v.coverage.mean()),missing_component_coverage=float(v.missing_component_coverage.mean()),median_se=float(v.se.median())))
        for (seed,scenario),v in b.groupby(["seed","scenario"]):
            wide=v.groupby(["station","pipeline"]).squared.mean().unstack()
            if "A1" not in wide or "D2_multiple_imputation" not in wide:
                continue
            a=wide.A1.to_numpy();c=wide.D2_multiple_imputation.to_numpy()
            ratio=np.sqrt(c/a)
            order=np.argsort(a)[::-1]
            robustness.append(dict(seed=seed,scenario=scenario,rmse_reduction=float(1-np.sqrt(np.nansum(c)/np.nansum(a))),station_ratio_median=float(np.nanmedian(ratio)),station_ratio_q25=float(np.nanquantile(ratio,.25)),station_ratio_q75=float(np.nanquantile(ratio,.75)),remove_to_reverse=removal_count(a,c),remove_to_below_20=removal_count(a,c,.2),after_remove_worst1=float(1-np.sqrt(np.nansum(c[order[1:]])/np.nansum(a[order[1:]]))),after_remove_worst3=float(1-np.sqrt(np.nansum(c[order[3:]])/np.nansum(a[order[3:]])))))
    return pd.DataFrame(parts),pd.DataFrame(robustness)


def savefig(name,rect=None):
    plt.tight_layout(rect=rect);plt.savefig(FIG/f"{name}.pdf",bbox_inches="tight");plt.savefig(FIG/f"{name}.png",dpi=150,bbox_inches="tight");plt.close()


def figures(score,rules,recovery,economic,trend):
    plt.rcParams.update({"font.size":11,"axes.labelsize":11,"xtick.labelsize":10,"ytick.labelsize":10})
    FIG.mkdir(parents=True,exist_ok=True)
    # Six scientific panels, each generated from a saved producing table.
    fig,axes=plt.subplots(1,2,figsize=(8,4.5));ax=axes[1]
    missing=T.E1_MISSINGNESS/"missingness_models.csv"
    if missing.exists():
        m=pd.read_csv(missing);m=m.loc[m.analysis.eq("station_year_conditional_logit")&m.covariate.isin(["z_air","trend"])]
        axes[0].errorbar(m.odds_ratio,np.arange(len(m)),xerr=np.array([m.odds_ratio-m.odds_ratio_lower95,m.odds_ratio_upper95-m.odds_ratio]),fmt="o")
        axes[0].set_yticks(np.arange(len(m)),m.covariate);axes[0].axvline(1,color="gray",lw=1);axes[0].set(xlabel="Odds ratio, historical missingness audit",title="Observed missingness association")
    if not score.empty:
        b=score.loc[score.estimator.isin(["plug_in","distribution_regression"])&score.stratum.str.startswith("overlap")]
        for (name,family),v in b.groupby(["estimator","family"]):
            v=v.assign(bin=v.stratum.str.extract(r"overlap(\d)",expand=False).astype(int)).groupby("bin").apply(lambda g:np.average(g.failure_rate,weights=g.n))
            ax.plot(v.index,v.values,marker="o",linestyle="-" if family=="calendar" else "--",label=display_name(name)+": "+family)
        ax.legend(fontsize=9);ax.set(xlabel="Peak-overlap bin",ylabel="Failure probability",title="Pre-delivery risk")
    savefig("r4_1_missingness_triage")
    fig,axs=plt.subplots(1,2,figsize=(8,4.5))
    if not recovery.empty:
        for ax,metric in zip(axs,["auc","brier_skill"]):
            b=recovery.loc[recovery.family.eq("crossed")&recovery.scope.eq("all")&~recovery.model.isin(["risk_classifier","oracle_D2"])].groupby("model")[metric].median().dropna()
            ax.barh(b.index.str.replace("_"," "),b);ax.set_xlabel(metric.replace("_"," "))
    savefig("r4_2_recovery")
    fig,axs=plt.subplots(1,2,figsize=(8,4.5))
    if not score.empty:
        paired=collect("paired_effects");dist=collect("distribution_paired_effects")
        if not paired.empty:
            b=paired.loc[paired.family.eq("crossed")&paired.unit.eq("station")&~paired.reference.isin(["observed_days","MOVE1_H30","triage_hybrid"])]
            q=b.groupby("reference").mean_paired_mae_difference.quantile([.025,.5,.975]).unstack().sort_values(.5)
            axs[0].errorbar(q[.5],np.arange(len(q)),xerr=np.array([q[.5]-q[.025],q[.975]-q[.5]]),fmt="o",capsize=3)
            axs[0].set_yticks(np.arange(len(q)),[display_name(x) for x in q.index]);axs[0].axvline(0,color="gray");axs[0].set_xlabel("Paired MAE difference\n(degrees C)")
        if not dist.empty:
            q=dist.loc[dist.family.eq("crossed")].groupby("reference").crps_difference.quantile([.025,.5,.975]).unstack().sort_values(.5)
            axs[1].errorbar(q[.5],np.arange(len(q)),xerr=np.array([q[.5]-q[.025],q[.975]-q[.5]]),fmt="o",capsize=3)
            axs[1].set_yticks(np.arange(len(q)),[display_name(x) for x in q.index]);axs[1].axvline(0,color="gray");axs[1].set_xlabel("Paired CRPS difference\n(degrees C)")
    savefig("r4_3_estimators")
    fig,axs=plt.subplots(1,2,figsize=(8,4.5))
    if not economic.empty:
        b=economic.loc[economic.family.eq("calendar")&economic.rule.isin(["individual_0.1","one_feature_50","average","average_cap","individual_group_adjusted"])]
        for name,v in b.groupby("rule"):
            v=v.groupby("cost_ratio").relative_economic_value.median();axs[0].plot(v.index,v,label=display_name(name))
        axs[0].set(xscale="log",xlabel="Admission / rejection cost",ylabel="Relative economic value");axs[0].legend(fontsize=9)
    selected=OUT/"meaning/summary.json"
    if selected.exists():
        v=json.loads(selected.read_text())["n_stations_by_rule"];axs[1].barh([display_name(x) for x in v],list(v.values()));axs[1].set_xlabel("Eligible panel stations")
    savefig("r4_4_decisions_selection")
    fig,axs=plt.subplots(1,2,figsize=(8,4.5))
    if not rules.empty:
        b=rules.loc[rules.family.eq("crossed")&rules.rule.isin(["average","average_cap","individual_0.1","individual_group_adjusted","group_certificate"])]
        for ax,metric in zip(axs,["risk","fraction_groups_above_10"]):
            v=b.groupby("rule")[metric].median();ax.barh([display_name(x) for x in v.index],v)
            for i,value in enumerate(v):
                if not np.isfinite(value):
                    ax.text(0,i,"No admissions; undefined",va="center",fontsize=10)
            ax.set_xlabel("Realized selected risk" if metric=="risk" else "Groups above 10% risk\n(fraction)")
    savefig("r4_5_group_risk")
    fig=plt.figure(figsize=(8,8));grid=fig.add_gridspec(2,2,height_ratios=[1,1.05])
    axs=[fig.add_subplot(grid[0,0]),fig.add_subplot(grid[0,1]),fig.add_subplot(grid[1,:])]
    scenario_names={"mcar":"Matched random","strong_heat":"Heat-associated","non_air_trend":"Incompatible annual trend"}
    if not trend.empty:
        for j,(scenario,b) in enumerate(trend.groupby("scenario")):
            style=dict(marker=["o","^","s"][j],linestyle=["-","--",":"][j])
            v=b.groupby("pipeline").rmse.median();axs[0].plot(v,range(len(v)),label=scenario_names.get(scenario,scenario),**style)
            interval=b.loc[b.pipeline.isin(["D2_multiple_imputation","stochastic_regression_MI","stochastic_calibrated_MI"])].groupby("pipeline").missing_component_coverage.median()
            axs[1].plot(interval,range(len(interval)),label=scenario_names.get(scenario,scenario),**style)
        axs[0].set_yticks(range(len(v)),[display_name(x) for x in v.index]);axs[0].set_xlabel("Trend RMSE\n(degrees C per decade)")
        handles,labels=axs[0].get_legend_handles_labels();fig.legend(handles,labels,loc="upper center",ncol=3,fontsize=9)
        axs[1].set_yticks(range(len(interval)),[display_name(x) for x in interval.index]);axs[1].axvspan(.9,.97,color="gray",alpha=.2);axs[1].axvline(.95,color="black",linestyle=":",lw=1)
        axs[1].set(xlim=(0,1),xlabel="Missing-component coverage\n(nominal 95%)")
    events=collect("events")
    if not events.empty:
        keep=["observed_days","plug_in","MOVE1_warm","functional_debias","distribution_regression","stochastic_regression_calibrated"]
        b=events.loc[events.family.eq("calendar")&events.scope.eq("danger")&events.estimator.isin(keep)].groupby("estimator").sedi.median();axs[2].barh([display_name(x) for x in b.index],b);axs[2].set_xlabel("Hot-year SEDI")
    savefig("r4_6_downstream_events",rect=(0,0,1,.94))


def main():
    p=argparse.ArgumentParser();p.add_argument("--allow-partial",action="store_true");a=p.parse_args()
    DOC.mkdir(parents=True,exist_ok=True);(OUT/"evidence").mkdir(parents=True,exist_ok=True)
    score=collect("scorecard");rules=collect("rules");recovery=collect("recovery");economic=collect("economic_value")
    n=int(score.seed.nunique()) if not score.empty else 0
    if n!=20 and not a.allow_partial:
        raise RuntimeError(f"Require all 20 complete repetition analyses; found {n}")
    summaries={
        "scorecard":aggregate(score,["family","stratum","estimator"],["mae","bias","failure_rate","crps","twcrps","coverage90","interval_score90","width90","availability"]),
        "rules":aggregate(rules,["family","delivery","rule"],["retention","risk","fraction_groups_above_7","fraction_groups_above_10","worst_group_risk","failures_per_1000"]),
        "recovery":aggregate(recovery,["family","scope","model"],["auc","brier_skill","diagnostic_retention_at_5"]),
    }
    trend,robust=trends();trend.to_csv(OUT/"evidence/trend_summary_per_seed.csv",index=False);robust.to_csv(OUT/"evidence/trend_robustness_per_seed.csv",index=False)
    for key,v in summaries.items():
        v.to_csv(OUT/"evidence"/f"{key}_summary.csv",index=False)
    for name in ["events","paired_effects","unit_paired_effects","distribution_paired_effects","group_risks","group_risk_coverage_curve","economic_value","archive_per_1000","primary_analogues","specification_sensitivity"]:
        b=collect(name)
        if not b.empty:
            b.to_csv(OUT/"evidence"/f"{name}_all_seeds.csv",index=False)
    claims=[]
    if not score.empty:
        paired=collect("paired_effects")
        danger=score.loc[score.family.eq("crossed")&score.stratum.eq("danger")].pivot(index="seed",columns="estimator",values="mae")
        for ref in ["plug_in","functional_debias","lookup_debias","MOVE1_annual","MOVE1_warm","stochastic_regression","stochastic_regression_calibrated","air_state_calibrated"]:
            if ref in danger and "distribution_regression" in danger:
                common=paired.loc[paired.family.eq("crossed")&paired.unit.eq("station")&paired.reference.eq(ref)] if not paired.empty else pd.DataFrame()
                reduction=common.set_index("seed").case_relative_reduction if len(common) and "case_relative_reduction" in common else 1-danger.distribution_regression/danger[ref]
                claims.append(dict(claim=f"D2_mae_vs_{ref}",n_repeats=int(reduction.notna().sum()),positive_repeats=int((reduction>0).sum()),ten_percent_repeats=int((reduction>=.1).sum()),median=float(reduction.median()),lower=float(reduction.quantile(.025)),upper=float(reduction.quantile(.975)),abstract_eligible=bool(n==20 and (reduction>0).sum()>=18)))
        distributions=collect("distribution_paired_effects")
        for reference,b in distributions.loc[distributions.family.eq("crossed")].groupby("reference"):
            for metric in ["crps","twcrps"]:
                improvement=-b[metric+"_difference"]
                claims.append(dict(claim=f"D2_{metric}_improvement_vs_{reference}",n_repeats=len(b),positive_repeats=int(improvement.gt(0).sum()),median=float(improvement.median()),lower=float(improvement.quantile(.025)),upper=float(improvement.quantile(.975)),abstract_eligible=bool(len(b)==20 and improvement.gt(0).sum()>=18)))
    if not robust.empty:
        for scenario,b in robust.groupby("scenario"):
            claims.append(dict(claim=f"trend_{scenario}",n_repeats=len(b),positive_repeats=int(b.rmse_reduction.gt(0).sum()),median=float(b.rmse_reduction.median()),lower=float(b.rmse_reduction.quantile(.025)),upper=float(b.rmse_reduction.quantile(.975)),abstract_eligible=bool(len(b)==20 and b.rmse_reduction.gt(0).sum()>=18)))
    claim=pd.DataFrame(claims);claim.to_csv(OUT/"evidence/claim_stability.csv",index=False)
    figures(score,rules,recovery,economic,trend)
    def median(frame,column,**selectors):
        if frame.empty or column not in frame:
            return None
        selected=np.ones(len(frame),bool)
        for k,v in selectors.items():
            selected&=frame[k].eq(v).to_numpy()
        return float(frame.loc[selected,column].median()) if selected.any() else None
    macros={"RSeeds":n,"RRecoveryAUC":median(recovery,"auc",family="crossed",scope="all",model="recovery_model"),"RWithinAUC":median(recovery,"auc",family="crossed",scope="within_cell",model="recovery_model"),"RRetention":median(rules,"retention",family="calendar",rule="individual_0.1"),"RRisk":median(rules,"risk",family="calendar",rule="individual_0.1"),"RGroupExcess":median(rules,"fraction_groups_above_10",family="crossed",rule="individual_0.1"),"RTrendGain":median(robust,"rmse_reduction",scenario="mcar")}
    macros.update({key:None for key in ["REuropeStations","REuropeRequested","REuropeErrors","REuropeCases","REuropeAirCases","REuropePowerMAE","REuropeEraMAE"]})
    from wrr_review_forcing_reporting import europe_evidence
    europe=europe_evidence(OUT);paired=europe["pairs"]
    macros.update(REuropeStations=europe["retrieved"],REuropeRequested=europe["selected"],REuropeErrors=len(europe["errors"]),REuropeCases=paired.loc["all","n"],REuropeAirCases=paired.loc["air_layer_danger","n"],REuropePowerMAE=paired.loc["air_layer_danger","POWER_mae"],REuropeEraMAE=paired.loc["air_layer_danger","ERA5_Land_mae"])
    lines=[]
    for name,value in macros.items():
        if value is None or not np.isfinite(value):
            rendered="pending"
        elif name in ["RSeeds","REuropeStations","REuropeRequested","REuropeErrors","REuropeCases","REuropeAirCases"]:
            rendered=str(int(value))
        elif name in ["RRetention","RRisk","RGroupExcess","RTrendGain"]:
            rendered=f"{100*value:.1f}"
        elif name in ["REuropePowerMAE","REuropeEraMAE"]:
            rendered=f"{value:.3f}"
        else:
            rendered=f"{value:.2f}"
        lines.append("\\newcommand{\\"+name+"}{"+rendered+"}")
    (PAPER/"review_completion_claims.tex").write_text("\n".join(lines)+"\n")
    historical=pd.DataFrame([{"endpoint":"P1","verdict":"not met","reason":"84.8 percent registered coverage, floor 85"},{"endpoint":"P2","verdict":"not met","reason":"zero retention gain at five percent risk"},{"endpoint":"P3","verdict":"not met","reason":"fixed-threshold transfer failed"},{"endpoint":"P4","verdict":"met historically","reason":"trend RMSE and missing-component interval"},{"endpoint":"N1--N3","verdict":"met after recomputation","reason":"opened outcomes; no longer blind"}])
    maintex=tex_table(historical[["endpoint","verdict"]],"Historical registered verdicts. The redesign cannot revise them.","tab:historical")
    if not claim.empty:
        shown=claim_display(claim)
        for start in range(0,len(shown),12):
            maintex+=tex_table(shown.iloc[start:start+12],"Exploratory direction stability; positive differences favor distribution regression. MAE and trend entries are fractional reductions; CRPS entries are score differences in degrees C. These are repeated analyses of the same archive.",f"tab:stability{start}")
    (PAPER/"review_completion_tables_main.tex").write_text(maintex)
    sitex=""
    for name,summary in summaries.items():
        if not summary.empty:
            if name=="scorecard":
                b=summary.loc[summary.stratum.eq("danger")];cols=["family","estimator","n_seeds","mae_median","crps_median","coverage90_median"]
            elif name=="rules":
                b=summary;cols=["family","delivery","rule","n_seeds","retention_median","risk_median","fraction_groups_above_10_median"]
            else:
                b=summary;cols=["family","scope","model","n_seeds","auc_median"]
            for i in range(0,len(b),20):
                sitex+=tex_table(b.iloc[i:i+20],name.replace("_"," ")+"; source tables contain all strata and empirical repetition intervals.",f"tab:{name}{i}",[c for c in cols if c in b])
    (PAPER/"review_completion_tables_si.tex").write_text(sitex)
    if n!=20:
        T.write_json(OUT/"evidence/completion_status.json",{"partial_run":True,"full_seed_analyses":n,"required_seed_analyses":20,"all_user_requirements_complete":False})
        (DOC/"EXECUTION_REPORT_ZH.md").write_text(f"# 开发中：当前仅有 {n}/20 个完整源域分析\n\n此输出由 `--allow-partial` 生成，未完成种子与依赖阶段不能写成最终证据。完成后须重新运行完整汇总、构建与检查。\n")
        return 0
    from wrr_review_reporting import finish_evidence
    finish_evidence(OUT,DOC,PAPER,CONFIG,collect,aggregate,tex_table,claim,summaries,trend,robust)
    from wrr_review_extensions import finish_extensions
    finish_extensions(OUT,DOC,PAPER,tex_table)
    from wrr_review_national_reporting import finish_national_reporting
    finish_national_reporting(OUT,DOC,PAPER)
    from wrr_review_window_reporting import finish_window_reporting
    finish_window_reporting(OUT,DOC,PAPER,tex_table)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
