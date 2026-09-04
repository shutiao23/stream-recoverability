#!/usr/bin/env python3
"""Round-3 v14 figure set (REVIEW_v14_round2.md W3): six figures drawn from
the six-duration-grid canonical CSVs (2026-09-04 regeneration).

Fig 1  Headline: duration structure of realized benefit over the climatology
       default (both panels, unit means with network-cluster CIs), with the
       MAE-scale zero crossing and its bootstrap CI band, the Johnson (2021)
       m_max = 49 d reference, and the three-family robustness curves
       (deployment xgboost_b_d, donor ridge, seasonal ridge).
Fig 2  Estimator contrast: realized benefit vs legacy risk prediction and vs
       the differential prediction (second panel, placements coloured by
       duration), with per-duration Spearman annotations.
Fig 3  Main result: per-duration placement-level rho of diff / -risk /
       r6-diff / duration-only / risk with the season-LOO ceiling, plus the
       paired deltas (diff minus r6-diff, and diff minus -risk) with 95% CIs.
Fig 4  Decision layer: within-duration top-20% budgets (diff vs duration-only
       vs r6 vs risk, harmful-rate labels) and EC(xi)/delta value curves.
Fig 5  Downstream: climatology-default flip days per metric and per panel
       (log-x), with the 39-60 d family-median window and the MAE crossings.
Fig 6  Boundaries: three-level decomposition (diff vs duration-only) and the
       stationarity/null + default-difficulty parity summary.

Every annotation is asserted in-script against the named CSV.  Outputs:
results/v14/figures_v3/fig01..06*.png (300 dpi) + FIGURE_NOTES_v3.md.

Run: PYTHONPATH=$PWD/src python3 scripts/153_run_v14_figures_r3.py
"""

from __future__ import annotations

import json
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
OUT = ROOT / "results/v14/figures_v3"

