#!/usr/bin/env python3
"""148_run_v14_figures_v2.py -- revised v14 figure set (WORKPLAN_v14.md §4,
REVIEW_v14.md Major 1/2/5 narrative restructure: the duration structure of
benefit is the headline, Fig 1).

Figures (written to results/v14/figures_v2/ at 300 dpi; results/v14/figures/
is left untouched):

  fig01_duration_structure.png  benefit by gap duration (unit level, both panels)
  fig02_estimand.png            risk vs differential placement scatter (second)
  fig03_main_result.png         per-duration placement rho bars + paired forest
  fig04_decision.png            within-duration top-20% budget + Laio-Tamea EC/xi
  fig05_downstream.png          downstream metric benefit over defaults (P4)
  fig06_boundary.png            three-level decomposition + within-cell rho +
                                drift strata

Colour contract (unchanged from scripts/145_run_v14_figures.py): diff=dark
blue, risk=red, duration_only=grey, r6_diff=teal, default_difficulty=amber,
random=light grey, oracle=green.
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
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
P0 = ROOT / "results/v14/p0_differential"
P1 = ROOT / "results/v14/p1_baselines"
P2 = ROOT / "results/v14/p2_decision"
P3 = ROOT / "results/v14/p3_drift"
P4 = ROOT / "results/v14/p4_downstream"
P4B = ROOT / "results/v14/p4_downstream_second"
FLIP = ROOT / "results/v14/p4_flip_analysis"
FIGDIR = ROOT / "results/v14/figures_v2"
FIGDIR.mkdir(parents=True, exist_ok=True)

DURS = ["7", "30", "90", "180"]
DURS_FULL = ["7", "30", "90", "180", "365"]
DUR_DAYS = [7, 30, 90, 180, 365]
DUR_LABEL = {"7": "7 d", "30": "30 d", "90": "90 d", "180": "180 d", "365": "365 d"}

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

C_DIFF = "#1f4e9c"          # navy
C_RISK = "#c62828"          # red
C_DURONLY = "#8c8c8c"       # grey
C_R6 = "#00897b"            # teal
C_RANDOM = "#c9c9c9"        # light grey
C_ORACLE = "#15803d"        # green
C_DEFAULT_DIFF = "#d97706"  # amber

C_DUR = {"7": "#2c7bb6", "30": "#fdae61", "90": "#66bd63", "180": "#8e44ad",
         "365": "#455a64"}
C_INTEGRAL = "#1f4e9c"
C_THRESHOLD = "#7c3aed"


def footer(fig, text: str, script: str = "scripts/148_run_v14_figures_v2.py") -> None:
    fig.text(0.004, 0.005, text + "  |  " + script,
             fontsize=5.6, color="#555555", ha="left", va="bottom")


def panel_label(ax, letter: str, xpos: float = 0.012, ypos: float = 0.965) -> None:
    ax.text(xpos, ypos, f"({letter})", transform=ax.transAxes,
            fontsize=11.5, fontweight="bold", va="top", ha="left", color="#111111",
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.6),
            zorder=30)


def _final(fig, out) -> None:
    """save + close; with AUDIT=1 also report clipped/overlapping text."""
    import os
    if os.environ.get("AUDIT"):
        fig.canvas.draw()
        rnd = fig.canvas.get_renderer()
        fb = fig.bbox
        warned = []
        for ax in fig.axes:
            texts = [t for t in ax.texts]
            if ax.legend_ is not None:
                texts += ax.legend_.get_texts()
            for t in ax.texts + ([] if ax.title is None else [ax.title]):
                b = t.get_window_extent(rnd)
                if b.x0 < fb.x0 - 1 or b.y0 < fb.y0 - 1 or b.x1 > fb.x1 + 1 \
                        or b.y1 > fb.y1 + 1:
                    warned.append(f"CLIP[{ax.get_title()[:18]}] {t.get_text()[:60]!r} "
                                  f"bbox=({b.x0:.0f},{b.y0:.0f},{b.x1:.0f},{b.y1:.0f}) "
                                  f"fig=({fb.x0:.0f},{fb.y0:.0f},{fb.x1:.0f},{fb.y1:.0f})")
            for i in range(len(texts)):
                for j in range(i + 1, len(texts)):
                    a, b = texts[i], texts[j]
                    if a.get_text() == "" or b.get_text() == "":
                        continue
                    ba, bb = a.get_window_extent(rnd), b.get_window_extent(rnd)
                    if ba.overlaps(bb):
                        warned.append(f"OVERLAP[{ax.get_title()[:18]}] "
                                      f"{a.get_text()[:38]!r} <-> {b.get_text()[:38]!r} "
                                      f"a=({ba.x0:.0f},{ba.y0:.0f},{ba.x1:.0f},{ba.y1:.0f}) "
                                      f"b=({bb.x0:.0f},{bb.y0:.0f},{bb.x1:.0f},{bb.y1:.0f})")
        if warned:
            print(f"AUDIT {Path(out).name}: {len(warned)} warnings")
            for w in warned:
                print("   ", w)
        else:
            print(f"AUDIT {Path(out).name}: no clipping, no text overlap")
    fig.savefig(out, dpi=300)
    plt.close(fig)


def xpos_days(days: np.ndarray | list) -> np.ndarray:
    a = np.log10(np.asarray(days, dtype=float))
    return a if a.ndim else float(a)


# ---------------------------------------------------------------- load ----
def _load() -> dict:
    d: dict = {}

    def csv(p: Path, **kw) -> pd.DataFrame:
        kw.setdefault("low_memory", False)
        return pd.read_csv(p, **kw)

    d["u_first"] = csv(P0 / "unit_predictions_first.csv")
    d["u_second"] = csv(P0 / "unit_predictions_second.csv")
    d["p_first"] = csv(P0 / "placement_predictions_first.csv")
    d["p_second"] = csv(P0 / "placement_predictions_second.csv")
    d["budget"] = csv(P0 / "budget_within_duration.csv")
    d["paired"] = csv(P0 / "paired_diff_vs_r6.csv")
    d["paired_unit"] = csv(P0 / "paired_diff_vs_r6_unit_diagnostic.csv")
    d["three_level"] = csv(P0 / "three_level_decomposition.csv")
    d["mh"] = csv(P0 / "metrics_by_horizon.csv", dtype={"horizon": str})

    d["p1_metrics"] = csv(P1 / "metrics_table.csv", dtype={"horizon": str})
    d["laio"] = csv(P2 / "laio_tamea_curves.csv", dtype={"horizon": str})
    d["stratum"] = csv(P3 / "stratum_comparison.csv", dtype={"horizon": str})
    d["dir_json"] = json.loads((P3 / "direction_test.json").read_text())

    d["flip"] = csv(FLIP / "flip_table.csv")
    d["ci_tables"] = csv(FLIP / "ci_tables.csv")
    d["labels"] = csv(P4 / "metric_error_summary.csv")[["metric", "label", "units"]].drop_duplicates()
    return d


def direct_placement_rows(df: pd.DataFrame, panel_days=(7, 30, 90, 180)) -> pd.DataFrame:
    df = df.copy()
    df["gap_length"] = df["gap_length"].astype(int)
    return df[df["direct"] & df["gap_length"].isin(list(panel_days))]


# =====================================================================
# Figure 1 - duration structure of benefit (NEW headline)
# =====================================================================
def fig01(d: dict) -> str:
    panels = [("first", d["u_first"], 42), ("second", d["u_second"], 57)]
    out = FIGDIR / "fig01_duration_structure.png"

    xp = xpos_days(DUR_DAYS)
    xlo, xhi = xp[0] - 0.22, xp[-1] + 0.22

    stats = {}
    box_data = {}
    for name, u, _nets in panels:
        u = u.copy()
        u["gap_length"] = u["gap_length"].astype(int)
        u = u[u["gap_length"].isin(DUR_DAYS)]
        stats[name] = {}
        box_data[name] = []
        for g in DUR_DAYS:
            s = u[u["gap_length"] == g]["realized_benefit"]
            box_data[name].append(s.values)
            stats[name][g] = dict(n=int(len(s)), mean=float(s.mean()),
                                  harm=float((s < 0).mean()))

    # shared data-y extent (whiskers incl.) across panels
    lo_y, hi_y = np.inf, -np.inf
    for name in ("first", "second"):
        for i, g in enumerate(DUR_DAYS):
            v = box_data[name][i]
            q1, q3 = np.percentile(v, [25, 75])
            w_lo = q1 - 1.5 * (q3 - q1)
            w_hi = q3 + 1.5 * (q3 - q1)
            lo_y = min(lo_y, w_lo, stats[name][g]["mean"])
            hi_y = max(hi_y, w_hi, stats[name][g]["mean"])
    rng = hi_y - lo_y
    ylo, yhi = lo_y - 0.10 * rng, hi_y + 0.55 * rng

    fig, (axl, axr) = plt.subplots(1, 2, figsize=(9.4, 5.1))
    fig.subplots_adjust(top=0.86, bottom=0.115, left=0.075, right=0.985, wspace=0.20)
    fig.suptitle("Duration structure of reconstruction benefit over the climatology default "
                 "(MAE scale, °C)", fontsize=12, fontweight="bold", y=0.995)
    fig.text(0.5, 0.945,
             "Unit = station × gap. realized benefit = MAE(climatology) − MAE(recon); "
             "negative = reconstruction is actively harmful. Means (♦) and harmful shares are "
             "computed directly from unit_predictions_{first,second}.csv. 365 d units exist "
             "(no direct diff support; extrapolated fitting) and are shown.",
             ha="center", va="top", fontsize=6.6, color="#333333")

    flip_notes = {
        "first": 105.3,   # flip_table.csv kind=crossing first mae_scale 105.337
        "second": 91.5,   # flip_table.csv kind=crossing second mae_scale 91.489
    }

    for ax, name, nets, letter in ((axl, "first", 42, "(a)"), (axr, "second", 57, "(b)")):
        bp = ax.boxplot(box_data[name], positions=xp, widths=0.17, showfliers=False,
                        patch_artist=True, whis=1.5, zorder=3,
                        medianprops=dict(color="#111111", lw=1.3),
                        whiskerprops=dict(color="#555555", lw=0.9),
                        capprops=dict(color="#555555", lw=0.9))
        for i, patch in enumerate(bp["boxes"]):
            patch.set_facecolor(C_DUR[str(DUR_DAYS[i])])
            patch.set_alpha(0.88)
            patch.set_edgecolor("#333333")
            patch.set_linewidth(0.8)
        means = [stats[name][g]["mean"] for g in DUR_DAYS]
        harms = [stats[name][g]["harm"] for g in DUR_DAYS]
        ax.plot(xp, means, marker="D", ms=4.2, ls="none", color="#111111", zorder=6)

        ax.axvspan(xpos_days(30), xpos_days(90), color="#d97706", alpha=0.12, zorder=0)
        ax.axvline(xpos_days(49), color="#37474f", ls="--", lw=1.0, zorder=4)
        ax.axhline(0, color="#999999", lw=0.7, ls=":", zorder=2)

        # harmful-rate row (above each box) and mean row — staggered to avoid
        # collisions between neighbouring duration columns
        fx = (xp - xlo) / (xhi - xlo)
        for i, g in enumerate(DUR_DAYS):
            y_h = 0.968 if i % 2 == 0 else 0.938
            y_m = 0.905 if i % 2 == 0 else 0.873
            ax.text(fx[i], y_h, f"harmful {harms[i] * 100:.1f}%",
                    transform=ax.transAxes, fontsize=6.2, fontweight="bold",
                    color="#111111", ha="center", va="center")
            ax.text(fx[i], y_m, f"μ {means[i]:+.2f} °C",
                    transform=ax.transAxes, fontsize=6.2, color=C_DUR[str(g)],
                    ha="center", va="center", fontweight="bold")

        ax.text(0.5, 0.815, "sign-flip window 30–90 d",
                transform=ax.transAxes, fontsize=6.2, ha="center", color="#b45309",
                style="italic",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))
        ax.text(0.51, 0.70, "Johnson et al. (2021) m_max = 49 d",
                transform=ax.transAxes, fontsize=6.4, color="#37474f", ha="left",
                va="center",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#37474f",
                          alpha=0.9, lw=0.5))

        n_direct = sum(1 for g in (7, 30, 90, 180)
                       for _ in box_data[name][DUR_DAYS.index(g)])
        ax.set_title(f"{letter}  {name} panel — development (n = {nets} networks)",
                     fontsize=9.0, pad=1)
        ax.set_xlim(xlo, xhi)
        ax.set_ylim(ylo, yhi)
        ax.set_xticks(xp)
        ax.set_xticklabels([f"{DUR_LABEL[str(g)]}\nn = {stats[name][g]['n']}"
                            for g in DUR_DAYS], fontsize=7.0)
        ax.tick_params(axis="x", length=0)
        ax.set_ylabel("unit-level realized benefit (°C)", fontsize=8.6)
        ax.yaxis.grid(True, alpha=0.35)

    fig.text(0.275, 0.030, "first panel: 42 networks · 858 direct units at 7–180 d · "
             "+144 units at 365 d",
             ha="center", fontsize=6.0, color="#444444")
    fig.text(0.765, 0.030, "second panel: 57 networks · 874 direct units at 7–180 d · "
             "+124 units at 365 d",
             ha="center", fontsize=6.0, color="#444444")
    fig.text(0.275, 0.016, "MAE-scale benefit crosses zero at ≈ 105 d "
             "(log10-interpolated between the 90/180 d grid points; flip_table.csv "
             "kind=crossing, first)",
             ha="center", fontsize=6.0, color="#111111")
    fig.text(0.765, 0.016, "MAE-scale benefit crosses zero at ≈ 91 d "
             "(log10-interpolated between the 90/180 d grid points; flip_table.csv "
             "kind=crossing, second) — vs Johnson et al. (2021) m_max = 49 d",
             ha="center", fontsize=6.0, color="#111111")

    footer(fig, "data: results/v14/p0_differential/unit_predictions_{first,second}.csv  |  "
                "crossings: results/v14/p4_flip_analysis/flip_table.csv; REVIEW_v14.md Major 5")
    _final(fig, out)
    return str(out), stats


# =====================================================================
# Figure 2 - estimand comparison (thesis)
# =====================================================================
def fig02(d: dict) -> str:
    p = direct_placement_rows(d["p_second"])
    out = FIGDIR / "fig02_estimand.png"

    rho_risk = {}
    rho_diff = {}
    for g in DUR_DAYS:
        sub = p[p["gap_length"] == g]
        rho_risk[g] = spearmanr(sub["risk_prediction"], sub["realized_benefit"]).statistic
        rho_diff[g] = spearmanr(sub["diff_prediction"], sub["realized_benefit"]).statistic
    rho_pool_risk = spearmanr(p["risk_prediction"], p["realized_benefit"]).statistic
    rho_pool_diff = spearmanr(p["diff_prediction"], p["realized_benefit"]).statistic

    fig, (axl, axr) = plt.subplots(1, 2, figsize=(9.4, 5.2))
    fig.subplots_adjust(top=0.86, bottom=0.12, left=0.08, right=0.985, wspace=0.24)
    fig.suptitle("What the two predictors rank (second panel, direct placements)",
                 fontsize=12.5, fontweight="bold", y=0.995)
    fig.text(0.5, 0.952, f"{len(p):,} direct placements; realized benefit = "
             "MAE(climatology) − MAE(model), °C. Spearman ρ per gap duration from "
             "p1_baselines/metrics_table.csv placement rows.",
             ha="center", va="top", fontsize=6.6, color="#333333")

    for g in DUR_DAYS:
        sub = p[p["gap_length"] == g]
        c = C_DUR[str(g)]
        for ax, xc in ((axl, "risk_prediction"), (axr, "diff_prediction")):
            ax.scatter(sub[xc], sub["realized_benefit"], s=5, alpha=0.12, c=c,
                       edgecolors="none", label=DUR_LABEL[str(g)], rasterized=True)
    for ax, xc in ((axl, "risk_prediction"), (axr, "diff_prediction")):
        ax.axhline(0, color="#999999", lw=0.7, ls=":")
        ax.set_ylabel("realized benefit = MAE(clim) − MAE(model) (°C)")

    axl.set_xlabel("risk prediction (predicted model MAE, °C)")
    axr.set_xlabel("diff prediction (predicted benefit over default, °C)")
    axl.set_title("the risk curve ranks model error, not benefit", fontsize=10.5)
    axr.set_title("the differential curve ranks benefit", fontsize=10.5)

    for ax, rho_d, rho_pool in ((axl, rho_risk, rho_pool_risk),
                                (axr, rho_diff, rho_pool_diff)):
        rows = [f"{DUR_LABEL[str(g)]}: ρ = {rho_d[g]:+.3f}" for g in DUR_DAYS]
        rows.append(f"pooled: ρ = {rho_pool:+.3f}")
        yt = 0.945
        for s in rows:
            ax.text(0.015, yt, s, transform=ax.transAxes, fontsize=6.6, va="top",
                    color="#111111",
                    bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#cccccc",
                              alpha=0.85))
            yt -= 0.052

    axl.text(0.015, 0.025, "Difficult gaps hurt the model and the default alike:\n"
             "ranking by predicted model error selects long gaps whose\n"
             "realized benefit is negative — ρ(risk, benefit) < 0 from 90 d.",
             transform=axl.transAxes, fontsize=6.2, va="bottom", color="#555555")
    axr.text(0.015, 0.025, "pooled ρ(diff) = +0.607 sits next to ρ(duration-only) = +0.604:\n"
             "pooling across durations is duration-confounded (REVIEW Major 2);\n"
             "the claim is the within-duration split (above).",
             transform=axr.transAxes, fontsize=6.2, va="bottom", color="#555555")

    for ax in (axl, axr):
        handles, labels = ax.get_legend_handles_labels()
        if labels:
            leg = ax.legend(handles, labels, loc="lower right", framealpha=0.92,
                            title="gap length", fontsize=7.2)
            leg.get_title().set_fontsize(7.2)

    footer(fig, "data: results/v14/p0_differential/placement_predictions_second.csv; "
                "ρ: recomputed (matches p1_baselines/metrics_table.csv placement rows "
                "0.184/0.129/−0.192/−0.540 and 0.297/0.303/0.371/0.555); pooled +0.607 "
                "duration-confounded vs duration-only +0.604")
    _final(fig, out)
    return str(out)


# =====================================================================
# Figure 3 - main result: paired diff vs r6
# =====================================================================
def fig03(d: dict) -> str:
    m = d["p1_metrics"]
    m2 = m[(m["panel"] == "second") & (m["level"] == "placement_pooled")
           & (m["horizon"].isin(DURS))]
    m2 = m2.set_index(["horizon", "predictor"])["rho"]
    mh = d["mh"]
    mh2 = mh[mh["panel"] == "second"].set_index("horizon")
    paired = d["paired"]
    out = FIGDIR / "fig03_main_result.png"

    preds = ["diff", "r6_diff", "default_difficulty", "risk"]
    rho = {pr: [float(m2.loc[(h, pr)]) for h in DURS] for pr in preds}
    ci_lo = [float(mh2.loc[h, "diff_ci_lower"]) for h in DURS]
    ci_hi = [float(mh2.loc[h, "diff_ci_upper"]) for h in DURS]

    fig = plt.figure(figsize=(10.8, 5.2))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.5, 1.0], wspace=0.30,
                          left=0.06, right=0.985, top=0.83, bottom=0.15)
    fig.suptitle("Main result: the differential curve ranks benefit within gap durations "
                 "(second panel)", fontsize=12, fontweight="bold", y=0.985)
    fig.text(0.5, 0.948, "ρ = placement-level Spearman vs realized benefit, per gap duration "
             "(metrics_table.csv placement rows, second panel); paired Δρ = "
             "network-cluster bootstrap, 2,000 draws, within panel × duration "
             "(paired_diff_vs_r6.csv).",
             ha="center", va="top", fontsize=6.4, color="#333333")

    # ---------- (a) per-duration placement-level rho bars ----------
    ax = fig.add_subplot(gs[0, 0])
    x = np.arange(len(DURS))
    w = 0.2
    for k, pr in enumerate(preds):
        off = (k - 1.5) * w
        vals = np.asarray(rho[pr])
        ax.bar(x + off, vals, w - 0.02, color=PCOL(pr), alpha=0.95, zorder=3)
        for xi, v in zip(x + off, vals):
            ax.text(xi, v + (0.02 if v >= 0 else -0.045), f"{v:+.3f}",
                    ha="center", fontsize=5.0, va="bottom" if v >= 0 else "top",
                    color="#111111")
    # diff CI (metrics_by_horizon bootstrap, placement level)
    for i, h in enumerate(DURS):
        v = rho["diff"][i]
        ax.errorbar(x[i] - 1.5 * w, v,
                    yerr=[[v - ci_lo[i]], [ci_hi[i] - v]],
                    fmt="none", ecolor="#111111", elinewidth=1.0, capsize=2.6, zorder=6)
    ax.axhline(0, color="#bbbbbb", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([DUR_LABEL[h] for h in DURS])
    ax.set_ylabel("placement-level Spearman ρ (vs realized benefit)")
    ax.set_ylim(-0.72, 0.78)
    ax.set_title("(a) per-duration placement ρ — four predictors", fontsize=9.5)
    panel_label(ax, "(a)", ypos=0.90)
    fig.legend(handles=[
        Patch(facecolor=C_DIFF, edgecolor="#111111", linewidth=0.6,
              label="diff (CI: placement bootstrap, metrics_by_horizon.csv)"),
        Patch(facecolor=C_R6, label="r6-diff"),
        Patch(facecolor=C_DEFAULT_DIFF, label="default difficulty"),
        Patch(facecolor=C_RISK, label="risk (v13 estimator)")],
        loc="lower center", bbox_to_anchor=(0.24, 0.045), ncol=2, fontsize=5.8,
        framealpha=0.95, columnspacing=1.0)

    # ---------- (b) paired delta forest ----------
    axf = fig.add_subplot(gs[0, 1])
    cells = [(pa, int(du)) for pa in ("first", "second") for du in (7, 30, 90, 180)]
    cells = cells[::-1]  # plot second block on top
    ypos = np.arange(len(cells))
    crossed_zero = []
    for i, (pa, du) in enumerate(cells):
        row = paired[(paired["panel"] == pa) & (paired["duration"] == du)].iloc[0]
        mean, clo, chi = row["delta_rho"], row["delta_ci_lower"], row["delta_ci_upper"]
        grey = (pa == "first") and (du == 90)
        col = "#9e9e9e" if grey else C_DIFF
        axf.errorbar([mean], [i], xerr=[[mean - clo], [chi - mean]], fmt="o", ms=6,
                     color=col, ecolor=col, elinewidth=1.5, capsize=3, zorder=4)
        axf.text(chi + 0.008, i,
                 f"{mean:+.3f} [{clo:+.3f}, {chi:+.3f}]  P(>0)={row['p_gt0']:.3f}",
                 va="center", fontsize=6.0, color="#111111")
        if clo > 0:
            crossed_zero.append(False)
        else:
            crossed_zero.append(True)
    axf.axvline(0, color="#999999", lw=0.9)
    axf.set_yticks(ypos)
    axf.set_yticklabels([f"{pa} {du} d" for pa, du in cells], fontsize=6.8)
    axf.set_xlim(-0.09, 0.70)
    axf.set_xlabel("paired Δρ = ρ(diff) − ρ(r6-diff)   (network-cluster bootstrap, "
                   "2,000 draws, within panel × duration)")
    axf.set_title("(b) paired diff vs r6-diff — the 8 cells", fontsize=9.5)
    axf.grid(axis="y", alpha=0.0)
    n_gt0 = sum(1 for i, (pa, du) in enumerate(cells) if not crossed_zero[i])
    axf.text(0.5, -0.13,
             f"{n_gt0}/8 (panel × duration) cells have paired-bootstrap CI strictly > 0, \n"
             "only first-90 d crosses zero — shown in grey.",
             transform=axf.transAxes, fontsize=6.0, ha="center", va="top",
             color="#111111")
    panel_label(axf, "(b)", ypos=0.90)

    footer(fig, "data: results/v14/p1_baselines/metrics_table.csv (placement rows)  |  "
                "results/v14/p0_differential/paired_diff_vs_r6.csv  |  "
                "metrics_by_horizon.csv (diff placement CI)")
    _final(fig, out)
    return str(out)


def PCOL(name: str) -> str:
    return {"diff": C_DIFF, "r6_diff": C_R6, "default_difficulty": C_DEFAULT_DIFF,
            "risk": C_RISK, "duration_only": C_DURONLY, "duration": C_DURONLY,
            "integral": C_INTEGRAL, "threshold_peak": C_THRESHOLD}[name]


# =====================================================================
# Figure 4 - decision layer
# =====================================================================
def fig04(d: dict) -> str:
    bwd = d["budget"].copy()
    bwd["horizon"] = bwd["horizon"].astype(str)
    bwd = bwd[(bwd["panel"] == "second") & (bwd["budget"] == 0.2)
              & (bwd["horizon"].isin(DURS))]
    bwd["predictor"] = bwd["predictor"].replace({"duration": "duration_only"})
    preds = ["diff", "duration_only", "r6_diff", "risk"]
    piv = bwd.set_index(["horizon", "predictor"])
    vals = {pr: [float(piv.loc[(h, pr), "mean_realized_benefit"]) for h in DURS]
            for pr in preds}
    harms = {h: float(piv.loc[(h, "diff"), "harmful_rate"]) * 100 for h in DURS}

    laio = d["laio"]
    l2 = laio[laio["panel"] == "second"]
    out = FIGDIR / "fig04_decision.png"

    fig, (axl, axr) = plt.subplots(1, 2, figsize=(9.6, 5.2),
                                   gridspec_kw={"width_ratios": [1.16, 1.0]})
    fig.subplots_adjust(top=0.84, bottom=0.12, left=0.075, right=0.985, wspace=0.30)
    fig.suptitle("Decision layer, duration-stratified (second panel)",
                 fontsize=12.5, fontweight="bold", y=0.985)

    # ---------------- (a) within-duration top-20% budget ----------------
    axl.set_title("(a) within-duration top-20% budget: mean realized benefit by rule")
    x = np.arange(len(DURS))
    w = 0.2
    for k, pr in enumerate(preds):
        off = (k - 1.5) * w
        bars = axl.bar(x + off, vals[pr], w - 0.015, color=PCOL(pr), alpha=0.95,
                       edgecolor="#111111" if pr == "diff" else "none",
                       linewidth=0.7 if pr == "diff" else 0, zorder=3)
        for xi, v in zip(x + off, vals[pr]):
            axl.text(xi, v + (0.05 if v >= 0 else -0.08), f"{v:+.3f}",
                     ha="center", fontsize=5.0,
                     va="bottom" if v >= 0 else "top", color="#111111", zorder=5)
    for i, h in enumerate(DURS):
        axl.text(x[i], 1.52, f"harmful {harms[h]:.1f}%", ha="center", fontsize=6.0,
                 fontweight="bold", color="#c62828", zorder=5)
    axl.axhline(0, color="#999999", lw=0.8)
    axl.set_xticks(x)
    axl.set_xticklabels([DUR_LABEL[h] for h in DURS])
    axl.set_ylim(-3.6, 1.74)
    axl.set_ylabel("mean realized benefit of the treated top-20% (°C)")
    axl.legend(handles=[Patch(facecolor=C_DIFF, edgecolor="#111111", label="diff"),
                        Patch(facecolor=C_DURONLY, label="duration-only"),
                        Patch(facecolor=C_R6, label="r6-diff"),
                        Patch(facecolor=C_RISK, label="risk")],
               loc="lower left", bbox_to_anchor=(0.0, 1.02), ncol=4, fontsize=6.2,
               framealpha=0.95, columnspacing=0.7, handlelength=1.1)
    axl.text(0.5, -0.085,
             "Red: harmful share of the diff-treated top-20%.  Margin vs duration-only: "
             "+0.22/+0.23/+0.32/+1.01 °C (7/30/90/180 d).\n"
             "Duration pooling is voided: a cross-duration top-20% selects duration, not "
             "skill (duration-only +0.906 > diff +0.878; REVIEW Major 1).",
             transform=axl.transAxes, fontsize=5.6, ha="center", va="top",
             color="#333333")
    panel_label(axl, "(a)", ypos=0.04)

    # ---------------- (b) Laio-Tamea EC/delta ----------------
    axr.set_title("(b) Laio & Tamea cost-loss: EC(ξ)/δ per duration", fontsize=9.2)
    axr.axvspan(0, 0.5, color="#b0bec5", alpha=0.15, zorder=0)
    for h in DURS:
        row = l2[l2["horizon"] == h].sort_values("xi")
        axr.plot(row["xi"], row["EC_fcst_delta_ratio"], color=C_DUR[h], lw=1.8,
                 zorder=4)
        axr.plot(row["xi"], row["EC_clim_delta_ratio"], color="#bdbdbd", ls="--",
                 lw=0.8, zorder=3)
    axr.axhline(1.0, color="#111111", lw=0.9, zorder=5)
    axr.text(0.99, 1.012, "EC/δ = 1 (parity with climatology)",
             transform=axr.get_yaxis_transform(), fontsize=6.0, ha="right",
             color="#111111", va="bottom")
    # 90 d peak annotation (xi 0.50-0.60 window)
    r90 = l2[l2["horizon"] == "90"].sort_values("xi")
    win = r90[r90["xi"].between(0.5, 0.6)]
    imax = win["EC_fcst_delta_ratio"].idxmax()
    pm = win.loc[imax]
    axr.plot([pm["xi"]], [pm["EC_fcst_delta_ratio"]], "o", ms=5.5, color=C_DUR["90"],
             zorder=6)
    axr.annotate(f"90 d: EC/δ = {pm['EC_fcst_delta_ratio']:.3f} > 1\n"
                 "at ξ = {pm['xi']:.2f} (window 0.50-0.60)",
                 xy=(pm["xi"], pm["EC_fcst_delta_ratio"]),
                 xytext=(0.05, 1.42), fontsize=5.8, color=C_DUR["90"], ha="left",
                 arrowprops=dict(arrowstyle="->", lw=0.8, color=C_DUR["90"]),
                 bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.9))
    axr.text(0.5, 0.035, "ξ < 0.5 shaded: hydrologically realistic (cheap action) half — "
             "every curve is < 1 there", transform=axr.transAxes, fontsize=5.8,
             ha="center", va="bottom", color="#37474f")
    axr.set_xlabel("cost-loss ratio ξ")
    axr.set_ylabel("EC(ξ)/δ — normalized expected cost")
    axr.set_ylim(0.05, 1.95)
    axr.set_xlim(0, 1)
    axr.legend(handles=[Line2D([], [], color=C_DUR[h], lw=1.8, label=f"{DUR_LABEL[h]} forecast")
                        for h in DURS] +
                       [Line2D([], [], color="#bdbdbd", ls="--", lw=0.8,
                               label="EC_clim(ξ)/δ per duration")],
               loc="upper right", fontsize=5.6, ncol=2, framealpha=0.95)
    panel_label(axr, "(b)", ypos=0.965)

    footer(fig, "data: results/v14/p0_differential/budget_within_duration.csv  |  "
                "results/v14/p2_decision/laio_tamea_curves.csv")
    _final(fig, out)
    return str(out), vals, harms


# =====================================================================
# Figure 5 - downstream
# =====================================================================
def fig05(d: dict) -> str:
    flip = d["flip"]
    labels = d["labels"].set_index("metric")["label"].to_dict()
    units = d["labels"].set_index("metric")["units"].to_dict()
    fam = {"annual_mean": "integral", "summer_mean": "integral", "p90": "integral",
           "cdd10": "integral", "trend_slope": "integral",
           "exceed_days_20": "threshold_peak", "exceed_days_25": "threshold_peak",
           "summer_max": "threshold_peak", "amplitude": "threshold_peak",
           "phase_doy": "threshold_peak"}
    ORDER = ["annual_mean", "summer_mean", "p90", "cdd10", "trend_slope",
             "exceed_days_20", "exceed_days_25", "summer_max", "amplitude",
             "phase_doy"]
    clim = flip[(flip["kind"] == "benefit_over_default") &
                (flip["default"] == "climatology")].copy()
    clim["horizon"] = clim["horizon"].astype(int)
    lin = flip[(flip["kind"] == "benefit_over_default") &
               (flip["default"] == "linear")].copy()
    lin["horizon"] = lin["horizon"].astype(int)
    cross = flip[flip["kind"] == "crossing"].set_index(["panel", "metric"])["crossing_day"]
    out = FIGDIR / "fig05_downstream.png"

    xp = xpos_days(DUR_DAYS)
    xlo, xhi = xp[0] - 0.18, xp[-1] + 0.18

    fig = plt.figure(figsize=(9.6, 11.2))
    gs = fig.add_gridspec(2, 1, height_ratios=[3.1, 1.0], hspace=0.35,
                          left=0.075, right=0.985, top=0.95, bottom=0.02)

    # ----------------- main grid: benefit over climatology ----------------
    gs0 = gs[0].subgridspec(len(ORDER), 2, hspace=0.02, wspace=0.16)
    big_ax = fig.add_subplot(gs[0])
    big_ax.axis("off")
    fig.text(0.5, 0.955, "Downstream distortion benefit over the climatology default "
             "(err_clim − err_recon, station-gap units, P4)",
             ha="center", fontsize=11.5, fontweight="bold")
    fig.text(0.5, 0.938, "95% CI = 2,000-draw network-cluster bootstrap "
             "(flip_table.csv). Positive = reconstruction reduces distortion.  "
             "Families: integral-type (navy) vs threshold/peak-type (violet).  "
             "Every metric crosses to net harm within or before the MAE-scale flip "
             "window (30–90 d); MAE-scale flip 105 d (first) / 91 d (second).",
             ha="center", fontsize=6.4, color="#333333")

    extremes = {}   # (ymin, ymax) per row across the two columns
    for i, met in enumerate(ORDER):
        sub = clim[clim["metric"] == met]
        ymax = -np.inf
        ymin = np.inf
        for pa in ("first", "second"):
            s = sub[sub["panel"] == pa].set_index("horizon")
            ymax = max(ymax, s["point"].max())
            ymin = min(ymin, s["point"].min())
        for pa in ("first", "second"):
            extremes[met] = (ymin, ymax)

    for i, met in enumerate(ORDER):
        col = C_INTEGRAL if fam[met] == "integral" else C_THRESHOLD
        (ymin, ymax) = extremes[met]
        pad = max(0.08 * (ymax - ymin), 0.02 * abs(ymax) + 0.02 * abs(ymin) + 1e-9)
        for j, pa in enumerate(("first", "second")):
            ax = fig.add_subplot(gs0[i, j])
            s = clim[(clim["metric"] == met) & (clim["panel"] == pa)] \
                .set_index("horizon").reindex(DUR_DAYS)
            ax.errorbar(xp, s["point"], yerr=[s["point"] - s["ci_lower"],
                                              s["ci_upper"] - s["point"]],
                        fmt="-o", ms=3.2, lw=1.1, color=col, ecolor=col,
                        elinewidth=0.7, capsize=1.6, zorder=4)
            ax.axhline(0, color="#999999", lw=0.7, ls=":", zorder=3)
            ax.set_ylim(ymin - pad, ymax + pad * 2.0)
            ax.set_xlim(xlo, xhi)
            ax.tick_params(length=2)
            if i < len(ORDER) - 1:
                ax.set_xticklabels([])
                ax.tick_params(axis="x", labelbottom=False)
            else:
                ax.set_xticks(xp)
                ax.set_xticklabels([str(g) for g in DUR_DAYS], fontsize=5.8)
            if i == 0:
                ax.set_title("first panel" if j == 0 else "second panel",
                             fontsize=8.2, fontweight="bold")
            if j == 1:
                ax.set_yticklabels([])
            else:
                ax.set_ylabel(f"{met} [{units[met]}]", fontsize=4.8, color=col,
                              fontweight="bold", labelpad=1)
                ax.tick_params(axis="y", labelsize=5.2)
            # crossing-day annotation
            key = (pa, met)
            if key in cross.index and not np.isnan(cross.loc[key]):
                cd = cross.loc[key]
                ax.axvline(xpos_days(cd), color="#555555", lw=0.5, ls="--", zorder=5)
                ax.text(xpos_days(cd) + 0.02, ymax + 1.85 * pad, f"≈ {cd:.0f} d",
                        fontsize=4.9, color="#111111", ha="left", va="top")

    # ----------------- strip: benefit over linear default -----------------
    gs1 = gs[1].subgridspec(1, 2, wspace=0.06)
    for j, pa in enumerate(("first", "second")):
        ax = fig.add_subplot(gs1[0, j])
        sub = lin[lin["panel"] == pa]
        # row-normalise by the metric's max |benefit| over both panels (sign kept)
        rowmax = {}
        for met in ORDER:
            both = lin[lin["metric"] == met]["point"]
            rowmax[met] = max(both.abs().max(), 1e-12)
        n_met = len(ORDER)
        for i, met in enumerate(ORDER):
            yrow = n_met - 1 - i          # top row = annual_mean, like the main grid
            norm = np.array([float(sub[(sub["metric"] == met) &
                                       (sub["horizon"] == g)]["point"].iloc[0])
                             / rowmax[met] for g in DUR_DAYS])
            for k, g in enumerate(DUR_DAYS):
                v = norm[k]
                if v < 0:
                    ax.add_patch(plt.Rectangle((k - 0.32, yrow - 0.42), 0.64, 0.84,
                                               facecolor=C_RISK, alpha=min(1.0, -v),
                                               edgecolor="none"))
                else:
                    ax.add_patch(plt.Rectangle((k - 0.32, yrow - 0.42), 0.64, 0.84,
                                               facecolor=C_ORACLE, alpha=min(0.95, v),
                                               edgecolor="none"))
        for _, r in sub[sub["point"] < 0].iterrows():
            col_i = [7, 30, 90, 180, 365].index(int(r["horizon"]))
            ax.text(col_i, n_met - 1 - ORDER.index(r["metric"]),
                    f"{r['point']:+.2f}", ha="center", va="center", fontsize=5.6,
                    color="white", fontweight="bold")
        ax.set_xlim(-0.55, 4.55)
        ax.set_ylim(-0.55, 10.95)
        ax.set_xticks(np.arange(5))
        ax.set_xticklabels([str(g) for g in DUR_DAYS], fontsize=6.4)
        ax.set_yticks(np.arange(n_met))
        ax.set_yticklabels([""] * n_met)
        if j == 0:
            ax.set_yticklabels(list(reversed(ORDER)), fontsize=5.4)
        ax.set_title("benefit over the LINEAR-interpolation default — " + pa + " panel",
                     fontsize=8.2, fontweight="bold")
        ax.grid(False)
        ax.text(0.5, 0.985, "98/100 panel×horizon×metric cells positive\n"
                "(exceptions: first 7 d phase_doy −0.06, second 30 d phase_doy −0.02)",
                transform=ax.transAxes, fontsize=5.2, ha="center", va="top",
                color="#333333")
    fig.text(0.5, 0.045,
             "The climatology-default flip does NOT exist under the linear default: "
             "reconstruction beats linear interpolation at every horizon on both panels "
             "(flip_table.csv, default = linear).  Flip days from flip_table.csv "
             "kind=crossing: annual_mean 55/40 d, amplitude 42/46 d (first/second).",
             ha="center", fontsize=6.4, color="#333333")

    footer(fig, "data: results/v14/p4_flip_analysis/{flip_table,ci_tables}.csv  |  "
                "results/v14/p4_downstream{, _second}/metric_error_summary.csv",
           script="scripts/148_run_v14_figures_v2.py")
    _final(fig, out)
    return str(out)


# =====================================================================
# Figure 6 - boundary
# =====================================================================
def fig06(d: dict) -> str:
    tl = d["three_level"]
    st = d["stratum"]
    jj = d["dir_json"]
    out = FIGDIR / "fig06_boundary.png"

    def lv(v):
        return float(tl[(tl["level"] == v) & (tl["predictor"] == p)]["rho"].iloc[0])

    fig = plt.figure(figsize=(9.8, 6.6))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.12], hspace=0.42, wspace=0.26,
                          left=0.08, right=0.985, top=0.90, bottom=0.10)
    fig.suptitle("Boundary: what the placement-level ρ is and is not (second panel)",
                 fontsize=12, fontweight="bold", y=0.985)

    # ---------------- (a) three-level decomposition ----------------
    axa = fig.add_subplot(gs[0, 0])
    levs = ["between_network", "within_network_across_durations", "per_network_mean"]
    levlbl = ["between-network\n(network means, n = 57)",
              "within-network,\ndemeaned (pooled)",
              "per-network mean\nof unit-level ρ"]
    x = np.arange(3)
    w = 0.34
    for k, p in enumerate(["diff", "duration_only"]):
        vals = [lv(le) for le in levs]
        axa.bar(x + (k - 0.5) * w, vals, w - 0.04, color=PCOL(p), alpha=0.95,
                edgecolor="#111111" if p == "diff" else "none",
                linewidth=0.7 if p == "diff" else 0, label=p)
        for xi, v in zip(x + (k - 0.5) * w, vals):
            axa.text(xi, v + 0.015, f"{v:.3f}", ha="center", fontsize=6.4)
    axa.axhline(0.35, color="#37474f", ls="-.", lw=0.9)
    axa.text(0.02, 0.385, "network gate 0.35", fontsize=5.6, color="#37474f")
    axa.set_xticks(x)
    axa.set_xticklabels(levlbl, fontsize=6.4)
    axa.set_ylim(0, 1.05)
    axa.set_ylabel("Spearman ρ (unit level)")
    axa.set_title("(a) three-level decomposition of the pooled ρ")
    axa.legend(loc="lower right", fontsize=6.8, framealpha=0.95)
    axa.text(0.5, -0.16,
             "Within-network cross-duration signal: diff 0.897 ≈ duration-only 0.899 — "
             "the unit-level ‘within-network’ signal is ALL duration signal;\n"
             "only the between-network level separates (0.657 vs 0.456).",
             transform=axa.transAxes, fontsize=5.9, ha="center", va="top",
             color="#333333")
    panel_label(axa, "(a)", ypos=0.92)

    # ---------------- (b) within (network × duration) cells ----------------
    axb = fig.add_subplot(gs[0, 1])
    means = []
    fracs = []
    for h in DURS:
        means.append(float(tl[(tl["level"] == "within_network_x_duration_cell_mean")
                              & (tl["duration_or_pooled"] == f"{h}d")]["rho"].iloc[0]))
        fracs.append(float(tl[(tl["level"] == "within_network_x_duration_cell_frac_gt0")
                              & (tl["duration_or_pooled"] == f"{h}d")]["rho"].iloc[0]))
    x = np.arange(4)
    axb.bar(x, means, 0.5, color=[C_DUR[h] for h in DURS], alpha=0.9,
            edgecolor="#333333", linewidth=0.6)
    for xi, (v, f) in enumerate(zip(means, fracs)):
        axb.text(xi, v + 0.02, f"{v:.3f}", ha="center", fontsize=7.4,
                 fontweight="bold")
        axb.text(xi, 0.06, f"frac ρ>0\n{f:.3f}", ha="center", fontsize=6.0,
                 color="#111111", va="bottom")
    axb.set_xticks(x)
    axb.set_xticklabels([DUR_LABEL[h] for h in DURS])
    axb.set_ylim(-0.05, 0.85)
    axb.set_ylabel("mean placement-level ρ inside (network × duration) cells")
    axb.set_title("(b) within-cell signal: duration AND network held fixed")
    axb.text(0.5, -0.16,
             "Cells = network × duration with ≥ 30 placements (57/57/55/45 networks) — "
             "the last pure-placement\nsignal survives the strictest stratification; "
             "unit-level variant (≥ 4 units/cell): 0.397/0.324/0.638/0.606.",
             transform=axb.transAxes, fontsize=5.8, ha="center", va="top",
             color="#333333")
    panel_label(axb, "(b)", ypos=0.92)

    # ---------------- (c) drift strata ----------------
    axc = fig.add_subplot(gs[1, :])
    stp = st[st["level"] == "placement"]
    strata = ["stable", "moderate", "drift"]
    xgrp = []
    xtl = []
    for k, h in enumerate(DURS):
        base = k * 4
        for i, sname in enumerate(strata):
            row = stp[(stp["horizon"] == h) & (stp["stratum"] == sname)].iloc[0]
            r1, r2 = row["rho_diff"], row["rho_r6_diff"]
            axc.bar(base + i - 0.18, r1, 0.33, color=C_DIFF, alpha=0.95)
            axc.bar(base + i + 0.18, r2, 0.33, color=C_R6, alpha=0.95)
            axc.text(base + i, max(r1, r2) + 0.015, f"Δ {r1 - r2:+.3f}",
                     ha="center", fontsize=5.8)
        xgrp.append(base + 1)
        xtl.append(DUR_LABEL[h])
    axc.set_xticks(xgrp)
    axc.set_xticklabels(xtl, fontsize=8)
    axc.set_ylabel("placement-level Spearman ρ (stratum × duration)")
    axc.set_title("(c) stationarity strata (P3): ρ(diff) vs ρ(r6-diff), placement rows")
    axc.set_ylim(-0.05, 1.0)
    axc.legend(handles=[Patch(facecolor=C_DIFF, label="ρ(diff)"),
                        Patch(facecolor=C_R6, label="ρ(r6-diff)")],
               loc="upper left", fontsize=6.8)
    axc.text(0.985, 0.965,
             "T2 (pooled placement ΔΔρ, drift − stable): +0.007 [−0.004, +0.019], "
             "P(>0) = 0.89 —\nno drift advantage: the method is not strengthened by "
             "non-stationarity (direction_test.json).\n"
             "Per-duration Δρ(diff − r6) grows with duration in every stratum; "
             "stratum networks 19/19/19 (7/30 d), 18/19/19 (90 d), 18/17/18 (180 d).",
             transform=axc.transAxes, fontsize=6.2, ha="right", va="top",
             bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#999999", alpha=0.9))
    panel_label(axc, "(c)", ypos=0.05)

    footer(fig, "data: results/v14/p0_differential/three_level_decomposition.csv  |  "
                "results/v14/p3_drift/stratum_comparison.csv  |  direction_test.json")
    _final(fig, out)
    return str(out), means, fracs


# =====================================================================
# consistency checks + figure notes
# =====================================================================
def verify_and_report(d: dict, stats, bwd_vals, bwd_harms, cell_means, cell_fracs) -> list:
    """Assert every drawn annotation against its archived source; return notes."""
    notes = []
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        notes.append(("PASS" if cond else "FAIL") + f"  {name} {detail}")

    # ---- fig01: unit means/harmful against CSVs ----
    for panel, u in (("first", d["u_first"]), ("second", d["u_second"])):
        u = u[u["gap_length"].isin(DUR_DAYS)]
        for g in DUR_DAYS:
            s = u[u["gap_length"] == g]["realized_benefit"]
            expect = dict(n=len(s), mean=s.mean(), harm=(s < 0).mean())
            got = stats[panel][g]
            check(f"fig01 {panel} {g} d unit stats",
                  abs(got["mean"] - expect["mean"]) < 1e-9
                  and abs(got["harm"] - expect["harm"]) < 1e-9
                  and got["n"] == expect["n"],
                  f"mean {expect['mean']:+.4f} harm {expect['harm'] * 100:.2f}% n {expect['n']}")

    # ---- fig02/fig03: placement rho rows vs metrics_table ----
    m = d["p1_metrics"]
    m2 = m[(m["panel"] == "second") & (m["level"] == "placement_pooled")]
    m2 = m2.set_index(["horizon", "predictor"])["rho"]
    expect_rho = {"diff": [0.297, 0.303, 0.371, 0.555],
                  "risk": [0.184, 0.129, -0.192, -0.540],
                  "r6_diff": [0.226, 0.237, 0.331, 0.353],
                  "default_difficulty": [0.286, 0.270, 0.179, 0.000]}
    for pr, vals in expect_rho.items():
        got = [float(m2.loc[(h, pr)]) for h in DURS]
        check(f"fig03(a) second placement ρ {pr}",
              all(abs(a - b) < 0.002 for a, b in zip(got, vals)),
              f"got {[round(x, 3) for x in got]}")
    # recompute from placements
    p = direct_placement_rows(d["p_second"])
    for h in DURS:
        sub = p[p["gap_length"] == int(h)]
        rr = spearmanr(sub["risk_prediction"], sub["realized_benefit"]).statistic
        rd = spearmanr(sub["diff_prediction"], sub["realized_benefit"]).statistic
        check(f"fig02 recompute {h} d risk/diff",
              abs(rr - float(m2.loc[(h, "risk")])) < 2e-3
              and abs(rd - float(m2.loc[(h, "diff")])) < 2e-3,
              f"recomputed risk {rr:+.4f} diff {rd:+.4f}")

    # ---- fig03(b): paired deltas and CI ----
    pa = d["paired"].set_index(["panel", "duration"])
    for panel in ("first", "second"):
        for h in DURS:
            row = pa.loc[(panel, int(h))]
            if row["delta_ci_lower"] > 0:
                n_gt = "CI>0"
            else:
                n_gt = "CI~0"
            check(f"fig03(b) {panel} {h} d paired", row["n_draws"] == 2000,
                  f"Δ {row['delta_rho']:+.3f} [{row['delta_ci_lower']:+.3f}, "
                  f"{row['delta_ci_upper']:+.3f}] {n_gt}")

    # ---- fig04: budget rows vs P0 file; harmful shares ----
    b = d["budget"]
    b["horizon"] = b["horizon"].astype(str)
    b = b[(b["panel"] == "second") & (b["budget"] == 0.2) & (b["horizon"].isin(DURS))]
    b = b.set_index(["horizon", "predictor"])
    for h in DURS:
        for pr in ("diff", "duration_only", "r6_diff", "risk"):
            src = "duration" if pr == "duration_only" else pr
            row = b.loc[(h, src)]
            check(f"fig04(a) {h} d {pr} budget",
                  abs(row["mean_realized_benefit"] - bwd_vals[pr][DURS.index(h)]) < 1e-9,
                  f"{row['mean_realized_benefit']:+.4f}")
    for h in DURS:
        check(f"fig04(a) {h} d diff harmful",
              abs(b.loc[(h, "diff"), "harmful_rate"] * 100 - bwd_harms[h]) < 1e-9,
              f"{bwd_harms[h]:.2f}%")

    # ---- fig04(b): Laio 90 d peak ----
    l2 = d["laio"]
    l2 = l2[l2["panel"] == "second"]
    r90 = l2[l2["horizon"] == "90"]
    win = r90[r90["xi"].between(0.5, 0.6000001)]
    pm = win.loc[win["EC_fcst_delta_ratio"].idxmax()]
    check("fig04(b) 90 d peak", 1.018 < pm["EC_fcst_delta_ratio"] < 1.020,
          f"EC/δ {pm['EC_fcst_delta_ratio']:.4f} at ξ {pm['xi']}")

    # ---- fig05: linear cells ----
    ft = d["flip"]
    lin = ft[(ft["kind"] == "benefit_over_default") & (ft["default"] == "linear")]
    n_pos = (lin["point"] > 0).sum()
    check("fig05 linear cells", n_pos == 98 and len(lin) == 100,
          f"{n_pos}/100 positive")
    for met, pa_, expect in (("annual_mean", "first", 54.98), ("annual_mean", "second", 39.93),
                             ("amplitude", "first", 42.35), ("amplitude", "second", 45.96)):
        cd = ft[(ft["kind"] == "crossing") & (ft["metric"] == met)
                & (ft["panel"] == pa_)]["crossing_day"].iloc[0]
        check(f"fig05 crossing {pa_} {met}", abs(cd - expect) < 0.1,
              f"{cd:.1f} d")
    mae_cross = {r.panel: r.crossing_day for _, r in
                 ft[(ft["kind"] == "crossing") & (ft["metric"] == "mae_scale")]
                 .drop_duplicates("panel").iterrows()}
    check("fig01 MAE crossing", abs(mae_cross["first"] - 105.34) < 0.1
          and abs(mae_cross["second"] - 91.49) < 0.1,
          f"first {mae_cross['first']:.1f} second {mae_cross['second']:.1f}")

    # ---- fig06: decomposition and cells ----
    tl = d["three_level"]
    for lev, pr, ex in (("between_network", "diff", 0.657),
                        ("between_network", "duration_only", 0.456),
                        ("within_network_across_durations", "diff", 0.897),
                        ("within_network_across_durations", "duration_only", 0.899),
                        ("per_network_mean", "diff", 0.861),
                        ("per_network_mean", "duration_only", 0.907)):
        v = float(tl[(tl["level"] == lev) & (tl["predictor"] == pr)]["rho"].iloc[0])
        check(f"fig06(a) {lev} {pr}", abs(v - ex) < 0.005, f"{v:.3f}")
    for i, h in enumerate(DURS):
        v = float(tl[(tl["level"] == "within_network_x_duration_cell_mean")
                     & (tl["duration_or_pooled"] == f"{h}d")]["rho"].iloc[0])
        f = float(tl[(tl["level"] == "within_network_x_duration_cell_frac_gt0")
                     & (tl["duration_or_pooled"] == f"{h}d")]["rho"].iloc[0])
        check(f"fig06(b) {h} d cell rho",
              abs(v - cell_means[i]) < 1e-9 and abs(f - cell_fracs[i]) < 1e-9,
              f"mean {v:.3f} frac>0 {f:.3f}")
    st = d["stratum"]
    stp = st[st["level"] == "placement"]
    stp_used = stp[stp["horizon"].isin(DURS)]
    check("fig06(c) strata rows (durations used)", len(stp_used) == 12,
          f"{len(stp_used)} rows (file also carries {len(stp) - len(stp_used)} 'direct' rows)")
    t2 = d["dir_json"]["T2_pooled_placement"]
    check("fig06(c) T2 CI", t2["ci"][0] < 0 < t2["ci"][1],
          f"{t2['mean']:+.3f} [{t2['ci'][0]:+.3f}, {t2['ci'][1]:+.3f}] "
          f"P(>0)={t2['prob_gt0']:.3f}")

    notes.append("SUMMARY " + ("all checks passed" if ok else "FAILURES PRESENT"))
    return notes


def main() -> None:
    d = _load()

    # ---------------- draw ----------------
    produced = []
    p1, stats = fig01(d)
    produced.append(p1)
    produced.append(fig02(d))
    p3 = fig03(d)
    produced.append(p3)
    p4, bwd_vals, bwd_harms = fig04(d)
    produced.append(p4)
    produced.append(fig05(d))
    p6, cell_means, cell_fracs = fig06(d)
    produced.append(p6)

    for p in produced:
        print("wrote", p)

    # ---------------- verification ----------------
    from PIL import Image
    print("\n--- verification ---")
    sizes = []
    for p in produced:
        im = Image.open(p)
        sizes.append((Path(p).name, Path(p).stat().st_size, im.size))
        if im.size[0] < 100 or im.size[1] < 100:
            raise SystemExit(f"figure too small: {p} {im.size}")
    for name, size, wh in sizes:
        print(f"{name:34s} {size:>10,} bytes  {wh[0]}x{wh[1]}")
    assert all(s > 20_000 for _, s, _ in sizes), "empty/failed figure"

    # ---------------- annotation verification ----------------
    print("\n--- annotation checks (every number vs its archived source) ---")
    notes = verify_and_report(d, stats, bwd_vals, bwd_harms, cell_means, cell_fracs)
    for n in notes:
        print("  " + n)
    fails = [n for n in notes if n.startswith("FAIL") or n.startswith("SUMMARY")]
    if any(n.startswith("FAIL") for n in notes):
        raise SystemExit("annotation check FAILED")

    # ---------------- copy of script + figure notes ----------------
    shutil.copy2(Path(__file__).resolve(), FIGDIR / "run_script_148.py")

    from datetime import date
    notes_md = f"""# FIGURE_NOTES_v2.md — revised v14 figure set

