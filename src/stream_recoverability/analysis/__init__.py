"""Descriptive analysis and event-label helpers."""

from .eda import (
    ACF_LAGS,
    build_event_labels,
    cross_station_lag_correlations,
    lagged_correlation,
    run_eda,
)

__all__ = [
    "ACF_LAGS",
    "build_event_labels",
    "cross_station_lag_correlations",
    "lagged_correlation",
    "run_eda",
]

