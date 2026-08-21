from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.experiments import validation_finalization as finalization
from stream_recoverability.experiments.contracts import build_design_contract
from stream_recoverability.data.confirmatory import (
    FINALIZED_MODEL_ROSTER_SCHEMA_VERSION,
    load_finalized_model_roster,
)
from stream_recoverability.experiments.validation import (
    DEEP_CANDIDATES,
    TRADITIONAL_CANDIDATES,
    VALIDATION_DEEP_SEEDS,
    VALIDATION_MASK_SEEDS,
    VALIDATION_STATIONS,
    build_validation_funnel,
    canonical_validation_anchor_path,
    validation_anchor_catalog_identity,
)


def _contract() -> dict[str, Any]:
    digest = "a" * 64
    return {
        "design_version": "design_freeze_v1",
        "design_hash": "d" * 64,
        "data_version": "published_v1",
        "evaluation_split": "validation",
        "mask_schema_version": "mask_schema_v2",
        "model_schema_version": "model_schema_v2",
        "statistics_schema_version": "statistics_schema_v2",
        "input_digests": {
            "design_freeze": "1" * 64,
            "study_manifest": "2" * 64,
            "experiment_config": "3" * 64,
            "data_version_manifest": "4" * 64,
        },
        "code_identity": {
            "schema_version": "code_provenance_v1",
            "relevant_source_digest": digest,
            "relevant_source_file_count": 10,
        },
        "code_provenance": {
            "schema_version": "code_provenance_v1",
            "git_commit": "b" * 40,
            "tracked_worktree_clean": True,
            "relevant_source_clean": True,
            "relevant_source_digest": digest,
            "relevant_source_file_count": 10,
            "dirty_tracked_paths": [],
            "relevant_untracked_paths": [],
            "external_relevant_input_count": 0,
            "status": "clean",
        },
    }


