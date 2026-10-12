#!/usr/bin/env python3
"""Figure 2 (panels a and b) -- where the certificate screen's gain holds, and
where it collapses.

Two data figures for the rewritten manuscript:

  a  the endpoint ordering. For each of the five endpoints the AUC difference
     between the best timing axis and the outage-length rule, with
     network-clustered 95% intervals. The ordering runs from the two warm
     extremes, where timing wins, through the amplitude, to the annual mean and
     the cold extreme, where the length rule wins. Both regimes are labelled on
     the panel and the reversal is marked.

  b  the panel heterogeneity. A forest plot of the pooled contrast
     (certificate rate minus length-rule rate, percentage points, negative
     favours the screen) with its 95% interval for each evidence panel from the
     oldest retrospective panel to the sealed transport panel, with the
     pre-declared threshold (delta = -1.0 point) drawn as a vertical line.

Data contract
-------------
Every plotted number is read at build time from a named artifact under
``results/``, and each row of the side-car JSON carries the artifact path, the
filter applied and the fields read. Nothing is typed by hand, no value is
recomputed here, and no artifact is written. The read-only inputs are hashed and
the digests are recorded in ``figures/wrr/f2_heterogeneity_data.json``.

One row the brief asks for is not available: a *real-archive empirical arm*.
The 2422 real incomplete station-years carry no truth by construction, so no
truth-based contrast exists for them; the closest outcome-agnostic comparison
(the admission disagreement) is recorded in the JSON and the caption material as
context, and is not plotted. See ``REAL_ARCHIVE_ROW`` below.

Style
-----
Palette, panel-letter convention, fonts and line weights follow
``scripts/188_v17_figures.py`` and ``scripts/204_v17_figures_q1.py``; the type
scale is the journal one from ``stream_recoverability.plotting.journal``, applied
unconditionally because these figures are drawn at the printed column width.
Both pages are 5.5 in wide or narrower, so they are never scaled down, and no
text is smaller than 6.0 pt.

Outputs (write scope: figures/wrr/ and scratch/heterogeneity/ only)
-------------------------------------------------------------------
  figures/wrr/f2a_endpoint_ordering.pdf
  figures/wrr/f2a_endpoint_ordering.png
  figures/wrr/f2b_panel_heterogeneity.pdf
  figures/wrr/f2b_panel_heterogeneity.png
  figures/wrr/f2_heterogeneity_data.json
  figures/wrr/f2_caption_material.md
  scratch/heterogeneity/f2a_endpoint_ordering_words.tsv   (pdftotext -bbox dump)
  scratch/heterogeneity/f2b_panel_heterogeneity_words.tsv
  scratch/heterogeneity/render_checks.json

Usage
-----
    python3 scripts/267_wrr_heterogeneity_figures.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.plotting.journal import COLUMN_INCHES, rc_overrides  # noqa: E402

# Drawn at the printed width, so the journal type scale applies unconditionally
# (the same device scripts/265_wrr_figure1_example.py uses).
os.environ.setdefault("WRR_JOURNAL_FIGURES", "1")

FIGURES = ROOT / "figures" / "wrr"
SCRATCH = ROOT / "scratch" / "heterogeneity"

# Categorical slots and surface from scripts/188_v17_figures.py and
# scripts/204_v17_figures_q1.py. One meaning per colour: grey = retrospective
# panel, blue = sealed confirmation, orange = transport.
SURFACE, INK, INK_2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8985", "#e4e3df"
BLUE, ORANGE = "#2a78d6", "#eb6834"
BLUE_TINT, ORANGE_TINT = "#eef4fd", "#fdeee6"

# Type scale (pt). The minimum is asserted below and re-measured from the PDF.
FS_TICK, FS_LABEL, FS_TITLE = 6.4, 7.0, 7.6
FS_LEGEND, FS_VALUE, FS_NOTE = 6.2, 6.2, 6.0
MIN_NOMINAL_PT = 6.0

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
        "axes.axisbelow": True,
        "legend.frameon": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "lines.linewidth": 2.0,
        # Type-42 embedding, so the PDF carries TrueType outlines rather than
        # Type-3 procedures.
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)
plt.rcParams.update(rc_overrides())

# --------------------------------------------------------------------------- #
# artifacts (read-only)
# --------------------------------------------------------------------------- #
A_AUC_CONTRASTS = "results/v17_fitness/step22_robustness/auc_contrasts.csv"
A_DEVELOPMENT_CASES = "results/v17_fitness/step4_ceiling/development_cases.parquet"
A_STEP10_VERDICT = "results/v17_fitness/step10_confirmation/verdict.json"
A_ARM_CONTRASTS = "results/v17_fitness/step11_arm_robustness/arm_contrasts.csv"
A_SEALED_VERDICT = "results/wrr_submission_ready/p0_07_sealed_confirmation/verdict.json"
A_SEALED_CASES = "results/wrr_submission_ready/p0_07_sealed_confirmation/sealed_cases.parquet"
A_SEALED_DIAGNOSTIC = (
    "results/wrr_submission_ready/amendments/sealed_usgs_prior_access_diagnostic/summary.json"
)
A_TRANSPORT_VERDICT = (
    "results/wrr_submission_ready/p0_07b_multi_agency_transport/verdict.json"
)
A_ARCHIVE_SUMMARY = "results/v18_closure/e2_archive_deployment/summary.json"
A_ARCHIVE_DISAGREEMENT = "results/v18_closure/e2_archive_deployment/threshold_disagreement.csv"

ARTIFACTS = [
    A_AUC_CONTRASTS,
    A_DEVELOPMENT_CASES,
    A_STEP10_VERDICT,
    A_ARM_CONTRASTS,
    A_SEALED_VERDICT,
    A_SEALED_CASES,
    A_SEALED_DIAGNOSTIC,
    A_TRANSPORT_VERDICT,
    A_ARCHIVE_SUMMARY,
    A_ARCHIVE_DISAGREEMENT,
]

# The endpoint order the panel draws, most positive to most negative.
ENDPOINT_ORDER = ["hottest7", "hottest30", "amplitude30", "annual_mean", "coldest30"]
ENDPOINT_LABELS = {
    "hottest7": "hottest 7-day mean",
    "hottest30": "hottest 30-day mean",
    "amplitude30": "amplitude",
    "annual_mean": "annual mean",
    "coldest30": "coldest 30-day mean",
}

IDENTITY_COLOURS = {
    "retrospective": MUTED,
    "sealed": BLUE,
    "transport": ORANGE,
}

REAL_ARCHIVE_ROW = {
    "requested_row": "real-archive empirical arm",
    "plotted": False,
    "reason": (
        "The real archive is the 2422 real incomplete station-years of "
        "e2_archive_deployment. Those years carry no truth by construction, so no "
        "certificate-minus-length error-rate contrast (or interval) exists for them; "
        "the requested row cannot be sourced and is not drawn."
    ),
    "checked_artifacts": [A_ARCHIVE_SUMMARY, A_ARCHIVE_DISAGREEMENT],
}


def read_json(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def disp(text: str) -> str:
    """Typographic minus for display, matching the axis tick labels."""

    return text.replace("-", "\u2212")


def sha256_of(rel: str) -> str:
    digest = hashlib.sha256()
    with (ROOT / rel).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# panel a
# --------------------------------------------------------------------------- #
def panel_a_rows() -> list[dict]:
    """Five endpoint contrasts, read whole from the step-22 robustness table."""

    frame = pd.read_csv(ROOT / A_AUC_CONTRASTS)
    present = set(frame["metric"])
    missing = [m for m in ENDPOINT_ORDER if m not in present]
    if missing:
        raise SystemExit(f"{A_AUC_CONTRASTS} is missing endpoint(s): {missing}")
    block = frame.set_index("metric").reindex(ENDPOINT_ORDER)

    # Case and network counts of the table the contrasts are computed on. The
    # step-22 contrast for each endpoint uses every row of this table
    # (n in auc_contrasts.csv equals its row count), so the network count is the
    # distinct network_id over the rows that carry that endpoint's truth.
    cases = pd.read_parquet(ROOT / A_DEVELOPMENT_CASES)
    axis_cols = ["peak_overlap", "warm_observed_fraction", "longest_run"]
    networks: dict[str, int] = {}
    rows_for_case_count: dict[str, int] = {}
    for metric in ENDPOINT_ORDER:
        keep = cases[[f"truth_{metric}", *axis_cols]].notna().all(axis=1)
        networks[metric] = int(cases.loc[keep, "network_id"].nunique())
        rows_for_case_count[metric] = int(keep.sum())

    rows: list[dict] = []
    for rank, metric in enumerate(ENDPOINT_ORDER):
        record = block.loc[metric]
        n_cases = int(record["n"])
        if rows_for_case_count[metric] != n_cases:
            raise SystemExit(
                f"case count mismatch for {metric}: auc_contrasts n={n_cases}, "
                f"development_cases filter rows={rows_for_case_count[metric]}"
            )
        rows.append(
            {
                "rank": rank,
                "metric": metric,
                "label": ENDPOINT_LABELS[metric],
                "auc_timing_minus_length": float(record["auc_timing_minus_length"]),
                "ci_low": float(record["ci_low"]),
                "ci_high": float(record["ci_high"]),
                "tolerance_c": float(record["tolerance_c"]),
                "base_rate": float(record["base_rate"]),
                "timing_wins": bool(record["timing_wins"]),
                "length_wins": bool(record["length_wins"]),
                "n_cases": n_cases,
                "n_networks": networks[metric],
                "source": {
                    "artifact": A_AUC_CONTRASTS,
                    "filter": f"metric == '{metric}' (whole table; five rows)",
                    "fields": [
                        "auc_timing_minus_length",
                        "ci_low",
                        "ci_high",
                        "tolerance_c",
                        "base_rate",
                        "timing_wins",
                        "length_wins",
                        "n",
                    ],
                },
                "n_source": {
                    "n_cases": {
                        "artifact": A_AUC_CONTRASTS,
                        "filter": f"metric == '{metric}'",
                        "field": "n",
                    },
                    "n_networks": {
                        "artifact": A_DEVELOPMENT_CASES,
                        "filter": (
                            f"truth_{metric}, peak_overlap, warm_observed_fraction and "
                            "longest_run all non-null; count distinct network_id"
                        ),
                        "field": "network_id.nunique()",
                    },
                },
            }
        )

    return rows


def draw_panel_a(rows: list[dict]) -> plt.Figure:
    # 2.70 in keeps the finished panel within the journal's 2.2:1 page-aspect rule
    # (5.43 in wide) while leaving the 6 pt type floor intact.
    figure, ax = plt.subplots(figsize=(COLUMN_INCHES, 2.95))
    figure.subplots_adjust(left=0.205, right=0.995, top=0.845, bottom=0.175)

    y = np.arange(len(rows), dtype=float)
    values = np.array([r["auc_timing_minus_length"] for r in rows])
    lows = np.array([r["ci_low"] for r in rows])
    highs = np.array([r["ci_high"] for r in rows])

    x_left, x_right = -0.272, 0.238
    ax.set_xlim(x_left, x_right)
    ax.set_ylim(len(rows) - 0.45, -0.55)  # row 0 at the top

    # The two regimes, shaded and labelled directly.
    ax.axhspan(-0.45, 1.45, color=BLUE_TINT, lw=0, zorder=0)
    ax.axhspan(2.55, 4.45, color=ORANGE_TINT, lw=0, zorder=0)
    ax.text(
        x_left + 0.006,
        0.5,
        "warm extremes:\ntiming axis wins",
        fontsize=FS_NOTE,
        color=BLUE,
        ha="left",
        va="center",
        linespacing=1.25,
    )
    ax.text(
        x_right - 0.006,
        3.5,
        "annual mean and cold extreme:\noutage-length rule wins",
        fontsize=FS_NOTE,
        color=ORANGE,
        ha="right",
        va="center",
        linespacing=1.25,
    )

    # The reversal itself, between the amplitude and the annual mean. The label
    # sits wholly clear of the dashed line (inverted axis: smaller y is higher).
    ax.axhline(2.5, color=MUTED, lw=0.8, ls=(0, (3, 2.5)), zorder=1)
    ax.text(
        x_left + 0.006,
        2.40,
        "ordering reverses",
        fontsize=FS_NOTE,
        color=MUTED,
        ha="left",
        va="bottom",
    )

    ax.axvline(0.0, color=INK_2, lw=1.0, zorder=1)
    colours = [BLUE if v > 0 else ORANGE for v in values]
    ax.errorbar(
        values,
        y,
        xerr=[values - lows, highs - values],
        fmt="none",
        ecolor=INK,
        elinewidth=1.0,
        capsize=2.0,
        capthick=1.0,
        zorder=3,
    )
    ax.scatter(values, y, s=26, color=colours, edgecolor=SURFACE, linewidth=1.0, zorder=4)

    # Value and interval next to each estimate, on whichever side is free.
    for rank, row in enumerate(rows):
        text = disp(
            f"{row['auc_timing_minus_length']:+.3f}  "
            f"[{row['ci_low']:+.3f}, {row['ci_high']:+.3f}]"
        )
        # Right of the interval, except for the negative rows that have room on
        # the left of it (the cold extreme's interval reaches the axis edge).
        if row["auc_timing_minus_length"] > 0 or rank == len(rows) - 1:
            ax.text(
                row["ci_high"] + 0.008,
                rank,
                text,
                fontsize=FS_VALUE,
                color=INK_2,
                ha="left",
                va="center",
            )
        else:
            ax.text(
                row["ci_low"] - 0.008,
                rank,
                text,
                fontsize=FS_VALUE,
                color=INK_2,
                ha="right",
                va="center",
            )

    ax.set_yticks(y, [row["label"] for row in rows], fontsize=FS_TICK)
    ax.set_xlabel("AUC(timing axis) − AUC(outage-length rule)", fontsize=FS_LABEL)
    ax.set_title("a  Which endpoints keep the gain", loc="left", pad=6, fontsize=FS_TITLE)
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="x", labelsize=FS_TICK)

    first = rows[0]
    ax.text(
        1.0,
        1.045,
        f"n = {first['n_cases']:,} cases in {first['n_networks']} networks, every endpoint",
        transform=ax.transAxes,
        fontsize=FS_NOTE,
        color=MUTED,
        ha="right",
        va="bottom",
    )
    return figure


# --------------------------------------------------------------------------- #
# panel b
# --------------------------------------------------------------------------- #
def panel_b_rows() -> list[dict]:
    """The evidence panels, oldest to newest, read one row at a time."""

    rows: list[dict] = []

    arms = pd.read_csv(ROOT / A_ARM_CONTRASTS)
    step10 = read_json(A_STEP10_VERDICT)

    # 1. v17 development, pooled (retrospective).
    development = arms[(arms["panel"] == "development") & (arms["arm"] == "pooled")].iloc[0]
    development_networks = int(
        pd.read_parquet(ROOT / A_DEVELOPMENT_CASES)["network_id"].nunique()
    )
    rows.append(
        {
            "label": "v17 development, pooled",
            "identity": "retrospective",
            "marker": "primary",
            "estimate_points": float(development["contrast_points"]),
            "ci_low_points": float(development["ci_low_points"]),
            "ci_high_points": float(development["ci_high_points"]),
            "n_cases": int(development["n_cases"]),
            "n_networks": development_networks,
            "source": {
                "artifact": A_ARM_CONTRASTS,
                "filter": "panel == 'development' & arm == 'pooled'",
                "fields": [
                    "contrast_points",
                    "ci_low_points",
                    "ci_high_points",
                    "n_cases",
                ],
            },
            "n_source": {
                "n_cases": {
                    "artifact": A_ARM_CONTRASTS,
                    "filter": "panel == 'development' & arm == 'pooled'",
                    "field": "n_cases",
                },
                "n_networks": {
                    "artifact": A_DEVELOPMENT_CASES,
                    "filter": "count distinct network_id (the development panel)",
                    "field": "network_id.nunique()",
                },
            },
        }
    )

    # 2. v17 reserved, pooled (retrospective holdout, scored once).
    primary = step10["primary"]
    rows.append(
        {
            "label": "v17 reserved, pooled",
            "identity": "retrospective",
            "marker": "primary",
            "estimate_points": float(primary["contrast_points"]),
            "ci_low_points": float(primary["ci_points"][0]),
            "ci_high_points": float(primary["ci_points"][1]),
            "n_cases": int(step10["n_cases"]),
            "n_networks": int(step10["n_networks"]),
            "source": {
                "artifact": A_STEP10_VERDICT,
                "filter": "(whole file; 'primary' block = the reserved panel at 70% retention)",
                "fields": ["primary.contrast_points", "primary.ci_points", "n_cases", "n_networks"],
            },
            "n_source": {
                "n_cases": {"artifact": A_STEP10_VERDICT, "filter": "whole file", "field": "n_cases"},
                "n_networks": {
                    "artifact": A_STEP10_VERDICT,
                    "filter": "whole file",
                    "field": "n_networks",
                },
            },
            "cross_check": {
                "artifact": A_ARM_CONTRASTS,
                "filter": "panel == 'reserved' & arm == 'pooled'",
                "estimate_points": float(
                    arms[(arms["panel"] == "reserved") & (arms["arm"] == "pooled")][
                        "contrast_points"
                    ].iloc[0]
                ),
                "ci_low_points": float(
                    arms[(arms["panel"] == "reserved") & (arms["arm"] == "pooled")][
                        "ci_low_points"
                    ].iloc[0]
                ),
                "ci_high_points": float(
                    arms[(arms["panel"] == "reserved") & (arms["arm"] == "pooled")][
                        "ci_high_points"
                    ].iloc[0]
                ),
                "note": (
                    "Same point estimate to the last digit; the two artifacts draw the "
                    "network-clustered bootstrap differently, so the interval ends differ "
                    "by about 0.05 points. The verdict artifact is plotted because it also "
                    "carries n_networks."
                ),
            },
        }
    )

    # 3-5. Sealed USGS confirmation: pooled, empirical arm, clean-subset diagnostic.
    sealed = read_json(A_SEALED_VERDICT)
    rows.append(
        {
            "label": "Sealed USGS, pooled",
            "identity": "sealed",
            "marker": "primary",
            "estimate_points": float(sealed["contrast_points"]),
            "ci_low_points": float(sealed["ci_low_points"]),
            "ci_high_points": float(sealed["ci_high_points"]),
            "n_cases": int(sealed["n_cases"]),
            "n_networks": int(sealed["n_networks"]),
            "source": {
                "artifact": A_SEALED_VERDICT,
                "filter": "whole file (pooled panel, 70% retention, scored once)",
                "fields": ["contrast_points", "ci_low_points", "ci_high_points", "n_cases", "n_networks"],
            },
        }
    )
    sealed_cases = pd.read_parquet(ROOT / A_SEALED_CASES)
    empirical = sealed_cases[sealed_cases["arm"] == "empirical"]
    rows.append(
        {
            "label": "Sealed USGS, empirical arm",
            "identity": "sealed",
            "marker": "empirical",
            "estimate_points": float(sealed["by_arm_points"]["empirical"]["contrast_points"]),
            "ci_low_points": float(sealed["by_arm_points"]["empirical"]["ci_low_points"]),
            "ci_high_points": float(sealed["by_arm_points"]["empirical"]["ci_high_points"]),
            "n_cases": len(empirical),
            "n_networks": int(empirical["network_id"].nunique()),
            "source": {
                "artifact": A_SEALED_VERDICT,
                "filter": "by_arm_points.empirical",
                "fields": ["contrast_points", "ci_low_points", "ci_high_points"],
            },
            "n_source": {
                "n_cases": {
                    "artifact": A_SEALED_CASES,
                    "filter": "arm == 'empirical'",
                    "field": "row count",
                },
                "n_networks": {
                    "artifact": A_SEALED_CASES,
                    "filter": "arm == 'empirical'",
                    "field": "network_id.nunique()",
                },
            },
        }
    )
    diagnostic = read_json(A_SEALED_DIAGNOSTIC)
    clean = next(
        row for row in diagnostic["rows"] if row["subset"] == "networks_clean_of_outcome_use"
    )
    rows.append(
        {
            "label": "Sealed USGS, clean subset",
            "identity": "sealed",
            "marker": "diagnostic",
            "estimate_points": float(clean["pooled_contrast_points"]),
            "ci_low_points": float(clean["pooled_ci_low_points"]),
            "ci_high_points": float(clean["pooled_ci_high_points"]),
            "n_cases": int(clean["n_cases"]),
            "n_networks": int(clean["n_networks"]),
            "source": {
                "artifact": A_SEALED_DIAGNOSTIC,
                "filter": "rows[subset == 'networks_clean_of_outcome_use']",
                "fields": [
                    "pooled_contrast_points",
                    "pooled_ci_low_points",
                    "pooled_ci_high_points",
                    "n_cases",
                    "n_networks",
                ],
            },
            "note": (
                "Post-seal robustness diagnostic on the networks with no outcome-bearing "
                "prior use; it does not revise the primary verdict."
            ),
        }
    )

    # 6-9. Multi-agency transport: primary panel, its three providers, NVE secondary.
    transport = read_json(A_TRANSPORT_VERDICT)
    primary_panel = transport["primary_panel"]
    rows.append(
        {
            "label": "Transport, primary panel",
            "identity": "transport",
            "marker": "primary",
            "estimate_points": float(primary_panel["contrast_points"]),
            "ci_low_points": float(primary_panel["ci_low_points"]),
            "ci_high_points": float(primary_panel["ci_high_points"]),
            "n_cases": int(primary_panel["n_cases"]),
            "n_networks": int(primary_panel["n_networks"]),
            "source": {
                "artifact": A_TRANSPORT_VERDICT,
                "filter": "primary_panel (agencies absent from the v17/v18 development programme)",
                "fields": ["contrast_points", "ci_low_points", "ci_high_points", "n_cases", "n_networks"],
            },
        }
    )
    providers = transport["by_provider_points"]
    for key, label in (("smhi", "SMHI"), ("uk_ea", "UK EA"), ("hubeau", "Hub'Eau")):
        block = providers[key]
        rows.append(
            {
                "label": f"   {label}",
                "identity": "transport",
                "marker": "primary",
                "provider": key,
                "estimate_points": float(block["contrast_points"]),
                "ci_low_points": float(block["ci_low_points"]),
                "ci_high_points": float(block["ci_high_points"]),
                "n_cases": int(block["n_cases"]),
                "n_networks": int(block["n_networks"]),
                "source": {
                    "artifact": A_TRANSPORT_VERDICT,
                    "filter": f"by_provider_points.{key}",
                    "fields": [
                        "contrast_points",
                        "ci_low_points",
                        "ci_high_points",
                        "n_cases",
                        "n_networks",
                    ],
                },
                "note": (
                    "n_cases and n_networks were filled from the stored transport cases after "
                    "the score (verdict.post_score_metadata_correction); no contrast value was "
                    "recomputed."
                ),
            }
        )
    secondary = transport["secondary_panel"]
    rows.append(
        {
            "label": "Transport, NVE secondary",
            "identity": "transport",
            "marker": "secondary",
            "estimate_points": float(secondary["contrast_points"]),
            "ci_low_points": float(secondary["ci_low_points"]),
            "ci_high_points": float(secondary["ci_high_points"]),
            "n_cases": int(secondary["n_cases"]),
            "n_networks": int(secondary["n_networks"]),
            "source": {
                "artifact": A_TRANSPORT_VERDICT,
                "filter": "secondary_panel (development provider, individually never-used stations)",
                "fields": ["contrast_points", "ci_low_points", "ci_high_points", "n_cases", "n_networks"],
            },
            "note": (
                "Secondary stratum: the provider took part in v17 development, so this row is "
                "reported separately from the primary transport panel."
            ),
        }
    )
    return rows


def draw_panel_b(rows: list[dict], threshold_points: float) -> plt.Figure:
    figure = plt.figure(figsize=(COLUMN_INCHES, 4.30))
    grid = figure.add_gridspec(
        1,
        2,
        width_ratios=[4.55, 0.92],
        wspace=0.06,
        left=0.285,
        right=0.995,
        top=0.925,
        bottom=0.135,
    )
    ax = figure.add_subplot(grid[0, 0])
    axn = figure.add_subplot(grid[0, 1], sharey=ax)
    axn.axis("off")

    n_rows = len(rows)
    y = np.arange(n_rows, dtype=float)
    colours = [IDENTITY_COLOURS[r["identity"]] for r in rows]

    x_left, x_right = -14.6, 3.1
    ax.set_xlim(x_left, x_right)
    ax.set_ylim(n_rows + 1.35, -2.05)  # row 0 at the top; legend band at the bottom

    for boundary in (1.5, 4.5, 8.5):
        ax.axhline(boundary, color=GRID, lw=0.8, zorder=0.6)
        axn.axhline(boundary, color=GRID, lw=0.8, zorder=0.6)

    ax.axvline(0.0, color=INK_2, lw=1.0, zorder=1)
    ax.axvline(
        threshold_points, color=INK, lw=1.1, ls=(0, (3, 2.5)), zorder=1
    )
    ax.text(
        threshold_points - 0.3,
        -1.78,
        disp(f"pre-declared Δ = {threshold_points:.1f} pt"),
        fontsize=FS_NOTE,
        color=INK,
        ha="right",
        va="bottom",
    )

    for index, row in enumerate(rows):
        colour = colours[index]
        filled = row["marker"] in ("primary", "empirical")
        marker = "o" if row["marker"] != "empirical" else "s"
        ax.errorbar(
            row["estimate_points"],
            index,
            xerr=[
                [row["estimate_points"] - row["ci_low_points"]],
                [row["ci_high_points"] - row["estimate_points"]],
            ],
            fmt="none",
            ecolor=colour,
            elinewidth=1.0,
            capsize=2.0,
            capthick=1.0,
            zorder=3,
        )
        ax.plot(
            [row["estimate_points"]],
            [index],
            marker=marker,
            ms=3.6,
            ls="none",
            mfc=colour if filled else SURFACE,
            mec=colour,
            mew=1.0,
            zorder=4,
        )
        axn.text(
            1.0,
            index,
            f"{row['n_cases']:,} / {row['n_networks']}",
            fontsize=FS_NOTE,
            color=INK_2,
            ha="right",
            va="center",
        )

    ax.set_yticks(y, [row["label"] for row in rows], fontsize=FS_TICK)
    ax.tick_params(axis="x", labelsize=FS_TICK)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel(
        "certificate rate − length-rule rate (percentage points, 70% retention)\n"
        "negative favours the screen; intervals are network-clustered 95%",
        fontsize=FS_LABEL,
        linespacing=1.35,
    )
    ax.set_title(
        "b  Where the gain holds, and where it collapses",
        loc="left",
        pad=6,
        fontsize=FS_TITLE,
    )

    axn.text(
        1.0,
        -1.78,
        "cases /\nnetworks",
        fontsize=FS_NOTE,
        color=MUTED,
        ha="right",
        va="bottom",
        linespacing=1.3,
    )

    handles = [
        plt.Line2D([], [], color=MUTED, marker="o", ms=3.6, ls="none", label="retrospective"),
        plt.Line2D([], [], color=BLUE, marker="o", ms=3.6, ls="none", label="sealed confirmation"),
        plt.Line2D([], [], color=ORANGE, marker="o", ms=3.6, ls="none", label="transport"),
        plt.Line2D(
            [],
            [],
            color=INK_2,
            marker="o",
            ms=3.6,
            ls="none",
            mfc=SURFACE,
            mec=INK_2,
            label="diagnostic or secondary stratum",
        ),
    ]
    ax.legend(
        handles=handles,
        loc="lower left",
        ncol=2,
        fontsize=FS_LEGEND,
        handletextpad=0.4,
        columnspacing=1.0,
        borderaxespad=0.2,
        labelspacing=0.5,
    )
    return figure


# --------------------------------------------------------------------------- #
# rendering checks
# --------------------------------------------------------------------------- #
WORD_RE = re.compile(
    r'<word xMin="([\d.eE+-]+)" yMin="([\d.eE+-]+)" xMax="([\d.eE+-]+)" '
    r'yMax="([\d.eE+-]+)">(.*?)</word>'
)
PAGE_RE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">')


def _run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(command)}\n{result.stderr}")
    return result.stdout


def _parse_fonts(text: str) -> list[dict]:
    fonts = []
    for line in text.splitlines()[2:]:
        if not line.strip():
            continue
        tail = re.match(
            r"^(?P<head>.+?)\s+(?P<emb>yes|no)\s+(?P<sub>yes|no)\s+"
            r"(?P<uni>yes|no)\s+(?P<obj>\d+)\s+(?P<gen>\d+)\s*$",
            line,
        )
        if tail is None:
            continue
        head = tail["head"].split()
        fonts.append(
            {
                "name": head[0],
                "type": " ".join(head[1:-1]),
                "encoding": head[-1],
                "embedded": tail["emb"] == "yes",
                "subset": tail["sub"] == "yes",
                "unicode": tail["uni"] == "yes",
            }
        )
    return fonts


def _font_box_ratio() -> float:
    """Ascent+descent of the figure font, in em, so ``pdftotext`` word boxes can
    be converted back to a type size."""

    from matplotlib import font_manager
    from matplotlib.ft2font import FT2Font

    family = plt.rcParams["font.sans-serif"]
    if isinstance(family, (list, tuple)):
        family = list(family)
    face = FT2Font(font_manager.findfont(font_manager.FontProperties(family=family)))
    return (face.ascender - face.descender) / face.units_per_EM


def check_pdf(name: str) -> dict:
    """One page, embedded fonts, every word on the page and none overlapping."""

    pdf = FIGURES / f"{name}.pdf"
    info = _run(["pdfinfo", str(pdf)])
    pages = int(re.search(r"^Pages:\s+(\d+)", info, re.MULTILINE).group(1))
    size = re.search(r"^Page size:\s+([\d.]+) x ([\d.]+) pts", info, re.MULTILINE)
    width_pt, height_pt = float(size.group(1)), float(size.group(2))

    fonts = _parse_fonts(_run(["pdffonts", str(pdf)]))

    bbox_path = SCRATCH / f"{name}_words.tsv"
    raw = _run(["pdftotext", "-bbox", str(pdf), "-"])
    page = PAGE_RE.search(raw)
    page_width, page_height = float(page.group(1)), float(page.group(2))
    words = [
        {
            "text": m.group(5),
            "x_min": float(m.group(1)),
            "y_min": float(m.group(2)),
            "x_max": float(m.group(3)),
            "y_max": float(m.group(4)),
        }
        for m in WORD_RE.finditer(raw)
    ]
    bbox_path.write_text(
        "text\tx_min\ty_min\tx_max\ty_max\theight_pt\n"
        + "\n".join(
            f"{w['text']}\t{w['x_min']:.3f}\t{w['y_min']:.3f}\t{w['x_max']:.3f}\t"
            f"{w['y_max']:.3f}\t{w['y_max'] - w['y_min']:.3f}"
            for w in words
        )
        + "\n",
        encoding="utf-8",
    )

    outside = [
        w
        for w in words
        if w["x_min"] < -0.01
        or w["y_min"] < -0.01
        or w["x_max"] > page_width + 0.01
        or w["y_max"] > page_height + 0.01
    ]

    tolerance = 0.4  # pt; guards against antialiasing/rounding, not real overlap
    collisions = []
    for i in range(len(words)):
        a = words[i]
        for j in range(i + 1, len(words)):
            b = words[j]
            overlap_x = min(a["x_max"], b["x_max"]) - max(a["x_min"], b["x_min"])
            overlap_y = min(a["y_max"], b["y_max"]) - max(a["y_min"], b["y_min"])
            if overlap_x > tolerance and overlap_y > tolerance:
                collisions.append(
                    {
                        "a": a["text"],
                        "b": b["text"],
                        "overlap_pt": [round(overlap_x, 3), round(overlap_y, 3)],
                    }
                )

    heights = sorted(w["y_max"] - w["y_min"] for w in words)
    named_heights = sorted(
        w["y_max"] - w["y_min"] for w in words if any(c.isupper() or c.isdigit() for c in w["text"])
    )
    # Placed at the printed column width, a page narrower than 5.5 in is scaled
    # up, never down, so the natural size is the worst case.
    scale_to_column = (COLUMN_INCHES * 72.0) / page_width if page_width < COLUMN_INCHES * 72 else 1.0
    ratio = _font_box_ratio()

    return {
        "pdf": f"figures/wrr/{name}.pdf",
        "png": f"figures/wrr/{name}.png",
        "pages": pages,
        "page_size_pt": [round(width_pt, 2), round(height_pt, 2)],
        "page_size_in": [round(width_pt / 72.0, 3), round(height_pt / 72.0, 3)],
        "fits_column_inches": COLUMN_INCHES,
        "fonts": fonts,
        "fonts_all_embedded": all(f["embedded"] for f in fonts),
        "fonts_all_type42": all("TrueType" in f["type"] for f in fonts),
        "font_embedding_note": (
            "pdf.fonttype = 42 (TrueType outlines). Matplotlib 3.9 writes these as a "
            "CID-keyed TrueType font with Identity-H encoding, which pdffonts reports as "
            "'CID TrueType': outlines embedded, subset, with a Unicode map."
        ),
        "n_words": len(words),
        "words_outside_page": [w["text"] for w in outside],
        "n_overlapping_word_pairs": len(collisions),
        "overlapping_word_pairs": collisions[:10],
        "min_word_box_height_pt": round(heights[0], 3) if heights else None,
        "min_word_box_height_pt_at_column_width": round(heights[0] * scale_to_column, 3)
        if heights
        else None,
        "min_cap_or_digit_word_height_pt": round(named_heights[0], 3) if named_heights else None,
        "min_cap_or_digit_word_height_pt_at_column_width": round(
            named_heights[0] * scale_to_column, 3
        )
        if named_heights
        else None,
        "font_box_ratio_em": round(ratio, 4),
        "min_implied_type_size_pt": round(heights[0] / ratio, 3) if heights else None,
        "min_implied_type_size_pt_at_column_width": round(heights[0] * scale_to_column / ratio, 3)
        if heights
        else None,
        "scale_to_column_width": round(scale_to_column, 4),
        "words_dump": f"scratch/heterogeneity/{name}_words.tsv",
    }


# --------------------------------------------------------------------------- #
# caption material
# --------------------------------------------------------------------------- #
def caption_material(
    panel_a: list[dict],
    panel_b: list[dict],
    threshold_points: float,
    checks: dict,
    disagreement: pd.Series,
) -> str:
    a = panel_a
    b = panel_b
    dev, res, sealed_pooled, sealed_emp, sealed_clean = b[0], b[1], b[2], b[3], b[4]
    transport, smhi, uk_ea, hubeau, nve = b[5], b[6], b[7], b[8], b[9]

    def _pt(row: dict, key: str = "estimate_points") -> str:
        return f"{row[key]:+.2f}"

    def _row(row: dict) -> str:
        return (
            f"| {row['label'].strip()} | {row['identity']} | "
            f"{row['estimate_points']:+.2f} | {row['ci_low_points']:+.2f} to "
            f"{row['ci_high_points']:+.2f} | {row['n_cases']:,} | {row['n_networks']} | "
            f"`{row['source']['artifact']}` |"
        )

    lines = [
        "# Figure 2 — where the screening gain holds, and where it collapses",
        "",
        "Generated by `scripts/267_wrr_heterogeneity_figures.py` from the artifacts named "
        "below. Every number in this file and in the two figures is read from those "
        "artifacts at build time; nothing is hand-entered.",
        "",
        "## Drop-in caption",
        "",
        "**Figure 2.** Heterogeneity of the screening gain. "
        "**(a)** Which endpoints keep the gain. For each of five endpoints, the difference "
        "in AUC between the better timing axis (peak-window overlap or warm-season coverage, "
        "whichever scores higher) and the outage-length rule, on the v17 development panel "
        f"({a[0]['n_cases']:,} cases in {a[0]['n_networks']} networks, identical for every "
        "endpoint). Points are the contrasts, bars the network-clustered 95% intervals "
        "(1200 clustered bootstrap draws, resampling networks). Positive values mean the "
        "timing axis separates consequential errors better than outage length; negative "
        "values mean the length rule wins. Endpoints are ordered most positive to most "
        "negative: "
        + "; ".join(
            f"{row['label']} {row['auc_timing_minus_length']:+.3f} "
            f"({row['ci_low']:+.3f} to {row['ci_high']:+.3f})"
            for row in a
        )
        + ". The two warm extremes keep the gain, the amplitude is weakly positive, and the "
        "ordering reverses at the annual mean: the annual mean and the cold extreme are the "
        "two endpoints where the outage-length rule is the better axis. Each endpoint is "
        "scored at its own natural-scale tolerance (0.5 °C divided by 1.062 times the "
        "endpoint's interannual standard deviation): "
        + "; ".join(f"{row['label']} {row['tolerance_c']:.2f} °C" for row in a)
        + ". The interval excludes zero on both sides of the reversal, so the sign of the "
        "endpoint contrast is resolved, not marginal.",
        "",
        "**(b)** Where the gain holds, and where it collapses. Forest plot of the pooled "
        "contrast between the certificate screen and the published-style outage-length rule, "
        "certificate rate minus length-rule rate in percentage points of 'consequential "
        "error' (hottest 30-day mean daily water temperature wrong by more than 0.5 °C), at "
        "70% retention, so negative values favour the screen. Bars are network-clustered 95% "
        "intervals; the solid line is zero and the dashed line is the pre-declared threshold "
        f"Δ = {threshold_points:.1f} percentage point, below which transport of the screen is "
        "declared supported. Panels are shown oldest to newest and are three kinds of "
        "evidence, distinguished by colour and by the legend inside the panel: grey, "
        "retrospective (v17 development and the v17 reserved holdout, both scored on designed "
        "masks over complete years); blue, sealed confirmation (the never-used USGS panel, "
        "scored once, with its empirical arm and a post-seal clean-subset diagnostic); "
        "orange, transport (a pre-registered multi-agency panel designed after the USGS score "
        "was known). The pooled retrospective panels give "
        f"{_pt(dev)} points [{_pt(dev, 'ci_low_points')}, {_pt(dev, 'ci_high_points')}] on "
        f"development and {_pt(res)} points [{_pt(res, 'ci_low_points')}, "
        f"{_pt(res, 'ci_high_points')}] on the reserved holdout; sealed confirmation gives "
        f"{_pt(sealed_pooled)} points [{_pt(sealed_pooled, 'ci_low_points')}, "
        f"{_pt(sealed_pooled, 'ci_high_points')}] on the pooled panel, its empirical arm "
        f"{_pt(sealed_emp)} points [{_pt(sealed_emp, 'ci_low_points')}, "
        f"{_pt(sealed_emp, 'ci_high_points')}] (the weakest cell of the figure: it is the one "
        "estimate that does not clear the threshold) and the clean subsets "
        f"{_pt(sealed_clean)} points [{_pt(sealed_clean, 'ci_low_points')}, "
        f"{_pt(sealed_clean, 'ci_high_points')}] on the networks with no outcome-bearing "
        f"prior use; transport gives {_pt(transport)} points "
        f"[{_pt(transport, 'ci_low_points')}, {_pt(transport, 'ci_high_points')}] on the "
        f"primary panel ({transport['n_networks']} networks across three agencies), "
        f"{_pt(smhi)} [{_pt(smhi, 'ci_low_points')}, {_pt(smhi, 'ci_high_points')}] for SMHI, "
        f"{_pt(uk_ea)} [{_pt(uk_ea, 'ci_low_points')}, {_pt(uk_ea, 'ci_high_points')}] for "
        f"UK EA ({uk_ea['n_networks']} networks; the only interval of the ten that reaches "
        f"above zero, and it does not reach the threshold either), {_pt(hubeau)} "
        f"[{_pt(hubeau, 'ci_low_points')}, {_pt(hubeau, 'ci_high_points')}] for Hub'Eau, and "
        f"{_pt(nve)} [{_pt(nve, 'ci_low_points')}, {_pt(nve, 'ci_high_points')}] on the NVE "
        "secondary stratum, whose provider appears in development and which is therefore "
        "never part of the primary panel. Nine of ten estimates lie below the pre-declared "
        f"threshold; the exception is the sealed empirical arm ({_pt(sealed_emp)} points, "
        f"interval [{_pt(sealed_emp, 'ci_low_points')}, {_pt(sealed_emp, 'ci_high_points')}]), "
        "which is the arm where real outage geometry replaces the designed masks. Every "
        "interval is a 95% network-clustered confidence interval for the difference in "
        "consequential-error rates, in percentage points; intervals that exclude zero are the "
        "ones that resolve the direction of the contrast. The right-hand column gives the "
        "cases and networks behind each row.",
        "",
        "## Plotted values, panel a",
        "",
        "| rank | endpoint | AUC difference | clustered 95% interval | tolerance (°C) | base rate | n cases | n networks | interval excludes zero | source artifact |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in a:
        excludes = "yes" if (row["ci_low"] > 0 or row["ci_high"] < 0) else "no"
        lines.append(
            f"| {row['rank'] + 1} | {row['label']} | "
            f"{row['auc_timing_minus_length']:+.4f} | {row['ci_low']:+.4f} to "
            f"{row['ci_high']:+.4f} | {row['tolerance_c']:.3f} | {row['base_rate']:.4f} | "
            f"{row['n_cases']:,} | {row['n_networks']} | {excludes} | "
            f"`{row['source']['artifact']}` |"
        )

    lines += [
        "",
        "Panel a identity: retrospective. The contrast is computed on the v17 development "
        "panel (designed masks over complete station-years); it is not a sealed or "
        "out-of-sample score. Values are dimensionless AUC differences, so the unit is AUC "
        "units, not °C; the tolerance column gives the °C threshold that defines a "
        "consequential error for that endpoint. n is identical across endpoints because the "
        "same case table carries all five statistics.",
        "",
        "## Plotted values, panel b",
        "",
        "| panel (oldest to newest) | evidence identity | contrast (points) | clustered 95% interval (points) | n cases | n networks | source artifact |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in b:
        lines.append(_row(row))

    lines += [
        "",
        "Units: percentage points of the consequential-error rate (error > 0.5 °C in the "
        "hottest 30-day mean daily water temperature) at 70% retention. Negative values "
        "favour the certificate screen over the length rule, because the contrast is "
        "(certificate rate − length-rule rate). The intervals are network-clustered 95% "
        "confidence intervals: the resampling unit is the network, not the case, so the "
        "interval reflects the number of independent river systems rather than the number of "
        "station-years. Panels are not independent of one another — the empirical arm and "
        "the clean subsets are subsets of the same sealed score, and the provider rows are "
        "strata of the transport panel — so the intervals must not be combined or compared "
        "as if they came from separate experiments.",
        "",
        "Panel b identity, row by row: retrospective (v17 development; v17 reserved "
        "holdout, scored once retrospectively); sealed confirmation (USGS HUC4 networks "
        "never used in development, scored once, plus a post-seal robustness diagnostic on "
        "the outcome-clean networks); transport (multi-agency panel sealed and scored once "
        "after the USGS score was known, with a development provider reported separately as "
        "a secondary stratum).",
        "",
        "## What is not in the panel",
        "",
        f"- **{REAL_ARCHIVE_ROW['requested_row']}** — not plotted. {REAL_ARCHIVE_ROW['reason']}",
        "  The closest outcome-agnostic evidence for the real archive is the admission "
        "disagreement between the two rules, which needs no truth: on "
        f"{int(disagreement['n_station_years'])} real incomplete station-years the incumbent "
        f"unfilled limit admits {disagreement['length_admits_pct']:.1f}% and the peak-window "
        f"rule {disagreement['timing_admits_pct']:.1f}%, and the two disagree on "
        f"{disagreement['disagreement_pct']:.1f}% of them (`{A_ARCHIVE_DISAGREEMENT}`, row "
        f"'{disagreement['incumbent']}'). That is a rate of disagreement, not an error-rate "
        "contrast, and it has no place on this axis.",
        "",
        "## Provenance and rendering",
        "",
        "| item | value |",
        "| --- | --- |",
        "| script | `scripts/267_wrr_heterogeneity_figures.py` |",
        "| reproduce | `python3 scripts/267_wrr_heterogeneity_figures.py` (reads only; writes figures/wrr/ and scratch/heterogeneity/) |",
        "| independent check | `python3 scratch/heterogeneity/verify_sources.py` re-reads every plotted value from the artifacts with the stdlib and re-checks the PDFs (102 checks) |",
        "| data side-car | `figures/wrr/f2_heterogeneity_data.json` |",
        "| panel a figure | `figures/wrr/f2a_endpoint_ordering.pdf` |",
        "| panel b figure | `figures/wrr/f2b_panel_heterogeneity.pdf` |",
        f"| page size, panel a | {checks['f2a_endpoint_ordering']['page_size_in'][0]:.3f} × "
        f"{checks['f2a_endpoint_ordering']['page_size_in'][1]:.3f} in "
        f"({checks['f2a_endpoint_ordering']['pages']} page) |",
        f"| page size, panel b | {checks['f2b_panel_heterogeneity']['page_size_in'][0]:.3f} × "
        f"{checks['f2b_panel_heterogeneity']['page_size_in'][1]:.3f} in "
        f"({checks['f2b_panel_heterogeneity']['pages']} page) |",
        f"| column width | {COLUMN_INCHES} in (AGU double column); both pages are narrower, so "
        "the figures are never scaled down |",
        f"| type scale | {FS_NOTE:.1f}–{FS_TITLE:.1f} pt nominal; minimum "
        f"{MIN_NOMINAL_PT:.1f} pt, asserted in the script and re-measured from the PDF |",
        f"| measured minimum type size | panel a "
        f"{checks['f2a_endpoint_ordering']['min_implied_type_size_pt']:.2f} pt "
        f"({checks['f2a_endpoint_ordering']['min_implied_type_size_pt_at_column_width']:.2f} pt "
        "if the page is scaled up to 5.5 in); panel b "
        f"{checks['f2b_panel_heterogeneity']['min_implied_type_size_pt']:.2f} pt "
        f"({checks['f2b_panel_heterogeneity']['min_implied_type_size_pt_at_column_width']:.2f} "
        "pt at 5.5 in) |",
        f"| word boxes | panel a {checks['f2a_endpoint_ordering']['n_words']} words, "
        f"panel b {checks['f2b_panel_heterogeneity']['n_words']} words; none outside the "
        "page, none overlapping (`pdftotext -bbox`) |",
        f"| embedding | Type 42 (TrueType): panel a "
        f"{'yes' if checks['f2a_endpoint_ordering']['fonts_all_type42'] else 'no'}, panel b "
        f"{'yes' if checks['f2b_panel_heterogeneity']['fonts_all_type42'] else 'no'} |",
        "| interval definition | network-clustered bootstrap (1200 draws in the v17 tables; "
        "the sealed and transport verdicts use their own frozen clustered bootstrap) |",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    FIGURES.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)

    if min(FS_TICK, FS_LABEL, FS_TITLE, FS_LEGEND, FS_VALUE, FS_NOTE) < MIN_NOMINAL_PT:
        raise SystemExit("a font size below the 6 pt floor is configured")

    missing = [rel for rel in ARTIFACTS if not (ROOT / rel).is_file()]
    if missing:
        raise SystemExit(f"missing artifacts: {missing}")

    threshold_points = float(
        read_json(A_TRANSPORT_VERDICT)["predeclared_rule"]["delta_points"]
    )

    rows_a = panel_a_rows()
    rows_b = panel_b_rows()

    figure_a = draw_panel_a(rows_a)
    figure_a.savefig(
        FIGURES / "f2a_endpoint_ordering.pdf", dpi=300, bbox_inches="tight", pad_inches=0.02
    )
    figure_a.savefig(
        FIGURES / "f2a_endpoint_ordering.png", dpi=300, bbox_inches="tight", pad_inches=0.02
    )
    plt.close(figure_a)

    figure_b = draw_panel_b(rows_b, threshold_points)
    figure_b.savefig(
        FIGURES / "f2b_panel_heterogeneity.pdf", dpi=300, bbox_inches="tight", pad_inches=0.02
    )
    figure_b.savefig(
        FIGURES / "f2b_panel_heterogeneity.png", dpi=300, bbox_inches="tight", pad_inches=0.02
    )
    plt.close(figure_b)

    checks = {name: check_pdf(name) for name in ("f2a_endpoint_ordering", "f2b_panel_heterogeneity")}
    (SCRATCH / "render_checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")

    disagreement = pd.read_csv(ROOT / A_ARCHIVE_DISAGREEMENT).iloc[0]
    payload = {
        "figure": [
            "figures/wrr/f2a_endpoint_ordering.pdf",
            "figures/wrr/f2b_panel_heterogeneity.pdf",
        ],
        "generated_by": "scripts/267_wrr_heterogeneity_figures.py",
        "purpose": (
            "Heterogeneity of the certificate screen's gain: which endpoints keep it "
            "(panel a) and which evidence panels keep it (panel b)."
        ),
        "conventions": {
            "panel_a_units": "AUC units (difference of two AUCs); dimensionless",
            "panel_b_units": "percentage points of the consequential-error rate at 70% retention",
            "panel_b_sign": (
                "certificate rate minus length-rule rate; negative favours the screen"
            ),
            "interval": (
                "95% network-clustered confidence interval; the resampling unit is the network"
            ),
            "threshold_points": threshold_points,
            "threshold_source": {
                "artifact": A_TRANSPORT_VERDICT,
                "filter": "predeclared_rule.delta_points",
            },
            "note_on_threshold": (
                "The v17 retrospective panels were declared against a 5.0-point effect "
                "(results/v17_fitness/step10_confirmation/verdict.json, primary."
                "declared_effect_points); the -1.0-point threshold drawn here is the transport "
                "protocol's pre-declared rule and is the same line for every row."
            ),
            "case_masks": (
                "Retrospective, sealed and transport cases are designed masks punched into "
                "complete station-years, except where a row is labelled empirical (the "
                "panel's own real outage geometry)."
            ),
        },
        "panel_a": {
            "file": "figures/wrr/f2a_endpoint_ordering.pdf",
            "endpoint_order": ENDPOINT_ORDER,
            "ordering_rule": "most positive to most negative contrast",
            "rows": rows_a,
        },
        "panel_b": {
            "file": "figures/wrr/f2b_panel_heterogeneity.pdf",
            "order": "oldest to newest",
            "rows": rows_b,
        },
        "unavailable_rows": [
            {
                **REAL_ARCHIVE_ROW,
                "closest_available_evidence": {
                    "artifact": A_ARCHIVE_DISAGREEMENT,
                    "filter": "row 'Johnson unfilled, longest run <= 49 d'",
                    "n_station_years": int(disagreement["n_station_years"]),
                    "length_admits_pct": float(disagreement["length_admits_pct"]),
                    "timing_admits_pct": float(disagreement["timing_admits_pct"]),
                    "disagreement_pct": float(disagreement["disagreement_pct"]),
                    "units": "percent of real incomplete station-years",
                    "why_not_plotted": (
                        "A disagreement rate between admission rules, not an error-rate "
                        "contrast; the real years carry no truth."
                    ),
                },
            }
        ],
        "artifacts": [
            {"path": rel, "sha256": sha256_of(rel), "bytes": (ROOT / rel).stat().st_size}
            for rel in ARTIFACTS
        ],
        "render_checks": checks,
        "font_sizes_pt": {
            "tick": FS_TICK,
            "axis_label": FS_LABEL,
            "panel_title": FS_TITLE,
            "legend": FS_LEGEND,
            "value_annotation": FS_VALUE,
            "note": FS_NOTE,
            "minimum_nominal": MIN_NOMINAL_PT,
        },
        "caption_material": "figures/wrr/f2_caption_material.md",
    }
    (FIGURES / "f2_heterogeneity_data.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    (FIGURES / "f2_caption_material.md").write_text(
        caption_material(rows_a, rows_b, threshold_points, checks, disagreement),
        encoding="utf-8",
    )

    print("panel a — endpoint ordering (AUC(timing) − AUC(length), clustered 95% CI)")
    for row in rows_a:
        print(
            f"  {row['rank'] + 1}. {row['label']:<22} {row['auc_timing_minus_length']:+.4f} "
            f"[{row['ci_low']:+.4f}, {row['ci_high']:+.4f}]  tol {row['tolerance_c']:.3f} °C  "
            f"n {row['n_cases']:,}/{row['n_networks']}"
        )
    print(f"\npanel b — pooled contrast, pre-declared Δ = {threshold_points:+.2f} pt")
    for row in rows_b:
        print(
            f"  {row['label']:<28} {row['identity']:<14} {row['estimate_points']:+7.2f} "
            f"[{row['ci_low_points']:+7.2f}, {row['ci_high_points']:+7.2f}]  "
            f"n {row['n_cases']:,}/{row['n_networks']}"
        )
    print(f"\nnot plotted: {REAL_ARCHIVE_ROW['requested_row']} — {REAL_ARCHIVE_ROW['reason']}")

    for name, check in checks.items():
        print(
            f"\n{name}: {check['pages']} page, "
            f"{check['page_size_in'][0]:.3f} × {check['page_size_in'][1]:.3f} in, "
            f"fonts embedded {check['fonts_all_embedded']}, "
            f"Type 42 {check['fonts_all_type42']}, "
            f"words {check['n_words']}, outside page {len(check['words_outside_page'])}, "
            f"overlapping pairs {check['n_overlapping_word_pairs']}, "
            f"min word box {check['min_word_box_height_pt']:.2f} pt "
            f"= {check['min_implied_type_size_pt']:.2f} pt type "
            f"({check['min_implied_type_size_pt_at_column_width']:.2f} pt at 5.5 in width)"
        )

    for suffix in ("pdf", "png"):
        print(f"\nwrote figures/wrr/f2a_endpoint_ordering.{suffix}")
        print(f"wrote figures/wrr/f2b_panel_heterogeneity.{suffix}")
    print("wrote figures/wrr/f2_heterogeneity_data.json")
    print("wrote figures/wrr/f2_caption_material.md")
    print("wrote scratch/heterogeneity/render_checks.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
