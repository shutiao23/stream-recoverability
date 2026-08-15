from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

import stream_recoverability.analysis.frozen_pipeline as frozen_pipeline_module
from stream_recoverability.analysis.compensation import information_combinations
from stream_recoverability.analysis.frozen_pipeline import (
    EVIDENCE_FIELDS,
    FIXED_ARTIFACTS,
    RETRAINED_INFORMATION_COMBINATIONS,
    analyze_calibration,
    analyze_data_version_sensitivity,
    analyze_event_pairs,
    analyze_frontiers,
    analyze_information,
    analyze_resilience_outputs,
    audit_prediction_overlap,
    build_analysis_code_identity,
    guarded_model_skill,
    load_frozen_inputs,
    load_frozen_inputs_from_manifest,
    load_frozen_statistics,
    one_hinge_breakpoint,
    run_frozen_analysis,
)

PROJECT_ROOT = Path(__file__).parents[1]
DESIGN = PROJECT_ROOT / "configs/design_freeze_v1.yaml"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_digest(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _contract(data_version: str = "published_v1") -> dict[str, object]:
    design = yaml.safe_load(DESIGN.read_text(encoding="utf-8"))
    contract: dict[str, object] = {
        "design_version": design["design_version"],
        "data_version": data_version,
        "evaluation_split": "development_test",
        "mask_schema_version": design["mask_design"]["schema_version"],
        "model_schema_version": design["training"]["schema_version"],
        "statistics_schema_version": design["statistics"]["schema_version"],
        "input_digests": {
            "design_freeze": _sha256(DESIGN),
            "study_manifest": "1" * 64,
            "experiment_config": "2" * 64,
            "data_version_manifest": "3" * 64,
        },
        "code_identity": {
            "schema_version": "code_provenance_v1",
            "relevant_source_digest": "a" * 64,
            "relevant_source_file_count": 17,
        },
    }
    contract["design_hash"] = _canonical_digest(contract)
    contract["code_provenance"] = {
        **contract["code_identity"],
        "git_commit": "b" * 40,
        "tracked_worktree_clean": True,
        "relevant_source_clean": True,
        "dirty_tracked_paths": [],
        "relevant_untracked_paths": [],
        "external_relevant_input_count": 0,
        "status": "clean",
    }
    return contract


def _evidence(data_version: str = "published_v1") -> dict[str, object]:
    contract = _contract(data_version)
    return {
        **{field: contract[field] for field in EVIDENCE_FIELDS},
        "formal_evidence": True,
        "evidence_role": "formal_development_evaluation",
    }


def _file_identity(path: Path) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _registry_builder_identity() -> dict[str, object]:
    source_paths = (
        PROJECT_ROOT / "scripts/21_build_formal_suite_registry.py",
        PROJECT_ROOT / "src/stream_recoverability/analysis/formal_registry.py",
    )
    value: dict[str, object] = {
        "schema_version": "formal_registry_builder_identity_v1",
        "sources": [
            {
                "path": path.relative_to(PROJECT_ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in source_paths
        ],
        "identity_hash_scope": "canonical_json_excluding_identity_sha256",
    }
    value["identity_sha256"] = _canonical_digest(value)
    return value


def _formal_registry_fields(
    root: Path,
    data_version: str,
    *,
    framework_only: bool = False,
) -> dict[str, object]:
    primary = data_version == "published_v1"
    selected_models = ["linear"] if framework_only else ["linear", "csdi", "proposed"]
    decision = "framework_only" if framework_only else "include_proposed_formally"
    bundle_directory_names = {
        "primary",
        "published_v1",
        "no_s2_suspect_v1",
        "b1_no_level_v1",
        "b1_shift_sensitivity_v1",
    }
    roster_root = root.parent if root.name in bundle_directory_names else root
    roster_path = roster_root / "finalized_model_roster.json"
    roster_path.write_text(
        json.dumps(
            {
                "schema_version": "finalized_model_roster_v1",
                "selected_models": selected_models,
                "proposed_decision": decision,
            }
        ),
        encoding="utf-8",
    )
    roster = {
        "path": str(roster_path.resolve()),
        "sha256": _sha256(roster_path),
        "selected_models": selected_models,
        "proposed_decision": decision,
    }
    if primary:
        required_roles = [
            "core_full",
            "dense_frontier",
            "network_resilience",
            "event_uncertainty",
            "operational_dropout",
            "retrained_upper_bound",
        ]
        role_sources = {
            "core_full": ("full", [*selected_models, "independent_flow", "rating_curve"]),
            "dense_frontier": (
                "science_dense",
                [*selected_models, "independent_flow", "rating_curve"],
            ),
            "network_resilience": ("science_resilience", selected_models),
            "event_uncertainty": (
                "full",
                [*selected_models, "independent_flow", "rating_curve"],
            ),
            "operational_dropout": (
                "science_compensation",
                ["information_compensation"],
            ),
            "retrained_upper_bound": (
                "retrained_information_upper_bounds",
                ["retrained_information_upper_bound"],
            ),
        }
        proposed_roles = {"operational_dropout", "retrained_upper_bound"}
        bundle_role = "primary"
        bundle_kind = "primary"
    else:
        required_roles = [
            "sensitivity_core_T",
            "sensitivity_dense_frontier",
            "sensitivity_operational_dropout",
        ]
        role_sources = {
            "sensitivity_core_T": ("core", selected_models),
            "sensitivity_dense_frontier": ("science_dense", selected_models),
            "sensitivity_operational_dropout": (
                "science_compensation",
                ["information_compensation"],
            ),
        }
        proposed_roles = {"sensitivity_operational_dropout"}
        bundle_role = "sensitivity_compact"
        bundle_kind = "sensitivity"

    source_by_suite: dict[str, dict[str, object]] = {}
    for suite, models in dict(role_sources.values()).items():
        directory = root / "registry_sources" / suite
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "run_manifest.json"
        path.write_text(json.dumps({"suite": suite, "models": models}), encoding="utf-8")
        source_by_suite[suite] = {
            "suite": suite,
            "run_directory": str(directory.resolve()),
            "manifest": _file_identity(path),
            "models": models,
        }
    suite_roles: list[dict[str, object]] = []
    for role in required_roles:
        if framework_only and role in proposed_roles:
            suite_roles.append(
                {
                    "role": role,
                    "status": "not_applicable",
                    "reason": "proposed_decision=framework_only",
                    "manifest_suites": [],
                    "source_manifest_sha256": [],
                    "expected_models": [],
                }
            )
            continue
        suite, models = role_sources[role]
        source = source_by_suite[suite]
        suite_roles.append(
            {
                "role": role,
                "status": "complete",
                "reason": None,
                "manifest_suites": [suite],
                "source_manifest_sha256": [source["manifest"]["sha256"]],
                "expected_models": models,
            }
        )
    if framework_only:
        used_suites = {
            role_sources[role][0]
            for role in required_roles
            if role not in proposed_roles
        }
        source_by_suite = {
            suite: source
            for suite, source in source_by_suite.items()
            if suite in used_suites
        }
    version_manifest = PROJECT_ROOT / f"data_versions/{data_version}/version_manifest.json"
    anchors = PROJECT_ROOT / "metadata/frontier_anchors.csv"
    registry: dict[str, object] = {
        "schema_version": "formal_suite_registry_v1",
        "finalized": True,
        "bundle_kind": bundle_kind,
        "bundle_role": bundle_role,
        "data_version": data_version,
        "evaluation_split": "development_test",
        "design_hash": _contract(data_version)["design_hash"],
        "code_identity": _contract(data_version)["code_identity"],
        "registry_builder_identity": _registry_builder_identity(),
        "data_version_manifest": _file_identity(version_manifest),
        "frontier_anchor_catalog": {
            **_file_identity(anchors),
            "count": len(pd.read_csv(anchors)),
            "data_version": "published_v1",
            "evaluation_split": "development_test",
        },
        "formal_root": str(root.resolve()),
        "finalized_model_roster": roster,
        "not_applicable_suites": [],
        "required_suite_roles": required_roles,
        "suite_roles": suite_roles,
        "sources": list(source_by_suite.values()),
        "suites": [
            {"name": suite, "path": source["run_directory"]}
            for suite, source in source_by_suite.items()
        ],
        "registry_hash_scope": "canonical_json_excluding_registry_sha256",
    }
    registry["registry_sha256"] = _canonical_digest(registry)
    registry_path = root / "formal_suite_registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    return {
        "formal_evidence": True,
        "evidence_role": "formal_development_evaluation",
        "bundle_kind": bundle_kind,
        "bundle_role": bundle_role,
        "finalized_model_roster": roster,
        "required_suite_roles": required_roles,
        "suite_roles": suite_roles,
        "suite_registry": {
            "source": "registry_file",
            "path": str(registry_path.resolve()),
            "size": registry_path.stat().st_size,
            "sha256": _sha256(registry_path),
        },
    }


def _write_minimal_bundle(
    tmp_path: Path, *, framework_only: bool = False
) -> tuple[Path, Path, Path]:
    evidence = _evidence()
    predictions = pd.DataFrame(
        [
            {
                **evidence,
                "experiment": "M1",
                "scenario_id": "s1",
                "station_id": "B1",
                "target": "T",
                "model": "climatology",
            }
        ]
    )
    events = pd.DataFrame(
        [
            {
                **evidence,
                "experiment": "M1",
                "scenario_id": "s1",
                "station_id": "B1",
                "target": "T",
                "model": "climatology",
                "MAE": 1.0,
            }
        ]
    )
    predictions_path = tmp_path / "predictions.parquet"
    events_path = tmp_path / "events.parquet"
    predictions.to_parquet(predictions_path, index=False)
    events.to_parquet(events_path, index=False)
    manifest = {
        **_contract(),
        **_formal_registry_fields(
            tmp_path, "published_v1", framework_only=framework_only
        ),
        "schema_version": "formal_aggregate_manifest_v2",
        "frozen": True,
        "complete": True,
        "formal_design_complete": True,
        "formal_training_seed_complete": True,
        "formal_mask_seed_complete": True,
        "run_unit_complete": True,
        "evidence_complete": True,
        "finite_predictions": True,
        "finite_event_metrics": True,
        "checkpoint_contract_complete": True,
        "expected_run_unit_count": 1,
        "completed_run_unit_count": 1,
        "structural_skip_run_unit_count": 0,
        "expected_evidence_run_unit_count": 1,
        "completed_evidence_run_unit_count": 1,
        "expected_run_unit_keys_sha256": "4" * 64,
        "completed_run_unit_keys_sha256": "4" * 64,
        "prediction_rows": len(predictions),
        "event_rows": len(events),
        "predictions_sha256": _sha256(predictions_path),
        "event_metrics_sha256": _sha256(events_path),
        "retryable_failures": [],
        "retryable_run_keys": [],
        "retryable_run_unit_count": 0,
    }
    manifest_path = tmp_path / "top_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return predictions_path, events_path, manifest_path


def _write_anchored_bundle(
    root: Path,
    data_version: str,
    *,
    mae_offset: float,
    framework_only: bool = False,
) -> tuple[Path, Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    evidence = _evidence(data_version)
    prediction_rows = []
    event_rows = []
    for anchor_index, anchor in enumerate(("A1", "A2")):
        for seed, seed_offset in ((11, -0.1), (22, 0.1)):
            shared = {
                **evidence,
                "experiment": "M2",
                "condition_id": "D30",
                "scenario_id": f"scenario-{anchor}",
                "anchor_id": anchor,
                "anchor_year": 2019 + anchor_index,
                "center_date": f"{2019 + anchor_index}-07-01",
                "mask_seed": 101 + anchor_index,
                "station_id": "B1",
                "target": "T",
                "model": "candidate",
                "training_seed": seed,
                "gap_length": 30,
                "window_length": 368,
            }
            prediction_rows.append(
                {
                    **shared,
                    "date": f"{2019 + anchor_index}-07-01",
                    "y_true": 10.0,
                    "y_pred": 11.0 + mae_offset + seed_offset,
                }
            )
            event_rows.append(
                {
                    **shared,
                    "MAE": 1.0 + anchor_index + mae_offset + seed_offset,
                    "RMSE": 1.1 + anchor_index + mae_offset + seed_offset,
                }
            )
    predictions_path = root / "predictions.parquet"
    events_path = root / "event_metrics.parquet"
    pd.DataFrame(prediction_rows).to_parquet(predictions_path, index=False)
    pd.DataFrame(event_rows).to_parquet(events_path, index=False)
    count = len(event_rows)
    manifest = {
        **_contract(data_version),
        **_formal_registry_fields(
            root, data_version, framework_only=framework_only
        ),
        "schema_version": "formal_aggregate_manifest_v2",
        "frozen": True,
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
        "retryable_run_unit_count": 0,
        "expected_run_unit_count": count,
        "completed_run_unit_count": count,
        "structural_skip_run_unit_count": 0,
        "expected_evidence_run_unit_count": count,
        "completed_evidence_run_unit_count": count,
        "expected_run_unit_keys_sha256": "7" * 64,
        "completed_run_unit_keys_sha256": "7" * 64,
        "daily_rows": len(prediction_rows),
        "event_rows": len(event_rows),
        "artifacts": {
            "predictions": {
                "path": str(predictions_path.resolve()),
                "size": predictions_path.stat().st_size,
                "sha256": _sha256(predictions_path),
            },
            "event_metrics": {
                "path": str(events_path.resolve()),
                "size": events_path.stat().st_size,
                "sha256": _sha256(events_path),
            },
        },
    }
    manifest_path = root / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return predictions_path, events_path, manifest_path


def _clean_code_identity() -> dict[str, object]:
    builder: dict[str, object] = {
        "schema_version": "frozen_analysis_builder_identity_v1",
        "sources": [],
        "identity_hash_scope": "canonical_json_excluding_identity_sha256",
    }
    builder["identity_sha256"] = _canonical_digest(builder)
    return {
        "schema_version": "analysis_code_identity_v1",
        "relevant_source_digest": "a" * 64,
        "relevant_source_file_count": 6,
        "files": [],
        "frozen_analysis_builder": builder,
        "tracked_relevant_source_clean": True,
        "dirty_tracked_paths": [],
        "relevant_untracked_paths": [],
        "missing_paths": [],
        "git_audit_available": True,
        "status": "clean",
    }


def test_frozen_statistics_lock_numerics_and_one_hinge_fit() -> None:
    statistics = load_frozen_statistics(DESIGN)
    assert statistics.bootstrap_replicates == 2000
    assert statistics.bootstrap_seed == 20260815
    assert statistics.confidence == pytest.approx(0.95)
    assert statistics.application_criteria is None
    assert statistics.denominator_guard["thresholds_by_target"]["T"]["value"] == 0.05

    estimate = one_hinge_breakpoint(
        [1, 3, 7, 14, 30, 60],
        [0.9, 0.85, 0.75, 0.55, 0.10, -0.50],
        [1, 1, 1, 2, 2, 2],
    )
    assert estimate["reason"] is None
    assert estimate["breakpoint_days"] in {3.0, 7.0, 14.0, 30.0}
    assert np.isfinite(estimate["weighted_sse"])


def test_guarded_skill_pairs_units_before_ratio_and_withholds_equality() -> None:
    guard = load_frozen_statistics(DESIGN).denominator_guard
    rows = []
    for scenario, target, denominator, numerator in (
        ("t-ok", "T", 1.0, 0.25),
        ("t-equal", "T", 0.05, 0.01),
        ("f-equal", "F", 0.5, 0.1),
        ("l-equal", "L", 0.005, 0.001),
    ):
        rows.extend(
            [
                {
                    "experiment": "SCI_DENSE",
                    "scenario_id": scenario,
                    "station_id": "B1",
                    "target": target,
                    "model": "candidate",
                    "MAE": numerator,
                },
                {
                    "experiment": "SCI_DENSE",
                    "scenario_id": scenario,
                    "station_id": "B1",
                    "target": target,
                    "model": "climatology",
                    "MAE": denominator,
                },
            ]
        )
    shuffled = pd.DataFrame(rows).sample(frac=1.0, random_state=17)
    result = guarded_model_skill(shuffled, guard).set_index(["scenario_id", "model"])
    assert result.loc[("t-ok", "candidate"), "skill"] == pytest.approx(0.75)
    for scenario in ("t-equal", "f-equal", "l-equal"):
        assert np.isnan(result.loc[(scenario, "candidate"), "skill"])
        assert result.loc[
            (scenario, "candidate"), "climatology_denominator_status"
        ] == ("near_zero_climatology_error")


def _dense_fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    evidence = _evidence()
    event_rows: list[dict[str, object]] = []
    daily_rows: list[dict[str, object]] = []
    skill_by_gap = {10: 0.8, 30: 0.4, 90: 0.6, 180: -0.2}
    for anchor_index, anchor in enumerate(("A1", "A2")):
        anchor_date = pd.Timestamp("2019-01-01") + pd.Timedelta(days=anchor_index * 20)
        for gap, skill in skill_by_gap.items():
            scenario = f"{anchor}-D{gap}"
            for model, seeds in (("climatology", [np.nan]), ("candidate", [11, 22])):
                for training_seed in seeds:
                    event_rows.append(
                        {
                            **evidence,
                            "experiment": "SCI_DENSE",
                            "scenario_id": scenario,
                            "condition_id": f"dense-D{gap}",
                            "anchor_id": anchor,
                            "anchor_year": 2019,
                            "center_date": anchor_date,
                            "station_id": "B1",
                            "target": "T",
                            "model": model,
                            "training_seed": training_seed,
                            "mask_seed": 101 + anchor_index,
                            "gap_length": gap,
                            "window_length": 368,
                            "MAE": 2.0
                            if model == "climatology"
                            else 2.0 * (1.0 - skill),
                        }
                    )
            daily_rows.append(
                {
                    **evidence,
                    "experiment": "SCI_DENSE",
                    "scenario_id": scenario,
                    "anchor_id": anchor,
                    "date": anchor_date,
                    "station_id": "B1",
                    "target": "T",
                    "model": "candidate",
                    "quality_approved": True,
                    "artificial_mask": True,
                }
            )
    return pd.DataFrame(event_rows), pd.DataFrame(daily_rows)


def test_frontier_pipeline_collapses_seeds_clusters_anchors_and_withholds_application() -> (
    None
):
    events, daily = _dense_fixture()
    overlap = audit_prediction_overlap(daily)
    statistics = dataclasses.replace(
        load_frozen_statistics(DESIGN),
        bootstrap_replicates=20,
        dense_t_gaps=(10.0, 30.0, 90.0, 180.0),
    )
    result = analyze_frontiers(events, overlap, statistics)
    candidate = result.statistical.loc[
        result.statistical["model"].eq("candidate")
    ].iloc[0]
    assert candidate["n_anchors"] == 2
    assert candidate["n_years"] == 1
    assert bool(candidate["training_seeds_collapsed_first"])
    assert candidate["n_bootstrap_samples"] == 20
    assert set(
        FRONTIER_REQUIRED := [
            "station_id",
            "target",
            "data_version",
            "model",
            "information_combination",
            "window",
        ]
    ).issubset(result.statistical.columns)
    assert len(FRONTIER_REQUIRED) == 6
    application = result.application.loc[
        result.application["model"].eq("candidate")
    ].iloc[0]
    assert application["application_threshold_status"] == "not_declared"
    assert np.isnan(application["operational_boundary_days"])
    monotone = result.monotone.loc[result.monotone["model"].eq("candidate")]
    assert monotone.sort_values("gap_length")[
        "frontier_value"
    ].tolist() == pytest.approx([0.8, 0.5, 0.5, -0.2])
    assert (
        len(
            result.bootstrap_samples.loc[
                result.bootstrap_samples["model"].eq("candidate")
            ]
        )
        == 80
    )
    for _, draw in result.bootstrap_samples.loc[
        result.bootstrap_samples["model"].eq("candidate")
    ].groupby("bootstrap_id"):
        assert draw["sampled_cluster_ids"].nunique() == 1
        assert draw["sampled_anchor_ids"].nunique() == 1


def test_information_seed_collapse_and_estimands_never_mix() -> None:
    evidence = _evidence()
    rows = []
    weights = {"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0}
    for subset in information_combinations():
        label = (
            "S0"
            if not subset
            else "S0+"
            + "+".join(source for source in ("A", "B", "C", "D") if source in subset)
        )
        for seed, offset in ((11, -0.5), (22, 0.5)):
            rows.append(
                {
                    **evidence,
                    "experiment": "SCI_COMP",
                    "scenario_id": "unit-1",
                    "anchor_id": "A1",
                    "anchor_year": 2019,
                    "mask_seed": 101,
                    "station_id": "B1",
                    "target": "T",
                    "gap_length": 30,
                    "window_length": 368,
                    "model": "information_compensation",
                    "training_seed": seed,
                    "information_combination": label,
                    "information_estimand": "operational_dropout",
                    "MAE": 20.0 - sum(weights[source] for source in subset) + offset,
                }
            )
    statistics = dataclasses.replace(
        load_frozen_statistics(DESIGN), bootstrap_replicates=20
    )
    result = analyze_information(pd.DataFrame(rows), statistics)
    shapley = result["shapley"].set_index("source")
    for source, expected in weights.items():
        assert shapley.loc[source, "shapley"] == pytest.approx(expected)
    assert set(result["operational"]["information_estimand"]) == {"operational_dropout"}
    assert result["retrained"].empty
    assert result["metrics"]["n_units"].eq(1).all()

    bad = pd.DataFrame(rows)
    bad["information_estimand"] = "unknown"
    with pytest.raises(ValueError, match="unknown information estimand"):
        analyze_information(bad, statistics)


def test_retrained_information_uses_exact_nine_without_shapley() -> None:
    evidence = _evidence()
    weights = {"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0}
    rows = []
    for anchor_index, anchor in enumerate(("A1", "A2")):
        for subset in RETRAINED_INFORMATION_COMBINATIONS:
            label = (
                "S0"
                if not subset
                else "S0+"
                + "+".join(
                    source for source in ("A", "B", "C", "D") if source in subset
                )
            )
            for seed, seed_offset in ((11, -0.25), (22, 0.25)):
                rows.append(
                    {
                        **evidence,
                        "experiment": "SCI_COMP_RETRAINED",
                        "scenario_id": f"unit-{anchor}",
                        "anchor_id": anchor,
                        "anchor_year": 2019 + anchor_index,
                        "mask_seed": 101 + anchor_index,
                        "station_id": "B1",
                        "target": "T",
                        "gap_length": 30,
                        "window_length": 368,
                        "model": "information_compensation_retrained",
                        "training_seed": seed,
                        "information_combination": label,
                        "information_estimand": "retrained_upper_bound",
                        "MAE": 20.0
                        - sum(weights[source] for source in subset)
                        + seed_offset,
                    }
                )
    statistics = dataclasses.replace(
        load_frozen_statistics(DESIGN), bootstrap_replicates=20
    )
    result = analyze_information(pd.DataFrame(rows), statistics)
    assert result["operational"].empty
    assert result["shapley"].empty
    assert result["interactions"].empty
    assert len(result["metrics"]) == 9
    assert len(result["retrained"]) == 8
    ab = (
        result["retrained"]
        .loc[result["retrained"]["information_combination"].eq("S0+A+B")]
        .iloc[0]
    )
    assert ab["reference_information_combination"] == "S0"
    assert ab["MAE_gain_vs_S0"] == pytest.approx(3.0)
    assert ab["n_units"] == 2
    assert set(result["retrained"]["hypothesis_family"]) == {
        "retrained_information_upper_bound"
    }
    assert set(result["hypotheses"]["hypothesis_family"]) == {
        "retrained_information_upper_bound"
    }

    missing = pd.DataFrame(rows).loc[
        lambda frame: (
            ~(
                frame["anchor_id"].eq("A2")
                & frame["information_combination"].eq("S0+A+B+C+D")
            )
        )
    ]
    with pytest.raises(ValueError, match="requires exactly 9 coalitions"):
        analyze_information(missing, statistics)


def test_information_rejects_estimand_mixing_within_one_unit() -> None:
    evidence = _evidence()
    rows = []
    for subset in information_combinations():
        rows.append(
            {
                **evidence,
                "experiment": "SCI_COMP",
                "scenario_id": "mixed-unit",
                "anchor_id": "A1",
                "anchor_year": 2019,
                "mask_seed": 101,
                "station_id": "B1",
                "target": "T",
                "gap_length": 30,
                "window_length": 368,
                "model": "information_compensation",
                "training_seed": 11,
                "information_combination": (
                    "S0" if not subset else "S0+" + "+".join(sorted(subset))
                ),
                "information_estimand": (
                    "retrained_upper_bound"
                    if subset == frozenset({"A"})
                    else "operational_dropout"
                ),
                "MAE": 1.0,
            }
        )
    with pytest.raises(ValueError, match="mixes operational and retrained"):
        analyze_information(pd.DataFrame(rows), load_frozen_statistics(DESIGN))


def test_event_episode_control_inference_collapses_training_seeds_first() -> None:
    evidence = _evidence()
    rows = []
    for pair_index in range(3):
        for role, mae in (("event_episode", 2.0), ("matched_control", 1.0)):
            for seed, offset in ((11, -0.2), (22, 0.2)):
                rows.append(
                    {
                        **evidence,
                        "experiment": "M7b",
                        "pair_id": f"P{pair_index}",
                        "anchor_id": f"P{pair_index}-{role}",
                        "event_id": f"E{pair_index}",
                        "control_id": f"C{pair_index}",
                        "catalog_role": role,
                        "anchor_year": 2019 + pair_index // 2,
                        "station_id": "B1",
                        "target": "T",
                        "event_type": "high_temperature",
                        "model": "candidate",
                        "training_seed": seed,
                        "window_length": 15,
                        "station": "B1",
                        "event_start": "2019-07-01",
                        "event_end": "2019-07-03",
                        "event_peak_date": "2019-07-02",
                        "event_length": 3,
                        "matched_control_id": f"C{pair_index}",
                        "MAE": mae + offset,
                        "RMSE": mae + 0.1 + offset,
                        "peak_error": mae + offset,
                        "timing_error": mae - 1.0 + offset,
                        "coverage_90": 0.9,
                        "interval_width_90": 2.0,
                    }
                )
    statistics = dataclasses.replace(
        load_frozen_statistics(DESIGN), bootstrap_replicates=30
    )
    result = analyze_event_pairs(pd.DataFrame(rows), statistics)
    mae = result["comparisons"].loc[result["comparisons"]["metric"].eq("MAE")].iloc[0]
    assert mae["event_minus_control"] == pytest.approx(1.0)
    assert mae["ci_lower"] == pytest.approx(1.0)
    assert mae["ci_upper"] == pytest.approx(1.0)
    assert mae["n_event_episodes"] == 3
    assert mae["n_years"] == 2
    assert mae["hypothesis_family"] == "event_vs_matched_control"
    assert result["episodes"]["training_seeds_collapsed_first"].all()
    assert {
        "event_id",
        "station",
        "event_type",
        "event_start",
        "event_end",
        "event_peak_date",
        "event_length",
        "matched_control_id",
        "MAE",
        "peak_error",
        "timing_error",
        "coverage_90",
        "interval_width_90",
    }.issubset(result["episodes"].columns)


def test_resilience_requires_and_summarizes_complete_three_site_powersets() -> None:
    evidence = _evidence()
    sites = ("B1", "B2", "B3")
    failure_sets = [
        tuple(subset)
        for size in range(len(sites) + 1)
        for subset in combinations(sites, size)
    ]
    rows = []
    for target_gap_id, year in (("G1", 2019), ("G2", 2020)):
        for failed in failure_sets:
            failed_label = "+".join(failed)
            for model, seeds in (
                ("climatology", [np.nan]),
                ("candidate", [11, 22]),
            ):
                for training_seed in seeds:
                    rows.append(
                        {
                            **evidence,
                            "experiment": "SCI_NET",
                            "scenario_id": f"{target_gap_id}-{failed_label or 'none'}",
                            "target_gap_id": target_gap_id,
                            "anchor_year": year,
                            "mask_seed": 101,
                            "station_id": "B1",
                            "target_station_id": "B1",
                            "target": "T",
                            "model": model,
                            "training_seed": training_seed,
                            "gap_length": 30,
                            "failed_stations": failed_label,
                            "network_size": 3,
                            "MAE": (
                                2.0
                                if model == "climatology"
                                else 1.0 + 0.1 * len(failed)
                            ),
                        }
                    )
    statistics = dataclasses.replace(
        load_frozen_statistics(DESIGN), bootstrap_replicates=20
    )
    result = analyze_resilience_outputs(pd.DataFrame(rows), statistics)
    candidate_auc = (
        result["auc"]
        .loc[result["auc"]["model"].eq("candidate"), "resilience_auc"]
        .iloc[0]
    )
    assert candidate_auc == pytest.approx(0.85)
    assert set(result["curves"]["failure_count"]) == {0, 1, 2, 3}
    assert set(result["importance"]["failed_station_id"]) == set(sites)
    assert result["failure_sets"]["n_units"].eq(2).all()
    assert set(result["hypotheses"]["hypothesis_family"]) == {"network_failure_set"}
    assert result["hypotheses"]["n_anchor_units"].eq(2).all()

    incomplete = pd.DataFrame(rows).loc[
        lambda frame: (
            ~(
                frame["target_gap_id"].eq("G2")
                & frame["model"].eq("candidate")
                & frame["failed_stations"].eq("B1+B2+B3")
            )
        )
    ]
    with pytest.raises(ValueError, match="incomplete"):
        analyze_resilience_outputs(incomplete, statistics)


def test_calibration_collapses_seeds_and_reports_all_difficulty_axes() -> None:
    evidence = _evidence()
    rows = []
    for scenario_index, (gap, failure_count, event_type) in enumerate(
        ((10, 0, "ordinary"), (30, 1, "high_temperature"))
    ):
        for training_seed in (11, 22):
            width = 1.0 + gap / 30 + failure_count
            rows.append(
                {
                    **evidence,
                    "experiment": "SCI_NET",
                    "scenario_id": f"C{scenario_index}",
                    "training_seed": training_seed,
                    "mask_seed": 101 + scenario_index,
                    "station_id": "B1",
                    "target": "T",
                    "model": "candidate",
                    "gap_length": gap,
                    "failure_count": failure_count,
                    "event_type": event_type,
                    "quality_approved": True,
                    "artificial_mask": True,
                    "y_true": 0.0,
                    "q05": -width,
                    "q95": width,
                }
            )
    result = analyze_calibration(pd.DataFrame(rows))
    assert result["by_gap"]["n_training_seeds"].eq(2).all()
    assert result["by_gap"]["training_seeds_collapsed_first"].all()
    assert set(result["difficulty"]["difficulty_axis"]) == {
        "gap_length",
        "failure_count",
        "event_type",
    }
    assert result["difficulty"]["training_seeds_collapsed_first"].all()


def test_data_version_sensitivity_pairs_separate_bundles_on_persistent_anchors() -> (
    None
):
    statistics = dataclasses.replace(
        load_frozen_statistics(DESIGN), bootstrap_replicates=25
    )
    frames: dict[str, pd.DataFrame] = {}
    for version, version_offset in (
        ("published_v1", 0.0),
        ("no_s2_suspect_v1", 0.5),
    ):
        rows = []
        for anchor_index, anchor in enumerate(("A1", "A2")):
            for seed, seed_offset in ((11, -0.1), (22, 0.1)):
                rows.append(
                    {
                        "data_version": version,
                        "evaluation_split": "development_test",
                        "experiment": "SCI_DENSE",
                        "condition_id": "D30",
                        "scenario_id": f"scenario-{anchor}",
                        "anchor_id": anchor,
                        "anchor_year": 2019 + anchor_index,
                        "mask_seed": 101 + anchor_index,
                        "station_id": "B1",
                        "target": "T",
                        "model": "candidate",
                        "training_seed": seed,
                        "gap_length": 30,
                        "window_length": 368,
                        "MAE": 1.0 + anchor_index + version_offset + seed_offset,
                    }
                )
        frames[version] = pd.DataFrame(rows)
    result = analyze_data_version_sensitivity(
        frames["published_v1"],
        {"no_s2_suspect_v1": frames["no_s2_suspect_v1"]},
        statistics,
    )
    assert len(result) == 1
    row = result.iloc[0]
    assert row["primary_data_version"] == "published_v1"
    assert row["sensitivity_data_version"] == "no_s2_suspect_v1"
    assert row["MAE_difference"] == pytest.approx(0.5)
    assert row["ci_lower"] == pytest.approx(0.5)
    assert row["ci_upper"] == pytest.approx(0.5)
    assert row["n_paired_anchors"] == 2
    assert row["n_years"] == 2
    assert row["hypothesis_family"] == "data_version_sensitivity"
    assert bool(row["training_seeds_collapsed_first"])


def test_separate_frozen_sensitivity_bundles_run_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        frozen_pipeline_module,
        "build_analysis_code_identity",
        _clean_code_identity,
    )
    primary_paths = _write_anchored_bundle(
        tmp_path / "primary", "published_v1", mae_offset=0.0
    )
    sensitivity_paths = [
        _write_anchored_bundle(tmp_path / version, version, mae_offset=offset)
        for version, offset in (
            ("no_s2_suspect_v1", 0.5),
            ("b1_no_level_v1", 0.25),
            ("b1_shift_sensitivity_v1", -0.25),
        )
    ]
    primary = load_frozen_inputs(*primary_paths, DESIGN)
    sensitivities = [
        load_frozen_inputs_from_manifest(paths[2], DESIGN)
        for paths in sensitivity_paths
    ]
    output = tmp_path / "analysis"
    manifest = run_frozen_analysis(
        primary,
        output,
        sensitivity_inputs=sensitivities,
    )
    table = pd.read_csv(output / "data_version_sensitivity.csv")
    assert len(table) == 3
    assert set(table["sensitivity_data_version"]) == {
        "no_s2_suspect_v1",
        "b1_no_level_v1",
        "b1_shift_sensitivity_v1",
    }
    sensitivity_manifest = json.loads(
        (output / "data_version_sensitivity_manifest.json").read_text()
    )
    assert sensitivity_manifest["status"] == "complete"
    assert sensitivity_manifest["available_sensitivity_data_versions"] == [
        "b1_no_level_v1",
        "b1_shift_sensitivity_v1",
        "no_s2_suspect_v1",
    ]
    assert manifest["data_version_inputs"]["no_s2_suspect_v1"]["status"] == (
        "available"
    )
    assert manifest["data_version_inputs"]["b1_no_level_v1"]["status"] == "available"
    assert manifest["status"] == "incomplete"
    assert "recoverability_frontier" in manifest["completion_gate"][
        "unavailable_domains"
    ]


def test_frozen_bundle_rejects_hash_contract_and_completeness_mismatches(
    tmp_path: Path,
) -> None:
    predictions, events, manifest = _write_minimal_bundle(tmp_path)
    loaded = load_frozen_inputs(predictions, events, manifest, DESIGN)
    assert len(loaded.predictions) == 1

    value = json.loads(manifest.read_text())
    value["complete"] = False
    manifest.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="not complete"):
        load_frozen_inputs(predictions, events, manifest, DESIGN)

    predictions, events, manifest = _write_minimal_bundle(tmp_path)
    value = json.loads(manifest.read_text())
    value["predictions_sha256"] = "0" * 64
    manifest.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="content hash"):
        load_frozen_inputs(predictions, events, manifest, DESIGN)

    predictions, events, manifest = _write_minimal_bundle(tmp_path)
    value = json.loads(manifest.read_text())
    value["design_hash"] = "f" * 64
    manifest.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="self-consistent"):
        load_frozen_inputs(predictions, events, manifest, DESIGN)


def test_dynamic_absence_writes_all_outputs_with_explicit_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        frozen_pipeline_module,
        "build_analysis_code_identity",
        _clean_code_identity,
    )
    predictions, events, manifest = _write_minimal_bundle(tmp_path)
    inputs = load_frozen_inputs(predictions, events, manifest, DESIGN)
    sensitivities = [
        load_frozen_inputs_from_manifest(
            _write_anchored_bundle(tmp_path / version, version, mae_offset=0.1)[2],
            DESIGN,
        )
        for version in (
            "no_s2_suspect_v1",
            "b1_no_level_v1",
            "b1_shift_sensitivity_v1",
        )
    ]
    output = tmp_path / "analysis"
    result = run_frozen_analysis(
        inputs, output, sensitivity_inputs=sensitivities
    )
    assert result["status"] == "incomplete"
    assert not result["complete"]
    assert (
        result["information_estimand_contracts"]["operational_dropout"][
            "required_coalition_count"
        ]
        == 16
    )
    assert (
        result["information_estimand_contracts"]["retrained_upper_bound"][
            "required_coalition_count"
        ]
        == 9
    )
    assert not result["information_estimand_contracts"]["retrained_upper_bound"][
        "exact_shapley"
    ]
    assert set(result["artifacts"]) == set(FIXED_ARTIFACTS)
    assert all((output / name).is_file() for name in FIXED_ARTIFACTS)
    assert result["artifacts"]["statistical_frontiers.csv"]["status"] == ("unavailable")
    empty_frontier = pd.read_csv(output / "statistical_frontiers.csv")
    assert empty_frontier.empty
    assert "statistical_frontier_days" in empty_frontier
    assert (
        result["artifacts"]["retrained_information_upper_bounds.csv"]["status"]
        == "unavailable"
    )
    assert (output / "analysis_input_manifest.json").is_file()


