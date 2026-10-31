from __future__ import annotations
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
from stream_recoverability.experiments.t2_batch_orchestrator import load_contract_spec
from stream_recoverability.experiments.t2_cached_executor import StrictFitExecutionCache
from stream_recoverability.experiments.t2_information_runner_integration import (
    load_materialized_auxiliary_v2,
)
from stream_recoverability.experiments.t2_recovery_benchmark import (
    OpenNetwork,
    WorkItem,
    deterministic_placements,
    discover_failure_closure_networks,
    execute_item,
    read_panel,
)

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "results/framework/t2_recovery_benchmark_v1/workload_manifest.json"


def _network(network_id: str = "huc8_02040103") -> OpenNetwork:
    networks, _ = discover_failure_closure_networks(ROOT)
    return next((network for network in networks if network.network_id == network_id))


def _binding() -> v4.V2NetworkBinding:
    return v4.V2NetworkBinding(
        network_id="huc8_02040103",
        role="development",
        network_manifest_schema="t2_v91_open_role_mh_network_acquisition_v2_1",
        network_manifest_path="open/network_manifest.json",
        daily_long_path="open/daily_long_auxiliary.csv",
        coverage_path="open/coverage.csv",
        adapter_schema_path="open/adapter_schema.json",
        materialization_status="materialized_partial",
    )


def _prerequisites(*, ready: bool = False) -> v4.V4Prerequisites:
    binding = _binding()
    return v4.V4Prerequisites(
        ready=ready,
        corpus_plan_path="open/corpus_request_plan.json",
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
    before = V3.read_bytes()
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
    assert V3.read_bytes() == before
    with pytest.raises(v4.V4FreezeBlocked, match="67 terminal"):
        list(v4.iter_v4_work_items([_item("B")], _prerequisites()))


def test_extended_items_expand_all_lags_with_readable_distinct_ids() -> None:
    prerequisites = _prerequisites(ready=True)
    base = list(
        v4.iter_v4_work_items([_item("B")], prerequisites, require_full_corpus=False)
    )
    extended = list(
        v4.iter_v4_work_items(
            [_item("B_union_D_union_M")], prerequisites, require_full_corpus=False
        )
    )
    assert len(base) == 1
    assert base[0].meteorology_lag_days is None
    assert [item.meteorology_lag_days for item in extended] == [-1, 0, 1]
    assert base[0].item_id == "v3-B-donor_regression.lagnone"
    assert [item.item_id for item in extended] == [
        "v3-B_union_D_union_M-donor_regression.lag-1",
        "v3-B_union_D_union_M-donor_regression.lag0",
        "v3-B_union_D_union_M-donor_regression.lag1",
    ]
    assert all((item.auxiliary_binding == _binding() for item in extended))


def test_item_index_rejects_a_truncated_v3_stream(tmp_path: Path, monkeypatch) -> None:
    source = replace(_item("B"), ordinal=0)
    monkeypatch.setattr(v4, "EXPECTED_V3_WORK_ITEMS", 2)
    monkeypatch.setattr(v4, "EXPECTED_V3_EXTENDED_WORK_ITEMS", 0)
    monkeypatch.setattr(v4, "EXPECTED_V4_WORK_ITEMS", 2)
    output = tmp_path / "truncated.parquet"
    with pytest.raises(v4.V4FreezeBlocked, match="count verification"):
        v4._write_v4_item_index(output, [source], _prerequisites(ready=True))
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
        "Auxiliary", (), {"audit": {"source_contract": "legacy_nwis_v2"}}
    )()
    prerequisites = _prerequisites(ready=True)
    donor_item = next(
        iter(
            v4.iter_v4_work_items(
                [_item("B_union_D_union_M")], prerequisites, require_full_corpus=False
            )
        )
    )
    donor_result = v4.execute_v4_item(
        ROOT, _network(), donor_item, panel=pd.DataFrame(), auxiliary=auxiliary
    )
    assert donor_result["status"] == "complete"
    assert calls == [("donor_regression", donor_item.source_v3_item.item_id)]
    reference_network = _network()
    reference_panel = read_panel(ROOT, reference_network)
    reference_target = str(reference_panel.columns[0])
    reference_start = deterministic_placements(
        reference_panel, target=reference_target, gap_length=7, count=1
    )[0]
    reference_source = replace(
        _item("B_union_D_union_M", model="climatology"),
        target_station=reference_target,
        start_index=reference_start,
    )
    unsupported = next(
        iter(
            v4.iter_v4_work_items(
                [reference_source], prerequisites, require_full_corpus=False
            )
        )
    )
    result = v4.execute_v4_item(
        ROOT,
        reference_network,
        unsupported,
        panel=reference_panel,
        base_execution_cache=StrictFitExecutionCache(ROOT),
    )
    assert result["status"] == "reference_complete"
    assert calls == [("donor_regression", donor_item.source_v3_item.item_id)]


