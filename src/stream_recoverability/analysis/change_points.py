"""Auditable single-change estimators for serially dependent time series.

The module deliberately separates the classical Pettitt calculation from the
resampling assumptions used for inference.  A day-wise permutation is useful
as a reference calculation, but it is not a valid null for persistent daily
stream-temperature anomalies.  Callers can therefore permute user-supplied
contiguous blocks (calendar years in the P3 analysis) and bootstrap a change
date with circular moving blocks.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from scipy.stats import rankdata


def _finite_vector(values: Sequence[float] | np.ndarray) -> np.ndarray:
    vector = np.asarray(values, dtype=float)
    if vector.ndim != 1:
        raise ValueError("change-point input must be one-dimensional")
    if len(vector) < 4:
        raise ValueError("change-point input requires at least four values")
    if not np.isfinite(vector).all():
        raise ValueError("change-point input must contain only finite values")
    return vector


def _validate_min_segment(n: int, min_segment: int) -> int:
    value = int(min_segment)
    if value < 1:
        raise ValueError("min_segment must be positive")
    if 2 * value > n:
        raise ValueError("min_segment leaves no admissible split")
    return value


def _admissible_slice(n: int, min_segment: int) -> slice:
    """Indices of statistics for splits after observations 0, ..., n - 2."""

    minimum = _validate_min_segment(n, min_segment)
    return slice(minimum - 1, n - minimum)


def pettitt_change_point(
    values: Sequence[float] | np.ndarray,
    *,
    min_segment: int = 1,
) -> dict[str, Any]:
    """Estimate one rank-based location change with Pettitt's statistic.

    ``change_index`` is the first observation in the second segment.  Thus a
    value of 300 denotes a split between observations 299 and 300.  The
    reported asymptotic p-value is the common Pettitt approximation and assumes
    independent observations; it is retained only for comparability.
    """

    vector = _finite_vector(values)
    n = len(vector)
    admissible = _admissible_slice(n, min_segment)
    ranks = rankdata(vector, method="average")
    positions = np.arange(1, n + 1, dtype=float)
    process = 2.0 * np.cumsum(ranks) - positions * (n + 1.0)
    candidate = np.abs(process[admissible])
    split_after_index = int(admissible.start + np.argmax(candidate))
    statistic = float(abs(process[split_after_index]))
    maximizing = (
        np.flatnonzero(np.isclose(candidate, statistic, rtol=0.0, atol=1e-12))
        + int(admissible.start)
        + 1
    )
    approximation = 2.0 * np.exp(-6.0 * statistic**2 / (float(n) ** 3 + float(n) ** 2))
    return {
        "method": "pettitt_rank_location_change",
        "change_index": split_after_index + 1,
        "split_after_index": split_after_index,
        "statistic": statistic,
        "signed_statistic": float(process[split_after_index]),
        "maximizing_change_indices": maximizing.astype(int),
        "asymptotic_p_value_iid": float(min(1.0, approximation)),
        "n": n,
        "min_segment": int(min_segment),
        "process": process,
    }


def least_squares_change_point(
    values: Sequence[float] | np.ndarray,
    *,
    min_segment: int = 1,
) -> dict[str, Any]:
    """Estimate one mean change by the binary-segmentation/CUSUM objective."""

    vector = _finite_vector(values)
    n = len(vector)
    admissible = _admissible_slice(n, min_segment)
    segment_sizes = np.arange(1, n, dtype=float)
    cumulative = np.cumsum(vector)
    score = np.square(cumulative[:-1] - segment_sizes * cumulative[-1] / n) / (
        segment_sizes * (1.0 - segment_sizes / n)
    )
    candidate = score[admissible]
    split_after_index = int(admissible.start + np.argmax(candidate))
    statistic = float(score[split_after_index])
    maximizing = (
        np.flatnonzero(np.isclose(candidate, statistic, rtol=1e-12, atol=1e-12))
        + int(admissible.start)
        + 1
    )
    return {
        "method": "single_binary_segmentation_least_squares",
        "change_index": split_after_index + 1,
        "split_after_index": split_after_index,
        "statistic": statistic,
        "maximizing_change_indices": maximizing.astype(int),
        "n": n,
        "min_segment": int(min_segment),
        "process": score,
    }


def permutation_p_value(
    values: Sequence[float] | np.ndarray,
    estimator: Callable[..., dict[str, Any]],
    *,
    n_permutations: int,
    seed: int,
    min_segment: int = 1,
    block_labels: Sequence[object] | np.ndarray | None = None,
) -> dict[str, Any]:
    """Monte Carlo randomisation p-value for a change-point statistic.

    With no ``block_labels``, individual observations are exchangeable.  With
    labels, each label must identify one contiguous run and complete runs are
    reordered, retaining their internal values and serial dependence.
    """

    vector = _finite_vector(values)
    if n_permutations < 1:
        raise ValueError("n_permutations must be positive")
    observed = estimator(vector, min_segment=min_segment)
    if block_labels is None:
        blocks = None
        block_count = len(vector)
        scheme = "individual_observation_permutation_iid_reference"
    else:
        labels = np.asarray(block_labels)
        if labels.ndim != 1 or len(labels) != len(vector):
            raise ValueError("block_labels must be one-dimensional and match values")
        boundaries = np.r_[
            0, np.flatnonzero(labels[1:] != labels[:-1]) + 1, len(labels)
        ]
        blocks = [
            np.arange(boundaries[index], boundaries[index + 1], dtype=int)
            for index in range(len(boundaries) - 1)
        ]
        run_labels = [labels[block[0]] for block in blocks]
        if len(set(run_labels)) != len(run_labels):
            raise ValueError("each block label must occupy exactly one contiguous run")
        if len(blocks) < 2:
            raise ValueError("block permutation requires at least two blocks")
        block_count = len(blocks)
        scheme = "contiguous_block_order_permutation"

    rng = np.random.default_rng(seed)
    exceedances = 0
    observed_statistic = float(observed["statistic"])
    for _ in range(int(n_permutations)):
        if blocks is None:
            permuted = rng.permutation(vector)
        else:
            ordering = rng.permutation(block_count)
            permuted = np.concatenate([vector[blocks[index]] for index in ordering])
        statistic = float(estimator(permuted, min_segment=min_segment)["statistic"])
        exceedances += int(statistic >= observed_statistic)
    return {
        "p_value": float((exceedances + 1) / (n_permutations + 1)),
        "exceedances": int(exceedances),
        "n_permutations": int(n_permutations),
        "seed": int(seed),
        "scheme": scheme,
        "block_count": int(block_count),
        "observed_statistic": observed_statistic,
        "monte_carlo_minimum_p": float(1.0 / (n_permutations + 1)),
    }


def _circular_moving_block_sample(
    residuals: np.ndarray,
    *,
    block_length: int,
    rng: np.random.Generator,
) -> np.ndarray:
    length = len(residuals)
    effective_block_length = min(int(block_length), length)
    block_count = int(np.ceil(length / effective_block_length))
    starts = rng.integers(0, length, size=block_count)
    offsets = np.arange(effective_block_length)
    return np.concatenate([residuals[(start + offsets) % length] for start in starts])[
        :length
    ]


def residual_block_bootstrap_change_points(
    values: Sequence[float] | np.ndarray,
    estimator: Callable[..., dict[str, Any]],
    *,
    n_bootstrap: int,
    block_length: int,
    seed: int,
    min_segment: int = 1,
    center: str = "mean",
) -> dict[str, Any]:
    """Percentile-bootstrap a fitted single-change date with moving blocks.

    Residual blocks are sampled independently within the two fitted segments,
    retaining the fitted step and allowing segment-specific residual scale.
    Circular sampling avoids privileging particular residual endpoints.
    """

    vector = _finite_vector(values)
    if n_bootstrap < 1:
        raise ValueError("n_bootstrap must be positive")
    if block_length < 1:
        raise ValueError("block_length must be positive")
    if center not in {"mean", "median"}:
        raise ValueError("center must be 'mean' or 'median'")
    fitted = estimator(vector, min_segment=min_segment)
    change_index = int(fitted["change_index"])
    location = np.mean if center == "mean" else np.median
    first = vector[:change_index]
    second = vector[change_index:]
    first_level = float(location(first))
    second_level = float(location(second))
    first_residual = first - first_level
    second_residual = second - second_level
    rng = np.random.default_rng(seed)
    draws = np.empty(int(n_bootstrap), dtype=int)
    for draw in range(int(n_bootstrap)):
        simulated = np.concatenate(
            [
                first_level
                + _circular_moving_block_sample(
                    first_residual, block_length=block_length, rng=rng
                ),
                second_level
                + _circular_moving_block_sample(
                    second_residual, block_length=block_length, rng=rng
                ),
            ]
        )
        draws[draw] = int(estimator(simulated, min_segment=min_segment)["change_index"])
    lower, median, upper = np.quantile(
        draws, [0.025, 0.5, 0.975], method="nearest"
    ).astype(int)
    return {
        "change_indices": draws,
        "ci_lower_index": int(lower),
        "bootstrap_median_index": int(median),
        "ci_upper_index": int(upper),
        "n_bootstrap": int(n_bootstrap),
        "block_length": int(block_length),
        "seed": int(seed),
        "center": center,
        "scheme": "segmentwise_circular_moving_block_residual_bootstrap",
        "fitted_first_level": first_level,
        "fitted_second_level": second_level,
        "fitted_level_change": second_level - first_level,
    }


def autocorrelation(
    values: Sequence[float] | np.ndarray,
    lag: int,
) -> float:
    """Pearson autocorrelation at one named positive lag."""

    vector = _finite_vector(values)
    if lag < 1 or lag >= len(vector):
        raise ValueError("lag must be positive and smaller than the series")
    return float(np.corrcoef(vector[:-lag], vector[lag:])[0, 1])
