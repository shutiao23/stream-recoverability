"""Step 3 — build the case table.

One case is (station, calendar year, outage realization). For each case every
supported estimator produces a completed year, the completed year produces the
thermal metric, and the metric produces a signed and absolute error against the
fully observed truth. Alongside the errors we record only features that are
visible at decision time; the split between visible and hidden is enforced here
rather than by convention.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.experiments.wrr_revision.failures import natural_gap_geometry
from stream_recoverability.experiments.v17_fitness.estimators import (
    StationModels,
    coldest_window_mean,
    exceedance_days,
    hottest_window_mean,
    linear_interp_fill,
    observed_days_metric,
    usable_donors,
    donor_coverage,
)
from stream_recoverability.experiments.v17_fitness.outages import (
    climatological_peak_window,
    design_for_year,
    peak_overlap_fraction,
)
from stream_recoverability.experiments.v17_fitness.panel import air_series_for, load_network_panel
from stream_recoverability.experiments.v17_fitness.paths import (
    stable_seed,
    EXCEEDANCE_THRESHOLDS_C,
    SENSOR_NOISE_C,
    HOTTEST_WINDOW_DAYS,
    REALIZATIONS_PER_STATION_YEAR,
    donor_regime,
)

FILL_ESTIMATORS = ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge")
ALL_ESTIMATORS = ("observed_days",) + FILL_ESTIMATORS
WARM_MONTHS = (5, 6, 7, 8, 9)


def deseasonalized_correlations(
    target: pd.Series, donors: pd.DataFrame, train_mask: pd.Series
) -> pd.Series:
    """Training-period correlation of day-of-year residuals. Visible at decision time."""

    y = target.loc[train_mask].dropna()
    if len(y) < 120 or donors.empty:
        return pd.Series(dtype=float)
    doy = pd.Series(y.index.dayofyear, index=y.index)
    residual = y - y.groupby(doy).transform("mean")
    out: dict[str, float] = {}
    block = donors.loc[train_mask]
    for name in block.columns:
        series = pd.to_numeric(block[name], errors="coerce").dropna()
        if len(series) < 120:
            continue
        d = pd.Series(series.index.dayofyear, index=series.index)
        donor_residual = series - series.groupby(d).transform("mean")
        aligned = pd.concat([residual, donor_residual], axis=1, keys=["t", "d"]).dropna()
        if len(aligned) < 120:
            continue
        out[str(name)] = float(aligned["t"].corr(aligned["d"]))
    return pd.Series(out, dtype=float)


def station_geometry_pool(daily: pd.DataFrame) -> pd.DataFrame:
    """Real outage runs anywhere in this network's record."""

    frames = []
    for column in daily.columns:
        geometry = natural_gap_geometry(pd.to_numeric(daily[column], errors="coerce"))
        if not geometry.empty:
            frames.append(geometry)
    if not frames:
        return pd.DataFrame(columns=["gap_length", "month"])
    pooled = pd.concat(frames, ignore_index=True)
    pooled["month"] = pd.to_datetime(pooled["gap_start"]).dt.month.astype(int)
    pooled["gap_length"] = pd.to_numeric(pooled["gap_length"], errors="coerce").astype(int)
    return pooled.loc[pooled["gap_length"].between(3, 330), ["gap_length", "month"]]


