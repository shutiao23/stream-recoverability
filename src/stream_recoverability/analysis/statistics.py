"""Event-level paired inference for recoverability experiments."""

from __future__ import annotations

import warnings
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

DESIGN_REGIME_COLUMNS = (
    "experiment",
    "mask_type",
    "layout",
    "outage_mode",
    "overlap_ratio",
    "variable_pattern",
    "pattern",
    "window_length",
    "training_protocol",
    "fit_split",
    "tuning_split",
    "evaluation_split",
    "validation_scope",
    "is_external_validation",
    "external_validation_status",
    "target_station_id",
    "target",
    "missing_rate",
    "event_type",
    "failed_station_ids",
    "failed_stations",
    "failure_count",
    "network_size",
    "information_combination",
    "component_estimator",
)
COMPARISON_GROUP_COLUMNS = (*DESIGN_REGIME_COLUMNS, "gap_length")
MIXED_EFFECTS_DESIGN_COLUMNS = tuple(
    column for column in DESIGN_REGIME_COLUMNS if column != "target_station_id"
)
DEFAULT_PAIR_COLUMNS = (
    "scenario_id",
    "condition_id",
    "target_gap_id",
    "experiment",
    "mask_type",
    "layout",
    "outage_mode",
    "overlap_ratio",
    "variable_pattern",
    "window_length",
    "training_protocol",
    "validation_scope",
    "station_id",
    "target",
    "gap_length",
    "missing_rate",
    "pattern",
    "mask_seed",
)


def require_columns(frame: pd.DataFrame, columns: Sequence[str], context: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"{context} requires columns: {missing}")


def paired_value_table(
    events: pd.DataFrame,
    model_a: str,
    model_b: str,
    *,
    metric: str = "MAE",
    model_col: str = "model",
    pair_cols: Sequence[str] | None = None,
) -> tuple[pd.DataFrame, str | None]:
    """Align two models on identical mask/event units.

    Replicate rows are averaged within each event/mask; daily rows are never
    treated as independent statistical units.
    """

    require_columns(events, [model_col, metric], "paired comparison")
    if pair_cols is None:
        pair_cols = [column for column in DEFAULT_PAIR_COLUMNS if column in events]
    else:
        pair_cols = list(pair_cols)
        require_columns(events, pair_cols, "paired comparison")
    if not pair_cols:
        return pd.DataFrame(
            columns=[model_a, model_b, "difference"]
        ), "no event identifier columns"

    selected = events.loc[
        events[model_col].astype(str).isin([model_a, model_b]),
        [*pair_cols, model_col, metric],
    ].copy()
    selected[metric] = pd.to_numeric(selected[metric], errors="coerce")
    selected = selected.dropna(subset=[metric])
    if selected.empty:
        return pd.DataFrame(
            columns=[*pair_cols, model_a, model_b, "difference"]
        ), "no finite paired values"
    collapsed = (
        selected.groupby([*pair_cols, model_col], dropna=False, observed=True)[metric]
        .mean()
        .unstack(model_col)
    )
    if model_a not in collapsed or model_b not in collapsed:
        return pd.DataFrame(
            columns=[*pair_cols, model_a, model_b, "difference"]
        ), "one model has no values"
    paired = collapsed[[model_a, model_b]].dropna().reset_index()
    if paired.empty:
        return pd.DataFrame(
            columns=[*pair_cols, model_a, model_b, "difference"]
        ), "models share no event units"
    paired["difference"] = paired[model_a] - paired[model_b]
    return paired, None


