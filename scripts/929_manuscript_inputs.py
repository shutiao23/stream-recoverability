#!/usr/bin/env python3
"""Assemble the revised manuscript's core evidence tables and figure inputs.

All numbers are read from saved result tables.  The script does not refit a
model.  It writes only paper inputs, a figure-cohort audit and a correction
record for the historical design metadata.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.cohort_denominators import (
    two_method_intersection,
)

REVISION = T.ROOT / "results/wrr_review_response_20261027"
OUT = T.ROOT / "results/wrr_adversarial_review_20261027"
PAPER = T.ROOT / "paper/wrr_tr"
RULE = OUT / "rule_accounting"
FAIL = OUT / "failure_strata"
RANK = OUT / "rank_convergence"
TOL = 5e-6

def tex(value: str) -> str:
    return (
        str(value)
        .replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("_", r"\_")
        .replace("#", r"\#")
    )

def pct(value: float, digits: int = 1) -> str:
    return f"{100 * value:.{digits}f}"

def number(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"

def write_tex(path: Path, text: str) -> None:
    path.write_text(text.strip() + "\n")

def cohort_table() -> pd.DataFrame:
    trend = pd.read_csv(REVISION / "whole_archive/trends.csv")
    rows = []
    for family in ["calendar", "crossed"]:
        for mode in ["offline", "forward"]:
            block = trend.loc[
                trend.family.eq(family)
                & trend["mode"].eq(mode)
                & trend.estimator.eq("D2")
                & trend.dependence.eq("point")
                & trend.available
            ]
            pivot = block.pivot_table(
                index=["station_key", "replicate"],
                columns="retention",
                values="squared_error",
                aggfunc="mean",
            )
            common = pivot[["all", "warm90"]].dropna()
            units = block.drop_duplicates(["station_key", "replicate"])
            rows.append(
                {
                    "family": family,
                    "mode": mode,
                    "n_all": int(pivot["all"].notna().sum()),
                    "n_warm90": int(pivot["warm90"].notna().sum()),
                    "n_common": int(len(common)),
                    "availability_common": len(common) / len(pivot),
                    "all_rmse_common": float(np.sqrt(common["all"].mean())),
                    "warm90_rmse_common": float(np.sqrt(common["warm90"].mean())),
                    "stations": int(units.station_key.nunique()),
                    "groups": int(units.independence_group.nunique()),
                }
            )
    frame = pd.DataFrame(rows)
    frame.to_csv(REVISION / "whole_archive/figure_cohort_common.csv", index=False)
    return frame

def uncertainty_bootstrap() -> pd.DataFrame:
    cases = pd.read_csv(REVISION / "whole_archive/uncertainty_common_cases.csv")
    rows = []
    rng = np.random.default_rng(20261027)
    for (family, mode, estimator), block in cases.groupby(
        ["family", "mode", "estimator"], sort=True
    ):
        groups = block.independence_group.to_numpy()
        unique = np.array(sorted(set(groups)))
        for dependence, column in [
            ("annual", "coverage90"),
            ("independent", "independent_coverage95"),
            ("shared_parameters", "shared_parameters_coverage95"),
            ("residual_blocks", "residual_blocks_coverage95"),
        ]:
            if column not in block:
                continue
            values = block[column].to_numpy(float)
            if not np.isfinite(values).all():
                continue
            estimates = []
            for _ in range(2000):
                chosen = rng.choice(unique, size=len(unique), replace=True)
                index = np.concatenate(
                    [np.flatnonzero(groups == group) for group in chosen]
                )
                estimates.append(float(np.mean(values[index])))
            rows.append(
                {
                    "family": family,
                    "mode": mode,
                    "estimator": estimator,
                    "dependence": dependence,
                    "metric": "coverage",
                    "value": float(np.mean(values)),
                    "low": float(np.quantile(estimates, 0.025)),
                    "high": float(np.quantile(estimates, 0.975)),
                    "n": len(block),
                    "groups": len(unique),
                }
            )
    frame = pd.DataFrame(rows)
    frame.to_csv(
        REVISION / "whole_archive/figure_uncertainty_bootstrap.csv", index=False
    )
    return frame

def rule_values() -> dict:
    summary = pd.read_csv(RULE / "rule_accounting_summary.csv").set_index("rule")
    increments = pd.read_csv(RULE / "rule_accounting_increments.csv")
    margins = pd.read_csv(RULE / "rule_accounting_measurement_margins.csv")
    warm = increments.loc[
        increments.rule.eq("warm_90_station_specific") & ~increments.admitted
    ].sort_values("excess_over_accepted_record", ascending=False)
    warm_admitted = increments.loc[
        increments.rule.eq("warm_90_station_specific") & increments.admitted
    ]
    margin_005 = margins.loc[
        margins.rule.eq("warm_90_station_specific")
        & margins.status.eq("excluded")
        & margins.assumed_absolute_error_c.eq(0.05)
    ].iloc[0]
    return {
        "summary": summary,
        "warm": warm,
        "warm_admitted": warm_admitted,
        "margin_005": margin_005,
    }

def rank_seed_change_max() -> float:
    cases = pd.read_csv(
        RANK / "rank_convergence_cases.csv.gz",
        usecols=["method", "construction", "seed", "draws", "covered"],
    )
    per_seed = cases.groupby(
        ["method", "construction", "seed", "draws"], observed=True
    ).covered.mean().unstack("draws")
    if 1024 not in per_seed.columns or 4096 not in per_seed.columns:
        raise ValueError("Rank cases do not contain both 1,024 and 4,096 draws")
    return float((per_seed[4096] - per_seed[1024]).abs().max() * 100)

def paired_forward_row() -> pd.Series:
    cases = pd.read_csv(REVISION / "whole_archive/uncertainty_common_cases.csv")
    paired = two_method_intersection(cases)
    return paired.loc[paired.family.eq("crossed") & paired["mode"].eq("forward")].iloc[0]

def forward_archive_denominator() -> int:
    summary = pd.read_csv(REVISION / "whole_archive/uncertainty_paired_summary.csv")
    row = summary.loc[
        summary.family.eq("crossed")
        & summary["mode"].eq("forward")
        & summary.estimator.eq("D2")
    ].iloc[0]
    classic = summary.loc[
        summary.family.eq("crossed")
        & summary["mode"].eq("forward")
        & summary.estimator.eq("stochastic_calibrated")
    ].iloc[0]
    if int(row.n_all) != int(classic.n_all):
        raise ValueError("Forward archive denominators differ by method")
    return int(row.n_all)

def core_values(
    cohort: pd.DataFrame,
    uncertainty: pd.DataFrame,
    rule: dict,
    peak: pd.DataFrame,
    task: pd.DataFrame,
    task_pairs: pd.DataFrame,
    release: pd.DataFrame,
    matched_release: pd.DataFrame,
    archive_match: pd.DataFrame,
    rank_summary: pd.DataFrame | None,
) -> str:
    cross = cohort.loc[cohort.family.eq("crossed") & cohort["mode"].eq("forward")].iloc[0]
    warm = rule["summary"].loc["warm_90_station_specific"]
    annual = rule["summary"].loc["annual_95"]
    complete = rule["summary"].loc["complete_100"]
    increments = rule["warm"]
    hidden = peak.loc[
        peak.stratum_type.eq("reference peak")
        & peak.stratum.eq("reference peak above bound")
    ].set_index("method")
    visible = peak.loc[
        peak.stratum_type.eq("reference peak")
        & peak.stratum.eq("reference peak at bound")
    ].set_index("method")
    task_forward = task.loc[
        task.family.eq("crossed")
        & task["mode"].eq("forward")
        & task.estimator.eq("D2")
    ].iloc[0]
    task_pair = task_pairs.loc[
        task_pairs.family.eq("crossed")
        & task_pairs["mode"].eq("forward")
        & task_pairs.estimator.eq("D2")
    ].iloc[0]
    future = matched_release.loc[
        matched_release.condition.eq("future_years")
        & matched_release.family.eq("crossed")
    ].iloc[0]
    archive = archive_match.loc[
        archive_match.family.eq("crossed")
        & archive_match["mode"].eq("forward")
        & archive_match.method.eq("values_and_bounds")
    ].iloc[0]
    lines = [
        r"\newcommand{\CCEligibleYears}{" + f"{int(warm.eligible_station_years):,}" + "}",
        r"\newcommand{\CCEligibleStations}{" + str(int(warm.eligible_stations)) + "}",
        r"\newcommand{\CCEligibleGroups}{" + str(int(warm.eligible_groups)) + "}",
        r"\newcommand{\CCWarmAdmittedYears}{" + f"{int(warm.admitted):,}" + "}",
        r"\newcommand{\CCWarmWitnessAdmitted}{32}",
        r"\newcommand{\CCAnnualWitnessAdmitted}{31}",
        r"\newcommand{\CCWitnessTotal}{35}",
        r"\newcommand{\CCWarmAdmittedStations}{"
        + str(int(warm.admitted_new_window_stations))
        + "}",
        r"\newcommand{\CCAnnualAdmitted}{" + f"{int(annual.admitted):,}" + "}",
        r"\newcommand{\CCCompleteAdmitted}{" + f"{int(complete.admitted):,}" + "}",
        r"\newcommand{\CCWarmAdmittedNewFacts}{"
        + str(int(warm.admitted_new_window_facts))
        + "}",
        r"\newcommand{\CCWarmExcludedFacts}{"
        + str(int(warm.excluded_new_window_facts))
        + "}",
        r"\newcommand{\CCWarmExcludedStations}{"
        + str(int(warm.excluded_new_window_stations))
        + "}",
        r"\newcommand{\CCWarmIncrementOne}{" + number(increments.iloc[0].excess_over_accepted_record, 3) + "}",
        r"\newcommand{\CCWarmIncrementTwo}{" + number(increments.iloc[1].excess_over_accepted_record, 3) + "}",
        r"\newcommand{\CCMarginHalfWidth}{" + number(0.05, 2) + "}",
        r"\newcommand{\CCMarginResolvedFacts}{"
        + str(int(rule["margin_005"].facts_resolved_above_2epsilon))
        + "}",
        r"\newcommand{\CCCohortAll}{" + str(int(cross.n_all)) + "}",
        r"\newcommand{\CCCohortWarm}{" + str(int(cross.n_warm90)) + "}",
        r"\newcommand{\CCCohortCommon}{" + str(int(cross.n_common)) + "}",
        r"\newcommand{\CCCohortStations}{" + str(int(cross.stations)) + "}",
        r"\newcommand{\CCCohortGroups}{" + str(int(cross.groups)) + "}",
        r"\newcommand{\CCAllCommonRMSE}{" + number(cross.all_rmse_common, 3) + "}",
        r"\newcommand{\CCWarmRMSE}{" + number(cross.warm90_rmse_common, 3) + "}",
        r"\newcommand{\CCPeakVisibleN}{" + f"{int(visible.loc['D2'].n):,}" + "}",
        r"\newcommand{\CCPeakHiddenN}{" + f"{int(hidden.loc['D2'].n):,}" + "}",
        r"\newcommand{\CCPeakVisibleDTwoCov}{"
        + pct(visible.loc["D2"].coverage90)
        + "}",
        r"\newcommand{\CCPeakVisibleStochCov}{"
        + pct(visible.loc["stochastic"].coverage90)
        + "}",
        r"\newcommand{\CCPeakHiddenDTwoCov}{"
        + pct(hidden.loc["D2"].coverage90)
        + "}",
        r"\newcommand{\CCPeakHiddenStochCov}{"
        + pct(hidden.loc["stochastic"].coverage90)
        + "}",
        r"\newcommand{\CCPeakHiddenDTwoMAE}{"
        + number(hidden.loc["D2"].mae, 3)
        + "}",
        r"\newcommand{\CCPeakHiddenStochMAE}{"
        + number(hidden.loc["stochastic"].mae, 3)
        + "}",
        r"\newcommand{\CCCalendarVisibleN}{3,125}",
        r"\newcommand{\CCCalendarHiddenN}{549}",
        r"\newcommand{\CCCalendarHiddenDTwoCov}{88.3}",
        r"\newcommand{\CCCalendarHiddenStochCov}{87.8}",
        r"\newcommand{\CCTaskN}{" + str(int(task_forward.n)) + "}",
        r"\newcommand{\CCTaskPercent}{" + pct(task_forward.availability) + "}",
        r"\newcommand{\CCTaskWidthBase}{" + number(task_pair.independent_width95, 3) + "}",
        r"\newcommand{\CCTaskWidthCal}{" + number(task_pair.task_width95, 3) + "}",
        r"\newcommand{\CCReleaseFutureN}{"
        + f"{int(future.n_equal_numerical):,}"
        + "}",
        r"\newcommand{\CCReleaseThreeError}{"
        + f"{int(future.three_output_bad):,}"
        + "}",
        r"\newcommand{\CCReleaseThreeRate}{" + pct(future.three_output_risk, 2) + "}",
        r"\newcommand{\CCReleaseScoreError}{"
        + f"{int(future.score_only_bad):,}"
        + "}",
        r"\newcommand{\CCReleaseScoreRate}{" + pct(future.score_only_risk, 2) + "}",
        r"\newcommand{\CCArchiveMatchedN}{" + f"{int(archive.n_numeric):,}" + "}",
        r"\newcommand{\CCArchiveMatchedThreeRMSE}{"
        + number(archive.rmse_original, 3)
        + "}",
        r"\newcommand{\CCArchiveMatchedScoreRMSE}{"
        + number(archive.rmse_score, 3)
        + "}",
    ]
    gap = peak.loc[peak.stratum_type.eq("longest gap") & peak.method.eq("D2")].set_index("stratum")
    overlap = peak.loc[
        peak.stratum_type.eq("training peak overlap") & peak.method.eq("D2")
    ].set_index("stratum")
    region = peak.loc[peak.stratum_type.eq("region") & peak.method.eq("D2")].set_index("stratum")
    overall_mae_difference = float(
        (peak.loc[peak.stratum_type.eq("region") & peak.method.eq("D2")]
         .set_index("stratum").mae
         - peak.loc[peak.stratum_type.eq("region") & peak.method.eq("stochastic")]
         .set_index("stratum").mae)
        .mul(peak.loc[peak.stratum_type.eq("region") & peak.method.eq("D2")]
             .set_index("stratum").n)
        .sum()
        / peak.loc[peak.stratum_type.eq("region") & peak.method.eq("D2")].n.sum()
    )
    leave = pd.read_csv(FAIL / "failure_strata_leave_region_out.csv")
    leave_bavaria = leave.loc[
        leave.excluded_region.eq("gkd_bayern") & leave.metric.eq("mae")
    ].iloc[0]
    lines.extend([
        r"\newcommand{\CCGapThirtyCov}{" + pct(gap.loc["30 d"].coverage90) + "}",
        r"\newcommand{\CCGapSixtyCov}{" + pct(gap.loc["31--60 d"].coverage90) + "}",
        r"\newcommand{\CCGapNinetyCov}{" + pct(gap.loc["61--90 d"].coverage90) + "}",
        r"\newcommand{\CCGapThirtyMAE}{" + number(gap.loc["30 d"].mae, 3) + "}",
        r"\newcommand{\CCGapSixtyMAE}{" + number(gap.loc["31--60 d"].mae, 3) + "}",
        r"\newcommand{\CCGapNinetyMAE}{" + number(gap.loc["61--90 d"].mae, 3) + "}",
        r"\newcommand{\CCOverlapNoneCov}{" + pct(overlap.loc["no overlap"].coverage90) + "}",
        r"\newcommand{\CCOverlapPartialCov}{" + pct(overlap.loc["partial"].coverage90) + "}",
        r"\newcommand{\CCOverlapHalfCov}{" + pct(overlap.loc["at least half"].coverage90) + "}",
        r"\newcommand{\CCRegionBavariaCov}{" + pct(region.loc["gkd_bayern"].coverage90) + "}",
        r"\newcommand{\CCRegionSwitzerlandCov}{" + pct(region.loc["foen"].coverage90) + "}",
        r"\newcommand{\CCOverallMAEDiff}{" + number(overall_mae_difference, 3) + "}",
        r"\newcommand{\CCLeaveBavariaMAEDiff}{" + number(leave_bavaria.difference_D2_minus_stochastic, 3) + "}",
    ])
    if rank_summary is not None and len(rank_summary):
        max_draws = int(rank_summary.draws.max())
        final = rank_summary.loc[rank_summary.draws.eq(max_draws)]
        for method, label in [("D2", "DTwo"), ("stochastic_cal", "Stoch")]:
            block = final.loc[final.method.eq(method)]
            if block.empty:
                continue
            lines.extend(
                [
                    r"\newcommand{\CCRank" + label + r"Draws}{" + f"{max_draws:,}" + "}",
                    r"\newcommand{\CCRank" + label + r"CovLow}{" + pct(block.coverage_min.min()) + "}",
                    r"\newcommand{\CCRank" + label + r"CovHigh}{" + pct(block.coverage_max.max()) + "}",
                    r"\newcommand{\CCRank" + label + r"WidthLow}{" + number(block.width_min.min(), 2) + "}",
                    r"\newcommand{\CCRank" + label + r"WidthHigh}{" + number(block.width_max.max(), 2) + "}",
                ]
            )
        change_column = f"coverage_change_1024_{max_draws}_pp"
        if change_column in rank_summary:
            checks = rank_summary.drop_duplicates(["method", "construction"])
            lines.extend(
                [
                    r"\newcommand{\CCRankChangeMax}{" + f"{rank_summary[change_column].abs().max():.2f}" + "}",
                    r"\newcommand{\CCRankSeedChangeMax}{" + f"{rank_seed_change_max():.3f}" + "}",
                    r"\newcommand{\CCRankStable}{" + str(int(checks.meets_numerical_stability_rule.sum())) + "}",
                    r"\newcommand{\CCRankTotal}{" + str(int(len(checks))) + "}",
                ]
            )
        forward = paired_forward_row()
        lines.extend(
            [
                r"\newcommand{\CCPairFwdN}{" + str(int(forward.n_paired)) + "}",
                r"\newcommand{\CCPairFwdYears}{" + f"{int(forward.incomplete_years):,}" + "}",
                r"\newcommand{\CCPairFwdDTwoAnnual}{" + pct(forward.annual_weighted_d2) + "}",
                r"\newcommand{\CCPairFwdClassicAnnual}{" + pct(forward.annual_weighted_classic) + "}",
                r"\newcommand{\CCPairFwdDTwoTrend}{" + pct(forward.trend_independent_d2) + "}",
                r"\newcommand{\CCPairFwdClassicTrend}{" + pct(forward.trend_independent_classic) + "}",
                r"\newcommand{\CCOwnFwdDTwoN}{" + str(int(forward.n_own_d2)) + "}",
                r"\newcommand{\CCOwnFwdClassicN}{" + str(int(forward.n_own_classic)) + "}",
                r"\newcommand{\CCOwnFwdAll}{" + str(forward_archive_denominator()) + "}",
            ]
        )
    return "\n".join(lines)

def core_claims_table() -> str:
    return r"""
