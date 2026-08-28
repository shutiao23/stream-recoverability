from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.experiments.development_data import (
    complete_operator_network_predictions,
)
from stream_recoverability.experiments.development_recovery import (
    GAP_LENGTHS,
    auxiliary_features,
    score_network,
    select_placements,
    station_gap_summary,
    year_split,
)


def _temperature_panel() -> pd.DataFrame:
    index = pd.date_range("2014-01-01", "2019-12-31", freq="D")
    day = np.arange(len(index), dtype=float)
    seasonal = 11.0 + 7.0 * np.sin(2.0 * np.pi * day / 365.25)
    return pd.DataFrame(
        {
            "target": seasonal + 0.8 * np.sin(day / 23.0),
            "donor_a": seasonal + 0.3 * np.cos(day / 17.0),
            "donor_b": 0.7 * seasonal + 2.0 * np.sin(day / 31.0),
        },
        index=index,
    )


def _auxiliary(*, include_hydraulics: bool = True) -> pd.DataFrame:
    index = pd.date_range("2014-01-01", "2019-12-31", freq="D")
    day = np.arange(len(index), dtype=float)
    rows = [
        pd.DataFrame(
            {
                "date": index,
                "site_id": "target",
                "variable": "Ta",
                "value": 10.0 + 9.0 * np.sin(2.0 * np.pi * day / 365.25),
                "source": "nasa_power_daily_point",
                "natural_observed": True,
                "quality_approved": True,
                "approval_status": "NotApplicable",
                "qc_status": "provider_value",
            }
        )
    ]
    if include_hydraulics:
        rows.append(
            pd.DataFrame(
                {
                    "date": index,
                    "site_id": "target",
                    "variable": "F",
                    "value": 4.0 + np.cos(day / 19.0),
                    "source": "usgs_ogc_daily",
                    "natural_observed": True,
                    "quality_approved": True,
                    "approval_status": "Approved",
                    "qc_status": "approved",
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


SMALL_XGBOOST = {
    "n_estimators": 12,
    "max_depth": 2,
    "learning_rate": 0.15,
    "subsample": 1.0,
    "colsample_bytree": 1.0,
    "random_state": 0,
    "n_jobs": 1,
    "objective": "reg:squarederror",
    "verbosity": 0,
}


def test_year_split_uses_first_seventy_percent_of_calendar_years() -> None:
    index = pd.date_range("2010-01-01", "2019-12-31", freq="D")
    mask, training_years, evaluation_years = year_split(index)
    assert training_years == tuple(range(2010, 2017))
    assert evaluation_years == (2017, 2018, 2019)
    assert set(index[mask].year) == set(training_years)
    assert set(index[~mask].year) == set(evaluation_years)

    seven_year_index = pd.date_range("2010-01-01", "2016-12-31", freq="D")
    _, seven_training, seven_evaluation = year_split(seven_year_index)
    assert seven_training == (2010, 2011, 2012, 2013, 2014)
    assert seven_evaluation == (2015, 2016)


def test_auxiliary_features_apply_plain_provider_qualification() -> None:
    auxiliary = _auxiliary()
    rejected = pd.DataFrame(
        {
            "date": [pd.Timestamp("2014-01-01")],
            "site_id": ["target"],
            "variable": ["P"],
            "value": [99.0],
            "source": ["nasa_power_daily_point"],
            "natural_observed": [True],
            "quality_approved": [True],
            "approval_status": ["NotApplicable"],
            "qc_status": ["fill_value"],
        }
    )
    values = auxiliary_features(
        pd.concat([auxiliary, rejected], ignore_index=True),
        target_station="target",
        target_index=_temperature_panel().index,
    )
    assert {"M__Ta", "H__F"}.issubset(values.columns)
    assert "M__P" not in values.columns
    assert values[["M__Ta", "H__F"]].notna().all().all()


def test_fixed_models_score_all_gaps_on_paired_test_placements() -> None:
    scored = score_network(
        "river_1",
        _temperature_panel(),
        _auxiliary(),
        target_stations=("target",),
        gap_lengths=GAP_LENGTHS,
        placements_per_gap=3,
        xgboost_parameters=SMALL_XGBOOST,
    )
    losses = scored["placement_losses"]
    assert len(losses) == len(GAP_LENGTHS) * 3 * 2
    assert set(losses["gap_length"]) == set(GAP_LENGTHS)
    assert set(losses["information_condition"]) == {
        "B_union_D",
        "B_union_D_union_M_union_H",
    }
    assert losses["training_years"].eq("2014|2015|2016|2017").all()
    assert losses["evaluation_years"].eq("2018|2019").all()
    assert losses["gap_start"].dt.year.isin((2018, 2019)).all()
    assert (
        (losses["gap_end"] - losses["gap_start"]).dt.days
        == losses["gap_length"] - 1
    ).all()
    assert np.isfinite(
        losses[["mae_deg_c", "rmse_deg_c", "climatology_mae_deg_c"]]
    ).all().all()

    starts = losses.pivot(
        index=["gap_length", "placement"],
        columns="information_condition",
        values="gap_start",
    )
    assert starts.nunique(axis=1).eq(1).all()
    assert scored["eligibility"]["eligible"].all()
    assert len(scored["station_gap_summary"]) == len(GAP_LENGTHS) * 2


def test_recovery_and_operator_use_identical_station_rosters(tmp_path: Path) -> None:
    panel = _temperature_panel()
    auxiliary = _auxiliary()
    scored = score_network(
        "river_roster",
        panel,
        auxiliary,
        target_stations=("target",),
        gap_lengths=(7,),
        placements_per_gap=2,
        xgboost_parameters=SMALL_XGBOOST,
    )["placement_losses"].query(
        "information_condition == 'B_union_D_union_M_union_H'"
    ).iloc[0]
    temperature_path = tmp_path / "temperature.csv"
    auxiliary_path = tmp_path / "auxiliary.parquet"
    panel.rename_axis("date").reset_index().to_csv(temperature_path, index=False)
    auxiliary.to_parquet(auxiliary_path, index=False)
    operator = complete_operator_network_predictions(
        temperature_path,
        auxiliary_path,
        network_id="river_roster",
        gaps=(7,),
        target_stations=("target",),
    ).iloc[0]
    assert operator["donor_station_ids"] == scored["donor_station_ids"]
    assert operator["meteorology_feature_ids"] == scored["meteorology_feature_ids"]
    assert operator["hydraulics_feature_ids"] == scored["hydraulics_feature_ids"]
    assert operator["operator_training_years"] == scored["training_years"]


def test_missing_hydraulics_is_an_explicit_full_condition_ineligibility() -> None:
    scored = score_network(
        "river_2",
        _temperature_panel(),
        _auxiliary(include_hydraulics=False),
        target_stations=("target",),
        gap_lengths=(14,),
        placements_per_gap=2,
        xgboost_parameters=SMALL_XGBOOST,
    )
    losses = scored["placement_losses"]
    assert set(losses["information_condition"]) == {"B_union_D"}
    full = scored["eligibility"].loc[
        scored["eligibility"]["information_condition"].eq(
            "B_union_D_union_M_union_H"
        )
    ].iloc[0]
    assert bool(full["eligible"]) is False
    assert full["reason"] == "no_hydraulics_with_minimum_training_days"
    assert full["selected_placements"] == 0


def test_gap_candidates_require_every_declared_donor_on_every_day() -> None:
    panel = _temperature_panel()
    panel.loc[panel.index.year.isin((2018, 2019)), "donor_b"] = float("nan")
    scored = score_network(
        "river_missing_donor",
        panel,
        _auxiliary(),
        target_stations=("target",),
        gap_lengths=(7,),
        placements_per_gap=2,
        xgboost_parameters=SMALL_XGBOOST,
    )
    eligibility = scored["eligibility"]
    assert eligibility["donor_feature_count"].eq(2).all()
    assert eligibility["candidate_windows"].eq(0).all()
    assert eligibility["selected_placements"].eq(0).all()


def test_full_gap_candidates_require_every_auxiliary_feature_on_every_day() -> None:
    auxiliary = _auxiliary()
    precipitation = auxiliary.loc[auxiliary["variable"].eq("Ta")].copy()
    precipitation["variable"] = "P"
    precipitation.loc[
        pd.to_datetime(precipitation["date"]).dt.year.isin((2018, 2019)), "value"
    ] = float("nan")
    scored = score_network(
        "river_missing_meteorology",
        _temperature_panel(),
        pd.concat([auxiliary, precipitation], ignore_index=True),
        target_stations=("target",),
        gap_lengths=(7,),
        placements_per_gap=2,
        xgboost_parameters=SMALL_XGBOOST,
    )
    full = scored["eligibility"].loc[
        scored["eligibility"]["information_condition"].eq(
            "B_union_D_union_M_union_H"
        )
    ].iloc[0]
    assert full["meteorology_feature_count"] == 2
    assert full["candidate_windows"] == 0
    assert full["selected_placements"] == 0


def test_station_gap_summary_uses_mean_placement_mae_as_loss() -> None:
    placements = pd.DataFrame(
        {
            "network_id": ["n", "n"],
            "station_id": ["s", "s"],
            "gap_length": [30, 30],
            "information_condition": ["B_union_D", "B_union_D"],
            "placement": [0, 1],
            "mae_deg_c": [1.0, 3.0],
            "rmse_deg_c": [1.5, 3.5],
            "climatology_mae_deg_c": [4.0, 4.0],
            "achieved_skill": [0.75, 0.25],
            "gap_start": pd.to_datetime(["2020-01-01", "2020-03-01"]),
            "gap_end": pd.to_datetime(["2020-01-30", "2020-03-30"]),
        }
    )
    summary = station_gap_summary(placements).iloc[0]
    assert summary["n_placements"] == 2
    assert summary["observed_recovery_loss"] == 2.0
    assert summary["placement_loss_sd"] == np.sqrt(2.0)
    assert summary["achieved_skill"] == 0.5


def test_even_placement_selection_spans_the_eligible_roster() -> None:
    selected = select_placements(np.arange(101), count=5)
    assert selected.tolist() == [0, 25, 50, 75, 100]


def test_zero_climatology_error_keeps_absolute_loss_and_undefined_skill() -> None:
    index = pd.date_range("2010-01-01", "2015-12-31", freq="D")
    panel = pd.DataFrame({"target": 5.0, "donor": 5.0}, index=index)
    scored = score_network(
        "constant_river",
        panel,
        None,
        target_stations=("target",),
        gap_lengths=(7,),
        placements_per_gap=1,
        xgboost_parameters=SMALL_XGBOOST,
    )
    loss = scored["placement_losses"].iloc[0]
    assert np.isfinite(loss["mae_deg_c"])
    assert loss["climatology_mae_deg_c"] == 0.0
    assert np.isnan(loss["achieved_skill"])


def test_script_inventory_excludes_empty_temperature_csv(tmp_path: Path) -> None:
    valid = tmp_path / "valid"
    empty = tmp_path / "empty"
    valid.mkdir()
    empty.mkdir()
    pd.DataFrame({"date": ["2020-01-01"], "station": [4.0]}).to_csv(
        valid / "daily_wide_qc.csv", index=False
    )
    pd.DataFrame(index=["2020-01-01"]).to_csv(empty / "daily_wide_qc.csv")
    script = Path(__file__).parents[1] / "scripts/108_score_development_recovery.py"
    spec = importlib.util.spec_from_file_location("score_development_recovery", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.temperature_input_paths(tmp_path) == [valid / "daily_wide_qc.csv"]
