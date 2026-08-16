from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest
import torch

import stream_recoverability.models.proposed_training as proposed_training_module
from stream_recoverability.models.proposed import (
    MAIN_ARCHITECTURE_VERSION,
    MissingAwareMultisourceImputer,
    ProposedModelConfig,
    all_information_group_combinations,
    compute_bidirectional_time_gaps,
    masked_imputation_loss,
    require_main_rs_architecture,
)
from stream_recoverability.models.proposed_curriculum import generate_curriculum_mask
from stream_recoverability.models.proposed_training import (
    ProposedTrainingConfig,
    load_proposed_checkpoint,
    sample_source_dropout,
    set_deterministic_seed,
    train_proposed_model,
    validate_proposed_checkpoint_contract,
)


def _config() -> ProposedModelConfig:
    return ProposedModelConfig(
        hidden_size=12,
        station_embedding_size=4,
        variable_embedding_size=3,
        dropout=0.0,
        max_time_gap=30,
    )


def _inputs(batch: int = 2, steps: int = 12) -> dict[str, torch.Tensor]:
    generator = torch.Generator().manual_seed(9)
    values = torch.randn((batch, steps, 3, 8), generator=generator)
    natural = torch.rand(values.shape, generator=generator) > 0.05
    artificial = torch.zeros_like(natural)
    artificial[:, 4:7, :, 0] = True
    phase = 2 * torch.pi * torch.arange(steps) / steps
    seasonal = (
        torch.stack(
            (
                torch.sin(phase),
                torch.cos(phase),
                torch.sin(phase / 2),
                torch.cos(phase / 2),
            ),
            dim=-1,
        )
        .unsqueeze(0)
        .expand(batch, -1, -1)
        .clone()
    )
    return {
        "values": values,
        "natural_mask": natural,
        "artificial_mask": artificial,
        "target": values[..., 0].clone(),
        "quality_mask": natural[..., 0].clone(),
        "seasonal_features": seasonal,
    }


def test_forward_shapes_finite_values_and_ordered_quantiles() -> None:
    model = MissingAwareMultisourceImputer(_config()).eval()
    batch = _inputs()
    output = model(
        batch["values"],
        batch["natural_mask"],
        batch["artificial_mask"],
        seasonal_features=batch["seasonal_features"],
    )
    assert output["quantiles"].shape == (2, 12, 3, 5)
    assert output["gate_weights"].shape == (2, 12, 3, 4)
    assert output["cross_station_attention"].shape == (2, 12, 3, 3)
    assert output["source_available_S0"].all()
    for index, group in enumerate(("A", "B", "C", "D")):
        assert output[f"source_available_{group}"].shape == (2, 12, 3)
        assert output[f"source_available_{group}"].dtype == torch.bool
        torch.testing.assert_close(
            output[f"gate_{group}"], output["gate_weights"][..., index]
        )
    assert torch.isfinite(output["quantiles"]).all()
    assert torch.all(output["q05"] < output["q25"])
    assert torch.all(output["q25"] < output["q50"])
    assert torch.all(output["q50"] < output["q75"])
    assert torch.all(output["q75"] < output["q95"])


def test_bidirectional_time_gaps_use_both_sides() -> None:
    available = torch.tensor([[[True], [False], [False], [True], [False]]])
    gaps = compute_bidirectional_time_gaps(available, max_gap=10)
    assert gaps.shape == (1, 5, 1, 2)
    assert gaps[0, :, 0, 0].tolist() == [0, 1, 2, 0, 1]
    assert gaps[0, :, 0, 1].tolist() == [0, 2, 1, 0, 10]


def test_unavailable_and_disabled_branches_have_zero_gate_weight() -> None:
    model = MissingAwareMultisourceImputer(_config()).eval()
    batch = _inputs()
    batch["natural_mask"][..., 1:3] = False
    output = model(
        batch["values"],
        batch["natural_mask"],
        batch["artificial_mask"],
        seasonal_features=batch["seasonal_features"],
    )
    assert torch.count_nonzero(output["branch_availability"][..., 1]) == 0
    assert torch.count_nonzero(output["gate_weights"][..., 1]) == 0

    only_a = model(
        batch["values"],
        batch["natural_mask"],
        batch["artificial_mask"],
        seasonal_features=batch["seasonal_features"],
        enabled_groups=("A",),
    )
    assert torch.count_nonzero(only_a["gate_weights"][..., 1:]) == 0
    assert torch.allclose(
        only_a["gate_weights"][..., 0], torch.ones_like(only_a["gate_weights"][..., 0])
    )


