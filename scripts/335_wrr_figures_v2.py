#!/usr/bin/env python3
"""Main figures for the 2026-10-20 rewrite.

Four figures, each answering one question and each raising the next:

1. What governs the error, and does the answer depend on which statistic is
   computed?  (support versus completeness; the reversal across endpoints)
2. How much of that is the reconstructor's doing?  (crossed design, five
   reconstructors)
3. What is the proximate mechanism, and what does support alone miss?
   (window misalignment, residual persistence, competing peaks, and the
   within-support separation a fitted score achieves)
4. What does it change for a decision?  (retention at a 5% cap, fixed-70%
   risk, the real-calendar replay, and the hot-year composition)

Every value is read from a versioned artifact; the tables behind the panels are
written next to the figures so the caption can be checked against them.

Run:

    PYTHONPATH=src python3 scripts/335_wrr_figures_v2.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results" / "wrr_submission_ready" / "major_revision_20261020"
ALIGNED = RUN / "p0_01_aligned_policy_admission"
REPLAY = RUN / "p0_03_real_calendar_adoption"
HOT = RUN / "p0_04_hot_year_closure"
MECH = ROOT / "results" / "wrr_submission_ready" / "major_revision_20261014" / "p1_mechanism_boundary"
WAVE2 = ROOT / "results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/wave2_cases.parquet"
REPLAY_RAW = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "major_revision_20261014"
    / "p0_03_final_method_replay"
    / "replay_decisions.parquet"
)
OUT_DIRS = [ROOT / "figures" / "wrr", ROOT / "paper" / "wrr" / "figures"]
TABLE_DIR = RUN / "p0_06_figures"

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#111111", "#52514e", "#dedcd6"
BLUE, ORANGE, PURPLE, GREY, RED, GREEN = (
    "#2166ac",
    "#d6604d",
    "#6b4fa0",
    "#8a8a86",
    "#b2182b",
    "#1b7837",
)
CLASS_COLOURS = {"none": "#4d4d4d", "partial": "#e08214", "full": "#2166ac"}
CLASS_LABELS = {
    "none": "peak observed (share = 0)",
    "partial": "peak partly hidden (0 < share < 1)",
    "full": "peak fully hidden (share = 1)",
}
METHOD_COLOURS = {
    "doy_climatology": "#762a83",
    "smooth_climatology": "#1b7837",
    "linear_interp": "#e08214",
    "donor_ridge": "#2166ac",
    "air_ridge": "#b2182b",
}
METHOD_LABELS = {
    "doy_climatology": "day-of-year climatology",
    "smooth_climatology": "smoothed climatology",
    "linear_interp": "linear interpolation",
    "donor_ridge": "donor regression",
    "air_ridge": "air-temperature regression",
}
ARM_LABELS = {
    "fitted_risk": "fitted risk score",
    "calibrated_bound": "certificate bound",
    "peak_overlap_rule": "peak-window rule",
    "length_rule": "gap-length rule",
    "reconstruct_all": "reconstruct everything",
}
ARM_ORDER = ("reconstruct_all", "peak_overlap_rule", "fitted_risk", "calibrated_bound", "length_rule")
ARM_COLOURS = {
    "reconstruct_all": "#4d4d4d",
    "peak_overlap_rule": BLUE,
    "fitted_risk": PURPLE,
    "calibrated_bound": GREY,
    "length_rule": ORANGE,
}

plt.rcParams.update(
    {
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "font.family": "serif",
        "font.serif": ["DejaVu Serif"],
        "font.size": 7.2,
        "axes.labelsize": 7.2,
        "axes.titlesize": 7.8,
        "xtick.labelsize": 6.6,
        "ytick.labelsize": 6.6,
        "legend.fontsize": 6.4,
        "savefig.facecolor": SURFACE,
        "axes.unicode_minus": False,
    }
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def style(ax, *, grid_axis="y"):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.grid(color=GRID, linewidth=0.55, axis=grid_axis)
    ax.set_axisbelow(True)


def title(ax, letter, text):
    ax.set_title(f"{letter}  {text}", loc="left", fontsize=7.8, color=INK, pad=4)


def cluster_mean_ci(
    values: np.ndarray,
    groups: np.ndarray,
    *,
    draws: int = 2000,
    seed: int = 0,
) -> tuple[float, float, float]:
    values = np.asarray(values, dtype=float)
    finite = np.isfinite(values)
    if finite.sum() == 0:
        return float("nan"), float("nan"), float("nan")
    point = float(values[finite].mean())
    units, codes = np.unique(np.asarray(groups)[finite], return_inverse=True)
    n_units = units.size
    per_unit_sum = np.bincount(codes, weights=values[finite], minlength=n_units)
    per_unit_n = np.bincount(codes, minlength=n_units).astype(float)
    rng = np.random.default_rng(seed)
    draws_values = np.empty(int(draws))
    for index in range(int(draws)):
        take = rng.integers(0, n_units, size=n_units)
        draws_values[index] = per_unit_sum[take].sum() / max(per_unit_n[take].sum(), 1e-12)
    return point, float(np.quantile(draws_values, 0.025)), float(np.quantile(draws_values, 0.975))


def save(fig, name: str):
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    for directory in OUT_DIRS:
        directory.mkdir(parents=True, exist_ok=True)
        fig.savefig(directory / f"{name}.pdf", bbox_inches="tight", facecolor=SURFACE)
        fig.savefig(directory / f"{name}.png", dpi=400, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
def designed_frame() -> pd.DataFrame:
    cases = pd.read_parquet(WAVE2).reset_index(drop=True)
    adm = pd.read_parquet(ALIGNED / "case_level_admissions_wave2_confirmation.parquet")
    adm = adm[adm.fold_seed.eq(101)].reset_index(drop=True)
    if not cases["network_id"].astype(str).equals(adm["network_id"].astype(str)):
        raise RuntimeError("wave-2 cases and admissions are not row-aligned")
    keep = [
        "independence_group",
        "longest_run",
        "peak_overlap",
        "true_peak_hidden_fraction",
        "policy_bad",
        "admit_riskcap_fitted_risk",
        "policy_choice",
        "n_visible_donors",
    ]
    for column in keep:
        cases[column] = adm[column].to_numpy()
    return cases


def fig1() -> None:
    cases = designed_frame()
    groups = cases["independence_group"].astype(str).to_numpy()
    run = pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy(dtype=float)
    share = pd.to_numeric(cases["true_peak_hidden_fraction"], errors="coerce").to_numpy(dtype=float)
    cls = np.where(share >= 0.999, "full", np.where(share <= 0.001, "none", "partial"))

    length_bins = [(0, 7), (7, 14), (14, 30), (30, 60), (60, 90), (90, 180), (180, 400)]
    length_labels = ["1–7", "8–14", "15–30", "31–60", "61–90", "91–180", "181+"]

    fig, axes = plt.subplots(2, 2, figsize=(5.6, 4.5))
    fig.patch.set_facecolor(SURFACE)

    rows = []
    for ax, endpoint, letter, panel_title in (
        (axes[0, 0], "hottest30", "a", "hottest 30-day mean"),
        (axes[0, 1], "annual_mean", "b", "annual mean"),
    ):
        style(ax)
        error = pd.to_numeric(
            cases[f"abserr_{endpoint}_doy_climatology"], errors="coerce"
        ).to_numpy(dtype=float)
        for klass in ("none", "partial", "full"):
            xs, ys, los, his = [], [], [], []
            for index, (low, high) in enumerate(length_bins):
                mask = (cls == klass) & (run > low) & (run <= high)
                if mask.sum() < 25:
                    continue
                point, lo, hi = cluster_mean_ci(
                    error[mask],
                    groups[mask],
                    seed=11 + index + (0 if klass == "none" else 100 if klass == "partial" else 200),
                )
                xs.append(index)
                ys.append(point)
                los.append(point - lo)
                his.append(hi - point)
                rows.append(
                    {
                        "figure": "fig1",
                        "endpoint": endpoint,
                        "overlap_class": klass,
                        "length_bin": length_labels[index],
                        "n_cases": int(mask.sum()),
                        "mean_abs_error_c": point,
                        "ci_low_c": lo,
                        "ci_high_c": hi,
                    }
                )
            ax.errorbar(
                xs,
                ys,
                yerr=[los, his],
                color=CLASS_COLOURS[klass],
                marker="o",
                markersize=3.4,
                linewidth=1.2,
                capsize=1.6,
                elinewidth=0.8,
                label=CLASS_LABELS[klass],
            )
        ax.set_xticks(range(len(length_labels)), length_labels, rotation=0)
        ax.set_xlabel("longest consecutive gap (days)")
        ax.set_ylabel("mean absolute error (°C)")
        title(ax, letter, panel_title)
        ax.set_ylim(bottom=0)

    axes[0, 1].legend(frameon=False, loc="upper left", handlelength=1.6, fontsize=6.0)

    # (c) the reversal across endpoints
    ax = axes[1, 0]
    style(ax)
    endpoints = [
        ("hottest7", "hottest 7-day"),
        ("hottest30", "hottest 30-day"),
        ("amplitude30", "seasonal amplitude"),
        ("annual_mean", "annual mean"),
        ("coldest30", "coldest 30-day"),
    ]
    width = 0.26
    for offset, klass in zip((-width, 0.0, width), ("none", "partial", "full")):
        values, lows, highs = [], [], []
        for endpoint, _label in endpoints:
            error = pd.to_numeric(
                cases[f"abserr_{endpoint}_doy_climatology"], errors="coerce"
            ).to_numpy(dtype=float)
            mask = cls == klass
            point, lo, hi = cluster_mean_ci(
                error[mask],
                groups[mask],
                seed=31 + (0 if klass == "none" else 10 if klass == "partial" else 20),
            )
            values.append(point)
            lows.append(point - lo)
            highs.append(hi - point)
        positions = np.arange(len(endpoints)) + offset
        ax.bar(positions, values, width=width * 0.92, color=CLASS_COLOURS[klass], alpha=0.92,
               edgecolor=SURFACE, linewidth=0.4, label=CLASS_LABELS[klass])
        ax.errorbar(positions, values, yerr=[lows, highs], fmt="none", ecolor=INK,
                    elinewidth=0.8, capsize=1.4)
        for endpoint_index, (endpoint_key, _endpoint_label) in enumerate(endpoints):
            rows.append(
                {
                    "figure": "fig1",
                    "endpoint": endpoint_key,
                    "overlap_class": klass,
                    "length_bin": "all",
                    "n_cases": int((cls == klass).sum()),
                    "mean_abs_error_c": values[endpoint_index],
                    "ci_low_c": values[endpoint_index] - lows[endpoint_index],
                    "ci_high_c": values[endpoint_index] + highs[endpoint_index],
                }
            )
    ax.set_xticks(range(len(endpoints)), [label for _key, label in endpoints], rotation=18, ha="right")
    ax.set_ylabel("mean absolute error (°C)")
    title(ax, "c", "the same gap, opposite consequences")
    ax.legend(frameon=False, loc="upper right", handlelength=1.4, ncol=1, fontsize=5.4)

    # (d) the two gap regimes
    ax = axes[1, 1]
    style(ax)
    replay = pd.read_parquet(REPLAY_RAW)
    # Use the observable overlap with the climatological peak window in both
    # panels: the real calendars have no truth-side window to compare against,
    # and mixing the two definitions would make the regimes incomparable.
    designed_share = pd.to_numeric(cases["peak_overlap"], errors="coerce").to_numpy(dtype=float)
    designed_share = designed_share[np.isfinite(designed_share)]
    real_share = pd.to_numeric(replay["peak_overlap"], errors="coerce").to_numpy(dtype=float)
    real_share = real_share[np.isfinite(real_share)]
    bins = np.linspace(0, 1, 21)
    for values, colour, label in (
        (designed_share, PURPLE, f"designed outages (n={designed_share.size:,})"),
        (real_share, GREEN, f"real calendars (n={real_share.size:,})"),
    ):
        histogram, edges = np.histogram(values, bins=bins, density=False)
        histogram = 100.0 * histogram / max(values.size, 1)
        centres = 0.5 * (edges[:-1] + edges[1:])
        ax.step(centres, histogram, where="mid", color=colour, linewidth=1.4, label=label)
        ax.fill_between(centres, 0, histogram, step="mid", color=colour, alpha=0.16)
        rows.append(
            {
                "figure": "fig1",
                "endpoint": "distribution",
                "overlap_class": label,
                "length_bin": "all",
                "n_cases": int(values.size),
                "mean_abs_error_c": float(np.mean(values)),
                "ci_low_c": float(np.median(values)),
                "ci_high_c": float(np.quantile(values, 0.9)),
            }
        )
    ax.set_xlabel("share of the climatological peak window hidden")
    ax.set_ylabel("share of cases (%)")
    title(ax, "d", "designed gaps are not real gaps")
    ax.legend(frameon=False, loc="upper right")

    fig.tight_layout()
    save(fig, "f1_support")
    pd.DataFrame(rows).drop_duplicates().to_csv(TABLE_DIR / "fig1_source.csv", index=False)


def fig2() -> None:
    crossed = pd.read_csv(MECH / "crossed_effects.csv")
    fig = plt.figure(figsize=(5.6, 4.4))
    grid = fig.add_gridspec(2, 2, height_ratios=[1.0, 0.85], hspace=0.55, wspace=0.32)
    ax_a = fig.add_subplot(grid[0, 0])
    ax_b = fig.add_subplot(grid[0, 1])
    ax_c = fig.add_subplot(grid[1, :])
    fig.patch.set_facecolor(SURFACE)
    rows = []
    reconstructors = ["doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge"]

    # (a) position effect at fixed length
    style(ax_a)
    table = crossed[
        crossed.design.eq("position_x_length")
        & crossed.contrast.eq("full_minus_none_at_fixed_length")
        & crossed.design_detail.isna()
    ]
    for index, reconstructor in enumerate(reconstructors):
        block = table[table.reconstructor.eq(reconstructor)].copy()
        block["length_days"] = block["level"].str.replace("length=", "", regex=False).astype(float)
        block = block.sort_values("length_days")
        xs = np.arange(len(block)) + (index - 2.0) * 0.11
        ax_a.errorbar(
            xs,
            block["point_C"],
            yerr=[block["point_C"] - block["ci_low_C"], block["ci_high_C"] - block["point_C"]],
            fmt="o",
            color=METHOD_COLOURS[reconstructor],
            markersize=2.6,
            capsize=1.0,
            elinewidth=0.7,
        )
        for row in block.itertuples(index=False):
            rows.append(
                {
                    "figure": "fig3",
                    "panel": "position_effect",
                    "reconstructor": reconstructor,
                    "length": row.length_days,
                    "point_c": row.point_C,
                    "ci_low_c": row.ci_low_C,
                    "ci_high_c": row.ci_high_C,
                    "n_cases": row.n_cases,
                }
            )
    ax_a.set_xticks(np.arange(3), ["30", "60", "90"])
    ax_a.set_xlabel("gap length (days)")
    ax_a.set_ylabel("hides peak − leaves peak (°C)")
    title(ax_a, "a", "position always costs")

    # (b) length effect at fixed hidden share
    style(ax_b)
    table = crossed[
        crossed.contrast.eq("long_minus_short_at_fixed_hidden_share")
        & crossed.level.eq("true_peak_hidden_fraction>=0.999")
        & crossed.design_detail.isna()
    ]
    ys = np.arange(len(reconstructors))[::-1]
    for y, reconstructor in zip(ys, reconstructors):
        row = table[table.reconstructor.eq(reconstructor)]
        if row.empty:
            continue
        row = row.iloc[0]
        ax_b.errorbar(
            [row.point_C],
            [y],
            xerr=[[row.point_C - row.ci_low_C], [row.ci_high_C - row.point_C]],
            fmt="o",
            color=METHOD_COLOURS[reconstructor],
            markersize=2.8,
            capsize=1.3,
            elinewidth=0.8,
        )
        rows.append(
            {
                "figure": "fig3",
                "panel": "length_effect_at_full_support",
                "reconstructor": reconstructor,
                "length": "90 minus 30",
                "point_c": row.point_C,
                "ci_low_c": row.ci_low_C,
                "ci_high_c": row.ci_high_C,
                "n_cases": row.n_cases,
            }
        )
    ax_b.axvline(0, color=INK_2, linewidth=0.7, linestyle=(0, (3, 2)))
    ax_b.set_xlim(-0.3, 1.65)
    ax_b.set_yticks(ys, ["clim.", "smooth", "interp.", "donor", "air"], fontsize=6.0)
    ax_b.set_xlabel("90 − 30 d at full support (°C)")
    title(ax_b, "b", "length sometimes matters")

    # (c) the curve across hidden share, wave-2 panel
    style(ax_c)
    cases = designed_frame()
    groups = cases["independence_group"].astype(str).to_numpy()
    share = pd.to_numeric(cases["true_peak_hidden_fraction"], errors="coerce").to_numpy(dtype=float)
    share_bins = [(0.0, 0.001), (0.001, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 0.999), (0.999, 1.01)]
    share_labels = ["0", "0–.25", ".25–.5", ".5–.75", ".75–1", "1"]
    for reconstructor in reconstructors:
        xs, ys_values = [], []
        for index, (low, high) in enumerate(share_bins):
            mask = (share > low) & (share <= high)
            if mask.sum() < 40:
                continue
            error = pd.to_numeric(
                cases[f"abserr_hottest30_{reconstructor}"], errors="coerce"
            ).to_numpy(dtype=float)
            point, lo, hi = cluster_mean_ci(error[mask], groups[mask], seed=71 + index)
            xs.append(index)
            ys_values.append(point)
            rows.append(
                {
                    "figure": "fig3",
                    "panel": "hidden_share_curve",
                    "reconstructor": reconstructor,
                    "length": share_labels[index],
                    "point_c": point,
                    "ci_low_c": lo,
                    "ci_high_c": hi,
                    "n_cases": int(mask.sum()),
                }
            )
        ax_c.plot(xs, ys_values, marker="o", markersize=2.6, linewidth=1.1,
                  color=METHOD_COLOURS[reconstructor], label=METHOD_LABELS[reconstructor])
    ax_c.set_xticks(range(len(share_labels)), share_labels)
    ax_c.set_xlabel("hidden share of the peak window")
    ax_c.set_ylabel("error (°C, log scale)")
    ax_c.set_yscale("log")
    ax_c.set_ylim(0.06, 7.0)
    title(ax_c, "c", "one axis, five heights")
    ax_c.legend(frameon=False, fontsize=5.4, handlelength=1.2, ncol=3, loc="upper left",
                columnspacing=0.8, labelspacing=0.2)

    save(fig, "f3_reconstructor")
    pd.DataFrame(rows).to_csv(TABLE_DIR / "fig3_source.csv", index=False)


def fig3() -> None:
    fig, axes = plt.subplots(2, 2, figsize=(5.6, 4.5))
    fig.patch.set_facecolor(SURFACE)
    rows = []
    reconstructors = ["doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge"]

    misalignment = pd.read_csv(MECH / "misalignment_table.csv")
    shares_table = pd.read_csv(MECH / "competing_peak.csv")
    shares_table = shares_table[shares_table.block.eq("misalignment_share_all")]
    contrast = misalignment[misalignment.block.eq("condition_contrast")]
    contrast = contrast[contrast.contrast.eq("misaligned_minus_aligned")]

    # (a) misalignment: error when the reconstructed window lands elsewhere
    ax = axes[0, 0]
    style(ax)
    xs = np.arange(len(reconstructors))
    values, lows, highs, shares = [], [], [], []
    for reconstructor in reconstructors:
        row = contrast[contrast.reconstructor.eq(reconstructor)].iloc[0]
        values.append(row.point_C)
        lows.append(row.point_C - row.ci_low_C)
        highs.append(row.ci_high_C - row.point_C)
        share_row = shares_table[shares_table.reconstructor.eq(reconstructor)].iloc[0]
        shares.append(share_row.share_misaligned)
        rows.append(
            {
                "figure": "fig4",
                "panel": "misaligned_minus_aligned",
                "variable": reconstructor,
                "point_c": row.point_C,
                "ci_low_c": row.ci_low_C,
                "ci_high_c": row.ci_high_C,
                "share_misaligned": share_row.share_misaligned,
            }
        )
    ax.bar(xs, values, color=[METHOD_COLOURS[r] for r in reconstructors], width=0.62, alpha=0.92)
    ax.errorbar(xs, values, yerr=[lows, highs], fmt="none", ecolor=INK, elinewidth=0.8, capsize=1.6)
    for x, value, share in zip(xs, values, shares):
        ax.text(x, value + max(highs) * 0.15, f"{share * 100:.0f}%", ha="center", fontsize=5.8, color=INK_2)
    ax.set_xticks(xs, ["clim.", "smooth", "interp.", "donor", "air"], rotation=0)
    ax.set_ylabel("misaligned − aligned error (°C)")
    title(ax, "a", "the window lands elsewhere")
    ax.text(0.01, 0.98, "labels: share of cases misaligned", transform=ax.transAxes,
            fontsize=5.8, color=INK_2, va="top")

    # (b) residual persistence: median split
    ax = axes[0, 1]
    style(ax)
    residual = pd.read_csv(MECH / "residual_correlation.csv")
    residual = residual[
        residual.block.eq("condition_contrast")
        & residual.contrast.eq("inside_gap_AC_above_reconstructor_median_minus_below")
    ]
    ys_local = np.arange(len(reconstructors))[::-1]
    for y, reconstructor in zip(ys_local, reconstructors):
        row = residual[residual.reconstructor.eq(reconstructor)]
        if row.empty:
            continue
        row = row.iloc[0]
        ax.errorbar(
            [row.point_C],
            [y],
            xerr=[[row.point_C - row.ci_low_C], [row.ci_high_C - row.point_C]],
            fmt="o",
            color=METHOD_COLOURS[reconstructor],
            markersize=2.8,
            capsize=1.3,
            elinewidth=0.8,
        )
        rows.append(
            {
                "figure": "fig4",
                "panel": "residual_ac_contrast",
                "variable": reconstructor,
                "bin": "above minus below median",
                "point_c": row.point_C,
                "ci_low_c": row.ci_low_C,
                "ci_high_c": row.ci_high_C,
                "n_cases": np.nan,
            }
        )
    ax.axvline(0, color=INK_2, linewidth=0.7, linestyle=(0, (3, 2)))
    ax.set_yticks(ys_local, ["clim.", "smooth", "interp.", "donor", "air"], fontsize=6.0)
    ax.set_xlabel("error above − below median AC (°C)")
    title(ax, "b", "persistent residuals cost more")

    # (c) competing peak: a negative control
    ax = axes[1, 0]
    style(ax)
    competing = pd.read_csv(MECH / "competing_peak.csv")
    competing = competing[
        competing.block.eq("error_by_bin") & competing.bin_variable.eq("competing_peak_gap_C")
    ]
    labels = ["[0,0.25)", "[0.25,0.5)", "[0.5,1)", "[1,2)", ">=2"]
    for reconstructor in reconstructors:
        block = competing[competing.reconstructor.eq(reconstructor)]
        if block.empty:
            continue
        xs = np.arange(len(labels))
        ax.plot(xs, block["point_C"], marker="o", markersize=2.6, linewidth=1.1,
                color=METHOD_COLOURS[reconstructor])
        for x, row in zip(xs, block.itertuples(index=False)):
            rows.append(
                {
                    "figure": "fig4",
                    "panel": "competing_peak",
                    "variable": reconstructor,
                    "bin": row.bin,
                    "point_c": row.point_C,
                    "ci_low_c": row.ci_low_C,
                    "ci_high_c": row.ci_high_C,
                    "n_cases": row.n_cases,
                }
            )
    ax.set_xticks(range(len(labels)), labels, fontsize=5.8)
    ax.set_xlabel("truth gap to the best disjoint window (°C)")
    ax.set_ylabel("mean absolute error (°C)")
    title(ax, "c", "a competing peak does not order the error")

    # (d) within-support separation
    ax = axes[1, 1]
    style(ax)
    cases = designed_frame()
    share = pd.to_numeric(cases["true_peak_hidden_fraction"], errors="coerce").to_numpy(dtype=float)
    bad = cases["policy_bad"].to_numpy(dtype=bool)
    admit = cases["admit_riskcap_fitted_risk"].to_numpy(dtype=bool)
    bins = [0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.01]
    labels = ["0–0.1", "0.1–0.3", "0.3–0.5", "0.5–0.7", "0.7–0.9", "0.9–1"]
    admitted_rate, rejected_rate, xs = [], [], []
    for index, (low, high) in enumerate(zip(bins[:-1], bins[1:])):
        mask = (share >= low) & (share < high)
        if mask.sum() < 40:
            continue
        xs.append(index)
        admitted_rate.append(bad[mask & admit].mean() if (mask & admit).any() else np.nan)
        rejected_rate.append(bad[mask & ~admit].mean() if (mask & ~admit).any() else np.nan)
        rows.append(
            {
                "figure": "fig4",
                "panel": "within_support",
                "variable": "admitted",
                "bin": labels[index],
                "point_c": admitted_rate[-1],
                "ci_low_c": np.nan,
                "ci_high_c": np.nan,
                "n_cases": int((mask & admit).sum()),
            }
        )
        rows.append(
            {
                "figure": "fig4",
                "panel": "within_support",
                "variable": "rejected",
                "bin": labels[index],
                "point_c": rejected_rate[-1],
                "ci_low_c": np.nan,
                "ci_high_c": np.nan,
                "n_cases": int((mask & ~admit).sum()),
            }
        )
    width = 0.38
    ax.bar(np.array(xs) - width / 2, admitted_rate, width=width, color=PURPLE, label="admitted by the fitted score")
    ax.bar(np.array(xs) + width / 2, rejected_rate, width=width, color=GREY, label="refused by the fitted score")
    ax.set_xticks(xs, [labels[i] for i in xs], fontsize=5.8)
    ax.set_xlabel("hidden share of the peak window")
    ax.set_ylabel("share above 0.5 °C")
    title(ax, "d", "within one support, the score separates")
    ax.legend(frameon=False, fontsize=5.8, loc="upper left")
    ax.set_ylim(0, 0.68)

    fig.tight_layout()
    save(fig, "f4_mechanism")
    pd.DataFrame(rows).to_csv(TABLE_DIR / "fig4_source.csv", index=False)


def fig4() -> None:
    pooled = pd.read_csv(ALIGNED / "crossfit_table.csv")
    contrasts = pd.read_csv(ALIGNED / "contrasts.csv")
    replay = pd.read_csv(REPLAY / "replay_admission.csv")
    hot = pd.read_csv(HOT / "hot_year_designed.csv")
    fig, axes = plt.subplots(2, 2, figsize=(5.6, 4.7))
    fig.patch.set_facecolor(SURFACE)
    rows = []

    # (a) retention at the 5% cap, both panels
    ax = axes[0, 0]
    style(ax)
    risk = pooled[pooled.row_type.eq("riskcap")]
    order = ["peak_overlap_rule", "fitted_risk", "calibrated_bound", "length_rule"]
    order_all = ["reconstruct_all", "peak_overlap_rule", "fitted_risk", "calibrated_bound", "length_rule"]
    width = 0.36
    for panel_index, (panel, label, hatch) in enumerate(
        (("wave2_confirmation", "external panel", None), ("development", "development", "///"))
    ):
        block = risk[risk.panel.eq(panel)]
        for arm_index, arm in enumerate(order):
            values = block[block.score.eq(arm)]["retention"].to_numpy(dtype=float) * 100
            if values.size == 0:
                continue
            x = arm_index + (panel_index - 0.5) * width
            ax.bar(x, values.mean(), width=width * 0.92, color=ARM_COLOURS[arm], alpha=0.9,
                   hatch=hatch, edgecolor=SURFACE, linewidth=0.4)
            ax.plot([x, x], [values.min(), values.max()], color=INK, linewidth=1.1)
            rows.append(
                {
                    "figure": "fig5",
                    "panel": "retention_at_cap",
                    "panel_name": panel,
                    "arm": arm,
                    "mean": values.mean(),
                    "min": values.min(),
                    "max": values.max(),
                }
            )
    ax.set_xticks(range(len(order)), [ARM_LABELS[a] for a in order], rotation=22, ha="right", fontsize=6.0)
    ax.set_ylabel("retention at the 5% cap (%)")
    ax.set_ylim(0, 108)
    ax.axhline(100, color=GRID, linewidth=0.8)
    title(ax, "a", "what each rule keeps")
    ax.text(0.38, 0.97, "solid: external panel\nhatched: development\nbars: mean of 3 fold seeds",
            transform=ax.transAxes, fontsize=5.2, color=INK_2, va="top")

    # (b) real-calendar coverage versus realised risk
    ax = axes[0, 1]
    style(ax)
    for arm in order_all:
        block = replay[replay.arm.eq(arm)]
        xs = block["admitted_share"].to_numpy(dtype=float) * 100
        ys = block["risk_among_admitted"].to_numpy(dtype=float) * 100
        ax.scatter(xs, ys, s=17, color=ARM_COLOURS[arm], alpha=0.85, edgecolor=SURFACE, linewidth=0.3,
                   label=ARM_LABELS[arm], zorder=3)
        rows.append(
            {
                "figure": "fig5",
                "panel": "replay_coverage_risk",
                "panel_name": "replay",
                "arm": arm,
                "mean": float(ys.mean()),
                "min": float(ys.min()),
                "max": float(ys.max()),
            }
        )
    ax.axhline(5.0, color=RED, linewidth=0.9, linestyle=(0, (4, 3)))
    ax.text(0.02, 0.84, "5% cap", color=RED, fontsize=6.0, transform=ax.transAxes)
    ax.set_xlabel("share of real-calendar groups admitted (%)")
    ax.set_ylabel("realised error rate (%)")
    ax.set_ylim(-0.3, 5.6)
    title(ax, "b", "real calendars may need no screen")
    ax.legend(frameon=False, fontsize=5.2, loc="center left", handletextpad=0.4, bbox_to_anchor=(0.02, 0.45))

    # (c) hot-year composition: what each rule refuses
    ax = axes[1, 0]
    style(ax)
    block = hot[(hot.panel.eq("wave2_confirmation")) & (hot.hot_c.eq(20.0)) & (hot.weighting.eq("case"))]
    order2 = ["reconstruct_all", "peak_overlap_rule", "fitted_risk", "calibrated_bound", "length_rule"]
    width = 0.38
    for arm_index, arm in enumerate(order2):
        subset = block[block.arm.eq(arm)]
        if subset.empty:
            continue
        refused = subset["abstained_hot_share"].to_numpy(dtype=float) * 100
        missed = 100.0 * subset["n_missed_hot"].to_numpy(dtype=float) / np.maximum(
            subset["n_true_hot_total"].to_numpy(dtype=float), 1.0
        )
        ax.bar(arm_index - width / 2, refused.mean(), width=width * 0.92, color=ARM_COLOURS[arm],
               alpha=0.92, edgecolor=SURFACE, linewidth=0.4, label="refused" if arm_index == 0 else None)
        ax.bar(arm_index + width / 2, missed.mean(), width=width * 0.92, color=ARM_COLOURS[arm],
               alpha=0.45, edgecolor=SURFACE, linewidth=0.4, label="kept but judged cool" if arm_index == 0 else None)
        for values, offset in ((refused, -width / 2), (missed, width / 2)):
            ax.plot([arm_index + offset, arm_index + offset], [values.min(), values.max()],
                    color=INK, linewidth=1.0)
            rows.append(
                {
                    "figure": "fig5",
                    "panel": "hot_year_error",
                    "panel_name": "wave2_20C",
                    "arm": arm,
                    "mean": values.mean(),
                    "min": values.min(),
                    "max": values.max(),
                }
            )
    ax.set_xticks(range(len(order2)), [ARM_LABELS[a] for a in order2], rotation=22, ha="right", fontsize=6.0)
    ax.set_ylabel("true hot years (%)")
    ax.set_ylim(0, 95)
    ax.legend(frameon=False, fontsize=5.6, loc="upper left")
    title(ax, "c", "refusal costs the hot years")

    # (d) the gain that survives: fitted minus peak-window retention
    ax = axes[1, 1]
    style(ax)
    subset = contrasts[
        contrasts.metric.eq("retention")
        & contrasts.left.eq("fitted_risk")
        & contrasts.right.eq("peak_overlap_rule")
    ]
    ys = []
    labels = []
    for index, panel in enumerate(("wave2_confirmation", "development")):
        block = subset[subset.panel.eq(panel)].sort_values("fold_seed")
        for seed_index, row in enumerate(block.itertuples(index=False)):
            y = index * 4 + seed_index
            ax.errorbar(
                [row.point * 100],
                [y],
                xerr=[[row.point * 100 - row.ci_low * 100], [row.ci_high * 100 - row.point * 100]],
                fmt="o",
                color=PURPLE,
                markersize=3.4,
                capsize=1.8,
                elinewidth=0.9,
            )
            ys.append(y)
            labels.append(f"{'external' if index == 0 else 'development'} seed {row.fold_seed}")
            rows.append(
                {
                    "figure": "fig5",
                    "panel": "fitted_minus_peak_pp",
                    "panel_name": panel,
                    "arm": f"seed {row.fold_seed}",
                    "mean": row.point * 100,
                    "min": row.ci_low * 100,
                    "max": row.ci_high * 100,
                }
            )
    ax.axvline(0, color=INK_2, linewidth=0.8)
    ax.axvline(5, color=RED, linewidth=0.9, linestyle=(0, (4, 3)))
    ax.text(2.4, 2.6, "pre-specified 5-point margin", fontsize=5.2, color=RED,
            rotation=90, va="center", ha="center")
    ax.set_yticks(ys, labels, fontsize=5.8)
    ax.set_xlabel("fitted − peak retention (points)")
    title(ax, "d", "the gain and its interval")
    ax.set_xlim(-2, 17)
    ax.set_ylim(-0.7, 6.2)
    ax.invert_yaxis()

    fig.tight_layout()
    save(fig, "f5_decision")
    pd.DataFrame(rows).to_csv(TABLE_DIR / "fig5_source.csv", index=False)




def main() -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    fig1()
    fig2()
    fig3()
    fig4()
    manifest = {
        "figures": ["f1_support", "f2_system_design", "f3_reconstructor", "f4_mechanism", "f5_decision", "s1_study_design"],
        "sources": {
            "wave2_cases": str(WAVE2.relative_to(ROOT)),
            "aligned_admissions": str((ALIGNED / "case_level_admissions_wave2_confirmation.parquet").relative_to(ROOT)),
            "aligned_crossfit": str((ALIGNED / "crossfit_table.csv").relative_to(ROOT)),
            "aligned_contrasts": str((ALIGNED / "contrasts.csv").relative_to(ROOT)),
            "replay_admission": str((REPLAY / "replay_admission.csv").relative_to(ROOT)),
            "hot_year": str((HOT / "hot_year_designed.csv").relative_to(ROOT)),
            "mechanism": str(MECH.relative_to(ROOT)),
        },
        "sha256": {
            "wave2_cases": sha256(WAVE2),
            "aligned_admissions": sha256(ALIGNED / "case_level_admissions_wave2_confirmation.parquet"),
            "aligned_crossfit": sha256(ALIGNED / "crossfit_table.csv"),
            "replay_admission": sha256(REPLAY / "replay_admission.csv"),
        },
    }
    (TABLE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("wrote figures and source tables")


if __name__ == "__main__":
    main()
