from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

import stream_recoverability.experiments.t2_chunk_executor_v4 as chunk_v4
import stream_recoverability.experiments.t2_workload_v4 as v4
from stream_recoverability.data.t2_information_corpus_acquisition_v2 import (
    NETWORK_SCHEMA_VERSION as V2_NETWORK_SCHEMA_VERSION,
)
from stream_recoverability.experiments.t2_batch_orchestrator import (
    load_contract_spec,
)
from stream_recoverability.experiments.t2_information_runner_integration import (
    load_materialized_auxiliary_v2,
)
from stream_recoverability.experiments.t2_recovery_benchmark import (
    OpenNetwork,
    WorkItem,
    discover_failure_closure_networks,
)

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "results/framework/t2_recovery_benchmark_v1/workload_manifest.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _network(network_id: str = "huc8_02040103") -> OpenNetwork:
    networks, _ = discover_failure_closure_networks(ROOT)
    return next(network for network in networks if network.network_id == network_id)


def _binding() -> v4.V2NetworkBinding:
    return v4.V2NetworkBinding(
        network_id="huc8_02040103",
        role="development",
        network_manifest_schema="t2_v91_open_role_mh_network_acquisition_v2_1",
        network_plan_sha256="1" * 64,
        network_manifest_path="open/network_manifest.json",
        network_manifest_sha256="2" * 64,
        daily_long_sha256="3" * 64,
        coverage_sha256="4" * 64,
        adapter_schema_sha256="5" * 64,
        materialization_status="materialized_partial",
    )


def _prerequisites(*, ready: bool = False) -> v4.V4Prerequisites:
    binding = _binding()
    return v4.V4Prerequisites(
        ready=ready,
        corpus_plan_path="open/corpus_request_plan.json",
        corpus_plan_file_sha256="6" * 64,
        corpus_plan_sha256="7" * 64,
        split_sha256="8" * 64,
        n_networks_expected=67,
        n_networks_terminal=67 if ready else 1,
        missing_network_ids=() if ready else ("huc8_missing",),
        invalid_networks={},
        bindings={binding.network_id: binding},
    )


def _item(condition: str, *, model: str = "donor_regression") -> WorkItem:
    return WorkItem(
        ordinal=12,
        item_id=f"v3-{condition}-{model}",
        network_id="huc8_02040103",
        role="development",
        source_key="open_role_qc/failure_closure6/development",
        target_station="01428750",
        model=model,
        gap_length=7,
        placement=0,
        start_index=100,
        information_condition=condition,
    )


def test_current_formal_freeze_is_fail_closed_and_v3_bytes_unchanged() -> None:
    before = _sha(V3)
    networks, _ = discover_failure_closure_networks(ROOT)
    readiness = v4.build_v4_readiness_manifest(
        ROOT, networks, source_v3_workload_path=V3
    )
    assert readiness["formal_workload_generated"] is False
    assert readiness["formal_result_generated"] is False
    assert readiness["auxiliary"]["n_networks_expected"] == 67
    if readiness["auxiliary"]["n_networks_terminal"] < 67:
        assert readiness["status"] == "blocked_fail_closed"
    else:
        assert readiness["status"] == "ready_for_formal_v4_freeze"
    assert _sha(V3) == before
    with pytest.raises(v4.V4FreezeBlocked, match="67 terminal"):
        list(v4.iter_v4_work_items([_item("B")], _prerequisites()))


def test_extended_items_expand_all_lags_and_bind_every_identity_component() -> None:
    prerequisites = _prerequisites(ready=True)
    base = list(
        v4.iter_v4_work_items(
            [_item("B")], prerequisites, require_full_corpus=False
        )
    )
    extended = list(
        v4.iter_v4_work_items(
            [_item("B_union_D_union_M")],
            prerequisites,
            require_full_corpus=False,
        )
    )
    assert len(base) == 1
    assert base[0].meteorology_lag_days is None
    assert [item.meteorology_lag_days for item in extended] == [-1, 0, 1]
    assert len({item.item_id for item in extended}) == 3

    changed_binding = replace(_binding(), coverage_sha256="9" * 64)
    changed = replace(
        prerequisites, bindings={changed_binding.network_id: changed_binding}
    )
    changed_items = list(
        v4.iter_v4_work_items(
            [_item("B_union_D_union_M")], changed, require_full_corpus=False
        )
    )
    assert [item.item_id for item in changed_items] != [
        item.item_id for item in extended
    ]
    assert extended[0].coverage_semantics_sha256 == v4.COVERAGE_SEMANTICS_SHA256
    assert extended[0].auxiliary_corpus_plan_sha256 == "7" * 64