def test_analysis_run_fails_before_writing_when_analysis_source_is_dirty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    predictions, events, manifest = _write_minimal_bundle(tmp_path)
    inputs = load_frozen_inputs(predictions, events, manifest, DESIGN)
    dirty = _clean_code_identity()
    dirty.update(
        {
            "status": "dirty",
            "tracked_relevant_source_clean": False,
            "dirty_tracked_paths": ["scripts/09_analyze_results.py"],
        }
    )
    monkeypatch.setattr(
        frozen_pipeline_module,
        "build_analysis_code_identity",
        lambda: dirty,
    )
    output = tmp_path / "must-not-exist"
    with pytest.raises(RuntimeError, match="analysis code identity is not clean"):
        run_frozen_analysis(inputs, output)
    assert not output.exists()


def _completion_frames(*, framework_only: bool) -> dict[str, pd.DataFrame]:
    frames = {
        name: pd.DataFrame({"value": [1.0]}) for name in FIXED_ARTIFACTS
    }
    if framework_only:
        for name in (
            "information_combination_metrics.csv",
            "operational_dropout_gains.csv",
            "retrained_information_upper_bounds.csv",
            "shapley_contributions.csv",
            "information_interactions.csv",
            "calibration_by_gap.csv",
            "calibration_overall.csv",
            "uncertainty_growth.csv",
            "uncertainty_by_difficulty.csv",
        ):
            frames[name] = pd.DataFrame()
        hypothesis_families = [
            "frontier_model_vs_climatology",
            "network_failure_set",
            "event_vs_matched_control",
            "data_version_sensitivity",
        ]
    else:
        frames["information_combination_metrics.csv"] = pd.DataFrame(
            {
                "information_estimand": [
                    "operational_dropout",
                    "retrained_upper_bound",
                ]
            }
        )
        hypothesis_families = list(load_frozen_statistics(DESIGN).hypothesis_families)
    frames["data_version_sensitivity.csv"] = pd.DataFrame(
        {
            "sensitivity_data_version": [
                "no_s2_suspect_v1",
                "b1_no_level_v1",
                "b1_shift_sensitivity_v1",
            ]
        }
    )
    frames["hypothesis_tests.csv"] = pd.DataFrame(
        {
            "hypothesis_family": hypothesis_families,
            "p_value": [0.5] * len(hypothesis_families),
            "p_bh": [0.5] * len(hypothesis_families),
        }
    )
    return frames


