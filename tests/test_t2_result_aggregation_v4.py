from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import pytest

import stream_recoverability.experiments.t2_result_aggregation_v4 as aggregation
from stream_recoverability.experiments.t2_chunk_executor_v4 import (
    V4_CHUNK_SCHEMA,
    _canonical_sha,
    _item_stream_sha,
    _validate_result_outcomes,
)
from stream_recoverability.experiments.t2_recovery_benchmark import WorkItem
from stream_recoverability.experiments.t2_workload_v4 import (
    EXECUTION_CODE_INVENTORY_SCHEMA,
    EXECUTION_CODE_PATHS,
    V4_RUNNER_CONTRACT_VERSION,
    V4_WORKLOAD_SCHEMA,
    V4FreezeBlocked,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_merge_normalization_serializes_dynamic_audit_structs_losslessly() -> None:
    first = pd.DataFrame(
        {"information_audit": [{"station_a": {"F": 1.0}}, None]}
    )
    second = pd.DataFrame(
        {"information_audit": [{"station_b": {"L": None}}]}
    )

    left = aggregation._normalize_merge_frame(first)
    right = aggregation._normalize_merge_frame(second)

    assert left["information_audit"].dtype == object
    assert json.loads(left.loc[0, "information_audit"]) == {
        "station_a": {"F": 1.0}
    }
    assert pd.isna(left.loc[1, "information_audit"])
    assert json.loads(right.loc[0, "information_audit"]) == {
        "station_b": {"L": None}
    }


def _fixture(tmp_path: Path) -> tuple[Path, list[Path]]:
    ids = [f"item-{index}" for index in range(4)]
    digest = hashlib.sha256()
    for item_id in ids:
        digest.update(item_id.encode())
        digest.update(b"\n")
    workload = tmp_path / "workload.json"
    index_rows = []
    sources = []
    for ordinal, item_id in enumerate(ids):
        source = WorkItem(
            ordinal=ordinal,
            item_id=f"source-{ordinal}",
            network_id="network",
            role="development",
            source_key="open",
            target_station="station",
            model="donor_regression",
            gap_length=7,
            placement=ordinal,
            start_index=100 + ordinal,
            information_condition="D",
        )
        sources.append(source)
        index_rows.append(
            {
                "ordinal": ordinal,
                "item_id": item_id,
                "meteorology_lag_days": "none",
                "source_item_json": json.dumps(asdict(source), sort_keys=True),
            }
        )
    index_path = tmp_path / "item_index.parquet"
    pd.DataFrame(index_rows).to_parquet(index_path, index=False)
    code_records = [
        {"path": path, "file_sha256": "a" * 64, "git_blob": "b" * 40}
        for path in EXECUTION_CODE_PATHS
    ]
    code_inventory_sha = _canonical_sha(code_records)
    workload.write_text(
        json.dumps(
            {
                "manifest_schema": V4_WORKLOAD_SCHEMA,
                "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
                "n_work_items": 4,
                "work_item_identity_sha256": digest.hexdigest(),
                "item_index": {
                    "path": index_path.name,
                    "file_sha256": _sha(index_path),
                },
                "pre_score_freeze": {"sha256": "f" * 64},
                "execution_code_inventory": {
                    "manifest_schema": EXECUTION_CODE_INVENTORY_SCHEMA,
                    "source_head_commit": "c" * 40,
                    "paths": code_records,
                    "path_roster": list(EXECUTION_CODE_PATHS),
                    "inventory_sha256": code_inventory_sha,
                    "all_paths_committed_unchanged": True,
                },
                "sealed_temperature_records_read": False,
            }
        ),
        encoding="utf-8",
    )
    workload_sha = _sha(workload)
    manifests = []
    for start, end in ((0, 2), (2, 4)):
        directory = tmp_path / f"chunk_{start:07d}_{end:07d}"
        directory.mkdir()
        frame_rows = []
        for ordinal in range(start, end):
            source = sources[ordinal]
            frame_rows.append(
                {
                    **asdict(source),
                    "ordinal": ordinal,
                    "item_id": ids[ordinal],
                    "source_v3_item_id": f"source-{ordinal}",
                    "network_id": "network",
                    "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
                    "status": "complete",
                    "auxiliary_corpus_plan_sha256": "b" * 64,
                    "auxiliary_corpus_plan_file_sha256": "c" * 64,
                    "auxiliary_network_manifest_sha256": "d" * 64,
                    "coverage_semantics_sha256": "e" * 64,
                    "pre_score_freeze_sha256": "f" * 64,
                    "meteorology_lag_days": None,
                    "sealed_temperature_records_read": False,
                    "mae_deg_c": 1.0,
                    "climatology_mae_deg_c": 2.0,
                    "achieved_skill": 0.5,
                    "n_scored": 7,
                    "prediction_sha256": "a" * 64,
                }
            )
        frame = pd.DataFrame(frame_rows)
        results = directory / "results.csv"
        frame.to_csv(results, index=False)
        identities = frame[["ordinal", "item_id"]].to_dict(orient="records")
        manifest = {
            "manifest_schema": V4_CHUNK_SCHEMA,
            "workload_manifest_sha256": workload_sha,
            "workload_item_identity_sha256": digest.hexdigest(),
            "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
            "item_index_file_sha256": _sha(index_path),
            "auxiliary_corpus_plan_sha256": "b" * 64,
            "auxiliary_corpus_plan_file_sha256": "c" * 64,
            "coverage_semantics_sha256": "e" * 64,
            "pre_score_freeze_sha256": "f" * 64,
            "execution_head_commit": "d" * 40,
            "execution_code_inventory_sha256": code_inventory_sha,
            "auxiliary_network_bindings": {
                "network": {"network_manifest_sha256": "d" * 64}
            },
            "start_ordinal": start,
            "end_ordinal_exclusive": end,
            "n_records": end - start,
            "results_format": "csv",
            "results_path": "results.csv",
            "results_sha256": _sha(results),
            "ordinal_item_identity_sha256": _canonical_sha(identities),
            "item_id_stream_sha256": _item_stream_sha(identities),
            "first_item_id": ids[start],
            "last_item_id": ids[end - 1],
            "completeness": "complete",
            "sealed_temperature_records_read": False,
        }
        path = directory / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        manifests.append(path)
    return workload, manifests


def test_v4_aggregation_proves_exact_complete_total_stream(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(aggregation, "EXPECTED_V4_WORK_ITEMS", 4)
    workload, manifests = _fixture(tmp_path)
    result = aggregation.aggregate_v4_chunk_manifests(
        workload_manifest_path=workload,
        chunk_manifest_paths=list(reversed(manifests)),
    )
    assert result["status"] == "complete"
    assert result["observed_item_records"] == 4
    assert (
        result["work_item_identity_sha256"]
        == result["frozen_work_item_identity_sha256"]
    )
    assert result["network_inference_status"] == "withheld_n_lt_100_network_interval"
    assert result["execution_head_commit"] == "d" * 40


def test_v4_aggregation_rejects_counterfeit_skill_arithmetic(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(aggregation, "EXPECTED_V4_WORK_ITEMS", 4)
    workload, manifests = _fixture(tmp_path)
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    result_path = manifests[0].parent / manifest["results_path"]
    frame = pd.read_csv(result_path)
    frame.loc[0, "achieved_skill"] = 42.0
    frame.to_csv(result_path, index=False)
    manifest["results_sha256"] = _sha(result_path)
    manifests[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(V4FreezeBlocked, match="frozen arithmetic"):
        aggregation.aggregate_v4_chunk_manifests(
            workload_manifest_path=workload,
            chunk_manifest_paths=manifests,
        )


def test_v4_aggregation_rejects_non_scored_row_with_outcome(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(aggregation, "EXPECTED_V4_WORK_ITEMS", 4)
    workload, manifests = _fixture(tmp_path)
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    result_path = manifests[0].parent / manifest["results_path"]
    frame = pd.read_csv(result_path)
    frame.loc[0, "status"] = "structural_not_applicable"
    frame.to_csv(result_path, index=False)
    manifest["results_sha256"] = _sha(result_path)
    manifests[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(V4FreezeBlocked, match="carries score fields"):
        aggregation.aggregate_v4_chunk_manifests(
            workload_manifest_path=workload,
            chunk_manifest_paths=manifests,
        )


def test_v4_aggregation_rejects_chunks_from_different_execution_heads(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(aggregation, "EXPECTED_V4_WORK_ITEMS", 4)
    workload, manifests = _fixture(tmp_path)
    second = json.loads(manifests[1].read_text(encoding="utf-8"))
    second["execution_head_commit"] = "e" * 40
    manifests[1].write_text(json.dumps(second), encoding="utf-8")
    with pytest.raises(aggregation.V4AggregationBlocked, match="different execution HEADs"):
        aggregation.aggregate_v4_chunk_manifests(
            workload_manifest_path=workload,
            chunk_manifest_paths=manifests,
        )


def test_reference_result_requires_zero_skill_and_matching_mae() -> None:
    frame = pd.DataFrame(
        [
            {
                "status": "reference_complete",
                "mae_deg_c": 1.0,
                "climatology_mae_deg_c": 1.0,
                "achieved_skill": 0.1,
                "n_scored": 7,
                "prediction_sha256": "a" * 64,
            }
        ]
    )
    with pytest.raises(V4FreezeBlocked, match="zero-skill arithmetic"):
        _validate_result_outcomes(frame)


def test_v4_aggregation_rejects_overlap_and_reports_contiguous_partial(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(aggregation, "EXPECTED_V4_WORK_ITEMS", 4)
    workload, manifests = _fixture(tmp_path)
    partial = aggregation.aggregate_v4_chunk_manifests(
        workload_manifest_path=workload,
        chunk_manifest_paths=manifests[:1],
    )
    assert partial["status"] == "blocked_incomplete_chunk_set"
    assert partial["next_missing_ordinal"] == 2
    with pytest.raises(aggregation.V4AggregationBlocked, match="overlap or leave"):
        aggregation.aggregate_v4_chunk_manifests(
            workload_manifest_path=workload,
            chunk_manifest_paths=[manifests[1]],
        )
