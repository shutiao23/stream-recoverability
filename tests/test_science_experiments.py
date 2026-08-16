from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest
import torch

import stream_recoverability.experiments.runner as runner_module
import stream_recoverability.experiments.science as science_module
from stream_recoverability.analysis.compensation import (
    benjamini_hochberg_fdr,
    combination_label,
)
from stream_recoverability.experiments.contracts import file_sha256
from stream_recoverability.experiments.model_registry import (
    load_frozen_model_design,
)
from stream_recoverability.experiments.runner import ExperimentRunner
from stream_recoverability.experiments.science import (
    _training_doy_anomaly,
    _validate_compensation_unit,
    build_compensation_grid,
    build_dense_science_grid,
    build_resilience_science_grid,
    compute_training_information_metrics,
    predict_proposed_information_combinations,
    run_information_compensation,
    training_doy_climatology,
)
from stream_recoverability.models.baselines import ClimatologyBaseline
from stream_recoverability.models.proposed import (
    MissingAwareMultisourceImputer,
    ProposedModelConfig,
    all_information_group_combinations,
)
from stream_recoverability.models.proposed_training import ProposedTrainingConfig

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VARIABLES = ("T", "F", "L", "Ta", "P", "W", "RH", "Rs")


@pytest.fixture(autouse=True)
def _authorize_operational_test_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    roster = SimpleNamespace(
        manifest_path="validation/finalized_model_roster.json",
        manifest_sha256="a" * 64,
        selected_models=("linear", "proposed"),
        proposed_decision="include_proposed_formally",
    )
    authorization = {
        "schema_version": "formal_execution_authorization_v1",
        "suite": "science_compensation",
        "formal_evidence": True,
        "model_scope": "authorized_proposed_estimand",
        "target_scope": ["T"],
        "expected_models": ["proposed"],
        "finalized_model_roster": {
            "path": roster.manifest_path,
            "sha256": roster.manifest_sha256,
            "selected_models": list(roster.selected_models),
            "proposed_decision": roster.proposed_decision,
        },
    }
    monkeypatch.setattr(
        science_module,
        "authorize_proposed_estimand",
        lambda *args, **kwargs: (roster, authorization),
    )
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


def test_dense_and_compensation_grids_have_fixed_counts() -> None:
    dense = build_dense_science_grid(PROJECT_ROOT / "study_manifest.yaml")
    assert len(dense.conditions) == 93
    assert len(dense.scenarios) == 1_860
    assert dense.mask_seeds == tuple(range(101, 121))
    counts = {}
    for condition in dense.conditions:
        variable = condition.variables[0]
        counts[variable] = counts.get(variable, 0) + 1
        assert condition.mask_type == "block"
        assert condition.layout == "single"
        assert condition.window_length == 736
    assert counts == {"T": 45, "F": 24, "L": 24}

    compensation = build_compensation_grid(
        PROJECT_ROOT / "study_manifest.yaml", mask_seeds=(101, 120)
    )
    assert len(compensation.conditions) == 12
    assert len(compensation.scenarios) == 24
    assert compensation.mask_seeds == (101, 120)

    resilience = build_resilience_science_grid(PROJECT_ROOT / "study_manifest.yaml")
    assert len(resilience.conditions) == 96
    assert len(resilience.scenarios) == 1_920
    assert resilience.mask_seeds == tuple(range(101, 121))
    expected_failures = {
        (),
        ("B1",),
        ("S2",),
        ("P3",),
        ("B1", "S2"),
        ("B1", "P3"),
        ("S2", "P3"),
        ("B1", "S2", "P3"),
    }
    for target in ("B1", "S2", "P3"):
        for length in (10, 30, 90, 180):
            selected = {
                condition.failed_station_ids
                for condition in resilience.conditions
                if condition.station_ids == (target,) and condition.gap_length == length
            }
            assert selected == expected_failures


def test_information_design_contains_s0_and_all_16_combinations() -> None:
    labels = [
        combination_label(value) for value in all_information_group_combinations()
    ]
    assert len(labels) == 16
    assert len(set(labels)) == 16
    assert labels[0] == "S0"
    assert "S0+A+B+C+D" in labels


