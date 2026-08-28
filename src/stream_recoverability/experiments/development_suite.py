"""Open-development evaluation for the recoverability operator.

The suite works at the station-by-gap estimand used by the public-river and
natural-outage experiments.  It compares the operator with donor R² and gap
length, evaluates out-of-network advancement, and exposes the stress tests
needed before another confirmatory study is considered.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from stream_recoverability.experiments.sensor_policy import (
    POLICIES,
    evaluate_placement,
    policy_oracle,
    policy_proposed,
)
from stream_recoverability.experiments.synthetic_river import SyntheticRiver

DEFAULT_PREDICTORS = {
    "operator": "predicted_conditional_risk",
    "donor_r2": "donor_r2",
    "gap_length": "gap_length",
}
SPEARMAN_GAIN_MIN = 0.10
R2_GAIN_MIN = 0.05


def station_gap_table(
    frame: pd.DataFrame,
    *,
    predictors: Mapping[str, str] = DEFAULT_PREDICTORS,
    outcome: str = "observed_recovery_loss",
) -> pd.DataFrame:
    """Collapse repeat placements to one row per network, station, and gap."""

    keys = ["network_id", "station_id", "gap_length"]
    columns = [
        column
        for column in dict.fromkeys([outcome, *predictors.values()])
        if column not in keys
    ]
    numeric = frame[keys + columns].copy()
    numeric[columns] = numeric[columns].apply(pd.to_numeric, errors="coerce")
    return numeric.groupby(keys, as_index=False, sort=False)[columns].mean()


def _fit_linear(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    design = np.column_stack([np.ones(len(x)), x])
    return np.linalg.lstsq(design, y, rcond=None)[0]


def _apply_linear(x: np.ndarray, coefficients: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(x)), x]) @ coefficients


def _network_equal_linear(
    frame: pd.DataFrame,
    columns: Sequence[str],
    outcome: str,
) -> np.ndarray:
    design = np.column_stack(
        [np.ones(len(frame)), frame[list(columns)].to_numpy(dtype=float)]
    )
    counts = frame.groupby("network_id")["network_id"].transform("size")
    root_weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    return np.linalg.lstsq(
        design * root_weight[:, None],
        frame[outcome].to_numpy(dtype=float) * root_weight,
        rcond=None,
    )[0]


def _linear_prediction(
    frame: pd.DataFrame,
    columns: Sequence[str],
    coefficients: np.ndarray,
) -> np.ndarray:
    design = np.column_stack(
        [np.ones(len(frame)), frame[list(columns)].to_numpy(dtype=float)]
    )
    return design @ coefficients


def _network_equal_rmse(frame: pd.DataFrame, outcome: str, prediction: str) -> float:
    squared = np.square(
        frame[outcome].to_numpy(dtype=float)
        - frame[prediction].to_numpy(dtype=float)
    )
    losses = pd.Series(squared, index=frame.index).groupby(frame["network_id"]).mean()
    return float(np.sqrt(losses.mean()))


def _inner_lono_simple_model(
    train: pd.DataFrame,
    *,
    simple_cols: Sequence[str],
    outcome: str,
    candidate_models: Sequence[Sequence[str]] | None = None,
) -> tuple[tuple[str, ...], pd.DataFrame]:
    candidates = (
        [tuple(model) for model in candidate_models]
        if candidate_models is not None
        else [
            subset
            for size in range(1, len(simple_cols) + 1)
            for subset in combinations(simple_cols, size)
        ]
    )
    best_key: tuple[float, int, tuple[str, ...]] | None = None
    best_subset: tuple[str, ...] = candidates[0]
    best_predictions = pd.DataFrame()
    for subset in candidates:
        inner_rows = []
        for held_out in pd.unique(train["network_id"]):
            inner_train = train.loc[~train["network_id"].eq(held_out)]
            inner_test = train.loc[train["network_id"].eq(held_out)].copy()
            coefficients = _network_equal_linear(inner_train, subset, outcome)
            inner_test["inner_prediction"] = _linear_prediction(
                inner_test, subset, coefficients
            )
            inner_rows.append(inner_test)
        inner_predictions = pd.concat(inner_rows, ignore_index=True)
        key = (
            _network_equal_rmse(inner_predictions, outcome, "inner_prediction"),
            len(subset),
            subset,
        )
        if best_key is None or key < best_key:
            best_key = key
            best_subset = subset
            best_predictions = inner_predictions
    return best_subset, best_predictions


def _metrics(y: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    rho = float(spearmanr(prediction, y).statistic)
    residual = float(np.square(y - prediction).sum())
    total = float(np.square(y - y.mean()).sum())
    return {
        "spearman": rho,
        "r2": float(1.0 - residual / total),
        "rmse": float(np.sqrt(np.mean(np.square(y - prediction)))),
    }


def station_gap_metrics(
    frame: pd.DataFrame,
    *,
    predictors: Mapping[str, str] = DEFAULT_PREDICTORS,
    outcome: str = "observed_recovery_loss",
) -> pd.DataFrame:
    """Calibrated univariate performance with station×gap as the sample unit."""

    units = station_gap_table(frame, predictors=predictors, outcome=outcome)
    rows: list[dict[str, float | str]] = []
    for name, column in predictors.items():
        usable = units[[outcome, column]].dropna()
        x = usable[column].to_numpy(dtype=float)
        y = usable[outcome].to_numpy(dtype=float)
        prediction = _apply_linear(x, _fit_linear(x, y))
        rows.append(
            {
                "predictor": name,
                "column": column,
                "unit": "station_gap",
                "n_station_gaps": float(len(usable)),
                **_metrics(y, prediction),
            }
        )
    return pd.DataFrame(rows)


def leave_one_network_out_predictions(
    frame: pd.DataFrame,
    *,
    predictors: Mapping[str, str] = DEFAULT_PREDICTORS,
    outcome: str = "observed_recovery_loss",
) -> pd.DataFrame:
    """Fit each univariate calibration on all but one river network."""

    units = station_gap_table(frame, predictors=predictors, outcome=outcome)
    rows: list[pd.DataFrame] = []
    for held_out in pd.unique(units["network_id"]):
        train = units.loc[~units["network_id"].eq(held_out)]
        test = units.loc[units["network_id"].eq(held_out)]
        for name, column in predictors.items():
            train_usable = train.dropna(subset=[column, outcome])
            test_usable = test.dropna(subset=[column, outcome]).copy()
            coefficients = _network_equal_linear(
                train_usable, (column,), outcome
            )
            test_usable["predictor"] = name
            test_usable["predicted_loss"] = _linear_prediction(
                test_usable, (column,), coefficients
            )
            rows.append(
                test_usable[
                    [
                        "network_id",
                        "station_id",
                        "gap_length",
                        outcome,
                        "predictor",
                        "predicted_loss",
                    ]
                ]
            )
    return pd.concat(rows, ignore_index=True)


def lono_metrics(
    predictions: pd.DataFrame,
    *,
    outcome: str = "observed_recovery_loss",
) -> pd.DataFrame:
    """Pool LONO predictions only after every station×gap was held out once."""

    rows = []
    for predictor, group in predictions.groupby("predictor", sort=False):
        y = group[outcome].to_numpy(dtype=float)
        predicted = group["predicted_loss"].to_numpy(dtype=float)
        rows.append(
            {
                "predictor": predictor,
                "unit": "station_gap",
                "n_station_gaps": float(len(group)),
                "n_networks": float(group["network_id"].nunique()),
                **_metrics(y, predicted),
            }
        )
    return pd.DataFrame(rows)


def leave_one_network_out_nested_predictions(
    frame: pd.DataFrame,
    *,
    operator_col: str = "predicted_conditional_risk",
    simple_cols: Sequence[str] = (
        "gap_length",
        "acf_only",
        "donor_r2_only",
        "additive_d_over_4_heuristic",
    ),
    outcome: str = "observed_recovery_loss",
    coverage: float = 0.90,
    candidate_models: Sequence[Sequence[str]] | None = None,
) -> pd.DataFrame:
    """Select the strongest simple subset inside each outer network fold."""

    predictor_map = {
        **{column: column for column in simple_cols},
        "operator": operator_col,
    }
    units = station_gap_table(frame, predictors=predictor_map, outcome=outcome)
    rows = []
    for held_out in pd.unique(units["network_id"]):
        train = units.loc[~units["network_id"].eq(held_out)]
        test = units.loc[units["network_id"].eq(held_out)].copy()
        selected_simple, inner_predictions = _inner_lono_simple_model(
            train,
            simple_cols=simple_cols,
            outcome=outcome,
            candidate_models=candidate_models,
        )
        inner_predictions["inner_absolute_residual"] = np.abs(
            inner_predictions[outcome] - inner_predictions["inner_prediction"]
        )
        network_scores = inner_predictions.groupby("network_id")[
            "inner_absolute_residual"
        ].max()
        interval_radius = float(
            np.quantile(network_scores, float(coverage), method="higher")
        )
        extended = (*selected_simple, operator_col)
        baseline_coef = _network_equal_linear(train, selected_simple, outcome)
        extended_coef = _network_equal_linear(train, extended, outcome)
        test["simple_prediction"] = _linear_prediction(
            test, selected_simple, baseline_coef
        )
        test["simple_prediction_lower"] = test["simple_prediction"] - interval_radius
        test["simple_prediction_upper"] = test["simple_prediction"] + interval_radius
        test["simple_interval_radius"] = interval_radius
        test["simple_interval_calibration_unit"] = (
            "network_max_absolute_inner_lono_residual"
        )
        test["n_simple_interval_calibration_networks"] = float(len(network_scores))
        test["simple_plus_operator_prediction"] = _linear_prediction(
            test, extended, extended_coef
        )
        test["selected_simple_model"] = "|".join(selected_simple)
        test["held_out_network"] = str(held_out)
        rows.append(test)
    return pd.concat(rows, ignore_index=True)


def nested_lono_metrics(
    predictions: pd.DataFrame,
    *,
    outcome: str = "observed_recovery_loss",
) -> dict[str, float]:
    """Return the operator's LONO increment after the simple combination."""

    observed = predictions[outcome].to_numpy(dtype=float)
    simple = _metrics(
        observed, predictions["simple_prediction"].to_numpy(dtype=float)
    )
    extended = _metrics(
        observed,
        predictions["simple_plus_operator_prediction"].to_numpy(dtype=float),
    )
    return {
        "simple_spearman": simple["spearman"],
        "simple_r2": simple["r2"],
        "simple_rmse": simple["rmse"],
        "simple_plus_operator_spearman": extended["spearman"],
        "simple_plus_operator_r2": extended["r2"],
        "simple_plus_operator_rmse": extended["rmse"],
        "operator_incremental_r2": extended["r2"] - simple["r2"],
    }


