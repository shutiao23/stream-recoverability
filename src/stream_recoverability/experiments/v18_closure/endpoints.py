"""Endpoints the v17 case table does not carry, on the v17 cases.

Two questions need estimands the original table never computed, and both need
them on exactly the same outage realizations, so this module regenerates those
realizations from the same deterministic seeds rather than sampling new ones.

E3 needs Johnson et al.'s own estimands. Their guidance is derived from a
sine-wave linear regression fitted to the annual series, from which they take a
mean, a phase and an amplitude. Our dichotomy makes a sharp prediction about
those three: the fitted mean is a whole-year functional and should be governed
by how many days are missing; the phase is a location parameter and should be
governed by which days; the amplitude sits between. If that comes out as
predicted we have explained their reported inconsistency on their own
estimands rather than by analogy from a different statistic.

E6 needs a continuum. The hottest-k-day mean for k from 1 to 365 interpolates
between an annual maximum and an annual mean, so the support of the estimand
becomes a knob rather than a dichotomy, and the governing axis should move
smoothly with it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.experiments.v17_fitness.cases import (
    WARM_MONTHS,
    station_geometry_pool,
)
from stream_recoverability.experiments.v17_fitness.estimators import (
    StationModels,
    donor_coverage,
    linear_interp_fill,
    usable_donors,
)
from stream_recoverability.experiments.v17_fitness.outages import (
    climatological_peak_window,
    design_for_year,
    peak_overlap_fraction,
)
from stream_recoverability.experiments.v17_fitness.panel import air_series_for, load_network_panel
from stream_recoverability.experiments.v17_fitness.paths import (
    REALIZATIONS_PER_STATION_YEAR,
    donor_regime,
    stable_seed,
)
from stream_recoverability.experiments.v18_closure.deployment import policy_choice
from stream_recoverability.experiments.v18_closure.paths import SUPPORT_WIDTHS

DAYS_IN_YEAR = 365.25


def hottest_k_mean(values: np.ndarray, width: int) -> float:
    """Mean of the hottest ``width`` consecutive days; width 365 is the annual mean."""

    series = pd.Series(values, dtype=float)
    if width <= 1:
        return float(np.nanmax(series.to_numpy())) if np.isfinite(series.to_numpy()).any() else float("nan")
    if width >= 365 or width >= len(series):
        # The right endpoint of the continuum is the annual mean itself, on a
        # leap year as well as an ordinary one.
        return float(np.nanmean(series.to_numpy()))
    rolled = series.rolling(int(width), min_periods=int(width)).mean().to_numpy(dtype=float)
    if not np.isfinite(rolled).any():
        return float("nan")
    return float(np.nanmax(rolled))


def hottest_k_window(climatology: np.ndarray, width: int) -> np.ndarray:
    """Positions of the climatological hottest ``width``-day window, wrapping the year."""

    n = len(climatology)
    if width >= n:
        return np.arange(n)
    padded = np.concatenate([climatology, climatology[: width - 1]])
    rolling = np.convolve(padded, np.ones(width) / width, mode="valid")[:n]
    start = int(np.nanargmax(rolling))
    return (start + np.arange(width)) % n


def sine_parameters(values: np.ndarray) -> dict[str, float]:
    """Johnson et al.'s estimator: a sine wave fitted by linear regression.

    Returns the fitted annual mean, the amplitude, and the phase expressed as
    the day of year on which the fitted wave peaks. NaN days are dropped, which
    is what fitting a regression to an incomplete record does.
    """

    y = np.asarray(values, dtype=float)
    t = np.arange(len(y), dtype=float)
    good = np.isfinite(y)
    if good.sum() < 30:
        return {"sine_mean": np.nan, "sine_amplitude": np.nan, "sine_phase": np.nan}
    angle = 2 * np.pi * t[good] / DAYS_IN_YEAR
    design = np.column_stack([np.ones(good.sum()), np.sin(angle), np.cos(angle)])
    try:
        beta, *_ = np.linalg.lstsq(design, y[good], rcond=None)
    except np.linalg.LinAlgError:
        return {"sine_mean": np.nan, "sine_amplitude": np.nan, "sine_phase": np.nan}
    intercept, a, b = (float(v) for v in beta)
    amplitude = float(np.hypot(a, b))
    # Writing the fit as A sin(theta - phi) with theta = 2 pi t / T gives
    # a = A cos(phi) and b = -A sin(phi), so phi = atan2(-b, a) and the wave
    # peaks a quarter of a year after phi. The phase is reported as the day of
    # year of that maximum, which is the form Johnson et al. interpret.
    phi = float(np.arctan2(-b, a) % (2 * np.pi))
    peak_day = float((phi * DAYS_IN_YEAR / (2 * np.pi) + DAYS_IN_YEAR / 4.0) % DAYS_IN_YEAR) + 1.0
    return {"sine_mean": intercept, "sine_amplitude": amplitude, "sine_phase": peak_day}


def influence_weights(climatology: np.ndarray) -> dict[str, np.ndarray]:
    """How much each day of the year moves each sine-fit parameter.

    This is the precise form of "the support of the estimand". Writing the fit
    as A sin(theta - phi), the derivative of each parameter with respect to one
    day's value is, up to a constant:

        mean       1                  every day equally
        amplitude  sin(theta - phi)   largest at the peak and at the trough
        phase      cos(theta - phi)   largest a quarter-year from the peak

    So the amplitude is supported on both extremes and the phase on the spring
    and autumn transitions, which is a sharper prediction than "timing matters":
    hiding the summer peak should barely move the phase.
    """

    n = len(climatology)
    fitted = sine_parameters(climatology)
    peak_day = fitted["sine_phase"]
    if not np.isfinite(peak_day):
        uniform = np.ones(n) / n
        return {"sine_mean": uniform, "sine_amplitude": uniform, "sine_phase": uniform}
    theta = 2 * np.pi * np.arange(n) / DAYS_IN_YEAR
    phi = 2 * np.pi * ((peak_day - 1.0) / DAYS_IN_YEAR) - np.pi / 2
    return {
        "sine_mean": np.ones(n),
        "sine_amplitude": np.abs(np.sin(theta - phi)),
        "sine_phase": np.abs(np.cos(theta - phi)),
    }


def transition_window(climatology: np.ndarray, half_width: int = 30) -> np.ndarray:
    """Positions a quarter-year either side of the climatological peak.

    The agency-computable stand-in for the phase's support: two windows around
    the spring warming and autumn cooling limbs.
    """

    n = len(climatology)
    fitted = sine_parameters(climatology)
    peak = int(fitted["sine_phase"]) - 1 if np.isfinite(fitted["sine_phase"]) else n // 2
    quarter = int(round(n / 4))
    positions = []
    for centre in (peak - quarter, peak + quarter):
        positions.append((centre + np.arange(-half_width, half_width + 1)) % n)
    return np.unique(np.concatenate(positions))


def phase_difference(a: float, b: float) -> float:
    """Circular difference between two days of year, in days."""

    if not (np.isfinite(a) and np.isfinite(b)):
        return float("nan")
    delta = abs(float(a) - float(b)) % DAYS_IN_YEAR
    return float(min(delta, DAYS_IN_YEAR - delta))


def realized_window_centres(job: dict) -> list[dict]:
    """Where each year's hottest-k window actually fell, for every k.

    The support-restricted axis conditions on the *climatological* hottest-k
    window, which is an estimate of where this year's window will be. For a
    narrow estimand that estimate is poor -- the hottest single day wanders --
    and a screening rule conditioned on it inherits the wander. Measuring the
    year-to-year dispersion of the realised window turns that from an excuse
    into a quantity.
    """

    network_id, station_id = str(job["network_id"]), str(job["station_id"])
    try:
        daily = load_network_panel(network_id, str(job["source_root"]))
    except (FileNotFoundError, ValueError, KeyError):
        return []
    daily = daily.copy()
    daily.columns = [str(c) for c in daily.columns]
    if station_id not in daily.columns:
        return []
    target = pd.to_numeric(daily[station_id], errors="coerce")
    rows = []
    for year in (int(y) for y in job["complete_years"]):
        values = target.loc[target.index.year == year].to_numpy(dtype=float)
        if not np.isfinite(values).all() or len(values) < 360:
            continue
        n = len(values)
        for width in SUPPORT_WIDTHS:
            if width >= 365:
                continue
            if width <= 1:
                centre = float(np.nanargmax(values))
            else:
                rolled = pd.Series(values).rolling(width, min_periods=width).mean().to_numpy()
                centre = float(np.nanargmax(rolled) - (width - 1) / 2.0)
            rows.append(
                {
                    "network_id": network_id,
                    "station_id": station_id,
                    "year": year,
                    "support_width_days": int(width),
                    "centre_angle": 2 * np.pi * centre / n,
                }
            )
    return rows


def endpoint_rows(job: dict) -> pd.DataFrame:
    """Extended endpoints for every case this station contributes.

    The realizations are regenerated from the same seeds the v17 case table
    used, so a row here lines up with a row there.
    """

    network_id = str(job["network_id"])
    station_id = str(job["station_id"])
    try:
        daily = load_network_panel(network_id, str(job["source_root"]))
    except (FileNotFoundError, ValueError, KeyError):
        return pd.DataFrame()
    daily = daily.copy()
    daily.columns = [str(c) for c in daily.columns]
    if station_id not in daily.columns:
        return pd.DataFrame()
    target = pd.to_numeric(daily[station_id], errors="coerce")
    donors = daily.drop(columns=[station_id])
    air = air_series_for(network_id, station_id, daily.index)
    pool = station_geometry_pool(daily)

    complete_years = tuple(int(y) for y in job["complete_years"])
    if len(complete_years) < 2:
        return pd.DataFrame()

    rows: list[dict] = []
    for year in complete_years:
        year_mask = target.index.year == int(year)
        year_index = daily.index[year_mask]
        truth = target.loc[year_mask].to_numpy(dtype=float)
        if not np.isfinite(truth).all() or len(truth) < 360:
            continue
        train_mask = pd.Series(~year_mask, index=daily.index)
        models = StationModels(target=target, donors=donors, air=air, train_mask=train_mask)
        peak_source = target.loc[target.index.year != int(year)]
        peak_doys = climatological_peak_window(peak_source, exclude_year=None)
        climatology = models.smooth_climatology(year_index)
        if not np.isfinite(climatology).all():
            continue
        support_windows = {width: hottest_k_window(climatology, width) for width in SUPPORT_WIDTHS}
        weights = influence_weights(climatology)
        weight_totals = {name: float(w.sum()) for name, w in weights.items()}
        transition = transition_window(climatology)

        truth_endpoints = {f"truth_hottest_{w}": hottest_k_mean(truth, w) for w in SUPPORT_WIDTHS}
        truth_sine = sine_parameters(truth)

        rng = np.random.default_rng(stable_seed(network_id, station_id, int(year), "leave_one_year_out"))
        realizations = design_for_year(
            year_index, peak_doys, pool, rng=rng, n_empirical=max(1, REALIZATIONS_PER_STATION_YEAR // 3)
        )
        months = year_index.month.to_numpy()
        warm = np.isin(months, WARM_MONTHS)

        for realization in realizations:
            mask = realization.mask(len(year_index))
            if not mask.any() or mask.all():
                continue
            observed = truth.copy()
            observed[mask] = np.nan
            visible = usable_donors(donors, year_index, mask)
            coverage = donor_coverage(donors, year_index, mask)

            row: dict[str, object] = {
                "network_id": network_id,
                "station_id": station_id,
                "provider": str(job["provider"]),
                "split_role": str(job["split_role"]),
                "year": int(year),
                "realization_id": realization.realization_id,
                "arm": realization.arm,
                "longest_run": int(realization.longest_run),
                "total_missing": int(realization.total_missing),
                "missing_fraction": float(mask.mean()),
                "n_runs": int(realization.n_runs),
                "peak_overlap": peak_overlap_fraction(year_index, mask, peak_doys),
                "warm_observed_fraction": float((~mask & warm).sum() / max(1, warm.sum())),
                "n_visible_donors": int(len(visible)),
                "donor_regime": donor_regime(len(visible)),
                "donor_coverage_mean": float(coverage.mean()) if len(coverage) else float("nan"),
                "left_flank": bool(not mask[0]),
                "right_flank": bool(not mask[-1]),
                "air_available": bool(air is not None),
            }
            row.update(truth_endpoints)
            row.update({f"truth_{k}": v for k, v in truth_sine.items()})

            # The unified axis: the share of the estimand's own support that the
            # outage hides. For width 365 this is the whole-year missing
            # fraction; for width 30 it is the peak-window overlap.
            for width, window in support_windows.items():
                row[f"support_hidden_{width}"] = float(mask[window].mean())
            # The same quantity for the sine parameters, where the support is a
            # weight over every day rather than a window.
            for name, weight in weights.items():
                total = weight_totals[name]
                row[f"influence_hidden_{name}"] = (
                    float(weight[mask].sum() / total) if total > 0 else float("nan")
                )
            row["transition_overlap"] = float(mask[transition].mean())

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
            choice = policy_choice(row, available)
            completed = completions.get(choice)
            row["policy_choice"] = choice
            if completed is None:
                rows.append(row)
                continue
            for width in SUPPORT_WIDTHS:
                value = hottest_k_mean(completed, width)
                row[f"policy_hottest_{width}"] = float(value)
                truth_value = truth_endpoints[f"truth_hottest_{width}"]
                row[f"abserr_hottest_{width}"] = (
                    float(abs(value - truth_value))
                    if np.isfinite(value) and np.isfinite(truth_value)
                    else float("nan")
                )
            fitted = sine_parameters(completed)
            # Johnson et al. fit the sine to whatever days are present; the
            # regression is the repair. Both variants are recorded: the fit to
            # the observed days alone is their protocol, the fit to the repaired
            # year is ours.
            observed_sine = sine_parameters(observed)
            for name, value in fitted.items():
                row[f"policy_{name}"] = float(value)
            for name, value in observed_sine.items():
                row[f"observed_{name}"] = float(value)
            for name in ("sine_mean", "sine_amplitude"):
                truth_value = truth_sine[name]
                row[f"abserr_{name}"] = (
                    float(abs(fitted[name] - truth_value))
                    if np.isfinite(fitted[name]) and np.isfinite(truth_value)
                    else float("nan")
                )
                row[f"abserr_observed_{name}"] = (
                    float(abs(observed_sine[name] - truth_value))
                    if np.isfinite(observed_sine[name]) and np.isfinite(truth_value)
                    else float("nan")
                )
            row["abserr_sine_phase"] = phase_difference(fitted["sine_phase"], truth_sine["sine_phase"])
            row["abserr_observed_sine_phase"] = phase_difference(
                observed_sine["sine_phase"], truth_sine["sine_phase"]
            )
            rows.append(row)

    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    return frame.sort_values(["network_id", "station_id", "year", "realization_id"]).reset_index(drop=True)
