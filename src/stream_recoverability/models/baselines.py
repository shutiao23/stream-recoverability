"""Traditional, leakage-aware baselines for daily stream observations.

All trainable models accept a pandas ``DataFrame`` in ``fit`` and ``predict``.
The target can be supplied as a column name or as a separate series.  Temporal
interpolators intentionally operate only in offline mode: callers must pass a
copy of the target with artificial gaps represented by ``NaN``.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence
import warnings

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def _as_frame(data: pd.DataFrame | pd.Series) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data
    if isinstance(data, pd.Series):
        name = data.name or "target"
        return data.to_frame(name=name)
    raise TypeError("data must be a pandas DataFrame or Series")


def _target_series(
    data: pd.DataFrame | pd.Series,
    y: str | Sequence[float] | pd.Series | None,
    target_col: str | None,
) -> pd.Series:
    frame = _as_frame(data)
    if isinstance(y, str):
        if y not in frame:
            raise KeyError(f"target column not found: {y}")
        return pd.to_numeric(frame[y], errors="coerce")
    if y is None:
        if isinstance(data, pd.Series):
            return pd.to_numeric(data, errors="coerce")
        if target_col is None:
            raise ValueError("target_col or y must be supplied")
        if target_col not in frame:
            raise KeyError(f"target column not found: {target_col}")
        return pd.to_numeric(frame[target_col], errors="coerce")
    if isinstance(y, pd.Series):
        if y.index.equals(frame.index):
            return pd.to_numeric(y, errors="coerce")
        if len(y) != len(frame):
            raise ValueError("y and data must have the same length")
        return pd.Series(pd.to_numeric(y, errors="coerce").to_numpy(), index=frame.index)
    values = np.asarray(y, dtype=float)
    if values.ndim != 1 or len(values) != len(frame):
        raise ValueError("y must be one-dimensional and match data length")
    return pd.Series(values, index=frame.index, name=target_col)


def _dates(
    data: pd.DataFrame | pd.Series,
    dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None,
    date_col: str | None,
) -> pd.DatetimeIndex:
    frame = _as_frame(data)
    if dates is not None:
        result = pd.DatetimeIndex(pd.to_datetime(dates))
    elif date_col and date_col in frame:
        result = pd.DatetimeIndex(pd.to_datetime(frame[date_col]))
    elif "date" in frame:
        result = pd.DatetimeIndex(pd.to_datetime(frame["date"]))
    elif "DATE" in frame:
        result = pd.DatetimeIndex(pd.to_datetime(frame["DATE"]))
    elif isinstance(frame.index, pd.DatetimeIndex):
        result = frame.index
    else:
        raise ValueError("dates are required (argument, date column, or DatetimeIndex)")
    if len(result) != len(frame):
        raise ValueError("dates and data must have the same length")
    return result


def _boolean_mask(
    mask: str | Sequence[bool] | pd.Series | None,
    frame: pd.DataFrame,
) -> pd.Series:
    if mask is None:
        return pd.Series(True, index=frame.index)
    if isinstance(mask, str):
        if mask not in frame:
            raise KeyError(f"mask column not found: {mask}")
        values = frame[mask]
    elif isinstance(mask, pd.Series) and mask.index.equals(frame.index):
        values = mask
    else:
        values = pd.Series(mask, index=frame.index)
    if len(values) != len(frame):
        raise ValueError("mask and data must have the same length")
    if pd.api.types.is_bool_dtype(values):
        return values.fillna(False).astype(bool)
    normalized = values.map(
        lambda value: (
            {"true": True, "false": False, "1": True, "0": False}.get(
                value.strip().lower(), bool(value)
            )
            if isinstance(value, str)
            else value
        )
    )
    return normalized.fillna(False).astype(bool)


def _climatological_doy(dates: pd.DatetimeIndex) -> np.ndarray:
    """Map month/day to a stable 366-day calendar (leap reference year 2000)."""

    return np.asarray(
        [pd.Timestamp(2000, value.month, value.day).dayofyear for value in dates],
        dtype=int,
    )


def _seasonal_features(
    dates: pd.DatetimeIndex,
    index: pd.Index,
    harmonics: int,
) -> pd.DataFrame:
    days_in_year = np.where(dates.is_leap_year, 366.0, 365.0)
    phase = 2.0 * np.pi * (dates.dayofyear.to_numpy(dtype=float) - 1.0) / days_in_year
    result: dict[str, np.ndarray] = {}
    for harmonic in range(1, harmonics + 1):
        result[f"doy_sin_{harmonic}"] = np.sin(harmonic * phase)
        result[f"doy_cos_{harmonic}"] = np.cos(harmonic * phase)
    return pd.DataFrame(result, index=index)


def _feature_frame(
    data: pd.DataFrame,
    dates: pd.DatetimeIndex,
    feature_cols: Sequence[str],
    harmonics: int,
    interaction_cols: Sequence[str] = (),
) -> pd.DataFrame:
    missing = [column for column in feature_cols if column not in data]
    if missing:
        raise KeyError(f"feature columns not found: {missing}")
    features = _seasonal_features(dates, data.index, harmonics)
    for column in feature_cols:
        features[column] = pd.to_numeric(data[column], errors="coerce")
    seasonal_columns = [column for column in features if column.startswith("doy_")]
    for column in interaction_cols:
        if column not in feature_cols:
            continue
        for seasonal_column in seasonal_columns:
            features[f"{column}_x_{seasonal_column}"] = (
                features[column] * features[seasonal_column]
            )
    return features


def _fit_feature_medians(features: pd.DataFrame, mask: pd.Series) -> pd.Series:
    medians = features.loc[mask].median(axis=0, skipna=True)
    return medians.fillna(0.0)


def _filled_features(features: pd.DataFrame, medians: pd.Series) -> np.ndarray:
    return features.reindex(columns=medians.index).fillna(medians).to_numpy(dtype=float)


class ClimatologyBaseline:
    """Training-period day-of-year median using a circular ``DOY +/- window``."""

    name = "climatology"
    offline = False

    def __init__(
        self,
        target_col: str | None = None,
        *,
        window: int = 7,
        date_col: str | None = "date",
    ) -> None:
        if window < 0 or window > 182:
            raise ValueError("window must be between 0 and 182 days")
        self.target_col = target_col
        self.window = int(window)
        self.date_col = date_col

    def fit(
        self,
        data: pd.DataFrame | pd.Series,
        y: str | Sequence[float] | pd.Series | None = None,
        *,
        dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None = None,
        train_mask: str | Sequence[bool] | pd.Series | None = None,
    ) -> "ClimatologyBaseline":
        frame = _as_frame(data)
        target = _target_series(data, y, self.target_col)
        fit_dates = _dates(data, dates, self.date_col)
        eligible = _boolean_mask(train_mask, frame) & target.notna()
        if not eligible.any():
            raise ValueError("no finite training targets are available")
        train_values = target.loc[eligible].to_numpy(dtype=float)
        train_doy = _climatological_doy(fit_dates[eligible.to_numpy()])
        fallback = float(np.median(train_values))
        values = np.empty(366, dtype=float)
        for doy in range(1, 367):
            distance = np.abs(train_doy - doy)
            distance = np.minimum(distance, 366 - distance)
            local = train_values[distance <= self.window]
            values[doy - 1] = float(np.median(local)) if local.size else fallback
        self.climatology_ = pd.Series(values, index=np.arange(1, 367), name="climatology")
        self.fallback_ = fallback
        return self

    def predict(
        self,
        data: pd.DataFrame | pd.Series,
        *,
        dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None = None,
    ) -> pd.Series:
        if not hasattr(self, "climatology_"):
            raise RuntimeError("fit must be called before predict")
        frame = _as_frame(data)
        predict_dates = _dates(data, dates, self.date_col)
        doys = _climatological_doy(predict_dates)
        values = self.climatology_.reindex(doys).to_numpy(dtype=float)
        return pd.Series(values, index=frame.index, name=self.target_col)


class OfflineLinearInterpolation:
    """Two-sided linear interpolation; edge gaps remain missing."""

    name = "linear"
    offline = True

    def __init__(self, target_col: str | None = None, *, online: bool = False) -> None:
        if online:
            raise ValueError("linear interpolation is an offline-only baseline")
        self.target_col = target_col

    def fit(
        self,
        data: pd.DataFrame | pd.Series,
        y: str | Sequence[float] | pd.Series | None = None,
        **_: object,
    ) -> "OfflineLinearInterpolation":
        if isinstance(y, str):
            self.target_col = y
        return self

    def predict(
        self,
        data: pd.DataFrame | pd.Series,
        *,
        target: str | None = None,
        dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None = None,
    ) -> pd.Series:
        frame = _as_frame(data)
        series = _target_series(data, target, self.target_col).astype(float)
        if dates is not None:
            x = pd.DatetimeIndex(pd.to_datetime(dates)).view("i8").astype(float)
        elif isinstance(series.index, pd.DatetimeIndex):
            x = series.index.view("i8").astype(float)
        elif "date" in frame or "DATE" in frame:
            x = _dates(data, None, "date" if "date" in frame else "DATE").view("i8").astype(float)
        else:
            x = np.arange(len(series), dtype=float)
        known = np.isfinite(series.to_numpy(dtype=float))
        result = np.full(len(series), np.nan, dtype=float)
        if known.any():
            result[known] = series.to_numpy(dtype=float)[known]
        if known.sum() >= 2:
            inside = (~known) & (x > x[known].min()) & (x < x[known].max())
            result[inside] = np.interp(x[inside], x[known], result[known])
        return pd.Series(result, index=series.index, name=series.name)


class PCHIPInterpolation:
    """Shape-preserving two-sided cubic interpolation without extrapolation."""

    name = "pchip"
    offline = True

    def __init__(self, target_col: str | None = None, *, online: bool = False) -> None:
        if online:
            raise ValueError("PCHIP interpolation is an offline-only baseline")
        self.target_col = target_col

    def fit(
        self,
        data: pd.DataFrame | pd.Series,
        y: str | Sequence[float] | pd.Series | None = None,
        **_: object,
    ) -> "PCHIPInterpolation":
        if isinstance(y, str):
            self.target_col = y
        return self

    def predict(
        self,
        data: pd.DataFrame | pd.Series,
        *,
        target: str | None = None,
        dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None = None,
    ) -> pd.Series:
        series = _target_series(data, target, self.target_col).astype(float)
        if dates is not None:
            parsed_dates = pd.DatetimeIndex(pd.to_datetime(dates))
            x = (parsed_dates - parsed_dates[0]).total_seconds().to_numpy(dtype=float)
        elif isinstance(series.index, pd.DatetimeIndex):
            x = (series.index - series.index[0]).total_seconds().to_numpy(dtype=float)
        else:
            x = np.arange(len(series), dtype=float)
        values = series.to_numpy(dtype=float)
        known = np.isfinite(values)
        result = values.copy()
        if known.sum() >= 2:
            interpolator = PchipInterpolator(x[known], values[known], extrapolate=False)
            missing = ~known
            result[missing] = interpolator(x[missing])
        return pd.Series(result, index=series.index, name=series.name)


class KalmanSmootherBaseline:
    """Local-linear-trend Kalman smoother based on ``statsmodels``."""

    name = "kalman"
    offline = True

    def __init__(self, target_col: str | None = None, *, maxiter: int = 200) -> None:
        self.target_col = target_col
        self.maxiter = int(maxiter)

    @staticmethod
    def _model(values: np.ndarray):
        from statsmodels.tsa.statespace.structural import UnobservedComponents

        return UnobservedComponents(values, level="local linear trend")

    def fit(
        self,
        data: pd.DataFrame | pd.Series,
        y: str | Sequence[float] | pd.Series | None = None,
        *,
        train_mask: str | Sequence[bool] | pd.Series | None = None,
    ) -> "KalmanSmootherBaseline":
        frame = _as_frame(data)
        target = _target_series(data, y, self.target_col).astype(float)
        eligible = _boolean_mask(train_mask, frame) & target.notna()
        values = target.where(eligible).to_numpy(dtype=float)
        if np.isfinite(values).sum() < 4:
            raise ValueError("at least four finite training values are required")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = self._model(values).fit(disp=False, maxiter=self.maxiter)
        self.params_ = np.asarray(result.params, dtype=float)
        return self

    def predict(
        self,
        data: pd.DataFrame | pd.Series,
        *,
        target: str | None = None,
    ) -> pd.Series:
        series = _target_series(data, target, self.target_col).astype(float)
        values = series.to_numpy(dtype=float)
        if np.isfinite(values).sum() < 2:
            return series.copy()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = self._model(values)
                if hasattr(self, "params_"):
                    result = model.smooth(self.params_)
                else:
                    result = model.fit(disp=False, maxiter=self.maxiter)
            smoothed = np.asarray(result.smoothed_state[0], dtype=float)
            return pd.Series(smoothed, index=series.index, name=series.name)
        except (ValueError, np.linalg.LinAlgError):
            return OfflineLinearInterpolation(self.target_col).predict(series)


class SeasonalRidgeBaseline:
    """Ridge regression with Fourier seasonality and named external features."""

    name = "seasonal_ridge"
    offline = False

    def __init__(
        self,
        feature_cols: Sequence[str],
        target_col: str | None = None,
        *,
        date_col: str | None = "date",
        harmonics: int = 3,
        alpha: float = 1.0,
        interaction_cols: Sequence[str] = (),
    ) -> None:
        self.feature_cols = tuple(feature_cols)
        self.target_col = target_col
        self.date_col = date_col
        self.harmonics = int(harmonics)
        self.alpha = float(alpha)
        self.interaction_cols = tuple(interaction_cols)

    def _features(
        self,
        data: pd.DataFrame,
        dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None,
    ) -> pd.DataFrame:
        parsed_dates = _dates(data, dates, self.date_col)
        return _feature_frame(
            data,
            parsed_dates,
            self.feature_cols,
            self.harmonics,
            self.interaction_cols,
        )

    def fit(
        self,
        data: pd.DataFrame,
        y: str | Sequence[float] | pd.Series | None = None,
        *,
        dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None = None,
        train_mask: str | Sequence[bool] | pd.Series | None = None,
    ) -> "SeasonalRidgeBaseline":
        frame = _as_frame(data)
        target = _target_series(data, y, self.target_col).astype(float)
        eligible = _boolean_mask(train_mask, frame) & target.notna()
        if not eligible.any():
            raise ValueError("no finite training targets are available")
        features = self._features(frame, dates)
        self.feature_medians_ = _fit_feature_medians(features, eligible)
        self.model_ = make_pipeline(StandardScaler(), Ridge(alpha=self.alpha))
        self.model_.fit(
            _filled_features(features.loc[eligible], self.feature_medians_),
            target.loc[eligible].to_numpy(dtype=float),
        )
        return self

    def predict(
        self,
        data: pd.DataFrame,
        *,
        dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None = None,
    ) -> pd.Series:
        if not hasattr(self, "model_"):
            raise RuntimeError("fit must be called before predict")
        frame = _as_frame(data)
        features = self._features(frame, dates)
        prediction = self.model_.predict(_filled_features(features, self.feature_medians_))
        return pd.Series(prediction, index=frame.index, name=self.target_col)


class AirOnlyBaseline(SeasonalRidgeBaseline):
    """Seasonal, varying-coefficient water-temperature/air-temperature model."""

    name = "air_only"

    def __init__(
        self,
        air_col: str,
        target_col: str | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(
            [air_col],
            target_col,
            interaction_cols=[air_col],
            **kwargs,
        )


class AirHydroBaseline(SeasonalRidgeBaseline):
    """Air-only baseline augmented with same-site flow and/or water level."""

    name = "air_hydro"

    def __init__(
        self,
        air_col: str,
        hydro_cols: Sequence[str],
        target_col: str | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(
            [air_col, *hydro_cols],
            target_col,
            interaction_cols=[air_col],
            **kwargs,
        )


class DonorRegressionBaseline:
    """Seasonal donor regression with each lag selected on training data only.

    A positive lag means that the donor at ``t - lag`` predicts the target at
    ``t``.  Negative lags are useful only for offline reconstruction and can be
    excluded by passing a non-negative ``candidate_lags`` sequence.
    """

    name = "donor_regression"

    def __init__(
        self,
        donor_cols: Sequence[str],
        target_col: str | None = None,
        *,
        covariate_cols: Sequence[str] = (),
        candidate_lags: Iterable[int] = range(-30, 31),
        date_col: str | None = "date",
        harmonics: int = 3,
        alpha: float = 1.0,
    ) -> None:
        if not donor_cols:
            raise ValueError("at least one donor column is required")
        self.donor_cols = tuple(donor_cols)
        self.target_col = target_col
        self.covariate_cols = tuple(covariate_cols)
        self.candidate_lags = tuple(int(lag) for lag in candidate_lags)
        if not self.candidate_lags:
            raise ValueError("candidate_lags cannot be empty")
        self.date_col = date_col
        self.harmonics = int(harmonics)
        self.alpha = float(alpha)

    def _select_lag(
        self,
        donor: pd.Series,
        target: pd.Series,
        train_mask: pd.Series,
    ) -> int:
        best_lag = 0 if 0 in self.candidate_lags else self.candidate_lags[0]
        best_key = (-np.inf, -np.inf, -np.inf)
        for lag in self.candidate_lags:
            shifted = donor.shift(lag)
            source_is_train = train_mask.shift(lag, fill_value=False)
            valid = train_mask & source_is_train & target.notna() & shifted.notna()
            if valid.sum() < 3:
                score = -np.inf
            else:
                target_values = target.loc[valid].to_numpy(dtype=float)
                donor_values = shifted.loc[valid].to_numpy(dtype=float)
                if np.std(target_values) == 0 or np.std(donor_values) == 0:
                    score = -np.inf
                else:
                    score = abs(float(np.corrcoef(target_values, donor_values)[0, 1]))
            key = (score, -abs(lag), -lag)
            if key > best_key:
                best_lag, best_key = lag, key
        return int(best_lag)

    def _features(
        self,
        data: pd.DataFrame,
        dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None,
    ) -> pd.DataFrame:
        parsed_dates = _dates(data, dates, self.date_col)
        features = _seasonal_features(parsed_dates, data.index, self.harmonics)
        for donor in self.donor_cols:
            features[f"{donor}_lag_{self.selected_lags_[donor]}"] = pd.to_numeric(
                data[donor], errors="coerce"
            ).shift(self.selected_lags_[donor])
        for column in self.covariate_cols:
            features[column] = pd.to_numeric(data[column], errors="coerce")
        return features

    def fit(
        self,
        data: pd.DataFrame,
        y: str | Sequence[float] | pd.Series | None = None,
        *,
        dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None = None,
        train_mask: str | Sequence[bool] | pd.Series | None = None,
    ) -> "DonorRegressionBaseline":
        frame = _as_frame(data)
        missing = [column for column in [*self.donor_cols, *self.covariate_cols] if column not in frame]
        if missing:
            raise KeyError(f"feature columns not found: {missing}")
        target = _target_series(data, y, self.target_col).astype(float)
        eligible = _boolean_mask(train_mask, frame)
        self.selected_lags_ = {
            donor: self._select_lag(
                pd.to_numeric(frame[donor], errors="coerce"), target, eligible
            )
            for donor in self.donor_cols
        }
        features = self._features(frame, dates)
        fit_rows = eligible & target.notna()
        if not fit_rows.any():
            raise ValueError("no finite training targets are available")
        self.feature_medians_ = _fit_feature_medians(features, fit_rows)
        self.model_ = make_pipeline(StandardScaler(), Ridge(alpha=self.alpha))
        self.model_.fit(
            _filled_features(features.loc[fit_rows], self.feature_medians_),
            target.loc[fit_rows].to_numpy(dtype=float),
        )
        return self

    def predict(
        self,
        data: pd.DataFrame,
        *,
        dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None = None,
    ) -> pd.Series:
        if not hasattr(self, "model_"):
            raise RuntimeError("fit must be called before predict")
        frame = _as_frame(data)
        features = self._features(frame, dates)
        values = self.model_.predict(_filled_features(features, self.feature_medians_))
        return pd.Series(values, index=frame.index, name=self.target_col)


class RandomForestBaseline:
    """Random-forest regression on seasonal and explicitly named features."""

    name = "random_forest"

    def __init__(
        self,
        feature_cols: Sequence[str],
        target_col: str | None = None,
        *,
        date_col: str | None = "date",
        harmonics: int = 3,
        n_estimators: int = 200,
        min_samples_leaf: int = 2,
        random_state: int = 0,
        n_jobs: int = 1,
    ) -> None:
        self.feature_cols = tuple(feature_cols)
        self.target_col = target_col
        self.date_col = date_col
        self.harmonics = int(harmonics)
        self.model_params = {
            "n_estimators": int(n_estimators),
            "min_samples_leaf": int(min_samples_leaf),
            "random_state": int(random_state),
            "n_jobs": int(n_jobs),
        }

    def _features(
        self,
        data: pd.DataFrame,
        dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None,
    ) -> pd.DataFrame:
        return _feature_frame(
            data,
            _dates(data, dates, self.date_col),
            self.feature_cols,
            self.harmonics,
        )

    def fit(
        self,
        data: pd.DataFrame,
        y: str | Sequence[float] | pd.Series | None = None,
        *,
        dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None = None,
        train_mask: str | Sequence[bool] | pd.Series | None = None,
    ) -> "RandomForestBaseline":
        frame = _as_frame(data)
        target = _target_series(frame, y, self.target_col).astype(float)
        eligible = _boolean_mask(train_mask, frame) & target.notna()
        if not eligible.any():
            raise ValueError("no finite training targets are available")
        features = self._features(frame, dates)
        self.feature_medians_ = _fit_feature_medians(features, eligible)
        self.model_ = RandomForestRegressor(**self.model_params)
        self.model_.fit(
            _filled_features(features.loc[eligible], self.feature_medians_),
            target.loc[eligible].to_numpy(dtype=float),
        )
        return self

    def predict(
        self,
        data: pd.DataFrame,
        *,
        dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None = None,
    ) -> pd.Series:
        if not hasattr(self, "model_"):
            raise RuntimeError("fit must be called before predict")
        frame = _as_frame(data)
        values = self.model_.predict(
            _filled_features(self._features(frame, dates), self.feature_medians_)
        )
        return pd.Series(values, index=frame.index, name=self.target_col)


class XGBoostBaseline(RandomForestBaseline):
    """XGBoost counterpart, available only when ``xgboost`` is installed."""

    name = "xgboost"

    def __init__(
        self,
        feature_cols: Sequence[str],
        target_col: str | None = None,
        *,
        date_col: str | None = "date",
        harmonics: int = 3,
        n_estimators: int = 300,
        max_depth: int = 4,
        learning_rate: float = 0.05,
        subsample: float = 0.9,
        colsample_bytree: float = 0.9,
        random_state: int = 0,
        n_jobs: int = 1,
    ) -> None:
        self.feature_cols = tuple(feature_cols)
        self.target_col = target_col
        self.date_col = date_col
        self.harmonics = int(harmonics)
        self.model_params = {
            "n_estimators": int(n_estimators),
            "max_depth": int(max_depth),
            "learning_rate": float(learning_rate),
            "subsample": float(subsample),
            "colsample_bytree": float(colsample_bytree),
            "random_state": int(random_state),
            "n_jobs": int(n_jobs),
            "objective": "reg:squarederror",
            "verbosity": 0,
        }

    @staticmethod
    def is_available() -> bool:
        try:
            import xgboost  # noqa: F401
        except ImportError:
            return False
        return True

    def fit(
        self,
        data: pd.DataFrame,
        y: str | Sequence[float] | pd.Series | None = None,
        *,
        dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None = None,
        train_mask: str | Sequence[bool] | pd.Series | None = None,
    ) -> "XGBoostBaseline":
        try:
            from xgboost import XGBRegressor
        except ImportError as exc:
            raise ImportError("xgboost is not installed; skip the xgboost baseline") from exc
        frame = _as_frame(data)
        target = _target_series(frame, y, self.target_col).astype(float)
        eligible = _boolean_mask(train_mask, frame) & target.notna()
        if not eligible.any():
            raise ValueError("no finite training targets are available")
        features = self._features(frame, dates)
        self.feature_medians_ = _fit_feature_medians(features, eligible)
        self.model_ = XGBRegressor(**self.model_params)
        self.model_.fit(
            _filled_features(features.loc[eligible], self.feature_medians_),
            target.loc[eligible].to_numpy(dtype=float),
        )
        return self


class RatingCurveBaseline:
    """Operational flow recovery from same-site level via a polynomial curve."""

    name = "rating_curve"

    def __init__(
        self,
        level_col: str,
        target_col: str | None = None,
        *,
        degree: int = 2,
    ) -> None:
        if degree < 1:
            raise ValueError("degree must be positive")
        self.level_col = level_col
        self.target_col = target_col
        self.degree = int(degree)

    def fit(
        self,
        data: pd.DataFrame,
        y: str | Sequence[float] | pd.Series | None = None,
        *,
        train_mask: str | Sequence[bool] | pd.Series | None = None,
    ) -> "RatingCurveBaseline":
        frame = _as_frame(data)
        if self.level_col not in frame:
            raise KeyError(f"level column not found: {self.level_col}")
        level = pd.to_numeric(frame[self.level_col], errors="coerce")
        flow = _target_series(frame, y, self.target_col).astype(float)
        eligible = _boolean_mask(train_mask, frame) & level.notna() & flow.notna()
        if eligible.sum() <= self.degree:
            raise ValueError("not enough training pairs for the requested rating curve")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.coefficients_ = np.polyfit(
                level.loc[eligible].to_numpy(dtype=float),
                flow.loc[eligible].to_numpy(dtype=float),
                self.degree,
            )
        return self

    def predict(self, data: pd.DataFrame) -> pd.Series:
        if not hasattr(self, "coefficients_"):
            raise RuntimeError("fit must be called before predict")
        frame = _as_frame(data)
        level = pd.to_numeric(frame[self.level_col], errors="coerce").to_numpy(dtype=float)
        values = np.polyval(self.coefficients_, level)
        values[~np.isfinite(level)] = np.nan
        return pd.Series(values, index=frame.index, name=self.target_col)


class IndependentFlowBaseline(SeasonalRidgeBaseline):
    """Flow regression that explicitly forbids the target station's level."""

    name = "independent_flow"

    def __init__(
        self,
        feature_cols: Sequence[str],
        target_level_col: str,
        target_col: str | None = None,
        **kwargs: object,
    ) -> None:
        if target_level_col in feature_cols:
            raise ValueError(
                f"{target_level_col} is forbidden in the independent-flow baseline"
            )
        self.target_level_col = target_level_col
        super().__init__(feature_cols, target_col, **kwargs)