def build_station_cases(job: dict) -> pd.DataFrame:
    """Every scored case contributed by one station. Picklable worker entry point."""

    network_id = str(job["network_id"])
    station_id = str(job["station_id"])
    try:
        daily = load_network_panel(network_id, str(job["source_root"]))
    except (FileNotFoundError, ValueError, KeyError):
        return pd.DataFrame()
    if station_id not in [str(c) for c in daily.columns]:
        return pd.DataFrame()
    daily = daily.copy()
    daily.columns = [str(c) for c in daily.columns]
    target = pd.to_numeric(daily[station_id], errors="coerce")
    donors = daily.drop(columns=[station_id])
    air = air_series_for(network_id, station_id, daily.index)
    pool = station_geometry_pool(daily)

    complete_years = tuple(int(y) for y in job["complete_years"])
    if len(complete_years) < 2:
        return pd.DataFrame()
    protocol = str(job.get("fit_protocol", "leave_one_year_out"))

    record_years = int(target.index.year.nunique())
    rows: list[dict] = []

    for year in complete_years:
        year_mask = target.index.year == int(year)
        year_index = daily.index[year_mask]
        truth = target.loc[year_mask].to_numpy(dtype=float)
        if not np.isfinite(truth).all() or len(truth) < 360:
            continue
        truth_metric = hottest_window_mean(truth)
        if not np.isfinite(truth_metric):
            continue

        if protocol == "strictly_prior_years":
            # An archivist who repairs as the record accrues, rather than one
            # who repairs an old outage with the whole record in hand.
            if sum(1 for other in complete_years if other < int(year)) < 2:
                continue
            train_mask = pd.Series(daily.index.year < int(year), index=daily.index)
            peak_source = target.loc[target.index.year < int(year)]
        else:
            train_mask = pd.Series(~year_mask, index=daily.index)
            peak_source = target.loc[target.index.year != int(year)]
        models = StationModels(target=target, donors=donors, air=air, train_mask=train_mask)
        peak_doys = climatological_peak_window(peak_source, exclude_year=None)

        # Training-period station diagnostics, all visible at decision time.
        train_values = target.loc[train_mask].dropna()
        if len(train_values) < 365:
            continue
        train_doy = pd.Series(train_values.index.dayofyear, index=train_values.index)
        train_residual = train_values - train_values.groupby(train_doy).transform("mean")
        train_resid_sd = float(train_residual.std())
        clim_grid = models.smooth_climatology(daily.index[train_mask])
        seasonal_amplitude = float(np.nanmax(clim_grid) - np.nanmin(clim_grid)) if len(clim_grid) else float("nan")
        clim_year = models.smooth_climatology(year_index)
        clim_peak = hottest_window_mean(clim_year)
        train_year_metrics = []
        for other in complete_years:
            if int(other) == int(year):
                continue
            if protocol == "strictly_prior_years" and int(other) > int(year):
                continue
            block = target.loc[target.index.year == int(other)].to_numpy(dtype=float)
            if np.isfinite(block).all() and len(block) >= 360:
                train_year_metrics.append(hottest_window_mean(block))
        train_metric_sd = float(np.std(train_year_metrics, ddof=1)) if len(train_year_metrics) > 1 else float("nan")

        correlations = deseasonalized_correlations(target, donors, train_mask)

        rng = np.random.default_rng(stable_seed(network_id, station_id, int(year), protocol))
        realizations = design_for_year(
            year_index, peak_doys, pool, rng=rng, n_empirical=max(1, REALIZATIONS_PER_STATION_YEAR // 3)
        )

        for realization in realizations:
            mask = realization.mask(len(year_index))
            if not mask.any() or mask.all():
                continue
            observed = truth.copy()
            observed[mask] = np.nan

            visible = usable_donors(donors, year_index, mask)
            coverage = donor_coverage(donors, year_index, mask)
            fits: dict[str, np.ndarray] = {}
            fits["doy_climatology"] = models.doy_climatology(year_index)
            fits["smooth_climatology"] = models.smooth_climatology(year_index)
            fits["linear_interp"] = linear_interp_fill(observed)
            donor_fit = models.donor_ridge(visible) if visible else None
            fits["donor_ridge"] = (
                models.donor_predict(donor_fit, year_index) if donor_fit is not None else np.full(len(year_index), np.nan)
            )
            fits["air_ridge"] = models.air_predict(year_index) if air is not None else np.full(len(year_index), np.nan)

            def _metrics(values: np.ndarray) -> dict[str, float]:
                """Every derived metric this study reports, on one completed year.

                ``hottest7`` is the seven-day analogue of the peak. Much
                regulatory practice uses a seven-day window rather than a
                thirty-day one, and a shorter extreme is more localised in
                time, so the timing mechanism predicts a stronger effect there.
                """

                hot = hottest_window_mean(values)
                cold = coldest_window_mean(values)
                return {
                    "hottest30": hot,
                    "hottest7": hottest_window_mean(values, window=7),
                    "annual_mean": float(np.nanmean(values)) if np.isfinite(values).any() else float("nan"),
                    "coldest30": cold,
                    "amplitude30": hot - cold if np.isfinite(hot) and np.isfinite(cold) else float("nan"),
                }

            truth_metrics = _metrics(truth)
            # Reference series carry instrument error of order 0.1-0.2 C. The
            # replica below perturbs the reference the scoring uses, so the
            # sensitivity of every conclusion to that error can be measured
            # rather than assumed away.
            noise_rng = np.random.default_rng(stable_seed(network_id, station_id, int(year), "sensor"))
            noisy_truth = truth + noise_rng.normal(0.0, SENSOR_NOISE_C, size=truth.shape)
            noisy_truth_metric = hottest_window_mean(noisy_truth)

            row: dict[str, object] = {
                "network_id": network_id,
                "station_id": station_id,
                "provider": str(job["provider"]),
                "split_role": str(job["split_role"]),
                "regulation_status": str(job["regulation_status"]),
                "year": int(year),
                "fit_protocol": protocol,
                "realization_id": realization.realization_id,
                "arm": realization.arm,
                "overlap_class": realization.overlap_class,
                "truth_metric": float(truth_metric),
            }
            for metric_name, metric_value in truth_metrics.items():
                row[f"truth_{metric_name}"] = float(metric_value)
            row["truth_hottest30_noisy"] = float(noisy_truth_metric)
            for threshold in EXCEEDANCE_THRESHOLDS_C:
                row[f"truth_exceed_{int(threshold)}"] = exceedance_days(truth, threshold)

            # ---- decision-time visible features ----
            months = year_index.month.to_numpy()
            warm = np.isin(months, WARM_MONTHS)
            row["n_runs"] = int(realization.n_runs)
            row["total_missing"] = int(realization.total_missing)
            row["missing_fraction"] = float(mask.sum() / len(mask))
            row["longest_run"] = int(realization.longest_run)
            longest_start = int(max(realization.runs, key=lambda item: item[1])[0])
            row["longest_run_month"] = int(months[longest_start])
            row["peak_overlap"] = peak_overlap_fraction(year_index, mask, peak_doys)
            row["warm_observed_fraction"] = float((~mask & warm).sum() / max(1, warm.sum()))
            row["n_visible_donors"] = int(len(visible))
            row["donor_regime"] = donor_regime(len(visible))
            row["donor_coverage_mean"] = float(coverage.mean()) if len(coverage) else float("nan")
            if len(correlations):
                visible_corr = correlations.reindex(list(visible)).dropna() if visible else pd.Series(dtype=float)
                row["donor_corr_mean"] = float(visible_corr.mean()) if len(visible_corr) else float("nan")
                row["donor_corr_max"] = float(visible_corr.max()) if len(visible_corr) else float("nan")
                row["donor_corr_min"] = float(visible_corr.min()) if len(visible_corr) else float("nan")
            else:
                row["donor_corr_mean"] = float("nan")
                row["donor_corr_max"] = float("nan")
                row["donor_corr_min"] = float("nan")
            row["air_available"] = bool(air is not None and np.isfinite(fits["air_ridge"]).any())
            row["train_resid_sd"] = train_resid_sd
            row["seasonal_amplitude"] = seasonal_amplitude
            row["train_metric_sd"] = train_metric_sd
            row["n_complete_years"] = int(len(complete_years))
            row["record_years"] = record_years
            row["clim_peak"] = float(clim_peak)
            observed_peak = observed_days_metric(observed, window=HOTTEST_WINDOW_DAYS)
            row["observed_peak"] = float(observed_peak)
            row["observed_peak_margin"] = float(observed_peak - clim_peak) if np.isfinite(observed_peak) else float("nan")
            strict_observed = hottest_window_mean(observed)
            row["strict_observed_peak"] = float(strict_observed)
            row["has_complete_window"] = bool(np.isfinite(strict_observed))
            row["left_flank"] = bool(not mask[0])
            row["right_flank"] = bool(not mask[-1])

            # ---- estimator outcomes ----
            row["metric_observed_days"] = float(observed_peak)
            observed_series = pd.Series(observed, dtype=float)
            observed_metrics = {
                "hottest30": observed_peak,
                "hottest7": observed_days_metric(observed, window=7),
                "annual_mean": float(observed_series.mean()),
                "coldest30": coldest_window_mean(observed, min_coverage=0.8),
            }
            observed_metrics["amplitude30"] = (
                observed_metrics["hottest30"] - observed_metrics["coldest30"]
                if np.isfinite(observed_metrics["hottest30"]) and np.isfinite(observed_metrics["coldest30"])
                else float("nan")
            )
            for metric_name, metric_value in observed_metrics.items():
                row[f"{metric_name}_observed_days"] = float(metric_value)
                truth_value = truth_metrics[metric_name]
                row[f"abserr_{metric_name}_observed_days"] = (
                    abs(metric_value - truth_value)
                    if np.isfinite(metric_value) and np.isfinite(truth_value)
                    else float("nan")
                )
            for name in FILL_ESTIMATORS:
                fill = np.asarray(fits[name], dtype=float)
                completed = observed.copy()
                completed[mask] = fill[mask]
                if not np.isfinite(completed).all():
                    row[f"metric_{name}"] = float("nan")
                    row[f"abserr_noisy_{name}"] = float("nan")
                    for metric_name in truth_metrics:
                        row[f"{metric_name}_{name}"] = float("nan")
                        row[f"abserr_{metric_name}_{name}"] = float("nan")
                    for threshold in EXCEEDANCE_THRESHOLDS_C:
                        row[f"exceed_{int(threshold)}_{name}"] = float("nan")
                    continue
                row[f"metric_{name}"] = hottest_window_mean(completed)
                completed_noisy = noisy_truth.copy()
                completed_noisy[mask] = fill[mask]
                noisy_value = hottest_window_mean(completed_noisy)
                row[f"abserr_noisy_{name}"] = (
                    float(abs(noisy_value - noisy_truth_metric))
                    if np.isfinite(noisy_value) and np.isfinite(noisy_truth_metric)
                    else float("nan")
                )
                for metric_name, metric_value in _metrics(completed).items():
                    row[f"{metric_name}_{name}"] = float(metric_value)
                    truth_value = truth_metrics[metric_name]
                    row[f"abserr_{metric_name}_{name}"] = (
                        abs(metric_value - truth_value)
                        if np.isfinite(metric_value) and np.isfinite(truth_value)
                        else float("nan")
                    )
                for threshold in EXCEEDANCE_THRESHOLDS_C:
                    row[f"exceed_{int(threshold)}_{name}"] = exceedance_days(completed, threshold)
            for name in ALL_ESTIMATORS:
                value = row.get(f"metric_{name}", float("nan"))
                row[f"err_{name}"] = float(value - truth_metric) if np.isfinite(value) else float("nan")
                row[f"abserr_{name}"] = abs(row[f"err_{name}"]) if np.isfinite(row[f"err_{name}"]) else float("nan")
            # Mechanism-only, not a feature: does the outage hide the realised peak?
            rolled = pd.Series(truth).rolling(HOTTEST_WINDOW_DAYS, min_periods=HOTTEST_WINDOW_DAYS).mean().to_numpy()
            true_peak_end = int(np.nanargmax(rolled))
            true_peak_slice = slice(max(0, true_peak_end - HOTTEST_WINDOW_DAYS + 1), true_peak_end + 1)
            row["true_peak_hidden_fraction"] = float(mask[true_peak_slice].mean())
            rows.append(row)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)
