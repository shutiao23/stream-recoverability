"""Invariants of the v17 fitness-for-use programme.

The tests that matter here are the ones that protect the experiment's logic:
that no feature can see the truth, that the outage design produces the overlap
it claims, that the conformal calibration covers, and that the split is
stratified and deterministic.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.experiments.v17_fitness.ceiling import gate_decision
from stream_recoverability.experiments.v17_fitness.estimators import (
    hottest_window_mean,
    linear_interp_fill,
    observed_days_metric,
    usable_donors,
)
from stream_recoverability.experiments.v17_fitness.outages import (
    Realization,
    climatological_peak_window,
    peak_overlap_fraction,
    stratified_realization,
)
from stream_recoverability.experiments.v17_fitness.panel import declare_split
from stream_recoverability.experiments.v17_fitness.policies import gather, information_conditioned_choice
from stream_recoverability.experiments.v17_fitness.screen import (
    SCREEN_FEATURES,
    _conformal_quantile,
    feature_frame,
    supported,
)
from stream_recoverability.experiments.v17_fitness.stats import (
    cluster_bootstrap,
    resolvable_margin,
)


def _year_index(year: int = 2015) -> pd.DatetimeIndex:
    return pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")


def _seasonal_series(years=(2012, 2013, 2014, 2015), amplitude: float = 8.0) -> pd.Series:
    index = pd.date_range(f"{min(years)}-01-01", f"{max(years)}-12-31", freq="D")
    doy = index.dayofyear.to_numpy()
    values = 12.0 + amplitude * np.sin(2 * np.pi * (doy - 110) / 365.25)
    return pd.Series(values, index=index)


# --------------------------------------------------------------------------
# No feature may see the truth
# --------------------------------------------------------------------------


def test_screen_features_contain_no_truth_derived_quantity() -> None:
    """No feature may be computed from the evaluation year's hidden days.

    Outcome columns are named by prefix in the case table, so a leak shows up
    as a feature carrying one of those prefixes. ``train_metric_sd`` is the
    interannual spread of the peak over the station's *other* complete years
    and is in the archive at decision time, so it is allowed by name; the
    behavioural test below is what actually pins it down.
    """

    forbidden_prefixes = ("truth_", "abserr_", "err_", "metric_", "exceed_")
    for name in SCREEN_FEATURES:
        assert not name.startswith(forbidden_prefixes), name
        assert "true_peak" not in name, name


def test_feature_frame_ignores_truth_columns_even_when_present() -> None:
    cases = pd.DataFrame(
        {
            "longest_run": [30, 90],
            "total_missing": [30, 90],
            "missing_fraction": [0.08, 0.25],
            "n_runs": [1, 1],
            "peak_overlap": [0.0, 1.0],
            "warm_observed_fraction": [1.0, 0.3],
            "observed_peak_margin": [0.2, -1.0],
            "observed_peak": [20.0, 18.0],
            "clim_peak": [19.8, 19.0],
            "n_visible_donors": [2, 0],
            "donor_corr_mean": [0.8, np.nan],
            "donor_corr_max": [0.9, np.nan],
            "donor_corr_min": [0.7, np.nan],
            "donor_coverage_mean": [1.0, np.nan],
            "train_resid_sd": [0.5, 0.6],
            "seasonal_amplitude": [16.0, 15.0],
            "train_metric_sd": [0.9, 1.1],
            "n_complete_years": [8, 8],
            "record_years": [12, 12],
            "longest_run_month": [1, 7],
            "left_flank": [True, True],
            "right_flank": [True, False],
            "has_complete_window": [True, False],
            "air_available": [False, False],
            "truth_metric": [21.0, 22.0],
            "abserr_policy": [0.1, 2.0],
        }
    )
    frame = feature_frame(cases)
    assert list(frame.columns) == list(SCREEN_FEATURES)
    assert "truth_metric" not in frame.columns
    assert "abserr_policy" not in frame.columns


# --------------------------------------------------------------------------
# The outage design produces the overlap it claims
# --------------------------------------------------------------------------


def test_climatological_peak_window_excludes_the_evaluation_year() -> None:
    series = _seasonal_series()
    spoiled = series.copy()
    spoiled.loc[spoiled.index.year == 2015] = 99.0
    window = climatological_peak_window(spoiled, exclude_year=2015)
    peak_doy = int(np.argmax(np.bincount(window)))
    assert 150 <= peak_doy <= 240, peak_doy


def test_stratified_realization_respects_its_overlap_class() -> None:
    index = _year_index()
    peak = climatological_peak_window(_seasonal_series(), exclude_year=2015)
    rng = np.random.default_rng(0)
    for overlap_class, low, high in [("none", 0.0, 0.0), ("full", 0.999, 1.0)]:
        item = stratified_realization(
            index, peak, length=60, overlap_class=overlap_class, rng=rng, realization_id="t"
        )
        assert item is not None
        fraction = peak_overlap_fraction(index, item.mask(len(index)), peak)
        assert low <= fraction <= high, (overlap_class, fraction)


def test_realization_mask_matches_its_runs() -> None:
    item = Realization(realization_id="r", arm="test", runs=((10, 5), (100, 3)), n_runs=2, total_missing=8, longest_run=5)
    mask = item.mask(365)
    assert int(mask.sum()) == 8
    assert mask[10:15].all() and mask[100:103].all()


# --------------------------------------------------------------------------
# Estimators
# --------------------------------------------------------------------------


def test_observed_days_estimator_degrades_when_the_peak_is_hidden() -> None:
    series = _seasonal_series(years=(2015,))
    values = series.to_numpy(dtype=float)
    truth = hottest_window_mean(values)
    hidden = values.copy()
    peak_end = int(np.nanargmax(pd.Series(values).rolling(30, min_periods=30).mean().to_numpy()))
    hidden[max(0, peak_end - 45) : peak_end + 15] = np.nan
    assert observed_days_metric(hidden) < truth - 1.0


def test_linear_interpolation_only_fills_interior_gaps() -> None:
    values = np.array([1.0, np.nan, 3.0, np.nan])
    filled = linear_interp_fill(values)
    assert filled[1] == pytest.approx(2.0)
    assert np.isnan(filled[3])


def test_usable_donors_requires_coverage_during_the_outage() -> None:
    index = _year_index()
    donors = pd.DataFrame({"a": np.ones(len(index)), "b": np.ones(len(index))}, index=index)
    donors.loc[donors.index[10:40], "b"] = np.nan
    mask = np.zeros(len(index), dtype=bool)
    mask[10:40] = True
    assert usable_donors(donors, index, mask) == ("a",)


# --------------------------------------------------------------------------
# Policy bookkeeping
# --------------------------------------------------------------------------


def test_information_conditioned_choice_prefers_donors_then_air_then_interpolation() -> None:
    cases = pd.DataFrame(
        {
            "longest_run": [10, 10, 10, 200],
            "left_flank": [True, True, True, True],
            "right_flank": [True, True, True, True],
            "n_visible_donors": [3, 0, 0, 0],
            "air_available": [False, True, False, False],
            "abserr_donor_ridge": [0.1, np.nan, np.nan, np.nan],
            "abserr_air_ridge": [np.nan, 0.2, np.nan, np.nan],
            "abserr_linear_interp": [0.3, 0.3, 0.3, 0.3],
            "abserr_smooth_climatology": [0.4, 0.4, 0.4, 0.4],
        }
    )
    choice = information_conditioned_choice(cases)
    assert list(choice) == ["donor_ridge", "air_ridge", "linear_interp", "smooth_climatology"]


def test_gather_selects_the_named_column_per_row() -> None:
    cases = pd.DataFrame({"abserr_a": [1.0, 2.0], "abserr_b": [10.0, 20.0]})
    picked = gather(cases, pd.Series(["a", "b"], index=cases.index))
    assert list(picked) == [1.0, 20.0]


def test_support_is_method_specific() -> None:
    cases = pd.DataFrame(
        {
            "n_visible_donors": [0, 2],
            "air_available": [False, True],
            "left_flank": [True, False],
            "right_flank": [True, True],
        }
    )
    assert list(supported(cases, "donor_ridge")) == [False, True]
    assert list(supported(cases, "air_ridge")) == [False, True]
    assert list(supported(cases, "linear_interp")) == [True, False]
    assert list(supported(cases, "doy_climatology")) == [True, True]


# --------------------------------------------------------------------------
# Calibration and inference
# --------------------------------------------------------------------------


def test_conformal_quantile_reaches_nominal_coverage_on_exchangeable_scores() -> None:
    rng = np.random.default_rng(3)
    calibration = rng.normal(size=4000)
    test = rng.normal(size=20000)
    threshold = _conformal_quantile(calibration, 0.90)
    assert 0.88 <= float((test <= threshold).mean()) <= 0.92


def test_cluster_bootstrap_resamples_whole_networks() -> None:
    frame = pd.DataFrame(
        {"network_id": ["a"] * 50 + ["b"] * 50, "value": np.r_[np.zeros(50), np.ones(50)]}
    )
    stat = cluster_bootstrap(frame, lambda f: float(f["value"].mean()), draws=500, seed=1)
    assert stat["point"] == pytest.approx(0.5)
    # With two clusters the resampled mean can only be 0, 0.5 or 1.
    assert stat["low"] <= 0.0 and stat["high"] >= 1.0


def test_resolvable_margin_shrinks_with_more_clusters() -> None:
    assert resolvable_margin(0.04, 36) < resolvable_margin(0.04, 9)


def test_gate_rejects_an_action_space_smaller_than_its_own_resolution() -> None:
    mean_table = pd.DataFrame(
        {
            "action_space": [
                "deployed information-conditioned policy",
                "oracle adopt/reject of that policy",
                "oracle choice among reconstruction methods",
            ],
            "headroom_over_deployed_c": [0.0, 0.01, 0.02],
        }
    )
    retention_table = pd.DataFrame({"retention": [0.7], "headroom_rate_points": [20.0]})
    resolution = pd.DataFrame(
        {
            "endpoint": ["mean benefit B_q", "absolute metric error", "indicator error > 0.5 C"],
            "resolvable_margin_reserved": [0.05, 0.04, 0.02],
        }
    )
    gate = gate_decision(mean_table, retention_table, resolution)
    assert gate["adopt_reject"]["passes"] is False
    assert gate["method_selection"]["passes"] is False
    assert gate["retain_exclude"]["passes"] is True


# --------------------------------------------------------------------------
# The split
# --------------------------------------------------------------------------


def test_declare_split_is_deterministic_and_stratified() -> None:
    strata = pd.DataFrame(
        {
            "network_id": [f"n{i}" for i in range(20)],
            "provider": ["p"] * 10 + ["q"] * 10,
            "donor_regime": (["rich"] * 5 + ["none"] * 5) * 2,
        }
    )
    strata["stratum"] = strata["provider"] + "|" + strata["donor_regime"]
    first = declare_split(strata.copy())
    second = declare_split(strata.copy())
    pd.testing.assert_frame_equal(first, second)
    counts = first.groupby(["stratum", "split_role"]).size().unstack(fill_value=0)
    assert (counts["reserved"] == 1).all()
    assert (counts["development"] == 4).all()


# --------------------------------------------------------------------------
# Reproducibility of the case table
# --------------------------------------------------------------------------


def test_stable_seed_is_process_independent() -> None:
    """Python's hash() is salted per process; seeding with it silently breaks reruns.

    This value was computed in a different interpreter session. If it ever
    changes, the outage realizations in the case table stop being reproducible
    and every artifact downstream of them becomes unverifiable.
    """

    from stream_recoverability.experiments.v17_fitness.paths import stable_seed

    assert stable_seed("arso_drava", "2005", 2015) == 669662013
    assert stable_seed("a", "b") != stable_seed("b", "a")


def test_case_and_mechanism_builders_do_not_seed_from_builtin_hash() -> None:
    import inspect

    from stream_recoverability.experiments.v17_fitness import cases, mechanism

    for module in (cases, mechanism):
        source = inspect.getsource(module)
        assert "default_rng(abs(hash(" not in source, module.__name__
        assert "stable_seed(" in source, module.__name__


def test_manuscript_headline_numbers_match_the_artifacts() -> None:
    """The prose carries a machine-readable block; it must equal the artifacts.

    A self-audit found a case count hardcoded in a figure caption that a rerun
    had silently invalidated. This closes that class of defect: if a number in
    the manuscript drifts from `results/v17_fitness/paper_numbers.json`, the
    test fails rather than the reader finding it.
    """

    import json
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    manuscript = root / "paper_archived" / "v17" / "manuscript.md"
    numbers_path = root / "results" / "v17_fitness" / "paper_numbers.json"
    if not manuscript.exists() or not numbers_path.exists():
        pytest.skip("v17 artifacts not built in this checkout")

    text = manuscript.read_text(encoding="utf-8")
    match = re.search(r"<!-- numbers:start -->\s*```json\s*(\{.*?\})\s*```", text, re.S)
    assert match, "manuscript is missing its machine-readable numbers block"
    quoted = json.loads(match.group(1))
    actual = json.loads(numbers_path.read_text(encoding="utf-8"))

    assert quoted["networks"] == actual["panel"]["networks"]
    assert quoted["station_years"] == actual["panel"]["station_years"]
    assert quoted["cases"] == actual["cases"]["total"]
    assert quoted["development_cases"] == actual["cases"]["development"]
    assert quoted["reserved_cases"] == actual["cases"]["reserved"]
    assert quoted["reserved_networks"] == actual["panel"]["reserved_networks"]
    for key, path in [
        ("certificate_at_70_reserved", ("frontier_at_70", "reserved", "certificate")),
        ("length_rule_at_70_reserved", ("frontier_at_70", "reserved", "length_rule")),
    ]:
        value = actual
        for step in path:
            value = value[step]
        assert abs(quoted[key] - float(value)) < 5e-4, key
    assert abs(quoted["confirmation_contrast_points"] - actual["confirmation"]["primary"]["contrast_points"]) < 5e-3
    assert abs(quoted["marginal_coverage"] - actual["confirmation"]["coverage"]["marginal"]) < 5e-4


def test_case_table_row_order_is_deterministic() -> None:
    """Content-identical is not enough; positional assignment needs stable order.

    Workers return in completion order, so an unsorted concatenation varies
    between runs. Anything downstream that assigns by position — the jitter
    that breaks ties in a discrete screening rule — would then move with it.
    """

    from pathlib import Path

    import pandas as pd

    path = Path(__file__).resolve().parents[1] / "results" / "v17_fitness" / "step3_cases" / "cases.parquet"
    if not path.exists():
        pytest.skip("v17 case table not built in this checkout")
    frame = pd.read_parquet(path, columns=["network_id", "station_id", "year", "arm", "realization_id"])
    key = ["network_id", "station_id", "year", "arm", "realization_id"]
    expected = frame.sort_values(key, kind="mergesort").reset_index(drop=True)
    pd.testing.assert_frame_equal(frame, expected)


def test_metric_dichotomy_holds_and_is_stable_across_tolerances() -> None:
    """The narrowed central claim: timing wins for warm extremes, length for averages.

    This is the claim the title rests on after the third review, so it is
    pinned rather than left to prose. If a change to the case table or the
    estimator set flips one of these, the title is wrong and the test says so.
    """

    from pathlib import Path

    import pandas as pd

    path = (
        Path(__file__).resolve().parents[1]
        / "results"
        / "v17_fitness"
        / "step17_metric_generality"
        / "tolerance_sweep.csv"
    )
    if not path.exists():
        pytest.skip("v17 metric-generality artifacts not built in this checkout")
    sweep = pd.read_csv(path)
    expected = {
        "hottest30": "timing",
        "amplitude30": "timing",
        "annual_mean": "length",
        "coldest30": "length",
    }
    for metric, axis in expected.items():
        block = sweep.loc[sweep["metric"].eq(metric)]
        assert not block.empty, metric
        assert set(block["winning_axis"]) == {axis}, (metric, sorted(set(block["winning_axis"])))
        assert len(block) >= 3, f"{metric} was not swept over several tolerances"

    # Hiding the warm peak must not help predict the cold extreme.
    cold = sweep.loc[sweep["metric"].eq("coldest30"), "auc_peak_overlap"]
    assert (cold < 0.55).all(), float(cold.max())


def test_manuscript_tables_match_their_artifacts() -> None:
    """Every table cell and audited inline claim must equal the artifact it quotes.

    The machine-readable block covers ten headline numbers; the prose carries
    about a hundred and seventy more. A proofread found four wrong ones that a
    table check could not see, so the audit runs here instead.
    """

    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "199_v17_audit_manuscript.py"
    if not (root / "results" / "v17_fitness" / "step17_metric_generality").exists():
        pytest.skip("v17 artifacts not built in this checkout")
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, cwd=str(root), check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "every table cell in the manuscript matches its artifact" in result.stdout


# --------------------------------------------------------------------------
# Endpoint definitions and basin attributes
# --------------------------------------------------------------------------


def test_seven_day_peak_is_never_below_the_thirty_day_peak() -> None:
    """A shorter window can only find a hotter mean. This is arithmetic.

    It is worth a test because the two endpoints are computed by separate calls
    and a transposed window argument would produce plausible-looking numbers
    that silently invert the paper's regulatory-window comparison.
    """

    from pathlib import Path

    import pandas as pd

    path = Path(__file__).resolve().parents[1] / "results" / "v17_fitness" / "step3_cases" / "cases.parquet"
    if not path.exists():
        pytest.skip("v17 case table not built in this checkout")
    frame = pd.read_parquet(path, columns=["truth_hottest7", "truth_hottest30"])
    violations = (frame["truth_hottest7"] < frame["truth_hottest30"] - 1e-9).sum()
    assert violations == 0, f"{violations} station-years have a 7-day peak below their 30-day peak"


def test_sensor_noise_is_within_the_instrument_range_it_claims() -> None:
    from stream_recoverability.experiments.v17_fitness.paths import SENSOR_NOISE_C

    assert 0.05 <= SENSOR_NOISE_C <= 0.25


def test_basin_attributes_declare_an_expected_sign_for_every_tested_predictor() -> None:
    """A hypothesis with no declared direction cannot be falsified."""

    from stream_recoverability.experiments.v17_fitness.basins import EXPECTED_SIGNS

    for name in ("BFI_AVE", "CONTACT", "STOR_NID_2009", "DRAIN_SQKM"):
        assert name in EXPECTED_SIGNS
        assert EXPECTED_SIGNS[name].split(":")[0] in {"positive", "negative", "none declared"}


def test_gages_join_covers_a_usable_share_of_the_united_states_panel() -> None:
    from pathlib import Path

    import pandas as pd

    from stream_recoverability.experiments.v17_fitness.basins import match_stations

    root = Path(__file__).resolve().parents[1]
    roster_path = root / "results" / "v17_fitness" / "step1_panel" / "station_roster.csv"
    archive = root / "data" / "cache" / "regulation_panel_v1" / "basinchar_and_report_sept_2011.zip"
    if not roster_path.exists() or not archive.exists():
        pytest.skip("panel or GAGES-II archive not present in this checkout")
    roster = pd.read_csv(roster_path, dtype={"station_id": str})
    roster = roster.loc[roster["eligible_station"]]
    matched = match_stations(roster)
    usgs = int((roster["provider"] == "usgs").sum())
    assert len(matched) >= 0.6 * usgs, f"only {len(matched)} of {usgs} US stations matched"
    assert matched["BFI_AVE"].notna().all()
