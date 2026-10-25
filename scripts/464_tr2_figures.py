#!/usr/bin/env python3
"""TR2 figures 1-7 for the revised manuscript, from the result tables.

Round-2 counterpart of script 444, with the same fixed colour assignment
(target-aware = blue, plug-in and current practice = orange, recovery law =
aqua, a fourth method = yellow, rules neutral grey). Figure 1 reads the
round-1 missingness audit; figures 3-7 use the corrected definitions, the
calibrated D2*, the label-free rule (R7b primary), the second test, the
decomposition of the downstream gain and the 7-day minimum flow.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

import wrr_tr_common as T

F444 = T.load_script("tr_figures_round1", T.ROOT / "scripts/444_tr_figures.py")
BLUE, ORANGE, AQUA, YELLOW, MUTED, INK, INK2, GRID = F444.BLUE, F444.ORANGE, F444.AQUA, F444.YELLOW, F444.MUTED, F444.INK, F444.INK2, F444.GRID
save, panel, region_label = F444.save, F444.panel, F444.region_label
BINS = [-0.01, 0.0, 0.25, 0.5, 0.75, 1.0]
BIN_LABELS = ["0", "0-25", "25-50", "50-75", "75-100"]


def source_cases() -> pd.DataFrame:
    return F444.source_cases()


def figure1() -> None:
    """E1 is unchanged by the season definitions; it is drawn from the round-1 audit."""

    # Script 444 reads the audit from T.OUT; the shared module is pointed at round 1 for this figure only.
    original = T.OUT
    try:
        T.OUT = T.ROUND1
        F444.figure1()
    finally:
        T.OUT = original


def figure2() -> None:
    """E3: the parametric law (v2) and the training-year replay, which is an empirical comparator."""

    cells = pd.read_csv(T.OUT / "e3_recovery_law/cells.csv")
    cells["layer_group"] = cells.layer.where(cells.layer.isin(["air_ridge", "donor_ridge"]), "other")
    reliability = pd.read_csv(T.OUT / "e3_recovery_law/reliability.csv")
    explained = pd.read_csv(T.OUT / "e3_recovery_law/summary.csv")
    figure, axes = plt.subplots(1, 3, figsize=(7.2, 2.55))
    markers = {30: "o", 60: "s", 90: "^"}
    for axis, (predicted, observed, label, limit) in zip(axes[:2], [("law_pfail", "failure_rate", "failure rate", (0, 0.75)), ("law_v3_bias", "mean_error", "mean signed error (°C)", (-0.9, 0.1))]):
        for layer, colour in F444.LAYER_COLOURS.items():
            block = cells.loc[cells.layer_group.eq(layer)]
            for length, marker in markers.items():
                sub = block.loc[block.gap_length.eq(length)]
                axis.scatter(sub[predicted], sub[observed], s=np.clip(sub.n / 120, 8, 40), marker=marker, facecolor=colour, edgecolor="white", linewidth=0.5, zorder=3)
        axis.plot(limit, limit, color=INK2, lw=0.7, zorder=2)
        axis.set_xlim(limit)
        axis.set_ylim(limit)
        axis.set_xlabel(f"Predicted {label}")
        axis.set_ylabel(f"Observed {label}")
    axes[0].set_title("Parametric law (v2)", loc="left", color=INK2)
    axes[1].set_title("Training-year replay (empirical comparator)", loc="left", color=INK2)
    ev2 = explained.loc[explained.metric.eq("explained_variance_failure_rate_by_law_pfail"), "value"].iloc[0]
    ev3 = explained.loc[explained.metric.eq("explained_variance_mean_error_by_law_v3_bias"), "value"].iloc[0]
    axes[0].text(0.03, 0.97, f"Cell variance explained {100 * ev2:.0f}%", transform=axes[0].transAxes, va="top", fontsize=6.5, color=INK2)
    axes[1].text(0.03, 0.97, f"Cell variance explained {100 * ev3:.0f}%", transform=axes[1].transAxes, va="top", fontsize=6.5, color=INK2)
    handles = [Line2D([], [], marker="o", ls="", color=colour, ms=5, label=F444.LAYER_LABELS[layer]) for layer, colour in F444.LAYER_COLOURS.items()]
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
    """E4: cold bias of the plug-in, and the coverage of calibrated D2* intervals by decision-time difficulty."""

    cases = source_cases()
    oof = pd.read_parquet(T.OUT / "e4_estimators/oof_predictions.parquet")
    calibrated = pd.read_parquet(T.OUT / "e4_estimators/oof_calibrated.parquet")
    estimators = {
        "Plug-in completion (P0)": (cases.h30__policy, ORANGE),
        "Air2stream-3 (P1)": (cases.h30__air2stream3, YELLOW),
        "Conditional simulation median (P3)": (cases.state_h30_q50, AQUA),
        "Distribution regression (D2*)": (calibrated.h30__D2c_q50, BLUE),
    }
    bins = pd.cut(cases.peak_overlap, BINS, labels=BIN_LABELS)
    mech = cases.design_family.eq("crossed")
    figure, axes = plt.subplots(1, 3, figsize=(7.2, 2.6))
    x = np.arange(len(BIN_LABELS))
    for axis, layer, title in ((axes[0], "air_ridge", "Air-temperature layer"), (axes[1], "donor_ridge", "Neighbour layer")):
        selected = mech & cases.policy_choice.eq(layer)
        for name, (values, colour) in estimators.items():
            error = (values - cases.eval_truth_h30)[selected]
            axis.plot(x, error.groupby(bins[selected], observed=False).mean().to_numpy(), "o-", color=colour, ms=4, lw=1.5, label=name)
        axis.axhline(0, color=INK2, lw=0.7)
        axis.set_xticks(x, BIN_LABELS, fontsize=6.8)
        axis.set_xlabel("Climatological peak hidden (%)")
        axis.set_title(title, loc="left", color=INK2)
        axis.set_ylim(-0.5, 0.1)
    axes[0].set_ylabel("Mean signed H30 error (°C)")
    axes[1].legend(loc="lower left", fontsize=6.2)
    axis = axes[2]
    axis.axhspan(85, 95, color=GRID, zorder=0)
    for name, lower, upper, colour, style in (
        ("Seasonal air-state simulation", cases.state_h30_q05, cases.state_h30_q95, AQUA, "-"),
        ("D2* before calibration", oof.h30__P5b_q05, oof.h30__P5b_q95, MUTED, "--"),
        ("D2* calibrated (approximate)", calibrated.h30__D2c_q05, calibrated.h30__D2c_q95, BLUE, "-"),
    ):
        covered = ((cases.eval_truth_h30 >= lower) & (cases.eval_truth_h30 <= upper)).astype(float)
        axis.plot(x, 100 * covered[mech].groupby(bins[mech], observed=False).mean().to_numpy(), "o" + style, color=colour, ms=4, lw=1.5, label=name)
    axis.axhline(90, color=INK2, lw=0.7, ls="--")
    axis.set_xticks(x, BIN_LABELS, fontsize=6.8)
    axis.set_xlabel("Climatological peak hidden (%)")
    axis.set_ylabel("Coverage of 90% interval (%)")
    axis.set_ylim(40, 102)
    axis.text(len(BIN_LABELS) - 1, 95.6, "85-95%", ha="right", va="bottom", fontsize=6.0, color=INK2)
    axis.legend(loc="lower left", fontsize=6.0)
    for axis, letter in zip(axes, "abc"):
        panel(axis, letter)
    figure.tight_layout(w_pad=1.0)
    save(figure, "tr_f3_estimators")


def figure4() -> None:
    """E5/E6 with R7b as the target-aware judgment (R7a is the comparator in Table S7)."""

    lines = (
        (("R7b_direct_failure_probability (D2*)", "D2*"), BLUE, "Target-aware judgment (R7b), D2* value"),
        (("R6_recovery_law_pfail", "P0"), AQUA, "Recovery law, plug-in value"),
        (("R5_h30_target_disagreement", "P0"), YELLOW, "H30 disagreement, plug-in value"),
        (("R2_warm_missing_fraction", "P0"), ORANGE, "Warm-season completeness, plug-in value"),
    )
    curves = pd.read_parquet(T.OUT / "e5_rules/curves.parquet")
    table = pd.read_csv(T.OUT / "e5_rules/risk_retention.csv")
    figure, axes = plt.subplots(2, 2, figsize=(7.2, 5.6))
    short = {
        "R1_usgs_indicator_311d_24pm": "USGS 311 d", "R1_wmo_11_5": "WMO 11/5", "R1_etccdi_15_3": "ETCCDI", "R1_gsim_350d": "GSIM",
        "R1_michel_no_gap_over_14d": "14-d gap", "R1_johnson_gap_le_49d": "7-week gap", "R2_oregon_jas_80pct": "Peak months 80%",
        "R2_norwest_aug_90pct": "Peak month 90%", "R2_beaufort_julaug_complete": "Two peak months", "R2_warm_gap_le_14d": "Warm gap ≤14 d",
    }
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
    key = "\n".join(f"{i + 1}  {text}" for i, text in enumerate(short.values()))
    axes[0, 0].text(0.03, 0.58, "Published rules\n" + key, transform=axes[0, 0].transAxes, va="top", fontsize=5.4, color=INK2, linespacing=1.25)
    axes[0, 1].text(0.02, 0.97, "Grey points: published rules,\nvalue computed from recorded days", transform=axes[0, 1].transAxes, va="top", fontsize=6.0, color=INK2)
    frontier = pd.read_csv(T.OUT / "e6_multitarget/target_frontier.csv")
    names = {"h30": "H30", "h7": "H7", "annual_mean": "Annual mean", "c30": "C30", T.DEGREE_DAYS: "Degree-days (4 hottest months)", "days_above_20": "Days >20 °C"}
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


def figure5() -> None:
    """Transfer: the label-free rule in held-out source regions, in Australia and in the second test."""

    development = pd.read_csv(T.OUT / "e7_transfer/expected_risk_development.csv")
    first = pd.read_csv(T.AU_ROUND1 / "sealed_frozen_thresholds.csv")
    au_dev = pd.read_csv(T.OUT / "e7_au_development/development_check.csv")
    sealed = pd.read_csv(T.OUT / "e10_sealed_usgs/sealed_expected_risk.csv")
    local = pd.read_csv(T.OUT / "e10_sealed_usgs/sealed_local_calibration.csv")
    figure, axes = plt.subplots(1, 3, figsize=(7.4, 3.4), gridspec_kw={"width_ratios": [1.15, 1.15, 0.9]})
    for axis, population, title in ((axes[0], "mech", "Controlled 30-90 day gaps"), (axes[1], "deploy", "Real gap calendars")):
        block = development.loc[development.population.eq(population) & development.score.eq("R7b")].set_index("region")
        order = list(block.risk.sort_values().index)
        y = np.arange(len(order))
        axis.scatter(100 * block.loc[order, "k1_risk"], y, s=13, color=MUTED, label="Label-free rule, k = 1", zorder=3)
        axis.scatter(100 * block.loc[order, "risk"], y, s=13, color=BLUE, label="Label-free rule with factor k", zorder=3)
        extra = []
        row = first.loc[first.population.eq(population) & first.score.eq("R7a_target_aware") & first.method.eq("mondrian_layer")].iloc[0]
        extra.append(("Australia, fixed thresholds (test 1)", row.risk, row.risk_lower95, row.risk_upper95, ORANGE, "D", True))
        row = au_dev.loc[au_dev.population.eq(population) & au_dev.score.eq("R7b") & au_dev.factor.eq("k")].iloc[0]
        extra.append(("Australia, label-free (post hoc)", row.risk, np.nan, row.risk_upper95, BLUE, "D", False))
        row = sealed.loc[sealed.population.eq(population) & sealed.score.eq("R7b") & sealed.factor.eq("k")].iloc[0]
        extra.append(("New USGS stations (test 2)", row.risk, row.risk_lower95, row.risk_upper95, BLUE, "*", True))
        ticks = list(y)
        for offset, (label, risk, low, high, colour, marker, filled) in enumerate(extra):
            yy = len(order) + 0.6 + 1.0 * offset
            ticks.append(yy)
            lower = 100 * (risk - low) if np.isfinite(low) else 0
            axis.errorbar(100 * risk, yy, xerr=[[lower], [100 * (high - risk)]], fmt=marker, ms=6 if marker == "*" else 4.2, color=colour, mfc=colour if filled else "white", mec=colour, elinewidth=1.0, capsize=0, zorder=4)
        axis.set_yticks(ticks, [region_label(r) for r in order] + [e[0] for e in extra], fontsize=5.8)
        axis.axvline(5, color=INK2, lw=0.7, ls="--")
        axis.axvline(7, color=MUTED, lw=0.7, ls=":")
        axis.set_xlabel("Realised risk among admitted cases (%)")
        axis.set_title(title, loc="left", color=INK2)
        axis.grid(axis="y", visible=False)
    axes[0].set_xlim(0, 20)
    axes[1].set_xlim(0, 15)
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.36, -0.05), ncol=2, fontsize=6.2)
    axis = axes[2]
    for population, colour, label in (("mech", ORANGE, "Controlled gaps"), ("deploy", BLUE, "Real calendars")):
        sub = local.loc[local.population.eq(population)].sort_values("m")
        axis.plot(sub.m, 100 * sub.share_risk_le_7pct, "o-", color=colour, ms=4, lw=1.5, label=label)
    axis.axhline(80, color=MUTED, lw=0.7, ls=":")
    axis.set_xscale("log", base=2)
    axis.set_xticks([2, 4, 8, 16], ["2", "4", "8", "16"])
    axis.set_xlabel("Labelled local groups")
    axis.set_ylabel("Repeats with risk ≤ 7% (%)")
    axis.set_ylim(0, 105)
    axis.set_title("New USGS stations", loc="left", color=INK2)
    axis.legend(loc="lower right", fontsize=5.9)
    for axis, letter in zip(axes, "abc"):
        panel(axis, letter)
    figure.tight_layout(w_pad=1.0)
    save(figure, "tr_f5_transfer")


def figure6() -> None:
    """E8/E9: where the trend gain comes from, and the Baden-Wuerttemberg record."""

    summary = pd.read_csv(T.OUT / "e8_downstream/summary.csv")
    stations = pd.read_csv(T.OUT / "e8_downstream/decomposition_station_ratios_mnar1.csv")
    bins = pd.read_csv(T.OUT / "e8_downstream/decomposition_by_incomplete_years.csv")
    series = pd.read_csv(T.OUT / "e9_application/bw_anomaly_series.csv").set_index("year")
    names = {"A0": "Drop every incomplete year", "A1": "Keep if ≥90% of warm season", "B": "Keep all, plug-in value", "C": "Keep all, D2* multiple imputation"}
    colours = {"A0": MUTED, "A1": ORANGE, "B": YELLOW, "C": BLUE}
    scenarios = ["mcar", "realistic_trend", "mnar1", "mnar2"]
    figure, axes = plt.subplots(2, 2, figsize=(7.2, 5.4))
    axis = axes[0, 0]
    x = np.arange(len(scenarios))
    for offset, pipeline in zip(np.linspace(-0.24, 0.24, len(names)), names):
        values = [summary.loc[(summary.scenario == s) & (summary.pipeline == pipeline), "slope_rmse"].iloc[0] for s in scenarios]
        axis.plot(x + offset, values, "o", ms=4.5, color=colours[pipeline], label=names[pipeline])
    axis.set_xticks(x, ["Random", "Trend", "Trend +\nstate", "Trend +\nstate ×2"], fontsize=6.6)
    axis.set_xlabel("How years become incomplete")
    axis.set_ylabel("Trend RMSE vs complete record\n(°C per decade)")
    axis.set_yscale("log")
    axis.set_ylim(0.005, 0.4)
    axis.grid(axis="x", visible=False)
    handles, labels = axis.get_legend_handles_labels()
    figure.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 1.035), ncol=4, fontsize=6.2, columnspacing=1.0, handletextpad=0.2)
    axis = axes[0, 1]
    rng = np.random.default_rng(1)
    for position, (column, colour, label) in enumerate((("ratio_B_A1", YELLOW, "Keeping years\n(B / A1)"), ("ratio_C_B", BLUE, "Estimator\n(C / B)"))):
        values = stations[column].dropna().to_numpy()
        axis.scatter(position + rng.uniform(-0.12, 0.12, len(values)), values, s=10, color=colour, alpha=0.8, zorder=3)
        quartiles = np.quantile(values, [0.25, 0.5, 0.75])
        axis.plot([position - 0.22, position + 0.22], [quartiles[1]] * 2, color=INK, lw=1.4, zorder=4)
        axis.plot([position, position], [quartiles[0], quartiles[2]], color=INK, lw=1.0, zorder=4)
    axis.axhline(1, color=INK2, lw=0.7)
    axis.set_yscale("log")
    axis.set_xticks([0, 1], ["Keeping years\n(B / A1)", "Estimator\n(C / B)"], fontsize=6.6)
    axis.set_xlim(-0.6, 1.6)
    axis.set_ylabel("Station trend RMSE ratio")
    axis.set_title("Fitted state-dependent scenario", loc="left", color=INK2)
    axis.grid(axis="x", visible=False)
    axis = axes[1, 0]
    block = bins.loc[bins.scenario.eq("mnar1") & bins.n_incomplete.ne("0")]
    x = np.arange(len(block))
    for pipeline in ("A1", "B", "C"):
        axis.plot(x, block[f"rmse_{pipeline}"], "o-", color=colours[pipeline], ms=4, lw=1.4, label=names[pipeline])
    axis.set_xticks(x, [label.replace(">=", "≥") for label in block.n_incomplete], fontsize=6.6)
    axis.set_xlabel("Years made incomplete in the record")
    axis.set_ylabel("Trend RMSE (°C per decade)")
    axis.set_yscale("log")
    axis.grid(axis="x", visible=False)
    axis = axes[1, 1]
    axis.plot(series.index, series.C_all_years_D2_median, "o-", color=BLUE, ms=3.0, lw=1.2, label="All years (D2* for incomplete years)")
    axis.plot(series.index, series.A0_complete_years, "o", color=ORANGE, ms=3.2, label="Complete years only")
    if 2003 in series.index:
        complete = int(series.loc[2003, "complete"]) if np.isfinite(series.loc[2003, "complete"]) else 0
        stations_2003 = complete + int(series.loc[2003, "incomplete"])
        axis.annotate(f"2003: {complete} of {stations_2003} stations complete", (2003, series.loc[2003, "C_all_years_D2_median"]), xytext=(8, -4), textcoords="offset points", fontsize=5.8, color=INK2, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.6))
    axis.axhline(0, color=INK2, lw=0.6)
    axis.set_xlabel("Year")
    axis.set_ylabel("Regional H30 anomaly (°C)\nstation and year effects")
    axis.set_title("Baden-Württemberg, same 19 stations", loc="left", color=INK2)
    axis.legend(loc="lower right", fontsize=5.9)
    for axis, letter in zip(axes.ravel(), "abcd"):
        panel(axis, letter)
    figure.tight_layout(h_pad=1.6, w_pad=1.6)
    save(figure, "tr_f6_downstream")


def figure7() -> None:
    """S1: the same mechanism for the annual 7-day minimum flow."""

    cases = pd.read_parquet(T.OUT / "s1_flow/case_predictions.parquet")
    curves = pd.read_csv(T.OUT / "s1_flow/rule_curves.csv")
    rules = pd.read_csv(T.OUT / "s1_flow/rules.csv")
    trend = pd.read_csv(T.OUT / "s1_flow/trend_summary.csv").set_index("pipeline")
    tolerance = pd.read_json(T.OUT / "s1_flow/summary.json", typ="series")["tolerance_percent"]
    figure, axes = plt.subplots(1, 3, figsize=(7.2, 2.6), gridspec_kw={"width_ratios": [1.1, 1.1, 0.8]})
    axis = axes[0]
    deploy = cases.loc[cases.design_family.eq("calendar")]
    bins = pd.cut(deploy.lowflow_overlap, BINS, labels=BIN_LABELS)
    x = np.arange(len(BIN_LABELS))
    for column, colour, label in (("plugin_log7q", ORANGE, "Plug-in completion"), ("recorded_log7q", MUTED, "Recorded days only"), ("d2_log7q", BLUE, "Target-aware estimate")):
        # Geometric-mean relative error, the measure quoted in the text.
        error = deploy[column] - deploy.truth_log7q
        axis.plot(x, 100 * np.expm1(error.groupby(bins, observed=False).mean().to_numpy()), "o-", color=colour, ms=4, lw=1.5, label=label)
    axis.axhline(0, color=INK2, lw=0.7)
    axis.set_xticks(x, BIN_LABELS, fontsize=6.8)
    axis.set_xlabel("Climatological low-flow window hidden (%)")
    axis.set_ylabel("Geometric-mean error of 7Q (%)")
    axis.set_title("Real gap calendars", loc="left", color=INK2)
    axis.legend(loc="upper left", fontsize=6.0)
    axis = axes[1]
    deploy_curves = curves.loc[curves.population.eq("deploy")]
    for (rule, delivered), colour, label in (
        (("target-aware failure probability", "D2"), BLUE, "Target-aware judgment"),
        (("low-flow window hidden", "recorded"), YELLOW, "Low-flow window hidden"),
        (("missing fraction", "recorded"), ORANGE, "Missing fraction"),
    ):
        block = deploy_curves.loc[deploy_curves.rule.eq(rule) & deploy_curves.delivered.eq(delivered)]
        axis.plot(100 * block.coverage, 100 * block.risk, color=colour, lw=1.6, label=label)
    fixed = rules.loc[rules.population.eq("deploy") & rules.kind.eq("fixed") & rules.delivered.eq("recorded")]
    numbers = {"SWToolbox (no missing day)": "1", "at least 90% of days": "2", "low-flow window complete": "3"}
    for _, row in fixed.iterrows():
        x_point, y_point = (100 * row.retention, 100 * row.risk) if row.retention > 0 else (0.0, 0.0)
        axis.scatter(x_point, y_point, s=16, color=INK2, zorder=4, clip_on=False)
        axis.annotate(numbers.get(row.rule, "?"), (x_point, y_point), xytext=(2, 4), textcoords="offset points", fontsize=5.8, color=INK2)
    axis.text(0.03, 0.66, "Fixed rules, recorded-day value\n1  SWToolbox: no incomplete year\n2  At least 90% of days\n3  Low-flow window complete", transform=axis.transAxes, va="top", fontsize=5.5, color=INK2, linespacing=1.3)
    axis.axhline(5, color=INK2, lw=0.7, ls="--")
    axis.set_xlim(0, 100)
    axis.set_ylim(0, 25)
    axis.set_xlabel("Incomplete climatic years used (%)")
    axis.set_ylabel(f"Used values outside {tolerance:.0f}% (%)")
    axis.legend(loc="upper left", fontsize=5.8)
    axis = axes[2]
    order = ["A0", "A1", "B", "C"]
    labels = ["Skip incomplete\n(SWToolbox)", "Keep if ≥90%\nof days", "Keep all,\nplug-in", "Keep all, multiple\nimputation"]
    colours = [MUTED, ORANGE, YELLOW, BLUE]
    y = np.arange(len(order))[::-1]
    axis.barh(y, [trend.loc[p, "rmse_per_decade_log"] for p in order], color=colours, height=0.6)
    axis.set_yticks(y, labels, fontsize=6.0)
    axis.set_xlabel("Trend RMSE of log 7Q\n(per decade)")
    axis.grid(axis="y", visible=False)
    for axis, letter in zip(axes, "abc"):
        panel(axis, letter)
    figure.tight_layout(w_pad=1.0)
    save(figure, "tr_f7_low_flow")


def main() -> int:
    import sys

    selected = sys.argv[1:] or ["1", "2", "3", "4", "5", "6", "7"]
    for name in selected:
        globals()[f"figure{name}"]()
        print(f"[464] figure {name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
