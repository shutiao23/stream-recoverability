from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

from stream_recoverability.experiments.grid import (
    CORE_EXPECTED_COUNTS,
    ExperimentScenario,
    build_experiment_grid,
)
from stream_recoverability.experiments.runner import (
    SUPPORTED_MODELS,
    ExperimentRunner,
    apply_full_artificial_mask,
    make_training_mask,
)
from stream_recoverability.models.proposed import (
    MissingAwareMultisourceImputer,
    ProposedModelConfig,
)
from stream_recoverability.models.proposed_training import ProposedTrainingConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "study_manifest.yaml"
CONFIG = REPO_ROOT / "configs" / "experiments.yaml"
VARIABLES = ("T", "F", "L", "Ta", "P", "W", "RH", "DH")


def _wide_data(path: Path) -> Path:
    dates = pd.date_range("2006-01-01", "2020-12-31", freq="D")
    day = np.arange(len(dates), dtype=float)
    frame = pd.DataFrame({"date": dates})
    frame["split"] = np.select(
        [dates <= "2015-12-31", dates <= "2017-12-31"],
        ["train", "validation"],
        default="test",
    )
    days_in_year = np.where(dates.is_leap_year, 366.0, 365.0)
    day_phase = 2 * np.pi * (dates.dayofyear.to_numpy() - 1) / days_in_year
    month_phase = 2 * np.pi * (dates.month.to_numpy() - 1) / 12.0
    frame["day_of_year_sin"] = np.sin(day_phase)
    frame["day_of_year_cos"] = np.cos(day_phase)
    frame["month_sin"] = np.sin(month_phase)
    frame["month_cos"] = np.cos(month_phase)
    for station_index, station in enumerate(("B1", "S2", "P3")):
        frame[f"{station}_T"] = 10 + station_index + 5 * np.sin(day / 58.0)
        frame[f"{station}_F"] = 100 + station_index * 10 + 8 * np.cos(day / 23.0)
        frame[f"{station}_L"] = 20 + 0.05 * frame[f"{station}_F"]
        frame[f"{station}_Ta"] = 8 + 7 * np.sin(day / 58.0)
        frame[f"{station}_P"] = np.maximum(0, np.sin(day / 7.0))
        frame[f"{station}_W"] = 2 + 0.2 * np.cos(day / 11.0)
        frame[f"{station}_RH"] = 55 + 4 * np.sin(day / 17.0)
        frame[f"{station}_DH"] = 8 + 2 * np.cos(day / 58.0)
    frame.to_parquet(path, index=False)
    return path


def _runner(
    tmp_path: Path, *, models: tuple[str, ...] = ("climatology", "linear")
) -> ExperimentRunner:
    wide_path = _wide_data(tmp_path / "wide.parquet")
    grid = build_experiment_grid(MANIFEST, CONFIG, suite="smoke")
    return ExperimentRunner(
        grid,
        wide_path=wide_path,
        quality_path=None,
        output_dir=tmp_path / "results",
        mask_dir=tmp_path / "masks",
        config_path=CONFIG,
        models=models,
        resume=True,
    )


def _write_synthetic_proposed_checkpoint(
    model: MissingAwareMultisourceImputer,
    config: ProposedTrainingConfig,
    checkpoint_path: str | Path,
) -> None:
    Path(checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "model_config": asdict(model.config),
            "training_config": asdict(config),
            "epoch": 1,
            "best_epoch": 1,
            "best_validation_loss": 1.0,
            "epochs_run": 1,
            "hit_epoch_limit": False,
            "history": [
                {"epoch": 1.0, "train_loss": 1.1, "validation_loss": 1.0}
            ],
        },
        checkpoint_path,
    )


def _write_runner_proposed_checkpoint(
    runner: ExperimentRunner,
    scenario: ExperimentScenario,
    checkpoint_path: Path,
) -> dict[str, object]:
    model = MissingAwareMultisourceImputer(
        ProposedModelConfig(
            station_ids=runner.data.station_ids,
            variable_names=runner.data.variable_names,
            hidden_size=24,
            dropout=0.0,
        )
    )
    config = ProposedTrainingConfig(
        epochs=runner.training_settings["proposed_epochs"],
        patience=runner.training_settings["proposed_patience"],
        seed=11,
        device=runner.training_settings["device"],
    )
    _write_synthetic_proposed_checkpoint(model, config, checkpoint_path)
    payload = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    mean, scale = runner._proposed_scaler()
    payload.update(
        {
            "quantile_levels": list(model.quantile_levels),
            "train_scaler": {
                "mean": mean.tolist(),
                "scale": scale.tolist(),
                "station_ids": list(runner.data.station_ids),
                "variable_names": list(runner.data.variable_names),
            },
            "training_context": {
                "profile": runner.training_profile_name,
                "train_mask_repeats": runner.training_settings[
                    "train_mask_repeats"
                ],
                "validation_mask_repeats": runner.training_settings[
                    "validation_mask_repeats"
                ],
                "window": scenario.condition.window_length,
                "protocol": scenario.condition.training_protocol,
                "input_files": runner._training_input_identities(),
            },
        }
    )
    torch.save(payload, checkpoint_path)
    return payload


def test_core_counts_and_fixed_seeds() -> None:
    grid = build_experiment_grid(MANIFEST, CONFIG, suite="core")
    assert grid.condition_counts == CORE_EXPECTED_COUNTS
    assert len(grid.conditions) == 156
    assert len(grid.scenarios) == 156 * 20
    assert grid.mask_seeds == tuple(range(101, 121))
    assert grid.training_seeds == (11, 22, 33, 44, 55)
    assert {scenario.mask_seed for scenario in grid.scenarios} == set(range(101, 121))


