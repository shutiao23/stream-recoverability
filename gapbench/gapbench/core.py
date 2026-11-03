"""Outcome-blind primitives for gap-handling benchmarks.

The functions in this module deliberately separate three concerns:

* what the observations can support (contiguous observed windows),
* which calendar years enter a finite-record trend (outcome-blind selection),
* how much of a trend error comes from the selected years versus reconstruction.

Only the last step is allowed to see annual temperature outcomes.  Selection
never receives a temperature, prediction, or reconstruction-error argument.
"""

from __future__ import annotations

import itertools
import math
import operator
from collections.abc import Sequence
from typing import Literal, NamedTuple

import numpy as np

__all__ = [
    "ObservedWindow",
    "SlopeErrorDecomposition",
    "SlopeFit",
    "decompose_slope_error",
    "finite_record_slope",
    "group_splits",
    "mask_archive",
    "observed_window_bound",
    "select_years",
]

_MAX_SUBSET_ENUMERATION = 2_000_000
_IDENTITY_TOLERANCE = 1e-12


class ObservedWindow(NamedTuple):
    """Best fully observed rolling window.

    Attributes
    ----------
    value:
        Maximum complete-window mean, or ``nan`` when no window is complete.
    start, end:
        Half-open positional bounds ``[start, end)`` of the maximising window,
        or ``None`` when no window is complete.  Ties resolve to the earliest
        start position.
    """

    value: float
    start: int | None
    end: int | None


class SlopeFit(NamedTuple):
    """Ordinary least-squares trend fit.

    Attributes
    ----------
    slope_per_decade:
        OLS slope multiplied by ten, in outcome units per decade.
    intercept:
        OLS intercept in the original year coordinate (the fitted value at
        calendar year zero).
    standard_error:
        Classical OLS standard error of ``slope_per_decade``.  It is ``nan``
        when there are exactly two observations because no residual degrees of
        freedom remain.
    n:
        Number of finite year/value pairs used in the fit.
    """

    slope_per_decade: float
    intercept: float
    standard_error: float
    n: int

    @property
    def slope(self) -> float:
        """Alias for :attr:`slope_per_decade`."""

        return self.slope_per_decade

    @property
    def se(self) -> float:
        """Alias for :attr:`standard_error`."""

        return self.standard_error


class SlopeErrorDecomposition(NamedTuple):
    """Finite-record slope-error decomposition.

    For one selected year set, let ``S`` be the selected complete-record slope
    minus the full-reference slope, ``R`` the estimated slope minus the selected
    complete-record slope, and ``E`` the estimated slope minus the full-reference
    slope.  Then ``E = S + R`` and the squared-error cross term is ``2 * S * R``.

    Attributes
    ----------
    S:
        Year-set (selection) error.
    R:
        Reconstruction error on the selected year set.
    E:
        Total slope error.
    cross_term:
        Signed squared-error cross term ``2 * S * R``.
    identity_residual:
        ``E - (S + R)``, which is zero up to floating-point arithmetic.
    identity_ok:
        Whether ``abs(identity_residual) <= 1e-12``.
    reference_slope:
        Supplied full-record slope.
    selected_truth_slope:
        Complete-record slope on the selected years.
    selected_estimate_slope:
        Estimated slope on the selected years.
    n:
        Number of selected years used in both fits.
    """

    S: float
    R: float
    E: float
    cross_term: float
    identity_residual: float
    identity_ok: bool
    reference_slope: float
    selected_truth_slope: float
    selected_estimate_slope: float
    n: int

    @property
    def year_set_error(self) -> float:
        """Alias for :attr:`S`."""

        return self.S

    @property
    def reconstruction_error(self) -> float:
        """Alias for :attr:`R`."""

        return self.R

    @property
    def total_error(self) -> float:
        """Alias for :attr:`E`."""

        return self.E

    @property
    def identity_holds(self) -> bool:
        """Alias for :attr:`identity_ok`."""

        return self.identity_ok


