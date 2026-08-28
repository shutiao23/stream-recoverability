from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from stream_recoverability.experiments.second_confirmation_guard import (
    SecondConfirmationGateError,
    attrition_gate_summary,
    build_authorized_readiness,
    validate_canonical_authorization,
    validate_scored_result_gate,
)

ROOT = Path(__file__).resolve().parents[1]


def test_second_confirmation_guard_withholds_before_temperature_access(
    tmp_path,
) -> None:
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


def test_forged_true_readiness_cannot_authorize_scoring(tmp_path) -> None:
    forged = tmp_path / "forged.json"
    forged.write_text(json.dumps({"scoring_authorized": True}), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/131_run_second_confirmation.py",
            "--readiness",
            str(forged),
            "--output",
            str(tmp_path / "scoring"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "canonical readiness path" in result.stderr
    assert not (tmp_path / "scoring").exists()


def test_canonical_readiness_is_recomputed_and_binds_exact_roster() -> None:
    path = ROOT / "results/development_v11/second_confirmation/readiness.json"
    readiness = json.loads(path.read_text(encoding="utf-8"))
    roster = validate_canonical_authorization(
        readiness,
        readiness_path=path,
        canonical_readiness_path=path,
        root=ROOT,
    )
    assert len(roster) == 60
    assert roster["network_id"].nunique() == 60
    assert readiness["independence_audit"]["outcome_scored_network_disjoint"] is True
    assert (
        readiness["independence_audit"]["first_confirmation_qc_only_reuse_count"] == 3
    )

    forged = dict(readiness)
    forged["qualified_networks_before_scoring"] = 61
    with pytest.raises(SecondConfirmationGateError, match="recomputed gate"):
        validate_canonical_authorization(
            forged,
            readiness_path=path,
            canonical_readiness_path=path,
            root=ROOT,
        )


def test_amended_gate_rejects_outcome_scored_network_overlap(tmp_path) -> None:
    root = tmp_path
    protocol = root / "protocol.yaml"
    protocol.write_text(
        "protocol_id: p1\ncandidate_floor: 1\nminimum_valid_scored_networks: 1\ntarget_scored_networks: [1, 2]\n",
        encoding="utf-8",
    )
    roster = pd.DataFrame(
        {
            "network_id": ["n1"],
            "provider": ["p"],
            "domain": ["temperate"],
            "qc_status": ["qualified"],
            "complete_enough": [True],
        }
    )
    roster_path = root / "readiness_roster.csv"
    roster.to_csv(roster_path, index=False)
    references = root / "references"
    references.mkdir()
    pd.DataFrame({"network_id": ["n1"]}).to_csv(
        references / "development.csv", index=False
    )
    pd.DataFrame({"network_id": []}).to_csv(references / "first.csv", index=False)
    pd.DataFrame({"network_id": []}).to_csv(references / "first_qc.csv", index=False)
    amendment = root / "amendment.yaml"
    amendment.write_text(
        """amendment_id: a2
parent_protocol_id: p1
status: frozen_pre_outcome_scoring
effective_domain_requirements:
  minimum_networks_by_domain: {temperate: 1}
invariants: {recovery_outcomes_seen_before_amendment: false}
frozen_scoring_roster:
  exact_networks: 1
  exact_networks_by_domain: {temperate: 1}
  first_confirmation_qc_only_reused: []
  independence_references:
    development_outcomes: references/development.csv
    first_confirmation_outcomes: references/first.csv
    first_confirmation_qc_panel: references/first_qc.csv
""",
        encoding="utf-8",
    )
    with pytest.raises(SecondConfirmationGateError, match="outcome-scored"):
        build_authorized_readiness(
            root=root,
            protocol_path=protocol,
            amendment_path=amendment,
            readiness_roster_path=roster_path,
            frozen_roster_path=root / "frozen.csv",
        )


def test_attrition_floor_suppresses_performance_reporting_below_40() -> None:
    failed = attrition_gate_summary(
        attempted_networks=60, attrited_networks=21, scored_networks=39
    )
    assert failed["status"] == "scored_but_invalid_below_attrition_floor"
    assert failed["performance_reporting_authorized"] is False
    passed = attrition_gate_summary(
        attempted_networks=60, attrited_networks=20, scored_networks=40
    )
    assert passed["performance_reporting_authorized"] is True
    validate_scored_result_gate(passed)
    with pytest.raises(SecondConfirmationGateError, match="status is invalid"):
        validate_scored_result_gate(failed)
