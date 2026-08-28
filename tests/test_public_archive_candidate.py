from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    path = ROOT / "scripts/40_build_public_archive_candidate.py"
    spec = importlib.util.spec_from_file_location("public_archive_candidate", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_public_archive_includes_rights_safe_companion_inventory() -> None:
    module = _load_module()
    relative = {path.relative_to(ROOT).as_posix() for path in module._candidate_files()}
    assert ".zenodo.json" in relative
    assert "CITATION.cff" in relative
    assert "results/audits/blueprint_completion_audit.json" in relative
    assert "results/development_v11/reviewer_completion/summary.json" in relative
    assert "results/development_v11/reviewer_completion/figure_03_mechanism.png" in relative
    assert "results/development_v11/second_confirmation/readiness.json" in relative
    assert "results/audits/goal_completion_audit.json" in relative
    assert (
        "data_versions/global_network_corpus_v1/qualified_corpus_v1/"
        "network_catalog_v3_qualified.parquet"
    ) in relative
    assert (
        "data_versions/global_network_corpus_v1/qualified_corpus_v1/"
        "network_catalog_v3_exclusions.csv"
    ) in relative
    assert not any(path.startswith("data/raw/") for path in relative)
    assert not any("/vault/" in path for path in relative)
    assert not any(path.startswith("private/") for path in relative)