def test_weather_dropout_disables_d_but_keeps_s0_finite_and_available() -> None:
    model = MissingAwareMultisourceImputer(_config()).eval()
    batch = _inputs(batch=1)
    meteorology = [
        model.variable_index[name] for name in model.config.meteorology_variables
    ]
    batch["natural_mask"][..., meteorology] = False

    output = model(
        batch["values"],
        batch["natural_mask"],
        batch["artificial_mask"],
        seasonal_features=batch["seasonal_features"],
        enabled_groups=("D",),
    )

    assert output["source_available_S0"].all()
    assert not output["source_available_D"].any()
    assert torch.count_nonzero(output["branch_availability"][..., 3]) == 0
    assert torch.count_nonzero(output["gate_D"]) == 0
    assert torch.count_nonzero(output["gate_weights"]) == 0
    assert torch.isfinite(output["quantiles"]).all()


def test_s0_is_independent_of_d_and_accepts_optional_training_climatology() -> None:
    torch.manual_seed(41)
    model = MissingAwareMultisourceImputer(_config()).eval()
    batch = _inputs(batch=1)
    climatology = torch.zeros((1, 12, 3))
    weather_changed = batch["values"].clone()
    meteorology = [
        model.variable_index[name] for name in model.config.meteorology_variables
    ]
    weather_changed[..., meteorology] += 1_000_000.0

    with torch.no_grad():
        reference = model(
            batch["values"],
            batch["natural_mask"],
            batch["artificial_mask"],
            seasonal_features=batch["seasonal_features"],
            training_climatology=climatology,
            enabled_groups=(),
        )
        changed_weather = model(
            weather_changed,
            batch["natural_mask"],
            batch["artificial_mask"],
            seasonal_features=batch["seasonal_features"],
            training_climatology=climatology,
            enabled_groups=(),
        )
        changed_calendar = model(
            batch["values"],
            batch["natural_mask"],
            batch["artificial_mask"],
            seasonal_features=batch["seasonal_features"] + 10.0,
            training_climatology=climatology + 10.0,
            enabled_groups=(),
        )

    torch.testing.assert_close(reference["quantiles"], changed_weather["quantiles"])
    assert torch.count_nonzero(reference["gate_weights"]) == 0
    assert not torch.allclose(reference["quantiles"], changed_calendar["quantiles"])


def test_s0_sanitizes_nonfinite_optional_inputs() -> None:
    model = MissingAwareMultisourceImputer(_config()).eval()
    batch = _inputs(batch=1)
    seasonal = torch.full_like(batch["seasonal_features"], torch.nan)
    seasonal[:, 0] = torch.inf
    climatology = torch.full((1, 12, 3, 1), torch.nan)
    climatology[:, 0] = -torch.inf

    output = model(
        batch["values"],
        batch["natural_mask"],
        batch["artificial_mask"],
        seasonal_features=seasonal,
        training_climatology=climatology,
        enabled_groups=(),
    )

    assert output["source_available_S0"].all()
    assert torch.isfinite(output["quantiles"]).all()


def test_all_sixteen_information_combinations_are_supported() -> None:
    model = MissingAwareMultisourceImputer(_config()).eval()
    batch = _inputs(batch=1)
    combinations = all_information_group_combinations()
    assert len(combinations) == 16
    for groups in combinations:
        output = model(
            batch["values"],
            batch["natural_mask"],
            batch["artificial_mask"],
            seasonal_features=batch["seasonal_features"],
            enabled_groups=groups,
        )
        assert torch.isfinite(output["quantiles"]).all()
        disabled = [
            index
            for index, name in enumerate(("A", "B", "C", "D"))
            if name not in groups
        ]
        if disabled:
            assert torch.count_nonzero(output["gate_weights"][..., disabled]) == 0


