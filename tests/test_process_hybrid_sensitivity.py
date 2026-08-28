from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.experiments.process_hybrid_sensitivity import (
    hybrid_prediction,
    process_features,
)


def test_process_features_are_timestamp_aligned_and_finite() -> None:
    index = pd.date_range("2020-01-01", periods=10, freq="D")
    result = process_features(
        index,
        pd.Series(np.arange(10), index=index),
        pd.Series(np.arange(10), index=index),
    )
    assert result.index.equals(index)
    assert result.shape == (10, 6)
    assert np.isfinite(result.to_numpy()).all()


def test_hybrid_prediction_uses_boundaries_without_changing_length() -> None:
    process = np.full(7, 5.0)
    result = hybrid_prediction(
        process, left_boundary=1.0, right_boundary=3.0, gap_length=7
    )
    assert result.shape == (7,)
    assert np.isfinite(result).all()
    assert (result > 1.0).all()
    assert (result < 5.0).all()
