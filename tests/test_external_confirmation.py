from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

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
)
from stream_recoverability.experiments.model_registry import (
    load_frozen_model_design,
)
from stream_recoverability.experiments.runner import ExperimentRunner

DESIGN = Path("configs/design_freeze_v1.yaml")
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
        "design_version": "design_freeze_v1",
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
