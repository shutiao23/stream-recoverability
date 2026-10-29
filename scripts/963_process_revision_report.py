#!/usr/bin/env python3
"""Figures, macros and tables for the 2026-10-28 process-hydrology revision."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_process_review_20261028"
PAPER = ROOT / "paper/wrr_tr"
FIG = PAPER / "figures/process_revision"
REVISION = ROOT / "results/wrr_process_revision_20261029"
COLORS = ["#315a7d", "#ca743c", "#48918a", "#97648b"]


def pct(value, digits=1):
    return f"{100 * value:.{digits}f}"


def num(value, digits=3):
    return f"{value:.{digits}f}"


def save(fig, name):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(FIG / f"{name}.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


def station_roster() -> pd.DataFrame:
    trends = pd.read_csv(
        ROOT / "results/wrr_review_response_20261027/whole_archive/trends.csv",
        usecols=["station_key", "region", "independence_group"],
    ).drop_duplicates("station_key")
    meta = pd.read_csv(
        ROOT / "results/wrr_review_completion_20261024/failure_map/station_failures_and_metadata.csv"
    ).drop_duplicates("station_key")
    ref = pd.read_parquet(
        ROOT / "results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet",
        columns=[
            "station_key",
            "year",
            "design_family",
            "n_complete_years",
            "statistic_class",
            "regulation_status",
            "n_visible_donors",
        ],
    )
    ref = ref.loc[ref.design_family.eq("crossed")]
    span = ref.groupby("station_key").agg(
        year_min=("year", "min"),
        year_max=("year", "max"),
        n_complete=("year", "nunique"),
        statistic_class=("statistic_class", "first"),
        regulation_status=("regulation_status", "first"),
        mean_visible_donors=("n_visible_donors", "mean"),
    )
    roster = trends.merge(meta[["station_key", "latitude", "longitude", "provider"]], on="station_key", how="left")
    roster = roster.merge(span, on="station_key", how="left")
    roster["river_or_code"] = roster.station_key.str.split("|").str[-1]
    return roster.sort_values(["region", "station_key"])


def write_macros():
    protocol = pd.read_csv(OUT / "region_protocol.csv").set_index("region")
    policy = pd.read_csv(OUT / "region_policy_hidden.csv")
    matched = pd.read_csv(OUT / "region_matched.csv")
    time = pd.read_csv(OUT / "time_support_summary.csv")
    stored = pd.read_csv(OUT / "trajectory_stored_quantile_se.csv").set_index("region")
    nested_path = OUT / "trajectory_nested_summary.csv"
    nested = pd.read_csv(nested_path) if nested_path.is_file() else pd.DataFrame()
    offset = {}
    report_path = OUT / "trajectory_budget_report.json"
    if report_path.is_file():
        offset = json.loads(report_path.read_text()).get("offset_check", {})

    def cell(frame, **query):
        block = frame
        for key, value in query.items():
            block = block.loc[block[key].eq(value)]
        if block.empty:
            raise RuntimeError(f"No row for {query}")
        return block.iloc[0]

    air = cell(policy, region="gkd_bayern", peak_hidden=True, policy_choice="air_ridge", method="D2")
    donor_b = cell(policy, region="gkd_bayern", peak_hidden=True, policy_choice="donor_ridge", method="D2")
    donor_f = cell(policy, region="foen", peak_hidden=True, policy_choice="donor_ridge", method="D2")
    trial = cell(matched, matching="gap_overlap_year_donors", region="gkd_bayern", part="common_support", method="D2")
    trial_f = cell(matched, matching="gap_overlap_year_donors", region="foen", part="common_support", method="D2")
    info = cell(matched, matching="trial_plus_reconstructor", region="gkd_bayern", part="common_support", method="D2")
    info_f = cell(matched, matching="trial_plus_reconstructor", region="foen", part="common_support", method="D2")
    info_u = cell(matched, matching="trial_plus_reconstructor", region="gkd_bayern", part="unmatched", method="D2")
    fwd = time.loc[time.family.eq("crossed") & time["mode"].eq("forward")].iloc[0]
    train = pd.read_csv(OUT / "region_training_support.csv")
    air_sd = cell(train, region="gkd_bayern", policy_choice="air_ridge")
    donor_b_sd = cell(train, region="gkd_bayern", policy_choice="donor_ridge")
    donor_f_sd = cell(train, region="foen", policy_choice="donor_ridge")
    gaps = pd.read_csv(OUT / "gap_geometry_summary.csv").set_index("family")
    archive = pd.read_csv(REVISION / "archive_comparison.csv").set_index("panel")
    recon = pd.read_csv(OUT / "time_support_reconstruction.csv")
    recon_fwd = recon.loc[recon.family.eq("crossed") & recon["mode"].eq("forward")].set_index("scheme")
    drift = pd.read_csv(OUT / "train_eval_support.csv")
    air_drift = cell(drift, region="gkd_bayern", policy_choice="air_ridge")
    donor_f_drift = cell(drift, region="foen", policy_choice="donor_ridge")
    observed = pd.read_csv(OUT / "observed_gap_summary.csv").iloc[0]
    water = pd.read_csv(OUT / "water_air_support.csv")
    foen_hist = cell(water, region="foen", period="before_2010")
    foen_eval = cell(water, region="foen", period="from_2010")
    bav_hist = cell(water, region="gkd_bayern", period="before_2010")
    bav_eval = cell(water, region="gkd_bayern", period="from_2010")
    changes = pd.read_csv(REVISION / "trajectory_revision_case_deltas.csv")
    tails_moved = bool(((changes.abs_delta_q05 > 0.05) | (changes.abs_delta_q95 > 0.05)).any())
    lines = [
        r"\newcommand{\PRBavariaAirShare}{" + pct(protocol.loc["gkd_bayern"].policy_air_ridge) + "}",
        r"\newcommand{\PRFoenDonorShare}{" + pct(protocol.loc["foen"].policy_donor_ridge) + "}",
        r"\newcommand{\PRBavariaHiddenFrac}{" + pct(protocol.loc["gkd_bayern"].hidden_peak_fraction) + "}",
        r"\newcommand{\PRFoenHiddenFrac}{" + pct(protocol.loc["foen"].hidden_peak_fraction) + "}",
        r"\newcommand{\PRBavariaAirDailySd}{" + num(air_sd.reconstructor_oof_daily_sd, 3) + "}",
        r"\newcommand{\PRBavariaDonorDailySd}{" + num(donor_b_sd.reconstructor_oof_daily_sd, 3) + "}",
        r"\newcommand{\PRFoenDonorDailySd}{" + num(donor_f_sd.reconstructor_oof_daily_sd, 3) + "}",
        r"\newcommand{\PRBavariaHiddenAirCov}{" + pct(air.coverage90) + "}",
        r"\newcommand{\PRBavariaHiddenAirBias}{" + num(air.bias, 3) + "}",
        r"\newcommand{\PRBavariaHiddenAirAbove}{" + pct(air.above_interval) + "}",
        r"\newcommand{\PRBavariaHiddenDonorCov}{" + pct(donor_b.coverage90) + "}",
        r"\newcommand{\PRBavariaHiddenDonorBias}{" + num(donor_b.bias, 3) + "}",
        r"\newcommand{\PRFoenHiddenDonorCov}{" + pct(donor_f.coverage90) + "}",
        r"\newcommand{\PRFoenHiddenDonorBias}{" + num(donor_f.bias, 3) + "}",
        r"\newcommand{\PRTrialBavariaCov}{" + pct(trial.coverage90) + "}",
        r"\newcommand{\PRTrialFoenCov}{" + pct(trial_f.coverage90) + "}",
        r"\newcommand{\PRTrialBavariaSupport}{" + pct(trial.support_fraction) + "}",
        r"\newcommand{\PRInfoBavariaCov}{" + pct(info.coverage90) + "}",
        r"\newcommand{\PRInfoFoenCov}{" + pct(info_f.coverage90) + "}",
        r"\newcommand{\PRInfoBavariaSupport}{" + pct(info.support_fraction) + "}",
        r"\newcommand{\PRInfoFoenSupport}{" + pct(info_f.support_fraction) + "}",
        r"\newcommand{\PRInfoBavariaUnmatchedCov}{" + pct(info_u.coverage90) + "}",
        r"\newcommand{\PRTimeN}{" + str(int(fwd.n)) + "}",
        r"\newcommand{\PRTimeAllRMSE}{" + num(fwd.all_estimate_rmse, 3) + "}",
        r"\newcommand{\PRTimeWarmRMSE}{" + num(fwd.warm90_estimate_rmse, 3) + "}",
        r"\newcommand{\PRTimeWarmTruthRMSE}{" + num(fwd.warm90_truth_rmse, 3) + "}",
        r"\newcommand{\PRTimeRandomRMSE}{" + num(fwd.random_same_count_estimate_rmse, 3) + "}",
        r"\newcommand{\PRTimeRandomTruthRMSE}{" + num(fwd.random_same_count_truth_rmse, 3) + "}",
        r"\newcommand{\PRTimeBalancedRMSE}{" + num(fwd.time_balanced_estimate_rmse, 3) + "}",
        r"\newcommand{\PRTimeBalancedTruthRMSE}{" + num(fwd.time_balanced_truth_rmse, 3) + "}",
        r"\newcommand{\PRTimeWarmYears}{" + num(fwd.warm90_n_years, 2) + "}",
        r"\newcommand{\PRTimeAllYears}{" + num(fwd.all_n_years, 2) + "}",
        r"\newcommand{\PRTimeWarmHot}{" + pct(fwd.warm90_hot_fraction) + "}",
        r"\newcommand{\PRTimeAllHot}{" + pct(fwd.all_hot_fraction) + "}",
        r"\newcommand{\PRTimeRandomHot}{" + pct(fwd.random_same_count_hot_fraction) + "}",
        r"\newcommand{\PRTimeWarmReconRMSE}{" + num(recon_fwd.loc["warm90"].reconstruction_rmse, 3) + "}",
        r"\newcommand{\PRTimeRandomReconRMSE}{" + num(recon_fwd.loc["random_same_count"].reconstruction_rmse, 3) + "}",
        r"\newcommand{\PRTimeBalancedReconRMSE}{" + num(recon_fwd.loc["time_balanced"].reconstruction_rmse, 3) + "}",
        r"\newcommand{\PRTimeAllReconRMSE}{" + num(recon_fwd.loc["all"].reconstruction_rmse, 3) + "}",
        r"\newcommand{\PRTimeWarmEndWeight}{" + num(fwd.warm90_end_weight, 2) + "}",
        r"\newcommand{\PRTimeAllEndWeight}{" + num(fwd.all_end_weight, 2) + "}",
        r"\newcommand{\PRCalMedianLen}{" + num(gaps.loc["calendar"].median_segment_length, 0) + "}",
        r"\newcommand{\PRCtrlMedianLen}{" + num(gaps.loc["crossed"].median_segment_length, 0) + "}",
        r"\newcommand{\PRCalJJA}{" + pct(gaps.loc["calendar"].mean_jja_fraction) + "}",
        r"\newcommand{\PRCtrlJJA}{" + pct(gaps.loc["crossed"].mean_jja_fraction) + "}",
        r"\newcommand{\PRCalAdjacent}{" + pct(gaps.loc["calendar"].mean_adjacent_year_fraction) + "}",
        r"\newcommand{\PRCtrlAdjacent}{" + pct(gaps.loc["crossed"].mean_adjacent_year_fraction) + "}",
        r"\newcommand{\PRCalSync}{" + pct(gaps.loc["calendar"].mean_shared_year_fraction) + "}",
        r"\newcommand{\PRCtrlSync}{" + pct(gaps.loc["crossed"].mean_shared_year_fraction) + "}",
        r"\newcommand{\PRArchiveTrendN}{" + str(int(archive.loc["trend_cohort"].stations)) + "}",
        r"\newcommand{\PRArchiveRestN}{" + str(int(archive.loc["source_remainder"].stations)) + "}",
        r"\newcommand{\PRArchiveTrendComplete}{" + num(archive.loc["trend_cohort"].median_complete_years, 0) + "}",
        r"\newcommand{\PRArchiveRestComplete}{" + num(archive.loc["source_remainder"].median_complete_years, 0) + "}",
        r"\newcommand{\PRArchiveTrendBavaria}{" + str(int(archive.loc["trend_cohort"].bavaria)) + "}",
        r"\newcommand{\PRArchiveRestBavaria}{" + str(int(archive.loc["source_remainder"].bavaria)) + "}",
        r"\newcommand{\PRArchiveTrendFoen}{" + str(int(archive.loc["trend_cohort"].foen)) + "}",
        r"\newcommand{\PRArchiveTrendUsgs}{" + str(int(archive.loc["trend_cohort"].usgs)) + "}",
        r"\newcommand{\PRArchiveRestUsgs}{" + str(int(archive.loc["source_remainder"].usgs)) + "}",
        r"\newcommand{\PRBavariaAirHistBias}{" + num(air_drift.hist_mask_h30_bias, 3) + "}",
        r"\newcommand{\PRBavariaAirEvalBias}{" + num(air_drift.eval_bias, 3) + "}",
        r"\newcommand{\PRBavariaAirShift}{" + num(air_drift.train_eval_h30_shift, 2) + "}",
        r"\newcommand{\PRFoenDonorHistBias}{" + num(donor_f_drift.hist_mask_h30_bias, 3) + "}",
        r"\newcommand{\PRFoenDonorEvalBias}{" + num(donor_f_drift.eval_bias, 3) + "}",
        r"\newcommand{\PRObsIncomplete}{" + str(int(observed.incomplete_years)) + "}",
        r"\newcommand{\PRObsStations}{" + str(int(observed.stations_with_incomplete)) + "}",
        r"\newcommand{\PRObsMedianRun}{" + num(observed.median_longest_run, 0) + "}",
        r"\newcommand{\PRObsLongThirty}{" + pct(observed.share_run_ge_30) + "}",
        r"\newcommand{\PRObsLongSixty}{" + pct(observed.share_run_ge_60) + "}",
        r"\newcommand{\PRObsAdjacent}{" + pct(observed.mean_adjacent_year_fraction) + "}",
        r"\newcommand{\PRObsSync}{" + pct(observed.mean_shared_year_fraction) + "}",
        r"\newcommand{\PRObsJulAug}{" + pct(observed.share_julaug_complete) + "}",
        r"\newcommand{\PRFoenWaterSlopeHist}{" + num(foen_hist.slope, 2) + "}",
        r"\newcommand{\PRFoenWaterSlopeEval}{" + num(foen_eval.slope, 2) + "}",
        r"\newcommand{\PRFoenWaterCorrHist}{" + num(foen_hist.correlation, 2) + "}",
        r"\newcommand{\PRFoenWaterCorrEval}{" + num(foen_eval.correlation, 2) + "}",
        r"\newcommand{\PRBavariaWaterSlopeHist}{" + num(bav_hist.slope, 2) + "}",
        r"\newcommand{\PRBavariaWaterSlopeEval}{" + num(bav_eval.slope, 2) + "}",
        r"\newcommand{\PRBavariaWaterCorrHist}{" + num(bav_hist.correlation, 2) + "}",
        r"\newcommand{\PRBavariaWaterCorrEval}{" + num(bav_eval.correlation, 2) + "}",
        r"\newcommand{\PRStoredBavariaTailSE}{" + num(stored.loc["gkd_bayern"].median_q95_se, 3) + "}",
        r"\newcommand{\PRStoredFoenTailSE}{" + num(stored.loc["foen"].median_q95_se, 3) + "}",
    ]
    if len(nested):
        nested = nested.set_index("count")
        lines += [
            r"\newcommand{\PRTrajTwentyCRPS}{" + num(nested.loc[20].crps, 3) + "}",
            r"\newcommand{\PRTrajFiveHundredCRPS}{" + num(nested.loc[500].crps, 3) + "}",
            r"\newcommand{\PRTrajTwentyCov}{" + pct(nested.loc[20].coverage90) + "}",
            r"\newcommand{\PRTrajFiveHundredCov}{" + pct(nested.loc[500].coverage90) + "}",
            r"\newcommand{\PRTrajLowerShift}{" + num(offset.get("median_abs_q05_change_500_vs_20", np.nan), 3) + "}",
            r"\newcommand{\PRTrajUpperShift}{" + num(offset.get("median_abs_q95_change_500_vs_20", np.nan), 3) + "}",
            r"\newcommand{\PRTrajTailsMoved}{" + ("yes" if tails_moved else "no") + "}",
            r"\newcommand{\PRTrajN}{" + str(int(nested.loc[20].n)) + "}",
            r"\newcommand{\PRTrajTwentyWidth}{" + num(nested.loc[20].width90, 3) + "}",
            r"\newcommand{\PRTrajFiveHundredWidth}{" + num(nested.loc[500].width90, 3) + "}",
        ]
    (PAPER / "process_revision_values.tex").write_text("\n".join(lines) + "\n")


def write_tables(roster: pd.DataFrame):
    labels = {
        "gkd_bayern": "Bavaria",
        "foen": "Switzerland (FOEN)",
        "usgs_huc03": "USGS HUC03",
        "usgs_huc04": "USGS HUC04",
        "usgs_huc10": "USGS HUC10",
        "usgs_huc17": "USGS HUC17",
        "syke": "Finland (SYKE)",
    }
    region = (
        roster.groupby("region")
        .agg(
            stations=("station_key", "nunique"),
            groups=("independence_group", "nunique"),
            year_min=("year_min", "min"),
            year_max=("year_max", "max"),
            statistic=("statistic_class", "first"),
            regulation=("regulation_status", lambda s: ",".join(sorted(set(map(str, s))))),
            donors=("mean_visible_donors", "mean"),
        )
        .reset_index()
    )
    region["region"] = region.region.map(labels).fillna(region.region)
    lines = [
        r"\begin{table}[t]\centering\small",
        r"\caption{Whole-archive evaluation stations. Regulation labels are project metadata; unmatched\_gages does not mean unregulated. Donor counts are mean visible neighbours in saved leave-one-year-out controlled-gap source cases; the Finnish record is included in that design, not in forward evaluation. Coordinates and station codes are in Supporting Information.}",
        r"\label{tab:sample-domain}",
        r"\resizebox{\textwidth}{!}{\begin{tabular}{lrrlllr}",
        r"\toprule",
        r"Region & Stations & Groups & Years & Statistic & Regulation & Mean donors \\",
        r"\midrule",
    ]
    for row in region.itertuples(index=False):
        statistic = str(row.statistic).replace("_", r"\_")
        regulation = str(row.regulation).replace("_", r"\_")
        lines.append(
            f"{row.region} & {int(row.stations)} & {int(row.groups)} & {int(row.year_min)}--{int(row.year_max)} & "
            f"{statistic} & {regulation} & {row.donors:.1f} \\\\"
        )
    lines += [r"\bottomrule\end{tabular}}", r"\end{table}"]
    (PAPER / "process_sample_table.tex").write_text("\n".join(lines) + "\n")

    time = pd.read_csv(OUT / "time_support_summary.csv")
    fwd = time.loc[time.family.eq("crossed") & time["mode"].eq("forward")].iloc[0]
    recon = pd.read_csv(OUT / "time_support_reconstruction.csv")
    recon_fwd = recon.loc[recon.family.eq("crossed") & recon["mode"].eq("forward")].set_index("scheme")
    lines = [
        r"\begin{table}[t]\centering\small",
        r"\caption{Finite-record H30 slope error ($^{\circ}$C per decade) on \PRTimeN{} forward controlled-gap archives. Random and time-balanced rules keep the same year count as the warm-season screen and use only year and availability. Truth RMSE uses complete-year H30 after selection and isolates the year-set effect. Reconstruction RMSE is the remaining difference between estimated and complete-year slopes on those same years.}",
        r"\label{tab:time-support-legacy-report}",
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        r"Retention & Years & Hot share & Estimate & Year-set & Reconstruction \\",
        r"\midrule",
        rf"Warm-season 90\% & {fwd.warm90_n_years:.2f} & {100*fwd.warm90_hot_fraction:.1f}\% & {fwd.warm90_estimate_rmse:.3f} & {fwd.warm90_truth_rmse:.3f} & {recon_fwd.loc['warm90'].reconstruction_rmse:.3f} \\",
        rf"Same-count random & {fwd.random_same_count_n_years:.2f} & {100*fwd.random_same_count_hot_fraction:.1f}\% & {fwd.random_same_count_estimate_rmse:.3f} & {fwd.random_same_count_truth_rmse:.3f} & {recon_fwd.loc['random_same_count'].reconstruction_rmse:.3f} \\",
        rf"Same-count time-balanced & {fwd.time_balanced_n_years:.2f} & {100*fwd.time_balanced_hot_fraction:.1f}\% & {fwd.time_balanced_estimate_rmse:.3f} & {fwd.time_balanced_truth_rmse:.3f} & {recon_fwd.loc['time_balanced'].reconstruction_rmse:.3f} \\",
        rf"All supported years & {fwd.all_n_years:.2f} & {100*fwd.all_hot_fraction:.1f}\% & {fwd.all_estimate_rmse:.3f} & {fwd.all_truth_rmse:.3f} & {recon_fwd.loc['all'].reconstruction_rmse:.3f} \\",
        r"\bottomrule\end{tabular}",
        r"\end{table}",
    ]
    (PAPER / "process_time_support_table.tex").write_text("\n".join(lines) + "\n")

    policy = pd.read_csv(OUT / "region_policy_hidden.csv")
    hidden = policy.loc[policy.peak_hidden]
    lines = [
        r"\begin{table}[t]\centering\small",
        r"\caption{Hidden-reference-peak recovery by region and daily reconstructor. The hidden-peak label uses withheld complete-year H30. Coverage is nominal 90\%. Above-interval is the share of complete references hotter than the 95th percentile.}",
        r"\label{tab:region-policy}",
        r"\resizebox{\textwidth}{!}{\begin{tabular}{llrrrrrr}",
        r"\toprule",
        r"Region & Reconstructor & Method & Cases & MAE & Bias & 90\% coverage & Above interval \\",
        r"\midrule",
    ]
    names = {"gkd_bayern": "Bavaria", "foen": "Switzerland"}
    for row in hidden.itertuples(index=False):
        policy = str(row.policy_choice).replace("_", r"\_")
        lines.append(
            f"{names.get(row.region, row.region)} & {policy} & {row.method} & "
            f"{int(row.n)} & {row.mae:.3f} & {row.bias:.3f} & {100*row.coverage90:.1f}\\% & {100*row.above_interval:.1f}\\% \\\\"
        )
    lines += [r"\bottomrule\end{tabular}}", r"\end{table}"]
    (PAPER / "process_region_policy_table.tex").write_text("\n".join(lines) + "\n")

    def roster_table(block: pd.DataFrame, caption: str, label: str) -> list[str]:
        lines = [
            r"\begin{table}[p]\centering\footnotesize",
            r"\setlength{\tabcolsep}{3pt}",
            rf"\caption{{{caption}}}",
            rf"\label{{{label}}}",
            r"\begin{tabular}{llrrll}",
            r"\toprule",
            r"Code & Group & Latitude & Longitude & Years & Regulation \\",
            r"\midrule",
        ]
        for row in block.itertuples(index=False):
            group = str(row.independence_group).replace("_", r"\_")
            regulation = str(row.regulation_status).replace("_", r"\_")
            lines.append(
                f"{row.river_or_code} & {group} & {row.latitude:.3f} & {row.longitude:.3f} & "
                f"{int(row.year_min)}--{int(row.year_max)} & {regulation} \\\\"
            )
        lines += [r"\bottomrule\end{tabular}", r"\end{table}", ""]
        return lines

    bavaria = roster.loc[roster.region.eq("gkd_bayern")]
    other = roster.loc[~roster.region.eq("gkd_bayern")]
    station_lines = roster_table(
        bavaria,
        "Bavarian whole-archive stations. Regulation labels are project metadata.",
        "tab:station-roster-bavaria",
    ) + roster_table(
        other,
        "Non-Bavarian whole-archive stations, including Switzerland (FOEN) and USGS HUC17. Regulation labels are project metadata.",
        "tab:station-roster-other",
    )
    (PAPER / "process_station_roster_table.tex").write_text("\n".join(station_lines) + "\n")
    roster.to_csv(REVISION / "station_roster.csv", index=False)

    gaps = pd.read_csv(OUT / "gap_geometry_summary.csv").set_index("family")
    names = {"calendar": "Empirical calendar", "crossed": "Controlled 30--90 d"}
    gap_lines = [
        r"\begin{table}[t]\centering\small",
        r"\caption{Forward-mask geometry on the 41-station trend cohort with twenty replicates. Year selection after a seven-year burn-in is shared. Segment length and season come from the copied empirical calendars or from the controlled-gap design. Shared-year fraction is the share of masked station-years that are also masked at another station in the same connected group.}",
        r"\label{tab:gap-geometry}",
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        r"Family & Median length (d) & JJA share & Adjacent years & Shared years & Stations \\",
        r"\midrule",
    ]
    for family in ("calendar", "crossed"):
        row = gaps.loc[family]
        gap_lines.append(
            f"{names[family]} & {row.median_segment_length:.0f} & {100*row.mean_jja_fraction:.1f}\\% & "
            f"{100*row.mean_adjacent_year_fraction:.1f}\\% & {100*row.mean_shared_year_fraction:.1f}\\% & "
            f"{int(row.stations)} \\\\"
        )
    gap_lines += [r"\bottomrule\end{tabular}", r"\end{table}"]
    (PAPER / "process_gap_geometry_table.tex").write_text("\n".join(gap_lines) + "\n")

    # The manuscript table is process_gap_revision_archive_table.tex. Keep a
    # compatibility alias and do not emit a second tab:archive-comparison label.
    (PAPER / "process_archive_table.tex").write_text(
        r"\input{process_gap_revision_archive_table.tex}" + "\n"
    )

    # The old table mixed longest annual runs with segment medians. Keep a
    # compatibility input pointing to the common annual-longest-gap statistic.
    (PAPER / "process_observed_gap_table.tex").write_text(
        r"\input{process_gap_revision_table.tex}" + "\n"
    )



def figures(roster: pd.DataFrame):
    plt.rcParams.update(
        {
            "font.family": "Liberation Sans",
            "font.size": 11,
            "axes.titlesize": 11,
            "axes.labelsize": 10.5,
            "xtick.labelsize": 9.5,
            "ytick.labelsize": 9.5,
            "legend.fontsize": 8.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "pdf.fonttype": 42,
            "figure.facecolor": "white",
        }
    )
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    names = {
        "gkd_bayern": "Bavaria",
        "foen": "Switzerland",
        "syke": "Finland",
        "usgs_huc03": "USGS HUC03",
        "usgs_huc04": "USGS HUC04",
        "usgs_huc10": "USGS HUC10",
        "usgs_huc17": "USGS HUC17",
    }
    for i, (region, block) in enumerate(roster.groupby("region")):
        ax.scatter(
            block.longitude,
            block.latitude,
            s=28,
            color=COLORS[i % 4],
            label=f"{names.get(region, region)} (n={len(block)})",
            alpha=0.85,
        )
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(loc="lower left", frameon=False, ncol=2)
    save(fig, "01_sample_domain")

    policy = pd.read_csv(OUT / "region_policy_hidden.csv")
    hidden = policy.loc[policy.peak_hidden & policy.method.eq("D2")].copy()
    hidden["label"] = hidden.region.map({"gkd_bayern": "Bavaria", "foen": "Switzerland"}) + " / " + hidden.policy_choice.str.replace("_", " ")
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.1))
    axes[0].bar(hidden.label, 100 * hidden.coverage90, color=[COLORS[0] if "Switzerland" in x else COLORS[1] for x in hidden.label])
    axes[0].set_ylabel("Nominal 90% coverage (%)")
    axes[0].tick_params(axis="x", rotation=20)
    axes[1].bar(hidden.label, hidden.bias, color=[COLORS[0] if "Switzerland" in x else COLORS[1] for x in hidden.label])
    axes[1].axhline(0, color="0.5", lw=1)
    axes[1].set_ylabel("H30 bias ($^{\\circ}$C)")
    axes[1].tick_params(axis="x", rotation=20)
    save(fig, "02_region_recovery")

    time = pd.read_csv(OUT / "time_support_summary.csv")
    fwd = time.loc[time.family.eq("crossed") & time["mode"].eq("forward")].iloc[0]
    labels = ["Warm-season", "Random", "Time-balanced", "All years"]
    estimate = [fwd.warm90_estimate_rmse, fwd.random_same_count_estimate_rmse, fwd.time_balanced_estimate_rmse, fwd.all_estimate_rmse]
    truth = [fwd.warm90_truth_rmse, fwd.random_same_count_truth_rmse, fwd.time_balanced_truth_rmse, fwd.all_truth_rmse]
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    x = np.arange(len(labels))
    ax.bar(x - 0.18, estimate, 0.36, label="Saved D2 estimates", color=COLORS[0])
    ax.bar(x + 0.18, truth, 0.36, label="Complete-year H30 on the same years", color=COLORS[2])
    ax.set_xticks(x, labels)
    ax.set_ylabel("Slope RMSE ($^{\\circ}$C decade$^{-1}$)")
    ax.legend(frameon=False)
    # Do not overwrite Figure 10. The manuscript figure is written by 970 from
    # the CDF/Sxx experiment; this four-bar chart is a named legacy reference.
    save(fig, "03_time_support_legacy")

    # Figure 11 is generated by 970 from the source-role experiment. Never
    # overwrite it with the former pooled mean curves or the uncalibrated 962 plot.


def write_supporting():
    text = r"""\section{Exploratory process and numerical diagnostics}
