from __future__ import annotations

import copy
import json
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import pytest

from stream_recoverability.data.foen_sealed_corpus import (
    DEFAULT_REGISTRY as DEFAULT_FOEN_REGISTRY,
)
from stream_recoverability.data.sealed_corpus import (
    DEFAULT_REGISTRY as DEFAULT_HUC8_REGISTRY,
)
from stream_recoverability.experiments.sealed_evaluation_readiness import (
    CLAIM_ACKNOWLEDGEMENT,
    READINESS_SCHEMA,
    SealedReadinessError,
    _audit_foen_registry,
    _audit_huc8_registry,
    build_readiness_manifest,
    claim_evaluate_once,
)


@lru_cache(maxsize=1)
def _default_inventory() -> dict[str, object]:
    huc8 = _audit_huc8_registry(DEFAULT_HUC8_REGISTRY / "sealed")
    foen = _audit_foen_registry(DEFAULT_FOEN_REGISTRY)
    return {
        "north_america_huc8": huc8,
        "foen_non_north_america": foen,
        "n_networks_total": huc8["n_networks"] + foen["n_networks"],
        "eligibility_warning": (
            "registry completeness is custody availability, not post-unseal "
            "temperature QC eligibility"
        ),
    }


def _ready(
    inventory: dict[str, object] | None = None,
) -> dict[str, object]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    relative = "configs/design_freeze_v9.yaml"
    blob = subprocess.run(
        ["git", "rev-parse", f"HEAD:{relative}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {
        "manifest_schema": READINESS_SCHEMA,
        "ready_for_unseal": True,
        "blockers": [],
        "sealed_registry_inventory": copy.deepcopy(
            inventory if inventory is not None else _default_inventory()
        ),
        "git_commit_before_unseal": {
            "head_commit": head,
            "all_required_paths_committed_unchanged": True,
            "required_paths": [
                {"path": relative, "head_blob": blob, "worktree_blob": blob}
            ],
        },
    }


def test_repository_audit_is_blocked_without_model_and_complete_aggregation() -> None:
    manifest = build_readiness_manifest()
    assert manifest["status"] == "blocked"
    assert manifest["ready_for_unseal"] is False
    assert manifest["sealed_outcomes_opened"] is False
    assert manifest["sealed_objects_opened_or_statted_by_audit"] is False
    assert "sealed_model_freeze_manifest_missing" in manifest["blockers"]
    assert "t2_primary_aggregation_not_ready" in manifest["blockers"]
    inventory = manifest["sealed_registry_inventory"]
    assert inventory["north_america_huc8"]["n_networks"] == 44
    assert inventory["north_america_huc8"]["n_objects"] == 228
    assert inventory["foen_non_north_america"]["n_networks"] == 10
    assert inventory["foen_non_north_america"]["n_objects"] == 2652
    assert inventory["foen_non_north_america"]["daily_qc_eligibility"].startswith(
        "unknown"
    )


def test_once_claim_refuses_a_blocked_manifest(tmp_path: Path) -> None:
    value = _ready()
    value["ready_for_unseal"] = False
    value["blockers"] = ["not_ready"]
    with pytest.raises(SealedReadinessError, match="not unconditionally ready"):
        claim_evaluate_once(
            value,
            lock_path=tmp_path / "once.json",
            acknowledgement=CLAIM_ACKNOWLEDGEMENT,
        )


def test_once_claim_requires_exact_acknowledgement(tmp_path: Path) -> None:
    with pytest.raises(SealedReadinessError, match="exact"):
        claim_evaluate_once(
            _ready(),
            lock_path=tmp_path / "once.json",
            acknowledgement="yes",
        )


def test_once_claim_is_exclusive_and_contains_no_outcomes(tmp_path: Path) -> None:
    lock = tmp_path / "once.json"
    payload = claim_evaluate_once(
        _ready(),
        lock_path=lock,
        acknowledgement=CLAIM_ACKNOWLEDGEMENT,
    )
    assert payload["status"] == "started_before_any_sealed_read"
    assert payload["sealed_outcomes_opened_at_lock_creation"] is False
    assert payload["rerun_permitted"] is False
    with pytest.raises(SealedReadinessError, match="already exists"):
        claim_evaluate_once(
            _ready(),
            lock_path=lock,
            acknowledgement=CLAIM_ACKNOWLEDGEMENT,
        )


def test_registry_tamper_between_audit_and_claim_fails_closed(tmp_path: Path) -> None:
    huc8_root = tmp_path / "huc8_registry"
    foen_root = tmp_path / "foen_registry"
    shutil.copytree(DEFAULT_HUC8_REGISTRY / "sealed", huc8_root)
    shutil.copytree(DEFAULT_FOEN_REGISTRY, foen_root)
    huc8 = _audit_huc8_registry(huc8_root)
    foen = _audit_foen_registry(foen_root)
    inventory = {
        "north_america_huc8": huc8,
        "foen_non_north_america": foen,
        "n_networks_total": huc8["n_networks"] + foen["n_networks"],
        "eligibility_warning": (
            "registry completeness is custody availability, not post-unseal "
            "temperature QC eligibility"
        ),
    }
    target = next(huc8_root.glob("*/*.json"))
    row = json.loads(target.read_text(encoding="utf-8"))
    row["byte_count"] += 1
    target.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")

    lock = tmp_path / "once.json"
    with pytest.raises(SealedReadinessError, match="HUC8 registry changed"):
        claim_evaluate_once(
            _ready(inventory),
            lock_path=lock,
            acknowledgement=CLAIM_ACKNOWLEDGEMENT,
        )
    assert not lock.exists()
