from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.experiments.gap_triage import (
    compare_operator_to_length_only,
    safe_fill_fraction,
)


def test_safe_fill_keeps_false_release_at_or_below_cap() -> None:
    risk = np.array([0.1, 0.2, 0.3, 0.8, 0.9])
    error = np.array([0.1, 0.2, 0.6, 0.7, 0.8])
    result = safe_fill_fraction(risk, error, false_release_rate=0.05, error_threshold_c=0.5)
    assert result["false_release_rate"] <= 0.05 + 1e-12
    assert result["n_declared_safe"] == 2


def test_operator_beats_length_only_on_a_constructed_case() -> None:
    frame = pd.DataFrame(
        {
            "network_id": ["a"] * 6 + ["b"] * 6,
            "predicted_conditional_risk": [0.2, 0.2, 0.9, 0.9, 0.1, 0.1] * 2,
            "gap_length": [7, 7, 14, 14, 90, 90] * 2,
            "fill_mae": [0.2, 0.2, 0.9, 0.9, 0.15, 0.15] * 2,
        }
    )
    result = compare_operator_to_length_only(frame)
    assert result["formal_evidence"] is False
    assert result["headline_claim_licensed"] is False
    assert result["passed"] is False
    assert result["relative_improvement"] > 0
    assert result["absolute_improvement_pp"] > 0
    assert result["n_fills"] == 12


def test_triage_does_not_pass_when_operator_is_no_better() -> None:
    frame = pd.DataFrame(
        {
            "network_id": ["x"] * 8,
            "predicted_conditional_risk": np.arange(8, dtype=float),
            "gap_length": np.arange(8, dtype=float),
            "fill_mae": np.linspace(0.1, 1.2, 8),
        }
    )
    result = compare_operator_to_length_only(frame)
    assert result["passed"] is False
    assert result["confirmatory_eligible"] is False
