#!/usr/bin/env python3
"""v15/W1 Figure 1: the benefit law as a mechanism figure (WORKPLAN_v15.md
Step 3.1, drawn early so the manuscript can lead with it).

Layout (2 x 2):
  (a) second panel: the two error curves — climatology MAE (nearly flat) and
      the deployment model MAE (rising ~10x) — with the crossing annotated
      (91 d [85-95]) and the "reconstruct" / "use the default" shading.
  (b) first panel: the same flat climatology threshold line with three model
      families' error curves crossing it at different grid intervals
      (seasonal ridge 60-90 d; deployment and donor ridge 90-180 d) — same
      threshold line, different model curves.
  (c) second panel: station-level test of the law — crossing day (log10) vs
      the station's own climatology MAE, rho = +0.41.
  (d) first panel: same scatter, rho = +0.24.

Data: results/v14/p5_mechanism/{benefit_decomposition,station_crossings,
station_crossing_summary}.csv (scripts/152), results/v14/p1_baselines/
family_benefit_table.csv, results/v14/p4_flip_analysis/mae_crossing_ci.csv.
Every annotation is asserted in-script against the named CSVs.

Run: PYTHONPATH=$PWD/src python3 scripts/154_run_v15_fig1_mechanism.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MECH = ROOT / "results/v14/p5_mechanism"
P1 = ROOT / "results/v14/p1_baselines"
P4 = ROOT / "results/v14/p4_flip_analysis"
OUT = MECH / "fig01_mechanism.png"

DUR = [7, 14, 30, 60, 90, 180, 365]
PANEL_COLOR = {"first": "#1f77b4", "second": "#d62728"}
FAMILY_STYLE = {
    "xgboost_b_d": ("#1f77b4", "o", "deployment xgboost_b_d"),
    "donor_blup_ridge": ("#2ca02c", "s", "donor ridge"),
    "seasonal_boundary_ridge": ("#ff7f0e", "^", "seasonal ridge"),
}

plt.rcParams.update(
    {
        "font.size": 8.5,
        "axes.titlesize": 9,
        "axes.labelsize": 8.5,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 7.5,
        "figure.dpi": 300,
    }
)


def log10_x(ax, lo=5, hi=400):
    ax.set_xscale("log")
    ax.set_xlim(lo, hi)
    ax.set_xticks([7, 14, 30, 60, 90, 180, 365])
    ax.set_xticklabels(["7", "14", "30", "60", "90", "180", "365"])


def main() -> None:
    dec = pd.read_csv(MECH / "benefit_decomposition.csv")
    fam = pd.read_csv(P1 / "family_benefit_table.csv")
    cross = pd.read_csv(P4 / "mae_crossing_ci.csv")
    stations = pd.read_csv(MECH / "station_crossings.csv")
    summary = pd.read_csv(MECH / "station_crossing_summary.csv")

    fig, axes = plt.subplots(2, 2, figsize=(11.0, 8.2))

    # ---------------- (a) second panel: the law ---------------------------
    ax = axes[0][0]
    s = dec.loc[dec["panel"] == "second"].sort_values("gap_length")
    ax.plot(s["gap_length"], s["clim_mae"], color="0.25", ls="--", lw=1.6,
            marker="D", ms=4, label="climatology default MAE")
    ax.plot(s["gap_length"], s["model_mae"], color=PANEL_COLOR["second"],
            lw=1.6, marker="o", ms=4, label="recovery model MAE")
    row = cross.loc[cross["panel"] == "second"].iloc[0]
    x0 = float(row["point_crossing_day"])
    lo, hi = float(row["ci_low"]), float(row["ci_high"])
    ax.axvline(x0, color=PANEL_COLOR["second"], ls="-", lw=1.0, alpha=0.8)
    ax.axvspan(lo, hi, color=PANEL_COLOR["second"], alpha=0.08)
    ax.axvspan(5, lo, color="#2ca02c", alpha=0.07)
    ax.axvspan(hi, 400, color="#d62728", alpha=0.07)
    ax.text(8.5, 3.6, "reconstruct\n(expected gain)", fontsize=7, color="#2ca02c")
    ax.text(160, 3.6, "use the default\n(expected harm)", fontsize=7, color="#d62728")
    ax.annotate(
        f"crossing: {x0:.0f} d\nCI {lo:.0f}-{hi:.0f} d",
        xy=(x0, 2.2), xytext=(95, 3.05), fontsize=7.5,
        color=PANEL_COLOR["second"],
        arrowprops={"arrowstyle": "-", "color": PANEL_COLOR["second"], "lw": 0.8},
    )
    log10_x(ax)
    ax.set_ylim(0, 5.8)
    ax.set_ylabel("mean absolute error (°C)")
    ax.set_title("(a) The law, second panel: flat default, rising model, one crossing")
    ax.legend(frameon=False, loc="upper left")
    # asserts
    clim7, clim365 = float(s["clim_mae"].iloc[0]), float(s["clim_mae"].iloc[-1])
    mod7, mod365 = float(s["model_mae"].iloc[0]), float(s["model_mae"].iloc[-1])
    assert clim365 / clim7 > 0.94 and clim365 / clim7 < 0.97  # ~4% decline
    assert mod365 / mod7 > 9.0 and mod365 / mod7 < 10.0  # ~9.8x growth
    assert abs(x0 - 91.489) < 0.5 and abs(lo - 85.270) < 0.5

    # ---------------- (b) first panel: three families ---------------------
    ax = axes[1][0]
    clim_first = dec.loc[dec["panel"] == "first"].set_index("gap_length")["clim_mae"]
    ax.plot(DUR, [clim_first.loc[d] for d in DUR], color="0.25", ls="--", lw=1.6,
            marker="D", ms=4, label="climatology threshold line (model-independent)")
    for fam_key, (color, marker, label) in FAMILY_STYLE.items():
        f = fam.loc[fam["model_family"] == fam_key].sort_values("gap_length_days")
        model_mae = clim_first.loc[f["gap_length_days"].to_numpy()].to_numpy() - \
            f["mean_benefit_deg_c"].to_numpy()
        ax.plot(f["gap_length_days"], model_mae, color=color, lw=1.4, marker=marker,
                ms=4, label=label)
    ax.annotate("crosses 60-90 d", xy=(73, 1.45), xytext=(9.5, 2.6), fontsize=7,
                color=FAMILY_STYLE["seasonal_boundary_ridge"][0],
                arrowprops={"arrowstyle": "-",
                            "color": FAMILY_STYLE["seasonal_boundary_ridge"][0],
                            "lw": 0.8})
    ax.annotate("cross 90-180 d", xy=(150, 1.5), xytext=(95, 3.7), fontsize=7,
                color=FAMILY_STYLE["xgboost_b_d"][0],
                arrowprops={"arrowstyle": "-",
                            "color": FAMILY_STYLE["xgboost_b_d"][0], "lw": 0.8})
    log10_x(ax)
    ax.set_ylim(0, 6.2)
    ax.set_ylabel("mean absolute error (°C)")
    ax.set_title("(b) First panel: same threshold line, three model curves, "
                 "different crossings")
    ax.legend(frameon=False, loc="upper left", fontsize=6.8)
    # asserts: family sign pattern on the grid intervals
    for fam_key in ("xgboost_b_d", "donor_blup_ridge"):
        f = fam.loc[fam["model_family"] == fam_key].set_index("gap_length_days")
        assert f.loc[90, "mean_benefit_deg_c"] > 0
        assert f.loc[180, "mean_benefit_deg_c"] < 0
    f = fam.loc[fam["model_family"] == "seasonal_boundary_ridge"].set_index(
        "gap_length_days")
    assert f.loc[60, "mean_benefit_deg_c"] > 0 and f.loc[90, "mean_benefit_deg_c"] < 0

    # ---------------- (c)/(d) station-level prediction --------------------
    for ax, panel in zip((axes[0][1], axes[1][1]), ("second", "first")):
        g = stations.loc[stations["panel"] == panel]
        srow = summary.loc[summary["panel"] == panel].iloc[0]
        x = g["station_clim_mae"].to_numpy(float)
        y = np.log10(g["crossing_days"].to_numpy(float))
        ax.scatter(x, y, s=7, alpha=0.45, color=PANEL_COLOR[panel],
                   edgecolors="none")
        k, b = np.polyfit(x, y, 1)
        xs = np.linspace(x.min(), x.max(), 50)
        ax.plot(xs, k * xs + b, color="k", lw=1.0)
        rho = float(srow["spearman"])
        pval = float(srow["p_value"])
        ax.text(0.03, 0.95,
                f"{panel} panel (n = {len(g)})\n"
                f"Spearman ρ = {rho:+.3f}\np = {pval:.1e}",
                transform=ax.transAxes, va="top", fontsize=7.5)
        ax.set_yticks(np.log10([30, 60, 90, 180, 365]))
        ax.set_yticklabels(["30", "60", "90", "180", "365"])
        ax.set_xlabel("station climatology MAE (°C)")
        ax.set_ylabel("crossing day (log scale)")
        ax.set_title("(c) The law's station-level prediction, second panel"
                     if panel == "second"
                     else "(d) The law's station-level prediction, first panel")
        assert abs(rho - (0.410598 if panel == "second" else 0.243114)) < 1e-4

    fig.tight_layout()
    fig.savefig(OUT)
    plt.close(fig)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
