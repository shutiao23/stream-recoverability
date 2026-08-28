from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    path = ROOT / "scripts/105_build_blueprint_completion_audit.py"
    spec = importlib.util.spec_from_file_location("blueprint_completion_audit", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_blueprint_audit_covers_every_declared_requirement() -> None:
    audit = _load_module().build_audit()
    expected = {
        *(f"P0-{index}" for index in range(10)),
        *(f"P1-{index}" for index in range(1, 6)),
        *(f"P2-{index}" for index in range(1, 5)),
    }
    rows = {row["id"]: row for row in audit["requirements"]}
    assert set(rows) == expected
    assert audit["objective_complete"] is False
    assert audit["counts"] == {
        "qualified_networks": 99,
        "qualified_floor": 100,
        "sealed_eligible": 32,
        "sealed_floor": 40,
    }
    assert rows["P0-3"]["status"] == "complete_negative"
    assert rows["P0-7"]["status"] == "failed_before_scoring"
    assert rows["P1-5"]["status"] == "implementation_smoke_complete"
    assert len(audit["external_submission_blockers"]) == 4


def test_blueprint_audit_evidence_paths_exist_when_file_backed() -> None:
    audit = _load_module().build_audit()
    directory_evidence = {
        "paper/case_study_v1/",
        "paper/main_v9/",
        "results/framework/t2_outage_geometry_v1/",
        "data_versions/global_network_corpus_v1/qualified_corpus_v1/",
    }
    for row in audit["requirements"]:
        assert row["evidence"], row["id"]
        for relative in row["evidence"]:
            path = ROOT / relative
            if relative in directory_evidence:
                assert path.is_dir(), relative
            else:
                assert path.is_file(), relative