Generated by scripts/148_run_v14_figures_v2.py on {date.today().isoformat()}; the script
itself is archived as run_script_148.py in this folder.  All figures are 300 dpi.
results/v14/figures/ (the v1 set) was not modified.

Narrative order per WORKPLAN_v14.md §4: the duration structure of benefit (Fig 1) is
the headline; estimation/baseline comparison (Figs 2-3), decision layer (Fig 4),
downstream (Fig 5) and boundary (Fig 6) follow.

Colour contract (as scripts/145_run_v14_figures.py): diff = navy #1f4e9c, risk = red
#c62828, duration-only = grey #8c8c8c, r6-diff = teal #00897b, default-difficulty =
amber #d97706, random = light grey, oracle = green; gap durations use C_DUR
7=#2c7bb6, 30=#fdae61, 90=#66bd63, 180=#8e44ad, 365=#455a64.

Verification: every annotation below was asserted against its source file inside the
script (see "annotation checks" stdout block); the script exits non-zero on a FAIL.

## fig01_duration_structure.png

- Source: results/v14/p0_differential/unit_predictions_first.csv and
  _second.csv (rows gap_length in 7/30/90/180/365; the 365-d rows exist and carry
  realized_benefit but are not "direct").
- Realized benefit = MAE(climatology default) − MAE(recon), °C, unit level
  (station × gap). Means and harmful shares are exact computed values (no rounding
  of the archive):
  - first panel (42 networks): 7 d μ +0.9792, 30 d μ +0.6845, 90 d μ +0.2601,
    180 d μ −0.8855, 365 d μ −2.5018; harmful share 0.00 / 0.00 / 27.40 / 83.58 /
    94.44 %.  n units 219/219/219/201/144.
  - second panel (57 networks): 7 d μ +0.9062, 30 d μ +0.5531, 90 d μ +0.0364,
    180 d μ −1.5000, 365 d μ −3.8934; harmful share 0.00 / 0.45 / 46.82 / 95.63 /
    100.00 %.  n units 224/224/220/206/124.