def test_disabled_source_cannot_change_enabled_branch_fusion() -> None:
    model = MissingAwareMultisourceImputer(_config()).eval()
    batch = _inputs(batch=1)
    perturbed_values = batch["values"].clone()
    perturbed_values[..., 3:] += 1_000.0

    with torch.no_grad():
        first = model(
            batch["values"],
            batch["natural_mask"],
            batch["artificial_mask"],
            seasonal_features=batch["seasonal_features"],
            enabled_groups=("A", "C"),
        )
        second = model(
            perturbed_values,
            batch["natural_mask"],
            batch["artificial_mask"],
            seasonal_features=batch["seasonal_features"],
            enabled_groups=("A", "C"),
        )

    torch.testing.assert_close(first["gate_weights"], second["gate_weights"])
    torch.testing.assert_close(first["quantiles"], second["quantiles"])


def test_hidden_input_truth_does_not_change_prediction_or_loss() -> None:
    model = MissingAwareMultisourceImputer(_config()).eval()
    batch = _inputs()
    perturbed = batch["values"].clone()
    hidden_target = batch["artificial_mask"][..., 0]
    perturbed[..., 0][hidden_target] += 1_000_000
    with torch.no_grad():
        first = model(
            batch["values"],
            batch["natural_mask"],
            batch["artificial_mask"],
            seasonal_features=batch["seasonal_features"],
        )
        second = model(
            perturbed,
            batch["natural_mask"],
            batch["artificial_mask"],
            seasonal_features=batch["seasonal_features"],
        )
    torch.testing.assert_close(first["quantiles"], second["quantiles"])
    first_loss = masked_imputation_loss(
        first, batch["target"], hidden_target, quality_mask=batch["quality_mask"]
    )["loss"]
    second_loss = masked_imputation_loss(
        second, batch["target"], hidden_target, quality_mask=batch["quality_mask"]
    )["loss"]
    torch.testing.assert_close(first_loss, second_loss)


def test_loss_only_uses_artificially_hidden_quality_targets() -> None:
    batch = _inputs(batch=1)
    model = MissingAwareMultisourceImputer(_config()).eval()
    output = model(
        batch["values"],
        batch["natural_mask"],
        batch["artificial_mask"],
        seasonal_features=batch["seasonal_features"],
    )
    mask = batch["artificial_mask"][..., 0]
    first = masked_imputation_loss(
        output, batch["target"], mask, quality_mask=batch["quality_mask"]
    )
    changed_outside = batch["target"].clone()
    changed_outside[~mask] += 100_000
    second = masked_imputation_loss(
        output, changed_outside, mask, quality_mask=batch["quality_mask"]
    )
    torch.testing.assert_close(first["loss"], second["loss"])
    assert int(first["masked_count"]) == int((mask & batch["quality_mask"]).sum())


def test_loss_uses_all_five_quantiles_and_huber_uses_median() -> None:
    quantiles = torch.tensor([[[[-4.0, -2.0, 1.0, 3.0, 5.0]]]])
    target = torch.zeros((1, 1, 1))
    mask = torch.ones_like(target, dtype=torch.bool)
    losses = masked_imputation_loss(quantiles, target, mask)
    torch.testing.assert_close(losses["huber"], torch.tensor(0.5))
    torch.testing.assert_close(losses["pinball"], torch.tensor(0.44))


def test_source_dropout_is_seeded_and_can_reach_the_s0_only_estimand() -> None:
    first = sample_source_dropout(32, 0.5, generator=torch.Generator().manual_seed(22))
    second = sample_source_dropout(32, 0.5, generator=torch.Generator().manual_seed(22))
    assert torch.equal(first, second)
    assert first.any(dim=1).all()
    assert (~first).any()
    assert first.any()
    s0_only = sample_source_dropout(
        4,
        1.0,
        generator=torch.Generator().manual_seed(23),
        ensure_one_source=False,
    )
    assert not s0_only.any()


def _weighted_epoch_batch(
    masked_count: int,
    factor: float,
    scenario: str,
) -> dict[str, torch.Tensor | float | str]:
    values = torch.zeros((1, 10, 3, 8))
    natural = torch.ones_like(values, dtype=torch.bool)
    artificial = torch.zeros_like(natural)
    artificial[0, :masked_count, 0, 0] = True
    return {
        "values": values,
        "natural_mask": natural,
        "artificial_mask": artificial,
        "target": values[..., 0].clone(),
        "quality_mask": torch.ones((1, 10, 3), dtype=torch.bool),
        "factor": factor,
        "validation_scenario": scenario,
    }