def test_nonextended_v4_item_uses_chunk_execution_cache() -> None:
    calls: list[str] = []

    class Cache:
        def execute(self, network, item, *, meteorology_lag_days=None):
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
    result = v4.execute_v4_item(ROOT, _network(), item, base_execution_cache=Cache())
    assert calls == [item.item_id]
    assert result["runner_contract_version"] == v4.V4_RUNNER_CONTRACT_VERSION


def test_real_open_extended_climatology_is_three_explicit_v4_references(
    monkeypatch,
) -> None:
    network = _network()
    panel = read_panel(ROOT, network)
    target = str(panel.columns[0])
    start = deterministic_placements(panel, target=target, gap_length=7, count=1)[0]
    source = WorkItem(
        ordinal=0,
        item_id="real-open-extended-climatology-source",
        network_id=network.network_id,
        role=network.role,
        source_key=network.source_key,
        target_station=target,
        model="climatology",
        gap_length=7,
        placement=0,
        start_index=start,
        information_condition="B_union_D_union_M",
    )
    items = list(
        v4.iter_v4_work_items(
            [source], _prerequisites(ready=True), require_full_corpus=False
        )
    )
    assert [item.meteorology_lag_days for item in items] == [-1, 0, 1]

    def auxiliary_must_not_be_read(*args, **kwargs):
        raise AssertionError("climatology reference must not load M/H outcomes")

    monkeypatch.setattr(
        v4, "load_materialized_auxiliary_v2", auxiliary_must_not_be_read
    )
    cache = StrictFitExecutionCache(ROOT)
    results = [
        v4.execute_v4_item(ROOT, network, item, panel=panel, base_execution_cache=cache)
        for item in items
    ]
    legacy = [
        execute_item(ROOT, network, item.runner_item(), panel=panel) for item in items
    ]
    assert len({row["item_id"] for row in results}) == 3
    assert [row["meteorology_lag_days"] for row in results] == [-1, 0, 1]
    assert all((row["status"] == "reference_complete" for row in results))
    assert all((row["workload_category"] == "reference" for row in results))
    assert all(
        (
            row["available_information_condition"] == source.information_condition
            for row in results
        )
    )
    assert all((row["consumed_information"] == [] for row in results))
    assert all((row["information_condition_result"] is False for row in results))
    assert all((row["achieved_skill"] == 0.0 for row in results))
    assert all(
        (row["reference_ignores_available_information"] is True for row in results)
    )
    assert all((row["sealed_temperature_records_read"] is False for row in results))
    for result, expected in zip(results, legacy, strict=True):
        for field in (
            "status",
            "implementation",
            "n_scored",
            "mae_deg_c",
            "climatology_mae_deg_c",
            "achieved_skill",
        ):
            assert result[field] == expected[field]
    assert cache.stats()["fit_cache_misses_by_model"] == {"climatology": 3}
    assert cache.stats()["fit_cache_hits_by_model"] == {}