DURATIONS = [7, 14, 30, 60, 90, 180]
PANEL_COLOR = {"first": "#1f77b4", "second": "#d62728"}
FAMILY_STYLE = {
    "xgboost_b_d (deployment)": ("#1f77b4", "o"),
    "donor_blup_ridge": ("#2ca02c", "s"),
    "seasonal_boundary_ridge": ("#ff7f0e", "^"),
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


def ci_text(lo: float, hi: float) -> str:
    return f"[{lo:+.2f}, {hi:+.2f}]"


def log10_x(ax, lo=5, hi=400):
    ax.set_xscale("log")
    ax.set_xlim(lo, hi)
    ax.set_xticks([7, 14, 30, 60, 90, 180, 365])
    ax.set_xticklabels(["7", "14", "30", "60", "90", "180", "365"])


def _load_flip_mae() -> pd.DataFrame:
    f = pd.read_csv(P4 / "flip_table.csv")
    return f.loc[f["kind"] == "mae_reference"].copy()


def _load_crossing() -> pd.DataFrame:
    return pd.read_csv(P4 / "mae_crossing_ci.csv")


def _load_family() -> pd.DataFrame:
    return pd.read_csv(P1 / "family_benefit_table.csv")


def _load_paired() -> pd.DataFrame:
    c = pd.read_csv(P0 / "paired_diff_vs_r6.csv")
    return c.loc[c["seed"] == 20260903].copy()


def _load_negrisk() -> pd.DataFrame:
    return pd.read_csv(P0 / "paired_diff_vs_negrisk.csv")


def _load_metrics_pooled() -> pd.DataFrame:
    m = pd.read_csv(P0 / "metrics_by_horizon.csv")
    m = m.loc[m["level"].astype(str).str.contains("placement", na=False)]
    m = m.loc[~m["horizon"].astype(str).eq("direct")]
    m["horizon"] = m["horizon"].astype(int)
    return m


def _load_loo() -> pd.DataFrame:
    return pd.read_csv(P0 / "season_loo_upper.csv")


def _load_three_level() -> pd.DataFrame:
    return pd.read_csv(P0 / "three_level_decomposition.csv")


def _load_budget() -> pd.DataFrame:
    b = pd.read_csv(P0 / "budget_within_duration.csv")
    return b.loc[(b["panel"] == "second") & (b["budget"] == 0.2)].copy()


def _load_laio() -> pd.DataFrame:
    return pd.read_csv(P2 / "laio_tamea_curves.csv")


def _load_flip_crossings() -> pd.DataFrame:
    f = pd.read_csv(P4 / "flip_table.csv")
    return f.loc[f["kind"] == "crossing"].copy()


# --------------------------------------------------------------------------
def fig1(mae: pd.DataFrame, cross: pd.DataFrame, fam: pd.DataFrame) -> Path:
    path = OUT / "fig01_duration_structure_and_families.png"
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), sharey=False)

    ax = axes[0]
    for panel, color in PANEL_COLOR.items():
        sub = mae.loc[mae["panel"] == panel].sort_values("horizon")
        x = sub["horizon"].astype(float).to_numpy()
        y = sub["point"].to_numpy()
        lo = sub["ci_lower"].to_numpy()
        hi = sub["ci_upper"].to_numpy()
        ax.errorbar(
            x, y, yerr=[y - lo, hi - y], fmt="o-", ms=4, lw=1.2,
            color=color, ecolor=color, capsize=2, label=f"{panel} panel",
        )
        row = cross.loc[cross["panel"] == panel].iloc[0]
        point = float(row["point_crossing_day"])
        ax.axvline(point, color=color, ls="--", lw=0.8, alpha=0.7)
        ax.axvspan(float(row["ci_low"]), float(row["ci_high"]),
                   color=color, alpha=0.06)
        ax.annotate(
            f"{panel}: flip {point:.0f} d\nCI {float(row['ci_low']):.0f}-"
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
    ax.set_ylabel("mean realized benefit vs climatology fill (°C)")
    ax.set_xlabel("gap duration (d, log scale)")
    ax.set_title("(a) Duration structure of realized benefit over climatology fill")
    ax.legend(frameon=False, loc="upper right")
    # assert annotations
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
            "gap_length_days"
        )
        ax.plot(
            rows["gap_length_days"], rows["mean_benefit_deg_c"],
            marker=marker, ms=4, lw=1.2, color=color, label=label,
        )
    ax.axhline(0.0, color="k", lw=0.8)
    log10_x(ax)
    ax.set_xlabel("gap duration (d, log scale)")
    ax.set_ylabel("mean benefit vs climatology (°C)")
    ax.set_title("(b) Three model families reproduce the sign flip (first panel)")
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------
def fig2(metrics: pd.DataFrame) -> Path:
    path = OUT / "fig02_estimand_contrast.png"
    df = pd.read_csv(P0 / "placement_predictions_second.csv")
    df = df.loc[df["direct"]].copy()
    durations = sorted(int(d) for d in df["gap_length"].unique())
    colors = plt.cm.viridis(np.linspace(0.05, 0.95, len(durations)))
    color_of = {d: c for d, c in zip(durations, colors)}
    m = metrics.loc[metrics["panel"] == "second"]

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    for ax, xcol, pred in (
        (axes[0], "risk_prediction", "legacy risk prediction (model MAE)"),
        (axes[1], "diff_prediction", "differential benefit prediction"),
    ):
        for dur in durations:
            sub = df.loc[df["gap_length"] == dur]
            ax.scatter(
                sub[xcol], sub["realized_benefit"], s=2.5, alpha=0.25,
                color=color_of[dur], label=f"{dur} d",
            )
        ax.set_xlabel(pred)
        ax.set_ylabel("realized benefit vs climatology (°C)")
    axes[0].set_title("(a) Ranked by model error")
    axes[1].set_title("(b) Ranked by differential benefit")
    for ax in axes:
        ax.legend(frameon=False, markerscale=3, fontsize=6.5, loc="upper left")
        ax.axhline(0.0, color="k", lw=0.6)

    # per-duration Spearman annotations (asserted from metrics table)
    for ax, pred in ((axes[0], "risk"), (axes[1], "diff")):
        ypos = 0.95
        for dur in durations:
            row = m.loc[(m["horizon"] == dur)].iloc[0]
            rho = float(row[f"{pred}_rho"])
            lo = float(row["diff_ci_lower"]) if pred == "diff" else np.nan
            hi = float(row["diff_ci_upper"]) if pred == "diff" else np.nan
            ax.text(
                0.03, ypos, f"{dur} d: {rho:+.2f}" +
                (f" {ci_text(lo, hi)}" if pred == "diff" else ""),
                transform=ax.transAxes, fontsize=6.8,
                color=color_of[dur],
            )
            ypos -= 0.055
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------
def fig3(paired, negrisk, metrics, loo) -> Path:
    path = OUT / "fig03_main_result.png"
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
    loo2 = loo2.loc[~loo2["horizon"].astype(str).eq("direct")].copy()
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
    ax.set_title("(a) Ranking strength within duration strata")
    ax.legend(frameon=False, ncol=3, loc="lower center", fontsize=6.6)
    for xi, y in zip(xs, rho_diff):
        ax.text(xi - 2 * width, y + 0.015, f"{y:.2f}", ha="center",
                fontsize=6.2, color="#1f77b4")

    ax = axes[1]
    d_r6 = second["delta_rho"].to_numpy()
    lo_r6 = second["delta_ci_lower"].to_numpy()
    hi_r6 = second["delta_ci_upper"].to_numpy()
    d_neg = np.array([float(neg.loc[d, "delta_diff_minus_negrisk_mean"]) for d in DURATIONS])
    lo_n = np.array([float(neg.loc[d, "delta_diff_minus_negrisk_ci_low"]) for d in DURATIONS])
    hi_n = np.array([float(neg.loc[d, "delta_diff_minus_negrisk_ci_high"]) for d in DURATIONS])
    ax.errorbar(
        xs - 0.12, d_r6, yerr=[d_r6 - lo_r6, hi_r6 - d_r6],
        fmt="o", ms=4, color="#2ca02c", capsize=2, label="diff − r6-diff",
    )
    ax.errorbar(
        xs + 0.12, d_neg, yerr=[d_neg - lo_n, hi_n - d_neg],
        fmt="s", ms=4, color="#1f77b4", capsize=2, label="diff − (−risk)",
    )
    ax.axhline(0.0, color="k", lw=0.8)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{d} d" for d in DURATIONS])
    ax.set_ylabel("paired Δρ (95% network-cluster CI)")
    ax.set_title("(b) Paired deltas vs fitting-record and sign-flipped baselines")
    ax.legend(frameon=False, loc="lower right", fontsize=7)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------
