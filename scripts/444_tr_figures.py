#!/usr/bin/env python3
"""TR figures 1-6 for the target-recovery manuscript, from the result tables.

Colours follow one fixed assignment across figures (validated categorical
order): target-aware = blue, plug-in and current practice = orange, recovery
law = aqua, a fourth method = yellow; rules are neutral grey points with
direct labels.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import wrr_tr_common as T

OUT = T.OUT / "figures"
PAPER = T.ROOT / "paper/wrr_tr/figures"
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#a8a7a2", "#e6e5e1"
LAYER_COLOURS = {"air_ridge": ORANGE, "donor_ridge": BLUE, "other": AQUA}
LAYER_LABELS = {"air_ridge": "Air-temperature regression", "donor_ridge": "Neighbour regression", "other": "Interpolation or climatology"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
    "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2, "axes.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False, "legend.fontsize": 7.5,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5, "axes.axisbelow": True, "savefig.dpi": 400,
})


def save(figure, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    PAPER.mkdir(parents=True, exist_ok=True)
    for extension in ("pdf", "png"):
        figure.savefig(OUT / f"{name}.{extension}", bbox_inches="tight")
        shutil.copy2(OUT / f"{name}.{extension}", PAPER / f"{name}.{extension}")
    plt.close(figure)


def panel(axis, letter: str) -> None:
    axis.text(-0.14, 1.04, letter, transform=axis.transAxes, fontsize=9.5, fontweight="bold", va="bottom", ha="left", color=INK)


def source_cases() -> pd.DataFrame:
    cases = pd.read_parquet(T.OUT / "e2_cases/cases.parquet")
    return cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)


def figure1() -> None:
    """E1: missingness is only weakly state-dependent but declines strongly over time."""

    models = pd.read_csv(T.OUT / "e1_missingness/missingness_models.csv")
    rows = [
        ("station_year_conditional_logit", "z_air", "Warm season incomplete,\nper SD summer air (station FE)"),
        ("station_year_conditional_logit_julaug", "z_air", "July-August incomplete,\nper SD summer air"),
        ("station_year_mixed_station_region_year", "z_air", "Warm season incomplete,\nstation + region-year effects"),
        ("onset_case_crossover_air", "z_air_week", "Gap onset day,\nper SD 7-day air anomaly"),
        ("onset_case_crossover_air_water", "z_water_lag", "Gap onset day,\nper SD water anomaly (lag 1-3 d)"),
        ("onset_case_crossover_usgs_flow", "low_flow", "Gap onset day,\nflow below 20th percentile (USGS)"),
        ("station_year_conditional_logit", "trend", "Warm season incomplete,\nper decade"),
    ]
    figure, axes = plt.subplots(1, 3, figsize=(7.2, 2.9), gridspec_kw={"width_ratios": [1.45, 1, 1]})
    axis = axes[0]
    for position, (analysis, covariate, label) in enumerate(rows):
        row = models.loc[(models.analysis == analysis) & (models.covariate == covariate)].iloc[0]
        y = len(rows) - 1 - position
        axis.errorbar(row.odds_ratio, y, xerr=[[row.odds_ratio - row.odds_ratio_lower95], [row.odds_ratio_upper95 - row.odds_ratio]], fmt="o", ms=4.5, color=BLUE, ecolor=BLUE, elinewidth=1.2, capsize=0)
    axis.set_yticks(range(len(rows)))
    axis.set_yticklabels([label for *_, label in rows][::-1], fontsize=6.6)
    axis.axvline(1, color=INK2, lw=0.8)
    axis.axvline(1.2, color=MUTED, lw=0.8, ls="--")
    axis.text(1.215, -0.35, "Gate A", fontsize=6.0, color=INK2, va="bottom")
    axis.set_xscale("log")
    axis.set_xticks([0.6, 0.8, 1, 1.2, 1.5])
    axis.set_xticklabels(["0.6", "0.8", "1", "1.2", "1.5"])
    axis.set_xlabel("Odds ratio (95% interval)")
    axis.grid(axis="y", visible=False)
    panel(axis, "a")
    sample = pd.read_parquet(T.OUT / "e1_missingness/station_year_sample.parquet")
    sample["decade"] = (sample.year // 10) * 10
    by_decade = sample.loc[sample.decade >= 1980].groupby("decade").agg(share=("warm_incomplete", "mean"), n=("warm_incomplete", "size")).reset_index()
    axis = axes[1]
    labels = [f"{d}s" for d in by_decade.decade]
    axis.bar(np.arange(len(labels)), 100 * by_decade.share, color=BLUE, width=0.62)
    for x, (share, n) in enumerate(zip(by_decade.share, by_decade.n)):
        axis.text(x, 100 * share + 1.2, f"{n:,}", ha="center", fontsize=5.8, color=INK2)
    axis.set_xticks(np.arange(len(labels)), labels, rotation=45, ha="right", fontsize=6.6)
    axis.set_ylabel("Station-years with warm-season gaps (%)")
    axis.set_ylim(0, max(100 * by_decade.share) * 1.2)
    axis.text(0.98, 0.98, "labels: station-years", transform=axis.transAxes, ha="right", va="top", fontsize=5.8, color=INK2)
    axis.grid(axis="x", visible=False)
    panel(axis, "b")
    hot = pd.read_csv(T.OUT / "e1_missingness/hot_summer_incompleteness_by_region.csv")
    wide = hot.pivot(index="region", columns="hot_summer", values="mean").dropna()
    sizes = hot.pivot(index="region", columns="hot_summer", values="size").reindex(wide.index)
    wide = wide.loc[sizes[True] >= 10]
    order = (wide[True] - wide[False]).sort_values().index
    axis = axes[2]
    y = np.arange(len(order))
    axis.scatter(100 * wide.loc[order, False], y, s=14, color=MUTED, label="Other summers", zorder=3)
    axis.scatter(100 * wide.loc[order, True], y, s=14, color=ORANGE, label="Hottest 10% of summers", zorder=3)
    for yy, region in zip(y, order):
        axis.plot([100 * wide.loc[region, False], 100 * wide.loc[region, True]], [yy, yy], color=GRID, lw=1.2, zorder=2)
    axis.set_yticks(y)
    axis.set_yticklabels([r.replace("usgs_huc", "USGS HUC ").replace("gkd_bayern", "Bavaria").replace("nve_hydapi", "NVE").replace("_", " ").upper() if r.startswith("usgs") else {"gkd_bayern": "Bavaria", "nve_hydapi": "NVE", "lubw": "LUBW", "chmi": "CHMI", "arso": "ARSO", "foen": "FOEN", "syke": "SYKE", "hubeau": "Hub'Eau", "rws_waterwebservices": "RWS"}.get(r, r) for r in order], fontsize=6.2)
    axis.set_xlabel("Warm seasons with gaps (%)")
    axis.legend(loc="upper center", bbox_to_anchor=(0.35, -0.2), fontsize=6.2, handletextpad=0.1, ncol=2, columnspacing=0.6)
    axis.grid(axis="y", visible=False)
    panel(axis, "c")
    figure.tight_layout(w_pad=1.2)
    save(figure, "tr_f1_missingness")


def figure2() -> None:
    """E3: the recovery law predicts where the plug-in fails, without fitting any error."""

    cells = pd.read_csv(T.OUT / "e3_recovery_law/cells.csv")
    cells["layer_group"] = cells.layer.where(cells.layer.isin(["air_ridge", "donor_ridge"]), "other")
    reliability = pd.read_csv(T.OUT / "e3_recovery_law/reliability.csv")
    figure, axes = plt.subplots(1, 3, figsize=(7.2, 2.55))
    markers = {30: "o", 60: "s", 90: "^"}
    for axis, (predicted, observed, label, limit) in zip(axes[:2], [("law_pfail", "failure_rate", "failure rate", (0, 0.75)), ("law_v3_bias", "mean_error", "mean signed error (°C)", (-0.9, 0.1))]):
        for layer, colour in LAYER_COLOURS.items():
            block = cells.loc[cells.layer_group.eq(layer)]
            for length, marker in markers.items():
                sub = block.loc[block.gap_length.eq(length)]
                axis.scatter(sub[predicted], sub[observed], s=np.clip(sub.n / 120, 8, 40), marker=marker, facecolor=colour, edgecolor="white", linewidth=0.5, zorder=3, label=f"{LAYER_LABELS[layer]}" if length == 30 else None)
        axis.plot(limit, limit, color=INK2, lw=0.7, zorder=2)
        axis.set_xlim(limit)
        axis.set_ylim(limit)
        axis.set_xlabel(f"Predicted {label}")
        axis.set_ylabel(f"Observed {label}")
    axes[0].set_title("Parametric law (v2)", loc="left", color=INK2)
    axes[1].set_title("Training-year replay (v3)", loc="left", color=INK2)
    explained = pd.read_csv(T.OUT / "e3_recovery_law/summary.csv")
    ev2 = explained.loc[explained.metric.eq("explained_variance_failure_rate_by_law_pfail"), "value"].iloc[0]
    ev3 = explained.loc[explained.metric.eq("explained_variance_mean_error_by_law_v3_bias"), "value"].iloc[0]
    axes[0].text(0.03, 0.97, f"Cell variance explained {100 * ev2:.0f}%", transform=axes[0].transAxes, va="top", fontsize=6.5, color=INK2)
    axes[1].text(0.03, 0.97, f"Cell variance explained {100 * ev3:.0f}%", transform=axes[1].transAxes, va="top", fontsize=6.5, color=INK2)
    from matplotlib.lines import Line2D

    handles = [Line2D([], [], marker="o", ls="", color=colour, ms=5, label=LAYER_LABELS[layer]) for layer, colour in LAYER_COLOURS.items()]
    handles += [Line2D([], [], marker=marker, ls="", color=INK2, ms=4.5, label=f"{length}-day gap") for length, marker in markers.items()]
    axes[0].legend(handles=handles, loc="lower right", fontsize=5.8, handletextpad=0.1, borderaxespad=0.2)
    axis = axes[2]
    for population, colour, label in (("mech", ORANGE, "Controlled gaps"), ("deploy", BLUE, "Real calendars")):
        block = reliability.loc[reliability.population.eq(population) & reliability.version.eq("v2") & reliability.truncated]
        axis.plot(block.predicted, block.observed, "o-", color=colour, ms=4, lw=1.4, label=label)
    axis.plot([0, 0.7], [0, 0.7], color=INK2, lw=0.7)
    axis.set_xlim(0, 0.7)
    axis.set_ylim(0, 0.7)
    axis.set_xlabel("Predicted failure probability (v2)")
    axis.set_ylabel("Observed failure rate")
    axis.legend(loc="upper left", fontsize=6.5)
    for axis, letter in zip(axes, "abc"):
        panel(axis, letter)
    figure.tight_layout(w_pad=1.0)
    save(figure, "tr_f2_recovery_law")


def figure3() -> None:
    """E4: the plug-in is biased cold where the peak is hidden; target-aware estimation removes most of it."""

    cases = source_cases()
    oof = pd.read_parquet(T.OUT / "e4_estimators/oof_predictions.parquet")
    estimators = {
        "Plug-in completion (P0)": (cases.h30__policy, ORANGE),
        "Air2stream-3 (P1)": (cases.h30__air2stream3, YELLOW),
        "Conditional simulation median (P3)": (cases.state_h30_q50, AQUA),
        "Distribution regression (D2*)": (oof.h30__P5b_q50, BLUE),
    }
    hidden = cases.peak_overlap
    bins = pd.cut(hidden, [-0.01, 0.0, 0.25, 0.5, 0.75, 1.0], labels=["0", "0-25", "25-50", "50-75", "75-100"])
    mech = cases.design_family.eq("crossed")
    figure, axes = plt.subplots(1, 3, figsize=(7.2, 2.6), sharey=False)
    for axis, layer, title in ((axes[0], "air_ridge", "Air-temperature layer"), (axes[1], "donor_ridge", "Neighbour layer")):
        selected = mech & cases.policy_choice.eq(layer)
        x = np.arange(len(bins.cat.categories))
        for offset, (name, (values, colour)) in zip(np.linspace(-0.24, 0.24, len(estimators)), estimators.items()):
            error = (values - cases.eval_truth_h30)[selected]
            grouped = error.groupby(bins[selected], observed=False)
            mean = grouped.mean()
            axis.plot(x + offset * 0, mean.to_numpy(), "o-", color=colour, ms=4, lw=1.5, label=name)
        axis.axhline(0, color=INK2, lw=0.7)
        axis.set_xticks(x)
        axis.set_xticklabels(bins.cat.categories, fontsize=6.8)
        axis.set_xlabel("Climatological peak hidden (%)")
        axis.set_title(title, loc="left", color=INK2)
        axis.set_ylim(-0.5, 0.1)
    axes[0].set_ylabel("Mean signed H30 error (°C)")
    axes[1].legend(loc="lower left", fontsize=6.2)
    axis = axes[2]
    levels = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
    for name, prefix, colour in (("Raw residual blocks", "raw", MUTED), ("Seasonal air-state simulation", "state", AQUA), ("Distribution regression (D2*)", "P5b", BLUE)):
        if prefix in ("raw", "state"):
            lower, upper = cases[f"{prefix}_h30_q05"], cases[f"{prefix}_h30_q95"]
        else:
            lower, upper = oof.h30__P5b_q05, oof.h30__P5b_q95
        covered = ((cases.eval_truth_h30 >= lower) & (cases.eval_truth_h30 <= upper)).astype(float)
        mean = covered[mech].groupby(bins[mech], observed=False).mean()
        axis.plot(np.arange(len(mean)), 100 * mean.to_numpy(), "o-", color=colour, ms=4, lw=1.5, label=name)
    axis.axhline(90, color=INK2, lw=0.7, ls="--")
    axis.set_xticks(np.arange(len(bins.cat.categories)))
    axis.set_xticklabels(bins.cat.categories, fontsize=6.8)
    axis.set_xlabel("Climatological peak hidden (%)")
    axis.set_ylabel("Coverage of 90% interval (%)")
    axis.set_ylim(40, 102)
    axis.legend(loc="lower left", fontsize=6.2)
    for axis, letter in zip(axes, "abc"):
        panel(axis, letter)
    figure.tight_layout(w_pad=1.0)
    save(figure, "tr_f3_estimators")


def figure4() -> None:
    """E5/E6: risk-retention against the completeness rules, and the multi-target view."""

    curves = pd.read_parquet(T.OUT / "e5_rules/curves.parquet")
    table = pd.read_csv(T.OUT / "e5_rules/risk_retention.csv")
    figure, axes = plt.subplots(2, 2, figsize=(7.2, 5.6))
    short = {
        "R1_usgs_indicator_311d_24pm": ("USGS 311 d", (-16, 8)), "R1_wmo_11_5": ("WMO 11/5", (-14, 8)), "R1_etccdi_15_3": ("ETCCDI", (2, 6)),
        "R1_gsim_350d": ("GSIM", (-4, 8)), "R1_michel_no_gap_over_14d": ("14-d gap", (-34, 3)), "R1_johnson_gap_le_49d": ("7-week gap", (3, 3)),
        "R2_oregon_jas_80pct": ("Oregon", (-4, 7)), "R2_norwest_aug_90pct": ("NorWeST", (-36, 4)), "R2_beaufort_julaug_complete": ("Jul-Aug", (-30, -3)),
        "R2_warm_gap_le_14d": ("Warm gap ≤14 d", (-62, -4)),
    }
    lines = (
        (("R7a_target_aware_pfail (D2* distribution)", "D2*"), BLUE, "Target-aware score, D2* value"),
        (("R6_recovery_law_pfail", "P0"), AQUA, "Recovery law, plug-in value"),
        (("R5_h30_target_disagreement", "P0"), YELLOW, "H30 disagreement, plug-in value"),
        (("R2_warm_missing_fraction", "P0"), ORANGE, "Warm-season completeness, plug-in value"),
    )
    for axis, population, title, ylim, xlim in ((axes[0, 0], "deploy", "Real gap calendars", 4.0, (30, 100)), (axes[0, 1], "mech", "Controlled 30-90 day gaps", 18.0, (0, 100))):
        for (score, delivered), colour, label in lines:
            block = curves.loc[curves.population.eq(population) & curves.rule.eq(score) & curves.delivered.eq(delivered)]
            axis.plot(100 * block.coverage, 100 * block.risk, color=colour, lw=1.6, label=label)
        fixed = table.loc[table.population.eq(population) & table.kind.eq("fixed") & table.delivered.eq("Pobs")]
        for _, row in fixed.iterrows():
            if row.rule not in short or not np.isfinite(row.risk) or row.retention <= 0:
                continue
            number = list(short).index(row.rule) + 1
            axis.scatter(100 * row.retention, 100 * row.risk, s=14, color=INK2, zorder=4)
            if row.risk * 100 <= ylim:
                axis.annotate(str(number), (100 * row.retention, 100 * row.risk), xytext=(2, 3), textcoords="offset points", fontsize=5.6, color=INK2)
        axis.axhline(5, color=INK2, lw=0.7, ls="--")
        axis.set_xlim(*xlim)
        axis.set_ylim(0, ylim)
        axis.set_xlabel("Incomplete station-years used (%)")
        axis.set_ylabel("Used values outside 0.5 °C (%)")
        axis.set_title(title, loc="left", color=INK2)
    axes[0, 0].legend(loc="upper left", fontsize=5.8)
    key = "\n".join(f"{i + 1}  {text}" for i, (text, _) in enumerate(short.values()))
    axes[0, 0].text(0.03, 0.58, "Published rules\n" + key, transform=axes[0, 0].transAxes, va="top", fontsize=5.4, color=INK2, linespacing=1.25)
    axes[0, 1].text(0.02, 0.97, "Grey points: published rules,\nvalue computed from recorded days", transform=axes[0, 1].transAxes, va="top", fontsize=6.0, color=INK2)
    frontier = pd.read_csv(T.OUT / "e6_multitarget/target_frontier.csv")
    names = {"h30": "H30", "h7": "H7", "annual_mean": "Annual mean", "c30": "C30", "degree_days_jjas": "Jun-Sep degree-days", "days_above_20": "Days >20 °C"}
    own = frontier.loc[frontier.population.eq("mech")].set_index("target")
    by_h30 = frontier.loc[frontier.population.eq("mech|scored_by_h30")].set_index("target")
    axis = axes[1, 0]
    order = list(names)
    y = np.arange(len(order))[::-1]
    for values, colour, label in ((own.best_rule_retention_at_5pct, ORANGE, "Best completeness rule"), (by_h30.target_aware_retention_at_5pct, AQUA, "Admitted by the H30 score"), (own.target_aware_retention_at_5pct, BLUE, "Admitted by the target's own score")):
        axis.scatter(100 * values.reindex(order), y, s=18, color=colour, label=label, zorder=3)
    for yy, target in zip(y, order):
        axis.plot([100 * own.best_rule_retention_at_5pct[target], 100 * own.target_aware_retention_at_5pct[target]], [yy, yy], color=GRID, lw=1.2, zorder=2)
    axis.set_yticks(y, [names[t] for t in order], fontsize=6.6)
    axis.set_xlim(20, 102)
    axis.set_ylim(-1.9, len(order) - 0.5)
    axis.set_xlabel("Used at 5% realised risk, controlled gaps (%)")
    axis.legend(loc="lower right", fontsize=5.8, ncol=1, borderaxespad=0.1)
    axis.grid(axis="y", visible=False)
    agreement = pd.read_csv(T.OUT / "e6_multitarget/target_agreement.csv")
    agreement = agreement.loc[agreement.population.eq("mech")]
    matrix = np.full((len(order), len(order)), np.nan)
    for _, row in agreement.iterrows():
        i, j = sorted((order.index(row.target_a), order.index(row.target_b)), reverse=True)
        matrix[i, j] = row.kappa_usable
    axis = axes[1, 1]
    colours = matplotlib.colors.LinearSegmentedColormap.from_list("blue", ["#f0efec", "#86b6ef", "#1c5cab"])
    axis.imshow(np.ma.masked_invalid(matrix), cmap=colours, vmin=0, vmax=1)
    for i in range(len(order)):
        for j in range(i):
            axis.text(j, i, f"{matrix[i, j]:.2f}", ha="center", va="center", fontsize=6.4, color=INK if matrix[i, j] < 0.6 else "white")
    labels = ["H30", "H7", "Mean", "C30", "Degree-days", "Days >20"]
    axis.set_xticks(range(len(order) - 1), labels[:-1], fontsize=6.4, rotation=30, ha="right")
    axis.set_yticks(range(1, len(order)), labels[1:], fontsize=6.4)
    axis.set_xlim(-0.5, len(order) - 1.5)
    axis.set_ylim(len(order) - 0.5, 0.5)
    axis.grid(False)
    axis.spines["left"].set_visible(False)
    axis.spines["bottom"].set_visible(False)
    axis.set_title("Agreement on usability (Cohen's κ), controlled gaps", loc="left", color=INK2)
    for axis, letter in zip(axes.ravel(), "abcd"):
        panel(axis, letter)
    figure.tight_layout(h_pad=1.6, w_pad=1.6)
    save(figure, "tr_f4_rules")


REGION_NAMES = {"gkd_bayern": "Bavaria", "nve_hydapi": "NVE", "lubw": "LUBW", "chmi": "CHMI", "arso": "ARSO", "foen": "FOEN", "syke": "SYKE", "hubeau": "Hub'Eau", "rws_waterwebservices": "RWS"}


def region_label(region: str) -> str:
    return region.replace("usgs_huc", "USGS HUC ") if region.startswith("usgs") else REGION_NAMES.get(region, region)


def figure5() -> None:
    """E7: transfer of calibrated thresholds to held-out regions and to the sealed Australian test."""

    loro = pd.read_csv(T.OUT / "e7_transfer/loro_transfer.csv")
    sealed = pd.read_csv(T.OUT / "e7_sealed/sealed_frozen_thresholds.csv")
    expected = pd.read_csv(T.OUT / "e7_transfer/expected_risk_threshold.csv")
    figure, axes = plt.subplots(1, 3, figsize=(7.4, 3.3), gridspec_kw={"width_ratios": [1.15, 1.15, 0.9]})
    for axis, population, title in ((axes[0], "mech", "Controlled 30-90 day gaps"), (axes[1], "deploy", "Real gap calendars")):
        block = loro.loc[loro.population.eq(population) & loro.score.eq("R7a_target_aware") & loro.method.isin(["marginal", "mondrian_layer"])]
        wide = block.pivot_table(index="region", columns="method", values="risk")
        order = list(wide.mondrian_layer.sort_values().index)
        y = np.arange(len(order))
        axis.scatter(100 * wide.loc[order, "marginal"], y, s=13, color=MUTED, label="One threshold", zorder=3)
        axis.scatter(100 * wide.loc[order, "mondrian_layer"], y, s=13, color=BLUE, label="One threshold per layer", zorder=3)
        frozen = sealed.loc[sealed.population.eq(population) & sealed.score.eq("R7a_target_aware")].set_index("method")
        yy = len(order) + 0.9
        for method, colour in (("marginal", MUTED), ("mondrian_layer", BLUE)):
            row = frozen.loc[method]
            axis.errorbar(100 * row.risk, yy, xerr=[[100 * (row.risk - row.risk_lower95)], [100 * (row.risk_upper95 - row.risk)]], fmt="D", ms=4.2, color=colour, elinewidth=1.0, capsize=0, zorder=4)
        post = expected.loc[expected.domain.eq("australia_post_hoc") & expected.population.eq(population) & expected.score.eq("R7a")]
        if len(post):
            axis.scatter(100 * post.risk.iloc[0], yy + 0.9, s=22, marker="D", facecolor="white", edgecolor=AQUA, linewidth=1.3, zorder=4, label="Expected-risk threshold (post hoc)")
        axis.set_yticks(np.r_[y, yy, yy + 0.9], [region_label(r) for r in order] + ["Australia, frozen", "Australia, post hoc"], fontsize=5.9)
        axis.axvline(5, color=INK2, lw=0.7, ls="--")
        axis.axvline(7, color=MUTED, lw=0.7, ls=":")
        axis.set_xlabel("Realised risk at nominal 5% (%)")
        axis.set_title(title, loc="left", color=INK2)
        axis.grid(axis="y", visible=False)
    axes[0].set_xlim(0, 22)
    axes[1].set_xlim(0, 17)
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.36, -0.06), ncol=3, fontsize=6.2)
    curve = pd.read_csv(T.OUT / "e7_transfer/local_recalibration_curve.csv")
    curve = curve.loc[curve.population.eq("mech") & curve.score.eq("R7a_target_aware")]
    axis = axes[2]
    for scheme, colour, label in (("local_only_mondrian", ORANGE, "Local blocks only"), ("pooled_upweighted_mondrian", BLUE, "Source + local blocks")):
        sub = curve.loc[curve.scheme.eq(scheme)].sort_values("k")
        axis.plot(sub.k, 100 * sub.p_risk_le_7pct, "o-", color=colour, ms=4, lw=1.5, label=label)
    axis.set_xscale("log", base=2)
    axis.set_xticks([2, 4, 8, 16], ["2", "4", "8", "16"])
    axis.set_xlabel("Local calibration blocks")
    axis.set_ylabel("Repeats with risk ≤ 7% (%)")
    axis.set_ylim(0, 105)
    axis.set_title("Controlled gaps", loc="left", color=INK2)
    axis.legend(loc="lower right", fontsize=5.9)
    for axis, letter in zip(axes, "abc"):
        panel(axis, letter)
    figure.tight_layout(w_pad=1.0)
    save(figure, "tr_f5_transfer")


def figure6() -> None:
    """E8/E9: the handling of incomplete years changes station trends, hot-year counts and regional records."""

    summary = pd.read_csv(T.OUT / "e8_downstream/summary.csv")
    names = {"A0": "Drop every incomplete year", "A1": "Keep if ≥90% of warm season", "B": "Keep all, plug-in value", "C": "Keep all, D2* multiple imputation"}
    colours = {"A0": MUTED, "A1": ORANGE, "B": YELLOW, "C": BLUE}
    scenarios = ["mcar", "realistic_trend", "mnar1", "mnar2"]
    scenario_labels = ["Random", "Trend", "Trend +\nstate", "Trend +\nstate ×2"]
    figure, axes = plt.subplots(2, 2, figsize=(7.2, 5.4))
    for axis, metric, label in ((axes[0, 0], "slope_rmse", "Trend RMSE vs complete record\n(°C per decade)"), (axes[0, 1], "slope_bias", "Trend bias (°C per decade)")):
        x = np.arange(len(scenarios))
        for offset, pipeline in zip(np.linspace(-0.24, 0.24, len(names)), names):
            values = [summary.loc[(summary.scenario == s) & (summary.pipeline == pipeline), metric].iloc[0] for s in scenarios]
            axis.plot(x + offset, values, "o", ms=4.5, color=colours[pipeline], label=names[pipeline])
        axis.set_xticks(x, scenario_labels, fontsize=6.6)
        axis.set_xlabel("How years become incomplete")
        axis.set_ylabel(label)
        axis.grid(axis="x", visible=False)
    axes[0, 0].set_yscale("log")
    axes[0, 0].set_ylim(0.005, 0.4)
    axes[0, 1].axhline(0, color=INK2, lw=0.7)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    figure.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 1.035), ncol=4, fontsize=6.2, columnspacing=1.0, handletextpad=0.2)
    axis = axes[1, 0]
    block = summary.loc[summary.scenario.eq("mnar1")].set_index("pipeline").reindex(list(names))
    missed = 100 * block.hot_missed_incomplete / block.hot_true_incomplete
    unknown = 100 * block.hot_unknown_incomplete / block.hot_true_incomplete
    y = np.arange(len(names))[::-1]
    axis.barh(y, missed - unknown, color=[colours[p] for p in names], height=0.58, label="Value below the hot threshold")
    axis.barh(y, unknown, left=missed - unknown, color=[colours[p] for p in names], alpha=0.35, height=0.58, label="Year dropped, no value")
    for yy, value in zip(y, missed):
        axis.text(value + 1.5, yy, f"{value:.0f}%", va="center", fontsize=6.2, color=INK2)
    axis.set_yticks(y, list(names.values()), fontsize=6.3)
    axis.set_xlim(0, 112)
    axis.set_xlabel("Truly hot incomplete years missed (%)")
    axis.legend(loc="lower right", fontsize=5.9)
    axis.grid(axis="y", visible=False)
    series = pd.read_parquet(T.OUT / "e9_application/station_series.parquet")
    lubw = series.loc[series.region.eq("lubw")].copy()
    lubw["anomaly"] = lubw.h30 - lubw.groupby("station_key").h30.transform("mean")
    complete_only = lubw.loc[lubw.kind.eq("complete")].groupby("year").anomaly.agg(["mean", "size"])
    everything = lubw.groupby("year").anomaly.agg(["mean", "size"])
    axis = axes[1, 1]
    axis.plot(everything.index, everything["mean"], "o-", color=BLUE, ms=3.2, lw=1.2, label="Incomplete years included (D2*)")
    axis.plot(complete_only.index, complete_only["mean"], "o", color=ORANGE, ms=3.2, label="Complete years only")
    for year in (2003, 2018):
        if year in everything.index:
            axis.annotate(f"{year}: {int(complete_only['size'].get(year, 0))} of {int(everything.loc[year, 'size'])} stations complete", (year, everything.loc[year, "mean"]), xytext=(9, -3) if year == 2003 else (-70, 16), textcoords="offset points", fontsize=5.8, color=INK2, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.6))
    axis.axhline(0, color=INK2, lw=0.6)
    axis.set_xlabel("Year")
    axis.set_ylabel("Regional mean H30 anomaly (°C)")
    axis.set_title("Baden-Württemberg (LUBW) archive", loc="left", color=INK2)
    axis.legend(loc="lower right", fontsize=5.9)
    for axis, letter in zip(axes.ravel(), "abcd"):
        panel(axis, letter)
    figure.tight_layout(h_pad=1.6, w_pad=1.6)
    save(figure, "tr_f6_downstream")


def main() -> int:
    import sys

    selected = sys.argv[1:] or ["1", "2", "3", "4", "5", "6"]
    for name in selected:
        globals()[f"figure{name}"]()
        print(f"[444] figure {name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
