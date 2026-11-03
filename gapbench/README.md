# gapbench

`gapbench` is a small, standalone library for **leakage-safe benchmarking of gap
handling in annual heat extremes and river-temperature trends**. It distills the
reusable measurement ideas from a larger stream-recoverability study into a
dependency-light package: observed-window support, outcome-blind calendar-year
selection, finite-record OLS trends, slope-error decomposition, group-disjoint
splits, and a contiguous masking utility.

The package is deliberately not a copy of the research pipeline. It contains no
restricted observations, no fitted recovery models, and no dependency on the
original `stream_recoverability` package.

## Install

From the repository root:

```bash
pip install -e gapbench
```

This installs `gapbench` 1.2.0 with Python >= 3.10, NumPy, and pandas. For tests:

```bash
pip install -e "gapbench[test]"
python -m pytest -q gapbench/tests
```

Run the self-contained example from a source checkout or after installation:

```bash
python gapbench/examples/quickstart.py
```

## API

| Function | Returns | Purpose |
| --- | --- | --- |
| `observed_window_bound(series, window=30)` | `ObservedWindow(value, start, end)` | Maximum mean over fully observed contiguous windows. `start`/`end` are half-open positional bounds; value is `nan` and bounds are `None` if no window is complete. |
| `finite_record_slope(years, values)` | `SlopeFit(slope_per_decade, intercept, standard_error, n)` | Complete-case OLS trend per decade, intercept, classical slope SE, and finite pair count. |
| `select_years(years, complete_years, method="cdf", count=None)` | `numpy.ndarray` | Outcome-blind selection that always retains every complete year and fills the remaining slots by a CDF or Sxx calendar-geometry objective. |
| `decompose_slope_error(reference_slope, selected_years, annual_truth, annual_estimate)` | `SlopeErrorDecomposition` | Year-set error `S`, reconstruction error `R`, total error `E = S + R`, cross term `2*S*R`, and an identity check. |
| `group_splits(groups, n_splits=5, seed=0)` | `list[tuple[train, test]]` | Deterministic, group-disjoint train/test folds. |
| `mask_archive(values, start, length)` | `numpy.ndarray` | Copy of the values with a contiguous `[start, start+length)` segment set to `nan`. |

All public objects are exported from `gapbench` and documented in
`gapbench/core.py`.

### `select_years` semantics

`count` is the **total** number of years to retain, including every complete
year. The default `count=None` retains all candidate years. For a non-trivial
selection, `count` must be at least the number of complete years and at most the
number of candidate years.

* `method="cdf"` minimises the mean squared difference between the selected and
  full empirical year CDFs on the integer-year grid.
* `method="sxx"` maximises the centred year spread
  `sum(((year - mean_year) / 10) ** 2)`.
* Primary ties are compared at 14 decimal places. Remaining ties use the other
  objective, then the lexicographic order of the chosen incomplete years.

The search is exhaustive over incomplete-year subsets and raises a clear error
above 2,000,000 candidate subsets. This is intended for archive-scale year grids,
not combinatorially large calendar ranges.

## 30-minute quickstart

The example in `gapbench/examples/quickstart.py` is the fastest end-to-end tour.
It builds a synthetic 20-year daily series with a 60-day outage and three shorter
outages, masks the missing segments, and then:

1. measures the best fully observed 30-day window;
2. selects 18 years by the CDF and Sxx rules, always retaining the 16 complete
   years;
3. computes the full-record reference slope and decomposes the slope error for
   each selected year set.

Run it with:

```bash
python gapbench/examples/quickstart.py
```

Expected shape of the output:

