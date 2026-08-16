from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import torch

import stream_recoverability.experiments.retrained_information as retrained
import stream_recoverability.experiments.runner as runner_module
from stream_recoverability.experiments.contracts import file_sha256
from stream_recoverability.experiments.retrained_information import (
    RETRAINED_COALITION_LABELS,
    RETRAINED_COALITIONS,
    RETRAINED_GAP_LENGTHS,
    _epoch,
    _validate_retrained_checkpoint,
    build_retrained_information_grid,
    coalition_slug,
    run_retrained_information_upper_bounds,
)
from stream_recoverability.experiments.validation import (
    validation_anchor_catalog_identity,
)
from stream_recoverability.models.proposed import (
    MissingAwareMultisourceImputer,
    ProposedModelConfig,
)
from stream_recoverability.models.proposed_curriculum import (
    FROZEN_VALIDATION_SCENARIOS,
)
from stream_recoverability.models.proposed_training import ProposedTrainingConfig

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VARIABLES = ("T", "F", "L", "Ta", "P", "W", "RH", "Rs")


@pytest.fixture(autouse=True)
def _accept_mock_roster_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runner_module,
        "validate_formal_authorization",
        lambda value, **kwargs: dict(value),
    )
    monkeypatch.setattr(
        runner_module,
        "validate_formal_grid_contract",
        lambda grid: {"suite": grid.suite, "test_fixture": True},
    )


def _small_processed_data(root: Path) -> tuple[Path, Path]:
    dates = pd.date_range("2018-01-01", periods=30, freq="D")
    split = np.repeat(("train", "validation", "test"), 10)
    wide = pd.DataFrame({"date": dates, "split": split})
    long_rows: list[dict[str, object]] = []
    for station_index, station in enumerate(("B1", "P3", "S2")):
        for variable_index, variable in enumerate(VARIABLES):
            values = (
                station_index
                + variable_index
                + np.sin(np.arange(len(dates), dtype=float) / 4.0)
            ).astype(np.float32)
            wide[f"{station}_{variable}"] = values
            long_rows.extend(
                {
                    "date": date,
                    "station_id": station,
                    "variable": variable,
                    "quality_approved": True,
                }
                for date in dates
            )
    wide_path = root / "daily_wide.parquet"
    quality_path = root / "daily_long.parquet"
    wide.to_parquet(wide_path, index=False)
    pd.DataFrame(long_rows).to_parquet(quality_path, index=False)
    (root / "version_manifest.json").write_text(
        json.dumps(
            {
                "data_version": "published_v1",
                "artifacts": {
                    "daily_wide.parquet": {"sha256": file_sha256(wide_path)},
                    "daily_long.parquet": {"sha256": file_sha256(quality_path)},
                },
            }
        ),
        encoding="utf-8",
    )
    return wide_path, quality_path


def _authorized_roster() -> SimpleNamespace:
    return SimpleNamespace(
        proposed_decision="include_proposed_formally",
        selected_models=("linear", "proposed"),
        best_traditional_model="linear",
        manifest_path="validation/finalized_model_roster.json",
        manifest_sha256="a" * 64,
        selection_data_version="published_v1",
        selection_design_hash="d" * 64,
        selection_contract={"code_identity": {"relevant_source_digest": "c" * 64}},
        selection_data_version_manifest={
            "path": "data_versions/published_v1/version_manifest.json",
            "sha256": "e" * 64,
            "bytes": 1,
        },
        validation_anchor_catalog=validation_anchor_catalog_identity(),
    )


