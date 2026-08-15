"""Masked point, hydrological, event, and probabilistic metrics.

Every public evaluator requires both ``quality_approved`` and
``artificial_mask``.  This makes it difficult to accidentally score natural
missing values or observations that were rejected during quality control.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.stats import rankdata


ArrayLike = Sequence[float] | Sequence[bool] | np.ndarray | pd.Series


def _numeric(values: ArrayLike, *, name: str) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    return pd.to_numeric(pd.Series(array), errors="coerce").to_numpy(dtype=float)


def _boolean(values: ArrayLike, *, name: str) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    series = pd.Series(array)
    if not pd.api.types.is_bool_dtype(series):
        series = series.map(
            lambda value: (
                {"true": True, "false": False, "1": True, "0": False}.get(
                    value.strip().lower(), bool(value)
                )
                if isinstance(value, str)
                else value
            )
        )
    return series.fillna(False).astype(bool).to_numpy()


def evaluation_mask(
    y_true: ArrayLike,
    y_pred: ArrayLike,
    quality_approved: ArrayLike,
    artificial_mask: ArrayLike,
) -> np.ndarray:
    """Return the only cells that may contribute to evaluation metrics."""

    truth = _numeric(y_true, name="y_true")
    prediction = _numeric(y_pred, name="y_pred")
    quality = _boolean(quality_approved, name="quality_approved")
    artificial = _boolean(artificial_mask, name="artificial_mask")
    lengths = {len(truth), len(prediction), len(quality), len(artificial)}
    if len(lengths) != 1:
        raise ValueError("truth, prediction, quality, and artificial masks must align")
    return quality & artificial & np.isfinite(truth) & np.isfinite(prediction)


def _correlation(observed: np.ndarray, simulated: np.ndarray) -> float:
    if len(observed) < 2 or np.std(observed) == 0 or np.std(simulated) == 0:
        return float("nan")
    return float(np.corrcoef(observed, simulated)[0, 1])


def _spearman(observed: np.ndarray, simulated: np.ndarray) -> float:
    if len(observed) < 2:
        return float("nan")
    observed_rank = rankdata(observed)
    simulated_rank = rankdata(simulated)
    return _correlation(observed_rank, simulated_rank)


def _safe_ratio(numerator: float, denominator: float) -> float:
    if not np.isfinite(denominator) or denominator == 0:
        return float("nan")
    return float(numerator / denominator)


def compute_metrics(
    y_true: ArrayLike,
    y_pred: ArrayLike,
    quality_approved: ArrayLike,
    artificial_mask: ArrayLike,
    *,
    climatology_pred: ArrayLike | None = None,
    normalization_iqr: float | None = None,
    normalization_std: float | None = None,
) -> dict[str, float | int]:
    """Compute common errors strictly on approved, artificially hidden cells.

    ``NMAE`` uses the observed interquartile range and ``NRMSE`` uses the
    population standard deviation unless explicit training-derived scales are
    supplied.  Skill is ``1 - MAE(model) / MAE(climatology)`` on common cells.
    """

    truth = _numeric(y_true, name="y_true")
    prediction = _numeric(y_pred, name="y_pred")
    selected = evaluation_mask(truth, prediction, quality_approved, artificial_mask)
    if not selected.any():
        return {
            "n": 0,
            "mae": float("nan"),
            "rmse": float("nan"),
            "bias": float("nan"),
            "pearson": float("nan"),
            "spearman": float("nan"),
            "nmae": float("nan"),
            "nrmse": float("nan"),
            "skill": float("nan"),
        }
    observed = truth[selected]
    simulated = prediction[selected]
    residual = simulated - observed
    mae_value = float(np.mean(np.abs(residual)))
    rmse_value = float(np.sqrt(np.mean(np.square(residual))))
    if normalization_iqr is None:
        q25, q75 = np.quantile(observed, [0.25, 0.75])
        normalization_iqr = float(q75 - q25)
    if normalization_std is None:
        normalization_std = float(np.std(observed, ddof=0))

    skill = float("nan")
    if climatology_pred is not None:
        climatology = _numeric(climatology_pred, name="climatology_pred")
        if len(climatology) != len(truth):
            raise ValueError("climatology_pred must align with y_true")
        common = selected & np.isfinite(climatology)
        if common.any():
            model_mae = float(np.mean(np.abs(prediction[common] - truth[common])))
            baseline_mae = float(np.mean(np.abs(climatology[common] - truth[common])))
            skill = 1.0 - _safe_ratio(model_mae, baseline_mae)

    return {
        "n": int(selected.sum()),
        "mae": mae_value,
        "rmse": rmse_value,
        "bias": float(np.mean(residual)),
        "pearson": _correlation(observed, simulated),
        "spearman": _spearman(observed, simulated),
        "nmae": _safe_ratio(mae_value, float(normalization_iqr)),
        "nrmse": _safe_ratio(rmse_value, float(normalization_std)),
        "skill": skill,
    }


def boundary_jump_metrics(
    y_true: ArrayLike,
    y_pred: ArrayLike,
    quality_approved: ArrayLike,
    artificial_mask: ArrayLike,
) -> dict[str, float]:
    """Mean discontinuity at the left and right sides of contiguous gaps."""

    truth = _numeric(y_true, name="y_true")
    prediction = _numeric(y_pred, name="y_pred")
    quality = _boolean(quality_approved, name="quality_approved")
    artificial = _boolean(artificial_mask, name="artificial_mask")
    if len({len(truth), len(prediction), len(quality), len(artificial)}) != 1:
        raise ValueError("all inputs must align")
    eligible_gap = quality & artificial & np.isfinite(truth)
    starts = np.flatnonzero(eligible_gap & ~np.r_[False, eligible_gap[:-1]])
    ends = np.flatnonzero(eligible_gap & ~np.r_[eligible_gap[1:], False])
    left_values: list[float] = []
    right_values: list[float] = []
    for start in starts:
        neighbor = start - 1
        if (
            neighbor >= 0
            and quality[neighbor]
            and not artificial[neighbor]
            and np.isfinite(truth[neighbor])
            and np.isfinite(prediction[start])
        ):
            left_values.append(abs(float(prediction[start] - truth[neighbor])))
    for end in ends:
        neighbor = end + 1
        if (
            neighbor < len(truth)
            and quality[neighbor]
            and not artificial[neighbor]
            and np.isfinite(truth[neighbor])
            and np.isfinite(prediction[end])
        ):
            right_values.append(abs(float(prediction[end] - truth[neighbor])))
    return {
        "boundary_jump_left": float(np.mean(left_values)) if left_values else float("nan"),
        "boundary_jump_right": float(np.mean(right_values)) if right_values else float("nan"),
    }


def _longest_run(values: np.ndarray) -> int:
    best = current = 0
    for value in values.astype(bool):
        if value:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return int(best)


def temperature_metrics(
    y_true: ArrayLike,
    y_pred: ArrayLike,
    quality_approved: ArrayLike,
    artificial_mask: ArrayLike,
    *,
    climatology_pred: ArrayLike | None = None,
    high_threshold: float | None = None,
    ecological_threshold: float | None = None,
    dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None = None,
    normalization_iqr: float | None = None,
    normalization_std: float | None = None,
) -> dict[str, float | int]:
    """Common metrics plus high-temperature and heat-event preservation."""

    truth = _numeric(y_true, name="y_true")
    prediction = _numeric(y_pred, name="y_pred")
    quality = _boolean(quality_approved, name="quality_approved")
    artificial = _boolean(artificial_mask, name="artificial_mask")
    result = compute_metrics(
        truth,
        prediction,
        quality,
        artificial,
        climatology_pred=climatology_pred,
        normalization_iqr=normalization_iqr,
        normalization_std=normalization_std,
    )
    selected = evaluation_mask(truth, prediction, quality, artificial)
    reference = quality & np.isfinite(truth)
    if high_threshold is None:
        high_threshold = (
            float(np.quantile(truth[reference], 0.90)) if reference.any() else float("nan")
        )
    extreme = selected & (truth >= high_threshold)
    result["high_temp_threshold"] = float(high_threshold)
    result["high_temp_n"] = int(extreme.sum())
    result["high_temp_mae"] = (
        float(np.mean(np.abs(prediction[extreme] - truth[extreme])))
        if extreme.any()
        else float("nan")
    )
    result["high_temp_bias"] = (
        float(np.mean(prediction[extreme] - truth[extreme]))
        if extreme.any()
        else float("nan")
    )
    result["extreme_peak_error"] = (
        float(np.max(prediction[extreme]) - np.max(truth[extreme]))
        if extreme.any()
        else float("nan")
    )

    threshold = high_threshold if ecological_threshold is None else float(ecological_threshold)
    result["threshold_days_bias"] = (
        int(np.sum(prediction[selected] >= threshold) - np.sum(truth[selected] >= threshold))
        if selected.any()
        else float("nan")
    )
    reconstructed = truth.copy()
    reconstructed[selected] = prediction[selected]
    valid_sequence = quality & np.isfinite(truth) & np.isfinite(reconstructed)
    true_hot = valid_sequence & (truth >= threshold)
    recovered_hot = valid_sequence & (reconstructed >= threshold)
    result["heatwave_duration_error"] = float(
        _longest_run(recovered_hot) - _longest_run(true_hot)
    )

    adjacent_artificial = artificial[1:] | artificial[:-1]
    valid_change = (
        quality[1:]
        & quality[:-1]
        & adjacent_artificial
        & np.isfinite(truth[1:])
        & np.isfinite(truth[:-1])
        & np.isfinite(reconstructed[1:])
        & np.isfinite(reconstructed[:-1])
    )
    true_change = np.diff(truth)
    recovered_change = np.diff(reconstructed)
    result["daily_change_mae"] = (
        float(np.mean(np.abs(recovered_change[valid_change] - true_change[valid_change])))
        if valid_change.any()
        else float("nan")
    )

    result["annual_max_error"] = float("nan")
    result["annual_peak_timing_error_days"] = float("nan")
    if dates is not None:
        parsed = pd.DatetimeIndex(pd.to_datetime(dates))
        if len(parsed) != len(truth):
            raise ValueError("dates must align with y_true")
        maximum_errors: list[float] = []
        timing_errors: list[float] = []
        for year in np.unique(parsed.year[selected]):
            year_mask = (parsed.year == year) & valid_sequence
            if not year_mask.any() or not np.any(selected & (parsed.year == year)):
                continue
            positions = np.flatnonzero(year_mask)
            true_position = positions[int(np.argmax(truth[positions]))]
            predicted_position = positions[int(np.argmax(reconstructed[positions]))]
            maximum_errors.append(
                float(reconstructed[predicted_position] - truth[true_position])
            )
            timing_errors.append(
                abs(float((parsed[predicted_position] - parsed[true_position]).days))
            )
        if maximum_errors:
            result["annual_max_error"] = float(np.mean(maximum_errors))
            result["annual_peak_timing_error_days"] = float(np.mean(timing_errors))
    return result


def _nse(observed: np.ndarray, simulated: np.ndarray) -> float:
    denominator = float(np.sum(np.square(observed - np.mean(observed))))
    if denominator == 0:
        return float("nan")
    return float(1.0 - np.sum(np.square(simulated - observed)) / denominator)


def _kge(observed: np.ndarray, simulated: np.ndarray) -> float:
    if len(observed) < 2:
        return float("nan")
    correlation = _correlation(observed, simulated)
    observed_std = float(np.std(observed, ddof=0))
    observed_mean = float(np.mean(observed))
    if not np.isfinite(correlation) or observed_std == 0 or observed_mean == 0:
        return float("nan")
    alpha = float(np.std(simulated, ddof=0) / observed_std)
    beta = float(np.mean(simulated) / observed_mean)
    return float(1.0 - np.sqrt((correlation - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2))


def flow_metrics(
    y_true: ArrayLike,
    y_pred: ArrayLike,
    quality_approved: ArrayLike,
    artificial_mask: ArrayLike,
    *,
    climatology_pred: ArrayLike | None = None,
    high_threshold: float | None = None,
    low_threshold: float | None = None,
    dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None = None,
    normalization_iqr: float | None = None,
    normalization_std: float | None = None,
) -> dict[str, float | int]:
    """Common errors plus water balance, PBIAS, NSE, KGE, and flow extremes."""

    truth = _numeric(y_true, name="y_true")
    prediction = _numeric(y_pred, name="y_pred")
    quality = _boolean(quality_approved, name="quality_approved")
    artificial = _boolean(artificial_mask, name="artificial_mask")
    result = compute_metrics(
        truth,
        prediction,
        quality,
        artificial,
        climatology_pred=climatology_pred,
        normalization_iqr=normalization_iqr,
        normalization_std=normalization_std,
    )
    selected = evaluation_mask(truth, prediction, quality, artificial)
    if not selected.any():
        result.update(
            {
                "log_mae": float("nan"),
                "volume_bias": float("nan"),
                "volume_bias_percent": float("nan"),
                "pbias": float("nan"),
                "nse": float("nan"),
                "kge": float("nan"),
                "high_flow_mae": float("nan"),
                "low_flow_mae": float("nan"),
                "peak_magnitude_error": float("nan"),
                "peak_timing_error_days": float("nan"),
            }
        )
        return result
    observed = truth[selected]
    simulated = prediction[selected]
    observed_volume = float(np.sum(observed))
    volume_bias = float(np.sum(simulated) - observed_volume)
    result["log_mae"] = float(
        np.mean(np.abs(np.log1p(np.clip(simulated, 0, None)) - np.log1p(np.clip(observed, 0, None))))
    )
    result["volume_bias"] = volume_bias
    result["volume_bias_percent"] = 100.0 * _safe_ratio(volume_bias, observed_volume)
    result["pbias"] = result["volume_bias_percent"]
    result["nse"] = _nse(observed, simulated)
    result["kge"] = _kge(observed, simulated)

    reference = quality & np.isfinite(truth)
    if high_threshold is None:
        high_threshold = float(np.quantile(truth[reference], 0.90)) if reference.any() else float("nan")
    if low_threshold is None:
        low_threshold = float(np.quantile(truth[reference], 0.10)) if reference.any() else float("nan")
    high = selected & (truth >= high_threshold)
    low = selected & (truth <= low_threshold)
    result["high_flow_mae"] = (
        float(np.mean(np.abs(prediction[high] - truth[high]))) if high.any() else float("nan")
    )
    result["low_flow_mae"] = (
        float(np.mean(np.abs(prediction[low] - truth[low]))) if low.any() else float("nan")
    )
    selected_positions = np.flatnonzero(selected)
    true_peak = selected_positions[int(np.argmax(truth[selected_positions]))]
    predicted_peak = selected_positions[int(np.argmax(prediction[selected_positions]))]
    result["peak_magnitude_error"] = float(prediction[predicted_peak] - truth[true_peak])
    if dates is None:
        result["peak_timing_error_days"] = float(abs(predicted_peak - true_peak))
    else:
        parsed = pd.DatetimeIndex(pd.to_datetime(dates))
        if len(parsed) != len(truth):
            raise ValueError("dates must align with y_true")
        result["peak_timing_error_days"] = abs(
            float((parsed[predicted_peak] - parsed[true_peak]).days)
        )
    return result


def level_metrics(
    y_true: ArrayLike,
    y_pred: ArrayLike,
    quality_approved: ArrayLike,
    artificial_mask: ArrayLike,
    *,
    climatology_pred: ArrayLike | None = None,
    high_threshold: float | None = None,
    dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None = None,
    normalization_iqr: float | None = None,
    normalization_std: float | None = None,
) -> dict[str, float | int]:
    """Common errors plus high-water duration, magnitude, and timing errors."""

    truth = _numeric(y_true, name="y_true")
    prediction = _numeric(y_pred, name="y_pred")
    quality = _boolean(quality_approved, name="quality_approved")
    artificial = _boolean(artificial_mask, name="artificial_mask")
    result = compute_metrics(
        truth,
        prediction,
        quality,
        artificial,
        climatology_pred=climatology_pred,
        normalization_iqr=normalization_iqr,
        normalization_std=normalization_std,
    )
    selected = evaluation_mask(truth, prediction, quality, artificial)
    reference = quality & np.isfinite(truth)
    if high_threshold is None:
        high_threshold = float(np.quantile(truth[reference], 0.90)) if reference.any() else float("nan")
    high = selected & (truth >= high_threshold)
    result["high_level_mae"] = (
        float(np.mean(np.abs(prediction[high] - truth[high]))) if high.any() else float("nan")
    )
    result["high_level_duration_bias"] = (
        int(np.sum(prediction[selected] >= high_threshold) - np.sum(truth[selected] >= high_threshold))
        if selected.any()
        else float("nan")
    )
    if not selected.any():
        result["peak_level_error"] = float("nan")
        result["peak_timing_error_days"] = float("nan")
        return result
    positions = np.flatnonzero(selected)
    true_peak = positions[int(np.argmax(truth[positions]))]
    predicted_peak = positions[int(np.argmax(prediction[positions]))]
    result["peak_level_error"] = float(prediction[predicted_peak] - truth[true_peak])
    if dates is None:
        result["peak_timing_error_days"] = float(abs(predicted_peak - true_peak))
    else:
        parsed = pd.DatetimeIndex(pd.to_datetime(dates))
        if len(parsed) != len(truth):
            raise ValueError("dates must align with y_true")
        result["peak_timing_error_days"] = abs(
            float((parsed[predicted_peak] - parsed[true_peak]).days)
        )
    return result


def pinball_loss(
    y_true: ArrayLike,
    y_quantile: ArrayLike,
    quantile: float,
    quality_approved: ArrayLike,
    artificial_mask: ArrayLike,
) -> float:
    """Mean pinball loss on the approved artificial cells."""

    if not 0 < quantile < 1:
        raise ValueError("quantile must be strictly between 0 and 1")
    truth = _numeric(y_true, name="y_true")
    prediction = _numeric(y_quantile, name="y_quantile")
    selected = evaluation_mask(truth, prediction, quality_approved, artificial_mask)
    if not selected.any():
        return float("nan")
    error = truth[selected] - prediction[selected]
    return float(np.mean(np.maximum(quantile * error, (quantile - 1.0) * error)))


def interval_metrics(
    y_true: ArrayLike,
    lower: ArrayLike,
    upper: ArrayLike,
    level: float,
    quality_approved: ArrayLike,
    artificial_mask: ArrayLike,
) -> dict[str, float]:
    """Coverage and mean width for one central prediction interval."""

    if not 0 < level < 1:
        raise ValueError("level must be strictly between 0 and 1")
    truth = _numeric(y_true, name="y_true")
    lower_values = _numeric(lower, name="lower")
    upper_values = _numeric(upper, name="upper")
    quality = _boolean(quality_approved, name="quality_approved")
    artificial = _boolean(artificial_mask, name="artificial_mask")
    if len({len(truth), len(lower_values), len(upper_values), len(quality), len(artificial)}) != 1:
        raise ValueError("all interval inputs must align")
    selected = (
        quality
        & artificial
        & np.isfinite(truth)
        & np.isfinite(lower_values)
        & np.isfinite(upper_values)
    )
    label = int(round(level * 100))
    if not selected.any():
        return {f"coverage_{label}": float("nan"), f"interval_width_{label}": float("nan")}
    lo = np.minimum(lower_values[selected], upper_values[selected])
    hi = np.maximum(lower_values[selected], upper_values[selected])
    return {
        f"coverage_{label}": float(np.mean((truth[selected] >= lo) & (truth[selected] <= hi))),
        f"interval_width_{label}": float(np.mean(hi - lo)),
    }


def _quantile_number(key: float | str) -> float:
    if isinstance(key, (int, float, np.integer, np.floating)):
        quantile = float(key)
    else:
        text = str(key).strip().lower()
        if text.startswith("q"):
            digits = text[1:]
            quantile = float(digits) / (10 ** len(digits))
        else:
            quantile = float(text)
    if not 0 < quantile < 1:
        raise ValueError(f"invalid quantile key: {key!r}")
    return quantile


def quantile_metrics(
    y_true: ArrayLike,
    quantile_predictions: Mapping[float | str, ArrayLike],
    quality_approved: ArrayLike,
    artificial_mask: ArrayLike,
) -> dict[str, float]:
    """Pinball losses, central interval calibration, and quantile CRPS.

    Approximate CRPS is twice the trapezoidal integral of pinball loss across
    the supplied quantiles.  At least two quantiles are required for CRPS.
    """

    if not quantile_predictions:
        return {"approx_crps": float("nan")}
    parsed: dict[float, np.ndarray] = {}
    for key, values in quantile_predictions.items():
        quantile = _quantile_number(key)
        if quantile in parsed:
            raise ValueError(f"duplicate quantile: {quantile}")
        parsed[quantile] = _numeric(values, name=f"quantile_{quantile}")
    truth = _numeric(y_true, name="y_true")
    quality = _boolean(quality_approved, name="quality_approved")
    artificial = _boolean(artificial_mask, name="artificial_mask")
    if any(len(values) != len(truth) for values in parsed.values()):
        raise ValueError("quantile predictions must align with y_true")
    result: dict[str, float] = {}
    for quantile, values in sorted(parsed.items()):
        label = f"q{int(round(100 * quantile)):02d}"
        result[f"pinball_{label}"] = pinball_loss(
            truth, values, quantile, quality, artificial
        )

    quantiles = sorted(parsed)
    for lower_quantile in quantiles:
        upper_quantile = 1.0 - lower_quantile
        matched = next((value for value in quantiles if np.isclose(value, upper_quantile)), None)
        if lower_quantile >= 0.5 or matched is None:
            continue
        level = matched - lower_quantile
        result.update(
            interval_metrics(
                truth,
                parsed[lower_quantile],
                parsed[matched],
                level,
                quality,
                artificial,
            )
        )

    common = quality & artificial & np.isfinite(truth)
    for values in parsed.values():
        common &= np.isfinite(values)
    if len(quantiles) < 2 or not common.any():
        result["approx_crps"] = float("nan")
    else:
        losses = []
        for quantile in quantiles:
            error = truth[common] - parsed[quantile][common]
            losses.append(np.maximum(quantile * error, (quantile - 1.0) * error))
        loss_matrix = np.stack(losses, axis=1)
        result["approx_crps"] = float(
            np.mean(2.0 * np.trapz(loss_matrix, x=np.asarray(quantiles), axis=1))
        )
    return result


calculate_metrics = compute_metrics
compute_regression_metrics = compute_metrics
masked_metrics = compute_metrics
boundary_jumps = boundary_jump_metrics


__all__ = [
    "boundary_jump_metrics",
    "boundary_jumps",
    "calculate_metrics",
    "compute_metrics",
    "compute_regression_metrics",
    "evaluation_mask",
    "flow_metrics",
    "interval_metrics",
    "level_metrics",
    "masked_metrics",
    "pinball_loss",
    "quantile_metrics",
    "temperature_metrics",
]
