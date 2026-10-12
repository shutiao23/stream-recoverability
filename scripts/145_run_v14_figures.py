#!/usr/bin/env python3
"""145_run_v14_figures.py -- publication figures for the v14 manuscript and its
negative-result note.

Provenance per figure follows paper_archived/v14_plan/figure_plan_v14.md (authoritative
per-panel spec) and paper_archived/v14_plan/negative_result_note.md.  All figures are
written to results/v14/figures/ at 300 dpi.

Figures:
  fig_01_thesis.png             risk vs differential ranking scatter (Fig 1)
  fig_02_baselines.png          Tier-0 baseline bars + paired-bootstrap forest (Fig 2)
  fig_03_support_budget.png     support tiers + within-duration top-20% budget (Fig 3)
  fig_04_decision.png           EC(xi)/delta, CRPS identity, selective curves, E-AURC (Fig 4)
  fig_05_eta_downstream.png     eta response-effectiveness + REV fixed-threshold loss (Fig 5)
  fig_06_strata.png             stationarity strata + direction tests (Fig 6)
  note_fig_01_loss_ranking.png  negative note: empirical vs r6 vs duration-only ranking
  note_fig_02_estimand.png      negative note: F1 diagnosis (risk vs default difficulty)
  note_fig_03_budget.png        negative note: top-20% benefit budget bars
  fig_v13_legacy_workflow.png   v13 Fig-1 design schematic (legacy, superseded)
  v13_legacy_figs.txt           supersession note

Color contract (shared across figures):
  diff=dark blue, risk=red, duration_only=grey, r6_diff=teal,
  random=light grey, oracle=green.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
P0 = ROOT / "results/v14/p0_differential"
P1 = ROOT / "results/v14/p1_baselines"
P2 = ROOT / "results/v14/p2_decision"
P3 = ROOT / "results/v14/p3_drift"
V13 = ROOT / "results/revision_v13/strongest_baseline/agent_a"
T08 = ROOT / "results/revision_v12/t08_downstream_metrics/agent_a"
FIGDIR = ROOT / "results/v14/figures"
FIGDIR.mkdir(parents=True, exist_ok=True)

DURS = ["7", "30", "90", "180"]
DUR_LABEL = {"7": "7 d", "30": "30 d", "90": "90 d", "180": "180 d"}

# ---------------------------------------------------------------- style ----
plt.rcParams.update(
    {
        "font.size": 9.5,
        "font.family": "DejaVu Sans",
        "axes.titlesize": 9.5,
        "axes.titleweight": "bold",
        "axes.labelsize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 7,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
    }
)

C_DUR = {"7": "#2c7bb6", "30": "#fdae61", "90": "#66bd63", "180": "#8e44ad"}

C_DIFF = "#1f4e9c"          # dark blue
C_RISK = "#c62828"          # red
C_DURONLY = "#8c8c8c"       # grey
C_R6 = "#00897b"            # teal
C_RANDOM = "#c9c9c9"        # light grey
C_ORACLE = "#15803d"        # green
C_DEFAULT_DIFF = "#d97706"  # amber
C_RH_BENEFIT = "#7c3aed"    # violet
C_RH_ERROR = "#db2777"      # pink
C_SD = "#64748b"            # slate
C_AMPLITUDE = "#65a30d"     # lime

PCOL = {
    "diff": C_DIFF,
    "risk": C_RISK,
    "duration": C_DURONLY,
    "duration_only": C_DURONLY,
    "r6_diff": C_R6,
    "default_difficulty": C_DEFAULT_DIFF,
    "rh_benefit": C_RH_BENEFIT,
    "rh_error": C_RH_ERROR,
    "sd": C_SD,
    "amplitude": C_AMPLITUDE,
    "random": C_RANDOM,
    "oracle": C_ORACLE,
    "global": "#555555",
}

PLABEL = {
    "diff": "diff",
    "risk": "risk",
    "duration": "duration-only",
    "duration_only": "duration-only",
    "r6_diff": "r6-diff",
    "default_difficulty": "default difficulty",
    "rh_benefit": "R&H benefit",
    "rh_error": "R&H error",
    "sd": "sd",
    "amplitude": "amplitude",
    "random": "random",
    "oracle": "oracle",
}


def footer(fig, text: str) -> None:
    fig.text(0.004, 0.005, text + "  |  scripts/145_run_v14_figures.py",
             fontsize=5.6, color="#555555", ha="left", va="bottom")


def panel_label(ax, letter: str, xpos: float = 0.012, ypos: float = 0.965) -> None:
    ax.text(xpos, ypos, f"({letter})", transform=ax.transAxes,
            fontsize=11.5, fontweight="bold", va="top", ha="left", color="#111111",
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.6),
            zorder=20)


def _load() -> dict:
    d: dict = {}

    def csv(p: Path, **kw) -> pd.DataFrame:
        kw.setdefault("low_memory", False)
        return pd.read_csv(p, **kw)

    p = csv(P0 / "placement_predictions_second.csv")
    p["gap_length"] = p["gap_length"].astype(int)
    p = p[p["direct"] & p["gap_length"].isin([7, 30, 90, 180])].copy()
    u = csv(P0 / "unit_predictions_second.csv")
    u["gap_length"] = u["gap_length"].astype(int)
    d["place2"] = p
    d["unit2"] = u[u["direct"]].copy()

    d["metrics_h"] = csv(P0 / "metrics_by_horizon.csv", dtype={"horizon": str})
    d["metrics_h"] = d["metrics_h"][d["metrics_h"]["panel"] == "second"]
    d["paired"] = csv(P0 / "paired_bootstrap.csv")
    d["derived_net"] = csv(P0 / "derived_network_level.csv", dtype={"horizon": str})
    d["derived_net"] = d["derived_net"][d["derived_net"]["panel"] == "second"]
    d["season_loo"] = csv(P0 / "season_loo_upper.csv", dtype={"horizon": str})
    d["season_loo"] = d["season_loo"][d["season_loo"]["panel"] == "second"]
    d["gates"] = json.loads((P0 / "gates.json").read_text())

    d["p1_metrics"] = csv(P1 / "metrics_table.csv", dtype={"horizon": str})
    d["p1_bwd"] = csv(P1 / "budget_within_duration.csv", dtype={"horizon": str})
    d["p0_bwd"] = csv(P0 / "budget_within_duration.csv", dtype={"horizon": str})

    d["laio"] = csv(P2 / "laio_tamea_curves.csv", dtype={"horizon": str})
    d["crps"] = csv(P2 / "crps_check.csv", dtype={"horizon": str})
    d["sel_curves"] = csv(P2 / "selective_risk_curves.csv", dtype={"horizon": str})
    d["sel_metrics"] = csv(P2 / "selective_metrics.csv", dtype={"horizon": str})
    d["eta"] = csv(P2 / "eta_sensitivity.csv", dtype={"horizon": str})
    d["rev_fixed"] = csv(P2 / "rev_fixed_threshold.csv", dtype={"horizon": str})

    d["stratum"] = csv(P3 / "stratum_comparison.csv", dtype={"horizon": str})
    d["stratum_dir"] = csv(P3 / "stratum_direction_test.csv", dtype={"horizon": str})
    d["dir_json"] = json.loads((P3 / "direction_test.json").read_text())

    d["v13_summary"] = csv(V13 / "summary_metrics.csv")
    d["v13_unit"] = csv(V13 / "unit_comparison_second.csv")
    d["v13_perh_net"] = csv(V13 / "per_horizon_network_spearman.csv")
    d["v13_paired"] = csv(V13 / "paired_bootstrap.csv")

    d["t08"] = csv(T08 / "placement_thermal_metrics.csv")
    return d


# =====================================================================
# Figure 1 - thesis statement
# =====================================================================
def fig01(d: dict) -> str:
    p = d["place2"].copy()
    p = p.sort_values("gap_length")
    out = FIGDIR / "fig_01_thesis.png"

    fig, (axl, axr) = plt.subplots(1, 2, figsize=(7.6, 5.0))
    fig.subplots_adjust(top=0.84, bottom=0.13, left=0.085, right=0.985, wspace=0.23)
    fig.suptitle("The sign of the ranking flips with the estimand", fontsize=12.5,
                 fontweight="bold", y=0.985)
    fig.text(0.5, 0.93,
             "17,298 direct placements (second panel). Realized benefit: mean +0.051 °C; 36.7% harmful. "
             "Lines: per-duration binned means.",
             ha="center", va="top", fontsize=6.6, color="#333333")

    rho_pool_risk = p["realized_benefit"].corr(p["risk_prediction"], method="spearman")
    rho_pool_diff = p["realized_benefit"].corr(p["diff_prediction"], method="spearman")
    u2 = d["unit2"]
    corr_insight = spearmanr(u2["risk_prediction"], u2["diff_prediction"]).statistic

    rho_risk, rho_diff = {}, {}
    for g in [7, 30, 90, 180]:
        sub = p[p["gap_length"] == g]
        rho_risk[g] = spearmanr(sub["risk_prediction"], sub["realized_benefit"]).statistic
        rho_diff[g] = spearmanr(sub["diff_prediction"], sub["realized_benefit"]).statistic

    def loessish(x, y, n_bins=18):
        o = np.argsort(x)
        xs, ys = x.values[o], y.values[o]
        edges = np.quantile(xs, np.linspace(0, 1, n_bins + 1))
        edges = np.unique(edges)
        bx, by = [], []
        idx = np.digitize(xs, edges) - 1
        for b in np.unique(idx):
            m = idx == b
            if m.sum() >= 5:
                bx.append(xs[m].mean())
                by.append(ys[m].mean())
        return np.asarray(bx), np.asarray(by)

    for g in [7, 30, 90, 180]:
        sub = p[p["gap_length"] == g]
        c = C_DUR[str(g)]
        for ax, xc in ((axl, "risk_prediction"), (axr, "diff_prediction")):
            ax.scatter(sub[xc], sub["realized_benefit"], s=5, alpha=0.16, c=c,
                       edgecolors="none", label=f"{g} d", rasterized=True)
            bx, by = loessish(sub[xc], sub["realized_benefit"])
            ax.plot(bx, by, c=c, lw=1.8, alpha=0.98, zorder=6)

    axl.set_xlabel("risk prediction - predicted model MAE (°C)")
    axr.set_xlabel("differential prediction - predicted benefit (°C)")
    for ax in (axl, axr):
        ax.set_ylabel("realized benefit = MAE(climatology) - MAE(model) (°C)")
        ax.axhline(0, color="#999999", lw=0.7, ls=":")
    xl = p["risk_prediction"].quantile([0.001, 0.999])
    xd = p["diff_prediction"].quantile([0.001, 0.999])
    yl = p["realized_benefit"].quantile([0.0002, 0.9998])
    axl.set_xlim(xl.values[0], xl.values[1])
    axr.set_xlim(xd.values[0], xd.values[1])
    for ax in (axl, axr):
        ax.set_ylim(yl.values[0], yl.values[1])

    axl.set_title("risk curve ranks model error, not benefit", fontsize=10)
    axr.set_title("differential curve ranks benefit", fontsize=10)

    def spearman_block(ax, rhos, pooled, box, y0=0.955):
        rows = [(f"{g} d   ρ = {rhos[g]:+.3f}", C_DUR[str(g)]) for g in [7, 30, 90, 180]]
        rows.append((f"pooled   ρ = {pooled:+.3f}", "#000000"))
        for i, (s, c) in enumerate(rows):
            ax.text(box[0], y0 - 0.045 * i, s, color=c, fontsize=7.2,
                    fontweight="bold" if i == len(rows) - 1 else "normal",
                    transform=ax.transAxes, va="top", ha="left",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8))

    spearman_block(axl, rho_risk, rho_pool_risk, (0.02, 0.94), y0=0.955)
    spearman_block(axr, rho_diff, rho_pool_diff, (0.02, 0.94), y0=0.955)
    axr.text(0.02, 0.055,
             f"Spearman corr(diff, risk) = {corr_insight:.3f} on 874\n"
             "direct units (sanity_checks.txt) - near-complement\ninstruments",
             transform=axr.transAxes, fontsize=6.8, color="#333333", va="bottom",
             bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#999999", alpha=0.9))

    for ax in (axl, axr):
        handles, labels = ax.get_legend_handles_labels()
        if labels:
            leg = ax.legend(handles, labels, loc="lower right", framealpha=0.92,
                            title="gap length", fontsize=7.4)
            leg.get_title().set_fontsize(7.4)

    footer(fig, "data: results/v14/p0_differential/placement_predictions_second.csv; "
                "ρ annotations: metrics_by_horizon.csv placement-pooled rows "
                "(risk 0.184/0.129/-0.192/-0.540 - pooled -0.481; "
                "diff 0.297/0.303/0.370/0.555 - pooled 0.607)")
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return str(out)


# =====================================================================
# Figure 2 - baselines + paired bootstrap
# =====================================================================
def fig02(d: dict) -> str:
    m = d["p1_metrics"]
    m = m[(m["panel"] == "second") & (m["level"] == "placement_pooled")]
    m = m[m["horizon"].isin(DURS)]
    mh = d["metrics_h"].set_index("horizon")
    loo = d["season_loo"].set_index("horizon")
    net = d["derived_net"].set_index("horizon")
    paired = d["paired"]

    preds = ["diff", "risk", "r6_diff", "default_difficulty", "rh_benefit", "sd",
             "amplitude", "rh_error"]
    out = FIGDIR / "fig_02_baselines.png"

    fig = plt.figure(figsize=(7.8, 6.0))
    gs = fig.add_gridspec(2, 3, width_ratios=[1.0, 1.0, 0.92], hspace=0.62, wspace=0.42,
                          left=0.10, right=0.985, top=0.87, bottom=0.13)
    fig.suptitle("Strong-baseline comparison: per-duration placement ρ and paired Δρ bootstrap "
                 "(second panel)", fontsize=11.5, fontweight="bold", y=0.985)

    for k, dur in enumerate(DURS):
        row, col = divmod(k, 2)
        ax = fig.add_subplot(gs[row, col])
        row_m = m[m["horizon"] == dur].set_index("predictor")["rho"]
        ypos = np.arange(len(preds))
        for i, pr in enumerate(preds):
            v = row_m.get(pr, np.nan)
            if np.isnan(v):
                continue
            ax.barh(ypos[i], v, height=0.62, color=PCOL[pr], alpha=0.92)
            if v >= 0:
                ax.text(v * 0.5, ypos[i], f"{v:.3f}", va="center", ha="center",
                        fontsize=6.2, color="white",
                        fontweight="bold" if pr == "diff" else "normal")
            else:
                ax.text(v + 0.015, ypos[i], f"{v:.3f}", va="center", ha="left",
                        fontsize=6.2, color="#111111")
        ci = mh.loc[dur]
        ax.errorbar(ci["diff_rho"], ypos[preds.index("diff")],
                    xerr=[[ci["diff_rho"] - ci["diff_ci_lower"]],
                          [ci["diff_ci_upper"] - ci["diff_rho"]]],
                    fmt="none", ecolor="#111111", elinewidth=1.1, capsize=2.8)
        lo = loo.loc[dur, "season_loo_rho"]
        ax.axvline(lo, color="#111111", ls="--", lw=1.0)
        ax.axvspan(0.25, 0.35, color="#b0bec5", alpha=0.16, zorder=0)
        ax.axvline(0.35, color="#37474f", ls="-.", lw=1.1)
        ax.axvline(0.0, color="#bbbbbb", lw=0.7)
        ax.set_yticks(ypos)
        ax.set_yticklabels([PLABEL[pr] for pr in preds])
        ax.set_xlim(-0.72, 0.82)
        nrow = net.loc[dur]
        cirow = mh.loc[dur]
        loo_v = loo.loc[dur, "season_loo_rho"]
        ax.set_title(f"{DUR_LABEL[dur]}  -  placement ρ {cirow['diff_rho']:.3f} "
                     f"CI [{cirow['diff_ci_lower']:.3f}, {cirow['diff_ci_upper']:.3f}]\n"
                     f"network ρ {nrow['network_rho']:.3f} [{nrow['network_rho_ci_lower']:.3f}, "
                     f"{nrow['network_rho_ci_upper']:.3f}] · season-LOO ceiling {loo_v:.3f} · "
                     f"{int(nrow['n_networks'])} nets",
                     fontsize=7.6)
        panel_label(ax, "abcd"[k])
        if k >= 2:
            ax.set_xlabel("placement-level Spearman ρ\n"
                          "(grey band: partial 0.25-0.35 · dash-dot: gate 0.35 · black dashed: "
                          "season-LOO ceiling)", fontsize=6.4)

    # ---------------- right: paired-bootstrap forest -----------------
    axf = fig.add_subplot(gs[:, 2])
    rows = ["risk", "duration_only", "r6_diff", "default_difficulty"]
    ypos = np.arange(len(rows))[::-1]
    sec = paired[paired["panel"] == "second"].set_index("comparator")
    fir = paired[paired["panel"] == "first"].set_index("comparator")
    for i, comp in enumerate(rows):
        y = ypos[i]
        s = sec.loc[comp]
        f = fir.loc[comp]
        axf.errorbar([f["mean"]], [y + 0.23], xerr=[[f["mean"] - f["ci_lower"]],
                                                    [f["ci_upper"] - f["mean"]]],
                     fmt="o", ms=4.5, mfc="none", mec="#888888", ecolor="#bbbbbb",
                     elinewidth=0.8, capsize=2)
        axf.errorbar([s["mean"]], [y - 0.23], xerr=[[s["mean"] - s["ci_lower"]],
                                                    [s["ci_upper"] - s["mean"]]],
                     fmt="o", ms=5.5, mfc=C_DIFF, mec=C_DIFF, ecolor=C_DIFF,
                     elinewidth=1.4, capsize=2.5)
        axf.text(s["mean"] + 0.02, y - 0.23, f"Δ = {s['mean']:+.3f} [{s['ci_lower']:+.3f}, "
                                            f"{s['ci_upper']:+.3f}] · {s['frac_gt0'] * 100:.0f}%>0",
                 fontsize=6.0, va="center")
        axf.text(0.02, y + 0.23, f"dev {f['mean']:+.3f} [{f['ci_lower']:+.3f}, "
                                 f"{f['ci_upper']:+.3f}]", fontsize=5.4, va="center",
                 color="#888888")
    axf.axvline(0, color="#999999", lw=0.9)
    axf.set_yticks(ypos)
    axf.set_yticklabels([f"vs {PLABEL[r]}" for r in rows])
    axf.set_xlim(-0.35, 1.85)
    axf.set_title("Paired bootstrap Δρ: ρ(diff) − ρ(comparator)\n(placement-level, 2,000 draws, "
                  "direct-pooled)", fontsize=8.6)
    panel_label(axf, "(e)")
    axf.legend(handles=[
        Line2D([], [], marker="o", ls="none", mfc=C_DIFF, mec=C_DIFF, ms=5.5,
               label="second panel"),
        Line2D([], [], marker="o", ls="none", mfc="none", mec="#888888", ms=4.5,
               label="development panel (inset)")],
        loc="lower right", fontsize=6.2, framealpha=0.95)
    axf.text(0.5, 0.005,
             "pooled near-tie with duration-only (+0.002, 54% > 0) is a cross-duration pooling "
             "artefact - per-duration separation (left) is the claim; duration-only is flat within a "
             "duration (ties → random) and enters only via budget rows.",
             transform=axf.transAxes, fontsize=5.8, ha="center", va="bottom", color="#333333")

    footer(fig, "data: results/v14/p1_baselines/metrics_table.csv  |  "
                "results/v14/p0_differential/{metrics_by_horizon,season_loo_upper,"
                "derived_network_level,paired_bootstrap}.csv")
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return str(out)


# =====================================================================
# Figure 3 - support tiers + within-duration budgets
# =====================================================================
def fig03(d: dict) -> str:
    u = d["unit2"].copy()
    u["gap_length"] = u["gap_length"].astype(str)
    p0b = d["p0_bwd"]
    p1b = d["p1_bwd"]
    p0b = p0b[(p0b["budget"] == 0.2) & (p0b["panel"] == "second")]
    p1b = p1b[(p1b["budget"] == 0.2) & (p1b["panel"] == "second")]
    bwd = pd.concat([
        p0b[p0b["predictor"].isin(["diff", "duration", "r6_diff", "risk"])],
        p1b[p1b["predictor"].isin(["default_difficulty", "rh_benefit"])],
    ], ignore_index=True)
    bwd["horizon"] = bwd["horizon"].astype(str)
    order = ["diff", "duration", "r6_diff", "risk", "default_difficulty", "rh_benefit"]

    p = d["place2"]
    panel_mean = p.groupby("gap_length")["realized_benefit"].mean()
    np_place = p.groupby("gap_length").size()

    out = FIGDIR / "fig_03_support_budget.png"
    fig, (axl, axr) = plt.subplots(1, 2, figsize=(7.8, 5.9))
    fig.subplots_adjust(top=0.84, bottom=0.12, left=0.075, right=0.985, wspace=0.30)
    fig.suptitle("Support tiers and within-duration top-20% budgets - second panel",
                 fontsize=11.5, fontweight="bold", y=0.985)
    fig.text(0.5, 0.945,
             "874 direct units (224/224/220/206 at 7/30/90/180 d) carry 17,298 placements.  "
             "Budget rows: archived budget_within_duration.csv (diff/duration/r6-diff/risk: P0; "
             "default-difficulty/R&H-benefit: P1 - P0 archived only the four plan predictors).",
             ha="center", va="top", fontsize=6.2, color="#333333")

    # -------------------- panel (a): support tiers --------------------
    panel_label(axl, "(a)")
    axl.set_title("Support accounting: exact station×gap×season vs collapsed (direct units)")
    tru = [int(u[(u.gap_length == g) & (u.diff_supported)].shape[0]) for g in DURS]
    fls = [int(u[(u.gap_length == g) & (~u.diff_supported)].shape[0]) for g in DURS]
    xpos = np.arange(len(DURS))
    b1 = axl.bar(xpos, tru, 0.55, color="#8da0cb",
                 label="exact station×gap×season (diff supported)")
    axl.bar(xpos, fls, 0.55, bottom=tru, color="#e08f5e",
            label="collapsed / network-mean fallback")
    for x, (t, f) in zip(xpos, zip(tru, fls)):
        axl.text(x, t / 2, f"{t} units", ha="center", va="center", fontsize=7.2)
        if f:
            axl.text(x, t + f / 2, f"{f} units", ha="center", va="center", fontsize=7.2)
    axl.set_xticks(xpos)
    axl.set_xticklabels([f"{DUR_LABEL[g]}\n({np_place[int(g)]:,} placements)" for g in DURS],
                        fontsize=7.0)
    axl.set_ylabel("direct units")
    axl.set_ylim(0, 262)
    axl.text(0.15, 253, "support falls with duration: 90 d: 4 units (80 placements) · 180 d: 20 units "
                        "(400 placements) at the network-mean fallback = 24/874 units, 480/17,298 "
                        "placements (2.8%)", fontsize=6.2, color="#333333")
    axl.legend(loc="upper left", bbox_to_anchor=(0.0, 1.02), fontsize=6.6, framealpha=0.95)

    # -------------------- panel (b): within-duration budget bars -------
    panel_label(axr, "(b)")
    axr.set_title("Within-duration top-20% budget: mean realized benefit by predictor\n"
                  "(dashed lines: per-duration panel-mean benefit)")
    pitch, bw = 0.36, 0.29
    xtick_pos = []
    for j, dur in enumerate(DURS):
        base = j * 3.35
        sub = bwd[bwd["horizon"] == dur]
        for k, pr in enumerate(order):
            row = sub[sub["predictor"] == pr]
            if row.empty:
                continue
            row = row.iloc[0]
            x = base + 0.20 + k * pitch
            axr.bar(x, row["mean_realized_benefit"], bw, color=PCOL[pr],
                    edgecolor="black" if pr == "diff" else "none",
                    linewidth=0.9 if pr == "diff" else 0.0, zorder=3)
        pm = panel_mean[int(dur)]
        cx = base + 0.20 + (len(order) - 1) * pitch / 2
        axr.plot([base + 0.05, base + 2.4], [pm, pm], color="#111111", ls="--",
                 lw=0.9, zorder=4)
        axr.text(cx, pm + (0.05 if pm >= -1.2 else -0.18), f"panel mean {pm:+.3f}",
                 fontsize=5.4, ha="center", color="#111111",
                 bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.85),
                 zorder=5)
        xtick_pos.append(cx)
    axr.set_xticks(xtick_pos)
    axr.set_xticklabels([DUR_LABEL[g] for g in DURS])
    axr.axhline(0, color="#999999", lw=0.7)
    axr.set_ylabel("mean realized benefit of treated top-20% (°C)")
    axr.set_ylim(-3.7, 2.15)
    axr.set_xlim(-0.35, 13.7)
    axr.legend(handles=[
        Patch(facecolor=PCOL["diff"], edgecolor="black", label="diff (highlighted)"),
        Patch(facecolor=PCOL["duration"], label="duration-only"),
        Patch(facecolor=PCOL["r6_diff"], label="r6-diff"),
        Patch(facecolor=PCOL["risk"], label="risk"),
        Patch(facecolor=PCOL["default_difficulty"], label="default difficulty"),
        Patch(facecolor=PCOL["rh_benefit"], label="R&H benefit")],
        loc="upper left", bbox_to_anchor=(0.0, 1.02), ncol=3, fontsize=6.2,
        framealpha=0.95, columnspacing=0.8, handlelength=1.0)

    tab_label = {"diff": "diff", "duration": "dur-only", "r6_diff": "r6-diff",
                 "risk": "risk", "default_difficulty": "default-diff",
                 "rh_benefit": "R&H-benefit"}
    tbl = [f"{'':<12s}" + "".join(f"{DUR_LABEL[g]:>7s}" for g in DURS)]
    for pr in order:
        sub = bwd[bwd["predictor"] == pr].set_index("horizon")
        tbl.append(f"{tab_label[pr]:<12s}"
                   + "".join(f"{sub.loc[g, 'mean_realized_benefit']:>7.3f}" for g in DURS))
    ytab = -1.02
    for s in tbl:
        axr.text(0.35, ytab, s, fontsize=5.5, color="#111111", ha="left", va="top",
                 family="DejaVu Sans Mono")
        ytab -= 0.205
    hb = bwd[bwd["predictor"].isin(order)].set_index(["predictor", "horizon"])["harmful_rate"] * 100
    hrows = [
        "harmful share of the treated top-20% (benefit < 0), % - order across cols: 7/30/90/180 d",
        "diff " + "  ".join(f"{hb.loc['diff', g]:4.1f}" for g in DURS) + "      "
        "dur-only " + "  ".join(f"{hb.loc['duration', g]:4.1f}" for g in DURS),
        "r6-diff " + "  ".join(f"{hb.loc['r6_diff', g]:4.1f}" for g in DURS) + "      "
        "risk " + "  ".join(f"{hb.loc['risk', g]:4.1f}" for g in DURS),
        "15% harmful cap = protocol v5 G3; flat duration-only rows are one seeded random 20% draw",
    ]
    yh = -2.62
    for s in hrows:
        axr.text(0.35, yh, s, fontsize=5.3, color="#444444", ha="left", va="top")
        yh -= 0.185

    axr.annotate("180-d harm avoidance:\ndiff -0.636 vs\ndur-only -1.647 vs\nrisk -2.881 °C",
                 xy=(10.10, -0.70), xytext=(11.45, 0.85), fontsize=6.0, color="#111111",
                 arrowprops=dict(arrowstyle="->", lw=0.8, color="#111111"))

    footer(fig, "data: results/v14/p0_differential/{unit_predictions_second,placement_predictions_second,"
                "budget_within_duration}.csv  |  results/v14/p1_baselines/budget_within_duration.csv")
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return str(out)


# =====================================================================
# Figure 4 - decision layer
# =====================================================================
def fig04(d: dict) -> str:
    laio = d["laio"]
    crps = d["crps"]
    sel = d["sel_curves"]
    met = d["sel_metrics"]
    laio2 = laio[laio["panel"] == "second"]
    crps2 = crps[crps["panel"] == "second"]
    sel2 = sel[sel["panel"] == "second"]
    met2 = met[met["panel"] == "second"]
    out = FIGDIR / "fig_04_decision.png"

    fig, axes = plt.subplots(2, 2, figsize=(7.8, 7.0))
    fig.subplots_adjust(top=0.87, bottom=0.10, left=0.115, right=0.985, hspace=0.62, wspace=0.30)
    fig.suptitle("Decision layer for differential (benefit) forecasts - second panel",
                 fontsize=11.5, fontweight="bold", y=0.985)

    # ---------------- (a) EC(xi)/delta ----------------
    ax = axes[0, 0]
    ax.set_title("Laio & Tamea continuous cost-loss: EC(ξ)/δ per horizon")
    ax.axvspan(0, 0.5, color="#b0bec5", alpha=0.14)
    for dur in DURS:
        row = laio2[laio2["horizon"] == dur].sort_values("xi")
        ax.plot(row["xi"], row["EC_fcst_delta_ratio"], color=C_DUR[dur], lw=1.7)
        ax.plot(row["xi"], row["EC_clim_delta_ratio"], color="#bdbdbd", ls="--", lw=0.9)
        imin = row["EC_fcst_delta_ratio"].idxmin()
        rmin = row.loc[imin]
        ax.plot([rmin["xi"]], [rmin["EC_fcst_delta_ratio"]], "o", ms=4.5,
                color=C_DUR[dur], zorder=5)
        if rmin["xi"] >= 0.8:
            tx, ty, h = 0.985, rmin["EC_fcst_delta_ratio"] + 0.05, "right"
        else:
            dy = 0.55 if dur == "90" else 0.13
            tx, ty, h = (0.16 if dur == "90" else 0.015), \
                        rmin["EC_fcst_delta_ratio"] + dy, "left"
        ax.annotate(f"min {rmin['EC_fcst_delta_ratio']:.3f} @ ξ={rmin['xi']:.2f}",
                    xy=(rmin["xi"], rmin["EC_fcst_delta_ratio"]), xytext=(tx, ty),
                    fontsize=5.2, ha=h, color=C_DUR[dur],
                    arrowprops=dict(arrowstyle="-", lw=0.5, color=C_DUR[dur]),
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))
    ax.axhline(1.0, color="#111111", lw=0.9)
    ax.text(0.985, 1.03, "EC/δ = 1 (climatology-mean forecast cost = δ)",
            transform=ax.get_yaxis_transform(), fontsize=6.0, ha="right", color="#111111")
    ax.text(0.5, 0.035, "ξ < 0.5 shaded: hydrologically realistic (cheap action) half",
            transform=ax.transAxes, fontsize=6.0, ha="center", va="bottom", color="#37474f")
    ax.set_xlabel("cost-loss ratio ξ")
    ax.set_ylabel("EC(ξ)/δ - normalized expected cost")
    ax.set_ylim(0, 1.95)
    ax.set_xlim(0, 1)
    ax.legend(handles=[Line2D([], [], color=C_DUR[k], lw=1.7, label=f"{k} d forecast")
                       for k in DURS] +
                      [Line2D([], [], color="#bdbdbd", ls="--", lw=0.9,
                              label="EC_clim(ξ)/δ per horizon")],
              loc="upper right", fontsize=5.8, ncol=2, framealpha=0.95)
    panel_label(ax, "(a)")

    # ---------------- (b) CRPS identity ----------------
    ax = axes[0, 1]
    ax.set_title("CRPS identity: trapezoidal ∫EC(ξ)dξ = CRPS")
    rows = crps2[crps2["horizon"].isin(DURS)].set_index("horizon")
    vals = (rows["crps_ratio"] - 1.0) * 1e4
    ax.bar(np.arange(len(DURS)), vals.values, 0.55, color=[C_DUR[k] for k in DURS])
    for i, (k, v) in enumerate(vals.items()):
        ax.text(i, v + (0.05 if v >= 0 else -0.30), f"ratio {1 + v / 1e4:.5f}",
                ha="center", fontsize=6.2, color="#111111")
    ax.axhline(0, color="#111111", lw=0.9)
    ax.set_xticks(np.arange(len(DURS)))
    ax.set_xticklabels([DUR_LABEL[k] for k in DURS])
    ax.set_ylabel("(∫EC dξ / CRPS − 1) × 10⁴")
    ax.set_ylim(-2.4, 1.1)
    ax.text(0.5, 0.02,
            "identity holds to ≥ 4 digits (max deviation 1.3×10⁻⁴); the curve is reported because "
            "uniform ξ-weighting over-weights ξ > 0.5\n(90 d is at parity with climatology only at "
            "ξ 0.50-0.60, below 1 over all of ξ < 0.5)",
            transform=ax.transAxes, fontsize=5.8, ha="center", va="bottom", color="#333333")
    panel_label(ax, "(b)")

    # ---------------- (c) selective curves, 90 d ----------------
    ax = axes[1, 0]
    ax.set_title("Selective risk vs coverage, 90 d (loss = −realized benefit)")
    s90 = sel2[sel2["horizon"] == "90"]
    for meth, col, ls in (("random", C_RANDOM, "-"), ("diff", C_DIFF, "-"),
                          ("risk", C_RISK, "-"), ("oracle", C_ORACLE, "--")):
        sub = s90[s90["method"] == meth].sort_values("coverage")
        ax.plot(sub["coverage"], sub["risk"], color=col, lw=1.7, ls=ls,
                label=PLABEL[meth], zorder=4)
        if meth == "random":
            ax.fill_between(sub["coverage"], sub["risk_band_lo"], sub["risk_band_hi"],
                            color=C_RANDOM, alpha=0.5, zorder=1)
    m90 = met2[met2["horizon"] == "90"].set_index("method")
    boxc = (f"E-AURC (norm.): diff {m90.loc['diff', 'e_aurc_norm']:+.3f} · risk "
            f"{m90.loc['risk', 'e_aurc_norm']:+.3f} · duration-only "
            f"{m90.loc['duration_only', 'e_aurc_norm']:+.3f}\n"
            f"risk@50%: diff {m90.loc['diff', 'risk_at_c50']:+.3f} vs risk "
            f"{m90.loc['risk', 'risk_at_c50']:+.3f} °C (risk below random)\n"
            "90-d top-20% context: diff +0.380 vs risk −0.256 °C")
    ax.text(0.99, 0.965, boxc, transform=ax.transAxes, fontsize=5.6, va="top",
            ha="right", color="#111111",
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#999999", alpha=0.9))
    ax.axhline(0, color="#999999", lw=0.7, ls=":")
    ax.set_xlabel("coverage (fraction of placements accepted)")
    ax.set_ylabel("selective risk - mean loss of accepted set (°C)")
    ax.set_ylim(-1.6, 0.95)
    ax.legend(loc="lower right", fontsize=6.4)
    panel_label(ax, "(c)", xpos=0.012, ypos=0.05)

    # ---------------- (d) E-AURC bars ----------------
    ax = axes[1, 1]
    ax.set_title("Normalized E-AURC by duration")
    meths = ["diff", "risk", "duration_only"]
    for i, dur in enumerate(DURS):
        sub = met2[met2["horizon"] == dur].set_index("method")
        for k, meth in enumerate(meths):
            v = sub.loc[meth, "e_aurc_norm"]
            x = i + (k - 1) * 0.27
            ax.bar(x, v, width=0.22, color=PCOL[meth])
            ax.text(x, v + (0.05 if v >= 0 else -0.09), f"{v:+.3f}",
                    ha="center", fontsize=4.9, rotation=90)
    ax.axhline(0, color="#999999", lw=0.8)
    ax.set_xticks(np.arange(len(DURS)))
    ax.set_xticklabels([DUR_LABEL[k] for k in DURS])
    ax.set_ylabel("E-AURC (normalized: 0 = random, 1 = oracle)")
    ax.set_ylim(-1.0, 1.45)
    ax.legend(handles=[Patch(facecolor=C_DIFF, label="diff"),
                       Patch(facecolor=C_RISK, label="risk"),
                       Patch(facecolor=C_DURONLY, label="duration-only")],
              loc="upper center", fontsize=6.4, ncol=3, framealpha=0.95)
    ax.text(0.02, 0.03,
            "values above bars (diff/risk/duration-only); risk is worse than random at 90/180 d "
            "(−0.260/−0.625)",
            transform=ax.transAxes, fontsize=5.6, ha="left", va="bottom", color="#333333")
    panel_label(ax, "(d)")

    footer(fig, "data: results/v14/p2_decision/{laio_tamea_curves,crps_check,selective_risk_curves,"
                "selective_metrics}.csv")
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return str(out)


# =====================================================================
# Figure 5 - eta response effectiveness + REV fixed-threshold
# =====================================================================
def fig05(d: dict) -> str:
    eta = d["eta"].copy()
    rev = d["rev_fixed"].copy()
    eta = eta[eta["panel"] == "second"]
    rev = rev.sort_values("horizon", key=lambda s: s.map({"7": 0, "30": 1, "90": 2, "180": 3}))
    out = FIGDIR / "fig_05_eta_downstream.png"

    fig = plt.figure(figsize=(7.8, 7.4))
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 1.3], hspace=0.68, wspace=0.30,
                          left=0.135, right=0.985, top=0.92, bottom=0.17)
    fig.suptitle("Response effectiveness (η) and REV fixed-threshold decision value - second panel",
                 fontsize=11.5, fontweight="bold", y=0.985)

    for k, dur in enumerate(DURS):
        ax = fig.add_subplot(gs[k // 2, k % 2])
        sub = eta[eta["horizon"] == dur]
        for pol, col in (("diff", C_DIFF), ("duration_only", C_DURONLY)):
            s = sub[sub["policy"] == pol].sort_values("eta")
            ax.plot(s["eta"], s["mean_effective_benefit"], color=col, lw=1.8,
                    marker="o", ms=4, label=PLABEL[pol])
        ax.axvline(0.5, color="#555555", ls="--", lw=0.8)
        ax.text(0.10, 0.965, "Verkade–Werner η = 0.5 (stars)", transform=ax.transAxes,
                fontsize=5.3, color="#555555", va="top")
        ax.axhline(0, color="#999999", lw=0.7)
        ax.set_xlim(0.2, 1.1)
        ax.set_ylim(auto=True)
        ax.set_title(f"{DUR_LABEL[dur]} · top-20% mean effective benefit "
                     f"(n = {int(sub['n_selected'].iloc[0])})", fontsize=9)
        ax.set_xlabel("effectiveness η (effective = η × realized benefit)")
        if k % 2 == 0:
            ax.set_ylabel("mean effective benefit (°C)")
        hd = sub[sub["policy"] == "diff"].iloc[0]["harmful_rate_realized"]
        hu = sub[sub["policy"] == "duration_only"].iloc[0]["harmful_rate_realized"]
        ax.text(0.985, 0.965, f"harmful: diff {hd * 100:.1f}% · dur {hu * 100:.1f}% (η-invariant)",
                transform=ax.transAxes, fontsize=5.3, ha="right", va="top", color="#333333")
        panel_label(ax, "abcd"[k])
        if k == 0:
            ax.legend(loc="lower right", fontsize=6.6, framealpha=0.95)
        for pol, col in (("diff", C_DIFF), ("duration_only", C_DURONLY)):
            s = sub[sub["policy"] == pol]
            s05 = s[s["eta"] == 0.5].iloc[0]
            y05 = s05["mean_effective_benefit"]
            ax.annotate(f"{y05:+.3f}", xy=(0.5, y05), xytext=(0.515, y05),
                        fontsize=5.4, color=col, va="center")

    # ---------------- REV fixed threshold ----------------
    for j, tau in enumerate(["zero", "panel_mean"]):
        ax = fig.add_subplot(gs[2, j])
        sub = rev[rev["tau_type"] == tau]
        x = np.arange(len(DURS))
        w = 0.33
        for i, row in enumerate(sub.to_dict("records")):
            col = C_DUR[row["horizon"]]
            ax.bar(i - w / 2, row["V_second_max"], w, color="none", edgecolor=col, lw=1.5)
            ax.bar(i + w / 2, row["V_second_fixed"], w, color=col)
            ax.text(i - w / 2, max(row["V_second_max"], 0.02) + 0.025,
                    f"V lost {row['value_loss']:.3f}", ha="center", fontsize=5.4,
                    color="#111111")
            ax.text(i + w / 2, row["V_second_fixed"] + (0.025 if row["V_second_fixed"] >= 0
                                                        else -0.05),
                    f"{row['V_second_fixed']:+.3f}", ha="center", fontsize=5.6,
                    color="#111111")
        ax.axhline(0, color="#999999", lw=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels([DUR_LABEL[k] for k in DURS])
        ax.set_ylim(-0.42, 0.70)
        ax.set_ylabel("REV V(α)")
        tau_txt = "benefit > 0" if tau == "zero" else "benefit > panel mean (+0.051 °C)"
        ax.set_title(f"Event τ = \"{tau_txt}\"", fontsize=9)
        panel_label(ax, "ef"[j])
        if j == 1:
            ax.legend(handles=[
                Patch(facecolor="none", edgecolor="#333333",
                      label="V envelope (α* per panel)"),
                Patch(facecolor="#9e9e9e", label="V fixed (α* frozen from dev panel)")],
                loc="upper right", fontsize=5.8)

    fig.text(0.5, 0.105,
             "Fixed α* keeps most of the envelope at 90/180 d for the above-mean event (0.235 vs 0.261; "
             "0.399 vs 0.422); short horizons and the zero-threshold event lose most (30 d: fixed V = "
             "−0.124 < 0, V lost 0.267).  REV: rev_fixed_threshold.csv.",
             ha="center", fontsize=6.0, color="#333333")

    footer(fig, "data: results/v14/p2_decision/{eta_sensitivity,rev_fixed_threshold}.csv")
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return str(out)


# =====================================================================
# Figure 6 - stationarity strata
# =====================================================================
def fig06(d: dict) -> str:
    st = d["stratum"]
    jj = d["dir_json"]
    st = st[st["level"] == "placement"]
    out = FIGDIR / "fig_06_strata.png"

    fig = plt.figure(figsize=(7.8, 7.6))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.2, 1.2, 1.0], hspace=0.75, wspace=0.30,
                          left=0.105, right=0.985, top=0.90, bottom=0.075)
    fig.suptitle("Stationarity stratification: differential curve vs r6-diff (second panel, "
                 "placement level)", fontsize=11.5, fontweight="bold", y=0.985)
    strata = ["stable", "moderate", "drift"]
    for k, dur in enumerate(DURS):
        ax = fig.add_subplot(gs[k // 2, k % 2])
        sub = st[st["horizon"] == dur]
        x = np.arange(len(strata))
        w = 0.32
        nets = []
        for i, stname in enumerate(strata):
            row = sub[sub["stratum"] == stname].iloc[0]
            ax.bar(i - w / 2, row["rho_diff"], w, color=C_DIFF)
            ax.bar(i + w / 2, row["rho_r6_diff"], w, color=C_R6)
            dlt = row["rho_diff"] - row["rho_r6_diff"]
            ax.text(i, max(row["rho_diff"], row["rho_r6_diff"]) + 0.02, f"Δ {dlt:+.3f}",
                    ha="center", fontsize=6.0, color="#111111")
            nets.append(int(row["n_networks"]))
        ax.axhspan(0.25, 0.35, color="#b0bec5", alpha=0.15)
        ax.axhline(0.35, color="#37474f", ls="-.", lw=1.0)
        ax.axhline(0, color="#999999", lw=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(strata)
        ax.set_ylim(-0.05, 1.12)
        ax.set_xlim(-0.7, 3.85)
        ax.set_title(f"{DUR_LABEL[dur]} - networks {nets[0]}/{nets[1]}/{nets[2]} per stratum",
                     fontsize=9)
        if k % 2 == 0:
            ax.set_ylabel("placement-level Spearman ρ")
        if k == 0:
            ax.legend(handles=[Patch(facecolor=C_DIFF, label="ρ(diff)"),
                               Patch(facecolor=C_R6, label="ρ(r6-diff)")],
                      loc="upper left", fontsize=6.6)
            ax.text(0.30, 0.90, "ρ gate 0.35 (dash-dot) · partial band\n0.25-0.35 (shaded)",
                    transform=ax.transAxes, fontsize=5.4, color="#37474f", va="top")
        panel_label(ax, "abcd"[k])
        if dur == "180":
            ax.text(2.55, 0.60, "drift 180-d:\nΔρ +0.236 vs +0.170\n(direction test\n+0.067 [0.025, "
                                "0.109],\nP(>0) = 0.9985)",
                    fontsize=5.9, color="#111111", va="top",
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#888888", alpha=0.92))
        if dur == "90":
            ax.text(2.55, 0.60, "90-d reversal:\nΔρ +0.007 vs +0.077\n(direction test\n"
                                "−0.070 [−0.111, −0.029],\nP(>0) = 0.0005)",
                    fontsize=5.9, color="#111111", va="top",
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#888888", alpha=0.92))

    ax = fig.add_subplot(gs[2, :])
    rows = [
        ("T1: per-duration Δρ, mean over horizons", jj["T1_mean_per_duration_placement"],
         jj["T1_ci"], None),
        ("T2: pooled placement Δρ", jj["T2_pooled_placement"]["mean"],
         jj["T2_pooled_placement"]["ci"], jj["T2_pooled_placement"]["prob_gt0"]),
        ("T3: pooled network Δρ", jj["T3_pooled_network"]["mean"],
         jj["T3_pooled_network"]["ci"], jj["T3_pooled_network"]["prob_gt0"]),
    ]
    yp = np.arange(len(rows))[::-1]
    for i, (lab, mean, ci, prob) in enumerate(rows):
        y = yp[i]
        ax.errorbar([mean], [y], xerr=[[mean - ci[0]], [ci[1] - mean]], fmt="o", ms=8,
                    color="#111111", ecolor="#111111", elinewidth=1.5, capsize=3.5)
        t = f"ΔΔρ = {mean:+.3f}  [{ci[0]:+.3f}, {ci[1]:+.3f}]"
        if prob is not None:
            t += f"   P(>0) = {prob:.3f}"
        ax.text(mean + 0.015, y + (0.28 if mean < 0 else 0.0), t, va="center",
                ha="left", fontsize=7.8)
    ax.axvline(0, color="#999999", lw=0.9)
    ax.set_yticks(yp)
    ax.set_yticklabels([r[0] for r in rows], fontsize=8.2)
    ax.set_xlim(-0.34, 0.30)
    ax.set_xlabel("ΔΔρ = Δρ(diff − r6-diff) in drift stratum − Δρ in stable stratum")
    ax.set_title("Direction tests (2,000 network-cluster draws): the pre-registered drift-advantage "
                 "hypothesis is NOT clearly supported - the statement is the stationarity boundary",
                 fontsize=9)
    ax.text(0.5, -0.14,
            "Strata frozen: 57 networks = stable 19 / moderate 19 / drift 19 "
            "(czechia 3/4/8 · norway 5/4/1 · united_states 11/11/10).",
            transform=ax.transAxes, fontsize=6.2, ha="center", va="top", color="#333333")
    panel_label(ax, "(e)")

    footer(fig, "data: results/v14/p3_drift/{stratum_comparison,stratum_direction_test}.csv  |  "
                "direction_test.json")
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return str(out)


# =====================================================================
# Negative-result note figures (v13 artifacts)
# =====================================================================
def note_fig01(d: dict) -> str:
    sm = d["v13_summary"]
    uc = d["v13_unit"]
    ph = d["v13_perh_net"]
    pb = d["v13_paired"]
    out = FIGDIR / "note_fig_01_loss_ranking.png"

    direct = uc[uc["subset"] == "direct"].copy()
    pooled = sm[(sm["panel"] == "second") & (sm["subset"] == "direct_874")].set_index("method")
    per_h = {}
    for g in [7, 30, 90, 180]:
        sub = direct[direct["gap_length"] == g]
        per_h[g] = (spearmanr(sub["empirical"], sub["observed"]).statistic,
                    spearmanr(sub["r6"], sub["observed"]).statistic)
    dur_only_pooled = spearmanr(direct["gap_length"], direct["observed"]).statistic

    pn = pb[(pb["panel"] == "second") & (pb["subset"] == "direct_874")]
    netrow = pn[pn["level"] == "network"].iloc[0]
    poolrow = pn[pn["level"] == "pooled"].iloc[0]

    fig, (axa, axb) = plt.subplots(1, 2, figsize=(7.8, 5.3))
    fig.subplots_adjust(top=0.90, bottom=0.38, left=0.09, right=0.985, wspace=0.24)
    fig.suptitle("Loss-ranking near-tie (v13, second panel): empirical stress curve vs station history",
                 fontsize=11, fontweight="bold", y=0.985)

    axa.set_title("(a) Unit-level Spearman ρ - 874 direct units")
    groups = [f"{g} d" for g in [7, 30, 90, 180]] + ["pooled"]
    x = np.arange(5)
    emp_vals = [per_h[g][0] for g in [7, 30, 90, 180]] + [pooled.loc["empirical", "pooled_spearman"]]
    r6_vals = [per_h[g][1] for g in [7, 30, 90, 180]] + [pooled.loc["r6", "pooled_spearman"]]
    axa.bar(x - 0.21, emp_vals, 0.4, color="#4472c4", label="empirical curve")
    axa.bar(x + 0.21, r6_vals, 0.4, color="#b58900", label="r6 station × horizon mean")
    for i, v in enumerate(emp_vals):
        axa.text(i - 0.21, v + 0.01, f"{v:.3f}", ha="center", fontsize=6.2)
    for i, v in enumerate(r6_vals):
        axa.text(i + 0.21, v + 0.01, f"{v:.3f}", ha="center", fontsize=6.2)
    axa.set_xticks(x)
    axa.set_xticklabels(groups)
    axa.set_ylabel("unit-level Spearman ρ (predicted vs observed loss, °C)")
    axa.set_ylim(0, 1.06)
    axa.legend(loc="lower left", fontsize=6.6)
    capa = [
        "computed from unit_comparison_second.csv (empirical/r6/observed); pooled rows match",
        "summary_metrics.csv: empirical 0.945 vs r6 0.942 (pooled, 874 units).",
        f"duration-only (rank by gap length): pooled ρ = {dur_only_pooled:.3f} - flat",
        "within a horizon, so per-duration ρ is n/a (ties).",
    ]
    for i, txt in enumerate(capa):
        axa.text(0.5, -0.10 - 0.062 * i, txt, transform=axa.transAxes, fontsize=5.5,
                 ha="center", va="top", color="#333333")

    axb.set_title("(b) Network-level Spearman ρ per horizon (57 networks)")
    ph2 = ph.set_index("horizon")
    x = np.arange(5)
    ev = ph2["empirical_network_spearman"].values
    rv = ph2["r6_network_spearman"].values
    ev_all = np.append(ev, pooled.loc["empirical", "network_spearman"])
    rv_all = np.append(rv, pooled.loc["r6", "network_spearman"])
    axb.bar(x - 0.21, ev_all, 0.4, color="#4472c4", label="empirical curve")
    axb.bar(x + 0.21, rv_all, 0.4, color="#b58900", label="r6 station × horizon mean")
    for i, v in enumerate(ev_all):
        axb.text(i - 0.21, v + 0.01, f"{v:.3f}", ha="center", fontsize=6.2)
    for i, v in enumerate(rv_all):
        axb.text(i + 0.21, v + 0.01, f"{v:.3f}", ha="center", fontsize=6.2)
    axb.set_xticks(x)
    axb.set_xticklabels(["7 d", "30 d", "90 d", "180 d", "pooled"])
    axb.set_ylabel("network-level Spearman ρ")
    axb.set_ylim(0, 1.06)
    axb.legend(loc="lower left", fontsize=6.6)
    dlt = ev - rv
    dlt_str = " · ".join(f"{g} d {v:+.3f}" for g, v in zip([7, 30, 90, 180], dlt))
    cap = [
        "per-horizon values as quoted in negative_result_note.md §3: emp 0.932/0.916/0.865/0.659",
        "vs r6 0.938/0.915/0.843/0.603 (7/30/90/180 d); pooled network 0.805 vs 0.763.",
        f"Δ(emp − r6): {dlt_str}",
        "convergence at 7/30 d; small advantage only at 90-180 d.",
        f"paired Δρ (2,000 draws): pooled {poolrow['delta_mean']:+.4f} "
        f"[{poolrow['ci_low']:+.4f}, {poolrow['ci_high']:+.4f}] P(Δ>0) = {poolrow['win_fraction']:.2f}",
        f"network {netrow['delta_mean']:+.4f} [{netrow['ci_low']:+.4f}, {netrow['ci_high']:+.4f}] "
        f"P(Δ>0) = {netrow['win_fraction']:.2f}",
        "CI straddles zero at both levels - the near-tie is the negative finding.",
    ]
    for i, txt in enumerate(cap):
        axb.text(0.5, -0.10 - 0.062 * i, txt, transform=axb.transAxes, fontsize=5.5,
                 ha="center", va="top", color="#333333")

    footer(fig, "data: results/revision_v13/strongest_baseline/agent_a/{summary_metrics,"
                "unit_comparison_second,per_horizon_network_spearman,paired_bootstrap}.csv")
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return str(out)


def note_fig02(d: dict) -> str:
    df = d["t08"].copy()
    df["realized_benefit"] = df["climatology_mae_deg_c"] - df["mae_deg_c"]
    r_risk = spearmanr(df["empirical_transfer_prediction"], df["realized_benefit"]).statistic
    r_clim = spearmanr(df["climatology_mae_deg_c"], df["realized_benefit"]).statistic
    out = FIGDIR / "note_fig_02_estimand.png"

    fig, (axl, axr) = plt.subplots(1, 2, figsize=(7.8, 5.0))
    fig.subplots_adjust(top=0.87, bottom=0.14, left=0.095, right=0.985, wspace=0.24)
    fig.suptitle("F1 diagnosis (v13 development corpus, 1,965 placements): what does loss ranking buy?",
                 fontsize=11, fontweight="bold", y=0.985)
    fig.text(0.5, 0.93,
             "realized benefit = MAE(climatology default) − MAE(model), computed from "
             "placement_thermal_metrics.csv; benefit mean +0.615 °C, harmful share 15.2%",
             ha="center", va="top", fontsize=6.2, color="#333333")

    for g, c in ((7, C_DUR["7"]), (30, C_DUR["30"]), (90, C_DUR["90"])):
        sub = df[df["gap_length"] == g]
        axl.scatter(sub["empirical_transfer_prediction"], sub["realized_benefit"],
                    s=6, alpha=0.3, color=c, edgecolors="none", label=f"{g} d")
        axr.scatter(sub["climatology_mae_deg_c"], sub["realized_benefit"],
                    s=6, alpha=0.3, color=c, edgecolors="none", label=f"{g} d")
    axl.set_title("model-error ranking (v13 empirical): Spearman ρ = −0.230")
    axr.set_title("default-difficulty ranking (climatology): Spearman ρ = +0.659")
    axl.set_xlabel("empirical transfer prediction - predicted model MAE (°C)")
    axr.set_xlabel("climatology MAE of the same gaps (°C)")
    ylim = (-3.5, 5.6)
    for ax in (axl, axr):
        ax.set_ylabel("realized benefit (°C)\n(MAE(clim) − MAE(model))", labelpad=8)
        ax.axhline(0, color="#999999", lw=0.8, ls=":")
        ax.axhline(df["realized_benefit"].mean(), color="#555555", lw=0.8, ls="--")
        ax.set_ylim(*ylim)
        ax.legend(loc="lower right", fontsize=7.0, title="gap length")
    axl.set_xlim(0.05, 3.15)
    axr.set_xlim(0, 6.8)
    axr.text(0.985, 0.97,
             "dashed: panel mean benefit +0.615 °C.\nThe benefit signal lives in the default's "
             "difficulty, not in the model's error -\nthe estimand that v14 adopts.",
             transform=axr.transAxes, fontsize=6.0, va="top", ha="right", color="#333333",
             bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#999999", alpha=0.9))

    footer(fig, "data: results/revision_v12/t08_downstream_metrics/agent_a/placement_thermal_metrics.csv "
                f"(benefit column computed; Spearman recomputed here: {r_risk:.3f} / {r_clim:.3f})")
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return str(out)


def note_fig03(d: dict) -> str:
    df = d["t08"].copy()
    df["realized_benefit"] = df["climatology_mae_deg_c"] - df["mae_deg_c"]
    n = int(round(0.2 * len(df)))
    assert n == 393, n

    loo = np.empty(len(df))
    for _, v in df.groupby(["network_id", "station_id", "gap_length"]):
        vals = v["realized_benefit"].values
        for i in range(len(v)):
            idx = v.index[i]
            mask = np.arange(len(vals)) != i
            loo[df.index.get_loc(idx)] = vals[mask].mean()
    df["loo_benefit"] = loo
    df["gap_length_rank"] = df["gap_length"].astype(float)
    out = FIGDIR / "note_fig_03_budget.png"

    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    fig.subplots_adjust(top=0.85, bottom=0.19, left=0.13, right=0.985)
    fig.suptitle("Top-20% fixed-budget mean realized benefit by ranking rule "
                 "(v13 t08 corpus: 1,965 placements, 393 treated)", fontsize=11,
                 fontweight="bold", y=0.975)

    d90 = df[df["gap_length"] == 90]
    gap_mean = d90["realized_benefit"].mean()     # expectation under the random top-20% tie-break
    gap_harm = (d90["realized_benefit"] < 0).mean()
    rows = [
        ("risk", C_RISK, "empirical_transfer_prediction", None, None),
        ("gap length", C_DURONLY, "gap_length_rank", gap_mean, gap_harm),
        ("LOO benefit", C_ORACLE, "loo_benefit", None, None),
    ]
    pm = df["realized_benefit"].mean()
    ph = (df["realized_benefit"] < 0).mean()
    for i, (lab, col, key, mfix, hfix) in enumerate(rows):
        if mfix is None:
            sel = df.nlargest(n, key)
            m = sel["realized_benefit"].mean()
            h = (sel["realized_benefit"] < 0).mean()
        else:
            m, h = mfix, hfix
        ax.bar(i, m, 0.5, color=col)
        ax.text(i, m + 0.03, f"{m:+.3f} °C", ha="center", fontsize=8.4, fontweight="bold")
        ax.text(i, -0.32, f"harmful {h * 100:.1f}%", ha="center", fontsize=7.2, color="#555555")
    ax.axhline(pm, color="#111111", ls="--", lw=1.1)
    ax.text(2.32, pm + 0.02, f"panel mean {pm:+.3f} °C\n(panel harmful {ph * 100:.1f}%)",
            fontsize=7.0, ha="left", color="#111111")
    ax.axhline(0, color="#999999", lw=0.8)
    ax.set_xticks(np.arange(3))
    ax.set_xticklabels([r[0] for r in rows])
    ax.set_ylabel("mean realized benefit of top-20% (°C)")
    ax.set_ylim(-0.6, 1.3)
    ax.set_xlim(-0.6, 4.6)
    ax.text(0.5, -0.16,
            "The model-error ranking concentrates harm (top-20% harmful 37.7% > panel 15.2%); gap-length "
            "and the in-sample LOO benefit rank °C-benefit far better. Loss ranking is not intervention "
            "value -\nv14 reframes the estimand as benefit over the default handling.  Gap-length bar: "
            "mean of the longest-gap (90 d) tier, the exact expectation of the top-20% under the "
            "required random tie-break.",
            transform=ax.transAxes, fontsize=6.6, ha="center", va="top", color="#111111")

    footer(fig, "data: results/revision_v12/t08_downstream_metrics/agent_a/placement_thermal_metrics.csv "
                "(budget rows computed here; benefit = climatology_mae_deg_c − mae_deg_c; "
                "LOO = leave-one-placement-out per station-gap)")
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return str(out)


# =====================================================================
# v13 legacy Fig 1 - design schematic (superseded; reproduced cheaply)
# =====================================================================
def legacy_workflow(d: dict) -> str:
    out = FIGDIR / "fig_v13_legacy_workflow.png"
    fig, ax = plt.subplots(figsize=(7.6, 5.4))
    fig.subplots_adjust(top=0.99, bottom=0.012, left=0.005, right=0.995)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    ax.text(0.5, 99.2, "v13 legacy Fig 1 - nested temporal design, support tiers, and regions "
                       "(superseded design schematic; spec: figure_plan_v13.md §Fig 1)",
            fontsize=10, fontweight="bold", ha="center", va="top")

    def box(x0, y0, w, h, fc, ec, hatch=None, tx=None, fs=7.0, lw=1.0, tc="#111111"):
        ax.add_patch(Rectangle((x0, y0), w, h, facecolor=fc, edgecolor=ec, hatch=hatch,
                               lw=lw, zorder=2))
        if tx:
            ax.text(x0 + w / 2, y0 + h / 2, tx, ha="center", va="center", fontsize=fs,
                    zorder=3, color=tc)

    # row 1: second-panel record, outer split
    ax.text(0.5, 96.2, "second panel: 57 networks (32 US · 15 CZ · 10 NO) - outer chronological split",
            fontsize=8, ha="center", va="top")
    box(0, 85.5, 70, 8, "#dbe7f5", "#1f4e9c", tx="fitting years - 70% of record")
    box(70, 85.5, 30, 8, "#fce8e6", "#c62828", tx="outer evaluation - 30%\n(outcomes untouched)")
    ax.annotate("", xy=(70, 86), xytext=(70, 94), arrowprops=dict(arrowstyle="->", lw=1))

    # row 2: nested split inside fitting years
    box(0, 67.5, 49, 8, "#dbe7f5", "#1f4e9c", tx="nested fit - 70% of fitting years")
    box(49, 67.5, 21, 8, "#fff2cc", "#d97706", tx="artificial-gap truth - 30%")
    ax.text(0.5, 79.2, "stress tests cut artificial gaps in the nested truth years - "
                       "4 durations × 4 seasonal strata (DJF/MAM/JJA/SON)", fontsize=8,
            ha="center", va="top")
    for x, lbl in ((51.5, "7 d"), (57, "30 d"), (62.5, "90 d"), (68, "180 d")):
        ax.plot([x], [65.8], marker="v", color="#d97706", ms=4.5)
        ax.text(x, 64.0, lbl, fontsize=5.8, ha="center", color="#d97706")

    # row 3: duration axis with regions (log-linear proxy)
    ax.text(0.5, 59.6, "support regions on the duration axis (log, 3-365 d):", fontsize=7.5,
            ha="center", va="top")
    y0, h = 52.0, 4.0

    def xlog(day):
        return (math.log10(day) - math.log10(3)) / (math.log10(365) - math.log10(3)) * 100

    x7, x14, x60, x180 = (xlog(dd) for dd in (7, 14, 60, 180))
    ax.plot([0, 100], [y0 + h / 2, y0 + h / 2], color="#333333", lw=0.7, zorder=1)
    ax.add_patch(Rectangle((x7, y0), 100 - x7, h, facecolor="#dbe7f5",
                           edgecolor="#1f4e9c", lw=0.8, zorder=2))
    ax.add_patch(Rectangle((x14, y0), x60 - x14, h, facecolor="none",
                           edgecolor="#555555", hatch="//", lw=0.8, zorder=3))
    ax.add_patch(Rectangle((x180, y0), 100 - x180, h, facecolor="#fadbd8",
                           edgecolor="#c62828", hatch="///", lw=0.8, zorder=4))
    for xd, lbl in ((0, "3 d"), (x7, "7 d"), (xlog(30), "30 d"), (xlog(90), "90 d"),
                    (x180, "180 d"), (100, "365 d")):
        ha = "left" if xd < 1 else ("right" if xd > 97 else "center")
        ax.text(xd, y0 - 0.8, lbl, fontsize=5.4, ha=ha, va="bottom", color="#111111")
    ax.text(x7 + 3, y0 + h + 2.2, "direct 7/30/90/180 d\n874 units (224/224/220/206)",
            fontsize=6.6, ha="left", va="top")
    ax.text((x14 + x60) / 2, y0 + h + 2.2, "interpolated 14/60 d\n448 units (224/224)",
            fontsize=6.6, ha="center", va="top")
    ax.text(x180 - 1, y0 + h + 2.2, "extrapolated 365 d\n124 units · 30 networks\n"
            "(8.6% units · 28.9% loss)", fontsize=6.6, ha="right", va="top")
    ax.text(50, 39.2, "monotone-duration surface fit inside fitting years; extrapolation beyond "
                      "180 d fails (90% interval coverage 46.8%)", fontsize=6.8,
            ha="center", va="top")

    # row 4: five-level support hierarchy (second-panel counts)
    ax.text(0.5, 35.8, "support hierarchy for curve cells (second panel):", fontsize=7.5,
            ha="center", va="top")
    tiers_a = [
        ("station × gap × season", "841 units · 57 networks", "#dbe7f5"),
        ("station × gap", "9 units · 2 networks", "#dbe7f5"),
        ("network × gap", "0", "#eaeaea"),
    ]
    tiers_b = [
        ("network-mean fallback", "596 units · 57 networks (24 at direct horizons)", "#eaeaea"),
        ("unavailable", "0", "#eaeaea"),
    ]
    x = 0
    for name, cnt, c in tiers_a:
        w = 5 + max(len(name), len(cnt)) * 0.9
        box(x, 28.0, w, 6.6, c, "#555555", tx=f"{name}\n{cnt}", fs=5.9)
        x += w + 1.2
    x = 0
    for name, cnt, c in tiers_b:
        w = 5 + max(len(name), len(cnt)) * 0.85
        box(x, 19.5, w, 6.6, c, "#555555", tx=f"{name}\n{cnt}", fs=5.9)
        x += w + 1.2

    # evidence legend
    ax.text(0.5, 17.0, "evidence role - colours repeat on every v13 figure:", fontsize=7.5,
            ha="center", va="top")
    lg = [
        ("frozen pre-outcome", "#1f77b4", ""),
        ("post-hoc v12 development", "#7f7f7f", ""),
        ("v13 harmonization", "#ff7f0e", "//"),
        ("future preregistered third panel", "#2ca02c", ""),
    ]
    x = 5
    for name, c, hatch in lg:
        ax.add_patch(Rectangle((x, 12.2), 2.2, 2.2, facecolor="white" if hatch else c,
                               edgecolor=c, hatch=hatch, lw=1.0))
        ax.text(x + 3.2, 13.3, name, fontsize=6.8, va="center")
        x += 5.0 + len(name) * 0.72
    ax.text(0.5, 8.6, "Panels: A chronology (rows 1-2); B support tiers over the duration axis "
                      "(rows 3-4); C evidence-provenance legend.", fontsize=6.8,
            ha="center", va="top")
    ax.text(0.5, 6.2, "Superseded in v14: ranking questions re-expressed for the benefit estimand - "
                      "see note_fig_01…03 and v13_legacy_figs.txt.", fontsize=6.8,
            ha="center", va="top", color="#555555")

    footer(fig, "data: design schematic per paper_archived/development_v13/figure_plan_v13.md §Fig 1 "
                "(counts as tabulated there, from revision_v12 t02/t03/t04 artifacts)")
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return str(out)


def write_legacy_txt() -> str:
    p = FIGDIR / "v13_legacy_figs.txt"
    text = """v13 legacy figures (paper_archived/development_v13/figure_plan_v13.md) - supersession note