def test_compensation_unit_contract_rejects_invalid_quantiles_and_metrics() -> None:
    scenario = build_compensation_grid(
        PROJECT_ROOT / "study_manifest.yaml", mask_seeds=(101,)
    ).scenarios[0]
    labels = [
        combination_label(value) for value in all_information_group_combinations()
    ]
    contract_fields = {
        "component_estimator": "proposed_checkpoint",
        "attribution_estimand": "operational_dropout",
        "design_version": "test",
        "design_hash": "a" * 64,
        "data_version": "published_v1",
        "evaluation_split": "development_test",
        "mask_schema_version": "mask_schema_v2",
        "model_schema_version": "model_schema_v2",
        "statistics_schema_version": "statistics_schema_v2",
    }
    daily = pd.DataFrame(
        {
            **contract_fields,
            "date": pd.Timestamp("2019-01-01"),
            "station_id": "B1",
            "target": "T",
            "scenario_id": scenario.scenario_id,
            "training_seed": 11,
            "information_combination": labels,
            "y_true": 10.0,
            "quality_approved": True,
            "artificial_mask": True,
            "q05": [8.0] * 16,
            "q25": [9.0] * 16,
            "q50": [10.0] * 16,
            "q75": [11.0] * 16,
            "q95": [12.0] * 16,
        }
    )
    events = pd.DataFrame(
        {
            **contract_fields,
            "scenario_id": scenario.scenario_id,
            "training_seed": 11,
            "information_combination": labels,
            "MAE": 1.0,
            "RMSE": 1.5,
        }
    )
    _validate_compensation_unit(daily, events, scenario, 11)

    nonfinite = daily.copy()
    nonfinite.loc[nonfinite["information_combination"] == "S0", "q95"] = np.inf
    with pytest.raises(ValueError, match="nonfinite"):
        _validate_compensation_unit(nonfinite, events, scenario, 11)

    unordered = daily.copy()
    unordered.loc[unordered["information_combination"] == "S0", "q75"] = 9.5
    with pytest.raises(ValueError, match="strictly ordered"):
        _validate_compensation_unit(unordered, events, scenario, 11)

    invalid_metrics = events.copy()
    invalid_metrics["RMSE"] = np.inf
    with pytest.raises(ValueError, match="MAE/RMSE"):
        _validate_compensation_unit(daily, invalid_metrics, scenario, 11)


def test_s0_is_fitted_only_from_training_day_of_year() -> None:
    dates = pd.to_datetime(["2019-01-01", "2020-01-01", "2021-01-01", "2021-01-02"])
    values = np.array([1.0, 3.0, 999.0, 999.0])
    train = np.array([True, True, False, False])
    approved = np.ones(4, dtype=bool)
    prediction = training_doy_climatology(dates, values, train, approved)
    assert prediction[2] == 2.0
    # Day 2 is absent in training and therefore uses the training global mean.
    assert prediction[3] == 2.0


def test_climatology_and_information_anomaly_use_stable_leap_calendar() -> None:
    dates = pd.to_datetime(["2019-03-01", "2020-02-29", "2020-03-01", "2021-03-01"])
    values = np.array([10.0, 100.0, 14.0, 18.0])
    approved = np.ones(len(values), dtype=bool)
    anomalies = _training_doy_anomaly(pd.DatetimeIndex(dates), values, approved)
    np.testing.assert_allclose(anomalies, [-4.0, 0.0, 0.0, 4.0])

    train = np.array([True, True, True, False])
    actual = training_doy_climatology(dates, values, train, approved)
    frame = pd.DataFrame({"date": dates, "target": values})
    expected = (
        ClimatologyBaseline("target", window=7)
        .fit(frame, train_mask=train)
        .predict(frame)
        .to_numpy()
    )
    np.testing.assert_allclose(actual, expected)
    assert actual[0] == actual[2] == actual[3]


def test_hidden_truth_is_removed_before_enabled_group_inference() -> None:
    torch.manual_seed(7)
    config = ProposedModelConfig(
        station_ids=("B1", "S2"),
        variable_names=VARIABLES,
        hidden_size=8,
        station_embedding_size=3,
        variable_embedding_size=2,
        dropout=0.0,
    )
    model = MissingAwareMultisourceImputer(config)
    rng = np.random.default_rng(4)
    values = rng.normal(size=(12, 2, len(VARIABLES))).astype(np.float32)
    natural = np.ones_like(values, dtype=bool)
    artificial = np.zeros_like(values, dtype=bool)
    # Treat a later target as hidden; changing this future hidden truth must not
    # change any information-combination prediction.
    artificial[9, 0, 0] = True
    seasonal = rng.normal(size=(12, 4)).astype(np.float32)
    mean = np.zeros((2, len(VARIABLES)), dtype=np.float32)
    scale = np.ones_like(mean)
    first = predict_proposed_information_combinations(
        model,
        values,
        natural,
        artificial,
        seasonal,
        mean,
        scale,
        target_index=0,
    )
    changed = values.copy()
    changed[9, 0, 0] = 1_000_000.0
    second = predict_proposed_information_combinations(
        model,
        changed,
        natural,
        artificial,
        seasonal,
        mean,
        scale,
        target_index=0,
    )
    assert len(first) == 16
    assert "S0" in first
    for label in first:
        for quantile in ("q05", "q25", "q50", "q75", "q95"):
            np.testing.assert_allclose(first[label][quantile], second[label][quantile])


