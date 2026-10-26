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
import matplotlib.ticker as mticker
import wrr_tr_common as T

SOURCE = T.ROOT / "results/wrr_review_completion_20261024"
OUT = T.ROOT / "results/whole_archive"
RELEASE = T.ROOT / "results/release_outputs"
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
    annual = pd.read_csv(OUT / "annual_summary.csv")
    contrasts = pd.read_csv(OUT / "factorial_contrasts.csv")
    comparisons = pd.read_csv(OUT / "paired_trend_estimators.csv")
    task = pd.read_csv(OUT / "task_calibration_summary.csv")
    task_pairs = pd.read_csv(OUT / "paired_task_intervals.csv")
    error_geometry = pd.read_csv(OUT / "evaluation_error_summary.csv")
    tail_sensitivity = pd.read_csv(OUT / "quantile_tail_summary.csv")
    sources = pd.read_csv(OUT / "task_calibration_sources.csv")
    releases = pd.read_csv(RELEASE / "release_metrics.csv")
    states = pd.read_csv(RELEASE / "output_states.csv")
    events = pd.read_csv(RELEASE / "hot_event_metrics.csv")
    status = json.loads((OUT / "status.json").read_text())
    nz = json.loads(
        (SOURCE / "independent_study/observed_qualification.json").read_text()
    )
    additional_path = T.ROOT / "results/additional_usgs_observed"
    additional = json.loads((additional_path / "status.json").read_text())
    additional_witness = pd.read_csv(
        additional_path / "robust_record_witnesses.csv", dtype={"station_id": str}
    )
    witness = pd.read_csv(SOURCE / "observed_records/observed_record_certificates.csv")
    score = pd.read_csv(SOURCE / "evidence/scorecard_summary.csv")
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

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9))
    methods = [
        "plug_in",
        "functional_debias",
        "distribution_regression",
        "stochastic_regression_calibrated",
    ]
    labels = ["Plug-in", "Debias", "D2", "Stochastic"]
    b = (
        score.loc[score.family.eq("crossed") & score.stratum.eq("danger")]
        .set_index("estimator")
        .loc[methods]
    )
    axes[0].bar(np.arange(4), b.mae_median, color=COLORS)
    axes[0].errorbar(
        np.arange(4),
        b.mae_median,
        yerr=np.vstack([b.mae_median - b.mae_lower, b.mae_upper - b.mae_median]),
        fmt="none",
        ecolor="0.25",
        capsize=3,
    )
    axes[0].set(
        xticks=np.arange(4),
        xticklabels=labels,
        ylabel="H30 MAE (C)",
        title="Point accuracy",
    )
    axes[1].bar(
        [0, 1], b.loc[methods[-2:], "coverage90_median"] * 100, color=COLORS[2:]
    )
    axes[1].axhline(90, color="0.35", ls="--", lw=1)
    axes[1].set(
        xticks=[0, 1],
        xticklabels=labels[-2:],
        ylabel="Coverage (%)",
        ylim=(0, 100),
        title="Calibration",
    )
    save(fig, "02_annual_comparators")

    settings = [
        ("calendar", "offline"),
        ("crossed", "offline"),
        ("calendar", "forward"),
        ("crossed", "forward"),
    ]
    names = [
        "Cal.\noffline",
        "Ctrl.\noffline",
        "Cal.\nforward",
        "Ctrl.\nforward",
    ]
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.2))
    for i, (family, mode) in enumerate(settings):
        b = trend.loc[
            trend.family.eq(family)
            & trend["mode"].eq(mode)
            & trend.estimator.eq("D2")
            & trend.dependence.eq("point")
        ].set_index("retention")
        axes[0].bar(
            i - 0.18,
            b.loc["warm90", "rmse"],
            width=0.34,
            color="0.72",
            label="Warm-season" if i == 0 else None,
        )
        axes[0].bar(
            i + 0.18,
            b.loc["all", "rmse"],
            width=0.34,
            color=COLORS[0],
            label="Retain all + D2" if i == 0 else None,
        )
        for j, estimator in enumerate(["D2", "stochastic_calibrated"]):
            row = factor.loc[
                factor.family.eq(family)
                & factor["mode"].eq(mode)
                & factor.estimator.eq(estimator)
            ].iloc[0]
            x = i + (-0.18 if j == 0 else 0.18)
            retention = 100 * row.retention_fraction
            axes[1].bar(x, retention, width=0.32, color=COLORS[0])
            axes[1].bar(
                x, 100 - retention, bottom=retention, width=0.32, color=COLORS[1]
            )
    axes[0].set(
        xticks=range(4),
        xticklabels=names,
        ylabel="Trend RMSE (C/dec)",
        title="Whole-archive trend error",
    )
    axes[0].set_yscale("log")
    axes[0].yaxis.set_major_formatter(mticker.FormatStrFormatter("%g"))
    axes[0].yaxis.set_minor_formatter(mticker.NullFormatter())
    axes[0].legend(frameon=False, fontsize=8.5)
    axes[1].set(
        xticks=range(4),
        xticklabels=names,
        ylabel="MSE gain (%)",
        ylim=(0, 105),
        title="Retention vs estimator",
    )
    from matplotlib.patches import Patch

    axes[1].legend(
        handles=[
            Patch(color=COLORS[0], label="Retention"),
            Patch(color=COLORS[1], label="Estimator"),
        ],
        frameon=False,
        fontsize=8.5,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.30),
        ncol=2,
    )
    save(fig, "03_archive_factorial")

    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.2))
    for j, estimator in enumerate(["D2", "stochastic_calibrated"]):
        b = annual.loc[
            annual.family.eq("crossed") & annual.estimator.eq(estimator)
        ].set_index("mode")
        axes[0].bar(
            np.arange(2) + (j - 0.5) * 0.34,
            b.loc[["offline", "forward"], "mean_station_coverage90"] * 100,
            width=0.32,
            color=COLORS[j],
            label="D2" if j == 0 else "Stochastic",
        )
    axes[0].axhline(90, color="0.4", ls="--", lw=1)
    axes[0].set(
        xticks=[0, 1],
        xticklabels=["Offline", "Forward"],
        ylabel="Coverage (%)",
        ylim=(0, 100),
        title="Annual marginals",
    )
    axes[0].legend(
        frameon=False,
        fontsize=8.5,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.2),
        ncol=3,
    )
    for j, dependence in enumerate(
        ["independent", "shared_parameters", "residual_blocks"]
    ):
        values = []
        for mode in ["offline", "forward"]:
            for estimator in ["D2", "stochastic_calibrated"]:
                row = trend.loc[
                    trend.family.eq("crossed")
                    & trend["mode"].eq(mode)
                    & trend.estimator.eq(estimator)
                    & trend.dependence.eq(dependence)
                ].iloc[0]
                values.append(100 * row.missing_coverage95)
        axes[1].plot(
            np.arange(4) + (j - 1) * 0.08,
            values,
            "o-",
            color=COLORS[j],
            ms=5,
            label=["Independent", "Shared", "Blocks"][j],
        )
    axes[1].axhspan(90, 97, color="0.9")
    axes[1].axhline(95, color="0.5", ls="--", lw=1)
    axes[1].set(
        xticks=range(4),
        xticklabels=[
            "D2\noff",
            "Stoch.\noff",
            "D2\nfwd",
            "Stoch.\nfwd",
        ],
        ylabel="Trend coverage (%)",
        ylim=(65, 100),
        title="Joint ranks",
    )
    axes[1].legend(frameon=False, fontsize=8.5, loc="lower left")
    save(fig, "04_joint_uncertainty")

    conditions = ["clean", "hot_year_extrapolation", "future_years", "air_exposure"]
    labels = ["Clean", "Hot", "Future", "Air"]
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.2))
    b = states.loc[states.family.eq("calendar")].set_index("condition").loc[conditions]
    bottom = np.zeros(4)
    for column, label, color in [
        ("estimate_fraction", "Estimate", COLORS[0]),
        ("bound_fraction", "Bound", COLORS[2]),
        ("unknown_fraction", "Unknown", "0.8"),
    ]:
        values = 100 * b[column].to_numpy()
        axes[0].bar(range(4), values, bottom=bottom, label=label, color=color)
        bottom += values
    axes[0].set(
        xticks=range(4),
        xticklabels=labels,
        ylabel="Cases (%)",
        title="Three outputs",
    )
    axes[0].legend(
        frameon=False,
        fontsize=8.5,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.2),
        ncol=3,
    )
    for i, condition in enumerate(conditions):
        b = releases.loc[
            releases.family.eq("crossed") & releases.condition.eq(condition)
        ].set_index("method")
        for method, marker in [("fixed_risk", "o"), ("three_outputs", "s")]:
            row = b.loc[method]
            if pd.notna(row.risk):
                axes[1].scatter(
                    row.retention * 100,
                    row.risk * 100,
                    color=COLORS[i],
                    marker=marker,
                    s=55,
                )
        if pd.notna(b.loc["three_outputs", "risk"]):
            row = b.loc["three_outputs"]
            axes[1].annotate(
                labels[i],
                (row.retention * 100, row.risk * 100),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=8.5,
            )
        else:
            row = b.loc["fixed_risk"]
            axes[1].annotate(
                labels[i],
                (row.retention * 100, row.risk * 100),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=8.5,
            )
    axes[1].set(
        xlabel="Values published (%)",
        ylabel="Selected error (%)",
        title="Withholding cost",
        xlim=(0, 100),
        ylim=(0, 45),
    )
    axes[1].text(
        0.03,
        0.95,
        "Circle: fixed cap\nSquare: three outputs\nNo square: zero published",
        transform=axes[1].transAxes,
        va="top",
        fontsize=8.5,
    )
    save(fig, "05_output_boundaries")
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
    methods = r"""\subsection{Whole-archive degradation and task-level uncertainty}
The new trend benchmark hides every selected year of a target station before fitting its daily models, climatology or residual histories. Neighboring physical stations remain observed covariates in this experiment. The benchmark contains 42 stations with at least twenty complete reference years in seven regions. One Finnish record ends in 1994, leaving 41 stations for forward evaluation. Twenty paired mask repetitions use both empirical calendars and controlled 30--90-day gaps; after seven observed burn-in years, each reference year is degraded with probability 0.35. These 3,320 archive experiments reuse no jointly hidden target observation for fitting another year. Original complete records enter scoring only. The archived single-year plug-in is retained as an optimistic-information paired comparator on identical masks.

Offline daily fits use the remaining visible history. Forward annual models and interval offsets use source observations before 2010, exclude the evaluated region and connected groups, and are applied to 2010 onward. Forward local daily fitting and dependence estimation also exclude water observations from 2010 onward. These are current-vintage retrospective forward experiments, not a historical real-time field trial. Annual regression weights remain source-only and use source-fit seed zero throughout. Their independent source observations do not change across archive masks, so those fits are reused; every local stage that uses the degraded target archive is refitted. Twenty archive masks are not twenty new global model fits.

On each degraded archive, the retention set (90\% warm-season rule or all supported years) is crossed with the annual estimator (daily plug-in, equally calibrated stochastic regression or D2). Every slope is scored against the same complete-record slope. For the four MSE cells $A$ (rule/plug-in), $B$ (all/plug-in), $C$ (rule/alternative) and $D$ (all/alternative), the symmetric retention contribution is $\{(A-B)+(C-D)\}/2$, and the estimator contribution is $\{(A-C)+(B-D)\}/2$. They sum to $A-D$; the interaction is $(A-B)-(C-D)$. Complete paired cells, rather than different available subsets, determine each decomposition.

We use 256 stratified samples of each stored annual quantile function. Independently permuted ranks, shared year-bootstrap regression parameters with annual residual innovations, and shared parameters with contiguous three-year residual blocks reorder exactly the same annual samples. Dependence information comes only from visible out-of-fold residual histories of a small auxiliary harmonic/air Ridge model. Its shared bootstrap state is not a posterior for the D2 tree weights or for the selected donor model, and both annual estimators receive the same coupling. Year gaps are not treated as adjacent residual years. These rank couplings are empirical dependence sensitivities, not exact posterior samples or coverage theorems. Constant outer quantile tails remain an explicit limitation.

The task-level comparator calibrates absolute slope error divided by an independent-draw interval half-width. Every source connected group receives equal total weight in the empirical 95th percentile. Calibration uses only the annual model's unused rule-calibration groups; their archives are re-predicted using the same held-region annual model and offsets. Forward task calibration is separately generated using jointly masked observations strictly before 2010. It uses no post-2009 calibration errors. Source support and matched-case width, coverage and interval-score comparisons are reported; one to a few source groups cannot establish population coverage. All uncertainty scores target the finite complete-record slope, excluding the regression noise that can make total trend intervals misleadingly wide.
"""
    (PAPER / "simple_research_methods.tex").write_text(methods)
    results = r"""\subsection{Whole-archive refitting, retention and uncertainty}
The whole-archive benchmark completes \WARepetitions{} station/repetition/setting evaluations at \WAStations{} long-record stations. Figure~\ref{fig:whole-archive} and Table~\ref{tab:whole-archive-paired} use common station/repetition rows. Retaining years still improves the finite-record slope comparison, but estimator rankings depend on the time setting. D2 improves over the daily plug-in in this benchmark; calibrated stochastic regression is better than D2 on the paired forward cases. The paired optimistic-information plug-in and the truly degraded-archive plug-in differ much less here than the retention-rule contrast. That result is conditional on observed neighboring stations and this mask design.

The factorial comparison identifies a retention contribution rather than assigning one step of a sequential pipeline all of its improvement. For offline controlled gaps, the symmetric retention contribution is \WARetentionShare\% of the D2-versus-rule/plug-in MSE gain. This is a result for this experiment, not a universal percentage. Estimator effects and interactions are retained in the full paired table.

Annual marginals and trend uncertainty give different answers (Figure~\ref{fig:joint-uncertainty}). Under controlled gaps the D2 missing-data trend interval covers \WAOfflineCoverage\% offline and \WAForwardCoverage\% forward. Shared parameters with residual blocks give \WABlockForwardCoverage\% in the forward experiment. Consequently, adding cross-year dependence does not by itself solve the forward uncertainty problem. An evaluation-only covariance decomposition also finds that cross-year terms need not increase slope-error variance; these oracle error covariances are never used to fit predictions. A paired tail sensitivity preserves the central stored quantile function but extends its unidentified outer tails using adjacent-quantile Gaussian scales. It changes the marginal tail assumption, not just the joint ranks. The continuation is unconstrained by the observed-window support and is a diagnostic only, not a calibrated full predictive distribution. Task-level calibration can change coverage and width, but limited independent source support and failure on some settings prevent a general calibrated-trend claim. Its available subset is compared with the same independent-draw subset in the supporting information.

\subsection{Observed facts, numerical estimates and unknown outputs}
The release logic is stated in Figure~\ref{fig:release-system}. It is a design schematic; the empirical support for each gate is reported below and does not constitute an operational certification.
The three-output comparison uses an estimate only within the source feature range and risk cap, an observed-window bound when a numerical estimate is withheld, and unknown when no valid bound is available or visible readings raise a quality flag. Visible edge anomalies and air-gap anomalies use source-only 99th-percentile limits. A separate seven-day mean absolute water--air difference at most 0.05$^{\circ}$C flags the existing exact-air-substitution scenario. This test is specific to that imposed contamination and is not a general validated sensor diagnostic. Hidden temperatures and intervention labels never enter the output decision.

Figure~\ref{fig:output-boundaries} reports the cost of withholding numbers. Source-range diagnostics do not make hot-year extrapolation or temporal shift safe. Exact-air substitution can be detected while sacrificing almost all numerical output in that condition; zero publication has undefined selected risk and is not successful numerical recovery. Observed bounds retain heat information only when the reported measurements are valid. Event tables distinguish detected hot-year cases, missed or withheld cases, and false hot declarations; mask realizations are not counted as independent physical events. Mixture curves vary the imposed contamination fraction; they do not estimate its prevalence in real archives.
"""
    (PAPER / "simple_research_results.tex").write_text(results)
    external_text = r"""\subsection{Additional observation-only corroboration}
We obtained approved daily-mean USGS temperature records at ten additional metadata-selected stream stations. None was a source-model target. Seven candidates lie in HUC2 regions 13 or 20, absent from the source station regions; three are additional station checks within already represented HUC2 regions. The candidates and all qualification failures are retained. This unregistered intake was not a random sample or a blinded confirmation, and the reference histories are shorter and sparser than the original long-record panel.

The unchanged four-complete-year reconstruction criterion yields zero eligible numerical-recovery references. The observation-only claim needs a different comparison: an incomplete year can contradict the maximum of the complete-year record whenever at least one approved-complete reference year exists. We retain every approved finite reference value, including reference years that an extra heuristic-QC filter might remove. Candidate windows must contain thirty consecutive approved, nonestimated daily values after source QC, and the incomplete year must have an actual absent, null, contradictory or unapproved provider day. Heuristic censoring alone cannot create a witness.

There are four stations with a nonempty approved-complete reference, each with only one to three reference years. At \WAAdditionalStations{} of these stations, \WAAdditionalYears{} incomplete station-years contain verified windows exceeding every approved-complete H30 in the analyzed record (Figure~\ref{fig:observed-records}; supporting information). For example, the Rio Mora 2020 window exceeds the complete-only record by approximately 0.883$^{\circ}$C, and a Pecos River 2020 window by 0.643$^{\circ}$C. These facts corroborate record omission without fitting any imputer. They do not estimate an omission incidence, verify a unique warmest year, establish external reconstruction accuracy, or validate trend or risk guarantees. Every witness includes the thirty original approved values; agency reporting and measurement validity remain assumptions.
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
            "Annual estimation under difficult controlled gaps. Bars on MAE show empirical repetition ranges within the same archive; matching interval calibration removes evidence of a unique D2 advantage.",
        ),
        (
            "03_archive_factorial",
            "fig:whole-archive",
            "Whole-archive trend errors and the symmetric retention/estimator decomposition. Left: D2 with identical masks and either retention set. Right: D2 and calibrated stochastic alternatives, with complete paired MSE cells. Contribution percentages are specific to each experimental setting.",
        ),
        (
            "04_joint_uncertainty",
            "fig:joint-uncertainty",
            "Annual and finite-record trend uncertainty are evaluated separately. Joint rank methods preserve every sampled annual marginal. The shaded 90--97 percent trend-coverage band is descriptive, and forward undercoverage remains.",
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
    core += "\n" + r"\begin{figure}[p]\centering" + "\n" + r"\includegraphics[width=\textwidth]{figures/architecture/fig2_release_system.pdf}" + "\n" + r"\caption{Release-system design. Gate 1 screens visible quality; Gate 2 requires source-range support and a calibrated group-risk estimate at or below the release cap; Gate 3 supplies an observed lower bound when a numerical value is withheld. Tier~1 values and Tier~2 bounds may enter task-calibrated trend inference, whereas Tier~3 cases remain in denominators. This is a schematic of the evaluated decision logic, not an operational certification. The editable draw.io source is archived with the figure.}\label{fig:release-system}" + "\n" + r"\end{figure}" + "\n"
    core += r"\begin{figure}[p]\centering\includegraphics[width=\textwidth]{figures/simple_research/05_output_boundaries.pdf}\caption{Three reported outputs and their numerical-publication costs. Source diagnostics do not remove extrapolation failures. The air-agreement flag addresses the specified exact-substitution stress only; zero publication is shown as unknown rather than zero-risk success.}\label{fig:output-boundaries}\end{figure}" + "\n"
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
    si += "The full MSE cells, interactions, matched estimator contrasts, unavailable cases and task calibration sources are stored in results/whole\\_archive. Independent source groups, rather than mask repetitions, determine calibration support. Forward task calibration ends before 2010. The four error-direction illustration uses a single synthetic half-degree common shock on thirty annual values; it is an algebraic sensitivity, not new river evidence. The evaluation-only error covariance uses hidden reference values solely for diagnosis and is never a deployment estimator. Gaussian-tail extrapolation leaves the central stored quantiles unchanged but changes the marginal tails, and is reported separately from the fixed-marginal rank comparison.\n"
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
            "evidence/scorecard_summary.csv",
        ),
        (
            "整档案趋势",
            "统一隐藏多年观测后，保留集合与估计器分别影响趋势误差",
            "42站、20次重复；邻站仍可观测",
            "results/whole_archive/factorial_paired_summary.csv",
        ),
        (
            "联合不确定性",
            "年度校准不能替代趋势校准",
            "前推长缺口覆盖不足；任务校准支持不足",
            "results/whole_archive/paired_task_intervals.csv",
        ),
        (
            "输出边界",
            "数值、观测下界、未知状态分别评价",
            "严重污染条件付出高输出损失；不能泛化为通用质控",
            "results/release_outputs/release_metrics.csv",
        ),
        (
            "外部资料",
            "实际确认资格，并检验原先选定的观测纪录主张",
            f"新西兰九站无合格精度参照；另十站中{additional['n_witness_stations']}站、{additional['n_witness_station_years']}站年有批准观测纪录反证；不报告外部精度",
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
        "# 简化后的研究交付（2026-10-26）",
        "主命题是：不完整记录可以保留极值信息，但年度恢复、发布数值和趋势推断需要分别验证。复杂估计器不必胜出；未通过的科学结论保留为未通过。",
        "代码使用普通文件、可读缓存名和整数随机种子。已删除哈希清单、逐字节归档检查、执行包冻结、公开注册执行门槛和进程写锁。保留观测质量、训练/评价隔离和数值验证。",
        matrix.to_markdown(index=False),
        "## 整档案实验",
        f"共 {status['completed_station_repetitions']:,} 组站点重复，42站、7地区、20次掩码重复。离线42站，前推41站；芬兰站记录止于1994年，不能参加2010年以后的前推评价。真实日历和受控长缺口分别报告。每次先统一隐藏目标站多年数据，再拟合每日模型、气候态和残差；邻站在此试验中保持可观测。年度模型与校准来自外区，不用目标站隐藏真值。年度模型统一使用源拟合种子0；其独立源资料未退化，因此复用既有权重，20次档案掩码不等于20次全局模型重拟合。",
        "前推方法的年度模型、每日模型、依赖结构及任务校准误差均来自2010年以前；任务校准另行生成，不使用2010年以后的校准误差。",
        comparisons.loc[comparisons.n_common.gt(0)].to_markdown(
            index=False, floatfmt=".5f"
        ),
        "## 保留集合与估计器",
        "在同一掩码、同一完整参考趋势下，交叉比较两种保留集合和三种估计器。四个配对MSE单元采用对称分解，同时保留交互，不再使用固定的“60%来自保留”归因。",
        factor.to_markdown(index=False, floatfmt=".5f"),
        "## 联合不确定性与任务校准",
        "独立逐年、共享参数、三年残差块采用逐年完全相同的边际样本，只改变联合次序。所有趋势区间针对缺失引起的有限档案斜率误差；不把气候回归噪声加进来掩盖欠覆盖。",
        trend.loc[
            trend.family.eq("crossed")
            & trend.retention.eq("all")
            & ~trend.dependence.eq("point")
        ].to_markdown(index=False, floatfmt=".4f"),
        f"任务校准使用年度拟合及年度区间校准未使用的规则校准组；每一目标地区使用同一个外区模型重新预测这些组。组总权重相同。实际前推任务校准的最后源年为 {int(sources.loc[sources['mode'].eq('forward'), 'last_calibration_year'].max())}。少量源组、有限前推可用率和部分失败，均不能转换为总体95%覆盖保证。",
        task.to_markdown(index=False, floatfmt=".4f"),
        task_pairs.to_markdown(index=False, floatfmt=".4f"),
        "### 欠覆盖的后续诊断",
        "评价端的年度误差矩阵区分站点斜率偏差、误差方差及年际协方差贡献；它使用已知评价真值，仅作诊断，没有进入恢复模型或区间校准。协方差项可以为负，不能由“有相关性”推导“趋势区间一定更宽”。",
        error_geometry.to_markdown(index=False, floatfmt=".5f"),
        "尾部敏感性在同一随机次序下比较常数端点与基于相邻分位数间距的高斯尾部延伸。它保持中间90%的分位数函数，改变外尾假设，且没有额外施加已观测窗口支持约束，因此仅作诊断，不能称作校准后的完整预测分布或归因为联合结构改进。覆盖、宽度和评分一起报告，实际有缺测的重复才进入该比较。",
        tail_sensitivity.to_markdown(index=False, floatfmt=".4f"),
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
        "漏检或保留未知的热事件、错误热事件和错误数值发布均单独记录于 [热事件表](../results/release_outputs/hot_event_metrics.csv) 与 [发布表](../results/release_outputs/release_metrics.csv)。不同污染比例是情景曲线，不是全国发生率估计。",
        "## 新西兰实际资格结果",
        f"{nz['n_acquired_daily_files']}/{nz['n_metadata_candidates']}站已取得日值资料。按原标准接受质量码600，{nz['n_eligible_stations']}站有合格完整热年支持。返回的历史质量码没有被重贴为600，因此没有把未确认质量的记录当作参照真值，也没有计算不存在的预测精度。该检验未预注册。若要建立新区域精度证据，需要确认机构质量码定义或取得符合标准的参照资料。",
        "## 额外批准观测对主要事实的检验",
        f"另行取得十个元数据选定USGS站的批准日均水温，未按恢复误差挑选或替换站点。七个候选位于源站未覆盖的HUC2 13/20，另外三个是既有源区域内的额外站点检验。十站均不满足原四个完整年数值恢复参照要求，因此未进行或宣称外部恢复精度验证。原先选择的主要观测主张则有不同的数学条件：只要有非空完整年纪录，就能检验不完整年的已观测窗口是否已经超出它。四站有非空批准完整年参照，其中{additional['n_witness_stations']}站、{additional['n_witness_station_years']}站年出现反证。",
        "这个额外比较保留了全部批准有限值组成的完整年作为更宽的参照集合；观测窗口排除估计值，并要求原始记录确有缺失、空值、矛盾或未批准日。仅额外质控删值不能制造证据。每个窗口的30个原始批准数值都在证据表中。额外站点仅有1—3个完整参照年，不能与原20/96长期站比例合并或解释为总体发生率，也不能确定唯一最热年或外部趋势可靠性。",
        external_table.to_markdown(index=False, floatfmt=".5f"),
        "## 复现与交付",
        "执行 `make review` 完成本地实验、输出边界、独立资料资格、报告、论文和科学测试。已有日拟合可用 `--resume` 复用；只需刷新年度校准与趋势结果时执行 `python scripts/521_whole_archive.py --reanalyze`。",
        "五张主图位于 [paper/wrr_tr/figures/simple_research](../paper/wrr_tr/figures/simple_research/)。主稿和补充材料源文件位于 [paper/wrr_tr](../paper/wrr_tr/)。作者、机构、资助和存档字段由用户填写。",
        "本轮结果支持问题与观测发现的价值，仍不支持通用安全发布、全情景趋势校准或独立气候迁移。不能以软件测试通过替代这些科学结论。",
    ]
    (DOC / "SIMPLE_WORKFLOW_ZH.md").write_text("\n\n".join(sections) + "\n")
    (DOC / "CLAIM_EVIDENCE_ZH.md").write_text(
        "# 主张、比较、指标和失败解释\n\n" + matrix.to_markdown(index=False) + "\n"
    )
    requirements = [
        (1, "收敛主张并给出证据表", "docs/CLAIM_EVIDENCE_ZH.md"),
        (2, "整档案缺测后重拟合，离线和时间前推", "results/whole_archive/status.json"),
        (
            3,
            "保留集合和估计器的因子试验",
            "results/whole_archive/factorial_contrasts.csv",
        ),
        (
            4,
            "相同年度边际的联合恢复及任务校准",
            "results/whole_archive/paired_task_intervals.csv",
        ),
        (5, "数值、下界和未知三类输出", "results/release_outputs/output_states.csv"),
        (
            6,
            "既有失败情景及未知污染比例",
            "results/release_outputs/exposure_mixtures.csv",
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
