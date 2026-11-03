"""Tests for the wild cluster bootstrap intervals (B6)."""
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


def test_wild_interval_recovers_a_large_shift():
    module = load_module()
    mse_a, mse_b, labels = synthetic_clusters(11, shift=0.05)
    result = module.wild_influence_interval(mse_a, mse_b, labels, seed=20261102, draws=4000)
    assert result["estimate"] > 0
    assert result["ci_low"] > 0
    assert result["groups"] == 17


def test_wild_interval_covers_zero_under_the_null():
    module = load_module()
    mse_a, mse_b, labels = synthetic_clusters(12, shift=0.0)
    result = module.wild_influence_interval(mse_a, mse_b, labels, seed=20261102, draws=4000)
    assert result["ci_low"] <= 0 <= result["ci_high"]


def test_influence_interval_simulation_coverage():
    module = load_module()
    covered = 0
    trials = 300
    truth = 0.0
    for trial in range(trials):
        mse_a, mse_b, labels = synthetic_clusters(1000 + trial, shift=0.01)
        truth = np.sqrt(mse_a.mean()) - np.sqrt(mse_b.mean())
        result = module.wild_influence_interval(mse_a, mse_b, labels, seed=7, draws=400)
        covered += int(result["ci_low"] <= truth <= result["ci_high"])
    coverage = covered / trials
    assert 0.88 <= coverage <= 1.0, coverage


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
    calendar_sxx = frame.loc[
        frame.family.eq("calendar") & frame.contrast.eq("sxx_all_years minus warm90")
    ].iloc[0]
    assert calendar_sxx.wild_rademacher_ci_high < 0
    crossed_all = frame.loc[
        frame.family.eq("crossed") & frame.contrast.eq("all minus warm90")
    ].iloc[0]
    assert crossed_all.wild_rademacher_ci_high < 0
    report = json.loads((ROOT / "results/ems_revision_20261102/wild_cluster_bootstrap.json").read_text())
    assert report["rows"] == 10
    assert report["clusters"] == 17
    assert report["retention_directions"]["calendar/cdf_all_years minus warm90"][
        "wild_rademacher_excludes_zero"
    ] is False
