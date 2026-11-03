#!/usr/bin/env python3
"""Run the full repository test suite and write a JUnit-bound summary."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_provenance

DEFAULT_OUT = ROOT / "results/final_release_20261101_r4"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    junit = out / "full_pytest.xml"
    command = [sys.executable, "-m", "pytest", "-q", "--junitxml", str(junit)]
    process = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    summary = release_provenance.summary_from_junit(
        junit,
        exit_code=process.returncode,
        command=" ".join(command),
        scope="Full repository pytest suite; Python 3.11 environment",
        out=out,
    )
    summary["created_utc"] = datetime.now(timezone.utc).isoformat()
    summary["stdout_tail"] = process.stdout[-4000:]
    summary["stderr_tail"] = process.stderr[-4000:]
    if process.returncode == 0:
        release_provenance.validate_summary(summary, "full_pytest", out)
    release_provenance.write_json(out / "full_pytest_summary.json", summary)
    print(json.dumps({
        key: summary[key] for key in ["exit_code", "tests", "passed", "failures", "errors", "skipped", "junit_sha256"]
    }))
    return 0 if process.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
