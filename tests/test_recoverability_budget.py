from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.analysis.recoverability_budget import budget_decomposition


def _frame() -> pd.DataFrame:
    dates = pd.date_range("2001-01-01", periods=365 * 4, freq="D")
    rng = np.random.default_rng(7)
    seasonal = 8.0 * np.sin(2.0 * np.pi * dates.dayofyear.to_numpy() / 365.25)
    donor = rng.normal(0.0, 0.5, len(dates))
    target = seasonal + 0.8 * donor + rng.normal(0.0, 0.2, len(dates))
    return pd.DataFrame(
        {"date": dates, "A_T": target, "B_T": seasonal + donor, "C_T": seasonal}
    )


def test_budget_decomposition_is_bounded_and_uses_requested_gaps() -> None:
    result = budget_decomposition(_frame(), "A", ("B", "C"), (1, 30, 180))
    assert result["gap_length_days"].tolist() == [1, 30, 180]
    assert result["R2_donor"].between(0.0, 1.0).all()
    assert result["R2_avail"].between(result["R2_donor"], 1.0).all()
    assert result["predicted_skill"].between(0.0, 1.0).all()
    assert result.loc[0, "effective_acf_lag_days"] == 1.0


def test_more_donor_information_raises_the_long_gap_budget() -> None:
    frame = _frame()
    with_donors = budget_decomposition(frame, "A", ("B", "C"), (180,))
    weak_donor = frame.assign(B_T=np.roll(frame["B_T"].to_numpy(), 180))
    without_aligned_donor = budget_decomposition(weak_donor, "A", ("B", "C"), (180,))
    assert with_donors.loc[0, "R2_donor"] > without_aligned_donor.loc[0, "R2_donor"]
