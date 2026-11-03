"""Dated annual statistics, gap generation, baseline reconstruction and the
benchmark runner.

This module extends the outcome-blind primitives in :mod:`gapbench.core` with
the pieces needed to reproduce a full gap-handling benchmark on real archives:

* :func:`annual_h30` computes date-aware annual H30 values, observed lower
  bounds ``L_y`` and completeness flags for incomplete years;
* :func:`generate_gaps` draws controlled contiguous gaps (length, warm-season
  placement, per-year probability, burn-in) with a reproducible seed;
* :func:`climatology_fill`, :func:`linear_interpolation_fill` and
  :func:`ar1_bridge_paths` are simple, dependency-free reconstruction
  baselines;
* :func:`run_benchmark` scores any user-supplied reconstructor against the
  complete-record reference and returns annual errors, trend errors and the
  ``S/R/E`` decomposition from the core module.

Selection functions from :mod:`gapbench.core` never see temperatures; the
runner enforces that contract by construction.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable, Sequence
from typing import NamedTuple

import numpy as np

from gapbench.core import decompose_slope_error, finite_record_slope, select_years

__all__ = [
    "AnnualH30",
    "AnnualRecord",
    "GapPlan",
    "BenchmarkResult",
    "annual_h30",
    "generate_gaps",
    "climatology_fill",
    "linear_interpolation_fill",
    "ar1_bridge_paths",
    "run_benchmark",
]


class AnnualH30(NamedTuple):
    """Annual H30 statistics for one dated daily series.

    Attributes
    ----------
    years:
        Sorted calendar years present in the series.
    h30:
        Annual maximum of complete rolling ``window``-day means.  ``nan`` for a
        year with fewer than ``window`` consecutive observed days.
    observed_bound:
        Largest mean over any fully observed ``window``-day run inside the
        year; equals ``h30`` for complete years and is a valid observed lower
        bound ``L_y`` for incomplete ones.
    complete:
        Boolean flag: the year contains every calendar day (no missing dates
        and no masked values).
    """

    years: np.ndarray
    h30: np.ndarray
    observed_bound: np.ndarray
    complete: np.ndarray


class GapPlan(NamedTuple):
    """A realized controlled-gap design.

    Attributes
    ----------
    years, start_days, lengths:
        Parallel arrays describing each gap: calendar year, zero-based day
        offset within that year, and gap length in days.
    mask:
        Boolean daily mask aligned with the input series; ``True`` marks a
        hidden (removed) day.
    """

    years: np.ndarray
    start_days: np.ndarray
    lengths: np.ndarray
    mask: np.ndarray


class AnnualRecord(NamedTuple):
    """One archive's annual quantities handed to the reconstructor.

    Attributes
    ----------
    years:
        Calendar years of the analysis window.
    observed_bound:
        ``L_y`` per year (``nan`` when no complete window exists).
    complete:
        Whether each year is fully observed.
    """

    years: np.ndarray
    observed_bound: np.ndarray
    complete: np.ndarray


class BenchmarkResult(NamedTuple):
    """Scores for one reconstructor on one masked archive.

    Attributes
    ----------
    annual_error:
        Reconstructed minus true H30 for the reconstructed (incomplete) years.
    slope_true:
        Complete-record reference slope (degrees per decade in input units).
    slope_estimated:
        Slope of the reconstructed annual series over the selected years.
    slope_selected_reference:
        Slope of the true annual series over the same selected years.
    decomposition:
        ``SlopeErrorDecomposition`` for the selected year set.
    """

    annual_error: np.ndarray
    slope_true: float
    slope_estimated: float
    slope_selected_reference: float
    decomposition: object


def _to_dates(dates: Sequence) -> np.ndarray:
    """Normalize date-like input to a ``datetime64[D]`` array."""
    return np.asarray(dates, dtype="datetime64[D]")


def _dated_series(dates: Sequence, values: Sequence[float] | np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Validate a dated series and return (sorted dates, sorted values, sort order, inverse order)."""
    values = np.asarray(values, float)
    days = _to_dates(dates)
    if days.size != values.size:
        raise ValueError("dates and values must have the same length")
    order = np.argsort(days, kind="stable")
    inverse = np.empty_like(order)
    inverse[order] = np.arange(order.size)
    return days[order], values[order], order, inverse


def _year_blocks(days: np.ndarray) -> dict[int, np.ndarray]:
    years = days.astype("datetime64[Y]").astype(int) + 1970
    return {int(year): np.flatnonzero(years == year) for year in np.unique(years)}


