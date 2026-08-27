#!/usr/bin/env python3
"""Validate dual-lineage study manifest and package separation (P0-0)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "paper/study_manifest.json"


def validate_study_manifest(repo_root: Path = ROOT) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    errors: list[str] = []
    lineages = manifest.get("lineages", {})
    if set(lineages) != {"case_study_v4", "main_v9"}:
        errors.append("expected exactly case_study_v4 and main_v9 lineages")
    v4 = lineages.get("case_study_v4", {})
    v9 = lineages.get("main_v9", {})
    for key, lineage in (("case_study_v4", v4), ("main_v9", v9)):
        root = repo_root / lineage.get("root", "")
        if not root.is_dir():
            errors.append(f"{key} root missing: {root}")
        manuscript = repo_root / lineage.get("manuscript", "")
        if not manuscript.is_file():
            errors.append(f"{key} manuscript missing: {manuscript}")
    v4_design = repo_root / v4.get("design_freeze", "")
    v9_charter = repo_root / v9.get("design_charter", v9.get("design_freeze_charter", ""))
    v10 = repo_root / v9.get("executable_protocol", "")
    if not v4_design.is_file():
        errors.append(f"v4 design freeze missing: {v4_design}")
    if not v9_charter.is_file():
        errors.append(f"v9 charter missing: {v9_charter}")
    if not v10.is_file():
        errors.append(f"v10 executable protocol missing: {v10}")
    forbidden_v4 = v4.get("forbidden_evidence_from", [])
    forbidden_v9 = v9.get("forbidden_evidence_from", [])
    if "paper/main_v9" not in forbidden_v4:
        errors.append("v4 must forbid evidence from paper/main_v9")
    if "paper/case_study_v1" not in forbidden_v9:
        errors.append("v9 must forbid evidence from paper/case_study_v1")
    return {
        "manifest_schema": manifest.get("manifest_schema"),
        "passed": not errors,
        "errors": errors,
        "lineages": list(lineages),
    }


def main() -> None:
    report = validate_study_manifest()
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
