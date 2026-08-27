from __future__ import annotations

import json
from pathlib import Path

import pytest

from stream_recoverability.experiments.w8_failure_closure import (
    ACTION_KEEP,
    ACTION_RETITLE,
    DEVELOPMENT_TITLE,
    FORBIDDEN_ACTIONS,
    GO_NO_GO,
    PURPOSE,
    W8FailureClosureError,
    operator_or_phi_retune_licensed,
    w8_failure_closure_action,
    write_w8_failure_closure,
    write_w8_failure_closure_from_w7_path,
)


REQUIRED_FALSE = (
    "passed",
    "formal_evidence",
    "headline_claim_licensed",
    "confirmatory_eligible",
    "operator_retuned",
    "twin_e_retuned",
    "phi_or_isolation_retuned",
    "design_freeze_v4_retargeted",
    "catalog_98_name_huc2_downloaded",
    "historical_two_network_manuscript_retitled",
    "slice_is_confirmatory_t2",
    "sealed_outcomes_opened",
    "new_temperatures_downloaded",
)


def _w7_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "n_networks": 1,
        "operator_incremental_r2_vs_donor_r2_only": 0.03997347826091091,
        "w8_failure_closure_trigger": True,
        "w8_failure_closure_reason": "operator_incremental_r2_vs_donor_r2_only_lt_0.05",
        "operator_retuned": False,
        "passed": False,
        "purpose": "development_slice_not_evidence",
        "slice_is_confirmatory_t2": False,
    }
    payload.update(overrides)
    return payload


def test_increment_below_floor_is_retitle_not_retune() -> None:
    assert w8_failure_closure_action(0.02) == ACTION_RETITLE
    assert w8_failure_closure_action(0.049) == ACTION_RETITLE
    assert w8_failure_closure_action(0.05) == ACTION_KEEP
    assert w8_failure_closure_action(0.20) == ACTION_KEEP
    assert operator_or_phi_retune_licensed(0.02) is False
    assert operator_or_phi_retune_licensed(0.20) is False


def test_write_w8_records_retitle_and_keeps_every_pass_flag_false(tmp_path: Path) -> None:
    manifest = write_w8_failure_closure(
        output_dir=tmp_path / "w8",
        w7_manifest=_w7_manifest(),
    )
    for key in REQUIRED_FALSE:
        assert manifest[key] is False
    assert manifest["w8_failure_closure_action"] == ACTION_RETITLE
    assert manifest["w8_failure_closure_action"] not in FORBIDDEN_ACTIONS
    assert manifest["operator_or_phi_retune_licensed"] is False
    assert manifest["go_no_go"] == GO_NO_GO
    assert manifest["purpose"] == PURPOSE
    assert manifest["development_title"] == DEVELOPMENT_TITLE
    assert manifest["n_networks"] == 1
    assert manifest["network_inference_status"] == "withheld_n_lt_100_network_interval"
    assert manifest["broader_w7_may_revise_increment"] is True
    assert manifest["broader_w7_may_not_retune"] is True
    assert (tmp_path / "w8" / "w8_failure_closure_manifest.json").is_file()


def test_write_w8_refuses_a_passed_or_retuned_w7_slice(tmp_path: Path) -> None:
    with pytest.raises(W8FailureClosureError, match="passed T2"):
        write_w8_failure_closure(
            output_dir=tmp_path / "w8",
            w7_manifest=_w7_manifest(passed=True),
        )
    with pytest.raises(W8FailureClosureError, match="retuned"):
        write_w8_failure_closure(
            output_dir=tmp_path / "w8",
            w7_manifest=_w7_manifest(operator_retuned=True),
        )
    with pytest.raises(W8FailureClosureError, match="confirmatory"):
        write_w8_failure_closure(
            output_dir=tmp_path / "w8",
            w7_manifest=_w7_manifest(slice_is_confirmatory_t2=True),
        )


def test_write_w8_refuses_missing_trigger_when_increment_is_below_floor(
    tmp_path: Path,
) -> None:
    with pytest.raises(W8FailureClosureError, match="trigger"):
        write_w8_failure_closure(
            output_dir=tmp_path / "w8",
            w7_manifest=_w7_manifest(w8_failure_closure_trigger=False),
        )


def test_write_w8_from_committed_slice(tmp_path: Path) -> None:
    source = tmp_path / "w7_open_role_bd_slice_manifest.json"
    source.write_text(json.dumps(_w7_manifest()), encoding="utf-8")
    manifest = write_w8_failure_closure_from_w7_path(
        repo_root=tmp_path,
        output_dir=tmp_path / "w8",
        w7_manifest_path=source,
    )
    assert manifest["w8_failure_closure_action"] == ACTION_RETITLE
    assert manifest["passed"] is False
    assert "donor R²" in manifest["development_title_not"]
