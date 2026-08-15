from __future__ import annotations

import hashlib
import importlib.util
import json
from functools import cache
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.experiments.contracts import (
    build_design_contract,
    validate_data_version_inputs,
)
from stream_recoverability.masks.anchors import load_frontier_anchor_catalog
from stream_recoverability.masks.event_catalog import (
    event_catalog_sha256,
    load_event_episode_catalog,
)

SCRIPT = Path(__file__).parents[1] / "scripts/13_aggregate_formal_results.py"
REPO_ROOT = SCRIPT.parents[1]
VERSION_MANIFEST = REPO_ROOT / "data_versions/published_v1/version_manifest.json"
FRONTIER_ANCHORS = REPO_ROOT / "metadata/frontier_anchors.csv"
EVENT_CATALOG = REPO_ROOT / "metadata/event_episode_catalog.csv"
SELECTED_MODELS = ["linear", "proposed"]
STRUCTURAL_MODELS = ["independent_flow", "rating_curve"]
COMPARISON_MODELS = [*SELECTED_MODELS, *STRUCTURAL_MODELS]
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

    # These fixtures exercise the aggregator's trust boundary.  Keep the two
    # upstream loaders deterministic, as the registry-builder tests do, while
    # retaining the complete hash-bound roster and authorization mirrors in
    # every artifact passed to the aggregator.
    def stable_roster_loader(path, **_kwargs):
        roster_path = Path(path)
        document = json.loads(roster_path.read_text(encoding="utf-8"))
        return SimpleNamespace(
            manifest_sha256=_sha256(roster_path),
            selected_models=tuple(document["selected_models"]),
            proposed_decision=document["proposed_decision"],
        )

    def stable_authorization(value, *, expected_suite, expected_models, **_kwargs):
        document = json.loads(json.dumps(dict(value)))
        if document.get("schema_version") != "formal_execution_authorization_v1":
            raise ValueError("formal execution authorization schema is not frozen")
        if document.get("formal_evidence") is not True:
            raise ValueError("formal execution authorization requires formal evidence")
        if document.get("suite") != expected_suite:
            raise ValueError("formal execution authorization is bound to another suite")
        if document.get("expected_models") != list(expected_models):
            raise ValueError("runner models differ from finalized formal authorization")
        return document

    module.load_finalized_model_roster = stable_roster_loader
    module.validate_formal_authorization = stable_authorization
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _file_identity(path: Path) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _run_unit(scenario: str, model: str, seed: int | None) -> str:
    return f"{scenario}|{model}:{'none' if seed is None else seed}"


@cache
def _data_version_input_identity() -> dict[str, object]:
    identity = validate_data_version_inputs(
        data_version_manifest_path=VERSION_MANIFEST,
        data_version="published_v1",
        wide_path=VERSION_MANIFEST.parent / "daily_wide.parquet",
        quality_path=VERSION_MANIFEST.parent / "daily_long.parquet",
        require_manifest=True,
        require_quality=True,
    )
    assert identity is not None
    return identity


@cache
def _frontier_catalog() -> pd.DataFrame:
    return load_frontier_anchor_catalog(
        FRONTIER_ANCHORS,
        expected_data_version="published_v1",
        expected_evaluation_split="development_test",
    )


@cache
def _event_catalog() -> pd.DataFrame:
    return load_event_episode_catalog(
        EVENT_CATALOG,
        expected_data_version="published_v1",
        expected_evaluation_split="development_test",
    )


def _write_roster(tmp_path: Path) -> Path:
    path = tmp_path / "validation/finalized_model_roster.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "finalized_model_roster_v1",
                "finalized": True,
                "selected_models": SELECTED_MODELS,
                "best_traditional_model": "linear",
                "proposed_decision": "include_proposed_formally",
            }
        ),
        encoding="utf-8",
    )
    return path


def _roster_mirror(roster_path: Path) -> dict[str, object]:
    document = json.loads(roster_path.read_text(encoding="utf-8"))
    return {
        "path": str(roster_path.resolve()),
        "sha256": _sha256(roster_path),
        "selected_models": list(document["selected_models"]),
        "proposed_decision": document["proposed_decision"],
    }


