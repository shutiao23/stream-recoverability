from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_second_confirmation_guard_withholds_before_temperature_access(tmp_path) -> None:
    readiness = tmp_path / "readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "scoring_authorized": False,
                "domain_checks": {
                    "canada": {"required": 1, "arrived": 0, "passed": False}
                },
            }
        )
    )
    output = tmp_path / "scoring"
    subprocess.run(
        [
            sys.executable,
            "scripts/131_run_second_confirmation.py",
            "--readiness",
            str(readiness),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
    )
    result = json.loads((output / "withheld.json").read_text())
    assert result["temperature_panels_read"] == 0
    assert result["outcomes_scored"] == 0
