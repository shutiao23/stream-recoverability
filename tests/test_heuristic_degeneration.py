from __future__ import annotations

import numpy as np

from stream_recoverability.analysis.heuristic_degeneration import (
    degeneration_bound,
    donor_count_inflation,
    forced_donor_dominated,
    jensen_acf_gap,
    memory_component,
    scan_degeneration,
)


def test_donor_r2_at_least_half_cannot_be_memory_dominated() -> None:
    bound = degeneration_bound(0.5)
    assert bound["forced_donor_dominated"] is True
    assert bound["memory_always_le_donor"] is True
    assert bound["any_rho_can_produce_memory_label"] is False
    for rho in (0.0, 0.5, 1.0):
        assert memory_component(0.85, rho) <= 0.85
        assert forced_donor_dominated(0.85)


def test_scan_has_no_memory_label_once_donor_r2_reaches_one_half() -> None:
    table = scan_degeneration()
    forced = table.loc[table["R2_donor"].ge(0.5)]
    assert forced["hard_label"].eq("donor_dominated").all()
    assert forced["forced_by_formula"].all()


def test_jensen_gap_is_nonzero_for_persistent_ar1() -> None:
    result = jensen_acf_gap(0.9, 180)
    assert abs(result["jensen_gap"]) > 1e-6
    assert abs(result["heuristic_gap"]) > 1e-6
    assert result["mean_nearest_boundary"] != result["d_over_4"]


def test_donor_count_inflates_in_sample_r2_more_than_cv() -> None:
    table = donor_count_inflation(seed=3)
    assert table.loc[table["n_donors"].eq(1), "in_sample_r2"].iloc[0] < table[
        "in_sample_r2"
    ].iloc[-1]
    assert table["year_block_cv_r2"].iloc[-1] <= table["in_sample_r2"].iloc[-1] + 1e-9