def test_completion_gate_requires_every_domain_and_all_sensitivity_versions() -> None:
    statistics = load_frozen_statistics(DESIGN)
    complete = frozen_pipeline_module._analysis_completion_gate(
        _completion_frames(framework_only=False),
        overlap_summary={"status": "ok"},
        statistics=statistics,
        proposed_decision="include_proposed_formally",
        selected_models=["linear", "csdi", "proposed"],
    )
    assert complete["status"] == "complete"
    assert complete["complete"]
    assert complete["unavailable_domains"] == []

    missing_domain = _completion_frames(framework_only=False)
    missing_domain["resilience_auc.csv"] = pd.DataFrame()
    unavailable = frozen_pipeline_module._analysis_completion_gate(
        missing_domain,
        overlap_summary={"status": "ok"},
        statistics=statistics,
        proposed_decision="include_proposed_formally",
        selected_models=["linear", "csdi", "proposed"],
    )
    assert unavailable["status"] == "incomplete"
    assert unavailable["unavailable_domains"] == ["network_resilience"]

    missing_version = _completion_frames(framework_only=False)
    missing_version["data_version_sensitivity.csv"] = missing_version[
        "data_version_sensitivity.csv"
    ].iloc[:2]
    unavailable = frozen_pipeline_module._analysis_completion_gate(
        missing_version,
        overlap_summary={"status": "ok"},
        statistics=statistics,
        proposed_decision="include_proposed_formally",
        selected_models=["linear", "csdi", "proposed"],
    )
    assert "data_version_sensitivity" in unavailable["unavailable_domains"]