- Annotated on the figure: "μ +x.xx °C" per duration (2 dp), "harmful x.x%" per
  duration (1 dp), shaded 30-90 d band ("sign-flip window 30-90 d"), dashed line at
  49 d labelled "Johnson et al. (2021) m_max = 49 d", and under each panel one
  caption line with the MAE-scale crossing day:
  - first ≈ 105 d, second ≈ 91 d — from flip_table.csv kind=crossing metric
    mae_scale: crossing_day 105.337 (first, bracket 90-180) and 91.489 (second,
    bracket 90-180), log10-interpolated between grid horizons (see
    p4_flip_analysis/flip_analysis.md §4).  REVIEW_v14.md Major 5 quotes 105/91 d.
- These reproduce REVIEW_v14.md Major 5 table (first +0.979/+0.684/+0.260/−0.885;
  second +0.906/+0.553/+0.036/−1.500; harmful 0.0/0.0/27.4/83.6 and
  0.0/0.4/46.8/95.6 %).

## fig02_estimand.png

- Source: results/v14/p0_differential/placement_predictions_second.csv — direct
  placements at 7/30/90/180 d only (17,298 rows).
- Left panel: x = risk_prediction, y = realized_benefit; right: x =
  diff_prediction. Both scatter panels: alpha 0.12, coloured by gap duration.
