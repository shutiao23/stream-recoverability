"""Tests for dual-lineage study manifest (P0-0)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

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


def test_main_v9_results_registry_pending() -> None:
    reg = json.loads((ROOT / "paper/main_v9/results_registry.json").read_text(encoding="utf-8"))
    assert reg["formal_evidence"] is False
    assert reg["sealed_outcomes_opened"] is False
    assert reg["corpus"]["floor_met"] is False


def test_case_study_v1_package_manifest() -> None:
    pkg = json.loads(
        (ROOT / "paper/case_study_v1/package_manifest.json").read_text(encoding="utf-8")
    )
    assert pkg["design_id"] == "design_freeze_v4"
    assert pkg["lineage"] == "case_study_v4"
