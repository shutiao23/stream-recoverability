#!/usr/bin/env python3
"""R2-06 -- Figures 4 and 5 after the attribution round (2026-10-20b).

Figures 1-3 and the schematics are unchanged and still come from
``scripts/335_wrr_figures_v2.py``.  This script replaces the two figures whose
claims the attribution round changed:

* Figure 4 (mechanism).  Panel (a) splits the error of the hottest 30-day mean
  into the hiding channel and the false-peak channel; (b) shows how much of the
  "misaligned minus aligned" contrast survives once the true hidden share is held
  fixed; (c) shows three interventions on the gap residuals; (d) adds the
  information back in layers for one learner and compares it with the rules.
* Figure 5 (decision).  Panel (b) is the unscreened failure rate of each real
  network, not the pooled rate; (c) sets the refusal of true hot years against
  the refusal of all records, the null a hot-year-blind rule would give; (d) shows
  the fitted score's gain over the peak-window rule with and without the
  engineered support feature.

Every value is read from a versioned artifact; the tables behind the panels are
written to ``results/.../r2_06_figures/``.

Run (after scripts 335 and 340-344):

    PYTHONPATH=src python3 scripts/345_wrr_figures_r2.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wrr_r2_common as C  # noqa: E402

F = C.load_script("wrr335", C.ROOT / "scripts" / "335_wrr_figures_v2.py")
plt = F.plt

OUT_TABLES = C.RUN / "r2_06_figures"
THREE = C.RUN / "r2_03_three_windows"
ABL = C.RUN / "r2_02_same_capacity_ablation"
HOT = C.RUN / "r2_04_hot_year_null"
NEED = C.RUN / "r2_05_screening_need"

RECON = ["doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge"]
SHORT = ["clim.", "smooth", "interp.", "donor", "air"]
HIDDEN = {"none": "0", "partial": "0–1", "all": "1"}
CHANNEL_COLOURS = {"hide": "#2166ac", "false": "#d6604d"}


def save(fig, name: str) -> None:
    F.save(fig, name)


def fig_mechanism() -> None:
    channels = pd.read_csv(THREE / "channels_by_hidden_class.csv")
    mis = pd.read_csv(THREE / "misalignment_within_strata.csv")
    inter = pd.read_csv(THREE / "residual_interventions.csv")
    ops = pd.read_csv(ABL / "ablation_operating_points.csv")
    rows = []
    fig, axes = plt.subplots(2, 2, figsize=(5.6, 4.7))
    fig.patch.set_facecolor(F.SURFACE)

    # (a) the two channels ---------------------------------------------------
    ax = axes[0, 0]
    F.style(ax)
    groups = [(r, k) for r in ("doy_climatology", "donor_ridge") for k in ("none", "partial", "all")]
    width = 0.27
    for i, (recon, klass) in enumerate(groups):
        row = channels[(channels.reconstructor == recon) & (channels.true_hidden_class == klass)].iloc[0]
        for j, (key, lo, hi, colour) in enumerate(
            (
                ("mean_hide_channel_C", "hide_lo", "hide_hi", CHANNEL_COLOURS["hide"]),
                ("mean_false_peak_channel_C", "false_lo", "false_hi", CHANNEL_COLOURS["false"]),
            )
        ):
            x = i + (j - 0.5) * width * 1.15
            ax.bar(x, row[key], width=width, color=colour, alpha=0.92)
            ax.plot([x, x], [row[lo], row[hi]], color=F.INK, linewidth=0.9)
        ax.plot(i, row["mean_abs_error_C"], marker="D", markersize=2.8, color=F.INK, zorder=4)
        rows.append(
            {
                "panel": "channels", "reconstructor": recon, "true_hidden_class": klass,
                "hide_channel_C": row.mean_hide_channel_C, "false_peak_channel_C": row.mean_false_peak_channel_C,
                "mean_abs_error_C": row.mean_abs_error_C, "n_cases": row.n_cases,
            }
        )
    ax.axhline(0, color=F.INK_2, linewidth=0.7)
    ax.set_xticks(
        range(len(groups)),
        [("clim." if r == "doy_climatology" else "donor") + "\n" + HIDDEN[k] for r, k in groups],
        fontsize=5.8,
    )
    ax.set_xlabel("reconstructor, and true hidden share of the peak window", fontsize=6.2)
    ax.set_ylabel("mean contribution (°C)")
    F.title(ax, "a", "hiding and false-peak channels")
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=CHANNEL_COLOURS["hide"]),
        plt.Rectangle((0, 0), 1, 1, color=CHANNEL_COLOURS["false"]),
        plt.Line2D([], [], marker="D", color=F.INK, linestyle="", markersize=3),
    ]
    ax.legend(handles, ["hiding", "false peak", "mean |error|"], frameon=False, fontsize=5.4,
              loc="upper left", ncol=3, columnspacing=0.8, handlelength=1.0)
    ax.set_ylim(-1.15, 1.25)

    # (b) misaligned - aligned, pooled vs within strata -----------------------
    ax = axes[0, 1]
    F.style(ax)
    xs = np.arange(len(RECON))
    for j, (stratum, colour, label) in enumerate(
        (("pooled", F.GREY, "pooled"), ("clim_class_x_true_class_weighted", F.PURPLE, "within strata"))
    ):
        vals, lows, highs = [], [], []
        for recon in RECON:
            row = mis[(mis.reconstructor == recon) & (mis.stratum == stratum)].iloc[0]
            vals.append(row.point_C)
            lows.append(row.point_C - row.lo_C)
            highs.append(row.hi_C - row.point_C)
            rows.append(
                {"panel": "misalignment_contrast", "reconstructor": recon, "stratum": stratum,
                 "point_C": row.point_C, "lo_C": row.lo_C, "hi_C": row.hi_C}
            )
        x = xs + (j - 0.5) * 0.36
        ax.bar(x, vals, width=0.33, color=colour, alpha=0.92, label=label)
        ax.errorbar(x, vals, yerr=[lows, highs], fmt="none", ecolor=F.INK, elinewidth=0.8, capsize=1.5)
    ax.set_xticks(xs, SHORT, fontsize=6.0)
    ax.set_ylabel("misaligned − aligned |error| (°C)")
    F.title(ax, "b", "most of the contrast is hidden share")
    ax.legend(frameon=False, fontsize=5.8, loc="upper right")

    # (c) interventions on the gap residuals ----------------------------------
    ax = axes[1, 0]
    F.style(ax)
    pooled = inter[inter.true_hidden_class == "pooled"].set_index("reconstructor")
    ys = np.arange(len(RECON))[::-1]
    spec = (
        ("permuted_minus_recorded", F.BLUE, "o", "residuals permuted"),
        ("mean_removed_minus_recorded", F.ORANGE, "s", "gap mean removed"),
        ("mean_only_minus_recorded", F.GREEN, "^", "gap mean only"),
    )
    for j, (key, colour, marker, label) in enumerate(spec):
        for y, recon in zip(ys, RECON):
            row = pooled.loc[recon]
            yy = y + (1 - j) * 0.2
            ax.errorbar(
                [row[f"{key}_C"]], [yy],
                xerr=[[row[f"{key}_C"] - row[f"{key}_lo"]], [row[f"{key}_hi"] - row[f"{key}_C"]]],
                fmt=marker, color=colour, markersize=2.8, capsize=1.2, elinewidth=0.8,
                label=label if y == ys[0] else None,
            )
            rows.append(
                {"panel": "interventions", "reconstructor": recon, "intervention": key,
                 "point_C": row[f"{key}_C"], "lo_C": row[f"{key}_lo"], "hi_C": row[f"{key}_hi"]}
            )
    ax.axvline(0, color=F.INK_2, linewidth=0.7, linestyle=(0, (3, 2)))
    ax.set_yticks(ys, SHORT, fontsize=6.0)
    ax.set_xlabel("change in mean |error| (°C)")
    ax.set_ylim(-1.15, 4.55)
    F.title(ax, "c", "persistence matters; the gap mean matters more")
    ax.legend(frameon=False, fontsize=5.4, loc="lower center", ncol=3, handletextpad=0.3,
              columnspacing=0.8)

    # (d) the information ladder ----------------------------------------------
    ax = axes[1, 1]
    F.style(ax, grid_axis="x")
    ladder = [
        ("length_rule", "gap-length rule", F.ORANGE, None),
        ("peak_overlap_rule", "peak-window rule", F.BLUE, None),
        ("gap_season", "model: gap and season", F.GREY, None),
        ("gap_season+donors", "+ donor information", F.GREY, None),
        ("gap_season+donors+residual", "+ reconstruction diagnostics", F.GREY, None),
        ("generic", "all generic, no support", F.PURPLE, None),
        ("generic+support", "+ peak-window share", F.PURPLE, "///"),
    ]
    risk = ops[ops.row_type == "riskcap"]
    ypos = np.arange(len(ladder))[::-1]
    for y, (spec_name, label, colour, hatch) in zip(ypos, ladder):
        ext = risk[(risk.panel == "wave2_confirmation") & (risk.score == spec_name)].retention.to_numpy() * 100
        dev = risk[(risk.panel == "development") & (risk.score == spec_name)].retention.to_numpy() * 100
        ax.barh(y, ext.mean(), height=0.62, color=colour, alpha=0.9, hatch=hatch, edgecolor=F.SURFACE, linewidth=0.4)
        ax.plot([ext.min(), ext.max()], [y, y], color=F.INK, linewidth=1.1)
        ax.plot(dev.mean(), y, marker="o", markersize=3.0, markerfacecolor=F.SURFACE, markeredgecolor=F.INK, zorder=4)
        rows.append(
            {"panel": "ladder", "score": spec_name, "external_mean_pct": ext.mean(), "external_min_pct": ext.min(),
             "external_max_pct": ext.max(), "development_mean_pct": dev.mean()}
        )
    ax.set_yticks(ypos, [item[1] for item in ladder], fontsize=5.6)
    ax.set_xlabel("retention at the 5% cap (%)")
    ax.set_xlim(0, 88)
    F.title(ax, "d", "what each layer of information adds")
    ax.text(0.99, 0.99, "bars: external, mean of 3 seeds\ncircles: development", transform=ax.transAxes,
            ha="right", va="top", fontsize=5.2, color=F.INK_2)

    fig.tight_layout()
    save(fig, "f4_mechanism")
    pd.DataFrame(rows).to_csv(OUT_TABLES / "fig4_source.csv", index=False)


def fig_decision() -> None:
    pooled = pd.read_csv(F.ALIGNED / "crossfit_table.csv")
    replay = pd.read_csv(F.REPLAY / "replay_admission.csv")
    hot = pd.read_csv(HOT / "hot_year_selection_null.csv")
    net = pd.read_csv(NEED / "real_calendar_by_network.csv")
    abl_contrasts = pd.read_csv(ABL / "ablation_contrasts.csv")
    rows = []
    fig, axes = plt.subplots(2, 2, figsize=(5.6, 4.9))
    fig.patch.set_facecolor(F.SURFACE)

    # (a) retention at the cap (unchanged content, plus the no-support model) --
    ax = axes[0, 0]
    F.style(ax)
    ops = pd.read_csv(ABL / "ablation_operating_points.csv")
    risk = ops[ops.row_type == "riskcap"]
    order = [
        ("peak_overlap_rule", "peak-window rule", F.BLUE),
        ("generic+support", "fitted risk score", F.PURPLE),
        ("generic", "same model, no support", F.GREY),
        ("calibrated_bound", "certificate bound", "#a8a8a4"),
        ("length_rule", "gap-length rule", F.ORANGE),
    ]
    width = 0.36
    for pi, (panel, hatch) in enumerate((("wave2_confirmation", None), ("development", "///"))):
        for ai, (name, _, colour) in enumerate(order):
            vals = risk[(risk.panel == panel) & (risk.score == name)].retention.to_numpy() * 100
            x = ai + (pi - 0.5) * width
            ax.bar(x, vals.mean(), width=width * 0.92, color=colour, alpha=0.9, hatch=hatch,
                   edgecolor=F.SURFACE, linewidth=0.4)
            ax.plot([x, x], [vals.min(), vals.max()], color=F.INK, linewidth=1.1)
            rows.append({"panel": "retention_at_cap", "panel_name": panel, "arm": name,
                         "mean": vals.mean(), "min": vals.min(), "max": vals.max()})
    ax.set_xticks(range(len(order)), [o[1] for o in order], rotation=24, ha="right", fontsize=5.8)
    ax.set_ylabel("retention at the 5% cap (%)")
    ax.set_ylim(0, 100)
    F.title(ax, "a", "what each rule keeps")
    ax.text(0.99, 0.98, "solid: external\nhatched: development", transform=ax.transAxes, fontsize=5.2,
            color=F.INK_2, va="top", ha="right")

    # (b) the real networks, one by one ---------------------------------------
    ax = axes[0, 1]
    F.style(ax, grid_axis="x")
    t = net[net.level == "target_only"].sort_values("observed_unscreened_failure").reset_index(drop=True)
    ys = np.arange(len(t))
    ax.scatter(t.observed_unscreened_failure * 100, ys, s=12, color=F.PURPLE, zorder=3, label="observed")
    ax.scatter(t.predicted_unscreened_failure * 100, ys, s=12, facecolor=F.SURFACE, edgecolor=F.INK,
               linewidth=0.7, zorder=3, label="predicted from gap calendar")
    for y, row in zip(ys, t.itertuples(index=False)):
        rows.append({"panel": "real_networks", "network": row.network_id,
                     "n_groups": row.n_groups, "n_target_station_years": row.n_target_station_years,
                     "observed_pct": row.observed_unscreened_failure * 100,
                     "predicted_pct": row.predicted_unscreened_failure * 100})
    ax.axvline(5, color=F.RED, linewidth=0.9, linestyle=(0, (4, 3)))
    ax.set_yticks(ys, [f"{r.network_id.replace('usgs2_', '').replace('gkd_bayern_', '')} ({r.n_target_station_years})"
                       for r in t.itertuples(index=False)], fontsize=4.9)
    ax.set_xlabel("failure rate of the unscreened reconstruction (%)")
    F.title(ax, "b", "most networks need no screen")
    ax.legend(frameon=False, fontsize=5.2, loc="center right", bbox_to_anchor=(1.0, 0.38))

    # (c) hot years: refusal vs the hot-year-blind null ------------------------
    ax = axes[1, 0]
    F.style(ax)
    block = hot[(hot.panel == "wave2_confirmation") & (hot.hot_c == 20.0)]
    arms = [("peak_overlap_rule", "peak-window rule", F.BLUE), ("generic+support", None, None)]
    arms = [
        ("peak_overlap_rule", "peak-window rule", F.BLUE),
        ("fitted_risk", "fitted risk score", F.PURPLE),
        ("calibrated_bound", "certificate bound", "#a8a8a4"),
        ("length_rule", "gap-length rule", F.ORANGE),
    ]
    width = 0.38
    for ai, (name, label, colour) in enumerate(arms):
        sub = block[block.arm == name]
        hot_ref = sub.refused_hot_share.to_numpy() * 100
        all_ref = (1 - sub.retention.to_numpy()) * 100
        ax.bar(ai - width / 2, hot_ref.mean(), width=width * 0.92, color=colour, alpha=0.92,
               edgecolor=F.SURFACE, linewidth=0.4)
        ax.bar(ai + width / 2, all_ref.mean(), width=width * 0.92, color="none", edgecolor=colour,
               linewidth=1.0, hatch="////")
        ax.plot([ai - width / 2] * 2, [hot_ref.min(), hot_ref.max()], color=F.INK, linewidth=1.0)
        rows.append({"panel": "hot_year_null", "arm": name, "hot_refused_pct": hot_ref.mean(),
                     "all_refused_pct": all_ref.mean(),
                     "excess_pp": float(sub.excess_hot_refusal.mean() * 100),
                     "excess_ci_low_pp_seed101": float(sub[sub.fold_seed == 101].excess_ci_low.iloc[0] * 100),
                     "excess_ci_high_pp_seed101": float(sub[sub.fold_seed == 101].excess_ci_high.iloc[0] * 100)})
    ax.set_xticks(range(len(arms)), [a[1] for a in arms], rotation=24, ha="right", fontsize=5.8)
    ax.set_ylabel("refused (%)")
    ax.set_ylim(0, 72)
    F.title(ax, "c", "hot years are refused like all records")
    ax.text(0.02, 0.97, "solid: true hot years\nhatched: all records", transform=ax.transAxes, fontsize=5.4,
            color=F.INK_2, va="top")

    # (d) the gain, with and without the support feature -----------------------
    ax = axes[1, 1]
    F.style(ax)
    spec = (("generic+support", F.PURPLE, "o", "fitted score (reads support)"),
            ("generic", F.GREY, "s", "same model, no support feature"))
    ys, labels = [], []
    for pi, panel in enumerate(("wave2_confirmation", "development")):
        for si, seed in enumerate((101, 202, 303)):
            y = pi * 5 + si
            ys.append(y)
            labels.append(f"{'external' if pi == 0 else 'development'} {seed}")
            for k, (name, colour, marker, label) in enumerate(spec):
                r = abl_contrasts[
                    (abl_contrasts.metric == "retention") & (abl_contrasts.panel == panel)
                    & (abl_contrasts.fold_seed == seed) & (abl_contrasts.left == name)
                    & (abl_contrasts.right == "peak_overlap_rule")
                ].iloc[0]
                yy = y + (k - 0.5) * 0.3
                ax.errorbar([r.point * 100], [yy], xerr=[[r.point * 100 - r.ci_low * 100], [r.ci_high * 100 - r.point * 100]],
                            fmt=marker, color=colour, markersize=3.0, capsize=1.5, elinewidth=0.8,
                            label=label if (pi == 0 and si == 0) else None)
                rows.append({"panel": "gain_over_peak_rule", "panel_name": panel, "fold_seed": seed, "score": name,
                             "point_pp": r.point * 100, "ci_low_pp": r.ci_low * 100, "ci_high_pp": r.ci_high * 100})
    ax.axvline(0, color=F.INK_2, linewidth=0.8)
    ax.axvline(5, color=F.RED, linewidth=0.9, linestyle=(0, (4, 3)))
    ax.set_yticks(ys, labels, fontsize=5.6)
    ax.set_xlabel("retention minus the peak-window rule (points)")
    F.title(ax, "d", "the gain does not need the support feature")
    ax.set_xlim(-2, 17)
    ax.set_ylim(-0.8, 7.8)
    ax.invert_yaxis()
    ax.legend(frameon=False, fontsize=5.2, loc="center right", bbox_to_anchor=(1.0, 0.5))

    fig.tight_layout()
    save(fig, "f5_decision")
    pd.DataFrame(rows).to_csv(OUT_TABLES / "fig5_source.csv", index=False)


def main() -> None:
    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    fig_mechanism()
    fig_decision()
    print("wrote figures 4 and 5 and their source tables ->", OUT_TABLES)


if __name__ == "__main__":
    main()
