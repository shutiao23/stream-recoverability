#!/usr/bin/env python3
"""Five evidence figures and prespecified learning/cofailure supplements."""

from __future__ import annotations

import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import wrr_r3_common as C

OUT = C.RUN / "r3_18_figures"
FIGURES = C.ROOT / "figures/wrr"
PAPER = C.ROOT / "paper/wrr/figures"
RET = "leave_one_year_out"
PRIOR = "strictly_prior_years"
BLUE, GREEN, ORANGE, GREY, RED = "#23628b", "#24816a", "#cf842f", "#a5adb2", "#b44f4f"
METHODS = ["doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge"]
LABELS = ["Daily climatology", "Smooth climatology", "Interpolation", "Neighbour ridge", "Air ridge"]


def save(figure, name: str) -> None:
    figure.savefig(FIGURES / f"{name}.pdf", bbox_inches="tight")
    figure.savefig(FIGURES / f"{name}.png", bbox_inches="tight", dpi=400)
    for extension in ("pdf", "png"):
        shutil.copy2(FIGURES / f"{name}.{extension}", PAPER / f"{name}.{extension}")
    plt.close(figure)


def recovery() -> None:
    base = C.RUN / "r3_05_mechanism" / RET
    figure, axes = plt.subplots(1, 2, figsize=(7.1, 3.25), layout="constrained", sharey=True)
    sources = []
    for scope, color, offset, label in [("all", GREY, -0.12, "All measurement classes"), ("documented_daily_mean", BLUE, 0.12, "Documented daily means")]:
        directory = base if scope == "all" else base / scope
        position = pd.read_csv(directory / "paired_position_contrasts.csv")
        length = pd.read_csv(directory / "paired_length_contrasts.csv")
        for panel, selected in enumerate([position.loc[position.family.eq("crossed_contiguous") & position.gap_length.eq(30)], length.loc[length.true_hidden_share_cutoff.eq(0.999)]]):
            selected = selected.set_index("reconstructor").reindex(METHODS)
            y = np.arange(len(METHODS)) + offset
            axes[panel].errorbar(selected["mean"], y, xerr=np.array([selected["mean"] - selected.ci_low, selected.ci_high - selected["mean"]]), fmt="o", ms=4, color=color, lw=1.1, capsize=2, label=label)
            sources.append(selected.reset_index().assign(scope=scope, contrast="position" if panel == 0 else "length"))
    for axis in axes:
        axis.axvline(0, color=GREY, lw=0.8)
        axis.set_xlabel("Paired change in H30 absolute error (°C)")
        axis.grid(axis="x", alpha=0.15)
    axes[0].set_yticks(np.arange(len(METHODS)), LABELS)
    axes[0].invert_yaxis()
    axes[0].set_title("a  Move a 30-day gap onto climate peak")
    axes[1].set_title("b  Extend 30 to 90 days; true peak hidden")
    axes[1].legend(loc="lower right", fontsize=8, frameon=False)
    pd.concat(sources).to_csv(OUT / "f1_source.csv", index=False)
    save(figure, "r3_f1_recovery")


def mechanisms() -> None:
    source = C.RUN / "r3_03_representative_recovery" / RET / "cases.parquet"
    columns = ["statistic_class", "replicate", "design_family", "hidden_channel_C__doy_climatology", "window_switch_increment_C__doy_climatology", "error_C__doy_climatology"]
    data = pd.read_parquet(source, columns=columns)
    data = data.loc[data.statistic_class.isin(["daily_mean", "documented_daily_mean"]) & data.replicate.eq(0) & data.design_family.eq("crossed_contiguous")].dropna()
    hidden, switch = data[columns[-3]].to_numpy(), data[columns[-2]].to_numpy()
    figure, axes = plt.subplots(1, 2, figsize=(7.1, 3.25), layout="constrained")
    extent = [float(np.quantile(hidden, 0.005)), max(0.1, float(np.quantile(hidden, 0.995))), 0, float(np.quantile(switch, 0.995))]
    axes[0].hexbin(hidden, switch, gridsize=40, bins="log", mincnt=1, cmap="Blues", extent=extent, linewidths=0, rasterized=True)
    line = np.linspace(extent[0], 0, 100)
    axes[0].plot(line, -line, "--", color=RED, lw=1)
    axes[0].set(xlim=extent[:2], ylim=extent[2:], xlabel="Error carried by true peak window (°C)", ylabel="Window-switch increment (°C)", title="a  Switching can compensate underestimation")
    axes[0].text(0.98, 0.96, "Above line: overestimate\nBelow line: underestimate", transform=axes[0].transAxes, ha="right", va="top", fontsize=8)
    table = pd.read_csv(C.RUN / "r3_05_mechanism" / RET / "documented_daily_mean/oracle_factorial_interventions.csv")
    table = table.loc[table.reconstructor.eq("doy_climatology")].set_index("variant")
    selected = table.reindex(["raw", "permuted", "demeaned", "demeaned_permuted"])
    axes[1].bar(np.arange(4), selected["mean"], color=[BLUE, GREY, ORANGE, GREEN], width=0.65)
    axes[1].errorbar(np.arange(4), selected["mean"], yerr=np.array([selected["mean"] - selected.ci_low, selected.ci_high - selected["mean"]]), fmt="none", color="#303030", capsize=3, lw=0.9)
    axes[1].set_xticks(np.arange(4), ["Original", "Permute", "Remove\nmean", "Both"])
    axes[1].set(ylabel="H30 mean absolute error (°C)", title="b  Oracle interventions are not deployable")
    axes[1].set_ylim(0, selected.ci_high.max() * 1.2)
    axes[1].text(0.98, 0.96, f"Interaction: {table.loc['interaction', 'mean']:.3f} °C", transform=axes[1].transAxes, ha="right", va="top", fontsize=9)
    data.to_csv(OUT / "f2_channels_source.csv", index=False)
    table.to_csv(OUT / "f2_interventions_source.csv")
    save(figure, "r3_f2_channels")


