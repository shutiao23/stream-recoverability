"""Step 3 — the estimator set, including the two incumbents v16 omitted.

Every estimator is fit leave-one-year-out within the station, which is the
correct protocol for offline archive repair: the analyst repairing a 2015
outage in 2026 does hold the rest of the record. A strictly-prior-years variant
is provided for the sensitivity analysis.

`observed_days` is the estimator practitioners actually use — compute the metric
from recorded days and ignore the outage. It was absent from the v16 comparison
set and is included here as a first-class competitor.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from stream_recoverability.experiments.v17_fitness.paths import HOTTEST_WINDOW_DAYS

DONOR_COVERAGE_FOR_USE = 0.90
MIN_TRAIN_ROWS = 120
SMOOTH_WINDOW = 15
AIR_LAGS = (0, 1, 2, 3, 5, 7, 14)

ESTIMATOR_NAMES = (
    "observed_days",
    "doy_climatology",
    "smooth_climatology",
    "linear_interp",
    "donor_ridge",
    "air_ridge",
)


def _doy(index: pd.DatetimeIndex) -> np.ndarray:
    return index.dayofyear.to_numpy()


def _circular_smooth(values: np.ndarray, window: int) -> np.ndarray:
    half = int(window) // 2
    padded = np.concatenate([values[-half:], values, values[:half]])
    kernel = np.ones(int(window)) / float(window)
    smoothed = np.convolve(padded, kernel, mode="same")
    return smoothed[half : half + len(values)]


@dataclass
class StationModels:
    """Fitted estimators for one station and one evaluation year."""

    target: pd.Series
    donors: pd.DataFrame
    air: pd.Series | None
    train_mask: pd.Series
    _doy_median: np.ndarray | None = None
    _doy_smooth: np.ndarray | None = None
    _donor_cache: dict | None = None
    _air_model: object | None = None
    _air_fitted: bool = False

    def __post_init__(self) -> None:
        if self._donor_cache is None:
            self._donor_cache = {}

    # -- climatologies -----------------------------------------------------
    def _climatology_tables(self) -> None:
        if self._doy_median is not None:
            return
        train = self.target.loc[self.train_mask]
        train = train.dropna()
        grid = np.full(367, np.nan, dtype=float)
        smooth_grid = np.full(367, np.nan, dtype=float)
        if train.empty:
            self._doy_median = grid
            self._doy_smooth = smooth_grid
            return
        doy = train.index.dayofyear
        median = train.groupby(doy).median().reindex(range(1, 367))
        mean = train.groupby(doy).mean().reindex(range(1, 367))
        median = median.interpolate(limit_direction="both")
        mean = mean.interpolate(limit_direction="both")
        grid[1:367] = median.to_numpy()
        smooth_grid[1:367] = _circular_smooth(mean.to_numpy(), SMOOTH_WINDOW)
        self._doy_median = grid
        self._doy_smooth = smooth_grid

    def doy_climatology(self, index: pd.DatetimeIndex) -> np.ndarray:
        self._climatology_tables()
        return np.asarray(self._doy_median, dtype=float)[_doy(index)]

    def smooth_climatology(self, index: pd.DatetimeIndex) -> np.ndarray:
        self._climatology_tables()
        return np.asarray(self._doy_smooth, dtype=float)[_doy(index)]

    # -- donor regression --------------------------------------------------
    def donor_ridge(self, donor_names: Sequence[str]) -> object | None:
        """Ridge on the *visible* donor subset, retrained per subset.

        v16 Step 4 established that imputing absent donor columns into a full
        model is harmful (-1.56 C) while retraining on the visible subset helps
        (+0.74 C). That finding is deployed here rather than only reported.
        """

        key = tuple(sorted(str(name) for name in donor_names))
        if not key:
            return None
        if key in self._donor_cache:
            return self._donor_cache[key]
        columns = [name for name in key if name in self.donors.columns]
        if not columns:
            self._donor_cache[key] = None
            return None
        frame = self.donors.loc[self.train_mask, columns].apply(pd.to_numeric, errors="coerce")
        y = self.target.loc[self.train_mask]
        design = pd.concat([frame, y.rename("__target__")], axis=1).dropna()
        if len(design) < MIN_TRAIN_ROWS:
            self._donor_cache[key] = None
            return None
        doy = design.index.dayofyear.to_numpy()
        harmonics = np.column_stack(
            [
                np.sin(2 * np.pi * doy / 365.25),
                np.cos(2 * np.pi * doy / 365.25),
                np.sin(4 * np.pi * doy / 365.25),
                np.cos(4 * np.pi * doy / 365.25),
            ]
        )
        X = np.column_stack([design[columns].to_numpy(dtype=float), harmonics])
        model = Ridge(alpha=1.0)
        model.fit(X, design["__target__"].to_numpy(dtype=float))
        fitted = (model, tuple(columns))
        self._donor_cache[key] = fitted
        return fitted

    def donor_predict(self, fitted: object, index: pd.DatetimeIndex) -> np.ndarray:
        model, columns = fitted
        frame = self.donors.reindex(index)[list(columns)].apply(pd.to_numeric, errors="coerce")
        doy = index.dayofyear.to_numpy()
        harmonics = np.column_stack(
            [
                np.sin(2 * np.pi * doy / 365.25),
                np.cos(2 * np.pi * doy / 365.25),
                np.sin(4 * np.pi * doy / 365.25),
                np.cos(4 * np.pi * doy / 365.25),
            ]
        )
        X = np.column_stack([frame.to_numpy(dtype=float), harmonics])
        out = np.full(len(index), np.nan, dtype=float)
        good = np.isfinite(X).all(axis=1)
        if good.any():
            out[good] = model.predict(X[good])
        return out

    # -- air regression ----------------------------------------------------
    def _air_design(self, index: pd.DatetimeIndex) -> np.ndarray | None:
        if self.air is None:
            return None
        series = pd.to_numeric(self.air, errors="coerce")
        lagged = [series.shift(lag).reindex(index).to_numpy(dtype=float) for lag in AIR_LAGS]
        doy = index.dayofyear.to_numpy()
        lagged.append(np.sin(2 * np.pi * doy / 365.25))
        lagged.append(np.cos(2 * np.pi * doy / 365.25))
        return np.column_stack(lagged)

    def air_ridge(self) -> object | None:
        if self._air_fitted:
            return self._air_model
        self._air_fitted = True
        self._air_model = None
        if self.air is None:
            return None
        index = self.target.index[self.train_mask.to_numpy()]
        X = self._air_design(index)
        if X is None:
            return None
        y = self.target.loc[self.train_mask].to_numpy(dtype=float)
        good = np.isfinite(X).all(axis=1) & np.isfinite(y)
        if int(good.sum()) < MIN_TRAIN_ROWS:
            return None
        model = Ridge(alpha=1.0)
        model.fit(X[good], y[good])
        self._air_model = model
        return model

    def air_predict(self, index: pd.DatetimeIndex) -> np.ndarray:
        model = self.air_ridge()
        out = np.full(len(index), np.nan, dtype=float)
        if model is None:
            return out
        X = self._air_design(index)
        if X is None:
            return out
        good = np.isfinite(X).all(axis=1)
        if good.any():
            out[good] = model.predict(X[good])
        return out


def linear_interp_fill(observed: np.ndarray) -> np.ndarray:
    """Linear interpolation across interior gaps; interior support only."""

    series = pd.Series(observed, dtype=float)
    filled = series.interpolate(method="linear", limit_area="inside")
    return filled.to_numpy(dtype=float)


def donor_coverage(donors: pd.DataFrame, index: pd.DatetimeIndex, mask: np.ndarray) -> pd.Series:
    """Fraction of the hidden days on which each donor is observed."""

    if donors.empty or not mask.any():
        return pd.Series(dtype=float)
    block = donors.reindex(index).loc[mask]
    return block.notna().mean()


def usable_donors(donors: pd.DataFrame, index: pd.DatetimeIndex, mask: np.ndarray) -> tuple[str, ...]:
    coverage = donor_coverage(donors, index, mask)
    if coverage.empty:
        return ()
    return tuple(str(name) for name, value in coverage.items() if float(value) >= DONOR_COVERAGE_FOR_USE)


def observed_days_metric(
    observed: np.ndarray,
    *,
    window: int = HOTTEST_WINDOW_DAYS,
    min_coverage: float = 0.8,
) -> float:
    """The incumbent estimator: the metric computed from recorded days only."""

    series = pd.Series(observed, dtype=float)
    min_periods = int(np.ceil(min_coverage * window))
    rolled = series.rolling(int(window), min_periods=min_periods).mean().to_numpy(dtype=float)
    if not np.isfinite(rolled).any():
        return float("nan")
    return float(np.nanmax(rolled))


def hottest_window_mean(values: np.ndarray, *, window: int = HOTTEST_WINDOW_DAYS) -> float:
    series = pd.Series(values, dtype=float)
    rolled = series.rolling(int(window), min_periods=int(window)).mean().to_numpy(dtype=float)
    if not np.isfinite(rolled).any():
        return float("nan")
    return float(np.nanmax(rolled))


def exceedance_days(values: np.ndarray, threshold: float) -> float:
    finite = np.asarray(values, dtype=float)
    if not np.isfinite(finite).any():
        return float("nan")
    return float(np.nansum(finite > float(threshold)))


def coldest_window_mean(
    values: np.ndarray,
    *,
    window: int = HOTTEST_WINDOW_DAYS,
    min_coverage: float | None = None,
) -> float:
    """Minimum of the rolling ``window``-day mean.

    With ``min_coverage`` this is the observed-days estimator of the cold
    extreme; without it, the window must be fully present.
    """

    series = pd.Series(values, dtype=float)
    min_periods = int(window) if min_coverage is None else int(np.ceil(float(min_coverage) * window))
    rolled = series.rolling(int(window), min_periods=min_periods).mean().to_numpy(dtype=float)
    if not np.isfinite(rolled).any():
        return float("nan")
    return float(np.nanmin(rolled))
