#!/usr/bin/env python3
"""Three-box graphical abstract for the EMS manuscript.

The page is built at 5.2 cm width so the labels remain legible when the
graphic is displayed at the 5 cm width used by the journal.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent


def box(
    fig: plt.Figure,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    face: str,
    edge: str,
) -> None:
    fig.patches.append(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.008,rounding_size=0.018",
            transform=fig.transFigure,
            facecolor=face,
            edgecolor=edge,
            linewidth=0.9,
            zorder=2,
        )
    )
    fig.text(
        x + w / 2,
        y + h / 2,
        title,
        ha="center",
        va="center",
        fontsize=7.0,
        fontweight="semibold",
        color="#1f2933",
        zorder=3,
    )


def main() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "figure.facecolor": "white",
        }
    )
    fig = plt.figure(figsize=(5.2 / 2.54, 6.2 / 2.54))
    fig.text(
        0.5,
        0.945,
        "Gap handling for trend decisions",
        ha="center",
        va="center",
        fontsize=7.2,
        fontweight="bold",
        color="#1f2933",
    )

    x, w, h = 0.055, 0.89, 0.145
    rows = [
        (0.735, "Incomplete archive", "#dbe9f2", "#2b6f9e"),
        (0.535, "Joint mask + recovery", "#f6e3d3", "#c85b1b"),
        (0.335, "Trend decision", "#dcefe3", "#2f855a"),
    ]
    for y, label, face, edge in rows:
        box(fig, x, y, w, h, label, face, edge)

    for y0, y1 in [(0.727, 0.690), (0.527, 0.490)]:
        fig.patches.append(
            FancyArrowPatch(
                (0.5, y0),
                (0.5, y1),
                transform=fig.transFigure,
                arrowstyle="-|>",
                mutation_scale=7.5,
                linewidth=0.9,
                color="#4a4a4a",
                zorder=3,
            )
        )

    fig.patches.append(
        FancyBboxPatch(
            (0.045, 0.095),
            0.91,
            0.195,
            boxstyle="round,pad=0.008,rounding_size=0.012",
            transform=fig.transFigure,
            facecolor="#f4f4f2",
            edgecolor="#c8c8c4",
            linewidth=0.5,
            zorder=1,
        )
    )
    fig.text(
        0.5,
        0.235,
        "Severe: recover 0.446 \u2192 0.170",
        ha="center",
        va="center",
        fontsize=5.9,
        fontweight="semibold",
        color="#8a3b10",
    )
    fig.text(
        0.5,
        0.168,
        "Typical: gap < trend uncertainty",
        ha="center",
        va="center",
        fontsize=5.9,
        color="#1f2933",
    )

    fig.patches.append(
        FancyBboxPatch(
            (0.365, 0.012),
            0.27,
            0.055,
            boxstyle="round,pad=0.004,rounding_size=0.008",
            transform=fig.transFigure,
            facecolor="#1f2933",
            edgecolor="#1f2933",
            linewidth=0.4,
            zorder=2,
        )
    )
    fig.text(
        0.5,
        0.039,
        "gapbench",
        ha="center",
        va="center",
        fontsize=6.6,
        fontweight="bold",
        color="white",
        zorder=3,
    )

    fig.savefig(OUT / "graphical_abstract.pdf", bbox_inches="tight", pad_inches=0.04)
    fig.savefig(
        OUT / "graphical_abstract.png",
        dpi=600,
        bbox_inches="tight",
        pad_inches=0.01,
    )
    plt.close(fig)


if __name__ == "__main__":
    main()
