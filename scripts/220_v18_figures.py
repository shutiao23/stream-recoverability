#!/usr/bin/env python3
"""Figures for the v18 closure programme."""

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
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from stream_recoverability.plotting.journal import (  # noqa: E402
    journal_mode,
    panel_grid,
    rc_overrides,
)
from stream_recoverability.experiments.v18_closure.paths import (  # noqa: E402
    FIGURES as DEFAULT_FIGURES,
    E1_SEASONALITY,
    E2_DEPLOYMENT,
    E3_SINE,
    E4_REPRESENTATIVENESS,
    E6_SUPPORT,
)

FIGURES = Path(os.environ.get("WRR_FIGURE_DIR", DEFAULT_FIGURES))

SURFACE = "#fcfcfb"
INK, INK_2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8985", "#e4e3df"
# Validated with the dataviz palette checker in this order: worst adjacent pair
# dE 20.1 under deuteranopia, 27.7 under normal vision. The aqua sits below 3:1
# against the surface, so every series carrying it is also directly labelled.
BLUE, ORANGE, PURPLE, AQUA = "#2a78d6", "#eb6834", "#9a5bd6", "#1baf7a"
SEQ = LinearSegmentedColormap.from_list(
    "seq_blue", ["#eef4fd", "#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"]
)
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.size": 8.5,
        "axes.labelsize": 8.5,
        "axes.titlesize": 9.5,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_2,
        "text.color": INK,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "legend.frameon": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "lines.linewidth": 2.0,
    }
)
plt.rcParams.update(rc_overrides())


def panel_label(ax, letter: str, title: str) -> None:
    ax.set_title(f"({letter}) {title}", loc="left", color=INK, pad=8)


