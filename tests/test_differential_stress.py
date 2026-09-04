"""Tests for the v14 differential-stress (incremental benefit) machinery."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.experiments.development_recovery import (
    year_split,
)
from stream_recoverability.experiments.differential_stress import (
    default_handling_losses,
    default_handling_losses_from_fit_rows,
    differential_fitting_losses,
    handler_prediction,
    realized_default_mae,
    r6_differential_predictions,
)
from stream_recoverability.experiments.recovery_roster import (
    fitting_period_empirical_losses,
)

SMALL_XGBOOST = {
    "n_estimators": 5,
    "max_depth": 2,
    "learning_rate": 0.3,
    "subsample": 1.0,
    "colsample_bytree": 1.0,
    "random_state": 0,
    "n_jobs": 1,
    "objective": "reg:squarederror",
    "verbosity": 0,
}


def _temperature_panel() -> pd.DataFrame:
    index = pd.date_range("2001-01-01", "2008-12-31", freq="D")
    doy = index.dayofyear.to_numpy(dtype=float)
    phase = 2.0 * np.pi * (doy - 1.0) / 365.0
    columns: dict[str, np.ndarray] = {"date": index}
    rng = np.random.default_rng(3)
    for station in ("A", "B", "C"):
        base = 12.0 - 10.0 * np.cos(phase)
        columns[station] = base + rng.normal(0.0, 0.4, len(index))
    for station in ("B", "C"):
        columns[station] = columns[station] + 0.6 * (
            columns["A"] - columns["A"].mean()
        )
    return pd.DataFrame(columns).set_index("date").round(3)


def _placements(panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for station in ("A", "B", "C"):
        donors = [s for s in ("A", "B", "C") if s != station]
        rows.append(
            {
                "network_id": "synthetic",
                "station_id": station,
                "gap_length": 30,
                "placement": 0,
                "information_condition": "B_union_D",
                "donor_station_ids": "|".join(donors),
            }
        )
    return pd.DataFrame(rows)


def test_handler_prediction_linear_interp_matches_flanking_values() -> None:
    panel = _temperature_panel()
    target = panel["A"]
    train_mask, _, _ = year_split(panel.index)
    start = 800
    length = 9
    predicted = handler_prediction(
        "linear_interp", target, start=start, gap_length=length, train_mask=train_mask
    )
    left = float(target.iloc[start - 1])
    right = float(target.iloc[start + length])
    fraction = np.arange(1, length + 1) / (length + 1.0)
    np.testing.assert_allclose(predicted, left + fraction * (right - left))


def test_default_handling_standalone_matches_replay_from_fit_rows() -> None:
    panel = _temperature_panel()
    placements = _placements(panel)
    panel_wide = panel.copy()
    fit = fitting_period_empirical_losses(
        "synthetic",
        panel_wide,
        placements,
        xgboost_parameters=SMALL_XGBOOST,
        min_train_days=180,
    )
    assert len(fit) > 0
    standalone = default_handling_losses(
        "synthetic",
        panel_wide,
        placements,
        handler="climatology",
        min_train_days=180,
    )
    replay = default_handling_losses_from_fit_rows(
        "synthetic", panel_wide, fit, handler="climatology"
    )
    assert len(standalone) == len(replay) > 0
    keys = ["network_id", "station_id", "gap_length", "season", "placement"]
    merged = standalone.merge(replay, on=keys, suffixes=("_standalone", "_replay"))
    assert len(merged) == len(standalone)
    np.testing.assert_allclose(
        merged["mae_deg_c_standalone"],
        merged["mae_deg_c_replay"],
        rtol=1e-12,
        atol=1e-12,
    )


def test_default_handling_linear_interp_is_replayed_exactly() -> None:
    panel = _temperature_panel()
    placements = _placements(panel)
    panel_wide = panel.copy()
    fit = fitting_period_empirical_losses(
        "synthetic",
        panel_wide,
        placements,
        xgboost_parameters=SMALL_XGBOOST,
        min_train_days=180,
    )
    replay = default_handling_losses_from_fit_rows(
        "synthetic", panel_wide, fit, handler="linear_interp"
    )
    target = panel["A"]
    subset = replay[replay["station_id"] == "A"]
    assert len(subset) > 0
    for row in subset.head(5).itertuples(index=False):
        start = panel.index.get_loc(pd.Timestamp(row.gap_start))
        gap = int(row.gap_length)
        truth = panel["A"].iloc[start : start + gap].to_numpy(dtype=float)
        left = float(target.iloc[start - 1])
        right = float(target.iloc[start + gap])
        fraction = np.arange(1, gap + 1) / (gap + 1.0)
        expected = np.mean(np.abs(left + fraction * (right - left) - truth))
        assert row.mae_deg_c == pytest.approx(expected, abs=1e-9)


def test_climatology_uses_only_inner_fit_years() -> None:
    panel = _temperature_panel()
    placements = _placements(panel)
    panel_wide = panel.copy()
    fit = fitting_period_empirical_losses(
        "synthetic",
        panel_wide,
        placements,
        xgboost_parameters=SMALL_XGBOOST,
        min_train_days=180,
    )
    replay = default_handling_losses_from_fit_rows(
        "synthetic", panel_wide, fit, handler="climatology"
    )
    row = replay.iloc[0]
    target = panel[row.station_id]
    years = tuple(
        int(value) for value in str(row.inner_fit_years).split("|") if value
    )
    mask = pd.Series(
        target.index.year.isin(years), index=target.index, dtype=bool
    )
    training = target.loc[mask & target.notna()]
    by_day = training.groupby(training.index.dayofyear).median()
    fallback = float(training.median())
    start = panel.index.get_loc(pd.Timestamp(row.gap_start))
    gap = int(row.gap_length)
    predicted = (
        by_day.reindex(panel.index[start : start + gap].dayofyear)
        .fillna(fallback)
        .to_numpy(dtype=float)
    )
    truth = panel[row.station_id].iloc[start : start + gap].to_numpy(dtype=float)
    assert row.mae_deg_c == pytest.approx(
        float(np.mean(np.abs(predicted - truth))), abs=1e-9
    )


def test_differential_fitting_losses_differences_and_drops_unpaired() -> None:
    model = pd.DataFrame(
        {
            "network_id": ["n1"] * 2 + ["n2"],
            "station_id": ["s1", "s1", "s2"],
            "gap_length": [7, 30, 7],
            "season": ["DJF", "MAM", "JJA"],
            "placement": [0, 1, 0],
            "gap_start": pd.to_datetime(["2020-01-01", "2020-04-01", "2020-07-01"]),
            "mae_deg_c": [0.5, 0.6, 0.7],
            "model_family": ["xgboost_b_d"] * 3,
            "outer_training_years": ["2010|2019"] * 3,
            "inner_fit_years": ["2010|2015"] * 3,
            "inner_score_years": ["2016|2019"] * 3,
        }
    )
    default = model.copy()
    default["mae_deg_c"] = [1.2, 1.1, 0.4]
    default["model_family"] = "default_climatology"
    default = default.iloc[[0, 2]].reset_index(drop=True)
    result = differential_fitting_losses(model, default)
    assert len(result) == 2
    assert result.loc[0, "mae_deg_c"] == pytest.approx(0.7)
    assert result.loc[1, "mae_deg_c"] == pytest.approx(-0.3)
    assert result.loc[0, "model_mae_deg_c"] == pytest.approx(0.5)
    assert result.loc[0, "default_mae_deg_c"] == pytest.approx(1.2)
    assert result["model_family"].iloc[0] == "differential_climatology"


def test_r6_differential_predictions_level_fallbacks() -> None:
    fit = pd.DataFrame(
        {
            "network_id": ["n1", "n1", "n1", "n1"],
            "station_id": ["s1", "s1", "s2", "s3"],
            "gap_length": [7, 30, 7, 7],
            "season": ["DJF", "DJF", "DJF", "DJF"],
            "placement": [0, 0, 0, 0],
            "gap_start": pd.to_datetime(["2020-01-01"] * 4),
            "mae_deg_c": [0.8, 1.2, 0.6, 0.4],
        }
    )
    evaluation = pd.DataFrame(
        {
            "network_id": ["n1", "n1", "n1", "n2"],
            "station_id": ["s1", "s2", "s3", "s9"],
            "gap_length": [7, 30, 7, 7],
            "placement": [0, 0, 0, 0],
            "gap_start": pd.to_datetime(["2021-01-01"] * 4),
        }
    )
    result = r6_differential_predictions(fit, evaluation)
    assert result["r6_diff_prediction"].iloc[0] == pytest.approx(0.8)
    assert result["r6_diff_prediction"].iloc[1] == pytest.approx(1.2)
    assert result["r6_diff_prediction"].iloc[2] == pytest.approx(0.4)
    assert result["r6_diff_prediction"].iloc[3] == pytest.approx(
        float(fit["mae_deg_c"].mean())
    )


def test_realized_default_mae_benefit() -> None:
    placements = pd.DataFrame(
        {
            "mae_deg_c": [0.5, np.nan, 0.7],
            "climatology_mae_deg_c": [1.5, 1.0, np.nan],
        }
    )
    benefit = realized_default_mae(placements)
    assert benefit.iloc[0] == pytest.approx(1.0)
    assert np.isnan(benefit.iloc[1])
    assert np.isnan(benefit.iloc[2])
