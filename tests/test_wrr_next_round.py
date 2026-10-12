from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.experiments.wrr_revision.decision import (
    same_adoption_rate_random,
    simple_length_season_adopt,
)
from stream_recoverability.experiments.wrr_revision.failures import (
    heat_event_mask,
    hide_donors_on_gaps,
    seasonal_threshold_from_training,
    transplant_month_length_pattern,
)
from stream_recoverability.experiments.wrr_revision.information import (
    information_conditioned_recoverer,
    keep_half_donors,
    split_donors_by_correlation,
)
from stream_recoverability.experiments.wrr_revision.replay import hide_gap_interiors, replay_case
from stream_recoverability.experiments.wrr_revision.thermal_decision import complete_year_split


def test_keep_half_and_correlation_split() -> None:
    assert keep_half_donors(["b", "a", "c", "d"]) == ("a", "b")
    assert keep_half_donors(["only"]) == ()
    strong, weak = split_donors_by_correlation(pd.Series({"x": 0.8, "y": 0.1, "z": np.nan}))
    assert strong == ("x",)
    assert weak == ("y",)


def test_information_conditioned_policy_does_not_require_right_when_donors_exist() -> None:
    assert (
        information_conditioned_recoverer(
            donors_observed=True, right_present=False, air_present=True, gap_length=180
        )
        == "donor_only_ridge"
    )
    assert (
        information_conditioned_recoverer(
            donors_observed=False, right_present=True, air_present=True, gap_length=90
        )
        == "air_ridge"
    )
    assert (
        information_conditioned_recoverer(
            donors_observed=False, right_present=True, air_present=False, gap_length=30
        )
        == "linear_interp"
    )
    assert (
        information_conditioned_recoverer(
            donors_observed=False, right_present=False, air_present=False, gap_length=30
        )
        == "smooth_climatology"
    )


def test_complete_year_split_keeps_eval_out_of_fit() -> None:
    fit, hist, ev = complete_year_split([2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024])
    assert set(fit).isdisjoint(ev)
    assert set(hist).isdisjoint(ev)
    assert set(fit).isdisjoint(hist)
    assert max(fit + hist) < min(ev)
    assert complete_year_split([2020]) == ((2020,), (), ())
    fit2, hist2, ev2 = complete_year_split([2020, 2021])
    assert fit2 == (2020,)
    assert hist2 == ()
    assert ev2 == (2021,)


def test_hide_gap_interiors_blocks_adjacent_boundaries() -> None:
    index = pd.date_range("2020-07-01", periods=20, freq="D")
    truth = pd.Series(np.arange(20, dtype=float), index=index)
    gaps = pd.DataFrame(
        {
            "gap_start": [index[4], index[6]],
            "gap_length": [2, 2],
        }
    )
    masked = hide_gap_interiors(truth, gaps)
    assert masked.iloc[4:6].isna().all()
    assert masked.iloc[6:8].isna().all()
    assert np.isfinite(masked.iloc[3])
    assert np.isfinite(masked.iloc[8])
    assert np.isnan(masked.iloc[6])


def test_seasonal_heat_threshold_ignores_eval_truth() -> None:
    index = pd.date_range("2018-01-01", periods=365 * 3, freq="D")
    values = pd.Series(10.0, index=index)
    values.loc["2020-07-01":"2020-07-10"] = 40.0
    train = pd.Series(index.year < 2020, index=index)
    threshold = seasonal_threshold_from_training(values, train, quantile=0.9)
    july = threshold.loc["2020-07-05"]
    assert july < 20.0
    events = heat_event_mask(values, threshold, min_duration=3)
    assert bool(events.loc["2020-07-05"]) is True
    assert bool(events.loc["2020-01-15"]) is False


def test_same_adoption_rate_random_and_simple_rule() -> None:
    adopt = pd.Series([True, True, False, False, False, False, False, False, False, False])
    random = same_adoption_rate_random(adopt, seed=1)
    assert abs(float(random.mean()) - 0.2) <= 0.4
    gaps = pd.DataFrame(
        {
            "gap_start": pd.to_datetime(["2020-07-01", "2020-01-01", "2020-07-01"]),
            "gap_length": [14, 14, 180],
        }
    )
    rule = simple_length_season_adopt(gaps)
    assert rule.tolist() == [True, False, False]


def test_transplant_and_co_missing() -> None:
    index = pd.date_range("2020-01-01", periods=366, freq="D")
    geometry = pd.DataFrame({"gap_start": [pd.Timestamp("2018-07-10")], "gap_length": [14]})
    placed = transplant_month_length_pattern(index, geometry, max_gaps=1)
    assert len(placed) == 1
    assert pd.Timestamp(placed.iloc[0]["gap_start"]).month == 7
    panel = pd.DataFrame({"target": 10.0, "donor": 11.0}, index=index)
    hidden = hide_donors_on_gaps(panel, ["donor"], placed)
    start = int(index.get_indexer([pd.Timestamp(placed.iloc[0]["gap_start"])])[0])
    assert hidden["donor"].iloc[start : start + 14].isna().all()
    assert hidden["target"].notna().all()


def test_replay_hides_interiors_before_interpolation() -> None:
    from stream_recoverability.experiments.wrr_revision.recoverers import LinearInterpRecoverer

    index = pd.date_range("2020-07-01", periods=15, freq="D")
    truth = pd.Series(np.linspace(0.0, 14.0, 15), index=index)
    default = np.full(15, 99.0)
    gaps = pd.DataFrame({"gap_start": [index[3], index[5]], "gap_length": [2, 2], "year": [2020, 2020]})
    recoverer = LinearInterpRecoverer(
        name="linear_interp",
        family="interpolator",
        training_protocol="none",
        uses_boundary=True,
        uses_donors=False,
        uses_air=False,
        uses_flow=False,
        information_group="time_neighbor",
        n_train_rows=0,
        extra={},
    )
    out = replay_case(
        truth,
        default_fill=default,
        recoverers={"linear_interp": recoverer, "doy_climatology": recoverer},
        features=pd.DataFrame(index=index),
        gaps=gaps,
        predicted_benefit=pd.Series([1.0, 1.0]),
        adopt=pd.Series([True, True]),
        chosen_recoverer="linear_interp",
    )
    assert out["n_gaps"] == 2.0
    assert np.isfinite(out["n_adopted"])
