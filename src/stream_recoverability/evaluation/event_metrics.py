"""Event-level evaluation built on the strict approved/artificial mask."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from .metrics import (
    boundary_jump_metrics,
    compute_metrics,
    flow_metrics,
    level_metrics,
    quantile_metrics,
    temperature_metrics,
)


EVENT_ID_COLUMNS = [
    "scenario_id",
    "station_id",
    "model",
    "training_seed",
    "mask_seed",
    "target",
    "gap_length",
    "missing_rate",
    "pattern",
]

EVENT_METRIC_COLUMNS = [
    *EVENT_ID_COLUMNS,
    "n_evaluated",
    "MAE",
    "RMSE",
    "bias",
    "Pearson",
    "Spearman",
    "NMAE",
    "NRMSE",
    "skill",
    "boundary_jump_left",
    "boundary_jump_right",
    "coverage_90",
    "interval_width_90",
]


def _metadata_value(metadata: Mapping[str, Any], name: str) -> Any:
    aliases = {
        "pattern": ("pattern", "variable_pattern", "variables"),
        "mask_seed": ("mask_seed", "seed"),
        "gap_length": ("gap_length", "gap_lengths"),
    }
    candidates = aliases.get(name, (name,))
    for candidate in candidates:
        if candidate in metadata:
            value = metadata[candidate]
            if isinstance(value, np.ndarray):
                value = value.tolist()
            if isinstance(value, (list, tuple)) and len(value) == 1:
                return value[0]
            if name == "pattern" and isinstance(value, (list, tuple)):
                return "+".join(str(item) for item in value)
            return value
    return None


def compute_event_metrics(
    y_true: Sequence[float] | np.ndarray | pd.Series,
    y_pred: Sequence[float] | np.ndarray | pd.Series,
    quality_approved: Sequence[bool] | np.ndarray | pd.Series,
    artificial_mask: Sequence[bool] | np.ndarray | pd.Series,
    *,
    target: str,
    metadata: Mapping[str, Any] | None = None,
    climatology_pred: Sequence[float] | np.ndarray | pd.Series | None = None,
    dates: Sequence[object] | pd.Series | pd.DatetimeIndex | None = None,
    quantile_predictions: Mapping[float | str, Sequence[float] | np.ndarray | pd.Series]
    | None = None,
    high_threshold: float | None = None,
    low_threshold: float | None = None,
    ecological_threshold: float | None = None,
    normalization_iqr: float | None = None,
    normalization_std: float | None = None,
) -> dict[str, Any]:
    """Evaluate one complete mask episode and return a flat result row."""

    metadata = {} if metadata is None else dict(metadata)
    target_kind = str(target).split("_")[-1].upper()
    common_kwargs = {
        "climatology_pred": climatology_pred,
        "normalization_iqr": normalization_iqr,
        "normalization_std": normalization_std,
    }
    if target_kind == "T":
        values = temperature_metrics(
            y_true,
            y_pred,
            quality_approved,
            artificial_mask,
            dates=dates,
            high_threshold=high_threshold,
            ecological_threshold=ecological_threshold,
            **common_kwargs,
        )
    elif target_kind == "F":
        values = flow_metrics(
            y_true,
            y_pred,
            quality_approved,
            artificial_mask,
            dates=dates,
            high_threshold=high_threshold,
            low_threshold=low_threshold,
            **common_kwargs,
        )
    elif target_kind == "L":
        values = level_metrics(
            y_true,
            y_pred,
            quality_approved,
            artificial_mask,
            dates=dates,
            high_threshold=high_threshold,
            **common_kwargs,
        )
    else:
        values = compute_metrics(
            y_true,
            y_pred,
            quality_approved,
            artificial_mask,
            **common_kwargs,
        )
    values.update(
        boundary_jump_metrics(y_true, y_pred, quality_approved, artificial_mask)
    )
    if quantile_predictions:
        values.update(
            quantile_metrics(
                y_true,
                quantile_predictions,
                quality_approved,
                artificial_mask,
            )
        )

    row = {column: _metadata_value(metadata, column) for column in EVENT_ID_COLUMNS}
    row["target"] = target
    row.update(
        {
            "n_evaluated": values.pop("n", 0),
            "MAE": values.pop("mae", float("nan")),
            "RMSE": values.pop("rmse", float("nan")),
            "bias": values.pop("bias", float("nan")),
            "Pearson": values.pop("pearson", float("nan")),
            "Spearman": values.pop("spearman", float("nan")),
            "NMAE": values.pop("nmae", float("nan")),
            "NRMSE": values.pop("nrmse", float("nan")),
            "skill": values.pop("skill", float("nan")),
            "boundary_jump_left": values.pop("boundary_jump_left", float("nan")),
            "boundary_jump_right": values.pop("boundary_jump_right", float("nan")),
            "coverage_90": values.pop("coverage_90", float("nan")),
            "interval_width_90": values.pop("interval_width_90", float("nan")),
        }
    )
    row.update(values)
    return row


def event_metrics_from_frame(
    predictions: pd.DataFrame,
    *,
    truth_col: str = "y_true",
    prediction_col: str = "y_pred",
    quality_col: str = "quality_approved",
    artificial_col: str = "artificial_mask",
    date_col: str = "date",
    target_col: str = "target",
    climatology_col: str = "climatology_pred",
    group_cols: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Reduce a daily prediction table to one row per mask episode/model/target."""

    required = {truth_col, prediction_col, quality_col, artificial_col, target_col}
    missing = sorted(required - set(predictions.columns))
    if missing:
        raise KeyError(f"prediction table is missing required columns: {missing}")
    if group_cols is None:
        group_cols = [column for column in EVENT_ID_COLUMNS if column in predictions]
    else:
        group_cols = list(group_cols)

    quantile_cols = [
        column
        for column in predictions.columns
        if column.lower().startswith("q") and column[1:].isdigit()
    ]
    rows: list[dict[str, Any]] = []
    if group_cols:
        grouped = predictions.groupby(list(group_cols), dropna=False, sort=False)
        iterator = grouped
    else:
        iterator = [(None, predictions)]
    for _, group in iterator:
        if date_col in group:
            group = group.sort_values(date_col)
        metadata = {
            column: group.iloc[0][column]
            for column in predictions.columns
            if column
            in {
                *EVENT_ID_COLUMNS,
                "mask_type",
                "event_type",
                "season",
                "window_length",
                "variable_pattern",
                "seed",
                "gap_lengths",
            }
        }
        target = str(group.iloc[0][target_col])
        quantiles = {column: group[column] for column in quantile_cols}
        row = compute_event_metrics(
            group[truth_col],
            group[prediction_col],
            group[quality_col],
            group[artificial_col],
            target=target,
            metadata=metadata,
            climatology_pred=(
                group[climatology_col] if climatology_col in group else None
            ),
            dates=group[date_col] if date_col in group else None,
            quantile_predictions=quantiles or None,
        )
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=EVENT_METRIC_COLUMNS)
    result = pd.DataFrame(rows)
    leading = [column for column in EVENT_METRIC_COLUMNS if column in result]
    trailing = [column for column in result if column not in leading]
    return result.loc[:, [*leading, *trailing]]


evaluate_event = compute_event_metrics
evaluate_events = event_metrics_from_frame
build_event_metrics = event_metrics_from_frame


__all__ = [
    "EVENT_ID_COLUMNS",
    "EVENT_METRIC_COLUMNS",
    "build_event_metrics",
    "compute_event_metrics",
    "evaluate_event",
    "evaluate_events",
    "event_metrics_from_frame",
]
