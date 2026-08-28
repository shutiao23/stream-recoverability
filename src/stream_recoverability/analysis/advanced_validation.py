"""Post-confirmation calibration and decision analyses for the v11 study.

The functions in this module deliberately distinguish three evidence roles:

* development-only calibration, which may select a method;
* labelled domain adaptation, which measures the cost of transporting it; and
* untouched confirmation, which must not be relabelled after adaptation.

All resampling is performed by river network whenever network identifiers are
available.  Station-gap rows are repeated observations, not independent
rivers.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from scipy.stats import beta, spearmanr


def finite_sample_quantile(values: Sequence[float], coverage: float) -> float:
    """Return the split-conformal ``higher`` quantile with finite-sample rank."""

    scores = np.sort(np.asarray(values, dtype=float))
    scores = scores[np.isfinite(scores)]
    if not len(scores):
        return float("nan")
    if not 0.0 < coverage < 1.0:
        raise ValueError("coverage must be strictly between zero and one")
    rank = min(len(scores), int(np.ceil((len(scores) + 1) * coverage)))
    return float(scores[rank - 1])


def horizon_bin(values: pd.Series) -> pd.Series:
    """Stable gap-length bins used by all Mondrian interval analyses."""

    numeric = pd.to_numeric(values, errors="coerce")
    return pd.cut(
        numeric,
        bins=[-np.inf, 14, 60, 180, np.inf],
        labels=["7-14", "30-60", "90-180", "365+"],
        right=True,
    ).astype("string")


def mondrian_intervals(
    calibration: pd.DataFrame,
    evaluation: pd.DataFrame,
    *,
    calibration_prediction: str,
    evaluation_prediction: str,
    outcome: str = "observed_recovery_loss",
    strata: Sequence[str] = ("horizon_bin",),
    coverage: float = 0.90,
    min_stratum_rows: int = 20,
) -> pd.DataFrame:
    """Apply absolute-residual split conformal intervals by fixed strata.

    Sparse or unseen strata fall back to the global calibration score.  The
    returned table records that fallback explicitly.
    """

    train = calibration.copy()
    test = evaluation.copy()
    if "horizon_bin" in strata:
        if "horizon_bin" not in train:
            train["horizon_bin"] = horizon_bin(train["gap_length"])
        if "horizon_bin" not in test:
            test["horizon_bin"] = horizon_bin(test["gap_length"])
    train["_score"] = np.abs(
        train[outcome].to_numpy(dtype=float)
        - train[calibration_prediction].to_numpy(dtype=float)
    )
    global_radius = finite_sample_quantile(train["_score"], coverage)
    radii: dict[tuple[object, ...], tuple[float, int]] = {}
    keys = list(strata)
    grouper: str | list[str] = keys[0] if len(keys) == 1 else keys
    for key, group in train.groupby(grouper, dropna=False):
        key_tuple = key if isinstance(key, tuple) else (key,)
        if len(group) >= min_stratum_rows:
            radii[key_tuple] = (
                finite_sample_quantile(group["_score"], coverage),
                len(group),
            )

    radius = []
    source = []
    calibration_n = []
    for row in test[keys].itertuples(index=False, name=None):
        if row in radii:
            value, count = radii[row]
            radius.append(value)
            source.append("mondrian")
            calibration_n.append(count)
        else:
            radius.append(global_radius)
            source.append("global_fallback")
            calibration_n.append(len(train))
    result = test.copy()
    result["conformal_radius"] = radius
    result["conformal_source"] = source
    result["conformal_calibration_n"] = calibration_n
    result["prediction_lower"] = np.maximum(
        0.0, result[evaluation_prediction] - result["conformal_radius"]
    )
    result["prediction_upper"] = (
        result[evaluation_prediction] + result["conformal_radius"]
    )
    return result


def interval_metrics(
    frame: pd.DataFrame,
    *,
    prediction: str = "predicted_loss",
    outcome: str = "observed_recovery_loss",
) -> dict[str, float]:
    """Return row and whole-network interval metrics and an efficiency ratio."""

    covered = frame[outcome].between(
        frame["prediction_lower"], frame["prediction_upper"], inclusive="both"
    )
    by_network = covered.groupby(frame["network_id"]).all()
    width = frame["prediction_upper"] - frame["prediction_lower"]
    median_loss = float(frame[outcome].median())
    return {
        "n_networks": float(frame["network_id"].nunique()),
        "n_station_gaps": float(len(frame)),
        "row_coverage": float(covered.mean()),
        "network_simultaneous_coverage": float(by_network.mean()),
        "mean_width": float(width.mean()),
        "median_width": float(width.median()),
        "median_loss": median_loss,
        "median_width_over_median_loss": (
            float(width.median() / median_loss) if median_loss > 0 else float("nan")
        ),
        "mean_prediction": float(frame[prediction].mean()),
    }


def network_block_scaled_intervals(
    calibration: pd.DataFrame,
    evaluation: pd.DataFrame,
    *,
    calibration_prediction: str,
    evaluation_prediction: str,
    outcome: str = "observed_recovery_loss",
    coverage: float = 0.90,
    scale_power: float = 0.70,
    scale_floor: float = 0.10,
) -> pd.DataFrame:
    """Simultaneous-network conformal intervals with prediction-scaled scores.

    One score is retained per calibration network: the maximum absolute
    residual after division by the predicted-loss scale.  The finite-sample
    quantile therefore targets a wholly new network, rather than a new row.
    ``scale_power`` is fixed from development-only efficiency comparisons.
    """

    train = calibration.copy()
    test = evaluation.copy()
    train_scale = train[calibration_prediction].clip(lower=scale_floor) ** scale_power
    test_scale = test[evaluation_prediction].clip(lower=scale_floor) ** scale_power
    train["_scaled_score"] = (
        np.abs(train[outcome] - train[calibration_prediction]) / train_scale
    )
    network_scores = train.groupby("network_id")["_scaled_score"].max()
    multiplier = finite_sample_quantile(network_scores, coverage)
    radius = multiplier * test_scale
    result = test.copy()
    result["conformal_radius"] = radius
    result["conformal_multiplier"] = multiplier
    result["conformal_scale_power"] = scale_power
    result["conformal_calibration_networks"] = train["network_id"].nunique()
    result["prediction_lower"] = np.maximum(
        0.0, result[evaluation_prediction] - radius
    )
    result["prediction_upper"] = result[evaluation_prediction] + radius
    return result


def calibration_components(
    frame: pd.DataFrame,
    *,
    prediction: str = "predicted_loss",
    outcome: str = "observed_recovery_loss",
) -> dict[str, float]:
    """Separate within-network ordering from between-network ordering."""

    usable = frame[["network_id", prediction, outcome]].dropna().copy()
    means = usable.groupby("network_id")[[prediction, outcome]].mean()
    within_prediction = usable[prediction] - usable.groupby("network_id")[
        prediction
    ].transform("mean")
    within_outcome = usable[outcome] - usable.groupby("network_id")[outcome].transform(
        "mean"
    )
    return {
        "pooled_spearman": float(
            spearmanr(usable[prediction], usable[outcome]).statistic
        ),
        "within_network_spearman": float(
            spearmanr(within_prediction, within_outcome).statistic
        ),
        "between_network_spearman": float(
            spearmanr(means[prediction], means[outcome]).statistic
        ),
        "n_networks": float(len(means)),
        "n_station_gaps": float(len(usable)),
    }


def clopper_pearson_upper(errors: int, total: int, confidence: float = 0.95) -> float:
    """One-sided exact upper confidence limit for a Bernoulli error rate."""

    if total <= 0:
        return 1.0
    if errors >= total:
        return 1.0
    return float(beta.ppf(confidence, errors + 1, total - errors))


def risk_control_threshold(
    calibration: pd.DataFrame,
    *,
    risk_column: str,
    loss_column: str = "observed_recovery_loss",
    unsafe_loss_c: float = 0.5,
    false_release_cap: float = 0.05,
    confidence: float = 0.95,
) -> dict[str, float | int | str]:
    """Learn the largest low-risk prefix with an exact false-release bound.

    The procedure is a conservative learn-then-test rule.  It returns no
    threshold when the labelled calibration budget cannot certify any prefix.
    """

    ordered = calibration[[risk_column, loss_column]].dropna().sort_values(
        risk_column, kind="mergesort"
    )
    unsafe = (ordered[loss_column].to_numpy(dtype=float) > unsafe_loss_c).astype(int)
    cumulative = np.cumsum(unsafe)
    accepted = -1
    accepted_upper = 1.0
    for index, errors in enumerate(cumulative):
        upper = clopper_pearson_upper(int(errors), index + 1, confidence)
        if upper <= false_release_cap:
            accepted = index
            accepted_upper = upper
    if accepted < 0:
        return {
            "status": "no_certified_release",
            "threshold": float("nan"),
            "n_calibration": int(len(ordered)),
            "n_certified": 0,
            "calibration_errors": 0,
            "error_upper_bound": 1.0,
        }
    return {
        "status": "certified",
        "threshold": float(ordered.iloc[accepted][risk_column]),
        "n_calibration": int(len(ordered)),
        "n_certified": int(accepted + 1),
        "calibration_errors": int(cumulative[accepted]),
        "error_upper_bound": float(accepted_upper),
    }


def evaluate_risk_control(
    evaluation: pd.DataFrame,
    rule: dict[str, float | int | str],
    *,
    risk_column: str,
    loss_column: str = "observed_recovery_loss",
    unsafe_loss_c: float = 0.5,
) -> dict[str, float | int | str]:
    """Evaluate a fitted risk-control rule on rows not used for calibration."""

    threshold = float(rule["threshold"])
    released = (
        np.zeros(len(evaluation), dtype=bool)
        if not np.isfinite(threshold)
        else evaluation[risk_column].to_numpy(dtype=float) <= threshold
    )
    unsafe = evaluation[loss_column].to_numpy(dtype=float) > unsafe_loss_c
    return {
        **rule,
        "n_evaluation": int(len(evaluation)),
        "n_released": int(released.sum()),
        "safe_fill_fraction": float(released.mean()) if len(released) else 0.0,
        "false_release_rate": (
            float(unsafe[released].mean()) if released.any() else float("nan")
        ),
    }


def recalibration_budget_curve(
    frame: pd.DataFrame,
    *,
    budgets: Sequence[int] = (0, 25, 50, 100),
    repeats: int = 100,
    seed: int = 0,
    domain_column: str = "domain_group",
    prediction: str = "predicted_loss",
    outcome: str = "observed_recovery_loss",
) -> pd.DataFrame:
    """Measure labelled examples needed for affine domain recalibration.

    Splits are grouped by network: a network contributes either calibration
    labels or evaluation labels within a repeat.  ``budget`` counts labelled
    station-gap rows, but whole networks are added until that budget is met.
    """

    rng = np.random.default_rng(seed)
    rows: list[dict[str, float | int | str]] = []
    for domain, domain_frame in frame.groupby(domain_column):
        networks = np.asarray(sorted(domain_frame["network_id"].unique()))
        for repeat in range(repeats):
            order = rng.permutation(networks)
            for budget in budgets:
                if budget <= 0:
                    calibration = domain_frame.iloc[0:0]
                    evaluation = domain_frame
                    intercept, slope = 0.0, 1.0
                else:
                    chosen: list[str] = []
                    n_rows = 0
                    for network in order:
                        chosen.append(str(network))
                        n_rows += int(domain_frame["network_id"].eq(network).sum())
                        if n_rows >= budget:
                            break
                    calibration = domain_frame.loc[
                        domain_frame["network_id"].isin(chosen)
                    ]
                    evaluation = domain_frame.loc[
                        ~domain_frame["network_id"].isin(chosen)
                    ]
                    if len(calibration) < 2 or evaluation.empty:
                        continue
                    design = np.column_stack(
                        [np.ones(len(calibration)), calibration[prediction]]
                    )
                    intercept, slope = np.linalg.lstsq(
                        design, calibration[outcome].to_numpy(dtype=float), rcond=None
                    )[0]
                calibrated = intercept + slope * evaluation[prediction].to_numpy(
                    dtype=float
                )
                if len(evaluation) < 2 or np.std(calibrated) == 0:
                    continue
                design_eval = np.column_stack([np.ones(len(evaluation)), calibrated])
                eval_intercept, eval_slope = np.linalg.lstsq(
                    design_eval,
                    evaluation[outcome].to_numpy(dtype=float),
                    rcond=None,
                )[0]
                rows.append(
                    {
                        domain_column: str(domain),
                        "repeat": repeat,
                        "requested_budget": int(budget),
                        "labelled_rows": int(len(calibration)),
                        "labelled_networks": int(
                            calibration["network_id"].nunique()
                        ),
                        "evaluation_networks": int(
                            evaluation["network_id"].nunique()
                        ),
                        "recalibration_intercept": float(intercept),
                        "recalibration_slope": float(slope),
                        "evaluation_intercept": float(eval_intercept),
                        "evaluation_slope": float(eval_slope),
                        "evaluation_spearman": float(
                            spearmanr(calibrated, evaluation[outcome]).statistic
                        ),
                        "slope_in_target_band": bool(0.9 <= eval_slope <= 1.1),
                    }
                )
    return pd.DataFrame(rows)


__all__ = [
    "calibration_components",
    "clopper_pearson_upper",
    "evaluate_risk_control",
    "finite_sample_quantile",
    "horizon_bin",
    "interval_metrics",
    "mondrian_intervals",
    "network_block_scaled_intervals",
    "recalibration_budget_curve",
    "risk_control_threshold",
]
