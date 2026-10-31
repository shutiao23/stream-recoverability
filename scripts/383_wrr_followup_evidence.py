#!/usr/bin/env python3
"""Bind follow-up manuscript text, SI tables and figures to computed evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import wrr_r3_common as C

RUN = C.READY / "followup_20261021"
OUT = RUN / "evidence"
PAPER = C.ROOT / "paper/wrr"
PROTOCOLS = ("leave_one_year_out", "strictly_prior_years")
ARM = {"quantile_direct": "Q direct", "quantile_window": "Q window", "probability_direct": "P direct", "probability_window": "P window"}


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def read(relative):
    return pd.read_csv(RUN / relative)


def table(frame, caption, label):
    source = OUT / f"{label}.csv"
    frame.to_csv(source, index=False)
    display = frame.copy()
    labels = {"reconstruct_all": "All reconstructed", "frozen_magnitude_screen": "Frozen screen", "all_unknown": "All unknown", "all_hot": "All hot", "all_cool": "All cool", "random_matched_screen": "Matched random",
              "direct_cost_source_direct": "Source probability", "direct_cost_local_direct": "Local probability", "direct_cost_source_window": "Source prob. + window", "direct_cost_local_window": "Local prob. + window",
              "seasonal_state_slow_short": "State residuals", "raw_block14": "Raw blocks", "visible_adjustment": "Visible correction", "priority": "Priority", "air2stream3": "Air2stream-3", "air2stream8": "Air2stream-8", "csdi_fixed8": "CSDI (8)",
              "source_original": "Source original", "source_no_donors": "Source no donor", "Swiss_opened_test": "Swiss test", "no_donors": "No donors", "original": "Original",
              "doy_climatology": "Climatology", "linear_interp": "Interpolation", "length_90_minus_30_full_support": "Length 90-30", "position_30_full_minus_none": "Position full-none",
              "air_common": "Air subset", "air_flow_common": "Flow subset"}
    for column in display.select_dtypes(include="object"):
        display[column] = display[column].map(lambda value: labels.get(value, value))
    display = display.rename(columns={"n_candidates": "N", "n_cases": "N", "n_groups": "G", "n_station_years": "Years", "accepted": "Accepted", "failures": "Failed", "n_calibration_groups": "Cal. G",
                                      "false_negative": "FN", "false_positive": "FP", "unknown": "Unknown", "retention": "Retention", "risk": "Risk", "formal_accepted": "Formal N", "mean_signed_error_C": "Bias C", "h30_mae_C": "MAE C",
                                      "n_available": "Avail.", "n_unavailable": "Unavail.", "mae_on_available_C": "MAE C",
                                      "training_latest_target_year": "Train through", "n_train_groups": "Train G", "n_cal_groups": "Cal. G", "test_event_years": "Event years", "held_region_proxy": "Region proxy", "test_bounded_loss_mean": "Mean X", "test_bounded_loss_upper": "Upper X"})
    tabular = display.to_latex(index=False, escape=True, na_rep="--", float_format=lambda value: f"{value:.3f}")
    return ("\\begin{table}\n\\caption{" + caption + "}\n\\label{tab:" + label + "}\n\\centering\n\\scriptsize\n"
            "\\resizebox{\\textwidth}{!}{%\n" + tabular + "}\n\\end{table}\n")


def numeric_evidence():
    tables, full_operating, full_contrasts, costs, whole, info, nested, histories, budgets = [], [], [], [], [], [], [], [], []
    for protocol in PROTOCOLS:
        short = "Retro" if protocol == PROTOCOLS[0] else "Past local"
        for seed in (101, 202, 303):
            operating = read(f"factorial/{protocol}/seed_{seed}/operating.csv")
            full_operating.append(operating)
            full_contrasts.append(read(f"factorial/{protocol}/seed_{seed}/contrasts.csv"))
        a = read(f"robustness/{protocol}/whole_procedure_contrasts.csv")
        a["Protocol"] = "Retro" if protocol == PROTOCOLS[0] else "Forward"
        whole.append(a)
        a = read(f"external_cost/{protocol}/decision_costs.csv")
        a = a.loc[a.threshold.eq("local_training_q90") & a.fn_cost.eq(5) & a.abstention_cost.eq(0.05)].copy()
        a["Protocol"] = "Retro" if protocol == PROTOCOLS[0] else "Forward"
        costs.append(a)
        a = read(f"information_calibration/{protocol}/information_operating.csv")
        a = a.loc[a.objective.eq("quantile") & a.window].groupby(["fitting_information", "calibration_information", "population"])[["retention", "risk"]].mean().reset_index()
        a["Protocol"] = short
        info.append(a)
        a = read(f"mechanism/{protocol}/nested_contrasts.csv")
        a = a.loc[a.method.isin(["doy_climatology", "linear_interp"])].copy()
        a["Protocol"] = short
        nested.append(a)
        a = read(f"history_boundaries/{protocol}/summary.csv")
        a["Protocol"] = "Retro" if protocol == PROTOCOLS[0] else "Forward"
        histories.append(a)
        a = read(f"information_calibration/{protocol}/calibration_budgets.csv")
        a = a.loc[a.selection.eq("empirical")].groupby("n_calibration_groups").agg(subsets=("risk", "size"), retention_mean=("retention", "mean"), retention_min=("retention", "min"), retention_max=("retention", "max"), risk_mean=("risk", "mean"), risk_min=("risk", "min"), risk_max=("risk", "max")).reset_index()
        a["Protocol"] = "Retro" if protocol == PROTOCOLS[0] else "Forward"
        budgets.append(a)
    operating = pd.concat(full_operating, ignore_index=True)
    contrasts = pd.concat(full_contrasts, ignore_index=True)
    operating.to_csv(OUT / "four_cell_operating_all.csv", index=False)
    contrasts.to_csv(OUT / "four_cell_contrasts_all.csv", index=False)
    summary = operating.loc[operating.selection.eq("empirical")].groupby(["protocol", "arm"]).agg(N=("n_candidates", "first"), G=("n_groups", "first"), ret_min=("retention", "min"), ret_max=("retention", "max"), risk_min=("risk", "min"), risk_max=("risk", "max")).reset_index()
    for name in ["ret_min", "ret_max", "risk_min", "risk_max"]:
        summary[name] *= 100
    summary["protocol"] = summary.protocol.map({PROTOCOLS[0]: "Retro", PROTOCOLS[1]: "Past local"})
    summary["arm"] = summary.arm.map(ARM)
    tables.append(table(summary, "Four-cell objective/window analysis on the identical documented-mean admission pool. Ranges span three split seeds, not independent replications. Q is the 0.9 absolute-error quantile; P is direct failure probability. Retention and selected risk are percentages. Formal admission is zero throughout.", "followup_four_cells"))
    a = pd.concat(whole, ignore_index=True)
    for name in ("mean_retention_difference", "ci_low", "ci_high"):
        a[name] *= 100
    short_names = {"('quantile', True)": "Q window", "('quantile', False)": "Q direct", "('probability', True)": "P window", "('probability', False)": "P direct"}
    a["Comparison"] = a.left.map(short_names) + " minus " + a.right.map(short_names)
    a = a.rename(columns={"n_refits": "Refits", "mean_retention_difference": "Difference pp", "ci_low": "Lower", "ci_high": "Upper", "joint_five_point_and_test_risk_evidence_fraction": "Joint fraction"})
    tables.append(table(a[["Protocol", "Comparison", "Refits", "Difference pp", "Lower", "Upper", "Joint fraction"]], "Complete-procedure refits of all four cells. Learning, calibration groups and evaluation groups are resampled. Retention differences are percentage points. The last column requires both a five-point sample gain and the specified test-group bounded-risk evidence; it is a descriptive bootstrap frequency, not attained power in a new population.", "followup_whole_procedure"))
    a = pd.concat(costs, ignore_index=True)
    tables.append(table(a[["Protocol", "arm", "n_candidates", "loss", "false_negative", "false_positive", "unknown"]], "Use-matched Swiss decisions at missed-hot cost five and unknown cost 0.05. The original screen is unchanged; added probability policies are post-test development. Random-matched counts are exact expectations. All other counts are realized outcomes in the same original pool.", "followup_absolute_costs"))
    failures = read("transfer/leave_one_year_out/station_results.csv")
    tables.append(table(failures, "Every Swiss station in the original frozen-window policy. No high-risk station is removed from the primary result. Detailed accepted-failure years, gap positions, proxy residuals and flow coverage remain in the accompanying case table.", "followup_station_failures"))
    tables.append(table(pd.concat(info, ignore_index=True), "Information intervention with identical masks and recomputed reconstruction/uncertainty. Entries average three source splits for the full quantile model. Fitting and calibration information vary independently. This separates one information channel from domain shift without identifying its full cause.", "followup_information"))
    a = pd.concat(nested, ignore_index=True)
    tables.append(table(a[["Protocol", "method", "direction", "contrast", "mean", "ci_low", "ci_high", "n_groups", "n_station_years"]], "Truth-assisted nested-gap mechanism assay. Every direction compares length and position in its own common feasible station-years. True support stays fully hidden under extension; the thirty-day control is displaced ninety days. These are mechanism masks, not deployable peak-location rules.", "followup_nested"))
    quality, trajectory_intervals = [], []
    keys = ["network_id", "station_id", "year", "realization_id"]
    for role in ("development", "calibration", "test"):
        frame = pd.read_parquet(RUN / "trajectory/leave_one_year_out" / role / "cases.parquet")
        available = frame.loc[frame.status.eq("available") & frame.n_draws.eq(128)]
        common = available.groupby(keys).variant.nunique()
        common = common[common.eq(3)].index.to_frame(index=False)
        paired = frame.merge(common, on=keys, validate="many_to_one")
        for (variant, draws), block in paired.groupby(["variant", "n_draws"]):
            if draws == 0:
                continue
            quality.append({"role": role, "variant": variant, "draws": draws, "N": len(block), "G": block.independence_group.nunique(), "MAE_C": block.absolute_error_C.mean(), "bias_C": block.signed_error_C.mean(), "coverage90": block.covered90.astype(float).mean(), "width_C": block.interval_width_C.mean(), "CRPS_C": block.crps_C.mean(), "Brier": block.brier_local.mean()})
        if role == "test":
            paired.loc[paired.n_draws.eq(128)].to_parquet(OUT / "trajectory_common_test.parquet", index=False)
    quality = pd.DataFrame(quality)
    quality.to_csv(OUT / "trajectory_common_all.csv", index=False)
    tables.append(table(quality.loc[quality.draws.eq(128)], "Trajectory quality at 128 draws on each role's intersection of supported cases. Unsupported state-model cases are reported separately and never treated as zero uncertainty. State conditioning uses visible water residuals and available air/flow states; common-subset performance is supplementary development, not new confirmation.", "followup_trajectory"))
    a = read("system_factorial/original_pool_operating.csv")
    tables.append(table(a.drop(columns=["training_and_calibration", "n_groups", "mae_on_available_C"]), "Reconstruction--admission factorial on all original Swiss controlled candidates in seven components, with unavailable reconstructions retained as unknown. Fitting/calibration use the identical shared subset within each information tier; matched reconstruction errors and paired supported-subset results are supplied in the source CSVs. Each method learns its own error event. Window features come from the common reconstruction for every method. CSDI retains its fixed eight-draw scope, not its performance ceiling; all formal policies refuse everything.", "followup_system"))
    tables.append(table(pd.concat(histories, ignore_index=True), "History length and explicit year-boundary/fragmented gaps on identical target years feasible for all three history budgets. These long-history comparison subsets do not replace the original population. Prospective histories are strictly earlier; retrospective histories use the closest permitted years.", "followup_history"))
    tables.append(table(pd.concat(budgets, ignore_index=True), "Target calibration budget sensitivity for the original frozen score on the unchanged Swiss test pool. Budgets count independent calibration groups. Means and ranges span enumerated or fixed-seed sampled subsets, not new independent test repetitions. No subset certifies positive admission under the formal rule.", "followup_calibration_budget"))
    tables.append(table(read("robustness/regional_forward_events.csv").drop(columns="interpretation"), "Provider-region and forward-event holdouts. Connected components from the target provider are removed from source fitting/calibration; global targets stop at 2014 and event test years are 2015, 2018 and 2022. All local reconstruction histories are strictly earlier. Regional proxies do not verify hydrological mechanisms.", "followup_region_events"))
    (PAPER / "si_r4_tables.tex").write_text("% Generated by script 383; each table has a source CSV.\n" + "\n".join(tables))
    q = contrasts.loc[contrasts.protocol.eq(PROTOCOLS[0]) & contrasts.left.eq("quantile_window")]
    p = contrasts.loc[contrasts.protocol.eq(PROTOCOLS[0]) & contrasts.left.eq("probability_window") & contrasts.right.eq("probability_direct")]
    cost = pd.concat(costs, ignore_index=True)
    c = cost.loc[cost.Protocol.eq("Retro")].set_index("arm")
    f = cost.loc[cost.Protocol.eq("Forward")].set_index("arm")
    procedure = read("robustness/leave_one_year_out/whole_procedure_contrasts.csv")
    whole_q, whole_p = procedure.iloc[0], procedure.iloc[1]
    text = (
        "\\subsection{Supplementary objective, use and failure checks}\n\n"
        f"The matched four-cell retrospective analysis contains 54,837 cases in 144 components. Added windows change retention by {100*q.retention_difference.min():.2f} to {100*q.retention_difference.max():.2f} percentage points with quantile learning and {100*p.retention_difference.min():.2f} to {100*p.retention_difference.max():.2f} with direct failure-probability learning. The learning objective does not recover a stable five-point representation advantage. Earlier-local-input and full-procedure results, including their uncertainty, are retained in SI; no non-significant result is declared proof of equivalence.\n\n"
        f"Across 1,000 full-procedure refits, retrospective window increments average {100*whole_q.mean_retention_difference:.2f} points [{100*whole_q.ci_low:.2f}, {100*whole_q.ci_high:.2f}] for quantile learning and {100*whole_p.mean_retention_difference:.2f} [{100*whole_p.ci_low:.2f}, {100*whole_p.ci_high:.2f}] for failure-probability learning. The wide intervals permit both harm and practically relevant benefit; superiority and equivalence remain unestablished.\n\n"
        f"At the same Swiss retrospective FN5/A0.05 setting, random rejection at the original screen's retention has expected loss {c.loc['random_matched_screen','loss']:.4f}. Direct hot-probability decisions using source-calibrated direct features have loss {c.loc['direct_cost_source_direct','loss']:.4f}, still above always unknown at 0.0500; their forward loss is {f.loc['direct_cost_source_direct','loss']:.4f}. Thus neither a magnitude tolerance nor a favorable reconstruct-all comparison determines the best classification action. These added policies use opened data and establish no new confirmatory superiority.\n\n"
        "The 669 retrospective Swiss masks represent 105 distinct station-years in seven stations, with 17 distinct hot station-years; they are generated single gaps retaining annual boundary observations. Sixteen of 33 frozen admitted failures occur at CH\\_2327, Dischmabach--Davos, Kriegsmatte, and all sixteen underestimate H30. Fifteen use air reconstruction. The official station inventory confirms a roughly 43-km$^2$ alpine catchment with 0.7\\% glacial area \\cite{foen2327}; this is not evidence of a specific regulation or groundwater class. Gap-period cold proxy errors can exceed visible-period errors, while low-flow overlap varies. Source donor removal raises unscreened error but does not reproduce the full Swiss distribution. Persistent peak-season proxy mismatch is a testable explanation, not an identified low-flow or melt mechanism \\cite{michel2020}. All original groups remain in the primary result.\n"
    )
    paragraphs = text.split("\n\n")
    if len(paragraphs) != 5:
        raise RuntimeError("Objective/use/failure paragraph structure changed")
    objective = "\n\n".join(paragraphs[1:3])
    objective = objective.replace("The matched four-cell retrospective analysis contains", "The choice of learning objective does not reveal a stable extra-window gain in the source cohort. The matched four-cell retrospective analysis contains")
    (PAPER / "r4_results.tex").write_text(
        "The additional objective comparisons use opened data and do not constitute a new independent test. " + objective + "\n")
    (PAPER / "r4_use_results.tex").write_text(paragraphs[3] + "\n")
    (PAPER / "r4_transfer_results.tex").write_text(paragraphs[4] + "\n")


def figures():
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42})
    data = read("external_cost/leave_one_year_out/decision_costs.csv")
    data = data.loc[data.threshold.eq("local_training_q90") & data.fn_cost.eq(5)]
    names = {"reconstruct_all": "Reconstruct all", "frozen_magnitude_screen": "Frozen magnitude", "random_matched_screen": "Matched random", "direct_cost_source_direct": "Direct cost (source)", "all_unknown": "All unknown", "all_hot": "All hot", "all_cool": "All cool"}
    colors = ["#315c87", "#b56a35", "#898989", "#318675", "#c7c7c7", "#9477a8", "#bca573"]
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.5), gridspec_kw={"width_ratios": [1, 1.2]}, layout="constrained")
    subset = data.loc[data.abstention_cost.eq(0.05)].set_index("arm")
    displayed = list(names)[:5]
    correct = np.array([subset.loc[name, "true_positive"] + subset.loc[name, "true_negative"] for name in displayed]) / 669
    wrong = np.array([subset.loc[name, "false_positive"] + subset.loc[name, "false_negative"] for name in displayed]) / 669
    unknown = np.array([subset.loc[name, "unknown"] for name in displayed]) / 669
    for label, values, bottom, color in [("Correct", correct, np.zeros(5), "#548b83"), ("Mistaken", wrong, correct, "#c96a58"), ("Unknown", unknown, correct + wrong, "#d7d7d7")]:
        axes[0].barh(range(5), values, left=bottom, label=label, color=color)
    axes[0].set(yticks=range(5), yticklabels=[names[name] for name in displayed], xlim=(0, 1), xlabel="Fraction of original candidates", title="(a) Outcomes at unknown cost 0.05")
    axes[0].invert_yaxis()
    axes[0].legend(loc="lower center", bbox_to_anchor=(0.5, -0.32), ncol=3, frameon=False, fontsize=8)
    for (name, label), color in zip(names.items(), colors):
        block = data.loc[data.arm.eq(name)].sort_values("abstention_cost")
        axes[1].plot(block.abstention_cost, block.loss, marker="o", ms=3, color=color, label=label, linestyle="--" if name in {"all_hot", "all_cool"} else "-")
    axes[1].set(xlabel="Unknown-answer cost", ylabel="Absolute loss per original candidate", title="(b) Explicit deployable references", ylim=(0, 0.9))
    axes[1].legend(fontsize=7, frameon=False, ncol=2, loc="center right", bbox_to_anchor=(1, 0.72))
    for suffix in ("pdf", "png"):
        fig.savefig(PAPER / f"figures/r4_f5_utility.{suffix}", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.3), layout="constrained")
    for ax, protocol in zip(axes, PROTOCOLS):
        frame = pd.concat([read(f"factorial/{protocol}/seed_{seed}/risk_retention.csv") for seed in (101, 202, 303)])
        for arm, label in ARM.items():
            block = frame.loc[frame.arm.eq(arm)].groupby("requested_retention")[["retention", "risk"]].mean()
            ax.plot(100 * block.retention, 100 * block.risk, label=label)
        ax.axhline(5, color="gray", ls=":")
        ax.set(xlabel="Retention (%)", ylabel="Selected failure (%)", title="Retrospective" if protocol == PROTOCOLS[0] else "Earlier local histories", ylim=(0, 16))
    axes[0].legend(frameon=False, fontsize=8)
    fig.savefig(PAPER / "figures/r4_s3_risk_retention.pdf")
    plt.close(fig)
    data = read("transfer/leave_one_year_out/accepted_failures.csv")
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.3), layout="constrained")
    for station, block in data.groupby("station_id"):
        focus = station == "CH_2327"
        axes[0].scatter(block.gap_air_proxy_bias_C, block.signed_error_C, label=station if focus else None, color="#be624b" if focus else "#9caab4", alpha=0.8)
    axes[0].axhline(-0.5, color="gray", ls=":")
    axes[0].set(xlabel="Gap air-proxy bias (C; evaluation only)", ylabel="H30 signed error (C)", title="(a) Every admitted failure")
    axes[0].legend(frameon=False)
    quality = read("evidence/trajectory_common_all.csv")
    quality = quality.loc[quality.role.eq("test")]
    for variant, block in quality.groupby("variant"):
        axes[1].plot(block.draws, block.coverage90, marker="o", label=variant.replace("_", " "))
    axes[1].axhline(0.9, color="gray", ls=":")
    axes[1].set(xlabel="Trajectory samples", ylabel="90% H30 band coverage", title="(b) Common supported Swiss cases", ylim=(0.5, 1))
    axes[1].legend(fontsize=7, frameon=False)
    fig.savefig(PAPER / "figures/r4_s4_failure_trajectory.pdf")
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    numeric_evidence()
    figures()
    # Audit outputs must not become inputs to the evidence they subsequently verify.
    inputs = {str(path.relative_to(RUN)): path for path in RUN.rglob("*.csv") if not {"evidence", "completion"}.intersection(path.parts)}
    C.write_json(OUT / "bindings.json", run_record(inputs, manuscript="paper/wrr/r4_results.tex", tables="paper/wrr/si_r4_tables.tex", new_confirmation=False))
    print("[383] follow-up text, eleven tables and three figures generated", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