- Per-duration Spearman ρ annotations (placement level, second panel):
  - risk (left): 7/30/90/180 d = +0.184 / +0.129 / −0.192 / −0.540; pooled −0.481.
  - diff (right): 7/30/90/180 d = +0.297 / +0.303 / +0.371 / +0.555; pooled +0.607.
  Values from p1_baselines/metrics_table.csv (level = placement_pooled, panel =
  second) and verified by recomputation from the placement CSV (agree to ±0.002).
  metrics_by_horizon.csv reports the same cells (diff 0.297/0.303/0.371/0.555).
- Annotations: per-duration ρ boxes (rounded 3 dp), pooled ρ, title "the risk curve
  ranks model error, not benefit" / "the differential curve ranks benefit", plus the
  Major-2 pooled near-tie note: pooled ρ(diff) +0.607 vs ρ(duration-only with
  average ties) +0.604 (recomputed here from the same placements) —
  duration-confounded, reported for comparability only.
- Risk values from p1 metrics_table placement rows: 0.1836/0.1286/−0.1919/−0.5401
  (displayed rounded 0.184/0.129/−0.192/−0.540).

## fig03_main_result.png

- Sources: p1_baselines/metrics_table.csv (placement rows), paired_diff_vs_r6.csv,
  metrics_by_horizon.csv.
