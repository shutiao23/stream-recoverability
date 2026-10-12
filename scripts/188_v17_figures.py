#!/usr/bin/env python3
"""Figures for the v17 manuscript.

Four figures, one per hypothesis. Colours are the validated categorical slots
(blue / orange / aqua) with the blue sequential ramp for magnitude; every line
carries a direct label so identity is never colour-alone, which also supplies
the relief the aqua slot needs against a light surface.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import json  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from stream_recoverability.plotting.journal import (  # noqa: E402
    journal_mode,
    panel_grid,
    rc_overrides,
)
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    RESULTS_ROOT,
    STEP4_CEILING,
    STEP10_CONFIRM,
    STEP5_MECHANISM,
    STEP6_SCREEN,
    STEP7_FRONTIER,
    STEP8_DOWNSTREAM,
)

FIGURES = Path(os.environ.get("WRR_FIGURE_DIR", ROOT / "figures" / "v17"))
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#8a8985"
GRID = "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SEQ = LinearSegmentedColormap.from_list(
    "seq_blue", ["#eef4fd", "#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"]
)

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
        "axes.axisbelow": True,
    }
)
plt.rcParams.update(rc_overrides())


def _save(fig, name: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "pdf"):
        fig.savefig(FIGURES / f"{name}.{suffix}", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote figures/v17/{name}.png")


def figure1_mechanism() -> None:
    table = pd.read_csv(STEP5_MECHANISM / "length_by_overlap.csv")
    nested = pd.read_csv(STEP5_MECHANISM / "nested_feature_sets.csv")
    importance = pd.read_csv(STEP5_MECHANISM / "permutation_importance.csv")

    grid = table.pivot(index="length_bucket", columns="overlap_bucket", values="rate_above_tolerance")
    order_rows = ["1-30", "31-60", "61-120", "121-200", "201+"]
    order_cols = ["0", "0-0.5", "0.5-1", "1"]
    grid = grid.reindex(index=order_rows, columns=order_cols)
    counts = table.pivot(index="length_bucket", columns="overlap_bucket", values="n").reindex(
        index=order_rows, columns=order_cols
    )

    generality = pd.read_csv(RESULTS_ROOT / "step17_metric_generality" / "metric_generality.csv")
    fig, axes = panel_grid(4, (15.8, 4.2), width_ratios=[1.0, 0.7, 0.95, 1.15])

    ax = axes[0]
    ax.grid(False)
    values = grid.to_numpy(dtype=float)
    thin = counts.to_numpy(dtype=float) < 30
    values = np.where(thin, np.nan, values)
    masked = np.ma.masked_invalid(values)
    palette = SEQ.copy()
    palette.set_bad("#f0efec")
    image = ax.imshow(masked, cmap=palette, vmin=0, vmax=0.5, aspect="auto")
    if journal_mode():
        ax.set_xticks(range(len(order_cols)), ["none", "<0.5", "0.5-1", "all"], fontsize=6.0)
        ax.set_yticks(range(len(order_rows)), order_rows, fontsize=6.0)
    else:
        ax.set_xticks(range(len(order_cols)), ["none", "partial\n(<0.5)", "most\n(0.5-1)", "complete"])
        ax.set_yticks(range(len(order_rows)), order_rows)
    ax.set_xlabel("share of the peak window hidden" if journal_mode()
                  else "share of the climatological peak window hidden")
    ax.set_ylabel("longest outage (days)")
    ax.set_title(("a  Error rate, annual peak" if journal_mode() else "a  Consequential-error rate, annual peak"), loc="left", pad=8)
    for i in range(len(order_rows)):
        for j in range(len(order_cols)):
            n = counts.to_numpy(dtype=float)[i, j]
            value = values[i, j]
            if not np.isfinite(value):
                ax.text(j, i, "n<30", ha="center", va="center",
                        fontsize=5.2 if journal_mode() else 7, color=MUTED)
                continue
            ax.text(
                j,
                i,
                f"{value:.0%}",
                ha="center",
                va="center",
                fontsize=5.6 if journal_mode() else 8,
                color="#ffffff" if value > 0.27 else INK,
                fontweight="bold" if n > 500 else "normal",
            )
    bar = fig.colorbar(image, ax=ax, fraction=0.045, pad=0.03)
    bar.outline.set_visible(False)
    bar.ax.tick_params(labelsize=7, color=GRID)
    bar.set_label("P(error > 0.5 °C)", size=7.5, color=INK_2)

    ax = axes[1]
    labels = nested["feature_set"].tolist()
    values = nested["grouped_cv_auc"].to_numpy()
    colours = [MUTED] + [BLUE] * (len(values) - 1)
    bars = ax.barh(range(len(values)), values, color=colours, height=0.6)
    for rect, value in zip(bars, values):
        ax.text(value + 0.004, rect.get_y() + rect.get_height() / 2, f"{value:.3f}", va="center", fontsize=8, color=INK)
    ax.set_yticks(range(len(labels)), labels)
    ax.invert_yaxis()
    ax.set_xlim(0.70, 0.92)
    ax.set_xlabel("grouped cross-validated AUC")
    ax.set_title("b  Each information layer adds", loc="left", pad=8)
    ax.grid(axis="y", visible=False)

    ax = axes[2]
    top = importance.iloc[::-1]
    names = top["feature"].str.replace("_", " ").tolist()
    values = top["permutation_r2_drop"].to_numpy()
    length_axis = {"longest run", "total missing", "missing fraction", "n runs"}
    colours = [ORANGE if name in length_axis else BLUE for name in names]
    ax.barh(range(len(values)), values, color=colours, height=0.7)
    ax.set_yticks(range(len(values)), names)
    ax.tick_params(axis="y", labelsize=7)
    ax.annotate(
        "outage-geometry axis",
        xy=(max(values) * 0.55, 1.2),
        fontsize=7.2,
        color=ORANGE,
    )
    ax.set_xlabel("drop in out-of-fold R² when permuted")
    ax.set_title(("c  Length adds almost nothing" if journal_mode() else "c  For the peak, outage length adds almost nothing"), loc="left", pad=8)
    ax.grid(axis="y", visible=False)

    ax = axes[3]
    labels = {
        "hottest7": "hot 7 d",
        "hottest30": "hot 30 d",
        "amplitude30": "amplitude",
        "annual_mean": "annual mean",
        "coldest30": "cold 30 d",
    }
    order = [m for m in ("hottest7", "hottest30", "amplitude30", "annual_mean", "coldest30")
             if m in set(generality["metric"])]
    block = generality.set_index("metric").reindex(order)
    x = np.arange(len(order))
    width = 0.27
    ax.bar(x - width, block["auc_peak_overlap"], width, color=BLUE, label="peak-window overlap")
    ax.bar(x, block["auc_warm_coverage"], width, color=AQUA, label="warm-season coverage")
    ax.bar(x + width, block["auc_longest_run"], width, color=ORANGE, label="outage length")
    ax.axhline(0.5, color=MUTED, linewidth=1.0, linestyle=(0, (3, 3)))
    for xi, metric in zip(x, order):
        timing = max(block.loc[metric, "auc_peak_overlap"], block.loc[metric, "auc_warm_coverage"])
        length = block.loc[metric, "auc_longest_run"]
        winner = "timing" if timing > length else "length"
        ax.text(
            xi,
            0.955 if journal_mode() else max(timing, length) + 0.018,
            winner,
            ha="center",
            fontsize=5.6 if journal_mode() else 7.6,
            color=BLUE if winner == "timing" else ORANGE,
            fontweight="bold",
        )
    ax.set_xticks(
        x,
        [labels[name] for name in order],
        fontsize=5.6 if journal_mode() else 7.6,
        rotation=32 if journal_mode() else 22,
        ha="right",
    )
    ax.set_ylim(0.4, 1.0)
    ax.set_ylabel("AUC for a consequential error")
    ax.set_title(("d  Which axis wins, by metric" if journal_mode() else "d  Which axis wins depends on the metric"), loc="left", pad=8)
    ax.grid(axis="x", visible=False)
    ax.legend(
        fontsize=5.4 if journal_mode() else 7.0,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.40 if journal_mode() else -0.17),
        ncol=2 if journal_mode() else 3,
        columnspacing=1.0,
        handlelength=1.2,
    )

    fig.tight_layout(h_pad=1.8 if journal_mode() else 1.08)
    _save(fig, "fig1_mechanism")


def _frontier_panel(ax, frame: pd.DataFrame, title: str, incumbent: pd.DataFrame) -> None:
    series = {
        "certificate": (BLUE, "certificate"),
        "length_rule": (ORANGE, "outage-length rule"),
        "peak_overlap_rule": (AQUA, "peak-overlap rule"),
        "random": (MUTED, "random"),
        "oracle": (INK_2, "oracle (retention only)"),
    }
    for name, (colour, label) in series.items():
        block = frame.loc[frame["screen"].eq(name)].sort_values("retention")
        if block.empty:
            continue
        style = {"linestyle": (0, (4, 3)), "linewidth": 1.4} if name in ("oracle", "random") else {}
        ax.plot(block["retention"] * 100, block["rate_above_0.5"] * 100, color=colour, **style)
        anchor = 0.55 if name == "certificate" else 0.62
        y = float(block.loc[block["retention"].sub(anchor).abs().idxmin(), "rate_above_0.5"]) * 100
        offsets = {"random": -12, "certificate": 9, "oracle": 6}
        ax.annotate(
            label,
            xy=(anchor * 100, y),
            xytext=(0, offsets.get(name, 5)),
            textcoords="offset points",
            fontsize=7.8,
            color=colour if name not in ("oracle", "random") else INK_2,
            ha="center",
        )
    johnson = incumbent.loc[incumbent["rule"].str.contains("140")]
    if not johnson.empty:
        row = johnson.iloc[0]
        ax.scatter([row["retention"] * 100], [row["rate_above_0.5"] * 100], s=42, color=ORANGE, zorder=5,
                   edgecolor=SURFACE, linewidth=1.5)
        ax.annotate(
            "published 20-week\nguideline, with\nimputation",
            xy=(row["retention"] * 100, row["rate_above_0.5"] * 100),
            xytext=(-8, -34) if journal_mode() else (26, -30),
            textcoords="offset points",
            fontsize=5.8 if journal_mode() else 7.4,
            color=ORANGE,
            ha="right" if journal_mode() else "left",
            arrowprops={"arrowstyle": "-", "color": ORANGE, "linewidth": 0.9, "shrinkA": 2, "shrinkB": 4},
        )
    ax.set_xlabel("station-years retained (%)")
    ax.set_title(title, loc="left", pad=8)
    ax.set_xlim(35, 100)


def figure2_frontier() -> None:
    development = pd.read_csv(STEP7_FRONTIER / "frontiers.csv")
    reserved = pd.read_csv(STEP10_CONFIRM / "frontiers.csv")
    inc_dev = pd.read_csv(STEP7_FRONTIER / "incumbent_operating_points.csv")
    inc_res = pd.read_csv(STEP10_CONFIRM / "incumbent_operating_points.csv")

    def _caption(letter: str, label: str, path, suffix: str) -> str:
        frame = pd.read_parquet(path, columns=["network_id"])
        return f"{letter}  {label} · {frame['network_id'].nunique()} networks, {len(frame):,} cases{suffix}"

    fig, axes = panel_grid(2, (9.6, 3.6), sharey=True)
    _frontier_panel(
        axes[0], development,
        _caption("a", "Development", STEP4_CEILING / "development_cases.parquet", ""),
        inc_dev,
    )
    _frontier_panel(
        axes[1], reserved,
        _caption("b", "Reserved", STEP10_CONFIRM / "reserved_cases.parquet", ", scored once"),
        inc_res,
    )
    axes[0].set_ylabel("retained years with error > 0.5 °C (%)")
    axes[0].set_ylim(-0.6, 16)
    fig.tight_layout(h_pad=1.8 if journal_mode() else 1.08)
    _save(fig, "fig2_frontier")


def figure3_calibration() -> None:
    coverage = pd.read_csv(STEP10_CONFIRM / "coverage.csv")
    coverage = coverage.loc[coverage["stratum"].ne("all") | coverage["level"].eq("marginal")]
    labels = (
        coverage["stratum"]
        .str.replace("donor_regime=", "donors: ", regex=False)
        .str.replace("longest_run=", "outage ", regex=False)
        .str.replace("peak_overlap=", "peak hidden ", regex=False)
        .str.replace("all", "marginal (all cases)", regex=False)
        .str.replace("(0, 30]", "1-30 d", regex=False)
        .str.replace("(30, 90]", "31-90 d", regex=False)
        .str.replace("(90, 180]", "91-180 d", regex=False)
        .str.replace("(180, 400]", "181+ d", regex=False)
        .str.replace("(-0.001, 0.001]", "none", regex=False)
        .str.replace("(0.001, 0.5]", "<half", regex=False)
        .str.replace("(0.5, 1.001]", "most or all", regex=False)
        .tolist()
    )
    values = coverage["coverage"].to_numpy() * 100
    widths = coverage["median_width_c"].to_numpy()

    cluster = json.loads((RESULTS_ROOT / "step18_cluster_conformal" / "summary.json").read_text())["variants"]
    fig, axes = panel_grid(3, (13.4, 3.7), width_ratios=[1.15, 0.7, 0.95])
    ax = axes[0]
    y = np.arange(len(values))
    ax.axvspan(85, 95, color="#eef4fd", zorder=0)
    ax.axvline(90, color=INK_2, linewidth=1.2, linestyle=(0, (4, 3)), zorder=1)
    colours = [ORANGE if label.startswith("marginal") else BLUE for label in labels]
    ax.scatter(values, y, s=46, color=colours, zorder=3, edgecolor=SURFACE, linewidth=1.2)
    for yi, value in zip(y, values):
        ax.text(value + 0.45, yi, f"{value:.1f}", va="center", fontsize=7.4, color=INK_2)
    ax.set_yticks(y, labels)
    ax.set_xlim(82, 98)
    ax.set_xlabel("empirical coverage of the nominal 90% interval (%)")
    ax.set_title("a  Stratum coverage holds" if journal_mode() else "a  Stratum coverage holds on unseen networks", loc="left", pad=8)
    ax.grid(axis="y", visible=False)
    ax.text(85.3, -0.9, "pre-declared conditional band", fontsize=7.2, color=INK_2, va="center")
    ax.text(90.25, len(values) - 0.75, "nominal 90%", fontsize=7.2, color=INK_2, va="center")
    ax.set_ylim(len(values) - 0.4, -1.3)

    ax = axes[1]
    ax.barh(y, widths, color=BLUE, height=0.6)
    ax.set_yticks(y, [""] * len(y))
    ax.set_xlabel("median interval width (°C)")
    ax.set_ylim(len(y) - 0.4, -1.3)
    ax.set_title("b  Width adapts to the case", loc="left", pad=8)
    ax.grid(axis="y", visible=False)
    for yi, width in zip(y, widths):
        ax.text(width + 0.04, yi, f"{width:.2f}", va="center", fontsize=7.4, color=INK_2)
    ax.set_xlim(0, max(widths) * 1.25)

    ax = axes[2]
    order = ["pooled", "cluster_0.5", "cluster_0.6", "cluster_0.7", "cluster_0.8", "cluster_0.9"]
    order = [name for name in order if name in cluster]
    width_values = [cluster[name]["median_interval_width_c"] for name in order]
    minima = [cluster[name]["per_network"]["min"] * 100 for name in order]
    below = [cluster[name]["per_network"]["share_below_0.85"] * 100 for name in order]
    ax.plot(width_values, minima, color=BLUE, marker="o", markersize=6, markeredgecolor=SURFACE, markeredgewidth=1.4)
    for x_value, y_value, name, share in zip(width_values, minima, order, below):
        if name in ("pooled", "cluster_0.7", "cluster_0.9"):
            ax.annotate(
                name.replace("cluster_", "cluster ").replace("pooled", "pooled"),
                xy=(x_value, y_value),
                xytext=(0, 9),
                textcoords="offset points",
                fontsize=7.4,
                color=INK_2,
                ha="center",
            )
            ax.annotate(
                f"{share:.0f}% of networks < 85",
                xy=(x_value, y_value),
                xytext=(0, -15),
                textcoords="offset points",
                fontsize=6.8,
                color=MUTED,
                ha="center",
            )
    ax.axhline(85, color=ORANGE, linewidth=1.2, linestyle=(0, (4, 3)))
    ax.set_xlabel("median interval width (°C)")
    ax.set_ylabel("worst per-network coverage (%)")
    ax.set_title("c  The price of site-level honesty", loc="left", pad=8)
    ax.set_ylim(72, 92)
    ax.set_xlim(min(width_values) - 0.04, max(width_values) + 0.09)

    fig.tight_layout(h_pad=1.8 if journal_mode() else 1.08)
    _save(fig, "fig3_calibration")


def figure4_consequence() -> None:
    per_year = pd.read_csv(STEP10_CONFIRM / "per_year_threshold.csv")
    controls = pd.read_csv(STEP5_MECHANISM / "donor_control_summary.csv")

    fig, axes = panel_grid(2, (9.6, 3.5), width_ratios=[1.1, 0.9])

    ax = axes[0]
    block = per_year.loc[per_year["threshold_c"].eq(20.0)].copy()
    order = ["observed_days_all", "reconstruct_all", "length_screened", "certificate_screened"]
    names = {
        "observed_days_all": "compute on\nobserved days",
        "reconstruct_all": "reconstruct,\nno screening",
        "length_screened": "length-rule\nscreening",
        "certificate_screened": "certificate\nscreening",
    }
    block = block.set_index("treatment").reindex(order).reset_index()
    x = np.arange(len(block))
    colours = [MUTED, MUTED, ORANGE, BLUE]
    ax.bar(x, block["false_negative_rate"] * 100, color=colours, width=0.58)
    for xi, value, retention in zip(x, block["false_negative_rate"] * 100, block["retention"]):
        ax.text(xi, value + 0.06, f"{value:.2f}%", ha="center", fontsize=8, color=INK)
        ax.text(xi, -0.28, f"keeps {retention:.0%}", ha="center", fontsize=7, color=MUTED)
    ax.set_xticks(x, [names[name] for name in block["treatment"]])
    ax.set_ylabel("missed 20 °C exceedances (%)")
    ax.set_title("a  Per-year judgement" if journal_mode() else "a  Per-year judgement, reserved networks", loc="left", pad=8)
    ax.grid(axis="x", visible=False)
    ax.set_ylim(-0.5, max(block["false_negative_rate"] * 100) * 1.25)

    ax = axes[1]
    order = ["all_donors", "strong_half", "weak_half", "anomaly_shuffled"]
    labels = {
        "all_donors": "all donors",
        "strong_half": "strong half",
        "weak_half": "weak half",
        "anomaly_shuffled": "anomalies\nshuffled",
    }
    block = controls.set_index("arm").reindex(order).reset_index()
    x = np.arange(len(block))
    colours = [MUTED, AQUA, ORANGE, INK_2]
    ax.bar(x, block["mean_abs_error_c"], color=colours, width=0.58)
    ax.errorbar(
        x,
        block["mean_abs_error_c"],
        yerr=[block["mean_abs_error_c"] - block["ci_low"], block["ci_high"] - block["mean_abs_error_c"]],
        fmt="none",
        ecolor=INK,
        elinewidth=1.1,
        capsize=3,
    )
    for xi, value, high in zip(x, block["mean_abs_error_c"], block["ci_high"]):
        ax.text(xi, high + 0.018, f"{value:.3f}", ha="center", fontsize=8, color=INK)
    ax.set_xticks(x, [labels[name] for name in block["arm"]])
    ax.set_ylabel("mean absolute metric error (°C)")
    ax.set_title("b  Donor quality, not donor count", loc="left", pad=8)
    ax.grid(axis="x", visible=False)
    ax.set_ylim(0, block["ci_high"].max() * 1.22)

    fig.tight_layout(h_pad=1.8 if journal_mode() else 1.08)
    _save(fig, "fig4_consequence")


def main() -> int:
    figure1_mechanism()
    figure2_frontier()
    figure3_calibration()
    figure4_consequence()
    captions = {
        "fig1_mechanism": "For warm-season extremes, outage length is a weak axis and peak-window overlap and donor quality govern the error; panel d shows the ordering reverses for the annual mean and the cold extreme.",
        "fig2_frontier": "Retention-error frontier against the incumbent fixed-length screening rule.",
        "fig3_calibration": "Conformal coverage on reserved networks, marginal and within pre-declared strata, and what site-level validity costs in interval width.",
        "fig4_consequence": "What changes for a per-year judgement, and the controlled donor experiments.",
    }
    (RESULTS_ROOT / "figure_captions.json").write_text(json.dumps(captions, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
