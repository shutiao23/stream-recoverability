from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml

from stream_recoverability.data.confirmatory import (
    CONFIRMATORY_DATA_VERSION,
    FROZEN_PERIODS,
    FROZEN_SITE_IDS,
    FROZEN_VARIABLES,
    FinalizedModelRoster,
    load_confirmatory_protocol,
)
from stream_recoverability.experiments import external_confirmation as external
from stream_recoverability.experiments.external_confirmation import (
    EXTERNAL_EVIDENCE_ROLE,
    EXTERNAL_INFORMATION_CONDITIONS,
    EXTERNAL_MASK_SEED,
    ConfirmatoryEvaluationInputs,
    ExternalConfirmationRunner,
    build_external_confirmation_grid,
    run_confirmatory_evaluation,
    run_confirmatory_feasibility,
)
from stream_recoverability.experiments.grid import build_experiment_grid
from stream_recoverability.experiments.model_registry import (
    load_frozen_model_design,
)
from stream_recoverability.experiments.runner import (
    CONFIRMATORY_ONCE_PATH_REQUIRED,
    ExperimentRunner,
)
from stream_recoverability.experiments.validation import (
    validation_anchor_catalog_identity,
)
from stream_recoverability.models.proposed import require_main_rs_architecture

DESIGN = Path("configs/design_freeze_v2.yaml")
STUDY_MANIFEST = Path("study_manifest.yaml")
EXPERIMENT_CONFIG = Path("configs/experiments.yaml")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _roster(
    tmp_path: Path,
    *,
    selected_models: tuple[str, ...] = ("linear",),
    best_traditional: str = "linear",
    proposed_decision: str = "framework_only",
) -> FinalizedModelRoster:
    manifest = tmp_path / "finalized_model_roster.json"
    manifest.write_text("{}\n", encoding="utf-8")
    code_identity = {
        "schema_version": "code_provenance_v1",
        "relevant_source_digest": "c" * 64,
        "relevant_source_file_count": 42,
    }
    return FinalizedModelRoster(
        manifest_path=str(manifest),
        manifest_sha256=_sha256(manifest),
        selected_models=selected_models,
        best_traditional_model=best_traditional,
        proposed_decision=proposed_decision,
        selection_data_version="published_v1",
        selection_design_hash="v" * 64,
        selection_contract={
            "evaluation_split": "validation",
            "data_version": "published_v1",
            "code_identity": code_identity,
        },
        selection_code_provenance=None,
        selection_data_version_manifest={
            "path": "data_versions/published_v1/version_manifest.json",
            "sha256": "s" * 64,
            "bytes": 1,
        },
        validation_anchor_catalog=validation_anchor_catalog_identity(
            require_canonical_path=True
        ),
        artifacts={},
    )


def test_external_grid_is_exact_compact_frozen_design() -> None:
    grid = build_external_confirmation_grid(training_seeds=(11, 22, 33, 44, 55))

    assert len(grid.conditions) == len(grid.scenarios) == 60
    assert grid.mask_seeds == (EXTERNAL_MASK_SEED,)
    assert grid.training_seeds == (11, 22, 33, 44, 55)
    assert grid.condition_counts == {
        "EXT_BLOCK": 30,
        "EXT_POINT": 10,
        "EXT_STATION_OUTAGE": 20,
    }
    assert {condition.evaluation_split for condition in grid.conditions} == {
        "confirmatory"
    }
    assert {condition.data_version for condition in grid.conditions} == {
        CONFIRMATORY_DATA_VERSION
    }
    assert {
        external._information_condition(condition) for condition in grid.conditions
    } == set(EXTERNAL_INFORMATION_CONDITIONS)
    assert {
        condition.missing_rate
        for condition in grid.conditions
        if condition.mask_type == "point"
    } == {0.30}
    assert {
        condition.gap_length
        for condition in grid.conditions
        if condition.mask_type == "block"
    } == {30, 90, 180}
    assert {
        condition.gap_length
        for condition in grid.conditions
        if condition.mask_type == "station_outage"
    } == {90, 180}
    assert all(
        condition.evaluation_variables == ("T",) for condition in grid.conditions
    )


