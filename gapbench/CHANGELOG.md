# Changelog

## 1.3.0 (2026-11-03)

### Added
- `gapbench.benchmark` module with a dated benchmark layer:
  - `annual_h30(dates, values, window=30)` returns per-year H30, the observed
    lower bound `L_y` for incomplete years and completeness flags, with leap
    year handling and duplicate-date validation;
  - `generate_gaps(years, seed, length_days, ...)` draws reproducible
    controlled gaps (per-year probability, burn-in, warm-season start range)
    using one spawned random stream per year so designs are stable under
    exclusion;
  - `climatology_fill`, `linear_interpolation_fill` and `ar1_bridge_paths`
    dependency-free baselines (the AR(1) bridge uses per-path spawned streams,
    so any prefix of an ensemble is reproducible);
  - `run_benchmark(dates, values, gap_plan, reconstructor)` scores any
    user-supplied reconstructor and returns annual errors, reference and
    estimated slopes and the `S/R/E` decomposition.
- 9 new tests (22 total), including leap-year and shuffled-input handling,
  bound validity `L_y <= H30`, prefix invariance of the bridge ensemble and
  decomposition identity checks through the runner.
- CHANGELOG (this file).

### Changed
- Quickstart rewritten around the dated API: it now demonstrates the
  observation-only result (per-incomplete-year `L_y` versus true H30) and a
  baseline benchmark run with the decomposition.
- Dropped the unused `pandas` dependency; the library is NumPy-only.

## 1.2.0 (2026-11-03)

Initial extracted release: six outcome-blind primitives (observed-window
bound, finite-record slope, calendar-only year selection, slope-error
decomposition, group-disjoint splits, archive masking), 13 tests, a synthetic
quickstart and documentation.
