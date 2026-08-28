"""Development-only air2stream-inspired temperature recovery sensitivity.

The model here is intentionally called a proxy rather than air2stream: it is
a ridge relation using air temperature, discharge, and annual phase, blended
with the observed two-sided temperature boundary.  It can diagnose whether a
basic process-input family changes loss ordering, but it cannot stand in for
the published air2stream differential-equation model.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from stream_recoverability.experiments.development_recovery import (
    auxiliary_features,
    year_split,
)


def process_features(
    index: pd.DatetimeIndex, air_temperature: pd.Series, discharge: pd.Series
) -> pd.DataFrame:
    """Construct the fixed Ta/F/season feature family."""

    phase = 2.0 * np.pi * (index.dayofyear.to_numpy(dtype=float) - 1.0) / np.where(
        index.is_leap_year, 366.0, 365.0
    )
    ta = pd.to_numeric(air_temperature, errors="coerce").to_numpy(dtype=float)
    flow = pd.to_numeric(discharge, errors="coerce").to_numpy(dtype=float)
    log_flow = np.full_like(flow, np.nan, dtype=float)
    nonnegative_flow = flow >= 0.0
    log_flow[nonnegative_flow] = np.log1p(flow[nonnegative_flow])
    sin_phase = np.sin(phase)
    cos_phase = np.cos(phase)
    return pd.DataFrame(
        {
            "air_temperature_c": ta,
            "log1p_discharge_m3s": log_flow,
            "season_sin": sin_phase,
            "season_cos": cos_phase,
            "air_x_season_sin": ta * sin_phase,
            "air_x_season_cos": ta * cos_phase,
        },
        index=index,
    )


def fit_process_hybrid(
    panel: pd.DataFrame,
    auxiliary: pd.DataFrame,
    target_station: str,
    *,
    minimum_training_rows: int = 365,
) -> tuple[object, pd.DataFrame, tuple[int, ...], tuple[int, ...]]:
    """Fit the proxy strictly in the outer training years."""

    station = str(target_station)
    if station not in panel.columns.astype(str):
        raise KeyError(f"target station absent: {station}")
    panel = panel.copy()
    panel.columns = panel.columns.astype(str)
    train_mask, training_years, evaluation_years = year_split(panel.index)
    aligned = auxiliary_features(
        auxiliary, target_station=station, target_index=panel.index
    )
    if "M__Ta" not in aligned or "H__F" not in aligned:
        raise ValueError("materialized target-site Ta and approved F are required")
    features = process_features(panel.index, aligned["M__Ta"], aligned["H__F"])
    target = pd.to_numeric(panel[station], errors="coerce")
    usable = train_mask & target.notna() & features.notna().all(axis=1)
    if int(usable.sum()) < minimum_training_rows:
        raise ValueError("insufficient timestamp-aligned Ta/F training rows")
    model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    model.fit(features.loc[usable], target.loc[usable])
    return model, features, training_years, evaluation_years


def hybrid_prediction(
    process_prediction: np.ndarray,
    *,
    left_boundary: float,
    right_boundary: float,
    gap_length: int,
    boundary_decay_days: float = 30.0,
) -> np.ndarray:
    """Blend process predictions with fixed two-sided boundary interpolation."""

    if gap_length <= 0 or boundary_decay_days <= 0:
        raise ValueError("gap and boundary decay must be positive")
    process = np.asarray(process_prediction, dtype=float)
    if process.shape != (gap_length,):
        raise ValueError("process prediction length differs from gap length")
    fraction = np.arange(1, gap_length + 1, dtype=float) / (gap_length + 1.0)
    boundary = left_boundary + fraction * (right_boundary - left_boundary)
    boundary_weight = float(np.exp(-gap_length / boundary_decay_days))
    return boundary_weight * boundary + (1.0 - boundary_weight) * process


def score_process_hybrid(
    network_id: str,
    panel: pd.DataFrame,
    auxiliary: pd.DataFrame,
    placements: pd.DataFrame,
    *,
    minimum_training_rows: int = 365,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    """Score all eligible existing B+D placements and return station-gap means."""

    panel = panel.copy().sort_index().asfreq("D")
    panel.columns = panel.columns.astype(str)
    network_rows = placements.loc[
        placements["network_id"].astype(str).eq(str(network_id))
        & placements["information_condition"].eq("B_union_D")
    ].copy()
    network_rows["station_id"] = network_rows["station_id"].astype(str)
    network_rows["gap_start"] = pd.to_datetime(network_rows["gap_start"])
    rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for station, selected in network_rows.groupby("station_id", sort=True):
        try:
            model, features, training_years, evaluation_years = fit_process_hybrid(
                panel,
                auxiliary,
                station,
                minimum_training_rows=minimum_training_rows,
            )
        except (KeyError, ValueError) as error:
            failures.append(
                {
                    "network_id": str(network_id),
                    "station_id": str(station),
                    "reason": str(error),
                }
            )
            continue
        for item in selected.itertuples(index=False):
            start = panel.index.get_indexer([pd.Timestamp(item.gap_start)])[0]
            gap = int(item.gap_length)
            if start < 1 or start + gap >= len(panel):
                continue
            truth = panel[station].iloc[start : start + gap].to_numpy(dtype=float)
            feature_gap = features.iloc[start : start + gap]
            left = float(panel[station].iloc[start - 1])
            right = float(panel[station].iloc[start + gap])
            if (
                not np.isfinite(truth).all()
                or feature_gap.isna().any(axis=None)
                or not np.isfinite([left, right]).all()
            ):
                continue
            process = model.predict(feature_gap)
            predicted = hybrid_prediction(
                process,
                left_boundary=left,
                right_boundary=right,
                gap_length=gap,
            )
            rows.append(
                {
                    "network_id": str(network_id),
                    "station_id": str(station),
                    "gap_length": gap,
                    "placement": int(item.placement),
                    "hybrid_mae_deg_c": float(np.mean(np.abs(predicted - truth))),
                    "xgboost_bd_mae_deg_c": float(item.mae_deg_c),
                    "training_years": "|".join(map(str, training_years)),
                    "evaluation_years": "|".join(map(str, evaluation_years)),
                }
            )
    scored = pd.DataFrame(rows)
    if scored.empty:
        return scored, failures
    station_gap = scored.groupby(
        [
            "network_id",
            "station_id",
            "gap_length",
            "training_years",
            "evaluation_years",
        ],
        as_index=False,
    ).agg(
        hybrid_mae_deg_c=("hybrid_mae_deg_c", "mean"),
        xgboost_bd_mae_deg_c=("xgboost_bd_mae_deg_c", "mean"),
        n_placements=("placement", "size"),
    )
    return station_gap, failures


__all__ = [
    "fit_process_hybrid",
    "hybrid_prediction",
    "process_features",
    "score_process_hybrid",
]
