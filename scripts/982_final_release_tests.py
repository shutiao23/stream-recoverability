#!/usr/bin/env python3
"""Run the declared final-release test list and write a versioned JUnit summary.

The test list lives in scripts/980_final_release.py so that build, verification
and acceptance all name the same scope. This runner does not install packages or
pretend to be a clean-environment test.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_provenance


def load_release_module():
    spec = importlib.util.spec_from_file_location("final_release_980", ROOT / "scripts/980_final_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--junit", type=Path, default=None)
    args = parser.parse_args()
    release = load_release_module()
    out = args.output or (release.OUT / "targeted_tests_summary.json")
    junit = args.junit or (release.OUT / "targeted_tests.xml")
    out.parent.mkdir(parents=True, exist_ok=True)
    junit.parent.mkdir(parents=True, exist_ok=True)
    files = list(release.TARGETED_TEST_FILES)
    missing = [relative for relative in files if not (ROOT / relative).is_file()]
    if missing:
        raise SystemExit("Targeted test file is missing: " + ", ".join(missing))
    command = [sys.executable, "-m", "pytest", "-q", "--junitxml", str(junit), *files]
    process = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if junit.is_file():
        summary = release_provenance.summary_from_junit(
            junit,
            exit_code=process.returncode,
            command=" ".join(command),
            scope="Declared final-release test list; not the full repository test suite",
            files=files,
            out=out.parent,
        )
    else:
        summary = {
            "exit_code": process.returncode,
            "scope": "Declared final-release test list; not the full repository test suite",
            "files": files,
            "junit": junit.name,
            "junit_sha256": None,
            "command": " ".join(command),
            "interpreter": sys.executable,
            "source_identity": release_provenance.source_identity(),
            "tests": 0,
            "passed": 0,
            "failures": 0,
            "errors": 1,
            "skipped": 0,
        }
    summary["created_utc"] = datetime.now(timezone.utc).isoformat()
    summary["stdout_tail"] = process.stdout[-4000:]
    summary["stderr_tail"] = process.stderr[-4000:]
    if process.returncode == 0:
        release_provenance.validate_summary(summary, "targeted", out.parent)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({key: summary[key] for key in ["exit_code", "tests", "passed", "failures", "errors", "skipped", "junit_sha256"]}))
    return 0 if process.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