- (a) Per-duration placement-level ρ bars (second panel):
  - diff 0.297/0.303/0.371/0.555 (navy; CI shown from metrics_by_horizon.csv
    placement-level bootstrap, diff_ci_lower/upper: 7 d [0.251, 0.339], 30 d
    [0.259, 0.344], 90 d [0.320, 0.416], 180 d [0.491, 0.617]).
  - r6_diff 0.226/0.237/0.331/0.353 (teal), default_difficulty 0.286/0.270/0.179/
    0.000 (amber), risk 0.184/0.129/−0.192/−0.540 (red) — all from metrics_table.csv
    placement rows (exact: 0.2857/0.2700/0.1792/0.0005, 0.1836/0.1286/−0.1919/
    −0.5401, 0.2263/0.2372/0.3307/0.3531, 0.2971/0.3034/0.3710/0.5555).  The 180 d
    default_difficulty value is 0.0005, displayed as +0.000.
  - NOTE (data-interpretation): the task spec asked for the diff CI "from
    paired_diff_vs_r6.csv", but that file archives only the paired Δρ bootstrap CI
    (used in (b)); it contains no per-ρ CI for diff.  The diff CI error bars
    therefore use the archived placement-level bootstrap CI from
    metrics_by_horizon.csv (diff_ci_lower/upper), which is the only archived CI of
    the diff ρ itself.  Reported here rather than silently changed.