def annual_h30(
    dates: Sequence,
    values: Sequence[float] | np.ndarray,
    window: int = 30,
    train_years: Sequence[int] | None = None,
) -> AnnualH30:
    """Compute date-aware annual H30, observed bounds and completeness.

    Parameters
    ----------
    dates:
        Daily timestamps (``datetime.date``, ``numpy.datetime64`` or ISO
        strings); each must be a calendar day, duplicates are rejected.
    values:
        Daily values aligned with ``dates``; masked days may be ``nan``.
    window:
        Rolling-window length in days (default 30).
    train_years:
        Optional calendar years used only to define the reference set of
        expected days (leap years are handled per calendar).  When omitted the
        years present in ``dates`` define the expectation.

    Returns
    -------
    AnnualH30
        Per-year H30 (``nan`` when no complete window exists), the observed
        lower bound ``L_y`` (also ``nan`` in that case) and a completeness flag
        that is ``True`` only when every calendar day of the year is present
        and finite.
    """
    if window < 1:
        raise ValueError("window must be positive")
    sorted_dates, series, _, _ = _dated_series(dates, values)
    blocks = _year_blocks(sorted_dates)
    expected_years = (
        [int(y) for y in train_years]
        if train_years is not None
        else sorted(blocks)
    )
    out_years, out_h30, out_bound, out_complete = [], [], [], []
    for year in sorted(expected_years):
        idx = blocks.get(year, np.array([], int))
        days_in_year = 366 if calendar.isleap(year) else 365
        present = np.zeros(days_in_year, bool)
        finite = np.full(days_in_year, np.nan)
        positions = (sorted_dates[idx] - np.datetime64(f"{year}-01-01")).astype(int)
        if np.unique(positions).size != positions.size:
            raise ValueError(f"duplicate dates in year {year}")
        present[positions] = True
        finite[positions] = series[idx]
        run_lengths = np.full(days_in_year + 1, 0)
        fully_observed = present & np.isfinite(finite)
        for day in range(days_in_year - 1, -1, -1):
            run_lengths[day] = run_lengths[day + 1] + 1 if fully_observed[day] else 0
        complete_window = run_lengths >= window
        if complete_window.any():
            sums = np.convolve(np.nan_to_num(finite), np.ones(window), mode="valid")
            starts = np.flatnonzero(complete_window)
            means = sums[starts] / window
            bound = float(means[int(np.argmax(means))])
        else:
            bound = np.nan
        complete = bool(present.all() and np.isfinite(finite).all())
        h30 = bound if complete else np.nan
        out_years.append(year)
        out_h30.append(h30)
        out_bound.append(bound)
        out_complete.append(complete)
    return AnnualH30(
        np.asarray(out_years, int),
        np.asarray(out_h30, float),
        np.asarray(out_bound, float),
        np.asarray(out_complete, bool),
    )


def generate_gaps(
    years: Sequence[int],
    seed: int,
    length_days: int,
    *,
    year_probability: float = 0.35,
    burn_in_years: int = 7,
    start_range: tuple[int, int] = (120, 275),
    exclude_years: Sequence[int] | None = None,
) -> GapPlan:
    """Draw a reproducible controlled-gap design over dated calendar years.

    Each post-burn-in year is masked independently with ``year_probability``;
    each selected year receives one contiguous ``length_days`` gap whose
    zero-based start is drawn uniformly from ``start_range`` (a warm-season
    band by default).  The plan is purely calendar-based: it never sees data.

    Parameters
    ----------
    years:
        Sorted calendar years of the analysis window.
    seed:
        Seed for the independent stream of this design.
    length_days:
        Contiguous gap length in days.
    year_probability:
        Per-year masking probability after the burn-in.
    burn_in_years:
        Leading years that are never masked.
    start_range:
        Half-open range of zero-based start-day offsets within the year.
    exclude_years:
        Years that are never masked regardless of the draw (for example,
        forward-mode cutoffs).

    Returns
    -------
    GapPlan
        Realized gaps and the aligned daily boolean mask over the concatenated
        calendar (365/366 days per year as appropriate).
    """
    if not 0.0 <= year_probability <= 1.0:
        raise ValueError("year_probability must be in [0, 1]")
    if length_days < 1:
        raise ValueError("length_days must be positive")
    if not 0 <= start_range[0] < start_range[1] <= 366:
        raise ValueError("start_range must satisfy 0 <= lo < hi <= 366")
    years = np.asarray(sorted(int(y) for y in years), int)
    if np.unique(years).size != years.size:
        raise ValueError("years must be unique")
    excluded = set() if exclude_years is None else {int(y) for y in exclude_years}
    chosen_years, starts, lengths = [], [], []
    total_days = sum(366 if calendar.isleap(int(y)) else 365 for y in years)
    mask = np.zeros(total_days, bool)
    # One spawned stream per year keeps designs stable under exclusion: skipping
    # a year never shifts the random draws of later years.
    children = np.random.SeedSequence(seed).spawn(len(years))
    offset = 0
    for position, (year, child) in enumerate(zip(years, children)):
        days = 366 if calendar.isleap(int(year)) else 365
        rng = np.random.default_rng(child)
        if (
            position >= burn_in_years
            and int(year) not in excluded
            and rng.random() < year_probability
        ):
            start = int(rng.integers(start_range[0], max(start_range[1], start_range[0] + 1)))
            start = min(start, days - length_days) if days - length_days >= 0 else 0
            chosen_years.append(int(year))
            starts.append(start)
            lengths.append(length_days)
            mask[offset + start : offset + start + length_days] = True
        offset += days
    return GapPlan(
        np.asarray(chosen_years, int),
        np.asarray(starts, int),
        np.asarray(lengths, int),
        mask,
    )