def test_framework_only_allows_only_structural_na_and_not_missing_core_domains() -> None:
    statistics = load_frozen_statistics(DESIGN)
    framework = frozen_pipeline_module._analysis_completion_gate(
        _completion_frames(framework_only=True),
        overlap_summary={"status": "ok"},
        statistics=statistics,
        proposed_decision="framework_only",
        selected_models=["linear"],
    )
    assert framework["status"] == "complete"
    assert framework["claim_downgrades"] == [
        "uncertainty_calibration_not_claimed"
    ]
    statuses = {item["domain"]: item["status"] for item in framework["domains"]}
    assert statuses["operational_information"] == "not_applicable"
    assert statuses["retrained_information"] == "not_applicable"
    assert statuses["uncertainty_calibration"] == "not_applicable"
    assert statuses["network_resilience"] == "complete"

    missing_dense = _completion_frames(framework_only=True)
    missing_dense["statistical_frontiers.csv"] = pd.DataFrame()
    failed = frozen_pipeline_module._analysis_completion_gate(
        missing_dense,
        overlap_summary={"status": "ok"},
        statistics=statistics,
        proposed_decision="framework_only",
        selected_models=["linear"],
    )
    assert failed["status"] == "incomplete"
    assert "recoverability_frontier" in failed["unavailable_domains"]


