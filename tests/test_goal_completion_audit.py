from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_goal_audit_proves_completed_work_and_keeps_real_blockers_open() -> None:
    subprocess.run(
        [sys.executable, "scripts/130_build_goal_completion_audit.py"],
        cwd=ROOT,
        check=True,
    )
    payload = json.loads(
        (ROOT / "results/audits/goal_completion_audit.json").read_text()
    )
    by_id = {row["id"]: row for row in payload["requirements"]}
    assert by_id["P1a"]["gate_passed"] is True
    assert by_id["P2a"]["gate_passed"] is True
    assert by_id["P3_candidates"]["gate_passed"] is True
    assert by_id["P3_domains"]["gate_passed"] is False
    assert by_id["P1c"]["completion_satisfied"] is True
    assert by_id["P2b"]["completion_satisfied"] is True
    assert by_id["P3_domains"]["completion_satisfied"] is False
    assert by_id["P3_scoring"]["gate_passed"] is False
    assert payload["overall_status"] == "incomplete"
