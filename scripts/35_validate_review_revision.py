#!/usr/bin/env python3
"""Fail closed on manuscript/result inconsistencies introduced by the revision."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _assert_manifest_identities(path: Path, section: str) -> int:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    records = manifest[section]
    for record in records.values():
        artifact = ROOT / record["path"]
        assert artifact.is_file(), artifact
        assert artifact.stat().st_size == record["bytes"], artifact
        assert _sha256(artifact) == record["sha256"], artifact
    return len(records)


def main() -> None:
    formal_manifest = json.loads(
        (ROOT / "results/analysis/analysis_manifest.json").read_text(encoding="utf-8")
    )
    assert formal_manifest["status"] == "complete"

    statistical = pd.read_csv(ROOT / "results/analysis/statistical_frontiers.csv")
    dual = pd.read_csv(ROOT / "results/analysis/dual_frontier_comparison.csv")
    climate = dual.loc[dual["frontier_denominator"].eq("climatology")]
    keys = [
        "station_id",
        "target",
        "data_version",
        "model",
        "information_combination",
        "window",
        "evaluation_split",
    ]
    comparison = statistical.merge(
        climate,
        on=keys,
        suffixes=("_statistical", "_dual"),
        validate="one_to_one",
    )
    assert len(comparison) == 27
    for column in ("statistical_frontier_days", "statistical_frontier_censoring"):
        left = comparison[f"{column}_statistical"]
        right = comparison[f"{column}_dual"]
        assert (left.eq(right) | (left.isna() & right.isna())).all(), column

    hypotheses = pd.read_csv(ROOT / "results/analysis/hypothesis_tests.csv")
    frontier_tests = hypotheses.loc[
        hypotheses["hypothesis_family"].eq("frontier_model_vs_climatology")
    ]
    assert len(frontier_tests) == 27
    assert frontier_tests["p_value"].notna().sum() == 24
    assert frontier_tests["bh_reject"].sum() == 14
    references = frontier_tests.loc[frontier_tests["model"].eq("climatology")]
    assert len(references) == 3
    assert references["hypothesis_status"].eq("reference_not_tested").all()

    importance = pd.read_csv(ROOT / "results/analysis/node_importance.csv")
    assert len(importance) == 36
    assert importance["model"].eq("best_available").all()
    assert (
        importance["impact_definition"]
        .eq("best_available_failed_minus_best_available_full_with_climatology_hard_cap")
        .all()
    )

    budget = pd.read_csv(ROOT / "paper/tables/table_03.csv")
    original_p3 = budget.loc[
        budget["analysis"].eq("original_training_climatology")
        & budget["station_id"].eq("P3")
    ].iloc[0]
    state_p3 = budget.loc[
        budget["analysis"].eq("state_matched_2016_2020_climatology")
        & budget["station_id"].eq("P3")
    ].iloc[0]
    assert original_p3["best_lower_ci_exceeds_budget_count"] == 9
    assert state_p3["best_lower_ci_exceeds_budget_count"] == 1

    fingerprint = pd.read_csv(
        ROOT / "paper/tables/table_01.csv", dtype={"station_id": str}
    )
    memory = set(
        fingerprint.loc[
            fingerprint["recoverability_type"].eq("memory_dominated"), "station_id"
        ]
    )
    assert memory == {"P3", "02334430"}

    external_manifest = json.loads(
        (
            ROOT
            / "results/confirmatory/external_upper_middle_chattahoochee_v1"
            / "external_confirmation/completion_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert external_manifest["complete"] is True
    assert external_manifest["completed_run_unit_count"] == 540
    assert external_manifest["model_selection_on_confirmatory"] is False
    external_root = (
        ROOT
        / "results/confirmatory/external_upper_middle_chattahoochee_v1"
        / "external_confirmation"
    )
    inventory = external_manifest["artifact_inventory"]
    assert external_manifest["artifact_count"] == len(inventory) == 306
    for relative, identity in inventory.items():
        artifact = external_root / relative
        assert artifact.is_file(), artifact
        assert artifact.stat().st_size == identity["bytes"], artifact
        assert _sha256(artifact) == identity["sha256"], artifact
    completion_path = external_root / "completion_manifest.json"
    sidecar = (external_root / "completion_manifest.json.sha256").read_text().strip()
    assert _sha256(completion_path) == sidecar
    once_lock_path = (
        ROOT
        / "data_versions"
        / ".external_upper_middle_chattahoochee_v1.confirmatory-evaluation-once.lock.json"
    )
    once_lock = json.loads(once_lock_path.read_text(encoding="utf-8"))
    assert once_lock["status"] == "complete"
    assert once_lock["completion_manifest_sha256"] == sidecar
    tracked = set(
        subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    )
    required_tracked = {
        str(path.relative_to(ROOT))
        for path in external_root.rglob("*")
        if path.is_file()
    }
    required_tracked.add(str(once_lock_path.relative_to(ROOT)))
    assert required_tracked.issubset(tracked), sorted(
        required_tracked.difference(tracked)
    )
    external = pd.read_csv(
        ROOT / "results/revision/external_confirmation_summary.csv",
        dtype={"station_id": str},
    )
    assert external["qualitative_prediction_consistent"].all()

    placement_root = ROOT / "results/revision/external_validation_uncertainty"
    placement_manifest = json.loads(
        (placement_root / "external_validation_uncertainty_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert placement_manifest["status"] == "complete"
    assert placement_manifest["evaluation_split"] == "validation"
    assert placement_manifest["confirmatory_outcomes_read"] is False
    assert placement_manifest["confirmatory_metric_uses"] == 0
    assert placement_manifest["once_lock_read"] is False
    assert placement_manifest["once_lock_modified"] is False
    for name, identity in placement_manifest["artifacts"].items():
        artifact = placement_root / name
        assert artifact.is_file(), artifact
        assert artifact.stat().st_size == identity["bytes"], artifact
        assert _sha256(artifact) == identity["sha256"], artifact
    placement_cells = pd.read_csv(
        placement_root / "external_validation_uncertainty_cells.csv"
    )
    assert len(placement_cells) == 135
    assert placement_cells["n_mask_seeds"].eq(20).all()
    paired_scale = pd.read_csv(
        placement_root / "external_validation_uncertainty_paired_differences.csv",
        dtype={"donor_station_id": str},
    )
    assert len(paired_scale) == 12
    confirm_cells = pd.read_csv(
        ROOT / "results/revision/external_confirmation_cells.csv",
        dtype={"station_id": str},
    )
    confirm_180 = confirm_cells.loc[confirm_cells["gap_length"].eq(180)].set_index(
        "station_id"
    )
    dam_skill = float(confirm_180.loc["02334430", "best_skill"])
    ratios = []
    for row in paired_scale.loc[paired_scale["gap_length"].eq(180)].itertuples():
        difference = float(
            confirm_180.loc[row.donor_station_id, "best_skill"] - dam_skill
        )
        ratios.append(difference / float(row.paired_difference_sd))
    assert min(ratios) > 3.0 and max(ratios) < 6.0

    change_manifest = json.loads(
        (ROOT / "results/revision/p3_change_point_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert change_manifest["status"] == "complete"
    for identity in change_manifest["artifacts"]:
        artifact = ROOT / identity["path"]
        assert artifact.is_file(), artifact
        assert artifact.stat().st_size == identity["bytes"], artifact
        assert _sha256(artifact) == identity["sha256"], artifact
    change_summary = pd.read_csv(ROOT / "results/revision/p3_change_point_summary.csv")
    primary_change = change_summary.loc[change_summary["role"].eq("primary")].iloc[0]
    sensitivity_change = change_summary.loc[
        change_summary["role"].eq("robust_sensitivity")
    ].iloc[0]
    assert primary_change["point_date"] == "2013-05-26"
    assert not bool(primary_change["event_in_95pct_bootstrap_ci"])
    assert sensitivity_change["point_date"] == "2014-10-18"
    assert bool(sensitivity_change["event_in_95pct_bootstrap_ci"])

    panel_root = ROOT / "results/regulation_panel_v1_legacy_transport"
    panel_manifest = json.loads(
        (panel_root / "artifact_manifest.json").read_text(encoding="utf-8")
    )
    assert panel_manifest["confirmatory_path_access_audit_passed"] is True
    for identity in panel_manifest["artifacts"]:
        artifact = ROOT / identity["path"]
        assert artifact.is_file(), artifact
        assert artifact.stat().st_size == identity["bytes"], artifact
        assert _sha256(artifact) == identity["sha256"], artifact
    panel_report = json.loads((panel_root / "report.json").read_text(encoding="utf-8"))
    assert panel_report["complete"] is True
    assert panel_report["confirmatory_network_touched"] is False
    assert panel_report["flow"]["eligible_stations"] == 335
    assert panel_report["flow"]["regulated_stations"] == 209
    assert panel_report["flow"]["unregulated_stations"] == 126
    assert panel_report["scientific_conclusion"]["primary_discrimination"] == (
        "not_supported"
    )
    assert (
        panel_report["primary"]["pooled_leave_ecoregion_out_auc"] == 0.40749601275917063
    )
    assert panel_report["transport_equivalence_audit"]["pass_fraction"] == 1.0

    manuscript = (ROOT / "paper/manuscript.md").read_text(encoding="utf-8")
    assert "RESULTS_PENDING" not in manuscript
    assert "changed abruptly at the end of 2014" not in manuscript
    abstract = re.search(r"## Abstract\n\n(.*?)\n\n##", manuscript, re.DOTALL)
    assert abstract is not None and len(abstract.group(1).split()) <= 250
    for line in (ROOT / "paper/key_points.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("- "):
            assert len(line[2:]) <= 140

    cited = set()
    for source in ("paper/manuscript.md", "paper/methods.md"):
        for group in re.findall(r"\[@([^\]]+)\]", (ROOT / source).read_text()):
            cited.update(item.strip().lstrip("@") for item in group.split(";"))
    bib_keys = set(
        re.findall(
            r"@\w+\{([^,]+),",
            (ROOT / "paper/references.bib").read_text(encoding="utf-8"),
        )
    )
    assert not cited.difference(bib_keys), sorted(cited.difference(bib_keys))

    figure_count = _assert_manifest_identities(
        ROOT / "figures/main/figure_manifest.json", "figures"
    )
    assert figure_count == 6
    table_count = _assert_manifest_identities(
        ROOT / "paper/tables/table_manifest.json", "tables"
    )
    print(
        json.dumps(
            {
                "status": "complete",
                "matching_frontier_cells": len(comparison),
                "finite_frontier_tests": 24,
                "node_importance_rows": len(importance),
                "external_run_units": 540,
                "external_validation_seed_cells": 2700,
                "p3_change_point_methods": 2,
                "regulation_panel_stations": 335,
                "tracked_external_artifacts": len(required_tracked),
                "figures": figure_count,
                "tables": table_count,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