def _apply_gap_plan(values: np.ndarray, plan: GapPlan) -> np.ndarray:
    out = np.asarray(values, float).copy()
    out[plan.mask] = np.nan
    return out


def climatology_fill(
    dates: Sequence, values: Sequence[float] | np.ndarray, window: int = 30
) -> np.ndarray:
    """Fill masked days with the day-of-year mean of fully observed years.

    Returns the filled daily series (same length and order as ``values``).
    """
    sorted_dates, series, _, inverse = _dated_series(dates, values)
    blocks = _year_blocks(sorted_dates)
    years = sorted(blocks)
    doy = (sorted_dates - sorted_dates.astype("datetime64[Y]")).astype(int)
    complete_years = []
    for year in years:
        idx = blocks[year]
        days_in_year = 366 if calendar.isleap(int(year)) else 365
        if idx.size == days_in_year and np.isfinite(series[idx]).all():
            complete_years.append(year)
    if not complete_years:
        raise ValueError("climatology_fill requires at least one fully observed year")
    reference = np.zeros(366)
    counts = np.zeros(366)
    for year in complete_years:
        idx = blocks[year]
        d = doy[idx]
        keep = np.isfinite(series[idx])
        reference[d[keep]] += series[idx][keep]
        counts[d[keep]] += 1
    climatology = np.divide(reference, counts, out=np.full(366, np.nan), where=counts > 0)
    filled = series.copy()
    nan_days = ~np.isfinite(filled)
    filled[nan_days] = climatology[np.minimum(doy[nan_days], 365)]
    return filled[inverse]


def linear_interpolation_fill(dates: Sequence, values: Sequence[float] | np.ndarray) -> np.ndarray:
    """Fill masked days by linear interpolation in time; edge gaps extend the
    nearest observed value."""
    sorted_dates, series, _, inverse = _dated_series(dates, values)
    positions = np.arange(series.size)
    finite = np.isfinite(series)
    if finite.sum() < 2:
        raise ValueError("at least two observed days are required")
    filled = np.interp(positions, positions[finite], series[finite])
    return filled[inverse]


def ar1_bridge_paths(
    dates: Sequence,
    values: Sequence[float] | np.ndarray,
    n_paths: int = 20,
    seed: int = 0,
) -> np.ndarray:
    """Pathwise AR(1) residual bridges with independent spawned streams.

    Residuals (value minus day-of-year climatology) inside each gap are bridged
    by a mean-zero AR(1) process tied to the surrounding observed residuals.
    Path ``i`` uses ``SeedSequence(seed).spawn(n_paths)[i]`` so any prefix of
    the ensemble is reproducible regardless of ``n_paths``.

    Returns
    -------
    numpy.ndarray
        ``(n_paths, len(values))`` filled daily series in input order.
    """
    if n_paths < 1:
        raise ValueError("n_paths must be positive")
    sorted_dates, series, order, inverse = _dated_series(dates, values)
    doy = (sorted_dates - sorted_dates.astype("datetime64[Y]")).astype(int)
    children = np.random.SeedSequence(seed).spawn(n_paths)
    filled = np.repeat(series[None, :], n_paths, axis=0)
    nan_days = np.flatnonzero(~np.isfinite(series))
    if nan_days.size == 0:
        return filled
    # Day-of-year climatology from observed days only.
    sums = np.zeros(366)
    counts = np.zeros(366)
    observed = np.isfinite(series)
    np.add.at(sums, doy[observed], series[observed])
    np.add.at(counts, doy[observed], 1.0)
    climatology = np.divide(sums, counts, out=np.zeros(366), where=counts > 0)
    residual = series - climatology[np.minimum(doy, 365)]
    # Split masked days into contiguous gaps and bridge each independently.
    gap_edges = np.flatnonzero(np.diff(np.r_[False, ~observed, False].astype(int)))
    starts, ends = gap_edges[0::2], gap_edges[1::2]
    for path_index, child in enumerate(children):
        rng = np.random.default_rng(child)
        for start, end in zip(starts, ends):
            left = residual[start - 1] if start > 0 and np.isfinite(residual[start - 1]) else 0.0
            right = residual[end] if end < residual.size and np.isfinite(residual[end]) else left
            n = end - start
            rho = 0.7
            innovations = rng.normal(0.0, max(np.nanstd(residual[observed]), 1e-6), n)
            path = np.empty(n)
            previous = left
            for day in range(n):
                weight = (day + 1) / (n + 1)
                deterministic = left * (1 - weight) + right * weight
                previous = rho * previous + innovations[day]
                path[day] = deterministic + previous
            # Taper the accumulated AR(1) state so both gap ends are respected.
            path = path - np.linspace(path[0] - left, path[-1] - right, n)
            filled[path_index, start:end] = climatology[np.minimum(doy[start:end], 365)] + path
    return filled[:, inverse]