def test_zero_climatology_denominator_is_terminal_data_attrition() -> None:
    network = _network("huc8_04060102")
    item = WorkItem(
        ordinal=522921,
        item_id="zero-climatology-denominator-regression",
        network_id=network.network_id,
        role=network.role,
        source_key=network.source_key,
        target_station="04121944",
        model="pchip_or_linear",
        gap_length=7,
        placement=4,
        start_index=8776,
        information_condition="B",
        task="offline_archival",
        geometry="artificial_stress",
        boundary_mode="both",
    )
    result = execute_item(ROOT, network, item)
    assert result["status"] == "data_ineligible"
    assert result["workload_category"] == "data_ineligible"
    assert result["reason"] == "undefined_skill_nonpositive_climatology_mae"
    for column in ("mae_deg_c", "climatology_mae_deg_c", "achieved_skill", "n_scored"):
        assert column not in result


def test_missing_climatology_training_target_is_terminal_data_attrition() -> None:
    network = _network("huc8_03050106")
    item = WorkItem(
        ordinal=2218185,
        item_id="missing-climatology-training-target-regression",
        network_id=network.network_id,
        role=network.role,
        source_key=network.source_key,
        target_station="02162035",
        model="climatology",
        gap_length=9,
        placement=0,
        start_index=13895,
        information_condition="B",
        task="offline_archival",
        geometry="natural_outage",
        boundary_mode="both",
    )
    result = execute_item(ROOT, network, item)
    assert result["status"] == "data_ineligible"
    assert result["workload_category"] == "data_ineligible"
    assert result["reason"] == "undefined_skill_no_finite_climatology_training_targets"
    assert "achieved_skill" not in result


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
                "execution_allowed": True,
                "source_v3_workload_path": str(V3.relative_to(ROOT)),
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


