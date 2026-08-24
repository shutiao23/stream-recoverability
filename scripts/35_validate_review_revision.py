#!/usr/bin/env python3
"""Fail closed on manuscript/result inconsistencies introduced by the revision."""

from __future__ import annotations

import hashlib
import json
import re
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
    external = pd.read_csv(
        ROOT / "results/revision/external_confirmation_summary.csv",
        dtype={"station_id": str},
    )
    assert external["qualitative_prediction_consistent"].all()

    manuscript = (ROOT / "paper/manuscript.md").read_text(encoding="utf-8")
    assert "RESULTS_PENDING" not in manuscript
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
                "figures": figure_count,
                "tables": table_count,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
