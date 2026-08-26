from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import stream_recoverability.experiments.t2_result_aggregation_v4 as aggregation
from stream_recoverability.experiments.t2_chunk_executor_v4 import (
    V4_CHUNK_SCHEMA,
    _canonical_sha,
    _item_stream_sha,
)
from stream_recoverability.experiments.t2_workload_v4 import (
    V4_RUNNER_CONTRACT_VERSION,
    V4_WORKLOAD_SCHEMA,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, list[Path]]:
    ids = [f"item-{index}" for index in range(4)]
    digest = hashlib.sha256()
    for item_id in ids:
        digest.update(item_id.encode())
        digest.update(b"\n")
    workload = tmp_path / "workload.json"
    workload.write_text(
        json.dumps(
            {
                "manifest_schema": V4_WORKLOAD_SCHEMA,
                "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
                "n_work_items": 4,
                "work_item_identity_sha256": digest.hexdigest(),
                "item_index": {"file_sha256": "a" * 64},
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
        frame = pd.DataFrame(
            [
                {
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
                    "sealed_temperature_records_read": False,
                }
                for ordinal in range(start, end)
            ]
        )
        results = directory / "results.csv"
        frame.to_csv(results, index=False)
        identities = frame[["ordinal", "item_id"]].to_dict(orient="records")
        manifest = {
            "manifest_schema": V4_CHUNK_SCHEMA,
            "workload_manifest_sha256": workload_sha,
            "workload_item_identity_sha256": digest.hexdigest(),
            "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
            "item_index_file_sha256": "a" * 64,
            "auxiliary_corpus_plan_sha256": "b" * 64,
            "auxiliary_corpus_plan_file_sha256": "c" * 64,
            "coverage_semantics_sha256": "e" * 64,
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
    assert result["work_item_identity_sha256"] == result[
        "frozen_work_item_identity_sha256"
    ]
    assert result["network_inference_status"] == "withheld_n_lt_100_network_interval"


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
