from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import stream_recoverability.experiments.formal_authorization as authorization_module
from stream_recoverability.experiments.formal_authorization import (
    proposed_estimand_authorization,
    validate_formal_authorization,
    validate_formal_grid_contract,
)
from stream_recoverability.experiments.grid import build_experiment_grid
from stream_recoverability.experiments.validation import (
    validation_anchor_catalog_identity,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
STUDY_MANIFEST = REPOSITORY_ROOT / "study_manifest.yaml"
EXPERIMENT_CONFIG = REPOSITORY_ROOT / "configs/experiments.yaml"
DESIGN = REPOSITORY_ROOT / "configs/design_freeze_v1.yaml"
EVENT_CATALOG = REPOSITORY_ROOT / "metadata/event_episode_catalog.csv"


def _grid(*, suite: str, event_catalog: Path | None = None):
    return build_experiment_grid(
        STUDY_MANIFEST,
        EXPERIMENT_CONFIG,
        suite=suite,
        data_version="published_v1",
        evaluation_split="development_test",
        event_catalog_path=event_catalog,
    )


def _roster(tmp_path: Path, *, decision: str = "include_proposed_formally"):
    path = tmp_path / "finalized_model_roster.json"
    path.write_text("{}\n", encoding="utf-8")
    selected = ("linear", "proposed") if decision != "framework_only" else ("linear",)
    return SimpleNamespace(
        manifest_path=str(path),
        manifest_sha256="a" * 64,
        selected_models=selected,
        best_traditional_model="linear",
        proposed_decision=decision,
        selection_data_version="published_v1",
        selection_design_hash="b" * 64,
        selection_contract={"evaluation_split": "validation"},
        selection_data_version_manifest={
            "path": "data_versions/published_v1/version_manifest.json",
            "sha256": "c" * 64,
            "bytes": 1,
        },
        validation_anchor_catalog=validation_anchor_catalog_identity(),
    )


def test_core_formal_grid_is_bound_to_canonical_frontier_catalog() -> None:
    grid = _grid(suite="core")

    contract = validate_formal_grid_contract(grid)

    assert contract["suite"] == "core"
    assert contract["frontier_anchor_required"] is True
    assert contract["frontier_anchor_count"] == 180
    assert contract["frontier_anchor_scenario_count"] > 0
    assert len(contract["frontier_anchor_bindings_sha256"]) == 64

    with pytest.raises(ValueError, match="frontier anchor catalog path"):
        validate_formal_grid_contract(
            replace(grid, frontier_anchor_catalog_path=None)
        )

    position, first = next(
        (position, scenario)
        for position, scenario in enumerate(grid.scenarios)
        if scenario.condition.anchor_id is not None
    )
    tampered = replace(
        grid,
        scenarios=(
            *grid.scenarios[:position],
            replace(first, condition=replace(first.condition, anchor_id="unknown")),
            *grid.scenarios[position + 1 :],
        ),
    )
    with pytest.raises(ValueError, match="lacks a catalog frontier anchor"):
        validate_formal_grid_contract(tampered)


def test_full_formal_grid_closes_exact_event_inventory() -> None:
    grid = _grid(suite="full", event_catalog=EVENT_CATALOG)

    contract = validate_formal_grid_contract(grid)

    assert contract["event_uncertainty_required"] is True
    assert contract["m7a_scenario_count"] == 12
    assert contract["m7b_scenario_count"] == 2 * contract[
        "event_catalog_analysis_count"
    ]
    assert contract["event_catalog_analysis_count"] > 0

    with pytest.raises(ValueError, match="event catalog path"):
        validate_formal_grid_contract(replace(grid, event_catalog_path=None))


def test_authorization_reopens_roster_and_rejects_stale_anchor_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roster = _roster(tmp_path)
    document = proposed_estimand_authorization(
        roster, suite="science_compensation"
    )
    assert document is not None
    monkeypatch.setattr(
        authorization_module,
        "_load_finalized_model_roster",
        lambda *_args, **_kwargs: roster,
    )

    validated = validate_formal_authorization(
        document,
        expected_suite="science_compensation",
        expected_models=("proposed",),
        design_path=DESIGN,
        study_manifest_path=STUDY_MANIFEST,
        experiment_config_path=EXPERIMENT_CONFIG,
    )
    assert validated == document

    stale = json.loads(json.dumps(document))
    stale["finalized_model_roster"]["validation_anchor_catalog"]["sha256"] = (
        "0" * 64
    )
    with pytest.raises(ValueError, match="roster metadata mismatch"):
        validate_formal_authorization(
            stale,
            expected_suite="science_compensation",
            expected_models=("proposed",),
            design_path=DESIGN,
            study_manifest_path=STUDY_MANIFEST,
            experiment_config_path=EXPERIMENT_CONFIG,
        )


def test_framework_only_roster_cannot_authorize_proposed_estimand(
    tmp_path: Path,
) -> None:
    roster = _roster(tmp_path, decision="framework_only")

    assert (
        proposed_estimand_authorization(
            roster, suite="science_compensation"
        )
        is None
    )
