#!/usr/bin/env python3
"""Shared provenance helpers for local release-test summaries."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identity() -> dict:
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        head = "unknown"
    digest = hashlib.sha256()
    files = sorted((ROOT / "src").rglob("*.py"))
    pyproject = ROOT / "pyproject.toml"
    if pyproject.is_file():
        files.append(pyproject)
    for path in files:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return {
        "git_head": head,
        "src_tree_sha256": digest.hexdigest(),
        "pyproject_sha256": sha256_file(pyproject) if pyproject.is_file() else None,
    }


def parse_junit(path: Path) -> dict:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    counts = {
        key: sum(int(suite.get(key, 0)) for suite in suites)
        for key in ["tests", "failures", "errors", "skipped"]
    }
    counts["passed"] = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
    return counts


def summary_from_junit(
    junit: Path,
    *,
    exit_code: int,
    command: str,
    scope: str,
    files: list[str] | None = None,
    out: Path | None = None,
) -> dict:
    counts = parse_junit(junit)
    label = str(junit.relative_to(out)) if out is not None and junit.is_relative_to(out) else (
        str(junit.relative_to(ROOT)) if junit.is_relative_to(ROOT) else str(junit)
    )
    summary = {
        "exit_code": int(exit_code),
        "scope": scope,
        "junit": label,
        "junit_sha256": sha256_file(junit),
        "command": command,
        "interpreter": sys.executable,
        "python_version": platform.python_version(),
        "source_identity": source_identity(),
        **counts,
    }
    if files is not None:
        summary["files"] = files
    return summary


def validate_summary(summary: dict, label: str, out: Path | None = None) -> None:
    required = ["exit_code", "tests", "passed", "failures", "errors", "skipped", "junit", "junit_sha256",
                "command", "interpreter", "source_identity"]
    missing = [key for key in required if key not in summary]
    if missing:
        raise ValueError(f"{label} summary is missing {missing}")
    for key in ["exit_code", "tests", "passed", "failures", "errors", "skipped"]:
        value = summary[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{label}.{key} must be a non-negative integer")
    if summary["exit_code"] != 0:
        raise ValueError(f"{label} exit code is not zero")
    if summary["tests"] <= 0 or summary["passed"] <= 0:
        raise ValueError(f"{label} has no executed passing tests")
    if summary["failures"] != 0:
        raise ValueError(f"{label} reports test failures")
    if summary["errors"] != 0:
        raise ValueError(f"{label} reports test errors")
    expected = summary["tests"] - summary["failures"] - summary["errors"] - summary["skipped"]
    if summary["passed"] != expected:
        raise ValueError(f"{label} counts are inconsistent")
    identity = summary["source_identity"]
    if not isinstance(identity, dict) or not identity.get("git_head") or not identity.get("src_tree_sha256"):
        raise ValueError(f"{label} source identity is incomplete")
    if not summary["command"] or not summary["interpreter"]:
        raise ValueError(f"{label} command or interpreter is missing")
    junit_path = Path(summary["junit"])
    if not junit_path.is_absolute():
        junit_path = (out / junit_path) if out is not None else (ROOT / junit_path)
    if not junit_path.is_file():
        raise ValueError(f"{label} JUnit file is missing")
    if sha256_file(junit_path) != summary["junit_sha256"]:
        raise ValueError(f"{label} JUnit hash differs")
    from_junit = parse_junit(junit_path)
    for key in ["tests", "passed", "failures", "errors", "skipped"]:
        if from_junit[key] != summary[key]:
            raise ValueError(f"{label} JUnit counts differ at {key}")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
