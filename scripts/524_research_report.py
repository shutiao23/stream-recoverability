#!/usr/bin/env python3
"""Build the five research figures and concise reports from computed results."""

from __future__ import annotations

import json
import os

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.review_figures import plot_aggregate_figures

SOURCE = T.ROOT / "results/wrr_review_completion_20261024"
REVISION = T.ROOT / "results/wrr_review_response_20261027"
OUT = REVISION / "whole_archive"
RELEASE = REVISION / "release_outputs"
PAPER = T.ROOT / "paper/wrr_tr"
FIG = PAPER / "figures/simple_research"
DOC = T.ROOT / "docs"
COLORS = ["#315a7d", "#ca743c", "#48918a", "#97648b"]


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / (name + ".pdf"), bbox_inches="tight")
    fig.savefig(FIG / (name + ".png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


def fmt(value, digits=3):
    return f"{value:.{digits}f}" if pd.notna(value) else "--"


def table(frame, columns, title, label):
    headers = [title for _, title in columns]
    lines = [
        r"\begin{table}[p]\centering\small",
        r"\caption{" + title + r"}\label{" + label + "}",
        r"\begin{tabular}{" + "l" * len(columns) + "}",
        r"\toprule",
        " & ".join(headers) + r"\\\midrule",
    ]
    for _, row in frame.iterrows():
        cells = [
            fmt(row[key])
            if isinstance(row[key], (float, np.floating))
            else str(row[key]).replace("_", r"\_")
            for key, _ in columns
        ]
        lines.append(" & ".join(cells) + r"\\")
    lines += [r"\bottomrule\end{tabular}", r"\end{table}"]
    return "\n".join(lines) + "\n"


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    trend = pd.read_csv(OUT / "trend_summary.csv")
    trend_cases = pd.read_csv(OUT / "trends.csv")
    uncertainty = pd.read_csv(OUT / "uncertainty_paired_summary.csv")
    uncertainty_cases = pd.read_csv(OUT / "uncertainty_common_cases.csv")
    uncertainty_ci_path = OUT / "figure_uncertainty_bootstrap.csv"
    if not uncertainty_ci_path.is_file():
        raise FileNotFoundError(
            "Required group-interval table is missing: " + str(uncertainty_ci_path)
        )
    uncertainty_ci = pd.read_csv(uncertainty_ci_path)
    annual = pd.read_csv(OUT / "annual_summary.csv")
    contrasts = pd.read_csv(OUT / "factorial_contrasts.csv")
    comparisons = pd.read_csv(OUT / "paired_trend_estimators.csv")
    task = pd.read_csv(OUT / "task_calibration_summary.csv")
    task_pairs = pd.read_csv(OUT / "paired_task_intervals.csv")
    error_geometry = pd.read_csv(OUT / "evaluation_error_summary.csv")
    tail_sensitivity = pd.read_csv(OUT / "quantile_tail_summary.csv")
    support_projection = pd.read_csv(OUT / "support_projection_summary.csv")
    projection_stages = pd.read_csv(OUT / "projection_stage_summary.csv")
    peak_visibility = pd.read_csv(OUT / "peak_visibility_annual.csv")
    annual_expansion = pd.read_csv(REVISION / "annual_interval_expansion/paired_summary.csv")
    uncertainty_paired = pd.read_csv(OUT / "uncertainty_paired_summary.csv")
    uncertainty_contrasts = pd.read_csv(OUT / "uncertainty_paired_contrasts.csv")
    sources = pd.read_csv(OUT / "task_calibration_sources.csv")
    releases = pd.read_csv(RELEASE / "release_metrics.csv")
    states = pd.read_csv(RELEASE / "output_states.csv")
    matched_release = pd.read_csv(RELEASE / "matched_numerical_retention.csv")
    source_release = pd.read_csv(RELEASE / "source_calibrated_release_summary.csv")
    source_release_bootstrap = pd.read_csv(RELEASE / "source_calibrated_group_bootstrap.csv")
    release_regions = pd.read_csv(RELEASE / "source_release_by_region.csv")
    release_group = pd.read_csv(RELEASE / "source_release_equal_group.csv")
    release_region_directions = pd.read_csv(RELEASE / "source_release_region_directions.csv")
    release_leaveout = pd.read_csv(RELEASE / "source_release_leave_one_region_out.csv")
    events = pd.read_csv(RELEASE / "hot_event_metrics.csv")
    status = json.loads((OUT / "status.json").read_text())
    observed_reaudit = json.loads((REVISION / "audit/observed_record_independent_reaudit.json").read_text())
    input_precision = json.loads((REVISION / "audit/input_panel_precision_audit.json").read_text())
    screening_reaudit = json.loads((REVISION / "audit/screening_rule_reaudit.json").read_text())
    usgs_reaudit = json.loads((REVISION / "audit/usgs_observed_independent_reaudit.json").read_text())
    nz = json.loads(
        (SOURCE / "independent_study/observed_qualification.json").read_text()
    )
    additional_path = T.ROOT / "results/additional_usgs_observed"
    additional = json.loads((additional_path / "status.json").read_text())
    additional_witness = pd.read_csv(
        additional_path / "robust_record_witnesses.csv", dtype={"station_id": str}
    )
    witness = pd.read_csv(SOURCE / "observed_records/observed_record_certificates.csv")
    score = pd.read_csv(REVISION / "annual/source_scorecard_summary.csv")
    paired_source = pd.read_csv(REVISION / "annual/source_paired.csv")
    rule_summary = pd.read_csv(REVISION / "rules/rule_summary.csv")
    neon = json.loads((REVISION / "external_neon/status.json").read_text())
    fresh_usgs = json.loads((REVISION / "external_usgs_fresh/status.json").read_text())
    reunion = json.loads((REVISION / "external_hubeau_reunion/status.json").read_text())
    attempted_usgs = json.loads((REVISION / "external_usgs/status.json").read_text())
    count_screen = json.loads((REVISION / "external_usgs_count_screen/preflight_status.json").read_text())
    nve_metadata = json.loads((REVISION / "external_nve_seriekart_metadata/status.json").read_text())
    nve_chart = json.loads((REVISION / "external_nve_seriekart_metadata/chart_status.json").read_text())
    eccc_red = json.loads((REVISION / "external_eccc_red/report.json").read_text())
    bc = json.loads((REVISION / "external_bc_air2stream/status.json").read_text())
    bc_scores = pd.read_csv(REVISION / "external_bc_air2stream/annual_scorecard.csv")
    bc_site = pd.read_csv(REVISION / "external_bc_air2stream/site_scorecard.csv")
    bc_integrity = json.loads((REVISION / "external_bc_air2stream/reference_integrity.json").read_text())
    bc_hidden = json.loads((REVISION / "external_bc_air2stream/hidden_value_audit.json").read_text())
    nechako_reference = json.loads((REVISION / "external_nechako_nhg/report.json").read_text())
    nechako_years = pd.read_csv(REVISION / "external_nechako_nhg/qualification_years.csv")
    poudre_reference = json.loads((REVISION / "external_csu_ross/report.json").read_text())
    poudre_years = pd.read_csv(REVISION / "external_csu_ross/qualification_years.csv")
    nova_reference = json.loads((REVISION / "external_nova_scotia_verified/report.json").read_text())
    nova_sites = pd.read_csv(REVISION / "external_nova_scotia_verified/common_complete_label_site_summary.csv")
    nova_exploratory = json.loads((REVISION / "external_nova_scotia_exploratory/report.json").read_text())
    nova_exploratory_pairs = pd.read_csv(REVISION / "external_nova_scotia_exploratory/paired_summary.csv")
    nova_exploratory_detail = pd.read_csv(REVISION / "external_nova_scotia_exploratory/paired_posthoc_diagnostics.csv")
    nova_clock = json.loads((REVISION / "external_nova_scotia_clock_sensitivity/report.json").read_text())
    nova_clock_pairs = pd.read_csv(REVISION / "external_nova_scotia_clock_sensitivity/paired_summary.csv")
    regional_sensitivity = pd.read_csv(REVISION / "robustness/leave_one_region_out.csv")
    group_sensitivity = pd.read_csv(REVISION / "robustness/paired_cluster_bootstrap.csv")
    scenarios = pd.read_csv(REVISION / "scenarios/paired_summary.csv")
    integrated = pd.read_csv(REVISION / "integrated_release_trend/summary.csv")
    integrated_pairs = pd.read_csv(REVISION / "integrated_release_trend/paired_baselines.csv")
    quality_sensitivity = pd.read_csv(REVISION / "integrated_release_trend/withhold_unassessed_summary.csv")
    complete_contrasts = contrasts.dropna(
        subset=["symmetric_retention", "symmetric_estimator", "total_gain"]
    )
    factor = (
        complete_contrasts.groupby(["family", "mode", "estimator"])
        .agg(
            n_paired=("total_gain", "size"),
            retention=("symmetric_retention", "mean"),
            estimator_gain=("symmetric_estimator", "mean"),
            total_gain=("total_gain", "mean"),
            interaction=("interaction", "mean"),
        )
        .reset_index()
    )
    factor["retention_fraction"] = factor.retention / factor.total_gain
    factor.to_csv(OUT / "factorial_paired_summary.csv", index=False)
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

    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.0))
    for i, (provider, block) in enumerate(witness.groupby("provider")):
        axes[0].scatter(
            block.incomplete_year,
            block.record_excess_lower_bound,
            color=COLORS[i % 4],
            label=provider,
            s=28,
            alpha=0.8,
        )
    axes[0].scatter(
        additional_witness.year,
        additional_witness.excess,
        marker="x",
        color=COLORS[3],
        label="Additional records",
        s=40,
    )
    axes[0].axhline(0.5, color="0.5", ls="--", lw=1)
    axes[0].set(
        xlabel="Incomplete year",
        ylabel="Excess over record (C)",
        title="Record omission",
    )
    axes[0].legend(frameon=False, fontsize=8.5)
    excess = (
        witness.groupby("station_key").record_excess_lower_bound.max().sort_values()
    )
    axes[1].barh(np.arange(len(excess)), excess, color=COLORS[0])
    axes[1].set(
        xlabel="Largest excess (C)",
        ylabel="Stations",
        title=f"{witness.station_key.nunique()} stations, {len(witness)} years",
        yticks=[],
    )
    save(fig, "01_observed_records")

    plot_aggregate_figures(
        score,
        trend,
        factor,
        annual,
        states,
        releases,
        save,
        trend_cases=trend_cases,
        uncertainty=uncertainty,
        uncertainty_ci=uncertainty_ci,
        uncertainty_cases=uncertainty_cases,
    )
    if os.environ.get("FIGURES_ONLY"):
        return

    # Explain four dependence directions without presenting toy errors as field evidence.
    years = np.arange(1990, 2020)
    x = (years - years.mean()) / 10
    weights = x / (x @ x)
    structures = {
        "constant_bias": np.ones(30),
        "smooth_drift": np.linspace(-1, 1, 30),
        "step_change": np.r_[-np.ones(15), np.ones(15)],
        "isolated_hot_year": np.r_[np.zeros(29), 1.0],
    }
    rows = [
        {
            "structure": name,
            "joint_slope_sd": 0.5 * abs(weights @ shape),
            "independent_same_marginal_sd": 0.5 * np.sqrt(np.sum((weights * shape) ** 2)),
        }
        for name, shape in structures.items()
    ]
    pd.DataFrame(rows).to_csv(OUT / "error_structure_sensitivity.csv", index=False)

    def result(family, mode, estimator="D2", dependence="independent", retention="all"):
        return trend.loc[
            trend.family.eq(family)
            & trend["mode"].eq(mode)
            & trend.estimator.eq(estimator)
            & trend.dependence.eq(dependence)
            & trend.retention.eq(retention)
        ].iloc[0]

    off = result("crossed", "offline")
    forward = result("crossed", "forward")
    block = result("crossed", "forward", dependence="residual_blocks")
    retained = factor.loc[
        factor.family.eq("crossed")
        & factor["mode"].eq("offline")
        & factor.estimator.eq("D2")
    ].iloc[0]
    danger = score.loc[score.family.eq("crossed") & score.stratum.eq("danger")].set_index("estimator")
    paired_danger = paired_source.loc[paired_source.family.eq("crossed") & paired_source.stratum.eq("danger")]
    warm_rule = rule_summary.loc[rule_summary.rule.eq("warm_90_station_specific")].iloc[0]
    task_forward = task.loc[task.family.eq("crossed") & task["mode"].eq("forward") & task.estimator.eq("D2")].iloc[0]
    scenario_d2 = scenarios.loc[scenarios.family.eq("crossed") & scenarios.estimator.eq("D2") & scenarios.retention.eq("all") & scenarios.dependence.eq("independent")]
    donor_forward = scenario_d2.loc[scenario_d2.scenario.eq("synchronized_donors") & scenario_d2["mode"].eq("forward")].iloc[0]
    heat_offline = scenario_d2.loc[scenario_d2.scenario.eq("heat_associated") & scenario_d2["mode"].eq("offline")].iloc[0]
    integrated_forward = integrated.loc[integrated.family.eq("crossed") & integrated["mode"].eq("forward") & integrated.method.eq("released_values_and_bounds")].iloc[0]
    integrated_forward_pair = integrated_pairs.loc[integrated_pairs.family.eq("crossed") & integrated_pairs["mode"].eq("forward") & integrated_pairs.release_method.eq("released_values_and_bounds") & integrated_pairs.baseline.eq("all")].iloc[0]
    quality_offline = quality_sensitivity.loc[quality_sensitivity.family.eq("crossed") & quality_sensitivity["mode"].eq("offline") & quality_sensitivity.method.eq("released_values_and_bounds")].iloc[0]
    claims = [
        r"\newcommand{\WAStations}{" + str(status["n_stations"]) + "}",
        r"\newcommand{\WARepetitions}{"
        + f"{status['completed_station_repetitions']:,}"
        + "}",
        r"\newcommand{\WAOfflineCoverage}{"
        + f"{100 * off.missing_coverage95:.1f}"
        + "}",
        r"\newcommand{\WAForwardCoverage}{"
        + f"{100 * forward.missing_coverage95:.1f}"
        + "}",
        r"\newcommand{\WABlockForwardCoverage}{"
        + f"{100 * block.missing_coverage95:.1f}"
        + "}",
        r"\newcommand{\WARetentionShare}{"
        + f"{100 * retained.retention_fraction:.1f}"
        + "}",
        r"\newcommand{\WADTwoMAE}{" + f"{danger.loc['distribution_regression', 'mae_median']:.3f}" + "}",
        r"\newcommand{\WAStochasticMAE}{" + f"{danger.loc['stochastic_regression_calibrated', 'mae_median']:.3f}" + "}",
        r"\newcommand{\WADTwoCoverage}{" + f"{100*danger.loc['distribution_regression', 'coverage90_median']:.1f}" + "}",
        r"\newcommand{\WAStochasticCoverage}{" + f"{100*danger.loc['stochastic_regression_calibrated', 'coverage90_median']:.1f}" + "}",
        r"\newcommand{\WADTwoCRPS}{" + f"{danger.loc['distribution_regression', 'crps_median']:.3f}" + "}",
        r"\newcommand{\WAStochasticCRPS}{" + f"{danger.loc['stochastic_regression_calibrated', 'crps_median']:.3f}" + "}",
        r"\newcommand{\WADTwoCRPSWins}{" + str(int((paired_danger.D2_crps < paired_danger.stochastic_crps).sum())) + "}",
        r"\newcommand{\WADTwoTailWins}{" + str(int((paired_danger.D2_twcrps < paired_danger.stochastic_twcrps).sum())) + "}",
        r"\newcommand{\WAWarmAdmitted}{" + str(int(warm_rule.admitted_witness_years)) + "}",
        r"\newcommand{\WAWarmExcludedExceed}{" + str(int(warm_rule.excluded_exceed_reported_record)) + "}",
        r"\newcommand{\WATaskForwardN}{" + str(int(task_forward.n)) + "}",
        r"\newcommand{\WATaskForwardPercent}{" + f"{100*task_forward.availability:.1f}" + "}",
        r"\newcommand{\WADonorBase}{" + f"{donor_forward.baseline_rmse:.3f}" + "}",
        r"\newcommand{\WADonorStress}{" + f"{donor_forward.stress_rmse:.3f}" + "}",
        r"\newcommand{\WAHeatBase}{" + f"{heat_offline.baseline_rmse:.3f}" + "}",
        r"\newcommand{\WAHeatStress}{" + f"{heat_offline.stress_rmse:.3f}" + "}",
        r"\newcommand{\WASelectedRMSE}{" + f"{integrated_forward.rmse:.3f}" + "}",
        r"\newcommand{\WASelectedBaseRMSE}{" + f"{integrated_forward_pair.baseline_rmse:.3f}" + "}",
        r"\newcommand{\WASelectedCoverage}{" + f"{100*integrated_forward.total_working_coverage95:.1f}" + "}",
        r"\newcommand{\WASelectedWidth}{" + f"{integrated_forward.total_working_width95:.2f}" + "}",
        r"\newcommand{\WAQualityUnassessed}{" + str(int(quality_offline.n_unassessed_years)) + "}",
        r"\newcommand{\WAQualityStrictRMSE}{" + f"{quality_offline.strict_rmse:.3f}" + "}",
    ]
    claims += [
        r"\newcommand{\WAAdditionalStations}{"
        + str(additional["n_witness_stations"])
        + "}",
        r"\newcommand{\WAAdditionalYears}{"
        + str(additional["n_witness_station_years"])
        + "}",
    ]
    (PAPER / "simple_research_claims.tex").write_text("\n".join(claims) + "\n")
    methods = r"""\subsection{Whole-archive degradation, common cohorts and task-level uncertainty}
The whole-archive benchmark jointly masks selected gaps in several years of a target station before fitting its daily models, climatology or residual histories. Unmasked target observations and neighboring physical stations remain available in this experiment. The benchmark contains 42 stations with at least twenty complete reference years in seven regions. One Finnish record ends in 1994, leaving 41 stations for forward evaluation. Twenty paired mask repetitions use both empirical calendars and controlled 30--90-day gaps; after seven observed burn-in years, each reference year is degraded with probability 0.35. These 3,320 archive experiments do not reuse any masked target day when fitting another year. The complete reference, including those hidden days, is used for scoring; its unmasked values can also enter local fitting. The archived single-year plug-in is retained as an optimistic-information paired comparator on identical masks.

Offline daily fits use the remaining visible history. Forward annual models and interval offsets use source observations before 2010 and exclude the evaluated test stations and their connected groups. The original partitioned role assignment can retain other training-only groups in the same named region: this occurs in the HUC17 estimator and in NVE interval calibration. Accordingly this forward experiment is held-test-group, not uniformly held-region, and is applied to 2010 onward. The strict-region sensitivity removes the additional same-region groups and is reported separately. Forward local daily fitting and dependence estimation also exclude water observations from 2010 onward. These are current-vintage retrospective forward experiments, not a historical real-time field trial. Annual regression weights remain source-only and use source-fit seed zero throughout. Source observations do not change across archive masks, so those fits are reused; every local stage that uses the degraded target archive is refitted. Twenty archive masks are not twenty new global model fits.

On each degraded archive, the retention set (90\% warm-season rule or all supported years) is crossed with the annual estimator (daily plug-in, equally calibrated stochastic regression or D2). Every slope is scored against the same complete-record slope. For the four MSE cells $A$ (rule/plug-in), $B$ (all/plug-in), $C$ (rule/alternative) and $D$ (all/alternative), the symmetric retention contribution is $\{(A-B)+(C-D)\}/2$, and the estimator contribution is $\{(A-C)+(B-D)\}/2$. They sum to $A-D$; the interaction is $(A-B)-(C-D)$. Complete paired cells, rather than different available subsets, determine each decomposition. The retention figure uses common station-repetition rows: in the forward controlled-gap setting, both retention sets are available for 807 of 820 settings, and the all-year RMSE is recomputed on those 807 rows.

\subsection{Specification of the executed estimators}
Daily completion uses one recorded reconstructor per case: donor ridge, air ridge, linear interpolation, smooth climatology, or day-of-year climatology. Air2stream-3 and the value computed from observed days are additional comparators. A reconstructor may use days that remain visible in the target year, the station's other visible years, and eligible neighboring stations. Days hidden by that year's target mask are not used to fit the local model. In the forward experiment, local daily fitting also excludes the target station's water observations from 2010 onward.

D2 learns the annual H30 error relative to the plug-in, not the annual value itself. Seven LightGBM quantile regressions use the quantile objective at levels 0.05, 0.10, 0.25, 0.50, 0.75, 0.90 and 0.95. The fixed settings, which were not re-tuned for this revision, are 300 trees, learning rate 0.05, 31 leaves, at least 50 cases per leaf, 80\% row and column subsampling, and an L2 penalty of 1. Features are available at decision time: gap length and runs, warm-season and peak overlap, donor count and correlation, historical reconstruction error, the visible edge anomaly, air anomalies, differences among the other reconstructors relative to the plug-in, and summaries of the stochastic and air-state simulation distributions when those summaries exist. A missing simulation feature stays missing and uses the tree's missing-value branch. Predicted quantiles are sorted to remove crossings. The published annual point is the calibrated 0.50 quantile.

The historical calibrated stochastic comparator stores 20 residual-bridge trajectories as a fixed computational budget. The same-target experiment reported below regenerates the original source-calibration cases at larger budgets and updates their offsets; it does not rerun the full whole-archive trend comparison. Fine method rankings are not asserted beyond the tested numerical subset. The bridge is a Gaussian AR(1) on a residual history with at least 30 finite days. Its lag coefficient is clipped to $[-0.95,0.995]$. When an observed water value exists at the left or right end of a gap, the trajectory is conditioned on that boundary; otherwise the left state is drawn from the residual margin. The same seven probability levels are read from those 20 trajectories. Where a stored bridge-repair table applies, it replaces the stochastic columns. It does not refit the daily bridge.

Both annual distributions use four disjoint connected-group roles, with shares 0.55, 0.15, 0.15 and 0.15: estimator fitting, interval calibration, score learning and rule calibration. Groups are shuffled within the source seed and bootstrapped only inside their own role. Each role must contain at least two groups. Interval offsets are empirical quantiles of the calibration-role errors, computed separately by peak-overlap bin and reconstructor. A stratum with fewer than 50 positive-weight calibration cases falls back to all calibration-role cases. Levels at or above 0.50 use the higher empirical quantile, and lower levels use the lower one. Offsets are added and the seven levels are sorted again.

Sampling then follows one order. A finite observed-window lower bound is applied to the annual quantiles. Stratified probabilities are interpolated between the seven stored levels. Outside 0.05 and 0.95, the default extends the quantile function by the adjacent normal-quantile spacing; holding the endpoint fixed is retained only as a paired sensitivity. These seven levels do not identify a complete central 90\% distribution: values between them are interpolations, and both outer tails are extrapolations. Samples are then projected onto the same lower bound. Independent ranks, auxiliary Ridge year-bootstrap states, or three-year residual blocks reorder the samples without changing each year's marginal. The ordinary-least-squares slope and its interval are computed from that joint sample. Task-level calibration is a later, separate step.

We refit both methods' annual quantile offsets on their original disjoint source calibration groups after imposing the observed-window lower bound. Both distributions and their samples respect the bound when one is available. Seven stored quantiles constrain only those seven probability levels; they do not identify the distribution between or outside them. We extrapolate both outer tails using the adjacent normal-quantile spacing and project the annual samples onto the bound; the endpoint-constant alternative is retained on paired cases. The normal extrapolation is an assumption, not a validated tail law. That projection is applied to the annual distribution and then carried into the slope. It does not project a trend interval onto an annual lower bound. The main analysis uses 256 stratified samples per year. Within one estimator, independent ranks, auxiliary shared year-bootstrap regression states and three-year residual blocks keep that estimator's annual marginals fixed. The two estimators do not share one annual distribution. Shared states come from a small harmonic/air Ridge model, not the D2 tree posterior or the selected donor model. These couplings are dependence sensitivities, not posterior samples or coverage theorems.

The joint-rank numerical sensitivity fixes the annual quantiles, observed bounds and evaluation years and increases the stratified sample count through 256, 1,024 and 4,096 on the difficult forward controlled gaps. Three random seeds index the rank construction. The rank sequence is generated at 4,096 draws and truncated for smaller counts; annual marginals are regenerated separately for each sample size. We report coverage, width, interval score, the three-seed mean and the largest single-seed change. A 0.3-point rule on the three-seed mean is only a diagnostic: averaging seeds can cancel opposing changes, and meeting it does not justify ranking small construction differences. The check uses the same opened data and is not an independent validation.

Table~\ref{tab:method-versions} separates the calibration and projection order of the historical, whole-archive, task-calibration and external analyses. The task-level comparator calibrates absolute slope error divided by an independent-draw interval half-width. Every source connected group receives equal total weight in the empirical 95th percentile. Calibration uses only unused rule-calibration groups, re-predicted with the held-region model; forward errors end before 2010. We withhold the calibration when fewer than three nondegenerate source groups remain, the calibration factor is effectively zero, or the target half-width lies outside the source 1st--99th percentile range. These thresholds are empirical support checks rather than a finite-sample guarantee. Source support, availability and matched-case width, coverage and interval score are reported. All uncertainty scores target the finite complete-record slope, not climate-trend uncertainty.

The historical design metadata are not rewritten. The saved 3,320 \texttt{design.json} files state that held region and connected groups were excluded; that is correct for held test groups but not an unconditional region exclusion. The forward HUC17 estimator retained one other same-region training group, and NVE interval calibration retained two. The paper uses the held-test-group analysis as primary and the strict-region sensitivity as a separate check. A correction manifest accompanies the historical files.
"""
    (PAPER / "simple_research_methods.tex").write_text(methods)
    results = r"""\subsection{Retention, estimator and the common cohort}
The whole-archive benchmark comprises \WARepetitions{} station/repetition/setting evaluations at \WAStations{} long-record stations in 18 connected groups. Figure~\ref{fig:whole-archive} and Table~\ref{tab:whole-archive-paired} use common station/repetition rows. For the forward controlled-gap retention contrast, both retention sets are available in \CCCohortCommon{} of \CCCohortAll{} settings; the all-year D2 RMSE on those \CCCohortCommon{} rows is \CCAllCommonRMSE{} $^{\circ}$C per decade, compared with \CCWarmRMSE{} under the warm-season rule. The 820-row all-year value is not used for this paired contrast. Retaining years improves the finite-record slope comparison in the evaluated settings. The executed fixed-budget D2 and classical comparisons vary with time setting and region; small differences do not establish a ranking for more fully sampled source-calibrated annual distributions. Results are conditional on donor availability and mask design. Twenty masks at one station are not twenty independent rivers or climates.

The four-cell factorial comparison gives an arithmetic retention contrast. It is not an orthogonal year-set/reconstruction error decomposition or an identified year-count effect. For offline controlled gaps, the symmetric retention contrast is \WARetentionShare\% of the D2-versus-rule/plug-in MSE gain. This is a result for this experiment, not a universal percentage. Estimator effects and interactions are retained in the full paired table.

The peak-visibility stratification separates cases where the complete reference peak is already visible at the observed lower bound from cases where it is not (Table~\ref{tab:peak-visibility-main}). In the forward empirical-calendar common cases, \CCCalendarVisibleN{} of 3,674 reference peaks are already at the bound and \CCCalendarHiddenN{} are above it; hidden-peak coverage is \CCCalendarHiddenDTwoCov\% for D2 and \CCCalendarHiddenStochCov\% for the classical method (Supporting Information). The controlled-gap stratum is harder. In the forward controlled gaps, \CCPeakVisibleN{} common cases have the reference peak at the bound and \CCPeakHiddenN{} have a higher reference peak. D2 nominal 90\% coverage is \CCPeakVisibleDTwoCov\% and \CCPeakVisibleStochCov\% in the visible stratum, but \CCPeakHiddenDTwoCov\% and \CCPeakHiddenStochCov\% in the hidden stratum. Hidden-stratum MAE is \CCPeakHiddenDTwoMAE{} and \CCPeakHiddenStochMAE{} $^{\circ}$C. Longer gaps, partial training-peak overlap and region change these values: D2 coverage falls from \CCGapThirtyCov\% at 30-day gaps to \CCGapSixtyCov\% at 31--60 days and \CCGapNinetyCov\% at 61--90 days, and from \CCOverlapNoneCov\% with no training-peak overlap to \CCOverlapPartialCov\% with partial overlap. Bavaria has \CCRegionBavariaCov\% coverage versus \CCRegionSwitzerlandCov\% for the Swiss FOEN stations. Removing Bavaria changes the D2-minus-classical MAE difference from \CCOverallMAEDiff{} to \CCLeaveBavariaMAEDiff{} $^{\circ}$C. These strata are descriptive; the hidden-peak stratum uses the withheld reference and cannot become a deployment filter.

Annual marginals and trend uncertainty give different answers (Figure~\ref{fig:joint-uncertainty}). The left panel is a paired comparison on the two-method intersection, weighted by incomplete years. For forward controlled gaps that intersection has \CCPairFwdN{} archives and \CCPairFwdYears{} missing-year cases; annual coverage is \CCPairFwdDTwoAnnual\% for D2 and \CCPairFwdClassicAnnual\% for the classical method. D2 is also available on \CCOwnFwdDTwoN{} of \CCOwnFwdAll{} archives and the classical method on \CCOwnFwdClassicN{}; those availability counts are not the paired denominator. The right panel keeps each method on its own available archives, so the printed sample sizes differ and the panel is not a paired comparison. On D2's own forward set, nominal 95\% independent-rank trend coverage is \WAForwardCoverage\% and residual blocks give \WABlockForwardCoverage\%. On the intersection, independent-rank trend coverage is \CCPairFwdDTwoTrend\% for D2 and \CCPairFwdClassicTrend\% for the classical method. The dashed lines are the nominal 90\% annual target on the left and the nominal 95\% trend target on the right. Within one estimator, the three rank constructions keep that estimator's annual marginals fixed; the two estimators do not share one annual distribution. The joint-rank numerical check increases the samples through 256, 1,024 and \CCRankDTwoDraws{} (Table~\ref{tab:rank-convergence}). At \CCRankDTwoDraws{} samples, nominal 95\% trend coverage is \CCRankStochCovLow\%--\CCRankDTwoCovHigh\% across methods, constructions and seeds, so the undercoverage remains. The largest change in the three-seed mean coverage is \CCRankChangeMax{} percentage points, and the largest single-seed change is \CCRankSeedChangeMax{} percentage points. \CCRankStable{} of \CCRankTotal{} method--construction pairs meet a 0.3-point rule on the three-seed mean. That mean can cancel opposing seed changes, so it is not a resolution guarantee and the constructions are not ranked. The experiment does not uniquely attribute the residual undercoverage to annual miscalibration, tail extrapolation or dependence.

Task calibration is available for \WATaskForwardN{} of 820 forward controlled-gap D2 cases (\WATaskForwardPercent\%), representing two stations and two groups. Both task calibration and the independent-draw comparator cover all of these same cases, but the task-calibrated average width is \CCTaskWidthCal{} $^{\circ}$C per decade versus \CCTaskWidthBase{} for the independent interval. This selected-subset result does not demonstrate general improvement. Withholding and regional support remain explicit.

The three-output release comparison also does not establish a general safety gain. Matching the numerical output count on future long gaps gives \CCReleaseFutureN{} values per rule; the three-output rule produces \CCReleaseThreeError{} errors (\CCReleaseThreeRate\%) and simple score ranking produces \CCReleaseScoreError{} (\CCReleaseScoreRate\%). Matching within the \CCArchiveMatchedN{} forward controlled-gap archives gives trend RMSE \CCArchiveMatchedThreeRMSE{} versus \CCArchiveMatchedScoreRMSE{} $^{\circ}$C per decade, and the connected-group interval for the paired squared-error difference spans zero. The published-values-plus-bounds working likelihood treats released values as exact and covers 99.8\% with a 3.26 $^{\circ}$C per decade width; it is not a calibrated missingness-only interval. These are boundary results, not a deployment recommendation.
"""
    (PAPER / "simple_research_results.tex").write_text(results)
    external_text = r"""\subsection{Additional observation-only corroboration}
We obtained approved daily-mean USGS temperature records at ten additional metadata-selected stream stations. None was a source-model target. Seven candidates lie in HUC2 regions 13 or 20, absent from the source station regions; three are additional station checks within already represented HUC2 regions. The candidates and all qualification failures are retained. This unregistered intake was not a random sample or a blinded confirmation, and the reference histories are shorter and sparser than the original long-record panel.

The unchanged four-complete-year reconstruction criterion yields zero eligible numerical-recovery references. The observation-only claim needs a different comparison: an incomplete year can contradict the maximum of the complete-year record whenever at least one approved-complete reference year exists. We retain every approved finite reference value, including reference years that an extra heuristic-QC filter might remove. Candidate windows must contain thirty consecutive approved, nonestimated daily values after source QC, and the incomplete year must have an actual absent, null, contradictory or unapproved provider day. Heuristic censoring alone cannot create a witness.

There are four stations with a nonempty approved-complete reference, each with only one to three reference years. At \WAAdditionalStations{} of these stations, \WAAdditionalYears{} incomplete station-years contain verified windows exceeding every approved-complete H30 in the analyzed record (Figure~2 of the main article). For example, the Rio Mora 2020 window exceeds the complete-only record by approximately 0.883$^{\circ}$C, and a Pecos River 2020 window by 0.643$^{\circ}$C. These facts corroborate record omission without fitting any imputer. They do not estimate an omission incidence, verify a unique warmest year, establish external reconstruction accuracy, or validate trend or risk guarantees. Every witness includes the thirty original approved values; agency reporting and measurement validity remain assumptions.
"""
    (PAPER / "simple_external_results.tex").write_text(external_text)
    observed = (
        "01_observed_records",
        "fig:observed-records",
        "Fully observed thirty-day windows in incomplete years exceed complete-only station records. Crosses on the left are additional approved-record witnesses with sparse one-to-three-year complete reference support; they are not included in the original long-record denominator or the source-station bars on the right. The evidence concerns reported measurements and requires no reconstruction.",
    )
    (PAPER / "figure_observed_records.tex").write_text(
        r"\begin{figure}[t]\centering\includegraphics[width=\textwidth]{figures/simple_research/"
        + observed[0]
        + r".pdf}\caption{"
        + observed[2]
        + r"}\label{"
        + observed[1]
        + r"}\end{figure}" + "\n"
    )
    figures = [
        (
            "02_annual_comparators",
            "fig:estimators",
            "Annual estimation under difficult controlled gaps. Both historical source-calibrated methods receive the same observed-bound projection and normal-spacing tail model. Bars show empirical repetition ranges within the same archive; these are not independent climates.",
        ),
        (
            "03_archive_factorial",
            "fig:whole-archive",
            "Whole-archive trend errors and the symmetric retention/estimator decomposition. Left: D2 on common station-repetition rows where both retention sets are available; annotations give n and station/group counts. The forward controlled-gap contrast uses 807 of 820 settings. Right: the left bar of each pair is D2 and the right bar is the calibrated classical method. Each bar uses that method's own complete four-cell count, printed under the setting; the two counts are not one shared denominator.",
        ),
        (
            "04_joint_uncertainty",
            "fig:joint-uncertainty",
            "Left: paired annual coverage on the two-method intersection, weighted by incomplete years. Ticks are station-repetition means on the same intersection. The tick labels give the paired archive count and each method's availability out of all archives. The dashed line is the nominal 90 percent annual target. Right: nominal 95 percent trend coverage on each method's own available archives, with that archive count. The right panel is not a paired method comparison. Group-bootstrap intervals use connected groups. No gray band is shown.",
        ),
    ]
    core = "\n".join(
        r"\begin{figure}[p]\centering\includegraphics[width=\textwidth]{figures/simple_research/"
        + name
        + r".pdf}\caption{"
        + caption
        + r"}\label{"
        + label
        + r"}\end{figure}"
        for name, label, caption in figures
    )
    core += "\n" + r"\begin{figure}[p]\centering" + "\n" + r"\includegraphics[width=\textwidth]{figures/architecture/fig2_release_actual.pdf}" + "\n" + r"\caption{The evaluated three-output decision and exploratory trend analysis. The cap applies to an individual raw classifier score, not a certified group risk. The seven-day water--air check was assessed only for the clean and imposed exact-air-substitution cases. The selected-trend working likelihood treats released values as exact and observed bounds as censored.}\label{fig:release-system}" + "\n" + r"\end{figure}" + "\n"
    core += r"\begin{figure}[p]\centering\includegraphics[width=\textwidth]{figures/simple_research/05_output_boundaries.pdf}\caption{Left: three outputs for empirical-calendar masks. Right: numerical-publication rates and selected errors for controlled gaps. Source diagnostics do not remove extrapolation failures. The air-agreement flag addresses the specified exact-substitution stress only; zero publication is shown as unknown rather than zero-risk success.}\label{fig:output-boundaries}\end{figure}" + "\n"
    (PAPER / "simple_core_figures.tex").write_text(core)
    compact = comparisons.loc[
        comparisons.left.eq("D2") & comparisons.n_common.gt(0)
    ].copy()
    compact["setting"] = compact.family + " / " + compact["mode"]
    compact["reference"] = compact.right.map(
        {"plug_in": "Daily plug-in", "stochastic_calibrated": "Calibrated stochastic"}
    )
    tex = table(
        compact,
        [
            ("setting", "Setting"),
            ("reference", "Reference"),
            ("n_common", "Paired $n$"),
            ("left_rmse", "D2 RMSE"),
            ("right_rmse", "Reference RMSE"),
        ],
        "Whole-archive trend errors on identical available station/repetition rows, in degrees C per decade.",
        "tab:whole-archive-paired",
    )
    (PAPER / "simple_research_tables.tex").write_text(tex)
    task_small = task_pairs.copy()
    task_small["setting"] = task_small.family + " / " + task_small["mode"]
    task_small["method"] = task_small.estimator.map(
        {"D2": "D2", "stochastic_calibrated": "Stochastic"}
    )
    si = r"\section{Whole-archive supplements}" + "\n"
    si += "Full paired MSE cells, group and region sensitivities, unavailable cases and source calibration support are in the review-response results. Forward task calibration ends before 2010. Normal-spacing tail extrapolation is compared to constant tails under the same observed-window constraint; its outer distribution is assumed, not identified by the seven stored quantiles. Auxiliary rank coupling is not a posterior for the annual estimator.\n"
    rule_table = rule_summary.copy()
    rule_table["rule"] = rule_table.rule.map({"complete_100":"Complete", "annual_95":"Annual 95",
        "warm_90_station_specific":"Station warm 90", "warm_90_fixed_original":"Fixed warm 90",
        "july_aug_complete":"July--August", "gap_le_49_days_context":"Gap $\\leq$49 d"})
    si += table(
        rule_table,
        [("rule", "Rule"), ("witness_years", "Witnesses"),
         ("admitted_witness_years", "Admitted"), ("excluded_witness_years", "Excluded"),
         ("excluded_exceed_reported_record", "Above accepted")],
        "The same 35 observation-only complete-year witnesses under each screening rule. The accepted-record comparison uses observed windows, not unknown complete H30 values. The 49-day and July--August rows are contextual proxies, not published H30 rules.",
        "tab:observed-rule-comparison",
    )
    small_scenarios = scenario_d2.copy()
    small_scenarios["setting"] = small_scenarios.scenario.map({"synchronized_donors":"Donors", "heat_associated":"Heat"}) + " / " + small_scenarios["mode"].map({"forward":"forward", "offline":"offline"})
    si += table(
        small_scenarios,
        [("setting", "Scenario"), ("paired_rows", "Eligible"),
         ("both_available", "Available"), ("baseline_rmse", "Base RMSE"),
         ("stress_rmse", "Stress RMSE")],
        "Seven-station stress comparisons on common available station/repetition rows. Heat-associated masks and numbers of missing years differ between arms; unavailable cases remain in the eligible denominator. Coverage and width are supplied in the result table.",
        "tab:small-stresses",
    )
    selected = integrated.loc[integrated.family.eq("crossed")].copy()
    selected["method"] = selected.method.map({"released_values_only":"Values", "released_values_and_bounds":"Values + bounds"})
    si += table(
        selected,
        [("mode", "Mode"), ("method", "Released data"), ("n_eligible", "Eligible"),
         ("n_available", "Available"), ("rmse", "RMSE"), ("total_working_width95", "Working width")],
        "Release followed by finite-record trend inference for controlled gaps. The values-and-bounds interval is a Gaussian working-likelihood interval, including regression variability; it is not calibrated missing-data uncertainty.",
        "tab:release-then-trend",
    )
    si += table(
        task_small,
        [
            ("setting", "Setting"),
            ("method", "Method"),
            ("n_common", "$n$"),
            ("independent_coverage95", "Original coverage"),
            ("task_coverage95", "Task coverage"),
            ("width_ratio", "Width ratio"),
        ],
        "Task calibration and independent-draw intervals on exactly the same supported cases. Coverage is a fraction; missing source support is reported separately.",
        "tab:task-calibration",
    )
    small = task[
        ["family", "mode", "estimator", "availability", "minimum_source_groups"]
    ].copy()
    si += table(
        small,
        [
            ("family", "Family"),
            ("mode", "Time setting"),
            ("estimator", "Estimator"),
            ("availability", "Availability"),
            ("minimum_source_groups", "Minimum source groups"),
        ],
        "Task calibration support. Empirical calibration from small source pools does not establish a finite-sample guarantee.",
        "tab:task-calibration-support",
    )
    (PAPER / "simple_research_supporting.tex").write_text(si)
    external_table = additional_witness[
        [
            "station_id",
            "year",
            "n_raw_complete_years",
            "window_mean",
            "maximum_raw_complete_H30",
            "excess",
        ]
    ]
    with (PAPER / "simple_research_supporting.tex").open("a") as handle:
        handle.write(
            table(
                external_table,
                [
                    ("station_id", "Station"),
                    ("year", "Year"),
                    ("n_raw_complete_years", "Complete $n$"),
                    ("window_mean", "Observed $L$"),
                    ("maximum_raw_complete_H30", "Complete max"),
                    ("excess", "Excess"),
                ],
                "Additional observation-only witnesses from approved USGS daily means. Every candidate remains in the qualification table. Sparse complete-reference support precludes an incidence or transfer inference.",
                "tab:additional-observed-records",
            )
        )

    claim_rows = [
        (
            "观测事实",
            "不完整年份可以已观测窗口否定完整年纪录",
            "20/96站、35站年；不确定唯一最热年",
            "observed_records/observed_record_certificates.csv",
        ),
        (
            "年度恢复",
            "目标指标恢复优于简单点填补，但不预设优于合格随机重建",
            "同等校准对照；不主张D2普遍必要",
            "results/wrr_review_response_20261027/annual/source_scorecard_summary.csv",
        ),
        (
            "整档案趋势",
            "统一隐藏多年观测后，保留集合与估计器分别影响趋势误差",
            "42站、20次重复；邻站仍可观测",
            "results/wrr_review_response_20261027/whole_archive/factorial_paired_summary.csv",
        ),
        (
            "联合不确定性",
            "年度校准不能替代趋势校准",
            "前推长缺口覆盖不足；任务校准支持不足",
            "results/wrr_review_response_20261027/whole_archive/paired_task_intervals.csv",
        ),
        (
            "输出边界",
            "数值、观测下界、未知状态分别评价",
            "严重污染条件付出高输出损失；不能泛化为通用质控",
            "results/wrr_review_response_20261027/release_outputs/release_metrics.csv",
        ),
        (
            "外部资料",
            "实际确认资格，并检验原先选定的观测纪录主张",
            f"新西兰九站无合格精度参照；加拿大{bc['n_scored_stations']}站以已发表日均值进行探索性遮挡评分，但逐日24小时完整性未知",
            "results/additional_usgs_observed/robust_record_witnesses.csv",
        ),
    ]
    matrix = pd.DataFrame(
        claim_rows, columns=["主张", "主要比较或事实", "结果及限制", "证据"]
    )
    matrix["主要指标"] = [
        "观测窗口下界减完整年纪录",
        "H30 MAE、CRPS、区间覆盖和宽度",
        "趋势RMSE、配对MSE主效应与交互",
        "缺失分量覆盖、区间宽度、评分和可用率",
        "数值错误率、输出率、热年案例召回与误报",
        "完整参照年数、批准窗口与纪录差值",
    ]
    matrix = matrix[["主张", "主要比较或事实", "主要指标", "结果及限制", "证据"]]
    matrix.to_csv(OUT / "claim_evidence.csv", index=False)
    sections = [
        "# 审稿问题修正与研究交付（2026-10-27）",
        "主命题是：不完整记录可以保留极值信息，但年度恢复、发布数值和趋势推断需要分别验证。复杂估计器不必胜出；未通过的科学结论保留为未通过。",
        "原始结果保留在原目录；本次修订结果位于 results/wrr_review_response_20261027。年度点值及分位数对已观测窗口下界一致投影，整档案两种方法在原源域校准组重新计算偏移；20次年度源域对比则对原有校准结果做相同的事后投影。外尾采用相邻正态分位数间距延伸，这是需要敏感性评价的假设。",
        matrix.to_markdown(index=False),
        "## 整档案实验",
        f"共 {status['completed_station_repetitions']:,} 组站点重复，42站、7地区、20次掩码重复。离线42站，前推41站；芬兰站记录止于1994年，不能参加2010年以后的前推评价。真实日历和受控长缺口分别报告。每次先统一隐藏目标站多年数据，再拟合每日模型、气候态和残差；邻站在此试验中保持可观测。年度模型与校准排除目标测试连接组及其隐藏真值，但前推HUC17估计器保留一个同地区其他训练组，NVE前推区间校准保留两个同地区其他训练组；因此前推并非对所有模型严格外区。年度模型统一使用源拟合种子0；其独立源资料未退化，因此复用既有权重，20次档案掩码不等于20次全局模型重拟合。",
        "前推方法的年度模型、每日模型、依赖结构及任务校准误差均来自2010年以前；任务校准另行生成，不使用2010年以后的校准误差。",
        comparisons.loc[comparisons.n_common.gt(0)].to_markdown(
            index=False, floatfmt=".5f"
        ),
        "## 保留集合与估计器",
        "在同一掩码、同一完整参考趋势下，交叉比较两种保留集合和三种估计器。四个配对MSE单元采用对称分解，同时保留交互，不再使用固定的“60%来自保留”归因。",
        factor.to_markdown(index=False, floatfmt=".5f"),
        "## 完整率规则与观测事实",
        f"独立实现的卷积和逐日历日核查，从同一规范化日值档案重算{observed_reaudit['eligible_stations']}站的{observed_reaudit['reference_station_years_recomputed']}个完整参考站年、{observed_reaudit['incomplete_station_years_recomputed']}个不完整站年及{observed_reaudit['certificate_station_years']}个见证，均与保存结果一致；这不是独立的原始传感器或测量误差验证。另对{screening_reaudit['witness_rule_decisions_checked']}个见证—规则判断和{screening_reaudit['target_year_perturbation_probes']}个目标年扰动进行了核查。10个额外USGS站的已保存日值响应中，{usgs_reaudit['complete_approved_station_years']}个完整参考站年与{usgs_reaudit['witness_station_years_checked']}个见证窗口的算术一致，但未独立重跑质量筛选选窗。",

        f"96站来自{input_precision['input_panel_files']}个项目输入面板，共比较{input_precision['finite_daily_values_compared']}个有限日值；缺失状态及float32转换均无差异，最大单日舍入差为{input_precision['maximum_float32_rounding_c']:.8f}°C，35个见证及0.5°C阈值分类没有变化。这些仍是项目处理后的输入面板，而非提供方原始传感器资料。",
        "逐站暖季使用排除目标年份的五个月气候态。被规则排除的见证若超过已保留年份的最大观测窗口，仅说明超过规则下的已报告窗口记录；保留的不完整年份真实H30可能更高。49日缺口与七八月完整仅作文献情境比较，不冒称相关研究为H30制定了相同规则。",
        rule_summary.to_markdown(index=False),
        "## 联合不确定性与任务校准",
        "独立逐年、共享参数、三年残差块采用逐年完全相同的边际样本，只改变联合次序。所有趋势区间针对缺失引起的有限档案斜率误差；不把气候回归噪声加进来掩盖欠覆盖。",
        trend.loc[
            trend.family.eq("crossed")
            & trend.retention.eq("all")
            & ~trend.dependence.eq("point")
        ].to_markdown(index=False, floatfmt=".4f"),
        f"任务校准使用年度拟合及年度区间校准未使用的规则校准组；组总权重相同。实际前推任务校准的最后源年为 {int(sources.loc[sources['mode'].eq('forward'), 'last_calibration_year'].max())}。少于3个非退化组、零因子或目标宽度不在源域范围时不输出任务校准；这是经验支持筛查，不提供覆盖保证。",
        task.to_markdown(index=False, floatfmt=".4f"),
        task_pairs.to_markdown(index=False, floatfmt=".4f"),
        "### 欠覆盖的后续诊断",
        "评价端的年度误差矩阵区分站点斜率偏差、误差方差及年际协方差贡献；它使用已知评价真值，仅作诊断，没有进入恢复模型或区间校准。协方差项可以为负，不能由“有相关性”推导“趋势区间一定更宽”。",
        error_geometry.to_markdown(index=False, floatfmt=".5f"),
        "逐年比较两方法共同有完整分位数且有下界的评价案例：统计区间端点和中位数落在观测下界、90%区间零宽及其参考覆盖。零宽是年度边际性质，不能与任务校准斜率区间混同。参考是有限档案报告值，不包含传感器测量误差。",
        support_projection.to_markdown(index=False, floatfmt=".4f"),
        "重新调用原模型并固定原校准参数，逐案例核对保存的全部分位数，再记录原始、首次投影、校准修正后和最后投影后的零宽计数。经典方法的原始分位数来自保留已观测日值的有限次插补，因此原始并不意味着不受观测约束。首次投影和投影感知校准仍存在于最后投影前的结果；这不是重新拟合无投影校准的因果试验。",
        projection_stages.to_markdown(index=False, floatfmt=".4f"),
        "使用完整参考H30与已观测下界的关系，将共同评价案例事后分成‘已观测窗口达到参考热峰’和‘参考热峰高于下界’；这必须知道隐藏真值，不能作为发布或模型选择规则。同一站年在不同掩码下可能进入两个组。下面报告按案例加权的覆盖、误差及连接群组重采样区间；群组重采样不能证明独立气候迁移。",
        peak_visibility[["family", "mode", "stratum", "estimator", "n", "stations", "station_years", "groups", "coverage90", "coverage90_bootstrap_low", "coverage90_bootstrap_high", "mae", "width90"]].to_markdown(index=False, floatfmt=".4f"),
        "年度区间另试验源群组加权的经验扩展：来源是与拟合、原区间校准及目标地区分离的规则校准群组；不足三个群组或经验修正为零时标记不可支持。下表的分母是两方法共同可用案例，前后结果只在同一有支持子集比较。这是看过现有结果后开展的探索，未实现分布无关的群组保证，也没有重建联合趋势分布。",
        annual_expansion.loc[annual_expansion.scope.eq("both_methods_common") & annual_expansion.stratum.eq("all"), ["family", "mode", "estimator", "n_eligible", "n_supported", "availability", "stations", "baseline_paired_coverage90", "expanded_paired_coverage90", "baseline_paired_width90", "expanded_paired_width90", "baseline_paired_interval_score90", "expanded_paired_interval_score90"]].to_markdown(index=False, floatfmt=".4f"),
        "尾部敏感性在相同随机次序下比较常数端点与相邻分位数间距给出的正态尾部；两者均施加已观测窗口支持约束。结果不能当作已证明的真实尾部分布或全部归因为联合结构。",
        tail_sensitivity.to_markdown(index=False, floatfmt=".4f"),
        "下面固定同一可评价子集，同时报告年度覆盖、尾部处理和固定年度边际的联合排序。尾部和排序实验各自内部配对，但两个实验的抽样随机数不同，年度失配也没有被实验性修正，故不能把差异相加当成因果分解。群组重采样区间为描述性结果。",
        uncertainty_paired.to_markdown(index=False, floatfmt=".4f"),
        uncertainty_contrasts.to_markdown(index=False, floatfmt=".4f"),
        "## 数值发布率配平比较",
        "在同一批评价案例中，分数规则按原始个体分类器分数从低到高排序，发布数量严格配平三类规则；分数相同按案例标识确定次序。匹配只使用评价特征分布和三类规则的发布数量，不使用隐藏标签，但阈值仍是评价集配平的描述性阈值，不是预先可部署的策略。相同数值数量并不意味着下界和未知状态提供的信息相同；群组重采样区间仅作描述，不能视为普遍安全保证。",
        matched_release.to_markdown(index=False, floatfmt=".4f"),
        "另一项干净回顾性试验中，每个目标地区的分数阈值只用模型的其他地区、组不重叠的规则校准集决定，以近似匹配源集三类规则的发布率。阈值不使用目标标签或目标发布数量；目标侧发布率可以不同。对185个连接组重采样仅作描述，阈值拟合不确定性及气候间依赖未得到保证。",
        source_release.to_markdown(index=False, floatfmt=".4f"),
        source_release_bootstrap.to_markdown(index=False, floatfmt=".4f"),
        "按地区和连接组分别汇总；仅保留两种方法都发布至少一个数值的组来计算组等权条件错误率，零发布的条件错误率为未定义。删去一个地区只删除该地区的评价案例，模型及其他地区的源阈值不重训；不同地区数值发布率可能相差很大，不能把条件错误率的方向计数解释成独立显著性检验。",
        release_region_directions.to_markdown(index=False, floatfmt=".4f"),
        release_group.to_markdown(index=False, floatfmt=".4f"),
        release_regions.to_markdown(index=False, floatfmt=".4f"),
        release_leaveout.to_markdown(index=False, floatfmt=".4f"),


        "## 三类输出和既有失败条件",
        "输出数值、观测窗口下界或未知。可见诊断在源域确定，污染标签和隐藏温度仅用于最后评分。空气贴合诊断只针对既有七日精确替换情景，不能作为通用设备故障识别器。完全拒绝发布时风险为未定义；保留下界仍要求测量有效。",
        states.to_markdown(index=False, floatfmt=".4f"),
        events.loc[
            events.family.eq("calendar") & events.method.eq("three_outputs"),
            [
                "condition",
                "n_true_hot",
                "n_hot_detected",
                "n_hot_missed_or_withheld",
                "n_false_hot",
                "hot_recall",
            ],
        ].to_markdown(index=False, floatfmt=".4f"),
        "漏检或保留未知的热事件、错误热事件和错误数值发布均单独记录于修订结果的热事件表与发布表。风险阈值是原始个体分类分数而非群组风险证书。不同污染比例是情景曲线，不是全国发生率估计。",
        "## 地区与独立组敏感性",
        "42站归为18个连接组。配对误差差异按组重采样并分别列出逐地区删除结果；群组和年份之间的气候独立性仍是条件假设。",
        group_sensitivity.to_markdown(index=False, floatfmt=".5f"),
        regional_sensitivity.to_markdown(index=False, floatfmt=".5f"),
        "## 热相关缺测和邻站同时缺测",
        "每地区按既定顺序各取一站、每站五次掩码。邻站试验对目标站与同一面板邻站同步隐藏相同日期；热相关试验以最早七年气温热峰确定阈值，选择热年及其他年的缺测概率分别为0.90和0.18，因而两臂掩码和缺测率并不完全相同。芬兰站因气温数据不足在热相关情景中不可用。",
        scenario_d2.to_markdown(index=False, floatfmt=".5f"),
        "## 发布后趋势：数值与删失下界",
        "已将实际三类输出接入趋势：数值视为精确观测，观测下界作为右删失，未知年份保留在可用率分母。Gaussian工作区间包含回归变化，不是已校准的缺测部分区间；分别与所有年份D2和暖季规则在共同案例上比较。",
        integrated.to_markdown(index=False, floatfmt=".4f"),
        integrated_pairs.to_markdown(index=False, floatfmt=".4f"),
        "将无法计算水温—气温贴合诊断的年份视为未知，是一个探索性保守选择；原规则未评估并不等于诊断通过。",
        quality_sensitivity.to_markdown(index=False, floatfmt=".4f"),
        "## 新西兰实际资格结果",
        f"{nz['n_acquired_daily_files']}/{nz['n_metadata_candidates']}站已取得日值资料。按原标准接受质量码600，{nz['n_eligible_stations']}站有合格完整热年支持。返回的历史质量码没有被重贴为600，因此没有把未确认质量的记录当作参照真值，也没有计算不存在的预测精度。该检验未预注册。若要建立新区域精度证据，需要确认机构质量码定义或取得符合标准的参照资料。",
        "## 额外批准观测对主要事实的检验",
        f"另行取得十个元数据选定USGS站的批准日均水温，未按恢复误差挑选或替换站点。七个候选位于源站未覆盖的HUC2 13/20，另外三个是既有源区域内的额外站点检验。十站均不满足原四个完整年数值恢复参照要求，因此未进行或宣称外部恢复精度验证。原先选择的主要观测主张则有不同的数学条件：只要有非空完整年纪录，就能检验不完整年的已观测窗口是否已经超出它。四站有非空批准完整年参照，其中{additional['n_witness_stations']}站、{additional['n_witness_station_years']}站年出现反证。",
        "这个额外比较保留了全部批准有限值组成的完整年作为更宽的参照集合；观测窗口排除估计值，并要求原始记录确有缺失、空值、矛盾或未批准日。仅额外质控删值不能制造证据。每个窗口的30个原始批准数值都在证据表中。额外站点仅有1—3个完整参照年，不能与原20/96长期站比例合并或解释为总体发生率，也不能确定唯一最热年或外部趋势可靠性。",
        external_table.to_markdown(index=False, floatfmt=".5f"),
        "## 新外部参考资格与旧接触核查",
        f"NEON公开作者归档的{neon['acquired']}站已按事先列明的单传感器、UTC日和质量标志处理；严格48/48半小时及46/48敏感性均有{neon['strict_reference_eligible']}站达到四个完整日历年，因此不报告恢复精度。",
        f"首次USGS参考尝试取得{attempted_usgs['n_acquired']}站，但身份复核发现{attempted_usgs['prior_contact_stations']}站此前已在全国资料中处理，不能当作新独立验证。更新排除清单后另行取得{fresh_usgs['n_acquired']}/{fresh_usgs['n_candidates']}站，其中{fresh_usgs['n_eligible']}站达到四个完整质量合格年；未达到资格不生成恢复精度。",
        f"留尼汪岛Hub'Eau目录按先固定的名单取得{reunion['n_acquired']}/{reunion['n_candidates']}站；要求正确质量码、每个报告日24个小时及四个完整7月至次年6月热年后，{reunion['n_eligible']}站合格，{reunion['n_unavailable']}站获取不可用。该数据的报告日时区仍待提供方核实，小时均值不是无误差现场真值。",
        f"进一步从网络和既有接触清单中固定{count_screen['metadata_candidates']}个USGS候选，仅筛查2010—2024年官方年度已批准日值数量；{count_screen['statistics_not_returned']}站未返回统计，{count_screen['preflight_pass']}站达到至少4个计数完整年，因此没有新站进入逐日评分。计数可能包含估计值，不能代替逐日质量检查；2010—2024以外年份不在此预筛选范围。接口试点站02450250此前已在E10及早期恢复对比中评分，且本次已打开年度汇总，不能视为新站，已排除。",
        f"挪威机构公开目录中{nve_metadata['not_in_named_raw_or_confirmation']}条记录未在命名原始缓存及确认站点中匹配，其他历史接触、年份质量及河网关系仍未完成核实。排除已读原始站点所在流域后固定{nve_chart['candidate_stations']}站，图表服务返回{nve_chart['points_returned']}站有值、{nve_chart['no_points']}站无值；没有因此证明无历史数据，也没有评分。机构HydAPI正式访问需要注册。英国、加拿大候选的其他来源级限制见 [外部参考线索](reviews/wrr_review_response_20261027/EXTERNAL_REFERENCE_LEADS_ZH.md)。",
        f"加拿大联邦Red River at Emerson的{eccc_red['files_acquired']}个文件已获取：所选站点与源样本一站同属Red River，不是独立流域。目录字典给出V和数字1/2等级，但实际状态、等级用词不同；{eccc_red['validated_word_rows_with_missing_grade']}条明确写VALIDATED却缺等级，{eccc_red['unresolved_station_identity_rows']}条站号与目录不一致。按预先固定的字面V与数字1/2条件，{eccc_red['complete_provider_wallclock_years']}个完整墙钟年；这不意味着被排除资料不可信。地方时间的夏令时约定仍未确认，不进行恢复精度评分。以前已读取的{eccc_red['previous_opened_stations_upper_bound']}站旧缓存，即使把每天至少24行当作乐观必要条件，最多也只有{eccc_red['max_possible_years_prior_cache']}个可能完整年，旧缓存不含唯一小时与等级信息。",
        "Greater Wellington机构说明QC200是未经验证的数据；其具体站点旧码映射仍需提供方确认。新西兰零合格参考不能被改称成功验证。",
        f"加拿大BC作者公开数据全部{bc['n_roster']}站中，{bc['n_exploratory_eligible']}站有至少四个已发表日均值完整年份；加拿大水文部门称水温为未经统一质量保证的辅助输出，原研究自行检查并允许每天只有20小时，逐小时质控标记未公开，故严格24小时参考{bc['n_strict_24h_eligible']}站。参考清洗还使用水气温比较。四站、{bc['n_station_years']}个站年完成逐年留一受控缺测探索，案例并非独立气候，三站属于Fraser河流域（Nechako、Thompson和Fraser）。实际日界线未知，气温使用四舍五入到0.01度的站点坐标。以下数值不是整档案趋势外部验证。",
        f"独立重算全部{bc_integrity['cases']}个案例的30日日均最大值、遮挡后下界和遮挡天数，并重算{bc_integrity['scorecard_metrics_checked']}项得分汇总；差异均在数值容差内。每站另选一个90日缺口，隐藏真值加5°C后四个探针的特征和预测均未变化；这不能证明其他案例或路径全部无泄漏。",
        bc_scores.to_markdown(index=False, floatfmt=".4f"),
        bc_site.to_markdown(index=False, floatfmt=".4f"),
        f"Nechako作者水温资料已更新至2019—2024年。按公开起止日期冻结唯一可能覆盖2020—2023四个完整UTC年的河流候选；每个UTC日必须有96个唯一15分钟数值且标记为P或A。该候选四年中合格完整年为{nechako_reference['qualified_reference_years']}，每年都有非有限记录，故未评分；其与已评价的BC站同一条河，不能作为独立气候确认。原始CC BY作者包和署名说明已包含在候选包中。",
        nechako_years.to_markdown(index=False),
        f"美国Poudre作者归档先按公开起止日期固定{poudre_reference['sites']}站，随后核查2020—2024年的{poudre_reference['site_years']}个站年。每个站年都至少缺{poudre_reference['minimum_missing_quarter_hour_timestamps']}个15分钟UTC时刻，且无完整PASS参考年，因此没有进行恢复评分。四站属于同一流域；作者称2019—2021未收集技术人员校准记录，不能视为独立气候或无误差参考。原始CC BY文件和署名已纳入候选包。",
        poudre_years.to_markdown(index=False),
        f"新斯科舍省固定四个河流站的旧版已核验工作簿与开放门户后，按报告时刻和有限数值检查完整性：两版本共有{nova_reference['common_complete_label_years']}个完整标签站年，其中{nova_reference['common_complete_label_years_equal_1e6']}个所有数值在1e-6°C内容差一致，{nova_reference['stations_with_four_equal_complete_label_years']}站各有至少四年。全时段共有数值标签中{nova_reference['numeric_different_over_0p5_c']}个差异大于0.5°C，这是查看初次比对后追加的描述性阈值。两版本来自同一项目，逐点质量、估计处理及共同时间基准尚未确定，不能称为严格独立精度参考，也未进行模型评分。开放门户数据入包，旧工作簿条款未解决，保留本机。",
        nova_sites.to_markdown(index=False),
        f"在查看来源完整性和两版本一致性之后、查看模型误差之前，另行冻结新斯科舍探索性修订：两站、八个报告时刻完整站年，共{nova_exploratory['cases']}个受控缺口案例。源模型和源校准固定，每次只遮挡一个目标年，其余三个完整年用于本地训练。D2和随机重建的配对MAE分别为{nova_exploratory['D2_mae']:.3f}和{nova_exploratory['stochastic_mae']:.3f}°C；这是重复掩码，不是独立气候。逐案例算术检查通过，两个事后选择的隐藏值扰动探针通过；探针非穷尽。水温时区、估计值标记及逐点质量仍未知，NASA POWER采用地方太阳时，因此该结果不能称为严格独立参考、整档案前推或自然缺测验证。",
        nova_exploratory_pairs.to_markdown(index=False, floatfmt=".4f"),
        nova_exploratory_detail.to_markdown(index=False, floatfmt=".4f"),
        f"在查看原探索结果后，将报告日边界前后移动一小时：八个站年跨年边界小时在两版本均可用且一致；保留完全相同的{nova_clock['common_cases']}个掩码，重新拟合本地阶段并固定源模型、源校准和NASA气温。参考H30最大改变{nova_clock['max_reference_h30_change_c']:.4f}°C，单案例D2点预测最大改变{nova_clock['max_d2_point_change_c']:.3f}°C。此试验不确定真实时区、不能覆盖所有时区偏差，也不验证传感器质量或气候独立性。",
        nova_clock_pairs.to_markdown(index=False, floatfmt=".4f"),
        "## 复现与交付",
        "执行 `make review` 使用已有数据和拟合缓存更新修订分析、图表、稿件及测试。完整从原始数据和模型重建仍需要各来源缓存、许可和原始拟合；不可把缓存模式称为已验证的干净环境端到端重建。源样本含LUBW观测，相关再使用和分发条件须按提供方条款处理；作者与永久存档信息仍待提供。",
        "五张主图位于 [paper/wrr_tr/figures/simple_research](../paper/wrr_tr/figures/simple_research/)。主稿和补充材料源文件位于 [paper/wrr_tr](../paper/wrr_tr/)。各提供方来源与当前记录条款位于 [来源清单](../results/wrr_review_response_20261027/source_rights/provider_source_inventory.csv)；LUBW咨询和编辑资料访问说明为未发送草稿。作者、机构、资助和存档字段由用户填写。",
        "本轮结果支持问题与观测发现的价值，仍不支持通用安全发布、全情景趋势校准或独立气候迁移。不能以软件测试通过替代这些科学结论。",
    ]
    (DOC / "SIMPLE_WORKFLOW_ZH.md").write_text("\n\n".join(sections) + "\n")
    (DOC / "CLAIM_EVIDENCE_ZH.md").write_text(
        "# 主张、比较、指标和失败解释\n\n" + matrix.to_markdown(index=False) + "\n"
    )
    requirements = [
        (1, "收敛主张并给出证据表", "docs/CLAIM_EVIDENCE_ZH.md"),
        (2, "整档案缺测后重拟合，离线和时间前推", "results/wrr_review_response_20261027/whole_archive/status.json"),
        (
            3,
            "保留集合和估计器的因子试验",
            "results/wrr_review_response_20261027/whole_archive/factorial_contrasts.csv",
        ),
        (
            4,
            "相同年度边际的联合恢复及任务校准",
            "results/wrr_review_response_20261027/whole_archive/paired_task_intervals.csv",
        ),
        (5, "数值、下界和未知三类输出", "results/wrr_review_response_20261027/release_outputs/output_states.csv"),
        (
            6,
            "既有失败情景及未知污染比例",
            "results/wrr_review_response_20261027/release_outputs/exposure_mixtures.csv",
        ),
        (
            7,
            "实际取得外部资料、确认资格并检验观测主张",
            "results/additional_usgs_observed/robust_record_witnesses.csv",
        ),
        (8, "五张核心主图及重排后的论文", "paper/wrr_tr/simple_core_figures.tex"),
    ]
    pd.DataFrame(requirements, columns=["step", "work", "evidence"]).to_csv(
        OUT / "requirements_evidence.csv", index=False
    )
    print(
        "Wrote five research figures, manuscript inputs and evidence reports.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