def test_full_grid_has_windows_protocols_and_honest_validation_labels() -> None:
    grid = build_experiment_grid(MANIFEST, CONFIG, suite="full")
    assert len(grid.conditions) == 300
    assert len(grid.scenarios) == 5_943
    assert {
        condition.window_length
        for condition in grid.conditions
        if condition.experiment == "M8"
    } == {
        184,
        368,
        736,
    }
    assert {
        condition.training_protocol
        for condition in grid.conditions
        if condition.experiment == "M9"
    } == {"seen_length", "unseen_length"}
    loso = [condition for condition in grid.conditions if condition.experiment == "M10"]
    assert len(loso) == 3
    assert all(
        condition.validation_scope
        == "exploratory_internal_loso_not_external_validation"
        for condition in loso
    )
    assert {
        scenario.mask_seed
        for scenario in grid.scenarios
        if scenario.condition.experiment == "M10"
    } == {101}
    assert grid.external_validation_status == "unavailable"
    synchronous = [
        condition
        for condition in grid.conditions
        if condition.experiment == "M6" and condition.overlap_ratio == 1.0
    ]
    assert synchronous
    assert all(condition.mask_type == "network_outage" for condition in synchronous)


def test_training_masks_are_fixed_and_unseen_protocol_excludes_180_day_blocks() -> None:
    values = np.ones((2_000, 24), dtype=float)
    first = make_training_mask(values, 11, "unseen_length")
    second = make_training_mask(values, 11, "unseen_length")
    seen = make_training_mask(values, 11, "seen_length")
    seen_repeat = make_training_mask(values, 11, "seen_length")
    different_seed = make_training_mask(values, 22, "seen_length")
    formal_seen = make_training_mask(values, 11, "seen_length", repeats=5)
    formal_unseen = make_training_mask(values, 11, "unseen_length", repeats=5)
    assert np.array_equal(first, second)
    assert np.array_equal(seen, seen_repeat)
    assert not np.array_equal(seen, different_seed)
    assert not np.any(first & ~np.isfinite(values))

    def runs(column: np.ndarray) -> list[int]:
        padded = np.pad(column.astype(int), (1, 1))
        changes = np.flatnonzero(np.diff(padded))
        return [int(value) for value in changes[1::2] - changes[::2]]

    for index in (0, 8, 16):
        assert set(runs(seen[:, index])) == {10, 30, 90, 180}
        assert set(runs(first[:, index])) == {10, 30, 90}
    assert all(max(runs(first[:, index])) <= 90 for index in range(first.shape[1]))
    assert all(max(runs(seen[:, index])) == 180 for index in range(seen.shape[1]))
    for index in range(values.shape[1]):
        assert (
            sorted(runs(formal_seen[:, index]))
            == [10] * 5 + [30] * 5 + [90] * 5 + [180] * 5
        )
        assert sorted(runs(formal_unseen[:, index])) == [10] * 5 + [30] * 5 + [90] * 5


def test_smoke_and_formal_training_profiles_are_separate(tmp_path: Path) -> None:
    smoke_root = tmp_path / "smoke"
    smoke_root.mkdir()
    smoke = _runner(smoke_root, models=("climatology",))
    formal_grid = build_experiment_grid(MANIFEST, CONFIG, suite="core")
    formal_root = tmp_path / "formal"
    formal_root.mkdir()
    formal = ExperimentRunner(
        formal_grid,
        wide_path=_wide_data(formal_root / "wide.parquet"),
        quality_path=None,
        output_dir=formal_root / "results",
        mask_dir=formal_root / "masks",
        config_path=CONFIG,
        models=("climatology",),
    )
    assert smoke.training_profile_name == "smoke"
    assert smoke.training_settings["train_mask_repeats"] == 1
    assert formal.training_profile_name == "formal"
    assert formal.training_settings == {
        "train_mask_repeats": 5,
        "validation_mask_repeats": 1,
        "deep_epochs": 50,
        "deep_patience": 8,
        "proposed_epochs": 20,
        "proposed_patience": 5,
        "batch_size": 8,
        "device": "cpu",
    }


def test_full_artificial_mask_hides_every_selected_channel() -> None:
    values = np.arange(5 * 3 * 8, dtype=float).reshape(5, 3, 8)
    mask = np.zeros_like(values, dtype=bool)
    mask[1:4, 0, [0, 1, 2, 3, 4, 5, 6, 7]] = True
    masked = apply_full_artificial_mask(values, mask)
    assert np.isnan(masked[mask]).all()
    np.testing.assert_array_equal(masked[~mask], values[~mask])


def test_generated_full_site_mask_is_complete_3d_and_test_only(tmp_path: Path) -> None:
    runner = _runner(tmp_path, models=("climatology",))
    core = build_experiment_grid(MANIFEST, CONFIG, suite="core")
    condition = next(
        value
        for value in core.conditions
        if value.experiment == "M4"
        and value.station_ids == ("B1",)
        and value.outage_mode == "full-site"
        and value.gap_length == 10
    )
    mask, metadata = runner._generate_mask(ExperimentScenario(condition, 101))
    assert mask.shape == runner.data.values.shape
    assert mask.dtype == np.bool_
    assert not mask[~runner.test_rows].any()
    station_mask = mask[:, runner.data.station_ids.index("B1")]
    assert station_mask.sum() == 10 * len(VARIABLES)
    assert np.all(station_mask.any(axis=1) == station_mask.all(axis=1))
    assert metadata["fit_split"] == "train"
    assert metadata["tuning_split"] == "validation"
    assert metadata["evaluation_split"] == "test"


