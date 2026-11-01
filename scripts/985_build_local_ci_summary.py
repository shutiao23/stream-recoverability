#!/usr/bin/env python3
"""Compose the local CI-equivalent summary from real JUnit, ruff and gates."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_provenance

DEFAULT_OUT = ROOT / "results/final_release_20261101_r2"


def run(command: list[str], out_path: Path | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src" + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    process = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, env=env)
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(process.stdout)
    return process


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    ruff_path = out / "ruff_current.json"
    ruff = run(["ruff", "check", "--select", "E4,E7,E9,F", "src", "--output-format", "json"], ruff_path)
    ruff_findings = json.loads(ruff_path.read_text()) if ruff_path.is_file() else []
    source_check = {
        "command": "ruff check --select E4,E7,E9,F src",
        "exit_code": int(ruff.returncode),
        "findings": len(ruff_findings),
        "report": ruff_path.name,
        "report_sha256": release_provenance.sha256_file(ruff_path) if ruff_path.is_file() else None,
    }

    full_pytest_path = out / "full_pytest_summary.json"
    if not full_pytest_path.is_file():
        raise SystemExit("Run scripts/984_full_pytest_summary.py first")
    full_pytest = json.loads(full_pytest_path.read_text())
    release_provenance.validate_summary(full_pytest, "full_pytest")
    junit_path = out / full_pytest["junit"]
    if not junit_path.is_file():
        raise SystemExit("Full pytest JUnit file is missing")
    if release_provenance.sha256_file(junit_path) != full_pytest["junit_sha256"]:
        raise SystemExit("Full pytest JUnit hash differs from its summary")

    evidence = {
        "evidence_snapshot_inventory.json": [
            sys.executable, "scripts/25_build_evidence_snapshot.py",
            "--output", str(out / "evidence_snapshot_inventory.json"),
        ],
        "restricted_hosting_audit_inventory.json": [
            sys.executable, "scripts/26_audit_restricted_hosting.py",
            "--output", str(out / "restricted_hosting_audit_inventory.json"),
        ],
        "submission_gate_inventory_only.json": [
            sys.executable, "scripts/27_submission_gate.py", "--allow-no-go",
            "--rights-audit", str(out / "restricted_hosting_audit_inventory.json"),
            "--output", str(out / "submission_gate_inventory_only.json"),
        ],
    }
    commands = []
    outputs = {}
    for name, command in evidence.items():
        process = run(command)
        commands.append("PYTHONPATH=src " + " ".join(command))
        path = out / name
        if not path.is_file():
            raise SystemExit("Evidence gate output is missing: " + name)
        outputs[name] = release_provenance.sha256_file(path)
        if process.returncode != 0:
            raise SystemExit("Evidence gate failed: " + name)
    decision = json.loads((out / "submission_gate_inventory_only.json").read_text())["decision"]
    evidence_summary = {
        "commands": commands,
        "decision": decision,
        "outputs": outputs,
        "note": "The committed results/audits/submission_gate.json retains the no_go submission state. This inventory_only run is a local --allow-no-go gate execution, not a claim that author or rights blockers are resolved.",
    }
    status = "passed" if source_check["exit_code"] == 0 and source_check["findings"] == 0 and decision == "inventory_only" else "failed"
    summary = {
        "schema": "local_ci_equivalent_v2",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Local equivalent of the declared CI sequence; not a remote GitHub Actions run for this revision.",
        "source_check": source_check,
        "full_pytest": full_pytest,
        "evidence_gates": evidence_summary,
        "status": status,
    }
    release_provenance.write_json(out / "ci_local_summary.json", summary)
    print(json.dumps({
        "status": status,
        "ruff_findings": source_check["findings"],
        "pytest": {key: full_pytest[key] for key in ["tests", "passed", "failures", "errors", "skipped", "exit_code"]},
        "gate_decision": decision,
    }))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
