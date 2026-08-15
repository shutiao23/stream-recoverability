import json
import runpy
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import stream_recoverability.analysis.statistics as statistics_module
from stream_recoverability.analysis.compensation import (
    benjamini_hochberg_fdr,
    build_value_function,
    combination_label,
    compensation_gains,
    exact_shapley,
    information_combinations,
    knn_mutual_information,
    shapley_table,
    transfer_entropy,
)
from stream_recoverability.analysis.frontiers import (
    DENSE_T_GAPS,
    application_frontier,
    cluster_bootstrap_frontier_ci,
    estimate_frontiers,
    interpolate_threshold_crossing,
    segmented_sse_breakpoint,
    statistical_frontier,
)
from stream_recoverability.analysis.resilience import (
    complete_resilience_units,
    node_importance,
    resilience_auc,
    resilience_curve,
)
from stream_recoverability.analysis.science_metrics import (
    mann_kendall_test,
    scientific_metrics_by_event,
    sen_slope,
    trend_preservation,
)
from stream_recoverability.analysis.statistics import (
    compare_models,
    fit_mixed_effects_by_design,
    holm_correction,
    paired_bootstrap_ci,
    paired_wilcoxon,
)
from stream_recoverability.analysis.uncertainty import (
    interval_calibration_by_gap,
    overall_calibration,
    uncertainty_growth,
)