def lono_advancement_gate(
    metrics: pd.DataFrame,
    *,
    operator: str = "operator",
    baseline: str = "donor_r2",
    spearman_gain_min: float = SPEARMAN_GAIN_MIN,
    r2_gain_min: float = R2_GAIN_MIN,
    incremental_r2: float | None = None,
) -> dict[str, float | str | bool]:
    """Apply the development promotion rule against donor R²."""

    indexed = metrics.set_index("predictor")
    delta_spearman = round(
        float(indexed.loc[operator, "spearman"] - indexed.loc[baseline, "spearman"]),
        12,
    )
    delta_r2 = round(
        float(
            indexed.loc[operator, "r2"] - indexed.loc[baseline, "r2"]
            if incremental_r2 is None
            else incremental_r2
        ),
        12,
    )
    return {
        "unit": "station_gap",
        "comparison": (
            f"{operator}_minus_{baseline}"
            if incremental_r2 is None
            else f"{operator}_rank_minus_{baseline}_and_increment_after_simple"
        ),
        "delta_spearman": delta_spearman,
        "delta_r2": delta_r2,
        "r2_comparison": (
            f"{operator}_minus_{baseline}"
            if incremental_r2 is None
            else "simple_plus_operator_minus_simple"
        ),
        "spearman_gain_min": float(spearman_gain_min),
        "r2_gain_min": float(r2_gain_min),
        "passed": bool(
            delta_spearman >= float(spearman_gain_min)
            and delta_r2 >= float(r2_gain_min)
        ),
    }


