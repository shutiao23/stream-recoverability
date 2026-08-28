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
    assert by_id["P1a_all"]["gate_passed"] is True
    assert "1440" in by_id["P1a_all"]["evidence"]
    assert by_id["P2a"]["gate_passed"] is True
    assert by_id["P3_candidates"]["gate_passed"] is True
    assert by_id["P3_domains"]["gate_passed"] is True
    assert by_id["P1c"]["completion_satisfied"] is True
    assert by_id["P1f"]["completion_satisfied"] is True
    assert by_id["P1f"]["gate_passed"] is False
    assert by_id["P1f2"]["completion_satisfied"] is True
    assert by_id["P1f2"]["gate_passed"] is False
    assert by_id["P1g"]["completion_satisfied"] is True
    assert by_id["P1h"]["completion_satisfied"] is True
    assert by_id["P1h"]["gate_passed"] is False
    assert by_id["P1i"]["completion_satisfied"] is True
    assert by_id["P1i"]["gate_passed"] is False
    assert by_id["P2b"]["completion_satisfied"] is True
    assert by_id["P3_domains"]["completion_satisfied"] is True
    assert by_id["P3_canada"]["completion_satisfied"] is True
    second_summary = ROOT / "results/development_v11/second_confirmation/scoring/summary.json"
    if second_summary.is_file():
        result = json.loads(second_summary.read_text())
        expected = bool(result.get("performance_reporting_authorized", False))
        assert by_id["P3_scoring"]["gate_passed"] is expected
    else:
        assert by_id["P3_scoring"]["gate_passed"] is False
    assert by_id["P3_intervals"]["completion_satisfied"] is second_summary.is_file()
    assert by_id["P3_intervals"]["gate_passed"] is False
    assert by_id["P3_triage"]["completion_satisfied"] is second_summary.is_file()
    assert by_id["P3_triage"]["gate_passed"] is False
    if second_summary.is_file():
        second_result = json.loads(second_summary.read_text())
        assert by_id["P3_placement"]["completion_satisfied"] is (
            "placement" in second_result
        )
    assert by_id["P3_placement"]["gate_passed"] is False
    assert by_id["P3_climate_regulation"]["completion_satisfied"] is True
    assert by_id["P3_climate_regulation"]["gate_passed"] is True
    assert by_id["P4_package"]["gate_passed"] is True
    assert payload["overall_status"] == "incomplete"
