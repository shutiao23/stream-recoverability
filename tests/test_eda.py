from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.analysis.eda import (
    ACF_LAGS,
    build_event_labels,
    lagged_correlation,
    run_eda,
)


def test_event_thresholds_use_train_only() -> None:
    dates = pd.date_range("2020-01-01", periods=10, freq="D")
    wide = pd.DataFrame(
        {
            "date": dates,
            "split": ["train"] * 6 + ["test"] * 4,
            "S1_T": [0, 1, 2, 3, 4, 5, 100, 101, 102, 103],
            "S1_F": [10, 20, 30, 40, 50, 60, 1000, 1100, 1200, 1300],
        }
    )
    labels, thresholds = build_event_labels(wide, ["S1"])
    assert thresholds.loc[0, "T_q90_train"] == np.quantile(np.arange(6), 0.90)
    assert thresholds.loc[0, "F_q90_train"] == np.quantile(
        [10, 20, 30, 40, 50, 60], 0.90
    )
    assert thresholds.loc[0, "F_q10_train"] == np.quantile(
        [10, 20, 30, 40, 50, 60], 0.10
    )
    assert labels.loc[labels["split"] == "test", "high_temperature"].all()

    changed = wide.copy()
    changed.loc[changed["split"] == "test", ["S1_T", "S1_F"]] = 1_000_000
    _, changed_thresholds = build_event_labels(changed, ["S1"])
    pd.testing.assert_frame_equal(thresholds, changed_thresholds)


def test_positive_lag_means_source_leads_target() -> None:
    rng = np.random.default_rng(9)
    source = rng.normal(size=200)
    target = np.full(200, np.nan)
    target[3:] = source[:-3]
    assert lagged_correlation(source, target, 3) == pytest.approx(1.0)
    assert lagged_correlation(source, target, 3) > lagged_correlation(source, target, -3)


def _write_small_processed_data(tmp_path):
    dates = pd.date_range("2017-01-01", periods=430, freq="D")
    stations = ["B1", "S2", "P3"]
    variables = ["T", "L", "F"]
    split = np.where(np.arange(len(dates)) < 400, "train", "validation")
    wide = pd.DataFrame(
        {
            "date": dates,
            "split": split,
            "season": pd.Series(dates.month).map(
                {
                    12: "DJF",
                    1: "DJF",
                    2: "DJF",
                    3: "MAM",
                    4: "MAM",
                    5: "MAM",
                    6: "JJA",
                    7: "JJA",
                    8: "JJA",
                    9: "SON",
                    10: "SON",
                    11: "SON",
                }
            ),
        }
    )
    rows = []
    time = np.arange(len(dates), dtype=float)
    for station_index, station in enumerate(stations):
        temperature = 10 + station_index + 7 * np.sin(2 * np.pi * time / 365)
        flow = 200 + 20 * station_index + 40 * np.sin(2 * np.pi * (time - 15) / 365) + time * 0.02
        level = 1000 - 100 * station_index + 0.015 * flow + 0.02 * np.cos(time / 9)
        for variable, values in {"T": temperature, "L": level, "F": flow}.items():
            wide[f"{station}_{variable}"] = values
            rows.extend(
                {
                    "date": date,
                    "station_id": station,
                    "variable": variable,
                    "value": float(value),
                    "quality_approved": True,
                    "split": split_value,
                }
                for date, value, split_value in zip(dates, values, split, strict=True)
            )
    long = pd.DataFrame(rows)
    long_path = tmp_path / "daily_long.parquet"
    wide_path = tmp_path / "daily_wide.parquet"
    long.to_parquet(long_path, index=False)
    wide.to_parquet(wide_path, index=False)

    stations_path = tmp_path / "station_metadata.csv"
    pd.DataFrame(
        {
            "station_id": stations,
            "station_name": ["Batang", "Shigu", "Panzhihua"],
            "latitude": [29.85, 26.91, 26.64],
            "longitude": [99.08, 99.95, 101.74],
            "network_order": [1, 2, 3],
        }
    ).to_csv(stations_path, index=False)
    candidates_path = tmp_path / "candidate_stations.csv"
    pd.DataFrame(
        {
            "station_id": ["JAQ"],
            "station_name": ["Jinanqiao"],
            "latitude": [np.nan],
            "longitude": [np.nan],
            "selection_reason": ["coordinate unavailable"],
        }
    ).to_csv(candidates_path, index=False)
    return long_path, wide_path, stations_path, candidates_path


def test_run_eda_writes_finite_core_outputs(tmp_path) -> None:
    long_path, wide_path, stations_path, candidates_path = _write_small_processed_data(
        tmp_path
    )
    outputs = run_eda(
        long_path,
        wide_path,
        stations_path,
        candidates_path,
        results_dir=tmp_path / "results/eda",
        eda_figures_dir=tmp_path / "figures/eda",
        qc_figures_dir=tmp_path / "figures/qc",
        event_output=tmp_path / "data/processed/event_labels.parquet",
        study_area_output=tmp_path / "figures/study_area.png",
    )
    for path in outputs.values():
        assert path.is_file(), path

    acf = pd.read_csv(outputs["acf"])
    assert set(acf["lag_days"]) == set(ACF_LAGS)
    assert np.isfinite(acf[["correlation", "n_pairs"]].to_numpy(float)).all()
    lag = pd.read_csv(outputs["cross_station_lag_correlations"])
    assert set(lag["lag_days"]) == set(range(-30, 31))
    assert np.isfinite(
        lag[
            [
                "raw_correlation",
                "raw_n_pairs",
                "anomaly_correlation",
                "anomaly_n_pairs",
            ]
        ].to_numpy(float)
    ).all()
    events = pd.read_parquet(outputs["event_labels"])
    assert len(events) == 430 * 3
    assert events[["T_q90_train", "F_q90_train", "F_q10_train"]].notna().all().all()
    points = pd.read_csv(outputs["study_area_points"])
    assert points.loc[points["station_id"] == "JAQ", "coordinate_status"].item().startswith(
        "plot_proxy"
    )