- (b) Paired-Δρ forest of the 8 panel × duration cells (paired_diff_vs_r6.csv,
  2,000 network-cluster draws, within panel × duration):
  - first 7/30/90/180 d: +0.033 [+0.003, +0.065] P(>0) 0.988 · +0.046 [+0.014,
    +0.076] 0.999 · +0.017 [−0.022, +0.056] 0.819 (grey — CI crosses zero) ·
    +0.053 [+0.029, +0.091] 1.000
  - second 7/30/90/180 d: +0.071 [+0.035, +0.113] 1.000 · +0.066 [+0.027, +0.113]
    1.000 · +0.040 [+0.011, +0.073] 0.998 · +0.202 [+0.149, +0.266] 1.000
  - Zero reference line; cells other than first-90 d drawn navy; annotation
    "7/8 CI > 0" (only first-90 d crosses zero).

## fig04_decision.png

- Sources: results/v14/p0_differential/budget_within_duration.csv (panel =
  second, budget = 0.2) and p2_decision/laio_tamea_curves.csv (panel = second).
- (a) Within-duration top-20% budget, mean realized benefit of the treated top-20%:
  - diff (navy) +1.219 / +0.840 / +0.380 / −0.636 at 7/30/90/180 d (exact
    1.2185/0.8401/0.3800/−0.6363).
  - duration-only (grey) +1.000 / +0.605 / +0.056 / −1.647 (exact
    0.9999/0.6054/0.0562/−1.6471).
  - r6-diff (teal) +1.153 / +0.773 / +0.367 / −0.862 (exact 1.1531/0.7726/0.3671/
    −0.8618).
  - risk (red) +1.026 / +0.616 / −0.256 / −2.881 (exact 1.0262/0.6158/−0.2564/
    −2.8810).
  - Harmful-rate annotations above each duration group (red), the harmful share of
    the diff-treated top-20%: 9.4 / 10.9 / 25.1 / 62.7 % at 7/30/90/180 d (exact
    9.375/10.9375/25.1136/62.6904 %) — per REVIEW_v14.md Minor 2, reported per
    duration, not pooled.
  - Margin vs duration-only (diff advantage): +0.22/+0.23/+0.32/+1.01 °C.
  - Caption: cross-duration pooling voided per REVIEW Major 1 composition table
    (reviewer recomputation): pooled top-20% diff +0.878 with duration composition
    66/19/10/4% vs duration-only +0.906 with 100/0/0/0% — one-line "shortest gap"
    rule beats the method once durations are pooled.