def gaussian_mutual_information(
    covariance: np.ndarray,
    selected: Sequence[int],
) -> float:
    """Mutual information between selected and unselected Gaussian stations."""

    matrix = np.asarray(covariance, dtype=float)
    chosen = tuple(int(item) for item in selected)
    remaining = tuple(index for index in range(matrix.shape[0]) if index not in chosen)
    if not chosen or not remaining:
        return 0.0
    logdet_selected = float(np.linalg.slogdet(matrix[np.ix_(chosen, chosen)])[1])
    logdet_remaining = float(np.linalg.slogdet(matrix[np.ix_(remaining, remaining)])[1])
    logdet_all = float(np.linalg.slogdet(matrix)[1])
    return 0.5 * (logdet_selected + logdet_remaining - logdet_all)


def greedy_mutual_information_indices(
    covariance: np.ndarray,
    k: int,
) -> tuple[int, ...]:
    """Greedily maximize Gaussian MI between monitored and unmonitored sites."""

    matrix = np.asarray(covariance, dtype=float)
    selected: list[int] = []
    remaining = list(range(matrix.shape[0]))
    while len(selected) < int(k):
        scores = [
            (gaussian_mutual_information(matrix, [*selected, candidate]), -candidate)
            for candidate in remaining
        ]
        winner = -max(scores)[1]
        selected.append(winner)
        remaining.remove(winner)
    return tuple(sorted(selected))