@pytest.mark.parametrize(
    ("information_condition", "expected_auxiliary_cells"),
    (("full_information", 0), ("no_meteorology", 25)),
)
def test_external_runner_masks_group_d_only_on_target_gap_dates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    information_condition: str,
    expected_auxiliary_cells: int,
) -> None:
    grid = build_external_confirmation_grid(training_seeds=(11,))
    scenario = next(
        value
        for value in grid.scenarios
        if external._information_condition(value.condition) == information_condition
        and value.condition.mask_type == "block"
    )
    dates = pd.date_range("2023-01-01", periods=3, freq="D")
    variables = tuple(FROZEN_VARIABLES)
    values = np.ones((3, len(FROZEN_SITE_IDS), len(variables)), dtype=np.float32)
    base_mask = np.zeros_like(values, dtype=bool)
    station_index = FROZEN_SITE_IDS.index(scenario.condition.station_ids[0])
    base_mask[1, station_index, variables.index("T")] = True

    def base_generate(
        _runner: ExperimentRunner, _scenario: Any
    ) -> tuple[np.ndarray, dict[str, Any]]:
        return base_mask.copy(), {"scenario_id": _scenario.scenario_id}

    monkeypatch.setattr(ExperimentRunner, "_generate_mask", base_generate)
    runner = object.__new__(ExternalConfirmationRunner)
    runner.data = SimpleNamespace(
        dates=dates,
        station_ids=tuple(FROZEN_SITE_IDS),
        variable_names=variables,
        values=values,
        natural_observed=np.ones_like(values, dtype=bool),
        quality_approved=np.ones_like(values, dtype=bool),
    )
    runner.mask_dir = tmp_path / "masks"
    runner._validate_scenario_mask = lambda *_args, **_kwargs: None

    mask, metadata = runner._generate_mask(scenario)

    meteorology = [variables.index(value) for value in external.METEOROLOGY_VARIABLES]
    assert int(mask[:, :, meteorology].sum()) == expected_auxiliary_cells
    assert metadata["information_condition"] == information_condition
    assert metadata["auxiliary_meteorology_masked_cells"] == expected_auxiliary_cells
    if information_condition == "no_meteorology":
        assert mask[1, :, meteorology].all()
        assert not mask[[0, 2], :, :][:, :, meteorology].any()


def test_artifact_inventory_rejects_tampering_and_unexpected_files(
    tmp_path: Path,
) -> None:
    identities: dict[str, dict[str, Any]] = {}
    for name in sorted(external.REQUIRED_DATA_ARTIFACTS):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode("utf-8"))
        identities[name] = {"sha256": _sha256(path), "bytes": path.stat().st_size}
    manifest = {"artifacts": identities}

    assert set(external._validate_artifact_inventory(tmp_path, manifest)) == set(
        identities
    )
    (tmp_path / "daily_wide.parquet").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="byte count mismatch|SHA-256 mismatch"):
        external._validate_artifact_inventory(tmp_path, manifest)
    (tmp_path / "daily_wide.parquet").write_bytes(b"daily_wide.parquet")
    (tmp_path / "unexpected.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory is not exact"):
        external._validate_artifact_inventory(tmp_path, manifest)


def test_complete_external_tables_enforce_dates_splits_and_grid(
    tmp_path: Path,
) -> None:
    dates = pd.date_range(FROZEN_PERIODS[0][1], FROZEN_PERIODS[-1][2], freq="D")
    splits = external._expected_split(dates)
    wide = pd.DataFrame(
        {
            "date": dates,
            "split": splits,
            "data_version": CONFIRMATORY_DATA_VERSION,
            "is_external_validation": True,
        }
    )
    for site_id in FROZEN_SITE_IDS:
        for variable in FROZEN_VARIABLES:
            wide[f"{site_id}_{variable}"] = 1.0
    wide.to_parquet(tmp_path / "daily_wide.parquet", index=False)

    index = pd.MultiIndex.from_product(
        [dates, FROZEN_SITE_IDS, FROZEN_VARIABLES],
        names=["date", "site_id", "variable"],
    )
    long = index.to_frame(index=False)
    long["value"] = 1.0
    long["split"] = external._expected_split(long["date"])
    long["data_version"] = CONFIRMATORY_DATA_VERSION
    long["natural_observed"] = True
    long["quality_approved"] = True
    long["is_external_validation"] = True
    long["external_evidence_role"] = long["split"].map(
        {
            "train": "external_model_fitting_only",
            "validation": "external_early_stopping_only",
            "confirmatory": "locked_confirmatory_evaluation_only",
        }
    )
    long.to_parquet(tmp_path / "daily_long.parquet", index=False)
    split_root = tmp_path / "splits"
    split_root.mkdir()
    split_counts: dict[str, int] = {}
    for label, _, _ in FROZEN_PERIODS:
        selected = wide.loc[wide["split"] == label].copy()
        selected.to_parquet(split_root / f"{label}.parquet", index=False)
        split_counts[label] = len(selected)
    manifest = {
        "output_counts": {
            "wide_rows": len(wide),
            "long_rows": len(long),
            "split_wide_rows": split_counts,
        }
    }

    _, _, counts = external._validate_complete_tables(tmp_path, manifest)

    assert counts["wide_rows"] == len(dates)
    assert counts["long_rows"] == len(dates) * 5 * 8
    broken = long.iloc[:-1].copy()
    broken.to_parquet(tmp_path / "daily_long.parquet", index=False)
    with pytest.raises(ValueError, match="complete date/site/variable grid"):
        external._validate_complete_tables(tmp_path, manifest)