def test_frozen_analysis_rejects_missing_or_duplicate_sensitivity_manifests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        frozen_pipeline_module,
        "build_analysis_code_identity",
        _clean_code_identity,
    )
    primary = load_frozen_inputs(
        *_write_anchored_bundle(
            tmp_path / "primary", "published_v1", mae_offset=0.0
        ),
        DESIGN,
    )
    sensitivities = [
        load_frozen_inputs_from_manifest(
            _write_anchored_bundle(tmp_path / version, version, mae_offset=0.1)[2],
            DESIGN,
        )
        for version in (
            "no_s2_suspect_v1",
            "b1_no_level_v1",
            "b1_shift_sensitivity_v1",
        )
    ]
    output = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="every sensitivity version"):
        run_frozen_analysis(primary, output, sensitivity_inputs=sensitivities[:2])
    assert not output.exists()
    with pytest.raises(ValueError, match="duplicate sensitivity bundle"):
        run_frozen_analysis(
            primary,
            output,
            sensitivity_inputs=[sensitivities[0], sensitivities[0], sensitivities[2]],
        )
    assert not output.exists()


def test_analysis_input_manifest_closes_registry_sources_and_builder_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        frozen_pipeline_module,
        "build_analysis_code_identity",
        _clean_code_identity,
    )
    primary = load_frozen_inputs(
        *_write_anchored_bundle(
            tmp_path / "primary", "published_v1", mae_offset=0.0
        ),
        DESIGN,
    )
    sensitivities = [
        load_frozen_inputs_from_manifest(
            _write_anchored_bundle(tmp_path / version, version, mae_offset=0.1)[2],
            DESIGN,
        )
        for version in (
            "no_s2_suspect_v1",
            "b1_no_level_v1",
            "b1_shift_sensitivity_v1",
        )
    ]
    output = tmp_path / "analysis"
    run_frozen_analysis(primary, output, sensitivity_inputs=sensitivities)
    value = json.loads((output / "analysis_input_manifest.json").read_text())
    assert value["status"] == "complete"
    assert value["registry_count"] == 4
    bundles = [value["bundles"]["primary"], *value["bundles"]["sensitivity"]]
    for bundle in bundles:
        registry = bundle["formal_registry"]
        assert len(registry["registry_file"]["sha256"]) == 64
        assert len(registry["registry_builder_identity"]["sources"]) == 2
        assert registry["source_manifests"]
        assert registry["suite_roles"]


