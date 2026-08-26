from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import stream_recoverability.experiments.t2_chunk_executor_v4 as chunk_v4
from stream_recoverability.experiments.t2_batch_orchestrator import (
    AGGREGATION_LIST_SCHEMA,
    V3_CONTRACT,
    BatchOrchestrationError,
    WorkloadContractSpec,
    build_chunk_ranges,
    load_contract_spec,
    orchestrate_t2_batch,
)
from stream_recoverability.experiments.t2_recovery_benchmark import WorkItem
from stream_recoverability.experiments.t2_workload_v4 import (
    V4_RUNNER_CONTRACT_VERSION,
    V4_WORKLOAD_SCHEMA,
    V4FreezeBlocked,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path, *, n_items: int = 12) -> dict[str, Any]:
    workload = {
        "manifest_schema": V3_CONTRACT.workload_manifest_schema,
        "runner_contract_version": "test_runner_v1",
        "sealed_temperature_records_read": False,
        "sealed_input_roots_allowed": [],
        "tier_1": {
            "n_work_items": n_items,
            "work_item_identity_sha256": "a" * 64,
        },
    }
    workload_path = tmp_path / "workload.json"
    workload_path.write_text(json.dumps(workload), encoding="utf-8")
    design = tmp_path / "design.yaml"
    design.write_text("design: test\n", encoding="utf-8")
    return {
        "workload": workload_path,
        "design": design,
        "state": tmp_path / "batch/state.json",
        "chunks": tmp_path / "chunks",
        "sha": _sha(workload_path),
        "calls": [],
    }


