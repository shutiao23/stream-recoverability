"""Alternative sensor-error models for the reference-series sensitivity (F11).

Why this module exists
----------------------
Audit finding F11: the published ``results/v17_fitness/step22_robustness/
noise_sensitivity.json`` was produced by a version of
``scripts/202_v17_robustness.py`` that evaluated the clean and the perturbed arm
of the length-versus-certificate contrast with *different* reconstruction
choices, so the published "noise effect" partly measured a method change. The
function is fixed in ``scripts/202_v17_robustness.py`` (commit a9a7ad99cf) and
that fix is enough to regenerate the iid-Gaussian sensitivity.

It is not enough for the question a reviewer actually asks: the frozen case
table stores exactly one perturbed-error column per estimator, built from one
error process (independent Gaussian, sd 0.15 C, seed tag ``"sensor"``). A
different daily error process -- a whole-year calibration offset, an
autocorrelated error, a mid-year step after a device replacement -- changes the
perturbation of *every* case, so it cannot be recovered from the frozen table.
It has to be re-derived from the daily panel.

What this module does
---------------------
``build_station_scenarios`` re-runs the case construction of
``stream_recoverability.experiments.v17_fitness.cases.build_station_cases`` with
a pluggable additive daily error process. Everything else is held identical:
the same panel loader, the same outage design and per-case seeds, the same
estimator fits, the same completion rule, the same case-eligibility conditions,
and the same row key. Only the block that draws the reference-series
perturbation is parameterised.

The replication is checked, not assumed: run with ``model_keys=["iid_0.15"]``
and the ``clean__*`` / ``iid_0.15__*`` columns must reproduce the frozen
``abserr_hottest30_*`` and ``abserr_noisy_*`` columns of
``results/v17_fitness/step3_cases/cases.parquet`` exactly. That check lives in
``scripts/246_wrr_noise_recompute.py`` and its outcome is recorded in
``results/wrr_submission_ready/amendments/step22_noise_post_fix/summary.json``.

Error convention (the one the frozen construction uses)
-------------------------------------------------------
The estimator's fill values are fitted on the *clean* observed record and are
not refitted under the error model. A daily error ``eps`` enters in two places
only:

* the observed days of the completed year, ``completed = clean_completed + eps``
  on days that are present and ``fill`` on days that are missing, exactly as
  ``cases.py`` builds ``completed_noisy``; and
* the reference the error is measured against, ``H(truth + eps)``, where ``H``
  is the hottest-30-day mean.

So the perturbation is an error in the *reference series*, measured against an
estimator whose parameters are those of the clean record, which is the
sensitivity the published 0.15 C check claims to measure. It is not a
sensitivity to error propagating into the reconstruction, and the report says
so.

The error processes
-------------------
``iid_0.15``            independent Gaussian, sd 0.15 C -- replica of the frozen
                        process, used as the validation anchor.
``bias_[pm]0.15/0.30/0.50``  one constant offset applied to the whole calendar
                        year (logger calibration offset). Note this cancels
                        exactly between estimate and reference where the record
                        is observed, and does not cancel across the filled days,
                        which is why it is a real test.
``ar1_r0.70_sd0.15``    stationary AR(1) daily error, marginal sd 0.15 C,
                        rho 0.7 (persistent logger/environment error).
``step_p0.30_midyear``  +0.30 C from day-of-year 183 onwards (device replaced
                        mid-year, new sensor offset).
``drift_0_to_p0.30``    monotone drift from 0 to +0.30 C across the calendar
                        year (slow calibration drift), supplied alongside the
                        step rather than instead of it.

All processes are seeded by ``stable_seed(network_id, station_id, year, tag)``,
so they are reproducible across processes and machines. ``iid_0.15`` reuses the
frozen tag ``"sensor"`` so that it reproduces the frozen column exactly; the new
processes use their own tags and do not disturb it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from stream_recoverability.experiments.v17_fitness.cases import (
    FILL_ESTIMATORS,
    WARM_MONTHS,
    deseasonalized_correlations,
    station_geometry_pool,
)
from stream_recoverability.experiments.v17_fitness.estimators import (
    StationModels,
    hottest_window_mean,
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
    SENSOR_NOISE_C,
    stable_seed,
)

# Frozen construction's seed tag for the reference-series perturbation. Kept so
# that the replica model reproduces the frozen noisy columns bit-for-bit.
FROZEN_NOISE_TAG = "sensor"

# A device is replaced "mid-year" at this day of year (2 July in a non-leap
# year). The step applies to that day and every later day of the calendar year.
MIDYEAR_DOY = 183


@dataclass(frozen=True)
class SensorErrorModel:
    """One additive daily error process, evaluated on a single calendar year."""

    key: str
    kind: str
    magnitude: float = 0.0
    rho: float = 0.0
    seed_tag: str = ""
    note: str = ""

    def draw(self, index: pd.DatetimeIndex, *, network_id: str, station_id: str, year: int) -> np.ndarray:
        """Daily additive error, same length as ``index``."""

        n = len(index)
        seed = stable_seed(network_id, station_id, int(year), self.seed_tag or self.key)
        if self.kind == "iid":
            return np.random.default_rng(seed).normal(0.0, float(self.magnitude), size=n)
        if self.kind == "bias":
            return np.full(n, float(self.magnitude), dtype=float)
        if self.kind == "ar1":
            # Stationary AR(1): x_0 ~ N(0, sd^2) so the marginal sd is exactly
            # ``magnitude`` on every day, not only asymptotically.
            rng = np.random.default_rng(seed)
            sd = float(self.magnitude)
            values = np.empty(n, dtype=float)
            values[0] = sd * float(rng.normal())
            innovation = sd * np.sqrt(1.0 - float(self.rho) ** 2) * rng.normal(size=n - 1)
            for position in range(1, n):
                values[position] = float(self.rho) * values[position - 1] + innovation[position - 1]
            return values
        if self.kind == "step":
            doy = np.asarray(index.dayofyear, dtype=int)
            return np.where(doy >= MIDYEAR_DOY, float(self.magnitude), 0.0)
        if self.kind == "drift":
            doy = np.asarray(index.dayofyear, dtype=float)
            span = float(doy.max() - doy.min())
            fraction = (doy - doy.min()) / span if span > 0 else np.zeros(n, dtype=float)
            return float(self.magnitude) * fraction
        raise ValueError(f"unknown error-process kind: {self.kind!r}")


#: The named processes reported by script 246. ``iid_0.15`` is the validation
#: anchor and reproduces the frozen step22 sensitivity exactly.
SCENARIO_MODELS: dict[str, SensorErrorModel] = {
    "iid_0.15": SensorErrorModel(
        key="iid_0.15",
        kind="iid",
        magnitude=SENSOR_NOISE_C,
        seed_tag=FROZEN_NOISE_TAG,
        note="replica of the frozen 0.15 C iid Gaussian process (validation anchor)",
    ),
    "bias_p0.15": SensorErrorModel(key="bias_p0.15", kind="bias", magnitude=0.15, note="+0.15 C all year"),
    "bias_p0.30": SensorErrorModel(key="bias_p0.30", kind="bias", magnitude=0.30, note="+0.30 C all year"),
    "bias_p0.50": SensorErrorModel(key="bias_p0.50", kind="bias", magnitude=0.50, note="+0.50 C all year"),
    "bias_m0.15": SensorErrorModel(key="bias_m0.15", kind="bias", magnitude=-0.15, note="-0.15 C all year"),
    "bias_m0.30": SensorErrorModel(key="bias_m0.30", kind="bias", magnitude=-0.30, note="-0.30 C all year"),
    "bias_m0.50": SensorErrorModel(key="bias_m0.50", kind="bias", magnitude=-0.50, note="-0.50 C all year"),
    "ar1_r0.70_sd0.15": SensorErrorModel(
        key="ar1_r0.70_sd0.15",
        kind="ar1",
        magnitude=0.15,
        rho=0.7,
        note="stationary AR(1) daily error, rho 0.7, marginal sd 0.15 C",
    ),
    "step_p0.30_midyear": SensorErrorModel(
        key="step_p0.30_midyear",
        kind="step",
        magnitude=0.30,
        note=f"+0.30 C from day-of-year {MIDYEAR_DOY} (device replaced mid-year)",
    ),
    "drift_0_to_p0.30": SensorErrorModel(
        key="drift_0_to_p0.30",
        kind="drift",
        magnitude=0.30,
        note="monotone drift 0 to +0.30 C across the calendar year",
    ),
}

#: Order used in tables and reports: anchor first, then bias, then structure.
SCENARIO_ORDER: tuple[str, ...] = tuple(SCENARIO_MODELS)

CLEAN_PREFIX = "clean__"
TRUTH_PREFIX = "truth_hottest30__"


def _error_column(model_key: str, estimator: str) -> str:
    return f"{model_key}__{estimator}"


def build_station_scenarios(job: dict, model_keys: Sequence[str] = SCENARIO_ORDER) -> pd.DataFrame:
    """Every scored case contributed by one station, under several error models.

    Worker entry point; picklable. Mirrors
    ``v17_fitness.cases.build_station_cases`` line for line, with the
    reference-series perturbation replaced by the requested
    :class:`SensorErrorModel` processes. The hot-day metric is the only metric
    retained, because it is the primary endpoint and the only one the locked
    contrast uses.
    """

    models = [SCENARIO_MODELS[key] for key in model_keys]
    network_id = str(job["network_id"])
    station_id = str(job["station_id"])
    try:
        daily = load_network_panel(network_id, str(job["source_root"]))
    except (FileNotFoundError, ValueError, KeyError):
        return pd.DataFrame()
    if station_id not in [str(column) for column in daily.columns]:
        return pd.DataFrame()
    daily = daily.copy()
    daily.columns = [str(column) for column in daily.columns]
    target = pd.to_numeric(daily[station_id], errors="coerce")
    donors = daily.drop(columns=[station_id])
    air = air_series_for(network_id, station_id, daily.index)
    pool = station_geometry_pool(daily)

    complete_years = tuple(int(year) for year in job["complete_years"])
    if len(complete_years) < 2:
        return pd.DataFrame()
    protocol = str(job.get("fit_protocol", "leave_one_year_out"))

    rows: list[dict[str, object]] = []

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
            if sum(1 for other in complete_years if other < int(year)) < 2:
                continue
            train_mask = pd.Series(daily.index.year < int(year), index=daily.index)
            peak_source = target.loc[target.index.year < int(year)]
        else:
            train_mask = pd.Series(~year_mask, index=daily.index)
            peak_source = target.loc[target.index.year != int(year)]
        models_for_year = StationModels(target=target, donors=donors, air=air, train_mask=train_mask)
        peak_doys = climatological_peak_window(peak_source, exclude_year=None)

        train_values = target.loc[train_mask].dropna()
        if len(train_values) < 365:
            continue

        correlations = deseasonalized_correlations(target, donors, train_mask)

        rng = np.random.default_rng(stable_seed(network_id, station_id, int(year), protocol))
        realizations = design_for_year(
            year_index,
            peak_doys,
            pool,
            rng=rng,
            n_empirical=max(1, REALIZATIONS_PER_STATION_YEAR // 3),
        )

        # One draw per process, re-used by every outage realization of this
        # station-year, exactly as the frozen construction draws one noisy
        # reference per station-year and not per realization.
        errors = {
            model.key: model.draw(year_index, network_id=network_id, station_id=station_id, year=int(year))
            for model in models
        }
        reference_metrics = {
            model.key: hottest_window_mean(truth + errors[model.key]) for model in models
        }

        for realization in realizations:
            mask = realization.mask(len(year_index))
            if not mask.any() or mask.all():
                continue
            observed = truth.copy()
            observed[mask] = np.nan

            visible = usable_donors(donors, year_index, mask)
            fits: dict[str, np.ndarray] = {}
            fits["doy_climatology"] = models_for_year.doy_climatology(year_index)
            fits["smooth_climatology"] = models_for_year.smooth_climatology(year_index)
            fits["linear_interp"] = linear_interp_fill(observed)
            donor_fit = models_for_year.donor_ridge(visible) if visible else None
            fits["donor_ridge"] = (
                models_for_year.donor_predict(donor_fit, year_index)
                if donor_fit is not None
                else np.full(len(year_index), np.nan)
            )
            fits["air_ridge"] = (
                models_for_year.air_predict(year_index)
                if air is not None
                else np.full(len(year_index), np.nan)
            )

            warm = np.isin(year_index.month.to_numpy(), WARM_MONTHS)
            row: dict[str, object] = {
                "network_id": network_id,
                "station_id": station_id,
                "provider": str(job["provider"]),
                "split_role": str(job["split_role"]),
                "year": int(year),
                "realization_id": realization.realization_id,
                "arm": realization.arm,
                "overlap_class": realization.overlap_class,
                "longest_run": int(realization.longest_run),
                "missing_fraction": float(mask.sum() / len(mask)),
                "peak_overlap": peak_overlap_fraction(year_index, mask, peak_doys),
                "warm_observed_fraction": float((~mask & warm).sum() / max(1, warm.sum())),
                "n_visible_donors": int(len(visible)),
                "truth_hottest30": float(truth_metric),
            }
            for model in models:
                row[f"{TRUTH_PREFIX}{model.key}"] = float(reference_metrics[model.key])

            for name in FILL_ESTIMATORS:
                fill = np.asarray(fits[name], dtype=float)
                completed = observed.copy()
                completed[mask] = fill[mask]
                if not np.isfinite(completed).all():
                    row[f"{CLEAN_PREFIX}{name}"] = float("nan")
                    for model in models:
                        row[_error_column(model.key, name)] = float("nan")
                    continue
                row[f"{CLEAN_PREFIX}{name}"] = float(abs(hottest_window_mean(completed) - truth_metric))
                for model in models:
                    completed_noisy = (truth + errors[model.key]).copy()
                    completed_noisy[mask] = fill[mask]
                    value = hottest_window_mean(completed_noisy)
                    reference = float(reference_metrics[model.key])
                    row[_error_column(model.key, name)] = (
                        float(abs(value - reference)) if np.isfinite(value) and np.isfinite(reference) else float("nan")
                    )
            rows.append(row)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


__all__ = [
    "CLEAN_PREFIX",
    "FROZEN_NOISE_TAG",
    "MIDYEAR_DOY",
    "SCENARIO_MODELS",
    "SCENARIO_ORDER",
    "TRUTH_PREFIX",
    "SensorErrorModel",
    "build_station_scenarios",
]