def test_exact_shapley_satisfies_efficiency_for_all_16_combinations():
    weights = {"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0}
    values = {
        subset: 10.0 + sum(weights[source] for source in subset)
        for subset in information_combinations()
    }
    contributions = exact_shapley(values)
    assert contributions == pytest.approx(weights)
    assert sum(contributions.values()) == pytest.approx(
        values[frozenset(weights)] - values[frozenset()]
    )
    value_table = pd.DataFrame(
        {
            "combination": [
                "S0" if not subset else "S0+" + "+".join(sorted(subset))
                for subset in values
            ],
            "value": list(values.values()),
            "raw_metric": list(values.values()),
            "higher_is_better": True,
        }
    )
    gains = compensation_gains(value_table).set_index("source")
    for source, weight in weights.items():
        assert gains.loc[source, "mean_marginal_gain"] == pytest.approx(weight)


def test_shapley_validates_each_scenario_training_seed_before_aggregation():
    rows = []
    combinations = information_combinations()
    for scenario, mask_seed, available in (
        ("complete", 101, combinations),
        ("incomplete", 102, combinations[:-1]),
    ):
        for index, subset in enumerate(available):
            rows.append(
                {
                    "scenario_id": scenario,
                    "training_seed": 11,
                    "mask_seed": mask_seed,
                    "station_id": "S1",
                    "target": "T",
                    "gap_length": 30,
                    "model": "proposed",
                    "information_combination": combination_label(subset),
                    "MAE": 20.0 - index,
                }
            )
    values = build_value_function(pd.DataFrame(rows))
    diagnostics = values.groupby("scenario_id", dropna=False).first()
    assert bool(diagnostics.loc["complete", "complete_2_to_n"])
    assert not bool(diagnostics.loc["incomplete", "complete_2_to_n"])
    assert "S0+A+B+C+D" in diagnostics.loc["incomplete", "missing_combinations"]

    shapley = shapley_table(values).set_index(["scenario_id", "source"])
    assert shapley.loc[("complete", "A"), "reason"] is None
    assert np.isfinite(shapley.loc[("complete", "A"), "shapley"])
    assert bool(shapley.loc[("incomplete", "A"), "excluded"])
    assert np.isnan(shapley.loc[("incomplete", "A"), "shapley"])


def test_paired_bootstrap_and_test_use_shared_event_units():
    rows = []
    for event in range(20):
        rows.extend(
            [
                {
                    "scenario_id": f"E{event}",
                    "station_id": "S1",
                    "target": "T",
                    "model": "A",
                    "MAE": event / 10 + 1.0,
                },
                {
                    "scenario_id": f"E{event}",
                    "station_id": "S1",
                    "target": "T",
                    "model": "B",
                    "MAE": event / 10,
                },
            ]
        )
    events = pd.DataFrame(rows)
    bootstrap = paired_bootstrap_ci(events, "A", "B", n_boot=200, seed=7)
    assert bootstrap["n_pairs"] == 20
    assert bootstrap["estimate"] == pytest.approx(1.0)
    assert bootstrap["ci_lower"] == pytest.approx(1.0)
    assert bootstrap["ci_upper"] == pytest.approx(1.0)
    test = paired_wilcoxon(events, "A", "B")
    assert test["n_pairs"] == 20
    assert test["p_value"] < 0.01
    adjusted = holm_correction([0.01, 0.04, np.nan])
    np.testing.assert_allclose(adjusted[:2], [0.02, 0.04])
    assert np.isnan(adjusted[2])


def test_comparisons_do_not_pool_distinct_design_regimes():
    rows = []
    for experiment, mask_type, failed, difference in (
        ("M2", "block", [], -1.0),
        ("M3", "multiblock", [], -5.0),
        ("SCI_NET", "matched_network", [], -2.0),
        ("SCI_NET", "matched_network", ["S2"], -4.0),
    ):
        for event in range(3):
            common = {
                "scenario_id": f"shared-{event}",
                "experiment": experiment,
                "mask_type": mask_type,
                "layout": "single" if experiment == "M2" else "random",
                "pattern": "T",
                "window_length": 368,
                "training_protocol": "seen_length",
                "station_id": "S1",
                "target_station_id": "S1",
                "target": "T",
                "failed_station_ids": json.dumps(failed),
                "failure_count": len(failed),
                "network_size": 3,
                "gap_length": 30,
                "mask_seed": event,
            }
            rows.extend(
                [
                    {**common, "model": "climatology", "MAE": 10.0},
                    {
                        **common,
                        "model": "candidate",
                        "MAE": 10.0 + difference,
                    },
                ]
            )
    comparisons = compare_models(pd.DataFrame(rows), n_boot=20, seed=3)
    assert len(comparisons) == 4
    estimates = comparisons.set_index("experiment")["estimate"]
    assert estimates.loc["M2"] == pytest.approx(-1.0)
    assert estimates.loc["M3"] == pytest.approx(-5.0)
    assert set(comparisons["mask_type"]) == {
        "block",
        "multiblock",
        "matched_network",
    }
    network_estimates = comparisons.loc[
        comparisons["experiment"].eq("SCI_NET"), "estimate"
    ]
    assert set(network_estimates) == {-2.0, -4.0}


def test_mixed_effects_are_fitted_separately_by_design(monkeypatch):
    events = pd.DataFrame(
        {
            "experiment": ["M2", "M2", "M3", "M3"],
            "mask_type": ["block", "block", "multiblock", "multiblock"],
            "layout": ["single", "single", "random", "random"],
            "pattern": "T",
            "window_length": 368,
            "training_protocol": "seen_length",
            "station_id": ["S1", "S2", "S1", "S2"],
            "target": "T",
            "model": ["A", "B", "A", "B"],
            "gap_length": 30,
            "MAE": [1.0, 2.0, 3.0, 4.0],
        }
    )
    seen: list[tuple[str, str]] = []

    def fake_fit(group, **_kwargs):
        seen.append((group["experiment"].iloc[0], group["mask_type"].iloc[0]))
        return (
            pd.DataFrame(
                {"term": ["Intercept"], "estimate": [1.0], "std_error": [0.1]}
            ),
            {"reason": None, "n_observations": len(group)},
        )

    monkeypatch.setattr(statistics_module, "fit_mixed_effects", fake_fit)
    coefficients, diagnostics = fit_mixed_effects_by_design(events)
    assert seen == [("M2", "block"), ("M3", "multiblock")]
    assert len(coefficients) == 2
    assert len(diagnostics) == 2
    assert set(coefficients["experiment"]) == {"M2", "M3"}


def test_frontier_crossing_is_linearly_interpolated_and_knee_is_finite():
    frontier = interpolate_threshold_crossing(
        [10, 30, 90], [0.5, 0.1, -0.2], threshold=0.0
    )
    assert frontier == pytest.approx(50.0)
    first_loss = interpolate_threshold_crossing(
        [10, 30, 90], [0.5, -0.1, 0.2], threshold=0.0
    )
    assert first_loss == pytest.approx(26.6666667)
    knee = segmented_sse_breakpoint(
        [1, 3, 7, 14, 30, 60],
        [0.9, 0.86, 0.8, 0.72, 0.35, -0.2],
    )
    assert np.isfinite(knee["breakpoint_days"])
    assert knee["reason"] is None
    statistical = statistical_frontier(
        pd.DataFrame(
            {
                "gap_length": [1, 3, 7],
                "mean_skill": [0.9, 0.5, -0.5],
                "ci_lower": [0.4, -0.4, -0.8],
            }
        )
    )
    assert statistical["statistical_frontier_days"] == pytest.approx(2.0)
    assert "lower_confidence_bound" in statistical["frontier_definition"]

    invalid_application = application_frontier(
        pd.DataFrame(
            {
                "gap_length": [1, 3, 7],
                "MAE": [0.5, np.nan, 1.5],
            }
        ),
        {"MAE": ("<=", 1.0)},
    )
    assert np.isnan(invalid_application["application_frontier_days"])
    assert "non-finite application values" in invalid_application["reason"]


def test_frontier_uses_dense_fixed_window_first_loss_and_paired_bootstrap():
    rows = []
    for mask_seed in (101, 102, 103):
        for gap in DENSE_T_GAPS:
            if mask_seed == 103 and gap == DENSE_T_GAPS[-1]:
                continue
            rows.append(
                {
                    "scenario_id": f"dense-{gap}-{mask_seed}",
                    "experiment": "SCI_DENSE",
                    "mask_type": "block",
                    "layout": "single",
                    "window_length": 368,
                    "training_protocol": "seen_length",
                    "station_id": "S1",
                    "target": "T",
                    "model": "candidate",
                    "pattern": "T",
                    "gap_length": gap,
                    "mask_seed": mask_seed,
                    "training_seed": 11,
                    "skill": 0.5 if gap == 1 else -0.5,
                }
            )
    for mask_seed in (101, 102):
        rows.append(
            {
                **rows[0],
                "scenario_id": f"long-365-{mask_seed}",
                "window_length": 736,
                "gap_length": 365,
                "mask_seed": mask_seed,
                "skill": 0.2,
            }
        )
    rows.extend(
        [
            {**rows[0], "experiment": "M2", "skill": 99.0},
            {**rows[0], "mask_type": "multiblock", "skill": 99.0},
        ]
    )
    curves, frontiers = estimate_frontiers(pd.DataFrame(rows), n_boot=30, seed=4)
    main = frontiers.loc[frontiers["window_length"].eq(368)].iloc[0]
    assert main["statistical_frontier_days"] == pytest.approx(2.0)
    assert main["mean_frontier_days"] == pytest.approx(2.0)
    assert main["frontier_ci_lower"] == pytest.approx(2.0)
    assert main["frontier_ci_upper"] == pytest.approx(2.0)
    assert main["frontier_bootstrap_unit"] == "mask_seed+training_seed"
    assert main["n_frontier_paired_units"] == 2
    assert main["n_incomplete_frontier_units_excluded"] == 1
    assert bool(main["dense_grid_complete"])
    assert set(frontiers["window_length"]) == {368, 736}
    incomplete = frontiers.loc[frontiers["window_length"].eq(736)].iloc[0]
    assert not bool(incomplete["dense_grid_complete"])
    assert np.isnan(incomplete["statistical_frontier_days"])
    assert np.isnan(incomplete["mean_frontier_days"])
    assert np.isnan(incomplete["breakpoint_days"])
    assert curves.loc[curves["window_length"].eq(368), "mean_skill"].max() < 1.0

    right_censored = cluster_bootstrap_frontier_ci(
        pd.DataFrame(rows)
        .loc[
            lambda frame: (
                frame["experiment"].eq("SCI_DENSE")
                & frame["mask_type"].eq("block")
                & frame["window_length"].eq(368)
            )
        ]
        .assign(skill=0.5),
        n_boot=20,
        seed=7,
    )
    assert right_censored["n_boot_valid"] == 20
    assert right_censored["n_boot_right_censored"] == 20
    assert right_censored["frontier_ci_upper"] == pytest.approx(365.0)


def test_transfer_entropy_direction_and_permutation_are_reproducible():
    rng = np.random.default_rng(12)
    source = rng.normal(size=600)
    target = np.r_[0.0, source[:-1]] + rng.normal(scale=0.01, size=600)
    forward = transfer_entropy(
        source, target, lag=1, n_bins=4, n_permutations=49, seed=22
    )
    repeated = transfer_entropy(
        source, target, lag=1, n_bins=4, n_permutations=49, seed=22
    )
    reverse = transfer_entropy(
        target, source, lag=1, n_bins=4, n_permutations=49, seed=22
    )
    assert forward["transfer_entropy"] > reverse["transfer_entropy"]
    assert forward["p_value"] == repeated["p_value"]
    assert forward["null_mean"] == repeated["null_mean"]
    assert forward["discretization"] == "independent empirical quantiles"
    assert "permutation" in forward["permutation"]
    mutual = knn_mutual_information(source[:-1], target[1:], seed=4)
    assert mutual["mutual_information"] > 1.0


def test_transfer_entropy_lag_two_conditions_on_immediate_target_history():
    rng = np.random.default_rng(123)
    source = rng.normal(size=3000)
    target = np.zeros(3000, dtype=float)
    for index in range(2, len(target)):
        target[index] = (
            0.8 * target[index - 1] + source[index - 2] + rng.normal(scale=0.05)
        )
    lag_one = transfer_entropy(
        source, target, lag=1, n_bins=4, n_permutations=49, seed=5
    )
    lag_two = transfer_entropy(
        source, target, lag=2, n_bins=4, n_permutations=49, seed=5
    )
    repeated = transfer_entropy(
        source, target, lag=2, n_bins=4, n_permutations=49, seed=5
    )
    assert lag_two["transfer_entropy"] > 10 * lag_one["transfer_entropy"]
    assert lag_two["conditioning"] == "target(t-1)"
    assert lag_two["surrogate"] == "circular_shift"
    assert lag_two["p_value"] == repeated["p_value"]
    assert lag_two["null_mean"] == repeated["null_mean"]
    adjusted = benjamini_hochberg_fdr([0.01, 0.04, 0.03, np.nan])
    np.testing.assert_allclose(adjusted[:3], [0.03, 0.04, 0.04])
    assert np.isnan(adjusted[3])


def test_q05_q95_coverage_is_masked_and_grouped_by_gap():
    truth = np.arange(12, dtype=float)
    lower = truth - 1.0
    upper = truth + 1.0
    lower[8:10] = truth[8:10] + 1.0
    upper[8:10] = truth[8:10] + 2.0
    daily = pd.DataFrame(
        {
            "model": "probabilistic",
            "station_id": "S1",
            "target": "T",
            "gap_length": 30,
            "y_true": truth,
            "q05": lower,
            "q95": upper,
            "quality_approved": [True] * 10 + [False, False],
            "artificial_mask": True,
        }
    )
    result = interval_calibration_by_gap(daily)
    assert len(result) == 1
    assert result.loc[0, "n"] == 10
    assert result.loc[0, "empirical_coverage"] == pytest.approx(0.8)
    assert result.loc[0, "calibration_error"] == pytest.approx(-0.1)


def test_uncertainty_is_unit_first_and_does_not_mix_regimes():
    rows = []
    for experiment, mask_type in (("SCI_DENSE", "block"), ("M3", "multiblock")):
        for gap in (10, 30, 90):
            for training_seed in (11, 22):
                scenario = f"{experiment}-{gap}"
                for day in range(3):
                    truth = float(day)
                    rows.append(
                        {
                            "experiment": experiment,
                            "mask_type": mask_type,
                            "window_length": 368,
                            "training_protocol": "seen_length",
                            "scenario_id": scenario,
                            "training_seed": training_seed,
                            "mask_seed": 101,
                            "station_id": "S1",
                            "target": "T",
                            "model": "candidate",
                            "gap_length": gap,
                            "y_true": truth,
                            "q05": truth - gap / 10,
                            "q95": truth + gap / 10,
                            "quality_approved": True,
                            "artificial_mask": True,
                        }
                    )
    calibration = interval_calibration_by_gap(pd.DataFrame(rows))
    assert len(calibration) == 12
    assert calibration.groupby(["scenario_id", "training_seed"]).size().eq(1).all()
    growth = uncertainty_growth(calibration)
    overall = overall_calibration(calibration)
    assert len(growth) == 2
    assert len(overall) == 2
    assert set(growth["mask_type"]) == {"block", "multiblock"}
    assert growth["gap_width_spearman"].eq(1.0).all()

    network = pd.concat(
        [
            pd.DataFrame(rows).assign(
                experiment="SCI_NET",
                mask_type="matched_network",
                failed_station_ids=failed,
                failed_stations=failed,
                failure_count=count,
                network_size=3,
            )
            for failed, count in (("[]", 0), ('["S2"]', 1))
        ],
        ignore_index=True,
    )
    network_calibration = interval_calibration_by_gap(network)
    assert len(uncertainty_growth(network_calibration)) == 2
    assert len(overall_calibration(network_calibration)) == 2


def test_network_resilience_requires_complete_three_station_powersets():
    failure_sets = [
        [],
        ["S1"],
        ["S2"],
        ["S3"],
        ["S1", "S2"],
        ["S1", "S3"],
        ["S2", "S3"],
        ["S1", "S2", "S3"],
    ]
    rows = []
    for mask_seed, available in ((101, failure_sets), (102, failure_sets[:-1])):
        for failed in available:
            rows.append(
                {
                    "experiment": "SCI_NET",
                    "mask_type": "matched_network",
                    "layout": "single",
                    "window_length": 736,
                    "training_protocol": "seen_length",
                    "station_id": "S1",
                    "target": "T",
                    "target_gap_id": f"S1-T-30-{mask_seed}",
                    "model": "M",
                    "gap_length": 30,
                    "mask_seed": mask_seed,
                    "training_seed": 11,
                    "network_size": 3,
                    "failed_stations": failed,
                    "skill": 1.0 - len(failed) / 3,
                    "MAE": 1.0 + len(failed),
                }
            )
    events = pd.DataFrame(rows)
    complete, exclusions = complete_resilience_units(events)
    assert len(complete) == 8
    assert complete["mask_seed"].eq(101).all()
    assert len(exclusions) == 1
    assert exclusions.loc[0, "n_unique_failure_sets"] == 7

    curve = resilience_curve(events)
    auc = resilience_auc(curve)
    assert set(curve["failure_class"]) == {
        "none",
        "single",
        "double",
        "full_network",
    }
    assert auc.loc[0, "resilience_auc"] == pytest.approx(0.5)
    importance = node_importance(events)
    assert len(importance) == 3
    assert importance["impact"].eq(1.0).all()
    assert importance["target_station_id"].eq("S1").all()
    assert set(importance["failed_station_id"]) == {"S1", "S2", "S3"}
    assert importance["value_metric"].eq("MAE").all()
    assert importance["impact_definition"].eq("failed_minus_full").all()

    nonpositive = events.loc[events["mask_seed"].eq(101)].assign(skill=-1.0)
    unavailable = resilience_curve(nonpositive)
    assert unavailable["relative_skill"].isna().all()
    assert unavailable["reason"].eq("full-network skill is not positive").all()

    duplicated = pd.concat(
        [
            events.loc[events["mask_seed"].eq(101)],
            events.loc[events["mask_seed"].eq(101)].iloc[[0]],
        ],
        ignore_index=True,
    )
    duplicate_complete, duplicate_exclusions = complete_resilience_units(duplicated)
    assert duplicate_complete.empty
    assert "duplicate failure sets" in duplicate_exclusions.loc[0, "reason"]

    nonfinite_skill = events.loc[events["mask_seed"].eq(101)].copy()
    nonfinite_skill.loc[nonfinite_skill.index[1], "skill"] = np.nan
    with pytest.raises(ValueError, match="non-finite skill"):
        resilience_curve(nonfinite_skill)
    nonfinite_mae = events.loc[events["mask_seed"].eq(101)].copy()
    nonfinite_mae.loc[nonfinite_mae.index[1], "MAE"] = np.nan
    with pytest.raises(ValueError, match="non-finite MAE"):
        node_importance(nonfinite_mae)

    with pytest.raises(ValueError, match="only experiment='SCI_NET'"):
        resilience_curve(
            pd.concat([events, events.iloc[[0]].assign(experiment="M4")]),
        )


def test_mann_kendall_sen_and_trend_preservation():
    dates = pd.date_range("2000-01-01", periods=30, freq="D")
    truth = np.arange(30, dtype=float)
    prediction = truth + 5.0
    mk = mann_kendall_test(truth, times=dates)
    sen = sen_slope(truth, times=dates)
    preserved = trend_preservation(truth, prediction, dates=dates)
    assert mk["direction"] == "increasing"
    assert mk["p_value"] < 0.001
    assert sen["slope"] == pytest.approx(1.0)
    assert sen["method"] == "exact_all_pairs"
    assert preserved["trend_direction_match"]
    assert preserved["sen_slope_error"] == pytest.approx(0.0)


def test_scientific_trends_are_seed_specific_and_require_complete_reconstruction():
    rows = []
    for training_seed, complete in ((11, True), (22, False)):
        for day in range(10):
            artificial = day in {3, 4, 5} if complete else True
            rows.append(
                {
                    "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=day),
                    "scenario_id": "scenario",
                    "training_seed": training_seed,
                    "mask_seed": 101,
                    "station_id": "S1",
                    "target": "T",
                    "model": "candidate",
                    "y_true": float(day),
                    "y_pred": float(day) + 0.1,
                    "quality_approved": True,
                    "artificial_mask": artificial,
                    "test_period_complete": complete,
                    "high_threshold": 8.0 if training_seed == 11 else np.nan,
                }
            )
    result = scientific_metrics_by_event(pd.DataFrame(rows)).set_index("training_seed")
    assert set(result.index) == {11, 22}
    assert bool(result.loc[11, "long_term_trend_available"])
    assert result.loc[11, "true_sen_slope"] == pytest.approx(1.0)
    assert result.loc[11, "sequence_metric_reason"] is None
    assert np.isfinite(result.loc[11, "daily_change_mae"])
    assert result.loc[11, "high_threshold_source"] == "high_threshold"
    assert result.loc[11, "ecological_threshold_source"] is None
    assert result.loc[11, "ecological_threshold_reason"] == (
        "no predeclared ecological threshold"
    )
    assert not bool(result.loc[22, "long_term_trend_available"])
    assert np.isnan(result.loc[22, "true_mk_tau"])
    assert result.loc[22, "local_true_sen_slope"] == pytest.approx(1.0)
    assert "local slopes only" in result.loc[22, "trend_reason"]
    assert np.isnan(result.loc[22, "high_temp_mae"])
    assert "training-derived high_threshold" in result.loc[22, "threshold_reason"]
    assert np.isnan(result.loc[22, "heatwave_duration_error"])
    assert np.isnan(result.loc[22, "daily_change_mae"])
    assert (
        "complete test reconstruction unavailable"
        in result.loc[22, "sequence_metric_reason"]
    )


def test_analysis_script_rejects_unmanifested_result_tables(tmp_path):
    event_rows = []
    daily_rows = []
    for station in ("S1", "S2"):
        for gap, skill in ((10, 0.5), (30, 0.25), (60, -0.1), (90, -0.3)):
            for replicate in range(3):
                scenario = f"{station}-{gap}-{replicate}"
                for model, mae in (("climatology", 2.0), ("candidate", 1.0)):
                    event_rows.append(
                        {
                            "scenario_id": scenario,
                            "station_id": station,
                            "target": "T",
                            "model": model,
                            "training_seed": 11 if model == "candidate" else np.nan,
                            "gap_length": gap,
                            "pattern": "T",
                            "mask_seed": replicate,
                            "MAE": mae,
                            "skill": 0.0 if model == "climatology" else skill,
                            "experiment": "SCI_DENSE",
                            "mask_type": "block",
                            "layout": "single",
                            "window_length": 368,
                            "training_protocol": "seen_length",
                        }
                    )
                    for day in range(5):
                        truth = float(day + replicate)
                        daily_rows.append(
                            {
                                "date": pd.Timestamp("2020-01-01")
                                + pd.Timedelta(days=day),
                                "scenario_id": scenario,
                                "station_id": station,
                                "target": "T",
                                "model": model,
                                "mask_seed": replicate,
                                "gap_length": gap,
                                "y_true": truth,
                                "y_pred": truth
                                + (0.1 if model == "candidate" else 0.2),
                                "q05": truth - 1.0,
                                "q95": truth + 1.0,
                                "quality_approved": True,
                                "artificial_mask": True,
                                "experiment": "SCI_DENSE",
                                "mask_type": "block",
                                "window_length": 368,
                                "training_protocol": "seen_length",
                            }
                        )
    events_path = tmp_path / "events.csv"
    daily_path = tmp_path / "daily.csv"
    output_dir = tmp_path / "analysis"
    pd.DataFrame(event_rows).to_csv(events_path, index=False)
    pd.DataFrame(daily_rows).to_csv(daily_path, index=False)
    script = Path(__file__).parents[1] / "scripts/09_analyze_results.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--event-metrics",
            str(events_path),
            "--predictions",
            str(daily_path),
            "--top-manifest",
            str(tmp_path / "missing-top-manifest.json"),
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "missing-top-manifest.json" in completed.stderr
    assert not output_dir.exists()


def test_training_seed_coverage_rejects_fractional_or_missing_formal_seeds():
    script = Path(__file__).parents[1] / "scripts/09_analyze_results.py"
    coverage_function = runpy.run_path(str(script))["_formal_training_seed_coverage"]
    fractional = pd.DataFrame(
        {
            "scenario_id": ["s"] * 5,
            "experiment": ["M2"] * 5,
            "station_id": ["B1"] * 5,
            "target": ["T"] * 5,
            "model": ["proposed"] * 5,
            "training_seed": [11.9, 22.9, 33.9, 44.9, 55.9],
        }
    )
    fractional_coverage = coverage_function(fractional)
    assert not fractional_coverage["complete"]
    assert fractional_coverage["incomplete_groups"][0]["invalid_training_seeds"]

    missing = fractional.assign(training_seed=np.nan)
    missing_coverage = coverage_function(missing)
    assert not missing_coverage["complete"]
    assert missing_coverage["incomplete_groups"][0]["missing_training_seeds"] == [
        11,
        22,
        33,
        44,
        55,
    ]

    smoke = coverage_function(
        fractional.iloc[[0]].assign(training_seed=11), expected_seeds={11}
    )
    assert smoke["complete"]