def test_information_combinations_use_half_overlap_windows_and_only_return_hidden_t() -> (
    None
):
    class RecordingModel(torch.nn.Module):
        quantile_levels = (0.05, 0.25, 0.5, 0.75, 0.95)

        def __init__(self) -> None:
            super().__init__()
            self.starts: list[int] = []
            self.group_masks: list[torch.Tensor] = []

        def forward(
            self,
            values: torch.Tensor,
            natural_mask: torch.Tensor,
            artificial_mask: torch.Tensor,
            *,
            seasonal_features: torch.Tensor,
            enabled_groups: torch.Tensor,
        ) -> dict[str, torch.Tensor]:
            del natural_mask, artificial_mask
            self.starts.append(int(seasonal_features[0, 0, 0].item()))
            self.group_masks.append(enabled_groups.detach().cpu().clone())
            median = torch.zeros(
                (values.shape[0], values.shape[1], values.shape[2]),
                dtype=values.dtype,
                device=values.device,
            )
            offsets = torch.tensor(
                (-2.0, -1.0, 0.0, 1.0, 2.0),
                dtype=values.dtype,
                device=values.device,
            )
            return {"quantiles": median[..., None] + offsets}

    model = RecordingModel()
    values = np.zeros((20, 2, len(VARIABLES)), dtype=np.float32)
    natural = np.ones_like(values, dtype=bool)
    artificial = np.zeros_like(values, dtype=bool)
    artificial[[5, 13], 0, 0] = True
    seasonal = np.zeros((20, 4), dtype=np.float32)
    seasonal[:, 0] = np.arange(20)
    result = predict_proposed_information_combinations(
        model,
        values,
        natural,
        artificial,
        seasonal,
        np.zeros((2, len(VARIABLES)), dtype=np.float32),
        np.ones((2, len(VARIABLES)), dtype=np.float32),
        target_index=0,
        window_length=8,
    )
    assert model.starts == [0, 4, 8, 12]
    assert len(result) == 16
    assert all(mask.shape == (16, 4) for mask in model.group_masks)
    assert all(not mask[0].any() for mask in model.group_masks)
    for quantiles in result.values():
        finite = np.isfinite(quantiles["q50"])
        np.testing.assert_array_equal(finite, artificial[..., 0])
        np.testing.assert_allclose(quantiles["q50"][finite], 0.0)


def _information_wide() -> pd.DataFrame:
    dates = pd.date_range("2010-01-01", periods=90, freq="D")
    time = np.arange(len(dates), dtype=float)
    frame = pd.DataFrame(
        {
            "date": dates,
            "split": np.where(time < 70, "train", "validation"),
        }
    )
    for station_index, station in enumerate(("B1", "S2")):
        base = np.sin(time / 6.0 + station_index * 0.3)
        frame[f"{station}_T"] = base + 0.02 * time
        frame[f"{station}_F"] = np.roll(base, 1) + station_index
        frame[f"{station}_L"] = 0.5 * base + station_index
        frame[f"{station}_Ta"] = np.cos(time / 9.0) + station_index
        frame[f"{station}_P"] = (time % 7) + station_index
        frame[f"{station}_W"] = (time % 5) / 2 + station_index
        frame[f"{station}_RH"] = 50 + 5 * base
        frame[f"{station}_Rs"] = 8 + np.cos(time / 4.0)
    return frame