def test_epoch_loss_and_gradient_are_weighted_by_masked_cells(monkeypatch) -> None:
    class ScalarModel(torch.nn.Module):
        target_index = 0

        def __init__(self) -> None:
            super().__init__()
            self.weight = torch.nn.Parameter(torch.tensor(1.0))

    model = ScalarModel()
    batches = (
        _weighted_epoch_batch(1, 1.0, "aggregate"),
        _weighted_epoch_batch(9, 3.0, "aggregate"),
    )

    def fake_batch_loss(model, batch, config, *, group_mask):
        del config, group_mask
        count = batch["artificial_mask"][..., 0].sum()
        loss = model.weight * float(batch["factor"])
        return {"loss": loss, "loss_sum": loss * count, "masked_count": count}

    monkeypatch.setattr(proposed_training_module, "_batch_loss", fake_batch_loss)
    optimizer = torch.optim.SGD(model.parameters(), lr=1.0)
    metrics = proposed_training_module._run_epoch(
        model,
        batches,
        ProposedTrainingConfig(gradient_clip=0.0, source_dropout_probability=0.0),
        torch.device("cpu"),
        optimizer=optimizer,
        source_generator=torch.Generator().manual_seed(1),
    )

    assert metrics.masked_cells == 10
    assert metrics.loss == pytest.approx((1.0 + 9 * 3.0) / 10)
    assert model.weight.item() == pytest.approx(1.0 - (1.0 + 9 * 3.0) / 10)


def test_validation_breakdown_covers_four_frozen_scenarios(monkeypatch) -> None:
    class ScalarModel(torch.nn.Module):
        target_index = 0

        def __init__(self) -> None:
            super().__init__()
            self.weight = torch.nn.Parameter(torch.tensor(1.0))

    scenarios = ("point", "short_block", "long_block", "station_outage")
    batches = tuple(
        _weighted_epoch_batch(index, float(index), scenario)
        for index, scenario in enumerate(scenarios, start=1)
    )

    def fake_batch_loss(model, batch, config, *, group_mask):
        del config, group_mask
        count = batch["artificial_mask"][..., 0].sum()
        loss = model.weight * float(batch["factor"])
        return {"loss": loss, "loss_sum": loss * count, "masked_count": count}

    monkeypatch.setattr(proposed_training_module, "_batch_loss", fake_batch_loss)
    model = ScalarModel()
    config = ProposedTrainingConfig()
    metrics = proposed_training_module._run_epoch(
        model,
        batches,
        config,
        torch.device("cpu"),
        optimizer=None,
        source_generator=None,
    )

    assert metrics.scenario_losses == {
        "long_block": 3.0,
        "point": 1.0,
        "short_block": 2.0,
        "station_outage": 4.0,
    }
    assert metrics.loss == pytest.approx((1 + 4 + 9 + 16) / 10)
    assert proposed_training_module._validation_score(metrics, config) == pytest.approx(
        2.5
    )


def test_fixed_seed_produces_identical_models_and_predictions() -> None:
    batch = _inputs(batch=1)
    set_deterministic_seed(123)
    first_model = MissingAwareMultisourceImputer(_config()).eval()
    first = first_model(
        batch["values"],
        batch["natural_mask"],
        batch["artificial_mask"],
        seasonal_features=batch["seasonal_features"],
    )["quantiles"]
    set_deterministic_seed(123)
    second_model = MissingAwareMultisourceImputer(_config()).eval()
    second = second_model(
        batch["values"],
        batch["natural_mask"],
        batch["artificial_mask"],
        seasonal_features=batch["seasonal_features"],
    )["quantiles"]
    torch.testing.assert_close(first, second)


