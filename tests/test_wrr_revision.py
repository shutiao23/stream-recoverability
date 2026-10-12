from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.experiments.wrr_revision.benefit import (
    attach_component_predictors,
    difference_identity_gap,
    history_switch_rule,
    ridge_benefit_predictor,
)
from stream_recoverability.experiments.wrr_revision.decision import (
    choose_tau,
    evaluate_rules,
    policy_metrics,
)
from stream_recoverability.experiments.wrr_revision.features import (
    neighbor_boundary_series,
    sample_training_blocks,
)
from stream_recoverability.experiments.wrr_revision.mechanism import (
    SCENARIOS,
    score_scenario,
    scenario_verdict,
    simulate_system,
)
from stream_recoverability.experiments.wrr_revision.recoverers import fit_station_recoverers
from stream_recoverability.experiments.wrr_revision.score import crossing_day, score_network
from stream_recoverability.experiments.wrr_revision.thermal import (
    annual_exceedance_days,
    annual_hottest_consecutive_mean,
    benefit,
    exceedance_days,
    hottest_consecutive_mean,
    seasonal_hottest_consecutive_mean,
    series_losses,
)


SMALL_XGB = {
    "n_estimators": 8,
    "max_depth": 2,
    "learning_rate": 0.2,
    "subsample": 1.0,
    "colsample_bytree": 1.0,
    "random_state": 0,
    "n_jobs": 1,
    "objective": "reg:squarederror",
    "verbosity": 0,
}


def _panel(n_years: int = 6) -> pd.DataFrame:
    index = pd.date_range("2014-01-01", periods=365 * n_years, freq="D")
    day = np.arange(len(index), dtype=float)
    season = 12.0 + 8.0 * np.sin(2.0 * np.pi * day / 365.25)
    return pd.DataFrame(
        {
            "target": season + 0.4 * np.sin(day / 19.0),
            "donor_a": season + 0.2 * np.cos(day / 11.0),
            "donor_b": 0.8 * season + 1.5,
        },
        index=index,
    )


def test_hottest_30_and_benefit_identity() -> None:
    index = pd.date_range("2020-01-01", periods=60, freq="D")
    truth = pd.Series(np.linspace(10.0, 20.0, 60), index=index)
    assert abs(hottest_consecutive_mean(truth, window=30) - float(truth.iloc[30:].mean())) < 1e-9
    default = truth.copy()
    alt = truth.copy()
    alt.iloc[30:60] = 0.0
    losses = series_losses(truth, default, alt)
    assert losses["hottest_30_benefit"] < 0
    assert abs(benefit(1.0, 0.4) - 0.6) < 1e-12
    assert exceedance_days(truth, threshold_c=15.0) == float((truth > 15.0).sum())

    year = pd.date_range("2020-01-01", "2020-12-31", freq="D")
    complete = pd.Series(10.0, index=year)
    complete.loc["2020-07-01":"2020-07-30"] = 25.0
    assert abs(annual_hottest_consecutive_mean(complete, 2020) - 25.0) < 1e-9
    winter_gap = complete.copy()
    winter_gap.loc["2020-01-15"] = np.nan
    assert np.isnan(annual_hottest_consecutive_mean(winter_gap, 2020))
    assert np.isnan(annual_exceedance_days(winter_gap, 2020))
    assert np.isfinite(hottest_consecutive_mean(winter_gap))
    assert abs(seasonal_hottest_consecutive_mean(winter_gap, 2020) - 25.0) < 1e-9
    assert abs(
        annual_hottest_consecutive_mean(complete, 2020)
        - seasonal_hottest_consecutive_mean(complete, 2020)
    ) < 1e-9


def test_neighbor_boundary_is_adjacent_mean_not_gap_interp() -> None:
    target = pd.Series([0.0, 10.0, 20.0, 30.0, 40.0])
    neighbor = neighbor_boundary_series(target)
    assert np.isnan(neighbor.iloc[0])
    assert neighbor.iloc[2] == 20.0


def test_crossing_day_censors_when_never_negative() -> None:
    frame = pd.DataFrame(
        {
            "network_id": ["n"] * 4,
            "station_id": ["s"] * 4,
            "recoverer": ["m"] * 4,
            "gap_length": [7, 30, 90, 180],
            "mae_benefit": [1.0, 0.8, 0.4, 0.1],
        }
    )
    out = crossing_day(frame, recoverer="m")
    assert bool(out.loc[0, "crossed"]) is False
    assert out.loc[0, "censoring"] == "right_censored"
    assert out.loc[0, "last_evaluated_length"] == 180
    frame2 = frame.copy()
    frame2.loc[3, "mae_benefit"] = -0.2
    crossed = crossing_day(frame2, recoverer="m")
    assert bool(crossed.loc[0, "crossed"]) is True
    assert 90 < float(crossed.loc[0, "crossing_day"]) < 180