def test_information_metrics_are_training_only_and_bidirectional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wide = _information_wide()
    transfer_entropy = science_module.transfer_entropy
    te_call_count = 0

    def counted_transfer_entropy(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal te_call_count
        te_call_count += 1
        return transfer_entropy(*args, **kwargs)

    monkeypatch.setattr(science_module, "transfer_entropy", counted_transfer_entropy)
    first = compute_training_information_metrics(
        wide,
        station_ids=("B1", "S2"),
        n_neighbors=3,
        lags=(1,),
        n_permutations=2,
        seed=5,
    )
    assert te_call_count == 38
    changed = wide.copy()
    nontrain = changed["split"] != "train"
    measurement_columns = [column for column in changed if "_" in column]
    changed.loc[nontrain, measurement_columns] = 1_000_000.0
    second = compute_training_information_metrics(
        changed,
        station_ids=("B1", "S2"),
        n_neighbors=3,
        lags=(1,),
        n_permutations=2,
        seed=5,
    )
    assert te_call_count == 76
    assert set(first["metric"]) == {"knn_mutual_information", "transfer_entropy"}
    te = first.loc[first["metric"] == "transfer_entropy"].copy()
    assert set(te["direction"]) == {
        "source_to_target",
        "target_to_source",
    }
    assert len(te) == 40
    assert te["hypothesis_id"].nunique() == 38
    assert int(te["hypothesis_duplicate"].sum()) == 2
    duplicate_hypotheses = te.loc[te["hypothesis_duplicate"], "hypothesis_id"].tolist()
    for hypothesis_id in duplicate_hypotheses:
        displayed = te.loc[te["hypothesis_id"] == hypothesis_id]
        assert len(displayed) == 2
        assert (
            displayed[
                [
                    "estimate",
                    "p_value",
                    "null_mean",
                    "null_std",
                    "z_score",
                    "n",
                    "seed",
                    "p_fdr_bh",
                ]
            ]
            .nunique(dropna=False)
            .eq(1)
            .all()
        )
    unique_te = te.drop_duplicates("hypothesis_id", keep="first")
    expected_fdr = benjamini_hochberg_fdr(unique_te["p_value"])
    expected_by_hypothesis = dict(
        zip(unique_te["hypothesis_id"], expected_fdr, strict=True)
    )
    np.testing.assert_allclose(
        te["p_fdr_bh"], te["hypothesis_id"].map(expected_by_hypothesis)
    )
    assert first["seed"].notna().all()
    assert first["fit_split"].eq("train").all()
    assert first["series_preprocessing"].eq("training_day_of_year_anomaly").all()
    assert (
        first["series_preprocessing_definition"]
        .str.contains("reference-year-2000", regex=False)
        .all()
    )
    assert (
        first["series_preprocessing_definition"]
        .str.contains("February 29", regex=False)
        .all()
    )
    pdt.assert_frame_equal(first, second)


def _write_small_processed_data(root: Path) -> tuple[Path, Path]:
    dates = pd.date_range("2018-01-01", periods=60, freq="D")
    split = np.array(["train"] * 20 + ["validation"] * 10 + ["test"] * 30)
    wide = pd.DataFrame({"date": dates, "split": split})
    long_rows = []
    for station_index, station in enumerate(("B1", "P3", "S2")):
        for variable_index, variable in enumerate(VARIABLES):
            values = (
                station_index * 2 + variable_index + np.sin(np.arange(len(dates)) / 5.0)
            ).astype(np.float32)
            wide[f"{station}_{variable}"] = values
            long_rows.extend(
                {
                    "date": date,
                    "station_id": station,
                    "variable": variable,
                    "quality_approved": True,
                    "natural_observed": True,
                }
                for date in dates
            )
    wide_path = root / "wide.parquet"
    quality_path = root / "long.parquet"
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


def _write_compensation_checkpoint(
    path: Path,
    *,
    training_seed: int,
    wide_path: Path,
    quality_path: Path,
    checkpoint_seed: int | None = None,
    window: int = 368,
    protocol: str = "seen_length",
) -> None:
    station_ids = ("B1", "P3", "S2")
    frozen_design = load_frozen_model_design(
        PROJECT_ROOT / "configs" / "design_freeze_v2.yaml"
    )
    frozen_model = frozen_design.protocol_for("proposed")
    common = frozen_design.common_training
    config = ProposedModelConfig(
        station_ids=station_ids,
        variable_names=VARIABLES,
        hidden_size=int(frozen_model["hidden_size"]),
        station_embedding_size=int(frozen_model["station_embedding_size"]),
        variable_embedding_size=int(frozen_model["variable_embedding_size"]),
        dropout=float(frozen_model["dropout"]),
        architecture_version=str(frozen_model["architecture_version"]),
    )
    model = MissingAwareMultisourceImputer(config)
    training_config = ProposedTrainingConfig(
        epochs=int(common["max_epochs"]),
        learning_rate=float(common["learning_rate"]),
        weight_decay=float(common["weight_decay"]),
        patience=int(common["patience"]),
        min_delta=float(common["minimum_delta"]),
        gradient_clip=float(common["gradient_clip"]),
        seed=training_seed if checkpoint_seed is None else checkpoint_seed,
        device="cpu",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "model_config": asdict(config),
            "quantile_levels": list(model.quantile_levels),
            "training_config": asdict(training_config),
            "training_context": {
                "profile": "formal",
                "training_budget_source": "design_freeze",
                "design_version": frozen_design.design_version,
                "frozen_common_training": dict(common),
                "frozen_model_protocol": frozen_model,
                "train_mask_repeats": 5,
                "validation_mask_repeats": 1,
                "window": window,
                "effective_window": 10,
                "protocol": protocol,
                "input_files": {
                    "wide": {
                        "path": str(wide_path.resolve()),
                        "size": wide_path.stat().st_size,
                        "mtime_ns": wide_path.stat().st_mtime_ns,
                        "sha256": file_sha256(wide_path),
                    },
                    "quality": {
                        "path": str(quality_path.resolve()),
                        "size": quality_path.stat().st_size,
                        "mtime_ns": quality_path.stat().st_mtime_ns,
                        "sha256": file_sha256(quality_path),
                    },
                },
            },
            "train_scaler": {
                "mean": np.zeros((3, len(VARIABLES))).tolist(),
                "scale": np.ones((3, len(VARIABLES))).tolist(),
                "station_ids": list(station_ids),
                "variable_names": list(VARIABLES),
            },
            "epoch": 1,
            "best_epoch": 1,
            "best_validation_loss": 1.0,
            "epochs_run": 1,
            "hit_epoch_limit": False,
            "history": [{"epoch": 1.0, "train_loss": 1.1, "validation_loss": 1.0}],
        },
        path,
    )


