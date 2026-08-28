"""Tests for dual-lineage study manifest (P0-0)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load_validate_module():
    spec = importlib.util.spec_from_file_location(
        "validate_study_manifest",
        ROOT / "scripts/103_validate_study_manifest.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_study_manifest_validates() -> None:
    mod = _load_validate_module()
    report = mod.validate_study_manifest(ROOT)
    assert report["passed"] is True, report.get("errors")


def test_design_freeze_v10_is_executable_charter_not_v4_replacement() -> None:
    v10 = yaml.safe_load(
        (ROOT / "configs/design_freeze_v10_executable.yaml").read_text(encoding="utf-8")
    )
    assert v10["executable"] is True
    assert v10["not_an_executable_design"] is False
    assert v10["does_not_replace_executable_design_version_v4"] is True
    assert v10["activation_gates"]["corpus_floor"]["passed"] is False


def test_main_v9_results_registry_records_failed_sealed_qc_gate() -> None:
    reg = json.loads((ROOT / "paper/main_v9/results_registry.json").read_text(encoding="utf-8"))
    assert reg["formal_evidence"] is False
    assert reg["sealed_outcomes_opened"] is True
    assert reg["confirmatory_scoring_performed"] is False
    assert reg["corpus"]["floor_met"] is False
    assert reg["sealed_qc"]["eligible_total"] == 32
    assert reg["sealed_qc"]["sealed_floor_met"] is False


def test_qualified_catalog_includes_open_and_sealed_networks() -> None:
    corpus = json.loads(
        (
            ROOT
            / "data_versions/global_network_corpus_v1/qualified_corpus_v1/qualified_corpus_manifest.json"
        ).read_text(encoding="utf-8")
    )
    catalog = json.loads(
        (
            ROOT
            / "data_versions/global_network_corpus_v1/qualified_corpus_v1/network_catalog_v3_qualified_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert corpus["qualified_total"] == 99
    assert corpus["components"]["open_role_complete_enough_failure_closure6"] == 67
    assert corpus["components"]["sealed_qc_complete_enough"] == 32
    assert catalog["n_open_role_unique"] == 67
    assert catalog["n_sealed_eligible"] == 32
    assert catalog["n_qualified_unique"] == corpus["qualified_total"]
    assert catalog["count_matches_corpus_manifest"] is True


def test_qualified_catalog_has_exclusion_and_balance_audits() -> None:
    root = ROOT / "data_versions/global_network_corpus_v1/qualified_corpus_v1"
    manifest = json.loads(
        (root / "network_catalog_v3_qualified_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    audit = manifest["audit_outputs"]
    exclusions = pd.read_csv(ROOT / audit["exclusions_path"])
    balance = pd.read_csv(ROOT / audit["balance_path"])
    assert audit["candidate_inventory_count"] == 177
    assert audit["candidate_qualified_count"] == 99
    assert audit["excluded_count"] == 78
    assert len(exclusions) == 78
    assert exclusions["network_id"].is_unique
    assert not set(exclusions["network_id"]) & set(
        pd.read_parquet(root / "network_catalog_v3_qualified.parquet")["network_id"]
    )
    assert set(balance["dimension"]) == {
        "provider",
        "locked_role",
        "climate_band",
        "size_tertile",
        "regulation_stratum",
    }
    for _, group in balance.groupby("dimension"):
        assert int(group["candidate_count"].sum()) == 177
        assert int(group["qualified_count"].sum()) == 99
        assert int(group["excluded_count"].sum()) == 78


def test_case_study_v1_package_manifest() -> None:
    pkg = json.loads(
        (ROOT / "paper/case_study_v1/package_manifest.json").read_text(encoding="utf-8")
    )
    assert pkg["design_id"] == "design_freeze_v4"
    assert pkg["lineage"] == "case_study_v4"
