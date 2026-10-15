#!/usr/bin/env python3
"""Figure 1 for the major revision: what the admission rule changes.

Replaces the study-design schematic as the opening figure (the schematic moves to
the SI).  Three panels, each answering one question a reader of the abstract will
ask, and every value read from a frozen artifact at build time:

a.  At an honest 5 % false-admit cap -- thresholds chosen on calibration networks
    only -- how much of the candidate pool does each rule keep?
b.  Where do those rules sit on the risk-retention plane, and how far is the
    operating point the earlier draft quoted (chosen on evaluation labels) from
    the deployable one?
c.  At a matched 70 % retention, what false-admit rate does each rule leave?

Source: results/wrr_submission_ready/major_revision_20261014/p0_02_frozen_risk_thresholds/
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
SRC = ROOT / "results" / "wrr_submission_ready" / "major_revision_20261014" / "p0_02_frozen_risk_thresholds"
OUT_DIRS = [ROOT / "figures" / "wrr", ROOT / "paper" / "wrr" / "figures"]
NAME = "f1_decision"

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, GREY, RED = "#2a78d6", "#eb6834", "#8a8a86", "#b03030"

# Type 42 outlines: AGU does not accept Type 3 fonts, and this figure is included
# at the printed column width, so the type must be legible at 5.5 in.
plt.rcParams.update({
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "font.size": 7.0,
    "axes.labelsize": 7.0,
    "axes.titlesize": 7.6,
    "xtick.labelsize": 6.4,
    "ytick.labelsize": 6.4,
    "legend.fontsize": 6.2,
    "savefig.facecolor": SURFACE,
})

LABELS = {
    "calibrated_bound": "calibrated certificate bound",
    "fitted_risk": "fitted risk score",
    "peak_overlap_rule": "peak-window rule",
    "length_rule": "gap-length rule",
}
ORDER = ["calibrated_bound", "fitted_risk", "peak_overlap_rule", "length_rule"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cross = pd.read_csv(SRC / "crossfit_risk_cap_table.csv")
    post = pd.read_csv(SRC / "posthoc_vs_honest.csv")
    return cross, post, cross


def main() -> int:
    cross, post, _ = load()
    wave = cross[cross.panel == "wave2_confirmation"]

    honest = wave[wave.row_type == "pooled_risk_cap"].copy()
    at70 = wave[wave.row_type == "fixed_retention_70_pooled"].copy()

    fig, axes = plt.subplots(3, 1, figsize=(5.5, 6.6))
    fig.patch.set_facecolor(SURFACE)
    for ax in axes:
        ax.set_facecolor(SURFACE)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.spines["left"].set_color(GRID)
        ax.spines["bottom"].set_color(GRID)
        ax.grid(color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)

    # ---- panel a: retention at the honest risk cap -------------------------
    ax = axes[0]
    ys = np.arange(len(ORDER))[::-1]
    for y, score in zip(ys, ORDER):
        rows = honest[honest.score == score]
        if rows.empty:
            continue
        value = float(rows.test_retention.mean()) * 100
        low = float(rows.test_retention.quantile(0.0)) * 100
        high = float(rows.test_retention.quantile(1.0)) * 100
        colour = BLUE if score == "calibrated_bound" else (ORANGE if score != "length_rule" else GREY)
        ax.barh(y, value, height=0.6, color=colour, alpha=0.9)
        ax.plot([low, high], [y, y], color=INK, linewidth=1.4)
        for spine in ("top", "bottom", "left", "right"):
            pass
        ax.text(value + 1.5, y, f"{value:.0f}%", va="center", fontsize=6.8, color=INK)
        n_adm = int(rows.test_n_admitted.mean())
        ax.text(1.0, y - 0.34, f"n={n_adm:,} of {int(rows.test_n_cases.iloc[0]):,}", fontsize=6.0, color=INK_2)
    ax.set_yticks(ys, [LABELS[s] for s in ORDER], fontsize=6.8)
    ax.set_xlim(0, 100)
    ax.set_xlabel("retention at an honest 5% false-admit cap (%)", fontsize=7)
    ax.set_title("a  What each rule can admit", loc="left", fontsize=7.6, color=INK)

    # ---- panel b: risk-retention plane -------------------------------------
    ax = axes[1]
    for score in ORDER:
        rows = honest[honest.score == score]
        if rows.empty:
            continue
        x = float(rows.test_retention.mean()) * 100
        y = float(rows.test_false_admit_rate.mean()) * 100
        colour = BLUE if score == "calibrated_bound" else (ORANGE if score != "length_rule" else GREY)
        ax.scatter([x], [y], s=42, color=colour, zorder=3, label=LABELS[score])
        ax.annotate(LABELS[score].split()[0], (x, y), textcoords="offset points", xytext=(5, 5),
                    fontsize=6.0, color=INK_2)
        ph = post[(post.panel == "wave2_confirmation") & (post.score == score) &
                  (post.method.str.contains("posthoc", na=False))]
        if not ph.empty:
            ax.scatter([float(ph.retention.iloc[0]) * 100], [float(ph.false_admit_rate.iloc[0]) * 100],
                       s=42, facecolors="none", edgecolors=RED, linewidths=1.2, zorder=2)
    ax.axhline(5.0, color=RED, linewidth=1.0, linestyle=(0, (4, 3)))
    ax.text(1, 5.25, "5% cap", fontsize=6.2, color=RED)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 12)
    ax.set_xlabel("retention (%)", fontsize=7)
    ax.set_ylabel("realised false-admit rate (%)", fontsize=7)
    ax.set_title("b  Honest (filled) vs label-chosen (open red)", loc="left", fontsize=7.6, color=INK)

    # ---- panel c: false-admit at matched retention -------------------------
    ax = axes[2]
    for y, score in zip(ys, ORDER):
        rows = at70[at70.score == score]
        if rows.empty:
            continue
        value = float(rows.test_false_admit_rate.iloc[0]) * 100
        low = float(rows.test_false_admit_ci95_low.iloc[0]) * 100
        high = float(rows.test_false_admit_ci95_high.iloc[0]) * 100
        colour = BLUE if score == "calibrated_bound" else (ORANGE if score != "length_rule" else GREY)
        ax.barh(y, value, height=0.6, color=colour, alpha=0.9)
        ax.plot([low, high], [y, y], color=INK, linewidth=1.4)
        ax.text(value + 0.15, y, f"{value:.1f}%", va="center", fontsize=6.8, color=INK)
    ax.set_yticks(ys, ["" for _ in ORDER])
    ax.set_xlim(0, 12)
    ax.set_xlabel("false-admit rate at 70% retention (%)", fontsize=7)
    ax.set_title("c  At matched retention", loc="left", fontsize=7.6, color=INK)

    fig.tight_layout()
    for directory in OUT_DIRS:
        directory.mkdir(parents=True, exist_ok=True)
        fig.savefig(directory / f"{NAME}.pdf", dpi=400, bbox_inches="tight", pad_inches=0.05)
        fig.savefig(directory / f"{NAME}.png", dpi=300, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)

    payload = {
        "schema_version": 1,
        "figure": NAME,
        "script_sha256": sha256(Path(__file__)),
        "inputs": {
            str((SRC / "crossfit_risk_cap_table.csv").relative_to(ROOT)):
                sha256(SRC / "crossfit_risk_cap_table.csv"),
            str((SRC / "posthoc_vs_honest.csv").relative_to(ROOT)):
                sha256(SRC / "posthoc_vs_honest.csv"),
        },
        "panel_a_retention_at_risk_cap_pct": {
            s: {
                "mean": round(float(honest[honest.score == s].test_retention.mean()) * 100, 3),
                "min": round(float(honest[honest.score == s].test_retention.min()) * 100, 3),
                "max": round(float(honest[honest.score == s].test_retention.max()) * 100, 3),
            }
            for s in ORDER if not honest[honest.score == s].empty
        },
        "panel_c_false_admit_at_70_pct": {
            s: round(float(at70[at70.score == s].test_false_admit_rate.iloc[0]) * 100, 3)
            for s in ORDER if not at70[at70.score == s].empty
        },
    }
    (ROOT / "figures" / "wrr" / f"{NAME}_data.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload["panel_a_retention_at_risk_cap_pct"], indent=1))
    print(json.dumps(payload["panel_c_false_admit_at_70_pct"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
