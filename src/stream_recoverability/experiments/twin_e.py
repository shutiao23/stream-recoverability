"""Twin E hard negative for the v9.1 known-covariance E5 gate.

The inspected f01--f06 cases are development diagnostics only. Formal
hold-out scoring is a separate entry point which refuses to run until its
external freeze file is tracked, committed, and clean.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from scipy.stats import spearmanr

from stream_recoverability.analysis.conditional_observability import (
    empirical_information_set_conditionals,
    expected_gaussian_mae,
    schur_complement,
)
from stream_recoverability.experiments.synthetic_river import (
    TWIN_ADVECT,
    TWIN_DAM_MEMORY,
    TWIN_DISPERS,
    TWIN_FACTOR_NOISE,
    TWIN_LOCAL_NOISE,
    TWIN_ORDINARY_LOADING,
    TWIN_ORDINARY_MEMORY,
)

GAP_LENGTHS = (30, 90, 180)
OPERATOR_SPEARMAN_MIN = 0.90
UNIVARIATE_SPEARMAN_MAX = 0.70
CALIBRATION_SLOPE_RANGE = (0.90, 1.10)
GAP_ATTENUATION_EXPONENT = 0.05
OBSERVATION_NOISE = TWIN_LOCAL_NOISE + TWIN_FACTOR_NOISE
TEMPORAL_SAMPLE_DONOR_R2_MATCH_ATOL = 0.02
TEMPORAL_POPULATION_DONOR_R2_MATCH_ATOL = 1e-12
UNIVARIATE_PREDICTORS = (
    "gap_length_only",
    "acf_only",
    "donor_r2_only",
    "additive_d4",
)


@dataclass(frozen=True)
class TwinEFamily:
    """Fixed settings for one paired Twin E family."""

    family: str
    split: str
    boundary_loading: float
    donor_loading: float
    marginal_phi: float


@dataclass(frozen=True)
class TemporalTwinEFamily:
    """Commit-locked real time-series graph family."""

    family: str
    propagation_lag: int
    seed: int
    n_train: int
    burn_in: int
    n_nodes: int
    phi: float
    factor_process_noise: float
    local_process_noise: float
    advect: float
    dispersion: float


# Already inspected: never eligible for hold-out promotion.
TWIN_E_FAMILIES = (
    TwinEFamily("twin_e_f01", "design_debug", 0.75, 0.70, TWIN_DAM_MEMORY),
    TwinEFamily("twin_e_f02", "design_debug", 0.75, 1.00, TWIN_ORDINARY_MEMORY),
    TwinEFamily("twin_e_f03", "design_debug", 1.00, 0.70, TWIN_DAM_MEMORY),
    TwinEFamily("twin_e_f04", "design_debug", 1.00, 1.00, TWIN_ORDINARY_MEMORY),
    TwinEFamily("twin_e_f05", "design_debug", 1.25, 0.70, TWIN_DAM_MEMORY),
    TwinEFamily("twin_e_f06", "design_debug", 1.25, 1.00, TWIN_ORDINARY_MEMORY),
)
HOLDOUT_FAMILIES: tuple[str, ...] = ()


def _observation_loading(
    family: TwinEFamily,
    gap_length: int,
    *,
    donor_relation: str,
) -> np.ndarray:
    """Map two standardized gap modes into boundary/donor observations."""

    if donor_relation not in {"redundant", "complementary"}:
        raise ValueError("donor_relation must be redundant or complementary")
    if int(gap_length) not in GAP_LENGTHS:
        raise ValueError(f"gap_length must be one of {GAP_LENGTHS}")
    boundary = float(family.boundary_loading) * (
        GAP_LENGTHS[0] / int(gap_length)
    ) ** GAP_ATTENUATION_EXPONENT
    donor = float(family.donor_loading)
    return np.array(
        [
            [boundary, 0.0],
            [donor, 0.0] if donor_relation == "redundant" else [0.0, donor],
        ],
        dtype=float,
    )


def _joint_covariance(
    family: TwinEFamily,
    gap_length: int,
    *,
    donor_relation: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    loading = _observation_loading(
        family, gap_length, donor_relation=donor_relation
    )
    sigma_gg = np.eye(2, dtype=float)
    sigma_go = loading.T
    sigma_oo = loading @ loading.T + OBSERVATION_NOISE * np.eye(2)
    return sigma_gg, sigma_go, sigma_oo


def _true_recoverability_from_generator(loading: np.ndarray) -> tuple[float, float]:
    """Analytic Bayes-optimal MAE from the generator posterior precision."""

    # G ~ N(0, I), O|G ~ N(HG, noise I). This direct generative derivation is
    # independent of the Schur-complement operator implementation below.
    precision = np.eye(loading.shape[1]) + (
        loading.T @ loading / OBSERVATION_NOISE
    )
    posterior = np.linalg.inv(precision)
    mae_factor = float(np.sqrt(2.0 / np.pi))
    conditional_mae = mae_factor * float(
        np.mean(np.sqrt(np.clip(np.diag(posterior), 0.0, None)))
    )
    return conditional_mae, 1.0 - conditional_mae / mae_factor


def _operator_recoverability_from_known_sigma(
    sigma_gg: np.ndarray,
    sigma_go: np.ndarray,
    sigma_oo: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Estimate through the public conditional-observability operator API."""

    sigma_cond = schur_complement(sigma_gg, sigma_go, sigma_oo)
    predicted = 1.0 - (
        expected_gaussian_mae(sigma_cond) / expected_gaussian_mae(sigma_gg)
    )
    return sigma_cond, predicted