def test_item_index_rejects_a_truncated_v3_stream(
    tmp_path: Path, monkeypatch
) -> None:
    source = replace(_item("B"), ordinal=0)
    digest = hashlib.sha256((source.item_id + "\n").encode()).hexdigest()
    monkeypatch.setattr(v4, "EXPECTED_V3_WORK_ITEMS", 2)
    monkeypatch.setattr(v4, "EXPECTED_V3_EXTENDED_WORK_ITEMS", 0)
    monkeypatch.setattr(v4, "EXPECTED_V4_WORK_ITEMS", 2)
    output = tmp_path / "truncated.parquet"
    with pytest.raises(v4.V4FreezeBlocked, match="count/identity"):
        v4._write_v4_item_index(
            output,
            [source],
            _prerequisites(ready=True),
            expected_v3_identity_sha256=digest,
        )
    assert not output.exists()


def test_v2_loader_accepts_only_the_legacy_source_and_schema() -> None:
    auxiliary = load_materialized_auxiliary_v2(
        ROOT, _network(), allow_legacy_pipeline_smoke=True
    )
    assert auxiliary.audit["source_contract"].startswith("legacy_nwis_v2")
    assert auxiliary.audit["manifest_schema"] in {
        "t2_v91_open_role_mh_network_acquisition_v2",
        "t2_v91_open_role_mh_network_acquisition_v2_1",
        V2_NETWORK_SCHEMA_VERSION,
    }
    assert set(auxiliary.daily_long["source"].astype(str)) <= {
        "nasa_power_daily_point",
        "usgs_legacy_nwis_dv_rdb",
    }
    assert auxiliary.audit["sealed_temperature_records_read"] is False