def test_diff_equals_seasonal_empirical_on_complete_cells() -> None:
    rng = np.random.default_rng(0)
    hist_rows = []
    ev_rows = []
    for station in ("a", "b"):
        for gap in (7, 30):
            for season, month in (("DJF", 1), ("JJA", 7)):
                for i in range(6):
                    model = 0.5 + 0.01 * i
                    clim = 1.2
                    hist_rows.append(
                        {
                            "network_id": "n",
                            "station_id": station,
                            "gap_length": gap,
                            "season": season,
                            "gap_start": pd.Timestamp(f"2016-{month:02d}-0{i+1}"),
                            "mae_deg_c": model,
                            "climatology_mae_deg_c": clim,
                        }
                    )
                ev_rows.append(
                    {
                        "network_id": "n",
                        "station_id": station,
                        "gap_length": gap,
                        "season": season,
                        "gap_start": pd.Timestamp(f"2019-{month:02d}-15"),
                        "mae_deg_c": 0.7,
                        "climatology_mae_deg_c": 1.2,
                    }
                )
    hist = pd.DataFrame(hist_rows)
    ev = pd.DataFrame(ev_rows)
    attached = attach_component_predictors(hist, ev)
    gap = attached["diff_prediction"] - attached["seasonal_empirical"]
    assert float(gap.abs().max()) < 1e-12
    assert difference_identity_gap(attached) < 1e-12
    switch = history_switch_rule(hist)
    assert set(switch["chosen"]).issubset({"default_difficulty", "neg_risk"})
    ridge = ridge_benefit_predictor(hist.assign(realized_benefit=hist["climatology_mae_deg_c"]-hist["mae_deg_c"]), ev)
    assert len(ridge) == len(ev)
    assert rng is not None


def test_single_station_network_scores_without_donors() -> None:
    panel = _panel()[["target"]]
    scored = score_network(
        "solo",
        panel,
        placements=pd.DataFrame(
            {
                "network_id": ["solo"],
                "station_id": ["target"],
                "gap_length": [7],
                "placement": [0],
                "gap_start": [panel.index[2000]],
                "gap_end": [panel.index[2006]],
                "information_condition": ["B_union_D"],
            }
        ),
        xgboost_parameters=SMALL_XGB,
        include_external=False,
        generate_extra_gaps=False,
        target_stations=("target",),
    )
    assert not scored.empty
    names = set(scored["recoverer"])
    assert "doy_climatology" in names
    assert "linear_interp" in names
    assert "ridge_neighbor_boundary" in names
    assert "donor_only_ridge" not in names


def test_adopt_rule_can_beat_or_lose_to_all_default() -> None:
    realized = pd.Series([0.5, 0.4, -2.0, -1.5])
    predicted = pd.Series([0.6, 0.5, 0.8, 0.7])
    table = evaluate_rules(
        pd.DataFrame({"pred": predicted, "realized_benefit": realized}),
        predicted_col="pred",
        tau=0.0,
    )
    all_def = table.loc[table["rule"].eq("all_default")].iloc[0]
    mean_rule = table.loc[table["rule"].eq("mean_gt_tau")].iloc[0]
    assert all_def["net_benefit_all_cases"] == 0.0
    assert mean_rule["net_benefit_all_cases"] < 0
    chosen = choose_tau(predicted, realized)
    assert chosen["tau"] >= 0.8 or chosen["net_benefit_all_cases"] >= 0
    good = evaluate_rules(
        pd.DataFrame({"pred": [1, 1, -1, -1], "realized_benefit": [1.0, 0.5, -3.0, -2.0]}),
        predicted_col="pred",
        tau=0.0,
    )
    assert policy_metrics(
        pd.Series([1.0, 0.5, -3.0, -2.0]),
        pd.Series([True, True, False, False]),
    )["beats_all_default"] == 1.0
    assert float(good.loc[good["rule"].eq("mean_gt_tau"), "beats_all_default"].iloc[0]) == 1.0


def test_fair_recovery_fits_neighbor_and_longblock_on_synthetic_panel() -> None:
    panel = _panel()
    scored = score_network(
        "synthetic",
        panel,
        placements=pd.DataFrame(
            {
                "network_id": ["synthetic"],
                "station_id": ["target"],
                "gap_length": [7],
                "placement": [0],
                "gap_start": [panel.index[2000]],
                "gap_end": [panel.index[2006]],
                "information_condition": ["B_union_D"],
            }
        ),
        xgboost_parameters=SMALL_XGB,
        include_external=False,
        generate_extra_gaps=False,
        target_stations=("target",),
    )
    names = set(scored["recoverer"])
    assert "xgb_neighbor_boundary" in names
    assert "xgb_longblock_boundary" in names
    assert "donor_only_ridge" in names
    assert "doy_climatology" in names
    clim = scored.loc[scored["recoverer"].eq("doy_climatology"), "mae_benefit"]
    assert abs(float(clim.iloc[0])) < 1e-9


def test_training_blocks_are_inside_fitting_years() -> None:
    panel = _panel()
    train = pd.Series(panel.index.year <= 2017, index=panel.index)
    blocks = sample_training_blocks(
        panel,
        target_station="target",
        donors=("donor_a",),
        train_mask=train,
        gap_lengths=(7, 30),
        blocks_per_length=4,
    )
    assert blocks
    for start, length in blocks:
        assert train.iloc[start]
        assert train.iloc[start + length - 1]


def test_mechanism_no_information_loss_struct_does_not_go_harmful() -> None:
    assert "no_information_loss" in SCENARIOS
    panel = simulate_system("no_information_loss", n_days=365 * 6, seed=1)
    assert panel["target"].notna().all()
    scores = score_scenario("no_information_loss", seed=1)
    verdict = scenario_verdict(scores)
    struct = verdict.loc[verdict["recoverer"].eq("structurally_correct")].iloc[0]
    assert bool(struct["crossed"]) is False