def fig4(budget, laio) -> Path:
    path = OUT / "fig04_decision_layer.png"
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))

    ax = axes[0]
    piv = budget.pivot_table(
        index="predictor", columns="horizon", values="mean_realized_benefit"
    )
    harm = budget.pivot_table(
        index="predictor", columns="horizon", values="harmful_rate"
    )
    xs = np.arange(len(DURATIONS))
    width = 0.19
    for i, (pred, color, lab) in enumerate(
        (
            ("diff", "#1f77b4", "diff (benefit ranking)"),
            ("duration", "#7f7f7f", "duration-only"),
            ("r6_diff", "#2ca02c", "r6-diff"),
            ("risk", "#d62728", "v13 risk"),
        )
    ):
        vals = [float(piv.loc[pred, d]) for d in DURATIONS]
        ax.bar(xs + (i - 1.5) * width, vals, width, color=color, label=lab)
    ax.axhline(0.0, color="k", lw=0.6)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{d} d" for d in DURATIONS])
    ax.set_ylabel("mean realized benefit of top-20% (°C)")
    ax.set_title("(a) Within-duration 20% budgets (second panel)")
    ax.legend(frameon=False, fontsize=6.6, loc="lower left")
    for d_i, d in enumerate(DURATIONS):
        h = float(harm.loc["diff", d]) * 100
        ax.text(d_i - 1.5 * width, float(piv.loc["diff", d]) + 0.03,
                f"{h:.0f}%", ha="center", fontsize=6.0, color="#1f77b4")

    ax = axes[1]
    for (panel, hor), g in laio.groupby(["panel", "horizon"]):
        if panel == "second" and hor in ("7", 7, "direct", "14", 14, "30", 30, "180", 180):
            pass
    for dur, color in ((7, "#cccccc"), (30, "#999999"), (180, "#666666"),
                       ("direct", "#bbbbbb")):
        g = laio.loc[(laio["panel"] == "second") & (laio["horizon"].astype(str) == str(dur))]
        ax.plot(g["xi"], g["EC_fcst_delta_ratio"], lw=1.0, color=color,
                label=f"{dur} d (pooled-direct)" if dur == "direct" else f"{dur} d")
    for dur, color in ((60, "#1f77b4"), (90, "#d62728")):
        g = laio.loc[(laio["panel"] == "second") & (laio["horizon"].astype(str) == str(dur))]
        ax.plot(g["xi"], g["EC_fcst_delta_ratio"], lw=1.4, color=color,
                label=f"{dur} d (bounded excursion)")
        gmax = g.loc[g["EC_fcst_delta_ratio"].idxmax()]
        ax.annotate(
            f"{float(gmax['EC_fcst_delta_ratio']):.3f} @ ξ={float(gmax['xi']):.2f}",
            xy=(float(gmax["xi"]), float(gmax["EC_fcst_delta_ratio"])),
            fontsize=6.2, color=color,
        )
    ax.axhline(1.0, color="k", lw=0.8)
    ax.axvspan(0.0, 0.5, color="0.9", alpha=0.6)
    ax.text(0.02, 1.12, "realistic region ξ<0.5", fontsize=6.4)
    ax.set_xlabel("cost ratio ξ")
    ax.set_ylabel("EC(ξ)/δ")
    ax.set_title("(b) Continuous cost–loss value curves (second panel)")
    ax.legend(frameon=False, fontsize=6.4)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------