DOYClimatology = ClimatologyBaseline
LinearInterpolationBaseline = OfflineLinearInterpolation
PCHIPBaseline = PCHIPInterpolation
KalmanSmoother = KalmanSmootherBaseline
DonorRegression = DonorRegressionBaseline
RandomForestImputer = RandomForestBaseline
XGBoostImputer = XGBoostBaseline
RatingCurve = RatingCurveBaseline


BASELINE_REGISTRY: Mapping[str, type] = {
    "climatology": ClimatologyBaseline,
    "linear": OfflineLinearInterpolation,
    "pchip": PCHIPInterpolation,
    "kalman": KalmanSmootherBaseline,
    "air_only": AirOnlyBaseline,
    "air_hydro": AirHydroBaseline,
    "donor_regression": DonorRegressionBaseline,
    "random_forest": RandomForestBaseline,
    "xgboost": XGBoostBaseline,
    "rating_curve": RatingCurveBaseline,
    "independent_flow": IndependentFlowBaseline,
}


def make_baseline(name: str, **kwargs: object):
    """Construct a baseline by its stable command-line name."""

    try:
        baseline_class = BASELINE_REGISTRY[name.lower()]
    except KeyError as exc:
        choices = ", ".join(sorted(BASELINE_REGISTRY))
        raise ValueError(f"unknown baseline {name!r}; choose one of: {choices}") from exc
    return baseline_class(**kwargs)


__all__ = [
    "AirHydroBaseline",
    "AirOnlyBaseline",
    "BASELINE_REGISTRY",
    "ClimatologyBaseline",
    "DOYClimatology",
    "DonorRegression",
    "DonorRegressionBaseline",
    "IndependentFlowBaseline",
    "KalmanSmoother",
    "KalmanSmootherBaseline",
    "LinearInterpolationBaseline",
    "OfflineLinearInterpolation",
    "PCHIPBaseline",
    "PCHIPInterpolation",
    "RandomForestBaseline",
    "RandomForestImputer",
    "RatingCurve",
    "RatingCurveBaseline",
    "SeasonalRidgeBaseline",
    "XGBoostBaseline",
    "XGBoostImputer",
    "make_baseline",
]