def test_v4_chunk_safe_resume_validates_table_identity_and_bindings(
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
                "sealed_temperature_records_read": False,
                "mae_deg_c": 1.0,
                "climatology_mae_deg_c": 2.0,
                "achieved_skill": 0.5,
                "n_scored": 7,
            },
            {
                "ordinal": 1,
                "item_id": "item-b",
                "source_v3_item_id": "source-b",
                "network_id": "network",
                "runner_contract_version": v4.V4_RUNNER_CONTRACT_VERSION,
                "status": "structural_not_applicable",
                "sealed_temperature_records_read": False,
            },
        ]
    )
    results = chunk_dir / "results.csv"
    frame.to_csv(results, index=False)
    expected = {
        "manifest_schema": chunk_v4.V4_CHUNK_SCHEMA,
        "runner_contract_version": v4.V4_RUNNER_CONTRACT_VERSION,
        "auxiliary_network_bindings": {
            "network": {"network_manifest_path": "open/network_manifest.json"}
        },
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
    manifest = {**expected, "first_item_id": "item-a", "last_item_id": "item-b"}
    manifest_path = chunk_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    resumed = chunk_v4._resume_existing(
        chunk_dir, expected_binding=expected, start=0, end=2
    )
    assert resumed["completeness"] == "complete"
    frame.iloc[:1].to_csv(results, index=False)
    with pytest.raises(v4.V4FreezeBlocked, match="row count mismatch"):
        chunk_v4._resume_existing(chunk_dir, expected_binding=expected, start=0, end=2)
    frame.to_csv(results, index=False)
    manifest["auxiliary_network_bindings"] = {"drifted": {}}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(v4.V4FreezeBlocked, match="auxiliary_network_bindings"):
        chunk_v4._resume_existing(chunk_dir, expected_binding=expected, start=0, end=2)


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
        manifest_path="open/network.json",
        n_days=1000,
        n_stations=3,
    )
    v3_path = tmp_path / "workload_v3.json"
    source_items = [
        replace(_item("B"), ordinal=0),
        replace(_item("B_union_D_union_M"), ordinal=1),
    ]
    v3_path.write_text(
        json.dumps(
            {
                "input_inventory": {"sealed_input_roots_allowed": []},
                "tier_1": {
                    "n_work_items": 2,
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
        lambda *args, **kwargs: {"status": "ready_for_formal_v4_freeze"},
    )
    manifest = v4.build_v4_workload_manifest(
        tmp_path,
        [network],
        source_v3_workload_path=v3_path,
        source_items=source_items,
        item_index_write_path=tmp_path / "item_index.parquet",
    )
    assert manifest["manifest_schema"] == v4.V4_INDEX_DRAFT_SCHEMA
    assert manifest["execution_allowed"] is False
    assert manifest["n_work_items"] == 4
    assert manifest["counts_by_model_information_lag"] == {
        "donor_regression|B|none": 1,
        "donor_regression|B_union_D_union_M|-1": 1,
        "donor_regression|B_union_D_union_M|0": 1,
        "donor_regression|B_union_D_union_M|1": 1,
    }
    assert manifest["auxiliary_network_bindings"] == {
        binding.network_id: binding.identity()
    }
    indexed = v4.load_v4_index_slice(tmp_path, manifest, prerequisites, start=1, end=4)
    assert [item.ordinal for item in indexed] == [1, 2, 3]
    assert [item.meteorology_lag_days for item in indexed] == [-1, 0, 1]
    assert [item.item_id for item in indexed] == [
        "v3-B_union_D_union_M-donor_regression.lag-1",
        "v3-B_union_D_union_M-donor_regression.lag0",
        "v3-B_union_D_union_M-donor_regression.lag1",
    ]


def test_final_workload_binds_complete_pre_score_bundle(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(v4, "EXPECTED_V4_WORK_ITEMS", 1)
    index = tmp_path / "item_index.parquet"
    pd.DataFrame({"ordinal": [0], "item_id": ["item"]}).to_parquet(index, index=False)
    draft = {
        "manifest_schema": v4.V4_INDEX_DRAFT_SCHEMA,
        "execution_allowed": False,
        "n_work_items": 1,
        "item_index": {"path": index.name},
    }
    draft_path = tmp_path / "index_draft_manifest.json"
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    artifact_names = [
        "eligibility_manifest",
        "eligibility_table",
        "feasibility_census",
        "exhaustive_item_ledger",
        "base_lattice_manifest",
        "base_lattice",
        "predictor_manifest",
        "predictor_table",
        "sensitivity_M",
        "sensitivity_M_H",
    ]
    records = {}
    for name in artifact_names:
        path = tmp_path / f"{name}.bin"
        path.write_bytes(name.encode())
        records[name] = {"path": path.name}
    freeze = {
        "manifest_schema": v4.V4_PRE_SCORE_FREEZE_SCHEMA,
        "status": "complete_outcome_blind_pre_score_freeze",
        "index_draft_manifest": {"path": draft_path.name},
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "v4_results_read": False,
        "selection_uses_outcomes": False,
        "achieved_skill_read": False,
        **{
            key: value
            for key, value in records.items()
            if not key.startswith("sensitivity_")
        },
        "base_lattice_status": "frozen_before_v4_scoring",
        "sensitivity_lattice_statuses": {
            "M": "blocked_insufficient_pre_score_support",
            "M_H": "blocked_insufficient_pre_score_support",
        },
        "sensitivity_lattices": {
            "M": records["sensitivity_M"],
            "M_H": records["sensitivity_M_H"],
        },
    }
    freeze_path = tmp_path / "pre_score_freeze_manifest.json"
    freeze_path.write_text(json.dumps(freeze), encoding="utf-8")
    final = v4.finalize_v4_workload(
        tmp_path,
        index_draft_manifest_path=draft_path,
        pre_score_freeze_manifest_path=freeze_path,
        output_path=tmp_path / "workload_manifest.json",
    )
    assert final["manifest_schema"] == v4.V4_WORKLOAD_SCHEMA
    assert final["execution_allowed"] is True
    assert final["pre_score_freeze"]["path"] == freeze_path.name
    assert final["index_draft_manifest"]["path"] == draft_path.name
    assert set(final["pre_score_freeze"]["artifacts"]) == {
        name for name in artifact_names if not name.startswith("sensitivity_")
    }
    assert set(final["pre_score_freeze"]["sensitivity_lattices"]) == {"M", "M_H"}


def test_v4_batch_contract_has_approved_executor() -> None:
    spec = load_contract_spec(ROOT / "configs/t2_workload_v4_contract.json")
    assert spec.workload_manifest_schema == v4.V4_WORKLOAD_SCHEMA
    assert spec.chunk_manifest_schema == chunk_v4.V4_CHUNK_SCHEMA
    assert spec.executor_adapter == "t2_v91_chunk_executor_v4"
