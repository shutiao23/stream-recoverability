"""gapbench quickstart: dated annual H30, observed bounds and a mini benchmark.

Builds a synthetic 20-year daily series, degrades it with a reproducible
controlled-gap design, and shows the two questions the library answers:

1. RQ1 (observation-only): for each incomplete year, the largest fully
   observed 30-day window is a valid lower bound L_y on that year's true H30.
2. RQ2 (benchmark): a baseline reconstructor (day-of-year climatology fill)
   is scored on the same finite-record slope, with the year-set and
   reconstruction error components separated.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from gapbench import (
    annual_h30,
    climatology_fill,
    finite_record_slope,
    generate_gaps,
    run_benchmark,
)

FIRST_YEAR = 2001
N_YEARS = 20
WINDOW = 30


def build_series() -> tuple[list[date], np.ndarray]:
    start = date(FIRST_YEAR, 1, 1)
    days = (date(FIRST_YEAR + N_YEARS, 1, 1) - start).days
    dates = [start + timedelta(days=i) for i in range(days)]
    doy = np.array([d.timetuple().tm_yday for d in dates])
    years = np.array([d.year for d in dates])
    rng = np.random.default_rng(20261102)
    seasonal = 12.0 * np.sin(2.0 * np.pi * (doy - 80) / 365.25)
    values = 15.0 + seasonal + 0.5 * (years - FIRST_YEAR) + rng.normal(0.0, 0.8, days)
    return dates, values


def main() -> None:
    dates, values = build_series()
    years = np.arange(FIRST_YEAR, FIRST_YEAR + N_YEARS)
    plan = generate_gaps(years, seed=0, length_days=60, burn_in_years=7, year_probability=0.45)

    masked = values.copy()
    masked[plan.mask] = np.nan
    truth = annual_h30(dates, values, window=WINDOW)
    observed = annual_h30(dates, masked, window=WINDOW)

    print("gapbench quickstart (dated API, v1.3.0)")
    print("---------------------------------------")
    print(f"series: {N_YEARS} years {FIRST_YEAR}-{FIRST_YEAR + N_YEARS - 1}, "
          f"{values.size} daily values; {plan.years.size} masked years "
          f"({plan.years.tolist()}), 60-day gaps")
    print(f"reference slope (complete truth): "
          f"{finite_record_slope(truth.years, truth.h30).slope_per_decade:+.4f} degC/decade")

    print("\nRQ1 - observed lower bounds L_y in incomplete years:")
    for year in plan.years:
        row = observed.years == year
        lower = observed.observed_bound[row][0]
        true_h30 = truth.h30[row][0]
        status = "valid" if lower <= true_h30 + 1e-9 else "VIOLATION"
        print(f"  {year}: L_y = {lower:7.3f} degC <= true H30 = {true_h30:7.3f} degC  [{status}]")

    print("\nRQ2 - baseline benchmark (climatology fill):")
    result = run_benchmark(dates, values, plan, lambda d, m, r: climatology_fill(d, m))
    decomposition = result.decomposition
    print(f"  annual errors (masked years): {np.round(result.annual_error, 3).tolist()}")
    print(f"  slope true {result.slope_true:+.4f}, estimated {result.slope_estimated:+.4f} "
          f"(selected-reference {result.slope_selected_reference:+.4f}) degC/decade")
    print(f"  decomposition: S={decomposition.S:+.4f} R={decomposition.R:+.4f} "
          f"E={decomposition.E:+.4f} (identity holds: {decomposition.identity_holds})")
    print("  note: R is ~0 here because complete-year screening drops the "
          "reconstructed years; only retained years enter the estimated slope.")


if __name__ == "__main__":
    main()