def full_regret_curve(
    river: SyntheticRiver,
    *,
    budgets: Sequence[int] | None = None,
    gap_length: int = 30,
    random_repeats: int = 8,
    seed: int = 0,
) -> pd.DataFrame:
    """Synthetic implementation regret, not realized-outcome H3 evidence."""

    requested = range(1, river.n_stations) if budgets is None else budgets
    budget_values = [int(k) for k in requested if int(k) < river.n_stations]
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    policies = {
        name: policy
        for name, policy in POLICIES.items()
        if name != "current_network"
    }
    for k in budget_values:
        budget_rows: list[dict[str, Any]] = []
        for name, policy in policies.items():
            repeats = int(random_repeats) if name == "random" else 1
            scored = []
            selections = []
            for _ in range(repeats):
                policy_rng = np.random.default_rng(int(rng.integers(1_000_000_000)))
                if name == "proposed_recoverability":
                    selected = policy_proposed(
                        river, int(k), policy_rng, gap_length=gap_length
                    )
                elif name == "oracle":
                    selected = policy_oracle(
                        river, int(k), policy_rng, gap_length=gap_length
                    )
                else:
                    selected = policy(river, int(k), policy_rng)
                selections.append(selected)
                scored.append(evaluate_placement(river, selected, gap_length=gap_length))
            budget_rows.append(
                {
                    "policy": name,
                    "k": int(k),
                    "protected_fraction": float(k / river.n_stations),
                    "selected": (
                        "random_ensemble"
                        if name == "random"
                        else scored[0]["selected"]
                    ),
                    "evaluated_targets": (
                        "random_ensemble"
                        if name == "random"
                        else scored[0]["evaluated_targets"]
                    ),
                    "mean_mae": float(np.mean([item["mean_mae"] for item in scored])),
                    "worst_case_mae": float(
                        np.mean([item["worst_case_mae"] for item in scored])
                    ),
                }
            )
        mi_selected = greedy_mutual_information_indices(river.sigma, int(k))
        mi_score = evaluate_placement(river, mi_selected, gap_length=gap_length)
        budget_rows.append(
            {
                "policy": "greedy_mutual_information",
                "k": int(k),
                "protected_fraction": float(k / river.n_stations),
                "selected": mi_score["selected"],
                "evaluated_targets": mi_score["evaluated_targets"],
                "mean_mae": mi_score["mean_mae"],
                "worst_case_mae": mi_score["worst_case_mae"],
            }
        )
        oracle = next(row for row in budget_rows if row["policy"] == "oracle")
        oracle_loss = float(oracle["worst_case_mae"])
        for row in budget_rows:
            loss = float(row["worst_case_mae"])
            row["oracle_worst_case_mae"] = oracle_loss
            row["absolute_regret"] = loss - oracle_loss
            row["relative_regret"] = (loss - oracle_loss) / oracle_loss
            row["evidence_role"] = "synthetic_implementation_only"
            row["independent_realized_outcomes"] = False
            row["selection_and_evaluation_share_true_covariance"] = True
            rows.append(row)
    return pd.DataFrame(rows)


def regime_shift_stress_test(
    frame: pd.DataFrame,
    *,
    predictors: Mapping[str, str] = DEFAULT_PREDICTORS,
    outcome: str = "observed_recovery_loss",
    fit_regime: str = "fit_regime",
    evaluation_regime: str = "evaluation_regime",
) -> dict[str, pd.DataFrame]:
    """Calibrate on stable regimes and measure degradation after state changes."""

    units = station_gap_table(frame, predictors=predictors, outcome=outcome)
    labels = frame.groupby(
        ["network_id", "station_id", "gap_length"], as_index=False, sort=False
    )[[fit_regime, evaluation_regime]].first()
    units = units.merge(labels, on=["network_id", "station_id", "gap_length"])
    stable = units[fit_regime].eq(units[evaluation_regime])
    rows = []
    for name, column in predictors.items():
        train = units.loc[stable, [column, outcome]].dropna()
        coefficients = _fit_linear(
            train[column].to_numpy(dtype=float), train[outcome].to_numpy(dtype=float)
        )
        for stratum, mask in (("stable", stable), ("regime_shift", ~stable)):
            test = units.loc[mask, [column, outcome]].dropna()
            y = test[outcome].to_numpy(dtype=float)
            prediction = _apply_linear(test[column].to_numpy(dtype=float), coefficients)
            rows.append(
                {
                    "predictor": name,
                    "stratum": stratum,
                    "n_station_gaps": float(len(test)),
                    **_metrics(y, prediction),
                }
            )
    by_regime = pd.DataFrame(rows)
    stable_metrics = by_regime.loc[by_regime["stratum"].eq("stable")].set_index(
        "predictor"
    )
    shifted_metrics = by_regime.loc[
        by_regime["stratum"].eq("regime_shift")
    ].set_index("predictor")
    degradation = pd.DataFrame(
        {
            "spearman_loss": stable_metrics["spearman"] - shifted_metrics["spearman"],
            "r2_loss": stable_metrics["r2"] - shifted_metrics["r2"],
            "rmse_increase": shifted_metrics["rmse"] - stable_metrics["rmse"],
        }
    ).reset_index()
    return {"by_regime": by_regime, "degradation": degradation}


