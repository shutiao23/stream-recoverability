from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from stream_recoverability.experiments.grid import (
    CORE_EXPECTED_COUNTS,
    ExperimentScenario,
    build_experiment_grid,
)
from stream_recoverability.experiments.runner import (
    ExperimentRunner,
    SUPPORTED_MODELS,
    apply_full_artificial_mask,
    make_training_mask,
)


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


def _runner(tmp_path: Path, *, models: tuple[str, ...] = ("climatology", "linear")) -> ExperimentRunner:
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
    assert {condition.window_length for condition in grid.conditions if condition.experiment == "M8"} == {
        184,
        368,
        736,
    }
    assert {
        condition.training_protocol for condition in grid.conditions if condition.experiment == "M9"
    } == {"seen_length", "unseen_length"}
    loso = [condition for condition in grid.conditions if condition.experiment == "M10"]
    assert len(loso) == 3
    assert all(condition.validation_scope == "exploratory_internal_loso_not_external_validation" for condition in loso)
    assert grid.external_validation_status == "unavailable"
    synchronous = [
        condition
        for condition in grid.conditions
        if condition.experiment == "M6" and condition.overlap_ratio == 1.0
    ]
    assert synchronous
    assert all(condition.mask_type == "network_outage" for condition in synchronous)


def test_training_masks_are_fixed_and_unseen_protocol_excludes_180_day_blocks() -> None:
    values = np.ones((500, 8), dtype=float)
    first = make_training_mask(values, 11, "unseen_length")
    second = make_training_mask(values, 11, "unseen_length")
    seen = make_training_mask(values, 11, "seen_length")
    assert np.array_equal(first, second)
    assert not np.any(first & ~np.isfinite(values))

    def longest_run(column: np.ndarray) -> int:
        padded = np.pad(column.astype(int), (1, 1))
        changes = np.flatnonzero(np.diff(padded))
        return int(np.max(changes[1::2] - changes[::2]))

    assert max(longest_run(first[:, index]) for index in range(first.shape[1])) <= 90
    assert max(longest_run(seen[:, index]) for index in range(seen.shape[1])) == 180


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
    with np.load(runner.mask_dir / "scenarios" / f"{scenario.scenario_id}.npz") as archive:
        assert archive["packed"].size == (first.size + 7) // 8


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
    np.testing.assert_allclose(second[mask[:, station, target]], first[mask[:, station, target]])


def test_deep_prediction_is_stitched_from_condition_sized_windows(
    tmp_path: Path, monkeypatch
) -> None:
    runner = _runner(tmp_path, models=("saits",))
    scenario = runner.grid.scenarios[0]
    mask, _ = runner._generate_mask(scenario)
    calls: list[int] = []

    class FakeImputer:
        def predict(self, values: np.ndarray, artificial_mask: np.ndarray) -> np.ndarray:
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

    def fake_train(model, train_batches, validation_batches, config, *, checkpoint_path):
        assert list(train_batches) and list(validation_batches)
        Path(checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "model_state_dict": model.state_dict(),
                "model_config": asdict(model.config),
            },
            checkpoint_path,
        )

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


def test_internal_loso_runs_and_never_uses_held_out_temperature_labels(tmp_path: Path) -> None:
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
    scenario = next(value for value in grid.scenarios if value.condition.experiment == "M10")
    station = runner.data.station_ids.index(str(scenario.condition.held_out_station))
    target = runner.data.variable_names.index("T")
    first = runner._pooled_loso_prediction(station)[1].copy()
    runner.data.values[runner.train_rows | runner.validation_rows, station, target] += 100_000.0
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


def test_smoke_runner_scores_only_masked_cells_and_resume_deduplicates(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    first_daily, first_events = runner.run()
    assert len(first_events) == 12
    assert {"q25", "q75", "season", "event_type"}.issubset(first_daily)
    assert set(first_daily["season"]) <= {"DJF", "MAM", "JJA", "SON"}
    assert np.isfinite(pd.to_numeric(first_daily["y_true"], errors="coerce")).all()
    assert np.isfinite(pd.to_numeric(first_daily["y_pred"], errors="coerce")).all()
    assert np.isfinite(pd.to_numeric(first_events["MAE"], errors="coerce")).all()
    assert np.isfinite(pd.to_numeric(first_events["RMSE"], errors="coerce")).all()
    assert set(first_events.loc[first_events["experiment"] == "M4", "failed_stations"]) == {
        '["B1"]'
    }
    assert set(first_events.loc[first_events["experiment"] != "M4", "failed_stations"]) == {
        "[]"
    }
    assert first_daily["artificial_mask"].all()
    assert first_daily["quality_approved"].all()
    assert not first_daily.duplicated(
        ["scenario_id", "model", "training_seed", "mask_seed", "date", "station_id", "target"]
    ).any()
    assert not first_events.duplicated(
        ["scenario_id", "model", "training_seed", "mask_seed", "station_id", "target"]
    ).any()
    assert set(first_events["fit_split"]) == {"train"}
    assert set(first_events["tuning_split"]) == {"validation"}
    assert set(first_events["evaluation_split"]) == {"test"}

    for row in first_events.itertuples(index=False):
        library = runner._generate_mask(
            next(scenario for scenario in runner.grid.scenarios if scenario.scenario_id == row.scenario_id)
        )[0]
        station = runner.data.station_ids.index(row.station_id)
        variable = runner.data.variable_names.index(row.target)
        expected = int((library[:, station, variable] & runner.data.quality_approved[:, station, variable]).sum())
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
        ["scenario_id", "model", "training_seed", "mask_seed", "date", "station_id", "target"]
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
    assert status["skipped_run_count"] == 1
    skipped = status["skipped_runs"][0]
    assert skipped["run_key"] == "rating_curve:none"
    assert skipped["target"] == "F"
    assert skipped["reason_code"] == "required_input_unavailable"
    assert skipped["required_inputs"] == ["B1_L"]
    assert not (scenario_dir / "daily_predictions.parquet").exists()
    assert not (scenario_dir / "event_metrics.parquet").exists()

    assert runner._run_scenario(scenario) == "complete"
    resumed = json.loads((scenario_dir / "status.json").read_text(encoding="utf-8"))
    assert resumed["skipped_runs"] == status["skipped_runs"]