def run_benchmark(
    dates: Sequence,
    values: Sequence[float] | np.ndarray,
    gap_plan: GapPlan,
    reconstructor: Callable[[np.ndarray, np.ndarray, AnnualRecord], np.ndarray],
    *,
    window: int = 30,
    selection_count: int | None = None,
    selection_method: str = "sxx",
) -> BenchmarkResult:
    """Score one reconstructor on one masked archive.

    Parameters
    ----------
    dates, values:
        The complete dated daily series (the hidden truth).
    gap_plan:
        A :class:`GapPlan` such as the output of :func:`generate_gaps`;
        ``plan.mask`` must align with the concatenated calendar of ``dates``.
    reconstructor:
        Callable ``reconstructor(dates, daily_masked, record) -> daily_filled``
        receiving the chronologically sorted dates and masked series plus the
        :class:`AnnualRecord` (or any array ``annual`` of length
        ``len(record.years)``; detection is by output size).  It must not use
        the complete ``values``.
    window:
        Rolling-window length for H30.
    selection_count:
        Optional fixed number of retained years for outcome-blind selection;
        ``None`` retains all supported years.
    selection_method:
        ``"cdf"`` or ``"sxx"`` when ``selection_count`` is given.

    Returns
    -------
    BenchmarkResult
        Annual errors, reference and estimated slopes, and the ``S/R/E``
        decomposition over the selected years.
    """
    sorted_dates, series, _, _ = _dated_series(dates, values)
    if gap_plan.mask.size != series.size:
        raise ValueError("gap plan mask must align with the daily series")
    truth = annual_h30(sorted_dates, series, window=window)
    masked = _apply_gap_plan(series, gap_plan)
    observed = annual_h30(sorted_dates, masked, window=window)
    record = AnnualRecord(observed.years, observed.observed_bound, observed.complete)
    output = reconstructor(sorted_dates, masked, record)
    output = np.asarray(output, float)
    if output.size == masked.size:
        reconstructed = annual_h30(sorted_dates, output, window=window)
        annual_estimate = reconstructed.h30
    elif output.size == observed.years.size:
        annual_estimate = output
    else:
        raise ValueError("reconstructor must return a daily series or annual values")
    reference = finite_record_slope(truth.years, truth.h30)
    incomplete_years = observed.years[~observed.complete]
    incomplete_index = np.flatnonzero(~observed.complete)
    if selection_count is None:
        selected = observed.years[observed.complete]
    else:
        selected = select_years(
            observed.years,
            observed.years[observed.complete],
            method=selection_method,
            count=selection_count,
        )
    selected_index = np.flatnonzero(np.isin(observed.years, selected))
    estimated = finite_record_slope(selected, annual_estimate[selected_index])
    selected_reference = finite_record_slope(selected, truth.h30[selected_index])
    decomposition = decompose_slope_error(
        reference.slope_per_decade,
        selected,
        truth.h30[selected_index],
        annual_estimate[selected_index],
    )
    return BenchmarkResult(
        annual_error=annual_estimate[incomplete_index] - truth.h30[incomplete_index],
        slope_true=float(reference.slope_per_decade),
        slope_estimated=float(estimated.slope_per_decade),
        slope_selected_reference=float(selected_reference.slope_per_decade),
        decomposition=decomposition,
    )