=====================================================================================

The five v13 figure spec sources all live in figure_plan_v13.md
(paper_archived/development_v13/), with supporting artifacts under
results/revision_v12/* and results/revision_v13/*:

  1. Fig 1 - nested temporal design, support tiers, interpolation/extrapolation
     regions (design schematic, no statistical estimation).
  2. Fig 2 - strongest-baseline external comparison (second panel, direct units):
     empirical vs station x horizon mean (r6) vs simple descriptors; paired
     network-bootstrap drho; within-network effects.
  3. Fig 3 - duration response across supported/interpolated/extrapolated
     regions (predicted vs observed loss vs duration; 90% interval coverage by
     support tier; support-based abstention rule).
  4. Fig 4 - model-selection coverage-regret frontier (unit and network
     coverage; harmonization floors).
  5. Fig 5 - downstream incremental benefit of reconstruction vs three
     untreated baselines (no-fill, climatology, linear interpolation) across
     ten thermal metrics.

Art produced here:
  - fig_v13_legacy_workflow.png : v13 Fig 1 redrawn as a design schematic
    directly from the figure_plan_v13.md spec (schematic only; counts as
    tabulated in that section). Cheap to produce - no estimation involved.

Why each remaining figure is superseded (one line each; see
paper_archived/v14_plan/negative_result_note.md "Relationship to v14"):

  - v13 Fig 2 (loss-ranking near-tie, empirical vs r6): superseded by
    note_fig_01.png + the negative-result note; loss ranking is now cited as
    the "prior work we no longer claim" (pooled 0.945 vs 0.942, paired drho CI
    straddling zero).
  - v13 Fig 3 (duration response + extrapolation failure): superseded by the
    per-duration-only panels of fig_01/fig_02/fig_03 (no-pooling rule; the
    365-d extrapolation boundary is quoted as context in the note, not
    re-plotted).
  - v13 Fig 4 (model-selection coverage-regret): superseded by fig_04.png
    (decision layer on the benefit estimand: EC(xi)/delta, selective
    risk/coverage, E-AURC) - model-family selection is out of the v14 scope.
  - v13 Fig 5 (downstream thermal-metric benefit vs three baselines):
    superseded by fig_05.png (eta response-effectiveness envelope + REV
    fixed-threshold value loss on the benefit estimand); the v13 F1 diagnosis
    (risk ranks model MAE, not benefit) is reproduced in
    note_fig_02/note_fig_03.png.

All five v13 content areas are therefore covered by the v14 figure set plus
the three negative-result note figures listed in the task deliverable.
"""
    p.write_text(text)
    return str(p)


# =====================================================================
# main
# =====================================================================
def main() -> None:
    d = _load()

    # --- consistency assertions (annotations trace to archived CSVs) ---
    mh = d["metrics_h"]
    chk = mh[mh["horizon"].isin(DURS)].set_index("horizon")
    exp_diff = {"7": 0.297, "30": 0.303, "90": 0.370, "180": 0.555}
    exp_risk = {"7": 0.184, "30": 0.129, "90": -0.192, "180": -0.540}
    for k in DURS:
        assert abs(chk.loc[k, "diff_rho"] - exp_diff[k]) < 5e-4, f"diff rho drift {k}"
        assert abs(chk.loc[k, "risk_rho"] - exp_risk[k]) < 5e-4, f"risk rho drift {k}"
    p0b = d["p0_bwd"]
    p0b = p0b[p0b["budget"] == 0.2]
    a180 = p0b[(p0b["horizon"] == "180") & (p0b["predictor"] == "diff")]["mean_realized_benefit"].iloc[0]
    b180 = p0b[(p0b["horizon"] == "180") & (p0b["predictor"] == "duration")]["mean_realized_benefit"].iloc[0]
    c180 = p0b[(p0b["horizon"] == "180") & (p0b["predictor"] == "risk")]["mean_realized_benefit"].iloc[0]
    assert abs(a180 + 0.636) < 5e-3 and abs(b180 + 1.647) < 5e-3 and abs(c180 + 2.881) < 5e-3
    paired = d["paired"]
    s_risk = paired[(paired["panel"] == "second") & (paired["comparator"] == "risk")].iloc[0]
    assert abs(s_risk["mean"] - 1.087) < 1e-3
    print("annotation consistency checks passed")

    produced = [
        fig01(d),
        fig02(d),
        fig03(d),
        fig04(d),
        fig05(d),
        fig06(d),
        note_fig01(d),
        note_fig02(d),
        note_fig03(d),
        legacy_workflow(d),
    ]
    for p in produced:
        print("wrote", p)
    print("wrote", write_legacy_txt())


if __name__ == "__main__":
    main()
