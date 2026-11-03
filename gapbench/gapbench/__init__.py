"""Leakage-safe benchmarking of gap handling for annual climate records.

``gapbench`` is a small, standalone library distilled from a larger
stream-temperature recoverability study.  It provides outcome-blind year
selection, observed-window support, finite-record OLS trends, slope-error
decomposition, group-disjoint splits, and a contiguous masking utility.
"""

from .core import (
    ObservedWindow,
    SlopeErrorDecomposition,
    SlopeFit,
    decompose_slope_error,
    finite_record_slope,
    group_splits,
    mask_archive,
    observed_window_bound,
    select_years,
)

__version__ = "1.2.0"

__all__ = [
    "ObservedWindow",
    "SlopeErrorDecomposition",
    "SlopeFit",
    "__version__",
    "decompose_slope_error",
    "finite_record_slope",
    "group_splits",
    "mask_archive",
    "observed_window_bound",
    "select_years",
]
