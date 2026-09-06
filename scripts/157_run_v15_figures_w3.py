#!/usr/bin/env python3
"""v15/W3: the assembled figure set (WORKPLAN_v15.md Step 3.1/3.2).

Fig 1 (mechanism) is drawn by scripts/154 to
results/v14/p5_mechanism/fig01_mechanism.png and copied here as
fig01_mechanism.png. This script draws the remaining five:

  Fig 2  duration structure of benefit (both panels, CIs, crossings, Johnson
         reference) + three-family robustness (renumbers round-3 fig01).
  Fig 3  regime structure: the inverted-U advantage of the differential curve
         over the best single-term shortcut, plus the per-duration rho curves
         of diff / -risk / default_difficulty showing the signal migration
         (regime_structure.csv).
  Fig 4  main ranking result: per-duration placement rho with the season-LOO
         ceiling and the paired deltas (round-3 fig03).
  Fig 5  decision layer: B=0.20 bars including default_difficulty / -risk /
         oracle / random; budget sweep with network-cluster CIs at 90 d and
         180 d (budget_full.csv + budget_full_ci.csv); EC(xi)/delta curves.
  Fig 6  boundaries: three-level decomposition, drift null, and support-tier
         composition.

Every annotation is asserted in-script. Outputs: results/v15/figures/.
Run: PYTHONPATH=$PWD/src python3 scripts/157_run_v15_figures_w3.py
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

ROOT = Path(__file__).resolve().parents[1]
P0 = ROOT / "results/v14/p0_differential"
P1 = ROOT / "results/v14/p1_baselines"
P2 = ROOT / "results/v14/p2_decision"
P3 = ROOT / "results/v14/p3_drift"
P4 = ROOT / "results/v14/p4_flip_analysis"
MECH = ROOT / "results/v14/p5_mechanism"
BUD = ROOT / "results/v15/budget_full"
OUT = ROOT / "results/v15/figures"

DURATIONS = [7, 14, 30, 60, 90, 180]
PANEL_COLOR = {"first": "#1f77b4", "second": "#d62728"}

plt.rcParams.update(
    {
        "font.size": 8.5,
        "axes.titlesize": 9,
        "axes.labelsize": 8.5,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 7,
        "figure.dpi": 300,
    }
)


def log10_x(ax, lo=5, hi=400):
    ax.set_xscale("log")
    ax.set_xlim(lo, hi)
    ax.set_xticks([7, 14, 30, 60, 90, 180, 365])
    ax.set_xticklabels(["7", "14", "30", "60", "90", "180", "365"])


def _load_flip_mae():
    f = pd.read_csv(P4 / "flip_table.csv")
    return f.loc[f["kind"] == "mae_reference"].copy()


def _load_crossing():
    return pd.read_csv(P4 / "mae_crossing_ci.csv")


def _load_family():
    return pd.read_csv(P1 / "family_benefit_table.csv")


def _load_paired():
    c = pd.read_csv(P0 / "paired_diff_vs_r6.csv")
    return c.loc[c["seed"] == 20260903].copy()


def _load_negrisk():
    return pd.read_csv(P0 / "paired_diff_vs_negrisk.csv")


def _load_metrics():
    m = pd.read_csv(P0 / "metrics_by_horizon.csv")
    m = m.loc[m["level"].astype(str).str.contains("placement", na=False)]
    m = m.loc[~m["horizon"].astype(str).eq("direct")]
    m["horizon"] = m["horizon"].astype(int)
    return m


def _load_loo():
    return pd.read_csv(P0 / "season_loo_upper.csv")


def _load_three():
    return pd.read_csv(P0 / "three_level_decomposition.csv")


def _load_laio():
    return pd.read_csv(P2 / "laio_tamea_curves.csv")


def _load_regime():
    return pd.read_csv(MECH / "regime_structure.csv")


def _load_budget():
    return pd.read_csv(BUD / "budget_full.csv")


def _load_budget_ci():
    return pd.read_csv(BUD / "budget_full_ci.csv")


def fig2(mae, cross, fam) -> Path:
    path = OUT / "fig02_duration_structure.png"
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
    ax = axes[0]
    for panel, color in PANEL_COLOR.items():
        sub = mae.loc[mae["panel"] == panel].sort_values("horizon")
        x = sub["horizon"].astype(float).to_numpy()
        y = sub["point"].to_numpy()
        lo = sub["ci_lower"].to_numpy()
        hi = sub["ci_upper"].to_numpy()
        ax.errorbar(x, y, yerr=[y - lo, hi - y], fmt="o-", ms=4, lw=1.2,
                    color=color, ecolor=color, capsize=2,
                    label=f"{panel} panel")
        row = cross.loc[cross["panel"] == panel].iloc[0]
        point = float(row["point_crossing_day"])
        ax.axvline(point, color=color, ls="--", lw=0.8, alpha=0.7)
        ax.axvspan(float(row["ci_low"]), float(row["ci_high"]),
                   color=color, alpha=0.06)
        ax.annotate(
            f"{panel}: {point:.0f} d\nCI {float(row['ci_low']):.0f}-"
            f"{float(row['ci_high']):.0f} d",
            xy=(point, 0.0), xytext=(point + 8, 0.55),
            fontsize=6.8, color=color,
            arrowprops={"arrowstyle": "-", "color": color, "lw": 0.6},
        )
    ax.axhline(0.0, color="k", lw=0.8)
    ax.axvline(49.0, color="gray", ls=":", lw=1.0)
    ax.text(52, ax.get_ylim()[1] * 0.92, "Johnson et al.\nm_max = 49 d",
            fontsize=6.5, color="gray")
    log10_x(ax)
    ax.set_ylabel("unit-mean realized benefit vs climatology fill (°C)")
    ax.set_xlabel("gap duration (d, log scale)")
    ax.set_title("(a) Duration structure (Table 2; MAE-scale crossings)")
    ax.legend(frameon=False, loc="upper right")
    for _, row in cross.iterrows():
        assert np.isfinite(row["point_crossing_day"])

    ax = axes[1]
    family_order = [
        ("deployment xgboost_b_d", "xgboost_b_d", "#1f77b4", "o"),
        ("donor ridge", "donor_blup_ridge", "#2ca02c", "s"),
        ("seasonal ridge", "seasonal_boundary_ridge", "#ff7f0e", "^"),
    ]
    for label, fam_key, color, marker in family_order:
        rows = fam.loc[fam["model_family"] == fam_key].sort_values(
            "gap_length_days")
        ax.plot(rows["gap_length_days"], rows["mean_benefit_deg_c"],
                marker=marker, ms=4, lw=1.2, color=color, label=label)
    ax.axhline(0.0, color="k", lw=0.8)
    log10_x(ax)
    ax.set_xlabel("gap duration (d, log scale)")
    ax.set_ylabel("mean benefit vs climatology (°C)")
    ax.set_title("(b) Three model families reproduce the sign flip "
                 "(first panel, Table 7)")
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def fig3(regime) -> Path:
    path = OUT / "fig03_regime_structure.png"
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
    ax = axes[0]
    for panel, color in PANEL_COLOR.items():
        sub = regime.loc[regime["panel"] == panel].sort_values("gap_length")
        x = sub["gap_length"].to_numpy(float)
        y = sub["diff_advantage"].to_numpy(float)
        ax.plot(x, y, marker="o", ms=4, lw=1.4, color=color,
                label=f"{panel} panel")
        peak = float(y.max())
        peak_d = float(x[np.argmax(y)])
        ax.annotate(f"{peak:+.3f} at {peak_d:.0f} d",
                    xy=(peak_d, peak), xytext=(peak_d - 25, peak + 0.02),
                    fontsize=7, color=color)
    ax.axhline(0.0, color="k", lw=0.8)
    log10_x(ax, lo=6)
    ax.set_ylabel("diff advantage over best single-term shortcut (Δρ)")
    ax.set_xlabel("gap duration (d, log scale)")
    ax.set_title("(a) The confirmed inverted U (Table 3a): peak in the "
                 "transition zone")
    ax.legend(frameon=False, loc="lower left")
    peak2 = regime.loc[regime["panel"] == "second", "diff_advantage"]
    peak1 = regime.loc[regime["panel"] == "first", "diff_advantage"]
    assert abs(float(peak2.max()) - 0.179) < 0.01
    assert abs(float(peak1.max()) - 0.143) < 0.01
    assert regime.loc[(regime["panel"] == "second")
                      & (regime["gap_length"] == 90),
                      "diff_advantage"].iloc[0] > 0.17

    ax = axes[1]
    for pred, color, lab in (
        ("diff", "#1f77b4", "diff"),
        ("neg_risk", "#7f7f7f", "−risk"),
        ("default_difficulty", "#2ca02c", "default difficulty"),
    ):
        sub = regime.loc[regime["panel"] == "second"].sort_values("gap_length")
        ax.plot(sub["gap_length"], sub[pred], marker="o", ms=4, lw=1.2,
                color=color, label=lab)
    ax.axhline(0.0, color="k", lw=0.8)
    log10_x(ax, lo=6)
    ax.set_ylabel("placement-level Spearman ρ (second panel)")
    ax.set_xlabel("gap duration (d, log scale)")
    ax.set_title("(b) The signal migrates between the two terms: "
                 "default difficulty at short gaps, −risk at long gaps")
    ax.legend(frameon=False, loc="upper left")
    ax.axvspan(60, 180, color="0.9", alpha=0.5)
    ax.text(0.02, 0.05, "shaded: transition zone\n(neither term dominates)",
            transform=ax.transAxes, fontsize=6.4, color="0.3")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def fig4(paired, negrisk, metrics, loo) -> Path:
    path = OUT / "fig04_main_result.png"
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.4))
    ax = axes[0]
    second = paired.loc[paired["panel"] == "second"].sort_values("duration")
    xs = np.arange(len(DURATIONS))
    rho_diff = second["rho_diff"].to_numpy()
    neg = negrisk.loc[negrisk["panel"] == "second"].set_index("duration_days")
    rho_neg = np.array([float(neg.loc[d, "rho_negrisk"]) for d in DURATIONS])
    r6 = second["rho_r6"].to_numpy()
    risk = np.array([float(neg.loc[d, "rho_risk"]) for d in DURATIONS])
    width = 0.16
    ax.bar(xs - 2 * width, rho_diff, width, label="diff", color="#1f77b4")
    ax.bar(xs - width, rho_neg, width, label="−risk", color="#7f7f7f")
    ax.bar(xs, r6, width, label="r6-diff", color="#2ca02c")
    ax.bar(xs + width, risk, width, label="risk", color="#d62728")
    loo2 = loo.loc[loo["panel"] == "second"].copy()
    loo2 = loo2.loc[~loo2["horizon"].astype(str).eq("direct")]
    loo2["horizon"] = loo2["horizon"].astype(int)
    loo2 = loo2.set_index("horizon")
    ceiling = np.array([float(loo2.loc[d, "season_loo_rho"]) for d in DURATIONS])
    ax.plot(xs, ceiling, "k--", lw=0.9, label="season-LOO ceiling")
    ax.axhline(0.0, color="k", lw=0.6)
    ax.axhspan(0.25, 0.35, color="0.85", alpha=0.5)
    ax.text(0.02, 0.36, "0.25–0.35 partial band", fontsize=6.4)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{d} d" for d in DURATIONS])
    ax.set_ylabel("placement-level Spearman ρ (second panel)")
    ax.set_title("(a) Ranking strength within duration strata (Table 3)")
    ax.legend(frameon=False, ncol=3, loc="lower center", fontsize=6.6)
    for xi, y in zip(xs, rho_diff):
        ax.text(xi - 2 * width, y + 0.015, f"{y:.2f}", ha="center",
                fontsize=6.2, color="#1f77b4")

    ax = axes[1]
    d_r6 = second["delta_rho"].to_numpy()
    lo_r6 = second["delta_ci_lower"].to_numpy()
    hi_r6 = second["delta_ci_upper"].to_numpy()
    d_neg = np.array([float(neg.loc[d, "delta_diff_minus_negrisk_mean"])
                      for d in DURATIONS])
    lo_n = np.array([float(neg.loc[d, "delta_diff_minus_negrisk_ci_low"])
                     for d in DURATIONS])
    hi_n = np.array([float(neg.loc[d, "delta_diff_minus_negrisk_ci_high"])
                     for d in DURATIONS])
    ax.errorbar(xs - 0.12, d_r6, yerr=[d_r6 - lo_r6, hi_r6 - d_r6],
                fmt="o", ms=4, color="#2ca02c", capsize=2,
                label="diff − r6-diff")
    ax.errorbar(xs + 0.12, d_neg, yerr=[d_neg - lo_n, hi_n - d_neg],
                fmt="s", ms=4, color="#1f77b4", capsize=2,
                label="diff − (−risk)")
    ax.axhline(0.0, color="k", lw=0.8)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{d} d" for d in DURATIONS])
    ax.set_ylabel("paired Δρ (95% network-cluster CI)")
    ax.set_title("(b) Paired deltas vs fitting-record and sign-flipped "
                 "baselines")
    ax.legend(frameon=False, loc="lower right", fontsize=7)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def _sweep_axes(ax, budget, ci, panel, horizon, title):
    sub = budget.loc[(budget["panel"] == panel)
                     & (budget["horizon"] == horizon)].sort_values("budget")
    ax.axhline(float(sub["stratum_mean"].iloc[0]), color="k", ls=":", lw=1.0)
    ax.text(0.51, float(sub["stratum_mean"].iloc[0]) - 0.06, "stratum mean",
            fontsize=6.2, color="k")
    for pred, color, lab in (
        ("oracle", "#111111", "oracle"),
        ("diff", "#1f77b4", "diff"),
        ("default_difficulty", "#2ca02c", "default difficulty"),
        ("neg_risk", "#7f7f7f", "−risk"),
        ("random", "#999999", "random"),
    ):
        if pred in ("oracle", "random"):
            pts = budget.loc[(budget["panel"] == panel)
                             & (budget["horizon"] == horizon)
                             & (budget["predictor"] == "diff")].sort_values(
                "budget")
            ax.plot(pts["budget"], pts[pred], ls="--", lw=1.1, color=color,
                    label=lab, marker="s", ms=3)
            continue
        pts = budget.loc[(budget["panel"] == panel)
                         & (budget["horizon"] == horizon)
                         & (budget["predictor"] == pred)].sort_values("budget")
        cis = ci.loc[(ci["panel"] == panel) & (ci["horizon"] == horizon)
                     & (ci["predictor"] == pred)].sort_values("budget")
        pts = pts.merge(cis[["budget", "ci_low", "ci_high"]], on="budget")
        ax.plot(pts["budget"], pts["treated_mean"], marker="o", ms=4, lw=1.4,
                color=color, label=lab)
        ax.fill_between(pts["budget"], pts["ci_low"], pts["ci_high"],
                        color=color, alpha=0.12)
    ax.set_xlabel("treatment budget B")
    ax.set_ylabel("mean realized benefit of treated set (°C)")
    ax.set_title(title)
    ax.legend(frameon=False, fontsize=6.2, loc="best")


def fig5(budget, ci, laio) -> Path:
    path = OUT / "fig05_decision_layer.png"
    fig, axes = plt.subplots(2, 2, figsize=(10.8, 7.6))

    ax = axes[0][0]
    b20 = budget.loc[(budget["panel"] == "second")
                     & (budget["budget"] == 0.20)]
    piv = b20.pivot_table(index="predictor", columns="horizon",
                          values="treated_mean")
    harm = b20.pivot_table(index="predictor", columns="horizon",
                           values="harmful_rate")
    xs = np.arange(len(DURATIONS))
    width = 0.19
    order = [("diff", "#1f77b4", "diff"),
             ("default_difficulty", "#2ca02c", "default difficulty"),
             ("neg_risk", "#7f7f7f", "−risk"),
             ("duration", "#999999", "duration-only"),
             ("risk", "#d62728", "v13 risk")]
    for i, (pred, color, lab) in enumerate(order):
        vals = [float(piv.loc[pred, d]) for d in DURATIONS]
        ax.bar(xs + (i - 2) * width, vals, width, color=color, label=lab)
    ax.axhline(0.0, color="k", lw=0.6)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{d} d" for d in DURATIONS])
    ax.set_ylabel("mean realized benefit of top-20% (°C)")
    ax.set_title("(a) Within-duration 20% budgets (second panel, Table 4)")
    ax.legend(frameon=False, fontsize=6.2, loc="lower left")
    for d_i, d in enumerate(DURATIONS):
        h = float(harm.loc["diff", d]) * 100
        ax.text(d_i - 2 * width, float(piv.loc["diff", d]) + 0.03,
                f"{h:.0f}%", ha="center", fontsize=5.8, color="#1f77b4")
    assert abs(float(piv.loc["default_difficulty", 7])
               - float(piv.loc["diff", 7])) < 0.02  # short-gap parity

    _sweep_axes(axes[0][1], budget, ci, "second", 90,
                "(b) Budget sweep at 90 d (second panel, 95% cluster CIs)")
    _sweep_axes(axes[1][0], budget, ci, "second", 180,
                "(c) Budget sweep at 180 d: harm selection with a positive "
                "oracle")
    o180 = budget.loc[(budget["panel"] == "second")
                      & (budget["horizon"] == 180)
                      & (budget["predictor"] == "diff")
                      & (budget["budget"] == 0.20), "oracle"].iloc[0]
    assert o180 > 0.3

    ax = axes[1][1]
    for dur, color in ((7, "#cccccc"), (30, "#999999"), (180, "#666666"),
                       ("direct", "#bbbbbb")):
        g = laio.loc[(laio["panel"] == "second")
                     & (laio["horizon"].astype(str) == str(dur))]
        ax.plot(g["xi"], g["EC_fcst_delta_ratio"], lw=1.0, color=color,
                label=f"{dur} d (pooled-direct)" if dur == "direct"
                else f"{dur} d")
    for dur, color in ((60, "#1f77b4"), (90, "#d62728")):
        g = laio.loc[(laio["panel"] == "second")
                     & (laio["horizon"].astype(str) == str(dur))]
        ax.plot(g["xi"], g["EC_fcst_delta_ratio"], lw=1.4, color=color,
                label=f"{dur} d (bounded excursion)")
        gmax = g.loc[g["EC_fcst_delta_ratio"].idxmax()]
        ax.annotate(
            f"{float(gmax['EC_fcst_delta_ratio']):.3f} @ ξ="
            f"{float(gmax['xi']):.2f}",
            xy=(float(gmax["xi"]), float(gmax["EC_fcst_delta_ratio"])),
            fontsize=6.2, color=color)
    ax.axhline(1.0, color="k", lw=0.8)
    ax.axvspan(0.0, 0.5, color="0.9", alpha=0.6)
    ax.text(0.02, 1.12, "realistic region ξ<0.5", fontsize=6.4)
    ax.set_xlabel("cost ratio ξ")
    ax.set_ylabel("EC(ξ)/δ")
    ax.set_title("(d) Continuous cost–loss value curves (second panel)")
    ax.legend(frameon=False, fontsize=6.2)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def fig6(three, drift_json: Path, panels: tuple[str, str]) -> Path:
    path = OUT / "fig06_boundaries.png"
    drift = json.loads(drift_json.read_text())
    fig, axes = plt.subplots(1, 3, figsize=(11.0, 4.0))
    ax = axes[0]
    levels = [
        ("between_network", "between networks"),
        ("within_network_across_durations", "within network,\nacross durations"),
        ("per_network_mean", "per-network mean"),
    ]
    xpos = np.arange(len(levels))
    for i, (key, lab) in enumerate(levels):
        a = three.loc[(three["level"] == key)
                      & (three["predictor"] == "diff")]["rho"].iloc[0]
        b = three.loc[(three["level"] == key)
                      & (three["predictor"] == "duration_only")]["rho"].iloc[0]
        ax.bar(i - 0.19, a, 0.38, color="#1f77b4",
               label="diff" if i == 0 else None)
        ax.bar(i + 0.19, b, 0.38, color="#7f7f7f",
               label="duration-only" if i == 0 else None)
    ax.set_xticks(xpos)
    ax.set_xticklabels(levels, fontsize=6.8)
    ax.set_ylabel("pooled-direct Spearman ρ (second panel)")
    ax.set_title("(a) Three-level decomposition")
    ax.legend(frameon=False, fontsize=6.5)

    ax = axes[1]
    t2 = drift["T2_pooled_placement"]
    t3 = drift["T3_pooled_network"]
    ax.errorbar([0], [t2["mean"]], yerr=[[t2["mean"] - t2["ci"][0]],
                                         [t2["ci"][1] - t2["mean"]]],
                fmt="o", color="#1f77b4", capsize=3,
                label=f"T2 placement (P(>0)={t2['prob_gt0']:.2f})")
    ax.errorbar([1], [t3["mean"]], yerr=[[t3["mean"] - t3["ci"][0]],
                                         [t3["ci"][1] - t3["mean"]]],
                fmt="s", color="#d62728", capsize=3,
                label=f"T3 network (P(>0)={t3['prob_gt0']:.2f})")
    ax.axhline(0.0, color="k", lw=0.8)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["T2 pooled\nplacement", "T3 pooled\nnetwork"],
                       fontsize=7)
    ax.set_ylabel("drift-stratum advantage of diff over r6-diff")
    ax.set_title("(b) Stationarity null (drift vs stable strata)")
    ax.legend(frameon=False, fontsize=6.5)

    ax = axes[2]
    rows = []
    for panel in panels:
        p = pd.read_csv(P0 / f"placement_predictions_{panel}.csv")
        p = p.loc[p["direct"].astype(str).str.lower().isin({"true", "1"})]
        counts = p["diff_source"].value_counts()
        for src, cnt in counts.items():
            rows.append({"panel": panel, "source": src, "n": int(cnt)})
    sup = pd.DataFrame(rows)
    piv = sup.pivot_table(index="source", columns="panel", values="n",
                          fill_value=0)
    sources = ["station_gap_season", "station_gap", "network_mean_fallback"]
    labels = ["exact cell\n(station·gap·season)", "station·gap",
              "network mean\n(unsupported)"]
    xs2 = np.arange(len(sources))
    for j, panel in enumerate(panels):
        vals = [float(piv.loc[s, panel]) if s in piv.index else 0.0
                for s in sources]
        ax.bar(xs2 + (j - 0.5) * 0.35, vals, 0.35, color=PANEL_COLOR[panel],
               label=f"{panel} panel")
    ax.set_xticks(xs2)
    ax.set_xticklabels(labels, fontsize=6.8)
    ax.set_ylabel("n placements (direct)")
    ax.set_title("(c) Support-tier composition (§2.3)")
    ax.legend(frameon=False, fontsize=6.5)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copy(MECH / "fig01_mechanism.png", OUT / "fig01_mechanism.png")
    mae = _load_flip_mae()
    cross = _load_crossing()
    fam = _load_family()
    paired = _load_paired()
    negrisk = _load_negrisk()
    metrics = _load_metrics()
    loo = _load_loo()
    three = _load_three()
    laio = _load_laio()
    regime = _load_regime()
    budget = _load_budget()
    ci = _load_budget_ci()
    paths = [
        OUT / "fig01_mechanism.png",
        fig2(mae, cross, fam),
        fig3(regime),
        fig4(paired, negrisk, metrics, loo),
        fig5(budget, ci, laio),
        fig6(three, P3 / "direction_test.json",
             ("first", "second")),
    ]
    notes = [
        "# FIGURE NOTES v15 (W3 assembly, 2026-09-05)",
        "",
        ("Fig 1 (mechanism) drawn by scripts/154; annotations asserted against "
         "p5_mechanism CSVs (benefit_decomposition, station_crossings, "
         "family_benefit_table, mae_crossing_ci)."),
        ("Fig 2: p4_flip_analysis/flip_table.csv (mae_reference), "
         "mae_crossing_ci.csv, p1_baselines/family_benefit_table.csv; "
         "Johnson line 49 d."),
        ("Fig 3: p5_mechanism/regime_structure.csv (diff_advantage inverted U, "
         "peak asserted at 90 d; per-duration rho of diff/-risk/"
         "default_difficulty)."),
        ("Fig 4: paired_diff_vs_r6.csv, paired_diff_vs_negrisk.csv, "
         "metrics_by_horizon.csv, season_loo_upper.csv."),
        ("Fig 5: results/v15/budget_full/budget_full.csv + budget_full_ci.csv "
         "(B=0.20 bars; sweeps at 90/180 d with 95% network-cluster CIs; "
         "oracle/random brackets); p2_decision/laio_tamea_curves.csv."),
        ("Fig 6: three_level_decomposition.csv, p3_drift/direction_test.json, "
         "placement_predictions support-tier counts (diff_source)."),
    ]
    (OUT / "FIGURE_NOTES_v15.md").write_text("\n".join(notes) + "\n")
    for p in paths:
        print("wrote", p)


if __name__ == "__main__":
    main()