def test_data_access_gate_is_bound_to_exact_roster(tmp_path: Path) -> None:
    protocol = load_confirmatory_protocol(DESIGN)
    roster = _roster(tmp_path)
    manifest = {
        "schema_version": external.CONFIRMATORY_SCHEMA_VERSION,
        "data_version": CONFIRMATORY_DATA_VERSION,
        "immutable": True,
        "design_version": protocol.design_version,
        "design_sha256": protocol.design_sha256,
        "protocol": protocol.metadata(),
        "confirmatory_evaluation_executed": False,
        "performance_metrics_computed": False,
        "quality_summary": {"performance_metrics_computed": False},
        "confirmatory_access_gate": roster.metadata(),
    }

    external._validate_access_gate(manifest, roster, protocol)
    manifest["confirmatory_access_gate"]["manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="supplied frozen roster"):
        external._validate_access_gate(manifest, roster, protocol)


@pytest.mark.parametrize(
    "selected_models",
    (("brits_lite",), ("rating_curve",), ("independent_flow",)),
)
def test_selected_models_must_be_formal_and_support_target_t(
    tmp_path: Path, selected_models: tuple[str, ...]
) -> None:
    roster = _roster(
        tmp_path,
        selected_models=selected_models,
        best_traditional=selected_models[0],
    )
    design = load_frozen_model_design(DESIGN)

    with pytest.raises(ValueError, match="non-formal|target T"):
        external._validate_selected_models(roster, design)


def _fake_inputs(tmp_path: Path) -> ConfirmatoryEvaluationInputs:
    roster = _roster(tmp_path)
    data_root = tmp_path / "external-data"
    data_root.mkdir()
    data_manifest = data_root / "provenance_manifest.json"
    wide = data_root / "daily_wide.parquet"
    long = data_root / "daily_long.parquet"
    data_manifest.write_text("{}\n", encoding="utf-8")
    wide.write_bytes(b"wide")
    long.write_bytes(b"long")
    code_identity = roster.selection_contract["code_identity"]
    contract = {
        "design_version": "design_freeze_v2",
        "design_hash": "d" * 64,
        "data_version": CONFIRMATORY_DATA_VERSION,
        "evaluation_split": "confirmatory",
        "mask_schema_version": "mask_schema_v2",
        "model_schema_version": "model_schema_v2",
        "statistics_schema_version": "statistics_schema_v2",
        "input_digests": {},
        "code_identity": code_identity,
    }
    return ConfirmatoryEvaluationInputs(
        protocol=load_confirmatory_protocol(DESIGN),
        roster=roster,
        model_design=load_frozen_model_design(DESIGN),
        selected_models=("linear",),
        training_seeds=(11, 22, 33, 44, 55),
        data_root=data_root,
        data_manifest_path=data_manifest,
        wide_path=wide,
        long_path=long,
        data_manifest_identity={
            "manifest_sha256": _sha256(data_manifest),
            "manifest_bytes": data_manifest.stat().st_size,
            "artifact_count": 2,
            "counts": {},
        },
        evidence_contract=contract,
        code_provenance={
            **code_identity,
            "git_commit": "g" * 40,
            "relevant_source_clean": True,
            "status": "clean",
        },
    )


class _SuccessfulFakeRunner:
    def __init__(self, grid: Any, **kwargs: Any) -> None:
        self.grid = grid
        self.output_dir = Path(kwargs["output_dir"])
        self.mask_dir = Path(kwargs["mask_dir"])
        self.evidence_contract = _FAKE_INPUTS.evidence_contract

    def run(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        rows: list[dict[str, Any]] = []
        for scenario in self.grid.scenarios:
            self.mask_dir.joinpath("scenarios").mkdir(parents=True, exist_ok=True)
            (self.mask_dir / "scenarios" / f"{scenario.scenario_id}.npz").write_bytes(
                scenario.scenario_id.encode("utf-8")
            )
            (self.mask_dir / "scenarios" / f"{scenario.scenario_id}.json").write_text(
                json.dumps({"scenario_id": scenario.scenario_id}), encoding="utf-8"
            )
            rows.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "model": "linear",
                    "training_seed": None,
                    "mask_seed": EXTERNAL_MASK_SEED,
                    "station_id": scenario.condition.station_ids[0],
                    "target": "T",
                    "data_version": CONFIRMATORY_DATA_VERSION,
                    "design_hash": self.evidence_contract["design_hash"],
                    "evaluation_split": "confirmatory",
                    "evidence_role": EXTERNAL_EVIDENCE_ROLE,
                }
            )
        daily = pd.DataFrame(
            [
                {
                    **row,
                    "date": pd.Timestamp("2023-01-01"),
                    "y_true": 1.0,
                    "y_pred": 1.1,
                }
                for row in rows
            ]
        )
        events = pd.DataFrame([{**row, "MAE": 0.1, "RMSE": 0.1} for row in rows])
        expected = sorted(
            f"{scenario.scenario_id}|linear:none" for scenario in self.grid.scenarios
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "suite": "external_confirmation",
            "grid_scenario_count": len(self.grid.scenarios),
            "selected_scenarios": len(self.grid.scenarios),
            "data_version": CONFIRMATORY_DATA_VERSION,
            "evaluation_split": "confirmatory",
            "evidence_role": EXTERNAL_EVIDENCE_ROLE,
            "design_hash": self.evidence_contract["design_hash"],
            "expected_run_unit_keys": expected,
            "run_unit_complete": True,
            "evidence_complete": True,
            "finite_predictions": True,
            "finite_event_metrics": True,
            "checkpoint_contract_complete": True,
            "formal_training_seed_complete": True,
            "retryable_run_unit_count": 0,
            "structural_skip_run_unit_count": 0,
            "training_checkpoints": [],
        }
        (self.output_dir / "run_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return daily, events


_FAKE_INPUTS: ConfirmatoryEvaluationInputs


def test_evaluate_once_execution_is_atomic_and_identity_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global _FAKE_INPUTS
    _FAKE_INPUTS = _fake_inputs(tmp_path)
    monkeypatch.setattr(
        external, "preflight_confirmatory_evaluation", lambda **_kwargs: _FAKE_INPUTS
    )
    monkeypatch.setattr(
        external,
        "assert_confirmatory_masks_constructable",
        lambda **_kwargs: pd.DataFrame(),
    )
    output = tmp_path / "published" / "external_confirmation"
    lock = external.confirmatory_once_lock_path(_FAKE_INPUTS.data_root)

    manifest = run_confirmatory_evaluation(
        data_root=_FAKE_INPUTS.data_root,
        finalized_model_roster_path=_FAKE_INPUTS.roster.manifest_path,
        output_dir=output,
        once_lock_path=lock,
        design_path=DESIGN,
        study_manifest_path=STUDY_MANIFEST,
        experiment_config_path=EXPERIMENT_CONFIG,
        runner_factory=_SuccessfulFakeRunner,
    )

    assert manifest["complete"] is True
    assert manifest["completed_run_unit_count"] == 60
    assert output.is_dir()
    assert not list(output.parent.glob(".external_confirmation.staging.*"))
    assert json.loads(lock.read_text(encoding="utf-8"))["status"] == "complete"
    completion = json.loads(
        (output / "completion_manifest.json").read_text(encoding="utf-8")
    )
    assert completion["grid"]["scenario_count"] == 60
    assert completion["model_selection_on_confirmatory"] is False
    daily = pd.read_parquet(output / "daily_predictions.parquet")
    events = pd.read_parquet(output / "event_metrics.parquet")
    for frame in (daily, events):
        assert external.REQUIRED_ROW_IDENTITY_FIELDS.issubset(frame.columns)
        assert frame["formal_evidence"].all()
        assert set(frame["evidence_role"]) == {EXTERNAL_EVIDENCE_ROLE}
        assert frame["run_unit_sha256"].str.len().eq(64).all()
        assert frame["mask_sha256"].str.len().eq(64).all()
    with pytest.raises(FileExistsError, match="existing confirmatory output"):
        run_confirmatory_evaluation(
            data_root=_FAKE_INPUTS.data_root,
            finalized_model_roster_path=_FAKE_INPUTS.roster.manifest_path,
            output_dir=output,
            once_lock_path=lock,
            runner_factory=_SuccessfulFakeRunner,
        )


def test_failed_execution_keeps_nonretryable_once_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global _FAKE_INPUTS
    _FAKE_INPUTS = _fake_inputs(tmp_path)
    monkeypatch.setattr(
        external, "preflight_confirmatory_evaluation", lambda **_kwargs: _FAKE_INPUTS
    )
    monkeypatch.setattr(
        external,
        "assert_confirmatory_masks_constructable",
        lambda **_kwargs: pd.DataFrame(),
    )

    class FailingRunner(_SuccessfulFakeRunner):
        def run(self) -> tuple[pd.DataFrame, pd.DataFrame]:
            raise RuntimeError("synthetic execution failure")

    output = tmp_path / "failed-output"
    lock = external.confirmatory_once_lock_path(_FAKE_INPUTS.data_root)
    with pytest.raises(RuntimeError, match="synthetic execution failure"):
        run_confirmatory_evaluation(
            data_root=_FAKE_INPUTS.data_root,
            finalized_model_roster_path=_FAKE_INPUTS.roster.manifest_path,
            output_dir=output,
            once_lock_path=lock,
            runner_factory=FailingRunner,
        )

    assert not output.exists()
    lock_value = json.loads(lock.read_text(encoding="utf-8"))
    assert lock_value["status"] == "failed_closed"
    assert lock_value["retry_permitted"] is False
    assert Path(lock_value["staging_path"]).is_dir()
    with pytest.raises(FileExistsError, match="already been started or completed"):
        run_confirmatory_evaluation(
            data_root=_FAKE_INPUTS.data_root,
            finalized_model_roster_path=_FAKE_INPUTS.roster.manifest_path,
            output_dir=output,
            once_lock_path=lock,
            runner_factory=_SuccessfulFakeRunner,
        )


def _load_script(filename: str) -> Any:
    path = Path("scripts") / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_availability_long(path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for label, _, _ in FROZEN_PERIODS:
        for site_id in FROZEN_SITE_IDS:
            for variable in FROZEN_VARIABLES:
                rows.append(
                    {
                        "split": label,
                        "site_id": site_id,
                        "variable": variable,
                        "value": 1.0,
                        "natural_observed": True,
                        "quality_approved": True,
                        "estimated_qualifier": False,
                        "qc_status": "approved",
                        "data_version": CONFIRMATORY_DATA_VERSION,
                    }
                )
    pd.DataFrame(rows).to_parquet(path, index=False)


def _patch_feasibility_masks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    corrupt_target_truth: bool = False,
) -> None:
    n_dates = 400
    n_stations = len(FROZEN_SITE_IDS)
    n_variables = len(FROZEN_VARIABLES)

    def fake_init(self, grid: Any, **kwargs: Any) -> None:
        del grid
        self.mask_dir = Path(kwargs["mask_dir"])
        self.mask_dir.mkdir(parents=True, exist_ok=True)
        values = np.ones((n_dates, n_stations, n_variables), dtype=np.float32)
        quality = np.ones_like(values, dtype=bool)
        natural = np.ones_like(values, dtype=bool)
        if corrupt_target_truth:
            values[:, :, 0] = np.nan
            quality[:, :, 0] = False
            natural[:, :, 0] = False
        self.data = SimpleNamespace(
            dates=pd.date_range("2023-01-01", periods=n_dates, freq="D"),
            station_ids=tuple(FROZEN_SITE_IDS),
            variable_names=tuple(FROZEN_VARIABLES),
            values=values,
            natural_observed=natural,
            quality_approved=quality,
        )

    def fake_generate(
        self, scenario: Any
    ) -> tuple[np.ndarray, dict[str, Any]]:
        mask = np.zeros((n_dates, n_stations, n_variables), dtype=bool)
        station_index = FROZEN_SITE_IDS.index(scenario.condition.station_ids[0])
        mask[10, station_index, 0] = True
        if external._information_condition(scenario.condition) == "no_meteorology":
            for variable_index in range(3, n_variables):
                mask[10, :, variable_index] = True
        scenarios = self.mask_dir / "scenarios"
        scenarios.mkdir(parents=True, exist_ok=True)
        (scenarios / f"{scenario.scenario_id}.npz").write_bytes(
            scenario.scenario_id.encode("utf-8")
        )
        (scenarios / f"{scenario.scenario_id}.json").write_text(
            json.dumps({"scenario_id": scenario.scenario_id}), encoding="utf-8"
        )
        return mask, {"scenario_id": scenario.scenario_id}

    def forbid_training(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("feasibility must not train models")

    monkeypatch.setattr(ExternalConfirmationRunner, "__init__", fake_init)
    monkeypatch.setattr(ExternalConfirmationRunner, "_generate_mask", fake_generate)
    monkeypatch.setattr(ExperimentRunner, "run", forbid_training)


def test_feasibility_only_builds_sixty_masks_without_lock_or_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global _FAKE_INPUTS
    _FAKE_INPUTS = _fake_inputs(tmp_path)
    _write_availability_long(_FAKE_INPUTS.long_path)
    monkeypatch.setattr(
        external, "preflight_confirmatory_evaluation", lambda **_kwargs: _FAKE_INPUTS
    )
    _patch_feasibility_masks(monkeypatch)
    output = tmp_path / "feasibility"
    lock = external.confirmatory_once_lock_path(_FAKE_INPUTS.data_root)

    result = run_confirmatory_feasibility(
        data_root=_FAKE_INPUTS.data_root,
        finalized_model_roster_path=_FAKE_INPUTS.roster.manifest_path,
        output_dir=output,
        design_path=DESIGN,
        study_manifest_path=STUDY_MANIFEST,
        experiment_config_path=EXPERIMENT_CONFIG,
    )

    assert result.once_lock_created is False
    assert result.performance_metrics_computed is False
    assert result.models_trained is False
    assert result.report["scenario_count"] == 60
    assert result.report["performance_metrics_computed"] is False
    assert result.report["models_trained"] is False
    assert result.report["once_lock_created"] is False
    assert result.report["status"] == "passed"
    assert len(result.mask_contract) == 60
    assert not lock.exists()
    mask_files = list((output / "masks" / "scenarios").glob("*.npz"))
    assert len(mask_files) == 60
    assert not (output / "daily_predictions.parquet").exists()
    assert not (output / "event_metrics.parquet").exists()


def test_feasibility_fails_if_once_lock_already_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global _FAKE_INPUTS
    _FAKE_INPUTS = _fake_inputs(tmp_path)
    monkeypatch.setattr(
        external, "preflight_confirmatory_evaluation", lambda **_kwargs: _FAKE_INPUTS
    )
    output = tmp_path / "feasibility"
    lock = external.confirmatory_once_lock_path(_FAKE_INPUTS.data_root)
    lock.write_text(json.dumps({"status": "complete"}), encoding="utf-8")

    with pytest.raises(FileExistsError, match="once-lock already exists"):
        run_confirmatory_feasibility(
            data_root=_FAKE_INPUTS.data_root,
            finalized_model_roster_path=_FAKE_INPUTS.roster.manifest_path,
            output_dir=output,
            design_path=DESIGN,
        )
    assert lock.exists()
    assert not output.exists()


def test_feasibility_requires_roster_but_does_not_create_lock(tmp_path: Path) -> None:
    data_root = tmp_path / "external-data"
    data_root.mkdir()
    missing_roster = tmp_path / "missing_roster.json"
    output = tmp_path / "feasibility"
    lock = external.confirmatory_once_lock_path(data_root)

    with pytest.raises(FileNotFoundError):
        run_confirmatory_feasibility(
            data_root=data_root,
            finalized_model_roster_path=missing_roster,
            output_dir=output,
            design_path=DESIGN,
        )
    assert not lock.exists()
    assert not output.exists()


def test_feasibility_rejects_nonfinite_or_unapproved_masked_target_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global _FAKE_INPUTS
    _FAKE_INPUTS = _fake_inputs(tmp_path)
    monkeypatch.setattr(
        external, "preflight_confirmatory_evaluation", lambda **_kwargs: _FAKE_INPUTS
    )
    _patch_feasibility_masks(monkeypatch, corrupt_target_truth=True)
    output = tmp_path / "feasibility"
    lock = external.confirmatory_once_lock_path(_FAKE_INPUTS.data_root)

    with pytest.raises(ValueError, match="approved finite truth"):
        run_confirmatory_feasibility(
            data_root=_FAKE_INPUTS.data_root,
            finalized_model_roster_path=_FAKE_INPUTS.roster.manifest_path,
            output_dir=output,
            design_path=DESIGN,
        )
    assert not lock.exists()
    assert not output.exists()


def test_cli_feasibility_only_flag_is_mutual_exclusive_with_preflight() -> None:
    parser = _load_script("20_run_confirmatory_evaluation.py").build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--feasibility-only",
                "--preflight-only",
                "--finalized-model-roster",
                "roster.json",
            ]
        )