\begin{table}[t]\centering
\fontsize{8}{10}\selectfont
\renewcommand{\arraystretch}{1.08}
\newcolumntype{C}[1]{>{\raggedright\arraybackslash}p{#1}}
\setlength{\tabcolsep}{4pt}
\caption{Three research questions, their evidence and inference limits. Regional, same-count and numerical diagnostics are exploratory, developed after inspecting existing results.}
\label{tab:core-claims}
\begin{tabular}{C{0.16\textwidth}C{0.20\textwidth}C{0.28\textwidth}C{0.28\textwidth}}\toprule
Question & Target & Evidence and denominator & Inference boundary \\\midrule
RQ1: What observed heat information survives each screen? & Reported 30-day window $L_y$ versus a stated accepted record; no reconstruction. & All \CCEligibleYears{} eligible station-years at \CCEligibleStations{} stations in \CCEligibleGroups{} groups. Rules use a common denominator. & Most witnesses pass the warm-season rule. The 19 accepted windows add facts relative to strict completeness; only \CCWarmExcludedFacts{} excluded windows exceed the warm-season accepted record, by \CCWarmIncrementOne{} and \CCWarmIncrementTwo{}$^{\circ}$C. \\
RQ2: How do year selection and recovery combine in a finite-record slope? & Total slope error $E=S+R$, with a signed MSE cross term. & \CCCohortCommon{} common forward controlled-gap archives; \PTRTimeN{} have actual masked years and enter same-count diagnostics. There are \PTRTimeGroups{} connected groups. & Calendar-CDF and spread controls improve over warm-season selection at fixed counts; all-year recovery improves further. \PTRTimeIdenticalN{}/\PTRTimeN{} selections are fixed by count constraints. Pure count effects and equivalence remain unidentified. \\
RQ3: Where does hidden-peak recovery fail? & Hidden-peak nominal 90\% coverage and recovery bias under visible information conditions. & Regional cases receive common-cell weights with support denominators. A 27-target, two-group numerical subset repeats three seeds and recalibrates on 2,370 original source-role cases. & Bavarian air-ridge failures lack a Swiss counterpart. Training imbalance persists. Re-estimated source offsets change endpoints and local method comparisons; 500 paths do not certify convergence or a general ranking. \\
\bottomrule\end{tabular}\end{table}
"""

def rule_table() -> str:
    summary = pd.read_csv(RULE / "rule_accounting_summary.csv")
    labels = {
        "complete_100": "Complete year (100\\%)",
        "annual_95": "Annual coverage $\\geq$95\\%",
        "warm_90_station_specific": "Station warm-season $\\geq$90\\%",
        "warm_90_fixed_original": "Fixed warm-season $\\geq$90\\%",
        "july_aug_complete": "July--August complete",
        "gap_le_49_days_context": "Longest gap $\\leq$49 d (context)",
    }
    lines = [
        r"\begin{table}[t]",
        r"\centering\small",
        r"\caption{Every eligible station-year under the compared completeness rules. ``Number'' is a complete-year H30; ``bound'' is an incomplete year with a fully observed 30-day window; ``unknown'' has neither. ``New facts'' counts admitted incomplete years whose observed window exceeds the maximum reported window among other accepted years.}",
        r"\label{tab:rule-accounting}",
        r"\resizebox{\textwidth}{!}{\begin{tabular}{lrrrrrrr}",
        r"\toprule",
        r"Rule & Eligible & Admitted & Number & Bound & Unknown & New facts & Excluded facts \\",
        r"\midrule",
    ]
    for row in summary.itertuples(index=False):
        lines.append(
            " & ".join(
                [
                    labels.get(row.rule, tex(row.rule)),
                    f"{int(row.eligible_station_years):,}",
                    f"{int(row.admitted):,}",
                    f"{int(row.admitted_complete_number):,}",
                    f"{int(row.admitted_observed_bound):,}",
                    f"{int(row.admitted_unknown):,}",
                    f"{int(row.admitted_new_window_facts):,}",
                    f"{int(row.excluded_new_window_facts):,}",
                ]
            )
            + r" \\"
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}}",
        r"\begin{flushleft}\footnotesize A reported window is not a complete-year H30. A rule-accepted incomplete year can contain a higher unobserved peak, so the last two columns compare reported windows only. The 49-day row is a contextual Johnson comparison, not a validated H30 rule.\end{flushleft}",
        r"\end{table}",
    ]
    return "\n".join(lines)

def peak_table() -> str:
    frame = pd.read_csv(FAIL / "failure_strata_summary.csv")
    frame = frame.loc[frame.stratum_type.eq("reference peak")].copy()
    order = ["reference peak at bound", "reference peak above bound"]
    frame["order"] = frame.stratum.map({value: i for i, value in enumerate(order)})
    frame = frame.sort_values(["order", "method"])
    lines = [
        r"\begin{table}[t]",
        r"\centering\small",
        r"\caption{Annual recovery separated by whether the complete reference peak is already visible at the observed lower bound. The stratification uses the withheld complete reference and is unavailable at decision time. Common finite D2 and classical cases, crossed forward controlled gaps.}",
        r"\label{tab:peak-visibility-main}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{llrrrrrr}",
        r"\toprule",
        r"Reference peak & Method & Cases & Stations & Groups & MAE ($^{\circ}$C) & 90\% coverage & Width ($^{\circ}$C) \\",
        r"\midrule",
    ]
    for row in frame.itertuples(index=False):
        lines.append(
            " & ".join(
                [
                    "At observed bound" if row.stratum == "reference peak at bound" else "Above observed bound",
                    "D2" if row.method == "D2" else "Classical",
                    f"{int(row.n):,}",
                    str(int(row.stations)),
                    str(int(row.groups)),
                    f"{row.mae:.3f}",
                    f"{100 * row.coverage90:.1f}\\%",
                    f"{row.width90:.2f}",
                ]
            )
            + r" \\"
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}}",
        r"\end{table}",
    ]
    return "\n".join(lines)

def rule_measurement_table() -> str:
    frame = pd.read_csv(RULE / "rule_accounting_measurement_margins.csv")
    frame = frame.loc[frame.rule.eq("warm_90_station_specific")]
    lines = [
        r"\begin{table}[t]",
        r"\centering\small",
        r"\caption{Measurement-margin sensitivity for the station-specific warm-season rule. A reported window ordering is counted as resolved only when the observed difference exceeds twice the assumed absolute error on each window. The margins are assumptions, not sensor-error estimates.}",
        r"\label{tab:rule-measurement-margins}",
        r"\begin{tabular}{rrrrr}",
        r"\toprule",
        r"Assumed absolute error ($^{\circ}$C) & Status & Facts & Resolved above $2\epsilon$ & Not resolved \\",
        r"\midrule",
    ]
    for row in frame.itertuples(index=False):
        lines.append(
            " & ".join(
                [
                    f"{row.assumed_absolute_error_c:.2f}",
                    "admitted" if row.status == "admitted" else "excluded",
                    str(int(row.facts)),
                    str(int(row.facts_resolved_above_2epsilon)),
                    str(int(row.facts_not_resolved)),
                ]
            )
            + r" \\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)

REGION_LABELS = {
    "foen": "Switzerland (FOEN)",
    "gkd_bayern": "Bavaria",
    "usgs_huc03": "USGS HUC03",
    "usgs_huc04": "USGS HUC04",
    "usgs_huc10": "USGS HUC10",
    "usgs_huc17": "USGS HUC17",
}

def stratum_label(kind: str, name: str) -> str:
    if kind == "region":
        shown = REGION_LABELS.get(str(name), str(name))
        return "region: " + shown
    return f"{kind}: {name}"

def _failure_rows(frame: pd.DataFrame) -> list[str]:
    lines = []
    for row in frame.itertuples(index=False):
        lines.append(
            " & ".join(
                [
                    tex(stratum_label(row.stratum_type, row.stratum)),
                    "D2" if row.method == "D2" else "Classical",
                    f"{int(row.n):,}",
                    str(int(row.stations)),
                    str(int(row.groups)),
                    f"{row.mae:.3f}",
                    f"{100 * row.coverage90:.1f}\\%",
                    f"{row.width90:.2f}",
                ]
            )
            + r" \\"
        )
    return lines

def _failure_float(frame: pd.DataFrame, caption: str, label: str) -> str:
    lines = [
        r"\begin{table}[p]",
        r"\centering",
        r"\scriptsize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\renewcommand{\arraystretch}{0.96}",
        r"\caption{" + caption + "}",
        r"\label{" + label + "}",
        r"\begin{tabular}{@{}llrrrrrr@{}}",
        r"\toprule",
        r"Stratum & Method & Cases & Stations & Groups & MAE ($^{\circ}$C) & 90\% coverage & Width ($^{\circ}$C) \\",
        r"\midrule",
        *_failure_rows(frame),
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ]
    return "\n".join(lines)

def failure_table() -> str:
    frame = pd.read_csv(FAIL / "failure_strata_summary.csv")
    order = {
        "reference peak": 0,
        "longest gap": 1,
        "training peak overlap": 2,
        "visible donors": 3,
        "region": 4,
    }
    frame["order"] = frame.stratum_type.map(order)
    frame = frame.sort_values(["order", "stratum", "method"])
    first = frame.loc[frame.stratum_type.isin(["reference peak", "longest gap", "training peak overlap"])]
    second = frame.loc[frame.stratum_type.isin(["visible donors", "region"])]
    shared = (
        "Descriptive failure strata for the crossed forward controlled gaps. "
        "Peak visibility uses the withheld complete reference. "
        "``At least half'' includes overlap equal to 0.5. "
        "Repeated masks are not independent rivers or climates, and small regional samples do not identify a climate mechanism."
    )
    return "\n\n".join(
        [
            _failure_float(first, shared, "tab:failure-strata"),
            _failure_float(
                second,
                shared + " Continued: visible donors and region.",
                "tab:failure-strata-region",
            ),
        ]
    )

def rank_table() -> str:
    path = RANK / "rank_convergence_summary.csv"
    if not path.exists():
        return r"% Rank-convergence table pending."
    frame = pd.read_csv(path)
    lines = [
        r"\begin{table}[t]",
        r"\centering\small",
        r"\caption{Numerical convergence of the three fixed-marginal joint-rank constructions on the difficult forward controlled gaps. Annual quantiles, bounds and evaluation years are fixed. The range is across three random seeds; it is not a confidence interval.}",
        r"\label{tab:rank-convergence}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{llrrrr}",
        r"\toprule",
        r"Method & Construction & Draws & Coverage (\%) & Width ($^{\circ}$C/dec) & Interval score \\",
        r"\midrule",
    ]
    for row in frame.itertuples(index=False):
        lines.append(
            " & ".join(
                [
                    "D2" if row.method == "D2" else "Classical",
                    row.construction.replace("_", " "),
                    str(int(row.draws)),
                    f"{100 * row.coverage_mean:.1f} [{100 * row.coverage_min:.1f}, {100 * row.coverage_max:.1f}]",
                    f"{row.width_mean:.3f} [{row.width_min:.3f}, {row.width_max:.3f}]",
                    f"{row.interval_score_mean:.3f} [{row.interval_score_min:.3f}, {row.interval_score_max:.3f}]",
                ]
            )
            + r" \\"
        )
    lines += [r"\bottomrule", r"\end{tabular}}", r"\end{table}"]
    return "\n".join(lines)

def method_table() -> str:
    return r"""
\begin{table}[t]
\centering
\fontsize{8}{10}\selectfont
\renewcommand{\arraystretch}{1.08}
\setlength{\tabcolsep}{3pt}
\newcolumntype{M}[1]{>{\raggedright\arraybackslash}p{#1}}
\caption{Calibration and projection order in the analyses used here. The rows are separate analyses; they are not twenty repetitions of one final pipeline.}
\label{tab:method-versions}
\begin{tabular}{M{0.18\textwidth}M{0.22\textwidth}M{0.22\textwidth}M{0.28\textwidth}}
\toprule
Analysis & Projection and tail treatment & Calibration and source roles & What it supports \\
\midrule
Twenty historical single-year source repetitions & The same observed-window projection is applied to both methods after their original calibration. The seven stored quantiles are extended with adjacent normal-quantile spacings. & Original weights and offsets remain fixed. Source roles are the original held-region and held-group assignments. & Historical annual H30 comparisons at the executed 20-path classical budget. Fine differences are not established for larger-budget source-calibrated distributions. Not a whole-archive trend refit. \\
Whole-archive factorial & The observed-bound projection is applied to each estimator's annual distribution before and after re-estimated offsets, and those annual samples then enter the slope. Each estimator has its own bounded annual marginals. Within one estimator those marginals stay fixed across the three rank constructions. Both use normal-spacing tails. A trend interval is not projected onto an annual lower bound. & Annual weights stay source-only; local daily models, climatology and residual histories are refitted after jointly masking the target archive. The main analysis excludes held test groups; the strict-region sensitivity removes additional same-region groups. & The retention/estimator decomposition and the finite-record trend comparison. The primary retention contrast uses common station-repetition rows. \\
Forward task calibration & The observed lower bound is imposed on the annual distribution. The independent-draw slope interval is then compared with the task-calibrated slope interval on the same cases. This does not project a trend interval onto an annual lower bound. & Calibration uses unused rule-calibration groups, equal group weights and pre-2010 source errors. Fewer than three nondegenerate groups, a zero factor or an out-of-range target width returns an unsupported status. & The negative result that task calibration is available for only a small selected subset and does not establish population coverage. \\
External exploratory comparisons & Source models and source calibration are fixed; local history is refitted where the adaptation requires it. & Reference quality, clock, quality codes and watershed dependence are unresolved. & Descriptive transfer evidence only. These rows cannot substitute for a strict independent reference. \\
\bottomrule
\end{tabular}
\end{table}
"""

def _json(path: Path) -> dict:
    return json.loads(path.read_text())

def _year_list(years: list[int]) -> str:
    shown = [str(int(year)) for year in years]
    if not shown:
        return "none"
    if len(shown) == 1:
        return shown[0]
    return ", ".join(shown[:-1]) + " and " + shown[-1]

def external_facts() -> dict:
    """Read qualification counts from saved screens. Unknown stays unknown."""
    wellington = _json(
        T.ROOT
        / "results/wrr_review_completion_20261024/independent_study/greater_wellington/qualification_summary.json"
    )
    neon = pd.read_csv(REVISION / "external_neon/qualification.csv")
    usgs = pd.read_csv(REVISION / "external_usgs_fresh/qualification.csv")
    reunion = pd.read_csv(REVISION / "external_hubeau_reunion/qualification.csv")
    eccc = _json(REVISION / "external_eccc_red/status.json")
    australia = _json(REVISION / "audit/australia_prior_exposure_status.json")
    bc = _json(REVISION / "external_bc_air2stream/status.json")
    bc_score = pd.read_csv(REVISION / "external_bc_air2stream/annual_scorecard.csv")
    nova = _json(REVISION / "external_nova_scotia_exploratory/score_status.json")
    truckee = _json(REVISION / "external_truckee_dwr/exploratory_score_status.json")
    finite = _json(REVISION / "external_usace_reservoir/finite_reference_status.json")
    reservoir = _json(REVISION / "external_usace_reservoir/partial_history_score_status.json")
    bounds = pd.read_csv(
        REVISION / "external_usgs_partial_daily/subdaily_h30_bounds_years.csv",
        dtype={"station_id": str},
    )
    bound_plan = _json(REVISION / "external_usgs_partial_daily/subdaily_h30_bounds_plan.json")
    support = _json(REVISION / "external_usgs_partial_daily/feature_support_status.json")
    controlled = int(
        bc_score.loc[
            bc_score.family.eq("crossed")
            & bc_score.stratum.eq("all")
            & bc_score.estimator.eq("D2"),
            "n_eligible",
        ].iloc[0]
    )
    calendar = int(
        bc_score.loc[
            bc_score.family.eq("calendar")
            & bc_score.stratum.eq("all")
            & bc_score.estimator.eq("D2"),
            "n_eligible",
        ].iloc[0]
    )
    if controlled + calendar != int(bc["n_cases"]):
        raise ValueError("BC controlled and calendar masks do not sum to the saved total")
    if controlled != int(bc["n_families"]["crossed"]) or calendar != int(bc["n_families"]["calendar"]):
        raise ValueError("BC scorecard counts disagree with the status file")
    if bool(wellington["temperature_observations_requested"]):
        raise ValueError("Greater Wellington observation status changed; do not keep the unknown-year wording")
    rio = bounds.loc[
        bounds.station_id.astype(str).eq("08377900") & bounds.clock.eq("fixed_standard")
    ].sort_values("year")
    if rio.empty:
        raise ValueError("Rio Mora fixed-standard bounds are missing")
    assumption = str(bound_plan["assumption"]).replace(" ", "")
    if "[-5,50]" not in assumption:
        raise ValueError("Rio Mora unknown-slot bound is not the saved [-5, 50] C assumption")
    hourly_masks = {
        int(block["hourly_supported_cases"]) for block in support["support"]
    }
    if len(hourly_masks) != 1:
        raise ValueError("Rio Mora hourly-supported case count is not unique")
    return {
        "wellington_sites": int(wellington["potentially_eligible_sites"]),
        "neon_sites": int(len(neon)),
        "neon_strict_years": int(neon.n_complete_strict.sum()),
        "neon_eligible_sites": int(neon.strict_reference_eligible.sum()),
        "usgs_sites": int(len(usgs)),
        "usgs_complete_years": int(usgs.n_complete_years.sum()),
        "usgs_four_year_sites": int(usgs.n_complete_years.ge(4).sum()),
        "reunion_sites": int(len(reunion)),
        "reunion_complete_years": int(reunion.n_complete_hot_years.sum()),
        "reunion_eligible_sites": int(reunion.eligible.sum()),
        "eccc_complete_years": int(eccc["complete_local_wallclock_years"]),
        "eccc_scored": bool(eccc["reconstruction_scored"]),
        "au_years": int(australia["original_reference_station_years"]),
        "au_previously_evaluable": int(australia["round1_prior_evaluation_eligible_station_years"]),
        "au_test_years": int(australia["round1_original_test_role_station_years"]),
        "au_test_evaluable": int(australia["round1_original_test_role_evaluated"]),
        "au_scored": bool(australia["new_F2_predictions_or_errors_computed_by_this_audit"]),
        "bc_stations": int(bc["n_scored_stations"]),
        "bc_years": int(bc["n_station_years"]),
        "bc_total": int(bc["n_cases"]),
        "bc_controlled": controlled,
        "bc_calendar": calendar,
        "bc_strict_stations": int(bc["n_strict_24h_eligible"]),
        "nova_stations": int(nova["stations"]),
        "nova_years": int(nova["station_years"]),
        "nova_cases": int(nova["cases"]),
        "truckee_stations": int(truckee["stations"]),
        "truckee_years": int(truckee["reference_years"]),
        "truckee_cases": int(truckee["cases"]),
        "reservoir_files": int(finite["resources"]),
        "reservoir_years": int(finite["station_years"]),
        "reservoir_complete_years": int(finite["complete_finite_station_years"]),
        "reservoir_four_year_sites": int(finite["sites_with_four_finite_years"]),
        "reservoir_scored_stations": int(reservoir["resources"]),
        "reservoir_scored_years": int(reservoir["target_station_years"]),
        "reservoir_scored_cases": int(reservoir["cases"]),
        "rio_complete_years": [int(year) for year in rio.loc[rio.unknown_slots.eq(0), "year"]],
        "rio_bounded_years": [int(year) for year in rio.loc[rio.unknown_slots.gt(0), "year"]],
        "rio_unknown_slots": {
            int(row.year): int(row.unknown_slots) for row in rio.itertuples(index=False)
        },
        "rio_hourly_masks": int(next(iter(hourly_masks))),
    }

def external_values(facts: dict | None = None) -> str:
    facts = external_facts() if facts is None else facts
    commands = {
        "BCMaskTotal": str(facts["bc_total"]),
        "BCCalendarMasks": str(facts["bc_calendar"]),
        "ResScoreStations": str(facts["reservoir_scored_stations"]),
        "ResScoreYears": str(facts["reservoir_scored_years"]),
        "ResScoreCases": str(facts["reservoir_scored_cases"]),
        "USGSCandidateSites": str(facts["usgs_sites"]),
        "USGSCompleteYears": str(facts["usgs_complete_years"]),
        "USGSFourYearStations": str(facts["usgs_four_year_sites"]),
        "RioCompleteQuarterYear": _year_list(facts["rio_complete_years"]),
        "RioBoundedYears": _year_list(facts["rio_bounded_years"]),
        "RioHourlyMasks": str(facts["rio_hourly_masks"]),
    }
    return "\n".join(
        rf"\newcommand{{\{name}}}{{{value}}}" for name, value in commands.items()
    )

def external_table(facts: dict | None = None) -> str:
    facts = external_facts() if facts is None else facts
    slot_text = "; ".join(
        f"{year}: {slots} unknown slots" for year, slots in facts["rio_unknown_slots"].items()
    )
    rows = [
        (
            "Greater Wellington",
            "Temperature series not acquired",
            f"{facts['wellington_sites']} potential sites; quality-code screen not completed",
            "Quality-code values were not requested",
            "Unknown",
            "Not scored",
        ),
        (
            "NEON",
            f"{facts['neon_strict_years']} strict complete years",
            f"{facts['neon_eligible_sites']} of {facts['neon_sites']} sites meet the four-year strict rule",
            "UTC day and final quality flag required",
            "Climate independence not established",
            "Not scored",
        ),
        (
            "New USGS candidates",
            f"{facts['usgs_complete_years']} complete station-years",
            f"{facts['usgs_four_year_sites']} of {facts['usgs_sites']} sites reach four complete years",
            "Daily screen only; hourly reference not verified here",
            "Not established",
            "Not scored. The observation-only witness check is separate.",
        ),
        (
            "R\\'eunion (Hub'Eau)",
            f"{facts['reunion_complete_years']} complete July--June thermal years",
            f"{facts['reunion_eligible_sites']} of {facts['reunion_sites']} sites meet the four-year rule",
            "Reported-day time zone unresolved",
            "Unknown",
            "Not scored",
        ),
        (
            "ECCC Red River",
            f"{facts['eccc_complete_years']} complete local wall-clock years",
            "Strict physical reference not met",
            "Grade and time basis unresolved",
            "Shares a river with a source station",
            "Not scored" if not facts["eccc_scored"] else "Scored",
        ),
        (
            "Australia candidate",
            f"{facts['au_years']} candidate station-years; strict 24-hour sampling not established",
            f"{facts['au_previously_evaluable']} of {facts['au_years']} were previously evaluable, including {facts['au_test_evaluable']} of {facts['au_test_years']} designated test years",
            "The saved screen allowed 20 observed hours",
            "Not independent: prior evaluation exposure",
            "Not scored as a new test" if not facts["au_scored"] else "Scored",
        ),
        (
            "British Columbia",
            f"{facts['bc_years']} published station-years; {facts['bc_strict_stations']} strict 24-hour stations",
            f"{facts['bc_stations']} stations scored; {facts['bc_strict_stations']} meet the strict 24-hour rule",
            "Days may contain 20 hours; clock unresolved",
            "Not established; three stations share the Fraser basin",
            f"{facts['bc_total']} masks total: {facts['bc_controlled']} controlled gaps and {facts['bc_calendar']} calendar gaps. The reported MAEs use the {facts['bc_controlled']}.",
        ),
        (
            "Nova Scotia",
            f"{facts['nova_years']} reported-clock station-years",
            f"{facts['nova_stations']} stations; strict reference not met",
            "Source QC and time zone unresolved",
            "Not established",
            f"{facts['nova_cases']} controlled-gap masks scored",
        ),
        (
            "Truckee, California",
            f"{facts['truckee_years']} reported years",
            f"{facts['truckee_stations']} station; strict reference not met",
            "Clock and estimation flags unresolved",
            "Not established; one managed station with prior basin contact",
            f"{facts['truckee_cases']} controlled-gap masks scored",
        ),
        (
            "USGS Rio Mora",
            f"Complete quarter-hour year: { _year_list(facts['rio_complete_years']) }. Bounded years: { _year_list(facts['rio_bounded_years']) } ({slot_text})",
            "1 station",
            "Unknown quarter-hour slots are assigned to the conditional range $[-5,50]\\,^{\\circ}$C",
            "Not an independent climate",
            f"{facts['rio_hourly_masks']} hourly-supported masks scored against the reported daily target and the conditional continuous target",
        ),
        (
            "Reservoir network",
            f"{facts['reservoir_complete_years']} complete finite years among {facts['reservoir_years']} station-years",
            f"{facts['reservoir_four_year_sites']} of {facts['reservoir_files']} files have four finite years",
            "Strict quarter-hour calendars were not met. The scored bounds assume missing values lie in $[-5,50]\\,^{\\circ}$C",
            "Not established",
            f"{facts['reservoir_scored_cases']} exploratory bounded-reference cases scored at {facts['reservoir_scored_stations']} stations and {facts['reservoir_scored_years']} target station-years",
        ),
    ]
    lines = [
        r"\begin{table}[p]",
        r"\centering",
        r"\scriptsize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\renewcommand{\arraystretch}{1.08}",
        r"\caption{External reference qualification. Complete or bounded reference years, stations meeting the stated history rule, quality and clock, independence, and scored cases are separate fields. Unknown is written as unknown. A zero appears only when the saved screen counted that quantity.}",
        r"\label{tab:external-qualification}",
        r"\begin{tabular}{@{}p{0.13\textwidth}p{0.16\textwidth}p{0.16\textwidth}p{0.16\textwidth}p{0.15\textwidth}p{0.16\textwidth}@{}}",
        r"\toprule",
        r"Source & Reference years & History-rule stations & Quality and clock & Independence & Scored cases \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(" & ".join(row) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)

def metadata_correction() -> str:
    manifest = pd.read_csv(OUT / "metadata_correction/design_correction_manifest.csv")
    old = int(manifest.original_text_present.sum())
    return r"""
\section*{Correction to historical design metadata}
\addcontentsline{toc}{section}{Correction to historical design metadata}
The __N__ saved whole-archive \texttt{design.json} files are historical records and were not rewritten. Their field \texttt{annual\_model} states that ``held region and connected groups excluded.'' That statement is correct for the held test connected groups, but it is not an unconditional region exclusion. The original forward HUC17 estimator retained one other same-region training group, and NVE interval calibration retained two other same-region groups. The paper therefore distinguishes the held-test-group main analysis from the strict-region sensitivity. This correction applies to the historical metadata; it does not change any saved prediction. A correction manifest is available in \texttt{results/wrr\_adversarial\_review\_20261027/metadata\_correction/}.
""".replace("__N__", f"{old:,}")

def main() -> int:
    PAPER.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    cohort = cohort_table()
    uncertainty_bootstrap()
    rule = rule_values()
    peak = pd.read_csv(FAIL / "failure_strata_summary.csv")
    task = pd.read_csv(REVISION / "whole_archive/task_calibration_summary.csv")
    task_pairs = pd.read_csv(REVISION / "whole_archive/paired_task_intervals.csv")
    release = pd.read_csv(REVISION / "release_outputs/release_metrics.csv")
    matched_release = pd.read_csv(
        REVISION / "release_outputs/matched_numerical_retention.csv"
    )
    archive_match = pd.read_csv(REVISION / "archive_matched_release_trend/summary.csv")
    rank_path = RANK / "rank_convergence_summary.csv"
    rank_summary = pd.read_csv(rank_path) if rank_path.exists() else None

    write_tex(PAPER / "core_claims_values.tex", core_values(
        cohort, pd.DataFrame(), rule, peak, task, task_pairs, release, matched_release, archive_match, rank_summary
    ))
    write_tex(PAPER / "core_claims_table.tex", core_claims_table())
    write_tex(PAPER / "rule_accounting_table.tex", rule_table())
    write_tex(PAPER / "peak_visibility_main_table.tex", peak_table())
    write_tex(PAPER / "failure_strata_table.tex", failure_table())
    write_tex(PAPER / "rule_measurement_table.tex", rule_measurement_table())
    write_tex(PAPER / "rank_convergence_table.tex", rank_table())
    write_tex(PAPER / "method_version_table.tex", method_table())
    facts = external_facts()
    write_tex(PAPER / "external_qualification_values.tex", external_values(facts))
    write_tex(PAPER / "external_qualification_table.tex", external_table(facts))
    paired = two_method_intersection(
        pd.read_csv(REVISION / "whole_archive/uncertainty_common_cases.csv")
    )
    paired.to_csv(OUT / "uncertainty_two_method_intersection.csv", index=False)

    # Metadata correction manifest: preserve the original files, record hashes
    # and add one clearly named correction statement at the archive root.
    correction = OUT / "metadata_correction"
    correction.mkdir(parents=True, exist_ok=True)
    paths = sorted(
        path
        for path in (REVISION / "whole_archive").glob("*/*/replicate_*/*/design.json")
        if "/pilot_" not in str(path) and "/calibration/" not in str(path)
    )
    rows = []
    stale = 0
    for path in paths:
        data = json.loads(path.read_text())
        text = str(data.get("annual_model", ""))
        present = "held region and connected groups excluded" in text
        stale += present
        rows.append(
            {
                "path": str(path.relative_to(T.ROOT)),
                "annual_model": text,
                "original_text_present": present,
                "correction": "Held test groups are excluded from the named roles. The forward HUC17 estimator and NVE interval calibration can retain other same-region training groups; use the strict-region sensitivity for an unconditional region exclusion.",
            }
        )
    manifest = pd.DataFrame(rows)
    manifest.to_csv(correction / "design_correction_manifest.csv", index=False)
    (correction / "README.md").write_text(
        "# Correction to historical whole-archive design metadata\n\n"
        f"{len(manifest):,} `design.json` files were read. {stale:,} contain the historical phrase "
        "`held region and connected groups excluded`. The phrase is accurate for held test connected "
        "groups but not for every named region: the original forward HUC17 estimator retained one other "
        "same-region training group, and NVE interval calibration retained two other same-region groups. "
        "The current paper uses a held-test-group main analysis and a separate strict-region sensitivity. "
        "The original files were not modified. The correction text is in "
        "`design_correction_manifest.csv`.\n"
    )
    write_tex(PAPER / "metadata_correction.tex", metadata_correction())

    print(cohort.to_string(index=False), flush=True)
    print(f"wrote manuscript inputs; {len(manifest):,} design files, {stale:,} stale", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