def test_resilience_masks_share_target_gap_and_export_complete_design(
    tmp_path: Path,
) -> None:
    wide_path, quality_path = _write_small_processed_data(tmp_path)
    grid = build_resilience_science_grid(
        PROJECT_ROOT / "study_manifest.yaml",
        mask_seeds=(101,),
        frontier_anchor_path=None,
    )
    runner = ExperimentRunner(
        grid,
        wide_path=wide_path,
        quality_path=quality_path,
        output_dir=tmp_path / "results",
        mask_dir=tmp_path / "masks",
        config_path=PROJECT_ROOT / "configs/experiments.yaml",
        models=("climatology",),
    )
    scenarios = [
        scenario
        for scenario in grid.scenarios
        if scenario.condition.station_ids == ("B1",)
        and scenario.condition.gap_length == 10
    ]
    assert len(scenarios) == 8
    target_station = runner.data.station_ids.index("B1")
    target_variable = runner.data.variable_names.index("T")
    hydro_variables = {
        runner.data.variable_names.index(variable) for variable in ("T", "F", "L")
    }
    shared_positions: np.ndarray | None = None
    generated: dict[tuple[str, ...], tuple[np.ndarray, dict[str, object]]] = {}
    for scenario in scenarios:
        mask, metadata = runner._generate_mask(scenario)
        failed = scenario.condition.failed_station_ids
        generated[failed] = (mask, metadata)
        positions = np.flatnonzero(mask[:, target_station, target_variable])
        assert len(positions) == 10
        if shared_positions is None:
            shared_positions = positions
        else:
            np.testing.assert_array_equal(positions, shared_positions)
        for station_id in runner.data.station_ids:
            station = runner.data.station_ids.index(station_id)
            for variable in range(len(runner.data.variable_names)):
                expected = (
                    shared_positions
                    if station_id in failed and variable in hydro_variables
                    else shared_positions
                    if station_id == "B1" and variable == target_variable
                    else np.empty(0, dtype=int)
                )
                np.testing.assert_array_equal(
                    np.flatnonzero(mask[:, station, variable]), expected
                )
        assert tuple(metadata["failed_station_ids"]) == failed
        assert metadata["failure_count"] == len(failed)
        assert metadata["network_size"] == 3

    mask, metadata = generated[("S2",)]
    scenario = next(
        value for value in scenarios if value.condition.failed_station_ids == ("S2",)
    )
    daily, events, skipped = runner._prediction_rows(
        scenario, metadata, mask, "climatology", None
    )
    assert not skipped
    assert len(events) == 1
    required_design = {
        "condition_id",
        "layout",
        "outage_mode",
        "target_station_id",
        "failed_station_ids",
        "failed_stations",
        "failure_count",
        "failure_fraction",
        "network_size",
        "target_gap_id",
        "target_gap_start_index",
        "target_gap_end_index",
        "target_gap_start_date",
        "target_gap_end_date",
        "high_threshold",
        "low_threshold",
        "normalization_iqr",
        "normalization_std",
    }
    assert required_design.issubset(daily.columns)
    assert required_design.issubset(events.columns)
    assert daily["failed_stations"].eq('["S2"]').all()
    assert events["failed_stations"].eq('["S2"]').all()
    assert daily["target_gap_id"].nunique() == 1
    assert daily["threshold_reference_split"].eq("train").all()
    reference = runner._training_reference(target_station, target_variable)
    np.testing.assert_allclose(daily["high_threshold"], reference.q90)
    np.testing.assert_allclose(daily["low_threshold"], reference.q10)
    np.testing.assert_allclose(daily["normalization_iqr"], reference.iqr)
    np.testing.assert_allclose(daily["normalization_std"], reference.std)