def _anchor_binding(target: str) -> dict[str, object]:
    catalog = _frontier_catalog()
    row = catalog.loc[
        catalog["station_id"].astype(str).eq("B1")
        & catalog["target"].astype(str).eq(target)
        & catalog["mask_seed"].astype(int).eq(101)
    ].iloc[0]
    return {
        "anchor_id": str(row["anchor_id"]),
        "anchor_target": str(row["target"]),
        "anchor_mask_seed": int(row["mask_seed"]),
        "center_date": str(row["center_date"]),
        "center_index": int(row["center_index"]),
        "anchor_data_version": str(row["data_version"]),
        "anchor_evaluation_split": str(row["evaluation_split"]),
        "anchor_source_split": str(row["source_split"]),
        "anchor_max_supported_length": int(row["max_supported_length"]),
        "anchor_start_month": int(row["start_month"]),
        "anchor_season": str(row["season"]),
        "anchor_year": int(row["year"]),
        "anchor_hydrologic_state": str(row["hydrologic_state"]),
    }


def _append_evidence(
    daily_rows: list[dict[str, object]],
    event_rows: list[dict[str, object]],
    shared: dict[str, object],
    *,
    mae: float,
) -> None:
    for offset in range(2):
        daily_rows.append(
            {
                **shared,
                "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=offset),
                "y_true": 10.0 + offset,
                "y_pred": 10.0 + offset + mae,
            }
        )
    event_rows.append({**shared, "MAE": mae, "RMSE": mae * 1.2, "bias": mae})


def _formal_authorization(
    suite: str, models: list[str], roster: dict[str, object]
) -> dict[str, object]:
    derived = suite in {
        "science_compensation",
        "retrained_information_upper_bounds",
    }
    return {
        "schema_version": "formal_execution_authorization_v1",
        "suite": suite,
        "formal_evidence": True,
        "model_scope": (
            "authorized_proposed_estimand"
            if derived
            else "t_roster_plus_internal_structural_baselines"
        ),
        "target_scope": ["T"] if derived else ["T", "F", "L"],
        "expected_models": ["proposed"] if derived else models,
        "finalized_model_roster": roster,
    }


def _event_scenarios() -> list[tuple[str, str, str, str]]:
    suffix = "-DEVELOPMENT_TEST-R0000"
    scenarios = [
        (f"M7A-STRESS-{station}-{event}{suffix}", target, "M7a", station)
        for station in ("B1", "S2", "P3")
        for event, target in (
            ("HIGH_TEMPERATURE", "T"),
            ("RAPID_WARMING", "T"),
            ("FLOOD", "F"),
            ("LOW_FLOW", "F"),
        )
    ]
    eligible = _event_catalog().loc[_event_catalog()["analysis_eligible"].astype(bool)]
    for row in eligible.itertuples(index=False):
        scenarios.append(
            (
                f"M7B-EVENT-{row.event_id}{suffix}",
                str(row.target),
                "M7b",
                str(row.station_id),
            )
        )
        scenarios.append(
            (
                f"M7B-CONTROL-{row.control_id}{suffix}",
                str(row.target),
                "M7b",
                str(row.station_id),
            )
        )
    return scenarios


def _formal_seeds(model: str) -> tuple[int | None, ...]:
    if model == "proposed":
        return (11, 22, 33, 44, 55)
    if model in {"information_compensation", "retrained_information_upper_bound"}:
        return (11,)
    return (None,)


