from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import stream_recoverability.experiments.t2_result_aggregation_v4 as aggregation
from stream_recoverability.experiments.t2_chunk_executor_v4 import (
    V4_CHUNK_SCHEMA,
    _validate_result_outcomes,
)
from stream_recoverability.experiments.t2_recovery_benchmark import WorkItem
from stream_recoverability.experiments.t2_workload_v4 import (
    V4_RUNNER_CONTRACT_VERSION,
    V4_WORKLOAD_SCHEMA,
    V4FreezeBlocked,
)


def test_merge_normalization_serializes_dynamic_audit_structs_losslessly() -> None:
    first = pd.DataFrame({"information_audit": [{"station_a": {"F": 1.0}}, None]})
    second = pd.DataFrame(
        {
            "information_audit": [
                {"station_b": {"L": None, "roster": np.array(["F", "L"])}}
            ]
        }
    )

    left = aggregation._normalize_merge_frame(first)
    right = aggregation._normalize_merge_frame(second)

    assert left["information_audit"].dtype == object
    assert json.loads(left.loc[0, "information_audit"]) == {"station_a": {"F": 1.0}}
    assert pd.isna(left.loc[1, "information_audit"])
    assert json.loads(right.loc[0, "information_audit"]) == {
        "station_b": {"L": None, "roster": ["F", "L"]}
    }


def _fixture(tmp_path: Path) -> tuple[Path, list[Path]]:
    ids = [f"item-{index}" for index in range(4)]
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
    workload.write_text(
        json.dumps(
            {
                "manifest_schema": V4_WORKLOAD_SCHEMA,
                "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
                "n_work_items": 4,
                "item_index": {"path": index_path.name},
                "sealed_temperature_records_read": False,
            }
        ),
        encoding="utf-8",
    )
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
                    "meteorology_lag_days": None,
                    "sealed_temperature_records_read": False,
                    "mae_deg_c": 1.0,
                    "climatology_mae_deg_c": 2.0,
                    "achieved_skill": 0.5,
                    "n_scored": 7,
                }
            )
        frame = pd.DataFrame(frame_rows)
        results = directory / "results.csv"
        frame.to_csv(results, index=False)
        manifest = {
            "manifest_schema": V4_CHUNK_SCHEMA,
            "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
            "start_ordinal": start,
            "end_ordinal_exclusive": end,
            "n_records": end - start,
            "results_format": "csv",
            "results_path": "results.csv",
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
    assert result["completeness"] == "complete"
    assert result["observed_item_records"] == 4
    assert result["next_missing_ordinal"] == 4
    assert result["network_inference_status"] == "withheld_n_lt_100_network_interval"
    merged = result["merged_item_results"]
    assert merged["n_rows"] == 4
    merged_path = tmp_path / "aggregation_v4" / merged["path"]
    assert pd.read_parquet(merged_path)["item_id"].tolist() == [
        f"item-{index}" for index in range(4)
    ]


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
    with pytest.raises(V4FreezeBlocked, match="carries score fields"):
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