def _score_row(
    family: TwinEFamily,
    gap_length: int,
    *,
    donor_relation: str,
) -> dict[str, Any]:
    loading = _observation_loading(
        family, gap_length, donor_relation=donor_relation
    )
    sigma_gg, sigma_go, sigma_oo = _joint_covariance(
        family, gap_length, donor_relation=donor_relation
    )
    conditional_mae, true_recoverability = _true_recoverability_from_generator(
        loading
    )
    sigma_cond, operator_recoverability = _operator_recoverability_from_known_sigma(
        sigma_gg, sigma_go, sigma_oo
    )
    donor_r2 = family.donor_loading**2 / (
        family.donor_loading**2 + OBSERVATION_NOISE
    )
    acf30 = abs(float(family.marginal_phi)) ** 30
    rho_d4_squared = abs(float(family.marginal_phi)) ** (gap_length / 2.0)
    additive_d4 = donor_r2 + (1.0 - donor_r2) * rho_d4_squared
    is_redundant = donor_relation == "redundant"
    return {
        "cell": "E",
        "family": family.family,
        "split": family.split,
        "gap_length": int(gap_length),
        "node_type": "dam_like_interior" if is_redundant else "ordinary_endpoint",
        "donor_relation": donor_relation,
        "n_donors": 1,
        "donor_direction": "downstream" if is_redundant else "upstream",
        "travel_time_role": (
            "boundary_redundant" if is_redundant else "boundary_complementary"
        ),
        "marginal_phi": float(family.marginal_phi),
        "marginal_acf30": acf30,
        "donor_r2": donor_r2,
        "true_conditional_mae": conditional_mae,
        "true_recoverability": true_recoverability,
        "operator_recoverability": operator_recoverability,
        "gap_length_only": float(gap_length),
        "acf_only": acf30,
        "donor_r2_only": donor_r2,
        "additive_d4": additive_d4,
        "sigma_cond_00": float(sigma_cond[0, 0]),
        "sigma_cond_01": float(sigma_cond[0, 1]),
        "sigma_cond_10": float(sigma_cond[1, 0]),
        "sigma_cond_11": float(sigma_cond[1, 1]),
    }


def generate_twin_e_scores(
    families: tuple[TwinEFamily, ...] = TWIN_E_FAMILIES,
) -> pd.DataFrame:
    rows = []
    for family in families:
        for gap_length in GAP_LENGTHS:
            for relation in ("redundant", "complementary"):
                rows.append(
                    _score_row(family, gap_length, donor_relation=relation)
                )
    return pd.DataFrame(rows)


def _spearman(left: pd.Series, right: pd.Series) -> float:
    result = spearmanr(
        pd.to_numeric(left, errors="coerce"),
        pd.to_numeric(right, errors="coerce"),
        nan_policy="omit",
    )
    return float(result.statistic)