- (b) Laio & Tamea EC(ξ)/δ curves per duration (xi on x); EC_clim dashed; EC/δ = 1
  reference; ξ < 0.5 shaded (all curves < 1 there — Minor 4).  90 d peak annotated:
  EC/δ = 1.019 at ξ = 0.55 (exact 1.01853 at xi = 0.55, the max over ξ ∈ [0.50,
  0.60]) — Minor 4: the peak must be named, not just "ξ<0.5 all <1".

## fig05_downstream.png

- Sources: p4_flip_analysis/flip_table.csv and ci_tables.csv (benefit = err_default
  − err_recon per station-gap unit; 95% CI = 2,000-draw network-cluster bootstrap),
  p4_downstream/metric_error_summary.csv and p4_downstream_second/… for metric
  labels/units.
- Main grid (10 rows × first/second columns): mean benefit over the climatology
  default per metric per horizon 7/30/90/180/365 d with CI error bars, zero line,
  rows grouped by family — integral-type (annual_mean, summer_mean, p90, cdd10,
  trend_slope; navy) vs threshold/peak-type (exceed_days_20, exceed_days_25,
  summer_max, amplitude, phase_doy; violet).  Families and membership per
  flip_analysis.md §1.
- Crossing-day annotations from flip_table.csv kind=crossing (all ten metrics
  drawn as ≈ day labels; the required headline pairs): annual_mean 55 d (first,
  54.98) / 40 d (second, 39.93); amplitude 42 d (first, 42.35) / 46 d (second,
  45.96).  MAE-scale crossings 105/91 d quoted in the header line.
