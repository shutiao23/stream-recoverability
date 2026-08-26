#!/usr/bin/env python3
"""Apply overlap-aware inference and claim-safe national/table revisions.

This script does not reopen frozen confirmatory outcomes or the national-panel
freeze.  It rewrites headline tables so they no longer report illegal p-values,
defective AUC headlines, or separated odds ratios as confirmatory evidence.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.analysis.evidence_boundaries import (
    compact_fingerprint_table,
    flag_separated_coefficients,
    topology_confound_rows,
    type_classification_table,
    valid_national_metrics,
    withhold_node_importance_intervals,
    withhold_overlap_inference,
)
from stream_recoverability.analysis.regulation_panel import (
    make_valid_regulation_panel_figure,
)
from stream_recoverability.analysis.regulation_panel_auc_diagnosis import (
    fold_auc_table,
)

ROOT = PROJECT_ROOT
REVISION = ROOT / "results/revision"
ANALYSIS = ROOT / "results/analysis"
PANEL = ROOT / "results/regulation_panel_v1_legacy_transport"
TABLES = ROOT / "paper/tables"
FIGURES = ROOT / "figures/main"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _identity(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _redraw_node_importance_figure(importance: pd.DataFrame) -> None:
    data = importance.copy()
    figure, axes = plt.subplots(
        1, 3, figsize=(11.5, 3.8), sharey=True, constrained_layout=True
    )
    for axis, station in zip(axes, ("B1", "S2", "P3"), strict=True):
        grouped = (
            data.loc[data["station_id"].eq(station)]
            .sort_values("impact", ascending=False)
            .reset_index(drop=True)
        )
        colors = np.where(grouped["impact"].ge(0), "#4c78a8", "#9d755d")
        axis.bar(
            grouped["failed_station_id"],
            grouped["impact"],
            color=colors,
            edgecolor="black",
            linewidth=0.5,
        )
        axis.axhline(0, color="black", linewidth=0.8)
        axis.set_title(f"Target {station}")
        axis.set_xlabel("Failed station")
        axis.grid(axis="y", alpha=0.2)
    axes[0].set_ylabel("Cross-fitted MAE difference (°C)")
    figure.suptitle(
        "Node importance from leave-one-year-out model selection",
        fontsize=13,
    )
    figure.savefig(FIGURES / "figure_05.png", dpi=300)
    plt.close(figure)


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _update_analysis_artifact_hashes(names: list[str]) -> None:
    manifest_path = ANALYSIS / "analysis_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts", {})
    for name in names:
        path = ANALYSIS / name
        if name not in artifacts or not path.is_file():
            continue
        artifacts[name]["sha256"] = _sha256(path)
        artifacts[name]["bytes"] = path.stat().st_size
        artifacts[name]["rows"] = int(len(pd.read_csv(path)))
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _refresh_publication_manifests() -> None:
    table_titles = {
        "table_01": "Eight-station regulation fingerprint",
        "table_02": "Annual Upper Jinsha thermal statistics",
        "table_03": "Frozen and stationarity-controlled covariance-heuristic evaluation",
        "table_04": "Descriptive recoverability in relative and absolute units",
        "table_05": "Leave-one-year-out cross-fitted node importance",
    }
    table_manifest = {
        "schema_version": "major_revision_table_manifest_v1",
        "status": "complete",
        "tables": {
            key: {
                **_identity(TABLES / f"{key}.csv"),
                "title": title,
                "rows": int(len(pd.read_csv(TABLES / f"{key}.csv"))),
            }
            for key, title in table_titles.items()
        },
    }
    (TABLES / "table_manifest.json").write_text(
        json.dumps(table_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    figure_titles = {
        "figure_01": "Study networks, monitoring stations, and regulating dams",
        "figure_02": "Reservoir-associated thermal structure across two networks",
        "figure_03": "Frozen covariance heuristic and post-hoc thermal-state control",
        "figure_04": "Recoverability in relative and absolute units",
        "figure_05": "Cross-fitted node importance",
        "figure_06": "Held-out Chattahoochee post-hoc fixed-model sensitivity",
        "figure_07": "National regulation-panel boundary, not a valid classifier",
    }
    figure_manifest = {
        "schema_version": "major_revision_figure_manifest_v1",
        "status": "complete",
        "figures": {
            key: {
                **_identity(FIGURES / f"{key}.png"),
                "title": title,
            }
            for key, title in figure_titles.items()
        },
    }
    (FIGURES / "figure_manifest.json").write_text(
        json.dumps(figure_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    final_path = ROOT / "results/final_results_manifest.json"
    final = json.loads(final_path.read_text(encoding="utf-8"))
    for key, relative in (
        ("analysis_manifest", "results/revision/revision_analysis_manifest.json"),
        ("figure_manifest", "figures/main/figure_manifest.json"),
        ("table_manifest", "paper/tables/table_manifest.json"),
        (
            "regulation_panel_manifest",
            "results/regulation_panel_v1_legacy_transport/artifact_manifest.json",
        ),
    ):
        final[key] = _identity(ROOT / relative)
    final_path.write_text(
        json.dumps(final, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    frontiers = withhold_overlap_inference(
        pd.read_csv(ANALYSIS / "statistical_frontiers.csv")
    )
    dual = withhold_overlap_inference(pd.read_csv(ANALYSIS / "dual_frontier_comparison.csv"))
    hypotheses = withhold_overlap_inference(
        pd.read_csv(ANALYSIS / "hypothesis_tests.csv")
    )
    _write_csv(ANALYSIS / "statistical_frontiers.csv", frontiers)
    _write_csv(ANALYSIS / "dual_frontier_comparison.csv", dual)
    _write_csv(ANALYSIS / "hypothesis_tests.csv", hypotheses)
    _write_csv(REVISION / "statistical_frontiers_overlap_aware.csv", frontiers)
    _write_csv(REVISION / "hypothesis_tests_overlap_aware.csv", hypotheses)
    _update_analysis_artifact_hashes(
        [
            "statistical_frontiers.csv",
            "dual_frontier_comparison.csv",
            "hypothesis_tests.csv",
        ]
    )

    importance = withhold_node_importance_intervals(
        pd.read_csv(REVISION / "node_importance_cross_fitted.csv")
    )
    _write_csv(REVISION / "node_importance_cross_fitted.csv", importance)
    _write_csv(TABLES / "table_05.csv", importance)
    _redraw_node_importance_figure(importance)

    fingerprint = pd.read_csv(TABLES / "table_01.csv", dtype={"station_id": str})
    if "donor_component" not in fingerprint:
        fingerprint = fingerprint.rename(
            columns={
                "donor_component_30d": "donor_component",
                "memory_component_30d": "memory_component",
            }
        )
    compact = compact_fingerprint_table(fingerprint)
    _write_csv(TABLES / "table_01.csv", compact)

    type_table = type_classification_table(
        pd.read_csv(
            REVISION / "recoverability_type_horizon_sensitivity.csv",
            dtype={"station_id": str},
        )
    )
    _write_csv(REVISION / "recoverability_type_classification_uncertainty.csv", type_table)
    topology = topology_confound_rows()
    _write_csv(REVISION / "topology_confound_audit.csv", topology)

    table_04 = pd.read_csv(TABLES / "table_04.csv")
    withheld_lookup = frontiers.loc[
        frontiers["target"].eq("T"),
        [
            "station_id",
            "model",
            "statistical_frontier_days",
            "statistical_frontier_censoring",
            "n_independent_clusters",
            "hypothesis_status",
        ],
    ]
    if "validation_selected_model" in table_04:
        table_04 = table_04.merge(
            withheld_lookup,
            left_on=["station_id", "validation_selected_model"],
            right_on=["station_id", "model"],
            how="left",
            suffixes=("", "_withheld"),
        )
        table_04["statistical_frontier_days"] = table_04.get(
            "statistical_frontier_days_withheld", table_04["statistical_frontier_days"]
        )
        table_04["statistical_frontier_censoring"] = table_04.get(
            "statistical_frontier_censoring_withheld",
            table_04["statistical_frontier_censoring"],
        )
        for column in ("skill_ci_lower", "skill_ci_upper"):
            if column in table_04:
                table_04[column] = pd.NA
        keep = [
            column
            for column in (
                "station_id",
                "gap_length",
                "validation_selected_model",
                "validation_mean_MAE",
                "mean_skill",
                "mean_MAE_degC",
                "mean_climatology_MAE_degC",
                "n_anchors",
                "n_independent_clusters",
                "hypothesis_status",
            )
            if column in table_04
        ]
        table_04 = table_04[keep]
    _write_csv(TABLES / "table_04.csv", table_04)

    metrics = pd.read_csv(PANEL / "station_metrics.csv", dtype={"station_id": str})
    predictions = pd.read_csv(
        PANEL / "leave_ecoregion_out_predictions.csv", dtype={"station_id": str}
    )
    folds = fold_auc_table(predictions)
    national = valid_national_metrics(metrics, predictions)
    (REVISION / "national_valid_metrics.json").write_text(
        json.dumps(national, indent=2, allow_nan=True) + "\n",
        encoding="utf-8",
    )
    logistic = flag_separated_coefficients(pd.read_csv(PANEL / "logistic_regression.csv"))
    _write_csv(REVISION / "national_logistic_suppressed.csv", logistic)
    firth_rows = [
        {
            "model": "firth_unadjusted",
            "term": "z_memory_range_index",
            "odds_ratio": national["firth_unadjusted_odds_ratio_per_index_sd"],
            "odds_ratio_ci_low": national["firth_unadjusted_odds_ratio_ci_low"],
            "odds_ratio_ci_high": national["firth_unadjusted_odds_ratio_ci_high"],
            "wald_p_value": national["firth_unadjusted_p_value"],
            "reporting_status": "reported_descriptive_null",
        }
    ]
    _write_csv(REVISION / "national_firth_unadjusted.csv", pd.DataFrame(firth_rows))

    profile = pd.read_csv(PANEL / "distance_profile.csv")
    make_valid_regulation_panel_figure(
        metrics,
        predictions,
        profile,
        folds,
        macro_auc=float(national["macro_within_fold_auc"]),
        output_path=FIGURES / "figure_07.png",
    )

    inference_manifest = {
        "schema_version": "wrr_evidence_revision_v1",
        "status": "complete",
        "does_not_reopen_freeze": True,
        "headline_claims_downgraded": True,
        "independent_cluster_floor": 5,
        "frontier_finite_p_values": int(
            frontiers.loc[
                frontiers["hypothesis_family"].eq("frontier_model_vs_climatology"),
                "p_value",
            ]
            .notna()
            .sum()
        ),
        "national_headline_estimand": national["headline_estimand"],
        "artifacts": {
            name: _identity(path)
            for name, path in {
                "statistical_frontiers": ANALYSIS / "statistical_frontiers.csv",
                "hypothesis_tests": ANALYSIS / "hypothesis_tests.csv",
                "type_uncertainty": REVISION
                / "recoverability_type_classification_uncertainty.csv",
                "topology_confound": REVISION / "topology_confound_audit.csv",
                "national_valid_metrics": REVISION / "national_valid_metrics.json",
                "national_logistic_suppressed": REVISION
                / "national_logistic_suppressed.csv",
            }.items()
        },
    }
    (REVISION / "wrr_evidence_revision_manifest.json").write_text(
        json.dumps(inference_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _refresh_publication_manifests()
    print(
        json.dumps(
            {
                "status": "complete",
                "frontier_finite_p_values": inference_manifest["frontier_finite_p_values"],
                "macro_within_fold_auc": national["macro_within_fold_auc"],
                "near_threshold_cells": int(
                    type_table["near_classification_threshold"].sum()
                ),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