def information() -> None:
    table = pd.read_csv(C.RUN / "r3_07_decision_report/admission" / RET / "documented_daily_mean/operating_points.csv")
    names = ["length_rule", "peak_overlap_rule", "season_spline_plus_support", "generic_daily_disagreement", "generic_target_disagreement", "generic_both_diagnostics", "generic_direct_h30_uncertainty", "uncertain_support", "complete_diagnostic_model"]
    labels = ["Length", "Climate overlap", "Season spline + overlap", "Generic: daily disagreement", "Generic: H30 disagreement", "Generic + OOF residual scale", "Generic + direct H30 uncertainty", "Uncertain-window design", "Complete historical diagnostics"]
    figure, axes = plt.subplots(1, 2, figsize=(7.1, 4.2), layout="constrained", gridspec_kw={"width_ratios": [1.25, 1]})
    for seed, offset in [(101, -0.12), (202, 0), (303, 0.12)]:
        block = table.loc[table.selection.eq("empirical") & table.fold_seed.eq(seed)].set_index("arm").reindex(names)
        axes[0].plot(100 * block.retention, np.arange(len(names)) + offset, "o", ms=3.3, color=BLUE, alpha=0.7)
    axes[0].set_yticks(np.arange(len(names)), labels)
    axes[0].invert_yaxis()
    axes[0].set(xlim=(20, 90), xlabel="Retention (%)", title="a  Same target and empirical calibration")
    intervals = []
    for protocol_name, color, offset, label in [(RET, BLUE, -0.1, "Retrospective"), (PRIOR, ORANGE, 0.1, "Forward hindcast")]:
        block = pd.read_csv(C.RUN / "r3_13_learning_power/admission" / protocol_name / "whole_procedure_intervals.csv")
        comparisons = [("uncertain_support", "generic_target_disagreement"), ("uncertain_support", "generic_direct_h30_uncertainty")]
        for position, (left, right) in enumerate(comparisons):
            row = block.loc[block.left.eq(left) & block.right.eq(right)].iloc[0]
            mean = 100 * row.mean_refitted_procedure_difference
            axes[1].errorbar(mean, position + offset, xerr=[[mean - 100 * row.whole_procedure_ci_low], [100 * row.whole_procedure_ci_high - mean]], fmt="o", color=color, capsize=3, lw=1, label=label if position == 0 else None)
        intervals.append(block.assign(protocol=protocol_name))
    axes[1].axvline(0, color=GREY, lw=0.8)
    axes[1].axvline(5, color=RED, ls="--", lw=0.8)
    axes[1].set_yticks([0, 1], ["Window minus\nH30 generic", "Window minus\ndirect uncertainty"])
    axes[1].invert_yaxis()
    axes[1].set(xlabel="Retention difference (percentage points)", title="b  Training and calibration also resampled")
    axes[1].legend(loc="center right", bbox_to_anchor=(1, 0.5), frameon=True, facecolor="white", edgecolor="none", framealpha=0.95, fontsize=8)
    table.to_csv(OUT / "f3_operating_source.csv", index=False)
    pd.concat(intervals).to_csv(OUT / "f3_whole_procedure_source.csv", index=False)
    save(figure, "r3_f3_information")


