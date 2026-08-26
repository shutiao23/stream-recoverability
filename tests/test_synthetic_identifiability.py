from __future__ import annotations

from stream_recoverability.experiments.recoverability_baselines import (
    residual_after_simple_baselines,
    run_baseline_suite,
)
from stream_recoverability.experiments.synthetic_identifiability import (
    run_e0,
    sampled_r2_comparison,
)
from stream_recoverability.experiments.synthetic_river import (
    catalog,
    high_donor_and_high_memory_river,
)


def test_e0_recovers_signs_and_exhibits_heuristic_degeneration() -> None:
    result = run_e0(include_coverage=False)
    assert result["pass"]["memory_sign"]
    assert result["pass"]["donor_sign"]
    assert result["pass"]["heuristic_forced_on_mixed"]
    assert result["pass"]["jensen_nonzero"]
    assert result["state_shift"]["sign_changes"]


def test_mixed_river_has_high_donor_r2_and_remaining_memory() -> None:
    stats = sampled_r2_comparison(high_donor_and_high_memory_river(), seed=1)
    assert stats["true_donor_r2"] >= 0.5
    assert stats["in_sample_r2"] >= 0.5


def test_operator_explains_residual_after_simple_baselines() -> None:
    suite = run_baseline_suite(catalog())
    gain = residual_after_simple_baselines(suite["predictions"])
    assert gain["residual_r2"] > 0.0
