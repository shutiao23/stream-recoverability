"""Gaussian conditional-observability operator for hidden gap blocks.

The operator is the Schur complement of a second-order covariance.  It is the
proposed structural recoverability predictor.  The legacy additive
``d/4`` heuristic is not an implementation of this operator.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd

GAUSSIAN_MAE_FACTOR = float(np.sqrt(2.0 / np.pi))
DEFAULT_RIDGE = 1e-8
INFORMATION_SETS = ("none", "B", "D", "B_union_D")
INFORMATION_PLAYER_ORDER = ("B", "D", "M", "H")
DEFAULT_LOEWNER_ATOL = 1e-7


def _as_square(matrix: np.ndarray, *, name: str) -> np.ndarray:
    array = np.asarray(matrix, dtype=float)
    if array.ndim != 2 or array.shape[0] != array.shape[1]:
        raise ValueError(f"{name} must be a square matrix")
    return array


def ridge_psd(matrix: np.ndarray, ridge: float = DEFAULT_RIDGE) -> np.ndarray:
    """Return a symmetric matrix with eigenvalues floored at ``ridge``."""

    array = 0.5 * (
        np.asarray(matrix, dtype=float) + np.asarray(matrix, dtype=float).T
    )
    if ridge < 0:
        raise ValueError("ridge must be non-negative")
    eigval, eigvec = np.linalg.eigh(array)
    eigval = np.maximum(eigval, float(ridge))
    return (eigvec * eigval) @ eigvec.T


def safe_logdet(matrix: np.ndarray, ridge: float = DEFAULT_RIDGE) -> float:
    """Log-determinant of a ridge-stabilized covariance."""

    stabilized = ridge_psd(matrix, ridge)
    sign, value = np.linalg.slogdet(stabilized)
    if sign <= 0:
        return float("nan")
    return float(value)


def schur_complement(
    sigma_gg: np.ndarray,
    sigma_go: np.ndarray,
    sigma_oo: np.ndarray,
    *,
    ridge: float = DEFAULT_RIDGE,
) -> np.ndarray:
    r"""Return \(\Sigma_{G\mid O}=\Sigma_{GG}-\Sigma_{GO}\Sigma_{OO}^{-1}\Sigma_{OG}\)."""

    hidden = _as_square(sigma_gg, name="sigma_gg")
    observed = _as_square(sigma_oo, name="sigma_oo")
    cross = np.asarray(sigma_go, dtype=float)
    if cross.shape != (hidden.shape[0], observed.shape[0]):
        raise ValueError("sigma_go must have shape (n_hidden, n_observed)")
    if observed.size == 0:
        return hidden.copy()
    regularized = ridge_psd(observed, ridge)
    try:
        solved = np.linalg.solve(regularized, cross.T)
    except np.linalg.LinAlgError:
        solved = np.linalg.pinv(regularized) @ cross.T
    residual = hidden - cross @ solved
    return ridge_psd(residual, ridge)


def expected_gaussian_mae(sigma: np.ndarray) -> float:
    r"""Mean \(E[|X_i|]\) for zero-mean Gaussians with covariance ``sigma``."""

    diagonal = np.clip(np.diag(np.asarray(sigma, dtype=float)), 0.0, None)
    if diagonal.size == 0:
        return float("nan")
    return float(np.mean(np.sqrt(diagonal)) * GAUSSIAN_MAE_FACTOR)


def recoverability_r(sigma_gg: np.ndarray, sigma_cond: np.ndarray) -> float:
    r"""Primary recoverability \(R=1-\sqrt{\overline{\mathrm{diag}}\,\Sigma_{G\mid O}/\overline{\mathrm{diag}}\,\Sigma_{G}}\).

    This is the v9 freeze primary summary.  ``predicted_skill`` remains the
    secondary Gaussian MAE-ratio skill.
    """

    hidden = _as_square(sigma_gg, name="sigma_gg")
    residual = _as_square(sigma_cond, name="sigma_cond")
    var_hidden = float(np.mean(np.clip(np.diag(hidden), 0.0, None)))
    var_residual = float(np.mean(np.clip(np.diag(residual), 0.0, None)))
    if var_hidden <= 0:
        return float("nan")
    return float(1.0 - np.sqrt(max(var_residual / var_hidden, 0.0)))


def loewner_leq(
    a: np.ndarray,
    b: np.ndarray,
    *,
    atol: float = DEFAULT_LOEWNER_ATOL,
) -> bool:
    r"""Return True if \(A\preceq B\), i.e. \(B-A\) is numerically PSD."""

    left = _as_square(a, name="a")
    right = _as_square(b, name="b")
    if left.shape != right.shape:
        raise ValueError("loewner_leq requires matching shapes")
    diff = right - left
    diff = 0.5 * (diff + diff.T)
    return bool(np.min(np.linalg.eigvalsh(diff)) >= -float(atol))


def residual_quantile_width(
    samples: np.ndarray,
    *,
    lower: float = 0.1,
    upper: float = 0.9,
) -> float:
    """Residual quantile width. Fallback if Gaussian PIT/QQ is rejected.

    Not the primary estimand.  Keep ``recoverability_r`` / ``predicted_skill``
    under the second-order operator unless the Gaussian model fails; this
    width is only a monotone residual summary in that fallback.
    """

    if not 0.0 <= float(lower) < float(upper) <= 1.0:
        raise ValueError("quantiles must satisfy 0 <= lower < upper <= 1")
    values = np.asarray(samples, dtype=float).reshape(-1)
    values = values[np.isfinite(values)]
    if values.size < 2:
        return float("nan")
    low, high = np.quantile(values, [float(lower), float(upper)])
    return float(high - low)


def coalition_label(
    players: Sequence[str],
    *,
    order: Sequence[str] = INFORMATION_PLAYER_ORDER,
) -> str:
    """Stable name for an information coalition, e.g. ``B_union_D``."""

    requested = {str(name) for name in players}
    ordered = [name for name in order if name in requested]
    if not ordered:
        return "none"
    if len(ordered) == 1:
        return ordered[0]
    return "_union_".join(ordered)


def conditional_summaries(
    sigma_gg: np.ndarray,
    sigma_cond: np.ndarray,
) -> dict[str, float]:
    """Trace, log-det, variance, primary R, and expected-MAE summaries."""

    hidden = _as_square(sigma_gg, name="sigma_gg")
    residual = _as_square(sigma_cond, name="sigma_cond")
    trace_hidden = float(np.trace(hidden))
    trace_residual = float(np.trace(residual))
    var_hidden = float(np.mean(np.clip(np.diag(hidden), 0.0, None)))
    var_residual = float(np.mean(np.clip(np.diag(residual), 0.0, None)))
    mae_0 = expected_gaussian_mae(hidden)
    mae_s = expected_gaussian_mae(residual)
    ncv = float("nan") if var_hidden <= 0 else var_residual / var_hidden
    return {
        "trace_hidden": trace_hidden,
        "trace_conditional": trace_residual,
        "trace_ratio": (
            float("nan") if trace_hidden <= 0 else trace_residual / trace_hidden
        ),
        "normalized_conditional_variance": ncv,
        "operator_explained_variance": (
            float("nan") if not np.isfinite(ncv) else 1.0 - ncv
        ),
        "recoverability_r": recoverability_r(hidden, residual),
        "logdet_hidden": safe_logdet(hidden),
        "logdet_conditional": safe_logdet(residual),
        "logdet_reduction": safe_logdet(hidden) - safe_logdet(residual),
        "expected_mae_unconditional": mae_0,
        "expected_mae_conditional": mae_s,
        "predicted_skill": (
            float("nan") if not np.isfinite(mae_0) or mae_0 == 0 else 1.0 - mae_s / mae_0
        ),
        "predicted_conditional_risk": mae_s,
    }


def predicted_skill(sigma_gg: np.ndarray, sigma_cond: np.ndarray) -> float:
    """Gaussian MAE skill of the conditional mean versus climatology."""

    return conditional_summaries(sigma_gg, sigma_cond)["predicted_skill"]


def spectral_radius(matrix: np.ndarray) -> float:
    return float(np.max(np.abs(np.linalg.eigvals(np.asarray(matrix, dtype=float)))))


def stationary_covariance(
    transition: np.ndarray,
    process_noise: np.ndarray,
    *,
    ridge: float = DEFAULT_RIDGE,
) -> np.ndarray:
    r"""Solve \(\Sigma=A\Sigma A^T+Q\) for a stable VAR(1)."""

    transition_matrix = np.asarray(transition, dtype=float)
    noise = np.asarray(process_noise, dtype=float)
    if transition_matrix.shape != noise.shape:
        raise ValueError("transition and process noise must share shape")
    if spectral_radius(transition_matrix) >= 1.0 - 1e-8:
        raise ValueError("VAR(1) transition must be strictly stable")
    size = transition_matrix.shape[0]
    identity = np.eye(size * size)
    kronecker = np.kron(transition_matrix, transition_matrix)
    try:
        vector = np.linalg.solve(identity - kronecker, noise.reshape(-1, order="F"))
    except np.linalg.LinAlgError:
        vector = np.linalg.pinv(identity - kronecker) @ noise.reshape(-1, order="F")
    sigma = vector.reshape((size, size), order="F")
    return ridge_psd(sigma, ridge)


def var1_cross_covariance(
    transition: np.ndarray,
    sigma: np.ndarray,
    lag: int,
) -> np.ndarray:
    r"""Return \(\mathrm{Cov}(x_t,x_{t+\mathrm{lag}})\) for a stationary VAR(1)."""

    matrix = np.asarray(transition, dtype=float)
    contemporaneous = np.asarray(sigma, dtype=float)
    if lag == 0:
        return contemporaneous.copy()
    if lag > 0:
        return np.linalg.matrix_power(matrix, int(lag)) @ contemporaneous
    return contemporaneous @ np.linalg.matrix_power(matrix, int(-lag)).T


@dataclass(frozen=True)
class StationTime:
    station: int
    time: int


def pair_covariance(
    transition: np.ndarray,
    sigma: np.ndarray,
    left: StationTime,
    right: StationTime,
) -> float:
    cross = var1_cross_covariance(transition, sigma, right.time - left.time)
    return float(cross[left.station, right.station])


def joint_covariance(
    transition: np.ndarray,
    sigma: np.ndarray,
    nodes: Sequence[StationTime],
) -> np.ndarray:
    """Exact joint covariance of selected station-time nodes."""

    nodes = tuple(nodes)
    if not nodes:
        return np.zeros((0, 0))
    times = np.array([node.time for node in nodes], dtype=int)
    stations = np.array([node.station for node in nodes], dtype=int)
    max_lag = int(times.max() - times.min())
    lags = {0: np.asarray(sigma, dtype=float)}
    power = np.eye(transition.shape[0])
    matrix = np.asarray(transition, dtype=float)
    for lag in range(1, max_lag + 1):
        power = matrix @ power
        lags[lag] = power @ sigma
    size = len(nodes)
    joint = np.empty((size, size), dtype=float)
    for i in range(size):
        for j in range(size):
            lag = int(times[j] - times[i])
            if lag >= 0:
                joint[i, j] = lags[lag][stations[i], stations[j]]
            else:
                joint[i, j] = lags[-lag][stations[j], stations[i]]
    return ridge_psd(joint)


def nearest_boundary_distances(gap_length: int) -> np.ndarray:
    """Distance from each hidden day to the nearer of the two boundaries."""

    if gap_length < 1:
        raise ValueError("gap_length must be positive")
    index = np.arange(int(gap_length))
    return np.minimum(index + 1, int(gap_length) - index).astype(float)


def mean_nearest_boundary_distance(gap_length: int) -> float:
    return float(np.mean(nearest_boundary_distances(gap_length)))


def gap_nodes(
    *,
    target: int,
    donors: Sequence[int],
    gap_length: int,
    include_left_boundary: bool = True,
    include_right_boundary: bool = True,
    include_donor_boundaries: bool = False,
    meteorology: Sequence[StationTime] = (),
    hydraulics: Sequence[StationTime] = (),
) -> dict[str, tuple[StationTime, ...]]:
    """Index hidden target days and observation sets for a two-sided gap.

    Hidden times are ``0, ..., d-1``.  The left boundary is time ``-1`` and
    the right boundary is time ``d``.  Online recovery drops the right
    boundary.      Optional ``meteorology`` / ``hydraulics`` are extra observed
    coordinates for the four-set interface {B, D, M, H}.
    """

    if gap_length < 1:
        raise ValueError("gap_length must be positive")
    hidden = tuple(StationTime(target, time) for time in range(gap_length))
    boundaries: list[StationTime] = []
    if include_left_boundary:
        boundaries.append(StationTime(target, -1))
    if include_right_boundary:
        boundaries.append(StationTime(target, gap_length))
    donor_nodes: list[StationTime] = []
    times = list(range(gap_length))
    if include_donor_boundaries:
        if include_left_boundary:
            times.append(-1)
        if include_right_boundary:
            times.append(gap_length)
    for donor in donors:
        if int(donor) == int(target):
            raise ValueError("target cannot also be a donor")
        donor_nodes.extend(StationTime(int(donor), time) for time in times)
    met_nodes = tuple(meteorology)
    hyd_nodes = tuple(hydraulics)
    return {
        "G": hidden,
        "B": tuple(boundaries),
        "D": tuple(donor_nodes),
        "M": met_nodes,
        "H": hyd_nodes,
        "B_union_D": tuple(boundaries) + tuple(donor_nodes),
        "B_union_D_union_M": tuple(boundaries) + tuple(donor_nodes) + met_nodes,
        "B_union_D_union_M_union_H": (
            tuple(boundaries) + tuple(donor_nodes) + met_nodes + hyd_nodes
        ),
    }


def _player_nodes(
    parts: Mapping[str, Sequence[StationTime]],
) -> dict[str, tuple[StationTime, ...]]:
    return {
        name: tuple(parts.get(name, ())) for name in INFORMATION_PLAYER_ORDER
    }


def _observed_nodes_for(
    players: Sequence[str],
    player_nodes: Mapping[str, Sequence[StationTime]],
) -> tuple[StationTime, ...]:
    nodes: list[StationTime] = []
    for name in INFORMATION_PLAYER_ORDER:
        if name in set(players):
            nodes.extend(player_nodes[name])
    return tuple(nodes)


def _information_coalitions(
    parts: Mapping[str, Sequence[StationTime]],
    *,
    include_extended: bool,
) -> list[tuple[str, tuple[StationTime, ...]]]:
    player_nodes = _player_nodes(parts)
    active = ["B", "D"]
    if include_extended:
        if player_nodes["M"]:
            active.append("M")
        if player_nodes["H"]:
            active.append("H")
    seen: set[str] = set()
    coalitions: list[tuple[str, tuple[StationTime, ...]]] = []

    def add(players: Sequence[str]) -> None:
        name = coalition_label(players)
        if name in seen:
            return
        seen.add(name)
        coalitions.append((name, _observed_nodes_for(players, player_nodes)))

    add(())
    add(("B",))
    add(("D",))
    add(("B", "D"))
    if include_extended:
        for size in range(len(active) + 1):
            for combo in combinations(active, size):
                add(combo)
    return coalitions


def _unique_universe(
    parts: Mapping[str, Sequence[StationTime]],
) -> tuple[StationTime, ...]:
    universe = (
        tuple(parts["G"])
        + tuple(parts["B"])
        + tuple(parts["D"])
        + tuple(parts.get("M", ()))
        + tuple(parts.get("H", ()))
    )
    if len(universe) != len(set(universe)):
        raise ValueError("information-set nodes must be unique")
    return universe


def _summaries_from_matrices(
    hidden: np.ndarray,
    matrices: Mapping[str, np.ndarray],
    coalitions: Sequence[tuple[str, Sequence[StationTime]]],
    *,
    gap_length: int,
) -> dict[str, dict[str, float]]:
    observed_counts = {name: float(len(nodes)) for name, nodes in coalitions}
    results: dict[str, dict[str, float]] = {}
    for name, conditional in matrices.items():
        summary = conditional_summaries(hidden, conditional)
        summary["information_set"] = name
        summary["n_hidden"] = float(hidden.shape[0])
        summary["n_observed"] = observed_counts.get(name, float("nan"))
        summary["gap_length"] = float(gap_length)
        results[name] = summary
    return results


def _conditionals_from_joint(
    joint: np.ndarray,
    universe: Sequence[StationTime],
    parts: Mapping[str, Sequence[StationTime]],
    *,
    ridge: float,
    include_extended: bool,
) -> dict[str, np.ndarray]:
    hidden = _select(joint, universe, parts["G"], parts["G"])
    matrices: dict[str, np.ndarray] = {}
    for name, observed_nodes in _information_coalitions(
        parts, include_extended=include_extended
    ):
        if not observed_nodes:
            matrices[name] = hidden.copy()
            continue
        cross = _select(joint, universe, parts["G"], observed_nodes)
        observed = _select(joint, universe, observed_nodes, observed_nodes)
        matrices[name] = schur_complement(hidden, cross, observed, ridge=ridge)
    return matrices


def _select(
    joint: np.ndarray,
    nodes: Sequence[StationTime],
    rows: Sequence[StationTime],
    cols: Sequence[StationTime],
) -> np.ndarray:
    index = {node: position for position, node in enumerate(nodes)}
    row_idx = [index[node] for node in rows]
    col_idx = [index[node] for node in cols]
    return joint[np.ix_(row_idx, col_idx)]


def information_set_conditional_covariances(
    transition: np.ndarray,
    sigma: np.ndarray,
    *,
    target: int,
    donors: Sequence[int],
    gap_length: int,
    include_left_boundary: bool = True,
    include_right_boundary: bool = True,
    include_donor_boundaries: bool = False,
    meteorology: Sequence[StationTime] = (),
    hydraulics: Sequence[StationTime] = (),
    ridge: float = DEFAULT_RIDGE,
) -> dict[str, np.ndarray]:
    r"""Return \(\Sigma_{G\mid S}\) for each computed information coalition."""

    parts = gap_nodes(
        target=target,
        donors=donors,
        gap_length=gap_length,
        include_left_boundary=include_left_boundary,
        include_right_boundary=include_right_boundary,
        include_donor_boundaries=include_donor_boundaries,
        meteorology=meteorology,
        hydraulics=hydraulics,
    )
    universe = _unique_universe(parts)
    joint = joint_covariance(transition, sigma, universe)
    return _conditionals_from_joint(
        joint,
        universe,
        parts,
        ridge=ridge,
        include_extended=bool(meteorology) or bool(hydraulics),
    )


def information_set_conditionals(
    transition: np.ndarray,
    sigma: np.ndarray,
    *,
    target: int,
    donors: Sequence[int],
    gap_length: int,
    include_left_boundary: bool = True,
    include_right_boundary: bool = True,
    include_donor_boundaries: bool = False,
    meteorology: Sequence[StationTime] = (),
    hydraulics: Sequence[StationTime] = (),
    ridge: float = DEFAULT_RIDGE,
) -> dict[str, dict[str, float]]:
    """Conditional risk of a gap under none, B, D, and B∪D information.

    When ``meteorology`` or ``hydraulics`` nodes are supplied, every
    coalition of the active {B, D, M, H} parts is also returned.
    """

    parts = gap_nodes(
        target=target,
        donors=donors,
        gap_length=gap_length,
        include_left_boundary=include_left_boundary,
        include_right_boundary=include_right_boundary,
        include_donor_boundaries=include_donor_boundaries,
        meteorology=meteorology,
        hydraulics=hydraulics,
    )
    include_extended = bool(meteorology) or bool(hydraulics)
    coalitions = _information_coalitions(parts, include_extended=include_extended)
    matrices = information_set_conditional_covariances(
        transition,
        sigma,
        target=target,
        donors=donors,
        gap_length=gap_length,
        include_left_boundary=include_left_boundary,
        include_right_boundary=include_right_boundary,
        include_donor_boundaries=include_donor_boundaries,
        meteorology=meteorology,
        hydraulics=hydraulics,
        ridge=ridge,
    )
    return _summaries_from_matrices(
        matrices["none"],
        matrices,
        coalitions,
        gap_length=gap_length,
    )


def var1_gap_conditional_risk(
    transition: np.ndarray,
    sigma: np.ndarray,
    *,
    target: int,
    donors: Sequence[int],
    gap_length: int,
    include_left_boundary: bool = True,
    include_right_boundary: bool = True,
    ridge: float = DEFAULT_RIDGE,
) -> dict[str, float]:
    """Scalable B-union-D conditional risk for a fitted Gaussian VAR(1).

    This computes the same marginal conditional variances used by the primary
    recoverability and Gaussian-MAE summaries, but avoids materializing the
    dense station-by-gap covariance built by :func:`information_set_conditionals`.
    Exact (zero-noise) observations are the target boundary value(s) and every
    donor value inside the gap.  Covariances are propagated with a Kalman
    filter and Rauch--Tung--Striebel covariance smoother.

    The returned log-determinant fields are intentionally omitted: marginal
    variances suffice for ``recoverability_r`` and
    ``predicted_conditional_risk``, whereas reconstructing the full smoothed
    gap covariance would defeat this routine's bounded-memory contract.
    """

    matrix = _as_square(np.asarray(transition, dtype=float), name="transition")
    stationary = _as_square(np.asarray(sigma, dtype=float), name="sigma")
    if matrix.shape != stationary.shape:
        raise ValueError("transition and sigma must share shape")
    if gap_length < 1:
        raise ValueError("gap_length must be positive")
    n_stations = int(matrix.shape[0])
    target = int(target)
    donor_index = tuple(int(value) for value in donors)
    if target < 0 or target >= n_stations:
        raise ValueError("target index is outside the VAR state")
    if target in donor_index or len(set(donor_index)) != len(donor_index):
        raise ValueError("donors must be unique and exclude the target")
    if any(value < 0 or value >= n_stations for value in donor_index):
        raise ValueError("donor index is outside the VAR state")
    if spectral_radius(matrix) >= 1.0 - 1e-8:
        raise ValueError("VAR(1) transition must be strictly stable")

    stationary = ridge_psd(stationary, ridge)
    process_noise = ridge_psd(
        stationary - matrix @ stationary @ matrix.T,
        ridge,
    )

    def observe(covariance: np.ndarray, observed: Sequence[int]) -> np.ndarray:
        if not observed:
            return covariance
        index = np.asarray(tuple(observed), dtype=int)
        cross = covariance[:, index]
        observed_covariance = ridge_psd(covariance[np.ix_(index, index)], ridge)
        try:
            solved = np.linalg.solve(observed_covariance, cross.T)
        except np.linalg.LinAlgError:
            solved = np.linalg.pinv(observed_covariance) @ cross.T
        posterior = covariance - cross @ solved
        # Exact observations have zero posterior variance.  Do not use
        # ridge_psd here because doing so would add artificial observation
        # noise at every time step.
        posterior = 0.5 * (posterior + posterior.T)
        eigval, eigvec = np.linalg.eigh(posterior)
        return (eigvec * np.maximum(eigval, 0.0)) @ eigvec.T

    # Time positions are -1, 0, ..., gap_length.  Store each filtered
    # covariance and the one-step prediction used by the backward smoother.
    filtered: list[np.ndarray] = []
    predicted: list[np.ndarray | None] = [None]
    covariance = stationary.copy()
    if include_left_boundary:
        covariance = observe(covariance, (target,))
    filtered.append(covariance)
    for time in range(int(gap_length) + 1):
        prior = ridge_psd(matrix @ covariance @ matrix.T + process_noise, ridge)
        predicted.append(prior)
        observed = donor_index if time < int(gap_length) else ()
        if time == int(gap_length) and include_right_boundary:
            observed = (target,)
        covariance = observe(prior, observed)
        filtered.append(covariance)

    smoothed = filtered[-1]
    hidden_variances = np.empty(int(gap_length), dtype=float)
    # filtered index 0 is time -1; hidden times 0..d-1 are indices 1..d.
    for position in range(int(gap_length), 0, -1):
        next_prior = predicted[position + 1]
        assert next_prior is not None
        try:
            gain = np.linalg.solve(next_prior, matrix @ filtered[position]).T
        except np.linalg.LinAlgError:
            gain = filtered[position] @ matrix.T @ np.linalg.pinv(next_prior)
        smoothed = filtered[position] + gain @ (
            smoothed - next_prior
        ) @ gain.T
        smoothed = 0.5 * (smoothed + smoothed.T)
        hidden_variances[position - 1] = max(float(smoothed[target, target]), 0.0)

    unconditional_variance = max(float(stationary[target, target]), 0.0)
    conditional_variance = float(np.mean(hidden_variances))
    unconditional_mae = float(np.sqrt(unconditional_variance) * GAUSSIAN_MAE_FACTOR)
    conditional_mae = float(
        np.mean(np.sqrt(hidden_variances)) * GAUSSIAN_MAE_FACTOR
    )
    return {
        "information_set": "B_union_D",
        "n_hidden": float(gap_length),
        "n_observed": float(
            len(donor_index) * int(gap_length)
            + int(include_left_boundary)
            + int(include_right_boundary)
        ),
        "gap_length": float(gap_length),
        "normalized_conditional_variance": (
            float("nan")
            if unconditional_variance <= 0
            else conditional_variance / unconditional_variance
        ),
        "recoverability_r": (
            float("nan")
            if unconditional_variance <= 0
            else 1.0 - np.sqrt(conditional_variance / unconditional_variance)
        ),
        "expected_mae_unconditional": unconditional_mae,
        "expected_mae_conditional": conditional_mae,
        "predicted_skill": (
            float("nan")
            if unconditional_mae <= 0
            else 1.0 - conditional_mae / unconditional_mae
        ),
        "predicted_conditional_risk": conditional_mae,
    }


def empirical_lag_covariances(
    series: np.ndarray,
    max_lag: int,
) -> list[np.ndarray]:
    """Sample cross-covariance matrices at lags ``0, ..., max_lag``."""

    values = np.asarray(series, dtype=float)
    if values.ndim != 2:
        raise ValueError("series must have shape (time, stations)")
    if max_lag < 0:
        raise ValueError("max_lag must be non-negative")
    centered = values - np.nanmean(values, axis=0, keepdims=True)
    n_stations = int(values.shape[1])
    covariances: list[np.ndarray] = []
    for lag in range(max_lag + 1):
        if lag == 0:
            left = right = centered
        else:
            left = centered[lag:]
            right = centered[:-lag]
        valid = np.isfinite(left).all(axis=1) & np.isfinite(right).all(axis=1)
        if int(valid.sum()) < 2:
            covariances.append(np.full((n_stations, n_stations), np.nan))
            continue
        stacked = np.cov(right[valid], left[valid], rowvar=False)
        covariances.append(stacked[:n_stations, n_stations:])
    return covariances


def empirical_pair_covariance(
    lag_covariances: Sequence[np.ndarray],
    left: StationTime,
    right: StationTime,
) -> float:
    lag = right.time - left.time
    if abs(lag) >= len(lag_covariances):
        return float("nan")
    matrix = np.asarray(lag_covariances[abs(lag)], dtype=float)
    if lag >= 0:
        return float(matrix[left.station, right.station])
    return float(matrix[right.station, left.station])


def empirical_information_set_conditionals(
    series: np.ndarray,
    *,
    target: int,
    donors: Sequence[int],
    gap_length: int,
    include_left_boundary: bool = True,
    include_right_boundary: bool = True,
    meteorology: Sequence[StationTime] = (),
    hydraulics: Sequence[StationTime] = (),
    ridge: float = DEFAULT_RIDGE,
) -> dict[str, dict[str, float]]:
    """Estimate the operator from a fitting-period multivariate series."""

    max_lag = gap_length + 1
    lags = empirical_lag_covariances(series, max_lag)
    parts = gap_nodes(
        target=target,
        donors=donors,
        gap_length=gap_length,
        include_left_boundary=include_left_boundary,
        include_right_boundary=include_right_boundary,
        meteorology=meteorology,
        hydraulics=hydraulics,
    )
    universe = _unique_universe(parts)
    joint = np.empty((len(universe), len(universe)), dtype=float)
    for i, left in enumerate(universe):
        for j, right in enumerate(universe):
            joint[i, j] = empirical_pair_covariance(lags, left, right)
    if not np.isfinite(joint).all():
        missing = float(np.mean(~np.isfinite(joint)))
        empty = {
            "information_set": "withheld",
            "n_hidden": float(len(parts["G"])),
            "n_observed": float("nan"),
            "gap_length": float(gap_length),
            "recoverability_r": float("nan"),
            "predicted_skill": float("nan"),
            "operator_explained_variance": float("nan"),
            "expected_mae_conditional": float("nan"),
            "withheld": True,
            "withheld_reason": "empirical_lag_covariance_incomplete",
            "missing_covariance_fraction": missing,
        }
        return {name: dict(empty, information_set=name) for name in INFORMATION_SETS}
    include_extended = bool(meteorology) or bool(hydraulics)
    coalitions = _information_coalitions(parts, include_extended=include_extended)
    matrices = _conditionals_from_joint(
        joint,
        universe,
        parts,
        ridge=ridge,
        include_extended=include_extended,
    )
    return _summaries_from_matrices(
        matrices["none"],
        matrices,
        coalitions,
        gap_length=gap_length,
    )


def conditionals_table(results: Mapping[str, Mapping[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame([dict(row) for row in results.values()])


__all__ = [
    "DEFAULT_LOEWNER_ATOL",
    "DEFAULT_RIDGE",
    "GAUSSIAN_MAE_FACTOR",
    "INFORMATION_PLAYER_ORDER",
    "INFORMATION_SETS",
    "StationTime",
    "coalition_label",
    "conditional_summaries",
    "conditionals_table",
    "empirical_information_set_conditionals",
    "empirical_lag_covariances",
    "expected_gaussian_mae",
    "gap_nodes",
    "information_set_conditional_covariances",
    "information_set_conditionals",
    "joint_covariance",
    "loewner_leq",
    "mean_nearest_boundary_distance",
    "nearest_boundary_distances",
    "pair_covariance",
    "predicted_skill",
    "recoverability_r",
    "residual_quantile_width",
    "ridge_psd",
    "safe_logdet",
    "schur_complement",
    "spectral_radius",
    "stationary_covariance",
    "var1_cross_covariance",
    "var1_gap_conditional_risk",
]
