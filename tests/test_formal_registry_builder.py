from __future__ import annotations

import hashlib
import importlib.util
import json
from functools import cache
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from stream_recoverability.analysis import formal_registry
from stream_recoverability.analysis.formal_registry import (
    build_formal_suite_registry,
)
from stream_recoverability.experiments.contracts import build_design_contract
from stream_recoverability.experiments.validation import (
    validation_anchor_catalog_identity,
)

REPOSITORY_ROOT = Path(__file__).parents[1]
DESIGN = REPOSITORY_ROOT / "configs/design_freeze_v1.yaml"
STUDY_MANIFEST = REPOSITORY_ROOT / "study_manifest.yaml"
EXPERIMENT_CONFIG = REPOSITORY_ROOT / "configs/experiments.yaml"
VERSION_MANIFEST = REPOSITORY_ROOT / "data_versions/published_v1/version_manifest.json"
AGGREGATOR_SCRIPT = REPOSITORY_ROOT / "scripts/13_aggregate_formal_results.py"
FRONTIER_ANCHORS = REPOSITORY_ROOT / "metadata/frontier_anchors.csv"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_aggregator():
    specification = importlib.util.spec_from_file_location(
        "formal_registry_integration_aggregator", AGGREGATOR_SCRIPT
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@cache
def _cached_contract(split: str, data_version: str) -> dict[str, object]:
    version_manifest = (
        REPOSITORY_ROOT / "data_versions" / data_version / "version_manifest.json"
    )
    return build_design_contract(
        design_path=DESIGN,
        manifest_path=STUDY_MANIFEST,
        experiment_config_path=EXPERIMENT_CONFIG,
        data_version=data_version,
        evaluation_split=split,
        data_version_manifest_path=version_manifest,
    )


def _contract(split: str, data_version: str = "published_v1") -> dict[str, object]:
    return json.loads(json.dumps(_cached_contract(split, data_version)))


@cache
def _data_version_input_identity(data_version: str) -> dict[str, object]:
    version_root = REPOSITORY_ROOT / "data_versions" / data_version
    identity = formal_registry.validate_data_version_inputs(
        data_version_manifest_path=version_root / "version_manifest.json",
        data_version=data_version,
        wide_path=version_root / "daily_wide.parquet",
        quality_path=version_root / "daily_long.parquet",
        require_manifest=True,
        require_quality=True,
    )
    assert identity is not None
    return identity


@pytest.fixture(autouse=True)
def _stable_repository_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep builder fixtures stable while sibling agents edit shared source files."""

    def stable_design_contract(**kwargs):
        return _contract(str(kwargs["evaluation_split"]), str(kwargs["data_version"]))

    def stable_roster_loader(path, **_kwargs):
        roster_path = Path(path)
        document = json.loads(roster_path.read_text(encoding="utf-8"))
        return SimpleNamespace(
            manifest_sha256=_sha256(roster_path),
            selected_models=tuple(document["selected_models"]),
            proposed_decision=document["proposed_decision"],
        )

    def stable_event_loader(path, **_kwargs):
        return pd.read_csv(path)

    def stable_authorization(value, *, expected_suite, expected_models, **_kwargs):
        document = json.loads(json.dumps(dict(value)))
        if document.get("schema_version") != "formal_execution_authorization_v1":
            raise ValueError("formal execution authorization schema is not frozen")
        if document.get("suite") != expected_suite:
            raise ValueError("formal execution authorization is bound to another suite")
        if document.get("expected_models") != list(expected_models):
            raise ValueError("runner models differ from finalized formal authorization")
        return document

    monkeypatch.setattr(
        formal_registry, "build_design_contract", stable_design_contract
    )
    monkeypatch.setattr(
        formal_registry, "_load_finalized_model_roster", stable_roster_loader
    )
    monkeypatch.setattr(
        formal_registry, "load_event_episode_catalog", stable_event_loader
    )
    monkeypatch.setattr(
        formal_registry, "event_catalog_sha256", lambda _catalog: "e" * 64
    )
    monkeypatch.setattr(
        formal_registry,
        "_validate_formal_execution_authorization",
        stable_authorization,
    )
    monkeypatch.setattr(
        formal_registry, "_require_builder_sources_tracked_clean", lambda: None
    )


def _write_roster(
    tmp_path: Path,
    *,
    selected_models: list[str] | None = None,
    decision: str | None = None,
) -> Path:
    selected = selected_models or ["linear", "proposed"]
    resolved_decision = decision or (
        "include_proposed_formally" if "proposed" in selected else "framework_only"
    )
    artifacts: dict[str, dict[str, str]] = {}
    for name in ("ranking", "stage2_selection", "go_no_go"):
        artifact = tmp_path / "validation" / f"{name}.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps({"artifact": name}), encoding="utf-8")
        artifacts[name] = {"path": str(artifact), "sha256": _sha256(artifact)}
    evidence = _contract("validation")
    roster = {
        "schema_version": "finalized_model_roster_v1",
        "finalized": True,
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
        "selected_models": selected,
        "best_traditional_model": "linear",
        "proposed_decision": resolved_decision,
        "validation_anchor_catalog": validation_anchor_catalog_identity(),
        "artifacts": artifacts,
        **{key: value for key, value in evidence.items() if key != "code_provenance"},
        "code_provenance": evidence["code_provenance"],
    }
    path = tmp_path / "validation/finalized_model_roster.json"
    path.write_text(json.dumps(roster), encoding="utf-8")
    return path


def _run_key(scenario: str, model: str, seed: int | None) -> str:
    return f"{scenario}|{model}:{'none' if seed is None else seed}"


def _write_formal_run(
    directory: Path,
    *,
    suite: str = "core",
    models: list[str] | None = None,
    contract: dict[str, object] | None = None,
    targets: dict[str, str] | None = None,
    structural_models: set[str] = frozenset(),
    event_catalog: bool | None = None,
    event_seed: int = 0,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    run_contract = json.loads(json.dumps(contract or _contract("development_test")))
    run_contract["code_provenance"].update(
        {
            "tracked_worktree_clean": True,
            "relevant_source_clean": True,
            "dirty_tracked_paths": [],
            "relevant_untracked_paths": [],
            "external_relevant_input_count": 0,
            "status": "clean",
        }
    )
    run_models = models or ["linear", "proposed"]
    model_targets = targets or {model: "T" for model in run_models}
    evidence_keys: list[str] = []
    structural_keys: list[str] = []
    daily_rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    checkpoint_keys: list[str] = []
    checkpoint_summaries: list[dict[str, object]] = []
    include_event_catalog = suite == "full" if event_catalog is None else event_catalog
    frontier = pd.read_csv(FRONTIER_ANCHORS)
    row_contract = {
        key: run_contract[key]
        for key in (
            "design_version",
            "design_hash",
            "data_version",
            "evaluation_split",
            "mask_schema_version",
            "model_schema_version",
            "statistics_schema_version",
        )
    }
    for position, model in enumerate(run_models):
        seed = (
            11
            if model
            in {
                "proposed",
                "information_compensation",
                "retrained_information_upper_bound",
            }
            else None
        )
        scenario_id = (
            f"{suite.upper()}-SCENARIO-{position}-DEVELOPMENT_TEST-R0101"
        )
        key = _run_key(scenario_id, model, seed)
        if model in structural_models:
            structural_keys.append(key)
            continue
        evidence_keys.append(key)
        target = model_targets[model]
        anchor = frontier.loc[
            frontier["station_id"].astype(str).eq("B1")
            & frontier["target"].astype(str).eq(target)
            & frontier["mask_seed"].astype(int).eq(101)
        ].iloc[0]
        shared = {
            **row_contract,
            "scenario_id": scenario_id,
            "model": model,
            "training_seed": seed,
            "mask_seed": 101,
            "station_id": "B1",
            "station_ids": json.dumps(["B1"]),
            "target": target,
            "experiment": "FORMAL",
            "mask_type": "block",
            "anchor_id": str(anchor["anchor_id"]),
            "anchor_target": str(anchor["target"]),
            "anchor_mask_seed": int(anchor["mask_seed"]),
            "center_date": str(anchor["center_date"]),
            "center_index": int(anchor["center_index"]),
            "anchor_data_version": str(anchor["data_version"]),
            "anchor_evaluation_split": str(anchor["evaluation_split"]),
            "anchor_source_split": str(anchor["source_split"]),
            "anchor_max_supported_length": int(anchor["max_supported_length"]),
            "anchor_start_month": int(anchor["start_month"]),
            "anchor_season": str(anchor["season"]),
            "anchor_year": int(anchor["year"]),
            "anchor_hydrologic_state": str(anchor["hydrologic_state"]),
            "evidence_role": "formal_development_evaluation",
            "formal_evidence": True,
        }
        for offset in range(2):
            daily_rows.append(
                {
                    **shared,
                    "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=offset),
                    "y_true": 10.0 + offset,
                    "y_pred": 10.1 + offset,
                }
            )
        event_rows.append({**shared, "MAE": 0.1, "RMSE": 0.12})
        if seed is not None:
            checkpoint_keys.append(key)
            checkpoint = directory / "checkpoints" / f"{model}.pt"
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            checkpoint.write_bytes(f"checkpoint:{model}".encode())
            checkpoint_summaries.append(
                {
                    "model": model,
                    "checkpoint_contract_valid": True,
                    "checkpoint": {
                        "path": str(checkpoint),
                        "size": checkpoint.stat().st_size,
                        "sha256": _sha256(checkpoint),
                    },
                    "checkpoint_sidecar": None,
                }
            )
    if include_event_catalog:
        for model in run_models:
            event_training_seeds = (
                (11, 22, 33, 44, 55)
                if model in {"brits_ref", "saits_ref", "csdi", "proposed"}
                else (None,)
            )
            for seed in event_training_seeds:
                for station_id in ("B1", "S2", "P3"):
                    for event_name in (
                        "HIGH_TEMPERATURE",
                        "RAPID_WARMING",
                        "FLOOD",
                        "LOW_FLOW",
                    ):
                        event_target = (
                            "T"
                            if event_name in {"HIGH_TEMPERATURE", "RAPID_WARMING"}
                            else "F"
                        )
                        scenario_id = (
                            f"M7A-STRESS-{station_id}-{event_name}-"
                            "DEVELOPMENT_TEST-R0000"
                        )
                        key = _run_key(scenario_id, model, seed)
                        if (
                            model in {"independent_flow", "rating_curve"}
                            and event_target != "F"
                        ):
                            structural_keys.append(key)
                            continue
                        evidence_keys.append(key)
                        shared = {
                            **row_contract,
                            "scenario_id": scenario_id,
                            "model": model,
                            "training_seed": seed,
                            "mask_seed": 0,
                            "station_id": station_id,
                            "station_ids": json.dumps([station_id]),
                            "target": event_target,
                            "experiment": "M7a",
                            "mask_type": "event",
                            "evidence_role": "formal_development_evaluation",
                            "formal_evidence": True,
                        }
                        for offset in range(2):
                            daily_rows.append(
                                {
                                    **shared,
                                    "date": pd.Timestamp("2024-02-01")
                                    + pd.Timedelta(days=offset),
                                    "y_true": 9.0 + offset,
                                    "y_pred": 9.1 + offset,
                                }
                            )
                        event_rows.append({**shared, "MAE": 0.1, "RMSE": 0.12})
                        if seed is not None:
                            checkpoint_keys.append(key)
        for position, model in enumerate(run_models):
            event_training_seeds = (
                (11, 22, 33, 44, 55)
                if model in {"brits_ref", "saits_ref", "csdi", "proposed"}
                else (None,)
            )
            target = model_targets[model]
            for seed in event_training_seeds:
                for catalog_role, identifier in (
                    ("EVENT", "E1"),
                    ("CONTROL", "C1"),
                ):
                    scenario_id = (
                        f"M7B-{catalog_role}-{identifier}-DEVELOPMENT_TEST-"
                        f"R{event_seed:04d}"
                    )
                    key = _run_key(scenario_id, model, seed)
                    evidence_keys.append(key)
                    shared = {
                        **row_contract,
                        "scenario_id": scenario_id,
                        "model": model,
                        "training_seed": seed,
                        "mask_seed": event_seed,
                        "station_id": "B1",
                        "station_ids": json.dumps(["B1"]),
                        "target": target,
                        "experiment": "M7b",
                        "mask_type": (
                            "event_episode"
                            if catalog_role == "EVENT"
                            else "event_control"
                        ),
                        "evidence_role": "formal_development_evaluation",
                        "formal_evidence": True,
                    }
                    for offset in range(2):
                        daily_rows.append(
                            {
                                **shared,
                                "date": pd.Timestamp("2024-02-01")
                                + pd.Timedelta(days=offset),
                                "y_true": 9.0 + offset,
                                "y_pred": 9.1 + offset,
                            }
                        )
                    event_rows.append({**shared, "MAE": 0.1, "RMSE": 0.12})
                    if seed is not None:
                        checkpoint_keys.append(key)
    daily = pd.DataFrame(daily_rows)
    events = pd.DataFrame(event_rows)
    daily.to_parquet(directory / "daily_predictions.parquet", index=False)
    events.to_parquet(directory / "event_metrics.parquet", index=False)
    expected_keys = [*evidence_keys, *structural_keys]
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
    roster_path = next(
        (
            ancestor / "validation/finalized_model_roster.json"
            for ancestor in (directory, *directory.parents)
            if (ancestor / "validation/finalized_model_roster.json").is_file()
        ),
        None,
    )
    if roster_path is None:
        raise AssertionError("formal fixture requires a finalized roster first")
    roster_document = json.loads(roster_path.read_text(encoding="utf-8"))
    roster_mirror = {
        "path": str(roster_path),
        "sha256": _sha256(roster_path),
        "selected_models": list(roster_document["selected_models"]),
        "proposed_decision": roster_document["proposed_decision"],
    }
    validation_contract = _contract("validation")
    authorization_roster = {
        **roster_mirror,
        "best_traditional_model": roster_document["best_traditional_model"],
        "selection_data_version": "published_v1",
        "selection_design_hash": validation_contract["design_hash"],
        "selection_contract": {
            key: value
            for key, value in validation_contract.items()
            if key != "code_provenance"
        },
        "selection_data_version_manifest": {
            "path": "data_versions/published_v1/version_manifest.json",
            "sha256": _sha256(VERSION_MANIFEST),
            "bytes": VERSION_MANIFEST.stat().st_size,
        },
        "validation_anchor_catalog": roster_document[
            "validation_anchor_catalog"
        ],
    }
    execution_models = (
        ["proposed"]
        if suite
        in {"science_compensation", "retrained_information_upper_bounds"}
        else run_models
    )
    formal_grid_contract = {
        "suite": suite,
        "frontier_anchor_required": True,
        "frontier_anchor_catalog_path": str(FRONTIER_ANCHORS),
        "frontier_anchor_catalog_sha256": _sha256(FRONTIER_ANCHORS),
        "frontier_anchor_count": len(frontier),
        "frontier_anchor_scenario_count": len(run_models),
        "frontier_anchor_bindings_sha256": "a" * 64,
        "event_uncertainty_required": suite == "full",
    }
    if include_event_catalog:
        formal_grid_contract.update(
            {
                "event_catalog_path": str(directory / "event_catalog.csv"),
                "event_catalog_sha256": "e" * 64,
                "event_catalog_episode_count": 1,
                "event_catalog_analysis_count": 1,
                "m7a_scenario_count": 12,
                "m7b_scenario_count": 2,
            }
        )
    manifest = {
        **run_contract,
        "data_version_input_identity": _data_version_input_identity(
            str(run_contract["data_version"])
        ),
        "suite": suite,
        "models": run_models,
        "expected_formal_models": run_models,
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
        "formal_grid_contract_complete": True,
        "formal_grid_contract": formal_grid_contract,
        "retryable_run_keys": [],
        "evidence_role": "formal_development_evaluation",
        "formal_evidence": True,
        **unit_fields,
        **counts,
        "completed_daily_rows": len(daily),
        "completed_event_rows": len(events),
        "training_checkpoints": checkpoint_summaries,
        "frontier_anchor_catalog_path": str(FRONTIER_ANCHORS),
        "frontier_anchor_catalog_sha256": _sha256(FRONTIER_ANCHORS),
        "frontier_anchor_count": len(frontier),
        "finalized_model_roster": roster_mirror,
        "formal_execution_authorization": {
            "schema_version": "formal_execution_authorization_v1",
            "suite": suite,
            "formal_evidence": True,
            "model_scope": (
                "authorized_proposed_estimand"
                if suite
                in {"science_compensation", "retrained_information_upper_bounds"}
                else "t_roster_plus_internal_structural_baselines"
            ),
            "target_scope": ["T", "F", "L"],
            "expected_models": execution_models,
            "finalized_model_roster": authorization_roster,
        },
    }
    if include_event_catalog:
        catalog_path = directory / "event_catalog.csv"
        pd.DataFrame(
            [
                {
                    "event_id": "E1",
                    "control_id": "C1",
                    "analysis_eligible": True,
                }
            ]
        ).to_csv(catalog_path, index=False)
        manifest.update(
            {
                "event_catalog_path": str(catalog_path),
                "event_catalog_sha256": "e" * 64,
                "event_catalog_episode_count": 1,
                "event_catalog_analysis_count": 1,
            }
        )
    path = directory / "run_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _write_primary_runs(
    tmp_path: Path,
    *,
    selected_models: list[str] | None = None,
    include_proposed_estimands: bool = True,
) -> list[Path]:
    selected = selected_models or ["linear", "proposed"]
    comparison_models = [*selected, "independent_flow", "rating_curve"]
    comparison_targets = {
        model: "F" if model in {"independent_flow", "rating_curve"} else "T"
        for model in comparison_models
    }
    manifests = [
        _write_formal_run(
            tmp_path / "formal/full",
            suite="full",
            models=comparison_models,
            targets=comparison_targets,
        ),
        _write_formal_run(
            tmp_path / "formal/dense",
            suite="science_dense",
            models=comparison_models,
            targets=comparison_targets,
        ),
        _write_formal_run(
            tmp_path / "formal/resilience",
            suite="science_resilience",
            models=selected,
        ),
    ]
    if include_proposed_estimands:
        manifests.extend(
            [
                _write_formal_run(
                    tmp_path / "formal/operational",
                    suite="science_compensation",
                    models=["information_compensation"],
                ),
                _write_formal_run(
                    tmp_path / "formal/retrained",
                    suite="retrained_information_upper_bounds",
                    models=["retrained_information_upper_bound"],
                ),
            ]
        )
    return manifests


def _write_sensitivity_runs(
    tmp_path: Path,
    *,
    data_version: str,
    selected_models: list[str] | None = None,
    include_operational: bool = True,
) -> tuple[list[Path], dict[str, object]]:
    selected = selected_models or ["linear", "proposed"]
    contract = _contract("development_test", data_version)
    manifests = [
        _write_formal_run(
            tmp_path / "formal/core",
            suite="core",
            models=selected,
            contract=contract,
        ),
        _write_formal_run(
            tmp_path / "formal/dense",
            suite="science_dense",
            models=selected,
            contract=contract,
        ),
    ]
    if include_operational:
        manifests.append(
            _write_formal_run(
                tmp_path / "formal/operational",
                suite="science_compensation",
                models=["information_compensation"],
                contract=contract,
            )
        )
    return manifests, contract


def _build(
    tmp_path: Path,
    manifests: list[Path],
    roster: Path,
    *,
    output_name: str = "suite_registry.json",
    contract: dict[str, object] | None = None,
) -> dict[str, object]:
    evidence = contract or _contract("development_test")
    target_version_manifest = (
        REPOSITORY_ROOT
        / "data_versions"
        / str(evidence["data_version"])
        / "version_manifest.json"
    )
    return build_formal_suite_registry(
        manifest_paths=manifests,
        finalized_model_roster_path=roster,
        formal_root=tmp_path / "formal",
        output_path=tmp_path / output_name,
        data_version=str(evidence["data_version"]),
        evaluation_split=str(evidence["evaluation_split"]),
        design_hash=str(evidence["design_hash"]),
        design_path=DESIGN,
        data_version_manifest_path=target_version_manifest,
        selection_data_version_manifest_path=VERSION_MANIFEST,
    )


def test_builds_immutable_hash_bound_primary_registry(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifests = _write_primary_runs(tmp_path)

    registry = _build(tmp_path, manifests, roster)

    output = tmp_path / "suite_registry.json"
    persisted = json.loads(output.read_text(encoding="utf-8"))
    hash_payload = dict(persisted)
    observed_hash = hash_payload.pop("registry_sha256")
    expected_hash = hashlib.sha256(
        json.dumps(
            hash_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert observed_hash == expected_hash == registry["registry_sha256"]
    assert registry["bundle_kind"] == "primary"
    assert registry["bundle_role"] == "primary"
    assert registry["required_suite_roles"] == [
        "core_full",
        "dense_frontier",
        "network_resilience",
        "event_uncertainty",
        "operational_dropout",
        "retrained_upper_bound",
    ]
    assert {role["status"] for role in registry["suite_roles"]} == {"complete"}
    assert {source["manifest"]["sha256"] for source in registry["sources"]} == {
        _sha256(manifest) for manifest in manifests
    }
    for source in registry["sources"]:
        run_directory = Path(source["run_directory"])
        for field, filename in (
            ("daily_predictions", "daily_predictions.parquet"),
            ("event_metrics", "event_metrics.parquet"),
        ):
            identity = source[field]
            artifact = run_directory / filename
            assert identity == {
                "path": str(artifact),
                "bytes": artifact.stat().st_size,
                "sha256": _sha256(artifact),
            }
    builder_identity = registry["registry_builder_identity"]
    assert builder_identity["schema_version"] == "formal_registry_builder_identity_v1"
    assert [source["path"] for source in builder_identity["sources"]] == [
        "scripts/21_build_formal_suite_registry.py",
        "src/stream_recoverability/analysis/formal_registry.py",
    ]
    for source in builder_identity["sources"]:
        path = REPOSITORY_ROOT / source["path"]
        assert source["bytes"] == path.stat().st_size
        assert source["sha256"] == _sha256(path)
    assert (
        formal_registry.validate_registry_builder_identity(builder_identity)
        == builder_identity
    )
    assert registry["frontier_anchor_catalog"] == {
        "path": "metadata/frontier_anchors.csv",
        "bytes": FRONTIER_ANCHORS.stat().st_size,
        "sha256": _sha256(FRONTIER_ANCHORS),
        "count": 180,
        "data_version": "published_v1",
        "evaluation_split": "development_test",
    }
    assert next(
        role for role in registry["suite_roles"] if role["role"] == "core_full"
    )["expected_models"] == [
        "linear",
        "proposed",
        "independent_flow",
        "rating_curve",
    ]

    with pytest.raises(FileExistsError, match="immutable"):
        _build(tmp_path, manifests, roster)


def test_groups_only_explicit_complete_model_children(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifests = _write_primary_runs(tmp_path)
    direct_dense = next(path for path in manifests if path.parent.name == "dense")
    manifests.remove(direct_dense)
    # This test uses a separate model-child parent to avoid mutating/removing the
    # already generated direct fixture.
    for model in ("linear", "proposed", "independent_flow", "rating_curve"):
        targets = {model: "F" if model in {"independent_flow", "rating_curve"} else "T"}
        manifests.append(
            _write_formal_run(
                tmp_path / f"formal/dense_children/{model}",
                suite="science_dense",
                models=[model],
                targets=targets,
            )
        )

    registry = _build(tmp_path, manifests, roster)

    dense = next(
        suite for suite in registry["suites"] if suite["name"] == "science_dense"
    )
    assert dense == {
        "name": "science_dense",
        "path": "dense_children",
        "layout": "model_children",
        "manifest_suite": "science_dense",
        "finalized": True,
        "finalized_models": [
            "independent_flow",
            "linear",
            "proposed",
            "rating_curve",
        ],
        "allowed_derived_models": [],
    }


def test_registry_is_consumable_by_formal_aggregator(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifests = _write_primary_runs(tmp_path)
    _build(tmp_path, manifests, roster)

    aggregator = _load_aggregator()
    aggregator.build_design_contract = lambda **_kwargs: _contract("development_test")
    aggregator.load_event_episode_catalog = lambda path, **_kwargs: pd.read_csv(path)
    aggregator.event_catalog_sha256 = lambda _catalog: "e" * 64
    aggregate = aggregator.aggregate_formal_results(
        tmp_path / "formal",
        tmp_path / "results",
        suite_registry=tmp_path / "suite_registry.json",
        design_path=DESIGN,
        manifest_path=STUDY_MANIFEST,
        config_path=EXPERIMENT_CONFIG,
        data_version="published_v1",
        evaluation_split="development_test",
        data_version_manifest_path=VERSION_MANIFEST,
    )

    assert aggregate["complete"] is True
    assert aggregate["suite_count"] == 5
    assert aggregate["source_run_count"] == len(manifests)


def test_rejects_unlisted_model_child_directory(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    first = _write_formal_run(
        tmp_path / "formal/dense/linear", suite="dense", models=["linear"]
    )
    second = _write_formal_run(
        tmp_path / "formal/dense/proposed", suite="dense", models=["proposed"]
    )
    (tmp_path / "formal/dense/stale").mkdir()

    with pytest.raises(ValueError, match="unlisted model child"):
        _build(tmp_path, [first, second], roster)


def test_accepts_fixed_f_only_structural_baseline(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path, selected_models=["linear"])
    manifests = _write_primary_runs(
        tmp_path,
        selected_models=["linear"],
        include_proposed_estimands=False,
    )

    registry = _build(tmp_path, manifests, roster)

    core_role = next(
        role for role in registry["suite_roles"] if role["role"] == "core_full"
    )
    assert core_role["expected_models"] == [
        "linear",
        "independent_flow",
        "rating_curve",
    ]


def test_rejects_non_f_evidence_for_structural_baseline(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path, selected_models=["linear"])
    manifest = _write_formal_run(
        tmp_path / "formal/core",
        models=["linear", "rating_curve"],
        targets={"linear": "T", "rating_curve": "T"},
    )

    with pytest.raises(ValueError, match="F-only semantics"):
        _build(tmp_path, [manifest], roster)


@pytest.mark.parametrize("model", ["brits", "saits"])
def test_rejects_legacy_model_names(tmp_path: Path, model: str) -> None:
    roster = _write_roster(tmp_path, selected_models=["linear", model])
    manifest = _write_formal_run(tmp_path / "formal/core", models=[model])

    with pytest.raises(ValueError, match="legacy brits/saits"):
        _build(tmp_path, [manifest], roster)


@pytest.mark.parametrize(
    ("suite", "model"),
    [
        ("science_compensation", "information_compensation"),
        ("retrained_information_upper_bounds", "retrained_information_upper_bound"),
    ],
)
def test_framework_only_rejects_completed_proposed_estimands(
    tmp_path: Path, suite: str, model: str
) -> None:
    roster = _write_roster(
        tmp_path, selected_models=["linear"], decision="framework_only"
    )
    manifest = _write_formal_run(
        tmp_path / f"formal/{suite}", suite=suite, models=[model]
    )

    with pytest.raises(ValueError, match="not_applicable"):
        _build(tmp_path, [manifest], roster)


def test_framework_only_records_not_applicable_suites(tmp_path: Path) -> None:
    roster = _write_roster(
        tmp_path, selected_models=["linear"], decision="framework_only"
    )
    manifests = _write_primary_runs(
        tmp_path,
        selected_models=["linear"],
        include_proposed_estimands=False,
    )

    registry = _build(tmp_path, manifests, roster)

    assert {item["manifest_suite"] for item in registry["not_applicable_suites"]} == {
        "science_compensation",
        "retrained_information_upper_bounds",
    }
    assert all(
        item["status"] == "not_applicable" for item in registry["not_applicable_suites"]
    )
    role_status = {item["role"]: item["status"] for item in registry["suite_roles"]}
    assert role_status["operational_dropout"] == "not_applicable"
    assert role_status["retrained_upper_bound"] == "not_applicable"


def test_include_proposed_authorizes_only_bound_derived_suite(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifests = _write_primary_runs(tmp_path)

    registry = _build(tmp_path, manifests, roster)

    operational = next(
        suite for suite in registry["suites"] if suite["name"] == "science_compensation"
    )
    assert operational["finalized_models"] == ["information_compensation"]


def test_rejects_mixed_code_identity(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    first_contract = _contract("development_test")
    second_contract = json.loads(json.dumps(first_contract))
    second_contract["code_identity"]["sha256"] = "f" * 64
    first = _write_formal_run(
        tmp_path / "formal/core",
        suite="core",
        models=["linear"],
        contract=first_contract,
    )
    second = _write_formal_run(
        tmp_path / "formal/events",
        suite="events",
        models=["linear"],
        contract=second_contract,
    )

    with pytest.raises(ValueError, match="code provenance/identity is inconsistent"):
        _build(tmp_path, [first, second], roster, contract=first_contract)


def test_rejects_target_contract_mismatch(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    contract = _contract("development_test")
    manifest = _write_formal_run(tmp_path / "formal/core", contract=contract)

    with pytest.raises(ValueError, match="design_hash"):
        build_formal_suite_registry(
            manifest_paths=[manifest],
            finalized_model_roster_path=roster,
            formal_root=tmp_path / "formal",
            output_path=tmp_path / "registry.json",
            data_version="published_v1",
            evaluation_split="development_test",
            design_hash="0" * 64,
            design_path=DESIGN,
            selection_data_version_manifest_path=VERSION_MANIFEST,
        )


def test_primary_registry_rejects_missing_required_role(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    models = ["linear", "proposed", "independent_flow", "rating_curve"]
    manifest = _write_formal_run(
        tmp_path / "formal/full",
        suite="full",
        models=models,
        targets={
            model: "F" if model in {"independent_flow", "rating_curve"} else "T"
            for model in models
        },
    )

    with pytest.raises(ValueError, match="missing required role dense_frontier"):
        _build(tmp_path, [manifest], roster)


def test_primary_registry_rejects_role_model_subset(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifests = _write_primary_runs(tmp_path)
    dense = next(path for path in manifests if path.parent.name == "dense")
    manifests.remove(dense)
    manifests.append(
        _write_formal_run(
            tmp_path / "formal/dense_subset",
            suite="science_dense",
            models=["linear", "proposed"],
        )
    )

    with pytest.raises(ValueError, match="dense_frontier model roster differs"):
        _build(tmp_path, manifests, roster)


def test_full_cannot_claim_event_role_without_catalog(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifests = _write_primary_runs(tmp_path)
    full = next(path for path in manifests if path.parent.name == "full")
    document = json.loads(full.read_text(encoding="utf-8"))
    document["event_catalog_path"] = None
    full.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="requires event_catalog_path"):
        _build(tmp_path, manifests, roster)


def test_full_event_role_rejects_nonzero_m7b_seed(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifests = _write_primary_runs(tmp_path)
    full = next(path for path in manifests if path.parent.name == "full")
    manifests.remove(full)
    models = ["linear", "proposed", "independent_flow", "rating_curve"]
    manifests.append(
        _write_formal_run(
            tmp_path / "formal/full_bad_seed",
            suite="full",
            models=models,
            targets={
                model: ("F" if model in {"independent_flow", "rating_curve"} else "T")
                for model in models
            },
            event_seed=1,
        )
    )

    with pytest.raises(ValueError, match="seed-0 scenarios per eligible pair"):
        _build(tmp_path, manifests, roster)


def test_full_event_role_rejects_catalog_count_mismatch(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifests = _write_primary_runs(tmp_path)
    full = next(path for path in manifests if path.parent.name == "full")
    document = json.loads(full.read_text(encoding="utf-8"))
    document["event_catalog_analysis_count"] = 2
    full.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="counts differ"):
        _build(tmp_path, manifests, roster)


def test_full_event_role_rejects_mixed_experiment_labels(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifests = _write_primary_runs(tmp_path)
    full = next(path for path in manifests if path.parent.name == "full")
    daily_path = full.parent / "daily_predictions.parquet"
    daily = pd.read_parquet(daily_path)
    row = daily["scenario_id"].astype(str).str.startswith("M7A-")
    daily.loc[daily.index[row][0], "experiment"] = "M1"
    daily.to_parquet(daily_path, index=False)

    with pytest.raises(ValueError, match="mixes event experiment labels"):
        _build(tmp_path, manifests, roster)


def test_full_event_role_rejects_wrong_m7a_target(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifests = _write_primary_runs(tmp_path)
    full = next(path for path in manifests if path.parent.name == "full")
    event_path = full.parent / "event_metrics.parquet"
    events = pd.read_parquet(event_path)
    row = events["scenario_id"].astype(str).str.contains("HIGH_TEMPERATURE")
    events.loc[events.index[row][0], "target"] = "F"
    events.to_parquet(event_path, index=False)

    with pytest.raises(ValueError, match="targets differ from the frozen event design"):
        _build(tmp_path, manifests, roster)


def test_sensitivity_registry_is_independent_compact_bundle(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifests, sensitivity = _write_sensitivity_runs(
        tmp_path, data_version="no_s2_suspect_v1"
    )

    registry = _build(tmp_path, manifests, roster, contract=sensitivity)

    assert registry["bundle_kind"] == "sensitivity"
    assert registry["bundle_role"] == "sensitivity_compact"
    assert registry["required_suite_roles"] == [
        "sensitivity_core_T",
        "sensitivity_dense_frontier",
        "sensitivity_operational_dropout",
    ]
    assert {role["status"] for role in registry["suite_roles"]} == {"complete"}
    assert registry["data_version"] == "no_s2_suspect_v1"


def test_sensitivity_registry_rejects_noncompact_suite(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    sensitivity = _contract("development_test", "b1_shift_sensitivity_v1")
    models = ["linear", "proposed"]
    manifest = _write_formal_run(
        tmp_path / "formal/resilience",
        suite="science_resilience",
        models=models,
        contract=sensitivity,
    )

    with pytest.raises(ValueError, match="unsupported suite"):
        _build(tmp_path, [manifest], roster, contract=sensitivity)


def test_sensitivity_core_alone_cannot_claim_complete_bundle(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    sensitivity = _contract("development_test", "b1_no_level_v1")
    manifest = _write_formal_run(
        tmp_path / "formal/core",
        suite="core",
        models=["linear", "proposed"],
        contract=sensitivity,
    )

    with pytest.raises(
        ValueError, match="missing required role sensitivity_dense_frontier"
    ):
        _build(tmp_path, [manifest], roster, contract=sensitivity)


def test_framework_only_sensitivity_marks_operational_not_applicable(
    tmp_path: Path,
) -> None:
    roster = _write_roster(
        tmp_path, selected_models=["linear"], decision="framework_only"
    )
    manifests, sensitivity = _write_sensitivity_runs(
        tmp_path,
        data_version="no_s2_suspect_v1",
        selected_models=["linear"],
        include_operational=False,
    )

    registry = _build(tmp_path, manifests, roster, contract=sensitivity)

    operational = next(
        role
        for role in registry["suite_roles"]
        if role["role"] == "sensitivity_operational_dropout"
    )
    assert operational["status"] == "not_applicable"
    assert operational["reason"] == "proposed_decision=framework_only"
    assert registry["not_applicable_suites"] == [
        {
            "manifest_suite": "science_compensation",
            "status": "not_applicable",
            "reason": "proposed_decision=framework_only",
        }
    ]


def test_rejects_data_version_outside_frozen_inventory() -> None:
    with pytest.raises(ValueError, match="not a frozen primary/sensitivity version"):
        formal_registry._data_version_bundle_kind(DESIGN, "ad_hoc_v1")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.__setitem__("training_profile", "smoke"), "smoke"),
        (
            lambda value: value.__setitem__("formal_design_complete", False),
            "requires formal_design_complete",
        ),
        (
            lambda value: value.__setitem__("retryable_run_keys", ["x"]),
            "retryable_run_keys",
        ),
    ],
)
def test_rejects_nonformal_or_incomplete_manifest(
    tmp_path: Path, mutation, message: str
) -> None:
    roster = _write_roster(tmp_path)
    manifest = _write_formal_run(tmp_path / "formal/core")
    value = json.loads(manifest.read_text(encoding="utf-8"))
    mutation(value)
    manifest.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        _build(tmp_path, [manifest], roster)


def test_rejects_dirty_manifest_code_provenance(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifest = _write_formal_run(tmp_path / "formal/core", suite="core")
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["code_provenance"]["relevant_source_clean"] = False
    document["code_provenance"]["status"] = "dirty"
    manifest.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="clean relevant source"):
        _build(tmp_path, [manifest], roster)


def test_rejects_table_without_formal_evidence_role(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifest = _write_formal_run(tmp_path / "formal/core", suite="core")
    daily_path = manifest.parent / "daily_predictions.parquet"
    daily = pd.read_parquet(daily_path)
    daily["formal_evidence"] = False
    daily.to_parquet(daily_path, index=False)

    with pytest.raises(ValueError, match="formal_evidence=true"):
        _build(tmp_path, [manifest], roster)


def test_rejects_validation_or_confirmatory_registry_target(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifest = _write_formal_run(tmp_path / "formal/core")
    evidence = _contract("development_test")

    with pytest.raises(ValueError, match="reject validation/confirmatory"):
        build_formal_suite_registry(
            manifest_paths=[manifest],
            finalized_model_roster_path=roster,
            formal_root=tmp_path / "formal",
            output_path=tmp_path / "registry.json",
            data_version="published_v1",
            evaluation_split="validation",
            design_hash=str(evidence["design_hash"]),
            design_path=DESIGN,
            selection_data_version_manifest_path=VERSION_MANIFEST,
        )


def test_rejects_duplicate_manifest_argument(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifest = _write_formal_run(tmp_path / "formal/core")

    with pytest.raises(ValueError, match="listed more than once"):
        _build(tmp_path, [manifest, manifest], roster)


def test_registry_builder_identity_rejects_source_hash_tampering(
    tmp_path: Path,
) -> None:
    roster = _write_roster(tmp_path)
    manifests = _write_primary_runs(tmp_path)
    registry = _build(tmp_path, manifests, roster)
    identity = json.loads(json.dumps(registry["registry_builder_identity"]))
    identity["sources"][0]["sha256"] = "0" * 64
    unsigned = {
        key: value for key, value in identity.items() if key != "identity_sha256"
    }
    identity["identity_sha256"] = formal_registry._canonical_sha256(unsigned)

    with pytest.raises(ValueError, match="current source bytes/SHA-256"):
        formal_registry.validate_registry_builder_identity(identity)


def test_registry_generation_requires_tracked_clean_builder_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roster = _write_roster(tmp_path)
    manifests = _write_primary_runs(tmp_path)

    def reject_dirty() -> None:
        raise ValueError("registry builder sources must be tracked and clean")

    monkeypatch.setattr(
        formal_registry, "_require_builder_sources_tracked_clean", reject_dirty
    )
    with pytest.raises(ValueError, match="tracked and clean"):
        _build(tmp_path, manifests, roster)


def test_rejects_missing_frontier_anchor_catalog_path(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifests = _write_primary_runs(tmp_path)
    manifest = manifests[0]
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["frontier_anchor_catalog_path"] = None
    manifest.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="requires frontier_anchor_catalog_path"):
        _build(tmp_path, manifests, roster)


def test_rejects_tampered_frontier_anchor_table_binding(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifests = _write_primary_runs(tmp_path)
    manifest = manifests[0]
    daily_path = manifest.parent / "daily_predictions.parquet"
    daily = pd.read_parquet(daily_path)
    anchored = daily["mask_type"].astype(str).isin(
        formal_registry.FRONTIER_ANCHORED_MASK_TYPES
    )
    daily.loc[anchored, "anchor_id"] = "ANCHOR-TAMPERED"
    daily.to_parquet(daily_path, index=False)

    with pytest.raises(ValueError, match="unknown frontier anchor"):
        _build(tmp_path, manifests, roster)


def test_rejects_formal_execution_authorization_roster_tampering(
    tmp_path: Path,
) -> None:
    roster = _write_roster(tmp_path)
    manifests = _write_primary_runs(tmp_path)
    manifest = manifests[0]
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["formal_execution_authorization"]["finalized_model_roster"][
        "sha256"
    ] = "0" * 64
    manifest.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="bound to another finalized roster"):
        _build(tmp_path, manifests, roster)


def test_rejects_data_version_input_identity_tampering(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifests = _write_primary_runs(tmp_path)
    manifest = manifests[0]
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["data_version_input_identity"]["artifacts"]["daily_wide.parquet"][
        "sha256"
    ] = "0" * 64
    manifest.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="data-version input identity is stale"):
        _build(tmp_path, manifests, roster)


def test_full_event_role_rejects_extra_m7_scenario(tmp_path: Path) -> None:
    roster = _write_roster(tmp_path)
    manifests = _write_primary_runs(tmp_path)
    full = next(path for path in manifests if path.parent.name == "full")
    document = json.loads(full.read_text(encoding="utf-8"))
    old_scenario = next(
        key.split("|", maxsplit=1)[0]
        for key in document["expected_run_unit_keys"]
        if key.startswith("FULL-SCENARIO-0-")
    )
    new_scenario = "M7B-EXTRA-DEVELOPMENT_TEST-R0101"
    for field in formal_registry.RUN_UNIT_FIELDS:
        document[field] = [
            value.replace(f"{old_scenario}|", f"{new_scenario}|")
            for value in document[field]
        ]
    full.write_text(json.dumps(document), encoding="utf-8")
    for table_name in ("daily_predictions.parquet", "event_metrics.parquet"):
        table_path = full.parent / table_name
        table = pd.read_parquet(table_path)
        table.loc[table["scenario_id"].eq(old_scenario), "scenario_id"] = new_scenario
        table.to_parquet(table_path, index=False)

    with pytest.raises(ValueError, match="full event inventory"):
        _build(tmp_path, manifests, roster)
