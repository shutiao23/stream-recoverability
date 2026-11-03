"""Leakage-safe benchmarking of gap handling for annual climate records.

``gapbench`` is a small, standalone library distilled from a larger
stream-temperature recoverability study.  It provides outcome-blind year
selection, observed-window support, finite-record OLS trends, slope-error
decomposition, group-disjoint splits, a contiguous masking utility, and a
dated benchmark layer (annual H30 with observed bounds, controlled gap
generation, dependency-free baselines and a benchmark runner).
"""

from .benchmark import (
    AnnualH30,
    AnnualRecord,
    BenchmarkResult,
    GapPlan,
    annual_h30,
    ar1_bridge_paths,
    climatology_fill,
    generate_gaps,
    linear_interpolation_fill,
    run_benchmark,
)
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

__version__ = "1.3.0"

__all__ = [
    "AnnualH30",
    "AnnualRecord",
    "BenchmarkResult",
    "GapPlan",
    "ObservedWindow",
    "SlopeErrorDecomposition",
    "SlopeFit",
    "__version__",
    "annual_h30",
    "ar1_bridge_paths",
    "climatology_fill",
    "decompose_slope_error",
    "finite_record_slope",
    "generate_gaps",
    "group_splits",
    "linear_interpolation_fill",
    "mask_archive",
    "observed_window_bound",
    "run_benchmark",
    "select_years",
]
