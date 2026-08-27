from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import stream_recoverability.experiments.t2_pre_score_eligibility as eligibility_builder
from stream_recoverability.experiments.t2_pre_score_eligibility import (
    NetworkAvailability,
    _extended_coverage_status,
    build_pre_score_eligibility,
)
from stream_recoverability.experiments.t2_primary_aggregation_v2 import (
    ELIGIBILITY_AUDIT_SCHEMA,
    PRIMARY_COMMON_GRID,
    PrimaryAggregationBlocked,
    _canonical_sha,
    _equal_hierarchical_event_weights,
    bind_complete_v4_primary_results,
    create_pre_score_freeze_bundle,
    freeze_v4_analyzable_lattice,
)
from stream_recoverability.experiments.t2_recovery_benchmark import (
    OpenNetwork,
    WorkItem,
)
from stream_recoverability.experiments.t2_result_aggregation_v4 import (
    V4_AGGREGATION_SCHEMA,
)
from stream_recoverability.experiments.t2_train_only_predictors import (
    PREDICTOR_COLUMNS,
    SIDECAR_SCHEMA,
)
from stream_recoverability.experiments.t2_train_only_predictors_v4 import (
    GAP_ROSTER_SOURCE as V4_GAP_ROSTER_SOURCE,
)
from stream_recoverability.experiments.t2_train_only_predictors_v4 import (
    SIDECAR_SCHEMA as V4_SIDECAR_SCHEMA,
)
from stream_recoverability.experiments.t2_workload_v4 import (
    V4_INDEX_DRAFT_SCHEMA,
    V4_ITEM_INDEX_SCHEMA,
    V4_RUNNER_CONTRACT_VERSION,
    V4_WORKLOAD_SCHEMA,
)
from stream_recoverability.experiments.t4_t5_post_t2 import (
    validate_v4_primary_inputs,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stream_sha(ids: list[str]) -> str:
    digest = hashlib.sha256()
    for item_id in ids:
        digest.update(item_id.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def test_logical_result_digest_normalizes_information_audit_storage() -> None:
    left = hashlib.sha256()
    right = hashlib.sha256()
    columns = ["item_id", "information_audit"]
    module = __import__(
        "stream_recoverability.experiments.t2_primary_aggregation_v2",
        fromlist=["_update_logical_result_digest"],
    )
    module._update_logical_result_digest(
        left,
        pd.DataFrame(
            [{"item_id": "x", "information_audit": {"lag": np.int64(-1), "ok": True}}]
        ),
        columns,
    )
    module._update_logical_result_digest(
        right,
        pd.DataFrame(
            [
                {
                    "item_id": "x",
                    "information_audit": json.dumps(
                        {"lag": -1, "ok": True},
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                }
            ]
        ),
        columns,
    )
    assert left.hexdigest() == right.hexdigest()


def test_logical_result_digest_normalizes_nested_numpy_containers() -> None:
    left = hashlib.sha256()
    right = hashlib.sha256()
    columns = ["item_id", "consumed_information", "audit"]
    module = __import__(
        "stream_recoverability.experiments.t2_primary_aggregation_v2",
        fromlist=["_update_logical_result_digest"],
    )
    module._update_logical_result_digest(
        left,
        pd.DataFrame(
            [{"item_id": "x", "consumed_information": np.array(["B", "D"]), "audit": {"n": np.int64(2)}}]
        ),
        columns,
    )
    module._update_logical_result_digest(
        right,
        pd.DataFrame(
            [{"item_id": "x", "consumed_information": ["B", "D"], "audit": {"n": 2}}]
        ),
        columns,
    )
    assert left.hexdigest() == right.hexdigest()


def _freeze_fixture(tmp_path: Path) -> dict[str, Path]:
    rows = []
    result_rows = []
    for event, (network, station, geometry) in enumerate(
        (
            ("net-a", "00000001", "artificial_stress"),
            ("net-b", "00000002", "natural_outage"),
        )
    ):
        for model, information, task, lag in PRIMARY_COMMON_GRID:
            ordinal = len(rows)
            item_id = f"item-{ordinal:03d}"
            source = WorkItem(
                ordinal=ordinal,
                item_id=f"source-{ordinal:03d}",
                network_id=network,
                role="development" if event == 0 else "validation",
                source_key=network,
                target_station=station,
                model=model,
                gap_length=7,
                placement=0,
                start_index=100 + event,
                information_condition=information,
                task=task,
                geometry=geometry,
                geometry_id=f"geometry-{event}",
                truth_start_date=str(
                    (pd.Timestamp("2001-01-01") + pd.Timedelta(days=event)).date()
                ),
                observed_missing_start_date=("" if event == 0 else "1999-01-01"),
            )
            rows.append(
                {
                    "ordinal": ordinal,
                    "item_id": item_id,
                    "source_v3_ordinal": ordinal,
                    "source_v3_item_id": source.item_id,
                    "network_id": network,
                    "meteorology_lag_days": lag,
                    "source_item_json": json.dumps(asdict(source), sort_keys=True),
                }
            )
            result_rows.append(
                {
                    **asdict(source),
                    "ordinal": ordinal,
                    "item_id": item_id,
                    "meteorology_lag_days": None if lag == "none" else int(lag),
                    "status": "complete",
                    "achieved_skill": 0.25 + ordinal / 1000,
                    "sealed_temperature_records_read": False,
                }
            )
    index = pd.DataFrame(rows)
    index_path = tmp_path / "item_index.parquet"
    index.to_parquet(index_path, index=False)
    ids = index["item_id"].tolist()
    workload = {
        "manifest_schema": V4_INDEX_DRAFT_SCHEMA,
        "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
        "n_work_items": len(index),
        "work_item_identity_sha256": _stream_sha(ids),
        "item_index": {
            "manifest_schema": V4_ITEM_INDEX_SCHEMA,
            "path": index_path.name,
            "file_sha256": _sha(index_path),
            "n_rows": len(index),
        },
        "input_sha256_by_network": {"net-a": "a" * 64, "net-b": "b" * 64},
        "input_inventory": {"catalog_split_sha256": "4" * 64},
        "source_v3_workload_sha256": "9" * 64,
        "auxiliary_network_bindings": {
            "net-a": {"coverage_sha256": "2" * 64},
            "net-b": {"coverage_sha256": "3" * 64},
        },
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
    }
    workload_path = tmp_path / "workload.json"
    workload["input_sha256_by_network_sha256"] = _canonical_sha(
        workload["input_sha256_by_network"]
    )
    workload_path.write_text(json.dumps(workload), encoding="utf-8")

    predictors = pd.DataFrame(
        [
            {
                "network_id": network,
                "station_id": station,
                "gap_length": 7,
                "role": "development" if network == "net-a" else "validation",
                "fit_role": "development" if network == "net-a" else "validation",
                **{
                    column: 0.1 + offset / 10
                    for offset, column in enumerate(PREDICTOR_COLUMNS)
                },
            }
            for network, station in (("net-a", "00000001"), ("net-b", "00000002"))
        ]
    )
    predictor_path = tmp_path / "train_only_predictors.parquet"
    predictors.to_parquet(predictor_path, index=False)
    predictor_manifest = {
        "manifest_schema": SIDECAR_SCHEMA,
        "trained_on_open_roles_only": True,
        "outcome_rows_read_during_fit": False,
        "recovery_result_rows_read": False,
        "sealed_temperature_records_read": False,
        "completeness": "complete",
        "join_keys": ["network_id", "station_id", "gap_length"],
        "workload_manifest_sha256": "9" * 64,
        "input_sha256_by_network": workload["input_sha256_by_network"],
        "catalog_split_sha256": "4" * 64,
        "gaps": [7, 14, 30, 60, 90, 180, 365],
        "network_covariance_fit_scope": "within_network_first_70pct_calendar_years",
        "learned_calibration": False,
        "parquet_path": predictor_path.name,
        "parquet_sha256": _sha(predictor_path),
    }
    predictor_manifest_path = tmp_path / "predictor_manifest.json"
    predictor_manifest_path.write_text(json.dumps(predictor_manifest), encoding="utf-8")

    eligibility = pd.DataFrame(
        {"item_id": ids, "pre_score_status": "complete", "reason": ""}
    )
    eligibility_path = tmp_path / "eligibility.parquet"
    eligibility.to_parquet(eligibility_path, index=False)
    coverage_map = {"net-a": "2" * 64, "net-b": "3" * 64}
    eligibility_manifest = {
        "manifest_schema": ELIGIBILITY_AUDIT_SCHEMA,
        "builder_schema": "t2_v91_v4_pre_score_eligibility_builder_v1",
        "status": "complete_outcome_blind_pre_score_audit",
        "completeness": "complete",
        "workload_manifest_sha256": _sha(workload_path),
        "item_index_file_sha256": _sha(index_path),
        "input_qc_inventory_sha256": workload["input_sha256_by_network_sha256"],
        "auxiliary_coverage_bindings_sha256": _canonical_sha(coverage_map),
        "placements_read_from_frozen_item_index": True,
        "selection_uses_outcomes": False,
        "achieved_skill_read": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "open_qc_date_labels_read": True,
        "open_qc_station_header_read": True,
        "open_qc_temperature_value_columns_read": [],
        "open_qc_temperature_na_availability_read": False,
        "open_qc_temperature_csv_bytes_traversed": True,
        "open_qc_excluded_temperature_fields_decoded": False,
        "gap_truth_values_read": False,
        "auxiliary_provider_qc_values_read_for_declared_information_coverage": True,
        "temperature_date_and_roster_classification": "design_metadata_not_recovery_outcome",
        "model_fit_or_prediction_run": False,
        "old_outcomes_read": False,
        "expected_item_records": len(eligibility),
        "observed_item_records": len(eligibility),
        "work_item_identity_sha256": workload["work_item_identity_sha256"],
        "eligibility_table": {
            "path": eligibility_path.name,
            "sha256": _sha(eligibility_path),
            "n_rows": len(eligibility),
        },
    }
    eligibility_manifest_path = tmp_path / "eligibility_manifest.json"
    eligibility_manifest_path.write_text(
        json.dumps(eligibility_manifest), encoding="utf-8"
    )
    results = pd.DataFrame(result_rows)
    results_path = tmp_path / "results.parquet"
    results.to_parquet(results_path, index=False)
    return {
        "workload": workload_path,
        "predictor_manifest": predictor_manifest_path,
        "eligibility_manifest": eligibility_manifest_path,
        "eligibility": eligibility_path,
        "results": results_path,
    }


def _append_ineligible_natural_gap(paths: dict[str, Path], gap: int = 8) -> None:
    """Add one fully audited but pre-score-ineligible natural event stratum."""

    index = pd.read_parquet(paths["workload"].parent / "item_index.parquet")
    natural = index.iloc[len(PRIMARY_COMMON_GRID) : 2 * len(PRIMARY_COMMON_GRID)]
    appended_index = []
    appended_eligibility = []
    for record in natural.to_dict(orient="records"):
        source = json.loads(record["source_item_json"])
        ordinal = len(index) + len(appended_index)
        item_id = f"item-{ordinal:03d}"
        source.update(
            {
                "ordinal": ordinal,
                "item_id": f"source-{ordinal:03d}",
                "gap_length": gap,
                "placement": 1,
                "start_index": 200,
                "geometry_id": "geometry-ineligible",
                "truth_start_date": "2001-02-01",
                "observed_missing_start_date": "1999-02-01",
            }
        )
        appended_index.append(
            {
                **record,
                "ordinal": ordinal,
                "item_id": item_id,
                "source_v3_ordinal": ordinal,
                "source_v3_item_id": source["item_id"],
                "source_item_json": json.dumps(source, sort_keys=True),
            }
        )
        appended_eligibility.append(
            {
                "item_id": item_id,
                "pre_score_status": "data_ineligible",
                "reason": "open_qc_gap_window_incomplete",
            }
        )
    index = pd.concat([index, pd.DataFrame(appended_index)], ignore_index=True)
    index_path = paths["workload"].parent / "item_index.parquet"
    index.to_parquet(index_path, index=False)

    workload = json.loads(paths["workload"].read_text(encoding="utf-8"))
    workload["n_work_items"] = len(index)
    workload["work_item_identity_sha256"] = _stream_sha(index["item_id"].tolist())
    workload["item_index"].update(
        {"file_sha256": _sha(index_path), "n_rows": len(index)}
    )
    paths["workload"].write_text(json.dumps(workload), encoding="utf-8")

    eligibility = pd.read_parquet(paths["eligibility"])
    eligibility = pd.concat(
        [eligibility, pd.DataFrame(appended_eligibility)], ignore_index=True
    )
    eligibility.to_parquet(paths["eligibility"], index=False)
    eligibility_manifest = json.loads(
        paths["eligibility_manifest"].read_text(encoding="utf-8")
    )
    eligibility_manifest.update(
        {
            "workload_manifest_sha256": _sha(paths["workload"]),
            "item_index_file_sha256": _sha(index_path),
            "expected_item_records": len(index),
            "observed_item_records": len(index),
            "work_item_identity_sha256": workload["work_item_identity_sha256"],
        }
    )
    eligibility_manifest["eligibility_table"].update(
        {"sha256": _sha(paths["eligibility"]), "n_rows": len(eligibility)}
    )
    paths["eligibility_manifest"].write_text(
        json.dumps(eligibility_manifest), encoding="utf-8"
    )

    predictors = pd.read_parquet(paths["predictor_manifest"].parent / "train_only_predictors.parquet")
    source_predictor = predictors.loc[predictors["network_id"].eq("net-b")].iloc[0].copy()
    source_predictor["gap_length"] = gap
    predictors = pd.concat(
        [predictors, source_predictor.to_frame().T], ignore_index=True
    )
    predictor_path = paths["predictor_manifest"].parent / "train_only_predictors.parquet"
    predictors.to_parquet(predictor_path, index=False)
    predictor_manifest = json.loads(
        paths["predictor_manifest"].read_text(encoding="utf-8")
    )
    predictor_manifest["gaps"] = sorted({*predictor_manifest["gaps"], gap})
    predictor_manifest["parquet_sha256"] = _sha(predictor_path)
    paths["predictor_manifest"].write_text(
        json.dumps(predictor_manifest), encoding="utf-8"
    )


def _convert_predictor_fixture_to_v2(paths: dict[str, Path]) -> None:
    root = paths["workload"].parent
    design = root / "design.json"
    design.write_text("{}\n", encoding="utf-8")
    source_v3 = root / "source_v3_workload.json"
    source_v3.write_text(
        json.dumps({"design_sha256": _sha(design)}), encoding="utf-8"
    )
    workload = json.loads(paths["workload"].read_text(encoding="utf-8"))
    workload.update(
        {
            "source_v3_workload_path": source_v3.name,
            "source_v3_workload_sha256": _sha(source_v3),
        }
    )
    paths["workload"].write_text(json.dumps(workload), encoding="utf-8")
    eligibility_manifest = json.loads(
        paths["eligibility_manifest"].read_text(encoding="utf-8")
    )
    eligibility_manifest["workload_manifest_sha256"] = _sha(paths["workload"])
    paths["eligibility_manifest"].write_text(
        json.dumps(eligibility_manifest), encoding="utf-8"
    )

    index_path = root / "item_index.parquet"
    predictors = pd.read_parquet(root / "train_only_predictors.parquet")
    manifest = json.loads(paths["predictor_manifest"].read_text(encoding="utf-8"))
    gaps_by_geometry = {
        "adversarial_stress": [],
        "artificial_stress": [7],
        "natural_outage": [7],
    }
    gaps = [7]
    manifest.update(
        {
            "manifest_schema": V4_SIDECAR_SCHEMA,
            "index_draft_manifest_path": paths["workload"].name,
            "index_draft_manifest_sha256": _sha(paths["workload"]),
            "item_index_path": index_path.name,
            "item_index_sha256": _sha(index_path),
            "item_index_work_item_identity_sha256": workload[
                "work_item_identity_sha256"
            ],
            "source_v3_workload_path": source_v3.name,
            "source_v3_workload_sha256": _sha(source_v3),
            "design_path": design.name,
            "design_sha256": _sha(design),
            "input_inventory": workload["input_inventory"],
            "input_inventory_contract_sha256": _canonical_sha(
                workload["input_inventory"]
            ),
            "input_inventory_sha256": workload[
                "input_sha256_by_network_sha256"
            ],
            "input_sha256_by_network_sha256": workload[
                "input_sha256_by_network_sha256"
            ],
            "gap_roster_source": V4_GAP_ROSTER_SOURCE,
            "gap_roster_sha256": _canonical_sha(
                {"gaps": gaps, "gaps_by_geometry": gaps_by_geometry}
            ),
            "gaps": gaps,
            "gaps_by_geometry": gaps_by_geometry,
            "n_unique_gaps": len(gaps),
            "n_rows": len(predictors),
            "predictor_columns": list(PREDICTOR_COLUMNS),
            "achieved_skill_read": False,
            "sealed_input_roots_allowed": [],
        }
    )
    manifest.pop("workload_manifest_sha256", None)
    paths["predictor_manifest"].write_text(json.dumps(manifest), encoding="utf-8")


def test_missing_v4_index_writes_blocked_readiness_without_results(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    manifest = freeze_v4_analyzable_lattice(
        workload_manifest_path=tmp_path / "missing.json",
        predictor_manifest_path=tmp_path / "also-missing.json",
        eligibility_manifest_path=tmp_path / "eligibility-missing.json",
        output_dir=output,
    )

    assert manifest["status"] == "blocked_waiting_for_frozen_v4_item_index"
    assert manifest["v4_results_read"] is False
    assert manifest["achieved_skill_read"] is False
    assert (output / "readiness_manifest.json").is_file()

    eligibility_output = tmp_path / "eligibility_output"
    eligibility = build_pre_score_eligibility(
        repo_root=tmp_path,
        workload_manifest_path=tmp_path / "missing.json",
        output_dir=eligibility_output,
    )
    assert eligibility["status"] == "blocked_waiting_for_formal_v4_item_index"
    assert eligibility["v4_results_read"] is False
    assert eligibility["open_qc_temperature_value_columns_read"] == []
    assert not (eligibility_output / "eligibility.parquet").exists()


def test_extended_coverage_uses_only_dates_qc_availability_and_frozen_start() -> None:
    dates = pd.date_range("2000-09-23", periods=1_096, freq="D")
    available = np.ones((7, len(dates)), dtype=bool)
    network = NetworkAvailability(
        network_id="net-a",
        role="development",
        dates=dates,
        site_ids=("00000001",),
        available_by_lag={lag: available.copy() for lag in (-1, 0, 1)},
        train_mask=np.asarray(dates.year <= 2002, dtype=bool),
        provenance={},
    )
    source = {
        "start_index": 100,
        "gap_length": 7,
        "truth_start_date": "2001-01-01",
        "information_condition": "B_union_D_union_M_union_H",
    }

    assert _extended_coverage_status(source, 0, network) == ("complete", "")
    unavailable = available.copy()
    unavailable[0, 102] = False
    blocked = NetworkAvailability(
        **{
            **network.__dict__,
            "available_by_lag": {-1: available, 0: unavailable, 1: available},
        }
    )
    assert _extended_coverage_status(source, 0, blocked) == (
        "data_ineligible",
        "requested_auxiliary_gap_coverage_incomplete",
    )


def test_equal_hierarchical_weights_do_not_reward_more_events_per_network() -> None:
    events = {
        ("development", "net-a", "s1", "artificial_stress", "g1", "", "", 7, 0, 10),
        ("development", "net-a", "s2", "artificial_stress", "g2", "", "", 7, 0, 20),
        ("development", "net-b", "s3", "artificial_stress", "g3", "", "", 7, 0, 30),
    }
    weights = _equal_hierarchical_event_weights(events, grid_size=6)
    network_mass = {
        network: sum(
            value[-1] * 6 for event, value in weights.items() if event[1] == network
        )
        for network in {event[1] for event in events}
    }
    assert network_mass == {"net-a": pytest.approx(0.5), "net-b": pytest.approx(0.5)}
    assert sum(value[-1] * 6 for value in weights.values()) == pytest.approx(1.0)


def test_streaming_eligibility_builder_writes_complete_create_once_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _freeze_fixture(tmp_path)
    dates = pd.date_range("2000-09-23", periods=1_096, freq="D")
    matrices = {lag: np.ones((7, len(dates)), dtype=bool) for lag in (-1, 0, 1)}
    networks = [
        OpenNetwork(
            network_id=network_id,
            role=role,
            source_key=f"open_role_qc/failure_closure6/{role}",
            wide_path=f"unused/{network_id}.csv",
            wide_sha256=sha,
            manifest_path=f"unused/{network_id}.json",
            n_days=len(dates),
            n_stations=1,
        )
        for network_id, role, sha in (
            ("net-a", "development", "a" * 64),
            ("net-b", "validation", "b" * 64),
        )
    ]
    monkeypatch.setattr(
        eligibility_builder,
        "discover_failure_closure_networks",
        lambda _: (networks, {}),
    )

    def availability(
        _repo: Path,
        network: OpenNetwork,
        binding: dict,
        *,
        split_sha256: str,
    ) -> NetworkAvailability:
        del _repo, binding, split_sha256
        return NetworkAvailability(
            network_id=network.network_id,
            role=network.role,
            dates=dates,
            site_ids=("00000001" if network.network_id == "net-a" else "00000002",),
            available_by_lag=matrices,
            train_mask=np.asarray(dates.year <= 2002, dtype=bool),
            provenance={
                "open_qc_wide_sha256": network.wide_sha256,
                "coverage_sha256": (
                    "2" * 64 if network.network_id == "net-a" else "3" * 64
                ),
            },
        )

    monkeypatch.setattr(eligibility_builder, "_load_network_availability", availability)
    output = tmp_path / "built_eligibility"
    manifest = build_pre_score_eligibility(
        repo_root=tmp_path,
        workload_manifest_path=paths["workload"],
        output_dir=output,
    )
    assert manifest["observed_item_records"] == 2 * len(PRIMARY_COMMON_GRID)
    assert manifest["status_counts"] == {"complete": 2 * len(PRIMARY_COMMON_GRID)}
    assert manifest["open_qc_temperature_value_columns_read"] == []
    assert manifest["open_qc_temperature_na_availability_read"] is False
    assert manifest["gap_truth_values_read"] is False
    assert (
        len(pd.read_parquet(output / "eligibility.parquet"))
        == manifest["observed_item_records"]
    )
    assert (
        build_pre_score_eligibility(
            repo_root=tmp_path,
            workload_manifest_path=paths["workload"],
            output_dir=output,
        )
        == manifest
    )


def test_freeze_rejects_achieved_skill_in_pre_score_audit(tmp_path: Path) -> None:
    paths = _freeze_fixture(tmp_path)
    eligibility = pd.read_parquet(paths["eligibility"])
    eligibility["achieved_skill"] = 0.99
    eligibility.to_parquet(paths["eligibility"], index=False)
    manifest = json.loads(paths["eligibility_manifest"].read_text(encoding="utf-8"))
    manifest["eligibility_table"]["sha256"] = _sha(paths["eligibility"])
    paths["eligibility_manifest"].write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(PrimaryAggregationBlocked, match="not outcome-blind"):
        freeze_v4_analyzable_lattice(
            workload_manifest_path=paths["workload"],
            predictor_manifest_path=paths["predictor_manifest"],
            eligibility_manifest_path=paths["eligibility_manifest"],
            output_dir=tmp_path / "freeze",
        )


def test_ineligible_event_stratum_is_exhaustively_excluded_not_a_fixed_roster_blocker(
    tmp_path: Path,
) -> None:
    paths = _freeze_fixture(tmp_path)
    _append_ineligible_natural_gap(paths)
    output = tmp_path / "freeze"

    manifest = freeze_v4_analyzable_lattice(
        workload_manifest_path=paths["workload"],
        predictor_manifest_path=paths["predictor_manifest"],
        eligibility_manifest_path=paths["eligibility_manifest"],
        output_dir=output,
    )

    assert manifest["status"] == "frozen_before_v4_scoring"
    readiness = json.loads((output / "readiness_manifest.json").read_text())
    assert readiness["status"] == "frozen_before_v4_scoring"
    assert readiness["execution_allowed"] is True
    assert readiness["analyzable_lattice_frozen"] is True
    assert readiness["v4_results_read"] is False
    assert manifest["execution_allowed"] is True
    assert manifest["network_inference_status"] == (
        "withheld_n_lt_100_network_interval"
    )
    assert manifest["evidence_blockers"] == ["n_analyzable_networks_lt_100"]
    census = json.loads((output / "feasibility_census.json").read_text())
    base = census["lattices"]["base_primary"]
    assert base["status"] == "ready"
    assert base["fixed_roster"]["gaps_by_geometry"]["natural_outage"] == [7]
    assert base["design_candidate_roster"]["gaps_by_geometry"][
        "natural_outage"
    ] == [7, 8]
    assert base["coverage_gate"]["network_geometry_gap_cross_product_required"] is False
    ledger = pd.read_parquet(output / "exhaustive_item_ledger.parquet")
    excluded = ledger.loc[ledger["final_reason"].eq("open_qc_gap_window_incomplete")]
    assert len(excluded) == len(PRIMARY_COMMON_GRID)
    assert not excluded["included"].any()
    attrition = pd.read_parquet(output / "pre_score_exclusion_attrition.parquet")
    assert set(excluded["item_id"]) <= set(attrition["item_id"])
    assert manifest["frozen_roster_may_shrink_after_scoring"] is False


def test_v2_predictor_manifest_is_bound_to_the_exact_draft_and_gap_roster(
    tmp_path: Path,
) -> None:
    paths = _freeze_fixture(tmp_path)
    _convert_predictor_fixture_to_v2(paths)

    manifest = freeze_v4_analyzable_lattice(
        workload_manifest_path=paths["workload"],
        predictor_manifest_path=paths["predictor_manifest"],
        eligibility_manifest_path=paths["eligibility_manifest"],
        output_dir=tmp_path / "freeze",
    )

    assert manifest["status"] == "frozen_before_v4_scoring"

    predictor_manifest = json.loads(
        paths["predictor_manifest"].read_text(encoding="utf-8")
    )
    predictor_manifest["gaps_by_geometry"]["natural_outage"] = []
    predictor_manifest["gap_roster_sha256"] = _canonical_sha(
        {
            "gaps": predictor_manifest["gaps"],
            "gaps_by_geometry": predictor_manifest["gaps_by_geometry"],
        }
    )
    paths["predictor_manifest"].write_text(
        json.dumps(predictor_manifest), encoding="utf-8"
    )
    with pytest.raises(PrimaryAggregationBlocked, match="geometry gap roster"):
        freeze_v4_analyzable_lattice(
            workload_manifest_path=paths["workload"],
            predictor_manifest_path=paths["predictor_manifest"],
            eligibility_manifest_path=paths["eligibility_manifest"],
            output_dir=tmp_path / "tampered",
        )


def test_pre_score_bundle_rejects_blocked_base_lattice(tmp_path: Path) -> None:
    paths = _freeze_fixture(tmp_path)
    freeze_dir = tmp_path / "freeze"
    freeze_v4_analyzable_lattice(
        workload_manifest_path=paths["workload"],
        predictor_manifest_path=paths["predictor_manifest"],
        eligibility_manifest_path=paths["eligibility_manifest"],
        output_dir=freeze_dir,
    )
    manifest_path = freeze_dir / "lattice_freeze_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "blocked_base_lattice_insufficient_pre_score_support"
    manifest_path.chmod(0o644)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(PrimaryAggregationBlocked, match="ready frozen base"):
        create_pre_score_freeze_bundle(
            index_draft_manifest_path=paths["workload"],
            eligibility_manifest_path=paths["eligibility_manifest"],
            lattice_freeze_manifest_path=manifest_path,
            output_path=tmp_path / "bundle.json",
        )


def test_pre_score_bundle_requires_both_sensitivity_lattices(tmp_path: Path) -> None:
    paths = _freeze_fixture(tmp_path)
    freeze_dir = tmp_path / "freeze"
    freeze_v4_analyzable_lattice(
        workload_manifest_path=paths["workload"],
        predictor_manifest_path=paths["predictor_manifest"],
        eligibility_manifest_path=paths["eligibility_manifest"],
        output_dir=freeze_dir,
    )
    manifest_path = freeze_dir / "lattice_freeze_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sensitivity_lattices"].pop("M_H")
    manifest_path.chmod(0o644)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(PrimaryAggregationBlocked, match="exact M and M_H"):
        create_pre_score_freeze_bundle(
            index_draft_manifest_path=paths["workload"],
            eligibility_manifest_path=paths["eligibility_manifest"],
            lattice_freeze_manifest_path=manifest_path,
            output_path=tmp_path / "bundle.json",
        )


def test_complete_results_bind_to_frozen_lattice_and_validate_for_t4_t5(
    tmp_path: Path,
) -> None:
    paths = _freeze_fixture(tmp_path)
    freeze_dir = tmp_path / "freeze"
    freeze = freeze_v4_analyzable_lattice(
        workload_manifest_path=paths["workload"],
        predictor_manifest_path=paths["predictor_manifest"],
        eligibility_manifest_path=paths["eligibility_manifest"],
        output_dir=freeze_dir,
    )
    assert freeze["n_analyzable_items"] == 2 * len(PRIMARY_COMMON_GRID)
    census = json.loads((freeze_dir / "feasibility_census.json").read_text())
    assert census["lattices"]["base_primary"]["status"] == "ready"
    assert census["lattices"]["sensitivity_M"]["status"].startswith("blocked")
    assert census["lattices"]["sensitivity_M_H"]["status"].startswith("blocked")
    ledger = pd.read_parquet(freeze_dir / "exhaustive_item_ledger.parquet")
    assert len(ledger) == len(pd.read_parquet(paths["results"]))
    assert ledger["included"].all()
    bundle_path = tmp_path / "pre_score_freeze_manifest.json"
    bundle = create_pre_score_freeze_bundle(
        index_draft_manifest_path=paths["workload"],
        eligibility_manifest_path=paths["eligibility_manifest"],
        lattice_freeze_manifest_path=freeze_dir / "lattice_freeze_manifest.json",
        output_path=bundle_path,
    )
    assert bundle["status"] == "complete_outcome_blind_pre_score_freeze"
    assert bundle["base_lattice_status"] == "frozen_before_v4_scoring"
    predictor_binding = json.loads(
        (freeze_dir / "operator_predictor_manifest.json").read_text(encoding="utf-8")
    )
    assert len(predictor_binding["join_keys_sha256"]) == 64
    assert len(predictor_binding["operator_univariate_columns_sha256"]) == 64
    lattice = pd.read_parquet(freeze_dir / "analyzable_lattice.parquet")
    assert "observed_achieved_skill" not in lattice
    assert (
        lattice.groupby(
            ["role", "network_id", "station_id", "geometry", "geometry_id"],
            dropna=False,
        )
        .size()
        .eq(len(PRIMARY_COMMON_GRID))
        .all()
    )

    workload = json.loads(paths["workload"].read_text(encoding="utf-8"))
    workload["manifest_schema"] = V4_WORKLOAD_SCHEMA
    workload["execution_allowed"] = True
    workload["pre_score_freeze"] = {
        "sha256": "f" * 64,
        "artifacts": {
            "base_lattice_manifest": {
                "sha256": _sha(freeze_dir / "lattice_freeze_manifest.json")
            }
        },
    }
    workload["execution_code_inventory"] = {"inventory_sha256": "c" * 64}
    paths["workload"].write_text(json.dumps(workload), encoding="utf-8")
    chunk_dir = tmp_path / "chunk_0000000_all"
    chunk_dir.mkdir()
    chunk_results = chunk_dir / "results.parquet"
    chunk_results.write_bytes(paths["results"].read_bytes())
    chunk_manifest = {
        "workload_manifest_sha256": _sha(paths["workload"]),
        "pre_score_freeze_sha256": "f" * 64,
        "execution_head_commit": "d" * 40,
        "execution_code_inventory_sha256": "c" * 64,
        "start_ordinal": 0,
        "end_ordinal_exclusive": len(pd.read_parquet(paths["results"])),
        "results_path": chunk_results.name,
        "results_format": "parquet",
        "results_sha256": _sha(chunk_results),
    }
    chunk_manifest_path = chunk_dir / "manifest.json"
    chunk_manifest_path.write_text(json.dumps(chunk_manifest), encoding="utf-8")
    aggregation = {
        "manifest_schema": V4_AGGREGATION_SCHEMA,
        "status": "complete",
        "completeness": "complete",
        "formal_result_generated": True,
        "all_executions_successful": True,
        "workload_manifest_sha256": _sha(paths["workload"]),
        "work_item_identity_sha256": workload["work_item_identity_sha256"],
        "pre_score_freeze_sha256": "f" * 64,
        "execution_head_commit": "d" * 40,
        "execution_code_inventory_sha256": "c" * 64,
        "sealed_temperature_records_read": False,
        "merged_item_results": {
            "path": paths["results"].name,
            "sha256": _sha(paths["results"]),
            "n_rows": len(pd.read_parquet(paths["results"])),
        },
        "n_chunks": 1,
        "chunk_manifest_records": [
            {
                "path": str(chunk_manifest_path),
                "sha256": _sha(chunk_manifest_path),
                "start_ordinal": 0,
                "end_ordinal_exclusive": len(pd.read_parquet(paths["results"])),
                "results_sha256": _sha(chunk_results),
                "execution_head_commit": "d" * 40,
                "execution_code_inventory_sha256": "c" * 64,
            }
        ],
    }
    aggregation_path = tmp_path / "aggregation.json"
    aggregation_path.write_text(json.dumps(aggregation), encoding="utf-8")
    binding_dir = tmp_path / "binding"
    binding = bind_complete_v4_primary_results(
        workload_manifest_path=paths["workload"],
        aggregation_manifest_path=aggregation_path,
        item_results_path=paths["results"],
        lattice_freeze_manifest_path=freeze_dir / "lattice_freeze_manifest.json",
        output_dir=binding_dir,
    )
    assert binding["primary_complete_item_scope"] == "frozen_analyzable_lattice"
    assert binding["achieved_skill_used_for_selection"] is False
    items, primary, validated = validate_v4_primary_inputs(
        paths["workload"], binding_dir / "post_t2_input_binding.json"
    )
    assert len(items) == len(primary) == 2 * len(PRIMARY_COMMON_GRID)
    assert validated["lattice_freeze_manifest_sha256"] == _sha(
        freeze_dir / "lattice_freeze_manifest.json"
    )
    counterfeit = tmp_path / "counterfeit.parquet"
    forged = pd.read_parquet(paths["results"])
    forged["achieved_skill"] = 42.0
    forged.to_parquet(counterfeit, index=False)
    with pytest.raises(PrimaryAggregationBlocked, match="not bound by aggregation"):
        bind_complete_v4_primary_results(
            workload_manifest_path=paths["workload"],
            aggregation_manifest_path=aggregation_path,
            item_results_path=counterfeit,
            lattice_freeze_manifest_path=freeze_dir / "lattice_freeze_manifest.json",
            output_dir=tmp_path / "counterfeit_binding",
        )
    forged.to_parquet(paths["results"], index=False)
    rebound = json.loads(aggregation_path.read_text(encoding="utf-8"))
    rebound["merged_item_results"]["sha256"] = _sha(paths["results"])
    aggregation_path.write_text(json.dumps(rebound), encoding="utf-8")
    with pytest.raises(PrimaryAggregationBlocked, match="differ from their chunks"):
        bind_complete_v4_primary_results(
            workload_manifest_path=paths["workload"],
            aggregation_manifest_path=aggregation_path,
            lattice_freeze_manifest_path=freeze_dir / "lattice_freeze_manifest.json",
            output_dir=tmp_path / "rebound_counterfeit_binding",
        )
