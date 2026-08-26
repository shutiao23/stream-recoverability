from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.experiments.natural_outage_scoring import (
    natural_outage_summary,
    observed_gap_starts,
    score_natural_outages,
    score_planted_gap,
)


def _toy_wide(*, n_years: int = 6, n_stations: int = 4, seed: int = 0) -> pd.DataFrame:
    dates = pd.date_range("2000-01-01", periods=365 * n_years, freq="D")
    rng = np.random.default_rng(seed)
    seasonal = 8.0 * np.sin(2.0 * np.pi * dates.dayofyear.to_numpy() / 365.25)
    factor = rng.normal(0.0, 1.1, len(dates))
    data = {
        f"s{index}": seasonal + factor + 0.2 * index + rng.normal(0.0, 0.3, len(dates))
        for index in range(n_stations)
    }
    return pd.DataFrame(data, index=dates)


def test_observed_gap_starts_require_labels_and_a_donor() -> None:
    dates = pd.date_range("2010-06-01", periods=20, freq="D")
    target_ok = np.ones(20, dtype=bool)
    donor_ok = np.ones(20, dtype=bool)
    target_ok[5:8] = False
    starts = observed_gap_starts(
        dates, target_ok, donor_ok, length=3, season="JJA", later_half=False
    )
    assert 5 not in starts.tolist()
    assert 0 in starts.tolist()


def test_planted_gap_has_truth_and_is_not_confirmatory() -> None:
    wide = _toy_wide()
    scored = score_planted_gap(
        wide,
        network_id="toy",
        site_id="s0",
        start_index=400,
        length=14,
        season="JJA",
    )
    assert scored is not None
    assert scored["truth_source"] == "held_out_observed_days"
    assert scored["formal_evidence"] is False
    assert np.isfinite(scored["fill_mae"])
    assert scored["gap_length"] == 14


def test_seven_day_gap_is_scored() -> None:
    wide = _toy_wide()
    scored = score_planted_gap(
        wide,
        network_id="toy",
        site_id="s0",
        start_index=500,
        length=7,
        season="JJA",
    )
    assert scored is not None
    assert scored["gap_length"] == 7
    assert np.isfinite(scored["fill_mae"])


def test_natural_outage_summary_refuses_confirmation() -> None:
    blocks = pd.DataFrame(
        {
            "site_id": ["s0", "s1"],
            "start_date": ["2010-07-01", "2011-07-01"],
            "length_days": [14, 14],
            "season": ["JJA", "JJA"],
            "network_id": ["toy_a", "toy_b"],
        }
    )
    scores = score_natural_outages(
        {"toy_a": _toy_wide(seed=1), "toy_b": _toy_wide(seed=2)},
        blocks,
        max_gaps_per_station=1,
    )
    summary = natural_outage_summary(scores)
    assert summary["passed"] is False
    assert summary["confirmatory_eligible"] is False
    assert summary["unlabeled_missing_days_scored"] is False
    assert summary["last_check_temperatures_used"] is False
    if not scores.empty:
        assert scores["geometry_source"].eq("real_missing_blocks_length_season").all()