def test_script_08_and_experiment_runner_cannot_use_confirmatory_split(
    tmp_path: Path,
) -> None:
    grid = build_external_confirmation_grid(training_seeds=(11,))
    with pytest.raises(ValueError, match=CONFIRMATORY_ONCE_PATH_REQUIRED):
        ExperimentRunner(
            grid,
            wide_path=tmp_path / "missing.parquet",
            output_dir=tmp_path / "results",
            mask_dir=tmp_path / "masks",
            config_path=EXPERIMENT_CONFIG,
            design_path=Path("configs/design_freeze_v3.yaml"),
            manifest_path=STUDY_MANIFEST,
            models=("climatology",),
        )
    with pytest.raises(ValueError, match="reserved for the once-locked"):
        build_experiment_grid(evaluation_split="confirmatory")
    parser = _load_script("08_run_experiments.py").build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--evaluation-split", "confirmatory"])
    with pytest.raises((FileNotFoundError, OSError, ValueError, KeyError)) as allowed:
        ExternalConfirmationRunner(
            grid,
            wide_path=tmp_path / "missing.parquet",
            output_dir=tmp_path / "results",
            mask_dir=tmp_path / "masks",
            config_path=EXPERIMENT_CONFIG,
            design_path=DESIGN,
            manifest_path=STUDY_MANIFEST,
            models=("climatology",),
        )
    assert CONFIRMATORY_ONCE_PATH_REQUIRED not in str(allowed.value)