def test_compensation_output_uses_checkpoint_for_s0_and_strict_score_mask(
    tmp_path: Path,
) -> None:
    wide_path, quality_path = _write_small_processed_data(tmp_path)
    checkpoint_path = tmp_path / "proposed.pt"
    _write_compensation_checkpoint(
        checkpoint_path,
        training_seed=11,
        wide_path=wide_path,
        quality_path=quality_path,
    )
    daily, events, skipped = run_information_compensation(
        checkpoint_path=checkpoint_path,
        manifest_path=PROJECT_ROOT / "study_manifest.yaml",
        config_path=PROJECT_ROOT / "configs/experiments.yaml",
        wide_path=wide_path,
        quality_path=quality_path,
        output_dir=tmp_path / "results",
        mask_dir=tmp_path / "masks",
        training_seed=11,
        mask_seeds=(101,),
        frontier_anchor_path=None,
        max_scenarios=1,
    )
    assert skipped.empty
    assert len(events) == 16
    assert events["information_combination"].nunique() == 16
    assert daily["quality_approved"].all()
    assert daily["artificial_mask"].all()
    assert daily["threshold_reference_split"].eq("train").all()
    assert daily["normalization_reference_split"].eq("train").all()
    assert daily[["high_threshold", "low_threshold"]].notna().all().all()
    assert daily[["normalization_iqr", "normalization_std"]].notna().all().all()
    s0 = daily.loc[daily["information_combination"] == "S0"].sort_values("date")
    assert daily[["q05", "q25", "q50", "q75", "q95"]].notna().all().all()
    assert (daily["q05"] < daily["q25"]).all()
    assert (daily["q25"] < daily["q50"]).all()
    assert (daily["q50"] < daily["q75"]).all()
    assert (daily["q75"] < daily["q95"]).all()
    wide = pd.read_parquet(wide_path)
    expected = training_doy_climatology(
        wide["date"],
        wide["B1_T"],
        wide["split"].eq("train"),
        np.ones(len(wide), dtype=bool),
    )
    expected_by_date = pd.Series(expected, index=pd.DatetimeIndex(wide["date"]))
    assert not np.allclose(
        s0["y_pred"].to_numpy(),
        expected_by_date.loc[pd.DatetimeIndex(s0["date"])].to_numpy(),
    )
    assert daily["component_estimator"].eq("proposed_checkpoint").all()
    assert daily["estimator"].eq("proposed_checkpoint").all()
    assert daily["attribution_estimand"].eq("operational_dropout").all()
    assert events["component_estimator"].eq("proposed_checkpoint").all()
    assert events["attribution_estimand"].eq("operational_dropout").all()
    assert daily["evaluation_split"].eq("development_test").all()
    for field in (
        "design_version",
        "design_hash",
        "data_version",
        "mask_schema_version",
        "model_schema_version",
        "statistics_schema_version",
    ):
        assert daily[field].notna().all()
        assert events[field].notna().all()
    training_values = wide.loc[wide["split"] == "train", "B1_T"].to_numpy(dtype=float)
    _q10, q25, q75, q90 = np.quantile(training_values, (0.10, 0.25, 0.75, 0.90))
    training_iqr = q75 - q25
    training_std = np.std(training_values, ddof=0)
    np.testing.assert_allclose(events["high_temp_threshold"], q90)
    assert events["ecological_threshold"].isna().all()
    assert events["threshold_days_bias"].isna().all()
    np.testing.assert_allclose(events["NMAE"], events["MAE"] / training_iqr)
    np.testing.assert_allclose(events["NRMSE"], events["RMSE"] / training_std)
    run_manifest = json.loads((tmp_path / "results" / "run_manifest.json").read_text())
    assert "reference-year-2000" in run_manifest["s0_definition"]
    assert "February 29" in run_manifest["s0_definition"]
    assert run_manifest["status"] == "partial"
    assert run_manifest["complete"] is False
    assert run_manifest["formal_design_complete"] is False
    assert run_manifest["formal_unit_grid_complete"] is False
    assert run_manifest["formal_training_seed_complete"] is False
    assert run_manifest["formal_mask_seed_complete"] is False
    assert run_manifest["expected_training_seeds"] == [11, 22, 33, 44, 55]
    assert run_manifest["expected_mask_seeds"] == list(range(101, 121))
    assert run_manifest["evaluation_split"] == "development_test"
    assert run_manifest["data_version"] == "published_v1"
    assert run_manifest["frontier_anchor_catalog_path"] is None
    assert run_manifest["frontier_anchor_catalog_sha256"] is None
    assert run_manifest["frontier_anchor_count"] == 0
    assert run_manifest["anchor_availability_rows"] == 0
    assert run_manifest["unavailable_anchor_rows"] == 0
    assert run_manifest["anchor_replacement_allowed"] is False
    assert run_manifest["training_profile"] == "formal"
    assert run_manifest["training_settings"]["train_mask_repeats"] == 5
    assert run_manifest["training_settings"]["proposed_epochs"] == 200
    assert run_manifest["training_settings"]["proposed_patience"] == 20
    assert run_manifest["attribution_estimand"] == "operational_dropout"
    assert run_manifest["component_estimator"] == "proposed_checkpoint"
    assert "mixed_baseline_limitation" not in run_manifest
    assert run_manifest["suite"] == "science_compensation"
    assert run_manifest["models"] == ["information_compensation"]
    assert run_manifest["expected_run_unit_count"] == 12 * 5
    assert run_manifest["completed_run_unit_count"] == 1
    assert run_manifest["retryable_run_unit_count"] == 12 * 5 - 1
    assert run_manifest["checkpoint_required_run_count"] == 12 * 5
    assert run_manifest["checkpoint_valid_run_count"] == 12
    assert run_manifest["finite_prediction_run_unit_count"] == 1
    assert run_manifest["finite_event_metric_run_unit_count"] == 1
    assert len(run_manifest["training_checkpoints"]) == 1
    assert len(run_manifest["training_checkpoints"][0]["checkpoint"]["sha256"]) == 64
    assert "code_identity" in run_manifest