def _fake_executor(fixture: dict[str, Any], *, fail_start: int | None = None):
    def execute(**kwargs: Any) -> dict[str, Any]:
        start = int(kwargs["start_ordinal"])
        end = int(kwargs["end_ordinal_exclusive"])
        fixture["calls"].append((start, end))
        if start == fail_start:
            raise RuntimeError("controlled failure")
        manifest = {
            "manifest_schema": V3_CONTRACT.chunk_manifest_schema,
            "workload_manifest_sha256": fixture["sha"],
            "runner_contract_version": "test_runner_v1",
            "start_ordinal": start,
            "end_ordinal_exclusive": end,
            "n_records": end - start,
            "completeness": "complete",
            "sealed_temperature_records_read": False,
            "formal_evidence": False,
            "passed": False,
        }
        chunk_dir = Path(kwargs["output_dir"]) / f"chunk_{start:07d}_{end:07d}"
        chunk_dir.mkdir(parents=True)
        (chunk_dir / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return manifest

    return execute


def _run(fixture: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    kwargs = {
        "repo_root": fixture["workload"].parent,
        "workload_manifest_path": fixture["workload"],
        "design_path": fixture["design"],
        "state_path": fixture["state"],
        "chunks_output_dir": fixture["chunks"],
        "expected_workload_sha256": fixture["sha"],
        "chunk_size": 5,
    }
    kwargs.update(overrides)
    return orchestrate_t2_batch(**kwargs)


def test_ranges_are_disjoint_contiguous_and_production_bounded() -> None:
    assert build_chunk_ranges(0, 12_001, 5_000) == [
        (0, 5_000),
        (5_000, 10_000),
        (10_000, 12_001),
    ]
    with pytest.raises(BatchOrchestrationError, match="between 1 and 5000"):
        build_chunk_ranges(0, 1, 5_001)


def test_dry_run_writes_atomic_plan_and_aggregation_list_without_execution(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    state = _run(fixture)
    assert state["status"] == "planned"
    assert state["full_workload"] is True
    assert state["planned_chunk_count"] == 3
    assert [(row["start_ordinal"], row["end_ordinal_exclusive"]) for row in state["chunks"]] == [
        (0, 5),
        (5, 10),
        (10, 12),
    ]
    aggregation = json.loads(
        fixture["state"].with_name("aggregation_chunk_manifests.json").read_text()
    )
    assert aggregation["manifest_schema"] == AGGREGATION_LIST_SCHEMA
    assert aggregation["chunk_manifest_paths"] == []
    assert aggregation["ready_for_aggregation"] is False
    assert aggregation["formal_evidence"] is False
    assert not list(fixture["state"].parent.glob("*.tmp"))


def test_execution_requires_exact_acknowledgements_and_explicit_full_gate(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    common = {
        "execute": True,
        "acknowledge_item_count": 12,
        "acknowledge_chunk_count": 3,
        "chunk_executor": _fake_executor(fixture),
    }
    with pytest.raises(BatchOrchestrationError, match="allow_full_workload"):
        _run(fixture, **common)
    with pytest.raises(BatchOrchestrationError, match="item-count"):
        _run(
            fixture,
            **{**common, "allow_full_workload": True, "acknowledge_item_count": 11},
        )
    with pytest.raises(BatchOrchestrationError, match="chunk-count"):
        _run(
            fixture,
            **{**common, "allow_full_workload": True, "acknowledge_chunk_count": 2},
        )
    assert fixture["calls"] == []


def test_two_small_chunks_execute_and_resume_without_duplicate_calls(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    executor = _fake_executor(fixture)
    kwargs = {
        "start_ordinal": 2,
        "end_ordinal_exclusive": 6,
        "chunk_size": 2,
        "execute": True,
        "max_workers": 2,
        "acknowledge_item_count": 12,
        "acknowledge_chunk_count": 2,
        "chunk_executor": executor,
    }
    state = _run(fixture, **kwargs)
    assert state["status"] == "complete"
    assert sorted(fixture["calls"]) == [(2, 4), (4, 6)]
    aggregation_path = fixture["state"].with_name("aggregation_chunk_manifests.json")
    aggregation = json.loads(aggregation_path.read_text())
    assert aggregation["completed_chunk_count"] == 2
    assert aggregation["ready_for_aggregation"] is True
    assert len(aggregation["chunk_manifest_paths"]) == 2

    fixture["calls"].clear()
    resumed = _run(fixture, **{**kwargs, "resume": True})
    assert resumed["status"] == "complete"
    assert fixture["calls"] == []


def test_failure_stops_new_chunks_and_explicit_resume_finishes(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    kwargs = {
        "start_ordinal": 0,
        "end_ordinal_exclusive": 6,
        "chunk_size": 2,
        "execute": True,
        "max_workers": 1,
        "acknowledge_item_count": 12,
        "acknowledge_chunk_count": 3,
    }
    with pytest.raises(BatchOrchestrationError, match="stopped after"):
        _run(fixture, **kwargs, chunk_executor=_fake_executor(fixture, fail_start=0))
    state = json.loads(fixture["state"].read_text())
    assert [row["status"] for row in state["chunks"]] == [
        "failed",
        "planned",
        "planned",
    ]
    assert fixture["calls"] == [(0, 2)]

    fixture["calls"].clear()
    state = _run(
        fixture,
        **kwargs,
        resume=True,
        chunk_executor=_fake_executor(fixture),
    )
    assert state["status"] == "complete"
    assert fixture["calls"] == [(0, 2), (2, 4), (4, 6)]


def test_v4_resume_revalidates_result_bytes_and_frozen_identities(
    tmp_path: Path, monkeypatch
) -> None:
    fixture = _fixture(tmp_path, n_items=1)
    item_id = "v4-item"
    source = WorkItem(
        ordinal=0,
        item_id="source-item",
        network_id="network",
        role="development",
        source_key="open",
        target_station="station",
        model="donor_regression",
        gap_length=7,
        placement=0,
        start_index=100,
        information_condition="D",
    )
    index_path = tmp_path / "item_index.parquet"
    pd.DataFrame(
        [
            {
                "ordinal": 0,
                "item_id": item_id,
                "meteorology_lag_days": "none",
                "source_item_json": json.dumps(asdict(source), sort_keys=True),
            }
        ]
    ).to_parquet(index_path, index=False)
    identity = hashlib.sha256(f"{item_id}\n".encode()).hexdigest()
    workload = {
        "manifest_schema": V4_WORKLOAD_SCHEMA,
        "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
        "sealed_temperature_records_read": False,
        "sealed_input_roots_allowed": [],
        "n_work_items": 1,
        "work_item_identity_sha256": identity,
        "item_index": {"path": index_path.name},
        "execution_code_inventory": {"inventory_sha256": "9" * 64},
    }
    fixture["workload"].write_text(json.dumps(workload), encoding="utf-8")
    fixture["sha"] = _sha(fixture["workload"])
    contract = WorkloadContractSpec(
        name="v4",
        workload_manifest_schema=V4_WORKLOAD_SCHEMA,
        chunk_manifest_schema=chunk_v4.V4_CHUNK_SCHEMA,
        item_count_pointer="/n_work_items",
        item_identity_sha256_pointer="/work_item_identity_sha256",
        executor_adapter="t2_v91_chunk_executor_v4",
    )

    def execute(**kwargs: Any) -> dict[str, Any]:
        directory = Path(kwargs["output_dir"]) / "chunk_0000000_0000001"
        directory.mkdir(parents=True)
        frame = pd.DataFrame(
            [
                {
                    **asdict(source),
                    "ordinal": 0,
                    "item_id": item_id,
                    "source_v3_item_id": source.item_id,
                    "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
                    "status": "complete",
                    "auxiliary_corpus_plan_sha256": "1" * 64,
                    "auxiliary_corpus_plan_file_sha256": "2" * 64,
                    "auxiliary_network_manifest_sha256": "3" * 64,
                    "coverage_semantics_sha256": "4" * 64,
                    "pre_score_freeze_sha256": "5" * 64,
                    "meteorology_lag_days": None,
                    "mae_deg_c": 1.0,
                    "climatology_mae_deg_c": 2.0,
                    "achieved_skill": 0.5,
                    "n_scored": 7,
                    "prediction_sha256": "6" * 64,
                    "sealed_temperature_records_read": False,
                }
            ]
        )
        result_path = directory / "results.csv"
        frame.to_csv(result_path, index=False)
        identities = [{"ordinal": 0, "item_id": item_id}]
        manifest = {
            "manifest_schema": chunk_v4.V4_CHUNK_SCHEMA,
            "workload_manifest_sha256": fixture["sha"],
            "workload_item_identity_sha256": identity,
            "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
            "item_index_file_sha256": "7" * 64,
            "coverage_semantics_sha256": "4" * 64,
            "auxiliary_corpus_plan_sha256": "1" * 64,
            "auxiliary_corpus_plan_file_sha256": "2" * 64,
            "auxiliary_network_bindings_sha256": "8" * 64,
            "auxiliary_network_bindings": {
                "network": {"network_manifest_sha256": "3" * 64}
            },
            "input_sha256_by_network_sha256": "a" * 64,
            "input_sha256_by_network": {"network": "b" * 64},
            "pre_score_freeze_sha256": "5" * 64,
            "execution_head_commit": "c" * 40,
            "execution_code_inventory_sha256": "9" * 64,
            "chunk_identity_sha256": "d" * 64,
            "start_ordinal": 0,
            "end_ordinal_exclusive": 1,
            "n_records": 1,
            "results_format": "csv",
            "results_path": result_path.name,
            "results_sha256": _sha(result_path),
            "ordinal_item_identity_sha256": chunk_v4._canonical_sha(identities),
            "item_id_stream_sha256": chunk_v4._item_stream_sha(identities),
            "first_item_id": item_id,
            "last_item_id": item_id,
            "completeness": "complete",
            "sealed_temperature_records_read": False,
            "formal_evidence": False,
            "passed": False,
        }
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return manifest

    monkeypatch.setattr(
        chunk_v4,
        "_validate_execution_inventory",
        lambda *_: ("c" * 40, "9" * 64),
    )
    common = {
        "contract": contract,
        "chunk_size": 1,
        "execute": True,
        "allow_full_workload": True,
        "acknowledge_item_count": 1,
        "acknowledge_chunk_count": 1,
        "chunk_executor": execute,
    }
    assert _run(fixture, **common)["status"] == "complete"
    result_path = fixture["chunks"] / "chunk_0000000_0000001/results.csv"
    result_path.unlink()
    with pytest.raises(V4FreezeBlocked, match="result table is missing"):
        _run(fixture, **common, resume=True)


def test_future_contract_is_parameterized_but_execute_fails_without_adapter(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, n_items=4)
    future = WorkloadContractSpec(
        name="future_v4",
        workload_manifest_schema="t2_open_role_workload_v4",
        chunk_manifest_schema="t2_result_chunk_v4",
        item_count_pointer="/work/n",
        item_identity_sha256_pointer="/work/identity_sha256",
        executor_adapter=None,
    )
    spec_path = tmp_path / "v4_contract.json"
    spec_path.write_text(json.dumps(future.__dict__), encoding="utf-8")
    assert load_contract_spec(spec_path) == future
    payload = {
        "manifest_schema": future.workload_manifest_schema,
        "runner_contract_version": "future_runner_v4",
        "sealed_temperature_records_read": False,
        "sealed_input_roots_allowed": [],
        "work": {"n": 4, "identity_sha256": "c" * 64},
    }
    fixture["workload"].write_text(json.dumps(payload), encoding="utf-8")
    fixture["sha"] = _sha(fixture["workload"])
    state = _run(fixture, contract=future, chunk_size=2)
    assert state["contract"]["name"] == "future_v4"
    with pytest.raises(BatchOrchestrationError, match="no approved chunk executor"):
        _run(
            fixture,
            contract=future,
            chunk_size=2,
            execute=True,
            allow_full_workload=True,
            acknowledge_item_count=4,
            acknowledge_chunk_count=2,
        )


def test_v4_executor_adapter_uses_the_v4_call_signature(
    tmp_path: Path, monkeypatch
) -> None:
    fixture = _fixture(tmp_path, n_items=4)
    contract = WorkloadContractSpec(
        name="v4",
        workload_manifest_schema="t2_open_role_workload_v4",
        chunk_manifest_schema="t2_result_chunk_v4",
        item_count_pointer="/n_work_items",
        item_identity_sha256_pointer="/work_item_identity_sha256",
        executor_adapter="t2_v91_chunk_executor_v4",
    )
    payload = {
        "manifest_schema": contract.workload_manifest_schema,
        "runner_contract_version": "future_runner_v4",
        "sealed_temperature_records_read": False,
        "sealed_input_roots_allowed": [],
        "n_work_items": 4,
        "work_item_identity_sha256": "c" * 64,
    }
    fixture["workload"].write_text(json.dumps(payload), encoding="utf-8")
    fixture["sha"] = _sha(fixture["workload"])
    monkeypatch.setattr(
        chunk_v4,
        "_validate_execution_inventory",
        lambda *_: ("a" * 40, "b" * 64),
    )

    def executor(**kwargs: Any) -> dict[str, Any]:
        assert "design_path" not in kwargs
        assert "execution_mode" not in kwargs
        start = int(kwargs["start_ordinal"])
        end = int(kwargs["end_ordinal_exclusive"])
        manifest = {
            "manifest_schema": contract.chunk_manifest_schema,
            "workload_manifest_sha256": fixture["sha"],
            "runner_contract_version": "future_runner_v4",
            "start_ordinal": start,
            "end_ordinal_exclusive": end,
            "n_records": end - start,
            "completeness": "complete",
                "sealed_temperature_records_read": False,
                "execution_head_commit": "a" * 40,
                "execution_code_inventory_sha256": "b" * 64,
                "formal_evidence": False,
            "passed": False,
        }
        directory = Path(kwargs["output_dir"]) / f"chunk_{start:07d}_{end:07d}"
        directory.mkdir(parents=True)
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return manifest

    state = _run(
        fixture,
        contract=contract,
        chunk_size=2,
        max_workers=1,
        execute=True,
        allow_full_workload=True,
        acknowledge_item_count=4,
        acknowledge_chunk_count=2,
        chunk_executor=executor,
    )
    assert state["status"] == "complete"


def test_wrong_workload_sha_and_sealed_paths_fail_before_state(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    with pytest.raises(BatchOrchestrationError, match="SHA-256 acknowledgement mismatch"):
        _run(fixture, expected_workload_sha256="0" * 64)
    fixture["state"] = tmp_path / "sealed_outputs/state.json"
    with pytest.raises(BatchOrchestrationError, match="sealed-path"):
        _run(fixture)