def test_retrained_design_is_exactly_nine_coalitions_and_three_gaps() -> None:
    grid = build_retrained_information_grid(
        PROJECT_ROOT / "study_manifest.yaml",
        mask_seeds=(101, 120),
        frontier_anchor_path=None,
    )
    assert RETRAINED_COALITION_LABELS == (
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
    assert len(RETRAINED_COALITIONS) == 9
    assert RETRAINED_GAP_LENGTHS == (30, 90, 180)
    assert len(grid.conditions) == 9
    assert len(grid.scenarios) == 18
    assert {condition.gap_length for condition in grid.conditions} == {30, 90, 180}
    assert all(
        condition.experiment == "SCI_RETRAINED_INFORMATION"
        for condition in grid.conditions
    )
    assert coalition_slug(()) == "s0"
    assert coalition_slug("S0+A+B+C+D") == "s0-a-b-c-d"
    with pytest.raises(ValueError, match="frozen nine-coalition"):
        coalition_slug("S0+B+C")


def test_retrained_epoch_never_enables_sources_outside_coalition() -> None:
    class RecordingModel(MissingAwareMultisourceImputer):
        def __init__(self, config: ProposedModelConfig) -> None:
            super().__init__(config)
            self.seen_group_masks: list[torch.Tensor] = []

        def forward(self, *args: object, **kwargs: object) -> dict[str, torch.Tensor]:
            group_mask = kwargs["group_mask"]
            assert isinstance(group_mask, torch.Tensor)
            self.seen_group_masks.append(group_mask.detach().cpu().clone())
            return super().forward(*args, **kwargs)

    config = ProposedModelConfig(
        station_ids=("B1", "S2"),
        variable_names=VARIABLES,
        hidden_size=8,
        station_embedding_size=3,
        variable_embedding_size=2,
        dropout=0.0,
    )
    model = RecordingModel(config)
    values = torch.zeros((1, 6, 2, len(VARIABLES)), dtype=torch.float32)
    natural = torch.ones_like(values, dtype=torch.bool)
    artificial = torch.zeros_like(values, dtype=torch.bool)
    artificial[:, 3, 0, 0] = True
    batch = {
        "values": values,
        "natural_mask": natural,
        "artificial_mask": artificial,
        "target": values[..., 0],
        "quality_mask": torch.ones((1, 6, 2), dtype=torch.bool),
        "seasonal_features": torch.zeros((1, 6, 4)),
        "training_climatology": torch.zeros((1, 6, 2)),
        "training_mask_type": "unit",
    }
    training = ProposedTrainingConfig(
        epochs=1,
        patience=1,
        source_dropout_probability=0.0,
        seed=11,
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    _epoch(
        model,
        (batch,),
        training,
        torch.tensor((False, True, False, False)),
        optimizer=optimizer,
        source_generator=torch.Generator().manual_seed(28),
    )
    _epoch(
        model,
        (batch,),
        training,
        torch.zeros(4, dtype=torch.bool),
        optimizer=None,
        source_generator=None,
    )
    assert model.seen_group_masks[0].shape == (1, 4)
    assert model.seen_group_masks[0].tolist() == [[False, True, False, False]]
    assert model.seen_group_masks[1].shape == (4,)
    assert not model.seen_group_masks[1].any()


def test_retrained_checkpoint_resume_requires_exact_contract(tmp_path: Path) -> None:
    model_config = ProposedModelConfig(
        station_ids=("B1",),
        variable_names=VARIABLES,
        hidden_size=8,
        station_embedding_size=3,
        variable_embedding_size=2,
        dropout=0.0,
    )
    training_config = ProposedTrainingConfig(epochs=2, patience=1, seed=11)
    model = MissingAwareMultisourceImputer(model_config)
    context = {"profile": "smoke", "input_files": {}}
    contract = {
        "schema_version": "retrained_information_checkpoint_v1",
        "coalition": ["A"],
        "training_seed": 11,
    }
    checkpoint = tmp_path / "checkpoint.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "model_config": asdict(model_config),
            "training_config": asdict(training_config),
            "training_context": context,
            "quantile_levels": list(model.quantile_levels),
            "train_scaler": {
                "mean": np.zeros((1, len(VARIABLES))).tolist(),
                "scale": np.ones((1, len(VARIABLES))).tolist(),
                "station_ids": ["B1"],
                "variable_names": list(VARIABLES),
            },
            "epoch": 1,
            "best_epoch": 1,
            "best_validation_loss": 1.0,
            "best_validation_score": 1.0,
            "epochs_run": 1,
            "hit_epoch_limit": False,
            "history": [
                {
                    "epoch": 1,
                    "train_loss": 1.1,
                    "validation_loss": 1.0,
                    "validation_score": 1.0,
                }
            ],
            "validation_scores": {name: 1.0 for name in FROZEN_VALIDATION_SCENARIOS},
            "retrained_contract": contract,
        },
        checkpoint,
    )
    _, metadata, mean, scale = _validate_retrained_checkpoint(
        checkpoint,
        contract,
        model_config,
        training_config,
        context,
    )
    assert metadata["retrained_contract"] == contract
    assert mean.shape == scale.shape == (1, len(VARIABLES))
    with pytest.raises(ValueError, match="exactly match"):
        _validate_retrained_checkpoint(
            checkpoint,
            {**contract, "coalition": ["B"]},
            model_config,
            training_config,
            context,
        )


def test_framework_only_roster_marks_retrained_not_applicable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roster = _authorized_roster()
    roster.proposed_decision = "framework_only"
    roster.selected_models = ("linear",)
    monkeypatch.setattr(
        retrained, "load_finalized_model_roster", lambda *a, **k: roster
    )
    output = tmp_path / "retrained"
    daily, events, manifest = run_retrained_information_upper_bounds(
        finalized_model_roster_path=tmp_path / "roster.json",
        output_dir=output,
    )
    assert daily.empty and events.empty
    assert manifest["status"] == "not_applicable"
    assert manifest["formal_design_complete"] is False
    assert manifest["proposed_decision"] == "framework_only"
    assert not (output / "checkpoints").exists()


