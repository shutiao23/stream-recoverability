"""Compact gapbench quickstart on a synthetic 20-year daily series."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from gapbench import (
    decompose_slope_error,
    finite_record_slope,
    mask_archive,
    observed_window_bound,
    select_years,
)

FIRST_YEAR = 2001
N_YEARS = 20
DAYS_PER_YEAR = 365
WINDOW = 30
GAPS = (
    (7, 170, 60),
    (11, 190, 21),
    (14, 215, 14),
    (18, 155, 10),
)


def annual_h30(daily: np.ndarray) -> np.ndarray:
    by_year = daily.reshape(N_YEARS, DAYS_PER_YEAR)
    windows = np.lib.stride_tricks.sliding_window_view(by_year, WINDOW, axis=1)
    return np.nanmax(windows.mean(axis=2), axis=1)


def main() -> None:
    rng = np.random.default_rng(20261102)
    years = np.repeat(np.arange(FIRST_YEAR, FIRST_YEAR + N_YEARS), DAYS_PER_YEAR)
    day_of_year = np.tile(np.arange(DAYS_PER_YEAR), N_YEARS)
    seasonal = 12.0 * np.sin(2.0 * np.pi * (day_of_year - 80) / DAYS_PER_YEAR)
    warming = 0.04 * (years - FIRST_YEAR)
    values = 15.0 + seasonal + warming + rng.normal(0.0, 1.2, years.size)

    masked = values.copy()
    for year_offset, start_day, length in GAPS:
        masked = mask_archive(masked, year_offset * DAYS_PER_YEAR + start_day, length)

    bound = observed_window_bound(masked, WINDOW)
    candidate_years = np.arange(FIRST_YEAR, FIRST_YEAR + N_YEARS)
    incomplete_years = np.array([FIRST_YEAR + offset for offset, _, _ in GAPS])
    complete_years = np.setdiff1d(candidate_years, incomplete_years)

    count = 18
    selected_cdf = select_years(
        candidate_years, complete_years, method="cdf", count=count
    )
    selected_sxx = select_years(
        candidate_years, complete_years, method="sxx", count=count
    )

    cube = masked.reshape(N_YEARS, DAYS_PER_YEAR)
    climatology = np.nanmean(cube, axis=0)
    filled = np.where(np.isnan(cube), climatology[None, :], cube)
    annual_truth = annual_h30(values)
    annual_estimate = annual_h30(filled.reshape(-1))
    reference = finite_record_slope(candidate_years, annual_truth)

    start_year = FIRST_YEAR + int(bound.start) // DAYS_PER_YEAR
    start_day = int(bound.start) % DAYS_PER_YEAR + 1
    end_year = FIRST_YEAR + (int(bound.end) - 1) // DAYS_PER_YEAR
    end_day = (int(bound.end) - 1) % DAYS_PER_YEAR + 1
    missing = int(np.isnan(masked).sum())

    print("gapbench quickstart")
    print("-------------------")
    print(
        f"series: {years.size} daily values, {N_YEARS} years "
        f"({FIRST_YEAR}-{FIRST_YEAR + N_YEARS - 1}); 4 gaps, longest 60 days"
    )
    print(
        f"observed H30 bound: {bound.value:.3f} degC at positions "
        f"{bound.start}..{bound.end} ({start_year} DOY {start_day}-{end_year} DOY {end_day})"
    )
    print(
        f"masked: {missing}/{years.size} values ({100.0 * missing / years.size:.2f}%)"
    )
    print(
        f"complete years: {complete_years.size}; incomplete: {incomplete_years.tolist()}"
    )
    print(
        f"reference slope (full complete truth): {reference.slope_per_decade:.4f} degC/decade"
    )
    print(f"reference slope classical SE: {reference.standard_error:.4f} degC/decade")
    print(f"CDF selection (n={count}): {selected_cdf.tolist()}")
    print(f"Sxx selection (n={count}): {selected_sxx.tolist()}")

    for label, selected in (("CDF", selected_cdf), ("Sxx", selected_sxx)):
        indices = selected - FIRST_YEAR
        result = decompose_slope_error(
            reference.slope_per_decade,
            selected,
            annual_truth[indices],
            annual_estimate[indices],
        )
        print(
            f"{label} decomposition: S={result.S:+.4f} R={result.R:+.4f} "
            f"E={result.E:+.4f} 2*S*R={result.cross_term:+.4f} "
            f"identity_ok={result.identity_ok}"
        )


if __name__ == "__main__":
    main()
