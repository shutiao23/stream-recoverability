"""Tests for the corrected Hamed-Rao modified Mann-Kendall implementation."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "docs/reviews/ems_dual_review_20261102/slope_signal_audit.py"
RESULTS = ROOT / "results/ems_revision_20261102/trend_signal.json"


def load_module():
    spec = importlib.util.spec_from_file_location("slope_signal_audit_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_white_noise_correction_is_trivial():
    module = load_module()
    rng = np.random.default_rng(11)
    y = rng.normal(size=14) + np.linspace(0, 0.8, 14) * 0.4
    n_star, p_hr = module.hamed_rao_p(y)
    _, _, _, p_mk = module.mann_kendall(y)
    # No significant rank autocorrelation: the correction is exactly 1.
    assert np.isclose(n_star, 14.0)
    assert np.isclose(p_hr, p_mk)


def test_persistent_series_never_becomes_more_significant():
    module = load_module()
    # Alternating plateaus produce strong positive rank autocorrelation at lag 1.
    y = np.repeat(np.array([0.0, 1.0, 2.0, 3.0, 2.6, 3.4, 4.0]), 2)[:14] + np.linspace(0, 1, 14) * 0.3
    n_star, p_hr = module.hamed_rao_p(y)
    _, _, _, p_mk = module.mann_kendall(y)
    if np.isfinite(p_hr) and np.isfinite(p_mk):
        assert p_hr >= p_mk - 1e-12


def test_matches_pymannkendall_on_all_saved_stations():
    pytest.importorskip("pymannkendall")
    import pandas as pd
    import pymannkendall as mk

    module = load_module()
    truths = pd.read_csv(ROOT / "results/wrr_final_revision_20261031/reference_truths.csv")
    truths = truths.loc[truths.family.eq("crossed")]
    year_sets = pd.read_csv(ROOT / "results/wrr_final_revision_20261031/reference_year_sets.csv")
    stations = module.station_slopes(truths, year_sets)
    reference = year_sets.set_index("station_key")
    for station, row in stations.iterrows():
        frame = truths.loc[truths.station_key.eq(station)].sort_values("year")
        years = {int(value) for value in str(reference.loc[station, "reference_years"]).split(";")}
        h30 = frame.loc[frame.year.isin(years), "eval_truth_h30"].to_numpy(float)
        try:
            expected = float(mk.hamed_rao_modification_test(h30).p)
        except (ValueError, ZeroDivisionError):
            expected = float("nan")
        mine = float(row["hamed_rao_p"])
        if np.isnan(expected):
            assert np.isnan(mine), station
        else:
            assert np.isclose(expected, mine, atol=1e-9, rtol=0), station


def test_saved_summary_counts_are_consistent():
    payload = json.loads(RESULTS.read_text())
    summary = payload["stations"]["summary"]
    rows = payload["stations"]["rows"]
    assert summary["n"] == 41
    finite = [row["hamed_rao_p"] for row in rows if row["hamed_rao_p"] is not None]
    assert sum(1 for value in finite if value < 0.05) == summary["hamed_rao_p_below_005"]
    assert summary["hamed_rao_p_below_005"] == 6
    assert summary["ols_p_below_005"] == 3
    assert summary["mann_kendall_p_below_005"] == 4
