"""Published completeness rules applied to a case's missing-day mask.

Each rule returns True when the year would be used. Rules that only count days
ignore where the gap falls; peak-season rules look at the summer window.

Round 2 adapts the peak-season rules to each station: their original calendar
windows (written for Northern Hemisphere rivers peaking around the source
median, day 211) are moved by the difference between the station's
climatological peak centre and that reference, and warm-season rules use the
station's five climatologically hottest months. Masks of Southern Hemisphere
stations are already on the July-June hot-year calendar. The original calendar
windows on the hot-year calendar are kept as ``*_as_written`` variants.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import wrr_tr_common as T

# Original windows as day-of-year ranges of a non-leap year (inclusive).
PEAK_WINDOWS = {
    "oregon_jas": (182, 273),
    "norwest_aug": (213, 243),
    "beaufort_julaug": (182, 243),
    "dunham_jul15_sep15": (196, 258),
}


def _months(text, default=(5, 6, 7, 8, 9)) -> tuple[int, ...]:
    if isinstance(text, str) and text:
        return tuple(int(value) for value in text.split(";"))
    return default


def _window(n_days: int, first: int, last: int, shift: int) -> np.ndarray:
    days = np.arange(1, n_days + 1)
    return (days >= first + shift) & (days <= last + shift)


def mask_features(cases: pd.DataFrame) -> pd.DataFrame:
    rows = []
    hot_year = T.SEASON_MODE == "hot_year" and "peak_center_doy" in cases
    reference = int(T.settings().get("rule_reference_peak_doy", 211))
    warm_column = cases["warm_months"] if "warm_months" in cases else pd.Series("", index=cases.index)
    peak_column = cases["peak_center_doy"] if "peak_center_doy" in cases else pd.Series(reference, index=cases.index)
    for runs, year, warm_text, peak in zip(cases.mask_runs, cases.year, warm_column, peak_column):
        index = pd.date_range(f"{int(year)}-01-01", f"{int(year)}-12-31", freq="D")
        mask = T.mask_from_runs(runs, len(index))
        month = index.month.to_numpy()
        missing_by_month = np.bincount(month[mask], minlength=13)[1:]
        consecutive_by_month = np.zeros(12, dtype=int)
        for m in range(1, 13):
            sub = mask[month == m]
            longest = 0
            run = 0
            for value in sub:
                run = run + 1 if value else 0
                longest = max(longest, run)
            consecutive_by_month[m - 1] = longest
        starts = np.flatnonzero(mask & ~np.r_[False, mask[:-1]])
        ends = np.flatnonzero(mask & ~np.r_[mask[1:], False]) + 1
        warm = np.isin(month, list(_months(warm_text) if hot_year else (5, 6, 7, 8, 9)))
        warm_mask = mask & warm
        warm_starts = np.flatnonzero(warm_mask & ~np.r_[False, warm_mask[:-1]])
        warm_ends = np.flatnonzero(warm_mask & ~np.r_[warm_mask[1:], False]) + 1
        window7 = np.convolve(mask.astype(int), np.ones(7, dtype=int), mode="valid")
        row = {
            "n_observed": int((~mask).sum()), "n_missing": int(mask.sum()),
            "min_month_observed": int((np.bincount(month, minlength=13)[1:] - missing_by_month).min()),
            "max_month_missing": int(missing_by_month.max()), "max_month_consecutive": int(consecutive_by_month.max()),
            "longest_gap": int((ends - starts).max()) if len(starts) else 0,
            "longest_warm_gap": int((warm_ends - warm_starts).max()) if len(warm_starts) else 0,
            "max_missing_in_7d": int(window7.max()),
        }
        shift = int(peak) - reference if hot_year and np.isfinite(peak) else 0
        for name, (first, last) in PEAK_WINDOWS.items():
            anchored = _window(len(index), first, last, shift)
            written = _window(len(index), first, last, 0)
            row[f"{name}_observed_fraction"] = float((~mask[anchored]).mean())
            row[f"{name}_observed_fraction_as_written"] = float((~mask[written]).mean())
        rows.append(row)
    return pd.DataFrame(rows, index=cases.index)


def fixed_rules(features: pd.DataFrame, cases: pd.DataFrame, as_written: bool = False) -> dict[str, pd.Series]:
    """Point rules: name -> accept. Peak-season rules are peak-anchored unless as_written."""

    f = features
    rules = {
        "R1_complete_year (USGS/SWToolbox)": f.n_missing.eq(0),
        "R1_usgs_indicator_311d_24pm": (f.n_observed >= 311) & (f.min_month_observed >= 24),
        "R1_usgs_indicator_strict_7d": (f.n_observed >= 311) & (f.min_month_observed >= 26) & (f.max_missing_in_7d <= 1),
        "R1_wmo_11_5": (f.max_month_missing < 11) & (f.max_month_consecutive < 5),
        "R1_etccdi_15_3": (f.n_missing <= 15) & (f.max_month_missing <= 3),
        "R1_gsim_350d": f.n_observed >= 350,
        "R1_michel_no_gap_over_14d": f.longest_gap <= 14,
        "R1_johnson_gap_le_49d": f.longest_gap <= 49,
        "R2_oregon_jas_80pct": f.oregon_jas_observed_fraction >= 0.8,
        "R2_norwest_aug_90pct": f.norwest_aug_observed_fraction >= 0.9,
        "R2_beaufort_julaug_complete": f.beaufort_julaug_observed_fraction >= 1.0,
        "R2_dunham_jul15_sep15_complete": f.dunham_jul15_sep15_observed_fraction >= 1.0,
        "R2_warm_gap_le_7d": f.longest_warm_gap <= 7,
        "R2_warm_gap_le_14d": f.longest_warm_gap <= 14,
        "R2_warm_gap_le_30d": f.longest_warm_gap <= 30,
    }
    if as_written:
        rules.update({
            "R2_oregon_jas_80pct_as_written": f.oregon_jas_observed_fraction_as_written >= 0.8,
            "R2_norwest_aug_90pct_as_written": f.norwest_aug_observed_fraction_as_written >= 0.9,
            "R2_beaufort_julaug_complete_as_written": f.beaufort_julaug_observed_fraction_as_written >= 1.0,
            "R2_dunham_jul15_sep15_complete_as_written": f.dunham_jul15_sep15_observed_fraction_as_written >= 1.0,
        })
    return rules


def parametric_scores(features: pd.DataFrame, cases: pd.DataFrame) -> dict[str, pd.Series]:
    """Rules with a free threshold, as scores where lower means accept first."""

    from scipy.stats import norm

    lower_bound = cases["observed_lower_bound__observed_days"]
    # Standardised position of the best fully observed window in the training H30 distribution.
    position = (lower_bound - cases.train_h30_mean) / cases.train_h30_sd.replace(0, np.nan)
    return {
        "R1_annual_missing_fraction": features.n_missing / (features.n_missing + features.n_observed),
        "R2_warm_missing_fraction": 1 - cases.warm_observed_fraction,
        "R3_observed_lower_bound (NRFA-type)": pd.Series(-norm.cdf(position), index=cases.index).fillna(0.0),
    }