```text
gapbench quickstart
-------------------
series: 7300 daily values, 20 years (2001-2020); 4 gaps, longest 60 days
observed H30 bound: 27.710 degC at positions 6363..6393 (2018 DOY 159-2018 DOY 188)
masked: 105/7300 values (1.44%)
complete years: 16; incomplete: [2008, 2012, 2015, 2019]
reference slope (full complete truth): 0.3280 degC/decade
reference slope classical SE: 0.0503 degC/decade
CDF selection (n=18): [2001, 2002, 2003, 2004, 2005, 2006, 2007, 2009, 2010, 2011, 2012, 2013, 2014, 2016, 2017, 2018, 2019, 2020]
Sxx selection (n=18): [2001, 2002, 2003, 2004, 2005, 2006, 2007, 2009, 2010, 2011, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020]
CDF decomposition: S=-0.0087 R=-0.0060 E=-0.0148 2*S*R=+0.0001 identity_ok=True
Sxx decomposition: S=-0.0029 R=-0.0040 E=-0.0069 2*S*R=+0.0000 identity_ok=True
```

The example runs in well under one second and uses only synthetic data generated
inside the script. Replace the synthetic generator with your annual summaries to
apply the same sequence to real archives.

A minimal manual flow looks like this:

```python
import numpy as np
from gapbench import (
    decompose_slope_error,
    finite_record_slope,
    mask_archive,
    observed_window_bound,
    select_years,
)

daily = np.array([...])                    # ordered daily values
masked = mask_archive(daily, start=200, length=60)
bound = observed_window_bound(masked, window=30)
print(bound.value, bound.start, bound.end)

years = np.arange(2001, 2021)
complete = np.array([2001, 2002, 2003, 2004, 2005, 2006, 2007, 2009, 2010,
                     2011, 2013, 2014, 2016, 2017, 2018, 2020])
selected = select_years(years, complete, method="cdf", count=18)

annual_truth = np.array([...])             # aligned with selected
annual_estimate = np.array([...])          # aligned with selected
reference = finite_record_slope(years, annual_truth)
result = decompose_slope_error(
    reference.slope_per_decade, selected, annual_truth, annual_estimate
)
print(result.S, result.R, result.E, result.identity_ok)
```

## Leakage contract

`gapbench` enforces leakage safety by construction where it can and documents it
where it cannot:

1. **No outcome argument in selection.** `select_years` accepts only calendar
   years, the fixed complete-year labels, the objective name, and the target
   count. It has no temperature, prediction, reconstruction-error, or
   gap-severity parameter.
2. **Calendar-only objectives.** CDF and Sxx are computed from integer year
   labels. The full-year reference CDF and the complete-year set are fixed before
   any outcome is consulted.
3. **Scoring is separate.** `decompose_slope_error` is the only function that
   sees annual complete-data truth and estimated outcomes. It is an evaluation
   step and must be called after selection is frozen.
4. **Groups stay together.** `group_splits` assigns every record from a group to
   exactly one test fold, preventing correlated stations, rivers, or replicate
   archives from appearing on both sides of a split.
5. **Do not encode outcomes in labels.** The contract cannot detect a user who
   derives `complete_years` or candidate years from temperature values. Build
   the year pool and completeness flags from data availability only, before
   looking at the target.

`observed_window_bound` uses observed values by design: it reports what the
observed record can support. It does not consult hidden or reconstructed values.

## Scope and limitations

* The library targets **annual records**: one outcome per calendar year, integer
  years for selection, and complete-case OLS for trends. It is not a general
  time-series or spatial-statistics package.
* `finite_record_slope` uses classical homoskedastic OLS standard errors. It does
  not correct for autocorrelation, heteroskedasticity, model selection, or
  multiple comparisons. Use it as a descriptive finite-record summary, not as a
  climate-trend significance test.
* `S`, `R`, and `E` are an arithmetic decomposition. `S` is the change caused by
  using a different year set and `R` is the remaining reconstruction difference;
  the signed cross term `2*S*R` can offset squared errors. These are not causal
  attributions and should not be reported as independent variance shares.
* CDF and Sxx are calendar-geometry heuristics. They do not encode scientific
  beliefs about which years matter, and other outcome-blind rules are possible.
* Selection is exhaustive and capped at 2,000,000 subsets. Larger problems need a
  different optimizer; the cap is an intentional guardrail.
* `group_splits` balances folds by sample count. It does not stratify on outcomes
  or guarantee equal fold sizes when groups are uneven.
* The package ships only synthetic example code. It does not include the study's
  restricted observations, frozen results, or recovery models.

## License

MIT. See `LICENSE`.
