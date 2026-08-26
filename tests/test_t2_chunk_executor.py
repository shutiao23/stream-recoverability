from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import pytest

import stream_recoverability.experiments.t2_chunk_executor as chunk_module
from stream_recoverability.experiments.t2_chunk_executor import (
    MAX_CHUNK_ITEMS,
    ChunkExecutionError,
    execute_t2_chunk,
)
from stream_recoverability.experiments.t2_recovery_benchmark import (
    RUNNER_CONTRACT_VERSION,
    OpenNetwork,
    WorkItem,
)
from stream_recoverability.experiments.t2_result_aggregation import (
    aggregate_t2_results,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def _stream_sha(items: list[WorkItem]) -> str:
    digest = hashlib.sha256()
    for item in items:
        digest.update(item.item_id.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    design = tmp_path / "design.yaml"
    design.write_text("design_id: design_freeze_v9\n", encoding="utf-8")
    design_sha = _sha(design)
    input_sha = "b" * 64
    network = OpenNetwork(
        network_id="huc8_test",
        role="development",
        source_key="open_role_qc/failure_closure6/development",
        wide_path="open/daily_wide_qc.csv",
        wide_sha256=input_sha,
        manifest_path="open/network_manifest.json",
        n_days=2_000,
        n_stations=1,
    )
    items: list[WorkItem] = []
    for ordinal in range(3):
        identity = {
            "design_sha256": design_sha,
            "input_sha256": input_sha,
            "network_id": network.network_id,
            "target_station": "station_a",
            "model": "donor_regression",
            "gap_length": 30,
            "placement": ordinal,
            "start_index": 900 + ordinal * 40,
            "information_condition": "B_union_D",
            "task": "offline_archival",
            "geometry": "artificial_stress",
            "runner_contract_version": RUNNER_CONTRACT_VERSION,
        }
        items.append(
            WorkItem(
                ordinal=ordinal,
                item_id=_canonical_sha([identity])[:24],
                network_id=network.network_id,
                role=network.role,
                source_key=network.source_key,
                target_station="station_a",
                model="donor_regression",
                gap_length=30,
                placement=ordinal,
                start_index=900 + ordinal * 40,
                information_condition="B_union_D",
            )
        )
    inventory = {
        "sealed_input_roots_allowed": [],
        "qualification_mode": "failure_closure6",
        "n_networks_eligible": 1,
    }
    workload = {
        "manifest_schema": "t2_v91_open_role_workload_v3",
        "runner_contract_version": RUNNER_CONTRACT_VERSION,
        "design_sha256": design_sha,
        "sealed_temperature_records_read": False,
        "sealed_input_roots_allowed": [],
        "input_inventory": inventory,
        "n_networks": 1,
        "network_ids": [network.network_id],
        "tier_1": {
            "n_work_items": len(items),
            "work_item_identity_sha256": _stream_sha(items),
            "online_causal_status": "ready",
        },
        "geometry_dependencies": {
            "artificial_stress": "ready",
            "natural_outage": "ready_frozen_catalog_bound",
            "adversarial_stress": "ready_frozen_catalog_bound",
        },
    }
    workload_path = tmp_path / "workload.json"
    workload_path.write_text(json.dumps(workload), encoding="utf-8")

    monkeypatch.setattr(
        chunk_module,
        "load_v91_budget",
        lambda _repo: {"design_sha256": design_sha},
    )
    monkeypatch.setattr(
        chunk_module,
        "discover_failure_closure_networks",
        lambda _repo: ([network], inventory),
    )
    monkeypatch.setattr(
        chunk_module,
        "iter_all_work_items",
        lambda _repo, _networks, _budget: iter(items),
    )

    calls: list[int] = []

    def fake_execute(_repo: Path, selected_network: OpenNetwork, item: WorkItem):
        calls.append(item.ordinal)
        return {
            **asdict(item),
            "input_sha256": selected_network.wide_sha256,
            "runner_contract_version": RUNNER_CONTRACT_VERSION,
            "status": "complete",
            "mae_deg_c": 0.5 + item.ordinal,
            "achieved_skill": 0.25,
            "sealed_temperature_records_read": False,
        }

    monkeypatch.setattr(chunk_module, "execute_item", fake_execute)
    return {
        "design": design,
        "workload": workload_path,
        "items": items,
        "calls": calls,
    }


@pytest.mark.parametrize("results_format", ["parquet", "csv"])
def test_chunk_is_single_table_sha_bound_and_aggregation_reads_partial_as_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, results_format: str
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    output = tmp_path / "chunks"
    manifest = execute_t2_chunk(
        repo_root=tmp_path,
        workload_manifest_path=fixture["workload"],
        design_path=fixture["design"],
        output_dir=output,
        start_ordinal=0,
        end_ordinal_exclusive=2,
        results_format=results_format,
    )
    chunk = output / "chunk_0000000_0000002"
    table = chunk / f"results.{results_format}"
    assert manifest["manifest_schema"] == "t2_v91_result_chunk_v1"
    assert manifest["start_ordinal"] == 0
    assert manifest["end_ordinal_exclusive"] == 2
    assert manifest["ordinal_contiguous"] is True
    assert manifest["n_records"] == 2
    assert manifest["results_sha256"] == _sha(table)
    assert manifest["passed"] is False
    assert list(chunk.glob("*.json")) == [chunk / "manifest.json"]
    frame = pd.read_parquet(table) if results_format == "parquet" else pd.read_csv(table)
    assert frame["ordinal"].tolist() == [0, 1]

    readiness = aggregate_t2_results(
        workload_manifest_path=fixture["workload"],
        design_path=fixture["design"],
        output_dir=tmp_path / "aggregation",
        chunk_manifest_paths=[chunk / "manifest.json"],
    )
    assert readiness["status"] == "blocked"
    assert readiness["passed"] is False
    assert readiness["observed_result_records"] == 2
    assert "result_workload_incomplete_2_of_3" in readiness["blockers"]
    assert readiness["inference_tables_written"] is False


def test_same_chunk_resumes_without_execution_and_changed_table_hash_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    kwargs = {
        "repo_root": tmp_path,
        "workload_manifest_path": fixture["workload"],
        "design_path": fixture["design"],
        "output_dir": tmp_path / "chunks",
        "start_ordinal": 0,
        "end_ordinal_exclusive": 2,
        "results_format": "parquet",
    }
    first = execute_t2_chunk(**kwargs)
    assert fixture["calls"] == [0, 1]
    fixture["calls"].clear()
    second = execute_t2_chunk(**kwargs)
    assert second == first
    assert fixture["calls"] == []

    table = tmp_path / "chunks/chunk_0000000_0000002/results.parquet"
    table.write_bytes(table.read_bytes() + b"drift")
    with pytest.raises(ChunkExecutionError, match="result-table SHA-256 mismatch"):
        execute_t2_chunk(**kwargs)


def test_range_limit_and_sealed_output_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    common = {
        "repo_root": tmp_path,
        "workload_manifest_path": fixture["workload"],
        "design_path": fixture["design"],
        "results_format": "parquet",
    }
    with pytest.raises(ChunkExecutionError, match="production maximum"):
        execute_t2_chunk(
            **common,
            output_dir=tmp_path / "chunks",
            start_ordinal=0,
            end_ordinal_exclusive=MAX_CHUNK_ITEMS + 1,
        )
    with pytest.raises(ChunkExecutionError, match="sealed-path"):
        execute_t2_chunk(
            **common,
            output_dir=tmp_path / "sealed_results",
            start_ordinal=0,
            end_ordinal_exclusive=1,
        )


def test_runner_cannot_change_global_ordinal_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    items = list(fixture["items"])
    broken = [items[0], WorkItem(**{**asdict(items[1]), "ordinal": 7})]
    monkeypatch.setattr(
        chunk_module,
        "iter_all_work_items",
        lambda _repo, _networks, _budget: iter(broken),
    )
    with pytest.raises(ChunkExecutionError, match="global ordinal continuity"):
        execute_t2_chunk(
            repo_root=tmp_path,
            workload_manifest_path=fixture["workload"],
            design_path=fixture["design"],
            output_dir=tmp_path / "chunks",
            start_ordinal=0,
            end_ordinal_exclusive=2,
        )
