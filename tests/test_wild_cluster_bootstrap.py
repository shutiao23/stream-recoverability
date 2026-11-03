"""Tests for the score-bootstrap sensitivity intervals (B6)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/ems_revision_20261102/wild_cluster_bootstrap.csv"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "wild_cluster_986_test", ROOT / "scripts/986_wild_cluster_bootstrap.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_clusters(seed: int, shift: float):
    rng = np.random.default_rng(seed)
    labels = np.repeat(np.arange(17), 48)
    base = rng.normal(0.20, 0.05, size=labels.size) ** 2
    other = base + shift + rng.normal(0.0, 0.02, size=labels.size)
    return other, base, labels


def test_influence_function_is_exactly_centered():
    """Regression test for the missing-centering bug found by the 2026-11-03 audit."""
    module = load_module()
    mse_a, mse_b, labels = synthetic_clusters(11, shift=0.05)
    root_a = float(np.sqrt(mse_a.mean()))
    root_b = float(np.sqrt(mse_b.mean()))
    influence = (mse_a - mse_a.mean()) / (2 * root_a) - (mse_b - mse_b.mean()) / (2 * root_b)
    assert abs(float(influence.mean())) < 1e-12
    result = module.wild_influence_interval(mse_a, mse_b, labels, seed=20261102, draws=4000)
    assert result["estimate"] > 0
    assert result["ci_low"] > 0
    assert result["groups"] == 17


def test_shifted_interval_excludes_zero_and_null_interval_covers_zero():
    module = load_module()
    mse_a, mse_b, labels = synthetic_clusters(12, shift=0.0)
    null = module.wild_influence_interval(mse_a, mse_b, labels, seed=20261102, draws=4000)
    assert null["ci_low"] <= 0 <= null["ci_high"]
    mse_a, mse_b, labels = synthetic_clusters(13, shift=0.05)
    shifted = module.wild_influence_interval(mse_a, mse_b, labels, seed=20261102, draws=4000)
    assert shifted["ci_low"] > 0


def test_influence_interval_simulation_coverage_is_close_to_nominal():
    """Coverage of the data-generating RMSE difference, not of the sample estimate."""
    module = load_module()
    shift = 0.01
    population = float(np.sqrt(0.0425 + shift) - np.sqrt(0.0425))
    covered = 0
    trials = 600
    for trial in range(trials):
        mse_a, mse_b, labels = synthetic_clusters(1000 + trial, shift=shift)
        result = module.wild_influence_interval(mse_a, mse_b, labels, seed=7, draws=400)
        covered += int(result["ci_low"] <= population <= result["ci_high"])
    coverage = covered / trials
    assert 0.90 <= coverage <= 0.99, coverage


def test_interval_width_matches_cluster_robust_sandwich_scale():
    """Centered score intervals must not be systematically wider than the sandwich SE."""
    module = load_module()
    ratios = []
    for trial in range(200):
        mse_a, mse_b, labels = synthetic_clusters(3000 + trial, shift=0.01)
        result = module.wild_influence_interval(mse_a, mse_b, labels, seed=7, draws=2000)
        root_a = float(np.sqrt(mse_a.mean()))
        root_b = float(np.sqrt(mse_b.mean()))
        influence = (mse_a - mse_a.mean()) / (2 * root_a) - (mse_b - mse_b.mean()) / (2 * root_b)
        groups = sorted(set(labels))
        means = np.array([influence[labels == g].mean() for g in groups])
        counts = np.array([(labels == g).sum() for g in groups], float)
        sandwich = float(np.sqrt(np.sum((counts / counts.sum()) ** 2 * (means - means.mean()) ** 2)))
        ratios.append((result["ci_high"] - result["ci_low"]) / (2 * 1.959964 * sandwich))
    median_ratio = float(np.median(ratios))
    assert 0.7 <= median_ratio <= 1.3, median_ratio


def test_webb_weights_available_and_misuse_rejected():
    module = load_module()
    mse_a, mse_b, labels = synthetic_clusters(13, shift=0.02)
    webb = module.wild_influence_interval(mse_a, mse_b, labels, weights="webb", draws=2000)
    assert np.isfinite(webb["ci_low"]) and np.isfinite(webb["ci_high"])
    with pytest.raises(ValueError):
        module.wild_influence_interval(mse_a, mse_b, labels, weights="unknown")
    with pytest.raises(ValueError):
        module.wild_influence_interval(mse_a[:-1], mse_b, labels)


def test_saved_table_reproduces_frozen_directions():
    frame = pd.read_csv(OUT)
    assert len(frame) == 10
    calendar_cdf = frame.loc[
        frame.family.eq("calendar") & frame.contrast.eq("cdf_all_years minus warm90")
    ].iloc[0]
    assert np.isclose(calendar_cdf.estimate, -0.0151656, atol=1e-6)
    assert calendar_cdf.wild_rademacher_ci_low < 0 < calendar_cdf.wild_rademacher_ci_high
    assert calendar_cdf.wild_webb_ci_low < 0 < calendar_cdf.wild_webb_ci_high
    calendar_sxx = frame.loc[
        frame.family.eq("calendar") & frame.contrast.eq("sxx_all_years minus warm90")
    ].iloc[0]
    assert calendar_sxx.wild_rademacher_ci_high < 0
    crossed_all = frame.loc[
        frame.family.eq("crossed") & frame.contrast.eq("all minus warm90")
    ].iloc[0]
    assert np.isclose(crossed_all.wild_rademacher_ci_low, -0.353, atol=5e-4)
    assert np.isclose(crossed_all.wild_rademacher_ci_high, -0.200, atol=5e-4)
    assert crossed_all.wild_rademacher_ci_high < 0
    report = json.loads((ROOT / "results/ems_revision_20261102/wild_cluster_bootstrap.json").read_text())
    assert report["rows"] == 10
    assert report["clusters"] == 17
    assert np.isclose(report["median_width_ratio_wild_over_group"], 0.878, atol=5e-4)
    directions = report["retention_directions"]
    assert directions["calendar/cdf_all_years minus warm90"]["wild_rademacher_excludes_zero"] is False
    assert directions["calendar/uniform_exact minus warm90"]["wild_rademacher_excludes_zero"] is True
    assert directions["calendar/uniform_exact minus warm90"]["group_boot_excludes_zero"] is False