def test_masks_use_one_shared_axis_and_compact_packbits(tmp_path: Path) -> None:
    runner = _runner(tmp_path, models=("climatology",))
    scenario = runner.grid.scenarios[0]
    first, metadata = runner._generate_mask(scenario)
    second, loaded_metadata = runner._generate_mask(scenario)
    np.testing.assert_array_equal(second, first)
    assert loaded_metadata == json.loads(json.dumps(metadata))

    axes = json.loads((runner.mask_dir / "axes.json").read_text(encoding="utf-8"))
    scenario_metadata = json.loads(
        (runner.mask_dir / "scenarios" / f"{scenario.scenario_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert axes["shape"] == list(first.shape)
    assert "axes" not in scenario_metadata
    assert "date" not in scenario_metadata
    with np.load(
        runner.mask_dir / "scenarios" / f"{scenario.scenario_id}.npz"
    ) as archive:
        assert archive["packed"].size == (first.size + 7) // 8


def test_cached_mask_rejects_changed_axes_and_rebuilds_changed_quality_or_metadata(
    tmp_path: Path,
) -> None:
    runner = _runner(tmp_path, models=("climatology",))
    scenario = runner.grid.scenarios[0]
    original_mask, _ = runner._generate_mask(scenario)
    axes_path = runner.mask_dir / "axes.json"
    original_axes = json.loads(axes_path.read_text(encoding="utf-8"))

    changed_axes = dict(original_axes)
    changed_axes["date"] = list(original_axes["date"])
    changed_axes["date"][0] = "1999-01-01"
    axes_path.write_text(json.dumps(changed_axes), encoding="utf-8")
    with pytest.raises(ValueError, match="axes"):
        runner._generate_mask(scenario)

    axes_path.write_text(json.dumps(original_axes), encoding="utf-8")
    position = tuple(np.argwhere(original_mask)[0])
    runner.data.quality_approved[position] = False
    rebuilt_mask, _ = runner._generate_mask(scenario)
    assert not rebuilt_mask[position]

    metadata_path = (
        runner.mask_dir / "scenarios" / f"{scenario.scenario_id}.json"
    )
    changed_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    changed_metadata["window_length"] += 1
    metadata_path.write_text(json.dumps(changed_metadata), encoding="utf-8")
    _, repaired_metadata = runner._generate_mask(scenario)
    assert repaired_metadata["window_length"] == scenario.condition.window_length


def test_event_thresholds_use_only_approved_finite_training_values(
    tmp_path: Path,
) -> None:
    grid = build_experiment_grid(MANIFEST, CONFIG, suite="full")
    runner = ExperimentRunner(
        grid,
        wide_path=_wide_data(tmp_path / "wide.parquet"),
        quality_path=None,
        output_dir=tmp_path / "results",
        mask_dir=tmp_path / "masks",
        config_path=CONFIG,
        models=("climatology",),
    )
    for event_type in ("high_temperature", "rapid_warming"):
        scenario = next(
            value
            for value in grid.scenarios
            if value.condition.experiment == "M7"
            and value.condition.event_type == event_type
        )
        station = runner.data.station_ids.index(scenario.condition.station_ids[0])
        variable = runner.data.variable_names.index("T")
        index = int(np.flatnonzero(runner.train_rows)[100])
        runner.data.quality_approved[index, station, variable] = False
        before = runner._event_condition(scenario)
        runner.data.values[index, station, variable] = 1_000_000.0
        after = runner._event_condition(scenario)
        np.testing.assert_array_equal(after, before)

    high_temperature = next(
        value
        for value in grid.scenarios
        if value.condition.experiment == "M7"
        and value.condition.event_type == "high_temperature"
    )
    station = runner.data.station_ids.index(
        high_temperature.condition.station_ids[0]
    )
    target = runner.data.variable_names.index("T")
    runner.data.quality_approved[runner.train_rows, station, target] = False
    with pytest.raises(ValueError, match="no approved finite training"):
        runner._event_condition(high_temperature)


def test_rapid_warming_threshold_requires_adjacent_approved_training_pairs(
    tmp_path: Path,
) -> None:
    grid = build_experiment_grid(MANIFEST, CONFIG, suite="full")
    runner = ExperimentRunner(
        grid,
        wide_path=_wide_data(tmp_path / "wide.parquet"),
        quality_path=None,
        output_dir=tmp_path / "results",
        mask_dir=tmp_path / "masks",
        config_path=CONFIG,
        models=("climatology",),
    )
    scenario = next(
        value
        for value in grid.scenarios
        if value.condition.experiment == "M7"
        and value.condition.event_type == "rapid_warming"
    )
    station = runner.data.station_ids.index(scenario.condition.station_ids[0])
    target = runner.data.variable_names.index("T")
    train_indices = np.flatnonzero(runner.train_rows)
    runner.data.quality_approved[train_indices, station, target] = False
    runner.data.quality_approved[train_indices[::2], station, target] = True
    with pytest.raises(ValueError, match="no adjacent approved finite training"):
        runner._event_condition(scenario)


def test_existing_baselines_are_runner_models_and_only_trainable_models_repeat_seeds(
    tmp_path: Path,
) -> None:
    expected = {
        "air_only",
        "air_hydro",
        "donor_regression",
        "random_forest",
        "xgboost",
        "rating_curve",
        "independent_flow",
    }
    assert expected.issubset(SUPPORTED_MODELS)
    grid = build_experiment_grid(MANIFEST, CONFIG, suite="core")
    runner = ExperimentRunner(
        grid,
        wide_path=_wide_data(tmp_path / "wide.parquet"),
        quality_path=None,
        output_dir=tmp_path / "results",
        mask_dir=tmp_path / "masks",
        config_path=CONFIG,
        models=("climatology", "air_only", "brits", "proposed"),
        training_seeds=(11, 22),
    )
    assert runner._run_keys() == [
        ("climatology", None),
        ("air_only", None),
        ("brits", 11),
        ("brits", 22),
        ("proposed", 11),
        ("proposed", 22),
    ]


def test_air_hydro_prediction_cannot_see_masked_auxiliary_truth(tmp_path: Path) -> None:
    runner = _runner(tmp_path, models=("air_hydro",))
    core = build_experiment_grid(MANIFEST, CONFIG, suite="core")
    condition = next(
        value
        for value in core.conditions
        if value.experiment == "M4"
        and value.station_ids == ("B1",)
        and value.outage_mode == "full-site"
        and value.gap_length == 10
    )
    mask, _ = runner._generate_mask(ExperimentScenario(condition, 101))
    station = runner.data.station_ids.index("B1")
    target = runner.data.variable_names.index("T")
    first = runner._traditional_prediction("air_hydro", station, target, mask)
    runner.data.values[mask] += 100_000.0
    second = runner._traditional_prediction("air_hydro", station, target, mask)
    np.testing.assert_allclose(
        second[mask[:, station, target]], first[mask[:, station, target]]
    )


def test_deep_prediction_is_stitched_from_condition_sized_windows(
    tmp_path: Path, monkeypatch
) -> None:
    runner = _runner(tmp_path, models=("saits",))
    scenario = runner.grid.scenarios[0]
    mask, _ = runner._generate_mask(scenario)
    calls: list[int] = []

    class FakeImputer:
        def predict(
            self, values: np.ndarray, artificial_mask: np.ndarray
        ) -> np.ndarray:
            calls.append(len(values))
            result = values.copy()
            result[artificial_mask] = 123.0
            return result

    monkeypatch.setattr(runner, "_deep_model", lambda *args: FakeImputer())
    prediction, _ = runner._model_prediction("saits", 11, scenario, mask)
    assert calls
    assert max(calls) <= scenario.condition.window_length
    assert max(calls) < len(runner.data.dates)
    np.testing.assert_array_equal(prediction[mask], 123.0)


def test_proposed_scaler_is_train_only_and_is_recorded_in_checkpoint(
    tmp_path: Path, monkeypatch
) -> None:
    runner = _runner(tmp_path, models=("proposed",))
    expected = runner.data.values[runner.train_rows].mean(axis=0)
    runner.data.values[~runner.train_rows] += 1_000_000.0
    mean, scale = runner._proposed_scaler()
    np.testing.assert_allclose(mean, expected, rtol=1e-5)
    assert np.all(scale > 0)

    def fake_train(
        model, train_batches, validation_batches, config, *, checkpoint_path
    ):
        assert list(train_batches) and list(validation_batches)
        _write_synthetic_proposed_checkpoint(model, config, checkpoint_path)

    monkeypatch.setattr(
        "stream_recoverability.experiments.runner.train_proposed_model", fake_train
    )
    runner._proposed_model(11, 184, "seen_length")
    checkpoint = torch.load(
        runner.output_dir / "checkpoints" / "proposed-S11-W184-seen_length.pt",
        map_location="cpu",
        weights_only=False,
    )
    np.testing.assert_allclose(checkpoint["train_scaler"]["mean"], mean)
    np.testing.assert_allclose(checkpoint["train_scaler"]["scale"], scale)
    assert checkpoint["quantile_levels"] == [0.05, 0.25, 0.5, 0.75, 0.95]
    assert checkpoint["training_config"]["epochs"] == 3
    assert checkpoint["training_config"]["patience"] == 2
    assert checkpoint["training_context"] == {
        "profile": "smoke",
        "train_mask_repeats": 1,
        "validation_mask_repeats": 1,
        "window": 184,
        "protocol": "seen_length",
        "input_files": runner._training_input_identities(),
    }


def test_proposed_initialization_is_seeded_before_construction(
    tmp_path: Path, monkeypatch
) -> None:
    initial_states: list[torch.Tensor] = []

    def fake_train(
        model, train_batches, validation_batches, config, *, checkpoint_path
    ):
        initial_states.append(
            torch.cat(
                [
                    value.detach().reshape(-1).cpu()
                    for value in model.state_dict().values()
                ]
            )
        )
        _write_synthetic_proposed_checkpoint(model, config, checkpoint_path)

    monkeypatch.setattr(
        "stream_recoverability.experiments.runner.train_proposed_model", fake_train
    )
    for name, seed in (("first", 11), ("repeat", 11), ("different", 22)):
        root = tmp_path / name
        root.mkdir()
        runner = _runner(root, models=("proposed",))
        runner._proposed_model(seed, 184, "seen_length")
    torch.testing.assert_close(initial_states[0], initial_states[1])
    assert not torch.equal(initial_states[0], initial_states[2])


def test_proposed_prediction_uses_requested_windows_and_only_covers_hidden_t(
    tmp_path: Path, monkeypatch
) -> None:
    runner = _runner(tmp_path, models=("proposed",))
    base = runner.grid.scenarios[0]
    artificial, metadata = runner._generate_mask(base)
    calls: list[int] = []

    class FakeProposed:
        def eval(self):
            return self

        def __call__(self, values, natural, hidden, *, seasonal_features):
            steps = values.shape[1]
            calls.append(steps)
            median = torch.full(
                (1, steps, values.shape[2]), float(steps), dtype=values.dtype
            )
            return {
                "quantiles": torch.stack(
                    (median - 2.0, median - 1.0, median, median + 1.0, median + 2.0),
                    dim=-1,
                )
            }

    mean = np.zeros(runner.data.values.shape[1:], dtype=np.float32)
    scale = np.ones_like(mean)
    monkeypatch.setattr(
        runner, "_proposed_model", lambda *args: (FakeProposed(), mean, scale)
    )
    target = runner.data.variable_names.index("T")
    target_hidden = artificial[..., target]
    for window in (184, 368, 736):
        calls.clear()
        condition = replace(
            base.condition,
            condition_id=f"{base.condition.condition_id}-W{window}",
            window_length=window,
        )
        prediction, quantiles = runner._model_prediction(
            "proposed", 11, ExperimentScenario(condition, 101), artificial
        )
        assert calls and set(calls) == {window}
        assert np.isfinite(prediction[..., target][target_hidden]).all()
        assert np.isnan(prediction[..., target][~target_hidden]).all()
        assert np.isnan(prediction[..., 1:]).all()
        np.testing.assert_allclose(
            prediction[..., target][target_hidden], float(window)
        )
        assert quantiles is not None
        np.testing.assert_allclose(quantiles["q25"][target_hidden], float(window) - 1.0)
        assert np.isfinite(quantiles["q50"][target_hidden]).all()
        np.testing.assert_allclose(quantiles["q75"][target_hidden], float(window) + 1.0)
        assert np.isnan(quantiles["q50"][~target_hidden]).all()

    daily, _, skips = runner._prediction_rows(
        base, metadata, artificial, "proposed", 11
    )
    assert not skips
    np.testing.assert_allclose(daily["q25"], daily["y_pred"] - 1.0)
    np.testing.assert_allclose(daily["q75"], daily["y_pred"] + 1.0)


def test_internal_loso_runs_and_never_uses_held_out_temperature_labels(
    tmp_path: Path,
) -> None:
    grid = build_experiment_grid(MANIFEST, CONFIG, suite="full")
    runner = ExperimentRunner(
        grid,
        wide_path=_wide_data(tmp_path / "wide.parquet"),
        quality_path=None,
        output_dir=tmp_path / "results",
        mask_dir=tmp_path / "masks",
        config_path=CONFIG,
        models=("climatology",),
    )
    scenario = next(
        value for value in grid.scenarios if value.condition.experiment == "M10"
    )
    station = runner.data.station_ids.index(str(scenario.condition.held_out_station))
    target = runner.data.variable_names.index("T")
    first = runner._pooled_loso_prediction(station)[1].copy()
    runner.data.values[runner.train_rows | runner.validation_rows, station, target] += (
        100_000.0
    )
    runner._loso_cache.clear()
    second = runner._pooled_loso_prediction(station)[1]
    np.testing.assert_allclose(second, first)

    assert runner._run_scenario(scenario) == "complete"
    status = json.loads(
        (
            runner.output_dir / "scenarios" / scenario.scenario_id / "status.json"
        ).read_text(encoding="utf-8")
    )
    events = pd.read_parquet(
        runner.output_dir / "scenarios" / scenario.scenario_id / "event_metrics.parquet"
    )
    assert status["completed_runs"] == ["pooled_loso:none"]
    assert set(events["model"]) == {"pooled_loso"}
    assert set(events["validation_scope"]) == {
        "exploratory_internal_loso_not_external_validation"
    }
    assert not events["is_external_validation"].any()


def test_training_references_and_metric_definitions_ignore_nontraining_truth(
    tmp_path: Path,
) -> None:
    wide_path = _wide_data(tmp_path / "wide.parquet")
    grid = build_experiment_grid(MANIFEST, CONFIG, suite="full")
    first_runner = ExperimentRunner(
        grid,
        wide_path=wide_path,
        quality_path=None,
        output_dir=tmp_path / "first_results",
        mask_dir=tmp_path / "first_masks",
        config_path=CONFIG,
        models=("climatology",),
    )
    conditions = {
        variable: next(
            condition
            for condition in grid.conditions
            if condition.station_ids == ("B1",)
            and condition.variables == (variable,)
            and condition.gap_length == 30
            and condition.mask_type == "block"
        )
        for variable in ("T", "F", "L")
    }
    first_events = {}
    masks = {}
    for variable, condition in conditions.items():
        scenario = ExperimentScenario(condition, 101)
        mask, metadata = first_runner._generate_mask(scenario)
        masks[variable] = mask
        _, events, _ = first_runner._prediction_rows(
            scenario, metadata, mask, "climatology", None
        )
        first_events[variable] = events.iloc[0]

    changed = pd.read_parquet(wide_path)
    nontraining = changed["split"].ne("train").to_numpy()
    station = first_runner.data.station_ids.index("B1")
    for variable in ("T", "F", "L"):
        variable_index = first_runner.data.variable_names.index(variable)
        hidden = masks[variable][:, station, variable_index]
        changed.loc[nontraining & ~hidden, f"B1_{variable}"] += 1_000_000.0
    changed_path = tmp_path / "changed.parquet"
    changed.to_parquet(changed_path, index=False)
    second_runner = ExperimentRunner(
        grid,
        wide_path=changed_path,
        quality_path=None,
        output_dir=tmp_path / "second_results",
        mask_dir=tmp_path / "second_masks",
        config_path=CONFIG,
        models=("climatology",),
    )

    threshold_fields = {
        "T": ("high_temp_threshold",),
        "F": ("high_flow_threshold", "low_flow_threshold"),
        "L": ("high_level_threshold",),
    }
    for variable, condition in conditions.items():
        variable_index = first_runner.data.variable_names.index(variable)
        first_reference = first_runner._training_reference(station, variable_index)
        second_reference = second_runner._training_reference(station, variable_index)
        assert first_reference == second_reference
        scenario = ExperimentScenario(condition, 101)
        mask, metadata = second_runner._generate_mask(scenario)
        _, events, _ = second_runner._prediction_rows(
            scenario, metadata, mask, "climatology", None
        )
        second_event = events.iloc[0]
        for field in (*threshold_fields[variable], "NMAE", "NRMSE"):
            assert second_event[field] == first_events[variable][field]
        if variable == "T":
            assert pd.isna(first_events[variable]["ecological_threshold"])
            assert pd.isna(second_event["ecological_threshold"])
        assert (
            second_event["NMAE"] == first_events[variable]["MAE"] / first_reference.iqr
        )
        assert (
            second_event["NRMSE"]
            == first_events[variable]["RMSE"] / first_reference.std
        )


def test_aggregate_is_limited_to_current_grid_and_models(tmp_path: Path) -> None:
    runner = _runner(tmp_path, models=("climatology",))
    runner.run(max_scenarios=1)
    partial_manifest = json.loads(
        (runner.output_dir / "run_manifest.json").read_text(encoding="utf-8")
    )
    assert partial_manifest["selected_scenarios"] == 1
    assert partial_manifest["grid_scenario_count"] == len(runner.grid.scenarios)
    assert partial_manifest["complete"] is False
    scenario = runner.grid.scenarios[0]
    scenario_dir = runner.output_dir / "scenarios" / scenario.scenario_id
    daily = pd.read_parquet(scenario_dir / "daily_predictions.parquet")
    events = pd.read_parquet(scenario_dir / "event_metrics.parquet")

    historical_daily = daily.iloc[[0]].copy()
    historical_daily["model"] = "historical_model"
    historical_events = events.iloc[[0]].copy()
    historical_events["model"] = "historical_model"
    pd.concat((daily, historical_daily), ignore_index=True).to_parquet(
        scenario_dir / "daily_predictions.parquet", index=False
    )
    pd.concat((events, historical_events), ignore_index=True).to_parquet(
        scenario_dir / "event_metrics.parquet", index=False
    )

    foreign_dir = runner.output_dir / "scenarios" / "FOREIGN-SUITE-R0101"
    foreign_dir.mkdir(parents=True)
    foreign_daily = daily.iloc[[0]].copy()
    foreign_daily["scenario_id"] = "FOREIGN-SUITE-R0101"
    foreign_events = events.iloc[[0]].copy()
    foreign_events["scenario_id"] = "FOREIGN-SUITE-R0101"
    foreign_daily.to_parquet(foreign_dir / "daily_predictions.parquet", index=False)
    foreign_events.to_parquet(foreign_dir / "event_metrics.parquet", index=False)

    aggregated_daily, aggregated_events = runner._aggregate()
    assert "FOREIGN-SUITE-R0101" not in set(aggregated_daily["scenario_id"])
    assert "FOREIGN-SUITE-R0101" not in set(aggregated_events["scenario_id"])
    assert set(aggregated_daily["model"]) == {"climatology"}
    assert set(aggregated_events["model"]) == {"climatology"}

    full = build_experiment_grid(MANIFEST, CONFIG, suite="full")
    loso = next(
        scenario
        for scenario in full.scenarios
        if scenario.condition.mask_type == "loso"
    )
    runner.grid = replace(
        full,
        conditions=(loso.condition,),
        scenarios=(loso,),
        mask_seeds=(loso.mask_seed,),
    )
    loso_dir = runner.output_dir / "scenarios" / loso.scenario_id
    loso_dir.mkdir(parents=True)
    loso_daily = daily.iloc[[0]].copy()
    loso_daily["scenario_id"] = loso.scenario_id
    loso_daily["model"] = "pooled_loso"
    loso_daily["training_seed"] = np.nan
    loso_events = events.iloc[[0]].copy()
    loso_events["scenario_id"] = loso.scenario_id
    loso_events["model"] = "pooled_loso"
    loso_events["training_seed"] = np.nan
    loso_daily.to_parquet(loso_dir / "daily_predictions.parquet", index=False)
    loso_events.to_parquet(loso_dir / "event_metrics.parquet", index=False)
    aggregated_daily, aggregated_events = runner._aggregate()
    assert aggregated_daily.empty
    assert aggregated_events.empty

    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    empty = _runner(empty_root, models=("climatology",))
    empty.output_dir.mkdir(parents=True)
    daily.to_parquet(empty.output_dir / "daily_predictions.parquet", index=False)
    events.to_parquet(empty.output_dir / "event_metrics.parquet", index=False)
    empty_daily, empty_events = empty._aggregate()
    assert empty_daily.empty and empty_events.empty
    assert pd.read_parquet(empty.output_dir / "daily_predictions.parquet").empty
    assert pd.read_parquet(empty.output_dir / "event_metrics.parquet").empty


def test_old_proposed_checkpoint_without_scaler_requires_structured_retraining(
    tmp_path: Path,
) -> None:
    runner = _runner(tmp_path, models=("proposed",))
    scenario = runner.grid.scenarios[0]
    model = MissingAwareMultisourceImputer(
        ProposedModelConfig(
            station_ids=runner.data.station_ids,
            variable_names=runner.data.variable_names,
            hidden_size=24,
            dropout=0.0,
        )
    )
    checkpoint = (
        runner.output_dir
        / "checkpoints"
        / f"proposed-S11-W{scenario.condition.window_length}-{scenario.condition.training_protocol}.pt"
    )
    checkpoint.parent.mkdir(parents=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "model_config": asdict(model.config),
            "quantile_levels": list(model.quantile_levels),
        },
        checkpoint,
    )
    assert runner._run_scenario(scenario) == "retryable_failure"
    status_path = runner.output_dir / "scenarios" / scenario.scenario_id / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["status"] == "retryable_failure"
    assert status["completed_runs"] == []
    assert status["retryable_run_keys"] == ["proposed:11"]
    assert (
        status["skipped_runs"][0]["reason_code"] == "checkpoint_missing_training_scaler"
    )
    assert status["skipped_runs"][0]["required_action"] == "retrain_proposed_model"
    quarantined = Path(status["skipped_runs"][0]["quarantined_checkpoint"])
    assert not checkpoint.exists() and quarantined.exists()
    assert "train_scaler" not in torch.load(quarantined, weights_only=False)

    # A retraining-required skip is retryable and must not suppress the next attempt.
    assert runner._run_scenario(scenario) == "complete"
    repaired = json.loads(status_path.read_text(encoding="utf-8"))
    assert repaired["status"] == "complete"
    assert repaired["completed_runs"] == ["proposed:11"]
    assert repaired["retryable_run_keys"] == []
    assert checkpoint.exists()


def test_three_quantile_checkpoint_requires_structured_retraining(
    tmp_path: Path,
) -> None:
    runner = _runner(tmp_path, models=("proposed",))
    scenario = runner.grid.scenarios[0]
    model = MissingAwareMultisourceImputer(
        ProposedModelConfig(
            station_ids=runner.data.station_ids,
            variable_names=runner.data.variable_names,
            hidden_size=24,
            dropout=0.0,
        )
    )
    legacy_state = model.state_dict()
    legacy_state["quantile_head.2.weight"] = legacy_state["quantile_head.2.weight"][
        :3
    ].clone()
    legacy_state["quantile_head.2.bias"] = legacy_state["quantile_head.2.bias"][
        :3
    ].clone()
    mean, scale = runner._proposed_scaler()
    checkpoint = (
        runner.output_dir
        / "checkpoints"
        / f"proposed-S11-W{scenario.condition.window_length}-{scenario.condition.training_protocol}.pt"
    )
    checkpoint.parent.mkdir(parents=True)
    torch.save(
        {
            "model_state_dict": legacy_state,
            "model_config": asdict(model.config),
            "quantile_levels": [0.05, 0.5, 0.95],
            "train_scaler": {
                "mean": mean.tolist(),
                "scale": scale.tolist(),
                "station_ids": list(runner.data.station_ids),
                "variable_names": list(runner.data.variable_names),
            },
        },
        checkpoint,
    )

    assert runner._run_scenario(scenario) == "retryable_failure"
    status = json.loads(
        (
            runner.output_dir / "scenarios" / scenario.scenario_id / "status.json"
        ).read_text(encoding="utf-8")
    )
    skip = status["skipped_runs"][0]
    assert skip["reason_code"] == "checkpoint_incompatible_model"
    assert skip["required_action"] == "retrain_proposed_model"
    assert "five-quantile architecture" in skip["reason"]
    quarantined = Path(skip["quarantined_checkpoint"])
    stored = torch.load(quarantined, map_location="cpu", weights_only=False)
    assert stored["model_state_dict"]["quantile_head.2.weight"].shape[0] == 3


def test_checkpoint_quantile_metadata_must_match_five_levels(tmp_path: Path) -> None:
    for case, quantile_levels in (
        ("missing", None),
        ("three-level", [0.05, 0.5, 0.95]),
    ):
        root = tmp_path / case
        root.mkdir()
        runner = _runner(root, models=("proposed",))
        scenario = runner.grid.scenarios[0]
        model = MissingAwareMultisourceImputer(
            ProposedModelConfig(
                station_ids=runner.data.station_ids,
                variable_names=runner.data.variable_names,
                hidden_size=24,
                dropout=0.0,
            )
        )
        mean, scale = runner._proposed_scaler()
        checkpoint = (
            runner.output_dir
            / "checkpoints"
            / f"proposed-S11-W{scenario.condition.window_length}-{scenario.condition.training_protocol}.pt"
        )
        checkpoint.parent.mkdir(parents=True)
        payload = {
            "model_state_dict": model.state_dict(),
            "model_config": asdict(model.config),
            "train_scaler": {
                "mean": mean.tolist(),
                "scale": scale.tolist(),
                "station_ids": list(runner.data.station_ids),
                "variable_names": list(runner.data.variable_names),
            },
        }
        if quantile_levels is not None:
            payload["quantile_levels"] = quantile_levels
        torch.save(payload, checkpoint)

        assert runner._run_scenario(scenario) == "retryable_failure"
        status = json.loads(
            (
                runner.output_dir / "scenarios" / scenario.scenario_id / "status.json"
            ).read_text(encoding="utf-8")
        )
        skip = status["skipped_runs"][0]
        assert skip["reason_code"] == "checkpoint_incompatible_quantiles"
        assert skip["required_action"] == "retrain_proposed_model"


def test_proposed_checkpoint_axes_must_match_current_data(tmp_path: Path) -> None:
    runner = _runner(tmp_path, models=("proposed",))
    scenario = runner.grid.scenarios[0]
    reversed_stations = tuple(reversed(runner.data.station_ids))
    model = MissingAwareMultisourceImputer(
        ProposedModelConfig(
            station_ids=reversed_stations,
            variable_names=runner.data.variable_names,
            hidden_size=24,
            dropout=0.0,
        )
    )
    mean, scale = runner._proposed_scaler()
    checkpoint = (
        runner.output_dir
        / "checkpoints"
        / f"proposed-S11-W{scenario.condition.window_length}-{scenario.condition.training_protocol}.pt"
    )
    checkpoint.parent.mkdir(parents=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "model_config": asdict(model.config),
            "quantile_levels": list(model.quantile_levels),
            "train_scaler": {
                "mean": mean.tolist(),
                "scale": scale.tolist(),
                "station_ids": list(runner.data.station_ids),
                "variable_names": list(runner.data.variable_names),
            },
        },
        checkpoint,
    )

    assert runner._run_scenario(scenario) == "retryable_failure"
    status = json.loads(
        (runner.output_dir / "scenarios" / scenario.scenario_id / "status.json").read_text(
            encoding="utf-8"
        )
    )
    assert status["skipped_runs"][0]["reason_code"] == "checkpoint_incompatible_axes"