def transfer() -> None:
    table = pd.read_csv(C.RUN / "r3_17_evidence/independent_admission.csv")
    table = table.loc[table.training_protocol.eq(RET) & table.provider.eq("foen") & table.scope.eq("documented_daily_mean") & table.selection.eq("empirical")]
    names = ["generic_target_disagreement", "generic_direct_h30_uncertainty", "uncertain_support", "certificate_joint"]
    figure, axes = plt.subplots(1, 2, figsize=(7.1, 3.4), layout="constrained")
    for mode, offset, color, label in [("frozen_source", -0.24, BLUE, "Frozen source"), ("frozen_model_local_calibration", 0, GREEN, "Local recalibration"), ("local_fit_and_calibration", 0.24, ORANGE, "Local fit + calibration")]:
        selected = table.loc[table["mode"].eq(mode)].set_index("arm").reindex(names)
        for axis, metric, lower, upper in [(axes[0], "retention", "retention_ci_low", "retention_ci_high"), (axes[1], "risk_among_admitted", "risk_ci_low", "risk_ci_high")]:
            mean = selected[metric].to_numpy() * 100
            axis.bar(np.arange(len(names)) + offset, mean, width=0.22, color=color, label=label)
            low = np.maximum(0, mean - selected[lower].to_numpy() * 100)
            high = np.maximum(0, selected[upper].to_numpy() * 100 - mean)
            axis.errorbar(np.arange(len(names)) + offset, mean, yerr=[low, high], fmt="none", color="#303030", capsize=1.5, lw=0.7)
    for axis in axes:
        axis.set_xticks(np.arange(len(names)), ["Generic", "Direct H30", "Window", "Joint cert."], rotation=20, ha="right")
    axes[0].set(ylabel="Retention (%)", title="a  Independent Swiss records")
    axes[1].set(ylabel="Failures among admitted (%)", title="b  Calibration target is not a transfer guarantee")
    axes[1].axhline(5, color=RED, ls="--", lw=1)
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(handles, labels, fontsize=8, frameon=False, loc="lower center", bbox_to_anchor=(0.5, -0.12), ncol=3)
    table.to_csv(OUT / "f4_source.csv", index=False)
    save(figure, "r3_f4_transfer")


def decisions() -> None:
    table = pd.read_csv(C.RUN / "r3_17_evidence/independent_decisions.csv")
    selected = table.loc[table.training_protocol.eq(RET) & table.provider.eq("foen") & table.scope.eq("documented_daily_mean") & table.arm.eq("uncertain_support") & table["mode"].eq("frozen_source") & table.threshold_definition.eq("local_training_q90") & table.measurement_margin_C.eq(0)]
    reference = selected.loc[selected.false_negative_cost.eq(5) & selected.abstention_cost.eq(0.05)].set_index("judgement_policy")
    frame = pd.read_parquet(C.RUN / "r3_10_external_decisions/test" / RET / "admission/cofailure_0/case_information.parquet")
    frame = frame.loc[frame.provider.eq("foen")]
    hot = frame.truth_hottest30.to_numpy() > frame.local_hot_threshold_C.to_numpy()
    predicted = frame.policy_metric.to_numpy() > frame.local_hot_threshold_C.to_numpy()
    available = np.isfinite(frame.policy_metric.to_numpy())
    baseline = {"true_positive": int((available & hot & predicted).sum()), "true_negative": int((available & ~hot & ~predicted).sum()), "false_negative": int((available & hot & ~predicted).sum()), "false_positive": int((available & ~hot & predicted).sum()), "abstained_hot": int((~available & hot).sum()), "abstained_cool": int((~available & ~hot).sum())}
    rows = [baseline, reference.loc["magnitude_screen"].to_dict(), reference.loc["screen_plus_observed_hot"].to_dict()]
    figure, axes = plt.subplots(1, 2, figsize=(7.1, 3.6), layout="constrained")
    bottom = np.zeros(3)
    for key, color, label in [("true_negative", BLUE, "Correct cool"), ("true_positive", GREEN, "Correct hot"), ("false_negative", RED, "Missed hot"), ("false_positive", ORANGE, "False hot"), ("abstained_cool", "#c1c6c9", "Unknown cool"), ("abstained_hot", "#efc5b4", "Unknown hot")]:
        values = np.array([row[key] / len(frame) * 100 for row in rows])
        axes[0].bar(np.arange(3), values, bottom=bottom, color=color, label=label, width=0.65)
        bottom += values
    axes[0].set_xticks(np.arange(3), ["Reconstruct\nall", "Magnitude\nscreen", "+ observed-hot\njudgement"])
    axes[0].set(ylabel="Original candidate pool (%)", ylim=(0, 100), title="a  Refused records remain unknown")
    axes[0].legend(loc="upper center", bbox_to_anchor=(0.5, -0.20), fontsize=8, ncol=3, frameon=False)
    for missed_cost, color in [(1, BLUE), (5, ORANGE), (10, GREEN)]:
        block = selected.loc[selected.judgement_policy.eq("magnitude_screen") & selected.false_negative_cost.eq(missed_cost)].sort_values("abstention_cost")
        axes[1].plot(block.abstention_cost, block.loss_difference_vs_reconstruct_all, "o-", color=color, ms=3, lw=1.2, label=f"Missed-hot cost {missed_cost}")
        axes[1].fill_between(block.abstention_cost, block.loss_difference_ci_low, block.loss_difference_ci_high, color=color, alpha=0.12, linewidth=0)
    axes[1].axhline(0, color=GREY, lw=0.8)
    axes[1].set(xlabel="Abstention cost / false-hot cost", ylabel="Loss difference versus reconstructing all", title="b  Benefit depends on the declared costs")
    axes[1].legend(loc="upper center", bbox_to_anchor=(0.5, -0.20), frameon=False, fontsize=8)
    selected.to_csv(OUT / "f5_cost_source.csv", index=False)
    pd.DataFrame(rows).to_csv(OUT / "f5_confusion_source.csv", index=False)
    save(figure, "r3_f5_utility")