def test_compensation_resume_preserves_other_seed_and_excludes_bad_checkpoint(
    tmp_path: Path,
) -> None:
    wide_path, quality_path = _write_small_processed_data(tmp_path)
    checkpoints = tmp_path / "checkpoints"
    for seed in (11, 22):
        _write_compensation_checkpoint(
            checkpoints / f"proposed-S{seed}-W368-seen_length.pt",
            training_seed=seed,
            wide_path=wide_path,
            quality_path=quality_path,
        )
    common = {
        "checkpoint_dir": checkpoints,
        "manifest_path": PROJECT_ROOT / "study_manifest.yaml",
        "config_path": PROJECT_ROOT / "configs/experiments.yaml",
        "wide_path": wide_path,
        "quality_path": quality_path,
        "output_dir": tmp_path / "results",
        "mask_dir": tmp_path / "masks",
        "mask_seeds": (101,),
        "frontier_anchor_path": None,
        "max_scenarios": 1,
    }
    run_information_compensation(training_seeds=(11,), **common)
    daily, events, skipped = run_information_compensation(
        training_seeds=(22,), **common
    )
    assert skipped.empty
    assert set(events["training_seed"]) == {11, 22}
    assert len(events) == 32
    assert set(daily["training_seed"]) == {11, 22}
    for seed in (11, 22):
        status_paths = list(
            (tmp_path / "results" / "units").glob(f"*/S{seed}/status.json")
        )
        assert len(status_paths) == 1
        assert json.loads(status_paths[0].read_text())["status"] == "complete"

    seed_11_status = next((tmp_path / "results" / "units").glob("*/S11/status.json"))
    original_artifact = json.loads(seed_11_status.read_text())["checkpoint_artifact"]
    _write_compensation_checkpoint(
        checkpoints / "proposed-S11-W368-seen_length.pt",
        training_seed=11,
        wide_path=wide_path,
        quality_path=quality_path,
    )
    daily, events, _ = run_information_compensation(training_seeds=(11,), **common)
    replacement_artifact = json.loads(seed_11_status.read_text())["checkpoint_artifact"]
    assert replacement_artifact != original_artifact
    assert set(events["training_seed"]) == {11, 22}
    assert set(daily["training_seed"]) == {11, 22}

    # Replacing seed 11's checkpoint with seed 22 metadata must invalidate only
    # seed 11. Its old unit remains recoverable on disk but cannot leak into the
    # rebuilt top-level aggregate.
    _write_compensation_checkpoint(
        checkpoints / "proposed-S11-W368-seen_length.pt",
        training_seed=11,
        checkpoint_seed=22,
        wide_path=wide_path,
        quality_path=quality_path,
    )
    daily, events, skipped = run_information_compensation(
        training_seeds=(11,), **common
    )
    assert set(events["training_seed"]) == {22}
    assert set(daily["training_seed"]) == {22}
    assert skipped["reason_code"].eq("checkpoint_unavailable_or_incompatible").all()
    stored_events = pd.read_parquet(tmp_path / "results" / "event_metrics.parquet")
    assert set(stored_events["training_seed"]) == {22}
    assert json.loads(seed_11_status.read_text())["status"] == "skipped"

    # A later resume of another seed must not resurrect units from a seed whose
    # checkpoint was already found invalid.
    daily, events, _ = run_information_compensation(training_seeds=(22,), **common)
    assert set(events["training_seed"]) == {22}
    assert set(daily["training_seed"]) == {22}


def test_compensation_rejects_training_input_changes_against_version_manifest(
    tmp_path: Path,
) -> None:
    wide_path, quality_path = _write_small_processed_data(tmp_path)
    checkpoints = tmp_path / "checkpoints"
    for seed in (11, 22):
        _write_compensation_checkpoint(
            checkpoints / f"proposed-S{seed}-W368-seen_length.pt",
            training_seed=seed,
            wide_path=wide_path,
            quality_path=quality_path,
        )
    common = {
        "checkpoint_dir": checkpoints,
        "manifest_path": PROJECT_ROOT / "study_manifest.yaml",
        "config_path": PROJECT_ROOT / "configs/experiments.yaml",
        "wide_path": wide_path,
        "quality_path": quality_path,
        "output_dir": tmp_path / "results",
        "mask_dir": tmp_path / "masks",
        "mask_seeds": (101,),
        "frontier_anchor_path": None,
        "max_scenarios": 1,
    }
    run_information_compensation(training_seeds=(11,), **common)
    _, events, _ = run_information_compensation(training_seeds=(22,), **common)
    assert set(events["training_seed"]) == {11, 22}

    wide = pd.read_parquet(wide_path)
    wide.loc[0, "B1_T"] = np.float32(wide.loc[0, "B1_T"] + 0.125)
    wide.to_parquet(wide_path, index=False)
    with pytest.raises(
        ValueError,
        match="data-version daily_wide.parquet SHA-256 does not match",
    ):
        run_information_compensation(training_seeds=(11,), **common)


