"""Hash-bound authorization for development-test formal experiment suites."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from stream_recoverability.masks.anchors import load_frontier_anchor_catalog
from stream_recoverability.masks.event_catalog import (
    event_catalog_sha256,
    load_event_episode_catalog,
)

from .contracts import file_sha256, load_frozen_data_versions
from .model_registry import load_frozen_model_design

if TYPE_CHECKING:
    from stream_recoverability.data.confirmatory import FinalizedModelRoster

FORMAL_EXECUTION_AUTHORIZATION_SCHEMA_VERSION = "formal_execution_authorization_v1"
INTERNAL_STRUCTURAL_BASELINES = ("rating_curve", "independent_flow")
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CANONICAL_FRONTIER_ANCHOR_PATH = (
    REPOSITORY_ROOT / "metadata/frontier_anchors.csv"
).resolve()
CANONICAL_V2_FRONTIER_ANCHOR_PATH = (
    REPOSITORY_ROOT / "metadata/frontier_anchors_v2.csv"
).resolve()
FORMAL_FRONTIER_SUITES = frozenset(
    {
        "core",
        "full",
        "science_dense",
        "science_compensation",
        "science_resilience",
        "retrained_information_upper_bounds",
        "science_donor_falsification",
    }
)
FRONTIER_ANCHORED_MASK_TYPES = frozenset(
    {"async", "block", "station_outage", "matched_network"}
)


def _load_finalized_model_roster(*args: Any, **kwargs: Any) -> Any:
    # data.confirmatory imports experiments.contracts, so this must remain lazy.
    from stream_recoverability.data.confirmatory import load_finalized_model_roster

    return load_finalized_model_roster(*args, **kwargs)


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _resolve_repository_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or candidate.is_file():
        return candidate
    return REPOSITORY_ROOT / candidate


def _validate_frontier_anchor_grid(grid: Any) -> dict[str, Any]:
    if str(grid.suite) not in FORMAL_FRONTIER_SUITES:
        raise ValueError(f"formal authorization does not support suite {grid.suite!r}")
    path_value = grid.frontier_anchor_catalog_path
    digest = grid.frontier_anchor_catalog_sha256
    count = grid.frontier_anchor_count
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("formal suite requires a frozen frontier anchor catalog path")
    path = _resolve_repository_path(path_value)
    if not path.is_file():
        raise FileNotFoundError(f"formal frontier anchor catalog is missing: {path}")
    anchor_versions = {
        str(scenario.condition.anchor_data_version)
        for scenario in grid.scenarios
        if scenario.condition.anchor_data_version is not None
    }
    if len(anchor_versions) != 1:
        raise ValueError("formal grid must carry one frontier anchor data version")
    anchor_version = next(iter(anchor_versions))
    canonical_path = (
        CANONICAL_V2_FRONTIER_ANCHOR_PATH
        if anchor_version == "published_v2"
        else CANONICAL_FRONTIER_ANCHOR_PATH
    )
    if path.resolve() != canonical_path:
        raise ValueError("formal execution must use the canonical frontier catalog")
    if digest != file_sha256(path):
        raise ValueError("formal frontier anchor catalog file SHA-256 mismatch")
    catalog = load_frontier_anchor_catalog(
        path,
        expected_data_version=anchor_version,
        expected_evaluation_split="development_test",
    )
    if isinstance(count, bool) or not isinstance(count, int) or count != len(catalog):
        raise ValueError("formal frontier anchor catalog count mismatch")

    by_id = catalog.set_index("anchor_id", drop=False)
    bindings: list[dict[str, Any]] = []
    for scenario in grid.scenarios:
        condition = scenario.condition
        if str(condition.mask_type) not in FRONTIER_ANCHORED_MASK_TYPES:
            continue
        anchor_id = condition.anchor_id
        if not isinstance(anchor_id, str) or anchor_id not in by_id.index:
            raise ValueError(
                f"formal scenario {scenario.scenario_id} lacks a catalog frontier anchor"
            )
        row = by_id.loc[anchor_id]
        if getattr(row, "ndim", 1) != 1:
            raise ValueError(f"frontier anchor {anchor_id!r} is not unique")
        expected = {
            "station_id": str(condition.station_ids[0]),
            "target": str(condition.anchor_target),
            "mask_seed": int(scenario.mask_seed),
            "center_date": str(condition.center_date),
            "center_index": int(condition.center_index),
            "max_supported_length": int(condition.anchor_max_supported_length),
            "data_version": str(condition.anchor_data_version),
            "evaluation_split": str(condition.anchor_evaluation_split),
            "source_split": str(condition.anchor_source_split),
        }
        observed = {
            "station_id": str(row["station_id"]),
            "target": str(row["target"]),
            "mask_seed": int(row["mask_seed"]),
            "center_date": str(row["center_date"]),
            "center_index": int(row["center_index"]),
            "max_supported_length": int(row["max_supported_length"]),
            "data_version": str(row["data_version"]),
            "evaluation_split": str(row["evaluation_split"]),
            "source_split": str(row["source_split"]),
        }
        if observed != expected:
            raise ValueError(
                f"formal scenario {scenario.scenario_id} frontier binding mismatch"
            )
        bindings.append(
            {
                "scenario_id": str(scenario.scenario_id),
                "condition_id": str(condition.condition_id),
                "mask_seed": int(scenario.mask_seed),
                "anchor_id": anchor_id,
            }
        )
    if not bindings:
        raise ValueError("formal suite contains no catalog-anchored frontier scenarios")
    bindings.sort(
        key=lambda item: (
            item["scenario_id"],
            item["condition_id"],
            item["mask_seed"],
            item["anchor_id"],
        )
    )
    return {
        "frontier_anchor_required": True,
        "frontier_anchor_catalog_path": path_value,
        "frontier_anchor_catalog_sha256": digest,
        "frontier_anchor_count": len(catalog),
        "frontier_anchor_scenario_count": len(bindings),
        "frontier_anchor_bindings_sha256": _canonical_sha256(bindings),
    }


def validate_formal_grid_contract(grid: Any) -> dict[str, Any]:
    """Validate formal-only suite structure that the CLI cannot be trusted to bind."""

    contract = {
        "suite": str(grid.suite),
        **_validate_frontier_anchor_grid(grid),
        "event_uncertainty_required": grid.suite == "full",
    }
    if grid.suite != "full":
        return contract
    path_value = grid.event_catalog_path
    digest = grid.event_catalog_sha256
    analysis_count = grid.event_catalog_analysis_count
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("formal full suite requires a frozen event catalog path")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError("formal full suite requires an event catalog SHA-256")
    if (
        isinstance(analysis_count, bool)
        or not isinstance(analysis_count, int)
        or analysis_count < 1
    ):
        raise ValueError("formal full suite requires analysis-eligible event pairs")
    data_versions = {str(condition.data_version) for condition in grid.conditions}
    evaluation_splits = {
        str(condition.evaluation_split) for condition in grid.conditions
    }
    if len(data_versions) != 1 or len(evaluation_splits) != 1:
        raise ValueError("formal full grid mixes data versions or evaluation splits")
    catalog = load_event_episode_catalog(
        path_value,
        expected_data_version=next(iter(data_versions)),
        expected_evaluation_split=next(iter(evaluation_splits)),
    )
    observed_digest = event_catalog_sha256(catalog)
    eligible_count = int(catalog["analysis_eligible"].sum())
    if observed_digest != digest or eligible_count != analysis_count:
        raise ValueError("formal full grid event catalog identity/count mismatch")
    if len(catalog) != grid.event_catalog_episode_count:
        raise ValueError("formal full grid event catalog episode count mismatch")

    m7a = tuple(
        scenario
        for scenario in grid.scenarios
        if scenario.condition.experiment == "M7a"
    )
    if len(m7a) != 12 or {scenario.mask_seed for scenario in m7a} != {0}:
        raise ValueError(
            "formal full grid must retain exactly twelve seed-0 M7a stresses"
        )
    m7b = tuple(
        scenario
        for scenario in grid.scenarios
        if scenario.condition.experiment == "M7b"
    )
    if len(m7b) != 2 * eligible_count or {scenario.mask_seed for scenario in m7b} != {
        0
    }:
        raise ValueError(
            "formal full grid M7b inventory must be two seed-0 scenarios per eligible pair"
        )
    pairs: dict[str, set[str]] = {}
    for scenario in m7b:
        condition = scenario.condition
        if not condition.pair_id or condition.analysis_eligible is not True:
            raise ValueError("formal M7b scenario lacks an eligible pair identity")
        pairs.setdefault(str(condition.pair_id), set()).add(str(condition.catalog_role))
    if len(pairs) != eligible_count or any(
        roles != {"event_episode", "matched_control"} for roles in pairs.values()
    ):
        raise ValueError("formal M7b event/control pair inventory is incomplete")
    return {
        **contract,
        "event_catalog_path": path_value,
        "event_catalog_sha256": digest,
        "event_catalog_episode_count": len(catalog),
        "event_catalog_analysis_count": eligible_count,
        "m7a_scenario_count": len(m7a),
        "m7b_scenario_count": len(m7b),
    }


def _load_authorizing_roster(
    roster_path: str | Path,
    *,
    design_path: str | Path,
    study_manifest_path: str | Path,
    experiment_config_path: str | Path,
    selection_data_version_manifest_path: str | Path,
) -> FinalizedModelRoster:
    selection_data_version = load_frozen_data_versions(design_path).primary
    roster = _load_finalized_model_roster(
        roster_path,
        design_path=design_path,
        study_manifest_path=study_manifest_path,
        experiment_config_path=experiment_config_path,
        selection_data_version=selection_data_version,
        selection_data_version_manifest_path=selection_data_version_manifest_path,
    )
    design = load_frozen_model_design(design_path)
    selected = tuple(roster.selected_models)
    if set(selected).intersection(INTERNAL_STRUCTURAL_BASELINES):
        raise ValueError("F-only structural baselines must not appear in the T roster")
    unauthorized = sorted(set(selected).difference(design.formal_candidates))
    if unauthorized:
        raise ValueError(
            f"finalized roster contains models outside the frozen design: {unauthorized}"
        )
    missing_structural = sorted(
        set(INTERNAL_STRUCTURAL_BASELINES).difference(design.formal_candidates)
    )
    if missing_structural:
        raise ValueError(
            f"design freeze omits internal structural baselines: {missing_structural}"
        )
    return roster


def _authorization(
    roster: FinalizedModelRoster,
    *,
    suite: str,
    expected_models: Sequence[str],
    target_scope: Sequence[str],
    model_scope: str,
) -> dict[str, Any]:
    models = tuple(str(value) for value in expected_models)
    if not models or len(set(models)) != len(models):
        raise ValueError("formal authorization requires unique expected models")
    return {
        "schema_version": FORMAL_EXECUTION_AUTHORIZATION_SCHEMA_VERSION,
        "suite": str(suite),
        "formal_evidence": True,
        "model_scope": model_scope,
        "target_scope": list(dict.fromkeys(str(value) for value in target_scope)),
        "expected_models": list(models),
        "finalized_model_roster": {
            "path": roster.manifest_path,
            "sha256": roster.manifest_sha256,
            "selected_models": list(roster.selected_models),
            "best_traditional_model": roster.best_traditional_model,
            "proposed_decision": roster.proposed_decision,
            "selection_data_version": roster.selection_data_version,
            "selection_design_hash": roster.selection_design_hash,
            "selection_contract": json.loads(json.dumps(roster.selection_contract)),
            "selection_data_version_manifest": json.loads(
                json.dumps(roster.selection_data_version_manifest)
            ),
            "validation_anchor_catalog": json.loads(
                json.dumps(roster.validation_anchor_catalog)
            ),
        },
    }


def authorize_roster_suite(
    roster_path: str | Path,
    *,
    suite: str,
    target_scope: Sequence[str],
    design_path: str | Path,
    study_manifest_path: str | Path,
    experiment_config_path: str | Path,
    selection_data_version_manifest_path: str | Path,
) -> tuple[tuple[str, ...], dict[str, Any]]:
    """Authorize the exact T roster plus fixed F/L structural baselines."""

    roster = _load_authorizing_roster(
        roster_path,
        design_path=design_path,
        study_manifest_path=study_manifest_path,
        experiment_config_path=experiment_config_path,
        selection_data_version_manifest_path=selection_data_version_manifest_path,
    )
    targets = tuple(dict.fromkeys(str(value) for value in target_scope))
    if not targets or not set(targets).issubset({"T", "F", "L"}):
        raise ValueError(f"formal suite has unsupported target scope: {targets}")
    models = tuple(roster.selected_models)
    model_scope = "t_roster_exact"
    if set(targets).intersection({"F", "L"}):
        models = (*models, *INTERNAL_STRUCTURAL_BASELINES)
        model_scope = "t_roster_plus_internal_structural_baselines"
    return models, _authorization(
        roster,
        suite=suite,
        expected_models=models,
        target_scope=targets,
        model_scope=model_scope,
    )


def authorize_proposed_estimand(
    roster_path: str | Path,
    *,
    suite: str,
    design_path: str | Path,
    study_manifest_path: str | Path,
    experiment_config_path: str | Path,
    selection_data_version_manifest_path: str | Path,
) -> tuple[FinalizedModelRoster, dict[str, Any] | None]:
    """Authorize a proposed-only estimand or return explicit non-applicability."""

    roster = _load_authorizing_roster(
        roster_path,
        design_path=design_path,
        study_manifest_path=study_manifest_path,
        experiment_config_path=experiment_config_path,
        selection_data_version_manifest_path=selection_data_version_manifest_path,
    )
    return roster, proposed_estimand_authorization(roster, suite=suite)


def proposed_estimand_authorization(
    roster: FinalizedModelRoster, *, suite: str
) -> dict[str, Any] | None:
    """Build execution metadata from an already hash-validated roster."""

    if roster.proposed_decision == "framework_only":
        return None
    if (
        roster.proposed_decision != "include_proposed_formally"
        or "proposed" not in roster.selected_models
    ):
        raise ValueError("finalized roster does not authorize proposed-model evidence")
    return _authorization(
        roster,
        suite=suite,
        expected_models=("proposed",),
        target_scope=("T",),
        model_scope="authorized_proposed_estimand",
    )


def validate_formal_authorization(
    value: Mapping[str, Any],
    *,
    expected_suite: str,
    expected_models: Sequence[str],
    design_path: str | Path,
    study_manifest_path: str | Path,
    experiment_config_path: str | Path,
) -> dict[str, Any]:
    """Validate the in-memory authorization before a runner can claim evidence."""

    document = json.loads(json.dumps(dict(value)))
    if document.get("schema_version") != FORMAL_EXECUTION_AUTHORIZATION_SCHEMA_VERSION:
        raise ValueError("formal execution authorization schema is not frozen")
    if document.get("formal_evidence") is not True:
        raise ValueError(
            "formal execution authorization must declare formal_evidence=true"
        )
    if document.get("suite") != expected_suite:
        raise ValueError("formal execution authorization is bound to another suite")
    models = document.get("expected_models")
    if models != list(expected_models):
        raise ValueError(
            "runner models differ from finalized formal authorization: "
            f"observed={list(expected_models)}, expected={models}"
        )
    roster = document.get("finalized_model_roster")
    if not isinstance(roster, Mapping):
        raise TypeError("formal authorization lacks finalized_model_roster")
    selected = roster.get("selected_models")
    decision = roster.get("proposed_decision")
    digest = roster.get("sha256")
    if (
        not isinstance(selected, list)
        or not selected
        or len(set(selected)) != len(selected)
        or decision not in {"include_proposed_formally", "framework_only"}
        or ("proposed" in selected) != (decision == "include_proposed_formally")
    ):
        raise ValueError("formal authorization contains an inconsistent roster")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError("formal authorization roster lacks lowercase SHA-256")
    roster_path_value = roster.get("path")
    if not isinstance(roster_path_value, str) or not roster_path_value:
        raise ValueError("formal authorization roster lacks a path")
    roster_path = Path(roster_path_value)
    if not roster_path.is_absolute():
        roster_path = REPOSITORY_ROOT / roster_path
    selection_manifest = roster.get("selection_data_version_manifest")
    if not isinstance(selection_manifest, Mapping):
        raise TypeError("formal authorization lacks selection data-version manifest")
    selection_path_value = selection_manifest.get("path")
    if not isinstance(selection_path_value, str) or not selection_path_value:
        raise ValueError("formal authorization selection manifest lacks a path")
    selection_path = Path(selection_path_value)
    if not selection_path.is_absolute():
        selection_path = REPOSITORY_ROOT / selection_path
    selection_data_version = load_frozen_data_versions(design_path).primary
    reloaded = _load_finalized_model_roster(
        roster_path,
        design_path=design_path,
        study_manifest_path=study_manifest_path,
        experiment_config_path=experiment_config_path,
        selection_data_version=selection_data_version,
        selection_data_version_manifest_path=selection_path,
    )
    reloaded_fields = {
        "sha256": reloaded.manifest_sha256,
        "selected_models": list(reloaded.selected_models),
        "best_traditional_model": reloaded.best_traditional_model,
        "proposed_decision": reloaded.proposed_decision,
        "selection_data_version": reloaded.selection_data_version,
        "selection_design_hash": reloaded.selection_design_hash,
        "selection_contract": reloaded.selection_contract,
        "selection_data_version_manifest": reloaded.selection_data_version_manifest,
        "validation_anchor_catalog": reloaded.validation_anchor_catalog,
    }
    mismatches = {
        field: (roster.get(field), expected)
        for field, expected in reloaded_fields.items()
        if roster.get(field) != expected
    }
    if mismatches:
        raise ValueError(f"formal authorization roster metadata mismatch: {mismatches}")
    allowed = set(selected) | set(INTERNAL_STRUCTURAL_BASELINES)
    if document.get("model_scope") == "authorized_proposed_estimand":
        allowed = {"proposed"}
        if decision != "include_proposed_formally":
            raise ValueError("framework-only roster cannot authorize proposed estimand")
    unauthorized = sorted(set(expected_models).difference(allowed))
    if unauthorized:
        raise ValueError(
            f"authorization expected_models are outside roster: {unauthorized}"
        )
    return document


__all__ = [
    "FORMAL_EXECUTION_AUTHORIZATION_SCHEMA_VERSION",
    "INTERNAL_STRUCTURAL_BASELINES",
    "authorize_proposed_estimand",
    "authorize_roster_suite",
    "proposed_estimand_authorization",
    "validate_formal_authorization",
    "validate_formal_grid_contract",
]
