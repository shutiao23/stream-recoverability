#!/usr/bin/env python3
"""Run 100-network US climate/regulation mixed calibration models."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import matplotlib
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from stream_recoverability.analysis.us_heterogeneity import (
    build_us_heterogeneity_panel,
    fit_mixed_calibration,
)

DEFAULT_OUTPUT = ROOT / "results/development_v11/reviewer_completion"
DEFAULT_GAGES = (
    ROOT / "data/cache/regulation_panel_v1/basinchar_and_report_sept_2011.zip"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def plot_level_slopes(levels: pd.DataFrame, output: Path) -> None:
    colors = {
        "simple_descriptors": "#0072B2",
        "fitting_period_empirical": "#D55E00",
    }
    figure, axes = plt.subplots(1, 2, figsize=(10.5, 4.8), sharex=True)
    for axis, moderator, title in zip(
        axes,
        ("climate_group", "regulation_stratum"),
        ("HUC2 climate group", "GAGES-II regulation stratum"),
        strict=True,
    ):
        subset = levels.loc[levels["moderator"].eq(moderator)].copy()
        names = sorted(subset["level"].unique())
        positions = {name: index for index, name in enumerate(names)}
        for offset, (risk_model, values) in zip(
            (-0.10, 0.10), subset.groupby("risk_model", sort=True), strict=True
        ):
            y = [positions[value] + offset for value in values["level"]]
            axis.errorbar(
                values["adjusted_calibration_slope"],
                y,
                xerr=[
                    values["adjusted_calibration_slope"] - values["ci_lower"],
                    values["ci_upper"] - values["adjusted_calibration_slope"],
                ],
                fmt="o",
                capsize=3,
                color=colors[risk_model],
                label=risk_model.replace("_", " "),
            )
        axis.axvline(1.0, color="black", lw=1, ls="--")
        axis.set_yticks(
            range(len(names)), [name.replace("_", " ") for name in names]
        )
        axis.set_title(title)
        axis.grid(axis="x", alpha=0.2)
    for axis in axes:
        axis.set_xlabel("Adjusted calibration slope (95% CI)")
    axes[1].legend(frameon=False, loc="best")
    figure.suptitle(
        "Calibration heterogeneity across 100+ US river networks\n"
        "random intercept and prediction slope by network; development reference phase"
    )
    figure.tight_layout()
    figure.savefig(output, dpi=300, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--gages-archive", type=Path, default=DEFAULT_GAGES)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    panel = build_us_heterogeneity_panel(ROOT, gages_archive=args.gages_archive)
    panel_path = args.output / "us_heterogeneity_panel.csv"
    panel.to_csv(panel_path, index=False)

    network_table = (
        panel[
            [
                "risk_model",
                "phase",
                "network_id",
                "network_uid",
                "huc2",
                "climate_band",
                "climate_group",
                "regulation_stratum",
                "n_stations",
            ]
        ]
        .drop_duplicates(["risk_model", "network_uid"])
        .sort_values(["risk_model", "phase", "network_id"])
    )
    network_path = args.output / "us_heterogeneity_networks.csv"
    network_table.to_csv(network_path, index=False)

    coefficient_parts = []
    diagnostics = []
    level_rows = []
    for risk_model in ("simple_descriptors", "fitting_period_empirical"):
        for moderator in ("climate_group", "regulation_stratum"):
            coefficients, diagnostic = fit_mixed_calibration(
                panel, risk_model=risk_model, moderator=moderator
            )
            coefficient_parts.append(coefficients)
            diagnostics.append(
                {key: value for key, value in diagnostic.items() if key != "level_slopes"}
            )
            level_rows.extend(diagnostic["level_slopes"])
    coefficient_path = args.output / "us_heterogeneity_coefficients.csv"
    pd.concat(coefficient_parts, ignore_index=True).to_csv(
        coefficient_path, index=False
    )
    level_path = args.output / "us_heterogeneity_level_slopes.csv"
    level_table = pd.DataFrame(level_rows)
    level_table.to_csv(level_path, index=False)
    figure_path = args.output / "figure_06_us_heterogeneity.png"
    plot_level_slopes(level_table, figure_path)

    counts = (
        network_table.groupby(["risk_model", "phase"], as_index=False)
        .agg(n_networks=("network_uid", "nunique"))
        .to_dict(orient="records")
    )
    manifest = {
        "analysis_id": "v11_us_100_network_mixed_heterogeneity_v1",
        "status": "complete_descriptive_mixed_model",
        "evidence_role": "cross_phase_descriptive_not_causal",
        "independent_unit": "river_network",
        "models": "random_intercept_and_random_prediction_slope_by_network",
        "modifiers": [
            "frozen_huc2_climate_group",
            "gages_ii_2009_major_dam_regulation_stratum",
            "phase_qc_regime",
            "network_size",
        ],
        "risk_models": {
            risk_model: int(
                network_table.loc[
                    network_table["risk_model"].eq(risk_model), "network_uid"
                ].nunique()
            )
            for risk_model in sorted(network_table["risk_model"].unique())
        },
        "phase_counts": counts,
        "known_regulation_networks": {
            risk_model: int(
                network_table.loc[
                    network_table["risk_model"].eq(risk_model)
                    & ~network_table["regulation_stratum"].eq("unmatched_gages"),
                    "network_uid",
                ].nunique()
            )
            for risk_model in sorted(network_table["risk_model"].unique())
        },
        "diagnostics": diagnostics,
        "boundaries": [
            "HUC2 climate bands are broad catalog strata, not site-scale climate attribution.",
            "GAGES-II major-dam presence is a descriptive regulation stratum, not a causal treatment.",
            "Development and two outcome panels have different QC regimes; phase interactions are retained.",
            "The analysis combines roles to reach 100 networks and is not a new independent confirmation.",
        ],
        "inputs": {
            "gages_archive": {
                "path": str(args.gages_archive.relative_to(ROOT)),
                "sha256": sha256(args.gages_archive),
                "redistributed": False,
            }
        },
        "outputs": {
            path.name: sha256(path)
            for path in (
                panel_path,
                network_path,
                coefficient_path,
                level_path,
                figure_path,
            )
        },
    }
    manifest_path = args.output / "us_heterogeneity_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