def test_training_early_stops_and_saves_loadable_checkpoint(tmp_path: Path) -> None:
    batch = _inputs(batch=2, steps=10)
    batches = [batch]
    set_deterministic_seed(5)
    model = MissingAwareMultisourceImputer(_config())
    checkpoint = tmp_path / "proposed.pt"
    result = train_proposed_model(
        model,
        batches,
        batches,
        ProposedTrainingConfig(
            epochs=5,
            learning_rate=0.0,
            patience=1,
            min_delta=0.0,
            source_dropout_probability=0.25,
            seed=5,
        ),
        checkpoint_path=checkpoint,
    )
    assert result.best_epoch == 1
    assert result.epochs_run == 2
    assert result.hit_epoch_limit is False
    assert checkpoint.exists()
    loaded, metadata = load_proposed_checkpoint(checkpoint)
    assert isinstance(loaded, MissingAwareMultisourceImputer)
    assert metadata["epoch"] == 1
    assert metadata["best_epoch"] == 1
    assert metadata["epochs_run"] == 2
    assert metadata["hit_epoch_limit"] is False
    assert len(metadata["history"]) == 2
    assert metadata["training_config"]["epochs"] == 5
    assert metadata["training_config"]["training_contract_version"] == (
        "proposed_training_v2"
    )
    assert metadata["training_config"]["loss_aggregation"] == ("masked_cell_weighted")
    assert metadata["model_config"]["architecture_version"] == (
        MAIN_ARCHITECTURE_VERSION
    )
    assert metadata["history"][0]["train_masked_cells"] > 0
    assert metadata["history"][0]["validation_masked_cells"] > 0
    assert metadata["training_curriculum"]["target_masked_cells"] > 0
    assert metadata["validation_curriculum"]["target_masked_cells"] > 0
    assert metadata["best_validation_loss"] == result.best_validation_loss


def test_old_training_contract_is_rejected() -> None:
    model = MissingAwareMultisourceImputer(_config())
    config = ProposedTrainingConfig(epochs=2, patience=1)
    stored_config = asdict(config)
    stored_config.pop("training_contract_version")
    checkpoint = {
        "model_state_dict": model.state_dict(),
        "model_config": asdict(model.config),
        "training_config": stored_config,
        "training_context": {},
        "epoch": 1,
        "best_epoch": 1,
        "best_validation_loss": 1.0,
        "epochs_run": 1,
        "hit_epoch_limit": False,
        "history": [{"epoch": 1.0, "train_loss": 1.0, "validation_loss": 1.0}],
    }
    with pytest.raises(ValueError, match="training_contract_version"):
        validate_proposed_checkpoint_contract(
            checkpoint,
            expected_model_config=model.config,
            expected_training_config=config,
            expected_training_context={},
        )


def test_training_rejects_nonfinite_losses(tmp_path: Path, monkeypatch) -> None:
    batch = _inputs(batch=1, steps=8)
    model = MissingAwareMultisourceImputer(_config())
    monkeypatch.setattr(
        "stream_recoverability.models.proposed_training._run_epoch",
        lambda *args, **kwargs: float("nan"),
    )
    with pytest.raises(RuntimeError, match="non-finite"):
        train_proposed_model(
            model,
            [batch],
            [batch],
            ProposedTrainingConfig(epochs=1, patience=1),
            checkpoint_path=tmp_path / "invalid.pt",
        )
    assert not (tmp_path / "invalid.pt").exists()


def test_cli_smoke_runs_on_cpu_and_saves_checkpoint(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "06_train_proposed.py"
    checkpoint = tmp_path / "smoke.pt"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--smoke",
            "--epochs",
            "1",
            "--batch-size",
            "6",
            "--checkpoint",
            str(checkpoint),
            "--device",
            "cpu",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout.strip().splitlines()[-1])
    assert summary["mode"] == "smoke"
    assert summary["quantile_shape"][-1] == 5
    assert checkpoint.exists()


def test_architecture_version_s0_abcd_v2_fails_closed_when_rs_is_main_channel() -> None:
    with pytest.raises(ValueError, match="s0_abcd_v2"):
        require_main_rs_architecture(
            architecture_version="s0_abcd_v2",
            meteorology_variables=("Ta", "P", "W", "RH", "Rs"),
            variable_names=("T", "F", "L", "Ta", "P", "W", "RH", "Rs"),
        )
    with pytest.raises(ValueError, match="s0_abcd_v2"):
        MissingAwareMultisourceImputer(
            ProposedModelConfig(architecture_version="s0_abcd_v2")
        )


def test_main_curriculum_requires_rs_and_rejects_silent_dh_fallback() -> None:
    eligible = np.ones((64, 3, 8), dtype=bool)
    dh_only = ("T", "F", "L", "Ta", "P", "W", "RH", "DH")
    with pytest.raises(ValueError, match="requires Rs"):
        generate_curriculum_mask(
            eligible,
            dh_only,
            scenario="point",
            protocol="seen_length",
            seed=0,
        )
    sensitivity = generate_curriculum_mask(
        eligible,
        dh_only,
        scenario="point",
        protocol="seen_length",
        seed=0,
        jinsha_sunshine_sensitivity=True,
    )
    assert sensitivity.artificial_mask[..., 0].any()