def save(fig, stem: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    for extension in ("pdf", "png"):
        # 400 dpi: the support-law panel rasterises a heatmap, and at 260 dpi the
        # embedded image printed at only 260 ppi.
        fig.savefig(FIGURES / f"{stem}.{extension}", dpi=400, bbox_inches="tight")
    plt.close(fig)
    print(FIGURES.relative_to(ROOT) / f"{stem}.pdf")


# --------------------------------------------------------------- figure V1

def figure_seasonality() -> None:
    gaps = pd.read_parquet(E1_SEASONALITY / "real_gaps.parquet")
    calendars = pd.read_csv(E1_SEASONALITY / "maintenance_calendars.csv")

    fig, axes = panel_grid(2, (10.8, 3.8))

    ax = axes[0]
    # Two shaded blocks rather than one, because the autumn-to-winter season
    # wraps the year boundary.
    ax.axvspan(-0.55, 0.5, color="#eef4fd", zorder=0)
    ax.axvspan(7.5, 11.55, color="#eef4fd", zorder=0)
    classes = (
        ("under 30 d", (1, 29), MUTED),
        ("30–89 d", (30, 89), PURPLE),
        ("90 d and longer", (90, 10_000), ORANGE),
    )
    width, x, ceiling = 0.26, np.arange(12), 0.0
    for offset, (label, (low, high), colour) in enumerate(classes):
        block = gaps.loc[gaps["length"].between(low, high)]
        counts = block["start_month"].value_counts().reindex(range(1, 13)).fillna(0.0)
        shares = (counts / counts.sum() * 100).to_numpy()
        ceiling = max(ceiling, float(shares.max()))
        ax.bar(x + (offset - 1) * width, shares, width, color=colour,
               label=f"{label}  (n={len(block):,})")
    ax.axhline(100 / 12, color=INK_2, linewidth=1.0, linestyle=(0, (4, 3)), zorder=4)
    ax.annotate("uniform", xy=(11.45, 100 / 12), xytext=(0, 4), textcoords="offset points",
                ha="right", fontsize=7.5, color=INK_2)
    ax.set_xticks(x)
    ax.set_xticklabels(MONTHS)
    ax.set_ylabel("share of outages beginning in the month (%)")
    ax.set_ylim(0, ceiling * 1.32)
    ax.legend(fontsize=6.0 if journal_mode() else 7.5, ncol=3, loc="upper center",
              bbox_to_anchor=(0.5, 1.02))
    ax.grid(axis="x", visible=False)
    panel_label(ax, "a", "When real outages begin")

    ax = axes[1]
    order = ["autumn_sep_to_jan", "observed", "uniform", "spring_mar_to_jul"]
    names = {
        "observed": "as observed",
        "uniform": "uniform over the year",
        "spring_mar_to_jul": "concentrated Mar–Jul",
        "autumn_sep_to_jan": "concentrated Sep–Jan",
    }
    block = calendars.set_index("calendar").loc[order]
    values = block["consequential_rate"].to_numpy() * 100
    colours = [AQUA if name == "autumn_sep_to_jan" else ORANGE if name == "spring_mar_to_jul" else BLUE for name in order]
    bars = ax.barh(range(len(order)), values, color=colours, height=0.62)
    for rect, value, points in zip(bars, values, block["points_vs_observed"]):
        ax.text(value + 0.18, rect.get_y() + rect.get_height() / 2,
                f"{value:.1f}%  ({points:+.1f} pts)", va="center", fontsize=8, color=INK)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([names[name] for name in order])
    ax.set_xlabel("consequential-error rate of the annual peak (%)")
    ax.set_xlim(0, max(values) * 1.36)
    ax.grid(axis="y", visible=False)
    panel_label(ax, "b", "What the maintenance calendar is worth")

    fig.tight_layout(h_pad=1.6 if journal_mode() else 1.08)
    save(fig, "figv1_outage_seasonality")


# --------------------------------------------------------------- figure V2

def figure_deployment() -> None:
    thresholds = pd.read_csv(E2_DEPLOYMENT / "threshold_disagreement.csv")
    transported = pd.read_csv(E2_DEPLOYMENT / "transported_risk.csv")
    consequence = pd.read_csv(E2_DEPLOYMENT / "archive_consequence.csv")

    fig, axes = panel_grid(3, (13.2, 3.7))

    ax = axes[0]
    labels = (
        ["unfilled\n(49 d)", "with imputation\n(140 d)"]
        if journal_mode()
        else ["Johnson\nunfilled (49 d)", "Johnson with\nimputation (140 d)"]
    )
    parts = [
        ("agree_admit", "both admit", "#dce9fa"),
        ("admitted_by_length_rejected_by_timing", "length admits, timing rejects", ORANGE),
        ("rejected_by_length_admitted_by_timing", "length rejects, timing admits", BLUE),
        ("agree_reject", "both reject", MUTED),
    ]
    bottom = np.zeros(len(thresholds))
    for column, legend, colour in parts:
        values = thresholds[column].to_numpy(dtype=float)
        ax.bar(labels, values, 0.55, bottom=bottom, color=colour, label=legend,
               edgecolor=SURFACE, linewidth=2)
        for index, (value, base) in enumerate(zip(values, bottom)):
            if value > (250 if journal_mode() else 120):
                ax.text(index, base + value / 2, f"{int(value)}", ha="center", va="center",
                        fontsize=6.2 if journal_mode() else 8,
                        color=INK if colour == "#dce9fa" else "#ffffff")
        bottom += values
    for index, row in thresholds.iterrows():
        ax.text(index, bottom[index] + (90 if journal_mode() else 40),
                f"{row['disagreement_pct']:.1f}%\ndisagree" if journal_mode()
                else f"{row['disagreement_pct']:.1f}% disagree",
                ha="center", fontsize=6.2 if journal_mode() else 8, color=INK)
    ax.set_ylabel("real incomplete station-years")
    ax.set_ylim(0, 3100 if journal_mode() else 2700)
    if journal_mode():
        ax.set_xlabel("published limit")
    ax.legend(fontsize=5.8 if journal_mode() else 7, loc="lower center",
              bbox_to_anchor=(0.5, -0.62 if journal_mode() else -0.36), ncol=2)
    ax.grid(axis="x", visible=False)
    panel_label(ax, "a", "The two rules on 2,422 real incomplete years")

    ax = axes[1]
    keep = [
        "admit everything",
        "Johnson with imputation (<= 140 d)",
        "Johnson unfilled (<= 49 d)",
        "peak window <= 10% hidden",
    ]
    block = transported.set_index("rule").loc[keep]
    values = block["predicted_consequential_rate_pct"].to_numpy()
    colours = [MUTED, ORANGE, ORANGE, BLUE]
    bars = ax.barh(range(len(keep)), values, color=colours, height=0.62)
    for rect, value, retention in zip(bars, values, block["retention_pct"]):
        ax.text(value + 0.06, rect.get_y() + rect.get_height() / 2,
                f"{value:.2f}%   (keeps {retention:.0f}%)", va="center", fontsize=8, color=INK)
    ax.set_yticks(range(len(keep)))
    ax.set_yticklabels(["admit everything", "length ≤ 140 d", "length ≤ 49 d", "peak window ≤ 10% hidden"])
    ax.set_xlabel("predicted consequential-error rate (%)")
    ax.set_xlim(0, max(values) * 1.5)
    ax.grid(axis="y", visible=False)
    panel_label(ax, "b", "Transported risk (extrapolation)")

    ax = axes[2]
    keep = [
        "repair everything, no screening",
        "Johnson with imputation (<= 140 d)",
        "Johnson unfilled (<= 49 d)",
        "peak window <= 10% hidden",
    ]
    block = consequence.set_index("rule").loc[keep]
    x = np.arange(len(keep))
    half = block["admitted_with_half_the_peak_window_hidden"].to_numpy(dtype=float)
    whole = block["admitted_with_peak_window_wholly_hidden"].to_numpy(dtype=float)
    ax.bar(x - 0.19, half, 0.36, color=ORANGE, label="more than half the peak window hidden")
    ax.bar(x + 0.19, whole, 0.36, color=PURPLE, label="peak window wholly hidden")
    for index, (a, b) in enumerate(zip(half, whole)):
        ax.text(index - 0.19, a + 4, f"{int(a)}", ha="center", fontsize=8, color=INK)
        ax.text(index + 0.19, b + 4, f"{int(b)}", ha="center", fontsize=8, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels(["repair\neverything", "length\n≤ 140 d", "length\n≤ 49 d", "peak window\n≤ 10% hidden"])
    ax.set_ylabel("admitted station-years")
    ax.set_ylim(0, max(half) * 1.24)
    ax.legend(fontsize=7.5, loc="upper right")
    ax.grid(axis="x", visible=False)
    panel_label(ax, "c", "Admitted years with >½ peak window hidden (not the 261-year population)")

    fig.tight_layout(h_pad=1.6 if journal_mode() else 1.08)
    save(fig, "figv2_archive_deployment")


# --------------------------------------------------------------- figure V3

def figure_support_law() -> None:
    sweep = pd.read_csv(E6_SUPPORT / "support_width_sweep.csv")
    contrasts = pd.read_csv(E6_SUPPORT / "auc_contrasts_by_width.csv")
    matrix = pd.read_csv(E6_SUPPORT / "conditioning_width_matrix.csv")
    sine = pd.read_csv(E3_SINE / "sine_axis_comparison.csv")
    summary = json.loads((E6_SUPPORT / "summary.json").read_text())

    fig, axes = panel_grid(3, (13.4, 3.8))

    ax = axes[0]
    block = contrasts.sort_values("support_width_days")
    x = block["support_width_days"].to_numpy(dtype=float)
    ax.fill_between(x, block["low"], block["high"], color=BLUE, alpha=0.16, linewidth=0)
    ax.plot(x, block["point"], color=BLUE, marker="o", markersize=5, zorder=3)
    ax.axhline(0.0, color=INK_2, linewidth=1.1, linestyle=(0, (4, 3)))
    crossover = float(summary["P2_crossover"]["crossover_width_days"])
    ax.axvline(crossover, color=ORANGE, linewidth=1.4)
    ax.annotate(f"crossover\n{crossover:.0f} days", xy=(crossover, 0.045), xytext=(6, 0),
                textcoords="offset points", fontsize=6.4 if journal_mode() else 8,
                color=ORANGE, va="center")
    ax.set_xscale("log")
    ticks = [1, 7, 30, 90, 365] if journal_mode() else [1, 3, 7, 15, 30, 60, 90, 182, 365]
    ax.set_xticks(ticks)
    ax.set_xticklabels(ticks)
    ax.set_xlabel("support width of the estimand, k days")
    ax.set_ylabel("AUC(peak window) − AUC(whole-year missing)")
    ax.annotate("timing axis wins", xy=(1.3, 0.030 if journal_mode() else 0.062),
                fontsize=6.4 if journal_mode() else 8, color=BLUE)
    ax.annotate("length axis wins", xy=(105, -0.145),
                fontsize=6.4 if journal_mode() else 8, color=ORANGE)
    panel_label(ax, "a", "The reversal is a continuum")

    ax = axes[1]
    widths = [int(c.replace("condition_", "")) for c in matrix.columns if c.startswith("condition_")]
    grid = matrix[[f"condition_{w}" for w in widths]].to_numpy(dtype=float)
    image = ax.imshow(grid, cmap=SEQ, aspect="auto", vmin=0.70, vmax=0.88)
    ax.set_xticks(range(len(widths)))
    ax.set_xticklabels(widths, fontsize=5.6 if journal_mode() else None)
    ax.set_yticks(range(len(matrix)))
    ax.set_yticklabels(matrix["endpoint_width_days"].astype(int),
                       fontsize=5.6 if journal_mode() else None)
    for row_index, row in matrix.iterrows():
        best = widths.index(int(row["best_conditioning_width_days"]))
        ax.add_patch(plt.Rectangle((best - 0.5, row_index - 0.5), 1, 1, fill=False,
                                   edgecolor=ORANGE, linewidth=2.0, zorder=4))
        own = int(row["endpoint_width_days"])
        if own in widths:
            ax.plot(widths.index(own), row_index, marker="s", markersize=4,
                    markerfacecolor="none", markeredgecolor=INK, markeredgewidth=1.0, zorder=5)
    ax.set_xlabel("climatological window the screen conditions on (days)")
    ax.set_ylabel("support width of the estimand (days)")
    ax.grid(False)
    bar = fig.colorbar(image, ax=ax, fraction=0.045, pad=0.02)
    bar.ax.tick_params(labelsize=7, color=GRID)
    bar.set_label("AUC", size=7.5, color=INK_2)
    if not journal_mode():
        ax.annotate("orange = best; black square = the estimand's own support",
                    xy=(0.0, -0.30), xycoords="axes fraction", fontsize=7.5, color=INK_2)
    panel_label(ax, "b", "Condition on a widened support")

    ax = axes[2]
    block = sine.loc[(sine["protocol"] == "repaired") & (sine["tolerance_fraction"] > 0.4) & (sine["tolerance_fraction"] < 0.6)]
    order = ["sine_mean", "sine_amplitude", "sine_phase"]
    block = block.set_index("endpoint").loc[order]
    x = np.arange(len(order))
    width = 0.26
    ax.bar(x - width, block["auc_peak_overlap"], width, color=ORANGE, label="30-day peak window")
    ax.bar(x, block["auc_missing_fraction"], width, color=MUTED, label="whole-year missing fraction")
    ax.bar(x + width, block["auc_influence_hidden"], width, color=BLUE, label="influence-weighted hidden mass")
    for index, row in enumerate(block.itertuples()):
        for offset, value in ((-width, row.auc_peak_overlap), (0, row.auc_missing_fraction), (width, row.auc_influence_hidden)):
            ax.text(index + offset, value + 0.008, f"{value:.2f}", ha="center", fontsize=7.5, color=INK)
    ax.axhline(0.5, color=MUTED, linewidth=1.0, linestyle=(0, (3, 3)))
    ax.set_xticks(x)
    ax.set_xticklabels(["fitted mean", "amplitude", "phase"])
    ax.set_ylim(0.5, 0.95)
    ax.set_ylabel("AUC for a consequential error")
    if journal_mode():
        ax.legend(fontsize=6.0, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3)
    else:
        ax.legend(fontsize=7.2, loc="upper center", bbox_to_anchor=(0.5, 1.03), ncol=1)
    ax.grid(axis="x", visible=False)
    panel_label(ax, "c", "Johnson et al.'s own three estimands")

    fig.tight_layout(h_pad=1.6 if journal_mode() else 1.08)
    save(fig, "figv3_support_law")


# --------------------------------------------------------------- figure V4

def figure_representativeness() -> None:
    frontier = pd.read_csv(E4_REPRESENTATIVENESS / "representativeness_frontier.csv")
    elevation = pd.read_csv(E4_REPRESENTATIVENESS / "elevation_retention.csv")

    fig, axes = panel_grid(2, (10.6, 3.8))

    ax = axes[0]
    block = frontier.loc[(frontier["split"] == "reserved") & (frontier["retention_target"] == 0.70)]
    labels = {
        "length rule (incumbent)": ("length rule", ORANGE),
        "peak-overlap rule": ("peak-overlap rule", PURPLE),
        "calibrated screen, global threshold": ("screen, global", BLUE),
        "calibrated screen, balanced within donor_and_elevation": ("screen, balanced", AQUA),
    }
    for row in block.itertuples():
        if row.rule not in labels:
            continue
        name, colour = labels[row.rule]
        ax.scatter(abs(row.rho_ELEV_SITE_M), row.error_rate_pct, s=95, color=colour, zorder=3,
                   edgecolor=SURFACE, linewidth=1.5)
        ax.annotate(f"{name}\n{row.error_rate_pct:.2f}%", xy=(abs(row.rho_ELEV_SITE_M), row.error_rate_pct),
                    xytext=(9, -3), textcoords="offset points", fontsize=8, color=INK, va="top")
    ax.set_xlabel("|Spearman ρ| between station retention and site elevation")
    ax.set_ylabel("consequential-error rate among retained (%)")
    ax.set_xlim(-0.02, 0.42)
    ax.set_ylim(0, 10.5)
    ax.annotate("better on both axes", xy=(0.02, 0.6), fontsize=7.5, color=INK_2)
    panel_label(ax, "a", "Accuracy against representativeness, reserved panel")

    ax = axes[1]
    block = elevation.loc[elevation["split"] == "reserved"]
    names = {
        "length rule (incumbent)": ("length rule", ORANGE),
        "calibrated screen, global threshold": ("screen, global", BLUE),
        "calibrated screen, balanced within elevation_tertile": ("screen, balanced", AQUA),
    }
    tertiles = ("low", "middle", "high")
    x = np.arange(len(tertiles))
    width = 0.26
    for offset, (rule, (name, colour)) in enumerate(names.items()):
        row = block.loc[block["rule"] == rule]
        if row.empty:
            continue
        values = [float(row[f"retention_{t}"].iloc[0]) * 100 for t in tertiles]
        ax.bar(x + (offset - 1) * width, values, width, color=colour, label=name)
        for index, value in enumerate(values):
            ax.text(index + (offset - 1) * width, value + 0.6, f"{value:.0f}", ha="center", fontsize=7.5, color=INK)
    ax.axhline(70, color=INK_2, linewidth=1.0, linestyle=(0, (4, 3)))
    ax.set_xticks(x)
    ax.set_xticklabels(["low", "middle", "high"])
    ax.set_xlabel("site elevation tertile")
    ax.set_ylabel("station-years retained (%)")
    ax.set_ylim(55, 88)
    ax.legend(fontsize=7.5, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.04))
    ax.grid(axis="x", visible=False)
    panel_label(ax, "b", "Who gets kept")

    fig.tight_layout(h_pad=1.6 if journal_mode() else 1.08)
    save(fig, "figv4_representativeness")


def main() -> int:
    figure_seasonality()
    figure_deployment()
    figure_support_law()
    figure_representativeness()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