def _write_run(
    directory: Path,
    *,
    suite: str,
    models: list[str],
    roster_path: Path,
    scenario_prefix: str,
    full_event_inventory: bool = False,
    checkpoint_model: str | None = None,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    daily_rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    evidence_keys: list[str] = []
    structural_keys: list[str] = []
    checkpoint_keys: list[str] = []
    roster = _roster_mirror(roster_path)
    row_contract = {
        **EVIDENCE_ROW,
        "evidence_role": "formal_development_evaluation",
        "formal_evidence": True,
    }
    position = 0
    for model in models:
        target = "F" if model in STRUCTURAL_MODELS else "T"
        scenario = f"{scenario_prefix}-{target}-R0101"
        for seed in _formal_seeds(model):
            key = _run_unit(scenario, model, seed)
            evidence_keys.append(key)
            position += 1
            shared = {
                **row_contract,
                "scenario_id": scenario,
                "model": model,
                "training_seed": seed,
                "mask_seed": 101,
                "station_id": "B1",
                "station_ids": json.dumps(["B1"]),
                "target": target,
                "experiment": "FORMAL",
                "mask_type": "block",
                "window_length": 30,
                "training_protocol": "seen_length",
                **_anchor_binding(target),
            }
            _append_evidence(daily_rows, event_rows, shared, mae=0.01 * position)
            if model == checkpoint_model:
                checkpoint_keys.append(key)

    if full_event_inventory:
        for scenario, target, experiment, station_id in _event_scenarios():
            for model in models:
                for seed in _formal_seeds(model):
                    key = _run_unit(scenario, model, seed)
                    if model in STRUCTURAL_MODELS and target != "F":
                        structural_keys.append(key)
                        continue
                    evidence_keys.append(key)
                    position += 1
                    shared = {
                        **row_contract,
                        "scenario_id": scenario,
                        "model": model,
                        "training_seed": seed,
                        "mask_seed": 0,
                        "station_id": station_id,
                        "station_ids": json.dumps([station_id]),
                        "target": target,
                        "experiment": experiment,
                        "mask_type": "event",
                        "window_length": 15,
                        "training_protocol": "seen_length",
                    }
                    _append_evidence(
                        daily_rows, event_rows, shared, mae=0.01 + 1e-6 * position
                    )

    expected_keys = [*evidence_keys, *structural_keys]
    daily_frame = pd.DataFrame(daily_rows)
    event_frame = pd.DataFrame(event_rows)
    daily_frame.to_parquet(directory / "daily_predictions.parquet", index=False)
    event_frame.to_parquet(directory / "event_metrics.parquet", index=False)

    checkpoint_summaries: list[dict[str, object]] = []
    for model in [checkpoint_model] if checkpoint_model is not None else []:
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
        "code_provenance": {
            **EVIDENCE["code_provenance"],
            "tracked_worktree_clean": True,
            "relevant_source_clean": True,
            "dirty_tracked_paths": [],
            "relevant_untracked_paths": [],
            "external_relevant_input_count": 0,
            "status": "clean",
        },
        "data_version_input_identity": _data_version_input_identity(),
        "suite": suite,
        "models": models,
        "expected_formal_models": models,
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
        "evidence_role": "formal_development_evaluation",
        "formal_evidence": True,
        **unit_fields,
        **counts,
        "expected_run_count": len(expected_keys),
        "completed_status_run_count": len(expected_keys),
        "aggregate_run_count": len(evidence_keys),
        "completed_daily_rows": len(daily_frame),
        "completed_event_rows": len(event_frame),
        "training_checkpoints": checkpoint_summaries,
        "frontier_anchor_catalog_path": str(FRONTIER_ANCHORS.resolve()),
        "frontier_anchor_catalog_sha256": _sha256(FRONTIER_ANCHORS),
        "frontier_anchor_count": len(_frontier_catalog()),
        "formal_grid_contract_complete": True,
        "formal_grid_contract": {
            "suite": suite,
            "frontier_anchor_required": True,
            "frontier_anchor_catalog_path": str(FRONTIER_ANCHORS.resolve()),
            "frontier_anchor_catalog_sha256": _sha256(FRONTIER_ANCHORS),
            "frontier_anchor_count": len(_frontier_catalog()),
            "frontier_anchor_scenario_count": len(models),
            "frontier_anchor_bindings_sha256": "a" * 64,
            "event_uncertainty_required": suite == "full",
        },
        "finalized_model_roster": roster,
        "formal_execution_authorization": _formal_authorization(suite, models, roster),
    }
    if full_event_inventory:
        catalog = _event_catalog()
        eligible = catalog.loc[catalog["analysis_eligible"].astype(bool)]
        event_fields = {
            "event_catalog_path": str(EVENT_CATALOG.resolve()),
            "event_catalog_sha256": event_catalog_sha256(catalog),
            "event_catalog_episode_count": len(catalog),
            "event_catalog_analysis_count": len(eligible),
        }
        manifest.update(event_fields)
        manifest["formal_grid_contract"].update(
            {
                **event_fields,
                "m7a_scenario_count": 12,
                "m7b_scenario_count": 2 * len(eligible),
            }
        )
    (directory / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _builder_identity() -> dict[str, object]:
    sources = []
    for relative in (
        "scripts/21_build_formal_suite_registry.py",
        "src/stream_recoverability/analysis/formal_registry.py",
    ):
        path = REPO_ROOT / relative
        sources.append(
            {"path": relative, "bytes": path.stat().st_size, "sha256": _sha256(path)}
        )
    identity: dict[str, object] = {
        "schema_version": "formal_registry_builder_identity_v1",
        "sources": sources,
        "identity_hash_scope": "canonical_json_excluding_identity_sha256",
    }
    identity["identity_sha256"] = _canonical_sha256(identity)
    return identity


def _refresh_registry(registry: dict[str, object]) -> None:
    sources = registry["sources"]
    assert isinstance(sources, list)
    suite_hashes: dict[str, list[str]] = {}
    for source in sources:
        assert isinstance(source, dict)
        directory = Path(str(source["run_directory"]))
        source["manifest"] = _file_identity(directory / "run_manifest.json")
        source["daily_predictions"] = _file_identity(
            directory / "daily_predictions.parquet"
        )
        source["event_metrics"] = _file_identity(directory / "event_metrics.parquet")
        suite_hashes.setdefault(str(source["suite"]), []).append(
            str(source["manifest"]["sha256"])
        )
    role_suites = {
        "core_full": ["full"],
        "dense_frontier": ["science_dense"],
        "network_resilience": ["science_resilience"],
        "event_uncertainty": ["full"],
        "operational_dropout": ["science_compensation"],
        "retrained_upper_bound": ["retrained_information_upper_bounds"],
    }
    roles = registry["suite_roles"]
    assert isinstance(roles, list)
    for role in roles:
        assert isinstance(role, dict)
        suites = role_suites[str(role["role"])]
        role["source_manifest_sha256"] = sorted(
            digest for suite in suites for digest in suite_hashes.get(suite, [])
        )
    registry.pop("registry_sha256", None)
    registry["registry_sha256"] = _canonical_sha256(registry)


def _source_entry(directory: Path) -> dict[str, object]:
    manifest = json.loads((directory / "run_manifest.json").read_text(encoding="utf-8"))
    return {
        "suite": manifest["suite"],
        "run_directory": str(directory.resolve()),
        "manifest": _file_identity(directory / "run_manifest.json"),
        "daily_predictions": _file_identity(directory / "daily_predictions.parquet"),
        "event_metrics": _file_identity(directory / "event_metrics.parquet"),
        "models": manifest["models"],
    }


def _fixture(
    tmp_path: Path, *, dense_model_children: bool = False
) -> tuple[Path, Path, dict[str, object]]:
    formal = tmp_path / "formal"
    results = tmp_path / "results"
    roster_path = _write_roster(tmp_path)
    _write_run(
        formal / "full",
        suite="full",
        models=COMPARISON_MODELS,
        roster_path=roster_path,
        scenario_prefix="FULL",
        full_event_inventory=True,
        checkpoint_model="proposed",
    )
    dense_directories: list[Path] = []
    if dense_model_children:
        for model in COMPARISON_MODELS:
            directory = formal / f"dense/{model}"
            _write_run(
                directory,
                suite="science_dense",
                models=[model],
                roster_path=roster_path,
                scenario_prefix=f"DENSE-{model.upper()}",
            )
            dense_directories.append(directory)
    else:
        directory = formal / "dense"
        _write_run(
            directory,
            suite="science_dense",
            models=COMPARISON_MODELS,
            roster_path=roster_path,
            scenario_prefix="DENSE",
        )
        dense_directories.append(directory)
    _write_run(
        formal / "resilience",
        suite="science_resilience",
        models=SELECTED_MODELS,
        roster_path=roster_path,
        scenario_prefix="RESILIENCE",
    )
    _write_run(
        formal / "operational",
        suite="science_compensation",
        models=["information_compensation"],
        roster_path=roster_path,
        scenario_prefix="OPERATIONAL",
    )
    _write_run(
        formal / "retrained",
        suite="retrained_information_upper_bounds",
        models=["retrained_information_upper_bound"],
        roster_path=roster_path,
        scenario_prefix="RETRAINED",
        checkpoint_model="retrained_information_upper_bound",
    )
    run_directories = [
        formal / "full",
        *dense_directories,
        formal / "resilience",
        formal / "operational",
        formal / "retrained",
    ]
    sources = [_source_entry(directory) for directory in run_directories]
    hashes_by_suite: dict[str, list[str]] = {}
    for source in sources:
        hashes_by_suite.setdefault(str(source["suite"]), []).append(
            str(source["manifest"]["sha256"])
        )
    role_specs = (
        ("core_full", "full", COMPARISON_MODELS),
        ("dense_frontier", "science_dense", COMPARISON_MODELS),
        ("network_resilience", "science_resilience", SELECTED_MODELS),
        ("event_uncertainty", "full", COMPARISON_MODELS),
        ("operational_dropout", "science_compensation", ["information_compensation"]),
        (
            "retrained_upper_bound",
            "retrained_information_upper_bounds",
            ["retrained_information_upper_bound"],
        ),
    )
    suite_roles = [
        {
            "role": role,
            "status": "complete",
            "reason": None,
            "manifest_suites": [suite],
            "source_manifest_sha256": sorted(hashes_by_suite[suite]),
            "expected_models": models,
        }
        for role, suite, models in role_specs
    ]
    suite_entries = [
        {
            "name": "full",
            "path": "full",
            "layout": "direct",
            "manifest_suite": "full",
            "finalized": True,
            "finalized_models": COMPARISON_MODELS,
            "allowed_derived_models": [],
        },
        {
            "name": "science_dense",
            "path": "dense",
            "layout": "model_children" if dense_model_children else "direct",
            "manifest_suite": "science_dense",
            "finalized": True,
            "finalized_models": COMPARISON_MODELS,
            "allowed_derived_models": [],
        },
        {
            "name": "science_resilience",
            "path": "resilience",
            "layout": "direct",
            "manifest_suite": "science_resilience",
            "finalized": True,
            "finalized_models": SELECTED_MODELS,
            "allowed_derived_models": [],
        },
        {
            "name": "science_compensation",
            "path": "operational",
            "layout": "direct",
            "manifest_suite": "science_compensation",
            "finalized": True,
            "finalized_models": ["information_compensation"],
            "allowed_derived_models": [],
        },
        {
            "name": "retrained_information_upper_bounds",
            "path": "retrained",
            "layout": "direct",
            "manifest_suite": "retrained_information_upper_bounds",
            "finalized": True,
            "finalized_models": ["retrained_information_upper_bound"],
            "allowed_derived_models": [],
        },
    ]
    registry: dict[str, object] = {
        "schema_version": "formal_suite_registry_v1",
        "finalized": True,
        "bundle_kind": "primary",
        "bundle_role": "primary",
        "data_version": "published_v1",
        "evaluation_split": "development_test",
        "design_hash": EVIDENCE["design_hash"],
        "code_identity": EVIDENCE["code_identity"],
        "registry_builder_identity": _builder_identity(),
        "data_version_manifest": _file_identity(VERSION_MANIFEST),
        "data_version_input_identity": _data_version_input_identity(),
        "frontier_anchor_catalog": {
            **_file_identity(FRONTIER_ANCHORS),
            "count": len(_frontier_catalog()),
            "data_version": "published_v1",
            "evaluation_split": "development_test",
        },
        "formal_root": str(formal.resolve()),
        "finalized_model_roster": _roster_mirror(roster_path),
        "not_applicable_suites": [],
        "required_suite_roles": [role for role, _, _ in role_specs],
        "suite_roles": suite_roles,
        "sources": sources,
        "suites": suite_entries,
        "registry_hash_scope": "canonical_json_excluding_registry_sha256",
    }
    registry["registry_sha256"] = _canonical_sha256(registry)
    return formal, results, registry


def _aggregate(module, formal: Path, results: Path, registry: dict[str, object]):
    _refresh_registry(registry)
    registry_path = formal.parent / "suite_registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    return module.aggregate_formal_results(
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
    expected_models = {
        *COMPARISON_MODELS,
        "information_compensation",
        "retrained_information_upper_bound",
    }
    source_manifests = [
        json.loads(Path(str(source["manifest"]["path"])).read_text(encoding="utf-8"))
        for source in registry["sources"]
    ]
    assert set(daily["model"]) == expected_models
    assert len(daily) == sum(item["completed_daily_rows"] for item in source_manifests)
    assert len(events) == sum(item["completed_event_rows"] for item in source_manifests)
    assert not summary.empty
    assert manifest["evaluation_split"] == "development_test"
    assert manifest["expected_run_unit_count"] == sum(
        item["expected_run_unit_count"] for item in source_manifests
    )
    assert manifest["structural_skip_run_unit_count"] == sum(
        item["structural_skip_run_unit_count"] for item in source_manifests
    )
    assert manifest["completed_evidence_run_unit_count"] == sum(
        item["completed_evidence_run_unit_count"] for item in source_manifests
    )
    assert manifest["suite_count"] == 5
    assert manifest["source_run_count"] == 5
    assert manifest["required_suite_roles"] == [
        "core_full",
        "dense_frontier",
        "network_resilience",
        "event_uncertainty",
        "operational_dropout",
        "retrained_upper_bound",
    ]
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
        formal / "full/run_manifest.json", lambda data: data.__setitem__(field, value)
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

    _mutate_manifest(formal / "full/run_manifest.json", mutation)
    module = _load_script()

    with pytest.raises(ValueError, match="retryable run units"):
        _aggregate(module, formal, results, registry)
    assert not (results / "predictions.parquet").exists()


def test_rejects_stale_contract_in_manifest_or_table(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)
    _mutate_manifest(
        formal / "full/run_manifest.json",
        lambda data: data.__setitem__("design_hash", "stale"),
    )
    module = _load_script()

    with pytest.raises(ValueError, match="evidence contract mismatch"):
        _aggregate(module, formal, results, registry)


def test_rejects_stale_relevant_source_identity(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)

    def mutation(data):
        data["code_identity"]["relevant_source_digest"] = "0" * 64

    _mutate_manifest(formal / "full/run_manifest.json", mutation)
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

    _mutate_manifest(formal / "full/run_manifest.json", mutation)
    module = _load_script()

    result = _aggregate(module, formal, results, registry)
    assert result["complete"] is True


def test_rejects_nonfinite_prediction(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)
    path = formal / "full/daily_predictions.parquet"
    frame = pd.read_parquet(path)
    frame.loc[0, "y_pred"] = np.inf
    frame.to_parquet(path, index=False)
    module = _load_script()

    with pytest.raises(ValueError, match="nonfinite y_pred"):
        _aggregate(module, formal, results, registry)


def test_rejects_missing_or_tampered_checkpoint(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)
    checkpoint = formal / "full/checkpoints/proposed.pt"
    checkpoint.write_bytes(b"tampered")
    module = _load_script()

    with pytest.raises(ValueError, match="recorded size/hash"):
        _aggregate(module, formal, results, registry)


def test_rejects_duplicate_frozen_row_within_source(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)
    path = formal / "full/event_metrics.parquet"
    frame = pd.read_parquet(path)
    pd.concat([frame, frame.iloc[[0]]], ignore_index=True).to_parquet(path, index=False)
    _mutate_manifest(
        formal / "full/run_manifest.json",
        lambda data: data.__setitem__("completed_event_rows", len(frame) + 1),
    )
    module = _load_script()

    with pytest.raises(ValueError, match="duplicate rows"):
        _aggregate(module, formal, results, registry)


def test_information_coalitions_extend_the_frozen_table_key() -> None:
    module = _load_script()
    rows = pd.DataFrame(
        {
            "scenario_id": ["INFO-1", "INFO-1"],
            "model": ["proposed", "proposed"],
            "training_seed": [11, 11],
            "mask_seed": [101, 101],
            "date": pd.to_datetime(["2020-01-01", "2020-01-01"]),
            "station_id": ["B1", "B1"],
            "target": ["T", "T"],
            "information_combination": ["S0", "S0+A"],
        }
    )
    module._require_unique(rows, module.DAILY_KEY, "information daily")
    duplicated = pd.concat([rows, rows.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate rows"):
        module._require_unique(duplicated, module.DAILY_KEY, "information daily")


def test_summary_never_pools_operational_and_retrained_estimands() -> None:
    module = _load_script()
    events = pd.DataFrame(
        {
            "model": ["proposed", "proposed"],
            "target": ["T", "T"],
            "station_id": ["B1", "B1"],
            "information_combination": ["S0+A", "S0+A"],
            "attribution_estimand": [
                "operational_dropout",
                "retrained_upper_bound",
            ],
            "information_estimand": [
                "operational_dropout",
                "retrained_upper_bound",
            ],
            "MAE": [1.0, 3.0],
            "RMSE": [1.2, 3.2],
        }
    )
    summary = module._summary_metrics(events)
    assert len(summary) == 2
    assert set(summary["attribution_estimand"]) == {
        "operational_dropout",
        "retrained_upper_bound",
    }
    assert set(summary["MAE"]) == {1.0, 3.0}


def test_dynamic_aggregator_accepts_nine_coalitions_in_one_retrained_run_unit(
    tmp_path: Path,
) -> None:
    formal, results, registry = _fixture(tmp_path)
    run = formal / "retrained"
    coalitions = (
        "S0",
        "S0+A",
        "S0+B",
        "S0+C",
        "S0+D",
        "S0+A+B",
        "S0+A+C",
        "S0+A+D",
        "S0+A+B+C+D",
    )
    base_daily = pd.read_parquet(run / "daily_predictions.parquet")
    base_event = pd.read_parquet(run / "event_metrics.parquet")
    daily = pd.concat(
        [
            base_daily.assign(
                information_combination=coalition,
                attribution_estimand="retrained_upper_bound",
                information_estimand="retrained_upper_bound",
            )
            for coalition in coalitions
        ],
        ignore_index=True,
    )
    events = pd.concat(
        [
            base_event.assign(
                information_combination=coalition,
                attribution_estimand="retrained_upper_bound",
                information_estimand="retrained_upper_bound",
            )
            for coalition in coalitions
        ],
        ignore_index=True,
    )
    daily.to_parquet(run / "daily_predictions.parquet", index=False)
    events.to_parquet(run / "event_metrics.parquet", index=False)
    _mutate_manifest(
        run / "run_manifest.json",
        lambda data: data.update(
            {
                "completed_daily_rows": len(daily),
                "completed_event_rows": len(events),
            }
        ),
    )
    manifest = _aggregate(_load_script(), formal, results, registry)
    aggregated = pd.read_parquet(results / "event_metrics.parquet")
    summary = pd.read_csv(results / "summary_metrics.csv")
    retrained = aggregated.loc[
        aggregated["model"].eq("retrained_information_upper_bound")
    ]
    retrained_summary = summary.loc[
        summary["model"].eq("retrained_information_upper_bound")
    ]
    assert manifest["expected_run_unit_count"] > 1
    assert len(retrained) == 9
    assert set(retrained["information_combination"]) == set(coalitions)
    assert retrained_summary["attribution_estimand"].eq("retrained_upper_bound").all()


def test_rejects_duplicate_run_unit_across_declared_suites(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)
    _write_run(
        formal / "resilience",
        suite="science_resilience",
        models=SELECTED_MODELS,
        roster_path=tmp_path / "validation/finalized_model_roster.json",
        scenario_prefix="FULL",
    )
    module = _load_script()

    with pytest.raises(ValueError, match="duplicate rows|duplicate run-unit"):
        _aggregate(module, formal, results, registry)


def test_rejects_missing_expected_daily_or_event_evidence(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)
    path = formal / "full/event_metrics.parquet"
    frame = pd.read_parquet(path)
    frame.iloc[1:].to_parquet(path, index=False)
    _mutate_manifest(
        formal / "full/run_manifest.json",
        lambda data: data.__setitem__("completed_event_rows", len(frame) - 1),
    )
    module = _load_script()

    with pytest.raises(ValueError, match="expected daily/event evidence is incomplete"):
        _aggregate(module, formal, results, registry)


def test_rejects_inconsistent_structural_skip_contract(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path)

    def mutation(data):
        data["structural_skip_run_unit_keys"] = []
        data["structural_skip_run_unit_count"] = 0

    _mutate_manifest(formal / "full/run_manifest.json", mutation)
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
    formal, results, registry = _fixture(tmp_path, dense_model_children=True)
    module = _load_script()

    manifest = _aggregate(module, formal, results, registry)

    dense = next(
        suite for suite in manifest["suites"] if suite["name"] == "science_dense"
    )
    assert manifest["expected_run_unit_count"] > len(COMPARISON_MODELS)
    assert dense["layout"] == "model_children"
    assert dense["finalized_models"] == COMPARISON_MODELS


def test_rejects_unlisted_model_child_directory(tmp_path: Path) -> None:
    formal, results, registry = _fixture(tmp_path, dense_model_children=True)
    (formal / "dense/stale_model").mkdir()
    module = _load_script()

    with pytest.raises(ValueError, match="child directories differ"):
        _aggregate(module, formal, results, registry)
