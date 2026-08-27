#!/usr/bin/env python3
"""Numerical Prop 3 bias-term figure on synthetic VAR(1) systems (T1 support)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.analysis.heuristic_bias import heuristic_bias_table

OUTPUT = ROOT / "results/framework/theory_v1"
FIGURE = OUTPUT / "prop3_bias_terms_synthetic.png"
TABLE = OUTPUT / "prop3_bias_terms_synthetic.csv"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame = heuristic_bias_table(gap_lengths=(14, 30, 90, 180))
    frame.to_csv(TABLE, index=False)
    pivot = frame.pivot_table(
        index="river",
        columns="gap_length",
        values=["epsilon_d_over_4", "epsilon_perp", "old_minus_new"],
        aggfunc="first",
    )
    systems = sorted(frame["river"].unique())
    gaps = sorted(frame["gap_length"].unique())
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), sharex=True)
    for ax, term, title in zip(
        axes,
        ("epsilon_d_over_4", "epsilon_perp", "old_minus_new"),
        (r"$\varepsilon_{d/4}$", r"$\varepsilon_\perp$", "old − new"),
        strict=False,
    ):
        for river in systems:
            piece = frame.loc[frame["river"].eq(river)].sort_values("gap_length")
            ax.plot(
                piece["gap_length"],
                piece[term],
                marker="o",
                label=river,
            )
        ax.axhline(0.0, color="0.7", linewidth=0.8)
        ax.set_title(title)
        ax.set_xlabel("gap length (days)")
    axes[0].set_ylabel("explained-variance remainder")
    axes[0].legend(fontsize=6, ncol=2, loc="best")
    fig.suptitle("Prop 3 named remainders on known VAR(1) systems (not river evidence)")
    fig.tight_layout()
    fig.savefig(FIGURE, dpi=160)
    manifest = {
        "figure": str(FIGURE.relative_to(ROOT)),
        "table": str(TABLE.relative_to(ROOT)),
        "n_rows": int(len(frame)),
        "systems": systems,
        "gap_lengths": gaps,
        "purpose": "t1_prop3_numerical_support_not_confirmatory",
        "formal_evidence": False,
        "pivot_columns": [str(item) for item in pivot.columns],
    }
    (OUTPUT / "prop3_bias_terms_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