def test_partial_retrained_run_writes_exact_retryable_and_hash_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wide_path, quality_path = _small_processed_data(tmp_path)
    monkeypatch.setattr(
        retrained, "load_finalized_model_roster", lambda *a, **k: _authorized_roster()
    )

    def fake_mask(
        self: object, scenario: object
    ) -> tuple[np.ndarray, dict[str, object]]:
        runner = self
        mask = np.zeros_like(runner.data.values, dtype=bool)
        station = runner.data.station_ids.index(scenario.condition.station_ids[0])
        target = runner.data.variable_names.index("T")
        position = int(np.flatnonzero(runner._evaluation_rows(scenario))[0])
        mask[position, station, target] = True
        return mask, {"mask_type": "frozen_test_mask", "position": position}

    monkeypatch.setattr(retrained.ExperimentRunner, "_generate_mask", fake_mask)

    def fake_train_or_load(
        runner: object,
        output_root: Path,
        coalition: tuple[str, ...],
        seed: int,
        *,
        window_length: int,
        training_protocol: str,
        resume: bool,
    ) -> tuple[object, dict[str, object], np.ndarray, np.ndarray, Path]:
        del resume
        model_config, _, _, contract = retrained._base_training_contract(
            runner,
            coalition,
            seed,
            window_length=window_length,
            training_protocol=training_protocol,
        )
        model = MissingAwareMultisourceImputer(model_config)
        mean, scale = runner._proposed_scaler()
        checkpoint = retrained._checkpoint_path(output_root, coalition, seed)
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        torch.save({"contract": contract}, checkpoint)
        metadata = {
            "best_epoch": 1,
            "epochs_run": 1,
            "best_validation_score": 1.0,
            "validation_scores": {name: 1.0 for name in FROZEN_VALIDATION_SCENARIOS},
        }
        return model, metadata, mean, scale, checkpoint

    def fake_validate(
        checkpoint: Path,
        contract: dict[str, object],
        model_config: ProposedModelConfig,
        training_config: ProposedTrainingConfig,
        training_context: dict[str, object],
    ) -> tuple[object, dict[str, object], np.ndarray, np.ndarray]:
        del training_config, training_context
        if not checkpoint.is_file():
            raise FileNotFoundError(checkpoint)
        model = MissingAwareMultisourceImputer(model_config)
        metadata = {
            "best_epoch": 1,
            "epochs_run": 1,
            "best_validation_score": 1.0,
            "validation_scores": {name: 1.0 for name in FROZEN_VALIDATION_SCENARIOS},
            "retrained_contract": contract,
        }
        shape = (len(model_config.station_ids), len(model_config.variable_names))
        return model, metadata, np.zeros(shape, np.float32), np.ones(shape, np.float32)

    monkeypatch.setattr(retrained, "_train_or_load_checkpoint", fake_train_or_load)
    monkeypatch.setattr(retrained, "_validate_retrained_checkpoint", fake_validate)
    output = tmp_path / "results"
    daily, events, manifest = run_retrained_information_upper_bounds(
        finalized_model_roster_path=tmp_path / "roster.json",
        manifest_path=PROJECT_ROOT / "study_manifest.yaml",
        config_path=PROJECT_ROOT / "configs/experiments.yaml",
        design_path=PROJECT_ROOT / "configs/design_freeze_v2.yaml",
        wide_path=wide_path,
        quality_path=quality_path,
        output_dir=output,
        mask_dir=tmp_path / "masks",
        training_seeds=(11,),
        mask_seeds=(101,),
        coalitions=("S0",),
        frontier_anchor_path=None,
        max_scenarios=1,
    )
    assert len(events) == 1
    assert len(daily) == 1
    assert daily["information_combination"].eq("S0").all()
    assert daily["attribution_estimand"].eq("retrained_upper_bound").all()
    assert daily["component_estimator"].eq("proposed_checkpoint").all()
    assert daily[["q05", "q25", "q50", "q75", "q95"]].notna().all().all()
    assert manifest["complete"] is False
    assert manifest["expected_run_unit_count"] == 9 * 5
    assert manifest["completed_run_unit_count"] == 0
    assert manifest["retryable_run_unit_count"] == 9 * 5
    assert manifest["checkpoint_required_run_count"] == 9 * 5
    assert manifest["checkpoint_valid_run_count"] == 0
    assert manifest["finite_prediction_run_unit_count"] == 0
    assert manifest["finite_event_metric_run_unit_count"] == 0
    assert manifest["pooling_rule"] == "never_mix_with_operational_dropout"
    assert manifest["data_version"] == "published_v1"
    assert manifest["evaluation_split"] == "development_test"
    assert (output / "run_manifest.json").is_file()
