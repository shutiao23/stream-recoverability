from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import pandas.testing as pdt
import torch

from stream_recoverability.analysis.compensation import combination_label
from stream_recoverability.experiments.science import (
    build_compensation_grid,
    build_dense_science_grid,
    compute_training_information_metrics,
    predict_proposed_information_combinations,
    run_information_compensation,
    training_doy_climatology,
)
from stream_recoverability.models.proposed import (
    MissingAwareMultisourceImputer,
    ProposedModelConfig,
    all_information_group_combinations,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VARIABLES = ("T", "F", "L", "Ta", "P", "W", "RH", "DH")


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
        assert condition.window_length == (736 if condition.gap_length == 365 else 368)
    assert counts == {"T": 45, "F": 24, "L": 24}

    compensation = build_compensation_grid(
        PROJECT_ROOT / "study_manifest.yaml", mask_seeds=(101, 120)
    )
    assert len(compensation.conditions) == 12
    assert len(compensation.scenarios) == 24
    assert compensation.mask_seeds == (101, 120)


def test_information_design_contains_s0_and_all_16_combinations() -> None:
    labels = [combination_label(value) for value in all_information_group_combinations()]
    assert len(labels) == 16
    assert len(set(labels)) == 16
    assert labels[0] == "S0"
    assert "S0+A+B+C+D" in labels


def test_s0_is_fitted_only_from_training_day_of_year() -> None:
    dates = pd.to_datetime(["2019-01-01", "2020-01-01", "2021-01-01", "2021-01-02"])
    values = np.array([1.0, 3.0, 999.0, 999.0])
    train = np.array([True, True, False, False])
    approved = np.ones(4, dtype=bool)
    prediction = training_doy_climatology(dates, values, train, approved)
    assert prediction[2] == 2.0
    # Day 2 is absent in training and therefore uses the training global mean.
    assert prediction[3] == 2.0


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
    assert len(first) == 15
    assert "S0" not in first
    for label in first:
        for quantile in ("q05", "q50", "q95"):
            np.testing.assert_allclose(first[label][quantile], second[label][quantile])


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
        frame[f"{station}_DH"] = 8 + np.cos(time / 4.0)
    return frame


def test_information_metrics_are_training_only_and_bidirectional() -> None:
    wide = _information_wide()
    first = compute_training_information_metrics(
        wide,
        station_ids=("B1", "S2"),
        n_neighbors=3,
        lags=(1,),
        n_permutations=2,
        seed=5,
    )
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
    assert set(first["metric"]) == {"knn_mutual_information", "transfer_entropy"}
    assert set(first.loc[first["metric"] == "transfer_entropy", "direction"]) == {
        "source_to_target",
        "target_to_source",
    }
    assert first["fit_split"].eq("train").all()
    assert first["series_preprocessing"].eq("training_day_of_year_anomaly").all()
    pdt.assert_frame_equal(first, second)


def _write_small_processed_data(root: Path) -> tuple[Path, Path]:
    dates = pd.date_range("2018-01-01", periods=60, freq="D")
    split = np.array(["train"] * 20 + ["validation"] * 10 + ["test"] * 30)
    wide = pd.DataFrame({"date": dates, "split": split})
    long_rows = []
    for station_index, station in enumerate(("B1", "P3", "S2")):
        for variable_index, variable in enumerate(VARIABLES):
            values = (
                station_index * 2
                + variable_index
                + np.sin(np.arange(len(dates)) / 5.0)
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
    return wide_path, quality_path


def test_compensation_output_uses_climatology_for_s0_and_strict_score_mask(
    tmp_path: Path,
) -> None:
    wide_path, quality_path = _write_small_processed_data(tmp_path)
    station_ids = ("B1", "P3", "S2")
    config = ProposedModelConfig(
        station_ids=station_ids,
        variable_names=VARIABLES,
        hidden_size=8,
        station_embedding_size=3,
        variable_embedding_size=2,
        dropout=0.0,
    )
    model = MissingAwareMultisourceImputer(config)
    checkpoint_path = tmp_path / "proposed.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "model_config": asdict(config),
            "train_scaler": {
                "mean": np.zeros((3, len(VARIABLES))).tolist(),
                "scale": np.ones((3, len(VARIABLES))).tolist(),
                "station_ids": list(station_ids),
                "variable_names": list(VARIABLES),
            },
        },
        checkpoint_path,
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
        max_scenarios=1,
    )
    assert skipped.empty
    assert len(events) == 16
    assert events["information_combination"].nunique() == 16
    assert daily["quality_approved"].all()
    assert daily["artificial_mask"].all()
    s0 = daily.loc[daily["information_combination"] == "S0"].sort_values("date")
    wide = pd.read_parquet(wide_path)
    expected = training_doy_climatology(
        wide["date"],
        wide["B1_T"],
        wide["split"].eq("train"),
        np.ones(len(wide), dtype=bool),
    )
    expected_by_date = pd.Series(expected, index=pd.DatetimeIndex(wide["date"]))
    np.testing.assert_allclose(
        s0["y_pred"].to_numpy(), expected_by_date.loc[pd.DatetimeIndex(s0["date"])].to_numpy()
    )
    assert s0["component_estimator"].eq("training_doy_climatology").all()
