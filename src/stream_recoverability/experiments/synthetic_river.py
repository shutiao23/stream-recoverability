"""Known-dynamics synthetic river graphs for identifiability experiments."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from stream_recoverability.analysis.conditional_observability import (
    spectral_radius,
    stationary_covariance,
)


@dataclass(frozen=True)
class SyntheticRiver:
    """Linear-Gaussian mainstem with optional release forcing."""

    name: str
    transition: np.ndarray
    process_noise: np.ndarray
    sigma: np.ndarray
    station_names: tuple[str, ...]
    target: int
    donors: tuple[int, ...]
    regime: str
    notes: str
    edges: tuple[tuple[int, int], ...] = ()
    dam_like_index: int | None = None
    ordinary_endpoint: int | None = None
    ordinary_interior: int | None = None

    @property
    def n_stations(self) -> int:
        return int(self.transition.shape[0])


def _stabilize(transition: np.ndarray, limit: float = 0.96) -> np.ndarray:
    matrix = np.asarray(transition, dtype=float)
    radius = spectral_radius(matrix)
    if radius >= limit:
        matrix = matrix * (limit / (radius + 1e-12))
    return matrix


def _build(
    name: str,
    transition: np.ndarray,
    process_noise: np.ndarray,
    *,
    station_names: Sequence[str],
    target: int,
    donors: Sequence[int],
    regime: str,
    notes: str,
    edges: Sequence[tuple[int, int]] = (),
    dam_like_index: int | None = None,
    ordinary_endpoint: int | None = None,
    ordinary_interior: int | None = None,
) -> SyntheticRiver:
    transition_matrix = _stabilize(np.asarray(transition, dtype=float))
    noise = np.asarray(process_noise, dtype=float)
    noise = 0.5 * (noise + noise.T)
    return SyntheticRiver(
        name=name,
        transition=transition_matrix,
        process_noise=noise,
        sigma=stationary_covariance(transition_matrix, noise),
        station_names=tuple(str(item) for item in station_names),
        target=int(target),
        donors=tuple(int(item) for item in donors),
        regime=regime,
        notes=notes,
        edges=tuple((int(left), int(right)) for left, right in edges),
        dam_like_index=None if dam_like_index is None else int(dam_like_index),
        ordinary_endpoint=None if ordinary_endpoint is None else int(ordinary_endpoint),
        ordinary_interior=None if ordinary_interior is None else int(ordinary_interior),
    )


def memory_dominant_river() -> SyntheticRiver:
    """High local memory, essentially independent donors."""

    transition = np.diag([0.95, 0.15, 0.15])
    noise = np.diag([1.00, 1.00, 1.00])
    return _build(
        "memory_dominant",
        transition,
        noise,
        station_names=("target", "up", "down"),
        target=0,
        donors=(1, 2),
        regime="memory",
        notes="True incremental value should favour boundaries.",
    )


def donor_dominant_river() -> SyntheticRiver:
    """Weak local memory, strong shared contemporaneous factor."""

    transition = 0.12 * np.eye(3)
    noise = np.array(
        [
            [1.00, 0.92, 0.90],
            [0.92, 1.00, 0.88],
            [0.90, 0.88, 1.00],
        ]
    )
    return _build(
        "donor_dominant",
        transition,
        noise,
        station_names=("target", "d1", "d2"),
        target=0,
        donors=(1, 2),
        regime="donor",
        notes="True incremental value should favour donors.",
    )


def high_donor_and_high_memory_river() -> SyntheticRiver:
    """Strong donors and strong residual memory. Heuristic must force donor."""

    # Shared AR coefficient keeps stationary correlations equal to Q correlations.
    transition = 0.90 * np.eye(4)
    noise = np.array(
        [
            [1.00, 0.88, 0.86, 0.84],
            [0.88, 1.00, 0.80, 0.78],
            [0.86, 0.80, 1.00, 0.76],
            [0.84, 0.78, 0.76, 1.00],
        ]
    )
    return _build(
        "high_donor_and_high_memory",
        transition,
        noise,
        station_names=("target", "d1", "d2", "d3"),
        target=0,
        donors=(1, 2, 3),
        regime="mixed",
        notes="In-sample donor R2 exceeds 0.5 while residual AR remains high.",
    )


def endpoint_upstream_origin() -> SyntheticRiver:
    """Target is the upstream origin; all donors are downstream."""

    # Order: origin, mid, mouth. Weak origin-to-downstream contemporaneous copy.
    transition = np.array(
        [
            [0.88, 0.00, 0.00],
            [0.25, 0.45, 0.00],
            [0.05, 0.25, 0.40],
        ]
    )
    noise = np.diag([1.0, 1.0, 1.0])
    return _build(
        "endpoint_upstream_origin",
        transition,
        noise,
        station_names=("origin", "mid", "mouth"),
        target=0,
        donors=(1, 2),
        regime="endpoint",
        notes="All donors lie downstream of the target.",
    )


def endpoint_downstream_terminus() -> SyntheticRiver:
    """Target is the downstream terminus; all donors are upstream."""

    transition = np.array(
        [
            [0.45, 0.00, 0.00],
            [0.25, 0.45, 0.00],
            [0.05, 0.20, 0.88],
        ]
    )
    noise = np.diag([1.0, 1.0, 1.0])
    return _build(
        "endpoint_downstream_terminus",
        transition,
        noise,
        station_names=("head", "mid", "terminus"),
        target=2,
        donors=(0, 1),
        regime="endpoint",
        notes="All donors lie upstream of the target.",
    )


def donor_count_redundant_river(n_donors: int = 6) -> SyntheticRiver:
    """One shared factor copied into many noisy donors."""

    size = n_donors + 1
    transition = 0.25 * np.eye(size)
    noise = 0.20 * np.eye(size) + 0.80 * np.ones((size, size))
    return _build(
        "donor_count_redundant",
        transition,
        noise,
        station_names=("target", *[f"d{i}" for i in range(n_donors)]),
        target=0,
        donors=tuple(range(1, size)),
        regime="redundant_donors",
        notes="Additional donors are copies of one factor.",
    )


def advection_chain(n_stations: int = 6, memory: float = 0.55, advect: float = 0.30) -> SyntheticRiver:
    """Mainstem chain used by sensor-policy experiments."""

    if n_stations < 3:
        raise ValueError("advection_chain needs at least three stations")
    transition = memory * np.eye(n_stations)
    for index in range(1, n_stations):
        transition[index, index - 1] = advect
    noise = 0.85 * np.eye(n_stations) + 0.15 * np.ones((n_stations, n_stations))
    mid = n_stations // 2
    donors = tuple(index for index in range(n_stations) if index != mid)
    return _build(
        "advection_chain",
        transition,
        noise,
        station_names=tuple(f"s{index}" for index in range(n_stations)),
        target=mid,
        donors=donors,
        regime="chain",
        notes="Linear advection plus local memory on a mainstem.",
    )


def nonstationary_release_river() -> tuple[SyntheticRiver, SyntheticRiver]:
    """Pre- and post-release states that share topology but not memory."""

    pre = memory_dominant_river()
    post_transition = 0.15 * np.eye(pre.n_stations)
    post_noise = np.array(
        [
            [1.00, 0.90, 0.88],
            [0.90, 1.00, 0.80],
            [0.88, 0.80, 1.00],
        ]
    )
    post = _build(
        "release_shifted",
        post_transition,
        post_noise,
        station_names=pre.station_names,
        target=pre.target,
        donors=pre.donors,
        regime="shifted",
        notes="Same graph after a memory collapse and donor-correlation rise.",
    )
    return pre, post


def simulate_var1(
    river: SyntheticRiver,
    n_time: int,
    *,
    seed: int = 0,
    burn_in: int = 200,
) -> np.ndarray:
    """Draw a zero-mean VAR(1) series with shape ``(n_time, n_stations)``."""

    rng = np.random.default_rng(seed)
    n_stations = river.n_stations
    try:
        factor = np.linalg.cholesky(river.process_noise)
    except np.linalg.LinAlgError:
        eigval, eigvec = np.linalg.eigh(river.process_noise)
        factor = eigvec * np.sqrt(np.maximum(eigval, 1e-12))
    state = rng.normal(0.0, 1.0, n_stations)
    rows = []
    for step in range(n_time + burn_in):
        state = river.transition @ state + factor @ rng.normal(0.0, 1.0, n_stations)
        if step >= burn_in:
            rows.append(state.copy())
    return np.asarray(rows)


TWIN_ORDINARY_MEMORY = 0.52
TWIN_DAM_MEMORY = 0.93
TWIN_ADVECT = 0.22
TWIN_DISPERS = 0.18
TWIN_DAM_COUPLING = 0.20
TWIN_DAM_LOADING = 0.12
TWIN_ORDINARY_LOADING = 1.00
TWIN_LOCAL_NOISE = 0.25
TWIN_FACTOR_NOISE = 0.75


def chain_edges(n_stations: int) -> tuple[tuple[int, int], ...]:
    if n_stations < 5:
        raise ValueError("twin chains need at least five stations")
    return tuple((index, index + 1) for index in range(n_stations - 1))


def confluence_edges(n_stations: int) -> tuple[tuple[tuple[int, int], ...], int]:
    """Mainstem plus one tributary joining an interior confluence.

    Nodes ``0 .. n-2`` are the mainstem; node ``n-1`` joins at the
    interior mainstem index.  Directed edges point downstream.
    """

    if n_stations < 5:
        raise ValueError("twin confluence graphs need at least five stations")
    mainstem = n_stations - 1
    join = mainstem // 2
    if join <= 0 or join >= mainstem - 1:
        raise ValueError("confluence join must be an interior mainstem node")
    edges = [(index, index + 1) for index in range(mainstem - 1)]
    edges.append((n_stations - 1, join))
    return tuple(edges), int(join)


def _factor_process_noise(
    loadings: Sequence[float],
    *,
    local: float = TWIN_LOCAL_NOISE,
    factor: float = TWIN_FACTOR_NOISE,
) -> np.ndarray:
    weights = np.asarray(loadings, dtype=float)
    noise = float(local) * np.eye(weights.size) + float(factor) * np.outer(weights, weights)
    return 0.5 * (noise + noise.T)


def _advection_dispersion_transition(
    n_stations: int,
    directed_edges: Sequence[tuple[int, int]],
    memories: Sequence[float],
    *,
    isolated: int | None,
    advect: float = TWIN_ADVECT,
    dispers: float = TWIN_DISPERS,
    isolation_scale: float = TWIN_DAM_COUPLING,
) -> np.ndarray:
    transition = np.diag(np.asarray(memories, dtype=float))
    for upstream, downstream in directed_edges:
        scale = (
            float(isolation_scale)
            if isolated is not None and isolated in (upstream, downstream)
            else 1.0
        )
        transition[downstream, upstream] += float(advect) * scale
        transition[upstream, downstream] += float(dispers) * scale
    return transition


def _twin_river(
    *,
    name: str,
    n_stations: int,
    directed_edges: Sequence[tuple[int, int]],
    dam_like: int | None,
    ordinary_endpoint: int | None,
    topology: str,
    ordinary_interior: int | None = None,
) -> SyntheticRiver:
    memories = [TWIN_ORDINARY_MEMORY] * n_stations
    loadings = [TWIN_ORDINARY_LOADING] * n_stations
    if dam_like is not None:
        memories[int(dam_like)] = TWIN_DAM_MEMORY
        loadings[int(dam_like)] = TWIN_DAM_LOADING
    transition = _advection_dispersion_transition(
        n_stations,
        directed_edges,
        memories,
        isolated=dam_like,
    )
    target = int(dam_like) if dam_like is not None else int(ordinary_endpoint or 0)
    donors = tuple(index for index in range(n_stations) if index != target)
    family = "A" if dam_like is not None else "B"
    notes = (
        f"Twin {family} {topology}: "
        + (
            f"interior dam-like node {dam_like} with high local AR and amplitude isolation."
            if dam_like is not None
            else f"ordinary-memory endpoint {ordinary_endpoint} with one-sided donors."
        )
    )
    return _build(
        name,
        transition,
        _factor_process_noise(loadings),
        station_names=tuple(f"s{index}" for index in range(n_stations)),
        target=target,
        donors=donors,
        regime=f"twin_{family.lower()}",
        notes=notes,
        edges=directed_edges,
        dam_like_index=dam_like,
        ordinary_endpoint=ordinary_endpoint,
        ordinary_interior=ordinary_interior,
    )


def twin_a_interior_dam_chain(n_stations: int = 6) -> SyntheticRiver:
    """Interior reservoir-like node on a mainstem chain. Not an endpoint."""

    edges = chain_edges(n_stations)
    dam = n_stations // 2
    if dam <= 0 or dam >= n_stations - 1:
        raise ValueError("chain dam-like node must be interior")
    return _twin_river(
        name=f"twin_a_interior_dam_chain_n{n_stations}",
        n_stations=n_stations,
        directed_edges=edges,
        dam_like=dam,
        ordinary_endpoint=0,
        topology="chain",
    )


def twin_b_ordinary_endpoint_chain(n_stations: int = 6) -> SyntheticRiver:
    """Same chain family; ordinary-memory headwater, no extra isolation."""

    return _twin_river(
        name=f"twin_b_ordinary_endpoint_chain_n{n_stations}",
        n_stations=n_stations,
        directed_edges=chain_edges(n_stations),
        dam_like=None,
        ordinary_endpoint=0,
        topology="chain",
    )


def twin_a_interior_dam_confluence(n_stations: int = 6) -> SyntheticRiver:
    """Reservoir-like confluence node with donors upstream, downstream, and on a tributary."""

    edges, join = confluence_edges(n_stations)
    return _twin_river(
        name=f"twin_a_interior_dam_confluence_n{n_stations}",
        n_stations=n_stations,
        directed_edges=edges,
        dam_like=join,
        ordinary_endpoint=0,
        topology="confluence",
    )


def twin_b_ordinary_endpoint_confluence(n_stations: int = 6) -> SyntheticRiver:
    """Same confluence family; ordinary headwater endpoint, no dam-like node."""

    edges, _join = confluence_edges(n_stations)
    return _twin_river(
        name=f"twin_b_ordinary_endpoint_confluence_n{n_stations}",
        n_stations=n_stations,
        directed_edges=edges,
        dam_like=None,
        ordinary_endpoint=0,
        topology="confluence",
    )


def twin_c_endpoint_dam_chain(n_stations: int = 6) -> SyntheticRiver:
    """Missing 2x2 cell: dam-like *and* endpoint (the historical confound)."""

    return _twin_river(
        name=f"twin_c_endpoint_dam_chain_n{n_stations}",
        n_stations=n_stations,
        directed_edges=chain_edges(n_stations),
        dam_like=0,
        ordinary_endpoint=0,
        topology="chain",
    )


def twin_d_ordinary_interior_chain(n_stations: int = 6) -> SyntheticRiver:
    """Missing 2x2 cell: ordinary-memory interior node, no dam-like isolation."""

    interior = n_stations // 2
    return _twin_river(
        name=f"twin_d_ordinary_interior_chain_n{n_stations}",
        n_stations=n_stations,
        directed_edges=chain_edges(n_stations),
        dam_like=None,
        ordinary_endpoint=0,
        topology="chain",
        ordinary_interior=interior,
    )


def twin_catalog() -> dict[str, SyntheticRiver]:
    """Named Fig. 2 twins. Kept out of ``catalog()`` so E0 stays unchanged."""

    rivers = [
        twin_a_interior_dam_chain(),
        twin_b_ordinary_endpoint_chain(),
        twin_a_interior_dam_confluence(),
        twin_b_ordinary_endpoint_confluence(),
        twin_c_endpoint_dam_chain(),
        twin_d_ordinary_interior_chain(),
    ]
    return {river.name: river for river in rivers}


def catalog() -> dict[str, SyntheticRiver]:
    rivers = [
        memory_dominant_river(),
        donor_dominant_river(),
        high_donor_and_high_memory_river(),
        endpoint_upstream_origin(),
        endpoint_downstream_terminus(),
        donor_count_redundant_river(),
        advection_chain(),
    ]
    return {river.name: river for river in rivers}


__all__ = [
    "SyntheticRiver",
    "advection_chain",
    "catalog",
    "chain_edges",
    "confluence_edges",
    "donor_count_redundant_river",
    "donor_dominant_river",
    "endpoint_downstream_terminus",
    "endpoint_upstream_origin",
    "high_donor_and_high_memory_river",
    "memory_dominant_river",
    "nonstationary_release_river",
    "simulate_var1",
    "twin_a_interior_dam_chain",
    "twin_a_interior_dam_confluence",
    "twin_b_ordinary_endpoint_chain",
    "twin_b_ordinary_endpoint_confluence",
    "twin_c_endpoint_dam_chain",
    "twin_catalog",
    "twin_d_ordinary_interior_chain",
]
