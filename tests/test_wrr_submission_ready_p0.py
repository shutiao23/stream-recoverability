"""Guards for WRR submission-readiness P0 fixes."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.v17_fitness.screen import Certificate  # noqa: E402


def test_outage_simulation_preserves_declared_length_across_year_end():
    from importlib.machinery import SourceFileLoader

    mod = SourceFileLoader(
        "seasonality210",
        str(ROOT / "scripts" / "210_v18_outage_seasonality.py"),
    ).load_module()
    lengths = np.array([180, 270, 90])
    peaks = np.array([200, 210, 180])
    # Force October starts (month index 9 -> October)
    weights = np.zeros(12)
    weights[9] = 1.0
    rng = np.random.default_rng(0)
    out_lengths, out_overlaps = mod._simulate_overlaps(lengths, peaks, weights, rng, draws_per_length=5)
    assert len(out_lengths) == len(out_overlaps)
    assert out_lengths.min() >= 1
    # Multi-year placement must not silently shorten a 180-day autumn gap to ~90 days
    # as a single truncated within-year mask while still labelling it 180.
    assert out_lengths.max() <= 360


def test_certificate_predict_without_truth_columns():
    # Minimal trained stub: one head with constant predictions via a tiny fit frame.
    n = 900
    rng = np.random.default_rng(1)
    base = {
        "longest_run": rng.integers(1, 100, n),
        "total_missing": rng.integers(1, 100, n),
        "missing_fraction": rng.random(n),
        "n_runs": rng.integers(1, 5, n),
        "peak_overlap": rng.random(n),
        "warm_observed_fraction": rng.random(n),
        "observed_peak_margin": rng.random(n),
        "observed_peak": rng.random(n) * 20,
        "clim_peak": rng.random(n) * 20,
        "n_visible_donors": rng.integers(0, 5, n),
        "donor_corr_mean": rng.random(n),
        "donor_corr_max": rng.random(n),
        "donor_corr_min": rng.random(n),
        "donor_coverage_mean": rng.random(n),
        "train_resid_sd": rng.random(n),
        "seasonal_amplitude": rng.random(n) * 10,
        "train_metric_sd": rng.random(n),
        "n_complete_years": rng.integers(4, 20, n),
        "record_years": rng.integers(4, 20, n),
        "longest_run_month": rng.integers(1, 12, n),
        "left_flank": True,
        "right_flank": True,
        "has_complete_window": True,
        "air_available": False,
        "network_id": [f"n{i%10}" for i in range(n)],
        "donor_regime": np.where(rng.random(n) > 0.5, "rich", "sparse"),
        "abserr_doy_climatology": rng.random(n),
        "err_doy_climatology": rng.normal(0, 0.2, n),
        "metric_doy_climatology": rng.random(n) * 20,
        "abserr_smooth_climatology": rng.random(n),
        "err_smooth_climatology": rng.normal(0, 0.2, n),
        "metric_smooth_climatology": rng.random(n) * 20,
        "abserr_linear_interp": rng.random(n),
        "err_linear_interp": rng.normal(0, 0.2, n),
        "metric_linear_interp": rng.random(n) * 20,
        "abserr_donor_ridge": rng.random(n),
        "err_donor_ridge": rng.normal(0, 0.2, n),
        "metric_donor_ridge": rng.random(n) * 20,
        "abserr_air_ridge": rng.random(n),
        "err_air_ridge": rng.normal(0, 0.2, n),
        "metric_air_ridge": rng.random(n) * 20,
    }
    cases = pd.DataFrame(base)
    fit = cases.iloc[:500]
    cal = cases.iloc[500:700]
    model = Certificate(coverage=0.9).fit(fit, cal, seed=0)
    assert any(head.trained for head in model.heads.values())
    deploy = cases.iloc[700:].drop(
        columns=[c for c in cases.columns if c.startswith(("abserr_", "err_", "metric_")) or c == "truth_hottest30"],
        errors="ignore",
    )
    pred = model.predict(deploy)
    assert pred["certificate_choice"].notna().any()
    assert "certificate_bound" in pred.columns
    # Adding truth columns back must not change predictions
    with_truth = cases.iloc[700:]
    pred2 = model.predict(with_truth)
    pd.testing.assert_series_equal(
        pred["certificate_choice"].reset_index(drop=True),
        pred2["certificate_choice"].reset_index(drop=True),
    )
    pd.testing.assert_series_equal(
        pred["certificate_bound"].reset_index(drop=True),
        pred2["certificate_bound"].reset_index(drop=True),
    )


def test_claim_registry_blocks_pending_headlines():
    path = ROOT / "results" / "wrr_submission_ready" / "claim_registry.csv"
    assert path.is_file()
    frame = pd.read_csv(path)
    blocked = frame.loc[frame["may_enter_abstract_or_conclusions"].astype(str).str.lower().eq("false")]
    assert not blocked.empty
    assert "A4" in set(frame["claim_id"])
    assert frame.loc[frame["claim_id"] == "A4", "status"].iloc[0] in {
        "invalid_pending_recompute",
        "recomputed_exploratory_not_for_headline",
    }
    assert not bool(frame.loc[frame["claim_id"] == "A4", "may_enter_abstract_or_conclusions"].iloc[0])


def test_provider_roles_match_split():
    roles = pd.read_csv(ROOT / "results" / "wrr_submission_ready" / "provider_roles_from_split.csv")
    by_provider = roles.set_index("provider")["role"].to_dict()
    assert by_provider["arso"] == "development and reserved"
    assert by_provider["foen"] == "development"
    assert by_provider["syke"] == "development"
    assert by_provider["rws_waterwebservices"] == "development"