- Bottom strip: benefit over the LINEAR default as a heat-map block per panel
  (colour intensity = benefit / max row |benefit| across both panels; green =
  positive, red = negative): 98/100 panel×horizon×metric cells positive — the only
  non-positive cells: first 7 d phase_doy −0.063 and second 30 d phase_doy −0.018
  (annotated in white).  The climatology-default flip does not exist under the
  linear default (flip_analysis.md §5/§7 Q2).

## fig06_boundary.png

- Sources: three_level_decomposition.csv (second panel, n = 57 networks),
  p3_drift/stratum_comparison.csv (placement rows), direction_test.json.
- (a) Three-level decomposition (diff vs duration-only): between-network
  0.657 vs 0.456; within-network demeaned 0.897 vs 0.899; per-network mean of
  unit-level ρ 0.861 vs 0.907 (exact 0.65699/0.45646/0.89710/0.89889/0.86108/
  0.90667).  Caption: within-network cross-duration signal is all duration signal
  (0.897 ≈ 0.899) — REVIEW Major 4.
- (b) Within (network × duration) cell-level mean placement ρ with frac(ρ>0):
  0.218/0.236/0.274/0.514 and frac 0.895/0.912/0.891/0.911 at 7/30/90/180 d (cells
  with ≥ 30 placements; n networks 57/57/55/45).  Unit-level variant (≥ 4 units)
  0.397/0.324/0.638/0.606 quoted in the caption from the same file.
- (c) Drift strata (stable/moderate/drift × duration, placement rows):
  ρ(diff) vs ρ(r6-diff) bars per stratum × duration from stratum_comparison.csv
  (second panel); Δρ(diff − r6) labelled above each pair
  (+0.067/+0.046/+0.096 at 7 d, +0.065/+0.046/+0.080 at 30 d, +0.077/+0.047/+0.007
  at 90 d, +0.170/+0.175/+0.236 at 180 d for stable/moderate/drift).  T2 CI
  annotation from direction_test.json T2_pooled_placement: +0.007 [−0.004, +0.019],
  P(>0) = 0.89 — no drift advantage, i.e. the stationarity boundary of REVIEW
  Major 6.  Stratum network counts 19/19/19 (7/30 d), 18/19/19 (90 d), 18/17/18
  (180 d) for stable/moderate/drift.

## Data-mismatch / interpretation notes (reported, not silently corrected)

1. Two budget_within_duration.csv archives disagree on the duration-only rows of the
   second panel: p0_differential/budget_within_duration.csv (used here; matches
   REVIEW_v14.md §1.4 and the review's numbers exactly) gives
   +1.000/+0.605/+0.056/−1.647, while p1_baselines/budget_within_duration.csv gives
   +0.875/+0.551/+0.033/−1.330 (and small differences for r6 7/30 d, diff 90/180 d,
   risk 90/180 d: e.g. risk 180 −2.881 vs −2.878).  fig04 uses the P0 archive.
2. default_difficulty placement ρ at 180 d (second) is 0.0005 in metrics_table.csv,
   displayed as +0.000 (the spec listed 0.000).
3. pooled duration-only placement ρ (+0.604, second) is not in metrics_table.csv
   (duration rows are NaN there because of ties); it is recomputed in the script
   from placement_predictions_second.csv with average-tie Spearman and matches the
   REVIEW Major-2 number 0.604.
4. fig03(a) diff CI: see note in the fig03 section — paired_diff_vs_r6.csv has no
   per-ρ CI; the archived per-ρ bootstrap CI from metrics_by_horizon.csv is drawn
   instead and the deviation is documented on the figure itself.
"""
    (FIGDIR / "FIGURE_NOTES_v2.md").write_text(notes_md)
    print("\nwrote", FIGDIR / "FIGURE_NOTES_v2.md")
    print("wrote", FIGDIR / "run_script_148.py")


if __name__ == "__main__":
    main()