def cross_domain_transfer_summary(
    frame: pd.DataFrame,
    *,
    predictors: Mapping[str, str] = DEFAULT_PREDICTORS,
    outcome: str = "observed_recovery_loss",
    domain: str = "domain",
    source_domain: str | None = None,
) -> pd.DataFrame:
    """Summarize station×gap transfer from one source or by held-out domain."""

    units = station_gap_table(frame, predictors=predictors, outcome=outcome)
    domains = frame.groupby(
        ["network_id", "station_id", "gap_length"], as_index=False, sort=False
    )[domain].first()
    units = units.merge(domains, on=["network_id", "station_id", "gap_length"])
    rows = []
    targets = [
        item
        for item in pd.unique(units[domain])
        if source_domain is None or item != source_domain
    ]
    for held_domain in targets:
        train = units.loc[
            units[domain].eq(source_domain)
            if source_domain is not None
            else ~units[domain].eq(held_domain)
        ]
        test = units.loc[units[domain].eq(held_domain)]
        for name, column in predictors.items():
            train_usable = train[[column, outcome]].dropna()
            test_usable = test[[column, outcome]].dropna()
            coefficients = _fit_linear(
                train_usable[column].to_numpy(dtype=float),
                train_usable[outcome].to_numpy(dtype=float),
            )
            y = test_usable[outcome].to_numpy(dtype=float)
            prediction = _apply_linear(
                test_usable[column].to_numpy(dtype=float), coefficients
            )
            rows.append(
                {
                    "training_domain": (
                        source_domain if source_domain is not None else "all_other_domains"
                    ),
                    "target_domain": held_domain,
                    "predictor": name,
                    "n_station_gaps": float(len(test_usable)),
                    "n_networks": float(test.loc[test_usable.index, "network_id"].nunique()),
                    **_metrics(y, prediction),
                }
            )
    result = pd.DataFrame(rows)
    donor = result.loc[result["predictor"].eq("donor_r2")].set_index("target_domain")
    operator = result.loc[result["predictor"].eq("operator")].set_index("target_domain")
    deltas = pd.DataFrame(
        {
            "operator_delta_spearman_vs_donor": (
                operator["spearman"] - donor["spearman"]
            ),
            "operator_delta_r2_vs_donor": operator["r2"] - donor["r2"],
        }
    )
    return result.merge(deltas, left_on="target_domain", right_index=True)


def run_development_suite(
    scores: pd.DataFrame,
    river: SyntheticRiver,
    *,
    budgets: Sequence[int] | None = None,
    predictors: Mapping[str, str] = DEFAULT_PREDICTORS,
    source_domain: str | None = None,
) -> dict[str, Any]:
    """Run all open-development evidence from a station-gap score table."""

    lono = leave_one_network_out_predictions(scores, predictors=predictors)
    lono_summary = lono_metrics(lono)
    return {
        "station_gap_metrics": station_gap_metrics(scores, predictors=predictors),
        "lono_predictions": lono,
        "lono_metrics": lono_summary,
        "advancement_gate": lono_advancement_gate(lono_summary),
        "regret_curve": full_regret_curve(river, budgets=budgets),
        "regime_shift": regime_shift_stress_test(scores, predictors=predictors),
        "cross_domain_transfer": cross_domain_transfer_summary(
            scores, predictors=predictors, source_domain=source_domain
        ),
    }


__all__ = [
    "DEFAULT_PREDICTORS",
    "R2_GAIN_MIN",
    "SPEARMAN_GAIN_MIN",
    "cross_domain_transfer_summary",
    "full_regret_curve",
    "gaussian_mutual_information",
    "greedy_mutual_information_indices",
    "leave_one_network_out_nested_predictions",
    "leave_one_network_out_predictions",
    "lono_advancement_gate",
    "lono_metrics",
    "nested_lono_metrics",
    "regime_shift_stress_test",
    "run_development_suite",
    "station_gap_metrics",
    "station_gap_table",
]
