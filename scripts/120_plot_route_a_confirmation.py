#!/usr/bin/env python3
"""Render Route A confirmation calibration, domain, and triage figures."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/development_v11/route_a_confirmation"


def scatter(axis: plt.Axes, frame: pd.DataFrame, title: str) -> None:
    axis.scatter(
        frame["predicted_loss"],
        frame["observed_recovery_loss"],
        s=9,
        alpha=0.25,
    )
    low = min(frame["predicted_loss"].min(), frame["observed_recovery_loss"].min())
    high = max(frame["predicted_loss"].max(), frame["observed_recovery_loss"].max())
    axis.plot([low, high], [low, high], color="black", linewidth=1)
    axis.set(title=title, xlabel="Predicted MAE (°C)", ylabel="Realized MAE (°C)")


def main() -> None:
    predictions = pd.read_csv(OUTPUT / "predictions.csv")
    figure, axis = plt.subplots(figsize=(6.4, 5.4))
    scatter(axis, predictions, "Route A confirmation: 42 new networks")
    figure.tight_layout()
    figure.savefig(OUTPUT / "calibration.png", dpi=220)
    plt.close(figure)

    figure, axes = plt.subplots(1, 2, figsize=(11.0, 4.8), sharex=True, sharey=True)
    for axis, group in zip(axes, ("united_states", "cross_domain"), strict=True):
        scatter(axis, predictions.loc[predictions["domain_group"].eq(group)], group.replace("_", " ").title())
    figure.tight_layout()
    figure.savefig(OUTPUT / "domain_calibration.png", dpi=220)
    plt.close(figure)

    triage = json.loads((OUTPUT / "triage.json").read_text(encoding="utf-8"))
    labels = ["Simple risk", "Gap length"]
    safe = [
        100.0 * triage["simple_model"]["safe_fill_fraction"],
        100.0 * triage["gap_length"]["safe_fill_fraction"],
    ]
    false_release = [
        100.0 * triage["simple_model"]["false_release_rate"],
        100.0 * triage["gap_length"]["false_release_rate"],
    ]
    figure, axes = plt.subplots(1, 2, figsize=(8.5, 4.2))
    axes[0].bar(labels, safe, color=("#2962a3", "#888888"))
    axes[0].set(ylabel="Released cells (%)", title="Safe-fill fraction")
    axes[1].bar(labels, false_release, color=("#2962a3", "#888888"))
    axes[1].axhline(5.0, color="black", linestyle="--", linewidth=1)
    axes[1].set(ylabel="False releases among released (%)", title="False-release rate")
    figure.tight_layout()
    figure.savefig(OUTPUT / "triage.png", dpi=220)
    plt.close(figure)


if __name__ == "__main__":
    main()
