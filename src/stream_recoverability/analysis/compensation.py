"""Information-combination, exact Shapley, mutual-information, and TE tools."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_regression

INFORMATION_SOURCES = ("A", "B", "C", "D")
INFORMATION_UNIT_GROUP_COLUMNS = (
    "scenario_id",
    "training_seed",
    "mask_seed",
    "experiment",
    "window_length",
    "training_protocol",
    "validation_scope",
    "station_id",
    "target",
    "gap_length",
    "model",
)


def benjamini_hochberg_fdr(
    p_values: Sequence[float] | np.ndarray | pd.Series,
) -> np.ndarray:
    """Return Benjamini-Hochberg adjusted p-values, preserving missing values."""

    values = pd.to_numeric(pd.Series(p_values), errors="coerce").to_numpy(dtype=float)
    adjusted = np.full(len(values), np.nan, dtype=float)
    finite = np.flatnonzero(np.isfinite(values))
    if not len(finite):
        return adjusted
    if np.any((values[finite] < 0) | (values[finite] > 1)):
        raise ValueError("p-values must lie between zero and one")
    order = finite[np.argsort(values[finite], kind="stable")]
    ranked = values[order] * len(order) / np.arange(1, len(order) + 1)
    adjusted[order] = np.minimum.accumulate(ranked[::-1])[::-1].clip(0.0, 1.0)
    return adjusted


def information_combinations(
    sources: Sequence[str] = INFORMATION_SOURCES,
) -> list[frozenset[str]]:
    """Return all ``2**len(sources)`` subsets in stable binary order."""

    normalized = tuple(str(source) for source in sources)
    return [
        frozenset(source for bit, source in enumerate(normalized) if mask & (1 << bit))
        for mask in range(1 << len(normalized))
    ]


def normalize_combination(
    value: object,
    sources: Sequence[str] = INFORMATION_SOURCES,
) -> frozenset[str]:
    """Parse ``S0+A+C``, ``A,C``, JSON lists, or iterable source labels."""

    allowed = {str(source) for source in sources}
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return frozenset()
    if isinstance(value, str):
        text = value.strip()
        if not text or text.upper() in {"S0", "NONE", "EMPTY"}:
            return frozenset()
        if text.startswith("["):
            parsed = json.loads(text)
            tokens = [str(token).strip() for token in parsed]
        else:
            cleaned = re.sub(r"\bS0\b", "", text, flags=re.IGNORECASE)
            tokens = [token for token in re.split(r"[+,|;/\s]+", cleaned) if token]
            if (
                len(tokens) == 1
                and len(tokens[0]) > 1
                and set(tokens[0]).issubset(allowed)
            ):
                tokens = list(tokens[0])
    elif isinstance(value, (set, frozenset, list, tuple, np.ndarray)):
        tokens = [str(token).strip() for token in value]
    else:
        raise ValueError(f"unsupported information combination: {value!r}")
    normalized = frozenset(token.upper() for token in tokens if token.upper() != "S0")
    unknown = sorted(normalized - allowed)
    if unknown:
        raise ValueError(f"unknown information sources: {unknown}")
    return normalized


def combination_label(
    combination: object,
    sources: Sequence[str] = INFORMATION_SOURCES,
) -> str:
    subset = normalize_combination(combination, sources)
    ordered = [source for source in sources if source in subset]
    return "S0" if not ordered else "S0+" + "+".join(ordered)


def build_value_function(
    events: pd.DataFrame,
    *,
    metric: str = "MAE",
    combination_col: str = "information_combination",
    group_cols: Sequence[str] = INFORMATION_UNIT_GROUP_COLUMNS,
    higher_is_better: bool | None = None,
    sources: Sequence[str] = INFORMATION_SOURCES,
) -> pd.DataFrame:
    """Aggregate event results into a higher-is-better value function."""

    missing = sorted({metric, combination_col} - set(events.columns))
    if missing:
        raise ValueError(f"value-function analysis requires columns: {missing}")
    if higher_is_better is None:
        higher_is_better = metric.lower() not in {
            "mae",
            "rmse",
            "nmae",
            "nrmse",
            "bias_abs",
            "interval_width_90",
        }
    active_groups = [column for column in group_cols if column in events]
    data = events.loc[:, [*active_groups, combination_col, metric]].copy()
    data[metric] = pd.to_numeric(data[metric], errors="coerce")
    data["combination"] = data[combination_col].map(
        lambda value: combination_label(value, sources)
    )
    grouped = (
        data.groupby([*active_groups, "combination"], dropna=False, observed=True)[
            metric
        ]
        .agg(
            [
                ("raw_metric", "mean"),
                ("n_events", "size"),
                ("n_finite_events", "count"),
            ]
        )
        .reset_index()
    )
    grouped["value"] = (
        grouped["raw_metric"] if higher_is_better else -grouped["raw_metric"]
    )
    grouped["higher_is_better"] = bool(higher_is_better)
    expected_labels = {
        combination_label(value, sources) for value in information_combinations(sources)
    }
    diagnostics: list[dict[str, Any]] = []
    units = (
        data.groupby(active_groups, dropna=False, observed=True)
        if active_groups
        else [((), data)]
    )
    for group_key, unit in units:
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(
            zip(active_groups, group_key if active_groups else (), strict=True)
        )
        finite_metric = pd.to_numeric(unit[metric], errors="coerce").to_numpy(
            dtype=float
        )
        finite = unit.loc[np.isfinite(finite_metric), "combination"]
        present = set(finite)
        missing_labels = sorted(expected_labels - present)
        duplicate_labels = sorted(
            label for label, count in finite.value_counts().items() if count > 1
        )
        reasons = []
        if missing_labels:
            reasons.append(f"missing or non-finite combinations: {missing_labels}")
        if duplicate_labels:
            reasons.append(f"duplicate combination rows: {duplicate_labels}")
        diagnostics.append(
            {
                **metadata,
                "complete_2_to_n": not reasons,
                "missing_combinations": json.dumps(
                    missing_labels, separators=(",", ":")
                ),
                "duplicate_combinations": json.dumps(
                    duplicate_labels, separators=(",", ":")
                ),
                "reason": "; ".join(reasons) if reasons else None,
            }
        )
    diagnostics_frame = pd.DataFrame(diagnostics)
    if active_groups:
        grouped = grouped.merge(
            diagnostics_frame,
            on=active_groups,
            how="left",
            validate="many_to_one",
        )
    elif len(diagnostics_frame):
        for column in (
            "complete_2_to_n",
            "missing_combinations",
            "duplicate_combinations",
            "reason",
        ):
            grouped[column] = diagnostics_frame.iloc[0][column]
    return grouped


def _normalized_value_mapping(
    value_function: Mapping[object, float],
    sources: Sequence[str],
) -> dict[frozenset[str], float]:
    normalized: dict[frozenset[str], float] = {}
    for key, value in value_function.items():
        subset = normalize_combination(key, sources)
        if subset in normalized:
            raise ValueError(
                f"duplicate value for {combination_label(subset, sources)}"
            )
        normalized[subset] = float(value)
    expected = set(information_combinations(sources))
    missing = expected - set(normalized)
    if missing:
        labels = sorted(combination_label(value, sources) for value in missing)
        raise ValueError(f"exact Shapley requires all combinations; missing: {labels}")
    if not all(np.isfinite(value) for value in normalized.values()):
        raise ValueError("exact Shapley requires finite values for all combinations")
    return normalized


def exact_shapley(
    value_function: Mapping[object, float],
    sources: Sequence[str] = INFORMATION_SOURCES,
) -> dict[str, float]:
    """Compute exact Shapley values by enumerating every source subset."""

    players = tuple(str(source) for source in sources)
    values = _normalized_value_mapping(value_function, players)
    n_players = len(players)
    denominator = math.factorial(n_players)
    result: dict[str, float] = {}
    for player in players:
        contribution = 0.0
        others = [source for source in players if source != player]
        for subset in information_combinations(others):
            size = len(subset)
            weight = (
                math.factorial(size)
                * math.factorial(n_players - size - 1)
                / denominator
            )
            contribution += weight * (values[subset | {player}] - values[subset])
        result[player] = float(contribution)
    return result


def shapley_table(
    value_table: pd.DataFrame,
    *,
    combination_col: str = "combination",
    value_col: str = "value",
    group_cols: Sequence[str] = INFORMATION_UNIT_GROUP_COLUMNS,
    sources: Sequence[str] = INFORMATION_SOURCES,
) -> pd.DataFrame:
    """Compute exact Shapley rows, returning NaN plus a reason when incomplete."""

    missing = sorted({combination_col, value_col} - set(value_table.columns))
    if missing:
        raise ValueError(f"Shapley table requires columns: {missing}")
    active_groups = [column for column in group_cols if column in value_table]
    grouped = (
        value_table.groupby(active_groups, dropna=False, observed=True)
        if active_groups
        else [((), value_table)]
    )
    rows: list[dict[str, Any]] = []
    full_subset = frozenset(sources)
    for group_key, group in grouped:
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(
            zip(active_groups, group_key if active_groups else (), strict=True)
        )
        mapping = {
            normalize_combination(combination, sources): value
            for combination, value in group[[combination_col, value_col]].itertuples(
                index=False, name=None
            )
        }
        declared_reason = (
            str(group.loc[group["reason"].notna(), "reason"].iloc[0])
            if "reason" in group and group["reason"].notna().any()
            else None
        )
        missing_combinations = (
            group["missing_combinations"].iloc[0]
            if "missing_combinations" in group
            else None
        )
        try:
            if declared_reason is not None:
                raise ValueError(declared_reason)
            if len(mapping) != len(group):
                raise ValueError("exact Shapley requires one row per combination")
            contributions = exact_shapley(mapping, sources)
            baseline = float(mapping[frozenset()])
            full = float(mapping[full_subset])
            residual = float(sum(contributions.values()) - (full - baseline))
            reason = None
        except ValueError as exc:
            contributions = {source: np.nan for source in sources}
            baseline = full = residual = np.nan
            reason = str(exc)
        for source in sources:
            rows.append(
                {
                    **metadata,
                    "source": source,
                    "shapley": contributions[source],
                    "baseline_value": baseline,
                    "full_value": full,
                    "total_gain": full - baseline,
                    "efficiency_residual": residual,
                    "excluded": reason is not None,
                    "missing_combinations": missing_combinations,
                    "reason": reason,
                }
            )
    return pd.DataFrame(rows)


def compensation_gains(
    value_table: pd.DataFrame,
    *,
    combination_col: str = "combination",
    value_col: str = "value",
    raw_metric_col: str = "raw_metric",
    group_cols: Sequence[str] = INFORMATION_UNIT_GROUP_COLUMNS,
    sources: Sequence[str] = INFORMATION_SOURCES,
) -> pd.DataFrame:
    """Report each source's full-removal and mean marginal compensation gains."""

    missing = sorted({combination_col, value_col} - set(value_table.columns))
    if missing:
        raise ValueError(f"compensation gains require columns: {missing}")
    active_groups = [column for column in group_cols if column in value_table]
    grouped = (
        value_table.groupby(active_groups, dropna=False, observed=True)
        if active_groups
        else [((), value_table)]
    )
    rows: list[dict[str, Any]] = []
    full = frozenset(sources)
    for group_key, group in grouped:
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(
            zip(active_groups, group_key if active_groups else (), strict=True)
        )
        values = {
            normalize_combination(combination, sources): float(value)
            for combination, value in group[[combination_col, value_col]].itertuples(
                index=False, name=None
            )
        }
        raw_values = (
            {
                normalize_combination(combination, sources): float(value)
                for combination, value in group[
                    [combination_col, raw_metric_col]
                ].itertuples(index=False, name=None)
            }
            if raw_metric_col in group
            else {}
        )
        higher_is_better = (
            bool(group["higher_is_better"].iloc[0])
            if "higher_is_better" in group
            else True
        )
        declared_reason = (
            str(group.loc[group["reason"].notna(), "reason"].iloc[0])
            if "reason" in group and group["reason"].notna().any()
            else None
        )
        try:
            if declared_reason is not None:
                raise ValueError(declared_reason)
            values = _normalized_value_mapping(values, sources)
            exclusion_reason = None
        except ValueError as exc:
            exclusion_reason = str(exc)
        for source in sources:
            marginal = []
            relative = []
            if exclusion_reason is None:
                for subset in information_combinations(
                    [item for item in sources if item != source]
                ):
                    with_source = subset | {source}
                    marginal.append(values[with_source] - values[subset])
                    if (
                        subset in raw_values
                        and with_source in raw_values
                        and raw_values[subset] != 0
                    ):
                        if higher_is_better:
                            numerator = raw_values[with_source] - raw_values[subset]
                        else:
                            numerator = raw_values[subset] - raw_values[with_source]
                        relative.append(numerator / abs(raw_values[subset]))
            full_without = full - {source}
            complete = exclusion_reason is None
            rows.append(
                {
                    **metadata,
                    "source": source,
                    "full_removal_gain": (
                        values[full] - values[full_without]
                        if full in values and full_without in values
                        else np.nan
                    ),
                    "mean_marginal_gain": float(np.mean(marginal))
                    if marginal
                    else np.nan,
                    "mean_relative_compensation": float(np.mean(relative))
                    if relative
                    else np.nan,
                    "n_marginal_pairs": len(marginal),
                    "excluded": not complete,
                    "missing_combinations": (
                        group["missing_combinations"].iloc[0]
                        if "missing_combinations" in group
                        else None
                    ),
                    "reason": None if complete else exclusion_reason,
                }
            )
    return pd.DataFrame(rows)