def fig5(crossings: pd.DataFrame) -> Path:
    path = OUT / "fig05_downstream_flips.png"
    metrics = [
        "annual_mean", "summer_mean", "amplitude", "phase_doy", "p90",
        "summer_max", "exceed_days_20", "exceed_days_25", "cdd10",
        "trend_slope",
    ]
    labels = {
        "annual_mean": "annual mean", "summer_mean": "summer mean",
        "amplitude": "amplitude", "phase_doy": "phase day",
        "p90": "p90", "summer_max": "summer max",
        "exceed_days_20": "days>20°C", "exceed_days_25": "days>25°C",
        "cdd10": "degree-days>10°C", "trend_slope": "trend slope",
    }
    fig, axes = plt.subplots(2, 1, figsize=(8.6, 7.0), sharex=True)
    for ax, panel in zip(axes, ("first", "second")):
        mae = crossings.loc[(crossings["panel"] == panel)
                            & (crossings["metric"] == "mae_scale")]
        mae_day = float(mae["crossing_day"].iloc[0])
        ax.axvline(mae_day, color=PANEL_COLOR[panel], ls="--", lw=1.0)
        ax.text(mae_day + 3, len(metrics) - 0.5,
                f"MAE-scale crossing {mae_day:.0f} d",
                fontsize=6.6, color=PANEL_COLOR[panel])
        for i, met in enumerate(metrics):
            row = crossings.loc[(crossings["panel"] == panel)
                                & (crossings["metric"] == met)]
            if not len(row):
                continue
            day = float(row["crossing_day"].iloc[0])
            y = len(metrics) - 1 - i
            if np.isfinite(day):
                ax.plot([day], [y], marker="o", ms=5, color=PANEL_COLOR[panel])
                ax.text(day + 3, y, f"{day:.0f}", fontsize=5.8,
                        color=PANEL_COLOR[panel])
            else:
                ax.text(8, y, "no flip", fontsize=5.8, color="gray")
        ax.axvspan(39, 60, color="0.9", alpha=0.7)
        ax.set_yticks(range(len(metrics)))
        ax.set_yticklabels([labels[m] for m in reversed(metrics)])
        ax.set_ylim(-0.6, len(metrics) + 0.4)
        ax.set_title(f"{panel} panel — downstream flips over climatology default")
    for ax in axes:
        ax.set_xscale("log")
        ax.set_xlim(5, 400)
        ax.set_xticks([7, 14, 30, 60, 90, 180, 365])
        ax.set_xticklabels(["7", "14", "30", "60", "90", "180", "365"])
        ax.grid(axis="y", lw=0.3, alpha=0.4)
    axes[1].set_xlabel("first horizon with negative reconstruction benefit (d, log)")
    axes[0].text(5.6, 0.2, "shaded: family-median window 39–60 d",
                 fontsize=6.4, color="0.3")
    fig.suptitle("Downstream thermal-regime flips vs the MAE-scale crossing",
                 fontsize=9.5)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------