def test_smoke_runner_scores_only_masked_cells_and_resume_deduplicates(
    tmp_path: Path,
) -> None:
    runner = _runner(tmp_path)
    first_daily, first_events = runner.run()
    run_manifest = json.loads(
        (runner.output_dir / "run_manifest.json").read_text(encoding="utf-8")
    )
    assert run_manifest["grid_scenario_count"] == len(runner.grid.scenarios)
    assert run_manifest["expected_run_count"] == len(runner.grid.scenarios) * 2
    assert (
        run_manifest["completed_status_run_count"] == run_manifest["expected_run_count"]
    )
    assert run_manifest["aggregate_scenario_count"] == len(runner.grid.scenarios)
    assert run_manifest["aggregate_run_count"] == run_manifest["expected_run_count"]
    assert run_manifest["complete"] is True
    assert len(first_events) == 12
    assert {"q25", "q75", "season", "event_type"}.issubset(first_daily)
    assert set(first_daily["season"]) <= {"DJF", "MAM", "JJA", "SON"}
    assert np.isfinite(pd.to_numeric(first_daily["y_true"], errors="coerce")).all()
    assert np.isfinite(pd.to_numeric(first_daily["y_pred"], errors="coerce")).all()
    assert np.isfinite(pd.to_numeric(first_events["MAE"], errors="coerce")).all()
    assert np.isfinite(pd.to_numeric(first_events["RMSE"], errors="coerce")).all()
    assert set(
        first_events.loc[first_events["experiment"] == "M4", "failed_stations"]
    ) == {'["B1"]'}
    assert set(
        first_events.loc[first_events["experiment"] != "M4", "failed_stations"]
    ) == {"[]"}
    assert first_daily["artificial_mask"].all()
    assert first_daily["quality_approved"].all()
    assert not first_daily.duplicated(
        [
            "scenario_id",
            "model",
            "training_seed",
            "mask_seed",
            "date",
            "station_id",
            "target",
        ]
    ).any()
    assert not first_events.duplicated(
        ["scenario_id", "model", "training_seed", "mask_seed", "station_id", "target"]
    ).any()
    assert set(first_events["fit_split"]) == {"train"}
    assert set(first_events["tuning_split"]) == {"validation"}
    assert set(first_events["evaluation_split"]) == {"test"}

    for row in first_events.itertuples(index=False):
        library = runner._generate_mask(
            next(
                scenario
                for scenario in runner.grid.scenarios
                if scenario.scenario_id == row.scenario_id
            )
        )[0]
        station = runner.data.station_ids.index(row.station_id)
        variable = runner.data.variable_names.index(row.target)
        expected = int(
            (
                library[:, station, variable]
                & runner.data.quality_approved[:, station, variable]
            ).sum()
        )
        assert row.n_evaluated == expected

    second_runner = ExperimentRunner(
        runner.grid,
        wide_path=tmp_path / "wide.parquet",
        quality_path=None,
        output_dir=tmp_path / "results",
        mask_dir=tmp_path / "masks",
        config_path=CONFIG,
        models=("climatology", "linear"),
        resume=True,
    )
    second_daily, second_events = second_runner.run()
    assert len(second_daily) == len(first_daily)
    assert len(second_events) == len(first_events)
    assert not second_daily.duplicated(
        [
            "scenario_id",
            "model",
            "training_seed",
            "mask_seed",
            "date",
            "station_id",
            "target",
        ]
    ).any()
    assert not second_events.duplicated(
        ["scenario_id", "model", "training_seed", "mask_seed", "station_id", "target"]
    ).any()