def knn_mutual_information(
    source: Sequence[float] | np.ndarray | pd.Series,
    target: Sequence[float] | np.ndarray | pd.Series,
    *,
    n_neighbors: int = 5,
    seed: int = 0,
) -> dict[str, Any]:
    """Estimate continuous mutual information with sklearn's kNN estimator."""

    x = pd.to_numeric(pd.Series(source), errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(pd.Series(target), errors="coerce").to_numpy(dtype=float)
    if len(x) != len(y):
        raise ValueError("source and target must align")
    valid = np.isfinite(x) & np.isfinite(y)
    if valid.sum() <= n_neighbors:
        return {
            "mutual_information": np.nan,
            "n": int(valid.sum()),
            "n_neighbors": int(n_neighbors),
            "reason": "insufficient paired observations",
        }
    estimate = mutual_info_regression(
        x[valid, None],
        y[valid],
        discrete_features=False,
        n_neighbors=int(n_neighbors),
        random_state=int(seed),
    )[0]
    return {
        "mutual_information": float(estimate),
        "n": int(valid.sum()),
        "n_neighbors": int(n_neighbors),
        "reason": None,
    }


def _quantile_discretize(values: np.ndarray, n_bins: int) -> tuple[np.ndarray, int]:
    labels = np.full(len(values), -1, dtype=int)
    valid = np.isfinite(values)
    if not valid.any():
        return labels, 0
    unique_values = np.unique(values[valid])
    if len(unique_values) <= n_bins:
        labels[valid] = np.searchsorted(unique_values, values[valid])
        return labels, len(unique_values)
    quantiles = np.linspace(0.0, 1.0, n_bins + 1)
    edges = np.unique(np.quantile(values[valid], quantiles))
    if len(edges) < 2:
        labels[valid] = 0
        return labels, 1
    internal = edges[1:-1]
    labels[valid] = np.digitize(values[valid], internal, right=False)
    return labels, len(edges) - 1


def _discrete_transfer_entropy(
    source_labels: np.ndarray,
    target_labels: np.ndarray,
    lag: int,
) -> tuple[float, int]:
    future_positions = np.arange(lag, len(target_labels))
    source_past = source_labels[future_positions - lag]
    target_past = target_labels[future_positions - 1]
    target_future = target_labels[future_positions]
    valid = (source_past >= 0) & (target_past >= 0) & (target_future >= 0)
    triples = list(
        zip(
            target_future[valid].tolist(),
            target_past[valid].tolist(),
            source_past[valid].tolist(),
            strict=True,
        )
    )
    n = len(triples)
    if n == 0:
        return np.nan, 0
    count_joint = Counter(triples)
    count_past_source = Counter((past, source) for _, past, source in triples)
    count_future_past = Counter((future, past) for future, past, _ in triples)
    count_past = Counter(past for _, past, _ in triples)
    estimate = 0.0
    for (future, past, source_value), count in count_joint.items():
        conditional_with_source = count / count_past_source[(past, source_value)]
        conditional_without_source = (
            count_future_past[(future, past)] / count_past[past]
        )
        estimate += (count / n) * math.log(
            conditional_with_source / conditional_without_source
        )
    return float(max(estimate, 0.0)), n


def transfer_entropy(
    source: Sequence[float] | np.ndarray | pd.Series,
    target: Sequence[float] | np.ndarray | pd.Series,
    *,
    lag: int = 1,
    n_bins: int = 4,
    n_permutations: int = 199,
    seed: int = 0,
) -> dict[str, Any]:
    """Estimate ``I(source[t-lag]; target[t] | target[t-1])``.

    Both series are discretized independently by empirical quantiles.  The null
    distribution circularly shifts the source labels, preserving their serial
    dependence while breaking their alignment with the target.  The p-value
    uses the standard plus-one correction.
    """

    if lag < 1:
        raise ValueError("lag must be positive")
    if n_bins < 2:
        raise ValueError("n_bins must be at least two")
    if n_permutations < 0:
        raise ValueError("n_permutations cannot be negative")
    x = pd.to_numeric(pd.Series(source), errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(pd.Series(target), errors="coerce").to_numpy(dtype=float)
    if len(x) != len(y):
        raise ValueError("source and target must align")
    if len(x) <= lag:
        return {
            "transfer_entropy": np.nan,
            "p_value": np.nan,
            "n": 0,
            "reason": "series is shorter than lag",
        }
    x_labels, effective_x_bins = _quantile_discretize(x, n_bins)
    y_labels, effective_y_bins = _quantile_discretize(y, n_bins)
    observed, n = _discrete_transfer_entropy(x_labels, y_labels, lag)
    if not np.isfinite(observed) or effective_x_bins < 2 or effective_y_bins < 2:
        return {
            "transfer_entropy": np.nan,
            "p_value": np.nan,
            "n": int(n),
            "lag": int(lag),
            "n_bins": int(n_bins),
            "reason": "both series need at least two occupied bins",
        }

    rng = np.random.default_rng(seed)
    null = np.empty(n_permutations, dtype=float)
    for index in range(n_permutations):
        shift = int(rng.integers(1, len(x_labels)))
        shifted = np.roll(x_labels, shift)
        null[index], _ = _discrete_transfer_entropy(shifted, y_labels, lag)
    if n_permutations:
        p_value = (1.0 + float(np.sum(null >= observed))) / (n_permutations + 1.0)
        null_mean = float(np.mean(null))
        null_std = float(np.std(null, ddof=0))
        z_score = (observed - null_mean) / null_std if null_std > 0 else np.nan
    else:
        p_value = null_mean = null_std = z_score = np.nan
    return {
        "transfer_entropy": float(observed),
        "p_value": float(p_value),
        "null_mean": null_mean,
        "null_std": null_std,
        "z_score": float(z_score),
        "n": int(n),
        "lag": int(lag),
        "n_bins": int(n_bins),
        "effective_source_bins": int(effective_x_bins),
        "effective_target_bins": int(effective_y_bins),
        "discretization": "independent empirical quantiles",
        "conditioning": "target(t-1)",
        "surrogate": "circular_shift",
        "permutation": "circular-shift surrogate permutation of source-bin labels",
        "n_permutations": int(n_permutations),
        "seed": int(seed),
        "reason": None,
    }


def transfer_entropy_by_lag(
    source: Sequence[float] | np.ndarray | pd.Series,
    target: Sequence[float] | np.ndarray | pd.Series,
    lags: Sequence[int],
    **kwargs: Any,
) -> pd.DataFrame:
    rows = []
    for offset, lag in enumerate(lags):
        parameters = dict(kwargs)
        parameters["seed"] = int(parameters.get("seed", 0)) + offset
        rows.append(transfer_entropy(source, target, lag=int(lag), **parameters))
    return pd.DataFrame(rows)


__all__ = [
    "INFORMATION_SOURCES",
    "INFORMATION_UNIT_GROUP_COLUMNS",
    "benjamini_hochberg_fdr",
    "build_value_function",
    "combination_label",
    "compensation_gains",
    "exact_shapley",
    "information_combinations",
    "knn_mutual_information",
    "normalize_combination",
    "shapley_table",
    "transfer_entropy",
    "transfer_entropy_by_lag",
]
