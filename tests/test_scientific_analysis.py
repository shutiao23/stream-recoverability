import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.analysis.compensation import (
    compensation_gains,
    exact_shapley,
    information_combinations,
    knn_mutual_information,
    transfer_entropy,
)
from stream_recoverability.analysis.frontiers import (
    interpolate_threshold_crossing,
    segmented_sse_breakpoint,
)
from stream_recoverability.analysis.resilience import (
    resilience_auc,
    resilience_curve,
)
from stream_recoverability.analysis.science_metrics import (
    mann_kendall_test,
    sen_slope,
    trend_preservation,
)
from stream_recoverability.analysis.statistics import (
    holm_correction,
    paired_bootstrap_ci,
    paired_wilcoxon,
)
from stream_recoverability.analysis.uncertainty import interval_calibration_by_gap


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
            "combination": ["S0" if not subset else "S0+" + "+".join(sorted(subset)) for subset in values],
            "value": list(values.values()),
            "raw_metric": list(values.values()),
            "higher_is_better": True,
        }
    )
    gains = compensation_gains(value_table).set_index("source")
    for source, weight in weights.items():
        assert gains.loc[source, "mean_marginal_gain"] == pytest.approx(weight)


def test_paired_bootstrap_and_test_use_shared_event_units():
    rows = []
    for event in range(20):
        rows.extend(
            [
                {"scenario_id": f"E{event}", "station_id": "S1", "target": "T", "model": "A", "MAE": event / 10 + 1.0},
                {"scenario_id": f"E{event}", "station_id": "S1", "target": "T", "model": "B", "MAE": event / 10},
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


def test_frontier_crossing_is_linearly_interpolated_and_knee_is_finite():
    frontier = interpolate_threshold_crossing(
        [10, 30, 90], [0.5, 0.1, -0.2], threshold=0.0
    )
    assert frontier == pytest.approx(50.0)
    knee = segmented_sse_breakpoint(
        [1, 3, 7, 14, 30, 60],
        [0.9, 0.86, 0.8, 0.72, 0.35, -0.2],
    )
    assert np.isfinite(knee["breakpoint_days"])
    assert knee["reason"] is None


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


def test_network_resilience_auc_uses_single_double_and_full_failures():
    events = pd.DataFrame(
        {
            "model": "M",
            "target": "T",
            "gap_length": 30,
            "failed_stations": [[], ["S1"], ["S2"], ["S1", "S2"]],
            "skill": [1.0, 0.5, 0.5, 0.0],
        }
    )
    curve = resilience_curve(events, total_sites=2)
    auc = resilience_auc(curve)
    assert set(curve["failure_class"]) == {"none", "single", "full_network"}
    assert auc.loc[0, "resilience_auc"] == pytest.approx(0.5)


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


def test_analysis_script_writes_csv_and_json_with_optional_skips(tmp_path):
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
                            "gap_length": gap,
                            "pattern": "T",
                            "mask_seed": replicate,
                            "MAE": mae,
                            "skill": 0.0 if model == "climatology" else skill,
                        }
                    )
                    for day in range(5):
                        truth = float(day + replicate)
                        daily_rows.append(
                            {
                                "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=day),
                                "scenario_id": scenario,
                                "station_id": station,
                                "target": "T",
                                "model": model,
                                "mask_seed": replicate,
                                "gap_length": gap,
                                "y_true": truth,
                                "y_pred": truth + (0.1 if model == "candidate" else 0.2),
                                "q05": truth - 1.0,
                                "q95": truth + 1.0,
                                "quality_approved": True,
                                "artificial_mask": True,
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
            "--daily-predictions",
            str(daily_path),
            "--output-dir",
            str(output_dir),
            "--bootstrap",
            "30",
            "--seed",
            "9",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    summary = json.loads((output_dir / "analysis_summary.json").read_text())
    assert summary["analyses"]["paired_comparisons"]["status"] == "ok"
    assert summary["analyses"]["information_compensation"]["status"] == "skipped"
    assert (output_dir / "recoverability_frontiers.csv").exists()
    assert (output_dir / "uncertainty_by_gap.csv").exists()
    assert (output_dir / "scientific_metrics.csv").exists()
