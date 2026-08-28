import numpy as np
import pandas as pd

from stream_recoverability.experiments.development_recovery import score_network
from stream_recoverability.experiments.recovery_roster import (
    empirical_transfer_predictions,
    fitting_period_empirical_losses,
    score_model_roster_on_placements,
    season_label,
)


def _panel() -> pd.DataFrame:
    index = pd.date_range("2010-01-01", "2021-12-31", freq="D")
    phase = 2 * np.pi * index.dayofyear.to_numpy() / 365.25
    return pd.DataFrame(
        {
            "001": 10 + 6 * np.sin(phase),
            "002": 10.5 + 5.5 * np.sin(phase + 0.05),
            "003": 9.5 + 6.2 * np.sin(phase - 0.04),
        },
        index=index,
    )


def test_season_labels_are_stable() -> None:
    assert season_label(
        pd.to_datetime(["2020-01-01", "2020-04-01", "2020-07-01", "2020-10-01"])
    ).tolist() == [
        "DJF",
        "MAM",
        "JJA",
        "SON",
    ]


def test_alternative_roster_scores_existing_gaps() -> None:
    panel = _panel()
    base = score_network(
        "n1",
        panel,
        None,
        gap_lengths=(7,),
        placements_per_gap=2,
        xgboost_parameters={
            "n_estimators": 5,
            "max_depth": 2,
            "random_state": 0,
            "n_jobs": 1,
            "objective": "reg:squarederror",
        },
    )["placement_losses"]
    result = score_model_roster_on_placements("n1", panel, base)
    assert set(result["model_family"]) == {
        "seasonal_boundary_ridge",
        "donor_blup_ridge",
    }
    assert result["mae_deg_c"].ge(0).all()


def test_empirical_curve_is_scored_before_outer_evaluation() -> None:
    panel = _panel()
    base = score_network(
        "n1",
        panel,
        None,
        gap_lengths=(7,),
        placements_per_gap=2,
        xgboost_parameters={
            "n_estimators": 5,
            "max_depth": 2,
            "random_state": 0,
            "n_jobs": 1,
            "objective": "reg:squarederror",
        },
    )["placement_losses"]
    empirical = fitting_period_empirical_losses(
        "n1",
        panel,
        base,
        gaps=(7,),
        placements_per_season=2,
        xgboost_parameters={
            "n_estimators": 5,
            "max_depth": 2,
            "random_state": 0,
            "n_jobs": 1,
            "objective": "reg:squarederror",
        },
    )
    assert not empirical.empty
    assert empirical["inner_score_years"].str.contains("2017").any()
    predicted = empirical_transfer_predictions(empirical, base)
    assert predicted["empirical_transfer_prediction"].notna().all()


def test_empirical_curve_uses_explicit_training_only_network_mean_for_unseen_horizon() -> (
    None
):
    empirical = pd.DataFrame(
        {
            "network_id": ["n1", "n1"],
            "station_id": ["001", "002"],
            "gap_length": [7, 7],
            "season": ["JJA", "JJA"],
            "mae_deg_c": [1.0, 3.0],
        }
    )
    placements = pd.DataFrame(
        {
            "network_id": ["n1"],
            "station_id": ["001"],
            "gap_length": [365],
            "gap_start": ["2020-07-01"],
            "information_condition": ["B_union_D"],
        }
    )
    predicted = empirical_transfer_predictions(empirical, placements)
    assert predicted.loc[0, "empirical_transfer_prediction"] == 2.0
    assert predicted.loc[0, "empirical_transfer_source"] == "network_mean_fallback"
    assert not bool(predicted.loc[0, "empirical_transfer_supported"])


def test_empirical_curve_normalizes_mixed_station_identifier_dtypes() -> None:
    empirical = pd.DataFrame(
        {
            "network_id": [1],
            "station_id": [123],
            "gap_length": [7],
            "season": ["JJA"],
            "mae_deg_c": [0.75],
        }
    )
    placements = pd.DataFrame(
        {
            "network_id": ["1"],
            "station_id": ["123"],
            "gap_length": [7],
            "gap_start": ["2020-07-01"],
            "information_condition": ["B_union_D"],
        }
    )
    predicted = empirical_transfer_predictions(empirical, placements)
    assert predicted.loc[0, "empirical_transfer_prediction"] == 0.75
    assert predicted.loc[0, "empirical_transfer_source"] == "station_gap_season"
