"""Metrics for the strictly causal online-recovery protocol."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def observation_horizons(observed_mask: np.ndarray) -> np.ndarray:
    """Days since the last observation per channel; -1 means no prior history."""

    observed = np.asarray(observed_mask)
    if observed.dtype != np.bool_ or observed.ndim != 3:
        raise ValueError("observed_mask must be boolean (time, station, variable)")
    horizons = np.full(observed.shape, -1, dtype=np.int32)
    last = np.full(observed.shape[1:], -1, dtype=np.int64)
    for index in range(len(observed)):
        missing = ~observed[index]
        has_history = last >= 0
        horizons[index][missing & has_history] = (
            index - last[missing & has_history]
        ).astype(np.int32)
        horizons[index][~missing] = 0
        last[~missing] = index
    return horizons


def _metrics(
    truth: np.ndarray, prediction: np.ndarray, climatology: np.ndarray
) -> dict[str, float | int]:
    error = prediction - truth
    climatology_error = climatology - truth
    mae = float(np.mean(np.abs(error)))
    climatology_mae = float(np.mean(np.abs(climatology_error)))
    skill = 1.0 - mae / climatology_mae if climatology_mae > 0 else 0.0
    return {
        "hidden_cells": int(len(truth)),
        "MAE": mae,
        "RMSE": float(np.sqrt(np.mean(np.square(error)))),
        "climatology_MAE": climatology_mae,
        "skill": skill,
    }


def _horizon_label(value: int) -> tuple[str, int]:
    if value < 0:
        return "no_history", 0
    if value == 1:
        return "1", 1
    if value <= 3:
        return "2-3", 2
    if value <= 7:
        return "4-7", 3
    if value <= 30:
        return "8-30", 4
    if value <= 90:
        return "31-90", 5
    return "91+", 6


def score_online_predictions(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    approved: np.ndarray,
    artificial_mask: np.ndarray,
    climatology_pred: np.ndarray,
    *,
    metadata: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Score only finite cells satisfying ``approved & artificial_mask``."""

    truth = np.asarray(y_true, dtype=float)
    prediction = np.asarray(y_pred, dtype=float)
    climatology = np.asarray(climatology_pred, dtype=float)
    approved_array = np.asarray(approved)
    artificial = np.asarray(artificial_mask)
    if truth.ndim != 3:
        raise ValueError("arrays must have shape (time, station, variable)")
    if prediction.shape != truth.shape or climatology.shape != truth.shape:
        raise ValueError("prediction and climatology must match y_true")
    if approved_array.dtype != np.bool_ or approved_array.shape != truth.shape:
        raise ValueError("approved must be boolean and match y_true")
    if artificial.dtype != np.bool_ or artificial.shape != truth.shape:
        raise ValueError("artificial_mask must be boolean and match y_true")
    target = approved_array & artificial & np.isfinite(truth)
    if not target.any():
        raise ValueError("no approved artificial targets are available for scoring")
    if not np.isfinite(prediction[target]).all() or not np.isfinite(climatology[target]).all():
        raise ValueError("predictions must be finite at scored cells")

    common = dict(metadata or {})
    overall = {
        **common,
        **_metrics(truth[target], prediction[target], climatology[target]),
    }
    observed = approved_array & np.isfinite(truth) & ~artificial
    horizons = observation_horizons(observed)
    labels = np.empty(truth.shape, dtype=object)
    orders = np.empty(truth.shape, dtype=np.int8)
    for value in np.unique(horizons[target]):
        label, order = _horizon_label(int(value))
        selected = horizons == value
        labels[selected] = label
        orders[selected] = order
    rows: list[dict[str, Any]] = []
    for order in sorted(np.unique(orders[target])):
        selected = target & (orders == order)
        label = str(labels[selected][0])
        horizon_values = horizons[selected]
        rows.append(
            {
                **common,
                "horizon_bin": label,
                "horizon_order": int(order),
                "minimum_horizon_days": int(horizon_values.min()),
                "maximum_horizon_days": int(horizon_values.max()),
                **_metrics(
                    truth[selected], prediction[selected], climatology[selected]
                ),
            }
        )
    return overall, pd.DataFrame(rows)