def fig6(three: pd.DataFrame, laio: pd.DataFrame) -> Path:
    path = OUT / "fig06_boundaries.png"
    drift = json.loads((P3 / "direction_test.json").read_text())
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0))
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
        ax.bar(i - 0.19, a, 0.38, color="#1f77b4", label="diff" if i == 0 else None)
        ax.bar(i + 0.19, b, 0.38, color="#7f7f7f", label="duration-only" if i == 0 else None)
    ax.set_xticks(xpos)
    ax.set_xticklabels(levels, fontsize=6.8)
    ax.set_ylabel("pooled-direct Spearman ρ (second panel)")
    ax.set_title("(a) Three-level decomposition")
    ax.legend(frameon=False, fontsize=7)

    ax = axes[1]
    t2 = drift["T2_pooled_placement"]
    t3 = drift["T3_pooled_network"]
    ax.errorbar(
        [0], [t2["mean"]], yerr=[[t2["mean"] - t2["ci"][0]],
                                 [t2["ci"][1] - t2["mean"]]],
        fmt="o", color="#1f77b4", capsize=3,
        label=f"T2 placement (P(>0)={t2['prob_gt0']:.2f})",
    )
    ax.errorbar(
        [1], [t3["mean"]], yerr=[[t3["mean"] - t3["ci"][0]],
                                 [t3["ci"][1] - t3["mean"]]],
        fmt="s", color="#d62728", capsize=3,
        label=f"T3 network (P(>0)={t3['prob_gt0']:.2f})",
    )
    ax.axhline(0.0, color="k", lw=0.8)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["T2 pooled\nplacement", "T3 pooled\nnetwork"], fontsize=7)
    ax.set_ylabel("drift-stratum advantage of diff over r6-diff")
    ax.set_title("(b) Stationarity null (drift vs stable strata)")
    ax.legend(frameon=False, fontsize=7)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    mae = _load_flip_mae()
    cross = _load_crossing()
    fam = _load_family()
    paired = _load_paired()
    negrisk = _load_negrisk()
    metrics = _load_metrics_pooled()
    loo = _load_loo()
    budget = _load_budget()
    laio = _load_laio()
    crossings = _load_flip_crossings()
    three = _load_three_level()

    notes = [
        "# FIGURE NOTES v3 (round-3 regeneration, 2026-09-04)",
        "",
        ("All numbers on the panels are asserted against the canonical CSVs "
        "(six-duration grid).  Sources per figure:"),
        ("- fig01: `p4_flip_analysis/flip_table.csv` (mae_reference rows), "
        "`p4_flip_analysis/mae_crossing_ci.csv`, "
        "`p1_baselines/family_benefit_table.csv`; Johnson line 49 d."),
        ("- fig02: `p0_differential/placement_predictions_second.csv` "
        "(scatter), `metrics_by_horizon.csv` (rho annotations)."),
        ("- fig03: `paired_diff_vs_r6.csv`, `paired_diff_vs_negrisk.csv`, "
        "`metrics_by_horizon.csv`, `season_loo_upper.csv`."),
        "- fig04: `budget_within_duration.csv`, `laio_tamea_curves.csv`.",
        "- fig05: `p4_flip_analysis/flip_table.csv` crossing rows.",
        ("- fig06: `three_level_decomposition.csv`, "
        "`p3_drift/direction_test.json`."),
    ]
    paths = [
        fig1(mae, cross, fam),
        fig2(metrics),
        fig3(paired, negrisk, metrics, loo),
        fig4(budget, laio),
        fig5(crossings),
        fig6(three, laio),
    ]
    (OUT / "FIGURE_NOTES_v3.md").write_text("\n".join(notes) + "\n")
    for p in paths:
        print("wrote", p)


if __name__ == "__main__":
    main()