@pytest.mark.parametrize(
    ("mutation", "reason_fragment"),
    [
        ("quantiles", "quantile levels"),
        ("window", "window"),
        ("protocol", "protocol"),
        ("profile", "profile"),
        ("mask_repeats", "train_mask_repeats"),
        ("validation_mask_repeats", "validation_mask_repeats"),
        ("epochs", "epochs"),
        ("patience", "patience"),
        ("device", "device"),
        ("learning_rate", "learning_rate"),
        ("model_config", "hidden_size"),
        ("missing_history", "history"),
        ("nonfinite_history", "finite"),
        ("nonfinite_state", "finite"),
        ("inconsistent_best", "best_validation_loss"),
        ("scaler_axes", "scaler axes"),
    ],
)
def test_compensation_rejects_mismatched_checkpoint_contract(
    tmp_path: Path, mutation: str, reason_fragment: str
) -> None:
    wide_path, quality_path = _write_small_processed_data(tmp_path)
    checkpoint = tmp_path / "proposed.pt"
    _write_compensation_checkpoint(
        checkpoint,
        training_seed=11,
        wide_path=wide_path,
        quality_path=quality_path,
    )
    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    if mutation == "quantiles":
        payload["quantile_levels"] = [0.05, 0.5, 0.95]
    elif mutation == "window":
        payload["training_context"]["window"] = 184
    elif mutation == "protocol":
        payload["training_context"]["protocol"] = "unseen_length"
    elif mutation == "profile":
        payload["training_context"]["profile"] = "smoke"
    elif mutation == "mask_repeats":
        payload["training_context"]["train_mask_repeats"] = 1
    elif mutation == "validation_mask_repeats":
        payload["training_context"]["validation_mask_repeats"] = 2
    elif mutation == "epochs":
        payload["training_config"]["epochs"] = 3
    elif mutation == "patience":
        payload["training_config"]["patience"] = 2
    elif mutation == "device":
        payload["training_config"]["device"] = "cuda"
    elif mutation == "learning_rate":
        payload["training_config"]["learning_rate"] = 0.01
    elif mutation == "model_config":
        different = MissingAwareMultisourceImputer(
            ProposedModelConfig(
                station_ids=("B1", "P3", "S2"),
                variable_names=VARIABLES,
                hidden_size=24,
                dropout=0.1,
            )
        )
        payload["model_config"] = asdict(different.config)
        payload["model_state_dict"] = different.state_dict()
    elif mutation == "missing_history":
        payload.pop("history")
    elif mutation == "nonfinite_history":
        payload["history"][0]["validation_loss"] = np.inf
    elif mutation == "nonfinite_state":
        state_name = next(
            key
            for key, value in payload["model_state_dict"].items()
            if torch.is_floating_point(value)
        )
        payload["model_state_dict"][state_name] = payload["model_state_dict"][
            state_name
        ].clone()
        payload["model_state_dict"][state_name].reshape(-1)[0] = float("nan")
    elif mutation == "inconsistent_best":
        payload["best_validation_loss"] = 2.0
    else:
        payload["train_scaler"]["station_ids"] = ["S2", "P3", "B1"]
    torch.save(payload, checkpoint)
    daily, events, skipped = run_information_compensation(
        checkpoint_path=checkpoint,
        manifest_path=PROJECT_ROOT / "study_manifest.yaml",
        config_path=PROJECT_ROOT / "configs/experiments.yaml",
        wide_path=wide_path,
        quality_path=quality_path,
        output_dir=tmp_path / "results",
        mask_dir=tmp_path / "masks",
        training_seed=11,
        mask_seeds=(101,),
        frontier_anchor_path=None,
        max_scenarios=1,
    )
    assert daily.empty and events.empty
    assert skipped["reason_code"].eq("checkpoint_unavailable_or_incompatible").all()
    assert skipped["reason"].str.contains(reason_fragment, regex=False).all()
    assert pd.read_parquet(tmp_path / "results" / "daily_predictions.parquet").empty
    assert pd.read_parquet(tmp_path / "results" / "event_metrics.parquet").empty
