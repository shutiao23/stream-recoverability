from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.analysis.frozen_pipeline import load_frozen_inputs
from stream_recoverability.experiments.contracts import build_design_contract

SCRIPT = Path(__file__).parents[1] / "scripts/13_aggregate_formal_results.py"
REPO_ROOT = SCRIPT.parents[1]
VERSION_MANIFEST = REPO_ROOT / "data_versions/published_v1/version_manifest.json"
EVIDENCE = build_design_contract(
    design_path=REPO_ROOT / "configs/design_freeze_v1.yaml",
    manifest_path=REPO_ROOT / "study_manifest.yaml",
    experiment_config_path=REPO_ROOT / "configs/experiments.yaml",
    data_version="published_v1",
    evaluation_split="development_test",
    data_version_manifest_path=VERSION_MANIFEST,
)
EVIDENCE_ROW = {
    field: EVIDENCE[field]
    for field in (
        "design_version",
        "design_hash",
        "data_version",
        "evaluation_split",
        "mask_schema_version",
        "model_schema_version",
        "statistics_schema_version",
    )
}


def _load_script():
    spec = importlib.util.spec_from_file_location("aggregate_formal_results", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_unit(scenario: str, model: str, seed: int | None) -> str:
    return f"{scenario}|{model}:{'none' if seed is None else seed}"


def _table_rows(
    scenario: str,
    model: str,
    seed: int | None,
    *,
    mae: float,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    shared = {
        **EVIDENCE_ROW,
        "scenario_id": scenario,
        "model": model,
        "training_seed": seed,
        "mask_seed": 101,
        "station_id": "B1",
        "target": "T",
        "experiment": "DYNAMIC",
        "mask_type": "block",
        "window_length": 30,
        "training_protocol": "seen_length",
    }
    daily = [
        {
            **shared,
            "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=offset),
            "y_true": 10.0 + offset,
            "y_pred": 10.0 + offset + mae,
        }
        for offset in range(2)
    ]
    event = {**shared, "MAE": mae, "RMSE": mae * 1.2, "bias": mae}
    return daily, event


def _write_run(
    directory: Path,
    *,
    suite: str,
    models: list[str],
    evidence_units: list[tuple[str, str, int | None]],
    structural_units: list[tuple[str, str, int | None]] | None = None,
    checkpoint_models: set[str] = frozenset(),
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    daily_rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    evidence_keys: list[str] = []
    checkpoint_keys: list[str] = []
    for position, (scenario, model, seed) in enumerate(evidence_units, start=1):
        daily, event = _table_rows(scenario, model, seed, mae=0.1 * position)
        daily_rows.extend(daily)
        event_rows.append(event)
        key = _run_unit(scenario, model, seed)
        evidence_keys.append(key)
        if model in checkpoint_models:
            checkpoint_keys.append(key)
    structural_keys = [
        _run_unit(scenario, model, seed)
        for scenario, model, seed in (structural_units or [])
    ]
    expected_keys = [*evidence_keys, *structural_keys]
    daily_frame = pd.DataFrame(daily_rows)
    event_frame = pd.DataFrame(event_rows)
    daily_frame.to_parquet(directory / "daily_predictions.parquet", index=False)
    event_frame.to_parquet(directory / "event_metrics.parquet", index=False)

    checkpoint_summaries: list[dict[str, object]] = []
    for model in sorted(checkpoint_models):
        checkpoint = directory / "checkpoints" / f"{model}.pt"
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_bytes(f"checkpoint:{model}".encode())
        checkpoint_summaries.append(
            {
                "model": model,
                "checkpoint_contract_valid": True,
                "checkpoint": {
                    "path": str(checkpoint.resolve()),
                    "size": checkpoint.stat().st_size,
                    "mtime_ns": checkpoint.stat().st_mtime_ns,
                    "sha256": _sha256(checkpoint),
                },
                "checkpoint_sidecar": None,
            }
        )
    unit_fields = {
        "expected_run_unit_keys": expected_keys,
        "completed_run_unit_keys": expected_keys,
        "retryable_run_unit_keys": [],
        "structural_skip_run_unit_keys": structural_keys,
        "expected_evidence_run_unit_keys": evidence_keys,
        "completed_evidence_run_unit_keys": evidence_keys,
        "finite_prediction_run_unit_keys": evidence_keys,
        "finite_event_metric_run_unit_keys": evidence_keys,
        "checkpoint_required_run_unit_keys": checkpoint_keys,
        "checkpoint_valid_run_unit_keys": checkpoint_keys,
    }
    counts = {
        f"{field.removesuffix('_keys')}_count": len(values)
        for field, values in unit_fields.items()
    }
    counts["checkpoint_required_run_count"] = counts.pop(
        "checkpoint_required_run_unit_count"
    )
    counts["checkpoint_valid_run_count"] = counts.pop("checkpoint_valid_run_unit_count")
    manifest = {
        **EVIDENCE,
        "suite": suite,
        "models": models,
        "training_profile": "formal",
        "complete": True,
        "formal_design_complete": True,
        "formal_training_seed_complete": True,
        "formal_mask_seed_complete": True,
        "run_unit_complete": True,
        "evidence_complete": True,
        "finite_predictions": True,
        "finite_event_metrics": True,
        "checkpoint_contract_complete": True,
        "retryable_run_keys": [],
        **unit_fields,
        **counts,
        "expected_run_count": len(expected_keys),
        "completed_status_run_count": len(expected_keys),
        "aggregate_run_count": len(evidence_keys),
        "completed_daily_rows": len(daily_frame),
        "completed_event_rows": len(event_frame),
        "training_checkpoints": checkpoint_summaries,
    }
    (directory / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    formal = tmp_path / "formal"
    results = tmp_path / "results"
    _write_run(
        formal / "core",
        suite="full",
        models=["linear", "final_model_alpha"],
        evidence_units=[
            ("CORE-1", "linear", None),
            ("CORE-1", "final_model_alpha", 11),
        ],
        structural_units=[("CORE-2", "linear", None)],
        checkpoint_models={"final_model_alpha"},
    )
    _write_run(
        formal / "events",
        suite="science_events",
        models=["final_model_alpha"],
        evidence_units=[("EVENT-1", "final_model_alpha", 11)],
        checkpoint_models={"final_model_alpha"},
    )
    registry: dict[str, object] = {
        "schema_version": "formal_suite_registry_v1",
        "finalized": True,
        "suites": [
            {
                "name": "core",
                "path": "core",
                "layout": "direct",
                "manifest_suite": "full",
                "finalized": True,
                "finalized_models": ["linear", "final_model_alpha"],
            },
            {
                "name": "events",
                "path": "events",
                "layout": "direct",
                "manifest_suite": "science_events",
                "finalized": True,
                "finalized_models": ["final_model_alpha"],
            },
        ],
    }
    return formal, results, registry


def _aggregate(module, formal: Path, results: Path, registry: dict[str, object]):
    return module.aggregate_formal_results(
        formal,
        results,
        suite_registry=registry,
        design_path=REPO_ROOT / "configs/design_freeze_v1.yaml",
        manifest_path=REPO_ROOT / "study_manifest.yaml",
        config_path=REPO_ROOT / "configs/experiments.yaml",
        data_version="published_v1",
        evaluation_split="test",
        data_version_manifest_path=VERSION_MANIFEST,
    )


def _mutate_manifest(path: Path, mutation) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mutation(manifest)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_dynamic_registry_aggregates_only_finalized_roster_and_hashes_outputs(
    tmp_path: Path,
) -> None:
    formal, results, registry = _fixture(tmp_path)
    module = _load_script()

    manifest = _aggregate(module, formal, results, registry)

    daily = pd.read_parquet(results / "predictions.parquet")
    events = pd.read_parquet(results / "event_metrics.parquet")
    summary = pd.read_csv(results / "summary_metrics.csv")
    assert set(daily["model"]) == {"linear", "final_model_alpha"}
    assert len(daily) == 6
    assert len(events) == 3
    assert not summary.empty
    assert manifest["evaluation_split"] == "development_test"
    assert manifest["expected_run_unit_count"] == 4
    assert manifest["structural_skip_run_unit_count"] == 1
    assert manifest["completed_evidence_run_unit_count"] == 3
    assert manifest["suite_count"] == 2
    assert manifest["source_run_count"] == 2
    assert manifest["formal_training_seed_complete"] is True
    assert manifest["formal_mask_seed_complete"] is True
    assert manifest["retryable_run_keys"] == []
    assert len(manifest["expected_run_unit_keys_sha256"]) == 64
    for name, path in (
        ("predictions", results / "predictions.parquet"),
        ("event_metrics", results / "event_metrics.parquet"),
        ("summary_metrics", results / "summary_metrics.csv"),
    ):
        assert manifest["artifacts"][name]["sha256"] == _sha256(path)
    persisted = json.loads((formal / "run_manifest.json").read_text())
    assert persisted == manifest
    frozen = load_frozen_inputs(
        results / "predictions.parquet",
        results / "event_metrics.parquet",
        formal / "run_manifest.json",
        REPO_ROOT / "configs/design_freeze_v1.yaml",
    )
    assert len(frozen.predictions) == len(daily)
    assert len(frozen.events) == len(events)


def test_registry_file_is_audited_by_hash(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)
    registry_path = tmp_path / "suite_registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    module = _load_script()

    manifest = module.aggregate_formal_results(
        formal,
        results,
        suite_registry=registry_path,
        design_path=REPO_ROOT / "configs/design_freeze_v1.yaml",
        manifest_path=REPO_ROOT / "study_manifest.yaml",
        config_path=REPO_ROOT / "configs/experiments.yaml",
        data_version="published_v1",
        evaluation_split="development_test",
        data_version_manifest_path=VERSION_MANIFEST,
    )

    assert manifest["suite_registry"]["sha256"] == _sha256(registry_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("complete", False, "complete=true"),
        ("formal_training_seed_complete", False, "formal_training_seed_complete"),
        ("evidence_complete", False, "evidence_complete"),
        ("checkpoint_contract_complete", False, "checkpoint_contract_complete"),
    ],
)
def test_rejects_incomplete_manifest_gates(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    formal, results, registry = _fixture(tmp_path)
    _mutate_manifest(
        formal / "core/run_manifest.json", lambda data: data.__setitem__(field, value)
    )
    module = _load_script()

    with pytest.raises(ValueError, match=message):
        _aggregate(module, formal, results, registry)
    assert not (results / "predictions.parquet").exists()


def test_rejects_retryable_run_units(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)

    def mutation(data):
        data["retryable_run_unit_keys"] = [data["expected_run_unit_keys"][0]]
        data["retryable_run_unit_count"] = 1

    _mutate_manifest(formal / "core/run_manifest.json", mutation)
    module = _load_script()

    with pytest.raises(ValueError, match="retryable run units"):
        _aggregate(module, formal, results, registry)
    assert not (results / "predictions.parquet").exists()


def test_rejects_stale_contract_in_manifest_or_table(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)
    _mutate_manifest(
        formal / "core/run_manifest.json",
        lambda data: data.__setitem__("design_hash", "stale"),
    )
    module = _load_script()

    with pytest.raises(ValueError, match="evidence contract mismatch"):
        _aggregate(module, formal, results, registry)


def test_rejects_stale_relevant_source_identity(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)

    def mutation(data):
        data["code_identity"]["relevant_source_digest"] = "0" * 64

    _mutate_manifest(formal / "core/run_manifest.json", mutation)
    module = _load_script()

    with pytest.raises(ValueError, match="evidence contract mismatch"):
        _aggregate(module, formal, results, registry)


def test_accepts_historical_git_audit_when_code_identity_matches(
    tmp_path: Path,
) -> None:
    formal, results, registry = _fixture(tmp_path)

    def mutation(data):
        data["code_provenance"]["git_commit"] = "f" * 40
        data["code_provenance"]["status"] = "historical"

    _mutate_manifest(formal / "core/run_manifest.json", mutation)
    module = _load_script()

    result = _aggregate(module, formal, results, registry)
    assert result["complete"] is True


def test_rejects_nonfinite_prediction(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)
    path = formal / "core/daily_predictions.parquet"
    frame = pd.read_parquet(path)
    frame.loc[0, "y_pred"] = np.inf
    frame.to_parquet(path, index=False)
    module = _load_script()

    with pytest.raises(ValueError, match="nonfinite y_pred"):
        _aggregate(module, formal, results, registry)


def test_rejects_missing_or_tampered_checkpoint(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)
    checkpoint = formal / "core/checkpoints/final_model_alpha.pt"
    checkpoint.write_bytes(b"tampered")
    module = _load_script()

    with pytest.raises(ValueError, match="recorded size/hash"):
        _aggregate(module, formal, results, registry)


def test_rejects_duplicate_frozen_row_within_source(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)
    path = formal / "core/event_metrics.parquet"
    frame = pd.read_parquet(path)
    pd.concat([frame, frame.iloc[[0]]], ignore_index=True).to_parquet(path, index=False)
    _mutate_manifest(
        formal / "core/run_manifest.json",
        lambda data: data.__setitem__("completed_event_rows", len(frame) + 1),
    )
    module = _load_script()

    with pytest.raises(ValueError, match="duplicate rows"):
        _aggregate(module, formal, results, registry)


def test_rejects_duplicate_run_unit_across_declared_suites(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)
    _write_run(
        formal / "events",
        suite="science_events",
        models=["final_model_alpha"],
        evidence_units=[("CORE-1", "final_model_alpha", 11)],
        checkpoint_models={"final_model_alpha"},
    )
    module = _load_script()

    with pytest.raises(ValueError, match="duplicate rows|duplicate run-unit"):
        _aggregate(module, formal, results, registry)


def test_rejects_missing_expected_daily_or_event_evidence(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)
    path = formal / "core/event_metrics.parquet"
    frame = pd.read_parquet(path)
    frame.iloc[[0]].to_parquet(path, index=False)
    _mutate_manifest(
        formal / "core/run_manifest.json",
        lambda data: data.__setitem__("completed_event_rows", 1),
    )
    module = _load_script()

    with pytest.raises(ValueError, match="expected daily/event evidence is incomplete"):
        _aggregate(module, formal, results, registry)


def test_rejects_inconsistent_structural_skip_contract(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)

    def mutation(data):
        data["structural_skip_run_unit_keys"] = []
        data["structural_skip_run_unit_count"] = 0

    _mutate_manifest(formal / "core/run_manifest.json", mutation)
    module = _load_script()

    with pytest.raises(ValueError, match="structural-skip/evidence contract"):
        _aggregate(module, formal, results, registry)


def test_rejects_roster_mismatch_and_unlisted_child(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)
    registry["suites"][0]["finalized_models"] = ["linear"]
    module = _load_script()

    with pytest.raises(ValueError, match="model roster"):
        _aggregate(module, formal, results, registry)


def test_model_children_layout_uses_only_explicit_dynamic_roster(
    tmp_path: Path,
) -> None:
    formal = tmp_path / "formal"
    results = tmp_path / "results"
    _write_run(
        formal / "dense/model_z",
        suite="science_dense",
        models=["model_z"],
        evidence_units=[("DENSE-Z", "model_z", None)],
    )
    registry = {
        "schema_version": "formal_suite_registry_v1",
        "finalized": True,
        "suites": [
            {
                "name": "dense",
                "path": "dense",
                "layout": "model_children",
                "manifest_suite": "science_dense",
                "finalized": True,
                "finalized_models": ["model_z"],
            }
        ],
    }
    module = _load_script()

    manifest = _aggregate(module, formal, results, registry)

    assert manifest["expected_run_unit_count"] == 1
    assert manifest["suites"][0]["finalized_models"] == ["model_z"]


def test_rejects_unlisted_model_child_directory(tmp_path: Path) -> None:
    formal = tmp_path / "formal"
    results = tmp_path / "results"
    for model in ("model_z", "stale_model"):
        _write_run(
            formal / f"dense/{model}",
            suite="science_dense",
            models=[model],
            evidence_units=[(f"DENSE-{model}", model, None)],
        )
    registry = {
        "schema_version": "formal_suite_registry_v1",
        "finalized": True,
        "suites": [
            {
                "name": "dense",
                "path": "dense",
                "layout": "model_children",
                "manifest_suite": "science_dense",
                "finalized": True,
                "finalized_models": ["model_z"],
            }
        ],
    }
    module = _load_script()

    with pytest.raises(ValueError, match="child directories differ"):
        _aggregate(module, formal, results, registry)