def test_only_declared_models_reach_extended_mh_consumer(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_execute(*args, **kwargs):
        item = args[2]
        calls.append((item.model, item.item_id))
        return {
            **item.__dict__,
            "runner_contract_version": "ignored_candidate_contract",
            "status": "candidate_complete_not_formal",
            "sealed_temperature_records_read": False,
        }

    monkeypatch.setattr(v4, "execute_materialized_information_item", fake_execute)
    auxiliary = type(
        "Auxiliary",
        (),
        {
            "audit": {
                "source_contract": "legacy_nwis_v2",
                "manifest_sha256": "2" * 64,
                "network_plan_sha256": "1" * 64,
                "daily_long_sha256": "3" * 64,
                "coverage_sha256": "4" * 64,
                "adapter_schema_sha256": "5" * 64,
            }
        },
    )()
    prerequisites = _prerequisites(ready=True)
    donor_item = next(
        iter(
            v4.iter_v4_work_items(
                [_item("B_union_D_union_M")],
                prerequisites,
                require_full_corpus=False,
            )
        )
    )
    donor_result = v4.execute_v4_item(
        ROOT, _network(), donor_item, panel=pd.DataFrame(), auxiliary=auxiliary
    )
    assert donor_result["status"] == "complete"
    assert calls == [("donor_regression", donor_item.source_v3_item.item_id)]

    unsupported = next(
        iter(
            v4.iter_v4_work_items(
                [_item("B_union_D_union_M", model="climatology")],
                prerequisites,
                require_full_corpus=False,
            )
        )
    )
    class ReferenceCache:
        def execute(self, network, item):
            return {
                **item.__dict__,
                "status": "reference_complete",
                "runner_contract_version": "wrapped",
                "sealed_temperature_records_read": False,
            }

    result = v4.execute_v4_item(
        ROOT, _network(), unsupported, base_execution_cache=ReferenceCache()
    )
    assert result["status"] == "reference_complete"
    assert calls == [("donor_regression", donor_item.source_v3_item.item_id)]


def test_nonextended_v4_item_uses_chunk_execution_cache() -> None:
    calls: list[str] = []

    class Cache:
        def execute(self, network, item):
            calls.append(item.item_id)
            return {
                **item.__dict__,
                "runner_contract_version": "v3_wrapped_below",
                "status": "complete",
                "sealed_temperature_records_read": False,
            }

    item = next(
        iter(
            v4.iter_v4_work_items(
                [_item("B")], _prerequisites(ready=True), require_full_corpus=False
            )
        )
    )
    result = v4.execute_v4_item(
        ROOT, _network(), item, base_execution_cache=Cache()
    )
    assert calls == [item.item_id]
    assert result["runner_contract_version"] == v4.V4_RUNNER_CONTRACT_VERSION

def test_v4_chunk_refuses_incomplete_auxiliary_before_creating_output(
    tmp_path: Path, monkeypatch
) -> None:
    workload = tmp_path / "workload.json"
    workload.write_text(
        json.dumps(
            {
                "manifest_schema": v4.V4_WORKLOAD_SCHEMA,
                "runner_contract_version": v4.V4_RUNNER_CONTRACT_VERSION,
                "sealed_input_roots_allowed": [],
                "sealed_temperature_records_read": False,
                "n_work_items": v4.EXPECTED_V4_WORK_ITEMS,
                "source_v3_workload_path": str(V3.relative_to(ROOT)),
                "source_v3_workload_sha256": _sha(V3),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        chunk_v4, "audit_v4_prerequisites", lambda *args: _prerequisites()
    )
    output = tmp_path / "chunks"
    with pytest.raises(v4.V4FreezeBlocked, match="before 67 terminal"):
        chunk_v4.execute_t2_v4_chunk(
            repo_root=ROOT,
            workload_manifest_path=workload,
            output_dir=output,
            start_ordinal=0,
            end_ordinal_exclusive=1,
        )
    assert not output.exists()


def test_v4_chunk_safe_resume_validates_table_hash_identity_and_bindings(
    tmp_path: Path,
) -> None:
    chunk_dir = tmp_path / "chunk_0000000_0000002"
    chunk_dir.mkdir()
    frame = pd.DataFrame(
        [
            {
                "ordinal": 0,
                "item_id": "item-a",
                "source_v3_item_id": "source-a",
                "network_id": "network",
                "runner_contract_version": v4.V4_RUNNER_CONTRACT_VERSION,
                "status": "complete",
                "auxiliary_corpus_plan_sha256": "3" * 64,
                "auxiliary_corpus_plan_file_sha256": "9" * 64,
                "auxiliary_network_manifest_sha256": "5" * 64,
                "coverage_semantics_sha256": "a" * 64,
                "sealed_temperature_records_read": False,
            },
            {
                "ordinal": 1,
                "item_id": "item-b",
                "source_v3_item_id": "source-b",
                "network_id": "network",
                "runner_contract_version": v4.V4_RUNNER_CONTRACT_VERSION,
                "status": "structural_not_applicable",
                "auxiliary_corpus_plan_sha256": "3" * 64,
                "auxiliary_corpus_plan_file_sha256": "9" * 64,
                "auxiliary_network_manifest_sha256": "5" * 64,
                "coverage_semantics_sha256": "a" * 64,
                "sealed_temperature_records_read": False,
            },
        ]
    )
    results = chunk_dir / "results.csv"
    frame.to_csv(results, index=False)
    identities = frame[["ordinal", "item_id"]].to_dict(orient="records")
    expected = {
        "manifest_schema": chunk_v4.V4_CHUNK_SCHEMA,
        "runner_contract_version": v4.V4_RUNNER_CONTRACT_VERSION,
        "workload_manifest_sha256": "1" * 64,
        "workload_item_identity_sha256": "2" * 64,
        "auxiliary_corpus_plan_sha256": "3" * 64,
        "auxiliary_corpus_plan_file_sha256": "9" * 64,
        "coverage_semantics_sha256": "a" * 64,
        "auxiliary_network_bindings_sha256": "4" * 64,
        "auxiliary_network_bindings": {
            "network": {"network_manifest_sha256": "5" * 64}
        },
        "input_sha256_by_network_sha256": "6" * 64,
        "input_sha256_by_network": {"network": "7" * 64},
        "chunk_identity_sha256": "8" * 64,
        "start_ordinal": 0,
        "end_ordinal_exclusive": 2,
        "n_records": 2,
        "results_format": "csv",
        "results_path": "results.csv",
        "completeness": "complete",
        "sealed_temperature_records_read": False,
        "formal_evidence": False,
        "passed": False,
    }
    manifest = {
        **expected,
        "ordinal_item_identity_sha256": chunk_v4._canonical_sha(identities),
        "item_id_stream_sha256": chunk_v4._item_stream_sha(identities),
        "first_item_id": "item-a",
        "last_item_id": "item-b",
        "results_sha256": _sha(results),
    }
    manifest_path = chunk_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    resumed = chunk_v4._resume_existing(
        chunk_dir, expected_binding=expected, start=0, end=2
    )
    assert resumed["completeness"] == "complete"

    results.write_text(results.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(v4.V4FreezeBlocked, match="result-table SHA"):
        chunk_v4._resume_existing(
            chunk_dir, expected_binding=expected, start=0, end=2
        )
    frame.to_csv(results, index=False)
    manifest["results_sha256"] = _sha(results)
    manifest["auxiliary_network_bindings"] = {"drifted": {}}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(v4.V4FreezeBlocked, match="auxiliary_network_bindings"):
        chunk_v4._resume_existing(
            chunk_dir, expected_binding=expected, start=0, end=2
        )


def test_formal_manifest_audits_counts_by_model_information_and_lag(
    tmp_path: Path, monkeypatch
) -> None:
    binding = _binding()
    prerequisites = replace(
        _prerequisites(ready=True), bindings={binding.network_id: binding}
    )
    network = OpenNetwork(
        network_id=binding.network_id,
        role=binding.role,
        source_key="open_role_qc/failure_closure6/development",
        wide_path="open/panel.csv",
        wide_sha256="a" * 64,
        manifest_path="open/network.json",
        n_days=1000,
        n_stations=3,
    )
    v3_path = tmp_path / "workload_v3.json"
    source_items = [
        replace(_item("B"), ordinal=0),
        replace(_item("B_union_D_union_M"), ordinal=1),
    ]
    source_digest = hashlib.sha256()
    for item in source_items:
        source_digest.update(item.item_id.encode())
        source_digest.update(b"\n")
    v3_path.write_text(
        json.dumps(
            {
                "input_inventory": {"sealed_input_roots_allowed": []},
                "tier_1": {
                    "n_work_items": 2,
                    "work_item_identity_sha256": source_digest.hexdigest(),
                    "counts_by_role_model_information": {
                        "development|donor_regression|B": 1,
                        "development|donor_regression|B_union_D_union_M": 1,
                    },
                },
            }
        )
    )
    monkeypatch.setattr(v4, "EXPECTED_V3_WORK_ITEMS", 2)
    monkeypatch.setattr(v4, "EXPECTED_V3_EXTENDED_WORK_ITEMS", 1)
    monkeypatch.setattr(v4, "EXPECTED_V4_WORK_ITEMS", 4)
    monkeypatch.setattr(v4, "audit_v4_prerequisites", lambda *args: prerequisites)
    monkeypatch.setattr(
        v4,
        "build_v4_readiness_manifest",
        lambda *args, **kwargs: {
            "source_v3_workload_sha256": "b" * 64,
            "source_v3_work_item_identity_sha256": "c" * 64,
        },
    )
    manifest = v4.build_v4_workload_manifest(
        tmp_path,
        [network],
        source_v3_workload_path=v3_path,
        source_items=source_items,
        item_index_write_path=tmp_path / "item_index.parquet",
    )
    assert manifest["n_work_items"] == 4
    assert manifest["counts_by_model_information_lag"] == {
        "donor_regression|B|none": 1,
        "donor_regression|B_union_D_union_M|-1": 1,
        "donor_regression|B_union_D_union_M|0": 1,
        "donor_regression|B_union_D_union_M|1": 1,
    }
    assert manifest["auxiliary_network_bindings_sha256"] == chunk_v4._canonical_sha(
        manifest["auxiliary_network_bindings"]
    )
    indexed = v4.load_v4_index_slice(
        tmp_path, manifest, prerequisites, start=1, end=4
    )
    assert [item.ordinal for item in indexed] == [1, 2, 3]
    assert [item.meteorology_lag_days for item in indexed] == [-1, 0, 1]


def test_formal_workload_json_is_create_once(tmp_path: Path) -> None:
    path = tmp_path / "workload.json"
    v4._create_once_json(path, {"identity": "a"})
    v4._create_once_json(path, {"identity": "a"})
    with pytest.raises(v4.V4FreezeBlocked, match="create-once"):
        v4._create_once_json(path, {"identity": "b"})


def test_v4_batch_contract_has_approved_executor() -> None:
    spec = load_contract_spec(ROOT / "configs/t2_workload_v4_contract.json")
    assert spec.workload_manifest_schema == v4.V4_WORKLOAD_SCHEMA
    assert spec.chunk_manifest_schema == chunk_v4.V4_CHUNK_SCHEMA
    assert spec.executor_adapter == "t2_v91_chunk_executor_v4"