def learning() -> None:
    figure, axes = plt.subplots(1, 2, figsize=(7.1, 3.4), layout="constrained", sharey=True)
    for axis, protocol_name, title in zip(axes, [RET, PRIOR], ["Retrospective", "Forward hindcast"]):
        table = pd.read_csv(C.RUN / "r3_13_learning_power/admission" / protocol_name / "learning_curves.csv")
        for name, color, label in [("generic_target_disagreement", GREY, "H30 generic"), ("generic_direct_h30_uncertainty", GREEN, "Direct H30 uncertainty"), ("uncertain_support", BLUE, "Uncertain-window design")]:
            selected = table.loc[table.name.eq(name)].groupby("training_groups").retention
            mean = selected.mean() * 100
            lower, upper = selected.quantile(0.1) * 100, selected.quantile(0.9) * 100
            axis.plot(mean.index, mean, "o-", color=color, label=label, ms=3)
            axis.fill_between(mean.index, lower, upper, color=color, alpha=0.12)
        axis.set(title=title, xlabel="Independent training components")
    axes[0].set_ylabel("Retention (%)")
    axes[1].legend(frameon=False, fontsize=8)
    save(figure, "r3_s1_learning")


def cofailure() -> None:
    figure, axes = plt.subplots(1, 2, figsize=(7.1, 3.4), layout="constrained", sharex=True)
    sources = []
    for phase, color in [("before", BLUE), ("during", RED), ("after", GREEN)]:
        rows = []
        for fraction in (0, 0.5, 1):
            path = C.RUN / "r3_15_held_group_replay" / RET / "events" / f"cofailure_{fraction:g}/stratum_results.csv"
            data = pd.read_csv(path)
            selected = data.loc[data.arm.eq("uncertain_support") & data.scope.eq("documented_daily_mean") & data.dimension.eq("event_phase") & data.stratum.eq(phase)]
            rows.append({"cofailure": fraction, "phase": phase, "retention": selected.retention.mean(), "risk": selected.risk_among_admitted.mean()})
        data = pd.DataFrame(rows)
        axes[0].plot(data.cofailure, data.retention * 100, "o-", ms=4, color=color, label=phase.capitalize())
        axes[1].plot(data.cofailure, data.risk * 100, "o-", ms=4, color=color)
        sources.append(data)
    axes[0].set(ylabel="Retention (%)", title="a  Fixed admission heads and thresholds")
    axes[1].set(ylabel="Failures among admitted (%)", title="b  Event timing and common information loss")
    axes[1].axhline(5, ls="--", color=GREY, lw=0.8)
    for axis in axes:
        axis.set_xticks([0, 0.5, 1], ["None", "Half", "All"])
        axis.set_xlabel("Initially usable neighbours removed")
    axes[0].legend(frameon=False, fontsize=8)
    pd.concat(sources).to_csv(OUT / "s2_cofailure_source.csv", index=False)
    save(figure, "r3_s2_cofailure")


def main() -> int:
    C.protocol()
    for directory in (OUT, FIGURES, PAPER):
        directory.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.titlesize": 9, "axes.labelsize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8.5, "pdf.fonttype": 42, "ps.fonttype": 42, "axes.spines.top": False, "axes.spines.right": False, "savefig.dpi": 400})
    recovery()
    mechanisms()
    information()
    transfer()
    decisions()
    learning()
    cofailure()
    C.write_json(OUT / "protocol_fingerprint.json", C.fingerprint(Path(__file__), {"claims": C.RUN / "r3_17_evidence/claim_registry.json"}))
    print("[368] five main and two supplementary evidence figures", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