def test_frozen_input_rejects_tampered_registry_source_identity(tmp_path: Path) -> None:
    predictions, events, manifest_path = _write_minimal_bundle(tmp_path)
    aggregate = json.loads(manifest_path.read_text())
    registry_path = Path(aggregate["suite_registry"]["path"])
    registry = json.loads(registry_path.read_text())
    source_path = Path(registry["sources"][0]["manifest"]["path"])
    source_path.write_text(
        source_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="recorded bytes/SHA-256"):
        load_frozen_inputs(predictions, events, manifest_path, DESIGN)


def test_analysis_cli_requires_exactly_three_explicit_sensitivity_manifests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = PROJECT_ROOT / "scripts/09_analyze_results.py"
    specification = importlib.util.spec_from_file_location(
        "frozen_analysis_cli_test", script
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    with pytest.raises(SystemExit) as error:
        module.main(["--sensitivity-manifest", "only-one.json"])
    assert error.value.code == 2

    sentinel = object()
    loaded: list[Path] = []
    monkeypatch.setattr(module, "load_frozen_inputs", lambda *args: sentinel)

    def load_sensitivity(path: Path, _design: Path) -> object:
        loaded.append(path)
        return sentinel

    monkeypatch.setattr(module, "load_frozen_inputs_from_manifest", load_sensitivity)
    monkeypatch.setattr(
        module,
        "run_frozen_analysis",
        lambda *args, **kwargs: {"status": "complete", "artifacts": {}},
    )
    assert (
        module.main(
            [
                "--sensitivity-manifest",
                "no_s2.json",
                "--sensitivity-manifest",
                "no_level.json",
                "--sensitivity-manifest",
                "shift.json",
            ]
        )
        == 0
    )
    assert loaded == [Path("no_s2.json"), Path("no_level.json"), Path("shift.json")]


def test_analysis_code_identity_is_clone_stable_and_audits_git_scope() -> None:
    identity = build_analysis_code_identity(PROJECT_ROOT)
    assert identity["schema_version"] == "analysis_code_identity_v1"
    assert len(identity["relevant_source_digest"]) == 64
    assert identity["relevant_source_file_count"] == 6
    assert [item["path"] for item in identity["files"]] == sorted(
        item["path"] for item in identity["files"]
    )
    assert "git_commit" not in identity
    if identity["status"] != "clean":
        assert (
            identity["dirty_tracked_paths"]
            or identity["relevant_untracked_paths"]
            or identity["missing_paths"]
        )
