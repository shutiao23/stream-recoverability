#!/usr/bin/env python3
"""Two figures the Q1 revision adds: robustness of the central claim, and
which rivers are hard.

Colours are the validated categorical slots with direct labels, matching the
other figures in the set.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.plotting.journal import (  # noqa: E402
    journal_mode,
    panel_grid,
    rc_overrides,
)
from stream_recoverability.experiments.v17_fitness.paths import RESULTS_ROOT  # noqa: E402

FIGURES = Path(os.environ.get("WRR_FIGURE_DIR", ROOT / "figures" / "v17"))
SURFACE, INK, INK_2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8985", "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.size": 8.5, "axes.labelsize": 8.5, "axes.titlesize": 9.5,
        "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "text.color": INK,
        "xtick.color": INK_2, "ytick.color": INK_2, "xtick.labelsize": 8, "ytick.labelsize": 8,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
        "legend.frameon": False, "axes.spines.top": False, "axes.spines.right": False,
        "lines.linewidth": 2.0,
    }
)
plt.rcParams.update(rc_overrides())

LABELS = {
    "hottest7": "hottest 7 d\n(regulatory window)",
    "hottest30": "hottest 30 d\n(primary)",
    "amplitude30": "amplitude",
    "annual_mean": "annual mean",
    "coldest30": "coldest 30 d",
}


def _save(fig, name: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "pdf"):
        fig.savefig(FIGURES / f"{name}.{suffix}", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote figures/v17/{name}.png")


def figure5_robustness() -> None:
    step = RESULTS_ROOT / "step22_robustness"
    contrasts = pd.read_csv(step / "auc_contrasts.csv")
    sweep = pd.read_csv(step / "threshold_sweep.csv")
    # F11: the frozen step-22 noise JSON predates the method lock in
    # scripts/202_v17_robustness.py. Prefer the amendment, which re-ran the same
    # comparison with one method on both arms; fall back only if it is absent.
    amendment = ROOT / "results/wrr_submission_ready/amendments/step22_noise_post_fix/noise_sensitivity.json"
    noise_source = amendment if amendment.is_file() else step / "noise_sensitivity.json"
    noise = json.loads(noise_source.read_text())

    fig, axes = panel_grid(3, (13.0, 3.6), width_ratios=[1.05, 0.85, 1.0])

    ax = axes[0]
    order = [m for m in ("hottest7", "hottest30", "amplitude30", "annual_mean", "coldest30")
             if m in set(contrasts["metric"])]
    block = contrasts.set_index("metric").reindex(order)
    y = np.arange(len(order))
    colours = [BLUE if v > 0 else ORANGE for v in block["auc_timing_minus_length"]]
    ax.barh(y, block["auc_timing_minus_length"], color=colours, height=0.6)
    ax.errorbar(
        block["auc_timing_minus_length"], y,
        xerr=[block["auc_timing_minus_length"] - block["ci_low"], block["ci_high"] - block["auc_timing_minus_length"]],
        fmt="none", ecolor=INK, elinewidth=1.1, capsize=3,
    )
    ax.axvline(0, color=INK_2, linewidth=1.1)
    ax.set_yticks(y, [LABELS.get(m, m) for m in order], fontsize=7.6)
    ax.invert_yaxis()
    ax.set_xlabel("AUC(timing) − AUC(outage length)")
    ax.set_title("a  Which axis wins" if journal_mode() else "a  Which axis wins, with clustered intervals", loc="left", pad=8)
    ax.grid(axis="y", visible=False)
    ax.text(0.02, len(order) - 0.55, "timing →", fontsize=7.4, color=BLUE)
    ax.text(-0.02, len(order) - 0.55, "← length", fontsize=7.4, color=ORANGE, ha="right")

    ax = axes[1]
    dev, res = noise["development"], noise["reserved"]
    labels = ["development", "reserved"]
    clean = [dev["contrast_clean_points"], res["contrast_clean_points"]]
    noisy = [dev["contrast_noisy_points"], res["contrast_noisy_points"]]
    x = np.arange(len(labels))
    ax.bar(x - 0.19, clean, 0.36, color=BLUE, label="exact reference")
    ax.bar(x + 0.19, noisy, 0.36, color=AQUA, label=f"reference + {noise['development']['sensor_noise_c']} °C")
    for xi, (a, b) in enumerate(zip(clean, noisy)):
        ax.text(xi - 0.19, a + 0.15, f"{a:.1f}", ha="center", fontsize=7.6, color=INK)
        ax.text(xi + 0.19, b + 0.15, f"{b:.1f}", ha="center", fontsize=7.6, color=INK)
    ax.set_xticks(x, labels)
    ax.set_ylabel("advantage over length rule (points)")
    ax.set_title("b  Instrument error" if journal_mode() else "b  Instrument error changes nothing", loc="left", pad=8)
    ax.grid(axis="x", visible=False)
    ax.legend(fontsize=7.2, loc="upper right")
    ax.set_ylim(0, max(clean + noisy) * 1.3)

    ax = axes[2]
    pivot = sweep.pivot_table(index="threshold_c", columns="treatment", values="misclassification_rate")
    series = {
        "observed_days": (MUTED, "compute on observed days"),
        "reconstruct_all": (INK_2, "reconstruct, no screen"),
        "length_screened": (ORANGE, "length rule"),
        "certificate_screened": (BLUE, "certificate"),
    }
    for name, (colour, label) in series.items():
        if name not in pivot.columns:
            continue
        ax.plot(pivot.index, pivot[name] * 100, color=colour, marker="o", markersize=3.5)
        ax.annotate(label, xy=(pivot.index[-1], pivot[name].iloc[-1] * 100), xytext=(4, 0),
                    textcoords="offset points", fontsize=7.2, color=colour, va="center")
    ax.set_xlabel("ecological threshold (°C)")
    ax.set_ylabel("exceedance misclassification (%)")
    ax.set_title("c  Not an artefact of 20 °C" if journal_mode() else "c  The result is not an artefact of 20 °C", loc="left", pad=8)
    ax.set_xlim(pivot.index.min() - 0.5, pivot.index.max() + 3.4)

    fig.tight_layout(h_pad=1.8 if journal_mode() else 1.08)
    _save(fig, "fig5_robustness")


def figure6_hydrology() -> None:
    step = RESULTS_ROOT / "step21_hydrology"
    correlations = pd.read_csv(step / "correlations.csv")
    strata = pd.read_csv(step / "strata.csv")

    fig, axes = panel_grid(3, (13.6, 3.6), width_ratios=[1.05, 0.9, 0.9])

    ax = axes[0]
    block = correlations.loc[correlations["target"].eq("donor_synchrony")].copy()
    pretty = {
        "BFI_AVE": "baseflow index", "CONTACT": "subsurface contact time",
        "log_storage": "upstream storage (log)", "log_area": "drainage area (log)",
        "ELEV_SITE_M": "site elevation", "SLOPE_PCT": "basin slope",
    }
    block["label"] = block["predictor"].map(pretty).fillna(block["predictor"])
    block = block.sort_values("spearman_rho")
    y = np.arange(len(block))
    colours = [BLUE if e else MUTED for e in block["excludes_zero"]]
    ax.barh(y, block["spearman_rho"], color=colours, height=0.6)
    ax.errorbar(
        block["spearman_rho"], y,
        xerr=[block["spearman_rho"] - block["ci_low"], block["ci_high"] - block["spearman_rho"]],
        fmt="none", ecolor=INK, elinewidth=1.0, capsize=3,
    )
    ax.axvline(0, color=INK_2, linewidth=1.1)
    ax.set_yticks(y, block["label"], fontsize=7.8)
    ax.set_xlabel("Spearman ρ with donor synchrony")
    ax.set_title("a  What makes donors informative", loc="left", pad=8)
    ax.grid(axis="y", visible=False)

    ax = axes[1]
    bfi = strata.loc[strata["variable"].eq("BFI_AVE")].copy()
    order = ["low", "middle", "high"]
    bfi = bfi.set_index("stratum").reindex([s for s in order if s in set(bfi["stratum"])]).reset_index()
    x = np.arange(len(bfi))
    ax.bar(x - 0.2, bfi["donor_synchrony"], 0.4, color=AQUA, label="donor synchrony")
    ax2 = ax.twinx()
    ax2.bar(x + 0.2, bfi["mean_abs_error"], 0.4, color=ORANGE, label="mean abs. error (°C)")
    ax2.grid(False)
    for xi, (s, e, n) in enumerate(zip(bfi["donor_synchrony"], bfi["mean_abs_error"], bfi["n_stations"])):
        size = 5.8 if journal_mode() else 7.4
        ax.text(xi - 0.2, s + 0.012, f"{s:.2f}", ha="center", fontsize=size, color=AQUA)
        ax2.text(xi + 0.2, e + (0.010 if journal_mode() else 0.004), f"{e:.3f}",
                 ha="center", fontsize=size, color=ORANGE)
    if journal_mode():
        ax.set_xticks(x, list(bfi["stratum"]), fontsize=6.0)
        ax.set_xlabel(f"baseflow-index tertile (n = {int(bfi['n_stations'].min())}-{int(bfi['n_stations'].max())})")
    else:
        ax.set_xticks(
            x,
            [f"{s}\nBFI (n={int(n)})" for s, n in zip(bfi["stratum"], bfi["n_stations"])],
            fontsize=7.6,
        )
    ax.set_ylabel("donor synchrony", color=AQUA)
    ax2.set_ylabel("mean absolute error (°C)", color=ORANGE)
    ax.set_title("b  Groundwater-influenced basins", loc="left", pad=8)
    ax.grid(axis="x", visible=False)
    ax.set_ylim(0, max(bfi["donor_synchrony"]) * (1.35 if journal_mode() else 1.25))
    ax2.set_ylim(0, max(bfi["mean_abs_error"]) * (1.45 if journal_mode() else 1.3))

    ax = axes[2]
    ax.bar(x - 0.2, bfi["peak_magnitude_c"], 0.4, color=ORANGE)
    ax3 = ax.twinx()
    ax3.bar(x + 0.2, bfi["peak_interannual_sd_c"], 0.4, color=BLUE)
    ax3.grid(False)
    for xi, (mag, sd) in enumerate(zip(bfi["peak_magnitude_c"], bfi["peak_interannual_sd_c"])):
        ax.text(xi - 0.2, mag + 0.25, f"{mag:.1f}", ha="center", fontsize=7.4, color=INK)
        ax3.text(xi + 0.2, sd + 0.012, f"{sd:.2f}", ha="center", fontsize=7.4, color=INK)
    ax.set_xticks(x, list(bfi["stratum"]) if journal_mode() else [f"{s}\nBFI" for s in bfi["stratum"]],
                  fontsize=6.0 if journal_mode() else 7.6)
    if journal_mode():
        ax.set_xlabel("baseflow-index tertile")
    ax.set_ylabel("mean annual peak (°C)", color=ORANGE)
    ax3.set_ylabel("interannual SD of the peak (°C)", color=BLUE)
    ax.set_title("c  A damped regime is a smaller target" if journal_mode() else "c  Why: a damped regime is a smaller target", loc="left", pad=8)
    ax.grid(axis="x", visible=False)
    ax.set_ylim(0, max(bfi["peak_magnitude_c"]) * 1.2)
    ax3.set_ylim(0, max(bfi["peak_interannual_sd_c"]) * 1.35)

    fig.tight_layout(h_pad=1.8 if journal_mode() else 1.08)
    _save(fig, "fig6_hydrology")


def main() -> int:
    figure5_robustness()
    figure6_hydrology()
    # Merge rather than overwrite: figures 1-4 are written by script 188.
    path = RESULTS_ROOT / "figure_captions.json"
    captions = json.loads(path.read_text()) if path.exists() else {}
    captions.update(
        {
            "fig5_robustness": (
                "Robustness of the central claim: clustered intervals on the axis contrast for "
                "five endpoints, the effect of instrument-scale error in the reference series, "
                "and the exceedance result across ecological thresholds."
            ),
            "fig6_hydrology": (
                "Which rivers are hard: catchment attributes against donor synchrony, outcomes "
                "by baseflow-index tertile, and the thermal damping that makes "
                "groundwater-influenced basins an easier target despite less informative donors."
            ),
        }
    )
    path.write_text(json.dumps(captions, indent=2), encoding="utf-8")
    print(f"captions updated: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