These checks were developed after inspecting earlier regional and time-support results. They are exploratory and reuse the opened archive; selection of six stations before a numerical replay is not preregistration of the research questions.

\subsection{Common support and common-weight standardization}
Common geometric cells contain gap length, training-peak overlap, year and visible-donor bins. Screening to shared cells preserves region-specific cell frequencies and is not balancing. The primary standardized target assigns identical weights proportional to the smaller regional cell count; equal-cell weighting is a sensitivity. Joint-cell frequency TV becomes zero under either common target, but within-bin continuous quantities and training histories remain imbalanced. In the geometry min-count analysis, mean training complete-year counts are 9.78 in FOEN versus 22.96 in Bavaria (SMD -3.052); after adding reconstructor they are 8.50 versus 20.18 (SMD -2.707). Saved CSV files also report continuous means, weighted KS distances and missing-weight fractions. A coverage contrast remains under these common geometric-cell weights; residual within-cell and history differences remain, and the comparison does not identify a reconstructor effect or exclude river processes. The absence of a Swiss air-ridge stratum prevents corresponding cross-region comparison of the main Bavarian failure layer.
\input{process_region_revision_table.tex}
\input{process_region_revision_balance.tex}
\input{process_region_policy_table.tex}

\subsection{Annual water--air associations}
Pooled annual associations mix station differences and within-station variation. We therefore center both H30 quantities within station and period, before/from 2010, and pool those centered observations. Both periods of a sampled connected group remain paired in 10,000 bootstrap replicates (seed 20261029); station-paired resampling is an additional sensitivity, not an assumption-free replacement. FOEN has two groups, with only three distinct bootstrap group compositions; its intervals are particularly coarse. Similar annual within-slope point estimates neither establish equivalence nor validate gap-day residuals, heat-peak timing, tails or autocorrelation. Each variable is its own annual maximum and their maximizing dates need not coincide.
\input{process_water_revision_table.tex}
\input{process_water_revision_correlation.tex}
\input{process_water_revision_uncertainty.tex}

\subsection{Year-set comparisons and retained baselines}
The original single random selection and incomplete-year-only spacing rule are retained as labeled legacy comparators in the table below. The exact subset expectation and the two selectors that incorporate fixed complete years are the current exploratory extensions. Paired intervals in this table use the common updated resampling specification; the previous resampling tables remain archived with the earlier revision.
\input{process_experiments_time_table.tex}
\input{process_gap_revision_supporting.tex}
\input{process_gap_revision_table.tex}
\input{process_gap_revision_archive_table.tex}
\input{process_gap_geometry_table.tex}
\input{process_station_roster_table.tex}
\subsection{Earlier uncalibrated-only trajectory diagnostic}
The original three-seed check reports raw, uncalibrated endpoints in the fixed 27-case sample. Its small pooled median does not establish stratified stability. The subsequent experiment section additionally regenerates the original source-calibration roles and re-estimates offsets at each budget; the table below is retained specifically as the uncalibrated reference.
\input{process_trajectory_revision_table.tex}
"""
    (PAPER / "process_revision_supporting.tex").write_text(text)


def main() -> int:
    roster = station_roster()
    write_macros()
    write_tables(roster)
    figures(roster)
    write_supporting()
    print("wrote process revision figures and tables", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