def _as_1d_float(values: Sequence[float] | np.ndarray, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    return array


def _as_1d_years(values: Sequence[int] | np.ndarray, name: str) -> np.ndarray:
    if isinstance(values, (set, frozenset)):
        values = sorted(values)
    raw = np.asarray(values)
    if raw.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if raw.size == 0:
        return np.empty(0, dtype=np.int64)
    try:
        numeric = raw.astype(np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain numeric calendar years") from exc
    if not np.all(np.isfinite(numeric)):
        raise ValueError(f"{name} must contain only finite calendar years")
    if not np.all(numeric == np.trunc(numeric)):
        raise ValueError(f"{name} must contain integer-valued calendar years")
    years = numeric.astype(np.int64)
    if np.unique(years).size != years.size:
        raise ValueError(f"{name} must not contain duplicate years")
    return years


def _as_int(value: int, name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer, not bool")
    try:
        return operator.index(value)
    except TypeError as exc:
        raise TypeError(f"{name} must be an integer") from exc


def observed_window_bound(
    series: Sequence[float] | np.ndarray,
    window: int = 30,
) -> ObservedWindow:
    """Find the maximum mean over fully observed contiguous windows.

    A window is fully observed only when every value in it is finite.  This is
    the observed support quantity used for H30-style annual heat extremes: the
    reported value is a realized lower bound on any unobserved maximum because
    a hidden peak cannot increase the best fully observed mean.

    Parameters
    ----------
    series:
        One-dimensional daily (or otherwise ordered) values.  Missing entries
        must be ``nan``.
    window:
        Positive window length.  The default 30 matches a 30-day H30 window.

    Returns
    -------
    ObservedWindow
        ``value`` is ``nan`` and ``start``/``end`` are ``None`` when no window
        is fully observed.  Otherwise ``start`` and ``end`` are positional,
        half-open bounds into ``series``; ties resolve to the earliest start.

    Raises
    ------
    ValueError
        If ``series`` is not one-dimensional or ``window`` is not positive.
    TypeError
        If ``window`` is not an integer.
    """

    values = _as_1d_float(series, "series")
    width = _as_int(window, "window")
    if width < 1:
        raise ValueError("window must be positive")
    if width > values.size:
        return ObservedWindow(float("nan"), None, None)

    finite = np.isfinite(values)
    cumulative_sum = np.concatenate(([0.0], np.cumsum(np.where(finite, values, 0.0))))
    cumulative_count = np.concatenate(([0], np.cumsum(finite.astype(np.int64))))
    sums = cumulative_sum[width:] - cumulative_sum[:-width]
    counts = cumulative_count[width:] - cumulative_count[:-width]
    complete = counts == width
    if not np.any(complete):
        return ObservedWindow(float("nan"), None, None)

    means = np.full(sums.size, -np.inf, dtype=float)
    means[complete] = sums[complete] / width
    start = int(np.argmax(means))
    return ObservedWindow(float(means[start]), start, start + width)


def finite_record_slope(
    years: Sequence[float] | np.ndarray,
    values: Sequence[float] | np.ndarray,
) -> SlopeFit:
    """Fit an OLS linear trend to a finite annual record.

    Parameters
    ----------
    years:
        One-dimensional calendar years (or decimal years).
    values:
        One-dimensional annual outcomes aligned with ``years``.  Non-finite
        pairs are dropped jointly.

    Returns
    -------
    SlopeFit
        Slope per decade, the intercept in the original year coordinate, the
        classical slope standard error, and the number of finite pairs.

    Raises
    ------
    ValueError
        If shapes differ, fewer than two finite pairs remain, or all finite
        years are identical.
    """

    year_values = _as_1d_float(years, "years")
    outcome_values = _as_1d_float(values, "values")
    if year_values.size != outcome_values.size:
        raise ValueError("years and values must have the same length")

    keep = np.isfinite(year_values) & np.isfinite(outcome_values)
    x = year_values[keep]
    y = outcome_values[keep]
    n = int(x.size)
    if n < 2:
        raise ValueError("at least two finite year/value pairs are required")

    x_mean = float(x.mean())
    y_mean = float(y.mean())
    centered = x - x_mean
    sxx = float(centered @ centered)
    if not math.isfinite(sxx) or sxx <= 0.0:
        raise ValueError("at least two distinct years are required")

    slope_per_year = float(centered @ (y - y_mean) / sxx)
    intercept = float(y_mean - slope_per_year * x_mean)
    residuals = y - (intercept + slope_per_year * x)
    sse = float(residuals @ residuals)
    if n > 2:
        standard_error = 10.0 * math.sqrt(max(sse, 0.0) / (n - 2) / sxx)
    else:
        standard_error = float("nan")
    return SlopeFit(
        slope_per_decade=10.0 * slope_per_year,
        intercept=intercept,
        standard_error=standard_error,
        n=n,
    )


def select_years(
    years: Sequence[int] | np.ndarray,
    complete_years: Sequence[int] | np.ndarray,
    method: Literal["cdf", "sxx"] = "cdf",
    count: int | None = None,
) -> np.ndarray:
    """Select calendar years without consulting any outcome.

    Every year in ``complete_years`` is retained.  The remaining ``count``
    slots are filled from the incomplete candidate years by an exhaustive,
    deterministic search over one of two calendar-geometry objectives:

    * ``"cdf"`` minimises the mean squared difference between the empirical
      CDFs of the selected and full year sets on the integer-year grid.
    * ``"sxx"`` maximises the centred year spread ``sum((year - mean) / 10)**2``.

    Ties are broken by the other objective and then by the lexicographic order
    of the chosen incomplete years.  The function has no temperature, outcome,
    prediction, or error parameter.  It cannot see whether a candidate year is
    hot, cold, well reconstructed, or badly reconstructed.

    Parameters
    ----------
    years:
        Unique integer calendar years in the candidate record.
    complete_years:
        Unique integer years that must be retained; they must be a subset of
        ``years``.
    method:
        ``"cdf"`` or ``"sxx"``.
    count:
        Total number of years to retain, including all complete years.  The
        default ``None`` retains all candidate years.  ``count`` must be at
        least ``len(complete_years)`` and at most ``len(years)``.

    Returns
    -------
    numpy.ndarray
        Sorted selected years as ``int64``.

    Raises
    ------
    ValueError
        For invalid methods, duplicate or non-integer years, incomplete years
        outside the candidate set, impossible counts, or more than 2,000,000
        candidate subsets.
    TypeError
        If ``count`` is not an integer.

    Notes
    -----
    The search enumerates ``C(len(incomplete), count - len(complete))`` sets and
    is intended for archive-scale year grids.  A hard limit of 2,000,000 subsets
    prevents accidental combinatorial blow-up.
    """

    if method not in ("cdf", "sxx"):
        raise ValueError("method must be 'cdf' or 'sxx'")
    all_years = np.sort(_as_1d_years(years, "years"))
    complete = np.sort(_as_1d_years(complete_years, "complete_years"))
    complete_set = set(complete.tolist())
    unknown = complete_set.difference(all_years.tolist())
    if unknown:
        raise ValueError(
            "complete_years must be a subset of years; unknown: "
            + ", ".join(map(str, sorted(unknown)))
        )

    total_years = int(all_years.size)
    if count is None:
        target_count = total_years
    else:
        target_count = _as_int(count, "count")
    if target_count < complete.size:
        raise ValueError("count must include every complete year")
    if target_count > total_years:
        raise ValueError("count cannot exceed the number of candidate years")

    incomplete = np.array(
        [year for year in all_years.tolist() if year not in complete_set],
        dtype=np.int64,
    )
    n_fill = target_count - int(complete.size)
    if n_fill == 0:
        return complete.astype(np.int64, copy=True)
    if n_fill == incomplete.size:
        return all_years.astype(np.int64, copy=True)

    number_of_subsets = math.comb(int(incomplete.size), int(n_fill))
    if number_of_subsets > _MAX_SUBSET_ENUMERATION:
        raise ValueError(
            f"{number_of_subsets} candidate subsets exceed the "
            f"{_MAX_SUBSET_ENUMERATION} enumeration limit"
        )

    grid = np.arange(int(all_years[0]), int(all_years[-1]) + 1, dtype=np.int64)
    full_counts = np.searchsorted(all_years, grid, side="right")
    complete_counts = np.searchsorted(complete, grid, side="right")
    candidate_steps = (incomplete[:, None] <= grid[None, :]).astype(np.int64)
    full_fraction = full_counts / float(total_years)

    best_key: tuple[float, float, tuple[int, ...]] | None = None
    best_selected: np.ndarray | None = None
    for combination in itertools.combinations(range(incomplete.size), n_fill):
        chosen = incomplete[list(combination)]
        selected = np.sort(np.concatenate((complete, chosen)))
        selected_counts = complete_counts + candidate_steps[list(combination)].sum(
            axis=0
        )
        cdf_distance = float(
            np.mean((selected_counts / float(target_count) - full_fraction) ** 2)
        )
        centered = (selected.astype(float) - float(selected.mean())) / 10.0
        sxx = float(centered @ centered)
        rounded_cdf = round(cdf_distance, 14)
        rounded_sxx = round(sxx, 14)
        chosen_key = tuple(int(year) for year in chosen)
        if method == "cdf":
            key = (rounded_cdf, -rounded_sxx, chosen_key)
        else:
            key = (-rounded_sxx, rounded_cdf, chosen_key)
        if best_key is None or key < best_key:
            best_key = key
            best_selected = selected

    assert best_selected is not None
    return best_selected.astype(np.int64, copy=False)


def decompose_slope_error(
    reference_slope: float,
    selected_years: Sequence[int] | np.ndarray,
    annual_truth: Sequence[float] | np.ndarray,
    annual_estimate: Sequence[float] | np.ndarray,
) -> SlopeErrorDecomposition:
    """Decompose a finite-record slope error into year-set and reconstruction parts.

    Parameters
    ----------
    reference_slope:
        Full-record complete-data slope in outcome units per decade.
    selected_years:
        Years retained by an outcome-blind selection.
    annual_truth:
        Complete-data annual outcomes aligned with ``selected_years``.
    annual_estimate:
        Reconstructed annual outcomes aligned with ``selected_years``.

    Returns
    -------
    SlopeErrorDecomposition
        ``S``, ``R``, ``E = S + R``, the cross term ``2 * S * R``, and an
        explicit identity check.  All slopes are per decade.

    Raises
    ------
    ValueError
        If inputs are not one-dimensional, lengths differ, years are invalid,
        or either selected slope cannot be fitted.
    """

    truth = _as_1d_float(annual_truth, "annual_truth")
    estimate = _as_1d_float(annual_estimate, "annual_estimate")
    selection = _as_1d_years(selected_years, "selected_years")
    if truth.size != selection.size or estimate.size != selection.size:
        raise ValueError(
            "selected_years, annual_truth, and annual_estimate must have the same length"
        )
    if not math.isfinite(reference_slope):
        raise ValueError("reference_slope must be finite")
    if not (np.all(np.isfinite(truth)) and np.all(np.isfinite(estimate))):
        raise ValueError("annual_truth and annual_estimate must be finite")

    truth_fit = finite_record_slope(selection.astype(float), truth)
    estimate_fit = finite_record_slope(selection.astype(float), estimate)
    s = float(truth_fit.slope_per_decade - reference_slope)
    r = float(estimate_fit.slope_per_decade - truth_fit.slope_per_decade)
    e = float(estimate_fit.slope_per_decade - reference_slope)
    residual = float(e - (s + r))
    return SlopeErrorDecomposition(
        S=s,
        R=r,
        E=e,
        cross_term=float(2.0 * s * r),
        identity_residual=residual,
        identity_ok=bool(abs(residual) <= _IDENTITY_TOLERANCE),
        reference_slope=float(reference_slope),
        selected_truth_slope=float(truth_fit.slope_per_decade),
        selected_estimate_slope=float(estimate_fit.slope_per_decade),
        n=int(truth_fit.n),
    )


def group_splits(
    groups: Sequence[object] | np.ndarray,
    n_splits: int = 5,
    seed: int = 0,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Build deterministic group-disjoint train/test folds.

    Groups are shuffled with ``numpy.random.default_rng(seed)`` and assigned
    greedily to the currently smallest fold (by sample count), with fold index
    breaking ties.  Every member of a group lands in exactly one test fold.
    This keeps correlated records, such as replicate archives from one river or
    station, out of both sides of a split.

    Parameters
    ----------
    groups:
        One-dimensional group label per sample.  Labels must be homogeneous and
        sortable.
    n_splits:
        Number of folds, at least two and no more than the number of groups.
    seed:
        Non-negative or negative integer seed for the deterministic shuffle.

    Returns
    -------
    list[tuple[numpy.ndarray, numpy.ndarray]]
        One ``(train_indices, test_indices)`` pair per fold.  Test folds are
        disjoint; train indices are their complements.

    Raises
    ------
    ValueError
        If ``groups`` is not one-dimensional or there are too few groups.
    TypeError
        If ``n_splits`` or ``seed`` is not an integer.
    """

    labels = np.asarray(groups)
    if labels.ndim != 1:
        raise ValueError("groups must be one-dimensional")
    if labels.size == 0:
        raise ValueError("groups must not be empty")
    folds_count = _as_int(n_splits, "n_splits")
    random_seed = _as_int(seed, "seed")
    if folds_count < 2:
        raise ValueError("n_splits must be at least two")

    unique_groups, inverse = np.unique(labels, return_inverse=True)
    if folds_count > unique_groups.size:
        raise ValueError("n_splits cannot exceed the number of unique groups")

    rng = np.random.default_rng(random_seed)
    order = rng.permutation(unique_groups.size)
    group_indices = [
        np.flatnonzero(inverse == index) for index in range(unique_groups.size)
    ]
    fold_groups: list[list[int]] = [[] for _ in range(folds_count)]
    fold_sizes = [0 for _ in range(folds_count)]
    for group_index in order:
        fold = min(range(folds_count), key=lambda index: (fold_sizes[index], index))
        fold_groups[fold].append(int(group_index))
        fold_sizes[fold] += int(group_indices[int(group_index)].size)

    all_indices = np.arange(labels.size, dtype=np.int64)
    folds: list[tuple[np.ndarray, np.ndarray]] = []
    for assigned in fold_groups:
        if assigned:
            test_indices = np.sort(
                np.concatenate([group_indices[index] for index in assigned])
            )
        else:
            test_indices = np.empty(0, dtype=np.int64)
        mask = np.ones(labels.size, dtype=bool)
        mask[test_indices] = False
        folds.append((all_indices[mask], test_indices))
    return folds


def mask_archive(
    values: Sequence[float] | np.ndarray,
    start: int,
    length: int,
) -> np.ndarray:
    """Return a copy with a contiguous archive segment replaced by ``nan``.

    Parameters
    ----------
    values:
        One-dimensional values.
    start:
        Zero-based start position of the masked segment.
    length:
        Number of consecutive positions to mask; may be zero.

    Returns
    -------
    numpy.ndarray
        A float copy of ``values`` with ``[start, start + length)`` set to
        ``nan``.  The input is never modified.

    Raises
    ------
    ValueError
        If ``values`` is not one-dimensional or the segment lies outside the
        array.
    TypeError
        If ``start`` or ``length`` is not an integer.
    """

    array = _as_1d_float(values, "values")
    first = _as_int(start, "start")
    span = _as_int(length, "length")
    if first < 0:
        raise ValueError("start must be non-negative")
    if span < 0:
        raise ValueError("length must be non-negative")
    if first > array.size or first + span > array.size:
        raise ValueError("masked segment lies outside the array")
    masked = array.copy()
    if span:
        masked[first : first + span] = np.nan
    return masked