def test_architecture_version_s0_abcd_v2_fails_closed_when_rs_is_main_channel(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="s0_abcd_v2"):
        require_main_rs_architecture(
            architecture_version="s0_abcd_v2",
            meteorology_variables=("Ta", "P", "W", "RH", "Rs"),
            variable_names=FROZEN_VARIABLES,
        )
    mutated = DESIGN.read_text(encoding="utf-8").replace(
        "architecture_version: s0_abcd_rs_v1",
        "architecture_version: s0_abcd_v2",
        1,
    )
    path = tmp_path / "design_freeze_rs_collision.yaml"
    path.write_text(mutated, encoding="utf-8")
    with pytest.raises(ValueError, match="s0_abcd_v2"):
        load_confirmatory_protocol(path)
    with pytest.raises(ValueError, match="s0_abcd_v2"):
        load_frozen_model_design(path)


def test_one_network_not_five_basins_language_exists_in_design_freeze_v2() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    geography = document["confirmatory_dataset"]["frozen_external_protocol"][
        "network_geography"
    ]
    assert document["claim_boundaries"]["confirmatory_panel"] == (
        "one_upper_middle_chattahoochee_mainstem_network"
    )
    assert document["claim_boundaries"]["confirmatory_not_five_independent_basins"] is True
    assert geography["claim_unit"] == "one_connected_mainstem_network_panel"
    assert geography["not_five_independent_basins"] is True
    assert "not_five_independent_basins" in text
    assert "one_connected_mainstem_network_panel" in text
