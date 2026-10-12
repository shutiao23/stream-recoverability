"""Applying the rules to records that really have holes in them.

The v17 study never does this, because these station-years carry no truth and
therefore cannot be scored. They can still be *decided*, and the decisions are
what an archive is made of. This module builds, for every real station-year in
the panel, exactly the features the v17 screen conditions on, plus the
completed-year metric each deployable estimator would produce, so that three
questions can be asked without inventing a truth:

1. how often do the incumbent and the timing rule disagree;
2. what does a risk model fitted on the scored cases predict for each admitted
   set (an extrapolation, and labelled as one);
3. what happens to an archive-level number under each rule.

The training period for every estimator is the station's fully observed years,
which is what an analyst repairing an incomplete year actually holds.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from stream_recoverability.experiments.v17_fitness.estimators import (
    StationModels,
    coldest_window_mean,
    donor_coverage,
    exceedance_days,
    hottest_window_mean,
    linear_interp_fill,
    observed_days_metric,
    usable_donors,
)
from stream_recoverability.experiments.v17_fitness.cases import (
    WARM_MONTHS,
    deseasonalized_correlations,
)
from stream_recoverability.experiments.v17_fitness.outages import peak_overlap_fraction
from stream_recoverability.experiments.v17_fitness.panel import air_series_for, load_network_panel
from stream_recoverability.experiments.v17_fitness.paths import (
    EXCEEDANCE_THRESHOLDS_C,
    HOTTEST_WINDOW_DAYS,
    donor_regime,
)
from stream_recoverability.experiments.v18_closure.archive import (
    StationJob,
    climatological_peak_doys,
    station_jobs,
)
from stream_recoverability.experiments.v18_closure.paths import MIN_DAYS_IN_YEAR

FILL_ESTIMATORS = ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge")
SHORT_GAP_DAYS = 30
MIN_COMPLETE_YEARS = 2


def policy_choice(row: dict, available: dict[str, bool]) -> str:
    """The information-conditioned policy, keyed on availability rather than error.

    `policies.information_conditioned_choice` decides from which `abserr_`
    columns are populated, which presumes a truth. The same ladder is applied
    here to which fills actually completed the year.
    """

    choice = "doy_climatology"
    if available.get("smooth_climatology"):
        choice = "smooth_climatology"
    short_interior = (
        int(row["longest_run"]) <= SHORT_GAP_DAYS
        and bool(row["left_flank"])
        and bool(row["right_flank"])
        and available.get("linear_interp", False)
    )
    if short_interior:
        choice = "linear_interp"
    if row["air_available"] and available.get("air_ridge"):
        choice = "air_ridge"
    if int(row["n_visible_donors"]) > 0 and available.get("donor_ridge"):
        choice = "donor_ridge"
    return choice


def real_year_rows(job: StationJob) -> list[dict]:
    """Every calendar year this station covers, decided but not scored."""

    try:
        daily = load_network_panel(job.network_id, job.source_root)
    except (FileNotFoundError, ValueError, KeyError):
        return []
    daily = daily.copy()
    daily.columns = [str(c) for c in daily.columns]
    if job.station_id not in daily.columns:
        return []
    target = pd.to_numeric(daily[job.station_id], errors="coerce")
    if target.notna().sum() < 400:
        return []
    span = slice(target.first_valid_index(), target.last_valid_index())
    target = target.loc[span]
    daily = daily.loc[span]
    donors = daily.drop(columns=[job.station_id])
    air = air_series_for(job.network_id, job.station_id, daily.index)

    by_year = target.groupby(target.index.year)
    complete_years = np.array(
        [int(year) for year, block in by_year if bool(block.notna().all()) and len(block) >= 365]
    )
    if len(complete_years) < MIN_COMPLETE_YEARS:
        return []
    peak_doys = climatological_peak_doys(target, complete_years)
    if peak_doys is None:
        return []

    train_mask = pd.Series(np.isin(daily.index.year, complete_years), index=daily.index)
    models = StationModels(target=target, donors=donors, air=air, train_mask=train_mask)
    correlations = deseasonalized_correlations(target, donors, train_mask)

    train_values = target.loc[train_mask].dropna()
    if len(train_values) < 365:
        return []
    train_doy = pd.Series(train_values.index.dayofyear, index=train_values.index)
    train_resid_sd = float((train_values - train_values.groupby(train_doy).transform("mean")).std())
    clim_grid = models.smooth_climatology(daily.index[train_mask])
    seasonal_amplitude = float(np.nanmax(clim_grid) - np.nanmin(clim_grid)) if len(clim_grid) else float("nan")
    complete_metrics = [
        hottest_window_mean(target.loc[target.index.year == int(year)].to_numpy(dtype=float))
        for year in complete_years
    ]
    train_metric_sd = float(np.std(complete_metrics, ddof=1)) if len(complete_metrics) > 1 else float("nan")
    record_years = int(target.index.year.nunique())

    rows: list[dict] = []
    for year, block in target.groupby(target.index.year):
        if len(block) < MIN_DAYS_IN_YEAR:
            continue
        year_index = block.index
        observed = block.to_numpy(dtype=float)
        mask = ~np.isfinite(observed)
        months = year_index.month.to_numpy()
        warm = np.isin(months, WARM_MONTHS)
        if mask.any():
            edges = np.diff(np.concatenate([[0], mask.view(np.int8), [0]]))
            starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0]
            longest_index = int(np.argmax(ends - starts))
            longest_run = int((ends - starts)[longest_index])
            longest_run_month = int(months[starts[longest_index]])
            n_runs = int(len(starts))
        else:
            longest_run, longest_run_month, n_runs = 0, 7, 0

        visible = usable_donors(donors, year_index, mask) if mask.any() else ()
        coverage = donor_coverage(donors, year_index, mask) if mask.any() else pd.Series(dtype=float)
        clim_year = models.smooth_climatology(year_index)
        observed_peak = observed_days_metric(observed, window=HOTTEST_WINDOW_DAYS)
        strict_observed = hottest_window_mean(observed)

        row: dict[str, object] = {
            "network_id": job.network_id,
            "station_id": job.station_id,
            "provider": job.provider,
            "year": int(year),
            "n_days": int(len(block)),
            "complete": bool(not mask.any()),
            "total_missing": int(mask.sum()),
            "missing_fraction": float(mask.mean()),
            "longest_run": longest_run,
            "longest_run_month": longest_run_month,
            "n_runs": n_runs,
            "peak_overlap": peak_overlap_fraction(year_index, mask, peak_doys),
            "warm_observed_fraction": float((~mask & warm).sum() / max(1, warm.sum())),
            "n_visible_donors": int(len(visible)),
            "donor_regime": donor_regime(len(visible)),
            "donor_coverage_mean": float(coverage.mean()) if len(coverage) else float("nan"),
            "train_resid_sd": train_resid_sd,
            "seasonal_amplitude": seasonal_amplitude,
            "train_metric_sd": train_metric_sd,
            "n_complete_years": int(len(complete_years)),
            "record_years": record_years,
            "clim_peak": float(hottest_window_mean(clim_year)),
            "observed_peak": float(observed_peak),
            "strict_observed_peak": float(strict_observed),
            "has_complete_window": bool(np.isfinite(strict_observed)),
            "left_flank": bool(not mask[0]),
            "right_flank": bool(not mask[-1]),
            "air_available": bool(air is not None and np.isfinite(models.air_predict(year_index)).any()),
        }
        row["observed_peak_margin"] = (
            float(observed_peak - row["clim_peak"]) if np.isfinite(observed_peak) else float("nan")
        )
        if len(correlations) and visible:
            visible_corr = correlations.reindex(list(visible)).dropna()
        else:
            visible_corr = pd.Series(dtype=float)
        row["donor_corr_mean"] = float(visible_corr.mean()) if len(visible_corr) else float("nan")
        row["donor_corr_max"] = float(visible_corr.max()) if len(visible_corr) else float("nan")
        row["donor_corr_min"] = float(visible_corr.min()) if len(visible_corr) else float("nan")

        if not mask.any():
            completed = observed
            row["policy_choice"] = "observed_days"
            row["metric_policy"] = float(hottest_window_mean(observed))
            row["metric_observed_days"] = float(observed_peak)
            row["annual_mean_policy"] = float(np.nanmean(observed))
            for threshold in EXCEEDANCE_THRESHOLDS_C:
                row[f"exceed_{int(threshold)}_policy"] = exceedance_days(completed, threshold)
            rows.append(row)
            continue

        donor_fit = models.donor_ridge(visible) if visible else None
        fits = {
            "doy_climatology": models.doy_climatology(year_index),
            "smooth_climatology": models.smooth_climatology(year_index),
            "linear_interp": linear_interp_fill(observed),
            "donor_ridge": (
                models.donor_predict(donor_fit, year_index)
                if donor_fit is not None
                else np.full(len(year_index), np.nan)
            ),
            "air_ridge": models.air_predict(year_index) if air is not None else np.full(len(year_index), np.nan),
        }
        completions: dict[str, np.ndarray] = {}
        available: dict[str, bool] = {}
        for name, fill in fits.items():
            candidate = observed.copy()
            candidate[mask] = np.asarray(fill, dtype=float)[mask]
            ok = bool(np.isfinite(candidate).all())
            available[name] = ok
            if ok:
                completions[name] = candidate
                row[f"metric_{name}"] = float(hottest_window_mean(candidate))

        choice = policy_choice(row, available)
        completed = completions.get(choice)
        row["policy_choice"] = choice
        row["metric_observed_days"] = float(observed_peak)
        if completed is None:
            row["metric_policy"] = float("nan")
            row["annual_mean_policy"] = float("nan")
            for threshold in EXCEEDANCE_THRESHOLDS_C:
                row[f"exceed_{int(threshold)}_policy"] = float("nan")
        else:
            row["metric_policy"] = float(hottest_window_mean(completed))
            row["annual_mean_policy"] = float(np.nanmean(completed))
            row["coldest30_policy"] = float(coldest_window_mean(completed))
            for threshold in EXCEEDANCE_THRESHOLDS_C:
                row[f"exceed_{int(threshold)}_policy"] = exceedance_days(completed, threshold)
        rows.append(row)
    return rows


def real_year_table(workers: int = 32) -> pd.DataFrame:
    jobs = station_jobs()
    rows: list[dict] = []
    if workers <= 1:
        for job in jobs:
            rows.extend(real_year_rows(job))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for block in pool.map(real_year_rows, jobs, chunksize=2):
                rows.extend(block)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["network_id", "station_id", "year"]).reset_index(drop=True)