def _identity(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "size": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def test_validation_mask_registry_serializes_nested_evidence_contract(
    tmp_path: Path,
) -> None:
    cli = runpy.run_path("scripts/15_run_validation_funnel.py")
    contract = _contract()

    cli["_write_funnel_registry"](build_validation_funnel(), contract, tmp_path)

    units = pd.read_csv(tmp_path / "validation_mask_units.csv")
    assert units["code_identity"].notna().all()
    assert units["code_provenance"].notna().all()
    assert units["input_digests"].notna().all()
    assert json.loads(units.loc[0, "code_identity"]) == contract["code_identity"]
    assert json.loads(units.loc[0, "code_provenance"]) == contract["code_provenance"]
    assert json.loads(units.loc[0, "input_digests"]) == contract["input_digests"]


def test_initial_ranking_uses_only_stage1_and_seed11_stage2_inputs(
    tmp_path: Path,
) -> None:
    cli = runpy.run_path("scripts/15_run_validation_funnel.py")
    run_root = tmp_path / "validation"
    assert cli["_initial_ranking_paths"](run_root) == (
        run_root / "traditional/event_metrics.parquet",
        run_root / "deep_single_seed/event_metrics.parquet",
    )
    events = pd.DataFrame(
        {
            "model": [*TRADITIONAL_CANDIDATES, *DEEP_CANDIDATES],
            "training_seed": [
                *([np.nan] * len(TRADITIONAL_CANDIDATES)),
                *([11] * len(DEEP_CANDIDATES)),
            ],
        }
    )
    cli["_validate_initial_ranking_inventory"](events)
    contaminated = pd.concat(
        [events, events.loc[events["model"].eq("proposed")].assign(training_seed=22)],
        ignore_index=True,
    )
    with pytest.raises(ValueError, match="seed 22/33"):
        cli["_validate_initial_ranking_inventory"](contaminated)


def _scenario_parts(scenario_id: str) -> tuple[str, str, int]:
    rest, raw_seed = scenario_id.rsplit("-R", maxsplit=1)
    if rest.endswith("-VALIDATION"):
        rest = rest[: -len("-VALIDATION")]
    station = rest.split("-")[2]
    return rest, station, int(raw_seed)


def _write_completed_stage(
    root: Path,
    *,
    models: tuple[str, ...] = DEEP_CANDIDATES,
    seeds: tuple[int, ...] = (11,),
    stage_name: str = "deep_single_seed",
) -> Path:
    contract = _contract()
    root.mkdir(parents=True)
    checkpoints: dict[tuple[str, int], dict[str, Any]] = {}
    summaries: list[dict[str, Any]] = []
    for model in models:
        for seed in seeds:
            checkpoint = root / "checkpoints" / f"{model}-S{seed}-W365-formal.pt"
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            checkpoint.write_bytes(f"{model}/{seed}".encode())
            identity = _identity(checkpoint)
            sidecar_identity = None
            if model in {"brits_ref", "saits_ref", "csdi"}:
                sidecar = Path(str(checkpoint) + ".sha256")
                sidecar.write_text(identity["sha256"] + "\n", encoding="ascii")
                sidecar_identity = _identity(sidecar)
            checkpoints[(model, seed)] = identity
            summaries.append(
                {
                    "model": model,
                    "training_seed": seed,
                    "best_epoch": 2,
                    "epochs_run": 4,
                    "hit_epoch_limit": False,
                    "checkpoint": identity,
                    "checkpoint_sidecar": sidecar_identity,
                    "checkpoint_contract_valid": True,
                }
            )

    scenario_ids = sorted(finalization._expected_scenario_ids())
    run_keys = {f"{model}:{seed}" for model in models for seed in seeds}
    units = {
        f"{scenario_id}|{run_key}"
        for scenario_id in scenario_ids
        for run_key in run_keys
    }
    event_rows: list[dict[str, Any]] = []
    for scenario_id in scenario_ids:
        condition_id, station, mask_seed = _scenario_parts(scenario_id)
        run_contracts = {}
        for model in models:
            for seed in seeds:
                run_key = f"{model}:{seed}"
                run_contracts[run_key] = {
                    **finalization._canonical_contract(contract),
                    "model": model,
                    "training_seed": seed,
                    "checkpoint": checkpoints[(model, seed)],
                }
                event_rows.append(
                    {
                        "scenario_id": scenario_id,
                        "condition_id": condition_id,
                        "model": model,
                        "training_seed": seed,
                        "mask_seed": mask_seed,
                        "station_id": station,
                        "target": "T",
                        "MAE": 1.0,
                        "RMSE": 1.1,
                        "skill": 0.2,
                        "coverage_90": 0.9,
                        "finite_predictions": True,
                        "finite_validation_score": True,
                        "best_epoch": 2,
                        "epochs_run": 4,
                        "hit_epoch_limit": False,
                        "evaluation_split": "validation",
                        "evidence_role": "model_selection_only",
                        "data_version": contract["data_version"],
                        "design_hash": contract["design_hash"],
                    }
                )
        status_path = root / "scenarios" / scenario_id / "status.json"
        status_path.parent.mkdir(parents=True)
        status_path.write_text(
            json.dumps(
                {
                    "scenario_id": scenario_id,
                    "status": "complete",
                    "completed_runs": sorted(run_keys),
                    "retryable_run_keys": [],
                    "run_contracts": run_contracts,
                    **finalization._canonical_contract(contract),
                }
            ),
            encoding="utf-8",
        )
    events = pd.DataFrame(event_rows)
    events.to_parquet(root / "event_metrics.parquet", index=False)
    stage_manifest = {
        "stage": stage_name,
        "models": list(models),
        "training_seeds": list(seeds),
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
        **contract,
    }
    (root / "validation_stage_manifest.json").write_text(
        json.dumps(stage_manifest), encoding="utf-8"
    )
    run_manifest = {
        "models": list(models),
        "training_seeds": list(seeds),
        "grid_scenario_count": 105,
        "selected_scenarios": 105,
        "run_unit_complete": True,
        "evidence_complete": True,
        "finite_predictions": True,
        "finite_event_metrics": True,
        "checkpoint_contract_complete": True,
        "expected_run_unit_keys": sorted(units),
        "completed_run_unit_keys": sorted(units),
        "expected_evidence_run_unit_keys": sorted(units),
        "completed_evidence_run_unit_keys": sorted(units),
        "finite_prediction_run_unit_keys": sorted(units),
        "finite_event_metric_run_unit_keys": sorted(units),
        "checkpoint_required_run_unit_keys": sorted(units),
        "checkpoint_valid_run_unit_keys": sorted(units),
        "retryable_run_unit_keys": [],
        "training_checkpoints": summaries,
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        **contract,
    }
    (root / "run_manifest.json").write_text(json.dumps(run_manifest), encoding="utf-8")
    return root


def test_extract_diagnostics_is_derived_from_complete_units_and_checkpoints(
    tmp_path: Path,
) -> None:
    stage = _write_completed_stage(tmp_path / "deep_single_seed")
    diagnostics = finalization.extract_stage2_diagnostics(
        stage, expected_contract=_contract()
    )

    assert tuple(diagnostics["model"]) == DEEP_CANDIDATES
    assert set(diagnostics["training_seed"]) == {11}
    assert set(diagnostics["event_rows"]) == {105}
    assert diagnostics["finite_predictions"].all()
    assert diagnostics["finite_validation_score"].all()
    assert diagnostics["checkpoint_sha256"].str.len().eq(64).all()
    assert set(diagnostics["evaluation_split"]) == {"validation"}
    assert not diagnostics["formal_evidence"].any()

    proposed = Path(diagnostics.set_index("model").loc["proposed", "checkpoint_path"])
    proposed.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA-256"):
        finalization.extract_stage2_diagnostics(stage, expected_contract=_contract())


def _write_ranking_artifact(tmp_path: Path, deep_events_path: Path) -> Path:
    contract = _contract()
    rows: list[dict[str, Any]] = []
    for scenario_id in sorted(finalization._expected_scenario_ids()):
        condition_id, station, mask_seed = _scenario_parts(scenario_id)
        for model_index, model in enumerate(TRADITIONAL_CANDIDATES):
            rows.append(
                {
                    "condition_id": condition_id,
                    "scenario_id": scenario_id,
                    "model": model,
                    "training_seed": np.nan,
                    "mask_seed": mask_seed,
                    "station_id": station,
                    "target": "T",
                    "skill": 0.10 + model_index / 100,
                    "evaluation_split": "validation",
                    "evidence_role": "model_selection_only",
                    "data_version": contract["data_version"],
                    "design_hash": contract["design_hash"],
                }
            )
    traditional_path = tmp_path / "traditional_events.parquet"
    pd.DataFrame(rows).to_parquet(traditional_path, index=False)
    deep = pd.read_parquet(deep_events_path)
    combined = pd.concat([pd.DataFrame(rows), deep], ignore_index=True, sort=False)
    ranking = finalization.rank_validation_models(
        combined,
        expected_data_version=contract["data_version"],
        expected_design_hash=contract["design_hash"],
    )
    ranking_path = tmp_path / "validation_model_ranking.csv"
    ranking.to_csv(ranking_path, index=False)
    manifest = {
        "schema_version": finalization.RANKING_MANIFEST_SCHEMA_VERSION,
        "event_metrics": [
            _identity(traditional_path),
            _identity(deep_events_path),
        ],
        "output": _identity(ranking_path),
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
        **contract,
    }
    ranking_path.with_suffix(".manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return ranking_path


def test_ranking_and_stage2_selection_are_recomputed_from_bound_artifacts(
    tmp_path: Path,
) -> None:
    stage = _write_completed_stage(tmp_path / "deep_single_seed")
    ranking_path = _write_ranking_artifact(tmp_path, stage / "event_metrics.parquet")
    ranking, _ = finalization.validate_ranking_artifact(
        ranking_path, expected_contract=_contract()
    )
    assert set(ranking["model"]) == set(TRADITIONAL_CANDIDATES) | set(DEEP_CANDIDATES)

    diagnostics_path = tmp_path / "stage2_diagnostics.csv"
    finalization.write_stage2_diagnostics(
        stage, diagnostics_path, expected_contract=_contract()
    )
    diagnostics = pd.read_csv(diagnostics_path)
    selected = finalization.select_stage2_finalists(
        ranking,
        diagnostics=diagnostics,
        **finalization._selection_settings("configs/design_freeze_v1.yaml"),
    )
    selected["data_version"] = _contract()["data_version"]
    selected["design_hash"] = _contract()["design_hash"]
    selection_path = tmp_path / "stage2_finalist_selection.csv"
    selected.to_csv(selection_path, index=False)
    finalists = selected.loc[selected["selected_for_stability"], "model"].tolist()
    selection_manifest = {
        "schema_version": finalization.STAGE2_SELECTION_MANIFEST_SCHEMA_VERSION,
        "selected_models": finalists,
        "ranking": _identity(ranking_path),
        "diagnostics": _identity(diagnostics_path),
        "output": _identity(selection_path),
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
        **_contract(),
    }
    selection_path.with_suffix(".manifest.json").write_text(
        json.dumps(selection_manifest), encoding="utf-8"
    )
    validated, validated_finalists, _ = finalization.validate_stage2_selection_artifact(
        selection_path,
        ranking=ranking,
        ranking_path=ranking_path,
        design_path="configs/design_freeze_v1.yaml",
        expected_contract=_contract(),
    )
    assert tuple(validated["model"]) == tuple(selected["model"])
    assert validated_finalists == tuple(finalists)

    tampered = ranking.copy()
    tampered.loc[0, "mean_skill_across_strata"] += 0.01
    tampered.to_csv(ranking_path, index=False)
    ranking_manifest_path = ranking_path.with_suffix(".manifest.json")
    ranking_manifest = json.loads(ranking_manifest_path.read_text())
    ranking_manifest["output"] = _identity(ranking_path)
    ranking_manifest_path.write_text(json.dumps(ranking_manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="deterministic recomputation"):
        finalization.validate_ranking_artifact(
            ranking_path, expected_contract=_contract()
        )


def test_branch_predictor_requires_same_checkpoint_s0_and_all_16_combinations() -> None:
    bundle = {
        label: {
            name: np.ones((2, 3), dtype=float)
            for name in ("q05", "q25", "q50", "q75", "q95")
        }
        for label in finalization.ALL_INFORMATION_COMBINATIONS
        if label != "S0"
    }
    with pytest.raises(ValueError, match="including empty enabled_groups as S0"):
        finalization._validate_prediction_bundle(bundle, time_count=2, station_count=3)

    bundle["S0"] = {
        name: np.ones((2, 3), dtype=float)
        for name in ("q05", "q25", "q50", "q75", "q95")
    }
    validated = finalization._validate_prediction_bundle(
        bundle, time_count=2, station_count=3
    )
    assert set(validated) == set(finalization.ALL_INFORMATION_COMBINATIONS)


def _write_branch_artifact(root: Path) -> Path:
    contract = _contract()
    root.mkdir(parents=True)
    checkpoints = {}
    for seed in VALIDATION_DEEP_SEEDS:
        checkpoint = root / f"proposed-S{seed}.pt"
        checkpoint.write_bytes(str(seed).encode())
        checkpoints[str(seed)] = _identity(checkpoint)
    events: list[dict[str, Any]] = []
    daily: list[dict[str, Any]] = []
    mask_inventory: dict[str, dict[str, Any]] = {}
    for seed in VALIDATION_DEEP_SEEDS:
        for station in VALIDATION_STATIONS:
            for mask_seed in VALIDATION_MASK_SEEDS:
                for gap in finalization.BRANCH_ABLATION_GAPS:
                    scenario_id = f"VAL-BLK1-{station}-T-D{gap:03d}-R{mask_seed:04d}"
                    score_hash = finalization._score_cells_sha256(
                        ["2017-01-01"], station, np.asarray([1.0])
                    )
                    if scenario_id not in mask_inventory:
                        mask = root / "masks" / f"{scenario_id}.npz"
                        metadata = root / "masks" / f"{scenario_id}.json"
                        mask.parent.mkdir(exist_ok=True)
                        mask.write_bytes(scenario_id.encode())
                        metadata.write_text(
                            json.dumps({"scenario_id": scenario_id}), encoding="utf-8"
                        )
                        mask_inventory[scenario_id] = {
                            "scenario_id": scenario_id,
                            "condition_id": scenario_id.rsplit("-R", 1)[0],
                            "station_id": station,
                            "gap_length": gap,
                            "mask_seed": mask_seed,
                            "anchor_id": f"A-{station}-{mask_seed}",
                            "score_cells_sha256": score_hash,
                            "score_cell_count": 1,
                            "mask": _identity(mask),
                            "mask_metadata": _identity(metadata),
                        }
                    for index, combination in enumerate(
                        finalization.BRANCH_ABLATION_COMBINATIONS
                    ):
                        common = {
                            "scenario_id": scenario_id,
                            "condition_id": scenario_id.rsplit("-R", 1)[0],
                            "station_id": station,
                            "training_seed": seed,
                            "mask_seed": mask_seed,
                            "gap_length": gap,
                            "information_combination": combination,
                            "attribution_estimand": "operational_dropout",
                            "component_estimator": "proposed_checkpoint",
                            "checkpoint_sha256": checkpoints[str(seed)]["sha256"],
                            "anchor_id": f"A-{station}-{mask_seed}",
                            "mask_sha256": mask_inventory[scenario_id]["mask"][
                                "sha256"
                            ],
                            "mask_metadata_sha256": mask_inventory[scenario_id][
                                "mask_metadata"
                            ]["sha256"],
                            "score_cells_sha256": score_hash,
                            "score_cell_count": 1,
                            "evaluation_split": "validation",
                            "evidence_role": "model_selection_only",
                            "formal_evidence": False,
                            "data_version": contract["data_version"],
                            "design_hash": contract["design_hash"],
                        }
                        events.append({**common, "MAE": 1.0 + index / 10, "RMSE": 2.0})
                        daily.append(
                            {
                                **common,
                                "date": "2017-01-01",
                                "target": "T",
                                "y_true": 1.0,
                                "y_pred": 1.1,
                                "q05": 0.5,
                                "q25": 0.8,
                                "q50": 1.1,
                                "q75": 1.4,
                                "q95": 1.8,
                                "quality_approved": True,
                                "artificial_mask": True,
                            }
                        )
    events_path = root / "branch_ablation_metrics.parquet"
    daily_path = root / "branch_ablation_daily_predictions.parquet"
    pd.DataFrame(events).to_parquet(events_path, index=False)
    pd.DataFrame(daily).to_parquet(daily_path, index=False)
    manifest = {
        "schema_version": finalization.BRANCH_ABLATION_MANIFEST_SCHEMA_VERSION,
        "attribution_estimand": "operational_dropout",
        "component_estimator": "proposed_checkpoint",
        "checkpoint_by_seed": checkpoints,
        "mask_units": list(mask_inventory.values()),
        "event_metrics": _identity(events_path),
        "daily_predictions": _identity(daily_path),
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
        **contract,
    }
    (root / "branch_ablation_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return events_path


def test_branch_artifact_has_exact_shared_cells_masks_and_checkpoint_seeds(
    tmp_path: Path,
) -> None:
    path = _write_branch_artifact(tmp_path / "branch")
    events, _ = finalization.validate_branch_ablation_artifact(
        path, expected_contract=_contract()
    )
    assert len(events) == 675

    changed = pd.read_parquet(path)
    changed.loc[0, "score_cells_sha256"] = "f" * 64
    changed.to_parquet(path, index=False)
    manifest_path = path.parent / "branch_ablation_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["event_metrics"] = _identity(path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="do not share score_cells_sha256"):
        finalization.validate_branch_ablation_artifact(
            path, expected_contract=_contract()
        )


def _checkpoint_metadata(
    models: tuple[str, ...],
    *,
    hit: dict[tuple[str, int], bool] | None = None,
) -> dict[tuple[str, int], dict[str, Any]]:
    hits = hit or {}
    return {
        (model, seed): {
            "model": model,
            "training_seed": seed,
            "best_epoch": 2,
            "epochs_run": 4,
            "hit_epoch_limit": bool(hits.get((model, seed), False)),
        }
        for model in models
        for seed in VALIDATION_DEEP_SEEDS
    }


def test_finalized_roster_is_t_capable_framework_only_and_immutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ranking_path = tmp_path / "ranking.csv"
    stage2_path = tmp_path / "stage2.csv"
    go_path = tmp_path / "go.json"
    stage3_dir = tmp_path / "stage3"
    branch_path = tmp_path / "branch.parquet"
    stage3_dir.mkdir()
    stage3_events_path = stage3_dir / "event_metrics.parquet"
    for path in (ranking_path, stage2_path, go_path, branch_path, stage3_events_path):
        path.write_bytes(path.name.encode())

    contract = build_design_contract(
        design_path="configs/design_freeze_v1.yaml",
        manifest_path="study_manifest.yaml",
        experiment_config_path="configs/experiments.yaml",
        data_version="published_v1",
        evaluation_split="validation",
        data_version_manifest_path="data_versions/published_v1/version_manifest.json",
    )
    contract["code_provenance"] = {
        **contract["code_provenance"],
        "relevant_source_clean": True,
        "tracked_worktree_clean": True,
        "status": "clean",
        "dirty_tracked_paths": [],
        "relevant_untracked_paths": [],
    }
    ranking = pd.DataFrame(
        {
            "rank": range(1, len(TRADITIONAL_CANDIDATES) + len(DEEP_CANDIDATES) + 1),
            "model": [
                "linear",
                *[model for model in TRADITIONAL_CANDIDATES if model != "linear"],
                *DEEP_CANDIDATES,
            ],
        }
    )
    finalists = ("brits_ref", "csdi", "proposed")
    stage3_events = pd.DataFrame({"model": list(finalists)})
    branch = pd.DataFrame({"training_seed": list(VALIDATION_DEEP_SEEDS)})
    decision = {
        "decision": "framework_only",
        "best_traditional_model": "linear",
    }
    monkeypatch.setattr(
        finalization,
        "validate_ranking_artifact",
        lambda *args, **kwargs: (ranking, {}),
    )
    monkeypatch.setattr(
        finalization,
        "validate_stage2_selection_artifact",
        lambda *args, **kwargs: (pd.DataFrame(), finalists, {}),
    )
    monkeypatch.setattr(
        finalization,
        "validate_completed_deep_stage",
        lambda *args, **kwargs: (
            stage3_events,
            _checkpoint_metadata(finalists),
            {},
        ),
    )
    monkeypatch.setattr(
        finalization,
        "validate_branch_ablation_artifact",
        lambda *args, **kwargs: (branch, {}),
    )
    monkeypatch.setattr(
        finalization,
        "validate_go_no_go_artifact",
        lambda *args, **kwargs: (decision, pd.DataFrame(), (stage3_events_path,)),
    )
    output = tmp_path / "finalized_model_roster.json"
    roster = finalization.finalize_validation_roster(
        ranking_path=ranking_path,
        stage2_selection_path=stage2_path,
        stage3_dir=stage3_dir,
        branch_metrics_path=branch_path,
        go_no_go_path=go_path,
        output_path=output,
        design_path="configs/design_freeze_v1.yaml",
        study_manifest_path="study_manifest.yaml",
        experiment_config_path="configs/experiments.yaml",
        data_version_manifest_path="data_versions/published_v1/version_manifest.json",
        anchor_catalog_path="metadata/validation_anchors.csv",
        expected_contract=contract,
    )

    assert roster["selected_models"][: len(TRADITIONAL_CANDIDATES)] == list(
        TRADITIONAL_CANDIDATES
    )
    assert "brits_ref" in roster["selected_models"]
    assert "csdi" in roster["selected_models"]
    assert "proposed" not in roster["selected_models"]
    assert "rating_curve" not in roster["selected_models"]
    assert "independent_flow" not in roster["selected_models"]
    assert roster["proposed_decision"] == "framework_only"
    assert set(roster["artifacts"]) == {
        "ranking",
        "stage2_selection",
        "go_no_go",
    }
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        finalization.finalize_validation_roster(
            ranking_path=ranking_path,
            stage2_selection_path=stage2_path,
            stage3_dir=stage3_dir,
            branch_metrics_path=branch_path,
            go_no_go_path=go_path,
            output_path=output,
            design_path="configs/design_freeze_v1.yaml",
            study_manifest_path="study_manifest.yaml",
            experiment_config_path="configs/experiments.yaml",
            data_version_manifest_path=(
                "data_versions/published_v1/version_manifest.json"
            ),
            anchor_catalog_path="metadata/validation_anchors.csv",
            expected_contract=contract,
        )


def test_stage3_hit_epoch_limit_excludes_model_from_roster(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ranking_path = tmp_path / "ranking.csv"
    stage2_path = tmp_path / "stage2.csv"
    go_path = tmp_path / "go.json"
    stage3_dir = tmp_path / "stage3"
    branch_path = tmp_path / "branch.parquet"
    stage3_dir.mkdir()
    stage3_events_path = stage3_dir / "event_metrics.parquet"
    for path in (ranking_path, stage2_path, go_path, branch_path, stage3_events_path):
        path.write_bytes(path.name.encode())

    contract = build_design_contract(
        design_path="configs/design_freeze_v1.yaml",
        manifest_path="study_manifest.yaml",
        experiment_config_path="configs/experiments.yaml",
        data_version="published_v1",
        evaluation_split="validation",
        data_version_manifest_path="data_versions/published_v1/version_manifest.json",
    )
    contract["code_provenance"] = {
        **contract["code_provenance"],
        "relevant_source_clean": True,
        "tracked_worktree_clean": True,
        "status": "clean",
        "dirty_tracked_paths": [],
        "relevant_untracked_paths": [],
    }
    ranking = pd.DataFrame(
        {
            "rank": range(1, len(TRADITIONAL_CANDIDATES) + 1),
            "model": list(TRADITIONAL_CANDIDATES),
        }
    )
    ranking.loc[0, "model"] = "linear"
    finalists = ("brits_ref", "csdi", "proposed")
    stage3_events = pd.DataFrame({"model": list(finalists)})
    branch = pd.DataFrame({"training_seed": list(VALIDATION_DEEP_SEEDS)})
    decision = {
        "decision": "include_proposed_formally",
        "best_traditional_model": "linear",
    }
    monkeypatch.setattr(
        finalization,
        "validate_ranking_artifact",
        lambda *args, **kwargs: (ranking, {}),
    )
    monkeypatch.setattr(
        finalization,
        "validate_stage2_selection_artifact",
        lambda *args, **kwargs: (pd.DataFrame(), finalists, {}),
    )
    monkeypatch.setattr(
        finalization,
        "validate_completed_deep_stage",
        lambda *args, **kwargs: (
            stage3_events,
            _checkpoint_metadata(finalists, hit={("csdi", 33): True}),
            {},
        ),
    )
    monkeypatch.setattr(
        finalization,
        "validate_branch_ablation_artifact",
        lambda *args, **kwargs: (branch, {}),
    )
    monkeypatch.setattr(
        finalization,
        "validate_go_no_go_artifact",
        lambda *args, **kwargs: (decision, pd.DataFrame(), (stage3_events_path,)),
    )
    output = tmp_path / "finalized_model_roster.json"
    roster = finalization.finalize_validation_roster(
        ranking_path=ranking_path,
        stage2_selection_path=stage2_path,
        stage3_dir=stage3_dir,
        branch_metrics_path=branch_path,
        go_no_go_path=go_path,
        output_path=output,
        design_path="configs/design_freeze_v1.yaml",
        study_manifest_path="study_manifest.yaml",
        experiment_config_path="configs/experiments.yaml",
        data_version_manifest_path="data_versions/published_v1/version_manifest.json",
        anchor_catalog_path="metadata/validation_anchors.csv",
        expected_contract=contract,
    )

    assert "csdi" not in roster["selected_models"]
    assert "brits_ref" in roster["selected_models"]
    assert "proposed" in roster["selected_models"]
    assert roster["proposed_decision"] == "include_proposed_formally"


def test_stage3_proposed_hit_epoch_limit_is_framework_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ranking_path = tmp_path / "ranking.csv"
    stage2_path = tmp_path / "stage2.csv"
    go_path = tmp_path / "go.json"
    stage3_dir = tmp_path / "stage3"
    branch_path = tmp_path / "branch.parquet"
    stage3_dir.mkdir()
    stage3_events_path = stage3_dir / "event_metrics.parquet"
    for path in (ranking_path, stage2_path, go_path, branch_path, stage3_events_path):
        path.write_bytes(path.name.encode())

    contract = build_design_contract(
        design_path="configs/design_freeze_v1.yaml",
        manifest_path="study_manifest.yaml",
        experiment_config_path="configs/experiments.yaml",
        data_version="published_v1",
        evaluation_split="validation",
        data_version_manifest_path="data_versions/published_v1/version_manifest.json",
    )
    contract["code_provenance"] = {
        **contract["code_provenance"],
        "relevant_source_clean": True,
        "tracked_worktree_clean": True,
        "status": "clean",
        "dirty_tracked_paths": [],
        "relevant_untracked_paths": [],
    }
    ranking = pd.DataFrame(
        {
            "rank": range(1, len(TRADITIONAL_CANDIDATES) + 1),
            "model": list(TRADITIONAL_CANDIDATES),
        }
    )
    ranking.loc[0, "model"] = "linear"
    finalists = ("brits_ref", "csdi", "proposed")
    stage3_events = pd.DataFrame({"model": list(finalists)})
    branch = pd.DataFrame({"training_seed": list(VALIDATION_DEEP_SEEDS)})
    decision = {
        "decision": "include_proposed_formally",
        "best_traditional_model": "linear",
    }
    monkeypatch.setattr(
        finalization,
        "validate_ranking_artifact",
        lambda *args, **kwargs: (ranking, {}),
    )
    monkeypatch.setattr(
        finalization,
        "validate_stage2_selection_artifact",
        lambda *args, **kwargs: (pd.DataFrame(), finalists, {}),
    )
    monkeypatch.setattr(
        finalization,
        "validate_completed_deep_stage",
        lambda *args, **kwargs: (
            stage3_events,
            _checkpoint_metadata(finalists, hit={("proposed", 22): True}),
            {},
        ),
    )
    monkeypatch.setattr(
        finalization,
        "validate_branch_ablation_artifact",
        lambda *args, **kwargs: (branch, {}),
    )
    monkeypatch.setattr(
        finalization,
        "validate_go_no_go_artifact",
        lambda *args, **kwargs: (decision, pd.DataFrame(), (stage3_events_path,)),
    )
    output = tmp_path / "finalized_model_roster.json"
    roster = finalization.finalize_validation_roster(
        ranking_path=ranking_path,
        stage2_selection_path=stage2_path,
        stage3_dir=stage3_dir,
        branch_metrics_path=branch_path,
        go_no_go_path=go_path,
        output_path=output,
        design_path="configs/design_freeze_v1.yaml",
        study_manifest_path="study_manifest.yaml",
        experiment_config_path="configs/experiments.yaml",
        data_version_manifest_path="data_versions/published_v1/version_manifest.json",
        anchor_catalog_path="metadata/validation_anchors.csv",
        expected_contract=contract,
    )

    assert "proposed" not in roster["selected_models"]
    assert roster["proposed_decision"] == "framework_only"
    assert "brits_ref" in roster["selected_models"]
    assert "csdi" in roster["selected_models"]


def test_v4_roster_reloads_published_v2_anchor_catalog(tmp_path: Path) -> None:
    artifacts: dict[str, dict[str, Any]] = {}
    for name, suffix in (
        ("ranking", ".csv"),
        ("stage2_selection", ".csv"),
        ("go_no_go", ".json"),
        ("best_simple_baseline_lookup", ".csv"),
    ):
        path = tmp_path / f"{name}{suffix}"
        path.write_text(f"frozen validation artifact: {name}\n", encoding="utf-8")
        artifacts[name] = {
            "path": str(path.resolve()),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    contract = build_design_contract(
        design_path="configs/design_freeze_v4.yaml",
        manifest_path="study_manifest.yaml",
        experiment_config_path="configs/experiments.yaml",
        data_version="published_v2",
        evaluation_split="validation",
        data_version_manifest_path="data_versions/published_v2/version_manifest.json",
    )
    document = {
        "schema_version": FINALIZED_MODEL_ROSTER_SCHEMA_VERSION,
        "finalized": True,
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
        "selected_models": ["donor_regression", "xgboost"],
        "best_traditional_model": "donor_regression",
        "proposed_decision": "framework_only",
        "validation_anchor_catalog": validation_anchor_catalog_identity(
            expected_data_version="published_v2"
        ),
        "artifacts": artifacts,
        **contract,
    }
    roster = tmp_path / "finalized_model_roster.json"
    roster.write_text(json.dumps(document), encoding="utf-8")

    loaded = load_finalized_model_roster(
        roster, design_path="configs/design_freeze_v4.yaml"
    )

    assert loaded.selected_models == ("donor_regression", "xgboost")
    assert loaded.selection_data_version == "published_v2"
    assert loaded.validation_anchor_catalog["path"].endswith(
        "metadata/validation_anchors_v2.csv"
    )
    historical = validation_anchor_catalog_identity()
    assert historical["path"].endswith("metadata/validation_anchors.csv")
    assert historical["sha256"] != loaded.validation_anchor_catalog["sha256"]
    assert canonical_validation_anchor_path("published_v2").name == (
        "validation_anchors_v2.csv"
    )


def test_historical_designs_still_read_v1_anchor_catalog() -> None:
    identity = validation_anchor_catalog_identity(expected_data_version="published_v1")
    assert identity["path"].endswith("metadata/validation_anchors.csv")
    assert canonical_validation_anchor_path("published_v1").name == (
        "validation_anchors.csv"
    )


def test_stage3_stability_and_proposed_versus_donor_use_key_cells() -> None:
    events = []
    for station in VALIDATION_STATIONS:
        for seed in VALIDATION_MASK_SEEDS:
            events.append(
                {
                    "condition_id": f"VAL-BLK1-{station}-T-D090",
                    "station_id": station,
                    "mask_seed": seed,
                    "model": "donor_regression",
                    "training_seed": np.nan,
                    "skill": 0.22,
                    "target": "T",
                    "evaluation_split": "validation",
                    "data_version": "published_v1",
                    "design_hash": "d" * 64,
                    "evidence_role": "model_selection_only",
                }
            )
            events.append(
                {
                    "condition_id": f"VAL-BLK1-{station}-T-D180",
                    "station_id": station,
                    "mask_seed": seed,
                    "model": "donor_regression",
                    "training_seed": np.nan,
                    "skill": 0.20,
                    "target": "T",
                    "evaluation_split": "validation",
                    "data_version": "published_v1",
                    "design_hash": "d" * 64,
                    "evidence_role": "model_selection_only",
                }
            )
            events.append(
                {
                    "condition_id": f"VAL-BLK1-{station}-TFL-D090",
                    "station_id": station,
                    "mask_seed": seed,
                    "model": "donor_regression",
                    "training_seed": np.nan,
                    "skill": 0.21,
                    "target": "T",
                    "evaluation_split": "validation",
                    "data_version": "published_v1",
                    "design_hash": "d" * 64,
                    "evidence_role": "model_selection_only",
                }
            )
            events.append(
                {
                    "condition_id": f"VAL-SITE-{station}-HYDROONLY-D090",
                    "station_id": station,
                    "mask_seed": seed,
                    "model": "donor_regression",
                    "training_seed": np.nan,
                    "skill": 0.19,
                    "target": "T",
                    "evaluation_split": "validation",
                    "data_version": "published_v1",
                    "design_hash": "d" * 64,
                    "evidence_role": "model_selection_only",
                }
            )
            for training_seed in VALIDATION_DEEP_SEEDS:
                events.append(
                    {
                        "condition_id": f"VAL-BLK1-{station}-T-D090",
                        "station_id": station,
                        "mask_seed": seed,
                        "model": "proposed",
                        "training_seed": training_seed,
                        "skill": 0.16 if station != "P3" else 0.24,
                        "target": "T",
                        "evaluation_split": "validation",
                        "data_version": "published_v1",
                        "design_hash": "d" * 64,
                        "evidence_role": "model_selection_only",
                    }
                )
                events.append(
                    {
                        "condition_id": f"VAL-BLK1-{station}-T-D180",
                        "station_id": station,
                        "mask_seed": seed,
                        "model": "proposed",
                        "training_seed": training_seed,
                        "skill": 0.15,
                        "target": "T",
                        "evaluation_split": "validation",
                        "data_version": "published_v1",
                        "design_hash": "d" * 64,
                        "evidence_role": "model_selection_only",
                    }
                )
                events.append(
                    {
                        "condition_id": f"VAL-BLK1-{station}-TFL-D090",
                        "station_id": station,
                        "mask_seed": seed,
                        "model": "proposed",
                        "training_seed": training_seed,
                        "skill": 0.14,
                        "target": "T",
                        "evaluation_split": "validation",
                        "data_version": "published_v1",
                        "design_hash": "d" * 64,
                        "evidence_role": "model_selection_only",
                    }
                )
                events.append(
                    {
                        "condition_id": f"VAL-SITE-{station}-HYDROONLY-D090",
                        "station_id": station,
                        "mask_seed": seed,
                        "model": "proposed",
                        "training_seed": training_seed,
                        "skill": 0.13,
                        "target": "T",
                        "evaluation_split": "validation",
                        "data_version": "published_v1",
                        "design_hash": "d" * 64,
                        "evidence_role": "model_selection_only",
                    }
                )
    comparison = finalization.assess_proposed_versus_donor(pd.DataFrame(events))
    assert comparison["claim"] == "conditional"
    assert comparison["n_compared_cells"] == 36
    assert comparison["n_proposed_better"] == 3
    assert comparison["formal_evidence"] is False


def test_stage3_stability_table_is_one_row_per_model_seed(tmp_path: Path) -> None:
    stage = _write_completed_stage(
        tmp_path / "deep_stability",
        models=("proposed",),
        seeds=VALIDATION_DEEP_SEEDS,
        stage_name="deep_stability",
    )
    events, checkpoints, _ = finalization.validate_completed_deep_stage(
        stage,
        expected_models=("proposed",),
        expected_seeds=VALIDATION_DEEP_SEEDS,
        expected_contract=_contract(),
        expected_stage_name="deep_stability",
    )
    checkpoints[("proposed", 33)]["hit_epoch_limit"] = True
    table = finalization.summarize_stage3_stability(events, checkpoints)
    assert len(table) == 3
    assert set(table["seed"]) == set(VALIDATION_DEEP_SEEDS)
    assert set(table["event_rows"]) == {105}
    assert table.loc[table["seed"].eq(33), "budget_status"].iloc[0] == "budget_unstable"
    assert table.loc[table["seed"].eq(11), "budget_status"].iloc[0] == "budget_stable"
    assert table["formal_evidence"].eq(False).all()


def test_expected_scenario_ids_include_validation_split_token() -> None:
    ids = finalization._expected_scenario_ids()
    conditions_per_station = 7
    assert len(ids) == (
        len(VALIDATION_STATIONS) * conditions_per_station * len(VALIDATION_MASK_SEEDS)
    )
    for station in VALIDATION_STATIONS:
        for seed in VALIDATION_MASK_SEEDS:
            assert f"VAL-PNT-{station}-T-P30-VALIDATION-R{seed:04d}" in ids
            assert f"VAL-BLK1-{station}-T-D010-VALIDATION-R{seed:04d}" in ids
            assert f"VAL-PNT-{station}-T-P30-R{seed:04d}" not in ids
    assert all("-VALIDATION-R" in item for item in ids)


def test_expected_v2_scenario_ids_include_data_version_token() -> None:
    ids = finalization._expected_scenario_ids("published_v2")
    assert "VAL-BLK1-B1-T-D010-PUBLISHED_V2-VALIDATION-R0101" in ids
    assert "VAL-BLK1-B1-T-D010-VALIDATION-R0101" not in ids