def paired_bootstrap_ci(
    events: pd.DataFrame,
    model_a: str,
    model_b: str,
    *,
    metric: str = "MAE",
    model_col: str = "model",
    pair_cols: Sequence[str] | None = None,
    statistic: str = "mean",
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> dict[str, Any]:
    """Paired bootstrap CI for ``model_a - model_b`` at the event unit."""

    if n_boot < 1:
        raise ValueError("n_boot must be positive")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")
    if statistic not in {"mean", "median"}:
        raise ValueError("statistic must be 'mean' or 'median'")
    paired, reason = paired_value_table(
        events,
        model_a,
        model_b,
        metric=metric,
        model_col=model_col,
        pair_cols=pair_cols,
    )
    if reason is not None:
        return {
            "model_a": model_a,
            "model_b": model_b,
            "metric": metric,
            "estimate": np.nan,
            "ci_lower": np.nan,
            "ci_upper": np.nan,
            "n_pairs": 0,
            "reason": reason,
        }
    differences = paired["difference"].to_numpy(dtype=float)
    estimator: Callable[[np.ndarray], float] = (
        np.mean if statistic == "mean" else np.median
    )
    rng = np.random.default_rng(seed)
    draws = np.empty(n_boot, dtype=float)
    for draw in range(n_boot):
        sample = rng.choice(differences, size=len(differences), replace=True)
        draws[draw] = estimator(sample)
    alpha = (1.0 - confidence) / 2.0
    return {
        "model_a": model_a,
        "model_b": model_b,
        "metric": metric,
        "statistic": statistic,
        "estimate": float(estimator(differences)),
        "ci_lower": float(np.quantile(draws, alpha)),
        "ci_upper": float(np.quantile(draws, 1.0 - alpha)),
        "n_pairs": len(differences),
        "reason": None,
    }


def paired_wilcoxon(
    events: pd.DataFrame,
    model_a: str,
    model_b: str,
    *,
    metric: str = "MAE",
    model_col: str = "model",
    pair_cols: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Two-sided paired Wilcoxon signed-rank test at the event unit."""

    paired, reason = paired_value_table(
        events,
        model_a,
        model_b,
        metric=metric,
        model_col=model_col,
        pair_cols=pair_cols,
    )
    if reason is not None:
        return {
            "statistic": np.nan,
            "p_value": np.nan,
            "n_pairs": 0,
            "median_difference": np.nan,
            "reason": reason,
        }
    differences = paired["difference"].to_numpy(dtype=float)
    if np.allclose(differences, 0.0):
        statistic_value, p_value = 0.0, 1.0
    else:
        result = wilcoxon(differences, alternative="two-sided", zero_method="wilcox")
        statistic_value, p_value = float(result.statistic), float(result.pvalue)
    return {
        "statistic": statistic_value,
        "p_value": p_value,
        "n_pairs": len(differences),
        "median_difference": float(np.median(differences)),
        "reason": None,
    }


def holm_correction(p_values: Sequence[float]) -> np.ndarray:
    """Holm family-wise adjusted p-values, preserving input order and NaNs."""

    values = np.asarray(p_values, dtype=float)
    adjusted = np.full(values.shape, np.nan, dtype=float)
    finite_positions = np.flatnonzero(np.isfinite(values))
    if not finite_positions.size:
        return adjusted
    order = finite_positions[np.argsort(values[finite_positions], kind="stable")]
    running = 0.0
    total = len(order)
    for rank, position in enumerate(order):
        candidate = min(1.0, (total - rank) * values[position])
        running = max(running, candidate)
        adjusted[position] = running
    return adjusted


def compare_models(
    events: pd.DataFrame,
    *,
    baseline_model: str = "climatology",
    metric: str = "MAE",
    model_col: str = "model",
    group_cols: Sequence[str] = COMPARISON_GROUP_COLUMNS,
    n_boot: int = 2000,
    seed: int = 0,
) -> pd.DataFrame:
    """Compare every model with a baseline within scientifically relevant groups."""

    require_columns(events, [model_col, metric], "model comparison")
    active_groups = [column for column in group_cols if column in events]
    grouped = (
        events.groupby(active_groups, dropna=False, observed=True)
        if active_groups
        else [((), events)]
    )
    rows: list[dict[str, Any]] = []
    for group_key, group in grouped:
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        group_values = dict(
            zip(active_groups, group_key if active_groups else (), strict=True)
        )
        models = sorted(set(group[model_col].dropna().astype(str)) - {baseline_model})
        for index, model in enumerate(models):
            bootstrap = paired_bootstrap_ci(
                group,
                model,
                baseline_model,
                metric=metric,
                model_col=model_col,
                n_boot=n_boot,
                seed=seed + index,
            )
            test = paired_wilcoxon(
                group,
                model,
                baseline_model,
                metric=metric,
                model_col=model_col,
            )
            rows.append(
                {
                    **group_values,
                    **bootstrap,
                    "wilcoxon_statistic": test["statistic"],
                    "p_value": test["p_value"],
                    "median_difference": test["median_difference"],
                    "test_reason": test["reason"],
                }
            )
    result = pd.DataFrame(rows)
    if not result.empty:
        result["p_holm"] = holm_correction(result["p_value"].to_numpy(dtype=float))
    return result


def fit_mixed_effects_by_design(
    events: pd.DataFrame,
    *,
    outcome: str = "MAE",
    design_cols: Sequence[str] = MIXED_EFFECTS_DESIGN_COLUMNS,
    fixed_effects: Sequence[str] = ("model", "gap_length"),
    group_col: str = "station_id",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit separate mixed models for each experimental-design regime."""

    active_design = [column for column in design_cols if column in events]
    grouped = (
        events.groupby(active_design, dropna=False, observed=True)
        if active_design
        else [((), events)]
    )
    coefficient_parts: list[pd.DataFrame] = []
    diagnostics: list[dict[str, Any]] = []
    for group_key, group in grouped:
        if active_design and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(
            zip(active_design, group_key if active_design else (), strict=True)
        )
        coefficients, summary = fit_mixed_effects(
            group,
            outcome=outcome,
            fixed_effects=fixed_effects,
            group_col=group_col,
        )
        diagnostics.append({**metadata, **summary})
        if coefficients.empty:
            continue
        for column, value in reversed(tuple(metadata.items())):
            coefficients.insert(0, column, value)
        coefficient_parts.append(coefficients)
    return (
        pd.concat(coefficient_parts, ignore_index=True)
        if coefficient_parts
        else pd.DataFrame(),
        pd.DataFrame(diagnostics),
    )


def fit_mixed_effects(
    events: pd.DataFrame,
    *,
    outcome: str = "MAE",
    fixed_effects: Sequence[str] = ("model", "gap_length", "pattern"),
    group_col: str = "station_id",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fit a random-intercept mixed model when the table is identifiable."""

    required = [
        outcome,
        group_col,
        *[column for column in fixed_effects if column in events],
    ]
    require_columns(events, [outcome, group_col], "mixed-effects model")
    data = events.loc[:, list(dict.fromkeys(required))].copy()
    data[outcome] = pd.to_numeric(data[outcome], errors="coerce")
    data = data.dropna(subset=[outcome, group_col])
    if data[group_col].nunique() < 2:
        return pd.DataFrame(), {
            "reason": "at least two random-effect groups are required"
        }
    if len(data) < 8 or data[outcome].nunique() < 2:
        return pd.DataFrame(), {"reason": "insufficient non-constant observations"}

    terms: list[str] = []
    used_fixed_effects: list[str] = []
    for column in fixed_effects:
        if column not in data or data[column].nunique(dropna=True) < 2:
            continue
        quoted = f'Q("{column}")'
        if pd.api.types.is_numeric_dtype(data[column]):
            terms.append(quoted)
        else:
            terms.append(f"C({quoted})")
        used_fixed_effects.append(column)
    if not terms:
        return pd.DataFrame(), {"reason": "no varying fixed effects are identifiable"}
    data = data.dropna(subset=[outcome, group_col, *used_fixed_effects]).reset_index(
        drop=True
    )
    if data[group_col].nunique() < 2 or len(data) < 8:
        return pd.DataFrame(), {
            "reason": "insufficient complete rows after fixed-effect filtering"
        }

    try:
        import statsmodels.formula.api as smf

        formula = f'Q("{outcome}") ~ ' + " + ".join(terms)
        with warnings.catch_warnings(record=True) as caught, np.errstate(all="ignore"):
            warnings.simplefilter("always")
            fitted = smf.mixedlm(formula, data=data, groups=data[group_col]).fit(
                reml=False, method="lbfgs", disp=False
            )
    except (ValueError, IndexError, RuntimeError, np.linalg.LinAlgError) as exc:
        return pd.DataFrame(), {"reason": f"mixed-effects fit failed: {exc}"}

    warning_messages = [str(item.message) for item in caught]
    identifiability_markers = (
        "singular",
        "not positive definite",
        "failed to converge",
        "boundary of the parameter space",
    )
    identifiability_warnings = [
        message
        for message in warning_messages
        if any(marker in message.lower() for marker in identifiability_markers)
    ]
    if not fitted.converged or identifiability_warnings:
        detail = "; ".join(dict.fromkeys(identifiability_warnings))
        if not detail:
            detail = "optimizer did not converge"
        return pd.DataFrame(), {
            "reason": f"mixed-effects model not identifiable: {detail}"
        }

    coefficients = pd.DataFrame(
        {
            "term": fitted.params.index,
            "estimate": fitted.params.to_numpy(dtype=float),
            "std_error": fitted.bse.reindex(fitted.params.index).to_numpy(dtype=float),
            "p_value": fitted.pvalues.reindex(fitted.params.index).to_numpy(
                dtype=float
            ),
        }
    )
    summary = {
        "reason": None,
        "formula": formula,
        "n_observations": int(fitted.nobs),
        "n_groups": int(data[group_col].nunique()),
        "converged": bool(fitted.converged),
        "aic": float(fitted.aic),
        "bic": float(fitted.bic),
    }
    return coefficients, summary


__all__ = [
    "COMPARISON_GROUP_COLUMNS",
    "DEFAULT_PAIR_COLUMNS",
    "DESIGN_REGIME_COLUMNS",
    "MIXED_EFFECTS_DESIGN_COLUMNS",
    "compare_models",
    "fit_mixed_effects",
    "fit_mixed_effects_by_design",
    "holm_correction",
    "paired_bootstrap_ci",
    "paired_value_table",
    "paired_wilcoxon",
    "require_columns",
]