def _score_correlations(
    scores: pd.DataFrame,
    *,
    formal_holdout: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    truth = scores["true_recoverability"]
    operator_spearman = _spearman(scores["operator_recoverability"], truth)
    calibration_slope, calibration_intercept = np.polyfit(
        scores["operator_recoverability"].to_numpy(dtype=float),
        truth.to_numpy(dtype=float),
        deg=1,
    )
    rows = []
    for predictor in UNIVARIATE_PREDICTORS:
        correlation = _spearman(scores[predictor], truth)
        rows.append(
            {
                "cell": "E",
                "split": "holdout" if formal_holdout else "design_debug",
                "predictor": predictor,
                "spearman": correlation,
                "absolute_spearman": abs(correlation),
                "n_rows": len(scores),
            }
        )
    univariate = pd.DataFrame(rows)
    best = univariate.loc[univariate["absolute_spearman"].idxmax()]
    operator_ok = bool(operator_spearman >= OPERATOR_SPEARMAN_MIN)
    univariate_ok = bool(
        float(best["absolute_spearman"]) <= UNIVARIATE_SPEARMAN_MAX
    )
    calibration_ok = bool(
        CALIBRATION_SLOPE_RANGE[0]
        <= float(calibration_slope)
        <= CALIBRATION_SLOPE_RANGE[1]
    )
    numeric_gate_met = bool(operator_ok and univariate_ok and calibration_ok)
    passed = bool(formal_holdout and numeric_gate_met)
    if passed:
        status = "twin_e_gate_pass"
    elif not formal_holdout:
        status = "not_tested_holdout_not_prelocked"
    elif not operator_ok:
        status = "twin_e_operator_spearman_miss"
    elif not univariate_ok:
        status = "twin_e_univariate_ceiling_miss"
    elif not calibration_ok:
        status = "twin_e_operator_calibration_miss"
    else:
        status = "twin_e_numeric_gate_miss"
    gate = {
        "cell": "E",
        "evaluated_split": "holdout" if formal_holdout else "design_debug",
        "holdout_families": (
            sorted(scores["family"].unique()) if formal_holdout else []
        ),
        "holdout_family_locked_before_scoring": formal_holdout,
        "n_rows": len(scores),
        "operator_spearman": operator_spearman,
        "operator_spearman_min": OPERATOR_SPEARMAN_MIN,
        "operator_meets_floor": operator_ok,
        "best_univariate": str(best["predictor"]),
        "best_univariate_absolute_spearman": float(best["absolute_spearman"]),
        "univariate_spearman_max": UNIVARIATE_SPEARMAN_MAX,
        "univariate_meets_ceiling": univariate_ok,
        "operator_calibration_slope": float(calibration_slope),
        "operator_calibration_intercept": float(calibration_intercept),
        "operator_calibration_slope_range": list(CALIBRATION_SLOPE_RANGE),
        "operator_calibration_meets_band": calibration_ok,
        "numeric_thresholds_met": numeric_gate_met,
        "passed": passed,
        "status": status,
        "forbidden_metric": "classification_auc",
        "generator_retuned_to_save_gate": False,
    }
    return univariate, gate


def evaluate_twin_e(scores: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Evaluate inspected f01--f06 as unlicensed design diagnostics only."""

    if not scores["split"].eq("design_debug").all():
        raise ValueError("evaluate_twin_e accepts design_debug rows only")
    return _score_correlations(scores, formal_holdout=False)


def _temporal_graph(
    family: TemporalTwinEFamily,
    relation: str,
) -> dict[str, Any]:
    """Return explicit nodes, directed edges, and integer factor-time offsets."""

    lag = int(family.propagation_lag)
    if family.n_nodes != 5:
        raise ValueError("the v1 temporal Twin E graph requires five nodes")
    if relation == "redundant":
        # The target is graph-interior. Reservoir-release alignment makes its
        # upstream/downstream neighbors carry the same delayed factor mode.
        nodes = ("target", "upstream", "downstream", "up_tail", "down_tail")
        edges = ((3, 1), (1, 0), (0, 2), (2, 4))
        offsets = (0, -lag, -lag, -2 * lag, -2 * lag)
        donors = (1, 2)
        target_kind = "dam_like_interior"
    elif relation == "complementary":
        # The graph endpoint has two one-direction donors at distinct integer
        # propagation times, so their gap information is complementary.
        nodes = ("target", "down_1", "down_2", "down_3", "down_4")
        edges = ((0, 1), (1, 2), (2, 3), (3, 4))
        offsets = (0, -lag, -2 * lag, -3 * lag, -4 * lag)
        donors = (1, 2)
        target_kind = "ordinary_endpoint"
    else:
        raise ValueError("relation must be redundant or complementary")
    return {
        "nodes": nodes,
        "edges": edges,
        "offsets": offsets,
        "donors": donors,
        "target": 0,
        "node_type": target_kind,
        "relation": relation,
    }


def _latent_transition_and_noise(
    family: TemporalTwinEFamily,
) -> tuple[np.ndarray, np.ndarray]:
    """Explicit AR(1) transition/Q used by the latent propagation factor."""

    transition = np.array([[float(family.phi)]], dtype=float)
    process_noise = np.array([[float(family.factor_process_noise)]], dtype=float)
    return transition, process_noise


def _population_donor_r2(
    family: TemporalTwinEFamily,
    offsets: tuple[int, int],
    donor_loading: float,
) -> float:
    """Population contemporaneous multiple R2 for the two locked donors."""

    latent_variance = family.factor_process_noise / (1.0 - family.phi**2)
    donor_covariance = np.array(
        [
            [
                donor_loading**2
                * latent_variance
                * abs(family.phi) ** abs(left - right)
                + (family.local_process_noise if i == j else 0.0)
                for j, right in enumerate(offsets)
            ]
            for i, left in enumerate(offsets)
        ],
        dtype=float,
    )
    cross = np.array(
        [
            TWIN_ORDINARY_LOADING
            * donor_loading
            * latent_variance
            * abs(family.phi) ** abs(offset)
            for offset in offsets
        ],
        dtype=float,
    )
    target_variance = (
        TWIN_ORDINARY_LOADING**2 * latent_variance
        + family.local_process_noise
    )
    return float(cross @ np.linalg.solve(donor_covariance, cross) / target_variance)


def _matched_station_loadings(
    family: TemporalTwinEFamily,
    graph: dict[str, Any],
) -> tuple[float, ...]:
    """Analytically match donor R2 without inspecting recoverability scores."""

    base = float(np.hypot(family.advect, family.dispersion))
    offsets = tuple(graph["offsets"][index] for index in graph["donors"])
    if graph["relation"] == "redundant":
        donor_loading = base
    else:
        redundant_offsets = (
            -family.propagation_lag,
            -family.propagation_lag,
        )
        target_r2 = _population_donor_r2(family, redundant_offsets, base)
        lower, upper = 0.0, 4.0 * base
        if _population_donor_r2(family, offsets, upper) < target_r2:
            raise RuntimeError("locked analytic donor-R2 match has no solution")
        for _ in range(80):
            midpoint = 0.5 * (lower + upper)
            if _population_donor_r2(family, offsets, midpoint) < target_r2:
                lower = midpoint
            else:
                upper = midpoint
        donor_loading = 0.5 * (lower + upper)
    return (TWIN_ORDINARY_LOADING,) + (donor_loading,) * (family.n_nodes - 1)


def simulate_temporal_twin_e(
    family: TemporalTwinEFamily,
    relation: str,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Simulate a five-node lagged river graph from the locked state process."""

    graph = _temporal_graph(family, relation)
    transition, process_noise = _latent_transition_and_noise(family)
    phi = float(transition[0, 0])
    q = float(process_noise[0, 0])
    # The same latent and target-noise window is used for both relations.
    # This prevents a relation-specific crop from fabricating an ACF mismatch.
    max_offset = 4 * int(family.propagation_lag)
    total = family.n_train + family.burn_in + 2 * max_offset
    rng = np.random.default_rng(int(family.seed))
    latent = np.empty(total, dtype=float)
    latent[0] = rng.normal(0.0, np.sqrt(q / (1.0 - phi**2)))
    for index in range(1, total):
        latent[index] = phi * latent[index - 1] + rng.normal(0.0, np.sqrt(q))
    start = family.burn_in + max_offset
    loadings = _matched_station_loadings(family, graph)
    columns = []
    for station, (offset, loading) in enumerate(zip(graph["offsets"], loadings)):
        signal = loading * latent[
            start + offset : start + offset + family.n_train
        ]
        noise_rng = np.random.default_rng(int(family.seed) + 10_000 + station)
        noise = noise_rng.normal(
            0.0, np.sqrt(family.local_process_noise), family.n_train
        )
        columns.append(signal + noise)
    graph.update(
        {
            "transition": transition,
            "process_noise": process_noise,
            "station_loadings": loadings,
        }
    )
    return np.column_stack(columns), graph


def _temporal_covariance(
    family: TemporalTwinEFamily,
    graph: dict[str, Any],
    left: tuple[int, int],
    right: tuple[int, int],
) -> float:
    """Known covariance kernel implied by the locked latent state process."""

    station_left, time_left = left
    station_right, time_right = right
    latent_variance = family.factor_process_noise / (1.0 - family.phi**2)
    latent_lag = abs(
        (time_left + graph["offsets"][station_left])
        - (time_right + graph["offsets"][station_right])
    )
    covariance = (
        graph["station_loadings"][station_left]
        * graph["station_loadings"][station_right]
        * latent_variance
        * abs(family.phi) ** latent_lag
    )
    if station_left == station_right and time_left == time_right:
        covariance += family.local_process_noise
    return float(covariance)


def _analytic_temporal_truth(
    family: TemporalTwinEFamily,
    graph: dict[str, Any],
    gap_length: int,
) -> tuple[float, float]:
    """Bayes-optimal gap MAE from the generator's analytic covariance kernel."""

    hidden = [(graph["target"], time) for time in range(gap_length)]
    observed = [(graph["target"], -1), (graph["target"], gap_length)]
    observed.extend(
        (donor, time)
        for donor in graph["donors"]
        for time in range(gap_length)
    )

    def block(left: list[tuple[int, int]], right: list[tuple[int, int]]) -> np.ndarray:
        return np.array(
            [
                [_temporal_covariance(family, graph, a, b) for b in right]
                for a in left
            ],
            dtype=float,
        )

    sigma_gg = block(hidden, hidden)
    sigma_go = block(hidden, observed)
    sigma_oo = block(observed, observed)
    solved = np.linalg.solve(
        sigma_oo + 1e-8 * np.eye(sigma_oo.shape[0]), sigma_go.T
    )
    conditional = sigma_gg - sigma_go @ solved
    mae_0 = expected_gaussian_mae(sigma_gg)
    mae_cond = expected_gaussian_mae(conditional)
    return mae_cond, 1.0 - mae_cond / mae_0


def _sample_acf(series: np.ndarray, lag: int = 30) -> float:
    return float(np.corrcoef(series[:-lag], series[lag:])[0, 1])


def _sample_donor_r2(series: np.ndarray, donors: tuple[int, ...]) -> float:
    target = series[:, 0]
    design = np.column_stack([np.ones(len(series)), series[:, donors]])
    fitted = design @ np.linalg.lstsq(design, target, rcond=None)[0]
    total = float(np.sum((target - target.mean()) ** 2))
    return float(1.0 - np.sum((target - fitted) ** 2) / total)


def validate_temporal_twin_e_pair(
    family: TemporalTwinEFamily,
) -> dict[str, float | bool]:
    """Assert marginal matching before any operator/gate calculation."""

    redundant, graph_r = simulate_temporal_twin_e(family, "redundant")
    complementary, graph_c = simulate_temporal_twin_e(family, "complementary")
    target_exact = bool(np.array_equal(redundant[:, 0], complementary[:, 0]))
    if not target_exact:
        raise RuntimeError("Twin E paired target series are not exactly matched")
    acf_r = _sample_acf(redundant[:, 0])
    acf_c = _sample_acf(complementary[:, 0])
    if acf_r != acf_c:
        raise RuntimeError("Twin E paired target ACF is not exactly matched")
    sample_r2_r = _sample_donor_r2(redundant, graph_r["donors"])
    sample_r2_c = _sample_donor_r2(complementary, graph_c["donors"])
    sample_delta = abs(sample_r2_r - sample_r2_c)
    if sample_delta > TEMPORAL_SAMPLE_DONOR_R2_MATCH_ATOL:
        raise RuntimeError("Twin E paired sample donor R2 exceeds locked tolerance")
    offsets_r = tuple(graph_r["offsets"][i] for i in graph_r["donors"])
    offsets_c = tuple(graph_c["offsets"][i] for i in graph_c["donors"])
    population_r2_r = _population_donor_r2(
        family, offsets_r, graph_r["station_loadings"][1]
    )
    population_r2_c = _population_donor_r2(
        family, offsets_c, graph_c["station_loadings"][1]
    )
    population_delta = abs(population_r2_r - population_r2_c)
    if population_delta > TEMPORAL_POPULATION_DONOR_R2_MATCH_ATOL:
        raise RuntimeError("Twin E paired population donor R2 is not matched")
    truth_deltas = []
    for gap_length in GAP_LENGTHS:
        truth_r = _analytic_temporal_truth(family, graph_r, gap_length)[1]
        truth_c = _analytic_temporal_truth(family, graph_c, gap_length)[1]
        truth_deltas.append(abs(truth_r - truth_c))
    if not all(delta > 1e-12 for delta in truth_deltas):
        raise RuntimeError("Twin E conditional truth does not differ within every pair")
    return {
        "target_series_exact": target_exact,
        "acf30_redundant": acf_r,
        "acf30_complementary": acf_c,
        "sample_donor_r2_redundant": sample_r2_r,
        "sample_donor_r2_complementary": sample_r2_c,
        "sample_donor_r2_delta": sample_delta,
        "population_donor_r2_redundant": population_r2_r,
        "population_donor_r2_complementary": population_r2_c,
        "population_donor_r2_delta": population_delta,
        "minimum_true_recoverability_delta": min(truth_deltas),
    }


def generate_temporal_twin_e_scores(
    families: tuple[TemporalTwinEFamily, ...],
) -> pd.DataFrame:
    """Score real temporal graphs using analytic truth and empirical hat-Sigma."""

    rows = []
    for family in families:
        # This preflight contains no operator or gate score. It must succeed
        # before empirical hat-Sigma is computed for the family.
        match = validate_temporal_twin_e_pair(family)
        for relation in ("redundant", "complementary"):
            series, graph = simulate_temporal_twin_e(family, relation)
            acf30 = _sample_acf(series[:, 0])
            donor_r2 = _sample_donor_r2(series, graph["donors"])
            for gap_length in GAP_LENGTHS:
                true_mae, truth = _analytic_temporal_truth(
                    family, graph, gap_length
                )
                empirical = empirical_information_set_conditionals(
                    series,
                    target=graph["target"],
                    donors=graph["donors"],
                    gap_length=gap_length,
                )["B_union_D"]
                additive = donor_r2 + (1.0 - donor_r2) * abs(acf30) ** (
                    gap_length / 60.0
                )
                rows.append(
                    {
                        "cell": "E",
                        "family": family.family,
                        "split": "holdout",
                        "relation": relation,
                        "node_type": graph["node_type"],
                        "nodes": json.dumps(graph["nodes"]),
                        "edges": json.dumps(graph["edges"]),
                        "donor_indices": json.dumps(graph["donors"]),
                        "n_donors": len(graph["donors"]),
                        "propagation_lag": family.propagation_lag,
                        "gap_length": gap_length,
                        "seed": family.seed,
                        "n_train": family.n_train,
                        "transition_phi": family.phi,
                        "factor_process_noise": family.factor_process_noise,
                        "local_process_noise": family.local_process_noise,
                        "advect": family.advect,
                        "dispersion": family.dispersion,
                        "paired_sample_donor_r2_delta": match[
                            "sample_donor_r2_delta"
                        ],
                        "paired_population_donor_r2_delta": match[
                            "population_donor_r2_delta"
                        ],
                        "paired_target_series_exact": match["target_series_exact"],
                        "true_conditional_mae": true_mae,
                        "true_recoverability": truth,
                        "operator_recoverability": float(empirical["predicted_skill"]),
                        "gap_length_only": float(gap_length),
                        "acf_only": acf30,
                        "donor_r2_only": donor_r2,
                        "additive_d4": additive,
                    }
                )
    return pd.DataFrame(rows)


def _git_lock_commit(lock_path: Path) -> str:
    """Return the commit locking a clean tracked file, or refuse scoring."""

    path = Path(lock_path).resolve()
    root = Path(__file__).resolve().parents[3]
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("Twin E hold-out lock must be inside the repository") from exc
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(relative)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", str(relative)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    commit = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", str(relative)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode or dirty.stdout.strip() or not commit.stdout.strip():
        raise RuntimeError(
            "Twin E hold-out scoring refused: lock must be committed and clean first"
        )
    return commit.stdout.strip()


def load_locked_holdout_families(
    lock_path: Path,
    *,
    require_committed: bool = True,
) -> tuple[tuple[TemporalTwinEFamily, ...], str | None]:
    """Expand an algorithmic full-factorial freeze without scoring it."""

    path = Path(lock_path)
    lock_commit = _git_lock_commit(path) if require_committed else None
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload.get("status") != "locked_unscored":
        raise ValueError("Twin E freeze must have status locked_unscored")
    factorial = payload["full_factorial"]
    lags = tuple(int(value) for value in factorial["propagation_lag"])
    seeds = tuple(int(value) for value in factorial["seed"])
    locked = payload["locked_generator"]
    if float(locked["phi"]) != TWIN_ORDINARY_MEMORY:
        raise ValueError("hold-out phi must reuse TWIN_ORDINARY_MEMORY")
    if float(locked["advect"]) != TWIN_ADVECT:
        raise ValueError("hold-out advect must reuse TWIN_ADVECT")
    if float(locked["dispersion"]) != TWIN_DISPERS:
        raise ValueError("hold-out dispersion must reuse TWIN_DISPERS")
    families = []
    index = 1
    for propagation_lag in lags:
        for seed in seeds:
            families.append(
                TemporalTwinEFamily(
                    family=f"twin_e_holdout_{index:03d}",
                    propagation_lag=propagation_lag,
                    seed=seed,
                    n_train=int(locked["n_train"]),
                    burn_in=int(locked["burn_in"]),
                    n_nodes=int(locked["n_nodes"]),
                    phi=float(locked["phi"]),
                    factor_process_noise=float(locked["factor_process_noise"]),
                    local_process_noise=float(locked["local_process_noise"]),
                    advect=float(locked["advect"]),
                    dispersion=float(locked["dispersion"]),
                )
            )
            index += 1
    if len(families) != int(payload["expected_n_families"]):
        raise ValueError("expanded hold-out count does not match freeze")
    return tuple(families), lock_commit


def run_locked_twin_e_holdout(lock_path: Path) -> dict[str, Any]:
    """Score hold-out only after its lock is verifiably committed and clean."""

    families, lock_commit = load_locked_holdout_families(
        lock_path, require_committed=True
    )
    scores = generate_temporal_twin_e_scores(families)
    univariates, gate = _score_correlations(scores, formal_holdout=True)
    gate["lock_commit"] = lock_commit
    return {"scores": scores, "univariates": univariates, "gate": gate}


def run_twin_e() -> dict[str, Any]:
    """Run the inspected design diagnostic; this can never pass the gate."""

    scores = generate_twin_e_scores()
    univariates, gate = evaluate_twin_e(scores)
    return {"scores": scores, "univariates": univariates, "gate": gate}


def write_twin_e_artifacts(result: dict[str, Any], output: Path) -> dict[str, Path]:
    """Write exploratory Twin E artifacts without replacing A--D outputs."""

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    scores_path = output / "twin_e_node_gap_scores.csv"
    univariate_path = output / "twin_e_univariate_spearman.csv"
    manifest_path = output / "twin_e_manifest.json"
    result["scores"].to_csv(scores_path, index=False)
    result["univariates"].to_csv(univariate_path, index=False)
    manifest = {
        "experiment": "E5_twin_e_design_debug",
        "protocol_amendment": "v9.1",
        "cell": "E",
        "formal_evidence": False,
        "sealed_outcomes_opened": False,
        "purpose": "exploratory_design_debug_not_gate_evidence",
        "estimand": "true_recoverability_from_known_sigma",
        "unit": "node_times_gap_length",
        "gap_lengths": list(GAP_LENGTHS),
        "four_preregistered_univariates": list(UNIVARIATE_PREDICTORS),
        "inspected_design_debug_families": [
            asdict(family) for family in TWIN_E_FAMILIES
        ],
        "marginal_matching": {
            "within_pair_equal_acf30": True,
            "within_pair_equal_donor_r2": True,
            "differ_only_in_joint_conditional_information": True,
        },
        "phi_source": "existing Twin A-D TWIN_DAM_MEMORY/TWIN_ORDINARY_MEMORY",
        "observation_noise_source": (
            "existing TWIN_LOCAL_NOISE plus TWIN_FACTOR_NOISE"
        ),
        "truth_path": "analytic_generator_posterior_precision",
        "operator_path": "conditional_observability_public_schur_api",
        "gate": result["gate"],
        "holdout_status": "locked_unscored_not_run_by_this_script",
        "holdout_freeze": "configs/twin_e_holdout_freeze_v1.yaml",
        "superseded_auc_gate_used": False,
        "historical_a_to_d_artifacts_overwritten": False,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "scores": scores_path,
        "univariates": univariate_path,
        "manifest": manifest_path,
    }


def write_locked_twin_e_holdout_artifacts(
    result: dict[str, Any],
    output: Path,
    *,
    lock_path: Path,
) -> dict[str, Path]:
    """Write first-score hold-out artifacts after the guarded runner succeeds."""

    gate = result["gate"]
    if gate.get("evaluated_split") != "holdout" or not gate.get("lock_commit"):
        raise ValueError("formal hold-out artifacts require a verified lock commit")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    scores_path = output / "twin_e_holdout_node_gap_scores.csv"
    univariate_path = output / "twin_e_holdout_univariate_spearman.csv"
    manifest_path = output / "twin_e_holdout_manifest.json"
    result["scores"].to_csv(scores_path, index=False)
    result["univariates"].to_csv(univariate_path, index=False)
    manifest = {
        "experiment": "E5_twin_e_locked_holdout",
        "protocol_amendment": "v9.1",
        "cell": "E",
        "formal_evidence": False,
        "purpose": "synthetic_falsification_holdout",
        "estimand": "analytic_truth_vs_finite_training_hat_sigma_operator",
        "truth_path": "analytic_locked_state_space_covariance",
        "operator_path": "empirical_hat_sigma_public_conditional_observability_api",
        "lock_path": str(Path(lock_path)),
        "lock_commit": gate["lock_commit"],
        "gate": gate,
        "superseded_auc_gate_used": False,
        "historical_a_to_d_artifacts_overwritten": False,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "scores": scores_path,
        "univariates": univariate_path,
        "manifest": manifest_path,
    }


NEGATIVE_RESULT_SCHEMA = "twin_e_holdout_negative_result_v1"
NEGATIVE_RESULT_STATUSES = frozenset(
    {
        "twin_e_operator_calibration_miss",
        "twin_e_operator_spearman_miss",
        "twin_e_univariate_ceiling_breach",
    }
)


def write_twin_e_holdout_negative_result(
    *,
    holdout_manifest_path: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Record a publishable negative from a failed, unscored hold-out gate.

    Retuning φ, noise, or the generator is never licensed by this writer.
    """

    holdout_manifest_path = Path(holdout_manifest_path)
    payload = json.loads(holdout_manifest_path.read_text(encoding="utf-8"))
    gate = dict(payload.get("gate", {}))
    if bool(gate.get("passed")):
        raise ValueError("negative result writer requires a failed hold-out gate")
    status = str(gate.get("status", ""))
    if status not in NEGATIVE_RESULT_STATUSES:
        raise ValueError(f"unexpected hold-out status for negative result: {status!r}")
    if bool(gate.get("generator_retuned_to_save_gate")):
        raise ValueError("generator retuning invalidates a publishable negative result")
    record = {
        "manifest_schema": NEGATIVE_RESULT_SCHEMA,
        "experiment": payload.get("experiment", "E5_twin_e_locked_holdout"),
        "protocol_amendment": payload.get("protocol_amendment", "v9.1"),
        "cell": payload.get("cell", "E"),
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "confirmatory_eligible": False,
        "publishable_negative_result": True,
        "negative_result_locked": True,
        "generator_retuning_allowed": False,
        "phi_or_noise_retuning_allowed": False,
        "purpose": "synthetic_falsification_negative_result_not_evidence",
        "estimand": payload.get(
            "estimand", "analytic_truth_vs_finite_training_hat_sigma_operator"
        ),
        "holdout_manifest": str(holdout_manifest_path),
        "lock_path": payload.get("lock_path"),
        "lock_commit": payload.get("lock_commit") or gate.get("lock_commit"),
        "gate_status": status,
        "gate": gate,
        "interpretation": (
            "Locked Twin E hold-out failed without generator retuning. "
            "This is a design falsification record, not confirmatory T2 or T5."
        ),
        "passed": False,
    }
    destination = (
        Path(output_path)
        if output_path is not None
        else holdout_manifest_path.with_name("twin_e_holdout_negative_result.json")
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    record["output_path"] = str(destination)
    return record


__all__ = [
    "CALIBRATION_SLOPE_RANGE",
    "GAP_LENGTHS",
    "HOLDOUT_FAMILIES",
    "OPERATOR_SPEARMAN_MIN",
    "TWIN_E_FAMILIES",
    "UNIVARIATE_PREDICTORS",
    "UNIVARIATE_SPEARMAN_MAX",
    "TemporalTwinEFamily",
    "evaluate_twin_e",
    "generate_temporal_twin_e_scores",
    "generate_twin_e_scores",
    "load_locked_holdout_families",
    "run_locked_twin_e_holdout",
    "run_twin_e",
    "simulate_temporal_twin_e",
    "validate_temporal_twin_e_pair",
    "write_locked_twin_e_holdout_artifacts",
    "write_twin_e_artifacts",
    "write_twin_e_holdout_negative_result",
]
