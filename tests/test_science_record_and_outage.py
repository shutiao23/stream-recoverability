from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.analysis.hierarchical_confirmation import (
    evaluate_success,
    simulate_confirmation_panel,
)
from stream_recoverability.analysis.natural_outage import (
    TASK_ONLINE,
    catalog_from_quality_flags,
    gap_runs,
    task_contract,
    weight_natural_suite,
)
from stream_recoverability.analysis.science_record import science_record_metrics
from stream_recoverability.analysis.state_segments import (
    assign_state,
    evaluation_regime,
    variance_ratio_segments,
)


def test_science_record_reports_phase_and_annual_errors() -> None:
    dates = pd.date_range("2010-01-01", periods=365 * 4, freq="D")
    truth = 10 + 6 * np.sin(2 * np.pi * dates.dayofyear.to_numpy() / 365.25)
    prediction = truth.copy()
    mask = np.zeros(len(dates), dtype=bool)
    mask[100:130] = True
    prediction[mask] = truth[mask] + 1.5
    quality = np.ones(len(dates), dtype=bool)
    metrics = science_record_metrics(
        truth, prediction, quality, mask, dates=dates, high_threshold=14.0
    )
    assert metrics["mae"] > 0
    assert np.isfinite(metrics["annual_amplitude_mae"])
    assert np.isfinite(metrics["seasonal_phase_true"])


def test_natural_outage_catalog_and_online_forbids_right_boundary() -> None:
    assert gap_runs([False, True, True, False, True]) == [
        {"start": 1, "end": 2, "length": 2},
        {"start": 4, "end": 4, "length": 1},
    ]
    frame = pd.DataFrame(
        {
            "station_id": ["A"] * 10,
            "date": pd.date_range("2020-01-01", periods=10, freq="D"),
            "missing": [False, True, True, False, False, True, False, False, False, False],
        }
    )
    catalog = weight_natural_suite(catalog_from_quality_flags(frame))
    assert len(catalog) == 2
    assert catalog["weight"].sum() == 1.0
    contract = task_contract(TASK_ONLINE)
    assert contract["right_boundary_allowed"] is False


def test_state_segments_and_confirmation_machinery() -> None:
    dates = pd.date_range("2000-01-01", periods=800, freq="D")
    values = np.r_[np.ones(400), 3 * np.ones(400)]
    values = values + np.random.default_rng(0).normal(0, 0.05, 800)
    segment = variance_ratio_segments(values, dates, min_days=100)
    assert segment["break_index"] is not None
    states = assign_state(dates, str(segment["break_date"]))
    assert evaluation_regime(states[0], states[-1]) == "changed_state"
    panel = simulate_confirmation_panel(n_networks=8, seed=2)
    result = evaluate_success(panel)
    assert result["spearman"]["n_networks"] == 8
    assert "passed" in result
