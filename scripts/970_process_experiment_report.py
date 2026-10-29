#!/usr/bin/env python3
"""Render the 2026-10-29 experiment evidence without changing saved data."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"results/wrr_process_experiments_20261029"
PAPER=ROOT/"paper/wrr_tr"
FIG=PAPER/"figures/process_revision"
SCHEMES=["warm90","legacy_random","legacy_time_balanced","uniform_random_expected","cdf_all_years","sxx_all_years","all"]
LABELS={"warm90":"Warm-season", "legacy_random":"Legacy random", "legacy_time_balanced":"Legacy spacing",
        "uniform_random_expected":"Uniform exact", "cdf_all_years":"CDF", "sxx_all_years":"Sxx", "all":"All years"}
LAYERS=["uncalibrated","fixed_old_offset","reestimated_source_offset"]
LAYER_LABELS=["Uncalibrated","Fixed native offsets","Updated source offsets"]
SEED_COLORS=["#2f6790","#c96935","#2c896c"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fmt(value,digits=4):
    return f"{float(value):.{digits}f}"


def range_text(values,digits=4):
    values=np.asarray(values,float)
    low,high=float(values.min()),float(values.max())
    return fmt(low,digits) if fmt(low,digits)==fmt(high,digits) else fmt(low,digits)+(" to " if high<0 else "--")+fmt(high,digits)


def int_range(values):
    values=np.asarray(values,int)
    return str(int(values.min())) if values.min()==values.max() else f"{int(values.min())}--{int(values.max())}"


def main_slice(frame):
    return frame.loc[frame.scope.eq("actual_mask_common")&frame.weighting.eq("equal_archive")]


def start_table(caption,label,columns,header):
    return [r"\begin{table}[t]\centering\small",r"\caption{"+caption+"}",r"\label{"+label+"}",
            r"\resizebox{\ifdim\width>\textwidth\textwidth\else\width\fi}{!}{%",r"\begin{tabular}{"+columns+"}",r"\toprule",header+r" \\",r"\midrule"]


def end_table():
    return [r"\bottomrule\end{tabular}}",r"\end{table}"]


def save_figure(fig,name,figdir):
    fig.savefig(figdir/(name+".pdf"),bbox_inches="tight")
    fig.savefig(figdir/(name+".png"),dpi=180,bbox_inches="tight")
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data",type=Path,default=DATA)
    parser.add_argument("--paper",type=Path,default=PAPER)
    parser.add_argument("--figures",type=Path,default=FIG)
    args=parser.parse_args()
    data,paper,figdir=args.data,args.paper,args.figures
    paper.mkdir(parents=True,exist_ok=True);figdir.mkdir(parents=True,exist_ok=True)
    sources=[]
    def read(name):
        path=data/name;sources.append(path)
        return pd.read_parquet(path) if path.suffix==".parquet" else pd.read_csv(path,float_precision="round_trip")
    time=read("time_sensitivity_summary.csv")
    paired=read("time_sensitivity_paired_cluster.csv")
    accounting=read("time_archive_accounting.csv")
    feasible=read("time_all_feasible_subsets.parquet")
    fixed=read("time_fixed_geometry_selections.parquet")
    random=read("time_random_selection_variation.csv")
    random_seeds=read("time_random_seed_summary.csv")
    source_union=read("source_calibration/source_union_cases.parquet")
    source_roles=read("source_calibration/source_role_cases.csv")
    targets=read("source_calibration/fixed_target_cases.csv")
    target_scores=read("source_calibration/full/target_three_layer_cases.csv")
    reference=read("source_calibration/full/target_historical_reference.csv")
    tail_cases=read("source_calibration/full/target_budget_case_deltas.csv")
    tails=read("source_calibration/full/target_budget_tail_summary.csv")
    grid_path=data/"source_calibration/crps_grid_sensitivity.json"
    sources.append(grid_path)
    grid_check=json.loads(grid_path.read_text())
    if grid_check["status"] != "passed" or not grid_check["all_three_grids_preserve_reported_seed0_order_crossing"]:
        raise ValueError("The reported local score ordering needs its integration-grid check")
    regional=read("region_water/regional_leave_group_out.csv")
    regional_standardized=read("region_water/independent_regional_standardization.csv")
    water=read("region_water/water_air_weight_and_leave_group_sensitivity.csv")
    gaps=read("gap_overlap_summary.csv")
    gap_cases=read("gap_overlap_station_year_cases.csv")
    primary=main_slice(time).set_index("scheme")
    contrasts=main_slice(paired).loc[lambda x:x.field.eq("estimate_mse")].set_index("scheme")
    if set(primary.index)!=set(SCHEMES) or int(primary.n.iloc[0])!=int(accounting.primary.sum()):
        raise ValueError("Time summary and case denominators disagree")
    primary_keys=accounting.loc[accounting.primary,["station_key","replicate"]]
    fixed_primary=fixed.merge(primary_keys,on=["station_key","replicate"],validate="many_to_one")
    means=fixed_primary.groupby("scheme").n_retained.mean()
    subset_membership=feasible.merge(accounting[["station_key","replicate","primary"]],on=["station_key","replicate"],validate="many_to_one")
    if target_scores.duplicated(["station_key","year","seed","count","layer"]).any():
        raise ValueError("Duplicate target experiment row")
    updated=target_scores.loc[target_scores.layer.eq("reestimated_source_offset")]
    pooled=updated.groupby(["seed","count"])[["mae","crps256_normal"]].mean().reset_index()
    native=reference.loc[reference.method.eq("historical_native20")]
    d2=reference.loc[reference.method.eq("fixed_D2")]
    updated_tails=tails.loc[tails.layer.eq("reestimated_source_offset")&tails.comparison.eq("nested20_to_500")]
    macros={
        "PETimeN":str(int(primary.n.iloc[0])),"PETimeGroups":str(int(primary.groups.iloc[0])),
        "PETimeOriginalCommon":str(int(accounting.original_common.sum())),"PETimeSubsets":str(len(feasible)),
        "PETimePrimarySubsets":str(int(subset_membership.primary.sum())),"PETimeChoiceN":str(int(accounting.nontrivial_choice.sum())),
        "PETimeIdenticalN":str(int((accounting.primary&~accounting.nontrivial_choice).sum())),
        "PECalSourceCases":str(len(source_union)),"PECalSourceStations":str(source_union.station_key.nunique()),
        "PECalSourceYears":str(len(source_union[["station_key","year"]].drop_duplicates())),
        "PECalTargetCases":str(len(targets)),"PECalTargetStations":str(targets.station_key.nunique()),"PECalTargetGroups":str(targets.independence_group.nunique()),
        "PEClassicNativeMAE":fmt(native.mae.mean()),"PEDTwoFixedMAE":fmt(d2.mae.mean()),
        "PEClassicNativeCRPS":fmt(native.crps256_normal.mean()),"PEDTwoFixedCRPS":fmt(d2.crps256_normal.mean()),
        "PEClassicUpdatedMAERange":range_text(pooled.mae),"PEClassicUpdatedCRPSRange":range_text(pooled.crps256_normal),
        "PEClassicUpdatedFiveHundredMAERange":range_text(pooled.loc[pooled["count"].eq(500),"mae"]),
        "PEClassicUpdatedFiveHundredCRPSRange":range_text(pooled.loc[pooled["count"].eq(500),"crps256_normal"]),
    }
    for scheme,tag in [("warm90","Warm"),("uniform_random_expected","Uniform"),("cdf_all_years","CDF"),("sxx_all_years","Sxx"),("all","All")]:
        macros["PETime"+tag+"RMSE"]=fmt(primary.loc[scheme].estimate_rmse)
        macros["PETime"+tag+"TruthRMSE"]=fmt(primary.loc[scheme].year_set_rmse)
        if scheme!="warm90":
            for name,column in [("Difference","rmse_difference"),("Low","group_percentile_low"),("High","group_percentile_high")]:
                macros["PETime"+tag+name]=fmt(contrasts.loc[scheme,column])
    for region,tag in [("foen","Swiss"),("gkd_bayern","Bavaria")]:
        macros["PECal"+tag+"UpperRange"]=range_text(updated_tails.loc[updated_tails.region.eq(region),"median_abs_delta_q95"])
        macros["PECal"+tag+"UpperExceedRange"]=int_range(updated_tails.loc[updated_tails.region.eq(region),"n_q95_gt005"])
        macros["PECal"+tag+"SourceGroups"]=str(source_roles.loc[source_roles.calibration_region.eq(region),"independence_group"].nunique())
    for region,tag in [("foen","Swiss"),("gkd_bayern","Bavaria")]:
        rows=water.loc[water.region.eq(region)]
        macros["PEWater"+tag+"EqualStationDelta"]=fmt(rows.loc[rows.analysis.eq("equal_station_total_weight"),"slope_difference"].iloc[0])
        macros["PEWater"+tag+"LeaveGroupRange"]=range_text(rows.loc[rows.analysis.eq("leave_connected_group_out"),"slope_difference"])
    observed=gaps.loc[gaps.source.eq("observed")&gaps.period.eq("2010-2025")].iloc[0]
    observed_cases=gap_cases.loc[gap_cases.source.eq("observed")&gap_cases.year.ge(2010)&gap_cases.peer_evaluable]
    macros.update(PEGapObservedPeerRows=str(int(observed.n_peer_evaluable_incomplete_rows)),
                  PEGapObservedSameDayRows=str(int(observed_cases.any_same_day_missing_peer.sum())),
                  PEGapObservedSharedDays=str(int(observed.shared_missing_station_days)),
                  PEGapObservedEligibleDays=str(int(observed.peer_evaluable_missing_station_days)))
    (paper/"process_experiments_values.tex").write_text("% Generated from saved experiment tables by scripts/970_process_experiment_report.py\n"+"\n".join("\\newcommand{\\"+name+"}{"+value+"}" for name,value in macros.items())+"\n")

    time_lines=start_table(
        r"Exploratory finite-record slope comparisons on \PETimeN{} actual-mask archives in \PETimeGroups{} connected groups. Errors are $^{\circ}$C per decade. CDF and Sxx optimize the entire retained set including fixed complete years. Uniform exact averages squared errors over feasible same-count sets within each archive, then averages archives and takes the square root. All-year truth-set error is zero by definition. The last column gives comparator-minus-warm-season estimated RMSE with a paired 95\% group-percentile interval, not an equivalence test.",
        "tab:time-support","lrrrrl",r"Rule & Years & Estimate & Year-set & Reconst. & $\Delta$ RMSE [95\% interval]")
    for scheme in SCHEMES:
        row=primary.loc[scheme]
        years=means.loc["warm90" if scheme=="uniform_random_expected" else scheme]
        interval="Reference" if scheme=="warm90" else fmt(contrasts.loc[scheme].rmse_difference)+" ["+fmt(contrasts.loc[scheme].group_percentile_low)+", "+fmt(contrasts.loc[scheme].group_percentile_high)+"]"
        time_lines.append(f"{LABELS[scheme]} & {years:.2f} & {row.estimate_rmse:.4f} & {row.year_set_rmse:.4f} & {row.reconstruction_rmse:.4f} & {interval} "+r"\\")
    time_lines+=end_table()
    (paper/"process_experiments_time_table.tex").write_text("\n".join(time_lines)+"\n")

    source_lines=start_table(
        r"Same-target annual comparison by region--reconstructor stratum. D2 and historical native20 are fixed original references. Updated rows regenerate the source-role offsets at the stated nested budget; entries are minima--maxima across seeds 0, 1 and 2, not confidence intervals. MAE and mean 90\% width are in $^{\circ}$C. CRPS uses the same seven-quantile normal-spacing 256-point approximation for every method. Each stratum contains one connected group; these counts do not estimate population coverage or establish a general method ranking.",
        "tab:source-budget","lrrrr",r"Method / paths & Covered & MAE & Width & CRPS256")
    for region,label in [("foen","Switzerland / donor ridge"),("gkd_bayern","Bavaria / air ridge")]:
        n=int(targets.region.eq(region).sum())
        source_lines.append(r"\multicolumn{5}{l}{\textit{"+label+f"; {n} target station-years"+r"}} \\")
        for method,title in [("fixed_D2","Fixed D2"),("historical_native20","Historical native20")]:
            block=reference.loc[reference.region.eq(region)&reference.method.eq(method)]
            source_lines.append(f"{title} & {int(block.covered90.sum())}/{len(block)} & {block.mae.mean():.4f} & {block.width90.mean():.4f} & {block.crps256_normal.mean():.4f} "+r"\\")
        for count in [20,100,500]:
            block=updated.loc[updated.region.eq(region)&updated["count"].eq(count)]
            by_seed=block.groupby("seed").agg(covered=("covered90","sum"),mae=("mae","mean"),width=("width90","mean"),crps=("crps256_normal","mean"))
            source_lines.append(f"Updated nested{count} & {int_range(by_seed.covered)} of {n} & {range_text(by_seed.mae)} & {range_text(by_seed.width)} & {range_text(by_seed.crps)} "+r"\\")
        source_lines.append(r"\addlinespace")
    source_lines+=end_table()
    (paper/"process_experiments_source_table.tex").write_text("\n".join(source_lines)+"\n")

    # Figure 10: actual values and paired uncertainty use the same primary cohort.
    plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False})
    fig,axes=plt.subplots(1,2,figsize=(11.8,4.2),gridspec_kw={"width_ratios":[1.35,1]},constrained_layout=True)
    shown=["warm90","uniform_random_expected","cdf_all_years","sxx_all_years","all"]
    x=np.arange(len(shown));width=.36
    axes[0].bar(x-width/2,[primary.loc[s].estimate_rmse for s in shown],width,color="#315f83",label="Estimated annual values")
    axes[0].bar(x+width/2,[primary.loc[s].year_set_rmse for s in shown],width,color="#9eb9cc",label="True values on selected years")
    for i,s in enumerate(shown):axes[0].text(i-width/2,primary.loc[s].estimate_rmse+.009,fmt(primary.loc[s].estimate_rmse,3),ha="center",fontsize=9)
    axes[0].set(xticks=x,xticklabels=["Warm","Uniform\nexact","CDF","Sxx","All"],ylabel="Slope RMSE (°C per decade)",ylim=(0,.53),title="(a) Year-set and estimated errors")
    axes[0].legend(frameon=False,fontsize=9,loc="upper right")
    compared=shown[1:]
    for i,s in enumerate(compared):
        row=contrasts.loc[s]
        axes[1].errorbar(row.rmse_difference,i,xerr=np.asarray([[row.rmse_difference-row.group_percentile_low],[row.group_percentile_high-row.rmse_difference]]),fmt="o",color="#315f83",capsize=4)
    axes[1].axvline(0,color="#555555",lw=1,ls="--")
    axes[1].set(yticks=np.arange(len(compared)),yticklabels=["Uniform exact","CDF","Sxx","All"],xlabel="Estimated RMSE minus warm-season",title=f"(b) Paired {int(primary.groups.iloc[0])}-group resampling")
    axes[1].invert_yaxis();axes[1].grid(axis="x",alpha=.18)
    save_figure(fig,"03_time_support",figdir)

    # Figure 11 retains every target case and each seed, with stratified medians.
    delta=tail_cases.loc[tail_cases.comparison.eq("nested20_to_500")]
    fig,axes=plt.subplots(1,3,figsize=(12.3,4.7),sharey=True,constrained_layout=True)
    ymax=max(float(delta.abs_delta_q95.max())*1.13,.10)
    markers=["o","^","s"]
    for panel,(layer,title) in enumerate(zip(LAYERS,LAYER_LABELS)):
        ax=axes[panel]
        for position,region in enumerate(["foen","gkd_bayern"]):
            for seed in [0,1,2]:
                block=delta.loc[delta.layer.eq(layer)&delta.region.eq(region)&delta.seed.eq(seed)].sort_values(["station_key","year"])
                if len(block)!=int(targets.region.eq(region).sum()):
                    raise ValueError("A figure layer omits or duplicates target cases")
                jitter=np.linspace(-.24,.24,len(block))+(seed-1)*.035
                ax.scatter(position+jitter,block.abs_delta_q95,color=SEED_COLORS[seed],marker=markers[seed],s=20,alpha=.67,zorder=3)
                median=float(block.abs_delta_q95.median())
                center=position+(seed-1)*.15
                ax.plot([center-.06,center+.06],[median,median],color=SEED_COLORS[seed],lw=3,zorder=4)
        ax.axhline(.05,color="#555555",ls="--",lw=1,zorder=1)
        n_s=int(targets.region.eq("foen").sum());n_b=int(targets.region.eq("gkd_bayern").sum())
        ax.set(xticks=[0,1],xticklabels=[f"Swiss donor\n{n_s} cases, 1 group",f"Bavarian air\n{n_b} cases, 1 group"],xlim=(-.45,1.45),ylim=(-.013,ymax),title=f"({chr(97+panel)}) {title}")
        ax.grid(axis="y",alpha=.16);ax.tick_params(axis="x",labelsize=9)
    axes[0].set_ylabel("Absolute 95th-percentile change (°C)\nNested prefix20 → 500")
    handles=[Line2D([],[],color=SEED_COLORS[s],marker=markers[s],ls="",label=f"Seed {s}") for s in [0,1,2]]
    handles.append(Line2D([],[],color="#222222",lw=3,label="Stratum × seed median"))
    fig.legend(handles=handles,loc="outside upper center",ncol=4,frameon=False,fontsize=9)
    save_figure(fig,"04_trajectory_budget",figdir)

    # Supporting text and compact sensitivity tables, all values read above.
    random_row=main_slice(random).iloc[0]
    random_primary=main_slice(random_seeds)
    cdf_changes=int(feasible.loc[feasible.cdf_all_years_selected&~feasible.warm90_selected].shape[0])
    sxx_changes=int(feasible.loc[feasible.sxx_all_years_selected&~feasible.warm90_selected].shape[0])
    support=[r"\section{Additional exploratory experiments}",
             r"\subsection{Outcome-blind year-set selection}",
             r"All feasible same-count subsets are enumerated while retaining every fixed complete year. There are \PETimeSubsets{} subsets across \PETimeOriginalCommon{} common archives; the \PETimeN{} actual-mask primary archives contribute \PETimePrimarySubsets{} subsets. The two zero-mask settings contribute one subset each. Only \PETimeChoiceN{} actual-mask archives offer a nontrivial choice; the remaining \PETimeIdenticalN{} have identical same-count selections by construction. CDF minimizes the retained-versus-full empirical-year-CDF squared distance, including complete years; Sxx maximizes the centered decade-year sum of squares of the entire retained set. Ties use the alternate geometry score and then the earliest incomplete-year tuple. No temperature or error enters either selector. They change "
             +str(cdf_changes)+" and "+str(sxx_changes)+r" selected sets relative to warm-season screening, respectively. These post-review exploratory rules are not deployment recommendations and do not separately identify effects of year count and temporal position.",
             r"Uniform exact means $\sqrt{\operatorname{mean}_{a}E_{U\mid a}(E_a^2)}$, with an equal-probability set $U$ inside each archive $a$. It is not the mean RMSE over random selections. Over "
             +str(int(random_row.random_draws))+" random seeds, the mean RMSE is "+fmt(random_row.mean_draw_rmse)+", the root of mean sampled MSE is "+fmt(random_row.sqrt_mean_draw_mse)+", and the exact conditional root-expected-MSE is "+fmt(random_row.exact_sqrt_expected_mse)+r" $^{\circ}$C per decade. The across-seed 2.5th--97.5th percentiles ["+fmt(random_row.selection_percentile_low)+", "+fmt(random_row.selection_percentile_high)+"] describe selection variation, not a confidence interval; "+str(int(random_primary.estimate_rmse.lt(primary.loc["warm90"].estimate_rmse).sum()))+"/"+str(len(random_primary))+r" seeds improve on the warm-season point result. Paired intervals in Table~\ref{tab:time-support} instead resample the recorded connected groups "+f"{int(contrasts.bootstraps.iloc[0]):,}"+r" times, preserving paired archives and their conditional subset-average MSEs before taking roots.",
             r"For each fixed set $E=S+R$, hence $\operatorname{MSE}(E)=\operatorname{MSE}(S)+\operatorname{MSE}(R)+2\operatorname{mean}(SR)$. Averaging over uniform subsets preserves this identity; negative cross terms can cancel squared errors. Neither RMSE subtraction nor normalized squared terms are independent causal contributions."]
    robustness=start_table(r"Estimated slope RMSE sensitivity to weighting and selection opportunity. Archive, station and group columns weight each respective unit equally within the 805-archive cohort; the last column uses only the 468 nontrivial-choice archives and equal archive weights. These are exploratory summaries, not equivalence tests.","tab:time-experiment-sensitivity","lrrrr",r"Rule & Archive wt. & Station wt. & Group wt. & Choice-only")
    for s in ["warm90","uniform_random_expected","cdf_all_years","sxx_all_years","all"]:
        vals=[time.loc[time.scope.eq("actual_mask_common")&time.weighting.eq(w)&time.scheme.eq(s),"estimate_rmse"].iloc[0] for w in ["equal_archive","equal_station","equal_group"]]
        vals.append(time.loc[time.scope.eq("choice_only")&time.weighting.eq("equal_archive")&time.scheme.eq(s),"estimate_rmse"].iloc[0])
        robustness.append(LABELS[s]+" & "+" & ".join(fmt(v) for v in vals)+" "+r"\\")
    support+=robustness+end_table()
    support += [r"\subsection{Larger-budget source-role calibration}",
                r"The source calibration union contains \PECalSourceCases{} cases at \PECalSourceStations{} stations and \PECalSourceYears{} unique station-years. The Swiss/Bavarian target roles contain \PECalSwissSourceGroups{}/\PECalBavariaSourceGroups{} positive-weight interval-calibration groups under the original saved role assignment. All source calibration years precede 2010; held target groups remain excluded and original integer bootstrap multiplicities are unchanged. For each seed and budget the order is seven raw source quantiles $\to$ observed-bound projection $\to$ weighted source residual order statistics; target raw quantiles $\to$ bound $\to$ add source offset $\to$ sort $\to$ bound. A cell requires at least 50 finite positive-weight cases before multiplicity; otherwise the finite positive calibration pool is used. No target truth is used for offset estimation.",
                r"Native20 calls the original bridge with 20 draws, whereas nested20 is the prefix of a 500-draw call; they need not be identical because the random arrays are generated by day. Native20 source and target references are checked separately against original case/repair and archive files. Seeds 0, 1 and 2 share fixed daily models, residual histories and masks. The uncalibrated, fixed-old-offset and updated-source-offset layers score the same target raw draws. D2 retains its original seven annual quantiles, with no refit or recalibration. Every CRPS uses the common bounded normal-spacing 256-point annual approximation; these are annual scores, not newly computed full-archive trends. The 27 target years span only two connected groups; 500 paths do not prove convergence or broad ranking robustness.",
                r"\input{process_experiments_source_table.tex}"]
    support += [r"\paragraph{CRPS integration precision.} Keeping every saved annual quantile and the tail assumption fixed, we score 783 method--case distributions on 256, 1,024 and 4,096 probability points. An independent order-statistic formula reproduces the original 256-point scores to floating-point precision. The maximum casewise 256-to-4,096 change is "
                + f"{grid_check['max_casewise_change_256_to4096']:.6f}"
                + r"$^{\circ}$C. The fixed-seed-0 updated-source nested20/nested500 comparison crosses the fixed-D2 CRPS at all three grids. This checks integration of the stipulated seven-quantile approximation; it does not validate its tail assumption or establish infinite-trajectory convergence."]
    detailed=start_table(r"Updated source-offset annual results for every nested seed and budget. Panels retain the original region--reconstructor strata. Counts are descriptive on one group per panel; all scores use the same bounded 256-point annual approximation.","tab:source-budget-seeds","lrrrrr",r"Seed / paths & $n$ & Covered & MAE & Width & CRPS256")
    for region,label in [("foen","Switzerland / donor ridge"),("gkd_bayern","Bavaria / air ridge")]:
        detailed.append(r"\multicolumn{6}{l}{\textit{"+label+r"}} \\")
        for (seed,count),block in updated.loc[updated.region.eq(region)].groupby(["seed","count"]):
            detailed.append(f"{seed} / {count} & {len(block)} & {int(block.covered90.sum())} & {block.mae.mean():.4f} & {block.width90.mean():.4f} & {block.crps256_normal.mean():.4f} "+r"\\")
        detailed.append(r"\addlinespace")
    support+=detailed+end_table()
    both_tails=start_table(
        r"Both endpoint sensitivities after source-role offset re-estimation, from nested-prefix20 to 500 paths. Entries are the median/maximum absolute change in $^{\circ}$C across the stated target stratum; the last column counts cases with either endpoint changing by more than 0.05$^{\circ}$C. Each region--reconstructor stratum is one connected group, and these descriptive changes do not establish convergence.",
        "tab:source-budget-both-tails","lrrrrr",r"Stratum & Seed & $n$ & $|\Delta q_{.05}|$ med./max. & $|\Delta q_{.95}|$ med./max. & Either $>0.05$")
    for region,label in [("foen","Swiss donor"),("gkd_bayern","Bavarian air")]:
        for row in updated_tails.loc[updated_tails.region.eq(region)].sort_values("seed").itertuples(index=False):
            both_tails.append(f"{label} & {row.seed} & {row.n} & {row.median_abs_delta_q05:.4f}/{row.max_abs_delta_q05:.4f} & {row.median_abs_delta_q95:.4f}/{row.max_abs_delta_q95:.4f} & {row.n_either_tail_gt005}/{row.n} "+r"\\")
    support+=both_tails+end_table()
    support += [r"\subsection{Regional and annual water--air influence diagnostics}",
                r"Removing a connected group and recomputing common cells changes both support and the standardized target population; it is an influence check, not a fixed-population causal contrast. Geometry min-count coverage gaps stay positive, whereas the smaller geometry-plus-reconstructor subset can reverse sign. Training-history imbalance and the missing Swiss air-ridge counterpart remain. Annual water--air sensitivity also depends on whether years or stations receive equal total weight. A group deletion can leave only one Swiss station, and the Bavarian aggregate change masks group influence. None of these checks establishes daily reconstruction stability or equivalence."]
    influence=start_table(r"Influence checks. Panel A shows FOEN-minus-Bavaria coverage gaps in percentage points using min-count weights; group deletion recomputes common support. Panel B shows after-minus-before-2010 within-station annual slopes; equal-station weighting changes the target relative to equal annual observations. Deletion ranges are not confidence intervals.","tab:region-water-experiment-influence","lrrr",r"Panel A: cells & Main gap & Group-deletion gap & Sign reversals")
    for matching,label in [("geometry","Geometry"),("geometry_plus_policy","+ reconstructor")]:
        b=regional_standardized.loc[regional_standardized.matching.eq(matching)&regional_standardized.weighting.eq("min_count")&regional_standardized.method.eq("D2")].set_index("region")
        values=regional.loc[regional.matching.eq(matching)&regional.status.eq("supported"),"difference_pp"]
        influence.append(label+" & "+fmt(100*(b.loc["foen"].coverage90-b.loc["gkd_bayern"].coverage90),3)+" & "+range_text(values,3)+" & "+str(int(values.lt(0).sum()))+" "+r"\\")
    influence += [r"\midrule",r"Panel B: region & Annual-weight $\Delta$ & Station-weight $\Delta$ & Group-deletion $\Delta$ \\",r"\midrule"]
    for region,label in [("foen","Switzerland"),("gkd_bayern","Bavaria")]:
        block=water.loc[water.region.eq(region)]
        influence.append(label+" & "+fmt(block.loc[block.analysis.eq("annual_observation_weights"),"slope_difference"].iloc[0])+" & "+fmt(block.loc[block.analysis.eq("equal_station_total_weight"),"slope_difference"].iloc[0])+" & "+range_text(block.loc[block.analysis.eq("leave_connected_group_out"),"slope_difference"])+" "+r"\\")
    support+=influence+end_table()
    support += [r"\subsection{Same-day missingness with an evaluable-peer denominator}",
                r"Peer-evaluable rows require another station in the same connected group with an eligible recorded missingness pattern in that year. Observed peers use the eligible-year roster, which includes incomplete years; trial peers use the complete-reference-year roster on which masks are imposed. Group-years with no such peer are excluded and counted. Same-day overlap means at least one missing day coincides with a peer missing day. Shared station-days count each focal station's missing days that coincide with any peer, divided by its eligible missing station-days. Observed rows are incomplete station-years; trial rows are station-year--replicates. Same-day co-missingness does not identify an outage cause, the donor actually used, or a naturally unobserved failure process."]
    overlap=start_table(r"Same-day overlap denominators. Any overlap is the percent of peer-evaluable incomplete rows with at least one shared missing day. Day share uses eligible missing station-days. Repeated trial masks retain their original weights; the historical observed row supplements the primary 2010--2025 comparison.","tab:gap-daily-overlap","lrrrrrr",r"Source / period & All & Peer & Excl. & Any (\%) & Shared / eligible days & Days (\%)")
    for source,period,label in [("observed","2010-2025","Observed / 2010--25"),("calendar","2010-2025","Calendar / 2010--25"),("crossed","2010-2025","Controlled / 2010--25"),("observed","1981-2025","Observed / 1981--25")]:
        row=gaps.loc[gaps.source.eq(source)&gaps.period.eq(period)].iloc[0]
        overlap.append(f"{label} & {int(row.n_incomplete_rows):,} & {int(row.n_peer_evaluable_incomplete_rows):,} & {int(row.n_no_evaluable_peer_excluded):,} & {100*row.same_day_overlap_fraction_peer_evaluable:.2f} & {int(row.shared_missing_station_days):,}/{int(row.peer_evaluable_missing_station_days):,} & {100*row.shared_missing_day_fraction:.2f} "+r"\\")
    support+=overlap+end_table()
    (paper/"process_experiments_supporting.tex").write_text("\n\n".join(support)+"\n")
    source_metadata={"script":"scripts/970_process_experiment_report.py","input_sha256":{str(p.relative_to(ROOT)):sha(p) for p in sources}}
    for name in ["03_time_support","04_trajectory_budget"]:
        details={"figure":name}
        if name=="04_trajectory_budget":
            details.update(source_role_offsets_reestimated=True,layers=LAYERS,plotted_case_seed_points=int(len(delta)),median_markers=len(LAYERS)*len(targets.region.unique())*target_scores.seed.nunique(),threshold_c=.05)
        (figdir/(name+".source.json")).write_text(json.dumps(source_metadata|details,indent=2)+"\n")
    report={"status":"generated_from_saved_data","macros":macros,"macro_count":len(macros),
            "generated_tex":[str((paper/name).relative_to(ROOT)) for name in ["process_experiments_values.tex","process_experiments_time_table.tex","process_experiments_source_table.tex","process_experiments_supporting.tex"]],
            "input_sha256":source_metadata["input_sha256"],"interpretation":"Report generation changes no case-level data and does not itself establish scientific validity or convergence."}
    (data/"process_experiment_report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