def test_unidentifiable_rating_curve_is_structurally_skipped(tmp_path: Path) -> None:
    runner = _runner(tmp_path, models=("rating_curve",))
    scenario = next(
        value
        for value in runner.grid.scenarios
        if value.condition.experiment == "M4"
        and value.condition.outage_mode == "hydro-only"
    )
    assert runner._run_scenario(scenario) == "complete"
    scenario_dir = runner.output_dir / "scenarios" / scenario.scenario_id
    status = json.loads((scenario_dir / "status.json").read_text(encoding="utf-8"))
    assert status["completed_runs"] == ["rating_curve:none"]
    assert status["skipped_run_count"] == 3
    skipped = next(row for row in status["skipped_runs"] if row["target"] == "F")
    assert skipped["run_key"] == "rating_curve:none"
    assert skipped["target"] == "F"
    assert skipped["reason_code"] == "required_input_unavailable"
    assert skipped["required_inputs"] == ["B1_L"]
    assert not (scenario_dir / "daily_predictions.parquet").exists()
    assert not (scenario_dir / "event_metrics.parquet").exists()

    assert runner._run_scenario(scenario) == "complete"
    resumed = json.loads((scenario_dir / "status.json").read_text(encoding="utf-8"))
    assert resumed["skipped_runs"] == status["skipped_runs"]


def test_nonfinite_model_output_is_not_marked_complete(
    tmp_path: Path, monkeypatch
) -> None:
    runner = _runner(tmp_path, models=("linear",))
    scenario = runner.grid.scenarios[0]

    monkeypatch.setattr(
        runner,
        "_prediction_rows",
        lambda *args: (
            pd.DataFrame(),
            pd.DataFrame(),
            [
                {
                    "run_key": "linear:none",
                    "model": "linear",
                    "training_seed": None,
                    "station_id": "B1",
                    "target": "T",
                    "reason_code": "nonfinite_prediction",
                    "reason": "test failure",
                }
            ],
        ),
    )

    assert runner._run_scenario(scenario) == "retryable_failure"
    status = json.loads(
        (runner.output_dir / "scenarios" / scenario.scenario_id / "status.json").read_text(
            encoding="utf-8"
        )
    )
    assert status["completed_runs"] == []
    assert status["retryable_run_keys"] == ["linear:none"]
    assert status["skipped_runs"][0]["required_action"] == "rerun_or_fix_model"
